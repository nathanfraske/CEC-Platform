"""Source-connected ordinary-signal/supply resistors in a moving IC cohort.

This is a distinct passive witness, not an IC, enable/BOOT, bypass, load,
current-sharing, or copper-retirement exception. The canonical resistor,
all ordinary-net peers and their real same-rail power inputs are observed
afresh. Every old native boundary and the complete rail current still owe
the enclosing macro's independent receiving.
"""
import json
import math
from pathlib import Path
import time

import pcbnew
import cec_cell_row_rebuild as row
import cec_control_pullup_placement as pullup
import cec_control_shunt_placement as shunt
import cec_device_power_roles as roles
import cec_force_current as force
import cec_ordinary_route_receiving as ordinary
import cec_quiet_signal_requests as pins
import cec_source_ground_leaf as canonical
import cec_source_netlist_semantics as semantic
import cec_synth_pipeline as synth


def _need(value, reason):
    if not value:
        raise ValueError(reason)


def _remaining(deadline):
    left = deadline-time.monotonic()
    _need(left > 0, 'source_signal_bias_deadline')
    return min(10., left)


def _pose(fp, poses):
    target = poses.get(fp.GetReference(), [fp.GetPosition().x/1e6,
        fp.GetPosition().y/1e6, fp.GetOrientationDegrees()])
    _need(type(target) in (list, tuple) and len(target) == 3
        and all(type(v) in (int, float) and math.isfinite(v) for v in target)
        and (target[2]-fp.GetOrientationDegrees()) % 90 == 0,
        'finite_cardinal_source_signal_bias_pose_required')
    return list(target)


def _peer(board, identity, number, signal_net, supply_net, node_net, hint, deadline):
    fp = identity[0]; model = roles.footprint_contract(fp)
    _need(model is not None and not fp.IsDNP(), 'source_signal_bias_known_peer_package_required')
    roles.physical_pinmap(fp, model, board_hint=hint, timeout_s=_remaining(deadline))
    allowed_roles = {'signal_input', 'signal_output', 'signal_io', 'control', 'address'}
    _need(model['pins'].get(number) in allowed_roles,
        'source_signal_bias_ordinary_manufacturer_peer_required')
    pads = list(fp.Pads()); signal = [p for p in pads if p.GetNumber() == number]
    _need(len(signal) == 1 and signal[0].GetNetname() == signal_net,
        'source_signal_bias_exact_signal_peer_required')
    signal = signal[0]; source_pin = pins._source_pin(identity, number, deadline)
    _need(source_pin['type'] in {'input', 'output', 'bidirectional', 'tri_state',
        'open_collector', 'open_emitter'}, 'source_signal_bias_canonical_signal_type_required')
    expected = signal.GetPinFunction() or model.get('native_pin_functions', {}).get(number)
    _need(not expected or source_pin['name'] == expected,
        'source_signal_bias_manufacturer_signal_name_changed')
    power = []
    for pad in pads:
        _remaining(deadline)
        _need(node_net.get((fp.GetReference(), pad.GetNumber())) == pad.GetNetname(),
            'source_signal_bias_complete_peer_pad_nets_required')
        if model['pins'].get(pad.GetNumber()) != 'power_input' or pad.GetNetname() != supply_net:
            continue
        source_power = pins._source_pin(identity, pad.GetNumber(), deadline)
        _need(source_power['type'] == 'power_in', 'source_signal_bias_canonical_supply_input_required')
        expected = pad.GetPinFunction() or model.get('native_pin_functions', {}).get(pad.GetNumber())
        _need(not expected or source_power['name'] == expected,
            'source_signal_bias_manufacturer_supply_name_changed')
        power.append(dict(pad_uuid=force._uid(pad), number=pad.GetNumber(), source_pin=source_power))
    _need(power, 'source_signal_bias_same_peer_source_supply_required')
    return dict(owner=fp.GetReference(), owner_uuid=force._uid(fp),
        source_symbol_uuid=identity[3]['uuid'], manufacturer=model,
        signal_pad_uuid=force._uid(signal), signal_number=number, source_signal_pin=source_pin,
        supply_inputs=sorted(power, key=lambda r: r['pad_uuid']))


def plan(board, poses, *, board_hint, timeout_s=10., reference_group_uuids=(), excluded_refs=()):
    """Observe a real supply/signal resistor; names do not confer eligibility."""
    _need(type(poses) is dict and 1 <= len(poses) <= 8 and type(board_hint) is str and board_hint
        and type(timeout_s) in (int, float) and math.isfinite(timeout_s) and 0 < timeout_s <= 10,
        'bounded_source_signal_bias_context_required')
    _need(type(excluded_refs) in (tuple, list, set) and len(excluded_refs) <= 8
        and all(type(v) is str for v in excluded_refs), 'bounded_distinct_source_passive_roles_required')
    shunt._reference_group_scope(reference_group_uuids)
    deadline = time.monotonic()+timeout_s; candidates = []
    for ref in sorted(set(poses)-set(excluded_refs)):
        fp = board.FindFootprintByReference(ref)
        if fp is None:
            continue
        pads = list(fp.Pads())
        if (len(pads) == 2 and len({p.GetNumber() for p in pads}) == 2
                and len({p.GetNetname() for p in pads}) == 2
                and all(p.GetNetCode() > 0 and p.GetNetname() != 'GND' for p in pads)
                and pullup._ohms(fp.GetValue()) is not None):
            candidates.append(fp)
    if not candidates:
        return {}
    eligible = ordinary.eligible_nets(board, Path(board.GetFileName()), board_hint)
    candidates = [(fp, [p for p in fp.Pads() if p.GetNetname() in eligible]) for fp in candidates]
    candidates = [(fp, signal[0]) for fp, signal in candidates if len(signal) == 1]
    if not candidates:
        return {}
    binding = row._source_binding(board); epoch = force._code_identity()
    authorized = shunt._reference_group_authorizations(board, poses, reference_group_uuids,
        binding=binding, deadline=deadline)
    root = canonical.source_nc._root(board, board_hint)
    _need(root is not None, 'source_signal_bias_canonical_root_required'); root = root.resolve()
    files, hashes, instances = canonical._hierarchy(root, deadline)
    tree, exporter = canonical._export(root, deadline)
    _need(all(exporter.get(key) == value for key, value in semantic.metadata(tree).items()),
        'source_signal_bias_fresh_export_semantics_required')
    comps, nets, node_net = canonical._tables(tree)
    import cec_additive_route_receiving as additive
    groups = {force._uid(i) for g in board.Groups() for i in g.GetItems()}
    groups.update(u for n in additive._nodes(board.GetFileName())[1].values()
        if n[0] == 'group' for u in additive._members(n))
    identities = {}; result = {}
    def identity(ref):
        if ref not in identities:
            identities[ref] = canonical._identity(board, ref, comps, instances, deadline)
        return identities[ref]
    for fp, signal in candidates:
        _remaining(deadline); ref = fp.GetReference(); ri = identity(ref); pads = list(fp.Pads())
        _need(synth._val(synth._first(comps[ref], 'libsource'), 'part', '') in ('R', 'R_Small'),
            'source_signal_bias_canonical_resistor_required')
        _need(not fp.IsLocked() and not fp.IsDNP()
            and ((not fp.GetParentGroup() and force._uid(fp) not in groups) or force._uid(fp) in authorized)
            and all(not p.IsLocked() and force._uid(p) not in groups and not p.HasHole()
                and p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD for p in pads),
            'source_signal_bias_unlocked_populated_two_smd_resistor_required')
        supply = next(p for p in pads if force._uid(p) != force._uid(signal))
        _need(all(canonical._pin(ri, p.GetNumber())['type'] == 'passive'
            and node_net.get((ref, p.GetNumber())) == p.GetNetname() for p in pads),
            'source_signal_bias_two_canonical_passive_nets_required')
        peers = []
        nodes = sorted(nets.get(signal.GetNetname(), set()))
        _need(2 <= len(nodes) <= 32 and (ref, signal.GetNumber()) in nodes,
            'bounded_complete_source_signal_bias_peer_net_required')
        for other, number in nodes:
            if other == ref:
                _need(number == signal.GetNumber(), 'source_signal_bias_single_signal_terminal_required')
                continue
            peers.append(_peer(board, identity(other), number, signal.GetNetname(), supply.GetNetname(),
                node_net, board_hint, deadline))
        _need(peers, 'source_signal_bias_positive_manufacturer_peers_required')
        peers.sort(key=lambda r: (r['owner_uuid'], r['signal_pad_uuid']))
        proof = semantic.replay_identity(dict(root_schematic=str(root), schematic_files_sha256=hashes,
            exporter=exporter, canonical_signal_nodes=nodes, source_symbol_uuid=ri[3]['uuid'], peers=peers))
        item = dict(role='source_canonical_ordinary_signal_supply_resistor',
            resistor_uuid=force._uid(fp), signal_pad_uuid=force._uid(signal), supply_pad_uuid=force._uid(supply),
            signal_net=signal.GetNetname(), supply_net=supply.GetNetname(), source_value=fp.GetValue(),
            nominal_resistance_ohms=pullup._ohms(fp.GetValue()), source_symbol_uuid=ri[3]['uuid'],
            peers=peers, source_proof=proof, source_native_binding=binding, source_code_identity=epoch,
            bypass_owner=False, current_authority=False, load_or_timing_qualified=False,
            source_trace_retirement_authority=False, release_authority=False)
        _pose(fp, poses)
        if force._uid(fp) in authorized:
            item['source_reference_group_authorization'] = authorized[force._uid(fp)]
        result[ref] = item
    _remaining(deadline)
    _need(binding == row._source_binding(board) and epoch == force._code_identity()
        and hashes == {str(p): force._hash(p) for p in files}
        and force._hash(Path(exporter['exporter'])) == exporter['exporter_sha256'],
        'source_signal_bias_source_family_or_code_changed')
    return json.loads(json.dumps(result, allow_nan=False))


def _rigid_part(original, child, poses):
    import cec_source_current_pad_ports as ports
    expected = pcbnew.FOOTPRINT(original); target = _pose(original, poses)
    expected.SetPosition(pcbnew.VECTOR2I(*(round(v*1e6) for v in target[:2])))
    expected.SetOrientationDegrees(target[2])
    def group_state(fp):
        opaque = fp.GetParentGroup()
        if opaque is None:
            return None
        # EDA_GROUP is a different C++ base subobject from PCB_GROUP; their
        # raw SWIG addresses need not agree. Ask the actual native groups
        # about exact membership instead of comparing cross-class pointers.
        matches = [g for g in fp.GetBoard().Groups() if g.ContainsItem(fp)]
        _need(len(matches) == 1 and matches[0].GetParentGroup() is None,
            'source_signal_bias_exact_top_level_group_required')
        group = matches[0]
        return (force._uid(group), bool(group.IsLocked()), sorted(force._uid(i) for i in group.GetItems()))
    _need(force._uid(original) == force._uid(child)
        and original.GetReference() == child.GetReference() and original.GetValue() == child.GetValue()
        and original.GetFPIDAsString() == child.GetFPIDAsString()
        and canonical.footprint_properties(original) == canonical.footprint_properties(child)
        and original.GetAttributes() == child.GetAttributes() and original.IsDNP() == child.IsDNP()
        and original.IsLocked() == child.IsLocked() and original.IsFlipped() == child.IsFlipped()
        and group_state(original) == group_state(child)
        and tuple(expected.GetPosition()) == tuple(child.GetPosition())
        and abs((expected.GetOrientationDegrees()-child.GetOrientationDegrees()+180) % 360-180) < 1e-9
        and sorted(ports._pad_identity(p) for p in expected.Pads()) == sorted(ports._pad_identity(p) for p in child.Pads()),
        'source_signal_bias_rigid_source_package_changed')


def requests(source, board, proposal, *, timeout_s=10.):
    _need(type(timeout_s) in (int, float) and math.isfinite(timeout_s) and 0 < timeout_s <= 10,
        'bounded_source_signal_bias_request_context_required')
    selected = proposal.get('selected_signal_bias_resistors', {})
    if not selected:
        return {}
    deadline = time.monotonic()+timeout_s
    excluded = set().union(*(set(proposal.get(key, {})) for key in
        ('selected_control_shunts', 'selected_control_pullups', 'selected_control_gate_biases', 'selected_programming_resistors')))
    import cec_programming_resistor_placement as programming
    excluded.update(programming.participant_refs(proposal.get('selected_programming_resistors',{})))
    excluded.update(proposal.get('selected_source_series_links',{}))
    fresh = plan(source, proposal['poses'], board_hint=proposal['board_hint'], timeout_s=_remaining(deadline),
        reference_group_uuids=proposal.get('reference_group_uuids', ()), excluded_refs=excluded)
    _need(fresh == selected, 'fresh_source_signal_bias_proof_required')
    import cec_decoupler_cell as cells
    pads = {force._uid(p): p for f in board.GetFootprints() for p in f.Pads()}
    old = {force._uid(p): p for f in source.GetFootprints() for p in f.Pads()}
    result = {}
    def endpoint(p):
        return dict(pad_uuid=force._uid(p), at_nm=list(p.GetPosition()), layers=list(map(int, p.GetLayerSet().CuStack())))
    for ref, item in selected.items():
        _remaining(deadline)
        original = source.FindFootprintByReference(ref); child = board.FindFootprintByReference(ref)
        _need(original is not None and child is not None, 'source_signal_bias_same_resistor_required')
        _rigid_part(original, child, proposal['poses'])
        checked = set()
        for peer in item['peers']:
            if peer['owner_uuid'] not in checked:
                first = source.FindFootprintByReference(peer['owner']); last = board.FindFootprintByReference(peer['owner'])
                _need(first is not None and last is not None, 'source_signal_bias_all_original_peers_required')
                _rigid_part(first, last, proposal['poses']); checked.add(peer['owner_uuid'])
        # A deterministic anchor does not erase any other peer. All peer
        # packages above, ALL old native contacts in the enclosing macro,
        # and the complete saved partition receiver remain mandatory.
        anchor = item['peers'][0]
        ids = [item['signal_pad_uuid'], item['supply_pad_uuid'],
            anchor['signal_pad_uuid'], anchor['supply_inputs'][0]['pad_uuid']]
        _need(all(u in pads and u in old for u in ids), 'source_signal_bias_complete_actual_lands_required')
        signal, supply, target, vdd = [pads[u] for u in ids]
        with force._thermal_hint(proposal['board_hint']):
            rail = cells._supply_current_widths(source, item['supply_net'])
        widths = rail.get('required_by_layer_nm') if type(rail) is dict else None
        _need(type(widths) is dict and set(widths) == set(map(int, source.GetEnabledLayers().CuStack()))
            and widths and all(type(w) is int and w > 0 for w in widths.values())
            and type(rail.get('current_authority')) is dict,
            'source_signal_bias_unchanged_complete_rail_current_required')
        for role, a, b, net in (('control_signal', signal, target, item['signal_net']),
                ('nonload_pullup_supply', supply, vdd, item['supply_net'])):
            width = max(int(board.GetDesignSettings().m_TrackMinWidth), int(cells._netclass(board, net)['width']))
            if role == 'nonload_pullup_supply':
                width = max(width, *widths.values())
            _need(width > 0, 'source_signal_bias_full_source_width_required')
            request = dict(kind='source_boundary', role=role, net=net, a=endpoint(a), b=endpoint(b),
                width_nm=width, source_signal_bias_resistor=item,
                no_source_trace_retirement_authority=True, no_power_bypass_or_current_authority=True,
                nominal_resistance_ohms=item['nominal_resistance_ohms'])
            if role == 'nonload_pullup_supply':
                request.update(unchanged_full_rail_current_contract=rail, new_barrel_authority=False,
                    class_only_supply_prefix_authority=False)
            result['signal_bias:'+force._uid(a)] = request
    _remaining(deadline)
    return result
