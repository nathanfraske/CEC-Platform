"""Pure descriptor semantics; synthetic claims are NOT physical authority."""
import copy
import pytest
import root_received_macro_measurement_scope_20261028 as d


def uid(n):return f'{n:08x}-1111-4111-8111-111111111111'


def receipt():
    t,v,added,pad=uid(1),uid(2),uid(3),uid(4)
    source='/private/original';prefix='/private/preclear';macro='/private/cell';measure='/private/input';final='/private/print'
    sha=['a'*64,'b'*64,'c'*64,'d'*64]
    ordinary=dict(ok=True,complete=True,scope='bounded_ordinary_source_delta_receiving',errors=[],max_retired_tracks=32,
        retired_track_uuids=[t],retired_via_uuids=[v],locked_scope_used=[t],locked_via_scope_used=[v],
        source_candidate_and_code_unchanged=True,original_power_pair_sense_and_placement_geometry_exact=True,
        all_prior_native_terminal_partitions_preserved=True,all_prior_surviving_copper_junctions_preserved=True,
        release_authority=False,inherited_debt_qualified=False,power_authority=False,redundant_single_face_via_ownership=[],
        dispatch_Source_lock_inventory=dict(allow_locked_track_uuids=[t],allow_locked_via_uuids=[v],
            exact_requested_Source_lock_inventory_derived=True,grouped_copper_permission=False,unrelated_locked_copper_permission=False),
        exclusive_retired_via_ownership=[dict(via_uuid=v,no_surviving_land_barrel_or_track_contact=True,
            all_departures_in_exact_typed_retirement=True,release_authority=False,source_contact_track_uuids=[t],net='/ordinary')],
        boundary_restoration=[dict(restored=True,net='/ordinary',retired_uuids=[t])],
        paired_native_partition_preservation=dict(available=True,preserved=True,demoted_component_count=0,whole_zone_uuid_connectivity_credit=False),
        exact_subtract_add_ground_rule_replay=dict(scope='source_plus_additions_ground_refill_receiving',ok=True,complete=True,
            errors=[],original_power_and_terminal_geometry_exact=True,existing_ground_fill_matches_independent_native_replay=True,
            exact_object_rule_matches_independent_native_replay=True))
    cell=dict(ok=True,complete=True,scope='independent_saved_source_owned_macro_cell',errors=[],
        all_original_surviving_native_partitions_preserved=True,source_candidate_families_and_code_unchanged=True,
        all_original_physical_ground_returns=dict(ok=True),actual_native_terminal_paths=[dict(kind='ground')],
        independent_exact_source_cut_transform_and_additions=dict(ok=True,complete=True),
        source_sha256=sha[1],candidate_sha256=sha[2],source_macro_packet=dict(source=prefix,source_sha256=sha[1]),
        routing_admitted=False,fab_ready=False,release_authority=False,current_qualified=False,
        independent_stage_max_seconds=10,stage_timings_s=dict(source_compilation=4.2,native_frame=.3))
    fresh=dict(scope='source_typed_stationary_isolated_measurement_join',complete=True,source=macro,source_sha256=sha[2],pad_uuid=pad,
        request=dict(demand=dict(pad_uuid=pad,net='/quiet',source_segment=dict(start=dict(ref='arbitrary_input'),leg='p',net='/quiet'))))
    joined=dict(ok=True,complete=True,scope='source_typed_isolated_measurement_saved_native_join',errors=[],
        exact_source_pickup_aperture_preserved=True,whole_shared_stage_still_required=True,
        current_authority=False,kelvin_qualified=False,retirement_authority=False,placement_authority=False,
        release_authority=False,routing_admitted=False,independently_compiled_source_scope=fresh,
        source_components=2,candidate_components=1,added_native_uuids=[added],complete_saved_path_craft=dict(ok=True,complete=True))
    phases=[dict(kind=d.PREFIX,candidate=prefix,candidate_sha256=sha[1],net='/ordinary',retired_track_uuids=[t],retired_via_uuids=[v],receiving=ordinary),
        dict(kind=d.MACRO,candidate=macro,candidate_sha256=sha[2],receiving=cell),
        dict(kind=d.MEASUREMENT,candidate=measure,candidate_sha256=sha[3],pad_uuid=pad,receiving=joined),
        dict(kind=d.PRINT,candidate=final,candidate_sha256=sha[3],receiving=dict(ok=True,complete=True))]
    suffix=dict(comparison_complete=True,same_evidence=True,raw_parent_and_candidate_evidence_not_rewritten=True,
        full_kelvin_qualification=False,release_authority=False,errors=[],actual_Source_derived_repair_legs=[['arbitrary_input','p','/quiet']],
        repaired_nets=[dict(net='/quiet',absolute_after_admission=dict(ok=True,applicable=True,net='/quiet',
            expected_legs=[['arbitrary_input','p']],checked=1,full_kelvin_qualification=False,
            release_authority=False,reasons=[],explicit_input_leg_scope=True,
            reason='affected_typed_legs_geometrically_verified'))],
        independently_received_measurement_phases=[dict(kind=p['kind'],candidate=p['candidate'],receiving=copy.deepcopy(p['receiving']))for p in phases[2:]])
    relation=dict(same_evidence=True,comparison_complete=True,macro_pose_or_input_repair_authority_not_applied_to_prefix_or_suffix=True,
        actual_macro_parent=prefix,independently_received_prefix_phases=[dict(kind=d.PREFIX,source=source,candidate=prefix,receiving=copy.deepcopy(ordinary))],
        source_evidence_match=dict(comparison_complete=True,same_evidence=True),full_kelvin_qualification=False,release_authority=False,
        macro=dict(ok=True,complete=True,comparison_complete=True,same_evidence=True,source_candidate_families_and_code_unchanged=True,full_kelvin_qualification=False),
        macro_boundary_to_final_comparison='fresh_typed_measurement_absolute_after',independently_received_measurement_suffix=suffix)
    registration=dict(Source_owned_kind=d.PREFIX,kinds=sorted(['ordinary_source_barrel_chain_reflow',d.PREFIX]),
        unchanged_public_receiver='cec_ordinary_route_receiving.receive',exact_Source_ID_sets_only=True,
        legacy_kind_still_requires_unlocked_Source=True,Source_owned_kind_derives_actual_requested_lock_inventory=True,
        all_original_parent_gates_retained=True,callbacks_or_constructor_verdicts_accepted=False,release_authority=False,
        maximum_source_tracks=32,maximum_source_vias=1,maximum_incoming_objects=64,constituent_limit_s=10.,maximum_local_phases_unchanged=6)
    return dict(ok=True,complete=True,gates=dict.fromkeys(d.GATES,True),phases=phases,candidate=final,candidate_sha256=sha[3],
        scope_source=source,scope_source_sha256=sha[0],registered_saved_receiver=registration,reports=dict(clipped=relation),
        current_qualified=False,full_kelvin_qualification=False,factory_qualified=False,thermal_qualified=False,
        release_authority=False,admitted=False,source_selected=False)


def test_descriptor_is_explicit_review_not_fab_current_or_selection_authority():
    r=receipt();before=copy.deepcopy(r);q=d.received_repair_scope(r)
    assert q['measurement_suffix_repair_authority_not_inherited_from_macro']
    assert q['Source_owned_isolated_measurement_additions_explicit']
    assert not q['release_authority']and not q['new_current_or_Kelvin_qualification']and r==before


def test_actual_base_receipt_endpoint_only_phase_shape_derives_public_proof_ids():
    r=receipt()
    for phase in r['phases']:
        for key in('net','retired_track_uuids','retired_via_uuids','pad_uuid'):phase.pop(key,None)
    assert d.received_repair_scope(r)['all_actual_parent_gates_passed']


@pytest.mark.parametrize('gate',sorted(d.GATES))
def test_every_original_parent_gate_is_mandatory(gate):
    r=receipt();r['gates'][gate]=False
    with pytest.raises(ValueError):d.received_repair_scope(r)


@pytest.mark.parametrize('fault',['registration','legacy_unlocked','locks','unrelated_lock','group','exclusive','partition',
    'raw_ground','macro_source','macro_sha','macro_return','macro_delta','macro_late','macro_qualification',
    'prefix_source','prefix_false','input_source','input_uuid','input_count','input_craft','input_authority',
    'repair_leg','extra_repair','raw_rewritten','suffix_false','suffix_endpoint','strict_alias','final_hash','release'])
def test_forged_or_incomplete_self_owned_boundaries_refuse(fault):
    r=receipt();p=r['phases'];a=p[0]['receiving'];m=p[1]['receiving'];i=p[2]['receiving'];rel=r['reports']['clipped'];s=rel['independently_received_measurement_suffix']
    if fault=='registration':r['registered_saved_receiver']['Source_owned_kind']='ordinary_source_barrel_chain_reflow'
    elif fault=='legacy_unlocked':r['registered_saved_receiver']['legacy_kind_still_requires_unlocked_Source']=False
    elif fault=='locks':a['locked_scope_used']=[]
    elif fault=='unrelated_lock':a['dispatch_Source_lock_inventory']['allow_locked_track_uuids'].append(uid(99))
    elif fault=='group':a['dispatch_Source_lock_inventory']['grouped_copper_permission']=True
    elif fault=='exclusive':a['exclusive_retired_via_ownership'][0]['all_departures_in_exact_typed_retirement']=False
    elif fault=='partition':a['paired_native_partition_preservation']['preserved']=False
    elif fault=='raw_ground':a['exact_subtract_add_ground_rule_replay']['existing_ground_fill_matches_independent_native_replay']=False
    elif fault=='macro_source':m['source_macro_packet']['source']='/different/source'
    elif fault=='macro_sha':m['source_sha256']='f'*64
    elif fault=='macro_return':m['all_original_physical_ground_returns']['ok']=False
    elif fault=='macro_delta':m['independent_exact_source_cut_transform_and_additions']['complete']=False
    elif fault=='macro_late':m['stage_timings_s']['source_compilation']=10.01
    elif fault=='macro_qualification':m['current_qualified']=True
    elif fault=='prefix_source':rel['independently_received_prefix_phases'][0]['source']='/other/source'
    elif fault=='prefix_false':rel['source_evidence_match']['same_evidence']=False
    elif fault=='input_source':i['independently_compiled_source_scope']['source']='/arbitrary/trunk'
    elif fault=='input_uuid':i['independently_compiled_source_scope']['pad_uuid']=uid(88)
    elif fault=='input_count':i['candidate_components']=True
    elif fault=='input_craft':i['complete_saved_path_craft']['ok']=False
    elif fault=='input_authority':i['retirement_authority']=True
    elif fault=='repair_leg':s['actual_Source_derived_repair_legs'][0][1]='n'
    elif fault=='extra_repair':s['actual_Source_derived_repair_legs'].append(['peer','n','/quiet'])
    elif fault=='raw_rewritten':s['raw_parent_and_candidate_evidence_not_rewritten']=False
    elif fault=='suffix_false':s['same_evidence']=False
    elif fault=='suffix_endpoint':s['independently_received_measurement_phases'][0]['candidate']='/other/child'
    elif fault=='strict_alias':rel['strict_macro_boundary_to_final']=dict(comparison_complete=True,same_evidence=True)
    elif fault=='final_hash':r['candidate_sha256']='f'*64
    elif fault=='release':r['release_authority']=True
    with pytest.raises(ValueError):d.received_repair_scope(r)


def test_new_pattern_cannot_fall_through_to_legacy(monkeypatch):
    monkeypatch.setattr(d.legacy,'received_repair_scope',lambda _:pytest.fail('malformed new scope fell through'))
    r=receipt();r['phases'][0]['kind']='arbitrary_owner'
    with pytest.raises(ValueError):d.received_repair_scope(r)


def test_legacy_delegate_is_unchanged_and_receives_original_object(monkeypatch):
    r={'phases':[{'kind':'legacy_scope'}]};marker=object();seen=[]
    monkeypatch.setattr(d.legacy,'received_repair_scope',lambda q:(seen.append(q),marker)[1])
    assert d.received_repair_scope(r)is marker and seen==[r]and seen[0]is r


@pytest.mark.parametrize('field,value',[('ok',False),('checked',True),('expected_legs',[['peer','p']]),
    ('explicit_input_leg_scope',False),('full_kelvin_qualification',True),('reasons',['unknown'])])
def test_absolute_after_admission_cannot_be_forged(field,value):
    r=receipt()
    r['reports']['clipped']['independently_received_measurement_suffix']['repaired_nets'][0]['absolute_after_admission'][field]=value
    with pytest.raises(ValueError):d.received_repair_scope(r)
