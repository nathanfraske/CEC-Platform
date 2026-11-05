"""Wide/shallow source pockets, not fabrication or current-budget fixtures."""
import pytest
from shapely.geometry import Polygon
import cec_shallow_copper_pocket_cover as pockets

SOURCE = [[0, 0], [6000000, 0], [6000000, 4000000], [4000000, 4000000],
    [4000000, 3800000], [2000000, 3800000], [2000000, 4000000], [0, 4000000]]
def orient(points, q, back):
    result = []
    for x, y in points:
        if back: x = -x
        for _ in range(q): x, y = -y, x
        result.append([x, y])
    return result

@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('back', [False, True])
def test_shallow_mouth_wider_than_depth_is_not_misclassified_as_a_deep_hook(quarter, back):
    source = orient(SOURCE, quarter, back)
    offers = pockets.candidates(source)
    assert offers
    assert any(Polygon(o['points_nm']).equals(Polygon(orient([[0, 0], [6000000, 0],
        [6000000, 4000000], [0, 4000000]], quarter, back))) for o in offers)
    for offer in offers:
        assert Polygon(offer['points_nm']).covers(Polygon(source))
        assert offer['native_source_polygon_loss_outlines'] == 0
        assert not offer['numeric_or_area_waiver_used']

def test_deep_hook_and_convex_outline_are_not_filled_as_small_pockets():
    deep = [[x, 1500000 if y == 3800000 else y] for x, y in SOURCE]
    assert not pockets.candidates(deep)
    assert not pockets.candidates([[0, 0], [6000000, 0], [6000000, 4000000], [0, 4000000]])

@pytest.mark.parametrize('key,value', [('maximum_depth_nm', 1000001), ('maximum_depth_nm', True),
    ('minimum_depth_nm', 0), ('maximum_span_nm', 9000000), ('maximum_window_edges', 9), ('timeout_s', 11)])
def test_finite_search_bounds_cannot_be_repurposed_as_geometry_permission(key, value):
    with pytest.raises(ValueError): pockets.candidates(SOURCE, **{key: value})

def test_collinear_source_vertices_are_not_physical_boundary_complexity():
    source = [SOURCE[0], [3000000, 0], *SOURCE[1:]]
    assert pockets.compact(source) == pockets.compact(SOURCE)
