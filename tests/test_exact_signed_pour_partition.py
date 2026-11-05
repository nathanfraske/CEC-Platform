"""Native windows survive simple-polygon and rectangle-only guard consumers."""
import copy,time
import pcbnew
import pytest
from shapely.geometry import Polygon,Point
from shapely.ops import unary_union
import cec_exact_outline_topology as topology
import cec_constraints as constraints
from test_exact_outline_topology import transformed,OUTER,HOLE,PEER


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('chamfer',[False,True])
def test_exact_native_window_partition_has_zero_loss_spill_or_phantom_hole_fill(angle,mirror,chamfer):
    outer=OUTER if not chamfer else [[0,1000],[1000,0],[9000,0],[10000,1000],
        [10000,9000],[9000,10000],[1000,10000],[0,9000]]
    shape=transformed([outer,HOLE,PEER],angle,mirror);original=copy.deepcopy(shape)
    rows=topology.partition_one_polygon(shape,deadline_monotonic=time.monotonic()+2.)
    actual=unary_union([Polygon(p) for p in rows]);expected=Polygon(shape[0][0],shape[0][1:])
    assert actual.equals(expected) and shape==original
    assert sum(Polygon(p).area for p in rows)==expected.area
    assert all(len(p) in (3,4) for p in rows)


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('angle',[0,90,180,270])
def test_canonical_native_recovery_keeps_cardinal_windows_out_of_absolute_guard_boxes(tmp_path,monkeypatch,face,angle):
    b=pcbnew.BOARD();n=pcbnew.NETINFO_ITEM(b,'/renamed_force_HI');b.Add(n)
    z=pcbnew.ZONE(b);z.SetNet(n);z.SetLayer(face);z.SetZoneName('orthofill:renamed')
    polygons=transformed([OUTER,HOLE,PEER],angle)
    for i,ring in enumerate(polygons[0]):
        if i==0:z.Outline().NewOutline()
        else:z.Outline().NewHole(0)
        for x,y in ring:z.Outline().Append(x*1000,y*1000,0,i-1)
    b.Add(z);path=tmp_path/'renamed.kicad_pcb';original=z.Outline().Format()
    monkeypatch.delenv('CEC_POURFIRST_STATE',raising=False)
    rows=constraints.canonical_high_current_pours(str(path),board=b)
    assert rows and all(r['zone_uuid']==z.m_Uuid.AsString() and not r['capacity_qualified'] for r in rows)
    expected=Polygon(polygons[0][0],polygons[0][1:])
    actual=unary_union([Polygon([[x*1000,y*1000] for x,y in r['polygon']]) for r in rows])
    assert actual.equals(expected) and z.Outline().Format()==original
    rects=constraints._exact_pour_rectangles(rows)
    for hole in polygons[0][1:]:
        x,y=Polygon(hole).representative_point().coords[0];x/=1000;y/=1000
        assert not any(r['x0']<=x<=r['x1'] and r['y0']<=y<=r['y1'] for r in rects)


@pytest.mark.parametrize('fault',['piece_budget','deadline','touching_hole','non45'])
def test_no_partition_or_unknown_geometry_can_be_accepted_by_relaxation(fault):
    shape=copy.deepcopy([[OUTER,HOLE]]);options={}
    deadline=time.monotonic()+2.
    if fault=='piece_budget':options['max_pieces']=1
    elif fault=='deadline':deadline=time.monotonic()-1.
    elif fault=='touching_hole':shape[0][1][0][0]=0
    else:shape[0][1][0][0]+=1
    with pytest.raises(ValueError):
        topology.partition_one_polygon(shape,deadline_monotonic=deadline,**options)
