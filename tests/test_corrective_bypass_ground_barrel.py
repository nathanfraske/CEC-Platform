"""Actual native barrel/plane geometry with synthetic missing-role provider.

No source hierarchy, application current or routing admission is mocked green.
"""
import copy
import time
import pcbnew
import pytest
import cec_corrective_bypass_ground_barrel as op
import cec_force_current as force
import cec_native_fill_geometry as fill
from cec_native_items import discard_items


def rect(x0,y0,x1,y1):
    return [[[int(x0*1e6),int(y0*1e6)],[int(x1*1e6),int(y0*1e6)],
        [int(x1*1e6),int(y1*1e6)],[int(x0*1e6),int(y1*1e6)]]]


def setfill(zone,rings):
    shape=fill.reconstruct(rings,time.monotonic()+3)if rings else pcbnew.SHAPE_POLY_SET()
    zone.SetFilledPolysList(zone.GetLayer(),shape);zone.SetIsFilled(True)


@pytest.fixture
def setup(tmp_path,monkeypatch):
    b=pcbnew.BOARD();b.SetCopperLayerCount(6)
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_high_current';b.SetProperties(props)
    nets={}
    for name in('GND','VCC'):
        net=pcbnew.NETINFO_ITEM(b,name);b.Add(net);nets[name]=net
    fp=pcbnew.FOOTPRINT(b);fp.SetReference('C1');fp.SetValue('10uF');b.Add(fp)
    for number,net,x in[('1','VCC',12),('2','GND',10)]:
        p=pcbnew.PAD(fp);p.SetNumber(number);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetSize(pcbnew.VECTOR2I_MM(1,1))
        p.SetLayerSet(pcbnew.PAD.SMDMask());p.SetNet(nets[net]);p.SetPosition(pcbnew.VECTOR2I_MM(x,10));fp.Add(p)
    via=pcbnew.PCB_VIA(b);via.SetPosition(pcbnew.VECTOR2I_MM(10.5,10));via.SetWidth(500000)
    via.SetDrill(300000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetNet(nets['GND']);via.SetLocked(True);b.Add(via)
    for face in(pcbnew.In1_Cu,pcbnew.In4_Cu):
        z=pcbnew.ZONE(b);z.SetNet(nets['GND']);z.SetLayer(face)
        z.Outline().Append(fill.reconstruct([rect(8,8,14,12)],time.monotonic()+3))
        b.Add(z);setfill(z,[rect(8,8,14,12)])
    source=tmp_path/'board.kicad_pcb';pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(source),b)
    intent=dict(source_sha256=force._hash(source),requirement_id='U1:1:local-ceramic',
        capacitor_uuid=force._uid(fp),owner_pad_uuid='synthetic-owner-port')
    def role(*a,**k):
        return dict(capacitor_ref='C1',intent=intent,requirement=dict(rail='VCC'),
            code_identity=dict(synthetic=True),source_family=dict(synthetic=True),
            source_capacitor_ports=[dict(uuid=force._uid(p),net=p.GetNetname(),at_nm=list(p.GetPosition()))for p in fp.Pads()])
    monkeypatch.setattr(op.repair,'plan',role)
    monkeypatch.setattr(op.repair,'_replay_identity',copy.deepcopy)
    monkeypatch.setattr(op.repair,'receive',lambda *_a,**_k:dict(ok=True,role_only=True,admitted=False))
    monkeypatch.setattr(force,'_family',lambda *_a:dict(synthetic=True))
    monkeypatch.setattr(force,'_code_identity',lambda:dict(synthetic=True))
    return source,intent,force._uid(fp.FindPadByNumber('2')),force._uid(via)


def plan(data):
    source,intent,pad,via=data
    return op.plan(source,intent,pad,via,board_hint='synthetic',allow_locked_via_uuid=via)


def candidate(data,tmp_path,fault=None):
    source,intent,pad,old=data;b=pcbnew.LoadBoard(str(source));cap=b.FindFootprintByReference('C1')
    cap.Move(pcbnew.VECTOR2I_MM(.3,0));v=next(t for t in b.GetTracks()if force._uid(t)==old)
    new=pcbnew.PCB_VIA(v);new.m_Uuid.Clone(pcbnew.KIID());new.SetPosition(pcbnew.VECTOR2I_MM(10.3,10))
    discard_items(b,[v]);b.Add(new)
    if fault=='drill':new.SetDrill(350000)
    if fault=='lock':new.SetLocked(False)
    if fault=='partial':new.SetPosition(pcbnew.VECTOR2I_MM(10.8,10))
    if fault=='distance':new.SetPosition(pcbnew.VECTOR2I_MM(12,10))
    if fault=='face':setfill(next(iter(b.Zones())),[])
    if fault=='foreign':
        t=pcbnew.PCB_TRACK(b);t.SetNet(cap.FindPadByNumber('1').GetNet());t.SetLayer(pcbnew.F_Cu)
        t.SetWidth(200000);t.SetStart(pcbnew.VECTOR2I_MM(10.3,9));t.SetEnd(pcbnew.VECTOR2I_MM(10.3,11));b.Add(t)
    path=tmp_path/'child.kicad_pcb';pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(path),b)
    return path,force._uid(new)


def test_native_exclusive_barrel_replacement_preserves_planes_and_partitions(setup,tmp_path):
    proposal=plan(setup);source,*_=setup;before=source.read_bytes();child,uid=candidate(setup,tmp_path)
    r=op.receive(source,child,proposal,uid,board_hint='synthetic')
    assert r['ok']and r['retained_native_partitions']['preserved']
    assert len(r['source_reference_contacts'])==len(r['candidate_reference_contacts'])==2
    assert r['all_other_returns_require_independent_receiving']
    assert not r['admitted']and not r['current_qualified']and not r['other_material_cut_authority']
    assert source.read_bytes()==before


@pytest.mark.parametrize('fault',['drill','lock','partial','distance','face','foreign'])
def test_candidate_geometry_process_and_reference_fail_closed(setup,tmp_path,fault):
    proposal=plan(setup);child,uid=candidate(setup,tmp_path,fault)
    with pytest.raises(ValueError):op.receive(setup[0],child,proposal,uid,board_hint='synthetic')


def test_locked_source_requires_exact_identity_consent(setup):
    source,intent,pad,via=setup
    for consent in(None,'other'):
        with pytest.raises(ValueError):op.plan(source,intent,pad,via,board_hint='synthetic',allow_locked_via_uuid=consent)


@pytest.mark.parametrize('fault',['track','pad','via','group','no_plane'])
def test_source_barrel_cannot_own_other_material(setup,fault):
    source,intent,pad,uid=setup;b=pcbnew.LoadBoard(str(source));v=next(iter(b.GetTracks()))
    if fault=='track':
        t=pcbnew.PCB_TRACK(b);t.SetNet(v.GetNet());t.SetLayer(pcbnew.F_Cu);t.SetWidth(200000)
        t.SetStart(v.GetPosition());t.SetEnd(pcbnew.VECTOR2I_MM(11,10));b.Add(t)
    elif fault=='pad':
        f=pcbnew.FOOTPRINT(b);f.SetReference('OTHER');b.Add(f)
        p=pcbnew.PAD(f);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetLayerSet(pcbnew.PAD.SMDMask())
        p.SetNet(v.GetNet());p.SetSize(pcbnew.VECTOR2I_MM(.4,.4));p.SetPosition(v.GetPosition());f.Add(p)
    elif fault=='via':
        other=pcbnew.PCB_VIA(v);other.m_Uuid.Clone(pcbnew.KIID());b.Add(other)
    elif fault=='group':
        g=pcbnew.PCB_GROUP(b);g.SetName('scope');g.AddItem(v);b.Add(g)
    else:
        for z in b.Zones():setfill(z,[])
    pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(source),b);intent['source_sha256']=force._hash(source)
    with pytest.raises(ValueError):plan(setup)


def test_forged_proposal_or_arbitrary_retirement_is_not_authority(setup,tmp_path):
    p=plan(setup);child,uid=candidate(setup,tmp_path)
    p['source_via_at_nm']=[0,0]
    with pytest.raises(ValueError):op.receive(setup[0],child,p,uid,board_hint='synthetic')


def test_saved_fill_split_cannot_disconnect_retained_copper(setup,tmp_path):
    source,intent,pad,uid=setup;b=pcbnew.LoadBoard(str(source));old=next(iter(b.GetTracks()))
    track=pcbnew.PCB_TRACK(b);track.SetNet(old.GetNet());track.SetLayer(pcbnew.In1_Cu)
    track.SetWidth(200000);track.SetStart(pcbnew.VECTOR2I_MM(13,10));track.SetEnd(pcbnew.VECTOR2I_MM(13.5,10));b.Add(track)
    pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(source),b);intent['source_sha256']=force._hash(source)
    proposal=plan(setup);child,newuid=candidate(setup,tmp_path)
    b=pcbnew.LoadBoard(str(child))
    for z in b.Zones():setfill(z,[rect(8,8,11,12),rect(12,8,14,12)])
    pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(child),b)
    with pytest.raises(ValueError,match='retained_native_terminal_and_copper'):
        op.receive(source,child,proposal,newuid,board_hint='synthetic')
