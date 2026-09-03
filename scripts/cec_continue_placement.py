#!/usr/bin/env python3
"""Continue bounded generic placement-craft repair from an admitted artifact.

The full pipeline deliberately stops when exact placement craft is open.  A
later wave should be able to continue from that incumbent without regenerating
every global placement, but it must never interpret an ordinarily routed board
as a placement source and erase its copper.  This entry point accepts only
boards whose existing copper is locked pipeline-owned cell/power geometry.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import cec_full_pipeline as full
import cec_synth_pipeline as synth


def _unlocked_copper(board):
    return [
        {
            "kind": item.GetClass(),
            "net": item.GetNetname(),
            "uuid": item.m_Uuid.AsString(),
        }
        for item in board.GetTracks() if not item.IsLocked()
    ]


def continue_placement(*, board_name, input_board, output_board,
                       report_path=None, max_trials=128, rounds=12,
                       epochs=3):
    import pcbnew

    source = Path(input_board).resolve()
    output = Path(output_board).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    loaded = pcbnew.LoadBoard(str(source))
    if loaded is None:
        raise RuntimeError("placement source is unreadable: %s" % source)
    unlocked = _unlocked_copper(loaded)
    if unlocked:
        raise RuntimeError(
            "placement continuation refuses unlocked detailed routing: %s" %
            unlocked[:8])

    cfg = synth.Config.load(board_name)
    candidate = synth.placement_candidate_from_board(
        cfg, str(source), allow_routed=True)
    candidate, repair = synth.repair_placement_craft_epochs(
        cfg, candidate, max_trials=int(max_trials), rounds=int(rounds),
        epochs=int(epochs))
    output.parent.mkdir(parents=True, exist_ok=True)
    synth.materialize(candidate, cfg, str(output))
    evidence = synth.placement_craft_evidence(str(output), cfg=cfg)
    result = {
        "schema": 1,
        "board": board_name,
        "source": str(source),
        "output": str(output),
        "ok": bool(evidence.get("ok")),
        "craft_key": list(synth.placement_craft_key(evidence)),
        "repair": repair,
        "craft": evidence,
    }
    if report_path:
        full.atomic_json(Path(report_path).resolve(), result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="continue fail-closed generic placement craft repair")
    parser.add_argument("--board", required=True)
    parser.add_argument("--input-board", required=True)
    parser.add_argument("--output-board", required=True)
    parser.add_argument("--report")
    parser.add_argument("--max-trials", type=int, default=128)
    parser.add_argument("--rounds", type=int, default=12)
    parser.add_argument("--epochs", type=int, default=3)
    args = parser.parse_args(argv)
    result = continue_placement(
        board_name=args.board, input_board=args.input_board,
        output_board=args.output_board, report_path=args.report,
        max_trials=args.max_trials, rounds=args.rounds,
        epochs=args.epochs)
    print("placement continuation: %s key=%s accepted=%s stop=%s" % (
        "PASS" if result["ok"] else "BLOCK",
        result["craft_key"],
        (result.get("repair") or {}).get("accepted_count"),
        (result.get("repair") or {}).get("stop_reason")), flush=True)
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
