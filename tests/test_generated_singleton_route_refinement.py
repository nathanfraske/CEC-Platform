"""One generated route choice is not immutable source or a mandatory column."""
import copy
import math

import pcbnew
import pytest

import cec_cell_escape_replan as escape
import cec_cell_row_rebuild as row
from test_local_supply_native_detours import source


def fixture(monkeypatch,turn,back,kind='local_supply',hard_first=True):
    board,request,obstacle,contract=source(monkeypatch,turn,back)
    board.Remove(obstacle.GetParentFootprint())
    request['kind']=kind
    a,b=request['a']['at_nm'],request['b']['at_nm']
    face=request['a']['layers'][0]
    centre=[(x+y)//2 for x,y in zip(a,b)]
    normal=[(b[1]-a[1])//2,(a[0]-b[0])//2]
    shift=lambda p,n:[p[i]+round(normal[i]*n) for i in range(2)]
    wall=dict(id='wall',cost=0,net='foreign_material',clearance_nm=200000,
        ops=[['trk',shift(centre,-.3),shift(centre,.3),200000,face]])
    straight=dict(id='only_generated_route',cost=2,net=request['net'],clearance_nm=200000,
        ops=[['trk',a,b,250000,face]])
    # Synthetic scheduling policy only, not a forged real Ground-ingress
    # proof or release authority. The real compiler/receiver validates that
    # contract before/after production routing.
    hard_request=dict(kind='ground',net=wall['net'],
        required_projected_ground_entry=dict(synthetic_obstacle_only=True))
    wall_key,route_key=('a_required','z_generated') if hard_first else ('z_required','a_generated')
    domains={wall_key:[wall],route_key:[straight]}
    requests={wall_key:hard_request,route_key:request}
    return board,requests,dict(domains=domains,source_native_binding=row._source_binding(board)),wall_key,route_key


@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('kind',['source_boundary','local_supply'])
@pytest.mark.parametrize('hard_first',[False,True])
def test_generated_singleton_can_be_reproposed_without_removing_required_future_copper(monkeypatch,turn,back,kind,hard_first):
    board,requests,packet,hard,route=fixture(monkeypatch,turn,back,kind,hard_first)
    before=row._source_binding(board);untouched=copy.deepcopy(packet)
    failed=escape.choose(board,packet)
    assert not failed['complete'] and failed['failure_frontier']
    refined=escape.refine_conflict_frontier(board,packet,requests,failed,
        board_path='opaque_fixture',board_hint='opaque_fixture',timeout_s=2.)
    trials=refined['conflict_aware_refinement']['trials']
    assert trials and trials[0]['obligation']==route and trials[0]['added_choices']>0
    selected=escape.choose(board,refined)
    assert selected['complete'] and selected['selected'][hard]==packet['domains'][hard][0]
    assert packet['domains'][route][0] in refined['domains'][route]
    assert all(op[0]=='trk' and op[3]==250000 and op[4]==requests[route]['a']['layers'][0]
        for op in selected['selected'][route]['ops'])
    assert tuple(selected['selected'][route]['ops'][0][1])==tuple(requests[route]['a']['at_nm'])
    assert tuple(selected['selected'][route]['ops'][-1][2])==tuple(requests[route]['b']['at_nm'])
    if kind=='local_supply':
        limit=escape.cell._local_supply_limit_mm(math.dist(requests[route]['a']['at_nm'],requests[route]['b']['at_nm'])/1e6,.25,.2)
        assert sum(math.dist(op[1],op[2]) for op in selected['selected'][route]['ops'])/1e6<=limit
    assert refined['domains'][hard]==packet['domains'][hard]
    assert row._source_binding(board)==before and packet==untouched


@pytest.mark.parametrize('turn',range(4))
def test_two_required_obstacles_are_not_reclassified_as_negotiable_routes(monkeypatch,turn):
    board,requests,packet,hard,route=fixture(monkeypatch,turn,False)
    requests[route]=dict(kind='ground',net=requests[route]['net'],
        required_projected_ground_entry=dict(synthetic_obstacle_only=True))
    before=row._source_binding(board);original=copy.deepcopy(packet)
    failed=escape.choose(board,packet)
    with pytest.raises(ValueError,match='mandatory_singleton_proposals_are_not_compatible'):
        escape.refine_conflict_frontier(board,packet,requests,failed,
            board_path='opaque_fixture',board_hint='opaque_fixture',timeout_s=2.)
    assert row._source_binding(board)==before and packet==original


def test_expired_obstacle_staging_never_starts_an_extra_route_search(monkeypatch):
    board,requests,packet,hard,route=fixture(monkeypatch,0,False)
    failed=escape.choose(board,packet);before=row._source_binding(board)
    original=escape._native_ops;clock={'now':0.};calls=[]
    monkeypatch.setattr(escape.time,'monotonic',lambda:clock['now'])
    def stage(*args,**kwargs):
        result=original(*args,**kwargs);clock['now']=3.;return result
    monkeypatch.setattr(escape,'_native_ops',stage)
    monkeypatch.setattr(escape,'menus',lambda *args,**kwargs:calls.append(kwargs))
    result=escape.refine_conflict_frontier(board,packet,requests,failed,
        board_path='opaque',board_hint='opaque',timeout_s=2.)
    assert calls==[] and row._source_binding(board)==before
    assert result['conflict_aware_refinement']['trials'][0]['deferred_reason']==(
        'refinement_lease_exhausted_after_obstacle_staging')


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_unrelated_conflicting_generated_singleton_does_not_starve_the_failed_domain(monkeypatch,quarter,back):
    from test_joint_route_negotiation import fixture as cluster_fixture
    board,packet,requests,unused=cluster_fixture(monkeypatch,quarter,back)
    # Make the required domain sort first. The real selector then reports
    # the first generated route, while the OTHER generated route still
    # conflicts with the same mandatory copper. Neither may be waived.
    packet['domains']['0_required']=packet['domains'].pop('z_required')
    requests['0_required']=requests.pop('z_required')
    old=copy.deepcopy(packet);binding=row._source_binding(board)
    failed=escape.choose(board,packet)
    assert failed['failure_frontier'][0]['obligation']=='a_generated'
    refined=escape.refine_conflict_frontier(board,packet,requests,failed,
        board_path='opaque',board_hint='opaque',timeout_s=2.)
    trial=refined['conflict_aware_refinement']['trials'][0]
    assert trial['added_choices']>0 and trial['unstaged_conflicting_generated_singletons']==['b_generated']
    assert trial['mandatory_obstacles']==['0_required'] and trial['staged_obligations']==['0_required']
    # The unmodified second obligation still fails. A producer opportunity
    # is NOT mistaken for a complete board or a partial connection waiver.
    second=escape.choose(board,refined)
    assert not second['complete'] and second['failure_frontier'][0]['obligation']=='b_generated'
    final=escape.refine_conflict_frontier(board,refined,requests,second,
        board_path='opaque',board_hint='opaque',timeout_s=2.)
    selected=escape.choose(board,final)
    assert selected['complete'] and set(selected['selected'])==set(requests)
    assert selected['selected']['0_required']==old['domains']['0_required'][0]
    assert all(old['domains'][key][0] in final['domains'][key] for key in requests)
    assert packet==old and row._source_binding(board)==binding


@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_actual_assigned_multichoice_prefix_is_present_during_failed_route_production(monkeypatch,turn,back):
    board,requests,packet,hard,route=fixture(monkeypatch,turn,back,kind='source_boundary')
    wall=copy.deepcopy(packet['domains'][hard][0]);wall['id']='wall'
    second=copy.deepcopy(wall);second['id']='wall_shifted';second['cost']=1
    a,b=requests[route]['a']['at_nm'],requests[route]['b']['at_nm']
    direction=[round((b[i]-a[i])/math.dist(a,b)*125000) for i in range(2)]
    for index in (1,2):second['ops'][0][index]=[second['ops'][0][index][i]+direction[i] for i in range(2)]
    net=pcbnew.NETINFO_ITEM(board,wall['net']);board.Add(net)
    straight=copy.deepcopy(packet['domains'][route][0]);alternate=copy.deepcopy(straight);alternate['id']='second_straight'
    requests={hard:dict(kind='source_boundary',net=wall['net']),route:requests[route]}
    packet=dict(domains={hard:[wall,second],route:[straight,alternate]},source_native_binding=row._source_binding(board))
    original=copy.deepcopy(packet);binding=row._source_binding(board)
    failed=escape.choose(board,packet)
    assert not failed['complete'] and failed['failure_frontier'][0]['obligation']==route
    refined=escape.refine_conflict_frontier(board,packet,requests,failed,
        board_path='opaque',board_hint='opaque',timeout_s=2.)
    trial=refined['conflict_aware_refinement']['trials'][0]
    assert trial['added_choices']>0 and trial['staged_assignment_choices']=={hard:'wall'}
    assert trial['mandatory_obstacles']==[] and trial['staged_obligations']==[hard]
    chosen=escape.choose(board,refined)
    assert chosen['complete'] and set(chosen['selected'])==set(requests)
    assert all(choice in refined['domains'][key] for key in packet['domains'] for choice in packet['domains'][key])
    assert row._source_binding(board)==binding and packet==original
