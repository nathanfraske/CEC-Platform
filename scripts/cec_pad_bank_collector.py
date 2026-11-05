"""Source-bound solid collectors for adjacent, same-net native pad banks.

This adds a rectangular, 45-degree-chamfered zone; it never moves pads,
retires conductors, changes a current contract, or grants release authority.
The envelope is derived from explicit native pads and retained source tracks.
Foreign copper and material constraints are checked before construction and
again after a native fill and saved-board replay. No renderer-only copper.
"""
from __future__ import annotations

import math
import time

import cec_rectilinear_copper as owner

Refused = owner.Refused
ZONE_NAME = "CEC_SOLID_PAD_BANK_COLLECTOR"


def _pad_shape(pad, layer):
    import pcbnew
    shape = pcbnew.SHAPE_POLY_SET()
    pad.TransformShapeToPolygon(shape, layer, 0, 1, pcbnew.ERROR_OUTSIDE, False)
    if shape.OutlineCount() != 1 or shape.HoleCount(0):
        raise Refused("simple_native_pad_bank_land_required")
    return shape


def _envelope(shapes, *, margin_nm, grid_nm, chamfer_nm, deadline):
    """Small uniform chamfers, limited by every actual source vertex."""
    points = []
    for shape in shapes:
        owner._check_deadline(deadline)
        owner._shape_identity(shape, deadline)
        for i in range(shape.OutlineCount()):
            ring = shape.Outline(i)
            points.extend((int(ring.CPoint(j).x), int(ring.CPoint(j).y))
                          for j in range(ring.PointCount()))
        if len(points) > 200000:
            raise Refused("native_pad_bank_vertex_bound")
    down = lambda v: v // grid_nm * grid_nm
    up = lambda v: -(-v // grid_nm) * grid_nm
    x0 = down(min(x for x, y in points) - margin_nm)
    x1 = up(max(x for x, y in points) + margin_nm)
    y0 = down(min(y for x, y in points) - margin_nm)
    y1 = up(max(y for x, y in points) + margin_nm)
    if max(x1-x0, y1-y0) > 50000000:
        raise Refused("local_native_pad_bank_span_bound")
    # Each support plane must remain outside ALL source copper. Uniform cuts
    # cannot silently trim an oval land, round cap, or annulus at a corner.
    permitted = min(min(x+y for x, y in points)-(x0+y0),
                    (x1-y0)-max(x-y for x, y in points),
                    (x1+y1)-max(x+y for x, y in points),
                    min(x-y for x, y in points)-(x0-y1),
                    (x1-x0)//2, (y1-y0)//2)
    cut = down(min(chamfer_nm, permitted))
    if cut <= 0:
        raise Refused("positive_source_preserving_bank_chamfer_unavailable")
    outline = [[x0+cut,y0], [x1-cut,y0], [x1,y0+cut], [x1,y1-cut],
               [x1-cut,y1], [x0+cut,y1], [x0,y1-cut], [x0,y0+cut]]
    profile = owner._poly(outline)
    for source in shapes:
        missing = source.CloneDropTriangulation()
        missing.BooleanSubtract(profile)
        if missing.OutlineCount():
            raise Refused("bank_envelope_loses_actual_native_copper")
    return outline, cut


def _geometry(board, pad_uuids, track_uuids, layer, policy, deadline):
    import pcbnew
    pads = {p.m_Uuid.AsString(): p for fp in board.GetFootprints() for p in fp.Pads()}
    tracks = {t.m_Uuid.AsString(): t for t in board.GetTracks()}
    if not set(pad_uuids) <= pads.keys() or not set(track_uuids) <= tracks.keys():
        raise Refused("explicit_native_pad_bank_source_missing")
    selected = [pads[u] for u in sorted(pad_uuids)]
    net = str(selected[0].GetNetname())
    if (not net or net.rsplit("/", 1)[-1] == "GND"
            or layer not in board.GetEnabledLayers().CuStack()
            or any(str(p.GetNetname()) != net or not p.IsOnLayer(layer)
                   or p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH for p in selected)):
        raise Refused("same_actual_net_and_enabled_pad_bank_layer_required")
    centers = [tuple(p.GetPosition()) for p in selected]
    if (len(set(centers)) != len(centers)
            or not (len({p[0] for p in centers}) == 1
                    or len({p[1] for p in centers}) == 1)):
        raise Refused("distinct_cardinal_native_pad_row_required")
    shapes = [_pad_shape(p, layer) for p in selected]
    rows = [owner._track_row(tracks[u]) for u in sorted(track_uuids)]
    if any(r["kind"] != "PCB_TRACK" or r["net"] != net or r["layer_id"] != layer
           or not owner._centerline_allowed(r["start_nm"], r["end_nm"], "chamfer45")
           for r in rows):
        raise Refused("same_net_octilinear_retained_bank_tracks_required")
    for row in rows:
        shape = owner._native_capsule(tracks[row["uuid"]])
        if not any(shape.Collide(p.GetEffectiveShape(layer), 0) for p in selected):
            raise Refused("bank_support_track_has_no_actual_pad_contact")
        shapes.append(shape)
    pad_rows = []
    for pad, shape in zip(selected, shapes):
        row = owner._link_pad_row(pad)
        row["drill_nm"] = list(tuple(pad.GetDrillSize()))
        row["geometry_sha256"] = owner._shape_identity(shape, deadline)[0]
        pad_rows.append(row)
    outline, cut = _envelope(shapes, deadline=deadline, **policy)
    return net, pad_rows, rows, shapes, outline, cut


def _clear(board, outline, net, layer, clearance, deadline, *, own_zone_uuid=None):
    import cec_board_geometry as geometry
    import cec_fr as fr
    import pcbnew
    profile = owner._poly(outline)
    owner._require_unoccupied_outline(board, profile, net, layer, deadline,
                                     clearance_nm=clearance)
    owner._require_same_net_priority_available(board, profile, net, layer, deadline,
                                               own_zone_uuid=own_zone_uuid)
    outside = profile.CloneDropTriangulation()
    outside.BooleanSubtract(geometry.outline_material(board))
    if outside.OutlineCount():
        raise Refused("native_pad_bank_outside_board_material")
    for a, b in zip(outline, outline[1:]+outline[:1]):
        owner._check_deadline(deadline)
        if not fr._edge_leg_clear(board, pcbnew.VECTOR2I(*a), pcbnew.VECTOR2I(*b), clearance):
            raise Refused("native_pad_bank_material_clearance")


def plan(board, pad_uuids, *, layer_id, support_track_uuids=(), clearance_nm,
         min_thickness_nm, chamfer_nm=600000, margin_nm=1000, grid_nm=1000,
         timeout_s=10.):
    """Read-only, explicit UUID-bound proposal; no board/refdes special cases."""
    if (type(pad_uuids) not in (list, tuple) or not 2 <= len(pad_uuids) <= 32
            or type(support_track_uuids) not in (list, tuple) or len(support_track_uuids) > 64
            or len(set(pad_uuids)) != len(pad_uuids)
            or len(set(support_track_uuids)) != len(support_track_uuids)
            or any(type(u) is not str or not u for u in (*pad_uuids, *support_track_uuids))
            or type(layer_id) is not int
            or type(clearance_nm) is not int or not 1 <= clearance_nm <= 10000000
            or type(min_thickness_nm) is not int or not 1 <= min_thickness_nm <= 1000000
            or type(chamfer_nm) is not int or not 1 <= chamfer_nm <= 1000000
            or type(margin_nm) is not int or not 1 <= margin_nm <= 100000
            or type(grid_nm) is not int or not 1 <= grid_nm <= 100000
            or type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10):
        raise Refused("bounded_explicit_native_pad_bank_policy_required")
    deadline = time.monotonic()+timeout_s
    policy = dict(margin_nm=margin_nm, grid_nm=grid_nm, chamfer_nm=chamfer_nm)
    net, pads, tracks, _, outline, cut = _geometry(board, pad_uuids, support_track_uuids,
                                                 layer_id, policy, deadline)
    if min_thickness_nm >= min(max(p["size_nm"]) for p in pads):
        raise Refused("bank_feature_floor_not_below_native_lands")
    fill_domain = owner._fill_envelope(outline, style="chamfer45", margin_nm=4)
    _clear(board, fill_domain, net, layer_id, clearance_nm, deadline)
    result = dict(schema=1, scope="native_solid_pad_bank_not_current_or_release_qualification",
        source_pads=pads, retained_source_tracks=tracks, layer_id=layer_id, net=net,
        polygon_nm=outline, actual_fill_envelope_nm=fill_domain,
        clearance_nm=clearance_nm, min_thickness_nm=min_thickness_nm,
        envelope_policy=policy, actual_chamfer_nm=cut,
        source_conductors_retained=True, new_capacity_credited=False, release_authority=False)
    result["plan_sha256"] = owner._digest(result)
    return result


def _replay(board, proposal, deadline, *, own_zone_uuid=None):
    p = dict(proposal)
    digest = p.pop("plan_sha256", None)
    if (digest != owner._digest(p) or p.get("schema") != 1
            or p.get("source_conductors_retained") is not True
            or p.get("new_capacity_credited") is not False or p.get("release_authority") is not False):
        raise Refused("native_pad_bank_proposal_identity_changed")
    actual = _geometry(board, [r["uuid"] for r in p["source_pads"]],
        [r["uuid"] for r in p["retained_source_tracks"]], p["layer_id"],
        p["envelope_policy"], deadline)
    net, pads, tracks, shapes, outline, cut = actual
    if (net != p["net"] or pads != p["source_pads"] or tracks != p["retained_source_tracks"]
            or outline != p["polygon_nm"] or cut != p["actual_chamfer_nm"]
            or owner._fill_envelope(outline, style="chamfer45", margin_nm=4)
                != p["actual_fill_envelope_nm"]):
        raise Refused("native_pad_bank_source_or_derived_envelope_changed")
    _clear(board, p["actual_fill_envelope_nm"], net, p["layer_id"], p["clearance_nm"], deadline,
           own_zone_uuid=own_zone_uuid)
    return shapes


def materialize(board, proposal):
    """Add one real solid zone to the caller's private board only."""
    import pcbnew
    _replay(board, proposal, time.monotonic()+10.)
    zone = pcbnew.ZONE(board)
    zone.SetNet(board.FindNet(proposal["net"])); zone.SetLayer(proposal["layer_id"])
    zone.SetZoneName(ZONE_NAME); zone.SetLocked(True); zone.SetAssignedPriority(0)
    zone.SetLocalClearance(proposal["clearance_nm"])
    zone.SetMinThickness(proposal["min_thickness_nm"])
    zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL); zone.SetCornerSmoothingType(0)
    zone.Outline().NewOutline()
    for x, y in proposal["polygon_nm"]:
        zone.Outline().Append(x, y)
    board.Add(zone)
    return dict(zone_uuid=zone.m_Uuid.AsString(), release_authority=False,
                source_conductors_retained=True, independent_receiving_required=True)


def receive(board, proposal, zone_uuid, *, timeout_s=10.):
    """Independently derive and receive the actual saved, filled native zone."""
    import pcbnew
    result = dict(ok=False, complete=False, zone_uuid=zone_uuid,
                  new_capacity_credited=False, release_authority=False)
    if (type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10):
        result["reason"] = "invalid_native_pad_bank_receiving_deadline"
        return result
    deadline = time.monotonic()+timeout_s
    try:
        shapes = _replay(board, proposal, deadline, own_zone_uuid=zone_uuid)
        zones = [z for z in board.Zones() if z.m_Uuid.AsString() == zone_uuid]
        if len(zones) != 1:
            raise Refused("actual_native_pad_bank_zone_missing")
        zone = zones[0]; layer = proposal["layer_id"]
        if (zone.GetIsRuleArea() or zone.GetNetname() != proposal["net"]
                or set(zone.GetLayerSet().CuStack()) != {layer}
                or zone.GetZoneName() != ZONE_NAME or not zone.IsLocked()
                or zone.GetAssignedPriority() != 0 or zone.GetParentGroup() is not None
                or zone.GetPadConnection() != pcbnew.ZONE_CONNECTION_FULL
                or zone.GetLocalClearance() != proposal["clearance_nm"]
                or zone.GetMinThickness() != proposal["min_thickness_nm"]
                or zone.GetCornerSmoothingType() != 0):
            raise Refused("native_pad_bank_zone_contract_changed")
        expected = owner._poly(proposal["polygon_nm"])
        for a, b in ((zone.Outline(), expected), (expected, zone.Outline())):
            delta = a.CloneDropTriangulation(); delta.BooleanSubtract(b)
            if delta.OutlineCount():
                raise Refused("native_pad_bank_zone_outline_changed")
        if not zone.IsFilled() or not zone.HasFilledPolysForLayer(layer):
            raise Refused("native_pad_bank_zone_not_filled")
        filled = zone.GetFilledPolysList(layer)
        owner._shape_identity(filled, deadline)
        if filled.OutlineCount() != 1:
            raise Refused("native_pad_bank_not_one_connected_fill")
        spill = filled.CloneDropTriangulation()
        spill.BooleanSubtract(owner._poly(proposal["actual_fill_envelope_nm"]))
        if spill.OutlineCount():
            raise Refused("native_pad_bank_fill_outside_declared_envelope")
        for shape in shapes:
            missing = shape.CloneDropTriangulation(); missing.BooleanSubtract(filled)
            if missing.OutlineCount():
                raise Refused("native_pad_bank_fill_does_not_enclose_source_copper")
        result.update(ok=True, complete=True, reason="saved_native_solid_pad_bank_received",
            pad_count=len(proposal["source_pads"]), retained_track_count=len(proposal["retained_source_tracks"]),
            actual_chamfer_nm=proposal["actual_chamfer_nm"], source_conductors_retained=True)
    except (Refused, ValueError, RuntimeError) as exc:
        result["reason"] = str(exc)
    return result
