"""Layer goals are finite graph obligations, not XY proximity or ampacity."""
import time

import pcbnew
import pytest

import cec_fr as fr
from cec_endpoint_layer_budget import minimum_new_vias
from test_multilayer_route_graph import board_net


def test_zero_count_can_only_reach_actual_goal_faces_without_retained_spans():
    assert minimum_new_vias([0,2,6],[0])=={0:0,2:1,6:1}
    assert minimum_new_vias([0,2,6],[0,6])=={0:0,2:1,6:0}


def test_retained_span_relaxation_is_optimistic_and_never_spends_or_qualifies_a_barrel():
    assert minimum_new_vias([0,2,6,10],[10],retained_spans=[[0,2],[2,6],[6,10]])=={0:0,2:0,6:0,10:0}
    assert minimum_new_vias([0,2,6,10],[10],retained_spans=[[0,2]])=={0:1,2:1,6:1,10:0}
    # A two-barrel face chain can be physically unreachable. Ignoring that
    # distance/guard debt deliberately lowers the bound, not route authority.
    assert minimum_new_vias([6,0,10,2],[10],retained_spans=[[6,2],[2,10]])[6]==0


@pytest.mark.parametrize('layers,goals,spans',[
    (None,[0],[]),([0],None,[]),('02',[0],[]),([],[],[]),([0]*2,[0],[]),
    ([True,2],[2],[]),([[0],2],[2],[]),([0,-1],[0],[]),([0],[2],[]),
    ([0],[0,0],[]),([0,2],[False],[]),([0,2],[0],None),
    ([0,2],[0],[[0]]),([0,2],[0],[[0,6]]),([0,2],[0],[[0,2,2]]),
    ([0,2],[0],[[0,True]]),([0,2],[0],[[0,[2]]]),([0,2],[0],[[0,2]]*257)])
def test_unknown_or_unbounded_goal_access_is_not_search_permission(layers,goals,spans):
    with pytest.raises(ValueError):minimum_new_vias(layers,goals,retained_spans=spans)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('target_back',[False,True])
def test_last_allowed_new_transition_cannot_be_spent_on_wrong_goal_face(monkeypatch,quarter,target_back):
    b,n=board_net();b.SetCopperLayerCount(6)
    first,last=(pcbnew.F_Cu,pcbnew.B_Cu)if target_back else(pcbnew.B_Cu,pcbnew.F_Cu)
    wrong=pcbnew.In2_Cu
    def point(x,y):
        for _ in range(quarter):x,y=-y,x
        return pcbnew.VECTOR2I_MM(20+x,20+y)
    a,z=point(0,0),point(2,0)
    monkeypatch.setattr(fr,'_guarded_power_reservations',lambda:[])
    monkeypatch.setattr(fr,'_via_spot_clear',lambda *args,**kw:True)
    detail={}
    ops=fr._multilayer_maze_lastmile_ops(b,a,z,n.GetNetCode(),(first,wrong,last),200000,
        lambda *args:True,width_for_layer=lambda l:220000,start_layers=(first,),end_layers=(last,),
        max_vias=1,grid_mm=.5,margin_mm=.5,deadline_monotonic=time.monotonic()+2.,diagnostics=detail)
    assert ops and sum(op[0]=='via'for op in ops)==1
    assert all(op[4]!=wrong for op in ops if op[0]=='trk')
    assert detail['endpoint_layer_budget_pruned_states']>0
    assert detail['endpoint_layer_budget_lower_bounds'][wrong]==1
    assert detail['nearest_target_state']['on_target_layer']
    assert detail['nearest_target_state']['minimum_remaining_new_vias']==0
    assert not list(b.GetTracks())and not detail['no_path_proof']


def test_zero_via_wrong_face_is_refused_before_planar_search_without_a_no_path_claim():
    b,n=board_net();d={}
    assert fr._multilayer_maze_lastmile_ops(b,pcbnew.VECTOR2I_MM(0,0),pcbnew.VECTOR2I_MM(1,0),
        n.GetNetCode(),(pcbnew.F_Cu,pcbnew.B_Cu),200000,lambda *args:True,
        width_for_layer=lambda l:220000,start_layers=(pcbnew.F_Cu,),end_layers=(pcbnew.B_Cu,),
        max_vias=0,diagnostics=d) is None
    assert d['stop']=='endpoint_layer_transition_budget_infeasible'and d['expanded_states']==0
    assert not d['no_path_proof']and not d['release_authority']
