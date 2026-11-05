"""Keep a full native Ground entry; do not waive process, width or locality."""
import copy,json,time,math
from pathlib import Path
import pcbnew
import pytest
import cec_projected_ground_contact as op
import cec_cell_escape_replan as cell
import cec_field_coupling as field
import cec_force_current as force
import cec_additive_route_receiving as additive
from cec_native_items import discard_items
from test_native_ground_terminal_branch import fixture as base_fixture
from test_field_proposals import track
from test_cell_escape_replan import fixture as complete_fixture


def fixture(tmp_path,quarter=0,back=False,turn=90):
    b,source,ids,ports,owner,cap,via=base_fixture(tmp_path,quarter=quarter,layer=pcbnew.B_Cu if back else pcbnew.F_Cu)
    before={force._uid(p):tuple(p.GetPosition()) for p in cap.Pads()}
    root=cap.FindPadByNumber('2');ground=tuple(root.GetPosition())
    # Rebase the native package anchor without changing any source land.
    cap.SetPosition(pcbnew.VECTOR2I(ground[0],ground[1]-400000))
    for pad in cap.Pads():pad.SetPosition(pcbnew.VECTOR2I(*before[force._uid(pad)]))
    root.SetSize(pcbnew.VECTOR2I_MM(.56,.62))
    # Native footprint angles rotate clockwise in board coordinates.
    angle=math.radians(turn);dx=ground[0]-cap.GetPosition().x;dy=ground[1]-cap.GetPosition().y
    rx=round(dx*math.cos(angle)+dy*math.sin(angle));ry=round(-dx*math.sin(angle)+dy*math.cos(angle))
    target=[(ground[0]-rx)/1e6,(ground[1]-ry)/1e6,cap.GetOrientationDegrees()+turn]
    b.SetFileName(str(source));field._save_field_snapshot(b,source)
    return b,source,owner,cap,root,via,target


def plan(b,root,target):return op.plan(b,force._uid(root),target,board_hint='synthetic')


def apply(b,cap,target):
    cap.SetPosition(pcbnew.VECTOR2I(*(round(v*1e6) for v in target[:2])));cap.SetOrientationDegrees(target[2])


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('turn',[90,180,270])
def test_projected_real_land_preserves_source_entry_across_rigid_frames_without_new_copper(tmp_path,quarter,back,turn):
    b,source,owner,cap,root,via,target=fixture(tmp_path,quarter,back,turn)
    before=cell.row._source_binding(b);raw=source.read_bytes();q=plan(b,root,target)
    assert cell.row._source_binding(b)==before and source.read_bytes()==raw
    assert q['complete_source_entry_disk_contained'] and not q['entire_source_land_unchanged']
    assert q['source_ground_role']['kind']=='source_selected_bypass_ground'
    assert not q['current_qualified'] and q['no_new_copper_or_hole']
    apply(b,cap,target);native=cell.row._source_binding(b)
    saved=json.loads(json.dumps(q));r=op.observe(b,root,saved)
    assert r and r['saved_return_mm']<=r['source_return_mm']+.000001 and r['full_source_entry_preserved_after_all_cuts']
    assert not r['full_class_direct_reference_reach_proved'] and not r['new_immediate_return_qualification']
    assert cell.row._source_binding(b)==native and source.read_bytes()==raw


@pytest.mark.parametrize('fault',['entry_sliver','not_ground','non_smd','unknown_owner','no_plane','missing_plane',
    'no_profile','no_source','unsaved_source','noncardinal','far','no_entry_axis'])
def test_partial_contact_unknown_role_or_unqualified_reference_is_not_retention_authority(tmp_path,fault):
    b,source,owner,cap,root,via,target=fixture(tmp_path)
    if fault=='entry_sliver':target[0]+=.24
    elif fault=='not_ground':root.SetNet(b.FindNet('+3V3'))
    elif fault=='non_smd':root.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    elif fault=='unknown_owner':owner.SetValue('UNKNOWN')
    elif fault=='no_plane':
        for z in b.Zones():z.UnFill()
    elif fault=='missing_plane':next(iter(b.Zones())).UnFill()
    elif fault=='no_profile':
        props=b.GetProperties();props['CEC_FAB_PROFILE']='';b.SetProperties(props)
    elif fault=='no_source':b.SetFileName('')
    elif fault=='unsaved_source':next(iter(b.GetTracks())).SetLocked(True)
    elif fault=='noncardinal':target[2]+=1.
    elif fault=='far':target[0]+=33.
    elif fault=='no_entry_axis':
        for t in b.GetTracks():
            if t.GetClass()=='PCB_TRACK' and t.GetNetname()=='GND':t.Move(pcbnew.VECTOR2I(1,0))
    # Present the actual hostile source except when testing an unsaved state.
    if fault not in ('no_source','unsaved_source'):pcbnew.SaveBoard(str(source),b)
    before=cell.row._source_binding(b)
    with pytest.raises((ValueError,RuntimeError)):plan(b,root,target)
    assert cell.row._source_binding(b)==before


@pytest.mark.parametrize('fault',['anchor_missing','anchor_width','anchor_pose','via_hole','via_pose','unfilled_plane',
    'changed_land','forged_return','forged_width','forged_role'])
def test_saved_live_observation_rederives_source_and_rejects_changed_contacts_after_other_cuts(tmp_path,fault):
    b,source,owner,cap,root,via,target=fixture(tmp_path);q=json.loads(json.dumps(plan(b,root,target)));apply(b,cap,target)
    anchors={force._uid(t):t for t in b.GetTracks()};anchor=anchors[q['source_entry_native_uuids'][0]]
    if fault=='anchor_missing':discard_items(b,[anchor])
    elif fault=='anchor_width':anchor.SetWidth(199999)
    elif fault=='anchor_pose':anchor.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='via_hole':via.SetDrill(250000)
    elif fault=='via_pose':via.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='unfilled_plane':next(iter(b.Zones())).UnFill()
    elif fault=='changed_land':root.SetSize(pcbnew.VECTOR2I_MM(.55,.62))
    elif fault=='forged_return':q['source_return_mm']+=1.
    elif fault=='forged_width':q['entry_width_nm']=199999
    else:q['source_ground_role']['kind']='ordinary_ground_guess'
    before=cell.row._source_binding(b)
    try:r=op.observe(b,root,q)
    except ValueError:r=None
    assert r is None and cell.row._source_binding(b)==before


@pytest.mark.parametrize('value',[0,True,11,float('nan'),float('inf'),None])
def test_projected_ground_contact_has_finite_explicit_work_lease(tmp_path,value):
    b,source,owner,cap,root,via,target=fixture(tmp_path);before=cell.row._source_binding(b)
    with pytest.raises(ValueError):op.plan(b,force._uid(root),target,board_hint='synthetic',timeout_s=value)
    assert cell.row._source_binding(b)==before


@pytest.mark.parametrize('short',[False,True])
def test_cell_menu_keeps_short_source_entry_but_does_not_waive_a_long_old_return(tmp_path,short):
    b,source,owner,cap,root,via,target=fixture(tmp_path,turn=90)
    if short:
        at=tuple(root.GetPosition());v=pcbnew.PCB_VIA(b);v.SetNet(b.FindNet('GND'))
        v.SetPosition(pcbnew.VECTOR2I(at[0],at[1]+700000));v.SetWidth(600000);v.SetDrill(300000)
        v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v)
        track(b,'GND',[a/1e6 for a in at],[at[0]/1e6,at[1]/1e6+.7],width=.2)
        additive._ground_refill(b);field._save_field_snapshot(b,source)
    q=plan(b,root,target);apply(b,cap,target);before=cell.row._source_binding(b)
    request=dict(kind='ground',net='GND',a=dict(pad_uuid=force._uid(root)),reach_mm=.8,
        retained_projected_source_return=json.loads(json.dumps(q)))
    menu=cell.menus(b,{'return':request},board_path=str(source),board_hint='synthetic')
    assert cell.row._source_binding(b)==before
    empty=[choice for choice in menu['domains']['return'] if not choice['ops']]
    if short:
        assert empty and menu['diagnostics']['return']['inherited_projected_source_return']['full_class_direct_reference_reach_proved']
        assert menu['diagnostics']['return']['inherited_projected_source_return']['saved_return_mm']<=.8
    else:
        assert not empty and 'inherited_projected_source_return' not in menu['diagnostics']['return']


@pytest.mark.parametrize('fault',[None,'forged_entry','forged_role','forged_land','missing_anchor'])
def test_complete_cell_rederives_contact_retention_before_pose_and_saved_menu_reuse(tmp_path,monkeypatch,fault):
    b,poses,owner,cap=complete_fixture(monkeypatch,prefix='independent_ground_pivot')
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';b.SetProperties(props)
    root=cap.FindPadByNumber('2');at=tuple(root.GetPosition())
    via=pcbnew.PCB_VIA(b);via.SetNet(b.FindNet('GND'));via.SetPosition(pcbnew.VECTOR2I(at[0]+750000,at[1]))
    via.SetWidth(600000);via.SetDrill(300000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(via)
    stem=track(b,'GND',[v/1e6 for v in at],[(at[0]+750000)/1e6,at[1]/1e6],width=.2)
    for face in (pcbnew.In1_Cu,pcbnew.In4_Cu):
        z=pcbnew.ZONE(b);z.SetNet(b.FindNet('GND'));z.SetLayer(face);z.SetLocalClearance(200000)
        z.SetMinThickness(100000);z.Outline().NewOutline()
        for x,y in ((1,1),(25,1),(25,25),(1,25)):z.Outline().Append(x*1000000,y*1000000)
        b.Add(z)
    additive._ground_refill(b)
    poses={owner.GetReference():[owner.GetPosition().x/1e6,owner.GetPosition().y/1e6,owner.GetOrientationDegrees()],
        cap.GetReference():[at[0]/1e6,at[1]/1e6+.5,90.]}
    source=tmp_path/'complete-source.kicad_pcb';b.SetFileName(str(source));field._save_field_snapshot(b,source)
    parent=pcbnew.LoadBoard(str(source));q=json.loads(json.dumps(cell.prepare(b,poses,board_hint='synthetic')))
    proof=q['native_projected_ground_contacts'][force._uid(root)]
    assert force._uid(stem) not in q['retired_track_uuids'] and proof['source_return_mm']==.75
    if fault is not None:
        if fault=='forged_entry':proof['source_entry_nm'][0]+=1
        elif fault=='forged_role':proof['source_ground_role']['kind']='untyped_ground'
        elif fault=='forged_land':proof['future_land_sha256']='not-source-native-land'
        else:proof['source_entry_native_uuids']=[]
        before=cell.row._source_binding(b)
        with pytest.raises(ValueError):cell.apply_private(b,q)
        assert cell.row._source_binding(b)==before;return
    cell.apply_private(b,q);requests=cell.obligations(parent,b,q)
    key='ground:'+force._uid(root);request=requests[key]
    assert request['retained_projected_source_return']==proof
    before=cell.row._source_binding(b)
    menu=cell.menus(b,{key:request},board_path=str(source),board_hint='synthetic')
    assert any(not v['ops'] for v in menu['domains'][key])
    assert cell.row._source_binding(b)==before and force._uid(stem) in {force._uid(t) for t in b.GetTracks()}


@pytest.mark.parametrize('at,diameter,expected',[
    ((10,8),.6,True),((9,8),.6,True),((8,8),.6,True),
    ((10,8.25),.6,False),((10.1,8),.6,False),((10,8),.2,False)])
def test_direct_reference_credit_requires_full_source_stroke_on_exact_barrel_axis(at,diameter,expected):
    b=pcbnew.BOARD();b.Add(pcbnew.NETINFO_ITEM(b,'GND'))
    t=track(b,'GND',(8,8),(10,8),width=.2)
    v=pcbnew.PCB_VIA(b);v.SetNet(b.FindNet('GND'));v.SetPosition(pcbnew.VECTOR2I_MM(*at))
    v.SetWidth(round(diameter*1e6));v.SetDrill(100000);b.Add(v)
    assert op._direct_full_axis(t,v,pcbnew.F_Cu)==expected


def test_live_reference_via_cannot_silently_change_source_process_group(tmp_path):
    b,source,owner,cap,root,via,target=fixture(tmp_path);q=json.loads(json.dumps(plan(b,root,target)))
    apply(b,cap,target);g=pcbnew.PCB_GROUP(b);g.SetName('INVENTED_PROCESS_OWNER');b.Add(g);g.AddItem(via)
    before=cell.row._source_binding(b)
    assert op.observe(b,root,q) is None and cell.row._source_binding(b)==before
