"""Actual power-input pad-body contacts, never a thin branched escape waiver.

The preferred-width trace cap may extend outside a narrow native pad. Its
union with that *same* pad must contain an inward/outward conservative swept
web sized for the unchanged whole Source current and ordinary board floor.
No other trace, zone, barrel, allocated load or producer proof supplies metal.
Saved receiving repeats this proof on actual incoming track endpoints.
"""
import math
import time

import pcbnew
import cec_decoupler_cell as cells
import cec_device_power_roles as roles
import cec_force_current as force
import cec_fr as fr
import cec_request_wire_identity as wire


def _check(deadline):
    if type(deadline) not in (int, float) or not math.isfinite(deadline):
        raise ValueError('source_current_pad_body_finite_deadline_required')
    if time.monotonic() >= deadline:
        raise ValueError('source_current_pad_body_deadline')


def _same(first, last, deadline):
    return wire.canonical(first, deadline=deadline) == wire.canonical(last, deadline=deadline)


def shared_terminals(requests):
    """Exact compiler-owned terminals repeated in mandatory obligations."""
    counts = {}
    for key, request in requests.items():
        if request.get('kind') not in ('local_supply', 'source_boundary') or request.get('net') == 'GND':
            continue
        for end in ('a', 'b'):
            uid = request.get(end, {}).get('pad_uuid')
            if uid:
                counts.setdefault(uid, set()).add(key)
    return {uid for uid, owners in counts.items() if len(owners) >= 2}


def _pad_identity(pad):
    return (force._uid(pad), pad.GetNumber(), str(pad.GetNetname()),
        int(pad.GetAttribute()), int(pad.GetShape()), tuple(pad.GetSize()),
        tuple(pad.GetOffset()), tuple(pad.GetDrillSize()),
        tuple(map(int, pad.GetLayerSet().CuStack())), tuple(pad.GetPosition()),
        float(pad.GetOrientationDegrees()), float(pad.GetRoundRectRadiusRatio()),
        str(pad.GetPinFunction()), str(pad.GetPinType()))


def context(source, board, pad_uuid, *, board_hint, deadline):
    """Rebuild Source identity and a rigid posed witness, not caller XY."""
    _check(deadline)
    old = [p for f in source.GetFootprints() for p in f.Pads() if force._uid(p) == pad_uuid]
    live = [p for f in board.GetFootprints() for p in f.Pads() if force._uid(p) == pad_uuid]
    if len(old) != 1 or len(live) != 1:
        raise ValueError('source_current_pad_body_exact_pad_required')
    old, pad = old[0], live[0]
    first, last = old.GetParentFootprint(), pad.GetParentFootprint()
    model = roles.footprint_contract(first)
    if (not model or model != roles.footprint_contract(last)
            or model['pins'].get(str(old.GetNumber())) != 'power_input'
            or first.IsDNP() or last.IsDNP() or old.GetNetCode() <= 0 or pad.GetNetCode() <= 0
            or force._uid(first) != force._uid(last)
            or first.GetValue() != last.GetValue() or first.GetFPIDAsString() != last.GetFPIDAsString()
            or first.IsFlipped() != last.IsFlipped()):
        raise ValueError('source_current_pad_body_positive_power_input_required')
    try:
        roles.physical_pinmap(first, model, board_hint=board_hint,
            timeout_s=min(8.,max(.001,deadline-time.monotonic())))
        _check(deadline)
        roles.physical_pinmap(last, model, board_hint=board_hint,
            timeout_s=min(8.,max(.001,deadline-time.monotonic())))
    except ValueError as exc:
        raise ValueError('source_current_pad_body_complete_unaliased_pinmap_required') from exc
    witness = pcbnew.FOOTPRINT(first)
    witness.SetPosition(last.GetPosition())
    witness.SetOrientationDegrees(last.GetOrientationDegrees())
    expected = sorted(_pad_identity(p) for p in witness.Pads())
    actual = sorted(_pad_identity(p) for p in last.Pads())
    if expected != actual:
        raise ValueError('source_current_pad_body_rigid_source_geometry_changed')
    layers = tuple(map(int, pad.GetLayerSet().CuStack()))
    if (pad.HasHole() or pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD
            or tuple(pad.GetOffset()) != (0, 0) or len(layers) != 1
            or pad.GetShape() not in (pcbnew.PAD_SHAPE_RECT, pcbnew.PAD_SHAPE_ROUNDRECT,
                                     pcbnew.PAD_SHAPE_CIRCLE, pcbnew.PAD_SHAPE_OVAL)
            or layers[0] not in (pcbnew.F_Cu, pcbnew.B_Cu)):
        raise ValueError('source_current_pad_body_supported_single_surface_required')
    face = layers[0]
    if (face not in set(map(int, source.GetEnabledLayers().CuStack()))
            or face not in set(map(int, board.GetEnabledLayers().CuStack()))):
        raise ValueError('source_current_pad_body_actual_enabled_face_required')
    with force._thermal_hint(board_hint):
        before = cells._supply_current_widths(source, str(old.GetNetname()))
        after = cells._supply_current_widths(board, str(pad.GetNetname()))
    authority = (before or {}).get('current_authority') or {}
    if (before is None or not _same(before, after, deadline)
            or any(type(authority.get(k)) not in (int, float) or not math.isfinite(authority[k])
                or authority[k] <= 0 for k in ('amps', 'geometry_margin'))
            or type(authority.get('margin_included')) is not bool
            or type(before.get('required_by_layer_nm', {}).get(face)) is not int
            or before['required_by_layer_nm'][face] <= 0):
        raise ValueError('source_current_pad_body_unchanged_positive_current_required')
    old_class = cells._netclass(source, str(old.GetNetname()))
    new_class = cells._netclass(board, str(pad.GetNetname()))
    if (old_class != new_class
            or source.GetDesignSettings().m_TrackMinWidth != board.GetDesignSettings().m_TrackMinWidth):
        raise ValueError('source_current_pad_body_original_class_and_factory_floor_required')
    _check(deadline)
    minimum = max(int(board.GetDesignSettings().m_TrackMinWidth), before['required_by_layer_nm'][face])
    return dict(pad=pad, face=face, current=before, minimum_nm=minimum,
        full_width_nm=max(minimum, int(old_class['width'])),
        clearance_nm=max(200000, int(old_class['clearance'])))


def capture(pad, at_nm, *, full_width_nm, minimum_nm, face, deadline):
    """Actual pad plus actual terminal cap contains the whole-current web."""
    _check(deadline)
    if (type(full_width_nm) is not int or type(minimum_nm) is not int
            or not 0 < minimum_nm <= full_width_nm <= 20000000
            or len(at_nm) != 2 or any(type(v) is not int for v in at_nm)):
        raise ValueError('source_current_pad_body_exact_dimensions_required')
    at = pcbnew.VECTOR2I(*at_nm)
    if not pad.GetEffectiveShape(face).Collide(at, 0):
        return False
    metal = pcbnew.SHAPE_POLY_SET()
    pad.TransformShapeToPolygon(metal, face, 0, 1, pcbnew.ERROR_INSIDE, False)
    cap = pcbnew.PCB_TRACK(pad.GetBoard())
    cap.SetLayer(face); cap.SetStart(at); cap.SetEnd(at); cap.SetWidth(full_width_nm)
    cap_shape = pcbnew.SHAPE_POLY_SET()
    cap.TransformShapeToPolygon(cap_shape, face, 0, 1, pcbnew.ERROR_INSIDE, False)
    metal.BooleanAdd(cap_shape)
    web = pcbnew.PCB_TRACK(pad.GetBoard())
    web.SetLayer(face); web.SetStart(pad.GetPosition()); web.SetEnd(at); web.SetWidth(minimum_nm)
    missing = pcbnew.SHAPE_POLY_SET()
    web.TransformShapeToPolygon(missing, face, 0, 1, pcbnew.ERROR_OUTSIDE, False)
    missing.BooleanSubtract(metal)
    _check(deadline)
    return missing.OutlineCount() == 0


def sites(source, board, pad_uuid, *, board_hint, width_nm, toward_nm=None, deadline):
    if (type(width_nm) is not int or not 0 < width_nm <= 20000000
            or toward_nm is not None and (len(toward_nm) != 2
                or any(type(v) is not int or abs(v) > 2000000000 for v in toward_nm))):
        raise ValueError('source_current_pad_body_exact_proposal_dimensions_required')
    ctx = context(source, board, pad_uuid, board_hint=board_hint, deadline=deadline)
    pad = ctx['pad']; face = ctx['face']; width = max(width_nm, ctx['full_width_nm'])
    centre = tuple(pad.GetPosition()); size = tuple(pad.GetSize())
    # Finite actual-body proposals, never a rectangular clearance authority.
    hx, hy = size[0]/2-10000, size[1]/2-10000
    if min(hx, hy) <= 0:
        return []
    local = {(sx*hx, 0.) for sx in (-1, 1)} | {(0., sy*hy) for sy in (-1, 1)}
    local |= {(sx*hx, sy*hy) for sx in (-1, 1) for sy in (-1, 1)}
    # Native pad angles use the PCB/editor rotation convention. Physical
    # polygon coordinates therefore rotate by the NEGATIVE display angle.
    angle = math.radians(-pad.GetOrientationDegrees()); c, s = math.cos(angle), math.sin(angle)
    points = {(round(centre[0]+x*c-y*s), round(centre[1]+x*s+y*c)) for x, y in local}
    target = tuple(toward_nm) if toward_nm is not None else centre
    result = []
    for point in sorted(points, key=lambda q: (math.dist(q, target), q)):
        _check(deadline)
        at = pcbnew.VECTOR2I(*point)
        if (not capture(pad, point, full_width_nm=width, minimum_nm=ctx['minimum_nm'], face=face, deadline=deadline)
                or not fr._edge_leg_clear(board, at, at, width/2+ctx['clearance_nm'])
                or not fr._tap_foreign_clear(board, at, at, width, face, ctx['clearance_nm'], {pad.GetNetCode()})):
            continue
        result.append(dict(at_nm=list(point), layers=[face], native_uuids=[pad_uuid], pad_uuid=pad_uuid,
            source_current_pad_body=dict(full_width_nm=width, minimum_web_nm=ctx['minimum_nm'],
                actual_source_current_unchanged=True, native_pad_and_cap_only=True)))
    return result


def receive(source, board, requests, items, *, board_hint, deadline):
    """Independently inspect actual full-class contacts; grant NO exemptions."""
    if type(requests) is not dict or len(requests) > 64 or len(items) > 256:
        raise ValueError('source_current_pad_body_bounded_saved_inventory_required')
    pads = {force._uid(p): p for fp in board.GetFootprints() for p in fp.Pads()}
    owned = {r.get(e, {}).get('pad_uuid') for r in requests.values()
        if r.get('kind') in ('local_supply', 'source_boundary') for e in ('a', 'b')}
    proofs = []
    for uid in sorted(owned - {None}):
        _check(deadline)
        pad = pads.get(uid)
        if pad is None:
            continue  # Existing exact original-obligation receiver owns this failure.
        model = roles.footprint_contract(pad.GetParentFootprint())
        if not model or model['pins'].get(str(pad.GetNumber())) != 'power_input':
            continue
        contacts = []
        for track in items:
            if track.GetClass() != 'PCB_TRACK' or track.GetNetname() != pad.GetNetname():
                continue
            face = int(track.GetLayer())
            if not pad.IsOnLayer(face):
                continue
            for point in (track.GetStart(), track.GetEnd()):
                if (tuple(point) != tuple(pad.GetPosition())
                        and pad.GetEffectiveShape(face).Collide(point, 0)):
                    contacts.append((track, tuple(point)))
        if not contacts:
            continue
        ctx = context(source, board, uid, board_hint=board_hint, deadline=deadline)
        import cec_source_face_widths as source_widths
        requested = max(ctx['full_width_nm'], source_widths.envelope(
            source, requests, str(pad.GetNetname()), ctx['current'])[ctx['face']])
        for request in requests.values():
            expected = request.get('unchanged_full_rail_current_contract')
            if request['net'] == pad.GetNetname() and expected is not None and not _same(expected, ctx['current'], deadline):
                raise ValueError('saved_pad_body_original_request_current_changed')
        for track, point in contacts:
            if track.GetWidth() < requested:
                continue  # No escape exemption; the existing narrow-prefix receiver applies.
            if not capture(pad, point, full_width_nm=int(track.GetWidth()), minimum_nm=ctx['minimum_nm'],
                    face=ctx['face'], deadline=deadline):
                raise ValueError('saved_pad_body_whole_original_current_web_refused')
            proofs.append(dict(kind='independently_received_source_power_input_body_contact',
                pad_uuid=uid, track_uuid=force._uid(track), at_nm=list(point), minimum_web_nm=ctx['minimum_nm'],
                full_width_nm=int(track.GetWidth()), original_current_unchanged=True,
                class_width_exemption=False, current_qualified=False, release_authority=False))
    return proofs
