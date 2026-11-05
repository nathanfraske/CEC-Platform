"""Complete-cell consumers retain the distinct stationary-MOS passive scope."""
import copy
import pcbnew
import pytest
import cec_cell_escape_replan as escape
import cec_complete_cell_receiving as saved
import cec_native_cell_pose_domains as domains
import cec_device_power_roles as device_roles
from test_control_gate_bias_placement import fixture, projected


@pytest.mark.parametrize('turn', [0, 90, 180, 270])
@pytest.mark.parametrize('back', [False, True])
def test_complete_source_compiler_records_passive_not_new_IC_or_bypass(tmp_path, monkeypatch, turn, back):
    data = fixture(tmp_path, monkeypatch, turn=turn, back=back)
    monkeypatch.setattr(escape.constraints, '_device_bypass_assignment', lambda *a, **k: {'assigned': {}})
    before = escape.row._source_binding(data['board'])
    result = escape.prepare(data['board'], data['poses'], board_hint=str(data['root']))
    assert set(result['selected_control_gate_biases']) == set(data['poses'])
    assert not result['device_contracts'] and not result['selected_bypasses']
    assert 'selected_control_pullups' not in result and 'selected_control_shunts' not in result
    assert device_roles.footprint_contract(data['mos']) is None
    assert result['retired_track_uuids'] == []
    assert escape.row._source_binding(data['board']) == before


@pytest.mark.parametrize('turn', [0, 90, 180, 270])
@pytest.mark.parametrize('back', [False, True])
def test_actual_saved_motion_rederives_gate_and_every_original_contact(tmp_path, monkeypatch, turn, back):
    data = fixture(tmp_path, monkeypatch, turn=turn, back=back)
    child, proposal = projected(data)
    monkeypatch.setattr(saved, '_assignments', lambda *a: {})
    actual, moved = saved._poses(data['board'], child, str(data['root']))
    assert actual.keys() == data['poses'].keys() and moved == set(data['poses'])
    for ref, pose in actual.items():
        assert pose[:2] == data['poses'][ref][:2]
        assert (pose[2]-data['poses'][ref][2]) % 360 == 0
    child.FindFootprintByReference(data['mos'].GetReference()).Move(pcbnew.VECTOR2I(1, 0))
    with pytest.raises(ValueError):
        saved._poses(data['board'], child, str(data['root']))


@pytest.mark.parametrize('other', ['shunt', 'pullup'])
def test_gate_bias_cannot_alias_an_independent_source_passive_role(tmp_path, monkeypatch, other):
    data = fixture(tmp_path, monkeypatch)
    owner = escape.control_shunt if other == 'shunt' else escape.control_pullup
    name = 'plan' if other == 'shunt' else 'complete_plan'
    monkeypatch.setattr(owner, name, lambda *a, **k: {data['bias'].GetReference(): {'wrong_alias': True}})
    with pytest.raises(ValueError, match='disjoint_source_control_passive_roles_required'):
        escape.prepare(data['board'], data['poses'], board_hint=str(data['root']))


def test_gate_bias_cannot_steal_a_bypass_assignment(tmp_path, monkeypatch):
    data = fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(escape.constraints, '_device_bypass_assignment', lambda *a, **k: {'assigned': {
        'actual_other_source_role': {'cap_ref': data['bias'].GetReference(), 'requirement': {'ref': 'other'}}}})
    with pytest.raises(ValueError, match='control_gate_bias_cannot_alias_power_bypass'):
        escape.prepare(data['board'], data['poses'], board_hint=str(data['root']))


def test_no_ground_terminal_is_not_a_claim_of_good_ground_return(tmp_path, monkeypatch):
    data = fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(escape.constraints, '_device_bypass_assignment', lambda *a, **k: {'assigned': {}})
    proposal = escape.prepare(data['board'], data['poses'], board_hint=str(data['root']))
    result = domains._pose_ground_screen(data['board'], proposal,
        board_hint=str(data['root']), timeout_s=1., complete_owner_ground=True)
    assert result['not_applicable'] and result['ground_terminal_count'] == 0
    assert result['source_typed_gate_bias_only'] and not result['source_typed_pullup_only']
    assert not result['new_ground_barrel_authority'] and not result['routing_admitted']
    del proposal['selected_control_gate_biases']
    with pytest.raises(ValueError):
        domains._pose_ground_screen(data['board'], proposal,
            board_hint=str(data['root']), timeout_s=1., complete_owner_ground=True)
