"""Refresh a literal source-derived signed contour after an external motion.

An owned pour is not a bounding rectangle and must not stay at its old pose
when its retained conductors move. This operator accepts only an existing
signed-region contour that is exactly reproducible from the caller's source
tracks. It preserves its identity/settings and rebuilds every real window
from those same tracks. It does not authorize their motion, rate their width,
infer parallel sharing, or grant fabrication/release credit.
"""
from __future__ import annotations

import time

import cec_native_contour_regions as regions
import cec_rectilinear_copper as owner

SCOPE = "exact_source_derived_owned_contour_refresh_not_motion_authority"
KEYS = {"schema", "scope", "zone_uuid", "source_zone", "source_tracks", "candidate_tracks",
        "source_regions_nm", "candidate_regions_nm", "actual_fill_regions_nm", "parameters",
        "candidate_geometry_binding", "source_geometry_binding", "plan_sha256", "source_tracks_retained",
        "new_capacity_credited", "release_authority", "external_motion_receiving_required"}


def _uid(item):
    return item.m_Uuid.AsString()


def _zone(board, uid):
    items = list(board.Zones())
    if len(items) > 256 or len({_uid(z) for z in items}) != len(items):
        raise owner.Refused("bounded_unique_refresh_zone_inventory_required")
    matches = [z for z in items if _uid(z) == uid]
    if len(matches) != 1:
        raise owner.Refused("literal_source_refresh_zone_unavailable")
    return matches[0]


def _configuration(zone):
    return dict(uuid=_uid(zone), name=str(zone.GetZoneName()), net=str(zone.GetNetname()),
        layer_id=int(zone.GetLayer()), layers=list(zone.GetLayerSet().CuStack()),
        priority=int(zone.GetAssignedPriority()), clearance_nm=int(zone.GetLocalClearance()),
        min_thickness_nm=int(zone.GetMinThickness()), locked=bool(zone.IsLocked()),
        pad_connection=int(zone.GetPadConnection()), smoothing=int(zone.GetCornerSmoothingType()),
        rule_area=bool(zone.GetIsRuleArea()), group_uuid=owner._group_uuid(zone))


def _settings_valid(configuration, parameters):
    import pcbnew
    if (configuration["name"] not in (regions.ZONE_NAME, owner.ZONE_NAME) or configuration["rule_area"]
            or configuration["group_uuid"] or configuration["layers"] != [configuration["layer_id"]]
            or configuration["priority"] != 0 or not configuration["net"]
            or configuration["net"].rsplit("/", 1)[-1] == "GND"
            or configuration["pad_connection"] != int(pcbnew.ZONE_CONNECTION_FULL)
            or configuration["smoothing"] != 0
            or configuration["clearance_nm"] != parameters["clearance_nm"]
            or configuration["min_thickness_nm"] != parameters["min_thickness_nm"]):
        raise owner.Refused("exact_signed_source_contour_settings_required")


def _same_regions(first, second):
    """Exact integer geometry, ignoring only redundant straight-edge vertices.

    The original single-outline generator removes collinear union vertices;
    the signed-region generator retains them. No coordinate snap, distance,
    area tolerance, window loss or non-collinear point removal is permitted.
    """
    def ring(points):
        points=[tuple(p) for p in points]
        while len(points)>3:
            kept=[]
            for index,b in enumerate(points):
                a=points[index-1];c=points[(index+1)%len(points)]
                u=(b[0]-a[0],b[1]-a[1]);v=(c[0]-b[0],c[1]-b[1])
                if u[0]*v[1]-u[1]*v[0]==0 and u[0]*v[0]+u[1]*v[1]>0:
                    continue
                kept.append(b)
            if len(kept)==len(points):break
            points=kept
        if len(points)<3:return None
        at=min(range(len(points)),key=points.__getitem__)
        return tuple(points[at:]+points[:at])
    def normalize(values):
        return sorted((ring(r['outer_nm']),tuple(sorted(ring(h) for h in r['holes_nm']))) for r in values)
    return normalize(first)==normalize(second)


def _rows(board, uids, configuration, parameters):
    index = regions._track_index(board)
    if not set(uids) <= index.keys():
        raise owner.Refused("retained_refresh_source_tracks_unavailable")
    rows = [owner._track_row(index[u]) for u in sorted(uids)]
    if any(r["kind"] != "PCB_TRACK" or r["net"] != configuration["net"]
           or r["layer_id"] != configuration["layer_id"] or r["group_uuid"]
           or r["width_nm"] < parameters["required_width_nm"]
           or r["width_nm"] <= parameters["min_thickness_nm"]
           or not owner._centerline_allowed(r["start_nm"], r["end_nm"], parameters["contour_style"])
           for r in rows):
        raise owner.Refused("same_native_source_contour_owner_and_dimensions_required")
    return rows


def _profiles(board, rows, parameters, deadline):
    return regions._profiles(board, rows, parameters["contour_style"],
        parameters["contour_grid_nm"], parameters["envelope_margin_nm"],
        parameters["fill_envelope_margin_nm"], deadline)


def _allow(values, bound):
    if (type(values) not in (list, tuple) or len(values) > bound
            or any(type(u) is not str or not u for u in values)
            or len(set(values)) != len(values)):
        raise owner.Refused("literal_unique_refresh_permission_required")
    return set(values)


def plan(source, candidate, *, zone_uuid, track_uuids, parameters,
         allow_locked_zone=False, allow_locked_track_uuids=(), timeout_s=10.):
    """Read-only proof that an existing zone was derived from these tracks.

    Candidate track/footprint motion requires its own receiving transaction.
    Neither a zone name nor a worker's claimed source list is accepted alone.
    """
    deadline = regions._deadline(timeout_s)
    if (type(zone_uuid) is not str or not zone_uuid or type(allow_locked_zone) is not bool
            or type(track_uuids) not in (list, tuple) or not 1 <= len(track_uuids) <= 128
            or len(set(track_uuids)) != len(track_uuids)
            or any(type(u) is not str or not u for u in track_uuids)
            or type(parameters) is not dict or set(parameters) != set(regions.PARAMETERS)):
        raise owner.Refused("bounded_exact_source_contour_refresh_request_required")
    regions._parameters(parameters)
    permissions = _allow(allow_locked_track_uuids, 128)
    old_zone, new_zone = _zone(source, zone_uuid), _zone(candidate, zone_uuid)
    configuration = _configuration(old_zone)
    _settings_valid(configuration, parameters)
    if configuration != _configuration(new_zone) or configuration["locked"] and not allow_locked_zone:
        raise owner.Refused("source_contour_settings_or_locked_permission_changed")
    old_rows = _rows(source, track_uuids, configuration, parameters)
    new_rows = _rows(candidate, track_uuids, configuration, parameters)
    if any(r["locked"] and r["uuid"] not in permissions for r in old_rows):
        raise owner.Refused("exact_locked_refresh_tracks_permission_required")
    dimensions = lambda r: {k: v for k, v in r.items() if k not in ("start_nm", "end_nm")}
    if any(dimensions(a) != dimensions(b) for a, b in zip(old_rows, new_rows)):
        raise owner.Refused("retained_contour_track_identity_or_width_changed")
    old_regions, _ = _profiles(source, old_rows, parameters, deadline)
    actual_old = regions.canonical_native_regions(old_zone.Outline(),
        style=parameters["contour_style"], timeout_s=max(.001, deadline-time.monotonic()))
    candidate_old = regions.canonical_native_regions(new_zone.Outline(),
        style=parameters["contour_style"], timeout_s=max(.001, deadline-time.monotonic()))
    if not _same_regions(actual_old,old_regions) or candidate_old != actual_old:
        raise owner.Refused("source_contour_not_exactly_derived_from_named_native_tracks")
    old_regions=actual_old
    new_regions, domain = _profiles(candidate, new_rows, parameters, deadline)
    if len(old_regions) != 1 or len(new_regions) != 1 or old_rows == new_rows:
        raise owner.Refused("one_changed_literal_signed_source_contour_required")
    owner._require_unoccupied_outline(candidate, regions.native_poly(domain),
        configuration["net"], configuration["layer_id"], deadline,
        clearance_nm=parameters["clearance_nm"], allow_native_hole_bridges=True)
    owner._require_same_net_priority_available(candidate, regions.native_poly(new_regions),
        configuration["net"], configuration["layer_id"], deadline, own_zone_uuid=zone_uuid)
    result = dict(schema=1, scope=SCOPE, zone_uuid=zone_uuid, source_zone=configuration,
        source_tracks=old_rows, candidate_tracks=new_rows, source_regions_nm=old_regions,
        candidate_regions_nm=new_regions, actual_fill_regions_nm=domain,
        parameters=dict(parameters), candidate_geometry_binding=regions._binding(candidate),
        source_geometry_binding=regions._binding(source),
        source_tracks_retained=True, new_capacity_credited=False, release_authority=False,
        external_motion_receiving_required=True)
    result["plan_sha256"] = owner._digest(result)
    return result


def _validate(board, proposal, deadline, *, binding=False, source=None):
    if type(proposal) is not dict or set(proposal) != KEYS:
        raise owner.Refused("exact_signed_contour_refresh_plan_required")
    check = dict(proposal); digest = check.pop("plan_sha256")
    if (digest != owner._digest(check) or type(check["schema"]) is not int or check["schema"] != 1
            or check["scope"] != SCOPE or check["source_tracks_retained"] is not True
            or check["new_capacity_credited"] is not False or check["release_authority"] is not False
            or check["external_motion_receiving_required"] is not True
            or type(check["parameters"]) is not dict
            or set(check["parameters"]) != set(regions.PARAMETERS)
            or type(check["candidate_geometry_binding"]) is not str
            or len(check["candidate_geometry_binding"]) != 64
            or type(check["source_geometry_binding"]) is not str
            or len(check["source_geometry_binding"]) != 64
            or type(check["candidate_tracks"]) is not list
            or not 1 <= len(check["candidate_tracks"]) <= 128):
        raise owner.Refused("signed_contour_refresh_authority_or_identity_changed")
    parameters = check["parameters"]; regions._parameters(parameters)
    zone = _zone(board, check["zone_uuid"])
    configuration = _configuration(zone); _settings_valid(configuration, parameters)
    if configuration != check["source_zone"]:
        raise owner.Refused("signed_contour_refresh_settings_changed")
    uids = [r["uuid"] for r in check["candidate_tracks"]]
    if len(set(uids)) != len(uids) or _rows(board, uids, configuration, parameters) != check["candidate_tracks"]:
        raise owner.Refused("refresh_retained_native_track_geometry_changed")
    generated, domain = _profiles(board, check["candidate_tracks"], parameters, deadline)
    if generated != check["candidate_regions_nm"] or domain != check["actual_fill_regions_nm"]:
        raise owner.Refused("refresh_contour_not_derived_from_actual_retained_tracks")
    dimensions = lambda r: {k: v for k, v in r.items() if k not in ("start_nm", "end_nm")}
    before = check["source_tracks"]
    if source is None or not hasattr(source,'GetTracks'):
        raise owner.Refused('actual_native_source_required_for_owned_contour_refresh')
    original_zone=_zone(source,check['zone_uuid'])
    if (regions._binding(source)!=check['source_geometry_binding']
            or _configuration(original_zone)!=check['source_zone']
            or _rows(source,uids,configuration,parameters)!=before
            or regions.canonical_native_regions(original_zone.Outline(),style=parameters['contour_style'],
                timeout_s=max(.001,deadline-time.monotonic()))!=check['source_regions_nm']):
        raise owner.Refused('actual_native_refresh_source_or_exact_rows_changed')
    if (type(before) is not list or len(before) != len(check["candidate_tracks"])
            or any(type(r) is not dict for r in before)
            or any(dimensions(a) != dimensions(b) for a, b in zip(before, check["candidate_tracks"]))
            or not _same_regions(_profiles(board, before, parameters, deadline)[0],check["source_regions_nm"])):
        raise owner.Refused("refresh_literal_source_tracks_or_windows_changed")
    regions._shape(check["source_regions_nm"], parameters["contour_style"])
    if binding and regions._binding(board) != check["candidate_geometry_binding"]:
        raise owner.Refused("refresh_candidate_geometry_binding_changed")
    return zone


def materialize(board, proposal, *, source=None, timeout_s=10.):
    """Change only the declared zone outline; preserve settings and all tracks."""
    deadline = regions._deadline(timeout_s)
    zone = _validate(board, proposal, deadline, binding=True,source=source)
    p = proposal["parameters"]
    if regions.canonical_native_regions(zone.Outline(), style=p["contour_style"],
            timeout_s=max(.001, deadline-time.monotonic())) != proposal["source_regions_nm"]:
        raise owner.Refused("refresh_source_outline_already_modified")
    owner._require_unoccupied_outline(board, regions.native_poly(proposal["actual_fill_regions_nm"]),
        proposal["source_zone"]["net"], proposal["source_zone"]["layer_id"], deadline,
        clearance_nm=p["clearance_nm"], allow_native_hole_bridges=True)
    zone.UnFill(); zone.Outline().RemoveAllContours()
    zone.Outline().Append(regions.native_poly(proposal["candidate_regions_nm"]))
    return dict(zone_uuid=proposal["zone_uuid"], plan_sha256=proposal["plan_sha256"],
        source_track_uuids=[r["uuid"] for r in proposal["candidate_tracks"]],
        tracks_added_or_retired=False, new_capacity_credited=False, release_authority=False)


def receive(board, proposal, *, source=None, timeout_s=10.):
    """Geometry-only saved receiving; external motion/current/DRC gates remain."""
    result = dict(schema=1, scope=SCOPE, ok=False, complete=False, errors=[],
        external_motion_receiving_required=True, current_qualified=False,
        new_capacity_credited=False, release_authority=False)
    try:
        deadline = regions._deadline(timeout_s)
        zone = _validate(board, proposal, deadline,source=source)
        # The established signed-region receiver independently checks real
        # filled copper, bore/foreign clearances, real holes and every capsule.
        p = proposal["parameters"]
        q = dict(schema=1, scope=regions.SCOPE, source_tracks=proposal["candidate_tracks"],
            regions_nm=proposal["candidate_regions_nm"],
            actual_fill_regions_nm=proposal["actual_fill_regions_nm"], supporting_zones=[],
            source_geometry_binding=proposal["candidate_geometry_binding"],
            net=proposal["source_zone"]["net"], layer_id=proposal["source_zone"]["layer_id"],
            group_uuid=None, locked=proposal["source_zone"]["locked"], **p, priority=0,
            source_tracks_retained=True, separate_regions_electrically_connected_inferred=False,
            filled_copper_received=False, new_capacity_credited=False, release_authority=False)
        q["plan_sha256"] = owner._digest(q)
        proof = regions.receive(board, q, [_uid(zone)],expected_zone_name=proposal['source_zone']['name'],
            timeout_s=max(.001, deadline-time.monotonic()))
        if not proof["ok"] or not proof["complete"]:
            raise owner.Refused("saved_signed_contour_refresh_not_received:"+str(proof["reason"]))
        result.update(ok=True, complete=True, saved_signed_contour=proof,
            source_track_count=len(q["source_tracks"]), zone_identity_and_settings_retained=True)
    except (ValueError, TypeError, KeyError, RuntimeError) as exc:
        result["errors"].append(type(exc).__name__+":"+str(exc))
    return result
