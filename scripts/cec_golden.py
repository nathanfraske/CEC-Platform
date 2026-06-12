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
    # SYNTHESIZE high-current copper (SB-08 item 3a, 2026-06-12). The owner-ratified FR-04 layer policy
    # (d26651d) correctly denies FR signal routing on the power planes; without it the board leaned on
    # plane routing for thermal spread (the +25 C the SB-08 forensic pinned). The principled fix is to give
    # the cable force corridors REAL thermal copper -- F.Cu+B.Cu mirror pour + via field -- so current
    # spreads through proper copper area, not the planes. Additive same-net (never strands the Kelvin tap).
    # Measured: 157.9 -> 75.5 C at drc 0, kelvin+diffpair pass. OPT-IN (CEC_GOLDEN_SYNTH=1) so this branch
    # changes nothing by default -- enabling it is the owner's item-3a act, coupled with the item-4
    # re-freeze (the committed golden stays red-pending until the owner picks 3a and re-freezes).
    if os.environ.get("CEC_GOLDEN_SYNTH") == "1":
        synth_out = os.path.join(out_dir, "golden-synth.kicad_pcb")
        cec_fr.synthesize_power_copper(board, synth_out)
        board = synth_out
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


def make_bands(res, *, thermal_headroom=None, rationale=None):
    """Derive expectation bands from a measured baseline at the FIXED CI params.

    SB-08 item 6 (2026-06-12): the old version set thermal_max_T_max = baseline*1.15 -- a baked
    multiplier that FLOATS UP with whatever baseline you freeze, so re-freezing a hotter board silently
    raises the ceiling (the PR #37 147.4->181.6 re-band). That is a self-ratifying gate. The ceiling now
    requires an EXPLICIT thermal_headroom (fraction) chosen and recorded by the owner -- there is no
    default multiplier; passing none refuses to invent one. FR 1.7.0 is deterministic at the CI params
    (no seed; sb08-fr-variance proves stdev 0), so any headroom is modelling slack, not variance cover --
    which is exactly why it must be a recorded decision, not a constant. Provenance is written into the
    frozen file so a future reader sees the params + headroom + rationale behind every band."""
    if thermal_headroom is None:
        raise ValueError("make_bands: thermal_headroom is REQUIRED (owner-chosen; no baked multiplier -- "
                         "SB-08 item 6). Pass e.g. thermal_headroom=0.10 with a rationale.")
    return {
        "frozen": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "frozen_from": {
            "fr_params": dict(FR_PARAMS),
            "fr_version": "1.7.0 (pinned, no seed -- deterministic at these params)",
            "thermal_headroom": thermal_headroom,
            "thermal_basis": f"fixed-param baseline {res['thermal_max_T']} C x (1+{thermal_headroom}) "
                             f"= {round(res['thermal_max_T'] * (1 + thermal_headroom), 1)}; "
                             "headroom is owner-chosen modelling slack (FR is deterministic, stdev 0)",
            "rationale": rationale or "(none supplied)",
        },
        "fr_params": dict(FR_PARAMS),
        "baseline": {k: res[k] for k in ("drc", "unconnected", "tracks", "vias", "length",
                                          "thermal_max_T", "kelvin_ok", "diffpair_ok")},
        "bands": {
            # HARD gates: the safety result must not regress, period.
            "kelvin_ok": res["kelvin_ok"],
            "diffpair_ok": res["diffpair_ok"],
            # bounded counts: a regression is MORE of these. Anchor to the (deterministic) baseline + 1.
            "drc_max": res["drc"] + 1,
            "unconnected_max": res["unconnected"] + max(2, int(res["unconnected"] * 0.5)),
            # structure bands: wildly different copper means the generator changed behavior
            "tracks_min": int(res["tracks"] * 0.7), "tracks_max": int(res["tracks"] * 1.3),
            "vias_min": int(res["vias"] * 0.6), "vias_max": int(res["vias"] * 1.4),
            # physics band: fixed-param baseline + the EXPLICIT owner headroom (no baked multiplier)
            "thermal_max_T_max": round(res["thermal_max_T"] * (1 + thermal_headroom), 1),
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
    ap.add_argument("--thermal-headroom", type=float, default=None,
                    help="REQUIRED with --freeze (SB-08 item 6): explicit owner-chosen fraction of "
                         "headroom over the fixed-param thermal baseline. No baked multiplier.")
    ap.add_argument("--rationale", default=None, help="provenance note recorded with --freeze")
    a = ap.parse_args(argv)

    res = run_golden(a.out)
    print(json.dumps({k: v for k, v in res.items() if k != "board"}, indent=1))
    if "error" in res:
        print("GOLDEN: FAIL (no candidate routed)", file=sys.stderr)
        return 1

    if a.freeze:
        exp = make_bands(res, thermal_headroom=a.thermal_headroom, rationale=a.rationale)
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
