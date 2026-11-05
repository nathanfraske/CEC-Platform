"""Saved passive motion keeps full Source entries, never an inferred return."""
import copy
import json
from pathlib import Path

import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_pose_additive_reconstruction as receiving
import cec_projected_ground_contact as contact
import cec_retained_passive_pose_stage as stage
from cec_native_items import discard_items
from test_field_proposals import track
from test_native_ground_terminal_branch import fixture as ground_fixture
from test_projected_ground_contact import fixture as pivot_fixture
from test_smd_macro_transport import inventory


def fixture(tmp_path,*,back=False,quarter=0,mapped=False):
    face=pcbnew.B_Cu if back else pcbnew.F_Cu
    board,source,_,_,owner,cap,_=ground_fixture(tmp_path,quarter=quarter,layer=face)
    cap.SetReference('C61'if mapped else'RENAMED_LOCAL_61')
    cap.SetFPID(pcbnew.LIB_ID('Capacitor_SMD','C_0603_1608Metric'))
    points={force._uid(p):tuple(p.GetPosition())for p in cap.Pads()}
    center=[round(sum(p[k]for p in points.values())/2)for k in(0,1)]
    cap.SetPosition(pcbnew.VECTOR2I(*center));cap.SetOrientationDegrees(quarter*90)
    for p in cap.Pads():
        p.SetPosition(pcbnew.VECTOR2I(*points[force._uid(p)]));p.SetSize(pcbnew.VECTOR2I_MM(.6,.6))
    root=cap.FindPadByNumber('2');at=tuple(root.GetPosition())
    # Discard only this synthetic cap's old shared Ground lead. Its Source
    # now has a real 0.93 mm dogbone, not an assumed shortest return.
    discard_items(board,[t for t in board.GetTracks()if t.GetClass()=='PCB_TRACK'
        and t.GetNetname()=='GND'and at in(tuple(t.GetStart()),tuple(t.GetEnd()))])
    dx,dy=((0,1),(-1,0),(0,-1),(1,0))[quarter]
    end=(at[0]+dx*930000,at[1]+dy*930000)
    via=pcbnew.PCB_VIA(board);via.SetNet(board.FindNet('GND'))
    via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetPosition(pcbnew.VECTOR2I(*end));via.SetWidth(350000);via.SetDrill(250000);board.Add(via)
    stem=track(board,'GND',[v/1e6 for v in at],[v/1e6 for v in end],layer=face,width=.2)
    assert fr.group_local_pofv_signal_vias(board,[via])
    groups=[]
    if mapped:
        import cec_source_reference_group_transport as maps
        vertices=[(center[0]-2000000,center[1]-1500000),(center[0]+2000000,center[1]-1500000),
            (center[0]+2000000,center[1]+1500000),(center[0]-2000000,center[1]+1500000)]
        group=pcbnew.PCB_GROUP(board);group.SetName(maps.PREFIX+cap.GetReference());board.Add(group);group.AddItem(cap)
        for a,b in zip(vertices,vertices[1:]+vertices[:1]):
            line=pcbnew.PCB_SHAPE(cap);line.SetShape(pcbnew.SHAPE_T_SEGMENT)
            line.SetLayer(pcbnew.B_CrtYd if back else pcbnew.F_CrtYd)
            line.SetStart(pcbnew.VECTOR2I(*a));line.SetEnd(pcbnew.VECTOR2I(*b));line.SetWidth(50000);cap.Add(line)
        contour=cap.GetCourtyard(cap.GetLayer()).COutline(0)
        vertices=[tuple(contour.CPoint(i))for i in range(contour.PointCount())]
        for a,b in zip(vertices,vertices[1:]+vertices[:1]):
            line=pcbnew.PCB_SHAPE(board);line.SetShape(pcbnew.SHAPE_T_SEGMENT)
            line.SetLayer(pcbnew.F_SilkS if back else pcbnew.B_SilkS)
            line.SetStart(pcbnew.VECTOR2I(*a));line.SetEnd(pcbnew.VECTOR2I(*b));line.SetWidth(150000)
            board.Add(line);group.AddItem(line)
        text=pcbnew.PCB_TEXT(board);text.SetText(cap.GetReference());text.SetPosition(cap.GetPosition())
        text.SetLayer(pcbnew.F_SilkS if back else pcbnew.B_SilkS);text.SetMirrored(not back)
        text.SetTextSize(pcbnew.VECTOR2I_MM(1,1));text.SetTextThickness(150000)
        text.SetKeepUpright(True);text.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER)
        text.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER);board.Add(text);group.AddItem(text)
        cap.Reference().SetVisible(False);group.SetLocked(True);cap.SetLocked(False);groups=[force._uid(group)]
    additive._ground_refill(board);field._save_field_snapshot(board,source)
    additive.bind_local_via_rule(board,source)
    pose=[center[0]/1e6+dx*.05,center[1]/1e6+dy*.05,cap.GetOrientationDegrees()]
    return source,cap.GetReference(),force._uid(cap),force._uid(root),force._uid(via),force._uid(stem),pose,groups


def build(tmp_path,**kwargs):
    source,ref,uid,pad,via,stem,pose,groups=fixture(tmp_path,**kwargs)
    proposal=stage.plan(source,{ref:pose},board_hint='synthetic',reference_group_uuids=groups,
        retain_projected_ground_entries=True)
    proposal=json.loads(json.dumps(proposal))
    result=stage.construct(source,tmp_path/'retained',proposal)
    assert result['ok']and result['complete'],result.get('receiving',{}).get('errors',result)
    return source,Path(result['candidate']),proposal,uid,pad,via,stem


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('quarter',range(4))
def test_saved_named_cap_dogbone_entry_retention_is_source_derived(tmp_path,back,quarter):
    source,child,q,uid,pad,via,stem=build(tmp_path,back=back,quarter=quarter)
    before=source.read_bytes();sidecars=force._sidecars(source)
    proof=stage.receive(source,child,json.loads(json.dumps(q)))
    assert proof['ok']and proof['complete'],proof
    exact=proof['independent_Source_pose_reconstruction']
    assert exact['Source_projected_Ground_entries_independently_rederived']
    assert exact['inherited_return_is_not_new_immediate_return_qualification']
    assert exact['all_original_terminal_and_copper_partitions_preserved']
    retained=exact['source_ground_barrel_transport']['independently_retained_projected_ground_contacts']
    assert len(retained)==1
    observed=retained[0]['after_complete_transport']
    assert observed['source_return_mm']==pytest.approx(.93)
    assert observed['saved_return_mm']==pytest.approx(.88)
    assert observed['saved_return_mm']>.8 and not observed['new_immediate_return_qualification']
    assert not proof['current_qualified']and not proof['routing_admitted']and not proof['release_authority']
    first,last=[inventory(pcbnew.LoadBoard(str(p)))for p in(source,child)]
    assert first==last and first[via]==last[via]and first[stem]==last[stem]
    assert source.read_bytes()==before and force._sidecars(source)==sidecars
    assert not exact['exact_source_plus_additions']['added_native_uuids']


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('turn',[90,180,270])
def test_helper_rederives_cardinal_projected_native_lands_in_rigid_frames(tmp_path,back,quarter,turn):
    board,source,_,cap,root,_,pose=pivot_fixture(tmp_path,quarter=quarter,back=back,turn=turn)
    cap.SetFPID(pcbnew.LIB_ID('Capacitor_SMD','C_0603_1608Metric'))
    cap.SetReference('IMPORTED_BYPASS_417');field._save_field_snapshot(board,source)
    before=source.read_bytes();binding=contact.row._source_binding(board)
    q=contact.plan_capacitor_entries(board,{cap.GetReference():pose},board_hint='synthetic')
    assert list(q)==[force._uid(root)]
    assert q[force._uid(root)]['source_ground_role']['kind']=='source_selected_bypass_ground'
    assert q[force._uid(root)]['unchanged_source_return_is_not_new_immediate_return_qualification']
    assert before==source.read_bytes()and binding==contact.row._source_binding(board)


def test_default_off_has_no_implicit_source_entry_policy_or_schema_change(tmp_path,monkeypatch):
    source,ref,uid,pad,via,stem,pose,groups=fixture(tmp_path)
    old=stage.plan(source,{ref:pose},board_hint='synthetic')
    explicit=stage.plan(source,{ref:pose},board_hint='synthetic',retain_projected_ground_entries=False)
    assert old==explicit and'retain_projected_ground_entries'not in old
    def forbidden(*args,**kwargs):raise AssertionError('default_must_not_derive_projected_proofs')
    monkeypatch.setattr(contact,'plan_capacitor_entries',forbidden)
    try:stage.construct(source,tmp_path/'legacy',old)
    except ValueError:pass  # The old destination POFV refusal is preserved.


@pytest.mark.parametrize('value',[None,0,1,'yes',{},[]])
def test_new_work_policy_is_a_strict_boolean_not_a_motion_waiver(tmp_path,value):
    source,ref,uid,pad,via,stem,pose,groups=fixture(tmp_path)
    with pytest.raises(ValueError):stage.plan(source,{ref:pose},board_hint='synthetic',retain_projected_ground_entries=value)
    q=receiving.receive(source,source,selected_footprint_uuids=[uid],board_hint='synthetic',
        allow_source_ground_barrel_motion=True,retain_projected_ground_entries=value)
    assert not q['ok']and any('bounded_explicit_connected_pose_scope_required'in e for e in q['errors'])


def test_ground_entry_retention_requires_existing_grounded_passive_tier(tmp_path):
    source,ref,uid,pad,via,stem,pose,groups=fixture(tmp_path)
    with pytest.raises(ValueError):stage.plan(source,{ref:pose},board_hint='synthetic',
        retain_projected_ground_entries=True,allow_source_ground_barrel_motion=False)
    q=receiving.receive(source,source,selected_footprint_uuids=[uid],board_hint='synthetic',
        retain_projected_ground_entries=True)
    assert not q['ok']and q['errors']


@pytest.mark.parametrize('fault',['resistor','bulk','unknown_role','clipped','unpopulated','missing_source',
    'stationary_only','duplicate_reference','wrong_face','noncardinal','far'])
def test_helper_cannot_invent_a_ground_role_contact_or_unbounded_work(tmp_path,fault):
    source,ref,uid,pad,via,stem,pose,groups=fixture(tmp_path)
    board=pcbnew.LoadBoard(str(source));cap=board.FindFootprintByReference(ref)
    if fault=='resistor':cap.SetFPID(pcbnew.LIB_ID('Resistor_SMD','R_0603_1608Metric'));cap.SetValue('47k')
    elif fault=='bulk':cap.SetFPID(pcbnew.LIB_ID('Capacitor_SMD','CP_Elec_6.3x5.8'));cap.SetValue('2200uF')
    elif fault=='unknown_role':next(fp for fp in board.GetFootprints()if force._uid(fp)!=uid).SetValue('UNKNOWN_IC')
    elif fault=='clipped':pose[0]+=.5
    elif fault=='unpopulated':cap.SetAttributes(pcbnew.FP_DNP)
    elif fault=='missing_source':board.SetFileName('')
    elif fault=='stationary_only':pose=[cap.GetPosition().x/1e6,cap.GetPosition().y/1e6,cap.GetOrientationDegrees()]
    elif fault=='duplicate_reference':
        peer=pcbnew.FOOTPRINT(board);peer.SetReference(ref);board.Add(peer)
    elif fault=='wrong_face':cap.FindPadByNumber('2').SetLayerSet(pcbnew.PAD.PTHMask())
    elif fault=='noncardinal':pose[2]+=1
    else:pose[0]+=7
    if fault!='missing_source':field._save_field_snapshot(board,source)
    before=inventory(board),source.read_bytes()
    with pytest.raises(ValueError):contact.plan_capacitor_entries(board,{ref:pose},board_hint='synthetic')
    assert before==(inventory(board),source.read_bytes())


@pytest.mark.parametrize('fault',['anchor','barrel','positive_copper','plane','pad','assignment','sidecar','proof_payload'])
def test_independent_saved_receiver_rejects_changed_material_or_caller_proof_authority(tmp_path,fault):
    source,child,q,uid,pad,via,stem=build(tmp_path)
    board=pcbnew.LoadBoard(str(child));items={force._uid(t):t for t in board.GetTracks()}
    if fault=='anchor':items[stem].Move(pcbnew.VECTOR2I(1,0))
    elif fault=='barrel':items[via].Move(pcbnew.VECTOR2I(1,0))
    elif fault=='positive_copper':next(t for t in board.GetTracks()if t.GetNetname()=='+3V3').SetWidth(199999)
    elif fault=='plane':next(iter(board.Zones())).UnFill()
    elif fault=='pad':next(p for f in board.GetFootprints()for p in f.Pads()if force._uid(p)==pad).SetSize(pcbnew.VECTOR2I_MM(.91,1))
    elif fault=='assignment':board.FindFootprintByReference(next(iter(q['poses']))).SetValue('2200uF')
    elif fault=='sidecar':child.with_suffix('.kicad_pro').write_text(json.dumps({'changed':True}))
    else:q['native_projected_ground_contacts']={'caller':'authority'}
    if fault not in('sidecar','proof_payload'):field._save_field_snapshot(board,child)
    proof=stage.receive(source,child,q)
    assert not proof['ok']and proof['errors'],proof


def test_constructor_and_receiver_derive_fresh_proofs_from_original_not_projected(tmp_path,monkeypatch):
    source,ref,uid,pad,via,stem,pose,groups=fixture(tmp_path);raw=source.read_bytes();calls=[]
    original=contact.plan_capacitor_entries
    def fresh(board,poses,**kwargs):
        current=board.FindFootprintByReference(ref)
        assert [current.GetPosition().x/1e6,current.GetPosition().y/1e6,current.GetOrientationDegrees()]!=pose
        assert Path(board.GetFileName()).resolve()==source.resolve()and source.read_bytes()==raw
        calls.append(1);return original(board,poses,**kwargs)
    monkeypatch.setattr(contact,'plan_capacitor_entries',fresh)
    q=stage.plan(source,{ref:pose},board_hint='synthetic',retain_projected_ground_entries=True)
    result=stage.construct(source,tmp_path/'fresh',q)
    assert result['ok']and result['complete'],result
    assert len(calls)==2
    assert stage.receive(source,result['candidate'],json.loads(json.dumps(q)))['ok']
    assert len(calls)==3


def test_mixed_inpad_and_retained_dogbone_keep_every_actual_source_conductor(tmp_path):
    source,ref,uid,pad,via,stem,pose,groups=fixture(tmp_path)
    board=pcbnew.LoadBoard(str(source));face=pcbnew.F_Cu
    def part(name,value,fpid,at,entries):
        fp=pcbnew.FOOTPRINT(board);fp.SetReference(name);fp.SetValue(value);fp.SetFPID(fpid)
        fp.SetPosition(pcbnew.VECTOR2I_MM(*at));board.Add(fp)
        for number,net,x,y in entries:
            p=pcbnew.PAD(fp);p.SetNumber(number);p.SetNet(board.FindNet(net));p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetSize(pcbnew.VECTOR2I_MM(.6,.6))
            p.SetPosition(pcbnew.VECTOR2I_MM(x,y));p.SetLayerSet(pcbnew.PAD.SMDMask());fp.Add(p)
        return fp
    owner=part('DIFFERENT_OWNER_22','INA238',pcbnew.LIB_ID(),(18.1,14.4),
        [('6','+3V3',18.1,14.),('7','GND',18.1,14.8)])
    cap=part('NATIVE_CAP_623','100nF',pcbnew.LIB_ID('Capacitor_SMD','C_0603_1608Metric'),(20.,14.),
        [('1','+3V3',19.6,14.),('2','GND',20.4,14.)])
    track(board,'+3V3',(18.1,14.),(19.6,14.),width=.2)
    v=pcbnew.PCB_VIA(board);v.SetNet(board.FindNet('GND'));v.SetPosition(pcbnew.VECTOR2I_MM(20.4,14.))
    v.SetWidth(350000);v.SetDrill(250000);v.SetViaType(pcbnew.VIATYPE_THROUGH)
    v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(v)
    assert fr.group_local_pofv_signal_vias(board,[v]);additive._ground_refill(board)
    field._save_field_snapshot(board,source);additive.bind_local_via_rule(board,source)
    proposal=stage.plan(source,{ref:pose,cap.GetReference():[20.05,14.,0.]},
        board_hint='synthetic',retain_projected_ground_entries=True)
    result=stage.construct(source,tmp_path/'mixed',json.loads(json.dumps(proposal)))
    assert result['ok']and result['complete'],result.get('receiving',{}).get('errors',result)
    exact=result['receiving']['independent_Source_pose_reconstruction']
    carried=exact['source_ground_barrel_transport']
    proofs=carried['independently_retained_projected_ground_contacts']
    assert [p['after_complete_transport']['saved_return_mm']for p in proofs]==pytest.approx([.88])
    assert all(not p['after_complete_transport']['new_immediate_return_qualification']for p in proofs)
    first,last=[inventory(pcbnew.LoadBoard(str(p)))for p in(source,result['candidate'])]
    changed={u for u in first if first[u]!=last[u]}
    assert changed=={force._uid(v)}and len(carried['changes'])==1
    assert carried['source_process_barrel_motion'][0]['actual_source_ownership_basis']=='complete_native_in_pad_containment'
    assert not exact['exact_source_plus_additions']['added_native_uuids']


@pytest.mark.parametrize('unknown_owner',[False,True])
def test_offcentre_zero_return_inpad_defers_to_existing_barrel_follow_not_fixed_entry(tmp_path,unknown_owner):
    source,ref,uid,pad,via,stem,pose,groups=fixture(tmp_path)
    board=pcbnew.LoadBoard(str(source));cap=board.FindFootprintByReference(ref);root=cap.FindPadByNumber('2')
    live={force._uid(t):t for t in board.GetTracks()};discard_items(board,[live[via],live[stem]])
    at=tuple(root.GetPosition());v=pcbnew.PCB_VIA(board);v.SetNet(board.FindNet('GND'))
    v.SetPosition(pcbnew.VECTOR2I(at[0],at[1]+100000));v.SetWidth(350000);v.SetDrill(250000)
    v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(v)
    track(board,'GND',[p/1e6 for p in at],[at[0]/1e6,(at[1]+100000)/1e6],width=.2)
    assert fr.group_local_pofv_signal_vias(board,[v])
    if unknown_owner:next(fp for fp in board.GetFootprints()if force._uid(fp)!=uid).SetValue('UNKNOWN_IC')
    additive._ground_refill(board);field._save_field_snapshot(board,source);additive.bind_local_via_rule(board,source)
    pose=[cap.GetPosition().x/1e6,cap.GetPosition().y/1e6-.08,cap.GetOrientationDegrees()]
    if unknown_owner:
        with pytest.raises(ValueError):contact.plan_capacitor_entries(board,{ref:pose},board_hint='synthetic')
        return
    before=inventory(board)
    assert contact.plan_capacitor_entries(board,{ref:pose},board_hint='synthetic')=={}
    q=stage.plan(source,{ref:pose},board_hint='synthetic',retain_projected_ground_entries=True)
    result=stage.construct(source,tmp_path/'zero-return-follow',json.loads(json.dumps(q)))
    assert result['ok']and result['complete'],result.get('receiving',{}).get('errors',result)
    child=pcbnew.LoadBoard(result['candidate']);future=child.FindFootprintByReference(ref).FindPadByNumber('2')
    witness=contact.cell._existing_return(child,future,16.,allow_native_track_body=True)
    assert witness is not None and witness[0]==0.
    carried=result['receiving']['independent_Source_pose_reconstruction']['source_ground_barrel_transport']
    assert len(carried['changes'])==1 and carried['changes'][0]['uuid']==force._uid(v)
    assert 'independently_retained_projected_ground_contacts'not in carried
    after=inventory(child);assert {u for u in before if before[u]!=after[u]}=={force._uid(v)}


@pytest.mark.parametrize('timeout',[None,True,0,10.01,float('nan'),float('inf')])
def test_helper_has_a_finite_strict_native_work_lease(tmp_path,timeout):
    source,ref,uid,pad,via,stem,pose,groups=fixture(tmp_path)
    board=pcbnew.LoadBoard(str(source));before=inventory(board)
    with pytest.raises(ValueError):contact.plan_capacitor_entries(board,{ref:pose},board_hint='synthetic',timeout_s=timeout)
    assert inventory(board)==before


@pytest.mark.parametrize('back',[False,True])
def test_closed_reference_maps_still_follow_only_their_own_source_capacitor(tmp_path,back):
    source,child,q,uid,pad,via,stem=build(tmp_path,back=back,mapped=True)
    proof=stage.receive(source,child,q)
    assert proof['ok']and proof['complete'],proof
    exact=proof['independent_Source_pose_reconstruction']
    assert exact['all_source_reference_group_memberships_and_locks_preserved']
    assert exact['source_closed_reference_maps_translated_with_own_passives']


@pytest.mark.parametrize('fault',['source','candidate','sidecar'])
def test_late_mutation_is_not_hidden_by_the_new_entry_policy(tmp_path,monkeypatch,fault):
    source,child,q,uid,pad,via,stem=build(tmp_path);inner=stage.pose_receiving.receive
    def changed(*args,**kwargs):
        proof=inner(*args,**kwargs);assert proof['ok'],proof
        if fault=='sidecar':child.with_suffix('.kicad_pro').write_text(json.dumps({'late':True}))
        else:
            path=source if fault=='source'else child
            board=pcbnew.LoadBoard(str(path));props=board.GetProperties();props['LATE']='mutation';board.SetProperties(props)
            field._save_field_snapshot(board,path)
        return proof
    monkeypatch.setattr(stage.pose_receiving,'receive',changed)
    proof=stage.receive(source,child,q)
    assert not proof['ok']and proof['errors']
