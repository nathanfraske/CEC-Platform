"""Descriptor conditionals only; public physical receiving is not mocked into authority."""
import copy

import pytest

import root_received_goal_scope_20261024 as scopes


FLAGS=('current_authority','numeric_load_assumed','trunk_capacity_credited',
    'barrel_qualified','kelvin_qualified','release_authority','routing_admitted',
    'retirement_authority','placement_authority','external_quiet_tree_qualified','no_path_proof')
GATES=('typed_phases','current','protected_copper_pairs','field','ground_returns',
    'contact_kelvin_preservation','source_intake','candidate_intake','native','progress','parity',
    'craft','live','all_phase_source_families_live','suite_live','code_and_inputs_live')


def receipt():
    source=dict(scope='Source_typed_local_auxiliary_measurement_join',complete=True,
        source='/Source',source_sha256='a'*64,paired_pad_uuid='paired',auxiliary_pad_uuid='auxiliary',
        isolated_auxiliary=dict(auxiliary_pad_uuid='auxiliary',native_component_size=1,
            all_saved_zone_islands_included=True),existing_external_quiet_tree_must_remain_exact=True,
        whole_shared_stage_still_required=True,**dict.fromkeys(FLAGS,False))
    proof=dict(ok=True,complete=True,errors=[],scope=source['scope'],Source_plan=source,
        bounded_receiving_stages=2,each_stage_lease_s=10.,composed_budget_s=20.,
        constituent_timings_s=dict(fresh_Source_and_native_ownership=3.,saved_additive_refill_and_partitions=2.),
        source='/Source',source_sha256='a'*64,candidate='/strap',candidate_sha256='b'*64,
        added_track_uuid='strap-track',independent_saved_literal_strap=dict(
            track_uuids=['strap-track'],boundary_uuids=['auxiliary']),
        positive_native_pad_contacts_nm2=dict(paired=100,auxiliary=200),
        saved_additive_receiving=dict(ok=True,complete=True),
        whole_native_Source_partitions=dict(available=True,preserved=True),
        existing_external_copper_and_all_fills_literal_exact=True,
        unchanged_external_quiet_tree_debt_not_qualified=True,
        whole_shared_stage_still_required=True,**dict.fromkeys(FLAGS,False))
    return dict(ok=True,complete=True,baseline='/Source',baseline_sha256='a'*64,
        candidate='/print',candidate_sha256='c'*64,
        gates=dict.fromkeys(GATES,True),phases=[dict(kind='measurement_auxiliary_input_join',
            candidate='/strap',candidate_sha256='b'*64,receiving=proof),dict(kind='print_context',
            candidate='/print',candidate_sha256='c'*64,receiving=dict(ok=True,complete=True))],
        reports=dict(clipped=dict(same_evidence=True,comparison_complete=True,
            comparison='qualified_contour_contact_preservation_v1',full_kelvin_qualification=False)),
        **dict.fromkeys(('release_authority','current_qualified','full_kelvin_qualification',
            'factory_qualified','thermal_qualified'),False))


def test_exact_local_scope_requires_original_parent_gates_and_no_qualification():
    result=scopes.received_repair_scope(receipt())
    assert result['exactly_one_Source_derived_local_planar_input_strap_explicit']is True
    assert result['no_external_quiet_tree_or_source_force_copper_changes']is True
    assert result['new_current_or_Kelvin_or_barrel_or_load_qualification']is False
    assert result['inherited_kelvin_uncertainty_not_newly_qualified']is True


def test_native_double_precision_area_is_accepted_without_integer_coercion():
    value=receipt();value['phases'][0]['receiving']['positive_native_pad_contacts_nm2']['paired']=45707765104.0
    assert scopes.received_repair_scope(value)['all_actual_parent_gates_passed']is True


@pytest.mark.parametrize('bad',[float('nan'),float('inf'),float('-inf'),True,'100',None])
def test_nonfinite_or_non_numeric_native_contact_area_refuses(bad):
    value=receipt();value['phases'][0]['receiving']['positive_native_pad_contacts_nm2']['paired']=bad
    with pytest.raises(ValueError):scopes.received_repair_scope(value)


@pytest.mark.parametrize('gate',GATES)
def test_each_original_parent_gate_is_mandatory(gate):
    value=receipt();value['gates'][gate]=False
    with pytest.raises(ValueError):scopes.received_repair_scope(value)


@pytest.mark.parametrize('owner',['proof','Source_plan'])
@pytest.mark.parametrize('flag',FLAGS)
def test_local_strap_never_funds_external_or_release_authority(owner,flag):
    value=receipt();proof=value['phases'][0]['receiving']
    (proof if owner=='proof'else proof['Source_plan'])[flag]=True
    with pytest.raises(ValueError):scopes.received_repair_scope(value)


@pytest.mark.parametrize('fault',['wrong_parent','wrong_parent_hash','wrong_child','wrong_child_hash',
    'missing_source','multiple_tracks','wrong_boundary','missing_contact','nonpositive_contact',
    'truthy_contact','no_additive','lost_partition','connected_source','no_zone_inventory',
    'external_changed','external_qualified','source_not_exact','loose_contact_relation','no_print',
    'extra_material_phase','changed_final_print'])
def test_no_partial_or_ambiguous_local_proof_is_described(fault):
    value=receipt();proof=value['phases'][0]['receiving'];source=proof['Source_plan']
    if fault=='wrong_parent':proof['source']='/other'
    elif fault=='wrong_parent_hash':proof['source_sha256']='d'*64
    elif fault=='wrong_child':proof['candidate']='/other'
    elif fault=='wrong_child_hash':proof['candidate_sha256']='d'*64
    elif fault=='missing_source':proof['Source_plan']={}
    elif fault=='multiple_tracks':proof['independent_saved_literal_strap']['track_uuids'].append('extra')
    elif fault=='wrong_boundary':proof['independent_saved_literal_strap']['boundary_uuids']=['paired']
    elif fault=='missing_contact':del proof['positive_native_pad_contacts_nm2']['auxiliary']
    elif fault=='nonpositive_contact':proof['positive_native_pad_contacts_nm2']['auxiliary']=0
    elif fault=='truthy_contact':proof['positive_native_pad_contacts_nm2']['auxiliary']=True
    elif fault=='no_additive':proof['saved_additive_receiving']['complete']=False
    elif fault=='lost_partition':proof['whole_native_Source_partitions']['preserved']=False
    elif fault=='connected_source':source['isolated_auxiliary']['native_component_size']=2
    elif fault=='no_zone_inventory':source['isolated_auxiliary']['all_saved_zone_islands_included']=False
    elif fault=='external_changed':proof['existing_external_copper_and_all_fills_literal_exact']=False
    elif fault=='external_qualified':proof['unchanged_external_quiet_tree_debt_not_qualified']=False
    elif fault=='source_not_exact':source['existing_external_quiet_tree_must_remain_exact']=False
    elif fault=='loose_contact_relation':value['reports']['clipped']['comparison']='loose_relation'
    elif fault=='no_print':value['phases'].pop()
    elif fault=='extra_material_phase':value['phases'].insert(1,copy.deepcopy(value['phases'][0]))
    elif fault=='changed_final_print':value['phases'][-1]['candidate_sha256']='d'*64
    with pytest.raises(ValueError):scopes.received_repair_scope(value)
