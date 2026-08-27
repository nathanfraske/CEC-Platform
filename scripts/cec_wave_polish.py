#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Re-run one adjudicated wave placement through the production deep polish.

This is deliberately a real module (rather than a stdin/python -c wrapper):
pcbnew validation uses the multiprocessing ``spawn`` method and therefore needs
an importable ``__main__``.  The command preserves the full verdict and routed
artifact for a controlled A/B or for recovering a polish invalidated by an
orchestrator failure.
"""
import argparse
import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import cec_fresh_wave as wave  # noqa: E402


def failed_nets(report):
    """Recover the stable failed-net set from either report schema."""
    best = (report or {}).get("best") or {}
    explicit = best.get("unconn_nets") or ()
    if explicit:
        return sorted(set(str(n) for n in explicit if n))
    return sorted({str(n)
                   for item in best.get("unconn_signature") or ()
                   for n in item.get("nets") or () if n})


def compact_verdict(verdict):
    keys = ("label", "gate", "kelvin_ok", "diffpair_ok", "drc",
            "drc_types", "unconnected", "unconn_nets",
            "unconn_signature", "unconn_signature_sha256", "sort_key",
            "route_s", "route_stage_s", "wall_s", "coordination",
            "future_route", "completion_report", "reasons", "routed")
    return {key: verdict.get(key) for key in keys}


def external_placed_row(board_name, board_path, W, H):
    """Build the normal reuse contract for an already-materialized placement."""
    board_path = os.path.abspath(board_path)
    if not os.path.isfile(board_path):
        raise FileNotFoundError("placed board not found: %s" % board_path)
    params = wave._placement_params(board_name, W, H)
    cfg = wave.csp.Config.load(board_name, params=params)
    craft = wave.csp.placement_craft_evidence(board_path, cfg=cfg)
    return {
        "placed": board_path,
        "cfg_params": params,
        "placement_craft": craft,
        "place_craft_key": list(wave.csp.placement_craft_key(craft)),
        "future_route": wave._future_route_preflight(
            board_path, critical_nets=tuple(
                params.get("critical_route_nets", ()) or ())),
        "intent_log": ["external placed-board validation: %s" % board_path],
    }


def main():
    ap = argparse.ArgumentParser(
        description="deep-polish one current wave placement with reactive hints")
    ap.add_argument("--board", default="hub-standard-rev2")
    ap.add_argument("--intent", default="plain")
    ap.add_argument("--strategy", choices=("dataflow", "compact"),
                    default="dataflow")
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--report", required=True,
                    help="wave report carrying the failed endpoint signature")
    ap.add_argument("--passes", type=int, default=24)
    ap.add_argument("--opt", type=int, default=30)
    ap.add_argument("--coord-stubs", action="store_true",
                    help="opt into measured-regressive hard coordinator stubs")
    ap.add_argument("--work", required=True)
    ap.add_argument("--placed",
                    help="reuse this materialized placement instead of compiling one")
    ap.add_argument("--out", required=True,
                    help="destination .kicad_pcb (JSON verdict is written beside it)")
    args = ap.parse_args()

    if args.board not in wave.BOARD_WH:
        ap.error("unknown wave board %r" % args.board)
    os.makedirs(args.work, exist_ok=True)
    with open(args.report, encoding="utf-8") as fh:
        prior = json.load(fh)
    nets = failed_nets(prior)
    W, H = wave.BOARD_WH[args.board]
    row = (external_placed_row(args.board, args.placed, W, H)
           if args.placed else wave._place_variant(
               args.board, W, H, args.intent, args.strategy, args.seed,
               None, args.work))
    print("POLISH_INPUT " + json.dumps({
        "placed": row.get("placed"), "failed_nets": nets}, sort_keys=True),
        flush=True)
    verdict = wave._grade_variant(
        args.board, W, H, args.intent, args.strategy, args.seed,
        args.passes, args.opt, args.work, proposal=None, polish=True,
        placed_row=row, coord_nets=(nets if args.coord_stubs else ()))
    summary = compact_verdict(verdict)
    print("POLISH_RESULT " + json.dumps(summary, sort_keys=True, default=str),
          flush=True)

    src = verdict.get("routed")
    if not src or not os.path.isfile(str(src)):
        return 2
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    shutil.copy2(src, args.out)
    src_base = str(src)[:-len(".kicad_pcb")]
    out_base = str(args.out)[:-len(".kicad_pcb")]
    for ext in (".kicad_pro", ".kicad_dru"):
        if os.path.isfile(src_base + ext):
            shutil.copy2(src_base + ext, out_base + ext)
    summary["published"] = os.path.abspath(args.out)
    summary["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    with open(out_base + ".json", "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, sort_keys=True, default=str)
    print("POLISH_ARTIFACT " + os.path.abspath(args.out), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
