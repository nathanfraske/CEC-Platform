from pathlib import Path
from types import SimpleNamespace

import pytest
import cec_full_pipeline as pipeline
import cec_operation_budget as budget
import cec_placement_checkpoint as checkpoint
from test_placement_checkpoint import fixture, publish


def attempt():
    return pipeline._priority_cooptimization_attempt(
        SimpleNamespace(params={}),SimpleNamespace(params={}),Path('private.kicad_pcb'),
        completion_report={},baseline_evidence={'measured':True},
        allow_authored_prefix=True,allow_unbound_power_authority=False)


@pytest.mark.parametrize('phase', ['repair','power'])
@pytest.mark.parametrize('status', ['operation_budget_exhausted','worker_failed'])
def test_only_budget_exhaustion_is_a_bounded_stop(monkeypatch,phase,status):
    evidence=dict(operation=phase,status=status,directory='/owned/operation',
                  last_progress={'phase':'native-proof'})
    def fail(*a,**k):raise budget.OperationFailure(evidence)
    monkeypatch.setattr(pipeline,'_repair_placement_priority_routes',fail if phase=='repair'
        else lambda *a,**k:dict(ok=True,changed=False,result_evidence={}))
    monkeypatch.setattr(pipeline,'_placement_priority_route_gate',lambda *a,**k:dict(ok=False))
    monkeypatch.setattr(pipeline,'_repair_placement_priority_routes_with_power_replan',fail)
    if status!='operation_budget_exhausted':
        with pytest.raises(budget.OperationFailure):attempt()
    else:
        result=attempt()
        assert not result['ok'] and not result['changed'] and not result['release_authority']
        assert result['operation_evidence']==evidence
        assert result['reason']=='cooptimization_operation_budget_exhausted'


@pytest.mark.parametrize('changed,admitted', [(True,False),(False,True)])
def test_no_replan_after_changed_or_already_admitted_repair(monkeypatch,changed,admitted):
    original=dict(ok=True,changed=changed,result_evidence={'specific':'result'})
    monkeypatch.setattr(pipeline,'_repair_placement_priority_routes',lambda *a,**k:original)
    monkeypatch.setattr(pipeline,'_placement_priority_route_gate',lambda *a,**k:dict(ok=admitted))
    monkeypatch.setattr(pipeline,'_repair_placement_priority_routes_with_power_replan',
        lambda *a,**k:pytest.fail('unneeded replan'))
    assert attempt() is original


def test_integrity_exception_is_never_reported_as_budget_stop(monkeypatch):
    def fail(*a,**k):raise RuntimeError('input family changed')
    monkeypatch.setattr(pipeline,'_repair_placement_priority_routes',fail)
    with pytest.raises(RuntimeError,match='input family changed'):attempt()


def test_complete_round_cost_reserves_finalization(monkeypatch):
    monkeypatch.setattr(budget.time,'time',lambda:1000.)
    # A 400 s complete round does not fit in 300 s, even though an individual
    # 120 s repair might. No solver limits or acceptance keys are relaxed.
    env={'CEC_JOB_DEADLINE_EPOCH':'1300'}
    assert budget.round_admission(None,reserve_s=120,env=env)['start']
    check=budget.round_admission(400,reserve_s=120,env=env)
    assert not check['start'] and check['required_s']==pytest.approx(560)
    assert budget.round_admission(400,reserve_s=120,env={})['start']


def test_priority_checkpoint_survives_later_native_abort_and_rejects_earlier_phase(tmp_path,monkeypatch):
    store,board,_=fixture(tmp_path)
    seed=publish(store,board,rank=10)
    board.write_text('complete physically measured priority incumbent')
    retained=publish(store,board,rank=9,phase='priority',observation={
        'physical_ok':True,'route_authority_ok':True,'priority_gate':{'ok':False}})
    assert retained['published'] and retained['sha256']!=seed['sha256']
    original=checkpoint.atomic_json
    def fail_pointer(path,data):
        if path.name=='current.json':raise OSError('later round aborted before pointer commit')
        return original(path,data)
    monkeypatch.setattr(checkpoint,'atomic_json',fail_pointer)
    board.write_text('uncommitted later proposal')
    with pytest.raises(OSError):publish(store,board,rank=8,phase='priority')
    current=checkpoint.read_current(store.root)
    assert current['sha256']==retained['sha256'] and current['phase']=='priority'
    assert not current['routing_admitted'] and not current['release_accepted']
    assert not publish(store,board,rank=1,phase='placement')['published']


def test_review_preserves_priority_checkpoint_identity_without_journal_claim(tmp_path):
    import cec_pass_review
    store,board,_=fixture(tmp_path)
    # Match the generic review store location; this contains no accepted board.
    store=checkpoint.Store(tmp_path/'attempt/02-placement/checkpoints',family=store.family,
        sources=[tmp_path/'source.kicad_sch'])
    saved=publish(store,board,rank=9,phase='priority')
    target,stage,verified=cec_pass_review.select_output(tmp_path/'attempt',
        {'board':store.family,'stages':{'placement':{'status':'failed'}}})
    assert target==Path(saved['board']) and stage=='placement-checkpoint:priority'
    assert not verified
