"""Co-owned capacitors are Source topology, never a low-power/current alias."""
import copy
from pathlib import Path
import time
import uuid
import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_cell_row_rebuild as row
import cec_coowned_ground_component_join as op
import cec_field_coupling as field
import cec_force_current as force
import cec_ground_component_join as legacy
import cec_source_capacitor_control_ground as source
import cec_source_ground_leaf as leaf
import cec_synth_pipeline as synth
from test_control_pullup_placement import fixture as control_fixture
from test_field_proposals import track


def fixture(tmp_path, monkeypatch, turn=0, back=False):
    b, module, control, pull, button, root, tree, poses = control_fixture(tmp_path, monkeypatch)
    net = pcbnew.NETINFO_ITEM(b, 'renamed_input_rail');b.Add(net)
    for name in ('other_mux_input', 'separate_mux_output'):b.Add(pcbnew.NETINFO_ITEM(b,name))
    parts = []
    def part(ref, value, mpn, fpid, assignments):
        fp = pcbnew.FOOTPRINT(b);b.Add(fp);fp.SetReference(ref);fp.SetValue(value)
        fp.SetField('MPN', mpn);fp.SetFPID(pcbnew.LIB_ID(*fpid.split(':')))
        for number, rail in assignments:
            pad = pcbnew.PAD(fp);pad.SetNumber(number);pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetLayerSet(pcbnew.PAD.SMDMask())
            pad.SetSize(pcbnew.VECTOR2I_MM(.5, .5));fp.Add(pad)
            if rail:pad.SetNet(b.FindNet(rail))
        parts.append(fp);return fp
    bulk = part('C_renamed_bulk', '10uF', 'CL21A106KAYNNNE',
        'cec-Capacitor_SMD:C_0805_2012Metric', [('1', net.GetNetname()), ('2', 'GND')])
    owner = part('renamed_power_mux', 'TPS2121RUXR', 'TPS2121RUXR',
        'cec-Package_DFN_QFN:RUX0012A', [(str(i), net.GetNetname() if i == 2 else 'GND' if i == 12 else
            'other_mux_input' if i == 7 else 'separate_mux_output' if i in (1,8) else '')
                                     for i in range(1, 13)])
    libraries, symbols = [], []
    for index, fp in enumerate(parts):
        name = 'Extra' + str(index);uid = str(uuid.uuid4());ref = fp.GetReference()
        pins = []
        for pad in fp.Pads():
            i=int(pad.GetNumber())
            kind = ('power_in' if pad.GetNumber() in ('2','7','12') else
                'power_out' if pad.GetNumber()in('1','8')else'passive')if fp==owner else'passive'
            pins.append('(pin ' + kind + ' line (at ' + str(i) + ' 0 0) (length 1) (name "P' +
                        pad.GetNumber() + '") (number "' + pad.GetNumber() + '"))')
        libraries.append('(symbol "fixture:' + name + '" (symbol "unit_1_1" ' + ' '.join(pins) + '))')
        props = [("Reference", ref), ("Value", fp.GetValue()), ("Footprint", fp.GetFPIDAsString()),
                 ("MPN", fp.GetField('MPN').GetText())]
        symbols.append('(symbol (lib_id "fixture:' + name + '") (at ' + str(500 + index * 100) +
            ' 10 0) (unit 1) (uuid "' + uid + '") ' +
            ' '.join('(property "' + key + '" "' + value + '")' for key, value in props) + ')')
        synth._first(tree, 'components').append(synth.parse_sexpr('(comp (ref "' + ref + '") (value "' +
            fp.GetValue() + '") (footprint "' + fp.GetFPIDAsString() + '") (property (name "MPN") (value "' +
            fp.GetField('MPN').GetText() + '")) (libsource (lib "fixture") (part "' + name +
            '")) (tstamps "' + uid + '"))'))
        for pad in fp.Pads():
            if not pad.GetNetname():continue
            section = synth._first(tree, 'nets')
            chosen = next((n for n in synth._kids(section, 'net') if synth._val(n, 'name', '') == pad.GetNetname()), None)
            if chosen is None:
                chosen = ['net', ['name', pad.GetNetname()]];section.append(chosen)
            chosen.append(['node', ['ref', ref], ['pin', pad.GetNumber()]])
    text = root.read_text().replace('(lib_symbols ', '(lib_symbols ' + ' '.join(libraries) + ' ')
    root.write_text(text[:-1] + ' ' + ' '.join(symbols) + ')')
    for index, fp in enumerate(b.GetFootprints()):
        for i, pad in enumerate(fp.Pads()):pad.SetPosition(pcbnew.VECTOR2I_MM(35 + index * 4, 5 + i * .7))
    control.FindPadByNumber('1').SetPosition(pcbnew.VECTOR2I_MM(20, 19))
    control.FindPadByNumber('2').SetPosition(pcbnew.VECTOR2I_MM(20, 20))
    bulk.FindPadByNumber('1').SetPosition(pcbnew.VECTOR2I_MM(22, 19))
    bulk.FindPadByNumber('2').SetPosition(pcbnew.VECTOR2I_MM(22, 20))
    for fp in b.GetFootprints():
        if turn:fp.Rotate(pcbnew.VECTOR2I_MM(20, 20), pcbnew.EDA_ANGLE(turn, pcbnew.DEGREES_T))
        if back:fp.Flip(pcbnew.VECTOR2I_MM(20, 20), False)
    b.GetNetInfo().GetNetItem('GND').GetNetClassSlow().SetTrackWidth(500000)
    ground = control.FindPadByNumber('2');second = bulk.FindPadByNumber('2')
    edge = track(b, 'GND', [x / 1e6 for x in ground.GetPosition()],
                 [x / 1e6 for x in second.GetPosition()], width=.5,
                 layer=int(next(iter(ground.GetLayerSet().CuStack()))))
    live = {force._item_key(p): p for p in (ground, second, edge)}
    part_keys = set(live)
    return b, control, bulk, owner, root, tree, part_keys, live, edge


def derive(data):
    b, control, bulk, owner, root, tree, part_keys, live, edge = data
    proof, snapshot = leaf.plan_with_export(b, board_hint=str(root))
    return source.derive(b, str(root), proof, snapshot, [part_keys], live, set(), time.monotonic() + 10)


@pytest.mark.parametrize('turn', [0, 90, 180, 270])
@pytest.mark.parametrize('back', [False, True])
def test_actual_renamed_source_cohort_is_pose_independent_and_not_ampacity(tmp_path, monkeypatch, turn, back):
    data = fixture(tmp_path, monkeypatch, turn, back);before = row._source_binding(data[0])
    cohorts = derive(data);assert len(cohorts) == 1
    proof = cohorts[0]['proof'];assert set(cohorts[0]['component']) == data[6]
    assert proof['unchanged_source_ground_class_floor_nm'] == 500000 and proof['class_only']
    for name in ('low_power_classification', 'aggregate_ground_current_inferred', 'ampacity_qualified',
                 'immediate_return_qualified', 'release_authority'):assert proof[name] is False
    assert source.bindings_current([proof]) and row._source_binding(data[0]) == before
    cap = proof['input_capacitor_ground_proofs'][0]
    assert cap['rail'] == 'renamed_input_rail' and cap['manufacturer_input_witnesses'][0]['pin'] == '2'


@pytest.mark.parametrize('fault', ['source_mpn', 'native_mpn', 'value', 'input_type', 'cap_type',
    'extra_rail_peer', 'input_net', 'ground_net', 'duplicate_pin', 'dnp', 'no_control',
    'thin_retained', 'retained_inner', 'unknown_pad', 'input_NC', 'ground_NC'])
def test_every_coowner_and_real_source_witness_is_required(tmp_path, monkeypatch, fault):
    data = fixture(tmp_path, monkeypatch);b, control, bulk, owner, root, tree, keys, live, edge = data
    if fault == 'source_mpn':root.write_text(root.read_text().replace('CL21A106KAYNNNE', 'unknown'))
    elif fault == 'native_mpn':bulk.SetField('MPN', 'unknown')
    elif fault == 'value':bulk.SetValue('not_capacitance')
    elif fault == 'input_type':
        text=root.read_text();start=text.index('(symbol "fixture:Extra1"');end=text.index('(symbol "fixture:Module"')
        chunk=text[start:end];assert chunk.count('(pin power_in line (at 2 0 0)')==1
        root.write_text(text[:start]+chunk.replace('(pin power_in line (at 2 0 0)','(pin passive line (at 2 0 0)')+text[end:])
    elif fault == 'cap_type':
        text = root.read_text();start = text.index('(symbol "fixture:Extra0"');end = text.index('(symbol "fixture:Extra1"')
        root.write_text(text[:start] + text[start:end].replace('(pin passive', '(pin input', 1) + text[end:])
    elif fault == 'extra_rail_peer':
        chosen = next(n for n in synth._kids(synth._first(tree, 'nets'), 'net') if synth._val(n, 'name', '') == 'renamed_input_rail')
        chosen.append(['node', ['ref', 'unowned'], ['pin', '1']])
    elif fault == 'input_net':owner.FindPadByNumber('2').SetNetCode(0)
    elif fault == 'ground_net':owner.FindPadByNumber('12').SetNetCode(0)
    elif fault == 'duplicate_pin':owner.FindPadByNumber('1').SetNumber('2')
    elif fault == 'dnp':bulk.SetDNP(True)
    elif fault == 'no_control':
        original = leaf.plan_with_export
        def without(*args, **kw):
            proof, snap = original(*args, **kw);proof['proofs'].pop(force._uid(control.FindPadByNumber('2')), None);return proof, snap
        monkeypatch.setattr(leaf, 'plan_with_export', without)
    elif fault == 'thin_retained':edge.SetWidth(499999)
    elif fault == 'retained_inner':edge.SetLayer(pcbnew.In2_Cu)
    elif fault == 'unknown_pad':
        pad = owner.FindPadByNumber('12');keys.add(force._item_key(pad));live[force._item_key(pad)] = pad
    elif fault in ('input_NC', 'ground_NC'):
        x = 602 if fault == 'input_NC' else 612
        root.write_text(root.read_text()[:-1] + ' (no_connect (at ' + str(x) + ' 10) (uuid "' + str(uuid.uuid4()) + '")))')
    try:cohorts = derive(data)
    except (ValueError, KeyError):cohorts = []
    assert not cohorts


def test_unused_singleton_NC_is_not_a_live_input_or_return_exception(tmp_path, monkeypatch):
    data = fixture(tmp_path, monkeypatch);b, control, bulk, owner, root, tree, *_ = data
    unused = pcbnew.NETINFO_ITEM(b, 'unused_name_is_not_authority');b.Add(unused)
    owner.FindPadByNumber('9').SetNet(unused)
    synth._first(tree, 'nets').append(['net', ['name', unused.GetNetname()],
        ['node', ['ref', owner.GetReference()], ['pin', '9']]])
    root.write_text(root.read_text()[:-1] + ' (no_connect (at 609 10) (uuid "' + str(uuid.uuid4()) + '")))')
    assert len(derive(data)) == 1


@pytest.mark.parametrize('fault', ['missing', 'root', 'semantic', 'tree', 'source_epoch'])
def test_ephemeral_export_must_be_complete_and_current(tmp_path, monkeypatch, fault):
    data = fixture(tmp_path, monkeypatch);b, control, bulk, owner, root, tree, keys, live, edge = data
    proof, snapshot = leaf.plan_with_export(b, board_hint=str(root))
    if fault == 'missing':snapshot = None
    elif fault == 'root':snapshot = ('not-current', *snapshot[1:])
    elif fault == 'semantic':snapshot = copy.deepcopy(snapshot);snapshot[2]['netlist_semantic_sha256'] = '0' * 64
    elif fault == 'tree':snapshot = copy.deepcopy(snapshot);snapshot[1].append(['unexpected', 'altered'])
    else:root.write_text(root.read_text() + '\n; changed after actual export\n')
    with pytest.raises(ValueError):source.derive(b, str(root), proof, snapshot, [keys], live, set(), time.monotonic() + 10)


def native_fixture(tmp_path, monkeypatch, turn=0, back=False):
    data = fixture(tmp_path, monkeypatch, turn, back);b, control, bulk, owner, root, *_ = data
    b.SetCopperLayerCount(6)
    props = b.GetProperties();props['CEC_FAB_PROFILE'] = 'jlcpcb_6l_pofv_signal';b.SetProperties(props)
    for a, z in [((-80,-80),(80,-80)),((80,-80),(80,80)),((80,80),(-80,80)),((-80,80),(-80,-80))]:
        edge = pcbnew.PCB_SHAPE(b);edge.SetShape(pcbnew.SHAPE_T_SEGMENT);edge.SetLayer(pcbnew.Edge_Cuts)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a));edge.SetEnd(pcbnew.VECTOR2I_MM(*z));edge.SetWidth(100000);b.Add(edge)
    face = int(next(iter(control.FindPadByNumber('2').GetLayerSet().CuStack())))
    via = pcbnew.PCB_VIA(b);via.SetNet(b.FindNet('GND'));via.SetWidth(600000);via.SetDrill(300000)
    at=tuple(control.FindPadByNumber('2').GetPosition());other=tuple(bulk.FindPadByNumber('2').GetPosition())
    delta=tuple(other[i]-at[i]for i in (0,1))
    axis=tuple(at[i]-3*delta[i]//2 for i in (0,1));end=tuple(at[i]-delta[i]for i in (0,1))
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu);via.SetPosition(pcbnew.VECTOR2I(*axis));b.Add(via)
    track(b, 'GND', [v/1e6 for v in axis], [v/1e6 for v in end], layer=face, width=.5)
    for face in (pcbnew.In1_Cu, pcbnew.In4_Cu):
        zone = pcbnew.ZONE(b);zone.SetNet(b.FindNet('GND'));zone.SetLayer(face);zone.SetLocalClearance(200000)
        zone.SetMinThickness(100000);zone.Outline().NewOutline()
        for x,y in ((-79,-79),(79,-79),(79,79),(-79,79)):zone.Outline().Append(x*1000000,y*1000000)
        b.Add(zone)
    additive._ground_refill(b);path=Path(b.GetFileName());field._save_field_snapshot(b,path)
    return data, path


def construct(tmp_path, monkeypatch, turn=0, back=False):
    data, path = native_fixture(tmp_path, monkeypatch,turn,back);b, control, *_ = data
    pad = force._uid(control.FindPadByNumber('2'));q = op.plan(b, board_hint=str(data[4]), pad_uuid=pad)
    assert q['complete'], q
    before = {force._uid(t) for t in b.GetTracks()};op.construct_private(b, q, board_hint=str(data[4]))
    additive._ground_refill(b);child = force._copy_family(path, tmp_path/'child');field._save_field_snapshot(b,child)
    return data, path, child, pad, before


@pytest.mark.parametrize('turn',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_real_saved_join_is_distinct_from_legacy_low_power_and_exports_afresh(tmp_path, monkeypatch,turn,back):
    data, path, child, pad, before = construct(tmp_path, monkeypatch,turn,back);root = str(data[4]);raw=path.read_bytes()
    exporter=leaf._export;calls=[]
    def export(*args):calls.append(args[0]);return exporter(*args)
    monkeypatch.setattr(leaf,'_export',export)
    proof = op.receive(path, child, board_hint=root, pad_uuid=pad)
    assert proof['ok'] and proof['complete'], proof
    assert calls==[data[4]]
    assert proof['joined_source_ground_components'] == 1 and proof['new_holes'] == 0
    assert proof['class_only'] and not proof['low_power_classification'] and not proof['ampacity_qualified']
    assert not legacy.receive(path, child, board_hint=root)['ok']
    assert path.read_bytes() == raw


@pytest.mark.parametrize('fault', ['thin', 'new_via', 'old_track', 'pad', 'zone', 'extra_contact', 'no_progress'])
def test_saved_receiver_refuses_unowned_or_underclass_changes(tmp_path, monkeypatch, fault):
    data, path, child, pad, old = construct(tmp_path, monkeypatch);b=pcbnew.LoadBoard(str(child))
    added=[t for t in b.GetTracks() if force._uid(t) not in old]
    if fault == 'thin':added[0].SetWidth(499999)
    elif fault == 'new_via':
        via=pcbnew.PCB_VIA(b);via.SetPosition(added[0].GetStart());via.SetNet(b.FindNet('GND'))
        via.SetWidth(600000);via.SetDrill(300000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(via)
    elif fault == 'old_track':next(t for t in b.GetTracks()if force._uid(t)in old and t.GetClass()=='PCB_TRACK').SetWidth(510000)
    elif fault == 'pad':b.FindFootprintByReference('C_renamed_bulk').FindPadByNumber('2').Move(pcbnew.VECTOR2I(1,0))
    elif fault == 'zone':b.Remove(next(iter(b.Zones())))
    elif fault == 'extra_contact':track(b,'GND',(18,20),(18,21),width=.5)
    else:
        from cec_native_items import discard_items
        discard_items(b,added)
    field._save_field_snapshot(b,child)
    assert not op.receive(path,child,board_hint=str(data[4]),pad_uuid=pad)['ok']


def test_functional_source_leaf_epoch_binding_is_not_limited_to_optional_or_control_leaves(tmp_path,monkeypatch):
    data=fixture(tmp_path,monkeypatch);proof=leaf.plan(data[0],board_hint=str(data[4]))
    selected=[v for v in proof['proofs'].values()if v['kind']=='source_manufacturer_functional_ground_pin']
    assert selected and leaf.bindings_current(selected)
    data[4].write_text(data[4].read_text()+'\n; real Source edit\n')
    assert not leaf.bindings_current(selected)
