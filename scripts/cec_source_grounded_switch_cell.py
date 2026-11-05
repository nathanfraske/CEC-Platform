"""Literal-Source scope for a bounded grounded power-switch repack.

This is deliberately NOT a low-power IC alias. Manufacturer G/S/D identity,
the existing whole drain-current contract and EVERY native departure are
required. Two existing in-pad barrels may follow their own lands; no new
barrel, sharing credit, current rating, completed route or pose admission is
granted. A caller still owes an original-parent, saved-candidate receiver.
"""
import math
from pathlib import Path
import time

import pcbnew
import cec_control_gate_bias_placement as identity
import cec_force_current as force
import cec_full_current_planar_reflow as full
import cec_source_ground_leaf as canonical
import cec_source_netlist_semantics as semantic
import cec_synth_pipeline as synth


ROLE = 'source_grounded_switch_cell'


def _need(value, reason):
    if not value:
        raise ValueError(reason)


def _tick(deadline):
    _need(time.monotonic() < deadline, 'grounded_switch_source_deadline')


def _pose(fp, target, maximum):
    _need(type(maximum) in (int, float) and math.isfinite(maximum)
          and 0 < maximum <= 10, 'bounded_grounded_switch_source_reach_required')
    _need(type(target) in (list, tuple) and len(target) == 3
          and all(type(v) in (int, float) and math.isfinite(v) for v in target)
          and all(abs(v) <= 2000 for v in target[:2])
          and fp.GetOrientationDegrees() % 90 == 0
          and (target[2] - fp.GetOrientationDegrees()) % 90 == 0,
          'literal_cardinal_grounded_switch_pose_required')
    at = tuple(round(v * 1e6) for v in target[:2])
    _need(math.dist(at, tuple(fp.GetPosition())) <= maximum * 1e6,
          'grounded_switch_source_reach_exceeded')
    return [*target[:2], target[2] % 360]


def _items(board):
    result = [*(p for f in board.GetFootprints() for p in f.Pads()),
              *board.GetTracks()]
    _need(len(result) + len(list(board.Zones())) <= 16384,
          'bounded_grounded_switch_native_inventory_required')
    return result


def _touch(board, conductor, deadline):
    """Actual all-face direct copper, never whole-net reachability/proximity."""
    rows = []
    for face in conductor.GetLayerSet().CuStack():
        shape = conductor.GetEffectiveShape(face)
        for item in _items(board):
            _tick(deadline)
            if force._uid(item) == force._uid(conductor) or not item.IsOnLayer(face):
                continue
            other = item.GetEffectiveShape(face)
            if not shape.BBox().Intersects(other.BBox()) or not shape.Collide(other, 0):
                continue
            _need(item.GetNetCode() == conductor.GetNetCode(),
                  'grounded_switch_Source_foreign_copper_contact')
            rows.append(dict(uuid=force._uid(item), kind=item.GetClass(),
                             layer_id=int(face)))
        for zone in board.Zones():
            _tick(deadline)
            if zone.GetIsRuleArea() or not zone.IsOnLayer(face):
                continue
            filled = zone.GetFilledPolysList(face)
            if filled.OutlineCount() and filled.Collide(shape, 0):
                _need(zone.GetNetCode() == conductor.GetNetCode(),
                      'grounded_switch_Source_foreign_fill_contact')
                rows.append(dict(uuid=force._uid(zone), kind='ZONE', layer_id=int(face)))
            elif zone.Outline().Collide(shape, 0):
                _need(zone.HasFilledPolysForLayer(face),
                      'grounded_switch_contact_requires_actual_saved_zone_fill')
    return sorted(rows, key=lambda r: (r['layer_id'], r['kind'], r['uuid']))


def _barrel(board, pad, deadline):
    import cec_fab_profile as fab
    direct = _touch(board, pad, deadline)
    ids = {r['uuid'] for r in direct if r['kind'] == 'PCB_VIA'}
    _need(len(ids) == 1, 'one_existing_grounded_switch_inpad_barrel_per_power_pin_required')
    via = next(t for t in board.GetTracks() if force._uid(t) in ids)
    _need(via.GetViaType() == pcbnew.VIATYPE_THROUGH
          and via.TopLayer() == pcbnew.F_Cu and via.BottomLayer() == pcbnew.B_Cu
          and tuple(via.GetPosition()) == tuple(pad.GetPosition())
          and set(map(int, via.GetLayerSet().CuStack())) == set(map(int, board.GetEnabledLayers().CuStack())),
          'exact_existing_centered_grounded_switch_through_barrel_required')
    ok, why = fab.local_pofv_via_decision(board, via, allow_source_track_body=False)
    _need(ok and why == 'fully contained same-net SMD POFV',
          'source_grounded_switch_existing_barrel_requires_full_land_POFV')
    groups = identity._groups(board, via)
    _need(not groups or len(groups) == 1 and groups[0]['name'] == 'CEC_LOCAL_POFV_SIGNAL_VIA'
          and groups[0]['parent'] is None,
          'grounded_switch_barrel_has_unrecognized_group_owner')
    material = identity._track(board, via)
    return via, dict(uuid=force._uid(via), pad_uuid=force._uid(pad),
        material=material, source_pad_contacts=direct,
        source_all_face_contacts=_touch(board, via, deadline),
        factory_geometry_witness=why, barrel_current_qualified=False,
        move_only_with_same_Source_land=True, new_barrel_authority=False)


def _edge(track, board, deadline):
    _tick(deadline)
    _need(track.GetClass() == 'PCB_TRACK' and not track.IsLocked()
          and not identity._groups(board, track) and track.GetParentGroup() is None
          and 0 < track.GetLength() <= 8e6,
          'bounded_unlocked_ungrouped_grounded_switch_source_edge_required')
    a, z = tuple(track.GetStart()), tuple(track.GetEnd())
    dx, dy = z[0] - a[0], z[1] - a[1]
    _need(dx == 0 or dy == 0 or abs(dx) == abs(dy),
          'grounded_switch_Source_edge_must_be_octilinear')
    return identity._track(board, track)


def _gate_chain(board, gate, deadline):
    direct = _touch(board, gate, deadline)
    first = {r['uuid'] for r in direct}
    _need(len(first) == 1 and all(r['kind'] == 'PCB_TRACK' for r in direct),
          'grounded_switch_gate_requires_one_unbranched_trace_departure')
    inventory = {force._uid(t): t for t in board.GetTracks()}
    edge = inventory[next(iter(first))]; start = tuple(gate.GetPosition())
    face = int(gate.GetLayerSet().CuStack()[0]); chain = []
    while True:
        material = _edge(edge, board, deadline)
        _need(edge.GetLayer() == face and edge.GetNetCode() == gate.GetNetCode()
              and (tuple(edge.GetStart()) == start) != (tuple(edge.GetEnd()) == start),
              'grounded_switch_gate_exact_endpoint_chain_required')
        far = tuple(edge.GetEnd()) if tuple(edge.GetStart()) == start else tuple(edge.GetStart())
        chain.append(edge)
        _need(len(chain) <= 8 and sum(t.GetLength() for t in chain) <= 16e6,
              'grounded_switch_gate_source_chain_bound')
        contacts = _touch(board, edge, deadline)
        allowed = {force._uid(gate)} | {force._uid(t) for t in chain}
        pending = {r['uuid'] for r in contacts if r['uuid'] not in allowed}
        _need(len(pending) == 1, 'grounded_switch_gate_branch_or_midsegment_contact_refused')
        uid = next(iter(pending)); following = inventory.get(uid)
        _need(following is not None, 'grounded_switch_gate_requires_fixed_native_via_boundary')
        if following.GetClass() == 'PCB_VIA':
            _need(tuple(following.GetPosition()) == far and following.IsOnLayer(face)
                  and following.GetNetCode() == gate.GetNetCode(),
                  'grounded_switch_gate_boundary_must_be_retained_Source_via')
            return chain, dict(role='gate', source_track_uuid=force._uid(chain[-1]),
                source_track_uuids=[force._uid(t) for t in chain], layer_id=face,
                width_nm=max(t.GetWidth() for t in chain), fixed_boundary_nm=list(far),
                fixed_boundary_item_uuids=[uid], fixed_boundary=identity._track(board, following))
        _need(following.GetClass() == 'PCB_TRACK'
              and force._uid(following) not in {force._uid(t) for t in chain}
              and (tuple(following.GetStart()) == far or tuple(following.GetEnd()) == far),
              'grounded_switch_gate_no_interior_or_cycle_cut')
        edge, start = following, far


def _canonical(board, fp, hint, deadline):
    root = canonical.source_nc._root(board, hint)
    _need(root is not None, 'grounded_switch_canonical_source_required')
    root = Path(root).resolve(strict=True)
    files, hashes, instances = canonical._hierarchy(root, deadline)
    tree, exporter = canonical._export(root, deadline)
    _need(Path(exporter.get('exporter', '')).is_file()
          and force._hash(Path(exporter['exporter'])) == exporter.get('exporter_sha256')
          and all(exporter.get(k) == v for k, v in semantic.metadata(tree).items()),
          'grounded_switch_fresh_complete_semantic_export_required')
    comps, nets, nodes = canonical._tables(tree)
    exported = {(synth._val(node, 'ref', ''), synth._val(node, 'pin', '')):
        dict(name=synth._val(node, 'pinfunction', ''), type=synth._val(node, 'pintype', ''))
        for net in synth._kids(synth._first(tree, 'nets'), 'net')
        for node in synth._kids(net, 'node')}
    model = identity._mos(fp)
    datasheet = Path(__file__).resolve().parents[1] / identity.MOS_PDF
    _need(datasheet.is_file() and force._hash(datasheet) == identity.MOS_PDF_SHA256,
          'grounded_switch_reviewed_manufacturer_source_changed')
    proof = identity._identity(board, fp, comps, instances, nodes, exported, deadline, model=model)
    ground_membership = None
    for pad in fp.Pads():
        actual = {(f.GetReference(), p.GetNumber()) for f in board.GetFootprints()
                  for p in f.Pads() if p.GetNetname() == pad.GetNetname()}
        logical = nets.get(pad.GetNetname(), set())
        matches = logical == actual
        if pad.GetNumber() == '2' and pad.GetNetname() == 'GND':
            ground_membership = canonical.complete_ground_membership(
                board, logical, comps, instances, board_hint=hint, deadline=deadline)
            matches = True
        _need(matches,
              'grounded_switch_complete_canonical_terminal_net_membership_required:'
              + str(dict(net=pad.GetNetname(), missing=sorted(logical-actual), extra=sorted(actual-logical))))
    return dict(manufacturer=model, component=proof, Ground_membership=ground_membership,
        semantic=semantic.replay_identity(dict(root_schematic=str(root),
            schematic_files_sha256=hashes, exporter=exporter,
            evidence_files_sha256={str(datasheet): identity.MOS_PDF_SHA256}))), files, hashes, exporter


def plan(source, *, footprint_uuid, target_pose, board_hint, timeout_s=10., max_shift_mm=6.):
    """Fresh, read-only Source scope; no caller copper cuts, models or caches.

    Restore obligations are a construction demand, not successful receiving.
    Body/copper clearance, same reference fills, original native partitions,
    full Source current and every saved final gate remain independently owed.
    """
    import cec_fab_profile as fab
    import cec_ordinary_route_receiving as ordinary
    import cec_source_reference_group_transport as maps
    _need(type(timeout_s) in (int, float) and math.isfinite(timeout_s) and 0 < timeout_s <= 10,
          'bounded_grounded_switch_Source_operation_required')
    _need(type(footprint_uuid) is str and footprint_uuid and type(board_hint) is str and board_hint,
          'literal_grounded_switch_Source_identity_required')
    deadline = time.monotonic() + timeout_s
    source = Path(source).resolve(strict=True)
    _need(source.suffix == '.kicad_pcb' and source.with_suffix('.kicad_pro').is_file(),
          'grounded_switch_exact_saved_Source_family_required')
    epoch = force._code_identity(); family = force._family(source, board_hint)
    sha = force._hash(source); board = pcbnew.LoadBoard(str(source))
    _need(board is not None, 'grounded_switch_native_Source_required')
    matches = [f for f in board.GetFootprints() if force._uid(f) == footprint_uuid]
    _need(len(matches) == 1, 'one_exact_Source_grounded_switch_required')
    fp = matches[0]; target = _pose(fp, target_pose, max_shift_mm)
    _need(not fp.IsLocked() and not fp.IsDNP() and all(not p.IsLocked() for p in fp.Pads()),
          'grounded_switch_populated_unlocked_Source_package_required')
    source_proof, files, hashes, exporter = _canonical(board, fp, board_hint, deadline)
    gate, ground, drain = [fp.FindPadByNumber(n) for n in ('1', '2', '3')]
    _need(ground.GetNetname() == 'GND' and drain.GetNetname() != 'GND'
          and gate.GetNetname() in ordinary.eligible_nets(board, source, board_hint),
          'canonical_grounded_Source_and_positive_ordinary_gate_required')
    source_via, source_barrel = _barrel(board, ground, deadline)
    drain_via, drain_barrel = _barrel(board, drain, deadline)
    source_contacts = source_barrel['source_all_face_contacts']
    _need(all(r['kind'] == 'ZONE' or r['kind'] == 'PAD' and r['uuid'] == force._uid(ground)
              for r in source_contacts), 'grounded_switch_Source_return_has_external_surface_branches')
    profile = fab.board_profile_name(board)
    _need(profile is not None, 'grounded_switch_declared_factory_stackup_required')
    layer_ids = {name: lid for lid, name in fab.COPPER_LAYER_IDS.items()}
    plane_faces = {layer_ids[name] for name, role in
                   zip(fab.COPPER_LAYERS, fab.get_profile(profile)['roles']) if role == 'GND'}
    references = [r for r in source_contacts if r['kind'] == 'ZONE' and r['layer_id'] in plane_faces]
    _need(references and {r['layer_id'] for r in references} == plane_faces,
          'grounded_switch_return_requires_all_actual_declared_Ground_reference_contacts')
    group_proof = None
    groups = identity._groups(board, fp)
    if groups:
        _need(len(groups) == 1 and groups[0]['parent'] is None,
              'grounded_switch_requires_one_closed_Source_reference_map')
        group_proof = maps.inspect_many(source, [(footprint_uuid, groups[0]['uuid'])],
            timeout_s=min(10., max(.001, deadline - time.monotonic())))[0]
    else:
        _need(fp.GetParentGroup() is None, 'grounded_switch_unknown_parent_group')
    kind, domain, current = full._model(board, source, str(drain.GetNetname()), board_hint)
    tracks = {force._uid(t): t for t in board.GetTracks()}
    departures = {r['uuid'] for r in drain_barrel['source_all_face_contacts'] if r['kind'] == 'PCB_TRACK'}
    _need(1 <= len(departures) <= 8 and all(r['kind'] == 'PCB_TRACK'
          or r['kind'] == 'PAD' and r['uuid'] == force._uid(drain)
          for r in drain_barrel['source_all_face_contacts']),
          'grounded_switch_drain_requires_complete_planar_departures_only')
    _need({r['uuid'] for r in drain_barrel['source_pad_contacts']}
          <= departures | {force._uid(drain_via)},
          'grounded_switch_unowned_drain_pad_contact')
    chain, gate_obligation = _gate_chain(board, gate, deadline)
    retired = set(departures) | {force._uid(t) for t in chain}
    obligations = [gate_obligation]; original = {}
    for uid in sorted(departures):
        t = tracks[uid]; original[uid] = _edge(t, board, deadline)
        at = tuple(drain_via.GetPosition())
        _need((tuple(t.GetStart()) == at) != (tuple(t.GetEnd()) == at),
              'grounded_switch_drain_no_interior_or_contained_cut')
        face = int(t.GetLayer()); floor = full._source_width_floor(board, source, current, face)
        _need(t.GetWidth() >= floor, 'grounded_switch_existing_drain_below_whole_current_floor')
        far = tuple(t.GetEnd()) if tuple(t.GetStart()) == at else tuple(t.GetStart())
        probe = pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*far), pcbnew.VECTOR2I(*far), 1)
        external = sorted(force._uid(i) for i in _items(board)
            if force._uid(i) not in retired | {force._uid(drain), force._uid(drain_via)}
            and i.IsOnLayer(face) and i.GetNetCode() == t.GetNetCode()
            and i.GetEffectiveShape(face).Collide(probe, 0))
        _need(external, 'grounded_switch_drain_far_boundary_requires_retained_native_contact')
        direct = _touch(board, t, deadline)
        _need({r['uuid'] for r in direct}
              <= set(external) | {force._uid(drain), force._uid(drain_via)},
              'grounded_switch_drain_has_unowned_midsegment_contact')
        obligations.append(dict(role='drain', source_track_uuid=uid, layer_id=face,
            width_nm=int(t.GetWidth()), full_current_floor_nm=int(floor),
            fixed_boundary_nm=list(far), fixed_boundary_item_uuids=external,
            source_direct_contacts=direct))
    original.update({force._uid(t): identity._track(board, t) for t in chain})
    _need(sum(tracks[u].GetLength() for u in retired) <= 32e6,
          'grounded_switch_total_Source_cut_bound')
    # Loading a hostile/shorted Source can itself normalize an authored via
    # net. Compare literal saved nets before that normalized object is ever
    # treated as ownership or a fixed restoration boundary. Include every
    # direct native copper peer named by this scope, not just removed edges.
    import cec_source_literal_additions as literal
    copper_scope = retired | {force._uid(source_via), force._uid(drain_via)}
    for barrel in (source_barrel, drain_barrel):
        copper_scope.update(r['uuid'] for r in barrel['source_all_face_contacts'] if r['uuid'] in tracks)
    for obligation in obligations:
        copper_scope.update(u for u in obligation['fixed_boundary_item_uuids'] if u in tracks)
        copper_scope.update(r['uuid'] for r in obligation.get('source_direct_contacts', ()) if r['uuid'] in tracks)
    authored = literal.incoming_copper_nets(source.read_text(), copper_scope)
    _need(all(authored[u] == tracks[u].GetNetname() for u in copper_scope),
          'grounded_switch_literal_saved_copper_net_differs_from_native_load')
    target_fp = pcbnew.FOOTPRINT(fp)
    target_fp.SetPosition(pcbnew.VECTOR2I(*(round(v * 1e6) for v in target[:2])))
    target_fp.SetOrientationDegrees(target[2])
    _tick(deadline)
    _need(sha == force._hash(source) and epoch == force._code_identity()
          and family == force._family(source, board_hint)
          and hashes == {str(p): force._hash(p) for p in files}
          and force._hash(Path(exporter['exporter'])) == exporter['exporter_sha256'],
          'grounded_switch_Source_canonical_family_or_code_changed')
    _tick(deadline)
    return identity._wire(dict(schema=1, role=ROLE, source=str(source), source_sha256=sha,
        source_family=family, source_code_identity=epoch, board_hint=board_hint,
        source_proof=source_proof, footprint_uuid=footprint_uuid,
        source_footprint=identity._footprint(board, fp), target_pose=target,
        target_pads={p.GetNumber(): identity._pad(p) for p in target_fp.Pads()},
        source_barrels=dict(source=source_barrel, drain=drain_barrel),
        source_reference_contacts=references,
        source_reference_group_transport=group_proof,
        source_retired_track_uuids=sorted(retired), source_retired_material=original,
        source_literal_copper_nets=authored,
        source_restore_obligations=obligations,
        current_contract=current, current_domain_kind=kind, current_domain=domain,
        all_Source_departures_mandatory=True, Source_barrel_geometry_must_remain_exact=True,
        all_shared_group_peers_must_remain_exact=True, original_parent_receiving_required=True,
        physical_placement_admitted=False, routing_admitted=False, current_authority=False,
        new_barrel_authority=False, current_sharing_inferred=False,
        switch_current_or_timing_qualified=False, barrel_current_qualified=False,
        power_or_thermal_qualified=False, release_authority=False))
