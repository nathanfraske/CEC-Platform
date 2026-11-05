"""Real reserved contours guide proposals, never weaken native placement."""
import math
import pcbnew
import pytest
import cec_reserved_pour_pose_events as events
import cec_cell_contact_frontier as contact
import cec_pi_cleanup as pi
import cec_force_current as force
import cec_field_coupling as field
from test_pi_pose_native_rule_areas import fixture
from test_pi_pose_laid_pour_reservations import zone


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('angle',[0,90,180,270])
def test_actual_reserved_outline_proposes_clear_native_translations_without_mutation(face,angle):
    b,fp=fixture(face,angle);z=zone(b,face,'/foreign/power')
    original=field._field_snapshot_inventory(b)
    with pytest.raises(ValueError,match='PI_pose_reserved_laid_pour'):pi._pose_preflight(b,fp)
    report=events.propose(b,fp,force._uid(z))
    assert report['events_nm'] and report['native_conflicting_faces']==[int(face)]
    assert report['exact_reserved_contours_not_filled_antipads']
    assert not report['placement_authority'] and not report['routing_admitted'] and not report['release_authority']
    assert field._field_snapshot_inventory(b)==original
    for dx,dy in report['events_nm']:
        assert (dx==0)!=(dy==0)
        old=fp.GetPosition();fp.Move(pcbnew.VECTOR2I(dx,dy))
        try:pi._pose_preflight(b,fp)
        finally:fp.SetPosition(old)
    assert field._field_snapshot_inventory(b)==original
    reason='PI_pose_reserved_laid_pour:'+force._uid(z)
    assert contact._events(b,fp.GetReference(),reason)==[tuple(p) for p in report['events_nm']]


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_concave_empty_pocket_is_not_replaced_by_the_whole_zone_bbox(face):
    b,fp=fixture(face);fp.Move(pcbnew.VECTOR2I(-1400000,0))
    z=zone(b,face,'/hook/power',((8,8),(12,8),(12,8.8),(8.8,8.8),(8.8,12),(8,12)))
    with pytest.raises(ValueError,match='PI_pose_reserved_laid_pour'):pi._pose_preflight(b,fp)
    report=events.propose(b,fp,force._uid(z))
    local=[p for p in report['events_nm'] if p[1]==0 and 0<p[0]<1500000]
    assert local,report
    fp.Move(pcbnew.VECTOR2I(*local[0]));pad=next(iter(fp.Pads()))
    assert 8<pad.GetPosition().x/1e6<12 and 8<pad.GetPosition().y/1e6<12
    pi._pose_preflight(b,fp)


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('kind',['same_net','opposite_face','ground_plane','unknown_uuid','not_a_zone'])
def test_nonconflicting_roles_or_unknown_identity_do_not_invent_a_reservation(face,kind):
    b,fp=fixture(face);pad=next(iter(fp.Pads()))
    other=pcbnew.B_Cu if face==pcbnew.F_Cu else pcbnew.F_Cu
    z=zone(b,other if kind=='opposite_face' else face,
        pad.GetNetname() if kind=='same_net' else 'GND' if kind=='ground_plane' else '/foreign/power')
    uid=force._uid(z) if kind not in ('unknown_uuid','not_a_zone') else (
        'missing-native-zone' if kind=='unknown_uuid' else force._uid(pad))
    original=field._field_snapshot_inventory(b);report=events.propose(b,fp,uid)
    assert not report['events_nm'] and field._field_snapshot_inventory(b)==original


def test_every_foreign_pad_must_clear_not_only_the_first_colliding_pad():
    b,fp=fixture();pad=next(iter(fp.Pads()));second=pcbnew.PAD(fp)
    second.SetNumber('another-pin');second.SetNet(pad.GetNet());second.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    second.SetShape(pcbnew.PAD_SHAPE_RECT);second.SetSize(pad.GetSize());second.SetLayerSet(pad.GetLayerSet())
    second.SetPosition(pad.GetPosition()+pcbnew.VECTOR2I(1800000,0));fp.Add(second)
    z=zone(b,pcbnew.F_Cu,'/array/power');report=events.propose(b,fp,force._uid(z))
    assert report['events_nm']
    original=fp.GetPosition()
    for dx,dy in report['events_nm']:
        fp.SetPosition(original+pcbnew.VECTOR2I(dx,dy))
        try:pi._pose_native_permissions(b,fp)
        finally:fp.SetPosition(original)


@pytest.mark.parametrize('options',[{'max_events':True},{'max_events':0},{'max_events':65},
    {'max_candidates':3},{'max_vertices':True},{'max_vertices':3},{'timeout_s':0},
    {'timeout_s':True},{'timeout_s':2.001},{'timeout_s':float('nan')}])
def test_invalid_or_unbounded_event_work_is_not_a_permission(options):
    with pytest.raises(ValueError,match='bounded_native_reserved_pour_events'):
        events.propose(None,None,'not-read',**options)


def test_finite_small_candidate_budget_is_explicit_and_still_never_admits_a_pose():
    b,fp=fixture();z=zone(b,pcbnew.F_Cu,'/finite/power')
    report=events.propose(b,fp,force._uid(z),max_candidates=4,max_events=1)
    assert report['candidate_translations']<=4 and len(report['events_nm'])<=1
    assert not report['complete'] and not report['placement_authority']
