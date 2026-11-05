"""Short source splices expand proposals, never physical routing authority."""
import math
from copy import deepcopy
import pytest
import cec_precision_route as precision


@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('mirror',(False,True))
def test_rotated_mirrored_equal_pair_has_short_transition_seats_without_lane_exchange(turn,mirror):
    def point(x,y):
        if mirror:x=-x
        for _ in range(turn):x,y=-y,x
        return x+30,y+30
    points=[point(0,0),point(0,.45),point(10,0),point(10,.45)]
    before=deepcopy(points)
    q=precision._paired_portal_candidates(*points,width=.25,gap=.2,portal_separation=.75,minimum_lead_mm=.25)
    assert points==before
    for side in ('start','end'):
        short=[r for r in q['by_sign'][q['preferred_signs'][side]][side] if r['lead_mm']==.25]
        assert short and all(abs(math.dist(r['p'],r['n'])-.75)<1e-6 for r in short)
        assert all(r['actual_p']==points[0 if side=='start' else 2]
                   and r['actual_n']==points[1 if side=='start' else 3] for r in short)


def test_legacy_default_menu_is_identical_and_has_no_short_seat():
    args=((0,0),(0,.45),(10,0),(10,.45));kwargs=dict(width=.25,gap=.2,portal_separation=.75)
    first=precision._paired_portal_candidates(*args,**kwargs)
    assert first==precision._paired_portal_candidates(*args,**kwargs,minimum_lead_mm=1.3)
    assert all(row['lead_mm']>=1.3 for group in first['by_sign'].values() for rows in group.values() for row in rows)


@pytest.mark.parametrize('value',(True,False,None,'0.25',0,-1,.099999,1.300001,float('nan'),float('inf')))
def test_invalid_local_lead_cannot_make_an_unbounded_or_implicit_menu(value):
    with pytest.raises(ValueError,match='bounded_explicit'):
        precision._paired_portal_candidates((0,0),(0,.45),(10,0),(10,.45),
            width=.25,gap=.2,minimum_lead_mm=value)


def test_wide_pinfield_still_keeps_geometric_convergence_floor_with_explicit_short_menu():
    q=precision._paired_portal_candidates((0,0),(0,8),(20,0),(20,.45),width=.25,gap=.2,
        portal_separation=.75,minimum_lead_mm=.25)
    expected=.5*(8-.45)-.15
    assert all(r['lead_mm']>=expected-1e-9 for group in q['by_sign'].values() for r in group['start'])


def test_external_completed_screen_cache_does_not_reuse_another_lead_domain():
    import time
    import pcbnew
    from unittest.mock import patch
    from test_lastmile import _board
    b=_board([],edge=(0,0,30,30));b.SetCopperLayerCount(6)
    for net in ('arbitrary-P','arbitrary-N'):b.Add(pcbnew.NETINFO_ITEM(b,net))
    pair=dict(name='renamed',kind='can',p='arbitrary-P',n='arbitrary-N',width=.25,gap=.2,clearance=.2)
    original=precision._paired_portal_candidates
    def finite(*args,**kwargs):
        q=original(*args,**kwargs)
        for group in q['by_sign'].values():
            for side in group:group[side]=group[side][:1]
        return q
    cache={};refusal=dict(refused='no clear direct paired terminal stub',admission=dict(direct=dict(p={},n={})))
    with patch.object(precision,'_paired_portal_candidates',side_effect=finite),patch.object(
            precision,'_route_paired_stub',return_value=refusal) as stub:
        args=(b,pair,((10,10),(20,10),(10,10.45),(20,10.45)))
        options=dict(layer='F.Cu',middle_layer='F.Cu',max_fanins_per_side=1,max_portal_pairs=1,
                     portal_screen_cache=cache,deadline=time.monotonic()+10.)
        first=precision._route_coupled_via_portal_beam(*args,**options)
        calls=stub.call_count
        assert first.get('refused') and calls>0 and cache
        second=precision._route_coupled_via_portal_beam(*args,minimum_portal_lead_mm=.9,**options)
        assert second.get('refused') and stub.call_count>calls
