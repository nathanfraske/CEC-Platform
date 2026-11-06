"""Synthetic role transitions, not canonical/current or routing certificates.

Native UUIDs, poses, parts and saved-file replay are real. Hierarchy/current
and assignment observations are isolated unit-test providers below.
"""
import copy
import json
import math

import pcbnew
import pytest
import cec_force_current as force
import cec_missing_bypass_repair as op


@pytest.fixture
def setup(tmp_path, monkeypatch):
    b = pcbnew.BOARD()
    nets = {}
    for name in ('GND', 'VCC'):
        n = pcbnew.NETINFO_ITEM(b, name); b.Add(n); nets[name] = n
    def fp(ref, at, pads):
        f = pcbnew.FOOTPRINT(b); f.SetReference(ref)
        f.SetFPID(pcbnew.LIB_ID('Capacitor_SMD', 'C_0805_2012Metric'))
        f.SetValue('10uF'); b.Add(f)
        for num, net in pads:
            p = pcbnew.PAD(f); p.SetNumber(num); p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            p.SetShape(pcbnew.PAD_SHAPE_RECT); p.SetSize(pcbnew.VECTOR2I(600000,600000))
            layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu)
            p.SetLayerSet(layers); p.SetNet(nets[net]); f.Add(p)
            p.SetPosition(pcbnew.VECTOR2I(*at))
        f.SetPosition(pcbnew.VECTOR2I(*at))
        # SetPosition moved existing pads too; align them explicitly.
        for p in f.Pads(): p.SetPosition(pcbnew.VECTOR2I(*at))
        return f
    owner = fp('U1', (10000000,10000000), [('1','VCC')])
    cap = fp('C1', (14000000,10000000), [('1','VCC'),('2','GND')])
    source = tmp_path/'board.kicad_pcb'; pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(source),b)
    req = dict(id='U1:1:local-ceramic', ref='U1', pin='1', rail='VCC', kind='local-ceramic',
        return_rail='GND', return_pin=None, max_mm=3.5, source='synthetic-unit-test')
    def assignment(board, hint):
        f = board.FindFootprintByReference('C1'); p = board.FindFootprintByReference('U1').FindPadByNumber('1')
        d = math.dist(tuple(f.FindPadByNumber('1').GetPosition()),tuple(p.GetPosition()))/1e6
        r = dict(req, pad=p)
        return dict(requirements=[r], assigned={r['id']:dict(requirement=r,cap_ref='C1',distance_mm=d)}
            if d<=3.5 else {}, missing=[] if d<=3.5 else [dict(r,nearest_ref='C1',nearest_mm=d)])
    monkeypatch.setattr(op,'_assignment',assignment)
    monkeypatch.setattr(op,'_canonical',lambda *_a:dict(synthetic_only=True,
        exporter=dict(netlist_semantic_policy='full-export-tree-except-single-generated-design-date-v1',
            netlist_semantic_sha256='1'*64,netlist_sha256='2'*64,exporter_sha256='3'*64)))
    # Match real native layer-ID keys; saved plans must survive JSON replay.
    monkeypatch.setattr(op,'_current',lambda *_a:dict(required_by_layer_nm={0:200000,2:300000}))
    monkeypatch.setattr(force,'_family',lambda *_a:dict(synthetic=True))
    monkeypatch.setattr(force,'_code_identity',lambda:dict(synthetic=True))
    intent = dict(source_sha256=force._hash(source),requirement_id=req['id'],
        capacitor_uuid=force._uid(cap),owner_pad_uuid=force._uid(next(iter(owner.Pads()))))
    return source,intent,req,assignment


def child(source, tmp_path, x=13, move_owner=False):
    b=pcbnew.LoadBoard(str(source)); f=b.FindFootprintByReference('C1')
    f.Move(pcbnew.VECTOR2I(round((x-14)*1e6),0))
    if move_owner: b.FindFootprintByReference('U1').Move(pcbnew.VECTOR2I(1,0))
    path=tmp_path/'child.kicad_pcb';pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(path),b)
    return path


def test_positive_role_is_nonadmitting_and_source_unchanged(setup,tmp_path):
    source,intent,*_=setup; saved=source.read_bytes()
    proposal=op.plan(source,intent,board_hint='synthetic')
    result=op.receive(source,child(source,tmp_path),json.loads(json.dumps(proposal)),board_hint='synthetic')
    assert result['ok'] and result['candidate_distance_mm']==3
    assert all(result[k] is False for k in ('admitted','cut_authority','route_authority',
        'current_authority','physical_connectivity_proved'))
    assert {p['net']for p in proposal['source_capacitor_ports']}=={'VCC','GND'}
    assert proposal['unchanged_source_current_contract']['required_by_layer_nm']=={'0':200000,'2':300000}
    assert source.read_bytes()==saved


@pytest.mark.parametrize('quarter',range(4))
def test_selected_cap_cardinal_rotation_does_not_move_owner(setup,tmp_path,quarter):
    source,intent,*_=setup;proposal=op.plan(source,intent,board_hint='synthetic')
    path=child(source,tmp_path);b=pcbnew.LoadBoard(str(path))
    b.FindFootprintByReference('C1').SetOrientationDegrees(90*quarter)
    pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(path),b)
    assert op.receive(source,path,proposal,board_hint='synthetic')['ok']


@pytest.mark.parametrize('key,value',[('source_sha256','bad'),('requirement_id','wrong'),
    ('capacitor_uuid','wrong'),('owner_pad_uuid','wrong')])
def test_intent_cannot_select_different_source_identity(setup,key,value):
    source,intent,*_=setup;intent[key]=value
    with pytest.raises(ValueError):op.plan(source,intent,board_hint='synthetic')


@pytest.mark.parametrize('fault',['contention','assigned','competing','nearest','tie'])
def test_no_contention_stealing_or_ambiguous_owner(setup,monkeypatch,fault):
    source,intent,req,assignment=setup
    def bad(board,hint):
        r=assignment(board,hint)
        if fault=='contention':r['missing'][0]['nearest_mm']=3
        elif fault=='assigned':r['assigned']['other']=dict(cap_ref='C1',requirement=dict(req,id='other'))
        elif fault=='competing':r['requirements'].append(dict(req,id='other',ref='U2'))
        elif fault=='nearest':r['missing'][0]['nearest_ref']='C2'
        elif fault=='tie':
            other=pcbnew.FOOTPRINT(board.FindFootprintByReference('C1'));other.SetReference('C2');board.Add(other)
        return r
    monkeypatch.setattr(op,'_assignment',bad)
    with pytest.raises(ValueError):op.plan(source,intent,board_hint='synthetic')


@pytest.mark.parametrize('fault',['bound','owner','parts','intent','current','assignment','missing'])
def test_candidate_must_repair_only_intended_role(setup,tmp_path,monkeypatch,fault):
    source,intent,req,assignment=setup;proposal=op.plan(source,intent,board_hint='synthetic')
    target=child(source,tmp_path,x=14 if fault=='bound' else 13,move_owner=fault=='owner')
    if fault=='parts':
        b=pcbnew.LoadBoard(str(target));b.FindFootprintByReference('C1').SetValue('1uF')
        pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(target),b)
    if fault=='intent':proposal['requirement']['max_mm']=4
    if fault=='current':
        old=op._current
        monkeypatch.setattr(op,'_current',lambda b,r,h:old(b,r,h)if b.GetFileName()==str(source)else{'changed':True})
    if fault in ('assignment','missing'):
        def bad(board,hint):
            r=assignment(board,hint)
            if board.GetFileName()==str(target):
                if fault=='assignment':r['assigned'][req['id']]['cap_ref']='C2'
                else:r['missing'].append(dict(req,id='new'))
            return r
        monkeypatch.setattr(op,'_assignment',bad)
    with pytest.raises(ValueError):op.receive(source,target,proposal,board_hint='synthetic')


@pytest.mark.parametrize('value',[True,0,-1,11,float('nan')])
def test_bounded_lease(setup,value):
    source,intent,*_=setup
    with pytest.raises(ValueError):op.plan(source,intent,board_hint='synthetic',timeout_s=value)


def test_fresh_generated_export_date_does_not_invalidate_saved_role(setup,tmp_path,monkeypatch):
    source,intent,*_=setup;proposal=op.plan(source,intent,board_hint='synthetic')
    canonical=copy.deepcopy(proposal['canonical'])
    canonical['exporter']['netlist_sha256']='4'*64
    monkeypatch.setattr(op,'_canonical',lambda *_a:canonical)
    assert op.receive(source,child(source,tmp_path),proposal,board_hint='synthetic')['ok']


@pytest.mark.parametrize('key',['netlist_semantic_sha256','exporter_sha256',
    'netlist_semantic_policy'])
def test_semantic_source_or_exporter_drift_is_still_refused(setup,tmp_path,monkeypatch,key):
    source,intent,*_=setup;proposal=op.plan(source,intent,board_hint='synthetic')
    canonical=copy.deepcopy(proposal['canonical'])
    canonical['exporter'][key]='4'*64
    monkeypatch.setattr(op,'_canonical',lambda *_a:canonical)
    with pytest.raises(ValueError):
        op.receive(source,child(source,tmp_path),proposal,board_hint='synthetic')
