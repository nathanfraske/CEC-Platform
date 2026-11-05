"""Scheduling may improve coverage, never erase a domain or swap its grid."""
import copy
import pytest
from cec_power_order import solve_prospective_batch


@pytest.mark.parametrize('names', [('A', 'B', 'C'), ('VCC_OUT', '/rail_9', 'other')])
@pytest.mark.parametrize('second_found,expected,reason', [
    ((0, 1, 2), 1, 'strict_terminal_coverage_improvement'),
    ((0, 2), 0, 'no_strict_improvement'),
    ((1, 2), 0, 'lost_solved_net')])
def test_bounded_dominance_and_grid_ownership(names, second_found, expected, reason):
    asks = [dict(net=name, layers=['F.Cu']) for name in names]
    pristine = copy.deepcopy(asks)
    calls=[]; objects=[object(), object()]
    def solve(rows, state):
        index=len(calls); calls.append([row['net'] for row in rows])
        found={names[i] for i in ((0, 2) if index == 0 else second_found)}
        # A mutable adapter cannot corrupt the caller's ask/alternate menu.
        rows[0]['layers'].append('B.Cu')
        state.update(_grid=objects[index], selected=index)
        return [dict(candidate=index)], [index], {name:dict(path_found=name in found) for name in names}
    state={'stale': True}; report={}
    result=solve_prospective_batch(asks, solve, current_priority={names[0]:2,names[2]:3},
        collect=state, report=report)
    assert calls == [list(names), [names[1], names[2], names[0]]]
    assert result[0] == [dict(candidate=expected)]
    assert state == {'_grid':objects[expected], 'selected':expected}
    assert report['selected'] == expected
    assert report['reason'] == reason
    assert report['exact_admission_required'] is True
    assert asks == pristine


@pytest.mark.parametrize('found,retries,reason', [
    (True, 1, 'all_paths_found'), (False, 1, 'no_distinct_order'), (False, 0, 'disabled')])
def test_no_duplicate_search(found, retries, reason):
    calls=[]; report={}
    def solve(rows, state):
        calls.append(1); return [], [], {'rail':dict(path_found=found)}
    solve_prospective_batch([dict(net='rail')], solve, max_retries=retries, report=report)
    assert len(calls) == 1
    assert report['reason'] == reason


@pytest.mark.parametrize('retries', [-1, 2, True, '1'])
def test_retry_budget_cannot_be_unbounded(retries):
    with pytest.raises(ValueError):
        solve_prospective_batch([], lambda *args: pytest.fail('must not run'), max_retries=retries)


def test_solver_failure_is_not_successful_partial_admission():
    calls=[]
    def solve(rows, state):
        calls.append(1)
        if len(calls)>1: raise RuntimeError('native geometry failed')
        return [], [], {'A':dict(path_found=True), 'B':dict(path_found=False)}
    with pytest.raises(RuntimeError, match='native geometry failed'):
        solve_prospective_batch([dict(net='A'),dict(net='B')], solve)
