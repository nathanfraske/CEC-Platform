"""Placement and cheap search must use sense inputs, not a nearer Vbus pad."""
import copy
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import cec_pcb
import cec_pair_semantics as semantics
import cec_synth_pipeline as synth


def fixture(value='INA238AIDGSR', *, offset=(0, 0), angle=0, reflected=False):
    anchor, follower = 'RENAMED_ANCHOR', 'RENAMED_MONITOR'
    hi, lo = '/arbitrary/rail_HI', '/arbitrary/rail_LO'
    pins = {anchor: {'a': hi, 'b': lo}, follower: {'10': hi, '9': lo, '8': lo, '6': 'SUPPLY'}}
    local = {anchor: {'a': (0, -2), 'b': (0, 2)},
             follower: {'10': (1, -1), '9': (1, 1), '8': (3, 2), '6': (-1, 0)}}
    if reflected:
        local = {ref: {pin: (-x, y) for pin, (x, y) in pads.items()} for ref, pads in local.items()}
    origin = {anchor: (10, 10), follower: (5, 10)}
    poses = {ref: (*[v+d for v,d in zip(cec_pcb._rot(*xy, angle), offset)], angle)
             for ref, xy in origin.items()}
    nets = {}
    for ref, pads in pins.items():
        for pin, net in pads.items():nets.setdefault(net, []).append((ref, pin))
    nl = SimpleNamespace(nets=nets, comps={follower:SimpleNamespace(value=value)})
    templates = {ref: tuple(dict(pad=pin, net=pins[ref][pin], local=xy) for pin,xy in pads.items())
                 for ref,pads in local.items()}
    return nl, local, poses, templates, follower, lo


def evidence(data):
    nl, local, poses, *_ = data
    with patch.object(cec_pcb,'local_pads',side_effect=lambda ref:local[ref]), \
         patch.object(cec_pcb,'local_pad_sizes',side_effect=lambda ref:{p:(.2,.2) for p in local[ref]}):
        return synth._critical_terminal_order_evidence(nl,{ref:ref for ref in poses},poses)


@pytest.mark.parametrize('angle', [0,90,180,270,37])
@pytest.mark.parametrize('reflected', [False,True])
def test_exact_input_identity_survives_pose_and_reference_changes(angle,reflected):
    data=fixture(offset=(127.25,-34.125),angle=angle,reflected=reflected)
    full=evidence(data)
    row=full['details'][0]
    assert row['selected_pads'][data[-1]]=='9'
    assert set(row['follower_pad_contract'].values())=={'10','9'}
    specs=synth._parallel_pour_critical_terminal_specs({'critical_terminal_order':full})
    cheap=synth._parallel_pour_critical_terminal_geometry(data[2],data[3],specs)
    assert cheap['details'][0]['selected_pads'][data[-1]]['follower_pad']=='9'
    assert cheap['key'][0]==full['crossing_count']
    assert abs(cheap['key'][1]-full['direct_length_mm'])<1e-5


def test_old_nearest_pad_is_reproduced_but_does_not_override_input_contract():
    data=fixture()
    with patch.object(semantics,'current_input_contract',return_value=None):old=evidence(data)
    new=evidence(data)
    assert old['details'][0]['selected_pads'][data[-1]]=='8'
    assert new['details'][0]['selected_pads'][data[-1]]=='9'
    assert old['direct_length_mm'] != new['direct_length_mm']


def test_unknown_device_retains_connectivity_fallback():
    row=evidence(fixture(value='UNKNOWN_MONITOR'))['details'][0]
    assert not row['follower_pad_contract']
    assert '8' in row['selected_pads'].values()


def test_nearby_vbus_cannot_hide_crossed_actual_input_rays():
    data=fixture()
    data[1][data[-2]]['9']=(1,-3)
    with patch.object(semantics,'current_input_contract',return_value=None):old=evidence(data)
    new=evidence(data)
    assert old['ok'] and old['crossing_count']==0
    assert not new['ok'] and new['crossing_count']==1
    specs=synth._parallel_pour_critical_terminal_specs({'critical_terminal_order':new})
    templates=copy.deepcopy(data[3])
    for row in templates[data[-2]]:
        if row['pad']=='9':row['local']=(1,-3)
    cheap=synth._parallel_pour_critical_terminal_geometry(data[2],templates,specs)
    assert cheap['key'][0]==1


@pytest.mark.parametrize('fault', ['missing_geometry','wrong_net','shorted_inputs'])
def test_known_input_contract_cannot_fall_back_when_invalid(fault):
    data=fixture()
    nl,local,_,_,follower,lo=data
    if fault=='missing_geometry':del local[follower]['9']
    else:
        nl.nets[lo].remove((follower,'9'))
        net='/arbitrary/rail_HI' if fault=='shorted_inputs' else 'UNRELATED'
        nl.nets.setdefault(net,[]).append((follower,'9'))
    with pytest.raises(ValueError,match='current-input terminal contract'):evidence(data)


@pytest.mark.parametrize('fault',['missing_input','incomplete_contract'])
def test_cheap_geometry_cannot_drop_a_declared_input(fault):
    data=fixture()
    full=evidence(data)
    specs=synth._parallel_pour_critical_terminal_specs({'critical_terminal_order':full})
    templates=copy.deepcopy(data[3])
    if fault=='missing_input':
        templates[data[-2]]=tuple(p for p in templates[data[-2]] if p['pad']!='9')
    else:del specs[0]['follower_pad_contract'][data[-1]]
    with pytest.raises(ValueError,match='current-input terminal'):
        synth._parallel_pour_critical_terminal_geometry(data[2],templates,specs)


def test_current_input_contract_retains_existing_device_mapping():
    for device,pins in semantics.CURRENT_INPUT_PINS.items():
        value = {'INA181': 'INA181A2IDBVR', 'INA240': 'INA240A2DR'}.get(device, device+'AIDGSR')
        assert semantics.current_input_contract(value)==(device,pins)
    assert semantics.current_input_contract('NOT_INA238') is None
