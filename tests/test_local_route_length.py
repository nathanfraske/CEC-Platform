"""Caller locality limits constrain search, not just its first returned path."""
import math
from unittest.mock import patch

import pytest
import cec_swig_guard
cec_swig_guard.pin()
import pcbnew
import cec_fr as router
import cec_search_budget
from test_lastmile import _board


@pytest.mark.parametrize('rotation,offset', [(0,(0,0)),(90,(13,0)),(180,(15,15))])
def test_overlong_first_clear_path_does_not_hide_shorter_legal_candidate(rotation,offset):
    def xy(x,y):
        if rotation==90:x,y=-y,x
        if rotation==180:x,y=-x,-y
        return x+offset[0],y+offset[1]
    start,end=xy(2,2),xy(6,2)
    board=_board([(*start,'RAIL'),(*end,'RAIL')],edge=(0,0,20,20))
    s,t=pcbnew.VECTOR2I_MM(*start),pcbnew.VECTOR2I_MM(*end)
    long=[xy(2,2),xy(2,5),xy(6,5),xy(6,2)]
    paths=[[(round(x*1e6),round(y*1e6)) for x,y in long],[(s.x,s.y),(t.x,t.y)]]
    net=board.GetNetcodeFromNetname('RAIL')
    def run(limit):
        return router._guarded_profiled_lastmile_legs(board,s,t,250000,pcbnew.F_Cu,
            200000,net,lambda a,b,r:router._edge_leg_clear(board,a,b,r),
            allow_maze=False,max_length_nm=limit)
    with patch.object(router,'_canonical_45_xy_paths',return_value=paths), \
            patch.object(router,'_offset_manhattan_xy_paths',return_value=[]):
        old,new=run(None),run(4.05e6)
    def length(legs):
        return sum(math.hypot(b.x-a.x,b.y-a.y) for a,b,_ in legs)/1e6
    assert length(old)==pytest.approx(10)
    assert length(new)==pytest.approx(4)
    assert not list(board.GetTracks())


def test_maze_admissible_lower_bound_avoids_unusable_detours_without_waiving_guards():
    board=_board([(2,2,'TARGET'),(6,2,'TARGET'),(4,2,'FOREIGN')],edge=(0,0,12,8))
    args=(board,pcbnew.VECTOR2I_MM(2,2),pcbnew.VECTOR2I_MM(6,2),250000,
          pcbnew.F_Cu,200000,board.GetNetcodeFromNetname('TARGET'),
          lambda a,b,r:router._edge_leg_clear(board,a,b,r))
    with cec_search_budget.scoped(20000) as old_work:
        unbounded=router._maze_lastmile_legs(*args,grid_mm=.5)
    with cec_search_budget.scoped(20000) as new_work:
        bounded=router._maze_lastmile_legs(*args,grid_mm=.5,max_length_nm=4.01e6)
    assert unbounded and bounded is None
    assert new_work.report()['work_used'] < old_work.report()['work_used']
    admitted=router._maze_lastmile_legs(*args,grid_mm=.5,max_length_nm=6e6)
    assert admitted
    assert sum(math.hypot(b.x-a.x,b.y-a.y) for a,b,_ in admitted) <= 6e6
    assert not list(board.GetTracks())


@pytest.mark.parametrize('bad', [-1,float('inf'),float('nan'),True,False])
def test_invalid_length_budget_is_not_a_silent_unbounded_fallback(bad):
    with pytest.raises(ValueError):
        router._checked_route_length_nm(bad)


def test_endpoint_stub_lengths_are_reserved_but_via_penalty_is_not_copper_length():
    a,b,c=pcbnew.VECTOR2I_MM(0,0),pcbnew.VECTOR2I_MM(3,4),pcbnew.VECTOR2I_MM(3,6)
    assert router._planar_ops_length_nm([
        ('trk',a,b,250000,pcbnew.F_Cu),('via',b,.2,.3),
        ('trk',b,c,250000,pcbnew.B_Cu)])==pytest.approx(7e6)


def test_impossible_direct_lower_bound_stops_before_native_obstacle_setup():
    board=_board([(2,2,'R'),(6,2,'R')])
    with patch.object(router,'_foreign_shape_indexes',side_effect=AssertionError('unneeded guard setup')):
        result=router._guarded_profiled_lastmile_legs(board,pcbnew.VECTOR2I_MM(2,2),
            pcbnew.VECTOR2I_MM(6,2),250000,pcbnew.F_Cu,200000,
            board.GetNetcodeFromNetname('R'),lambda *_:True,max_length_nm=3e6)
    assert result is None
