"""Manufacturing-grid serialization must not invent an invalid contour."""
import pytest
from shapely.geometry import Polygon, box
from shapely.ops import unary_union
import cec_slab_pour as slab


@pytest.mark.parametrize('dx,dy', [(0, 0), (37, -11)])
def test_subgrid_neck_collapses_to_two_valid_areas_without_added_copper(dx, dy):
    geometry = unary_union([box(dx, dy, dx+2, dy+2),
                            box(dx+2, dy+.9999, dx+4, dy+1.0001),
                            box(dx+4, dy, dx+6, dy+2)])
    assert geometry.is_valid and geometry.geom_type == 'Polygon'
    rows = slab._export_polygon_geometry(geometry)
    assert len(rows) == 2
    result = unary_union([Polygon(row['polygon'], row.get('holes') or ()) for row in rows])
    assert result.is_valid and result.area == pytest.approx(8)
    assert result.difference(geometry).area < 1e-9


def test_holes_and_manhattan_edges_survive_export():
    geometry = box(0, 0, 10, 10).difference(box(3, 3, 7, 7))
    [row] = slab._export_polygon_geometry(geometry)
    assert len(row['holes']) == 1
    assert Polygon(row['polygon'], row['holes']).equals(geometry)
    for ring in [row['polygon']] + row['holes']:
        assert all(a[0] == b[0] or a[1] == b[1] for a, b in zip(ring, ring[1:]))


def test_arbitrary_self_intersection_is_not_silently_healed():
    with pytest.raises(ValueError, match='invalid source'):
        slab._export_polygon_geometry(Polygon([(0, 0), (2, 2), (0, 2), (2, 0)]))


def test_zero_area_export_sliver_is_not_kept_as_a_route():
    assert slab._export_polygon_geometry(box(0, 0, .0001, 4)) == []
