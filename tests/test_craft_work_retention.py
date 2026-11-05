from concurrent.futures import Future
from pathlib import Path
from types import SimpleNamespace

import pytest

import cec_operation_budget as budget
import cec_synth_pipeline as synth


def test_cohort_budget_preserves_finish_reserve_and_uses_tightest_deadline(monkeypatch):
    monkeypatch.setattr(budget.time,'time',lambda:100.)
    plan=budget.generation_admission(900,30,reserve_s=20,
          env={'CEC_JOB_DEADLINE_EPOCH':'200','CEC_OPERATION_DEADLINE_EPOCH':'160'})
    assert plan['start'] and plan['timeout_s']==40
    assert not budget.generation_admission(900,40,reserve_s=20,
          env={'CEC_JOB_DEADLINE_EPOCH':'160'})['start']
    assert budget.generation_admission(900,40,reserve_s=20,env={})['timeout_s']==900


@pytest.mark.parametrize('value',[0,-1,float('inf'),float('nan')])
def test_invalid_generation_limit_refused(value):
    with pytest.raises(ValueError): budget.generation_admission(value,env={})


@pytest.mark.parametrize('deferred_stage',range(4))
def test_deferred_lookahead_is_not_misreported_as_an_exhaustive_plateau(deferred_stage):
    reports=[{'budget_exhausted':False} for _ in range(4)]
    assert not budget.evaluations_exhausted(*reports,{},None)
    reports[deferred_stage]['budget_exhausted']=True
    assert budget.evaluations_exhausted(*reports)


class FakePool:
    def __init__(self,**kwargs): pass
    def submit(self,fn,job):
        future=Future(); future.set_result(fn(job)); return future
    def shutdown(self,**kwargs): pass


@pytest.mark.parametrize('workers',[1,2])
def test_batch_returns_ordered_completed_prefix_before_deadline(monkeypatch,workers):
    clock={'t':100.}
    monkeypatch.setattr(budget.time,'time',lambda:clock['t'])
    monkeypatch.setattr(synth.time,'monotonic',lambda:clock['t'])
    monkeypatch.setenv('CEC_JOB_DEADLINE_EPOCH','145')
    monkeypatch.delenv('CEC_OPERATION_DEADLINE_EPOCH',raising=False)
    monkeypatch.setattr(synth,'ProcessPoolExecutor',FakePool)
    monkeypatch.setattr(synth,'_placement_craft_memory_budget',lambda cfg:{'worker_limit':4})
    def worker(job):
        clock['t']+=5
        return {'ok':True,'evidence':job['n'],'timing':{'total_s':5}}
    monkeypatch.setattr(synth,'_placement_craft_trial_worker',worker)
    cfg=SimpleNamespace(params={'placement_craft_eval_workers':workers,
                               'placement_craft_finish_reserve_s':20})
    results,runtime=synth._evaluate_placement_craft_trials(cfg,[{'n':i} for i in range(10)])
    assert [r['evidence'] for r in results]==list(range(4))
    assert runtime['isolated'] and runtime['budget_exhausted']
    assert runtime['unevaluated_jobs']==6 and runtime['timed_out_jobs']==0
    assert clock['t']==120
    assert all(row['budget']['timeout_s']<=25 for row in runtime['cohorts'])


def test_expired_deadline_does_not_launch_even_one_worker(monkeypatch):
    monkeypatch.setenv('CEC_JOB_DEADLINE_EPOCH','1')
    def forbidden(*args,**kwargs): raise AssertionError('worker launched after budget')
    monkeypatch.setattr(synth,'ProcessPoolExecutor',forbidden)
    results,runtime=synth._evaluate_placement_craft_trials(SimpleNamespace(params={}),[{}])
    assert results==[] and runtime['budget_exhausted'] and runtime['unevaluated_jobs']==1


def test_deadline_timeout_rejects_unproved_job_and_retains_completed_peer(monkeypatch):
    monkeypatch.setenv('CEC_JOB_DEADLINE_EPOCH','130')
    monkeypatch.delenv('CEC_OPERATION_DEADLINE_EPOCH',raising=False)
    monkeypatch.setattr(budget.time,'time',lambda:100.)
    monkeypatch.setattr(synth,'_placement_craft_memory_budget',lambda cfg:{'worker_limit':4})
    completed=Future(); completed.set_result({'ok':True,'evidence':{'score':1}})
    pending=Future()
    submitted=[]
    class Pool(FakePool):
        def submit(self,fn,job):
            submitted.append(job)
            return completed if len(submitted)==1 else pending
    monkeypatch.setattr(synth,'ProcessPoolExecutor',Pool)
    waits=[]
    def wait(futures,timeout):
        waits.append(timeout)
        return {completed},{pending}
    monkeypatch.setattr(synth,'wait',wait)
    cfg=SimpleNamespace(params={'placement_craft_eval_workers':2,
                               'placement_craft_finish_reserve_s':20})
    results,runtime=synth._evaluate_placement_craft_trials(cfg,[{}, {}, {}, {}])
    assert waits==[10] and len(submitted)==2
    assert results[0]['ok'] and results[1]['ok'] is False and results[1]['timed_out']
    assert runtime['budget_exhausted'] and runtime['timed_out_indices']==[1]
    assert runtime['unevaluated_jobs']==2


def test_serial_fixture_path_honors_clean_callback(monkeypatch):
    monkeypatch.delenv('CEC_JOB_DEADLINE_EPOCH',raising=False)
    monkeypatch.delenv('CEC_OPERATION_DEADLINE_EPOCH',raising=False)
    monkeypatch.setattr(synth,'_placement_craft_trial_worker',lambda job:{'ok':True})
    results,runtime=synth._evaluate_placement_craft_trials(
        SimpleNamespace(params={'placement_craft_eval_workers':1}),[{},{}],
        stop_after_generation=lambda *args:True)
    assert len(results)==1 and runtime['early_stopped'] and runtime['unevaluated_jobs']==1


@pytest.mark.parametrize('fault',[None,'key_drift','overlap','materialize'])
def test_only_revalidated_winner_reaches_checkpoint(monkeypatch,fault,tmp_path):
    cfg=SimpleNamespace(params={'placement_craft_failure_dir':str(tmp_path/'failures')})
    candidate=SimpleNamespace(P={'component':(10,10,0)},back_refs=())
    def materialize(candidate,cfg,path):
        if fault=='materialize': raise RuntimeError('native refused')
        Path(path).write_text('native tested artifact')
    monkeypatch.setattr(synth,'materialize',materialize)
    monkeypatch.setattr(synth,'placement_craft_key',lambda e:(e['score'],))
    monkeypatch.setattr(synth,'placement_craft_repair_key',lambda e,n:(n,e['score']))
    monkeypatch.setattr(synth,'placement_craft_evidence',
                        lambda *a,**k:{'score':2 if fault=='key_drift' else 1})
    monkeypatch.setattr(synth,'_extend_footprint_map_from_board',lambda *a,**k:{})
    monkeypatch.setattr(synth,'_overlap_pairs',lambda *a,**k:{('A','B')} if fault=='overlap' else set())
    saved=[]
    def checkpoint(candidate,cfg,path,**kwargs):
        saved.append((Path(path).read_text(),kwargs))
    if fault:
        with pytest.raises(RuntimeError):
            synth._certify_craft_incumbent(cfg,candidate,{'score':1},0,{},checkpoint=checkpoint)
        assert saved==[]
        if fault in ('key_drift','overlap'):
            import json
            report=json.loads((tmp_path/'failures/failure-00/manifest.json').read_text())
            assert report['complete'] and report['promotion_allowed'] is False
            assert any(row['role']=='board' for row in report['files'])
    else:
        evidence,overlap=synth._certify_craft_incumbent(
            cfg,candidate,{'score':1},0,{},checkpoint=checkpoint)
        assert saved[0][0]=='native tested artifact'
        assert saved[0][1]['phase']=='craft' and saved[0][1]['rank']==(0,1)
        assert evidence=={'score':1} and overlap==0


def test_checkpoint_callback_stays_outside_worker_config_and_epochs_do_not_restart_exhaustion(monkeypatch):
    cfg=SimpleNamespace(params={}); candidate=object(); callback=object(); calls=[]
    def repair(cfg,candidate,**kwargs):
        calls.append(kwargs)
        return candidate,{'result_key':[0,1],'ok':False,'changed':True,
            'accepted_count':1,'rounds':[], 'stop_reason':'evaluation_budget_exhausted'}
    monkeypatch.setattr(synth,'repair_placement_craft',repair)
    _,result=synth.repair_placement_craft_epochs(cfg,candidate,epochs=4,checkpoint=callback)
    assert len(calls)==1 and calls[0]['checkpoint'] is callback
    assert cfg.params=={} and result['stop_reason']=='evaluation_budget_exhausted'
