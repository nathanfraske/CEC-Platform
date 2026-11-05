"""Explicit Source-owned locked contact repairs retain the original locks."""
from unittest.mock import patch
import pcbnew,pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_rated_barrel_reseat as reseat
import cec_source_cut_chain as chain
from test_rated_barrel_contact_fault_repair import case,receive,OPTIONS


def lock(data,source=True,child=True):
    for path,uid,value in ((data[0],data[3],source),(data[1],data[4],child)):
        board=pcbnew.LoadBoard(str(path))
        for t in board.GetTracks():
            if force._uid(t)==uid or t.GetClass()=='PCB_TRACK':t.SetLocked(value)
        field._save_field_snapshot(board,path)


@pytest.mark.parametrize('quarter,prefix',[(0,'/locked-a/'),(1,'/renamed/'),(2,'/other/'),(3,'/nested/')])
def test_explicit_owned_locked_repair_keeps_every_current_and_lock_obligation(tmp_path,quarter,prefix):
    data=case(tmp_path,quarter,prefix);lock(data)
    before=[p.read_bytes() for p in data[:2]]
    assert not receive(data)['ok']
    proof=receive(data,allow_owned_locked=True)
    assert proof['ok'] and proof['complete'],proof
    assert proof['source_proposal']['source_barrels'][0]['locked'] is True
    assert proof['allow_owned_locked'] and proof['repair_source_contact_web']
    assert proof['all_surviving_source_native_partitions_preserved']
    assert not proof['barrel_ampacity_qualified'] and not proof['release_authority']
    assert [p.read_bytes() for p in data[:2]]==before


@pytest.mark.parametrize('old_lock,new_lock',[(True,False),(False,True)])
def test_explicit_repair_cannot_change_source_barrel_lock_state(tmp_path,old_lock,new_lock):
    data=case(tmp_path);lock(data,old_lock,new_lock)
    proof=receive(data,allow_owned_locked=True)
    assert not proof['ok'] and 'exact_local_barrel_identity_or_geometry_ambiguous' in proof['errors'][0]


@pytest.mark.parametrize('value',[1,0,None,'yes',[],{}])
def test_owned_lock_policy_must_be_positive_explicit_boolean(tmp_path,value):
    proof=receive(case(tmp_path),allow_owned_locked=value)
    assert not proof['ok'] and 'explicit_boolean_rated_barrel_repair_mode_required' in proof['errors'][0]


def test_owned_lock_flag_does_not_change_legacy_reseat_or_enable_unobserved_fault(tmp_path):
    data=case(tmp_path);lock(data)
    proof=receive(data,allow_owned_locked=True,repair_source_contact_web=False)
    assert not proof['ok'] and 'locked_contact_repair_requires_explicit_fault_mode' in proof['errors'][0]


def test_chain_schema_and_saved_receiving_independently_retype_locked_contact_owner(tmp_path):
    data=case(tmp_path);lock(data)
    source,child,cuts,old,new,net,contract=data
    phase=dict(kind='rated_barrel_reseat',candidate=str(child),retired_track_uuids=cuts,
        retired_via_uuids=[old],allow_owned_locked=True,**OPTIONS)
    with patch.object(reseat.rated.topology,'distributed_supply_contracts',
            return_value=dict(contracts={net:contract},refusals={})):
        proof=chain.receive(source,child,board_hint='synthetic',phases=[phase],per_phase_leases=True)
    assert proof['ok'] and proof['complete'],proof
    assert proof['phase_receiving'][0]['proof']['allow_owned_locked']
