"""Owner-authorized negative-rail interface data, not a routing special case."""
from copy import deepcopy
import cec_board_policy as policy
import cec_synth_pipeline as synth


def test_negative_rail_is_one_amp_with_once_applied_conductor_margin():
    for net in ('/ATX_NEG12V','/a/renamed/sheet/ATX_NEG12V'):
        contract=synth.spec_net_current_contract('atx-24pin-rev3',net)
        assert contract['amps']==1. and contract['geometry_margin']==1.25
        assert contract['margin_included'] is False and contract['source']=='board_design_basis'
        assert contract['amps']*contract['geometry_margin']==1.25


def test_negative_rail_endpoint_map_owns_the_pass_through_not_its_divider():
    params=policy.params('atx-24pin-rev3')
    rows=[r for r in params['current_endpoint_contracts'] if r['net']=='/ATX_NEG12V']
    assert len(rows)==1
    row=rows[0]
    assert [(r['ref'],r['pins']) for r in row['sources']]==[('J3',['14'])]
    assert [(r['ref'],r['pins']) for r in row['sinks']]==[('J_SIG1',['1'])]
    assert set(row)=={'net','sources','sinks','basis'}
    assert 'Owner-authorized 1 A sustained' in row['basis']


def test_conservative_return_basis_gets_one_new_amp_without_cancellation(monkeypatch):
    hint='atx-24pin-rev3';table=synth._spec_current_table(hint)
    names=['/SENSE3V3_HI','/SENSE3V3_LO','/SENSE5V_HI','/SENSE5V_LO',
        '/SENSE12V_HI','/SENSE12V_LO','/SENSE5VSB_HI','/SENSE5VSB_LO','/a/ATX_NEG12V']
    current=synth.spec_gnd_current(hint,names)
    old=deepcopy(table);old.pop('/ATX_NEG12V')
    monkeypatch.setattr(synth,'_spec_current_table',lambda _board:old)
    assert current-synth.spec_gnd_current(hint,names)==1.
