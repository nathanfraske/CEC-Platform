"""Exact-objective search must agree with exhaustive geometric enumeration."""
import math
import random
import time
from unittest.mock import patch

import pytest
import cec_precision_route as route


def exhaustive(ps, ns, *, p_span, n_span, width, gap, max_skew=None,
               preferred_end_direction=None, minimum_end_coherence=None,
               strict_pair_gap=False, existing_signed_skew_mm=0.):
    choices = []
    for p in ps:
        for n in ns:
            if minimum_end_coherence is not None and route._pair_end_coherence(p,n)+1e-9 < minimum_end_coherence:
                continue
            if not route._polys_no_cross(p,n): continue
            if not route._pair_min_clear(p,n,-1,-1,width,gap,strict_pair_gap=strict_pair_gap): continue
            pl = sum(math.dist(a,b) for a,b in zip(p,p[1:]))
            nl = sum(math.dist(a,b) for a,b in zip(n,n[1:]))
            skew = abs(existing_signed_skew_mm+pl-nl)
            heading = min(route._path_end_heading_alignment(p,preferred_end_direction),
                          route._path_end_heading_alignment(n,preferred_end_direction))
            shortfall = max(0.,math.cos(math.radians(67.5))-heading)
            if max_skew is None:
                score = (round(skew,6),round(shortfall,6),round(pl+nl,6))
            else:
                score = (round(max(0.,skew-max_skew),6),round(shortfall,6),
                         round(max(pl/p_span,nl/n_span),6),round(pl+nl,6),round(skew,6))
            choices.append(score+(len(p)+len(n),tuple(p),tuple(n)))
    return tuple(list(row) for row in min(choices)[-2:]) if choices else None


def menu(start, end, count=10):
    sx,sy=start; ex,ey=end
    return [[start,end]] + [route._chamfer_axis_path(
        [start,(sx,sy+offset),(ex,sy+offset),end])
        for offset in [(-1 if i%2 else 1)*(i+1)*.5 for i in range(count-1)]]


@pytest.mark.parametrize('angle', [0,45,90,180,270])
@pytest.mark.parametrize('max_skew', [None,.25,4.])
@pytest.mark.parametrize('crossed', [False,True])
@pytest.mark.parametrize('existing_signed_skew_mm', [-2.268766,0.,2.268766])
def test_ranked_selection_matches_exhaustive_with_identical_tiebreaks(angle,max_skew,crossed,existing_signed_skew_mm):
    ps = menu((0,0),(4,0))
    ns = menu((0,.8),(4,-.8 if crossed else .8))
    radians=math.radians(angle); c,s=math.cos(radians),math.sin(radians)
    def rotate(paths):
        return [[(10+x*c-y*s,20+x*s+y*c) for x,y in path] for path in paths]
    ps,ns=rotate(ps),rotate(ns)
    options=dict(width=.2,gap=.2,p_span=4.,n_span=math.dist(ns[0][0],ns[0][-1]),
                 max_skew=max_skew,preferred_end_direction=(c,s),
                 existing_signed_skew_mm=existing_signed_skew_mm,
                 minimum_end_coherence=.7,strict_pair_gap=True)
    expected=exhaustive(ps,ns,**options)
    for seed in (1,2):
        random.Random(seed).shuffle(ps);random.Random(seed+1).shuffle(ns)
        actual=route._ranked_joint_escape(ps,ns,**options)
        assert actual == expected


def test_open_domain_prunes_dominated_geometry_without_changing_result():
    ps,ns=menu((0,0),(4,0),32),menu((0,.8),(4,.8),32)
    options=dict(width=.2,gap=.2,p_span=4.,n_span=4.,max_skew=4.)
    evidence={}
    expected=exhaustive(ps,ns,**options)
    with patch.object(route,'_polys_no_cross',wraps=route._polys_no_cross) as crossing:
        actual=route._ranked_joint_escape(ps,ns,diagnostics=evidence,**options)
    assert actual==expected
    assert evidence['path_pairs_available']==1024
    assert evidence['path_pairs_checked']==crossing.call_count==1
    assert evidence['objective_pruned_pairs']==1023
    assert not evidence['deadline_exhausted']


def test_expired_budget_returns_no_unchecked_candidate():
    evidence={}
    result=route._ranked_joint_escape([[(0,0),(4,0)]],[[(0,.8),(4,.8)]],
        width=.2,gap=.2,p_span=4,n_span=4,deadline=time.monotonic()-1,diagnostics=evidence)
    assert result is None
    assert evidence['deadline_exhausted'] and evidence['path_pairs_checked']==0


def test_fully_blocked_domain_still_checks_every_candidate():
    evidence={}
    ps,ns=menu((0,0),(4,0),4),menu((0,.8),(4,.8),4)
    with patch.object(route,'_polys_no_cross',return_value=False) as crossing:
        result=route._ranked_joint_escape(ps,ns,width=.2,gap=.2,p_span=4,n_span=4,
                                         diagnostics=evidence)
    assert result is None
    assert evidence['path_pairs_checked']==crossing.call_count==16
    assert evidence['objective_pruned_pairs']==0


@pytest.mark.parametrize('sign',[-1,1])
def test_existing_mismatch_prefers_compensation_not_another_locally_balanced_leg(sign):
    straight_p=[(0,0),(4,0)]
    straight_n=[(0,.8),(4,.8)]
    detour_p=[(0,0),(1,-1),(3,-1),(4,0)]
    detour_n=[(0,.8),(1,1.8),(3,1.8),(4,.8)]
    ps,ns=([straight_p],[straight_n,detour_n]) if sign>0 else ([straight_p,detour_p],[straight_n])
    args=dict(width=.2,gap=.2,p_span=4.,n_span=4.,max_skew=.1)
    assert route._ranked_joint_escape(ps,ns,**args)==(straight_p,straight_n)
    actual=route._ranked_joint_escape(ps,ns,existing_signed_skew_mm=sign*.8,**args)
    assert actual == ((straight_p,detour_n) if sign>0 else (detour_p,straight_n))


@pytest.mark.parametrize('bad',[float('nan'),float('inf'),-float('inf')])
def test_nonfinite_existing_mismatch_cannot_disable_scoring(bad):
    with pytest.raises(ValueError,match='finite'):
        route._ranked_joint_escape([],[],width=.2,gap=.2,p_span=1,n_span=1,existing_signed_skew_mm=bad)


def test_native_stub_passes_actual_signed_multilayer_copper_to_escape_search():
    import pcbnew
    board=pcbnew.BOARD()
    board.SetCopperLayerCount(6)
    pair=dict(name='anonymous',kind='can',p='positive',n='negative',width=.2,gap=.2)
    for name in ('positive','negative'):
        board.Add(pcbnew.NETINFO_ITEM(board,name))
    for a,b in [((0,0),(40,0)),((40,0),(40,40)),((40,40),(0,40)),((0,40),(0,0))]:
        edge=pcbnew.PCB_SHAPE(board);edge.SetLayer(pcbnew.Edge_Cuts)
        edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a));edge.SetEnd(pcbnew.VECTOR2I_MM(*b));board.Add(edge)
    for name,length,layer in [('positive',2.,pcbnew.B_Cu),('negative',.5,pcbnew.F_Cu)]:
        track=pcbnew.PCB_TRACK(board);track.SetNet(board.FindNet(name));track.SetLayer(layer)
        track.SetStart(pcbnew.VECTOR2I_MM(2,2));track.SetEnd(pcbnew.VECTOR2I_MM(2+length,2))
        track.SetWidth(pcbnew.FromMM(.2));board.Add(track)
    before={item.m_Uuid.AsString() for item in board.GetTracks()}
    with patch.object(route,'_short_pair_ribbon_candidates',return_value=()), \
            patch('cec_pair_ribbon.candidates',return_value=()), \
            patch.object(route,'_joint_endpoint_escape',return_value=None) as escape:
        result=route._route_paired_stub(board,pair,((10,20),(14,21),(10,20.8),(14,21.8)))
    assert result.get('refused')
    assert escape.call_args.kwargs['existing_signed_skew_mm']==1.5
    assert escape.call_args.kwargs['max_skew']==4.0
    assert {item.m_Uuid.AsString() for item in board.GetTracks()}==before
