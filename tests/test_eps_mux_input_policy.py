"""Owner-authorized mux conductor headroom, not invented component loading."""
import cec_board_policy as policy
import cec_synth_pipeline as synth
import cec_power_budget as power


def test_each_mux_input_is_one_amp_with_existing_independent_margin():
    for board in ('eps-8pin-rev3','eps-8pin'):
        for net in ('VCC_RJ45','/USB-C SERVICE INGRESS/VBUS_FUSED','/renamed/sheet/VBUS_FUSED'):
            c=synth.spec_net_current_contract(board,net)
            assert c['amps']==1. and c['geometry_margin']==1.25
            assert c['margin_included']is False and c['source']=='board_design_basis'
            assert c['amps']*c['geometry_margin']==1.25


def test_output_and_component_load_budget_are_not_replaced_by_input_headroom():
    output=synth.spec_net_current_contract('eps-8pin-rev3','+5VSB')
    assert output['amps']==.5 and output['geometry_margin']==1.25
    logic=synth.spec_net_current_contract('eps-8pin-rev3','+3V3')
    actual=power.budget('eps-8pin-rev3')
    assert logic['source']=='component_power_budget'and logic['amps']==actual['required_mA']/1000.
    assert logic['geometry_margin']==1. and logic['margin_included']is True


def test_source_policy_is_explicit_and_control_or_unknown_nets_gain_no_rating():
    p=policy.params('eps-8pin-rev3')
    assert p['net_current_contracts']['/SENSEC']==52.
    notes=' '.join(p['net_current_contract_notes'])
    assert 'no sharing is assumed'in notes and 'not a changed load'in notes
    for net in ('/USB-C SERVICE INGRESS/U4_ILIM','/USB-C SERVICE INGRESS/U4_PR1',
                '/USB-C SERVICE INGRESS/U4_SS','/unrated_supply'):
        assert synth.spec_net_current_contract('eps-8pin-rev3',net)is None
