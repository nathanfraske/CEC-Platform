"""Bounded local-return recovery at the exact-power dependency boundary.

This never replans power. It reuses the ordinary craft solver inside the
existing frozen-placement domain and requires fresh native admission before
returning a changed private trial to its caller's complete priority gate.
"""
import copy
from pathlib import Path
import tempfile


def eligibility(physical):
    from cec_local_return_feedback import failed_searches
    from cec_full_pipeline import _placement_craft_failures

    physical = physical or {}
    if (physical.get('craft_gate') or {}).get('ok') is not False:
        return dict(ok=False, reason='craft_not_blocked')
    if not all((physical.get(term) or {}).get('ok') is True for term in
               ('pads_in_bounds', 'courtyards', 'constraint_gate')):
        return dict(ok=False, reason='other_physical_gate_unproven')
    craft = physical.get('craft') or {}
    # Integrity errors and unknown failed checkers cannot become a repair
    # permission. Only the existing decoupler solver owns this boundary.
    if set(_placement_craft_failures(craft)) != {'decoupler'}:
        return dict(ok=False, reason='other_craft_failure')
    count = sum(bool(failed_searches(row)) for row in
                (craft.get('decoupler') or {}).get('details') or ())
    return dict(ok=bool(count), failed_return_cells=count,
                reason=('exhausted_local_return_after_authority' if count
                        else 'no_structured_return_failure'))


def recover(cfg, board, physical, *, max_trials=16, allow_authored_prefix=False):
    """One finite repair; rollback the complete family unless every gate closes."""
    import cec_full_pipeline as pipeline
    import cec_synth_pipeline as synth
    import cec_frozen_placement_domain as frozen

    permitted = eligibility(physical)
    result = dict(schema=1, applicable=permitted['ok'], changed=False,
                  one_shot=True, release_authority=False, eligibility=permitted)
    if not permitted['ok']:
        return dict(result, ok=False, reason=permitted['reason']), physical
    if (isinstance(max_trials, bool) or not isinstance(max_trials, int)
            or not 1 <= max_trials <= 64):
        raise ValueError('post-authority return trials must be an integer in 1..64')
    board = Path(board).resolve()
    local = copy.deepcopy(cfg)
    candidate = synth.placement_candidate_from_board(
        local, str(board), allow_routed=allow_authored_prefix)
    candidate.frozen_placement_contract = frozen.bind(board, candidate)
    positions = copy.deepcopy(candidate.P)
    accepted = False
    with tempfile.TemporaryDirectory(prefix='cec-post-authority-return-') as scratch:
        pipeline._snapshot_placement_authority(board, scratch)
        try:
            candidate, repair = synth.repair_placement_craft_epochs(
                local, candidate, max_trials=max_trials, rounds=1, epochs=1,
                initial_evidence=physical['craft'])
            commit = pipeline._commit_frozen_craft_repair(local, candidate, board, repair)
            result.update(repair=commit, trials_limit=max_trials,
                          reason='bounded_repair_did_not_close')
            if not commit.get('changed'):
                return dict(result, ok=False), physical
            local, binding = synth.config_with_board_route_authority(local, str(board))
            result['authority_binding'] = binding
            if not binding.get('ok') or not binding.get('bound'):
                return dict(result, ok=False, reason='recovered_authority_unbound'), physical
            exact = pipeline._exact_admit_placement_route_authority(
                local, board, Path(binding['state']))
            result['exact_admission'] = exact
            if not exact.get('ok'):
                return dict(result, ok=False, reason='recovered_authority_refused'), physical
            after = pipeline._measure_placement_physical(local, board)
            result['after_gates'] = {key: after.get(key) for key in
                ('pads_in_bounds', 'courtyards', 'craft_gate', 'constraint_gate')}
            if not all((after.get(key) or {}).get('ok') is True for key in
                       ('pads_in_bounds', 'courtyards', 'craft_gate', 'constraint_gate')):
                return dict(result, ok=False, reason='recovered_physical_refused'), physical
            result['changed_refs'] = sorted(ref for ref, pose in candidate.P.items()
                                            if tuple(pose) != tuple(positions[ref]))
            cfg.params = dict(local.params)
            accepted = True
            return dict(result, ok=True, changed=True,
                        reason='frozen_local_return_recovered'), after
        finally:
            if not accepted:
                pipeline._restore_placement_authority(board, scratch)
