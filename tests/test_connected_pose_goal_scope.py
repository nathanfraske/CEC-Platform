"""Reporting conditionals, not mock fabrication/routing qualification."""
import copy

import pytest

import root_received_goal_scope_20261024 as scope
from test_measurement_auxiliary_goal_scope import GATES, receipt as auxiliary_receipt


def receipt(reference=False):
    value=auxiliary_receipt()
    proof=dict(ok=True,complete=True,errors=[],
        scope='explicit_connected_pose_with_exact_additive_contact_restoration',
        moved=[dict(uuid='owner',before_nm=[0,0],after_nm=[0,600000],quarter_turns=0)],
        all_original_terminal_and_copper_partitions_preserved=True,
        source_candidate_and_code_unchanged=True,independently_rebuilt_source_pose=True,
        independent_native_current_field_pair_and_assembly_receiving_required=True,
        source_material_retired=False,current_qualified=False,placement_qualified=False,
        routing_admitted=False,release_authority=False,
        exact_source_plus_additions=dict(ok=True,complete=True,
            existing_ground_fill_matches_independent_native_replay=True),
        paired_native_partition_preservation=dict(available=True,preserved=True))
    kind='source_ordinary_resistor_reference_pose'if reference else'connected_footprint_pose'
    if reference:
        proof.update(source_ordinary_resistor_witness=dict(root='/actual-Source'),
            source_closed_reference_maps_translated_with_own_passives=True,
            all_source_reference_group_memberships_and_locks_preserved=True,
            source_reference_group_uuids=['actual-map'],
            all_source_tracks_arcs_and_barrels_retained_exactly=True,
            source_ordinary_resistor_translation_only=True,
            no_source_ground_or_signal_barrel_motion_authorized=True,
            source_ordinary_resistor_contact_restoration=[])
    value['phases'][0].update(kind=kind,receiving=proof)
    return value


@pytest.mark.parametrize('reference',[False,True])
def test_exact_pose_scope_never_claims_unchanged_placement_or_new_qualification(reference):
    result=scope.received_repair_scope(receipt(reference))
    assert result['selected_footprint_pose_and_exact_Source_contact_restoration_explicit']is True
    assert result['all_copper_parts_pinouts_stack_and_dimensions_unchanged']is False
    assert result['no_Source_Ground_barrel_motion_authorized']is True
    assert result['closed_ordinary_resistor_reference_map_explicit']is reference
    assert result['new_current_or_Kelvin_or_barrel_or_voltage_qualification']is False


@pytest.mark.parametrize('gate',GATES)
def test_each_whole_actual_parent_gate_is_still_mandatory(gate):
    value=receipt();value['gates'][gate]=False
    with pytest.raises(ValueError):scope.received_repair_scope(value)


@pytest.mark.parametrize('fault',['Source_cut','Ground_motion','lost_partition','no_additive',
    'no_refill','no_pose_rebuild','duplicate_owner','two_poses','untyped_supply',
    'map_on_plain','missing_canonical','missing_group_proof','multiple_groups'])
def test_no_mixed_group_ground_cut_or_ambiguous_pose_authority(fault):
    value=receipt(fault in('missing_canonical','missing_group_proof','multiple_groups'))
    phase=value['phases'][0];proof=phase['receiving']
    if fault=='Source_cut':proof['source_material_retired']=True
    elif fault=='Ground_motion':proof['source_ground_barrel_transport']={}
    elif fault=='lost_partition':proof['paired_native_partition_preservation']['preserved']=False
    elif fault=='no_additive':proof['exact_source_plus_additions']['complete']=False
    elif fault=='no_refill':proof['exact_source_plus_additions']['existing_ground_fill_matches_independent_native_replay']=False
    elif fault=='no_pose_rebuild':proof['independently_rebuilt_source_pose']=False
    elif fault=='duplicate_owner':proof['moved']*=2
    elif fault=='two_poses':value['phases'].insert(1,copy.deepcopy(phase))
    elif fault=='untyped_supply':
        value['phases'].insert(1,dict(kind='distributed_supply_join',candidate='/supply',
            candidate_sha256='d'*64,receiving=dict(ok=True,complete=True)))
    elif fault=='map_on_plain':proof['source_reference_group_uuids']=['unowned-map']
    elif fault=='missing_canonical':proof['source_ordinary_resistor_witness']={}
    elif fault=='missing_group_proof':proof['all_source_reference_group_memberships_and_locks_preserved']=False
    elif fault=='multiple_groups':proof['source_reference_group_uuids'].append('another')
    with pytest.raises(ValueError):scope.received_repair_scope(value)


def test_six_phase_ordinary_cohort_is_bounded_but_not_given_cut_authority_by_pose():
    value=receipt(True)
    for i in range(4):
        value['phases'].insert(-1,dict(kind='ordinary_source_reflow',candidate='/signal'+str(i),
            candidate_sha256=str(i)*64,receiving=dict(ok=True,complete=True,errors=[],
                scope='bounded_ordinary_source_delta_receiving',release_authority=False)))
    result=scope.received_repair_scope(value)
    assert len(result['typed_signal_companions'])==4
    assert result['no_Source_copper_retirement_authority_transferred_from_pose']is True
