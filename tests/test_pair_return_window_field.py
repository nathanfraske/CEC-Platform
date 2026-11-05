"""An existing local-reference role is not an ordinary Ground/current waiver."""
import copy,json,time
from pathlib import Path
import pcbnew as pcb
import pytest
import cec_constraints as constraints
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_pair_return_window_field as operation
import cec_zone_fill as fill
from test_pair_reference_clearance_window import fixture as base_fixture


def xy(point,quarter,back):
    x,y=point
    if back:x=20-x
    x,y=x-10,y-10
    for _ in range(quarter):x,y=y,-x
    return x+10,y+10


def fixture(tmp_path,quarter=0,back=False,selection='preferred'):
    source,args,foreign=base_fixture(tmp_path,quarter=quarter,back=back)
    board=pcb.LoadBoard(str(source));owned=[]
    for point in ((12.9,7.2),(12.9,9.8)):
        via=pcb.PCB_VIA(board);via.SetViaType(pcb.VIATYPE_THROUGH);via.SetLayerPair(pcb.F_Cu,pcb.B_Cu)
        via.SetPosition(pcb.VECTOR2I_MM(*xy(point,quarter,back)));via.SetWidth(600000);via.SetDrill(300000)
        via.SetNet(board.FindNet('GND'));board.Add(via);owned.append(via)
    fr.group_local_pair_return_vias(board,owned)
    selected=pcb.ZONES()
    for zone in board.Zones():selected.append(zone)
    fill.compile_selected(board,selected,initialize_selected=True);field._save_field_snapshot(board,source)
    positions=[list(pcb.VECTOR2I_MM(*xy(p,quarter,back)))for p in ((7,7.1),(7,9.9))]
    args.pop('position_nm');args.update(positions_nm=positions,geometry_selection=selection)
    return source,args,foreign


def saved(tmp_path,**options):
    source,args,foreign=fixture(tmp_path,**options);proposal=operation.plan(source,**args)
    made=operation.write_private(proposal,tmp_path/'candidate')
    return source,Path(made['candidate']),args,proposal,foreign


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('selection',['preferred','board-minimum-land-same-drill'])
def test_existing_source_role_and_same_drill_menu_generalize_in_native_frames(tmp_path,quarter,back,selection):
    source,child,args,proposal,foreign=saved(tmp_path,quarter=quarter,back=back,selection=selection)
    before=source.read_bytes();result=operation.receive(source,child,**args)
    assert result['ok']and result['complete'],result
    authority=proposal['local_reference_authority']
    assert authority['diameter_nm']==(600000 if selection=='preferred'else 500000)
    assert authority['drill_nm']==300000 and authority['ordinary_Ground_class_not_changed']
    assert authority['spacing_and_process_authority']['class_spec']['via_diameter']==.9
    assert authority['spacing_and_process_authority']['class_spec']['via_drill']==.5
    assert result['every_Source_native_partition_identical']and result['complete_local_return_field_received']
    assert len(result['construction']['independently_qualified_new_local_return_uuids'])==2
    assert result['construction']['all_face_native_new_hole_geometry_received']
    assert result['construction']['local_foreign_subtractions'][0]['authorized_mask_is_exact_Source_windows_not_bbox']
    assert not result['routing_admitted']and not result['current_capacity_qualified']and not result['release_authority']
    assert source.read_bytes()==before


@pytest.mark.parametrize('fault',['group_absent','group_unqualified','ambiguous_geometry','one_missing_member',
    'duplicate_seat','too_many_seats','remote','wrong_pair','wrong_barrel','unknown_selection',
    'saved_rule_floor','project_absent','profile_absent','foreign_track'])
def test_positive_Source_geometry_role_and_complete_field_are_mandatory(tmp_path,fault):
    source,args,_=fixture(tmp_path);board=pcb.LoadBoard(str(source));groups=list(board.Groups())
    changed=False
    if fault=='group_absent':groups[0].SetName('NOT_THE_SOURCE_ROLE');changed=True
    elif fault=='group_unqualified':
        for via in groups[0].GetItems():via.Move(pcb.VECTOR2I_MM(4,4))
        changed=True
    elif fault=='ambiguous_geometry':
        via=next(iter(groups[0].GetItems()));via.SetWidth(700000);via.SetDrill(400000);changed=True
    elif fault=='one_missing_member':args['positions_nm']=args['positions_nm'][:1]
    elif fault=='duplicate_seat':args['positions_nm'][1]=args['positions_nm'][0]
    elif fault=='too_many_seats':args['positions_nm'].append([1000000,1000000])
    elif fault=='remote':args['positions_nm'][1]=[17000000,17000000]
    elif fault=='wrong_pair':args['pair_name']='undefined'
    elif fault=='wrong_barrel':args['signal_via_uuids'][0]=force._uid(next(iter(groups[0].GetItems())))
    elif fault=='unknown_selection':args['geometry_selection']='smaller than the Source menu'
    elif fault=='project_absent':source.with_suffix('.kicad_pro').unlink()
    elif fault=='saved_rule_floor':source.with_suffix('.kicad_dru').write_text(
        '(version 1)(rule "strict unchanged"(constraint via_diameter(min .8mm)))')
    elif fault=='profile_absent':
        props=board.GetProperties();props.erase('CEC_FAB_PROFILE');board.SetProperties(props);changed=True
    else:
        edge=pcb.PCB_TRACK(board);edge.SetNet(board.FindNet('UNRELATED_POWER'));edge.SetLayer(pcb.In3_Cu)
        edge.SetWidth(250000);edge.SetStart(pcb.VECTOR2I_MM(6,7.1));edge.SetEnd(pcb.VECTOR2I_MM(8,7.1));board.Add(edge);changed=True
    if changed:field._save_field_snapshot(board,source)
    with pytest.raises(ValueError):
        proposal=operation.plan(source,**args);operation.write_private(proposal,tmp_path/'bad')


@pytest.mark.parametrize('fault',['width','drill','axis','unlock','net','remove_owned_group_member',
    'extra_copper','retired_Source','Source_part','Source_fill','Source_outline','sidecar'])
def test_exact_saved_Field_and_every_original_primitive_are_independently_received(tmp_path,fault):
    source,child,args,proposal,foreign=saved(tmp_path);board=pcb.LoadBoard(str(child))
    old={force._uid(t)for t in pcb.LoadBoard(str(source)).GetTracks()}
    via=next(t for t in board.GetTracks()if force._uid(t)not in old)
    if fault=='width':via.SetWidth(via.GetWidth()+1)
    elif fault=='drill':via.SetDrill(via.GetDrillValue()+1)
    elif fault=='axis':via.Move(pcb.VECTOR2I(1,0))
    elif fault=='unlock':via.SetLocked(False)
    elif fault=='net':via.SetNet(board.FindNet('/CAN_H'))
    elif fault=='remove_owned_group_member':next(iter(board.Groups())).RemoveItem(via)
    elif fault=='retired_Source':board.Remove(next(t for t in board.GetTracks()if force._uid(t)in old))
    elif fault=='Source_part':next(iter(board.GetFootprints())).Move(pcb.VECTOR2I(1,0))
    elif fault=='Source_fill':next(z for z in board.Zones()if force._uid(z)==foreign).UnFill()
    elif fault=='Source_outline':next(z for z in board.Zones()if force._uid(z)==foreign).Move(pcb.VECTOR2I(1,0))
    elif fault=='sidecar':child.with_suffix('.kicad_pro').write_text('{}')
    else:
        edge=pcb.PCB_TRACK(board);edge.SetNet(board.FindNet('GND'));edge.SetWidth(500000)
        edge.SetStart(pcb.VECTOR2I_MM(17,17));edge.SetEnd(pcb.VECTOR2I_MM(18,17));board.Add(edge)
    if fault!='sidecar':pcb.PCB_IO_KICAD_SEXPR().SaveBoard(str(child),board)
    result=operation.receive(source,child,**args)
    assert not result['ok']and not result['complete']and result['errors']


@pytest.mark.parametrize('key,value',[('positions_nm',[[1,2],[3,4]]),('pair_nets',['GND','UNRELATED_POWER']),
    ('foreign_zones',[]),('Source_missing_return_uuids',[])])
def test_derived_Source_scope_is_not_a_caller_cut_list(tmp_path,key,value):
    source,args,_=fixture(tmp_path);proposal=operation.plan(source,**args)
    forged=copy.deepcopy(proposal);forged[key]=value
    with pytest.raises(ValueError):operation.write_private(forged,tmp_path/'forged')


def test_bbox_between_disjoint_windows_is_not_a_removal_grant():
    def rect(a,b,c,d):
        shape=pcb.SHAPE_POLY_SET();shape.NewOutline()
        for x,y in((a,b),(c,b),(c,d),(a,d)):shape.Append(x,y)
        return shape
    before=rect(0,0,1000000,1000000);compiled=before.CloneDropTriangulation()
    compiled.BooleanSubtract(rect(450000,400000,550000,600000))
    with pytest.raises(ValueError,match='outside_Source_envelope'):
        operation._clip_field_face(before,compiled,[[100000,200000,300000,800000],[700000,200000,900000,800000]],time.monotonic()+1.)


def test_different_Source_lands_at_the_same_drill_keep_a_reusable_menu(tmp_path):
    source,args,_=fixture(tmp_path);board=pcb.LoadBoard(str(source))
    next(iter(next(iter(board.Groups())).GetItems())).SetWidth(700000)
    field._save_field_snapshot(board,source)
    proposal=operation.plan(source,**args)
    assert proposal['local_reference_authority']['Source_preferred_geometry_nm']==[700000,300000]
    args['geometry_selection']='board-minimum-land-same-drill'
    minimum=operation.plan(source,**args)
    assert minimum['local_reference_authority']['diameter_nm']==500000
    assert minimum['local_reference_authority']['drill_nm']==300000


@pytest.mark.parametrize('timeout',[0,11,True,float('nan')])
def test_each_native_constituent_stays_bounded(tmp_path,timeout):
    with pytest.raises(ValueError):operation.plan(tmp_path/'missing',board_hint='synthetic',pair_name='CAN',
        signal_via_uuids=['a','b'],positions_nm=[[0,0],[1,1]],timeout_s=timeout)
