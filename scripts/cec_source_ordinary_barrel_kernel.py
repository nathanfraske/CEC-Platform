"""Receive one complete Source-exclusive ordinary barrel kernel, including tees.

This is a Source-typed facade over the existing exclusive ordinary receiver,
not an expansion of the endpoint-only barrel owner's scope. A caller names
one old barrel; native Source contacts determine the complete cut. No caller
track list, lock list, width, current, face or ownership flag is accepted.
All real external ports, surviving partitions and literal unowned material
still owe the existing public saved receiver and whole-board gates.
"""
import math
from pathlib import Path
import time

import pcbnew
import cec_additive_route_receiving as additive
import cec_force_current as force
import cec_fr as fr
import cec_ordinary_route_receiving as ordinary
import cec_route_dimensions as dimensions


def _deadline(seconds):
    if (type(seconds) not in (int, float) or not math.isfinite(seconds)
            or not 0 < seconds <= 10.):
        raise ValueError('bounded_Source_ordinary_kernel_receiving_required')
    return time.monotonic()+seconds


def _left(deadline):
    remaining = deadline-time.monotonic()
    if remaining <= 0:
        raise ValueError('Source_ordinary_kernel_receiving_deadline')
    return min(10., remaining)


def plan(source, *, via_uuid, board_hint, timeout_s=10.):
    deadline = _deadline(timeout_s)
    if (type(via_uuid) is not str or not via_uuid or len(via_uuid) > 128
            or via_uuid != via_uuid.strip() or any(ord(c) < 32 for c in via_uuid)
            or type(board_hint) is not str or not board_hint):
        raise ValueError('one_literal_Source_ordinary_barrel_identity_required')
    source = Path(source).resolve(strict=True)
    family, epoch = force._family(source, board_hint), force._code_identity()
    board = pcbnew.LoadBoard(str(source))
    tracks = {force._uid(t): t for t in board.GetTracks()}
    via = tracks.get(via_uuid)
    if via is None or via.GetClass() != 'PCB_VIA':
        raise ValueError('actual_Source_ordinary_barrel_required')
    layers = list(board.GetEnabledLayers().CuStack())
    contacts = []
    for t in tracks.values():
        _left(deadline)
        if force._uid(t) == via_uuid:
            continue
        if any(t.IsOnLayer(l) and t.GetEffectiveShape(l).Collide(
                via.GetEffectiveShape(l), 0) for l in layers):
            if t.GetClass() != 'PCB_TRACK':
                raise ValueError('Source_ordinary_barrel_has_unowned_barrel_contact')
            contacts.append(t)
    ids = {force._uid(t) for t in contacts}
    locked = {force._uid(t) for t in contacts if t.IsLocked()}
    via_locks = {via_uuid} if via.IsLocked() else set()
    positive = ordinary.eligible_nets(board, source, board_hint)
    proof = ordinary._exclusive_retired_vias(board, {via_uuid},
        retired_tracks=ids, nets=positive, unlock=via_locks, deadline=deadline)
    grouped = {force._uid(i) for g in board.Groups() for i in g.GetItems()}
    if (ids & grouped or any(t.GetNetname() != via.GetNetname()
            or not 0 < t.GetWidth() <= 350000 or not 0 < t.GetLength() <= 8000000
            for t in contacts) or sum(t.GetLength() for t in contacts) > 24000000):
        raise ValueError('bounded_ungrouped_Source_ordinary_contact_kernel_required')
    spec = fr._project_netclass_resolver(str(source))(via.GetNetname()) or {}
    floors = dimensions.source_board_limits(board, source)
    diameter, drill = dimensions.ordinary_via_geometry(spec, floors)
    if (via.GetDrillValue() < math.ceil(drill*1e6)
            or any(via.GetWidth(l) < math.ceil(diameter*1e6) for l in layers)):
        raise ValueError('full_saved_Source_ordinary_barrel_geometry_required')
    by_face = {}
    for t in contacts:
        by_face.setdefault(int(t.GetLayer()), set()).add(int(t.GetWidth()))
    if (any(len(widths) != 1 for widths in by_face.values())
            or any(next(iter(widths)) < math.ceil(max(floors['track_width'],
                    float(spec.get('track_width') or 0))*1e6)
                   for widths in by_face.values())):
        raise ValueError('one_full_Source_ordinary_width_per_contact_face_required')
    _left(deadline)
    if family != force._family(source, board_hint) or epoch != force._code_identity():
        raise ValueError('Source_ordinary_kernel_family_or_code_changed')
    result = dict(schema=1, scope='one_Source_exclusive_ordinary_barrel_kernel',
        source=str(source), source_sha256=force._hash(source), board_hint=board_hint,
        via_uuid=via_uuid, net=via.GetNetname(), root_nm=list(via.GetPosition()),
        diameter_by_layer_nm={str(int(l)): int(via.GetWidth(l)) for l in layers},
        drill_nm=int(via.GetDrillValue()),
        retired_track_uuids=sorted(ids), allow_locked_track_uuids=sorted(locked),
        allow_locked_via_uuids=sorted(via_locks),
        source_face_widths_nm={str(l): next(iter(w)) for l, w in by_face.items()},
        source_length_nm=sum(t.GetLength() for t in contacts),
        existing_exclusive_Source_ownership=proof, release_authority=False,
        current_authority=False, source_contact_is_not_capacity_qualification=True)
    _left(deadline)
    return result


def receive(source, candidate, *, via_uuid, board_hint, timeout_s=10.):
    result = dict(scope='saved_Source_exclusive_ordinary_barrel_kernel', ok=False,
        complete=False, errors=[], release_authority=False, current_authority=False,
        all_whole_board_gates_still_required=True)
    try:
        deadline = _deadline(timeout_s)
        source, candidate = [Path(p).resolve(strict=True) for p in (source, candidate)]
        if source == candidate:
            raise ValueError('distinct_Source_ordinary_kernel_candidate_required')
        families = [force._family(p, board_hint) for p in (source, candidate)]
        epoch = force._code_identity()
        q = plan(source, via_uuid=via_uuid, board_hint=board_hint,
                 timeout_s=_left(deadline))
        _, old = additive._nodes(source)
        _, new = additive._nodes(candidate)
        removed = set(q['retired_track_uuids']) | {via_uuid}
        if old.keys()-new.keys() != removed:
            raise ValueError('exact_Source_exclusive_barrel_contacts_required')
        incoming = new.keys()-old.keys()
        child = pcbnew.LoadBoard(str(candidate))
        material = [t for t in child.GetTracks() if force._uid(t) in incoming]
        vias = [t for t in material if t.GetClass() == 'PCB_VIA']
        tracks = [t for t in material if t.GetClass() == 'PCB_TRACK']
        if (len(vias) != 1 or not 2 <= len(tracks) <= 24
                or len(material) != len(incoming) or len(material) != len(tracks)+1
                or any(t.GetNetname() != q['net'] for t in material)):
            raise ValueError('one_barrel_and_bounded_same_Source_face_legs_required')
        via = vias[0]
        if (via.GetViaType() != pcbnew.VIATYPE_THROUGH
                or via.TopLayer() != pcbnew.F_Cu or via.BottomLayer() != pcbnew.B_Cu
                or via.GetDrillValue() != q['drill_nm']
                or {str(int(l)): int(via.GetWidth(l)) for l in child.GetEnabledLayers().CuStack()}
                    != q['diameter_by_layer_nm']
                or not 0 < math.dist(tuple(via.GetPosition()), q['root_nm']) <= 2000000
                or any(q['source_face_widths_nm'].get(str(int(t.GetLayer()))) != t.GetWidth()
                       for t in tracks)
                or sum(t.GetLength() for t in tracks) > q['source_length_nm']+4000000):
            raise ValueError('Source_kernel_geometry_face_width_or_work_extent_changed')
        native = fr._read_only_route_connectivity(child)
        reached = {force._uid(via)} | {force._uid(t) for t in native.GetConnectedItems(via)}
        if any(force._uid(t) not in reached for t in tracks):
            raise ValueError('Source_kernel_has_disconnected_new_material')
        result['independent_existing_ordinary_receiving'] = ordinary.receive(source, candidate,
            retired_track_uuids=q['retired_track_uuids'], board_hint=board_hint,
            allow_locked_track_uuids=q['allow_locked_track_uuids'],
            retired_via_uuids=[via_uuid], allow_locked_via_uuids=q['allow_locked_via_uuids'],
            timeout_s=_left(deadline), max_retired_tracks=8)
        proof = result['independent_existing_ordinary_receiving']
        if proof.get('ok') is not True or proof.get('complete') is not True:
            raise ValueError('existing_exclusive_ordinary_saved_receiving_refused')
        _left(deadline)
        if families != [force._family(p, board_hint) for p in (source, candidate)] or epoch != force._code_identity():
            raise ValueError('Source_kernel_saved_families_or_code_changed')
        _left(deadline)
        result.update(ok=True, complete=True, source_derived_plan=q,
            same_barrel_geometry_and_full_face_widths=True,
            all_actual_Source_departures_restored=True, source_candidate_and_code_unchanged=True)
    except Exception as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result
