"""Ratified routing data must not downgrade the shared GPU current domain.

These tests check actual policy/provider semantics, not fan loading, contact
or barrel ampacity, startup/flyback or release qualification.
"""
import cec_board_policy as policy
import cec_current_topology as topology
import cec_synth_pipeline as synth


def test_complete_distinct_fan_return_has_approved_current_and_original_margin():
    contract = synth.spec_net_current_contract('12vhpwr-standard', '/01-input/FAN_RET')
    assert contract['amps'] == 1.
    assert contract['geometry_margin'] == 1.25
    assert contract['margin_included'] is False
    assert contract['source'] == 'board_design_basis'


def test_fan_name_is_not_a_whole_shared_supply_current_override():
    rows = policy.params('12vhpwr-standard')['net_current_contracts']
    assert '/FAN_12V' not in rows
    assert 'GND' not in rows
    assert rows['/SENSEP'] == 9.2
    assert synth.spec_net_current_contract('12vhpwr-standard', '/FAN_12V') is None


def test_actual_source_sink_alias_retains_design_not_separate_thermal_current():
    # A complete native-domain binding is represented here as provider input;
    # the existing binder and native path tests separately own its derivation.
    domains = {'/FAN_12V': dict(complete=True, amps=8.33,
        configured_net='/SENSEP6_HI', binding=dict(actual_net='/FAN_12V',
            design_current_net='/SENSEP6_HI', resolution='unique_endpoint_net'))}
    contract = topology.current_contract_for_net('/FAN_12V', '12vhpwr-standard', domains)
    assert contract['amps'] == 9.2
    assert contract['geometry_margin'] == 1.25
    assert contract['margin_included'] is False
    assert contract['source'] == 'board_design_basis'
    assert contract['configured_net'] == '/SENSEP6_HI'
    assert contract['actual_net'] == '/FAN_12V'
