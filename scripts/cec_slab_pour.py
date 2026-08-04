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
import math
import sys

import numpy as np
import cec_fab_profile as fab

try:
    import pcbnew
except ImportError:                                    # host-side import for tests
    pcbnew = None

# SWIG REGISTRY PIN -- see scripts/cec_swig_guard.py (hub all-9999 root cause).
if pcbnew is not None:
    import cec_swig_guard as _swig_guard
    _swig_guard.pin()

MM = 1e6


class SlabAllocationError(RuntimeError):
    """A requested slab set could not satisfy its hard geometric contract."""

    def __init__(self, failures, report):
        self.failures = tuple(failures)
        self.report = report
        super().__init__("slab allocation failed closed for %s"
                         % ", ".join("%s/%s" % key for key in self.failures))

    def __reduce__(self):
        """Preserve the structured failure across multiprocessing boundaries.

        RuntimeError normally pickles only ``args``.  This exception's public
        constructor also requires the allocation report, so relying on the
        default reducer makes a worker-result thread crash while unpickling the
        error and leaves its parent blocked forever.
        """
        return type(self), (self.failures, self.report)


def _board_file_path(board):
    """Return the loaded board path when pcbnew exposes one.

    Committed boards already identify their family in the filename. Requiring a
    separate CEC_THERMAL_BOARD_HINT for those boards made the standalone pour
    command silently lose its current model even though the input itself was
    sufficient. Generated wave boards still use the explicit environment hint
    because their temporary filenames do not identify the board family.
    """
    if board is None:
        return ""
    try:
        return str(board.GetFileName() or "")
    except Exception:                                  # noqa: BLE001
        return ""


def _board_thermal_config(board=None):
    """Resolve thermal inputs from the explicit hint or loaded board path."""
    try:
        import cec_thermal_overlay as _ov
        path = _board_file_path(board)
        hint = (os.environ.get("CEC_THERMAL_BOARD_HINT", "")
                or os.path.basename(path))
        return _ov.board_thermal_config(path or hint, board_hint=hint)
    except Exception:                                  # noqa: BLE001
        return None


def _board_identity(board=None):
    """Board-family key used by the synthesis design-current table."""
    path = _board_file_path(board)
    return (os.environ.get("CEC_THERMAL_BOARD_HINT", "")
            or os.path.basename(path))


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

    def stamp_anchor_box(self, mask, x0, y0, x1, y1, val=True):
        """Stamp only raster cells whose centres lie inside real copper.

        ``stamp_box`` is intentionally conservative for obstacles: every cell
        touched by foreign copper is blocked.  Applying that same expansion to
        own-net anchors lets a route terminate at a cell whose centre is almost
        a full cell diagonal outside a small pad/via.  The drawn lane then need
        not touch the physical terminal even though the raster says it does.
        Anchor masks use the dual rule: centre-contained cells, with one nearest
        cell fallback for sub-cell copper.
        """
        if x1 < self.x0 or x0 > self.x1 or y1 < self.y0 or y0 > self.y1:
            return
        i0 = int(math.ceil((x0 - self.x0) / self.cell - 0.5))
        i1 = int(math.floor((x1 - self.x0) / self.cell - 0.5))
        j0 = int(math.ceil((y0 - self.y0) / self.cell - 0.5))
        j1 = int(math.floor((y1 - self.y0) / self.cell - 0.5))
        i0, i1 = max(0, i0), min(self.nx - 1, i1)
        j0, j1 = max(0, j0), min(self.ny - 1, j1)
        if i1 >= i0 and j1 >= j0:
            mask[j0:j1 + 1, i0:i1 + 1] = val
            return
        # Copper smaller than one grid cell still owns its nearest cell.
        i = min(self.nx - 1, max(0, int(round(
            (((x0 + x1) / 2.0) - self.x0) / self.cell - 0.5))))
        j = min(self.ny - 1, max(0, int(round(
            (((y0 + y1) / 2.0) - self.y0) / self.cell - 0.5))))
        mask[j, i] = val


def edge_cut_items(board):
    """All board-level and footprint-local Edge.Cuts graphics."""
    items = [item for item in getattr(board, "GetDrawings", lambda: ())()
             if item.GetLayer() == pcbnew.Edge_Cuts]
    items.extend(
        item for fp in board.GetFootprints()
        for item in getattr(fp, "GraphicalItems", lambda: ())()
        if item.GetLayer() == pcbnew.Edge_Cuts)
    return items


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
                grid.stamp_anchor_box(anchors, x0, y0, x1, y1)
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

    # Edge.Cuts is a fabrication obstacle on EVERY copper layer, including
    # footprint-local apertures (the Hub's reverse LEDs).  The outer outline
    # is already represented by Grid's board-edge margin, but stamping all
    # graphics also captures internal slots/cutouts that the old copper-only
    # raster completely ignored.  Lane-width erosion adds the routed copper's
    # own radius later.  Via-field seating has a larger, separate exclusion in
    # realize_overunder_rects; using that barrel halo here sealed the Hub's
    # reverse-LED supply pads inside their own apertures.
    edge_halo = c
    board_edges = [item for item in getattr(board, "GetDrawings", lambda: ())()
                   if item.GetLayer() == pcbnew.Edge_Cuts]
    footprint_edges = []
    for fp in board.GetFootprints():
        # A reverse-mount aperture may be enclosed by the net's own annular
        # F.Cu pads.  Those pads must remain valid terminal anchors; the zone
        # filler clips their local copper to the aperture and the via-field
        # exclusion below still forbids a barrel there.  Inner layers (where
        # those SMD pads are not anchors) continue to see the through-cutout.
        own_anchor = any(pad.GetNetCode() == nc for pad in fp.Pads())
        if own_anchor:
            continue
        footprint_edges.extend(
            item for item in getattr(fp, "GraphicalItems", lambda: ())()
            if item.GetLayer() == pcbnew.Edge_Cuts)
    for item in board_edges + footprint_edges:
        bb = item.GetBoundingBox()
        grid.stamp_box(
            foreign,
            bb.GetLeft() / MM - edge_halo,
            bb.GetTop() / MM - edge_halo,
            bb.GetRight() / MM + edge_halo,
            bb.GetBottom() / MM + edge_halo)
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


def _drop_collinear(pts, tol=1e-6):
    """Remove vertices that lie on the segment between their neighbours.

    Shape-preserving by construction (unlike simplify(), which moves the outline
    and turns a staircase into a diagonal). Purely fewer points."""
    if len(pts) < 4:
        return pts
    closed = pts[0] == pts[-1]
    ring = pts[:-1] if closed else list(pts)
    out = []
    n = len(ring)
    for i in range(n):
        x0, y0 = ring[i - 1]
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        cross = (x1 - x0) * (y2 - y0) - (y1 - y0) * (x2 - x0)
        if abs(cross) > tol:
            out.append((x1, y1))
    if len(out) < 3:
        return pts
    return out + [out[0]] if closed else out


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
        # SMOOTH ON THE MASK, NEVER ON THE POLYGON (owner 2026-07-25: "diagonal
        # blobs that don't make sense"). The union of cell-runs below is exactly
        # rectilinear; the Douglas-Peucker simplify that used to follow it cut
        # corners and MANUFACTURED the diagonals -- measured on the 24-pin winner
        # as 77 diagonal edges across the pourfirst zones and 64 across pourplan,
        # while every hand-shaped producer (manifold:, patch:) sat at 0. Closing
        # then opening removes the one-cell bites and spurs that made the raw
        # raster read as "weirdly blocky" (the 07-24 complaint this smoothing was
        # added for) and leaves every edge axis-aligned.
        _st2 = ndimage.generate_binary_structure(2, 1)
        m = ndimage.binary_closing(mask, structure=_st2, iterations=2)
        m = ndimage.binary_opening(m, structure=_st2, iterations=1)
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
    # NO polygon-level simplify: it is the diagonal source (see above). Collinear
    # vertices are dropped instead -- identical geometry, fewer points.
    if smooth:
        u = u.buffer(0)
    geoms = getattr(u, "geoms", [u])
    out = []
    for g in geoms:
        if g.area < min_area_mm2:
            continue
        _pts = [(round(x, 3), round(y, 3)) for x, y in g.exterior.coords]
        out.append(_drop_collinear(_pts))
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
                          min_w_mm=1.2, strict=True):
    """asks: pour dicts ({net, layer, ...}) naming the slab (net, layer) pairs
    -- the ask CHANNEL is kept; the rect geometry is replaced by the slab.
    Returns (pour_dicts, per-net report). By default any requested rail with
    missing anchors/current or a failed minimum-width invariant raises
    SlabAllocationError. ``strict=False`` is diagnostic-only and returns the
    tentative geometry plus the marked report."""
    grid = Grid(board, cell_mm)
    nets_nc = {n.GetNetname(): c
               for c, n in board.GetNetInfo().NetsByNetcode().items()}
    seen = set()
    out, rep, prepared = [], {}, []
    for a in asks:
        net = a.get("net")
        for lay in (a.get("layers") or (a.get("layer", "F.Cu"),)):
            key = (net, lay)
            if key in seen:
                continue
            seen.add(key)
            if net not in nets_nc:
                rep[key] = {"skipped": "requested net is absent from the board",
                            "allocation_failed_closed": True}
                continue
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
            prepared.append({"key": key, "net": net, "layer": lay,
                             "ask": a, "foreign": foreign,
                             "anchors": anchors, "mask": mask})

    # A zone filler resolves equal-priority overlapping outlines by allowing one
    # net to own the contested copper. The old implementation handed every
    # additive Hub rail almost the whole inner layer, so ask/order or fill order
    # selected a roughly 4300 mm2 winner while tail rails received no zone. Do
    # the ownership solve before polygons exist. Disjoint candidate groups keep
    # their historical maximal slabs; overlapping groups use a weighted,
    # anchor-seeded flood whose service rate is proportional to the verified
    # sustained design current.
    by_layer = {}
    for p in prepared:
        by_layer.setdefault(p["layer"], []).append(p)
    for lay in sorted(by_layer):
        layer_plans = sorted(by_layer[lay], key=lambda p: p["net"])
        for group in _overlap_groups(layer_plans):
            if len(group) == 1:
                # Closing/smoothing may grow an outline into a nearby net's
                # non-overlapping candidate. Preserve exact raster ownership
                # whenever more than one rail uses the layer.
                _emit_slab_plan(out, rep, group[0], group[0]["mask"], grid,
                                smooth=(len(layer_plans) == 1))
                continue
            weights, missing, current_sources = _slab_design_currents(
                group, board=board)
            if missing:
                why = ("overlapping slab allocation requires a declared "
                       "design-basis current; missing %s" % ", ".join(missing))
                for p in group:
                    rep[p["key"]].update({"skipped": why,
                                           "allocation_failed_closed": True})
                print("[cec_slab_pour] %s %s" % (lay, why),
                      file=sys.stderr, flush=True)
                continue
            masks, alloc = weighted_fair_masks(
                [p["mask"] for p in group],
                [p["anchors"] for p in group], weights,
                names=[p["net"] for p in group])
            for p, owned, amps, ar, current_source in zip(
                    group, masks, weights, alloc, current_sources):
                # Re-run the same width/prune invariant with every other
                # allocation cell treated as contested. This cannot introduce
                # overlap and catches a fair-share strip that became too thin.
                final, final_rep = shave(~owned, p["anchors"], grid, min_w_mm)
                final &= owned
                final_rep.update({
                    "allocation": "weighted_fair_v1",
                    "design_current_A": float(amps),
                    "design_current_source": current_source,
                    "target_cells": ar["target_cells"],
                    "allocated_cells_before_shave": ar["allocated_cells"],
                    "allocation_share": ar["share"],
                })
                rep[p["key"]].update(final_rep)
                _emit_slab_plan(out, rep, p, final, grid, smooth=False)
    failures = []
    for key, row in rep.items():
        reason = None
        if row.get("allocation_failed_closed"):
            reason = row.get("skipped") or "allocation failed"
        elif row.get("skipped"):
            reason = row["skipped"]
        elif row.get("min_width_ok") is False:
            reason = ("minimum-width invariant failed with %s anchor group(s)"
                      % row.get("anchor_groups_after_erosion"))
        if reason:
            row["allocation_failed_closed"] = True
            row["failure_reason"] = reason
            failures.append(key)
    if failures and strict:
        raise SlabAllocationError(sorted(failures), rep)
    return out, rep


def _emit_slab_plan(out, rep, plan, mask, grid, *, smooth=True):
    """Emit one prepared slab without allowing outline smoothing to overlap a
    neighbour's allocated territory."""
    polys = mask_to_polys(mask, grid, smooth=smooth)
    rep[plan["key"]]["emitted_polygons"] = len(polys)
    for poly in polys:
        out.append({"net": plan["net"], "layer": plan["layer"],
                    "polygon": poly,
                    "priority": int(plan["ask"].get("priority", 2)),
                    "provenance": "slab"})


def _overlap_groups(plans):
    """Connected components of plans whose candidate copper overlaps."""
    left = set(range(len(plans)))
    groups = []
    while left:
        todo = [left.pop()]
        group = []
        while todo:
            i = todo.pop()
            group.append(plans[i])
            hit = [j for j in left
                   if np.logical_and(plans[i]["mask"],
                                     plans[j]["mask"]).any()]
            for j in hit:
                left.remove(j)
                todo.append(j)
        groups.append(sorted(group, key=lambda p: p["net"]))
    return groups


def _slab_design_currents(plans, *, board=None):
    """Resolve sustained currents without inventing a fallback value.

    An ask may carry ``design_current_A`` explicitly. Otherwise the board's
    thermal adapter supplies the declared model input, followed by the shared
    synthesis design-current table when the thermal adapter has no entry. A
    committed board is resolved from its loaded filename; generated wave
    boards use the explicit CEC_THERMAL_BOARD_HINT set by the synthesis
    pipeline. A missing or non-positive value is returned as missing so an
    overlapping allocation fails closed instead of silently becoming an
    equal-share guess. This function records provenance but does not claim
    owner approval for a model value; release validation remains a separate
    design-basis gate.
    """
    cfg_currents = {}
    cfg = _board_thermal_config(board)
    cfg_currents = dict((cfg[0] if cfg else None) or {})
    try:
        import cec_synth_pipeline as _sp
        spec_current = lambda net: _sp.spec_net_current(  # noqa: E731
            _board_identity(board), net)
    except Exception:                                  # noqa: BLE001
        spec_current = lambda _net: None               # noqa: E731
    values, missing, sources = [], [], []
    for p in plans:
        raw = p["ask"].get("design_current_A")
        source = "ask.design_current_A"
        if raw is None:
            raw = cfg_currents.get(p["net"])
            source = "board_thermal_config"
        if raw is None:
            raw = spec_current(p["net"])
            source = "spec_net_current"
        try:
            val = float(raw)
        except (TypeError, ValueError):
            val = 0.0
        if not math.isfinite(val) or val <= 0:
            missing.append(p["net"])
        values.append(val)
        sources.append(source)
    return values, missing, sources


def weighted_fair_masks(candidates, anchors, weights, *, names=None):
    """Partition overlapping boolean masks with current-weighted quotas.

    Each net may own only cells reachable from its same-net anchors inside its
    already verified candidate mask. A multi-source graph distance ranks those
    cells. The allocator then fills explicit ampere-weighted quotas from the
    nearest cells globally, rather than allowing a centrally placed first net
    to wall off the rest. The result is deterministic and disjoint. It is not a
    copper-sizing model: the required-width and anchor-connectivity checks run
    again after this territory allocation.
    """
    if not candidates or not (len(candidates) == len(anchors) == len(weights)):
        raise ValueError("candidate, anchor, and weight lists must be non-empty and equal")
    shape = candidates[0].shape
    if any(m.shape != shape for m in list(candidates) + list(anchors)):
        raise ValueError("all allocation masks must have the same shape")
    vals = [float(v) for v in weights]
    if any(not math.isfinite(v) or v <= 0 for v in vals):
        raise ValueError("allocation weights must be finite and positive")
    from collections import deque
    labels = list(names or [str(i) for i in range(len(candidates))])
    order = sorted(range(len(candidates)), key=lambda i: labels[i])
    owner = np.full(shape, -1, dtype=np.int16)
    allocated = [0 for _ in candidates]
    ny, nx = shape

    # Same-net anchors are mandatory ownership. If two nets claim one raster
    # anchor cell, the input copper already collides and allocation must stop.
    for i in order:
        seed = anchors[i] & candidates[i]
        collision = seed & (owner >= 0) & (owner != i)
        if collision.any():
            raise ValueError("overlapping anchors between slab nets")
        new = seed & (owner < 0)
        owner[new] = i
        allocated[i] += int(new.sum())
    union_cells = int(np.logical_or.reduce(candidates).sum())

    # Mandatory anchor cells are paid first. Divide every remaining cell by
    # the current ratios using largest-remainder rounding, so capacities sum
    # exactly to the allocatable union and no rail disappears at the tail.
    remaining = max(0, union_cells - sum(allocated))
    raw_extra = [remaining * v / sum(vals) for v in vals]
    extra = [int(math.floor(v)) for v in raw_extra]
    for i in sorted(range(len(vals)),
                    key=lambda q: (-(raw_extra[q] - extra[q]), labels[q]))[
                        :remaining - sum(extra)]:
        extra[i] += 1
    quotas = [allocated[i] + extra[i] for i in range(len(vals))]

    # Independent obstacle-aware graph distance from every net's own anchors.
    # All proposals enter one heap. Distance dominates; name/coordinate ties
    # make the result byte-stable and independent of ask order.
    distances = [None for _ in candidates]
    proposals = []
    unreachable = np.iinfo(np.int32).max
    for i in order:
        dist = np.full(shape, unreachable, dtype=np.int32)
        q = deque()
        for r, c in np.argwhere(anchors[i] & candidates[i]):
            r, c = int(r), int(c)
            dist[r, c] = 0
            q.append((r, c))
        while q:
            r, c = q.popleft()
            nd = int(dist[r, c]) + 1
            for dr, dc in ((-1, 0), (0, -1), (0, 1), (1, 0)):
                rr, cc = r + dr, c + dc
                if (0 <= rr < ny and 0 <= cc < nx
                        and candidates[i][rr, cc] and nd < dist[rr, cc]):
                    dist[rr, cc] = nd
                    q.append((rr, cc))
        distances[i] = dist
        for r, c in np.argwhere(dist < unreachable):
            if owner[r, c] < 0:
                heapq.heappush(proposals,
                               (int(dist[r, c]), labels[i], int(r), int(c), i))

    while proposals:
        _dist, _name, r, c, i = heapq.heappop(proposals)
        if owner[r, c] >= 0 or allocated[i] >= quotas[i]:
            continue
        owner[r, c] = i
        allocated[i] += 1

    # A constrained mask can be smaller than its quota. Assign any remaining
    # reachable cell to the eligible rail with the greatest quota deficit,
    # then the shortest anchor distance. This is the only source of a reported
    # share deviation and represents geometry, not input/fill order.
    union = np.logical_or.reduce(candidates)
    for r, c in np.argwhere(union & (owner < 0)):
        r, c = int(r), int(c)
        eligible = [i for i in order if distances[i][r, c] < unreachable]
        if not eligible:
            continue
        i = min(eligible, key=lambda q: (
            -(quotas[q] - allocated[q]), distances[q][r, c],
            allocated[q] / vals[q], labels[q]))
        owner[r, c] = i
        allocated[i] += 1

    masks = [owner == i for i in range(len(candidates))]
    total_weight = sum(vals)
    report = [{
        "target_cells": union_cells * vals[i] / total_weight,
        "allocated_cells": allocated[i],
        "share": (allocated[i] / union_cells if union_cells else 0.0),
    } for i in range(len(candidates))]
    return masks, report


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
def req_width_mm(amps, layer, *, board=None, profile_name=None):
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
    if profile_name is None and board is not None:
        profile_name = fab.board_profile_name(board)
    if profile_name is None:
        profile_name = (os.environ.get("CEC_FAB_PROFILE") or
                        fab.profile_for_board_hint(
                            os.environ.get("CEC_THERMAL_BOARD_HINT", "")))
    if profile_name:
        return fab.ipc2221_required_width_mm(
            amps, layer, profile_name=profile_name)

    # Back-compatible four-layer baseline. These are the old function's
    # explicit 2 oz outer and 1 oz inner thicknesses, expressed in mm so the
    # same centralized equation is used in both paths.
    copper_mm = fab.OZ_COPPER_MM * (2.0 if layer in ("F.Cu", "B.Cu") else 1.0)
    return fab.ipc2221_required_width_mm(
        amps, layer, copper_mm=copper_mm)


def terminal_clusters(board, nc, grid):
    """Step 1 (owner v2 design): physically connected terminal clusters.

    Pads and vias seed the terminal raster. Existing same-net tracks then
    merge the endpoint clusters they actually join. This matters for guarded
    pad-to-pickup links laid before pour synthesis: ignoring their track made
    the already-connected pad and through-via look like two terminals, so the
    solver added a redundant bridge field and clipped its landing into islands.
    Track chains are grouped by exact endpoint and layer; crossings on different
    layers therefore do not create fictitious connectivity.

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
        grid.stamp_anchor_box(mask, q.x / MM - r, q.y / MM - r,
                              q.x / MM + r, q.y / MM + r)
    clab, n = ndimage.label(mask)
    if n <= 1:
        return clab, n

    segments = []
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA" or t.GetNetCode() != nc:
            continue
        s, e = t.GetStart(), t.GetEnd()
        segments.append((
            (int(t.GetLayer()), int(s.x), int(s.y)),
            (int(t.GetLayer()), int(e.x), int(e.y)),
            (grid.iy(s.y / MM), grid.ix(s.x / MM)),
            (grid.iy(e.y / MM), grid.ix(e.x / MM)),
        ))
    if not segments:
        return clab, n

    # Connected track components, keyed by exact endpoint on one layer.
    node_parent = {}
    def _node_find(node):
        node_parent.setdefault(node, node)
        while node_parent[node] != node:
            node_parent[node] = node_parent[node_parent[node]]
            node = node_parent[node]
        return node
    def _node_union(a, b):
        ra, rb = _node_find(a), _node_find(b)
        if ra != rb:
            node_parent[rb] = ra
    for start, end, _scell, _ecell in segments:
        _node_union(start, end)

    label_parent = list(range(n + 1))
    def _label_find(label):
        while label_parent[label] != label:
            label_parent[label] = label_parent[label_parent[label]]
            label = label_parent[label]
        return label
    def _label_union(a, b):
        ra, rb = _label_find(a), _label_find(b)
        if ra != rb:
            label_parent[rb] = ra

    component_labels = {}
    for start, _end, scell, ecell in segments:
        root = _node_find(start)
        labels = component_labels.setdefault(root, set())
        for row, col in (scell, ecell):
            if 0 <= row < grid.ny and 0 <= col < grid.nx:
                label = int(clab[row, col])
                if label:
                    labels.add(label)
    for labels in component_labels.values():
        labels = sorted(labels)
        for label in labels[1:]:
            _label_union(labels[0], label)

    roots = sorted({_label_find(label) for label in range(1, n + 1)})
    dense = {root: index + 1 for index, root in enumerate(roots)}
    if len(roots) == n:
        return clab, n
    merged = np.zeros_like(clab)
    for label in range(1, n + 1):
        merged[clab == label] = dense[_label_find(label)]
    return merged, len(roots)


def route_overunder(layers, passable, anchors, clab, nclusters, *,
                    bias_fn, bridge_cost=8.0, turn_cost=1.75,
                    chains_out=None, bridge_forbidden=None):
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

    # A cluster with real non-top copper (normally a THT pad or a qualified
    # pickup via) must attach there instead of taking a shorter detour to some
    # broad F.Cu pad cell and paying for an unnecessary layer transition.  The
    # latter leaves the already-created pickup redundant/dangling and defeats
    # the top-copper choke.  Pure F.Cu SMD clusters remain valid F targets.
    non_f_clusters = set()
    for lay in layers:
        if lay == "F.Cu":
            continue
        ys, xs = np.where(anchors[lay])
        non_f_clusters.update(int(clab[y, x]) for y, x in zip(ys, xs)
                              if int(clab[y, x]))

    seed = cluster_ids[0]
    remaining = set(cluster_ids[1:])
    tree = set()                                # {(row, col, layer_idx)}
    path_cells = {lay: np.zeros((ny, nx), bool) for lay in layers}
    for lay in layers:
        if lay == "F.Cu" and seed in non_f_clusters:
            continue
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
            if (cid in remaining and anchors[lay][r, c]
                    and not (lay == "F.Cu" and cid in non_f_clusters)):
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
                if (oli == li or not passable[olay][r, c]
                        or (bridge_forbidden is not None
                            and bridge_forbidden[r, c])):
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
        if chains_out is not None:
            # v4-grade fallback realization (rect covers per same-layer run)
            # needs the ORDERED walks, not just the cell masks
            chains_out.append([(r_, c_, layers[li_]) for (r_, c_, li_)
                               in chain])
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
        # LAYER-SET TOLERANCE (2026-07-25, the 453-crash conviction: the
        # anchor-driven widening can add a layer MID-SEARCH, so a bridge may
        # reference a layer absent from a mask dict built from the
        # pre-widening set -- KeyError 'F.Cu' killed pour_first_stage on
        # every live variant and fail-open silently reverted the whole wave
        # to old machinery). A missing layer gets an empty mask, never a
        # crash.
        for _lay in (lay_from, lay_to):
            if _lay not in path_cells:
                path_cells[_lay] = np.zeros((ny, nx), bool)
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


VIA_R = 0.45             # add_overunder_vias default barrel dia 0.9 / 2
PAD_MARGIN = 0.20        # minimum copper clearance beyond the barrel radius
VIA_LEDGER_MM = 2 * VIA_R + PAD_MARGIN


def _via_ledger_hit(placed, x, y, ledger_mm=VIA_LEDGER_MM):
    """Return true when a 0.9-mm bridge barrel would violate the ledger.

    Two-element entries are legacy 0.9-mm bridge-via centres.  A third value
    carries an existing barrel's radius, allowing larger board vias to expand
    the required centre distance instead of being treated like points.
    """
    for q in placed:
        qx, qy = q[:2]
        qr = float(q[2]) if len(q) > 2 else VIA_R
        required = max(float(ledger_mm), VIA_R + qr + PAD_MARGIN)
        if (x - qx) ** 2 + (y - qy) ** 2 < required ** 2:
            return True
    return False


def bridges_to_vias(bridges, req_w, grid, *, pitch_mm=1.2,
                    ledger_mm=VIA_LEDGER_MM,
                    existing=()):
    """A via-array LINE across each bridge, perpendicular to the path's
    local travel direction, spaced *pitch_mm* apart and spanning the WIDER
    of the two transitioning layers' required widths ('via positions on the
    transition line at 1.2mm pitch', owner v2 design step 4).

    Skips any spot within *ledger_mm* of an entry in *existing* (mm tuples)
    OR of a spot this call already placed for an earlier bridge.  The default
    is the two 0.9-mm barrel radii plus 0.20-mm copper clearance, applied
    cumulatively.  Existing tuples may include a third radius value so larger
    barrels expand the ledger. *req_w* maps a layer name
    to its required width in mm (missing entries fall back to the 1.2mm
    floor). Returns [{'x_mm':, 'y_mm':}] -- the caller stamps 'net'."""
    placed = list(existing)
    out = []
    for (r, c, lay_from, lay_to, dx, dy) in bridges:
        half_w = max(req_w.get(lay_from, 1.2), req_w.get(lay_to, 1.2)) / 2.0
        cx = grid.x0 + (c + 0.5) * grid.cell
        cy = grid.y0 + (r + 0.5) * grid.cell
        # sized by current where the caller knows it, else the width heuristic,
        # capped -- a layer change is a field, not a perforation (owner 2026-07-26)
        n_v = min(FIELD_VIA_CAP, max(1, int(round((2.0 * half_w) / pitch_mm)) + 1))
        perp = (-dy, dx)                        # rotate travel dir by 90
        for k in range(n_v):
            off = (k - (n_v - 1) / 2.0) * pitch_mm
            vx = round(cx + perp[0] * off, 3)
            vy = round(cy + perp[1] * off, 3)
            if _via_ledger_hit(placed, vx, vy, ledger_mm):
                continue
            placed.append((vx, vy))
            out.append({"x_mm": vx, "y_mm": vy})
    return out


def _pad_hit(pad_boxes, x, y, r):
    """Conservative square test: does a circle (x, y, r) overlap any pad
    bbox? (bbox superset of the pad shape; the exact-shape authority is
    cec_fr._via_pad_excluded at lay time)."""
    for (x0, y0, x1, y1) in pad_boxes:
        if x + r >= x0 and x - r <= x1 and y + r >= y0 and y - r <= y1:
            return True
    return False


def footprint_copper_boxes(board, *, is_copper_layer=None):
    """Bounding boxes for netless copper graphics embedded in footprints.

    KiCad footprint graphics can live directly on F.Cu/B.Cu (logos, exposed
    copper artwork, shields, and similar features), but they are not pads and
    therefore never appeared in the over-under via obstacle set.  A generated
    field could consequently pass DRC planning and then drill straight through
    that copper.  Treat these items exactly like other foreign copper.  The
    conservative bounding box is intentional: netless artwork cannot provide
    an electrical landing for a rail via.

    ``is_copper_layer`` is injectable so the geometry rule remains host-testable
    without importing pcbnew.
    """
    if is_copper_layer is None:
        if pcbnew is None:
            return []
        is_copper_layer = pcbnew.IsCopperLayer
    out = []
    for fp in board.GetFootprints():
        try:
            items = fp.GraphicalItems()
        except (AttributeError, TypeError):
            continue
        for item in items:
            try:
                if not is_copper_layer(item.GetLayer()):
                    continue
                bb = item.GetBoundingBox()
                out.append((bb.GetLeft() / MM, bb.GetTop() / MM,
                            bb.GetRight() / MM, bb.GetBottom() / MM))
            except (AttributeError, TypeError, ValueError):
                continue
    return out


def rectilinear_inner(poly, step=0.5, min_keep=0.02, max_pts=160):
    """Largest axis-aligned (Manhattan) approximation CONTAINED IN *poly*.

    Owner 2026-07-25: pours must not be diagonal blobs. A capsule around a
    genuinely diagonal path is diagonal no matter how its caps are joined, so the
    shape is re-expressed as grid-aligned boxes -- and deliberately as an INNER
    approximation: copper may only shrink, never grow into space the path was
    routed around. The cost is bounded by *step* on diagonal edges only; runs that
    were already Manhattan come back unchanged.
    """
    try:
        from shapely.geometry import box as _b
        from shapely.ops import unary_union
    except ImportError:
        return poly
    if poly.is_empty:
        return poly
    x0, y0, x1, y1 = poly.bounds
    nx = max(1, int(math.ceil((x1 - x0) / step)))
    ny = max(1, int(math.ceil((y1 - y0) / step)))
    if nx * ny > 40000:                       # keep it bounded; leave huge shapes alone
        return poly
    keep = []
    for j in range(ny):
        cy0 = y0 + j * step
        cy1 = min(y1, cy0 + step)
        run0 = None
        for i in range(nx + 1):
            inside = False
            if i < nx:
                cx0 = x0 + i * step
                cx1 = min(x1, cx0 + step)
                inside = poly.contains(_b(cx0, cy0, cx1, cy1))
            if inside and run0 is None:
                run0 = x0 + i * step
            elif not inside and run0 is not None:
                keep.append(_b(run0, cy0, x0 + i * step, cy1))
                run0 = None
    if not keep:
        return poly                            # nothing survives: keep the original
    out = unary_union(keep)
    if out.is_empty or out.area < poly.area * min_keep:
        return poly
    # VERTEX BUDGET (2026-07-25): a staircase can carry hundreds of points, and
    # these polygons ride into the DSN as keepouts -- an oversized DSN made
    # Freerouting die with "Network.read_net_scope: unexpected end of file".
    # Too complex to express cheaply -> keep the original shape and say so, which
    # is honest: a diagonal that survives is one the geometry could not simplify.
    try:
        npts = sum(len(g.exterior.coords) for g in getattr(out, "geoms", [out]))
    except Exception:                                      # noqa: BLE001
        return poly
    if npts > max_pts:
        # COARSEN BEFORE SURRENDERING (2026-07-26): one doubling was not enough --
        # the 24-pin's big B.Cu rail regions still blew the budget at 1.0mm and
        # fell back to their original DIAGONAL shape, which is exactly what the
        # owner is looking at. A 2mm staircase on a power pour is a fine shape; a
        # diagonal blob is not. Ladder 0.5 -> 1.0 -> 2.0, then keep the original
        # and let the audit report the residual honestly.
        if step < 2.0:
            return rectilinear_inner(poly, step=min(2.0, step * 2.0),
                                     min_keep=min_keep, max_pts=max_pts)
        return poly
    return out


# VIA AMPACITY, WITH ITS BASIS STATED (owner 2026-07-26: "don't just say it gives
# some amperage without checking it against design spec... plan for worst case").
#
#   VIA_AMPS -- 0.5mm drill / 0.9mm pad carries ~2A at a 10C rise. That is the
#   platform's own figure from the 12VHPWR routing plan (CLAUDE.md), and it is
#   DELIBERATELY CONSERVATIVE against the spec's electrothermal convention, which
#   gates at <=30C rise: the same barrel carries materially more at the gate
#   temperature, so sizing at the 10C figure spends copper to buy margin.
#
#   MARGIN -- the spec's own connector rule, applied here for consistency:
#   "continuous rating >= 125% of sustained worst case at <=30C rise" (§2.8,
#   ratified 2026-07-04). Worst case is the SUSTAINED figure; per the same
#   ruling transients stay transients and are never folded into a continuous
#   rating.
#
# The CURRENT must come from the design basis, never a code default. For this
# platform the spec anchors are:
#   * 24-pin power rails -- the 6A/circuit ATX bar is PER CIRCUIT, not the rail
#     total (owner correction 2026-07-26: "we have two blades, because I have
#     seen much more amperage than that"). The RAIL is what crosses a layer, and
#     the ratified joint counts say so: the 2026-07-06 re-ratification on the TE
#     63969-1 (22.9A at 125% = 18.32A/joint) gives atx24 TEN joints with
#     3V3 x2 -- two blades, so 3.3V sustained worst case exceeds one joint's
#     18.32A. Three ATX 3.3V circuits x the 6A bar ~= 18A is the working rail
#     figure, consistent with two blades and with real PSUs' 20-24A 3.3V rating.
#     My first pass read the per-circuit 6A as the rail and undersized it.
#   * the module's OWN +3V3 logic rail -- bounded by its source, the LP5907 LDO
#     at 250mA maximum per the TI datasheet (spec Hub regulator row). 0.25A.
#     This is the net in the owner's 29-via screenshot: worst case a quarter of
#     an amp, sized as if it were a power bus.
#   * EPS ~13A/pin -> ~52A/cable, PCIe ~39A/cable, 12VHPWR per-pin (§2.8).
# NOTE (surfaced, not silently patched): cec_synth_pipeline._net_currents gives
# any net matching "3V3" a flat 0.8A default, which matches NEITHER anchor -- it
# is 3.2x the LDO ceiling for the logic rail and 7.5x too small for a 6A ATX
# circuit. Sizing anything from that default is guesswork; see docs/owner-queue.md.
VIA_AMPS = 2.0              # 0.5/0.9mm barrel @ 10C rise (platform figure)
MARGIN = 1.25               # spec §2.8 continuous-rating policy
FIELD_VIA_CAP = 12          # a layer change, not a perforation


def vias_for_current(amps, *, redundancy=1):
    """Barrels to carry *amps* SUSTAINED at the spec's 125% margin, plus a spare.

    Worked against the spec anchors:
      +3V3 logic rail   0.25A (LDO ceiling)  -> 1.25*0.25/2   = 1 -> 2 with spare
      24-pin 3.3V RAIL  ~18A (3 circuits)    -> 1.25*18/2     = 12 -> the cap
      one 24-pin circuit  6A  (the ATX bar)   -> 1.25*6/2      = 4 -> 5 with spare
      EPS cable         52A                  -> capped at the field cap, and a
                                                52A crossing wants a planned
                                                transition, not a via field.
    """
    import math as _m
    if not amps or amps <= 0:
        return 2
    need = int(_m.ceil((MARGIN * float(amps)) / VIA_AMPS)) + redundancy
    return max(2, min(FIELD_VIA_CAP, need))


def field_via_line(field6, half_w, grid, pad_boxes, placed, *, pitch_mm=1.2,
                   ledger_mm=VIA_LEDGER_MM, n_needed=None, pad_allow=None,
                   via_allow=None):
    """Via positions for ONE compact field: a roughly square ARRAY centred on
    the transition (owner ruling 2026-07-25 -- a layer change is one via array,
    not a fence across the corridor), each slot checked against the barrel
    ledger AND the
    assembly-class pad exclusion (via-in-pad ruling, owner 2026-07-25); a
    blocked slot SLIDES outward along the same line. Shared by the v4
    planner (cec_pour_plan._field_vias) and the rect-realized fallback
    (realize_overunder_rects) so the two via disciplines can never drift.
    Returns ([(x, y)], reseated_count); [] = honest total failure."""
    (r, c, _lf, _lt, dx, dy) = field6[:6]
    cx = grid.x0 + (c + 0.5) * grid.cell
    cy = grid.y0 + (r + 0.5) * grid.cell
    # SIZED BY CURRENT, NOT BY CORRIDOR WIDTH (owner 2026-07-26: "does 3v3 really
    # need this massive of a via array? That's a bit ridiculous"). It did not: this
    # formula gave +3V3 -- a 0.8A rail needing ONE barrel -- a 29-via block, because
    # a corridor is wide for ampacity, reach and min-width reasons that have nothing
    # to do with how much copper must cross a layer change. A caller that knows the
    # net's current passes n_needed; otherwise the heuristic stands but is capped.
    n_v = (int(n_needed) if n_needed
           else min(FIELD_VIA_CAP, max(1, int(round((2.0 * half_w) / pitch_mm)) + 1)))
    perp = (-dy, dx)

    # ONE COMPACT ARRAY, NOT A FULL-WIDTH LINE (owner ruling 2026-07-25: "it
    # should concentrate them at one via array spot to do a layer change...
    # instead of going ham on them"). The barrel COUNT is ampacity -- it stays
    # exactly as computed -- but the ARRANGEMENT was a single row spanning the
    # corridor's whole width, so an ampacity-driven rail corridor produced the
    # measured 22-via row spanning 1.6..37.0mm on /SENSE3V3_HI: half the board.
    # The same barrels now pack into a roughly square array centred on the
    # transition, laid perp-major so it still presents its widest face to the
    # arriving copper. Electrically identical (same barrels, same pitch),
    # geometrically a via array instead of a fence.
    n_cols = max(1, int(round(n_v ** 0.5)))
    n_rows = max(1, -(-n_v // n_cols))                 # ceil
    slots = []                                          # (perp_offset, along_offset)
    for j in range(n_rows):
        a = (j - (n_rows - 1) / 2.0) * pitch_mm
        for i in range(n_cols):
            slots.append(((i - (n_cols - 1) / 2.0) * pitch_mm, a))
    slots.sort(key=lambda t: (abs(t[1]), abs(t[0])))
    # spare ring for blocked slots: widen the array a little, never into a fence
    extra_cap = max(pitch_mm, min(2.5 * pitch_mm, half_w))
    k = 1
    while len(slots) < n_v * 3:
        ring = []
        for j in range(-n_rows, n_rows + 1):
            for i in range(-n_cols - k, n_cols + k + 1):
                px, ay = i * pitch_mm, j * pitch_mm
                if abs(px) <= (n_cols / 2.0) * pitch_mm + k * extra_cap:
                    ring.append((px, ay))
        if not ring:
            break
        slots.extend(ring)
        k += 1
        if k > 3:
            break
    out = []
    reseated = 0
    for (sp, sa) in slots:
        if len(out) >= n_v:
            break
        vx = round(cx + perp[0] * sp + dx * sa, 3)
        vy = round(cy + perp[1] * sp + dy * sa, 3)
        if _via_ledger_hit(list(placed) + out, vx, vy, ledger_mm):
            continue
        if (_pad_hit(pad_boxes, vx, vy, VIA_R + PAD_MARGIN)
                and not (pad_allow and pad_allow(vx, vy))):
            reseated += 1                  # blocked slot -> keep sliding
            continue
        if via_allow is not None and not via_allow(vx, vy):
            reseated += 1
            continue
        out.append((vx, vy))
    reseated = reseated if out else 0
    return out, reseated


def _chain_runs(chain):
    """Split one ordered (row, col, layer) walk into maximal same-layer runs
    [(layer, [(r, c), ...]), ...]."""
    runs = []
    for (r, c, lay) in chain:
        if runs and runs[-1][0] == lay:
            runs[-1][1].append((r, c))
        else:
            runs.append((lay, [(r, c)]))
    return runs


def _run_polyline(cells, grid):
    """Cell centers -> collinear-simplified mm polyline (direction-change
    vertices only; the direction-state Dijkstra's turn tax keeps runs
    straight, so this is a handful of points per run)."""
    pts = [(grid.x0 + (c + 0.5) * grid.cell, grid.y0 + (r + 0.5) * grid.cell)
           for (r, c) in cells]
    if len(pts) <= 2:
        return pts
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        ax, ay = out[-1]
        bx, by = pts[i]
        cx, cy = pts[i + 1]
        if abs((bx - ax) * (cy - ay) - (by - ay) * (cx - ax)) > 1e-9:
            out.append(pts[i])
    out.append(pts[-1])
    return out


def _l_simplify(cells, free, grid):
    """Turn a staircase run into an L when the L is legal (owner 2026-07-26:
    the pours "are still diagonal" -- Manhattan EDGES were not enough while the
    PATH still walks a diagonal as steps).

    A run's copper should be one or two straight legs, not a stair. Both L
    variants between the run's endpoints are tested cell-by-cell against the
    same free mask the search used; the first legal one wins, otherwise the
    original walk is kept. Never widens the search's own freedom -- it only
    straightens inside space the search already proved free."""
    if free is None or len(cells) < 3:
        return cells
    (r0, c0), (r1, c1) = cells[0], cells[-1]
    if r0 == r1 or c0 == c1:
        return cells                                    # already straight
    def _inclusive(a, b):
        """Ordered inclusive integer walk from *a* to *b*."""
        step = 1 if b >= a else -1
        return range(a, b + step, step)

    # Preserve traversal order and, critically, both original endpoints.
    # The former second-corner construction started at (r1,c0), then walked
    # back to (r0,c0), and ended at (r1,c0).  Its geometry could pass the
    # free-mask check while silently dropping the real destination terminal;
    # the search reported path_found even though the realized pour stopped
    # millimetres short of its connector manifold.  Spell the two candidates
    # as ordered horizontal-then-vertical / vertical-then-horizontal walks.
    candidates = [
        ([(r0, c) for c in _inclusive(c0, c1)]
         + [(r, c1) for r in _inclusive(r0, r1)][1:]),
        ([(r, c0) for r in _inclusive(r0, r1)]
         + [(r1, c) for c in _inclusive(c0, c1)][1:]),
    ]
    for leg in candidates:
        try:
            if all(free[r][c] for (r, c) in leg):
                return leg
        except (IndexError, TypeError):
            continue
    return cells


def realize_overunder_rects(chains, bridges, reqw, grid, *, pad_boxes=(),
                            existing_vias=(), f_admit=None, free_masks=None,
                            clip_masks=None, holes_out=None,
                            pitch_mm=1.2, ledger_mm=VIA_LEDGER_MM,
                            pad_allow=None, via_allow=None,
                            strict_bridges=False):
    """v4-GRADE FALLBACK REALIZATION (mandate part 3, 2026-07-25): the path
    stays the search's; the copper is DRAWN geometry -- one straight capsule
    cover per maximal same-layer run (collinear-simplified centerline at
    that layer's required width) + ONE compact pad-aware via field per
    genuine layer change at the run boundary, each field embedded by a
    cover box on both transitioning layers. Replaces the dilated-cell smear
    (3-cell bridge disks + closing -> the owner's "amorphous blobs / giant
    via lines" on s510-class boards).

    *f_admit* -- optional list of (x0, y0, x1, y1) F.Cu admit boxes (shunt
    neighborhoods + own manifolds): F run pieces are clipped to their union
    (the add_power_pours choke would refuse them anyway -- clipping here is
    the same rule applied at draw time, loud via the returned notes).

    *clip_masks* -- optional per-layer final corridor masks.  The vector
    capsules and bridge landings are intersected with their exact raster
    cover before export.  This reapplies the search's foreign-pad/track/via
    mask after widening the centerline; without it a legal centerline could
    grow sideways over an obstacle that the search itself correctly blocked.

    *holes_out* -- optional dict populated as ``(layer, polygon_index) ->
    [hole_ring, ...]``.  The public polygon return remains backwards
    compatible, while pour callers can preserve an obstacle wholly enclosed
    by a lane instead of discarding its interior ring.

    Returns (polys_by_layer, via_pts, notes):
      polys_by_layer: {layer: [[(x, y), ...], ...]} exterior coord lists
      via_pts:        [(x, y), ...] ledger/pad-clear via positions
      notes:          human-readable drops/reseats."""
    from shapely.geometry import LineString, Point, box as _sbox
    from shapely.ops import unary_union
    lay_geoms = {}
    landing_geoms = {}
    notes = []
    admit = (unary_union([_sbox(*b) for b in f_admit])
             if f_admit else None)
    for chain in chains:
        for (lay, cells) in _chain_runs(chain):
            simplify_mask = (free_masks or {}).get(lay)
            final_mask = (clip_masks or {}).get(lay)
            if simplify_mask is not None and final_mask is not None:
                # The clean L is a new route, not just a prettier rendering of
                # the old staircase.  It must therefore remain inside the
                # final admitted corridor that clips the vector geometry
                # below.  Checking only broad free space can choose an L that
                # is legal in isolation but then gets cut into disconnected
                # islands by the old staircase-shaped clip mask.
                simplify_mask = simplify_mask & final_mask
            cells = _l_simplify(cells, simplify_mask, grid)
            pts = _run_polyline(cells, grid)
            half = max(0.3, reqw.get(lay, 1.2) / 2.0)
            # SQUARE CAPS / MITRED JOINS, same reason as cec_pour_plan._capsule
            # (owner 2026-07-25 "diagonal blobs"): a round buffer facets every
            # corner and end into short diagonals. A Manhattan run now yields an
            # exactly rectilinear capsule; a diagonal run still reads diagonal,
            # which is the path telling the truth rather than rounding hiding it.
            if len(pts) == 1:
                g = Point(pts[0]).buffer(half, cap_style=3, join_style=2,
                                         mitre_limit=4.0)
            else:
                g = LineString(pts).buffer(half, cap_style=3, join_style=2,
                                           mitre_limit=4.0)
                if any(abs(b[0] - a[0]) > 1e-6 and abs(b[1] - a[1]) > 1e-6
                       for a, b in zip(pts, pts[1:])):
                    g = rectilinear_inner(g)      # diagonal run -> Manhattan copper
            if lay == "F.Cu" and admit is not None:
                clipped = g.intersection(admit)
                if clipped.is_empty:
                    notes.append("F run at (%.1f,%.1f) outside the top-copper"
                                 " admit -- dropped (choke rule, draw-time)"
                                 % pts[0])
                    continue
                if clipped.area < g.area - 1e-6:
                    notes.append("F run at (%.1f,%.1f) clipped to the "
                                 "top-copper admit" % pts[0])
                g = clipped
            lay_geoms.setdefault(lay, []).append(g)
    # ONE compact via field per bridge, pad-aware + ledgered, embedded by a
    # cover box on both transitioning layers
    placed = list(existing_vias)
    via_pts = []
    from shapely.geometry import box as _sbox2
    for f in bridges:
        (r, c, lf, lt, dx, dy) = f[:6]
        fcx = grid.x0 + (c + 0.5) * grid.cell
        fcy = grid.y0 + (r + 0.5) * grid.cell
        # The search and drawing stages must use the same F.Cu admission
        # contract.  Keeping a via field after dropping its F landing is not a
        # degraded route; it is a one-layer-connected barrel array.  Refuse the
        # whole bridge when a caller supplies inconsistent geometry.
        if ("F.Cu" in {lf, lt} and admit is not None
                and not admit.buffer(1e-6).covers(Point(fcx, fcy))):
            msg = ("bridge at cell (%d,%d) has no admitted F.Cu landing"
                   % (r, c))
            if strict_bridges:
                raise RuntimeError(msg)
            notes.append(msg + " -- whole bridge dropped")
            continue
        half_w = max(reqw.get(lf, 1.2), reqw.get(lt, 1.2)) / 2.0
        vs, rs = field_via_line(f, half_w, grid, pad_boxes, placed,
                                pitch_mm=pitch_mm, ledger_mm=ledger_mm,
                                pad_allow=pad_allow, via_allow=via_allow)
        if not vs:
            # The path search proves copper-cell freedom but historically did
            # not include the diameter-aware barrel ledger.  A transition cell
            # can therefore be legal for copper yet have every compact field
            # slot blocked by existing vias or pads.  Reseat the transition a
            # few cells along a straight, both-layer-free spur; the landing box
            # below bonds the shifted field back to the original run boundary.
            def _cell_free(rr, cc):
                for layer in (lf, lt):
                    mask = (free_masks or {}).get(layer)
                    if mask is None:
                        continue
                    if (rr < 0 or cc < 0 or rr >= mask.shape[0]
                            or cc >= mask.shape[1] or not mask[rr, cc]):
                        return False
                x = grid.x0 + (cc + 0.5) * grid.cell
                y = grid.y0 + (rr + 0.5) * grid.cell
                if ("F.Cu" in {lf, lt} and admit is not None
                        and not admit.buffer(1e-6).covers(Point(x, y))):
                    return False
                return via_allow is None or via_allow(x, y)

            def _spur_free(rr, cc):
                dr = 0 if rr == r else (1 if rr > r else -1)
                dc = 0 if cc == c else (1 if cc > c else -1)
                cr, cc_ = r, c
                while (cr, cc_) != (rr, cc):
                    cr += dr
                    cc_ += dc
                    if not _cell_free(cr, cc_):
                        return False
                return True

            for radius in range(1, 5):
                found = False
                for dr, dc in ((0, -radius), (0, radius),
                               (-radius, 0), (radius, 0)):
                    rr, cc = r + dr, c + dc
                    if not _spur_free(rr, cc):
                        continue
                    shifted = (rr, cc, lf, lt, dx, dy)
                    shifted_vs, shifted_rs = field_via_line(
                        shifted, half_w, grid, pad_boxes, placed,
                        pitch_mm=pitch_mm, ledger_mm=ledger_mm,
                        pad_allow=pad_allow, via_allow=via_allow)
                    if not shifted_vs:
                        continue
                    vs, rs = shifted_vs, shifted_rs
                    notes.append(
                        "bridge at cell (%d,%d) field reseated to (%d,%d) "
                        "for diameter-aware ledger clearance"
                        % (r, c, rr, cc))
                    found = True
                    break
                if found:
                    break
        if not vs:
            msg = ("bridge at cell (%d,%d) placed NO via (ledger + pad "
                   "exclusion exhausted every slot)" % (r, c))
            if strict_bridges:
                raise RuntimeError(msg)
            notes.append(msg)
            continue
        if rs:
            notes.append("bridge at cell (%d,%d): %d slot(s) reseated "
                         "past pads" % (r, c, rs))
        placed.extend(vs)
        via_pts.extend(vs)
        qs = list(vs) + [(fcx, fcy)]
        cover = _sbox2(min(q[0] for q in qs) - 0.5, min(q[1] for q in qs) - 0.5,
                       max(q[0] for q in qs) + 0.5, max(q[1] for q in qs) + 0.5)
        for lay in {lf, lt}:
            # A current-sized compact field needs copper under every barrel on
            # both endpoint layers.  Its transition centre was admitted by the
            # same mask as the search above, and pad/graphic/edge obstacles have
            # already reseated the individual barrels.  Clipping this landing
            # back to the path mask can strand the outer rows of the field.
            # Keep the pad-aware bridge landing separate from route lanes.
            # The corridor clip is a centreline/width guard; applying it to a
            # field that deliberately reseated barrels around pads removes
            # copper from outer rows and creates one-layer dangling vias. The
            # compact cover is already pad/via/edge checked slot-by-slot, and
            # KiCad's filler performs the final exact foreign-copper carve.
            landing_geoms.setdefault(lay, []).append(cover)
    out = {}
    for lay, gs in lay_geoms.items():
        u = unary_union([g for g in gs if not g.is_empty])
        clip = (clip_masks or {}).get(lay)
        if clip is not None:
            allowed = unary_union([_sbox(*rect)
                                   for rect in _mask_rects(clip, grid)])
            u = u.intersection(allowed)
        if landing_geoms.get(lay):
            u = unary_union([u] + landing_geoms[lay])
        polys = []
        for g in getattr(u, "geoms", [u]):
            if g.geom_type != "Polygon" or g.area < 0.4:
                continue
            polys.append([(round(x, 3), round(y, 3))
                          for (x, y) in g.exterior.coords])
            holes = [[(round(x, 3), round(y, 3))
                      for (x, y) in ring.coords]
                     for ring in g.interiors]
            if holes and holes_out is not None:
                holes_out[(lay, len(polys) - 1)] = holes
        if polys:
            out[lay] = polys
    return out, via_pts, notes


def _clip_pours_around_generated_vias(pours, vias, *, clearance_mm=0.3):
    """Subtract every foreign-net generated barrel from the returned outlines.

    Each net is solved in sequence so a later net can avoid earlier bridge
    barrels, but an earlier outline cannot know where a later bridge will land.
    KiCad's filler would clear that barrel in the filled copper, yet the saved
    zone outline would still contain it -- precisely the phantom-slab contract
    failure the materialization conformance gate is meant to reject. Resolve
    the batch symmetrically after all via locations are known.
    """
    if not pours or not vias:
        return list(pours), 0

    from shapely.geometry import Point, Polygon
    from shapely.ops import unary_union

    cuts_by_owner = {}
    for via in vias:
        owner = via.get("net")
        if not owner:
            continue
        cut = Point(float(via["x_mm"]), float(via["y_mm"])).buffer(
            VIA_R + float(clearance_mm), resolution=12)
        cuts_by_owner.setdefault(owner, []).append(cut)
    all_owners = tuple(cuts_by_owner)

    out = []
    clipped = 0
    for row in pours:
        foreign = [cut for owner in all_owners if owner != row.get("net")
                   for cut in cuts_by_owner[owner]]
        if not foreign:
            out.append(row)
            continue
        geom = Polygon(row["polygon"], row.get("holes") or ()).buffer(0)
        result = geom.difference(unary_union(foreign))
        pieces = [result] if result.geom_type == "Polygon" else list(
            getattr(result, "geoms", ()))
        valid = [piece for piece in pieces
                 if piece.geom_type == "Polygon" and piece.area >= 0.4]
        if result.equals(geom):
            out.append(row)
            continue
        clipped += 1
        for piece in valid:
            revised = dict(row)
            revised["polygon"] = [(round(x, 3), round(y, 3))
                                  for x, y in piece.exterior.coords]
            holes = [[(round(x, 3), round(y, 3)) for x, y in ring.coords]
                     for ring in piece.interiors]
            if holes:
                revised["holes"] = holes
            else:
                revised.pop("holes", None)
            out.append(revised)
    return out, clipped


def _clip_pours_around_foreign_copper(board, pours, *, clearance_mm=0.25):
    """Subtract real foreign pads/tracks/vias from saved pour *outlines*.

    KiCad's filler automatically creates antipads in the rendered copper, but
    leaving the foreign object inside the zone outline violates the pipeline's
    pour-first ownership contract and makes guarded post-route helpers treat a
    visually empty antipad as reserved copper. Clip the vector source itself so
    FEM, conformance, routing guards, and fabricated fill all describe the same
    geometry. Same-net copper remains available as an anchor.

    Bounding rectangles are deliberately conservative for pads and uncommon
    track shapes; ordinary tracks and vias use their actual centerline/diameter.
    Returns ``(revised_pours, number_of_source_outlines_clipped)``.
    """
    if not pours:
        return [], 0

    from shapely.geometry import LineString, Point, Polygon, box as _sbox
    from shapely.ops import unary_union

    clearance = float(clearance_mm)
    enabled = set(board.GetEnabledLayers().CuStack())
    pads = []
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            if not pad.GetNetname():
                continue
            bb = pad.GetBoundingBox()
            layers = tuple(layer for layer in pad.GetLayerSet().CuStack()
                           if layer in enabled)
            pads.append((pad.GetNetname(), layers,
                         _sbox(bb.GetLeft() / MM - clearance,
                               bb.GetTop() / MM - clearance,
                               bb.GetRight() / MM + clearance,
                               bb.GetBottom() / MM + clearance)))

    copper = []
    for item in board.GetTracks():
        net = item.GetNetname()
        if not net:
            continue
        if item.GetClass() == "PCB_VIA":
            pos = item.GetPosition()
            radius = item.GetWidth(item.TopLayer()) / MM / 2.0 + clearance
            geom = Point(pos.x / MM, pos.y / MM).buffer(radius, resolution=12)
            layers = tuple(layer for layer in item.GetLayerSet().CuStack()
                           if layer in enabled)
        elif item.GetClass() == "PCB_TRACK":
            start, end = item.GetStart(), item.GetEnd()
            radius = item.GetWidth() / MM / 2.0 + clearance
            geom = LineString(((start.x / MM, start.y / MM),
                               (end.x / MM, end.y / MM))).buffer(
                                   radius, cap_style=2, join_style=2)
            layers = (item.GetLayer(),)
        else:
            bb = item.GetBoundingBox()
            geom = _sbox(bb.GetLeft() / MM - clearance,
                         bb.GetTop() / MM - clearance,
                         bb.GetRight() / MM + clearance,
                         bb.GetBottom() / MM + clearance)
            layers = tuple(layer for layer in item.GetLayerSet().CuStack()
                           if layer in enabled)
        copper.append((net, layers, geom))

    out = []
    clipped = 0
    for row in pours:
        layer = board.GetLayerID(row.get("layer", "F.Cu"))
        net = row.get("net")
        foreign = [geom for owner, layers, geom in pads + copper
                   if owner != net and layer in layers]
        if not foreign:
            out.append(row)
            continue
        source = Polygon(row.get("polygon") or (), row.get("holes") or ()).buffer(0)
        revised_geom = source.difference(unary_union(foreign))
        if revised_geom.equals(source):
            out.append(row)
            continue
        clipped += 1
        pieces = ([revised_geom] if revised_geom.geom_type == "Polygon" else
                  list(getattr(revised_geom, "geoms", ())))
        for piece in pieces:
            if piece.geom_type != "Polygon" or piece.area < 0.4:
                continue
            revised = dict(row)
            revised["polygon"] = [(round(x, 3), round(y, 3))
                                  for x, y in piece.exterior.coords]
            holes = [[(round(x, 3), round(y, 3)) for x, y in ring.coords]
                     for ring in piece.interiors]
            if holes:
                revised["holes"] = holes
            else:
                revised.pop("holes", None)
            out.append(revised)
    return out, clipped


def _stamp_generated_via_keepouts(mask, grid, vias, net, clearance_mm=0.3):
    """Reserve earlier generated through-vias in a later rail's search mask.

    Over-under nets are solved sequentially without adding their barrels to the
    board between solves.  ``rasterize`` therefore cannot see an earlier net's
    bridge field.  If a later path crosses one, the final symmetric via clip
    cuts a gap through an otherwise valid corridor.  Stamp those real planned
    barrels as foreign copper before erosion so the later route detours around
    them instead of being severed after the fact.
    """
    stamped = 0
    for via in vias or ():
        if via.get("net") == net:
            continue
        radius = float(via.get("radius_mm", VIA_R)) + float(clearance_mm)
        x, y = float(via["x_mm"]), float(via["y_mm"])
        grid.stamp_box(mask, x - radius, y - radius,
                       x + radius, y + radius)
        stamped += 1
    return stamped


def _stamp_generated_pour_keepouts(mask, grid, pours, net, layer,
                                   clearance_mm=0.3):
    """Reserve already allocated foreign rail copper in a later search.

    Generated zones are returned as dictionaries and are not added to the
    pcbnew board until the complete batch has been solved.  Consequently the
    ordinary board raster cannot see an earlier rail or connector manifold.
    Rasterize those planned outlines explicitly so sequential allocation has
    the same foreign-copper contract as allocation against the source board.
    """
    from shapely.geometry import Polygon
    from shapely.vectorized import contains

    stamped = 0
    cell_halo = grid.cell * math.sqrt(2.0) / 2.0
    xs_all = grid.x0 + (np.arange(grid.nx) + 0.5) * grid.cell
    ys_all = grid.y0 + (np.arange(grid.ny) + 0.5) * grid.cell
    for pour in pours or ():
        if (pour.get("net") == net
                or (layer is not None and pour.get("layer") != layer)):
            continue
        geom = Polygon(pour.get("polygon") or (),
                       pour.get("holes") or ()).buffer(0)
        if geom.is_empty:
            continue
        # Expanding by half a cell diagonal makes centre sampling conservative:
        # every raster cell touched by the clearance-expanded copper is marked.
        geom = geom.buffer(float(clearance_mm) + cell_halo, join_style=2)
        x0, y0, x1, y1 = geom.bounds
        i0 = max(0, int(math.floor((x0 - grid.x0) / grid.cell - 0.5)))
        i1 = min(grid.nx - 1,
                 int(math.ceil((x1 - grid.x0) / grid.cell - 0.5)))
        j0 = max(0, int(math.floor((y0 - grid.y0) / grid.cell - 0.5)))
        j1 = min(grid.ny - 1,
                 int(math.ceil((y1 - grid.y0) / grid.cell - 0.5)))
        if i1 < i0 or j1 < j0:
            continue
        xx, yy = np.meshgrid(xs_all[i0:i1 + 1], ys_all[j0:j1 + 1])
        mask[j0:j1 + 1, i0:i1 + 1] |= contains(geom, xx, yy)
        stamped += 1
    return stamped


def _prep_overunder_net(board, net, nc, ask_layers, grid, *, net_currents,
                        shunt_mask, clearance_mm=0.3, manifolds=(),
                        generated_vias=(), generated_pours=()):
    """Shared per-net SEARCH PREP for the over-under machinery -- extracted
    2026-07-25 (pre-FR corridor reservation, docs/slab-pour-design-2026-07-24.md
    priority ruling) so `synthesize_overunder_pours` (post-route realization)
    and `reserve_pour_corridors` (pre-route reservation) run the IDENTICAL
    terminal-cluster + eroded-mask + bias construction: reserved corridors must
    predict realized lanes, so the two may never drift.

    *ask_layers* is the ask's OWN layer list (before the power/fallback union --
    applied here, matching the ask-channel contract documented on
    `synthesize_overunder_pours`). Returns ``(prep, None)`` on success --
    prep = {layers, passable, anchors, foreign, clab, nclusters, rcells,
    reqw, bias_fn} (foreign = the raw rasterize() masks incl. clearance,
    kept for the reservation's corridor-carve) -- or ``(None, reason_str)``
    on the two honest no-search cases ("no valid layer" / "no pads/vias for
    net"), byte-identical to the report reasons the realization always used."""
    from scipy import ndimage
    st = ndimage.generate_binary_structure(2, 1)
    raw_policy = [x.strip() for x in
                  os.environ.get("CEC_POWER_POUR_LAYERS", "").split(",")
                  if x.strip() in fab.COPPER_LAYERS]
    profile_name = fab.active_profile_name(
        board, hint=os.environ.get("CEC_THERMAL_BOARD_HINT", ""))
    fallbacks = (raw_policy or
                 (["In3.Cu", "B.Cu", "In2.Cu"] if profile_name
                  else ["In2.Cu", "B.Cu"]))
    layers = list(dict.fromkeys(list(ask_layers) + list(fallbacks)))
    enabled = set(fab.enabled_copper_layers(board))
    layers = [lay for lay in layers if lay in enabled]
    if not layers:
        return None, "no valid layer"

    # step 1: terminal groups
    clab, nclusters = terminal_clusters(board, nc, grid)
    if nclusters == 0:
        return None, "no pads/vias for net"

    # step 2: per-layer eroded/passable masks + required width
    amps = net_currents.get(net, 0.0)
    bridge_forbidden = np.zeros((grid.ny, grid.nx), bool)
    _stamp_generated_pour_keepouts(
        bridge_forbidden, grid, generated_pours, net, None, clearance_mm)
    passable, anchors, rcells, reqw, foreign = {}, {}, {}, {}, {}
    for lay in layers:
        lay_id = board.GetLayerID(lay)
        fmask, anc = rasterize(board, nc, lay_id, grid, clearance_mm)
        _stamp_generated_via_keepouts(
            fmask, grid, generated_vias, net, clearance_mm)
        _stamp_generated_pour_keepouts(
            fmask, grid, generated_pours, net, lay, clearance_mm)
        w = req_width_mm(amps, lay, board=board) if amps > 0 else 1.2
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
        if extra in passable or extra not in enabled:
            continue
        uncov = [k for k in range(1, nclusters + 1)
                 if not any((anchors[lay] & (clab == k)).any()
                            for lay in layers)]
        if not uncov:
            break
        fmask, anc = rasterize(board, nc, board.GetLayerID(extra),
                               grid, clearance_mm)
        _stamp_generated_via_keepouts(
            fmask, grid, generated_vias, net, clearance_mm)
        _stamp_generated_pour_keepouts(
            fmask, grid, generated_pours, net, extra, clearance_mm)
        helped = [k for k in uncov if (anc & (clab == k)).any()]
        if not helped:
            continue
        w = req_width_mm(amps, extra, board=board) if amps > 0 else 1.2
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
    f_admit_mask = None
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
        # Preserve the exact post-foreign, post-choke search mask for the draw
        # stage.  Rebuilding admission later from only shunt/manifold boxes
        # omitted the short landing regions around ordinary F.Cu anchors.
        f_admit_mask = passable["F.Cu"].copy()
    f_prox = None
    if "F.Cu" in anchors:
        f_prox = ndimage.binary_dilation(anchors["F.Cu"], structure=st,
                                         iterations=2)

    preferred_power = fallbacks[0]

    def _bias(lay, r, c, _shunt=shunt_mask, _fprox=f_prox,
              _preferred=preferred_power):
        # per-layer bias (design step 3): preferred power layer +0, other
        # non-top layers +0.15/step,
        # F.Cu +0.6/step EXCEPT free inside a shunt neighborhood or
        # within 2 cells of this net's own F-anchored terminal.
        if lay == "F.Cu":
            if _shunt[r, c] or (_fprox is not None and _fprox[r, c]):
                return 1.0
            return 1.6
        return 1.0 + (0.0 if lay == _preferred else 0.15)

    return {"layers": layers, "passable": passable, "anchors": anchors,
            "foreign": foreign, "clab": clab, "nclusters": nclusters,
            "rcells": rcells, "reqw": reqw, "bias_fn": _bias,
            "attach_notes": attach_notes, "f_admit_mask": f_admit_mask,
            "bridge_forbidden": bridge_forbidden}, None


def synthesize_overunder_pours(board, asks, *, cell_mm=0.8, clearance_mm=0.3,
                               manifolds=False, collect=None,
                               manifold_dicts=None):
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
    `layers` (or `layer`, default "F.Cu") UNIONED with the active board
    profile's power and fallback routing layers -- an ask that
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
    _cfg = _board_thermal_config(board)
    net_currents = dict((_cfg[0] if _cfg else None) or {})

    # shunt neighborhoods, once (the F.Cu bias input -- design step 3's
    # "free inside shunt neighborhoods")
    shunt_mask = np.zeros((grid.ny, grid.nx), bool)
    for (x0, y0, x1, y1) in shunt_neighborhoods(board):
        grid.stamp_box(shunt_mask, x0, y0, x1, y1)

    # Existing board vias, once.  Preserve each radius so a larger barrel
    # expands the generated bridge-via clearance ledger.
    existing_vias_mm = []
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA":
            p = t.GetPosition()
            existing_vias_mm.append(
                (p.x / MM, p.y / MM, t.GetWidth(pcbnew.F_Cu) / MM / 2.0))

    pour_dicts, via_list, report = [], [], {}
    planned_bridge_vias = []
    planned_pours = []

    # v3.1 stage 0: connector manifolds -- LAID FIRST (they lead the dict
    # list) and handed to every net's search as attach targets.
    # *manifold_dicts* (2026-07-25, planner-fallback quality): a caller that
    # ALREADY laid the manifolds (cec_pour_plan stage 0) passes them here so
    # the search keeps the width-margin attach WITHOUT re-laying/duplicating
    # the dicts (they are attach inputs only, never re-returned).
    man_by_net = {}
    if manifold_dicts:
        for md in manifold_dicts:
            if md.get("net") in nets_nc:
                man_by_net.setdefault(md["net"], []).append(md)
                planned_pours.append(md)
    elif manifolds:
        _ask_nets = {a.get("net") for a in asks if a.get("net") in nets_nc}
        for md in connector_manifolds(board, nets=_ask_nets):
            man_by_net.setdefault(md["net"], []).append(md)
        for _mn in sorted(man_by_net):
            pour_dicts.extend(man_by_net[_mn])
            planned_pours.extend(man_by_net[_mn])
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
            clearance_mm=clearance_mm, manifolds=man_by_net.get(net, ()),
            generated_vias=planned_bridge_vias, generated_pours=planned_pours)
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
        chains = []
        path_cells, bridges, ok, bottleneck = route_overunder(
            prep["layers"], prep["passable"], prep["anchors"], prep["clab"],
            prep["nclusters"], bias_fn=prep["bias_fn"], chains_out=chains,
            bridge_forbidden=prep["bridge_forbidden"])
        if collect is not None:
            collect[net] = {"ok": ok, "path_cells": path_cells,
                            "bridges": bridges, "rcells": prep["rcells"],
                            "foreign": prep["foreign"], "reqw": prep["reqw"]}

        _man_rep = ({"manifolds": len(man_by_net.get(net, ())),
                     "manifold_attach": prep.get("attach_notes")}
                    if (manifolds or manifold_dicts) else {})
        if not ok:
            report[net] = {"path_found": False, "segments": 0, "bridges": 0,
                           "layers_used": [], "bottleneck": bottleneck,
                           **_man_rep}
            print(f"[cec_slab_pour] over-under: NO PATH for {net} -- "
                  f"bottleneck {bottleneck}", file=sys.stderr)
            continue

        # step 4: realize (lanes + bridge vias). DEFAULT = the v4-grade RECT
        # realization (mandate part 3, 2026-07-25): straight capsule covers
        # per same-layer run + ONE compact pad-aware via field per layer
        # change -- the dilated-cell smear (3-cell bridge disks + closing =
        # the owner's "amorphous blobs / via lines") survives only behind
        # CEC_OU_SMEAR=1 as the A/B escape hatch.
        _realize_masks = corridor_masks(
            path_cells, bridges, rcells, prep["foreign"], grid,
            margin_cells=0)
        _realized_holes = {}
        if os.environ.get("CEC_OU_SMEAR") == "1":
            # The legacy shape stays available for A/B, but it must obey the
            # same foreign-obstacle mask as every other realization.
            realized = {
                lay: [[(round(x0, 3), round(y0, 3)),
                       (round(x1, 3), round(y0, 3)),
                       (round(x1, 3), round(y1, 3)),
                       (round(x0, 3), round(y1, 3))]
                      for (x0, y0, x1, y1) in _mask_rects(mask, grid)]
                for lay, mask in _realize_masks.items()
            }
            net_vias = bridges_to_vias(bridges, reqw, grid,
                                       existing=existing_vias_mm)
        else:
            _fmask = prep.get("f_admit_mask")
            _f_admit = (_mask_rects(_fmask, grid)
                        if _fmask is not None else None)
            _padb = []
            for _fp in board.GetFootprints():
                for _pd in _fp.Pads():
                    _bb = _pd.GetBoundingBox()
                    _padb.append((_bb.GetLeft() / MM, _bb.GetTop() / MM,
                                  _bb.GetRight() / MM, _bb.GetBottom() / MM))
            _padb.extend(footprint_copper_boxes(board))
            # Reuse the field-via pad exclusion machinery for Edge.Cuts.  Its
            # VIA_R + PAD_MARGIN expansion is only the pad-standoff rule; pre-
            # inflate apertures by the 0.5-mm copper-edge requirement as well
            # so a 0.9-mm barrel cannot sit 0.7 mm outside the cut and still
            # fail DRC (the Wave-8d DL1 pair).
            _edge_clear = 0.5
            for _edge in edge_cut_items(board):
                _bb = _edge.GetBoundingBox()
                _padb.append((_bb.GetLeft() / MM - _edge_clear,
                              _bb.GetTop() / MM - _edge_clear,
                              _bb.GetRight() / MM + _edge_clear,
                              _bb.GetBottom() / MM + _edge_clear))
            def _pofv_pad_allow(_x, _y, _nc=nc):
                if pcbnew is None:
                    return False
                _at = pcbnew.VECTOR2I(_nm(_x), _nm(_y))
                _blocking, _allowed = fab.via_at_pad_conflicts(
                    board, _at, _nm(0.9), _nm(0.5), _nc)
                return _blocking is None and bool(_allowed)
            _bridge_forbidden = prep["bridge_forbidden"]
            def _planned_via_allow(_x, _y, _mask=_bridge_forbidden):
                _i, _j = grid.ix(_x), grid.iy(_y)
                return (0 <= _i < grid.nx and 0 <= _j < grid.ny
                        and not _mask[_j, _i])
            realized, _vpts, _rnotes = realize_overunder_rects(
                chains, bridges, reqw, grid, pad_boxes=_padb,
                existing_vias=existing_vias_mm, f_admit=_f_admit,
                free_masks=prep.get("free") or prep.get("passable"),
                clip_masks=_realize_masks, holes_out=_realized_holes,
                pad_allow=_pofv_pad_allow, via_allow=_planned_via_allow,
                strict_bridges=True)
            net_vias = [{"x_mm": x, "y_mm": y} for (x, y) in _vpts]
            for _nt in _rnotes:
                print(f"[cec_slab_pour] over-under[{net}]: {_nt}",
                      file=sys.stderr)
        segs = 0
        for lay, polys in realized.items():
            for poly_index, poly in enumerate(polys):
                row = {"net": net, "layer": lay, "polygon": poly,
                       "provenance": "overunder",
                       # Shapely legitimately emits separate components that
                       # meet at one corner. KiCad classifies same-priority
                       # point contact as zones_intersect even on the same
                       # net. Distinct priorities within this one net/layer
                       # make that intentional contact explicit. Cross-net
                       # safety remains fail-closed in the exact foreign-net
                       # raster mask and post-fill incursion/conformance gate;
                       # the index deliberately resets rather than creating a
                       # global priority scheme that could conceal bad copper.
                       "priority": 4 + poly_index}
                holes = _realized_holes.get((lay, poly_index))
                if holes:
                    row["holes"] = holes
                pour_dicts.append(row)
                planned_pours.append(row)
                segs += 1

        for v in net_vias:
            v["net"] = net
            existing_vias_mm.append((v["x_mm"], v["y_mm"]))
            planned_bridge_vias.append({"net": net,
                                        "x_mm": v["x_mm"],
                                        "y_mm": v["y_mm"],
                                        "radius_mm": VIA_R})
        via_list.extend(net_vias)

        report[net] = {"path_found": True, "segments": segs,
                       "bridges": len(bridges),
                       "layers_used": sorted(realized.keys()),
                       **_man_rep}
        print(f"[cec_slab_pour] over-under: {net} -> {segs} lane segment(s) "
              f"on {sorted(realized.keys())}, {len(bridges)} bridge(s), "
              f"{len(net_vias)} via(s)", file=sys.stderr)

    # A sequential solve knows about earlier barrels but not later ones. Clip
    # every outline against the complete generated-via batch before any caller
    # can materialize it, so ask ordering cannot decide whether a foreign via
    # is hidden inside a saved pour outline.
    pour_dicts, _via_clipped = _clip_pours_around_generated_vias(
        pour_dicts, via_list, clearance_mm=clearance_mm)
    if _via_clipped:
        print("[cec_slab_pour] over-under: clipped %d pour outline(s) around "
              "foreign bridge vias" % _via_clipped, file=sys.stderr)
    pour_dicts, _copper_clipped = _clip_pours_around_foreign_copper(
        board, pour_dicts, clearance_mm=clearance_mm)
    if _copper_clipped:
        print("[cec_slab_pour] over-under: clipped %d pour outline(s) around "
              "foreign board copper" % _copper_clipped, file=sys.stderr)

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
    _cfg = _board_thermal_config(board)
    net_currents = dict((_cfg[0] if _cfg else None) or {})
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


def _pcb_item_identity(item):
    """Stable process-local identity for a KiCad board item."""
    for uuid_getter in (lambda: item.m_Uuid, lambda: item.GetUuid()):
        try:
            uuid = uuid_getter()
        except Exception:                              # noqa: BLE001
            continue
        # ``str(KIID)`` is SWIG's proxy representation, including the address
        # of a short-lived wrapper.  Those wrappers are repeatedly allocated
        # and their addresses are reused while walking connectivity, which can
        # collapse unrelated copper objects onto the same graph node.  Extract
        # the UUID value owned by KiCad instead.
        for value_getter in (getattr(uuid, "AsString", None),
                             getattr(uuid, "AsStdString", None)):
            if value_getter is None:
                continue
            try:
                value = str(value_getter())
                if value:
                    return value
            except Exception:                          # noqa: BLE001
                continue
    return "swig:%d" % id(item)


def _zone_components(adjacency):
    """Connected components of a pure zone adjacency graph."""
    unseen = set(adjacency)
    out = []
    while unseen:
        root = unseen.pop()
        component = {root}
        stack = [root]
        while stack:
            key = stack.pop()
            for other in adjacency.get(key, ()):
                if other in unseen:
                    unseen.remove(other)
                    component.add(other)
                    stack.append(other)
        out.append(component)
    return out


def _copper_zone_graph(conn, zones, excluded_keys=()):
    """Build exact zone adjacency, including shared pad/track/via carriers."""
    by_key = {_pcb_item_identity(z): z for z in zones}
    excluded = set(excluded_keys)
    adjacency = {key: set() for key in by_key if key not in excluded}
    terminals = set()
    carriers = {}
    for key, zone in by_key.items():
        if key not in adjacency:
            continue
        try:
            items = list(conn.GetConnectedItems(zone))
        except Exception:                              # noqa: BLE001
            # Connectivity uncertainty must never authorize copper deletion.
            terminals.add(key)
            continue
        for item in items:
            klass = item.GetClass()
            if klass == "ZONE":
                other = _pcb_item_identity(item)
                if (other in adjacency
                        and by_key[other].GetNetCode() == zone.GetNetCode()):
                    adjacency[key].add(other)
                    adjacency[other].add(key)
            elif klass in ("PAD", "PCB_VIA", "PCB_TRACK"):
                terminals.add(key)
                carriers.setdefault(
                    (zone.GetNetCode(), klass, _pcb_item_identity(item)),
                    set()).add(key)
    # Two zone polygons on different layers commonly meet only through the
    # same through-via.  KiCad may report the barrel to both polygons without
    # reporting the polygons directly to one another, so make that conductive
    # relationship explicit in the graph.
    for keys in carriers.values():
        keys = list(keys)
        for key in keys[1:]:
            adjacency[keys[0]].add(key)
            adjacency[key].add(keys[0])
    return by_key, adjacency, terminals


def _terminal_reachable_zone_keys(adjacency, terminal_keys):
    """Return every zone in a zone-to-zone component that reaches copper.

    KiCad reports zone connectivity one item at a time.  A routed-object pour
    is deliberately made from several abutting zone polygons, so an interior
    polygon can touch only its two neighbouring zones while a polygon at the
    end of the component reaches a pad, via, or track.  Judging each polygon
    independently therefore dismantles a valid corridor from the middle.

    Keep the graph walk pure so the component rule has regression teeth
    without depending on pcbnew/SWIG object construction in unit tests.
    """
    adjacency = {key: set(rows) for key, rows in adjacency.items()}
    live = {key for key in terminal_keys if key in adjacency}
    stack = list(live)
    while stack:
        key = stack.pop()
        for other in adjacency.get(key, ()):
            if other in adjacency and other not in live:
                live.add(other)
                stack.append(other)
    return live


def cleanup_floating_zones(board_path):
    """FLOATING-ZONE CLEANUP (owner requirement 2026-07-24): remove copper
    zones whose connectivity cluster contains NO pad, via, or track -- pure
    floating decoration. Runs as a FRESH load->remove->save cycle (the
    2026-06-09 footgun was zone removal inside a manipulation-heavy process;
    a clean cycle isolates it -- verified by the caller re-loading + DRC)."""
    if pcbnew is None:
        return 0
    board = pcbnew.LoadBoard(board_path)
    # MAKE THE EVIDENCE REAL BEFORE JUDGING ON IT (regression fix 2026-07-25).
    # The zero-fill rule below reads an empty area as "the filler carved this
    # away, it is a phantom" -- and the original comment asserted the cleanup
    # "runs after the fill, so an empty area is the filler's verdict, not a
    # race". That assumption was FALSE and cost real copper: on the cable boards
    # (eps/pcie/12vhpwr) the board's own GND planes arrive here UNFILLED, so the
    # rule deleted them outright. Measured on eps-8pin: In1 and In2 both lost
    # their plane (7021mm2 each) and structural DRC went 2 -> 23, with FR then
    # routing 165 signal tracks across what should have been solid ground.
    # Filling here makes the verdict honest -- a phantom still fills to zero and
    # still dies, a real plane fills and lives -- and it leaves the artifact with
    # its pours actually filled, which is what a reviewable board looks like.
    # NOTE this is deliberately NOT a name-based exemption: the owner overturned
    # name-skipping for the zero-cluster rule on 2026-07-25, and the fix must not
    # smuggle it back in through the fill rule.
    filled_now = False
    try:
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        filled_now = True
        if hasattr(board, "BuildConnectivity"):
            board.BuildConnectivity()          # connectivity must see the fill
    except Exception as e:                                 # noqa: BLE001
        print(f"[cec_slab_pour] zone cleanup: fill failed ({e}) -- zero-fill "
              "rule DISABLED for this pass (never delete on unmeasured "
              "evidence)", file=sys.stderr)
    conn = board.GetConnectivity()
    zones = [z for z in board.Zones()
             if not z.GetIsRuleArea() and z.GetNetname()]

    empty = set()
    for z in zones:
        key = _pcb_item_identity(z)
        # ZERO-FILL zones are dead by definition (measured on the s510
        # winner: a `pourplan:` outline whose fill was fully carved away
        # survived as a phantom "pour connected to nothing") -- but ONLY once a
        # fill has actually run in this cycle, per the note above.
        try:
            if filled_now and z.GetFilledArea() == 0:
                empty.add(key)
                continue
        except Exception:                              # noqa: BLE001
            pass
    # Zero-fill polygons cannot conduct and therefore cannot bridge two live
    # parts of the graph. Exclude them while building connectivity.
    by_key, adjacency, terminals = _copper_zone_graph(conn, zones, empty)
    live = _terminal_reachable_zone_keys(adjacency, terminals)
    doomed = [z for key, z in by_key.items()
              if key in empty or key not in live]
    for z in doomed:
        board.Remove(z)
    # Save when anything changed -- including a fill with no removals, so the
    # artifact carries its filled copper instead of empty outlines.
    if doomed or filled_now:
        pcbnew.SaveBoard(board_path, board)
        if doomed:
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
    try:
        pours, rep = synthesize_slab_pours(b, asks)
    except SlabAllocationError as exc:
        # A fail-closed CLI that prints only the net/layer list forces manual
        # instrumentation precisely when the placer/pour contract needs repair.
        # Preserve the non-zero exit while surfacing the invariant evidence.
        print(json.dumps({
            "pours": 0,
            "failures": [f"{net}|{layer}" for net, layer in exc.failures],
            "report": {f"{k[0]}|{k[1]}": v for k, v in exc.report.items()},
        }, indent=1, default=str))
        raise SystemExit(1)
    print(json.dumps({"pours": len(pours),
                      "report": {f"{k[0]}|{k[1]}": v for k, v in rep.items()}},
                     indent=1, default=str))


def _shunt_pad_halves(board):
    """Per-RS shunt pad-group geometry: [{ref, horiz, halves: [(net, gbox,
    centre), (net, gbox, centre)], gap: (x0, y0, x1, y1)}] with gbox/gap in
    mm. *gap* is the INTER-PAD strip between the two groups' inner edges,
    spanning the union of their lateral extents -- the region the
    pour-termination ruling (owner 2026-07-25) assigns EXCLUSIVELY to the
    authored Kelvin tap stubs. Shared by guaranteed_shunt_patches (inner-
    edge clip) and the v4 planner (F-corridor gap exclusion)."""
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
        if horiz:
            left, right = (ba, bbx) if ca[0] <= cb[0] else (bbx, ba)
            gap = (left[2], min(ba[1], bbx[1]), right[0],
                   max(ba[3], bbx[3]))
        else:
            top, bot = (ba, bbx) if ca[1] <= cb[1] else (bbx, ba)
            gap = (min(ba[0], bbx[0]), top[3], max(ba[2], bbx[2]),
                   bot[1])
        out.append({"ref": fp.GetReference(), "horiz": horiz,
                    "halves": [(na, ba, ca), (nb, bbx, cb)], "gap": gap})
    return out


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

    INNER-SIDE CLIP AT THE PAD INNER EDGE (pour-termination ruling, owner
    2026-07-25 -- supersedes the original mid-gap clip): force copper
    terminates AT the shunt pad and never enters the inter-pad gap, which
    belongs exclusively to the authored Kelvin tap stubs (tap-form v5:
    the stubs enter from the pad inner edges). *gap_mm* is retired by the
    ruling (kept in the signature for call-site compatibility; unused).
    Outer/side margins keep *margin_mm* -- they cover the outboard
    force-via rows, the patch's original purpose. Local COVERAGE guarantee
    only -- reachability is the pre-FR corridor reservation's job."""
    del gap_mm                                         # retired (ruling)
    out = []
    for sh in _shunt_pad_halves(board):
        horiz = sh["horiz"]
        cs = [c for (_n, _g, c) in sh["halves"]]
        mid = ((cs[0][0] + cs[1][0]) / 2, (cs[0][1] + cs[1][1]) / 2)
        for (net, gb, cc) in sh["halves"]:
            x0, y0 = gb[0] - margin_mm, gb[1] - margin_mm
            x1, y1 = gb[2] + margin_mm, gb[3] + margin_mm
            if horiz:
                if cc[0] < mid[0]:
                    x1 = min(x1, gb[2])                # inner edge, exact
                else:
                    x0 = max(x0, gb[0])
            else:
                if cc[1] < mid[1]:
                    y1 = min(y1, gb[3])
                else:
                    y0 = max(y0, gb[1])
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
def connector_manifolds(board, nets=None, *, margin_mm=0.3,
                        ref_prefixes=("J", "TB")):
    """Manifold pour dicts for every (connector, net) pin group.

    *nets* -- restrict to these net names (None = every non-GND net on a
    connector). GND is always excluded (plane-carried; a GND manifold would
    just shadow the plane). ``margin_mm`` is a local attach allowance, not a
    board-routing corridor: the over-under solver owns the widened remote path.
    Keeping this small prevents a connector's grouped power row from creating
    a giant slab across interleaved foreign pins. Returns dicts in
    add_power_pours' format with
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
                profile_name = fab.active_profile_name(
                    board, hint=os.environ.get("CEC_THERMAL_BOARD_HINT", ""))
                power = "In3.Cu" if profile_name else "In2.Cu"
                enabled = set(fab.enabled_copper_layers(board))
                lays = [l for l in ("F.Cu", power) if l in enabled]
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
                            "provenance": "slab", "priority": 3,
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


REAP_EXEMPT_PREFIXES = ("patch:", "manifold:", "pourfirst:", "pourplan:")


def enumerate_winning(cands, vias, *, no_path_nets=(), gang_keep=None,
                      locked_vias=(), pads=(), min_layers=None,
                      net_amps=None):
    """SINGLE-OWNER WHITELIST (owner sharpening 2026-07-25, docs/slab-pour-
    design-2026-07-24.md: "if it finds a solution, all other pours that were
    made in pursuit of that solution get deleted unless they are specifically
    required bridges or required thermal second planes"). Pure enumeration --
    a piece survives only by being NAMED in the winning set, never by evading
    a test.

    *cands*: the frozen-candidate pour dicts (winning lanes/regions/landings
    + stage-0 manifolds + guaranteed patches; name/net/layer/polygon).
    *vias*:  the solution's via list ([{net, x_mm, y_mm}]) -- a via field IS
    part of the winning solution (required bridges), and copper embedding it
    is winning copper.
    *no_path_nets*: nets the solve could NOT route -- no winning set exists,
    so the v3 loud rule stands for them (manifolds kept as the honest gang
    copper FR will finish against; patches only under locked barrels).
    *gang_keep*: {net: preferred_layer} for TRIVIAL nets whose manifold gang
    IS the solution (single served group after ganging) -- that one manifold
    layer is winning copper; its other-layer siblings are not.
    *locked_vias*: [(net, x_mm, y_mm)] locked barrels on the board (force
    arrays) -- copper covering them is required (barrel embed), the one
    insurance class the ruling keeps.

    KEEP set: (1) solution dicts (anything NOT manifold:/patch:-named);
    (2) manifold pieces the solution touches on the SAME layer (terminal
    attach the path lands on = winning copper) or that embed a solution/
    locked via, or the gang_keep layer, or any manifold of a no-path net;
    (3) patches with same-net solution F copper at the shunt or a same-net
    solution/locked via inside them. DELETE everything else, with reasons.
    Returns (kept, dropped) -- dropped = [(dict, reason)]."""
    from shapely.geometry import Point, box as _sbox
    from shapely.geometry import Polygon
    gang_keep = dict(gang_keep or {})
    no_path = set(no_path_nets or ())

    def _poly(d):
        try:
            p = Polygon(d.get("polygon") or ()).buffer(0)
            return p if not p.is_empty else None
        except Exception:                              # noqa: BLE001
            return None

    sol_by = {}                                        # (net, layer) -> [poly]
    for d in cands:
        nm = str(d.get("name") or "")
        if nm.startswith(("manifold:", "patch:")):
            continue
        p = _poly(d)
        if p is not None:
            sol_by.setdefault((d.get("net"), d.get("layer", "F.Cu")),
                              []).append(p)
    via_by = {}                                        # net -> [Point]
    for v in vias or ():
        via_by.setdefault(v.get("net"), []).append(
            Point(v.get("x_mm", 0.0), v.get("y_mm", 0.0)))
    for (n, x, y) in locked_vias or ():
        via_by.setdefault(n, []).append(Point(x, y))

    kept, dropped = [], []
    for d in cands:
        nm = str(d.get("name") or "")
        net = d.get("net")
        lay = d.get("layer", "F.Cu")
        if not nm.startswith(("manifold:", "patch:")):
            kept.append(d)                             # (1) winning copper
            continue
        p = _poly(d)
        if p is None:
            dropped.append((d, "degenerate polygon"))
            continue
        touches_sol = any(p.intersects(sp)
                          for sp in sol_by.get((net, lay), ()))
        embeds_via = any(p.covers(q) for q in via_by.get(net, ()))
        if nm.startswith("manifold:"):
            gk = gang_keep.get(nm, gang_keep.get(net))
            if net in no_path:
                kept.append(d)                         # v3 loud rule
            elif touches_sol or embeds_via:
                kept.append(d)                         # attach/bridge copper
            elif gk == lay:
                kept.append(d)                         # the gang IS part of
                #   the winning terminal (it binds >=2 clusters the
                #   connectivity proof relied on) -- one layer stays
            else:
                dropped.append((d, "manifold layer unused by the winning "
                                   "solution"))
            continue
        # patch:
        f_sol = (lay == "F.Cu" and touches_sol)
        if f_sol or embeds_via:
            kept.append(d)
        else:
            dropped.append((d, "insurance patch -- solution does not use "
                               "%s at this shunt and no barrel needs cover"
                            % lay))
    kept, _redundant = drop_redundant_layers(
        kept, pads=pads, vias=list(vias or ()) +
        [{"net": n, "x_mm": x, "y_mm": y} for (n, x, y) in (locked_vias or ())],
        min_layers=min_layers, net_amps=net_amps)
    dropped.extend(_redundant)
    return kept, dropped


def _conn_set(poly, pts, layer=None):
    """Connection points a polygon actually covers ON ITS OWN LAYER."""
    return frozenset((round(x, 1), round(y, 1)) for (x, y, lay) in pts
                     if (lay is None or layer is None or lay == layer)
                     and poly.covers(_shp_point(x, y)))


def _shp_point(x, y):
    from shapely.geometry import Point
    return Point(x, y)


def prune_orphan_vias(vias, kept, *, locked_vias=()):
    """Drop barrels the single-owner pass just orphaned.

    Removing a redundant layer STRANDS the vias that only existed to feed it --
    a barrel to nowhere, which is precisely the "random vias" complaint and a
    defect the tidy-up would otherwise create. A via survives if it still joins
    kept copper on two or more layers, or if it is locked (force-array barrels
    are placed copper, never inferred).

    Returns (kept_vias, dropped_vias).
    """
    from shapely.geometry import Polygon
    locked = {(round(x, 1), round(y, 1)) for (_n, x, y) in (locked_vias or ())}
    by_net = {}
    for d in kept or ():
        try:
            g = Polygon(d.get("polygon") or ()).buffer(0)
        except Exception:                                  # noqa: BLE001
            continue
        if not g.is_empty:
            by_net.setdefault(d.get("net"), []).append(
                (d.get("layer", "F.Cu"), g))
    out, dropped = [], []
    for v in vias or ():
        x, y = v.get("x_mm", 0.0), v.get("y_mm", 0.0)
        if (round(x, 1), round(y, 1)) in locked:
            out.append(v)
            continue
        pt = _shp_point(x, y)
        lays = {lay for (lay, g) in by_net.get(v.get("net"), ()) if g.covers(pt)}
        if len(lays) >= 2:
            out.append(v)
        else:
            dropped.append(v)
    return out, dropped


def layers_for_current(amps, width_mm, *, inner=True, dt_c=30.0, oz=1.0):
    """How many parallel layers one net genuinely needs -- IPC-2221:
    I = k * dT^0.44 * A^0.725  (A in mil^2, k=0.024 internal / 0.048 external).

    This is the AMPACITY GUARD for drop_redundant_layers. Parallel copper laid
    for current has the SAME connection set as its twin (that is what parallel
    means), so the subset test would delete it as a duplicate without a real
    number to stop it. dT 30C is the platform gate (spec 6.6); oz is the
    finished copper weight of the layer class.
    """
    if not amps or amps <= 0 or not width_mm or width_mm <= 0:
        return 1
    a_mm2 = float(width_mm) * 0.0347 * float(oz)          # 1oz = 34.7um
    a_mil2 = a_mm2 * 1550.0
    k = 0.024 if inner else 0.048
    per_layer = k * (float(dt_c) ** 0.44) * (a_mil2 ** 0.725)
    if per_layer <= 0:
        return 1
    import math
    return max(1, int(math.ceil(float(amps) / per_layer)))


def drop_redundant_layers(kept, *, pads=(), vias=(), min_layers=None,
                          net_amps=None):
    """SINGLE-OWNER, APPLIED TO SOLUTION COPPER TOO (owner 2026-07-26: "it is
    already gathered and good on the top layer -- why is it ALSO on the bottom
    layer?").

    enumerate_winning's own rules could never answer that. Solution lanes were
    kept UNCONDITIONALLY on every layer, and the manifold `embeds_via` test is
    satisfied on every layer a through-barrel passes, so an exact functional
    copy of a zone (same pads, same barrels, different layer) always looked
    load-bearing. Measured on the 24-pin s963 winner: /SENSE3V3_HI held SIX
    zones over THREE layers, 1869mm2 for one 20A rail -- including an In2 copy
    of the J3 manifold with byte-identical pads and barrels, and an In2 lane
    touching no pad at all.

    The test here is deliberately the CONSERVATIVE one: a zone is redundant
    only when its whole connection set is a subset of ONE other kept same-net
    zone. Subset-of-the-union would be unsound -- points spread across several
    zones are not mutually connected the way one contiguous piece connects
    them -- so this can never sever a bridge to save copper.

    *min_layers*: {net: n} where current genuinely needs n parallel layers;
    that many are kept before redundancy applies (the ampacity guard, so this
    never trades a thermal requirement for tidiness).
    """
    from shapely.geometry import Polygon
    min_layers = dict(min_layers or {})
    # Pads are LAYER-AWARE: an SMD pad exists on exactly one copper layer, so
    # an inner zone passing over it connects nothing. Modelling pads as bare
    # points made an In2 copy look like it owned an F.Cu terminal -- which
    # would have deleted the only zone actually touching the pad.
    pts_by_net = {}                                        # net -> [(x,y,lay)]
    _pad_only = {}
    for _p in pads or ():
        n, x, y = _p[0], _p[1], _p[2]
        lay = _p[3] if len(_p) > 3 else None                # None = all layers
        pts_by_net.setdefault(n, []).append((x, y, lay))
        _pad_only.setdefault(n, set()).add((x, y, lay))
    for v in vias or ():
        pts_by_net.setdefault(v.get("net"), []).append(
            (v.get("x_mm", 0.0), v.get("y_mm", 0.0), None))

    by_net = {}
    for i, d in enumerate(kept):
        by_net.setdefault(d.get("net"), []).append(i)

    drop_idx, reasons = set(), {}
    for net, idxs in by_net.items():
        if len(idxs) < 2:
            continue
        pts = pts_by_net.get(net) or []
        if not pts:
            continue
        info = []
        for i in idxs:
            d = kept[i]
            try:
                p = Polygon(d.get("polygon") or ()).buffer(0)
            except Exception:                              # noqa: BLE001
                continue
            if p.is_empty:
                continue
            _lay = d.get("layer", "F.Cu")
            cs = _conn_set(p, pts, _lay)
            _pp = [(q[1], q[2]) for q in (pads or ())
                   if q[0] == net and (len(q) < 4 or q[3] is None
                                       or q[3] == _lay)]
            npads = sum(1 for (x, y) in _pp
                        if (round(x, 1), round(y, 1)) in cs)
            info.append((i, d, cs, npads, p.area))
        # Own the net from the strongest piece down: real terminals first,
        # then connection count, then area. A layer only survives past the
        # ampacity floor by contributing a connection nothing else provides.
        # Real terminals first, then OUTER layers (IPC k 0.048 vs 0.024 --
        # an outer layer carries ~2x the same slab), then connection count,
        # then area. Ranking by area alone let a larger inner copy outrank
        # the outer zone and evict it.
        info.sort(key=lambda t: (
            -t[3],
            0 if t[1].get("layer", "F.Cu") in ("F.Cu", "B.Cu") else 1,
            -len(t[2]), -t[4]))
        # AMPACITY FLOOR, judged against the OWNER's layer class. An external
        # layer carries ~2x an internal one for the same slab (IPC-2221 k
        # 0.048 vs 0.024), so a rail already gathered on F.Cu often needs no
        # second layer at all -- which is why the 24-pin's 20A 3V3 had two
        # copies it could not justify.
        if net in min_layers:
            floor = max(1, int(min_layers[net]))
        else:
            _o = info[0]
            _lay = _o[1].get("layer", "F.Cu")
            try:
                _b = _o[1].get("polygon") or ()
                _w = min(max(q[0] for q in _b) - min(q[0] for q in _b),
                         max(q[1] for q in _b) - min(q[1] for q in _b))
            except Exception:                              # noqa: BLE001
                _w = 0.0
            floor = layers_for_current(
                (net_amps or {}).get(net, 0.0), _w,
                inner=_lay not in ("F.Cu", "B.Cu"))
        accepted = []
        for (i, d, cs, npads, area) in info:
            if len(accepted) < floor or not cs:
                accepted.append((i, d, cs))
                continue
            host = next((hd for (_hi, hd, hcs) in accepted if cs <= hcs), None)
            if host is not None:
                drop_idx.add(i)
                reasons[i] = ("redundant layer -- every connection (%d) is "
                              "already made by %s on %s"
                              % (len(cs), host.get("name"),
                                 host.get("layer", "F.Cu")))
            else:
                accepted.append((i, d, cs))
    out = [d for i, d in enumerate(kept) if i not in drop_idx]
    dropped = [(kept[i], reasons[i]) for i in sorted(drop_idx)]
    out, par = _drop_parallel_bridges(out, pts_by_net, min_layers, net_amps,
                                      _pad_pts=_pad_only)
    return out, dropped + par


def _net_graph_connected(zones, pts):
    """All of a net's terminals in ONE component, given these zones.

    Zones join through a shared via barrel (any two layers a barrel passes) or
    by overlapping on the same layer. A pad is a terminal held by any zone that
    covers it on the pad's own layer.
    """
    from shapely.geometry import Polygon
    polys = []
    for d in zones:
        try:
            g = Polygon(d.get("polygon") or ()).buffer(0)
        except Exception:                                  # noqa: BLE001
            continue
        if not g.is_empty:
            polys.append((d.get("layer", "F.Cu"), g))
    if not polys:
        return False
    parent = list(range(len(polys)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i in range(len(polys)):
        for j in range(i + 1, len(polys)):
            li, gi = polys[i]
            lj, gj = polys[j]
            if li == lj:
                if gi.intersects(gj):
                    union(i, j)
                continue
            for (x, y, lay) in pts:                        # barrel: all layers
                if lay is None and gi.covers(_shp_point(x, y)) \
                        and gj.covers(_shp_point(x, y)):
                    union(i, j)
                    break
    terms = set()
    comps = set()
    for (x, y, lay) in pts:
        for i, (li, gi) in enumerate(polys):
            if (lay is None or lay == li) and gi.covers(_shp_point(x, y)):
                terms.add((round(x, 1), round(y, 1)))
                comps.add(find(i))
                break
    return bool(terms) and len(comps) <= 1


def _drop_parallel_bridges(kept, pts_by_net, min_layers, net_amps,
                           _pad_pts=None):
    """PARALLEL BRIDGES (owner 2026-07-26, the second half of "why is it ALSO
    on the bottom layer?").

    Two lanes of one net on different layers can each cover a barrel the other
    does not, so neither is a subset of the other and the conservative pass
    keeps both -- measured on the 24-pin s963 winner, where /SENSE3V3_HI kept a
    1564mm2 In2 lane AND a 618mm2 B.Cu lane doing the same job.

    Deciding this needs a CONNECTIVITY PROOF, not a set comparison: drop a lane
    only when the net's terminals provably remain in one component without it,
    and the ampacity floor still holds. That is sound where subset-of-the-union
    was not.
    """
    _pad_pts = {k: set(v) for k, v in (_pad_pts or {}).items()}
    by_net = {}
    for i, d in enumerate(kept):
        by_net.setdefault(d.get("net"), []).append(i)
    drop, reasons = set(), {}
    for net, idxs in by_net.items():
        if len(idxs) < 2:
            continue
        pts = pts_by_net.get(net) or []
        if not pts:
            continue
        live = list(idxs)
        if not _net_graph_connected([kept[i] for i in live], pts):
            continue                                       # already broken --
            #   never "tidy" a net whose proof does not hold to begin with
        floor = max(1, int(min_layers.get(net, 1))) if net in min_layers else 1
        if net not in min_layers and (net_amps or {}).get(net):
            widths = []
            for i in live:
                b = kept[i].get("polygon") or ()
                if b:
                    widths.append(min(max(q[0] for q in b) - min(q[0] for q in b),
                                      max(q[1] for q in b) - min(q[1] for q in b)))
            lay = kept[live[0]].get("layer", "F.Cu")
            floor = layers_for_current(net_amps[net], max(widths) if widths else 0.0,
                                       inner=lay not in ("F.Cu", "B.Cu"))
        # WHICH copy dies matters as much as that one does. Try the weakest
        # owner first: copper holding no real terminal, then inner layers
        # (IPC k 0.024 vs 0.048 -- an outer layer carries ~2x), then the
        # smaller piece. Without this the pass dropped the F.Cu manifold
        # holding J3's pads and kept an inner lane, which is electrically
        # legal through THT barrels but is the wrong owner on both counts.
        _pads_only = [(x, y, lay) for (x, y, lay) in pts
                      if (x, y, lay) in _pad_pts.get(net, ())]

        def _holds_pad(i):
            from shapely.geometry import Polygon
            try:
                g = Polygon(kept[i].get("polygon") or ()).buffer(0)
            except Exception:                              # noqa: BLE001
                return False
            lay = kept[i].get("layer", "F.Cu")
            return any((pl is None or pl == lay) and g.covers(_shp_point(px, py))
                       for (px, py, pl) in _pads_only)

        def _area(i):
            from shapely.geometry import Polygon
            try:
                return Polygon(kept[i].get("polygon") or ()).buffer(0).area
            except Exception:                              # noqa: BLE001
                return 0.0

        order = sorted(live, key=lambda i: (
            1 if _holds_pad(i) else 0,
            1 if kept[i].get("layer", "F.Cu") in ("F.Cu", "B.Cu") else 0,
            _area(i)))
        for i in order:
            rest = [j for j in live if j != i]
            if len({kept[j].get("layer", "F.Cu") for j in rest}) < floor:
                continue                                   # ampacity floor
            if len(rest) >= 1 and _net_graph_connected([kept[j] for j in rest], pts):
                live = rest
                drop.add(i)
                reasons[i] = ("parallel bridge -- the net's terminals stay in "
                              "one component without this %s lane"
                              % kept[i].get("layer", "F.Cu"))
    out = [d for i, d in enumerate(kept) if i not in drop]
    return out, [(kept[i], reasons[i]) for i in sorted(drop)]


def _nowhere_zone_verdict(zone_name, netname, clusters_hit):
    """PURE reaper decision (v3 defense-in-depth, owner: "the giant
    cross-board L3 pour and leads-nowhere pours must die"): a non-GND zone
    that connects <2 distinct same-net terminal clusters is DEAD WEIGHT --
    unless its name marks it as a guaranteed shunt patch, a connector
    manifold, or frozen pour-first state (sanctioned pad-anchored copper /
    set-in-stone geometry). Returns True = reap.

    ZERO-CONNECTION OVERRIDE (mandate part 4b, 2026-07-25, measured on the
    s510 winner: exempt-named `pourplan:` fragments with fill touching NO
    terminal cluster survived both reaps -- the owner's "pours not connected
    to anything, exist for no reason"): the name exemption protects the
    <2-cluster JUDGMENT only (sanctioned single-cluster copper); a zone
    touching NOTHING is dead regardless of what it is called."""
    if not netname or netname == "GND":
        return False
    if int(clusters_hit) == 0:
        return True
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
    board.BuildConnectivity()
    conn = board.GetConnectivity()
    grid = Grid(board, cell_mm)
    zones = [z for z in board.Zones()
             if (not z.GetIsRuleArea() and z.GetNetname()
                 and z.GetNetname() != "GND")]
    by_key, adjacency, _terminal_keys = _copper_zone_graph(conn, zones)
    cl_cache = {}
    zone_hits = {}
    for key, z in by_key.items():
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
        zone_hits[key] = hit

    doomed = []
    for component in _zone_components(adjacency):
        component_hits = set().union(
            *(zone_hits.get(key, set()) for key in component))
        # A routed-object pour is a chain of zone polygons. Interior members
        # intentionally touch no terminal cluster themselves; the component's
        # endpoints carry that responsibility. Judge the conducting component
        # as a whole or the reaper cuts valid power corridors into pieces.
        if len(component_hits) >= 2:
            continue
        for key in component:
            z = by_key[key]
            net = z.GetNetname()
            try:
                name = z.GetZoneName() or ""
            except Exception:                          # noqa: BLE001
                name = ""
            # NO early name-exit here (mandate part 4b): the exemption is the
            # VERDICT's business, and protects the single-cluster judgment
            # only. A zero-terminal component dies regardless of its name.
            if not _nowhere_zone_verdict(
                    name, net, len(component_hits)):
                continue
            bb = z.GetBoundingBox()
            doomed.append((z, net,
                           (round(bb.GetLeft() / MM, 1),
                            round(bb.GetTop() / MM, 1),
                            round(bb.GetRight() / MM, 1),
                            round(bb.GetBottom() / MM, 1)),
                           len(component_hits)))
    for (z, net, bbox, nhit) in doomed:
        print(f"[cec_slab_pour] nowhere-reap: zone on {net} at {bbox} "
              f"belongs to component with {nhit} terminal cluster(s) (<2) "
              "-- REMOVED",
              file=sys.stderr)
        board.Remove(z)
    # ORPHAN-VIA SWEEP (mandate part 4a, 2026-07-25): an UNLOCKED via whose
    # barrel touches no pad, track, or filled zone serves nothing (a bridge
    # via whose lane was dropped/reaped, a stranded field slot). Locked
    # barrels are materialize truth (force arrays) and stay. Runs after the
    # zone reaps on a REBUILT connectivity so a via orphaned BY a reap above
    # is caught in the same pass.
    board.BuildConnectivity()
    conn = board.GetConnectivity()
    dead_v = []
    for t in board.GetTracks():
        if t.GetClass() != "PCB_VIA" or t.IsLocked():
            continue
        try:
            items = list(conn.GetConnectedItems(t))
        except Exception:                              # noqa: BLE001
            continue
        if not any(it.GetClass() in ("PAD", "PCB_TRACK", "ZONE")
                   for it in items):
            dead_v.append(t)
    for t in dead_v:
        q = t.GetPosition()
        print(f"[cec_slab_pour] nowhere-reap: orphan via {t.GetNetname()} at "
              f"({q.x / MM:.1f},{q.y / MM:.1f}) touches nothing -- REMOVED",
              file=sys.stderr)
        board.Remove(t)
    if doomed or dead_v:
        pcbnew.SaveBoard(board_path, board)
        print(f"[cec_slab_pour] nowhere-reap: removed {len(doomed)} "
              f"leads-nowhere zone(s) + {len(dead_v)} orphan via(s)",
              file=sys.stderr)
    return len(doomed) + len(dead_v)
