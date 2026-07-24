#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# SLAB POURS -- subtractive power copper (owner concept + ratification 2026-07-24;
# design of record: docs/slab-pour-design-2026-07-24.md).
#
# The constructive approach derived small rects and kept missing (the 0.4mm
# rect-miss at RS1's via rows, dead mirrors, 8-13% lace fills). This module
# inverts it: seed each rail net's pour as a GIANT SLAB (the whole board
# interior), then SHAVE it on a raster -- contested space (foreign copper +
# clearance), fragments not touching any own-net anchor (the owner's floating-
# zone rule, structural here), and slivers below the width floor -- and hand the
# converged footprint to the real ZONE_FILLER for fine detail (exterior-only
# outlines are safe: the filler re-subtracts foreign clearances itself).
#
# MIN-WIDTH INVARIANT (the owner's "no cross-section below the minimum"): erode
# the shaved mask by half the required width; if the net's anchor groups remain
# connected in the eroded mask, every cut along that path is provably >= the
# required width (erosion-connectivity duality). Reported per net; the LOCKED
# guaranteed-core rung (laid at materialize, never shaved) is stage 2.
#
# Fill speed is architectural: the loop runs on numpy/scipy morphology
# (microseconds), the real filler runs ONCE on the final outlines.
import os
import sys

import numpy as np

try:
    import pcbnew
except ImportError:                                    # host-side import for tests
    pcbnew = None

MM = 1e6


def _nm(mm):
    return int(round(mm * MM))


class Grid:
    def __init__(self, board, cell_mm=0.8, edge_margin_mm=0.55):
        bb = board.GetBoardEdgesBoundingBox()
        self.x0 = bb.GetLeft() / MM + edge_margin_mm
        self.y0 = bb.GetTop() / MM + edge_margin_mm
        self.x1 = bb.GetRight() / MM - edge_margin_mm
        self.y1 = bb.GetBottom() / MM - edge_margin_mm
        self.cell = cell_mm
        self.nx = max(1, int((self.x1 - self.x0) / cell_mm))
        self.ny = max(1, int((self.y1 - self.y0) / cell_mm))

    def ix(self, x_mm):
        return int((x_mm - self.x0) / self.cell)

    def iy(self, y_mm):
        return int((y_mm - self.y0) / self.cell)

    def stamp_box(self, mask, x0, y0, x1, y1, val=True):
        i0, i1 = max(0, self.ix(x0)), min(self.nx - 1, self.ix(x1))
        j0, j1 = max(0, self.iy(y0)), min(self.ny - 1, self.iy(y1))
        if i1 >= i0 and j1 >= j0:
            mask[j0:j1 + 1, i0:i1 + 1] = val


def rasterize(board, nc, lay_id, grid, clearance_mm=0.3):
    """(foreign, anchors) boolean masks for one (net, layer)."""
    foreign = np.zeros((grid.ny, grid.nx), bool)
    anchors = np.zeros((grid.ny, grid.nx), bool)
    c = clearance_mm
    for fp in board.GetFootprints():
        for p in fp.Pads():
            on_layer = lay_id in p.GetLayerSet().CuStack()
            if not on_layer:
                continue
            bb = p.GetBoundingBox()
            x0, y0 = bb.GetLeft() / MM, bb.GetTop() / MM
            x1, y1 = bb.GetRight() / MM, bb.GetBottom() / MM
            if p.GetNetCode() == nc:
                grid.stamp_box(anchors, x0, y0, x1, y1)
            else:
                grid.stamp_box(foreign, x0 - c, y0 - c, x1 + c, y1 + c)
    for t in board.GetTracks():
        is_via = t.GetClass() == "PCB_VIA"
        if is_via:
            if lay_id not in t.GetLayerSet().CuStack():
                continue
            r = t.GetWidth(t.TopLayer()) / MM / 2.0
            q = t.GetPosition()
            x0, y0 = q.x / MM - r, q.y / MM - r
            x1, y1 = q.x / MM + r, q.y / MM + r
            if t.GetNetCode() == nc:
                grid.stamp_box(anchors, x0, y0, x1, y1)
            else:
                grid.stamp_box(foreign, x0 - c, y0 - c, x1 + c, y1 + c)
            continue
        if t.GetLayer() != lay_id:
            continue
        w = t.GetWidth() / MM / 2.0
        s, e = t.GetStart(), t.GetEnd()
        # stamp the segment as steps of cell-sized boxes (0.8mm fidelity)
        L = max(abs(e.x - s.x), abs(e.y - s.y)) / MM
        n = max(1, int(L / (grid.cell * 0.5)))
        own = t.GetNetCode() == nc
        for k in range(n + 1):
            f = k / n
            px = (s.x + f * (e.x - s.x)) / MM
            py = (s.y + f * (e.y - s.y)) / MM
            if own:
                grid.stamp_box(anchors, px - w, py - w, px + w, py + w)
            else:
                grid.stamp_box(foreign, px - w - c, py - w - c,
                               px + w + c, py + w + c)
    return foreign, anchors


def shave(foreign, anchors, grid, min_w_mm=1.2):
    """The subtractive loop on one (net, layer) mask. Returns (mask, report).
    mask = the slab footprint: interior minus contested space, minus fragments
    touching NO anchor (the floating-zone rule, structural), minus slivers
    below the width floor -- with a loud fallback if sliver-removal would
    disconnect everything. report carries the min-width invariant verdict."""
    from scipy import ndimage
    free = ~foreign
    lab, n = ndimage.label(free)
    keep = np.zeros_like(free)
    anchor_labels = set(np.unique(lab[anchors & (lab > 0)]))
    for al in anchor_labels:
        keep |= (lab == al)
    # sliver removal: opening by the width floor
    r_cells = max(1, int(round(min_w_mm / 2.0 / grid.cell)))
    st = ndimage.generate_binary_structure(2, 1)
    opened = ndimage.binary_opening(keep, structure=st, iterations=r_cells)
    lab2, _ = ndimage.label(opened)
    keep2 = np.zeros_like(opened)
    for al in set(np.unique(lab2[anchors & (lab2 > 0)])):
        keep2 |= (lab2 == al)
    if not keep2.any():
        keep2 = keep                                   # loud fallback: no sliver cut
        fallback = True
    else:
        fallback = False
    # DEAD-END APPENDAGE PRUNE (owner addendum 2026-07-24, render evidence:
    # fingers hanging off the pour body reaching nothing). body = opening at
    # the body scale; each appendage component (mask minus body) is PRUNED iff
    # it contains NO anchor (a finger reaching a pad/via is a tap -- stays)
    # AND touches at most ONE body region (a narrow corridor bridging two
    # body lobes is a pathway -- stays; pruning can then never disconnect).
    pruned = 0
    rb = max(1, int(round(min_w_mm * 2.5 / 2.0 / grid.cell)))
    body = ndimage.binary_opening(keep2, structure=st, iterations=rb)
    if body.any():
        blab, _nb = ndimage.label(body)
        alab, na = ndimage.label(keep2 & ~body)
        pruned = 0
        for k in range(1, na + 1):
            m = alab == k
            if (m & anchors).any():
                continue                               # goes somewhere: a tap
            touched = set(np.unique(blab[ndimage.binary_dilation(m, st) & body]))
            touched.discard(0)
            if len(touched) <= 1:
                keep2 = keep2 & ~m
                pruned += 1
    # min-width invariant: erode by half the floor; anchor groups still meet?
    eroded = ndimage.binary_erosion(keep2, structure=st, iterations=r_cells)
    lab3, _ = ndimage.label(eroded | anchors)          # anchors themselves count
    agroups = set(np.unique(lab3[anchors & (lab3 > 0)]))
    invariant_ok = len(agroups) <= 1
    return keep2, {"cells": int(keep2.sum()), "fallback": fallback,
                   "min_width_ok": bool(invariant_ok),
                   "anchor_groups_after_erosion": len(agroups),
                   "appendages_pruned": pruned}


def mask_to_polys(mask, grid, min_area_mm2=6.0):
    """Rectilinear exterior outlines from the mask via shapely union of cell
    runs. Exterior-only is safe: the real filler re-subtracts fine detail."""
    from shapely.geometry import box
    from shapely.ops import unary_union
    rects = []
    for j in range(grid.ny):
        i = 0
        while i < grid.nx:
            if mask[j, i]:
                k = i
                while k < grid.nx and mask[j, k]:
                    k += 1
                rects.append(box(grid.x0 + i * grid.cell, grid.y0 + j * grid.cell,
                                 grid.x0 + k * grid.cell,
                                 grid.y0 + (j + 1) * grid.cell))
                i = k
            else:
                i += 1
    if not rects:
        return []
    u = unary_union(rects)
    geoms = getattr(u, "geoms", [u])
    out = []
    for g in geoms:
        if g.area < min_area_mm2:
            continue
        out.append([(round(x, 3), round(y, 3)) for x, y in g.exterior.coords])
    return out


def synthesize_slab_pours(board, asks, *, cell_mm=0.8, clearance_mm=0.3,
                          min_w_mm=1.2):
    """asks: pour dicts ({net, layer, ...}) naming the slab (net, layer) pairs
    -- the ask CHANNEL is kept; the rect geometry is replaced by the slab.
    Returns (pour_dicts, per-net report)."""
    grid = Grid(board, cell_mm)
    nets_nc = {n.GetNetname(): c
               for c, n in board.GetNetInfo().NetsByNetcode().items()}
    seen = set()
    out, rep = [], {}
    for a in asks:
        net = a.get("net")
        for lay in (a.get("layers") or (a.get("layer", "F.Cu"),)):
            key = (net, lay)
            if key in seen or net not in nets_nc:
                continue
            seen.add(key)
            lay_id = board.GetLayerID(lay)
            foreign, anchors = rasterize(board, nets_nc[net], lay_id, grid,
                                         clearance_mm)
            if not anchors.any():
                rep[key] = {"skipped": "no own-net anchors on layer"}
                continue
            mask, r = shave(foreign, anchors, grid, min_w_mm)
            rep[key] = r
            for poly in mask_to_polys(mask, grid):
                out.append({"net": net, "layer": lay, "polygon": poly,
                            "priority": int(a.get("priority", 2)),
                            "provenance": "slab"})
    return out, rep


def cleanup_floating_zones(board_path):
    """FLOATING-ZONE CLEANUP (owner requirement 2026-07-24): remove copper
    zones whose connectivity cluster contains NO pad, via, or track -- pure
    floating decoration. Runs as a FRESH load->remove->save cycle (the
    2026-06-09 footgun was zone removal inside a manipulation-heavy process;
    a clean cycle isolates it -- verified by the caller re-loading + DRC)."""
    if pcbnew is None:
        return 0
    board = pcbnew.LoadBoard(board_path)
    conn = board.GetConnectivity()
    doomed = []
    for z in board.Zones():
        if z.GetIsRuleArea() or not z.GetNetname():
            continue
        try:
            items = list(conn.GetConnectedItems(z))
        except Exception:                              # noqa: BLE001
            continue
        if not any(it.GetClass() in ("PAD", "PCB_VIA", "PCB_TRACK")
                   for it in items):
            doomed.append(z)
    for z in doomed:
        board.Remove(z)
    if doomed:
        pcbnew.SaveBoard(board_path, board)
        print(f"[cec_slab_pour] zone cleanup: removed {len(doomed)} floating "
              "zone(s)", file=sys.stderr)
    return len(doomed)


if __name__ == "__main__":
    import argparse
    import json
    ap = argparse.ArgumentParser()
    ap.add_argument("board")
    ap.add_argument("--nets", default="")
    ap.add_argument("--layers", default="F.Cu,In2.Cu,B.Cu")
    ap.add_argument("--cleanup", action="store_true")
    a = ap.parse_args()
    if a.cleanup:
        print(cleanup_floating_zones(a.board))
        sys.exit(0)
    b = pcbnew.LoadBoard(a.board)
    asks = [{"net": n, "layers": tuple(a.layers.split(","))}
            for n in a.nets.split(",") if n]
    pours, rep = synthesize_slab_pours(b, asks)
    print(json.dumps({"pours": len(pours),
                      "report": {f"{k[0]}|{k[1]}": v for k, v in rep.items()}},
                     indent=1, default=str))
