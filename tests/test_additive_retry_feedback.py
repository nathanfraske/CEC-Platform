"""Search feedback orders fresh work without becoming negative authority."""
from unittest.mock import patch

import pytest
import cec_additive_pair_repair as additive
import cec_certificate_repair as repair
import cec_final_residual as residual
from test_residual_breadth import run_portfolio


@pytest.mark.parametrize('prefix', ['', 'renamed/'])
def test_changed_geometry_keeps_retry_order_but_not_search_suppression(tmp_path, prefix):
    keys = [prefix + name for name in ('costly', 'fresh')]
    seen = []
    def attempt(_path, _before, target, **kwargs):
        seen.append(target['pair_key'])
        return dict(adopted=False, attempts=[dict(target=target,
            completion={'closed': 0}, target_budget_s=40.)], stop='target_still_refused')
    stale = dict(input_identity={'pcb': 'old'},
        algorithm_revision=repair.REPAIR_ALGORITHM_REVISION,
        sampled_pair_budgets={keys[0]: 40.})
    with patch.object(additive, 'targets', return_value=dict(targets=[
            {'pair_key': key} for key in keys], skipped=[], stop='planned')), \
         patch.object(residual, '_identity', return_value={'pcb': 'changed'}), \
         patch.object(additive, 'attempt', side_effect=attempt):
        report = additive.sweep('source', {}, {'plan': {'certified_additive': stale}},
            work_dir=tmp_path, effort=repair.RepairEffortBudget(),
            scheduling_history={keys[0]: 4}, max_targets=2)
    assert seen == [keys[1], keys[0]]  # Old failure is still eligible and retried.
    assert report['sampled_pair_budgets'] == dict.fromkeys(keys, 40.)
    assert report['scheduling_feedback']['scope'] == 'ordering_only_no_search_suppression'


def test_feedback_does_not_count_failed_process_startup_or_accept_invalid_values():
    prior = {'real': 1, 'bad-bool': True, 'bad-negative': -1, 'bad-float': 2., '': 3}
    attempts = [dict(target={'pair_key': 'not-started'}, decision='additive_worker_error'),
        dict(target={'pair_key': 'real'}, completion={'closed': 0}),
        dict(target={'pair_key': 'new'}, completion={'timed_out': True})]
    result = additive.scheduling_feedback(prior, attempts)
    assert result == {'real': 2, 'new': 1}
    assert prior['real'] == 1
    assert len(additive.scheduling_feedback({str(i): 1 for i in range(5000)}, [])) == 4096


def test_success_retains_only_ordering_feedback_across_fresh_snapshot(tmp_path):
    first = dict(adopted=True, after={'unconnected': 37, 'drc': 3},
        attempts=[dict(target={'pair_key': 'tried'}, completion={'closed': 1})])
    last = dict(adopted=False, attempts=[], stop='no_unvisited_additive_gain')
    result, packets = run_portfolio(tmp_path, [first, last])
    assert result['changed'] and result['scheduling_history'] == {'tried': 1}
    assert packets[1]['final_residual'] == {'fresh': True}
    assert 'certified_additive' not in packets[1].get('plan', {})


@pytest.mark.parametrize('invalid', [None, [], True, {'bad': False}])
def test_invalid_feedback_does_not_create_suppression(invalid):
    assert additive.scheduling_feedback(invalid, []) == {}


def test_larger_finite_round_menu_still_stops_at_exact_budget(tmp_path):
    batch = dict(adopted=False, stop='additive_stage_wall_budget', attempts=[{}])
    result, packets = run_portfolio(tmp_path, [batch] * 17, max_rounds=17)
    assert len(packets) == 17 and result['stop'] == 'round_budget'
    assert result['effort_budget']['max_attempts'] == 17 * 8
