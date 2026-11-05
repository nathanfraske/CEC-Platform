"""Conservative planar full-width launch-pocket evidence, never ampacity.

The complement of LOWER forbidden-center envelopes is a SUPERSET of legal
round-track centers.  An UPPER terminal/contact-center territory bounds every
endpoint permitted by the finite-contact premise.  Only enclosure of ALL its
possible free components can certify a local launch pocket.  Sample failure,
an omitted obstacle, or a small routing window cannot certify one.

Only native simple, flashed, hole-free SMD pads are used in this first slice.
Tracks, zones, holes, same-net leaves, board edges and nonplanar transitions
are deliberately omitted: that enlarges free space.  Native rounded-pad
ERROR_INSIDE/OUTSIDE polygon envelopes are supported; unlinearized polygon
arcs and unsupported pad shapes are unknown.  No current floor, contact
policy, placement, copper, or electrical qualification is changed here.
"""
from __future__ import annotations

import hashlib
import json
import math
import time

SCHEMA = 1
ERROR_NM = 1000
GUARD_NM = 2
JOIN_GUARD_NM = 4
BUFFER_QUADRANTS = 64
MAX_PADS = 4096
MAX_OBSTACLES = 256
MAX_VERTICES = 65536
MAX_COMPONENTS = 256
MAX_MINKOWSKI_VERTICES = 200_000
MAX_WIDTH_NM = 100_000_000
MAX_COORDINATE_NM = 2_000_000_000
SCOPE = "planar_constant_width_round_track_launch_only_not_global_no_path"


class Unknown(RuntimeError):
    pass


def _identity(pad):
    fp, at = pad.GetParentFootprint(), pad.GetPosition()
    return dict(uuid=str(pad.m_Uuid.AsString()),
        footprint_uuid=str(fp.m_Uuid.AsString()) if fp else None,
        ref=str(fp.GetReference()) if fp else None, pad=str(pad.GetNumber()),
        net=str(pad.GetNetname()), position_nm=[int(at.x), int(at.y)])


def _key(pad):
    row = _identity(pad)
    return row["footprint_uuid"], row["uuid"]


class _Work:
    def __init__(self, deadline, max_obstacles, max_vertices):
        self.deadline = deadline
        self.max_obstacles, self.max_vertices = max_obstacles, max_vertices
        self.vertices = 0

    def tick(self):
        if time.monotonic() >= self.deadline:
            raise Unknown("launch_pocket_deadline_exhausted")


def _parts(shape):
    if shape.is_empty:
        return []
    if shape.geom_type == "Polygon":
        return [shape]
    if shape.geom_type in ("MultiPolygon", "GeometryCollection"):
        return [part for item in shape.geoms for part in _parts(item)]
    raise Unknown("non_areal_boolean_result")


def _valid(shape, *, nonempty=False):
    if (not shape.is_valid or (nonempty and (shape.is_empty or shape.area <= 0))
            or (not shape.is_empty and any(not math.isfinite(v) for v in shape.bounds))):
        raise Unknown("invalid_or_uncertain_boolean_geometry")
    return shape


def _native_polygon(pad, layer, outside, work):
    import pcbnew
    from shapely.geometry import Polygon
    work.tick()
    native = pcbnew.SHAPE_POLY_SET()
    pad.TransformShapeToPolygon(native, layer, 0, ERROR_NM,
        pcbnew.ERROR_OUTSIDE if outside else pcbnew.ERROR_INSIDE, False)
    if native.OutlineCount() != 1 or native.HoleCount(0):
        raise Unknown("unsupported_native_pad_regions")
    chain = native.Outline(0)
    if chain.ArcCount():
        raise Unknown("unlinearized_native_pad_arc")
    work.vertices += chain.PointCount()
    if work.vertices > work.max_vertices:
        raise Unknown("launch_pocket_vertex_bound")
    points = [[int(chain.CPoint(i).x), int(chain.CPoint(i).y)]
              for i in range(chain.PointCount())]
    if len(points) < 3 or any(abs(v) > MAX_COORDINATE_NM for p in points for v in p):
        raise Unknown("native_polygon_coordinates_unavailable")
    shape = _valid(Polygon(points), nonempty=True)
    return shape, points


def _pad_geometry(pad, layer, work):
    """Replayable native envelopes; unsupported geometry never uses a bbox."""
    import pcbnew
    work.tick()
    if (pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD or pad.HasHole()
            or pad.GetShape(layer) not in (pcbnew.PAD_SHAPE_RECT, pcbnew.PAD_SHAPE_ROUNDRECT)):
        raise Unknown("unsupported_planar_pad_geometry")
    if not pad.IsOnLayer(layer) or not pad.FlashLayer(layer):
        raise Unknown("native_pad_copper_not_flashed")
    offset = pad.GetOffset(layer)
    if offset.x or offset.y:
        raise Unknown("unsupported_offset_pad_geometry")
    before = _identity(pad)
    lower, inside = _native_polygon(pad, layer, False, work)
    upper, outside = _native_polygon(pad, layer, True, work)
    lower_guard = _valid(lower.buffer(-GUARD_NM, join_style=2), nonempty=True)
    upper_guard = _valid(upper.buffer(GUARD_NM, join_style=2), nonempty=True)
    if (not lower.covers(lower_guard) or not upper_guard.covers(upper)
            or not upper_guard.covers(lower_guard) or before != _identity(pad)):
        raise Unknown("native_pad_envelope_or_identity_uncertain")
    size = pad.GetSize(layer)
    row = dict(identity=before, layer_id=int(layer), shape=int(pad.GetShape(layer)),
        copper_layer_ids=sorted(map(int, pad.GetLayerSet().CuStack())),
        size_nm=[int(size.x), int(size.y)],
        orientation_degrees=float(pad.GetOrientationDegrees()),
        offset_nm=[int(offset.x), int(offset.y)], flashed=True, hole=False,
        native_inside_nm=inside, native_outside_nm=outside)
    row["geometry_sha256"] = hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()
    return lower_guard, upper_guard, row


def _buffer(shape, distance, *, upper):
    """Round polygon Minkowski envelope; inscribed lower, circumscribed upper."""
    radius = distance - GUARD_NM
    if upper:
        # A scaled GEOS round buffer is NOT a proven upper bound: its arc
        # tessellation can round the per-corner segment count. Use an actual
        # circumscribed regular polygon and the convex Minkowski vertex sum.
        # Convex-hulling the source only enlarges its upper envelope.
        from shapely.geometry import MultiPoint
        count = 4*BUFFER_QUADRANTS
        vertices = list(shape.convex_hull.exterior.coords)[:-1]
        if len(vertices)*count > MAX_MINKOWSKI_VERTICES:
            raise Unknown("launch_pocket_minkowski_vertex_bound")
        radius = (distance+GUARD_NM)/math.cos(math.pi/count)
        offsets = [(radius*math.cos(2*math.pi*i/count),
                    radius*math.sin(2*math.pi*i/count)) for i in range(count)]
        return _valid(MultiPoint([(x+dx,y+dy) for x,y in vertices
                                  for dx,dy in offsets]).convex_hull, nonempty=True)
    if radius <= 0:
        raise Unknown("invalid_offset_radius")
    return _valid(shape.buffer(radius, quad_segs=BUFFER_QUADRANTS, join_style=1),
                  nonempty=True)


def _connected_groups(parts, work):
    """Merge point contacts / numerical near-contacts instead of hiding exits."""
    if len(parts) > MAX_COMPONENTS:
        raise Unknown("launch_pocket_component_bound")
    parent = list(range(len(parts)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, a in enumerate(parts):
        for j in range(i):
            work.tick()
            if a.distance(parts[j]) <= JOIN_GUARD_NM:
                parent[root(i)] = root(j)
    result = {}
    for i in range(len(parts)):
        result.setdefault(root(i), []).append(i)
    return list(result.values())


def _validate_epoch(board, source, obstacles, layer, work):
    if layer not in set(board.GetEnabledLayers().CuStack()):
        raise Unknown("launch_pocket_geometry_identity_changed")
    live = {}
    count = 0
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            work.tick()
            count += 1
            if count > MAX_PADS:
                raise Unknown("launch_pocket_pad_inventory_bound")
            key = _key(pad)
            if key in live:
                raise Unknown("ambiguous_native_pad_identity")
            live[key] = pad
    for row in [source, *obstacles]:
        work.tick()
        ident = row["identity"]
        pad = live.get((ident["footprint_uuid"], ident["uuid"]))
        if pad is None:
            raise Unknown("launch_pocket_geometry_identity_changed")
        _lo, _hi, current = _pad_geometry(pad, layer, work)
        if current != row:
            raise Unknown("launch_pocket_geometry_identity_changed")


def audit(board, pad, layer, *, width_nm, clearance_nm, contact_inset_nm=50_000,
          deadline=None, max_obstacles=MAX_OBSTACLES, max_vertices=MAX_VERTICES):
    """Return a conservative, bounded enclosure certificate or typed unknown.

    No source/sink current is inferred. ``width_nm`` is the caller's unchanged
    rated floor. The contact premise is the existing finite interior disk in
    the native pad contained by a conservative round endpoint cap. Nothing
    here proves terminal, solder, via, polygon-spreading or thermal capacity.
    """
    import pcbnew
    from shapely.geometry import box
    from shapely.ops import unary_union
    from shapely.errors import GEOSException

    for name, value, low, high in (
        ("width_nm", width_nm, 1, MAX_WIDTH_NM),
        ("clearance_nm", clearance_nm, 0, 5_000_000),
        ("contact_inset_nm", contact_inset_nm, 1, 500_000),
        ("max_obstacles", max_obstacles, 1, MAX_OBSTACLES),
        ("max_vertices", max_vertices, 16, MAX_VERTICES),
        ("layer", layer, 0, 127)):
        if type(value) is not int or not low <= value <= high:
            raise ValueError(name + " outside hard bounds")
    if width_nm < 2*(contact_inset_nm+1):
        raise ValueError("width cannot contain the required finite contact disk")
    if deadline is not None and (type(deadline) not in (int, float)
            or not math.isfinite(deadline) or deadline < 0):
        raise ValueError("deadline must be finite nonnegative monotonic time")
    work = _Work(time.monotonic()+3 if deadline is None else deadline,
                 max_obstacles, max_vertices)
    report = dict(schema=SCHEMA, operation="terminal_launch_pocket", scope=SCOPE,
        status="unknown", certified=None, reason="not_assessed", geometry_only=True,
        physical_no_path_proof=False, electrical_capacity_qualified=False,
        release_authority=False, placement_prerequisite=None,
        width_nm=width_nm, clearance_nm=clearance_nm,
        contact_inset_nm=contact_inset_nm, layer_id=layer, terminal=_identity(pad),
        premise="round_endpoint_contains_native_interior_contact_disk",
        omitted_obstacles=["tracks", "zones", "non_smd_pads", "holes",
            "same_net_leaves", "board_edges"],
        recipe=dict(native_error_nm=ERROR_NM, numeric_guard_nm=GUARD_NM,
            component_join_guard_nm=JOIN_GUARD_NM, buffer_quadrants=BUFFER_QUADRANTS,
            source="ERROR_OUTSIDE_plus_guard_circumscribed_contact_radius",
            upper_offset="convex_Minkowski_sum_with_circumscribed_regular_256_gon",
            obstacles="ERROR_INSIDE_minus_guard_inscribed_radius_plus_clearance",
            free_space="bounded_rectangle_minus_lower_forbidden_center_union",
            samples_are_not_proof=True),
        limits=dict(max_pads=MAX_PADS, max_obstacles=max_obstacles,
            max_vertices=max_vertices, max_components=MAX_COMPONENTS,
            max_minkowski_vertices=MAX_MINKOWSKI_VERTICES))
    try:
        work.tick()
        enabled = set(board.GetEnabledLayers().CuStack())
        report["enabled_copper_layer_ids"] = sorted(map(int, enabled))
        own_layers = set(pad.GetLayerSet().CuStack()) & enabled
        if layer not in enabled or own_layers != {layer}:
            raise Unknown("single_enabled_planar_terminal_required")
        if not pad.GetNetCode() or not str(pad.GetNetname()):
            raise Unknown("resolved_terminal_net_required")
        _source_lo, source_hi, source_row = _pad_geometry(pad, layer, work)
        # Positive finite pad-contact existence is only a witness, never the
        # enclosure proof or an exhaustive cap-center grid.
        import cec_pad_surface_access as contact
        contacts = contact.sample(pad, layer, contact_inset_nm=contact_inset_nm,
                                  axis_samples=3, deadline=work.deadline)
        if not contacts["points"]:
            raise Unknown("finite_native_interior_contact_not_witnessed")
        report["interior_contact_witness_nm"] = contacts["points"][0]
        radius = width_nm//2
        territory = _buffer(source_hi, radius-contact_inset_nm, upper=True)
        padding = max(width_nm, 2_000_000)
        x0, y0, x1, y1 = territory.bounds
        bounds = [math.floor(x0-padding), math.floor(y0-padding),
                  math.ceil(x1+padding), math.ceil(y1+padding)]
        if any(abs(v) > MAX_COORDINATE_NM for v in bounds):
            raise Unknown("launch_pocket_coordinate_bound")
        region = box(*bounds)
        if not region.covers(territory) or territory.distance(region.boundary) < padding-1:
            raise Unknown("contact_territory_not_inside_diagnostic_region")
        report.update(source_geometry=source_row, region_nm=bounds,
            conservative_cap_radius_nm=radius, contact_territory_bounds_nm=list(territory.bounds))
        forbidden, rows, seen = [], [], set()
        count, omitted = 0, 0
        for fp in board.GetFootprints():
            for other in fp.Pads():
                work.tick()
                count += 1
                if count > MAX_PADS:
                    raise Unknown("launch_pocket_pad_inventory_bound")
                key = _key(other)
                if key in seen:
                    raise Unknown("ambiguous_native_pad_identity")
                seen.add(key)
                if (other.GetNetCode() == pad.GetNetCode()
                        or not other.IsOnLayer(layer)
                        or other.GetAttribute() != pcbnew.PAD_ATTRIB_SMD
                        or other.HasHole() or not other.FlashLayer(layer)):
                    omitted += 1
                    continue
                # Bbox rejection only omits obstacles, enlarging free space;
                # it is never substituted for a certified copper polygon.
                bb = other.GetBoundingBox()
                loose = box(bb.GetLeft(), bb.GetTop(), bb.GetRight(), bb.GetBottom())
                if loose.distance(region) > radius+clearance_nm+ERROR_NM+GUARD_NM:
                    omitted += 1
                    continue
                lower, _upper, row = _pad_geometry(other, layer, work)
                obstacle = _buffer(lower, radius+clearance_nm, upper=False)
                if not obstacle.intersects(region):
                    omitted += 1
                    continue
                if len(rows) >= max_obstacles:
                    raise Unknown("launch_pocket_obstacle_bound")
                rows.append(row)
                forbidden.append(obstacle)
        report["counts"] = dict(inventory_pads=count, used_obstacles=len(rows),
                                 deliberately_omitted_pads=omitted)
        report["obstacle_geometry"] = rows
        work.tick()
        blocked = _valid(unary_union(forbidden))
        free = _valid(region.difference(blocked))
        reconstructed = _valid(unary_union([free, blocked.intersection(region)]))
        if (not reconstructed.covers(region) or not region.difference(reconstructed).is_empty
                or free.intersection(blocked).area > 0):
            raise Unknown("free_space_boolean_coverage_uncertain")
        parts = _parts(free)
        groups = _connected_groups(parts, work)
        components = []
        for indices in groups:
            work.tick()
            combined = _valid(unary_union([parts[i] for i in indices]), nonempty=True)
            if not combined.intersects(territory):
                continue
            intersects = _valid(combined.intersection(territory))
            if intersects.is_empty or intersects.area <= 0:
                raise Unknown("contact_territory_boundary_only_uncertain")
            clearance = combined.distance(region.boundary)
            boundary = [i for i, obstacle in enumerate(forbidden)
                        if combined.boundary.distance(obstacle.boundary) <= JOIN_GUARD_NM]
            components.append(dict(part_indices=indices, bounds_nm=list(combined.bounds),
                area_nm2=combined.area, possible_contact_area_nm2=intersects.area,
                diagnostic_boundary_distance_nm=clearance,
                enclosed=clearance > JOIN_GUARD_NM,
                obstacle_indices=boundary))
        report.update(possible_launch_components=components,
                      free_component_count=len(groups))
        if not components:
            raise Unknown("no_nonempty_possible_launch_component")
        if set(board.GetEnabledLayers().CuStack()) != enabled:
            raise Unknown("launch_pocket_geometry_identity_changed")
        _validate_epoch(board, source_row, rows, layer, work)
        report["geometry_identity_verified"] = True
        report["counts"]["native_vertices_checked"] = work.vertices
        if any(not row["enclosed"] for row in components):
            report.update(status="not_enclosed", certified=False,
                reason="possible_launch_component_reaches_diagnostic_boundary")
        else:
            report.update(status="enclosed", certified=True,
                reason="full_width_planar_launch_components_enclosed",
                placement_prerequisite=dict(required_for_planar_exit=True,
                    kind="terminal_clearance_placement_prerequisite",
                    scope="current_planar_round_track_and_contact_contract_only",
                    condition="authoritative_rated_path_must_exit_this_launch_component",
                    complete_domain_placement_infeasible=None,
                    width_or_contact_waiver_authorized=False,
                    nonplanar_or_variable_width_feasibility="not_assessed",
                    retry_same_placement=False,
                    recheck_after="materially_changed_terminal_or_obstacle_placement",
                    rerun_recipe="same_net_layer_width_clearance_contact_and_native_envelope_parameters"))
    except Unknown as exc:
        report.update(status="unknown", certified=None, reason=str(exc), placement_prerequisite=None)
    except GEOSException:
        report.update(status="unknown", certified=None,
            reason="geos_geometry_uncertain", placement_prerequisite=None)
    except Exception as exc:  # A native/API gap is evidence absence, never pass.
        report.update(status="unknown", certified=None,
            reason="native_geometry_unavailable", error_type=type(exc).__name__,
            placement_prerequisite=None)
    return report
