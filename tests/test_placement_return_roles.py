"""Placement feedback and the native local-cell builder share return roles."""
from types import SimpleNamespace
from unittest import mock

import pcbnew
import pytest

import cec_decoupler_cell as cells
import cec_device_power_roles as roles
import cec_synth_pipeline as synth
from test_decoupler_ground_roles import fixture


@pytest.mark.parametrize('value,mpn,footprint,ground,other', [
    ('INA240A3', 'INA240A3DR', 'cec-Package_SO:SOIC-8_3.9x4.9mm_P1.27mm', '2', ['3','4','7']),
    ('TPS2121RUXR', 'TPS2121RUXR', 'cec-Package_DFN_QFN:RUX0012A', '12', ['3','4']),
    ('TJA1051T/3', 'TJA1051T/3/1J', 'cec-Package_SO:SOIC-8_3.9x4.9mm_P1.27mm', '2', ['8']),
])
def test_source_geometry_rejects_ground_tied_nonreturns(value, mpn, footprint, ground, other):
    nets = dict.fromkeys([ground,*other], 'GND')
    result = roles.source_return_pins(value,nets,mpn=mpn,footprint=footprint)
    assert result['pins'] == [ground]
    assert result['manufacturer_ground_role_qualified']
    assert not result['current_or_fabrication_qualification']
    for pin in other:
        assert roles.source_return_pins(value,nets,mpn=mpn,footprint=footprint,
                                       explicit_pin=pin)['pins'] == []


def test_unknown_and_explicit_nonground_returns_remain_distinct():
    row = roles.source_return_pins('uncovered',{'A':'GND','B':'GND'})
    assert row['pins'] == ['A','B'] and not row['manufacturer_ground_role_qualified']
    row = roles.source_return_pins('TJA1051T/3', {'2':'GND','3':'RAIL','5':'OTHER'},
                                  return_rail='RAIL', explicit_pin='3')
    assert row['pins'] == ['3'] and row['scope'] == 'explicit-rail-to-rail-contract'
    assert row['manufacturer_ground_role_qualified'] is None


def test_contradictory_package_is_not_net_only_fallback():
    with pytest.raises(ValueError,match='manufacturer_selected_package_footprint_mismatch'):
        roles.source_return_pins('INA240A1DR',{'2':'GND','7':'GND'},
                                 footprint='Package_SO:TSSOP-8_3x3mm_P0.65mm')


@pytest.mark.parametrize('owner', ['U71', 'RENAMED_DEVICE'])
def test_production_source_adapter_uses_selected_part_not_reference(owner):
    comp=SimpleNamespace(value='TPS2121RUXR',props={'MPN':'TPS2121RUXR'})
    nl=synth.Netlist(comps={owner:comp},nets={'GND':[(owner,'12'),(owner,'3')]})
    comps={owner:'cec-Package_DFN_QFN:RUX0012A'}
    assert synth._source_owner_return_pins(nl,comps,owner,'GND') == ['12']
    assert synth._source_owner_return_pins(nl,comps,owner,'GND',explicit_pin='3') == []


@pytest.mark.parametrize('missing', [False,True])
@pytest.mark.parametrize('turn', [0,1,2,3])
def test_actual_oracle_feedback_never_offers_control_return_pin(turn, missing):
    board,owner,cap,req=fixture(turn=turn)
    req.update(nearest_ref=cap.GetReference(),nearest_mm=5.)
    cell_id='local'
    measured=dict(requirements=[req],missing=[req] if missing else [],
        assigned={} if missing else {cell_id:dict(requirement=req,
            cap_ref=cap.GetReference(),distance_mm=1.)})
    access=dict(ok=False,cells=[],refused=[])
    import cec_constraints,cec_shared_pin_reference,cec_prefreeze_local_pi
    with mock.patch.object(pcbnew,'LoadBoard',return_value=board), \
         mock.patch.object(cec_constraints,'_device_bypass_assignment',return_value=measured), \
         mock.patch.object(cec_prefreeze_local_pi,'replay_for_measurement',return_value={}), \
         mock.patch.object(cells,'audit_pre_route_cells_board',return_value=access), \
         mock.patch.object(cec_shared_pin_reference,'references_from_board',return_value={}):
        report=synth._oracle_decoupler_adjacency('read-only-fixture')
    assert len(report['details']) == 1
    row=report['details'][0]
    assert row['ground_pin'] == '12'
    assert [p['pin'] for p in row['owner_ground_positions_mm']] == ['12']
    assert row['owner_return_role_evidence']['manufacturer_ground_role_qualified']
