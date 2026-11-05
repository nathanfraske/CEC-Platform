"""Bounded same-net copper-minus-pad topology, not an electrical rating.

Never replace this with deletion of a PAD graph vertex or clipped centrelines.
Complete conductor polygons are cut, including track caps and filled zones.
An upper copper / lower cut model can prove isolation. A lower copper / upper
cut model can prove a bypass. Disagreement is unknown, never a width waiver.
Native ERROR_INSIDE/OUTSIDE approximations and a 2 nm numerical guard bracket
curves; they are not fabrication clearance or electrical design margins.
"""
from __future__ import annotations

from collections import deque
import hashlib
import json
import math
import time

MAX_ITEMS = 8192
MAX_NET_ITEMS = 512
MAX_VERTICES = 200_000
MAX_COMPONENTS = 2048
MAX_CONTACTS = 262_144
ERROR_NM = 1000
GUARD_NM = 2
SCOPE = "same_net_geometric_copper_cut_isolation_not_electrical_qualification"


class Unknown(RuntimeError):
    pass


def identity(item):
    result = dict(kind=item.GetClass(), uuid=item.m_Uuid.AsString(), net=item.GetNetname())
    if item.GetClass() == "PAD":
        fp, at = item.GetParentFootprint(), item.GetPosition()
        result.update(footprint_uuid=fp.m_Uuid.AsString(), ref=fp.GetReference(),
                      pad=item.GetNumber(), position_nm=[int(at.x), int(at.y)])
    return result


def _key(item):
    import json
    return json.dumps(identity(item), sort_keys=True)


class _Work:
    def __init__(self, deadline):
        self.deadline, self.vertices, self.contacts = deadline, 0, 0
        self.envelopes = {}
        self.linear_certificates = {}
        self.linear_epochs = {}
        self.linear_items = {}
        self.linear_object_keys = {}

    def tick(self):
        if time.monotonic() >= self.deadline:
            raise Unknown("copper_cut_deadline_exhausted")

    def contact(self):
        self.tick()
        self.contacts += 1
        if self.contacts > MAX_CONTACTS:
            raise Unknown("copper_cut_contact_budget_exhausted")


def _parts(shape):
    if shape.is_empty:
        return []
    if shape.geom_type == "Polygon":
        return [shape]
    if shape.geom_type in ("MultiPolygon", "GeometryCollection"):
        return [part for member in shape.geoms for part in _parts(member)]
    raise Unknown("non_areal_copper_geometry")


def _poly(native, work):
    from shapely.geometry import Polygon, GeometryCollection
    from shapely.ops import unary_union

    work.tick()
    if native.OutlineCount()>MAX_COMPONENTS:
        raise Unknown('copper_cut_component_budget_exhausted')
    if native.OutlineCount()>1:
        # A filled polygon set is a UNION of independently signed positive
        # records. Source-preserving fills can legitimately retain overlapping
        # records, even identical boundaries. Decode each one's paired bridges
        # before that union: counting all record edges together conflates a
        # real overlap with a malformed bridge and can turn valid saved copper
        # into unknown. No boundary is discarded, deduplicated or repaired;
        # EVERY record passes the same native exact-edge/zero-set-change
        # decoder and validity/vertex/deadline checks below, holes included.
        import pcbnew
        pieces=[]
        for i in range(native.OutlineCount()):
            work.tick();one=pcbnew.SHAPE_POLY_SET()
            one.AddOutline(native.Outline(i))
            for j in range(native.HoleCount(i)):
                work.tick();one.AddHole(native.Hole(i,j),0)
            pieces.append(_poly(one,work))
        work.tick();result=unary_union(pieces)
        if not result.is_valid:raise Unknown('invalid_native_polygon_union')
        return result

    # Filled KiCad holes are often saved as a weakly-simple outer ring with
    # paired zero-width bridges. A floating Polygon calls that ring invalid.
    # Decode only an exact native-set-equivalent PRIVATE clone; never repair
    # topology with buffer(0), fill holes, or alter the saved source copper.
    repeated = False; inspected = 0
    for i in range(native.OutlineCount()):
        for chain in [native.Outline(i), *[native.Hole(i,j) for j in range(native.HoleCount(i))]]:
            work.tick(); inspected += chain.PointCount()
            if work.vertices + inspected > MAX_VERTICES:
                raise Unknown('copper_cut_vertex_budget_exhausted')
            points = [(int(chain.CPoint(k).x), int(chain.CPoint(k).y)) for k in range(chain.PointCount())]
            # A literal repeated closing point is an ordinary closed chain,
            # not an interior zero-width hole bridge.
            if len(points)>1 and points[0]==points[-1]: points=points[:-1]
            repeated |= len(set(points)) != len(points)
    if repeated:
        from cec_native_fill_geometry import decode_linear_hole_bridges, decode_exact_hole_boundaries
        try:
            try:
                decoded, proof = decode_linear_hole_bridges(native, work.deadline,
                    max_vertices=MAX_VERTICES-work.vertices)
            except ValueError as exc:
                # An edge-changing native Unfracture is NOT accepted. Read
                # the untouched source's literal edges with the independent
                # integer-cycle decoder instead. All exact edge, topology,
                # deadline and zero native-set-change checks remain required.
                if str(exc)!='native_bridge_contours_or_boundary_edges_changed':raise
                decoded, proof = decode_exact_hole_boundaries(native, work.deadline,
                    max_vertices=MAX_VERTICES-work.vertices)
            native=decoded
        except (ValueError, RuntimeError) as exc:
            raise Unknown('native_hole_bridge_decode_refused:'+str(exc)) from exc
        work.vertices += proof['input_vertices']

    def ring(chain):
        work.tick()
        if chain.ArcCount():
            raise Unknown("unlinearized_native_polygon_arc")
        work.vertices += chain.PointCount()
        if work.vertices > MAX_VERTICES:
            raise Unknown("copper_cut_vertex_budget_exhausted")
        points = [(int(chain.CPoint(i).x), int(chain.CPoint(i).y))
                  for i in range(chain.PointCount())]
        if len(points) < 3 or any(abs(v) > 2_147_483_647 for p in points for v in p):
            raise Unknown("invalid_native_polygon_coordinates")
        return points

    polygons = []
    for i in range(native.OutlineCount()):
        shape = Polygon(ring(native.Outline(i)),
                        [ring(native.Hole(i, j)) for j in range(native.HoleCount(i))])
        if not shape.is_valid or shape.is_empty or shape.area <= 0:
            raise Unknown("invalid_native_polygon")
        polygons.append(shape)
    work.tick()
    result = unary_union(polygons) if polygons else GeometryCollection()
    if not result.is_valid:
        raise Unknown("invalid_native_polygon_union")
    return result


def _envelope(shape, upper):
    # Square joins prevent an outward buffer from inscribing a convex corner.
    # The guard accounts only for integer/boolean roundoff, not missing copper.
    return shape.buffer(GUARD_NM if upper else -GUARD_NM, join_style=2)


def _shape(item, layer, upper, work):
    import pcbnew
    work.tick()
    key = ("copper", _key(item), layer)
    if key not in work.envelopes:
        bounds = {}
        for outside in (False, True):
            polygon = pcbnew.SHAPE_POLY_SET()
            item.TransformShapeToPolygon(polygon, layer, 0, ERROR_NM,
                pcbnew.ERROR_OUTSIDE if outside else pcbnew.ERROR_INSIDE, False)
            shape = _poly(polygon, work)
            if shape.is_empty:
                raise Unknown("native_conductor_polygon_unavailable")
            bounds[outside] = _envelope(shape, outside)
        if not bounds[True].covers(bounds[False]):
            raise Unknown("native_copper_bounds_not_nested")
        work.envelopes[key] = bounds
    return work.envelopes[key][upper]


def _orientation(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def _convex_core_contained(native, rectangles, work, *, returned_geometry=None):
    """Exact integer half-plane proof; no epsilon or floating containment test.

    Independently require that the native ERROR_INSIDE ring is its convex
    hull, including winding/order. Checking only its bbox or four corner
    samples in a possibly concave pad would not certify a whole rectangle.
    """
    if native.OutlineCount() != 1 or native.HoleCount(0):
        return False
    ring = native.Outline(0)
    if ring.ArcCount():
        return False
    points = [(int(ring.CPoint(i).x), int(ring.CPoint(i).y)) for i in range(ring.PointCount())]
    if points and points[0] == points[-1]:
        points.pop()
    if len(points) < 3 or len(set(points)) != len(points):
        return False
    ordered = sorted(points)
    def half(sequence):
        out = []
        for point in sequence:
            work.contact()
            while len(out) >= 2 and _orientation(out[-2], out[-1], point) <= 0:
                out.pop()
            out.append(point)
        return out
    hull = half(ordered)[:-1] + half(reversed(ordered))[:-1]
    reduced = [p for i,p in enumerate(points)
               if _orientation(points[i-1],p,points[(i+1)%len(points)]) != 0]
    area2 = sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(reduced,reduced[1:]+reduced[:1]))
    if area2 < 0:
        reduced.reverse()
    if len(hull) < 3 or len(hull) != len(reduced) or not area2:
        return False
    index = hull.index(reduced[0]) if reduced[0] in hull else -1
    if index < 0 or hull[index:]+hull[:index] != reduced:
        return False
    for x1,y1,x2,y2 in rectangles:
        for corner in ((x1,y1),(x1,y2),(x2,y1),(x2,y2)):
            for a,b in zip(hull,hull[1:]+hull[:1]):
                work.contact()
                if _orientation(a,b,corner) < 0:
                    return False
    if returned_geometry is not None:
        # GEOS returns binary64 vertices. Their exact integer ratios, not a
        # tolerance or rounded database coordinate, certify every returned
        # segment against the same convex native interior half-planes. A
        # polygon whose vertices lie in a convex set lies entirely in it.
        from fractions import Fraction
        for part in _parts(returned_geometry):
            for ring in [part.exterior,*part.interiors]:
                for x,y in ring.coords:
                    point = (Fraction(x),Fraction(y))
                    for a,b in zip(hull,hull[1:]+hull[:1]):
                        work.contact()
                        if _orientation(a,b,point) < 0:
                            return False
    return True


def _linear_epoch(item, layer, kind, signature, certificate, work, *, snapshot_key):
    key = (kind, _key(item), int(layer))
    if key[1] != snapshot_key:
        raise Unknown("exact_linear_geometry_identity_changed")
    # A changed reference/net/position must not register a fresh epoch for the
    # same native object. Nor may a replacement object silently overwrite the
    # original item under an identical UUID and receipt identity.
    object_key = (kind, int(item.this), int(layer))
    if object_key in work.linear_object_keys and work.linear_object_keys[object_key] != key:
        raise Unknown("exact_linear_geometry_identity_changed")
    if key in work.linear_items and int(work.linear_items[key][0].this) != int(item.this):
        raise Unknown("exact_linear_native_object_replaced")
    digest = hashlib.sha256(json.dumps(signature, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if key in work.linear_epochs and work.linear_epochs[key] != digest:
        raise Unknown("exact_linear_geometry_identity_changed")
    work.linear_epochs[key] = digest
    work.linear_items[key] = (item, layer, kind)
    work.linear_object_keys[object_key] = key
    certificate.update(identity=identity(item), layer=int(layer), geometry_sha256=digest)
    work.linear_certificates[key] = certificate


def _source_cut(item, layer, upper, work):
    """Refine ONLY the lower cut with an independently certified exact core.

    Cardinal zero-offset native RECT/ROUNDRECT pads contain their analytic
    central rectangle(s). Integer floor half-extents round INWARD for odd
    sizes. Layer-specific native dimensions, shape position, radius and an
    exact convex ERROR_INSIDE containment proof must independently agree.
    The union of two certified subsets remains a lower bound. Curved corners
    retain their original 2 nm inward guard and native curve approximation.
    """
    import pcbnew
    from shapely.geometry import box
    from shapely.ops import unary_union
    work.tick()
    if item.GetClass() != "PAD":
        raise Unknown("exact_source_cut_requires_native_pad")
    snapshot_key = _key(item)
    size, offset, delta = item.GetSize(layer), item.GetOffset(layer), item.GetDelta(layer)
    position, shape_position = item.GetPosition(), item.ShapePos(layer)
    shape = item.GetShape(layer)
    angle = item.GetOrientationDegrees()
    radius = item.GetRoundRectCornerRadius(layer) if shape == pcbnew.PAD_SHAPE_ROUNDRECT else 0
    parameters = dict(shape=int(shape), attribute=int(item.GetAttribute()),
        size_nm=[int(size.x),int(size.y)], position_nm=[int(position.x),int(position.y)],
        shape_position_nm=[int(shape_position.x),int(shape_position.y)],
        offset_nm=[int(offset.x),int(offset.y)], delta_nm=[int(delta.x),int(delta.y)],
        orientation_degrees=angle, radius_nm=radius, chamfer_positions=int(item.GetChamferPositions(layer)),
        has_hole=bool(item.HasHole()), on_layer=bool(item.IsOnLayer(layer)), flashed=bool(item.FlashLayer(layer)))
    native = pcbnew.SHAPE_POLY_SET()
    item.TransformShapeToPolygon(native, layer, 0, ERROR_NM, pcbnew.ERROR_INSIDE, False)
    inside = _poly(native, work)
    native_sha = hashlib.sha256(native.Format().encode()).hexdigest()
    certificate = dict(kind="source_interior_core", applied=False, parameters=parameters,
        native_inside_sha256=native_sha, core_rectangles_nm=[],
        provenance="integer_cardinal_parameters_and_exact_convex_native_inside_halfplanes",
        returned_cut_provenance="exact_rational_vertex_halfplanes_in_convex_native_inside")
    supported = (shape in (pcbnew.PAD_SHAPE_RECT,pcbnew.PAD_SHAPE_ROUNDRECT)
        and item.GetAttribute() == pcbnew.PAD_ATTRIB_SMD and not item.HasHole()
        and not (offset.x or offset.y or delta.x or delta.y or item.GetChamferPositions(layer))
        and position == shape_position and item.IsOnLayer(layer) and item.FlashLayer(layer)
        and math.isfinite(angle) and angle % 360 in (0,90,180,270)
        and size.x > 0 and size.y > 0 and type(radius) is int
        and 0 <= radius <= min(size.x,size.y)//2)
    rectangles = []
    if supported:
        hx,hy = int(size.x)//2,int(size.y)//2
        if angle % 180 == 90:
            hx,hy = hy,hx
        x,y = int(position.x),int(position.y)
        local = [(hx,hy)] if shape == pcbnew.PAD_SHAPE_RECT else [(hx-radius,hy),(hx,hy-radius)]
        rectangles = [[x-a,y-b,x+a,y+b] for a,b in local if a>0 and b>0]
        if (not rectangles or any(abs(n)>2_147_483_647 for r in rectangles for n in r)
                or not _convex_core_contained(native,rectangles,work)):
            rectangles = []
            certificate["reason"] = "native_inside_core_containment_unproved"
        else:
            certificate.update(applied=True,core_rectangles_nm=rectangles,
                               reason="certified_exact_integer_interior_core")
    else:
        certificate["reason"] = "unsupported_exact_linear_source_geometry_conservative_fallback"
    _linear_epoch(item,layer,"source",dict(parameters=parameters,native_inside_sha256=native_sha),
                  certificate,work,snapshot_key=snapshot_key)
    base = _shape(item,layer,upper,work)
    if upper or not rectangles:
        return base
    core = unary_union([box(*r) for r in rectangles])
    # Certify the actual Boolean output as well as its inputs. GEOS can report
    # covers(base) false although base.difference(union) is empty. Retaining
    # every old lower-bound point is not needed for safety: a lost point only
    # weakens the cut. The exact rational proof forbids ANY exterior point;
    # the enlarged cut remains a subset of the native ERROR_INSIDE polygon.
    refined = base.union(core)
    if (not refined.is_valid or not inside.covers(core) or not refined.covers(core)
            or not _shape(item,layer,True,work).covers(refined)
            or not _convex_core_contained(native,[],work,returned_geometry=refined)):
        raise Unknown("exact_source_cut_nesting_unproved")
    return refined


def _filled_native_snapshot(item, layer, work):
    """Own and bind exact saved linear fill before any numerical envelope."""
    import pcbnew
    work.tick()
    if item.GetClass() != "ZONE" or not item.IsFilled() or not item.IsOnLayer(layer):
        raise Unknown("native_zone_fill_unavailable")
    snapshot_key = _key(item)
    # Own a snapshot: a borrowed mutable polygon must not supply geometry and
    # an unrelated later fingerprint during one helper call.
    native = pcbnew.SHAPE_POLY_SET(item.GetFilledPolysList(layer))
    poly = _poly(native,work)
    bounds = None
    for i in range(native.OutlineCount()):
        chain = native.Outline(i)
        for j in range(chain.PointCount()):
            work.tick()
            point = chain.CPoint(j)
            x,y = int(point.x),int(point.y)
            if bounds is None:
                bounds = [x,y,x,y]
            else:
                bounds = [min(bounds[0],x),min(bounds[1],y),max(bounds[2],x),max(bounds[3],y)]
    native_sha = hashlib.sha256(native.Format().encode()).hexdigest()
    certificate = dict(kind="filled_zone_integer_axis_bounds",applied=bounds is not None,
        bounds_nm=bounds,native_filled_polygon_sha256=native_sha,
        provenance="linear_native_integer_endpoints_and_polygon_axis_halfplanes",
        reason="certified_exact_native_coordinate_extrema" if bounds else "empty_native_fill")
    _linear_epoch(item,layer,"zone",dict(native_filled_polygon_sha256=native_sha,bounds_nm=bounds),
                  certificate,work,snapshot_key=snapshot_key)
    return poly,bounds


def _filled_shape(item, layer, upper, work):
    """Constrain an upper fill only by its exact native integer axis bounds.

    Every native linear edge is a convex combination of its integer endpoints;
    every filled polygon lies within their coordinate extrema. Thus this box
    is an independently proven SUPERSET, including holes and disconnected
    islands. Intersecting two supersets does not discard any native copper.
    No vertex is snapped and a real one-database-unit protrusion moves the
    bound by that unit. Unsupported polygon arcs still fail in _poly.
    """
    from shapely.geometry import box
    poly,bounds=_filled_native_snapshot(item,layer,work)
    envelope = _envelope(poly,upper)
    if not upper or bounds is None:
        return envelope
    exact_box = box(*bounds)
    refined = envelope.intersection(exact_box)
    # Only containment of actual native material and the unchanged lower
    # bound is safety-critical. GEOS can report envelope.covers(refined)
    # false even when refined.difference(envelope) is empty; retaining extra
    # upper-bound material would be conservative, not false isolation.
    if (not refined.is_valid or not exact_box.covers(poly) or not refined.covers(poly)
            or not refined.covers(_envelope(poly,False))):
        raise Unknown("exact_filled_zone_bound_nesting_unproved")
    return refined


def _validate_linear_epochs(work):
    """Re-read geometry before any result is used as a positive certificate."""
    board_items = {}
    for key,(item,layer,kind) in list(work.linear_items.items()):
        work.tick()
        if key != (kind,_key(item),int(layer)):
            raise Unknown("exact_linear_geometry_identity_changed")
        board = item.GetBoard()
        if board is None:
            raise Unknown("exact_linear_native_object_not_on_board")
        board_key = int(board.this)
        if board_key not in board_items:
            pointers, count = set(), 0
            for fp in board.GetFootprints():
                count += 1
                work.tick()
                if count > MAX_ITEMS:
                    raise Unknown("copper_cut_inventory_budget_exhausted")
                for pad in fp.Pads():
                    count += 1
                    work.tick()
                    if count > MAX_ITEMS:
                        raise Unknown("copper_cut_inventory_budget_exhausted")
                    pointers.add(int(pad.this))
            for zone in board.Zones():
                count += 1
                work.tick()
                if count > MAX_ITEMS:
                    raise Unknown("copper_cut_inventory_budget_exhausted")
                pointers.add(int(zone.this))
            board_items[board_key] = pointers
        if int(item.this) not in board_items[board_key]:
            raise Unknown("exact_linear_native_object_not_on_board")
        if kind == "source":
            _source_cut(item,layer,False,work)
        else:
            _filled_shape(item,layer,False,work)
    work.tick()


def _hole(item, upper, work):
    import pcbnew
    key = ("hole", _key(item))
    if key not in work.envelopes:
        bounds = {}
        for outside in (False, True):
            polygon = pcbnew.SHAPE_POLY_SET()
            item.GetEffectiveHoleShape().TransformToPolygon(polygon, ERROR_NM,
                pcbnew.ERROR_OUTSIDE if outside else pcbnew.ERROR_INSIDE)
            shape = _poly(polygon, work)
            if shape.is_empty:
                raise Unknown("native_drill_polygon_unavailable")
            bounds[outside] = _envelope(shape, outside)
        if not bounds[True].covers(bounds[False]):
            raise Unknown("native_drill_bounds_not_nested")
        work.envelopes[key] = bounds
    return work.envelopes[key][upper]


def _inventory(board, work):
    import pcbnew
    pads, tracks, zones = [], [], []
    copper = tuple(board.GetEnabledLayers().CuStack())
    if not copper or len(copper) > 64:
        raise Unknown("invalid_enabled_copper_stack")
    count = 0
    for fp in board.GetFootprints():
        work.tick()
        count += 1
        if count > MAX_ITEMS:
            raise Unknown("copper_cut_inventory_budget_exhausted")
        for pad in fp.Pads():
            count += 1
            if count > MAX_ITEMS:
                raise Unknown("copper_cut_inventory_budget_exhausted")
            pads.append(pad)
        # Copper graphics/net ties are not silently omitted from a certificate.
        for graphic in fp.GraphicalItems():
            work.tick()
            count += 1
            if count > MAX_ITEMS:
                raise Unknown("copper_cut_inventory_budget_exhausted")
            if any(graphic.IsOnLayer(layer) for layer in copper):
                raise Unknown("unsupported_footprint_copper_graphic")
    for collection, target in ((board.GetTracks(), tracks), (board.Zones(), zones)):
        for item in collection:
            work.tick()
            count += 1
            if count > MAX_ITEMS:
                raise Unknown("copper_cut_inventory_budget_exhausted")
            if item.GetClass() == "ZONE" and item.GetIsRuleArea():
                continue
            target.append(item)
    for graphic in board.GetDrawings():
        work.tick()
        count += 1
        if count > MAX_ITEMS:
            raise Unknown("copper_cut_inventory_budget_exhausted")
        if any(graphic.IsOnLayer(layer) for layer in copper):
            raise Unknown("unsupported_board_copper_graphic")
    return pads, tracks, zones, copper


def _simple_drill(item, copper):
    """Only unmodified through barrels are currently modeled in three dimensions."""
    import pcbnew
    if item.GetClass() == "PAD":
        if not item.HasHole():
            return False
        if item.GetAttribute() not in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH):
            raise Unknown("unsupported_drilled_pad_attribute")
        if (item.GetAttribute() == pcbnew.PAD_ATTRIB_PTH
                and not set(copper).issubset(item.GetLayerSet().CuStack())):
            raise Unknown("unsupported_partial_barrel_padstack")
        if (item.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH
                and (item.GetPrimaryDrillFilledFlag() or item.GetPrimaryDrillCappedFlag())):
            raise Unknown("unsupported_filled_or_capped_nonplated_hole")
    elif item.GetClass() == "PCB_VIA":
        if item.GetViaType() != pcbnew.VIATYPE_THROUGH:
            raise Unknown("unsupported_non_through_barrel")
        if not set(copper).issubset(item.GetLayerSet().CuStack()):
            raise Unknown("unsupported_partial_barrel_span")
    else:
        return False
    # Flipping a footprint reverses these endpoints without changing a full
    # through bore. Only the two physical outer layers, in either order, are
    # accepted; all partial/backdrilled/secondary/padstack checks remain.
    if ({item.GetPrimaryDrillStartLayer(), item.GetPrimaryDrillEndLayer()}
            != {copper[0], copper[-1]}):
        raise Unknown("unsupported_partial_primary_drill")
    for prefix in ("Secondary", "Tertiary"):
        size = getattr(item, "Get"+prefix+"DrillSize")()
        nonzero = bool(size.x or size.y) if hasattr(size, "x") else size not in (None, 0)
        if (nonzero or getattr(item, "Get"+prefix+"DrillShape")() != pcbnew.PAD_DRILL_SHAPE_UNDEFINED
                or getattr(item, "Get"+prefix+"DrillStartLayer")() != pcbnew.UNDEFINED_LAYER
                or getattr(item, "Get"+prefix+"DrillEndLayer")() != pcbnew.UNDEFINED_LAYER):
            raise Unknown("unsupported_secondary_or_tertiary_drill")
    if item.GetBackdrillMode() != pcbnew.BACKDRILL_MODE_NO_BACKDRILL:
        raise Unknown("unsupported_backdrilled_barrel")
    for side in ("Top", "Bottom"):
        if (getattr(item, "Get"+side+"BackdrillLayer")() != pcbnew.UNDEFINED_LAYER
                or getattr(item, "Get"+side+"BackdrillSize")() is not None):
            raise Unknown("unsupported_backdrilled_barrel")
    if (any(getattr(item, "Get"+side+"PostMachiningMode")() !=
            pcbnew.PAD_DRILL_POST_MACHINING_MODE_NOT_POST_MACHINED for side in ("Front", "Back"))
            or any(item.IsBackdrilledOrPostMachined(layer) for layer in copper)):
        raise Unknown("unsupported_postmachined_barrel")
    if item.GetEffectiveHoleShape() is None:
        raise Unknown("native_drill_shape_unavailable")
    return True


def _model(items, drilled, zones, copper, source, sense, authorities, upper, work, *, cut_enabled=True):
    from shapely.geometry import GeometryCollection
    from shapely.ops import unary_union
    import pcbnew

    empty = GeometryCollection()
    # Holes cut the entire union, including a trace that crosses a drill centre.
    holes = {key: _hole(item, not upper, work) for key, item in drilled.items()}
    # Retaining possible plated fill/cap material only enlarges the upper
    # model. Never infer that a manufacturing-profile POFV cap is a void.
    # The lower model subtracts every bore, independent of fill metallurgy.
    voids = [shape for key, shape in holes.items() if not upper or
             drilled[key].GetClass() == "PAD" and
             drilled[key].GetAttribute() == pcbnew.PAD_ATTRIB_NPTH]
    void = unary_union(voids) if voids else empty
    cut = ({layer: _source_cut(source, layer, not upper, work)
            for layer in copper if source.IsOnLayer(layer) and source.FlashLayer(layer)}
           if cut_enabled else {})
    if cut_enabled and (not cut or any(shape.is_empty for shape in cut.values())):
        raise Unknown("source_cut_polygon_unavailable")
    shapes, raw_shapes = {}, {}
    for item in items:
        work.tick()
        if cut_enabled and _key(item) == _key(source):
            continue
        per_layer, raw = {}, {}
        for layer in copper:
            if not item.IsOnLayer(layer):
                continue
            key = _key(item)
            if (key in drilled and (item.GetClass() == "PCB_VIA"
                    or item.GetAttribute() == pcbnew.PAD_ATTRIB_PTH)):
                # An offset/undersized nominal land can miss real plated wall
                # contact outside it. Do not silently omit that barrel copper.
                # This is containment only, not a minimum-annular-ring rating.
                if not _shape(item, layer, False, work).covers(_hole(item, True, work)):
                    raise Unknown("plated_bore_not_enclosed_by_native_land")
            # Nominal unflashed lands only enlarge the upper connectivity model.
            if not upper and hasattr(item, "FlashLayer") and not item.FlashLayer(layer):
                continue
            shape = _shape(item, layer, upper, work)
            raw[layer] = shape
            per_layer[layer] = shape.difference(void).difference(cut.get(layer, empty))
        shapes[_key(item)], raw_shapes[_key(item)] = per_layer, raw
    filled = {layer: [] for layer in copper}
    native_lower_fills = {layer: [] for layer in copper}
    zone_shapes = {}
    for zone in zones:
        if not zone.IsFilled():
            raise Unknown("native_zone_fill_unavailable")
        if zone.GetNetname()!=source.GetNetname():
            raise Unknown("same_net_native_fill_union_required")
        per = {}
        for layer in copper:
            if zone.IsOnLayer(layer):
                if upper:
                    fill=_filled_shape(zone,layer,True,work)
                else:
                    native,_=_filled_native_snapshot(zone,layer,work)
                    native_lower_fills[layer].append(native)
                    fill=_envelope(native,False)
                per[layer] = fill.difference(void).difference(cut.get(layer, empty))
                if upper:filled[layer].append(per[layer])
        zone_shapes[_key(zone)] = per
    if not upper:
        for layer,parts in native_lower_fills.items():
            work.tick()
            # A saved filled polygon is exact native linear material, not a
            # curve approximation. Same-net/face records may share a genuine
            # positive-length boundary. Eroding each record separately invents
            # two numerical guards at that INTERNAL seam. Union only their
            # exact sets first, with holes intact, then guard the physical
            # union once. No outward buffer, snapping, tolerance join, other
            # net/face or nominal zone outline participates. Point contacts
            # and real one-unit gaps remain disconnected in the lower model.
            native=unary_union(parts) if parts else empty
            if not native.is_valid:raise Unknown("invalid_native_lower_fill_union")
            filled[layer]=[_envelope(native,False).difference(void).difference(cut.get(layer,empty))]
    nodes = []
    for layer in copper:
        work.tick()
        union = unary_union([per[layer] for per in shapes.values() if layer in per]
                            + filled[layer])
        if not union.is_valid:
            raise Unknown("invalid_clipped_copper_union")
        # GEOS polygon enumeration is not a physical component identity.
        # Equivalent input-container orders can permute disjoint islands,
        # spuriously changing the ordinal carried by an otherwise identical
        # native witness. Canonicalize the exact material BEFORE graph/BFS
        # construction; keep holes, contributors, bounds and every proof
        # field intact. This is not a consumer-side ignored-field waiver.
        def physical_order(part):
            work.tick()
            return (*part.bounds, part.normalize().wkb)
        nodes.extend((layer, part) for part in sorted(_parts(union),key=physical_order))
    if len(nodes) > MAX_COMPONENTS:
        raise Unknown("copper_cut_component_budget_exhausted")
    # A globally sorted ordinal still changes when an unrelated island is
    # relocated before this one. Bind each reported component to its actual
    # layer and complete normalized polygon (holes included), not its BFS
    # storage slot. Graph indices remain private implementation details.
    component_tokens=[]
    for layer,part in nodes:
        work.tick()
        component_tokens.append('native-copper-'+str(layer)+'-'+
            hashlib.sha256(part.normalize().wkb).hexdigest())
    adjacency = [[] for _ in nodes]

    def link(a, b, via=None):
        adjacency[a].append((b, via))
        adjacency[b].append((a, via))

    # Separate polygons can touch at a single point. Only upper connectivity
    # counts such zero-area contacts as a possible path.
    if upper:
        for a, (layer, poly) in enumerate(nodes):
            for b in range(a):
                work.contact()
                if nodes[b][0] == layer and poly.intersects(nodes[b][1]):
                    link(a, b)

    def contacts(per, positive=False):
        hit = []
        for i, (layer, poly) in enumerate(nodes):
            work.contact()
            shape = per.get(layer)
            if shape is not None and (poly.intersection(shape).area > 0 if positive
                                      else poly.intersects(shape)):
                hit.append(i)
        return hit

    for key, item in drilled.items():
        if key not in shapes or item.GetClass() == "PAD" and item.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
            continue
        per, raw = shapes[key], raw_shapes[key]
        if not upper:
            # A partly cut/overdrilled annulus has no definite lower barrel
            # link. The upper model retains it, so uncertainty cannot pass.
            own_hole = holes[key]
            safe = {}
            for layer, body in raw.items():
                work.tick()
                if (len(_parts(body)) == 1 and body.covers(own_hole.buffer(GUARD_NM, join_style=2))
                        and not body.intersects(cut.get(layer, empty))
                        and not any(body.intersects(other) for other_key, other in holes.items()
                                    if other_key != key)):
                    safe[layer] = per[layer]
            per = safe
        ends = contacts(per, positive=not upper)
        for end in ends[1:]:
            link(ends[0], end, identity(item))

    # A terminal overlapping the cut can have ambiguous ownership; neither
    # absence nor a fragment-only seed can become a positive certificate.
    terminal_keys = [_key(sense), *(_key(pad) for pad in authorities)]
    for key in terminal_keys:
        if key not in shapes or not shapes[key] or any(
                shape.intersects(cut.get(layer, empty)) for layer, shape in raw_shapes[key].items()):
            raise Unknown("sense_or_authority_terminal_intersects_cut")
    starts = contacts(shapes[_key(sense)], positive=not upper)
    terminals = [(pad, contacts(shapes[_key(pad)], positive=not upper)) for pad in authorities]
    if not starts or any(not ends for _, ends in terminals):
        raise Unknown("terminal_has_no_retained_copper_contact")
    if not upper:
        # Multi-source BFS must not turn disconnected custom-pad islands or
        # unplated SMD faces into one physical electrical terminal.
        for ends in [starts, *(ends for _, ends in terminals)]:
            connected, pending = {ends[0]}, [ends[0]]
            while pending:
                work.tick()
                for nxt, _ in adjacency[pending.pop()]:
                    if nxt not in connected:
                        connected.add(nxt)
                        pending.append(nxt)
            if not set(ends).issubset(connected):
                raise Unknown("terminal_copper_islands_not_physically_connected")
    parent = {i: (None, None) for i in starts}
    queue = deque(starts)
    while queue:
        work.tick()
        node = queue.popleft()
        for nxt, via in adjacency[node]:
            if nxt not in parent:
                parent[nxt] = (node, via)
                queue.append(nxt)
    reached, witnesses = [], []
    for pad, ends in terminals:
        end = next((i for i in ends if i in parent), None)
        if end is None:
            continue
        reached.append(identity(pad))
        chain = []
        while end is not None:
            layer, part = nodes[end]
            previous, via = parent[end]
            contributors = []
            for item in items:
                work.contact()
                key = _key(item)
                if key in shapes and layer in shapes[key] and part.intersects(shapes[key][layer]):
                    contributors.append(identity(item))
            for zone in zones:
                work.contact()
                per = zone_shapes[_key(zone)]
                if layer in per and part.intersects(per[layer]):
                    contributors.append(identity(zone))
            # Native container iteration order is not material evidence.
            # Adding unrelated copper can reorder BOARD.GetTracks() while
            # every actual witness contributor remains identical. Emit a
            # canonical sequence at the producer; retain ALL identities and
            # duplicates. Consumers still compare every contributor/value.
            contributors.sort(key=lambda row:json.dumps(row,sort_keys=True,separators=(',',':')))
            chain.append(dict(component=component_tokens[end], layer=pcbnew.LayerName(layer),
                bounds_nm=list(part.bounds), via=via, contributors=contributors))
            end = previous
        witnesses.append(dict(authority=identity(pad), path=list(reversed(chain))))
    return dict(reached_authority=reached, witnesses=witnesses, components=len(nodes),
                cut_layers=[pcbnew.LayerName(layer) for layer in cut],
                bound="upper_possible_connectivity" if upper else "lower_definite_connectivity")


def audit(board, source_pad, sense_pad, authority_pads, *, deadline=None):
    """Read-only proof for one declared physical source/sense/authority leg.

    The caller owns electrical lineage/current authority; this function checks
    exact native identities, baseline connectivity and every modeled conductor.
    Unsupported material/drill geometry is unknown. No source mutation, fill,
    thermal/current rating, whole-board Kelvin pass or fabrication permission.
    """
    import pcbnew
    start = time.monotonic()
    if deadline is None:
        deadline = start + 30
    if (type(deadline) not in (float, int) or not math.isfinite(deadline)
            or deadline < 0 or deadline > start+60):
        raise ValueError("deadline must be finite and at most 60 seconds ahead")
    work = _Work(deadline)
    result = dict(schema=1, scope=SCOPE, ok=None, complete=False,
        reason=None, tracks_clipped=True,
        physical_bypass_proved=False, release_authority=False,
        full_kelvin_qualification=False, electrical_rating_qualified=False,
        approximation_error_nm=ERROR_NM, numerical_guard_nm=GUARD_NM,
        exact_linear_identity_verified=False)
    try:
        import shapely
        result["runtime"] = dict(kicad=pcbnew.GetBuildVersion(), shapely=shapely.__version__,
                                  geos=shapely.geos_version_string)
        # Iterators must not be consumed once for reporting and again for
        # validation. The bounded snapshot is the sole terminal authority.
        from itertools import islice
        authority_pads = list(islice(iter(authority_pads), MAX_NET_ITEMS+1))
        if len(authority_pads) > MAX_NET_ITEMS:
            raise Unknown("authority_terminal_budget_exhausted")
        result.update(source=identity(source_pad), sense=identity(sense_pad),
                      authority=[identity(p) for p in authority_pads])
        pads, tracks, zones, copper = _inventory(board, work)
        by_key = {_key(pad): pad for pad in pads}
        if len(by_key) != len(pads):
            raise Unknown("ambiguous_physical_pad_identity")
        terminals = [source_pad, sense_pad, *authority_pads]
        if not authority_pads or len({_key(p) for p in terminals}) != len(terminals):
            raise Unknown("missing_or_aliased_terminal_identity")
        if any(_key(p) not in by_key for p in terminals):
            raise Unknown("terminal_identity_not_on_board")
        source_pad, sense_pad, *authority_pads = [by_key[_key(p)] for p in terminals]
        net = source_pad.GetNetname()
        if not net or any(p.GetNetname() != net for p in terminals):
            raise Unknown("terminal_net_mismatch")
        if any(p.GetAttribute() not in (pcbnew.PAD_ATTRIB_SMD, pcbnew.PAD_ATTRIB_PTH) for p in terminals):
            raise Unknown("unsupported_nonconducting_terminal")
        if source_pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD or source_pad.HasHole():
            raise Unknown("unsupported_non_smd_shunt_cut")
        if sum(source_pad.IsOnLayer(layer) and source_pad.FlashLayer(layer) for layer in copper) != 1:
            raise Unknown("unsupported_multiface_smd_shunt_cut")
        # Prime the source epoch before the independent baseline uses its
        # native geometry; later refinements may not certify a different pad.
        for layer in copper:
            if source_pad.IsOnLayer(layer) and source_pad.FlashLayer(layer):
                _source_cut(source_pad,layer,False,work)
        items = [p for p in pads if p.GetNetname() == net] + [t for t in tracks if t.GetNetname() == net]
        net_zones = [z for z in zones if z.GetNetname() == net]
        if len(items)+len(net_zones) > MAX_NET_ITEMS:
            raise Unknown("copper_cut_net_budget_exhausted")
        if len({_key(i) for i in items+net_zones}) != len(items)+len(net_zones):
            raise Unknown("ambiguous_native_conductor_identity")
        if any(t.GetClass() not in ("PCB_TRACK", "PCB_ARC", "PCB_VIA") for t in tracks):
            raise Unknown("unsupported_copper_track_type")
        drilled = {}
        for item in [*pads, *tracks]:
            work.tick()
            if _simple_drill(item, copper):
                key = _key(item)
                if key in drilled:
                    raise Unknown("ambiguous_physical_drill_identity")
                drilled[key] = item
        conn = pcbnew.CONNECTIVITY_DATA()
        for item in items+net_zones:
            work.tick()
            if item.GetClass() == "ZONE" and not item.IsFilled():
                raise Unknown("native_zone_fill_unavailable")
            if not conn.Add(item):
                raise Unknown("native_connectivity_rejected_item")
        reached = {_key(source_pad)} | {_key(i) for i in conn.GetConnectedItems(source_pad)}
        if any(_key(p) not in reached for p in [sense_pad, *authority_pads]):
            raise Unknown("baseline_native_terminal_connectivity_incomplete")
        result["baseline_connected"] = True
        # Native connectivity can treat logical custom-pad islands as one pad.
        # A definite geometric connection BEFORE cutting rules out that
        # additional vacuous-isolation route, including multi-layer SMD pads.
        result["baseline_geometry"] = _model(items, drilled, net_zones, copper, source_pad,
            sense_pad, [*authority_pads, source_pad], False, work, cut_enabled=False)
        expected = {_key(pad) for pad in [*authority_pads, source_pad]}
        import json
        observed = {json.dumps(pad, sort_keys=True) for pad in result["baseline_geometry"]["reached_authority"]}
        if observed != expected:
            raise Unknown("baseline_geometric_terminal_connectivity_unproved")
        result["upper"] = _model(items, drilled, net_zones, copper, source_pad,
                                  sense_pad, authority_pads, True, work)
        result["lower"] = _model(items, drilled, net_zones, copper, source_pad,
                                  sense_pad, authority_pads, False, work)
        _validate_linear_epochs(work)
        result["exact_linear_identity_verified"] = True
        work.tick()
        if not result["upper"]["reached_authority"]:
            if result["lower"]["reached_authority"]:
                raise Unknown("inconsistent_native_polygon_bounds")
            result.update(ok=True, reason="isolated_in_upper_copper_model")
        elif result["lower"]["reached_authority"]:
            result.update(ok=False, reason="bypass_in_lower_copper_model", physical_bypass_proved=True)
        else:
            result["reason"] = "polygon_bounds_or_barrel_connectivity_inconclusive"
        result["complete"] = True
    except Unknown as exc:
        result["reason"] = str(exc)
    except Exception as exc:
        result.update(reason="native_copper_cut_failure", error=repr(exc))
    result.update(elapsed_s=round(time.monotonic()-start, 6),
                  vertices_examined=work.vertices, contacts_examined=work.contacts,
                  exact_linear_refinements=list(work.linear_certificates.values()))
    return result
