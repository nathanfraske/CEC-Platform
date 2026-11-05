"""Real native Source role/contact fixtures; synthetic export/current only.

No test result claims a route, MOS switch rating or saved whole-board grade.
"""
import copy
import hashlib
import json
from pathlib import Path
import uuid

import pcbnew
import pytest

import cec_control_gate_bias_placement as op
import cec_decoupler_cell as cell
import cec_field_coupling as field
import cec_source_ground_leaf as canonical
import cec_source_netlist_semantics as semantic
import cec_synth_pipeline as synth
from cec_native_items import create_empty_board, discard_items
from test_field_proposals import track


def fixture(tmp_path, monkeypatch, *, turn=0, back=False, series=True,
            names=('switch', 'bias', 'series'), annotation=False,
            series_part=('100Ω', '0402WGF1000TCE', 'UNI-ROYAL', 'renamed_library:R_0402_1005Metric')):
    board = create_empty_board(); board.SetCopperLayerCount(2)
    source = tmp_path / 'board.kicad_pcb'; board.SetFileName(str(source))
    for name in ('/opaque/rail', '/opaque/gate', '/opaque/command', 'GND', '/opaque/drain'):
        board.Add(pcbnew.NETINFO_ITEM(board, name))
    source.with_suffix('.kicad_pro').write_text(json.dumps(dict(net_settings=dict(classes=[
        dict(name='Default', track_width=.2, clearance=.2, via_diameter=.6, via_drill=.3),
        dict(name='Power', track_width=.5, clearance=.2, via_diameter=.9, via_drill=.5)],
        netclass_patterns=[dict(netclass='Power', pattern='/opaque/rail')]))))
    def footprint(ref, value, mpn, manufacturer, fpid, center, pins):
        fp = pcbnew.FOOTPRINT(board); fp.SetReference(ref); fp.SetValue(value)
        fp.SetField('MPN', mpn); fp.SetField('Manufacturer', manufacturer)
        fp.SetFPID(pcbnew.LIB_ID(*fpid.split(':'))); fp.SetPosition(pcbnew.VECTOR2I_MM(*center)); board.Add(fp)
        for number, net, at in pins:
            p = pcbnew.PAD(fp); p.SetNumber(number); p.SetNet(board.FindNet(net))
            p.SetAttribute(pcbnew.PAD_ATTRIB_SMD); p.SetShape(pcbnew.PAD_SHAPE_RECT)
            p.SetLayerSet(pcbnew.PAD.SMDMask()); p.SetSize(pcbnew.VECTOR2I_MM(.54, .64))
            p.SetPosition(pcbnew.VECTOR2I_MM(*at)); fp.Add(p)
        return fp
    mos = footprint(names[0], 'AO3400A', 'AO3400A', 'Alpha & Omega Semiconductor',
        'another_library:SOT-23-3_L2.9-W1.3-P1.90-LS2.4-BR', (18, 11),
        [('1', '/opaque/gate', (17, 10)), ('2', 'GND', (17, 12)), ('3', '/opaque/drain', (19, 11))])
    bias = footprint(names[1], '10kΩ', '0402WGF1002TCE', 'UNI-ROYAL',
        'renamed_library:R_0402_1005Metric', (10, 10),
        [('1', '/opaque/rail', (9.5, 10)), ('2', '/opaque/gate', (10.5, 10))])
    peer = footprint(names[2], *series_part, (14, 7),
        [('1', '/opaque/gate', (13.5, 7)), ('2', '/opaque/command', (14.5, 7))]) if series else None
    rail_a = track(board, '/opaque/rail', (9.5, 10), (8, 10), width=.5); rail_a.SetLocked(True)
    rail_b = track(board, '/opaque/rail', (9.5, 10), (9.5, 8), width=.5)
    gate = track(board, '/opaque/gate', (10.5, 10), (17, 10), width=.2)
    ground = track(board, 'GND', (17, 12), (17, 14), width=.5)
    drain = track(board, '/opaque/drain', (19, 11), (22, 11), width=.5)
    if series:
        track(board, '/opaque/gate', (13.5, 7), (13.5, 10), width=.2)
        track(board, '/opaque/command', (14.5, 7), (16, 7), width=.2)
    group = None
    if annotation:
        from test_source_measurement_auxiliary_join import annotation as mapped
        group = mapped(board, bias)
    if turn:
        for item in [*board.GetFootprints(), *board.GetTracks(), *board.GetDrawings()]:
            item.Rotate(pcbnew.VECTOR2I_MM(25, 25), pcbnew.EDA_ANGLE(turn, pcbnew.DEGREES_T))
    if back:
        for item in [*board.GetFootprints(), *board.GetTracks(), *board.GetDrawings()]:
            item.Flip(pcbnew.VECTOR2I_MM(25, 25), False)
    field._save_field_snapshot(board, source)
    root = tmp_path / 'root.kicad_sch'; symbols = []; libraries = []; components = []; members = {}
    for index, fp in enumerate(board.GetFootprints()):
        ref = fp.GetReference(); symbol = str(uuid.uuid4()); lib = 'fixture:' + str(index)
        props = dict(Reference=ref, Value=fp.GetValue(), Footprint=fp.GetFPIDAsString(),
                     MPN=fp.GetField('MPN').GetText(), Manufacturer=fp.GetField('Manufacturer').GetText())
        pin_nodes = []
        for pin in fp.Pads():
            kind, name = ((op.MOS_PINS[pin.GetNumber()]['type'], op.MOS_PINS[pin.GetNumber()]['name'])
                          if fp == mos else ('passive', '~'))
            pin_nodes.append('(pin ' + kind + ' line (at ' + str(int(pin.GetNumber()) * 4) +
                ' 0 0) (length 1) (name ' + json.dumps(name) + ') (number ' + json.dumps(pin.GetNumber()) + '))')
            members.setdefault(pin.GetNetname(), []).append((ref, pin.GetNumber()))
        libraries.append('(symbol ' + json.dumps(lib) + ' (symbol "body_1_1" ' + ' '.join(pin_nodes) + '))')
        symbols.append('(symbol (lib_id ' + json.dumps(lib) + ') (at ' + str(index * 100) +
            ' 0 0) (unit 1) (uuid ' + json.dumps(symbol) + ') ' + ' '.join('(property ' +
            json.dumps(k) + ' ' + json.dumps(v) + ')' for k, v in props.items()) + ')')
        components.append('(comp (ref ' + json.dumps(ref) + ') (value ' + json.dumps(props['Value']) +
            ') (footprint ' + json.dumps(props['Footprint']) + ') (libsource (lib "fixture") (part ' +
            json.dumps('Q_NMOS_GSD' if fp == mos else 'R') + ')) ' + ' '.join('(property (name ' +
            json.dumps(k) + ') (value ' + json.dumps(v) + '))' for k, v in props.items()
            if k not in ('Reference', 'Value', 'Footprint')) + ' (tstamps ' + json.dumps(symbol) + '))')
    root.write_text(('(kicad_sch (version 20250114) (uuid ' + json.dumps(str(uuid.uuid4())) +
                    ') (lib_symbols ' + ' '.join(libraries) + ') ' + ' '.join(symbols) + ')').replace('\\u03a9', 'Ω'))
    tree = synth.parse_sexpr('(export (design (source ' + json.dumps(str(root)) +
        ') (date "2026-10-28T10:00:00Z") (tool "fixture")) (components ' + ' '.join(components) +
        ') (nets ' + ' '.join('(net (name ' + json.dumps(n) + ') ' + ' '.join('(node (ref ' +
        json.dumps(r) + ') (pin ' + json.dumps(p) + '))' for r, p in ends) + ')' for n, ends in members.items()) + '))')
    # KiCad S-expressions use literal UTF-8, not JSON's Unicode escape form.
    for comp in synth._kids(synth._first(tree, 'components'), 'comp'):
        value = synth._first(comp, 'value'); value[1] = value[1].replace('\\u03a9', 'Ω')
    for net in synth._kids(synth._first(tree, 'nets'), 'net'):
        for node in synth._kids(net, 'node'):
            info = (op.MOS_PINS[synth._val(node, 'pin', '')]
                    if synth._val(node, 'ref', '') == mos.GetReference() else dict(name='~', type='passive'))
            node.extend([['pinfunction', info['name']], ['pintype', info['type']]])
    exporter = tmp_path / 'exporter'; exporter.write_bytes(b'fixture exporter')
    calls = []
    def export(path, deadline):
        assert path == root and deadline > op.time.monotonic()
        calls.append(path)
        return tree, dict(exporter=str(exporter), exporter_sha256=op.force._hash(exporter),
            netlist_sha256=hashlib.sha256(repr(tree).encode()).hexdigest(), **semantic.metadata(tree))
    monkeypatch.setattr(canonical, '_export', export)
    current = dict(current_authority=dict(amps=.2123268, geometry_margin=1.2, margin_included=True,
                                          source='explicit synthetic aggregate test authority'),
        profile='synthetic-existing-profile', required_by_layer_nm={int(l): 800000 for l in board.GetEnabledLayers().CuStack()},
        release_authority=False, barrel_capacity_qualified=False)
    monkeypatch.setattr(cell, '_supply_current_widths', lambda b, n: copy.deepcopy(current) if n == '/opaque/rail' else None)
    poses = {bias.GetReference(): [bias.GetPosition().x / 1e6 + .5, bias.GetPosition().y / 1e6,
                                   (bias.GetOrientationDegrees() + 90) % 360]}
    return dict(board=board, source=source, root=root, tree=tree, mos=mos, bias=bias, peer=peer,
                poses=poses, current=current, exporter=exporter, calls=calls, group=group,
                tracks=dict(rail_a=rail_a, rail_b=rail_b, gate=gate, ground=ground, drain=drain))


def plan(data, **kwargs):
    return op.plan(data['board'], data['poses'], board_hint=str(data['root']), **kwargs)


def contract(data, **kwargs):
    return op.source_contract(data['board'], data['source'], resistor_uuid=op.force._uid(data['bias']),
                              board_hint=str(data['root']), **kwargs)


def projected(data, selected=None, *, groups=()):
    child = pcbnew.LoadBoard(str(data['source'])); fp = child.FindFootprintByReference(data['bias'].GetReference())
    selected = selected if selected is not None else plan(data, reference_group_uuids=groups)
    target = data['poses'][fp.GetReference()]
    if groups:
        import cec_source_reference_group_transport as maps
        proof = selected[fp.GetReference()]['source_reference_group_authorization']
        maps.transform_cardinal(child, proof, quarter_turns=int((target[2] - fp.GetOrientationDegrees()) % 360) // 90,
            delta_nm=tuple(round(v * 1e6) - tuple(fp.GetPosition())[i] for i, v in enumerate(target[:2])))
    else:
        fp.SetPosition(pcbnew.VECTOR2I(*(round(v * 1e6) for v in target[:2])))
        fp.SetOrientationDegrees(target[2])
    return child, dict(board_hint=str(data['root']), poses=copy.deepcopy(data['poses']),
                       selected_control_gate_biases=copy.deepcopy(selected), reference_group_uuids=list(groups))


@pytest.mark.parametrize('turn', [0, 90, 180, 270])
@pytest.mark.parametrize('back', [False, True])
def test_complete_source_gate_bias_role_on_actual_rotated_flipped_packages(tmp_path, monkeypatch, turn, back):
    data = fixture(tmp_path, monkeypatch, turn=turn, back=back)
    before = op.row._source_binding(data['board']); material = data['source'].read_bytes()
    selected = plan(data); item = selected[data['bias'].GetReference()]
    assert item['role'] == op.ROLE and item['control_pin'] == '1'
    assert item['source_proof']['manufacturer']['pins'] == op.MOS_PINS
    assert len(item['source_proof']['selected_components']) == 3
    assert len(item['source_gate_peer_pad_uuids']) == 3
    assert len(item['source_terminal_contacts'][item['supply_pad_uuid']]) == 2
    assert len(item['source_gate_components']['components']) == 1
    assert item['nominal_resistance_ohms'] == 10000
    assert all(item[k] is False for k in op._flags())
    assert len(data['calls']) == 1 and 'netlist_sha256' not in item['source_proof']['exporter']
    assert before == op.row._source_binding(data['board']) and material == data['source'].read_bytes()


@pytest.mark.parametrize('names,series', [(('other_Q', 'other_R', 'other_series'), False),
                                         (('stationary', 'moving', 'port_resistor'), True)])
def test_names_and_native_blank_pin_metadata_do_not_create_authority(tmp_path, monkeypatch, names, series):
    data = fixture(tmp_path, monkeypatch, names=names, series=series)
    item = contract(data)
    assert item['control_owner'] == names[0] and len(item['stationary_components']) == (2 if series else 1)
    assert not any(p.GetPinType() or p.GetPinFunction() for p in data['mos'].Pads())
    import cec_device_power_roles as roles
    assert roles.footprint_contract(data['mos']) is None  # NOT a low-power IC model.


def test_every_original_contact_is_a_fullwidth_obligation_not_a_cut_or_completed_route(tmp_path, monkeypatch):
    data = fixture(tmp_path, monkeypatch); child, proposal = projected(data)
    requests = op.requests(data['board'], child, proposal)
    rail = [r for r in requests.values() if r['role'] == 'gate_bias_supply']
    signal = [r for r in requests.values() if r['role'] == 'gate_bias_signal']
    assert len(rail) == len(signal) == 2
    assert {r['b']['native_uuids'][0] for r in rail} == {
        op.force._uid(data['tracks']['rail_a']), op.force._uid(data['tracks']['rail_b'])}
    assert all(r['width_nm'] == 800000 and not r['new_barrel_authority']
               and not r['class_only_supply_prefix_authority'] for r in rail)
    assert all(r['unchanged_full_rail_current_contract']['current_authority'] == data['current']['current_authority'] for r in rail)
    assert any(r['b'].get('pad_uuid') == op.force._uid(data['mos'].FindPadByNumber('1')) for r in signal)
    assert all(('source_pad_track_contact' in r) == bool(r['b'].get('native_uuids')) for r in requests.values())
    assert all(r['kind'] == 'source_boundary' and r['all_source_contacts_are_mandatory']
               and r['no_source_trace_retirement_authority'] for r in requests.values())
    assert data['tracks']['rail_a'].IsLocked() and len(data['calls']) == 2


@pytest.mark.parametrize('fault', ['manufacturer', 'MPN', 'package', 'missing_pad', 'duplicate_pad',
    'native_gate_name', 'native_source_name', 'native_drain_type', 'mos_DNP', 'resistor_DNP',
    'resistor_value', 'resistor_manufacturer', 'resistor_lock', 'pad_lock', 'hole', 'Ground_bias',
    'drain_bias', 'same_gate', 'second_bias', 'foreign_contact'])
def test_false_or_partial_native_source_never_becomes_gate_bias_scope(tmp_path, monkeypatch, fault):
    data = fixture(tmp_path, monkeypatch); b, q, r = data['board'], data['mos'], data['bias']
    if fault == 'manufacturer': q.SetField('Manufacturer', 'unreviewed supplier')
    elif fault == 'MPN': q.SetField('MPN', 'AO3401A')
    elif fault == 'package': q.SetFPID(pcbnew.LIB_ID('fake', 'SOT-23-6'))
    elif fault == 'missing_pad': q.Remove(q.FindPadByNumber('3'))
    elif fault == 'duplicate_pad': q.FindPadByNumber('3').SetNumber('2')
    elif fault == 'native_gate_name': q.FindPadByNumber('1').SetPinFunction('D')
    elif fault == 'native_source_name': q.FindPadByNumber('2').SetPinFunction('G')
    elif fault == 'native_drain_type': q.FindPadByNumber('3').SetPinType('power_in')
    elif fault == 'mos_DNP': q.SetDNP(True)
    elif fault == 'resistor_DNP': r.SetDNP(True)
    elif fault == 'resistor_value': r.SetValue('100kΩ')
    elif fault == 'resistor_manufacturer': r.SetField('Manufacturer', 'unreviewed supplier')
    elif fault == 'resistor_lock': r.SetLocked(True)
    elif fault == 'pad_lock': r.FindPadByNumber('1').SetLocked(True)
    elif fault == 'hole':
        r.FindPadByNumber('1').SetAttribute(pcbnew.PAD_ATTRIB_PTH)
        r.FindPadByNumber('1').SetDrillSize(pcbnew.VECTOR2I_MM(.2, .2))
    elif fault == 'Ground_bias': r.FindPadByNumber('1').SetNet(b.FindNet('GND'))
    elif fault == 'drain_bias': r.FindPadByNumber('1').SetNet(q.FindPadByNumber('3').GetNet())
    elif fault == 'same_gate': r.FindPadByNumber('1').SetNet(q.FindPadByNumber('1').GetNet())
    elif fault == 'second_bias': data['peer'].FindPadByNumber('2').SetNet(r.FindPadByNumber('1').GetNet())
    elif fault == 'foreign_contact': track(b, '/opaque/drain', (9.5, 10), (8, 10), width=.2)
    # Contradictory RAM net edits must already fail the exact saved-Source
    # binding; never serialize a deliberately shorted test as a new Source.
    if fault not in ('Ground_bias', 'drain_bias', 'same_gate', 'second_bias', 'foreign_contact'):
        field._save_field_snapshot(b, data['source'])
    with pytest.raises(ValueError): contract(data)


@pytest.mark.parametrize('fault', ['gate_name', 'source_name', 'drain_type', 'missing_pin', 'duplicate_pin',
    'resistor_symbol', 'resistor_pin_type', 'manufacturer', 'MPN', 'export_net', 'extra_gate_peer',
    'export_manufacturer', 'symbol_uuid', 'hierarchy', 'exporter_hash', 'semantic_hash'])
def test_fresh_complete_canonical_hierarchy_export_and_all_three_functions_are_required(tmp_path, monkeypatch, fault):
    data = fixture(tmp_path, monkeypatch); root, tree = data['root'], data['tree']
    if fault in ('gate_name', 'source_name', 'drain_type', 'missing_pin', 'duplicate_pin',
                 'resistor_pin_type', 'manufacturer', 'MPN'):
        old, new = {
            'gate_name': ('(name "G")', '(name "D")'),
            'source_name': ('(name "S")', '(name "G")'),
            'drain_type': ('(pin passive line (at 12 0 0) (length 1) (name "D")',
                           '(pin input line (at 12 0 0) (length 1) (name "D")'),
            'missing_pin': ('(number "3")', '(number "4")'),
            'duplicate_pin': ('(number "3")', '(number "2")'),
            'resistor_pin_type': ('(pin passive line (at 4 0 0) (length 1) (name "~")',
                                  '(pin input line (at 4 0 0) (length 1) (name "~")'),
            'manufacturer': ('Alpha & Omega Semiconductor', 'unreviewed supplier'),
            'MPN': ('(property "MPN" "AO3400A")', '(property "MPN" "AO3401A")')}[fault]
        assert old in root.read_text(); root.write_text(root.read_text().replace(old, new, 1))
    elif fault in ('resistor_symbol', 'export_manufacturer', 'symbol_uuid'):
        c = next(c for c in synth._kids(synth._first(tree, 'components'), 'comp')
                 if synth._val(c, 'ref', '') == data['bias'].GetReference())
        if fault == 'resistor_symbol': synth._first(synth._first(c, 'libsource'), 'part')[1] = 'C'
        elif fault == 'symbol_uuid': synth._first(c, 'tstamps')[1] = str(uuid.uuid4())
        else:
            p = next(p for p in synth._kids(c, 'property') if synth._val(p, 'name', '') == 'Manufacturer')
            synth._first(p, 'value')[1] = 'unknown'
    elif fault in ('export_net', 'extra_gate_peer'):
        net = next(n for n in synth._kids(synth._first(tree, 'nets'), 'net') if synth._val(n, 'name', '') == '/opaque/gate')
        if fault == 'export_net': synth._first(net, 'name')[1] = '/forged'
        else: net.append(['node', ['ref', 'unselected'], ['pin', '1']])
    elif fault == 'hierarchy': root.unlink()
    else:
        original = canonical._export
        def forged(*args):
            tree, proof = original(*args)
            proof['exporter_sha256' if fault == 'exporter_hash' else 'netlist_semantic_sha256'] = '0' * 64
            return tree, proof
        monkeypatch.setattr(canonical, '_export', forged)
    with pytest.raises((ValueError, FileNotFoundError)): contract(data)


@pytest.mark.parametrize('fault', ['missing', 'partial_layers', 'zero_width', 'negative_current', 'missing_margin',
    'margin_bool', 'included_missing', 'profile_missing'])
def test_unknown_or_conflicting_aggregate_contract_has_no_nonload_exception(tmp_path, monkeypatch, fault):
    data = fixture(tmp_path, monkeypatch); current = data['current']
    if fault == 'missing': monkeypatch.setattr(cell, '_supply_current_widths', lambda *a: None)
    elif fault == 'partial_layers': current['required_by_layer_nm'].pop(next(iter(current['required_by_layer_nm'])))
    elif fault == 'zero_width': current['required_by_layer_nm'] = {k: 0 for k in current['required_by_layer_nm']}
    elif fault == 'negative_current': current['current_authority']['amps'] = -1
    elif fault == 'missing_margin': current['current_authority'].pop('geometry_margin')
    elif fault == 'margin_bool': current['current_authority']['geometry_margin'] = True
    elif fault == 'included_missing': current['current_authority'].pop('margin_included')
    elif fault == 'profile_missing': current.pop('profile')
    with pytest.raises(ValueError, match='aggregate_supply'): contract(data)


@pytest.mark.parametrize('fault', ['MOS_pose', 'MOS_field', 'MOS_pad', 'MOS_net', 'MOS_lock', 'series_pose',
    'DS_track_cut', 'DS_track_width', 'DS_track_lock', 'resistor_pose', 'resistor_pad', 'resistor_field',
    'resistor_face', 'resistor_DNP', 'resistor_group', 'forged_contact', 'forged_current', 'forged_role'])
def test_projected_request_context_cannot_move_MOS_or_forge_source_obligations(tmp_path, monkeypatch, fault):
    data = fixture(tmp_path, monkeypatch); child, proposal = projected(data)
    q = child.FindFootprintByReference(data['mos'].GetReference())
    r = child.FindFootprintByReference(data['bias'].GetReference())
    if fault == 'MOS_pose': q.Move(pcbnew.VECTOR2I(1, 0))
    elif fault == 'MOS_field': q.SetField('MPN', 'wrong')
    elif fault == 'MOS_pad': q.FindPadByNumber('3').SetSize(pcbnew.VECTOR2I_MM(1, 1))
    elif fault == 'MOS_net': q.FindPadByNumber('2').SetNet(q.FindPadByNumber('3').GetNet())
    elif fault == 'MOS_lock': q.SetLocked(not q.IsLocked())
    elif fault == 'series_pose': child.FindFootprintByReference(data['peer'].GetReference()).Move(pcbnew.VECTOR2I(1, 0))
    elif fault.startswith('DS_track'):
        t = next(t for t in child.GetTracks() if op.force._uid(t) == op.force._uid(data['tracks']['ground']))
        if fault == 'DS_track_cut': discard_items(child, [t])
        elif fault == 'DS_track_width': t.SetWidth(t.GetWidth() + 1)
        else: t.SetLocked(not t.IsLocked())
    elif fault == 'resistor_pose': r.Move(pcbnew.VECTOR2I(1, 0))
    elif fault == 'resistor_pad': r.FindPadByNumber('1').SetSize(pcbnew.VECTOR2I_MM(1, 1))
    elif fault == 'resistor_field': r.SetField('MPN', 'wrong')
    elif fault == 'resistor_face': r.Flip(r.GetPosition(), False)
    elif fault == 'resistor_DNP': r.SetDNP(True)
    elif fault == 'resistor_group': g = pcbnew.PCB_GROUP(child); child.Add(g); g.AddItem(r)
    else:
        item = proposal['selected_control_gate_biases'][r.GetReference()]
        if fault == 'forged_contact': item['source_terminal_contacts'][item['supply_pad_uuid']].pop()
        elif fault == 'forged_current': item['unchanged_full_rail_current_contract']['current_authority']['amps'] = .001
        else: item['role'] = 'low_power_device'
    with pytest.raises(ValueError): op.requests(data['board'], child, proposal)


@pytest.mark.parametrize('fault', ['MOS', 'series'])
def test_caller_pose_cannot_move_switch_or_series_boundary(tmp_path, monkeypatch, fault):
    data = fixture(tmp_path, monkeypatch); fp = data['mos' if fault == 'MOS' else 'peer']
    data['poses'][fp.GetReference()] = [1, 2, 0]
    with pytest.raises(ValueError, match='stationary'): plan(data)


def test_declared_old_copper_cuts_are_not_used_as_skiplist(tmp_path, monkeypatch):
    data = fixture(tmp_path, monkeypatch); child, proposal = projected(data)
    ids = [op.force._uid(v) for k, v in data['tracks'].items() if k.startswith('rail')]
    discard_items(child, [t for t in child.GetTracks() if op.force._uid(t) in ids])
    proposal['retired_track_uuids'] = ids
    result = op.requests(data['board'], child, proposal)
    assert {r['b']['native_uuids'][0] for r in result.values() if r['role'] == 'gate_bias_supply'} == set(ids)
    assert all(r['all_source_contacts_are_mandatory'] for r in result.values())


def test_json_roundtrip_and_generated_clock_do_not_change_source_semantics(tmp_path, monkeypatch):
    data = fixture(tmp_path, monkeypatch); selected = json.loads(json.dumps(plan(data)))
    synth._first(synth._first(data['tree'], 'design'), 'date')[1] = '2026-10-28T11:00:00Z'
    assert plan(data) == selected
    child, proposal = projected(data, selected)
    assert op.requests(data['board'], child, proposal)


@pytest.mark.parametrize('fault', ['semantic_tool', 'source_file', 'code_epoch', 'companion', 'exporter'])
def test_live_source_drift_never_rebinds_old_role(tmp_path, monkeypatch, fault):
    data = fixture(tmp_path, monkeypatch); child, proposal = projected(data)
    if fault == 'semantic_tool': synth._first(synth._first(data['tree'], 'design'), 'tool')[1] = 'changed'
    elif fault == 'source_file': data['root'].write_text(data['root'].read_text() + '\n')
    elif fault == 'code_epoch': monkeypatch.setattr(op.force, '_code_identity', lambda: {'unexpected.py': '0' * 64})
    elif fault == 'companion': data['source'].with_suffix('.new').write_text('new companion')
    else: data['exporter'].write_bytes(b'changed tool binary')
    with pytest.raises(ValueError, match='fresh_exact'): op.requests(data['board'], child, proposal)


def test_final_source_recheck_catches_change_after_export(tmp_path, monkeypatch):
    data = fixture(tmp_path, monkeypatch); original = op._gate_components
    def changing(*args):
        value = original(*args); data['root'].write_text(data['root'].read_text() + '\n'); return value
    monkeypatch.setattr(op, '_gate_components', changing)
    with pytest.raises(ValueError, match='canonical_or_code_changed'): contract(data)


def test_expired_native_work_is_not_partial_positive(tmp_path, monkeypatch):
    data = fixture(tmp_path, monkeypatch); now = op.time.monotonic(); original = op._gate_components
    def late(*args):
        value = original(*args); monkeypatch.setattr(op.time, 'monotonic', lambda: now + 11); return value
    monkeypatch.setattr(op, '_gate_components', late)
    with pytest.raises(ValueError, match='deadline'): contract(data)


@pytest.mark.parametrize('pin,key,value', [('1', 'pinfunction', 'D'), ('2', 'pinfunction', 'G'),
    ('3', 'pinfunction', ''), ('1', 'pintype', 'passive'), ('2', 'pintype', 'input'), ('3', 'pintype', '')])
def test_all_exported_G_S_D_functions_and_types_must_match(tmp_path, monkeypatch, pin, key, value):
    data = fixture(tmp_path, monkeypatch)
    node = next(node for net in synth._kids(synth._first(data['tree'], 'nets'), 'net')
                for node in synth._kids(net, 'node')
                if synth._val(node, 'ref', '') == data['mos'].GetReference()
                and synth._val(node, 'pin', '') == pin)
    synth._first(node, key)[1] = value
    with pytest.raises(ValueError, match='export_pin_or_net'): contract(data)


def _export_node(data, fp, pin):
    return next(node for net in synth._kids(synth._first(data['tree'], 'nets'), 'net')
                for node in synth._kids(net, 'node')
                if synth._val(node, 'ref', '') == fp.GetReference()
                and synth._val(node, 'pin', '') == pin)


RC_SERIES = ('100Ω', 'RC0402JR-07100RL', 'YAGEO', 'arbitrary_library:R_0402_1005Metric')


@pytest.mark.parametrize('turn', [0, 90, 180, 270])
@pytest.mark.parametrize('back', [False, True])
def test_stationary_RC_series_peer_is_Source_identity_not_a_monitor_current_model(tmp_path, monkeypatch, turn, back):
    import cec_resistive_monitor_branch as monitor
    data = fixture(tmp_path, monkeypatch, turn=turn, back=back, series_part=RC_SERIES,
                   names=('fixed_Q', 'moving_bias', 'fixed_peer'))
    assert monitor.resistor_contract(data['peer']) is None
    for pin in ('1', '2'):
        synth._first(_export_node(data, data['peer'], pin), 'pinfunction')[1] = '~_' + pin
    before = op._footprint(data['board'], data['peer'])
    selected = plan(data); child, proposal = projected(data, selected)
    item = selected[data['bias'].GetReference()]
    identity = item['source_proof']['selected_components'][data['peer'].GetReference()]
    assert identity['fields']['MPN'] == 'RC0402JR-07100RL' and identity['fields']['Manufacturer'] == 'YAGEO'
    assert identity['source_only'] and identity['identity_only'] and identity['source_declared_resistance_ohms'] == 100
    assert not any(identity[k] for k in ('current_authority', 'resistor_current_assumed',
        'manufacturer_resistance_model_applied', 'power_or_thermal_qualified', 'voltage_qualified',
        'resistance_or_power_qualification', 'source_trace_retirement_authority',
        'placement_authority', 'routing_admitted', 'release_authority'))
    assert set(item['stationary_series_contacts']) == {op.force._uid(p) for p in data['peer'].Pads()}
    assert op.requests(data['board'], child, proposal)
    assert op._footprint(child, child.FindFootprintByReference(data['peer'].GetReference())) == before


def _peer_source_symbol_replace(data, old, new):
    sf = canonical.sch.SchFile(str(data['root']))
    lib_id = next(s['lib_id'] for s in sf.symbols if s['ref'] == data['peer'].GetReference())
    libraries = next(block for tag, block in sf.children if tag == 'lib_symbols')
    block = next(block for tag, block in canonical.sch.iter_children(libraries)
                 if tag == 'symbol' and canonical.sch.first_string(block) == lib_id)
    assert old in block
    data['root'].write_text(data['root'].read_text().replace(block, block.replace(old, new, 1), 1))


@pytest.mark.parametrize('fault', ['native_type', 'native_name', 'native_value', 'native_package',
    'native_MPN', 'native_manufacturer', 'DNP', 'hole', 'missing_pad', 'duplicate_pad',
    'canonical_type', 'canonical_symbol', 'export_value', 'export_MPN', 'export_manufacturer', 'export_net'])
def test_stationary_peer_requires_complete_exact_native_and_canonical_identity(tmp_path, monkeypatch, fault):
    data = fixture(tmp_path, monkeypatch, series_part=RC_SERIES); fp = data['peer']; b = data['board']
    if fault == 'native_type': fp.FindPadByNumber('1').SetPinType('input')
    elif fault == 'native_name': fp.FindPadByNumber('1').SetPinFunction('gate')
    elif fault == 'native_value': fp.SetValue('101Ω')
    elif fault == 'native_package': fp.SetFPID(pcbnew.LIB_ID('arbitrary_library', 'R_0603_1608Metric'))
    elif fault == 'native_MPN': fp.SetField('MPN', 'other')
    elif fault == 'native_manufacturer': fp.SetField('Manufacturer', 'other')
    elif fault == 'DNP': fp.SetDNP(True)
    elif fault == 'hole':
        p = fp.FindPadByNumber('1'); p.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
        p.SetDrillSize(pcbnew.VECTOR2I_MM(.2, .2))
    elif fault == 'missing_pad': fp.Remove(fp.FindPadByNumber('2'))
    elif fault == 'duplicate_pad': fp.FindPadByNumber('2').SetNumber('1')
    elif fault == 'canonical_type':
        _peer_source_symbol_replace(data, '(pin passive', '(pin input')
    elif fault == 'export_net':
        node = _export_node(data, fp, '2'); synth._first(node, 'pin')[1] = '3'
    else:
        comp = next(c for c in synth._kids(synth._first(data['tree'], 'components'), 'comp')
                    if synth._val(c, 'ref', '') == fp.GetReference())
        if fault == 'canonical_symbol': synth._first(synth._first(comp, 'libsource'), 'part')[1] = 'C'
        elif fault == 'export_value': synth._first(comp, 'value')[1] = '101Ω'
        else:
            key = 'MPN' if fault == 'export_MPN' else 'Manufacturer'
            prop = next(p for p in synth._kids(comp, 'property') if synth._val(p, 'name', '') == key)
            synth._first(prop, 'value')[1] = 'other'
    if fault.startswith('native_') or fault in ('DNP', 'hole', 'missing_pad', 'duplicate_pad'):
        field._save_field_snapshot(b, data['source'])
    with pytest.raises(ValueError): contract(data)


@pytest.mark.parametrize('value', ['0Ω', '-100Ω', 'NaN', '100X', '1e1000'])
def test_stationary_passive_requires_finite_positive_declared_value_even_with_full_parity(tmp_path, monkeypatch, value):
    data = fixture(tmp_path, monkeypatch, series_part=(value, *RC_SERIES[1:]))
    with pytest.raises(ValueError, match='positive_Source_resistance'): contract(data)


def test_stationary_passive_package_tier_is_not_arbitrary_two_land_canonical_part(tmp_path, monkeypatch):
    data = fixture(tmp_path, monkeypatch, series_part=(*RC_SERIES[:3], 'arbitrary_library:C_0402_1005Metric'))
    with pytest.raises(ValueError, match='series_two_land_resistor_package'): contract(data)


@pytest.mark.parametrize('fault', ['pose', 'DNP', 'field', 'group', 'copper_cut', 'copper_width', 'copper_lock', 'new_contact'])
def test_real_RC_stationary_peer_and_both_local_contact_sets_cannot_change(tmp_path, monkeypatch, fault):
    data = fixture(tmp_path, monkeypatch, series_part=RC_SERIES); child, proposal = projected(data)
    peer = child.FindFootprintByReference(data['peer'].GetReference())
    if fault == 'pose': peer.Move(pcbnew.VECTOR2I(1, 0))
    elif fault == 'DNP': peer.SetDNP(True)
    elif fault == 'field': peer.SetField('MPN', 'other')
    elif fault == 'group': g = pcbnew.PCB_GROUP(child); child.Add(g); g.AddItem(peer)
    elif fault == 'new_contact': track(child, '/opaque/command', (14.5, 7), (14.5, 6), width=.2)
    else:
        t = next(t for t in child.GetTracks() if t.GetNetname() == '/opaque/command')
        if fault == 'copper_cut': discard_items(child, [t])
        elif fault == 'copper_width': t.SetWidth(t.GetWidth() + 1)
        else: t.SetLocked(not t.IsLocked())
    with pytest.raises(ValueError, match='stationary'): op.requests(data['board'], child, proposal)


def test_stationary_identity_seam_does_not_make_the_RC_peer_a_moving_bias(tmp_path, monkeypatch):
    data = fixture(tmp_path, monkeypatch, series_part=RC_SERIES)
    with pytest.raises(ValueError, match='positive_selected_gate_bias_resistor_required'):
        op._resistor(data['peer'])
    data['poses'][data['peer'].GetReference()] = [1, 2, 0]
    with pytest.raises(ValueError): plan(data)


@pytest.mark.parametrize('part', ['R', 'R_Small'])
@pytest.mark.parametrize('turn,back', [(0, False), (90, False), (180, True), (270, True)])
def test_exact_anonymous_passive_export_number_suffix_replays_both_pins(tmp_path, monkeypatch, part, turn, back):
    data = fixture(tmp_path, monkeypatch, turn=turn, back=back,
                   names=('fixed_switch', 'rail_bias', 'fixed_signal_resistor'))
    for fp in (data['bias'], data['peer']):
        comp = next(c for c in synth._kids(synth._first(data['tree'], 'components'), 'comp')
                    if synth._val(c, 'ref', '') == fp.GetReference())
        synth._first(synth._first(comp, 'libsource'), 'part')[1] = part
        for pin in ('1', '2'):
            synth._first(_export_node(data, fp, pin), 'pinfunction')[1] = '~_' + pin
    selected = plan(data)
    child, proposal = projected(data, selected)
    assert op.requests(data['board'], child, proposal)
    assert selected[data['bias'].GetReference()]['source_proof']['manufacturer']['pins'] == op.MOS_PINS
    assert all(selected[data['bias'].GetReference()][key] is False for key in op._flags())


@pytest.mark.parametrize('fault', ['wrong_number', 'leading_zero', 'double_suffix', 'missing_number',
    'foreign_suffix', 'space', 'named_pin', 'native_name', 'native_type', 'export_type',
    'embedded_type', 'other_symbol'])
def test_anonymous_passive_export_suffix_cannot_hide_identity_mismatch(tmp_path, monkeypatch, fault):
    data = fixture(tmp_path, monkeypatch); fp = data['bias']
    node = _export_node(data, fp, '1'); synth._first(node, 'pinfunction')[1] = '~_1'
    if fault in ('wrong_number', 'leading_zero', 'double_suffix', 'missing_number', 'foreign_suffix', 'space'):
        synth._first(node, 'pinfunction')[1] = dict(wrong_number='~_2', leading_zero='~_01',
            double_suffix='~_1_1', missing_number='~_', foreign_suffix='~_x', space='~_1 ')[fault]
    elif fault == 'named_pin':
        data['root'].write_text(data['root'].read_text().replace('(name "~")', '(name "named")'))
    elif fault in ('native_name', 'native_type'):
        pad = fp.FindPadByNumber('1')
        if fault == 'native_name': pad.SetPinFunction('other')
        else: pad.SetPinType('input')
        field._save_field_snapshot(data['board'], data['source'])
    elif fault == 'export_type': synth._first(node, 'pintype')[1] = 'input'
    elif fault == 'embedded_type':
        data['root'].write_text(data['root'].read_text().replace(
            '(pin passive line (at 4 0 0) (length 1) (name "~")',
            '(pin input line (at 4 0 0) (length 1) (name "~")'))
    else:
        comp = next(c for c in synth._kids(synth._first(data['tree'], 'components'), 'comp')
                    if synth._val(c, 'ref', '') == fp.GetReference())
        synth._first(synth._first(comp, 'libsource'), 'part')[1] = 'C'
    with pytest.raises(ValueError, match='export_pin_or_net|canonical_passive_resistor'):
        contract(data)


@pytest.mark.parametrize('turn,back', [(0, False), (90, False), (180, True), (270, True)])
@pytest.mark.parametrize('mixed', [False, True])
def test_exact_named_MOS_export_number_suffix_replays_complete_model(tmp_path, monkeypatch, turn, back, mixed):
    data = fixture(tmp_path, monkeypatch, turn=turn, back=back,
                   names=('fixed_gate_device', 'rail_bias', 'fixed_signal_resistor'))
    for fp in (data['mos'], data['bias'], data['peer']):
        for pad in fp.Pads():
            pin = pad.GetNumber(); node = _export_node(data, fp, pin)
            if not mixed or pin == '1':
                synth._first(node, 'pinfunction')[1] += '_' + pin
    selected = plan(data); child, proposal = projected(data, selected)
    assert op.requests(data['board'], child, proposal)
    item = selected[data['bias'].GetReference()]
    assert item['source_proof']['manufacturer']['pins'] == op.MOS_PINS
    mos_identity = next(r for r in item['source_proof']['selected_components'].values()
                        if r['reference'] == data['mos'].GetReference())
    assert {pin: {k: r[k] for k in ('name', 'type')} for pin, r in mos_identity['pins'].items()} == op.MOS_PINS
    assert all(item[key] is False for key in op._flags())


@pytest.mark.parametrize('pin', ['1', '2', '3'])
@pytest.mark.parametrize('fault', ['wrong_function', 'wrong_number', 'leading_zero', 'double_suffix',
                                 'anonymous', 'space'])
def test_named_MOS_export_suffix_requires_exact_function_and_number(tmp_path, monkeypatch, pin, fault):
    data = fixture(tmp_path, monkeypatch)
    node = _export_node(data, data['mos'], pin)
    name = op.MOS_PINS[pin]['name']; other = str(int(pin) % 3 + 1)
    bad = dict(wrong_function=op.MOS_PINS[other]['name'] + '_' + pin,
        wrong_number=name + '_' + other, leading_zero=name + '_0' + pin,
        double_suffix=name + '_' + pin + '_' + pin, anonymous='~_' + pin,
        space=name + '_' + pin + ' ')[fault]
    synth._first(node, 'pinfunction')[1] = bad
    with pytest.raises(ValueError, match='export_pin_or_net') as error:
        contract(data)
    detail = json.loads(str(error.value).split(':', 1)[1])
    assert detail['reference'] == data['mos'].GetReference() and detail['pin'] == pin
    assert detail['embedded'] == op.MOS_PINS[pin]
    assert detail['exported']['name'] == bad


@pytest.mark.parametrize('pin', ['1', '2', '3'])
@pytest.mark.parametrize('fault', ['native_name', 'native_type', 'export_type'])
def test_export_suffix_cannot_override_contradictory_native_or_electrical_type(tmp_path, monkeypatch, pin, fault):
    data = fixture(tmp_path, monkeypatch); fp = data['mos']; pad = fp.FindPadByNumber(pin)
    node = _export_node(data, fp, pin)
    synth._first(node, 'pinfunction')[1] = op.MOS_PINS[pin]['name'] + '_' + pin
    wrong_type = 'passive' if pin == '1' else 'input'
    if fault == 'export_type': synth._first(node, 'pintype')[1] = wrong_type
    else:
        if fault == 'native_name': pad.SetPinFunction(op.MOS_PINS[pin]['name'] + '_' + pin)
        else: pad.SetPinType(wrong_type)
        field._save_field_snapshot(data['board'], data['source'])
    with pytest.raises(ValueError, match='export_pin_or_net|native_identity'):
        contract(data)


def zone(board, net, bounds):
    from test_native_partition_pair import rect, setfill
    z = pcbnew.ZONE(board); z.SetNet(board.FindNet(net)); z.SetLayer(pcbnew.F_Cu)
    ring = rect(*(round(v * 1e6) for v in bounds))
    z.Outline().NewOutline()
    for x, y in ring: z.Outline().Append(pcbnew.VECTOR2I(x, y))
    board.Add(z); setfill(z, [[ring]])
    return z


@pytest.mark.parametrize('kind', ['barrel', 'filled_zone', 'other_pad'])
def test_actual_moving_pad_barrel_fill_or_shared_land_contact_is_not_omitted(tmp_path, monkeypatch, kind):
    data = fixture(tmp_path, monkeypatch); b = data['board']; p = data['bias'].FindPadByNumber('1')
    if kind == 'barrel':
        via = pcbnew.PCB_VIA(b); via.SetPosition(p.GetPosition()); via.SetNet(p.GetNet())
        via.SetWidth(900000); via.SetDrill(500000); via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); b.Add(via)
    elif kind == 'filled_zone': zone(b, p.GetNetname(), (9.2, 9.6, 9.8, 10.4))
    else:
        # Same logical pad number would otherwise be collapsed by a netlist
        # set; the native two-land package/actual contact cannot borrow it.
        fp = pcbnew.FOOTPRINT(b); fp.SetReference('external_land'); b.Add(fp)
        new = pcbnew.PAD(fp); new.SetNumber('1'); new.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        new.SetLayerSet(pcbnew.PAD.SMDMask()); new.SetSize(pcbnew.VECTOR2I_MM(.2, .2))
        new.SetNet(p.GetNet()); new.SetPosition(p.GetPosition()); fp.Add(new)
        net = next(n for n in synth._kids(synth._first(data['tree'], 'nets'), 'net')
                   if synth._val(n, 'name', '') == p.GetNetname())
        net.append(['node', ['ref', 'external_land'], ['pin', '1'], ['pintype', 'passive']])
    field._save_field_snapshot(b, data['source'])
    with pytest.raises(ValueError, match='trace_only'): contract(data)


@pytest.mark.parametrize('changed', [False, True])
def test_actual_stationary_source_Ground_fill_aperture_is_replayed(tmp_path, monkeypatch, changed):
    from test_native_partition_pair import rect, setfill
    data = fixture(tmp_path, monkeypatch); z = zone(data['board'], 'GND', (16.5, 11.5, 17.5, 12.5))
    field._save_field_snapshot(data['board'], data['source'])
    child, proposal = projected(data)
    item = proposal['selected_control_gate_biases'][data['bias'].GetReference()]
    ground_uid = op.force._uid(data['mos'].FindPadByNumber('2'))
    assert any(r['kind'] == 'ZONE' for r in item['stationary_MOS_drain_source_contacts'][ground_uid])
    if changed:
        actual = next(z for z in child.Zones())
        setfill(actual, [[rect(16500000, 11500000, 16900000, 12500000)]])
        with pytest.raises(ValueError, match='drain_source_material'): op.requests(data['board'], child, proposal)
    else:
        assert op.requests(data['board'], child, proposal)


@pytest.mark.parametrize('kind', ['canonical', 'code', 'projected'])
def test_request_generation_has_its_own_final_live_guard(tmp_path, monkeypatch, kind):
    data = fixture(tmp_path, monkeypatch); child, proposal = projected(data); original = op._rail; calls = []
    def changed(*args):
        answer = original(*args); calls.append(1)
        if len(calls) == 2:  # After fresh plan, during actual request generation.
            if kind == 'canonical': data['root'].write_text(data['root'].read_text() + '\n')
            elif kind == 'code': monkeypatch.setattr(op.force, '_code_identity', lambda: {'late': '0' * 64})
            else: child.FindFootprintByReference(data['bias'].GetReference()).Move(pcbnew.VECTOR2I(1, 0))
        return answer
    monkeypatch.setattr(op, '_rail', changed)
    with pytest.raises(ValueError, match='requests_live'): op.requests(data['board'], child, proposal)


def test_specialized_gate_class_does_not_become_ordinary_from_MOS_name(tmp_path, monkeypatch):
    data = fixture(tmp_path, monkeypatch); project = data['source'].with_suffix('.kicad_pro')
    spec = json.loads(project.read_text()); spec['net_settings']['classes'].append(dict(
        name='Sense', track_width=.25, clearance=.2, via_diameter=.6, via_drill=.3))
    spec['net_settings']['netclass_patterns'].append(dict(netclass='Sense', pattern='/opaque/gate'))
    project.write_text(json.dumps(spec))
    with pytest.raises(ValueError, match='positive_ordinary_gate'): contract(data)


@pytest.mark.parametrize('timeout', [True, 0, -1, 10.01, float('nan')])
def test_strict_ten_second_native_lease(tmp_path, monkeypatch, timeout):
    data = fixture(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match='lease'): plan(data, timeout_s=timeout)


def test_unrelated_pose_fast_path_never_exports_or_invokes_current(tmp_path, monkeypatch):
    data = fixture(tmp_path, monkeypatch)
    def forbidden(*args, **kwargs): raise AssertionError('unrelated cell must not compile this role')
    monkeypatch.setattr(canonical, '_export', forbidden); monkeypatch.setattr(cell, '_supply_current_widths', forbidden)
    assert op.plan(data['board'], {data['mos'].GetReference(): [1, 2, 0]}, board_hint=str(data['root'])) == {}


@pytest.mark.parametrize('fault', ['none', 'copper', 'pad', 'nested', 'no_optin', 'child_lock'])
def test_exact_closed_reference_map_is_not_copper_or_unlock_permission(tmp_path, monkeypatch, fault):
    data = fixture(tmp_path, monkeypatch, annotation=True); group = data['group']; gid = op.force._uid(group)
    if fault == 'copper': group.AddItem(data['tracks']['rail_a'])
    elif fault == 'pad': group.AddItem(data['bias'].FindPadByNumber('1'))
    elif fault == 'nested': outer = pcbnew.PCB_GROUP(data['board']); data['board'].Add(outer); outer.AddItem(group)
    if fault in ('copper', 'pad', 'nested'):
        field._save_field_snapshot(data['board'], data['source'])
    if fault != 'none' and fault != 'child_lock':
        with pytest.raises(ValueError): plan(data, reference_group_uuids=() if fault == 'no_optin' else [gid])
        return
    selected = plan(data, reference_group_uuids=[gid]); child, proposal = projected(data, selected, groups=[gid])
    if fault == 'child_lock':
        next(iter(child.Groups())).SetLocked(False)
        with pytest.raises(ValueError, match='group_members'): op.requests(data['board'], child, proposal)
    else:
        assert op.requests(data['board'], child, proposal)
        assert next(iter(child.Groups())).IsLocked() and not child.FindFootprintByReference(data['bias'].GetReference()).IsLocked()
