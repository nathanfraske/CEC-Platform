"""The standalone canonical candidate owns one hard lease, not one per domain."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace
from unittest import mock

import pytest

import cec_full_pipeline as pipeline
import cec_operation_budget as budget
import cec_route_candidate_worker as entry
import cec_synth_pipeline as synth


SHIM = r'''
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import cec_full_pipeline as pipeline
import cec_operation_budget as budget
import cec_route_candidate_worker as entry

def synthetic(payload):
    report = Path(sys.argv[sys.argv.index('--report') + 1])
    mode = os.environ.get('CEC_TEST_ROUTE_MODE', 'inspect')
    state = dict(pid=os.getpid(), operation_deadline=float(os.environ['CEC_OPERATION_DEADLINE_EPOCH']),
                 job_deadline=os.environ.get('CEC_JOB_DEADLINE_EPOCH'), payload=payload)
    if mode == 'timeout':
        ready = report.with_name('descendant-ready')
        child = subprocess.Popen([sys.executable, '-c',
            'import signal,sys,time; from pathlib import Path; '
            'signal.signal(signal.SIGTERM,signal.SIG_IGN); '
            'Path(sys.argv[1]).write_text("ready"); time.sleep(30)', str(ready)])
        state['child_pid'] = child.pid
        while not ready.exists():
            time.sleep(.005)
    report.with_name('observed.json').write_text(json.dumps(state))
    budget.progress('synthetic_route', mode=mode)
    if mode == 'timeout':
        time.sleep(30)
    if mode == 'crash_after_report':
        report.write_text(json.dumps(dict(seed=payload['seed'], gate=True, routed=payload['board'])))
        raise RuntimeError('synthetic failure after writing an untrusted candidate receipt')
    result = dict(seed=payload['seed'], gate=False, routed=None,
                  failure_stage='synthetic_refusal', sort_key=[1,99], observed=state)
    if mode == 'bad_seed':
        result['seed'] += 1
    if mode == 'bad_gate':
        result['gate'] = 'yes'
    if mode == 'nested':
        import cec_synth_pipeline as synth
        import cec_power_artifact_worker as worker
        worker.__file__ = os.environ['CEC_TEST_NESTED_WORKER']
        trial = Path(payload['work_dir']) / 'private-current.kicad_pcb'
        trial.write_text('private source')
        rows = [synth._route_priority_current_domain_isolated(trial, 'POWER_%d' % i, timeout=45)
                for i in range(15)]
        rows.append(synth._route_priority_current_domain_isolated(trial, 'POWER_0',
                                                                timeout=120, effort='exact'))
        result['nested'] = rows
    return result

pipeline._route_candidate_worker = synthetic
raise SystemExit(entry.main())
'''


@pytest.fixture
def candidate_context(tmp_path, monkeypatch):
    source = tmp_path / 'input.kicad_pcb'
    source.write_text('immutable input')
    cfg = SimpleNamespace(board='synthetic-source', dir=str(tmp_path),
        sch='explicit-source.kicad_sch', net=None, pcb=str(source),
        pins={'ANCHOR': 'USER_PINNED'}, profile='consumer', board_key='synthetic/key',
        bom_csv='explicit-bom.csv',
        params={'automatic_pin_escape_tier': True, 'route_worker_watchdog_s': 60,
                'route_finish_reserve_s': 5})
    monkeypatch.delenv('CEC_JOB_DEADLINE_EPOCH', raising=False)
    monkeypatch.delenv('CEC_OPERATION_DEADLINE_EPOCH', raising=False)
    monkeypatch.delenv('CEC_OPERATION_PROGRESS', raising=False)
    monkeypatch.delenv('CEC_OPERATION_STACKS', raising=False)
    monkeypatch.setattr(pipeline, '_route_params_for_board', lambda *_: dict(cfg.params))
    monkeypatch.setattr(pipeline, '_grade_route_incumbent', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(pipeline, '_resume_route_residuals', lambda *_args, **_kwargs:
                        (None, {'skip_global': False}))
    recovery = mock.Mock(return_value=([], {'recovered': 0}))
    monkeypatch.setattr(pipeline, '_recover_route_checkpoints', recovery)
    shim = tmp_path / 'route-entry-shim.py'
    shim.write_text(SHIM)
    monkeypatch.setattr(entry, '__file__', str(shim))
    return source, cfg, recovery


def dispatch(candidate_context, tmp_path):
    source, cfg, recovery = candidate_context
    output = tmp_path / 'route'
    with pytest.raises(pipeline.PipelineBlocked):
        pipeline._route_stage(source, output, cfg, passes=7, opt=8, seed=39,
                              timeout=11, thermal='lazy', allow_route_access_repair=True)
    assert source.read_text() == 'immutable input'
    summary = json.loads((output / 'candidate-summary.json').read_text())
    executor = summary['executor']
    report = Path(executor['report'])
    result = json.loads(report.read_text()) if report.exists() else None
    return summary, executor, report, result


def test_standalone_candidate_creates_shared_lease_and_transports_exact_payload(candidate_context, tmp_path):
    started = time.time()
    summary, executor, report, result = dispatch(candidate_context, tmp_path)
    source, cfg, recovery = candidate_context
    assert executor['mode'] == 'isolated_operation' and executor['status'] == 'complete'
    assert executor['candidate_watchdog_s'] == 60
    assert executor['finalization_reserve_s'] == 5
    assert 0 < executor['operation_evidence']['allowed_timeout_s'] <= 40
    assert started + 35 < result['observed']['operation_deadline'] <= executor['deadline_epoch'] - 19.9
    assert 'CEC_OPERATION_DEADLINE_EPOCH' not in os.environ
    payload = result['observed']['payload']
    assert payload['board'] == str(source.resolve())
    assert payload['params'] == cfg.params
    assert payload['config'] == {key: getattr(cfg, key) for key in
        ('board_key', 'profile', 'pins', 'dir', 'sch', 'net', 'pcb', 'bom_csv')}
    assert payload['seed'] == 39 and payload['passes'] == 7 and payload['opt'] == 8
    assert payload['timeout'] == 11 and payload['allow_route_access_repair']
    assert payload['checkpoint_dir'] == str(tmp_path / 'route' / 'checkpoints' / 'seed-000039')
    assert summary['candidates'][0]['failure_stage'] == 'synthetic_refusal'
    assert report.is_file() and report.with_name('operation.json').is_file()
    recovery.assert_called_once()  # Candidate wall does not suppress checkpoint recovery.


@pytest.mark.parametrize('limiting', ['CEC_JOB_DEADLINE_EPOCH', 'CEC_OPERATION_DEADLINE_EPOCH'])
def test_expired_enclosing_lease_is_not_renewed_even_with_other_lease_funded(candidate_context, tmp_path, monkeypatch, limiting):
    expired = time.time() - 1
    monkeypatch.setenv('CEC_JOB_DEADLINE_EPOCH', str(expired + 600))
    monkeypatch.setenv('CEC_OPERATION_DEADLINE_EPOCH', str(expired + 600))
    monkeypatch.setenv(limiting, str(expired))
    with mock.patch.object(budget.subprocess, 'Popen') as launch:
        summary, executor, report, result = dispatch(candidate_context, tmp_path)
    launch.assert_not_called()
    assert result is None and not report.with_name('observed.json').exists()
    assert executor['deadline_epoch'] == expired
    assert executor['status'] == 'deferred_budget' and executor['budget_exhausted']
    assert executor['outcome'] == 'inconclusive'
    assert executor['operation_failure']['allowed_timeout_s'] == 0
    assert summary['candidates'][0]['blocker_evidence']['physical_feasibility'] == 'not_assessed'
    assert os.environ[limiting] == str(expired)
    candidate_context[2].assert_called_once()


def running(pid):
    path = Path(f'/proc/{pid}/stat')
    return path.exists() and path.read_text().split(') ', 1)[1].split()[0] != 'Z'


@pytest.mark.skipif(os.name != 'posix', reason='WSL process group cleanup')
def test_candidate_hard_wall_kills_owned_native_descendants(candidate_context, tmp_path, monkeypatch):
    monkeypatch.setenv('CEC_TEST_ROUTE_MODE', 'timeout')
    deadline = time.time() + 5 + 15 + 2
    monkeypatch.setenv('CEC_JOB_DEADLINE_EPOCH', str(deadline))
    unrelated = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], start_new_session=True)
    try:
        started = time.monotonic()
        summary, executor, report, _result = dispatch(candidate_context, tmp_path)
        assert time.monotonic() - started < 7
        observed = json.loads(report.with_name('observed.json').read_text())
        assert executor['status'] == 'deferred_budget' and executor['budget_exhausted']
        assert executor['operation_failure']['status'] == 'operation_budget_exhausted'
        assert executor['operation_failure']['last_progress']['phase'] == 'synthetic_route'
        assert summary['candidates'][0]['artifact'] is None
        until = time.monotonic() + 2
        while running(observed['child_pid']) and time.monotonic() < until:
            time.sleep(.01)
        assert not running(observed['pid']) and not running(observed['child_pid'])
        assert unrelated.poll() is None
    finally:
        unrelated.terminate()
        unrelated.wait(timeout=5)


@pytest.mark.parametrize('mode', ['bad_seed', 'bad_gate', 'crash_after_report'])
def test_incomplete_worker_or_invalid_receipt_never_enters_candidate_admission(candidate_context, tmp_path, monkeypatch, mode):
    monkeypatch.setenv('CEC_TEST_ROUTE_MODE', mode)
    summary, executor, _report, _result = dispatch(candidate_context, tmp_path)
    assert executor['status'] == 'worker_failed' and not executor['budget_exhausted']
    assert executor['outcome'] == 'inconclusive'
    assert summary['candidates'][0]['artifact'] is None
    assert summary['candidates'][0]['blocker_evidence']['proof_complete'] is False
    assert executor['operation_failure']['status'] == (
        'worker_failed' if mode == 'crash_after_report' else 'worker_report_invalid')
    if mode == 'crash_after_report':
        assert 'synthetic failure' in executor['operation_failure']['log_tail']


def test_real_standalone_child_shares_lease_across_fifteen_domains_and_exact_retry(candidate_context, tmp_path, monkeypatch):
    nested = tmp_path / 'nested-current.py'
    events = tmp_path / 'nested-events.jsonl'
    nested.write_text('import os,time\n'
                      'with open(os.environ["CEC_TEST_NESTED_EVENTS"], "a") as out: out.write("started\\n")\n'
                      'time.sleep(30)\n')
    monkeypatch.setenv('CEC_TEST_NESTED_EVENTS', str(events))
    monkeypatch.setenv('CEC_TEST_NESTED_WORKER', str(nested))
    monkeypatch.setenv('CEC_TEST_ROUTE_MODE', 'nested')
    monkeypatch.setenv('CEC_OPERATION_DEADLINE_EPOCH', str(time.time() + 5 + 15 + 17))
    started = time.monotonic()
    _summary, executor, _report, result = dispatch(candidate_context, tmp_path)
    assert time.monotonic() - started < 7
    assert executor['status'] == 'complete'  # Completed, honestly inconclusive test receipt.
    assert events.read_text().splitlines() == ['started']
    assert len(result['nested']) == 16
    assert result['nested'][0]['timed_out']
    assert all(row['status'] == 'deferred_budget' and row['retryable'] is False for row in result['nested'])
    assert all(row['operation_failure']['allowed_timeout_s'] == 0 for row in result['nested'][1:])


def test_worker_entry_preserves_config_seed_checkpoint_and_restores_seed_axis(tmp_path, monkeypatch):
    source = tmp_path / 'source.kicad_pcb'
    payload = dict(board=str(source), board_name='fixture', params={'route_effort': 17},
        config={'board_key': 'explicit/key', 'profile': 'pro', 'pins': {'A': 'USER_PINNED'},
                'dir': str(tmp_path), 'sch': 'explicit.sch', 'net': None, 'pcb': 'explicit.pcb',
                'bom_csv': 'explicit.csv', 'params': {'must_not_replace': True}, 'unknown': 'ignored'},
        passes=7, opt=8, seed=39, timeout=11, thermal='lazy', work_dir=str(tmp_path / 'work'),
        checkpoint_dir=str(tmp_path / 'checkpoints'), allow_route_access_repair=True)
    payload_file, report = tmp_path / 'payload.json', tmp_path / 'report.json'
    payload_file.write_text(json.dumps(payload))
    cfg = SimpleNamespace(params=dict(payload['params']), net='stale.net')
    checkpoint = object()
    seen = {}
    def oracle(board, **kwargs):
        seen.update(board=board, **kwargs)
        assert os.environ['CEC_FR_SEED_AXIS'] == '1'
        return {'gate': False, 'routed': None, 'failure_stage': 'physical_refusal'}
    monkeypatch.setenv('CEC_FR_SEED_AXIS', 'caller-value')
    with mock.patch.object(budget, 'arm_diagnostics', return_value=None), \
            mock.patch.object(synth.Config, 'load', return_value=cfg) as load, \
            mock.patch.object(synth, 'route_oracle_grade', side_effect=oracle), \
            mock.patch('cec_route_checkpoint.publisher', return_value=checkpoint) as publisher:
        assert entry.main(['--payload', str(payload_file), '--report', str(report)]) == 0
    assert os.environ['CEC_FR_SEED_AXIS'] == 'caller-value'
    for key in ('board_key', 'profile', 'pins', 'dir', 'sch', 'net', 'pcb', 'bom_csv'):
        assert getattr(cfg, key) == payload['config'][key]
    assert cfg.params == payload['params'] and not hasattr(cfg, 'unknown')
    assert seen['checkpoint'] is checkpoint and seen['board'] == payload['board']
    assert seen['seed'] == 39 and seen['fr_timeout'] == 11 and seen['allow_route_access_repair']
    assert seen['craft_gates'] and seen['precision'] and seen['keep']
    publisher.assert_called_once_with(payload['checkpoint_dir'], cfg, payload['board'], 39)
    load.assert_called_once_with('fixture', params=payload['params'])
    result = json.loads(report.read_text())
    assert result['seed'] == 39 and result['failure_stage'] == 'physical_refusal'
    assert result['route_candidate_diversity']['seed'] == 39


@pytest.mark.parametrize('candidates', [1, 3])
@pytest.mark.parametrize('configured,environment,timeout,expected', [
    (None, None, 11, 7200),
    (None, None, 2000, 13800),
    (None, '5', 11, 60),
    (90, '180', 11, 90),
    ('invalid', None, 11, 7200),
    ('inf', None, 11, 7200),
])
def test_single_and_ensemble_preserve_effective_config_and_watchdog_policy(
        candidate_context, tmp_path, monkeypatch, candidates,
        configured, environment, timeout, expected):
    source, cfg, _recovery = candidate_context
    # A promotion reconstructs Config, whose discovered source defaults must
    # not replace the caller's explicit source family or pins.
    cfg.params.pop('automatic_pin_escape_tier')
    cfg.params.pop('route_worker_watchdog_s')
    if configured is not None:
        cfg.params['route_worker_watchdog_s'] = configured
    if environment is None:
        monkeypatch.delenv('CEC_ROUTE_WORKER_WATCHDOG_S', raising=False)
    else:
        monkeypatch.setenv('CEC_ROUTE_WORKER_WATCHDOG_S', environment)
    monkeypatch.setattr(synth.Config, 'load', lambda name, params:
        SimpleNamespace(board=name, params=params, dir='stale-dir', sch='stale.sch',
                        net='stale.net', pcb='stale.pcb', pins={}))
    seen = []

    def receipt(payload):
        seen.append(payload)
        return dict(seed=payload['seed'], gate=False, routed=None,
                    failure_stage='synthetic_refusal', sort_key=[1, 99])

    def serial(command, directory, *, operation, timeout, env):
        assert timeout == expected and operation == 'route-candidate'
        payload = json.loads(Path(command[command.index('--payload') + 1]).read_text())
        budget.write_json(command[command.index('--report') + 1], receipt(payload))
        return dict(status='complete', operation=operation, directory=str(directory))

    def ensemble(pool, payloads, workers, *, results, **kwargs):
        assert len(payloads) == candidates and workers == 2
        results.extend(receipt(payload) for payload in payloads)

    monkeypatch.setattr(budget, 'run', serial)
    monkeypatch.setattr(pipeline, '_route_candidate_cohorts', ensemble)
    monkeypatch.setattr('concurrent.futures.ProcessPoolExecutor', mock.Mock())
    monkeypatch.setattr('cec_process_pool.shutdown_process_pool', lambda *_args, **_kwargs: {})
    output = tmp_path / 'policy-route'
    with pytest.raises(pipeline.PipelineBlocked):
        pipeline._route_stage(source, output, cfg, passes=7, opt=8, seed=39,
            timeout=timeout, thermal='lazy', candidates=candidates, route_workers=2,
            allow_route_access_repair=True)
    summary = json.loads((output / 'candidate-summary.json').read_text())
    assert summary['executor']['candidate_watchdog_s'] == expected
    assert len(seen) == candidates
    for payload in seen:
        assert payload['config'] == {key: getattr(cfg, key) for key in
            ('board_key', 'profile', 'pins', 'dir', 'sch', 'net', 'pcb', 'bom_csv')}
        assert payload['params'] == dict(cfg.params, automatic_pin_escape_tier=True)
        assert payload['seed'] in summary['seeds']
        assert payload['timeout'] == timeout and payload['passes'] == 7 and payload['opt'] == 8
        assert payload['allow_route_access_repair']
        assert Path(payload['checkpoint_dir']).name == 'seed-%06d' % payload['seed']
    assert source.read_text() == 'immutable input'
