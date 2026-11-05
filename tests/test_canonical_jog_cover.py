"""Exact rotated native 45-degree notch closures, not renderer smoothing."""
import time
import copy
import pcbnew
import pytest
from shapely.geometry import Point,Polygon
import cec_rectilinear_copper as owner
from cec_local_copper_cell import copper_inventory
from test_rectilinear_copper import fixture


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_exact_45_kink_is_closed_without_closing_large_placement_pocket(angle,mirror,layer):
    b=pcbnew.BOARD();b.SetCopperLayerCount(6)
    n=pcbnew.NETINFO_ITEM(b,'/RENAMED_NATIVE_572');b.Add(n)
    def at(x,y):
        if mirror:x=-x
        for _ in range(angle//90):x,y=-y,x
        return [30_000_000+x,30_000_000+y]
    # A small H/45/V recess at the top-right, and a real large lower pocket.
    pts=[at(x,y) for x,y in [(0,0),(4_800_000,0),(4_800_000,200_000),
        (5_000_000,400_000),(5_000_000,5_000_000),(3_000_000,5_000_000),
        (3_000_000,2_000_000),(0,2_000_000)]]
    before=copper_inventory(b)
    clean=owner._canonical_jog_cover(b,pts,n.GetNetname(),layer,style='chamfer45',
        max_jog_nm=500_000,clearance_nm=200_000,deadline=time.monotonic()+2)
    loss=owner._poly(pts);loss.BooleanSubtract(owner._poly(clean))
    assert not loss.OutlineCount() and len(clean)<len(pts)
    assert Polygon(clean).covers(Point(*at(4_950_000,100_000)))
    assert not Polygon(clean).covers(Point(*at(1_000_000,4_000_000)))
    assert copper_inventory(b)==before


@pytest.mark.parametrize('kind',['pad','track','zone'])
def test_actual_foreign_material_prevents_45_closure(kind):
    b=pcbnew.BOARD();b.SetCopperLayerCount(6)
    n=pcbnew.NETINFO_ITEM(b,'/FOREIGN_981');b.Add(n)
    pts=[[0,0],[4_800_000,0],[4_800_000,200_000],[5_000_000,400_000],
         [5_000_000,5_000_000],[0,5_000_000]]
    at=pcbnew.VECTOR2I(4_950_000,100_000)
    if kind=='pad':
        fp=pcbnew.FOOTPRINT(b);b.Add(fp);x=pcbnew.PAD(fp);fp.Add(x)
        x.SetPosition(at);x.SetSize(pcbnew.VECTOR2I(20_000,20_000))
        x.SetShape(pcbnew.PAD_SHAPE_RECT);x.SetNet(n)
        ls=pcbnew.LSET();ls.AddLayer(pcbnew.F_Cu);x.SetLayerSet(ls)
    elif kind=='track':
        x=pcbnew.PCB_TRACK(b);x.SetNet(n);x.SetLayer(pcbnew.F_Cu)
        x.SetStart(at);x.SetEnd(pcbnew.VECTOR2I(at.x+10_000,at.y));x.SetWidth(20_000);b.Add(x)
    else:
        x=pcbnew.ZONE(b);x.SetNet(n);x.SetLayer(pcbnew.F_Cu);b.Add(x)
        shape=owner._poly([[4_940_000,90_000],[4_960_000,90_000],
                          [4_960_000,110_000],[4_940_000,110_000]])
        x.SetFilledPolysList(pcbnew.F_Cu,shape);x.SetIsFilled(True)
    clean=owner._canonical_jog_cover(b,pts,'/ACTUAL_SOURCE',pcbnew.F_Cu,
        style='chamfer45',max_jog_nm=500_000,clearance_nm=0,deadline=time.monotonic()+2)
    assert not Polygon(clean).covers(Point(at.x,at.y))


@pytest.mark.parametrize('value',[True,-1,1_000_001])
def test_policy_bounds_and_rehashed_policy_refuse_before_mutation(value):
    b,ts=fixture();ids=[t.m_Uuid.AsString() for t in ts];before=copper_inventory(b)
    with pytest.raises(owner.Refused):
        owner.plan(b,ids,required_width_nm=1_500_000,clearance_nm=200_000,
            min_thickness_nm=100_000,contour_max_jog_nm=value)
    plan=owner.plan(b,ids,required_width_nm=1_500_000,clearance_nm=200_000,
        min_thickness_nm=100_000)
    bad=copy.deepcopy(plan);bad['contour_max_jog_nm']=value;bad.pop('plan_sha256')
    bad['plan_sha256']=owner._digest(bad)
    with pytest.raises(owner.Refused):owner.materialize(b,bad)
    assert copper_inventory(b)==before


def test_union_jog_is_independently_reconstructed_and_native_saved_received(tmp_path):
    b,ts=fixture();ids=[t.m_Uuid.AsString() for t in ts]
    raw=owner.plan(b,ids,required_width_nm=1_500_000,clearance_nm=200_000,
        min_thickness_nm=100_000,contour_style='chamfer45',retire_source_tracks=False)
    p=owner.plan(b,ids,required_width_nm=1_500_000,clearance_nm=200_000,
        min_thickness_nm=100_000,contour_style='chamfer45',retire_source_tracks=False,
        contour_max_jog_nm=1_000_000)
    assert len(p['polygon_nm'])<len(raw['polygon_nm'])
    e=owner.materialize(b,p)
    z=next(z for z in b.Zones() if z.m_Uuid.AsString()==e['zone_uuid'])
    batch=pcbnew.ZONES();batch.append(z);b.BuildConnectivity()
    assert pcbnew.ZONE_FILLER(b).Fill(batch)
    path=tmp_path/'actual-native.kicad_pcb';pcbnew.SaveBoard(str(path),b)
    r=owner.receive(pcbnew.LoadBoard(str(path)),p,e['zone_uuid'])
    assert r['complete'] and r['ok'],r
    assert not r['new_capacity_credited'] and not r['release_authority']


def test_deadline_is_not_silent_noop():
    b=pcbnew.BOARD()
    with pytest.raises(owner.Refused,match='deadline'):
        owner._canonical_jog_cover(b,[[0,0],[1,0],[1,1],[2,1],[2,2],[0,2]],
            '/X',pcbnew.F_Cu,style='square',max_jog_nm=1,clearance_nm=0,
            deadline=time.monotonic()-1)
