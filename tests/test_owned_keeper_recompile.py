"""Owned cover reconstruction never retires or narrows the actual bus."""
import copy
import pcbnew
import pytest
from shapely.geometry import Point, Polygon
import cec_rectilinear_copper as owner
from cec_local_copper_cell import copper_inventory
from test_rectilinear_copper import fixture


def setup(**kw):
    b,ts=fixture(**kw);ids=[t.m_Uuid.AsString() for t in ts]
    old=owner.plan(b,ids,required_width_nm=1_500_000,clearance_nm=200_000,
        min_thickness_nm=100_000,retire_source_tracks=False)
    e=owner.materialize(b,old)
    z=next(z for z in b.Zones() if z.m_Uuid.AsString()==e['zone_uuid'])
    # An owned oversized native cover, not an arbitrary unowned plane.
    z.Outline().RemoveAllContours();z.Outline().NewOutline()
    ends=[at for t in ts for at in (t.GetStart(),t.GetEnd())]
    x0=min(at.x for at in ends)-2_000_000;y0=min(at.y for at in ends)-2_000_000
    x1=max(at.x for at in ends)+2_000_000;y1=max(at.y for at in ends)+2_000_000
    for p in [(x0,y0),(x1,y0),(x1,y1),(x0,y1)]:z.Outline().Append(*p)
    b.BuildConnectivity();assert pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    return b,ts,z


def plan(b,ts,z,**kw):
    ids=[t.m_Uuid.AsString() for t in ts]
    return owner.plan(b,ids,required_width_nm=1_500_000,clearance_nm=200_000,
        min_thickness_nm=100_000,retire_source_tracks=False,
        replace_native_zone_uuid=z.m_Uuid.AsString(),enclosing_native_zone_uuids=[z.m_Uuid.AsString()],
        landing_enclosure_mode='canonical_outline',rebuild_keeper_from_tracks=True,**kw)


@pytest.mark.parametrize('style',['square','chamfer45'])
@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.In3_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('policy',['native','conductor_preserving_regions'])
def test_saved_native_owner_recompile_preserves_real_bus_and_pockets(tmp_path,style,angle,mirror,layer,policy):
    b,ts,z=setup(angle=angle,mirror=mirror,layer=layer);before=copper_inventory(b)
    path=tmp_path/'immutable-source.kicad_pcb';pcbnew.SaveBoard(str(path),b)
    source=pcbnew.LoadBoard(str(path))
    rows=[owner._track_row(t) for t in ts]
    p=plan(b,ts,z,contour_style=style,contour_max_jog_nm=1_000_000,fill_policy=policy)
    assert copper_inventory(b)==before
    ends=[at for t in ts for at in (t.GetStart(),t.GetEnd())]
    pocket=Point((min(at.x for at in ends)+max(at.x for at in ends))//2,
        (min(at.y for at in ends)+max(at.y for at in ends))//2)
    assert not Polygon(p['polygon_nm']).covers(pocket)
    e=owner.materialize(b,p)
    owner.fill(b,p,e['zone_uuid'],regional_source=source)
    path=tmp_path/'private-native.kicad_pcb';pcbnew.SaveBoard(str(path),b)
    saved=pcbnew.LoadBoard(str(path));r=owner.receive(saved,p,e['zone_uuid'],regional_source=source,timeout_s=10.)
    assert r['ok'] and r['complete'],r
    assert r['original_keeper_fill_preserved'] is False
    assert sorted([owner._track_row(t) for t in saved.GetTracks()],key=lambda r:r['uuid']) == sorted(rows,key=lambda r:r['uuid'])
    assert r['original_native_keeper_fill_preserved'] is False
    assert not r['release_authority'] and not r['new_capacity_credited']
    if policy=='conductor_preserving_regions':
        assert r['regional_fill_receiving']['exact_source_copper_preserved'] is False
        assert r['regional_fill_receiving']['independently_replayed_native_additions'] is True


def test_source_inventory_omission_and_later_hidden_branch_are_refused():
    b,ts,z=setup();before=copper_inventory(b)
    with pytest.raises(owner.Refused,match='all_enclosed_native_tracks'):plan(b,ts[:1],z)
    assert copper_inventory(b)==before
    p=plan(b,ts,z)
    extra=ts[0].Duplicate();b.Add(extra)
    with pytest.raises(owner.Refused,match='inventory_changed'):owner.materialize(b,p)


@pytest.mark.parametrize('fault',['no_owner','retire','regions','convex','boolean'])
def test_rehashed_policy_cannot_broaden_scope(fault):
    b,ts,z=setup();p=plan(b,ts,z);bad=copy.deepcopy(p)
    if fault=='no_owner':bad.pop('replacement_source_zone')
    elif fault=='retire':bad['retire_source_tracks']=True
    elif fault=='regions':bad['fill_policy']='source_preserving_regions'
    elif fault=='convex':bad['convex_support_cover']=True
    else:bad['rebuild_keeper_from_tracks']=1
    bad.pop('plan_sha256');bad['plan_sha256']=owner._digest(bad)
    before=copper_inventory(b)
    with pytest.raises(owner.Refused):owner.materialize(b,bad)
    assert copper_inventory(b)==before


def test_saved_receiver_rederives_all_enclosed_native_sources():
    b,ts,z=setup();p=plan(b,ts,z);e=owner.materialize(b,p)
    owner.fill(b,p,e['zone_uuid'])
    extra=ts[0].Duplicate();b.Add(extra)
    r=owner.receive(b,p,e['zone_uuid'])
    assert not r['ok'] and not r['complete'] and 'inventory_changed' in r['reason'],r


def test_recompile_still_requires_exact_keeper_process_configuration():
    b,ts,z=setup();p=plan(b,ts,z);e=owner.materialize(b,p)
    owner.fill(b,p,e['zone_uuid'])
    z.SetMinThickness(z.GetMinThickness()+1)
    r=owner.receive(b,p,e['zone_uuid'])
    assert not r['ok'] and r['reason']=='native_keeper_configuration_changed',r


def test_recompile_cannot_fill_a_higher_priority_native_void():
    b,ts,z=setup()
    high=pcbnew.ZONE(b);high.SetNet(ts[0].GetNet());high.SetLayer(pcbnew.F_Cu)
    high.SetZoneName('OTHER_PROCESS_OWNER');high.SetAssignedPriority(3)
    high.SetMinThickness(100_000);high.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    high.Outline().NewOutline()
    for at in [(29_000_000,29_000_000),(29_400_000,29_000_000),
               (29_400_000,29_400_000),(29_000_000,29_400_000)]:high.Outline().Append(*at)
    b.Add(high)
    high.SetFilledPolysList(pcbnew.F_Cu,owner._poly([(29_200_000,29_200_000),
        (29_400_000,29_200_000),(29_400_000,29_400_000),(29_200_000,29_400_000)]))
    high.SetIsFilled(True)
    p=plan(b,ts,z);e=owner.materialize(b,p)
    # Injecting a native filled profile across the other owner's clearance
    # void must fail even though all selected actual strokes are enclosed.
    z.SetFilledPolysList(pcbnew.F_Cu,owner._poly(p['polygon_nm']));z.SetIsFilled(True)
    r=owner.receive(b,p,e['zone_uuid'])
    assert not r['ok'] and r['reason']=='higher_priority_native_landing_void_changed',r
