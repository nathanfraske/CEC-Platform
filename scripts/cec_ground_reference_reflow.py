"""Reflow one source-proved reference return without moving power ground.

The manufacturer reference role, unique selected bypass, real native ground
component and exact unbranched source departure own this cut. A replacement
must be shorter or equal and use the same ground component. No power-ground,
mesh, barrel, force copper, placement, current or release authority follows.
"""
import math
from pathlib import Path
import tempfile
import time

import pcbnew
import cec_additive_route_receiving as additive
import cec_constraints as constraints
import cec_copper_echo as sexpr
import cec_decoupler_cell as cells
import cec_device_power_roles as roles
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_ground_reference_access as reference
import cec_ordinary_route_receiving as ordinary
import cec_return_escape as surface
from cec_native_items import discard_items


def _deadline(timeout_s):
    if (type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10):
        raise ValueError('bounded_reference_reflow_required')
    return time.monotonic() + timeout_s


def plan(board, pad_uuid, *, allow_locked_track_uuids=(), timeout_s=10.):
    deadline = _deadline(timeout_s)
    allowed = ordinary._ids(allow_locked_track_uuids, 'reference_reflow_locked_scope', 8)
    pads = [p for fp in board.GetFootprints() for p in fp.Pads()]
    found = [p for p in pads if force._uid(p) == pad_uuid]
    if len(found) != 1:
        raise ValueError('unique_source_reference_land_required')
    pad = found[0]; owner = pad.GetParentFootprint()
    model = roles.footprint_contract(owner); layer = surface.smd_surface_layer(pad)
    if (not model or owner.IsDNP() or layer is None or pad.HasHole()
            or model['pins'].get(str(pad.GetNumber())) != 'reference'
            or pad.GetNetname() != 'GND'):
        raise ValueError('manufacturer_ground_tied_nonpower_reference_required')
    assigned = constraints._device_bypass_assignment(board, project_max_mm=3.5)
    selected = [r for r in assigned['assigned'].values()
        if r['requirement']['ref'] == owner.GetReference()
        and (r['requirement'].get('return_rail') or 'GND') == 'GND']
    grounds = [p for p in owner.Pads() if p.GetNetname() == 'GND'
        and model['pins'].get(str(p.GetNumber())) == 'ground']
    if len(selected) != 1 or len(grounds) != 1:
        raise ValueError('unique_source_selected_bypass_and_owner_ground_required')
    req = selected[0]['requirement']; cap = board.FindFootprintByReference(selected[0]['cap_ref'])
    cap_pads = list(cap.Pads()) if cap is not None else []
    cap_ground = [p for p in cap_pads if p.GetNetname() == 'GND']
    if (model['pins'].get(str(req['pin'])) != 'power_input'
            or cap is None or cap.IsDNP() or len(cap_pads) != 2 or len(cap_ground) != 1
            or any(surface.smd_surface_layer(p) != layer or p.HasHole() for p in cap_pads)
            or len([p for p in cap_pads if p.GetNetname() == req['rail']]) != 1):
        raise ValueError('actual_selected_local_surface_bypass_required')
    target = cap_ground[0]; graph = fr._read_only_route_connectivity(board)
    reached = {force._uid(pad)} | {force._uid(i) for i in graph.GetConnectedItems(pad)}
    if not {force._uid(grounds[0]), force._uid(target)} <= reached:
        raise ValueError('source_reference_owner_and_bypass_ground_not_native_connected')
    task = dict(owner=owner.GetReference(), pin=str(pad.GetNumber()), role='ground_reference',
        net='GND', pad_uuid=pad_uuid, cap=cap.GetReference(), cap_pad=str(target.GetNumber()),
        destination_uuid=force._uid(target), a_nm=list(pad.GetPosition()), b_nm=list(target.GetPosition()),
        verified_ground_alternatives=[dict(ref=owner.GetReference(), pin=str(grounds[0].GetNumber()),
            uuid=force._uid(grounds[0]), role='manufacturer_ground', at_nm=list(grounds[0].GetPosition()))])
    tracks = list(board.GetTracks()); grouped = {force._uid(i) for g in board.Groups() for i in g.GetItems()}
    touching = [t for t in tracks if t.GetNetname() == 'GND' and t.IsOnLayer(layer)
        and t.GetEffectiveShape(layer).Collide(pad.GetEffectiveShape(layer), 0)]
    if len(touching) != 1:
        raise ValueError('unique_unbranched_source_reference_departure_required')
    current = touching[0]; point = tuple(pad.GetPosition()); retired = []; length = 0.
    targets = {tuple(p.GetPosition()): force._uid(p) for p in (grounds[0], target)}
    while True:
        if time.monotonic() >= deadline:
            raise ValueError('reference_reflow_plan_deadline')
        uid = force._uid(current)
        if (current.GetClass() != 'PCB_TRACK' or current.GetNetname() != 'GND'
                or current.GetLayer() != layer or uid in grouped or uid in retired
                or current.IsLocked() and uid not in allowed
                or current.GetWidth() != max(board.GetDesignSettings().m_TrackMinWidth,
                    int(cells._netclass(board, 'GND')['width']))):
            raise ValueError('exact_full_class_unbranched_reference_tracks_required')
        ends = (tuple(current.GetStart()), tuple(current.GetEnd()))
        if point not in ends or ends[0] == ends[1]:
            raise ValueError('reference_source_must_be_endpoint_linear')
        far = ends[1] if ends[0] == point else ends[0]
        retired.append(uid); length += current.GetLength() / 1e6
        if len(retired) > 8 or length > 4.:
            raise ValueError('small_local_reference_reflow_scope_required')
        if far in targets:
            break
        next_items = [t for t in tracks if force._uid(t) not in retired
            and t.GetNetname() == 'GND' and t.IsOnLayer(layer)
            and t.HitTest(pcbnew.VECTOR2I(*far))]
        if len(next_items) != 1:
            raise ValueError('source_reference_tail_has_branch_or_unknown_root')
        current = next_items[0]; point = far
    if not allowed <= set(retired):
        raise ValueError('locked_reference_scope_contains_unowned_material')
    # Recheck the complete source chain independently, including exact
    # terminal identity and width; no downstream mesh becomes cut authority.
    old_tracks = [t for t in tracks if force._uid(t) in retired]
    used = reference._linear_returns(board, [task], old_tracks)
    if len(used) != 1:
        raise ValueError('actual_source_reference_return_chain_required')
    material = [*pads, *tracks, *[z for z in board.Zones() if not z.GetIsRuleArea()]]
    for edge in old_tracks:
        ends = [pcbnew.SHAPE_SEGMENT(at, at, edge.GetWidth()) for at in (edge.GetStart(), edge.GetEnd())]
        for item in material:
            if force._uid(item) in retired or item.GetNetname() != 'GND' or not item.IsOnLayer(layer): continue
            if time.monotonic() >= deadline: raise ValueError('reference_reflow_plan_deadline')
            shape = item.GetFilledPolysList(layer) if item.GetClass() == 'ZONE' else item.GetEffectiveShape(layer)
            if shape.Collide(edge.GetEffectiveShape(layer), 0) and not any(shape.Collide(end, 0) for end in ends):
                raise ValueError('source_reference_chain_has_unowned_interior_tee')
    return dict(schema=1, task=task, retired_track_uuids=retired, source_path_mm=length,
        source_root_pad_uuid=targets[far], manufacturer_source=model['source'],
        source_binding=field._field_snapshot_inventory(board), release_authority=False)


def receive(source, candidate, *, pad_uuid, board_hint, allow_locked_track_uuids=(), timeout_s=10.):
    result = dict(schema=1, ok=False, complete=False, errors=[], release_authority=False,
        current_authority=False, full_saved_board_receiving_still_required=True)
    try:
        deadline = _deadline(timeout_s)
        source, candidate = [Path(p).resolve() for p in (source, candidate)]
        if source == candidate:
            raise ValueError('distinct_saved_reference_reflow_required')
        families = [force._family(p, board_hint) for p in (source, candidate)]
        epoch = force._code_identity(); parent, child = [pcbnew.LoadBoard(str(p)) for p in (source, candidate)]
        proposal = plan(parent, pad_uuid, allow_locked_track_uuids=allow_locked_track_uuids, timeout_s=timeout_s)
        retired = set(proposal['retired_track_uuids'])
        _, old = additive._nodes(source); _, new = additive._nodes(candidate)
        if old.keys() - new.keys() != retired:
            raise ValueError('reference_reflow_cut_differs_from_source_owned_chain')
        incoming = new.keys() - old.keys(); tracks = [t for t in child.GetTracks() if force._uid(t) in incoming]
        if not 1 <= len(tracks) == len(incoming) <= 8:
            raise ValueError('bounded_track_only_reference_replacement_required')
        fresh = reference._linear_returns(child, [proposal['task']], tracks)
        if len(fresh) != 1 or fresh[0]['saved_native_path_mm'] > proposal['source_path_mm'] + 1e-6:
            raise ValueError('manufacturer_reference_return_length_worsened')
        before = ordinary._partition(parent, deadline, retired_uuids=retired)
        after = ordinary._partition(child, deadline, retained_keys=set().union(*before))
        if any(not any(p <= q for q in after) for p in before):
            raise ValueError('reference_reflow_lost_surviving_native_partition')
        for fp in parent.GetFootprints():
            for pad in fp.Pads():
                if pad.GetNetname() != 'GND': continue
                old_return = cells._existing_return(parent, pad, 3.5)
                if old_return is None: continue
                live = child.FindFootprintByReference(fp.GetReference()).FindPadByNumber(str(pad.GetNumber()))
                new_return = cells._existing_return(child, live, 3.5)
                if new_return is None or new_return[0] > old_return[0] + 1e-6:
                    raise ValueError('already_proved_immediate_ground_return_worsened')
        with tempfile.TemporaryDirectory(prefix='cec-reference-reflow-') as work:
            projected = force._copy_family(source, Path(work) / 'projected'); basis = pcbnew.LoadBoard(str(projected))
            discard_items(basis, [t for t in basis.GetTracks() if force._uid(t) in retired])
            field._save_field_snapshot(basis, projected); _, nodes = additive._nodes(projected)
            if (nodes.keys() != old.keys() - retired or any(sexpr._freeze(nodes[u]) != sexpr._freeze(old[u]) for u in nodes)):
                raise ValueError('reference_reflow_subtraction_changed_unowned_material')
            spec = fr._project_netclass_resolver(str(source))('GND') or {}
            gap = max(basis.GetDesignSettings().m_MinClearance, round(float(spec.get('clearance') or .2)*1e6))
            cache = {}
            for track in tracks:
                if (not fr._edge_leg_clear(basis, track.GetStart(), track.GetEnd(), math.ceil(track.GetWidth()/2 + gap))
                        or not fr._tap_foreign_clear(basis, track.GetStart(), track.GetEnd(), track.GetWidth(),
                            track.GetLayer(), gap, {basis.GetNetcodeFromNetname('GND')}, foreign_cache=cache)):
                    raise ValueError('reference_replacement_native_source_guard_refused')
            remaining = min(timeout_s, deadline - time.monotonic())
            if remaining <= 0: raise ValueError('reference_reflow_replay_deadline')
            proof = additive.receive(projected, candidate, timeout_s=remaining)
            result['independent_exact_reference_cut_replay'] = proof
            if not proof['ok'] or not proof['complete']:
                raise ValueError('reference_reflow_source_delta_replay_refused')
        if (families != [force._family(p, board_hint) for p in (source, candidate)]
                or epoch != force._code_identity() or time.monotonic() >= deadline):
            raise ValueError('reference_reflow_binding_or_deadline_changed')
        result.update(ok=True, complete=True, source_proposal={k:v for k,v in proposal.items() if k!='source_binding'},
            retired_track_uuids=sorted(retired), added_native_uuids=sorted(incoming),
            received_return=fresh[0], all_surviving_native_partitions_preserved=True,
            return_length_nonworsening=True, power_ground_and_main_force_material_exact=True,
            source_candidate_and_code_unchanged=True)
    except Exception as exc:
        result['errors'].append(type(exc).__name__ + ':' + str(exc))
    return result


def run(source, directory, *, board_hint, pad_uuid, source_sha256,
        allow_locked_track_uuids=(), timeout_s=10.):
    """Source-owned automatic shorter-return proposal, not board admission.

    A reflow itself may close no opens. Its saved native receipt is a bounded
    pre-clear for a later independently received transaction, never plateau
    progress or a fab-ready claim.
    """
    _deadline(timeout_s)
    source, directory = [Path(p).resolve() for p in (source, directory)]
    if directory.exists() or force._hash(source) != source_sha256:
        raise ValueError('fresh_reference_reflow_output_and_exact_source_required')
    families = force._family(source, board_hint); epoch = force._code_identity()
    directory.mkdir(parents=True)
    board = pcbnew.LoadBoard(str(source)); result = dict(schema=1, ok=False, board=None, errors=[],
        release_authority=False, routing_admitted=False, measured_open_progress=False)
    try:
        proposal = plan(board, pad_uuid, allow_locked_track_uuids=allow_locked_track_uuids, timeout_s=timeout_s)
        result['source_proposal'] = {k:v for k,v in proposal.items() if k!='source_binding'}
        discard_items(board, [t for t in board.GetTracks() if force._uid(t) in proposal['retired_track_uuids']])
        owner = board.FindFootprintByReference(proposal['task']['owner']).FindPadByNumber(proposal['task']['pin'])
        target = board.FindFootprintByReference(proposal['task']['cap']).FindPadByNumber(proposal['task']['cap_pad'])
        diagnostics = {}
        evidence, error = cells._add_supply_link(board, owner, target, lock=True,
            link_role='shared-ground-entry', diagnostics=diagnostics, search_timeout_s=timeout_s)
        result['search'] = diagnostics
        if evidence is None: raise ValueError('shorter_source_assigned_reference_path_refused:' + str(error))
        candidate = force._copy_family(source, directory / 'UNADMITTED-reference-reflow')
        additive._ground_refill(board); field._save_field_snapshot(board, candidate)
        proof = receive(source, candidate, pad_uuid=pad_uuid, board_hint=board_hint,
            allow_locked_track_uuids=allow_locked_track_uuids, timeout_s=timeout_s)
        result['independent_receiving'] = proof
        if not proof['ok'] or not proof['complete']: raise ValueError('saved_reference_reflow_refused')
        result.update(ok=True, board=str(candidate), board_sha256=force._hash(candidate))
    except Exception as exc:
        result['errors'].append(type(exc).__name__ + ':' + str(exc))
    stable = families == force._family(source, board_hint) and epoch == force._code_identity()
    result['source_family_and_code_unchanged'] = stable; result['ok'] &= stable
    force._write(directory / 'receiving.json', result)
    return result
