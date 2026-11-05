"""Actual pair search expiry retains its bounded causes, never no-path rights."""
import copy,math,time
import pytest
import pcbnew
import cec_precision_route as route
import cec_probe_evidence as probe
from cec_search_completion import search_completion_evidence


PAIR=dict(name='renamed_bus',kind='diff',p='arbitrary_positive',n='arbitrary_negative',
    width=.2,gap=.2,clearance=.2)


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('layer',['F.Cu','In2.Cu','B.Cu'])
def test_actual_deadline_exit_keeps_native_search_frontier_and_no_copper(monkeypatch,angle,layer):
    board=pcbnew.CreateEmptyBoard();board.SetCopperLayerCount(6)
    for net in (PAIR['p'],PAIR['n']):board.Add(pcbnew.NETINFO_ITEM(board,net))
    c=round(math.cos(math.radians(angle)));s=round(math.sin(math.radians(angle)))
    at=lambda x,y:(50+c*x-s*y,50+s*x+c*y)
    ends=tuple(at(x,y) for x,y in ((0,0),(20,0),(0,.8),(20,.8)))
    expired=[False];calls=[]
    def grid(*args,**kwargs):
        calls.append(kwargs['layer_id'])
        kwargs['diagnostics'].update(status='deadline_exhausted',visited=37,
            frontier_gap_mm=7.25,nearest_frontier_mm=list(at(12.75,.4)),
            rejection_counts={'foreign copper':4},dominant_blockers=[dict(ref='renamed_owner')])
        expired[0]=True
        return None
    monkeypatch.setattr(route,'_deadline_expired',lambda deadline:expired[0])
    monkeypatch.setattr(route,'_grid_coupled_path',grid)
    result=route.route_coupled_pair(board,PAIR,endpoints=ends,layer=layer,
        pair_grid=True,allow_layer_transitions=False,prefer_grid=True,deadline=time.monotonic()+10.)
    assert result['search_budget_exhausted'] and calls==[board.GetLayerID(layer)]
    assert not list(board.GetTracks())
    cert=result['failure_certificate']
    assert cert['search_interrupted'] and 'search_exhausted' in cert['classification']
    assert cert['conclusion']=='bounded_search_exhausted_not_global_impossibility'
    assert cert['grid']['attempt_count']==1 and cert['grid']['status_counts']=={'deadline_exhausted':1}
    assert cert['grid']['nearest_frontier']['gap_mm']==7.25
    assert cert['grid']['attempts'][0]['visited']==37
    assert cert['grid']['attempts'][0]['launch_geometry'] is not None
    trace=probe.compact_pair_search_trace(dict(outer=dict(inner_refusal=result)))
    assert trace[0]['search_budget_exhausted'] and search_completion_evidence(trace)['inconclusive']
    assert trace[0]['failure_certificate']['nearest_frontier']['gap_mm']==7.25
    assert trace[0]['failure_certificate']['explored_blocker_refs']==['renamed_owner']
    assert trace[0]['failure_certificate']['grid_attempts'][0]['visited']==37
    assert probe.compact_pair_search_trace(dict(search_trace=trace))==trace


@pytest.mark.parametrize('wrapper',['inner_refusal','endpoint_route','third_party_label','nested'])
def test_endpoint_only_refusal_is_included_in_outer_geometric_stack(wrapper):
    raw={wrapper:dict(refused='ribbon deadline exhausted',grid=dict(status='deadline_exhausted',visited=9,
        frontier_gap_mm=2.,nearest_frontier_mm=[7.,.4],dominant_blockers=[dict(ref='arbitrary_part')]))}
    before=copy.deepcopy(raw)
    cert=route._pair_route_failure_certificate(PAIR,((0,0),(10,0),(0,.8),(10,.8)),
        layer='In2.Cu',width=.2,gap=.2,clearance=.2,endpoint_pofv_refusals=[raw],search_interrupted=True)
    assert raw==before and cert['grid']['attempt_count']==1
    assert cert['grid']['nearest_frontier']['gap_mm']==2.
    assert cert['grid']['explored_blocker_refs']==['arbitrary_part']
    assert any('endpoint_pofv' in q['path'] for q in cert['grid']['attempts'])


@pytest.mark.parametrize('flag',['search_budget_exhausted','deadline_exhausted','flow_leg_budget_exhausted','budget_exhausted'])
@pytest.mark.parametrize('value',[True,False])
def test_leaf_budget_flags_survive_projection_without_becoming_no_path(flag,value):
    raw=dict(wrapper=dict(refused='bounded candidate failed',**{flag:value}));before=copy.deepcopy(raw)
    trace=probe.compact_pair_search_trace(raw)
    assert len(trace)==1 and trace[0][flag] is value
    assert search_completion_evidence(trace)['inconclusive'] is value and raw==before
    assert probe.compact_pair_search_trace(dict(search_trace=trace))==trace


def test_one_native_grid_attempt_is_not_counted_twice():
    row=dict(launch_signs=[1,-1],launch_geometry=dict(start_lead_mm=.5),
        grid=dict(status='grid_exhausted',visited=3,frontier_gap_mm=1.5))
    cert=route._pair_route_failure_certificate(PAIR,((0,0),(10,0),(0,.8),(10,.8)),
        layer='B.Cu',width=.2,gap=.2,clearance=.2,grid_failure_diagnostics=[row])
    assert cert['grid']['attempt_count']==1 and cert['grid']['status_counts']=={'grid_exhausted':1}
    assert not cert['search_interrupted'] and 'search_exhausted' not in cert['classification']


def test_compact_forensic_details_remain_bounded():
    cert=dict(conclusion='bounded_search_exhausted_not_global_impossibility',search_interrupted=True,
        dominant_reasons=[dict(reason=str(i)) for i in range(100)],
        dominant_blockers=[dict(uuid=str(i)) for i in range(100)],
        grid=dict(explored_blocker_refs=[str(i) for i in range(100)],
            attempts=[dict(status='deadline_exhausted',visited=i) for i in range(100)]))
    trace=probe.compact_pair_search_trace(dict(failure_certificate=cert),limit=1)
    q=trace[0]['failure_certificate']
    assert len(q['dominant_reasons'])==len(q['dominant_blockers'])==len(q['explored_blocker_refs'])==16
    assert len(q['grid_attempts'])==8 and q['search_interrupted']
