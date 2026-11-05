"""Generation and recovery share the same bounded native-pad flare budget."""
import pcbnew
import pytest
import cec_fr


@pytest.mark.parametrize('major,length,expected', [
    (1.45,1.175,1), (1.45,1.176,0), (4.,1.5,1), (4.,1.501,0),
    (.4,.75,1), (.4,.751,0)])
def test_recovery_matches_independent_qualification(major,length,expected):
    from test_lastmile import _board
    board=_board([(5,5,'/ANONYMOUS_POWER')],edge=(0,0,15,10))
    pad=next(iter(next(iter(board.GetFootprints())).Pads()))
    pad.SetSize(pcbnew.VECTOR2I_MM(major,.3))
    net=board.GetNetInfo().GetNetItem('/ANONYMOUS_POWER')
    narrow=pcbnew.PCB_TRACK(board)
    narrow.SetStart(pad.GetPosition());narrow.SetEnd(pcbnew.VECTOR2I_MM(5+length,5))
    narrow.SetWidth(pcbnew.FromMM(.2));narrow.SetLayer(pcbnew.F_Cu);narrow.SetNet(net)
    board.Add(narrow)
    trunk=pcbnew.PCB_TRACK(board);trunk.SetStart(narrow.GetEnd())
    trunk.SetEnd(pcbnew.VECTOR2I_MM(10,5));trunk.SetWidth(pcbnew.FromMM(.5))
    trunk.SetLayer(pcbnew.F_Cu);trunk.SetNet(net);board.Add(trunk)
    qualified,rejected=cec_fr._qualified_endpoint_neckdown_tracks(
        board,[narrow],pcbnew.FromMM(.5),required_clearance=pcbnew.FromMM(.2))
    report=cec_fr.reconcile_endpoint_neckdown_groups(board,
        netclass_resolver=lambda _:dict(track_width=.5,clearance=.2))
    assert len(qualified)==report['recovered']==expected,(report,rejected)
    if not expected:assert rejected[0]['reason']=='escape_budget_exceeded'


def test_long_elongated_escape_still_needs_full_width_throat():
    from test_lastmile import _board
    board=_board([(5,5,'/N')],edge=(0,0,15,10))
    pad=next(iter(next(iter(board.GetFootprints())).Pads()))
    pad.SetSize(pcbnew.VECTOR2I_MM(1.45,.3))
    narrow=pcbnew.PCB_TRACK(board);narrow.SetStart(pad.GetPosition())
    narrow.SetEnd(pcbnew.VECTOR2I_MM(6.175,5));narrow.SetWidth(pcbnew.FromMM(.2))
    narrow.SetLayer(pcbnew.F_Cu);narrow.SetNet(pad.GetNet());board.Add(narrow)
    report=cec_fr.reconcile_endpoint_neckdown_groups(board,
        netclass_resolver=lambda _:dict(track_width=.5,clearance=.2))
    assert report['recovered']==0
