"""Cooperative child effort shares the actual parent lease, with no renewal."""
import ast
from concurrent.futures import Future
from pathlib import Path
from unittest import mock

import pytest
import cec_certificate_repair as repair


@pytest.mark.parametrize('remaining,expected', [(None, 30.), (100., 30.),
    (16.261, 11.261), (6., 1.)])
def test_explicit_budget_argument_is_clamped_and_reserve_retained(monkeypatch, remaining, expected):
    pool = mock.Mock(); future = Future(); future.set_result({'target_closed': False})
    pool.submit.return_value = future
    monkeypatch.setattr(repair, 'ProcessPoolExecutor', lambda **_: pool)
    watch = mock.Mock(return_value=iter([future]))
    monkeypatch.setattr(repair.cec_process_pool, 'watched_as_completed', watch)
    monkeypatch.setattr(repair.cec_process_pool, 'shutdown_process_pool', mock.Mock())
    monkeypatch.setattr(repair.time, 'monotonic', lambda: 100.)
    token = repair._WORKER_DEADLINE.set(None if remaining is None else 100. + remaining)
    try:
        result = repair._spawn_apply(str, ('PRIVATE_PATH', {'unchanged': True}, (), 30.),
            timeout_s=35., search_budget_arg=3)
    finally:
        repair._WORKER_DEADLINE.reset(token)
    assert pool.submit.call_args.args[:4] == (str, 'PRIVATE_PATH', {'unchanged': True}, ())
    assert pool.submit.call_args.args[4] == pytest.approx(expected)
    budget = result['worker_budget']
    assert budget['effective_search_s'] == pytest.approx(expected)
    assert budget['finish_reserve_s'] == 5.
    assert budget['effective_worker_s'] == pytest.approx(expected + 5.)
    assert watch.call_args.kwargs['wall_timeout_s'] == budget['effective_worker_s']
    assert not budget['release_authority'] and not result['target_closed']
    assert 'PRIVATE_PATH' not in str(budget)


@pytest.mark.parametrize('remaining', [-1., 0., .05, 4.99, 5.])
def test_unfunded_search_does_not_spawn_or_become_geometric_failure(monkeypatch, remaining):
    create = mock.Mock(); monkeypatch.setattr(repair, 'ProcessPoolExecutor', create)
    monkeypatch.setattr(repair.time, 'monotonic', lambda: 100.)
    token = repair._WORKER_DEADLINE.set(100. + remaining)
    try:
        with pytest.raises(repair.cec_process_pool.WorkerPoolStalled) as caught:
            repair._spawn_apply(str, ('PRIVATE_PATH', 30.), timeout_s=35., search_budget_arg=1)
    finally:
        repair._WORKER_DEADLINE.reset(token)
    create.assert_not_called()
    data = caught.value.certificate_worker_diagnostics
    assert not data['dispatched'] and data['effective_search_s'] == 0.
    assert data['deadline_limited'] and data['operation'] == 'builtins.str'
    assert 'PRIVATE_PATH' not in str(caught.value)


@pytest.mark.parametrize('args,outer,index', [
    ((30.,), 35., True), ((30.,), 35., -1), ((30.,), 35., 1),
    ((30.,), None, 0), ((30.,), 30., 0), ((30.,), 29., 0),
    ((30.,), float('inf'), 0), ((30.,), float('nan'), 0), ((.5,), True, 0),
    ((0.,), 35., 0), ((float('inf'),), 35., 0),
    ((float('nan'),), 35., 0), ((True,), 35., 0), (('30',), 35., 0),
])
def test_bad_budget_contract_is_rejected_without_spawning(monkeypatch, args, outer, index):
    create = mock.Mock(); monkeypatch.setattr(repair, 'ProcessPoolExecutor', create)
    with pytest.raises(ValueError, match='cooperative search'):
        repair._spawn_apply(str, args, timeout_s=outer, search_budget_arg=index)
    create.assert_not_called()


def test_unregistered_argument_is_not_guessed(monkeypatch):
    pool = mock.Mock(); future = Future(); future.set_result({'unchanged': True})
    pool.submit.return_value = future
    monkeypatch.setattr(repair, 'ProcessPoolExecutor', lambda **_: pool)
    monkeypatch.setattr(repair.cec_process_pool, 'watched_as_completed', lambda *_a, **_k: [future])
    monkeypatch.setattr(repair.cec_process_pool, 'shutdown_process_pool', mock.Mock())
    monkeypatch.setattr(repair.time, 'monotonic', lambda: 100.)
    token = repair._WORKER_DEADLINE.set(106.)
    try:
        result = repair._spawn_apply(str, (30.,), timeout_s=35.)
    finally:
        repair._WORKER_DEADLINE.reset(token)
    assert pool.submit.call_args.args == (str, 30.)
    assert result == {'unchanged': True}


def test_every_production_relocated_reconnect_declares_its_budget():
    tree = ast.parse(Path(repair.__file__).read_text())
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Name) and node.func.id == '_spawn_apply'
             and node.args and isinstance(node.args[0], ast.Name)
             and node.args[0].id == '_exact_relocated_connections_worker']
    assert len(calls) >= 7
    for call in calls:
        values = {item.arg: item.value for item in call.keywords}
        assert ast.literal_eval(values['search_budget_arg']) == 3


@pytest.mark.parametrize('envelope', ['exact_reconnect', 'exact_reconnect_after_route_evacuation',
    'target_completion', 'target_endpoint_access', 'target_endpoint_retreat',
    'route_certificate_via_clearance', 'placement_route_order_negotiation'])
def test_parent_clipped_native_result_cannot_poison_pose_history(tmp_path, envelope):
    import cec_route_pose_history as poses
    from test_route_pose_history import measured, nested, pose_key, source, scoped
    row = measured(); row['decision'] = 'target_still_refused'
    row['placement_preflight']['accepted'] = True
    result = dict(target_closed=False, support_closed=13, support_expected=19,
        worker_budget=dict(parent_deadline_limited=True, effective_search_s=11.261),
        refused=[dict(role='support', refusal='relocated_pair_budget_exhausted')])
    row[envelope] = result if envelope in ('exact_reconnect', 'exact_reconnect_after_route_evacuation',
        'target_completion') else dict(attempts=[dict(exact_reconnect=result)])
    found, retry = poses.measured_keys(nested(row))
    assert not found and pose_key(row) in retry
    board = source(tmp_path); scope = scoped(board)
    prior = dict(scope=scope, rejected_keys=[pose_key(row)])
    assert not poses.merge(prior, current_scope=scope, plan=nested(row))['rejected_keys']


def test_full_worker_lease_remains_a_scoped_measurement():
    import cec_route_pose_history as poses
    from test_route_pose_history import measured, nested, pose_key
    row = measured(); row['decision'] = 'target_still_refused'
    row['exact_reconnect'] = dict(worker_budget=dict(parent_deadline_limited=False))
    assert poses.measured_keys(nested(row)) == ({pose_key(row)}, set())


def test_unrelated_large_diagnostic_payload_cannot_invent_budget_clipping():
    import cec_route_pose_history as poses
    from test_route_pose_history import measured, nested, pose_key
    row = measured()
    row['exact_reconnect'] = dict(details=[dict(worker_budget=dict(parent_deadline_limited=True))] * 25000)
    assert poses.measured_keys(nested(row)) == ({pose_key(row)}, set())


def test_incomplete_execution_walk_remains_retryable():
    import cec_route_pose_history as poses
    from test_route_pose_history import measured, nested, pose_key
    row = measured(); row['target_endpoint_access'] = dict(attempts=[{}] * 4097)
    physical = poses.physical_key(row['target'], row['candidate'], row['search_context'])
    assert poses.measured_keys(nested(row)) == (set(), {pose_key(row), physical})
