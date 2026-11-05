"""Execute the production current-worker call sites and failure handoff."""
import ast
import copy
import inspect
import os
from pathlib import Path
import time
from unittest import mock

import pytest

import cec_operation_budget as budget
import cec_synth_pipeline as synth


def exercise(tmp_path, phase, *, error=None, report=None, route_nets=('POWER',)):
    """Use the actual branch plus its _trace/_fail helpers, as other oracle tests do."""
    function = ast.parse(inspect.getsource(synth.route_oracle_grade)).body[0]
    helpers = [copy.deepcopy(node) for node in function.body
               if isinstance(node, ast.FunctionDef)
               and node.name in ('_trace', '_fail', '_fail_current_operation')]
    assert len(helpers) == 3
    if phase == 'compile':
        branches = [node for node in ast.walk(function) if isinstance(node, ast.If)
                    and isinstance(node.test, ast.Name) and node.test.id == '_current_pre_nets']
    else:
        branches = [node for node in ast.walk(function) if isinstance(node, ast.Try)
                    and any(isinstance(child, ast.Assign)
                            and any(isinstance(target, ast.Name) and target.id == '_current_prune'
                                    for target in child.targets) for child in node.body)]
    assert len(branches) == 1
    initial = ast.parse('label="current-operation-test"\nstage_trace=[]\n'
                        'route_requested=True\ncheckpoint=None\n'
                        'priority_current_route={"enabled":True}\n'
                        'route_input=initial_route_input\nt0=time.monotonic()\n'
                        '_protect=[]').body
    success = ast.parse('return {"passed":True, "priority_current_route":priority_current_route, '
                        '"route_input":route_input, "stage_trace":stage_trace}').body
    module = ast.Module(body=[ast.FunctionDef(name='run', args=ast.arguments(
        posonlyargs=[], args=[], kwonlyargs=[], kw_defaults=[], defaults=[]),
        body=initial + helpers + [copy.deepcopy(branches[0])] + success,
        decorator_list=[])], type_ignores=[])
    ast.fix_missing_locations(module)
    source = tmp_path / 'input.kicad_pcb'
    source.write_text('immutable input')
    work = tmp_path / 'oracle'
    work.mkdir()
    called = mock.Mock(return_value=report, side_effect=error)
    sanitize = mock.Mock(wraps=synth._sanitize_failure_artifact)
    scope = dict(os=os, time=time, cec_operation_budget=budget,
        _oracle_fail_dict=synth._oracle_fail_dict, _sanitize_failure_artifact=sanitize,
        initial_route_input=str(source), work_dir=str(work), seed=7,
        protect_nets=(),
        _current_pre_nets=['POWER'], _current_pre_domains={}, rules=None,
        _local_power_prefix=None, decoupler_ground={},
        _compile_priority_current_prefix=called,
        _prune_priority_current_artifact_isolated=called,
        _current_seed=str(work / 'private-prune.kicad_pcb'),
        _current_route_nets=route_nets, _current_nets=['POWER'], _current_legal_neckdowns=[])
    exec(compile(module, '<actual-current-operation-handoff>', 'exec'), scope)
    result = scope['run']()
    assert source.read_text() == 'immutable input'
    return result, called, sanitize


def failure(status):
    return budget.OperationFailure(dict(operation='priority-current-prune', status=status,
        directory='/already-removed/operation', requested_timeout_s=120, allowed_timeout_s=.5,
        elapsed_s=.51, exit_code=-15, last_progress={'phase': 'native_prune'},
        log='/already-removed/operation/worker.log', log_tail='retained native diagnostic'))


@pytest.mark.parametrize('status,reason', [
    ('deferred_budget', 'force_prefix_shared_budget_deferred'),
    ('deferred_dependency', 'incomplete_affected_sense'),
    ('deferred_evidence', 'force_prefix_post_copy_epoch_drift'),
    ('deferred_operator', 'bounded_no_legal_rated_path')])
def test_actual_aggregate_failure_is_typed_without_failure_board_work(tmp_path, status, reason):
    report = dict(operation='saved_force_current_prefix', accepted=False,
        status=status, reason=reason, incomplete_nets=['POWER'],
        current_width={'ok':None}, domain_attempts={'POWER':dict(status=status,reason=reason)})
    result, called, sanitize = exercise(tmp_path, 'compile', report=report)
    assert result['status'] == status and result['outcome'] == 'inconclusive'
    assert result['blocker_evidence']['reason'] == ('deferred_budget' if status == 'deferred_budget' else reason)
    assert result['budget_exhausted'] is (status == 'deferred_budget')
    assert result['failure_artifact'] is None and result['routed'] is None
    assert not result['retryable'] and not result['release_authority']
    assert sanitize.call_args.args[0] is None


@pytest.mark.parametrize('phase', ['compile', 'prune'])
@pytest.mark.parametrize('status', ['operation_budget_exhausted', 'campaign_budget_exhausted',
                                  'worker_failed', 'worker_report_invalid'])
def test_current_operation_failure_reaches_trace_and_verdict_without_physical_no_path(tmp_path, phase, status):
    error = failure(status)
    original = copy.deepcopy(error.failure_evidence)
    result, called, sanitize = exercise(tmp_path, phase, error=error)
    exhausted = status in ('operation_budget_exhausted', 'campaign_budget_exhausted')
    assert result['status'] == ('deferred_budget' if exhausted else 'worker_failed')
    assert result['budget_exhausted'] is exhausted
    assert result['outcome'] == 'inconclusive' and result['search_inconclusive']
    assert not result['proof_complete'] and not result['retryable']
    assert result['physical_feasibility'] == 'not_assessed'
    assert not result['gate'] and not result['routing_complete'] and not result['release_authority']
    assert result['failure_stage'] == 'priority_current_route'
    assert result['routed'] is None and result['failure_artifact'] is None
    assert result['operation_failure'] == original == error.failure_evidence
    evidence = result['blocker_evidence']
    assert evidence['operation_failure'] == original
    assert evidence['current_width']['ok'] is None
    assert evidence['input_artifact'] == str(tmp_path / 'input.kicad_pcb')
    assert evidence['attempted_artifact'].endswith('.kicad_pcb')
    assert result['stage_trace'][-1]['detail']['operation_failure'] == original
    assert result['blockers'][0]['causal_chain'][-1]['detail']['operation_failure'] == original
    assert evidence['operation_failure']['log_tail'] == 'retained native diagnostic'
    called.assert_called_once()
    sanitize.assert_called_once_with(None, str(tmp_path / 'oracle'), 'priority_current_route')


@pytest.mark.parametrize('phase', ['compile', 'prune'])
@pytest.mark.parametrize('error', [RuntimeError('unrelated integrity failure'), SystemExit(143)])
def test_scoped_operation_catches_do_not_swallow_integrity_or_cancellation(tmp_path, phase, error):
    with pytest.raises(type(error)) as caught:
        exercise(tmp_path, phase, error=error)
    assert caught.value is error


@pytest.mark.parametrize('budget_exhausted', [False, True])
def test_inconclusive_domain_results_are_not_flattened_into_physical_tier_refusal(tmp_path, budget_exhausted):
    receipt = {'connected': False, 'search_inconclusive': True, 'outcome': 'inconclusive',
               'budget_exhausted': budget_exhausted, 'retryable': False,
               'operation_failure': failure('operation_budget_exhausted' if budget_exhausted
                                            else 'worker_failed').failure_evidence}
    report = {'accepted': False, 'incomplete_nets': ['POWER'], 'authority_open': ['POWER'],
              'current_width': {'ok': False, 'detail': 'measured open domain'},
              'domain_attempts': {'POWER': {'fast': receipt, 'exact': None}}}
    original = copy.deepcopy(report)
    result, _called, sanitize = exercise(tmp_path, 'compile', report=report)
    assert result['outcome'] == 'inconclusive' and result['budget_exhausted'] is budget_exhausted
    assert result['status'] == ('deferred_budget' if budget_exhausted else 'worker_failed')
    assert result['operation_failure']['domain_attempts']['POWER'] == receipt
    assert result['blocker_evidence']['domain_attempts'] == report['domain_attempts']
    assert result['blocker_evidence']['current_width'] == report['current_width']
    assert result['failure_artifact'] is None
    assert report == original
    assert sanitize.call_args.args[0] is None


@pytest.mark.parametrize('earlier_interruption', [False, True])
def test_completed_physical_refusal_retains_existing_admission_evidence(tmp_path, earlier_interruption):
    fast = {'connected': False}
    if earlier_interruption:
        fast.update(search_inconclusive=True, budget_exhausted=True)
    report = {'accepted': False, 'incomplete_nets': ['POWER'], 'authority_open': ['POWER'],
              'current_width': {'ok': False, 'detail': 'native width failed'},
              'domain_attempts': {'POWER': {'fast': fast,
                                  'exact': {'connected': True} if earlier_interruption else None}}}
    result, _called, _sanitize = exercise(tmp_path, 'compile', report=report)
    assert not result['gate']
    assert not result.get('search_inconclusive')
    assert 'operation_failure' not in result
    assert 'pre-pour priority current-domain tier refused' in result['error']
    assert result['blocker_evidence']['current_width'] == report['current_width']


def test_independently_certified_prefix_success_is_not_reclassified(tmp_path):
    report = {'accepted': True, 'completed_nets': ['POWER'],
              'domain_attempts': {'POWER': {'fast': {'search_inconclusive': True,
                                                    'budget_exhausted': True},
                                          'exact': {'connected': True}}}}
    result, called, sanitize = exercise(tmp_path, 'compile', report=report)
    assert result['passed'] and result['priority_current_route']['accepted']
    assert result['route_input'].endswith('pre-pour-priority-current-route.kicad_pcb')
    assert result['stage_trace'][-1]['status'] == 'passed'
    called.assert_called_once()
    sanitize.assert_not_called()


def test_qualified_prefix_still_skips_late_prune(tmp_path):
    result, called, sanitize = exercise(tmp_path, 'prune', route_nets=())
    assert result['passed']
    called.assert_not_called()
    sanitize.assert_not_called()
