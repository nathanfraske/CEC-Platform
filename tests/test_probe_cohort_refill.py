"""Fixed-share scheduling reuses actual spare time, never weakens probe effort."""
from unittest.mock import patch

import pytest

import cec_operation_budget as budget


def allocation(share=555., workers=2, cost=245.):
    return dict(workers=workers, allocated_s=share, estimated_batch_s=cost,
                reserve_s=60., per_pair_timeout_s=120., admitted_jobs=4)


def execute(durations, *, alloc=None, count=7, fail=False, malformed=False, env=None):
    now = [0.]
    batches = []
    def run(rows):
        batches.append([row['slot'] for row in rows])
        assert all(row['pair_timeout_s'] == 120 for row in rows)
        now[0] += durations[len(batches)-1]
        if fail:
            raise RuntimeError('native worker unavailable')
        result = [dict(slot=row['slot'], pair_report={'ok':False}) for row in reversed(rows)]
        return result[:-1] if malformed else result
    with patch.object(budget.time, 'time', side_effect=lambda: now[0]):
        result, schedule = budget.run_probe_cohorts(
            [dict(slot=n, pair_timeout_s=120) for n in range(count)],
            allocation() if alloc is None else alloc, run,
            clock=lambda: now[0], env={} if env is None else env)
    return batches, result, schedule


def test_fast_native_probes_refill_without_renewing_the_share():
    batches, result, schedule = execute([90., 80., 20.])
    assert batches == [[0,1,2,3], [4,5], [6]]
    assert sorted(row['slot'] for row in result) == list(range(7))
    assert schedule['initial_admitted_jobs'] == 4
    assert schedule['dispatched_slots'] == list(range(7))
    assert schedule['deferred_slots'] == []
    assert schedule['initial_share_s'] == 555 and schedule['elapsed_s'] == 190
    assert [row['remaining_share_s'] for row in schedule['cohorts']] == [555,465,385]
    assert not schedule['release_authority']


def test_full_cost_probes_leave_unfunded_jobs_deferred():
    batches, result, schedule = execute([490.])
    assert batches == [[0,1,2,3]]
    assert len(result) == 4 and schedule['deferred_slots'] == [4,5,6]
    assert schedule['stop'] == 'insufficient_complete_probe_budget'


def test_parent_finalist_reserve_can_reduce_but_never_increase_share():
    batches, _, schedule = execute([245.], env={'CEC_OPERATION_DEADLINE_EPOCH':'400'})
    assert batches == [[0,1]] and schedule['deferred_slots'] == [2,3,4,5,6]
    assert schedule['cohorts'][0]['remaining_share_s'] == 340


@pytest.mark.parametrize('fail,malformed', [(True,False), (False,True)])
def test_bad_worker_batch_is_not_replayed_or_followed_with_more_jobs(fail,malformed):
    batches, result, schedule = execute([1.], fail=fail, malformed=malformed)
    assert batches == [[0,1,2,3]]
    assert all(row['pair_report'] is None and row['error'] for row in result)
    assert schedule['deferred_slots'] == [4,5,6]
    assert schedule['stop'] == 'probe_worker_failure_no_retry'


def test_single_worker_uses_same_fixed_share_and_exact_order():
    batches, _, schedule = execute([10.,10.], alloc=allocation(share=75, workers=1, cost=25), count=4)
    assert batches == [[0,1,2], [3]] and not schedule['deferred_slots']


def test_no_deadline_still_has_a_finite_number_of_unique_jobs():
    batches, _, schedule = execute([1.], alloc=allocation(share=None))
    assert batches == [list(range(7))] and schedule['deferred_slots'] == []


def test_no_funded_probe_is_not_dispatched():
    unfunded = allocation(share=20)
    unfunded['per_pair_timeout_s'] = None
    batches, result, schedule = execute([], alloc=unfunded)
    assert not batches and not result and len(schedule['deferred_slots']) == 7


@pytest.mark.parametrize('bad', [dict(workers=0), dict(estimated_batch_s=0),
                              dict(allocated_s=float('nan'))])
def test_invalid_allocation_fails_closed(bad):
    value = allocation()
    value.update(bad)
    with pytest.raises(ValueError):
        execute([], alloc=value)


def test_duplicate_jobs_cannot_be_launched_twice():
    with pytest.raises(ValueError, match='duplicate'):
        budget.run_probe_cohorts([dict(slot=1),dict(slot=1)], allocation(), lambda rows: rows)


def test_outer_journal_retains_dispatch_and_deferred_evidence():
    import cec_full_pipeline as pipeline
    _, _, schedule = execute([490.])
    deferred = [dict(move_index=9, proof_complete=False)]
    funding = dict(minimum_remaining_s=305, minimum_budget_shortfall_s=208)
    compact = pipeline._compact_priority_repair_round_history(dict(rounds=[dict(
        pair_probe_schedule=schedule, pair_probe_deferred=deferred,
        pair_probe_budget=funding)]))[0]
    assert compact['pair_probe_schedule'] == schedule
    assert compact['pair_probe_deferred'] == deferred
    assert compact['pair_probe_budget'] == funding


@pytest.mark.parametrize('setup_s', [.000001, .1, 4.9, 5.])
def test_exactly_funded_cohort_spends_setup_allowance_once(setup_s):
    now = [100.]
    batches = []
    with patch.object(budget.time, 'time', side_effect=lambda: now[0]), \
            patch.object(budget.time, 'monotonic', side_effect=lambda: now[0]):
        env = {'CEC_OPERATION_DEADLINE_EPOCH':'405'}
        alloc = budget.probe_allocation(120, 4, 2, 2, fraction=.01, env=env)
        assert alloc['minimum_batch_funded'] and alloc['allocated_s'] == 245
        now[0] += setup_s
        def run(rows):
            batches.append([r['slot'] for r in rows])
            # Consume only the still-reserved solver/remaining setup time.
            now[0] += 245-setup_s
            return [dict(slot=r['slot'], pair_report={'ok':False}) for r in rows]
        _, schedule = budget.run_probe_cohorts(
            [dict(slot=n) for n in range(4)], alloc, run, env=env)
    assert batches == [[0,1]]
    assert schedule['deferred_slots'] == [2,3]
    cohort = schedule['cohorts'][0]
    assert cohort['setup_already_spent_s'] == pytest.approx(setup_s)
    assert cohort['estimated_remaining_s'] <= cohort['remaining_share_s'] + 1e-9
    assert now[0] == 345  # untouched 60-second finalist reserve


@pytest.mark.parametrize('setup_s', [5.001, 30., 246.])
def test_slow_pool_setup_cannot_renew_a_precisely_funded_share(setup_s):
    now = [100.]
    with patch.object(budget.time, 'time', side_effect=lambda: now[0]), \
            patch.object(budget.time, 'monotonic', side_effect=lambda: now[0]):
        # The distant parent has ample time, but the fixed probe share does not.
        alloc = budget.probe_allocation(120, 4, 2, 2, fraction=.01,
            env={'CEC_OPERATION_DEADLINE_EPOCH':'1000'})
        now[0] += setup_s
        _, schedule = budget.run_probe_cohorts([dict(slot=n) for n in range(4)],
            alloc, lambda _: pytest.fail('expired probe lease dispatched'), env={})
    assert schedule['dispatched_slots'] == []


def test_parent_shortening_cannot_be_paid_from_setup_credit():
    now = [100.]
    with patch.object(budget.time, 'time', side_effect=lambda: now[0]), \
            patch.object(budget.time, 'monotonic', side_effect=lambda: now[0]):
        alloc = budget.probe_allocation(120, 2, 2, 2,
            env={'CEC_OPERATION_DEADLINE_EPOCH':'405'}, fraction=.01)
        now[0] += 1
        _, schedule = budget.run_probe_cohorts([dict(slot=0)], alloc,
            lambda _: pytest.fail('full solver effort no longer funded'),
            env={'CEC_OPERATION_DEADLINE_EPOCH':'403'})
    assert not schedule['dispatched_slots']


def test_incompatible_parent_budget_reports_required_effort_without_reducing_it():
    with patch.object(budget.time, 'time', return_value=100):
        alloc = budget.probe_allocation(120, 9, 2, 2,
            env={'CEC_OPERATION_DEADLINE_EPOCH':'196.86465191841125'})
    assert alloc['minimum_remaining_s'] == 305
    assert alloc['minimum_budget_shortfall_s'] == pytest.approx(208.13534808158875)
    assert alloc['per_pair_timeout_s'] is None
    assert alloc['requested_per_pair_s'] == 120
