"""Bounded, opt-in mesh fallback; never a clearance/current exception."""
import time
from unittest import mock

import pcbnew
import pytest

import cec_fr as fr
import cec_search_budget as budget


def invoke(*, refine=True, span=2., deadline=None, validator=None, diagnostics=None,
           maze=None, allow=True,grids=()):
    board=pcbnew.BOARD()
    net=pcbnew.NETINFO_ITEM(board,'renamed-load');board.Add(net)
    a,b=pcbnew.VECTOR2I_MM(4.,5.),pcbnew.VECTOR2I_MM(4.+span,5.)
    end=time.monotonic()+1 if deadline is None else deadline
    with mock.patch.object(fr,'_canonical_45_xy_paths',return_value=[]), \
         mock.patch.object(fr,'_offset_manhattan_xy_paths',return_value=[]), \
         mock.patch('cec_maze_channels.orthogonal_channel_paths',return_value=[]), \
         mock.patch.object(fr,'_maze_lastmile_legs',side_effect=maze,return_value=None) as tiers:
        result=fr._guarded_profiled_lastmile_legs(board,a,b,477370,pcbnew.F_Cu,
            200000,net.GetNetCode(),lambda *_:True,allow_maze=allow,
            deadline_monotonic=end,path_validator=validator,
            refine_maze=refine,search_diagnostics=diagnostics,refinement_grids_mm=grids)
    return result,tiers,a,b,end


def test_coarse_failure_enters_finer_tiers_with_same_contract_and_outer_deadline():
    report={}
    def maze(_board,a,b,width,*_args,grid_mm,**_kwargs):
        return [(a,b,width)] if grid_mm==.1 else None
    result,tiers,a,b,end=invoke(maze=maze,diagnostics=report)
    assert result==[(a,b,477370)]
    assert [call.kwargs['grid_mm'] for call in tiers.call_args_list]==[.5,.2,.1]
    assert all(call.args[3]==477370 and call.args[5]==200000
        and call.kwargs['deadline_monotonic']<=end and call.kwargs['start_escape'] is None
        and call.kwargs['end_escape'] is None for call in tiers.call_args_list)
    assert [row['path_accepted'] for row in report['maze_tiers']]==[False,False,True]
    assert [row['same_deadline']for row in report['maze_tiers']]==[False,False,True]
    assert all(row['same_outer_deadline']and not row['no_path_proof']
        and row['outer_deadline_monotonic']==end for row in report['maze_tiers'])


def test_a_slow_coarse_grid_cannot_starve_requested_fine_contact_domains():
    class Clock:
        now=100.
        def monotonic(self):return self.now
    clock=Clock();report={}
    def maze(_board,a,b,width,*_args,grid_mm,deadline_monotonic,**_kwargs):
        assert clock.now<deadline_monotonic<=101.
        if grid_mm!=.1:
            # Model a legitimate unsuccessful search that uses its ENTIRE
            # own lease. No sleep, physical-rule mock or larger outer lease.
            clock.now=deadline_monotonic+.00001
            return None
        clock.now=(clock.now+deadline_monotonic)/2
        return [(a,b,width)]
    with mock.patch.object(time,'monotonic',clock.monotonic):
        result,tiers,a,b,end=invoke(maze=maze,deadline=101.,diagnostics=report)
    assert result==[(a,b,477370)]and tiers.call_count==3
    assert clock.now<end==101.
    assert [row['remaining_tiers']for row in report['maze_tiers']]==[3,2,1]
    assert all(row['tier_lease_s']>0 for row in report['maze_tiers'])
    assert all(call.args[3]==477370 and call.args[5]==200000
        for call in tiers.call_args_list)


def test_single_tier_keeps_the_identical_original_deadline():
    _,tiers,_,_,end=invoke(refine=False)
    assert tiers.call_count==1
    assert tiers.call_args.kwargs['deadline_monotonic']==end


def test_explicit_middle_grids_never_coarsen_after_automatic_local_refinement():
    _,tiers,_,_,end=invoke(grids=(.25,.125))
    assert [call.kwargs['grid_mm']for call in tiers.call_args_list]==[.5,.25,.2,.125,.1]
    assert all(call.kwargs['deadline_monotonic']<=end for call in tiers.call_args_list)
    assert tiers.call_args_list[-1].kwargs['deadline_monotonic']==end


def test_solved_coarse_route_never_changes_or_enters_more_expensive_tiers():
    def maze(_board,a,b,width,*_args,**_kwargs):return [(a,b,width)]
    result,tiers,a,b,_=invoke(maze=maze)
    assert result==[(a,b,477370)] and tiers.call_count==1


@pytest.mark.parametrize('refine,span,allow',[(False,2.,True),(True,20.,True),(True,2.,False)])
def test_refinement_is_local_explicit_and_respects_maze_permission(refine,span,allow):
    result,tiers,*_=invoke(refine=refine,span=span,allow=allow)
    assert result is None and tiers.call_count==(1 if allow else 0)


def test_refined_paths_still_need_the_complete_field_or_other_path_validator():
    validator=mock.Mock(return_value=False)
    def maze(_board,a,b,width,*_args,**_kwargs):return [(a,b,width)]
    result,tiers,*_=invoke(maze=maze,validator=validator)
    assert result is None and tiers.call_count==validator.call_count==3


def test_expired_work_and_exhausted_operation_budget_never_start_more_search():
    result,tiers,*_=invoke(deadline=time.monotonic()-1)
    assert result is None and tiers.call_count==0
    with budget.scoped(1) as work:
        work.used=1
        result,tiers,*_=invoke()
    assert result is None and tiers.call_count==0


@pytest.mark.parametrize('bad',[True,None,float('inf'),float('nan')])
def test_refinement_cannot_acquire_an_unbounded_work_lease(bad):
    board=pcbnew.BOARD()
    with pytest.raises(ValueError,match='finite_local_maze_refinement_deadline_required'):
        fr._guarded_profiled_lastmile_legs(board,pcbnew.VECTOR2I(0,0),pcbnew.VECTOR2I(1,1),
            200000,pcbnew.F_Cu,200000,1,lambda *_:True,refine_maze=True,deadline_monotonic=bad)


@pytest.mark.parametrize('bad',[1,None,'yes'])
def test_refinement_requires_literal_boolean_mode(bad):
    with pytest.raises(ValueError,match='explicit_bounded_maze_refinement_mode_required'):
        invoke(refine=bad)
