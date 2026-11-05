"""Witness refresh is not a cut, departure, dimension, or release waiver."""
import copy
from unittest.mock import patch
import pcbnew
import pytest
import cec_force_current as force
import cec_measurement_leaf as leaf
import cec_received_route_evidence as receiving
from test_measurement_leaf_reflow import reflow_fixture


def reports(tmp_path,quarter=0):
    source,child,pad=reflow_fixture(tmp_path,quarter,'RENAMED_INPUT_73')
    old=pcbnew.LoadBoard(str(source));new=pcbnew.LoadBoard(str(child))
    first,last=leaf.plan(old,pad),leaf.plan(new,pad)
    # Unit-scope phase record. Independent native phase admission is exercised
    # separately in test_measurement_leaf_reflow; this test grants no admission.
    proof=dict(ok=True,complete=True,only_exact_typed_measurement_leaf_changed=True,
        source_candidate_and_code_unchanged=True,
        source_leaf=first,new_leaf=last)
    prefix=[first['boundary_uuids'][0]]
    def report(proposal):
        return dict(inner_departure=dict(details=[dict(net=proposal['net'],ok=True,
            sense_terminal=dict(uuid=pad),native=dict(contact_count=1,departures=[
                dict(uuid=prefix[0],contact_exit_mm=[1,2],input_contact_paths={
                    pad:prefix+list(reversed(proposal['track_uuids']))+[pad]})]))]))
    return old,new,report(first),report(last),[dict(kind='measurement_leaf_reflow',proof=proof)]


def absolute(ok=True):
    return dict(ok=ok,expected_legs=[['PHYSICAL_INPUT','n']],checked=1)


@pytest.mark.parametrize('quarter',range(4))
def test_exact_rotated_renamed_native_leaf_refreshes_only_its_witness(tmp_path,quarter):
    old,new,before,after,phases=reports(tmp_path,quarter)
    initial=copy.deepcopy((before,after,phases))
    with patch.object(receiving.sense,'admit_changed_net',return_value=absolute()) as cuts:
        adjusted,observations=receiving._rebind_received_measurement_paths(old,new,before,after,phases)
    assert len(observations)==1 and cuts.call_count==2
    assert adjusted==before
    assert (before,after,phases)==initial
    assert not observations[0]['release_authority']
    assert observations[0]['retained_witness_prefix']==[phases[0]['proof']['source_leaf']['boundary_uuids'][0]]


@pytest.mark.parametrize('fault',['unknown_cut','failed_cut','changed_cut_inventory','changed_cut_count',
    'wrong_prefix','wrong_leaf_order','missing_leaf','extra_contact','missing_terminal',
    'unknown_departure','duplicate_terminal','stale_dimensions','stale_owner','incomplete_phase',
    'wrong_role','repeated_phase','native_owner_motion'])
def test_refresh_refuses_changed_authority_or_any_unproved_leaf(tmp_path,fault):
    old,new,before,after,phases=reports(tmp_path)
    row=after['inner_departure']['details'][0];pad=row['sense_terminal']['uuid']
    path=row['native']['departures'][0]['input_contact_paths'][pad]
    answers=[absolute(),absolute()]
    if fault in ('unknown_cut','failed_cut'):answers[1]['ok']=None if fault=='unknown_cut' else False
    elif fault=='changed_cut_inventory':answers[1]['expected_legs']=[['FOREIGN','n']]
    elif fault=='changed_cut_count':answers[1]['checked']=0
    elif fault=='wrong_prefix':path[0]='another-native-junction'
    elif fault=='wrong_leaf_order':path[1:3]=reversed(path[1:3])
    elif fault=='missing_leaf':path.pop(1)
    elif fault=='extra_contact':path.insert(1,'acquired-contact')
    elif fault=='missing_terminal':row['sense_terminal']['uuid']='another-native-land'
    elif fault=='unknown_departure':row['ok']=None
    elif fault=='duplicate_terminal':after['inner_departure']['details'].append(copy.deepcopy(row))
    elif fault=='stale_dimensions':phases[0]['proof']['new_leaf']['width_nm']+=1
    elif fault=='stale_owner':phases[0]['proof']['source_leaf']['owner']='ANOTHER_INPUT'
    elif fault=='incomplete_phase':phases[0]['proof']['complete']=False
    elif fault=='wrong_role':phases[0]['proof']['only_exact_typed_measurement_leaf_changed']=False
    elif fault=='repeated_phase':phases.append(copy.deepcopy(phases[0]))
    elif fault=='native_owner_motion':new.FindFootprintByReference('RENAMED_INPUT_73').Move(pcbnew.VECTOR2I_MM(.002,0))
    with patch.object(receiving.sense,'admit_changed_net',side_effect=answers):
        with pytest.raises((ValueError,KeyError)):
            receiving._rebind_received_measurement_paths(old,new,before,after,phases)


def test_no_received_measurement_phase_has_no_witness_rebinding_authority(tmp_path):
    old,new,before,after,phases=reports(tmp_path)
    phases[0]['kind']='additive'
    adjusted,observations=receiving._rebind_received_measurement_paths(old,new,before,after,phases)
    assert adjusted==after and not observations
    assert adjusted!=before


def test_unknown_or_changed_nonwitness_fields_are_not_normalized(tmp_path):
    old,new,before,after,phases=reports(tmp_path)
    after['inner_departure']['details'][0]['native']['unrecorded_permission']=True
    after['inner_departure']['details'][0]['native']['departures'][0]['contact_exit_mm'][0]+=1
    with patch.object(receiving.sense,'admit_changed_net',return_value=absolute()):
        adjusted,_=receiving._rebind_received_measurement_paths(old,new,before,after,phases)
    assert adjusted!=before
    assert adjusted['inner_departure']['details'][0]['native']['unrecorded_permission']
    assert adjusted['inner_departure']['details'][0]['native']['departures'][0]['contact_exit_mm']==[2,2]


@pytest.mark.parametrize('reason',['baseline_native_terminal_connectivity_incomplete',
    'numeric_exhaustion','cut_geometry_unavailable'])
def test_exact_suffix_may_preserve_but_never_qualify_inherited_unconnected_authority(tmp_path,reason):
    old,new,before,after,phases=reports(tmp_path)
    pad=phases[0]['proof']['source_leaf']['pad_uuid'];net=phases[0]['proof']['source_leaf']['net']
    for report in (before,after):
        report['clipped_isolation']=dict(details=[dict(net=net,ok=None,status='unknown',
            sense_terminal=dict(uuid=pad),native=dict(complete=False,reason=reason))])
    with patch.object(receiving.sense,'admit_changed_net',return_value=absolute(None)):
        if reason!='baseline_native_terminal_connectivity_incomplete':
            with pytest.raises(ValueError):receiving._rebind_received_measurement_paths(old,new,before,after,phases)
        else:
            adjusted,observations=receiving._rebind_received_measurement_paths(old,new,before,after,phases)
            assert adjusted==before
            assert observations[0]['inherited_unknown_not_qualified']
            assert adjusted['clipped_isolation']['details'][0]['ok'] is None
