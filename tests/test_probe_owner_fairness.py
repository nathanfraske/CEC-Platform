"""Topology alternatives must not masquerade as independent failed owners."""
import copy

import pytest

import cec_synth_pipeline as synth


def population(names):
    # Deliberately put every alternative from one pair ahead of all other
    # owners. Ref names and kinds carry no policy meaning in this fixture.
    rows = [dict(ref=names[0], kind='alternative', budget_group=f'edge-{i}',
                 refs=[names[0], 'follower'], position=(i, 0, 0))
            for i in range(100)]
    rows += [dict(ref=name, kind='range', budget_group=f'{name}-{i}',
                  position=(i, 1, 0)) for name in names[1:] for i in range(4)]
    return rows


@pytest.mark.parametrize('names', [('alpha', 'beta', 'gamma', 'delta'),
                                  ('X800', 'A4', 'P9000', 'Z')])
@pytest.mark.parametrize('budget', [0, 1, 4, 8, 16, 150])
def test_owner_quota_is_bounded_deterministic_and_rename_invariant(names, budget):
    rows = population(names)
    before = copy.deepcopy(rows)
    picked = synth._bounded_critical_owner_move_specs(rows, budget, names)
    assert rows == before
    assert len(picked) == min(budget, len(rows))
    assert len({id(row) for row in picked}) == len(picked)
    assert picked == synth._bounded_critical_owner_move_specs(rows, budget, names)
    if budget >= len(names):
        assert {row['ref'] for row in picked} == set(names)
    if 4 <= budget <= 16:
        counts = [sum(row['ref'] == name for row in picked) for name in names]
        assert max(counts) - min(counts) <= 1


def test_direct_physical_reserve_also_covers_other_owners():
    names = ('a', 'b', 'c', 'd')
    direct = population(names)
    speculative = [dict(ref='a', kind='speculative', budget_group=f'spec-{i}',
                        position=(i, 2, 90)) for i in range(80)]
    blockers = [dict(ref=f'obstacle-{i}', kind='blocker', position=(i, 3, 0))
                for i in range(5)]
    rows = speculative + direct + blockers
    picked, reserved = synth._bounded_critical_owner_move_specs_with_direct_physical_reserve(
        rows, 16, names, direct)
    assert reserved == 8
    assert {row['ref'] for row in picked[:reserved]} == set(names)
    assert any(row['kind'] == 'blocker' for row in picked)
    assert any(row['kind'] == 'speculative' for row in picked)
    assert len(picked) == len({id(row) for row in picked}) == 16


def test_incidental_follower_does_not_steal_their_owner_quota():
    rows = population(('a', 'b', 'c'))
    for row in rows[:100]:
        row['refs'] = ['a', 'b', 'c']
    picked = synth._bounded_owner_evidence_move_specs(rows, 3, {'a', 'b', 'c'})
    assert [row['ref'] for row in picked] == ['a', 'b', 'c']


def test_family_breadth_and_tail_sampling_survive_inside_owner():
    rows = [dict(ref=ref, budget_group=family, index=i)
            for ref in ('a', 'b') for family in ('near', 'far') for i in range(10)]
    picked = synth._bounded_owner_evidence_move_specs(rows, 8, {'a', 'b'})
    for ref in ('a', 'b'):
        assert [(row['budget_group'], row['index']) for row in picked if row['ref'] == ref] == [
            ('near', 0), ('near', 9), ('far', 0), ('far', 9)]


def test_rootless_atomic_moves_remain_a_single_family_owner():
    rows = [dict(placements={'x': (i, 0, 0), 'y': (i, 1, 0)},
                 budget_group=f'atomic-{i}') for i in range(30)]
    rows.append(dict(ref='z', position=(0, 0, 0)))
    picked = synth._bounded_owner_evidence_move_specs(rows, 2, {'x', 'y', 'z'})
    assert len(picked) == 2 and picked[-1]['ref'] == 'z'
