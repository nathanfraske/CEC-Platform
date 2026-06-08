#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_judge_local -- local-vLLM realisation of the cec_router MANAGER judge tier (Thrust A).
# ============================================================================
# Wires a LOCAL vLLM OpenAI-compatible server (the Qwen3-Coder-30B-A3B AWQ judge on the workstation
# 5090) into cec_router's `manager=` slot, using vLLM GUIDED JSON constrained to the Verdict schema
# (docs/local-compute-exploration.md Thrust A: "the ~90% mechanical manager/worker volume runs local;
# cloud Opus stays for structural re-plan").
#
# FAIL-SAFE + HYBRID by construction:
#   * ANY failure (server down/loading, HTTP error, timeout, bad JSON) -> falls back to
#     cec_router.default_manager. A route NEVER breaks because the LLM is unavailable.
#   * the LLM CANNOT widen the safety envelope: route() only accepts when the best candidate already
#     has gates_pass (kelvin_ok + diffpair_ok), and we additionally downgrade an `accept` to `repair`
#     if the best candidate is not gate-passing. The hard gates + the independent DRC own correctness;
#     the LLM only chooses among already-safe outcomes (accept finishing-residual vs repair vs escalate).
#
#   from cec_judge_local import make_manager, available
#   route(board, spec, manager=make_manager(spec))     # if available() else the deterministic default
# ============================================================================
import os
import sys
import json
import time
import shutil
import subprocess
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

# cec_router / cec_score are imported LAZILY (inside make_manager/_context) -- they pull pcbnew, which
# is absent on the host. Keeping the module top pcbnew-free lets the LIFECYCLE + HTTP run on the host
# (where docker access lives) so the gate can start/stop the GPU server on demand.

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# inside the routing container the server is reachable as the compose service `inference`;
# from the host it is http://localhost:8000. Override with CEC_VLLM_URL.
VLLM_URL = os.environ.get("CEC_VLLM_URL", "http://localhost:8000/v1").rstrip("/")
MODEL = os.environ.get("CEC_VLLM_MODEL_NAME", "cec-judge")     # --served-model-name in compose
TIMEOUT = float(os.environ.get("CEC_VLLM_TIMEOUT", "120"))   # absorbs the cold first guided-JSON grammar compile
TIER = "local:qwen3-coder-30b-awq"

# guided-JSON schema the server is constrained to (vLLM structured outputs)
VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["accept", "repair", "escalate"]},
        "reason": {"type": "string"},
    },
    "required": ["action", "reason"],
    "additionalProperties": False,
}

SYSTEM = (
    "You are the MANAGER judge tier in an automated PCB routing loop for the CEC power-telemetry "
    "platform. You are shown the scored Freerouting candidates for ONE region (best first) and must "
    "choose exactly ONE action.\n"
    "HARD RULES:\n"
    "1. `kelvin_ok` and `diffpair_ok` are HARD SAFETY GATES. NEVER choose `accept` unless the best "
    "candidate has gates_pass=true (both gates true).\n"
    "2. When gates_pass=true, a small residual `drc` and a couple of `unconnected` are normally "
    "finishing/cosmetic (silk, a decorative logo keepout, a shield-tab tie) -- prefer `accept`.\n"
    "3. If a hard gate is false (the sense pair or USB diff pair is not fully routed), choose "
    "`repair` -- the loop will bump Freerouting effort and re-route.\n"
    "4. If repairs have already run for several iterations with no improvement in drc/unconnected, "
    "choose `escalate` (a structural re-plan is needed).\n"
    "Reply ONLY with the JSON object {\"action\":..., \"reason\":...}. Keep the reason under 30 words."
)


def _post(path, payload, timeout=None):
    req = urllib.request.Request(VLLM_URL + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout or TIMEOUT) as r:
        return json.load(r)


def available(timeout=3):
    """True if the vLLM server answers /models (the judge is up). Cheap pre-check before wiring."""
    try:
        with urllib.request.urlopen(VLLM_URL + "/models", timeout=timeout) as r:
            return bool(json.load(r).get("data"))
    except Exception:
        return False


def _chat_json(system, user, schema, *, name="out", temperature=0.0, max_tokens=400, timeout=None):
    """One guided-JSON call constrained to `schema` -> the parsed dict. Raises on any transport/parse
    error (callers wrap this and fall back to the deterministic policy). `temperature` > 0 gives a
    diverse reply for swarm replicas."""
    payload = {
        "model": MODEL,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_schema",
                            "json_schema": {"name": name, "schema": schema, "strict": True}},
    }
    resp = _post("/chat/completions", payload, timeout=timeout)
    return json.loads(resp["choices"][0]["message"]["content"])


def chat_verdict(system, user, *, timeout=None, temperature=0.0):
    """One guided-JSON manager-verdict call -> {action, reason}."""
    return _chat_json(system, user, VERDICT_SCHEMA, name="verdict",
                      temperature=temperature, timeout=timeout)


def _context(region, scored, history, spec):
    """Pack the manager's decision context as JSON the judge reads (same metric shape as the
    DecisionLog) -- the top candidates + the best candidate's failing hard-gate reasons."""
    import cec_router
    import cec_score
    cands = [cec_router.DecisionLog._m(m) for _, m in scored[:4]]
    best = scored[0][1] if scored else None
    reasons = (cec_score.gate(best, cec_router.region_rules(region, spec))[1][:4]
               if best is not None else ["no candidate routed"])
    return json.dumps({
        "region": getattr(region, "name", "all"),
        "iteration": len(history) + 1,
        "prior_iterations": len(history),
        "candidates_best_first": cands,
        "best_candidate_gate_failures": reasons,
    }, indent=1)


def make_manager(spec, *, verbose=False):
    """Return a cec_router `manager(region, scored, history)` backed by the local LLM, with a
    deterministic fallback. Drop straight into route(..., manager=make_manager(spec))."""
    import cec_router

    def _fallback(region, scored, history):
        return cec_router.default_manager(region, scored, history, spec)

    def manager(region, scored, history):
        try:
            user = _context(region, scored, history, spec)
            v = chat_verdict(SYSTEM, user)
            action = v.get("action", "repair")
            best = scored[0][1] if scored else None
            if action == "accept" and not (best is not None and best.gates_pass):
                action = "repair"            # SAFETY: never accept a non-gate-passing board
            if action not in ("accept", "repair", "escalate"):
                action = "repair"
            if verbose:
                print(f"[judge:local] {getattr(region,'name','all')} -> {action}: {v.get('reason','')[:80]}")
            return cec_router.Verdict(action, str(v.get("reason", ""))[:200], tier=TIER)
        except Exception as e:
            fb = _fallback(region, scored, history)
            fb.tier = (fb.tier or "") + f" (local-judge-fallback:{type(e).__name__})"
            if verbose:
                print(f"[judge:local] FALLBACK ({type(e).__name__}: {e}) -> {fb.action}")
            return fb

    return manager


def swarm_judge(contexts, *, max_workers=8, timeout=None):
    """Fire N judge calls CONCURRENTLY at the batched vLLM -- the local AGENT SWARM (Thrust A: one
    batched server serves the swarm, not many small servers). `contexts` is a list of user-message
    JSON strings; returns a list of verdict dicts (or {"error":...}) aligned with `contexts`. The
    batched server interleaves the concurrent requests, so wall-clock for N << N x single-call."""
    from concurrent.futures import ThreadPoolExecutor

    def _one(user):
        try:
            return chat_verdict(SYSTEM, user, timeout=timeout)
        except Exception as e:
            return {"error": type(e).__name__}

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        return list(ex.map(_one, contexts))


# ===========================================================================
#  TRUE AGENT SWARM -- the manager + worker + dispatch tiers as CONCURRENT, PERSPECTIVE-DIVERSE,
#  VOTED panels of local agents (the batched vLLM serves them in parallel). Wires into
#  cec_router.route(manager=, worker=) and cec_dispatch.agent_route(tiers=).
# ===========================================================================
# Each manager decision is judged by a PANEL of agents, each with a DISTINCT LENS, then voted --
# diversity catches failure modes a single judge misses, and the vote is conservative (an `accept`
# needs a true majority AND a gate-passing candidate; disagreement falls to the safer action).
MANAGER_LENSES = [
    ("safety", "You are the SAFETY lens of a routing MANAGER panel. Judge ONLY the hard safety gates: "
               "choose `accept` IFF the best candidate has gates_pass=true (kelvin_ok AND diffpair_ok). "
               "If either is false (the shunt-sense pair or USB diff pair is not fully routed), choose "
               "`repair`. Never weigh cosmetics. Reply JSON {action,reason} (reason < 25 words)."),
    ("finishing", "You are the FINISHING lens of a routing MANAGER panel. Assume the hard gates are "
                  "judged elsewhere. Decide whether the residual drc/unconnected is FINISHING/cosmetic "
                  "(a decorative LOGO touching only GND, the RJ-45 shield tabs SH1/SH2, or a "
                  "same-footprint false short) versus a REAL fault. If gates_pass=true and the residual "
                  "is finishing-only, `accept`; if a real fault remains, `repair`. JSON {action,reason}."),
    ("progress", "You are the PROGRESS lens of a routing MANAGER panel. Judge the trajectory across "
                 "iterations: if drc/unconnected are improving, `repair` (keep going); if they have "
                 "STALLED for two or more iterations with no improvement, `escalate` (structural re-plan); "
                 "if the best candidate already passes the gates cleanly, `accept`. JSON {action,reason}."),
]


def _escalate_corroborated(drc_trail, loci):
    """Deterministic guard so the structural lens can't over-escalate (verify pattern): escalate is
    justified by the METRICS, not just a lens's word -- the DRC has STALLED (>=3 identical recent
    values, FR's deterministic no-progress signature) OR a DRC locus shorts two DIFFERENT functional
    nets (a real cross-net fault more routing won't fix). A still-improving / merely-unrouted board
    does NOT corroborate -> the escalate is downgraded to repair."""
    import re
    trail = [d for d in (drc_trail or []) if isinstance(d, (int, float))]
    for lc in (loci or []):
        nets = re.findall(r"\[(/[^\]]+|\+[0-9A-Za-z_]+)\]", str(lc.get("where", "")))
        if len({n for n in nets if n != "GND"}) >= 2:
            return True
    return len(trail) >= 3 and len(set(trail[-3:])) == 1


def _vote(votes, valid_actions, *, accept_ok, accept_word="accept", escalate_word="escalate",
          repair_word="repair", escalate_lens=None, escalate_ok=True):
    """DIMENSION-AWARE aggregation of (lens, action, reason) votes -> (action, tally, picks). Each lens
    judges a DIFFERENT dimension, so a naive majority is wrong (only ONE lens is qualified to call
    escalate). Rules: (1) the `escalate_lens` is AUTHORITATIVE on escalate -- if it (or a majority)
    escalates, escalate, since it's the only lens judging structural/stall merit; (2) else accept only
    when accept_ok AND >=1 lens accepts AND none escalate AND accept is not outvoted by repair (the
    SAFETY lens owns the accept gate); (3) else repair. Conservative: ties favor the safer action."""
    valid = []
    for (ln, a, r) in votes:
        if a == accept_word and not accept_ok:
            a = repair_word          # SAFETY: never accept a non-gate-passing candidate
        if a == escalate_word and not escalate_ok:
            a = repair_word          # VERIFY: an uncorroborated escalate (lens over-fired) -> repair
        if a in valid_actions:
            valid.append((ln, a, r))
    if not valid:
        return None, Counter(), ""
    tally = Counter(a for (_, a, _) in valid)
    n = len(valid)
    by = {ln: a for (ln, a, _) in valid}
    picks = "; ".join(f"{ln}:{a}" for (ln, a, _) in valid)
    if (escalate_lens and by.get(escalate_lens) == escalate_word) or tally.get(escalate_word, 0) > n / 2:
        return escalate_word, tally, picks
    if accept_ok and tally.get(accept_word, 0) >= 1 and tally.get(escalate_word, 0) == 0 \
            and tally.get(accept_word, 0) >= tally.get(repair_word, 0):
        return accept_word, tally, picks
    return repair_word, tally, picks


def _panel(user_or_fn, lenses, schema, *, name, temps=None, max_workers=None):
    """Fire one judge per lens CONCURRENTLY at the batched server. `user_or_fn` is a user string (same
    for all) or a fn(lens_name)->user. Returns [(lens_name, dict|None), ...]."""
    temps = temps or {}

    def one(idx_lens):
        idx, (lname, lsys) = idx_lens
        user = user_or_fn(lname) if callable(user_or_fn) else user_or_fn
        try:
            return (lname, _chat_json(lsys, user, schema, name=name, temperature=temps.get(idx, 0.0)))
        except Exception as e:
            return (lname, {"error": type(e).__name__})

    with ThreadPoolExecutor(max_workers=max_workers or len(lenses)) as ex:
        return list(ex.map(one, list(enumerate(lenses))))


def make_manager_swarm(spec, *, panel=3, verbose=False):
    """A TRUE manager SWARM for cec_router.route's manager= slot: `panel` concurrent local agents,
    each a distinct lens (safety / finishing / progress, cycled with temperature for replicas), voting
    on accept/repair/escalate. Fail-safe -> default_manager; cannot accept a non-gate-passing board."""
    import cec_router
    lenses = [MANAGER_LENSES[i % len(MANAGER_LENSES)] for i in range(max(1, panel))]
    temps = {i: (0.0 if i < len(MANAGER_LENSES) else 0.4) for i in range(len(lenses))}

    def manager(region, scored, history):
        try:
            user = _context(region, scored, history, spec)
            best = scored[0][1] if scored else None
            results = _panel(user, lenses, VERDICT_SCHEMA, name="verdict", temps=temps)
            votes = [(ln, (d or {}).get("action"), str((d or {}).get("reason", ""))) for ln, d in results]
            trail = [h["best"].drc for h in (history or []) if h.get("best") is not None] \
                + ([best.drc] if best is not None else [])
            esc_ok = _escalate_corroborated(trail, [])
            action, tally, picks = _vote(votes, ("accept", "repair", "escalate"),
                                         accept_ok=bool(best is not None and best.gates_pass),
                                         escalate_lens="progress", escalate_ok=esc_ok)
            if action is None:
                raise RuntimeError("no valid panel vote")
            if verbose:
                print(f"[swarm-mgr] {getattr(region,'name','all')} panel={dict(tally)} -> {action}")
            return cec_router.Verdict(action, f"panel {dict(tally)} -> {action} | {picks}"[:240],
                                      tier=f"local-swarm-mgr({sum(tally.values())})")
        except Exception as e:
            fb = cec_router.default_manager(region, scored, history, spec)
            fb.tier = (fb.tier or "") + f" (swarm-fallback:{type(e).__name__})"
            return fb

    return manager


WORKER_SYS = (
    "You are a WORKER in a routing REPAIR swarm. The manager asked to repair a route whose hard gate "
    "failed (unrouted ratlines). Given the current Freerouting effort and the failure reason, propose "
    "NEW effort to clear it: more routing passes and/or more optimization seconds. Be decisive but "
    "bounded: passes 1..60, opt_time 1..120, and at least a real increase over current. Reply JSON "
    "{passes:int, opt_time:int, reason}."
)
WORKER_SCHEMA = {
    "type": "object",
    "properties": {"passes": {"type": "integer"}, "opt_time": {"type": "integer"},
                   "reason": {"type": "string"}},
    "required": ["passes", "opt_time", "reason"], "additionalProperties": False,
}


def make_worker_swarm(spec, *, fanout=3, verbose=False):
    """A TRUE worker SWARM for cec_router.route's worker= slot: `fanout` concurrent agents each propose
    a repair effort (passes/opt_time), aggregated to a CONSENSUS (mean, bounded, > current). Fail-safe
    -> default_worker."""
    import cec_router

    def worker(region, verdict, state, history):
        cur_p, cur_o = int(state.fr.get("passes", 10)), int(state.fr.get("opt_time", 30))
        try:
            user = json.dumps({"current_passes": cur_p, "current_opt_time": cur_o,
                               "gate_failure_reason": str(verdict.reason)[:200],
                               "iteration": len(history) + 1})

            def one(i):
                try:
                    r = _chat_json(WORKER_SYS, user, WORKER_SCHEMA, name="effort",
                                   temperature=(0.0 if i == 0 else 0.5))
                    return (min(max(int(r["passes"]), 1), 60), min(max(int(r["opt_time"]), 1), 120))
                except Exception:
                    return None

            with ThreadPoolExecutor(max_workers=fanout) as ex:
                props = [p for p in ex.map(one, range(fanout)) if p]
            if not props:
                raise RuntimeError("no worker proposal")
            P = max(cur_p + 1, min(60, round(sum(p for p, _ in props) / len(props))))
            O = max(cur_o + 1, min(120, round(sum(o for _, o in props) / len(props))))
            if verbose:
                print(f"[swarm-wrk] {len(props)} proposals -> passes={P} opt={O}")
            return cec_router.Verdict("repair", f"swarm worker({len(props)}) consensus passes={P} opt={O}",
                                      tier=f"local-swarm-wrk({len(props)})",
                                      edit={"type": "fr_params", "set": {"passes": P, "opt_time": O}})
        except Exception as e:
            fb = cec_router.default_worker(region, verdict, state, history, spec)
            fb.tier = (fb.tier or "") + f" (swarm-fallback:{type(e).__name__})"
            return fb

    return worker


DISPATCH_LENSES = [
    ("safety", "You are the SAFETY lens of a candidate-judge SWARM tier. `accept` IFF the best candidate "
               "has gates_pass=true (kelvin_ok AND diffpair_ok); else `request_more` (route harder). "
               "Reply JSON {action,reason}."),
    ("finishing", "You are the FINISHING lens. If gates_pass=true and the residual drc is finishing-only "
                  "per the gate_note (LOGO-on-GND, shield tabs, same-footprint false short), `accept`; if "
                  "a real fault remains, `request_more`. JSON {action,reason}."),
    ("structural", "You are the STRUCTURAL lens. Choose `escalate` (defer UP a tier for a re-plan) ONLY "
                   "when more Freerouting passes won't help: the best candidate has a REAL fault between "
                   "two DIFFERENT functional nets (a genuine short/clearance per the gate_note -- NOT a "
                   "finishing LOGO/shield/same-footprint item), OR drc/unconnected have NOT improved "
                   "across the prior `history` rounds (stalled). Otherwise `request_more` (still improving) "
                   "or `accept` (gates pass + finishing-only). Budget-exhaustion is handled by the loop, "
                   "not you -- escalate on the MERITS. JSON {action,reason}."),
]
DISPATCH_SCHEMA = {
    "type": "object",
    "properties": {"action": {"type": "string", "enum": ["accept", "request_more", "escalate"]},
                   "reason": {"type": "string"}},
    "required": ["action", "reason"], "additionalProperties": False,
}


def make_dispatch_swarm_tier(*, panel=3, tier_name="local-haiku-swarm", verbose=False):
    """A cec_dispatch decide(JudgeContext)->Verdict SWARM tier (the parallel 'Haiku swarm' rung of
    agent_route): `panel` concurrent diverse-lens agents vote accept/request_more/escalate. Fail-safe
    -> cec_dispatch.det_haiku."""
    import cec_dispatch
    lenses = [DISPATCH_LENSES[i % len(DISPATCH_LENSES)] for i in range(max(1, panel))]
    temps = {i: (0.0 if i < len(DISPATCH_LENSES) else 0.4) for i in range(len(lenses))}

    def decide(ctx):
        try:
            cands = ctx.candidates or []
            best = cands[0] if cands else None
            hist = [{"round": i, "drc": h.get("best_drc"), "unconnected": h.get("best_unconnected"),
                     "verdict": h.get("verdict")} for i, h in enumerate(ctx.history or [])]
            user = json.dumps({"candidates_best_first": cands[:4], "budget_left": ctx.budget_left,
                               "history_drc_trail": hist, "gate_note": ctx.gate_note}, default=str)
            results = _panel(user, lenses, DISPATCH_SCHEMA, name="verdict", temps=temps)
            votes = [(ln, (d or {}).get("action"), str((d or {}).get("reason", ""))) for ln, d in results]
            trail = [h.get("best_drc") for h in (ctx.history or [])] + [(best or {}).get("drc")]
            esc_ok = _escalate_corroborated(trail, (best or {}).get("drc_loci"))
            action, tally, picks = _vote(votes, ("accept", "request_more", "escalate"),
                                         accept_ok=bool(best and best.get("gates_pass")),
                                         repair_word="request_more", escalate_lens="structural",
                                         escalate_ok=esc_ok)
            if action is None:
                return cec_dispatch.det_haiku(ctx)
            if verbose:
                print(f"[swarm-tier:{tier_name}] panel={dict(tally)} -> {action}")
            if action == "accept":
                return cec_dispatch.Verdict("accept", seed=(best or {}).get("seed"),
                                            reason=f"swarm {dict(tally)} | {picks}"[:200], tier=tier_name)
            if action == "escalate":
                return cec_dispatch.Verdict("escalate", reason=f"swarm {dict(tally)}"[:200], tier=tier_name)
            opt = (ctx.history[-1].get("params", {}).get("opt_time", 12) if ctx.history else 12)
            return cec_dispatch.Verdict("request_more", params={"opt_time": int(opt * 1.6)},
                                        reason=f"swarm {dict(tally)} | {picks}"[:200], tier=tier_name)
        except Exception:
            return cec_dispatch.det_haiku(ctx)

    decide.tier_name = tier_name
    return decide


def differentiated_test(*, panel=3, verbose=True):
    """PROVE (or disprove) that the swarm makes DISTINCT, correct calls -- the open question from the
    Opus-team stress test (identical-outcome boards couldn't show it). Feeds the dispatch swarm three
    contexts whose CORRECT answer differs and checks it returns accept / request_more / escalate:
      * accept-now           : clean, gate-passing, drc=0           -> accept
      * real-repair          : a hard gate fails, but improving      -> request_more
      * structural-escalate  : gates 'pass' yet a REAL cross-net short, STALLED at drc=40 -> escalate
    Returns {scenario: {expected, got, ok, reason}}. Needs the vLLM server up."""
    import cec_dispatch
    GN = cec_dispatch.GATE_NOTE
    tier = make_dispatch_swarm_tier(panel=panel)

    def cand(**kw):
        b = dict(seed=0, params={}, board="b", drc=0, unconnected=0, kelvin_ok=True, diffpair_ok=True,
                 gates_pass=True, tracks=500, vias=80, drc_types={}, drc_loci=[], unconn_nets=[])
        b.update(kw)
        return b

    scen = {
        "accept-now": ("accept", cec_dispatch.JudgeContext(
            board="b", tier="haiku", budget_left=2, gate_note=GN, history=[],
            candidates=[cand(gates_pass=True)])),
        "real-repair": ("request_more", cec_dispatch.JudgeContext(
            board="b", tier="haiku", budget_left=2, gate_note=GN,
            history=[{"verdict": "request_more", "best_drc": 22, "best_unconnected": 26}],   # improving 26->14
            candidates=[cand(drc=12, unconnected=14, kelvin_ok=False, gates_pass=False,
                             drc_types={"clearance": 12},
                             drc_loci=[{"where": "unrouted sense pair SENSEC1_HI/SENSEC1_LO", "type": "clearance"}],
                             unconn_nets=["/SENSEC1_HI", "/SENSEC1_LO"])])),
        "structural-escalate": ("escalate", cec_dispatch.JudgeContext(
            board="b", tier="haiku", budget_left=2, gate_note=GN,
            history=[{"verdict": "request_more", "best_drc": 40, "best_unconnected": 8},
                     {"verdict": "request_more", "best_drc": 40, "best_unconnected": 8},
                     {"verdict": "request_more", "best_drc": 40, "best_unconnected": 8}],   # STALLED at 40
            candidates=[cand(drc=40, unconnected=8, gates_pass=False, drc_types={"shorting_items": 40},
                             drc_loci=[{"where": "clearance: +3V3 track to /USB_DP via < 0.1mm [+3V3] [/USB_DP]",
                                        "type": "shorting_items"}], unconn_nets=[])])),
    }
    out = {}
    for name, (exp, ctx) in scen.items():
        v = tier(ctx)
        ok = (v.action == exp)
        out[name] = {"expected": exp, "got": v.action, "ok": ok, "reason": str(v.reason)[:160]}
        if verbose:
            print(f"  [{'OK' if ok else 'XX'}] {name:21s} expected={exp:13s} got={v.action:13s}  {str(v.reason)[:80]}")
    n = sum(1 for r in out.values() if r["ok"])
    if verbose:
        print(f"  -> {n}/{len(out)} distinct scenarios judged correctly by the local swarm")
    return out


# ===========================================================================
#  ON-DEMAND LIFECYCLE GATE -- spin the GPU server up only when needed, warm it, free VRAM after.
# ===========================================================================
# The vLLM server holds ~0.85 x VRAM for as long as it runs, so it is profile-gated in compose
# (never auto-started) and managed here. These shell out to `docker compose` -> run them on the HOST
# (the routing container has no docker socket). ensure_up() is idempotent (no-op if already serving).
def _compose(*args, capture=True):
    cf = os.path.join(ROOT, "docker", "compose.yaml")
    return subprocess.run(["docker", "compose", "-f", cf, *args], capture_output=capture, text=True)


def warmup(*, timeout=180, verbose=True):
    """Compile the guided-JSON grammar NOW (one tiny structured call) so the first real judge call is
    fast instead of paying the cold first-compile (which would otherwise time out -> a fallback)."""
    try:
        t0 = time.time()
        chat_verdict(SYSTEM,
                     '{"region":"warmup","iteration":1,"candidates_best_first":[],'
                     '"best_candidate_gate_failures":[]}', timeout=timeout)
        if verbose:
            print(f"[judge:gate] grammar warmup done in {time.time() - t0:.0f}s")
        return True
    except Exception as e:
        if verbose:
            print(f"[judge:gate] warmup skipped ({type(e).__name__})")
        return False


def ensure_up(*, warm=True, timeout=600, poll=4.0, verbose=True):
    """Bring the vLLM judge UP on demand and (warm=True) compile the grammar. Idempotent: if it is
    already serving, just warm. Returns True once /v1/models answers. Needs the host `docker` CLI."""
    if available(timeout=3):
        if warm:
            warmup(verbose=verbose)
        return True
    if not shutil.which("docker"):
        if verbose:
            print("[judge:gate] docker CLI not on PATH -> cannot autostart vLLM (start it manually)")
        return False
    if verbose:
        print("[judge:gate] starting vLLM inference service on demand (this holds ~0.85x VRAM while up)...")
    r = _compose("--profile", "inference", "up", "-d", "inference")
    if r.returncode != 0:
        if verbose:
            print("[judge:gate] compose up failed:", (r.stderr or "")[-300:])
        return False
    t0 = time.time()
    while time.time() - t0 < timeout:
        if available(timeout=3):
            if verbose:
                print(f"[judge:gate] vLLM ready in {time.time() - t0:.0f}s")
            if warm:
                warmup(verbose=verbose)
            return True
        time.sleep(poll)
    if verbose:
        print(f"[judge:gate] vLLM not ready after {timeout}s (model still loading?)")
    return False


def shutdown(*, verbose=True):
    """Stop the vLLM service -> frees the GPU VRAM. Safe no-op if docker is absent / already stopped."""
    if not shutil.which("docker"):
        return False
    r = _compose("stop", "inference")
    if verbose:
        print("[judge:gate] vLLM stopped, VRAM freed" if r.returncode == 0 else "[judge:gate] stop failed")
    return r.returncode == 0


if __name__ == "__main__":
    # Host-side gate CLI: manage the on-demand GPU judge + a smoke test.
    import argparse
    ap = argparse.ArgumentParser(description="cec_judge_local -- local vLLM judge gate + smoke")
    ap.add_argument("cmd", nargs="?", default="status",
                    choices=["up", "down", "warm", "status", "smoke", "diff-test"],
                    help="up=start+warm, down=stop (free VRAM), warm, status, smoke=judge a fake candidate, "
                         "diff-test=prove the swarm differentiates accept/repair/escalate")
    ap.add_argument("--url", default=VLLM_URL)
    ap.add_argument("--timeout", type=int, default=600, help="seconds to wait for the server to come up")
    a = ap.parse_args()
    VLLM_URL = a.url.rstrip("/")

    if a.cmd == "up":
        sys.exit(0 if ensure_up(timeout=a.timeout) else 1)
    if a.cmd == "down":
        sys.exit(0 if shutdown() else 1)
    if a.cmd == "warm":
        sys.exit(0 if warmup() else 1)
    if a.cmd == "diff-test":
        if not available():
            print("vLLM down -- run 'up' first")
            sys.exit(2)
        res = differentiated_test(panel=3)
        sys.exit(0 if all(r["ok"] for r in res.values()) else 1)
    if a.cmd == "status":
        print(f"server URL: {VLLM_URL} | model: {MODEL} | available: {available()}")
        sys.exit(0)
    # smoke: a gate-passing finishing-residual candidate -> expect accept
    print(f"server URL: {VLLM_URL} | model: {MODEL} | available: {available()}")
    if available():
        user = json.dumps({"region": "all", "iteration": 2, "prior_iterations": 1,
                           "candidates_best_first": [{"drc": 4, "unconnected": 2, "tracks": 556,
                               "vias": 84, "kelvin_ok": True, "diffpair_ok": True, "gates_pass": True}],
                           "best_candidate_gate_failures": []}, indent=1)
        print("verdict:", chat_verdict(SYSTEM, user))
