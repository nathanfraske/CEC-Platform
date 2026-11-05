"""Search fairness is scheduling only, never geometric admission."""
from unittest import mock

import pytest
import cec_portal_feedback as feedback
import cec_precision_route as precision


class Clock:
    def __init__(self): self.now = 0.
    def __call__(self): return self.now


def test_impossible_first_polarity_does_not_starve_ready_alternative():
    clock = Clock(); calls = []
    def probe(domain, deadline):
        calls.append(domain)
        clock.now = deadline
        return dict(candidates=[domain] if domain.endswith('-') else [],
                    complete=False, progress=len(calls))
    report = feedback.fair_screen_domains(
        [('source+', 'target+'), ('source-', 'target-')], probe,
        deadline=10., clock=clock)
    assert calls == ['source+', 'target+', 'source-', 'target-']
    assert report['ready_groups'] == [1]
    assert clock.now < 2.
    assert not report['domains']['source+']['complete']


def test_interrupted_query_gets_larger_quantum_without_false_completion():
    clock=Clock(); calls=[]
    def probe(domain, deadline):
        enough=deadline-clock.now >= .5
        calls.append((domain,enough)); clock.now=deadline
        return dict(candidates=[domain] if enough else [], complete=False,
                    progress=int(enough))
    report=feedback.fair_screen_domains([('a','b')],probe,deadline=20.,clock=clock)
    assert calls==[('a',False),('b',False),('a',True),('b',True)]
    assert report['ready_groups']==[0]


def test_finite_exhausted_domains_are_not_repeated():
    calls=[]
    def probe(domain,deadline):
        calls.append(domain);return dict(candidates=[],complete=True,progress=1)
    result=feedback.fair_screen_domains([('a','b')],probe)
    assert calls==['a','b'] and result['ready_groups']==[]
    assert not result['budget_exhausted']


def test_no_progress_has_bounded_rounds_and_no_impossibility_claim():
    result=feedback.fair_screen_domains([('a','b')],
        lambda *args:dict(candidates=[],complete=False,progress=0),max_rounds=3)
    assert len(result['visits'])==6 and result['round_limit_reached']
    assert not any(row['complete'] for row in result['domains'].values())


@pytest.mark.parametrize('policy',[{'max_rounds':0},{'initial_quantum_s':0},
    {'maximum_quantum_s':float('nan')},{'deadline':float('inf')}])
def test_invalid_budget_policy_refuses(policy):
    with pytest.raises(ValueError):feedback.fair_screen_domains([],None,**policy)


def test_native_screen_resumes_completed_rows_and_preserves_parent_copper():
    pcbnew=pytest.importorskip('pcbnew');board=pcbnew.BOARD()
    for name in ('P','N','GND'):board.Add(pcbnew.NETINFO_ITEM(board,name))
    parent=pcbnew.PCB_TRACK(board)
    parent.SetStart(pcbnew.VECTOR2I_MM(1,1));parent.SetEnd(pcbnew.VECTOR2I_MM(2,1))
    parent.SetNetCode(board.GetNetcodeFromNetname('GND'));board.Add(parent)
    original={item.m_Uuid.AsString() for item in board.GetTracks()}
    pair=dict(name='arbitrary',p='P',n='N',width=.2,gap=.13)
    clock=Clock();probed=[]
    def refused(_board,_pair,endpoints,**kw):
        key=(tuple(endpoints),kw['allow_detour'])
        assert key not in probed, 'completed exact query was replayed'
        probed.append(key);clock.now+=.10
        temporary=pcbnew.PCB_TRACK(board);board.Add(temporary)
        return dict(refused='synthetic exact obstacle',admission={'direct':{'p':{}}})
    # A long fake clock is advanced only by exact queries. The scheduler
    # receives the same clock so its subdeadlines bind the real screen loop.
    real_scheduler=feedback.fair_screen_domains
    def scheduler(*args,**kwargs):
        return real_scheduler(*args,**kwargs,clock=clock,max_rounds=3)
    with mock.patch.object(precision.time,'monotonic',side_effect=clock), \
            mock.patch.object(feedback,'fair_screen_domains',side_effect=scheduler), \
            mock.patch.object(precision,'_route_paired_stub',side_effect=refused):
        result=precision._route_coupled_via_portal_beam(board,pair,
            ((4,9),(34,9),(4,11),(34,11)),deadline=20.)
    assert result.get('refused')
    screens=result['portal_evidence']['screened']
    assert set(screens)=={'start:+1','end:+1','start:-1','end:-1'}
    assert all(row['checked']>0 and row['resume_calls']>1 for row in screens.values())
    assert all(not row['domain_complete'] for row in screens.values())
    assert {item.m_Uuid.AsString() for item in board.GetTracks()}==original
