#!/usr/bin/env python3
"""Short-lived pcbnew worker for exact dangling-copper removal.

KiCad's legacy SWIG bindings can retain invalid board/connectivity objects
after a Remove/Save/reload cycle.  The route coordinator therefore computes
and admits the mutation, while this worker owns exactly one destructive board
edit and exits before the next independent score.
"""

import argparse
import json
import os

import pcbnew


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("board")
    parser.add_argument("--targets-json", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--refill-zones", action="store_true")
    args = parser.parse_args()

    targets = {
        str(row.get("uuid")): str(row.get("kind") or "")
        for row in json.loads(args.targets_json)
        if row.get("uuid")
    }
    board = pcbnew.LoadBoard(os.path.abspath(args.board))
    by_uuid = {
        item.m_Uuid.AsString(): item
        for item in board.GetTracks()
    }
    removed = []
    missing = []
    for uuid, kind in sorted(targets.items()):
        item = by_uuid.get(uuid)
        if item is None:
            missing.append({"uuid": uuid, "kind": kind})
            continue
        removed.append({
            "uuid": uuid,
            "kind": kind,
            "net": item.GetNetname(),
            "class": item.GetClass(),
            "was_locked": bool(item.IsLocked()),
        })
        board.Remove(item)
    if removed and args.refill_zones:
        for zone in board.Zones():
            zone.UnFill()
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    if removed:
        pcbnew.SaveBoard(os.path.abspath(args.board), board)
    payload = {
        "schema": 1,
        "removed": removed,
        "removed_count": len(removed),
        "missing": missing,
        "zones_refilled": bool(removed and args.refill_zones),
    }
    with open(args.report, "w", encoding="utf-8") as sink:
        json.dump(payload, sink, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
