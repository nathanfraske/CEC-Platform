import math
import pcbnew
import pytest
import cec_force_current as force
from test_lastmile import _board
from test_field_proposals import track
from root_native_motion_impact_scope_20261013 import scope
from root_native_motion_contact_rebuild_scope_20261013 import inspect


def pair(rotation=0, shift=(0,0), via=False):
    source=_board([(20,20,'RENAMED_A'),(20,16,'RENAMED_B')])
    candidate=_board([(20,20,'RENAMED_A'),(20,16,'RENAMED_B')])
    before=list(source.GetFootprints());after=list(candidate.GetFootprints())
    for a,b in zip(before,after):
        b.m_Uuid.Clone(a.m_Uuid)
        for p,q in zip(a.Pads(),b.Pads()):q.m_Uuid.Clone(p.m_Uuid)
    t=track(source,'RENAMED_A',(10,20),(30,20))
    clone=pcbnew.Cast_to_PCB_TRACK(pcbnew.Cast_to_BOARD_ITEM(t.Clone()))
    candidate.Add(clone);clone.SetNet(candidate.FindNet('RENAMED_A'))
    if via:
        root=pcbnew.PCB_VIA(source);root.SetPosition(pcbnew.VECTOR2I_MM(20,16))
        root.SetWidth(600000);root.SetDrill(300000);root.SetViaType(pcbnew.VIATYPE_THROUGH)
        root.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);root.SetNet(source.FindNet('RENAMED_B'));source.Add(root)
        moved=pcbnew.Cast_to_PCB_VIA(pcbnew.Cast_to_BOARD_ITEM(root.Clone()))
        candidate.Add(moved);moved.SetNet(candidate.FindNet('RENAMED_B'));moved.Move(pcbnew.VECTOR2I_MM(0,4))
    else:
        root=next(f for f in before if any(p.GetNetname()=='RENAMED_B' for p in f.Pads()))
        moved=next(f for f in after if force._uid(f)==force._uid(root))
        moved.Move(pcbnew.VECTOR2I_MM(0,4))
    for board in (source,candidate):
        for item in [*board.GetFootprints(),*board.GetTracks()]:
            item.Rotate(pcbnew.VECTOR2I(0,0),pcbnew.EDA_ANGLE(rotation*90,pcbnew.DEGREES_T))
            item.Move(pcbnew.VECTOR2I_MM(*shift))
    return source,candidate,t,force._uid(root)


@pytest.mark.parametrize('rotation',range(4))
@pytest.mark.parametrize('via',[False,True])
@pytest.mark.parametrize('shift',[(0,0),(5,-3)])
def test_stationary_tracks_hit_by_moved_foreign_native_items_are_not_missed(rotation,via,shift):
    source,candidate,t,owner=pair(rotation,shift,via)
    result=scope(source,candidate,[owner],clearance_nm=200000)
    assert force._uid(t) in result['audit_track_uuids']
    debt=inspect(source,candidate,result['audit_track_uuids'],clearance_for=lambda n:200000)
    assert force._uid(t) in debt['rebuild_track_uuids']
    assert not result['automatic_retirement_authorized'] and not result['release_authority']


@pytest.mark.parametrize('bad',[True,0,-1,math.nan,math.inf,10.1])
def test_bounded_source_identity_and_finite_work_remain_required(bad):
    source,candidate,t,owner=pair()
    with pytest.raises(ValueError):scope(source,candidate,[owner],clearance_nm=200000,timeout_s=bad)


def test_missing_source_item_is_not_permission_for_retirement():
    source,candidate,t,owner=pair()
    with pytest.raises(ValueError):scope(source,candidate,['missing-owner'],clearance_nm=200000)


def test_distant_silk_fields_do_not_make_an_unrelated_route_a_copper_repair_target():
    source,candidate,t,owner=pair()
    unrelated=track(source,'RENAMED_A',(70,70),(75,70))
    clone=pcbnew.Cast_to_PCB_TRACK(pcbnew.Cast_to_BOARD_ITEM(unrelated.Clone()))
    candidate.Add(clone);clone.SetNet(candidate.FindNet('RENAMED_A'))
    for b in (source,candidate):
        fp=next(f for f in b.GetFootprints() if force._uid(f)==owner)
        fp.Reference().SetPosition(pcbnew.VECTOR2I_MM(100,100));fp.Reference().SetLayer(pcbnew.F_SilkS)
    r=scope(source,candidate,[owner],clearance_nm=200000)
    assert force._uid(t) in r['audit_track_uuids']
    assert force._uid(unrelated) not in r['audit_track_uuids']
    assert r['non_copper_fields_not_used_as_copper_scope']


def test_copper_field_is_still_an_actual_native_obstacle_window():
    source,candidate,t,owner=pair()
    unrelated=track(source,'RENAMED_A',(70,70),(75,70))
    clone=pcbnew.Cast_to_PCB_TRACK(pcbnew.Cast_to_BOARD_ITEM(unrelated.Clone()))
    candidate.Add(clone);clone.SetNet(candidate.FindNet('RENAMED_A'))
    for b in (source,candidate):
        fp=next(f for f in b.GetFootprints() if force._uid(f)==owner)
        fp.Reference().SetVisible(True);fp.Reference().SetLayer(pcbnew.F_Cu)
        fp.Reference().SetPosition(pcbnew.VECTOR2I_MM(72,70))
    r=scope(source,candidate,[owner],clearance_nm=200000)
    assert force._uid(unrelated) in r['audit_track_uuids']


def test_explicit_abandoned_boundary_seed_is_always_a_mandatory_audit_without_owning_other_routes():
    source,candidate,t,owner=pair();uid=force._uid(t)
    other=track(source,'RENAMED_A',(70,70),(75,70))
    clone=pcbnew.Cast_to_PCB_TRACK(pcbnew.Cast_to_BOARD_ITEM(other.Clone()))
    candidate.Add(clone);clone.SetNet(candidate.FindNet('RENAMED_A'))
    moving=next(x for x in candidate.GetTracks() if force._uid(x)==uid)
    moving.SetEnd(pcbnew.VECTOR2I_MM(100,100))
    r=scope(source,candidate,[uid],clearance_nm=200000,provisional_reconstruction_track_uuids=[uid])
    assert r['audit_track_uuids']==[uid]
    assert r['provisional_endpoint_seeds_are_mandatory_audit_and_reconstruction_only']==[uid]
    assert not r['automatic_retirement_authorized']
    with pytest.raises(ValueError):scope(source,candidate,[owner],clearance_nm=200000,
        provisional_reconstruction_track_uuids=[uid])
