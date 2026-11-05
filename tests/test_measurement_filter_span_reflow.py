"""Real Source RC node, fixed ports and independently saved reconstruction."""
import copy
from pathlib import Path
import pcbnew
import pytest
import cec_field_coupling as field
import cec_force_current as force
import cec_measurement_filter_span_reflow as operation
from test_measurement_filter_span import fixture as observer_fixture
from test_field_proposals import track


def fixture(tmp_path,monkeypatch,*,quarter=0,mirror=False):
    f=observer_fixture(tmp_path,monkeypatch,quarter=quarter,mirror=mirror)
    board=f['board'];corners=[(-5,-5),(50,-5),(50,50),(-5,50),(-5,-5)]
    for a,z in zip(corners,corners[1:]):
        edge=pcbnew.PCB_SHAPE(board);edge.SetShape(pcbnew.SHAPE_T_SEGMENT);edge.SetLayer(pcbnew.Edge_Cuts)
        edge.SetWidth(50000);edge.SetStart(pcbnew.VECTOR2I_MM(*a));edge.SetEnd(pcbnew.VECTOR2I_MM(*z));board.Add(edge)
    field._save_field_snapshot(board,f['source'])
    def transform(point):
        x,y=point
        if mirror:x=40000000-x
        # KiCad's positive angle uses the PCB's downward-positive Y axis.
        # Match the actual native source rotation, not Cartesian screen math.
        for _ in range(quarter):x,y=y,40000000-x
        return [x,y]
    points=[transform(p)for p in((12000000,10000000),(12000000,10500000),(12500000,11000000),
        (12500000,13000000),(12000000,13500000),(12000000,14000000))]
    args=dict(board_hint=f['hint'],pad_uuid=force._uid(f['root']),span_uuid=force._uid(f['span']))
    return f,args,points


def saved(tmp_path,monkeypatch,**options):
    f,args,points=fixture(tmp_path,monkeypatch,**options)
    proposal=operation.plan(f['source'],**args)
    result=operation.write_private(proposal,tmp_path/'child',points)
    return f,args,points,proposal,Path(result['candidate'])


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',(False,True))
def test_native_canonical_RC_span_fixed_contact_replay_in_every_frame(tmp_path,monkeypatch,quarter,mirror):
    f,args,points,proposal,child=saved(tmp_path,monkeypatch,quarter=quarter,mirror=mirror)
    before=f['source'].read_bytes();proof=operation.receive(f['source'],child,**args)
    assert proof['complete'] and proof['ok'],proof
    assert proposal['exact_source_retirement']==[args['span_uuid']]
    assert len(proposal['terminal_bearing_cut_parts'])==2
    assert proof['geometry']['native_lower_and_upper_contacts_identical']
    assert proof['geometry']['no_new_same_net_pickup']
    assert proof['original_native_partitions']['preserved']
    assert proof['exact_saved_subtract_add_refill']['ok']
    assert not any(proof[k]for k in('current_authority','Kelvin_qualified','routing_admitted','release_authority'))
    assert f['source'].read_bytes()==before


@pytest.mark.parametrize('fault',('endpoint','non45','too_long','new_pickup','foreign_track','input_terminal'))
def test_unowned_route_contacts_or_scope_cannot_be_added(tmp_path,monkeypatch,fault):
    f,args,points=fixture(tmp_path,monkeypatch)
    if fault=='endpoint':points[0][0]+=1
    elif fault=='non45':points[2][0]+=1
    elif fault=='too_long':points[2]=[22000000,11000000];points[3]=[22000000,13000000]
    elif fault=='new_pickup':
        track(f['board'],'positive_input',(12.5,12),(15,12),width=.25)
        field._save_field_snapshot(f['board'],f['source'])
    elif fault=='foreign_track':
        track(f['board'],'negative_input',(12.5,11),(12.5,13),width=.25)
        field._save_field_snapshot(f['board'],f['source'])
    else:args['span_uuid']=force._uid(f['tracks'][0])
    with pytest.raises(ValueError):
        q=operation.plan(f['source'],**args);operation.write_private(q,tmp_path/'bad',points)


@pytest.mark.parametrize('fault',('width','back','axis','part','cap_value','extra_track','old_track','project'))
def test_saved_foreign_deltas_and_process_changes_are_refused(tmp_path,monkeypatch,fault):
    f,args,points,proposal,child=saved(tmp_path,monkeypatch)
    board=pcbnew.LoadBoard(str(child));old={force._uid(t)for t in pcbnew.LoadBoard(str(f['source'])).GetTracks()}
    incoming=[t for t in board.GetTracks()if force._uid(t)not in old]
    if fault=='width':incoming[0].SetWidth(249999)
    elif fault=='back':incoming[0].SetLayer(pcbnew.B_Cu)
    elif fault=='axis':incoming[0].SetStart(incoming[0].GetStart()+pcbnew.VECTOR2I(1,0))
    elif fault=='part':board.FindFootprintByReference('arbitrary_input').SetValue('not Source')
    elif fault=='cap_value':board.FindFootprintByReference('K7').SetValue('1nF')
    elif fault=='extra_track':track(board,'positive_input',(30,30),(31,30),width=.25)
    elif fault=='old_track':next(t for t in board.GetTracks()if force._uid(t)in old).SetWidth(249999)
    else:child.with_suffix('.kicad_pro').write_text('{}')
    if fault!='project':pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(child),board)
    proof=operation.receive(f['source'],child,**args)
    assert not proof['ok'] and not proof['complete'] and proof['errors']


@pytest.mark.parametrize('key,value',(('span_uuid','not Source'),('source_observation',{}),('exact_source_retirement',[])))
def test_plan_is_a_recompiled_Source_request_not_a_caller_permission(tmp_path,monkeypatch,key,value):
    f,args,points=fixture(tmp_path,monkeypatch);q=operation.plan(f['source'],**args)
    forged=copy.deepcopy(q);forged[key]=value
    with pytest.raises(ValueError):operation.write_private(forged,tmp_path/'bad',points)


@pytest.mark.parametrize('bad',(True,0,-1,11,float('nan')))
def test_each_native_constituent_has_a_hard_ten_second_lease(tmp_path,bad):
    with pytest.raises(ValueError):operation.plan(tmp_path/'missing',board_hint='x',pad_uuid='x',span_uuid='x',timeout_s=bad)
