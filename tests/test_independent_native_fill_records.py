"""Overlapping source records are copper unions, not one shared bridge graph."""
import time
import pcbnew
import pytest
from shapely.geometry import Polygon
import cec_kelvin_copper_cut as cut
import cec_rectilinear_copper as owner
from test_native_hole_bridge_decode import holed
from test_kelvin_copper_cut import native_board_fixture,audit,zone


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('mode',['duplicate','offset','solid_overlap','touching'])
def test_each_signed_record_decodes_before_union_with_literal_saved_boundaries_kept(angle,mirror,mode):
    base=holed(angle=angle,mirror=mirror)
    expected=cut._poly(base,cut._Work(time.monotonic()+2.))
    if mode in ('duplicate','offset'):
        peer=base.CloneDropTriangulation()
        if mode=='offset':peer.Move(pcbnew.VECTOR2I(1000000,0))
    else:
        x0,y0,x1,y1=map(int,expected.bounds)
        if mode=='touching':x0,x1=x1,x1+1000000
        peer=owner._poly([(x0,y0),(x1,y0),(x1,y1),(x0,y1)])
    expected=expected.union(cut._poly(peer,cut._Work(time.monotonic()+2.)))
    base.Fracture(False);peer.Fracture(False);base.Append(peer);original=base.Format()
    actual=cut._poly(base,cut._Work(time.monotonic()+2.))
    assert actual.equals(expected) and base.Format()==original
    if mode=='duplicate':assert len(actual.interiors)==2
    if mode=='solid_overlap':assert len(actual.interiors)==0


@pytest.mark.parametrize('fault',['fold','crossing','duplicate_edge','zero_edge'])
@pytest.mark.parametrize('covered',[False,True])
def test_invalid_record_is_not_hidden_by_another_positive_fill(fault,covered):
    points={
        'fold':[(0,0),(10,0),(10,10),(5,10),(5,5),(5,10),(0,10)],
        'crossing':[(0,0),(10,10),(0,10),(10,0)],
        'duplicate_edge':[(0,0),(10,0),(10,10),(0,10),(10,10),(10,0)],
        'zero_edge':[(0,0),(10,0),(10,0),(10,10),(0,10)]}[fault]
    p=owner._poly(points)
    if fault=='zero_edge':
        # Append discards an immediately duplicate input coordinate. Corrupt
        # the ACTUAL native chain instead of testing a normalized fixture.
        p.Outline(0).SetPoint(2,p.Outline(0).CPoint(1))
    peer=owner._poly([(-1,-1),(11,-1),(11,11),(-1,11)]
        if covered else [(20,20),(30,20),(30,30),(20,30)])
    p.Append(peer);original=p.Format()
    with pytest.raises(cut.Unknown):cut._poly(p,cut._Work(time.monotonic()+2.))
    assert p.Format()==original


@pytest.mark.parametrize('fault',['deadline','vertex_budget','component_budget'])
def test_aggregate_budgets_still_fail_closed_across_records(monkeypatch,fault):
    p=holed();p.Fracture(False);p.Append(p.CloneDropTriangulation());original=p.Format()
    work=cut._Work(time.monotonic()+2.)
    if fault=='deadline':work.deadline=time.monotonic()-1.
    elif fault=='vertex_budget':monkeypatch.setattr(cut,'MAX_VERTICES',32)
    else:monkeypatch.setattr(cut,'MAX_COMPONENTS',1)
    with pytest.raises(cut.Unknown):cut._poly(p,work)
    assert p.Format()==original


@pytest.mark.parametrize('bypass',[False,True])
@pytest.mark.parametrize('duplicate',[False,True])
def test_actual_kelvin_cut_with_retained_overlapping_records_still_detects_bypass(tmp_path,bypass,duplicate):
    values=native_board_fixture(tmp_path/'source.kicad_pcb')
    item=zone(values[0],[(88 if bypass else 89.9,72,92 if bypass else 90.1,78)])
    # Add a remote drilled-window record to exercise the fractured decoder,
    # while the near-source record decides the real pad-minus-copper result.
    hole=holed();hole.Fracture(False)
    filled=item.GetFilledPolysList(pcbnew.F_Cu).CloneDropTriangulation()
    filled.Append(hole)
    if duplicate:filled.Append(hole)
    item.SetFilledPolysList(pcbnew.F_Cu,filled);item.SetIsFilled(True)
    original=filled.Format();r=audit(values)
    assert r['complete'] and r['ok'] is (not bypass),r
    assert r['physical_bypass_proved'] is bypass
    assert item.GetFilledPolysList(pcbnew.F_Cu).Format()==original
