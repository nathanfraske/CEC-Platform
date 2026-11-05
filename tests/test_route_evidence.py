import copy
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest
import cec_route_evidence as proofs
import cec_operation_budget as budget


def test_round_admission_reserves_return_time_and_binds_nearest_deadline():
    with mock.patch.object(budget.time, 'time', return_value=100.):
        assert budget.round_admission(543., env={})['start']
        result=budget.round_admission(543., env={
            'CEC_OPERATION_DEADLINE_EPOCH':'155', 'CEC_JOB_DEADLINE_EPOCH':'1000'})
        assert not result['start']
        assert result['remaining_s']==55.
        assert result['required_s']>600.
        assert not budget.round_admission(env={'CEC_OPERATION_DEADLINE_EPOCH':'120'})['start']
        with pytest.raises(ValueError): budget.round_admission(float('nan'), env={})


def test_completed_round_is_returned_before_unaffordable_next_round(tmp_path,monkeypatch):
    import cec_synth_pipeline as synth
    path=tmp_path/'progress.json'
    monkeypatch.setenv('CEC_OPERATION_PROGRESS',str(path))
    monkeypatch.setenv('CEC_OPERATION_OWNER_PID',str(os.getpid()))
    monkeypatch.setenv('CEC_OPERATION_DEADLINE_EPOCH','700')
    monkeypatch.delenv('CEC_JOB_DEADLINE_EPOCH',raising=False)
    start=SimpleNamespace(route_preflight={'critical_pair_refused_count':3},P={})
    improved=SimpleNamespace(route_preflight={'critical_pair_refused_count':2},P={'X1':(1,2,90)})
    now=[100.]
    def repair(*args,**kwargs):
        now[0]=645.
        return improved,{'accepted':True,'move':{'kind':'synthetic'}}
    with mock.patch.object(budget.time,'time',side_effect=lambda:now[0]), \
         mock.patch.object(synth.time,'monotonic',side_effect=[0.,543.]), \
         mock.patch.object(synth,'repair_route_preflight',side_effect=repair) as evaluate:
        current,report=synth.repair_route_preflight_iterative(SimpleNamespace(),start,rounds=2)
    assert current is improved
    assert evaluate.call_count==1
    assert report['accepted_count']==1
    assert report['changed']
    assert report['stop_reason']=='remaining_budget_preserves_incumbent'
    saved=json.loads((tmp_path/'checkpoint.json').read_text())
    assert saved['promotion_allowed'] is False
    assert saved['round']==1 and saved['placements']=={'X1':[1,2,90]}
    assert saved['route_evidence']['critical_pair_refused_count']==2


def test_nonmonotonic_round_is_not_checkpointed_as_improved():
    import cec_synth_pipeline as synth
    start=SimpleNamespace(route_preflight={'critical_pair_refused_count':2})
    wrong=SimpleNamespace(route_preflight={'critical_pair_refused_count':3})
    with mock.patch.object(synth,'repair_route_preflight',return_value=(wrong,{'accepted':True})), \
         mock.patch.object(budget,'checkpoint') as checkpoint:
        current,report=synth.repair_route_preflight_iterative(SimpleNamespace(),start,rounds=1)
    assert current is start and report['accepted_count']==0
    assert report['stop_reason']=='non_monotonic_result_key'
    checkpoint.assert_not_called()


@pytest.fixture
def case(tmp_path):
    board=tmp_path/'board.kicad_pcb';board.write_text('embedded placement and copper')
    root=tmp_path/'root.kicad_sch';root.write_text('(kicad_sch)')
    cfg=SimpleNamespace(board='synthetic', board_key='synthetic', profile='consumer',
        pins={},dir=str(tmp_path),sch=str(root),net=None,pcb=str(board),bom_csv='',
        params={'placement_route_repair_trials':1,'placement_route_repair_rounds':1})
    return board,cfg


def authority(case):
    board,cfg=case
    return proofs.baseline_context(cfg,board,allow_authored_prefix=True)


def test_completed_refusal_is_reusable_without_becoming_admission(case):
    ctx=authority(case)
    evidence=proofs.seal({'critical_route_refused_count':3,'gate':False},ctx)
    assert proofs.verify(evidence,ctx)['used']
    assert proofs.clean(evidence)['gate'] is False
    for incomplete in ({}, {'error':'native worker failed'}):
        assert proofs.ENVELOPE not in proofs.seal(incomplete,ctx)


def test_search_ordering_receipt_does_not_self_invalidate_geometry_evidence(case):
    board,cfg=case
    before=authority(case)
    certificate=proofs.seal({'gate':False,'critical_route_refused_count':2},before)
    board.with_suffix('.placement-search.json').write_text('{"ordering":"only"}')
    cfg.params['placement_probe_history']={'priority':{'opaque':'work accounting'}}
    assert proofs.verify(certificate,authority(case))['used']
    board.write_text('different actual geometry')
    assert not proofs.verify(certificate,authority(case))['used']


@pytest.mark.parametrize('suffix', ['.kicad_pcb','.kicad_pro','.kicad_dru',
    '.cellreport.json','.authored-prefix.json','.pourplan.json'])
def test_changed_or_new_artifact_dependency_refuses_reuse(case,suffix):
    board,_=case
    evidence=proofs.seal({'gate':False},authority(case))
    board.with_suffix(suffix).write_text('new content')
    result=proofs.verify(evidence,authority(case))
    assert not result['used']
    assert 'artifact' in result['changed_sections']


def test_changed_nested_sheet_invalidates_proof(case):
    board,cfg=case
    nested=board.parent/'nested';nested.mkdir()
    child=nested/'child.kicad_sch';child.write_text('(kicad_sch)')
    Path(cfg.sch).write_text('(kicad_sch (sheet (property "Sheetfile" "nested/child.kicad_sch")))')
    evidence=proofs.seal({'gate':False},authority(case))
    child.write_text('(kicad_sch (junction))')
    assert 'sources' in proofs.verify(evidence,authority(case))['changed_sections']
    child.unlink()
    with pytest.raises(FileNotFoundError): authority(case)


def test_evidence_tampering_and_missing_certificate_fail_closed(case):
    ctx=authority(case)
    evidence=proofs.seal({'critical_route_refused_count':2},ctx)
    evidence['critical_route_refused_count']=0
    assert proofs.verify(evidence,ctx)['reason']=='evidence_changed_or_failed'
    assert not proofs.verify({'critical_route_refused_count':0},ctx)['used']
    evidence[proofs.ENVELOPE]['complete']=False
    assert not proofs.verify(evidence,ctx)['used']
    assert not proofs.verify({'baseline_certificate':[]},ctx)['used']
    assert not proofs.verify([],ctx)['used']


def test_identical_board_cannot_borrow_other_source_identity(case):
    board,cfg=case
    evidence=proofs.seal({'gate':False},authority(case))
    cfg.board='another-synthetic-family'
    assert not proofs.verify(evidence,authority(case))['used']


def test_policy_environment_engine_and_explicit_net_selection_are_bound(case,monkeypatch,tmp_path):
    board,cfg=case
    before=authority(case)
    cfg.params['placement_route_pair_timeout_s']=30
    assert authority(case)['sections']['policy']!=before['sections']['policy']
    cfg.params.pop('placement_route_pair_timeout_s')
    cfg.params['placement_route_excluded_move_signatures']=['already tried']
    assert authority(case)==before
    monkeypatch.setenv('CEC_OPERATION_DEADLINE_EPOCH','123')
    monkeypatch.setenv('CEC_OPERATION_OWNER_PID','123')
    assert authority(case)==before
    monkeypatch.setenv('CEC_PRECISION_PAIR_TIMEOUT','17')
    assert authority(case)['sections']['environment']!=before['sections']['environment']
    net=board.parent/'stale.net';net.write_text('stale selection')
    cfg.net=str(net)
    assert authority(case)['sections']['policy']!=before['sections']['policy']
    engine=tmp_path/'engine';(engine/'scripts').mkdir(parents=True)
    source=engine/'scripts'/'solve.py';source.write_text('before')
    monkeypatch.setattr(proofs,'ROOT',engine)
    ctx=proofs.context(board,{})
    source.write_text('after')
    assert proofs.context(board,{})['sections']['engine']!=ctx['sections']['engine']


def test_memory_cache_binds_project_rules_and_solver_environment(case,monkeypatch):
    import cec_synth_pipeline as synth
    board,_=case
    args=dict(grid_mm=1.,iters=4,backend='cpu',multiresolution=True,critical_selectors=('BUS*',))
    original=synth._route_authority_digest(board,**args)
    board.with_suffix('.kicad_dru').write_text('(rules changed)')
    assert synth._route_authority_digest(board,**args)!=original
    changed=synth._route_authority_digest(board,**args)
    monkeypatch.setenv('CEC_PRECISION_PAIR_TIMEOUT','19')
    assert synth._route_authority_digest(board,**args)!=changed
    synth._ROUTE_AUTHORITY_CACHE.clear()
    synth._route_authority_cache_put('failed',{'error':'timeout'})
    assert 'failed' not in synth._ROUTE_AUTHORITY_CACHE


@pytest.mark.parametrize('valid', [True,False])
def test_repair_boundary_seeds_only_verified_baseline(case,valid):
    import cec_full_pipeline as pipeline
    import cec_synth_pipeline as synth
    board,cfg=case
    evidence=proofs.seal({'critical_route_refused_count':2},authority(case))
    if not valid: board.with_suffix('.kicad_dru').write_text('changed')
    candidate=SimpleNamespace(route_preflight={})
    loaded=mock.Mock();loaded.GetTracks.return_value=[]
    def repair(_cfg,received,**kwargs):
        assert bool(received.route_preflight) is valid
        return received,{'changed':False}
    bound=copy.copy(cfg);bound.params=dict(cfg.params)
    with mock.patch('pcbnew.LoadBoard',return_value=loaded), \
         mock.patch.object(synth,'config_with_board_route_authority',return_value=(bound,{'ok':True,'bound':False})), \
         mock.patch.object(synth,'placement_candidate_from_board',return_value=candidate), \
         mock.patch.object(synth,'repair_route_preflight_iterative',side_effect=repair):
        result=pipeline._repair_placement_priority_routes_in_process(
            cfg,board,allow_authored_prefix=True,baseline_evidence=evidence)
    assert result['baseline_reuse']['used'] is valid


def test_isolated_copy_receipt_preserves_explicit_config_and_rechecks_contents(case):
    import cec_full_pipeline as pipeline
    board,cfg=case
    cfg.pins={'datum':'mechanical'}
    evidence=proofs.seal({'critical_route_refused_count':2},authority(case))
    def worker(command,directory,**kwargs):
        config=json.loads(Path(command[command.index('--config-file')+1]).read_text())
        assert config['net'] is None
        assert config['pins']==cfg.pins
        received=json.loads(Path(command[command.index('--baseline-file')+1]).read_text())
        target=Path(command[3])
        assert proofs.verify(received,proofs.baseline_context(cfg,target,allow_authored_prefix=True))['used']
        target.with_suffix('.kicad_dru').write_text('changed after dispatch')
        assert not proofs.verify(received,proofs.baseline_context(cfg,target,allow_authored_prefix=True))['used']
        (Path(directory)/'report.json').write_text(json.dumps({'ok':True,'changed':False}))
        return {'status':'complete'}
    with mock.patch.object(budget,'run',side_effect=worker):
        result=pipeline._run_priority_placement_operation_isolated(
            'priority-repair',cfg,board,baseline_evidence=evidence,allow_authored_prefix=True)
    assert result['baseline_transfer']['used']
    assert not board.with_suffix('.kicad_dru').exists()


def test_probe_budget_reserves_finalist_time_and_accounts_for_batches():
    with mock.patch.object(budget.time,'time',return_value=100):
        row=budget.probe_allocation(120,16,8,2,env={'CEC_OPERATION_DEADLINE_EPOCH':'400'})
        assert row['per_pair_timeout_s'] is None
        assert row['batches']==0
        assert row['admitted_jobs']==0 and row['deferred_jobs']==16
        assert row['allocated_s']==120
        assert budget.probe_allocation(120,16,8,2,env={})['per_pair_timeout_s']==120
        row=budget.probe_allocation(120,16,8,2,env={'CEC_OPERATION_DEADLINE_EPOCH':'140'})
        assert row['per_pair_timeout_s'] is None


def test_probe_budget_funds_fewer_trials_without_slicing_their_effort():
    with mock.patch.object(budget.time,'time',return_value=100):
        row=budget.probe_allocation(120,12,2,1,env={'CEC_JOB_DEADLINE_EPOCH':'512.7'})
    assert row['per_pair_timeout_s']==120
    assert row['admitted_jobs']==2 and row['deferred_jobs']==10
    assert row['batches']==1 and row['estimated_batch_s']==125
    assert row['estimated_batch_s']*row['batches'] <= row['allocated_s']


def test_complete_probe_batch_can_borrow_idle_fraction_without_using_finalist_reserve():
    with mock.patch.object(budget.time, 'time', return_value=100):
        row = budget.probe_allocation(120, 13, 2, 2,
            env={'CEC_OPERATION_DEADLINE_EPOCH': '572.678648'})
    assert row['minimum_batch_funded'] is True
    assert row['fractional_allocation_s'] == pytest.approx(206.339324)
    assert row['allocated_s'] == 245
    assert row['per_pair_timeout_s'] == 120
    assert row['admitted_jobs'] == 2 and row['deferred_jobs'] == 11
    assert row['allocated_s'] + row['reserve_s'] <= row['remaining_s']


@pytest.mark.parametrize('remaining,admitted', [(304.999,0),(305,2),(306,2)])
def test_minimum_probe_cohort_respects_exact_hard_reserve_boundary(remaining, admitted):
    with mock.patch.object(budget.time, 'time', return_value=100):
        row = budget.probe_allocation(120, 13, 2, 2,
            env={'CEC_JOB_DEADLINE_EPOCH': str(100+remaining)}, fraction=.01)
    assert row['admitted_jobs'] == admitted
    assert row['batches'] * row['estimated_batch_s'] <= max(0, remaining-60)


def test_empty_probe_queue_never_borrows_a_batch():
    with mock.patch.object(budget.time, 'time', return_value=100):
        row = budget.probe_allocation(120, 0, 2, 2,
            env={'CEC_JOB_DEADLINE_EPOCH': '1000'}, fraction=.01)
    assert row['admitted_jobs'] == 0
    assert row['minimum_batch_funded'] is False


@pytest.mark.parametrize('jobs,workers,pairs', [(0,2,1),(1,1,1),(17,3,2),(2,8,1)])
def test_probe_batch_plan_stays_within_fixed_budget(jobs,workers,pairs):
    with mock.patch.object(budget.time,'time',return_value=100):
        row=budget.probe_allocation(40,jobs,workers,pairs,
            env={'CEC_JOB_DEADLINE_EPOCH':'460'},fraction=.75)
    assert row['admitted_jobs'] + row['deferred_jobs']==jobs
    assert row['estimated_batch_s']*row['batches'] <= row['allocated_s']
    assert row['per_pair_timeout_s'] in (None,40)


@pytest.mark.parametrize('jobs,workers,pairs', [(1.5,2,1),(2,1.5,1),(2,2,1.5),
                                             (True,2,1)])
def test_fractional_or_boolean_probe_counts_are_not_silently_truncated(jobs,workers,pairs):
    with pytest.raises(ValueError):
        budget.probe_allocation(120,jobs,workers,pairs,env={})


def test_dependency_edit_during_worker_prevents_promotion(case):
    import cec_full_pipeline as pipeline
    board,cfg=case
    original=board.read_bytes()
    evidence=proofs.seal({'gate':False},authority(case))
    def worker(command,directory,**kwargs):
        Path(command[3]).write_text('candidate copper')
        Path(cfg.sch).write_text('(kicad_sch (junction))')
        (Path(directory)/'report.json').write_text(json.dumps({'ok':True,'changed':True}))
        return {'status':'complete'}
    with mock.patch.object(budget,'run',side_effect=worker):
        with pytest.raises(RuntimeError,match='dependencies changed'):
            pipeline._run_priority_placement_operation_isolated(
                'priority-repair',cfg,board,baseline_evidence=evidence,allow_authored_prefix=True)
    assert board.read_bytes()==original
