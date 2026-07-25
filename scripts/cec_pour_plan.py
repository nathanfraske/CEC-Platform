#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
"""v4 TERRITORY POUR PLANNER (owner GO 2026-07-25; design of record:
docs/slab-pour-design-2026-07-24.md v4). The designer's method, algorithmic:

  * TERMINALS -- v3.1 connector manifolds + guaranteed shunt patches + the
    net's terminal clusters (all reused from cec_slab_pour, proven).
  * CORRIDORS -- straight fat polygons (trapezoid/L, one bend preferred)
    connecting the terminal groups at the net's required width, planned as
    CENTERLINES in configuration space (obstacles inflated by width/2) on a
    sparse OBSTACLE-CORNER graph: direct segment -> one-bend (axis corners +
    inflated-obstacle corners) -> bounded corner-visibility Dijkstra. Never
    a cell grid.
  * LAYER ASSIGNMENT -- each corridor picks one layer from {F.Cu (shunt
    neighborhoods + manifold landings only -- the categorical top rule),
    In2.Cu, B.Cu} by exact branch-and-bound over per-corridor per-layer
    geometry candidates: zero same-layer inter-net overlap is HARD; then
    minimize via fields; then prefer In2 for power.
  * CROSSINGS -- a corridor with no conflict-free single layer SPLITS at one
    defined crossing point with ONE compact via field there (never smeared
    along the run). Terminal attach on a foreign layer = one compact via
    field AT the terminal (through-barrels serve every layer at once).
  * VERIFICATION -- the realized plan is rasterized with the EXISTING
    cec_slab_pour machinery and must prove clearance, the min-width
    erosion-connectivity invariant, and every served terminal group attached
    at width (the v3.1 width-margin attach rule). A failing net gets ONE
    re-plan with the violated cells added as obstacles; only when the
    planner cannot place it does the net fall back to route_overunder
    (loudly labeled).

Root-cause note (2026-07-25 probe, the s464 "+3V3 weave"): the raster
searcher's 17 bridges were each mask-forced terminal attaches (16 F-only SMD
islands; ablations: F-bias landing-only = identical, bridge_cost x2 = still
17 bridges) -- the mess was REALIZATION smear (3-cell bridge disks + closing
merging into blocky tiles, ~2 scattered vias per bridge). v4 therefore keeps
per-island terminal via fields (they are physics) but makes them compact,
labeled, and placed at the terminal, and realizes corridors as drawn
geometry instead of dilated cell walks.

NAMING: this module is `cec_pour_plan` (the v4 territory planner);
`cec_pourplan` (no underscore) is the UNRELATED pour-lever state owner
(PourPlan/PourSpec, docs/pour-lever-scoping-2026-07-08.md). Task-specified
name; do not merge the two.
"""
import math
import os
import sys

import numpy as np

try:
    import pcbnew                                      # noqa: F401
except ImportError:                                    # host-side tests
    pcbnew = None

import cec_slab_pour as _sp
from cec_slab_pour import (
    Grid,
    connector_manifolds,
    guaranteed_shunt_patches,
    rasterize,
    req_width_mm,
    shunt_neighborhoods,
    terminal_clusters,
)

MM = 1e6
LAYERS_ALL = ("F.Cu", "In2.Cu", "B.Cu")
LAYER_PREF = {"In2.Cu": 0.0, "B.Cu": 0.4, "F.Cu": 0.8}   # In2 preferred for power
VIA_FIELD_COST = 3.0
BEND_COST = 0.5
LEN_COST = 0.02                                          # per mm
TAPER_MAX_MM = 3.2       # max sub-width terminal-approach run (pad = bottleneck)
W_NECK = 0.8             # anchor-approach neck width (true-clearance legal
#                          through a 4.2mm THT pin field; raster-exempt by
#                          the terminal-zone doctrine, geometric proof only)
APPROACH_MM = 3.2        # anchor-approach reach around own pads
SPOT_OFFSET_MM = 1.1     # via-field spot standoff from an SMD pad group edge
EPS = 0.05               # configuration-space epsilon (corner points strictly free)
BB_NODE_CAP = 200000     # branch-and-bound node budget before greedy fallback


# ---------------------------------------------------------------------------
# geometry helpers (shapely; imported lazily nowhere -- the module is only
# imported behind the pour_plan lever / the --v4 flag / the teeth)
# ---------------------------------------------------------------------------
from shapely.geometry import LineString, Point, box as _box  # noqa: E402
from shapely.ops import nearest_points, unary_union  # noqa: E402
from shapely.prepared import prep  # noqa: E402


def _poly_of(points):
    from shapely.geometry import Polygon
    return Polygon(points).buffer(0)


def _capsule(pts, half_w):
    return LineString(pts).buffer(half_w, quad_segs=4)


def _stamp_poly(mask, poly, grid):
    """Scanline-stamp a shapely polygon onto the raster (CELL-CENTER
    containment -- deliberately conservative vs rasterize()'s box-overlap
    over-stamping, so the erosion-connectivity verdict can only be stricter
    than the drawn geometry)."""
    if poly.is_empty:
        return
    minx, miny, maxx, maxy = poly.bounds
    j0 = max(0, grid.iy(miny) - 1)
    j1 = min(grid.ny - 1, grid.iy(maxy) + 1)
    for j in range(j0, j1 + 1):
        y = grid.y0 + (j + 0.5) * grid.cell
        cut = poly.intersection(
            LineString([(minx - 1.0, y), (maxx + 1.0, y)]))
        if cut.is_empty:
            continue
        for seg in getattr(cut, "geoms", [cut]):
            if seg.geom_type != "LineString" or seg.length <= 0:
                continue
            xa, xb = seg.bounds[0], seg.bounds[2]
            i0 = max(0, grid.ix(xa))
            i1 = min(grid.nx - 1, grid.ix(xb))
            for i in range(i0, i1 + 1):
                xc = grid.x0 + (i + 0.5) * grid.cell
                if xa - 1e-9 <= xc <= xb + 1e-9:
                    mask[j, i] = True


def _cell_of(grid, x, y):
    return (min(grid.ny - 1, max(0, grid.iy(y))),
            min(grid.nx - 1, max(0, grid.ix(x))))


# ---------------------------------------------------------------------------
# per-net prep: raster masks, terminal groups, attach geometry, obstacles
# ---------------------------------------------------------------------------
def _net_currents():
    """Same source synthesize_overunder_pours reads (no drift)."""
    try:
        import cec_thermal_overlay as _ov
        _cfg = _ov.board_thermal_config(
            os.environ.get("CEC_THERMAL_BOARD_HINT", ""))
        return dict((_cfg[0] if _cfg else None) or {})
    except Exception:                                  # noqa: BLE001
        return {}


def _geo_obstacles(board, nc, layers, clearance_mm, guard_mm):
    """Per-layer shapely obstacle lists for one net: every FOREIGN pad /
    track / via on that layer, inflated by clearance + *guard_mm* (the
    raster-safety standoff that keeps geometric legality at least as strict
    as the 0.8mm-cell verifier). Locked-ness is ignored, matching
    rasterize() exactly."""
    grow = clearance_mm + guard_mm
    out = {lay: [] for lay in layers}
    lay_ids = {lay: board.GetLayerID(lay) for lay in layers}
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetCode() == nc:
                continue
            bb = p.GetBoundingBox()
            g = _box(bb.GetLeft() / MM - grow, bb.GetTop() / MM - grow,
                     bb.GetRight() / MM + grow, bb.GetBottom() / MM + grow)
            stack = set(p.GetLayerSet().CuStack())
            for lay, lid in lay_ids.items():
                if lid in stack:
                    out[lay].append(g)
    for t in board.GetTracks():
        if t.GetNetCode() == nc:
            continue
        if t.GetClass() == "PCB_VIA":
            r = t.GetWidth(t.TopLayer()) / MM / 2.0
            q = t.GetPosition()
            g = Point(q.x / MM, q.y / MM).buffer(r + grow, quad_segs=4)
            for lay, lid in lay_ids.items():
                if lid in t.GetLayerSet().CuStack():
                    out[lay].append(g)
            continue
        lay = next((L for L, lid in lay_ids.items()
                    if lid == t.GetLayer()), None)
        if lay is None:
            continue
        w = t.GetWidth() / MM / 2.0
        s, e = t.GetStart(), t.GetEnd()
        # SQUARE end caps, deliberately: rasterize() stamps a track as
        # square step boxes of half-extent (w + clearance), so its raster
        # shadow overhangs the endpoint by that much (measured: a 6mm
        # locked rail's phantom reached 4mm past its end and flunked a
        # geometrically-legal corridor). cap_style=3 extends the buffer
        # distance beyond the end >= the raster overhang, keeping planner
        # legality a SUBSET of verifier legality.
        out[lay].append(LineString(
            [(s.x / MM, s.y / MM), (e.x / MM, e.y / MM)]).buffer(
                w + grow, quad_segs=4, cap_style=3))
    return out


class _Group:
    """One terminal group: a spatial cluster of the net's own pads/vias
    (cec_slab_pour.terminal_clusters), optionally ganged under a manifold /
    widened by a guaranteed patch / MERGED with groups the board's existing
    own-net copper (locked force rails, pre-laid stubs, via arrays) already
    connects (_preconnect_merge, mandate part 1 2026-07-25)."""
    __slots__ = ("gid", "cells", "bbox", "cx", "cy", "native", "attach",
                 "f_zone", "eligible", "why", "is_manifold", "merged",
                 "spot", "man_layers", "lay_attach")

    def __init__(self, gid):
        self.gid = gid
        self.cells = []
        self.bbox = None          # (x0,y0,x1,y1) mm
        self.cx = self.cy = 0.0
        self.native = set()       # layers with real anchors
        self.attach = None        # shapely attach-target geometry
        self.f_zone = None        # sanctioned F landing zone (patch/manifold)
        self.eligible = True
        self.why = ""
        self.is_manifold = False
        self.merged = []          # gids ganged into this one
        self.lay_attach = None    # {layer: geometry} PER-LAYER attach copper
        #   (a merged super-group's union bbox is HOLLOW -- the nearest-bbox
        #   point can be empty space; real attach must land on copper that
        #   exists on THAT layer: member pad boxes native there + own-net
        #   track capsules on that layer)
        self.man_layers = set()   # layers the manifold DICTS actually
        #   cover -- manifold-polygon attach is real copper contact ONLY
        #   there (measured on s464: a B.Cu corridor "attached" to an
        #   F/In2 manifold floated 1mm from any B copper and stranded
        #   the connector component)
        self.spot = None          # CANONICAL via-field spot: the group has
        #   ONE terminal field, so every non-native corridor attach must
        #   land at the SAME point -- the first successful attach fixes it
        #   (measured on s464: per-corridor ring spots + one-field dedup
        #   left the tree in 2-6 disconnected components)


def _build_groups(board, net, nc, grid, layers, anchors, man_dicts,
                  patch_dicts, shunt_boxes):
    clab, ncl = terminal_clusters(board, nc, grid)
    if ncl == 0:
        return [], clab, "no pads/vias for net", {}
    groups = {}
    for cid in range(1, ncl + 1):
        ys, xs = np.where(clab == cid)
        if not len(ys):
            continue
        g = _Group(cid)
        g.cells = list(zip(ys.tolist(), xs.tolist()))
        x0 = grid.x0 + xs.min() * grid.cell
        x1 = grid.x0 + (xs.max() + 1) * grid.cell
        y0 = grid.y0 + ys.min() * grid.cell
        y1 = grid.y0 + (ys.max() + 1) * grid.cell
        g.bbox = (x0, y0, x1, y1)
        g.cx, g.cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        g.native = {lay for lay in layers
                    if (anchors[lay] & (clab == cid)).any()}
        g.attach = _box(*g.bbox)
        groups[cid] = g

    # v3.1 manifold gang: clusters covered by one own-net manifold merge into
    # ONE group whose attach geometry is the manifold polygon (width-margin
    # attach applied at corridor-endpoint time via buffer(-w/2)).
    man_polys = {}
    for d in man_dicts:
        if d.get("net") != net:
            continue
        man_polys.setdefault(d.get("name"), {"layers": set(), "poly": None})
        ent = man_polys[d.get("name")]
        ent["layers"].add(d.get("layer", "F.Cu"))
        p = _poly_of(d.get("polygon") or ())
        ent["poly"] = p if ent["poly"] is None else ent["poly"].union(p)
    ganged = {}
    for name, ent in man_polys.items():
        hit = [g for g in groups.values()
               if not g.is_manifold and ent["poly"].intersects(_box(*g.bbox))]
        if not hit:
            continue
        if len(hit) >= 2:
            # this manifold's copper BINDS >=2 terminal clusters -- it is
            # attach copper of the winning terminal, not insurance (the
            # single-owner whitelist keeps one layer of it)
            ganged[name] = len(hit)
        keep = hit[0]
        keep.is_manifold = True
        keep.attach = ent["poly"]
        keep.man_layers = {l for l in ent["layers"] if l in layers}
        keep.native = set(l for l in ent["layers"] if l in layers) | keep.native
        for g in hit[1:]:
            keep.merged.append(g.gid)
            keep.cells.extend(g.cells)
            keep.native |= g.native
            del groups[g.gid]

    # guaranteed-patch cover: the patch is sanctioned F landing copper
    for d in patch_dicts:
        if d.get("net") != net:
            continue
        p = _poly_of(d.get("polygon") or ())
        for g in groups.values():
            if p.intersects(_box(*g.bbox)):
                g.f_zone = p if g.f_zone is None else g.f_zone.union(p)

    # pour eligibility (the F choke, planner-side): an F-only SMD group is
    # pour-servable only where top copper is admitted -- inside a shunt
    # neighborhood, its own manifold, or its guaranteed patch. Everything
    # else is honestly delegated to FR (same boundary _excludable_pad draws
    # for the reservation's pour-owned pads).
    sb_polys = [_box(*b) for b in shunt_boxes]
    for g in groups.values():
        if g.native - {"F.Cu"}:
            continue                                   # THT / inner / B-SMD
        gb = _box(*g.bbox)
        # g.f_zone stays REAL laid F copper (guaranteed patch) only -- the
        # shunt boxes are an ADMIT region, not copper, and must never make
        # a landing patch look redundant.
        admitted = (any(sp.intersects(gb) for sp in sb_polys)
                    or g.is_manifold
                    or (g.f_zone is not None and g.f_zone.intersects(gb)))
        if not admitted:
            g.eligible = False
            g.why = "F-only SMD outside top-copper admit (FR keeps it)"
    return (sorted(groups.values(), key=lambda g: g.gid), clab,
            None, ganged)


def _own_track_polys(board, nc, layers):
    """Own-net PCB_TRACK capsules per layer (mm shapely) -- the board's
    ALREADY-PRESENT corridors (locked force rails, pre-laid stubs)."""
    out = {lay: [] for lay in layers}
    lay_ids = {board.GetLayerID(lay): lay for lay in layers}
    for t in board.GetTracks():
        if t.GetClass() != "PCB_TRACK" or t.GetNetCode() != nc:
            continue
        lay = lay_ids.get(t.GetLayer())
        if lay is None:
            continue
        w = t.GetWidth() / MM / 2.0
        s, e = t.GetStart(), t.GetEnd()
        out[lay].append(LineString(
            [(s.x / MM, s.y / MM), (e.x / MM, e.y / MM)]).buffer(
                max(w, 0.05), quad_segs=4))
    return out


def _preconnect_merge(groups, layers, anchors, grid, own_tracks):
    """MANDATE PART 1 (2026-07-25, live-probe measured): on live skeletons
    the materialize-laid LOCKED force rails already connect most of a rail
    net's terminal groups (+5V_MAIN {1,2,3}; /SENSE3V3_LO ALL FIVE -- the
    598mm2 s510 amoeba re-solved a net that was already done). Same-net
    existing copper is an ALREADY-PRESENT corridor, never an obstacle:
    union-find the groups over the anchor rasters (which include own
    tracks), fusing layers at multi-layer anchor cells (THT barrels/vias),
    and MERGE groups sharing a component into one super-group whose
    per-layer attach geometry is the member copper PLUS the connecting
    track capsules on that layer. Corridors are then planned only for the
    residual components. Returns the merged, re-sorted group list."""
    from scipy import ndimage
    stl = ndimage.generate_binary_structure(2, 1)
    comp = {}
    for lay in layers:
        comp[lay], _n = ndimage.label(anchors[lay], structure=stl)
    parent = {}

    def find(x):
        while parent.get(x, x) != x:
            parent[x] = parent.get(parent[x], parent[x])
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    for i in range(len(layers)):
        for j in range(i + 1, len(layers)):
            both = anchors[layers[i]] & anchors[layers[j]]
            ys, xs = np.where(both)
            for y, x in zip(ys.tolist(), xs.tolist()):
                a = (layers[i], int(comp[layers[i]][y, x]))
                b = (layers[j], int(comp[layers[j]][y, x]))
                if a[1] and b[1]:
                    union(a, b)
    # a group is ONE terminal: every raster component ANY of its cells
    # touches (on any layer) fuses through it -- a manifold-ganged group's
    # clusters span several components by construction, and the first-cell
    # shortcut mis-rooted exactly those (measured: J1/TB gangs never merged
    # across their rail)
    for g in groups:
        tags = []
        for lay in layers:
            for (r, c) in g.cells:
                v = int(comp[lay][r, c])
                if v:
                    tags.append((lay, v))
        for t in tags[1:]:
            union(tags[0], t)
    by_root = {}
    for g in groups:
        gtag = None
        for lay in layers:
            for (r, c) in g.cells:
                v = int(comp[lay][r, c])
                if v:
                    gtag = find((lay, v))
                    break
            if gtag:
                break
        by_root.setdefault(gtag, []).append(g)
    out = []
    for root, members in by_root.items():
        if root is None or len(members) == 1:
            out.extend(members)
            continue
        keep = members[0]
        for g in members[1:]:
            keep.merged.append(g.gid)
            keep.cells.extend(g.cells)
            keep.native |= g.native
            keep.man_layers |= g.man_layers
            keep.is_manifold = keep.is_manifold or g.is_manifold
            keep.eligible = keep.eligible or g.eligible
            if g.f_zone is not None:
                keep.f_zone = (g.f_zone if keep.f_zone is None
                               else keep.f_zone.union(g.f_zone))
            keep.attach = keep.attach.union(g.attach)
            keep.bbox = (min(keep.bbox[0], g.bbox[0]),
                         min(keep.bbox[1], g.bbox[1]),
                         max(keep.bbox[2], g.bbox[2]),
                         max(keep.bbox[3], g.bbox[3]))
        keep.cx = (keep.bbox[0] + keep.bbox[2]) / 2.0
        keep.cy = (keep.bbox[1] + keep.bbox[3]) / 2.0
        # per-layer attach copper: member pieces native to the layer + the
        # own-track capsules touching the merged extent (two passes cover
        # track chains). The hollow union bbox is NEVER an attach target.
        la = {}
        hull = keep.attach
        for lay in layers:
            parts = []
            for g in members:
                if lay in g.native:
                    parts.append(g.attach if g.is_manifold
                                 and lay in g.man_layers
                                 else _box(*g.bbox))
            cand_tr = list(own_tracks.get(lay, ()))
            tr_ids = {id(t) for t in cand_tr if t.intersects(hull)}
            for _pass in range(2):
                if not tr_ids:
                    break
                cur = unary_union([t for t in cand_tr if id(t) in tr_ids])
                more = {id(t) for t in cand_tr
                        if id(t) not in tr_ids and t.intersects(cur)}
                if not more:
                    break
                tr_ids |= more
            parts.extend(t for t in cand_tr if id(t) in tr_ids)
            if parts:
                la[lay] = unary_union(parts)
                keep.native.add(lay)
        keep.lay_attach = la
        if la:
            keep.attach = unary_union(list(la.values()))
        out.append(keep)
    out.sort(key=lambda g: g.gid)
    return out


# ---------------------------------------------------------------------------
# corridor path search: direct -> one-bend -> bounded corner Dijkstra
# ---------------------------------------------------------------------------
class _LayerSpace:
    """Configuration space for one (net, layer, width): free = planning
    region minus obstacles inflated by w/2 + EPS; corner candidates from the
    obstacles inflated a hair more (strictly free bend points).

    *approach* + *half_neck* (the ANCHOR-APPROACH NECK, geometric twin of
    _prep_overunder_net's raster taper): within the approach region (own
    pads + ~3mm), the free space additionally admits centerlines that are
    legal at the NECK width only -- the pad is the physical width
    bottleneck there, and a short pad-adjacent neck is thermally fine.
    Measured necessity (s464): the J3 THT barrel belt closes every 4.2mm
    pin gap at trunk width + guard on every layer, walling the connector
    manifolds off the board; the true-clearance 0.8mm passage beside the
    net's own pin is the only way out, exactly the passage the raster
    search always used."""

    def __init__(self, region, obstacles, half_w, f_allow=None,
                 approach=None, half_neck=None, neck_unguard=0.0):
        infl = [o.buffer(half_w + EPS, join_style=2, mitre_limit=2.0)
                for o in obstacles]
        self._union = unary_union(infl) if infl else None
        free = region
        if f_allow is not None:
            free = free.intersection(f_allow.buffer(-half_w)
                                     if not f_allow.is_empty else f_allow)
        if self._union is not None:
            free = free.difference(self._union)
        self.free_main = free
        self.neck = None
        corner_src = [o.buffer(half_w + 3 * EPS, join_style=2,
                               mitre_limit=2.0) for o in obstacles]
        if approach is not None and half_neck and not approach.is_empty:
            neck = approach.intersection(region)
            if f_allow is not None:
                neck = neck.intersection(f_allow)      # categorical F rule
            # the neck is raster-exempt terminal-zone copper, so the
            # raster-safety guard baked into *obstacles* only builds false
            # walls here -- *neck_unguard* backs it out (measured: with the
            # guard the free ring beside an own J3 pin shrinks to ~0.5mm
            # and every perimeter attach point misses it)
            infl_t = [o.buffer(half_neck + EPS - neck_unguard,
                               join_style=2, mitre_limit=2.0)
                      for o in obstacles]
            u_t = unary_union(infl_t) if infl_t else None
            if u_t is not None:
                neck = neck.difference(u_t)
            if not neck.is_empty:
                self.neck = neck
                near = approach.buffer(2.0)
                corner_src += [o.buffer(half_neck + 3 * EPS - neck_unguard,
                                        join_style=2,
                                        mitre_limit=2.0).intersection(near)
                               for o in obstacles]
        self.free = (free.union(self.neck) if self.neck is not None
                     else free)
        self._prep = prep(self.free) if not self.free.is_empty else None
        cu = unary_union([c for c in corner_src if not c.is_empty]) \
            if corner_src else None
        self.corners = []
        if cu is not None:
            for g in getattr(cu, "geoms", [cu]):
                if g.geom_type != "Polygon":
                    continue
                rings = [g.exterior] + list(g.interiors)
                for ring in rings:
                    self.corners.extend(list(ring.coords)[:-1])

    def ok_pt(self, p):
        return self._prep is not None and self._prep.covers(Point(p))

    def ok_line(self, a, b):
        if self._prep is None:
            return False
        return self._prep.covers(LineString([a, b]))


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _find_path(space, p_from, p_to, *, max_corners=64):
    """Centerline polyline p_from -> p_to in *space*. Returns (pts, bends)
    or (None, None). Direct, then one bend (axis + obstacle corners), then
    a bounded visibility Dijkstra over the corner graph."""
    if not (space.ok_pt(p_from) and space.ok_pt(p_to)):
        return None, None
    if space.ok_line(p_from, p_to):
        return [p_from, p_to], 0
    sx, sy = p_from
    tx, ty = p_to
    cands = [(sx, ty), (tx, sy)]
    reg = _box(min(sx, tx), min(sy, ty), max(sx, tx),
               max(sy, ty)).buffer(12.0)
    corners = [c for c in space.corners if reg.covers(Point(c))]
    if len(corners) > max_corners:
        mid = ((sx + tx) / 2.0, (sy + ty) / 2.0)
        corners.sort(key=lambda c: _dist(c, mid))
        corners = corners[:max_corners]
    best = None
    for c in cands + corners:
        if space.ok_line(p_from, c) and space.ok_line(c, p_to):
            L = _dist(p_from, c) + _dist(c, p_to)
            if best is None or L < best[0]:
                best = (L, [p_from, tuple(c), p_to])
    if best is not None:
        return best[1], 1
    # bounded visibility Dijkstra (>= 2 bends; still sparse geometry)
    import heapq
    nodes = [tuple(p_from)] + [tuple(c) for c in corners] + [tuple(p_to)]
    n = len(nodes)
    if n < 3:
        return None, None
    seen_edge = {}

    def vis(i, j):
        key = (min(i, j), max(i, j))
        if key not in seen_edge:
            seen_edge[key] = space.ok_line(nodes[i], nodes[j])
        return seen_edge[key]

    dist = {0: 0.0}
    par = {}
    heap = [(0.0, 0)]
    while heap:
        d, i = heapq.heappop(heap)
        if d > dist.get(i, float("inf")):
            continue
        if i == n - 1:
            break
        for j in range(n):
            if j == i:
                continue
            if not vis(i, j):
                continue
            nd = d + _dist(nodes[i], nodes[j]) + 1.5   # bend tax per hop
            if nd < dist.get(j, float("inf")):
                dist[j] = nd
                par[j] = i
                heapq.heappush(heap, (nd, j))
    if (n - 1) not in par and (n - 1) not in dist:
        return None, None
    if dist.get(n - 1) is None:
        return None, None
    pts = [nodes[n - 1]]
    i = n - 1
    while i != 0:
        i = par.get(i)
        if i is None:
            return None, None
        pts.append(nodes[i])
    pts.reverse()
    return pts, max(0, len(pts) - 2)


# ---------------------------------------------------------------------------
# the planner
# ---------------------------------------------------------------------------
class _Corridor:
    __slots__ = ("net", "ga", "gb", "cands", "pick", "split", "tapered",
                 "diag")

    def __init__(self, net, ga, gb):
        self.net = net
        self.ga, self.gb = ga, gb
        self.cands = []           # [{layer, pts, poly, bends, length, taper}]
        self.pick = None          # chosen candidate (dict)
        self.split = None         # {"at": (x,y), "lay2": str, "poly2": poly}
        self.tapered = False
        self.diag = {}            # {layer: why-no-candidate}


def _attach_point(g, toward, half_w, native, space=None):
    """Attach point for group *g* aiming toward *toward* (a Point).
    Manifold groups attach on (manifold INTERSECT the corridor's own free
    space) -- the geometric width-margin attach: a centerline point there
    is on the manifold AND provably clear of foreign copper at width (the
    raster rule's erode(manifold, w/2) analogue, which additionally sees
    the foreign barrels INSIDE a connector manifold; plain nearest-point on
    the eroded polygon strands in the pin field -- measured on s464, every
    manifold net failed with 'no conflict-free layer' before this).
    A NATIVE-layer pad group (the corridor's layer is one the group
    anchors) attaches ON the pad group itself -- the copper must reach the
    pads, no via field exists to bridge a standoff gap. A FOREIGN-layer
    attach lands at a via-spot ring position just outside the pad bbox
    (the terminal field goes there, never in the pads)."""
    if g.is_manifold:
        tgt = None
        if space is not None and space._prep is not None:
            t = g.attach.intersection(space.free)
            if not t.is_empty:
                tgt = t
        if tgt is None:
            core = g.attach.buffer(-half_w)
            tgt = core if not core.is_empty else g.attach
        return tuple(nearest_points(tgt, toward)[0].coords[0]), True
    if native:
        return tuple(nearest_points(_box(*g.bbox),
                                    toward)[0].coords[0]), True
    x0, y0, x1, y1 = g.bbox
    cx, cy = g.cx, g.cy
    dx, dy = toward.x - cx, toward.y - cy
    L = math.hypot(dx, dy) or 1.0
    ex = (x1 - x0) / 2.0 + SPOT_OFFSET_MM
    ey = (y1 - y0) / 2.0 + SPOT_OFFSET_MM
    return (cx + dx / L * ex, cy + dy / L * ey), True


def _ring_spots(g):
    """Candidate via-spot positions around a pad group: 8 directions x 3
    radii (a contested gap can swallow the whole near ring -- measured on
    s464, /SENSE5V_HI's island beside a claimed +3V3 corridor; a spot one
    step farther is still inside the APPROACH_MM terminal zone)."""
    x0, y0, x1, y1 = g.bbox
    out = []
    for off in (SPOT_OFFSET_MM, SPOT_OFFSET_MM + 0.8,
                min(APPROACH_MM - 0.4, SPOT_OFFSET_MM + 1.6)):
        ex = (x1 - x0) / 2.0 + off
        ey = (y1 - y0) / 2.0 + off
        for (ux, uy) in ((1, 0), (-1, 0), (0, 1), (0, -1),
                         (0.71, 0.71), (-0.71, 0.71), (0.71, -0.71),
                         (-0.71, -0.71)):
            out.append((g.cx + ux * ex, g.cy + uy * ey))
    return out


def plan_pours(board, asks, *, cell_mm=0.8, clearance_mm=0.3,
               manifolds=True, collect=None, fallback=None):
    """v4 entry point -- same contract as
    cec_slab_pour.synthesize_overunder_pours: returns (pour_dicts, via_list,
    report) and fills *collect* with per-net reservation internals
    ({ok, path_cells, bridges, rcells, foreign, reqw} + "_grid").

    *fallback*: callable(board, ask, collect_slot) -> (dicts, vias, rep_entry)
    for a net the planner cannot place (default: route_overunder via
    synthesize_overunder_pours, loudly labeled). Pass a recorder in tests."""
    grid = Grid(board, cell_mm)
    if collect is not None:
        collect["_grid"] = grid
    nets_nc = {n.GetNetname(): c
               for c, n in board.GetNetInfo().NetsByNetcode().items()}
    net_currents = _net_currents()
    shunt_boxes = shunt_neighborhoods(board)
    region = _box(grid.x0, grid.y0, grid.x1, grid.y1)
    # ALL pad boxes, any net (assembly-class via-in-pad exclusion, owner
    # ruling 2026-07-25: no via barrel in/overlapping ANY pad -- the
    # foreign-copper guards exempt same-net pads by construction, which
    # was the measured gap) + the inter-pad GAP strips (pour-termination
    # ruling: the gap belongs exclusively to the Kelvin tap stubs).
    pad_boxes = []
    _outer_ids = {board.GetLayerID("F.Cu"), board.GetLayerID("B.Cu")}
    for fp in board.GetFootprints():
        for p in fp.Pads():
            # the assembly-class exclusion is a SOLDER-surface rule: only
            # pads with an OUTER copper face (SMD lands, THT annuli) repel
            # vias; an inner-layer-only pad shape has no solder surface
            # and a barrel through it is ordinary plane contact
            if not (_outer_ids & set(p.GetLayerSet().CuStack())):
                continue
            bb = p.GetBoundingBox()
            pad_boxes.append((bb.GetLeft() / MM, bb.GetTop() / MM,
                              bb.GetRight() / MM, bb.GetBottom() / MM))
    gap_strips = [sh["gap"] for sh in _sp._shunt_pad_halves(board)]
    gap_geom = (unary_union([_box(*gsp) for gsp in gap_strips])
                if gap_strips else None)

    pour_dicts, via_list, report = [], [], {}

    # stage 0: manifolds (v3.1, proven) -- laid first, lead the dict list
    ask_nets = []
    for a in asks:
        n = a.get("net")
        if n and n != "GND" and n in nets_nc and n not in ask_nets:
            ask_nets.append(n)
    man_by_net = {}
    if manifolds:
        for md in connector_manifolds(board, nets=set(ask_nets)):
            man_by_net.setdefault(md["net"], []).append(md)
        for _mn in sorted(man_by_net):
            pour_dicts.extend(man_by_net[_mn])
    patch_dicts = guaranteed_shunt_patches(board)

    # net order: heavier rails first (they claim In2 first), then name
    order = sorted(ask_nets,
                   key=lambda n: (-(net_currents.get(n) or 0.0), n))
    ask_by_net = {}
    for a in asks:
        if a.get("net") in nets_nc:
            ask_by_net.setdefault(a["net"], a)

    # ---- phase A: per-net prep + terminal groups + corridor candidates ----
    nets = {}
    for net in order:
        nc = nets_nc[net]
        layers = [l for l in LAYERS_ALL if board.GetLayerID(l) >= 0]
        if not layers:
            report[net] = _fail_entry("no valid layer")
            continue
        foreign, anchors = {}, {}
        for lay in layers:
            f, an = rasterize(board, nc, board.GetLayerID(lay), grid,
                              clearance_mm)
            foreign[lay], anchors[lay] = f, an
        amps = net_currents.get(net, 0.0)
        reqw = {lay: (req_width_mm(amps, lay) if amps > 0 else 1.2)
                for lay in layers}
        rcells = {lay: max(1, int(round(reqw[lay] / (2.0 * grid.cell))))
                  for lay in layers}
        groups, clab, why, gang_man = _build_groups(
            board, net, nc, grid, layers, anchors,
            man_by_net.get(net, ()), patch_dicts, shunt_boxes)
        own_tracks = _own_track_polys(board, nc, layers)
        if not why and groups:
            n_before = len(groups)
            groups = _preconnect_merge(groups, layers, anchors, grid,
                                       own_tracks)
            if len(groups) < n_before:
                print("[cec_pour_plan] %s: %d group(s) pre-connected by "
                      "existing copper -> %d planning group(s)"
                      % (net, n_before, len(groups)), file=sys.stderr)
        # own-net stage-0 copper (manifolds + guaranteed patches): part of
        # the realized state, so the connectivity verifier must see it --
        # it is the copper that carries corridor-to-pad attach inside a
        # manifold. NEVER clearance-checked (v3.1 contract: pad-anchored by
        # construction, the filler carves true clearances at fill time).
        own_pours = [(d.get("layer", "F.Cu"), _poly_of(d["polygon"]))
                     for d in man_by_net.get(net, ())]
        own_pours += [("F.Cu", _poly_of(d["polygon"]))
                      for d in patch_dicts if d.get("net") == net]
        if why:
            report[net] = _fail_entry(why)
            if collect is not None:
                collect[net] = {"ok": False, "path_cells": {}, "bridges": [],
                                "rcells": {}, "foreign": {}, "reqw": {}}
            continue
        served = [g for g in groups if g.eligible]
        delegated = [g for g in groups if not g.eligible]
        nets[net] = {
            "nc": nc, "layers": layers, "foreign": foreign,
            "anchors": anchors, "reqw": reqw, "rcells": rcells,
            "groups": groups, "served": served, "delegated": delegated,
            "clab": clab, "corridors": [], "notes": [], "region": region,
            "own_pours": own_pours, "_grid": grid, "pad_boxes": pad_boxes,
            "gap_geom": gap_geom, "gang_man": gang_man,
        }
        if len(served) <= 1:
            nets[net]["trivial"] = (
                "single pour-eligible terminal group (nothing to connect"
                + (" -- existing copper pre-connects the rest)"
                   if any(g.merged for g in served) else ")"))
            continue
        # REGION-CLASS (mandate part 2): many-island logic nets take the
        # power-plane doctrine at realization time (phase D); no corridor
        # machinery is built for them.
        if _classify_net(nets[net]) == "region":
            nets[net]["net_class"] = "region"
            print("[cec_pour_plan] %s: region-class (%d served groups) -- "
                  "power-plane doctrine" % (net, len(served)),
                  file=sys.stderr)
            continue
        # geometric obstacle space per layer (guard = raster-safety
        # standoff: 0.75*cell + EPS clears the verifier's half-diagonal
        # cell reach, so geometric legality is never looser than the raster)
        obst = _geo_obstacles(board, nc, layers, clearance_mm,
                              0.75 * grid.cell)
        # foreign manifolds / patches are obstacles on their layer
        for on, mds in man_by_net.items():
            if on == net:
                continue
            for d in mds:
                if d.get("layer") in obst:
                    obst[d["layer"]].append(
                        _poly_of(d["polygon"]).buffer(clearance_mm))
        for d in patch_dicts:
            if d.get("net") != net and "F.Cu" in obst:
                obst["F.Cu"].append(
                    _poly_of(d["polygon"]).buffer(clearance_mm))
        # F-allow region (categorical top rule; empty shunt set = no choke,
        # matching add_power_pours' own behavior)
        f_allow = None
        if shunt_boxes:
            parts = [_box(*b) for b in shunt_boxes]
            for d in man_by_net.get(net, ()):
                if d.get("layer") == "F.Cu":
                    parts.append(_poly_of(d["polygon"]))
            for g in groups:
                if g.f_zone is not None:
                    parts.append(g.f_zone)
            f_allow = unary_union(parts)
            if gap_strips:
                # pour-termination ruling: F corridors never enter the
                # inter-pad gap (the taps' exclusive territory)
                f_allow = f_allow.difference(
                    unary_union([_box(*gsp) for gsp in gap_strips]))
        # anchor-approach region for the neck sub-space: own pads + own
        # MANIFOLD polygons + own TRACK capsules (mandate part 1, probe-
        # measured: the collar between a manifold's outer face and eroded
        # free space sealed every wide net inside the J3/TB belts -- the
        # neck legitimacy extends around ALL own copper, not just pads;
        # a manifold/rail is the "pad" of its super-terminal)
        own_boxes = []
        for fp in board.GetFootprints():
            for p in fp.Pads():
                if p.GetNetCode() != nc:
                    continue
                bb = p.GetBoundingBox()
                own_boxes.append(_box(bb.GetLeft() / MM, bb.GetTop() / MM,
                                      bb.GetRight() / MM,
                                      bb.GetBottom() / MM))
        for d in man_by_net.get(net, ()):
            if d.get("polygon"):
                own_boxes.append(_poly_of(d["polygon"]))
        for _tl in own_tracks.values():
            own_boxes.extend(_tl)
        approach = (unary_union([b.buffer(APPROACH_MM) for b in own_boxes])
                    if own_boxes else None)
        spaces = {}
        for lay in layers:
            spaces[lay] = _LayerSpace(
                region, obst[lay], reqw[lay] / 2.0,
                f_allow=f_allow if lay == "F.Cu" else None,
                approach=approach, half_neck=W_NECK / 2.0,
                neck_unguard=0.75 * grid.cell)
        nets[net]["spaces"] = spaces
        nets[net]["obst"] = obst
        nets[net]["f_allow"] = f_allow
        nets[net]["approach"] = approach

        # Prim tree over served groups (attach-geometry distance)
        tree = [served[0]]
        rest = list(served[1:])
        while rest:
            best = None
            for g in rest:
                for t in tree:
                    d = t.attach.distance(g.attach)
                    if best is None or d < best[0]:
                        best = (d, t, g)
            _d, ta, gb = best
            rest.remove(gb)
            tree.append(gb)
            nets[net]["corridors"].append(_Corridor(net, ta, gb))
        # group incidence: the canonical-spot rule binds only groups SHARED
        # by 2+ corridors (the one terminal field must serve them all); a
        # leaf group's single corridor re-chooses its attach freely (the
        # dodge re-plan needs that freedom -- measured on s464, leaf stubs
        # pinned to a spot inside a contested gap could never dodge)
        inc = {}
        for cor in nets[net]["corridors"]:
            for g in (cor.ga, cor.gb):
                inc[id(g)] = inc.get(id(g), 0) + 1
        nets[net]["inc"] = inc

        # per-corridor per-layer candidates
        for cor in nets[net]["corridors"]:
            _make_candidates(cor, nets[net], grid)

    # ---- phase B: exact layer assignment (branch and bound) ----
    _assign_layers(nets, order)

    # ---- phase C: conflict repair for corridors left unassigned --
    # first a same-layer geometric DODGE around the assigned foreign
    # corridors (re-plan with the conflict as an obstacle -- no via field),
    # then the crossing SPLIT (one defined crossing, one compact field) ----
    for net in order:
        st = nets.get(net)
        if not st:
            continue
        for cor in st["corridors"]:
            if cor.pick is None:
                if _replan_blocked(cor, st, nets, grid):
                    continue
                if cor.cands:
                    _try_split(cor, st, nets)

    # ---- phase D: realize + verify (one re-plan, then fallback) ----
    existing_vias = []
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA":
            p = t.GetPosition()
            existing_vias.append((p.x / MM, p.y / MM))
    for net in order:
        st = nets.get(net)
        if st is None:
            continue
        if st.get("net_class") == "region":
            entry, dicts, vias = _realize_region(net, st, grid,
                                                 existing_vias)
        else:
            entry, dicts, vias = _realize_verify(net, st, grid,
                                                 existing_vias, nets)
        if st.get("gang_man"):
            # ganged manifolds are attach copper of the winning terminal --
            # the whitelist (enumerate_winning) keeps one layer of each
            entry["gang_manifolds"] = dict(st["gang_man"])
        if entry.get("path_found"):
            for v in vias:
                existing_vias.append((v["x_mm"], v["y_mm"]))
            pour_dicts.extend(dicts)
            via_list.extend(vias)
            report[net] = entry
            if collect is not None:
                collect[net] = _collect_entry(
                    st, grid, dicts, vias,
                    ok=bool(entry.get("path_found")))
            _say(net, entry)
            continue
        # planner failure -> loud fallback
        ask = ask_by_net.get(net) or {"net": net, "layers": ("In2.Cu",)}
        sub = {}
        if fallback is not None:
            fdicts, fvias, fent = fallback(board, ask, sub)
        else:
            fdicts, fvias, fent = _default_fallback(board, ask, sub,
                                                    manifolds, man_by_net)
        fent = dict(fent or {})
        fent["fallback"] = "route_overunder"
        fent["planner_reason"] = entry.get("reason") or entry.get("bottleneck")
        if st.get("gang_man"):
            fent["gang_manifolds"] = dict(st["gang_man"])
        print("[cec_pour_plan] %s: PLANNER FAILED (%s) -- FALLBACK to "
              "route_overunder (path_found=%s)"
              % (net, fent["planner_reason"], fent.get("path_found")),
              file=sys.stderr)
        for v in fvias:
            existing_vias.append((v["x_mm"], v["y_mm"]))
        pour_dicts.extend(fdicts)
        via_list.extend(fvias)
        report[net] = fent
        if collect is not None:
            collect[net] = sub.get(net) or {
                "ok": bool(fent.get("path_found")), "path_cells": {},
                "bridges": [], "rcells": {}, "foreign": {}, "reqw": {}}
    return pour_dicts, via_list, report


def _fail_entry(reason):
    return {"path_found": False, "segments": 0, "bridges": 0,
            "layers_used": [], "reason": reason, "planner": "territory"}


def _say(net, entry):
    vf = entry.get("via_fields") or {}
    print("[cec_pour_plan] %s: %s -- %d corridor(s), %d bend(s), via fields "
          "terminal=%d crossing=%d, layers %s%s"
          % (net, ("region-planned on %s" % entry.get("region_layer")
                   if entry.get("planner") == "territory-region"
                   else "planned") if entry.get("path_found") else "trivial",
             entry.get("corridors", 0), entry.get("bends", 0),
             vf.get("terminal", 0), vf.get("crossing", 0),
             entry.get("layers_used", []),
             (" [delegated: %d]" % entry["groups"]["delegated"])
             if entry.get("groups", {}).get("delegated") else ""),
          file=sys.stderr)


def _default_fallback(board, ask, sub, manifolds, man_by_net):
    """The demoted direction-state Dijkstra, one net, loudly labeled.
    The net's manifolds were already laid by plan_pours' stage 0, so they
    ride in as manifold_dicts (attach inputs ONLY, never re-laid/returned)
    -- the fallback search keeps the v3.1 width-margin attach instead of
    losing it (2026-07-25)."""
    dicts, vias, rep = _sp.synthesize_overunder_pours(
        board, [dict(ask)], manifolds=False, collect=sub,
        manifold_dicts=man_by_net.get(ask.get("net"), ()))
    ent = rep.get(ask.get("net")) or {}
    return dicts, vias, ent


def _manifold_attach_pts(g, toward, space, cap=6):
    """Attach candidates on (manifold INTERSECT free space): the nearest
    point of EACH connected component, nearest component first. A component
    can be a walled pocket between connector pin rows (measured on s464:
    +5VSB/J3's nearest sliver had no route out on B.Cu) -- so alternates
    matter: the path search walks the components until one connects."""
    if space._prep is None:
        return []
    t = g.attach.intersection(space.free)
    if t.is_empty:
        return []
    comps = [c for c in getattr(t, "geoms", [t])
             if c.geom_type in ("Polygon", "LineString", "Point")
             and not c.is_empty]
    comps.sort(key=lambda c: c.distance(toward))
    return [tuple(nearest_points(c, toward)[0].coords[0])
            for c in comps[:cap]]


VIA_R = _sp.VIA_R        # add_overunder_vias default barrel dia 0.9 / 2
PAD_MARGIN = _sp.PAD_MARGIN
_pad_hit = _sp._pad_hit  # shared conservative square test (one authority)


def _spot_ok(st, g, pt):
    """Via-spot validity beyond free space: (a) the assembly-class pad
    standoff (via-in-pad ruling -- the spot's CENTER via must clear every
    pad, own net included); (b) for a patch-covered shunt-pad group the
    spot must sit INSIDE the (inner-edge-clipped) patch -- the outer-face
    rule of the pour-termination ruling by construction (the patch no
    longer exists gap-side of the pad)."""
    if _pad_hit(st.get("pad_boxes", ()), pt[0], pt[1], VIA_R + PAD_MARGIN):
        return False
    if g.f_zone is not None and not g.f_zone.covers(Point(pt)):
        return False
    return True


def _field_vias(field6, half_w, grid, pad_boxes, placed, *, pitch_mm=1.2,
                ledger_mm=0.85):
    """Via positions for ONE compact field -- DELEGATES to the shared
    cec_slab_pour.field_via_line (2026-07-25: the rect-realized fallback
    lays fields through the identical code path, so the two via
    disciplines can never drift). Same signature/return as always."""
    return _sp.field_via_line(field6, half_w, grid, pad_boxes, placed,
                              pitch_mm=pitch_mm, ledger_mm=ledger_mm)


def _endpoints_for_layer(cor, st, lay, space):
    """(pa, spot_a, alts_a, pb, spot_b, alts_b) endpoint resolution for one
    corridor on one layer -- shared by the static candidate pass and the
    conflict re-plan so attach semantics can never drift. A None point =
    every candidate spot failed the via-spot validity (_spot_ok)."""
    ga, gb = cor.ga, cor.gb
    half = st["reqw"][lay] / 2.0

    def _endpoint(g, toward):
        native = lay in g.native
        if g.is_manifold and lay in g.man_layers:
            # manifold-polygon attach only where the manifold has COPPER
            pts = _manifold_attach_pts(g, toward, space)
            if pts:
                return pts[0], False, tuple(pts[1:])
            return (_attach_point(g, toward, half, native,
                                  space=space)[0], False, ())
        la = (g.lay_attach or {}).get(lay) if native else None
        if la is not None and not la.is_empty:
            # PRE-CONNECTED super-group (mandate part 1): attach ON the
            # per-layer copper (member pads + connecting rails) -- the
            # union bbox is hollow and must never be the target. Alternates
            # walk the components (nearest first) + boundary samples of the
            # nearest component (a long rail offers many departure points).
            comps = sorted(getattr(la, "geoms", [la]),
                           key=lambda c: c.distance(toward))
            alts = []
            for c in comps[:8]:
                alts.append(tuple(nearest_points(c, toward)[0].coords[0]))
            b0 = getattr(comps[0], "exterior", None)
            if b0 is not None:
                cs = list(b0.coords)[:-1]
                step = max(1, len(cs) // 6)
                alts.extend(tuple(q) for q in cs[::step][:6])
            return alts[0], False, tuple(alts[1:])
        if g.is_manifold and native:
            # off-manifold layer: attach the pin group's own copper (THT
            # barrels anchor every layer) -- the neck admits the approach.
            # Alternates: bbox perimeter + the group's own CELL CENTERS
            # (contact preserved by construction -- a manifold gang merges
            # several pin clusters, and only its first cluster is in bbox;
            # a far pin at the barrel-field edge may hold the only exit).
            x0, y0, x1, y1 = g.bbox
            xm, ym = (x0 + x1) / 2.0, (y0 + y1) / 2.0
            alts = [(xm, y0), (xm, y1), (x0, ym), (x1, ym),
                    (x0, y0), (x1, y0), (x0, y1), (x1, y1)]
            cells = g.cells
            step = max(1, len(cells) // 12)
            gr = st.get("_grid")
            if gr is not None:
                for (r, c) in cells[::step][:12]:
                    alts.append((gr.x0 + (c + 0.5) * gr.cell,
                                 gr.y0 + (r + 0.5) * gr.cell))
            return (tuple(nearest_points(_box(*g.bbox),
                                         toward)[0].coords[0]),
                    False, tuple(alts))
        if native:
            return (_attach_point(g, toward, half, True,
                                  space=space)[0], False, ())
        shared = st.get("inc", {}).get(id(g), 1) > 1
        if g.spot is not None and shared:
            return g.spot, True, ()        # canonical spot, no alternates
        # via-spot validity filter (via-in-pad + pour-termination rulings):
        # the default + every ring alternate must clear pads and, for a
        # patch-covered shunt group, sit inside the clipped patch (outer
        # face). All blocked -> None (no candidate on this layer).
        cands = [_attach_point(g, toward, half, False, space=space)[0]]
        cands += _ring_spots(g)
        ok = [pt for pt in cands if _spot_ok(st, g, pt)]
        if not ok:
            return None, shared, ()
        return ok[0], shared, tuple(ok[1:])

    pa, spot_a, alts_a = _endpoint(ga, Point(gb.cx, gb.cy))
    pb, spot_b, alts_b = _endpoint(gb, Point(ga.cx, ga.cy))
    return pa, spot_a, alts_a, pb, spot_b, alts_b


def _path_with_alternates(space, pa, alts_a, pb, alts_b):
    """Direct path, then endpoint alternates (ring spots / manifold
    components). Returns (pts, bends) or (None, None). A None endpoint
    (every spot failed via-spot validity) is an immediate no-path."""
    if pa is None or pb is None:
        return None, None
    pts, bends = _find_path(space, pa, pb)
    if pts is None and alts_a:
        for spot in alts_a:
            pts, bends = _find_path(space, spot, pb)
            if pts:
                pa = spot
                break
    if pts is None and alts_b:
        for spot in alts_b:
            pts, bends = _find_path(space, pa, spot)
            if pts:
                pb = spot
                break
    return pts, bends


def _cand_from_path(cor, st, lay, pts, bends, taper, space=None):
    """Candidate from a found centerline. When the path crosses the neck
    sub-space (anchor-approach passage), the realization splits: full-width
    copper clipped to where full width is legal + a W_NECK spine along the
    whole centerline (true-clearance legal by construction of the search).
    The spine is the terminal-zone piece (raster-exempt); the main piece
    stays raster-verified; the width invariant is then honestly W_NECK."""
    width_eff = taper or st["reqw"][lay]
    poly = _capsule(pts, width_eff / 2.0)
    length = sum(_dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
    cand = {"layer": lay, "pts": pts, "poly": poly, "bends": bends,
            "length": length, "taper": taper, "main": poly, "spine": None}
    space = space or st["spaces"].get(lay)
    if space is not None and space.neck is not None:
        line = LineString(pts)
        if not space.free_main.covers(line):
            spine = _capsule(pts, W_NECK / 2.0)
            clip = space.free_main.buffer(width_eff / 2.0 - 0.02,
                                          join_style=2)
            main_piece = poly.intersection(clip)
            cand["main"] = main_piece
            cand["spine"] = spine
            cand["poly"] = unary_union([main_piece, spine])
    return cand


def _make_candidates(cor, st, grid):
    """Per-layer geometry candidates for one corridor."""
    ga, gb = cor.ga, cor.gb
    for lay in st["layers"]:
        space = st["spaces"][lay]
        w = st["reqw"][lay]
        if space._prep is None:
            # the layer's free space is EMPTY at this width (probe-measured:
            # 1oz-internal In2 demands 16-46mm for the heavy rails -- no
            # 74x59 board holds that corridor). Honest diag, not the
            # misleading 'pa-blocked'.
            cor.diag[lay] = "width-infeasible(%.1fmm)" % w
            continue
        pa, spot_a, alts_a, pb, spot_b, alts_b = _endpoints_for_layer(
            cor, st, lay, space)
        taper = None
        pts, bends = _path_with_alternates(space, pa, alts_a, pb, alts_b)
        if pts is None:
            cor.diag[lay] = (
                "pa-spot-padlocked" if pa is None else
                "pb-spot-padlocked" if pb is None else
                "pa-blocked" if not space.ok_pt(pa) else
                "pb-blocked" if not space.ok_pt(pb) else "no-path")
            # TERMINAL TAPER (the pad is the physical bottleneck): allow the
            # last stretch at reduced width by planning in a thinner space,
            # but only for a SHORT stub (<= TAPER_MAX_MM) so no sub-width
            # run ever carries a long span.
            wt = min(w, 1.2)
            if wt < w and pa is not None and pb is not None \
                    and ga.attach.distance(gb.attach) <= TAPER_MAX_MM:
                tsp = st.setdefault("spaces_taper", {})
                if lay not in tsp:
                    tsp[lay] = _LayerSpace(
                        st["region"], st["obst"][lay], wt / 2.0,
                        f_allow=st["f_allow"] if lay == "F.Cu" else None)
                pts, bends = _find_path(tsp[lay], pa, pb)
                if pts:
                    taper = wt
        if pts is None:
            continue
        cor.diag.pop(lay, None)
        # fix the canonical spot on first success (all later corridors
        # incident to the group MUST land at the same point -- the one
        # terminal via field is the only cross-layer bridge there)
        if spot_a and ga.spot is None:
            ga.spot = tuple(pts[0])
        if spot_b and gb.spot is None:
            gb.spot = tuple(pts[-1])
        cor.cands.append(_cand_from_path(cor, st, lay, pts, bends, taper))
    cor.cands.sort(key=lambda c: LAYER_PREF[c["layer"]])


def _assigned_foreign(nets, net, lay):
    """Every other net's standing copper on *lay*: picked corridors, split
    legs, and terminal-zone geometry is NOT included (landings live inside
    pad fields; corridors are the contested territory)."""
    out = []
    for onet, ost in nets.items():
        if onet == net:
            continue
        for oc in ost.get("corridors", ()):
            if oc.pick and oc.pick["layer"] == lay:
                out.append(oc.pick["poly"])
            if oc.split and oc.split["lay2"] == lay:
                out.append(oc.split["poly2"])
    return out


def _replan_blocked(cor, st, nets, grid):
    """Task step 5's re-plan loop, conflict flavor: a corridor whose static
    candidates all clash with other nets' assigned corridors re-plans its
    PATH with those corridors as obstacles (clearance-buffered) -- a
    same-layer geometric dodge, preferred over a crossing split (no via
    field). Returns True and sets cor.pick on success."""
    for lay in st["layers"]:
        if lay in cor.diag:
            continue                       # statically impossible here
        assigned = _assigned_foreign(nets, cor.net, lay)
        if not assigned:
            continue                       # nothing to dodge: real no-cand
        space2 = _LayerSpace(
            st["region"],
            list(st["obst"][lay]) + [p.buffer(0.35) for p in assigned],
            st["reqw"][lay] / 2.0,
            f_allow=st["f_allow"] if lay == "F.Cu" else None,
            approach=st.get("approach"), half_neck=W_NECK / 2.0,
            neck_unguard=0.6)
        pa, spot_a, alts_a, pb, spot_b, alts_b = _endpoints_for_layer(
            cor, st, lay, space2)
        pts, bends = _path_with_alternates(space2, pa, alts_a, pb, alts_b)
        if os.environ.get("CEC_POUR_PLAN_DEBUG"):
            print("[cec_pour_plan][dbg] dodge %s %s->%s on %s: %d foreign "
                  "obstacle(s), pa=%s(%s) pb=%s(%s) -> %s"
                  % (cor.net, cor.ga.gid, cor.gb.gid, lay, len(assigned),
                     tuple(round(v, 1) for v in pa), space2.ok_pt(pa),
                     tuple(round(v, 1) for v in pb), space2.ok_pt(pb),
                     "path %d pts" % len(pts) if pts else "NO PATH"),
                  file=sys.stderr)
        if pts is None:
            continue
        if spot_a and cor.ga.spot is None:
            cor.ga.spot = tuple(pts[0])
        if spot_b and cor.gb.spot is None:
            cor.gb.spot = tuple(pts[-1])
        cor.pick = _cand_from_path(cor, st, lay, pts, bends, None,
                                   space=space2)
        return True
    return False


def _field_needed(group, lay):
    """Does attaching *group* with a corridor on *lay* need a via field?"""
    return lay not in group.native


def _assign_layers(nets, order):
    """Exact branch-and-bound over (corridor -> candidate) with zero
    same-layer inter-net overlap as the HARD constraint, minimizing
    via-field count, then bends, then layer preference + length. Corridors
    ordered net-by-net (heavier first), Prim order within a net (parent
    before child, so terminal-field dedup is well-defined). Falls back to
    greedy-first-fit if the node budget blows (reported)."""
    cors = []
    for net in order:
        st = nets.get(net)
        if not st:
            continue
        cors.extend(st["corridors"])
    if not cors:
        return
    # MOST-CONSTRAINED-FIRST (measured on s464: net-order assignment let
    # the flexible 10-corridor +3V3 system claim the In2 belt before the
    # 2-candidate sense stubs arrived, cornering them; the node cap makes
    # deep global backtracking unreachable, so ordering must carry the
    # weight). Tight corridors claim territory first; flexible ones dodge
    # (phase C re-plan). Stable on the (net-current, Prim) order for ties.
    cors.sort(key=lambda c: len(c.cands))
    ncor = len(cors)
    best = {"cost": float("inf"), "picks": None}
    nodes = [0]

    def _conflict(cand, i, picks):
        # clearance-buffered: two foreign pours may never TOUCH (zone-to-
        # zone clearance is real DRC), so the test runs at +0.3mm standoff
        p = cand["poly"].buffer(0.3)
        lay = cand["layer"]
        for j in range(i):
            cj = picks[j]
            if cj is None or cors[j].net == cors[i].net:
                continue
            if cj["layer"] != lay:
                continue
            if p.intersects(cj["poly"]) and \
                    p.intersection(cj["poly"]).area > 0.01:
                return True
        return False

    def _cand_cost(cor, cand, fielded):
        cost = (LAYER_PREF[cand["layer"]] + BEND_COST * cand["bends"]
                + LEN_COST * cand["length"])
        for g in (cor.ga, cor.gb):
            if _field_needed(g, cand["layer"]) and id(g) not in fielded:
                cost += VIA_FIELD_COST
        return cost

    def dfs(i, cost, picks, fielded):
        nodes[0] += 1
        if nodes[0] > BB_NODE_CAP:
            if nodes[0] == BB_NODE_CAP + 1:
                print("[cec_pour_plan] layer assignment: node budget hit -- "
                      "best-so-far kept (bounded exactness)", file=sys.stderr)
            return
        if cost >= best["cost"]:
            return
        if i == ncor:
            best["cost"] = cost
            best["picks"] = list(picks)
            return
        cor = cors[i]
        any_c = False
        for cand in cor.cands:
            if _conflict(cand, i, picks):
                continue
            any_c = True
            add = _cand_cost(cor, cand, fielded)
            newf = set()
            for g in (cor.ga, cor.gb):
                if _field_needed(g, cand["layer"]) and id(g) not in fielded:
                    newf.add(id(g))
            picks.append(cand)
            fielded |= newf
            dfs(i + 1, cost + add, picks, fielded)
            fielded -= newf
            picks.pop()
        # allow "unassigned" (phase C split repair picks it up) at a stiff
        # price so a single blocked corridor cannot sink the whole net set
        picks.append(None)
        dfs(i + 1, cost + 4.0 * VIA_FIELD_COST, picks, fielded)
        picks.pop()
        return any_c

    dfs(0, 0.0, [], set())
    picks = best["picks"]
    if picks is None:
        # greedy first-fit fallback (budget blown / fully constrained)
        picks = []
        fielded = set()
        for i, cor in enumerate(cors):
            pick = None
            for cand in cor.cands:
                if not _conflict(cand, i, picks):
                    pick = cand
                    break
            picks.append(pick)
            if pick:
                for g in (cor.ga, cor.gb):
                    if _field_needed(g, pick["layer"]):
                        fielded.add(id(g))
        print("[cec_pour_plan] layer assignment: node budget blown -- "
              "greedy first-fit used", file=sys.stderr)
    for cor, pick in zip(cors, picks):
        cor.pick = pick


def _try_split(cor, st, nets):
    """Crossing repair: run the preferred candidate's centerline on layer A
    up to ONE defined crossing point, via field there, remainder on a layer
    where it is conflict-free. Never smeared -- exactly one field."""
    for cand in cor.cands:
        layA = cand["layer"]
        line = LineString(cand["pts"])
        # find the FIRST foreign assigned poly this candidate hits
        # (clearance-buffered: touching is already a conflict)
        cpoly = cand["poly"].buffer(0.3)
        hits = [h for h in _assigned_foreign(nets, cor.net, layA)
                if cpoly.intersects(h)]
        if not hits:
            cor.pick = cand                            # late free candidate
            return True
        cut_t = min((line.project(nearest_points(line, h)[0]) for h in hits))
        back = max(0.0, cut_t - (st["reqw"][layA] / 2.0 + 1.2))
        # back off until leg1 genuinely clears every conflicting poly (the
        # projection lands SOMEWHERE inside the overlap, not at its entry)
        leg1_pts = poly1 = None
        while back > 0.5:
            leg1_pts = _cut_line(cand["pts"], back)
            poly1 = _capsule(leg1_pts, st["reqw"][layA] / 2.0)
            b1 = poly1.buffer(0.3)
            sp_pt = line.interpolate(back)
            if not any(b1.intersects(h)
                       and b1.intersection(h).area > 0.01 for h in hits) \
                    and not _pad_hit(st.get("pad_boxes", ()), sp_pt.x,
                                     sp_pt.y, VIA_R + PAD_MARGIN):
                # crossing FIELD spot must also clear every pad (via-in-pad
                # ruling) -- keep backing off past a pad-blocked spot
                break
            back -= 1.0
        if leg1_pts is None or back <= 0.5:
            continue
        p_split = line.interpolate(back)
        # leg 2 from the split point on another layer
        for layB in st["layers"]:
            if layB == layA:
                continue
            space = st["spaces"][layB]
            pts2, bends2 = _find_path(space,
                                      (p_split.x, p_split.y),
                                      tuple(cand["pts"][-1]))
            if pts2 is None:
                continue
            poly2 = _capsule(pts2, st["reqw"][layB] / 2.0)
            b2 = poly2.buffer(0.3)
            if any(b2.intersects(h) and b2.intersection(h).area > 0.01
                   for h in _assigned_foreign(nets, cor.net, layB)):
                continue
            cor.pick = {"layer": layA, "pts": leg1_pts, "poly": poly1,
                        "bends": max(0, len(leg1_pts) - 2),
                        "length": LineString(leg1_pts).length, "taper": None}
            cor.split = {"at": (p_split.x, p_split.y), "lay2": layB,
                         "pts2": pts2, "poly2": poly2,
                         "bends2": bends2}
            return True
    return False


def _cut_line(pts, dist):
    """Prefix of polyline *pts* up to arc-length *dist* (endpoint appended)."""
    out = [tuple(pts[0])]
    acc = 0.0
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        L = _dist(a, b)
        if acc + L >= dist:
            f = (dist - acc) / (L or 1.0)
            out.append((a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1])))
            return out
        out.append(tuple(b))
        acc += L
    return out


def _terminal_field(g, cor_pts, at_start, lay_from, lay_to, grid):
    """One compact via field AT a terminal group: bridge-tuple form
    (r, c, lay_from, lay_to, dx, dy) consumed by bridges_to_vias -- the line
    runs perpendicular to the corridor's arrival direction."""
    p = cor_pts[0] if at_start else cor_pts[-1]
    q = cor_pts[1] if at_start else cor_pts[-2]
    dx, dy = p[0] - q[0], p[1] - q[1]
    L = math.hypot(dx, dy) or 1.0
    r, c = _cell_of(grid, p[0], p[1])
    return (r, c, lay_from, lay_to, dx / L, dy / L)


def _attach_connectivity(net, st, grid, masks, land_polys, field_vias):
    """Raster attach-connectivity verdict (verification 3, factored
    2026-07-25 so the region realization shares it verbatim): per layer,
    anchors | realized masks | own pours | terminal-zone landings, layers
    fused at ACTUAL via positions (+1-cell tolerance) and THT anchor cells;
    every served group must sit in ONE component. Returns (stranded_gids,
    n_roots)."""
    from scipy import ndimage
    stl = ndimage.generate_binary_structure(2, 1)
    own_masks = {}
    for (olay, opoly) in st.get("own_pours", ()):
        om = own_masks.setdefault(olay,
                                  np.zeros((grid.ny, grid.nx), bool))
        _stamp_poly(om, opoly, grid)
    for lay, polys in land_polys.items():
        om = own_masks.setdefault(lay,
                                  np.zeros((grid.ny, grid.nx), bool))
        for p in polys:
            _stamp_poly(om, p, grid)
    comp = {}
    for lay in st["layers"]:
        base = st["anchors"][lay].copy()
        if lay in masks:
            base |= masks[lay]
        if lay in own_masks:
            base |= own_masks[lay]
        lab, _n = ndimage.label(base, structure=stl)
        comp[lay] = lab
    parent = {}

    def find(x):
        while parent.get(x, x) != x:
            parent[x] = parent.get(parent[x], parent[x])
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    # through-barrels fuse every layer at each ACTUAL via cell (+1-cell
    # tolerance) -- a reseat may have slid a via off the field cell
    for vs in field_vias:
        for (vx, vy) in vs:
            r, c = _cell_of(grid, vx, vy)
            tags = []
            for lay in comp:
                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        rr, cc = r + dr, c + dc
                        if 0 <= rr < grid.ny and 0 <= cc < grid.nx \
                                and comp[lay][rr, cc]:
                            tags.append((lay, int(comp[lay][rr, cc])))
            for t in tags[1:]:
                union(tags[0], t)
    # THT anchors fuse layers where the same cell anchors 2+ layers
    alay = list(comp)
    for i in range(len(alay)):
        for j in range(i + 1, len(alay)):
            both = st["anchors"][alay[i]] & st["anchors"][alay[j]]
            ys, xs = np.where(both)
            for y, x in zip(ys.tolist(), xs.tolist()):
                a = (alay[i], int(comp[alay[i]][y, x]))
                b = (alay[j], int(comp[alay[j]][y, x]))
                if a[1] and b[1]:
                    union(a, b)
    roots = set()
    stranded = []
    for g in st["served"]:
        gtag = None
        for lay in comp:
            for (r, c) in g.cells:
                v = int(comp[lay][r, c])
                if v:
                    gtag = find((lay, v))
                    break
            if gtag:
                break
        if gtag is None:
            stranded.append(g.gid)
        else:
            roots.add(gtag)
    if os.environ.get("CEC_POUR_PLAN_DEBUG") and len(roots) > 1:
        by_root = {}
        for g in st["served"]:
            for lay in comp:
                got = next((int(comp[lay][r, c]) for (r, c) in g.cells
                            if comp[lay][r, c]), 0)
                if got:
                    by_root.setdefault(find((lay, got)),
                                       []).append((g.gid, lay))
                    break
        print("[cec_pour_plan][dbg] %s components: %s"
              % (net, list(by_root.values())), file=sys.stderr)
    return stranded, len(roots)


REGION_MIN_ISLANDS = 6


def _classify_net(st):
    """CORRIDOR vs REGION class (mandate part 2, 2026-07-25). Region-class =
    logic distribution with many scattered SMD islands (+3V3-shaped: the
    s510 amoeba was a 16-island TREE -- ~17 bridges is the proven minimum
    for a tree, i.e. the WRONG SHAPE CLASS for that net). Structural test,
    never name-based: after manifold gang + pre-connect merge, >=
    REGION_MIN_ISLANDS served groups of which >=70% are plain F-only SMD
    islands. Heavy few-terminal shunt/rail nets stay corridor-class."""
    served = st["served"]
    if len(served) < REGION_MIN_ISLANDS:
        return "corridor"
    islands = [g for g in served
               if g.native == {"F.Cu"} and not g.is_manifold
               and not g.merged]
    if len(islands) >= max(REGION_MIN_ISLANDS,
                           int(round(0.7 * len(served)))):
        return "region"
    return "corridor"


def _realize_region(net, st, grid, existing_vias):
    """REGION-CLASS realization (mandate part 2 + single-owner 5a): the
    POWER-PLANE doctrine -- ONE deliberate clean polygon region on an inner/
    bottom layer covering the islands' projection, shaved only by real
    obstacles (existing raster masks + mask_to_polys smoothing, min-width
    invariant kept), + ONE compact pad-aware terminal via field per island
    dropping into it + one landing per island bonding pads to vias. No
    tree, no bridges, no snake. The LAYER IS CHOSEN BY THE SOLVE (In2
    preferred as bias, B on failure -- the ask's layer is a preference,
    never a mandate); the realized solution owns exactly its layers.
    Returns (entry, dicts, vias) -- entry.path_found False = both layers
    failed (caller falls back, loudly)."""
    from scipy import ndimage
    stl = ndimage.generate_binary_structure(2, 1)
    served = st["served"]
    margin = 2.4
    notes = []
    for lay in [l for l in ("In2.Cu", "B.Cu") if l in st["layers"]]:
        rc = max(1, int(st["rcells"][lay]))
        if st["reqw"][lay] > 0.5 * min(grid.x1 - grid.x0,
                                       grid.y1 - grid.y0):
            notes.append("%s: required width %.1fmm infeasible on this "
                         "board" % (lay, st["reqw"][lay]))
            continue
        # the islands' projection + margin, shaved by real obstacles
        rect = np.zeros((grid.ny, grid.nx), bool)
        x0 = min(g.bbox[0] for g in served) - margin
        y0 = min(g.bbox[1] for g in served) - margin
        x1 = max(g.bbox[2] for g in served) + margin
        y1 = max(g.bbox[3] for g in served) + margin
        grid.stamp_box(rect, x0, y0, x1, y1)
        free = rect & ~st["foreign"][lay]
        # split served: groups the plane must TOUCH (anchored on lay) vs
        # groups needing a DROP field (no copper on lay)
        touch, drop = [], []
        for g in served:
            if any(st["anchors"][lay][r, c] for (r, c) in g.cells):
                touch.append(g)
            else:
                drop.append(g)
        placed = list(existing_vias)
        fields, f_vias, dropped_notes = [], [], []
        for g in drop:
            cxr = (x0 + x1) / 2.0
            cyr = (y0 + y1) / 2.0
            cands = [_attach_point(g, Point(cxr, cyr),
                                   st["reqw"][lay] / 2.0, False)[0]]
            cands += _ring_spots(g)
            pick = None
            for s in cands:
                if not _spot_ok(st, g, s):
                    continue
                r, c = _cell_of(grid, *s)
                if free[r, c]:
                    pick = (s, (r, c))
                    break
            if pick is None:
                dropped_notes.append(
                    "island G%d at (%.1f,%.1f): no clear drop spot -- "
                    "delegated to FR" % (g.gid, g.cx, g.cy))
                continue
            (sx, sy), (r, c) = pick
            dx, dy = sx - g.cx, sy - g.cy
            L = math.hypot(dx, dy) or 1.0
            f6 = (r, c, lay, sorted(g.native)[0] if g.native else "F.Cu",
                  dx / L, dy / L)
            vs, rs = _field_vias(f6, max(st["reqw"][lay], 1.2) / 2.0, grid,
                                 st.get("pad_boxes", ()), placed)
            if not vs:
                dropped_notes.append(
                    "island G%d: via slots exhausted (ledger + pads) -- "
                    "delegated to FR" % g.gid)
                continue
            placed.extend(vs)
            fields.append(f6 + ("terminal",))
            f_vias.append((g, vs))
        if len(f_vias) + len(touch) < 2:
            notes.append("%s: fewer than 2 attachable groups" % lay)
            continue
        # the region component: the free component covering the most drops
        # + touch anchors; drops must LAND on it
        lab, _n = ndimage.label(free, structure=stl)
        score = {}
        for (g, vs) in f_vias:
            for (vx, vy) in vs:
                r, c = _cell_of(grid, vx, vy)
                v = int(lab[r, c])
                if v:
                    score[v] = score.get(v, 0) + 1
        for g in touch:
            seen = set()
            for (r, c) in g.cells:
                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        rr, cc = r + dr, c + dc
                        if 0 <= rr < grid.ny and 0 <= cc < grid.nx:
                            v = int(lab[rr, cc])
                            if v and v not in seen:
                                seen.add(v)
                                score[v] = score.get(v, 0) + 2
        if not score:
            notes.append("%s: no free component reaches any terminal" % lay)
            continue
        comp_id = max(score, key=lambda k: (score[k],
                                            int((lab == k).sum())))
        mask = lab == comp_id
        # every touch group must border the component; every drop's vias on it
        bad = []
        dil = ndimage.binary_dilation(mask, structure=stl)
        for g in touch:
            if not any(dil[r, c] for (r, c) in g.cells):
                bad.append("touch group G%d off the region component"
                           % g.gid)
        kept_fields, kept_fv = [], []
        for f6t, (g, vs) in zip(fields, f_vias):
            on = [(vx, vy) for (vx, vy) in vs
                  if mask[_cell_of(grid, vx, vy)]]
            if not on:
                dropped_notes.append(
                    "island G%d: drop field off the region component -- "
                    "delegated to FR" % g.gid)
                continue
            kept_fields.append(f6t)
            kept_fv.append((g, on))
        if bad:
            notes.append("%s: %s" % (lay, "; ".join(bad)))
            continue
        if len(kept_fv) + len(touch) < 2:
            notes.append("%s: region reaches <2 groups" % lay)
            continue
        # min-width invariant (shave duality): erode by the width floor;
        # the drop cells + touch anchors must stay one component
        seeds = np.zeros((grid.ny, grid.nx), bool)
        for (g, vs) in kept_fv:
            for (vx, vy) in vs:
                r, c = _cell_of(grid, vx, vy)
                seeds[r, c] = True
        for g in touch:
            for (r, c) in g.cells:
                if dil[r, c]:
                    seeds[r, c] = True
        eroded = ndimage.binary_erosion(mask, structure=stl, iterations=rc)
        lab3, _ = ndimage.label(eroded | seeds, structure=stl)
        ag = set(int(v) for v in np.unique(lab3[seeds & (lab3 > 0)]))
        if len(ag) > 1:
            notes.append("%s: region pinches below the width floor "
                         "(%d fragments after erosion)" % (lay, len(ag)))
            continue
        # realize: ONE clean region polygon (+ satellites the same component
        # produced, if smoothing splits -- rare), landings, vias
        dicts = []
        polys = _sp.mask_to_polys(mask, grid, min_area_mm2=2.0, smooth=True)
        for poly in polys:
            dicts.append({"net": net, "layer": lay, "polygon": poly,
                          "priority": 2, "provenance": "pourplan",
                          "name": "pourplan:%s" % net})
        if not dicts:
            notes.append("%s: region polygonized to nothing" % lay)
            continue
        land_polys = {}
        for (g, vs) in kept_fv:
            gx0, gy0, gx1, gy1 = g.bbox
            qs = list(vs)
            land = _box(min([gx0] + [q[0] for q in qs]) - 0.6,
                        min([gy0] + [q[1] for q in qs]) - 0.6,
                        max([gx1] + [q[0] for q in qs]) + 0.6,
                        max([gy1] + [q[1] for q in qs]) + 0.6)
            gl = sorted(g.native)[0] if g.native else "F.Cu"
            if g.f_zone is not None and g.f_zone.covers(land):
                continue
            if gl == "F.Cu" and st.get("gap_geom") is not None:
                land = land.difference(st["gap_geom"])
            if land.is_empty:
                continue
            land_polys.setdefault(gl, []).append(land)
        masks = {lay: mask}
        field_vias_pts = [vs for (_g, vs) in kept_fv]
        stranded, nroots = _attach_connectivity(net, st, grid, masks,
                                                land_polys, field_vias_pts)
        if stranded or nroots > 1:
            notes.append("%s: attach-connectivity failed (stranded=%s, "
                         "%d components)" % (lay, stranded, nroots))
            continue
        for gl, lps in land_polys.items():
            u = unary_union(lps)
            if gl == "F.Cu" and st.get("gap_geom") is not None:
                u = u.difference(st["gap_geom"])
            for g2 in getattr(u, "geoms", [u]):
                if g2.is_empty or g2.geom_type != "Polygon" \
                        or g2.area < 0.4:
                    continue
                dicts.append({"net": net, "layer": gl,
                              "polygon": [(round(x, 3), round(y, 3))
                                          for (x, y) in g2.exterior.coords],
                              "priority": 2, "provenance": "pourplan",
                              "name": "pourplan:%s" % net})
        vias = [{"net": net, "x_mm": x, "y_mm": y}
                for (_g, vs) in kept_fv for (x, y) in vs]
        st["_masks"] = masks
        st["_fields"] = kept_fields
        ent = {"path_found": True, "planner": "territory-region",
               "segments": len(dicts), "bridges": len(kept_fields),
               "layers_used": sorted({d["layer"] for d in dicts}),
               "corridors": 0, "bends": 0,
               "via_fields": {"terminal": len(kept_fields), "crossing": 0},
               "groups": {"served": len(served),
                          "delegated": len(st["delegated"]),
                          "total": len(st["groups"])},
               "region_layer": lay,
               "notes": list(st["notes"]) + notes + dropped_notes}
        return ent, dicts, vias
    e = _fail_entry("region plan failed on every layer (%s)"
                    % "; ".join(notes[-4:]))
    e["planner"] = "territory-region"
    return e, [], []


def _realize_verify(net, st, grid, existing_vias, nets):
    """Realize the assigned corridors as polygon dicts + via fields, verify
    on the raster (clearance + min-width erosion-connectivity + width-margin
    attach), one re-plan on violation, honest entry either way."""
    from scipy import ndimage
    if st.get("trivial"):
        # path_found=True matches route_overunder's <=1-cluster contract
        # (trivially connected; nothing to lay, nothing to reserve)
        ent = {"path_found": True, "segments": 0, "bridges": 0,
               "layers_used": [], "reason": st["trivial"],
               "trivial": True, "planner": "territory", "corridors": 0,
               "bends": 0, "via_fields": {"terminal": 0, "crossing": 0},
               "groups": {"served": len(st["served"]),
                          "delegated": len(st["delegated"]),
                          "total": len(st["groups"])}}
        return ent, [], []
    unplaced = [c for c in st["corridors"] if c.pick is None]
    if unplaced:
        u = unplaced[0]
        ga, gb = u.ga, u.gb
        return {"path_found": False, "segments": 0, "bridges": 0,
                "layers_used": [], "planner": "territory",
                "reason": "no conflict-free layer for corridor %s->%s (%s)"
                          % (ga.gid, gb.gid,
                             u.diag or "all layers conflicted"),
                "bottleneck": {"groups": (ga.gid, gb.gid),
                               "at": (round(ga.cx, 1), round(ga.cy, 1)),
                               "diag": dict(u.diag)}}, [], []

    for attempt in (0, 1):
        # --- gather realized geometry ---
        lay_polys = {}                      # layer -> [shapely] (verified)
        land_polys = {}                     # layer -> [shapely] terminal-zone
        width_checks = []                   # (poly, width_mm, what)
        fields = []                         # bridge tuples + kind tag
        fielded = {}                        # id(group) -> True
        bends = 0
        pending_land = []                   # (group, spot_pt, field_index)
        neck_corridors = 0
        for cor in st["corridors"]:
            pk = cor.pick
            w_eff = pk.get("taper") or st["reqw"][pk["layer"]]
            if pk.get("spine") is not None:
                # neck decomposition: main piece raster-verified, spine =
                # terminal-zone (true-clearance legal by search construction)
                lay_polys.setdefault(pk["layer"], []).append(pk["main"])
                land_polys.setdefault(pk["layer"], []).append(pk["spine"])
                width_checks.append((pk["spine"], W_NECK,
                                     "neck spine %s->%s on %s"
                                     % (cor.ga.gid, cor.gb.gid,
                                        pk["layer"])))
                neck_corridors += 1
            else:
                lay_polys.setdefault(pk["layer"], []).append(pk["poly"])
                width_checks.append((pk["poly"], w_eff,
                                     "corridor %s->%s on %s"
                                     % (cor.ga.gid, cor.gb.gid,
                                        pk["layer"])))
            if pk.get("taper"):
                cor.tapered = True
            bends += pk["bends"]
            if cor.split:
                sp = cor.split
                lay_polys.setdefault(sp["lay2"], []).append(sp["poly2"])
                width_checks.append((sp["poly2"], st["reqw"][sp["lay2"]],
                                     "split leg %s->%s on %s"
                                     % (cor.ga.gid, cor.gb.gid, sp["lay2"])))
                bends += sp.get("bends2", 0)
                r, c = _cell_of(grid, *sp["at"])
                d = LineString(pk["pts"])
                q = d.interpolate(max(0.0, d.length - 1.0))
                dx, dy = sp["at"][0] - q.x, sp["at"][1] - q.y
                L = math.hypot(dx, dy) or 1.0
                fields.append((r, c, pk["layer"], sp["lay2"],
                               dx / L, dy / L, "crossing"))
            for g, at_start in ((cor.ga, True), (cor.gb, False)):
                glay = pk["layer"] if not (cor.split and not at_start) \
                    else cor.split["lay2"]
                gpts = pk["pts"] if not (cor.split and not at_start) \
                    else cor.split["pts2"]
                if _field_needed(g, glay) and id(g) not in fielded:
                    fielded[id(g)] = True
                    fields.append(_terminal_field(
                        g, gpts, at_start, glay,
                        sorted(g.native)[0] if g.native else "F.Cu", grid)
                        + ("terminal",))
                    # F LANDING PATCH deferred until the field's ACTUAL via
                    # positions exist (they may slide beside a pad under
                    # the via-in-pad reseat and the landing must embed
                    # them) -- built below in the via-placement pass.
                    if g.native == {"F.Cu"}:
                        p = gpts[0] if at_start else gpts[-1]
                        pending_land.append((g, p, len(fields) - 1))

        # --- via placement: assembly-class pad exclusion + slide reseat
        # (via-in-pad ruling, owner 2026-07-25) -- placed BEFORE the
        # landings so each landing embeds its field's ACTUAL vias ---
        placed = list(existing_vias)
        field_vias = []
        via_reseated = 0
        for f in fields:
            half_w = max(st["reqw"].get(f[2], 1.2),
                         st["reqw"].get(f[3], 1.2)) / 2.0
            vs, rs = _field_vias(f, half_w, grid, st.get("pad_boxes", ()),
                                 placed)
            field_vias.append(vs)
            via_reseated += rs
            placed.extend(vs)
            if vs and rs:
                # a slid via can sit past the corridor half-width: a
                # compact same-layer COVER rect (field centre + vias +
                # 0.5) keeps every barrel embedded in copper on the
                # non-F transitioning layer(s); the F side is the
                # landing patch's job. Corridor-class copper: raster
                # clearance-checked like any corridor piece.
                fcx = grid.x0 + (f[1] + 0.5) * grid.cell
                fcy = grid.y0 + (f[0] + 0.5) * grid.cell
                qs = list(vs) + [(fcx, fcy)]
                cover = _box(min(q[0] for q in qs) - 0.5,
                             min(q[1] for q in qs) - 0.5,
                             max(q[0] for q in qs) + 0.5,
                             max(q[1] for q in qs) + 0.5)
                for lay in {f[2], f[3]} - {"F.Cu"}:
                    if lay in st["reqw"]:
                        lay_polys.setdefault(lay, []).append(cover)
        vias = [{"net": net, "x_mm": x, "y_mm": y}
                for vs in field_vias for (x, y) in vs]
        for i, vs in enumerate(field_vias):
            if not vs:
                st["notes"].append(
                    "field %d (%s) placed NO via (pad exclusion + ledger "
                    "exhausted every slot) -- attach-connectivity judges"
                    % (i, fields[i][6]))
        # F LANDING PATCHES (terminal-zone copper, guaranteed-patch class:
        # connectivity-stamped, raster-clearance-exempt, the filler carves
        # truth). Pour-termination ruling: for a patch-covered shunt-pad
        # group the landing is CLIPPED to the (inner-edge-clipped) patch,
        # so it can never enter the inter-pad gap; skipped entirely when
        # the patch alone already covers pad + vias.
        for (g, p, fi) in pending_land:
            x0, y0, x1, y1 = g.bbox
            qs = [p] + list(field_vias[fi])
            raw = _box(min([x0] + [q[0] for q in qs]) - 0.6,
                       min([y0] + [q[1] for q in qs]) - 0.6,
                       max([x1] + [q[0] for q in qs]) + 0.6,
                       max([y1] + [q[1] for q in qs]) + 0.6)
            if g.f_zone is not None:
                if g.f_zone.covers(raw):
                    continue               # patch already provides it all
                land = raw.intersection(g.f_zone)
            else:
                land = raw
            # pour-termination ruling: NO landing copper inside a shunt
            # inter-pad gap (measured on s464: raw landings for cell
            # islands beside RS2 poked into its gap strip)
            if st.get("gap_geom") is not None:
                land = land.difference(st["gap_geom"])
            if land.is_empty:
                continue                   # connectivity will judge
            land_polys.setdefault("F.Cu", []).append(land)

        # --- verification 1: raster clearance (the EXISTING rasterize()
        # masks are the authority; own anchors may legitimately coincide;
        # terminal-zone landings are exempt by class, see above) ---
        masks = {}
        viol = {}
        for lay, polys in lay_polys.items():
            m = np.zeros((grid.ny, grid.nx), bool)
            for p in polys:
                _stamp_poly(m, p, grid)
            masks[lay] = m
            bad = m & st["foreign"][lay] & ~st["anchors"][lay]
            if bad.any():
                viol[lay] = bad
                if os.environ.get("CEC_POUR_PLAN_DEBUG"):
                    ys, xs = np.where(bad)
                    pts_mm = [(round(grid.x0 + (x + 0.5) * grid.cell, 1),
                               round(grid.y0 + (y + 0.5) * grid.cell, 1))
                              for y, x in list(zip(ys.tolist(),
                                                   xs.tolist()))[:10]]
                    who = []
                    for (px, py) in pts_mm[:3]:
                        for k, cor2 in enumerate(st["corridors"]):
                            pk2 = cor2.pick
                            if pk2 and pk2["layer"] == lay and \
                                    pk2["main"].buffer(0.01).covers(
                                        Point(px, py)):
                                who.append((px, py, "cor%d %s->%s%s"
                                            % (k, cor2.ga.gid, cor2.gb.gid,
                                               " SPLIT" if cor2.split
                                               else "")))
                            if cor2.split and \
                                    cor2.split["lay2"] == lay and \
                                    cor2.split["poly2"].buffer(0.01).covers(
                                        Point(px, py)):
                                who.append((px, py, "cor%d leg2" % k))
                    print("[cec_pour_plan][dbg] %s viol on %s: %d cell(s) "
                          "at %s owners=%s"
                          % (net, lay, int(bad.sum()), pts_mm, who),
                          file=sys.stderr)
        if viol and attempt == 0:
            # ONE re-plan (task step 5): the violated raster cells join the
            # net's obstacle set on their layer and every corridor re-plans
            # against the SAME F-allow choke; re-picks must stay
            # conflict-free against the other nets' standing assignments.
            for lay, bad in viol.items():
                ys, xs = np.where(bad)
                st["obst"][lay] = list(st["obst"][lay]) + [
                    _box(grid.x0 + x * grid.cell,
                         grid.y0 + y * grid.cell,
                         grid.x0 + (x + 1) * grid.cell,
                         grid.y0 + (y + 1) * grid.cell)
                    for y, x in zip(ys.tolist(), xs.tolist())]
                st["spaces"][lay] = _LayerSpace(
                    st["region"], st["obst"][lay], st["reqw"][lay] / 2.0,
                    f_allow=st["f_allow"] if lay == "F.Cu" else None,
                    approach=st.get("approach"), half_neck=W_NECK / 2.0,
                    neck_unguard=0.6)
            st.pop("spaces_taper", None)

            def _foreign_clash(cand):
                cb = cand["poly"].buffer(0.3)
                return any(cb.intersects(h)
                           and cb.intersection(h).area > 0.01
                           for h in _assigned_foreign(nets, net,
                                                      cand["layer"]))

            for g in st["served"]:
                g.spot = None              # re-resolve against new obstacles
            for cor in st["corridors"]:
                cor.cands = []
                cor.pick = None
                cor.split = None
                _make_candidates(cor, st, grid)
                cor.pick = next((c for c in cor.cands
                                 if not _foreign_clash(c)), None)
            if any(c.pick is None for c in st["corridors"]):
                return _fail_entry("re-plan after clearance violation "
                                   "found no path"), [], []
            st["notes"].append("re-planned after raster clearance violation")
            continue
        if viol:
            return _fail_entry("raster clearance violation persisted "
                               "after re-plan"), [], []

        # --- verification 2: MIN-WIDTH, exact geometric erosion. The
        # erosion-connectivity invariant is checked with shapely's exact
        # negative buffer per realized piece: erode(piece, w/2 - tol) must
        # survive as ONE component spanning the piece. (Deviation from the
        # 0.8mm-raster erosion, with a measured reason: at cell 0.8 the
        # smallest expressible erosion radius is one cell = proves 1.6mm --
        # every floor-width 1.2mm corridor would fail STRUCTURALLY, and
        # diagonal capsules mis-verify at any near-width cell size. The
        # exact buffer is the same duality with zero discretization loss;
        # clearance and connectivity stay on the existing raster.) ---
        for (poly, w_eff, what) in width_checks:
            core = poly.buffer(-(w_eff / 2.0 - 0.05))
            geoms = [g for g in getattr(core, "geoms", [core])
                     if not g.is_empty]
            if not geoms:
                return _fail_entry("min-width invariant: %s erodes to "
                                   "nothing at %.2fmm" % (what, w_eff)), [], []
            if len(geoms) > 1:
                return _fail_entry("min-width invariant: %s pinches below "
                                   "%.2fmm (splits on erosion)"
                                   % (what, w_eff)), [], []

        # --- verification 3: connectivity + width-margin attach on the
        # raster (shared helper -- the region realization proves attach
        # through the identical machinery) ---
        stranded, nroots = _attach_connectivity(net, st, grid, masks,
                                                land_polys, field_vias)
        if stranded or nroots > 1:
            reason = ("width-margin attach failed for group(s) %s"
                      % stranded if stranded else
                      "attach-connectivity: served groups sit in %d "
                      "disconnected components" % nroots)
            if attempt == 0:
                return _fail_entry(reason), [], []
            return _fail_entry(reason + " (after re-plan)"), [], []

        # --- emit (corridors + terminal-zone landings, unioned per layer) ---
        dicts = []
        all_lays = sorted(set(lay_polys) | set(land_polys))
        for lay in all_lays:
            u = unary_union(list(lay_polys.get(lay, ()))
                            + list(land_polys.get(lay, ())))
            if lay == "F.Cu" and st.get("gap_geom") is not None:
                # pour-termination ruling, emit-side authority: no v4 F
                # copper inside any shunt inter-pad gap (also trims the
                # <=0.4mm neck-spine edge overhang the space-level
                # exclusions cannot express)
                u = u.difference(st["gap_geom"])
            for g in getattr(u, "geoms", [u]):
                if g.is_empty or g.geom_type != "Polygon" or g.area < 0.4:
                    continue
                dicts.append({
                    "net": net, "layer": lay,
                    "polygon": [(round(x, 3), round(y, 3))
                                for (x, y) in g.exterior.coords],
                    "priority": 2, "provenance": "pourplan",
                    "name": "pourplan:%s" % net})
        kinds = {}
        for f in fields:
            kinds[f[6]] = kinds.get(f[6], 0) + 1
        ent = {"path_found": True, "planner": "territory",
               "segments": len(dicts), "bridges": len(fields),
               "layers_used": all_lays,
               "corridors": len(st["corridors"]), "bends": bends,
               "via_fields": {"terminal": kinds.get("terminal", 0),
                              "crossing": kinds.get("crossing", 0)},
               "groups": {"served": len(st["served"]),
                          "delegated": len(st["delegated"]),
                          "total": len(st["groups"])},
               "neck_corridors": neck_corridors,
               "via_reseated": via_reseated,
               "notes": list(st["notes"])}
        st["_masks"] = masks
        st["_fields"] = fields
        return ent, dicts, vias
    return _fail_entry("unreachable"), [], []


def _collect_entry(st, grid, dicts, vias, *, ok):
    """Reservation internals in synthesize_overunder_pours' collect shape:
    path_cells = the realized masks (already at width; rcells 0 so
    corridor_masks adds only its margin ring), bridges = the via fields."""
    masks = st.get("_masks") or {}
    return {"ok": ok and bool(masks),
            "path_cells": {lay: m.copy() for lay, m in masks.items()},
            "bridges": [f[:6] for f in (st.get("_fields") or ())],
            "rcells": {lay: 0 for lay in masks},
            "foreign": st["foreign"], "reqw": st["reqw"]}


if __name__ == "__main__":
    import argparse
    import json
    ap = argparse.ArgumentParser()
    ap.add_argument("board")
    ap.add_argument("--nets", default="")
    a = ap.parse_args()
    b = pcbnew.LoadBoard(a.board)
    asks = [{"net": n, "layers": ("In2.Cu",)}
            for n in a.nets.split(",") if n]
    pours, vias, rep = plan_pours(b, asks)
    print(json.dumps({"pours": len(pours), "vias": len(vias),
                      "report": rep}, indent=1, default=str))
