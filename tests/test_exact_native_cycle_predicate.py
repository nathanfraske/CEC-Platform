"""Internal rounded collision diagnostics are not exact integer topology."""
import time
import pcbnew
import pytest
from shapely.geometry import Polygon
import cec_native_fill_geometry as native
import cec_kelvin_copper_cut as cut
import cec_rectilinear_copper as owner


HOLE=[(0,0),(0,1),(0,100000),(100000,100000),(100000,99999),
      (50000,90000),(10000,50000)]
OUTER=[(-1000000,-1000000),(1000000,-1000000),(1000000,100000),
       (1000000,1000000),(-1000000,1000000)]


def transformed(points,angle=0,mirror=False,offset=0):
    result=[]
    for x,y in points:
        if mirror:x=-x
        for _ in range(angle//90):x,y=-y,x
        result.append((x+offset,y+offset))
    return result


def bridged(angle=0,mirror=False,offset=0):
    # One real signed hole, attached to its outer by an exactly reverse
    # paired zero-width bridge. Every boundary coordinate is literal.
    ring=[*OUTER[:3],*HOLE[3:],*HOLE[:3],HOLE[3],OUTER[2],*OUTER[3:]]
    shape=owner._poly(transformed(ring,angle,mirror,offset))
    expected=Polygon(transformed(OUTER,angle,mirror,offset),
                     [transformed(HOLE,angle,mirror,offset)])
    assert expected.is_valid
    return shape,expected


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('offset',[0,1900000000,-1900000000])
def test_one_unit_nonadjacent_near_edges_decode_exactly_without_native_geometry_repair(angle,mirror,offset):
    shape,expected=bridged(angle,mirror,offset);before=shape.Format()
    decoded,proof=native.decode_exact_hole_boundaries(shape,time.monotonic()+2.)
    assert proof['zero_native_loss'] and proof['zero_native_spill']
    assert proof['exact_native_directed_edges_preserved'] and not proof['source_mutated']
    assert cut._poly(decoded,cut._Work(time.monotonic()+2.)).equals(expected)
    assert shape.Format()==before
    for item in proof['exact_cycle_false_positive_rechecks']:
        assert item['exact_integer_topology']['numeric_tolerance_nm']==0
        assert not item['exact_integer_topology']['source_geometry_repaired']
    assert not proof['new_capacity_credited'] and not proof['release_authority']


def test_real_native_one_unit_predicate_disagreement_is_reproduced():
    assert owner._poly(HOLE).IsSelfIntersecting()
    shape,expected=bridged();decoded,proof=native.decode_exact_hole_boundaries(shape,time.monotonic()+2.)
    assert len(proof['exact_cycle_false_positive_rechecks'])==1
    assert cut._poly(decoded,cut._Work(time.monotonic()+2.)).equals(expected)


@pytest.mark.parametrize('fault',['cross','touch','reverse','overlap','zero_area'])
def test_forced_native_positive_does_not_hide_real_exact_cycle_faults(monkeypatch,fault):
    holes={
        'cross':[(0,0),(0,100000),(100000,0),(100000,100000),(50000,80000)],
        'touch':[(0,0),(0,100000),(100000,100000),(0,50000),(100000,0)],
        'reverse':[(0,0),(0,100000),(0,50000),(100000,100000),(100000,0)],
        'overlap':[(0,0),(0,100000),(100000,100000),(50000,100000),(100000,0)],
        'zero_area':[(0,0),(0,100000),(0,200000),(0,300000)]}
    hole=holes[fault];anchor=hole[0]
    points=[*OUTER[:3],*hole,anchor,OUTER[2],*OUTER[3:]]
    shape=owner._poly(points);before=shape.Format()
    monkeypatch.setattr(pcbnew.SHAPE_POLY_SET,'IsSelfIntersecting',lambda *a:True)
    with pytest.raises(owner.Refused):
        native.decode_exact_hole_boundaries(shape,time.monotonic()+2.)
    assert shape.Format()==before


@pytest.mark.parametrize('fault',['deadline','exact_pair_budget','native_loss','native_spill','edge_shift'])
def test_independent_work_edge_and_zero_set_change_guards_still_refuse(monkeypatch,fault):
    shape,_=bridged();before=shape.Format();deadline=time.monotonic()+2.
    if fault=='deadline':deadline=time.monotonic()-1.
    elif fault=='exact_pair_budget':
        import cec_exact_outline_topology as exact
        original=exact.require_one_polygon
        monkeypatch.setattr(exact,'require_one_polygon',lambda q,**kw:original(q,**kw,max_pair_checks=1))
    elif fault in ('native_loss','native_spill'):
        actual=pcbnew.SHAPE_POLY_SET.BooleanSubtract;calls=[0]
        def changed(self,other,*args):
            calls[0]+=1
            if calls[0]==(1 if fault=='native_loss' else 2):
                self.RemoveAllContours();self.Append(owner._poly([(0,0),(1,0),(1,1),(0,1)]))
            else:actual(self,other,*args)
        monkeypatch.setattr(pcbnew.SHAPE_POLY_SET,'BooleanSubtract',changed)
    else:
        actual=pcbnew.SHAPE_POLY_SET.Append
        def changed(self,*args):
            if len(args)>=2 and type(args[0]) is int:args=(args[0]+1,*args[1:])
            return actual(self,*args)
        monkeypatch.setattr(pcbnew.SHAPE_POLY_SET,'Append',changed)
    with pytest.raises(owner.Refused):native.decode_exact_hole_boundaries(shape,deadline)
    assert shape.Format()==before


@pytest.mark.parametrize('bypass',[False,True])
def test_cut_fallback_keeps_holes_and_real_bypass_decision(monkeypatch,bypass):
    shape,expected=bridged();before=shape.Format()
    # Exercise exactly the fallback used when native Unfracture changes an
    # edge, without changing the saved native source or any other check.
    def cannot_unfracture(*args,**kwargs):
        raise owner.Refused('native_bridge_contours_or_boundary_edges_changed')
    monkeypatch.setattr(native,'decode_linear_hole_bridges',cannot_unfracture)
    actual=cut._poly(shape,cut._Work(time.monotonic()+2.))
    assert actual.equals(expected) and shape.Format()==before
    from shapely.geometry import LineString
    route=LineString([(20000,95000),(40000,95000)]) if not bypass else LineString([(-500000,-500000),(500000,-500000)])
    assert actual.covers(route) is bypass


@pytest.mark.parametrize('bypass',[False,True])
@pytest.mark.parametrize('duplicate',[False,True])
def test_complete_native_kelvin_audit_still_proves_actual_isolation_or_bypass(tmp_path,monkeypatch,bypass,duplicate):
    from test_kelvin_copper_cut import native_board_fixture,audit,zone
    values=native_board_fixture(tmp_path/'source.kicad_pcb')
    item=zone(values[0],[(88 if bypass else 89.9,72,92 if bypass else 90.1,78)])
    record,_=bridged(offset=30000000)
    filled=item.GetFilledPolysList(pcbnew.F_Cu).CloneDropTriangulation();filled.Append(record)
    if duplicate:filled.Append(record)
    item.SetFilledPolysList(pcbnew.F_Cu,filled);item.SetIsFilled(True);before=filled.Format()
    def cannot_unfracture(*args,**kwargs):
        raise owner.Refused('native_bridge_contours_or_boundary_edges_changed')
    monkeypatch.setattr(native,'decode_linear_hole_bridges',cannot_unfracture)
    r=audit(values)
    assert r['complete'] and r['ok'] is (not bypass),r
    assert r['physical_bypass_proved'] is bypass
    assert item.GetFilledPolysList(pcbnew.F_Cu).Format()==before
