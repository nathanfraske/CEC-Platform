"""Describe an already received physical repair without calling it ink-only.

This is ledger validation, not a receiving bypass. The caller still binds
the live receipt, Source, selected saved suite, code, regressions and archive.
No new qualification or mutation authority is returned here.
"""


def _need(condition, reason):
    if not condition:
        raise ValueError(reason)


def complete_macro_scope(receipt):
    if sum(p.get('kind')=='complete_macro'for p in receipt.get('phases',[]))>1:
        return _complete_macro_chain_scope(receipt)
    from root_receive_local_transaction_20261022 import MAX_LOCAL_PHASES
    required = {
        'typed_phases', 'current', 'protected_copper_pairs', 'field',
        'ground_returns', 'contact_kelvin_preservation', 'source_intake',
        'candidate_intake', 'native', 'progress', 'parity', 'craft', 'live',
        'all_phase_source_families_live', 'suite_live', 'code_and_inputs_live',
    }
    gates = receipt.get('gates', {})
    _need(receipt.get('ok') is True and receipt.get('complete') is True
          and required <= gates.keys() and all(v is True for v in gates.values()),
          'complete_live_original_parent_macro_gates_required')
    phases = receipt.get('phases')
    _need(type(phases) is list and 2 <= len(phases) <= MAX_LOCAL_PHASES
          and sum(p.get('kind')=='complete_macro'for p in phases)==1
          and phases[-1].get('kind') == 'print_context'
          ,'exact_saved_macro_then_typed_cleanup_and_print_boundary_required')
    index=next(i for i,p in enumerate(phases)if p.get('kind')=='complete_macro')
    _need(all(p.get('kind')in {'source_ordinary_barrel_reseat','rated_branch',
                             'redundant_source_ground_link'}for p in phases[:index])
          and all(p.get('kind') in {'reference_fields', 'reference_map',
                                   'root_reference_seat', 'macro_tail_cleanup','source_class_ground_tail',
                                   'source_ground_land_root_spur','source_ground_literal_endpoint_tail',
                                   'redundant_source_ground_link'}
                  for p in phases[index+1:-1]),
          'exact_saved_macro_then_typed_cleanup_and_print_boundary_required')
    _need(phases[-1].get('candidate') == receipt.get('candidate')
          and phases[-1].get('candidate_sha256') == receipt.get('candidate_sha256'),
          'exact_final_macro_transaction_endpoint_required')
    for phase in phases:
        proof = phase.get('receiving', {})
        _need(proof.get('ok') is True and proof.get('complete') is True,
              'all_saved_macro_transaction_phases_must_be_received')
    macro = phases[index]['receiving']
    _need(macro.get('scope') == 'independent_saved_source_owned_macro_cell'
          and macro.get('errors') == []
          and macro.get('all_original_surviving_native_partitions_preserved') is True
          and macro.get('all_original_physical_ground_returns', {}).get('ok') is True
          and bool(macro.get('actual_native_terminal_paths')),
          'independent_complete_saved_macro_path_and_return_proofs_required')
    exact = macro.get('independent_exact_source_cut_transform_and_additions', {})
    _need(exact.get('ok') is True and exact.get('complete') is True,
          'independent_exact_source_cut_transform_required')
    relation = receipt.get('reports', {}).get('clipped', {})
    if index:
        prefix=relation.get('independently_received_prefix_phases',[])
        _need(relation.get('macro_pose_or_input_repair_authority_not_applied_to_prefix_or_suffix')is True
            and relation.get('actual_macro_parent')==phases[index-1].get('candidate')
            and len(prefix)==index
            and [p.get('kind')for p in prefix]==[p.get('kind')for p in phases[:index]]
            and [p.get('candidate')for p in prefix]==[p.get('candidate')for p in phases[:index]]
            and all(p.get('receiving',{}).get('ok')is True
                and p['receiving'].get('complete')is True for p in prefix),
            'independent_strict_macro_prefix_contact_boundary_required')
    _need(relation.get('same_evidence') is True
          and relation.get('comparison_complete') is True,
          'original_parent_macro_contact_preservation_required')
    for key in ('source_evidence_match', 'strict_macro_boundary_to_final'):
        proof = relation.get(key, {})
        _need(proof.get('same_evidence') is True
              and proof.get('comparison_complete') is True,
              'exact_macro_contact_boundary_and_remainder_required')
    contact = relation.get('macro', {})
    _need(all(contact.get(k) is True for k in (
        'ok', 'complete', 'comparison_complete', 'same_evidence',
        'source_candidate_families_and_code_unchanged')),
        'independent_saved_macro_contact_receiving_required')
    _need(all(macro.get(k) is False for k in (
        'routing_admitted', 'fab_ready', 'release_authority', 'current_qualified'))
        and relation.get('full_kelvin_qualification') is False
        and contact.get('full_kelvin_qualification') is False,
        'routing_review_must_not_be_relabelled_full_qualification')
    return dict(
        scope='independently_received_complete_source_owned_native_macro',
        all_copper_parts_pinouts_stack_and_dimensions_unchanged=False,
        source_owned_placement_and_copper_reconstruction_explicit=True,
        preparatory_typed_copper_repairs_explicit=bool(index),
        parts_pinouts_courtyards_and_board_outline_preserved=True,
        all_actual_parent_gates_passed=True,
        inherited_kelvin_uncertainty_not_newly_qualified=True,
    )


def _complete_macro_chain_scope(receipt):
    """Describe two independently received immediate Source boundaries.

    This is not a proof constructor. The live-bound transaction must already
    contain the raw contact chain and every unchanged original-parent gate.
    Neither the second macro nor this descriptor can qualify old debt.
    """
    from root_receive_local_transaction_20261022 import MAX_LOCAL_PHASES,MAX_COMPLETE_MACROS
    required={'typed_phases','current','protected_copper_pairs','field','ground_returns',
        'contact_kelvin_preservation','source_intake','candidate_intake','native','progress',
        'parity','craft','live','all_phase_source_families_live','suite_live','code_and_inputs_live'}
    gates=receipt.get('gates',{});phases=receipt.get('phases',[])
    _need(receipt.get('ok')is True and receipt.get('complete')is True
        and required<=gates.keys()and all(v is True for v in gates.values()),
        'all_live_original_parent_macro_chain_gates_required')
    indices=[i for i,p in enumerate(phases)if p.get('kind')=='complete_macro']
    _need(3<=len(phases)<=MAX_LOCAL_PHASES and len(indices)==MAX_COMPLETE_MACROS
        and indices[1]==indices[0]+1 and phases[-1].get('kind')=='print_context'
        and all(p.get('kind')in {'source_ordinary_barrel_reseat','rated_branch',
            'redundant_source_ground_link'}for p in phases[:indices[0]])
        and all(p.get('kind')in {'reference_fields','reference_map','root_reference_seat',
            'macro_tail_cleanup','source_class_ground_tail','source_ground_land_root_spur',
            'source_ground_literal_endpoint_tail','redundant_source_ground_link'}
            for p in phases[indices[-1]+1:-1]),'exact_bounded_immediate_Source_macro_chain_required')
    _need(phases[-1].get('candidate')==receipt.get('candidate')
        and phases[-1].get('candidate_sha256')==receipt.get('candidate_sha256'),
        'exact_final_macro_chain_endpoint_required')
    _need(all(p.get('receiving',{}).get('ok')is True and p['receiving'].get('complete')is True
        for p in phases),'every_typed_saved_macro_chain_phase_must_be_received')
    relation=receipt.get('reports',{}).get('clipped',{})
    _need(relation.get('scope')=='bounded_immediate_Source_macro_contact_chain'
        and all(relation.get(k)is True for k in('comparison_complete','same_evidence',
            'all_immediate_Source_macro_boundaries_received','source_candidate_families_and_code_unchanged',
            'macro_pose_or_input_repair_authority_not_applied_to_prefix_or_suffix'))
        and relation.get('source')==receipt.get('scope_source')
        and relation.get('source_sha256')==receipt.get('scope_source_sha256')
        and relation.get('candidate')==receipt.get('candidate')
        and relation.get('candidate_sha256')==receipt.get('candidate_sha256'),
        'fresh_exact_original_parent_macro_contact_chain_required')
    boundaries=relation.get('macro_boundaries',[])
    _need(type(boundaries)is list and len(boundaries)==MAX_COMPLETE_MACROS,
        'every_immediate_Source_macro_contact_boundary_required')

    def positive(proof,*keys):
        return type(proof)is dict and all(proof.get(k)is True for k in keys)

    def actual_macro(proof,parent,parent_sha,phase):
        packet=proof.get('source_macro_packet',{})
        _need(proof.get('scope')=='independent_saved_source_owned_macro_cell'and proof.get('errors')==[]
            and positive(proof,'ok','complete','all_original_surviving_native_partitions_preserved',
                'source_candidate_families_and_code_unchanged')
            and positive(proof.get('all_original_physical_ground_returns',{}),'ok')
            and bool(proof.get('actual_native_terminal_paths'))
            and positive(proof.get('independent_exact_source_cut_transform_and_additions',{}),'ok','complete')
            and proof.get('source_sha256')==parent_sha and proof.get('candidate_sha256')==phase.get('candidate_sha256')
            and packet.get('source')==parent and packet.get('source_sha256')==parent_sha
            and all(proof.get(k)is False for k in('routing_admitted','fab_ready','release_authority','current_qualified')),
            'exact_complete_immediate_Source_macro_path_cut_return_and_identity_proofs_required')

    for entry,index in zip(boundaries,indices):
        phase=phases[index]
        parent=phases[index-1]['candidate']if index else receipt.get('scope_source')
        parent_sha=phases[index-1]['candidate_sha256']if index else receipt.get('scope_source_sha256')
        _need(entry.get('phase_index')==index and type(entry['phase_index'])is int
            and entry.get('source')==parent and entry.get('source_sha256')==parent_sha
            and entry.get('candidate')==phase.get('candidate')
            and entry.get('candidate_sha256')==phase.get('candidate_sha256'),
            'exact_ordered_immediate_Source_macro_contact_endpoint_required')
        actual_macro(phase['receiving'],parent,parent_sha,phase)
        contact=entry.get('macro',{})
        _need(positive(contact,'ok','complete','comparison_complete','same_evidence',
                'source_candidate_families_and_code_unchanged')
            and contact.get('errors')==[]and all(contact.get(k)is False for k in('full_kelvin_qualification','release_authority')),
            'independent_immediate_Source_macro_contact_receiving_required')
        actual_macro(contact.get('saved_macro_receiving',{}),parent,parent_sha,phase)
        _need(positive(entry.get('source_evidence_match',{}),'comparison_complete','same_evidence'),
            'strict_raw_contact_link_between_every_actual_saved_macro_required')
        if index!=indices[0]:
            _need(entry.get('strict_prefix_actual_modified_nets')==[]
                and entry.get('strict_prefix_native_copper_transforms')==[],
                'same_saved_inter_macro_link_cannot_borrow_a_material_transform')
    for key,expected in(('independently_received_prefix_phases',phases[:indices[0]]),
            ('independently_received_suffix_phases',phases[indices[-1]+1:])):
        replay=relation.get(key,[])
        _need(type(replay)is list and len(replay)==len(expected)
            and all(p.get('kind')==q.get('kind')and p.get('candidate')==q.get('candidate')
                and p.get('candidate_sha256')==q.get('candidate_sha256')
                and positive(p.get('receiving',{}),'ok','complete')for p,q in zip(replay,expected)),
            'independent_exact_typed_macro_chain_prefix_and_suffix_required')
    _need(positive(relation.get('strict_macro_boundary_to_final',{}),'comparison_complete','same_evidence')
        and all(relation.get(k)is False for k in('full_kelvin_qualification','release_authority')),
        'strict_final_remainder_and_no_new_macro_chain_qualification_required')
    return dict(scope='independently_received_bounded_Source_macro_chain',
        all_copper_parts_pinouts_stack_and_dimensions_unchanged=False,
        source_owned_placement_and_copper_reconstruction_explicit=True,
        preparatory_typed_copper_repairs_explicit=bool(indices[0]),
        independently_received_immediate_Source_macro_count=MAX_COMPLETE_MACROS,
        no_later_macro_authority_applied_to_earlier_boundary=True,
        parts_pinouts_courtyards_and_board_outline_preserved=True,
        all_actual_parent_gates_passed=True,inherited_kelvin_uncertainty_not_newly_qualified=True)


def _received_connector_layer_policy(proof):
    """Validate an explicit search policy without granting plane authority.

    Old receipts did not carry this field; their default behavior cannot be
    relabelled explicit recovery. Live saved receivers, not this reporting
    consumer, derive the menu and prove actual geometry and Source identity.
    """
    import cec_fab_profile as fab
    if 'Source_routing_layer_policy' not in proof:
        return dict(allow_nonplane_power_role=False,
            legacy_default_without_explicit_recovery=True)
    policy=proof['Source_routing_layer_policy']
    _need(type(policy)is dict
        and policy.get('scope')=='Source_profile_nonplane_search_menu_not_reference_authority'
        and type(policy.get('allow_nonplane_power_role'))is bool
        and policy.get('actual_planes_and_disabled_layers_excluded')is True
        and policy.get('current_or_plane_reference_or_barrel_qualified')is False,
        'independent_Source_connector_nonplane_search_policy_required')
    allowed,used=policy.get('allowed_layer_ids'),policy.get('used_layer_ids')
    _need(all(type(rows)is list and rows
            and all(type(face)is int and face in fab.COPPER_LAYER_IDS for face in rows)
            and len(set(rows))==len(rows)
            for rows in(allowed,used))and set(used)<=set(allowed),
        'exact_Source_derived_allowed_and_used_connector_faces_required')
    profile=policy.get('saved_Source_profile')
    _need(profile is None or type(profile)is str and profile in fab.PROFILES,
        'known_or_absent_saved_Source_connector_profile_required')
    if policy['allow_nonplane_power_role']:
        _need(profile is not None,'explicit_connector_recovery_requires_saved_Source_profile')
    if profile is not None:
        roles=dict(zip(fab.COPPER_LAYERS,fab.get_profile(profile)['roles']))
        permitted={face for face,name in fab.COPPER_LAYER_IDS.items()
            if 'SIG'in roles[name]or policy['allow_nonplane_power_role']and roles[name]=='PWR'}
        _need(set(allowed)<=permitted,'Source_connector_recovery_cannot_report_ground_role_or_unauthored_face')
    return dict(policy)


def _received_local_monitor_factory_scope(proof,added,saved):
    """Describe only independently received Source-clamped factory deltas."""
    import math
    keys=('new_factory_group_uuids','extended_factory_group_uuids','factory_group_delta_uuids')
    groups={k:proof.get(k)for k in keys}
    def ids(values):
        return type(values)is list and len(values)<=1 and len(set(values))==len(values)and all(
            type(v)is str and bool(v)for v in values)
    _need(all(ids(v)for v in groups.values())
        and not(set(groups[keys[0]])&set(groups[keys[1]]))
        and set(groups[keys[2]])==set(groups[keys[0]])|set(groups[keys[1]]),
        'exact_new_or_extended_Source_factory_group_delta_required')
    local=proof.get('Source_local_POFV_vias',{});normal=proof.get('new_normal_vias');count=proof.get('new_local_vias')
    _need(type(local)is dict and type(count)is int and 0<=count<=2 and len(local)==count
        and set(local)<=set(added)and type(normal)is int and 0<=normal<=2 and normal+count<=2
        and type(saved.get('added_native_uuids'))is list
        and set(saved['added_native_uuids'])==set(added)|set(groups[keys[0]]),
        'exact_copper_plus_only_new_factory_groups_and_disjoint_normal_local_counts_required')
    for uid,via in local.items():
        geometry=[via.get('diameter_nm'),via.get('drill_nm')];menu=via.get('Source_clamped_menu_nm')
        _need(type(uid)is str and bool(uid)and all(type(v)is int for v in geometry)
            and geometry[0]>geometry[1]>0 and type(menu)is list and 1<=len(menu)<=16
            and all(type(p)in(list,tuple)and len(p)==2 and all(type(v)is int for v in p)
                and p[0]>p[1]>0 for p in menu)
            and tuple(geometry)in{tuple(p)for p in menu}
            and type(via.get('provenance'))is str and bool(via['provenance'])
            and type(via.get('Source_profile'))is str and bool(via['Source_profile']),
            'positive_Source_clamped_process_and_SMD_provenance_per_local_via_required')
    times=proof.get('stage_timings_s',{})
    _need(proof.get('bounded_receiving_stages')==2 and proof.get('each_stage_lease_s')==10.
        and proof.get('composed_budget_s')==20.
        and type(times)is dict and set(times)=={'Source_geometry_field','independent_saved_replay_partitions'}
        and all(type(v)in(int,float)and math.isfinite(v)and 0<=v<=10. for v in times.values()),
        'two_separate_positive_Source_and_saved_replay_ten_second_constituents_required')
    return dict(new_factory_group_uuids=groups[keys[0]],extended_factory_group_uuids=groups[keys[1]],
        Source_qualified_local_via_uuids=sorted(local),new_local_vias=count,new_normal_vias=normal,
        no_barrel_current_or_manufacturing_qualification=True)


def _received_source_sideband_scope(receipt):
    """Describe newly typed sidebands only after the unchanged parent gates.

    This is a reporting consumer of live-bound receipts, not a replacement
    for their canonical Source, physical copper, Ground, field or current
    receivers. The legacy direct-connector branch retains its own checks.
    """
    import math
    kinds={'source_connector_feedthrough','source_connector_native_frontier',
           'source_series_resistor_monitor_tap','source_series_resistor_monitor_local_tap'}
    phases=receipt['phases']
    _need(all(p.get('kind')in kinds for p in phases[:-1]),
          'exact_Source_connector_or_series_monitor_phases_then_print_required')

    def identities(values,count=None):
        return (type(values)is list and (count is None or len(values)==count)
            and all(type(v)is str and v and v==v.strip()and len(v)<=128 for v in values)
            and len(set(values))==len(values))

    def area(value):
        return type(value)in(int,float)and math.isfinite(value)and value>0

    def channel(fresh):
        _need(identities(fresh.get('requested_pad_uuids'),2)
            and fresh.get('Source_numbering_remap_only')is True
            and fresh.get('publisher_numeric_pin_map_claimed')is False
            and fresh.get('current_authority')is False,
            'fresh_Source_connector_channel_identity_without_current_or_publisher_grant_required')
        return frozenset(fresh['requested_pad_uuids'])

    seen_channels=set();seen_taps=set();seen_targets=set();boundaries=[];ground=set();vias=0
    for phase in phases[:-1]:
        kind=phase['kind'];proof=phase['receiving']
        if kind=='source_connector_feedthrough':
            # Reuse the unchanged direct reporting path, not a frontier
            # contact substituted for its mandatory terminal annuli.
            received_repair_scope(dict(receipt,phases=[phase,phases[-1]]))
            pair=channel(proof.get('independently_compiled_Source_scope',{}))
            _need(pair not in seen_channels|seen_taps,'duplicate_or_out_of_order_Source_connector_channel')
            policy=_received_connector_layer_policy(proof)
            seen_channels.add(pair);boundaries.append(dict(kind=kind,connector_pad_uuids=sorted(pair),
                Source_routing_layer_policy=policy))
            continue
        _need(proof.get('errors')==[]and proof.get('whole_shared_stage_still_required')is True
            and all(proof.get(k)is False for k in('ordinary_reclassification','quiet_reclassification',
                'new_current_budget','current_qualified','barrel_qualified','inherited_footprint_qualified',
                'release_authority','routing_admitted')),
            'independent_Source_sideband_receipt_without_reclassification_or_qualification_required')
        added=proof.get('added_native_uuids')
        _need(identities(added)and 1<=len(added)<=32,'exact_bounded_received_sideband_copper_required')
        saved=proof.get('exact_saved_additive_receiving',{})
        local_factory=(_received_local_monitor_factory_scope(proof,added,saved)
            if kind=='source_series_resistor_monitor_local_tap'else None)
        expected_added=set(added)|(set(local_factory['new_factory_group_uuids'])if local_factory else set())
        _need(saved.get('ok')is True and saved.get('complete')is True
            and identities(saved.get('added_native_uuids'))and set(saved['added_native_uuids'])==expected_added
            and saved.get('existing_ground_fill_matches_independent_native_replay')is True,
            'independent_exact_sideband_additions_and_native_Ground_refill_required')
        guard=proof.get('native_route_proposal_guard',{})
        _need(all(type(guard.get(k))is int and guard[k]==v
                for k,v in dict(assessed=1,passed=1,refused=0,unknown=0).items())
            and guard.get('saved_native_or_whole_board_receiving_cached')is False,
            'fresh_sideband_route_guard_not_cached_or_unknown_required')
        partitions=proof.get('whole_native_Source_partitions',{})
        _need(partitions.get('available')is True and partitions.get('preserved')is True,
            'all_retained_native_sideband_Source_partitions_required')
        fresh=proof.get('independently_compiled_Source_scope',{})
        if kind=='source_connector_native_frontier':
            policy=_received_connector_layer_policy(proof)
            pair=channel(fresh);contacts=proof.get('retained_native_frontier_contacts',{})
            _need(_received_connector_layer_policy(contacts)==policy,
                'same_actual_Source_layer_policy_required_for_frontier_and_incoming_tracks')
            _need(proof.get('scope')=='Source_canonical_existing_native_frontier_sideband_feedthrough'
                and type(proof.get('source_components'))is int and type(proof.get('candidate_components'))is int
                and 0<proof['candidate_components']==proof['source_components']-1
                and proof.get('only_requested_existing_Source_islands_joined')is True
                and pair not in seen_channels|seen_taps,
                'one_distinct_received_Source_connector_frontier_join_required')
            _need(contacts.get('complete')is True and type(contacts.get('new_barrels'))is int
                and contacts['new_barrels']==0
                and contacts.get('original_barrels_used_for_physical_access_only')is True
                and contacts.get('every_old_native_partition_and_exact_Source_additive_receiving_required')is True
                and all(contacts.get(k)is False for k in('old_barrel_capacity_credited','new_current_budget',
                    'current_qualified','barrel_qualified','release_authority')),
                'retained_access_only_not_new_or_rated_connector_barrels_required')
            access={}
            records=contacts.get('actual_contacts')
            _need(type(records)is list and records,'positive_actual_Source_frontier_contacts_required')
            for record in records:
                uid=record.get('source_access_uuid');index=record.get('source_connector_island_index')
                source_kind=record.get('source_kind')
                _need(identities([uid],1)and type(index)is int and index in(0,1)
                    and source_kind in('PAD','PCB_TRACK','PCB_VIA')
                    and type(record.get('layer'))is int and record['layer']>=0
                    and area(record.get('positive_native_contact_nm2'))
                    and record.get('actual_drill_subtracted')is(source_kind in('PAD','PCB_VIA'))
                    and (source_kind!='PAD'or uid in pair),
                    'literal_positive_drill_subtracted_frontier_contact_required')
                _need(uid not in access or access[uid]==(index,source_kind),'inconsistent_Source_frontier_identity')
                access[uid]=(index,source_kind)
            _need(len(access)==2 and {v[0]for v in access.values()}=={0,1},
                  'one_actual_retained_access_per_Source_connector_island_required')
            seen_channels.add(pair)
            boundaries.append(dict(kind=kind,connector_pad_uuids=sorted(pair),access_uuids=sorted(access),
                Source_routing_layer_policy=policy))
        else:
            _need('Source_routing_layer_policy'not in proof,
                'connector_recovery_policy_does_not_extend_monitor_tap_authority')
            pair=channel(fresh.get('connector_channel',{}));target=fresh.get('target_pad_uuid')
            backbone=fresh.get('retained_backbone_uuids')
            _need(proof.get('scope')==fresh.get('scope')=='Source_typed_digital_sideband_monitor_tap'
                and identities(fresh.get('connector_pad_uuids'),2)and set(fresh['connector_pad_uuids'])==set(pair)
                and identities([target],1)and target not in pair and target not in seen_targets and pair not in seen_taps
                and identities(backbone)and pair<=set(backbone)and target not in backbone
                and fresh.get('current_authority')is False
                and fresh.get('GPIO_application_mode_or_high_impedance_assumed')is False
                and proof.get('voltage_qualified')is False
                and type(proof.get('source_components'))is int and proof['source_components']==2
                and type(proof.get('candidate_components'))is int and proof['candidate_components']==1
                and proof.get('only_requested_monitor_island_joined')is True
                and type(proof.get('new_normal_vias'))is int and 0<=proof['new_normal_vias']<=2,
                'one_stranded_Source_series_resistor_monitor_not_a_load_or_GPIO_mode_grant_required')
            front=proof.get('actual_front_monitor_contacts');contacts=proof.get('actual_Source_backbone_contacts')
            _need(type(front)is list and bool(front)and all(r.get('uuid')in added and area(r.get('area_nm2'))for r in front)
                and type(contacts)is list and bool(contacts)
                and all(r.get('incoming_uuid')in added and r.get('retained_uuid')in backbone
                    and r.get('retained_class')in('PAD','PCB_TRACK','PCB_VIA')
                    and type(r.get('layer'))is int and r['layer']>=0 and area(r.get('area_nm2'))for r in contacts),
                'positive_actual_front_monitor_and_retained_backbone_material_contacts_required')
            changed=proof.get('generated_Ground_fill_changes_requiring_independent_replay')
            replayed=saved.get('replayed_ground_uuids')
            _need(identities(changed)and identities(replayed)and set(changed)<=set(replayed),
                  'every_changed_Ground_fill_requires_independent_native_replay')
            ground.update(changed);vias+=proof['new_normal_vias'];seen_taps.add(pair);seen_targets.add(target)
            boundaries.append(dict(kind=kind,connector_pad_uuids=sorted(pair),target_pad_uuid=target,
                                   new_normal_vias=proof['new_normal_vias'],
                                   **({'Source_local_factory':local_factory}if local_factory else {})))
    return dict(scope='independently_received_Source_connector_frontier_and_series_monitor_additions',
        all_copper_parts_pinouts_stack_and_dimensions_unchanged=False,
        Source_connector_native_frontier_additions_explicit=any(p['kind']=='source_connector_native_frontier'for p in phases),
        Source_series_resistor_monitor_taps_explicit=bool(seen_taps),
        exact_received_Source_boundaries=boundaries,new_normal_monitor_vias=vias,
        independently_replayed_generated_Ground_fill_uuids=sorted(ground),
        parts_pinouts_and_board_outline_preserved=True,all_actual_parent_gates_passed=True,
        new_current_or_Kelvin_or_barrel_or_voltage_qualification=False,
        GPIO_application_mode_or_high_impedance_assumed=False,
        Source_numbering_remap_not_publisher_pin_numbering=True,
        inherited_kelvin_uncertainty_not_newly_qualified=True)


def _received_connected_pose_scope(receipt):
    """Report typed pose/contact restoration, never transfer pose permission."""
    poses={'connected_footprint_pose','source_ordinary_resistor_reference_pose'}
    allowed=poses|{'ordinary_reflow','ordinary_source_reflow','ordinary_join',
        'source_series_resistor_monitor_tap','source_series_resistor_monitor_local_tap','print_context'}
    phases=receipt['phases'];selected=[p for p in phases if p['kind']in poses]
    _need(len(selected)==1 and all(p['kind']in allowed for p in phases)
        and phases[-1]['kind']=='print_context',
        'one_received_connected_pose_and_only_typed_signal_companions_required')
    phase=selected[0];proof=phase['receiving'];moved=proof.get('moved')
    exact=proof.get('exact_source_plus_additions',{});parts=proof.get('paired_native_partition_preservation',{})
    _need(proof.get('scope')=='explicit_connected_pose_with_exact_additive_contact_restoration'
        and proof.get('errors')==[]and type(moved)is list and 1<=len(moved)<=8
        and len({p.get('uuid')for p in moved})==len(moved)
        and all(type(p.get('uuid'))is str and bool(p['uuid'])for p in moved)
        and all(proof.get(k)is True for k in('all_original_terminal_and_copper_partitions_preserved',
            'source_candidate_and_code_unchanged','independently_rebuilt_source_pose',
            'independent_native_current_field_pair_and_assembly_receiving_required'))
        and all(proof.get(k)is False for k in('source_material_retired','current_qualified',
            'placement_qualified','routing_admitted','release_authority'))
        and exact.get('ok')is True and exact.get('complete')is True
        and exact.get('existing_ground_fill_matches_independent_native_replay')is True
        and parts.get('available')is True and parts.get('preserved')is True
        and 'source_ground_barrel_transport'not in proof,
        'exact_saved_connected_pose_additions_and_all_Source_partitions_without_Ground_motion_required')
    if phase['kind']=='source_ordinary_resistor_reference_pose':
        canonical=proof.get('source_ordinary_resistor_witness',{})
        contacts=proof.get('source_ordinary_resistor_contact_restoration')
        import math
        _need(len(moved)==1 and type(canonical)is dict and bool(canonical)
            and proof.get('source_closed_reference_maps_translated_with_own_passives')is True
            and proof.get('all_source_reference_group_memberships_and_locks_preserved')is True
            and type(proof.get('source_reference_group_uuids'))is list
            and len(proof['source_reference_group_uuids'])==1
            and all(proof.get(k)is True for k in('all_source_tracks_arcs_and_barrels_retained_exactly',
                'source_ordinary_resistor_translation_only','no_source_ground_or_signal_barrel_motion_authorized'))
            and type(contacts)is list and len(contacts)<=16
            and all(type(c.get('uuid'))is str and bool(c['uuid'])
                and c.get('net')in{p.get('net')for p in canonical.get('pins',[])}
                and type(c.get('layer_id'))is int and c['layer_id']>=0
                and type(c.get('length_nm'))in(int,float)and math.isfinite(c['length_nm'])
                and c['length_nm']>0 for c in contacts)
            and sum(c['length_nm']for c in contacts)<=32000000,
            'fresh_canonical_ordinary_resistor_and_exact_closed_Source_reference_map_required')
    else:
        _need('source_reference_group_uuids'not in proof,
            'plain_connected_pose_cannot_inherit_reference_group_authority')
    companions=[]
    for other in phases[:-1]:
        kind=other['kind'];q=other['receiving']
        if kind in poses:continue
        expected={'ordinary_reflow':'bounded_ordinary_source_delta_receiving',
            'ordinary_source_reflow':'bounded_ordinary_source_delta_receiving',
            'ordinary_join':'ordinary_saved_additive_native_join',
            'source_series_resistor_monitor_tap':'Source_typed_digital_sideband_monitor_tap',
            'source_series_resistor_monitor_local_tap':'Source_typed_digital_sideband_monitor_tap'}[kind]
        _need(q.get('scope')==expected and q.get('errors')==[]and q.get('release_authority')is False,
            'independently_received_typed_signal_companion_required')
        if 'monitor'in kind:
            saved=q.get('exact_saved_additive_receiving',{});preserved=q.get('whole_native_Source_partitions',{})
            _need(type(q.get('source_components'))is int and q['source_components']==2
                and type(q.get('candidate_components'))is int and q['candidate_components']==1
                and q.get('only_requested_monitor_island_joined')is True
                and saved.get('ok')is True and saved.get('complete')is True
                and saved.get('existing_ground_fill_matches_independent_native_replay')is True
                and preserved.get('available')is True and preserved.get('preserved')is True
                and all(q.get(k)is False for k in('ordinary_reclassification','quiet_reclassification',
                    'new_current_budget','current_qualified','barrel_qualified','voltage_qualified',
                    'inherited_footprint_qualified','routing_admitted')),
                'exact_Source_monitor_island_join_without_role_or_barrel_waiver_required')
            if kind=='source_series_resistor_monitor_local_tap':
                _received_local_monitor_factory_scope(q,q.get('added_native_uuids',[]),saved)
        companions.append(dict(kind=kind,candidate=other['candidate'],candidate_sha256=other['candidate_sha256']))
    return dict(scope='independently_received_connected_pose_contact_restoration_and_typed_signal_cohort',
        all_copper_parts_pinouts_stack_and_dimensions_unchanged=False,
        selected_footprint_pose_and_exact_Source_contact_restoration_explicit=True,
        closed_ordinary_resistor_reference_map_explicit=phase['kind']=='source_ordinary_resistor_reference_pose',
        pose_moved_footprint_uuids=sorted(p['uuid']for p in moved),typed_signal_companions=companions,
        no_Source_copper_retirement_authority_transferred_from_pose=True,
        no_Source_Ground_barrel_motion_authorized=True,
        parts_pinouts_and_board_outline_preserved=True,all_actual_parent_gates_passed=True,
        new_current_or_Kelvin_or_barrel_or_voltage_qualification=False,
        inherited_kelvin_uncertainty_not_newly_qualified=True)


def received_repair_scope(receipt):
    """Describe only a positively typed, fully received saved transaction."""
    phases=receipt.get('phases')
    _need(type(phases)is list and bool(phases),'explicit_received_repair_phases_required')
    if any(p.get('kind')=='complete_macro'for p in phases):return complete_macro_scope(receipt)
    required={'typed_phases','current','protected_copper_pairs','field','ground_returns',
        'contact_kelvin_preservation','source_intake','candidate_intake','native','progress','parity',
        'craft','live','all_phase_source_families_live','suite_live','code_and_inputs_live'}
    gates=receipt.get('gates',{})
    _need(receipt.get('ok')is True and receipt.get('complete')is True and required<=gates.keys()
        and all(v is True for v in gates.values()),'complete_live_original_parent_repair_gates_required')
    new_sidebands=any(p.get('kind')in('source_connector_native_frontier','source_series_resistor_monitor_tap',
        'source_series_resistor_monitor_local_tap')for p in phases)
    connected_pose=any(p.get('kind')in('connected_footprint_pose','source_ordinary_resistor_reference_pose')for p in phases)
    from root_receive_local_transaction_20261022 import MAX_LOCAL_PHASES
    _need(2<=len(phases)<=(MAX_LOCAL_PHASES if new_sidebands or connected_pose else 4) and phases[-1].get('kind')=='print_context'
        and phases[-1].get('candidate')==receipt.get('candidate')
        and phases[-1].get('candidate_sha256')==receipt.get('candidate_sha256')
        and all(p.get('receiving',{}).get('ok')is True and p['receiving'].get('complete')is True
            for p in phases),'exact_received_repair_and_final_print_boundary_required')
    _need(all(receipt.get(k)is False for k in('release_authority','current_qualified',
        'full_kelvin_qualification','factory_qualified','thermal_qualified')),
        'review_receipt_cannot_claim_full_qualification')
    clipped=receipt.get('reports',{}).get('clipped',{})
    _need(clipped.get('same_evidence')is True and clipped.get('comparison_complete')is True,
        'original_parent_repair_contact_preservation_required')
    if connected_pose:return _received_connected_pose_scope(receipt)
    if new_sidebands:return _received_source_sideband_scope(receipt)
    kind=phases[0]['kind'];proof=phases[0]['receiving']
    if kind=='measurement_auxiliary_input_join':
        import math
        _need([p.get('kind')for p in phases]==[
            'measurement_auxiliary_input_join','print_context'],
            'exact_Source_local_auxiliary_join_then_print_required')
        source=proof.get('Source_plan',{});literal=proof.get('independent_saved_literal_strap',{})
        paired=source.get('paired_pad_uuid');auxiliary=source.get('auxiliary_pad_uuid')
        track=proof.get('added_track_uuid');contacts=proof.get('positive_native_pad_contacts_nm2',{})
        flags=('current_authority','numeric_load_assumed','trunk_capacity_credited',
            'barrel_qualified','kelvin_qualified','release_authority','routing_admitted',
            'retirement_authority','placement_authority','external_quiet_tree_qualified','no_path_proof')
        _need(proof.get('scope')=='Source_typed_local_auxiliary_measurement_join'
            and proof.get('errors')==[]and source.get('complete')is True
            and source.get('scope')==proof['scope']
            and type(paired)is str and bool(paired)and type(auxiliary)is str and bool(auxiliary)
            and paired!=auxiliary and type(track)is str and bool(track)
            and proof.get('source')==receipt.get('baseline')
            and proof.get('source_sha256')==receipt.get('baseline_sha256')
            and proof.get('candidate')==phases[0].get('candidate')
            and proof.get('candidate_sha256')==phases[0].get('candidate_sha256')
            and source.get('source')==proof['source']
            and source.get('source_sha256')==proof['source_sha256']
            and source.get('isolated_auxiliary',{}).get('auxiliary_pad_uuid')==auxiliary
            and source['isolated_auxiliary'].get('native_component_size')==1
            and source['isolated_auxiliary'].get('all_saved_zone_islands_included')is True
            and source.get('existing_external_quiet_tree_must_remain_exact')is True
            and literal.get('track_uuids')==[track]
            and literal.get('boundary_uuids')==[auxiliary]
            and type(contacts)is dict and set(contacts)=={paired,auxiliary}
            and all(type(v)in(int,float)and math.isfinite(v)and v>0 for v in contacts.values())
            and proof.get('existing_external_copper_and_all_fills_literal_exact')is True
            and proof.get('unchanged_external_quiet_tree_debt_not_qualified')is True
            and proof.get('whole_shared_stage_still_required')is True
            and source.get('whole_shared_stage_still_required')is True
            and proof.get('bounded_receiving_stages')==2
            and proof.get('each_stage_lease_s')==10.
            and proof.get('composed_budget_s')==20.
            and set(proof.get('constituent_timings_s',{}))=={
                'fresh_Source_and_native_ownership','saved_additive_refill_and_partitions'}
            and all(type(v)in(int,float)and math.isfinite(v)and 0<=v<=10.
                for v in proof['constituent_timings_s'].values())
            and all(p.get(k)is False for p in(proof,source)for k in flags),
            'independent_manufacturer_local_auxiliary_geometry_without_external_tree_waiver_required')
        additive=proof.get('saved_additive_receiving',{})
        partitions=proof.get('whole_native_Source_partitions',{})
        _need(additive.get('ok')is True and additive.get('complete')is True
            and partitions.get('available')is True and partitions.get('preserved')is True,
            'fresh_local_auxiliary_additive_and_all_original_native_partitions_required')
        _need(clipped.get('comparison')=='qualified_contour_contact_preservation_v1'
            and clipped.get('full_kelvin_qualification')is False,
            'unchanged_strict_contact_receiver_required_for_local_auxiliary_join')
        return dict(scope='independently_received_Source_manufacturer_local_auxiliary_measurement_join',
            all_copper_parts_pinouts_stack_and_dimensions_unchanged=False,
            exactly_one_Source_derived_local_planar_input_strap_explicit=True,
            no_external_quiet_tree_or_source_force_copper_changes=True,
            parts_pinouts_and_board_outline_preserved=True,all_actual_parent_gates_passed=True,
            new_current_or_Kelvin_or_barrel_or_load_qualification=False,
            inherited_kelvin_uncertainty_not_newly_qualified=True)
    if kind=='auxiliary_attachment':
        _need([p.get('kind')for p in phases]==['auxiliary_attachment','print_context'],
            'exact_received_auxiliary_attachment_then_print_required')
        contract=proof.get('contract',{});minimum=contract.get('minimum_conductor_authority',{})
        aggregate=contract.get('aggregate_current_authority',{})
        def positive(value):
            import math
            return type(value)in(int,float)and math.isfinite(value)and value>0
        tracks=proof.get('received_track_uuids',[]);requirements=proof.get('track_requirements',{})
        _need(proof.get('scope')=='explicit_auxiliary_attachment_minimum_conductor_geometry_only'
            and proof.get('errors')==[]and proof.get('identity_stable')is True
            and all(positive(c.get('amps'))and positive(c.get('geometry_margin'))for c in(minimum,aggregate))
            and minimum['amps']<=aggregate['amps']
            and minimum.get('geometry_margin')==aggregate.get('geometry_margin')
            and minimum.get('margin_included')==aggregate.get('margin_included')
            and contract.get('declaration',{}).get('minimum_continuous_amps')==minimum['amps']
            and contract.get('aggregate_budget_reduced')is False
            and proof.get('aggregate_budget_reduced')is False
            and proof.get('original_terminal_partitions_preserved')is True
            and proof.get('attached_named_connection_proved')is True
            and proof.get('source_topology',{}).get('aggregate_native_terminals_connected')is True
            and type(proof.get('contacts',{}).get('physical_tap_count'))is int
            and proof['contacts']['physical_tap_count']==1
            and type(tracks)is list and 1<=len(tracks)<=64 and len(set(tracks))==len(tracks)
            and type(requirements)is dict and set(requirements)==set(tracks)
            and all(positive(v)for v in requirements.values())
            and proof.get('additive',{}).get('ok')is True
            and proof['additive'].get('complete')is True
            and all(proof.get(k)is False for k in('current_total_qualified','barrel_current_qualified',
                'whole_fan_supply_qualified','kelvin_qualified','load_model_qualified',
                'thermal_or_transient_qualified','release_authority')),
            'independent_Source_auxiliary_minimum_geometry_without_aggregate_or_qualification_waiver_required')
        return dict(scope='independently_received_Source_auxiliary_minimum_conductor_attachment',
            all_copper_parts_pinouts_stack_and_dimensions_unchanged=False,
            Source_auxiliary_conductor_additions_explicit=True,aggregate_requirement_reduced=False,
            parts_pinouts_and_board_outline_preserved=True,all_actual_parent_gates_passed=True,
            new_current_or_Kelvin_or_barrel_qualification=False,
            inherited_kelvin_uncertainty_not_newly_qualified=True)
    if kind=='existing_local_ground_entry':
        _need([p.get('kind')for p in phases]==[
            'existing_local_ground_entry','source_divider_ground_span','ordinary_join','print_context'],
            'exact_existing_entry_Source_divider_span_ordinary_join_then_print_required')
        entry=proof;branch=phases[1]['receiving'];joined=phases[2]['receiving']
        _need(entry.get('errors')==[]and entry.get('retired_track_uuids')==[]
            and entry.get('modified_nets')==['GND']and entry.get('new_holes')==1
            and entry.get('saved_return_witness_mm')==0
            and entry.get('every_source_native_partition_identical')is True
            and entry.get('original_parts_poses_barrels_rules_and_power_copper_unchanged')is True
            and entry.get('proposal',{}).get('use_existing_local_pad_rule')is True
            and all(entry.get(k)is False for k in('fab_ready','current_qualified','release_authority')),
            'independent_saved_existing_rule_in_pad_Ground_entry_required')
        owner=branch.get('source_owner',{})
        _need(branch.get('scope')=='fresh_source_reference_divider_ground_span'
            and branch.get('errors')==[]
            and branch.get('source_candidate_hierarchy_and_code_unchanged')is True
            and branch.get('no_ground_current_budget_or_public_small_span_width_waiver')is True
            and branch.get('no_new_holes_or_part_pose_group_rule_or_power_copper_changes')is True
            and branch.get('every_source_native_partition_preserved')is True
            and branch.get('same_source_entry_contacts_to_each_saved_ground_reference_preserved')is True
            and branch.get('contact_kernels',{}).get('all_old_native_contact_kernels_fully_covered')is True
            and branch.get('native_field_delta',{}).get('no_new_blockers')is True
            and owner.get('kind')=='fresh_source_closed_reference_divider_ground_span'
            and owner.get('ground_pad_uuid')==entry.get('proposal',{}).get('pad_uuid')
            and owner.get('inferred_ground_current_budget')is False
            and all(branch.get(k)is False for k in('current_qualified','routing_admitted','release_authority')),
            'independent_full_class_Source_divider_span_contact_and_return_preservation_required')
        for parent,name in((entry,'independent_additive_receiving'),(entry,'all_source_known_returns'),
                (branch,'independent_additive_receiving'),(branch,'all_source_known_returns')):
            detail=parent.get(name,{})
            _need(detail.get('ok')is True and detail.get('complete')is True,
                'exact_saved_Ground_entry_span_and_all_known_returns_required')
            if name=='independent_additive_receiving':
                _need(all(detail.get(k)is True for k in(
                    'existing_ground_fill_matches_independent_native_replay',
                    'original_power_and_terminal_geometry_exact',
                    'original_power_copper_and_supply_anchors_exact')),
                    'exact_Ground_fill_and_all_original_power_and_terminal_geometry_required')
        _need(joined.get('scope')=='ordinary_saved_additive_native_join'
            and joined.get('errors')==[]and joined.get('source_ordinary_scope_independently_recompiled')is True
            and type(joined.get('source_components'))is int and type(joined.get('candidate_components'))is int
            and 0<joined['candidate_components']<joined['source_components']
            and bool(joined.get('added_native_uuids'))
            and all(joined.get(k)is False for k in('routing_admitted','current_qualified','release_authority')),
            'independent_ordinary_signal_reduction_after_received_Ground_preparation_required')
        return dict(scope='independently_received_Source_divider_Ground_preparation_and_ordinary_join',
            all_copper_parts_pinouts_stack_and_dimensions_unchanged=False,
            Source_owned_full_class_Ground_span_and_existing_rule_entry_explicit=True,
            Source_ordinary_signal_additions_explicit=True,
            no_public_Ground_width_or_current_rule_relaxed=True,
            parts_pinouts_and_board_outline_preserved=True,all_actual_parent_gates_passed=True,
            inherited_kelvin_uncertainty_not_newly_qualified=True,new_current_or_Kelvin_qualification=False)
    if kind=='rc_return_pivot':
        _need(len(phases)==2 and proof.get('scope')=='isolated_rc_ground_pivot_receiving'
            and proof.get('errors')==[]and proof.get('new_native_faults')==[]
            and proof.get('new_native_field_blockers')==[]
            and proof.get('original_native_conductor_and_terminal_partitions_preserved')is True
            and proof.get('source_candidate_and_code_unchanged')is True
            and proof.get('physical_placement',{}).get('ok')is True
            and type(proof.get('source_opens'))is int and type(proof.get('opens'))is int
            and 0<=proof['opens']<proof['source_opens']
            and 1<=len(proof.get('pivots',[]))<=4
            and all(proof.get(k)is False for k in('release_authority','power_authority',
                'routing_admitted','placement_authority_transferred')),
            'independent_saved_RC_fixed_signal_land_and_immediate_ground_reduction_required')
        exact=proof.get('independent_pose_and_additive_replay',{})
        _need(exact.get('ok')is True and exact.get('complete')is True
            and exact.get('original_power_and_terminal_geometry_exact')is True
            and exact.get('original_power_copper_and_supply_anchors_exact')is True
            and exact.get('existing_ground_fill_matches_independent_native_replay')is True
            and bool(exact.get('added_native_uuids')),
            'independent_exact_RC_pose_and_saved_additive_replay_required')
        return dict(scope='independently_received_Source_isolated_RC_fixed_anchor_ground_pivot',
            all_copper_parts_pinouts_stack_and_dimensions_unchanged=False,
            Source_owned_RC_placement_and_local_ground_additions_explicit=True,
            all_original_signal_land_geometry_preserved=True,
            parts_pinouts_and_board_outline_preserved=True,all_actual_parent_gates_passed=True,
            new_current_or_Kelvin_qualification=False,
            inherited_kelvin_uncertainty_not_newly_qualified=True)
    if kind=='source_connector_feedthrough':
        _need(all(p.get('kind')=='source_connector_feedthrough'for p in phases[:-1]),
            'exact_Source_connector_feedthroughs_then_print_required')
        policies=[]
        for phase in phases[:-1]:
            joined=phase['receiving'];fresh=joined.get('independently_compiled_Source_scope',{})
            policies.append(_received_connector_layer_policy(joined))
            _need(joined.get('scope')=='Source_canonical_existing_plated_sideband_feedthrough'
                and joined.get('errors')==[]and joined.get('whole_shared_stage_still_required')is True
                and type(joined.get('source_components'))is int
                and type(joined.get('candidate_components'))is int
                and 0<joined['candidate_components']==joined['source_components']-1
                and joined.get('only_requested_existing_Source_islands_joined')is True
                and bool(joined.get('added_native_uuids'))
                and len(joined.get('actual_flashed_annular_contacts',[]))>=2
                and fresh.get('Source_numbering_remap_only')is True
                and fresh.get('publisher_numeric_pin_map_claimed')is False
                and all(joined.get(k)is False for k in('ordinary_reclassification',
                    'quiet_reclassification','new_current_budget','current_qualified',
                    'barrel_qualified','inherited_footprint_qualified','release_authority','routing_admitted')),
                'independent_Source_existing_connector_channel_reduction_required')
            guard=joined.get('native_route_proposal_guard',{})
            _need(all(type(guard.get(k))is int and guard[k]==v
                    for k,v in dict(assessed=1,passed=1,refused=0,unknown=0).items())
                and guard.get('saved_native_or_whole_board_receiving_cached')is False,
                'independent_saved_connector_geometry_and_literal_Source_required')
            detail=joined.get('exact_saved_additive_receiving',{})
            _need(detail.get('ok')is True and detail.get('complete')is True,
                'independent_saved_connector_geometry_and_literal_Source_required')
            partition=joined.get('whole_native_Source_partitions',{})
            _need(partition.get('available')is True and partition.get('preserved')is True,
                'all_retained_Source_connector_partitions_required')
        return dict(scope='independently_received_Source_canonical_existing_connector_feedthrough',
            all_copper_parts_pinouts_stack_and_dimensions_unchanged=False,
            Source_owned_existing_plated_sideband_additions_explicit=True,
            Source_connector_routing_layer_policies=policies,
            parts_pinouts_and_board_outline_preserved=True,all_actual_parent_gates_passed=True,
            new_barrel_current_or_footprint_qualification=False,
            Source_numbering_remap_not_publisher_pin_numbering=True,
            inherited_kelvin_uncertainty_not_newly_qualified=True)
    if kind in('can_endpoint_join','isolated_measurement_join'):
        _need(all(p.get('kind')in{'can_endpoint_join','isolated_measurement_join'}for p in phases[:-1]),
            'exact_Source_typed_endpoint_joins_then_print_required')
        measurements=[];can=[]
        for phase in phases[:-1]:
            joined=phase['receiving']
            _need(type(joined.get('source_components'))is int
                and type(joined.get('candidate_components'))is int,
                'literal_native_endpoint_component_counts_required')
            if phase['kind']=='isolated_measurement_join':
                fresh=joined.get('independently_compiled_source_scope',{})
                _need(joined.get('scope')=='source_typed_isolated_measurement_saved_native_join'
                    and joined.get('errors')==[]and joined.get('exact_source_pickup_aperture_preserved')is True
                    and joined.get('whole_shared_stage_still_required')is True
                    and fresh.get('scope')=='source_typed_stationary_isolated_measurement_join'
                    and fresh.get('complete')is True
                    and 0<joined['candidate_components']<joined['source_components']
                    and bool(joined.get('added_native_uuids'))
                    and all(joined.get(k)is False for k in('current_authority','kelvin_qualified',
                        'retirement_authority','placement_authority','release_authority','routing_admitted')),
                    'independent_Source_isolated_measurement_reduction_required')
                measurements.append(joined);continue
            _need(joined.get('scope')in{'Source_canonical_CAN_surface_endpoint_join',
                    'Source_canonical_CAN_plated_connector_join'}
                and joined.get('errors')==[]and joined.get('Source_CAN_scope_independently_recompiled')is True
                and joined.get('source_components')==2 and joined.get('candidate_components')==1
                and bool(joined.get('added_native_uuids'))
                and all(joined.get(k)is False for k in('ordinary_reclassification',
                    'pair_performance_qualified','current_qualified','release_authority','routing_admitted')),
                'independent_Source_CAN_endpoint_reduction_required')
            can.append(joined)
        direct=any(p['scope']=='Source_canonical_CAN_plated_connector_join'for p in can)
        return dict(scope=('independently_received_Source_typed_endpoint_joins'if measurements
                else'independently_received_Source_CAN_endpoint_join'),
            all_copper_parts_pinouts_stack_and_dimensions_unchanged=False,
            Source_owned_surface_CAN_additions_explicit=bool(can)and not direct,
            Source_owned_CAN_additions_explicit=bool(can),Source_contained_barrels_explicit=direct,
            Source_owned_isolated_measurement_additions_explicit=bool(measurements),
            new_current_or_Kelvin_qualification=False,
            parts_pinouts_and_board_outline_preserved=True,
            all_actual_parent_gates_passed=True,new_pair_performance_qualification=False,
            inherited_kelvin_uncertainty_not_newly_qualified=True)
    if kind=='detached_passive_translation':
        kinds=[p['kind']for p in phases]
        _need(kinds in([
            'detached_passive_translation','ordinary_join','print_context'],[
            'detached_passive_translation','ordinary_join','reference_fields','print_context'],[
            'detached_passive_translation','ordinary_join','reference_map','print_context']),
            'exact_detached_pose_ordinary_join_annotation_print_sequence_required')
        _need(proof.get('errors')==[]and proof.get('exact_literal_root_at_only')is True
            and proof.get('all_copper_pads_fields_rules_and_parts_unchanged')is True
            and proof.get('release_authority')is False,
            'independent_exact_detached_passive_pose_required')
        joined=phases[1]['receiving']
        _need(joined.get('scope')=='ordinary_saved_additive_native_join'and joined.get('errors')==[]
            and joined.get('source_ordinary_scope_independently_recompiled')is True
            and type(joined.get('source_components'))is int and type(joined.get('candidate_components'))is int
            and 0<joined['candidate_components']<joined['source_components']
            and bool(joined.get('added_native_uuids'))
            and all(joined.get(k)is False for k in('routing_admitted','current_qualified','release_authority')),
            'independent_positive_ordinary_native_component_reduction_required')
        return dict(scope='independently_received_detached_canonical_pose_and_ordinary_join',
            all_copper_parts_pinouts_stack_and_dimensions_unchanged=False,
            source_owned_detached_placement_and_additive_join_explicit=True,
            parts_pinouts_and_board_outline_preserved=True,all_actual_parent_gates_passed=True,
            inherited_kelvin_uncertainty_not_newly_qualified=True)
    if kind=='rated_branch':
        _need(all(p.get('kind')in{'reference_fields','reference_map','root_reference_seat'}
            for p in phases[1:-1]),'exact_rated_repair_then_annotation_and_print_required')
        source=proof.get('source_proposal',{})
        _need(proof.get('scope')=='rated_branch_and_additive_scalar_receiving'
            and proof.get('errors')==[]and source.get('repair_undersized_source')is True
            and bool(source.get('exact_source_current_fault_keys'))
            and source.get('full_load_width_required')is True and source.get('inferred_branch_load')is False
            and proof.get('source_distributed_load_ownership_unchanged')is True
            and proof.get('all_surviving_native_partitions_preserved')is True
            and proof.get('all_unowned_current_copper_poses_and_power_fills_exact')is True
            and proof.get('new_barrel_ampacity_credited')is False,
            'independent_complete_full_load_source_fault_repair_required')
        for name in('exact_source_cut_additions_ground_and_rule_replay','strict_source_current_fault_repair'):
            detail=proof.get(name,{})
            _need(detail.get('ok')is True and detail.get('complete')is True,
                'independent_exact_current_repair_subproof_required')
        detail=proof['strict_source_current_fault_repair']
        _need(type(detail.get('before_fault_objects'))is int and type(detail.get('after_fault_objects'))is int
            and 0<=detail['after_fault_objects']<detail['before_fault_objects']
            and detail.get('new_faults')==detail.get('worsened_faults')==[],
            'strict_actual_current_fault_object_reduction_required')
        subtraction=proof.get('literal_source_subtraction',{})
        _need(subtraction.get('exact_opaque_source_subtraction')is True
            and subtraction.get('independent_full_native_inventory_equal')is True,
            'opaque_source_and_independent_native_cut_equality_required')
        return dict(scope='independently_received_full_source_current_fault_reconstruction',
            all_copper_parts_pinouts_stack_and_dimensions_unchanged=False,
            source_owned_current_reconstruction_explicit=True,
            parts_pinouts_courtyards_and_board_outline_preserved=True,
            all_actual_parent_gates_passed=True,new_through_barrel_ampacity_credited=False,
            inherited_kelvin_uncertainty_not_newly_qualified=True)
    if kind=='root_caption_seat':
        _need(len(phases)==2 and proof.get('exact_reviewed_caption_translation_and_readable_floor_only')is True
            and proof.get('whole_saved_second_native_roundtrip_stable')is True,
            'exact_reviewed_root_caption_then_print_required')
        relation=receipt.get('reports',{}).get('contact_caption_query_identity',{})
        _need(all(relation.get(k)is True for k in('ok','complete','same_material','comparison_complete'))
            and relation.get('mutation_authority')is False and relation.get('full_kelvin_qualification')is False,
            'whole_received_caption_query_identity_required')
        return dict(scope='independently_received_reviewed_root_caption_and_print',
            all_copper_parts_pinouts_stack_and_dimensions_unchanged=True,
            all_actual_parent_gates_passed=True,inherited_kelvin_uncertainty_not_newly_qualified=True)
    raise ValueError('unknown_received_repair_scope_cannot_be_described_as_annotation')
