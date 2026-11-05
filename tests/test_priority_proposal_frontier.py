"""Finite search continuation is not geometric admission or a no-path proof."""
import copy
import json
from types import SimpleNamespace

import pytest

import cec_placement_probe_coverage as coverage
import cec_synth_pipeline as synth


def rows(prefix='DEVICE', offset=0.):
    return [dict(kind='test_shift', ref=prefix, position=(offset+i, 1., 90.))
            for i in range(1, 5)]


def test_search_history_json_round_trip_and_unvisited_preference():
    moves = rows()
    visits = {}
    for move in moves[:2]:
        coverage.record(move, visits)
    encoded = json.loads(json.dumps(coverage.export_visits(visits)))
    restored = coverage.import_visits(encoded)
    assert restored == visits
    selected = coverage.select(moves, 2, visits=restored,
                               selector=lambda proposals,n: proposals[:n])
    assert selected == moves[2:]
    # It only orders work: nothing is excluded after every pose got a turn.
    for move in selected: coverage.record(move, restored)
    assert coverage.select(moves,4,visits=restored,
                           selector=lambda proposals,n:proposals[:n]) == moves
    assert not encoded['cached_admission']


@pytest.mark.parametrize('mutation', [
    lambda d: d.update(cached_admission=True),
    lambda d: d.update(exhaustion_is_no_path_proof=True),
    lambda d: d.update(purpose='passed'),
    lambda d: d['visits'][0].update(count=True),
    lambda d: d['visits'][0].update(count=0),
    lambda d: d['visits'][0].update(placements={'X': [float('nan'),0,0]}),
    lambda d: d['visits'].append(copy.deepcopy(d['visits'][0])),
])
def test_malformed_history_cannot_become_authority(mutation):
    visits={};coverage.record(rows()[0],visits)
    data=coverage.export_visits(visits);mutation(data)
    with pytest.raises(ValueError):coverage.import_visits(data)


@pytest.mark.parametrize('prefix,offset', [('DEVICE',0.),('RENAMED',91.75)])
@pytest.mark.parametrize('mode', ['second_wins','no_gain','timeout','deferred','error','deadline'])
def test_iterative_route_loop_spends_only_funded_rounds_on_distinct_samples(
        monkeypatch,prefix,offset,mode):
    import cec_operation_budget as budget
    moves=rows(prefix,offset);seen=[];histories=[];budgets=[]
    start=SimpleNamespace(P={prefix:(offset,1.,90.)},
                          route_preflight={'critical_pair_refused_count':2})
    before=copy.deepcopy(start.__dict__)
    def repair(cfg,current,**kwargs):
        histories.append(kwargs['probe_visits'])
        visits=kwargs['probe_visits']
        selected=coverage.select(moves,1,visits=visits,
                                  selector=lambda proposals,n:proposals[:n])
        for move in selected: coverage.record(move,visits)
        seen.extend(selected)
        reason={'timeout':'critical_probe_budget_inconclusive',
                'deferred':'critical_probe_budget_inconclusive',
                'error':'baseline_preflight_error'}.get(
                    mode,'no_critical_route_improving_legal_trial')
        accepted=mode=='second_wins' and len(seen)==2
        candidate=copy.deepcopy(current) if accepted else current
        if accepted:candidate.route_preflight={'critical_pair_refused_count':1}
        return candidate,dict(accepted=accepted,reason=reason,attempted=1,
            move=selected[0] if accepted else None,
            proposal_frontier=coverage.frontier(moves,visits),
            pair_probe_inconclusive=int(mode=='timeout'),
            pair_probe_deferred=[{'proof_complete':False}] if mode=='deferred' else [])
    def admission(*a,**k):
        budgets.append(k)
        return dict(start=not (mode=='deadline' and len(budgets)>1))
    monkeypatch.setattr(synth,'repair_route_preflight',repair)
    monkeypatch.setattr(budget,'round_admission',admission)
    monkeypatch.setattr(budget,'checkpoint',lambda *a,**k:None)
    selected,report=synth.repair_route_preflight_iterative(
        SimpleNamespace(params={}),start,rounds=2,max_trials=1)
    # Existing diagnostic history is attached to the incumbent; its geometry
    # and measured route evidence, rather than log fields, must be immutable.
    assert start.P==before['P'] and start.route_preflight==before['route_preflight']
    assert len(seen)==(2 if mode in ('second_wins','no_gain') else 1)
    assert len({coverage.signature(move) for move in seen})==len(seen)
    assert report['accepted_count']==int(mode=='second_wins')
    assert report['changed']==(mode=='second_wins')
    assert len(coverage.import_visits(report['probe_history']))==len(seen)
    if len(histories)==2:assert histories[0] is histories[1]
    if mode=='no_gain':assert report['stop_reason']=='proposal_budget_exhausted'
    if mode=='deadline':assert report['stop_reason']=='remaining_budget_preserves_incumbent'


def test_history_is_explicitly_resumable_without_cached_measurement(monkeypatch):
    import cec_operation_budget as budget
    visits={};coverage.record(rows()[0],visits)
    payload=coverage.export_visits(visits)
    cfg=SimpleNamespace(params={'placement_probe_history':{'priority':payload}})
    current=SimpleNamespace(route_preflight={'critical_pair_refused_count':1})
    def repair(cfg,initial,**kwargs):
        assert kwargs['probe_visits']==visits
        return initial,dict(accepted=False,reason='baseline_preflight_error')
    monkeypatch.setattr(synth,'repair_route_preflight',repair)
    monkeypatch.setattr(budget,'round_admission',lambda *a,**k:dict(start=True))
    _,report=synth.repair_route_preflight_iterative(cfg,current,rounds=1)
    assert report['probe_history']==payload and not report['changed']


def test_production_round_filters_before_fair_sampling_and_never_caches_admission():
    import inspect
    source=inspect.getsource(synth.repair_route_preflight)
    assert source.index('frozen_plan.filter_moves') < source.index('trial_moves = coverage.select')
    assert source.index('trial_moves = coverage.select') < source.index('for move_index, move in enumerate(trial_moves)')
    assert 'report[\'proposal_frontier\'] = coverage.frontier' in source


def test_pipeline_persists_and_copies_only_byte_bound_search_hints(tmp_path):
    import cec_full_pipeline as pipeline
    board=tmp_path/'original.kicad_pcb';board.write_text('unchanged board')
    visits,state,receipt=pipeline._placement_search_history(board,'priority')
    assert not visits and receipt['reason']=='missing'
    coverage.record(rows()[0],visits)
    report={'probe_history':coverage.export_visits(visits)}
    pipeline._save_placement_search_history(board,'priority',state,report)
    destination=tmp_path/'next'/'board.kicad_pcb'
    pipeline._copy_sidecars(board,destination)
    restored,new_state,receipt=pipeline._placement_search_history(destination,'priority')
    assert restored==visits and receipt['reason']=='matched'
    assert not receipt['cached_admission']
    assert board.read_text()==destination.read_text()=='unchanged board'
    destination.write_text('changed placement')
    restored,_,receipt=pipeline._placement_search_history(destination,'priority')
    assert not restored and receipt['reason']=='stale_or_invalid'


@pytest.mark.parametrize('payload', ['bad json', '[]', 'null', '{"schema":1,"scopes":[]}'])
def test_bad_optional_history_cannot_block_or_admit_a_board(tmp_path,payload):
    import cec_full_pipeline as pipeline
    board=tmp_path/'board.kicad_pcb';board.write_text('geometry')
    board.with_suffix('.placement-search.json').write_text(payload)
    visits,_,receipt=pipeline._placement_search_history(board,'craft')
    assert not visits and receipt['reason'] in ('unreadable_or_invalid','stale_or_invalid')
    assert not receipt['cached_admission'] and board.read_text()=='geometry'


def test_craft_stage_reloads_next_batch_not_the_same_first_batch(tmp_path,monkeypatch):
    import cec_full_pipeline as pipeline
    board=tmp_path/'board.kicad_pcb';board.write_text('geometry')
    cfg=SimpleNamespace(params={});candidate=object();seen=[]
    def repair(cfg,current,**kwargs):
        moves=coverage.select(rows(),1,visits=kwargs['probe_visits'],
                              selector=lambda proposals,n:proposals[:n])
        for move in moves:coverage.record(move,kwargs['probe_visits'])
        seen.extend(moves)
        return current,dict(changed=False,probe_history=coverage.export_visits(kwargs['probe_visits']))
    monkeypatch.setattr(synth,'repair_placement_craft_epochs',repair)
    for _ in range(2):pipeline._repair_craft_with_search_history(cfg,candidate,board)
    assert seen==rows()[:2] and board.read_text()=='geometry'


def test_priority_wrapper_reloads_ordering_without_mutating_recipe(tmp_path,monkeypatch):
    import cec_full_pipeline as pipeline
    board=tmp_path/'board.kicad_pcb';board.write_text('geometry')
    cfg=SimpleNamespace(params={'priority_route_process_isolation':True})
    original=copy.deepcopy(cfg.params);seen=[]
    def repair(operation,bound,target,**kwargs):
        data=bound.params['placement_probe_history'].get('priority')
        visits=coverage.import_visits(data) if data else {}
        selected=coverage.select(rows(),1,visits=visits,
                                  selector=lambda proposals,n:proposals[:n])
        for move in selected:coverage.record(move,visits)
        seen.extend(selected)
        return dict(ok=True,changed=False,probe_history=coverage.export_visits(visits))
    monkeypatch.setattr(pipeline,'_run_priority_placement_operation_isolated',repair)
    for _ in range(2):pipeline._repair_placement_priority_routes(cfg,board)
    assert seen==rows()[:2] and cfg.params==original


def test_changed_result_history_retains_old_geometry_key(tmp_path):
    import cec_full_pipeline as pipeline
    board=tmp_path/'board.kicad_pcb';board.write_text('before')
    visits,state,_=pipeline._placement_search_history(board,'craft')
    coverage.record(rows()[0],visits)
    board.write_text('after')
    pipeline._save_placement_search_history(board,'craft',state,
        {'probe_history':coverage.export_visits(visits)})
    restored,_,receipt=pipeline._placement_search_history(board,'craft')
    assert not restored and receipt['reason']=='stale_or_invalid'
