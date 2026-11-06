"""Fresh canonical ceramic intent, actual copper paths and exact saved replay.

Only the pre-existing aggregate current domain is fixture-stubbed. Source
hierarchy exports, assignment, geometry, partitions and saved deltas are real.
"""
import copy
import json
import re
import time
import uuid

import cec_swig_guard
cec_swig_guard.pin()
import wx
_QUIET = wx.LogNull()
import pcbnew
import pytest

import cec_source_aggregate_capacitor_cell as op
from test_detached_ordinary_passive_translation import fixture as passive_fixture
from test_field_proposals import track


def fixture(tmp_path, monkeypatch, quarter=0, back=False, kind='C'):
    source, root, uid = passive_fixture(tmp_path, quarter, back)
    text = root.read_text().replace('fixture:R_0402', 'Capacitor_SMD:C_0402_1005Metric')
    text = text.replace('fixture:R"', 'fixture:' + kind + '"')
    text = text.replace('"R_0_1"', '"' + kind + '_0_1"').replace('"R_1_1"', '"' + kind + '_1_1"')
    text = text.replace('RENAMED_R', 'RENAMED_C').replace('"100k"', '"100nF"')
    text = text.replace('0402WGF1003TCE', 'CL05B104KO5NNNC')
    text = text.replace('(label "BETA"', '(global_label "GND" (shape input)')
    text = text.replace('(property "MPN" "CL05B104KO5NNNC"',
        '(property "Manufacturer" "FIXTURE_VENDOR" (at 50 50 0) (effects (font (size 1 1))))\n'
        '(property "LCSC" "FIXTURE_LCSC" (at 50 50 0) (effects (font (size 1 1))))\n'
        '(property "MPN" "CL05B104KO5NNNC"')
    root.write_text(text)
    children = op.leaf.sch.SchFile(str(root)).children
    instance = next(b for tag, b in children if tag == 'symbol')
    peer = instance.replace('RENAMED_C', 'EXISTING_FEED').replace('(at 50 ', '(at 70 ')
    peer = re.sub(r'\(uuid "[^"]+"\)', lambda _: '(uuid "' + str(uuid.uuid4()) + '")', peer)
    text = '(kicad_sch\n' + '\n'.join(b for _, b in children) + '\n' + peer + '\n' + (
        '(label "ALPHA" (at 67.46 50 0) (effects (font (size 1 1))) (uuid "' + str(uuid.uuid4()) + '"))\n'
        '(global_label "GND" (shape input) (at 72.54 50 0) (effects (font (size 1 1))) (uuid "' + str(uuid.uuid4()) + '"))\n)')
    root.write_text(text)
    board = pcbnew.LoadBoard(str(source)); fp = next(iter(board.GetFootprints()))
    fp.SetReference('RENAMED_C'); fp.SetValue('100nF')
    fp.SetFPID(pcbnew.LIB_ID('Capacitor_SMD', 'C_0402_1005Metric'))
    for key, val in [('MPN', 'CL05B104KO5NNNC'), ('Manufacturer', 'FIXTURE_VENDOR'), ('LCSC', 'FIXTURE_LCSC')]:
        fp.SetField(key, val)
    gnd = pcbnew.NETINFO_ITEM(board, 'GND'); board.Add(gnd)
    fp.FindPadByNumber('2').SetNet(gnd)
    other = pcbnew.Cast_to_FOOTPRINT(fp.Duplicate(False)); other.m_Uuid.Clone(pcbnew.KIID()); other.SetReference('EXISTING_FEED')
    for p in other.Pads(): p.m_Uuid.Clone(pcbnew.KIID())
    board.Add(other); other.SetPosition(pcbnew.VECTOR2I_MM(16.5, 10))
    # Real canonical local supply owner plus a distinct already-local minimum
    # capacitor. Only aggregate-current authority remains fixture-stubbed.
    _locality_owner_fixture(board,root,back)
    properties = board.GetProperties()
    for key, val in op.fab.board_properties('jlcpcb_6l_pofv_signal').items(): properties[key] = val
    board.SetProperties(properties)
    for lid in (pcbnew.In1_Cu, pcbnew.In4_Cu):
        z = pcbnew.ZONE(board); z.SetLayer(lid); z.SetNet(gnd); z.SetLocalClearance(200000)
        poly = pcbnew.SHAPE_POLY_SET(); poly.NewOutline()
        for x, y in [(1, 1), (29, 1), (29, 29), (1, 29)]: poly.Append(x*1000000, y*1000000)
        z.Outline().Append(poly); board.Add(z)
    # Existing real Ground entry near the translated cell, not a new-hole credit.
    v = pcbnew.PCB_VIA(board); v.SetNet(gnd); v.SetPosition(pcbnew.VECTOR2I_MM(15.2, 14))
    v.SetWidth(600000); v.SetDrill(300000); v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); board.Add(v)
    op.additive._ground_refill(board); op.field._save_field_snapshot(board, source)
    authority = dict(source='board_design_basis', amps=.75, geometry_margin=1.25, margin_included=False)
    contract = dict(net='/ALPHA', current_authority=authority,
        routing_layers=['F.Cu', 'In2.Cu', 'In3.Cu', 'B.Cu'],
        required_by_layer_mm={'F.Cu': .5, 'In2.Cu': .845075, 'In3.Cu': .845075, 'B.Cu': .5})
    domain = dict(complete=True, source_refs=['EXISTING_FEED'], sink_refs=['RENAMED_C'], amps=.75)
    monkeypatch.setattr(op.full, '_model', lambda *args: ('aggregate_source_sink', copy.deepcopy(domain), copy.deepcopy(contract)))
    monkeypatch.setattr(op.cells, '_supply_current_widths', lambda *args:
        dict(current_authority=copy.deepcopy(authority), profile='jlcpcb_6l_pofv_signal',
             required_by_layer_nm={0: 500000, 6: 845075, 8: 845075, 2: 500000}, release_authority=False))
    return source, root, uid


def _locality_owner_fixture(board,root,back):
    ref='AMP73';uid=str(uuid.uuid4());root_uid=re.search(r'\(uuid "([^"]+)"',root.read_text()).group(1)
    names={'1':('OUT','output','LOCAL_OUT'),'2':('GND','power_in','GND'),
        '3':('IN+','input','LOCAL_HI'),'4':('IN-','input','LOCAL_LO'),
        '5':('GND','power_in','GND'),'6':('VS','power_in','ALPHA')}
    pins=[];labels=[]
    for n,(name,kind,net)in names.items():
        x=-2.54 if n=='6'else 2.54;y=0 if n=='6'else (int(n)-3)*2.54
        pins.append(f'(pin {kind} line (at {x} {y} 0) (length 1.27) (name "{name}" (effects (font (size 1 1)))) (number "{n}" (effects (font (size 1 1)))))')
        tag='global_label'if net=='GND'else'label';shape=' (shape input)'if tag=='global_label'else''
        labels.append(f'({tag} "{net}"{shape} (at {90+x} {50-y} 0) (effects (font (size 1 1))) (uuid "{uuid.uuid4()}"))')
    lib='(symbol "fixture:INA181" (property "Reference" "U" (at 0 0 0) (effects (font (size 1 1)))) (property "Value" "INA181" (at 0 0 0) (effects (font (size 1 1)))) (symbol "INA181_1_1" '+' '.join(pins)+'))'
    props={'Reference':ref,'Value':'INA181A2IDBVR','Footprint':'Package_TO_SOT_SMD:SOT-23-6',
        'MPN':'INA181A2IDBVR','Manufacturer':'Texas Instruments'}
    symbol=f'(symbol (lib_id "fixture:INA181") (at 90 50 0) (unit 1) (in_bom yes) (on_board yes) (dnp no) (uuid "{uid}") '+ ' '.join(f'(property "{k}" "{v}" (at 90 50 0) (effects (font (size 1 1))))'for k,v in props.items())+''.join(f'(pin "{n}" (uuid "{uuid.uuid4()}"))'for n in names)+f'(instances (project "canonical" (path "/{root_uid}" (reference "{ref}") (unit 1)))))'
    children=op.leaf.sch.SchFile(str(root)).children
    pieces=[]
    for tag,b in children:
        if tag=='lib_symbols':b=b[:-1]+lib+')'
        elif tag=='symbol'and op.leaf.sch.prop_value(b,'Reference')=='EXISTING_FEED':
            b=b[:-1]+'(property "BypassOwner" "AMP73.6" (at 70 50 0) (effects (font (size 1 1)))))'
        pieces.append(b)
    root.write_text('(kicad_sch\n'+'\n'.join(pieces+labels+[symbol])+'\n)')
    owner=pcbnew.FOOTPRINT(board);board.Add(owner);owner.SetReference(ref);owner.SetValue(props['Value'])
    owner.SetFPID(pcbnew.LIB_ID('Package_TO_SOT_SMD','SOT-23-6'));owner.SetPosition(pcbnew.VECTOR2I_MM(17,12))
    owner.SetField('Manufacturer',props['Manufacturer']);owner.SetField('MPN',props['MPN'])
    if back:owner.Flip(owner.GetPosition(),False)
    for n,(name,kind,net)in names.items():
        native='GND'if net=='GND'else'/'+net
        actual=board.FindNet(native)
        if actual is None:actual=pcbnew.NETINFO_ITEM(board,native);board.Add(actual)
        p=pcbnew.PAD(owner);owner.Add(p);p.SetNumber(n);p.SetNet(actual);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        mask=pcbnew.LSET();mask.AddLayer(pcbnew.B_Cu if back else pcbnew.F_Cu);p.SetLayerSet(mask)
        p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetSize(pcbnew.VECTOR2I_MM(.5,.6))
        p.SetPosition(pcbnew.VECTOR2I_MM(16,12)if n=='6'else pcbnew.VECTOR2I_MM(17.8,10+int(n)*.5))
    supply=board.FindFootprintByReference('EXISTING_FEED').FindPadByNumber('1')
    board.FindFootprintByReference('EXISTING_FEED').SetField('BypassOwner','AMP73.6')
    at=tuple(v/1e6 for v in supply.GetPosition());face=pcbnew.B_Cu if back else pcbnew.F_Cu
    track(board,'/ALPHA',at,(16,12),layer=face,width=.5)


def proposal(source, root, uid, **kwargs):
    original = pcbnew.LoadBoard(str(source)).FindFootprintByReference('RENAMED_C')
    return op.compile(source, footprint_uuid=uid, target_pose=[14, 14, original.GetOrientationDegrees()],
        board_hint=str(root), **kwargs)


def saved(tmp_path, monkeypatch):
    source, root, uid = fixture(tmp_path, monkeypatch)
    board, q = proposal(source, root, uid)
    # Canonical route approaches the supply land from the left; it does not
    # cross the adjacent Ground pad. Ground dogbone is immediately to the right.
    for a, b in [((13.5, 14), (15.5, 12)), ((15.5, 12), (16, 12))]:
        track(board, '/ALPHA', a, b, width=.5)
    track(board, 'GND', (14.5, 14), (15.2, 14), width=.2)
    child = op.force._copy_family(source, tmp_path/'child')
    op.additive._ground_refill(board); op.save_private(board, child, q)
    return source, child, q


@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('back', [False, True])
@pytest.mark.parametrize('kind', ['C', 'C_Small'])
def test_complete_fresh_canonical_request_is_renamed_and_rigid_frame_independent(tmp_path, monkeypatch, quarter, back, kind):
    source, root, uid = fixture(tmp_path, monkeypatch, quarter, back, kind)
    raw = source.read_bytes(); board, q = proposal(source, root, uid)
    assert q == json.loads(json.dumps(q)) and source.read_bytes() == raw
    assert q['canonical_source']['symbol_kind'] == kind
    assert q['unchanged_selected_bypass_assignments']['AMP73:6:100n']=='EXISTING_FEED'
    assert q['supply_request']['unchanged_full_rail_current_contract']['current_authority']['amps'] == .75
    assert q['native_supply_contact_contract']['required_by_layer_mm']['In2.Cu'] == .845075
    fp = board.FindFootprintByReference('RENAMED_C')
    assert fp.IsFlipped() == back and list(fp.GetPosition()) == [14000000, 14000000]
    assert not q['routing_admitted'] and not q['current_qualified'] and not q['release_authority']


def test_independent_saved_complete_supply_and_immediate_ground_paths(tmp_path, monkeypatch):
    source, child, q = saved(tmp_path, monkeypatch); originals = (source.read_bytes(), child.read_bytes())
    r = op.receive(source, child, q)
    assert r['ok'] and r['complete'], r
    assert r['actual_cell_paths']['actual_Ground_return_mm'] == pytest.approx(.7)
    assert r['native_partition_preservation']['preserved']
    assert r['all_Source_copper_retained_exactly']
    assert originals == (source.read_bytes(), child.read_bytes())
    assert not r['current_qualified'] and not r['routing_admitted'] and not r['release_authority']


def test_partial_overlap_same_net_ground_via_is_not_ordinary_dogbone(tmp_path, monkeypatch):
    source, root, uid = fixture(tmp_path, monkeypatch)
    board = pcbnew.LoadBoard(str(source))
    via = next(t for t in board.GetTracks()
               if t.GetClass() == 'PCB_VIA' and t.GetNetname() == 'GND')
    # Preserve the old invalid positive fixture as an explicit negative:
    # 0.9 mm land, 0.5 mm centre offset from the future Ground pad.
    via.SetPosition(pcbnew.VECTOR2I_MM(15,14)); via.SetWidth(900000); via.SetDrill(400000)
    op.additive._ground_refill(board); op.field._save_field_snapshot(board, source)
    _, q = proposal(source, root, uid)
    assert not q['pose_screen']['ok']
    conflicts = q['pose_screen']['surface']['conflicts']
    assert any(c['kind'] == 'same_net_via_pad_process'
               and c['reason'] == 'full via land is not contained by the SMD pad'
               for c in conflicts)


@pytest.mark.parametrize('fault', ['symbol', 'pin_type', 'mpn', 'manufacturer', 'lcsc', 'value', 'package', 'pin_net', 'missing_pin'])
def test_canonical_source_not_part_spelling_or_caller_assertion(tmp_path, monkeypatch, fault):
    source, root, uid = fixture(tmp_path, monkeypatch); text = root.read_text()
    if fault == 'symbol': text = text.replace('fixture:C"', 'fixture:R"')
    elif fault == 'pin_type': text = text.replace('(pin passive line', '(pin power_in line', 1)
    elif fault == 'mpn': text = text.replace('CL05B104KO5NNNC', 'UNKNOWN')
    elif fault == 'manufacturer': text = text.replace('FIXTURE_VENDOR', 'UNKNOWN')
    elif fault == 'lcsc': text = text.replace('FIXTURE_LCSC', 'UNKNOWN')
    elif fault == 'value': text = text.replace('"100nF"', '"47nF"')
    elif fault == 'package': text = text.replace('Capacitor_SMD:C_0402_1005Metric', 'fixture:OTHER')
    elif fault == 'pin_net': text = text.replace('"ALPHA"', '"OTHER"')
    else: text = text.replace('(number "2"', '(number "3"', 1)
    root.write_text(text)
    with pytest.raises(ValueError): proposal(source, root, uid)


@pytest.mark.parametrize('fault', ['dnp', 'locked', 'group', 'pad_group', 'hole', 'copper_field', 'same_net', 'lands_overlap', 'source_supply_contact'])
def test_actual_source_owner_and_detachment_cannot_be_granted_by_request(tmp_path, monkeypatch, fault):
    source, root, uid = fixture(tmp_path, monkeypatch)
    board = pcbnew.LoadBoard(str(source)); fp = board.FindFootprintByReference('RENAMED_C'); p = fp.FindPadByNumber('1')
    if fault == 'dnp': fp.SetDNP(True)
    elif fault == 'locked': fp.SetLocked(True)
    elif fault in ('group', 'pad_group'):
        g = pcbnew.PCB_GROUP(board); board.Add(g); g.AddItem(fp if fault == 'group' else p)
    elif fault == 'hole':
        p.SetAttribute(pcbnew.PAD_ATTRIB_PTH); p.SetLayerSet(pcbnew.LSET.AllCuMask())
        p.SetDrillSize(pcbnew.VECTOR2I_MM(.2, .2))
    elif fault == 'copper_field': fp.Reference().SetLayer(pcbnew.F_Cu)
    elif fault == 'same_net': p.SetNet(fp.FindPadByNumber('2').GetNet())
    elif fault == 'lands_overlap': p.SetPosition(fp.FindPadByNumber('2').GetPosition())
    else: track(board, '/ALPHA', (9.5, 10), (8.5, 10), width=.5)
    op.field._save_field_snapshot(board, source)
    with pytest.raises(ValueError): proposal(source, root, uid)


@pytest.mark.parametrize('fault', ['explicit_owner', 'assigned', 'missing_rail'])
def test_existing_bypass_owner_or_unresolved_same_rail_intent_is_not_reclassified(tmp_path, monkeypatch, fault):
    source, root, uid = fixture(tmp_path, monkeypatch)
    if fault == 'explicit_owner':
        b = pcbnew.LoadBoard(str(source)); b.FindFootprintByReference('RENAMED_C').SetField('BypassOwner', 'U7.1')
        op.field._save_field_snapshot(b, source)
    else:
        assigned = {'req': {'cap_ref': 'RENAMED_C'}} if fault == 'assigned' else {}
        missing = [{'rail': '/ALPHA'}] if fault == 'missing_rail' else []
        actual=op.constraints._device_bypass_assignment(pcbnew.LoadBoard(str(source)))
        monkeypatch.setattr(op.constraints, '_device_bypass_assignment', lambda *a, **k: dict(actual,assigned=assigned, missing=missing))
    with pytest.raises(ValueError, match='bypass'): proposal(source, root, uid)


@pytest.mark.parametrize('fault', ['below_source_width', 'noncanonical', 'mask', 'unrelated_new_material', 'part', 'source_track', 'proposal_current', 'rules'])
def test_saved_receiver_rejects_thin_or_unowned_material_and_changed_authority(tmp_path, monkeypatch, fault):
    source, child, q = saved(tmp_path, monkeypatch)
    if fault == 'proposal_current': q['aggregate_contract']['current_authority']['amps'] = .1
    elif fault == 'rules':
        project = json.loads(child.with_suffix('.kicad_pro').read_text())
        project['net_settings']['classes'][0]['clearance'] = .3
        child.with_suffix('.kicad_pro').write_text(json.dumps(project))
    else:
        board = pcbnew.LoadBoard(str(child)); source_ids = {op.force._uid(t) for t in pcbnew.LoadBoard(str(source)).GetTracks()}
        new = next(t for t in board.GetTracks() if t.GetNetname() == '/ALPHA' and op.force._uid(t) not in source_ids)
        if fault == 'below_source_width': new.SetWidth(499999)
        elif fault == 'noncanonical': new.SetEnd(new.GetEnd() + pcbnew.VECTOR2I(1, 0))
        elif fault == 'mask': new.SetHasSolderMask(True)
        elif fault == 'unrelated_new_material': track(board, 'GND', (25, 25), (26, 25))
        elif fault == 'part': board.FindFootprintByReference('RENAMED_C').SetValue('47nF')
        else: next(t for t in board.GetTracks() if op.force._uid(t) in source_ids).Move(pcbnew.VECTOR2I(1, 0))
        op.field._save_field_snapshot(board, child)
    r = op.receive(source, child, q)
    assert not r['ok'] and not r['complete'] and r['errors'], (fault, r)


@pytest.mark.parametrize('updates', [{'max_shift_mm': True}, {'max_shift_mm': 128.000001}, {'timeout_s': 11},
    {'timeout_s': float('nan')}, {'target_pose': [True, 14, 0]}, {'target_pose': [14, 14, 90]},
    {'target_pose': [10, 10, 0]}, {'supply_contact': {'native_uuids': ['fake'], 'at_nm': [1, 2], 'layers': [0]}}])
def test_finite_constructor_bounds_and_literal_current_port_required(tmp_path, monkeypatch, updates):
    source, root, uid = fixture(tmp_path, monkeypatch)
    kwargs = dict(footprint_uuid=uid, target_pose=[14, 14, 0], board_hint=str(root)); kwargs.update(updates)
    with pytest.raises(ValueError): op.compile(source, **kwargs)


def test_partial_or_distributed_model_is_not_aggregate_capacitor_authority(tmp_path, monkeypatch):
    source, root, uid = fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(op.full, '_model', lambda *args: ('explicit_all_terminal_distributed_supply', None, {}))
    with pytest.raises(ValueError, match='aggregate'): proposal(source, root, uid)


@pytest.mark.parametrize('back', [False, True])
@pytest.mark.parametrize('fault', [None, 'thin', 'changed_current', 'wrong_ground_face'])
def test_long_translation_is_not_long_routing_or_relaxed_saved_authority(tmp_path, monkeypatch, back, fault):
    source, root, uid = fixture(tmp_path, monkeypatch, back=back)
    board = pcbnew.LoadBoard(str(source))
    feed=board.FindFootprintByReference('EXISTING_FEED');feed.SetPosition(pcbnew.VECTOR2I_MM(48,10))
    board.FindFootprintByReference('AMP73').Move(pcbnew.VECTOR2I_MM(34,0))
    from cec_native_items import discard_items
    discard_items(board,[t for t in board.GetTracks()if t.GetNetname()=='/ALPHA'])
    at=tuple(v/1e6 for v in feed.FindPadByNumber('1').GetPosition());face=pcbnew.B_Cu if back else pcbnew.F_Cu
    track(board,'/ALPHA',at,(at[0]+2,12),layer=face,width=.5)
    track(board,'/ALPHA',(at[0]+2,12),(50,12),layer=face,width=.5)
    for edge in board.GetDrawings():
        if edge.GetLayer() != pcbnew.Edge_Cuts:
            continue
        for get, put in ((edge.GetStart, edge.SetStart), (edge.GetEnd, edge.SetEnd)):
            at = get()
            put(pcbnew.VECTOR2I(80000000 if at.x == 30000000 else at.x,
                              80000000 if at.y == 30000000 else at.y))
    for zone in board.Zones():
        outline = pcbnew.SHAPE_POLY_SET(); outline.NewOutline()
        for x, y in [(1, 1), (79, 1), (79, 79), (1, 79)]:
            outline.Append(x*1000000, y*1000000)
        zone.Outline().RemoveAllContours(); zone.Outline().Append(outline)
    ground = board.FindNet('GND')
    via = pcbnew.PCB_VIA(board); via.SetNet(ground)
    return_x = 48.8 if back else 51.2
    via.SetPosition(pcbnew.VECTOR2I_MM(return_x, 14)); via.SetWidth(600000); via.SetDrill(300000)
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); board.Add(via)
    op.additive._ground_refill(board); op.field._save_field_snapshot(board, source)
    raw_source = source.read_bytes()
    pose = [50, 14, board.FindFootprintByReference('RENAMED_C').GetOrientationDegrees()]
    # Existing local requests do not silently become broad placement requests.
    with pytest.raises(ValueError, match='bounded_nonzero_capacitor_translation_only'):
        op.compile(source, footprint_uuid=uid, target_pose=pose, board_hint=str(root), max_shift_mm=32)
    board, q = op.compile(source, footprint_uuid=uid, target_pose=pose,
        board_hint=str(root), max_shift_mm=64)
    assert q['pose_screen']['ok'] and q['request']['max_shift_mm'] == 64
    face = pcbnew.B_Cu if back else pcbnew.F_Cu
    # Only a short full-width rail connection is added, although the part
    # moved over forty millimetres. No long path/work budget was enlarged.
    points = ([(50.5,14),(50,13.5),(50,12)] if back
              else [(49.5,14),(50,13.5),(50,12)])
    added = [track(board, '/ALPHA', a, b, layer=face, width=.5)
             for a, b in zip(points, points[1:])]
    ground_at = tuple(board.FindFootprintByReference('RENAMED_C').FindPadByNumber('2').GetPosition())
    return_track = track(board, 'GND', tuple(v/1e6 for v in ground_at), (return_x, 14), layer=face, width=.2)
    if fault == 'thin':
        added[0].SetWidth(499999)
    elif fault == 'wrong_ground_face':
        return_track.SetLayer(pcbnew.F_Cu if back else pcbnew.B_Cu)
    child = op.force._copy_family(source, tmp_path/'long-child')
    op.additive._ground_refill(board); op.save_private(board, child, q)
    if fault == 'changed_current':
        q['aggregate_contract']['current_authority']['amps'] = .1
    received = op.receive(source, child, q)
    assert source.read_bytes() == raw_source
    if fault is None:
        assert received['ok'] and received['complete'], received['errors']
        assert received['actual_cell_paths']['actual_Ground_return_mm'] == pytest.approx(.7)
        assert received['all_Source_copper_retained_exactly']
    else:
        assert not received['ok'] and not received['complete'] and received['errors']
    assert op.MAX_NEW_LENGTH_NM == 32000000
    assert not received['routing_admitted'] and not received['current_qualified']


def virtual_flag(root, *, source_type='PWR_FLAG', reference='PWR5432'):
    """A real embedded one-pin power symbol and actual global Ground join."""
    children = op.leaf.sch.SchFile(str(root)).children
    libs = next(b for tag, b in children if tag == 'lib_symbols')
    declaration = ('(symbol "power:' + source_type + '" (power) (in_bom yes) (on_board yes) '
        '(property "Reference" "PWR" (at 0 0 0) (effects (font (size 1 1)))) '
        '(property "Value" "' + source_type + '" (at 0 0 0) (effects (font (size 1 1)))) '
        '(symbol "' + source_type + '_1_1" '
        '(pin power_out line (at 0 0 0) (length 0) '
        '(name "pwr" (effects (font (size 1 1)))) (number "1" (effects (font (size 1 1)))))))')
    libs = libs[:-1] + declaration + ')'
    root_uid = next(b for tag, b in children if tag == 'uuid').split('"')[1]
    instance = ('(symbol (lib_id "power:' + source_type + '") (at 50 70 0) (unit 1) '
        '(in_bom yes) (on_board yes) (dnp no) (uuid "' + str(uuid.uuid4()) + '") '
        '(property "Reference" "' + reference + '" (at 50 70 0) (effects (font (size 1 1)))) '
        '(property "Value" "' + source_type + '" (at 50 70 0) (effects (font (size 1 1)))) '
        '(pin "1" (uuid "' + str(uuid.uuid4()) + '")) '
        '(instances (project "canonical" (path "/' + root_uid + '" (reference "' + reference + '") (unit 1)))))')
    label = ('(global_label "GND" (shape input) (at 50 70 0) '
        '(effects (font (size 1 1))) (uuid "' + str(uuid.uuid4()) + '"))')
    root.write_text('(kicad_sch ' + ' '.join(libs if tag == 'lib_symbols' else b for tag, b in children)
        + instance + label + ')')


def test_positive_canonical_nonphysical_ground_flag_has_no_phantom_board_requirement(tmp_path, monkeypatch):
    source, root, uid = fixture(tmp_path, monkeypatch); virtual_flag(root)
    _, q = proposal(source, root, uid)
    proof, = q['canonical_source']['complete_net_membership']['GND']['nonphysical_canonical_Ground_symbols']
    assert proof['ref'] == 'PWR5432' and proof['nonphysical_power_symbol']
    assert proof['physical_footprint_absent'] and proof['mpn_absent']


@pytest.mark.parametrize('fault', ['missing_physical_Ground', 'unknown_extra_Ground', 'power_name_only'])
def test_ground_exceptions_require_positive_actual_canonical_roles(tmp_path, monkeypatch, fault):
    source, root, uid = fixture(tmp_path, monkeypatch)
    if fault == 'power_name_only': virtual_flag(root, source_type='UNKNOWN', reference='PWR5432')
    else:
        b = pcbnew.LoadBoard(str(source))
        if fault == 'missing_physical_Ground':
            peer = b.FindFootprintByReference('EXISTING_FEED'); peer.Remove(peer.FindPadByNumber('2'))
        else:
            peer = pcbnew.FOOTPRINT(b); b.Add(peer); peer.SetReference('H999')
            p = pcbnew.PAD(peer); peer.Add(p); p.SetNumber('1'); p.SetNet(b.FindNet('GND'))
            p.SetAttribute(pcbnew.PAD_ATTRIB_SMD); p.SetLayerSet(pcbnew.PAD.SMDMask())
            p.SetShape(pcbnew.PAD_SHAPE_RECT); p.SetSize(pcbnew.VECTOR2I_MM(.5, .5))
            p.SetPosition(pcbnew.VECTOR2I_MM(25, 25))
        op.field._save_field_snapshot(b, source)
    with pytest.raises(ValueError): proposal(source, root, uid)


def test_export_clock_has_no_semantic_authority_but_source_epoch_does(tmp_path, monkeypatch):
    source, root, uid = fixture(tmp_path, monkeypatch)
    _, first = proposal(source, root, uid)
    real = op.leaf._export
    def export(*args):
        tree, witness = real(*args); witness['netlist_sha256'] = 'f'*64
        return tree, witness
    monkeypatch.setattr(op.leaf, '_export', export)
    _, second = proposal(source, root, uid)
    assert first == second
    root.write_text(root.read_text() + '\n')
    _, third = proposal(source, root, uid)
    assert first['canonical_source'] != third['canonical_source']


@pytest.mark.parametrize('kind', ['source_aggregate_capacitor_cell', 'source_rc_elbow_reflow'])
@pytest.mark.parametrize('extra', ['width_nm', 'current_authority', 'timeout_s', 'allow_power', 'source_role', 'skip_native'])
def test_typed_phase_schema_accepts_no_caller_permission_override(kind, extra):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'build'))
    import root_receive_local_transaction_20261022 as driver
    row = dict(kind=kind, candidate='/private/board.kicad_pcb', candidate_sha256='a'*64)
    if kind == 'source_aggregate_capacitor_cell': row['proposal'] = '/private/proposal.json'
    else: row.update(pad_uuid='land', span_uuids=['one', 'two', 'three'])
    assert driver.validate_phases([row]) == [kind]
    row[extra] = True
    with pytest.raises(ValueError, match='schema'): driver.validate_phases([row])


@pytest.mark.parametrize('fault', ['duplicate', 'partial', 'nonstring', 'repeated_phase'])
def test_typed_RC_elbow_phase_has_exact_three_nonrepeated_source_identities(fault):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'build'))
    import root_receive_local_transaction_20261022 as driver
    row = dict(kind='source_rc_elbow_reflow', candidate='/private/board.kicad_pcb',
        candidate_sha256='a'*64, pad_uuid='land', span_uuids=['one', 'two', 'three'])
    if fault == 'duplicate': row['span_uuids'] = ['one']*3
    elif fault == 'partial': row['span_uuids'] = ['one', 'two']
    elif fault == 'nonstring': row['pad_uuid'] = 1
    phases = [row, copy.deepcopy(row)] if fault == 'repeated_phase' else [row]
    with pytest.raises(ValueError): driver.validate_phases(phases)
