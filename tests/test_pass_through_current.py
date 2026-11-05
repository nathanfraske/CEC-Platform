from copy import deepcopy
import pytest
import cec_device_power_roles as roles
from cec_pass_through_current import input_bound


def data():
    return roles.contract('TPS2121', mpn='TPS2121RUXR'), dict(
        amps=3., geometry_margin=1.25, margin_included=False, source='board_design_basis')


@pytest.mark.parametrize('pin', ['2', '7'])
@pytest.mark.parametrize('amps', [.01, .75, 1.1, 3.])
def test_full_declared_output_each_input_plus_manufacturer_max_not_equal_sharing(pin, amps):
    model, output = data(); output['amps'] = amps
    source = deepcopy(output)
    q = input_bound(model, pin, output)
    assert q['minimum_declared_input_a'] == pytest.approx(amps+.0004)
    assert q['disabled_input_absolute_bound_a'] == pytest.approx(.000525)
    assert q['output_current_authority'] == source == output
    assert not q['branch_sharing_assumed'] and not q['release_authority']
    assert not q['inrush_fault_barrel_and_release_qualified']


@pytest.mark.parametrize('bad', [0, -1, True, None, float('nan'), float('inf'), '3'])
def test_unknown_or_invalid_output_load_does_not_create_an_input_budget(bad):
    model, output = data(); output['amps'] = bad
    with pytest.raises(ValueError): input_bound(model, '7', output)


@pytest.mark.parametrize('pin', ['1', '8', '10', '', None])
def test_control_output_or_unknown_pin_never_an_input_allocation(pin):
    model, output = data()
    with pytest.raises(ValueError): input_bound(model, pin, output)


@pytest.mark.parametrize('fault', ['package', 'role', 'source', 'domain', 'margin_twice', 'margin_unknown', 'authority'])
def test_incomplete_manufacturer_or_once_only_source_authority_refuses(fault):
    model, output = data()
    if fault == 'package': model['device_package'] = 'Unknown converter'
    elif fault == 'role': model['pins']['7'] = 'control'
    elif fault == 'source': model['source'] = 'unverified'
    elif fault == 'domain': model['common_domains'] = []
    elif fault == 'margin_twice': output['margin_included'] = True
    elif fault == 'margin_unknown': output['geometry_margin'] = None
    elif fault == 'authority': output['source'] = 'guessed_rating'
    with pytest.raises(ValueError): input_bound(model, '7', output)
