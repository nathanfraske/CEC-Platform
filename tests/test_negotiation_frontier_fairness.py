"""Ranked nets retain a real chance before repeated windows consume a lease."""
import pytest
import cec_certificate_repair as repair


def windows():
    return [dict(net=n, priority=(p,), marker=m) for n, p, m in [
        ('crowded', -2, 'cut-a'), ('crowded', -1, 'cut-b'),
        ('other', 0, 'other-a'), ('third', 1, 'third-a'),
        ('other', 2, 'other-b')]]


def attempt(net, completion=None):
    return dict(stage='atomic_negotiation', window={'net': net},
        phases={'close': {'completion': completion or {'closed': 0}}})


def test_cost_sort_does_not_undo_planner_round_robin():
    rows, evidence = repair._prioritize_windows_by_proven_close(windows(), {})
    assert [r['marker'] for r in rows] == ['cut-a', 'other-a', 'third-a', 'cut-b', 'other-b']
    assert evidence['window_schedule'] == 'history_ranked_net_round_robin'
    assert sorted(r['marker'] for r in rows) == sorted(r['marker'] for r in windows())


def test_round_trip_in_actual_resume_payload_preserves_cost_only():
    first = repair.route_search_history({}, [attempt('crowded'), attempt('crowded')])
    payload = {'final_residual': {'fresh': True}, 'route_search_history': first}
    second = repair.route_search_history(payload, [attempt('other')])
    rows, evidence = repair._prioritize_windows_by_proven_close(windows(), {'route_search_history': second})
    assert [r['net'] for r in rows[:3]] == ['third', 'other', 'crowded']
    assert evidence['negotiation_visits'] == {'crowded': 2, 'other': 1}
    assert evidence['exhausted_nets'] == evidence['timed_out_nets'] == []
    assert second['release_authority'] is False


def test_worker_startup_failure_is_not_counted_as_an_attempt():
    report = repair.route_search_history({}, [
        dict(stage='atomic_negotiation', window={'net': 'unused'}, decision='worker_error'),
        attempt('sampled', {'timed_out': True})])
    assert report['negotiation_visits'] == {'sampled': 1}


def test_old_revision_cost_cannot_suppress_new_frontier():
    report = repair.route_search_history({'route_search_history': {
        'algorithm_revision': 'old', 'negotiation_visits': {'crowded': 100}}})
    assert report['negotiation_visits'] == {}


@pytest.mark.parametrize('bad', [None, [], 'bad', {'a': '1', 'b': True, 'c': -1}])
def test_malformed_history_is_not_authority(bad):
    report = repair.route_search_history({'route_search_history': {
        'algorithm_revision': repair.REPAIR_ALGORITHM_REVISION, 'negotiation_visits': bad}})
    assert report['negotiation_visits'] == {}


def test_attempt_counts_and_storage_are_bounded():
    report = repair.route_search_history({}, [attempt(str(i)) for i in range(400)])
    assert len(report['negotiation_visits']) == 256
    report = repair.route_search_history({'route_search_history': {
        'algorithm_revision': repair.REPAIR_ALGORITHM_REVISION,
        'negotiation_visits': {'repeated': 10**30}}}, [attempt('repeated')])
    assert report['negotiation_visits']['repeated'] == 1000000


def test_proven_close_priority_does_not_starve_first_windows_of_peers():
    prior = dict(algorithm_revision=repair.REPAIR_ALGORITHM_REVISION,
                attempts=[attempt('crowded', {'closed': 1})])
    rows, _ = repair._prioritize_windows_by_proven_close(windows(), prior)
    assert [r['net'] for r in rows[:3]] == ['crowded', 'other', 'third']
