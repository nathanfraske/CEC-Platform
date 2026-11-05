"""Canonical shared-bus bias is a passive, never an IC/current exception."""
import copy
import hashlib
import json
import re
from pathlib import Path
import sys
import uuid

import pcbnew
import pytest
import cec_field_coupling as field
import cec_source_signal_bias_placement as op


def fixture(tmp_path, monkeypatch, turn=0, back=False):
    board = pcbnew.BOARD(); board.SetCopperLayerCount(6)
    board.SetFileName(str(tmp_path/'board.kicad_pcb'))
    nets = {}
    def net(name):
        if name not in nets:
            item = pcbnew.NETINFO_ITEM(board, name); board.Add(item); nets[name] = item
        return nets[name]
    def footprint(ref, value, mpn, library, names):
        fp = pcbnew.FOOTPRINT(board); fp.SetReference(ref); fp.SetValue(value); fp.SetField('MPN', mpn)
        fp.SetFPID(pcbnew.LIB_ID(*library.split(':'))); board.Add(fp)
        fp.SetPosition(pcbnew.VECTOR2I_MM(10+len(list(board.GetFootprints()))*8, 12))
        for index, name in enumerate(names, 1):
            pad = pcbnew.PAD(fp); pad.SetNumber(str(index)); pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            pad.SetShape(pcbnew.PAD_SHAPE_RECT); pad.SetSize(pcbnew.VECTOR2I_MM(.3, .6))
            pad.SetLayerSet(pcbnew.PAD.SMDMask()); pad.SetPosition(fp.GetPosition()+pcbnew.VECTOR2I(index*700000, 0))
            pad.SetNet(net(name)); fp.Add(pad)
        return fp
    def names(ref):
        return [ref+'-a0', ref+'-a1', ref+'-alert', ref+'-sda', 'ordinary-bus',
            'logic-rail', 'GND', ref+'-in-p', ref+'-in-n', ref+'-vbus']
    first = footprint('Ua', 'INA238', 'INA238AIDGSR',
        'pkg:VSSOP-10_3x3mm_P0.5mm', names('Ua'))
    second = footprint('Ub', 'INA238', 'INA238AIDGSR',
        'pkg:VSSOP-10_3x3mm_P0.5mm', names('Ub'))
    resistor = footprint('Rb', '2.2kΩ', '0402WGF2201TCE',
        'pkg:R_0402_1005Metric', ['ordinary-bus', 'logic-rail'])
    libraries = []; symbols = []; components = []; members = {}
    for index, fp in enumerate((first, second, resistor)):
        ref = fp.GetReference(); sid = str(uuid.uuid4()); lib = 'fixture:'+('R' if fp == resistor else ref)
        logical = []
        for pin_index, pad in enumerate(fp.Pads()):
            number = pad.GetNumber()
            kind = 'passive' if fp == resistor else 'power_in' if number in ('6', '7') else 'input'
            name = 'SCL' if fp != resistor and number == '5' else 'P'+number
            logical.append('(pin '+kind+' line (at '+str(pin_index)+' 0 0) (length 1) '
                '(name "'+name+'") (number "'+number+'"))')
            members.setdefault(pad.GetNetname(), []).append((ref, number))
        libraries.append('(symbol "'+lib+'" (symbol "unit_1_1" '+' '.join(logical)+'))')
        props = [('Reference', ref), ('Value', fp.GetValue()), ('Footprint', fp.GetFPIDAsString()), ('MPN', fp.GetField('MPN').GetText())]
        symbols.append('(symbol (lib_id "'+lib+'") (at '+str(index*100)+' 10 0) (unit 1) (uuid "'+sid+'") '
            +' '.join('(property "'+k+'" "'+v+'")' for k, v in props)+')')
        components.append('(comp (ref "'+ref+'") (value "'+fp.GetValue()+'") (footprint "'+fp.GetFPIDAsString()+'") '
            '(property (name "MPN") (value "'+fp.GetField('MPN').GetText()+'")) '
            '(libsource (lib "fixture") (part "'+('R_Small' if fp == resistor else 'INA238')+'")) (tstamps "'+sid+'"))')
    root = tmp_path/'source.kicad_sch'
    root.write_text('(kicad_sch (version 20250114) (uuid "'+str(uuid.uuid4())+'") '
        '(lib_symbols '+' '.join(libraries)+') '+' '.join(symbols)+')')
    tree = op.synth.parse_sexpr('(export (components '+' '.join(components)+') (nets '
        +' '.join('(net (name "'+name+'") '+' '.join('(node (ref "'+ref+'") (pin "'+pin+'"))'
            for ref, pin in nodes)+')' for name, nodes in members.items())+'))')
    def export(path, deadline):
        return tree, dict(exporter=sys.executable, exporter_sha256=op.force._hash(Path(sys.executable)),
            netlist_sha256=hashlib.sha256(repr(tree).encode()).hexdigest(), **op.semantic.metadata(tree))
    monkeypatch.setattr(op.canonical, '_export', export)
    monkeypatch.setattr(op.ordinary, 'eligible_nets', lambda *a, **k: {'ordinary-bus'})
    for fp in board.GetFootprints():
        fp.SetOrientationDegrees(turn)
        if back:
            fp.Flip(pcbnew.VECTOR2I(0, 0), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    field._save_field_snapshot(board, Path(board.GetFileName()))
    poses = {resistor.GetReference(): [resistor.GetPosition().x/1e6+.5,
        resistor.GetPosition().y/1e6, (resistor.GetOrientationDegrees()+90) % 360]}
    return board, first, second, resistor, root, tree, poses


@pytest.mark.parametrize('turn', [0, 90, 180, 270])
@pytest.mark.parametrize('back', [False, True])
def test_shared_peers_and_every_face_are_preserved_without_unique_owner_assumption(tmp_path, monkeypatch, turn, back):
    board, first, second, resistor, root, tree, poses = fixture(tmp_path, monkeypatch, turn, back)
    before = op.row._source_binding(board); saved = Path(board.GetFileName()).read_bytes()
    result = op.plan(board, poses, board_hint=str(root)); item = result[resistor.GetReference()]
    assert item['role'] == 'source_canonical_ordinary_signal_supply_resistor'
    assert {v['owner'] for v in item['peers']} == {first.GetReference(), second.GetReference()}
    assert item['nominal_resistance_ohms'] == 2200
    assert json.loads(json.dumps(result)) == result
    assert not any(item[k] for k in ('bypass_owner', 'current_authority',
        'load_or_timing_qualified', 'source_trace_retirement_authority', 'release_authority'))
    assert op.row._source_binding(board) == before and Path(board.GetFileName()).read_bytes() == saved


@pytest.mark.parametrize('fault', ['ordinary', 'value', 'mpn', 'part', 'passive_type', 'peer_type',
    'supply_type', 'peer_net', 'unknown_peer', 'dnp', 'locked', 'group', 'rotation', 'missing_export_semantics'])
def test_names_partial_source_and_unknown_authority_do_not_create_eligibility(tmp_path, monkeypatch, fault):
    board, first, second, resistor, root, tree, poses = fixture(tmp_path, monkeypatch)
    if fault == 'ordinary': monkeypatch.setattr(op.ordinary, 'eligible_nets', lambda *a, **k: set())
    elif fault == 'value': resistor.SetValue('0')
    elif fault == 'mpn': resistor.SetField('MPN', 'changed')
    elif fault == 'part': op.synth._first(op.synth._first(tree, 'components')[-1], 'libsource')[-1][1] = 'C'
    elif fault == 'passive_type': root.write_text(root.read_text().replace('(symbol "fixture:R" (symbol "unit_1_1" (pin passive', '(symbol "fixture:R" (symbol "unit_1_1" (pin input'))
    elif fault in ('peer_type', 'supply_type'):
        kind, name = ('input', 'SCL') if fault == 'peer_type' else ('power_in', 'P6')
        text, changed = re.subn(r'\(pin '+kind+r'(?= line \(at [^)]+\) \(length 1\) \(name "'+name+r'"\))', '(pin passive', root.read_text())
        assert changed == 2; root.write_text(text)
    elif fault == 'peer_net': second.FindPadByNumber('5').SetNetCode(0)
    elif fault == 'unknown_peer': second.SetField('MPN', 'unknown')
    elif fault == 'dnp': resistor.SetDNP(True)
    elif fault == 'locked': resistor.SetLocked(True)
    elif fault == 'group':
        group = pcbnew.PCB_GROUP(board); board.Add(group); group.AddItem(resistor)
    elif fault == 'rotation': poses[resistor.GetReference()][2] = 45
    elif fault == 'missing_export_semantics':
        exporter = op.canonical._export
        def incomplete(*args):
            tree, metadata = exporter(*args); metadata.pop(next(iter(op.semantic.metadata(tree))))
            return tree, metadata
        monkeypatch.setattr(op.canonical, '_export', incomplete)
    try:
        result = op.plan(board, poses, board_hint=str(root))
    except ValueError:
        return
    assert result == {}


@pytest.mark.parametrize('fault', [None, 'forged', 'missing_current', 'width_missing', 'part',
    'pad', 'net', 'face', 'stationary_peer', 'unrequested_peer_motion', 'regroup'])
def test_fresh_requests_restore_two_domains_and_every_original_peer_without_current_guess(tmp_path, monkeypatch, fault):
    import cec_decoupler_cell as cells
    board, first, second, resistor, root, tree, poses = fixture(tmp_path, monkeypatch)
    selected = op.plan(board, poses, board_hint=str(root))
    child = pcbnew.LoadBoard(board.GetFileName()); fp = child.FindFootprintByReference(resistor.GetReference())
    target = poses[resistor.GetReference()]
    fp.SetPosition(pcbnew.VECTOR2I(*(round(v*1e6) for v in target[:2]))); fp.SetOrientationDegrees(target[2])
    current = dict(required_by_layer_nm={int(l): 800000 for l in board.GetEnabledLayers().CuStack()},
        current_authority={'test_source_requirement': True})
    monkeypatch.setattr(cells, '_supply_current_widths', lambda *a: current)
    if fault == 'forged': selected[resistor.GetReference()]['nominal_resistance_ohms'] = 1
    elif fault == 'missing_current': monkeypatch.setattr(cells, '_supply_current_widths', lambda *a: None)
    elif fault == 'width_missing': current['required_by_layer_nm'].pop(next(iter(current['required_by_layer_nm'])))
    elif fault == 'part': fp.SetField('MPN', 'changed')
    elif fault == 'pad': fp.FindPadByNumber('1').SetSize(pcbnew.VECTOR2I_MM(2, 2))
    elif fault == 'net': fp.FindPadByNumber('1').SetNetCode(0)
    elif fault == 'face': fp.Flip(pcbnew.VECTOR2I(0, 0), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    elif fault == 'stationary_peer': child.FindFootprintByReference(second.GetReference()).SetField('MPN', 'changed')
    elif fault == 'unrequested_peer_motion': child.FindFootprintByReference(second.GetReference()).Move(pcbnew.VECTOR2I(1, 0))
    elif fault == 'regroup':
        group = pcbnew.PCB_GROUP(child); child.Add(group); group.AddItem(fp)
    proposal = dict(poses=poses, selected_signal_bias_resistors=selected, board_hint=str(root))
    if fault is not None:
        with pytest.raises(ValueError): op.requests(board, child, proposal)
        return
    requests = op.requests(board, child, proposal)
    assert len(requests) == 2 and {r['role'] for r in requests.values()} == {'control_signal', 'nonload_pullup_supply'}
    supply = next(r for r in requests.values() if r['role'] == 'nonload_pullup_supply')
    assert supply['width_nm'] >= 800000 and supply['unchanged_full_rail_current_contract'] == current
    assert supply['new_barrel_authority'] is False and supply['class_only_supply_prefix_authority'] is False


def test_a_moving_shared_peer_requires_its_actual_rigid_cohort_not_a_stationary_alias(tmp_path, monkeypatch):
    import cec_decoupler_cell as cells
    board, first, second, resistor, root, tree, poses = fixture(tmp_path, monkeypatch)
    poses[second.GetReference()] = [second.GetPosition().x/1e6+1, second.GetPosition().y/1e6, 90]
    selected = op.plan(board, poses, board_hint=str(root)); child = pcbnew.LoadBoard(board.GetFileName())
    for ref, target in poses.items():
        fp = child.FindFootprintByReference(ref); fp.SetPosition(pcbnew.VECTOR2I(*(round(v*1e6) for v in target[:2])))
        fp.SetOrientationDegrees(target[2])
    monkeypatch.setattr(cells, '_supply_current_widths', lambda *a: dict(
        required_by_layer_nm={int(l): 800000 for l in board.GetEnabledLayers().CuStack()}, current_authority={'source': True}))
    assert len(op.requests(board, child, dict(poses=poses, selected_signal_bias_resistors=selected, board_hint=str(root)))) == 2


def test_macro_dispatch_saved_context_and_mandatory_restoration_are_wired():
    import cec_cell_escape_replan as escape
    import cec_complete_cell_receiving as saved
    text = Path(escape.__file__).read_text(); receiving = Path(saved.__file__).read_text()
    assert "result['selected_signal_bias_resistors']=signal_biases" in text
    assert "requests.update(signal_bias.requests(source,board,proposal))" in text
    assert "signal_bias_resistor_cannot_alias_power_bypass" in text
    assert "for ref in sorted(refs|unowned):" in receiving
    assert 'signal_bias.requests(parent,child' in receiving
    assert 'actual_motion_not_complete_source_selected_cells' in receiving


def test_real_dispatch_and_saved_motion_use_the_new_passive_witness(tmp_path, monkeypatch):
    import cec_cell_escape_replan as escape
    import cec_complete_cell_receiving as saved
    import cec_decoupler_cell as cells
    board, first, second, resistor, root, tree, poses = fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(escape.constraints, '_device_bypass_assignment', lambda *a, **k: {'assigned': {}})
    proposal = escape.prepare(board, poses, board_hint=str(root))
    assert set(proposal['selected_signal_bias_resistors']) == {resistor.GetReference()}
    assert not proposal['device_contracts'] and not proposal['selected_bypasses']
    assert 'selected_control_pullups' not in proposal
    child = pcbnew.LoadBoard(board.GetFileName()); fp = child.FindFootprintByReference(resistor.GetReference())
    target = poses[resistor.GetReference()]
    fp.SetPosition(pcbnew.VECTOR2I(*(round(v*1e6) for v in target[:2]))); fp.SetOrientationDegrees(target[2])
    monkeypatch.setattr(saved, '_assignments', lambda *a: {})
    monkeypatch.setattr(cells, '_supply_current_widths', lambda *a: dict(
        required_by_layer_nm={int(l): 800000 for l in board.GetEnabledLayers().CuStack()}, current_authority={'source': True}))
    actual, moved = saved._poses(board, child, str(root))
    assert actual == poses and moved == set(poses)


def test_export_mutation_cannot_reuse_source_facts(tmp_path, monkeypatch):
    board, first, second, resistor, root, tree, poses = fixture(tmp_path, monkeypatch)
    export = op.canonical._export
    def changed(*args):
        answer = export(*args); root.write_text(root.read_text()+'\n')
        return answer
    monkeypatch.setattr(op.canonical, '_export', changed)
    with pytest.raises(ValueError, match='source_family_or_code_changed'):
        op.plan(board, poses, board_hint=str(root))


@pytest.mark.parametrize('timeout', [True, 0, -1, 11, float('nan')])
def test_invalid_work_leases_never_create_source_or_requests(tmp_path, monkeypatch, timeout):
    board, first, second, resistor, root, tree, poses = fixture(tmp_path, monkeypatch)
    with pytest.raises(ValueError): op.plan(board, poses, board_hint=str(root), timeout_s=timeout)
    with pytest.raises(ValueError): op.requests(board, board, {}, timeout_s=timeout)


@pytest.mark.parametrize('locked', [False, True])
@pytest.mark.parametrize('fault', [None, 'lock', 'member', 'regroup', 'nested'])
def test_unchanged_grouped_bus_peer_uses_native_membership_not_base_pointer_equality(tmp_path, monkeypatch, locked, fault):
    import cec_decoupler_cell as cells
    board, first, second, resistor, root, tree, poses = fixture(tmp_path, monkeypatch)
    group = pcbnew.PCB_GROUP(board); board.Add(group); group.AddItem(first); group.SetLocked(locked)
    field._save_field_snapshot(board, Path(board.GetFileName()))
    selected = op.plan(board, poses, board_hint=str(root)); child = pcbnew.LoadBoard(board.GetFileName())
    fp = child.FindFootprintByReference(resistor.GetReference()); target = poses[resistor.GetReference()]
    fp.SetPosition(pcbnew.VECTOR2I(*(round(v*1e6) for v in target[:2]))); fp.SetOrientationDegrees(target[2])
    actual_group = next(g for g in child.Groups() if op.force._uid(g) == op.force._uid(group))
    if fault == 'lock': actual_group.SetLocked(not locked)
    elif fault == 'member': actual_group.AddItem(child.FindFootprintByReference(second.GetReference()))
    elif fault == 'regroup':
        actual_group.RemoveItem(child.FindFootprintByReference(first.GetReference()))
        replacement = pcbnew.PCB_GROUP(child); child.Add(replacement); replacement.AddItem(child.FindFootprintByReference(first.GetReference()))
    elif fault == 'nested':
        parent = pcbnew.PCB_GROUP(child); child.Add(parent); parent.AddItem(actual_group)
    monkeypatch.setattr(cells, '_supply_current_widths', lambda *a: dict(
        required_by_layer_nm={int(l): 800000 for l in board.GetEnabledLayers().CuStack()}, current_authority={'source': True}))
    proposal = dict(poses=poses, selected_signal_bias_resistors=selected, board_hint=str(root))
    if fault is not None:
        with pytest.raises(ValueError): op.requests(board, child, proposal)
    else:
        assert len(op.requests(board, child, proposal)) == 2
