"""Locality proofs do not depend on a rebuilt global connectivity graph."""
from unittest import mock

import pcbnew
import cec_decoupler_cell as cell
import test_decoupler_cell as fixtures


def test_geometry_proof_observes_add_remove_and_move_without_global_rebuild():
    board, _ = fixtures.DecouplerCellTests()._board()
    pad = board.FindFootprintByReference('C1').FindPadByNumber('2')
    p = pad.GetPosition()
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(pcbnew.VECTOR2I(p.x + pcbnew.FromMM(.8), p.y))
    via.SetWidth(pcbnew.FromMM(.6)); via.SetDrill(pcbnew.FromMM(.3))
    via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    via.SetNetCode(pad.GetNetCode()); board.Add(via)
    track = pcbnew.PCB_TRACK(board)
    track.SetStart(p); track.SetEnd(via.GetPosition())
    track.SetWidth(pcbnew.FromMM(.2)); track.SetLayer(pcbnew.F_Cu)
    track.SetNetCode(pad.GetNetCode())
    with mock.patch.object(pcbnew.BOARD, 'BuildConnectivity',
                           side_effect=AssertionError('global graph is not a locality proof')):
        assert cell._existing_return(board, pad, 1.5) is None
        board.Add(track)
        assert cell._existing_return(board, pad, 1.5)[0] == .8
        # Move beyond the exact endpoint: no cache may retain its old proof.
        via.SetPosition(pcbnew.VECTOR2I(p.x + pcbnew.FromMM(1.3), p.y))
        assert cell._existing_return(board, pad, 1.5) is None
        via.SetPosition(track.GetEnd())
        assert cell._existing_return(board, pad, 1.5)[0] == .8
        cell.discard_items(board, [track])
        assert cell._existing_return(board, pad, 1.5) is None
