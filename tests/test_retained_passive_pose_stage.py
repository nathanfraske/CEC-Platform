"""Closed maps do not replace exact Source copper/contact reconstruction."""
import copy
import json
from pathlib import Path

import pcbnew
import pytest
import cec_field_coupling as field
import cec_force_current as force
import cec_pose_additive_reconstruction as receiving
import cec_retained_passive_pose_stage as stage
import cec_source_reference_group_transport as maps
from test_retained_copper_passive_pose import fixture as passive_fixture


def fixture(tmp_path, *, back=False, quarter=0, capacitor=False):
    source,_,owner,_=passive_fixture(tmp_path,back=back,quarter=quarter)
    board=pcbnew.LoadBoard(str(source))
    fp=next(f for f in board.GetFootprints()if force._uid(f)==owner)
    fp.SetReference('R87')
    if capacitor:
        fp.SetReference('C91');fp.SetValue('100nF')
        fp.SetFPID(pcbnew.LIB_ID('Capacitor_SMD','C_0603_1608Metric'))
    fp.Reference().SetVisible(False)
    origin=tuple(fp.GetPosition());x,y=origin
    vertices=[(x-2000000,y-1500000),(x+2000000,y-1500000),
              (x+2000000,y+1500000),(x-2000000,y+1500000)]
    court_face=pcbnew.B_CrtYd if back else pcbnew.F_CrtYd
    for a,z in zip(vertices,vertices[1:]+vertices[:1]):
        line=pcbnew.PCB_SHAPE(fp);line.SetShape(pcbnew.SHAPE_T_SEGMENT)
        line.SetLayer(court_face);line.SetStart(pcbnew.VECTOR2I(*a));line.SetEnd(pcbnew.VECTOR2I(*z))
        line.SetWidth(50000);fp.Add(line)
    chain=fp.GetCourtyard(fp.GetLayer()).COutline(0)
    vertices=[tuple(chain.CPoint(i))for i in range(chain.PointCount())]
    group=pcbnew.PCB_GROUP(board);group.SetName(maps.PREFIX+fp.GetReference());board.Add(group)
    group.AddItem(fp)
    face=pcbnew.F_SilkS if back else pcbnew.B_SilkS
    text=pcbnew.PCB_TEXT(board);text.SetText(fp.GetReference());text.SetLayer(face)
    rules=maps._cardinal_rules(source,board);settings=board.GetDesignSettings()
    height=max(800000,round(rules['silk_height']*1e6),settings.m_MinSilkTextHeight)
    stroke=max(120000,round(rules['silk']*1e6),settings.m_MinSilkTextThickness)
    text.SetMirrored(not back);text.SetTextSize(pcbnew.VECTOR2I(height,height))
    text.SetTextThickness(stroke);text.SetTextPos(pcbnew.VECTOR2I(*origin));text.SetKeepUpright(True)
    text.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER);text.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER)
    board.Add(text);group.AddItem(text)
    for a,z in zip(vertices,vertices[1:]+vertices[:1]):
        line=pcbnew.PCB_SHAPE(board);line.SetShape(pcbnew.SHAPE_T_SEGMENT)
        line.SetLayer(face);line.SetStart(pcbnew.VECTOR2I(*a));line.SetEnd(pcbnew.VECTOR2I(*z))
        line.SetWidth(stroke);board.Add(line);group.AddItem(line)
    group.SetLocked(True);fp.SetLocked(False)
    field._save_field_snapshot(board,source)
    dx,dy=((0,.12),(.12,0),(0,-.12),(-.12,0))[quarter]
    if back:dx=-dx
    pose=[x/1e6+dx,y/1e6+dy,fp.GetOrientationDegrees()]
    return source,owner,force._uid(group),fp.GetReference(),pose


def build(tmp_path, **kwargs):
    source,owner,group,ref,pose=fixture(tmp_path,**kwargs)
    q=stage.plan(source,{ref:pose},board_hint='synthetic',reference_group_uuids=[group])
    # The actual public saved JSON boundary, not Python-object equality.
    q=json.loads(json.dumps(q))
    result=stage.construct(source,tmp_path/'received',q)
    assert result['ok']and result['complete'],result
    return source,Path(result['candidate']),q,owner,group


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('capacitor',[False,True])
def test_saved_mapped_capacitor_and_resistor_translation_is_exact(tmp_path,back,quarter,capacitor):
    source,target,q,owner,group=build(tmp_path,back=back,quarter=quarter,capacitor=capacitor)
    before=source.read_bytes();sidecars=force._sidecars(source)
    proof=stage.receive(source,target,q)
    assert proof['ok']and proof['complete'],proof
    exact=proof['independent_Source_pose_reconstruction']
    assert exact['all_source_reference_group_memberships_and_locks_preserved']
    assert exact['all_original_terminal_and_copper_partitions_preserved']
    assert exact['all_source_tracks_and_arcs_retained_exactly']
    assert not proof['current_qualified']and not proof['release_authority']
    assert source.read_bytes()==before and force._sidecars(source)==sidecars


@pytest.mark.parametrize('fault',['ink','label','group_unlock','group_rename','member_remove',
    'unrelated_fp','track','positive_via','ground_size','metadata','sidecar'])
def test_map_authority_cannot_hide_unowned_saved_changes(tmp_path,fault):
    source,target,q,owner,group=build(tmp_path)
    board=pcbnew.LoadBoard(str(target));g=next(g for g in board.Groups()if force._uid(g)==group)
    if fault=='ink':next(i for i in g.GetItems()if i.GetClass()=='PCB_SHAPE').Move(pcbnew.VECTOR2I(1,0))
    elif fault=='label':next(i for i in g.GetItems()if i.GetClass()=='PCB_TEXT').Move(pcbnew.VECTOR2I(1,0))
    elif fault=='group_unlock':g.SetLocked(False)
    elif fault=='group_rename':g.SetName('FORGED')
    elif fault=='member_remove':g.RemoveItem(next(i for i in g.GetItems()if i.GetClass()=='PCB_SHAPE'))
    elif fault=='unrelated_fp':next(f for f in board.GetFootprints()if force._uid(f)!=owner).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='track':next(t for t in board.GetTracks()if t.GetClass()=='PCB_TRACK').SetWidth(210000)
    elif fault=='positive_via':next(t for t in board.GetTracks()if t.GetClass()=='PCB_VIA'and t.GetNetname()!='GND').Move(pcbnew.VECTOR2I(1,0))
    elif fault=='ground_size':next(t for t in board.GetTracks()if t.GetClass()=='PCB_VIA'and t.GetNetname()=='GND').SetDrill(240000)
    elif fault=='metadata':
        props=board.GetProperties();props['FORGED']='unowned';board.SetProperties(props)
    if fault=='sidecar':target.with_suffix('.kicad_pro').write_text(json.dumps({'forged':True}))
    else:field._save_field_snapshot(board,target)
    before=source.read_bytes()
    proof=stage.receive(source,target,q)
    assert not proof['ok']and proof['errors'],proof
    assert source.read_bytes()==before


@pytest.mark.parametrize('fault',['pose','source','family','code','selected','group','current','new_copper',
    'integer_false','float_false'])
def test_saved_proposal_is_not_caller_authority(tmp_path,fault):
    source,target,q,owner,group=build(tmp_path)
    bad=copy.deepcopy(q)
    if fault=='pose':bad['poses'][next(iter(bad['poses']))][0]+=.000001
    elif fault=='source':bad['source_sha256']='0'*64
    elif fault=='family':bad['source_family']={}
    elif fault=='code':bad['code_identity']={}
    elif fault=='selected':bad['selected_footprint_uuids'].append('invented')
    elif fault=='group':bad['reference_group_uuids']=[]
    elif fault=='current':bad['current_qualified']=True
    elif fault=='new_copper':bad['new_conductors_authorized']=True
    elif fault=='integer_false':bad['new_conductors_authorized']=0
    elif fault=='float_false':bad['new_conductors_authorized']=0.0
    assert not stage.receive(source,target,bad)['ok']


@pytest.mark.parametrize('fault',['omitted','unselected','duplicate','string','boolean','many','ordinary_mode'])
def test_reference_scope_is_explicit_not_a_group_allowlist(tmp_path,fault):
    source,target,q,owner,group=build(tmp_path)
    kwargs=dict(selected_footprint_uuids=[owner],board_hint='synthetic',max_shift_mm=6.,
        allow_source_ground_barrel_motion=True,reference_group_uuids=[group])
    if fault=='omitted':kwargs['reference_group_uuids']=[]
    elif fault=='unselected':kwargs['selected_footprint_uuids']=['invented']
    elif fault=='duplicate':kwargs['reference_group_uuids']=[group,group]
    elif fault=='string':kwargs['reference_group_uuids']=group
    elif fault=='boolean':kwargs['reference_group_uuids']=[True]
    elif fault=='many':kwargs['reference_group_uuids']=[str(i)for i in range(9)]
    elif fault=='ordinary_mode':kwargs['allow_source_ground_barrel_motion']=False
    proof=receiving.receive(source,target,**kwargs)
    assert not proof['ok']and proof['errors'],proof


@pytest.mark.parametrize('turn',[90,180,270])
def test_mapped_passive_rotation_is_not_enabled_by_annotation_translation(tmp_path,turn):
    source,owner,group,ref,pose=fixture(tmp_path)
    pose[2]+=turn
    q=stage.plan(source,{ref:pose},board_hint='synthetic',reference_group_uuids=[group])
    with pytest.raises(ValueError,match='translation_only'):
        stage.construct(source,tmp_path/'rotated',q)


@pytest.mark.parametrize('fault',['name','nested','copper_member','missing_court'])
def test_unrecognized_Source_map_never_falls_back_to_fab_or_name(tmp_path,fault):
    source,owner,group,ref,pose=fixture(tmp_path)
    board=pcbnew.LoadBoard(str(source));g=next(g for g in board.Groups()if force._uid(g)==group)
    fp=board.FindFootprintByReference(ref)
    if fault=='name':g.SetName('arbitrary')
    elif fault=='nested':
        outer=pcbnew.PCB_GROUP(board);board.Add(outer);outer.AddItem(g)
    elif fault=='copper_member':g.AddItem(next(iter(board.GetTracks())))
    elif fault=='missing_court':
        for line in fp.GraphicalItems():
            if line.GetLayer()==pcbnew.F_CrtYd:line.SetLayer(pcbnew.F_Fab)
    field._save_field_snapshot(board,source);before=source.read_bytes()
    q=stage.plan(source,{ref:pose},board_hint='synthetic',reference_group_uuids=[group])
    with pytest.raises(ValueError):stage.construct(source,tmp_path/'refused',q)
    assert source.read_bytes()==before


def test_mixed_mapped_and_unmapped_passives_have_one_exact_transform_each(tmp_path):
    import cec_fr as fr
    from test_field_proposals import track
    source,owner,group,ref,pose=fixture(tmp_path)
    board=pcbnew.LoadBoard(str(source))
    fp=pcbnew.FOOTPRINT(board);fp.SetReference('R88');fp.SetValue('47k')
    fp.SetFPID(pcbnew.LIB_ID('Resistor_SMD','R_0603_1608Metric'))
    fp.SetPosition(pcbnew.VECTOR2I_MM(22,14));board.Add(fp)
    for pin,net,x in [('1','/CONTROL',21.2),('2','GND',22.8)]:
        pad=pcbnew.PAD(fp);pad.SetPadName(pin);pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetSize(pcbnew.VECTOR2I_MM(.8,.8))
        pad.SetPosition(pcbnew.VECTOR2I_MM(x,14));pad.SetLayerSet(pcbnew.PAD.SMDMask())
        pad.SetNetCode(board.GetNetcodeFromNetname(net));fp.Add(pad)
    vias=[]
    for net,x in [('GND',22.8),('/CONTROL',20.6)]:
        via=pcbnew.PCB_VIA(board);via.SetNetCode(board.GetNetcodeFromNetname(net))
        via.SetViaType(pcbnew.VIATYPE_THROUGH);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        via.SetPosition(pcbnew.VECTOR2I_MM(x,14));via.SetWidth(350000);via.SetDrill(250000)
        board.Add(via);vias.append(via)
    track(board,'/CONTROL',(20.6,14),(21.2,14))
    assert fr.group_local_pofv_signal_vias(board,vias)
    field._save_field_snapshot(board,source)
    q=stage.plan(source,{ref:pose,'R88':[22.,14.12,0.]},
        board_hint='synthetic',reference_group_uuids=[group])
    r=stage.construct(source,tmp_path/'mixed',q)
    assert r['ok']and r['complete'],r
    assert stage.receive(source,r['candidate'],q)['ok']


def test_exact_saved_transaction_dispatch_and_schema(tmp_path):
    from test_detached_passive_transaction import wrapper
    module=wrapper();source,target,q,owner,group=build(tmp_path)
    proposal=tmp_path/'proposal.json';proposal.write_text(json.dumps(q))
    row=dict(kind='retained_passive_pose',candidate=str(target),
        candidate_sha256=force._hash(target),proposal=str(proposal))
    assert module.validate_phases([row])==['retained_passive_pose']
    candidate,proof=module.receive_phase(source,source,row,'synthetic')
    assert candidate==target and proof['ok']and proof['complete']
    with pytest.raises(ValueError):module.validate_phases([row,row])
    with pytest.raises(ValueError):module.validate_phases([dict(row,allow_new_copper=True)])
    q['new_conductors_authorized']=0;proposal.write_text(json.dumps(q))
    with pytest.raises(AssertionError):module.receive_phase(source,source,row,'synthetic')


@pytest.mark.parametrize('fault',[None,'narrow','unlisted_cut'])
def test_full_current_preclear_dispatch_retains_its_original_authority(tmp_path,fault):
    from unittest.mock import patch
    from test_detached_passive_transaction import wrapper
    from test_full_current_planar_reflow import fixture as current_fixture
    module=wrapper()
    source,target,uid,net,contract,domains=current_fixture(tmp_path)
    if fault=='narrow':
        board=pcbnew.LoadBoard(str(target));next(iter(board.GetTracks())).SetWidth(999999)
        field._save_field_snapshot(board,target)
    row=dict(kind='full_current_planar_reflow',candidate=str(target),
        candidate_sha256=force._hash(target),retired_track_uuids=[uid])
    if fault=='unlisted_cut':row['retired_track_uuids']=['invented']
    assert module.validate_phases([row])==['full_current_planar_reflow']
    with patch.object(module.full_current_planar.topology,'route_width_contracts',return_value={net:contract}), \
         patch.object(module.full_current_planar.topology,'board_current_domains',return_value=domains):
        if fault:
            with pytest.raises(AssertionError):module.receive_phase(source,source,row,'synthetic')
        else:
            received,proof=module.receive_phase(source,source,row,'synthetic')
            assert received==Path(target) and proof['ok']and proof['complete']
            assert proof['source_width_and_current_exact']
            assert not proof['routing_admitted']and not proof['release_authority']
    with pytest.raises(ValueError):module.validate_phases([dict(row,amps=.1)])
    with pytest.raises(ValueError):module.validate_phases([row,row])


@pytest.mark.parametrize('fault',['metadata','track','sidecar'])
def test_saved_candidate_cannot_change_after_inner_pose_receiving(tmp_path,monkeypatch,fault):
    source,target,q,owner,group=build(tmp_path)
    original=stage.pose_receiving.receive
    def late_write(*args,**kwargs):
        result=original(*args,**kwargs)
        assert result['ok']and result['complete'],result
        if fault=='sidecar':target.with_suffix('.kicad_pro').write_text(json.dumps({'late':True}))
        else:
            board=pcbnew.LoadBoard(str(target))
            if fault=='metadata':
                props=board.GetProperties();props['LATE_WORKER_WRITE']='unreceived';board.SetProperties(props)
            else:next(t for t in board.GetTracks()if t.GetClass()=='PCB_TRACK').SetWidth(210000)
            field._save_field_snapshot(board,target)
        return result
    monkeypatch.setattr(stage.pose_receiving,'receive',late_write)
    result=stage.receive(source,target,q)
    assert not result['ok']and any('changed_during_receiving'in e for e in result['errors']),result
