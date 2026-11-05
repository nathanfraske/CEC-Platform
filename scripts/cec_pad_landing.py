"""Explicit full-width native pad landing reconstruction, not a DRC waiver.

A round track cap can overhang a short rectangular power pad and collide with
a nearby signal when its existing current-width floor is compiled. Shorten
only that declared pad-center endpoint, preserve the real track identity and
width, and require an independently filled, full-width overlap into the actual
pad. Any same-net attachment on the discarded overhang prevents this repair.
All terminal/current/Kelvin/field/factory receiving remains the caller's duty.
"""
from __future__ import annotations

import time

import cec_rectilinear_copper as owner

Refused = owner.Refused


def _pad_copper(pad, layer):
    import pcbnew
    shape = pcbnew.SHAPE_POLY_SET()
    pad.TransformShapeToPolygon(shape, layer, 0, 1, pcbnew.ERROR_INSIDE, False)
    if shape.OutlineCount() != 1 or shape.HoleCount(0):
        raise Refused("simple_drill_free_pad_landing_required")
    owner._shape_identity(shape, time.monotonic()+2.)
    return shape


def _overlap_witness(pad_shape, profile, center, axis, width):
    ring = pad_shape.Outline(0)
    vertices = [[ring.CPoint(i).x, ring.CPoint(i).y] for i in range(ring.PointCount())]
    project = lambda p: p[0]*axis[0]+p[1]*axis[1]
    lo, at = min(map(project, vertices)), project(center)
    perpendicular = [-axis[1], axis[0]]
    for divisor in (16, 8, 4, 2):
        depth = max(1, (at-lo)//divisor); axial = lo+depth
        p = [c+a*(axial-at) for c, a in zip(center, axis)]
        left = width//2; right = width-left
        points = [[p[k]+perpendicular[k]*side+axis[k]*d for k in (0,1)]
            for side, d in ((-left,0),(right,0),(right,1000),(-left,1000))]
        strip = owner._poly(points)
        missing = strip.CloneDropTriangulation(); missing.BooleanSubtract(pad_shape)
        absent = strip.CloneDropTriangulation(); absent.BooleanSubtract(profile)
        if not missing.OutlineCount() and not absent.OutlineCount(): return points
    raise Refused("actual_full_width_pad_overlap_unavailable")


def plan(board, track_uuid, pad_uuid, *, required_width_nm, clearance_nm,
         allow_locked_track_uuids=(), allow_grouped_track_uuids=(),
         envelope_margin_nm=1000, contour_grid_nm=1000):
    import pcbnew
    if (type(required_width_nm) is not int or not 1 <= required_width_nm <= 100_000_000
            or type(clearance_nm) is not int or not 0 <= clearance_nm <= 10_000_000
            or type(envelope_margin_nm) is not int or not 1 <= envelope_margin_nm <= 100000
            or type(contour_grid_nm) is not int or not 1 <= contour_grid_nm <= 100000):
        raise Refused("invalid_pad_landing_dimensional_contract")
    tracks = {t.m_Uuid.AsString(): t for t in board.GetTracks()}
    pads = {p.m_Uuid.AsString(): p for fp in board.GetFootprints() for p in fp.Pads()}
    if track_uuid not in tracks or pad_uuid not in pads:
        raise Refused("native_pad_landing_boundary_missing")
    t, pad = tracks[track_uuid], pads[pad_uuid]
    row = owner._track_row(t); layer = row["layer_id"]
    if (row["kind"] != "PCB_TRACK" or not row["net"]
            or row["net"] != pad.GetNetname() or not pad.IsOnLayer(layer)
            or pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD
            or pad.GetDrillSize().x or pad.GetDrillSize().y
            or pad.GetShape() not in (pcbnew.PAD_SHAPE_RECT, pcbnew.PAD_SHAPE_ROUNDRECT)
            or pad.GetOrientationDegrees() % 90 != 0
            or row["locked"] and track_uuid not in set(allow_locked_track_uuids)
            or row["group_uuid"] and track_uuid not in set(allow_grouped_track_uuids)):
        raise Refused("explicit_manhattan_rectangular_pad_landing_owner_required")
    center = [pad.GetPosition().x, pad.GetPosition().y]
    if row["start_nm"] == center:
        terminal_key, fixed = "start_nm", row["end_nm"]
    elif row["end_nm"] == center:
        terminal_key, fixed = "end_nm", row["start_nm"]
    else:
        raise Refused("actual_pad_center_endpoint_required")
    if not owner._centerline_allowed(fixed, center, "square"):
        raise Refused("manhattan_pad_center_approach_required")
    axis = [0 if c == a else 1 if c > a else -1 for a, c in zip(fixed, center)]
    def project(p): return p[0]*axis[0]+p[1]*axis[1]
    pad_shape = _pad_copper(pad, layer); ring = pad_shape.Outline(0)
    vertices = [[ring.CPoint(i).x, ring.CPoint(i).y] for i in range(ring.PointCount())]
    lo, hi = min(map(project, vertices)), max(map(project, vertices)); at = project(center)
    width = max(required_width_nm, row["width_nm"])
    radius = (width+1)//2
    guard = envelope_margin_nm+contour_grid_nm
    backoff = radius+guard-(hi-at)
    if backoff <= 0 or backoff >= project(center)-project(fixed):
        raise Refused("no_bounded_pad_overhang_to_reconstruct")
    endpoint = [c-a*backoff for c, a in zip(center, axis)]
    replacement = dict(row, width_nm=width, **{terminal_key: endpoint})
    prototype = pcbnew.PCB_TRACK(board); prototype.SetNet(t.GetNet()); prototype.SetLayer(layer)
    prototype.SetStart(pcbnew.VECTOR2I(*replacement["start_nm"]))
    prototype.SetEnd(pcbnew.VECTOR2I(*replacement["end_nm"])); prototype.SetWidth(width)
    profile_points = owner.purposeful_envelope(owner._native_capsule(prototype), style="chamfer45",
        margin_nm=envelope_margin_nm, grid_nm=contour_grid_nm)
    profile = owner._poly(profile_points)
    # Check the future cover plus actual design clearance, not only a centerline.
    reserve = pcbnew.PCB_TRACK(board); reserve.SetNet(t.GetNet()); reserve.SetLayer(layer)
    reserve.SetStart(prototype.GetStart()); reserve.SetEnd(prototype.GetEnd())
    reserve.SetWidth(width+2*clearance_nm+2*guard)
    deadline = time.monotonic()+2.
    owner._require_unoccupied_outline(board, owner._native_capsule(reserve), row["net"], layer, deadline)
    for z in board.Zones():
        owner._check_deadline(deadline)
        if z.GetIsRuleArea() or z.GetNetname() == row["net"] or not z.IsOnLayer(layer): continue
        if not z.IsFilled() or not z.HasFilledPolysForLayer(layer):
            raise Refused("foreign_pad_landing_fill_unknown")
        overlap = owner._native_capsule(reserve)
        overlap.BooleanIntersection(z.GetFilledPolysList(layer))
        if overlap.OutlineCount(): raise Refused("foreign_pad_landing_zone_clearance")
    # Derive a full-width physical overlap strip from the actual pad entry.
    # ERROR_INSIDE pad geometry and exact Boolean differences grant no epsilon.
    witness = _overlap_witness(pad_shape, profile, center, axis, width)
    removed = owner._native_capsule(t); removed.BooleanSubtract(owner._native_capsule(prototype))
    removed.BooleanSubtract(pad_shape)
    # No discarded toe may be the attachment of another native same-net item.
    for other in [*board.GetTracks(), *pads.values()]:
        owner._check_deadline(deadline)
        uid = other.m_Uuid.AsString()
        if uid in (track_uuid, pad_uuid) or other.GetNetname() != row["net"] or not other.IsOnLayer(layer): continue
        if removed.Collide(other.GetEffectiveShape(layer), 0):
            raise Refused("pad_overhang_has_retained_same_net_attachment:"+uid)
    for z in board.Zones():
        owner._check_deadline(deadline)
        if z.GetIsRuleArea() or z.GetNetname() != row["net"] or not z.IsOnLayer(layer): continue
        if not z.IsFilled() or not z.HasFilledPolysForLayer(layer):
            raise Refused("same_net_pad_landing_fill_unknown")
        overlap = removed.CloneDropTriangulation(); overlap.BooleanIntersection(z.GetFilledPolysList(layer))
        if overlap.OutlineCount(): raise Refused("pad_overhang_has_retained_same_net_zone")
    result = dict(schema=1, scope="owned_pad_overhang_reconstruction_not_current_or_release_qualification",
        source_track=row, target_track=replacement, source_pad=owner._link_pad_row(pad),
        pad_geometry_sha256=owner._shape_identity(pad_shape, deadline)[0],
        required_width_nm=required_width_nm, clearance_nm=clearance_nm,
        envelope_margin_nm=envelope_margin_nm, contour_grid_nm=contour_grid_nm,
        profile_nm=profile_points, full_width_pad_overlap_nm=witness,
        discarded_unattached_overhang_sha256=owner._shape_identity(removed, deadline)[0],
        new_capacity_credited=False, release_authority=False, independent_native_receiving_required=True)
    result["plan_sha256"] = owner._digest(result)
    return result


def materialize(board, proposal, *, allow_locked_track_uuids=(), allow_grouped_track_uuids=()):
    import pcbnew
    p = dict(proposal); digest = p.pop("plan_sha256", None)
    if digest != owner._digest(p): raise Refused("pad_landing_proposal_identity_changed")
    actual = plan(board, p["source_track"]["uuid"], p["source_pad"]["uuid"],
        required_width_nm=p["required_width_nm"], clearance_nm=p["clearance_nm"],
        envelope_margin_nm=p["envelope_margin_nm"], contour_grid_nm=p["contour_grid_nm"],
        allow_locked_track_uuids=allow_locked_track_uuids, allow_grouped_track_uuids=allow_grouped_track_uuids)
    if actual != proposal: raise Refused("native_pad_landing_source_or_construction_changed")
    row = p["target_track"]
    t = next(t for t in board.GetTracks() if t.m_Uuid.AsString() == row["uuid"])
    t.SetStart(pcbnew.VECTOR2I(*row["start_nm"])); t.SetEnd(pcbnew.VECTOR2I(*row["end_nm"]))
    t.SetWidth(row["width_nm"])
    return dict(modified_track_uuids=[row["uuid"]], new_capacity_credited=False, release_authority=False)


def receive(board, proposal, cover, zone_uuid):
    p = dict(proposal); digest = p.pop("plan_sha256", None)
    if digest != owner._digest(p): raise Refused("pad_landing_receiving_identity_changed")
    row = p["target_track"]
    tracks = [t for t in board.GetTracks() if t.m_Uuid.AsString() == row["uuid"]]
    if len(tracks) != 1 or owner._track_row(tracks[0]) != row:
        raise Refused("saved_pad_landing_not_exact_declared_reconstruction")
    pads = [pad for fp in board.GetFootprints() for pad in fp.Pads()
        if pad.m_Uuid.AsString() == p["source_pad"]["uuid"]]
    if len(pads) != 1 or owner._link_pad_row(pads[0]) != p["source_pad"]:
        raise Refused("saved_pad_landing_physical_pad_changed")
    shape = _pad_copper(pads[0], row["layer_id"])
    if owner._shape_identity(shape, time.monotonic()+2.)[0] != p["pad_geometry_sha256"]:
        raise Refused("saved_pad_landing_native_pad_geometry_changed")
    source = p["source_track"]; center = p["source_pad"]["position_nm"]
    if source["start_nm"] == center: terminal_key, fixed = "start_nm", source["end_nm"]
    elif source["end_nm"] == center: terminal_key, fixed = "end_nm", source["start_nm"]
    else: raise Refused("saved_pad_landing_not_an_actual_pad_center_reconstruction")
    if not owner._centerline_allowed(fixed, center, "square"):
        raise Refused("saved_pad_landing_source_not_manhattan")
    axis = [0 if c == a else 1 if c > a else -1 for a, c in zip(fixed, center)]
    if type(p["required_width_nm"]) is not int or not 1 <= p["required_width_nm"] <= 100000000:
        raise Refused("saved_pad_landing_current_floor_invalid")
    width = max(p["required_width_nm"], source["width_nm"])
    ring = shape.Outline(0); at = sum(c*a for c,a in zip(center,axis))
    hi = max(ring.CPoint(i).x*axis[0]+ring.CPoint(i).y*axis[1] for i in range(ring.PointCount()))
    backoff = (width+1)//2+p["envelope_margin_nm"]+p["contour_grid_nm"]-(hi-at)
    endpoint = [c-a*backoff for c,a in zip(center,axis)]
    if backoff <= 0 or row != dict(source,width_nm=width,**{terminal_key:endpoint}):
        raise Refused("saved_pad_landing_not_derived_from_actual_pad_extents")
    derived = owner.purposeful_envelope(owner._native_capsule(tracks[0]),style="chamfer45",
        margin_nm=p["envelope_margin_nm"],grid_nm=p["contour_grid_nm"])
    if p["profile_nm"] != derived or p["full_width_pad_overlap_nm"] != _overlap_witness(
            shape,owner._poly(derived),center,axis,width):
        raise Refused("saved_pad_landing_profile_or_overlap_not_derived")
    if (p.get("schema") != 1 or p.get("new_capacity_credited") is not False
            or p.get("release_authority") is not False or p.get("independent_native_receiving_required") is not True):
        raise Refused("pad_landing_receipt_cannot_grant_current_or_release_authority")
    proof = owner.receive(board, cover, zone_uuid)
    if not proof["complete"] or not proof["ok"]:
        raise Refused("saved_pad_landing_cover_unreceived:"+proof["reason"])
    if row not in cover["source_tracks"]:
        raise Refused("pad_landing_not_bound_to_actual_cover_owner")
    z = next(z for z in board.Zones() if z.m_Uuid.AsString() == zone_uuid)
    actual = z.GetFilledPolysList(row["layer_id"]).CloneDropTriangulation()
    for support in owner._receive_support(board, cover, time.monotonic()+2.)[0]:
        actual.BooleanAdd(support.GetFilledPolysList(row["layer_id"]))
    strip = owner._poly(p["full_width_pad_overlap_nm"])
    missing = strip.CloneDropTriangulation(); missing.BooleanSubtract(shape)
    strip.BooleanSubtract(actual)
    if missing.OutlineCount() or strip.OutlineCount():
        raise Refused("saved_native_full_width_pad_overlap_not_received")
    return dict(ok=True, full_width_native_pad_overlap_received=True,
        pad_and_track_identity_preserved=True, new_capacity_credited=False, release_authority=False)
