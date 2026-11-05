"""Native regressions for Source-selected cap Ground boundary ownership.

Canonical KiCad schematic export, manufacturer roles and real native copper
execute normally. Only the explicitly synthetic full-rail current catalog is
fixture-stubbed; it supplies no current authority to real project boards.
"""
import copy
import json
from pathlib import Path
import time
import uuid

import cec_swig_guard
cec_swig_guard.pin()
import wx
_QUIET = wx.LogNull()
import pcbnew
import pytest

import cec_selected_cap_ground_boundary as draft
from cec_native_items import discard_items
from test_field_proposals import track


def fixture(tmp_path, monkeypatch, quarter=0, reflected=False, group=False, with_via=True,
            contact_case='both'):
    board = pcbnew.BOARD(); board.SetCopperLayerCount(6)
    owner_ref = 'U738'; cap_ref = 'C847'
    nets = {}
    def net(name):
        if name not in nets:
            nets[name] = pcbnew.NETINFO_ITEM(board, name); board.Add(nets[name])
        return nets[name]
    def footprint(ref, value, mpn, package, at):
        fp = pcbnew.FOOTPRINT(board); board.Add(fp); fp.SetReference(ref); fp.SetValue(value)
        fp.SetFPID(pcbnew.LIB_ID(*package.split(':'))); fp.SetField('MPN', mpn)
        fp.SetField('Manufacturer', 'Texas Instruments' if ref == owner_ref else 'FIXTURE_VENDOR')
        fp.SetPosition(pcbnew.VECTOR2I_MM(*at))
        return fp
    def pad(fp, number, name, at, size):
        p = pcbnew.PAD(fp); fp.Add(p); p.SetNumber(number); p.SetNet(net(name))
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD); p.SetShape(pcbnew.PAD_SHAPE_RECT)
        p.SetSize(pcbnew.VECTOR2I_MM(*size)); p.SetLayerSet(pcbnew.PAD.SMDMask())
        p.SetPosition(pcbnew.VECTOR2I_MM(*at)); return p
    cap = footprint(cap_ref, '10uF', 'CL05A106MQ5NUNC',
        'Capacitor_SMD:C_0402_1005Metric', (10., 10.))
    cap.SetField('BypassOwner', owner_ref + '.2')
    cp = pad(cap, '1', '/RAIL', (9.5, 10), (.7, 1.))
    cg = pad(cap, '2', 'GND', (11.15, 9.2) if contact_case == 'control_only' else (10.5, 10), (1., 1.))
    owner = footprint(owner_ref, 'TPS2121RUXR', 'TPS2121RUXR',
        'Package_DFN_QFN:VQFN-HR-12_2.5x2.5mm_P0.5mm', (12., 11.))
    names = {'1': ('OUT', 'power_out', '/OUT'), '2': ('IN2', 'power_in', '/RAIL'),
        '3': ('PR1', 'input', 'GND'), '4': ('CP2', 'input', 'GND'),
        '5': ('OV2', 'input', '/OV2'), '6': ('OV1', 'input', '/OV1'),
        '7': ('IN1', 'power_in', '/OTHER'), '8': ('OUT', 'power_out', '/OUT'),
        '9': ('ST', 'output', '/STATUS'), '10': ('SS', 'input', '/SS'),
        '11': ('ILIM', 'input', '/ILIM'), '12': ('GND', 'power_in', 'GND')}
    for n, (_, _, name) in names.items():
        at = {'2': (11, 8), '3': (10.95, 10.8), '4': (11.35, 10.8),
            '12': (13.5, 10.8)}.get(n, (16.+int(n), 16.))
        if contact_case == 'body_only' and n in ('3','4'): at = (20.+int(n), 15.)
        pad(owner, n, name, at, (.2, .6))
    # Both ends outside the capacitor land; positive native body overlap.
    owned = track(board, 'GND', (11.15, 9.2), (11.15, 10.8), width=.5)
    trunk = track(board, 'GND', (11.15, 9.2), (12., 8.35), width=.5)
    thin = [track(board, 'GND', (10.95, 10.8), (11.15, 10.8), width=.2),
        track(board, 'GND', (11.15, 10.8), (11.35, 10.8), width=.2)]
    via = None
    if with_via:
        via = pcbnew.PCB_VIA(board); board.Add(via); via.SetNet(net('GND'))
        via.SetPosition(pcbnew.VECTOR2I_MM(10.85, 10)); via.SetWidth(900000); via.SetDrill(500000)
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    for fp in (cap, owner):
        # Every whole native fixture is transformed coherently; schematic
        # identity stays cardinal and unmirrored as in the real hierarchy.
        fp.Rotate(pcbnew.VECTOR2I_MM(20, 20), pcbnew.EDA_ANGLE(quarter*90, pcbnew.DEGREES_T))
        if reflected: fp.Flip(pcbnew.VECTOR2I_MM(20, 20), False)
    for t in board.GetTracks():
        t.Rotate(pcbnew.VECTOR2I_MM(20, 20), pcbnew.EDA_ANGLE(quarter*90, pcbnew.DEGREES_T))
        if reflected: t.Flip(pcbnew.VECTOR2I_MM(20, 20), False)
    for a, b in [((0, 0), (50, 0)), ((50, 0), (50, 50)), ((50, 50), (0, 50)), ((0, 50), (0, 0))]:
        e = pcbnew.PCB_SHAPE(board); e.SetShape(pcbnew.SHAPE_T_SEGMENT); e.SetLayer(pcbnew.Edge_Cuts)
        e.SetStart(pcbnew.VECTOR2I_MM(*a)); e.SetEnd(pcbnew.VECTOR2I_MM(*b)); e.SetWidth(50000); board.Add(e)
    groups = []
    if group:
        import cec_source_reference_group_transport as reference
        cap.Reference().SetVisible(False)
        pos = cap.GetPosition(); x, y = tuple(pos)
        face = pcbnew.B_CrtYd if reflected else pcbnew.F_CrtYd
        layer = pcbnew.F_SilkS if reflected else pcbnew.B_SilkS
        g = pcbnew.PCB_GROUP(board); board.Add(g); g.SetName(reference.PREFIX + cap_ref); g.SetLocked(True); g.AddItem(cap)
        text = pcbnew.PCB_TEXT(board); text.SetText(cap_ref); text.SetLayer(layer); text.SetMirrored(not reflected)
        text.SetTextSize(pcbnew.VECTOR2I_MM(.8, .8)); text.SetTextThickness(120000); text.SetTextPos(pos)
        text.SetKeepUpright(True); text.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER)
        text.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER); board.Add(text); g.AddItem(text)
        pts = [(x-4000000,y-2000000),(x+4000000,y-2000000),(x+4000000,y+2000000),(x-4000000,y+2000000)]
        for a, b in zip(pts, pts[1:]+pts[:1]):
            court = pcbnew.PCB_SHAPE(cap); court.SetShape(pcbnew.SHAPE_T_SEGMENT); court.SetLayer(face)
            court.SetStart(pcbnew.VECTOR2I(*a)); court.SetEnd(pcbnew.VECTOR2I(*b)); court.SetWidth(50000); cap.Add(court)
        actual = cap.GetCourtyard(cap.GetLayer()).COutline(0)
        pts = [tuple(actual.CPoint(i)) for i in range(actual.PointCount())]
        for a, b in zip(pts, pts[1:]+pts[:1]):
            line = pcbnew.PCB_SHAPE(board); line.SetShape(pcbnew.SHAPE_T_SEGMENT); line.SetLayer(layer)
            line.SetStart(pcbnew.VECTOR2I(*a)); line.SetEnd(pcbnew.VECTOR2I(*b)); line.SetWidth(120000); board.Add(line); g.AddItem(line)
        groups = [draft.force._uid(g)]
    root = tmp_path/'canonical.kicad_sch'; root_uid = str(uuid.uuid4())
    font = '(effects (font (size 1 1)))'
    libs = []; symbols = []; labels = []
    for index, fp in enumerate((cap, owner)):
        ref = fp.GetReference(); sx = 50+index*50; sy = 50
        libname = 'C' if fp == cap else 'TPS2121'
        pin_defs = ({'1': ('~', 'passive', '/RAIL'), '2': ('~', 'passive', 'GND')} if fp == cap else names)
        pins = []
        for n, (name, kind, wire) in pin_defs.items():
            px = -2.54 if int(n)%2 else 2.54; py = int(n)*2.54
            pins.append(f'(pin {kind} line (at {px} {py} 0) (length 1.27) (name "{name}" {font}) (number "{n}" {font}))')
            tag = 'global_label' if wire == 'GND' else 'label'; shape = ' (shape input)' if tag == 'global_label' else ''
            labels.append(f'({tag} "{wire.lstrip("/")}"{shape} (at {sx+px} {sy-py} 0) {font} (uuid "{uuid.uuid4()}"))')
        libs.append(f'(symbol "fixture:{libname}" (property "Reference" "{libname}" (at 0 0 0) {font}) (property "Value" "{libname}" (at 0 0 0) {font}) (symbol "{libname}_1_1" '+''.join(pins)+'))')
        props = {'Reference': ref, 'Value': fp.GetValue(), 'MPN': draft.canonical.footprint_properties(fp)['MPN'],
            'Footprint': fp.GetFPIDAsString(), 'Manufacturer': draft.canonical.footprint_properties(fp)['Manufacturer']}
        if fp == cap: props['BypassOwner'] = owner_ref+'.2'
        symbols.append(f'(symbol (lib_id "fixture:{libname}") (at {sx} {sy} 0) (unit 1) (in_bom yes) (on_board yes) (dnp no) (uuid "{uuid.uuid4()}") '+
            ''.join(f'(property "{k}" "{v}" (at {sx} {sy} 0) {font})' for k,v in props.items())+
            ''.join(f'(pin "{n}" (uuid "{uuid.uuid4()}"))' for n in pin_defs)+
            f'(instances (project "canonical" (path "/{root_uid}" (reference "{ref}") (unit 1)))))')
    root.write_text(f'(kicad_sch (version 20250114) (generator "eeschema") (uuid "{root_uid}") (paper "A4") (lib_symbols '+''.join(libs)+')'+''.join(labels+symbols)+')')
    path = tmp_path/'source.kicad_pcb'; pcbnew.SaveBoard(str(path), board)
    pro = path.with_suffix('.kicad_pro'); data = json.loads(pro.read_text())
    data['net_settings']['classes'][0].update(track_width=.5, clearance=.2, via_diameter=.9, via_drill=.5)
    pro.write_text(json.dumps(data))
    # Explicit synthetic FULL rail declaration, never a new Ground load.
    contract = dict(net='/RAIL', current_authority=dict(source='synthetic_fixture_only',
        amps=.75, geometry_margin=1.25, margin_included=False),
        required_by_layer_mm={'F.Cu': .5, 'B.Cu': .5}, routing_layers=['F.Cu','B.Cu'])
    monkeypatch.setattr(draft.full, '_model', lambda *args: ('aggregate_source_sink',
        dict(complete=True, source_refs=[owner_ref], sink_refs=[cap_ref], amps=.75), copy.deepcopy(contract)))
    source = pcbnew.LoadBoard(str(path)); posed = pcbnew.LoadBoard(str(path))
    poses = {fp.GetReference(): [v/1e6 for v in fp.GetPosition()]+[fp.GetOrientationDegrees()] for fp in source.GetFootprints()}
    proposal = draft.escape._prepare_source(source, poses, board_hint=str(root), reference_group_uuids=groups)
    ids = dict(edge=draft.force._uid(owned), trunk=draft.force._uid(trunk),
        thin=[draft.force._uid(t) for t in thin], cap=draft.force._uid(cg),
        controls=[draft.force._uid(owner.FindPadByNumber(n)) for n in ('3','4')],
        via=None if via is None else draft.force._uid(via))
    return source, posed, proposal, ids, root


def plan(source, proposal, ids):
    return draft.ownership(source, proposal, [ids['edge']], deadline=time.monotonic()+8.)


def reconstruct(source, candidate, ids):
    original = next(t for t in source.GetTracks() if draft.force._uid(t) == ids['edge'])
    a, b = original.GetStart(), original.GetEnd(); middle = pcbnew.VECTOR2I((a.x+b.x)//2,(a.y+b.y)//2)
    discard_items(candidate, [t for t in candidate.GetTracks() if draft.force._uid(t) == ids['edge']])
    for x, y in ((a,middle),(middle,b)):
        t = pcbnew.PCB_TRACK(candidate); t.SetNetCode(original.GetNetCode()); t.SetLayer(original.GetLayer())
        t.SetStart(x); t.SetEnd(y); t.SetWidth(original.GetWidth()); candidate.Add(t)




@pytest.mark.parametrize('contact_case', ['body_only', 'control_only'])
def test_two_actual_missing_scope_edges_are_independent(tmp_path, monkeypatch, contact_case):
    source, child, proposal, ids, root = fixture(tmp_path, monkeypatch, contact_case=contact_case)
    edge = draft._items(source)[ids['edge']]
    with pytest.raises(ValueError, match='not_owned' if contact_case == 'body_only' else 'unowned_land'):
        draft.macro._legacy_ground_boundary_authority(source,edge,{'source_process_barrel_motion':[]},proposal,time.monotonic()+8.)
    proof = plan(source,proposal,ids)['extras'][0]['authority']
    endpoints = proof['source_pad_roots'][0]['endpoint_inside']
    assert (not any(endpoints)) if contact_case == 'body_only' else any(endpoints)



def test_third_party_drill_cannot_invent_body_contact(tmp_path,monkeypatch):
    source, child, proposal, ids, root = fixture(tmp_path,monkeypatch,with_via=False)
    live=draft._items(source); edge=live[ids['edge']]; cap=live[ids['cap']]
    assert draft._positive_contact(source,edge,cap,edge.GetLayer(),time.monotonic()+8)>0
    fp=pcbnew.FOOTPRINT(source);source.Add(fp);fp.SetReference('MECHANICAL')
    hole=pcbnew.PAD(fp);fp.Add(hole);hole.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
    hole.SetShape(pcbnew.PAD_SHAPE_CIRCLE);hole.SetSize(pcbnew.VECTOR2I_MM(2,2))
    hole.SetDrillSize(pcbnew.VECTOR2I_MM(2,2));hole.SetLayerSet(pcbnew.LSET.AllCuMask())
    hole.SetPosition(pcbnew.VECTOR2I_MM(11.15,10))
    assert draft._positive_contact(source,edge,cap,edge.GetLayer(),time.monotonic()+8)==0


def test_native_tangency_is_not_positive_body_material(tmp_path,monkeypatch):
    source, child, proposal, ids, root = fixture(tmp_path,monkeypatch,with_via=False)
    live=draft._items(source); edge=live[ids['edge']]; cap=live[ids['cap']]
    edge.SetStart(pcbnew.VECTOR2I_MM(11.25,9.2));edge.SetEnd(pcbnew.VECTOR2I_MM(11.25,10.8))
    assert draft._positive_contact(source,edge,cap,pcbnew.F_Cu,time.monotonic()+8)==0



@pytest.mark.parametrize('fault', ['unknown_current', 'unknown_role', 'canonical_tie', 'unowned_trunk', 'thin_cut', 'class_change', 'grouped_cut', 'foreign_pad'])
def test_fresh_source_scope_refusals(tmp_path, monkeypatch, fault):
    source, child, proposal, ids, root = fixture(tmp_path, monkeypatch)
    if fault == 'unknown_current': monkeypatch.setattr(draft.full, '_model', lambda *a: ('unknown',{},{}))
    elif fault == 'unknown_role':
        original = draft.roles.footprint_contract
        def changed(fp):
            model = original(fp)
            if model: model['pins']['3'] = 'unknown'
            return model
        monkeypatch.setattr(draft.roles,'footprint_contract',changed)
    elif fault == 'canonical_tie': root.write_text(root.read_text().replace('(global_label "GND" (shape input) (at 97.46 42.38', '(global_label "NOT_GND" (shape input) (at 97.46 42.38'))
    elif fault == 'unowned_trunk': ids['edge'] = ids['trunk']
    elif fault == 'thin_cut': ids['edge'] = ids['thin'][0]
    else:
        obj = draft._items(source)[ids['edge']]
        if fault == 'class_change':
            pro = Path(source.GetFileName()).with_suffix('.kicad_pro'); data=json.loads(pro.read_text());data['net_settings']['classes'][0]['track_width']=.6;pro.write_text(json.dumps(data))
        elif fault == 'grouped_cut':
            g=pcbnew.PCB_GROUP(source);source.Add(g);g.AddItem(obj)
        else:
            p=source.FindFootprintByReference('U738').FindPadByNumber('5');p.SetPosition(obj.GetStart())
        # A native mutation not serialized to Source must already fail closed.
    with pytest.raises(ValueError): plan(source, proposal, ids)



@pytest.mark.parametrize('fault', ['expired', 'too_long', 'nan'])
def test_inherited_deadline_not_renewed(tmp_path, monkeypatch, fault):
    source, child, proposal, ids, root = fixture(tmp_path, monkeypatch)
    deadline = {'expired':time.monotonic()-1,'too_long':time.monotonic()+11,'nan':float('nan')}[fault]
    with pytest.raises(ValueError,match='bounded_lease'):
        draft.ownership(source, proposal, [ids['edge']], deadline=deadline)
