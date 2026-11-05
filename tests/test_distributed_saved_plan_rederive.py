"""Persisted JSON is not independent authority and cannot alter source loads."""
import json
from unittest import mock
import pytest
import cec_distributed_loop_retirement as op
import cec_force_current as force
import cec_field_coupling as field
import cec_additive_route_receiving as additive
from test_distributed_loop_retirement import fixture


def prepared(tmp_path):
    source,b,q,catalog,*rest=fixture(tmp_path)
    catalog['contracts'][q['net']]['routing_layers']=tuple(catalog['contracts'][q['net']]['routing_layers'])
    with mock.patch.object(op.topology,'distributed_supply_contracts',return_value=catalog):
        original=op.plan(b,source,**q)
    return source,b,q,catalog,original,json.loads(json.dumps(original))


def test_tuple_array_roundtrip_is_rederived_and_the_existing_strict_receiver_remains_unchanged(tmp_path):
    source,b,q,catalog,original,stored=prepared(tmp_path);before=field._field_snapshot_inventory(b)
    assert original!=stored
    with mock.patch.object(op.topology,'distributed_supply_contracts',return_value=catalog):
        with pytest.raises(ValueError):op.subtract(b,stored)
        fresh=op.rederive_saved_plan(b,stored)
        assert fresh==original and before==field._field_snapshot_inventory(b)
        op.subtract(b,fresh);child=force._copy_family(source,tmp_path/'candidate')
        additive._ground_refill(b);field._save_field_snapshot(b,child)
        received=op.receive(source,child,fresh,board_hint='synthetic')
    assert received['ok'] and received['complete'],received
    assert not received['current_qualified'] and not received['release_authority']


@pytest.mark.parametrize('fault',['amps','margin','role','layers','binding','coordinates','extra','nan'])
def test_source_or_electrical_value_changes_are_not_hidden_by_json_carrier_normalization(tmp_path,fault):
    source,b,q,catalog,original,stored=prepared(tmp_path)
    if fault=='amps':stored['contract']['current_authority']['amps']*=2
    elif fault=='margin':stored['contract']['current_authority']['geometry_margin']=1.
    elif fault=='role':stored['contract']['role']='guessed'
    elif fault=='layers':stored['contract']['routing_layers'].append('In1.Cu')
    elif fault=='binding':stored['source_binding']='forged'
    elif fault=='coordinates':stored['source_tracks'][0]['start_nm'][0]+=1
    elif fault=='extra':stored['ignored_untrusted_field']=True
    else:stored['contract']['current_authority']['amps']=float('nan')
    before=field._field_snapshot_inventory(b)
    with mock.patch.object(op.topology,'distributed_supply_contracts',return_value=catalog):
        with pytest.raises(ValueError):op.rederive_saved_plan(b,stored)
    assert before==field._field_snapshot_inventory(b)


def test_changed_actual_source_cannot_reuse_an_old_json_plan(tmp_path):
    source,b,q,catalog,original,stored=prepared(tmp_path)
    first=next(iter(b.GetTracks()));first.SetWidth(first.GetWidth()+1)
    with mock.patch.object(op.topology,'distributed_supply_contracts',return_value=catalog):
        with pytest.raises(ValueError):op.rederive_saved_plan(b,stored)
