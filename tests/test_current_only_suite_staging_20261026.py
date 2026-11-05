"""The driver stages a real strict current reduction, never a count waiver."""
import ast
from pathlib import Path

import pytest
from root_receive_local_transaction_20261022 import strict_current_repair_progress


def checker():
    path = Path(__file__).resolve().parents[1]/'build/root_prepare_parallel_suite_gates_20261026.py'
    tree = ast.parse(path.read_text())
    method, = [n for n in tree.body if isinstance(n, ast.FunctionDef)
        and n.name == 'received_physical_progress']
    scope = dict(strict_current_repair_progress=strict_current_repair_progress)
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(path), 'exec'), scope)
    return scope['received_physical_progress']


def current(before=3, after=0):
    return dict(ok=True, complete=True, errors=[], new_faults=[], worsened_faults=[],
        before_fault_objects=before, after_fault_objects=after)


def counts():
    return dict(opens=12, errors=0, warnings=157, exclusions=0)


def test_current_only_progress_is_distinct_from_native_open_closure():
    decide = checker()
    assert decide(counts(), counts(), current())
    assert not decide(counts(), counts(), current(3, 3))
    assert not decide(counts(), counts(), current(3, 4))
    assert decide(counts(), dict(counts(), opens=11), {})


@pytest.mark.parametrize('changes', [dict(ok=False), dict(ok=1), dict(complete=False),
    dict(complete=1), dict(errors=['failed']), dict(new_faults=['new']),
    dict(worsened_faults=['worse']), dict(before_fault_objects=True),
    dict(after_fault_objects=True), dict(after_fault_objects=-1)])
def test_partial_or_worsened_current_evidence_cannot_stage_equal_open_counts(changes):
    assert not checker()(counts(), counts(), dict(current(), **changes))


@pytest.mark.parametrize('changes', [dict(opens=13), dict(opens=-1), dict(opens=True),
    dict(errors=1), dict(warnings=-1), dict(exclusions=1), dict(exclusions=False)])
def test_current_repair_never_hides_native_regression_or_exclusions(changes):
    assert not checker()(counts(), dict(counts(), **changes), current())


def test_no_source_exclusion_or_empty_native_evidence_may_be_staged():
    assert not checker()(dict(counts(), exclusions=1), counts(), current())
    assert not checker()({}, counts(), current())
    assert not checker()(counts(), None, current())
