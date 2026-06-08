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
from dataclasses import dataclass, field, asdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_fr        # noqa: E402
import cec_score     # noqa: E402

_COSMETIC = ("silk_overlap", "silk_over_copper", "silk_edge_clearance",
             "lib_footprint_mismatch", "lib_footprint_issues")
# ---- FINISHING vs REAL classification of a structural DRC locus -------------------------------
# Some non-cosmetic DRC hits are FINISHING items owned by the placement pass (not routing faults),
# OR known headless kicad-cli FALSE artifacts (present headless, absent in the GUI). The loop and
# the judges treat these as acceptable-with-a-note. Three documented classes (CLAUDE.md + verified
# on these boards 2026-06-07):
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
    """Classify ONE structural DRC locus: True = finishing or known-false (acceptable-with-a-note),
    False = a real routing/placement fault."""
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
def _drc_types(board):
    """Structural DRC violation-type counts (cosmetic filtered) -- so a tier agent can tell a real
    short from the logo/shield-tab finishing residual."""
    out = os.path.join(tempfile.gettempdir(), f"cec_disp_drc_{os.getpid()}.json")
    subprocess.run(["kicad-cli", "pcb", "drc", "--exit-code-violations", "--format", "json",
                    "-o", out, board], capture_output=True)
    try:
        d = json.load(open(out))
    except Exception:
        return {}, []
    viol = [v for v in d.get("violations", []) if v.get("type") not in _COSMETIC]
    types = dict(collections.Counter(v["type"] for v in viol))
    # tag whether the non-zero DRC is dominated by the known finishing items (logo / shield tabs)
    loci = []
    for v in viol[:80]:
        desc = " ".join(it.get("description", "") for it in v.get("items", []))
        # keep enough of the description that BOTH 'of <REF>' tokens and BOTH bracketed nets survive
        # (the finishing classifier reads them) -- 80 chars truncated the 2nd 'of SWx'/the 2nd net.
        loci.append({"type": v["type"], "where": re.sub(r"\s+", " ", desc)[:160]})
    return types, loci


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


def _generate_scored(board, params, seeds, max_workers, out_dir):
    out_dir = out_dir or tempfile.mkdtemp(prefix="cec_disp_", dir=tempfile.gettempdir())
    cands = cec_fr.generate_batch(board, seeds=tuple(seeds), params=(lambda s: dict(params)),
                                  out_dir=out_dir, max_workers=max_workers)
    res = []
    for c in cands:
        if not (c.ok and c.board):
            continue
        m = cec_score.score(c.board)
        types, loci = _drc_types(c.board)
        res.append(CandidateMetrics(
            seed=c.seed, params=dict(params), board=c.board,
            drc=m.drc, unconnected=m.unconnected, kelvin_ok=m.kelvin_ok,
            diffpair_ok=m.diffpair_ok, gates_pass=m.gates_pass,
            tracks=m.tracks, vias=m.vias, drc_types=types, drc_loci=loci,
            unconn_nets=m.detail.get("unconn_nets", [])))
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
    m = cec_score.score(board)
    types, loci = _drc_types(board)
    return {"drc": m.drc, "unconnected": m.unconnected, "kelvin_ok": m.kelvin_ok,
            "diffpair_ok": m.diffpair_ok, "gates_pass": m.gates_pass,
            "tracks": m.tracks, "vias": m.vias, "drc_types": types, "drc_loci": loci,
            "unconn_nets": m.detail.get("unconn_nets", [])}


def render(board, png):
    subprocess.run(["kicad-cli", "pcb", "render", "-o", png, board], capture_output=True)
    return png if os.path.isfile(png) else None


# ============================================================ the protocol
GATE_NOTE = (
    "HARD SAFETY GATES (must hold to accept): kelvin_ok AND diffpair_ok. "
    "drc==0 is ideal. FINISHING / known-false residual is acceptable-with-a-note (owned by the "
    "placement pass, not routing): (a) the decorative B.Cu LOGO polygon touching ONLY GND / <no "
    "net>; (b) the RJ-45 shield tabs SH1/SH2 tied to GND; (c) a short / mask-bridge between two "
    "pads of the SAME footprint (e.g. 'Pad 1 ... of SW1' AND 'Pad 2 ... of SW1') -- a KNOWN "
    "headless kicad-cli false artifact, geometrically impossible (the pads are mm apart), absent "
    "in the GUI. NOT acceptable (REAL faults): the LOGO polygon bridging a FUNCTIONAL net "
    "(/I2C_SCL, /THRESH, /USB_*, +3V3, ...); a clearance/short between two DIFFERENT real "
    "nets/footprints; or unrouted ratlines on a functional net. Prefer fewer vias / shorter length."
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
            best = next((c for c in cands if c.seed == v.seed), cands[0] if cands else None)
            return best, log
        if v.action == "request_more" and b > 0:
            params = {**params, **(v.params or {})}
            b -= 1
        else:                                            # escalate, or budget exhausted -> forced up
            ti += 1
            b = budget
    return None, log


# ---- deterministic default tiers (headless, NO LLM -- so the loop is testable) ----
def _is_finishing_only(types, loci):
    """True if EVERY structural DRC locus is finishing or a known headless false artifact -- i.e.
    nothing is a real routing/placement short. Per-locus via _locus_is_finishing(), so a LOGO
    polygon bridging a FUNCTIONAL net correctly reads REAL while a same-footprint pad short reads
    false-acceptable."""
    if not types:
        return True
    return all(_locus_is_finishing(lc) for lc in loci)


def det_haiku(ctx):
    """Deterministic stand-in for the Haiku tier: accept if a candidate passes the hard gates and
    its DRC is finishing-only; else request_more ONCE with more optimization; else escalate."""
    best = ctx.candidates[0] if ctx.candidates else None
    if best and best["kelvin_ok"] and best["diffpair_ok"] and \
       (best["drc"] == 0 or _is_finishing_only(best["drc_types"], best["drc_loci"])):
        return Verdict("accept", seed=best["seed"], reason="gates pass; DRC clean or finishing-only")
    if ctx.budget_left > 0:
        opt = ctx.history[-1]["params"]["opt_time"] if ctx.history else 12
        return Verdict("request_more", params={"opt_time": int(opt * 1.6)},
                       reason="gates fail / real DRC; raise optimization and re-request")
    return Verdict("escalate", reason="budget spent without a clean candidate")
det_haiku.tier_name = "haiku"


def det_escalate(ctx):
    """Deterministic Sonnet/Opus stand-in: best-effort accept-if-gates, else give up to human."""
    best = ctx.candidates[0] if ctx.candidates else None
    if best and best["kelvin_ok"] and best["diffpair_ok"]:
        return Verdict("accept", seed=best["seed"], reason="gates pass; accepting best-so-far")
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

    if a.cmd == "request-candidates":
        import glob
        bp = a.board if a.board.endswith(".kicad_pcb") else None
        if not bp:
            cands = [p for p in glob.glob(f"{ROOT}/modules/{a.board}/*.kicad_pcb")
                     if "-routed" not in p and ".merged." not in p]
            bp = sorted(cands)[0]
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
        import glob
        import contextlib
        bp = a.board if a.board.endswith(".kicad_pcb") else None
        if not bp:
            cands = [p for p in glob.glob(f"{ROOT}/modules/{a.board}/*.kicad_pcb")
                     if "-routed" not in p and ".merged." not in p]
            bp = sorted(cands)[0]
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
