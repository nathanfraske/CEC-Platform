import math
import pytest
import pcbnew
import cec_force_current as force
from test_lastmile import _board
from test_field_proposals import track
from root_native_motion_contact_rebuild_scope_20261013 import inspect


def _track(board,net,start,end,width,layer):
    item=track(board,net,start,end);item.SetWidth(round(width*1e6));item.SetLayer(layer)
    return item


@pytest.mark.parametrize('rotation',range(4))
def test_a_canonical_moved_track_still_needs_reconstruction_when_it_hits_native_copper(rotation):
    source=_board([(20,20,'UNRELATED_A'),(20,16,'UNRELATED_B')])
    candidate=_board([(20,20,'UNRELATED_A'),(20,16,'UNRELATED_B')])
    for board in (source,candidate):
        for fp in board.GetFootprints():fp.Rotate(pcbnew.VECTOR2I(0,0),pcbnew.EDA_ANGLE(rotation*90,pcbnew.DEGREES_T))
    original=_track(source,'UNRELATED_A',(10,20),(30,20),1.,pcbnew.F_Cu)
    moved=pcbnew.Cast_to_PCB_TRACK(pcbnew.Cast_to_BOARD_ITEM(original.Clone()));candidate.Add(moved)
    moved.SetNet(candidate.FindNet('UNRELATED_A'))
    moved.SetStart(pcbnew.VECTOR2I_MM(10,16));moved.SetEnd(pcbnew.VECTOR2I_MM(30,16))
    for t in (original,moved):
        t.Rotate(pcbnew.VECTOR2I(0,0),pcbnew.EDA_ANGLE(rotation*90,pcbnew.DEGREES_T))
    before=(tuple(original.GetStart()),tuple(moved.GetStart()))
    result=inspect(source,candidate,[force._uid(original)],clearance_for=lambda net:200000)
    assert result['complete'] and result['rebuild_track_uuids']==[force._uid(original)]
    row=result['tracks'][0]
    assert row['candidate_canonical'] and row['source_native_clear'] and not row['candidate_native_clear']
    assert before==(tuple(original.GetStart()),tuple(moved.GetStart()))
    assert not result['automatic_retirement_authorized'] and not result['release_authority']


@pytest.mark.parametrize('case',['clear','inherited','another_layer'])
def test_no_new_clearance_is_credited_and_inherited_faults_are_not_a_new_motion_cut(case):
    source=_board([(20,20,'A'),(20,16,'B')]);candidate=_board([(20,20,'A'),(20,16,'B')])
    y=16 if case=='inherited' else 20
    layer=pcbnew.B_Cu if case=='another_layer' else pcbnew.F_Cu
    original=_track(source,'A',(10,y),(30,y),1.,layer)
    moved=pcbnew.Cast_to_PCB_TRACK(pcbnew.Cast_to_BOARD_ITEM(original.Clone()));candidate.Add(moved);moved.SetNet(candidate.FindNet('A'))
    cy=y if case=='clear' else 16
    moved.SetStart(pcbnew.VECTOR2I_MM(10,cy));moved.SetEnd(pcbnew.VECTOR2I_MM(30,cy))
    result=inspect(source,candidate,[force._uid(original)],clearance_for=lambda net:200000)
    assert result['rebuild_track_uuids']==[] and not result['clearance_qualified']


@pytest.mark.parametrize('budget',[True,0,-1,math.nan,math.inf,10.1])
def test_only_finite_bounded_explicit_motion_inventory_is_allowed(budget):
    board=_board([(20,20,'A')]);t=_track(board,'A',(10,20),(30,20),1.,pcbnew.F_Cu)
    with pytest.raises(ValueError):inspect(board,board,[force._uid(t)],clearance_for=lambda n:200000,timeout_s=budget)


@pytest.mark.parametrize('change',['width','layer','lock','net','stale_scope'])
def test_motion_inventory_never_authorizes_a_hidden_geometry_or_identity_change(change):
    source=_board([(20,20,'A'),(20,16,'B')]);candidate=_board([(20,20,'A'),(20,16,'B')])
    original=_track(source,'A',(10,20),(30,20),1.,pcbnew.F_Cu)
    moved=pcbnew.Cast_to_PCB_TRACK(pcbnew.Cast_to_BOARD_ITEM(original.Clone()));candidate.Add(moved)
    moved.SetNet(candidate.FindNet('A'));uid=force._uid(original)
    if change=='width':moved.SetWidth(999999)
    elif change=='layer':moved.SetLayer(pcbnew.B_Cu)
    elif change=='lock':moved.SetLocked(True)
    elif change=='net':moved.SetNet(candidate.FindNet('B'))
    else:uid='missing-actual-track'
    with pytest.raises(ValueError):inspect(source,candidate,[uid],clearance_for=lambda n:200000)
