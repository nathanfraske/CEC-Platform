"""Real native leaf geometry with isolated synthetic canonical-role provider.

These tests are not source hierarchy/current or production admission proofs.
"""
import copy
import pcbnew
import pytest
import cec_force_current as force
import cec_measurement_leaf as leaf
import cec_missing_bypass_repair as repair
import cec_decoupler_cell as cells
import cec_source_netlist_semantics as semantics


@pytest.fixture
def setup(tmp_path,monkeypatch):
    b=pcbnew.BOARD();nets={}
    for name in ('VCC','GND'):
        n=pcbnew.NETINFO_ITEM(b,name);b.Add(n);nets[name]=n
    def pad(fp,pin,net,x,y):
        p=pcbnew.PAD(fp);p.SetNumber(pin);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetSize(pcbnew.VECTOR2I_MM(.5,.5))
        p.SetLayerSet(pcbnew.PAD.SMDMask());p.SetPosition(pcbnew.VECTOR2I_MM(x,y))
        p.SetNet(nets[net]);fp.Add(p);return p
    cap=pcbnew.FOOTPRINT(b);cap.SetReference('C1');cap.SetValue('10uF');b.Add(cap)
    supply=pad(cap,'1','VCC',10,10);ground=pad(cap,'2','GND',10,12)
    owner=pcbnew.FOOTPRINT(b);owner.SetReference('U1');b.Add(owner)
    op=pad(owner,'1','VCC',16,10)
    anchor=pcbnew.FOOTPRINT(b);anchor.SetReference('FIXED');b.Add(anchor)
    for net,y in [('VCC',10),('GND',12)]:
        pad(anchor,net,net,14,y)
        for a,z in [(10,12),(12,14)]:
            t=pcbnew.PCB_TRACK(b);t.SetStart(pcbnew.VECTOR2I_MM(a,y));t.SetEnd(pcbnew.VECTOR2I_MM(z,y))
            t.SetWidth(200000);t.SetLayer(pcbnew.F_Cu);t.SetNet(nets[net]);b.Add(t)
    path=tmp_path/'board.kicad_pcb';pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(path),b)
    b=pcbnew.LoadBoard(str(path));cap=b.FindFootprintByReference('C1')
    supply=cap.FindPadByNumber('1');ground=cap.FindPadByNumber('2')
    op=b.FindFootprintByReference('U1').FindPadByNumber('1')
    intent=dict(source_sha256=force._hash(path),requirement_id='U1:1:local-ceramic',
        capacitor_uuid=force._uid(cap),owner_pad_uuid=force._uid(op))
    proof=dict(scope=repair.SCOPE,complete=True,role_only=True,admitted=False,
        source=str(path),source_sha256=force._hash(path),intent=intent,
        requirement=dict(ref='U1',pin='1',rail='VCC'),source_owner_port=dict(at_nm=list(op.GetPosition())),
        source_capacitor_ports=[dict(uuid=force._uid(p),pin=p.GetNumber(),net=p.GetNetname(),
            at_nm=list(p.GetPosition()),layers=list(map(int,p.GetLayerSet().CuStack())))for p in cap.Pads()],
        cut_authority=False,route_authority=False,current_authority=False,
        canonical=dict(exporter=dict(netlist_sha256='a'*64,netlist_semantic_sha256='b'*64,
            netlist_semantic_policy=semantics.POLICY,exporter_sha256='c'*64,exporter='/synthetic/cli')))
    calls=[]
    def plan(source,incoming,**kw):
        calls.append((source,incoming,kw))
        if incoming!=intent:raise ValueError('synthetic_intent_mismatch')
        return copy.deepcopy(proof)
    monkeypatch.setattr(repair,'plan',plan)
    monkeypatch.setattr(cells,'_supply_current_widths',lambda *_a:{'required_by_layer_nm':{0:150000}})
    return b,supply,ground,intent,proof,calls


@pytest.mark.parametrize('ground_return',[False,True])
def test_missing_role_reuses_actual_exclusive_native_leaf(setup,ground_return):
    b,s,g,intent,proof,calls=setup;before=leaf._binding(b)
    fn=leaf.plan_missing_bypass_ground if ground_return else leaf.plan_missing_bypass_supply
    q=fn(b,force._uid(g if ground_return else s),board_hint='synthetic',missing_bypass_intent=intent)
    assert len(calls)==1 and q['source_missing_bypass_repair']==repair._replay_identity(proof)
    assert q['scope'].startswith('source_corrective_missing_bypass_')
    assert 'source_selected_bypass'not in q and q['device']=='source-corrective-missing-bypass'
    assert len(q['track_uuids'])==2 and len(q['boundary_uuids'])==1
    assert before==leaf._binding(b) and not q['current_authority']
    if not ground_return:assert q['unchanged_full_rail_current_contract']['required_by_layer_nm'][0]==150000


@pytest.mark.parametrize('fault',['intent','pad','owner','ram','proof','width','fork','current'])
def test_invalid_role_or_geometry_never_becomes_cut_permission(setup,monkeypatch,fault,tmp_path):
    b,s,g,intent,proof,calls=setup
    if fault=='intent':intent=dict(intent,owner_pad_uuid='wrong')
    if fault=='pad':s=g
    if fault=='owner':proof['source_owner_port']['at_nm']=[0,0]
    if fault=='proof':proof['cut_authority']=True
    if fault=='ram':b.FindFootprintByReference('U1').Move(pcbnew.VECTOR2I(1,0))
    if fault in('width','fork'):
        t=next(t for t in b.GetTracks()if t.GetNetname()=='VCC'and t.GetStart()==s.GetPosition())
        if fault=='width':t.SetWidth(400000)
        else:
            t=pcbnew.PCB_TRACK(b);t.SetNet(s.GetNet());t.SetLayer(pcbnew.F_Cu)
            t.SetWidth(200000);t.SetStart(pcbnew.VECTOR2I_MM(11,10));t.SetEnd(pcbnew.VECTOR2I_MM(11,11));b.Add(t)
        # Bind the changed source so geometry, not RAM-literal guard, refuses.
        path=b.GetFileName();pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(path,b)
        intent['source_sha256']=force._hash(path);proof['source_sha256']=force._hash(path)
    if fault=='current':monkeypatch.setattr(cells,'_supply_current_widths',lambda *_a:{'required_by_layer_nm':{0:300000}})
    with pytest.raises(ValueError):leaf.plan_missing_bypass_supply(b,force._uid(s),
        board_hint='synthetic',missing_bypass_intent=intent)


def test_intent_cannot_retype_ordinary_leaf(setup):
    b,s,g,intent,*_=setup
    with pytest.raises(ValueError,match='cannot_retype'):
        leaf._plan(b,force._uid(s),role='measurement',timeout_s=10,max_tracks=8,max_length_mm=8,
            missing_bypass_intent=intent)


def test_existing_selected_bypass_entrypoint_does_not_borrow_missing_role(setup,monkeypatch):
    b,s,g,intent,*_=setup
    monkeypatch.setattr(leaf,'_bypass_supply_owner',lambda *_a,**_k:(_ for _ in()).throw(ValueError('selected_only')))
    with pytest.raises(ValueError,match='selected_only'):
        leaf.plan_rated_bypass_supply(b,force._uid(s),board_hint='synthetic')


def test_raw_export_clock_drift_does_not_change_replayed_leaf(setup):
    b,s,g,intent,proof,calls=setup
    first=leaf.plan_missing_bypass_supply(b,force._uid(s),board_hint='synthetic',missing_bypass_intent=intent)
    proof['canonical']['exporter']['netlist_sha256']='d'*64
    second=leaf.plan_missing_bypass_supply(b,force._uid(s),board_hint='synthetic',missing_bypass_intent=intent)
    assert first==second
    assert 'netlist_sha256'not in second['source_missing_bypass_repair']['canonical']['exporter']
    assert proof['canonical']['exporter']['netlist_sha256']=='d'*64


@pytest.mark.parametrize('key,value',[('netlist_semantic_sha256','d'*64),
    ('exporter_sha256','d'*64),('exporter','/different/cli')])
def test_semantic_or_exporter_identity_drift_remains_in_leaf(setup,key,value):
    b,s,g,intent,proof,calls=setup
    first=leaf.plan_missing_bypass_supply(b,force._uid(s),board_hint='synthetic',missing_bypass_intent=intent)
    proof['canonical']['exporter'][key]=value
    second=leaf.plan_missing_bypass_supply(b,force._uid(s),board_hint='synthetic',missing_bypass_intent=intent)
    assert first!=second


def test_missing_semantic_export_identity_cannot_be_stripped(setup):
    b,s,g,intent,proof,calls=setup
    del proof['canonical']['exporter']['netlist_semantic_policy']
    with pytest.raises(ValueError,match='semantic_export_identity'):
        leaf.plan_missing_bypass_supply(b,force._uid(s),board_hint='synthetic',missing_bypass_intent=intent)
