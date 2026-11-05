"""Native field relocation cannot hide barrel loss or unsupported layer geometry."""
import pcbnew
import pytest
import cec_via_field_layout as fields
import cec_rectilinear_copper as native
from test_purposeful_landings import fixture
from cec_local_copper_cell import copper_inventory


def field_fixture(angle=0,mirror=False):
    b,t,at=fixture(angle,mirror);net=t.GetNet();b.Remove(t)
    zs=[]
    for layer,pts in [(pcbnew.F_Cu,[(-4,-4),(4,-4),(4,4),(-4,4)]),
                      (pcbnew.B_Cu,[(-2,-2),(3.2,-2),(3.2,2),(-2,2)])]:
        z=pcbnew.ZONE(b);z.SetNet(net);z.SetLayer(layer);z.SetLocalClearance(200000)
        z.SetMinThickness(100000);z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        z.Outline().NewOutline()
        for x,y in pts:
            pt=at(x,y);z.Outline().Append(pt.x,pt.y)
        b.Add(z);zs.append(z)
    vs=[]
    sites=[(x*1.3,y*1.3) for x in (-1,0,1) for y in (-1,0,1)]+[(2.6,0)]
    for x,y in sites:
        v=pcbnew.PCB_VIA(b);v.SetNet(net);v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetPosition(at(x,y));v.SetWidth(900000);v.SetDrill(500000)
        v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v);vs.append(v)
    b.BuildConnectivity();assert pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    return b,vs,zs,at


def plan(b,vs,zs):
    return fields.plan_owned_field(b,[v.m_Uuid.AsString() for v in vs],
        center_zone_uuid=zs[0].m_Uuid.AsString(),expand_zone_uuids=[zs[1].m_Uuid.AsString()],
        pitch_nm=1300000,reach_nm=2600000,clearance_nm=200000)


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
def test_ten_barrels_receive_exact_symmetry_dimensions_and_full_native_landings(tmp_path,angle,mirror):
    b,vs,zs,at=field_fixture(angle,mirror);old=copper_inventory(b);proposal=plan(b,vs,zs)
    assert copper_inventory(b)==old and proposal['field_shape']['centered']
    fields.materialize_owned_field(b,proposal);b.BuildConnectivity()
    assert pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    path=tmp_path/'native-field.kicad_pcb';pcbnew.SaveBoard(str(path),b)
    received=fields.receive_owned_field(pcbnew.LoadBoard(str(path)),proposal)
    assert received['ok'] and received['barrel_count']==10 and not received['new_capacity_credited']
    assert not received['release_authority'] and received['source_landing_copper_preserved']


@pytest.mark.parametrize('fault',['barrel','lock','center_outline','center_fill','seats_rehash','count_rehash','expansion_rehash'])
def test_stale_or_rehashed_owner_never_mutates_existing_field(fault):
    b,vs,zs,at=field_fixture();proposal=plan(b,vs,zs)
    if fault=='barrel':vs[0].SetDrill(510000)
    elif fault=='lock':vs[0].SetLocked(True)
    elif fault=='center_outline':zs[0].Move(pcbnew.VECTOR2I(1,0))
    elif fault=='center_fill':zs[0].UnFill()
    elif fault=='seats_rehash':proposal['seats_by_uuid'][vs[0].m_Uuid.AsString()][0]+=1
    elif fault=='count_rehash':proposal['source_vias'].pop()
    else:proposal['expanded_zones'][0]['polygon_nm'][0][0]-=1
    if fault.endswith('rehash'):
        proposal.pop('plan_sha256');proposal['plan_sha256']=native._digest(proposal)
    old=copper_inventory(b)
    with pytest.raises(native.Refused):fields.materialize_owned_field(b,proposal)
    assert copper_inventory(b)==old


@pytest.mark.parametrize('fault',['drill','missing_barrel','unfilled','outline','one_nm_landing_loss'])
def test_saved_native_receiving_refuses_actual_barrel_or_landing_damage(fault):
    b,vs,zs,at=field_fixture();proposal=plan(b,vs,zs);fields.materialize_owned_field(b,proposal)
    b.BuildConnectivity();assert pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    if fault=='drill':vs[0].SetDrill(510000)
    elif fault=='missing_barrel':b.Remove(vs[0])
    elif fault=='unfilled':zs[1].UnFill()
    elif fault=='outline':zs[1].Outline().Append(30000000,30000000)
    else:
        v=vs[0].GetPosition();cut=native._poly([(v.x,v.y),(v.x+1,v.y),(v.x+1,v.y+1),(v.x,v.y+1)])
        actual=zs[0].GetFilledPolysList(pcbnew.F_Cu).CloneDropTriangulation();actual.BooleanSubtract(cut)
        zs[0].SetFilledPolysList(pcbnew.F_Cu,actual)
    with pytest.raises(native.Refused):fields.receive_owned_field(b,proposal)


def test_interior_layer_obstacle_is_not_ignored_by_top_view_symmetry():
    b,vs,zs,at=field_fixture();net=pcbnew.NETINFO_ITEM(b,'/INNER_LAYER_BUS');b.Add(net)
    t=pcbnew.PCB_TRACK(b);t.SetNet(net);t.SetLayer(pcbnew.In2_Cu)
    t.SetStart(at(-4,0));t.SetEnd(at(4,0));t.SetWidth(8000000);b.Add(t)
    with pytest.raises(native.Refused,match='foreign_all_layer_barrel_clearance'):plan(b,vs,zs)


def test_real_resident_support_track_is_bound_and_does_not_hide_a_changed_source():
    b,vs,zs,at=field_fixture();t=pcbnew.PCB_TRACK(b);t.SetNet(vs[0].GetNet())
    t.SetLayer(pcbnew.F_Cu);t.SetStart(at(-3,0));t.SetEnd(at(3,0));t.SetWidth(3000000);b.Add(t)
    proposal=plan(b,vs,zs);assert proposal['supporting_tracks'][str(pcbnew.F_Cu)]
    fields.materialize_owned_field(b,proposal);b.BuildConnectivity();assert pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    assert fields.receive_owned_field(b,proposal)['ok']
    t.SetWidth(3000001)
    with pytest.raises(native.Refused,match='native_support_track_changed'):fields.receive_owned_field(b,proposal)


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
def test_joint_recompile_is_centered_on_complete_native_barrels_not_old_oversized_zone(tmp_path,angle,mirror):
    b,vs,zs,at=field_fixture(angle,mirror);before=copper_inventory(b)
    p=fields.plan_owned_field(b,[v.m_Uuid.AsString() for v in vs],
        center_zone_uuid=zs[0].m_Uuid.AsString(),expand_zone_uuids=[zs[1].m_Uuid.AsString()],
        pitch_nm=1300000,reach_nm=2600000,clearance_nm=200000,
        rebuild_center_landing=True,required_center_width_nm=4000000)
    assert copper_inventory(b)==before
    assert p['old_center_fill_preserved'] is False
    assert p['center_reference']=='exact_native_barrel_centroid'
    fields.materialize_owned_field(b,p);b.BuildConnectivity();assert pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    path=tmp_path/'saved-joint.kicad_pcb';pcbnew.SaveBoard(str(path),b)
    r=fields.receive_owned_field(pcbnew.LoadBoard(str(path)),p)
    assert r['ok'] and r['barrel_count']==10 and r['field_shape']['centered'],r
    assert not r['source_landing_copper_preserved'] and r['other_landing_copper_preserved']
    assert not r['new_capacity_credited'] and not r['release_authority']


@pytest.mark.parametrize('fault',['omit','width_type','slab_rehash','center_rehash','changed_source'])
def test_joint_recompile_cannot_hide_missing_barrels_or_rehash_oversized_frames(fault):
    b,vs,zs,at=field_fixture();ids=[v.m_Uuid.AsString() for v in vs]
    kw=dict(center_zone_uuid=zs[0].m_Uuid.AsString(),expand_zone_uuids=[zs[1].m_Uuid.AsString()],
        pitch_nm=1300000,reach_nm=2600000,clearance_nm=200000,
        rebuild_center_landing=True,required_center_width_nm=4000000)
    before=copper_inventory(b)
    if fault=='omit':
        with pytest.raises(native.Refused,match='complete_joint'):fields.plan_owned_field(b,ids[:-1],**kw)
        assert copper_inventory(b)==before;return
    if fault=='width_type':
        kw['required_center_width_nm']=True
        with pytest.raises(native.Refused):fields.plan_owned_field(b,ids,**kw)
        assert copper_inventory(b)==before;return
    p=fields.plan_owned_field(b,ids,**kw)
    if fault=='slab_rehash':p['rebuilt_center_polygon_nm'][0][0]-=1000000
    elif fault=='center_rehash':p['center_nm'][0]+=1
    else:zs[0].SetLocalClearance(200001)
    p.pop('plan_sha256');p['plan_sha256']=native._digest(p)
    before=copper_inventory(b)
    with pytest.raises(native.Refused):fields.materialize_owned_field(b,p)
    assert copper_inventory(b)==before
