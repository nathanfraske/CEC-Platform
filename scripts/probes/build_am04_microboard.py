#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# AM-04 Ruling 8: build the hand-derivable MICRO-BOARD composition anchor.
# One high-current net "HC" at 10 A: pad -> 20 mm of 5 mm F.Cu -> via pair ->
# 20 mm of 5 mm B.Cu -> pad, with one 2-pad 1 mOhm shunt in line. Geometry
# chosen so every electrothermal_solve term is hand-computable; the committed
# derivation (DERIVATION.md) documents the CURRENT model value AND the
# corrected min-cut value, making this fixture the PR-two debt-fix witness.
# Run IN the kicad container (pcbnew). One-shot: refuses to overwrite.
import os
import sys

import pcbnew

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "tests", "golden", "fixtures", "am04-microboard",
                   "microboard.kicad_pcb")


def main():
    if os.path.exists(OUT) and "--force" not in sys.argv:
        print("exists (one-shot):", OUT)
        return 0
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    board = pcbnew.BOARD()
    nets = {}
    for name in ("HC", "GND"):
        n = pcbnew.NETINFO_ITEM(board, name)
        board.Add(n)
        nets[name] = n

    def mm(v):
        return pcbnew.FromMM(v)

    def footprint(ref, at_xy, pads):
        fp = pcbnew.FOOTPRINT(board)
        fp.SetReference(ref)
        fp.SetPosition(pcbnew.VECTOR2I(mm(at_xy[0]), mm(at_xy[1])))
        for num, (dx, dy, net) in pads.items():
            p = pcbnew.PAD(fp)
            p.SetNumber(num)
            p.SetShape(pcbnew.PAD_SHAPE_RECT)
            p.SetSize(pcbnew.VECTOR2I(mm(2.0), mm(2.0)))
            p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            ls = pcbnew.LSET()                          # KiCad-10: build via AddLayer
            ls.AddLayer(pcbnew.F_Cu)
            p.SetLayerSet(ls)
            p.SetPosition(pcbnew.VECTOR2I(mm(at_xy[0] + dx), mm(at_xy[1] + dy)))
            p.SetNet(nets[net])
            fp.Add(p)
        board.Add(fp)
        return fp

    # J1 (in) at x=5; RS1 shunt pads at x=22/26 (the in-line break); J2 (out)
    # pad sits past the via pair. All on y=10.
    footprint("J1", (5, 10), {"1": (0, 0, "HC")})
    footprint("RS1", (24, 10), {"1": (-2, 0, "HC"), "2": (2, 0, "HC")})
    footprint("J2", (45, 10), {"1": (0, 0, "HC")})

    def track(x1, x2, layer, width=5.0):
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(pcbnew.VECTOR2I(mm(x1), mm(10)))
        t.SetEnd(pcbnew.VECTOR2I(mm(x2), mm(10)))
        t.SetLayer(layer)
        t.SetWidth(mm(width))
        t.SetNet(nets["HC"])
        board.Add(t)

    # F.Cu: J1 -> RS1.1 (17 mm), RS1.2 -> via pair (9 mm)
    track(5, 22, pcbnew.F_Cu)
    track(26, 35, pcbnew.F_Cu)
    # via pair at x=35 (two vias sharing the layer change)
    for dy in (-1.0, 1.0):
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(pcbnew.VECTOR2I(mm(35), mm(10 + dy)))
        v.SetDrill(mm(0.3))
        v.SetWidth(mm(0.6))
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        v.SetNet(nets["HC"])
        board.Add(v)
    # B.Cu: via pair -> J2 (10 mm)
    track(35, 45, pcbnew.B_Cu)

    # board outline 50x20
    for (a, b) in (((0, 0), (50, 0)), ((50, 0), (50, 20)),
                   ((50, 20), (0, 20)), ((0, 20), (0, 0))):
        seg = pcbnew.PCB_SHAPE(board)
        seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
        seg.SetStart(pcbnew.VECTOR2I(mm(a[0]), mm(a[1])))
        seg.SetEnd(pcbnew.VECTOR2I(mm(b[0]), mm(b[1])))
        seg.SetLayer(pcbnew.Edge_Cuts)
        board.Add(seg)

    pcbnew.SaveBoard(OUT, board)
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
