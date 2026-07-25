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


def synthesize_overunder_pours(board, asks, *, cell_mm=0.8, clearance_mm=0.3):
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
    """
    from scipy import ndimage
    st = ndimage.generate_binary_structure(2, 1)

    grid = Grid(board, cell_mm)
    nets_nc = {n.GetNetname(): c
               for c, n in board.GetNetInfo().NetsByNetcode().items()}

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

    for a in asks:
        net = a.get("net")
        if net not in nets_nc:
            report[net] = {"path_found": False, "segments": 0, "bridges": 0,
                           "layers_used": [], "reason": "net not on board"}
            continue
        nc = nets_nc[net]
        layers = list(dict.fromkeys(
            list(a.get("layers") or (a.get("layer", "F.Cu"),))
            + ["In2.Cu", "B.Cu"]))
        layers = [lay for lay in layers if board.GetLayerID(lay) >= 0]
        if not layers:
            report[net] = {"path_found": False, "segments": 0, "bridges": 0,
                           "layers_used": [], "reason": "no valid layer"}
            continue

        # step 1: terminal groups
        clab, nclusters = terminal_clusters(board, nc, grid)
        if nclusters == 0:
            report[net] = {"path_found": False, "segments": 0, "bridges": 0,
                           "layers_used": [], "reason": "no pads/vias for net"}
            continue

        # step 2: per-layer eroded/passable masks + required width
        amps = net_currents.get(net, 0.0)
        passable, anchors, rcells, reqw = {}, {}, {}, {}
        for lay in layers:
            lay_id = board.GetLayerID(lay)
            foreign, anc = rasterize(board, nc, lay_id, grid, clearance_mm)
            w = req_width_mm(amps, lay) if amps > 0 else 1.2
            rc = max(1, int(round(w / (2.0 * grid.cell))))
            eroded = ndimage.binary_erosion(~foreign, structure=st,
                                            iterations=rc)
            passable[lay] = eroded | anc
            anchors[lay] = anc
            rcells[lay] = rc
            reqw[lay] = w

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
            foreign, anc = rasterize(board, nc, board.GetLayerID(extra),
                                     grid, clearance_mm)
            helped = [k for k in uncov if (anc & (clab == k)).any()]
            if not helped:
                continue
            w = req_width_mm(amps, extra) if amps > 0 else 1.2
            rc = max(1, int(round(w / (2.0 * grid.cell))))
            layers.append(extra)
            passable[extra] = ndimage.binary_erosion(
                ~foreign, structure=st, iterations=rc) | anc
            anchors[extra] = anc
            rcells[extra] = rc
            reqw[extra] = w
            print(f"[cec_slab_pour] over-under: widened {net} search to "
                  f"{extra} (terminal cluster(s) {helped} anchored only "
                  f"there)", file=sys.stderr)
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
            passable["F.Cu"] &= (
                ndimage.binary_dilation(anchors["F.Cu"], structure=st,
                                        iterations=3)
                | shunt_mask | anchors["F.Cu"])
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

        # step 3: multi-layer Steiner-ish tree
        path_cells, bridges, ok, bottleneck = route_overunder(
            layers, passable, anchors, clab, nclusters, bias_fn=_bias)

        if not ok:
            report[net] = {"path_found": False, "segments": 0, "bridges": 0,
                           "layers_used": [], "bottleneck": bottleneck}
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
                       "layers_used": sorted(realized.keys())}
        print(f"[cec_slab_pour] over-under: {net} -> {segs} lane segment(s) "
              f"on {sorted(realized.keys())}, {len(bridges)} bridge(s), "
              f"{len(net_vias)} via(s)", file=sys.stderr)

    return pour_dicts, via_list, report


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
