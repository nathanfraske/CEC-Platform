"""Scoped deterministic search work limits with independent wall-clock guards.

One unit is a candidate/queue expansion checkpoint, not a geometric limit.
Nested searches share their caller's budget; thread/task context is restored
even on failure. Exhaustion means unproved, never an impossible connection.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import time

_ACTIVE = ContextVar('cec_search_work_budgets', default=())


@dataclass
class WorkBudget:
    limit: int
    used: int = 0
    stop_reason: str | None = None

    def __post_init__(self):
        if isinstance(self.limit, bool) or not isinstance(self.limit, int) or not 1 <= self.limit <= 1_000_000:
            raise ValueError('search step limit must be an integer in 1..1000000')

    def report(self):
        return {'work_limit': self.limit, 'work_used': self.used,
                'stop_reason': self.stop_reason,
                'budget_exhausted': self.stop_reason is not None,
                'exhaustion_is_no_path_proof': False}


@contextmanager
def scoped(limit):
    budget = WorkBudget(limit)
    token = _ACTIVE.set(_ACTIVE.get() + (budget,))
    try:
        yield budget
    finally:
        _ACTIVE.reset(token)


def exhausted(deadline_monotonic=None):
    """Consume one deterministic work unit, or honor an emergency deadline.

    Outside a scoped search this has the former wall-deadline behavior.
    """
    budgets = _ACTIVE.get()
    if any(b.stop_reason is not None for b in budgets):
        return True
    if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
        for budget in budgets:
            budget.stop_reason = 'wall_deadline'
        return True
    if any(b.used >= b.limit for b in budgets):
        for budget in budgets:
            if budget.used >= budget.limit:
                budget.stop_reason = 'work_limit'
        return True
    for budget in budgets:
        budget.used += 1
    return False


def stop_status():
    """Poll a latched/exactly consumed scope without spending another unit.

    Outer coordinators must stop too: a lower-level work refusal is not proof
    of an impossible route and must not trigger thousands of futile retries.
    No active scope means no change to legacy wall-clock-only callers.
    """
    budgets = _ACTIVE.get()
    for budget in budgets:
        if budget.stop_reason is None and budget.used >= budget.limit:
            budget.stop_reason = 'work_limit'
    if not any(budget.stop_reason is not None for budget in budgets):
        return None
    return {'budgets': [budget.report() for budget in budgets],
            'exhaustion_is_no_path_proof': False}
