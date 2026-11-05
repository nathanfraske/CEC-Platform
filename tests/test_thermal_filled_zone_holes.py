"""Actual native filled holes stay void in electrical/thermal raster copper.

Independent analytic masks and native point collisions are the oracle. These
tests do not accept a larger authored outline or call the implementation to
calculate their expected copper area. No capacity/thermal qualification follows.
"""
import numpy as np
import pcbnew
import pytest
from shapely.geometry import Point
import cec_thermal2d as thermal


def _pose(x,y,quarter):
    for _ in range(quarter):x,y=-y,x
    return x+12.,y+12.


def _poly(regions,quarter=0):
    poly=pcbnew.SHAPE_POLY_SET()
    for oi,(outer,holes)in enumerate(regions):
        assert poly.NewOutline()==oi
        for x,y in outer:
            x,y=_pose(x,y,quarter);poly.Append(round(x*1e6),round(y*1e6),oi,-1)
        for hi,ring in enumerate(holes):
            poly.NewHole(oi)
            for x,y in ring:
                x,y=_pose(x,y,quarter);poly.Append(round(x*1e6),round(y*1e6),oi,hi)
    return poly


def _rectangle(a,b,c,d):return[(a,b),(c,b),(c,d),(a,d)]


REGIONS=[(_rectangle(0,0,10,8),[_rectangle(2,2,4,4),_rectangle(6,3,8,5)]),
         (_rectangle(2.75,2.75,3.25,3.25),[])]


def _rings(poly):
    return [[[(int(r.CPoint(k).x),int(r.CPoint(k).y))for k in range(r.PointCount())]
        for r in [poly.Outline(i),*[poly.Hole(i,j)for j in range(poly.HoleCount(i))]]]
        for i in range(poly.OutlineCount())]


def _fixture(face=pcbnew.F_Cu,quarter=0,netname='RENAMED_NATIVE_POWER'):
    board=pcbnew.BOARD();board.SetCopperLayerCount(6)
    net=pcbnew.NETINFO_ITEM(board,netname);board.Add(net)
    zone=pcbnew.ZONE(board);zone.SetNet(net);zone.SetLayer(face)
    # The authored perimeter is deliberately larger. It is not copper.
    zone.Outline().Append(_poly([(_rectangle(-1,-1,11,9),[])],quarter))
    fill=_poly(REGIONS,quarter);zone.SetFilledPolysList(face,fill);zone.SetIsFilled(True);board.Add(zone)
    return board,zone


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu,pcbnew.In2_Cu])
def test_native_filled_holes_and_inner_island_are_preserved(face,quarter):
    board,zone=_fixture(face,quarter)
    native=zone.GetFilledPolysList(face);before=_rings(native)
    assert native.OutlineCount()==2 and native.HoleCount(0)==2
    out=thermal._zone_polys(board,{face:'LAYER_RENAMED'})
    assert set(out)=={('RENAMED_NATIVE_POWER','LAYER_RENAMED')}
    polygons=out[('RENAMED_NATIVE_POWER','LAYER_RENAMED')]
    assert len(polygons)==2
    assert sum(len(p.interiors)for p in polygons)==2
    assert sum(p.area for p in polygons)==pytest.approx(72.25,abs=1e-12)
    for x,y,want in[(1,1,True),(2.5,2.5,False),(3,3,True),(7,4,False),(10.5,4,False)]:
        point=_pose(x,y,quarter)
        native_inside=native.Collide(pcbnew.VECTOR2I(*(round(c*1e6)for c in point)))
        assert native_inside is want
        assert any(p.contains(Point(*point))for p in polygons)is want
    assert _rings(zone.GetFilledPolysList(face))==before


@pytest.mark.parametrize('quarter',range(4))
def test_raster_uses_actual_voids_not_solid_bounding_rectangle(quarter):
    board,zone=_fixture(quarter=quarter)
    grid=thermal.Grid(0,0,24,24,.25)
    polygons=thermal._zone_polys(board,{pcbnew.F_Cu:'F'})[('RENAMED_NATIVE_POWER','F')]
    actual=thermal._rasterize_polys(polygons,grid)
    xx,yy=np.meshgrid(grid.xc-12.,grid.yc-12.)
    # Independent inverse cardinal transform followed by exact rectangle CSG.
    for _ in range(quarter):xx,yy=yy,-xx
    outer=(xx>0)&(xx<10)&(yy>0)&(yy<8)
    hole1=(xx>2)&(xx<4)&(yy>2)&(yy<4)
    hole2=(xx>6)&(xx<8)&(yy>3)&(yy<5)
    island=(xx>2.75)&(xx<3.25)&(yy>2.75)&(yy<3.25)
    np.testing.assert_array_equal(actual,(outer&~hole1&~hole2)|island)
    assert actual.sum()*grid.grid_mm**2==pytest.approx(72.25)


def test_unfilled_authored_outline_is_not_a_solid_thermal_slab():
    board,zone=_fixture()
    zone.SetFilledPolysList(pcbnew.F_Cu,pcbnew.SHAPE_POLY_SET());zone.SetIsFilled(False)
    assert thermal._zone_polys(board,{pcbnew.F_Cu:'F'})=={}


def test_other_face_or_net_does_not_fill_this_nets_antipad():
    board,zone=_fixture()
    other=pcbnew.NETINFO_ITEM(board,'OTHER_RAIL');board.Add(other)
    z=pcbnew.ZONE(board);z.SetNet(other);z.SetLayer(pcbnew.F_Cu)
    fill=_poly([(_rectangle(2,2,4,4),[])])
    z.Outline().Append(fill);z.SetFilledPolysList(pcbnew.F_Cu,fill);z.SetIsFilled(True);board.Add(z)
    rows=thermal._zone_polys(board,{pcbnew.F_Cu:'F',pcbnew.B_Cu:'B'})
    point=Point(*_pose(2.5,2.5,0))
    assert not any(p.contains(point)for p in rows[('RENAMED_NATIVE_POWER','F')])
    assert any(p.contains(point)for p in rows[('OTHER_RAIL','F')])
    assert all(face=='F'for _net,face in rows)
