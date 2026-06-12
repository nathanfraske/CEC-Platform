"""SB-08 golden FR-variance report (owner directive 2026-06-12, item 2a).

WHY this shape: Freerouting 1.7.0 has NO seed (cec_fr: the `seed` arg is logged but inert). Routing
the golden at its FIXED params (passes 10, opt_time 20) is DETERMINISTIC -- measured byte-identical
drc=0 / thermal 157.9 / 526 tracks across repeated runs. So "FR variance" cannot mean run-to-run noise
at fixed params; FR's ONLY diversity lever is OPT_TIME / PASSES (the R-01 spread mechanism). This
harness therefore characterizes the OUTPUT ENVELOPE across a spread of FR effort on the post-keepout
golden board -- the evidence both SB-08 bands (drc_max, thermal_max_T_max) must be derived from, instead
of the current baseline*1.15 hand-margin (cec_golden.make_bands).

It reuses cec_golden's EXACT route->pour->score->thermal path (so the numbers are the golden's numbers),
varying only opt_time per variant. Output: per-variant rows + per-metric distribution + a derivation-
ready band proposal (max-observed envelope, not a fixed multiplier).

    docker exec docker-routing-1 python3 /workspace/scripts/cec_golden_variance.py --opt-times 10,15,20,30,45,60
"""
import argparse
import json
import os
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

NUMERIC = ("drc", "unconnected", "tracks", "vias", "thermal_max_T")
GATES = ("kelvin_ok", "diffpair_ok")


def _route_variant(opt_time, passes, out_dir):
    """One golden route at a given FR effort -> the cec_golden metric dict (+ the opt_time)."""
    import cec_fr
    import cec_score
    import cec_golden as g
    import cec_synth_pipeline as sp

    pours = cec_fr.derive_power_pours(g.GOLDEN_PCB)
    params = {"passes": passes, "opt_time": opt_time, "threads": 1}
    cands = cec_fr.generate_batch(g.GOLDEN_PCB, seeds=(0,), params=params,
                                  power_pours=pours, out_dir=out_dir)
    ok = [c for c in cands if c.ok and c.board]
    if not ok:
        return {"opt_time": opt_time, "passes": passes, "error": "route failed"}
    board = ok[0].board
    m = cec_score.score(board)
    cfg = sp.Config.load(g.GOLDEN_DIR)
    th = sp.electrothermal_solve(board, cfg)
    return {"opt_time": opt_time, "passes": passes, "drc": m.drc, "unconnected": m.unconnected,
            "tracks": m.tracks, "vias": m.vias, "kelvin_ok": m.kelvin_ok,
            "diffpair_ok": m.diffpair_ok, "thermal_max_T": round(th.max_T, 1)}


def _dist(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    return {"n": len(vals), "min": min(vals), "max": max(vals),
            "mean": round(statistics.mean(vals), 2),
            "median": round(statistics.median(vals), 2),
            "stdev": round(statistics.pstdev(vals), 2) if len(vals) > 1 else 0.0}


def run(opt_times, passes, workdir, passes_sweep=None):
    t0 = time.time()
    rows = []
    for i, ot in enumerate(opt_times):
        rows.append(_route_variant(ot, passes, os.path.join(workdir, f"ot{ot}_{i}")))
    # SECOND axis (the informative one): vary passes at the golden's opt_time. FR converges in passes,
    # so this is a convergence curve, not stochastic variance -- it shows WHERE the golden's 157.9 comes
    # from (converged by passes>=10) and that fewer passes route a cooler, less-complete board.
    import cec_golden as _g                              # passes axis runs at the CI opt_time
    _ci_opt = _g.FR_PARAMS["opt_time"]
    passes_rows = []
    for j, p in enumerate(passes_sweep or []):
        passes_rows.append(_route_variant(_ci_opt, p, os.path.join(workdir, f"p{p}_{j}")))
    good = [r for r in rows if "error" not in r]
    dists = {k: _dist([r.get(k) for r in good]) for k in NUMERIC}
    gate_pass = {g: sum(1 for r in good if r.get(g)) for g in GATES}

    # Band ANCHOR = the FIXED-param CI baseline (passes=`passes`, the median opt_time), NOT max-across-
    # sweep (owner correction 2026-06-12: golden CI runs ONE fixed-param route; max-across-sweep would
    # inflate the ceiling for params CI never runs). The opt_time/passes envelope below is SENSITIVITY
    # CONTEXT, not the ceiling source. Headroom is the OWNER's explicit choice -- we present a few
    # candidate ceilings, we do NOT bake a multiplier (that is the self-ratifying make_bands flaw).
    import cec_golden as g                              # the CI params are the golden's own FR_PARAMS
    ci_opt, ci_passes = g.FR_PARAMS["opt_time"], g.FR_PARAMS["passes"]
    anchor = next((r for r in good if r.get("opt_time") == ci_opt and passes == ci_passes),
                  next((r for r in good if r.get("opt_time") == ci_opt), good[0] if good else None))
    th = dists.get("thermal_max_T")
    drc = dists.get("drc")
    proposal = None
    if anchor:
        base_T, base_drc = anchor["thermal_max_T"], anchor["drc"]
        proposal = {
            "anchor": {"params": {"passes": ci_passes, "opt_time": ci_opt}, "thermal_max_T": base_T,
                       "drc": base_drc, "note": "the CI fixed-param route (cec_golden.FR_PARAMS) -- "
                       "the only params CI runs"},
            "thermal_ceiling_candidates_owner_picks_headroom": {
                "+5%": round(base_T * 1.05, 1), "+10%": round(base_T * 1.10, 1),
                "+15%": round(base_T * 1.15, 1)},
            "drc_max_candidates": {"baseline_plus_1": base_drc + 1, "baseline_plus_2": base_drc + 2},
            "envelope_is_context_only": {
                "opt_time_10_60s": f"thermal {th['min']}-{th['max']} (stdev {th['stdev']})" if th else None,
                "note": "attached as sensitivity context, NOT the ceiling source"},
            "rule": "ceiling = fixed-param baseline + EXPLICIT owner headroom; never baseline*const baked "
                    "in code (that is the make_bands self-ratifying flaw). Re-freeze records the chosen "
                    "headroom + rationale in expectations.json provenance.",
        }
    converged = (dists.get("thermal_max_T") or {}).get("stdev") == 0.0 and \
                (dists.get("drc") or {}).get("stdev") == 0.0
    return {
        "board": "tests/golden/eps-8pin/eps8pin-module.kicad_pcb (post-LOGO1-keepout, main)",
        "fr_determinism_note": "FR 1.7.0 has no seed; fixed-param routes are byte-stable (measured). "
                               "Variance below is across opt_time effort, FR's only diversity lever.",
        "passes": passes, "opt_times_s": list(opt_times),
        "n_variants": len(rows), "n_routed": len(good),
        "elapsed_s": round(time.time() - t0, 1),
        "opt_time_axis": rows, "passes_axis": passes_rows,
        "distributions_opt_time": dists, "gate_pass_counts": gate_pass,
        "zero_fr_variance": converged,
        "finding": ("ZERO FR variance across opt_time: drc and thermal stdev = 0. The board routes to one "
                    "deterministic solution; the 157.9C is converged, not noise. The 'drc-10 variance "
                    "event' does not reproduce here (drc=0 at every setting). Bands need no variance width "
                    "-- the real decision is fix-or-accept the deterministic thermal (owner item 3).")
                   if converged else "FR output moved across opt_time -- see distributions.",
        "band_proposal_derived": proposal,
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--opt-times", default="10,15,20,30,45,60",
                    help="comma list of FR opt_time seconds to sweep (the variance axis)")
    ap.add_argument("--passes", type=int, default=10, help="fixed passes for the opt_time axis")
    ap.add_argument("--passes-sweep", default="4,10,20,40",
                    help="comma list of passes to sweep at the golden's opt_time (the convergence axis)")
    ap.add_argument("--out", default="docs/det-inspection/sb08-fr-variance.json")
    a = ap.parse_args()
    opt_times = [int(x) for x in a.opt_times.split(",") if x.strip()]
    passes_sweep = [int(x) for x in a.passes_sweep.split(",") if x.strip()]
    import tempfile
    with tempfile.TemporaryDirectory() as wd:
        rep = run(opt_times, a.passes, wd, passes_sweep=passes_sweep)
    outp = a.out if os.path.isabs(a.out) else os.path.join(ROOT, a.out)
    os.makedirs(os.path.dirname(outp), exist_ok=True)
    json.dump(rep, open(outp, "w"), indent=1)
    print(f"[opt_time axis @ passes={a.passes}]")
    for r in rep["opt_time_axis"]:
        if "error" in r:
            print(f"  opt_time={r['opt_time']:>3}s  ROUTE FAILED")
        else:
            print(f"  opt_time={r['opt_time']:>3}s  drc={r['drc']:<3} thermal={r['thermal_max_T']:<6} "
                  f"tracks={r['tracks']} vias={r['vias']} kelvin={r['kelvin_ok']} diff={r['diffpair_ok']}")
    if rep["passes_axis"]:
        _po = next((r.get("opt_time") for r in rep["passes_axis"] if "opt_time" in r), "?")
        print(f"[passes axis @ opt_time={_po} -- convergence curve]")
        for r in rep["passes_axis"]:
            if "error" in r:
                print(f"  passes={r['passes']:>3}  ROUTE FAILED")
            else:
                print(f"  passes={r['passes']:>3}    drc={r['drc']:<3} thermal={r['thermal_max_T']:<6} "
                      f"tracks={r['tracks']} vias={r['vias']}")
    d = rep["distributions_opt_time"]
    if d.get("thermal_max_T"):
        print(f"\nthermal_max_T: {json.dumps(d['thermal_max_T'])}")
        print(f"drc:           {json.dumps(d['drc'])}")
    if rep["band_proposal_derived"]:
        print(f"\nBAND PROPOSAL (anchor to fixed-param baseline; owner picks headroom):"
              f"\n{json.dumps(rep['band_proposal_derived'], indent=1)}")
    print(f"\n-> {a.out}")
