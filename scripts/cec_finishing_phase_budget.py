"""Explicit finite review-chain work scope, never copper or gate authority.

The ordinary four-phase default is unchanged. A caller may explicitly select
up to eight independently received phases for a longer finishing transaction.
Every leaf receiver and the whole ORIGINAL parent must still pass; changing
this cardinality grants no longer leaf deadline, weaker physics or new role.
"""
DEFAULT_LIMIT = 4
MAX_LIMIT = 8


def require_count(phases, *, limit=DEFAULT_LIMIT, allow_empty=False):
    if (type(limit) is not int or not 1 <= limit <= MAX_LIMIT
            or type(allow_empty) is not bool
            or type(phases) not in (list, tuple)
            or not (0 if allow_empty else 1) <= len(phases) <= limit):
        raise ValueError('explicit_finite_finishing_phase_work_scope_required')
    return dict(explicit_phase_limit=limit, actual_phase_count=len(phases),
        default_limit_unchanged=DEFAULT_LIMIT,
        independent_leaf_deadlines_unchanged=True,
        whole_original_parent_receiving_required=True,
        no_copper_current_or_release_authority=True)
