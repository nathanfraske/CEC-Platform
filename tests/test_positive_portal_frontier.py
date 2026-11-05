"""Positive local escapes remain resumable after whole-edge consumer refusal."""
import copy
from unittest.mock import patch

import pytest
import cec_portal_feedback as feedback
import cec_precision_route as precision


class Clock:
    def __init__(self): self.now = 0.
    def __call__(self): return self.now


def test_consumer_requests_two_distinct_positive_rows_not_first_positive_again():
    clock=Clock(); rows={key:[] for key in ('a','b')}; calls=[]
    def probe(domain,deadline):
        calls.append(domain);clock.now=deadline
        rows[domain].append(len(rows[domain]))
        return dict(candidates=rows[domain],complete=False,progress=len(rows[domain]))
    report=feedback.fair_screen_domains([('a','b')],probe,clock=clock,
        deadline=10.,minimum_candidates=2)
    assert calls==['a','b','a','b'] and report['ready_groups']==[0]
    assert report['stalled_domains']==[]


def test_completed_smaller_beam_remains_usable_and_is_not_replayed():
    calls=[]
    def probe(domain,deadline):
        calls.append(domain)
        return dict(candidates=[domain],complete=True,progress=1)
    report=feedback.fair_screen_domains([('a','b')],probe,minimum_candidates=4)
    assert calls==['a','b'] and report['ready_groups']==[0]


@pytest.mark.parametrize('positives',[[],['usable']])
def test_unchanged_full_quantum_is_stall_not_exhaustion(positives):
    clock=Clock()
    def probe(domain,deadline):
        clock.now=deadline
        return dict(candidates=positives,complete=False,progress=7)
    report=feedback.fair_screen_domains([('a','b')],probe,clock=clock,
        deadline=100.,minimum_candidates=4)
    assert len(report['visits'])==12
    assert report['stalled_domains']==['a','b']
    assert not report['budget_exhausted'] and not report['round_limit_reached']
    assert all(not r['complete'] for r in report['domains'].values())
    assert report['ready_groups']==([0] if positives else [])


def test_limited_deadline_share_is_not_full_quantum_stall():
    clock=Clock()
    def probe(domain,deadline):
        clock.now=deadline
        return dict(candidates=[],complete=False,progress=0)
    result=feedback.fair_screen_domains([('a','b')],probe,clock=clock,
        deadline=3.,max_rounds=10)
    assert not result['stalled_domains']


def test_actual_progress_resets_stall_counter():
    clock=Clock(); calls=0
    def probe(domain,deadline):
        nonlocal calls
        calls+=1;clock.now=deadline
        return dict(candidates=['a'] if calls==9 else [],complete=False,
                    progress=1 if calls>=6 else 0)
    result=feedback.fair_screen_domains([('a',)],probe,clock=clock,deadline=100.)
    assert calls==9 and result['ready_groups']==[0] and not result['stalled_domains']


@pytest.mark.parametrize('policy',[dict(minimum_candidates=0),
    dict(minimum_candidates=1.5),dict(maximum_stalled_rounds=0),
    dict(maximum_stalled_rounds=True)])
def test_invalid_positive_frontier_policy(policy):
    with pytest.raises(ValueError):feedback.fair_screen_domains([],None,**policy)


def consumer_failure():
    return dict(refused='no admitted portal pair',portal_evidence={
        'max_fanins_per_side':4,
        'attempts':[dict(refused='whole portal edge admission failed')],
        'screened':{'start:+1':dict(accepted=1,domain_complete=False),
                    'end:+1':dict(accepted=1,domain_complete=False)}})


def test_consumer_refill_is_one_two_four_and_transaction_scoped():
    with patch.object(precision,'_route_coupled_via_portal_beam',
            side_effect=lambda *a,**k:consumer_failure()) as beam:
        result=precision._route_coupled_via_portals(object(),{},(),
            max_portal_refills=9,deadline=float('inf'))
    assert [c.kwargs['minimum_screen_candidates'] for c in beam.call_args_list]==[1,2,4]
    resumes=beam.call_args_list[0].kwargs['_screen_resumes']
    assert all(c.kwargs['_screen_resumes'] is resumes and
               c.kwargs['deadline']==float('inf') for c in beam.call_args_list)
    assert result['portal_refill']['selected_round']==2
    assert all(r['kind']=='positive-frontier-widening'
               for r in result['portal_refill']['rounds'])


@pytest.mark.parametrize('stop',['success','expired','fixed','complete','stalled','local-only'])
def test_no_widening_when_it_cannot_help_or_changes_success(stop):
    row=consumer_failure(); kwargs={}
    if stop=='success':row={'route_mode':'unchanged'}
    if stop=='expired':kwargs['deadline']=0.
    if stop=='fixed':kwargs['start_prequalified']={}
    if stop=='complete':
        for item in row['portal_evidence']['screened'].values():item['domain_complete']=True
    if stop=='stalled':row['portal_evidence']['screen_schedule']={
        'stalled_domains':list(row['portal_evidence']['screened'])}
    if stop=='local-only':row['portal_evidence']['attempts']=[]
    before=copy.deepcopy(row)
    with patch.object(precision,'_route_coupled_via_portal_beam',return_value=row) as beam:
        result=precision._route_coupled_via_portals(object(),{},(),**kwargs)
    assert beam.call_count==1 and result==before


def test_loaded_native_positive_resume_reaches_later_phase_and_rolls_back(tmp_path):
    import pcbnew
    from test_native_pair_terminal_layers import fixture
    from cec_local_copper_cell import copper_inventory
    board,pair,ends,_=fixture()
    existing=pcbnew.PCB_TRACK(board)
    existing.SetStart(pcbnew.VECTOR2I_MM(1,1));existing.SetEnd(pcbnew.VECTOR2I_MM(2,1))
    existing.SetNetCode(board.GetNetcodeFromNetname(pair['p']));board.Add(existing)
    path=tmp_path/'positive-frontier.kicad_pcb'
    pcbnew.SaveBoard(str(path),board,True);board=pcbnew.LoadBoard(str(path))
    original=copper_inventory(board); clock=Clock(); direct_successes=set(); queries=[]
    shared={}
    def fanin(_board,_pair,endpoints,**kwargs):
        clock.now+=.1
        key=(tuple(endpoints),kwargs['allow_detour'])
        assert key not in queries, 'completed exact query replayed'
        queries.append(key)
        # One direct candidate per terminal/polarity heading; another is
        # available only in the later dogbone phase. Emit temporary native
        # copper on every query so rollback is exercised, not merely assumed.
        parent=pcbnew.PCB_TRACK(board)
        parent.SetStart(pcbnew.VECTOR2I_MM(1,1));parent.SetEnd(pcbnew.VECTOR2I_MM(2,1))
        board.Add(parent)
        heading=tuple(kwargs['preferred_end_direction'])
        separation=(endpoints[1][0]-endpoints[3][0],endpoints[1][1]-endpoints[3][1])
        polarity=1 if heading[0]*separation[1]-heading[1]*separation[0]>0 else -1
        domain=(tuple(endpoints[0]),polarity)
        if not kwargs['allow_detour'] and domain in direct_successes:
            return dict(refused='synthetic obstacle',admission={'direct':{'p':{}}})
        direct_successes.add(domain)
        return dict(handoff_route_heading=heading,handoff_member_coherence=1.,
            handoff_heading_alignment=1.,length_mm=1.,coupled_coverage_pct=100.)
    real_scheduler=feedback.fair_screen_domains
    def scheduler(*a,**k):return real_scheduler(*a,**k,clock=clock)
    with patch.object(precision.time,'monotonic',side_effect=clock), \
         patch.object(feedback,'fair_screen_domains',side_effect=scheduler), \
         patch.object(precision,'_route_paired_stub',side_effect=fanin), \
         patch.object(precision,'_pair_graph_geometry',return_value={'ok':True}):
        first=precision._route_coupled_via_portal_beam(board,pair,ends,
            max_portal_pairs=0,deadline=200.,_screen_resumes=shared)
        first_queries=len(queries)
        second=precision._route_coupled_via_portal_beam(board,pair,ends,
            max_portal_pairs=0,deadline=200.,_screen_resumes=shared,
            minimum_screen_candidates=2)
    assert first.get('refused') and second.get('refused')
    assert len(queries)>first_queries
    assert any(k[1] for k in queries[first_queries:])
    screens=second['portal_evidence']['screened']
    assert any(row['accepted']>=2 and 'bounded-dogbone' in row['phase_checked']
               for row in screens.values())
    assert not second['portal_evidence']['screen_schedule']['round_limit_reached']
    for row in screens.values():
        keys=[feedback.portal_geometry_key(r) for r in row['candidates']]
        assert len(keys)==len(set(keys))
    assert copper_inventory(board)==original
