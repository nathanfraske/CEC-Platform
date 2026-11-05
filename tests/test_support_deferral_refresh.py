"""Fresh routing evidence, not stale promises, orders bounded support work."""
from copy import deepcopy
import inspect
import pytest
import cec_certificate_repair as repair


class Effort:
    stop_reason = None

    def available(self, _stage):
        return self.stop_reason is None


def target(ref='X1', net='/SUPPLY', x=17):
    return dict(ref=ref, target_net=net, endpoint_x_mm=x)


def run(monkeypatch, *, initial=None, fresh=None, negotiation=None,
        adopted=False, stop=False, prior=None, limits=None, prior_refresh=None):
    old = target(x=1)
    initial = initial if initial is not None else dict(
        support_schedule=dict(deferred=[old]), sweep=dict(attempts=[]))
    fresh = fresh if fresh is not None else dict(targets=[target()])
    negotiation = negotiation if negotiation is not None else dict(windows=[])
    snapshot = deepcopy((initial, fresh, negotiation))
    calls = []

    def plan(worker, args):
        assert worker is repair._footprint_plan_worker
        assert args == ('current-board', {'fresh': True}, 4)
        return deepcopy(fresh)

    def move(board, before, row, **kwargs):
        calls.append((board, before, deepcopy(row), kwargs))
        attempt = dict(stage='footprint_relocation', target=row,
                       accepted=adopted, decision='measured')
        return dict(adopted=adopted, accepted=attempt,
                    after=dict(drc=0, unconnected=2), attempts=[attempt],
                    stop='measured_no_improvement')

    monkeypatch.setattr(repair, '_spawn_apply', plan)
    monkeypatch.setattr(repair, '_attempt_footprint_relocation', move)
    effort = Effort()
    if stop: effort.stop_reason = 'wall_budget'
    report = {}
    result = repair._refresh_deferred_supports(
        'current-board', dict(drc=0, unconnected=3), initial, {'fresh': True},
        negotiation, report=report, work_dir='private-trials', effort=effort,
        prior_report=prior, skip_candidate_keys={('X1', 180, 0, 0)},
        generated_locked_uuids={'generated-only'}, support_limits=limits,
        prior_refresh=prior_refresh, token_prefix='post-negotiate-refresh')
    assert result is report and not report['release_authority']
    assert (initial, fresh, negotiation) == snapshot
    return report, calls


@pytest.mark.parametrize('names', [('X1','/SUPPLY'), ('RENAMED_C42','/OTHER')])
def test_disappeared_window_uses_fresh_geometry_and_same_transaction(monkeypatch, names):
    ref, net = names
    limits = {'max_refs': 1, 'max_shift_mm': 2.5}
    report, calls = run(monkeypatch,
        initial=dict(support_schedule=dict(deferred=[target(ref,net,x=1)])),
        fresh=dict(targets=[target(ref,net,x=103)]), limits=limits,
        negotiation=dict(windows=[dict(net='/UNRELATED')]))
    assert len(calls) == 1 and calls[0][2]['endpoint_x_mm'] == 103
    args = calls[0][3]
    assert args['support_limits'] is limits
    assert args['generated_locked_uuids'] == {'generated-only'}
    assert args['skip_candidate_keys'] == {('X1', 180, 0, 0)}
    assert args['max_candidates'] == 2
    assert report['sweep']['attempts'] and not report['adopted']


@pytest.mark.parametrize('negotiation', [{}, {'windows': [], 'skipped': 'wall_budget'},
                                       {'windows': [], 'error': 'worker_failed'}])
def test_unavailable_fresh_planner_is_not_an_empty_window_proof(monkeypatch, negotiation):
    report, calls = run(monkeypatch, negotiation=negotiation)
    assert not calls and report['stop'] == 'fresh_negotiation_unavailable'


def test_same_net_windows_still_precede_support_motion(monkeypatch):
    report, calls = run(monkeypatch, negotiation=dict(windows=[dict(net='/SUPPLY')]))
    assert not calls and report['support_schedule']['deferred']


def test_changed_target_identity_cannot_be_resurrected(monkeypatch):
    for rows in ([], [target('UNRELATED')], [target(net='/CHANGED')]):
        report, calls = run(monkeypatch, fresh=dict(targets=rows))
        assert not calls and report['stop'] == 'no_newly_eligible_support'


def test_already_tried_support_is_not_repeated_within_slice(monkeypatch):
    initial = dict(support_schedule=dict(deferred=[target()]),
                   sweep=dict(attempts=[dict(target=target())]))
    report, calls = run(monkeypatch, initial=initial)
    assert not calls and report['stop'] == 'no_deferred_support'


def test_no_budget_no_motion(monkeypatch):
    report, calls = run(monkeypatch, stop=True)
    assert not calls and report['stop'] == 'effort_budget'


@pytest.mark.parametrize('adopted', [False, True])
def test_finite_breadth_and_first_adoption_stop(monkeypatch, adopted):
    rows = [target('X'+str(i)) for i in range(4)]
    report, calls = run(monkeypatch, adopted=adopted,
        initial=dict(support_schedule=dict(deferred=rows)), fresh=dict(targets=rows))
    assert len(calls) == (1 if adopted else 2)
    assert len(report['sweep']['targets']) == 2
    if adopted:
        assert report['after']['unconnected'] == 2
        assert report['stop'] == 'accepted_one_remeasure_required'


def test_refresh_keeps_native_gate_and_remeasure_in_coordinator():
    source = inspect.getsource(repair.repair_board)
    fresh = source.index('plan["fresh_negotiation"] = fresh_negotiation_plan')
    refresh = source.index('_refresh_deferred_supports(', fresh)
    assert fresh < refresh < source.index('for window_index, window_row in enumerate(', refresh)
    assert "fresh_negotiation_plan['skipped'] = 'support_remeasure_required'" in source
    assert "effort.stop_reason = 'placement_slice_complete'" in source


def test_current_wave_measured_timeout_releases_support_without_new_wave(monkeypatch):
    attempts = [dict(stage='atomic_negotiation', window=dict(net='/SUPPLY'),
        decision='blocked_net_search_timeout',
        phases=dict(close=dict(completion=dict(closed=0, timed_out=True))))]
    history = repair.route_search_history(None, attempts,
        negotiation_stop='no_admissible_negotiation')
    report, calls = run(monkeypatch, negotiation=dict(windows=[dict(net='/SUPPLY')]),
        prior=dict(route_search_history=history))
    assert len(calls) == 1
    assert calls[0][3]['token'] == 'post-negotiate-refresh-00'
    assert calls[0][3]['max_candidates'] == 2
    assert not report['release_authority']


def test_worker_error_does_not_become_measured_ordering_evidence(monkeypatch):
    attempts = [dict(stage='atomic_negotiation', window=dict(net='/SUPPLY'),
        decision='worker_error')]
    history = repair.route_search_history(None, attempts,
        negotiation_stop='no_admissible_negotiation')
    report, calls = run(monkeypatch, negotiation=dict(windows=[dict(net='/SUPPLY')]),
        prior=dict(route_search_history=history))
    assert not calls and report['support_schedule']['deferred']


@pytest.mark.parametrize('already_tried', [1, 2])
def test_two_refreshes_share_target_budget_and_never_retry_target(monkeypatch, already_tried):
    targets = [target('PART'+str(i)) for i in range(4)]
    prior_refresh = dict(sweep=dict(attempts=[dict(target=row)
        for row in targets[:already_tried]]))
    report, calls = run(monkeypatch,
        initial=dict(support_schedule=dict(deferred=targets)),
        fresh=dict(targets=targets), prior_refresh=prior_refresh)
    assert len(calls) == 2-already_tried
    if calls:
        assert calls[0][2]['ref'] == targets[already_tried]['ref']
    else:
        assert report['stop'] == 'shared_support_refresh_budget'


def test_final_refresh_uses_new_native_ledger_and_current_attempts_only():
    source = inspect.getsource(repair.repair_board)
    ledger = source.index('post_route_refusal_evidence = _repair_attempt_completion_payload')
    after = source.index("plan['post_negotiation_support_refresh']", ledger)
    assert source.index('negotiation_attempt_offset = len(attempts)') < ledger < after
    assert 'attempts[negotiation_attempt_offset:]' in source[ledger:after]
    assert 'support_windows = _spawn_apply(_negotiation_plan_worker,' in source[ledger:after]
    assert "prior_refresh=refreshed_support, token_prefix='post-negotiate-refresh'" in source[after:]
    assert "effort.stop_stage = 'post_negotiation_support_refresh'" in source[after:]
