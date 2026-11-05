"""Actual pad/barrel-boundary construction retains independent receiving gates."""
import copy
import pcbnew
import pytest
import cec_rectilinear_copper as owner
from test_purposeful_landings import fixture
from cec_local_copper_cell import copper_inventory


def link_fixture(angle=0,mirror=False,layer=pcbnew.F_Cu):
    b,t,at=fixture(angle,mirror,layer);pad=next(iter(next(iter(b.GetFootprints())).Pads()))
    t.SetStart(at(0,0));t.SetEnd(at(-2,2));t.SetWidth(1000000)
    second=pcbnew.PCB_TRACK(b);second.SetNet(t.GetNet());second.SetLayer(layer)
    second.SetStart(at(-2,2));second.SetEnd(at(-4,4));second.SetWidth(1000000);b.Add(second)
    v=pcbnew.PCB_VIA(b);v.SetNet(t.GetNet());v.SetPosition(at(-5,4));v.SetWidth(900000)
    v.SetDrill(500000);v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v)
    return b,[t,second],pad,v


def plan(b,ts,p,v,width=1800000):
    return owner.plan_power_link_rebuild(b,[t.m_Uuid.AsString() for t in ts],
        source_pad_uuid=p.m_Uuid.AsString(),target_via_uuids=[v.m_Uuid.AsString()],
        required_width_nm=width,clearance_nm=200000)


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_renamed_rotated_mirrored_actual_native_link_receives_after_save(tmp_path,angle,mirror,layer):
    b,ts,p,v=link_fixture(angle,mirror,layer);old=copper_inventory(b)
    proposal=plan(b,ts,p,v);assert copper_inventory(b)==old
    assert proposal['target_width_nm']==1800000
    owner.materialize_power_link_rebuild(b,proposal)
    path=tmp_path/'native-link.kicad_pcb';pcbnew.SaveBoard(str(path),b)
    received=owner.receive_power_link_rebuild(pcbnew.LoadBoard(str(path)),proposal)
    assert received['ok'] and not received['release_authority'] and not received['new_capacity_credited']
    assert all(owner._centerline_allowed(a,z,'chamfer45') for a,z in zip(proposal['path_nm'],proposal['path_nm'][1:]))


def test_existing_wider_segment_is_reserved_and_never_narrowed():
    b,ts,p,v=link_fixture();ts[0].SetWidth(2500000)
    proposal=plan(b,ts,p,v);assert proposal['target_width_nm']==2500000
    owner.materialize_power_link_rebuild(b,proposal)
    assert all(t.GetWidth()==2500000 for t in ts)
    assert owner.receive_power_link_rebuild(b,proposal)['ok']


@pytest.mark.parametrize('fault',['stale_track','stale_pad_size','stale_via','lock','path_rehash','floor_rehash','source_at_joint','disconnected'])
def test_stale_or_unowned_recompile_never_mutates_native_copper(fault):
    b,ts,p,v=link_fixture();proposal=plan(b,ts,p,v)
    if fault=='stale_track':ts[0].Move(pcbnew.VECTOR2I(1000,0))
    elif fault=='stale_pad_size':p.SetSize(pcbnew.VECTOR2I_MM(2.1,2))
    elif fault=='stale_via':v.Move(pcbnew.VECTOR2I(1000,0))
    elif fault=='lock':ts[0].SetLocked(True)
    elif fault=='source_at_joint':p.SetPosition(ts[0].GetEnd())
    elif fault=='disconnected':ts[1].Move(pcbnew.VECTOR2I(1,0))
    elif fault=='path_rehash':proposal['path_nm'][1][0]+=1
    else:proposal['target_width_nm']-=1
    if fault.endswith('rehash'):
        proposal.pop('plan_sha256');proposal['plan_sha256']=owner._digest(proposal)
    old=copper_inventory(b)
    with pytest.raises(owner.Refused):owner.materialize_power_link_rebuild(b,proposal)
    assert copper_inventory(b)==old


def test_all_actual_barrels_changed_or_tiny_annular_contact_refuses_saved_link():
    b,ts,p,v=link_fixture();proposal=plan(b,ts,p,v);owner.materialize_power_link_rebuild(b,proposal)
    v.SetDrill(510000)
    with pytest.raises(owner.Refused,match='barrel_boundary'):owner.receive_power_link_rebuild(b,proposal)


def test_foreign_filled_landing_is_a_real_obstacle_not_a_filler_excuse():
    b,ts,p,v=link_fixture();n=pcbnew.NETINFO_ITEM(b,'/UNRELATED_LANDING');b.Add(n)
    z=pcbnew.ZONE(b);z.SetNet(n);z.SetLayer(pcbnew.F_Cu);z.Outline().NewOutline()
    for x,y in [(20,20),(40,20),(40,40),(20,40)]:z.Outline().Append(x*1000000,y*1000000)
    b.Add(z);z.SetFilledPolysList(pcbnew.F_Cu,z.Outline().CloneDropTriangulation());z.SetIsFilled(True)
    with pytest.raises(owner.Refused,match='no_clear_owned_link'):plan(b,ts,p,v)


@pytest.mark.parametrize('required',[-1,0,True,100000001])
def test_invalid_current_floor_is_not_new_authority(required):
    b,ts,p,v=link_fixture()
    with pytest.raises(owner.Refused):plan(b,ts,p,v,required)


def test_width_only_recompile_is_received_and_cannot_rehash_endpoints(tmp_path):
    b,ts,p,v=link_fixture();uid=ts[0].m_Uuid.AsString()
    proposal=owner.plan_width_recompile(b,[uid],required_width_nm=1800000)
    owner.materialize_width_recompile(b,proposal)
    path=tmp_path/'width.kicad_pcb';pcbnew.SaveBoard(str(path),b)
    assert owner.receive_width_recompile(pcbnew.LoadBoard(str(path)),proposal)['ok']
    ts[0].Move(pcbnew.VECTOR2I(1,0))
    with pytest.raises(owner.Refused):owner.receive_width_recompile(b,proposal)


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
def test_joined_link_uses_one_native_chamfer_not_mutually_voiding_sibling_covers(tmp_path,angle,mirror):
    b,ts,p,v=link_fixture(angle,mirror);proposal=plan(b,ts,p,v)
    owner.materialize_power_link_rebuild(b,proposal)
    contour=owner.plan(b,[t.m_Uuid.AsString() for t in ts],clearance_nm=200000,
        min_thickness_nm=100000,required_width_nm=1800000,contour_style='chamfer45',
        contour_grid_nm=1000,fill_envelope_margin_nm=4,retire_source_tracks=False,convex_support_cover=True)
    emitted=owner.materialize(b,contour);b.BuildConnectivity();assert pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    path=tmp_path/'joined-link.kicad_pcb';pcbnew.SaveBoard(str(path),b)
    saved=pcbnew.LoadBoard(str(path));assert owner.receive(saved,contour,emitted['zone_uuid'])['ok']
    assert owner.receive_power_link_rebuild(saved,proposal)['ok']


def test_rehashed_convex_cover_is_not_a_license_for_arbitrary_copper_slabs():
    b,ts,p,v=link_fixture();proposal=plan(b,ts,p,v);owner.materialize_power_link_rebuild(b,proposal)
    contour=owner.plan(b,[t.m_Uuid.AsString() for t in ts],clearance_nm=200000,
        min_thickness_nm=100000,required_width_nm=1800000,contour_style='chamfer45',
        retire_source_tracks=False,convex_support_cover=True)
    contour['polygon_nm'][0][0]+=1;contour.pop('plan_sha256');contour['plan_sha256']=owner._digest(contour)
    old=copper_inventory(b)
    with pytest.raises(owner.Refused):owner.materialize(b,contour)
    assert copper_inventory(b)==old
