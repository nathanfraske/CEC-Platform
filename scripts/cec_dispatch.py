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
# DRC types that are FINISHING/placement, not a routing fault -- the judge treats these as
# acceptable-with-a-note (they belong to the floorplan/placement pass): the decorative B.Cu logo
# and the RJ-45 shield-tab-to-GND tie (documented platform-wide).
_FINISHING = ("solder_mask_bridge", "shorting_items")   # only when they involve LOGO/shield (see note)


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
    for v in viol[:20]:
        desc = " ".join(it.get("description", "") for it in v.get("items", []))
        loci.append({"type": v["type"], "where": re.sub(r"\s+", " ", desc)[:80]})
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


def request_candidates(board, *, params, seeds=(0, 1), max_workers=None, out_dir=None,
                       where="local"):
    """TOOL: generate + score N Freerouting candidates and return STRUCTURED METRICS (not raw
    boards) for a tier agent to judge. *params* = {passes, opt_time, threads}. Returns the list of
    CandidateMetrics (ok ones), best-first by (gates_pass, drc, unconnected)."""
    if where == "runner":
        raise NotImplementedError("runner dispatch (synth.yml) is the next step; use where='local'")
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
            tracks=m.tracks, vias=m.vias, drc_types=types, drc_loci=loci))
    res.sort(key=lambda c: (0 if c.gates_pass else 1, c.drc, c.unconnected))
    return res


def score_board(board):
    """TOOL: score one board -> dict."""
    m = cec_score.score(board)
    types, loci = _drc_types(board)
    return {"drc": m.drc, "unconnected": m.unconnected, "kelvin_ok": m.kelvin_ok,
            "diffpair_ok": m.diffpair_ok, "gates_pass": m.gates_pass,
            "tracks": m.tracks, "vias": m.vias, "drc_types": types, "drc_loci": loci}


def render(board, png):
    subprocess.run(["kicad-cli", "pcb", "render", "-o", png, board], capture_output=True)
    return png if os.path.isfile(png) else None


# ============================================================ the protocol
GATE_NOTE = (
    "HARD SAFETY GATES (must hold to accept): kelvin_ok AND diffpair_ok. "
    "drc==0 is ideal, BUT a small DRC dominated by the decorative B.Cu LOGO and the RJ-45 "
    "shield-tab-to-GND tie is FINISHING (owned by the placement pass), not a routing fault -- "
    "acceptable with a note. A clearance/short between two REAL signal nets, or unrouted ratlines "
    "on a functional net, is NOT acceptable. Prefer fewer vias / shorter length among equals."
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
                request_fn=None, verbose=True):
    """The tiered-judge loop. request candidates -> tier judges -> accept | request_more (budget--,
    re-request with changed params) | escalate (defer UP a tier, reset budget). Budget exhausted ->
    FORCED escalate (no thrash). Returns (accepted CandidateMetrics|None, decision_log).

    *tiers*: ordered decide(JudgeContext)->Verdict callables (Haiku swarm -> Sonnet -> Opus ->
    human). *request_fn*: defaults to request_candidates; inject a stub to unit-test the loop."""
    req = request_fn or (lambda p, s: request_candidates(board, params=p, seeds=s,
                                                          max_workers=max_workers))
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
        log.append({"tier": tier_name, "budget_left": b, "params": dict(params),
                    "n_cands": len(cands), "verdict": v.action, "reason": v.reason[:200]})
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
    """True if the structural DRC is dominated by LOGO/shield-tab finishing (cosmetic-acceptable)."""
    if not types:
        return True
    real = 0
    for lc in loci:
        w = lc["where"].upper()
        if "LOGO" not in w and "SH1" not in w and "SH2" not in w and "SHIELD" not in w:
            real += 1
    return real == 0


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
                                     max_workers=(a.max_workers or None), out_dir=a.out)
        # emit the metrics a tier agent judges (drop the board path's noise to a basename)
        payload = [{**asdict(c), "board": os.path.basename(c.board)} for c in res]
        print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
