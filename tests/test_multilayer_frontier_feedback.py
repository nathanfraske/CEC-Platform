"""Bounded predecessor feedback is never partial-route admission."""
import math
import time
import pcbnew
import pytest
import cec_fr as fr


@pytest.mark.parametrize('turn',[0,1,2,3])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('back',[False,True])
def test_budgeted_frontier_preserves_checked_native_path_without_admission(turn,mirror,back):
    board=pcbnew.CreateEmptyBoard();net=pcbnew.NETINFO_ITEM(board,'/different/control');board.Add(net)
    def point(x,y):
        if mirror:x=-x
        for _ in range(turn):x,y=-y,x
        return pcbnew.VECTOR2I(fr._nm(20+x),fr._nm(20+y))
    start,target=point(0,0),point(8,4)
    layers=(pcbnew.F_Cu,pcbnew.B_Cu);face=pcbnew.B_Cu if back else pcbnew.F_Cu
    report={};checked=[]
    def edge(a,b,half):
        checked.append((tuple(a),tuple(b),half));return True
    result=fr._multilayer_maze_lastmile_ops(board,start,target,net.GetNetCode(),layers,200000,edge,
        width_for_layer=lambda _layer:200000,start_layers=(face,),end_layers=(face,),
        grid_mm=.5,margin_mm=2,max_vias=0,deadline_monotonic=time.monotonic()+2,
        canonical_turns_only=True,heuristic_weight=3,max_expanded_states=4,diagnostics=report)
    assert result is None and report['stop']=='explicit_state_budget_exhausted'
    prefix=report['best_reached_prefix']
    assert prefix['complete'] and not prefix['complete_route'] and not prefix['target_reached']
    assert prefix['source_checked_search_only'] and prefix['whole_original_parent_receiving_still_required']
    assert not prefix['routing_admitted'] and not prefix['release_authority'] and not report['no_path_proof']
    assert 1<=len(prefix['ops'])<=256 and prefix['ops'][0]['start_nm']==list(start)
    endpoint=start;length=0
    for op in prefix['ops']:
        assert op['kind']=='trk' and op['width_nm']==200000 and op['layer']==face
        assert op['start_nm']==list(endpoint)
        a,b=op['start_nm'],op['end_nm'];dx,dy=b[0]-a[0],b[1]-a[1]
        assert dx==0 or dy==0 or abs(dx)==abs(dy)
        assert dx or dy
        length+=math.dist(a,b)/1e6;endpoint=pcbnew.VECTOR2I(*b)
    assert length==pytest.approx(prefix['length_mm'])
    assert [v/1e6 for v in endpoint]==report['nearest_target_state']['at_mm']
    assert math.dist(tuple(endpoint),tuple(target))<math.dist(tuple(start),tuple(target))
    assert len(list(board.GetTracks()))==0


def test_no_frontier_material_when_only_the_source_was_popped():
    board=pcbnew.CreateEmptyBoard();net=pcbnew.NETINFO_ITEM(board,'control');board.Add(net)
    report={}
    assert fr._multilayer_maze_lastmile_ops(board,pcbnew.VECTOR2I_MM(0,0),pcbnew.VECTOR2I_MM(8,4),
        net.GetNetCode(),(pcbnew.F_Cu,pcbnew.B_Cu),200000,lambda *_:True,
        width_for_layer=lambda _layer:200000,max_vias=0,max_expanded_states=1,
        deadline_monotonic=time.monotonic()+2,diagnostics=report) is None
    assert report['stop']=='explicit_state_budget_exhausted' and 'best_reached_prefix' not in report
    assert not report['no_path_proof']


def test_completed_route_does_not_emit_unadmitted_prefix_feedback():
    board=pcbnew.CreateEmptyBoard();net=pcbnew.NETINFO_ITEM(board,'control');board.Add(net)
    report={}
    assert fr._multilayer_maze_lastmile_ops(board,pcbnew.VECTOR2I_MM(0,0),pcbnew.VECTOR2I_MM(1,0),
        net.GetNetCode(),(pcbnew.F_Cu,pcbnew.B_Cu),200000,lambda *_:True,
        width_for_layer=lambda _layer:200000,max_vias=0,max_expanded_states=100,
        deadline_monotonic=time.monotonic()+2,diagnostics=report)
    assert report['stop']=='found' and 'best_reached_prefix' not in report
    assert not report['release_authority'] and not report['no_path_proof']
