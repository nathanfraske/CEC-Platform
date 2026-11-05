import pcbnew
import pytest
import cec_force_current as force
from test_lastmile import _board
from test_field_proposals import track
from root_native_motion_contact_rebuild_scope_20261013 import inspect


@pytest.mark.parametrize('rotation',range(4))
def test_provisional_moved_edge_does_not_create_a_false_stationary_source_cut(rotation):
    source=_board([(10,20,'A'),(20,10,'B')]);candidate=_board([(10,20,'A'),(20,10,'B')])
    fixed=track(source,'A',(10,20),(30,20));pending=track(source,'B',(23,14),(27,14))
    copies=[]
    for item in (fixed,pending):
        copied=pcbnew.Cast_to_PCB_TRACK(pcbnew.Cast_to_BOARD_ITEM(item.Clone()))
        candidate.Add(copied);copied.SetNet(candidate.FindNet(item.GetNetname()));copies.append(copied)
    copies[1].Move(pcbnew.VECTOR2I_MM(0,6))
    for board in (source,candidate):
        for item in [*board.GetFootprints(),*board.GetTracks()]:
            item.Rotate(pcbnew.VECTOR2I(0,0),pcbnew.EDA_ANGLE(rotation*90,pcbnew.DEGREES_T))
    ids=[force._uid(t) for t in (fixed,pending)]
    real=inspect(source,candidate,ids,clearance_for=lambda n:200000)
    assert force._uid(fixed) in real['rebuild_track_uuids']
    ordered=inspect(source,candidate,ids,clearance_for=lambda n:200000,
        transient_reconstruction_track_uuids=[force._uid(pending)])
    assert force._uid(fixed) not in ordered['rebuild_track_uuids']
    assert force._uid(pending) in ordered['rebuild_track_uuids']
    assert not ordered['clearance_qualified'] and not ordered['automatic_retirement_authorized']


def test_a_real_native_barrel_cannot_be_excluded_as_a_temporary_stroke():
    board=_board([(10,20,'A')]);t=track(board,'A',(10,20),(30,20))
    via=pcbnew.PCB_VIA(board);via.SetPosition(pcbnew.VECTOR2I_MM(20,20))
    via.SetWidth(600000);via.SetDrill(300000);via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetNet(board.FindNet('A'));board.Add(via)
    with pytest.raises(ValueError):
        inspect(board,board,[force._uid(t)],clearance_for=lambda n:200000,
            transient_reconstruction_track_uuids=[force._uid(via)])
