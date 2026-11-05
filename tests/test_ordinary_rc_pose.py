"""Ordinary RC seating carries only its actual owned return, with saved replay."""
import json,math,os
from pathlib import Path
import pcbnew
import pytest
import cec_ordinary_rc_pose as rc
import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
from test_lastmile import _board
from test_field_proposals import track


def fixture(tmp_path,turn=0,suffix=''):
    b=_board([],edge=(0,0,30,30));b.SetCopperLayerCount(6)
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';b.SetProperties(props)
    settings=b.GetDesignSettings();settings.m_ViasMinSize=400000
    settings.m_MinThroughDrill=300000;settings.m_ViasMinAnnularWidth=100000
    nets={}
    for name in ('/SERVICE_TIMING','GND'):
        n=pcbnew.NETINFO_ITEM(b,name);b.Add(n);nets[name]=n
    def footprint(ref,value,origin,rows):
        fp=pcbnew.FOOTPRINT(b);fp.SetReference(ref);fp.SetValue(value);fp.SetPosition(pcbnew.VECTOR2I_MM(*origin))
        if ref.startswith('C'):fp.SetFPID(pcbnew.LIB_ID('Capacitor_SMD','C_0603_1608Metric'))
        for number,net,at in rows:
            p=pcbnew.PAD(fp);p.SetNumber(number);p.SetNet(nets[net]);p.SetPosition(pcbnew.VECTOR2I_MM(*at))
            p.SetSize(pcbnew.VECTOR2I_MM(.8,.8));p.SetShape(pcbnew.PAD_SHAPE_RECT)
            p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu);p.SetLayerSet(layers)
            fp.Add(p)
        b.Add(fp);return fp
    owner=footprint('U'+suffix+'71','ordinary-logic-owner',(10,10),[('1','/SERVICE_TIMING',(10,10))])
    cap=footprint('C'+suffix+'92','2.2uF',(12.5,10),[('1','/SERVICE_TIMING',(12,10)),('2','GND',(13,10))])
    track(b,'/SERVICE_TIMING',(10,10),(12,10))
    v=pcbnew.PCB_VIA(b);v.SetPosition(pcbnew.VECTOR2I_MM(13,10));v.SetWidth(500000);v.SetDrill(300000)
    v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetNet(nets['GND']);b.Add(v)
    for layer in (pcbnew.In1_Cu,pcbnew.In4_Cu):
        z=pcbnew.ZONE(b);z.SetLayer(layer);z.SetNet(nets['GND']);z.SetLocalClearance(200000);z.SetMinThickness(100000)
        poly=z.Outline();poly.NewOutline()
        for x,y in ((1,1),(29,1),(29,29),(1,29)):poly.Append(round(x*1e6),round(y*1e6))
        b.Add(z)
    if turn:
        pivot=pcbnew.VECTOR2I_MM(15,15);angle=pcbnew.EDA_ANGLE(turn,pcbnew.DEGREES_T)
        for fp in b.GetFootprints():fp.Rotate(pivot,angle)
        for t in b.GetTracks():t.Rotate(pivot,angle)
    additive._ground_refill(b)
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,source);b.SetFileName(str(source))
    return b,source,force._uid(v),force._uid(cap)


def construct(tmp_path,turn=0,suffix=''):
    b,source,uid,fpuid=fixture(tmp_path,turn,suffix);scope=rc.plan(b,source,uid,hint='synthetic')
    theta=math.radians(turn);shift=(round(2000000*math.sin(theta)),round(2000000*math.cos(theta)))
    at=[scope['source_pose_nm'][i]+shift[i] for i in (0,1)]
    cap,via,supply,ground=rc.pose(b,scope,at,scope['source_orientation'])
    rc.preflight(b,scope)
    track(b,scope['net'],tuple(v/1e6 for v in scope['source_supply_nm']),tuple(v/1e6 for v in supply.GetPosition()))
    additive._ground_refill(b);target=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(b,target)
    return source,target,uid,fpuid,scope


def local_rule_fixture(tmp_path,turn=0,profile='jlcpcb_6l_pofv_signal'):
    b,source,uid,fpuid=fixture(tmp_path,turn,'RULE')
    props=b.GetProperties();props['CEC_FAB_PROFILE']=profile;b.SetProperties(props)
    via=next(t for t in b.GetTracks() if force._uid(t)==uid);via.SetWidth(350000);via.SetDrill(250000)
    evidence=fr.group_local_pofv_signal_vias(b,[via]);assert evidence
    field._save_field_snapshot(b,source)
    source.with_suffix('.kicad_pro').write_text(json.dumps({'board':{'design_settings':{'rules':{
        'min_via_diameter':.5,'min_through_hole_diameter':.3,'min_via_annular_width':.1,
        'min_hole_to_hole':.254,'min_clearance':.2}}}}))
    fr.ensure_local_pofv_signal_via_rule(str(source),dict(local_pofv_signal_vias=evidence))
    return pcbnew.LoadBoard(str(source)),source,uid,fpuid


@pytest.mark.parametrize('turn',[0,90,180,270])
@pytest.mark.parametrize('profile',['jlcpcb_6l_pofv_signal','jlcpcb_6l_pofv_high_current'])
def test_retained_small_RC_return_uses_only_its_exact_existing_native_local_rule(tmp_path,turn,profile):
    import cec_native_drc_runner as native
    import cec_existing_local_pofv_pad_rule as rule
    b,source,uid,fpuid=local_rule_fixture(tmp_path,turn,profile);before=source.read_bytes()
    scope=rc.plan(b,source,uid,hint='synthetic');assert scope['source_local_pad_rule']
    limits=rule._floors(b);assert limits[:3]==(500000,300000,100000)
    angle=math.radians(turn);at=[scope['source_pose_nm'][0]+round(2000000*math.sin(angle)),
        scope['source_pose_nm'][1]+round(2000000*math.cos(angle))]
    cap,via,supply,ground=rc.pose(b,scope,at,scope['source_orientation'])
    preflight=rc.preflight(b,scope);assert preflight['retained_barrel_process']['existing_local_rule_retained']
    track(b,scope['net'],tuple(v/1e6 for v in scope['source_supply_nm']),tuple(v/1e6 for v in supply.GetPosition()))
    additive._ground_refill(b);child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(b,child)
    proof=rc.receive(source,child,via_uuid=uid,board_hint='synthetic')
    assert proof['ok'] and proof['complete'],proof
    assert source.read_bytes()==before and rule._floors(b)==limits
    assert source.with_suffix('.kicad_dru').read_bytes()==child.with_suffix('.kicad_dru').read_bytes()
    build=os.environ.get('CEC_NATIVE_DRC_TEST_BUILD')
    if not build:pytest.skip('native retained-rule parity requires explicit native build')
    def faults(path,label):
        output=tmp_path/(label+'.json');producer=native.run(path,output,reporting_build=Path(build),timeout_s=10.)
        assert producer['ok'] and producer['complete'] and not producer['native_inventory']['potentially_truncated']
        return {q['type'] for q in json.loads(output.read_text())['violations']
            if q['type'] in ('via_diameter','drill_out_of_range','annular_width') and any(i.get('uuid')==uid for i in q['items'])}
    assert not faults(child,'retained-existing-rule')
    changed=pcbnew.LoadBoard(str(child));v=next(t for t in changed.GetTracks() if force._uid(t)==uid)
    next(g for g in changed.Groups() if g.ContainsItem(v)).RemoveItem(v)
    control=force._copy_family(child,tmp_path/'removed-group');field._save_field_snapshot(changed,control)
    assert faults(control,'removed-group')=={'via_diameter','drill_out_of_range','annular_width'}
    assert not rc.receive(source,control,via_uuid=uid,board_hint='synthetic')['ok']


@pytest.mark.parametrize('fault',['missing_rule','changed_rule','missing_group','profile','floors','diameter','drill','offpad','owner','context'])
def test_retained_local_RC_rule_cannot_waive_new_geometry_or_lost_source_context(tmp_path,fault):
    b,source,uid,fpuid=local_rule_fixture(tmp_path);scope=rc.plan(b,source,uid,hint='synthetic')
    cap,via,supply,ground=rc.pose(b,scope,[scope['source_pose_nm'][0],scope['source_pose_nm'][1]+2000000],scope['source_orientation'])
    if fault=='missing_rule':source.with_suffix('.kicad_dru').unlink()
    elif fault=='changed_rule':
        path=source.with_suffix('.kicad_dru');path.write_text(path.read_text().replace('0.050mm','0.100mm'))
    elif fault=='missing_group':next(g for g in b.Groups() if g.ContainsItem(via)).RemoveItem(via)
    elif fault=='profile':
        props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_high_current';b.SetProperties(props)
    elif fault=='floors':b.GetDesignSettings().m_ViasMinSize+=1
    elif fault=='diameter':via.SetWidth(351000)
    elif fault=='drill':via.SetDrill(249000)
    elif fault=='offpad':via.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='owner':ground.SetNetCode(supply.GetNetCode())
    else:scope['source_local_pad_rule']['minimum_nm']['annular_width']=49999
    with pytest.raises((ValueError,OSError)):rc.preflight(b,scope)


@pytest.mark.parametrize('turn',[0,90,180,270])
@pytest.mark.parametrize('local_rule',[False,True])
def test_small_rigid_RC_shift_does_not_require_redundant_copper_when_actual_contacts_survive(tmp_path,turn,local_rule):
    b,source,uid,fpuid=(local_rule_fixture(tmp_path,turn) if local_rule else fixture(tmp_path,turn))
    original=source.read_bytes();scope=rc.plan(b,source,uid,hint='synthetic');angle=math.radians(turn)
    dx=round(100000*math.cos(angle)+50000*math.sin(angle));dy=round(-100000*math.sin(angle)+50000*math.cos(angle))
    rc.pose(b,scope,[scope['source_pose_nm'][0]+dx,scope['source_pose_nm'][1]+dy],scope['source_orientation'])
    rc.preflight(b,scope);additive._ground_refill(b)
    child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(b,child)
    proof=rc.receive(source,child,via_uuid=uid,board_hint='synthetic')
    assert proof['ok'] and proof['complete'],proof
    assert proof['added_ordinary_lead_count']==0 and proof['all_source_contacts_preserved_without_new_leads']
    assert proof['all_original_terminal_and_copper_partitions_preserved'] and source.read_bytes()==original


@pytest.mark.parametrize('fault',['lost_signal_contact','orphan_return','changed_pad'])
def test_zero_lead_RC_motion_still_requires_exact_package_return_and_every_native_contact(tmp_path,fault):
    b,source,uid,fpuid=local_rule_fixture(tmp_path);scope=rc.plan(b,source,uid,hint='synthetic')
    cap,via,supply,ground=rc.pose(b,scope,[scope['source_pose_nm'][0],scope['source_pose_nm'][1]+(800000 if fault=='lost_signal_contact' else 50000)],scope['source_orientation'])
    if fault=='orphan_return':via.Move(pcbnew.VECTOR2I(1000000,0))
    elif fault=='changed_pad':ground.SetSize(pcbnew.VECTOR2I_MM(.81,.8))
    additive._ground_refill(b);child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(b,child)
    proof=rc.receive(source,child,via_uuid=uid,board_hint='synthetic')
    assert not proof['ok'] and not proof['complete'],proof


@pytest.mark.parametrize('turn,suffix',[(0,''),(90,'A'),(180,'RENAMED'),(270,'Q')])
def test_renamed_rotated_RC_pose_restores_all_original_native_contacts(tmp_path,turn,suffix):
    source,target,uid,fpuid,scope=construct(tmp_path,turn,suffix);before=source.read_bytes()
    assert not additive.receive(source,target)['ok']
    proof=rc.receive(source,target,via_uuid=uid,board_hint='synthetic')
    assert proof['ok'] and proof['complete'],proof['errors']
    assert proof['source_owned_inpad_entry_geometry_preserved'] and proof['all_original_terminal_and_copper_partitions_preserved']
    assert not proof['release_authority'] and not proof['current_qualified'] and source.read_bytes()==before


@pytest.mark.parametrize('fault',['owner_move','value','net','shape','diameter','drill','missing_via','wrong_via',
    'old_trace_cut','old_trace_changed','lost_lead','new_via','wide_new_lead','other_net','noncardinal','outside_motion','outline'])
def test_saved_pose_cannot_smuggle_geometry_identity_or_source_connection_changes(tmp_path,fault):
    source,target,uid,fpuid,scope=construct(tmp_path);b=pcbnew.LoadBoard(str(target))
    cap=next(f for f in b.GetFootprints() if force._uid(f)==fpuid);via=next(t for t in b.GetTracks() if force._uid(t)==uid)
    old_ids={force._uid(t) for t in pcbnew.LoadBoard(str(source)).GetTracks()}
    old=next(t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK' and force._uid(t) in old_ids)
    new=next(t for t in b.GetTracks() if force._uid(t) not in old_ids)
    if fault=='owner_move':b.FindFootprintByReference('U71').Move(pcbnew.VECTOR2I_MM(.1,0))
    elif fault=='value':cap.SetValue('10nF')
    elif fault=='net':cap.FindPadByNumber('1').SetNetCode(b.GetNetcodeFromNetname('GND'))
    elif fault=='shape':cap.FindPadByNumber('2').SetSize(pcbnew.VECTOR2I_MM(1,1))
    elif fault=='diameter':via.SetWidth(600000)
    elif fault=='drill':via.SetDrill(350000)
    elif fault=='missing_via':b.Remove(via)
    elif fault=='wrong_via':uid='absent-native-identity'
    elif fault=='old_trace_cut':b.Remove(old)
    elif fault=='old_trace_changed':old.SetWidth(250000)
    elif fault=='lost_lead':new.SetEnd(pcbnew.VECTOR2I_MM(12,11.2))
    elif fault=='new_via':
        q=pcbnew.PCB_VIA(b);q.SetPosition(pcbnew.VECTOR2I_MM(20,20));q.SetNetCode(via.GetNetCode())
        q.SetWidth(600000);q.SetDrill(300000);q.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(q)
    elif fault=='wide_new_lead':new.SetWidth(500000)
    elif fault=='other_net':track(b,'GND',(20,20),(22,20))
    elif fault=='noncardinal':cap.SetOrientationDegrees(13)
    elif fault=='outside_motion':cap.Move(pcbnew.VECTOR2I_MM(7,0))
    else:next(d for d in b.GetDrawings() if d.GetLayer()==pcbnew.Edge_Cuts).Move(pcbnew.VECTOR2I_MM(.1,0))
    field._save_field_snapshot(b,target);proof=rc.receive(source,target,via_uuid=uid,board_hint='synthetic')
    assert not proof['ok'] and not proof['complete'] and proof['errors'],proof


@pytest.mark.parametrize('fault',['locked','bulk','not_RC','power','one_plane','external_ground_branch','shared_ground_land'])
def test_source_eligibility_refuses_unsafe_return_reassignment_before_motion(tmp_path,fault):
    b,source,uid,fpuid=fixture(tmp_path);cap=next(f for f in b.GetFootprints() if force._uid(f)==fpuid)
    if fault=='locked':cap.SetLocked(True)
    elif fault=='bulk':cap.SetValue('4700uF')
    elif fault=='not_RC':cap.SetReference('OTHER');cap.SetFPID(pcbnew.LIB_ID('Unknown','OTHER'))
    elif fault=='power':cap.FindPadByNumber('1').SetPinType('power_in')
    elif fault=='one_plane':b.Remove(next(iter(b.Zones())))
    elif fault=='external_ground_branch':track(b,'GND',(13,10),(13,11))
    else:
        other=pcbnew.FOOTPRINT(b);other.SetReference('OTHER_GROUND');p=pcbnew.PAD(other)
        p.SetNumber('1');p.SetNetCode(b.GetNetcodeFromNetname('GND'));p.SetPosition(pcbnew.VECTOR2I_MM(13,10))
        p.SetSize(pcbnew.VECTOR2I_MM(.8,.8));p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu);p.SetLayerSet(layers);other.Add(p);b.Add(other)
    before=field._field_snapshot_inventory(b)
    with pytest.raises(ValueError):rc.plan(b,source,uid,hint='synthetic')
    assert before==field._field_snapshot_inventory(b)


@pytest.mark.parametrize('turn',[0,90,180,270])
def test_future_owned_RC_obstacles_are_disposable_without_source_or_field_motion(tmp_path,turn):
    from cec_native_items import discard_items
    b,source,uid,fpuid=fixture(tmp_path,turn);before=field._field_snapshot_inventory(b)
    old=source.read_bytes();scope=rc.plan(b,source,uid,hint='synthetic');angle=math.radians(turn)
    at=[scope['source_pose_nm'][0]+round(2000000*math.sin(angle)),scope['source_pose_nm'][1]+round(2000000*math.cos(angle))]
    request=dict(schema=1,source_sha256=force._hash(source),via_uuid=uid,position_nm=at,orientation_deg=scope['source_orientation'])
    items,proof=rc.reserve_future_pose(b,source,request,board_hint='synthetic',blocked_net='/OTHER_POWER')
    assert len(items)==3 and sum(q.GetClass()=='PCB_VIA' for q in items)==1
    assert not proof['pose_admitted'] and not proof['saved_copper'] and not proof['release_authority']
    discard_items(b,items);assert before==field._field_snapshot_inventory(b) and source.read_bytes()==old


@pytest.mark.parametrize('fault',['stale','same_net','far','angle','extra_permission'])
def test_bad_future_RC_request_never_leaves_obstacles_or_mutates_source(tmp_path,fault):
    b,source,uid,fpuid=fixture(tmp_path);before=field._field_snapshot_inventory(b)
    request=dict(schema=1,source_sha256=force._hash(source),via_uuid=uid,position_nm=[12500000,12000000],orientation_deg=0)
    blocked='/OTHER_POWER'
    if fault=='stale':request['source_sha256']='a'*64
    elif fault=='same_net':blocked='/SERVICE_TIMING'
    elif fault=='far':request['position_nm']=[22000000,12000000]
    elif fault=='angle':request['orientation_deg']=13
    else:request['allow_vent']=True
    with pytest.raises(ValueError):rc.reserve_future_pose(b,source,request,board_hint='synthetic',blocked_net=blocked)
    assert before==field._field_snapshot_inventory(b)
