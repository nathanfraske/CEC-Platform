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
import heapq
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


def mask_to_polys(mask, grid, min_area_mm2=6.0, smooth=True):
    """Rectilinear exterior outlines from the mask via shapely union of cell
    runs. Exterior-only is safe: the real filler re-subtracts fine detail.

    *smooth* (owner 2026-07-24 "weirdly blocky"): the raster mask
    OVER-carves -- rasterize() excludes any cell a foreign item merely
    touches -- so raw outlines staircase at cell size and thin clearance
    shadows read as random bites. The ZONE_FILLER is the precision
    authority (it re-subtracts TRUE clearances from whatever outline it is
    given at fill time), so closing small voids and simplifying steps in
    the OUTLINE is safe by construction: realized copper only moves toward
    filler truth, never into a violation, and mask-proven connectivity /
    min-width can only gain copper, never lose it."""
    from shapely.geometry import box
    from shapely.ops import unary_union
    from scipy import ndimage
    m = mask
    if smooth:
        _st2 = ndimage.generate_binary_structure(2, 1)
        m = ndimage.binary_closing(mask, structure=_st2, iterations=2)
    rects = []
    for j in range(grid.ny):
        i = 0
        while i < grid.nx:
            if m[j, i]:
                k = i
                while k < grid.nx and m[j, k]:
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
    if smooth:
        u = u.simplify(min(0.5, grid.cell * 0.7), preserve_topology=True)
    geoms = getattr(u, "geoms", [u])
    out = []
    for g in geoms:
        if g.area < min_area_mm2:
            continue
        out.append([(round(x, 3), round(y, 3)) for x, y in g.exterior.coords])
    return out


def shunt_neighborhoods(board, margin_mm=4.5):
    """Boxes (x0,y0,x1,y1 mm) around every RS* shunt's pads + margin -- sized to
    cover the outboard force-via rows (owner rule 2026-07-24: top pours exist
    ONLY around the shunts, and they must COVER their via arrays)."""
    out = []
    for fp in board.GetFootprints():
        if not fp.GetReference().startswith("RS"):
            continue
        x0 = y0 = 1e18
        x1 = y1 = -1e18
        for p in fp.Pads():
            bb = p.GetBoundingBox()
            x0 = min(x0, bb.GetLeft() / MM)
            y0 = min(y0, bb.GetTop() / MM)
            x1 = max(x1, bb.GetRight() / MM)
            y1 = max(y1, bb.GetBottom() / MM)
        if x1 > x0:
            out.append((x0 - margin_mm, y0 - margin_mm,
                        x1 + margin_mm, y1 + margin_mm))
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
            # TOP = SHUNT-ONLY (owner categorical rule 2026-07-24: "remove top
            # pours unless they are around the shunts" -- F.Cu is the signal
            # fabric; the shunt neighborhoods are the one place top copper is
            # structural, and the boxes cover the force-via arrays so barrels
            # never sit outside the pour).
            if lay == "F.Cu":
                nb = shunt_neighborhoods(board)
                if not nb:
                    rep[key] = {"skipped": "F.Cu shunt-only: no shunts"}
                    continue
                allow = np.zeros_like(foreign)
                for (bx0, by0, bx1, by1) in nb:
                    grid.stamp_box(allow, bx0, by0, bx1, by1)
                foreign = foreign | ~allow
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


# ---------------------------------------------------------------------------
# v2 -- OVER-UNDER POURS (owner ratification 2026-07-24 late; design of
# record: docs/slab-pour-design-2026-07-24.md, "v2" section). "the pour is a
# routed object": per rail, ONE continuous path from source terminals to sink
# terminals, existing on exactly ONE layer per segment -- a preferred layer
# until contested space blocks it, then a via-array BRIDGE to another layer,
# carrying on; the vacated layer carries NO copper there (removed by
# construction, never by rule). The min-width requirement is the SEARCH
# CONSTRAINT, not a post-hoc check: every layer's free-space mask is eroded
# by half that net's IPC-required width before the pathfind runs, so any
# path the search finds is provably wide enough (erosion-connectivity
# duality, the same trick `shave()`'s min-width invariant uses above).
#
# A/B'd behind CEC_OVERUNDER=1 in cec_fr.import_ses against the shave-slab
# path (synthesize_slab_pours, above) -- never default-on.
# ---------------------------------------------------------------------------
def req_width_mm(amps, layer):
    """Required copper width (mm) for *amps* at a 30C rise, layer-oz-aware.

    Ported VERBATIM from cec_fr.synthesize_pour_bonds's nested
    `_req_width_mm` closure (IPC-2221 trace-width inverse; k=0.048 ext /
    0.024 int, 2oz outer / 1oz inner is this platform's LOCKED stackup --
    see CLAUDE.md's board-class stackup doctrine). *amps* is the RAW net
    current -- the 1.25x margin is applied INSIDE this formula, matching
    the source exactly; do not apply it again at the call site. Replicated
    rather than imported: the source is a closure nested inside
    synthesize_pour_bonds, not a module-level name (datasheet/provenance
    rule, docs/agent-working-principles.md item 11: this constant already
    has a traced source -- the validated cec_fr implementation -- so it is
    copied, not re-derived)."""
    if amps <= 0:
        return 0.0
    outer = layer in ("F.Cu", "B.Cu")
    k = 0.048 if outer else 0.024                  # IPC-2221 ext/int
    oz = 2.0 if outer else 1.0                     # platform stackup
    a_mil2 = (1.25 * amps / (k * 30.0 ** 0.44)) ** (1.0 / 0.725)
    return a_mil2 / (1.378 * oz) * 0.0254


def terminal_clusters(board, nc, grid):
    """Step 1 (owner v2 design): the net's own pads/vias, clustered
    spatially via scipy.ndimage.label on the union anchor raster.

    THT pads/vias anchor every copper layer; SMD anchor only their own
    side. No separate THT/SMD branch is needed here: a plain union of every
    footprint pad + via of this net over the WHOLE board (ignoring layer)
    already gives exactly that shape once combined with the per-layer
    `rasterize()` anchors used downstream (a THT pad's bounding box is
    stamped once, and every per-layer anchor mask independently rediscovers
    it via `CuStack()` containment; an SMD pad likewise appears in this
    union AND in exactly one per-layer anchor mask).

    Returns (clab, nclusters): clab is a (grid.ny, grid.nx) int label array
    (0 = no terminal there); cluster ids are 1..nclusters."""
    from scipy import ndimage
    mask = np.zeros((grid.ny, grid.nx), bool)
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetCode() != nc:
                continue
            bb = p.GetBoundingBox()
            grid.stamp_box(mask, bb.GetLeft() / MM, bb.GetTop() / MM,
                           bb.GetRight() / MM, bb.GetBottom() / MM)
    for t in board.GetTracks():
        if t.GetClass() != "PCB_VIA" or t.GetNetCode() != nc:
            continue
        r = t.GetWidth(t.TopLayer()) / MM / 2.0
        q = t.GetPosition()
        grid.stamp_box(mask, q.x / MM - r, q.y / MM - r,
                       q.x / MM + r, q.y / MM + r)
    clab, n = ndimage.label(mask)
    return clab, n


def route_overunder(layers, passable, anchors, clab, nclusters, *,
                    bias_fn, bridge_cost=8.0, turn_cost=1.75):
    """PURE-RASTER core of the over-under pathfinder (owner v2 design, step
    3): grow ONE multi-layer Steiner-ish tree connecting every terminal
    cluster 1..nclusters recorded in *clab* (a (ny,nx) int label array, 0 =
    no terminal).

    *layers* is an ordered list of layer-name keys into *passable* and
    *anchors* (each a {layer: (ny,nx) bool ndarray} dict): *passable[lay]*
    is the eroded-free mask UNIONED with *anchors[lay]* (own-net copper
    always counts as walkable, matching the `shave()` min-width-invariant
    pattern above -- a real pad needs no erosion margin, only the NEW
    copper connecting it does); *anchors[lay]* is real per-net copper on
    that layer. *bias_fn(lay, row, col) -> float* is the cost charged to
    ENTER that cell on that layer (>=1.0 is the unbiased floor -- 1.0 =
    'step cost 1' in the design doc). *bridge_cost* is the flat same-cell
    layer-change cost, legal only where BOTH layers are *passable* there
    (a via can only land in copper the search already proved wide enough
    on both sides).

    Grows the tree with a Prim-style nearest-terminal expansion: each round
    is ONE multi-source Dijkstra seeded at zero cost from every cell
    already in the tree, so previously-found path cells are reused for
    free -- the owner's 'reusing already-found path cells at zero cost' --
    stopping at the first popped node that is an anchor cell of an
    unconnected cluster. Dijkstra's pop order guarantees that is the
    globally NEAREST unconnected terminal from the current tree, the
    standard shortest-paths approximation to a Steiner tree.

    Returns (path_cells, bridges, ok, bottleneck):
      path_cells: {layer: (ny,nx) bool} -- cells the realized tree touches
                  on that layer. {} on failure (NEVER a partial guess).
      bridges:    [(row, col, from_layer, to_layer, dir_dx, dir_dy)] --
                  dir_dx/dir_dy is a unit vector estimating the path's
                  local travel direction AT the transition (nearest
                  spatially-distinct chain cells before/after it), used to
                  lay the bridge's via LINE perpendicular to travel.
      ok:         False iff some terminal cluster could never be reached
                  (an already-searched-empty cluster, or a hop that
                  exhausts the graph) -- the honest 'no path exists' case.
      bottleneck: None when ok; else a dict naming the stranded cluster
                  (id + representative row/col) and why.
    """
    ny, nx = clab.shape
    lidx = {lay: i for i, lay in enumerate(layers)}
    nlay = len(layers)
    cluster_ids = sorted(int(v) for v in np.unique(clab) if v)
    if len(cluster_ids) <= 1:
        return {}, [], True, None              # nothing to connect

    # reachability pre-check: a cluster with NO anchor cell on any searched
    # layer can never be reached by construction -- fail fast and name it,
    # rather than burn a Dijkstra pass discovering the same thing.
    reachable = set()
    for lay in layers:
        ys, xs = np.where(anchors[lay])
        for y, x in zip(ys.tolist(), xs.tolist()):
            cid = int(clab[y, x])
            if cid:
                reachable.add(cid)
    unreachable = [c for c in cluster_ids if c not in reachable]
    if unreachable:
        cid = unreachable[0]
        ys, xs = np.where(clab == cid)
        return {}, [], False, {
            "cluster": cid, "row": int(round(ys.mean())),
            "col": int(round(xs.mean())),
            "reason": "terminal has no anchor on any searched layer",
        }

    seed = cluster_ids[0]
    remaining = set(cluster_ids[1:])
    tree = set()                                # {(row, col, layer_idx)}
    path_cells = {lay: np.zeros((ny, nx), bool) for lay in layers}
    for lay in layers:
        li = lidx[lay]
        ys, xs = np.where(anchors[lay] & (clab == seed))
        for y, x in zip(ys.tolist(), xs.tolist()):
            tree.add((y, x, li))
            path_cells[lay][y, x] = True

    bridges = []
    INF = float("inf")
    MOVES = ((-1, 0), (1, 0), (0, -1), (0, 1))
    while remaining:
        # DIRECTION-STATE Dijkstra (owner 2026-07-24 "laid very willy-nilly":
        # the direction-blind search wandered wherever cost ties broke, so
        # lanes snaked. State = (layer, row, col, incoming-move); every
        # heading change pays *turn_cost* on top of the cell bias, so lanes
        # run straight like intentional trunks and turn only when the board
        # makes them. dir 4 = seed/no-heading (tree cells; bridges keep the
        # heading across the layer change).
        dist = np.full((nlay, ny, nx, 5), INF)
        parent = {}
        heap = []
        for (r, c, li) in tree:
            dist[li, r, c, 4] = 0.0
            heapq.heappush(heap, (0.0, r, c, li, 4))
        found = None
        while heap:
            d, r, c, li, di = heapq.heappop(heap)
            if d > dist[li, r, c, di]:
                continue                        # stale heap entry
            lay = layers[li]
            cid = int(clab[r, c])
            if cid in remaining and anchors[lay][r, c]:
                found = (r, c, li, di, cid)
                break
            for ndir, (dr, dc) in enumerate(MOVES):
                nr, ncc = r + dr, c + dc
                if not (0 <= nr < ny and 0 <= ncc < nx):
                    continue
                if not passable[lay][nr, ncc]:
                    continue
                nd = d + bias_fn(lay, nr, ncc) + (
                    turn_cost if di not in (ndir, 4) else 0.0)
                if nd < dist[li, nr, ncc, ndir]:
                    dist[li, nr, ncc, ndir] = nd
                    parent[(nr, ncc, li, ndir)] = (r, c, li, di)
                    heapq.heappush(heap, (nd, nr, ncc, li, ndir))
            for oli, olay in enumerate(layers):
                if oli == li or not passable[olay][r, c]:
                    continue                    # bridge needs BOTH sides
                nd = d + bridge_cost
                if nd < dist[oli, r, c, di]:
                    dist[oli, r, c, di] = nd
                    parent[(r, c, oli, di)] = (r, c, li, di)
                    heapq.heappush(heap, (nd, r, c, oli, di))
        if found is None:
            cid = next(iter(remaining))
            ys, xs = np.where(clab == cid)
            return {}, [], False, {
                "cluster": cid, "row": int(round(ys.mean())),
                "col": int(round(xs.mean())),
                "reason": "no route from the connected tree "
                          "(eroded masks disconnect the terminals)",
            }
        r, c, li, di, cid = found
        node = (r, c, li, di)
        chain4 = [node]
        while node in parent and (node[0], node[1], node[2]) not in tree:
            node = parent[node]
            chain4.append(node)
        chain4.reverse()
        # project the direction-states back to cells; consecutive repeats
        # (same cell re-entered under another heading) collapse so the
        # bridge detector below sees each position once per layer visit
        chain = []
        for (pr, pc, pli, _pdi) in chain4:
            if not chain or chain[-1] != (pr, pc, pli):
                chain.append((pr, pc, pli))
        prev_li = None
        for i, (pr, pc, pli) in enumerate(chain):
            lay = layers[pli]
            tree.add((pr, pc, pli))
            path_cells[lay][pr, pc] = True
            if prev_li is not None and prev_li != pli:
                # BRIDGE: same-cell layer change. Estimate local travel
                # direction from the nearest spatially-DISTINCT chain cells
                # either side (a bridge move keeps row/col fixed, so the
                # immediate neighbours in the chain are useless for this).
                before = next((chain[j] for j in range(i - 1, -1, -1)
                              if (chain[j][0], chain[j][1]) != (pr, pc)), None)
                after = next((chain[j] for j in range(i + 1, len(chain))
                             if (chain[j][0], chain[j][1]) != (pr, pc)), None)
                if before is not None and after is not None:
                    dx, dy = after[1] - before[1], after[0] - before[0]
                elif after is not None:
                    dx, dy = after[1] - pc, after[0] - pr
                elif before is not None:
                    dx, dy = pc - before[1], pr - before[0]
                else:
                    dx, dy = 1.0, 0.0
                dn = (dx * dx + dy * dy) ** 0.5 or 1.0
                bridges.append((pr, pc, layers[prev_li], lay,
                               dx / dn, dy / dn))
            prev_li = pli
        remaining.discard(cid)
    return path_cells, bridges, True, None


def apply_bridge_overlap(path_cells, bridges, grid, radius_cells=3):
    """~3-cell-radius overlap on BOTH transitioning layers around each
    bridge point (owner v2 design step 4: 'both layers' dilated disks
    overlapping for ~3 cells'), so after dilation the two lane polygons
    overlap there and the via array sits embedded in copper on both layers
    rather than at a bare edge. Mutates *path_cells* in place."""
    ny, nx = grid.ny, grid.nx
    r2 = radius_cells * radius_cells
    for (r, c, lay_from, lay_to, _dx, _dy) in bridges:
        for dr in range(-radius_cells, radius_cells + 1):
            for dc in range(-radius_cells, radius_cells + 1):
                if dr * dr + dc * dc > r2:
                    continue
                rr, cc = r + dr, c + dc
                if 0 <= rr < ny and 0 <= cc < nx:
                    path_cells[lay_from][rr, cc] = True
                    path_cells[lay_to][rr, cc] = True


def realize_overunder(path_cells, layer_rcells, grid, *, min_area_mm2=0.5):
    """Dilate each layer's accumulated path mask by its OWN half-width (in
    cells) and polygonize -- 'maximal same-layer runs' realized as lane
    polygons. Dilating the union of a layer's runs equals the union of
    dilating each run separately (dilation distributes over union for a
    fixed structuring element), so accumulating per-layer and dilating once
    is the identical result without tracking each run as a separate object.

    *min_area_mm2* is deliberately far below `mask_to_polys`'s 6.0mm2 slab
    default: over-under lanes are purpose-built narrow paths, not maximal
    slabs, and a short bridge patch can legitimately be under 6mm2.

    Returns {layer: [poly, ...]} (only layers that produced >=1 polygon)."""
    from scipy import ndimage
    st = ndimage.generate_binary_structure(2, 1)
    out = {}
    for lay, m in path_cells.items():
        if not m.any():
            continue
        dil = ndimage.binary_dilation(
            m, structure=st, iterations=max(1, layer_rcells.get(lay, 1)))
        polys = mask_to_polys(dil, grid, min_area_mm2=min_area_mm2)
        if polys:
            out[lay] = polys
    return out


def bridges_to_vias(bridges, req_w, grid, *, pitch_mm=1.2, ledger_mm=0.85,
                    existing=()):
    """A via-array LINE across each bridge, perpendicular to the path's
    local travel direction, spaced *pitch_mm* apart and spanning the WIDER
    of the two transitioning layers' required widths ('via positions on the
    transition line at 1.2mm pitch', owner v2 design step 4).

    Skips any spot within *ledger_mm* of an entry in *existing* (mm tuples)
    OR of a spot this call already placed for an earlier bridge (the 0.85mm
    any-net barrel ledger, applied cumulatively). *req_w* maps a layer name
    to its required width in mm (missing entries fall back to the 1.2mm
    floor). Returns [{'x_mm':, 'y_mm':}] -- the caller stamps 'net'."""
    placed = list(existing)
    out = []
    for (r, c, lay_from, lay_to, dx, dy) in bridges:
        half_w = max(req_w.get(lay_from, 1.2), req_w.get(lay_to, 1.2)) / 2.0
        cx = grid.x0 + (c + 0.5) * grid.cell
        cy = grid.y0 + (r + 0.5) * grid.cell
        n_v = max(1, int(round((2.0 * half_w) / pitch_mm)) + 1)
        perp = (-dy, dx)                        # rotate travel dir by 90
        for k in range(n_v):
            off = (k - (n_v - 1) / 2.0) * pitch_mm
            vx = round(cx + perp[0] * off, 3)
            vy = round(cy + perp[1] * off, 3)
            if any((vx - qx) ** 2 + (vy - qy) ** 2 < ledger_mm ** 2
                  for (qx, qy) in placed):
                continue
            placed.append((vx, vy))
            out.append({"x_mm": vx, "y_mm": vy})
    return out


def _prep_overunder_net(board, net, nc, ask_layers, grid, *, net_currents,
                        shunt_mask, clearance_mm=0.3, manifolds=()):
    """Shared per-net SEARCH PREP for the over-under machinery -- extracted
    2026-07-25 (pre-FR corridor reservation, docs/slab-pour-design-2026-07-24.md
    priority ruling) so `synthesize_overunder_pours` (post-route realization)
    and `reserve_pour_corridors` (pre-route reservation) run the IDENTICAL
    terminal-cluster + eroded-mask + bias construction: reserved corridors must
    predict realized lanes, so the two may never drift.

    *ask_layers* is the ask's OWN layer list (before the fixed In2/B union --
    applied here, matching the ask-channel contract documented on
    `synthesize_overunder_pours`). Returns ``(prep, None)`` on success --
    prep = {layers, passable, anchors, foreign, clab, nclusters, rcells,
    reqw, bias_fn} (foreign = the raw rasterize() masks incl. clearance,
    kept for the reservation's corridor-carve) -- or ``(None, reason_str)``
    on the two honest no-search cases ("no valid layer" / "no pads/vias for
    net"), byte-identical to the report reasons the realization always used."""
    from scipy import ndimage
    st = ndimage.generate_binary_structure(2, 1)
    layers = list(dict.fromkeys(list(ask_layers) + ["In2.Cu", "B.Cu"]))
    layers = [lay for lay in layers if board.GetLayerID(lay) >= 0]
    if not layers:
        return None, "no valid layer"

    # step 1: terminal groups
    clab, nclusters = terminal_clusters(board, nc, grid)
    if nclusters == 0:
        return None, "no pads/vias for net"

    # step 2: per-layer eroded/passable masks + required width
    amps = net_currents.get(net, 0.0)
    passable, anchors, rcells, reqw, foreign = {}, {}, {}, {}, {}
    for lay in layers:
        lay_id = board.GetLayerID(lay)
        fmask, anc = rasterize(board, nc, lay_id, grid, clearance_mm)
        w = req_width_mm(amps, lay) if amps > 0 else 1.2
        rc = max(1, int(round(w / (2.0 * grid.cell))))
        eroded = ndimage.binary_erosion(~fmask, structure=st,
                                        iterations=rc)
        # ANCHOR-APPROACH TAPER (2026-07-25, from the skeleton-board
        # pour-first runs: wide lanes could not REACH terminals seated
        # in connector pin fields -- the gaps between foreign THT
        # barrels are narrower than the lane width, so full-width
        # erosion walls the terminal even on an empty board). Within a
        # few cells of the net's OWN anchors, any non-foreign cell is
        # passable: the pad itself is the physical width bottleneck
        # there, and a short pad-adjacent neck is thermally fine (the
        # current spreads at the pad; neck length is what matters).
        approach = ndimage.binary_dilation(anc, structure=st,
                                           iterations=4) & ~fmask
        passable[lay] = eroded | anc | approach
        anchors[lay] = anc
        rcells[lay] = rc
        reqw[lay] = w
        foreign[lay] = fmask

    # ANCHOR-DRIVEN LAYER WIDENING (2026-07-24, the implementation-agent's
    # flag 1 materialized on the first live 24-pin wave: rail-compiler
    # SENSE asks carry In2-only layers, but the shunt/INA SMD terminals
    # live on F.Cu -> route_overunder refused with "terminal has no
    # anchor on any searched layer"). A terminal cluster anchored on NO
    # searched layer but anchored on an outer layer pulls that layer
    # into the search set. F.Cu LEGALITY is unaffected: the realized
    # lane still goes through add_power_pours' shunt-only F choke at lay
    # time -- and a widened net's F anchors are shunt/INA pads, i.e.
    # inside the shunt neighborhoods that choke admits.
    for extra in ("F.Cu", "B.Cu"):
        if extra in passable or board.GetLayerID(extra) < 0:
            continue
        uncov = [k for k in range(1, nclusters + 1)
                 if not any((anchors[lay] & (clab == k)).any()
                            for lay in layers)]
        if not uncov:
            break
        fmask, anc = rasterize(board, nc, board.GetLayerID(extra),
                               grid, clearance_mm)
        helped = [k for k in uncov if (anc & (clab == k)).any()]
        if not helped:
            continue
        w = req_width_mm(amps, extra) if amps > 0 else 1.2
        rc = max(1, int(round(w / (2.0 * grid.cell))))
        layers.append(extra)
        passable[extra] = ndimage.binary_erosion(
            ~fmask, structure=st, iterations=rc) | anc
        anchors[extra] = anc
        rcells[extra] = rc
        reqw[extra] = w
        foreign[extra] = fmask
        print(f"[cec_slab_pour] over-under: widened {net} search to "
              f"{extra} (terminal cluster(s) {helped} anchored only "
              f"there)", file=sys.stderr)
    # v3.1 WIDTH-MARGIN ATTACH (owner algorithm 2026-07-25, docs/slab-pour-
    # design-2026-07-24.md v3.1): connector MANIFOLDS -- one margin-width
    # bus-bar pour per (connector, net) pin group, laid before any spine --
    # become the spine's ATTACH TARGETS. A terminal cluster whose cells
    # intersect a manifold has its anchor mask REPLACED by
    # erode(manifold|anchors, req_w/2) restricted to that manifold component:
    # the lane attaches only where the manifold can actually FEED the width
    # (today's raw-pad targets sit between foreign barrels the eroded search
    # can never reach -- the three s415 skeleton no-paths). Clusters ganged
    # by one manifold component MERGE (the manifold copper is one solid
    # terminal by construction). Erosion emptying a component falls back to
    # the raw anchors, with a note in attach_notes (honest per-net report).
    attach_notes = []
    _man_eff_f = None                      # F manifold footprint: choke-admitted
    if manifolds:
        man_by_lay = {}
        for d in manifolds:
            if d.get("net") != net:
                continue
            _mlay = d.get("layer", "F.Cu")
            if _mlay not in passable:
                continue                       # only searched layers matter
            _mm = man_by_lay.setdefault(
                _mlay, np.zeros((grid.ny, grid.nx), bool))
            _mxs = [q[0] for q in d.get("polygon") or ()]
            _mys = [q[1] for q in d.get("polygon") or ()]
            if _mxs:
                grid.stamp_box(_mm, min(_mxs), min(_mys), max(_mxs), max(_mys))
        for _mlay, _mm in man_by_lay.items():
            eff = _mm & ~foreign[_mlay]
            if not eff.any():
                attach_notes.append(f"{_mlay}: manifold fully foreign-carved"
                                    " -- raw anchors kept")
                continue
            # manifold copper is own-net solid laid FIRST: walkable by
            # construction (the filler carves true clearances at fill time)
            passable[_mlay] = passable[_mlay] | eff
            if _mlay == "F.Cu":
                _man_eff_f = eff if _man_eff_f is None else (_man_eff_f | eff)
            mlab, _nman = ndimage.label(eff)
            att = ndimage.binary_erosion(eff | anchors[_mlay], structure=st,
                                         iterations=rcells[_mlay])
            for _mc in range(1, _nman + 1):
                comp = mlab == _mc
                cids = sorted(int(v) for v in np.unique(clab[comp]) if v)
                if not cids:
                    continue                   # touches no terminal: inert
                keep_id = cids[0]
                for _cid in cids[1:]:          # gang = merge terminals
                    clab[clab == _cid] = keep_id
                tgt = att & comp
                if tgt.any():
                    cl_mask = clab == keep_id
                    anchors[_mlay] = (anchors[_mlay] & ~cl_mask) | tgt
                    clab[tgt & (clab == 0)] = keep_id
                    attach_notes.append(
                        f"{_mlay} cluster {keep_id}: anchors -> "
                        f"{int(tgt.sum())} eroded manifold cell(s)"
                        + (f" (merged {cids})" if len(cids) > 1 else ""))
                else:
                    attach_notes.append(
                        f"{_mlay} cluster {keep_id}: manifold erosion empty "
                        "at req width -- raw anchors kept")
    # F.Cu HARD CONSTRAINT (owner categorical rule 2026-07-24 "top
    # pours only around the shunts" + the s427 sprawl finding: the
    # f_prox SOFT bias let a widened net whose terminals are all
    # F-anchored -- e.g. +5VSB's decoupling caps board-wide -- route
    # its WHOLE lane on F.Cu). F transit cells now exist only inside
    # shunt neighborhoods or hugging the net's own F anchors (short
    # landing patches, ~2.4mm); any longer F run is impossible, so the
    # search bridges to an inner/bottom layer instead. Anchors stay
    # passable by the passable-=eroded|anchors construction above.
    if "F.Cu" in passable:
        _f_allow = (ndimage.binary_dilation(anchors["F.Cu"], structure=st,
                                            iterations=3)
                    | shunt_mask | anchors["F.Cu"])
        if _man_eff_f is not None:
            # a laid F manifold is ADMITTED top copper (the add_power_pours
            # choke admits it by name) -- transit through its own footprint
            # is not signal-fabric sprawl; bounded by the manifold bbox
            _f_allow = _f_allow | _man_eff_f
        passable["F.Cu"] &= _f_allow
    f_prox = None
    if "F.Cu" in anchors:
        f_prox = ndimage.binary_dilation(anchors["F.Cu"], structure=st,
                                         iterations=2)

    def _bias(lay, r, c, _shunt=shunt_mask, _fprox=f_prox):
        # per-layer bias (design step 3): In2 +0, B.Cu +0.15/step,
        # F.Cu +0.6/step EXCEPT free inside a shunt neighborhood or
        # within 2 cells of this net's own F-anchored terminal.
        if lay == "F.Cu":
            if _shunt[r, c] or (_fprox is not None and _fprox[r, c]):
                return 1.0
            return 1.6
        return 1.0 + (0.0 if lay == "In2.Cu" else 0.15)

    return {"layers": layers, "passable": passable, "anchors": anchors,
            "foreign": foreign, "clab": clab, "nclusters": nclusters,
            "rcells": rcells, "reqw": reqw, "bias_fn": _bias,
            "attach_notes": attach_notes}, None


def synthesize_overunder_pours(board, asks, *, cell_mm=0.8, clearance_mm=0.3,
                               manifolds=False, collect=None):
    """v2 OVER-UNDER POURS -- "the pour is a routed object" (owner
    ratification 2026-07-24 late; docs/slab-pour-design-2026-07-24.md, "v2"
    section). Per rail: ONE continuous path from terminal to terminal,
    existing on exactly one layer per segment (preferred layer until
    contested space blocks it, then a via-array bridge to another layer,
    carrying on); the vacated layer carries NO copper there.

    *asks*: pour-ask dicts ({"net": ..., "layers": (...)}) -- the SAME ask
    channel `synthesize_slab_pours` reads; this is an alternate REALIZATION
    of the same asks (A/B'd behind CEC_OVERUNDER=1 in cec_fr.import_ses),
    not a new request format. Layers searched per net = the ask's own
    `layers` (or `layer`, default "F.Cu") UNIONED with {"In2.Cu", "B.Cu"}
    (always considered regardless of what the ask names) -- an ask that
    wants an F.Cu-anchored terminal (e.g. an SMD shunt pad) reachable MUST
    include "F.Cu" in its own `layers`, matching the ask-channel contract
    (this function does not silently widen an ask's own layer list beyond
    that fixed pair).

    Returns (pour_dicts, via_list, report):
      pour_dicts: [{"net", "layer", "polygon", "provenance": "overunder"}]
      via_list:   [{"net", "x_mm", "y_mm"}, ...] bridge vias, ledger-clear
                  against the board's existing vias AND every other via
                  already synthesized in this same call (any-net ledger).
      report:     {net: {"segments", "bridges", "layers_used",
                  "path_found", ...}} -- on path_found=False the entry ALSO
                  carries "bottleneck" (see route_overunder) and nothing is
                  laid for that net (never a partial guess, step 5).

    *manifolds* (v3.1, owner algorithm 2026-07-25 -- default OFF so existing
    import-side callers are byte-identical): stage 0 lays one margin-width
    CONNECTOR MANIFOLD per (connector, net) pin group (connector_manifolds)
    BEFORE any spine -- the manifold dicts lead the returned pour_dicts, and
    the per-net search treats them as own-net anchors under the WIDTH-MARGIN
    ATTACH rule (see _prep_overunder_net). On a no-path net the manifolds are
    still returned (its ONLY copper besides guaranteed patches -- the v3
    set-in-stone rule: never board-wide fallback sprawl).

    *collect* (pour-first seam): pass a dict to receive per-net search
    internals -- collect[net] = {ok, path_cells, bridges, rcells, foreign,
    reqw} and collect["_grid"] = the Grid -- so the caller can derive the
    pre-FR corridor reservation from the SAME solve (one solve, three
    consumers; reservation_from_search consumes exactly these).
    """
    grid = Grid(board, cell_mm)
    nets_nc = {n.GetNetname(): c
               for c, n in board.GetNetInfo().NetsByNetcode().items()}
    if collect is not None:
        collect["_grid"] = grid

    # net currents (the IPC required-width search constraint's input) --
    # same source cec_fr.synthesize_pour_bonds._mirror_needed reads; a net
    # absent from the config (or a board with none) falls back to the
    # 1.2mm practical floor (task-specified default).
    net_currents = {}
    try:
        import cec_thermal_overlay as _ov
        _cfg = _ov.board_thermal_config(os.environ.get("CEC_THERMAL_BOARD_HINT", ""))
        net_currents = dict((_cfg[0] if _cfg else None) or {})
    except Exception:                                  # noqa: BLE001
        net_currents = {}

    # shunt neighborhoods, once (the F.Cu bias input -- design step 3's
    # "free inside shunt neighborhoods")
    shunt_mask = np.zeros((grid.ny, grid.nx), bool)
    for (x0, y0, x1, y1) in shunt_neighborhoods(board):
        grid.stamp_box(shunt_mask, x0, y0, x1, y1)

    # existing board vias, once -- the 0.85mm any-net barrel ledger seed
    existing_vias_mm = []
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA":
            p = t.GetPosition()
            existing_vias_mm.append((p.x / MM, p.y / MM))

    pour_dicts, via_list, report = [], [], {}

    # v3.1 stage 0: connector manifolds -- LAID FIRST (they lead the dict
    # list) and handed to every net's search as attach targets.
    man_by_net = {}
    if manifolds:
        _ask_nets = {a.get("net") for a in asks if a.get("net") in nets_nc}
        for md in connector_manifolds(board, nets=_ask_nets):
            man_by_net.setdefault(md["net"], []).append(md)
        for _mn in sorted(man_by_net):
            pour_dicts.extend(man_by_net[_mn])
        if man_by_net:
            print("[cec_slab_pour] over-under: %d connector manifold(s) for "
                  "%d net(s) laid first (v3.1 stage 0)"
                  % (sum(len(v) for v in man_by_net.values()), len(man_by_net)),
                  file=sys.stderr)

    for a in asks:
        net = a.get("net")
        if net not in nets_nc:
            report[net] = {"path_found": False, "segments": 0, "bridges": 0,
                           "layers_used": [], "reason": "net not on board"}
            continue
        nc = nets_nc[net]
        prep, _why = _prep_overunder_net(
            board, net, nc, list(a.get("layers") or (a.get("layer", "F.Cu"),)),
            grid, net_currents=net_currents, shunt_mask=shunt_mask,
            clearance_mm=clearance_mm, manifolds=man_by_net.get(net, ()))
        if prep is None:
            report[net] = {"path_found": False, "segments": 0, "bridges": 0,
                           "layers_used": [], "reason": _why}
            if collect is not None:
                collect[net] = {"ok": False, "path_cells": {}, "bridges": [],
                                "rcells": {}, "foreign": {}, "reqw": {}}
            continue
        rcells, reqw = prep["rcells"], prep["reqw"]

        # step 3: multi-layer Steiner-ish tree over the shared prep
        # (steps 1-2 + widening + F choke + bias live in _prep_overunder_net,
        # shared verbatim with the pre-FR corridor reservation below)
        path_cells, bridges, ok, bottleneck = route_overunder(
            prep["layers"], prep["passable"], prep["anchors"], prep["clab"],
            prep["nclusters"], bias_fn=prep["bias_fn"])
        if collect is not None:
            collect[net] = {"ok": ok, "path_cells": path_cells,
                            "bridges": bridges, "rcells": prep["rcells"],
                            "foreign": prep["foreign"], "reqw": prep["reqw"]}

        if not ok:
            report[net] = {"path_found": False, "segments": 0, "bridges": 0,
                           "layers_used": [], "bottleneck": bottleneck,
                           **({"manifolds": len(man_by_net.get(net, ())),
                               "manifold_attach": prep.get("attach_notes")}
                              if manifolds else {})}
            print(f"[cec_slab_pour] over-under: NO PATH for {net} -- "
                  f"bottleneck {bottleneck}", file=sys.stderr)
            continue

        # step 4: realize (lanes + bridge vias)
        apply_bridge_overlap(path_cells, bridges, grid)
        realized = realize_overunder(path_cells, rcells, grid)
        segs = 0
        for lay, polys in realized.items():
            for poly in polys:
                pour_dicts.append({"net": net, "layer": lay, "polygon": poly,
                                   "provenance": "overunder"})
                segs += 1

        net_vias = bridges_to_vias(bridges, reqw, grid,
                                   existing=existing_vias_mm)
        for v in net_vias:
            v["net"] = net
            existing_vias_mm.append((v["x_mm"], v["y_mm"]))
        via_list.extend(net_vias)

        report[net] = {"path_found": True, "segments": segs,
                       "bridges": len(bridges),
                       "layers_used": sorted(realized.keys()),
                       **({"manifolds": len(man_by_net.get(net, ())),
                           "manifold_attach": prep.get("attach_notes")}
                          if manifolds else {})}
        print(f"[cec_slab_pour] over-under: {net} -> {segs} lane segment(s) "
              f"on {sorted(realized.keys())}, {len(bridges)} bridge(s), "
              f"{len(net_vias)} via(s)", file=sys.stderr)

    return pour_dicts, via_list, report


# ---------------------------------------------------------------------------
# PRE-FR POUR-CORRIDOR RESERVATION (owner priority ruling, docs/slab-pour-
# design-2026-07-24.md: "the pour takes priority and gets its route first
# before everyone else gets to encroach"; realized 2026-07-25 as the
# REACHABILITY half of the RS1 starvation-cycle fix -- guaranteed_shunt_
# patches above is the coverage half). The over-under solver used to run
# only POST-route: by then FR has filled the board and a congested net's
# terminal clusters can be GENUINELY disconnected on every layer (measured:
# /SENSE12V_LO, TB1<->RS1, proven by union-find over the passable graph).
# Here the SAME search runs on the PRE-ROUTE board -- foreign masks see only
# existing copper (locked force rails, pads, pre-laid taps; no FR tracks
# yet) -- and each found corridor is handed back as keepout rects so FR
# routes signals AROUND it; the post-route realization then finds the
# corridor still clear by construction. Gated CEC_POUR_RESERVE=1 at the
# cec_fr.route_once wire-up; never default-on (golden safety).
# ---------------------------------------------------------------------------
def _mask_rects(mask, grid):
    """EXACT rectangle cover of a boolean mask (mm coords): per-row runs
    merged across consecutive rows with an identical span. Straight corridor
    legs collapse to ONE rect each (turn_cost keeps lanes straight); corners,
    bridge disks and foreign-bite fragments contribute a handful more.
    Exactness matters BOTH ways: a rect never overshoots the mask (a keepout
    must not swallow a foreign pad or its clearance halo) and the union
    covers every cell (no unreserved sliver inside the corridor for a signal
    to squeeze into). Returns [(x0, y0, x1, y1), ...]."""
    ny, nx = mask.shape
    open_runs = {}                       # (i0, i1) -> first row j it appeared
    out = []
    for j in range(ny + 1):
        runs = set()
        if j < ny:
            row = mask[j]
            i = 0
            while i < nx:
                if row[i]:
                    k = i
                    while k < nx and row[k]:
                        k += 1
                    runs.add((i, k))
                    i = k
                else:
                    i += 1
        for span in [s for s in open_runs if s not in runs]:
            i0, i1 = span
            j0 = open_runs.pop(span)
            out.append((grid.x0 + i0 * grid.cell, grid.y0 + j0 * grid.cell,
                        grid.x0 + i1 * grid.cell, grid.y0 + j * grid.cell))
        for span in runs:
            open_runs.setdefault(span, j)
    return out


def corridor_masks(path_cells, bridges, rcells, foreign, grid, *,
                   margin_cells=1):
    """PURE raster half of the reservation: per-layer corridor masks from one
    net's over-under search result. Each layer's path is dilated by that
    layer's OWN half-width in cells (the same *rcells* the search eroded by
    -- erosion-connectivity duality: that ring is provably foreign-free for
    eroded path cells) PLUS *margin_cells* of clearance buffer (so an FR
    track hugging the keepout boundary has its clearance shadow eat only the
    buffer ring, never the lane itself), then the layer's raw *foreign* mask
    (rasterize() output, already clearance-padded) is SUBTRACTED -- the
    margin ring and any anchor-walked stretch (own pads beside foreign pads
    at a connector carry no erosion guarantee, incl. the anchor-approach
    taper cells) can therefore never swallow a foreign pad or its halo,
    which would wall FR off from copper it MUST still reach. Bridge overlap
    disks are applied first (on a copy) so the via-array landing areas are
    reserved on both transitioning layers. Returns {layer: mask}, non-empty
    layers only."""
    from scipy import ndimage
    st = ndimage.generate_binary_structure(2, 1)
    pc = {lay: m.copy() for lay, m in path_cells.items()}
    apply_bridge_overlap(pc, bridges, grid)
    out = {}
    for lay, m in pc.items():
        if not m.any():
            continue
        dil = ndimage.binary_dilation(
            m, structure=st,
            iterations=max(1, int(rcells.get(lay, 1)) + int(margin_cells)))
        f = foreign.get(lay)
        if f is not None:
            dil = dil & ~f
        if dil.any():
            out[lay] = dil
    return out


def reservation_from_search(net, ok, path_cells, bridges, rcells, foreign,
                            grid, *, margin_cells=1):
    """PURE post-search half of `reserve_pour_corridors`: corridor rect dicts
    from one net's search outcome. Returns (corridors, reserved):

      * ok=False (no path)         -> ([], False)  -- a no-path net reserves
        NOTHING and must stay fully FR-routed (the caller excludes no pads);
      * path_cells empty (a single terminal cluster: trivially connected)
        -> ([], False) -- nothing to reserve, FR keeps the net;
      * else -> one dict per covering rect {net, layer, x0, y0, x1, y1,
        polygon} (polygon = the rect's 4 corners, for consumers that want
        outline form), reserved=True iff at least one rect survived the
        foreign carve."""
    if not ok or not path_cells or not any(m.any()
                                           for m in path_cells.values()):
        return [], False
    cors = []
    for lay, m in corridor_masks(path_cells, bridges, rcells, foreign, grid,
                                 margin_cells=margin_cells).items():
        for (x0, y0, x1, y1) in _mask_rects(m, grid):
            cors.append({"net": net, "layer": lay,
                         "x0": round(x0, 3), "y0": round(y0, 3),
                         "x1": round(x1, 3), "y1": round(y1, 3),
                         "polygon": [(round(x0, 3), round(y0, 3)),
                                     (round(x1, 3), round(y0, 3)),
                                     (round(x1, 3), round(y1, 3)),
                                     (round(x0, 3), round(y1, 3))]})
    return cors, bool(cors)


def corridors_to_keepouts(corridors):
    """bake_hints-ready keepout dicts from `reserve_pour_corridors` corridor
    rects, on each rect's OWN layer only. block_fills=False -- the reserved
    corridor exists exactly so the SAME-NET pour can fill it solid (the
    _vital_keepouts_from_rules precedent). Vias stay BLOCKED (bake_hints
    default): a foreign via inside the lane would antipad a hole through it
    at fill time -- the pinch class the reservation exists to prevent."""
    out = []
    for i, c in enumerate(corridors):
        net_tag = str(c.get("net", "net")).strip("/").replace("/", "_")
        out.append({"name": "pourres_%s_%d" % (net_tag, i),
                    "x0": c["x0"], "y0": c["y0"],
                    "x1": c["x1"], "y1": c["y1"],
                    "layers": (c["layer"],),
                    "block_fills": False})
    return out


def reserve_pour_corridors(board, asks, *, cell_mm=0.8, clearance_mm=0.3):
    """Compute + return the pre-FR corridor reservation for *asks* (the SAME
    pour-ask dicts the import-side conversion consumes: {"net",
    "layer"/"layers", ...}), running the IDENTICAL terminal-cluster +
    eroded-mask + direction-state Dijkstra machinery as
    `synthesize_overunder_pours` (shared `_prep_overunder_net` +
    `route_overunder`) -- but on the PRE-ROUTE board, where foreign masks
    see only existing copper. Asks are DEDUPED per net (union of their layer
    lists): the rail compiler emits several region dicts per net, and one
    corridor per net is the reservation unit.

    Returns {"corridors": [rect dicts, see reservation_from_search],
             "report": {net: {"reserved", "rects"/"reason"/"bottleneck",
                              "layers", "bridges", "exclude_pins"}}}.

    exclude_pins -- the "<ref>-<pad>" DSN tokens whose connectivity the
    reserved pour OWNS, for the _dsn_exclude_pins pattern. CONSERVATIVE
    tiers, deliberately NOT every pad of the net: (a) THT pads (they pierce
    natively to any lane layer -- an In2/B corridor through the cluster
    bonds them at fill); (b) SMD pads inside a shunt neighborhood (the one
    place the add_power_pours F.Cu choke ADMITS landing copper). Other SMD
    pads (scattered logic-side decoupling) stay FR-routed: their over-under
    F landing patches would be REFUSED at the choke, so handing their
    connectivity to the pour would strand them. A net whose search found NO
    path excludes nothing at all."""
    grid = Grid(board, cell_mm)
    nets_nc = {n.GetNetname(): c
               for c, n in board.GetNetInfo().NetsByNetcode().items()}
    net_currents = {}
    try:
        import cec_thermal_overlay as _ov
        _cfg = _ov.board_thermal_config(
            os.environ.get("CEC_THERMAL_BOARD_HINT", ""))
        net_currents = dict((_cfg[0] if _cfg else None) or {})
    except Exception:                                  # noqa: BLE001
        net_currents = {}
    shunt_boxes = shunt_neighborhoods(board)
    shunt_mask = np.zeros((grid.ny, grid.nx), bool)
    for (x0, y0, x1, y1) in shunt_boxes:
        grid.stamp_box(shunt_mask, x0, y0, x1, y1)

    per_net = {}
    for a in asks:
        net = a.get("net")
        if not net:
            continue
        lays = per_net.setdefault(net, [])
        for lay in (a.get("layers") or (a.get("layer", "F.Cu"),)):
            if lay not in lays:
                lays.append(lay)

    def _excludable(fp, p):
        # shared tier test (extracted 2026-07-25 so the pour-first stage
        # computes the IDENTICAL exclusion set -- no drift)
        return _excludable_pad(p, shunt_boxes)

    corridors, report = [], {}
    for net, ask_layers in per_net.items():
        if net not in nets_nc:
            report[net] = {"reserved": False, "reason": "net not on board",
                           "exclude_pins": []}
            continue
        nc = nets_nc[net]
        prep, _why = _prep_overunder_net(board, net, nc, ask_layers, grid,
                                         net_currents=net_currents,
                                         shunt_mask=shunt_mask,
                                         clearance_mm=clearance_mm)
        if prep is None:
            report[net] = {"reserved": False, "reason": _why,
                           "exclude_pins": []}
            continue
        path_cells, bridges, ok, bottleneck = route_overunder(
            prep["layers"], prep["passable"], prep["anchors"], prep["clab"],
            prep["nclusters"], bias_fn=prep["bias_fn"])
        cors, reserved = reservation_from_search(
            net, ok, path_cells, bridges, prep["rcells"], prep["foreign"],
            grid)
        if not reserved:
            report[net] = {"reserved": False, "exclude_pins": [],
                           **({"bottleneck": bottleneck} if not ok else
                              {"reason": "single terminal cluster "
                                         "(nothing to connect)"})}
            print(f"[cec_slab_pour] pour-reserve: nothing reserved for {net}"
                  + (f" -- NO PATH, stays fully FR-routed ({bottleneck})"
                     if not ok else " -- single terminal cluster"),
                  file=sys.stderr)
            continue
        corridors.extend(cors)
        pins = sorted({f"{fp.GetReference()}-{p.GetPadName()}"
                       for fp in board.GetFootprints() for p in fp.Pads()
                       if p.GetNetCode() == nc and _excludable(fp, p)})
        lays = sorted({c["layer"] for c in cors})
        report[net] = {"reserved": True, "rects": len(cors), "layers": lays,
                       "bridges": len(bridges), "exclude_pins": pins}
        print(f"[cec_slab_pour] pour-reserve: {net} -> {len(cors)} corridor "
              f"rect(s) on {lays}, {len(bridges)} bridge(s), {len(pins)} "
              f"pour-owned pad(s) to exclude from FR", file=sys.stderr)
    return {"corridors": corridors, "report": report}


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


def guaranteed_shunt_patches(board, margin_mm=4.5, gap_mm=0.15):
    """UNCONDITIONAL per-pad F.Cu patch dicts for every RS* shunt (owner,
    2026-07-25: RS1 measured pour-naked -- the starvation cycle: congested
    area -> its shave comes out lace-bound -> scrap filter drops it ->
    coverage-gated force-vias refuse -> no anchors -> unreachable -> no
    pour, forever). Each shunt pad-net gets its half of the shunt
    neighborhood as a patch: anchored by the pad itself BY DEFINITION (so
    the floating-fragment rule can never drop it), inside the shunt
    neighborhood by construction (so the F choke admits it), provenance
    'slab' (so the bond/scrap filter and F-rectangularize exempt it).
    HI/LO halves are clipped at the pad-group mid-gap so the two nets'
    patches never overlap. Local COVERAGE guarantee only -- reachability
    is the pre-FR corridor reservation's job."""
    out = []
    for fp in board.GetFootprints():
        if not fp.GetReference().startswith("RS"):
            continue
        by_net = {}
        for p in fp.Pads():
            n = p.GetNetname()
            if n and n != "GND":
                by_net.setdefault(n, []).append(p)
        if len(by_net) != 2:
            continue
        def _gbox(ps):
            return (min(p.GetBoundingBox().GetLeft() for p in ps) / MM,
                    min(p.GetBoundingBox().GetTop() for p in ps) / MM,
                    max(p.GetBoundingBox().GetRight() for p in ps) / MM,
                    max(p.GetBoundingBox().GetBottom() for p in ps) / MM)
        (na, pa), (nb, pb) = by_net.items()
        ba, bbx = _gbox(pa), _gbox(pb)
        ca = ((ba[0] + ba[2]) / 2, (ba[1] + ba[3]) / 2)
        cb = ((bbx[0] + bbx[2]) / 2, (bbx[1] + bbx[3]) / 2)
        horiz = abs(cb[0] - ca[0]) >= abs(cb[1] - ca[1])
        mid = ((ca[0] + cb[0]) / 2, (ca[1] + cb[1]) / 2)
        for net, gb, cc in ((na, ba, ca), (nb, bbx, cb)):
            x0, y0 = gb[0] - margin_mm, gb[1] - margin_mm
            x1, y1 = gb[2] + margin_mm, gb[3] + margin_mm
            if horiz:
                if cc[0] < mid[0]:
                    x1 = min(x1, mid[0] - gap_mm)
                else:
                    x0 = max(x0, mid[0] + gap_mm)
            else:
                if cc[1] < mid[1]:
                    y1 = min(y1, mid[1] - gap_mm)
                else:
                    y0 = max(y0, mid[1] + gap_mm)
            out.append({"net": net, "layer": "F.Cu",
                        "polygon": [(round(x0, 3), round(y0, 3)),
                                    (round(x1, 3), round(y0, 3)),
                                    (round(x1, 3), round(y1, 3)),
                                    (round(x0, 3), round(y1, 3))],
                        "provenance": "slab", "priority": 2,
                        # zone-name identity (v3 nowhere-reaper exemption:
                        # a guaranteed patch is sanctioned single-cluster
                        # copper -- never "leads nowhere")
                        "name": "patch:%s" % net})
    return out


# ---------------------------------------------------------------------------
# v3.1 -- CONNECTOR MANIFOLDS (owner algorithm 2026-07-25, docs/slab-pour-
# design-2026-07-24.md v3.1: "combine up all similar pins on one connector
# with a margin-width pour"). One bus-bar pour dict per (connector footprint,
# net, layer): the pin group's bbox + margin -- guaranteed_shunt_patches'
# construction generalized to connectors. Pad-anchored BY CONSTRUCTION (the
# group's own pads are inside it), so the floating-fragment rule and the
# nowhere-reaper can never drop it (name "manifold:<ref>:<net>"). Layers by
# the pad type's natural layer: a THT group anchors every copper layer, so it
# gets an F.Cu AND an In2.Cu manifold (the inner power layer is where the
# spine wants to attach; the F one is the barrel-field bus bar); an SMD group
# gets its own side only.
# ---------------------------------------------------------------------------
def connector_manifolds(board, nets=None, *, margin_mm=4.0,
                        ref_prefixes=("J", "TB")):
    """Manifold pour dicts for every (connector, net) pin group.

    *nets* -- restrict to these net names (None = every non-GND net on a
    connector). GND is always excluded (plane-carried; a GND manifold would
    just shadow the plane). Returns dicts in add_power_pours' format with
    provenance "slab" (the bond/scrap filter + F-rectangularize exemption
    class) and a "name" carrying the manifold identity for the choke-point
    admit + the nowhere-reaper exemption."""
    fcu = board.GetLayerID("F.Cu")
    bcu = board.GetLayerID("B.Cu")
    out = []
    for fp in board.GetFootprints():
        ref = fp.GetReference() or ""
        if not ref.startswith(tuple(ref_prefixes)):
            continue
        by_net = {}
        for p in fp.Pads():
            n = p.GetNetname()
            if not n or n == "GND" or (nets is not None and n not in nets):
                continue
            by_net.setdefault(n, []).append(p)
        for net, ps in sorted(by_net.items()):
            x0 = min(p.GetBoundingBox().GetLeft() for p in ps) / MM - margin_mm
            y0 = min(p.GetBoundingBox().GetTop() for p in ps) / MM - margin_mm
            x1 = max(p.GetBoundingBox().GetRight() for p in ps) / MM + margin_mm
            y1 = max(p.GetBoundingBox().GetBottom() for p in ps) / MM + margin_mm
            # natural layers: >1 copper layer on any pad = THT group (barrels
            # anchor F AND In2); single-layer = SMD group on its own side.
            tht = any(len(set(p.GetLayerSet().CuStack())) > 1 for p in ps)
            if tht:
                lays = [l for l in ("F.Cu", "In2.Cu")
                        if board.GetLayerID(l) >= 0]
            else:
                stack = set(ps[0].GetLayerSet().CuStack())
                lays = ["B.Cu" if bcu in stack and fcu not in stack
                        else "F.Cu"]
            for lay in lays:
                out.append({"net": net, "layer": lay,
                            "polygon": [(round(x0, 3), round(y0, 3)),
                                        (round(x1, 3), round(y0, 3)),
                                        (round(x1, 3), round(y1, 3)),
                                        (round(x0, 3), round(y1, 3))],
                            "provenance": "slab", "priority": 2,
                            "name": "manifold:%s:%s" % (ref, net)})
    return out


def _excludable_pad(p, shunt_boxes):
    """Shared pour-owns-this-pad tier test (extracted from
    reserve_pour_corridors so the pour-first stage computes the IDENTICAL
    exclusion set): THT pads pierce natively to any lane layer; SMD pads are
    pour-owned only inside a shunt neighborhood (the one place the F.Cu choke
    admits landing copper). pcbnew-free: THT-ness by copper-layer count."""
    if len(set(p.GetLayerSet().CuStack())) > 1:
        return True                                    # THT: pierces natively
    q = p.GetPosition()
    px, py = q.x / MM, q.y / MM
    return any(bx0 <= px <= bx1 and by0 <= py <= by1
               for (bx0, by0, bx1, by1) in shunt_boxes)


def pourfirst_conv_split(power_pours, frozen_nets, full):
    """PURE decision core of import_ses' conversion site under the v3
    POUR-FIRST freeze (set-in-stone semantics, docs/slab-pour-design-
    2026-07-24.md v3): returns (conv, frozen, keep_rest) where

      * conv   -- the dicts the conversion may still (re)solve: the usual
        filter (everything under CEC_SLAB_POUR=1 *full*, else placer_ask
        provenance) MINUS every frozen-stage dict AND every dict on a frozen
        net -- a net the pour-first stage solved is NEVER re-solved, found
        or failed;
      * frozen -- the pass-through dicts (provenance "pourfirst"), laid
        as-is;
      * keep_rest -- the non-converted remainder that must survive the
        final reassignment (frozen dicts + the non-ask dicts when not
        *full*)."""
    frozen = [p for p in power_pours if p.get("provenance") == "pourfirst"]
    conv = ([p for p in power_pours if p.get("provenance") != "pourfirst"]
            if full else
            [p for p in power_pours if p.get("provenance") == "placer_ask"])
    conv = [p for p in conv if p.get("net") not in set(frozen_nets or ())]
    keep_rest = frozen + ([] if full else
                          [p for p in power_pours
                           if p.get("provenance") not in ("placer_ask",
                                                          "pourfirst")])
    return conv, frozen, keep_rest


REAP_EXEMPT_PREFIXES = ("patch:", "manifold:", "pourfirst:")


def _nowhere_zone_verdict(zone_name, netname, clusters_hit):
    """PURE reaper decision (v3 defense-in-depth, owner: "the giant
    cross-board L3 pour and leads-nowhere pours must die"): a non-GND zone
    that connects <2 distinct same-net terminal clusters is DEAD WEIGHT --
    unless its name marks it as a guaranteed shunt patch, a connector
    manifold, or frozen pour-first state (sanctioned pad-anchored copper /
    set-in-stone geometry). Returns True = reap."""
    if not netname or netname == "GND":
        return False
    if str(zone_name or "").startswith(REAP_EXEMPT_PREFIXES):
        return False
    return int(clusters_hit) < 2


def reap_nowhere_zones(board_path, *, cell_mm=0.8):
    """NOWHERE-REAPER (v3 deliverable D): after the fill, remove every
    non-GND copper zone whose FILLED area touches <2 distinct same-net
    terminal clusters (pads/vias groups, `terminal_clusters`) -- the
    leads-nowhere class -- unless it is a named guaranteed patch / manifold /
    frozen pour-first dict (`_nowhere_zone_verdict`). Same fresh
    load->remove->save discipline as cleanup_floating_zones (the 2026-06-09
    in-process zone-removal footgun). Logs each reap with net + bbox."""
    if pcbnew is None:
        return 0
    board = pcbnew.LoadBoard(board_path)
    grid = Grid(board, cell_mm)
    cl_cache = {}
    doomed = []
    for z in board.Zones():
        if z.GetIsRuleArea():
            continue
        net = z.GetNetname()
        if not net or net == "GND":
            continue
        name = ""
        try:
            name = z.GetZoneName() or ""
        except Exception:                              # noqa: BLE001
            name = ""
        if str(name).startswith(REAP_EXEMPT_PREFIXES):
            continue
        nc = z.GetNetCode()
        if nc not in cl_cache:
            cl_cache[nc] = terminal_clusters(board, nc, grid)
        clab, ncl = cl_cache[nc]
        hit = set()
        if ncl:
            lay_ids = [lid for lid in z.GetLayerSet().CuStack()]
            ys, xs = np.where(clab > 0)
            for y, x in zip(ys.tolist(), xs.tolist()):
                cid = int(clab[y, x])
                if cid in hit:
                    continue
                at = pcbnew.VECTOR2I(
                    _nm(grid.x0 + (x + 0.5) * grid.cell),
                    _nm(grid.y0 + (y + 0.5) * grid.cell))
                for lid in lay_ids:
                    try:
                        if z.HitTestFilledArea(lid, at, 0):
                            hit.add(cid)
                            break
                    except Exception:                  # noqa: BLE001
                        break
        if _nowhere_zone_verdict(name, net, len(hit)):
            bb = z.GetBoundingBox()
            doomed.append((z, net,
                           (round(bb.GetLeft() / MM, 1),
                            round(bb.GetTop() / MM, 1),
                            round(bb.GetRight() / MM, 1),
                            round(bb.GetBottom() / MM, 1)), len(hit)))
    for (z, net, bbox, nhit) in doomed:
        print(f"[cec_slab_pour] nowhere-reap: zone on {net} at {bbox} "
              f"connects {nhit} terminal cluster(s) (<2) -- REMOVED",
              file=sys.stderr)
        board.Remove(z)
    if doomed:
        pcbnew.SaveBoard(board_path, board)
        print(f"[cec_slab_pour] nowhere-reap: removed {len(doomed)} "
              "leads-nowhere zone(s)", file=sys.stderr)
    return len(doomed)
