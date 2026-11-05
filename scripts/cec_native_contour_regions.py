"""Source-retaining native power contours with real windows and split regions.

The single-outline owner deliberately refuses holed/disconnected unions. This
opt-in owner derives a bounded polygon set from the SAME actual track capsules,
keeps all of those tracks, and saves native KiCad holes rather than a convex
filler slab. Separate regions do not become a claimed electrical connection.
It grants no sharing, current, thermal, clearance or release qualification.
"""
from __future__ import annotations

import math
import time
import uuid

import cec_rectilinear_copper as owner

ZONE_NAME = "CEC_NATIVE_POWER_CONTOUR_REGIONS"
SCOPE = "retained_native_capsules_and_signed_regions_not_current_authority"
MAX_REGIONS = 8
MAX_HOLES = 32
MAX_VERTICES = 8192
PARAMETERS = ("required_width_nm", "clearance_nm", "min_thickness_nm", "contour_style",
              "contour_grid_nm", "envelope_margin_nm", "fill_envelope_margin_nm")
PLAN_KEYS = {"schema", "scope", "source_tracks", "regions_nm", "actual_fill_regions_nm",
    "supporting_zones", "source_geometry_binding", "net", "layer_id", "group_uuid", "locked",
    *PARAMETERS, "priority", "source_tracks_retained", "separate_regions_electrically_connected_inferred",
    "filled_copper_received", "new_capacity_credited", "release_authority", "plan_sha256"}


def _parameters(values):
    if (any(type(values.get(k)) is not int for k in PARAMETERS if k != "contour_style")
            or not 1 <= values["required_width_nm"] <= 100_000_000
            or not 0 <= values["clearance_nm"] <= 10_000_000
            or not 1 <= values["min_thickness_nm"] <= 1_000_000
            or not 1 <= values["contour_grid_nm"] <= 100_000
            or not 1 <= values["envelope_margin_nm"] <= 100_000
            or not 0 <= values["fill_envelope_margin_nm"] <= 10
            or values.get("contour_style") not in ("square", "chamfer45")):
        raise owner.Refused("bounded_explicit_native_region_parameters_required")


def _track_index(board):
    items = list(board.GetTracks())
    index = {t.m_Uuid.AsString(): t for t in items}
    if len(items) > 8192 or len(index) != len(items):
        raise owner.Refused("bounded_unique_native_region_source_inventory_required")
    return index


def _deadline(seconds):
    if (type(seconds) not in (int, float) or not math.isfinite(seconds)
            or not 0 < seconds <= 10):
        raise owner.Refused("bounded_native_region_deadline_required")
    return time.monotonic() + seconds


def _ring(coordinates, style):
    points = list(coordinates)[:-1]
    if (not 4 <= len(points) <= 1024
            or any(v != int(v) or abs(v) > 2_000_000_000 for p in points for v in p)):
        raise owner.Refused("bounded_integer_native_region_ring_required")
    result = [[int(x), int(y)] for x, y in points]
    if any(a == b or (a[0] != b[0] and a[1] != b[1]
           and (style != "chamfer45" or abs(a[0]-b[0]) != abs(a[1]-b[1])))
           for a, b in zip(result, result[1:]+result[:1])):
        raise owner.Refused("canonical_native_region_edges_required")
    at = min(range(len(result)), key=result.__getitem__)
    return result[at:] + result[:at]


def _serialize(shape, style):
    from shapely.geometry import Polygon, MultiPolygon
    from shapely.geometry.polygon import orient
    if (not isinstance(shape, (Polygon, MultiPolygon)) or not shape.is_valid
            or shape.is_empty or shape.area <= 0):
        raise owner.Refused("valid_positive_native_regions_required")
    polygons = [shape] if isinstance(shape, Polygon) else list(shape.geoms)
    if not 1 <= len(polygons) <= MAX_REGIONS:
        raise owner.Refused("native_region_count_bound")
    result = []; holes = 0; vertices = 0
    for polygon in polygons:
        polygon = orient(polygon, sign=1.)
        outer = _ring(polygon.exterior.coords, style)
        inner = sorted(_ring(r.coords, style) for r in polygon.interiors)
        holes += len(inner); vertices += len(outer) + sum(map(len, inner))
        if holes > MAX_HOLES or vertices > MAX_VERTICES:
            raise owner.Refused("native_region_hole_or_vertex_bound")
        result.append(dict(outer_nm=outer, holes_nm=inner))
    return sorted(result, key=lambda r: r["outer_nm"])


def _shape(regions, style):
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    if (type(regions) is not list or not 1 <= len(regions) <= MAX_REGIONS
            or any(type(r) is not dict or set(r) != {"outer_nm", "holes_nm"}
                   or type(r["outer_nm"]) is not list or type(r["holes_nm"]) is not list
                   or not 4 <= len(r["outer_nm"]) <= 1024
                   or len(r["holes_nm"]) > MAX_HOLES
                   or any(type(ring) is not list or not 4 <= len(ring) <= 1024
                       or any(type(p) is not list or len(p) != 2
                           or any(type(v) is not int or abs(v) > 2_000_000_000 for v in p)
                           for p in ring)
                       for ring in [r["outer_nm"], *r["holes_nm"]])
                   for r in regions)):
        raise owner.Refused("explicit_bounded_signed_native_regions_required")
    pieces = [Polygon(r["outer_nm"], r["holes_nm"]) for r in regions]
    if any(not p.is_valid or p.is_empty for p in pieces):
        raise owner.Refused("invalid_native_region_topology")
    result = unary_union(pieces)
    if _serialize(result, style) != regions:
        raise owner.Refused("noncanonical_or_overlapping_native_region_inventory")
    return result


def native_poly(regions):
    import pcbnew
    result = pcbnew.SHAPE_POLY_SET()
    for index, region in enumerate(regions):
        result.NewOutline()
        for x, y in region["outer_nm"]:
            result.Append(x, y, index, -1)
        for hole, points in enumerate(region["holes_nm"]):
            result.NewHole(index)
            for x, y in points:
                result.Append(x, y, index, hole)
    return result


def canonical_native_regions(native, *, style="chamfer45", timeout_s=2.):
    """Read actual signed native outlines, not their bounding rectangles."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    deadline = _deadline(timeout_s)
    if style not in ("square", "chamfer45") or not 1 <= native.OutlineCount() <= MAX_REGIONS:
        raise owner.Refused("native_region_outline_bound")
    pieces = []; count = 0
    for index in range(native.OutlineCount()):
        owner._check_deadline(deadline)
        if native.HoleCount(index) > MAX_HOLES:
            raise owner.Refused("native_region_hole_bound")
        rings = []
        for ring in [native.Outline(index), *[native.Hole(index, j)
                     for j in range(native.HoleCount(index))]]:
            count += ring.PointCount()
            if ring.ArcCount() or not 4 <= ring.PointCount() <= 1024 or count > MAX_VERTICES:
                raise owner.Refused("native_region_ring_bound")
            rings.append([(int(ring.CPoint(k).x), int(ring.CPoint(k).y))
                          for k in range(ring.PointCount())])
        pieces.append(Polygon(rings[0], rings[1:]))
    if any(not p.is_valid or p.is_empty for p in pieces):
        raise owner.Refused("invalid_actual_native_region_topology")
    return _serialize(unary_union(pieces), style)


def _profiles(board, rows, style, grid, margin, fill_margin, deadline):
    import pcbnew
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    pieces = []; vertices = 0
    for row in rows:
        owner._check_deadline(deadline)
        track = pcbnew.PCB_TRACK(board)
        track.SetLayer(row["layer_id"]); track.SetWidth(row["width_nm"])
        track.SetStart(pcbnew.VECTOR2I(*row["start_nm"]))
        track.SetEnd(pcbnew.VECTOR2I(*row["end_nm"]))
        capsule = owner._native_capsule(track)
        vertices += capsule.Outline(0).PointCount()
        if vertices > 200_000:
            raise owner.Refused("native_region_capsule_vertex_bound")
        pieces.append(Polygon(owner.purposeful_envelope(capsule, style=style,
            margin_nm=margin, grid_nm=grid)))
    shape = unary_union(pieces)
    regions = _serialize(shape, style)
    return regions, _fill_domain(shape, regions, style, fill_margin, deadline)


def _fill_domain(shape, regions, style, fill_margin, deadline):
    from shapely.geometry import MultiPoint
    from shapely.ops import unary_union
    # Exact integer square Minkowski domain includes only declared nm-scale
    # fill construction slack. Sweeping ALL boundaries shrinks holes rather
    # than convex-filling them. No omitted source pixel or arbitrary slab.
    domain_pieces = [shape]
    if fill_margin:
        offsets = [(-fill_margin, -fill_margin), (-fill_margin, fill_margin),
                   (fill_margin, fill_margin), (fill_margin, -fill_margin)]
        for region in regions:
            for ring in [region["outer_nm"], *region["holes_nm"]]:
                for a, b in zip(ring, ring[1:]+ring[:1]):
                    owner._check_deadline(deadline)
                    domain_pieces.append(MultiPoint([(p[0]+dx, p[1]+dy)
                        for p in (a, b) for dx, dy in offsets]).convex_hull)
    return _serialize(unary_union(domain_pieces), style)


def _binding(board):
    import cec_field_coupling as field
    return owner._digest(sorted((str(k), v) for k, v in
                                field._field_snapshot_inventory(board).items()))


def _support_row(zone, layer, deadline, *, max_vertices=200_000):
    """Keep literal native hole bridges; never simplify them into filler."""
    from cec_native_fill_geometry import identity
    if zone.GetIsRuleArea() or not zone.IsFilled() or not zone.HasFilledPolysForLayer(layer):
        raise owner.Refused("native_region_support_not_filled")
    outline, a = identity(zone.Outline(), deadline, max_vertices=max_vertices)
    filled, b = identity(zone.GetFilledPolysList(layer), deadline, max_vertices=max_vertices-a)
    return dict(uuid=zone.m_Uuid.AsString(), net=zone.GetNetname(), layer_id=layer,
        priority=int(zone.GetAssignedPriority()), outline_sha256=outline, fill_sha256=filled,
        native_vertices=a+b)


def _receive_support(board, proposal, deadline):
    items = list(board.Zones()); zones = {z.m_Uuid.AsString(): z for z in items}
    if len(items) > 8192 or len(zones) != len(items):
        raise owner.Refused("native_region_support_zone_inventory_bound")
    rows = proposal["supporting_zones"]
    if (any(type(r) is not dict or type(r.get("uuid")) is not str for r in rows)
            or len({r["uuid"] for r in rows}) != len(rows)):
        raise owner.Refused("unique_native_region_support_rows_required")
    vertices = 0; result = []
    for row in rows:
        owner._check_deadline(deadline)
        zone = zones.get(row["uuid"])
        if (zone is None or not zone.IsOnLayer(proposal["layer_id"])
                or zone.GetNetname() != proposal["net"] or zone.GetAssignedPriority() <= proposal["priority"]):
            raise owner.Refused("native_region_support_identity_changed")
        actual = _support_row(zone, proposal["layer_id"], deadline, max_vertices=200_000-vertices)
        if actual != row:
            raise owner.Refused("native_region_support_copper_changed")
        vertices += actual["native_vertices"]; result.append(zone)
    return result


def plan(board, track_uuids, *, required_width_nm, clearance_nm,
         min_thickness_nm, allow_locked_track_uuids=(), allow_grouped_track_uuids=(),
         contour_style="chamfer45", contour_grid_nm=1000,
         envelope_margin_nm=1000, fill_envelope_margin_nm=4, timeout_s=10.):
    """Explicit opt-in geometry only; preserve every original conductor."""
    deadline = _deadline(timeout_s)
    _parameters(locals())
    if (type(track_uuids) not in (list, tuple) or not 1 <= len(track_uuids) <= 128
            or any(type(u) is not str or not u for u in track_uuids)
            or len(set(track_uuids)) != len(track_uuids)):
        raise owner.Refused("bounded_explicit_native_region_owner_required")
    index = _track_index(board)
    if not set(track_uuids) <= index.keys():
        raise owner.Refused("native_region_source_inventory_unavailable")
    items = [index[u] for u in sorted(track_uuids)]
    if any(t.GetClass() != "PCB_TRACK" for t in items):
        raise owner.Refused("native_region_straight_conductors_required")
    rows = [owner._track_row(t) for t in items]
    if (len({(r["net"], r["layer_id"], r["group_uuid"]) for r in rows}) != 1
            or not rows[0]["net"] or rows[0]["net"].rsplit("/", 1)[-1] == "GND"
            or rows[0]["layer_id"] not in board.GetEnabledLayers().CuStack()
            or any(r["width_nm"] < required_width_nm or r["width_nm"] <= min_thickness_nm
                or not owner._centerline_allowed(r["start_nm"], r["end_nm"], contour_style)
                or r["locked"] and r["uuid"] not in set(allow_locked_track_uuids)
                or r["group_uuid"] and r["uuid"] not in set(allow_grouped_track_uuids)
                for r in rows)):
        raise owner.Refused("exact_native_region_dimensions_layer_group_and_permissions_required")
    regions, domain = _profiles(board, rows, contour_style, contour_grid_nm,
        envelope_margin_nm, fill_envelope_margin_nm, deadline)
    net, layer = rows[0]["net"], rows[0]["layer_id"]
    profile = native_poly(regions)
    owner._require_unoccupied_outline(board, native_poly(domain), net, layer,
        deadline, clearance_nm=clearance_nm, allow_native_hole_bridges=True)
    owner._require_same_net_priority_available(board, profile, net, layer, deadline)
    support = []
    for zone in board.Zones():
        owner._check_deadline(deadline)
        if (zone.GetIsRuleArea() or zone.GetNetname() != net or not zone.IsOnLayer(layer)
                or not zone.IsFilled() or not zone.HasFilledPolysForLayer(layer)): continue
        overlap = zone.GetFilledPolysList(layer).CloneDropTriangulation()
        overlap.BooleanIntersection(profile)
        if overlap.OutlineCount():
            support.append(_support_row(zone, layer, deadline))
            if len(support) > 64: raise owner.Refused("native_region_support_bound")
    result = dict(schema=1, scope=SCOPE, source_tracks=rows, regions_nm=regions,
        actual_fill_regions_nm=domain, supporting_zones=sorted(support, key=lambda r: r["uuid"]),
        source_geometry_binding=_binding(board), net=net, layer_id=layer,
        group_uuid=rows[0]["group_uuid"], locked=any(r["locked"] for r in rows),
        required_width_nm=required_width_nm, clearance_nm=clearance_nm,
        min_thickness_nm=min_thickness_nm, contour_style=contour_style,
        contour_grid_nm=contour_grid_nm, envelope_margin_nm=envelope_margin_nm,
        fill_envelope_margin_nm=fill_envelope_margin_nm, priority=0,
        source_tracks_retained=True, separate_regions_electrically_connected_inferred=False,
        filled_copper_received=False, new_capacity_credited=False, release_authority=False)
    owner._check_deadline(deadline)
    result["plan_sha256"] = owner._digest(result)
    return result


def _validate(board, proposal, deadline, *, require_source_binding=False):
    if type(proposal) is not dict:
        raise owner.Refused("native_region_plan_required")
    if set(proposal) != PLAN_KEYS:
        raise owner.Refused("exact_native_region_plan_fields_required")
    check = dict(proposal); digest = check.pop("plan_sha256", None)
    _parameters(check)
    if (digest != owner._digest(check) or type(check.get("schema")) is not int or check["schema"] != 1
            or check.get("scope") != SCOPE or type(check.get("priority")) is not int
            or check.get("source_tracks_retained") is not True or check["priority"] != 0
            or type(check.get("locked")) is not bool or type(check.get("layer_id")) is not int
            or type(check.get("source_geometry_binding")) is not str
            or len(check["source_geometry_binding"]) != 64
            or type(check.get("supporting_zones")) is not list or len(check["supporting_zones"]) > 64
            or any(check.get(k) is not False for k in ("new_capacity_credited", "release_authority",
                "filled_copper_received", "separate_regions_electrically_connected_inferred"))):
        raise owner.Refused("native_region_plan_identity_or_authority_changed")
    rows = check.get("source_tracks")
    if (type(rows) is not list or not 1 <= len(rows) <= 128
            or any(type(r) is not dict or type(r.get("uuid")) is not str for r in rows)):
        raise owner.Refused("bounded_native_region_source_rows_required")
    index = _track_index(board)
    if (len({r.get("uuid") for r in rows}) != len(rows)
            or any(r.get("uuid") not in index or owner._track_row(index[r["uuid"]]) != r for r in rows)):
        raise owner.Refused("native_region_source_conductor_changed")
    if ((check["net"], check["layer_id"], check["group_uuid"]) != (
            rows[0]["net"], rows[0]["layer_id"], rows[0]["group_uuid"])
            or not check["net"] or check["net"].rsplit("/", 1)[-1] == "GND"
            or check["layer_id"] not in board.GetEnabledLayers().CuStack()
            or check["locked"] != any(r["locked"] for r in rows)
            or any((r["net"], r["layer_id"], r["group_uuid"]) != (
                check["net"], check["layer_id"], check["group_uuid"])
                or r["kind"] != "PCB_TRACK" or r["width_nm"] < check["required_width_nm"]
                or r["width_nm"] <= check["min_thickness_nm"]
                or not owner._centerline_allowed(r["start_nm"], r["end_nm"], check["contour_style"])
                for r in rows)):
        raise owner.Refused("native_region_plan_owner_changed")
    profiles = _profiles(board, rows, check["contour_style"], check["contour_grid_nm"],
        check["envelope_margin_nm"], check["fill_envelope_margin_nm"], deadline)
    if profiles != (check["regions_nm"], check["actual_fill_regions_nm"]):
        raise owner.Refused("native_regions_not_derived_from_actual_conductors")
    _shape(check["regions_nm"], check["contour_style"])
    _shape(check["actual_fill_regions_nm"], check["contour_style"])
    if require_source_binding and _binding(board) != check["source_geometry_binding"]:
        raise owner.Refused("native_region_source_geometry_binding_changed")
    return rows


def _zones(board, proposal, zone_uuids):
    if (type(zone_uuids) not in (list, tuple) or len(zone_uuids) != len(proposal["regions_nm"])
            or any(type(u) is not str or not u for u in zone_uuids)
            or len(set(zone_uuids)) != len(zone_uuids)):
        raise owner.Refused("exact_native_region_zone_identities_required")
    items = list(board.Zones()); index = {z.m_Uuid.AsString(): z for z in items}
    if len(items) > 8192 or len(index) != len(items) or not set(zone_uuids) <= index.keys():
        raise owner.Refused("native_region_zone_identity_unavailable")
    return [index[u] for u in zone_uuids]


def materialize(board, proposal, *, allow_locked_track_uuids=(), allow_grouped_track_uuids=(),
                zone_uuids=None, timeout_s=10.):
    """Private native construction only; no saving, track cuts or promotion."""
    import pcbnew
    deadline = _deadline(timeout_s)
    rows = _validate(board, proposal, deadline, require_source_binding=True)
    # Recompile all bounds/policies from the source, not a rehashed worker flag.
    replay = plan(board, [r["uuid"] for r in rows],
        **{k: proposal[k] for k in ("required_width_nm", "clearance_nm", "min_thickness_nm",
            "contour_style", "contour_grid_nm", "envelope_margin_nm", "fill_envelope_margin_nm")},
        allow_locked_track_uuids=allow_locked_track_uuids,
        allow_grouped_track_uuids=allow_grouped_track_uuids,
        timeout_s=max(.001, deadline-time.monotonic()))
    if replay != proposal: raise owner.Refused("native_region_source_plan_replay_changed")
    if zone_uuids is not None:
        try:
            valid = (type(zone_uuids) in (list, tuple)
                and len(zone_uuids) == len(proposal["regions_nm"])
                and all(type(u) is str and str(uuid.UUID(u)) == u for u in zone_uuids)
                and len(set(zone_uuids)) == len(zone_uuids))
        except (ValueError, TypeError):
            valid = False
        existing = {item.m_Uuid.AsString() for item in [*board.Zones(), *board.GetTracks(),
            *board.GetFootprints(), *board.GetDrawings(), *board.Groups(),
            *[p for fp in board.GetFootprints() for p in fp.Pads()]]}
        if not valid or set(zone_uuids) & existing:
            raise owner.Refused("fresh_native_region_zone_identity_required")
    groups = [g for g in board.Groups() if g.m_Uuid.AsString() == proposal["group_uuid"]]
    if proposal["group_uuid"] and len(groups) != 1:
        raise owner.Refused("native_region_parent_group_unavailable")
    net = board.FindNet(proposal["net"])
    zones = []
    # KiCad 10 serializes only the first outer contour of an authored ZONE.
    # Emit one literal zone PER region, keeping real holes within that zone.
    # An in-memory polygon set alone is not saved-board persistence evidence.
    for i, region in enumerate(proposal["regions_nm"]):
        zone = pcbnew.ZONE(board)
        if zone_uuids is not None: zone.m_Uuid.Clone(pcbnew.KIID(zone_uuids[i]))
        zone.SetNet(net); zone.SetLayer(proposal["layer_id"]); zone.SetZoneName(ZONE_NAME)
        zone.SetLocked(proposal["locked"]); zone.SetAssignedPriority(0)
        zone.SetLocalClearance(proposal["clearance_nm"]); zone.SetMinThickness(proposal["min_thickness_nm"])
        zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL); zone.SetCornerSmoothingType(0)
        zone.SetIsRuleArea(False)
        zone.Outline().Append(native_poly([region])); zones.append(zone)
    for zone in zones:
        board.Add(zone)
        if proposal["group_uuid"]: groups[0].AddItem(zone)
    return dict(zone_uuids=[z.m_Uuid.AsString() for z in zones], plan_sha256=proposal["plan_sha256"],
        retained_track_uuids=[r["uuid"] for r in rows], retired_track_uuids=[],
        new_capacity_credited=False, release_authority=False)


def fill(board, proposal, zone_uuids, *, timeout_s=10.):
    import pcbnew
    import cec_zone_fill
    _validate(board, proposal, _deadline(timeout_s))
    zones = _zones(board, proposal, zone_uuids)
    selected = pcbnew.ZONES()
    for zone in zones: selected.append(zone)
    board.BuildConnectivity()
    cec_zone_fill.compile_selected(board, selected, timeout_s=timeout_s)


def receive(board, proposal, zone_uuids, *, timeout_s=10., expected_zone_name=None):
    """Re-derive signed geometry and prove literal saved fill enclosure."""
    import pcbnew
    result = dict(schema=1, scope=SCOPE, ok=False, complete=False, reason=None,
        new_capacity_credited=False, release_authority=False, full_board_receiving_required=True)
    try:
        if expected_zone_name is None:expected_zone_name=ZONE_NAME
        if type(expected_zone_name) is not str or expected_zone_name not in (ZONE_NAME,owner.ZONE_NAME):
            raise owner.Refused('explicit_known_native_contour_zone_name_required')
        deadline = _deadline(timeout_s)
        rows = _validate(board, proposal, deadline)
        zones = _zones(board, proposal, zone_uuids)
        from cec_native_fill_geometry import identity
        actual = pcbnew.SHAPE_POLY_SET()
        for zone, region in zip(zones, proposal["regions_nm"]):
            owner._check_deadline(deadline)
            if (zone.GetZoneName() != expected_zone_name or zone.GetIsRuleArea()
                or zone.GetNetname() != proposal["net"] or set(zone.GetLayerSet().CuStack()) != {proposal["layer_id"]}
                or zone.IsLocked() != proposal["locked"] or zone.GetAssignedPriority() != 0
                or zone.GetLocalClearance() != proposal["clearance_nm"]
                or zone.GetMinThickness() != proposal["min_thickness_nm"]
                or zone.GetCornerSmoothingType() != 0 or zone.GetPadConnection() != pcbnew.ZONE_CONNECTION_FULL
                    or owner._group_uuid(zone) != proposal["group_uuid"]):
                raise owner.Refused("native_region_zone_configuration_changed")
            if canonical_native_regions(zone.Outline(), style=proposal["contour_style"],
                    timeout_s=max(.001, deadline-time.monotonic())) != [region]:
                raise owner.Refused("native_region_zone_outline_or_holes_changed")
            domain = native_poly(_fill_domain(_shape([region], proposal["contour_style"]),
                [region], proposal["contour_style"], proposal["fill_envelope_margin_nm"], deadline))
            owner._require_unoccupied_outline(board, domain, proposal["net"], proposal["layer_id"],
                deadline, clearance_nm=proposal["clearance_nm"], allow_native_hole_bridges=True)
            owner._require_same_net_priority_available(board, native_poly([region]), proposal["net"],
                proposal["layer_id"], deadline, own_zone_uuid=zone.m_Uuid.AsString())
            if not zone.IsFilled() or not zone.HasFilledPolysForLayer(proposal["layer_id"]):
                raise owner.Refused("native_region_saved_fill_unavailable")
            filled = zone.GetFilledPolysList(proposal["layer_id"])
            if not filled.OutlineCount(): raise owner.Refused("native_region_saved_fill_empty")
            identity(filled, deadline)
            spill = filled.CloneDropTriangulation(); spill.BooleanSubtract(domain)
            if spill.OutlineCount(): raise owner.Refused("native_region_fill_spills_into_undeclared_space")
            actual.BooleanAdd(filled)
        supports = _receive_support(board, proposal, deadline)
        for support in supports:
            actual.BooleanAdd(support.GetFilledPolysList(proposal["layer_id"]))
            for zone in zones:
                intrusion = zone.GetFilledPolysList(proposal["layer_id"]).CloneDropTriangulation()
                intrusion.BooleanIntersection(support.Outline())
                intrusion.BooleanSubtract(support.GetFilledPolysList(proposal["layer_id"]))
                if intrusion.OutlineCount(): raise owner.Refused("native_region_higher_priority_void_changed")
        missing = []
        items = {t.m_Uuid.AsString(): t for t in board.GetTracks()}
        for row in rows:
            owner._check_deadline(deadline)
            loss = owner._native_capsule(items[row["uuid"]]); loss.BooleanSubtract(actual)
            if loss.OutlineCount(): missing.append(row["uuid"])
        if missing:
            result["missing_source_track_uuids"] = missing
            raise owner.Refused("native_region_source_capsule_loss")
        result.update(ok=True, complete=True, reason="signed_native_regions_and_complete_capsules_received",
            verified_track_count=len(rows), region_count=len(proposal["regions_nm"]),
            verified_zone_uuids=list(zone_uuids),
            authored_hole_count=sum(len(r["holes_nm"]) for r in proposal["regions_nm"]),
            source_tracks_retained=True, separate_regions_electrically_connected_inferred=False)
    except (ValueError, RuntimeError, KeyError, TypeError) as exc:
        result["reason"] = str(exc)
    return result
