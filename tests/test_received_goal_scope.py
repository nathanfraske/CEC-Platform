"""Ledger scope cannot turn a real copper repair into an ink-only waiver."""
import copy
import importlib.util
from pathlib import Path
import pytest

PATH=Path(__file__).resolve().parents[1]/'build/root_received_goal_scope_20261024.py'
spec=importlib.util.spec_from_file_location('received_goal_scope',PATH)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def fixture():
    # Shape-only consumer tests. This is not native evidence or admission;
    # the ledger driver independently binds the live original receipt and
    # actual saved nine-board suite before this description is usable.
    proof=dict(ok=True,complete=True)
    macro=dict(proof,scope='independent_saved_source_owned_macro_cell',errors=[],
        all_original_surviving_native_partitions_preserved=True,
        all_original_physical_ground_returns=dict(ok=True),actual_native_terminal_paths=[{}],
        independent_exact_source_cut_transform_and_additions=proof,
        routing_admitted=False,fab_ready=False,release_authority=False,current_qualified=False)
    contact=dict(proof,comparison_complete=True,same_evidence=True,
        source_candidate_families_and_code_unchanged=True,full_kelvin_qualification=False)
    return dict(proof,candidate='last',candidate_sha256='last-sha',
        gates={k:True for k in (
            'typed_phases','current','protected_copper_pairs','field','ground_returns',
            'contact_kelvin_preservation','source_intake','candidate_intake','native','progress',
            'parity','craft','live','all_phase_source_families_live','suite_live','code_and_inputs_live')},
        phases=[dict(kind='complete_macro',receiving=macro),
            dict(kind='print_context',candidate='last',candidate_sha256='last-sha',receiving=proof)],
        reports=dict(clipped=dict(same_evidence=True,comparison_complete=True,
            source_evidence_match=dict(same_evidence=True,comparison_complete=True),
            strict_macro_boundary_to_final=dict(same_evidence=True,comparison_complete=True),
            macro=contact,full_kelvin_qualification=False)))


def test_physical_repair_is_explicit_and_cannot_claim_all_copper_unchanged():
    r=fixture();before=copy.deepcopy(r);q=module.complete_macro_scope(r)
    assert r==before
    assert not q['all_copper_parts_pinouts_stack_and_dimensions_unchanged']
    assert q['source_owned_placement_and_copper_reconstruction_explicit']
    assert q['inherited_kelvin_uncertainty_not_newly_qualified']


@pytest.mark.parametrize('fault',[None,'unreceived_prefix','wrong_parent','missing_strict','borrowed_authority',
    'prefix_count','unknown_prefix','unknown_suffix'])
@pytest.mark.parametrize('ground_kind',['source_class_ground_tail','source_ground_land_root_spur'])
def test_cooperative_preclear_macro_owns_only_its_actual_saved_boundary(fault,ground_kind):
    r=fixture();prefix=[dict(kind=k,candidate='prefix'+str(i),receiving=dict(ok=True,complete=True))
        for i,k in enumerate(('source_ordinary_barrel_reseat','rated_branch'))]
    r['phases']=[*prefix,r['phases'][0],
        dict(kind='macro_tail_cleanup',receiving=dict(ok=True,complete=True)),
        dict(kind=ground_kind,receiving=dict(ok=True,complete=True)),r['phases'][-1]]
    relation=r['reports']['clipped']
    relation.update(actual_macro_parent='prefix1',independently_received_prefix_phases=copy.deepcopy(prefix),
        macro_pose_or_input_repair_authority_not_applied_to_prefix_or_suffix=True)
    if fault=='unreceived_prefix':relation['independently_received_prefix_phases'][0]['receiving']['ok']=False
    elif fault=='wrong_parent':relation['actual_macro_parent']='prefix0'
    elif fault=='missing_strict':relation.pop('source_evidence_match')
    elif fault=='borrowed_authority':relation['macro_pose_or_input_repair_authority_not_applied_to_prefix_or_suffix']=False
    elif fault=='prefix_count':relation['independently_received_prefix_phases'].pop()
    elif fault=='unknown_prefix':r['phases'][0]['kind']='unknown'
    elif fault=='unknown_suffix':r['phases'][-2]['kind']='unknown'
    if fault:
        with pytest.raises(ValueError):module.received_repair_scope(r)
    else:
        before=copy.deepcopy(r);value=module.received_repair_scope(r)
        assert r==before and value['preparatory_typed_copper_repairs_explicit']


@pytest.mark.parametrize('fault',[None,'aggregate','qualified','wrong_scope','one_tap','incomplete',
    'unreceived_current','boolean_amps','missing_floor','parts_changed'])
def test_auxiliary_scope_is_not_whole_supply_or_current_qualification(fault):
    r=fixture();r.update(release_authority=False,current_qualified=False,
        full_kelvin_qualification=False,factory_qualified=False,thermal_qualified=False)
    proof=dict(ok=True,complete=True,errors=[],identity_stable=True,
        scope='explicit_auxiliary_attachment_minimum_conductor_geometry_only',
        contract=dict(minimum_conductor_authority=dict(amps=1.,geometry_margin=1.25,margin_included=False),
            aggregate_current_authority=dict(amps=8.,geometry_margin=1.25,margin_included=False),
            declaration=dict(minimum_continuous_amps=1.),aggregate_budget_reduced=False),
        aggregate_budget_reduced=False,original_terminal_partitions_preserved=True,attached_named_connection_proved=True,
        source_topology=dict(aggregate_native_terminals_connected=True),contacts=dict(physical_tap_count=1),
        received_track_uuids=['actual-new-track'],track_requirements={'actual-new-track':.2},
        additive=dict(ok=True,complete=True),**{k:False for k in('current_total_qualified','barrel_current_qualified',
            'whole_fan_supply_qualified','kelvin_qualified','load_model_qualified','thermal_or_transient_qualified','release_authority')})
    r['phases'][0]=dict(kind='auxiliary_attachment',receiving=proof)
    if fault=='aggregate':proof['aggregate_budget_reduced']=True
    elif fault=='qualified':proof['whole_fan_supply_qualified']=True
    elif fault=='wrong_scope':proof['scope']='ordinary'
    elif fault=='one_tap':proof['contacts']['physical_tap_count']=2
    elif fault=='incomplete':proof['complete']=False
    elif fault=='unreceived_current':r['gates']['current']=False
    elif fault=='boolean_amps':proof['contract']['minimum_conductor_authority']['amps']=True
    elif fault=='missing_floor':proof['track_requirements']={}
    elif fault=='parts_changed':proof['additive']['ok']=False
    if fault:
        with pytest.raises(ValueError):module.received_repair_scope(r)
    else:
        value=module.received_repair_scope(r)
        assert value['Source_auxiliary_conductor_additions_explicit']
        assert not value['aggregate_requirement_reduced']and not value['new_current_or_Kelvin_or_barrel_qualification']


def can_fixture():
    r=fixture();r.update(release_authority=False,current_qualified=False,
        full_kelvin_qualification=False,factory_qualified=False,thermal_qualified=False)
    r['phases'][0]=dict(kind='can_endpoint_join',receiving=dict(ok=True,complete=True,errors=[],
        scope='Source_canonical_CAN_surface_endpoint_join',Source_CAN_scope_independently_recompiled=True,
        source_components=2,candidate_components=1,added_native_uuids=['actual-track'],
        ordinary_reclassification=False,pair_performance_qualified=False,current_qualified=False,
        release_authority=False,routing_admitted=False))
    return r


def test_CAN_ledger_description_is_surface_addition_not_pair_qualification():
    r=can_fixture();before=copy.deepcopy(r);q=module.received_repair_scope(r)
    assert r==before and q['Source_owned_surface_CAN_additions_explicit']
    assert not q['all_copper_parts_pinouts_stack_and_dimensions_unchanged']
    assert not q['new_pair_performance_qualification']


@pytest.mark.parametrize('fault',['unreceived','ordinary','source','no_reduction','missing_tracks',
    'pair_rating','wrong_scope','missing_gate','contact','print'])
def test_CAN_ledger_requires_independent_full_parent_gates(fault):
    r=can_fixture();q=r['phases'][0]['receiving']
    if fault=='unreceived':q['ok']=False
    elif fault=='ordinary':q['ordinary_reclassification']=True
    elif fault=='source':q['Source_CAN_scope_independently_recompiled']=False
    elif fault=='no_reduction':q['candidate_components']=2
    elif fault=='missing_tracks':q['added_native_uuids']=[]
    elif fault=='pair_rating':q['pair_performance_qualified']=True
    elif fault=='wrong_scope':q['scope']='planner_claim'
    elif fault=='missing_gate':r['gates'].pop('native')
    elif fault=='contact':r['reports']['clipped']['same_evidence']=False
    else:r['phases'].pop()
    with pytest.raises(ValueError):module.received_repair_scope(r)


def measurement_fixture(mixed=False):
    r=can_fixture()
    q=dict(kind='isolated_measurement_join',receiving=dict(ok=True,complete=True,errors=[],
        scope='source_typed_isolated_measurement_saved_native_join',
        independently_compiled_source_scope=dict(complete=True,
            scope='source_typed_stationary_isolated_measurement_join'),
        source_components=2,candidate_components=1,added_native_uuids=['measurement-track'],
        exact_source_pickup_aperture_preserved=True,whole_shared_stage_still_required=True,
        current_authority=False,kelvin_qualified=False,retirement_authority=False,
        placement_authority=False,release_authority=False,routing_admitted=False))
    if mixed:r['phases'].insert(1,q)
    else:r['phases'][0]=q
    return r


@pytest.mark.parametrize('mixed',[False,True])
def test_measurement_join_description_cannot_claim_current_or_Kelvin_qualification(mixed):
    r=measurement_fixture(mixed);before=copy.deepcopy(r);q=module.received_repair_scope(r)
    assert r==before and q['Source_owned_isolated_measurement_additions_explicit']
    assert q['Source_owned_CAN_additions_explicit']is mixed
    assert q['Source_contained_barrels_explicit']is False
    assert q['new_current_or_Kelvin_qualification']is False
    assert q['all_copper_parts_pinouts_stack_and_dimensions_unchanged']is False


@pytest.mark.parametrize('fault',['unreceived','scope','source_scope','source_incomplete','pickup',
    'no_reduction','boolean_source','boolean_child','missing_tracks','current','kelvin','retirement',
    'placement','release','whole_stage','unknown_phase','missing_gate','contact','print'])
def test_measurement_ledger_requires_independent_typed_proof_and_all_parent_gates(fault):
    r=measurement_fixture(True);q=r['phases'][1]['receiving']
    if fault=='unreceived':q['ok']=False
    elif fault=='scope':q['scope']='worker_claim'
    elif fault=='source_scope':q['independently_compiled_source_scope']['scope']='ordinary'
    elif fault=='source_incomplete':q['independently_compiled_source_scope']['complete']=False
    elif fault=='pickup':q['exact_source_pickup_aperture_preserved']=False
    elif fault=='no_reduction':q['candidate_components']=2
    elif fault=='boolean_source':q['source_components']=True
    elif fault=='boolean_child':q['candidate_components']=True
    elif fault=='missing_tracks':q['added_native_uuids']=[]
    elif fault in('current','kelvin','retirement','placement','release'):
        key={'current':'current_authority','kelvin':'kelvin_qualified','retirement':'retirement_authority',
            'placement':'placement_authority','release':'release_authority'}[fault];q[key]=True
    elif fault=='whole_stage':q['whole_shared_stage_still_required']=False
    elif fault=='unknown_phase':r['phases'][1]['kind']='arbitrary_callback'
    elif fault=='missing_gate':r['gates'].pop('native')
    elif fault=='contact':r['reports']['clipped']['same_evidence']=False
    else:r['phases'].pop()
    with pytest.raises(ValueError):module.received_repair_scope(r)


@pytest.mark.parametrize('gate',list(fixture()['gates']))
@pytest.mark.parametrize('fault',['missing','false','truthy'])
def test_every_original_parent_gate_is_mandatory(gate,fault):
    r=fixture()
    if fault=='missing':r['gates'].pop(gate)
    else:r['gates'][gate]=False if fault=='false'else 1
    with pytest.raises(ValueError):module.complete_macro_scope(r)


@pytest.mark.parametrize('fault',[
    'scope','partition','return','paths','exact','phase','endpoint','contact',
    'source_contact','remainder','contact_live','qualified','missing_print','unknown_cleanup'])
def test_incomplete_or_relabelled_macro_never_acquires_ledger_scope(fault):
    r=fixture();m=r['phases'][0]['receiving'];c=r['reports']['clipped']
    if fault=='scope':m['scope']='planner_only'
    elif fault=='partition':m['all_original_surviving_native_partitions_preserved']=False
    elif fault=='return':m['all_original_physical_ground_returns']['ok']=False
    elif fault=='paths':m['actual_native_terminal_paths']=[]
    elif fault=='exact':m['independent_exact_source_cut_transform_and_additions']={}
    elif fault=='phase':r['phases'][-1]['receiving']={}
    elif fault=='endpoint':r['phases'][-1]['candidate_sha256']='different'
    elif fault=='contact':c['same_evidence']=False
    elif fault=='source_contact':c['source_evidence_match']={}
    elif fault=='remainder':c['strict_macro_boundary_to_final']={}
    elif fault=='contact_live':c['macro']['source_candidate_families_and_code_unchanged']=False
    elif fault=='qualified':c['full_kelvin_qualification']=True
    elif fault=='missing_print':r['phases'].pop()
    else:r['phases'].insert(1,dict(kind='arbitrary_callback',receiving=dict(ok=True,complete=True)))
    with pytest.raises(ValueError):module.complete_macro_scope(r)


def rated_fixture():
    r=fixture();r.update(release_authority=False,current_qualified=False,
        full_kelvin_qualification=False,factory_qualified=False,thermal_qualified=False)
    proof=dict(ok=True,complete=True,scope='rated_branch_and_additive_scalar_receiving',errors=[],
        source_proposal=dict(repair_undersized_source=True,exact_source_current_fault_keys=[['trace','renamed','uid','In2.Cu']],
            full_load_width_required=True,inferred_branch_load=False),
        source_distributed_load_ownership_unchanged=True,all_surviving_native_partitions_preserved=True,
        all_unowned_current_copper_poses_and_power_fills_exact=True,new_barrel_ampacity_credited=False,
        exact_source_cut_additions_ground_and_rule_replay=dict(ok=True,complete=True),
        strict_source_current_fault_repair=dict(ok=True,complete=True,before_fault_objects=2,
            after_fault_objects=0,new_faults=[],worsened_faults=[]),
        literal_source_subtraction=dict(exact_opaque_source_subtraction=True,independent_full_native_inventory_equal=True))
    r['phases'][0]=dict(kind='rated_branch',receiving=proof)
    return r


def test_rated_current_repair_is_physical_not_silently_ink_only():
    r=rated_fixture();original=copy.deepcopy(r);scope=module.received_repair_scope(r)
    assert r==original and scope['source_owned_current_reconstruction_explicit']
    assert not scope['all_copper_parts_pinouts_stack_and_dimensions_unchanged']
    assert not scope['new_through_barrel_ampacity_credited']
    assert scope['all_actual_parent_gates_passed']


@pytest.mark.parametrize('fault',['missing_gate','truthy_gate','unproved_source','new_debt','no_reduction',
    'partition','literal','no_native_equality','missing_print','unknown_cleanup','release','contact'])
def test_rated_ledger_description_needs_actual_whole_parent_and_source_proofs(fault):
    r=rated_fixture();proof=r['phases'][0]['receiving']
    if fault=='missing_gate':r['gates'].pop('field')
    elif fault=='truthy_gate':r['gates']['field']=1
    elif fault=='unproved_source':proof['source_proposal']['exact_source_current_fault_keys']=[]
    elif fault=='new_debt':proof['strict_source_current_fault_repair']['new_faults']=['new']
    elif fault=='no_reduction':proof['strict_source_current_fault_repair']['after_fault_objects']=2
    elif fault=='partition':proof['all_surviving_native_partitions_preserved']=False
    elif fault=='literal':proof['literal_source_subtraction']['exact_opaque_source_subtraction']=False
    elif fault=='no_native_equality':proof['literal_source_subtraction']['independent_full_native_inventory_equal']=False
    elif fault=='missing_print':r['phases'].pop()
    elif fault=='unknown_cleanup':r['phases'].insert(1,dict(kind='callback',receiving=dict(ok=True,complete=True)))
    elif fault=='release':r['release_authority']=True
    else:r['reports']['clipped']['same_evidence']=False
    with pytest.raises(ValueError):module.received_repair_scope(r)


def caption_fixture():
    r=rated_fixture();r['phases'][0]=dict(kind='root_caption_seat',receiving=dict(ok=True,complete=True,
        translation_only=False,exact_reviewed_caption_translation_and_readable_floor_only=True,
        whole_saved_second_native_roundtrip_stable=True))
    r['reports']['contact_caption_query_identity']=dict(ok=True,complete=True,same_material=True,
        comparison_complete=True,mutation_authority=False,full_kelvin_qualification=False)
    return r


def test_caption_floor_enlargement_is_exact_reviewed_annotation_not_copper_work():
    r=caption_fixture();scope=module.received_repair_scope(r)
    assert scope['all_copper_parts_pinouts_stack_and_dimensions_unchanged']
    assert scope['inherited_kelvin_uncertainty_not_newly_qualified']


@pytest.mark.parametrize('fault',['missing_scope','unreceived','unstable_save','no_query','query_mutation',
    'query_qualification','missing_print','extra_material_phase'])
def test_caption_ledger_cannot_describe_unreceived_or_physical_work_as_ink(fault):
    r=caption_fixture();proof=r['phases'][0]['receiving']
    if fault=='missing_scope':proof.pop('exact_reviewed_caption_translation_and_readable_floor_only')
    elif fault=='unreceived':proof['complete']=False
    elif fault=='unstable_save':proof['whole_saved_second_native_roundtrip_stable']=False
    elif fault=='no_query':r['reports'].pop('contact_caption_query_identity')
    elif fault=='query_mutation':r['reports']['contact_caption_query_identity']['mutation_authority']=True
    elif fault=='query_qualification':r['reports']['contact_caption_query_identity']['full_kelvin_qualification']=True
    elif fault=='missing_print':r['phases'].pop()
    else:r['phases'].insert(1,dict(kind='rated_branch',receiving=dict(ok=True,complete=True)))
    with pytest.raises(ValueError):module.received_repair_scope(r)


def detached_fixture():
    r=rated_fixture();r['phases']=[dict(kind='detached_passive_translation',receiving=dict(
        ok=True,complete=True,errors=[],exact_literal_root_at_only=True,
        all_copper_pads_fields_rules_and_parts_unchanged=True,release_authority=False)),
        dict(kind='ordinary_join',receiving=dict(ok=True,complete=True,errors=[],
            scope='ordinary_saved_additive_native_join',source_ordinary_scope_independently_recompiled=True,
            source_components=2,candidate_components=1,added_native_uuids=['actual-addition'],
            routing_admitted=False,current_qualified=False,release_authority=False)),r['phases'][-1]]
    return r


def test_detached_translation_plus_real_join_is_explicit_physical_progress_not_ink_only():
    r=detached_fixture();scope=module.received_repair_scope(r)
    assert scope['source_owned_detached_placement_and_additive_join_explicit']
    assert scope['all_copper_parts_pinouts_stack_and_dimensions_unchanged']is False
    assert scope['all_actual_parent_gates_passed']is True


@pytest.mark.parametrize('fault',['missing-gate','pose','pose-extra-material','ordinary-role','no-join',
    'boolean-components','no-additions','qualified','unreceived','unknown-phase','no-print'])
def test_unreceived_or_relabelled_detached_routes_cannot_gain_ledger_scope(fault):
    r=detached_fixture();pose=r['phases'][0]['receiving'];joined=r['phases'][1]['receiving']
    if fault=='missing-gate':r['gates'].pop('native')
    elif fault=='pose':pose['exact_literal_root_at_only']=False
    elif fault=='pose-extra-material':pose['all_copper_pads_fields_rules_and_parts_unchanged']=False
    elif fault=='ordinary-role':joined['source_ordinary_scope_independently_recompiled']=False
    elif fault=='no-join':joined['candidate_components']=2
    elif fault=='boolean-components':joined['candidate_components']=True
    elif fault=='no-additions':joined['added_native_uuids']=[]
    elif fault=='qualified':joined['current_qualified']=True
    elif fault=='unreceived':joined['complete']=False
    elif fault=='unknown-phase':r['phases'][1]['kind']='callback'
    else:r['phases'].pop()
    with pytest.raises(ValueError):module.received_repair_scope(r)
