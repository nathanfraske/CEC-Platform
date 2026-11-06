"""Standalone source-canonical out-of-range bypass role; NOT an actuator.

An explicit intent identifies a missing requirement, not a fictional old
assignment. This module grants no cuts, routes, current or admission authority.
"""
import copy
import json
import math
from pathlib import Path
import time
import tempfile

import pcbnew
import cec_constraints as constraints
import cec_device_bypass as bypass
import cec_device_power_roles as roles
import cec_force_current as force
import cec_source_ground_leaf as leaf
import cec_source_literal_additions as literal
from cec_footprint_fields import footprint_properties

SCOPE = 'source_canonical_missing_bypass_corrective_role-v1'


def _wire(value):
    return json.loads(json.dumps(value, sort_keys=True, allow_nan=False))


def _replay_identity(proposal):
    # Fresh CLI exports include the current time. Keep the raw digest as
    # evidence, but compare the existing full-tree semantic identity, which
    # excludes only the single generated design/date value.
    import cec_source_netlist_semantics as semantic
    result = copy.deepcopy(proposal)
    result['canonical'] = semantic.replay_identity(result['canonical'])
    return result


def _need(ok, reason):
    if not ok: raise ValueError(reason)


def _assignment(board, hint):
    with force._thermal_hint(hint):
        return constraints._device_bypass_assignment(board, project_max_mm=3.5)


def _role(req):
    return {k: req.get(k) for k in ('id', 'ref', 'pin', 'rail', 'kind',
        'return_rail', 'return_pin', 'max_mm', 'source')}


def _assignments(inventory):
    return {key: dict(cap_ref=row['cap_ref'], requirement=_role(row['requirement']))
        for key, row in inventory['assigned'].items()}


def _compatible(fp, req):
    props = footprint_properties(fp); declared = bypass.declared_owner(props)
    pads = list(fp.Pads())
    farads = bypass.capacitance_f(fp.GetValue())
    return (not fp.IsDNP() and not fp.IsExcludedFromBOM()
        and bypass.capacitor_identity(fp.GetReference(), fp.GetFPIDAsString())
        and len(pads) == 2 and {p.GetNetname() for p in pads} == {req['rail'], 'GND'}
        and all(p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD and not p.HasHole() for p in pads)
        and bypass.local_bypass_technology(fp.GetValue(), fp.GetFPIDAsString())
        and farads is not None and bypass.kind_compatible(req['kind'], farads)
        and (declared is None or declared[0] == req['ref']
             and (not declared[1] or declared[1] == str(req['pin']))))


def _canonical(board, cap, owner, req, hint, deadline):
    """Fresh hierarchy/export and selected manufacturer pin identity."""
    import cec_quiet_signal_requests as pins
    root = leaf.source_nc._root(board, hint)
    _need(root is not None, 'canonical_missing_bypass_source_required')
    root = root.resolve(); files, hashes, instances = leaf._hierarchy(root, deadline)
    tree, exporter = leaf._export(root, deadline)
    comps, nets, node_net = leaf._tables(tree)
    model = roles.footprint_contract(owner)
    _need(model and {p.GetNumber() for p in owner.Pads()} == set(model['pins'])
        and len(list(owner.Pads())) == len(model['pins'])
        and model['pins'].get(str(req['pin'])) in ('power_input', 'power_output'),
        'complete_manufacturer_missing_bypass_owner_required')
    for fp in (cap, owner):
        identity = leaf._identity(board, fp.GetReference(), comps, instances, deadline)
        exported = {leaf.synth._val(p, 'name', ''): leaf.synth._val(p, 'value', '')
            for p in leaf.synth._kids(comps[fp.GetReference()], 'property')}
        blocks = [b for tag, b in identity[2].children if tag == 'symbol'
            and leaf.sch.prop_value(b, 'Reference') == fp.GetReference()]
        _need(len(blocks) == 1, 'unique_missing_bypass_source_symbol_required')
        for key in ('MPN', 'Manufacturer'):
            value = footprint_properties(fp).get(key)
            _need(value and exported.get(key) == value
                and leaf.sch.prop_value(blocks[0], key) == value,
                'missing_bypass_selected_source_field_mismatch:' + key)
        # Notes are never interpreted. Explicit owner fields, if present, must
        # agree in all three representations; intent never rewrites them.
        value = footprint_properties(fp).get('BypassOwner', '') or ''
        _need((exported.get('BypassOwner', '') or '') == value
            and (leaf.sch.prop_value(blocks[0], 'BypassOwner') or '') == value,
            'missing_bypass_source_owner_declaration_mismatch')
        for pad in fp.Pads():
            _need(node_net.get((fp.GetReference(), pad.GetNumber())) == pad.GetNetname(),
                'missing_bypass_source_pin_net_mismatch')
            if fp == cap:
                pin = pins._source_pin(identity, pad.GetNumber(), deadline)
                _need(pin['type'] == 'passive', 'canonical_passive_capacitor_required')
            elif pad.GetNumber() == str(req['pin']):
                pin = pins._source_pin(identity, pad.GetNumber(), deadline)
                _need(pin['type'] in ('power_in', 'power_out'), 'canonical_power_owner_pin_required')
    for pad in cap.Pads():
        exported = nets.get(pad.GetNetname(), set())
        if pad.GetNetname() == 'GND':
            leaf.complete_ground_membership(board, exported, comps, instances,
                board_hint=hint, deadline=deadline)
        else:
            native = {(fp.GetReference(), p.GetNumber()) for fp in board.GetFootprints()
                for p in fp.Pads() if p.GetNetname() == pad.GetNetname()}
            _need(native == exported, 'complete_missing_bypass_rail_membership_required')
    _need(hashes == {str(p): force._hash(p) for p in files}, 'missing_bypass_hierarchy_changed')
    return dict(root=str(root), files_sha256=hashes, exporter=exporter,
        manufacturer_source=model['source'])


def _current(board, rail, hint):
    import cec_decoupler_cell as cells
    with force._thermal_hint(hint):
        result = cells._supply_current_widths(board, rail)
    _need(isinstance(result, dict) and bool(result), 'existing_source_rail_current_contract_required')
    return result


def plan(source, intent, *, board_hint, timeout_s=10.):
    """Bind explicit intent to one actual out-of-range source capacitor."""
    _need(type(timeout_s) in (int, float) and math.isfinite(timeout_s) and 0 < timeout_s <= 10,
        'bounded_missing_bypass_lease_required')
    _need(type(board_hint) is str and bool(board_hint), 'missing_bypass_board_authority_required')
    _need(type(intent) is dict and set(intent) == {
        'source_sha256', 'requirement_id', 'capacitor_uuid', 'owner_pad_uuid'}
        and all(type(v) is str and bool(v) for v in intent.values()), 'exact_missing_bypass_intent_required')
    deadline = time.monotonic() + timeout_s
    source = Path(source).resolve(strict=True); digest = force._hash(source)
    _need(digest == intent['source_sha256'], 'missing_bypass_source_hash_mismatch')
    epoch = force._code_identity(); family = force._family(source, board_hint)
    board = pcbnew.LoadBoard(str(source)); inventory = _assignment(board, board_hint)
    rows = [r for r in inventory['missing'] if r['id'] == intent['requirement_id']]
    _need(len(rows) == 1, 'unique_source_missing_bypass_requirement_required')
    req = rows[0]
    _need((req.get('return_rail') or 'GND') == 'GND'
        and req.get('return_pin') is None and type(req['max_mm']) in (int, float)
        and math.isfinite(req['max_mm']) and 0 < req['max_mm'] <= 3.5,
        'bounded_ordinary_missing_bypass_requirement_required')
    caps = [fp for fp in board.GetFootprints() if force._uid(fp) == intent['capacitor_uuid']]
    owners = [fp for fp in board.GetFootprints() if fp.GetReference() == req['ref']]
    _need(len(caps) == len(owners) == 1, 'unique_missing_bypass_native_owners_required')
    cap, owner = caps[0], owners[0]; pad = owner.FindPadByNumber(str(req['pin']))
    _need(cap != owner and not cap.IsLocked() and not owner.IsDNP() and pad is not None
        and force._uid(pad) == intent['owner_pad_uuid'] and pad.GetNetname() == req['rail']
        and cap.IsFlipped() == owner.IsFlipped() and _compatible(cap, req),
        'exact_compatible_missing_bypass_native_identity_required')
    _need(not any(r['cap_ref'] == cap.GetReference() for r in inventory['assigned'].values()),
        'missing_bypass_cannot_steal_assigned_capacitor')
    _need(not any(r['id'] != req['id'] and _compatible(cap, r) for r in inventory['requirements']),
        'missing_bypass_competing_owner_refused')
    supply = next(p for p in cap.Pads() if p.GetNetname() == req['rail'])
    distance = math.dist(tuple(pad.GetPosition()), tuple(supply.GetPosition())) / 1e6
    compatible = [fp for fp in board.GetFootprints() if _compatible(fp, req)]
    distances = [(math.dist(tuple(pad.GetPosition()), tuple(next(p for p in fp.Pads()
        if p.GetNetname() == req['rail']).GetPosition())) / 1e6, fp) for fp in compatible]
    _need(distance > req['max_mm'] and req.get('nearest_ref') == cap.GetReference()
        and type(req.get('nearest_mm')) in (int, float)
        and abs(req['nearest_mm'] - distance) < 1e-9
        and all(fp == cap or d > distance + 1e-9 for d, fp in distances),
        'unique_nearest_out_of_range_bypass_not_contention_required')
    canonical = _canonical(board, cap, owner, req, board_hint, deadline)
    current = _current(board, req['rail'], board_hint)
    ports = [dict(uuid=force._uid(p), pin=p.GetNumber(), net=p.GetNetname(),
        at_nm=list(p.GetPosition()), layers=list(map(int, p.GetLayerSet().CuStack()))) for p in cap.Pads()]
    _need(time.monotonic() < deadline and digest == force._hash(source)
        and epoch == force._code_identity() and family == force._family(source, board_hint),
        'missing_bypass_source_epoch_changed')
    return _wire(dict(scope=SCOPE, source=str(source), source_sha256=digest,
        intent=copy.deepcopy(intent), board_hint=board_hint, code_identity=epoch, source_family=family,
        capacitor_ref=cap.GetReference(), requirement=_role(req), source_distance_mm=distance,
        source_assignments=_assignments(inventory), source_missing=sorted(r['id'] for r in inventory['missing']),
        canonical=canonical, unchanged_source_current_contract=current, source_capacitor_ports=ports,
        owner_pad_uuid=force._uid(pad), source_owner_port=dict(uuid=force._uid(pad),
            ref=owner.GetReference(), pin=pad.GetNumber(), net=pad.GetNetname(),
            at_nm=list(pad.GetPosition()), layers=list(map(int, pad.GetLayerSet().CuStack()))),
        complete=True, role_only=True,
        cut_authority=False, route_authority=False, current_authority=False, admitted=False))


def _footprints(path):
    inventory, *_ = literal._inventory(Path(path).read_text())
    result = {}
    for uid, (_, _, text) in inventory.items():
        if literal.kind(text) != 'footprint': continue
        node = leaf.synth.parse_sexpr(text)
        result[uid] = node
    return result


def _receive_parts(source, candidate, uid):
    parent = pcbnew.LoadBoard(str(source)); child = pcbnew.LoadBoard(str(candidate))
    old = [fp for fp in parent.GetFootprints() if force._uid(fp) == uid]
    new = [fp for fp in child.GetFootprints() if force._uid(fp) == uid]
    _need(len(old) == len(new) == 1, 'same_missing_bypass_capacitor_uuid_required')
    delta = (new[0].GetOrientationDegrees() - old[0].GetOrientationDegrees()) % 90
    _need(min(delta, 90-delta) < 1e-9 and new[0].IsFlipped() == old[0].IsFlipped(),
        'cardinal_same_surface_missing_bypass_pose_required')
    # Reconstruct the exact native transform, including pad/field angles.
    # Blindly ignoring nested angles would permit process/land corruption.
    old[0].SetOrientationDegrees(new[0].GetOrientationDegrees())
    old[0].SetPosition(new[0].GetPosition())
    with tempfile.TemporaryDirectory(prefix='cec-missing-role-') as work:
        expected = Path(work)/'expected.kicad_pcb'
        pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(expected), parent)
        original_parts = _footprints(source)
        expected_parts = _footprints(expected)
        candidate_parts = _footprints(candidate)
        # Native serialization may normalize unrelated numeric lexemes.
        # Use its rigid transform ONLY for the selected package; all other
        # source packages must remain literally identical in the candidate.
        _need(original_parts.keys() == expected_parts.keys() == candidate_parts.keys()
            and candidate_parts[uid] == expected_parts[uid]
            and all(candidate_parts[key] == value for key, value in original_parts.items() if key != uid),
            'stationary_owner_and_unchanged_source_electrical_parts_required')


def receive(source, candidate, proposal, *, board_hint, timeout_s=10.):
    """Freshly replay source role and candidate assignments, never admission."""
    _need(type(timeout_s) in (int, float) and math.isfinite(timeout_s) and 0 < timeout_s <= 10,
        'bounded_missing_bypass_receiving_lease_required')
    deadline = time.monotonic() + timeout_s
    fresh = plan(source, proposal['intent'], board_hint=board_hint, timeout_s=timeout_s)
    _need(_replay_identity(fresh) == _replay_identity(proposal),
        'missing_bypass_proposal_not_exact_fresh_source_replay')
    candidate = Path(candidate).resolve(strict=True); digest = force._hash(candidate)
    uid = fresh['intent']['capacitor_uuid']
    _receive_parts(Path(source).resolve(strict=True), candidate, uid)
    board = pcbnew.LoadBoard(str(candidate)); final = _assignment(board, board_hint)
    before = fresh['source_assignments']; after = _assignments(final)
    target = fresh['requirement']['id']
    expected = dict(before); expected[target] = dict(cap_ref=fresh['capacitor_ref'], requirement=fresh['requirement'])
    _need(after == expected and sorted(r['id'] for r in final['missing']) ==
        [k for k in fresh['source_missing'] if k != target],
        'repair_must_select_exact_cap_remove_only_target_and_preserve_other_assignments')
    selected = final['assigned'][target]
    _need(type(selected['distance_mm']) in (int, float) and math.isfinite(selected['distance_mm'])
        and 0 <= selected['distance_mm'] <= fresh['requirement']['max_mm'],
        'repaired_bypass_must_meet_original_locality_bound')
    _need(_wire(_current(board, fresh['requirement']['rail'], board_hint)) == fresh['unchanged_source_current_contract'],
        'missing_bypass_source_current_contract_changed')
    _need(time.monotonic() < deadline and digest == force._hash(candidate)
        and force._hash(source) == fresh['source_sha256']
        and force._code_identity() == fresh['code_identity']
        and force._family(source, board_hint) == fresh['source_family'], 'missing_bypass_receiving_epoch_changed')
    return dict(scope=SCOPE, complete=True, ok=True, role_only=True,
        source_sha256=fresh['source_sha256'], candidate_sha256=digest,
        repaired_requirement_id=target, source_distance_mm=fresh['source_distance_mm'],
        candidate_distance_mm=selected['distance_mm'], cut_authority=False, route_authority=False,
        current_authority=False, physical_connectivity_proved=False, admitted=False)
