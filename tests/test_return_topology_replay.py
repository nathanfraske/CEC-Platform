"""Created and reused qualified returns must use the same physical metric."""
import pytest
import pcbnew
import cec_decoupler_cell as cell
import cec_synth_pipeline as synth
import test_decoupler_cell as native_fixtures


@pytest.mark.parametrize('side', ['front', 'back'])
def test_reused_native_pofv_retains_topology_without_new_copper(tmp_path, side):
    board, _ = native_fixtures.DecouplerCellTests()._board()
    fp = board.FindFootprintByReference('C1')
    if side == 'back':
        fp.Flip(fp.FindPadByNumber('2').GetPosition(), False)
    pad = fp.FindPadByNumber('2')
    first, error = cell._add_ground_return(board, pad, board_path='', reach_mm=1.5, lock=True)
    assert error is None and first['status'] == 'via-in-pad'
    ids = {item.m_Uuid.AsString() for item in board.GetTracks()}
    for attempt in range(2):
        if attempt:
            path = tmp_path / 'roundtrip.kicad_pcb'
            pcbnew.SaveBoard(str(path), board)
            board = pcbnew.LoadBoard(str(path))
            pad = board.FindFootprintByReference('C1').FindPadByNumber('2')
        reused, error = cell._add_ground_return(board, pad, board_path='', reach_mm=1.5, lock=True)
        assert error is None and reused['status'] == 'covered'
        assert cell.qualified_via_in_pad_return(reused)
        assert not reused['items'] and reused['via_uuid'] == first['via_uuid']
        assert {item.m_Uuid.AsString() for item in board.GetTracks()} == ids


@pytest.mark.parametrize('fault', ['no_profile', 'nearby', 'through_hole', 'blind', 'foreign'])
def test_only_a_native_qualified_land_gets_reuse_topology(fault):
    board, _ = native_fixtures.DecouplerCellTests()._board()
    pad = board.FindFootprintByReference('C1').FindPadByNumber('2')
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(pad.GetPosition()); via.SetWidth(pcbnew.FromMM(.35)); via.SetDrill(pcbnew.FromMM(.25))
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); via.SetNetCode(pad.GetNetCode()); board.Add(via)
    if fault == 'no_profile':
        props = board.GetProperties(); props['CEC_FAB_PROFILE'] = 'jlcpcb_4l_standard'; board.SetProperties(props)
    elif fault == 'nearby':
        at = pad.GetPosition(); via.SetPosition(pcbnew.VECTOR2I(at.x + pcbnew.FromMM(1), at.y))
    elif fault == 'through_hole': pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    elif fault == 'blind':
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.In1_Cu); via.SetViaType(pcbnew.VIATYPE_BLIND)
    elif fault == 'foreign': via.SetNetCode(0)
    assert cell._existing_return_topology(board, pad, via) == {}


def test_reuse_and_construction_have_equal_proximity_verdicts():
    tangent = {'best_loop': {'supply_mm': 2.35, 'loop_proxy_mm': 4.20}}
    fresh = dict(status='via-in-pad')
    reused = dict(status='covered', return_topology='via-in-pad', topology_qualified=True, via_uuid='measured')
    def grade(return_row):
        return synth._decoupler_proximity_gate('GND', 2.635, 1.577, tangent,
            dict(ground_return=return_row, owner_ground_return=return_row))
    assert grade(fresh) == grade(reused)
    assert not grade(reused)['bad']
    for unproven in (dict(status='covered'), dict(reused, topology_qualified=False), dict(reused, via_uuid=None)):
        assert grade(unproven)['bad']
        assert grade(unproven)['mode'] == 'isolated_tangent_supply'
