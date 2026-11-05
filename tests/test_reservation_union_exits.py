"""Tessellation-independent, bounded return-portal proposal endpoints."""
import copy
import math

import pytest
from cec_placement_search_domain import axis_exits_from_rect_union as exits
import cec_local_return_feedback as feedback
from test_local_return_feedback import fixture


def test_tiled_rectangle_has_same_exits_as_whole_rectangle():
    whole = [(0, 0, 8, 10)]
    tiles = [(0, 0, 8, 4), (0, 4, 8, 7), (0, 7, 8, 10)]
    assert exits((4, 3.8), tiles, .5) == exits((4, 3.8), whole, .5)
    assert exits((4, 3.8), list(reversed(tiles)), .5) == exits((4, 3.8), whole, .5)


def test_concave_union_does_not_use_oversized_bounding_box():
    assert exits((5, 2), [(0, 0, 10, 3), (0, 3, 2, 8)]) == [
        (-5, 0), (5, 0), (0, -2), (0, 1)]


def test_disjoint_obstacle_does_not_force_exit_past_real_gap():
    assert exits((2, 2), [(0, 0, 4, 4), (6, 0, 9, 4)]) == [
        (-2, 0), (2, 0), (0, -2), (0, 2)]
    # Inflated forbidden intervals can close that gap.
    assert exits((2, 2), [(0, 0, 4, 4), (6, 0, 9, 4)], 1)[1] == (8, 0)


@pytest.mark.parametrize('point', [(3, 5), (0, 2), (6, 1)])
def test_point_outside_union_needs_no_translation(point):
    assert exits(point, [(0, 0, 4, 4)]) == [(0, 0)]


@pytest.mark.parametrize('boxes,margin', [([(2, 0, 1, 3)], 0),
    ([(0, 0, math.nan, 3)], 0), ([(0, 0, 1, 3)], -1)])
def test_invalid_geometry_cannot_generate_moves(boxes, margin):
    with pytest.raises(ValueError):
        exits((0, 0), boxes, margin)


def test_return_feedback_does_not_exit_into_next_known_tile():
    positions, evidence, row, proof = fixture()
    admission = proof['pad_center']['copper_admission']
    admission['blockers'][0]['rect_mm'] = [8., 8., 12., 10.2]
    second = copy.deepcopy(admission)
    second.update(ok=False, at_mm=[10., 10.1])
    second['blockers'][0]['rect_mm'] = [8., 10.2, 12., 13.]
    proof['dogbone_candidates'] = [dict(failed_checks=['via_spot_clearance'],
                                      copper_admission=second)]
    original = copy.deepcopy((positions, evidence))
    old = feedback.move_specs(positions, evidence['decoupler']['details'], reservation_union=False)
    new = feedback.move_specs(positions, evidence['decoupler']['details'])
    assert min(m['dy_mm'] for m in old if m['dy_mm'] > 0) < 1
    assert min(m['dy_mm'] for m in new if m['dy_mm'] > 0) > 3
    assert all(m['exit_basis'] == 'known_reservation_union' for m in new)
    assert all(set(m['placements']) == set(positions) for m in new)
    assert all(m['requires_native_requalification'] for m in new)
    assert (positions, evidence) == original


def test_union_exit_respects_existing_move_budget_and_fixed_ownership():
    positions, evidence, row, proof = fixture()
    proof['pad_center']['copper_admission']['blockers'].append(dict(
        kind='pour_first_reservation', layer='B.Cu', net='OTHER', rect_mm=[8, 12, 12, 15]))
    assert len(feedback.move_specs(positions, evidence['decoupler']['details'], max_specs=2)) == 2
    assert not feedback.move_specs(positions, evidence['decoupler']['details'], immovable={'C_OTHER'})
