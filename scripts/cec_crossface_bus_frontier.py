"""Bounded native-copper component proposals for an explicit two-face bus.

Polygonization is a conservative search hint, not a native route/clearance,
current-sharing, via-ampacity, no-path or release certificate. Every selected
transition and every subsequent conductor still needs independent native
construction/receiving. No board, reference, coordinate or current defaults.
"""
import math
import time


def pending_native_frontier(board, **explicit_context):
    """Prospective incoming native islands, not ownership or bus admission.

    Opt-in counterpart to the retained-copper frontier. Full explicit Source
    binding, absent definitions, mandatory terminals and actual via geometry
    are required; existing retained zones never gain planning exemptions.
    """
    from cec_pending_copper_frontier import native_frontier
    return native_frontier(board, **explicit_context)


def _polygons(geometry):
    if not geometry.is_valid:
        raise ValueError('crossface_invalid_polygon_geometry')
    if geometry.is_empty:
        return []
    if geometry.geom_type == 'Polygon':
        return [geometry]
    if geometry.geom_type == 'MultiPolygon':
        return list(geometry.geoms)
    raise ValueError('crossface_nonpolygon_geometry')


def component_graph(faces, *, source_points, target_points, transitions,
                    native_transition_clear, maximum_transitions=128,
                    deadline=None):
    """Pure bounded component graph; proposed legs are NOT constructed copper.

    Each transition region must lie in both actual face components. The native
    callback independently checks a representative centre, never an area or
    overlap count. Missing samples remain unresolved, not proof of no path.
    """
    from shapely.geometry import Point
    if (not isinstance(faces, dict) or len(faces) != 2
            or type(maximum_transitions) is not int or not 1 <= maximum_transitions <= 256
            or not callable(native_transition_clear)
            or len(source_points) not in (1, 2) or len(target_points) not in (1, 2)
            or deadline is not None and not math.isfinite(deadline)):
        raise ValueError('crossface_bounded_explicit_graph_required')
    if set(source_points)-faces.keys() or set(target_points)-faces.keys():
        raise ValueError('crossface_endpoint_face_unknown')
    components = {face: _polygons(shape) for face, shape in faces.items()}
    if sum(map(len, components.values())) > 4096:
        raise ValueError('crossface_component_bound')
    def locate(face, point):
        if (len(point) != 2 or any(type(v) not in (int, float)
                or not math.isfinite(v) or abs(v) > 2000 for v in point)):
            raise ValueError('crossface_finite_endpoint_required:'+repr(point))
        matches = [(face, n) for n, part in enumerate(components[face])
                   if part.covers(Point(*point))]
        if len(matches) > 1:
            raise ValueError('crossface_ambiguous_component')
        return matches[0] if matches else None
    sources = {node for face, pt in source_points.items() if (node := locate(face, pt)) is not None}
    targets = {node for face, pt in target_points.items() if (node := locate(face, pt)) is not None}
    regions = _polygons(transitions)
    if len(regions) > 4096:
        raise ValueError('crossface_transition_region_bound')
    # Area is only proposal priority. It is never trace width/current credit.
    regions.sort(key=lambda part: (-part.area, part.bounds))
    adjacency = {}; accepted = []; checked = 0; exhausted = False
    names = list(faces)
    for region in regions:
        if checked >= maximum_transitions or deadline is not None and time.monotonic() >= deadline:
            exhausted = True
            break
        point = region.representative_point()
        at = (float(point.x), float(point.y))
        nodes = [locate(face, at) for face in names]
        if any(node is None for node in nodes):
            raise ValueError('crossface_transition_outside_face_components')
        checked += 1
        if native_transition_clear(at) is not True:
            continue
        index = len(accepted)
        accepted.append(dict(at_mm=list(at), components=[list(n) for n in nodes],
                             proposal_region_area_mm2=region.area))
        for node, other in ((nodes[0], nodes[1]), (nodes[1], nodes[0])):
            adjacency.setdefault(node, []).append((other, index))
    queue = sorted(sources); previous = {node: None for node in sources}; reached = None
    for node in queue:
        if node in targets:
            reached = node
            break
        for other, index in adjacency.get(node, ()):
            if other not in previous:
                previous[other] = (node, index)
                queue.append(other)
    path = []
    cursor = reached
    while cursor is not None and previous[cursor] is not None:
        before, index = previous[cursor]
        path.append(dict(from_component=list(before), to_component=list(cursor),
                         transition=accepted[index]))
        cursor = before
    path.reverse()
    # A failed bounded map should guide a physical repair, not another blind
    # maze retry. Compare only same-face source/target-side components. These
    # are proposal distances, not a min-cut or authority to move the blockers.
    from shapely.ops import nearest_points
    target_queue = sorted(targets); target_side = set(target_queue)
    for node in target_queue:
        for other, _ in adjacency.get(node, ()):
            if other not in target_side:
                target_side.add(other); target_queue.append(other)
    comparisons = [(left, right) for left in previous for right in target_side
                   if left[0] == right[0] and left != right]
    if len(comparisons) > 16384:
        raise ValueError('crossface_gap_comparison_bound')
    gaps = []
    if reached is None:
        for left, right in comparisons:
            a, b = nearest_points(components[left[0]][left[1]], components[right[0]][right[1]])
            gaps.append(dict(layer=left[0], source_component=list(left), target_component=list(right),
                source_point_mm=[float(a.x), float(a.y)], target_point_mm=[float(b.x), float(b.y)],
                proposed_centreline_gap_mm=float(a.distance(b))))
        gaps.sort(key=lambda row: (row['proposed_centreline_gap_mm'], row['source_component'], row['target_component']))
    return dict(component_counts={str(k): len(v) for k, v in components.items()},
        source_components=[list(n) for n in sorted(sources)],
        target_components=[list(n) for n in sorted(targets)],
        proposed_face_path_found=reached is not None, proposed_transitions=path,
        native_checked_transition_centres=accepted, transition_regions=len(regions),
        native_checked_count=checked, proposal_budget_exhausted=exhausted,
        closest_unjoined_same_face_component_proposals=gaps[:8],
        no_path_proof=False, native_planar_legs_received=False,
        current_sharing_inferred=False, barrel_ampacity_qualified=False,
        routing_admitted=False, release_authority=False)


def native_frontier(board, *, net_code, widths_nm, clearance_nm, via,
                    source_points_nm, target_points_nm, timeout_s=10.,
                    maximum_transitions=128):
    """Snapshot actual foreign shapes and all enabled via-land faces.

    Input widths/current authority and via process/rating are the caller's
    responsibility. This function never narrows them or omits an inner land.
    The native guard retains the real drill field, local rules and padstack.
    Returned shapes are for private diagnostics only, not fabrication copper.
    """
    import pcbnew
    import cec_fr as fr
    import cec_board_geometry as geometry
    from cec_assembly_envelope import polygon_from_native
    from shapely.ops import unary_union
    if (type(net_code) is not int or net_code <= 0 or via.GetNetCode() != net_code
            or set(widths_nm) != {int(pcbnew.F_Cu), int(pcbnew.B_Cu)}
            or any(type(w) is not int or not 0 < w <= 10000000 for w in widths_nm.values())
            or type(clearance_nm) is not int or not 0 <= clearance_nm <= 2000000
            or type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10):
        raise ValueError('crossface_native_explicit_source_geometry_required')
    from cec_native_via_land_context import inspect
    if any(item.m_Uuid.AsString() == via.m_Uuid.AsString() for item in board.GetTracks()):
        raise ValueError('crossface_proposal_via_must_not_mutate_saved_conductor')
    context = inspect(board, via, net_code=net_code, at=via.GetPosition(),
        maximum_diameter_nm=max(via.GetWidth(l) for l in board.GetEnabledLayers().CuStack()),
        drill_nm=via.GetDrillValue(), clearance_nm=clearance_nm)
    deadline = time.monotonic()+timeout_s
    material = polygon_from_native(geometry.outline_material(board))
    face_free = {}; land_free = []; inventory = []; total_vertices = 0
    for face in board.GetEnabledLayers().CuStack():
        if time.monotonic() >= deadline:
            raise ValueError('crossface_native_snapshot_deadline')
        face = int(face)
        zones, copper = fr._identified_foreign_shape_indexes(board, face, {net_code})
        rows = [*zones['rows'], *copper['rows']]
        if len(rows) > 16384:
            raise ValueError('crossface_native_obstacle_bound')
        polygons = []
        for row in rows:
            shape, _, identity = row[:3]
            poly = pcbnew.SHAPE_POLY_SET()
            shape.TransformToPolygon(poly, 1000, pcbnew.ERROR_OUTSIDE)
            if not poly.OutlineCount():
                raise ValueError('crossface_native_obstacle_polygon_unavailable')
            total_vertices += sum(poly.COutline(i).PointCount()+sum(
                poly.CHole(i,j).PointCount() for j in range(poly.HoleCount(i)))
                for i in range(poly.OutlineCount()))
            if total_vertices > 500000:
                raise ValueError('crossface_native_polygon_work_bound')
            geom = polygon_from_native(poly)
            if not geom.is_valid or geom.is_empty:
                raise ValueError('crossface_native_invalid_obstacle_polygon')
            extra = (0 if identity.get('kind') == 'native_track_rule_area'
                     else max(clearance_nm, row[3] if len(row) > 3 else 0))/1e6
            # Polygonization/outside rounding reserve is conservative search
            # geometry. Native exact clearance remains the independent gate.
            polygons.append(geom.buffer(extra+.002, quad_segs=32))
        obstacles = unary_union(polygons)
        width = widths_nm.get(face)
        if width is not None:
            face_free[face] = material.buffer(-width/2e6-.502, quad_segs=32).difference(
                obstacles.buffer(width/2e6+.002, quad_segs=32))
        radius = via.GetWidth(face)/2e6
        land_free.append(material.buffer(-radius-.502, quad_segs=32).difference(
            obstacles.buffer(radius+.002, quad_segs=32)))
        inventory.append(dict(layer=board.GetLayerName(face), obstacles=len(rows),
                              native_land_diameter_nm=via.GetWidth(face)))
    transitions = land_free[0]
    for shape in land_free[1:]:
        transitions = transitions.intersection(shape)
    cache = {}
    def native_clear(at):
        if time.monotonic() >= deadline:
            return False
        point = pcbnew.VECTOR2I(*(round(v*1e6) for v in at))
        prior = tuple(via.GetPosition())
        via.SetPosition(point)
        try:
            return fr._via_spot_clear(board, point, max(context.values()),
                clearance_nm, {net_code}, drill_nm=via.GetDrillValue(), net_code=net_code,
                native_padstack_via=via, foreign_cache=cache) and fr._edge_leg_clear(
                    board, point, point, math.ceil(max(context.values())/2))
        finally:
            via.SetPosition(pcbnew.VECTOR2I(*prior))
    report = component_graph(face_free,
        source_points={k: [v/1e6 for v in p] for k,p in source_points_nm.items()},
        target_points={k: [v/1e6 for v in p] for k,p in target_points_nm.items()},
        transitions=transitions, native_transition_clear=native_clear,
        maximum_transitions=maximum_transitions, deadline=deadline)
    report.update(native_obstacle_inventory=inventory, polygon_vertices=total_vertices,
                  elapsed_s=timeout_s-(deadline-time.monotonic()),
                  polygon_map_is_search_hint_only=True)
    for gap in report['closest_unjoined_same_face_component_proposals']:
        face=gap['layer']
        points=[pcbnew.VECTOR2I(*(round(v*1e6) for v in gap[k]))
                for k in ('source_point_mm','target_point_mm')]
        zones,copper=fr._identified_foreign_shape_indexes(board,face,{net_code})
        gap['actual_native_shortcut_blockers']=fr._snapshot_foreign_blockers(
            *points,widths_nm[face],clearance_nm,zones,copper,limit=32)
    if time.monotonic() >= deadline:
        raise ValueError('crossface_native_diagnostic_deadline')
    return report, face_free, transitions
