"""Describe a received macro plus its independently owned input repair.

Pure metadata validation, NOT native receiving, qualification, selection or
permission to trust fabricated receipts. The selection caller must bind the
actual live receipt, files, dependencies, regression and complete suite.
Legacy repair descriptors are delegated without modification.
"""
import re
import math
import root_received_goal_scope_20261024 as legacy

PREFIX='source_owned_ordinary_barrel_chain_reflow'
MACRO='complete_macro'
MEASUREMENT='isolated_measurement_join'
PRINT='print_context'
GATES={'typed_phases','current','protected_copper_pairs','field','ground_returns',
       'contact_kelvin_preservation','source_intake','candidate_intake','native','progress',
       'parity','craft','live','all_phase_source_families_live','suite_live','code_and_inputs_live'}
UUID=re.compile(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}')


def need(value,reason):
    if not value:raise ValueError(reason)


def yes(proof,*keys):
    return type(proof)is dict and all(proof.get(k)is True for k in keys)


def no(proof,*keys):
    return type(proof)is dict and all(proof.get(k)is False for k in keys)


def ids(value,minimum,maximum):
    need(type(value)is list and minimum<=len(value)<=maximum
        and all(type(u)is str and UUID.fullmatch(u)for u in value)
        and len(set(value))==len(value),'exact_bounded_native_UUID_inventory_required')
    return set(value)


def endpoint(phase):
    path,sha=phase.get('candidate'),phase.get('candidate_sha256')
    need(type(path)is str and path and type(sha)is str and re.fullmatch('[0-9a-f]{64}',sha),
        'exact_saved_phase_endpoint_required')
    return path,sha


def _prefix(phase,registration):
    need(registration.get('Source_owned_kind')==PREFIX
        and registration.get('kinds')==sorted(['ordinary_source_barrel_chain_reflow',PREFIX])
        and registration.get('unchanged_public_receiver')=='cec_ordinary_route_receiving.receive'
        and yes(registration,'exact_Source_ID_sets_only','legacy_kind_still_requires_unlocked_Source',
            'Source_owned_kind_derives_actual_requested_lock_inventory','all_original_parent_gates_retained')
        and no(registration,'callbacks_or_constructor_verdicts_accepted','release_authority')
        and registration.get('maximum_source_tracks')==32 and registration.get('maximum_source_vias')==1
        and registration.get('maximum_incoming_objects')==64 and registration.get('constituent_limit_s')==10.
        and registration.get('maximum_local_phases_unchanged')==6,
        'exact_registered_Source_owned_barrel_receiver_required')
    # The base receipt deliberately serializes phase endpoints, not caller
    # options. Scope identities therefore come from the fresh public proof.
    p=phase['receiving'];tracks=ids(p.get('retired_track_uuids'),1,32);vias=ids(p.get('retired_via_uuids'),1,1)
    if 'retired_track_uuids'in phase:need(ids(phase['retired_track_uuids'],1,32)==tracks,'requested_track_scope_differs_from_received')
    if 'retired_via_uuids'in phase:need(ids(phase['retired_via_uuids'],1,1)==vias,'requested_via_scope_differs_from_received')
    need(not tracks&vias and p.get('scope')=='bounded_ordinary_source_delta_receiving'
        and p.get('errors')==[] and p.get('max_retired_tracks')==32
        and ids(p.get('retired_track_uuids'),1,32)==tracks and ids(p.get('retired_via_uuids'),1,1)==vias
        and yes(p,'source_candidate_and_code_unchanged','original_power_pair_sense_and_placement_geometry_exact',
            'all_prior_native_terminal_partitions_preserved','all_prior_surviving_copper_junctions_preserved')
        and no(p,'release_authority','inherited_debt_qualified','power_authority'),
        'independent_exact_Source_owned_ordinary_delta_required')
    lock=p.get('dispatch_Source_lock_inventory',{})
    a=ids(lock.get('allow_locked_track_uuids'),0,32);b=ids(lock.get('allow_locked_via_uuids'),0,1)
    need(a<=tracks and b<=vias and a==ids(p.get('locked_scope_used'),0,32)
        and b==ids(p.get('locked_via_scope_used'),0,1)
        and yes(lock,'exact_requested_Source_lock_inventory_derived')
        and no(lock,'grouped_copper_permission','unrelated_locked_copper_permission'),
        'exact_derived_Source_lock_inventory_required')
    exclusive=p.get('exclusive_retired_via_ownership',[])
    net=exclusive[0].get('net')if type(exclusive)is list and len(exclusive)==1 else None
    need(type(net)is str and bool(net)and phase.get('net',net)==net,'one_actual_Source_ordinary_net_required')
    need(type(exclusive)is list and len(exclusive)==1 and exclusive[0].get('via_uuid')in vias
        and yes(exclusive[0],'no_surviving_land_barrel_or_track_contact','all_departures_in_exact_typed_retirement')
        and no(exclusive[0],'release_authority')
        and ids(exclusive[0].get('source_contact_track_uuids'),1,32)<=tracks
        and p.get('redundant_single_face_via_ownership')==[],
        'complete_exclusive_Source_barrel_departures_required')
    boundaries=p.get('boundary_restoration',[])
    need(type(boundaries)is list and boundaries and all(yes(q,'restored')for q in boundaries)
        and {q.get('net')for q in boundaries}=={net}
        and set().union(*(ids(q.get('retired_uuids'),1,32)for q in boundaries))==tracks,
        'complete_original_Source_boundary_restoration_required')
    partition=p.get('paired_native_partition_preservation',{})
    need(yes(partition,'available','preserved')and partition.get('demoted_component_count')==0
        and no(partition,'whole_zone_uuid_connectivity_credit'),'exact_native_island_preservation_required')
    additive=p.get('exact_subtract_add_ground_rule_replay',{})
    need(additive.get('scope')=='source_plus_additions_ground_refill_receiving'
        and yes(additive,'ok','complete','original_power_and_terminal_geometry_exact',
            'existing_ground_fill_matches_independent_native_replay','exact_object_rule_matches_independent_native_replay')
        and additive.get('errors')==[],'exact_independent_Source_subtract_add_replay_required')


def _measurement(phase,source,source_sha):
    p=phase['receiving'];fresh=p.get('independently_compiled_source_scope',{})
    pad=fresh.get('pad_uuid');ids([pad],1,1)
    need(p.get('scope')=='source_typed_isolated_measurement_saved_native_join'and p.get('errors')==[]
        and yes(p,'ok','complete','exact_source_pickup_aperture_preserved','whole_shared_stage_still_required')
        and no(p,'current_authority','kelvin_qualified','retirement_authority','placement_authority','release_authority','routing_admitted')
        and fresh.get('scope')=='source_typed_stationary_isolated_measurement_join'
        and fresh.get('complete')is True and fresh.get('source')==source and fresh.get('source_sha256')==source_sha
        and phase.get('pad_uuid',pad)==pad
        and type(p.get('source_components'))is int and type(p.get('candidate_components'))is int
        and 0<p['candidate_components']<p['source_components']
        and bool(ids(p.get('added_native_uuids'),1,16))
        and yes(p.get('complete_saved_path_craft',{}),'ok','complete'),
        'exact_independent_Source_measurement_reduction_required')
    demand=fresh.get('request',{}).get('demand',{});segment=demand.get('source_segment',{})
    ref=segment.get('start',{}).get('ref');net=demand.get('net');leg=segment.get('leg')
    need(demand.get('pad_uuid')==pad and type(ref)is str and bool(ref)
        and type(net)is str and bool(net)and segment.get('net')==net and leg in('p','n'),
        'actual_Source_manufacturer_input_leg_required')
    return [ref,leg,net]


def received_repair_scope(receipt):
    phases=receipt.get('phases');kinds=[p.get('kind')for p in phases]if type(phases)is list else []
    if not (MACRO in kinds and MEASUREMENT in kinds):return legacy.received_repair_scope(receipt)
    need(yes(receipt,'ok','complete')and type(receipt.get('gates'))is dict
        and GATES<=receipt['gates'].keys()and all(v is True for v in receipt['gates'].values()),
        'all_live_original_parent_gates_required')
    need(4<=len(phases)<=6 and kinds[:2]==[PREFIX,MACRO]and kinds[-1]==PRINT
        and all(k==MEASUREMENT for k in kinds[2:-1])
        and kinds.count(MACRO)==1 and all(yes(p.get('receiving',{}),'ok','complete')for p in phases),
        'exact_Source_prefix_macro_self_owned_measurement_print_sequence_required')
    need(endpoint(phases[-1])==(receipt.get('candidate'),receipt.get('candidate_sha256')),
        'exact_final_received_endpoint_required')
    _prefix(phases[0],receipt.get('registered_saved_receiver',{}))
    macro=phases[1]['receiving'];packet=macro.get('source_macro_packet',{})
    parent,sha=endpoint(phases[0]);boundary,boundary_sha=endpoint(phases[1])
    need(macro.get('scope')=='independent_saved_source_owned_macro_cell'and macro.get('errors')==[]
        and yes(macro,'all_original_surviving_native_partitions_preserved','source_candidate_families_and_code_unchanged')
        and yes(macro.get('all_original_physical_ground_returns',{}),'ok')and bool(macro.get('actual_native_terminal_paths'))
        and yes(macro.get('independent_exact_source_cut_transform_and_additions',{}),'ok','complete')
        and macro.get('source_sha256')==sha and macro.get('candidate_sha256')==boundary_sha
        and packet.get('source')==parent and packet.get('source_sha256')==sha
        and no(macro,'routing_admitted','fab_ready','release_authority','current_qualified'),
        'exact_saved_Source_macro_frame_and_returns_required')
    times=macro.get('stage_timings_s',{})
    need(macro.get('independent_stage_max_seconds')==10 and times
        and all(type(v)in(int,float)and math.isfinite(v)and 0<=v<=10 for v in times.values()),
        'bounded_independent_macro_constituents_required')
    relation=receipt.get('reports',{}).get('clipped',{})
    prefix=relation.get('independently_received_prefix_phases',[])
    need(yes(relation,'same_evidence','comparison_complete',
            'macro_pose_or_input_repair_authority_not_applied_to_prefix_or_suffix')
        and relation.get('actual_macro_parent')==parent and len(prefix)==1
        and prefix[0].get('kind')==PREFIX and prefix[0].get('candidate')==parent
        and prefix[0].get('source')==receipt.get('scope_source')
        and yes(prefix[0].get('receiving',{}),'ok','complete')
        and yes(relation.get('source_evidence_match',{}),'comparison_complete','same_evidence')
        and no(relation,'full_kelvin_qualification','release_authority'),
        'strict_original_prefix_and_raw_macro_boundary_required')
    contact=relation.get('macro',{})
    need(yes(contact,'ok','complete','comparison_complete','same_evidence','source_candidate_families_and_code_unchanged')
        and no(contact,'full_kelvin_qualification'),'independent_exact_macro_contact_required')
    legs=[];cursor,sha=boundary,boundary_sha
    for phase in phases[2:-1]:
        leg=_measurement(phase,cursor,sha);need(leg not in legs,'duplicate_actual_input_repair_leg')
        legs.append(leg);cursor,sha=endpoint(phase)
    suffix=relation.get('independently_received_measurement_suffix',{})
    received=suffix.get('independently_received_measurement_phases',[])
    repaired=suffix.get('repaired_nets',[])
    nets={leg[2]for leg in legs}
    need(isinstance(repaired,list)and len(repaired)==len(nets)
        and all(isinstance(row,dict)for row in repaired)
        and {row.get('net')for row in repaired}==nets,
        'exact_absolute_after_net_inventory_required')
    for row in repaired:
        admission=row.get('absolute_after_admission',{})
        expected=[leg[:2]for leg in legs if leg[2]==row['net']]
        need(yes(admission,'ok','applicable','explicit_input_leg_scope')
            and no(admission,'full_kelvin_qualification','release_authority')
            and admission.get('net')==row['net']and admission.get('expected_legs')==expected
            and type(admission.get('checked'))is int and admission['checked']==len(expected)
            and admission.get('reasons')==[]
            and admission.get('reason')=='affected_typed_legs_geometrically_verified',
            'fresh_exact_absolute_after_input_admission_required')
    need(relation.get('macro_boundary_to_final_comparison')=='fresh_typed_measurement_absolute_after'
        and 'strict_macro_boundary_to_final'not in relation
        and yes(suffix,'comparison_complete','same_evidence','raw_parent_and_candidate_evidence_not_rewritten')
        and no(suffix,'full_kelvin_qualification','release_authority')and suffix.get('errors')==[]
        and suffix.get('actual_Source_derived_repair_legs')==legs
        and len(received)==len(phases)-2
        and all(q.get('kind')==p['kind']and q.get('candidate')==p['candidate']
            and yes(q.get('receiving',{}),'ok','complete')for q,p in zip(received,phases[2:])),
        'independently_owned_absolute_measurement_suffix_required')
    need(no(receipt,'current_qualified','full_kelvin_qualification','factory_qualified','thermal_qualified',
        'release_authority','admitted','source_selected'),'review_is_not_release_or_electrical_qualification')
    return dict(scope='independently_received_Source_macro_with_self_owned_measurement_suffix',
        all_copper_parts_pinouts_stack_and_dimensions_unchanged=False,
        source_owned_placement_and_copper_reconstruction_explicit=True,
        preparatory_Source_owned_ordinary_barrel_reconstruction_explicit=True,
        Source_owned_isolated_measurement_additions_explicit=True,
        measurement_suffix_repair_authority_not_inherited_from_macro=True,
        parts_pinouts_courtyards_and_board_outline_preserved=True,all_actual_parent_gates_passed=True,
        inherited_kelvin_uncertainty_not_newly_qualified=True,new_current_or_Kelvin_qualification=False,
        release_authority=False)
