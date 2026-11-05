"""Exact endpoint rejection is not a global no-path or width exception."""
import time
from unittest import mock

import pcbnew
import pytest
import cec_fr as fr


def fixture(turn=0, mirror=False, back=False, narrow=False):
    board=pcbnew.CreateEmptyBoard();board.SetCopperLayerCount(6)
    def point(x,y):
        if mirror:x=-x
        for _ in range(turn):x,y=-y,x
        return pcbnew.VECTOR2I(round((x+17)*1e6),round((y+23)*1e6))
    own=pcbnew.NETINFO_ITEM(board,'arbitrary-load');board.Add(own)
    foreign=pcbnew.NETINFO_ITEM(board,'unrelated-copper');board.Add(foreign)
    layer=pcbnew.B_Cu if back else pcbnew.F_Cu
    trace=pcbnew.PCB_TRACK(board);trace.SetStart(point(8,9));trace.SetEnd(point(8,11))
    trace.SetNet(foreign);trace.SetWidth(200000);trace.SetLayer(layer);board.Add(trace)
    return board,point,own,layer,trace


@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('mirror,back',[(False,False),(True,False),(False,True),(True,True)])
@pytest.mark.parametrize('terminal',['start','end'])
def test_actual_foreign_endpoint_refuses_before_lattice(turn,mirror,back,terminal):
    board,point,own,layer,trace=fixture(turn,mirror,back)
    start,end=(point(8,10),point(13,10)) if terminal=='start' else (point(3,10),point(8,10))
    before=(tuple(trace.GetStart()),tuple(trace.GetEnd()),trace.GetNetCode(),trace.GetWidth())
    report={};leg=mock.Mock(return_value=True);run=mock.Mock(return_value=True)
    with mock.patch('cec_maze_channels.native_obstacle_boxes',side_effect=AssertionError('no lattice')):
        result=fr._maze_lastmile_legs(board,start,end,200000,layer,200000,own.GetNetCode(),leg,
            run_guard=run,deadline_monotonic=time.monotonic()+1,diagnostics=report)
    assert result is None and not leg.called and not run.called
    assert report['stop']=='native_endpoint_cap_blocked_before_lattice'
    assert report['native_endpoint_caps'][-1]['endpoint']==terminal
    assert report['lattice_constructed'] is False and report['no_path_proof'] is False
    assert before==(tuple(trace.GetStart()),tuple(trace.GetEnd()),trace.GetNetCode(),trace.GetWidth())


@pytest.mark.parametrize('escape,blocked',[(None,True),((200000,0),True),
    ((200000,-1),True),((200000,1000000),False)])
def test_positive_local_neckdown_budget_is_preserved(escape,blocked):
    board,point,own,layer,_trace=fixture()
    report={}
    # Wide cap overlaps the foreign trace; the declared narrow cap clears it.
    with mock.patch('cec_maze_channels.native_obstacle_boxes',return_value=[]):
        result=fr._maze_lastmile_legs(board,point(8.6,10),point(12,10),1000000,layer,
            200000,own.GetNetCode(),lambda *_:True,start_escape=escape,
            deadline_monotonic=time.monotonic()+1,diagnostics=report)
    assert report['native_endpoint_caps'][0]['native_foreign_cap_clear'] is not blocked
    if blocked:assert result is None and report['lattice_constructed'] is False
    else:assert result and report['lattice_constructed'] is True


def test_other_layer_and_own_net_never_become_false_native_obstacles():
    for other_layer in (False,True):
        board,point,own,layer,trace=fixture()
        if other_layer:trace.SetLayer(pcbnew.B_Cu)
        else:trace.SetNet(own)
        report={}
        result=fr._maze_lastmile_legs(board,point(8,10),point(12,10),200000,layer,
            200000,own.GetNetCode(),lambda *_:True,
            deadline_monotonic=time.monotonic()+1,diagnostics=report)
        assert result and all(q['native_foreign_cap_clear'] for q in report['native_endpoint_caps'])


def test_point_checks_do_not_fake_calls_to_length_sensitive_guards():
    board,point,own,layer,_trace=fixture()
    def run(a,b,width):
        assert tuple(a)!=tuple(b)
        return True
    assert fr._maze_lastmile_legs(board,point(9,10),point(12,10),200000,layer,
        200000,own.GetNetCode(),lambda a,b,_half:tuple(a)!=tuple(b),run_guard=run,
        deadline_monotonic=time.monotonic()+1)
