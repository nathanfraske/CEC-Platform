#!/usr/bin/env python3
"""Read-only cross-board replay of the shared physical rail contract.

Compares library-based proposed placement against the immutable board's actual
pads and escape envelope. Library drift is reported, never repaired implicitly.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace


def replay(board_path, *, board_hint):
    import pcbnew
    import cec_force_rails as force
    import cec_rail_geometry as geometry
    path = Path(board_path).resolve()
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    board = pcbnew.LoadBoard(str(path))
    if board is None:
        raise ValueError("cannot read board %s" % path)
    pads, courtyards, roles = geometry.board_facts(board)
    topology = geometry.discover_topology(pads, roles=roles)
    resolver = lambda nets: force.rail_current_contract(nets, board_hint=board_hint)
    live = geometry.compile_rails(topology, pads, courtyards, resolver)
    nets, comps, poses, back = {}, {}, {}, set()
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        comps[ref] = str(fp.GetFPID().GetLibItemName())
        nickname = str(fp.GetFPID().GetLibNickname())
        if nickname:
            comps[ref] = nickname + ":" + comps[ref]
        at = fp.GetPosition()
        angle = fp.GetOrientationDegrees()
        if fp.IsFlipped():
            back.add(ref)
            angle = -angle  # inverse of materializer's native flip convention
        poses[ref] = (at.x / 1e6, at.y / 1e6, angle)
    for row in pads:
        if row["net"]:
            nets.setdefault(row["net"], set()).add((row["ref"], row["number"]))
    proposed_pads, proposed_cy = geometry.placement_facts(
        SimpleNamespace(nets=nets), comps, poses.get, topology, back_refs=back)
    proposed = geometry.compile_rails(topology, proposed_pads, proposed_cy, resolver)
    rows = []
    for actual, expected in zip(live, proposed):
        def contacts(rail):
            return sorted((tuple(p) for p in rail["j3"]), key=str), sorted(
                (tuple(p) for p in rail["tb"]), key=str)
        def rounded(value):
            if isinstance(value, float):
                return round(value, 5)
            if isinstance(value, (list, tuple)):
                return [rounded(v) for v in value]
            return value
        terms = {
            "same_contacts": rounded(contacts(actual)) == rounded(contacts(expected)),
            "same_series_pads": rounded((actual["hi"], actual["lo"])) ==
                rounded((expected["hi"], expected["lo"])),
            "same_face": actual["face"] == expected["face"],
            "same_current": actual["amps"] == expected["amps"],
            "same_escape_envelope": abs(actual["tb_escape_y"] - expected["tb_escape_y"]) < 0.001,
        }
        rows.append({"series": actual["rs"], "terms": terms,
                     "source_contacts": len(actual["j3"]),
                     "sink_contacts": len(actual["tb"]),
                     "current": actual["current_authority"],
                     "escape_delta_mm": round(expected["tb_escape_y"] - actual["tb_escape_y"], 6)})
    unchanged = before == hashlib.sha256(path.read_bytes()).hexdigest()
    return {"schema": 1, "board": str(path), "sha256": before,
            "unchanged": unchanged, "rail_count": len(rows), "rails": rows,
            "ok": bool(rows) and unchanged and all(all(r["terms"].values()) for r in rows)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--board", required=True)
    parser.add_argument("--board-hint", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = replay(args.board, board_hint=args.board_hint)
    Path(args.out).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
