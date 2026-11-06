"""Monitor upper supply seats are not decouplers or new current ratings."""
import copy
import time
import pcbnew
import pytest
import cec_programming_resistor_placement as programming
import cec_macro_priority_reconstruction as pending
from test_programming_monitor_divider_placement import moving_pair


def fixture(tmp_path, monkeypatch, turn=0, back=False):
    board, child, owner, lower, upper, root, poses, rail = moving_pair(
        tmp_path, monkeypatch, turn, back)
    selected = programming.plan(board, poses, board_hint=str(root))
    proposal = dict(poses=poses, board_hint=str(root), selected_programming_resistors=selected)
    requests = programming.requests(board, child, proposal)
    pad = upper.FindPadByNumber('1')
    return board, child, upper, pad, proposal, requests, str(root), rail


@pytest.mark.parametrize('turn', [0, 90, 180, 270])
@pytest.mark.parametrize('back', [False, True])
def test_source_upper_role_requires_fresh_full_rail_request_not_bypass_alias(tmp_path, monkeypatch, turn, back):
    board, child, upper, pad, proposal, requests, hint, rail = fixture(tmp_path, monkeypatch, turn, back)
    def no_bypass(*args): raise AssertionError('A monitor resistor must not become a bypass')
    monkeypatch.setattr(pending.leaf, '_bypass_supply_owner', no_bypass)
    cache = {}
    kind, role, reference = pending._supply_owner(board, child, proposal, pad, requests,
        hint, time.monotonic()+10., cache)
    assert kind == 'source_selected_monitor_divider' and reference == upper.GetReference()
    assert role['rail'] == pad.GetNetname() and role['unchanged_full_rail_current_contract'] == rail
    assert not role['bypass_owner'] and not role['new_current_authority'] and not role['barrel_capacity_qualified']
    assert role['required_full_rail_request_id'] in requests
    assert cache['monitor_requests'] == requests


@pytest.mark.parametrize('fault', ['source_claim', 'request_missing', 'request_current',
    'request_width', 'owner_motion', 'upper_value', 'upper_net', 'wrong_pad'])
def test_unknown_or_changed_owner_cannot_receive_priority_motion(tmp_path, monkeypatch, fault):
    board, child, upper, pad, proposal, requests, hint, rail = fixture(tmp_path, monkeypatch)
    request = requests['monitor_divider_supply:' + pending.force._uid(pad)]
    if fault == 'source_claim':
        next(iter(proposal['selected_programming_resistors'].values()))['source_monitor_divider']['supply_net'] = 'forged'
    elif fault == 'request_missing': del requests['monitor_divider_supply:' + pending.force._uid(pad)]
    elif fault == 'request_current':
        request['unchanged_full_rail_current_contract'] = copy.deepcopy(rail)
        request['unchanged_full_rail_current_contract']['required_by_layer_nm'][0] //= 2
    elif fault == 'request_width': request['width_nm'] //= 2
    elif fault == 'owner_motion': child.FindFootprintByReference('U_program').Move(pcbnew.VECTOR2I(1, 0))
    elif fault == 'upper_value': child.FindFootprintByReference(upper.GetReference()).SetValue('forged')
    elif fault == 'upper_net': child.FindFootprintByReference(upper.GetReference()).FindPadByNumber('1').SetNetCode(0)
    else: pad = upper.FindPadByNumber('2')
    with pytest.raises(ValueError):
        pending._supply_owner(board, child, proposal, pad, requests, hint, time.monotonic()+10., {})
