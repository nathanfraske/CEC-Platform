"""Correlated proposals obey the same geometry rules as emitted copper."""
import math
import time
from unittest.mock import patch

import pytest
import pcbnew
import cec_pair_ribbon as ribbon
import cec_precision_route as route

PAIR=dict(name='anonymous',kind='can',p='positive',n='negative',width=.2,gap=.25)


@pytest.mark.parametrize('angle',[0,45,90,180,270])
@pytest.mark.parametrize('swap',[False,True])
def test_correlated_menu_preserves_endpoints_and_octilinear_spacing(angle,swap):
    c,s=math.cos(math.radians(angle)),math.sin(math.radians(angle))
    def pose(x,y):return (20+x*c-y*s,20+x*s+y*c)
    ps,pe,ns,ne=map(lambda p:pose(*p),[(0,0),(8,1),(0,.8),(8,1.8)])
    if swap:ps,pe,ns,ne=ns,ne,ps,pe
    rows=ribbon.candidates(PAIR,ps,pe,ns,ne)
    assert rows and len(rows)<=128
    assert any(row['coupling_contract']['ok'] for row in rows)
    for row in rows:
        assert (row['p'][0],row['p'][-1],row['n'][0],row['n'][-1])==(ps,pe,ns,ne)
        assert route._polyline_is_octilinear(row['p']) and route._polyline_is_octilinear(row['n'])
        assert min(route._polyline_min_opening_angle(row['p']),route._polyline_min_opening_angle(row['n']))>=89
        assert route._polys_no_cross(row['p'],row['n'])
        assert route._pair_min_clear(row['p'],row['n'],-1,-1,.2,.25,strict_pair_gap=True)


def test_menu_is_deterministic_bounded_and_deadline_cannot_admit_partial_search():
    args=(PAIR,(0,0),(8,1),(0,.8),(8,1.8))
    assert ribbon.candidates(*args,limit=3)==ribbon.candidates(*args,limit=3)
    assert len(ribbon.candidates(*args,limit=3))<=3
    assert ribbon.candidates(*args,limit=0)==[]
    assert ribbon.candidates(*args,deadline=time.monotonic()-1)==[]
    with pytest.raises(ValueError,match='invalid'):
        ribbon.candidates(PAIR,(float('nan'),0),(8,1),(0,.8),(8,1.8))


def native_board():
    b=pcbnew.BOARD();b.SetCopperLayerCount(6)
    for name in ('positive','negative','blocker'):b.Add(pcbnew.NETINFO_ITEM(b,name))
    for a,z in [((0,0),(40,0)),((40,0),(40,40)),((40,40),(0,40)),((0,40),(0,0))]:
        edge=pcbnew.PCB_SHAPE(b);edge.SetLayer(pcbnew.Edge_Cuts);edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a));edge.SetEnd(pcbnew.VECTOR2I_MM(*z));b.Add(edge)
    return b


def test_native_ribbon_is_constructed_without_raw_diagonal_and_keeps_pair_contract():
    b=native_board()
    ends=((10,10),(18,11),(10,10.8),(18,11.8))
    old=route._short_pair_ribbon_candidates(PAIR,ends[0],ends[1],ends[2],ends[3])
    assert old and not any(route._polyline_is_octilinear(r['p']) and route._polyline_is_octilinear(r['n']) for r in old)
    result=route._route_paired_stub(b,PAIR,ends)
    assert not result.get('refused'),result
    assert result['coupled_coverage_pct']>=60
    assert list(b.GetTracks())
    for track in b.GetTracks():
        a,z=track.GetStart(),track.GetEnd()
        assert route._segment_is_octilinear((a.x/1e6,a.y/1e6),(z.x/1e6,z.y/1e6))


def test_new_domain_does_not_run_after_legacy_success_or_when_detour_disabled():
    with patch.object(ribbon,'candidates',side_effect=AssertionError('unnecessary domain')):
        result=route._route_paired_stub(native_board(),PAIR,((10,10),(18,10),(10,10.45),(18,10.45)))
        assert not result.get('refused'),result
        route._route_paired_stub(native_board(),PAIR,((10,10),(18,11),(10,10.8),(18,11.8)),allow_detour=False)


def test_native_foreign_copper_cannot_be_ignored_by_new_generator():
    b=native_board()
    track=pcbnew.PCB_TRACK(b);track.SetNet(b.FindNet('blocker'));track.SetLayer(pcbnew.F_Cu)
    track.SetStart(pcbnew.VECTOR2I_MM(14,0));track.SetEnd(pcbnew.VECTOR2I_MM(14,40))
    track.SetWidth(pcbnew.FromMM(1));b.Add(track)
    before={t.m_Uuid.AsString() for t in b.GetTracks()}
    result=route._route_paired_stub(b,PAIR,((10,10),(18,11),(10,10.8),(18,11.8)))
    assert result.get('refused')
    assert {t.m_Uuid.AsString() for t in b.GetTracks()}==before
