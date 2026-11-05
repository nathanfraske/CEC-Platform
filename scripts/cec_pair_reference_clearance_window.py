"""Source-paired transition return through one checked native antipad.

This is a full GND-owned ordinary barrel, not a signal-via-size exception.
Only a saved declared pair, two of its existing through barrels, and a
proposed seat are inputs. No existing conductor or pour outline may move.
The independent receiver replays the exact local native subtraction and
retained partitions. Current/field/native/factory admission remains due.
"""
import math
from pathlib import Path
import tempfile
import time

import pcbnew
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_ground_return_shortcut as returns
import cec_ground_via_clearance_window as geometry
import cec_native_fill_geometry as fills
import cec_native_frozen_zone_access as frozen
import cec_native_ground_span_reflow as lease
from cec_native_items import discard_items
import cec_native_partition_pair as partitions
import cec_precision_route as precision
import cec_pth_pair_returns as ground
import cec_signal_via_clearance_window as signal
import cec_source_retaining_ses_import as text_io
import cec_zone_fill as native_fill


def _tick(deadline):
    if time.monotonic() >= deadline:
        raise ValueError('Source_pair_reference_window_deadline')


def _transition(board, source, pair_name, signal_via_uuids):
    if (type(pair_name) is not str or not pair_name
            or type(signal_via_uuids) not in (list, tuple)
            or len(signal_via_uuids) != 2
            or any(type(u) is not str or not u for u in signal_via_uuids)
            or len(set(signal_via_uuids)) != 2):
        raise ValueError('one_declared_Source_pair_and_two_exact_barrels_required')
    pairs = [p for p in precision.derive_coupled_pairs(str(source), board=board)
             if p['name'] == pair_name]
    if len(pairs) != 1:
        raise ValueError('one_saved_declared_Source_pair_required')
    pair = pairs[0]
    by_id = {force._uid(t): t for t in board.GetTracks()}
    vias = [by_id.get(u) for u in signal_via_uuids]
    if (any(v is None or v.GetClass() != 'PCB_VIA'
            or v.GetViaType() != pcbnew.VIATYPE_THROUGH
            or v.TopLayer() != pcbnew.F_Cu or v.BottomLayer() != pcbnew.B_Cu for v in vias)
            or {str(v.GetNetname()) for v in vias} != {pair['p'], pair['n']}):
        raise ValueError('unchanged_native_barrel_of_each_Source_pair_member_required')
    points = [tuple(v.GetPosition()) for v in vias]
    if not 0 < math.dist(*points) <= 1500000:
        raise ValueError('bounded_actual_Source_pair_transition_required')
    completion = precision._native_pair_completion(board, pair)
    if not completion.get('complete') or not completion.get('connected'):
        raise ValueError('complete_saved_Source_pair_required_before_reference_window')
    return pair, vias


def _covered(board, signal_via):
    at = signal_via.GetPosition()
    for barrel in ground.ground_barrels(board):
        if math.dist(tuple(at), tuple(barrel.GetPosition())) > 1500000:
            continue
        try:
            returns._reference_contacts(board, barrel)
        except ValueError:
            continue
        return True
    return False


def plan(source, *, board_hint, pair_name, signal_via_uuids, position_nm, timeout_s=10.):
    deadline = lease._deadline(timeout_s)
    if type(board_hint) is not str or not board_hint:
        raise ValueError('explicit_Source_pair_reference_board_identity_required')
    point = signal._axis(position_nm)
    source = Path(source).resolve(strict=True)
    family, code = force._family(source, board_hint), force._code_identity()
    board = pcbnew.LoadBoard(str(source))
    pair, vias = _transition(board, source, pair_name, signal_via_uuids)
    dimensions = ground.ground_return_contract(board)
    diameter, drill, clearance = [dimensions[k] for k in
        ('diameter_nm', 'drill_nm', 'clearance_nm')]
    if not 0 < drill < diameter <= 1000000:
        raise ValueError('bounded_full_Source_Ground_reference_geometry_required')
    reached = [force._uid(v) for v in vias
               if math.dist(point, tuple(v.GetPosition())) <= 1500000]
    missing = [force._uid(v) for v in vias if not _covered(board, v)]
    if not set(reached) & set(missing):
        raise ValueError('seat_must_complete_an_unreturned_Source_transition_member')
    at = pcbnew.VECTOR2I(*point)
    report = ground.ground_site_guard(board, at, diameter, drill, dimensions, deadline=deadline)
    if not report['ok']:
        raise ValueError('Source_pair_reference_'+report['reason'])
    blocked, overlaps = signal.fab.via_at_pad_conflicts(board, at, diameter, drill,
        board.GetNetcodeFromNetname('GND'))
    if blocked is not None or overlaps:
        raise ValueError('Source_pair_reference_seat_must_be_outside_all_actual_lands')
    resolve = fr._foreign_clearance_resolver(board)
    circle = pcbnew.SHAPE_CIRCLE(at, (diameter+1)//2)
    for item in [*board.GetTracks(), *(p for fp in board.GetFootprints() for p in fp.Pads())]:
        _tick(deadline)
        if item.GetNetname() == 'GND':
            continue
        for layer in board.GetEnabledLayers().CuStack():
            if item.IsOnLayer(layer) and item.GetEffectiveShape(layer).Collide(
                    circle, max(clearance, resolve(item, layer))):
                raise ValueError('Source_pair_reference_intersects_immutable_copper:'+force._uid(item))
    foreign, reference = [], []
    for zone in board.Zones():
        _tick(deadline)
        if zone.GetIsRuleArea():
            continue
        if not zone.IsFilled():
            raise ValueError('Source_pair_reference_requires_complete_saved_fills')
        faces = []
        for layer in zone.GetLayerSet().CuStack():
            if not zone.HasFilledPolysForLayer(layer):
                raise ValueError('Source_pair_reference_native_face_unavailable')
            if zone.GetNetname() == 'GND':
                continue
            gap = max(clearance, int(zone.GetLocalClearance()), resolve(zone, layer))
            if zone.GetFilledPolysList(layer).Collide(circle, gap):
                if zone.GetFillMode() != pcbnew.ZONE_FILL_MODE_POLYGONS:
                    raise ValueError('Source_pair_reference_solid_foreign_fill_required')
                _, radius = geometry._window(zone, at, diameter, gap, board)
                faces.append(dict(layer=int(layer), gap_nm=gap, envelope_radius_nm=radius,
                    source_native_fill_sha256=fills.identity(zone.GetFilledPolysList(layer), deadline)[0]))
        if zone.GetNetname() == 'GND':
            reference.append(force._uid(zone))
        elif faces:
            foreign.append(dict(uuid=force._uid(zone), net=str(zone.GetNetname()), faces=faces))
    if not 1 <= len(foreign) <= 8 or not reference:
        raise ValueError('one_to_eight_actual_pair_reference_antipads_and_Ground_planes_required')
    if family != force._family(source, board_hint) or code != force._code_identity():
        raise ValueError('Source_pair_reference_family_or_code_changed')
    _tick(deadline)
    result = dict(schema=1, scope='Source_paired_transition_full_Ground_via_native_windows',
        source=str(source), source_sha256=force._hash(source), source_family=family,
        script_code_identity=code, board_hint=board_hint, pair_name=pair_name,
        pair_nets=[pair['p'], pair['n']], signal_via_uuids=sorted(signal_via_uuids),
        Source_missing_return_uuids=sorted(missing), Source_members_within_reach=sorted(reached),
        at_nm=point, diameter_nm=diameter, drill_nm=drill, clearance_nm=clearance,
        Ground_owned_contract=dimensions, foreign_zones=foreign, ground_zone_uuids=sorted(reference),
        all_original_parent_gates_still_required=True, current_capacity_qualified=False,
        routing_admitted=False, release_authority=False)
    _tick(deadline)
    return result


def _construct_fresh(proposal, incoming_uuid, deadline):
    board, original = [pcbnew.LoadBoard(proposal['source']) for _ in range(2)]
    via = pcbnew.PCB_VIA(board)
    via.m_Uuid.Clone(pcbnew.KIID(incoming_uuid) if incoming_uuid else pcbnew.KIID())
    via.SetPosition(pcbnew.VECTOR2I(*proposal['at_nm']))
    via.SetWidth(proposal['diameter_nm']); via.SetDrill(proposal['drill_nm'])
    via.SetViaType(pcbnew.VIATYPE_THROUGH); via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    via.SetNet(board.FindNet('GND')); via.SetLocked(True); board.Add(via)
    ids = set(proposal['ground_zone_uuids']) | {r['uuid'] for r in proposal['foreign_zones']}
    selected = pcbnew.ZONES()
    for zone in board.Zones():
        if force._uid(zone) in ids:
            zone.UnFill(); selected.append(zone)
    native = native_fill.compile_selected(board, selected,
        timeout_s=min(10., max(.001, deadline-time.monotonic())), initialize_selected=True)
    before, after = [{force._uid(z): z for z in b.Zones()} for b in (original, board)]
    proofs = []
    for record in proposal['foreign_zones']:
        left, right = before[record['uuid']], after[record['uuid']]
        selected_faces = {f['layer'] for f in record['faces']}
        replacements = {}
        for layer in left.GetLayerSet().CuStack():
            if int(layer) not in selected_faces and fills.identity(
                    left.GetFilledPolysList(layer), deadline) != fills.identity(
                    right.GetFilledPolysList(layer), deadline):
                raise ValueError('pair_reference_changed_an_unselected_foreign_face')
        for face in record['faces']:
            region, radius = geometry._window(left, via.GetPosition(), proposal['diameter_nm'],
                face['gap_nm'], original)
            if radius != face['envelope_radius_nm']:
                raise ValueError('Source_pair_reference_native_envelope_changed')
            constrained, proof = signal._source_clipped_native_fill(left.GetFilledPolysList(face['layer']),
                right.GetFilledPolysList(face['layer']), region, deadline)
            replacements[face['layer']] = constrained
            proofs.append(dict(zone_uuid=record['uuid'], layer=face['layer'], **proof))
        signal._reinstall_native_faces(right, replacements, deadline, source_zone=left)
    contacts = returns._reference_contacts(board, via)
    with tempfile.TemporaryDirectory(prefix='cec-pair-reference-window-geometry-') as work:
        snapshot = Path(work)/'board.kicad_pcb'
        field._save_field_snapshot(board, snapshot)
        probe = pcbnew.LoadBoard(str(snapshot)); probe.SetFileName(proposal['source'])
        discard_items(probe, [t for t in probe.GetTracks() if force._uid(t) == force._uid(via)])
        guard = ground.ground_site_guard(probe, via.GetPosition(), proposal['diameter_nm'],
            proposal['drill_nm'], proposal['Ground_owned_contract'], deadline=deadline)
        if not guard['ok']:
            raise ValueError('native_pair_reference_'+guard['reason'])
        with frozen.frozen(probe, snapshot,
                timeout_s=min(10., max(.001, deadline-time.monotonic()))):
            report = {}
            if not fr._via_spot_clear(probe, via.GetPosition(), proposal['diameter_nm'],
                    proposal['clearance_nm'], {via.GetNetCode()}, drill_nm=proposal['drill_nm'],
                    net_code=via.GetNetCode(), report=report):
                raise ValueError('native_pair_reference_all_face_geometry_refused:'+str(report))
    _tick(deadline)
    return board, dict(native_fill=native, local_foreign_subtractions=proofs,
        actual_contacts_to_every_Ground_reference=contacts,
        full_Source_Ground_class_dimensions=True, all_face_native_new_hole_geometry_received=True,
        native_open_progress_claimed=False, current_capacity_qualified=False)


def write_private(proposal, directory, *, timeout_s=10.):
    deadline = lease._deadline(timeout_s)
    fresh = plan(proposal['source'], board_hint=proposal['board_hint'], pair_name=proposal['pair_name'],
        signal_via_uuids=proposal['signal_via_uuids'], position_nm=proposal['at_nm'],
        timeout_s=min(10., max(.001, deadline-time.monotonic())))
    if fresh != proposal:
        raise ValueError('fresh_exact_Source_pair_reference_proposal_required')
    board, proof = _construct_fresh(fresh, None, deadline)
    target = force._copy_family(Path(fresh['source']), Path(directory))
    text_io.write_raw(target, geometry._literal_text(Path(fresh['source']), board, fresh))
    if (fresh['script_code_identity'] != force._code_identity()
            or fresh['source_family'] != force._family(Path(fresh['source']), fresh['board_hint'])):
        raise ValueError('Source_pair_reference_changed_before_private_save')
    _tick(deadline)
    result = dict(complete=True, candidate=str(target), candidate_sha256=force._hash(target),
        construction=proof, routing_admitted=False, current_capacity_qualified=False,
        all_original_parent_gates_still_required=True, release_authority=False)
    _tick(deadline)
    return result


def receive(source, candidate, *, board_hint, pair_name, signal_via_uuids, position_nm, timeout_s=10.):
    result = dict(ok=False, complete=False, errors=[], scope_only=True, routing_admitted=False,
        current_capacity_qualified=False, all_original_parent_gates_still_required=True, release_authority=False)
    try:
        deadline = lease._deadline(timeout_s)
        source, candidate = [Path(p).resolve(strict=True) for p in (source, candidate)]
        if source == candidate:
            raise ValueError('distinct_saved_pair_reference_boundaries_required')
        epoch = force._code_identity()
        families = [force._family(p, board_hint) for p in (source, candidate)]
        fresh = plan(source, board_hint=board_hint, pair_name=pair_name, signal_via_uuids=signal_via_uuids,
            position_nm=position_nm, timeout_s=min(10., max(.001, deadline-time.monotonic())))
        _, old = additive._nodes(source); new_root, new = additive._nodes(candidate)
        incoming = new.keys()-old.keys()
        if old.keys()-new.keys() or len(incoming) != 1 or new[next(iter(incoming))][0] != 'via':
            raise ValueError('one_new_pair_reference_Ground_barrel_without_retirement_required')
        projected, proof = _construct_fresh(fresh, next(iter(incoming)), deadline)
        with tempfile.TemporaryDirectory(prefix='cec-pair-reference-independent-') as work:
            expected = force._copy_family(source, Path(work)/'expected')
            text_io.write_raw(expected, geometry._literal_text(source, projected, fresh))
            expected_root = additive._nodes(expected)[0]
        if (syntax._freeze(expected_root) != syntax._freeze(new_root)
                or force._sidecars(source) != force._sidecars(candidate)):
            raise ValueError('saved_pair_reference_differs_from_independent_Source_replay')
        parent, child = [pcbnew.LoadBoard(str(p)) for p in (source, candidate)]
        paired = partitions.compare(parent, child,
            timeout_s=min(10., max(.001, deadline-time.monotonic())))
        if paired.get('available') is not True or paired.get('preserved') is not True:
            raise ValueError('pair_reference_window_demoted_a_retained_native_partition')
        # This operation supplies a local return, not a Source Ground-island
        # join. Check the complete Source relation, not just no disconnections.
        source_parts = {frozenset(part) for part in paired['source_parts']}
        source_keys = set().union(*source_parts)
        child_parts = {frozenset(k for k in part if k in source_keys)
                       for part in paired['child_parts']}
        child_parts.discard(frozenset())
        if child_parts != source_parts:
            raise ValueError('pair_reference_window_cannot_merge_Source_native_partitions')
        _, vias = _transition(child, candidate, pair_name, signal_via_uuids)
        if not all(_covered(child, v) for v in vias if force._uid(v) in fresh['Source_members_within_reach']):
            raise ValueError('saved_pair_reference_return_contact_not_completed')
        if (epoch != force._code_identity()
                or families != [force._family(p, board_hint) for p in (source, candidate)]):
            raise ValueError('Source_pair_reference_saved_epoch_changed')
        _tick(deadline)
        result.update(ok=True, complete=True, source_sha256=force._hash(source),
            candidate_sha256=force._hash(candidate), construction=proof,
            every_Source_native_partition_identical=True, local_return_completed=True,
            native_open_progress_claimed=False)
        _tick(deadline)
    except Exception as exc:
        result.update(ok=False, complete=False); result['errors'].append(str(exc))
    return result
