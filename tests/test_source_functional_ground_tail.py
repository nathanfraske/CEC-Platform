"""Actual native normal-Ground tails; no board/refdes coordinate exceptions."""
import hashlib
import json
import time
import uuid

import pcbnew
import pytest
import cec_source_functional_ground_tail as op
import cec_source_ground_leaf as canonical
import cec_force_current as force
import cec_field_coupling as field
import cec_additive_route_receiving as additive
import cec_source_netlist_semantics as semantics
import cec_synth_pipeline as synth
from test_lastmile import _board


def fixture(tmp_path,monkeypatch,quarter=0,back=False):
    b=_board([(12,12,'GND')],edge=(0,0,40,40));b.SetCopperLayerCount(6)
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';b.SetProperties(props)
    fp=next(iter(b.GetFootprints()));fp.SetReference('renamed_measurement_IC');fp.SetValue('INA240A3')
    fp.SetFPID(pcbnew.LIB_ID('cec-Package_SO','SOIC-8_3.9x4.9mm_P1.27mm'))
    fp.SetField('MPN','INA240A3DR');fp.SetField('Manufacturer','Texas Instruments')
    pad=next(iter(fp.Pads()));pad.SetNumber('2');pad.SetSize(pcbnew.VECTOR2I_MM(1.8,.6))
    pad.SetPinType('power_in');pad.SetPinFunction('GND')
    ni=pcbnew.NETINFO_ITEM(b,'/other');b.Add(ni)
    pins={'1':('IN-','input'),'2':('GND','power_in'),'3':('REF2','input'),
        '4':('NC','no_connect'),'5':('OUT','output'),'6':('VS','power_in'),
        '7':('REF1','input'),'8':('IN+','input')}
    for number,(name,kind)in pins.items():
        if number=='2':continue
        p=pcbnew.PAD(fp);p.SetNumber(number);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetLayerSet(pcbnew.PAD.SMDMask());p.SetSize(pcbnew.VECTOR2I_MM(.3,.3))
        p.SetPosition(pcbnew.VECTOR2I_MM(22+int(number)*.8,25));p.SetNet(ni)
        p.SetPinType(kind);p.SetPinFunction(name);fp.Add(p)
    def track(a,z,locked=True,net=None,face=pcbnew.F_Cu):
        t=pcbnew.PCB_TRACK(b);t.SetStart(pcbnew.VECTOR2I_MM(*a));t.SetEnd(pcbnew.VECTOR2I_MM(*z))
        t.SetWidth(500000);t.SetLayer(face);t.SetNet(net or pad.GetNet());t.SetLocked(locked);b.Add(t);return t
    first=track((12,12),(12,10.5));last=track((12,10.5),(10.5,9))
    rootpeer=track((13.5,12),(12,12),False)
    unrelated=track((22,15),(24,15),False,ni)
    via=pcbnew.PCB_VIA(b);via.SetPosition(pcbnew.VECTOR2I_MM(10.5,9));via.SetNet(pad.GetNet())
    via.SetWidth(900000);via.SetDrill(500000);via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetLocked(True);b.Add(via)
    for face in(pcbnew.In1_Cu,pcbnew.In4_Cu):
        z=pcbnew.ZONE(b);z.SetLayer(face);z.SetNet(pad.GetNet());z.SetLocalClearance(200000)
        z.SetThermalReliefGap(200000);z.SetThermalReliefSpokeWidth(200000);z.Outline().NewOutline()
        for at in((1,1),(39,1),(39,39),(1,39)):z.Outline().Append(pcbnew.VECTOR2I_MM(*at))
        b.Add(z)
    if back:
        for item in [*b.GetFootprints(),*b.GetTracks()]:item.Flip(pcbnew.VECTOR2I_MM(20,20),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    if quarter:
        angle=pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T)
        for item in [*b.GetFootprints(),*b.GetTracks()]:item.Rotate(pcbnew.VECTOR2I_MM(20,20),angle)
    additive._ground_refill(b)
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,source)
    field._save_field_snapshot(pcbnew.LoadBoard(str(source)),source)
    source.with_suffix('.kicad_pro').write_text(json.dumps(dict(net_settings=dict(classes=[
        dict(name='Default',track_width=.2,clearance=.2,via_diameter=.6,via_drill=.3),
        dict(name='GND',track_width=.5,clearance=.2,via_diameter=.9,via_drill=.5)],
        netclass_patterns=[dict(netclass='GND',pattern='GND')]))))
    uid=str(uuid.uuid4());root=tmp_path/'current.kicad_sch'
    props=dict(Reference=fp.GetReference(),Value=fp.GetValue(),Footprint=fp.GetFPIDAsString(),
        MPN='INA240A3DR',Manufacturer='Texas Instruments')
    libpins=' '.join('(pin '+kind+' line (at '+number+' 0 0) (length 1) (name "'+name+'") (number "'+number+'"))'
        for number,(name,kind)in pins.items())
    root.write_text('(kicad_sch (version 20250114) (uuid "'+str(uuid.uuid4())+'")'
        ' (lib_symbols (symbol "fixture:INA240" (symbol "body_1_1" '+libpins+')))'
        ' (symbol (lib_id "fixture:INA240") (at 0 0 0) (unit 1) (uuid "'+uid+'") '+
        ' '.join('(property "'+k+'" "'+v+'")'for k,v in props.items())+'))')
    comp='(comp (ref "'+fp.GetReference()+'") (value "INA240A3") (footprint "'+props['Footprint']+'") '+\
        ' '.join('(property (name "'+k+'") (value "'+v+'"))'for k,v in props.items()if k in('MPN','Manufacturer'))+\
        ' (tstamps "'+uid+'"))'
    tree=synth.parse_sexpr('(export (components '+comp+') (nets (net (name "GND") (node (ref "'+fp.GetReference()+'") (pin "2")))'
        ' (net (name "/other") '+' '.join('(node (ref "'+fp.GetReference()+'") (pin "'+n+'"))'for n in pins if n!='2')+')))')
    exporter=tmp_path/'exporter';exporter.write_bytes(b'fresh selected fixture exporter')
    def export(root,deadline):
        return tree,dict(exporter=str(exporter),exporter_sha256=force._hash(exporter),
            netlist_sha256=hashlib.sha256(repr(tree).encode()).hexdigest(),**semantics.metadata(tree))
    monkeypatch.setattr(canonical,'_export',export)
    def at(x,y):
        if back:x=40-x
        for _ in range(quarter):x,y=y,40-x
        return [round(x*1e6),round(y*1e6)]
    return dict(source=source,root=root,owner=force._uid(pad),via=force._uid(via),first=force._uid(first),
        last=force._uid(last),peer=force._uid(rootpeer),unrelated=force._uid(unrelated),tree=tree,
        exporter=exporter,points=[at(12,12),at(12,11),at(10.5,9.5)],quarter=quarter,back=back)


def proposal(data,**kwargs):
    return op.plan(data['source'],board_hint=str(data['root']),owner_pad_uuid=data['owner'],via_uuid=data['via'],
        locked_item_uuids=[data[k]for k in('first','last','via')],**kwargs)


def receive(data,path,**kwargs):
    return op.receive(data['source'],path,board_hint=str(data['root']),owner_pad_uuid=data['owner'],via_uuid=data['via'],
        locked_item_uuids=[data[k]for k in('first','last','via')],**kwargs)


def save(data,tmp_path):
    q=proposal(data);r=op.write_private(q,tmp_path/'private',data['points']);assert r['complete'],r
    return r['candidate']


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',(False,True))
def test_real_saved_normal_tail_keeps_locks_process_root_contacts_and_returns(tmp_path,monkeypatch,quarter,back):
    data=fixture(tmp_path,monkeypatch,quarter,back);before=data['source'].read_bytes();path=save(data,tmp_path)
    r=receive(data,path);assert r['ok']and r['complete'],r
    assert len(r['phases'])==5 and all(p['complete']for p in r['phases'].values())
    assert r['new_objects']==r['retired_objects']==0
    assert r['independent_Source_proposal']['fixed_root_contact_uuids']==sorted([data['owner'],data['peer']])
    assert not any(r[k]for k in('current_authority','barrel_capacity_qualified','routing_admitted','release_authority'))
    assert before==data['source'].read_bytes()


@pytest.mark.parametrize('fault',('maker','mpn','value','GND_name','GND_role','duplicate_pin','missing_pin','export','reference_as_ground','switcher','Source_small_via','Source_group','Source_branch','lock_manifest'))
def test_source_eligibility_is_independent_and_fail_closed(tmp_path,monkeypatch,fault):
    data=fixture(tmp_path,monkeypatch);b=pcbnew.LoadBoard(str(data['source']))
    fp=next(iter(b.GetFootprints()));live={force._uid(t):t for t in b.GetTracks()};root=data['root'].read_text()
    if fault=='maker':data['root'].write_text(root.replace('Texas Instruments','unknown'))
    elif fault=='mpn':data['root'].write_text(root.replace('INA240A3DR','INA240-unselected'))
    elif fault=='value':data['root'].write_text(root.replace('"INA240A3"','"stale"'))
    elif fault=='GND_name':data['root'].write_text(root.replace('(name "GND")','(name "REF")'))
    elif fault=='GND_role':data['root'].write_text(root.replace('pin power_in line (at 2','pin input line (at 2'))
    elif fault=='duplicate_pin':data['root'].write_text(root.replace('(number "8")','(number "2")'))
    elif fault=='missing_pin':fp.Remove(fp.FindPadByNumber('8'))
    elif fault=='export':synth._first(synth._first(data['tree'],'nets')[1],'name')[1]='/not-ground'
    elif fault=='reference_as_ground':fp.FindPadByNumber('2').SetNumber('3')
    elif fault=='switcher':fp.SetField('MPN','TPS2121RUXR');fp.SetValue('TPS2121')
    elif fault=='Source_small_via':live[data['via']].SetWidth(600000);live[data['via']].SetDrill(300000)
    elif fault=='Source_group':
        g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(live[data['last']])
    elif fault=='Source_branch':
        t=pcbnew.PCB_TRACK(b);t.SetStart(pcbnew.VECTOR2I_MM(12,10.5));t.SetEnd(pcbnew.VECTOR2I_MM(14,10.5))
        t.SetLayer(pcbnew.F_Cu);t.SetWidth(500000);t.SetNet(live[data['via']].GetNet());b.Add(t)
    elif fault=='lock_manifest':live[data['first']].SetLocked(False)
    if fault in('missing_pin','reference_as_ground','switcher','Source_small_via','Source_group','Source_branch','lock_manifest'):
        field._save_field_snapshot(b,data['source'])
    with pytest.raises(ValueError):proposal(data)


@pytest.mark.parametrize('fault',('width','drill','lock','unowned','pose','peer','new','zone','fill','sidecar','root_metadata'))
def test_saved_unowned_and_owned_process_mutations_refused(tmp_path,monkeypatch,fault):
    data=fixture(tmp_path,monkeypatch);path=save(data,tmp_path);b=pcbnew.LoadBoard(path)
    live={force._uid(t):t for t in b.GetTracks()}
    if fault=='width':live[data['first']].SetWidth(400000)
    elif fault=='drill':live[data['via']].SetDrill(400000)
    elif fault=='lock':live[data['last']].SetLocked(False)
    elif fault=='unowned':live[data['unrelated']].Move(pcbnew.VECTOR2I_MM(.1,0))
    elif fault=='pose':next(iter(b.GetFootprints())).Move(pcbnew.VECTOR2I_MM(.1,0))
    elif fault=='peer':live[data['peer']].Move(pcbnew.VECTOR2I_MM(.1,0))
    elif fault=='new':
        t=pcbnew.PCB_TRACK(b);t.SetStart(pcbnew.VECTOR2I_MM(30,10));t.SetEnd(pcbnew.VECTOR2I_MM(32,10))
        t.SetLayer(pcbnew.F_Cu);t.SetWidth(500000);t.SetNet(live[data['via']].GetNet());b.Add(t)
    elif fault=='zone':next(iter(b.Zones())).SetLocalClearance(300000)
    if fault not in('fill','sidecar','root_metadata'):field._save_field_snapshot(b,path)
    if fault=='sidecar':
        from pathlib import Path
        Path(path).with_suffix('.kicad_pro').write_text('{}')
    elif fault=='root_metadata':
        from pathlib import Path
        p=Path(path);p.write_text(p.read_text().replace('(thickness 1.6)','(thickness 1.7)'))
    elif fault=='fill':
        from pathlib import Path
        p=Path(path);text=p.read_text();_,nodes=additive._nodes(p)
        for uid,node in nodes.items():
            if node[0]!='zone':continue
            old=op.literal._inventory(text)[0][uid][2];poly=synth._first(node,'filled_polygon')
            pts=synth._first(poly,'pts');pts[1][1]=str(float(pts[1][1])+.01)
            text=text.replace(old,additive._render(node));break
        p.write_text(text)
    r=receive(data,path);assert not r['ok']and not r['complete']and r['errors'],r


@pytest.mark.parametrize('points',(
    [[12000001,12000000],[12000000,11000000],[10500000,9500000]],
    [[12000000,12000000],[12000000,11000000],[10500000,9000000]],
    [[12000000,12000000],[12000000,12000000],[10500000,9500000]],
    [[12000000,12000000],[12000000,11000000],[10500000.0,9500000]],
    [[12000000,12000000],[12000000,11000000],[10500000,9500000],[10500000,9500001]],
))
def test_invalid_candidate_geometry_is_never_written(tmp_path,monkeypatch,points):
    data=fixture(tmp_path,monkeypatch);q=proposal(data)
    with pytest.raises(ValueError):op.write_private(q,tmp_path/'refused',points)
    assert not(tmp_path/'refused').exists()


@pytest.mark.parametrize('lease',(0,True,float('nan'),float('inf'),10.01))
def test_bounded_finite_explicit_lease_required(lease):
    with pytest.raises(ValueError):op._deadline(lease)


def test_stationary_passive_reference_and_optional_NC_do_not_become_ground_roots(tmp_path,monkeypatch):
    data=fixture(tmp_path,monkeypatch);text=data['root'].read_text()
    for n in('3','7'):
        text=text.replace('pin input line (at '+n+' ','pin passive line (at '+n+' ')
    text=text.replace('pin no_connect line (at 4 ','pin passive line (at 4 ');data['root'].write_text(text)
    b=pcbnew.LoadBoard(str(data['source']));fp=next(iter(b.GetFootprints()))
    for n in('3','4','7'):fp.FindPadByNumber(n).SetPinType('passive')
    field._save_field_snapshot(b,data['source']);q=proposal(data)
    assert q['Source_pin']['pin']=='2'
    for n in('3','4','7'):
        with pytest.raises(ValueError):
            op.plan(data['source'],board_hint=str(data['root']),owner_pad_uuid=force._uid(fp.FindPadByNumber(n)),
                via_uuid=data['via'],locked_item_uuids=[data[k]for k in('first','last','via')])


@pytest.mark.parametrize('face',(pcbnew.F_Cu,pcbnew.In2_Cu,pcbnew.B_Cu))
def test_proposed_normal_barrel_checks_foreign_copper_on_every_face(tmp_path,monkeypatch,face):
    data=fixture(tmp_path,monkeypatch);b=pcbnew.LoadBoard(str(data['source']))
    track=pcbnew.PCB_TRACK(b);track.SetNet(b.FindNet('/other'));track.SetLayer(face);track.SetWidth(200000)
    track.SetStart(pcbnew.VECTOR2I_MM(10.0,10.15));track.SetEnd(pcbnew.VECTOR2I_MM(10.4,10.15));b.Add(track)
    additive._ground_refill(b);field._save_field_snapshot(b,data['source']);q=proposal(data)
    with pytest.raises(ValueError,match='all_face_normal_via_guard'):
        op.write_private(q,tmp_path/'refused',data['points'])
    assert not(tmp_path/'refused').exists()


def test_unowned_same_net_root_extension_outside_actual_land_is_not_owned(tmp_path,monkeypatch):
    data=fixture(tmp_path,monkeypatch);b=pcbnew.LoadBoard(str(data['source']));live={force._uid(t):t for t in b.GetTracks()}
    live[data['peer']].SetStart(pcbnew.VECTOR2I_MM(12,10))
    field._save_field_snapshot(b,data['source'])
    with pytest.raises(ValueError,match='unbranched|unowned_interior'):proposal(data)


def test_expired_last_predicate_cannot_return_complete(tmp_path,monkeypatch):
    data=fixture(tmp_path,monkeypatch);path=save(data,tmp_path)
    original=op._left;calls=[]
    def remaining(deadline):
        calls.append(None)
        return original(deadline)
    monkeypatch.setattr(op,'_left',remaining);assert receive(data,path)['ok'];count=len(calls)
    calls.clear()
    def expire_final(deadline):
        calls.append(None)
        if len(calls)==count:raise ValueError('functional_ground_tail_deadline')
        return original(deadline)
    monkeypatch.setattr(op,'_left',expire_final);r=receive(data,path)
    assert not r['ok']and not r['complete']and any('deadline'in e for e in r['errors']),r


def test_stale_plan_and_changed_exporter_refuse_before_candidate_write(tmp_path,monkeypatch):
    data=fixture(tmp_path,monkeypatch);q=proposal(data);data['exporter'].write_bytes(b'changed tool')
    with pytest.raises(ValueError,match='stale_or_forged'):
        op.write_private(q,tmp_path/'refused',data['points'])
    assert not(tmp_path/'refused').exists()


def _posed(data,x,y):
    if data['back']:x=40-x
    for _ in range(data['quarter']):x,y=y,40-x
    return [round(x*1e6),round(y*1e6)]


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',(False,True))
def test_native_in_land_corner_contact_does_not_need_a_second_pad_centre_endpoint(tmp_path,monkeypatch,quarter,back):
    data=fixture(tmp_path,monkeypatch,quarter,back)
    board=pcbnew.LoadBoard(str(data['source']))
    pad=next(p for f in board.GetFootprints()for p in f.Pads()if force._uid(p)==data['owner'])
    pad.SetSize(pcbnew.VECTOR2I_MM(.6,1.8))
    live={force._uid(t):t for t in board.GetTracks()}
    t=live[data['last']]
    t.SetStart(pcbnew.VECTOR2I(*_posed(data,12,11.79)))
    t.SetEnd(pcbnew.VECTOR2I(*_posed(data,10.5,10.29)))
    root=tuple(pad.GetPosition());face=op._surface(pad);peer=live[data['peer']]
    assert root not in(tuple(t.GetStart()),tuple(t.GetEnd()))
    assert op.native._contact(t,pad,face)and op.native._contact(t,peer,face)
    # Both actual overlap envelopes lie in the SAME real owner land. This
    # is not endpoint aliasing or ownership of exposed Source tee copper.
    assert op._root_contact(t,pad,pad,face,root,time.monotonic()+2)
    assert op._root_contact(t,peer,pad,face,root,time.monotonic()+2)
    pad.SetSize(pcbnew.VECTOR2I_MM(.2,1.8))
    assert not op._root_contact(t,peer,pad,face,root,time.monotonic()+2)
    pad.SetSize(pcbnew.VECTOR2I_MM(.6,1.8))
    peer.SetStart(pcbnew.VECTOR2I(*_posed(data,10,10)))
    peer.SetEnd(pcbnew.VECTOR2I(*root))
    assert not op._root_contact(t,peer,pad,face,root,time.monotonic()+2)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',(False,True))
def test_saved_corner_inside_owner_land_keeps_exact_fixed_peer_and_all_receiving_gates(tmp_path,monkeypatch,quarter,back):
    data=fixture(tmp_path,monkeypatch,quarter,back)
    board=pcbnew.LoadBoard(str(data['source']))
    pad=next(p for f in board.GetFootprints()for p in f.Pads()if force._uid(p)==data['owner'])
    pad.SetSize(pcbnew.VECTOR2I_MM(.6,1.8))
    field._save_field_snapshot(board,data['source'])
    data['points']=[_posed(data,12,12),_posed(data,12,11.3),_posed(data,10.5,9.8)]
    before=data['source'].read_bytes()
    path=save(data,tmp_path)
    received=receive(data,path)
    assert received['ok']and received['complete'],received
    assert received['new_objects']==received['retired_objects']==0
    assert received['independent_Source_proposal']['fixed_root_contact_uuids']==sorted([data['owner'],data['peer']])
    assert all(row['complete']for row in received['phases'].values())
    assert before==data['source'].read_bytes()
