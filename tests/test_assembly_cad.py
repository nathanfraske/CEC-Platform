"""Run with the optional isolated CadQuery interpreter, not the KiCad venv."""
import math
import pytest
pytest.importorskip('cadquery')
from cec_assembly_cad import drill_solid


@pytest.mark.parametrize('sizes,angle,expected',[
    ([2,2],0,[2,2]),([4,2],0,[4,2]),([4,2],90,[2,4]),([2,4],0,[2,4])])
def test_native_drill_slots_keep_dimensions_and_orientation(sizes,angle,expected):
    row=dict(xy=[11,17],size_mm=sizes,diameter_mm=min(sizes),angle_degrees=angle)
    solid=drill_solid(row,1.6);bound=solid.BoundingBox()
    assert solid.isValid()
    assert [bound.xlen,bound.ylen]==pytest.approx(expected)
    assert bound.zlen==pytest.approx(1.62)
    assert [(bound.xmin+bound.xmax)/2,(bound.ymin+bound.ymax)/2]==pytest.approx([11,17])
    area=math.pi+2*(max(sizes)-min(sizes))
    assert solid.Volume()==pytest.approx(area*1.62)
