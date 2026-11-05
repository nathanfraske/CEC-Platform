"""Placement screening must agree with the existing authored-pour gate."""
import pcbnew
import pytest
import cec_constraints as constraints
import cec_pi_cleanup as cleanup
import cec_field_coupling as field
from test_pi_pose_native_rule_areas import fixture


def zone(board,face,net,points=None):
    found=board.FindNet(net)
    if found is None:
        found=pcbnew.NETINFO_ITEM(board,net);board.Add(found)
    z=pcbnew.ZONE(board);z.SetNet(found);z.SetLayer(face)
    z.SetZoneName('GND plane is only an untrusted label')
    z.Outline().NewOutline()
    for x,y in points or ((8,8),(12,8),(12,12),(8,12)):
        z.Outline().Append(round(x*1e6),round(y*1e6))
    z.SetLocalClearance(200000);z.SetMinThickness(100000);board.Add(z)
    board.BuildConnectivity();assert pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    return z


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('angle',[0,90,180,270])
def test_filler_clearance_hole_does_not_grant_a_reserved_power_seat(face,angle):
    b,fp=fixture(face,angle);z=zone(b,face,'/different/power')
    pad=next(iter(fp.Pads()));native=z.GetFilledPolysList(face)
    assert not native.Collide(pad.GetEffectiveShape(face),0)
    assert constraints.laid_pour_incursion_summary(b)['n_parts']==1
    before=field._field_snapshot_inventory(b)
    with pytest.raises(ValueError,match='PI_pose_reserved_laid_pour'):
        cleanup._pose_preflight(b,fp)
    assert before==field._field_snapshot_inventory(b)


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_reservation_uses_native_pad_edge_not_just_centre(face):
    b,fp=fixture(face);pad=next(iter(fp.Pads()));pad.SetSize(pcbnew.VECTOR2I_MM(1,1))
    z=zone(b,face,'/edge/power',((10.4,8),(12,8),(12,12),(10.4,12)))
    assert not z.Outline().Contains(pad.GetPosition())
    with pytest.raises(ValueError,match='PI_pose_reserved_laid_pour'):
        cleanup._pose_native_permissions(b,fp)


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('kind',['own_net','other_face','reference','concave'])
def test_existing_exceptions_and_true_native_empty_seats_remain_available(face,kind):
    b,fp=fixture(face);pad=next(iter(fp.Pads()))
    target_face=pcbnew.B_Cu if face==pcbnew.F_Cu else pcbnew.F_Cu
    net='/other/power';points=None
    if kind=='own_net':net=pad.GetNetname();target_face=face
    elif kind=='reference':net='GND';target_face=face
    elif kind=='concave':
        target_face=face;points=((8,8),(12,8),(12,8.8),(8.8,8.8),(8.8,12),(8,12))
    zone(b,target_face,net,points)
    assert constraints.laid_pour_incursion_summary(b)['n_parts']==0
    cleanup._pose_preflight(b,fp)


def test_declared_power_plane_keeps_its_existing_role_exception():
    b,fp=fixture();props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';b.SetProperties(props)
    zone(b,b.GetLayerID('In3.Cu'),'/actual/power-plane')
    assert not constraints.laid_pour_regions(b)
    cleanup._pose_native_permissions(b,fp)
    assert constraints.laid_pour_regions(b,exclude_plane=False)


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_future_pose_preclear_cannot_route_away_a_power_reservation(face):
    import cec_future_pose_clearance as future
    b,fp=fixture(face);original=next(iter(fp.Pads()));second=pcbnew.PAD(fp)
    second.SetNumber('2');second.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    second.SetShape(pcbnew.PAD_SHAPE_RECT);second.SetSize(pcbnew.VECTOR2I_MM(.4,.4))
    second.SetPosition(pcbnew.VECTOR2I_MM(10.4,10));second.SetNet(original.GetNet())
    second.SetLayerSet(original.GetLayerSet());fp.Add(second)
    zone(b,face,'/future/power',((11.8,9),(13,9),(13,11),(11.8,11)))
    # The current part is outside; the detached future pose alone is illegal.
    assert constraints.laid_pour_incursion_summary(b)['n_parts']==0
    before=field._field_snapshot_inventory(b)
    with pytest.raises(ValueError,match='PI_pose_reserved_laid_pour'):
        future._future_pads(b,{fp.GetReference():[12,10,0]})
    assert before==field._field_snapshot_inventory(b)
