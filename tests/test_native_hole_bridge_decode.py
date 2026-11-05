"""Decode actual native hole bridges without inventing or modifying copper."""
import time
import pcbnew
import pytest
from shapely.geometry import Polygon
import cec_native_fill_geometry as native
import cec_kelvin_copper_cut as cut
import cec_rectilinear_copper as owner


def holed(*, angle=0, mirror=False):
    p = pcbnew.SHAPE_POLY_SET()
    def at(x,y):
        if mirror: x = -x
        for _ in range(angle//90): x,y = -y,x
        return x+30000000,y+30000000
    p.NewOutline()
    for xy in [(0,0),(10000000,0),(10000000,10000000),(0,10000000)]:
        p.Append(*at(*xy),0,-1)
    for j,(x,y) in enumerate([(1000000,1000000),(6000000,6000000)]):
        p.NewHole(0)
        for xy in [(x,y),(x,y+2000000),(x+2000000,y+2000000),(x+2000000,y)]:
            p.Append(*at(*xy),0,j)
    return p


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
def test_native_fractured_holes_decode_with_exact_edges_and_zero_set_change(angle,mirror):
    original = holed(angle=angle,mirror=mirror)
    expected = cut._poly(original,cut._Work(time.monotonic()+2.))
    original.Fracture(False)
    before = original.Format()
    decoded, proof = native.decode_linear_hole_bridges(original,time.monotonic()+2.)
    assert proof['bridge_count'] == 2
    assert proof['zero_native_loss'] and proof['zero_native_spill']
    assert proof['exact_native_boundary_edges_preserved'] and not proof['source_mutated']
    assert original.Format() == before
    assert decoded.HoleCount(0) == 2
    actual = cut._poly(original,cut._Work(time.monotonic()+2.))
    assert actual.equals(expected) and len(actual.interiors) == 2
    assert original.Format() == before
    assert not proof['new_capacity_credited'] and not proof['release_authority']


@pytest.mark.parametrize('points', [
    [(0,0),(10,0),(10,10),(5,10),(5,5),(5,10),(0,10)], # dangling fold, NOT a hole
    [(0,0),(10,10),(0,10),(10,0)], # crossing; never make-valid
    [(0,0),(10,0),(10,10),(0,10),(10,10),(10,0)], # doubled non-hole path
    [(0,0),(10,0),(10,0),(10,10),(0,10)], # zero edge
])
def test_malformed_native_rings_remain_unknown(points):
    p = owner._poly(points)
    before = p.Format()
    with pytest.raises((owner.Refused,cut.Unknown)):
        if len(set(points)) < len(points): native.decode_linear_hole_bridges(p,time.monotonic()+2.)
        else: cut._poly(p,cut._Work(time.monotonic()+2.))
    assert p.Format() == before


def test_bridge_decode_budget_and_deadline_cannot_report_clean_geometry():
    p = holed(); p.Fracture(False)
    with pytest.raises(owner.Refused): native.decode_linear_hole_bridges(p,time.monotonic()-1.)
    with pytest.raises(owner.Refused): native.decode_linear_hole_bridges(p,time.monotonic()+2.,max_vertices=3)
    with pytest.raises(cut.Unknown): cut._poly(p,cut._Work(time.monotonic()-1.))


def test_collinear_bridge_attachment_split_is_the_same_exact_integer_boundary():
    points=[(0,0),(10,0),(10,5),(8,5),(8,2),(2,2),(2,8),(8,8),
            (8,5),(10,5),(10,10),(0,10)]
    original = owner._poly(points)
    before = original.Format()
    decoded, proof = native.decode_linear_hole_bridges(original,time.monotonic()+2.)
    assert decoded.HoleCount(0)==1 and proof['exact_native_boundary_edges_preserved']
    actual=cut._poly(original,cut._Work(time.monotonic()+2.))
    expected=Polygon([(0,0),(10,0),(10,10),(0,10)], [[(2,2),(2,8),(8,8),(8,2)]])
    assert actual.equals(expected) and original.Format()==before


@pytest.mark.parametrize('fault',['one_nm_edge','fill_hole'])
def test_decoder_cannot_hide_changed_native_geometry(fault,monkeypatch):
    original=holed(); original.Fracture(False); before=original.Format()
    actual=pcbnew.SHAPE_POLY_SET.Unfracture
    def changed(shape):
        actual(shape)
        if fault=='one_nm_edge':
            p=shape.Outline(0).CPoint(0)
            shape.Outline(0).SetPoint(0,pcbnew.VECTOR2I(p.x+1,p.y))
        else:
            simple=owner._poly([(30000000,30000000),(40000000,30000000),
                (40000000,40000000),(30000000,40000000)])
            shape.RemoveAllContours();shape.Append(simple)
    monkeypatch.setattr(pcbnew.SHAPE_POLY_SET,'Unfracture',changed)
    with pytest.raises(owner.Refused): native.decode_linear_hole_bridges(original,time.monotonic()+2.)
    assert original.Format()==before
