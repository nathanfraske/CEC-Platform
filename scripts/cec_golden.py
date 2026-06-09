#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_golden -- golden-board regression for the PIPELINE ITSELF (SB-08).
# ============================================================================
# Agents modify scripts/ (PR #17 merged, #18 merged); a change must prove it
# still produces a good board. This is the spec's golden-sample method pointed
# at the TOOLCHAIN: route + score + physics on a FROZEN eps-8pin floorplan
# (tests/golden/eps-8pin/) and compare against stored expectation BANDS
# (tests/golden/expectations.json) -- bands, not exact values, so a legitimate
# improvement does not false-fail; a band change requires a human-approved
# expectation bump in the same PR (--freeze writes a new baseline).
#
# RUNNER: needs Freerouting + pcbnew + kicad-cli. Owner decision (2026-06-09):
# run ON-DEVICE in the routing container --
#   docker compose -f docker/compose.yaml run --rm --no-deps routing \
#       bash -lc 'cd /workspace && python3 scripts/cec_golden.py'
# Run it before merging any scripts/** change that touches the route/score/
# physics plane. Freerouting 1.7.0 is deterministic, so with an unchanged
# pipeline the candidate is byte-stable; the bands absorb environment drift.
#
# Exit 0 = within bands; 1 = regression (or no baseline; use --freeze once).
# ============================================================================
import os
import sys
import json
import time
import argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

GOLDEN_DIR = os.path.join(ROOT, "tests", "golden", "eps-8pin")
GOLDEN_PCB = os.path.join(GOLDEN_DIR, "eps8pin-module.kicad_pcb")
EXPECT = os.path.join(ROOT, "tests", "golden", "expectations.json")

# Fixed route effort: enough for the gates to settle, small enough to stay fast.
FR_PARAMS = {"passes": 10, "opt_time": 20, "threads": 1}


def run_golden(out_dir=None):
    import cec_fr
    import cec_score
    import cec_synth_pipeline as sp

    out_dir = out_dir or os.path.join(ROOT, "build", "golden")
    os.makedirs(out_dir, exist_ok=True)
    t0 = time.time()
    # Pour AFTER route (the documented ordering): the additive same-net 12V pours are what
    # carry the cable current, so the physics stage reads real copper instead of clamping
    # at the fusing ceiling on a 0.2 mm FR trace.
    pours = cec_fr.derive_power_pours(GOLDEN_PCB)
    cands = cec_fr.generate_batch(GOLDEN_PCB, seeds=(0,), params=dict(FR_PARAMS),
                                  power_pours=pours, out_dir=out_dir)
    ok = [c for c in cands if c.ok and c.board]
    if not ok:
        return {"error": "no candidate routed", "elapsed_s": round(time.time() - t0, 1)}
    board = ok[0].board
    m = cec_score.score(board)
    cfg = sp.Config.load(GOLDEN_DIR)
    th = sp.electrothermal_solve(board, cfg)
    return {
        "elapsed_s": round(time.time() - t0, 1),
        "board": board,
        "kelvin_ok": m.kelvin_ok,
        "diffpair_ok": m.diffpair_ok,
        "drc": m.drc,
        "unconnected": m.unconnected,
        "tracks": m.tracks,
        "vias": m.vias,
        "length": m.length,
        "drc_types": m.drc_types,
        "thermal_max_T": round(th.max_T, 1),
        "thermal_max_dT": round(th.max_dT, 1),
        "thermal_ambient": th.ambient,
    }


def make_bands(res):
    """Derive expectation bands from a measured baseline. Counts get +/-20-30%;
    gates and bounded counts are hard."""
    return {
        "frozen": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "fr_params": dict(FR_PARAMS),
        "baseline": {k: res[k] for k in ("drc", "unconnected", "tracks", "vias", "length",
                                          "thermal_max_T", "kelvin_ok", "diffpair_ok")},
        "bands": {
            # HARD gates: the safety result must not regress, period.
            "kelvin_ok": res["kelvin_ok"],
            "diffpair_ok": res["diffpair_ok"],
            # bounded counts: a regression is MORE of these, not fewer
            "drc_max": res["drc"] + max(2, int(res["drc"] * 0.5)),
            "unconnected_max": res["unconnected"] + max(2, int(res["unconnected"] * 0.5)),
            # structure bands: wildly different copper means the generator changed behavior
            "tracks_min": int(res["tracks"] * 0.7), "tracks_max": int(res["tracks"] * 1.3),
            "vias_min": int(res["vias"] * 0.6), "vias_max": int(res["vias"] * 1.4),
            # physics band: the analytic model's read of the same copper
            "thermal_max_T_max": round(res["thermal_max_T"] * 1.15, 1),
        },
    }


def compare(res, exp):
    b = exp["bands"]
    fails = []
    if b.get("kelvin_ok") and not res["kelvin_ok"]:
        fails.append("kelvin_ok regressed to False (HARD gate)")
    if b.get("diffpair_ok") and not res["diffpair_ok"]:
        fails.append("diffpair_ok regressed to False (HARD gate)")
    if res["drc"] > b["drc_max"]:
        fails.append(f"drc {res['drc']} > band max {b['drc_max']}")
    if res["unconnected"] > b["unconnected_max"]:
        fails.append(f"unconnected {res['unconnected']} > band max {b['unconnected_max']}")
    if not (b["tracks_min"] <= res["tracks"] <= b["tracks_max"]):
        fails.append(f"tracks {res['tracks']} outside band [{b['tracks_min']}, {b['tracks_max']}]")
    if not (b["vias_min"] <= res["vias"] <= b["vias_max"]):
        fails.append(f"vias {res['vias']} outside band [{b['vias_min']}, {b['vias_max']}]")
    if res["thermal_max_T"] > b["thermal_max_T_max"]:
        fails.append(f"thermal max_T {res['thermal_max_T']} > band max {b['thermal_max_T_max']}")
    return fails


def main(argv=None):
    ap = argparse.ArgumentParser(description="golden-board pipeline regression (SB-08)")
    ap.add_argument("--freeze", action="store_true",
                    help="write the current result as the new expectation baseline "
                         "(a band bump is a human-approved act -- commit it in the same PR "
                         "as the change that legitimately moved the numbers)")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)

    res = run_golden(a.out)
    print(json.dumps({k: v for k, v in res.items() if k != "board"}, indent=1))
    if "error" in res:
        print("GOLDEN: FAIL (no candidate routed)", file=sys.stderr)
        return 1

    if a.freeze:
        exp = make_bands(res)
        json.dump(exp, open(EXPECT, "w"), indent=1)
        print(f"GOLDEN: baseline frozen -> {os.path.relpath(EXPECT, ROOT)}")
        return 0

    if not os.path.isfile(EXPECT):
        print("GOLDEN: no expectations.json -- run once with --freeze to set the baseline",
              file=sys.stderr)
        return 1
    exp = json.load(open(EXPECT))
    fails = compare(res, exp)
    for f in fails:
        print(f"  REGRESSION: {f}", file=sys.stderr)
    print(f"GOLDEN: {'PASS (within bands, baseline ' + exp['frozen'] + ')' if not fails else 'FAIL'}")
    # ledger line (fail-safe)
    try:
        import cec_ledger
        cec_ledger.append(board="golden:eps-8pin", mode="golden",
                          verdict=("pass" if not fails else "fail"),
                          board_file=res.get("board"), input_board=GOLDEN_PCB,
                          elapsed_s=res.get("elapsed_s"),
                          extra={"fails": fails})
    except Exception:
        pass
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
