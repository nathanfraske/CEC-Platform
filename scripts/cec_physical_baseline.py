#!/usr/bin/env python3
"""Emit deterministic physical-design baselines for current BETA boards."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
DEFAULT_SUITE = os.path.join(ROOT, "benchmarks", "physical-design-suite.json")


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_suite(path=DEFAULT_SUITE):
    with open(path, encoding="utf-8") as stream:
        suite = json.load(stream)
    if int(suite.get("schema", 0)) != 1:
        raise ValueError("unsupported physical-design suite schema")
    ids = [row.get("id") for row in suite.get("cases") or ()]
    if not ids or len(ids) != len(set(ids)) or any(not row for row in ids):
        raise ValueError("physical-design case ids must be present and unique")
    return suite


def _resolve_current_beta(case):
    board_rel = str(case.get("board") or "")
    schematic_rel = str(case.get("root_schematic") or "")
    for label, relative in (("board", board_rel),
                            ("root_schematic", schematic_rel)):
        normalized = os.path.normpath(relative).replace("\\", "/")
        if not normalized.startswith("beta/") or any(token in normalized.lower()
                for token in ("archive", "legacy", "old-revision", "build/")):
            raise ValueError("%s is not an admissible current BETA path: %s" %
                             (label, relative))
    board = os.path.join(ROOT, board_rel)
    schematic = os.path.join(ROOT, schematic_rel)
    if not os.path.isfile(board) or not os.path.isfile(schematic):
        raise FileNotFoundError("missing benchmark artifact for %s" % case["id"])
    with open(schematic, encoding="utf-8") as stream:
        root_text = stream.read()
    base = os.path.dirname(schematic)
    missing_sheets = []
    unreferenced_sheets = []
    for sheet in case.get("required_sheets") or ():
        if not os.path.isfile(os.path.join(base, sheet)):
            missing_sheets.append(sheet)
        if sheet not in root_text:
            unreferenced_sheets.append(sheet)
    if missing_sheets or unreferenced_sheets:
        raise ValueError("%s hierarchy mismatch: missing=%r unreferenced=%r" %
                         (case["id"], missing_sheets, unreferenced_sheets))
    return board, schematic


def build_baseline(case, *, grid_mm=1.0, iters=0, backend="cpu",
                   congestion=False, critical_nets=()):
    import cec_boarddb
    import cec_constraints
    import cec_route_preflight

    board, schematic = _resolve_current_beta(case)
    database = cec_boarddb.BoardDB.from_board(board)
    expected_profile = case.get("expected_profile")
    if (expected_profile is not None and
            database.declared_profile != str(expected_profile)):
        raise ValueError("%s declared profile %r != expected %r" %
                         (case["id"], database.declared_profile,
                          str(expected_profile)))
    expected_layers = tuple(case.get("expected_routing_layers") or ())
    if expected_layers and database.routing_layers != expected_layers:
        raise ValueError("%s routing layers %r != expected %r" %
                         (case["id"], database.routing_layers,
                          expected_layers))
    expected_copper = case.get("expected_copper_layers")
    if (expected_copper is not None and
            database.copper_layer_count != int(expected_copper)):
        raise ValueError("%s copper layer count %d != expected %d" %
                         (case["id"], database.copper_layer_count,
                          int(expected_copper)))
    constraint_ir = cec_constraints.compiled_constraint_ir()
    report = cec_route_preflight.analyze(
        board, grid_mm=float(grid_mm), iters=int(iters), backend=backend,
        run_congestion=bool(congestion), run_critical_routes=False,
        critical_nets=tuple(critical_nets or ()))
    evidence = cec_route_preflight.compact_placement_evidence(report)
    # Runtime is deliberately excluded from the reproducible artifact. It is
    # a benchmark observation, not part of board identity.
    evidence.pop("wall_s", None)
    footprints = database.footprints
    net_names = sorted({pad.net for pad in database.pads})
    return {
        "schema": 1,
        "suite_case": case["id"],
        "revision_policy": "current_beta_hierarchical_only",
        "artifacts": {
            "board": os.path.relpath(board, ROOT).replace(os.sep, "/"),
            "board_sha256": _sha256(board),
            "root_schematic": os.path.relpath(
                schematic, ROOT).replace(os.sep, "/"),
            "root_schematic_sha256": _sha256(schematic),
            "required_sheet_sha256": {
                sheet: _sha256(os.path.join(os.path.dirname(schematic), sheet))
                for sheet in case.get("required_sheets") or ()},
        },
        "geometry": {
            "boarddb_schema": database.SCHEMA,
            "fingerprint": database.fingerprint,
            "profile": database.profile,
            "declared_profile": database.declared_profile,
            "copper_layer_count": database.copper_layer_count,
            "routing_layers": list(database.routing_layers),
            "footprint_count": len(footprints),
            "pad_count": len(database.pads),
            "net_count": len(net_names),
            "edge_bbox_mm": list(database.edge_bbox),
        },
        "analysis": {
            "constraint_ir": constraint_ir.as_dict(include_records=False),
            "grid_mm": float(grid_mm),
            "iters": int(iters),
            "backend": str(backend),
            "congestion": bool(congestion),
            "evidence": evidence,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case")
    parser.add_argument("--suite", default=DEFAULT_SUITE)
    parser.add_argument("--grid-mm", type=float, default=1.0)
    parser.add_argument("--iters", type=int, default=0)
    parser.add_argument("--backend", default="cpu")
    parser.add_argument("--congestion", action="store_true")
    parser.add_argument("--critical-net", action="append", default=[])
    parser.add_argument("--output")
    args = parser.parse_args()
    suite = load_suite(args.suite)
    cases = {row["id"]: row for row in suite["cases"]}
    if args.case not in cases:
        parser.error("unknown case %r; choose one of %s" %
                     (args.case, ", ".join(sorted(cases))))
    result = build_baseline(
        cases[args.case], grid_mm=args.grid_mm, iters=args.iters,
        backend=args.backend, congestion=args.congestion,
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


if __name__ == "__main__":
    main()
