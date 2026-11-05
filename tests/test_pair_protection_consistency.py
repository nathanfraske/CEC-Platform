"""Shared semantic pairs must not escape post-route finishing protection."""
import pytest
import pcbnew
import cec_fr as fr
import cec_pair_semantics as semantics


@pytest.mark.parametrize('p,n', [
    ('/BUS/CAN_H_J1', '/BUS/CAN_L_J1'),
    ('/A/B/CAN_H_EXT_STAGE', '/A/B/CAN_L_EXT_STAGE'),
    ('/USB_DP_ESD', '/USB_DM_ESD'),
    ('/A/USB_D+_J2', '/A/USB_D-_J2'),
])
def test_full_series_names_receive_symmetric_pair_protection(p, n):
    assert fr._coupled_pair_partners(p, n)
    assert fr._coupled_pair_partners(n, p)


@pytest.mark.parametrize('p,n', [
    ('/A/CAN_H_J1', '/B/CAN_L_J1'),
    ('/A/CAN_H_J1', '/A/CAN_L_J2'),
    ('/CAN_HIGH_J1', '/CAN_LOW_J1'),
    ('/USB_DP_ESD', '/USB_DM_OTHER'),
    ('/USB_D+_J2', '/OTHER/USB_D-_J2'),
    ('/CAN_H_', '/CAN_L'),
])
def test_no_cross_sheet_suffix_or_approximate_mate_is_invented(p, n):
    assert not fr._coupled_pair_partners(p, n)
    assert not fr._coupled_pair_partners(n, p)


@pytest.mark.parametrize('p,n', [
    ('/GENERIC_P', '/GENERIC_N'),
    ('/SHEET/BUS_H', '/SHEET/BUS_L'),
    ('/LEGACYDP', '/LEGACYDM'),
])
def test_conservative_legacy_protection_is_not_removed(p, n):
    assert fr._coupled_pair_partners(p, n)
    board = pcbnew.CreateEmptyBoard()
    for name in (p, n):
        board.Add(pcbnew.NETINFO_ITEM(board, name))
    assert fr.coupled_pair_nets(board) == {p, n}


def test_every_shared_semantic_pair_is_in_the_finishing_protection_set():
    board = pcbnew.CreateEmptyBoard()
    names = {'/A/CAN_H', '/A/CAN_L', '/B/CAN_H_J1', '/B/CAN_L_J1',
        '/USB_DP_ESD', '/USB_DM_ESD', '/A/USB_D+_J2', '/A/USB_D-_J2',
        '/A/DIFF_P', '/A/DIFF_N', '/missing/CAN_H_J1', '/else/CAN_L_J1',
        '/unpaired/USB_DP_ESD'}
    for name in names:
        board.Add(pcbnew.NETINFO_ITEM(board, name))
    expected = {n for _, p, q in semantics.coupled_pair_names(board) for n in (p, q)}
    assert expected <= fr.coupled_pair_nets(board)
    assert not {'/missing/CAN_H_J1', '/else/CAN_L_J1', '/unpaired/USB_DP_ESD'} & fr.coupled_pair_nets(board)


def test_series_pair_member_cannot_be_chamfered_by_scalar_finishing():
    board = pcbnew.CreateEmptyBoard()
    names = ('/BUS/CAN_H_J1', '/BUS/CAN_L_J1')
    for name in names:
        board.Add(pcbnew.NETINFO_ITEM(board, name))
    net = board.FindNet(names[0])
    for a, b in (((5, 10), (10, 10)), ((10, 10), (10, 15))):
        track = pcbnew.PCB_TRACK(board)
        track.SetStart(pcbnew.VECTOR2I_MM(*a)); track.SetEnd(pcbnew.VECTOR2I_MM(*b))
        track.SetWidth(250000); track.SetLayer(pcbnew.F_Cu); track.SetNet(net)
        board.Add(track)
    before = sorted((t.m_Uuid.AsString(), tuple(t.GetStart()), tuple(t.GetEnd())) for t in board.GetTracks())
    result = fr.chamfer_unlocked_right_angles(board, exclude_nets=fr.coupled_pair_nets(board))
    assert result['chamfered'] == 0
    assert result['skipped']['sensitive'] == 1
    assert before == sorted((t.m_Uuid.AsString(), tuple(t.GetStart()), tuple(t.GetEnd())) for t in board.GetTracks())


def test_board_protection_uses_direct_mate_lookups_not_cartesian_scan(monkeypatch):
    board = pcbnew.CreateEmptyBoard()
    for i in range(256):
        for member in ('H', 'L'):
            board.Add(pcbnew.NETINFO_ITEM(board, f'/S{i}/CAN_{member}_EXT'))
    def no_cartesian_probe(*_):
        raise AssertionError('all-net Cartesian pair scan must not be used')
    monkeypatch.setattr(fr, '_coupled_pair_partners', no_cartesian_probe)
    assert len(fr.coupled_pair_nets(board)) == 512
