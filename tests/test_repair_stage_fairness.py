"""Early via probes cannot exhaust or poison the residual-route portfolio."""
from dataclasses import asdict
from unittest.mock import patch
import pytest
import cec_certificate_repair as repair


def test_stage_deadline_is_capped_and_restored_even_on_failure():
    parent = repair._WORKER_DEADLINE.set(1000.0)
    seen = []
    def probe(*args, **kwargs):
        seen.append(repair._WORKER_DEADLINE.get())
        raise RuntimeError('synthetic worker failure')
    try:
        with patch.object(repair.time, 'monotonic', return_value=100.0), \
                patch.object(repair, '_attempt_congestion_via_relocation_impl', side_effect=probe):
            with pytest.raises(RuntimeError):
                repair._attempt_congestion_via_relocation(
                    'unused', {}, {}, work_dir='unused', token='synthetic', stage_budget_s=60)
        assert seen == [160.0]
        assert repair._WORKER_DEADLINE.get() == 1000.0
    finally:
        repair._WORKER_DEADLINE.reset(parent)


def test_repeated_timeout_stops_locally_preserving_later_stage_budget():
    target = repair.ViaRepairTarget(uuid='arbitrary', net='/arbitrary', x_nm=0, y_nm=0,
        diameter_nm=600000, drill_nm=300000, counterpart_uuids=(), drc_types=(),
        away_dx=1, away_dy=0, priority=())
    row = {'via': asdict(target), 'target_net': '/other'}
    budget = repair.RepairEffortBudget(wall_budget_s=240)
    calls = []
    def worker(function, args, **kwargs):
        calls.append(function.__name__)
        if function is repair._relocate_via_worker:
            return True, {'changed': True}
        assert function is repair._certified_via_target_worker
        assert kwargs['timeout_s'] >= 45
        assert 0 < args[-1] < kwargs['timeout_s']
        raise repair.cec_process_pool.WorkerPoolStalled('synthetic timeout')
    with patch.object(repair, '_copy_board_family'), \
            patch.object(repair, '_spawn_apply', side_effect=worker):
        result = repair._attempt_congestion_via_relocation(
            'unused', {}, row, work_dir='unused', token='synthetic', effort=budget,
            max_candidates=8, stage_budget_s=60)
    assert not result['adopted']
    assert result['stop'] == 'repeated_via_worker_timeout'
    assert len(result['attempts']) == 2
    assert budget.stop_reason is None
    assert budget.claim('later_route_portfolio')
    assert calls.count('_certified_via_target_worker') == 2


def test_expired_phase_does_not_copy_or_claim_another_trial():
    target = repair.ViaRepairTarget(uuid='arbitrary', net='/arbitrary', x_nm=0, y_nm=0,
        diameter_nm=600000, drill_nm=300000, counterpart_uuids=(), drc_types=(),
        away_dx=1, away_dy=0, priority=())
    token = repair._WORKER_DEADLINE.set(1.0)
    budget = repair.RepairEffortBudget(wall_budget_s=240)
    try:
        with patch.object(repair, '_copy_board_family') as copy:
            result = repair._attempt_congestion_via_relocation_impl(
                'unused', {}, {'via':asdict(target)}, work_dir='unused', token='test', effort=budget)
        assert result['stop'] == 'via_stage_wall_budget'
        assert not result['attempts']
        copy.assert_not_called()
        assert budget.attempts_started == 0 and budget.stop_reason is None
    finally:
        repair._WORKER_DEADLINE.reset(token)
