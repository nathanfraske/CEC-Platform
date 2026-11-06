"""A smaller laminate is not necessarily a smaller installed assembly."""
import copy

import pytest
from shapely.geometry import box, mapping

from cec_assembly_envelope import projected_dimensions


def board(body=None):
    return dict(outline=mapping(box(0, 0, 20, 20)), missing=[], bodies=[] if body is None else [
        dict(ref='connector', height_max_mm=5., xy=mapping(body),
             geometry_source='native_courtyard', basis='design_allocation')])


def measure(a, b, transform=(1, 0, 0, 1, 0, 0)):
    return projected_dimensions(a, b, transform)


def test_edge_trim_cannot_claim_fixed_connector_height_saving():
    a, b = board(box(5, 18, 12, 25)), board()
    baseline = measure(a, b)
    a['outline'] = b['outline'] = mapping(box(0, 0, 20, 18))
    result = measure(a, b)
    assert result['laminate']['size_mm'] == [20, 18]
    assert result['declared_body_plus_laminate'] == baseline['declared_body_plus_laminate']
    assert not result['release_authority']
    assert 'external_cables_and_plugs' in result['exclusions']


def test_real_connector_move_reports_body_gain_without_laminate_change():
    a, b = board(box(5, 18, 12, 25)), board()
    old = measure(a, b)
    a['bodies'][0]['xy'] = mapping(box(5, 14, 12, 21))
    new = measure(a, b)
    assert new['laminate'] == old['laminate']
    assert old['declared_body_plus_laminate']['size_mm'] == [20, 25]
    assert new['declared_body_plus_laminate']['size_mm'] == [20, 21]


def test_deadbug_fixed_datum_does_not_follow_a_trimmed_bbox():
    a, b = board(), board(box(-4, 8, 0, 12))
    transform = (-1, 0, 0, 1, 20, 5)
    old = measure(a, b, transform)
    b['outline'] = mapping(box(2, 0, 20, 18))
    new = measure(a, b, transform)
    assert old['declared_body_plus_laminate']['bounds_mm'] == [0, 0, 24, 25]
    assert new['declared_body_plus_laminate']['bounds_mm'] == [0, 0, 24, 23]
    assert new['laminate']['bounds_mm'] == [0, 0, 20, 23]


@pytest.mark.parametrize('transform', [(1, 0, 0, 1, 0, 0), (-1, 0, 0, 1, 20, 0),
                                     (0, -1, 1, 0, 20, 0), (0, 1, -1, 0, 0, 20)])
def test_rigid_frames_preserve_identity_and_inputs(transform):
    a, b = board(box(1, 1, 3, 3)), board(box(1, 1, 3, 3))
    before = copy.deepcopy((a, b))
    result = measure(a, b, transform)
    assert result['complete']
    assert result['laminate']['size_mm'] == [20, 20]
    assert (a, b) == before


def test_missing_body_is_unknown_not_small():
    a, b = board(), board()
    b['missing'] = [dict(ref='unknown', footprint='unknown-package')]
    result = measure(a, b)
    assert not result['complete']
    assert result['declared_body_plus_laminate'] is None
    assert result['laminate']['size_mm'] == [20, 20]
    assert result['missing'][0]['side'] == 'cover'


def test_zero_height_art_has_no_fictitious_body():
    a, b = board(), board()
    a['bodies'] = [dict(ref='mark', height_max_mm=0)]
    result = measure(a, b)
    assert result['declared_body_plus_laminate'] == result['laminate']


@pytest.mark.parametrize('transform', [(2, 0, 0, 1, 0, 0), (1, .2, 0, 1, 0, 0),
                                     (1, 0, 0, 1, float('nan'), 0)])
def test_scale_shear_and_nonfinite_frames_refuse(transform):
    with pytest.raises(ValueError):
        measure(board(), board(), transform)


@pytest.mark.parametrize('height', [True, -1, float('inf'), float('nan')])
def test_invalid_height_cannot_make_a_body_vanish(height):
    a = board(box(1, 1, 3, 3)); a['bodies'][0]['height_max_mm'] = height
    with pytest.raises(ValueError):
        measure(a, board())


def test_duplicate_body_identity_and_incomplete_population_refuse():
    a = board(box(1, 1, 3, 3)); a['bodies'].append(copy.deepcopy(a['bodies'][0]))
    with pytest.raises(ValueError):
        measure(a, board())
    a = board(); del a['missing']
    with pytest.raises(ValueError):
        measure(a, board())


def test_invalid_known_body_still_refuses_when_another_is_missing():
    a, b = board(box(1, 1, 3, 3)), board()
    a['bodies'][0]['xy'] = mapping(box(1, 1, 1, 3))
    b['missing'] = [dict(ref='unknown')]
    with pytest.raises(ValueError):
        measure(a, b)


def test_extreme_finite_coordinates_cannot_overflow_metrics():
    a = board(box(-1e308, 0, 1e308, 1))
    with pytest.raises(ValueError):
        measure(a, board())
