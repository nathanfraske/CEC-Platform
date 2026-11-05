"""Explicitly owned native rectilinear conductor proposals and fill receiving.

This owner is separate from ordinary signal polish and additive force routing.
It covers a declared set of Manhattan or exactly 45-degree PCB_TRACK capsules with a solid native
square or 45-degree chamfered zone. Explicit source retention keeps the real
rated track in place for downstream default current checks. Optional retirement
requires separately replayed resident-subset evidence. Ends preserve extents;
they are NOT a license to trim a pad landing or reduce a current-width floor.
Only native saved/refilled enclosure can prove no old conductor was lost.

No ampacity, via sharing, thermal qualification, DRC waiver or release authority
is inferred. Full-board current, field, pair, Kelvin, fabrication, source-family
and ownership receiving must still be done independently by the caller.
"""
from __future__ import annotations

import hashlib
import json
import math
import time

SCHEMA = 2
ZONE_NAME = "CEC_RECTILINEAR_POWER_CONTOUR"
SCOPE = "owned_native_conductor_envelope_not_new_current_or_release_authority"


class Refused(ValueError):
    pass


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True,
        separators=(",", ":")).encode()).hexdigest()


def _track_row(item):
    a, b = item.GetStart(), item.GetEnd()
    return dict(uuid=item.m_Uuid.AsString(), kind=item.GetClass(),
        net=item.GetNetname(), layer_id=int(item.GetLayer()),
        width_nm=int(item.GetWidth()), start_nm=[int(a.x), int(a.y)],
        end_nm=[int(b.x), int(b.y)], locked=bool(item.IsLocked()),
        group_uuid=_group_uuid(item))


def _group_uuid(item):
    # KiCad 10 GetParentGroup returns an EDA_GROUP base proxy without m_Uuid.
    # Resolve exact membership in the board's native PCB_GROUP registry; names
    # and borrowed proxy addresses are not durable ownership identities.
    if item.GetParentGroup() is None:
        return None
    groups = [g for g in item.GetBoard().Groups() if g.ContainsItem(item)]
    if len(groups) != 1:
        raise Refused("ambiguous_native_parent_group")
    return groups[0].m_Uuid.AsString()


def _check_deadline(deadline):
    if time.monotonic() >= deadline:
        raise Refused("rectilinear_owner_deadline")


def _centerline_allowed(a, b, style):
    return a != b and (a[0] == b[0] or a[1] == b[1]
        or style == "chamfer45" and abs(a[0]-b[0]) == abs(a[1]-b[1]))


def _source_centerline_allowed(a,b,style,quantum_nm=0):
    """Input-only quantization, never a new-route or clearance tolerance.

    No source point moves. The explicit native one-nanometre quantum only
    permits building a strictly canonical cover; saved real fills must then
    enclose the entire original capsule, independently of retained material.
    """
    if _centerline_allowed(a,b,style):return True
    dx,dy=abs(a[0]-b[0]),abs(a[1]-b[1])
    return quantum_nm==1 and style=='chamfer45' and min(dx,dy)>1 and abs(dx-dy)==1


def _native_capsule(item, *, max_vertices=200_000):
    import pcbnew
    if item.GetClass() != "PCB_TRACK":
        raise Refused("only_straight_native_tracks_supported")
    shape = pcbnew.SHAPE_POLY_SET()
    item.TransformShapeToPolygon(shape, item.GetLayer(), 0, 1,
                                  pcbnew.ERROR_OUTSIDE, False)
    if shape.OutlineCount() != 1 or shape.HoleCount(0):
        raise Refused("unsupported_native_capsule")
    ring = shape.Outline(0)
    if ring.ArcCount() or not 3 <= ring.PointCount() <= max_vertices:
        raise Refused("native_capsule_vertex_or_arc_bound")
    return shape


def _poly(points):
    import pcbnew
    shape = pcbnew.SHAPE_POLY_SET()
    shape.NewOutline()
    for x, y in points:
        shape.Append(int(x), int(y))
    return shape


def purposeful_envelope(native, *, style="chamfer45", margin_nm=1000, grid_nm=1):
    """Integer square/eight-direction cover of actual native copper.

    Diagonal support planes are at exactly 45 degrees. They are measured
    from every source vertex, not guessed from a radius or a raster mask.
    This is an OUTER cover: it never trims the source capsule/landing.
    """
    from shapely.geometry import Polygon
    if (style not in ("square", "chamfer45") or type(margin_nm) is not int or not 1 <= margin_nm <= 100000
            or type(grid_nm) is not int or not 1<=grid_nm<=100000):
        raise Refused("invalid_purposeful_envelope_policy")
    if native.OutlineCount() != 1 or native.HoleCount(0):
        raise Refused("simple_landing_envelope_required")
    ring = native.Outline(0)
    if ring.ArcCount() or not 3 <= ring.PointCount() <= 200000:
        raise Refused("landing_envelope_vertex_or_arc_bound")
    source = [(int(ring.CPoint(i).x), int(ring.CPoint(i).y)) for i in range(ring.PointCount())]
    def down(v):return v//grid_nm*grid_nm
    def up(v):return -(-v//grid_nm)*grid_nm
    # Only new outer support planes are quantized, always OUTWARDS. Original
    # pads, tracks, widths and source evidence are never snapped or narrowed.
    x0, x1 = down(min(p[0] for p in source)-margin_nm), up(max(p[0] for p in source)+margin_nm)
    y0, y1 = down(min(p[1] for p in source)-margin_nm), up(max(p[1] for p in source)+margin_nm)
    if style == "square":
        points = [(x0,y0),(x1,y0),(x1,y1),(x0,y1)]
    else:
        s0, s1 = down(min(x+y for x,y in source)-2*margin_nm), up(max(x+y for x,y in source)+2*margin_nm)
        d0, d1 = down(min(x-y for x,y in source)-2*margin_nm), up(max(x-y for x,y in source)+2*margin_nm)
        points = [(s0-y0,y0),(d1+y0,y0),(x1,x1-d1),(x1,s1-x1),
                  (s1-y1,y1),(d0+y1,y1),(x0,x0-d0),(x0,s0-x0)]
        # Adjacent diagonal support faces can overlap on arbitrary thin shapes.
        # Those are not landing envelopes and must not be silently snapped.
        if any(not x0 <= x <= x1 or not y0 <= y <= y1 for x,y in points):
            raise Refused("overlapping_chamfer_support_planes")
        points = [p for i,p in enumerate(points) if p != points[i-1]]
    shape = Polygon(points)
    if not shape.is_valid or not shape.equals(shape.convex_hull) or shape.area <= 0:
        raise Refused("invalid_purposeful_envelope")
    points = [list(p) for p in points]
    if any(abs(v)>2000000000 for p in points for v in p):
        raise Refused("native_coordinate_bound")
    missing = native.CloneDropTriangulation()
    missing.BooleanSubtract(_poly(points))
    if missing.OutlineCount():
        raise Refused("purposeful_envelope_loses_native_copper")
    return points


def _shape_identity(shape, deadline, *, max_vertices=200_000):
    """Integer native polygon identity, independent of ring start/direction.

    No triangulation, approximate area or floating-coordinate comparison is
    authority. Unsupported arcs and bounded-out inventories remain unknown.
    """
    polygons, vertices = [], 0
    for i in range(shape.OutlineCount()):
        rings = []
        for ring in [shape.Outline(i), *[shape.Hole(i,j) for j in range(shape.HoleCount(i))]]:
            _check_deadline(deadline)
            size = ring.PointCount()
            vertices += size
            if ring.ArcCount() or size < 3 or vertices > max_vertices:
                raise Refused("supporting_native_polygon_vertex_or_arc_bound")
            points = [(int(ring.CPoint(k).x), int(ring.CPoint(k).y)) for k in range(size)]
            if len(set(points)) != size:
                raise Refused("unsupported_supporting_native_ring")
            anchor = min(range(size), key=points.__getitem__)
            forward = points[anchor:]+points[:anchor]
            reverse = [forward[0], *reversed(forward[1:])]
            rings.append(min(forward, reverse))
        polygons.append([rings[0], *sorted(rings[1:])])
    _check_deadline(deadline)
    return _digest(sorted(polygons)), vertices


def _validated_native_fill_identity(shape, deadline, *, max_vertices=200_000):
    """Accept native hole bridges only with exact topology and zero set change.

    Authored outlines still use the strict simple-ring identity. A saved fill
    can encode its real holes with repeated bridge vertices; that is not a
    license to buffer, simplify or discard a boundary. Validate a PRIVATE
    exact-edge decoding per DECLARED positive polygon, then hash the literal
    complete representation. Separate source polygons can overlap or share
    edges: their repeated edges are not a self-intersection within one ring.
    No polygon is deduplicated or ignored, including an island inside another
    polygon's hole. The actual source fill and collision operations stay put.
    """
    try:
        return _shape_identity(shape, deadline, max_vertices=max_vertices)
    except Refused as exc:
        if str(exc) != "unsupported_supporting_native_ring":
            raise
    import pcbnew
    from cec_native_fill_geometry import decode_exact_hole_boundaries, identity, snapshot
    polygons = snapshot(shape, deadline, max_vertices=max_vertices)
    for index, polygon in enumerate(polygons):
        _check_deadline(deadline)
        part = pcbnew.SHAPE_POLY_SET()
        part.AddOutline(shape.Outline(index))
        for hole in range(shape.HoleCount(index)):
            part.AddHole(shape.Hole(index, hole), 0)
        # Copy literal native chains, not point-by-point Append (which can
        # silently coalesce a malformed zero edge). Prove the copy before
        # validating it; source rings never pass through make-valid/buffer.
        if snapshot(part, deadline, max_vertices=max_vertices, max_polygons=1) != [polygon]:
            raise Refused("native_fill_positive_polygon_copy_changed")
        try:
            _shape_identity(part, deadline, max_vertices=max_vertices)
        except Refused as exc:
            if str(exc) != "unsupported_supporting_native_ring":
                raise
            decoded, proof = decode_exact_hole_boundaries(
                part, deadline, max_vertices=max_vertices)
            if not (proof["zero_native_loss"] and proof["zero_native_spill"]
                    and proof["exact_native_directed_edges_preserved"]):
                raise Refused("native_fill_bridge_topology_or_set_change")
            _shape_identity(decoded, deadline, max_vertices=max_vertices)
    return identity(shape, deadline, max_vertices=max_vertices)


def _fill_envelope(points, *, style, margin_nm):
    if type(margin_nm) is not int or not 1 <= margin_nm <= 10:
        raise Refused("invalid_actual_fill_envelope_bound")
    return _outer_envelope(points, style=style, margin_nm=margin_nm)


def _outer_envelope(points, *, style, margin_nm):
    """Declared integer fill domain, without filling a corridor's empty corner.

    Convex profiles retain the existing support-plane construction. For a
    concave corridor, use its exact square Minkowski construction: the source
    polygon plus each edge swept by the bounded integer margin. This is a
    construction domain declared before filling, never a copper-loss tolerance
    or a convex hull across component space. Fractional intersections refuse.
    """
    from shapely.geometry import MultiPoint, Polygon
    from shapely.ops import unary_union
    if type(margin_nm) is not int or not 1 <= margin_nm <= 100000:
        raise Refused("invalid_declared_outer_envelope_bound")
    source = Polygon(points)
    if not source.is_valid or source.interiors or source.area <= 0:
        raise Refused("simple_native_fill_profile_required")
    if source.equals(source.convex_hull):
        return purposeful_envelope(_poly(points), style=style, margin_nm=margin_nm)
    pieces = [source]
    offsets = ((-margin_nm, -margin_nm), (-margin_nm, margin_nm),
               (margin_nm, margin_nm), (margin_nm, -margin_nm))
    for a, b in zip(points, points[1:]+points[:1]):
        pieces.append(MultiPoint([(p[0]+dx, p[1]+dy)
            for p in (a, b) for dx, dy in offsets]).convex_hull)
    domain = unary_union(pieces)
    if not isinstance(domain, Polygon) or not domain.is_valid or domain.interiors:
        raise Refused("unsupported_native_fill_envelope_union")
    ring = list(domain.exterior.coords)[:-1]
    if len(ring) > 4096 or any(v != int(v) for p in ring for v in p):
        raise Refused("non_integer_native_fill_envelope")
    result = [[int(x), int(y)] for x, y in ring]
    if any(a == b or (a[0] != b[0] and a[1] != b[1]
            and (style != "chamfer45" or abs(a[0]-b[0]) != abs(a[1]-b[1])))
            for a, b in zip(result, result[1:]+result[:1])):
        raise Refused("noncanonical_native_fill_envelope")
    if any(abs(v) > 2_000_000_000 for p in result for v in p):
        raise Refused("native_coordinate_bound")
    missing = _poly(points); missing.BooleanSubtract(_poly(result))
    if missing.OutlineCount():
        raise Refused("native_fill_envelope_loses_profile")
    return result


def _support_row(zone, layer, deadline, *, max_vertices=200_000,allow_native_hole_bridges=False):
    if zone.GetIsRuleArea() or not zone.IsFilled() or not zone.HasFilledPolysForLayer(layer):
        raise Refused("supporting_native_zone_not_filled")
    outline, a = _shape_identity(zone.Outline(), deadline, max_vertices=max_vertices)
    if type(allow_native_hole_bridges) is not bool:
        raise Refused('explicit_native_support_identity_policy_required')
    if allow_native_hole_bridges:
        from cec_native_fill_geometry import identity
        fill,b=identity(zone.GetFilledPolysList(layer),deadline,max_vertices=max_vertices-a)
    else:
        fill,b=_validated_native_fill_identity(zone.GetFilledPolysList(layer),deadline,max_vertices=max_vertices-a)
    return dict(uuid=zone.m_Uuid.AsString(), net=zone.GetNetname(), layer_id=layer,
        priority=int(zone.GetAssignedPriority()), outline_sha256=outline, fill_sha256=fill,
        native_vertices=a+b)


def _receive_support(board, proposal, deadline, *, max_vertices=200_000):
    rows = proposal["supporting_zones"]
    zones = {z.m_Uuid.AsString(): z for z in board.Zones()}
    vertices, received = 0, []
    for row in rows:
        _check_deadline(deadline)
        z = zones.get(row["uuid"])
        if z is None or not z.IsOnLayer(proposal["layer_id"]) or z.GetNetname()!=proposal["net"]:
            raise Refused("supporting_native_zone_identity_changed")
        actual = _support_row(z, proposal["layer_id"], deadline, max_vertices=max_vertices-vertices,
            allow_native_hole_bridges=proposal.get('allow_signed_native_keeper',False))
        if actual != row:
            raise Refused("supporting_native_zone_copper_changed")
        vertices += actual["native_vertices"]
        received.append(z)
    return received, vertices


def _require_unoccupied_outline(board, profile, net, layer, deadline, *, clearance_nm=0,
                                allow_native_hole_bridges=False):
    """No foreign native copper inside a newly reserved pour outline.

    Unlike a fill test, this catches a foreign pad in a square corner which the
    filler would simply void. Use the same native effective-shape collision
    semantics as the existing laid-pour gate, with a bounded inventory and no
    temporary board mutation. This owner conservatively applies it to all
    selected copper layers; it does not guess a plane-role exception.
    """
    items = [*board.GetTracks(), *[p for fp in board.GetFootprints() for p in fp.Pads()]]
    if len(items)>16384:
        raise Refused("native_obstacle_inventory_bound")
    for item in items:
        _check_deadline(deadline)
        if item.GetNetname()==net or not item.IsOnLayer(layer):
            continue
        if profile.Collide(item.GetEffectiveShape(layer), clearance_nm):
            raise Refused("foreign_native_copper_inside_proposed_outline: "
                + item.m_Uuid.AsString()+" "+item.GetClass()+" "+item.GetNetname())
    zones = list(board.Zones())
    if len(zones) > 8192:
        raise Refused("native_obstacle_zone_inventory_bound")
    for zone in zones:
        _check_deadline(deadline)
        if zone.GetIsRuleArea() or zone.GetNetname() == net or not zone.IsOnLayer(layer):
            continue
        if not zone.IsFilled() or not zone.HasFilledPolysForLayer(layer):
            raise Refused("foreign_native_zone_fill_unknown")
        if allow_native_hole_bridges:
            from cec_native_fill_geometry import identity
            identity(zone.GetFilledPolysList(layer), deadline)
        else:
            _validated_native_fill_identity(zone.GetFilledPolysList(layer), deadline)
        if clearance_nm and profile.Collide(zone.GetFilledPolysList(layer), clearance_nm):
            raise Refused("foreign_native_zone_inside_proposed_clearance:"+zone.m_Uuid.AsString())
        overlap = profile.CloneDropTriangulation()
        overlap.BooleanIntersection(zone.GetFilledPolysList(layer))
        if overlap.OutlineCount():
            raise Refused("foreign_native_zone_inside_proposed_outline:"+zone.m_Uuid.AsString())


def _canonical_jog_cover(board, points, net, layer, *, style, max_jog_nm,
                         clearance_nm, deadline, allow_native_hole_bridges=False):
    """Close only bounded additive 0/45/90 kinks, preserving large pockets.

    Intersections are exact integer support lines, never raster smoothing.
    Each closure must reduce the native ring, fit its local displacement and
    area bounds, lose zero copper, and clear actual foreign native material.
    Unsupported or occupied choices stay unchanged; expiry remains unknown.
    """
    from shapely.geometry import Polygon
    if (type(max_jog_nm) is not int or not 0<=max_jog_nm<=1_000_000
            or style not in ('square','chamfer45')):
        raise Refused('invalid_canonical_jog_policy')
    points=[list(p) for p in points]
    if not max_jog_nm:return points
    def compact(ring):
        # Polygon unions insert collinear intersection vertices. They are not
        # physical corners, but can hide a four-edge kink from a local menu.
        for _ in range(len(ring)):
            remove=set()
            for i,b in enumerate(ring):
                a,c=ring[i-1],ring[(i+1)%len(ring)]
                u=[b[k]-a[k] for k in (0,1)];v=[c[k]-b[k] for k in (0,1)]
                if u[0]*v[1]==u[1]*v[0] and sum(u[k]*v[k] for k in (0,1))>0:
                    remove.add(i)
            if not remove:break
            ring=[p for i,p in enumerate(ring) if i not in remove]
        return ring
    points=compact(points)
    shape=Polygon(points)
    if not shape.is_valid or shape.interiors or shape.area<=0:
        raise Refused('simple_canonical_jog_source_required')
    def canonical(ring):
        return all(_centerline_allowed(a,b,style)
                   for a,b in zip(ring,ring[1:]+ring[:1]))
    if not canonical(points):raise Refused('canonical_jog_source_required')
    def cross(a,b):return a[0]*b[1]-a[1]*b[0]
    for _ in range(min(128,len(points))):
        _check_deadline(deadline)
        if len(points)<=4:break
        choices=[]
        for i in range(len(points)):
            _check_deadline(deadline)
            a,b,c,d=[points[(i+k)%len(points)] for k in range(4)]
            v=[b[k]-a[k] for k in (0,1)];w=[d[k]-c[k] for k in (0,1)]
            # An authored long notch is never a "small" edge artifact.
            if max(abs(c[k]-b[k]) for k in (0,1))>max_jog_nm:continue
            corners=[[a[0],d[1]],[d[0],a[1]]]
            det=cross(v,w)
            if det:
                num=cross([c[k]-a[k] for k in (0,1)],w)
                coords=[a[k]*det+v[k]*num for k in (0,1)]
                if all(q%det==0 for q in coords):
                    corners.append([q//det for q in coords])
            for corner in sorted(set(map(tuple,corners))):
                if max(abs(corner[k]-p[k]) for p in (b,c) for k in (0,1))>max_jog_nm:
                    continue
                rotated=points[i:]+points[:i]
                trial=[a,list(corner),d]+rotated[4:]
                trial=compact([p for k,p in enumerate(trial) if p!=trial[k-1]])
                if len(trial)<4 or not canonical(trial):continue
                candidate=Polygon(trial);added_area=candidate.area-shape.area
                if (not candidate.is_valid or candidate.interiors
                        or not 0<added_area<=max_jog_nm*max_jog_nm
                        or not candidate.covers(shape)):
                    continue
                lost=_poly(points);lost.BooleanSubtract(_poly(trial))
                if lost.OutlineCount():continue
                addition=_poly(trial);addition.BooleanSubtract(_poly(points))
                try:
                    _require_unoccupied_outline(board,addition,net,layer,deadline,
                        clearance_nm=clearance_nm,allow_native_hole_bridges=allow_native_hole_bridges)
                except Refused as exc:
                    _check_deadline(deadline)
                    if not str(exc).startswith('foreign_native_'):raise
                    continue
                choices.append((added_area,trial))
        if not choices:break
        _,points=min(choices,key=lambda row:(row[0],row[1]))
        shape=Polygon(points)
    return points


def _landing_envelope(board, zone, layer, *, style, margin_nm, grid_nm,
                      mode, max_jog_nm, deadline, allow_native_hole_bridges=False):
    """Native landing cover, never an arbitrary polygon supplied by the caller.

    Convex covers remain the default. Canonical native outlines keep their
    concavities; optional small step closures only ADD copper, are bounded by
    feature size and area, and must respect the selected zone's actual foreign
    copper clearance. No coordinates, component names or new current estimate
    are used. The unchanged native filled source is independently bound too.
    """
    from shapely.geometry import Polygon
    if mode == "convex_fill":
        return purposeful_envelope(zone.GetFilledPolysList(layer), style=style,
            margin_nm=margin_nm, grid_nm=grid_nm)
    native = zone.Outline()
    if native.OutlineCount() != 1 or native.HoleCount(0):
        raise Refused("simple_canonical_landing_outline_required")
    ring = native.Outline(0)
    if ring.ArcCount() or not 4 <= ring.PointCount() <= 1024:
        raise Refused("canonical_landing_outline_vertex_or_arc_bound")
    points = [[int(ring.CPoint(i).x), int(ring.CPoint(i).y)]
              for i in range(ring.PointCount())]
    if any(a == b or (a[0] != b[0] and a[1] != b[1]
            and (style != "chamfer45" or abs(a[0]-b[0]) != abs(a[1]-b[1])))
            for a, b in zip(points, points[1:]+points[:1])):
        raise Refused("canonical_native_landing_outline_required")
    shape = Polygon(points)
    if not shape.is_valid or shape.interiors or shape.area <= 0:
        raise Refused("simple_canonical_landing_outline_required")
    points=_canonical_jog_cover(board,points,zone.GetNetname(),layer,style=style,
        max_jog_nm=max_jog_nm,clearance_nm=int(zone.GetLocalClearance()),deadline=deadline,
        allow_native_hole_bridges=allow_native_hole_bridges)
    # Native saved fill may lie one nanometre beyond an authored diagonal
    # after integer shrink/expand. This is ACTUAL added construction margin,
    # not permission to omit an incumbent sliver or spill beyond the profile.
    return _outer_envelope(points,style=style,margin_nm=margin_nm)


def _require_same_net_priority_available(board, profile, net, layer, deadline, *, own_zone_uuid=None, priority=0):
    """Do not hide a needed native zone consolidation behind a new overlay.

    Same-priority overlapping same-net zones are a native DRC error. This
    additive owner has no authority to renumber or retire an existing owner.
    Detect the conflict before filling or running expensive board receiving.
    """
    zones = list(board.Zones())
    if len(zones) > 8192:
        raise Refused('native_zone_inventory_bound')
    for zone in zones:
        _check_deadline(deadline)
        if (zone.GetIsRuleArea() or zone.GetNetname() != net or not zone.IsOnLayer(layer)
                or zone.GetAssignedPriority() != priority or zone.m_Uuid.AsString() == own_zone_uuid):
            continue
        _shape_identity(zone.Outline(), deadline)
        overlap = profile.CloneDropTriangulation(); overlap.BooleanIntersection(zone.Outline())
        if overlap.OutlineCount():
            raise Refused('same_priority_native_zone_requires_consolidation:'+zone.m_Uuid.AsString())


def _enclosed_native_track_ids(board, outline, net, layer, deadline):
    """Bounded actual stroke inventory inside an immutable owned outline."""
    enclosed=set();seen=set()
    for track in board.GetTracks():
        _check_deadline(deadline)
        uid=track.m_Uuid.AsString()
        if uid in seen:raise Refused('ambiguous_native_track_identity')
        seen.add(uid)
        if len(seen)>8192:raise Refused('native_track_inventory_bound')
        if (track.GetClass()!='PCB_TRACK' or track.GetNetname()!=net
                or not track.IsOnLayer(layer)):continue
        missing=_native_capsule(track);missing.BooleanSubtract(outline)
        if not missing.OutlineCount():enclosed.add(uid)
    return enclosed


def _derived_profile(board, proposal, deadline):
    """Reconstruct the declaration from native strokes and bound native zones.

    Used independently by both construction and saved receiving: a rehashed
    wider profile, or an old ok flag, is not evidence for a new copper slab.
    """
    import pcbnew
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    style=proposal.get('contour_style','square');grid=proposal.get('contour_grid_nm',1)
    margin=proposal['envelope_margin_nm'];combined=pcbnew.SHAPE_POLY_SET();pieces=[]
    net=board.FindNet(proposal['net'])
    if net is None or net.GetNetCode() <= 0:
        raise Refused('native_net_identity_unavailable')
    vertices=0
    for row in proposal['source_tracks']:
        _check_deadline(deadline)
        if (not _source_centerline_allowed(row['start_nm'],row['end_nm'],style,
                proposal.get('source_diagonal_quantum_nm',0))
                or row['width_nm'] < proposal['required_width_nm']):
            raise Refused('native_declared_conductor_policy_changed')
        ghost=pcbnew.PCB_TRACK(board);ghost.SetNet(net);ghost.SetLayer(row['layer_id'])
        ghost.SetWidth(row['width_nm']);ghost.SetStart(pcbnew.VECTOR2I(*row['start_nm']))
        ghost.SetEnd(pcbnew.VECTOR2I(*row['end_nm']))
        cap=_native_capsule(ghost);vertices+=cap.Outline(0).PointCount()
        if vertices > 200000:raise Refused('native_capsule_total_vertex_bound')
        pieces.append(Polygon(purposeful_envelope(cap,style=style,margin_nm=margin,grid_nm=grid)))
        if proposal.get('convex_support_cover',False):combined.BooleanAdd(cap)
    zones_by_id={z.m_Uuid.AsString():z for z in board.Zones()}
    keeper_id=(proposal.get('replacement_source_zone') or {}).get('configuration',{}).get('uuid')
    if proposal.get('rebuild_keeper_from_tracks',False):
        old_owner=_source_zone_proxy(board,proposal['replacement_source_zone'])
        enclosed=_enclosed_native_track_ids(board,old_owner.Outline(),proposal['net'],
            proposal['layer_id'],deadline)
        if enclosed!={r['uuid'] for r in proposal['source_tracks']}:
            raise Refused('keeper_recompile_native_track_inventory_changed')
    for uid in proposal.get('enclosing_native_zone_uuids',[]):
        if proposal.get('rebuild_keeper_from_tracks',False) and uid==keeper_id:continue
        _check_deadline(deadline)
        zone=zones_by_id.get(uid)
        if zone is None:raise Refused('native_landing_enclosure_identity_unavailable')
        replacement=proposal.get('replacement_source_zone')
        if replacement and replacement['configuration']['uuid']==uid:
            # Saved receiving must derive the profile from the immutable OLD
            # native owner, not the already reauthored candidate outline.
            zone=_source_zone_proxy(board,replacement)
        pieces.append(Polygon(_landing_envelope(board,zone,proposal['layer_id'],
            style=style,margin_nm=margin,grid_nm=grid,
            mode=proposal.get('landing_enclosure_mode','convex_fill'),
            max_jog_nm=proposal.get('landing_max_jog_nm',0),deadline=deadline,
            allow_native_hole_bridges=proposal.get('allow_signed_native_keeper',False))))
        if proposal.get('convex_support_cover',False):
            combined.BooleanAdd(zone.GetFilledPolysList(proposal['layer_id']))
    if proposal.get('convex_support_cover',False):
        return purposeful_envelope(combined,style=style,margin_nm=margin,grid_nm=grid)
    shape=unary_union(pieces)
    if not isinstance(shape,Polygon) or not shape.is_valid or shape.interiors:
        raise Refused('native_landing_union_not_connected_and_simple')
    ring=list(shape.exterior.coords)[:-1]
    if len(ring)>1024 or any(v!=int(v) for point in ring for v in point):
        raise Refused('native_landing_union_not_integer')
    return _canonical_jog_cover(board,[[int(x),int(y)] for x,y in ring],proposal['net'],
        proposal['layer_id'],style=style,max_jog_nm=proposal.get('contour_max_jog_nm',0),
        clearance_nm=proposal['clearance_nm'],deadline=deadline,
        allow_native_hole_bridges=proposal.get('allow_signed_native_keeper',False))


def _source_zone_proxy(board, source):
    """Geometry-only native proxy; not added, not capacity or source authority."""
    import pcbnew
    c=source['configuration'];z=pcbnew.ZONE(board);z.SetNet(board.FindNet(c['net']))
    z.SetLayer(c['layers'][0]);z.SetLocalClearance(c['clearance_nm'])
    z.SetMinThickness(c['min_thickness_nm']);z.SetAssignedPriority(c['priority'])
    z.Outline().NewOutline()
    for x,y in source['outline_nm']:z.Outline().Append(x,y)
    from cec_native_fill_geometry import source_fill
    z.SetFilledPolysList(c['layers'][0],source_fill(source,time.monotonic()+2));z.SetIsFilled(True)
    return z


def plan_width_recompile(board,track_uuids,*,required_width_nm,allow_locked_track_uuids=(),
        allow_grouped_track_uuids=()):
    """Explicit owned native widening, distinct from preserving an old width.

    The caller must compile the existing current/role/layer dimensional floor.
    Only width can increase: identity, endpoints, net, layer, locks and groups
    remain exact. No rating or neckdown authority is granted by this proposal.
    """
    import pcbnew
    if type(required_width_nm) is not int or not 1<=required_width_nm<=100000000:
        raise Refused("invalid_existing_width_recompile_contract")
    wanted=list(track_uuids)
    if not 1<=len(wanted)<=64 or len(set(wanted))!=len(wanted):
        raise Refused("bounded_unique_width_owner_inventory_required")
    native={t.m_Uuid.AsString():t for t in board.GetTracks()}
    if not set(wanted)<=native.keys():raise Refused("width_owner_source_missing")
    rows=[]
    for uid in sorted(wanted):
        item=native[uid]
        if item.GetClass()!="PCB_TRACK":raise Refused("straight_width_owner_required")
        row=_track_row(item)
        if (not _centerline_allowed(row["start_nm"],row["end_nm"],"chamfer45")
                or row["locked"] and uid not in set(allow_locked_track_uuids)
                or row["group_uuid"] and uid not in set(allow_grouped_track_uuids)):
            raise Refused("explicit_octilinear_width_lock_group_owner_required")
        target=max(row["width_nm"],required_width_nm)
        prototype=pcbnew.PCB_TRACK(board);prototype.SetNet(item.GetNet())
        prototype.SetLayer(item.GetLayer());prototype.SetStart(item.GetStart())
        prototype.SetEnd(item.GetEnd());prototype.SetWidth(target)
        _require_unoccupied_outline(board,_native_capsule(prototype),row["net"],row["layer_id"],time.monotonic()+2)
        missing=_native_capsule(item);missing.BooleanSubtract(_native_capsule(prototype))
        if missing.OutlineCount():raise Refused("width_recompile_loses_source_copper")
        rows.append(dict(source_track=row,target_width_nm=target))
    if len({(r["source_track"]["net"],r["source_track"]["layer_id"]) for r in rows})!=1:
        raise Refused("one_width_domain_and_layer_required")
    result=dict(schema=1,scope="owned_width_only_recompile_not_current_qualification",
        rows=rows,required_width_nm=required_width_nm,new_capacity_credited=False,release_authority=False)
    result["plan_sha256"]=_digest(result)
    return result


def materialize_width_recompile(board,proposal,*,allow_locked_track_uuids=(),allow_grouped_track_uuids=()):
    p=dict(proposal);digest=p.pop("plan_sha256",None)
    if digest!=_digest(p):raise Refused("width_recompile_plan_identity_changed")
    expected=plan_width_recompile(board,[r["source_track"]["uuid"] for r in p["rows"]],
        required_width_nm=p["required_width_nm"],allow_locked_track_uuids=allow_locked_track_uuids,
        allow_grouped_track_uuids=allow_grouped_track_uuids)
    if expected!=proposal:raise Refused("width_recompile_source_or_geometry_changed")
    tracks={t.m_Uuid.AsString():t for t in board.GetTracks()}
    for row in p["rows"]:tracks[row["source_track"]["uuid"]].SetWidth(row["target_width_nm"])
    return dict(modified_track_uuids=[r["source_track"]["uuid"] for r in p["rows"]
        if r["target_width_nm"]!=r["source_track"]["width_nm"]],new_capacity_credited=False,release_authority=False)


def receive_width_recompile(board,proposal):
    p=dict(proposal);digest=p.pop("plan_sha256",None)
    if digest!=_digest(p):raise Refused("width_recompile_receiving_identity_changed")
    tracks={t.m_Uuid.AsString():t for t in board.GetTracks()}
    for row in p["rows"]:
        source=row["source_track"];uid=source["uuid"]
        expected=dict(source,width_nm=max(source["width_nm"],p["required_width_nm"]))
        if row["target_width_nm"]!=expected["width_nm"] or uid not in tracks or _track_row(tracks[uid])!=expected:
            raise Refused("saved_width_recompile_not_exact_width_only_change")
    return dict(ok=True,verified_track_count=len(p["rows"]),new_capacity_credited=False,release_authority=False)


def plan_power_link_rebuild(board,track_uuids,*,source_pad_uuid,target_via_uuids,
        required_width_nm,clearance_nm,allow_locked_track_uuids=(),allow_grouped_track_uuids=()):
    """Owned two-segment current link to real native pad/barrel boundaries.

    A bounded 0/45/90 portfolio can replace an invalid free-end landing path.
    The original native tracks/ownership stay; only their width/endpoints may
    recompile. No pad, via, other conductor, current budget or gate changes.
    Independent terminal/current/Kelvin/field/DRC receiving is mandatory.
    """
    import pcbnew
    if (type(required_width_nm) is not int or not 1<=required_width_nm<=100000000
            or type(clearance_nm) is not int or not 0<=clearance_nm<=10000000):
        raise Refused("invalid_power_link_width_or_clearance_authority")
    wanted=list(track_uuids);targets=list(target_via_uuids)
    if len(wanted)!=2 or len(set(wanted))!=2 or not 1<=len(targets)<=25 or len(set(targets))!=len(targets):
        raise Refused("bounded_two_segment_link_and_barrel_boundary_required")
    tracks={t.m_Uuid.AsString():t for t in board.GetTracks()}
    pads={p.m_Uuid.AsString():p for fp in board.GetFootprints() for p in fp.Pads()}
    if not set(wanted+targets)<=tracks.keys() or source_pad_uuid not in pads:
        raise Refused("power_link_native_boundary_missing")
    rows=[_track_row(tracks[u]) for u in sorted(wanted)]
    if (any(r['kind']!='PCB_TRACK' for r in rows)
            or len({(r['net'],r['layer_id']) for r in rows})!=1
            or any(r['locked'] and r['uuid'] not in set(allow_locked_track_uuids)
                or r['group_uuid'] and r['uuid'] not in set(allow_grouped_track_uuids) for r in rows)):
        raise Refused("explicit_same_domain_power_link_owner_required")
    net,layer=rows[0]['net'],rows[0]['layer_id'];source=pads[source_pad_uuid]
    shared={tuple(rows[0]['start_nm']),tuple(rows[0]['end_nm'])}&{tuple(rows[1]['start_nm']),tuple(rows[1]['end_nm'])}
    if (len(shared)!=1 or any(not _centerline_allowed(r['start_nm'],r['end_nm'],'chamfer45')
            or r['width_nm']<=0 for r in rows)):
        raise Refused('one_connected_canonical_owned_link_required')
    if not net or source.GetNetname()!=net or not source.IsOnLayer(layer):
        raise Refused("power_link_actual_same_net_source_pad_required")
    start=[source.GetPosition().x,source.GetPosition().y]
    if tuple(start) in shared or not any(start in (r['start_nm'],r['end_nm']) for r in rows):
        raise Refused("source_pad_not_boundary_of_owned_link")
    target_width=max(required_width_nm,*(r['width_nm'] for r in rows))
    from cec_via_field_layout import _via_row
    ends=[]
    for uid in targets:
        via=tracks[uid]
        if via.GetClass()!='PCB_VIA' or via.GetNetname()!=net or not via.IsOnLayer(layer):
            raise Refused("power_link_actual_same_net_barrel_required")
        ends.append(_via_row(via))
    attempts=[];options=[];deadline=time.monotonic()+10
    boundaries=[]
    for endpoint in sorted(ends,key=lambda r:(math.dist(start,r['position_nm']),r['uuid'])):
        # A legal landing need not end at a barrel's center. Each alternative
        # must contain the ENTIRE native annulus in its real rated track,
        # rather than touch one pixel or claim a synthetic filled slab.
        reach=max(0,(target_width-endpoint['diameter_nm'])//2-4000)
        x,y=endpoint['position_nm']
        for ox,oy in dict.fromkeys([(0,0),(reach,0),(-reach,0),(0,reach),(0,-reach)]):
            boundaries.append((endpoint,[x+ox,y+oy]))
    for endpoint,end in boundaries:
        dx,dy=end[0]-start[0],end[1]-start[1]
        sx=1 if dx>=0 else -1;sy=1 if dy>=0 else -1;diagonal=min(abs(dx),abs(dy))
        elbows=[(end[0],start[1]),(start[0],end[1]),
            (end[0]-sx*diagonal,start[1]),(start[0],end[1]-sy*diagonal),
            (start[0]+sx*diagonal,end[1]),(end[0],start[1]+sy*diagonal)]
        if abs(dx)==abs(dy):elbows.append(((start[0]+end[0])//2,(start[1]+end[1])//2))
        for mid in dict.fromkeys(elbows):
            _check_deadline(deadline)
            path=[start,list(mid),end]
            if not all(_centerline_allowed(a,b,'chamfer45') for a,b in zip(path,path[1:])):continue
            error=None
            final=pcbnew.PCB_TRACK(board);final.SetNet(source.GetNet());final.SetLayer(layer)
            final.SetStart(pcbnew.VECTOR2I(*path[-2]));final.SetEnd(pcbnew.VECTOR2I(*path[-1]));final.SetWidth(target_width)
            from cec_via_field_layout import _disk
            annulus=_disk(board,net,layer,endpoint['position_nm'],endpoint['diameter_nm'])
            annulus.BooleanSubtract(_native_capsule(final))
            if annulus.OutlineCount():continue
            for a,b in zip(path,path[1:]):
                prototype=pcbnew.PCB_TRACK(board);prototype.SetNet(source.GetNet());prototype.SetLayer(layer)
                prototype.SetStart(pcbnew.VECTOR2I(*a));prototype.SetEnd(pcbnew.VECTOR2I(*b))
                # Reserve the full future chamfer, not merely the centerline.
                prototype.SetWidth(target_width+2*clearance_nm+8000)
                reserved=_poly(purposeful_envelope(_native_capsule(prototype),style='chamfer45',margin_nm=1000,grid_nm=1000))
                try:
                    _require_unoccupied_outline(board,reserved,net,layer,deadline)
                    for z in board.Zones():
                        _check_deadline(deadline)
                        if z.GetIsRuleArea() or z.GetNetname()==net or not z.IsOnLayer(layer):continue
                        if not z.IsFilled() or not z.HasFilledPolysForLayer(layer):
                            raise Refused('foreign_landing_fill_unknown')
                        overlap=reserved.CloneDropTriangulation();overlap.BooleanIntersection(z.GetFilledPolysList(layer))
                        if overlap.OutlineCount():raise Refused('foreign_native_zone_reservation:'+z.m_Uuid.AsString())
                except Refused as exc:error=str(exc);break
            attempts.append(dict(target_via_uuid=endpoint['uuid'],path_nm=path,refused=error))
            if error:continue
            length=sum(math.dist(a,b) for a,b in zip(path,path[1:]))
            options.append((length,sum(a[0]!=b[0] and a[1]!=b[1] for a,b in zip(path,path[1:])),path,endpoint))
    if not options:
        refusal=Refused('no_clear_owned_link_portfolio:'+str([r['refused'] for r in attempts[:8]]))
        refusal.attempts=attempts
        raise refusal
    _,_,path,end=min(options,key=lambda r:(r[0],-r[1],r[2],r[3]['uuid']))
    result=dict(schema=1,source_tracks=rows,source_pad=_link_pad_row(source),
        target_vias=ends,selected_target_via=end,path_nm=path,required_width_nm=required_width_nm,
        target_width_nm=target_width,clearance_nm=clearance_nm,attempts=attempts,
        new_capacity_credited=False,release_authority=False)
    result['plan_sha256']=_digest(result)
    return result


def _link_pad_row(pad):
    return dict(uuid=pad.m_Uuid.AsString(),net=pad.GetNetname(),
        position_nm=[pad.GetPosition().x,pad.GetPosition().y],
        size_nm=[pad.GetSize().x,pad.GetSize().y],shape=int(pad.GetShape()),
        attribute=int(pad.GetAttribute()),orientation_deg=pad.GetOrientationDegrees(),
        layers=[int(v) for v in pad.GetLayerSet().Seq()])


def materialize_power_link_rebuild(board,proposal,*,allow_locked_track_uuids=(),allow_grouped_track_uuids=()):
    p=dict(proposal);digest=p.pop('plan_sha256',None)
    if digest!=_digest(p):raise Refused('owned_power_link_identity_changed')
    actual=plan_power_link_rebuild(board,[r['uuid'] for r in p['source_tracks']],
        source_pad_uuid=p['source_pad']['uuid'],target_via_uuids=[r['uuid'] for r in p['target_vias']],
        required_width_nm=p['required_width_nm'],clearance_nm=p['clearance_nm'],
        allow_locked_track_uuids=allow_locked_track_uuids,allow_grouped_track_uuids=allow_grouped_track_uuids)
    if actual!=proposal:raise Refused('owned_power_link_source_or_plan_changed')
    import pcbnew
    native={t.m_Uuid.AsString():t for t in board.GetTracks()}
    for row,a,b in zip(p['source_tracks'],p['path_nm'],p['path_nm'][1:]):
        track=native[row['uuid']];track.SetStart(pcbnew.VECTOR2I(*a));track.SetEnd(pcbnew.VECTOR2I(*b))
        track.SetWidth(p['target_width_nm'])
    return dict(modified_track_uuids=[r['uuid'] for r in p['source_tracks']],new_capacity_credited=False,release_authority=False)


def receive_power_link_rebuild(board,proposal):
    p=dict(proposal);digest=p.pop('plan_sha256',None)
    if digest!=_digest(p):raise Refused('owned_link_receiving_identity_changed')
    if (len(p['source_tracks'])!=2 or len(p['path_nm'])!=3
            or not all(_centerline_allowed(a,b,'chamfer45') for a,b in zip(p['path_nm'],p['path_nm'][1:]))
            or p['path_nm'][0]!=p['source_pad']['position_nm']
            or p['selected_target_via'] not in p['target_vias']
            or p['target_width_nm']!=max(p['required_width_nm'],*(r['width_nm'] for r in p['source_tracks']))):
        raise Refused('saved_power_link_declared_boundary_or_width_invalid')
    native={t.m_Uuid.AsString():t for t in board.GetTracks()}
    for row,a,b in zip(p['source_tracks'],p['path_nm'],p['path_nm'][1:]):
        expected=dict(row,start_nm=a,end_nm=b,width_nm=p['target_width_nm'])
        if row['uuid'] not in native or _track_row(native[row['uuid']])!=expected:
            raise Refused('saved_owned_power_link_not_exact_declared_recompile')
    from cec_via_field_layout import _via_row
    for row in p['target_vias']:
        if row['uuid'] not in native or _via_row(native[row['uuid']])!=row:
            raise Refused('saved_power_link_barrel_boundary_changed')
    from cec_via_field_layout import _disk
    row=p['selected_target_via']
    last=native[p['source_tracks'][-1]['uuid']]
    annulus=_disk(board,row['net'],int(last.GetLayer()),row['position_nm'],row['diameter_nm'])
    annulus.BooleanSubtract(_native_capsule(last))
    if annulus.OutlineCount():raise Refused('saved_owned_link_does_not_cover_actual_full_annulus')
    pad=next((v for f in board.GetFootprints() for v in f.Pads() if v.m_Uuid.AsString()==p['source_pad']['uuid']),None)
    if pad is None or _link_pad_row(pad)!=p['source_pad']:
        raise Refused('saved_owned_link_source_pad_changed')
    return dict(ok=True,verified_track_count=2,physical_source_pad_preserved=True,
        physical_barrels_preserved=True,new_capacity_credited=False,release_authority=False)


def plan(board, track_uuids, *, clearance_nm, min_thickness_nm,
         required_width_nm, allow_locked_track_uuids=(),
         allow_grouped_track_uuids=(), excluded_nets=(),
         envelope_margin_nm=1000, timeout_s=2.0, max_tracks=64,
         max_vertices=200_000, contour_style="square", contour_grid_nm=1,
         fill_envelope_margin_nm=0, retire_source_tracks=True, convex_support_cover=False,
         enclosing_native_zone_uuids=(), landing_enclosure_mode="convex_fill",
         landing_max_jog_nm=0, replace_native_zone_uuid=None,
         allow_locked_zone_uuids=(), allow_grouped_zone_uuids=(), fill_policy="native",
         contour_max_jog_nm=0, rebuild_keeper_from_tracks=False,
         retain_existing_keeper_lock=False, retain_existing_keeper_group=False,
         retained_native_track_material=False, allow_signed_native_keeper=False,source_diagonal_quantum_nm=0,
         allow_source_solid_keeper=False):
    """Read-only native envelope; unknowns refuse, never snap source copper.

    The explicit required width is the caller's existing dimensional contract,
    not a new current estimate. No selected source width is reduced. A bounded
    positive envelope margin is actual added copper, never an area tolerance.
    By default the enclosing portfolio cannot shrink old cover extents. An
    explicit owned-keeper recompile may discard old excess cover pixels, but
    never alters any declared actual conductor or grants current capacity;
    prior terminal/current/Kelvin connections still need whole-board receiving.
    Explicit source-preserving keeper extension may retain an incumbent
    keeper's own lock independently of the retained tracks' lock bits. Neither
    is changed; exact item permissions and saved-source receiving still apply.
    The separate explicit group-retention mode likewise keeps the old keeper
    group AND each retained track group exact, without reparenting either.
    """
    import pcbnew
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    values = (clearance_nm, min_thickness_nm, required_width_nm, envelope_margin_nm)
    if (any(type(v) is not int for v in values)
            or not 0 <= clearance_nm <= 10_000_000
            or not 1 <= min_thickness_nm <= 1_000_000
            or not 1 <= required_width_nm <= 100_000_000
            or not 1 <= envelope_margin_nm <= 100_000
            or type(max_tracks) is not int or not 1 <= max_tracks <= 128
            or type(max_vertices) is not int or not 32 <= max_vertices <= 200_000
            or type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 <= timeout_s <= 10 or contour_style not in ("square", "chamfer45")
            or type(contour_grid_nm) is not int or not 1<=contour_grid_nm<=100000
            or type(fill_envelope_margin_nm) is not int or not 0<=fill_envelope_margin_nm<=10
            or fill_policy not in ("native", "source_preserving_regions", "conductor_preserving_regions")
            or type(retire_source_tracks) is not bool or type(convex_support_cover) is not bool
            or type(contour_max_jog_nm) is not int or not 0<=contour_max_jog_nm<=1_000_000
            or (contour_max_jog_nm and convex_support_cover)
            or type(rebuild_keeper_from_tracks) is not bool
            or (rebuild_keeper_from_tracks and (replace_native_zone_uuid is None
                or retire_source_tracks or fill_policy not in ('native','conductor_preserving_regions')
                or convex_support_cover))
            or (fill_policy=='conductor_preserving_regions' and not rebuild_keeper_from_tracks)):
        raise Refused("invalid_rectilinear_owner_bounds")
    if (type(retain_existing_keeper_lock) is not bool or retain_existing_keeper_lock and
            (replace_native_zone_uuid is None or retire_source_tracks or rebuild_keeper_from_tracks
             or fill_policy!='source_preserving_regions')):
        raise Refused('explicit_source_retaining_keeper_lock_policy_required')
    if (type(retain_existing_keeper_group) is not bool or retain_existing_keeper_group and
            (replace_native_zone_uuid is None or retire_source_tracks or rebuild_keeper_from_tracks
             or fill_policy!='source_preserving_regions')):
        raise Refused('explicit_source_retaining_keeper_group_policy_required')
    if (type(retained_native_track_material) is not bool or retained_native_track_material and
            (replace_native_zone_uuid is None or retire_source_tracks or rebuild_keeper_from_tracks
             or fill_policy!='source_preserving_regions')):
        raise Refused('explicit_unchanged_native_track_material_policy_required')
    if (type(allow_signed_native_keeper) is not bool or allow_signed_native_keeper and
            (replace_native_zone_uuid is None or retire_source_tracks or rebuild_keeper_from_tracks
             or fill_policy!='source_preserving_regions')):
        raise Refused('explicit_source_retaining_signed_keeper_policy_required')
    if (type(allow_source_solid_keeper) is not bool or allow_source_solid_keeper and
            (replace_native_zone_uuid is None or retire_source_tracks or rebuild_keeper_from_tracks
             or fill_policy!='source_preserving_regions' or not retained_native_track_material
             or not retain_existing_keeper_lock or not retain_existing_keeper_group
             or not allow_signed_native_keeper)):
        raise Refused('source_solid_keeper_requires_literal_source_tracks_fill_process_and_ownership')
    if (type(source_diagonal_quantum_nm) is not int or source_diagonal_quantum_nm not in (0,1)
            or source_diagonal_quantum_nm and (replace_native_zone_uuid is None or retire_source_tracks
                or rebuild_keeper_from_tracks or fill_policy!='source_preserving_regions'
                or contour_style!='chamfer45')):
        raise Refused('explicit_unchanged_native_diagonal_cover_policy_required')
    if not isinstance(track_uuids, (list, tuple, set)):
        raise Refused("explicit_track_uuid_inventory_required")
    wanted = list(track_uuids)
    if not wanted or len(wanted) > max_tracks or len(set(wanted)) != len(wanted):
        raise Refused("invalid_owned_track_inventory")
    if any(not isinstance(u, str) or not u for u in wanted):
        raise Refused("invalid_owned_track_identity")
    if (not isinstance(enclosing_native_zone_uuids, (list, tuple, set))
            or len(enclosing_native_zone_uuids) > 8
            or len(set(enclosing_native_zone_uuids)) != len(enclosing_native_zone_uuids)
            or any(type(u) is not str or not u for u in enclosing_native_zone_uuids)):
        raise Refused("bounded_explicit_native_landing_enclosure_required")
    if (landing_enclosure_mode not in ("convex_fill", "canonical_outline")
            or type(landing_max_jog_nm) is not int or not 0 <= landing_max_jog_nm <= 1_000_000
            or (landing_max_jog_nm and landing_enclosure_mode != "canonical_outline")
            or (not enclosing_native_zone_uuids and (landing_max_jog_nm
                or landing_enclosure_mode != "convex_fill"))
            or (convex_support_cover and landing_enclosure_mode != "convex_fill")):
        raise Refused("invalid_bound_native_landing_policy")
    deadline = time.monotonic() + timeout_s
    _check_deadline(deadline)
    native = {}
    for t in board.GetTracks():
        _check_deadline(deadline)
        uid = t.m_Uuid.AsString()
        if uid in native:
            raise Refused("ambiguous_native_track_identity")
        native[uid] = t
        if len(native) > 8192:
            raise Refused("native_track_inventory_bound")
    if not set(wanted) <= native.keys():
        raise Refused("owned_track_missing")
    locked, grouped = set(allow_locked_track_uuids), set(allow_grouped_track_uuids)
    selected = [native[u] for u in sorted(wanted)]
    if any(t.GetClass() != "PCB_TRACK" for t in selected):
        raise Refused("only_straight_native_tracks_supported")
    rows = [_track_row(t) for t in selected]
    keys = {(r["net"], r["layer_id"]) for r in rows}
    if len(keys) != 1 or not rows[0]["net"]:
        raise Refused("one_actual_net_and_layer_required")
    net, layer = next(iter(keys))
    if net in set(excluded_nets) or net.rsplit("/", 1)[-1] == "GND":
        raise Refused("protected_net_owner_required")
    if layer not in set(board.GetEnabledLayers().CuStack()):
        raise Refused("disabled_copper_layer")
    parents = {r["group_uuid"] for r in rows if r["group_uuid"]}
    if len(parents) > 1:
        raise Refused("multiple_native_groups_require_separate_owners")
    if any(r["locked"] and r["uuid"] not in locked for r in rows):
        raise Refused("locked_track_not_owned")
    if any(r["group_uuid"] and r["uuid"] not in grouped for r in rows):
        raise Refused("grouped_track_not_owned")
    rectangles, vertices = [], 0
    combined_capsules=pcbnew.SHAPE_POLY_SET()
    for t, r in zip(selected, rows):
        _check_deadline(deadline)
        a, b = r["start_nm"], r["end_nm"]
        if not _source_centerline_allowed(a,b,contour_style,source_diagonal_quantum_nm):
            raise Refused("native_manhattan_centerline_required")
        if r["width_nm"] < required_width_nm:
            raise Refused("existing_track_below_current_width_contract")
        if min_thickness_nm >= r["width_nm"]:
            raise Refused("zone_feature_floor_not_below_conductor_width")
        cap = _native_capsule(t, max_vertices=max_vertices)
        ring = cap.Outline(0)
        vertices += ring.PointCount()
        if vertices > max_vertices:
            raise Refused("native_capsule_total_vertex_bound")
        rectangles.append(Polygon(purposeful_envelope(cap, style=contour_style,
            margin_nm=envelope_margin_nm,grid_nm=contour_grid_nm)))
        if convex_support_cover:combined_capsules.BooleanAdd(cap)
    _check_deadline(deadline)
    zones_by_id = {z.m_Uuid.AsString(): z for z in board.Zones()}
    replacement=None
    if replace_native_zone_uuid is not None:
        from cec_rounded_landing import _native_source
        if (type(replace_native_zone_uuid) is not str
                or replace_native_zone_uuid not in enclosing_native_zone_uuids
                or retire_source_tracks):
            raise Refused('explicit_enclosed_native_keeper_and_retained_tracks_required')
        keeper=zones_by_id.get(replace_native_zone_uuid)
        if keeper is None:raise Refused('native_keeper_zone_unavailable')
        replacement=_native_source(keeper,allow_complex_fill=True);config=replacement['configuration']
        from cec_native_contour_regions import ZONE_NAME as signed_name
        owner_names=(ZONE_NAME,signed_name) if allow_signed_native_keeper else (ZONE_NAME,)
        if ((not allow_source_solid_keeper and config['name'] not in owner_names)
                or type(config['name']) is not str or len(config['name'])>512
                or config['net']!=net or config['layers']!=[layer]
                or type(config['priority']) is not int or not 0<=config['priority']<=100_000
                or (not allow_source_solid_keeper and config['priority']!=0) or config['rule_area']
                or config['smoothing']!=0 or config['connection']!=int(pcbnew.ZONE_CONNECTION_FULL)
                or config['clearance_nm']!=clearance_nm or config['min_thickness_nm']!=min_thickness_nm
                or not retain_existing_keeper_lock and config['locked']!=any(r['locked'] for r in rows)
                or not retain_existing_keeper_group and config['group_uuid']!=(next(iter(parents)) if parents else None)):
            raise Refused('native_keeper_contract_must_be_retained_exactly')
        if (config['locked'] and replace_native_zone_uuid not in set(allow_locked_zone_uuids)
                or config['group_uuid'] and replace_native_zone_uuid not in set(allow_grouped_zone_uuids)):
            raise Refused('explicit_native_keeper_lock_group_authority_required')
        if rebuild_keeper_from_tracks:
            # Declared geometry recompile, not a blanket permission to trim
            # a power plane. Every same-net native stroke fully enclosed by
            # this old owner must participate; all actual strokes stay exact.
            enclosed=_enclosed_native_track_ids(board,keeper.Outline(),net,layer,deadline)
            if enclosed!=set(wanted):
                raise Refused('keeper_recompile_requires_all_enclosed_native_tracks')
    for uid in sorted(enclosing_native_zone_uuids):
        _check_deadline(deadline)
        zone = zones_by_id.get(uid)
        if zone is None or zone.GetNetname() != net or not zone.IsOnLayer(layer):
            raise Refused("native_landing_enclosure_identity_unavailable")
        witness = _support_row(zone, layer, deadline, max_vertices=max_vertices-vertices,
            allow_native_hole_bridges=allow_signed_native_keeper)
        vertices += witness["native_vertices"]
        if rebuild_keeper_from_tracks and uid==replace_native_zone_uuid:continue
        actual = zone.GetFilledPolysList(layer)
        rectangles.append(Polygon(_landing_envelope(board, zone, layer,
            style=contour_style, margin_nm=envelope_margin_nm, grid_nm=contour_grid_nm,
            mode=landing_enclosure_mode, max_jog_nm=landing_max_jog_nm, deadline=deadline,
            allow_native_hole_bridges=allow_signed_native_keeper)))
        if convex_support_cover: combined_capsules.BooleanAdd(actual)
    shape = unary_union(rectangles)
    if not isinstance(shape, Polygon) or not shape.is_valid or shape.interiors:
        raise Refused("disconnected_or_holed_corridor_requires_separate_owner")
    if convex_support_cover:
        shape=Polygon(purposeful_envelope(combined_capsules,style=contour_style,
            margin_nm=envelope_margin_nm,grid_nm=contour_grid_nm))
    ring = list(shape.exterior.coords)[:-1]
    if len(ring) > 1024 or any(v != int(v) for p in ring for v in p):
        raise Refused("non_native_rectilinear_union")
    points = [[int(x), int(y)] for x, y in ring]
    points=_canonical_jog_cover(board,points,net,layer,style=contour_style,
        max_jog_nm=contour_max_jog_nm,clearance_nm=clearance_nm,deadline=deadline,
        allow_native_hole_bridges=allow_signed_native_keeper)
    if any(a[0] != b[0] and a[1] != b[1] and
           (contour_style != "chamfer45" or abs(a[0]-b[0]) != abs(a[1]-b[1]))
           for a, b in zip(points, points[1:]+points[:1])):
        raise Refused("non_purposeful_contour")
    # Independent native outer capsule minus analytic polygon, no area waiver.
    profile = _poly(points)
    fill_envelope = None
    if fill_envelope_margin_nm:
        # KiCad's integer shrink/expand fill can put diagonal tessellation
        # vertices just outside an authored edge. Declare the larger actual
        # construction domain BEFORE generation; no overflow is ignored and
        # no old-copper loss tolerance is introduced. Default remains zero.
        fill_envelope = _fill_envelope(points, style=contour_style,
            margin_nm=fill_envelope_margin_nm)
    _require_unoccupied_outline(board, _poly(fill_envelope) if fill_envelope else profile, net, layer, deadline,
        allow_native_hole_bridges=allow_signed_native_keeper)
    _require_same_net_priority_available(board, profile, net, layer, deadline,
        own_zone_uuid=replace_native_zone_uuid,
        priority=replacement['configuration']['priority'] if replacement else 0)
    for t in selected:
        _check_deadline(deadline)
        missing = _native_capsule(t, max_vertices=max_vertices)
        missing.BooleanSubtract(profile)
        if missing.OutlineCount():
            raise Refused("proposal_does_not_enclose_native_conductor")
    # KiCad fills a lower-priority zone around higher-priority same-net zones.
    # The absent patch there is not missing conductor: actual existing native
    # fill may already supply it. Bind only exact overlapping saved same-net
    # fills; NEVER escalate priority or infer copper from an unfilled outline.
    support = []
    zones = list(board.Zones())
    if len(zones)>8192:
        raise Refused("native_zone_inventory_bound")
    for z in zones:
        _check_deadline(deadline)
        if z.m_Uuid.AsString()==replace_native_zone_uuid:continue
        if z.GetIsRuleArea() or z.GetNetname()!=net or not z.IsOnLayer(layer):
            continue
        if not z.IsFilled() or not z.HasFilledPolysForLayer(layer):
            continue
        filled = z.GetFilledPolysList(layer)
        if not filled.OutlineCount():
            continue
        # Validate bounds BEFORE any native boolean on this supporting fill.
        witness = _support_row(z, layer, deadline, max_vertices=max_vertices-vertices,
            allow_native_hole_bridges=allow_signed_native_keeper)
        vertices += witness["native_vertices"]
        overlap = filled.CloneDropTriangulation()
        overlap.BooleanIntersection(profile)
        if overlap.OutlineCount():
            support.append(witness)
            if len(support)>64:
                raise Refused("supporting_native_zone_inventory_bound")
    result = dict(schema=SCHEMA, scope=SCOPE, source_tracks=rows, supporting_zones=sorted(support,key=lambda r:r["uuid"]),
        net=net, layer_id=layer, polygon_nm=points, clearance_nm=clearance_nm,
        min_thickness_nm=min_thickness_nm, required_width_nm=required_width_nm,
        envelope_margin_nm=envelope_margin_nm, pad_connection="solid",
        group_uuid=(replacement['configuration']['group_uuid'] if retain_existing_keeper_group
                    else next(iter(parents)) if parents else None),
        locked=(replacement['configuration']['locked'] if retain_existing_keeper_lock
                else any(r["locked"] for r in rows)),
        priority=replacement['configuration']['priority'] if replacement else 0,
        filled_copper_received=False, new_capacity_credited=False,
        release_authority=False, requires_independent_receiving=True)
    if contour_style != "square":
        result["contour_style"] = contour_style
    if contour_grid_nm != 1:
        result["contour_grid_nm"] = contour_grid_nm
    if contour_max_jog_nm:
        result['contour_max_jog_nm']=contour_max_jog_nm
    if fill_envelope is not None:
        result["fill_envelope_margin_nm"] = fill_envelope_margin_nm
        result["actual_fill_envelope_nm"] = fill_envelope
    if not retire_source_tracks:
        result["retire_source_tracks"] = False
    if convex_support_cover:
        result['convex_support_cover']=True
    if enclosing_native_zone_uuids:
        result['enclosing_native_zone_uuids']=sorted(enclosing_native_zone_uuids)
        result['landing_enclosure_mode']=landing_enclosure_mode
        result['landing_max_jog_nm']=landing_max_jog_nm
    if replacement is not None:
        result['replacement_source_zone']=replacement
    if retain_existing_keeper_lock:
        result['retain_existing_keeper_lock']=True
    if retain_existing_keeper_group:
        result['retain_existing_keeper_group']=True
        result['retained_source_group_uuid']=next(iter(parents)) if parents else None
    if retained_native_track_material:
        result['retained_native_track_material']=True
    if allow_signed_native_keeper:
        result['allow_signed_native_keeper']=True
    if allow_source_solid_keeper:
        result['allow_source_solid_keeper']=True
    if source_diagonal_quantum_nm:
        result['source_diagonal_quantum_nm']=source_diagonal_quantum_nm
    if rebuild_keeper_from_tracks:
        result['rebuild_keeper_from_tracks']=True
    if fill_policy != "native":
        import cec_regional_fill
        result['fill_policy']=fill_policy
        result['regional_fill_binding']=cec_regional_fill.source_binding(board,result,deadline)
    result["plan_sha256"] = _digest(result)
    return result


def _validate_plan(proposal):
    import pcbnew
    if not isinstance(proposal, dict):
        raise Refused("missing_rectilinear_proposal")
    check = dict(proposal)
    digest = check.pop("plan_sha256", None)
    if (digest != _digest(check) or type(check.get("schema")) is not int
            or check.get("schema") != SCHEMA or check.get("scope") != SCOPE):
        raise Refused("rectilinear_proposal_identity_mismatch")
    if (check.get("release_authority") is not False
            or check.get("new_capacity_credited") is not False):
        raise Refused("proposal_cannot_grant_capacity_or_release")
    points, rows = check.get("polygon_nm"), check.get("source_tracks")
    if (not isinstance(points,list) or not 4 <= len(points) <= 1024
            or any(not isinstance(p,list) or len(p)!=2
                or any(type(v) is not int or abs(v)>2_000_000_000 for v in p) for p in points)
            or not isinstance(rows,list) or not 1 <= len(rows) <= 128
            or any(not isinstance(r,dict) or r.get("kind")!="PCB_TRACK"
                or r.get("net")!=check.get("net") or r.get("layer_id")!=check.get("layer_id")
                or type(r.get("width_nm")) is not int or not 1 <= r["width_nm"] <= 100_000_000
                or type(r.get("locked")) is not bool
                or any(not isinstance(r.get(k),list) or len(r[k])!=2
                    or any(type(v) is not int or abs(v)>2_000_000_000 for v in r[k])
                    for k in ("start_nm","end_nm")) for r in rows)):
        raise Refused("invalid_rectilinear_proposal_inventory")
    if (not isinstance(check.get("net"),str) or not check["net"]
            or type(check.get("layer_id")) is not int
            or type(check.get("required_width_nm")) is not int
            or not 1 <= check["required_width_nm"] <= 100_000_000
            or any(r["width_nm"] < check["required_width_nm"] for r in rows)
            or any(not isinstance(r.get("uuid"),str) or not r["uuid"] for r in rows)
            or len({r["uuid"] for r in rows}) != len(rows)):
        raise Refused("invalid_rectilinear_source_contract")
    retain_lock=check.get('retain_existing_keeper_lock',False)
    expected_lock=any(r['locked'] for r in rows)
    if type(retain_lock) is not bool:
        raise Refused('invalid_existing_keeper_lock_policy')
    if retain_lock:
        incumbent=check.get('replacement_source_zone')
        config=incumbent.get('configuration',{}) if type(incumbent) is dict else {}
        if (type(config.get('locked')) is not bool or check.get('retire_source_tracks') is not False
                or check.get('rebuild_keeper_from_tracks',False) is not False
                or check.get('fill_policy')!='source_preserving_regions'):
            raise Refused('retained_keeper_lock_requires_exact_source_fill_and_tracks')
        expected_lock=config['locked']
    retain_group=check.get('retain_existing_keeper_group',False)
    if type(retain_group) is not bool:
        raise Refused('invalid_existing_keeper_group_policy')
    source_group=check.get('group_uuid')
    if retain_group:
        incumbent=check.get('replacement_source_zone')
        config=incumbent.get('configuration',{}) if type(incumbent) is dict else {}
        if ('retained_source_group_uuid' not in check
                or check.get('retire_source_tracks') is not False
                or check.get('rebuild_keeper_from_tracks',False) is not False
                or check.get('fill_policy')!='source_preserving_regions'
                or 'group_uuid' not in config or check.get('group_uuid')!=config['group_uuid']):
            raise Refused('retained_keeper_group_requires_exact_source_fill_and_tracks')
        source_group=check['retained_source_group_uuid']
        if source_group is not None and (type(source_group) is not str or not source_group):
            raise Refused('exact_retained_source_group_identity_required')
    elif 'retained_source_group_uuid' in check:
        raise Refused('retained_source_group_binding_requires_explicit_policy')
    retained_material=check.get('retained_native_track_material',False)
    if (type(retained_material) is not bool or retained_material and
            (check.get('replacement_source_zone') is None or check.get('retire_source_tracks') is not False
             or check.get('rebuild_keeper_from_tracks',False) is not False
             or check.get('fill_policy')!='source_preserving_regions')):
        raise Refused('retained_native_material_requires_exact_source_keeper_fill_and_tracks')
    signed_keeper=check.get('allow_signed_native_keeper',False)
    if (type(signed_keeper) is not bool or signed_keeper and
            (check.get('replacement_source_zone') is None or check.get('retire_source_tracks') is not False
             or check.get('rebuild_keeper_from_tracks',False) is not False
             or check.get('fill_policy')!='source_preserving_regions')):
        raise Refused('signed_keeper_requires_exact_source_fill_and_tracks')
    source_solid=check.get('allow_source_solid_keeper',False)
    if (type(source_solid) is not bool or source_solid and
            (check.get('replacement_source_zone') is None or check.get('retire_source_tracks') is not False
             or check.get('rebuild_keeper_from_tracks',False) is not False
             or check.get('fill_policy')!='source_preserving_regions' or not retained_material
             or not retain_lock or not retain_group or not signed_keeper)):
        raise Refused('invalid_source_solid_keeper_literal_preservation_policy')
    quantum=check.get('source_diagonal_quantum_nm',0)
    if (type(quantum) is not int or quantum not in (0,1) or quantum and
            (check.get('replacement_source_zone') is None or check.get('retire_source_tracks') is not False
             or check.get('rebuild_keeper_from_tracks',False) is not False
             or check.get('fill_policy')!='source_preserving_regions'
             or check.get('contour_style')!='chamfer45')):
        raise Refused('invalid_retained_native_diagonal_cover_policy')
    bounds = {"clearance_nm":(0,10_000_000), "min_thickness_nm":(1,1_000_000),
              "envelope_margin_nm":(1,100_000), "priority":(0,100_000 if source_solid else 0)}
    if (any(type(check.get(k)) is not int or not lo<=check[k]<=hi for k,(lo,hi) in bounds.items())
            or any(check["min_thickness_nm"]>=r["width_nm"] for r in rows)
            or check.get("pad_connection")!="solid" or type(check.get("locked")) is not bool
            or check["locked"]!=expected_lock
            or check.get("filled_copper_received") is not False
            or check.get("requires_independent_receiving") is not True
            or any(not _source_centerline_allowed(r["start_nm"],r["end_nm"],
                check.get("contour_style","square"),quantum) for r in rows)
            or any(r.get("group_uuid") is not None and (not isinstance(r["group_uuid"],str) or not r["group_uuid"]) for r in rows)
            or {r["group_uuid"] for r in rows if r["group_uuid"]}!=(
                {source_group} if source_group else set())):
        raise Refused("invalid_rectilinear_native_configuration")
    support = check.get("supporting_zones")
    if (not isinstance(support,list) or len(support)>64
            or any(not isinstance(r,dict) or r.get("net")!=check["net"] or r.get("layer_id")!=check["layer_id"]
                or not isinstance(r.get("uuid"),str) or not r["uuid"]
                or type(r.get("priority")) is not int or not 0<=r["priority"]<=100_000
                or type(r.get("native_vertices")) is not int or not 1<=r["native_vertices"]<=200_000
                or any(not isinstance(r.get(k),str) or len(r[k])!=64 or any(c not in '0123456789abcdef' for c in r[k])
                    for k in ("outline_sha256","fill_sha256")) for r in support)
            or len({r["uuid"] for r in support})!=len(support)):
        raise Refused("invalid_supporting_native_copper_inventory")
    replacement=check.get('replacement_source_zone')
    keeper_id=None
    if replacement is not None:
        if (type(replacement) is not dict or set(replacement) not in (
                {'configuration','outline_nm','fill_nm'},
                {'configuration','outline_nm','fill_polygons_nm'})):
            raise Refused('invalid_native_keeper_source')
        c=replacement.get('configuration',{})
        keeper_id=c.get('uuid')
        from cec_native_contour_regions import ZONE_NAME as signed_name
        owner_names=(ZONE_NAME,signed_name) if signed_keeper else (ZONE_NAME,)
        if (type(keeper_id) is not str or not keeper_id or
                (not source_solid and c.get('name') not in owner_names)
                or type(c.get('name')) is not str or len(c['name'])>512
                or c.get('net')!=check['net'] or c.get('layers')!=[check['layer_id']]
                or type(c.get('priority')) is not int or c['priority']!=check['priority']
                or c.get('rule_area') is not False or c.get('smoothing')!=0
                or c.get('connection')!=int(pcbnew.ZONE_CONNECTION_FULL) or c.get('clearance_nm')!=check['clearance_nm']
                or c.get('min_thickness_nm')!=check['min_thickness_nm']
                or c.get('locked')!=check['locked'] or c.get('group_uuid')!=check['group_uuid']
                or check.get('retire_source_tracks',True)):
            raise Refused('invalid_native_keeper_configuration')
        for key in ('outline_nm',):
            source_points=replacement.get(key)
            if (type(source_points) is not list or not 3<=len(source_points)<=4096
                    or any(type(p) is not list or len(p)!=2 or any(type(v) is not int
                        or abs(v)>2000000000 for v in p) for p in source_points)):
                raise Refused('invalid_native_keeper_source_geometry')
        from cec_native_fill_geometry import source_fill
        source_fill(replacement,time.monotonic()+2)
        if keeper_id in {r['uuid'] for r in support}:
            raise Refused('native_keeper_cannot_claim_unchanged_support')
    recompile=check.get('rebuild_keeper_from_tracks',False)
    if (type(recompile) is not bool or (recompile and (replacement is None
            or check.get('retire_source_tracks',True)
            or check.get('fill_policy','native') not in ('native','conductor_preserving_regions')
            or check.get('convex_support_cover',False)))
            or (check.get('fill_policy')=='conductor_preserving_regions' and not recompile)):
        raise Refused('invalid_owned_keeper_recompile_policy')
    enclosed = check.get("enclosing_native_zone_uuids", [])
    if (not isinstance(enclosed, list) or len(enclosed) > 8
            or len(set(enclosed)) != len(enclosed)
            or any(type(u) is not str or not u for u in enclosed)
            or not set(enclosed) <= {r["uuid"] for r in support}|({keeper_id} if keeper_id else set())
            or (keeper_id is not None and keeper_id not in enclosed)):
        raise Refused("invalid_bound_native_landing_enclosure")
    mode = check.get('landing_enclosure_mode', 'convex_fill')
    jog = check.get('landing_max_jog_nm', 0)
    if (mode not in ('convex_fill', 'canonical_outline') or type(jog) is not int
            or not 0 <= jog <= 1_000_000 or (jog and mode != 'canonical_outline')
            or (not enclosed and (jog or mode != 'convex_fill'))
            or (check.get('convex_support_cover', False) and mode != 'convex_fill')):
        raise Refused('invalid_bound_native_landing_policy')
    style = check.get("contour_style", "square")
    if (style not in ("square", "chamfer45") or type(check.get("contour_grid_nm",1)) is not int
            or not 1<=check.get("contour_grid_nm",1)<=100000):
        raise Refused("invalid_proposal_contour_style")
    contour_jog=check.get('contour_max_jog_nm',0)
    if (type(contour_jog) is not int or not 0<=contour_jog<=1_000_000
            or (contour_jog and check.get('convex_support_cover',False))):
        raise Refused('invalid_canonical_jog_policy')
    for a,b in zip(points,points[1:]+points[:1]):
        if a==b or (a[0]!=b[0] and a[1]!=b[1] and
                    (style!="chamfer45" or abs(a[0]-b[0])!=abs(a[1]-b[1]))):
            raise Refused("non_purposeful_proposal_outline")
    guard=check.get("fill_envelope_margin_nm",0)
    if type(check.get("retire_source_tracks",True)) is not bool or type(check.get('convex_support_cover',False)) is not bool:
        raise Refused("invalid_source_track_retirement_policy")
    if type(guard) is not int or not 0<=guard<=10:
        raise Refused("invalid_actual_fill_envelope_bound")
    if guard:
        expected=_fill_envelope(points,style=style,margin_nm=guard)
        if check.get("actual_fill_envelope_nm")!=expected:
            raise Refused("actual_fill_envelope_not_derived_from_profile")
    elif "actual_fill_envelope_nm" in check:
        raise Refused("undeclared_actual_fill_envelope")
    fill_policy=check.get('fill_policy','native')
    if fill_policy not in ('native','source_preserving_regions','conductor_preserving_regions'):
        raise Refused('invalid_native_fill_policy')
    if fill_policy in ('source_preserving_regions','conductor_preserving_regions'):
        import cec_regional_fill
        cec_regional_fill.validate_binding(check)
    elif 'regional_fill_binding' in check:
        raise Refused('undeclared_regional_fill_binding')


def materialize(board, proposal, *, allow_locked_track_uuids=(), allow_grouped_track_uuids=(),
                allow_locked_zone_uuids=(), allow_grouped_zone_uuids=()):
    """Mutate a caller-owned PRIVATE board only; never save, refill or promote.

    The caller retains an immutable saved source and owns rollback/receiving.
    All source native track fingerprints must match before any mutation.
    """
    import pcbnew
    from cec_native_items import discard_items
    _validate_plan(proposal)
    replacement=proposal.get('replacement_source_zone');keeper=None
    if replacement:
        from cec_rounded_landing import _native_source
        config=replacement['configuration'];uid=config['uuid']
        keeper=next((z for z in board.Zones() if z.m_Uuid.AsString()==uid),None)
        if keeper is None or _native_source(keeper,allow_complex_fill=True)!=replacement:
            raise Refused('native_keeper_source_changed')
        if (config['locked'] and uid not in set(allow_locked_zone_uuids)
                or config['group_uuid'] and uid not in set(allow_grouped_zone_uuids)):
            raise Refused('materialization_requires_native_keeper_authority')
        if proposal.get('rebuild_keeper_from_tracks',False):
            enclosed=_enclosed_native_track_ids(board,keeper.Outline(),proposal['net'],
                proposal['layer_id'],time.monotonic()+2.0)
            if enclosed!={r['uuid'] for r in proposal['source_tracks']}:
                raise Refused('keeper_recompile_native_track_inventory_changed')
    _receive_support(board, proposal, time.monotonic()+2.0)
    _require_unoccupied_outline(board, _poly(proposal.get("actual_fill_envelope_nm",proposal["polygon_nm"])), proposal["net"],
        proposal["layer_id"], time.monotonic()+2.0,
        allow_native_hole_bridges=proposal.get('allow_signed_native_keeper',False))
    _require_same_net_priority_available(board, _poly(proposal['polygon_nm']), proposal['net'],
        proposal['layer_id'], time.monotonic()+2.0,
        own_zone_uuid=replacement['configuration']['uuid'] if replacement else None,priority=proposal['priority'])
    locked, grouped = set(allow_locked_track_uuids), set(allow_grouped_track_uuids)
    if any(r["locked"] and r["uuid"] not in locked for r in proposal["source_tracks"]):
        raise Refused("materialization_requires_locked_item_authority")
    if any(r["group_uuid"] and r["uuid"] not in grouped for r in proposal["source_tracks"]):
        raise Refused("materialization_requires_grouped_item_authority")
    inventory = {t.m_Uuid.AsString(): t for t in board.GetTracks()}
    selected = []
    for row in proposal["source_tracks"]:
        t = inventory.get(row["uuid"])
        if t is None or t.GetClass() != "PCB_TRACK" or _track_row(t) != row:
            raise Refused("native_owned_source_changed")
        selected.append(t)
    if _derived_profile(board,proposal,time.monotonic()+2.0) != proposal['polygon_nm']:
        raise Refused('cover_not_derived_from_actual_native_copper')
    net = board.FindNet(proposal["net"])
    if net is None or net.GetNetCode() <= 0:
        raise Refused("native_net_identity_unavailable")
    group = None
    if proposal["group_uuid"]:
        group = next((g for g in board.Groups()
            if g.m_Uuid.AsString() == proposal["group_uuid"]), None)
        if group is None:
            raise Refused("native_parent_group_changed")
    zone = keeper if keeper is not None else pcbnew.ZONE(board)
    zone.SetNet(net)
    zone.SetLayer(proposal["layer_id"])
    zone.SetZoneName(replacement['configuration']['name'] if replacement else ZONE_NAME)
    zone.SetLocked(proposal["locked"])
    zone.SetAssignedPriority(proposal["priority"])
    zone.SetLocalClearance(proposal["clearance_nm"])
    zone.SetMinThickness(proposal["min_thickness_nm"])
    zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    zone.SetCornerSmoothingType(0)
    zone.SetIsRuleArea(False)
    if keeper is not None:
        zone.UnFill();zone.Outline().RemoveAllContours()
    zone.Outline().NewOutline()
    for x, y in proposal["polygon_nm"]:
        zone.Outline().Append(x, y)
    if keeper is None:board.Add(zone)
    if group is not None and keeper is None:
        group.AddItem(zone)
    zone_uuid = zone.m_Uuid.AsString()
    retire=proposal.get("retire_source_tracks",True)
    if retire:discard_items(board, selected)
    return dict(zone_uuid=zone_uuid, retired_track_uuids=[r["uuid"] for r in proposal["source_tracks"]] if retire else [],
        modified_zone_uuids=[zone_uuid] if keeper is not None else [],
        preserved_source_track_uuids=[] if retire else [r["uuid"] for r in proposal["source_tracks"]],
        plan_sha256=proposal["plan_sha256"], source_primitive_retirement_declared=retire,
        native_filled_copper_received=False, requires_independent_receiving=True,
        new_capacity_credited=False, release_authority=False)


def fill(board, proposal, zone_uuid, *, regional_source=None, timeout_s=10):
    """Compile the declared native fill policy, never skip its receiving."""
    import pcbnew
    _validate_plan(proposal)
    if proposal.get('fill_policy','native') in ('source_preserving_regions','conductor_preserving_regions'):
        import cec_regional_fill
        return cec_regional_fill.fill(regional_source,board,proposal,zone_uuid,timeout_s=timeout_s)
    batch=pcbnew.ZONES()
    zone=next((z for z in board.Zones() if z.m_Uuid.AsString()==zone_uuid),None)
    if zone is None:raise Refused('native_zone_identity_unavailable')
    batch.append(zone);board.BuildConnectivity()
    import cec_zone_fill
    cec_zone_fill.compile_selected(board,batch,timeout_s=timeout_s)
    return dict(zone_uuid=zone_uuid,native_filled_copper_received=False,release_authority=False)


def receive(board, proposal, zone_uuid, *, timeout_s=2.0, max_vertices=200_000,
            regional_source=None):
    """Native post-fill enclosure, not a full-board electrical/current pass.

    Every selected native capsule is independently rebuilt and its 1 nm
    ERROR_OUTSIDE polygon must be inside actual native FILLED copper: the
    replacement plus exact unchanged, bound same-net supporting fills. Zero
    missing outlines is mandatory; area and renderer comparisons grant nothing.
    """
    import pcbnew
    started = time.monotonic()
    if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
            or not 0 <= timeout_s <= 10 or type(max_vertices) is not int
            or not 32 <= max_vertices <= 200_000):
        raise Refused("invalid_rectilinear_receiving_bounds")
    result = dict(schema=SCHEMA, scope=SCOPE, ok=False, complete=False,
        zone_uuid=zone_uuid, missing_source_tracks=[], new_capacity_credited=False,
        release_authority=False, full_board_receiving_required=True)
    deadline = started + timeout_s
    try:
        _check_deadline(deadline)
        _validate_plan(proposal)
        zones = [z for z in board.Zones() if z.m_Uuid.AsString() == zone_uuid]
        if len(zones) != 1:
            raise Refused("native_zone_identity_unavailable")
        z = zones[0]
        replacement=proposal.get('replacement_source_zone')
        if replacement:
            from cec_rounded_landing import _configuration
            if _configuration(z)!=replacement['configuration']:
                raise Refused('native_keeper_configuration_changed')
        if (z.GetIsRuleArea() or z.GetNetname() != proposal["net"]
                or set(z.GetLayerSet().CuStack()) != {proposal["layer_id"]}
                or z.GetZoneName() != (replacement['configuration']['name'] if replacement else ZONE_NAME)
                or bool(z.IsLocked()) != proposal["locked"]
                or z.GetAssignedPriority() != proposal["priority"]
                or z.GetLocalClearance() != proposal["clearance_nm"]
                or z.GetMinThickness() != proposal["min_thickness_nm"]
                or z.GetCornerSmoothingType() != 0
                or z.GetPadConnection() != pcbnew.ZONE_CONNECTION_FULL
                or _group_uuid(z) != proposal["group_uuid"]):
            raise Refused("native_zone_contract_changed")
        expected = _poly(proposal["polygon_nm"])
        fill_domain=_poly(proposal.get("actual_fill_envelope_nm",proposal["polygon_nm"]))
        _require_unoccupied_outline(board, fill_domain, proposal["net"], proposal["layer_id"], deadline,
            allow_native_hole_bridges=proposal.get('allow_signed_native_keeper',False))
        outline = z.Outline()
        a, b = expected.CloneDropTriangulation(), outline.CloneDropTriangulation()
        a.BooleanSubtract(outline)
        b.BooleanSubtract(expected)
        if a.OutlineCount() or b.OutlineCount():
            raise Refused("native_zone_outline_changed")
        if not z.IsFilled() or not z.HasFilledPolysForLayer(proposal["layer_id"]):
            raise Refused("native_zone_not_filled")
        filled = z.GetFilledPolysList(proposal["layer_id"])
        vertices = 0
        if not filled.OutlineCount():
            raise Refused("native_zone_empty_fill")
        for i in range(filled.OutlineCount()):
            _check_deadline(deadline)
            for ring in [filled.Outline(i), *[filled.Hole(i,j) for j in range(filled.HoleCount(i))]]:
                if ring.ArcCount():
                    raise Refused("unsupported_filled_polygon_arc")
                vertices += ring.PointCount()
                if vertices > max_vertices:
                    raise Refused("native_fill_vertex_bound")
        spill = filled.CloneDropTriangulation()
        spill.BooleanSubtract(fill_domain)
        if spill.OutlineCount():
            raise Refused("native_fill_outside_declared_profile")
        supporting, support_vertices = _receive_support(board, proposal, deadline, max_vertices=max_vertices-vertices)
        if _derived_profile(board,proposal,deadline) != proposal['polygon_nm']:
            raise Refused('cover_not_derived_from_actual_native_copper')
        _require_same_net_priority_available(board,expected,proposal['net'],proposal['layer_id'],deadline,
            own_zone_uuid=zone_uuid,priority=proposal['priority'])
        vertices += support_vertices
        actual_copper = filled.CloneDropTriangulation()
        for support in supporting:
            _check_deadline(deadline)
            actual_copper.BooleanAdd(support.GetFilledPolysList(proposal["layer_id"]))
        if replacement and not proposal.get('rebuild_keeper_from_tracks',False):
            from cec_native_fill_geometry import source_fill
            source_native=source_fill(replacement,deadline)
            old_fill=source_native.CloneDropTriangulation();old_fill.BooleanSubtract(actual_copper)
            if old_fill.OutlineCount():
                exact_source=False
                if proposal.get('fill_policy','native')=='source_preserving_regions':
                    import cec_regional_fill
                    exact_source=cec_regional_fill.exact_source_contour_present(
                        filled,source_native,deadline)
                if not exact_source:raise Refused('native_keeper_source_fill_loss')
                result['keeper_preservation_basis']='exact_positive_native_source_contour'
        if replacement:
            # An unchanged higher-priority source landing's unfilled clearance
            # spaces are not permission for the lower-priority keeper to fill
            # them. Preserve its actual process clearance and contact geometry.
            for support in supporting:
                if support.GetAssignedPriority() <= proposal['priority']:continue
                intrusion=filled.CloneDropTriangulation();intrusion.BooleanIntersection(support.Outline())
                intrusion.BooleanSubtract(support.GetFilledPolysList(proposal['layer_id']))
                if intrusion.OutlineCount():raise Refused('higher_priority_native_landing_void_changed')
        if proposal.get('rebuild_keeper_from_tracks',False):
            # The superseded keeper's cosmetic pixels are not retained. Its
            # process/ownership, actual native stroke fingerprints and zero-
            # loss filled stroke covers ARE retained and received below.
            # Whole-board contact/current/Kelvin/field/DRC receiving remains
            # mandatory; no current capacity is assigned to the new zone.
            result['keeper_preservation_basis']='unchanged_declared_native_conductors_not_old_cover_pixels'
            result['original_keeper_fill_preserved']=False
        # Bound the actual union too, not just each contributing inventory.
        if proposal.get('fill_policy','native') in ('source_preserving_regions','conductor_preserving_regions'):
            from cec_native_fill_geometry import identity
            _, union_vertices = identity(actual_copper,deadline,max_vertices=max_vertices-vertices)
        else:
            _, union_vertices = _shape_identity(actual_copper, deadline, max_vertices=max_vertices-vertices)
        vertices += union_vertices
        inventory={t.m_Uuid.AsString():t for t in board.GetTracks()}
        if proposal.get("retire_source_tracks",True):
            if inventory.keys() & {r["uuid"] for r in proposal["source_tracks"]}:
                raise Refused("declared_source_track_not_retired")
        elif any(r["uuid"] not in inventory or _track_row(inventory[r["uuid"]])!=r for r in proposal["source_tracks"]):
            raise Refused("preserved_native_source_track_changed")
        # Fill-only enclosure is distinct from actual source-material
        # preservation. This opt-in cannot retire any source track. Exact
        # unchanged REAL native tracks may supply their own original copper,
        # but never a ghost, a new width/current allocation, or a claim that
        # their exposed cap is hidden by the keeper fill.
        fill_only_copper=actual_copper
        retained_material=proposal.get('retained_native_track_material',False)
        quantum=proposal.get('source_diagonal_quantum_nm',0)
        if quantum:result['quantized_source_diagonal_track_uuids']=[]
        if retained_material:
            actual_copper=fill_only_copper.CloneDropTriangulation()
            for row in proposal['source_tracks']:
                _check_deadline(deadline)
                actual_copper.BooleanAdd(_native_capsule(inventory[row['uuid']],max_vertices=max_vertices))
            from cec_native_fill_geometry import identity
            _,count=identity(actual_copper,deadline,max_vertices=max_vertices-vertices)
            vertices+=count
            result['keeper_fill_only_missing_source_tracks']=[]
        net = board.FindNet(proposal["net"])
        for row in proposal["source_tracks"]:
            _check_deadline(deadline)
            ghost = pcbnew.PCB_TRACK(board)
            ghost.SetNet(net)
            ghost.SetLayer(row["layer_id"])
            ghost.SetWidth(row["width_nm"])
            ghost.SetStart(pcbnew.VECTOR2I(*row["start_nm"]))
            ghost.SetEnd(pcbnew.VECTOR2I(*row["end_nm"]))
            missing = _native_capsule(ghost, max_vertices=max_vertices)
            vertices += missing.Outline(0).PointCount()
            if vertices > max_vertices:
                raise Refused("native_receiving_total_vertex_bound")
            if retained_material or quantum:
                missing_fill=missing.CloneDropTriangulation();missing_fill.BooleanSubtract(fill_only_copper)
                if retained_material and missing_fill.OutlineCount():
                    result['keeper_fill_only_missing_source_tracks'].append(row['uuid'])
                if quantum and not _centerline_allowed(row['start_nm'],row['end_nm'],proposal['contour_style']):
                    result['quantized_source_diagonal_track_uuids'].append(row['uuid'])
                    if missing_fill.OutlineCount():
                        raise Refused('quantized_native_diagonal_requires_complete_actual_fill_cover')
            missing.BooleanSubtract(actual_copper)
            if missing.OutlineCount():
                result["missing_source_tracks"].append(row["uuid"])
        _check_deadline(deadline)
        result.update(complete=True, ok=not result["missing_source_tracks"],
            reason="native_conductor_enclosed" if not result["missing_source_tracks"] else "native_conductor_loss",
            verified_track_count=len(proposal["source_tracks"]), native_vertices=vertices,
            supporting_zone_uuids=[z.m_Uuid.AsString() for z in supporting],
            enclosure_basis="replacement_and_exact_unchanged_same_net_native_fills",
            fill_envelope_margin_nm=proposal.get("fill_envelope_margin_nm",0),
            plan_sha256=proposal["plan_sha256"])
        if retained_material:
            result.update(retained_native_track_material_used=True,
                keeper_fill_only_encloses_all_source_tracks=not result['keeper_fill_only_missing_source_tracks'],
                enclosure_basis='exact_unchanged_real_native_tracks_and_replacement_and_same_net_fills',
                reason='native_source_material_preserved' if result['ok'] else 'native_source_material_loss',
                fill_only_capacity_qualified=False,all_power_contours_clean=False)
        if replacement:
            result['original_native_keeper_fill_preserved']=not proposal.get('rebuild_keeper_from_tracks',False)
        if proposal.get('fill_policy','native') in ('source_preserving_regions','conductor_preserving_regions'):
            import cec_regional_fill
            result['regional_fill_receiving']=cec_regional_fill.receive(
                regional_source,board,proposal,zone_uuid,
                timeout_s=max(0,deadline-time.monotonic()))
            if retained_material:
                regional=result['regional_fill_receiving']
                if (regional.get('ok') is not True
                        or regional.get('independently_replayed_native_additions') is not True
                        or regional.get('exact_source_copper_preserved') is not True):
                    raise Refused('retained_material_native_regional_replay_refused')
    except (Refused, ValueError, RuntimeError) as exc:
        result.update(ok=False,complete=False,reason=str(exc))
    result["elapsed_s"] = time.monotonic() - started
    return result


def enclosed_track_witnesses(board, proposal, zone_uuid, *, timeout_s=2.0,regional_source=None):
    """Replayed native filled-copper subsets, NEVER virtual unproved routes.

    These native tracks are NOT added to the board. Their entire conservative
    copper envelopes have just been proved inside the real filled zone. A
    current checker may use their existing dimensions as conservative resident
    subsets; it must still apply its actual per-layer dimensional authority.
    Vias, arbitrary zone capacity and parallel-current sharing receive no
    credit. No cached or caller-supplied 'ok' flag substitutes for replay.
    """
    import pcbnew
    proof = receive(board, proposal, zone_uuid, timeout_s=timeout_s,regional_source=regional_source)
    if proof.get("ok") is not True or proof.get("complete") is not True:
        raise Refused("native_enclosure_witness_unavailable: " + proof["reason"])
    net = board.FindNet(proposal["net"])
    witnesses = []
    if not proposal.get("retire_source_tracks",True):
        # The real rated track already remains on the board. Never add a
        # second ghost or duplicate capacity credit for that same conductor.
        return witnesses,proof
    for row in proposal["source_tracks"]:
        t = pcbnew.PCB_TRACK(board)
        t.m_Uuid.Clone(pcbnew.KIID(row["uuid"]))
        t.SetNet(net); t.SetLayer(row["layer_id"]); t.SetWidth(row["width_nm"])
        t.SetStart(pcbnew.VECTOR2I(*row["start_nm"]))
        t.SetEnd(pcbnew.VECTOR2I(*row["end_nm"]))
        t.SetLocked(row["locked"])
        witnesses.append(t)
    return witnesses, proof
