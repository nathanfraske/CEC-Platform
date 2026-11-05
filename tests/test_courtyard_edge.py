"""Edge proposals respect native-outline geometry and finite search bounds."""
import sys
from pathlib import Path
import pytest
from shapely.geometry import box, Polygon
from shapely import affinity
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import cec_courtyard_edge as edge


@pytest.mark.parametrize('rotation',[0,90,180,270])
def test_rotated_translated_edge_gap(rotation):
    outline=affinity.translate(affinity.rotate(box(0,0,10,10),rotation,origin=(0,0)),13,27)
    shape=affinity.translate(affinity.rotate(box(8,4,9.5,6),rotation,origin=(0,0)),13,27)
    rows=edge.translation_offsets(shape,outline)
    assert rows
    assert min((x*x+y*y)**.5 for x,y in rows)==pytest.approx(.4)
    assert all(outline.buffer(-.9,join_style='mitre').covers(
        affinity.translate(shape,xoff=x,yoff=y)) for x,y in rows)


def test_corner_requires_joint_move():
    rows=edge.translation_offsets(box(8,8,9.5,9.5),box(0,0,10,10))
    assert rows and all(x<0 and y<0 for x,y in rows)


def test_cutout_is_not_ignored_as_bounding_box():
    outline=Polygon([(0,0),(10,0),(10,10),(0,10)],holes=[[(4,4),(6,4),(6,6),(4,6)]])
    shape=box(6.4,4.5,7,5.5)
    rows=edge.translation_offsets(shape,outline)
    assert rows and rows[0][0]>0
    assert all(outline.buffer(-.9,join_style='mitre').covers(
        affinity.translate(shape,xoff=x,yoff=y)) for x,y in rows)


def test_clean_or_impossible_seat_proposes_nothing():
    assert edge.translation_offsets(box(3,3,4,4),box(0,0,10,10))==[]
    assert edge.translation_offsets(box(0,0,10,10),box(0,0,10,10))==[]


@pytest.mark.parametrize('options',[{'max_shift_mm':3},{'step_mm':.001},
    {'margin_mm':float('nan')},{'limit':1000},{'limit':True}])
def test_unbounded_domains_refused(options):
    with pytest.raises(ValueError):
        edge.translation_offsets(box(8,4,9.5,6),box(0,0,10,10),**options)
