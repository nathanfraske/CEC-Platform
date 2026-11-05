"""Native leaf identity refresh is narrower than physical cut admission.

Absolute admissions and the enclosing macro grade are explicit unit seams;
these tests do not manufacture board, current, Kelvin or release authority.
Actual leaf geometry/ports/IDs are rederived from native boards in every case.
"""
import copy
from unittest.mock import patch

import pcbnew
import pytest

import cec_force_current as force
import cec_macro_measurement_evidence as receiver
import cec_measurement_leaf as leaf
from test_received_measurement_witness_rebind import reports


def fixture(tmp_path,quarter=0):
    old,new,before,after,phases=reports(tmp_path,quarter)
    initial=phases[0]['proof']['source_leaf'];pad=initial['pad_uuid']
    last=leaf.plan(new,pad)
    owner=new.FindFootprintByReference(initial['owner'])
    point=pcbnew.VECTOR2I(*last['points_nm'][0]);peer=last['points_nm'][1]
    delta=pcbnew.VECTOR2I(*(250000*((b>a)-(b<a))for a,b in zip(last['points_nm'][0],peer)))
    owner.Move(delta)
    for item in new.GetTracks():
        if force._uid(item)not in last['track_uuids']:continue
        if item.GetStart()==point:item.SetStart(point+delta)
        if item.GetEnd()==point:item.SetEnd(point+delta)
    final=leaf.plan(new,pad)
    for report in(before,after):
        report['inner_departure']['details'][0].update(input_ref=initial['owner'],leg='n')
    proof=dict(scope='independent_saved_source_owned_macro_cell',ok=True,complete=True,
        source_candidate_families_and_code_unchanged=True,
        all_original_surviving_native_partitions_preserved=True,
        all_original_physical_ground_returns=dict(ok=True),
        independent_exact_source_cut_transform_and_additions=dict(ok=True,complete=True),
        source_macro_packet=dict(source_plan=dict(measurement_leaves=[initial])),
        retired_track_uuids=list(initial['track_uuids']),added_native_uuids=list(final['track_uuids']))
    bindings={pad:dict(ref=initial['owner'],net=initial['net'],before=initial['points_nm'][0],
        after=final['points_nm'][0])}
    return old,new,before,after,proof,bindings


def absolute(ok=True):
    return dict(ok=ok,applicable=True,expected_legs=[['RENAMED_INPUT_73','n']],checked=1)


@pytest.mark.parametrize('quarter',range(4))
def test_native_moved_leaf_keeps_identical_retained_prefix_and_raw_reports(tmp_path,quarter):
    old,new,before,after,proof,bindings=fixture(tmp_path,quarter)
    original=copy.deepcopy((before,after,proof,bindings))
    with patch.object(receiver.sense,'admit_changed_net',return_value=absolute())as cuts:
        adjusted,observations=receiver._rebind_owned_moved_leaf_witnesses(old,new,before,after,proof,bindings)
    assert cuts.call_count==2 and adjusted==before
    assert len(observations)==1
    assert observations[0]['retained_witness_prefix']==[proof['source_macro_packet']['source_plan']['measurement_leaves'][0]['boundary_uuids'][0]]
    assert observations[0]['raw_native_reports_unchanged']
    assert not observations[0]['full_kelvin_qualification']and not observations[0]['release_authority']
    assert original==(before,after,proof,bindings)


@pytest.mark.parametrize('fault',['unknown_before','unknown_after','failed_after','changed_cohort','changed_count',
    'open_before','bad_after'])
def test_inherited_bad_or_unknown_evidence_gets_no_witness_refresh(tmp_path,fault):
    old,new,before,after,proof,bindings=fixture(tmp_path)
    answers=[absolute(),absolute()]
    if fault=='unknown_before':answers[0]['ok']=None
    elif fault=='unknown_after':answers[1]['ok']=None
    elif fault=='failed_after':answers[1]['ok']=False
    elif fault=='changed_cohort':answers[1]['expected_legs']=[['ANOTHER_INPUT','n']]
    elif fault=='changed_count':answers[1]['checked']=0
    elif fault=='open_before':before['inner_departure']['details'][0]['ok']=None
    else:after['inner_departure']['details'][0]['ok']=False
    with patch.object(receiver.sense,'admit_changed_net',side_effect=answers):
        adjusted,observations=receiver._rebind_owned_moved_leaf_witnesses(old,new,before,after,proof,bindings)
    assert adjusted==after and not observations


@pytest.mark.parametrize('fault',['wrong_prefix','wrong_suffix','extra_contact','wrong_source_leaf','missing_cut',
    'unreceived_new_leaf','moved_boundary','changed_width','missing_return','incomplete_exact',
    'lost_partition','untyped_scope','wrong_input_before','wrong_input_after','repeated_leaf'])
def test_new_pose_cannot_mask_ownership_boundary_current_or_contact_changes(tmp_path,fault):
    old,new,before,after,proof,bindings=fixture(tmp_path)
    pad=next(iter(bindings));path=after['inner_departure']['details'][0]['native']['departures'][0]['input_contact_paths'][pad]
    claimed=proof['source_macro_packet']['source_plan']['measurement_leaves'][0]
    if fault=='wrong_prefix':path[0]='unowned-port'
    elif fault=='wrong_suffix':path[-2]='unreceived-track'
    elif fault=='extra_contact':path.insert(1,'new-tap')
    elif fault=='wrong_source_leaf':claimed['source_length_mm']+=.001
    elif fault=='missing_cut':proof['retired_track_uuids'].pop()
    elif fault=='unreceived_new_leaf':proof['added_native_uuids'].pop()
    elif fault=='moved_boundary':
        edge=next(t for t in [*new.GetTracks(),*[p for f in new.GetFootprints()for p in f.Pads()]]
            if force._uid(t)==claimed['boundary_uuids'][0])
        edge.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='changed_width':
        edge=next(t for t in new.GetTracks()if force._uid(t)in proof['added_native_uuids'])
        edge.SetWidth(edge.GetWidth()+1)
    elif fault=='missing_return':proof['all_original_physical_ground_returns']['ok']=False
    elif fault=='incomplete_exact':proof['independent_exact_source_cut_transform_and_additions']['complete']=False
    elif fault=='lost_partition':proof['all_original_surviving_native_partitions_preserved']=False
    elif fault=='untyped_scope':proof['scope']='worker'
    elif fault=='wrong_input_before':bindings[pad]['before'][0]+=1
    elif fault=='wrong_input_after':bindings[pad]['after'][0]+=1
    else:proof['source_macro_packet']['source_plan']['measurement_leaves'].append(copy.deepcopy(claimed))
    with patch.object(receiver.sense,'admit_changed_net',return_value=absolute()):
        with pytest.raises((ValueError,KeyError)):
            receiver._rebind_owned_moved_leaf_witnesses(old,new,before,after,proof,bindings)


def test_every_nonwitness_field_remains_for_final_strict_comparison(tmp_path):
    old,new,before,after,proof,bindings=fixture(tmp_path)
    after['inner_departure']['details'][0]['native']['departures'][0]['contact_exit_mm'][0]+=1
    after['inner_departure']['details'][0]['native']['unproved_permission']=True
    with patch.object(receiver.sense,'admit_changed_net',return_value=absolute()):
        adjusted,observations=receiver._rebind_owned_moved_leaf_witnesses(old,new,before,after,proof,bindings)
    assert observations and adjusted!=before
    assert adjusted['inner_departure']['details'][0]['native']['unproved_permission']


def test_no_Source_leaf_packet_has_no_rebinding_authority(tmp_path):
    old,new,before,after,proof,bindings=fixture(tmp_path)
    proof.pop('source_macro_packet')
    adjusted,observations=receiver._rebind_owned_moved_leaf_witnesses(old,new,before,after,proof,bindings)
    assert adjusted==after and not observations
