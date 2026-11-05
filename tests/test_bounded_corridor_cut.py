"""Finite search coverage for multi-owner current-corridor witnesses."""
import itertools
import math
from types import SimpleNamespace

import pytest

from cec_cell_packing import bounded_translation_product
import cec_synth_pipeline as synth


def test_small_product_preserves_exhaustive_order():
    menus = [[(0., 1.), (0., -1.)], [(2., 0.), (3., 0.)]]
    assert list(bounded_translation_product(menus)) == list(itertools.product(*menus))


def test_large_product_is_bounded_unique_and_cost_ordered():
    menus = [[(0., float(i)) for i in range(1, 9)]] * 8
    result = list(bounded_translation_product(menus, max_combinations=128))
    assert len(result) == len(set(result)) == 128
    costs = [(max(math.hypot(*c) for c in row), sum(math.hypot(*c) for c in row))
             for row in result]
    assert costs == sorted(costs)
    assert result == list(bounded_translation_product(menus, max_combinations=128))


@pytest.mark.parametrize('budget', [0, -1, 1.5])
def test_product_rejects_invalid_budget(budget):
    with pytest.raises(ValueError):
        list(bounded_translation_product([[(0., 0.)]], max_combinations=budget))


def test_product_rejects_nonfinite_geometry():
    with pytest.raises(ValueError):
        list(bounded_translation_product([[(math.inf, 0.)]]))
    assert list(bounded_translation_product([[]])) == []


def fixture(count):
    poses = {f'X{i}': (5.+i*5., 10., 0.) for i in range(count)}
    cut = {'owners': list(poses), 'owner_bounds_mm': {
        ref: [x-1., y-1., x+1., y+1.] for ref,(x,y,_) in poses.items()},
        'path_mm': [[0., 10.], [count*5.+10., 10.]]}
    return SimpleNamespace(P=poses, W=100., H=60., back_refs=()), cut


def test_five_independent_roots_are_not_silently_discarded():
    candidate, cut = fixture(5)
    relief = {'wide_relief_sets': [cut]}
    assert synth._placement_actionable_relief_cuts(relief, candidate.P, {})
    specs = synth._placement_relief_joint_envelope_specs(
        candidate, cut, 4., {}, {}, max_combinations=32, max_specs=16)
    assert specs
    assert len(specs) <= 16
    assert all(set(s['placements']) == set(candidate.P) for s in specs)
    assert all(s['search']['root_count'] == 5 for s in specs)
    assert all(s['search']['combination_budget'] == 32 for s in specs)
    assert all(abs(dy) >= 3.1-1e-6 for s in specs
               for dx,dy in s['translations_mm'].values())


def test_root_limit_is_explicit_and_configurable():
    candidate, cut = fixture(5)
    assert not synth._placement_actionable_relief_cuts(
        {'wide_relief_sets': [cut]}, candidate.P, {}, max_actionable_roots=4)
    assert not synth._placement_relief_joint_envelope_specs(
        candidate, cut, 4., {}, {}, max_roots=4)


def test_multiroot_packs_preserve_protected_corridor():
    candidate, cut = fixture(6)
    specs = synth._placement_relief_joint_envelope_specs(
        candidate, cut, 4., {}, {}, max_combinations=64,
        protected_regions=[{'layer':'F.Cu','box':[0.,0.,100.,7.5]}])
    assert specs
    assert all(9.+dy >= 7.5 for s in specs
               for dx,dy in s['translations_mm'].values())


def test_complete_cut_has_its_own_budget_not_its_lead_roots_rotations():
    candidate, cut = fixture(5)
    evidence = {'power_body_clearance': {'planner_failures': {
        '/synthetic-rail': {'planner_bottleneck': {'relief': {'edge': {
            'required_width_mm': 4., 'wide_relief_sets': [cut]}}}}}}}
    proposals = synth._placement_craft_move_specs(
        candidate, evidence, required_stages=['power_corridor_access'])
    packs = [row for row in proposals if row['kind'] ==
             'power_corridor_relief_joint_envelope_pack']
    assert packs and all(set(row['placements']) == set(candidate.P) for row in packs)
    lead = packs[0]['ref']
    cheap = [dict(kind='rotation', ref=lead, rotation=i) for i in range(100)]
    selected = synth._bounded_diverse_move_specs(cheap + packs, 2)
    assert any(row['kind']=='power_corridor_relief_joint_envelope_pack' for row in selected)
    assert any(row['kind']=='rotation' for row in selected)
    assert synth._bounded_move_group(packs[0]) != lead
