"""Certified hard pairs get effort before supports, without renewing the lease."""
import copy
from concurrent.futures import Future
from unittest import mock

import pytest

import cec_certificate_repair as repair
from test_support_budget_recovery import native_fixture


def exercise(tmp_path, monkeypatch, *, supports=24, translated=False,
             fraction=None, support_success=True, wall_s=35., cap_s=20.):
    path, target, move = native_fixture(tmp_path, translated)
    originals = move['preserved_anchors']
    move['preserved_anchors'] = [dict(originals[i % len(originals)],
        track_uuid='distinct-boundary-%d' % i) for i in range(supports)]
    clock, calls = [100.], []
    def close(board, window, **kwargs):
        allowance = kwargs['wall_timeout_s']
        assert 0 < allowance <= min(cap_s, wall_s-(clock[0]-100.))+1e-8
        role = 'target' if window.net == target['target_net'] else 'support'
        supported = any(call['role'] == 'support' for call in calls)
        calls.append(dict(role=role, allowance=allowance,
                          elapsed=clock[0]-100., endpoints=copy.deepcopy(window.endpoints)))
        if role == 'target':
            # Model a five-second hard search and a corridor occupied by
            # subsequently restored supports. This is scheduler behavior,
            # not a claimed native geometric/DRC qualification.
            clock[0] += min(5., allowance)
            ok = allowance >= 5 and not supported
            timeout = allowance < 5
            return ok, dict(refusal='certificate_pair_search_timeout' if timeout
                else 'certificate_pair_no_exact_clear_path', timed_out=timeout)
        clock[0] += min(.1, allowance)
        return support_success, dict(refusal='support_not_restored')
    monkeypatch.setattr(repair.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(repair, '_close_certificate_component_pair', close)
    monkeypatch.setattr(repair, '_save_with_reconciled_endpoint_neckdowns', lambda *_: None)
    options = {} if fraction is None else dict(target_budget_fraction=fraction)
    result = repair._exact_relocated_connections_worker(path, target, move, wall_s,
        pair_budget_cap_s=cap_s, **options)
    assert clock[0]-100. <= wall_s+1e-8
    return result, calls


@pytest.mark.parametrize('translated', [False, True])
@pytest.mark.parametrize('supports', [1, 3, 19, 24])
def test_default_target_priority_restores_all_supports(tmp_path, monkeypatch, supports, translated):
    report, calls = exercise(tmp_path, monkeypatch, supports=supports, translated=translated)
    assert calls[0]['role'] == 'target' and calls[0]['allowance'] == 20.
    assert report['target_closed']
    assert report['support_expected'] == report['support_closed'] == supports
    assert len(calls) == 1+supports
    assert not report['target_budget_recovery']['attempted']
    assert not report['budget_policy']['release_authority']


@pytest.mark.parametrize('supports', [19, 24])
def test_equal_share_ablation_misses_before_supports_occupy_corridor(tmp_path, monkeypatch, supports):
    old_dir, new_dir = tmp_path/'old', tmp_path/'new'
    old_dir.mkdir(); new_dir.mkdir()
    old, old_calls = exercise(old_dir, monkeypatch, supports=supports, fraction=0.)
    new, new_calls = exercise(new_dir, monkeypatch, supports=supports)
    assert old_calls[0]['allowance'] == 35./(supports+1)
    assert not old['target_closed'] and old['target_budget_recovery']['attempted']
    assert new['target_closed'] and new_calls[0]['allowance'] == 20.
    assert old['support_closed'] == new['support_closed'] == supports


def test_failed_support_is_still_required_even_when_target_closed(tmp_path, monkeypatch):
    report, _ = exercise(tmp_path, monkeypatch, support_success=False)
    assert report['target_closed'] and report['support_closed'] == 0
    assert report['support_expected'] == 24
    assert len([r for r in report['refused'] if r['role'] == 'support']) == 24
    assert not report['budget_policy']['release_authority']


@pytest.mark.parametrize('wall_s,cap_s', [(1.,20.), (5.,20.), (35.,3.), (120.,20.)])
def test_priority_cannot_exceed_transaction_or_pair_cap(tmp_path, monkeypatch, wall_s, cap_s):
    report, calls = exercise(tmp_path, monkeypatch, wall_s=wall_s, cap_s=cap_s)
    assert calls and all(c['allowance'] <= cap_s for c in calls)
    assert all(c['elapsed']+c['allowance'] <= wall_s+1e-8 for c in calls)


def test_target_only_does_not_reserve_time_for_absent_supports(tmp_path, monkeypatch):
    report, calls = exercise(tmp_path, monkeypatch, supports=0, wall_s=10.)
    assert calls[0]['allowance'] == 10.
    assert report['target_closed'] and report['support_expected'] == 0


@pytest.mark.parametrize('deadline,requested,expected', [(None,20.,20.), (106.,20.,6.)])
def test_timeout_names_exact_worker_and_budget_without_arguments(monkeypatch, deadline, requested, expected):
    pool = mock.Mock(); future = Future(); pool.submit.return_value = future
    monkeypatch.setattr(repair, 'ProcessPoolExecutor', lambda **_: pool)
    monkeypatch.setattr(repair.time, 'monotonic', lambda: 100.)
    monkeypatch.setattr(repair.cec_process_pool, 'watched_as_completed',
        mock.Mock(side_effect=repair.cec_process_pool.WorkerPoolStalled('native worker stalled')))
    shutdown = mock.Mock(); monkeypatch.setattr(repair.cec_process_pool, 'shutdown_process_pool', shutdown)
    token = repair._WORKER_DEADLINE.set(deadline)
    try:
        with pytest.raises(repair.cec_process_pool.WorkerPoolStalled) as caught:
            repair._spawn_apply(str, ('DO_NOT_LOG_PAYLOAD',), timeout_s=requested)
    finally:
        repair._WORKER_DEADLINE.reset(token)
    evidence = caught.value.certificate_worker_diagnostics
    assert evidence['operation'] == 'builtins.str'
    assert evidence['requested_s'] == requested and evidence['effective_s'] == expected
    assert evidence['deadline_limited'] is (deadline is not None)
    assert 'DO_NOT_LOG_PAYLOAD' not in str(caught.value)
    assert 'operation=builtins.str' in str(caught.value)
    assert future.cancelled()
    shutdown.assert_called_once_with(pool, force=True, grace_s=2.)


def test_nonbudget_native_error_keeps_original_type_and_cause(monkeypatch):
    pool = mock.Mock(); future = Future(); pool.submit.return_value = future
    monkeypatch.setattr(repair, 'ProcessPoolExecutor', lambda **_: pool)
    monkeypatch.setattr(repair.cec_process_pool, 'watched_as_completed',
        mock.Mock(side_effect=ValueError('native input invalid')))
    monkeypatch.setattr(repair.cec_process_pool, 'shutdown_process_pool', mock.Mock())
    with pytest.raises(ValueError, match='native input invalid') as caught:
        repair._spawn_apply(str, ('value',))
    assert not hasattr(caught.value, 'certificate_worker_diagnostics')
