import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import cec_operation_budget as budget
import cec_board_suite as suite


def test_child_budget_is_clamped_to_campaign_deadline():
    with patch.object(budget.time, 'time', return_value=100):
        assert budget.available_timeout(600, {'CEC_JOB_DEADLINE_EPOCH':'180'}) == 65
        assert budget.available_timeout(20, {'CEC_JOB_DEADLINE_EPOCH':'180'}) == 20
        assert budget.available_timeout(600, {'CEC_JOB_DEADLINE_EPOCH':'110'}) == 0
        assert budget.available_timeout(600, {}) == 600


@pytest.mark.parametrize('parent,job,expected', [(180,900,65), (900,180,65),
                                               (110,900,0), (180,180,65)])
def test_nested_worker_cannot_renew_parent_lease(parent,job,expected):
    with patch.object(budget.time,'time',return_value=100):
        assert budget.available_timeout(1800, {
            'CEC_OPERATION_DEADLINE_EPOCH':str(parent),
            'CEC_JOB_DEADLINE_EPOCH':str(job)}) == expected
        assert budget.available_timeout(1800, {
            'CEC_OPERATION_DEADLINE_EPOCH':'180'}) == 65


@pytest.mark.parametrize('value', [float('nan'),float('inf'),-1])
def test_invalid_nested_deadline_or_reserve_fails_closed(value):
    with pytest.raises(ValueError):
        budget.available_timeout(20,{},reserve_s=value)
    if value != -1:
        with pytest.raises(ValueError):
            budget.available_timeout(20,{'CEC_OPERATION_DEADLINE_EPOCH':str(value)})


def test_expired_parent_does_not_launch_child_even_with_funded_campaign(tmp_path):
    with patch.object(budget.subprocess,'Popen') as launch:
        with pytest.raises(budget.OperationFailure):
            budget.run(['unused'],tmp_path,operation='nested',timeout=1800,
                       env={'CEC_OPERATION_DEADLINE_EPOCH':'1',
                            'CEC_JOB_DEADLINE_EPOCH':'9999999999'})
        launch.assert_not_called()


def test_native_child_inherits_clamped_deadline(tmp_path):
    import time
    parent_deadline=time.time()+40
    env=dict(os.environ,CEC_OPERATION_DEADLINE_EPOCH=str(parent_deadline),
             CEC_JOB_DEADLINE_EPOCH=str(parent_deadline+600))
    result=budget.run([sys.executable,'-c',
        'import os; print(os.environ["CEC_OPERATION_DEADLINE_EPOCH"])'],
        tmp_path,operation='nested',timeout=1800,env=env)
    inherited=float((tmp_path/'worker.log').read_text())
    assert result['status']=='complete'
    assert inherited <= parent_deadline-14.9
    assert 0 < result['allowed_timeout_s'] <= 25


@pytest.mark.parametrize('value', [float('inf'), float('nan'), -1])
def test_invalid_budgets_cannot_disable_bounding(value):
    with pytest.raises(ValueError):
        budget.available_timeout(value, {})
    if value != -1:
        with pytest.raises(ValueError):
            budget.available_timeout(5, {'CEC_JOB_DEADLINE_EPOCH': str(value)})


def test_completed_search_refusal_is_not_worker_crash(tmp_path):
    evidence = budget.run([sys.executable, '-c', 'raise SystemExit(2)'],
                          tmp_path, operation='search', timeout=5,
                          accepted_exit_codes=(0, 2))
    assert evidence['status'] == 'complete'
    assert evidence['exit_code'] == 2
    assert 'admitted' not in evidence


def test_expired_campaign_does_not_launch_worker(tmp_path):
    with patch.object(budget.subprocess, 'Popen') as launch:
        with pytest.raises(budget.OperationFailure) as caught:
            budget.run(['unused'], tmp_path, operation='probe', timeout=5,
                       env={'CEC_JOB_DEADLINE_EPOCH':'1'})
        launch.assert_not_called()
    assert caught.value.failure_evidence['status']=='campaign_budget_exhausted'
    assert json.loads((tmp_path/'operation.json').read_text())['status']=='campaign_budget_exhausted'


def test_worker_failure_keeps_diagnostics_and_exit_code(tmp_path):
    with pytest.raises(budget.OperationFailure) as caught:
        budget.run([sys.executable, '-c', 'print("witness",flush=True); raise SystemExit(7)'],
                   tmp_path, operation='probe', timeout=5)
    assert caught.value.failure_evidence['exit_code']==7
    assert (tmp_path/'worker.log').read_text().strip()=='witness'


@pytest.mark.skipif(os.name!='posix', reason='WSL process groups')
def test_timeout_stops_owned_process_group_and_preserves_last_phase(tmp_path):
    env = dict(os.environ, PYTHONPATH=str(Path(budget.__file__).parent))
    script = ('import cec_operation_budget as b, time; '
              'handle=b.arm_diagnostics(); b.progress("exact_geometry", trial=3); time.sleep(30)')
    with pytest.raises(budget.OperationFailure) as caught:
        budget.run([sys.executable, '-c', script], tmp_path, operation='probe', timeout=.5, env=env)
    evidence = caught.value.failure_evidence
    assert evidence['status']=='operation_budget_exhausted'
    assert evidence['last_progress']['phase']=='exact_geometry'
    assert evidence['elapsed_s'] < 5
    assert (tmp_path/'stacks.log').stat().st_size > 0
    with pytest.raises(ProcessLookupError):
        os.kill(evidence['pid'], 0)


def test_probe_children_cannot_overwrite_coordinator_phase(tmp_path, monkeypatch):
    path=tmp_path/'progress.json'
    monkeypatch.setenv('CEC_OPERATION_PROGRESS',str(path))
    monkeypatch.setenv('CEC_OPERATION_OWNER_PID','-1')
    budget.progress('child')
    assert not path.exists()
    monkeypatch.setenv('CEC_OPERATION_OWNER_PID',str(os.getpid()))
    budget.progress('owner')
    assert json.loads(path.read_text())['phase']=='owner'


def test_dead_job_journal_no_longer_claims_running(tmp_path):
    path=tmp_path/'pipeline-state.json'
    previous={'status':'complete', 'result':{'ok':True}}
    path.write_text(json.dumps({'stages':{'source':previous,'placement':{'status':'running','input_digest':'unchanged'}}}))
    result=suite.terminalize_state(path,process_status='budget_exhausted',exit_code=-15)
    assert result['stages']['placement']['status']=='timed_out'
    assert result['stages']['placement']['input_digest']=='unchanged'
    assert result['stages']['source']==previous
    assert suite.stage_summary(result['stages']['placement'])['admission_ok'] is None


def test_failed_isolated_repair_cannot_mutate_parent(tmp_path):
    import cec_full_pipeline as pipeline
    source=tmp_path/'board.kicad_pcb'
    source.write_text('protected original')
    cfg=SimpleNamespace(board='synthetic',params={})
    def fail(command, directory, **kwargs):
        # Simulate a native operation interrupted in the middle of saving.
        worker=Path(command[3])
        assert worker != source
        worker.write_text('partial candidate')
        raise budget.OperationFailure(dict(operation='priority-repair',directory=str(directory),status='operation_budget_exhausted'))
    with patch.object(budget,'run',side_effect=fail):
        with pytest.raises(budget.OperationFailure):
            pipeline._run_priority_placement_operation_isolated('priority-repair',cfg,source)
    assert source.read_text()=='protected original'


@pytest.mark.parametrize('ok, changed', [(False, True), (True, False), (True, True)])
def test_isolated_repair_promotes_only_completed_accepted_change(tmp_path, ok, changed):
    import cec_full_pipeline as pipeline
    source = tmp_path/'board.kicad_pcb'
    source.write_text('protected original')
    cfg = SimpleNamespace(board='synthetic', params={})
    def complete(command, directory, **kwargs):
        Path(command[3]).write_text('qualified candidate')
        (Path(directory)/'report.json').write_text(json.dumps(dict(ok=ok, changed=changed)))
        return dict(status='complete', exit_code=0)
    with patch.object(budget, 'run', side_effect=complete):
        pipeline._run_priority_placement_operation_isolated('priority-repair', cfg, source)
    assert source.read_text() == ('qualified candidate' if ok and changed else 'protected original')


@pytest.mark.skipif(os.name!='posix', reason='WSL process groups')
def test_parent_cancellation_is_forwarded_to_owned_worker(tmp_path):
    import signal
    import subprocess
    import time
    env = dict(os.environ, PYTHONPATH=str(Path(budget.__file__).parent))
    script = ('import cec_operation_budget as b, sys; '
              'b.run([sys.executable,"-c","import time; time.sleep(30)"],'
              'sys.argv[1],operation="cancel-test",timeout=20)')
    parent = subprocess.Popen([sys.executable, '-c', script, str(tmp_path)], env=env)
    try:
        deadline = time.monotonic()+5
        while not (tmp_path/'operation.json').exists() and time.monotonic()<deadline:
            time.sleep(.01)
        evidence = json.loads((tmp_path/'operation.json').read_text())
        os.kill(parent.pid, signal.SIGTERM)
        parent.wait(timeout=5)
        result = json.loads((tmp_path/'operation.json').read_text())
        assert result['status'] == 'cancelled_by_parent'
        with pytest.raises(ProcessLookupError):
            os.kill(evidence['pid'], 0)
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.wait()
