"""Source-land Ground entry with independently replayed local native antipads.

This explicit operation may remove ONLY native-filled foreign copper inside
the Source-derived clearance envelope of one fully contained through via.
It never moves an authored pour outline, pad, part, track, existing barrel,
rule, budget or companion. It is not the ordinary frozen-pour search mode.
All original-parent current, field, contact, factory, native and release gates
remain mandatory. A local geometric window is not an ampacity certificate.
"""
import math
from pathlib import Path
import tempfile
import time

import pcbnew
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_decoupler_cell as cells
import cec_fab_profile as fab
import cec_field_coupling as field
import cec_field_search as shield
import cec_force_current as force
import cec_fr as fr
import cec_ground_access_completion as access
import cec_ground_return_shortcut as returns
import cec_native_fill_geometry as fills
import cec_native_frozen_zone_access as frozen
import cec_native_ground_span_reflow as lease
import cec_native_partition_pair as partitions
from cec_native_items import discard_items
import cec_source_literal_additions as literal
import cec_source_retaining_ses_import as text_io
import cec_zone_fill as native_fill


def _tick(deadline):
    if time.monotonic() >= deadline:
        raise ValueError('Source_ground_window_deadline')


def _window(zone, at, diameter, gap, board):
    # These are the ACTUAL Source filler/process parameters, not a new
    # clearance/tolerance allowance. Exact native reconstruction is also due.
    error = int(board.GetDesignSettings().m_MaxError)
    radius = diameter//2 + gap + int(zone.GetMinThickness()) + error
    if not 0 < radius <= 2000000:
        raise ValueError('bounded_Source_native_antipad_envelope_required')
    shape = pcbnew.SHAPE_POLY_SET()
    index = shape.NewOutline()
    for x, y in ((at.x-radius, at.y-radius), (at.x+radius, at.y-radius),
                 (at.x+radius, at.y+radius), (at.x-radius, at.y+radius)):
        shape.Append(x, y, index)
    return shape, radius


def _local_subtraction(before, after, window, deadline):
    """Native zero-spill and zero-removal outside the exact bounded region."""
    _tick(deadline)
    spill = after.CloneDropTriangulation()
    spill.BooleanSubtract(before)
    if spill.OutlineCount():
        raise ValueError('Ground_window_added_foreign_power_copper')
    lost = before.CloneDropTriangulation()
    lost.BooleanSubtract(after)
    if not lost.OutlineCount():
        raise ValueError('Ground_window_must_make_an_actual_native_clearance')
    local = lost.CloneDropTriangulation()
    local.BooleanSubtract(window)
    _tick(deadline)
    if local.OutlineCount():
        raise ValueError('Ground_window_removed_foreign_copper_outside_Source_envelope')
    return dict(zero_foreign_spill=True, zero_loss_outside_Source_envelope=True,
        lost_native_identity=fills.identity(lost, deadline)[0],
        current_capacity_qualified=False)


def _new_via(board, proposal, incoming_uuid=None):
    if incoming_uuid is not None and (type(incoming_uuid) is not str or not incoming_uuid):
        raise ValueError('one_exact_new_Ground_via_identity_required')
    via = pcbnew.PCB_VIA(board)
    via.m_Uuid.Clone(pcbnew.KIID(incoming_uuid) if incoming_uuid else pcbnew.KIID())
    via.SetPosition(pcbnew.VECTOR2I(*proposal['at_nm']))
    via.SetWidth(proposal['diameter_nm'])
    via.SetDrill(proposal['drill_nm'])
    via.SetNetCode(board.GetNetcodeFromNetname('GND'))
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetLocked(True)
    board.Add(via)
    group = next(g for g in board.Groups() if force._uid(g) == proposal['existing_group_uuid'])
    group.AddItem(via)
    return via


def _purpose(value):
    if type(value) is not str or value not in ('island_join', 'local_return_completion'):
        raise ValueError('explicit_Source_Ground_window_purpose_required')
    return value


def plan(source, *, board_hint, pad_uuid, timeout_s=10., purpose='island_join'):
    deadline = lease._deadline(timeout_s)
    purpose = _purpose(purpose)
    if type(board_hint) is not str or not board_hint or type(pad_uuid) is not str or not pad_uuid:
        raise ValueError('explicit_Source_Ground_window_identity_required')
    source = Path(source).resolve(strict=True)
    family, code = force._family(source, board_hint), force._code_identity()
    board = pcbnew.LoadBoard(str(source))
    pad, face = access._pad(board, pad_uuid)
    prior = cells._existing_return(board, pad, 16., allow_native_track_body=True)
    if prior is not None and prior[0] <= 1.5:
        raise ValueError('Source_already_has_a_local_Ground_return')
    context, group_uid, geometry = access._existing_pad_rule(board, pad)
    diameter, drill = [round(v*1e6) for v in geometry]
    if not 0 < drill < diameter <= 1000000:
        raise ValueError('bounded_existing_Source_Ground_via_geometry_required')
    at = pad.GetPosition()
    if not fab._pad_contains_circle(pad, at, diameter/2, tolerance_nm=0):
        raise ValueError('complete_Source_Ground_land_containment_required')
    clearance = max(200000, int(board.GetDesignSettings().m_MinClearance),
        int(cells._netclass(board, 'GND')['clearance']))
    if (not cells._hole_to_hole_clear(board, at, drill/1e6)[0]
            or not fr._edge_leg_clear(board, at, at, diameter//2+clearance)
            or not fab.via_pad_decision(board, pad, at, diameter, drill, pad.GetNetCode())[0]
            or not shield.retained_shield_barrel_allowed(board, at, diameter, clearance, pad.GetNetCode())):
        raise ValueError('Source_Ground_window_process_hole_edge_or_shield_refused')
    blocked, _ = fab.via_at_pad_conflicts(board, at, diameter, drill, pad.GetNetCode())
    if blocked is not None:
        raise ValueError('Source_Ground_window_conflicts_with_an_actual_pad')
    # All existing non-zone copper is immutable. The post-fill full via
    # guard separately checks rule areas, graphics and every actual face.
    resolve = fr._foreign_clearance_resolver(board)
    circle = pcbnew.SHAPE_CIRCLE(at, diameter//2)
    for item in [*board.GetTracks(), *(p for fp in board.GetFootprints() for p in fp.Pads())]:
        _tick(deadline)
        if item.GetNetCode() == pad.GetNetCode():
            continue
        for layer in board.GetEnabledLayers().CuStack():
            if item.IsOnLayer(layer) and item.GetEffectiveShape(layer).Collide(
                    circle, max(clearance, resolve(item, layer))):
                raise ValueError('Source_Ground_window_intersects_immutable_copper:'+force._uid(item))
    foreign = []
    ground = []
    for zone in board.Zones():
        _tick(deadline)
        if zone.GetIsRuleArea():
            continue
        if not zone.IsFilled():
            raise ValueError('Source_Ground_window_requires_complete_saved_fills')
        faces = []
        for layer in zone.GetLayerSet().CuStack():
            if not zone.HasFilledPolysForLayer(layer):
                raise ValueError('Source_Ground_window_fill_face_unavailable')
            if zone.GetNetname() == 'GND':
                continue
            gap = max(clearance, int(zone.GetLocalClearance()), resolve(zone, layer))
            if zone.GetFilledPolysList(layer).Collide(circle, gap):
                if zone.GetFillMode() != pcbnew.ZONE_FILL_MODE_POLYGONS:
                    raise ValueError('Source_Ground_window_requires_solid_foreign_fill')
                _, radius = _window(zone, at, diameter, gap, board)
                faces.append(dict(layer=int(layer), gap_nm=gap, envelope_radius_nm=radius,
                    source_native_fill_sha256=fills.identity(zone.GetFilledPolysList(layer), deadline)[0]))
        if zone.GetNetname() == 'GND':
            ground.append(force._uid(zone))
        elif faces:
            foreign.append(dict(uuid=force._uid(zone), net=str(zone.GetNetname()), faces=faces))
    if not 1 <= len(foreign) <= 8 or not ground:
        raise ValueError('one_to_eight_actual_foreign_native_antipads_and_Ground_planes_required')
    _tick(deadline)
    if family != force._family(source, board_hint) or code != force._code_identity():
        raise ValueError('Source_Ground_window_family_or_code_changed')
    result = dict(schema=1, scope='Source_contained_Ground_via_native_clearance_windows',
        source=str(source), source_sha256=force._hash(source), source_family=family,
        script_code_identity=code, board_hint=board_hint, pad_uuid=pad_uuid, face=face,
        at_nm=list(at), diameter_nm=diameter, drill_nm=drill, clearance_nm=clearance,
        existing_group_uuid=group_uid, existing_local_pad_rule=context,
        foreign_zones=foreign, ground_zone_uuids=sorted(ground),
        Source_authored_outlines_and_all_existing_conductors_immutable=True,
        current_capacity_qualified=False, all_original_parent_gates_still_required=True,
        routing_admitted=False, release_authority=False)
    if purpose == 'local_return_completion':
        result.update(purpose=purpose, source_return_witness_mm=None if prior is None else prior[0],
            fixed_source_local_return_limit_mm=1.5, native_open_progress_claimed=False)
    _tick(deadline)
    return result


def _construct_fresh(proposal, incoming_uuid, deadline):
    board = pcbnew.LoadBoard(proposal['source'])
    original = pcbnew.LoadBoard(proposal['source'])
    via = _new_via(board, proposal, incoming_uuid)
    ids = set(proposal['ground_zone_uuids']) | {r['uuid'] for r in proposal['foreign_zones']}
    selected = pcbnew.ZONES()
    for zone in board.Zones():
        if force._uid(zone) in ids:
            zone.UnFill()
            selected.append(zone)
    native = native_fill.compile_selected(board, selected,
        timeout_s=min(10., max(.001, deadline-time.monotonic())), initialize_selected=True)
    before = {force._uid(z): z for z in original.Zones()}
    after = {force._uid(z): z for z in board.Zones()}
    proofs = []
    for record in proposal['foreign_zones']:
        left, right = before[record['uuid']], after[record['uuid']]
        selected_faces = {f['layer'] for f in record['faces']}
        for layer in left.GetLayerSet().CuStack():
            if int(layer) not in selected_faces and fills.identity(
                    left.GetFilledPolysList(layer), deadline) != fills.identity(
                    right.GetFilledPolysList(layer), deadline):
                raise ValueError('Ground_window_changed_an_unselected_foreign_face')
        for face in record['faces']:
            region, radius = _window(left, via.GetPosition(), proposal['diameter_nm'], face['gap_nm'], original)
            if radius != face['envelope_radius_nm']:
                raise ValueError('Source_Ground_window_native_envelope_changed')
            proof = _local_subtraction(left.GetFilledPolysList(face['layer']),
                right.GetFilledPolysList(face['layer']), region, deadline)
            proofs.append(dict(zone_uuid=record['uuid'], layer=face['layer'], **proof))
    contacts = returns._reference_contacts(board, via)
    pad, _ = access._pad(board, proposal['pad_uuid'])
    witness = cells._existing_return(board, pad, 16., allow_native_track_body=True)
    if witness is None or witness[0] != 0.:
        raise ValueError('native_Ground_window_must_have_a_zero_length_reference_return')
    decision = fab.local_pofv_via_decision(board, via)
    if not decision[0]:
        raise ValueError('actual_Ground_window_via_process_refused:'+decision[1])
    with tempfile.TemporaryDirectory(prefix='cec-Ground-window-geometry-') as work:
        snapshot = Path(work)/'board.kicad_pcb'
        field._save_field_snapshot(board, snapshot)
        probe = pcbnew.LoadBoard(str(snapshot))
        # This is a NEW-hole guard, not an existing-barrel exemption. Remove
        # only that newly emitted barrel from a private geometric clone,
        # retaining the freshly compiled native antipads without a refill.
        # The actual saved Source still owns the package/process/rules.
        probe.SetFileName(proposal['source'])
        incoming = next(v for v in probe.GetTracks() if force._uid(v)==force._uid(via))
        discard_items(probe, [incoming])
        probe_pad, _ = access._pad(probe, proposal['pad_uuid'])
        # Explicitly Source-derivable ONLY these just-replayed foreign zones.
        # The resulting shape guard sees actual saved metal; it neither fills
        # nor authorizes this snapshot. Independent original replay is owed.
        with frozen.frozen(probe, snapshot, timeout_s=min(10., max(.001, deadline-time.monotonic())),
                zone_uuids=[r['uuid'] for r in proposal['foreign_zones']]):
            geometry_report = {}
            if not fr._via_spot_clear(probe, via.GetPosition(), proposal['diameter_nm'],
                    proposal['clearance_nm'], {probe_pad.GetNetCode()}, drill_nm=proposal['drill_nm'],
                    net_code=probe_pad.GetNetCode(), local_pofv_pad=probe_pad, report=geometry_report):
                raise ValueError('native_Ground_window_all_face_via_geometry_refused:'+str(geometry_report))
    _tick(deadline)
    return board, dict(native_fill=native, local_foreign_subtractions=proofs,
        reference_contacts=contacts, Ground_return_mm=0.,
        all_face_native_via_geometry_received=True, current_capacity_qualified=False)


def _literal_text(source, board, proposal):
    original = text_io.raw_text(source)
    with tempfile.TemporaryDirectory(prefix='cec-Ground-window-literal-') as work:
        path = Path(work)/'native.kicad_pcb'
        field._save_field_snapshot(board, path)
        native = text_io.raw_text(path)
    # Ordinary immutable-source assembly still owns every addition and group
    # extension. Foreign fill edits are then the EXACT independently replayed
    # native fills, never a caller polygon or an alias of the Ground exception.
    result = literal.assemble(original, native, ground_ids=proposal['ground_zone_uuids'])
    old = literal._inventory(result)[0]
    fresh = literal._inventory(native)[0]
    for uid in sorted((r['uuid'] for r in proposal['foreign_zones']),
            key=lambda u: old[u][0], reverse=True):
        a, b, node = old[uid]
        regenerated = fresh[uid][2]
        result = result[:a]+text_io.replace_fills(node, regenerated)+result[b:]
    return result


def write_private(proposal, directory, *, incoming_uuid=None, timeout_s=10.):
    deadline = lease._deadline(timeout_s)
    fresh = plan(proposal['source'], board_hint=proposal['board_hint'], pad_uuid=proposal['pad_uuid'],
        purpose=proposal.get('purpose', 'island_join'),
        timeout_s=min(10., max(.001, deadline-time.monotonic())))
    if fresh != proposal:
        raise ValueError('fresh_exact_Source_Ground_window_proposal_required')
    board, proof = _construct_fresh(fresh, incoming_uuid, deadline)
    target = force._copy_family(Path(fresh['source']), Path(directory))
    text_io.write_raw(target, _literal_text(Path(fresh['source']), board, fresh))
    _tick(deadline)
    if (fresh['script_code_identity'] != force._code_identity()
            or fresh['source_family'] != force._family(Path(fresh['source']), fresh['board_hint'])):
        raise ValueError('Source_Ground_window_changed_before_private_save')
    result = dict(candidate=str(target), candidate_sha256=force._hash(target), construction=proof,
        complete=True, routing_admitted=False, current_capacity_qualified=False,
        all_original_parent_gates_still_required=True, release_authority=False)
    _tick(deadline)
    return result


def receive(source, candidate, *, board_hint, pad_uuid, timeout_s=10., purpose='island_join'):
    result = dict(ok=False, complete=False, errors=[], scope_only=True,
        routing_admitted=False, current_capacity_qualified=False, release_authority=False,
        all_original_parent_gates_still_required=True)
    try:
        deadline = lease._deadline(timeout_s)
        purpose = _purpose(purpose)
        source, candidate = [Path(p).resolve(strict=True) for p in (source, candidate)]
        if source == candidate:
            raise ValueError('distinct_saved_Ground_window_boundaries_required')
        epoch = force._code_identity()
        families = [force._family(p, board_hint) for p in (source, candidate)]
        fresh = plan(source, board_hint=board_hint, pad_uuid=pad_uuid, purpose=purpose,
            timeout_s=min(10., max(.001, deadline-time.monotonic())))
        old_root, old = additive._nodes(source)
        new_root, new = additive._nodes(candidate)
        incoming = new.keys()-old.keys()
        if old.keys()-new.keys() or len(incoming) != 1 or new[next(iter(incoming))][0] != 'via':
            raise ValueError('exactly_one_new_Ground_via_without_retirement_required')
        uid = next(iter(incoming))
        projected, proof = _construct_fresh(fresh, uid, deadline)
        with tempfile.TemporaryDirectory(prefix='cec-Ground-window-independent-') as work:
            expected = force._copy_family(source, Path(work)/'expected')
            text_io.write_raw(expected, _literal_text(source, projected, fresh))
            expected_root = additive._nodes(expected)[0]
        if (syntax._freeze(expected_root) != syntax._freeze(new_root)
                or force._sidecars(source) != force._sidecars(candidate)):
            raise ValueError('saved_Ground_window_differs_from_complete_independent_Source_replay')
        parent, child = [pcbnew.LoadBoard(str(p)) for p in (source, candidate)]
        paired = partitions.compare(parent, child,
            timeout_s=min(10., max(.001, deadline-time.monotonic())))
        if paired.get('available') is not True or paired.get('preserved') is not True:
            raise ValueError('Source_Ground_window_demoted_a_retained_native_partition')
        # Ground may merge ONLY the selected land's original island. Zone
        # overlap tokens name literal physical islands, not entire zone UUIDs.
        inventory = partitions._inventory(parent, deadline,
            dict(items=16384, polygons=4096, vertices=200000))
        ground = {force._item_key(i) for i in inventory['objects'] if i.GetNetname() == 'GND'}
        ground.update(k for part in paired['source_parts'] for k in part
            if type(k) is tuple and len(k)>2 and k[0]=='zone_overlap' and k[2]=='GND')
        pad, _ = access._pad(parent, pad_uuid)
        joins = access._selected_ground_join_partitions(paired['source_parts'], paired['child_parts'],
            force._item_key(pad), ground)
        if purpose == 'island_join':
            if joins['joined_Source_ground_partitions'] <= 0:
                raise ValueError('Source_Ground_window_must_close_a_real_native_Ground_island')
        else:
            # Local-return progress is separate from closing a PCB island.
            # The fresh plan proves absent/nonlocal Source return; native
            # construction proves the exact original land now has 0 mm.
            # This mode cannot merge even the selected Source Ground island.
            prior = fresh['source_return_witness_mm']
            if (prior is not None and not prior > 1.5
                    or proof.get('Ground_return_mm') != 0.):
                raise ValueError('Source_Ground_window_local_return_progress_required')
            if (joins['every_Source_partition_identical'] is not True
                    or joins['joined_Source_ground_partitions'] != 0):
                raise ValueError('Source_Ground_window_local_return_cannot_merge_Source_islands')
            result.update(purpose=purpose, local_return_completed=True,
                source_return_witness_mm=prior, saved_return_witness_mm=0.,
                native_open_progress_claimed=False)
        _tick(deadline)
        if (epoch != force._code_identity()
                or families != [force._family(p, board_hint) for p in (source, candidate)]):
            raise ValueError('Source_Ground_window_saved_families_or_code_changed')
        result.update(ok=True, complete=True, source_sha256=force._hash(source),
            candidate_sha256=force._hash(candidate), plan=fresh, construction=proof,
            original_native_partitions=joins, all_original_authored_items_unchanged=True,
            exact_native_Source_reconstruction_received=True,
            only_Source_bounded_foreign_clearance_removal=True)
        _tick(deadline)
    except Exception as exc:
        result.update(ok=False, complete=False)
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result
