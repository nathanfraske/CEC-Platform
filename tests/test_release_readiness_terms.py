"""Empty measurement scope must be distinguished from missing evidence."""
import pytest
from cec_release_readiness import coverage_term


def record(**updates):
    return dict(dict(status='verified', ok=True, expected=2, checked=2,
                     passed=2, failed=0, unknown=0, unresolved_inputs=0), **updates)


def test_complete_positive_scope():
    assert coverage_term(record()) is True


def test_proved_empty_scope_is_not_a_fabricated_pass_or_failure():
    assert coverage_term(record(status='not_applicable', ok=None, expected=0, checked=0, passed=0)) is None


@pytest.mark.parametrize('updates', [dict(expected=0), dict(unknown=1), dict(unresolved_inputs=1),
                                   dict(checked=1), dict(passed=1), dict(failed=1), dict(ok=False),
                                   dict(status='not_applicable'), dict(expected=True),
                                   dict(expected=-1)])
def test_partial_or_inconsistent_coverage_fails_closed(updates):
    assert coverage_term(record(**updates)) is False


def test_missing_coverage_is_not_not_applicable():
    assert coverage_term({}) is False
