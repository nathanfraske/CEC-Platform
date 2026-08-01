#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_dispatch -- the COMPUTE-AS-TOOLS layer + the budgeted tier-escalation loop
#                  for the AGENTIC control plane (the "tighten the coupling" design).
# ============================================================================
# The two-plane router kept the heavy CPU (Freerouting / scoring / FEA) and the LLM judgement
# DETACHED: compute ran a blind batch, judgement happened after. This module makes the compute
# a set of discrete TOOLS a tier agent calls ON DEMAND, and gives a budgeted escalation loop the
# agents drive and defer up from:
#
#   TOOLS (request -> structured METRICS the agent reasons on, never raw boards):
#     request_candidates(board, params, seeds, where)  -> [CandidateMetrics]   (FR + score)
#     score_board(board)                               -> dict
#     render(board, png)                               -> png
#
#   LOOP:  agent_route(board, tiers, budget) -- request candidates -> a TIER judges ->
#          accept | request_more(new_params)  (budget--, re-request)
#          | escalate                          (defer UP to the next tier; budget resets)
#          budget exhausted -> FORCED escalate (no thrash). Ladder exhausted -> human.
#
# `tiers` is the ordered list of decide(JudgeContext)->Verdict callables: the Haiku SWARM at the
# bottom, then Sonnet, Opus, human. Deterministic defaults run headless (so the loop is testable
# with NO LLM); the real tiers are sub-agents the orchestrator (Claude) spawns -- the Python loop
# provides the protocol + state + budget, the sub-agent provides the judgement.
#
# `where`: 'local' runs the compute here; 'runner' will dispatch to synth.yml on the self-hosted
# runner (async; the LLM swarm stays in the cloud, the CPU stays on the box) -- TODO.
import os
import re
import sys
import json
import collections
import tempfile
import subprocess
from dataclasses import dataclass, field, asdict, replace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_fr        # noqa: E402
import cec_score     # noqa: E402
import cec_toolchain as _tc   # noqa: E402  -- toolchain presence helpers (R-05)

# Cosmetic DRC filter: ONE definition, in cec_score (R-02 -- the lists were defined twice
# and the parity rule "MUST match cec_route.verify" lived only on the cec_score copy).
_COSMETIC = cec_score.COSMETIC_DRC_TYPES
# ---- FINISHING vs REAL classification of a structural DRC locus -------------------------------
# This classification is retained for diagnostics and constraint-specific reporting. It is never
# an automatic acceptance waiver. A candidate must satisfy its complete independent gates_pass
# contract. Three historically documented classes are:
#   1. a short / mask-bridge between two pads of the SAME footprint -> a known headless FALSE
#      artifact. Verified on the TS-1088 buttons: the two pads sit 3.13mm apart edge-to-edge, so a
#      copper/mask short is geometrically impossible; kicad-cli reports it headless (it flips
#      between SW1/SW2 across runs on identical geometry) but it never appears in the GUI.
#   2. the decorative B.Cu LOGO polygon touching ONLY GND / <no net> (LOGO1 wants a GND-assign or
#      a no-via keepout) -- BUT the LOGO bridging a FUNCTIONAL net (/I2C_SCL, /THRESH, /USB_*,
#      +3V3, ...) is a REAL short, not finishing.
#   3. the RJ-45 shield tabs SH1/SH2 tied to GND.


def _fp_refs(where):
    """Footprint refs named in a DRC locus: 'Pad 1 [GND] of SW1 on F.Cu ...' -> ['SW1']."""
    return re.findall(r"\bof ([A-Za-z]+\d+)\b", where)


def _bracket_nets(where):
    """Bracketed net tokens in a locus: '... [GND] ... [/I2C_SCL] ...' -> ['GND', '/I2C_SCL']."""
    return re.findall(r"\[([^\]]+)\]", where)


def _within_footprint_short(where):
    """A short / mask-bridge whose items are two pads of the SAME footprint = the known headless
    false artifact (class 1 above)."""
    refs = _fp_refs(where)
    return len(refs) >= 2 and len(set(refs)) == 1


def _locus_is_finishing(lc):
    """Classify one DRC locus for diagnostics, never for automatic acceptance."""
    w = lc["where"]
    wu = w.upper()
    if lc["type"] in ("shorting_items", "solder_mask_bridge") and _within_footprint_short(w):
        return True                                   # class 1: same-footprint pad short (false)
    if "LOGO" in wu:                                  # class 2: decorative logo copper
        real = [n for n in _bracket_nets(w) if n not in ("<no net>", "no net", "GND", "")]
        return len(real) == 0                         # logo vs GND/no-net = finishing; vs a real net = REAL
    if "SH1" in wu or "SH2" in wu or "SHIELD" in wu:  # class 3: RJ-45 shield-tab tie
        return True
    return False


# ============================================================ TOOLS
# (R-02) the old _drc_types here ran a SECOND full DRC on every board cec_score had just
# DRC'd. Removed: Metrics.drc_types / Metrics.drc_loci now ride the score() run, and the
# standalone path-only form lives in cec_score.drc_types (used by cec_constraints).
_drc_types = cec_score.drc_types   # deprecated alias; do not add callers


@dataclass
class CandidateMetrics:
    seed: object
    params: dict
    board: str
    drc: int
    unconnected: int
    kelvin_ok: bool
    diffpair_ok: bool
    gates_pass: bool
    tracks: int
    vias: int
    drc_types: dict
    drc_loci: list
    unconn_nets: list   # net names carrying unrouted ratlines -- so a judge can tell a
                        # finishing tie (SH1/SH2 shield tabs) from a real functional-net failure


# ---- the LOCAL runner: a bounded compute pool on THIS system (NOT a GitHub Actions runner) --------
# A cross-process slot semaphore (flock on N files under build/.runner_slots) bounds the TOTAL number
# of concurrent Freerouting jobs across every caller -- so a TEAM of agents (each driving its own
# swarm + routes) can't oversubscribe the CPU and lock the box (the 3-parallel-routes / 48-seed
# lockup failure mode). Slots default to ~cores/4 (each FR job already spawns a seed-pool of JVMs);
# tune with CEC_RUNNER_SLOTS. A holder that dies releases its flock automatically (OS-backed).
import contextlib

def runner_slots():
    return int(os.environ.get("CEC_RUNNER_SLOTS", max(1, (os.cpu_count() or 4) // 4)))


@contextlib.contextmanager
def runner_slot(*, poll=0.5, label=""):
    """Acquire one of CEC_RUNNER_SLOTS global compute slots (blocking) for a local FR job; release on
    exit. No-op-safe on a platform without fcntl (degrades to unbounded)."""
    try:
        import fcntl
    except Exception:
        yield -1
        return
    n = runner_slots()
    d = os.path.join(ROOT, "build", ".runner_slots")
    os.makedirs(d, exist_ok=True)
    fd = held = None
    try:
        while held is None:
            for i in range(n):
                f = os.open(os.path.join(d, f"slot{i}.lock"), os.O_CREAT | os.O_RDWR)
                try:
                    fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    fd, held = f, i
                    break
                except OSError:
                    os.close(f)
            if held is None:
                time.sleep(poll)
        yield held
    finally:
        if fd is not None:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)


def _spread_params(params, seeds):
    """R-01: Freerouting 1.7.0 is deterministic, so a constant params dict across multiple
    seeds produces byte-identical candidates -- the judging tier would be handed duplicate
    boards. Expand a single requested dict to a per-seed opt_time spread (0.5x .. 1.5x the
    requested value, linear across seeds) and return {seed: resolved_params}. The RESOLVED
    per-seed params are what gets recorded in CandidateMetrics.params, so the judge can see
    the spread. A single seed keeps the dict untouched."""
    seeds = list(seeds)
    if len(seeds) <= 1:
        return {s: dict(params) for s in seeds}
    base = dict(params)
    ot = int(base.get("opt_time", 20))
    out = {}
    for i, s in enumerate(seeds):
        f = 0.5 + 1.0 * i / (len(seeds) - 1)
        out[s] = {**base, "opt_time": max(5, int(round(ot * f)))}
    return out


def _generate_scored(board, params, seeds, max_workers, out_dir):
    out_dir = out_dir or tempfile.mkdtemp(prefix="cec_disp_", dir=tempfile.gettempdir())
    resolved = _spread_params(params, seeds)                      # R-01: per-seed spread
    cands = cec_fr.generate_batch(board, seeds=tuple(seeds),
                                  params=(lambda s: dict(resolved[s])),
                                  out_dir=out_dir, max_workers=max_workers)
    res = []
    seen = {}                                                     # sha256 -> CandidateMetrics
    for c in cands:
        if not (c.ok and c.board):
            continue
        # R-01 adjunct: content-hash dedupe BEFORE scoring (scoring is the expensive step).
        # A duplicate reuses the first occurrence's metrics and is tagged in its params so
        # the judge sees it is not independent evidence.
        h = _tc.sha256_file(c.board)
        if h in seen:
            first = seen[h]
            res.append(replace(first, seed=c.seed, board=c.board,
                               params={**resolved[c.seed], "_dup_of_seed": first.seed}))
            continue
        m = cec_score.score(c.board)                              # R-02: ONE DRC, via score()
        cm = CandidateMetrics(
            seed=c.seed, params=dict(resolved[c.seed]), board=c.board,
            drc=m.drc, unconnected=m.unconnected, kelvin_ok=m.kelvin_ok,
            diffpair_ok=m.diffpair_ok, gates_pass=m.gates_pass,
            tracks=m.tracks, vias=m.vias, drc_types=m.drc_types, drc_loci=m.drc_loci,
            unconn_nets=m.detail.get("unconn_nets", []))
        seen[h] = cm
        res.append(cm)
    res.sort(key=lambda c: (0 if c.gates_pass else 1, c.drc, c.unconnected))
    return res


def request_candidates(board, *, params, seeds=(0, 1), max_workers=None, out_dir=None,
                       where="local"):
    """TOOL: generate + score N Freerouting candidates and return STRUCTURED METRICS (not raw
    boards) for a tier agent to judge. *params* = {passes, opt_time, threads}. Returns the list of
    CandidateMetrics (ok ones), best-first by (gates_pass, drc, unconnected).

    where='local'  -> run FR in-process (unbounded; the caller owns concurrency).
    where='runner' -> run FR through THIS system's bounded local runner (runner_slot, a cross-process
                      slot semaphore), so a team of agents can't oversubscribe the CPU. NOT a GitHub
                      Actions runner -- the compute runs here, just centrally rate-limited."""
    if where == "runner":
        with runner_slot(label=os.path.basename(str(board))):
            return _generate_scored(board, params, seeds, max_workers, out_dir)
    return _generate_scored(board, params, seeds, max_workers, out_dir)


def score_board(board):
    """TOOL: score one board -> dict."""
    m = cec_score.score(board)                                    # R-02: ONE DRC, via score()
    return {"drc": m.drc, "unconnected": m.unconnected, "kelvin_ok": m.kelvin_ok,
            "diffpair_ok": m.diffpair_ok, "gates_pass": m.gates_pass,
            "tracks": m.tracks, "vias": m.vias, "drc_types": m.drc_types, "drc_loci": m.drc_loci,
            "unconn_nets": m.detail.get("unconn_nets", [])}


def render(board, png):
    if not _tc.have_kicad_cli():                 # DEGRADE: render is optional (R-05)
        _tc.warn_once("disp_render", "kicad-cli absent -- skipping render. " + _tc.KICAD_CLI_HINT)
        return None
    subprocess.run([_tc.kicad_cli(), "pcb", "render", "-o", png, board], capture_output=True)
    return png if os.path.isfile(png) else None


# ============================================================ the protocol
GATE_NOTE = (
    "HARD ACCEPTANCE GATE (must hold to accept): gates_pass. This includes kelvin_ok, "
    "diffpair_ok, and every configured DRC and unconnected-ratline completion gate. "
    "No finishing or known-false residual may be waived by the routing dispatcher. Such findings "
    "must be corrected or explicitly dispositioned outside automatic route acceptance. An owner "
    "disposition does not alter this automatic gate. Among candidates that pass, prefer fewer vias "
    "and shorter length."
)


@dataclass
class Verdict:
    action: str                 # "accept" | "request_more" | "escalate"
    seed: object = None         # accept: which candidate
    params: dict = None         # request_more: the changed FR params
    reason: str = ""
    tier: str = ""


@dataclass
class JudgeContext:
    board: str
    candidates: list            # [asdict(CandidateMetrics), ...]
    budget_left: int
    tier: str
    history: list               # prior {tier, verdict, params} entries
    gate_note: str = GATE_NOTE


# ============================================================ the budgeted loop
def agent_route(board, *, tiers, budget=3, init_params=None, seeds=(0, 1), max_workers=None,
                request_fn=None, where="local", verbose=True):
    """The tiered-judge loop. request candidates -> tier judges -> accept | request_more (budget--,
    re-request with changed params) | escalate (defer UP a tier, reset budget). Budget exhausted ->
    FORCED escalate (no thrash). Returns (accepted CandidateMetrics|None, decision_log).

    *tiers*: ordered decide(JudgeContext)->Verdict callables (Haiku swarm -> Sonnet -> Opus ->
    human). *where*: 'runner' routes the FR compute through the bounded local runner (safe under a
    team of agents). *request_fn*: defaults to request_candidates; inject a stub to unit-test the loop."""
    req = request_fn or (lambda p, s: request_candidates(board, params=p, seeds=s,
                                                          max_workers=max_workers, where=where))
    params = dict(init_params or {"passes": 8, "opt_time": 12, "threads": 1})
    log = []
    ti = 0
    b = budget
    while ti < len(tiers):
        tier_name = getattr(tiers[ti], "tier_name", f"tier{ti}")
        cands = req(params, seeds)
        ctx = JudgeContext(board=board, candidates=[asdict(c) for c in cands], budget_left=b,
                           tier=tier_name, history=list(log), gate_note=GATE_NOTE)
        v = tiers[ti](ctx)
        v.tier = v.tier or tier_name
        _bm = cands[0] if cands else None
        log.append({"tier": tier_name, "budget_left": b, "params": dict(params),
                    "n_cands": len(cands), "verdict": v.action, "reason": v.reason[:200],
                    "best_drc": (_bm.drc if _bm else None),               # the stall trail: a
                    "best_unconnected": (_bm.unconnected if _bm else None),  # structural lens reads
                    "best_gates_pass": (_bm.gates_pass if _bm else None)})   # this to detect no-progress
        if verbose:
            print(f"  [{tier_name}] {len(cands)} cands, budget={b} -> {v.action}: {v.reason[:90]}")
        if v.action == "accept":
            if not cands:
                # R-08: an accept against an EMPTY candidate list is not a success. Coerce to
                # escalate (logged) instead of returning None indistinguishably from failure.
                log[-1]["note"] = "accept-with-no-candidates coerced to escalate"
                ti += 1
                b = budget
                continue
            best = next((c for c in cands if c.seed == v.seed), None)
            if best is None:
                # R-08: a verdict naming an unknown seed falls back to the best candidate,
                # but the fallback is RECORDED -- the tier's stated intent must not be lost.
                log[-1]["note"] = f"seed fallback: verdict seed {v.seed!r} not in candidates; using best"
                best = cands[0]
            if not best.gates_pass:
                # A model or deterministic tier is advisory. It cannot waive the complete scorer
                # contract, which includes the configured DRC and unconnected-ratline gates in
                # addition to Kelvin and differential-pair topology. Escalate rather than return a
                # route that the independent scorer rejected.
                prior_note = log[-1].get("note")
                rejection = "accept rejected because selected candidate gates_pass=false"
                log[-1]["note"] = f"{prior_note}; {rejection}" if prior_note else rejection
                ti += 1
                b = budget
                continue
            return best, log
        if v.action == "request_more" and b > 0:
            params = {**params, **(v.params or {})}
            b -= 1
        else:                                            # escalate, or budget exhausted -> forced up
            if v.action == "request_more":
                # R-08: the coercion is recorded -- the log must show the tier ASKED for more
                # but the budget forced the escalation.
                log[-1]["note"] = "budget-coerced escalate (tier requested more with budget 0)"
            ti += 1
            b = budget
    return None, log


# ---- deterministic default tiers (headless, NO LLM -- so the loop is testable) ----
def _is_finishing_only(types, loci):
    """Diagnostic-only classification; this result never overrides gates_pass."""
    if not types:
        return True
    return all(_locus_is_finishing(lc) for lc in loci)


def det_haiku(ctx):
    """Accept only a candidate that passes the complete independent scorer contract."""
    best = ctx.candidates[0] if ctx.candidates else None
    if best and best["gates_pass"]:
        return Verdict("accept", seed=best["seed"], reason="complete gates_pass contract satisfied")
    if ctx.budget_left > 0:
        opt = ctx.history[-1]["params"]["opt_time"] if ctx.history else 12
        return Verdict("request_more", params={"opt_time": int(opt * 1.6)},
                       reason="gates fail / real DRC; raise optimization and re-request")
    return Verdict("escalate", reason="budget spent without a clean candidate")
det_haiku.tier_name = "haiku"


def det_escalate(ctx):
    """Deterministic Sonnet/Opus stand-in: accept only the complete scorer gate."""
    best = ctx.candidates[0] if ctx.candidates else None
    if best and best["gates_pass"]:
        return Verdict("accept", seed=best["seed"], reason="complete gates_pass contract satisfied")
    return Verdict("escalate", reason="no gate-passing candidate; defer to human")
det_escalate.tier_name = "sonnet"

DEFAULT_TIERS = [det_haiku, det_escalate]


# ============================================================ CLI (the TOOL surface)
def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="cec_dispatch -- compute-as-tools for the agentic loop")
    sub = ap.add_subparsers(dest="cmd", required=True)
    rc = sub.add_parser("request-candidates", help="generate+score FR candidates -> metrics JSON")
    rc.add_argument("--board", default="eps-8pin")
    rc.add_argument("--seeds", default="0,1")
    rc.add_argument("--passes", type=int, default=8)
    rc.add_argument("--opt-time", type=int, default=12)
    rc.add_argument("--threads", type=int, default=1)
    rc.add_argument("--max-workers", type=int, default=0)
    rc.add_argument("--out", default=None)
    rc.add_argument("--where", choices=("local", "runner"), default="local",
                    help="'runner' = the bounded local compute pool (team-safe)")

    ar = sub.add_parser("agent-route", help="run the budgeted agent_route ladder (optionally with the "
                                            "LOCAL swarm Haiku tier)")
    ar.add_argument("--board", default="eps-8pin")
    ar.add_argument("--seeds", default="0,1")
    ar.add_argument("--budget", type=int, default=2)
    ar.add_argument("--panel", type=int, default=3)
    ar.add_argument("--swarm", action="store_true",
                    help="tier-0 = the local-LLM swarm (else the deterministic det_haiku)")
    ar.add_argument("--where", choices=("local", "runner"), default="local",
                    help="'runner' routes FR compute through the bounded local runner (team-safe)")
    a = ap.parse_args(argv)

    def _find_board(name):
        # R-08: cec_router.find_board is the ONE board-lookup (same skip rules, and a
        # friendly error instead of a bare IndexError when a module dir has no floorplan).
        import cec_router
        try:
            return cec_router.find_board(name)
        except FileNotFoundError as e:
            print(f"cec_dispatch: {e}", file=sys.stderr)
            sys.exit(2)

    if a.cmd == "request-candidates":
        bp = _find_board(a.board)
        # the compute (Freerouting / pcbnew) logs to stdout; send that to stderr so stdout is
        # CLEAN JSON the calling agent can parse.
        import contextlib
        with contextlib.redirect_stdout(sys.stderr):
            res = request_candidates(bp, params={"passes": a.passes, "opt_time": a.opt_time,
                                                 "threads": a.threads},
                                     seeds=tuple(int(s) for s in a.seeds.split(",")),
                                     max_workers=(a.max_workers or None), out_dir=a.out, where=a.where)
        # emit the metrics a tier agent judges (drop the board path's noise to a basename).
        # The MARKERS let the orchestrator pull the JSON cleanly out of a GitHub Actions job log
        # (where stdout+stderr interleave) when this runs via synth.yml on the self-hosted runner.
        payload = [{**asdict(c), "board": os.path.basename(c.board)} for c in res]
        blob = json.dumps(payload, indent=2)
        print("===CEC_CANDIDATES_JSON_BEGIN===")
        print(blob)
        print("===CEC_CANDIDATES_JSON_END===")
        if a.out:                                        # also persist for an artifact upload
            os.makedirs(a.out, exist_ok=True)
            with open(os.path.join(a.out, "candidates.json"), "w") as fh:
                fh.write(blob)

    elif a.cmd == "agent-route":
        import contextlib
        bp = _find_board(a.board)               # R-08: one lookup, friendly error
        tiers = list(DEFAULT_TIERS)
        if a.swarm:
            import cec_judge_local
            if cec_judge_local.available():
                tiers = [cec_judge_local.make_dispatch_swarm_tier(panel=a.panel, verbose=True), det_escalate]
                print(f"[dispatch] tier-0 = LOCAL SWARM (panel={a.panel}, {cec_judge_local.MODEL})",
                      file=sys.stderr)
            else:
                print("[dispatch] --swarm requested but vLLM down -> deterministic tiers", file=sys.stderr)
        # the FR/pcbnew compute + the loop's progress print to stderr so stdout stays clean JSON
        with contextlib.redirect_stdout(sys.stderr):
            best, log = agent_route(bp, tiers=tiers, budget=a.budget, where=a.where,
                                    seeds=tuple(int(s) for s in a.seeds.split(",")))
        print(json.dumps({"accepted": (asdict(best) if best else None), "log": log},
                         indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
