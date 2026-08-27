#!/usr/bin/env python3
"""Benchmark exact BoardDB placement deltas against KiCad save/reload trials."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time


HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import cec_route_preflight  # noqa: E402


def _stable_evidence(report):
    evidence = cec_route_preflight.compact_placement_evidence(report)
    evidence.pop("wall_s", None)
    # BoardDB v1 incrementally owns pad geometry and pin-access decisions. The
    # coarse global obstacle raster is still rebuilt by KiCad for finalists;
    # its base-context counts are intentionally outside this equivalence claim.
    evidence.pop("blocked_cell_count", None)
    evidence.pop("blocked_cells_per_layer", None)
    forecast = dict(evidence.get("future_congestion") or {})
    forecast.pop("context_fingerprint", None)
    forecast.pop("incremental", None)
    evidence["future_congestion"] = forecast
    return evidence


def _differences(left, right, *, limit=24):
    differences = []

    def walk(a, b, path):
        if len(differences) >= limit:
            return
        if type(a) is not type(b):
            differences.append({"path": path, "incremental": repr(a),
                                "materialized": repr(b)})
        elif isinstance(a, dict):
            for key in sorted(set(a) | set(b)):
                if key not in a or key not in b:
                    differences.append({
                        "path": "%s/%s" % (path, key),
                        "incremental": repr(a.get(key, "<missing>")),
                        "materialized": repr(b.get(key, "<missing>")),
                    })
                else:
                    walk(a[key], b[key], "%s/%s" % (path, key))
        elif isinstance(a, list):
            if len(a) != len(b):
                differences.append({
                    "path": path + "/length",
                    "incremental": len(a), "materialized": len(b),
                })
            for index, (x, y) in enumerate(zip(a, b)):
                walk(x, y, "%s/%d" % (path, index))
        elif a != b:
            differences.append({"path": path, "incremental": a,
                                "materialized": b})

    walk(left, right, "")
    return differences


def _candidate_refs(report, database):
    owners = []
    blockers = []
    for row in (report.get("pin_access") or {}).get("blocked") or ():
        owners.append(str(row.get("ref") or ""))
        for direction in row.get("blocked_options") or ():
            for layer in direction.get("layers") or ():
                blockers.extend(str(blocker.get("ref") or "")
                                for blocker in layer.get("blockers") or ())
    available = set(database.footprints)
    pressure = [str(row.get("ref") or "")
                for row in (report.get("future_congestion") or {}).get(
                    "pressure_refs", ())]

    def admissible(ref):
        return (ref in available and
                not ref.startswith(("J", "H", "FID", "LOGO")))

    ordered = []
    for ref in blockers + owners + pressure:
        if admissible(ref) and ref not in ordered:
            ordered.append(ref)
    # A clean board has no obstruction-named neighborhood. Preserve utility as
    # a geometry benchmark without diluting a real repair neighborhood with
    # unrelated parts when obstruction evidence does exist.
    if not ordered:
        ordered = [ref for ref in sorted(available) if admissible(ref)]
    return ordered


def _proposals(report, database, limit):
    refs = _candidate_refs(report, database)
    proposals = []
    for delta, kind in ((180.0, "rotate_180"),
                        (90.0, "rotate_90"),
                        (270.0, "rotate_270")):
        for ref in refs:
            pose = database.footprints[ref]
            proposals.append({
                "kind": kind, "ref": ref,
                "placements": {
                    ref: (pose.x, pose.y,
                          (pose.rotation + delta) % 360.0)},
            })
            if len(proposals) >= limit:
                return proposals
    for dx, dy in ((0.25, 0.0), (-0.25, 0.0),
                   (0.0, 0.25), (0.0, -0.25)):
        for ref in refs:
            pose = database.footprints[ref]
            proposals.append({
                "kind": "shift", "ref": ref,
                "placements": {
                    ref: (pose.x + dx, pose.y + dy, pose.rotation)},
            })
            if len(proposals) >= limit:
                return proposals
    return proposals


def _materialize_delta(source, target, placements):
    import pcbnew

    board = pcbnew.LoadBoard(source)
    footprints = {str(row.GetReference()): row
                  for row in board.GetFootprints()}
    for ref, (x, y, rotation) in placements.items():
        footprint = footprints[ref]
        footprint.SetPosition(pcbnew.VECTOR2I(
            int(round(float(x) * 1.0e6)),
            int(round(float(y) * 1.0e6))))
        footprint.SetOrientationDegrees(float(rotation))
    pcbnew.SaveBoard(target, board)


def benchmark(board_path, *, trials=8, grid_mm=1.0,
              critical_nets=()):
    board_path = os.path.abspath(board_path)
    context_started = time.monotonic()
    context = cec_route_preflight.prepare_incremental_access(
        board_path, grid_mm=float(grid_mm),
        critical_nets=tuple(critical_nets or ()))
    context_wall = time.monotonic() - context_started
    base = cec_route_preflight.analyze_incremental_access(
        context, run_future_congestion=True)
    base_stable = _stable_evidence(base)
    proposals = _proposals(base, context.board_db, max(0, int(trials)))
    incremental = []
    incremental_started = time.monotonic()
    for proposal in proposals:
        incremental.append(_stable_evidence(
            cec_route_preflight.analyze_incremental_access(
                context, placements=proposal["placements"],
                run_future_congestion=True)))
    incremental_wall = time.monotonic() - incremental_started

    materialized = []
    materialized_started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="cec-boarddb-benchmark-") as work:
        for index, proposal in enumerate(proposals):
            target = os.path.join(work, "%03d.kicad_pcb" % index)
            _materialize_delta(
                board_path, target, proposal["placements"])
            materialized.append(_stable_evidence(
                cec_route_preflight.analyze(
                    target, grid_mm=float(grid_mm), iters=0,
                    backend="cpu", run_congestion=False,
                    run_critical_routes=False,
                    run_future_congestion=True,
                    critical_nets=tuple(critical_nets or ()))))
    materialized_wall = time.monotonic() - materialized_started

    mismatches = []
    for index, (fast, authority) in enumerate(zip(incremental, materialized)):
        if fast == authority:
            continue
        payload = json.dumps(
            {"incremental": fast, "materialized": authority},
            sort_keys=True, separators=(",", ":")).encode("utf-8")
        mismatches.append({
            "index": index, "proposal": proposals[index],
            "diff_sha256": hashlib.sha256(payload).hexdigest(),
            "differences": _differences(fast, authority),
        })
    count = len(proposals)
    incremental_per = incremental_wall / count if count else 0.0
    materialized_per = materialized_wall / count if count else 0.0
    forecast_keys = (
        "future_critical_corridor_conflicts",
        "future_overflow_units",
        "future_corridor_obstacle_crossings",
        "future_expected_via_count",
        "future_wire_demand_units",
    )
    baseline_forecast = {
        key: int(base_stable.get(key, 0) or 0) for key in forecast_keys}
    outcomes = []
    for proposal, evidence in zip(proposals, incremental):
        metrics = {key: int(evidence.get(key, 0) or 0)
                   for key in forecast_keys}
        outcomes.append({
            "kind": proposal["kind"], "ref": proposal["ref"],
            "metrics": metrics,
            "delta": {key: metrics[key] - baseline_forecast[key]
                      for key in forecast_keys},
        })
    return {
        "schema": 1,
        "comparison_scope": (
            "quick_access_and_future_congestion_excluding_legacy_"
            "global_obstacle_counts"),
        "board": board_path,
        "boarddb_fingerprint": context.board_db.fingerprint,
        "trials": count,
        "exact_matches": count - len(mismatches),
        "mismatches": mismatches,
        "baseline_forecast": baseline_forecast,
        "forecast_outcomes": outcomes,
        "timing_s": {
            "context_build": round(context_wall, 6),
            "incremental_total": round(incremental_wall, 6),
            "incremental_per_trial": round(incremental_per, 6),
            "materialized_total": round(materialized_wall, 6),
            "materialized_per_trial": round(materialized_per, 6),
            "steady_state_speedup": round(
                materialized_per / incremental_per, 3)
                if incremental_per else None,
            "amortized_speedup": round(
                materialized_wall / (context_wall + incremental_wall), 3)
                if context_wall + incremental_wall else None,
        },
        "proposals": [{"kind": row["kind"], "ref": row["ref"]}
                      for row in proposals],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("board")
    parser.add_argument("--trials", type=int, default=8)
    parser.add_argument("--grid-mm", type=float, default=1.0)
    parser.add_argument("--critical-net", action="append", default=[])
    parser.add_argument("--output")
    args = parser.parse_args()
    result = benchmark(
        args.board, trials=args.trials, grid_mm=args.grid_mm,
        critical_nets=args.critical_net)
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        target = os.path.abspath(args.output)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        temporary = target + ".tmp-%d" % os.getpid()
        with open(temporary, "w", encoding="utf-8") as stream:
            stream.write(payload)
        os.replace(temporary, target)
    else:
        sys.stdout.write(payload)
    return 0 if result["exact_matches"] == result["trials"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
