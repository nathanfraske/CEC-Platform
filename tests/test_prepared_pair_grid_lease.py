"""Native renamed/rotated prepared pair access does not repeat portal search."""
import time
from unittest.mock import patch

import pcbnew
import pytest
import cec_precision_route as route


def cell(quarter):
    b=pcbnew.CreateEmptyBoard(); b.SetCopperLayerCount(6)
    for name in ('RENAMED_P','RENAMED_N','OBSTACLE'):
        b.Add(pcbnew.NETINFO_ITEM(b,name))
    def xy(x,y):
        for _ in range(quarter):x,y=-y,x
        return 40+x,40+y
    for a,z in zip(((10,10),(70,10),(70,70),(10,70)),
                   ((70,10),(70,70),(10,70),(10,10))):
        edge=pcbnew.PCB_SHAPE(b);edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetLayer(pcbnew.Edge_Cuts);edge.SetStart(pcbnew.VECTOR2I_MM(*a))
        edge.SetEnd(pcbnew.VECTOR2I_MM(*z));b.Add(edge)
    ends=tuple(xy(*p) for p in ((-10,-.95),(10,-.635),(-10,.95),(10,.635)))
    for i,point in enumerate(ends):
        v=pcbnew.PCB_VIA(b);v.SetPosition(pcbnew.VECTOR2I_MM(*point))
        v.SetWidth(500000);v.SetDrill(250000);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        v.SetNet(b.FindNet('RENAMED_P' if i<2 else 'RENAMED_N'));b.Add(v)
    return b,ends,dict(name='renamed',kind='usb',p='RENAMED_P',n='RENAMED_N',
        width=.2,gap=.34,ztarget=90.,clearance=.2)


@pytest.mark.parametrize('quarter',range(4))
def test_native_unequal_pitch_prepared_access_spends_lease_on_body_not_new_portals(quarter):
    b,ends,pair=cell(quarter)
    before={q.m_Uuid.AsString() for q in b.GetTracks()}
    with patch.object(route,'_route_coupled_via_portals',side_effect=AssertionError('extra portal search')), \
         patch.object(route,'_grid_coupled_path',wraps=route._grid_coupled_path) as grid:
        r=route.route_coupled_pair(b,pair,endpoints=ends,layer='In2.Cu',
            pair_grid=True,allow_layer_transitions=False,prefer_grid=True,
            minimum_coupled_fraction=.35,deadline=time.monotonic()+10.)
    assert not r.get('refused'),r
    assert grid.call_count and r['route_mode']=='octilinear-grid'
    assert r['coupled_coverage_pct']>=35
    assert before<={q.m_Uuid.AsString() for q in b.GetTracks()}
    for q in b.GetTracks():
        if q.GetClass()=='PCB_TRACK':
            assert q.GetWidth()==200000 and q.GetLayer()==b.GetLayerID('In2.Cu')
            assert route._polyline_is_octilinear([(q.GetStart().x/1e6,q.GetStart().y/1e6),
                                                 (q.GetEnd().x/1e6,q.GetEnd().y/1e6)])


@pytest.mark.parametrize('quarter',range(4))
def test_prepared_grid_does_not_accept_blocked_exact_members(quarter):
    b,ends,pair=cell(quarter)
    obstacle=pcbnew.PCB_TRACK(b);obstacle.SetLayer(b.GetLayerID('In2.Cu'))
    obstacle.SetStart(pcbnew.VECTOR2I_MM(40,10));obstacle.SetEnd(pcbnew.VECTOR2I_MM(40,70))
    obstacle.SetWidth(5000000);obstacle.SetNet(b.FindNet('OBSTACLE'));b.Add(obstacle)
    if quarter%2:
        obstacle.SetStart(pcbnew.VECTOR2I_MM(10,40));obstacle.SetEnd(pcbnew.VECTOR2I_MM(70,40))
    before={q.m_Uuid.AsString() for q in b.GetTracks()}
    # A proposal is not authority. Even a nominally coupled supplied grid must
    # pass the real foreign-shape and member guards before emission.
    proposed=([ends[0],ends[1]],[ends[2],ends[3]],20.)
    with patch.object(route,'_route_coupled_via_portals',side_effect=AssertionError('extra portal search')), \
         patch.object(route,'_grid_coupled_path',return_value=proposed):
        r=route.route_coupled_pair(b,pair,endpoints=ends,layer='In2.Cu',
            pair_grid=True,allow_layer_transitions=False,prefer_grid=True,
            minimum_coupled_fraction=.35,deadline=time.monotonic()+10.)
    assert r.get('refused')
    assert before=={q.m_Uuid.AsString() for q in b.GetTracks()}


@pytest.mark.parametrize('kwargs',[dict(prefer_grid=1),dict(prefer_grid=True),
    dict(prefer_grid=True,pair_grid=True)])
def test_prepared_policy_rejects_ambiguous_or_recursive_configuration(kwargs):
    b,ends,pair=cell(0)
    with pytest.raises(ValueError):route.route_coupled_pair(b,pair,endpoints=ends,**kwargs)


def test_prepared_pair_expired_lease_does_not_renew_or_emit():
    b,ends,pair=cell(0);before={q.m_Uuid.AsString() for q in b.GetTracks()}
    with patch.object(route,'_grid_coupled_path') as grid:
        r=route.route_coupled_pair(b,pair,endpoints=ends,pair_grid=True,
            allow_layer_transitions=False,prefer_grid=True,deadline=time.monotonic()-1.)
    assert r.get('refused') and not grid.called
    assert before=={q.m_Uuid.AsString() for q in b.GetTracks()}


def test_grid_deadline_preserves_the_actual_previous_search_failure():
    b,ends,pair=cell(0);expired=[False]
    def exhausted(_board,**kwargs):
        kwargs['diagnostics'].update(status='deadline_exhausted',visited_states=123)
        expired[0]=True
        return None
    with patch.object(route,'_grid_coupled_path',side_effect=exhausted), \
         patch.object(route,'_deadline_expired',side_effect=lambda _deadline:expired[0]):
        r=route.route_coupled_pair(b,pair,endpoints=ends,pair_grid=True,
            allow_layer_transitions=False,prefer_grid=True,deadline=time.monotonic()+10.)
    assert r['search_budget_exhausted']
    assert len(r['grid_fallback'])==1
    assert r['grid_fallback'][0]['grid']==dict(status='deadline_exhausted',visited_states=123)
