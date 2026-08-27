#!/usr/bin/env python3
"""Prove that placement preflight consumes the detailed-route reservation.

This is a bounded diagnostic: it compiles the board's routed-object recipe,
runs the incremental future-congestion model without negotiated routing, and
prints only the ownership/crossing summary needed by CI or an unattended-run
preflight.  It never edits the board.
"""

from __future__ import annotations

import argparse
import json
import os

import cec_fresh_wave
import cec_route_preflight
import cec_synth_pipeline


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("board")
    parser.add_argument("--board-config", choices=sorted(
        cec_fresh_wave.BOARD_PARAMS))
    parser.add_argument("--grid-mm", type=float, default=1.0)
    parser.add_argument("--route-iters", type=int, default=0)
    args = parser.parse_args()

    board = os.path.abspath(args.board)
    config_name = args.board_config or os.path.basename(
        os.path.dirname(os.path.dirname(board)))
    params = cec_fresh_wave.BOARD_PARAMS.get(config_name)
    if params is None:
        parser.error("--board-config is required for an unrecognized path")
    with cec_synth_pipeline._oracle_env(params):
        report = cec_route_preflight.analyze(
            board, grid_mm=args.grid_mm, iters=max(0, args.route_iters),
            run_congestion=args.route_iters > 0,
            run_critical_routes=False,
            critical_nets=tuple(params.get("critical_route_nets", ()) or ()),
            run_future_congestion=True)
    future = report.get("future_congestion") or {}
    reservation = report.get("route_reservations") or {}
    congestion = report.get("congestion") or {}
    stackup = report.get("stackup") or {}
    summary = {
        "schema": 1,
        "board": board,
        "gate": bool(report.get("gate")),
        "reservation_enabled": bool(reservation.get("enabled")),
        "reservation_fingerprint": reservation.get("fingerprint"),
        "reservation_rect_count": int(
            future.get("reservation_rect_count", 0) or 0),
        "reservation_cell_count": int(
            future.get("reservation_cell_count", 0) or 0),
        "reservation_owned_nets": list(
            future.get("reservation_owned_nets") or ()),
        "reservation_refused_nets": list(
            future.get("reservation_refused_nets") or ()),
        "reservation_crossings": int(
            future.get("reservation_crossings", 0) or 0),
        "reservation_connections_removed": int(
            stackup.get("reservation_connections_removed", 0) or 0),
        "global_unroutable_count": int(
            congestion.get("unroutable_count", 0) or 0),
        "global_residual_overuse": float(
            congestion.get("residual_overuse", 0.0) or 0.0),
        "global_residual_overuse_escaped": float(
            congestion.get("residual_overuse_escaped", 0.0) or 0.0),
        "overflow_units": int(future.get("overflow_units", 0) or 0),
        "pressure_refs": list(future.get("pressure_refs") or ()),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    if not summary["reservation_enabled"]:
        return 2
    if not summary["reservation_rect_count"]:
        return 3
    if summary["reservation_refused_nets"]:
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
