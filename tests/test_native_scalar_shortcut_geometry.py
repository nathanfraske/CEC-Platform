"""The proposal is parameterized; native saved-board receiving is separate."""
import math
import pytest
import cec_route_quality as quality
import root_native_scalar_shortcut_geometry_20261015 as geometry


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('displacement',[(7000000,3000000),(3000000,7000000),(7,3),(0,7000000),(3000000,3000000)])
def test_finite_shortcuts_use_exact_axis_and_45_strokes_without_hard_right_angles(angle,mirror,displacement):
    c,s=round(math.cos(math.radians(angle))),round(math.sin(math.radians(angle)))
    dx,dy=displacement;dx*=(-1 if mirror else 1)
    start=(100000003,200000007);end=(start[0]+c*dx-s*dy,start[1]+s*dx+c*dy)
    paths=geometry.paths(start,end)
    assert 1<=len(paths)<=2 and paths==geometry.paths(start,end)
    for path in paths:
        assert path[0]==start and path[-1]==end and 2<=len(path)<=3 and len(set(path))==len(path)
        assert all(quality.is_canonical_stroke(a,b,tolerance_nm=0) for a,b in zip(path,path[1:]))
        if len(path)==3:
            a,m,b=path;v=(m[0]-a[0],m[1]-a[1]);w=(b[0]-m[0],b[1]-m[1])
            assert v[0]*w[0]+v[1]*w[1]>0
        assert list(reversed(path)) in geometry.paths(end,start)


@pytest.mark.parametrize('start,end',[
    ((0,0),(0,0)),((True,0),(1,1)),((0.,0),(1,1)),((0,),(1,1)),
    ((0,0),(2000000001,1)),((0,0),(float('nan'),1)),('0,0',(1,1)),
])
def test_malformed_rounded_or_unbounded_coordinates_refuse(start,end):
    with pytest.raises(ValueError):geometry.paths(start,end)
