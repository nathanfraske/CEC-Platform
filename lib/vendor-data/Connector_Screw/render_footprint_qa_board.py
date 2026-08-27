#!/usr/bin/env python3
"""Build a temporary KiCad board containing both main-board terminals.

Run this script with KiCad's system Python, place the output inside any current
main-board project directory so `${KIPRJMOD}/../../lib` resolves, and render it
with `kicad-cli pcb render`.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pcbnew


FOOTPRINTS = (
    ("XFCN_T34069_THT_M3_40A", 12.0, 12.0),
    ("XFCN_TTR32100127-0600_THT_M3_60A", 32.0, 12.0),
)


def mm(value: float) -> int:
    return pcbnew.FromMM(value)


def add_edge(board: pcbnew.BOARD, start: tuple[float, float], end: tuple[float, float]) -> None:
    edge = pcbnew.PCB_SHAPE(board)
    edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
    edge.SetLayer(pcbnew.Edge_Cuts)
    edge.SetStart(pcbnew.VECTOR2I(mm(start[0]), mm(start[1])))
    edge.SetEnd(pcbnew.VECTOR2I(mm(end[0]), mm(end[1])))
    edge.SetWidth(mm(0.1))
    board.Add(edge)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[3]
    library = repo_root / "lib" / "vendor" / "Connector_Screw.pretty"
    board = pcbnew.BOARD()

    for name, x, y in FOOTPRINTS:
        footprint = pcbnew.FootprintLoad(str(library), name)
        if footprint is None:
            raise RuntimeError(f"failed to load {name} from {library}")
        footprint.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
        board.Add(footprint)

    for start, end in (
        ((2.0, 2.0), (42.0, 2.0)),
        ((42.0, 2.0), (42.0, 22.0)),
        ((42.0, 22.0), (2.0, 22.0)),
        ((2.0, 22.0), (2.0, 2.0)),
    ):
        add_edge(board, start, end)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    pcbnew.SaveBoard(str(args.output), board)
    print(args.output)


if __name__ == "__main__":
    main()
