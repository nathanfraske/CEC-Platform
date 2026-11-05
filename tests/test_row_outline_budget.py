"""A fixed last-contact datum is not the complete mated outline budget."""
import math

import pytest

from cec_mating_rows import rigid_row_outline_fit


def fit(xs, lands, bounds=(0, 20), gap=.5):
    return rigid_row_outline_fit(xs, lands, outline_interval_mm=bounds,
                                 edge_clearance_mm=gap)


def test_recovers_translation_slack_without_repacking_or_growth():
    result = fit([1, 11], [(-2, 2)]*2)
    assert result['fits_fixed_outline']
    assert result['proposed_translation_mm'] == pytest.approx(1.5)
    assert result['minimum_width_mm'] == 15
    assert not result['admission_ok'] and not result['dimensions_changed']


def test_impossible_row_cannot_publish_a_translation():
    result = fit([3.5, 11.25, 19, 26.75], [(-3, 3)]*4, (0, 28))
    assert not result['fits_fixed_outline']
    assert result['minimum_width_mm'] == 30.25
    assert result['additional_width_mm'] == 2.25
    assert result['proposed_translation_mm'] is None


def test_all_contacts_and_asymmetric_companion_contribute():
    result = fit([5, 12, 16], [(-2, 2), (-9, 9), (-1, 3)])
    assert result['limiting_indices'] == [0, 1]
    assert result['minimum_width_mm'] == 19
    assert result['translation_window_mm'] == [-2.5, -1.5]


@pytest.mark.parametrize('shift', [-411.3, 0, 22.7])
def test_translation_invariance(shift):
    base = fit([3, 12], [(-2, 2)]*2)
    result = fit([3+shift, 12+shift], [(-2, 2)]*2, (shift, 20+shift))
    for key in ('translation_window_mm', 'minimum_width_mm', 'additional_width_mm'):
        assert result[key] == pytest.approx(base[key])


@pytest.mark.parametrize('xs,lands,bounds,gap', [
    ([], [], (0, 20), .5), ([1], [], (0, 20), .5),
    ([1], [(2, -2)], (0, 20), .5), ([1], [(-1, 1)], (0, 0), .5),
    ([math.inf], [(-1, 1)], (0, 20), .5), ([1], [(-1, 1)], (0, 20), -.1),
    ([1], [(-1, math.nan)], (0, 20), .5),
])
def test_missing_invalid_or_nonfinite_geometry_refuses(xs, lands, bounds, gap):
    with pytest.raises(ValueError):
        fit(xs, lands, bounds, gap)


def test_live_compilation_preserves_main_patterns_and_resizes_only_authorized_daughters():
    import cec_xfcn_contract as contract
    for name in ('eps-db', 'atx-db', 'pcie-db'):
        receipt = contract.PROJECTS[name]['mating_row_compilation']
        budget = receipt['fixed_outline_budget']
        assert receipt['ok'] and budget['fits_fixed_outline']
        assert budget['admission_ok'] is False
        assert budget['dimensions_changed'] is False
    eps = contract.PROJECTS['eps-db']['mating_row_compilation']['fixed_outline_budget']
    assert eps['minimum_width_mm'] == pytest.approx(30.25)
    atx = contract.PROJECTS['atx-db']['mating_row_compilation']['fixed_outline_budget']
    assert atx['members'][-1] == 'J20'
    assert atx['minimum_width_mm'] == pytest.approx(59.76)
    assert contract.PROJECTS['atx-db']['outline_rect_mm'][2] == 59.8
