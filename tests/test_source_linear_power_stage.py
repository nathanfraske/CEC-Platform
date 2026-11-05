"""Native/canonical Source stage fixtures; ONLY export/current are synthetic.

The reused fixture authors actual schematic hierarchy and native saved pads;
its exporter is a narrow literal synthetic netlist, not an identity mock.
The full-current stub below is explicitly synthetic, never a board budget.
"""
import json
from pathlib import Path
import uuid

import pcbnew
import pytest
import cec_field_coupling as field
import cec_source_linear_power_stage as op
from test_programming_resistor_placement import fixture as canonical_fixture

REAL_CURRENT_MODEL = op.full._model


def power_symbol_fixture(board, root, tree, *, part='out', reference='UNRELATED_ANNOTATION'):
    """A real nonphysical power symbol; reference spelling grants nothing."""
    sid=str(uuid.uuid4());lib_id='cec-power:'+part
    kind='power_out'if part=='PWR_FLAG'else'power_in'
    declaration='(symbol "'+lib_id+'" (power global) (symbol "power_0_1" (pin '+kind+' line '+\
        '(at 0 0 90) (length 0) (name "~") (number "1"))))'
    text=root.read_text().replace('(lib_symbols ', '(lib_symbols '+declaration+' ', 1)
    block='(symbol (lib_id "'+lib_id+'") (at 400 10 0) (unit 1) (uuid "'+sid+'") '+\
        '(property "Reference" "'+reference+'") (property "Value" "'+part+'"))'
    root.write_text(text[:-1]+' '+block+')')
    comp=['comp',['ref',reference],['value',part],['libsource',['lib','cec-power'],['part',part]],['tstamps',sid]]
    op.synth._first(tree,'components').append(comp)
    net=next(n for n in op.synth._kids(op.synth._first(tree,'nets'),'net')if op.synth._val(n,'name','')=='out')
    node=['node',['ref',reference],['pin','1'],['pinfunction','~_1'],['pintype',kind]]
    net.append(node)
    return comp,node,declaration


def literal_erc_convention(board, owner, root, tree, types):
    """Author matching actual Source/native/export metadata, not a waiver."""
    text = root.read_text()
    for number, kind in types.items():
        # Fixture pins have unique names, so replace only that literal pin.
        name = op.manufacturer.PIN_NAMES[number]
        start = text.index('(pin ', text.index('(symbol "fixture:TPS"'))
        needle = '(name "'+name+'") (number "'+number+'"))'
        end = text.index(needle, start)+len(needle)
        begin = text.rfind('(pin ', start, end)
        old = text[begin:end]
        text = text[:begin]+old.replace(old.split()[1], kind, 1)+text[end:]
        owner.FindPadByNumber(number).SetPinFunction(name)
        owner.FindPadByNumber(number).SetPinType(kind)
        node = next(n for net in op.synth._kids(op.synth._first(tree, 'nets'), 'net')
                    for n in op.synth._kids(net, 'node') if op.synth._val(n, 'ref', '') == owner.GetReference()
                    and op.synth._val(n, 'pin', '') == number)
        op.synth._first(node, 'pintype')[1] = kind
    root.write_text(text)
    field._save_field_snapshot(board, Path(board.GetFileName()))


def fixture(tmp_path, monkeypatch, turn=0, back=False):
    board, owner, resistor, root, tree, _ = canonical_fixture(tmp_path, monkeypatch, turn, back)
    calls = []
    def synthetic_current(board, source, net, hint):
        assert Path(source) == Path(board.GetFileName()) and hint == str(root)
        assert net in ('input-a', 'input-b', 'out')
        calls.append(net)
        return ('synthetic_test_only', {'complete': True, 'net': net},
                {'net': net, 'synthetic_test_only': True, 'amps': .125,
                 'geometry_margin': 1.25})
    monkeypatch.setattr(op.full, '_model', synthetic_current)
    poses = {owner.GetReference(): [owner.GetPosition().x/1e6+.5,
        owner.GetPosition().y/1e6, (owner.GetOrientationDegrees()+90) % 360]}
    return board, owner, root, tree, poses, calls


@pytest.mark.parametrize('turn', [0, 90, 180, 270])
@pytest.mark.parametrize('back', [False, True])
def test_complete_native_canonical_linear_stage(tmp_path, monkeypatch, turn, back):
    board, owner, root, tree, poses, calls = fixture(tmp_path, monkeypatch, turn, back)
    saved = Path(board.GetFileName()).read_bytes(); before = op.row._source_binding(board)
    result = op.collect(board, poses, board_hint=str(root), enabled=True)
    item = result[owner.GetReference()]
    assert item['role'] == op.ROLE and item['owner_uuid'] == op.force._uid(owner)
    assert sorted(calls) == ['input-a', 'input-b', 'out']
    assert set(item['source_power_nets']) == set(calls)
    assert sum(len(n['terminals']) for n in item['source_power_nets'].values()) == 4
    assert item['source_component']['pins']['9']['explicit_Source_no_connect_identity']
    assert not any(item[k] for k in ('current_authority', 'source_trace_retirement_authority',
        'new_barrel_authority', 'routing_admitted', 'placement_admitted', 'release_authority'))
    assert json.loads(json.dumps(result)) == result
    assert before == op.row._source_binding(board) and saved == Path(board.GetFileName()).read_bytes()


def test_disabled_is_noop_even_without_a_board():
    assert op.collect(None, None, board_hint=None) == {}


def test_stationary_owner_is_not_claimed(tmp_path, monkeypatch):
    board, owner, root, tree, poses, calls = fixture(tmp_path, monkeypatch)
    poses[owner.GetReference()] = [owner.GetPosition().x/1e6, owner.GetPosition().y/1e6,
                                  owner.GetOrientationDegrees()]
    assert op.collect(board, poses, board_hint=str(root), enabled=True) == {} and calls == []


@pytest.mark.parametrize('fault', ['unsaved', 'manufacturer', 'mpn', 'pin_missing', 'pin_duplicate',
    'native_function', 'native_type', 'native_net', 'source_function', 'export_type',
    'export_net', 'export_manufacturer', 'current_missing', 'switching', 'locked', 'dnp',
    'noncardinal', 'missing_owner', 'bad_hint', 'group', 'duplicate_reference',
    'extra_native_supply_peer', 'extra_export_supply_peer'])
def test_unknown_or_partial_Source_never_grants_stage_scope(tmp_path, monkeypatch, fault):
    board, owner, root, tree, poses, calls = fixture(tmp_path, monkeypatch)
    ref = owner.GetReference()
    if fault == 'unsaved': owner.SetPosition(owner.GetPosition()+pcbnew.VECTOR2I(1000, 0))
    elif fault == 'manufacturer': owner.SetField('Manufacturer', 'Unknown')
    elif fault == 'mpn': owner.SetField('MPN', 'TPS2121-UNKNOWN')
    elif fault == 'pin_missing': owner.Remove(owner.FindPadByNumber('1'))
    elif fault == 'pin_duplicate': owner.FindPadByNumber('1').SetNumber('2')
    elif fault == 'native_function': owner.FindPadByNumber('2').SetPinFunction('OUT')
    elif fault == 'native_type': owner.FindPadByNumber('2').SetPinType('power_out')
    elif fault == 'native_net': owner.FindPadByNumber('2').SetNet(owner.FindPadByNumber('1').GetNet())
    elif fault == 'source_function': root.write_text(root.read_text().replace('(name "IN2")', '(name "OUT")'))
    elif fault in ('export_type', 'export_net'):
        for net in op.synth._kids(op.synth._first(tree, 'nets'), 'net'):
            for node in op.synth._kids(net, 'node'):
                if op.synth._val(node, 'ref', '') == ref and op.synth._val(node, 'pin', '') == '2':
                    if fault == 'export_type': op.synth._first(node, 'pintype')[1] = 'power_out'
                    else: op.synth._first(node, 'pin')[1] = '99'
    elif fault == 'export_manufacturer':
        comp = next(c for c in op.synth._kids(op.synth._first(tree, 'components'), 'comp')
                    if op.synth._val(c, 'ref', '') == ref)
        prop = next(p for p in op.synth._kids(comp, 'property') if op.synth._val(p, 'name', '') == 'Manufacturer')
        op.synth._first(prop, 'value')[1] = 'Unknown'
    elif fault == 'current_missing':
        def missing(*a, **k): raise ValueError('synthetic_missing_current_authority')
        monkeypatch.setattr(op.full, '_model', missing)
    elif fault == 'switching': owner.SetField('MPN', 'TLV62569DBVR'); owner.SetValue('TLV62569DBVR')
    elif fault == 'locked': owner.SetLocked(True)
    elif fault == 'dnp': owner.SetDNP(True)
    elif fault == 'noncardinal': poses[ref][2] += 45
    elif fault == 'missing_owner': poses = {'not-a-native-owner': [1, 2, 0]}
    elif fault == 'group':
        group = pcbnew.PCB_GROUP(board); group.SetName('unreviewed-stage-group')
        board.Add(group); group.AddItem(owner)
    elif fault == 'duplicate_reference':
        duplicate = pcbnew.FOOTPRINT(board); duplicate.SetReference(ref); board.Add(duplicate)
    elif fault == 'extra_native_supply_peer':
        peer = pcbnew.FOOTPRINT(board); peer.SetReference('extra-peer'); board.Add(peer)
        pad = pcbnew.PAD(peer); pad.SetNumber('1'); pad.SetNet(owner.FindPadByNumber('2').GetNet()); peer.Add(pad)
    elif fault == 'extra_export_supply_peer':
        net = next(n for n in op.synth._kids(op.synth._first(tree, 'nets'), 'net')
                   if op.synth._val(n, 'name', '') == 'input-b')
        net.append(['node', ['ref', 'missing-native-peer'], ['pin', '1']])
    hint = 'invented-board-family' if fault == 'bad_hint' else str(root)
    # Persist intentional hostile native facts so failures exercise the
    # canonical/manufacturer checks rather than only the saved-board guard.
    if fault not in ('unsaved',): field._save_field_snapshot(board, Path(board.GetFileName()))
    if fault == 'mpn':
        # An unknown model is unclaimed, never granted an invented table.
        assert op.collect(board, poses, board_hint=hint, enabled=True) == {}
    else:
        with pytest.raises((ValueError, AssertionError, FileNotFoundError)):
            op.collect(board, poses, board_hint=hint, enabled=True)


@pytest.mark.parametrize('timeout', [0, -1, 11, float('nan'), True])
def test_operation_lease_is_finite(tmp_path, monkeypatch, timeout):
    board, owner, root, tree, poses, calls = fixture(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match='bounded_linear_stage'):
        op.collect(board, poses, board_hint=str(root), enabled=True, timeout_s=timeout)


def test_more_than_four_stages_are_refused_before_Source_export(tmp_path, monkeypatch):
    board, owner, root, tree, poses, calls = fixture(tmp_path, monkeypatch)
    for index in range(4):
        other = pcbnew.FOOTPRINT(owner); other.SetReference('extra-stage-'+str(index)); board.Add(other)
        poses[other.GetReference()] = [other.GetPosition().x/1e6+.5, other.GetPosition().y/1e6, 0]
    with pytest.raises(ValueError, match='four_stage_sixty_four_pin'):
        op.collect(board, poses, board_hint=str(root), enabled=True)


@pytest.mark.parametrize('missing_rail', ['input-a', 'input-b', 'out'])
def test_each_independent_power_net_needs_its_own_existing_current_authority(tmp_path, monkeypatch, missing_rail):
    board, owner, root, tree, poses, calls = fixture(tmp_path, monkeypatch)
    positive = op.full._model
    def one_unrated(board, source, net, hint):
        if net == missing_rail:
            raise ValueError('synthetic_unrated_rail:'+net)
        return positive(board, source, net, hint)
    monkeypatch.setattr(op.full, '_model', one_unrated)
    before = Path(board.GetFileName()).read_bytes()
    with pytest.raises(ValueError, match='synthetic_unrated_rail:'+missing_rail):
        op.collect(board, poses, board_hint=str(root), enabled=True)
    assert before == Path(board.GetFileName()).read_bytes()


def test_actual_full_model_refuses_fixture_without_existing_ratings(tmp_path, monkeypatch):
    board, owner, root, tree, poses, calls = fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(op.full, '_model', REAL_CURRENT_MODEL)
    with pytest.raises(ValueError, match='existing|authority|contract|current'):
        op.collect(board, poses, board_hint=str(root), enabled=True)
    assert not calls  # No synthetic current authority was used in this test.


@pytest.mark.parametrize('turn', [0, 90, 180, 270])
@pytest.mark.parametrize('back', [False, True])
def test_documented_pass_through_erc_convention_preserves_physical_OUT_role(tmp_path, monkeypatch, turn, back):
    board, owner, root, tree, poses, calls = fixture(tmp_path, monkeypatch, turn, back)
    literal_erc_convention(board, owner, root, tree, {'1': 'power_in', '8': 'power_in'})
    before = Path(board.GetFileName()).read_bytes()
    item = op.collect(board, poses, board_hint=str(root), enabled=True)[owner.GetReference()]
    assert item['literal_source_output_erc_type'] == 'power_in'
    assert item['physical_power_direction_from_complete_manufacturer_table_not_erc_type']
    terminals = {p['number']: p for net in item['source_power_nets'].values() for p in net['terminals']}
    assert terminals['1']['role'] == terminals['8']['role'] == 'power_output'
    assert terminals['1']['literal_source_erc_type'] == terminals['8']['literal_source_erc_type'] == 'power_in'
    assert sorted(calls) == ['input-a', 'input-b', 'out']
    assert not item['current_authority'] and before == Path(board.GetFileName()).read_bytes()


@pytest.mark.parametrize('types', [
    {'1': 'power_in'}, {'2': 'power_out'}, {'1': 'input', '8': 'input'},
    {'1': 'passive', '8': 'passive'},
])
def test_mixed_or_unreviewed_literal_erc_types_never_gain_physical_role(tmp_path, monkeypatch, types):
    board, owner, root, tree, poses, calls = fixture(tmp_path, monkeypatch)
    literal_erc_convention(board, owner, root, tree, types)
    before = Path(board.GetFileName()).read_bytes()
    with pytest.raises(ValueError, match='canonical_linear_stage_power_direction|consistent_literal'):
        op.collect(board, poses, board_hint=str(root), enabled=True)
    assert before == Path(board.GetFileName()).read_bytes()


@pytest.mark.parametrize('part', ['out', 'PWR_FLAG'])
def test_real_global_power_label_or_flag_is_not_a_missing_physical_component(tmp_path, monkeypatch, part):
    board, owner, root, tree, poses, calls = fixture(tmp_path, monkeypatch)
    power_symbol_fixture(board, root, tree, part=part)
    before=Path(board.GetFileName()).read_bytes()
    item=op.collect(board,poses,board_hint=str(root),enabled=True)[owner.GetReference()]
    output=item['source_power_nets']['out'];virtual=output['nonphysical_Source_global_power_symbols']
    assert len(virtual)==1 and virtual[0]['reference']=='UNRELATED_ANNOTATION'
    assert virtual[0]['nonphysical_global_power_symbol']and not virtual[0]['current_authority']
    assert len(output['canonical_logical_members'])==len(output['native_logical_members'])+1
    assert not board.FindFootprintByReference('UNRELATED_ANNOTATION')
    assert before==Path(board.GetFileName()).read_bytes()


@pytest.mark.parametrize('fault', ['no_marker','selected_mpn','physical_footprint','wrong_export_type',
    'extra_pin','wrong_value','missing_instance','missing_component','fake_library'])
def test_missing_physical_part_cannot_hide_as_power_annotation(tmp_path, monkeypatch, fault):
    board, owner, root, tree, poses, calls = fixture(tmp_path, monkeypatch)
    comp,node,declaration=power_symbol_fixture(board,root,tree)
    if fault=='no_marker':root.write_text(root.read_text().replace('(power global)',''))
    elif fault=='selected_mpn':comp.append(['property',['name','MPN'],['value','actual-part']])
    elif fault=='physical_footprint':comp.append(['footprint','actual:physical'])
    elif fault=='wrong_export_type':op.synth._first(node,'pintype')[1]='passive'
    elif fault=='extra_pin':root.write_text(root.read_text().replace(declaration,
        declaration[:-2]+' (pin power_in line (at 1 0 0) (length 0) (name "~") (number "2"))))'))
    elif fault=='wrong_value':op.synth._first(comp,'value')[1]='other'
    elif fault=='missing_instance':root.write_text(root.read_text().replace('(property "Reference" "UNRELATED_ANNOTATION")',
        '(property "Reference" "OTHER")'))
    elif fault=='missing_component':op.synth._first(tree,'components').remove(comp)
    else:root.write_text(root.read_text().replace('cec-power:out','fixture:out'))
    before=Path(board.GetFileName()).read_bytes()
    with pytest.raises(ValueError):op.collect(board,poses,board_hint=str(root),enabled=True)
    assert before==Path(board.GetFileName()).read_bytes()
