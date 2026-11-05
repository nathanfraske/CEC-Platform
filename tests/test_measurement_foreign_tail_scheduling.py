"""Never spend a finite surface-search seat on an already blocked fixed tail.

The search stub records scheduling only. Actual native pad geometry, foreign
copper and board-edge predicates remain real; no successful route is inferred.
"""
import math
import time

import pcbnew
import pytest

import cec_force_current as force
import cec_field_coupling as field
import cec_measurement_terminal_route as route
from test_measurement_terminal_access import get
from test_measurement_terminal_route import fixture


def _example(quarter,back,*,blocked_all=False,edge=False):
    board,_,root,target=fixture()
    peer=next(p for p in target.GetParentFootprint().Pads() if p.GetNumber()!=target.GetNumber())
    reach=math.hypot(*tuple(target.GetSize()))/2e6
    x,y,ux,uy=route.fr._inner_edge_pt(target,peer.GetPosition(),inset_mm=min(.12,reach*.25))
    # A long preferred tail crosses a real foreign strip. Short tails
    # terminate on its near side and remain legal at these SAME pickup ports.
    offset=.45 if blocked_all else .8
    barrier=pcbnew.PCB_SHAPE(board) if edge else pcbnew.PCB_TRACK(board)
    if edge:
        barrier.SetShape(pcbnew.SHAPE_T_SEGMENT);barrier.SetLayer(pcbnew.Edge_Cuts)
        barrier.SetWidth(50000)
    else:
        foreign=pcbnew.NETINFO_ITEM(board,'unrelated_retained_signal');board.Add(foreign)
        barrier.SetNet(foreign);barrier.SetLayer(pcbnew.F_Cu);barrier.SetWidth(200000)
    barrier.SetStart(pcbnew.VECTOR2I_MM(x+ux*offset,y-1))
    barrier.SetEnd(pcbnew.VECTOR2I_MM(x+ux*offset,y+1));board.Add(barrier)
    pivot=pcbnew.VECTOR2I_MM(30,30);angle=pcbnew.EDA_ANGLE(90*quarter,pcbnew.DEGREES_T)
    for item in [*board.GetFootprints(),*board.GetTracks(),*board.GetDrawings()]:
        item.Rotate(pivot,angle)
        if back:item.Flip(pivot,True)
    demand=next(d for d in get(board)['requests'] if d['pad_uuid']==force._uid(root))
    return board,demand,root,target


def _capture(monkeypatch,board,demand):
    calls=[]
    # Isolate the finite maze scheduling decision, not native clearance.
    monkeypatch.setattr(route.fr,'_canonical_45_xy_paths',lambda *a:[])
    monkeypatch.setattr(route.fr,'_offset_manhattan_xy_paths',lambda *a:[])
    def search(b,start,end,width,layer,gap,net,*args,**kwargs):
        assert b is board
        calls.append((tuple(end),width,layer,gap,net))
        return None
    monkeypatch.setattr(route.fr,'_guarded_profiled_lastmile_legs',search)
    before=field._field_snapshot_inventory(board)
    result=route.menus(board,demand,width_nm=200000,timeout_s=2.,max_choices=1)
    assert before==field._field_snapshot_inventory(board)
    assert result['source_unchanged'] and not result['ops']
    assert result['no_path_proof'] is False
    assert not result['current_authority'] and not result['retirement_authority']
    assert not result['release_authority']
    return result,calls


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_blocked_preferred_tail_cannot_starve_short_legal_run(monkeypatch,quarter,back):
    board,demand,root,target=_example(quarter,back)
    result,calls=_capture(monkeypatch,board,demand)
    assert calls and result['pickup_tail_preflight']['foreign_or_edge_refusals']>0
    guard=route.contact_guard(board,demand,width_nm=200000,deadline=time.monotonic()+2)
    peer=guard['opposite'];size=target.GetSize()
    reach=math.hypot(*tuple(size))/2e6
    x,y,ux,uy=route.fr._inner_edge_pt(target,peer.GetPosition(),inset_mm=min(.12,reach*.25))
    axis=(round(x*1e6),round(y*1e6))
    # Both tiers keep the unchanged six-goal bound. Each actual funded
    # goal has a complete, independently native-clear finishing tail.
    assert len(calls)<=12
    physical_ports=set()
    for at,width,layer,gap,net in calls:
        along=round((at[0]-axis[0])*ux+(at[1]-axis[1])*uy)
        pickup=(at[0]-round(ux*along),at[1]-round(uy*along))
        assert 299999<=along<=450001
        assert guard['planar'](at,pickup,width,layer)
        a,b=pcbnew.VECTOR2I(*at),pcbnew.VECTOR2I(*pickup)
        assert route.fr._edge_leg_clear(board,a,b,width/2+gap)
        assert route.fr._tap_foreign_clear(board,a,b,width,layer,gap,{net},foreign_cache={})
        physical_ports.add(pickup)
    assert len(physical_ports)==5
    assert result['pickup_tail_preflight']['queries']==30


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('edge',[False,True])
def test_no_maze_work_for_entirely_foreign_or_edge_blocked_tails(monkeypatch,quarter,back,edge):
    board,demand,_,_=_example(quarter,back,blocked_all=True,edge=edge)
    result,calls=_capture(monkeypatch,board,demand)
    assert not calls
    assert result['pickup_tail_preflight']['queries']>0
    assert result['pickup_tail_preflight']['foreign_or_edge_refusals']==result['pickup_tail_preflight']['queries']
