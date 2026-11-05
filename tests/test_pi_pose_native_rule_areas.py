"""Local poses must observe native body/pad permissions on their actual face."""
import pcbnew
import pytest
import cec_pi_cleanup as cleanup
import cec_field_coupling as field
from test_lastmile import _board


def fixture(face=pcbnew.F_Cu,angle=0):
    board=_board([(10,10,'/renamed_ordinary')],edge=(0,0,30,30));board.SetCopperLayerCount(6)
    fp=board.FindFootprintByReference('X1');fp.SetReference('ANY_RENAMED_PART');fp.SetLayer(face)
    p=next(iter(fp.Pads()));layers=pcbnew.LSET();layers.AddLayer(face);p.SetLayerSet(layers)
    # A closed native courtyard deliberately extends beyond the copper land.
    court=pcbnew.B_CrtYd if face==pcbnew.B_Cu else pcbnew.F_CrtYd
    for a,b in (((9,9),(11,9)),((11,9),(11,11)),((11,11),(9,11)),((9,11),(9,9))):
        g=pcbnew.PCB_SHAPE(fp);g.SetShape(pcbnew.SHAPE_T_SEGMENT)
        g.SetStart(pcbnew.VECTOR2I_MM(*a));g.SetEnd(pcbnew.VECTOR2I_MM(*b))
        g.SetWidth(50000);g.SetLayer(court);fp.Add(g)
    if angle:fp.Rotate(fp.GetPosition(),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
    return board,fp


def rule(board,face,permission,points):
    z=pcbnew.ZONE(board);z.SetIsRuleArea(True);z.SetLayer(face)
    z.SetDoNotAllowTracks(False);z.SetDoNotAllowVias(False);z.SetDoNotAllowZoneFills(False)
    z.SetDoNotAllowFootprints(permission=='footprints');z.SetDoNotAllowPads(permission=='pads')
    if permission=='tracks':z.SetDoNotAllowTracks(True)
    poly=z.Outline();poly.NewOutline()
    for x,y in points:poly.Append(round(x*1e6),round(y*1e6))
    board.Add(z);return z


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('angle',[0,90,180,270])
def test_native_body_only_keepout_rejects_all_rotations_without_source_mutation(face,angle):
    b,fp=fixture(face,angle);rule(b,face,'footprints',[(10.7,9.8),(10.9,9.8),(10.9,10.2),(10.7,10.2)])
    before=field._field_snapshot_inventory(b)
    with pytest.raises(ValueError,match='PI_pose_native_footprint_keepout'):cleanup._pose_preflight(b,fp)
    assert before==field._field_snapshot_inventory(b)


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('angle',[0,90,180,270])
def test_native_pad_only_keepout_is_not_net_exempt(face,angle):
    b,fp=fixture(face,angle);rule(b,face,'pads',[(9.8,9.8),(10.2,9.8),(10.2,10.2),(9.8,10.2)])
    with pytest.raises(ValueError,match='PI_pose_native_pad_keepout'):cleanup._pose_preflight(b,fp)


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('permission',['pads','footprints'])
def test_opposite_face_and_permission_do_not_invent_a_body_prohibition(face,permission):
    b,fp=fixture(face);other=pcbnew.B_Cu if face==pcbnew.F_Cu else pcbnew.F_Cu
    rule(b,other,permission,[(9,9),(11,9),(11,11),(9,11)])
    cleanup._pose_preflight(b,fp)


@pytest.mark.parametrize('permission',['pads','tracks'])
def test_body_overlap_alone_is_not_a_pad_or_track_prohibition(permission):
    b,fp=fixture();rule(b,pcbnew.F_Cu,permission,[(10.7,9.8),(10.9,9.8),(10.9,10.2),(10.7,10.2)])
    cleanup._pose_preflight(b,fp)


def test_concave_native_permission_is_not_a_bounding_box_keepout():
    b,fp=fixture();rule(b,pcbnew.F_Cu,'footprints',[(8,8),(12,8),(12,8.8),(8.8,8.8),(8.8,12),(8,12)])
    cleanup._pose_preflight(b,fp)


def test_pad_only_area_over_actual_land_does_not_require_footprint_flag():
    b,fp=fixture();z=rule(b,pcbnew.F_Cu,'pads',[(9.8,9.8),(10.2,9.8),(10.2,10.2),(9.8,10.2)])
    assert not z.GetDoNotAllowFootprints()
    with pytest.raises(ValueError,match='PI_pose_native_pad_keepout'):cleanup._pose_preflight(b,fp)


@pytest.mark.parametrize('permission',['pads','footprints'])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_future_land_compiler_checks_same_native_body_and_pad_permissions(permission,face):
    import cec_future_pose_clearance as future
    b,fp=fixture(face)
    original=next(iter(fp.Pads()));second=pcbnew.PAD(fp);second.SetNumber('2')
    second.SetAttribute(pcbnew.PAD_ATTRIB_SMD);second.SetShape(pcbnew.PAD_SHAPE_RECT)
    second.SetSize(pcbnew.VECTOR2I_MM(.4,.4));second.SetPosition(pcbnew.VECTOR2I_MM(10.4,10))
    second.SetNet(original.GetNet());second.SetLayerSet(original.GetLayerSet());fp.Add(second)
    points=([(12.7,9.8),(12.9,9.8),(12.9,10.2),(12.7,10.2)] if permission=='footprints'
            else [(11.8,9.8),(12.2,9.8),(12.2,10.2),(11.8,10.2)])
    rule(b,face,permission,points);before=field._field_snapshot_inventory(b)
    with pytest.raises(ValueError,match='PI_pose_native_'):
        future._future_pads(b,{fp.GetReference():[12,10,0]})
    assert before==field._field_snapshot_inventory(b)
