#!/usr/bin/env python3
"""Short-lived exact completer for nets stranded by route sanitation.

The global autorouter is allowed to propose copper, but KiCad DRC remains the
acceptance authority.  Removing an illegal proposal primitive can expose a
previously hidden open endpoint.  This worker gives only those newly stranded
nets a bounded, collision-aware completion attempt in a fresh pcbnew process.
The coordinator performs the whole-board transactional admission afterward.
"""

import argparse
import json
import os

import pcbnew

import cec_fr


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("board")
    parser.add_argument("--nets-json", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--max-mm", type=float, default=80.0)
    parser.add_argument("--maze-max-mm", type=float, default=25.0)
    parser.add_argument("--maze-margin-mm", type=float, default=8.0)
    parser.add_argument("--attempts", type=int, default=12)
    args = parser.parse_args()

    board_path = os.path.abspath(args.board)
    nets = sorted({str(net) for net in json.loads(args.nets_json) if net})
    board = pcbnew.LoadBoard(board_path)
    before = {item.m_Uuid.AsString() for item in board.GetTracks()}
    board.BuildConnectivity()
    report = cec_fr.synthesize_lastmile(
        board,
        max_mm=float(args.max_mm),
        min_w=0.2,
        clearance=0.2,
        cap=max(8, 8 * len(nets)),
        netclass_resolver=cec_fr._project_netclass_resolver(board_path),
        include_nets=set(nets),
        attempts_per_pair=max(1, int(args.attempts)),
        maze_max_mm=float(args.maze_max_mm),
        maze_margin_mm=float(args.maze_margin_mm),
    )
    if report.get("closed"):
        geometry = cec_fr.normalize_netclass_geometry(board, board_path)
        for zone in board.Zones():
            zone.UnFill()
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        board.BuildConnectivity()
        pcbnew.SaveBoard(board_path, board)
    else:
        geometry = {"tracks": 0, "vias": 0}
    generated = []
    for item in board.GetTracks():
        uuid = item.m_Uuid.AsString()
        if uuid not in before:
            generated.append({
                "uuid": uuid,
                "net": item.GetNetname(),
                "class": item.GetClass(),
            })
    payload = {
        "schema": 1,
        "nets": nets,
        "completion": report,
        "generated": generated,
        "generated_count": len(generated),
        "netclass_geometry": geometry,
    }
    with open(args.report, "w", encoding="utf-8") as sink:
        json.dump(payload, sink, indent=2, sort_keys=True, default=str)


if __name__ == "__main__":
    main()
