"""Via construction must respect native rule areas before final DRC."""
import pcbnew
import pytest
import cec_fr
import cec_slab_pour


def board_area(*, layer=pcbnew.F_Cu, vias=True, rule=True, footprint=False):
    b=pcbnew.BOARD();b.SetCopperLayerCount(6)
    net=pcbnew.NETINFO_ITEM(b,'TEST_RETURN');b.Add(net)
    parent=b
    if footprint:
        parent=pcbnew.FOOTPRINT(b);parent.SetReference('ARBITRARY_BODY');b.Add(parent)
    z=pcbnew.ZONE(parent);z.SetLayer(layer);z.SetIsRuleArea(rule)
    z.SetDoNotAllowVias(vias);z.SetDoNotAllowTracks(True);z.SetZoneName('native test keepout')
    z.Outline().NewOutline()
    for x,y in [(4,4),(9,4),(9,9),(4,9)]:z.Outline().Append(pcbnew.FromMM(x),pcbnew.FromMM(y))
    parent.Add(z)
    return b,net,z


@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.In1_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('footprint',[False,True])
def test_all_copper_layers_and_both_area_owners_block_vias(layer,footprint):
    b,n,z=board_area(layer=layer,footprint=footprint)
    assert cec_fr._overunder_via_conflict_reason(b,n.GetNetCode(),5,5,[])=='native_via_keepout'
    assert cec_fr._overunder_via_conflict_reason(b,n.GetNetCode(),12,12,[]) is None
    assert not cec_slab_pour.via_clear_of_foreign_tracks(b,n.GetNetCode(),5,5)


@pytest.mark.parametrize('rule,vias,layer',[(False,True,pcbnew.F_Cu),(True,False,pcbnew.F_Cu),(True,True,pcbnew.F_Fab)])
def test_permissions_and_layers_are_not_blanket_obstacles(rule,vias,layer):
    b,n,z=board_area(rule=rule,vias=vias,layer=layer)
    assert cec_fr._overunder_via_conflict_reason(b,n.GetNetCode(),5,5,[]) is None


def test_via_land_overlap_not_just_drill_origin():
    b,n,z=board_area()
    assert cec_fr._overunder_via_conflict_reason(b,n.GetNetCode(),3.7,5,[],dia=.9)=='native_via_keepout'
    assert cec_fr._overunder_via_conflict_reason(b,n.GetNetCode(),3.5,5,[],dia=.9) is None


@pytest.mark.parametrize('cached',[False,True])
def test_native_helper_cannot_exempt_same_net_or_miss_keepout_with_cache(cached):
    b,n,z=board_area();report={}
    assert not cec_fr._via_spot_clear(b,pcbnew.VECTOR2I_MM(5,5),pcbnew.FromMM(.6),0,
        {n.GetNetCode()},net_code=n.GetNetCode(),drill_nm=pcbnew.FromMM(.3),
        foreign_cache={} if cached else None,report=report)
    assert report['reason']=='native rule area excludes via land'
    assert report['blockers'][0]['uuid']==z.m_Uuid.AsString()


def test_refused_field_is_not_partially_materialized():
    b,n,z=board_area()
    report={}
    emitted=cec_fr.add_overunder_vias(b,[{'net':n.GetNetname(),'x_mm':5,'y_mm':5}],evidence=report)
    assert not emitted and not list(b.GetTracks())
    assert not report.get('ok',True)


def test_zone_fill_permission_reaches_exact_and_raster_planners():
    import cec_pour_plan
    from shapely.geometry import Point
    from test_slab_pour import _G
    b,n,z=board_area();z.SetDoNotAllowZoneFills(True)
    layers=['F.Cu','In1.Cu']
    records=cec_pour_plan._geo_obstacle_records(b,n.GetNetCode(),layers,.2,0)
    assert any(r['kind']=='native_rule_area' and r['geometry'].covers(Point(5,5)) for r in records['F.Cu'])
    assert not records['In1.Cu']
    grid=_G(30,30,cell=.5)
    foreign,_=cec_slab_pour.rasterize(b,n.GetNetCode(),pcbnew.F_Cu,grid)
    assert foreign[grid.iy(5),grid.ix(5)] and not foreign[grid.iy(12),grid.ix(12)]
    inner,_=cec_slab_pour.rasterize(b,n.GetNetCode(),pcbnew.In1_Cu,grid)
    assert not inner[grid.iy(5),grid.ix(5)]
    # A routing-only keepout must not forbid otherwise permitted fill.
    z.SetDoNotAllowZoneFills(False)
    assert not cec_pour_plan._geo_obstacle_records(b,n.GetNetCode(),layers,.2,0)['F.Cu']


def test_rule_area_hole_is_not_replaced_by_bounding_box():
    import cec_native_rule_areas
    b,n,z=board_area();z.SetDoNotAllowZoneFills(True)
    z.Outline().NewHole(0)
    for x,y in [(5,5),(5,8),(8,8),(8,5)]:
        z.Outline().Append(pcbnew.FromMM(x),pcbnew.FromMM(y),0,0)
    assert cec_native_rule_areas.via_conflict(b,pcbnew.VECTOR2I_MM(6.5,6.5),pcbnew.FromMM(.6)) is None
    assert cec_native_rule_areas.via_conflict(b,pcbnew.VECTOR2I_MM(4.5,4.5),pcbnew.FromMM(.6))
    from shapely.geometry import Point
    obstacle=cec_native_rule_areas.pour_obstacles(b,['F.Cu'])['F.Cu'][0]['geometry']
    assert not obstacle.covers(Point(6.5,6.5)) and obstacle.covers(Point(4.5,4.5))
