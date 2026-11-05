from types import SimpleNamespace
from unittest.mock import patch

import pcbnew
import cec_pair_semantics as semantics
import cec_constraints
import cec_precision_route
import cec_staged_fr
import cec_priority_recovery


def board_with_inputs(value='INA240A2DR', pins=('8', '1'), names=('sensor/P_P', 'sensor/P_N')):
    board = pcbnew.BOARD()
    footprint = pcbnew.FOOTPRINT(board)
    footprint.SetReference('U99')
    footprint.SetValue(value)
    board.Add(footprint)
    for pin, name in zip(pins, names):
        net = pcbnew.NETINFO_ITEM(board, name)
        board.Add(net)
        pad = pcbnew.PAD(footprint)
        pad.SetNumber(pin)
        pad.SetNet(net)
        footprint.Add(pad)
    return board


def add_nets(board, names):
    for name in names:
        board.Add(pcbnew.NETINFO_ITEM(board, name))


def test_known_analog_inputs_use_device_pins_not_reference_or_net_spelling():
    board = board_with_inputs()
    assert semantics.coupled_pair_names(board) == []
    witness = semantics.analog_input_pairs(board)
    assert witness == [dict(kind='kelvin_input', p='sensor/P_P', n='sensor/P_N',
                            device='INA240', ref='U99', pins=['8', '1'])]
    # Changing the name or placing the device anywhere cannot change its role.
    renamed = board_with_inputs(names=('arbitrary/positive', 'other/negative'))
    assert len(semantics.analog_input_pairs(renamed)) == 1


def test_unknown_parts_or_wrong_pins_cannot_waive_diff_pair_checks():
    for board in (board_with_inputs(value='INA299'), board_with_inputs(pins=('6', '7'))):
        assert semantics.coupled_pair_names(board) == [('diff', 'sensor/P_P', 'sensor/P_N')]


def test_vbus_is_not_misidentified_as_current_input():
    assert not semantics.analog_input_pairs(board_with_inputs(value='INA238', pins=('8', '9')))
    assert len(semantics.analog_input_pairs(board_with_inputs(value='INA238', pins=('10', '9')))) == 1


def test_routing_and_signoff_share_full_hierarchy_and_series_pair_membership():
    board = board_with_inputs()
    names = ['/A/CAN_H', '/A/CAN_L', '/B/CAN_H', '/B/CAN_L',
             '/A/CAN_H_INT', '/A/CAN_L_INT', '/USB_DP_ESD', '/USB_DM_ESD',
             '/unpaired/CAN_H', '/elsewhere/CAN_L']
    add_nets(board, names)
    expected = semantics.coupled_pair_names(board)
    assert len(expected) == 4
    assert ('can', '/A/CAN_H_INT', '/A/CAN_L_INT') in expected
    assert ('usb', '/USB_DP_ESD', '/USB_DM_ESD') in expected
    assert cec_constraints._coupled_pair_names(board) == expected
    with patch.object(cec_precision_route.cec_score.Rules, 'from_board',
                      return_value=SimpleNamespace(diff_pairs=[])), \
            patch.object(cec_precision_route, '_netclass_geometry', return_value={}):
        pairs = cec_precision_route.derive_coupled_pairs('none', board=board)
    assert [(row['kind'], row['p'], row['n']) for row in pairs] == expected
    assert len({row['name'] for row in pairs}) == len(pairs)


def test_tier_ownership_is_atomic_and_independent_of_later_unrouted_pairs():
    declared = [dict(p='P', n='N'), dict(p='NEXT_P', n='NEXT_N')]
    summary = dict(ok=False, pairs=[dict(p='P', n='N', violations=[]),
                                   dict(p='NEXT_P', n='NEXT_N', violations=['open'])])
    assert cec_staged_fr.tier_pair_physics(summary, ['P', 'N'], declared)['ok']
    summary['pairs'][0]['violations'] = ['asymmetric via count']
    assert not cec_staged_fr.tier_pair_physics(summary, ['P'], declared)['ok']
    assert not cec_staged_fr.tier_pair_physics({}, ['P', 'N'], declared)['ok']


def test_saved_board_failures_skip_search_but_never_count_as_admission():
    row = dict(prefix={'ok': True}, placement_unchanged=True,
               score_admission={'accepted': True}, independent_pair_signoff_ok=True,
               pair_physics={'ok': True})
    assert cec_priority_recovery.constructive_validation_eligible(row)
    for field in row:
        partial = dict(row)
        partial.pop(field)
        assert not cec_priority_recovery.constructive_validation_eligible(partial)
        assert not cec_priority_recovery.candidate_admitted(partial)
    row['pair_physics']['ok'] = False
    assert cec_priority_recovery.failure_stack(row) == ['pair_physics']
