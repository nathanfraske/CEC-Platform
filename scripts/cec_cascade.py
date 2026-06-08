#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_cascade -- the cascading SWARM pipeline: PLACE-swarm -> ROUTE-swarm -> FEM -> APEX.
# ============================================================================
# Chains the local-agent swarms at every tier, escalating UP to the human/Opus APEX on success
# (the user's design: "placement candidates made via swarm -> triggers a routing swarm -> triggers
# FEM -> if that passes it goes back up to you"):
#
#   PLACE : placement_metrics(floorplan) -> the PLACEMENT swarm (accept / refine / escalate).
#           accept -> route it; refine -> a placement-refinement pass then route; escalate -> a
#           DIFFERENT placement candidate (lever 1) or stop for the human (lever 2).
#   ROUTE : cec_router.route() driven by the MANAGER PANEL + WORKER SWARM (the routing swarm).
#   FEM   : electrothermal physics_gates on the routed board (J / dT / T / via / shunt).
#   APEX  : if FEM passes -> escalate to the APEX (human/Opus sign-off) -- back up to you.
#
# Every tier is FAIL-SAFE to its deterministic policy; with --no-swarm the whole cascade runs
# deterministically (no GPU). Gated: for --swarm the local vLLM judge must be up (cec_judge_local up).
# Run in the routing container (needs pcbnew + kicad-cli).
#   python3 scripts/cec_cascade.py --board eps-8pin [--panel 3] [--no-swarm] [--max-iters 2]
# ============================================================================
import os
import sys
import json
import tempfile
import subprocess
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_router
import cec_constraints
import cec_synth_pipeline as synth


# ----------------------------------------------------------------- PLACE tier
# Route-time / FEM gates are NOT placement constraints -- they fail on an unrouted floorplan by
# definition (the diff pair / sense / pours aren't laid yet) and are owned by the ROUTE and FEM tiers
# below. The PLACE tier must judge only PLACEMENT-meaningful constraints, so these are excluded here.
ROUTE_TIME_IDS = {"usb-diffpair-routed-coupled", "board-routing-complete", "min-pour-cross-section",
                  "high-current-pour-present", "high-current-pour-integrity", "kelvin-sense-fcu-no-via",
                  "kelvin-sense-from-inner-pad"}


def placement_metrics(board_path):
    """Summarize a placement for the placement swarm: the constraint registry's PLACEMENT hard/strong
    FAILs (route-time/FEM gates excluded) + directive types, plus courtyard overlaps from DRC."""
    blob = cec_constraints.report(board_path, {"radio": False}, as_json=True)
    vs = [v for v in blob["verdicts"] if v["id"] not in ROUTE_TIME_IDS]
    hard = sorted(v["id"] for v in vs if v["status"] == "FAIL" and v["severity"] == "hard")
    strong = sorted(v["id"] for v in vs if v["status"] == "FAIL" and v["severity"] == "strong")
    out = os.path.join(tempfile.gettempdir(), "cascade_drc_%d.json" % os.getpid())
    subprocess.run(["kicad-cli", "pcb", "drc", "--format", "json", "-o", out, board_path],
                   capture_output=True)
    try:
        viols = json.load(open(out)).get("violations", [])
    except Exception:
        viols = []
    courtyard = sum(1 for v in viols if v.get("type") == "courtyards_overlap")
    return {"board": os.path.basename(board_path), "hard_fails": hard, "strong_fails": strong,
            "courtyard_overlaps": courtyard,
            "directive_types": dict(Counter(d.get("directive") for d in blob.get("directives", []))),
            "n_fail": sum(1 for v in vs if v["status"] == "FAIL")}


def place_tier(board, floorplan, *, place_decide, verbose=True):
    """Judge the floorplan placement with the placement swarm; on `refine` run one cec_place refinement
    pass and re-judge. Returns (placement_path, verdict_dict)."""
    metrics = placement_metrics(floorplan)
    v = place_decide(metrics)
    if verbose:
        print(f"[cascade:PLACE] {metrics['board']} hard={metrics['hard_fails']} "
              f"courtyard={metrics['courtyard_overlaps']} -> {v['action']} {v.get('tally', {})}")
    placement = floorplan
    if v["action"] == "refine":
        try:
            import cec_place
            refined = os.path.join(ROOT, "build", "cascade", f"{board}-placed.kicad_pcb")
            os.makedirs(os.path.dirname(refined), exist_ok=True)
            cec_place.refine(floorplan, refined, {"radio": False})
            placement = refined
            v = {**v, "refined": True, "metrics_after": placement_metrics(refined)}
            if verbose:
                print(f"[cascade:PLACE] refined -> hard={v['metrics_after']['hard_fails']}")
        except Exception as e:
            v = {**v, "refine_error": repr(e)}
    return placement, v


# ----------------------------------------------------------------- ROUTE tier
def route_tier(board, placement, *, panel, swarm, max_iters, kmax, seeds, passes, opt_time, verbose=True):
    """Route the placement with the routing MANAGER PANEL + WORKER SWARM (or deterministic). Returns
    (routed_board_path, DecisionLog, verdict_dict)."""
    out_dir = os.path.join(ROOT, "build", "cascade", board)
    os.makedirs(out_dir, exist_ok=True)
    spec, _ = cec_router.board_spec(board, out_dir, seeds=tuple(seeds), passes=passes,
                                    opt_time=opt_time, max_iters=max_iters, kmax=kmax)
    manager = worker = None
    if swarm:
        import cec_judge_local
        if cec_judge_local.available():
            manager = cec_judge_local.make_manager_swarm(spec, panel=panel, verbose=verbose)
            worker = cec_judge_local.make_worker_swarm(spec, fanout=panel, verbose=verbose)
        elif verbose:
            print("[cascade:ROUTE] vLLM down -> deterministic routing tiers")
    final, log = cec_router.route(placement, spec, manager=manager, worker=worker, verbose=verbose)
    verdict = (log.final or {}).get("verdict", {})
    return final, log, verdict


# ----------------------------------------------------------------- FEM tier
# the cable design current is a TRANSIENT peak, not sustained (the user's design call): a lower
# sustained 'longer peak' baseline + a brief spike to the peak. The FEM heats on the RMS-over-tau
# current and models the peak excursion separately. Tune per board via cfg.params['transient'].
DEFAULT_TRANSIENT = {"sustained_ratio": 0.5, "peak_duty": 0.05, "peak_ms": 5.0, "tau_s": 10.0}
# SUSTAINED over-temp is the real blocking thermal fault; sustained-J / transient-fusing are advisory
# (need an I^2t analysis to confirm), matching the min-pour-cross-section advisory stance.
FEM_ADVISORY = ("current density high", "transient fusing risk", "transient via fusing")


def fem_tier(board, routed, *, transient=None, verbose=True):
    """Transient-aware electrothermal FEM gate on the routed board. SUSTAINED over-temp (RMS current)
    BLOCKS; a brief transient excursion / peak-J fusing is advisory. Returns
    {pass, blocking, advisory, flags, max_T, transient}."""
    try:
        cfg = synth.Config.load(board)
    except Exception:
        cfg = synth.Config(board=board)
    cfg.params.setdefault("transient", dict(transient or DEFAULT_TRANSIENT))
    try:
        res = synth.electrothermal_solve(routed, cfg)
        flags = synth.physics_gates(res, cfg)
    except Exception as e:
        return {"pass": False, "blocking": ["solver_error"], "advisory": [], "flags": [], "error": repr(e)}
    blocking = sorted({f.name for f in flags if f.name not in FEM_ADVISORY})
    advisory = sorted({f.name for f in flags if f.name in FEM_ADVISORY})
    detail = [{"name": f.name, "where": str(f.where)[:60], "conf": f.conf} for f in flags]
    if verbose:
        print(f"[cascade:FEM] {len(flags)} flag(s); blocking={blocking} advisory={advisory} "
              f"(max_T={res.max_T}C, transient on)")
    return {"pass": not blocking, "blocking": blocking, "advisory": advisory, "flags": detail,
            "max_T": res.max_T, "transient": cfg.params["transient"]}


# ----------------------------------------------------------------- APEX
_THERMAL = ("conductor over-temp", "via over-temp", "shunt over-temp", "solver_error")


def default_apex(summary):
    """Deterministic apex stand-in for the HUMAN/OPUS at the top of the cascade -- it CLASSIFIES the
    escalation that comes 'back up to you' and signs only when clean. Three outcomes:
      release-ready          : FEM passed + route gates clean + placement clean -> sign the release.
      design-change (lever 2): a FEM over-temp/structural flag re-routing can't fix -> a human
                               stackup/copper-coin design decision (CLAUDE.md ratification boundary).
      cascade-down           : route/finishing residual -> re-route or a finishing pass, not the human."""
    fem = summary["fem"]
    route_clean = not summary["route"].get("reasons")
    place_clean = not summary["place"].get("hard_fails")
    if fem["pass"] and route_clean and place_clean:
        return {"signed": True, "by": "default-cautious-apex", "escalation": "release-ready",
                "reason": "FEM passed + route gates clean + placement clean -> READY for release sign-off (up to you)"}
    if not fem["pass"] and any(b in _THERMAL for b in fem.get("blocking", [])):
        return {"signed": False, "by": "default-cautious-apex", "escalation": "design-change (lever 2)",
                "reason": f"FEM {fem.get('blocking')} -- NOT fixable by re-route; needs a human "
                          f"stackup/copper design decision (the §6.7/OQ-10 boundary -- up to you)"}
    return {"signed": False, "by": "default-cautious-apex", "escalation": "cascade-down",
            "reason": "route/finishing residual -> re-route or a finishing pass (cascade back down)"}


# ----------------------------------------------------------------- the cascade
def cascade(board, *, panel=3, swarm=True, max_iters=2, kmax=2, seeds=(0, 1), passes=8, opt_time=10,
            place_decide=None, apex=None, verbose=True):
    """Run PLACE-swarm -> ROUTE-swarm -> FEM -> APEX and return the full structured result."""
    apex = apex or default_apex
    if place_decide is None:
        if swarm:
            import cec_judge_local
            place_decide = (cec_judge_local.make_placement_swarm(panel=panel, verbose=verbose)
                            if cec_judge_local.available()
                            else (lambda m: {"action": "escalate" if m["hard_fails"] else "accept",
                                             "reason": "deterministic", "tally": {}}))
        else:
            place_decide = (lambda m: {"action": "escalate" if m["hard_fails"] else "accept",
                                       "reason": "deterministic", "tally": {}})

    floorplan = cec_router.find_board(board)
    if verbose:
        print(f"=== CASCADE :: {board} (swarm={swarm}, panel={panel}) ===")

    # PLACE
    placement, pv = place_tier(board, floorplan, place_decide=place_decide, verbose=verbose)
    pm = pv.get("metrics_after") or placement_metrics(floorplan)
    if pv["action"] == "escalate":
        summary = {"board": board, "place": {**pm, "verdict": pv}, "route": {}, "fem": {"pass": False},
                   "stopped_at": "PLACE", "reason": "placement swarm escalated -> regenerate candidate / human"}
        summary["apex"] = {"signed": False, "by": "n/a", "reason": "did not reach FEM"}
        return summary

    # ROUTE
    routed, log, rv = route_tier(board, placement, panel=panel, swarm=swarm, max_iters=max_iters,
                                 kmax=kmax, seeds=seeds, passes=passes, opt_time=opt_time, verbose=verbose)
    route_info = {"final": routed, "verdict": rv, "reasons": rv.get("reasons", []),
                  "tiers": sorted({(e.get("verdict") or {}).get("tier", "") for e in log.entries if e.get("verdict")})}

    # FEM
    fem = fem_tier(board, routed, verbose=verbose) if routed else {"pass": False, "blocking": ["no routed board"], "flags": []}

    # APEX -- back up to you
    summary = {"board": board, "place": {**pm, "verdict": pv},
               "route": route_info, "fem": fem, "stopped_at": "APEX"}
    summary["apex"] = apex(summary)
    if verbose:
        a = summary["apex"]
        print(f"[cascade:APEX] -> {'SIGNED' if a['signed'] else 'WITHHELD'} ({a['by']}): {a['reason']}")
    return summary


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="cec_cascade -- PLACE-swarm -> ROUTE-swarm -> FEM -> APEX")
    ap.add_argument("--board", default="eps-8pin")
    ap.add_argument("--panel", type=int, default=3)
    ap.add_argument("--no-swarm", action="store_true", help="run every tier deterministically (no GPU)")
    ap.add_argument("--max-iters", type=int, default=2)
    ap.add_argument("--kmax", type=int, default=2)
    ap.add_argument("--seeds", default="0,1")
    ap.add_argument("--passes", type=int, default=8)
    ap.add_argument("--opt-time", type=int, default=10)
    ap.add_argument("--json", action="store_true", help="emit the full summary as JSON")
    a = ap.parse_args(argv)
    res = cascade(a.board, panel=a.panel, swarm=not a.no_swarm, max_iters=a.max_iters, kmax=a.kmax,
                  seeds=tuple(int(s) for s in a.seeds.split(",")), passes=a.passes, opt_time=a.opt_time,
                  verbose=not a.json)
    if a.json:
        print(json.dumps(res, indent=2, default=str))
    else:
        print("\n=== CASCADE SUMMARY ===")
        print(f"  board:      {res['board']}")
        print(f"  PLACE:      {res['place']['verdict']['action']} (hard_fails={res['place'].get('hard_fails')})")
        if res.get("route"):
            print(f"  ROUTE:      gates_pass={res['route'].get('verdict',{}).get('gates_pass')} "
                  f"tiers={res['route'].get('tiers')}")
        print(f"  FEM:        pass={res['fem']['pass']} blocking={res['fem'].get('blocking')}")
        print(f"  APEX:       {'SIGNED' if res['apex']['signed'] else 'WITHHELD'} -- {res['apex']['reason']}")
    return 0 if res.get("apex", {}).get("signed") else 1


if __name__ == "__main__":
    sys.exit(main())
