"""Actual-face consumer repair is opt-in and preserves every old strict gate."""
import copy,json,math,os,runpy,sys
from pathlib import Path
import pcbnew
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'ops'))
import cec_planar_consumer_reconstruction as planar
import cec_consumer_group_reconstruction as outer
import cec_field_coupling as field
import cec_force_current as force
from test_pass_through_supply_branch import fixture
from test_consumer_corner_miter_tool import run_tool as run_outer,BUILD
import cec_native_drc_runner as native
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax

TOOL=Path(__file__).resolve().parents[1]/'ops/cec_consumer_corner_miter.py'


def case(tmp_path,monkeypatch,quarter=0,mirror=False,fault=None):
    board,root,anchor,owner,cap,tracks,trunk,group,row,domain,downstream=fixture(monkeypatch,tmp_path)
    # Explicit fictional low-current fixture, NOT a hardware budget change.
    # The 3 A outer-face fixture needs >5 mm on its thin inner copper and
    # therefore must not be treated as a sub-1-mm inner-face test case.
    row['amps']=.3004;downstream['amps']=.3
    source=Path(board.GetFileName());old=tracks[0];scope=outer.plan(board,source,board_hint='synthetic',retired_track_uuids=[force._uid(old)])
    start,end=tuple(old.GetStart()),tuple(old.GetEnd());outer.subtract(board,scope)
    for point in (start,end):
        via=pcbnew.PCB_VIA(board);via.SetNet(root.GetNet());via.SetPosition(pcbnew.VECTOR2I(*point));via.SetWidth(800000)
        via.SetDrill(300000);via.SetViaType(pcbnew.VIATYPE_THROUGH);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(via)
    budget=planar.consumer.contract(board,force._uid(root),board_hint='synthetic')
    width=math.ceil(budget['required_by_layer_mm']['In2.Cu']*1e6)
    points=[start,(start[0],start[1]+2000000),(end[0],end[1]+2000000),end];new=[]
    for a,z in zip(points,points[1:]):
        t=pcbnew.PCB_TRACK(board);t.SetNet(root.GetNet());t.SetLayer(pcbnew.In2_Cu);t.SetWidth(width);t.SetLocked(True)
        t.SetStart(pcbnew.VECTOR2I(*a));t.SetEnd(pcbnew.VECTOR2I(*z));board.Add(t);new.append(t)
    outer.assign(board,scope,[force._uid(t) for t in new],[])
    output=pcbnew.PCB_TRACK(board);output.SetNet(owner.FindPadByNumber('1').GetNet());output.SetLayer(pcbnew.F_Cu)
    output.SetWidth(200000);output.SetStart(owner.FindPadByNumber('1').GetPosition());output.SetEnd(owner.FindPadByNumber('8').GetPosition());board.Add(output)
    for a,z in [((-50,-50),(50,-50)),((50,-50),(50,50)),((50,50),(-50,50)),((-50,50),(-50,-50))]:
        edge=pcbnew.PCB_SHAPE(board);edge.SetLayer(pcbnew.Edge_Cuts);edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a));edge.SetEnd(pcbnew.VECTOR2I_MM(*z));board.Add(edge)
    for item in [*board.GetFootprints(),*board.GetTracks()]:
        if quarter:item.Rotate(pcbnew.VECTOR2I(0,0),pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T))
        if mirror:item.Flip(pcbnew.VECTOR2I(0,0),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    if fault=='plane':
        for t in new:t.SetLayer(pcbnew.In1_Cu)
    elif fault=='underwidth':
        for t in new:t.SetWidth(100000)
    elif fault=='mixed_width':new[0].SetWidth(width+1000)
    elif fault=='masked':
        for t in new:t.SetHasSolderMask(True)
    elif fault=='unknown_group':group.SetName('untyped owner')
    elif fault=='wrong_package':owner.SetField('MPN','UNKNOWN')
    elif fault=='lowered_allocation':row['amps']=.3
    field._save_field_snapshot(board,source)
    return source,board,[force._uid(t) for t in new],row,domain,downstream


def run_case(tmp_path,source):
    shadow=force._copy_family(source,tmp_path/'native-source');path=tmp_path/'native-source.json'
    producer=native.run(shadow,path,reporting_build=BUILD,timeout_s=10.)
    assert producer['ok'] and producer['complete'] and not producer['native_inventory']['potentially_truncated']
    assert not json.loads(path.read_text())['unconnected_items']
    grade=tmp_path/'grade.json';force._write(grade,dict(code_identity=force._code_identity(),
        boards=dict(candidate=dict(sha256=force._hash(source),native_producer=producer))))
    return runpy.run_path(str(TOOL))['run'](source,tmp_path/'work',board_hint='synthetic',expected_source_sha256=force._hash(source),
        grade=grade,reporting_build=BUILD,allow_locked_source=True,source_ownership='planar_nonplane')


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
def test_opt_in_actual_inner_face_keeps_same_budget_native_contacts_and_saved_process(tmp_path,monkeypatch,quarter,mirror):
    source,board,ids,row,domain,downstream=case(tmp_path,monkeypatch,quarter,mirror);before=source.read_bytes()
    budget=copy.deepcopy((row,domain,downstream));functions=runpy.run_path(str(TOOL))
    strict=functions['inventory'](board,source,board_hint='synthetic',allow_locked_source=True)
    assert not strict['batches']
    with pytest.raises(ValueError):outer.plan(board,source,board_hint='synthetic',retired_track_uuids=ids[:2])
    result=run_case(tmp_path,source)
    assert result['ok'] and result['complete'] and result['changed'],result
    owned=result['independent_source_consumer_receiving'];assert owned['ok'] and owned['complete'] and not owned['errors']
    assert owned['actual_face_current_floor_rederived'] and owned['all_original_surviving_partitions_preserved']
    assert owned['exact_native_ground_refill_replayed'] and not owned['incoming_via_uuids']
    scope=owned['source_scope'];assert scope['source_width_nm']>=scope['actual_face_floor_nm']
    assert scope['source_budget']['current_authority']['amps']==.3004
    assert scope['source_budget']['aggregate_current_authority']['amps']==20.
    assert not owned['source_current_reduced'] and not owned['branch_sharing_assumed'] and not owned['release_authority']
    assert result['attempts'][-1]['opens']==0 and not result['attempts'][-1]['new_native_faults']
    assert result['source_family_and_code_unchanged'] and source.read_bytes()==before and budget==(row,domain,downstream)


@pytest.mark.parametrize('fault',['plane','underwidth','mixed_width','masked','unknown_group','wrong_package','lowered_allocation'])
def test_inner_face_is_not_a_plane_current_or_process_waiver(tmp_path,monkeypatch,fault):
    source,board,ids,*_=case(tmp_path,monkeypatch,fault=fault);before=source.read_bytes()
    with pytest.raises(ValueError):planar.plan(board,source,board_hint='synthetic',retired_track_uuids=ids[:2])
    assert source.read_bytes()==before


def test_inner_owner_still_cannot_retire_the_complete_group(tmp_path,monkeypatch):
    source,board,*_=case(tmp_path,monkeypatch);group=next(g for g in board.Groups() if g.GetName().startswith(planar.consumer.PREFIX))
    with pytest.raises(ValueError,match='partial'):
        planar.plan(board,source,board_hint='synthetic',retired_track_uuids=[force._uid(t) for t in group.GetItems()])


@pytest.mark.parametrize('fault',['face','width','lock','mask','foreign_item','pose'])
def test_saved_planar_delta_cannot_change_actual_face_process_or_unowned_material(tmp_path,monkeypatch,fault):
    source,board,*_=case(tmp_path,monkeypatch);result=run_case(tmp_path,source);assert result['changed']
    candidate=Path(result['candidate']);child=pcbnew.LoadBoard(str(candidate))
    before_root,_=additive._nodes(candidate)
    incoming=result['independent_source_consumer_receiving']['incoming_track_uuids']
    track=next(t for t in child.GetTracks() if force._uid(t)==incoming[0])
    if fault=='face':track.SetLayer(pcbnew.F_Cu)
    elif fault=='width':track.SetWidth(track.GetWidth()+1)
    elif fault=='lock':track.SetLocked(not track.IsLocked())
    elif fault=='mask':track.SetHasSolderMask(True)
    elif fault=='pose':next(iter(child.GetFootprints())).Move(pcbnew.VECTOR2I(1000,0))
    else:
        extra=pcbnew.PCB_TRACK(child);extra.SetNet(child.FindNet('OTHER'));extra.SetLayer(pcbnew.F_Cu)
        extra.SetWidth(200000);extra.SetStart(pcbnew.VECTOR2I_MM(20,20));extra.SetEnd(pcbnew.VECTOR2I_MM(21,20));child.Add(extra)
    field._save_field_snapshot(child,candidate)
    received=planar.receive(source,candidate,board_hint='synthetic',retired_track_uuids=result['records'][0]['plan']['retired_track_uuids'])
    if fault=='mask':
        # KiCad does not serialize an outer-mask option on an inner track.
        # Prove that this was NO saved mutation, not a tolerated mutation.
        after_root,_=additive._nodes(candidate)
        assert syntax._freeze(before_root)==syntax._freeze(after_root)
        assert received['ok'] and received['complete']
    else:assert not received['ok'] and received['errors']


@pytest.mark.parametrize('choice',['ordinary',True,None,'unknown'])
def test_arbitrary_ownership_strategy_is_not_executable(choice):
    with pytest.raises(ValueError):runpy.run_path(str(TOOL))['owner_for'](choice)
