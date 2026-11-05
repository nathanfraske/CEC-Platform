#!/usr/bin/env python3
"""Bounded normalization experiment on copies, never on the source board.

Produces before/after independent probes and retains a proposal for inspection.
It never promotes the proposal: spatial repair and complete transaction
admission remain separate from the dimensional requirement solver.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _normalize(path, *, spatial=False, spatial_budget=240.0):
    import pcbnew
    import cec_fr
    board = pcbnew.LoadBoard(str(path))
    if board is None:
        raise ValueError("cannot read trial board")
    report = cec_fr.normalize_netclass_geometry(board, str(path))
    if report.get("tracks") or report.get("vias"):
        for zone in board.Zones():
            zone.UnFill()
        if list(board.Zones()):
            import cec_zone_fill
            cec_zone_fill.fill(board)
        pcbnew.SaveBoard(str(path), board)
    if spatial:
        import cec_dimension_repair
        report["spatial_repair"] = cec_dimension_repair.repair_admitted(
            path, wall_budget_s=spatial_budget)
    return report


def replay(board_path, out_dir, board_hint, *, spatial=False, spatial_budget=240.0):
    from cec_fab_review_regression import _run_worker
    from cec_fr import copy_project_sidecars
    source, out = Path(board_path).resolve(), Path(out_dir).resolve()
    if out.exists():
        raise FileExistsError("use a fresh replay directory: %s" % out)
    source_sha = _digest(source)
    out.mkdir(parents=True)
    boards = {}
    for phase in ("before", "proposal"):
        directory = out / phase
        directory.mkdir()
        target = directory / source.name
        shutil.copy2(source, target)
        # Pour/placement ownership is executable authority, not decoration.
        # A replay without those sidecars can silently change which gates run.
        copy_project_sidecars(str(source), str(target))
        boards[phase] = target
    mutation_path = out / "normalization.json"
    command = [sys.executable, str(Path(__file__).resolve()), "--worker-normalize",
               "--board", str(boards["proposal"]), "--out", str(mutation_path)]
    if spatial:
        command += ["--spatial-repair", "--spatial-budget", str(spatial_budget)]
    worker = subprocess.run(command, capture_output=True, text=True,
                            timeout=120 + (spatial_budget if spatial else 0),
                            env={**os.environ, "CEC_THERMAL_BOARD_HINT": board_hint})
    if worker.returncode or not mutation_path.is_file():
        raise RuntimeError("normalization failed: " + worker.stderr[-4000:])
    probes = {}
    for phase, board in boards.items():
        probes[phase] = {kind: _run_worker(kind, board, board_hint, board.parent)
                         for kind in ("score", "constraints", "route_quality", "fab")}
    unchanged = source_sha == _digest(source)
    old, new = probes["before"], probes["proposal"]
    def failures(probe):
        return sorted(row["id"] for row in probe["constraints"].get("blockers", ()))
    report = {"schema": 1, "source": str(source), "source_sha256": source_sha,
              "source_unchanged": unchanged, "adopted": False,
              "status": "diagnostic_proposal_only", "probes": probes,
              "normalization": json.loads(mutation_path.read_text()),
              "comparison": {"before_blockers": failures(old), "proposal_blockers": failures(new),
                             "new_blocker_ids": sorted(set(failures(new)) - set(failures(old)))}}
    (out / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--board", required=True)
    parser.add_argument("--board-hint", default="")
    parser.add_argument("--out", required=True)
    parser.add_argument("--worker-normalize", action="store_true")
    parser.add_argument("--spatial-repair", action="store_true")
    parser.add_argument("--spatial-budget", type=float, default=240.0)
    args = parser.parse_args()
    if args.worker_normalize:
        Path(args.out).write_text(json.dumps(_normalize(args.board,
            spatial=args.spatial_repair, spatial_budget=args.spatial_budget), indent=2) + "\n")
        return 0
    report = replay(args.board, args.out, args.board_hint,
                    spatial=args.spatial_repair, spatial_budget=args.spatial_budget)
    print(json.dumps({key: value for key, value in report.items()
                      if key not in {"probes", "normalization"}}, sort_keys=True))
    return 0 if report["source_unchanged"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
