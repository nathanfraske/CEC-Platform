"""An unchanged regenerated pour must retain its persistent ownership identity."""
import pcbnew
import pytest
import cec_fr


def fixture():
    board = pcbnew.BOARD()
    board.Add(pcbnew.NETINFO_ITEM(board, 'arbitrary-rail'))
    declaration = dict(net='arbitrary-rail', layer='B.Cu', name='pour:arbitrary',
                       polygon=[(0,0),(8,0),(8,8),(0,8)],
                       holes=[[(2,2),(2,3),(3,3),(3,2)]])
    zone = cec_fr.add_power_pours(board, [declaration])[0]
    return board, declaration, zone


def test_unchanged_replacement_retains_identity_and_group_membership():
    board, declaration, zone = fixture()
    identity = zone.m_Uuid.AsString()
    group = pcbnew.PCB_GROUP(board); group.SetName('arbitrary-owner')
    board.Add(group); group.AddItem(zone)
    for _ in range(2):
        report = cec_fr.replace_generated_power_pours(
            board, [declaration], managed_nets={'arbitrary-rail'})
        zones = list(board.Zones())
        assert len(zones) == 1
        assert zones[0].m_Uuid.AsString() == identity
        assert group.ContainsItem(zones[0])
        assert report['identity_preserved'] == 1


@pytest.mark.parametrize('change', ['outline','hole','priority','minimum','connection','clearance'])
def test_changed_geometry_or_fill_policy_does_not_claim_original_identity(change):
    board, declaration, zone = fixture()
    if change == 'connection': zone.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    elif change == 'clearance': zone.SetLocalClearance(pcbnew.FromMM(.6))
    original = zone.m_Uuid.AsString()
    if change == 'outline': declaration['polygon'] = [(0,0),(9,0),(9,8),(0,8)]
    elif change == 'hole': declaration['holes'] = []
    elif change == 'priority': declaration['priority'] = 7
    elif change == 'minimum': declaration['min_thickness'] = .3
    cec_fr.replace_generated_power_pours(board, [declaration], managed_nets={'arbitrary-rail'})
    assert list(board.Zones())[0].m_Uuid.AsString() != original


def test_unmanaged_zone_identity_is_not_touched():
    board, declaration, zone = fixture()
    identity = zone.m_Uuid.AsString()
    cec_fr.replace_generated_power_pours(board, [declaration], managed_nets={'unrelated'})
    assert len(list(board.Zones())) == 1
    assert zone.m_Uuid.AsString() == identity


def test_closed_rotated_and_reversed_rings_are_the_same_exact_geometry(tmp_path):
    board, declaration, zone = fixture()
    identity = zone.m_Uuid.AsString()
    points = declaration['polygon']
    points = list(reversed(points[2:] + points[:2]))
    declaration['polygon'] = points + [points[0]]
    hole = list(reversed(declaration['holes'][0]))
    declaration['holes'] = [hole + [hole[0]]]
    result = cec_fr.replace_generated_power_pours(
        board, [declaration], managed_nets={'arbitrary-rail'})
    assert result['identity_preserved'] == 1
    path = str(tmp_path/'reload.kicad_pcb')
    pcbnew.SaveBoard(path, board)
    loaded = pcbnew.LoadBoard(path)
    assert list(loaded.Zones())[0].m_Uuid.AsString() == identity
