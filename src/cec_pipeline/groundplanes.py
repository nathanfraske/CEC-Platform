"""Exact-source extension of one existing Ground zone; no current authority.

The saved receiver admits only monotonic, source-component-rooted filled
copper. Every other native object and every selected-zone setting/cutout is
literal. Electrical, thermal, clearance and fabrication gates remain due.
"""
from __future__ import annotations

from pathlib import Path
import time

from .identity import digest, require, family, code_identity, inspection
from .legacy import bootstrap

bootstrap()


def _tick(deadline):
    require(time.monotonic() < deadline, 'ground_plane_receiving_deadline')


def _rings(poly):
    require(poly.OutlineCount() == 1, 'one_existing_ground_outer_required')
    def points(chain):
        return [[int(chain.CPoint(i).x), int(chain.CPoint(i).y)] for i in range(chain.PointCount())]
    return [points(poly.COutline(0)), *[points(poly.CHole(0, i)) for i in range(poly.HoleCount(0))]]


def _poly(rings):
    import pcbnew
    result = pcbnew.SHAPE_POLY_SET(); result.NewOutline()
    for x, y in rings[0]: result.Append(x, y, 0, -1)
    for index, hole in enumerate(rings[1:]):
        result.NewHole(0)
        for x, y in hole: result.Append(x, y, 0, index)
    return result


def _canonical(points):
    values = [tuple(p) for p in points]
    start = min(range(len(values)), key=values.__getitem__)
    forward = values[start:] + values[:start]
    backward = [forward[0], *reversed(forward[1:])]
    return min(forward, backward)


def _area2(poly, deadline):
    """Integer twice-area of native saved copper, including real holes."""
    require(poly.OutlineCount() <= 4096, 'bounded_native_ground_components_required')
    total, vertices = 0, 0
    def area(chain):
        nonlocal vertices
        count = chain.PointCount(); vertices += count
        require(vertices <= 262144, 'bounded_native_ground_vertices_required')
        value = 0
        for i in range(count):
            if i % 256 == 0: _tick(deadline)
            a, b = chain.CPoint(i), chain.CPoint((i+1) % count)
            value += int(a.x)*int(b.y)-int(a.y)*int(b.x)
        return abs(value)
    for i in range(poly.OutlineCount()):
        _tick(deadline)
        total += area(poly.COutline(i))
        total -= sum(area(poly.CHole(i, h)) for h in range(poly.HoleCount(i)))
    require(total >= 0, 'invalid_native_ground_area')
    return total


def _difference(a, b, deadline):
    _tick(deadline)
    result = a.CloneDropTriangulation(); result.BooleanSubtract(b)
    _tick(deadline)
    return result


def _intersection(a, b, deadline):
    _tick(deadline)
    result = a.CloneDropTriangulation(); result.BooleanIntersection(b)
    _tick(deadline)
    return result


def _zone(board, uid):
    import pcbnew
    zones = [zone for zone in board.Zones() if str(zone.m_Uuid.AsString()) == uid]
    require(len(zones) == 1, 'one_exact_source_ground_zone_required')
    zone = zones[0]
    faces = list(zone.GetLayerSet().CuStack())
    require(not zone.GetIsRuleArea() and zone.GetNetname() == 'GND'
            and 1 <= len(faces) <= 6
            and all(face in board.GetEnabledLayers().CuStack() for face in faces)
            and zone.GetMinThickness() > 0,
            'existing_enabled_ground_zone_and_source_feature_floor_required')
    require(all(pcbnew.IsCopperLayer(face) for face in faces), 'ground_copper_faces_required')
    require(set(zone.GetLayerSet().Seq()) == set(faces), 'ground_zone_non_copper_faces_forbidden')
    return zone


def _plan(board, source, operation, deadline):
    import cec_exact_outline_topology as topology
    require(type(operation) is dict and set(operation) == {'kind', 'zone_uuid', 'outline_nm'}
            and operation['kind'] == 'ground_plane_extension'
            and type(operation['zone_uuid']) is str and operation['zone_uuid'],
            'exact_ground_plane_extension_fields_required')
    points = operation['outline_nm']
    require(type(points) is list and 4 <= len(points) <= 64
            and all(type(p) is list and len(p) == 2
                    and all(type(v) is int and abs(v) <= 2_000_000_000 for v in p) for p in points),
            'bounded_integer_ground_outer_required')
    require(all(a != b and (a[0] == b[0] or a[1] == b[1]
                    or abs(a[0]-b[0]) == abs(a[1]-b[1]))
                for a, b in zip(points, points[1:]+points[:1])),
            'cardinal_or_45deg_ground_outer_required')
    zone = _zone(board, operation['zone_uuid']); old = _rings(zone.Outline())
    topology.require_one_polygon([old], deadline_monotonic=deadline)
    new = [points, *old[1:]]
    topology.require_one_polygon([new], deadline_monotonic=deadline)
    old_outer, new_outer = _poly([old[0]]), _poly([points])
    require(_difference(old_outer, new_outer, deadline).OutlineCount() == 0,
            'ground_outer_must_contain_entire_source_outer')
    require(_area2(new_outer, deadline) > _area2(old_outer, deadline),
            'strict_ground_outer_extension_required')
    return dict(kind='ground_plane_extension', zone_uuid=operation['zone_uuid'],
                source=str(Path(source).resolve()), source_sha256=inspection.sha(source),
                source_outline_nm=old[0], source_cutouts_nm=old[1:], outline_nm=points,
                source_faces=[int(face) for face in zone.GetLayerSet().CuStack()],
                source_min_thickness_nm=int(zone.GetMinThickness()),
                source_zone_locked=bool(zone.IsLocked()),
                no_parts_tracks_barrels_or_foreign_zones_authorized=True,
                source_ground_not_current_authority=True, release_authority=False)


def construct(board, source, operation, *, board_hint, request):
    import pcbnew
    import cec_zone_fill as fill
    require(type(request) is dict and request.get('operations') == [operation],
            'one_exact_ground_extension_per_transaction_required')
    deadline = time.monotonic()+8.0
    record = _plan(board, source, operation, deadline)
    zone = _zone(board, operation['zone_uuid'])
    shape = _poly([operation['outline_nm'], *record['source_cutouts_nm']])
    zone.Outline().RemoveAllContours(); zone.Outline().Append(shape)
    selected = pcbnew.ZONES(); selected.append(zone)
    fill.compile_selected(board, selected, timeout_s=8.0, initialize_selected=True)
    return record


def _literal_residue(source, candidate, uid):
    import cec_additive_route_receiving as native
    import cec_copper_echo as syntax
    roots, nodes = zip(*(native._nodes(path) for path in (source, candidate)))
    require(nodes[0].keys() == nodes[1].keys(), 'ground_extension_native_population_changed')
    for key in nodes[0]:
        if key != uid:
            require(syntax._freeze(nodes[0][key]) == syntax._freeze(nodes[1][key]),
                    'ground_extension_changed_unowned_native_object')
    def globals_only(root, objects):
        values = {id(node) for node in objects.values()}
        return syntax._freeze([part for part in root if id(part) not in values])
    require(globals_only(roots[0], nodes[0]) == globals_only(roots[1], nodes[1]),
            'ground_extension_changed_global_context')
    def settings(node):
        return syntax._freeze([part for part in node if not
            (isinstance(part, list) and part and part[0] in ('polygon', 'filled_polygon'))])
    require(settings(nodes[0][uid]) == settings(nodes[1][uid]),
            'ground_extension_changed_zone_settings')


def receive(source, candidate, operation, record, *, board_hint):
    import pcbnew
    import cec_force_current as force
    import cec_zone_fill as fill
    import cec_native_fill_geometry as fill_geometry
    deadline = time.monotonic()+8.0
    paths = [Path(path).resolve(strict=True) for path in (source, candidate)]
    require(paths[0] != paths[1], 'distinct_saved_ground_source_and_candidate_required')
    families = [family(path) for path in paths]; epoch = code_identity()
    require(force._sidecars(paths[0]) == force._sidecars(paths[1]),
            'ground_extension_project_companions_changed')
    before, after = [pcbnew.LoadBoard(str(path)) for path in paths]
    fresh = _plan(before, paths[0], operation, deadline)
    require(digest(record) == digest(fresh), 'stale_or_forged_ground_extension_record')
    _literal_residue(*paths, operation['zone_uuid'])
    old, new = [_zone(board, operation['zone_uuid']) for board in (before, after)]
    rings = _rings(new.Outline())
    require(_canonical(rings[0]) == _canonical(operation['outline_nm'])
            and rings[1:] == fresh['source_cutouts_nm'],
            'saved_ground_outer_or_source_cutouts_changed')
    require(list(old.GetLayerSet().CuStack()) == list(new.GetLayerSet().CuStack()),
            'ground_source_faces_changed')
    # Rebuild independently from immutable Source, never from candidate fill
    # or the constructor. Area/rooting alone cannot exclude substituted thin
    # necks or other material the authored outline's native filler never made.
    expected_board = pcbnew.LoadBoard(str(paths[0]))
    expected_zone = _zone(expected_board, operation['zone_uuid'])
    expected_outline = _poly([operation['outline_nm'], *fresh['source_cutouts_nm']])
    expected_zone.Outline().RemoveAllContours()
    expected_zone.Outline().Append(expected_outline)
    selected = pcbnew.ZONES(); selected.append(expected_zone)
    _tick(deadline)
    fill.compile_selected(expected_board, selected,
                          timeout_s=min(8.0, deadline-time.monotonic()),
                          initialize_selected=True)
    _tick(deadline)
    faces = []; added_total2 = 0
    for face in old.GetLayerSet().CuStack():
        _tick(deadline)
        require(old.IsFilled() and new.IsFilled()
                and old.HasFilledPolysForLayer(face) and new.HasFilledPolysForLayer(face),
                'actual_saved_source_and_candidate_ground_fill_required')
        initial, final = [zone.GetFilledPolysList(face).CloneDropTriangulation() for zone in (old, new)]
        require(expected_zone.IsFilled() and expected_zone.HasFilledPolysForLayer(face),
                'independent_native_ground_fill_unavailable')
        expected = expected_zone.GetFilledPolysList(face).CloneDropTriangulation()
        require(fill_geometry.identity(final, deadline) == fill_geometry.identity(expected, deadline),
                'saved_ground_fill_not_exact_independent_native_fill')
        require(_difference(final, new.Outline(), deadline).OutlineCount() == 0,
                'saved_ground_fill_outside_authored_zone_or_inside_cutout')
        initial_area = _area2(initial, deadline); final_area = _area2(final, deadline)
        require(initial_area > 0, 'nonempty_source_ground_material_required')
        require(_difference(initial, final, deadline).OutlineCount() == 0,
                'saved_ground_source_material_was_removed')
        addition = _difference(final, initial, deadline); added = _area2(addition, deadline)
        require(final_area-initial_area == added, 'ground_fill_area_identity_changed')
        if added:
            require(added >= 2*fresh['source_min_thickness_nm']**2,
                    'ground_addition_below_source_feature_area')
            for index in range(final.OutlineCount()):
                component = final.CloneDropTriangulation()
                for other in reversed(range(final.OutlineCount())):
                    if other != index: component.DeletePolygon(other)
                if _area2(_intersection(component, addition, deadline), deadline):
                    require(_area2(_intersection(component, initial, deadline), deadline) > 0,
                            'ground_addition_not_rooted_in_original_saved_component')
        faces.append(dict(layer_id=int(face), source_area2_nm2=initial_area,
                          candidate_area2_nm2=final_area, added_area2_nm2=added))
        added_total2 += added
    require(added_total2 > 0, 'meaningful_actual_ground_fill_addition_required')
    _tick(deadline)
    require(families == [family(path) for path in paths] and epoch == code_identity(),
            'ground_extension_source_candidate_or_code_changed')
    return dict(ok=True, complete=True, scope='exact_saved_monotonic_source_component_ground_extension',
                zone_uuid=operation['zone_uuid'], faces=faces,
                minimum_added_area_nm2=fresh['source_min_thickness_nm']**2,
                rooting_basis='positive_area_overlap_with_original_saved_ground_component',
                current_qualified=False, thermal_qualified=False, assembly_qualified=False,
                release_authority=False)
