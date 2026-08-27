#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
"""v4 TERRITORY POUR PLANNER (owner GO 2026-07-25; design of record:
docs/slab-pour-design-2026-07-24.md v4). The designer's method, algorithmic:

  * TERMINALS -- v3.1 connector manifolds + guaranteed shunt patches + the
    net's terminal clusters (all reused from cec_slab_pour, proven).
  * CORRIDORS -- straight fat polygons (I/L/U, few bends preferred)
    connecting the terminal groups at the net's required width, planned as
    RECTILINEAR CENTERLINES in configuration space (obstacles inflated by
    width/2) on a sparse obstacle-coordinate grid: direct axis segment ->
    one-bend dogleg -> bounded Manhattan Dijkstra. Never a cell grid and never
    a diagonal that needs a staircase approximation at emission.
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
from itertools import combinations

import numpy as np

try:
    import pcbnew                                      # noqa: F401
except ImportError:                                    # host-side tests
    pcbnew = None

# SWIG REGISTRY PIN -- see scripts/cec_swig_guard.py (hub all-9999 root cause).
if pcbnew is not None:
    import cec_swig_guard as _swig_guard
    _swig_guard.pin()

import cec_slab_pour as _sp
import cec_fab_profile as _fab
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
LAYERS_ALL = ("F.Cu", "In2.Cu", "In3.Cu", "B.Cu")
LAYER_PREF = {"In2.Cu": 0.0, "B.Cu": 0.4, "F.Cu": 0.8,
              "In3.Cu": 1.2}   # legacy default; profile policy prefers In3

# BOARD-CLASS POWER-LAYER POLICY (owner ruling 2026-07-25). The In2-first bias
# above is correct for a board whose second inner IS a power-routing layer (the
# 24-pin: `rail_alt_layer: In2.Cu`). It is WRONG for a board whose second inner
# is the SIGNAL escape layer -- the hub, where the 2026-06-14 stackup ruling
# already says In2 is signal, and where the planner was measured filling it with
# ten rail pours (two of them dead) while 132 signal tracks fought for the same
# copper.
#
# The engineering case, on the hub's own numbers: its 5VSB trunk is ~2.5A over
# ~60mm, which on a 2oz OUTER at 2mm wide is ~7mohm / 18mV / 45mW -- power does
# not need inner-layer real estate, while routing genuinely is the scarce
# resource (120 parts on 88x70 with four RJ-45 jacks and a mezzanine). Rails on
# the outers also keep B.Cu signals referenced to continuous copper instead of
# crossing rail-to-rail plane splits, which is the part that matters for the
# unintentional-radiator posture.
#
# CEC_POWER_POUR_LAYERS (set from the `power_pour_layers` board param via
# _oracle_env) names the preference order. UNSET = the historical In2-first
# behaviour, byte-identical -- every existing board keeps exactly what it had.
_LAYER_ORDER_DEFAULT = ("In2.Cu", "B.Cu", "F.Cu")
# Region realization historically considered only In2/B; the default keeps that.
_REGION_ORDER_DEFAULT = ("In2.Cu", "B.Cu")


def power_layer_order(default=_LAYER_ORDER_DEFAULT):
    """Preferred layer order for POWER copper, most-preferred first."""
    raw = (os.environ.get("CEC_POWER_POUR_LAYERS") or "").strip()
    if not raw and os.environ.get("CEC_FAB_PROFILE") in _fab.PROFILES:
        return ("In3.Cu", "B.Cu", "F.Cu", "In2.Cu")
    if not raw:
        return tuple(default)
    order = tuple(x.strip() for x in raw.split(",") if x.strip() in LAYERS_ALL)
    return order or tuple(default)


def region_layer_order():
    """Layer order for region-class realization (the logic-rail plane)."""
    raw = (os.environ.get("CEC_POWER_POUR_LAYERS") or "").strip()
    if not raw and os.environ.get("CEC_FAB_PROFILE") in _fab.PROFILES:
        return power_layer_order()
    if not raw:
        return _REGION_ORDER_DEFAULT
    return power_layer_order()


def layer_pref():
    """Per-layer cost bias, derived from the active policy order."""
    order = power_layer_order()
    pref = {lay: round(0.4 * i, 10) for i, lay in enumerate(order)}
    # A layer the policy does not name is allowed but never preferred.
    for lay in LAYERS_ALL:
        pref.setdefault(lay, round(0.4 * len(order), 10))
    return pref


def demoted_layers():
    """Layers the policy pushes BELOW the historical default (for loud
    reporting when the solve lands on one anyway -- the sanctioned exception)."""
    order = power_layer_order()
    if order == _LAYER_ORDER_DEFAULT:
        return frozenset()
    # anything the policy ranks last is the exception layer
    return frozenset(order[-1:]) if len(order) > 1 else frozenset()


def power_net_order(nets, amps_of, priority_nets=None):
    """Return a deterministic, importance-aware power-commodity order.

    Higher-current conductors retain first claim on scarce copper.  Boards may
    additionally declare the electrical order of equal-current commodities
    (for example input-to-shunt paths before their downstream distribution
    paths).  Unknown or undeclared peers fall back to their stable net name;
    no board name or net-name heuristic is embedded in the planner.
    """
    if priority_nets is None:
        raw = (os.environ.get("CEC_POWER_ROUTE_PRIORITY_NETS") or "").strip()
        priority_nets = tuple(x.strip() for x in raw.split(",") if x.strip())
    else:
        priority_nets = tuple(priority_nets)
    declared_rank = {net: rank for rank, net in enumerate(priority_nets)}
    fallback_rank = len(declared_rank)
    return sorted(
        nets,
        key=lambda net: (
            -float(amps_of(net)),
            declared_rank.get(net, fallback_rank),
            net,
        ),
    )


def parallel_layer_bundle(ask, amps, enabled_layers):
    """Return an explicit redundant-current-layer contract, or ``None``.

    A compact high-current path may need two conductors in parallel when no
    single copper layer can provide the required cross-section.  This is not
    inferred from a board name: the board policy (or an individual pour ask)
    must opt in, name the layers, and declare the worst-case current fraction
    that either layer must carry. Two layers at 0.50 each prove 100% aggregate
    capacity; any current-imbalance reserve must be present in the upstream
    margin-inclusive design current. Invalid or under-capacity declarations
    fail closed.
    """
    ask = ask or {}
    raw = ask.get("parallel_layers")
    if raw is None:
        raw = os.environ.get("CEC_POWER_PARALLEL_LAYERS", "")
    if isinstance(raw, str):
        selected = tuple(x.strip() for x in raw.split(",") if x.strip())
    else:
        selected = tuple(raw or ())
    enabled = set(enabled_layers)
    selected = tuple(dict.fromkeys(
        layer for layer in selected
        if layer in LAYERS_ALL and layer in enabled))
    if len(selected) < 2:
        return None
    fraction = float(ask.get("parallel_layer_fraction") or
                     os.environ.get("CEC_POWER_PARALLEL_FRACTION", "0.50"))
    threshold = float(ask.get("parallel_min_amps") or
                      os.environ.get("CEC_POWER_PARALLEL_MIN_AMPS", "0"))
    if float(amps) < threshold:
        return None
    if not (0.5 <= fraction <= 1.0):
        raise ValueError("parallel-layer current fraction must be in [0.5, 1.0]")
    if len(selected) * fraction < 1.0:
        raise ValueError("parallel-layer contract has less than 100% capacity")
    return {
        "layers": selected,
        "per_layer_fraction": fraction,
        "aggregate_capacity_fraction": len(selected) * fraction,
    }


def declared_parallel_bundles(board, asks):
    """Resolve every active parallel-current contract for *asks*.

    This is the shared admission oracle for planning and production compile.
    Keeping it here prevents the compiler from deciding that a board opted in
    while the geometry planner silently decides the same net did not (or vice
    versa).  Returned currents are the same margin-inclusive geometry basis
    used by :func:`plan_pours`.
    """
    enabled = tuple(_fab.enabled_copper_layers(board))
    overlay = _net_currents()
    board_hint = (os.environ.get("CEC_THERMAL_BOARD_HINT")
                  or getattr(board, "GetFileName", lambda: "")())
    result = {}
    for ask in asks or ():
        net = str((ask or {}).get("net") or "")
        if not net or net in result:
            continue
        amps = _design_current_amps(
            net, overlay_currents=overlay, board_hint=board_hint)
        bundle = parallel_layer_bundle(ask, amps, enabled)
        if bundle:
            result[net] = {
                **bundle,
                "design_current_A": float(amps),
                "per_layer_amps": float(amps) *
                    float(bundle["per_layer_fraction"]),
            }
    return result


def _candidate_layers(candidate):
    """Every physical layer occupied by one corridor candidate."""
    return tuple(candidate.get("bundle_layers") or (candidate["layer"],))


def _candidate_poly(candidate, layer):
    """Layer-specific geometry for ordinary and parallel candidates."""
    part = (candidate.get("bundle_parts") or {}).get(layer)
    return part["poly"] if part is not None else candidate["poly"]
VIA_FIELD_COST = 3.0
BEND_COST = 0.5
LEN_COST = 0.02                                          # per mm
TAPER_MAX_MM = 3.2       # max sub-width terminal-approach run (pad = bottleneck)
W_NECK = 0.8             # anchor-approach neck width (true-clearance legal
#                          through a 4.2mm THT pin field; raster-exempt by
#                          the terminal-zone doctrine, geometric proof only)
APPROACH_MM = 3.2        # anchor-approach reach around own pads
TERMINAL_FIELD_MAX_SPAN_MM = 25.0  # bounded local multi-pin PTH escape field
SPOT_OFFSET_MM = 1.1     # via-field spot standoff from an SMD pad group edge
EPS = 0.05               # configuration-space epsilon (corner points strictly free)
BB_NODE_CAP = 200000     # branch-and-bound node budget before greedy fallback
ENDPOINT_ALT_CAP = 16    # bounded terminal landing alternatives per endpoint
ENDPOINT_CROSS_BEAM = 6  # paired-alternate beam after one-sided evaluation


def _multipin_terminal_approach_fields(board, net_code):
    """Return bounded local neck regions for multi-pin PTH terminals.

    A fixed-radius halo around a power pad cannot cross a second connector row
    whose pitch is larger than that radius.  That makes an otherwise valid
    high-current connector permanently unroutable even after every movable
    board obstacle is removed.  Treat the complete local PTH pad field as the
    terminal escape domain only when at least two plated lands carry this net;
    foreign lands remain exact obstacles inside the domain, and the ordinary
    contiguous-neck length/ratio gate still limits the realized conductor.
    """
    fields = []
    for footprint in board.GetFootprints():
        through = []
        own = []
        for pad in footprint.Pads():
            try:
                copper_layers = tuple(pad.GetLayerSet().CuStack())
            except Exception:                           # noqa: BLE001
                copper_layers = ()
            if len(copper_layers) <= 2:
                continue
            box = pad.GetBoundingBox()
            geometry = _box(
                box.GetLeft() / MM, box.GetTop() / MM,
                box.GetRight() / MM, box.GetBottom() / MM)
            through.append(geometry)
            if pad.GetNetCode() == net_code:
                own.append(geometry)
        if len(own) < 2 or len(through) <= len(own):
            continue
        x0 = min(geometry.bounds[0] for geometry in through)
        y0 = min(geometry.bounds[1] for geometry in through)
        x1 = max(geometry.bounds[2] for geometry in through)
        y1 = max(geometry.bounds[3] for geometry in through)
        if (x1 - x0 > TERMINAL_FIELD_MAX_SPAN_MM
                or y1 - y0 > TERMINAL_FIELD_MAX_SPAN_MM):
            continue
        fields.append(_box(x0, y0, x1, y1).buffer(
            APPROACH_MM, join_style=2, mitre_limit=2.0))
    return fields


# ---------------------------------------------------------------------------
# geometry helpers (shapely; imported lazily nowhere -- the module is only
# imported behind the pour_plan lever / the --v4 flag / the teeth)
# ---------------------------------------------------------------------------
from shapely.geometry import LineString, Point, Polygon, box as _box  # noqa: E402
from shapely.ops import nearest_points, unary_union  # noqa: E402
from shapely.prepared import prep  # noqa: E402


def _poly_of(points):
    from shapely.geometry import Polygon
    return Polygon(points).buffer(0)


def _capsule(pts, half_w):
    """Corridor copper around a path.

    SQUARE CAPS, MITRED JOINS (owner 2026-07-25: "diagonal blobs that don't make
    sense"). The old round buffer (quad_segs=4) faceted every corner and every
    end into short diagonal segments, which is where the 24-pin's diagonal pour
    edges came from -- 79 across the pourfirst zones, 86 across pourplan, while
    every rectangle-shaped producer (manifold:, patch:) measured 0. With a
    Manhattan path these settings give an exactly rectilinear polygon. The path
    generator now guarantees that input contract; the emission checks below are
    a fail-closed defense against any future producer regression."""
    # Search geometry is deliberately not post-processed here. Shrinking a
    # candidate changes which corridors pass width/legality checks. Instead the
    # centerline search itself is Manhattan, so the checked and emitted copper
    # are the same shape.
    return LineString(pts).buffer(half_w, cap_style=3, join_style=2,
                                  mitre_limit=4.0)


def _minimal_rectilinear_inner(poly):
    """Replace each diagonal boundary edge by one legal inside elbow.

    Raster staircases are a useful last resort, but a polygon made from a
    clipped landing or mitred corner normally needs only one of the two
    possible Manhattan elbows.  Choosing the elbow whose two legs remain
    inside the already verified polygon preserves the compact human-designed
    outline and adds at most one vertex per diagonal edge.
    """
    if poly.is_empty or getattr(poly, "geom_type", "") != "Polygon" \
            or list(poly.interiors):
        return None
    source = list(poly.exterior.coords)[:-1]
    if len(source) < 3:
        return None
    permitted = poly.buffer(1e-7, join_style=2)
    points = []
    for index, a in enumerate(source):
        b = source[(index + 1) % len(source)]
        points.append(a)
        if abs(b[0] - a[0]) <= 1e-6 or abs(b[1] - a[1]) <= 1e-6:
            continue
        elbows = ((a[0], b[1]), (b[0], a[1]))
        legal = [elbow for elbow in elbows
                 if permitted.covers(LineString((a, elbow, b)))]
        if not legal:
            return None
        # Both can be legal at a shallow concavity. Prefer the shorter
        # boundary perturbation (distance from the original diagonal).
        elbow = min(legal, key=lambda p: LineString((a, p, b)).hausdorff_distance(
            LineString((a, b))))
        if elbow != a and elbow != b:
            points.append(elbow)
    out = Polygon(points).buffer(0)
    if getattr(out, "geom_type", "") != "Polygon" or out.is_empty:
        return None
    if not permitted.covers(out) or _diagonal_edges(out.exterior.coords):
        return None
    return out


def _emit_rectilinear(poly):
    """Final pour copper is Manhattan (owner 2026-07-25). Applied to the EMITTED
    polygon only, inner-approximated so copper can only shrink -- never into
    space the path was routed around."""
    try:
        ext = list(poly.exterior.coords)
    except Exception:                                      # noqa: BLE001
        return poly
    diag = any(abs(b[0] - a[0]) > 1e-6 and abs(b[1] - a[1]) > 1e-6
               for a, b in zip(ext, ext[1:]))
    if not diag:
        return poly
    minimal = _minimal_rectilinear_inner(poly)
    if minimal is not None and minimal.area >= 0.90 * poly.area:
        return minimal
    out = _sp.rectilinear_inner(poly)
    # The emit site takes ONE polygon. If the inner approximation SPLIT the shape
    # (a diagonal neck can pinch off at the grid step), keep the original rather
    # than silently shipping a fragment -- a split pour is a connectivity change,
    # which this rule has no business making.
    if getattr(out, "geom_type", "") != "Polygon":
        # A split is only acceptable when it shaves SLIVERS: if one piece still
        # carries essentially the whole pour, take it and lose the crumbs. If the
        # shape genuinely breaks in two, keep the original -- turning one pour
        # into two is a connectivity change this rule has no business making.
        # (Measured: the 24-pin's last residual, pourplan:/SENSE5V_HI on B.Cu,
        # 163mm2 with 9 diagonal edges, splits when gridded.)
        parts = sorted(getattr(out, "geoms", []), key=lambda g: -g.area)
        if parts and parts[0].area >= 0.95 * out.area:
            return parts[0]
        return poly
    return out


def _restore_rectilinear_barrels(rect, original, barrels, *, forbidden=None,
                                 region=None):
    """Add legal axis-aligned landing squares for barrels shaved at emit.

    The verified source polygon may follow a round/rotated terminal boundary.
    Its compact rectilinear inner approximation can consequently shave an
    edge of a via annulus.  A square built from the annulus bounds restores
    full copper coverage while remaining Manhattan; exact region and foreign
    clearance checks decide whether that additive repair is legal.
    """
    result = rect
    forbidden = forbidden if forbidden is not None else _box(0, 0, 0, 0)
    for barrel in barrels:
        if not original.buffer(0.01).covers(barrel) \
                or result.buffer(0.01).covers(barrel):
            continue
        proposal = _box(*barrel.bounds)
        addition = proposal.difference(result)
        if region is not None and not region.buffer(1e-6).covers(addition):
            return None
        if not forbidden.is_empty and \
                forbidden.intersection(addition).area > 1e-6:
            return None
        result = result.union(proposal).buffer(0)
        if getattr(result, "geom_type", "") != "Polygon":
            return None
    if any(not result.buffer(0.01).covers(barrel)
           for barrel in barrels
           if original.buffer(0.01).covers(barrel)):
        return None
    if _diagonal_edges(result.exterior.coords):
        return None
    return result


def _diagonal_edges(points, tol=1e-6):
    """Return non-axis-aligned edges in a closed or open polygon point list."""
    pts = list(points or ())
    if len(pts) < 2:
        return []
    if pts[0] != pts[-1]:
        pts.append(pts[0])
    return [(a, b) for a, b in zip(pts, pts[1:])
            if abs(b[0] - a[0]) > tol and abs(b[1] - a[1]) > tol]


def _assert_manhattan_pours(dicts, *, context="pour planner"):
    """Fail closed if any generated pour contains a diagonal boundary.

    This is deliberately a producer-side contract, not a dashboard cosmetic
    check. A post-hoc staircase can alter minimum width, clearance, and via
    coverage. All copper producers that feed this planner must therefore emit
    exact horizontal/vertical boundaries before a board is written.
    """
    bad = []
    for d in dicts:
        edges = _diagonal_edges(d.get("polygon", ()))
        if edges:
            bad.append((d.get("name") or d.get("net") or "unnamed",
                        d.get("layer"), len(edges)))
    if bad:
        sample = ", ".join("%s@%s:%d" % item for item in bad[:6])
        raise RuntimeError("%s emitted non-Manhattan pour edge(s): %s"
                           % (context, sample))


def _orthogonal_cleanup(poly, width_mm, forbidden=None, region=None,
                        *, micro_step_mm=0.25,
                        allow_elbow_fills=False):
    """Remove cosmetic orthogonal notches without weakening the pour.

    Corridor capsules are conservative routing geometry. Their union with a
    landing patch can leave (1) a shallow 0.05--0.25 mm edge band where two
    valid copper rectangles almost align, and (2) a large empty inside elbow
    even though only the *outside* of the bend contains an obstacle. A human
    designer normally floods both. This pass proposes only axis-aligned
    rectangles, adds copper only, and accepts a proposal only when it is inside
    the board and has zero positive-area overlap with the exact foreign-copper
    reservation. Required antipads and shunt gaps therefore remain untouched.

    Returns ``(geometry, {micro_fills, elbow_fills, added_mm2})``.
    """
    stats = {"micro_fills": 0, "elbow_fills": 0, "added_mm2": 0.0}
    if poly.is_empty or getattr(poly, "geom_type", "") != "Polygon":
        return poly, stats
    forbidden = forbidden if forbidden is not None else _box(0, 0, 0, 0)

    def _accept(g, proposal, kind):
        addition = proposal.difference(g)
        if addition.is_empty or addition.area <= 1e-6:
            return g, False
        if region is not None and not region.buffer(EPS).covers(addition):
            return g, False
        if not forbidden.is_empty and \
                forbidden.intersection(addition).area > 1e-6:
            return g, False
        merged = g.union(addition).buffer(0)
        if getattr(merged, "geom_type", "") != "Polygon":
            return g, False
        stats[kind] += 1
        stats["added_mm2"] += addition.area
        return merged, True

    # Large elbows are useful placement pockets. Flooding one is therefore an
    # explicit policy choice, never a cosmetic default. The former unconditional
    # pass turned a compact hook into the large PCIe slab the reviewer rejected.
    if allow_elbow_fills:
        for _pass in range(3):
            changed = False
            pts = list(poly.exterior.coords)[:-1]
            for i, vertex in enumerate(pts):
                prev = pts[i - 1]
                nxt = pts[(i + 1) % len(pts)]
                dx = abs(prev[0] - nxt[0])
                dy = abs(prev[1] - nxt[1])
                if dx <= EPS or dy <= EPS:
                    continue
                # Shallow outline mismatches belong to the micro-band pass below.
                # Treating one as an "elbow" can extend it past a shunt boundary,
                # after which the sink clips it back into yet another tiny step.
                if min(dx, dy) <= micro_step_mm + EPS:
                    continue
                if min(dx, dy) > width_mm / 2.0 + EPS or \
                        max(dx, dy) > 1.5 * width_mm + EPS:
                    continue
                proposal = _box(min(prev[0], vertex[0], nxt[0]),
                                min(prev[1], vertex[1], nxt[1]),
                                max(prev[0], vertex[0], nxt[0]),
                                max(prev[1], vertex[1], nxt[1]))
                poly, accepted = _accept(poly, proposal, "elbow_fills")
                if accepted:
                    changed = True
                    break
            if not changed:
                break

    # Flatten shallow H/V bands by extending the adjacent edge that lies
    # outside the current polygon. This keeps all existing copper (including
    # the full shunt pad) and fills the 0.15 mm strip beside it, rather than
    # shaving a required landing to make the picture look straight.
    for _pass in range(8):
        changed = False
        pts = list(poly.exterior.coords)[:-1]
        for i, a in enumerate(pts):
            b = pts[(i + 1) % len(pts)]
            prev = pts[i - 1]
            nxt = pts[(i + 2) % len(pts)]
            vertical = abs(a[0] - b[0]) <= EPS
            horizontal = abs(a[1] - b[1]) <= EPS
            length = _dist(a, b)
            proposals = []
            if vertical and length <= micro_step_mm + EPS \
                    and abs(prev[1] - a[1]) <= EPS \
                    and abs(b[1] - nxt[1]) <= EPS:
                y0, y1 = sorted((a[1], b[1]))
                proposals = [
                    _box(min(prev[0], a[0]), y0,
                         max(prev[0], a[0]), y1),
                    _box(min(b[0], nxt[0]), y0,
                         max(b[0], nxt[0]), y1),
                ]
            elif horizontal and length <= micro_step_mm + EPS \
                    and abs(prev[0] - a[0]) <= EPS \
                    and abs(b[0] - nxt[0]) <= EPS:
                x0, x1 = sorted((a[0], b[0]))
                proposals = [
                    _box(x0, min(prev[1], a[1]),
                         x1, max(prev[1], a[1])),
                    _box(x0, min(b[1], nxt[1]),
                         x1, max(b[1], nxt[1])),
                ]
            for proposal in proposals:
                poly, accepted = _accept(poly, proposal, "micro_fills")
                if accepted:
                    changed = True
                    break
            if changed:
                break
        if not changed:
            break
    stats["added_mm2"] = round(stats["added_mm2"], 3)
    return poly, stats


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


def _design_current_amps(net, *, overlay_currents=None, board_hint=None):
    """Resolve the geometry-sizing current, including declared margin once.

    Thermal overlays describe board-specific source/sink cases, while the
    shared synthesis table owns the cable design basis and its margin
    provenance.  Ordinary EPS/PCIe main boards intentionally have no bespoke
    overlay entry, so neither source may be treated as an exclusive fallback.
    """
    overlay = float((overlay_currents or {}).get(net) or 0.0)
    try:
        import cec_synth_pipeline as _csp
        contract = _csp.spec_net_current_contract(
            board_hint if board_hint is not None else
            os.environ.get("CEC_THERMAL_BOARD_HINT", ""), net)
        specified = float((contract or {}).get("amps") or 0.0)
        if contract and not contract.get("margin_included"):
            specified *= float(contract.get("geometry_margin") or 1.0)
    except Exception:                                  # noqa: BLE001
        specified = 0.0
    return max(overlay, specified)


def required_widths_from_geometry_basis(layer_amps, layers, board):
    """Size layers from currents whose upstream margin is already included."""
    return {
        lay: (req_width_mm(
            layer_amps[lay], lay, board=board, margin=1.0)
              if layer_amps[lay] > 0 else 1.2)
        for lay in layers}


def _append_access_primitive_records(out, primitives, lay_ids, nc,
                                     clearance_mm, guard_mm):
    """Project future local-PI copper into a pour's obstacle layers.

    The primitive is already an exact successful decoupler route trial.  A
    track blocks only its own copper layer; a through-via blocks every layer
    it spans.  The eventual pour half-width is added by ``_LayerSpace``, so
    this geometry owns only the future primitive radius plus mutual clearance
    and the caller's raster guard.
    """
    grow = float(clearance_mm) + float(guard_mm)
    for primitive in primitives or ():
        if primitive.get("net_code") == nc:
            continue
        kind = primitive.get("kind")
        if kind == "track":
            geometry = LineString([
                tuple(primitive["start_mm"]),
                tuple(primitive["end_mm"]),
            ]).buffer(
                float(primitive["width_mm"]) / 2.0 + grow,
                quad_segs=4, cap_style=3)
            primitive_layers = {int(primitive["layer_id"])}
        elif kind == "via":
            geometry = Point(*primitive["at_mm"]).buffer(
                float(primitive["diameter_mm"]) / 2.0 + grow,
                quad_segs=4)
            primitive_layers = {
                int(layer) for layer in primitive.get("layer_ids") or ()}
        else:
            continue
        # Obstacle attribution is consumed by the bounded placement-relief
        # beam.  Name the movable capacitor, not an abstract pair label, so a
        # no-path proof produces an actionable generic placement lever.
        owner = str(primitive.get("cap") or primitive.get("owner") or "?")
        if primitive.get("purpose") == "ground_plane_access":
            detail = "ground-plane-access:%s.%s %s" % (
                primitive.get("owner") or "?",
                primitive.get("pad") or "?", kind)
        else:
            detail = "decoupler:%s:%s %s" % (
                primitive.get("owner") or "?",
                primitive.get("cap") or "?", kind)
        for lay, lid in lay_ids.items():
            if lid not in primitive_layers:
                continue
            out[lay].append({
                "geometry": geometry,
                "kind": "future_decoupler_access",
                "owner": owner,
                "detail": detail,
                "net": primitive.get("net"),
            })


def _priority_access_primitives(primitives):
    """Partition complete local-PI cells from negotiable plane portals.

    A proved bypass cell is one electrical object: its short supply bridge,
    capacitor return, owner return, and any shared dogbone/via column are all
    mandatory. Reserving only its supply half lets a broad current corridor
    occupy the deterministic GND return; production then locks that return and
    cannot clip or replan the current path around it. The placement oracle has
    also lost the obstruction owner that could have rotated or reseated the
    capacitor.

    Whole-board surface-GND completion remains negotiable because those
    ``ground_plane_access`` portals are selected after declared-current copper
    and have multiple legal seats. Keep only those rows deferred. This makes
    power planning fail or route around a *complete* local PI cell early,
    giving the generic placement-relief beam actionable owner/cap evidence.
    """
    immutable, deferred = [], []
    for primitive in primitives or ():
        reseatable_ground = (
            primitive.get("purpose") == "ground_plane_access")
        target = deferred if reseatable_ground else immutable
        target.append(primitive)
    return tuple(immutable), tuple(deferred)


def _append_owned_rect_reservation_records(out, reservations, net, *,
                                           kind="future_owned_route"):
    """Add net-owned future route rectangles as foreign-only obstacles.

    Placement and routing can reserve copper that is not materialized on the
    source board yet.  A conventional global keepout is too blunt for this
    case: the owning net may legally merge into its future route, while every
    other net must preserve the channel plus its already-authored margin.
    ``out`` is the same per-layer attributed obstacle map used by exact
    territory planning, so failures retain the owner/net/purpose that consumed
    the channel instead of degrading into a generic no-path result.
    """
    added = 0
    for reservation in reservations or ():
        owner_net = str(reservation.get("net") or "")
        if not owner_net or owner_net == net:
            continue
        try:
            geometry = _box(
                float(reservation["x0"]), float(reservation["y0"]),
                float(reservation["x1"]), float(reservation["y1"]))
        except (KeyError, TypeError, ValueError):
            continue
        if geometry.is_empty or geometry.area <= EPS:
            continue
        name = str(reservation.get("name") or kind)
        source = str(reservation.get("source_ref") or "")
        target = str(reservation.get("target_ref") or "")
        detail = name
        if source or target:
            detail += ":%s->%s" % (source or "?", target or "?")
        for layer in reservation.get("layers") or ("F.Cu",):
            if layer not in out:
                continue
            out[layer].append({
                "geometry": geometry,
                "kind": kind,
                "owner": target or source or name,
                "detail": detail,
                "net": owner_net,
            })
            added += 1
    return added


def _geo_obstacle_records(board, nc, layers, clearance_mm, guard_mm,
                          access_primitives=()):
    """Per-layer exact obstacle lists for one net.

    Every foreign pad/track/via is blocked as before. On an outer layer, a
    foreign assembled footprint's courtyard is also an obstacle: placement
    admission forbids component bodies inside high-current pours, so planning
    those bodies out here keeps the two stages consistent and produces the
    deliberate Manhattan hooks a designer would draw around a local cell.
    Footprints carrying the planned net and through-hole/mechanical interfaces
    retain their existing exemptions. All geometry is inflated by clearance
    plus *guard_mm*; locked-ness remains irrelevant, matching ``rasterize``.
    """
    grow = clearance_mm + guard_mm
    out = {lay: [] for lay in layers}
    lay_ids = {lay: board.GetLayerID(lay) for lay in layers}

    def _item_id(item):
        uuid = getattr(item, "m_Uuid", None)
        try:
            return uuid.AsString()
        except AttributeError:
            return "anonymous-%x" % id(item)
    for fp in board.GetFootprints():
        pads = list(fp.Pads())
        for p in pads:
            if p.GetNetCode() == nc:
                continue
            bb = p.GetBoundingBox()
            g = _box(bb.GetLeft() / MM - grow, bb.GetTop() / MM - grow,
                     bb.GetRight() / MM + grow, bb.GetBottom() / MM + grow)
            stack = set(p.GetLayerSet().CuStack())
            for lay, lid in lay_ids.items():
                if lid in stack:
                    out[lay].append({
                        "geometry": g, "kind": "footprint",
                        "owner": str(fp.GetReference()),
                        "detail": "%s-%s" % (fp.GetReference(),
                                               p.GetPadName()),
                        "net": p.GetNetname(),
                    })
        ref = str(fp.GetReference() or "")
        # Same-net components are legitimate pour endpoints. THT connectors
        # and board-only mechanics likewise need copper at/under their barrel
        # or datum fields and are governed by their pad/hole obstacles instead.
        if (any(p.GetNetCode() == nc for p in pads)
                or ref.startswith(("J", "TB", "H", "LOGO", "FID"))
                or not hasattr(fp, "IsFlipped")):
            continue
        side = "B.Cu" if fp.IsFlipped() else "F.Cu"
        if side not in out:
            continue
        try:
            courtyard_layer = board.GetLayerID(
                "B.CrtYd" if fp.IsFlipped() else "F.CrtYd")
            courtyard = fp.GetCourtyard(courtyard_layer)
            body = (courtyard.BBox() if courtyard.OutlineCount()
                    else fp.GetBoundingBox(False, False))
        except Exception:                              # noqa: BLE001
            try:
                body = fp.GetBoundingBox(False, False)
            except Exception:                          # noqa: BLE001
                continue
        geometry = _box(
            body.GetLeft() / MM - grow,
            body.GetTop() / MM - grow,
            body.GetRight() / MM + grow,
            body.GetBottom() / MM + grow)
        out[side].append({
            "geometry": geometry, "kind": "footprint_body",
            "owner": ref, "detail": "%s courtyard" % ref,
            "net": "",
        })
    for t in board.GetTracks():
        if t.GetNetCode() == nc:
            continue
        if t.GetClass() == "PCB_VIA":
            r = t.GetWidth(t.TopLayer()) / MM / 2.0
            q = t.GetPosition()
            g = Point(q.x / MM, q.y / MM).buffer(r + grow, quad_segs=4)
            item_id = _item_id(t)
            for lay, lid in lay_ids.items():
                if lid in t.GetLayerSet().CuStack():
                    out[lay].append({
                        "geometry": g, "kind": "via",
                        "owner": "via:%s" % item_id,
                        "detail": item_id,
                        "net": t.GetNetname(),
                    })
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
        geometry = LineString(
            [(s.x / MM, s.y / MM), (e.x / MM, e.y / MM)]).buffer(
                w + grow, quad_segs=4, cap_style=3)
        item_id = _item_id(t)
        out[lay].append({
            "geometry": geometry, "kind": "track",
            "owner": "track:%s" % item_id,
            "detail": item_id, "net": t.GetNetname(),
        })
    _append_access_primitive_records(
        out, access_primitives, lay_ids, nc, clearance_mm, guard_mm)
    return out


def _geo_obstacles(board, nc, layers, clearance_mm, guard_mm,
                   access_primitives=()):
    """Compatibility geometry view of :func:`_geo_obstacle_records`."""
    records = _geo_obstacle_records(
        board, nc, layers, clearance_mm, guard_mm,
        access_primitives=access_primitives)
    return {lay: [row["geometry"] for row in rows]
            for lay, rows in records.items()}


def _fixed_current_authority_refs(board, authority_refs):
    """Current-domain endpoints that placement may not use as relief knobs.

    Source/sink authority describes electrical proof, not placement
    immobility: a shunt is an authority endpoint but is intentionally movable
    during structure-first placement.  Connector and mounting footprints are
    mechanical interfaces, so keep only those out of the relief beam.
    """
    wanted = {str(ref) for ref in (authority_refs or ())}
    fixed = set()
    for footprint in board.GetFootprints():
        ref = str(footprint.GetReference())
        if ref not in wanted:
            continue
        identity = "%s %s" % (
            footprint.GetFPIDAsString(), footprint.GetValue() or "")
        lowered = identity.lower()
        if ("connector" in lowered or "mountinghole" in lowered
                or "terminalblock" in lowered):
            fixed.add(ref)
    return fixed


class _Group:
    """One terminal group: a spatial cluster of the net's own pads/vias
    (cec_slab_pour.terminal_clusters), optionally ganged under a manifold /
    widened by a guaranteed patch / MERGED with groups the board's existing
    own-net copper (locked force rails, pre-laid stubs, via arrays) already
    connects (_preconnect_merge, mandate part 1 2026-07-25)."""
    __slots__ = ("gid", "cells", "bbox", "cx", "cy", "native", "attach",
                 "f_zone", "eligible", "why", "is_manifold", "merged",
                 "spot", "man_layers", "lay_attach", "refs")

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
        self.refs = set()         # physical pad-owner refs represented here


def _build_groups(board, net, nc, grid, layers, anchors, man_dicts,
                  patch_dicts, shunt_boxes, authority_refs=None):
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
        # Bind raster clusters back to physical pad owners.  The aggregate
        # current-domain authority can then delegate Kelvin/monitor leaves
        # instead of asking a cable-width pour to terminate on an INA pin.
        gb = _box(*g.bbox)
        for fp in board.GetFootprints():
            ref = str(fp.GetReference() or "")
            for pad in fp.Pads():
                if pad.GetNetCode() != nc:
                    continue
                bb = pad.GetBoundingBox()
                pb = _box(bb.GetLeft() / MM, bb.GetTop() / MM,
                          bb.GetRight() / MM, bb.GetBottom() / MM)
                if gb.intersects(pb):
                    g.refs.add(ref)
                    break
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
            keep.refs |= g.refs
            del groups[g.gid]

    # guaranteed-patch cover: the patch is sanctioned F landing copper
    for d in patch_dicts:
        if d.get("net") != net:
            continue
        p = _poly_of(d.get("polygon") or ())
        owner_ref = str(d.get("owner_ref") or "")
        for g in groups.values():
            # A guaranteed shunt patch is local copper owned by that shunt,
            # not a region-class admission token. Coarse raster cluster boxes
            # can touch a nearby INA/current-monitor group even when their
            # physical pads do not; binding by intersection then makes the
            # monitor's landing jump into the remote shunt patch and strands
            # its terminal via field. New patches carry exact owner identity;
            # retain intersection fallback only for legacy/test producers.
            if owner_ref and owner_ref not in g.refs:
                continue
            if p.intersects(_box(*g.bbox)):
                g.f_zone = p if g.f_zone is None else g.f_zone.union(p)

    # pour eligibility (the F choke, planner-side): an F-only SMD group is
    # pour-servable only where top copper is admitted -- inside a shunt
    # neighborhood, its own manifold, or its guaranteed patch. Everything
    # else is honestly delegated to FR (same boundary _excludable_pad draws
    # for the reservation's pour-owned pads).
    sb_polys = [_box(*b) for b in shunt_boxes]
    authority_refs = (None if authority_refs is None
                      else {str(ref) for ref in authority_refs})
    for g in groups.values():
        if authority_refs is not None and not (g.refs & authority_refs):
            g.eligible = False
            g.why = "non-authority current-domain leaf"
            continue
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
            keep.refs |= g.refs
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
        # per-layer attach copper: the members' ACTUAL anchored cells on
        # that layer (a cluster's B-nativeness may be a few via cells --
        # its bbox edge is NOT B copper; measured: +5V_MAIN's planned B
        # corridor landed on a bbox edge over nothing and the attach
        # verify split in two) + manifold polys on their own layers + the
        # own-track capsules touching the merged extent (two passes cover
        # track chains). A hollow bbox is NEVER an attach target.
        la = {}
        hull = keep.attach
        for lay in layers:
            parts = []
            for g in members:
                if not (lay in g.native):
                    continue
                if g.is_manifold and lay in g.man_layers:
                    parts.append(g.attach)
                    continue
                cellpolys = [
                    _box(grid.x0 + c * grid.cell, grid.y0 + r * grid.cell,
                         grid.x0 + (c + 1) * grid.cell,
                         grid.y0 + (r + 1) * grid.cell)
                    for (r, c) in g.cells if anchors[lay][r, c]]
                if cellpolys:
                    parts.append(unary_union(cellpolys))
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
        raw_union = unary_union(obstacles) if obstacles else None
        copper_legal = region
        if f_allow is not None:
            copper_legal = copper_legal.intersection(f_allow)
        if raw_union is not None:
            copper_legal = copper_legal.difference(raw_union)
        # Exact conductor-domain authority.  In particular, retain small via
        # and pad holes: reconstructing this domain later by buffering the
        # centerline free space can morphologically close those holes.
        self.copper_legal = copper_legal
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


def _space_component_diag(space, pa, pb):
    """Compact endpoint-connectivity evidence for no-path diagnostics."""
    comps = [g for g in getattr(space.free, "geoms", [space.free])
             if g.geom_type == "Polygon" and not g.is_empty]
    ia = [i for i, g in enumerate(comps) if g.buffer(EPS).covers(Point(pa))]
    ib = [i for i, g in enumerate(comps) if g.buffer(EPS).covers(Point(pb))]
    return {"components": len(comps), "from": ia, "to": ib,
            "same": bool(set(ia) & set(ib)),
            "bounds": [tuple(round(v, 1) for v in g.bounds)
                       for g in comps],
            "areas": [round(g.area, 1) for g in comps]}


def _greedy_minimized_relief_sets(ranked, try_removed, initial_result):
    """Find deterministic inclusion-minimal cuts from a proven broad cut.

    ``try_removed`` is the exact path oracle and returns path evidence or
    ``None``.  This helper intentionally does not guess geometry; it only
    reduces an already-successful owner set in two stable orders so a small
    mixed-rank cut can be recovered without exponential enumeration.
    """
    ranked = tuple(ranked or ())
    if not ranked or not initial_result:
        return []
    results = []
    seen = set()
    for owner_order in (ranked, tuple(reversed(ranked))):
        removed = list(ranked)
        current_result = initial_result
        for owner in owner_order:
            if owner not in removed:
                continue
            trial_removed = tuple(item for item in removed if item != owner)
            result = try_removed(trial_removed)
            if result:
                removed = list(trial_removed)
                current_result = result
        signature = tuple(sorted(str(owner) for owner in removed))
        if signature in seen:
            continue
        seen.add(signature)
        results.append({
            **current_result,
            "search": "greedy_inclusion_minimal",
            "searched_from_owner_count": len(ranked),
        })
    results.sort(key=lambda row: (
        len(row.get("owners") or ()),
        float(row.get("length_mm") or 0.0),
        tuple(row.get("owners") or ())))
    return results


def _corridor_relief_evidence(cor, st, lay, space, *, owner_cap=18,
                              pair_cap=10, max_cardinality=4,
                              immovable_owners=()):
    """Name the smallest movable obstacle set that restores a wide path.

    This is a bounded placement diagnostic, not a geometry exception: remove
    one footprint/track owner at a time (then pairs from the closest owners),
    rebuild the exact width-expanded configuration space, and report only
    removals that make the ordinary pathfinder succeed. The placement stage
    can then relocate named owners instead of guessing from a heat map.
    """
    pa, _sa, alts_a, pb, _sb, alts_b = _endpoints_for_layer(
        cor, st, lay, space)
    if pa is None or pb is None:
        return {"layer": lay, "reason": "endpoint-blocked",
                "relief_sets": []}
    record_key = ("bundle_obstacle_records" if st.get("bundle")
                  else "obstacle_records")
    records = list((st.get(record_key) or {}).get(lay, ()))
    if not records:
        return {"layer": lay, "reason": "no-attributed-obstacles",
                "relief_sets": []}
    direct = LineString((pa, pb))
    def _relief_owner(row):
        # Generated route objects are one reroutable ownership unit per net,
        # not one independent placement degree of freedom per UUID. Treating
        # five Kelvin segments as five unrelated owners exhausted the
        # four-item ablation beam without ever testing the actionable
        # operation: release/reroute that precision net as a whole.
        if row.get("kind") in ("track", "via") and row.get("net"):
            return "%s-net:%s" % (row.get("kind"), row.get("net"))
        return row["owner"]

    by_owner = {}
    for row in records:
        by_owner.setdefault(_relief_owner(row), []).append(row)
    immovable = {str(owner) for owner in (immovable_owners or ())}
    movable_ranked = sorted(
        (owner for owner in by_owner if str(owner) not in immovable),
        key=lambda owner: (
            min(row["geometry"].distance(direct)
                for row in by_owner[owner]),
            owner))
    ranked = movable_ranked[:owner_cap]

    def _try_removed(removed):
        obstacles = [row["geometry"] for owner, rows in by_owner.items()
                     if owner not in removed for row in rows]
        if st.get("gap_geom") is not None:
            obstacles.append(st["gap_geom"])
        trial = _LayerSpace(
            st["region"], obstacles, st["reqw"][lay] / 2.0,
            f_allow=None, approach=st.get("approach"),
            half_neck=W_NECK / 2.0,
            neck_unguard=(0.0 if st.get("bundle") else 0.6))
        ta, _tsa, taa, tb, _tsb, tbb = _endpoints_for_layer(
            cor, st, lay, trial)
        pts, bends = _path_with_alternates(
            trial, ta, taa, tb, tbb,
            _projection_aligned_pairs(cor.ga, cor.gb, lay, st, trial))
        if pts is None:
            return None
        owner_bounds = {}
        for owner in removed:
            geometry = unary_union([
                row["geometry"] for row in by_owner.get(owner, ())])
            if not geometry.is_empty:
                owner_bounds[str(owner)] = [
                    round(float(value), 6) for value in geometry.bounds]
        return {
            "owners": list(removed), "bends": int(bends),
            "length_mm": round(sum(
                _dist(a, b) for a, b in zip(pts, pts[1:])), 3),
            # Preserve the successful ablation geometry.  Placement can then
            # move a named blocker directly to a width-expanded path tangent
            # instead of guessing on a board-wide Cartesian grid.
            "path_mm": [[round(float(x), 6), round(float(y), 6)]
                        for x, y in pts],
            "owner_bounds_mm": owner_bounds,
        }

    relief = []
    for owner in ranked:
        result = _try_removed((owner,))
        if result:
            relief.append(result)
    if not relief and max_cardinality >= 2:
        # Dense passive rows can form a wall only collectively. Escalate the
        # exact ablation in small bounded shells; stop at the first cardinality
        # that yields relief so the certificate is a minimum within the
        # searched owner beam.
        shells = ((2, pair_cap), (3, 10), (4, 8))
        for cardinality, cap in shells:
            if cardinality > max_cardinality:
                break
            for removed in combinations(ranked[:cap], cardinality):
                result = _try_removed(removed)
                if result:
                    relief.append(result)
                    if len(relief) >= 6:
                        break
            if relief:
                break
    # A bounded minimum-cut beam can legitimately find no cut.  Distinguish
    # "the useful cut is wider than the beam" from "movable placement cannot
    # solve this topology at all" with one exact counterfactual: remove every
    # ranked movable owner and rerun the same width-expanded pathfinder.  This
    # is diagnostic only; it never authorizes a mass move or weakens copper
    # clearance.  Placement can use the result to choose a larger local
    # window, while a false result points at fixed/unattributed geometry.
    all_ranked_result = None
    all_movable_result = None
    wide_relief = []
    if not relief and ranked:
        all_ranked_result = _try_removed(tuple(ranked))
        if all_ranked_result:
            # Minimize the successful broad cut without enumerating the
            # exponential owner power set.  Two deterministic greedy orders
            # expose both a near-demand-biased and a far-obstacle-biased
            # inclusion-minimal cut.  These remain diagnosis/placement input;
            # they are deliberately separate from the <=4-owner exact beam.
            wide_relief = _greedy_minimized_relief_sets(
                ranked, _try_removed, all_ranked_result)
            # The prefix-bounded combination beam can miss a small mixed-rank
            # cut (for example owners ranked 1 and 11).  If broad removal plus
            # exact greedy minimization proves that the resulting cut is still
            # within the declared cardinality bound, promote that witness to
            # the ordinary relief contract.  This expands ranking coverage,
            # not move cardinality, and the path was re-proved by the same
            # width/clearance authority as every enumerated cut.
            existing_cuts = {
                tuple(sorted(str(owner) for owner in row.get("owners") or ()))
                for row in relief}
            for result in wide_relief:
                signature = tuple(sorted(
                    str(owner) for owner in result.get("owners") or ()))
                if (not signature or len(signature) > max_cardinality
                        or signature in existing_cuts):
                    continue
                relief.append(result)
                existing_cuts.add(signature)
        elif len(movable_ranked) > len(ranked):
            # ``owner_cap`` bounds combinatorial diagnosis, not the meaning of
            # "placement cannot solve this topology." Prove that stronger
            # statement by removing every attributed movable owner once. A
            # success means the local beam was too narrow; a failure isolates
            # the obstruction to fixed, unattributed, or categorical geometry.
            all_movable_result = _try_removed(tuple(movable_ranked))
            if all_movable_result:
                wide_relief = _greedy_minimized_relief_sets(
                    movable_ranked, _try_removed, all_movable_result)
                existing_cuts = {
                    tuple(sorted(str(owner) for owner in
                                 row.get("owners") or ()))
                    for row in relief}
                for result in wide_relief:
                    signature = tuple(sorted(
                        str(owner) for owner in
                        result.get("owners") or ()))
                    if (not signature
                            or len(signature) > max_cardinality
                            or signature in existing_cuts):
                        continue
                    relief.append(result)
                    existing_cuts.add(signature)
    owner_detail = {
        owner: {"kind": by_owner[owner][0].get("kind"),
                "net": by_owner[owner][0].get("net"),
                "items": sorted({row.get("detail") for row in
                                  by_owner[owner]})}
        for result in relief for owner in result["owners"]}
    ranked_candidates = [{
        "owner": owner,
        "kind": by_owner[owner][0].get("kind"),
        "net": by_owner[owner][0].get("net"),
        "distance_to_demand_mm": round(min(
            row["geometry"].distance(direct)
            for row in by_owner[owner]), 3),
        "items": sorted({row.get("detail") for row in by_owner[owner]}),
    } for owner in ranked]
    return {
        "layer": lay,
        "required_width_mm": round(float(st["reqw"][lay]), 6),
        "components": _space_component_diag(space, pa, pb),
        "relief_sets": relief,
        "owners": owner_detail,
        "ranked_candidates": ranked_candidates,
        "searched_owner_count": len(ranked),
        "total_movable_owner_count": len(movable_ranked),
        "all_ranked_removal_restores_path": bool(all_ranked_result),
        "all_ranked_removal_path": all_ranked_result,
        "all_movable_removal_restores_path": bool(
            all_movable_result or all_ranked_result),
        "all_movable_removal_path": (
            all_movable_result or all_ranked_result),
        "wide_relief_sets": wide_relief,
        "immovable_owners": sorted(
            owner for owner in by_owner if str(owner) in immovable),
    }


def _find_path(space, p_from, p_to, *, max_corners=192):
    """Rectilinear centerline from ``p_from`` to ``p_to`` in ``space``.

    Wide pour geometry is an orthogonal-routing problem. The former arbitrary-
    angle visibility graph found short diagonal centerlines and then asked the
    emitter to approximate their capsules with a raster staircase. Besides the
    visual defect, that late conversion could shave min-width or via coverage.
    This search uses an exact sparse Manhattan grid built from terminal and
    clearance-obstacle coordinates. Every accepted edge is horizontal or
    vertical and lies in the same configuration space used by clearance proof.
    """
    if not (space.ok_pt(p_from) and space.ok_pt(p_to)):
        return None, None
    sx, sy = p_from
    tx, ty = p_to
    if (abs(sx - tx) <= 1e-9 or abs(sy - ty) <= 1e-9) and \
            space.ok_line(p_from, p_to):
        return [p_from, p_to], 0
    # The two canonical one-bend doglegs are both cheaper and clearer than a
    # graph solve; test them first.
    cands = [(sx, ty), (tx, sy)]
    best = None
    for corner in cands:
        if space.ok_line(p_from, corner) and space.ok_line(corner, p_to):
            length = _dist(p_from, corner) + _dist(corner, p_to)
            if best is None or length < best[0]:
                best = (length, [tuple(p_from), tuple(corner), tuple(p_to)])
    if best is not None:
        return best[1], 1

    # The search halo scales with terminal separation. A fixed crop hid legal
    # side detours around wide connector pin walls.
    detour_halo = max(12.0, _dist(p_from, p_to))
    reg = _box(min(sx, tx), min(sy, ty), max(sx, tx),
               max(sy, ty)).buffer(detour_halo)
    corners = list({(round(c[0], 6), round(c[1], 6))
                    for c in space.corners if reg.covers(Point(c))})
    if len(corners) > max_corners:
        mid = ((sx + tx) / 2.0, (sy + ty) / 2.0)
        corners.sort(key=lambda c: _dist(c, mid))
        corners = corners[:max_corners]

    # Obstacle-corner coordinate cross-product, searched lazily. Unlike a
    # uniform raster it creates a bend only at a meaningful geometric event,
    # so a detour around a rectangle is one clean U rather than a staircase.
    xs = {round(sx, 6), round(tx, 6)}
    ys = {round(sy, 6), round(ty, 6)}
    for x, y in corners:
        xs.add(x)
        ys.add(y)
    for component in getattr(space.free, "geoms", [space.free]):
        if component.is_empty or component.geom_type != "Polygon":
            continue
        x0, y0, x1, y1 = component.bounds
        xs.update((round(x0, 6), round(x1, 6)))
        ys.update((round(y0, 6), round(y1, 6)))
    xs, ys = sorted(xs), sorted(ys)
    x_index = {value: index for index, value in enumerate(xs)}
    y_index = {value: index for index, value in enumerate(ys)}
    start = (x_index[round(sx, 6)], y_index[round(sy, 6)], 0)
    target_xy = (x_index[round(tx, 6)], y_index[round(ty, 6)])

    import heapq
    point_ok = {}
    edge_ok = {}

    def _point(ix, iy):
        return (xs[ix], ys[iy])

    def _node_ok(ix, iy):
        key = (ix, iy)
        if key not in point_ok:
            point_ok[key] = space.ok_pt(_point(ix, iy))
        return point_ok[key]

    def _edge_legal(a, b):
        key = (a, b) if a <= b else (b, a)
        if key not in edge_ok:
            edge_ok[key] = space.ok_line(_point(*a), _point(*b))
        return edge_ok[key]

    dist = {start: 0.0}
    metric = {start: (0, 0.0)}              # bends, physical length
    par = {}
    heap = [(0.0, 0, 0.0, start)]
    winner = None
    while heap:
        cost, bends, length, state = heapq.heappop(heap)
        if cost > dist.get(state, float("inf")) + 1e-12:
            continue
        ix, iy, direction = state
        if (ix, iy) == target_xy:
            winner = state
            break
        for jx, jy, new_direction in (
                (ix - 1, iy, 1), (ix + 1, iy, 1),
                (ix, iy - 1, 2), (ix, iy + 1, 2)):
            if not (0 <= jx < len(xs) and 0 <= jy < len(ys)):
                continue
            if not _node_ok(jx, jy) or \
                    not _edge_legal((ix, iy), (jx, jy)):
                continue
            step = abs(xs[jx] - xs[ix]) + abs(ys[jy] - ys[iy])
            turned = int(direction not in (0, new_direction))
            nbends = bends + turned
            nlength = length + step
            ncost = nlength + 1.5 * nbends
            nxt = (jx, jy, new_direction)
            if (ncost, nbends, nlength) < (
                    dist.get(nxt, float("inf")),
                    *(metric.get(nxt, (10**9, float("inf"))))):
                dist[nxt] = ncost
                metric[nxt] = (nbends, nlength)
                par[nxt] = state
                heapq.heappush(heap, (ncost, nbends, nlength, nxt))
    if winner is None:
        return None, None

    states = [winner]
    while states[-1] != start:
        states.append(par[states[-1]])
    states.reverse()
    pts = [_point(ix, iy) for ix, iy, _direction in states]
    # Collapse coordinate-grid subdivisions; retain only actual 90-degree
    # direction changes.
    simplified = [pts[0]]
    for point in pts[1:]:
        simplified.append(point)
        while len(simplified) >= 3:
            a, b, c = simplified[-3:]
            if not ((abs(a[0] - b[0]) <= 1e-9 and
                     abs(b[0] - c[0]) <= 1e-9) or
                    (abs(a[1] - b[1]) <= 1e-9 and
                     abs(b[1] - c[1]) <= 1e-9)):
                break
            simplified.pop(-2)
    return simplified, max(0, len(simplified) - 2)


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


def _patch_spots(g, toward):
    """Candidate bridge centers inside a guaranteed same-net landing patch.

    A patch-covered terminal is electrically reachable anywhere on that patch,
    not only on a fixed compass ring around the component pad. Limiting a
    foreign-layer route to the ring made the full-width trunk stop beside the
    patch and then dogleg back into it. Sample the via-safe patch boundary so
    endpoint choice and corridor routing can be optimized together.
    """
    if g.f_zone is None:
        return []
    core = g.f_zone.buffer(-VIA_R, join_style=2)
    if core.is_empty:
        core = g.f_zone
    out = []
    for component in getattr(core, "geoms", [core]):
        if component.is_empty or component.geom_type != "Polygon":
            continue
        out.append(tuple(nearest_points(component, toward)[0].coords[0]))
        coords = list(component.exterior.coords)[:-1]
        out.extend(tuple(p) for p in coords)
        out.extend(((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
                   for a, b in zip(coords, coords[1:] + coords[:1]))
        out.append(tuple(component.representative_point().coords[0]))
    unique = []
    seen = set()
    for point in out:
        key = (round(point[0], 6), round(point[1], 6))
        if key not in seen:
            seen.add(key)
            unique.append(point)
    return unique


def plan_pours(board, asks, *, cell_mm=0.8, clearance_mm=0.3,
               manifolds=True, collect=None, fallback=None,
               relief_diagnostics=True):
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
    declared_bundles = declared_parallel_bundles(board, asks)
    try:
        import cec_current_topology as _current_topology
        current_domains = _current_topology.board_current_domains(
            board, board_hint=(os.environ.get("CEC_THERMAL_BOARD_HINT")
                               or getattr(board, "GetFileName", lambda: "")()))
    except Exception:                                  # noqa: BLE001
        current_domains = {}
    shunt_boxes = shunt_neighborhoods(board)
    region = _box(grid.x0, grid.y0, grid.x1, grid.y1)
    # ALL pad boxes, any net (assembly-class via-in-pad exclusion, owner
    # ruling 2026-07-25: no via barrel in/overlapping ANY pad -- the
    # foreign-copper guards exempt same-net pads by construction, which
    # was the measured gap) + the inter-pad GAP strips (pour-termination
    # ruling: the gap belongs exclusively to the Kelvin tap stubs).
    pad_boxes = []
    pad_box_records = []
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
            pad_box = (bb.GetLeft() / MM, bb.GetTop() / MM,
                       bb.GetRight() / MM, bb.GetBottom() / MM)
            pad_boxes.append(pad_box)
            pad_box_records.append({
                "owner": str(fp.GetReference() or ""),
                "pad": str(p.GetPadName() or ""),
                "net": str(p.GetNetname() or ""),
                "box": pad_box,
            })
    gap_strips = [sh["gap"] for sh in _sp._shunt_pad_halves(board)]
    gap_geom = (unary_union([_box(*gsp) for gsp in gap_strips])
                if gap_strips else None)

    # FUTURE-ROUTE-AWARE LOCAL PI/GND TERRITORY. Broad current corridors are
    # compiled before local cells and plane portals, but the ordering must not
    # allow a pour to occupy their only legal dogbone or through-via column.
    # Probe the exact production sequence (complete bypass cells, then every
    # surface-GND plane entry) on the unpoured board once and feed its read-
    # only primitives to every per-net obstacle solve. Fake/host boards retain
    # the old behavior.
    decoupler_access = {"schema": 1, "ok": True, "primitives": [],
                        "cells": [], "refused": []}
    if pcbnew is not None and hasattr(board, "BuildConnectivity"):
        try:
            import cec_decoupler_cell as _decoupler_cell
            board_path = getattr(board, "GetFileName", lambda: "")()
            decoupler_access = (
                _decoupler_cell.supply_access_reservations_file(board_path)
                if board_path and os.path.isfile(board_path) else
                _decoupler_cell.supply_access_reservations_board(board))
        except Exception as access_error:              # noqa: BLE001
            decoupler_access = {
                "schema": 1, "ok": False, "primitives": [],
                "cells": [], "refused": [{
                    "reason": "%s: %s" % (
                        type(access_error).__name__, access_error)}],
            }
    access_primitives, deferred_ground_access = _priority_access_primitives(
        decoupler_access.get("primitives") or ())
    if deferred_ground_access:
        print(
            "[cec_pour_plan] deferred %d reseatable surface-GND portal "
            "primitive(s) until after declared-current copper" %
            len(deferred_ground_access), file=sys.stderr)

    # PROSPECTIVE KELVIN OWNERSHIP.  Kelvin taps are synthesized after the
    # high-current territory pass, so they are absent from pcbnew's ordinary
    # foreign-copper masks.  Without an explicit future reservation, a power
    # replan can consume the exact lane placement just opened for a tap and
    # create a placement/power chase.  Reuse the route keepout derivation as a
    # single geometry authority, but retain its net ownership: only foreign
    # rails are blocked; the tap's own sense pour remains free to merge.
    future_kelvin = []
    if pcbnew is not None and hasattr(board, "BuildConnectivity"):
        try:
            import cec_fr as _fr
            future_kelvin = _fr.tap_channel_keepouts(
                getattr(board, "GetFileName", lambda: "")(), board=board)
        except Exception as kelvin_error:               # noqa: BLE001
            print("[cec_pour_plan] future Kelvin reservation derivation "
                  "skipped: %s: %s" % (type(kelvin_error).__name__,
                                        kelvin_error), file=sys.stderr)

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

    # POUR ELIGIBILITY (owner 2026-07-26: "is it on the wrong netclass?" for the
    # L3 slab crossing the rightmost shunt). It was not a netclass problem --
    # net_currents only ORDERED the asks, it never decided whether a net earns a
    # region at all, so +3V3 (LDO-fed, 0.25A per the spec table) drew a 391mm2
    # In2 slab spanning x 22.9-60.5 / y 18.9-34.9: across the shunt row, over
    # RS1, swallowing U11 / RS2 / U612V1 pads, and the last producer still
    # emitting long diagonal fill edges. A rail a plain track carries with
    # margin routes as a track. IPC-2221: 0.25mm of 1oz outer carries ~1.3A, so
    # the floor is set where a pour starts to buy something real.
    _pour_floor = float(os.environ.get("CEC_POUR_MIN_AMPS", "1.5"))

    def _amps_of(n):
        """The LARGER of the thermal overlay and the spec table.

        Two reasons it is a max, not a preference. (1) The overlay carries only
        the 9 heavy rails -- +3V3 is absent from it, so keying the gate on the
        overlay alone left it INERT for the very net that motivated it
        (measured). (2) The two sources DISAGREE where both have a value:
        /SENSE5V_HI reads 25A in the overlay against the spec table's 20A
        (the owner's 2026-07-26 ceiling), and +5VSB reads 5.0 vs 0.5. Skipping
        a rail's copper on the smaller of two disagreeing numbers is the one
        failure that is not recoverable later, so the gate takes the max and
        the drift is an owner item rather than a silent pick.
        """
        # CLI/direct callers do not pass through cec_full_pipeline's
        # environment wrapper. Use the loaded board filename as the stable
        # identity fallback so the very same PCIe/EPS current contract sizes
        # pours in tests, review tools, and production runs.
        board_hint = (os.environ.get("CEC_THERMAL_BOARD_HINT")
                      or getattr(board, "GetFileName", lambda: "")())
        return _design_current_amps(
            n, overlay_currents=net_currents, board_hint=board_hint)

    # NOT WHERE THE POUR IS THE NET'S DISTRIBUTION MECHANISM (2026-07-27).
    # The floor exists to stop a low-current rail claiming a territory REGION on
    # a pour-first board (+3V3's 391mm2 In2 slab). Where floods are post-route
    # ADDITIVE they also carry CONNECTIVITY -- that is why power_pickup stitches
    # pads into their covering flood -- so gating one strands pads. Measured on
    # the hub: gating /USB_VBUS at 0.5A left J_USB's four VBUS pads unable to
    # reach C10/D6, eight of the board's sixteen remaining gaps. An ask with
    # evac False is an additive flood; leave it alone.
    _additive = {a.get("net") for a in asks if a.get("evac") is False}
    _thin = [n for n in ask_nets
             if n not in _additive and 0.0 < _amps_of(n) < _pour_floor]
    for _n in _thin:
        ask_nets.remove(_n)
        _e = _fail_entry(
            "no pour: %.2fA is below the %.2fA pour floor -- a track carries "
            "it (CEC_POUR_MIN_AMPS)" % (_amps_of(_n), _pour_floor))
        # NOT a failure: a deliberate skip must not read as no-path, or the v3
        # loud rule answers it with exactly the insurance copper this removes.
        _e["skipped"] = True
        _e["path_found"] = True
        report[_n] = _e
    # Higher-current rails claim scarce copper first.  Equal-current
    # commodities follow the board's declared electrical importance, with a
    # stable name fallback for boards that do not need an explicit order.
    order = power_net_order(ask_nets, _amps_of)
    ask_by_net = {}
    for a in asks:
        if a.get("net") in nets_nc:
            ask_by_net.setdefault(a["net"], a)

    # ---- phase A: per-net prep + terminal groups + corridor candidates ----
    nets = {}
    for net in order:
        nc = nets_nc[net]
        enabled = set(_fab.enabled_copper_layers(board))
        layers = [l for l in LAYERS_ALL if l in enabled]
        if not layers:
            report[net] = _fail_entry("no valid layer")
            continue
        foreign, anchors = {}, {}
        for lay in layers:
            f, an = rasterize(board, nc, board.GetLayerID(lay), grid,
                              clearance_mm)
            foreign[lay], anchors[lay] = f, an
        # The thermal overlay intentionally has no bespoke entry for ordinary
        # EPS/PCIe main boards; their design current lives in the shared board
        # design-basis table.  Using only ``net_currents`` therefore planned
        # every such force corridor at the 1.2 mm unknown-current fallback,
        # even while the eligibility gate below correctly knew it was 39 A.
        # One resolver must size, order, and admit the corridor.
        amps = _amps_of(net)
        # Use the same resolved contract exported to the production compiler.
        # The planner adds transient geometry fields to this mapping, so take
        # a fresh copy rather than mutating the shared admission evidence.
        bundle = dict(declared_bundles.get(net) or {}) or None
        layer_amps = {
            lay: (amps * bundle["per_layer_fraction"]
                  if bundle and lay in bundle["layers"] else amps)
            for lay in layers}
        # _design_current_amps returns the geometry basis with its declared
        # margin already applied.  Passing that value through req_width_mm's
        # historical 1.25 default applied the same reserve twice (the PCIe
        # 39 A / 1.25 contract became 60.94 A before the IPC inverse).  The
        # territory planner therefore uses a unity local margin; the source
        # contract remains the single authority for reserve.
        reqw = required_widths_from_geometry_basis(
            layer_amps, layers, board)
        rcells = {lay: max(1, int(round(reqw[lay] / (2.0 * grid.cell))))
                  for lay in layers}
        domain = current_domains.get(net) or {}
        authority_refs = (domain.get("authority_refs")
                          if domain.get("complete") else None)
        groups, clab, why, gang_man = _build_groups(
            board, net, nc, grid, layers, anchors,
            man_by_net.get(net, ()), patch_dicts, shunt_boxes,
            authority_refs=authority_refs)
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
            "amps": amps,
            "anchors": anchors, "reqw": reqw, "rcells": rcells,
            "layer_amps": layer_amps, "bundle": bundle,
            "groups": groups, "served": served, "delegated": delegated,
            "clab": clab, "corridors": [], "notes": [], "region": region,
            "own_pours": own_pours, "_grid": grid, "pad_boxes": pad_boxes,
            "pad_box_records": pad_box_records,
            "board": board,
            "gap_geom": gap_geom, "gang_man": gang_man,
            # Mechanical/current-domain terminals cannot be relocated to
            # relieve their own escape.  Preserve them in obstacle geometry,
            # but exclude them from the bounded ablation beam so the failure
            # certificate names the smallest *actionable* neighboring cell.
            "authority_refs": tuple(authority_refs or ()),
            "fixed_authority_refs": tuple(sorted(
                _fixed_current_authority_refs(board, authority_refs))),
            # ``"light"`` is an actionable single-owner certificate for
            # negotiated-congestion beam expansion.  ``True`` retains the
            # exhaustive bounded combination shells for terminal forensics.
            "relief_diagnostics": relief_diagnostics,
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
        obstacle_records = _geo_obstacle_records(
            board, nc, layers, clearance_mm, 0.75 * grid.cell,
            access_primitives=access_primitives)
        future_kelvin_count = _append_owned_rect_reservation_records(
            obstacle_records, future_kelvin, net,
            kind="future_kelvin_tap")
        obst = {lay: [row["geometry"] for row in rows]
                for lay, rows in obstacle_records.items()}
        # foreign manifolds / patches are obstacles on their layer
        for on, mds in man_by_net.items():
            if on == net:
                continue
            for d in mds:
                if d.get("layer") in obst:
                    obst[d["layer"]].append(
                        _poly_of(d["polygon"]).buffer(clearance_mm))
                    obstacle_records[d["layer"]].append({
                        "geometry": obst[d["layer"]][-1],
                        "kind": "reserved_pour",
                        "owner": str(d.get("name") or on),
                        "detail": str(d.get("name") or on), "net": on,
                    })
        for d in patch_dicts:
            if d.get("net") != net and "F.Cu" in obst:
                obst["F.Cu"].append(
                    _poly_of(d["polygon"]).buffer(clearance_mm))
                obstacle_records["F.Cu"].append({
                    "geometry": obst["F.Cu"][-1],
                    "kind": "reserved_patch",
                    "owner": str(d.get("name") or d.get("net")),
                    "detail": str(d.get("name") or d.get("net")),
                    "net": d.get("net"),
                })
        # Explicit parallel bundles use exact geometric clearance throughout
        # search and verification. Do not carry the legacy raster-alias guard
        # into that exact solve: clearance + half conductor width is the real
        # configuration-space inflation. The guarded geometry remains the
        # authority for ordinary raster-verified corridors.
        bundle_obstacle_records = None
        bundle_obst = None
        if bundle:
            bundle_obstacle_records = _geo_obstacle_records(
                board, nc, layers, clearance_mm, 0.0,
                access_primitives=access_primitives)
            _append_owned_rect_reservation_records(
                bundle_obstacle_records, future_kelvin, net,
                kind="future_kelvin_tap")
            bundle_obst = {
                lay: [row["geometry"] for row in rows]
                for lay, rows in bundle_obstacle_records.items()}
            for on, mds in man_by_net.items():
                if on == net:
                    continue
                for d in mds:
                    lay = d.get("layer")
                    if lay not in bundle_obst:
                        continue
                    geometry = _poly_of(d["polygon"]).buffer(clearance_mm)
                    bundle_obst[lay].append(geometry)
                    bundle_obstacle_records[lay].append({
                        "geometry": geometry, "kind": "reserved_pour",
                        "owner": str(d.get("name") or on),
                        "detail": str(d.get("name") or on), "net": on,
                    })
            for d in patch_dicts:
                if d.get("net") == net or "F.Cu" not in bundle_obst:
                    continue
                geometry = _poly_of(d["polygon"]).buffer(clearance_mm)
                bundle_obst["F.Cu"].append(geometry)
                bundle_obstacle_records["F.Cu"].append({
                    "geometry": geometry, "kind": "reserved_patch",
                    "owner": str(d.get("name") or d.get("net")),
                    "detail": str(d.get("name") or d.get("net")),
                    "net": d.get("net"),
                })
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
        approach_parts = [b.buffer(APPROACH_MM) for b in own_boxes]
        terminal_fields = _multipin_terminal_approach_fields(board, nc)
        approach_parts.extend(terminal_fields)
        approach = (unary_union(approach_parts)
                    if approach_parts else None)
        spaces = {}
        for lay in layers:
            spaces[lay] = _LayerSpace(
                region, obst[lay], reqw[lay] / 2.0,
                f_allow=f_allow if lay == "F.Cu" else None,
                approach=approach, half_neck=W_NECK / 2.0,
                neck_unguard=0.75 * grid.cell)
        nets[net]["spaces"] = spaces
        nets[net]["obst"] = obst
        nets[net]["obstacle_records"] = obstacle_records
        nets[net]["bundle_obstacle_records"] = bundle_obstacle_records
        nets[net]["bundle_obst"] = bundle_obst
        nets[net]["f_allow"] = f_allow
        nets[net]["approach"] = approach
        nets[net]["terminal_field_approach_count"] = len(terminal_fields)
        nets[net]["future_kelvin_reservation_count"] = int(
            future_kelvin_count)
        if bundle:
            # Each parallel conductor gets an independent path on its own
            # layer. Requiring identical centerlines creates a fictitious
            # common bottleneck wherever an F.Cu-only and B.Cu-only obstacle
            # are offset. The common contract is electrical attachment and
            # per-layer ampacity, not coincident geometry. The explicit bundle
            # is the narrow exception to the ordinary F.Cu shunt-only
            # preference because its F.Cu copper is structural and reserved
            # before signal routing. Shunt gaps remain hard obstacles.
            bundle_width = max(reqw[lay] for lay in bundle["layers"])
            bundle["width_mm"] = bundle_width
            bundle["primary_layer"] = (
                "B.Cu" if "B.Cu" in bundle["layers"]
                else bundle["layers"][0])
            bundle["spaces"] = {}
            for lay in bundle["layers"]:
                bundle_obstacles = list(bundle_obst[lay])
                if gap_geom is not None:
                    bundle_obstacles.append(gap_geom)
                bundle["spaces"][lay] = _LayerSpace(
                    region, bundle_obstacles, reqw[lay] / 2.0,
                    f_allow=None, approach=approach,
                    half_neck=W_NECK / 2.0,
                    # Bundle obstacles are already exact-clearance geometry;
                    # unlike the ordinary raster-guarded obstacle set there
                    # is no alias margin to subtract in the terminal neck.
                    neck_unguard=0.0)

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

    # Future-route-aware candidate expansion: the exact assignment needs more
    # than one locally shortest geometry when commodities compete for a belt.
    _expand_future_conflict_alternatives(nets, order)

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
        entry["future_kelvin_reservation_count"] = int(
            st.get("future_kelvin_reservation_count") or 0)
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
        ask = dict(ask_by_net.get(net) or {
            "net": net, "layers": ("In2.Cu",)})
        # The fallback is a different geometry engine, not a license to drop
        # the sizing basis that caused the territory planner to refuse.  Pass
        # the resolved, margin-inclusive current explicitly so a no-path at
        # 48.75 A cannot become a falsely successful 1.2 mm / 0 A lane.
        ask["design_current_A"] = float(st.get("amps") or 0.0)
        sub = {}
        if fallback is not None:
            fdicts, fvias, fent = fallback(board, ask, sub)
        else:
            fdicts, fvias, fent = _default_fallback(board, ask, sub,
                                                    manifolds, man_by_net)
        fent = dict(fent or {})
        fent["fallback"] = "route_overunder"
        fent["future_kelvin_reservation_count"] = int(
            st.get("future_kelvin_reservation_count") or 0)
        fent["planner_reason"] = entry.get("reason") or entry.get("bottleneck")
        if entry.get("bottleneck"):
            fent["planner_bottleneck"] = entry["bottleneck"]
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
    # The dashboard, KiCad writer, and thermal solver must all see the same
    # geometry. Do not let any upstream producer reintroduce a diagonal and
    # rely on a later renderer to hide it with blocky raster steps.
    _assert_manhattan_pours(pour_dicts)
    return pour_dicts, via_list, report


def _fail_entry(reason, *, bottleneck=None):
    entry = {"path_found": False, "segments": 0, "bridges": 0,
             "layers_used": [], "reason": reason, "planner": "territory"}
    if bottleneck:
        entry["bottleneck"] = bottleneck
    return entry


def _exact_clearance_clash_evidence(realized, records, *, area_floor=1e-6):
    """Attribute exact realized-copper collisions to physical owners.

    Bundle paths are proven in exact configuration space, but terminal cover
    copper and other realization-time geometry are added after the centerline
    search. If that final union is illegal, retain the owner and overlap
    geometry instead of collapsing the certificate to an unactionable layer
    name.
    """
    clashes = []
    for row in records or ():
        obstacle = row.get("geometry")
        if obstacle is None or obstacle.is_empty or not realized.intersects(
                obstacle):
            continue
        intersection = realized.intersection(obstacle)
        area = float(intersection.area)
        if area <= float(area_floor):
            continue
        clashes.append({
            "owner": str(row.get("owner") or ""),
            "kind": str(row.get("kind") or ""),
            "detail": str(row.get("detail") or ""),
            "net": str(row.get("net") or ""),
            "intersection_area_mm2": round(area, 6),
            "intersection_bounds_mm": [
                round(float(value), 6) for value in intersection.bounds],
        })
    clashes.sort(key=lambda row: (
        -row["intersection_area_mm2"], row["owner"], row["detail"]))
    return clashes


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
    if (_pad_hit(st.get("pad_boxes", ()), pt[0], pt[1], VIA_R + PAD_MARGIN)
            and not _pofv_spot_allowed(st, pt)):
        return False
    if g.f_zone is not None and not g.f_zone.covers(Point(pt)):
        return False
    return True


def _pofv_spot_allowed(st, pt):
    """True only when a conservative pad hit is an explicitly qualified
    same-net POFV placement on the board's declared fabrication profile."""
    board = st.get("board")
    nc = st.get("nc")
    if board is None or nc is None or pcbnew is None:
        return False
    at = pcbnew.VECTOR2I(int(round(pt[0] * MM)), int(round(pt[1] * MM)))
    blocking, allowed = _fab.via_at_pad_conflicts(
        board, at, int(round(2.0 * VIA_R * MM)), int(round(0.5 * MM)), nc)
    return blocking is None and bool(allowed)


def _field_vias(field6, half_w, grid, pad_boxes, placed, *, pitch_mm=1.2,
                ledger_mm=0.85, st=None, n_needed=None):
    """Via positions for ONE compact field -- DELEGATES to the shared
    cec_slab_pour.field_via_line (2026-07-25: the rect-realized fallback
    lays fields through the identical code path, so the two via
    disciplines can never drift). Same signature/return as always."""
    allow = ((lambda x, y: _pofv_spot_allowed(st, (x, y)))
             if st is not None else None)
    return _sp.field_via_line(field6, half_w, grid, pad_boxes, placed,
                              pitch_mm=pitch_mm, ledger_mm=ledger_mm,
                              pad_allow=allow, n_needed=n_needed)


def _field_terminal_pofv_seed(net, field, st, grid, placed, *,
                              ledger_mm=0.85, allowed_refs=None):
    """Return one profile-qualified same-net terminal POFV seed, if any.

    A terminal field normally lands beside its pad. In a dense current cell,
    the exact two-layer overlap can erode below one via diameter even though a
    large SMD terminal pad is explicitly qualified for filled/capped POFV.
    Use that process authority only after ordinary field placement fails. The
    complete land must fit the same-net pad, no foreign pad/track may overlap,
    and the global barrel ledger remains mandatory.
    """
    if st is None or st.get("board") is None or st.get("nc") is None:
        return []
    cx = grid.x0 + (field[1] + 0.5) * grid.cell
    cy = grid.y0 + (field[0] + 0.5) * grid.cell
    allowed_refs = (set(map(str, allowed_refs))
                    if allowed_refs is not None else None)
    candidates = []
    for row in st.get("pad_box_records") or ():
        if str(row.get("net") or "") != str(net or ""):
            continue
        if (allowed_refs is not None
                and str(row.get("owner") or "") not in allowed_refs):
            continue
        x0, y0, x1, y1 = map(float, row["box"])
        point = ((x0 + x1) / 2.0, (y0 + y1) / 2.0)
        candidates.append((
            _dist(point, (cx, cy)), str(row.get("owner") or ""),
            str(row.get("pad") or ""), point))
    for _distance, _owner, _pad, (x, y) in sorted(candidates):
        if any(_dist((x, y), other) < ledger_mm - EPS
               for other in placed or ()):
            if os.environ.get("CEC_POUR_PLAN_DEBUG"):
                print("[cec_pour_plan][dbg] %s terminal POFV %s.%s "
                      "rejected by via ledger at (%.3f,%.3f)" %
                      (net, _owner, _pad, x, y), file=sys.stderr)
            continue
        if not _pofv_spot_allowed(st, (x, y)):
            if os.environ.get("CEC_POUR_PLAN_DEBUG"):
                at = pcbnew.VECTOR2I(
                    int(round(x * MM)), int(round(y * MM)))
                blocking, allowed = _fab.via_at_pad_conflicts(
                    st["board"], at, int(round(2.0 * VIA_R * MM)),
                    int(round(0.5 * MM)), st["nc"])
                blocker = (blocking.GetParentFootprint().GetReference()
                           if blocking is not None else "none")
                print("[cec_pour_plan][dbg] %s terminal POFV %s.%s "
                      "rejected by profile/pad fit at (%.3f,%.3f); "
                      "blocker=%s decisions=%s" %
                      (net, _owner, _pad, x, y, blocker, allowed),
                      file=sys.stderr)
            continue
        if not _sp.via_clear_of_foreign_tracks(
                st["board"], st["nc"], x, y,
                diameter_mm=2.0 * VIA_R, clearance_mm=PAD_MARGIN):
            if os.environ.get("CEC_POUR_PLAN_DEBUG"):
                print("[cec_pour_plan][dbg] %s terminal POFV %s.%s "
                      "rejected by foreign track clearance at (%.3f,%.3f)" %
                      (net, _owner, _pad, x, y), file=sys.stderr)
            continue
        if os.environ.get("CEC_POUR_PLAN_DEBUG"):
            print("[cec_pour_plan][dbg] %s terminal POFV %s.%s "
                  "accepted at (%.3f,%.3f)" %
                  (net, _owner, _pad, x, y), file=sys.stderr)
        return [(round(x, 3), round(y, 3))]
    return []


def _field_via_need(st, field, half_w, *, pitch_mm=1.2):
    """Barrel count for a physical layer transition.

    ``layer_amps`` already contains the margin-inclusive design current for
    each conductor.  A terminal field feeding a parallel layer must therefore
    carry the larger participating-layer share through its barrels; sizing by
    corridor width alone can materially under-provision that transfer.  The
    legacy width heuristic remains only for callers without a current basis.
    """
    layer_amps = (st or {}).get("layer_amps") or {}
    amps = max((float(layer_amps.get(layer) or 0.0)
                for layer in field[2:4]), default=0.0)
    if amps > 0.0:
        return _sp.vias_for_current(amps, margin=1.0)
    return min(_sp.FIELD_VIA_CAP,
               max(1, int(round((2.0 * half_w) / pitch_mm)) + 1))


def _field_via_minimum(st, field):
    """Hard barrel count: enough ampacity, excluding the desired spare."""
    layer_amps = (st or {}).get("layer_amps") or {}
    amps = max((float(layer_amps.get(layer) or 0.0)
                for layer in field[2:4]), default=0.0)
    if amps <= 0.0:
        return 1
    return max(1, min(_sp.FIELD_VIA_CAP,
                      int(math.ceil(amps / _sp.VIA_AMPS))))


def _spread_field_over_overlap(field, vias, overlap, grid, pad_boxes,
                               reserved=(), *, st=None,
                               pitch_mm=1.2, ledger_mm=0.85, region=None,
                               edge_clearance_mm=0.5, target_count=None):
    """Lay a uniform transition/stitch lattice in the two-layer overlap.

    Broad terminal fields use a centered, near-isotropic rectangular lattice
    in the largest clear axis-aligned rectangle of the connected overlap;
    row/column orientation follows that rectangle's aspect ratio, while a
    modest preferred pitch avoids peppering the whole pour. A genuine
    mid-route crossing stays compact at its defined transition point. This
    makes current-sharing vias regular and reviewable without scattering
    drills through every hook and pocket.

    Returns ``(positions, moved_count, span_before_mm, span_after_mm)``. If a
    full safe replacement cannot be found, the original verified field is
    returned unchanged.
    """
    vias = list(vias or ())
    target_count = int(target_count if target_count is not None else
                       len(vias))
    if (target_count <= 1 or overlap is None or overlap.is_empty or
            (len(field) > 6 and field[6] == "crossing")):
        return vias, 0, 0.0, 0.0
    core = overlap.buffer(-(VIA_R + 0.05), join_style=2)
    region = region if region is not None else (
        st.get("region") if st is not None else None)
    if region is not None:
        # Authored zones may extend beyond Edge.Cuts and rely on KiCad's fill
        # clip. A via in that authored-only tail is dangling after refill.
        centre_region = region.buffer(
            -(VIA_R + max(0.0, edge_clearance_mm)), join_style=2)
        core = core.intersection(centre_region)
    if core.is_empty:
        return vias, 0, 0.0, 0.0
    cx = grid.x0 + (field[1] + 0.5) * grid.cell
    cy = grid.y0 + (field[0] + 0.5) * grid.cell
    parts = [p for p in getattr(core, "geoms", [core])
             if p.geom_type == "Polygon" and not p.is_empty]
    if not parts:
        return vias, 0, 0.0, 0.0
    component = max(
        parts,
        key=lambda p: (sum(p.buffer(EPS).covers(Point(v)) for v in vias),
                       -p.distance(Point(cx, cy)), p.area))
    # Put the visual lattice in one honest rectangle, not in the bounding box
    # of an L/U-shaped hook. Snapping a nominal grid into missing quadrants
    # produced a technically even but visually random constellation. Corridor
    # unions are rectilinear, so their vertex coordinate set is a compact exact
    # search space for the largest contained rectangle.
    coords = list(component.exterior.coords)[:-1]
    xs = sorted({round(x, 6) for x, _y in coords})
    ys = sorted({round(y, 6) for _x, y in coords})
    best_rect = None
    if len(xs) * len(ys) <= 1600:       # bounded for unusual imported zones
        for i, x0 in enumerate(xs[:-1]):
            for x1 in xs[i + 1:]:
                for j, y0 in enumerate(ys[:-1]):
                    for y1 in ys[j + 1:]:
                        rect = _box(x0, y0, x1, y1)
                        if (best_rect is None or rect.area > best_rect.area) \
                                and component.buffer(EPS).covers(rect):
                            best_rect = rect
    if best_rect is not None and best_rect.area > 1e-6:
        component = best_rect
    fixed = list(reserved or ())

    minx, miny, maxx, maxy = component.bounds
    def candidate_population(sample_pitch, bounds):
        bx0, by0, bx1, by1 = bounds
        ix0 = int(math.ceil((bx0 - grid.x0) / sample_pitch))
        iy0 = int(math.ceil((by0 - grid.y0) / sample_pitch))
        ix1 = int(math.floor((bx1 - grid.x0) / sample_pitch))
        iy1 = int(math.floor((by1 - grid.y0) / sample_pitch))
        positions = []
        cells = {}
        for ix in range(ix0, ix1 + 1):
            for iy in range(iy0, iy1 + 1):
                x = round(grid.x0 + ix * sample_pitch, 3)
                y = round(grid.y0 + iy * sample_pitch, 3)
                if not component.covers(Point(x, y)):
                    continue
                if (_pad_hit(pad_boxes, x, y, VIA_R + PAD_MARGIN)
                        and not (st is not None and
                                 _pofv_spot_allowed(st, (x, y)))):
                    continue
                if (st is not None and st.get("board") is not None and
                        st.get("nc") is not None and
                        not _sp.via_clear_of_foreign_tracks(
                            st["board"], st["nc"], x, y,
                            diameter_mm=2.0 * VIA_R,
                            clearance_mm=PAD_MARGIN)):
                    continue
                if any(_dist((x, y), q) < ledger_mm - EPS for q in fixed):
                    continue
                positions.append((x, y))
                cells[(ix, iy)] = (x, y)
        return positions, cells

    candidate_pitch = float(pitch_mm)
    candidates, candidate_cells = candidate_population(
        candidate_pitch, (minx, miny, maxx, maxy))
    standard_candidate_count = len(candidates)
    used_fine_phase = False
    if len(candidates) < target_count:
        # A legal POFV window can be narrower than one globally phased via
        # pitch. Retry on a bounded sub-grid around the actual transition,
        # retaining the ordinary 1.2 mm lattice as the fast/default path. The
        # later progression search still enforces ledger spacing and regular
        # rows; this only supplies the missing phase choices.
        candidate_pitch = max(0.25, min(float(pitch_mm) / 3.0,
                                        float(grid.cell) / 2.0))
        radius = max(3.0, 3.0 * float(pitch_mm))
        fine_bounds = (
            max(minx, cx - radius), max(miny, cy - radius),
            min(maxx, cx + radius), min(maxy, cy + radius))
        candidates, candidate_cells = candidate_population(
            candidate_pitch, fine_bounds)
        used_fine_phase = True

    if os.environ.get("CEC_POUR_PLAN_DEBUG"):
        print("[cec_pour_plan][dbg] via-spread field%d centre=(%.3f,%.3f) "
              "target=%d standard=%d final=%d pitch=%.3f fine=%s "
              "component=%s" % (
                  int(field[0]), cx, cy, target_count,
                  standard_candidate_count, len(candidates),
                  candidate_pitch, used_fine_phase,
                  tuple(round(value, 3) for value in component.bounds)),
              file=sys.stderr)

    if len(candidates) < target_count:
        return vias, 0, 0.0, 0.0

    width = maxx - minx
    height = maxy - miny
    aspect = width / max(height, EPS)
    n = target_count

    def _progressions(values, count):
        """All constant-pitch integer progressions on one grid axis."""
        values = sorted(set(values))
        if count == 1:
            return [(v,) for v in values]
        present = set(values)
        out = []
        for start in values:
            max_step = (values[-1] - start) // (count - 1)
            for step in range(1, max_step + 1):
                seq = tuple(start + k * step for k in range(count))
                if all(v in present for v in seq):
                    out.append(seq)
        return out

    x_indices = sorted({ix for ix, _iy in candidate_cells})
    y_indices = sorted({iy for _ix, iy in candidate_cells})
    best = None
    # Never accept a partially populated or independently displaced lattice.
    # Every supported count, including primes (1 x N), has exact factors.
    for rows in range(1, n + 1):
        if n % rows:
            continue
        cols = n // rows
        for xseq in _progressions(x_indices, cols):
            for yseq in _progressions(y_indices, rows):
                cells = [(ix, iy) for iy in yseq for ix in xseq]
                if not all(cell in candidate_cells for cell in cells):
                    continue
                chosen = [candidate_cells[cell] for cell in cells]
                # pitch_mm exceeds the default ledger, but retain an explicit
                # invariant for non-default fabrication profiles.
                if any(_dist(a, b) < ledger_mm - EPS
                       for i, a in enumerate(chosen)
                       for b in chosen[i + 1:]):
                    continue
                step_x = ((xseq[1] - xseq[0]) * candidate_pitch
                          if cols > 1 else None)
                step_y = ((yseq[1] - yseq[0]) * candidate_pitch
                          if rows > 1 else None)
                preferred_pitch = max(2.0 * pitch_mm,
                                      ledger_mm + 2.0 * VIA_R)
                used_w = (cols - 1) * (step_x or preferred_pitch) + pitch_mm
                used_h = (rows - 1) * (step_y or preferred_pitch) + pitch_mm
                lattice_aspect = used_w / max(used_h, EPS)
                aspect_cost = abs(math.log(max(
                    EPS, lattice_aspect / max(aspect, EPS))))
                active_steps = [s for s in (step_x, step_y)
                                if s is not None]
                uniformity_cost = (abs(math.log(step_x / step_y))
                                   if step_x is not None and
                                   step_y is not None else 0.0)
                pitch_cost = sum(abs(math.log(
                    max(EPS, step / preferred_pitch)))
                    for step in active_steps)
                coverage = ((used_w / max(width, EPS)) *
                            (used_h / max(height, EPS)))
                lx = sum(p[0] for p in chosen) / n
                ly = sum(p[1] for p in chosen) / n
                centre_error = math.hypot(
                    (lx - (minx + maxx) / 2.0) / max(width, EPS),
                    (ly - (miny + maxy) / 2.0) / max(height, EPS))
                # First demand a genuinely uniform moderate-pitch grid; then
                # orient and centre it in the usable rectangle. Coverage is
                # deliberately late: this is a via field, not random stitching
                # that should consume every available square millimetre.
                # Coordinates make the final tie-break deterministic across
                # Python/Shapely versions.
                score = (round(uniformity_cost, 9), round(pitch_cost, 9),
                         round(aspect_cost, 9), round(centre_error, 9),
                         -round(coverage, 9), rows, cols,
                         tuple(chosen))
                if best is None or score < best[0]:
                    best = (score, chosen)
    if best is None:
        if os.environ.get("CEC_POUR_PLAN_DEBUG"):
            print("[cec_pour_plan][dbg] via-spread no regular lattice for "
                  "target=%d candidates=%d" % (
                      target_count, len(candidates)), file=sys.stderr)
        return vias, 0, 0.0, 0.0
    chosen = sorted(best[1], key=lambda p: (p[1], p[0]))

    def _span(points):
        return max((_dist(a, b) for i, a in enumerate(points)
                    for b in points[i + 1:]), default=0.0)

    before, after = _span(vias), _span(chosen)
    original_safe = all(component.buffer(EPS).covers(Point(v)) for v in vias)
    if after <= before + 0.5 and original_safe:
        return vias, 0, before, before
    original = {(round(x, 3), round(y, 3)) for x, y in vias}
    moved = sum((round(x, 3), round(y, 3)) not in original for x, y in chosen)
    return chosen, moved, before, after


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
        la = _lay_attach_geom(st, g, lay) if native else None
        if la is not None and not la.is_empty:
            # NATIVE attach ON the layer's ACTUAL copper (anchored cells +
            # rails + manifold polys on their own layers) -- a bbox is
            # hollow and must never be the target (measured twice: a
            # merged super-group's rail-spanning bbox, AND a manifold
            # gang's multi-connector bbox whose corner sits over nothing).
            # Alternates walk the components (nearest first) + boundary
            # samples of the nearest one (a long rail offers many
            # departure points).
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
        # A guaranteed same-net patch is the broadest, most useful landing
        # geometry and must enter the bounded endpoint solve before the legacy
        # 24-point compass rings. Appending it after those rings made
        # ENDPOINT_ALT_CAP silently discard every patch-derived point on the
        # real PCIe shunts: the feature existed but never influenced the board.
        cands += _patch_spots(g, toward)
        cands += _ring_spots(g)
        ok = [pt for pt in cands if _spot_ok(st, g, pt)]
        if not ok:
            return None, shared, ()
        return ok[0], shared, tuple(ok[1:])

    pa, spot_a, alts_a = _endpoint(ga, Point(gb.cx, gb.cy))
    pb, spot_b, alts_b = _endpoint(gb, Point(ga.cx, ga.cy))
    return pa, spot_a, alts_a, pb, spot_b, alts_b


def _lay_attach_geom(st, g, lay):
    """Per-(group, layer) attach copper, cached on the group: the pre-
    connect merge's rich geometry when present (member cells + rails +
    manifold polys), else the group's OWN anchored cells on that layer.
    None when the group anchors nothing there."""
    la = g.lay_attach
    if la is None:
        la = {}
        g.lay_attach = la
    if lay not in la:
        grid = st.get("_grid")
        an = (st.get("anchors") or {}).get(lay)
        polys = []
        if grid is not None and an is not None:
            polys = [
                _box(grid.x0 + c * grid.cell, grid.y0 + r * grid.cell,
                     grid.x0 + (c + 1) * grid.cell,
                     grid.y0 + (r + 1) * grid.cell)
                for (r, c) in g.cells if an[r, c]]
        la[lay] = unary_union(polys) if polys else None
    return la[lay]


def _projection_aligned_pairs(ga, gb, lay, st, space):
    """Matched terminal points that admit a zero-bend H/V corridor.

    Independent nearest-point sampling can miss the one shared coordinate in
    two broad terminal regions. That made the real PCIe rail choose a legal
    two-bend C path even though the width-eroded terminal projections overlap.
    Work in the corridor-centre domain: shrink each terminal's usable copper by
    half the required width, intersect their X or Y projections, and return
    exact matched points. Empty/irregular terminals simply contribute nothing.
    """
    half = st["reqw"][lay] / 2.0

    def _terminal_geom(g):
        parts = []
        if g.is_manifold and lay in g.man_layers and g.attach is not None:
            parts.append(g.attach)
        elif lay in g.native:
            # This is the same native-terminal authority used by
            # _attach_point: a THT/pad group may accept a broad zone across its
            # aggregate terminal bbox even when individual annuli are disjoint.
            parts.append(_box(*g.bbox))
        if lay == "F.Cu" and g.f_zone is not None:
            parts.append(g.f_zone)
        if not parts:
            return None
        geom = unary_union(parts).buffer(-half, join_style=2)
        return None if geom.is_empty else geom

    aa, bb = _terminal_geom(ga), _terminal_geom(gb)
    if aa is None or bb is None:
        return ()
    out = []
    region = st.get("region", space.free_main.envelope)
    vertical = abs(gb.cy - ga.cy) >= abs(gb.cx - ga.cx)
    if vertical:
        lo = max(aa.bounds[0], bb.bounds[0])
        hi = min(aa.bounds[2], bb.bounds[2])
        if hi + EPS < lo:
            return ()
        coords = (0.5 * (lo + hi), lo, hi)
        extent = max(region.bounds[3] - region.bounds[1], 1.0)
        for x in coords:
            line = LineString([(x, region.bounds[1] - extent),
                               (x, region.bounds[3] + extent)])
            ia, ib = aa.intersection(line), bb.intersection(line)
            if ia.is_empty or ib.is_empty:
                continue
            pa = tuple(nearest_points(ia, Point(x, gb.cy))[0].coords[0])
            pb = tuple(nearest_points(ib, Point(x, ga.cy))[0].coords[0])
            out.append((pa, pb))
    else:
        lo = max(aa.bounds[1], bb.bounds[1])
        hi = min(aa.bounds[3], bb.bounds[3])
        if hi + EPS < lo:
            return ()
        coords = (0.5 * (lo + hi), lo, hi)
        extent = max(region.bounds[2] - region.bounds[0], 1.0)
        for y in coords:
            line = LineString([(region.bounds[0] - extent, y),
                               (region.bounds[2] + extent, y)])
            ia, ib = aa.intersection(line), bb.intersection(line)
            if ia.is_empty or ib.is_empty:
                continue
            pa = tuple(nearest_points(ia, Point(gb.cx, y))[0].coords[0])
            pb = tuple(nearest_points(ib, Point(ga.cx, y))[0].coords[0])
            out.append((pa, pb))
    unique = []
    seen = set()
    for a, b in out:
        key = tuple(round(v, 6) for p in (a, b) for v in p)
        if key not in seen:
            seen.add(key)
            unique.append((a, b))
    return tuple(unique)


def _path_with_alternates(space, pa, alts_a, pb, alts_b,
                          aligned_pairs=()):
    """Jointly select terminal endpoints and the rectilinear path.

    The former first-success policy considered alternates only after the
    default endpoint failed. A merely *routable* default could therefore leave
    two tiny terminal doglegs even when a legal patch/manifold landing removed
    them. Evaluate a bounded set of alternatives and minimize bends first,
    then path length and endpoint displacement. This is the same professional
    trade: meaningful topology beats a marginally shorter but fussy route.
    """
    if pa is None or pb is None:
        return None, None
    aa = [pa] + list(alts_a[:ENDPOINT_ALT_CAP - 1])
    bb = [pb] + list(alts_b[:ENDPOINT_ALT_CAP - 1])
    seen = set()
    attempts = []

    def _try(a, b):
        key = (round(a[0], 6), round(a[1], 6),
               round(b[0], 6), round(b[1], 6))
        if key in seen:
            return
        seen.add(key)
        pts, bends = _find_path(space, a, b)
        if pts is None:
            return
        length = sum(_dist(x, y) for x, y in zip(pts, pts[1:]))
        displacement = _dist(pa, a) + _dist(pb, b)
        attempts.append((bends, length, displacement, pts, a, b))

    _try(pa, pb)
    for a, b in aligned_pairs:
        _try(a, b)
    for a in aa[1:]:
        _try(a, pb)
    for b in bb[1:]:
        _try(pa, b)
    # Paired alternates matter when both terminal neighborhoods are locally
    # constrained. Bound the cross product to the most promising one-sided
    # endpoints so dense manifolds do not turn path planning quadratic.
    ranked_a = sorted({row[4] for row in attempts},
                      key=lambda a: _dist(pa, a))[:ENDPOINT_CROSS_BEAM]
    ranked_b = sorted({row[5] for row in attempts},
                      key=lambda b: _dist(pb, b))[:ENDPOINT_CROSS_BEAM]
    if not ranked_a:
        ranked_a = aa[:ENDPOINT_CROSS_BEAM]
    if not ranked_b:
        ranked_b = bb[:ENDPOINT_CROSS_BEAM]
    for a in ranked_a:
        for b in ranked_b:
            _try(a, b)
    if not attempts:
        return None, None
    # One bend is worth 1.5 mm in the underlying search. Preserve that scale
    # while using displacement only as a gentle preference for the nominal
    # landing; it must not keep a visibly worse topology.
    best = min(attempts,
               key=lambda row: (row[0], row[1] + 0.05 * row[2], row[2]))
    return best[3], best[0]


NECK_MAX_MM = 4.8        # contiguous sub-width (W_NECK) run floor -- runs
#                          under this are always acceptable collar
#                          crossings (measured ~2-3mm at the J3/TB belts;
#                          several per corridor are fine). Above it, the
#                          RATIO rule judges: the neck must be a MINORITY
#                          of its corridor (a crossing, never the corridor
#                          itself -- measured degenerate case: an In2
#                          "corridor" that was one 9.7mm 0.8mm spine on a
#                          10mm run, passing the width invariant for a 20A
#                          rail; a long J3-belt traverse on a 25mm B
#                          corridor stays legal, and rejecting it only
#                          demotes the net to 0.2mm FR tracks -- strictly
#                          worse thermally).


def _cand_from_path(cor, st, lay, pts, bends, taper, space=None):
    """Candidate from a found centerline. When the path crosses the neck
    sub-space (anchor-approach passage), the realization splits: full-width
    copper clipped to where full width is legal + a W_NECK spine along the
    whole centerline (true-clearance legal by construction of the search).
    The spine is the terminal-zone piece (raster-exempt); the main piece
    stays raster-verified; the width invariant is then honestly W_NECK.
    Returns None when the sub-width portion exceeds NECK_MAX_MM (the neck
    doctrine's length bound -- the caller diags 'neck-too-long')."""
    width_eff = taper or st["reqw"][lay]
    poly = _capsule(pts, width_eff / 2.0)
    length = sum(_dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
    cand = {"layer": lay, "pts": pts, "poly": poly, "bends": bends,
            "length": length, "taper": taper, "main": poly, "spine": None}
    space = space or st["spaces"].get(lay)
    if space is not None and space.neck is not None:
        line = LineString(pts)
        if not space.free_main.covers(line):
            out_part = line.difference(space.free_main)
            longest = max((seg.length for seg in
                           getattr(out_part, "geoms", [out_part])
                           if not seg.is_empty), default=0.0)
            if longest > max(NECK_MAX_MM, 0.5 * line.length):
                return None
            spine = _capsule(pts, W_NECK / 2.0)
            # Recover the full-width portion by clipping the requested
            # capsule against the original legal copper domain.  Expanding
            # ``free_main`` back outward is not its inverse: it closes small
            # forbidden via/pad holes and can silently recreate copper over a
            # reserved access primitive.
            clip = space.copper_legal.buffer(-EPS, join_style=2)
            main_piece = poly.intersection(clip)
            cand["main"] = main_piece
            cand["spine"] = spine
            cand["poly"] = unary_union([main_piece, spine])
    return cand


def _make_candidates(cor, st, grid):
    """Per-layer geometry candidates for one corridor."""
    ga, gb = cor.ga, cor.gb
    bundle = st.get("bundle")
    if bundle:
        label = "+".join(bundle["layers"])
        parts = {}
        spots = {}
        for lay in bundle["layers"]:
            space = bundle["spaces"][lay]
            if space._prep is None:
                cor.diag[label] = "%s-width-infeasible(%.1fmm)" % (
                    lay, st["reqw"][lay])
                return
            pa, spot_a, alts_a, pb, spot_b, alts_b = _endpoints_for_layer(
                cor, st, lay, space)
            pts, bends = _path_with_alternates(
                space, pa, alts_a, pb, alts_b,
                _projection_aligned_pairs(ga, gb, lay, st, space))
            if pts is None:
                relief_mode = st.get("relief_diagnostics", True)
                relief = (_corridor_relief_evidence(
                    cor, st, lay, space,
                    owner_cap=(6 if relief_mode == "light" else 18),
                    pair_cap=(0 if relief_mode == "light" else 10),
                    max_cardinality=(1 if relief_mode == "light" else 4),
                    immovable_owners=st.get(
                        "fixed_authority_refs") or ())
                    if relief_mode else {
                        "layer": lay, "relief_sets": [],
                        "skipped": "bounded_candidate_sweep"})
                st.setdefault("bottlenecks", {})[
                    "%s:%s->%s" % (lay, ga.gid, gb.gid)] = relief
                if os.environ.get("CEC_POUR_PLAN_DEBUG"):
                    print(
                        "[cec_pour_plan][dbg] bundle %s %s->%s %s "
                        "pa=%s ok=%s alts=%d pb=%s ok=%s alts=%d comp=%s"
                        % (cor.net, ga.gid, gb.gid, lay,
                           pa, bool(pa is not None and space.ok_pt(pa)),
                           len(alts_a), pb,
                           bool(pb is not None and space.ok_pt(pb)),
                           len(alts_b),
                           _space_component_diag(space, pa, pb)
                           if pa is not None and pb is not None else None),
                        file=sys.stderr)
                cor.diag[label] = "%s:%s" % (lay,
                    "pa-spot-padlocked" if pa is None else
                    "pb-spot-padlocked" if pb is None else
                    "pa-blocked" if not space.ok_pt(pa) else
                    "pb-blocked" if not space.ok_pt(pb) else "no-path")
                return
            part = _cand_from_path(
                cor, st, lay, pts, bends, None, space=space)
            if part is None:
                cor.diag[label] = "%s:bundle-neck-too-long" % lay
                return
            parts[lay] = part
            spots[lay] = (spot_a, spot_b, pts)
        primary = bundle["primary_layer"]
        cand = dict(parts[primary])
        cand["bundle_layers"] = tuple(bundle["layers"])
        cand["bundle_parts"] = parts
        cand["bundle_fraction"] = float(bundle["per_layer_fraction"])
        cand["bends"] = sum(part["bends"] for part in parts.values())
        cand["length"] = sum(part["length"] for part in parts.values())
        cand["poly"] = unary_union(
            [part["poly"] for part in parts.values()])
        # Cross-layer terminal fields follow the primary-layer route. Bind a
        # shared group's canonical field spot to that route, never whichever
        # participating layer happened to be iterated first.
        spot_a, spot_b, primary_pts = spots[primary]
        if spot_a and ga.spot is None:
            ga.spot = tuple(primary_pts[0])
        if spot_b and gb.spot is None:
            gb.spot = tuple(primary_pts[-1])
        cor.cands.append(cand)
        cor.diag.pop(label, None)
        return
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
        pts, bends = _path_with_alternates(
            space, pa, alts_a, pb, alts_b,
            _projection_aligned_pairs(ga, gb, lay, st, space))
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
        cand = _cand_from_path(cor, st, lay, pts, bends, taper)
        if cand is None:
            cor.diag[lay] = "neck-too-long"
            continue
        cor.diag.pop(lay, None)
        # fix the canonical spot on first success (all later corridors
        # incident to the group MUST land at the same point -- the one
        # terminal via field is the only cross-layer bridge there)
        if spot_a and ga.spot is None:
            ga.spot = tuple(pts[0])
        if spot_b and gb.spot is None:
            gb.spot = tuple(pts[-1])
        cor.cands.append(cand)
    _pref = layer_pref()
    cor.cands.sort(key=lambda c: _pref[c["layer"]])


def _assigned_foreign(nets, net, lay):
    """Every other net's standing copper on *lay*: picked corridors, split
    legs, and terminal-zone geometry is NOT included (landings live inside
    pad fields; corridors are the contested territory)."""
    out = []
    for onet, ost in nets.items():
        if onet == net:
            continue
        for oc in ost.get("corridors", ()):
            if oc.pick and lay in _candidate_layers(oc.pick):
                out.append(_candidate_poly(oc.pick, lay))
            if oc.split and oc.split["lay2"] == lay:
                out.append(oc.split["poly2"])
    return out


def _candidate_conflicts(a, b, clearance_mm=0.3):
    """Whether two candidate corridors compete for the same copper space."""
    for lay in set(_candidate_layers(a)) & set(_candidate_layers(b)):
        pa = _candidate_poly(a, lay).buffer(clearance_mm)
        pb = _candidate_poly(b, lay)
        if pa.intersects(pb) and pa.intersection(pb).area > 0.01:
            return True
    return False


def _bundle_candidate_avoiding(cor, st, avoided):
    """Build one complete bundle while treating *avoided* as future copper."""
    bundle = st.get("bundle")
    if not bundle:
        return None
    parts = {}
    spots = {}
    for lay in bundle["layers"]:
        obstacles = list((st.get("bundle_obst") or st["obst"])[lay])
        if lay in _candidate_layers(avoided):
            obstacles.append(_candidate_poly(avoided, lay).buffer(0.35))
        if st.get("gap_geom") is not None:
            obstacles.append(st["gap_geom"])
        space = _LayerSpace(
            st["region"], obstacles, st["reqw"][lay] / 2.0,
            f_allow=None, approach=st.get("approach"),
            half_neck=W_NECK / 2.0, neck_unguard=0.0)
        pa, spot_a, alts_a, pb, spot_b, alts_b = _endpoints_for_layer(
            cor, st, lay, space)
        pts, bends = _path_with_alternates(
            space, pa, alts_a, pb, alts_b,
            _projection_aligned_pairs(cor.ga, cor.gb, lay, st, space))
        if pts is None:
            return None
        part = _cand_from_path(
            cor, st, lay, pts, bends, None, space=space)
        if part is None:
            return None
        parts[lay] = part
        spots[lay] = (spot_a, spot_b, pts)
    primary = bundle["primary_layer"]
    cand = dict(parts[primary])
    cand["bundle_layers"] = tuple(bundle["layers"])
    cand["bundle_parts"] = parts
    cand["bundle_fraction"] = float(bundle["per_layer_fraction"])
    cand["bends"] = sum(part["bends"] for part in parts.values())
    cand["length"] = sum(part["length"] for part in parts.values())
    cand["poly"] = unary_union(
        [part["poly"] for part in parts.values()])
    cand["future_avoidance"] = {
        "net": avoided.get("net"),
        "layers": list(_candidate_layers(avoided)),
    }
    # Spots are evidence carried by the candidate. They become canonical only
    # after assignment; mutating a group here would let a losing alternative
    # constrain every later search.
    cand["bundle_spots"] = spots
    return cand


def _expand_future_conflict_alternatives(nets, order, cap_per_corridor=4):
    """Pre-route around predicted corridor conflicts before assignment.

    A single shortest path per commodity is not a multi-commodity solve: two
    individually optimal routes can overlap even though moving either one
    makes the set feasible.  For each predicted conflict, generate a bounded
    alternative for both directions with the peer treated as future reserved
    copper. Branch-and-bound then chooses the globally compatible combination.
    """
    corridors = [cor for net in order for cor in
                 (nets.get(net) or {}).get("corridors", ())
                 if cor.cands]
    added = {id(cor): 0 for cor in corridors}
    for index, left in enumerate(corridors):
        for right in corridors[index + 1:]:
            conflicts = [(a, b) for a in left.cands for b in right.cands
                         if _candidate_conflicts(a, b)]
            if left.net == right.net or not conflicts:
                continue
            if os.environ.get("CEC_POUR_PLAN_DEBUG"):
                overlap = {}
                a, b = conflicts[0]
                for lay in set(_candidate_layers(a)) & \
                        set(_candidate_layers(b)):
                    area = _candidate_poly(a, lay).buffer(0.3).intersection(
                        _candidate_poly(b, lay)).area
                    if area > 0.01:
                        overlap[lay] = round(area, 3)
                print("[cec_pour_plan][dbg] future conflict %s vs %s "
                      "overlap_mm2=%s" % (left.net, right.net, overlap),
                      file=sys.stderr)
            for target, peer in ((left, right), (right, left)):
                st = nets[target.net]
                if not st.get("bundle") or \
                        added[id(target)] >= cap_per_corridor:
                    continue
                # Avoid the peer's best static candidate. Later pairwise
                # conflicts can add another candidate, but total growth stays
                # fixed by cap_per_corridor.
                alt = _bundle_candidate_avoiding(
                    target, st, peer.cands[0])
                if os.environ.get("CEC_POUR_PLAN_DEBUG"):
                    print("[cec_pour_plan][dbg] future alternative %s "
                          "avoiding %s: %s" % (
                              target.net, peer.net,
                              "found" if alt is not None else "no-path"),
                          file=sys.stderr)
                if alt is None or any(
                        all(_candidate_poly(alt, lay).equals_exact(
                            _candidate_poly(old, lay), 1e-6)
                            for lay in _candidate_layers(alt))
                        for old in target.cands
                        if set(_candidate_layers(old)) ==
                           set(_candidate_layers(alt))):
                    continue
                target.cands.append(alt)
                added[id(target)] += 1
    for net in order:
        st = nets.get(net)
        if not st:
            continue
        count = sum(added.get(id(cor), 0) for cor in st["corridors"])
        if count:
            st["notes"].append(
                "generated %d future-conflict alternative(s)" % count)
    return sum(added.values())


def _replan_blocked(cor, st, nets, grid):
    """Task step 5's re-plan loop, conflict flavor: a corridor whose static
    candidates all clash with other nets' assigned corridors re-plans its
    PATH with those corridors as obstacles (clearance-buffered) -- a
    same-layer geometric dodge, preferred over a crossing split (no via
    field). Returns True and sets cor.pick on success."""
    # A redundant current bundle is an all-layers-or-none contract. Re-plan
    # every participating layer independently around the copper already
    # assigned on that layer, then accept only the complete bundle. This keeps
    # the capacity contract while avoiding the old false requirement that
    # both outer-layer conductors share one centerline.
    bundle = st.get("bundle")
    if bundle:
        parts = {}
        spots = {}
        label = "+".join(bundle["layers"])
        for lay in bundle["layers"]:
            assigned = _assigned_foreign(nets, cor.net, lay)
            obstacles = list((st.get("bundle_obst") or st["obst"])[lay])
            obstacles.extend(p.buffer(0.35) for p in assigned)
            if st.get("gap_geom") is not None:
                obstacles.append(st["gap_geom"])
            space2 = _LayerSpace(
                st["region"], obstacles, st["reqw"][lay] / 2.0,
                f_allow=None, approach=st.get("approach"),
                half_neck=W_NECK / 2.0, neck_unguard=0.0)
            pa, spot_a, alts_a, pb, spot_b, alts_b = _endpoints_for_layer(
                cor, st, lay, space2)
            pts, bends = _path_with_alternates(
                space2, pa, alts_a, pb, alts_b,
                _projection_aligned_pairs(
                    cor.ga, cor.gb, lay, st, space2))
            if pts is None:
                cor.diag[label] = "%s:reserved-copper-no-path" % lay
                return False
            part = _cand_from_path(
                cor, st, lay, pts, bends, None, space=space2)
            if part is None:
                cor.diag[label] = "%s:reserved-copper-neck-too-long" % lay
                return False
            parts[lay] = part
            spots[lay] = (spot_a, spot_b, pts)
        primary = bundle["primary_layer"]
        cand = dict(parts[primary])
        cand["bundle_layers"] = tuple(bundle["layers"])
        cand["bundle_parts"] = parts
        cand["bundle_fraction"] = float(bundle["per_layer_fraction"])
        cand["bends"] = sum(part["bends"] for part in parts.values())
        cand["length"] = sum(part["length"] for part in parts.values())
        cand["poly"] = unary_union(
            [part["poly"] for part in parts.values()])
        spot_a, spot_b, primary_pts = spots[primary]
        if spot_a and cor.ga.spot is None:
            cor.ga.spot = tuple(primary_pts[0])
        if spot_b and cor.gb.spot is None:
            cor.gb.spot = tuple(primary_pts[-1])
        cor.pick = cand
        cor.diag.pop(label, None)
        return True
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
        pts, bends = _path_with_alternates(
            space2, pa, alts_a, pb, alts_b,
            _projection_aligned_pairs(
                cor.ga, cor.gb, lay, st, space2))
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
        cand = _cand_from_path(cor, st, lay, pts, bends, None,
                               space=space2)
        if cand is None:
            continue                       # neck-too-long on the dodge
        if spot_a and cor.ga.spot is None:
            cor.ga.spot = tuple(pts[0])
        if spot_b and cor.gb.spot is None:
            cor.gb.spot = tuple(pts[-1])
        cor.pick = cand
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
    # Closure is lexicographically dominant. The former scalar objective gave
    # an unassigned corridor a fixed 4*VIA_FIELD_COST penalty (12), so a long
    # but valid high-current bundle could cost more and the exact solver would
    # deliberately leave it open. First maximize assigned corridors; only
    # then minimize vias/bends/layer preference/length.
    best = {"assigned": -1, "cost": float("inf"), "picks": None}
    nodes = [0]

    def _conflict(cand, i, picks):
        # clearance-buffered: two foreign pours may never TOUCH (zone-to-
        # zone clearance is real DRC), so the test runs at +0.3mm standoff
        lays = set(_candidate_layers(cand))
        for j in range(i):
            cj = picks[j]
            if cj is None or cors[j].net == cors[i].net:
                continue
            for lay in lays & set(_candidate_layers(cj)):
                p = _candidate_poly(cand, lay).buffer(0.3)
                q = _candidate_poly(cj, lay)
                if p.intersects(q) and p.intersection(q).area > 0.01:
                    return True
        return False

    _LP = layer_pref()

    def _cand_cost(cor, cand, fielded):
        cost = (sum(_LP[lay] for lay in _candidate_layers(cand))
                + BEND_COST * cand["bends"]
                + LEN_COST * cand["length"])
        for g in (cor.ga, cor.gb):
            if _field_needed(g, cand["layer"]) and id(g) not in fielded:
                cost += VIA_FIELD_COST
        return cost

    def dfs(i, assigned, cost, picks, fielded):
        nodes[0] += 1
        if nodes[0] > BB_NODE_CAP:
            if nodes[0] == BB_NODE_CAP + 1:
                print("[cec_pour_plan] layer assignment: node budget hit -- "
                      "best-so-far kept (bounded exactness)", file=sys.stderr)
            return
        remaining = ncor - i
        if assigned + remaining < best["assigned"]:
            return
        if assigned + remaining == best["assigned"] and \
                cost >= best["cost"]:
            return
        if i == ncor:
            if (assigned > best["assigned"] or
                    (assigned == best["assigned"] and
                     cost < best["cost"])):
                best["assigned"] = assigned
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
            dfs(i + 1, assigned + 1, cost + add, picks, fielded)
            fielded -= newf
            picks.pop()
        # allow "unassigned" (phase C split repair picks it up) at a stiff
        # price so a single blocked corridor cannot sink the whole net set
        picks.append(None)
        dfs(i + 1, assigned, cost + 4.0 * VIA_FIELD_COST, picks,
            fielded)
        picks.pop()
        return any_c

    dfs(0, 0, 0.0, [], set())
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
    if st.get("bundle"):
        return False
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
                    and (not _pad_hit(st.get("pad_boxes", ()), sp_pt.x,
                                      sp_pt.y, VIA_R + PAD_MARGIN)
                         or _pofv_spot_allowed(st, (sp_pt.x, sp_pt.y))):
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


def _attach_connectivity(net, st, grid, masks, land_polys, field_vias,
                         extra_lines=()):
    """Raster attach-connectivity verdict (verification 3, factored
    2026-07-25 so the region realization shares it verbatim): per layer,
    anchors | realized masks | own pours | terminal-zone landings, layers
    fused at ACTUAL via positions (+1-cell tolerance) and THT anchor cells;
    every served group must sit in ONE component. Returns (stranded_gids,
    n_roots).

    *extra_lines*: [(layer, pts)] CENTERLINES stamped by line-walk -- a
    W_NECK spine is thinner than a cell, so _stamp_poly's conservative
    cell-center containment can miss it entirely (measured: a planned
    corridor whose neck leg vanished from the raster and split the net in
    two). Connectivity-only over-stamp; clearance never reads these."""
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
    for (llay, lpts) in extra_lines:
        om = own_masks.setdefault(llay,
                                  np.zeros((grid.ny, grid.nx), bool))
        last = None
        for i in range(len(lpts) - 1):
            (ax, ay), (bx, by) = lpts[i], lpts[i + 1]
            n = max(1, int(_dist(lpts[i], lpts[i + 1]) / (grid.cell * 0.4)))
            for k in range(n + 1):
                f = k / n
                r, c = _cell_of(grid, ax + f * (bx - ax), ay + f * (by - ay))
                if last is not None and r != last[0] and c != last[1]:
                    # 4-CONNECTED walk: a diagonal step stamps its elbow,
                    # or ndimage's 4-neighborhood label splits the strand
                    # (measured: a spine spanning two components)
                    om[last[0], c] = True
                om[r, c] = True
                last = (r, c)
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
    if os.environ.get("CEC_POUR_PLAN_DEBUG") and (stranded or len(roots) > 1):
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
        for g in st["served"]:
            tags = sorted({(lay, int(comp[lay][r, c])) for lay in comp
                           for (r, c) in g.cells if comp[lay][r, c]})
            print("[cec_pour_plan][dbg]   G%s tags=%s"
                  % (g.gid, [(t, find(t)) for t in tags[:8]]),
                  file=sys.stderr)
        for src, mm in (("mask", masks), ("own", own_masks)):
            for lay, m in mm.items():
                vals = sorted(int(v) for v in
                              np.unique(comp[lay][m & (comp[lay] > 0)]))
                print("[cec_pour_plan][dbg]   %s[%s] cells=%d comps=%s "
                      "roots=%s"
                      % (src, lay, int(m.sum()), vals[:6],
                         sorted({str(find((lay, v)))
                                 for v in vals})[:6]), file=sys.stderr)
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
    for lay in [l for l in region_layer_order() if l in st["layers"]]:
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
                                 st.get("pad_boxes", ()), placed, st=st)
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
                g2 = _emit_rectilinear(g2)
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
        # SANCTIONED-EXCEPTION REPORT (owner ruling 2026-07-25): on a board whose
        # policy demotes an inner layer, landing power copper there anyway is
        # allowed but must never be silent -- it means the preferred outers could
        # not carry this rail, which is exactly the evidence the ruling wants to
        # see. Every earlier layer in the order failed with a reason in `notes`.
        if lay in demoted_layers():
            ent["policy_exception"] = lay
            print("[cec_pour_plan] %s: region landed on the DEMOTED layer %s -- "
                  "the preferred layer(s) %s could not carry it (%s)"
                  % (net, lay, ", ".join(l for l in region_layer_order()
                                         if l != lay),
                     "; ".join(notes[-2:]) or "no reason recorded"),
                  file=sys.stderr, flush=True)
        return ent, dicts, vias
    e = _fail_entry("region plan failed on every layer (%s)"
                    % "; ".join(notes[-4:]))
    e["planner"] = "territory-region"
    return e, [], []


def _component_physical_seeded(component, layer, st, fields, field_vias):
    """True when a same-layer copper component reaches real connectivity."""
    seeded_by_terminal = any(
        layer in group.native and group.attach is not None
        and component.buffer(EPS).intersects(group.attach)
        for group in st.get("served", ()))
    seeded_by_owned_copper = any(
        own_layer == layer and
        component.buffer(EPS).intersects(own_poly)
        for own_layer, own_poly in st.get("own_pours", ()))
    seeded_by_via = any(
        layer in (field[2], field[3]) and
        component.buffer(EPS).covers(Point(x, y))
        for field, vs in zip(fields, field_vias)
        for x, y in vs)
    return bool(seeded_by_terminal or seeded_by_owned_copper or seeded_by_via)


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
                               "diag": dict(u.diag),
                               "relief": dict(
                                   st.get("bottlenecks") or {})}}, [], []

    for attempt in (0, 1):
        # --- gather realized geometry ---
        lay_polys = {}                      # layer -> [shapely] (verified)
        land_polys = {}                     # layer -> [shapely] terminal-zone
        width_checks = []                   # (poly, width_mm, what)
        fields = []                         # bridge tuples + kind tag
        field_via_needs = []                # ampacity count, same index
        field_via_minima = []               # hard count, excludes spare
        fielded = {}                        # id(group) -> True
        bends = 0
        pending_land = []                   # (group, spot, field_idx, cells)
        spine_lines = []                    # (layer, pts) -- line-stamped
        neck_corridors = 0
        for cor in st["corridors"]:
            pk = cor.pick
            occupied_layers = _candidate_layers(pk)
            has_neck = False
            for lay in occupied_layers:
                part = (pk.get("bundle_parts") or {}).get(lay, pk)
                if part.get("spine") is not None:
                    # neck decomposition: main piece raster-verified, spine =
                    # terminal-zone (true-clearance legal by search
                    # construction). Parallel bundles may take different
                    # legal centerlines, so realize the part for this layer.
                    lay_polys.setdefault(lay, []).append(part["main"])
                    land_polys.setdefault(lay, []).append(part["spine"])
                    spine_lines.append((lay, part["pts"]))
                    width_checks.append((part["spine"], W_NECK,
                                         "neck spine %s->%s on %s"
                                         % (cor.ga.gid, cor.gb.gid, lay)))
                    has_neck = True
                else:
                    lay_polys.setdefault(lay, []).append(part["poly"])
                    width_checks.append((part["poly"], st["reqw"][lay],
                                         "corridor %s->%s on %s"
                                         % (cor.ga.gid, cor.gb.gid, lay)))
                if part.get("taper"):
                    cor.tapered = True
            if has_neck:
                neck_corridors += 1
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
                    # LOCAL-CELLS RULE (2026-07-25, live-wave measured: a
                    # pre-connected super-group has MIXED natives, so the
                    # old `native == {F}` test skipped its landing and the
                    # attach verify split in two; and its union bbox spans
                    # the rails, so a bbox landing would be a giant blob):
                    # the landing embeds the group's F-anchored cells NEAR
                    # the attach point only -- none nearby = true THT
                    # attach, barrels fuse, no landing.
                    if "F.Cu" in g.native:
                        p = gpts[0] if at_start else gpts[-1]
                        fa = st["anchors"].get("F.Cu")
                        loc = [(r, c) for (r, c) in g.cells
                               if fa is not None and fa[r, c] and _dist(
                                   (grid.x0 + (c + 0.5) * grid.cell,
                                    grid.y0 + (r + 0.5) * grid.cell),
                                   p) <= 3.2]
                        if loc:
                            pending_land.append((g, p, len(fields) - 1,
                                                 loc))

        # --- via placement: assembly-class pad exclusion + slide reseat
        # (via-in-pad ruling, owner 2026-07-25) -- placed BEFORE the
        # landings so each landing embeds its field's ACTUAL vias ---
        placed = list(existing_vias)
        field_vias = []
        via_reseated = 0
        pofv_seeded_fields = 0
        landing_group_by_field = {
            field_idx: group
            for group, _spot, field_idx, _cells in pending_land}
        for field_index, f in enumerate(fields):
            half_w = max(st["reqw"].get(f[2], 1.2),
                         st["reqw"].get(f[3], 1.2)) / 2.0
            n_needed = _field_via_need(st, f, half_w)
            n_minimum = _field_via_minimum(st, f)
            vs, rs = _field_vias(f, half_w, grid, st.get("pad_boxes", ()),
                                 placed, st=st, n_needed=n_needed)
            field_via_needs.append(n_needed)
            field_via_minima.append(n_minimum)
            landing_group = landing_group_by_field.get(field_index)
            if landing_group is not None and landing_group.f_zone is not None:
                # A reseated field may fan away from its canonical center. All
                # of its F-side barrels must remain inside the sanctioned
                # shunt landing patch; checking only the center allowed one
                # outer via to become a KiCad `via_dangling` item.
                via_core = landing_group.f_zone.buffer(-VIA_R)
                vs = [(x, y) for x, y in vs
                      if not via_core.is_empty
                      and via_core.covers(Point(x, y))]
            if not vs and f[6] == "terminal" and landing_group is not None:
                # The ordinary reseat may find a barrel near the canonical
                # field and then lose it at the exact F-side landing check.
                # A declared-profile POFV does not need that auxiliary F-side
                # patch: its complete outer land is the same-net SMD pad.
                # Restrict the fallback to this terminal group so a remote
                # same-net pad can never become an accidental escape portal.
                vs = _field_terminal_pofv_seed(
                    net, f, st, grid, placed,
                    allowed_refs=getattr(landing_group, "refs", ()))
                if vs:
                    pofv_seeded_fields += 1
                    rs += 1
                    st["notes"].append(
                        "field %d terminal escape seeded by declared-profile "
                        "same-net POFV" % field_index)
            field_vias.append(vs)
            via_reseated += rs
            placed.extend(vs)
            if vs:
                # A field's outer slots (and especially a slid via) can sit
                # past the corridor half-width: a
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
        if os.environ.get("CEC_POUR_PLAN_DEBUG"):
            for k, cor in enumerate(st["corridors"]):
                pk = cor.pick
                print("[cec_pour_plan][dbg] %s cor%d %s->%s pick=%s pts=%s"
                      "%s%s" % (net, k, cor.ga.gid, cor.gb.gid,
                                pk and "+".join(_candidate_layers(pk)),
                                pk and [tuple(round(v, 1) for v in q)
                                        for q in (pk["pts"][0],
                                                  pk["pts"][-1])],
                                " taper=%.2f" % pk["taper"]
                                if pk and pk.get("taper") else "",
                                " NECK" if pk and pk.get("spine") is not None
                                else ""), file=sys.stderr)
            for i, f in enumerate(fields):
                print("[cec_pour_plan][dbg] %s field%d %s %s->%s at cell "
                      "(%d,%d) vias=%d" % (net, i, f[6], f[2], f[3], f[0],
                                           f[1], len(field_vias[i])),
                      file=sys.stderr)
        vias = [
            {"net": net, "x_mm": x, "y_mm": y,
             "role": ("transition_bridge"
                      if fields[field_index][6] == "crossing"
                      else "current_share_stitch"),
             "field_kind": fields[field_index][6],
             "field_index": field_index,
             "distribution": ("compact"
                              if fields[field_index][6] == "crossing"
                              else "uniform_overlap")}
            for field_index, vs in enumerate(field_vias)
            for slot, (x, y) in enumerate(vs)]
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
        for (g, p, fi, loc) in pending_land:
            # local F cells near the attach, never the (possibly rail-
            # spanning) union bbox
            half_c = grid.cell / 2.0
            cx = [grid.x0 + (c + 0.5) * grid.cell for (_r, c) in loc]
            cy = [grid.y0 + (r + 0.5) * grid.cell for (r, _c) in loc]
            x0, y0 = min(cx) - half_c, min(cy) - half_c
            x1, y1 = max(cx) + half_c, max(cy) + half_c
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

        # A via is useful only if its complete barrel is embedded in same-net
        # copper on both transition layers. Geometric field generation can
        # place an outer slot just beyond a clipped landing/corridor edge; KiCad
        # then correctly reports `via_dangling` even though the field centre is
        # sound. Prune only that slot, never the field as a whole, and let the
        # attach-connectivity proof reject the plan if no bridge remains.
        own_by_layer = {}
        for own_layer, own_poly in st.get("own_pours", ()):
            own_by_layer.setdefault(own_layer, []).append(own_poly)
        for field_index, field in enumerate(fields):
            safe = []
            for x, y in field_vias[field_index]:
                barrel = Point(x, y).buffer(max(0.01, VIA_R - 0.03))
                if all(any(poly.buffer(0.01).covers(barrel)
                           for poly in (list(lay_polys.get(layer, ()))
                                        + list(land_polys.get(layer, ()))
                                        + list(own_by_layer.get(layer, ()))))
                       for layer in (field[2], field[3])):
                    safe.append((x, y))
            field_vias[field_index] = safe

        # A compact array is required at the actual transition, but packing
        # every barrel into that one square wastes their current-sharing and
        # thermal-spreading value wherever the same net has broad copper on
        # both layers. Keep two local transition barrels, then distribute the
        # remaining already-budgeted barrels across the connected overlap.
        # No extra drills are introduced, and no via enters a placement hook:
        # both layer polygons must already cover its full barrel.
        spread_moved = 0
        spread_fields = 0
        spread_before = []
        spread_after = []
        spread_reserved = list(existing_vias)
        for field_index, field in enumerate(fields):
            layer_geom = []
            for layer in (field[2], field[3]):
                parts = (list(lay_polys.get(layer, ()))
                         + list(land_polys.get(layer, ()))
                         + list(own_by_layer.get(layer, ())))
                layer_geom.append(unary_union(parts) if parts else None)
            overlap = (layer_geom[0].intersection(layer_geom[1])
                       if all(g is not None and not g.is_empty
                              for g in layer_geom) else None)
            old = field_vias[field_index]
            new, moved, before, after = _spread_field_over_overlap(
                field, old, overlap, grid, st.get("pad_boxes", ()),
                spread_reserved, st=st, region=st.get("region"))
            if len(new) < field_via_needs[field_index]:
                new, moved, before, after = _spread_field_over_overlap(
                    field, old, overlap, grid, st.get("pad_boxes", ()),
                    spread_reserved, st=st, region=st.get("region"),
                    target_count=field_via_needs[field_index])
            field_vias[field_index] = new
            spread_reserved.extend(new)
            if moved:
                spread_fields += 1
                spread_moved += moved
                spread_before.append(before)
                spread_after.append(after)
        incomplete_fields = [
            (index, fields[index][6], len(field_vias[index]), minimum,
             field_via_needs[index])
            for index, minimum in enumerate(field_via_minima)
            if len(field_vias[index]) < minimum]
        if incomplete_fields:
            field_failures = []
            fixed_refs = set(st.get("fixed_authority_refs") or ())
            for index, kind, placed_count, minimum, desired in \
                    incomplete_fields:
                field = fields[index]
                centre = (
                    grid.x0 + (field[1] + 0.5) * grid.cell,
                    grid.y0 + (field[0] + 0.5) * grid.cell)
                pad_rows = []
                for pad in st.get("pad_box_records") or ():
                    x0, y0, x1, y1 = pad["box"]
                    dx = max(x0 - centre[0], centre[0] - x1, 0.0)
                    dy = max(y0 - centre[1], centre[1] - y1, 0.0)
                    distance = math.hypot(dx, dy)
                    pad_rows.append({
                        "owner": pad.get("owner"),
                        "pad": pad.get("pad"),
                        "net": pad.get("net"),
                        "distance_mm": round(distance, 6),
                        "fixed": pad.get("owner") in fixed_refs,
                        "box": [round(float(value), 6)
                                for value in pad["box"]],
                    })
                pad_rows.sort(key=lambda row: (
                    row["distance_mm"], row.get("owner") or "",
                    row.get("pad") or ""))
                nearest_group = min(
                    st.get("served") or (),
                    key=lambda group: math.hypot(
                        float(group.cx) - centre[0],
                        float(group.cy) - centre[1]),
                    default=None)
                field_failures.append({
                    "field_index": index, "field_kind": kind,
                    "centre_mm": [round(centre[0], 6),
                                  round(centre[1], 6)],
                    "layers": [field[2], field[3]],
                    "placed": placed_count, "minimum": minimum,
                    "desired": desired,
                    "terminal_refs": sorted(
                        getattr(nearest_group, "refs", ()) or ()),
                    "nearest_pad_obstacles": pad_rows[:12],
                })
            return _fail_entry(
                "required cross-layer via field incomplete: %s" %
                ", ".join("field %d (%s) %d/%d minimum (%d desired)" % row
                          for row in incomplete_fields),
                bottleneck={
                    "kind": "via_field_access",
                    "net": net,
                    "fields": field_failures,
                    "relief": dict(st.get("bottlenecks") or {}),
                }), [], []
        for index, desired in enumerate(field_via_needs):
            if len(field_vias[index]) < desired:
                st["notes"].append(
                    "field %d (%s) has %d/%d barrels: ampacity minimum met, "
                    "redundancy target constrained" %
                    (index, fields[index][6], len(field_vias[index]),
                     desired))
        vias = [
            {"net": net, "x_mm": x, "y_mm": y,
             "role": ("transition_bridge"
                      if fields[field_index][6] == "crossing"
                      else "current_share_stitch"),
             "field_kind": fields[field_index][6],
             "field_index": field_index,
             "distribution": ("compact"
                              if fields[field_index][6] == "crossing"
                              else "uniform_overlap")}
            for field_index, vs in enumerate(field_vias)
            for slot, (x, y) in enumerate(vs)]

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
            if st.get("bundle"):
                # Bundle candidates are searched independently in each
                # participating layer's exact clearance-expanded geometry.
                # The 0.8 mm raster deliberately over-stamps foreign pads by
                # up to a cell diagonal and was vetoing legal connector-edge
                # detours that the exact configuration-space proof cleared.
                # Recheck the emitted polygon against the same exact obstacle
                # authority; do not turn conservative raster aliasing into a
                # fictitious pinch point.
                realized = unary_union(
                    list(polys) + list(land_polys.get(lay, ())))
                record_source = (st.get("bundle_obstacle_records")
                                 or st.get("obstacle_records") or {})
                clashes = _exact_clearance_clash_evidence(
                    realized, record_source.get(lay, ()))
                if clashes:
                    return _fail_entry(
                        "parallel-bundle exact clearance violation on %s"
                        % lay,
                        bottleneck={
                            "kind": "realized_exact_clearance",
                            "layer": lay,
                            "clashes": clashes,
                            "owners": sorted({
                                row["owner"] for row in clashes
                                if row.get("owner")}),
                        }), [], []
                bad = np.zeros_like(m)
            else:
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
                            if pk2 and lay in _candidate_layers(pk2) and \
                                    _candidate_poly(pk2, lay).buffer(
                                        0.01).covers(
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
            if st.get("bundle"):
                bundle = st["bundle"]
                for lay in bundle["layers"]:
                    layer_obstacles = list(
                        (st.get("bundle_obst") or st["obst"])[lay])
                    if st.get("gap_geom") is not None:
                        layer_obstacles.append(st["gap_geom"])
                    bundle["spaces"][lay] = _LayerSpace(
                        st["region"], layer_obstacles,
                        st["reqw"][lay] / 2.0,
                        f_allow=None, approach=st.get("approach"),
                        half_neck=W_NECK / 2.0, neck_unguard=0.0)
            st.pop("spaces_taper", None)

            def _foreign_clash(cand):
                return any(
                    _candidate_poly(cand, lay).buffer(0.3).intersects(h)
                    and _candidate_poly(cand, lay).buffer(
                        0.3).intersection(h).area > 0.01
                    for lay in _candidate_layers(cand)
                    for h in _assigned_foreign(nets, net, lay))

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
                                                land_polys, field_vias,
                                                extra_lines=spine_lines)
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
        cleanup_stats = {"micro_fills": 0, "elbow_fills": 0,
                         "added_mm2": 0.0}
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
                # A layer-specific satellite is conductive only if it owns a
                # physical seed on that layer: a native terminal/pad, an
                # already pad-anchored same-net pour, or an actual transition
                # barrel. Aggregate multi-layer connectivity can otherwise
                # hide a dead polygon after a field is redistributed away
                # from its nominal terminal spot; KiCad correctly reports the
                # result as isolated copper even though the rail as a whole
                # remains connected.
                if not _component_physical_seeded(
                        g, lay, st, fields, field_vias):
                    st["notes"].append(
                        "pruned unseeded %.3fmm2 %s copper component" %
                        (g.area, lay))
                    continue
                obstacle_source = ((st.get("bundle_obst") or {})
                                   if st.get("bundle") else
                                   (st.get("obst") or {}))
                forbidden_parts = list(obstacle_source.get(lay, ()))
                forbidden_parts.extend(
                    p.buffer(0.3, join_style=2)
                    for p in _assigned_foreign(nets, net, lay))
                if lay == "F.Cu" and st.get("gap_geom") is not None:
                    forbidden_parts.append(st["gap_geom"])
                forbidden = (unary_union(forbidden_parts)
                             if forbidden_parts else None)
                g, cleaned = _orthogonal_cleanup(
                    g, st["reqw"].get(lay, W_NECK), forbidden,
                    st.get("region"))
                for key in cleanup_stats:
                    cleanup_stats[key] += cleaned[key]
                original = g
                g = _emit_rectilinear(g)
                field_barrels = [
                    Point(x, y).buffer(max(0.01, VIA_R - 0.03))
                    for field, vs in zip(fields, field_vias)
                    if lay in (field[2], field[3])
                    for x, y in vs]
                g = _restore_rectilinear_barrels(
                    g, original, field_barrels, forbidden=forbidden,
                    region=st.get("region"))
                if g is None or _diagonal_edges(g.exterior.coords):
                    return _fail_entry(
                        "rectilinear emission cannot preserve a legal via "
                        "landing on %s" % lay), [], []
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
               "pofv_seeded_fields": pofv_seeded_fields,
               "via_distribution": {
                   "mode": "uniform-overlap-lattice",
                   "fields_spread": spread_fields,
                   "vias_moved": spread_moved,
                   "max_span_before_mm": round(max(spread_before), 3)
                       if spread_before else 0.0,
                   "max_span_after_mm": round(max(spread_after), 3)
                       if spread_after else 0.0,
               },
               "orthogonal_cleanup": {
                   "micro_fills": cleanup_stats["micro_fills"],
                   "elbow_fills": cleanup_stats["elbow_fills"],
                   "added_mm2": round(cleanup_stats["added_mm2"], 3)},
               "notes": list(st["notes"])}
        if st.get("bundle"):
            ent["parallel_bundle"] = {
                "layers": list(st["bundle"]["layers"]),
                "per_layer_fraction": st["bundle"]["per_layer_fraction"],
                "aggregate_capacity_fraction":
                    st["bundle"]["aggregate_capacity_fraction"],
                "per_layer_amps": {
                    lay: st["layer_amps"][lay]
                    for lay in st["bundle"]["layers"]},
                "required_width_mm": {
                    lay: st["reqw"][lay]
                    for lay in st["bundle"]["layers"]},
            }
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
    ap.add_argument("--cell-mm", type=float, default=0.8)
    ap.add_argument("--clearance-mm", type=float, default=0.3)
    a = ap.parse_args()
    b = pcbnew.LoadBoard(a.board)
    asks = [{"net": n, "layers": ("In2.Cu",)}
            for n in a.nets.split(",") if n]
    pours, vias, rep = plan_pours(
        b, asks, cell_mm=a.cell_mm, clearance_mm=a.clearance_mm)
    print(json.dumps({"pours": len(pours), "vias": len(vias),
                      "report": rep}, indent=1, default=str))
