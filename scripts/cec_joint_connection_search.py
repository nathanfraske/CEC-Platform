"""Bounded all-obligation routing search, not copper or release authority.

Routing a cell greedily can consume the only escape of a different terminal.
Choose a compatible candidate for EVERY source-derived obligation together.
Neither an exhausted finite menu nor a timeout is a no-route proof. A failed
transaction returns no partial selection. Native ownership, widths, vias,
Kelvin apertures, placement and saved-board receiving stay with the caller.
"""
import hashlib
import json
import math
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class RejectedSelection:
    """Run-local rejecting clause, never an acceptance or no-path witness.

    The independent constructor owns the causal scope. Every pair must name
    the exact currently selected choice in this immutable domain epoch.
    """
    domain_binding: str
    choices: tuple
    reason: str


def _binding(domains):
    return hashlib.sha256(json.dumps(domains, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def solve(domains, *, conflicts, validate_selection=None, timeout_s=10.,
          max_states=4096, max_pair_checks=100000):
    """MRV plus forward checking/backtracking over immutable finite menus.

    ``domains`` maps opaque obligation IDs to JSON candidates with unique
    ``id`` and nonnegative ``cost``. ``conflicts(a,b)`` must return bool;
    ``validate_selection`` independently checks a COMPLETE selection only.
    No board/reference/net/coordinate dispatch or mutation is performed.
    Bounds include callback time, not merely search-loop time. All results
    remain proposals, including complete compatible selections.
    """
    if (type(domains) is not dict or not 1 <= len(domains) <= 64
            or any(type(k) is not str or not k for k in domains)
            or type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10 or type(max_states) is not int
            or not 1 <= max_states <= 8192 or type(max_pair_checks) is not int
            or not 1 <= max_pair_checks <= 200000 or not callable(conflicts)
            or (validate_selection is not None and not callable(validate_selection))):
        raise ValueError('bounded_explicit_joint_connection_search_required')
    for choices in domains.values():
        if (type(choices) is not list or len(choices) > 96
                or any(type(c) is not dict or type(c.get('id')) is not str
                    or not c['id'] or type(c.get('cost')) not in (int, float)
                    or not math.isfinite(c['cost']) or c['cost'] < 0 for c in choices)
                or len({c['id'] for c in choices}) != len(choices)):
            raise ValueError('finite_unique_json_candidate_menu_required')
    initial = _binding(domains)
    started = time.monotonic(); deadline = started + timeout_s
    report = dict(schema=1, scope='bounded_all_obligation_connection_proposal',
        complete=False, selected={}, errors=[], states=0, pair_checks=0,
        complete_selections_checked=0, failure_frontier=[], no_path_proof=False,
        compatibility_visits=0, incremental_forward_domains=True,
        learned_rejections=[], learned_prefix_cuts=0,
        routing_admitted=False, release_authority=False, source_authority=False,
        domain_binding=initial)
    ordered = {key: sorted(choices, key=lambda c: (c['cost'], c['id']))
        for key, choices in domains.items()}
    cache = {}; selected = {}; failed = set(); learned = set()

    def tick():
        if time.monotonic() >= deadline:
            raise ValueError('joint_connection_deadline')

    def compatible(left_key, left, right_key, right):
        tick()
        report['compatibility_visits'] += 1
        key = tuple(sorted(((left_key, left['id']), (right_key, right['id']))))
        if key not in cache:
            if report['pair_checks'] >= max_pair_checks:
                raise ValueError('joint_connection_pair_check_budget')
            report['pair_checks'] += 1
            answer = conflicts(left, right)
            tick()
            if type(answer) is not bool:
                raise ValueError('conflict_oracle_must_be_explicit_bool')
            cache[key] = not answer
        return cache[key]

    def frontier(key):
        if len(report['failure_frontier']) < 64:
            report['failure_frontier'].append(dict(obligation=key,
                assigned={k: c['id'] for k, c in sorted(selected.items())},
                reason='finite_domain_has_no_compatible_choice'))

    def rejected_prefix():
        active=frozenset((key,choice['id'])for key,choice in selected.items())
        if any(clause<=active for clause in learned):
            report['learned_prefix_cuts']+=1
            return True
        return False

    def learn(answer):
        if (type(answer.domain_binding)is not str or answer.domain_binding!=initial or type(answer.choices)is not tuple
                or not 1<=len(answer.choices)<=len(selected)
                or type(answer.reason)is not str or not 1<=len(answer.reason)<=256
                or any(type(pair)is not tuple or len(pair)!=2
                    or any(type(v)is not str or not v for v in pair)for pair in answer.choices)):
            raise ValueError('exact_current_selection_rejection_clause_required')
        clause=frozenset(answer.choices)
        if (len(clause)!=len(answer.choices)or len({key for key,_ in clause})!=len(clause)
                or any(key not in selected or selected[key]['id']!=uid for key,uid in clause)):
            raise ValueError('rejection_clause_must_be_exact_selected_choices')
        if clause not in learned:
            if len(learned)>=256:raise ValueError('joint_rejection_clause_budget')
            learned.add(clause)
            report['learned_rejections'].append(dict(choices=sorted(clause),reason=answer.reason,
                bound_to_current_domain_epoch=True,rejecting_only=True))

    def visit(available_domains):
        tick()
        if report['states'] >= max_states:
            raise ValueError('joint_connection_state_budget')
        report['states'] += 1
        signature = tuple(sorted((k, c['id']) for k, c in selected.items()))
        if signature in failed or rejected_prefix():
            return None
        if len(selected) == len(ordered):
            report['complete_selections_checked'] += 1
            if validate_selection is not None:
                answer = validate_selection(dict(selected))
                tick()
                if type(answer)is RejectedSelection:
                    learn(answer);failed.add(signature)
                    return None
                if type(answer) is not bool:
                    raise ValueError('complete_selection_oracle_must_be_explicit_bool')
                if not answer:
                    failed.add(signature)
                    return None
            return dict(selected)
        remaining = []
        # Parent domains already satisfy every previous assignment. Do not
        # rescan their complete original menus against the whole prefix at
        # every node, even when the physical pair answer is cached. Filter
        # only by the NEW assignment; sibling branches retain their own
        # immutable parent lists. MRV, cost/id order, and all budgets stay.
        for key, choices in sorted(available_domains.items()):
            if not choices:
                frontier(key); failed.add(signature)
                return None
            remaining.append((len(choices), key, choices))
        _, key, choices = min(remaining, key=lambda row: (row[0], row[1]))
        for choice in choices:
            selected[key] = choice
            future={other:[candidate for candidate in values
                if compatible(other,candidate,key,choice)]
                for other,values in sorted(available_domains.items())if other!=key}
            answer = visit(future)
            del selected[key]
            if answer is not None:
                return answer
            # Reject a causal prefix immediately; do not visit another late
            # Ground/other-net variant that cannot alter its actual metal.
            if rejected_prefix():
                failed.add(signature)
                return None
        failed.add(signature)
        return None

    try:
        answer = visit(ordered)
        if _binding(domains) != initial:
            raise ValueError('joint_connection_input_changed')
        if answer is not None:
            report.update(complete=True, selected=answer,
                all_obligations_present=set(answer) == set(domains))
        else:
            report['errors'].append('finite_joint_candidate_menus_exhausted')
    except Exception as exc:
        # Never export partially assigned routes as a repair, even when the
        # last callback ran out of budget or modified its input packet.
        report.update(complete=False, selected={})
        report['errors'].append(type(exc).__name__ + ':' + str(exc))
    try:
        report['input_unchanged'] = _binding(domains) == initial
    except (ValueError, TypeError):
        report['input_unchanged'] = False
    if not report['input_unchanged']:
        report.update(complete=False, selected={})
    report['elapsed_s'] = round(time.monotonic() - started, 6)
    return report
