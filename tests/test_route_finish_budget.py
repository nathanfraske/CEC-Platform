"""A repair or queued seed cannot consume a completed candidate's finish time."""
from concurrent.futures import Future
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import cec_operation_budget as budget
import cec_full_pipeline as pipeline
import cec_synth_pipeline as synth
import cec_process_pool


@pytest.mark.parametrize('remaining,expected',[(390,True),(389.999,False),(0,False),(-1,False)])
def test_full_optional_allowance_plus_finish_must_fit(monkeypatch,remaining,expected):
    monkeypatch.setattr(budget.time,'time',lambda:100.)
    plan=budget.optional_work_admission(270,reserve_s=120,
        env={'CEC_JOB_DEADLINE_EPOCH':str(100+remaining)})
    assert plan['start'] is expected and plan['release_authority'] is False
    assert budget.optional_work_admission(270,env={})['start']


@pytest.mark.parametrize('value',[-1,float('nan'),float('inf')])
def test_invalid_allowance_is_not_an_unlimited_lease(value):
    with pytest.raises(ValueError):budget.optional_work_admission(value,env={})


def test_tightest_nested_deadline_and_outer_reserve_win(monkeypatch):
    monkeypatch.setattr(budget.time,'time',lambda:100.)
    assert not budget.optional_work_admission(270,reserve_s=120,
        env={'CEC_JOB_DEADLINE_EPOCH':'1000','CEC_OPERATION_DEADLINE_EPOCH':'300'})['start']


@pytest.mark.parametrize('remaining,called',[(194,False),(500,True)])
def test_production_certificate_hook_preserves_input_and_finalist_time(tmp_path,monkeypatch,remaining,called):
    monkeypatch.setenv('CEC_JOB_DEADLINE_EPOCH',str(100+remaining))
    monkeypatch.delenv('CEC_OPERATION_DEADLINE_EPOCH',raising=False)
    monkeypatch.setattr(budget.time,'time',lambda:100.)
    source=tmp_path/'input.kicad_pcb';source.write_text('immutable source')
    completion={'lastmile':{'refused_details':[{'net':'arbitrary'}]}}
    calls=[]
    def run(command,**kwargs):
        calls.append((command,kwargs))
        Path(command[command.index('--report')+1]).write_text(json.dumps({'changed':False}))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(synth.subprocess,'run',run)
    target,report=synth._route_oracle_certificate_repair(str(source),completion,str(tmp_path),timeout_s=900)
    assert bool(calls) is called and target==str(source) and source.read_text()=='immutable source'
    if called:
        assert calls[0][1]['timeout']==380
        command=calls[0][0]
        assert float(command[command.index('--wall-budget-s')+1])==240
    else:
        assert report['skipped']=='campaign_finish_reserve'
        assert not (tmp_path/'certificate-completion.json').exists()


@pytest.mark.parametrize('workers',[1,2])
def test_route_dispatch_funds_cohorts_not_a_blind_queue(monkeypatch,workers):
    clock={'now':100.}
    monkeypatch.setattr(budget.time,'time',lambda:clock['now'])
    monkeypatch.setattr(pipeline.time,'monotonic',lambda:clock['now'])
    monkeypatch.setenv('CEC_JOB_DEADLINE_EPOCH','300')
    monkeypatch.delenv('CEC_OPERATION_DEADLINE_EPOCH',raising=False)
    submitted=[]
    class Pool:
        def submit(self,fn,payload):
            submitted.append(payload['seed']);future=Future()
            future.set_result({'seed':payload['seed'],'routed':'already-qualified','gate':False})
            return future
    def watch(pool,futures,**kwargs):
        assert kwargs['wall_timeout_s']==80
        clock['now']+=70
        yield from futures
    monkeypatch.setattr(cec_process_pool,'watched_as_completed',watch)
    rows=[];evidence={};active={}
    pipeline._route_candidate_cohorts(Pool(),[{'seed':i} for i in range(6)],workers,
        watchdog_s=7200,reserve_s=120,results=rows,evidence=evidence,active=active)
    assert submitted==list(range(workers))
    assert [r['seed'] for r in rows]==submitted
    assert evidence['status']=='budget_deferred'
    assert evidence['deferred_seeds']==list(range(workers,6))
    assert clock['now']==170


def test_expired_route_budget_dispatches_nothing(monkeypatch):
    monkeypatch.setenv('CEC_JOB_DEADLINE_EPOCH','1')
    class Pool:
        def submit(self,*args):raise AssertionError('launched after campaign deadline')
    rows=[];evidence={}
    pipeline._route_candidate_cohorts(Pool(),[{'seed':7}],1,watchdog_s=7200,
        reserve_s=120,results=rows,evidence=evidence,active={})
    assert not rows and evidence['deferred_seeds']==[7]


def test_without_deadline_all_seeds_run_and_worker_failure_is_not_success(monkeypatch):
    monkeypatch.delenv('CEC_JOB_DEADLINE_EPOCH',raising=False)
    monkeypatch.delenv('CEC_OPERATION_DEADLINE_EPOCH',raising=False)
    class Pool:
        def submit(self,fn,payload):
            future=Future()
            if payload['seed']==3:future.set_exception(RuntimeError('native failure'))
            else:future.set_result({'seed':payload['seed'],'gate':False,'routed':'kept'})
            return future
    monkeypatch.setattr(cec_process_pool,'watched_as_completed',lambda p,f,**kw:iter(f))
    rows=[];evidence={}
    pipeline._route_candidate_cohorts(Pool(),[{'seed':i} for i in range(5)],2,
        watchdog_s=7200,reserve_s=120,results=rows,evidence=evidence,active={})
    assert [r['seed'] for r in rows]==list(range(5))
    assert rows[3]['routed'] is None and rows[3]['gate'] is False
    assert 'RuntimeError' in rows[3]['worker_error']
    assert len(evidence['cohorts'])==3


def test_generation_watchdog_is_not_renewed_without_outer_deadline(monkeypatch):
    monkeypatch.delenv('CEC_JOB_DEADLINE_EPOCH',raising=False)
    monkeypatch.delenv('CEC_OPERATION_DEADLINE_EPOCH',raising=False)
    clock={'now':0.};monkeypatch.setattr(pipeline.time,'monotonic',lambda:clock['now'])
    class Pool:
        def submit(self,fn,payload):
            f=Future();f.set_result({'seed':payload['seed'],'gate':False});return f
    timeouts=[]
    def watch(pool,futures,**kwargs):
        timeouts.append(kwargs['wall_timeout_s']);clock['now']+=6
        yield from futures
    monkeypatch.setattr(cec_process_pool,'watched_as_completed',watch)
    rows=[];evidence={}
    pipeline._route_candidate_cohorts(Pool(),[{'seed':i} for i in range(3)],1,
        watchdog_s=10,reserve_s=0,results=rows,evidence=evidence,active={})
    assert timeouts==[10,4] and [r['seed'] for r in rows]==[0,1]
    assert evidence['deferred_seeds']==[2]
    assert evidence['next_cohort_budget']['reason']=='generation_watchdog_exhausted'
