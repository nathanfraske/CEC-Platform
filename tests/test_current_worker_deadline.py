"""Current workers spend one enclosing lease, never one renewed lease per net."""
import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from unittest import mock

import pytest

import cec_operation_budget as budget
import cec_power_artifact_worker as worker
import cec_synth_pipeline as synth


WORKER_SOURCE = r'''
import json
import os
from pathlib import Path
import subprocess
import sys
import time

phase, board = sys.argv[1:3]
options = dict(zip(sys.argv[3::2], sys.argv[4::2]))
report = Path(options['--report'])
mode = os.environ.get('CEC_TEST_CURRENT_MODE', 'success')
event = dict(phase=phase, pid=os.getpid(), options=options,
             deadline=float(os.environ['CEC_OPERATION_DEADLINE_EPOCH']))
if mode == 'descendant_timeout':
    ready = report.with_name('child-ready')
    child = subprocess.Popen([sys.executable, '-c',
        'import signal,sys,time; from pathlib import Path; '
        'signal.signal(signal.SIGTERM,signal.SIG_IGN); '
        'Path(sys.argv[1]).write_text("ready"); time.sleep(30)', str(ready)])
    event['child_pid'] = child.pid
    while not ready.exists():
        time.sleep(.005)
with open(os.environ['CEC_TEST_CURRENT_EVENTS'], 'a') as sink:
    sink.write(json.dumps(event) + '\n')
if mode in ('timeout', 'descendant_timeout'):
    Path(board).write_text('unfinished private candidate')
    time.sleep(30)
if mode == 'crash':
    Path(board).write_text('unfinished private candidate')
    print('x' * 8192)
    print('synthetic native worker crashed', flush=True)
    raise SystemExit(7)
if mode == 'missing_report':
    raise SystemExit(0)
if mode == 'invalid_json':
    report.write_text('{')
    raise SystemExit(0)
if phase == 'prune-current':
    result = dict(schema=1, removed=[], removed_vias=[])
else:
    result = dict(schema=1, net=options['--net'], changed=False,
                  connected=mode != 'refusal', effort=options['--effort'])
if mode == 'non_object':
    result = []
elif mode == 'incomplete_object':
    result = dict(schema=1)
elif mode == 'wrong_net':
    result['net'] = 'A_DIFFERENT_DOMAIN'
elif mode == 'truthy_connectivity':
    result['connected'] = 'yes'
report.write_text(json.dumps(result))
'''


@pytest.fixture
def fake_worker(tmp_path, monkeypatch):
    script = tmp_path / 'current-worker.py'
    script.write_text(WORKER_SOURCE)
    monkeypatch.setattr(worker, '__file__', str(script))
    monkeypatch.delenv('CEC_OPERATION_DEADLINE_EPOCH', raising=False)
    monkeypatch.delenv('CEC_JOB_DEADLINE_EPOCH', raising=False)
    monkeypatch.delenv('CEC_OPERATION_PROGRESS', raising=False)
    monkeypatch.setenv('CEC_TEST_CURRENT_EVENTS', str(tmp_path / 'events.jsonl'))
    board = tmp_path / 'trial.kicad_pcb'
    board.write_text('input')
    return board


def events(board):
    path = board.parent / 'events.jsonl'
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def caller_retries_exact(result):
    """Exercise the actual coordinator branch, not a duplicated predicate."""
    tree = ast.parse(Path(synth.__file__).read_text())
    prefix = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                  and node.name == '_compile_priority_current_prefix')
    branch = next(node for node in ast.walk(prefix) if isinstance(node, ast.If)
                  and any(isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
                          and call.func.id == '_route_priority_current_domain_isolated'
                          for call in ast.walk(ast.Module(body=node.body, type_ignores=[]))))
    return eval(compile(ast.Expression(branch.test), str(synth.__file__), 'eval'),
                {'fast': result})


@pytest.mark.parametrize('phase', ['route', 'prune'])
@pytest.mark.parametrize('limiting', ['CEC_OPERATION_DEADLINE_EPOCH', 'CEC_JOB_DEADLINE_EPOCH'])
def test_expired_enclosing_lease_never_launches_current_worker(fake_worker, monkeypatch, phase, limiting):
    monkeypatch.setenv('CEC_OPERATION_DEADLINE_EPOCH', str(time.time() + 600))
    monkeypatch.setenv('CEC_JOB_DEADLINE_EPOCH', str(time.time() + 600))
    monkeypatch.setenv(limiting, str(time.time() + 10))  # Finalization reserve is not search time.
    with mock.patch.object(budget.subprocess, 'Popen') as launch:
        if phase == 'prune':
            with pytest.raises(budget.OperationFailure) as caught:
                synth._prune_priority_current_artifact_isolated(fake_worker, ['POWER'])
            result = caught.value.failure_evidence
        else:
            result = synth._route_priority_current_domain_isolated(fake_worker, 'POWER', timeout=120)
            assert result['status'] == 'deferred_budget'
            assert not result['timed_out']  # It did not start and then time out.
            assert not caller_retries_exact(result)
        launch.assert_not_called()
    assert result['reason'] == 'deferred_budget'
    assert result['outcome'] == 'inconclusive'
    assert result['budget_exhausted'] and result['search_inconclusive']
    assert not result['retryable'] and not result['proof_complete']
    assert result['physical_feasibility'] == 'not_assessed'
    assert not result['release_authority']
    assert fake_worker.read_text() == 'input'


@pytest.mark.parametrize('phase', ['route', 'prune'])
def test_real_current_worker_receives_clamped_deadline_and_unique_diagnostics(fake_worker, monkeypatch, phase):
    deadline = time.time() + 25
    monkeypatch.setenv('CEC_OPERATION_DEADLINE_EPOCH', str(deadline))
    monkeypatch.setenv('CEC_JOB_DEADLINE_EPOCH', str(deadline + 600))
    reports = []
    for _attempt in range(2):
        if phase == 'route':
            report = synth._route_priority_current_domain_isolated(
                fake_worker, 'POWER', timeout=120, effort='exact', passes=2)
            assert report['connected'] and not report['timed_out']
        else:
            report = synth._prune_priority_current_artifact_isolated(
                fake_worker, ['POWER'], ['retained-copper'], timeout=120)
            assert report['removed'] == [] and report['removed_vias'] == []
        reports.append(report)
    paths = [Path(report['operation_evidence']['directory']) for report in reports]
    assert paths[0] != paths[1]
    assert all((path / 'operation.json').is_file() and (path / 'report.json').is_file()
               and (path / 'worker.log').is_file() for path in paths)
    assert all(0 < report['operation_evidence']['allowed_timeout_s'] <= 10 for report in reports)
    assert all(event['deadline'] <= deadline - 14.9 for event in events(fake_worker))
    assert os.environ['CEC_OPERATION_DEADLINE_EPOCH'] == str(deadline)
    if phase == 'prune':
        assert json.loads(events(fake_worker)[0]['options']['--preserve-uuids-json']) == ['retained-copper']
    else:
        assert events(fake_worker)[0]['options']['--passes'] == '2'


def test_fifteen_domains_and_explicit_exact_retry_cannot_renew_a_spent_parent_lease(fake_worker, monkeypatch):
    monkeypatch.setenv('CEC_TEST_CURRENT_MODE', 'timeout')
    deadline = time.time() + 15.6
    monkeypatch.setenv('CEC_OPERATION_DEADLINE_EPOCH', str(deadline))
    monkeypatch.setenv('CEC_JOB_DEADLINE_EPOCH', str(deadline + 600))
    started = time.monotonic()
    reports = [synth._route_priority_current_domain_isolated(fake_worker, f'POWER_{index}', timeout=45)
               for index in range(15)]
    exact = synth._route_priority_current_domain_isolated(fake_worker, 'POWER_0', timeout=120, effort='exact')
    assert time.monotonic() - started < 5
    assert len(events(fake_worker)) == 1
    assert reports[0]['timed_out']
    assert all(row['status'] == 'deferred_budget' and not row['connected'] for row in [*reports, exact])
    assert all(row['retryable'] is False for row in [*reports, exact])
    assert all(row['operation_failure']['allowed_timeout_s'] == 0 for row in [*reports[1:], exact])
    assert os.environ['CEC_OPERATION_DEADLINE_EPOCH'] == str(deadline)
    assert not caller_retries_exact(reports[0])


def process_is_running(pid):
    stat = Path(f'/proc/{pid}/stat')
    # An orphan may await PID 1's reap after SIGKILL; a zombie cannot keep working.
    return stat.is_file() and stat.read_text().split(') ', 1)[1].split()[0] != 'Z'


@pytest.mark.skipif(os.name != 'posix', reason='Owned WSL process groups')
@pytest.mark.parametrize('phase', ['route', 'prune'])
def test_real_timeout_kills_term_resistant_descendant_but_not_unrelated_process(fake_worker, monkeypatch, phase):
    monkeypatch.setenv('CEC_TEST_CURRENT_MODE', 'descendant_timeout')
    unrelated = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'],
                                 start_new_session=True)
    try:
        if phase == 'route':
            result = synth._route_priority_current_domain_isolated(fake_worker, 'POWER', timeout=.6)
            evidence = result['operation_failure']
            assert result['status'] == 'deferred_budget' and result['timed_out']
        else:
            with pytest.raises(budget.OperationFailure) as caught:
                synth._prune_priority_current_artifact_isolated(fake_worker, ['POWER'], timeout=.6)
            evidence = caught.value.failure_evidence
        event, = events(fake_worker)
        assert evidence['status'] == 'operation_budget_exhausted'
        assert evidence['elapsed_s'] < 5
        assert not process_is_running(event['pid'])
        deadline = time.monotonic() + 2
        while process_is_running(event['child_pid']) and time.monotonic() < deadline:
            time.sleep(.01)
        assert not process_is_running(event['child_pid'])
        assert unrelated.poll() is None
        assert Path(evidence['directory'], 'operation.json').is_file()
    finally:
        unrelated.terminate()
        unrelated.wait(timeout=5)


@pytest.mark.parametrize('mode', ['crash', 'missing_report', 'invalid_json', 'non_object', 'incomplete_object',
                                  'wrong_net', 'truthy_connectivity'])
def test_route_infrastructure_failure_is_inconclusive_and_never_exact_retried(fake_worker, monkeypatch, mode):
    monkeypatch.setenv('CEC_TEST_CURRENT_MODE', mode)
    result = synth._route_priority_current_domain_isolated(fake_worker, 'POWER', timeout=5)
    assert not result['connected'] and not result['changed']
    assert result['outcome'] == 'inconclusive' and result['search_inconclusive']
    assert result['status'] == 'worker_failed' and not result['budget_exhausted']
    assert result['physical_feasibility'] == 'not_assessed'
    assert result['current_width']['ok'] is None
    assert not result['proof_complete'] and not result['release_authority']
    assert not caller_retries_exact(result)
    evidence = result['operation_failure']
    assert evidence['status'] == ('worker_failed' if mode == 'crash' else 'worker_report_invalid')
    assert Path(evidence['directory'], 'result.json').is_file()
    assert json.loads(Path(evidence['directory'], 'operation.json').read_text()) == evidence
    if mode == 'crash':
        assert result['returncode'] == 7
        assert 'synthetic native worker crashed' in Path(evidence['log']).read_text()


@pytest.mark.parametrize('phase', ['route', 'prune'])
def test_launch_error_is_typed_infrastructure_failure_not_physical_refusal(fake_worker, phase):
    with mock.patch.object(budget.subprocess, 'Popen', side_effect=OSError('cannot launch')):
        if phase == 'route':
            result = synth._route_priority_current_domain_isolated(fake_worker, 'POWER')
            assert not caller_retries_exact(result)
            evidence = result['operation_failure']
        else:
            with pytest.raises(budget.OperationFailure) as caught:
                synth._prune_priority_current_artifact_isolated(fake_worker, ['POWER'])
            evidence = caught.value.failure_evidence
    assert evidence['status'] == 'worker_start_failed'
    assert evidence['error'] == 'cannot launch'
    assert json.loads(Path(evidence['directory'], 'operation.json').read_text()) == evidence


@pytest.mark.parametrize('mode', ['crash', 'missing_report', 'invalid_json', 'non_object', 'incomplete_object'])
def test_prune_infrastructure_failure_raises_instead_of_an_empty_success_report(fake_worker, monkeypatch, mode):
    monkeypatch.setenv('CEC_TEST_CURRENT_MODE', mode)
    with pytest.raises(budget.OperationFailure) as caught:
        synth._prune_priority_current_artifact_isolated(fake_worker, ['POWER'], timeout=5)
    evidence = caught.value.failure_evidence
    assert evidence['outcome'] == 'inconclusive' and evidence['search_inconclusive']
    assert not evidence['budget_exhausted'] and not evidence['retryable']
    assert evidence['physical_feasibility'] == 'not_assessed'
    saved = json.loads(Path(evidence['directory'], 'operation.json').read_text())
    assert saved == evidence


def test_completed_physical_refusal_keeps_existing_fast_exact_portfolio(fake_worker, monkeypatch):
    monkeypatch.setenv('CEC_TEST_CURRENT_MODE', 'refusal')
    result = synth._route_priority_current_domain_isolated(fake_worker, 'POWER', timeout=5)
    assert not result['connected']
    assert not result['timed_out'] and not result.get('search_inconclusive')
    assert result['operation_evidence']['status'] == 'complete'
    assert caller_retries_exact(result)


def test_prefix_caller_aborts_on_unfinished_prune_and_retains_immutable_input(fake_worker, monkeypatch):
    monkeypatch.setenv('CEC_TEST_CURRENT_MODE', 'timeout')
    monkeypatch.setenv('CEC_OPERATION_DEADLINE_EPOCH', str(time.time() + 15.6))
    candidate = fake_worker.parent / 'candidate.kicad_pcb'
    with mock.patch('pcbnew.LoadBoard'), \
            mock.patch.object(worker, 'current_route_operation_admission',
                              return_value={'eligible': True, 'qualified_prefix_nets': []}), \
            mock.patch('cec_fr.copy_project_sidecars'), \
            mock.patch('cec_fr.materialize_hierarchical_netclass_assignments'), \
            mock.patch('cec_constraints._legal_neckdown_uuids', return_value=[]), \
            mock.patch('cec_score.score'), \
            mock.patch.object(synth, '_route_priority_current_domain_isolated') as route:
        with pytest.raises(budget.OperationFailure) as caught:
            synth._compile_priority_current_prefix(str(fake_worker), ['POWER'], {}, str(candidate))
    assert caught.value.failure_evidence['reason'] == 'deferred_budget'
    assert fake_worker.read_text() == 'input'
    assert not candidate.exists()
    assert candidate.with_name('candidate-pruned.kicad_pcb').read_text() == 'unfinished private candidate'
    route.assert_not_called()


@pytest.mark.parametrize('mode', ['crash', 'timeout'])
def test_filled_authority_caller_never_promotes_interrupted_private_candidate(fake_worker, monkeypatch, mode):
    monkeypatch.setenv('CEC_TEST_CURRENT_MODE', mode)
    proof = {'POWER': {'available': True, 'connected': False, 'domain': {'complete': True}}}
    with mock.patch('cec_fr.copy_project_sidecars'), \
            mock.patch.object(synth, '_score_priority_power_artifact_isolated'), \
            mock.patch.object(synth, '_route_score_admission') as admission:
        result = synth._repair_filled_current_authority(str(fake_worker), proof, timeout=.6)
    assert not result['changed']
    assert fake_worker.read_text() == 'input'
    admission.assert_not_called()
    assert not result['domains']['POWER']['accepted']
    assert result['domains']['POWER']['routing']['outcome'] == 'inconclusive'


@pytest.mark.parametrize('phase', ['route', 'prune'])
def test_parent_cancellation_is_not_swallowed_as_a_routing_refusal(fake_worker, phase):
    with mock.patch.object(budget, 'run', side_effect=SystemExit(143)):
        with pytest.raises(SystemExit) as caught:
            if phase == 'route':
                synth._route_priority_current_domain_isolated(fake_worker, 'POWER')
            else:
                synth._prune_priority_current_artifact_isolated(fake_worker, ['POWER'])
    assert caught.value.code == 143


@pytest.mark.parametrize('phase', ['route', 'prune'])
def test_enclosing_diagnostics_outlive_disposable_candidate_directory(fake_worker, monkeypatch, phase):
    durable = fake_worker.parent / 'enclosing-operation'
    durable.mkdir()
    progress = durable / 'progress.json'
    progress.write_text('{"phase":"parent"}')
    monkeypatch.setenv('CEC_OPERATION_PROGRESS', str(progress))
    with tempfile.TemporaryDirectory(dir=fake_worker.parent) as private:
        trial = Path(private) / 'trial.kicad_pcb'
        trial.write_text('input')
        if phase == 'route':
            report = synth._route_priority_current_domain_isolated(trial, 'POWER', timeout=5)
        else:
            report = synth._prune_priority_current_artifact_isolated(trial, ['POWER'], timeout=5)
        evidence = report['operation_evidence']
    directory = Path(evidence['directory'])
    assert directory.parent == durable
    assert not trial.exists()
    assert (directory / 'operation.json').is_file()
    assert (directory / 'report.json').is_file()
    assert progress.read_text() == '{"phase":"parent"}'


@pytest.mark.parametrize('phase', ['route', 'prune'])
@pytest.mark.parametrize('invalid', ['relative', 'missing_parent', 'directory', 'unwritable'])
def test_invalid_enclosing_progress_location_falls_back_to_candidate_parent(fake_worker, monkeypatch, phase, invalid):
    enclosing = fake_worker.parent / 'enclosing'
    enclosing.mkdir()
    progress = {'relative': Path('relative-progress.json'),
                'missing_parent': enclosing / 'absent' / 'progress.json',
                'directory': enclosing,
                'unwritable': enclosing / 'progress.json'}[invalid]
    monkeypatch.setenv('CEC_OPERATION_PROGRESS', str(progress))
    original = synth.tempfile.mkdtemp
    def create(*args, **kwargs):
        if invalid == 'unwritable' and Path(kwargs['dir']) == enclosing:
            raise PermissionError('synthetic unwritable enclosing diagnostics')
        return original(*args, **kwargs)
    with mock.patch.object(synth.tempfile, 'mkdtemp', side_effect=create):
        if phase == 'route':
            report = synth._route_priority_current_domain_isolated(fake_worker, 'POWER', timeout=5)
        else:
            report = synth._prune_priority_current_artifact_isolated(fake_worker, ['POWER'], timeout=5)
    assert Path(report['operation_evidence']['directory']).parent == fake_worker.parent


@pytest.mark.parametrize('phase', ['route', 'prune'])
def test_bounded_inline_failure_log_survives_without_durable_diagnostic_root(fake_worker, monkeypatch, phase):
    monkeypatch.setenv('CEC_TEST_CURRENT_MODE', 'crash')
    with tempfile.TemporaryDirectory(dir=fake_worker.parent) as private:
        trial = Path(private) / 'trial.kicad_pcb'
        trial.write_text('input')
        if phase == 'route':
            result = synth._route_priority_current_domain_isolated(trial, 'POWER', timeout=5)
            evidence = result['operation_failure']
        else:
            with pytest.raises(budget.OperationFailure) as caught:
                synth._prune_priority_current_artifact_isolated(trial, ['POWER'], timeout=5)
            evidence = caught.value.failure_evidence
    assert not Path(evidence['directory']).exists()
    assert 'synthetic native worker crashed' in evidence['log_tail']
    assert len(evidence['log_tail']) <= 4096
