#!/usr/bin/env python3
"""Single-load worker phases for generated power-artifact settling.

KiCad's legacy pcbnew SWIG API owns process-global board state.  Running a
file cleanup that LoadBoard/save/reloads and then another cleanup in the same
interpreter can return a bare invalid SwigPyObject.  The coordinator invokes
one phase per fresh process through this small, deterministic boundary.
"""
from __future__ import annotations

import argparse
import json


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "phase", choices=("via", "floating", "nowhere", "admit",
                          "prune-current"))
    parser.add_argument("board")
    parser.add_argument("--nets-json", default="[]")
    parser.add_argument("--baseline-board")
    parser.add_argument("--preserve-uuids-json", default="[]")
    parser.add_argument("--report")
    args = parser.parse_args(argv)

    if args.phase == "admit":
        if not args.baseline_board:
            parser.error("admit requires --baseline-board")
        import cec_score
        import cec_synth_pipeline
        value = cec_synth_pipeline._admit_priority_power_candidate(
            args.board,
            json.loads(args.nets_json),
            cec_score.score(args.baseline_board),
        )
    elif args.phase == "prune-current":
        import pcbnew
        import cec_current_topology
        board = pcbnew.LoadBoard(args.board)
        value = cec_current_topology.prune_undersized_current_tracks(
            board, json.loads(args.nets_json), board_hint=args.board,
            preserve_uuids=json.loads(args.preserve_uuids_json))
        pcbnew.SaveBoard(args.board, board)
    elif args.phase == "via":
        import cec_fr
        value = cec_fr.prune_dead_zone_via_pairs(
            args.board, json.loads(args.nets_json))
    elif args.phase == "floating":
        import cec_slab_pour
        value = {"removed": int(
            cec_slab_pour.cleanup_floating_zones(args.board) or 0)}
    else:
        import cec_slab_pour
        value = {"removed": int(
            cec_slab_pour.reap_nowhere_zones(args.board) or 0)}
    if args.report:
        with open(args.report, "w", encoding="utf-8") as sink:
            json.dump(value, sink, indent=1, sort_keys=True, default=str)
    print(json.dumps(value, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
