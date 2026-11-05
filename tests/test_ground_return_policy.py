"""Do not accidentally replace the source owner policy by the cap rule."""
from types import SimpleNamespace
from unittest.mock import patch
import ast
from pathlib import Path
import math

import pytest
import cec_ground_return_policy as policy
import cec_force_current as force
from test_address_supply import Tests as AddressFixture


def fixture():
    source,_,_=AddressFixture().fixture()
    fp=source.FindFootprintByReference('ANY_OWNER');pad=fp.FindPadByNumber('1')
    pad.SetNet(source.FindNet('GND'))
    entry=dict(selected_owner=fp.GetReference(),owner_ground_pad_uuid=force._uid(pad),
        source_owner_return_policy=dict(max_mm=1.5))
    return pad,{force._uid(pad):entry}


@pytest.mark.parametrize('role',['ground','power_return'])
def test_actual_typed_owner_keeps_canonical_reach(role):
    pad,entries=fixture()
    with patch('cec_device_power_roles.footprint_contract',return_value={'pins':{'1':role}}):
        assert policy.reach(pad,entries)==1.5


@pytest.mark.parametrize('role',['reference','address','power_input','signal_input'])
def test_nonreturn_lands_never_inherit_owner_extension(role):
    pad,entries=fixture()
    with patch('cec_device_power_roles.footprint_contract',return_value={'pins':{'1':role}}):
        assert policy.reach(pad,entries)==.8


def test_capacitor_or_unassigned_owner_stays_at_point_eight():
    pad,_=fixture()
    assert policy.reach(pad,{})==.8
    with pytest.raises(ValueError):policy.reach(pad,{},portal_max_mm=1.5)


@pytest.mark.parametrize('role',['ground','reference','address','power_input'])
def test_retained_barrel_extension_requires_the_exact_typed_owner_entry(role):
    import time
    import cec_cell_escape_replan as escape
    pad,entries=fixture();entry=entries[force._uid(pad)]
    with patch('cec_device_power_roles.footprint_contract',return_value={'pins':{'1':role}}):
        if role=='ground':
            assert escape.retained_ground_barrel_ops(pad.GetBoard(),pad,
                deadline=time.monotonic()+1.,reach_mm=1.,owner_return_entry=entry)==[]
        else:
            with pytest.raises(ValueError,match='bounded_native_immediate_ground_barrel'):
                escape.retained_ground_barrel_ops(pad.GetBoard(),pad,
                    deadline=time.monotonic()+1.,reach_mm=1.,owner_return_entry=entry)


@pytest.mark.parametrize('fault',['wrong_owner','wrong_pad','switching','unknown','invalid_bound'])
def test_entry_cannot_retype_a_foreign_or_switching_ground(fault):
    pad,entries=fixture();entry=next(iter(entries.values()));model={'pins':{'1':'ground'}}
    if fault=='wrong_owner':entry['selected_owner']='unrelated'
    elif fault=='wrong_pad':entry['owner_ground_pad_uuid']='invented'
    elif fault=='switching':model['pins']['2']='switch'
    elif fault=='unknown':model=None
    else:entry['source_owner_return_policy']['max_mm']=2.
    with patch('cec_device_power_roles.footprint_contract',return_value=model):
        if fault=='invalid_bound':
            with pytest.raises(ValueError):policy.reach(pad,entries)
        else:assert policy.reach(pad,entries)==.8


@pytest.mark.parametrize('value',[True,0,-1,1.50001,float('nan'),float('inf')])
def test_canonical_policy_cannot_enlarge_source_ceiling_or_use_unknown(value):
    cfg=SimpleNamespace(params={'decoupler_ground_reach_mm':value},board_key='generic',dir='source')
    with patch('cec_synth_pipeline.Config.load',return_value=cfg):
        with pytest.raises(ValueError):policy.owner_policy('source')


def test_resolved_default_is_the_actual_synthesis_default_not_a_guessed_device_rating():
    cfg=SimpleNamespace(params={},board_key='generic',dir='source')
    with patch('cec_synth_pipeline.Config.load',return_value=cfg):
        result=policy.owner_policy('source')
    assert result['max_mm']==1.5 and not result['explicit_parameter']
    assert result['capacitor_portal_max_mm']==.8 and not result['current_authority']
    with patch('cec_synth_pipeline.Config.load',side_effect=FileNotFoundError):
        assert policy.owner_policy('unresolved')['max_mm']==.8


def test_precheck_construction_and_saved_replay_share_source_request_authority():
    root=Path(policy.__file__).parent
    construction=(root/'cec_cell_escape_replan.py').read_text()
    precheck=(root/'cec_escape_pose_frontier.py').read_text()
    receiving=(root/'cec_complete_cell_receiving.py').read_text()
    assert 'source_return_policy=return_policy.owner_policy(board_hint)' in construction
    assert 'reach_mm=return_policy.reach(p,entries)' in construction
    assert 'actual_reach=return_policy.reach(pad,entries,portal_max_mm=reach_mm)' in precheck
    assert 'requests=escape.obligations(parent,projected,plan)' in receiving
    assert "_existing_return(child,a,request['reach_mm']" in receiving
