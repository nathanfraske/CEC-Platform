"""Independently receive a finite chain of typed local source-cut repairs.

This is not arbitrary rip-up authority. Each step is retyped from its actual
saved parent by its narrow receiver; a later step cannot retire new material
from an earlier one. The whole transaction is also replayed from the original
source minus exactly those proved cuts. Final native DRC, current, field,
pair, contact and measured-progress gates remain mandatory.
"""
import math
import copy
import hashlib
import json
import os
from collections import OrderedDict
from pathlib import Path
import tempfile
import time

import pcbnew
import cec_additive_route_receiving as additive
import cec_copper_echo as sexpr
import cec_field_coupling as field
import cec_force_current as force
from cec_native_items import discard_items


# Process-local only, positive complete receipts only. No worker JSON, disk
# cache, failed search, partial result, or expired proof becomes admission.
# Every lookup rehashes all saved source/phase families and the local engine.
_RECEIVED = OrderedDict()
_MAX_RECEIVED = 4


def _cache_key(paths, families, epoch, board_hint, rows, per_phase_leases=False):
    import cec_ground_strap_rebuild as ground
    import cec_rated_branch_repair as rated
    import cec_rated_barrel_reseat as rated_barrel
    import cec_fr
    import cec_support_pivot_receiving as pivot
    import cec_ordinary_route_receiving as ordinary
    import cec_shunt_force_landing as force_seat
    import cec_shunt_endcap_clearance as force_cap
    import cec_redundant_bypass_ground as bypass_ground
    import cec_bypass_return_reseat as bypass_return
    import cec_ordinary_barrel_reseat as ordinary_barrel
    import cec_ground_reference_reflow as reference_reflow
    import cec_local_branch_access as stationary
    import cec_ground_plane_echo as ground_echo
    import cec_manufacturer_land_pattern as land_pattern
    import cec_full_current_planar_reflow as full_current
    import cec_pair_axis_miter as pair_axis
    import cec_pair_fixed_port_shortening as pair_fixed
    import cec_pair_source_reference as pair_reference
    import cec_sensitive_redundant_span as sensitive_span
    import cec_source_literal_retirement as literal_cut
    import cec_source_literal_group_retirement as literal_groups
    import cec_source_obsolete_supply_barrels as obsolete_barrels
    import cec_surface_supply_path_graph as surface_paths
    import cec_native_partition_pair as native_partitions
    functions=(additive.receive,ground.receive,rated.receive,rated.plan,rated._receive_steps,
        rated_barrel.receive,rated_barrel.plan,rated_barrel.reconstruction_options,
        rated_barrel._fault_repair_diameter,rated_barrel.context.receive,pivot.receive,ordinary.receive,
        ordinary.eligible_nets,ordinary._redundant_single_face_vias,ordinary._exclusive_retired_vias,
        ordinary._partition,ordinary._boundaries,
        force_seat.receive,force_seat.plan,force_cap.receive,force_cap.plan,
        bypass_ground.receive,bypass_ground.plan,
        bypass_return.receive,bypass_return.plan,
        ordinary_barrel.receive,ordinary_barrel.plan,ordinary_barrel.source_leg_budget_mm,
        reference_reflow.receive,reference_reflow.plan,
        stationary.receive,stationary.receive_measurement_reflow,stationary.leaf.plan,stationary.leaf.path_clear,
        ground_echo.receive,ground_echo.plan,land_pattern.receive,land_pattern.plan,land_pattern.materialize,
        bypass_ground.constraints._device_bypass_assignment,bypass_ground.roles.footprint_contract,
        rated.topology.distributed_supply_contracts,ground.roles.footprint_contract,
        full_current.plan,full_current.receive,full_current._model,
        pair_axis.receive,pair_axis.discover,pair_axis.frame,pair_axis.replacements,pair_axis._reference,
        pair_fixed.receive_literal_phase,pair_fixed.owner.receive_literal_phase,pair_fixed.kernel_schema,
        pair_fixed.owner._fixed_port_kernels,pair_fixed.owner._visible_kernel_shortening,
        pair_fixed.owner._literal_native_contact_polygon_identity,pair_fixed.owner.reference_deficit,
        pair_fixed.owner.metric_progress,pair_fixed.owner.continuous_from_board,pair_fixed.owner.compare_continuous,
        pair_fixed.owner.new_bend_sites,pair_reference.reference_deficit,pair_reference._counterfactual_ground,
        pair_reference.lengths.measure,pair_reference.lengths.nonincreasing,
        sensitive_span.plan,sensitive_span.receive,sensitive_span._terminals,sensitive_span._trim,sensitive_span.trim_schema,
        sensitive_span.sensitive.eligible_nets,
        full_current.topology.board_current_domains,full_current.topology.route_width_contracts,
        cec_fr._project_netclass_resolver,literal_cut.subtract,literal_cut.write_native_projection,
        literal_groups.subtract,literal_groups.write_native_projection,
        obsolete_barrels.plan,surface_paths.prove,
        native_partitions.compare,native_partitions._inventory,native_partitions._positive_overlap,
        force._code_identity,pcbnew.LoadBoard)
    if any(hasattr(fn,'mock_calls') for fn in functions):return None
    payload=dict(paths=list(map(str,paths)),families=families,code=epoch,
        per_phase_leases=per_phase_leases,
        board_hint=board_hint,phases=[dict(r,candidate=str(r['candidate'])) for r in rows],
        context={k:v for k,v in os.environ.items() if k.startswith('CEC_')},
        manufacturer_library_identity=land_pattern.library_identity() if any(
            r['kind']=='manufacturer_land_pattern' for r in rows) else {},
        live_functions=list(map(id,functions)))
    return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _phases(phases, candidate):
    if type(phases) not in (list, tuple) or not 1 <= len(phases) <= 4:
        raise ValueError('finite_nonempty_typed_cut_chain_required')
    resolved = []
    for index,row in enumerate(phases):
        if type(row) is not dict:
            raise ValueError('typed_cut_phase_object_required')
        kind = row.get('kind')
        expected = {'manufacturer_land_pattern': {'kind','candidate','footprint_uuids'},
                    'ground_strap': {'kind', 'candidate', 'pad_uuid'},
                    'redundant_bypass_ground': {'kind','candidate','pad_uuid','track_uuid'},
                    'ground_plane_echo': {'kind','candidate','track_uuid'},
                    'bypass_return_reseat': {'kind','candidate','pad_uuid','track_uuid'},
                    'ordinary_barrel_reseat': {'kind','candidate','via_uuid'},
                    'ground_reference_reflow': {'kind','candidate','pad_uuid','allow_locked_track_uuids'},
                    'stationary_cell': {'kind','candidate','pad_uuids'},
                    'measurement_leaf_reflow': {'kind','candidate','pad_uuid'},
                    'rated_branch': {'kind', 'candidate', 'retired_track_uuids'},
                    'rated_barrel_reseat': {'kind','candidate','retired_track_uuids','retired_via_uuids'},
                    'full_current_planar_reflow': {'kind', 'candidate', 'retired_track_uuids'},
                    'paired_axis_miter': {'kind','candidate','pair_name','retired_track_uuids','retreat_nm'},
                    'paired_fixed_port_shortening': {'kind','candidate','pair_name','kernel_track_uuids'},
                    'sensitive_redundant_span': {'kind','candidate','retired_track_uuids'},
                    'support_pivot': {'kind', 'candidate'},
                    'force_landing': {'kind','candidate','pad_uuid','zone_uuid','track_uuids'},
                    'force_keeper': {'kind','candidate','pad_uuid','zone_uuid','track_uuids'},
                    'force_endcap': {'kind','candidate','pad_uuid','track_uuid'},
                    'ordinary': {'kind','candidate','retired_track_uuids','allow_locked_track_uuids'},
                    'ordinary_redundant_cut': {'kind','candidate','retired_track_uuids','allow_locked_track_uuids',
                        'redundant_single_face_via_uuids','allow_locked_via_uuids'},
                    'ordinary_exclusive_via_path': {'kind','candidate','retired_track_uuids',
                        'allow_locked_track_uuids','retired_via_uuids','allow_locked_via_uuids'},
                    'additive': {'kind', 'candidate'}}.get(kind)
        if (kind=='ground_strap' and expected<=set(row)
                and set(row)<=expected|{'allow_locked_track_uuids','allow_locked_via_uuid','land_role'}):
            if row.get('land_role','logical') not in ('logical','selected_bypass'):
                raise ValueError('explicit_ground_leaf_ownership_mode_required')
            import cec_ordinary_route_receiving as ordinary
            ordinary._ids(row.get('allow_locked_track_uuids',()),'logical_ground_locked_tracks',8)
            ordinary._ids([] if row.get('allow_locked_via_uuid') is None else [row['allow_locked_via_uuid']],
                'logical_ground_locked_root',1)
        elif kind=='rated_barrel_reseat' and expected<=set(row):
            import cec_rated_barrel_reseat as rated_barrel
            import cec_ordinary_route_receiving as ordinary
            rated_barrel.reconstruction_options({k:v for k,v in row.items() if k not in expected})
            tracks=ordinary._ids(row['retired_track_uuids'],'rated_barrel_chain_tracks',32)
            vias=ordinary._ids(row['retired_via_uuids'],'rated_barrel_chain_barrels',2)
            if not tracks or not vias or tracks&vias:
                raise ValueError('exact_nonempty_rated_barrel_chain_scope_required')
        elif (kind=='rated_branch' and expected<=set(row)
                and set(row)<=expected|{'allow_rated_layer_bridges','max_source_track_mm',
                    'allow_qualified_local_vias','max_replacement_width_mm','max_retired_tracks',
                    'max_source_width_mm','allow_rated_source_inner_layers','repair_undersized_source',
                    'use_source_declared_consumer_island','repair_aggregate_current_domain',
                    'retire_obsolete_terminal_vias'}):
            import cec_rated_branch_repair as rated
            rated.reconstruction_options({k:v for k,v in row.items()if k not in expected})
            if ('allow_rated_layer_bridges' in row and type(row['allow_rated_layer_bridges']) is not bool):
                raise ValueError('explicit_rated_layer_bridge_mode_required')
            if ('allow_rated_source_inner_layers' in row and (type(row['allow_rated_source_inner_layers']) is not bool
                    or row['allow_rated_source_inner_layers'] and row.get('allow_rated_layer_bridges') is not True)):
                raise ValueError('inner_source_requires_explicit_full_load_layer_bridge')
            if ('repair_undersized_source' in row and (type(row['repair_undersized_source']) is not bool
                    or row['repair_undersized_source'] and row.get('allow_rated_source_inner_layers') is not True)):
                raise ValueError('undersized_source_repair_requires_explicit_inner_scope')
            if ('repair_aggregate_current_domain' in row and
                    (type(row['repair_aggregate_current_domain']) is not bool
                     or row['repair_aggregate_current_domain'] and row.get('repair_undersized_source') is not True)):
                raise ValueError('aggregate_domain_repair_requires_explicit_undersized_inner_scope')
            if ('use_source_declared_consumer_island' in row and
                    (type(row['use_source_declared_consumer_island']) is not bool or
                     row['use_source_declared_consumer_island'] and row.get('repair_undersized_source',False))):
                raise ValueError('distinct_explicit_source_consumer_reconstruction_scope_required')
            if 'max_source_track_mm' in row:
                import cec_rated_branch_repair as rated
                rated.source_span_mm(row['max_source_track_mm'],
                    allow_undersized_reconstruction=row.get('repair_undersized_source',False))
            if 'max_replacement_width_mm' in row:
                import cec_rated_branch_repair as rated
                rated.replacement_width_mm(row['max_replacement_width_mm'],
                    allow_rated_layer_bridges=row.get('allow_rated_layer_bridges',False))
            if 'max_retired_tracks' in row:
                import cec_rated_branch_repair as rated
                rated.retirement_count(row['max_retired_tracks'])
            if 'max_source_width_mm' in row:
                import cec_rated_branch_repair as rated
                rated.source_width_mm(row['max_source_width_mm'])
            if ('allow_qualified_local_vias' in row and (type(row['allow_qualified_local_vias']) is not bool
                    or row['allow_qualified_local_vias'] and row.get('allow_rated_layer_bridges') is not True)):
                raise ValueError('qualified_local_vias_require_explicit_rated_bridge_mode')
        elif (kind=='sensitive_redundant_span' and expected<=set(row)
                and set(row)<=expected|{'allow_locked_source','source_contained_trim'}):
            import cec_ordinary_route_receiving as ordinary
            import cec_sensitive_redundant_span as sensitive_span
            sensitive_span.trim_schema(row.get('source_contained_trim'))
            if (not ordinary._ids(row['retired_track_uuids'],'sensitive_redundant_tracks',16)
                    or 'allow_locked_source' in row and type(row['allow_locked_source']) is not bool):
                raise ValueError('bounded_explicit_sensitive_redundant_span_required')
        elif (kind=='paired_fixed_port_shortening' and expected<=set(row)
                and set(row)<=expected|{'allow_locked_source','reference_mode'}):
            import cec_pair_fixed_port_shortening as pair_fixed
            pair_fixed.kernel_schema(row['kernel_track_uuids'])
            if (type(row['pair_name']) is not str or not row['pair_name']
                    or 'allow_locked_source' in row and type(row['allow_locked_source']) is not bool
                    or type(row.get('reference_mode','strict_source_deficit')) is not str
                    or row.get('reference_mode','strict_source_deficit') not in ('strict_source_deficit','native_source_reference_context')):
                raise ValueError('bounded_explicit_fixed_port_pair_phase_required')
        elif (kind=='paired_axis_miter' and expected<=set(row)
                and set(row)<=expected|{'allow_locked_source','allow_existing_non_signal_face'}):
            import cec_ordinary_route_receiving as ordinary
            if (len(ordinary._ids(row['retired_track_uuids'],'balanced_axis_tracks',5))!=5
                    or type(row['pair_name']) is not str or not row['pair_name']
                    or type(row['retreat_nm']) is not int or not 20000<=row['retreat_nm']<=200000
                    or any(type(row[k]) is not bool for k in ('allow_locked_source','allow_existing_non_signal_face') if k in row)):
                raise ValueError('bounded_explicit_balanced_axis_draft_phase_required')
        elif (kind=='full_current_planar_reflow' and expected<=set(row)
                and set(row)<=expected|{'max_source_track_mm','max_source_cut_mm'}):
            import cec_full_current_planar_reflow as full_current
            full_current.source_work_bounds(row.get('max_source_track_mm',8.),row.get('max_source_cut_mm',32.))
        elif kind=='support_pivot' and set(row)==expected|{'allow_support_field_reflow'}:
            if type(row['allow_support_field_reflow']) is not bool:
                raise ValueError('explicit_bounded_support_field_reflow_required')
        elif (kind=='bypass_return_reseat' and expected<=set(row)
                and set(row)<=expected|{'allow_owned_locked','allow_qualified_local_vias'}):
            if any(type(row[k]) is not bool for k in
                    ('allow_owned_locked','allow_qualified_local_vias') if k in row):
                raise ValueError('explicit_bypass_return_reconstruction_policy_required')
        elif (kind=='ordinary_barrel_reseat' and expected<=set(row)
                and set(row)<=expected|{'allow_owned_locked','max_additional_path_mm','max_source_leg_mm'}):
            if 'allow_owned_locked' in row and type(row['allow_owned_locked']) is not bool:
                raise ValueError('explicit_source_barrel_reconstruction_policy_required')
            if 'max_additional_path_mm' in row and (type(row['max_additional_path_mm']) not in (int,float)
                    or not math.isfinite(row['max_additional_path_mm'])
                    or not 0<=row['max_additional_path_mm']<=16.):
                raise ValueError('finite_source_barrel_additional_path_budget_required')
            if 'max_source_leg_mm' in row:
                import cec_ordinary_barrel_reseat as ordinary_barrel
                ordinary_barrel.source_leg_budget_mm(row['max_source_leg_mm'])
        elif (kind=='ordinary_redundant_cut' and expected<=set(row)
                and set(row)<=expected|{'retired_via_uuids'}):
            pass
        elif expected is None or set(row) != expected:
            raise ValueError('unsupported_or_ambiguous_typed_cut_phase')
        if type(row['candidate']) is not str or not row['candidate']:
            raise ValueError('saved_cut_phase_path_required')
        if kind=='manufacturer_land_pattern':
            import cec_ordinary_route_receiving as ordinary
            if index!=0 or not ordinary._ids(row['footprint_uuids'],'manufacturer_pattern_scope',4):
                raise ValueError('bounded_manufacturer_pattern_must_be_first_phase')
        if kind == 'ground_strap' and (type(row['pad_uuid']) is not str or not row['pad_uuid']):
            raise ValueError('positive_source_ground_land_identity_required')
        if kind=='ordinary_redundant_cut':
            import cec_ordinary_route_receiving as ordinary
            tracks=ordinary._ids(row['retired_track_uuids'],'redundant_chain_tracks',32)
            locked=ordinary._ids(row['allow_locked_track_uuids'],'redundant_chain_track_locks',32)
            vias=ordinary._ids(row['redundant_single_face_via_uuids'],'redundant_chain_one_face_barrels',4)
            exclusive=ordinary._ids(row.get('retired_via_uuids',()),'redundant_chain_exclusive_barrels',4)
            via_locked=ordinary._ids(row['allow_locked_via_uuids'],'redundant_chain_barrel_locks',4)
            if (not tracks|vias|exclusive or tracks&(vias|exclusive) or vias&exclusive
                    or len(vias|exclusive)>4 or not locked<=tracks or not via_locked<=vias|exclusive):
                raise ValueError('nonempty_exact_redundant_chain_scope_and_lock_subsets_required')
        if kind=='ordinary_barrel_reseat' and (type(row['via_uuid']) is not str or not row['via_uuid']):
            raise ValueError('positive_source_ordinary_barrel_identity_required')
        if kind=='ground_plane_echo' and (type(row['track_uuid']) is not str or not row['track_uuid']):
            raise ValueError('exact_source_inner_ground_stitch_required')
        if kind=='stationary_cell' and (type(row['pad_uuids']) is not list
                or not 1<=len(row['pad_uuids'])<=4
                or any(type(u) is not str or not u for u in row['pad_uuids'])
                or len(set(row['pad_uuids']))!=len(row['pad_uuids'])):
            raise ValueError('exact_bounded_stationary_source_leaf_cohort_required')
        if kind=='measurement_leaf_reflow' and (type(row['pad_uuid']) is not str or not row['pad_uuid']):
            raise ValueError('positive_stationary_measurement_leaf_identity_required')
        if kind in ('redundant_bypass_ground','bypass_return_reseat','force_endcap') and any(
                type(row[k]) is not str or not row[k] for k in ('pad_uuid','track_uuid')):
            raise ValueError('exact_source_bypass_land_and_departure_required')
        if kind == 'ground_reference_reflow':
            import cec_ordinary_route_receiving as ordinary
            if type(row['pad_uuid']) is not str or not row['pad_uuid']:
                raise ValueError('exact_source_reference_land_required')
            ordinary._ids(row['allow_locked_track_uuids'], 'reference_reflow_locked_scope', 8)
        if kind in ('force_landing','force_keeper') and (any(type(row[k]) is not str or not row[k] for k in ('pad_uuid','zone_uuid'))
                or type(row['track_uuids']) is not list or len(row['track_uuids'])!=2
                or len(set(row['track_uuids']))!=2
                or any(type(u) is not str or not u for u in row['track_uuids'])):
            raise ValueError('exact_source_owned_force_landing_scope_required')
        path = Path(row['candidate']).resolve()
        if not path.is_file() or path in [q['candidate'] for q in resolved]:
            raise ValueError('distinct_saved_phase_candidates_required')
        resolved.append(dict(row, candidate=path))
    if resolved[-1]['candidate'] != Path(candidate).resolve():
        raise ValueError('cut_chain_does_not_end_at_actual_candidate')
    return resolved


def subtract(board, proof):
    """Private replay helper; this does not independently authorize a cut."""
    if proof.get('ok') is not True or proof.get('complete') is not True:
        raise ValueError('independently_received_cut_chain_required')
    ids = set(proof['retired_track_uuids']) | set(proof['retired_via_uuids'])
    live = {force._uid(t): t for t in board.GetTracks()}
    if not ids <= live.keys():
        raise ValueError('exact_original_cut_material_missing')
    discard_items(board, [live[u] for u in ids])


def receive(source, candidate, *, board_hint, phases, timeout_s=10.,per_phase_leases=False):
    """Optionally compose separate <=10-s independent receiving stages.

    The legacy aggregate deadline remains the default. Explicit per-phase
    leases bound each retyped phase AND whole-source replay by timeout_s;
    <=4 phases therefore allow <=50 s total, never an unbounded retry loop.
    This changes work allocation only, not any ownership or acceptance gate.
    """
    result = dict(schema=1, scope='finite_independent_typed_source_cut_chain',
        ok=False, complete=False, errors=[], release_authority=False,
        current_authority=False, inherited_debt_qualified=False,
        full_saved_board_receiving_still_required=True, phase_receiving=[])
    try:
        if (type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
                or not 0 < timeout_s <= 10):
            raise ValueError('bounded_cut_chain_receiving_required')
        if type(per_phase_leases) is not bool:
            raise ValueError('explicit_finite_independent_phase_lease_mode_required')
        source, candidate = [Path(p).resolve() for p in (source, candidate)]
        rows = _phases(phases, candidate)
        total_budget=timeout_s*(len(rows)+1) if per_phase_leases else timeout_s
        deadline=time.monotonic()+total_budget
        result.update(per_phase_leases=per_phase_leases,
            independent_stage_max_seconds=timeout_s,total_work_bound_seconds=total_budget)
        paths = [source, *[q['candidate'] for q in rows]]
        if len(set(paths)) != len(paths):
            raise ValueError('cut_chain_cannot_revisit_source_or_candidate')
        families = [force._family(p, board_hint) for p in paths]
        epoch = force._code_identity()
        key=_cache_key(paths,families,epoch,board_hint,rows,per_phase_leases)
        if time.monotonic()>=deadline:raise ValueError('typed_cut_chain_binding_deadline')
        if key is not None and key in _RECEIVED:
            # Callers can annotate their receipt, but never mutate the cached
            # independent native proof used by the next receiving stage.
            result=copy.deepcopy(_RECEIVED[key]);_RECEIVED.move_to_end(key)
            current=[force._family(p,board_hint) for p in paths]
            if key!=_cache_key(paths,current,force._code_identity(),board_hint,rows,per_phase_leases):
                raise ValueError('cached_cut_chain_input_changed_during_rebinding')
            if time.monotonic()>=deadline:raise ValueError('cached_cut_chain_rebinding_deadline')
            result['independent_geometry_reused_with_fresh_content_binding']=True
            return result
        retired_tracks, retired_vias, earlier_additions = set(), set(), set()
        pose_replays=[];posed=set();force_replays=[];force_modified=set();force_added=set()
        land_replays=[];land_modified=set()
        local_factory_groups=set()
        parent = source
        for row in rows:
            remaining = min(timeout_s,deadline-time.monotonic())
            if remaining <= 0:
                raise ValueError('typed_cut_chain_deadline')
            if row['kind']=='manufacturer_land_pattern':
                import cec_manufacturer_land_pattern as receiving
                proof=receiving.receive(parent,row['candidate'],board_hint=board_hint,
                    footprint_uuids=row['footprint_uuids'],timeout_s=remaining)
            elif row['kind'] == 'ground_strap':
                import cec_ground_strap_rebuild as receiving
                proof = receiving.receive(parent, row['candidate'], board_hint=board_hint,
                    pad_uuid=row['pad_uuid'], timeout_s=remaining,
                    allow_locked_track_uuids=row.get('allow_locked_track_uuids',()),
                    allow_locked_via_uuid=row.get('allow_locked_via_uuid'),
                    land_role=row.get('land_role','logical'))
            elif row['kind'] == 'redundant_bypass_ground':
                import cec_redundant_bypass_ground as receiving
                proof = receiving.receive(parent,row['candidate'],board_hint=board_hint,
                    pad_uuid=row['pad_uuid'],track_uuid=row['track_uuid'],timeout_s=remaining)
            elif row['kind']=='ground_plane_echo':
                import cec_ground_plane_echo as receiving
                proof=receiving.receive(parent,row['candidate'],board_hint=board_hint,
                    track_uuid=row['track_uuid'],timeout_s=remaining)
            elif row['kind'] == 'bypass_return_reseat':
                import cec_bypass_return_reseat as receiving
                proof = receiving.receive(parent,row['candidate'],board_hint=board_hint,
                    pad_uuid=row['pad_uuid'],track_uuid=row['track_uuid'],timeout_s=remaining,
                    allow_owned_locked=row.get('allow_owned_locked',False),
                    allow_qualified_local_vias=row.get('allow_qualified_local_vias',False))
            elif row['kind'] == 'ordinary_barrel_reseat':
                import cec_ordinary_barrel_reseat as receiving
                proof = receiving.receive(parent,row['candidate'],board_hint=board_hint,
                    via_uuid=row['via_uuid'],allow_owned_locked=row.get('allow_owned_locked',False),
                    max_additional_path_mm=row.get('max_additional_path_mm',4.),
                    max_source_leg_mm=row.get('max_source_leg_mm',8.),
                    timeout_s=remaining)
            elif row['kind'] == 'ground_reference_reflow':
                import cec_ground_reference_reflow as receiving
                proof = receiving.receive(parent,row['candidate'],board_hint=board_hint,
                    pad_uuid=row['pad_uuid'],allow_locked_track_uuids=row['allow_locked_track_uuids'],timeout_s=remaining)
            elif row['kind']=='measurement_leaf_reflow':
                import cec_local_branch_access as receiving
                proof=receiving.receive_measurement_reflow(parent,row['candidate'],board_hint=board_hint,
                    pad_uuid=row['pad_uuid'],timeout_s=remaining)
            elif row['kind']=='stationary_cell':
                import cec_local_branch_access as receiving
                proof=receiving.receive(parent,row['candidate'],board_hint=board_hint,
                    pad_uuids=row['pad_uuids'],timeout_s=remaining)
            elif row['kind']=='rated_barrel_reseat':
                import cec_rated_barrel_reseat as receiving
                proof=receiving.receive(parent,row['candidate'],board_hint=board_hint,
                    retired_track_uuids=row['retired_track_uuids'],
                    retired_via_uuids=row['retired_via_uuids'],timeout_s=remaining,
                    **{k:v for k,v in row.items() if k not in
                        {'kind','candidate','retired_track_uuids','retired_via_uuids'}})
            elif row['kind'] == 'rated_branch':
                import cec_rated_branch_repair as receiving
                proof = receiving.receive(parent, row['candidate'], board_hint=board_hint,
                    retired_track_uuids=row['retired_track_uuids'], timeout_s=remaining,
                    allow_rated_layer_bridges=row.get('allow_rated_layer_bridges',False),
                    max_source_track_mm=row.get('max_source_track_mm',8.),
                    max_replacement_width_mm=row.get('max_replacement_width_mm',.35),
                    max_retired_tracks=row.get('max_retired_tracks',8),
                    max_source_width_mm=row.get('max_source_width_mm',.35),
                    allow_rated_source_inner_layers=row.get('allow_rated_source_inner_layers',False),
                    repair_undersized_source=row.get('repair_undersized_source',False),
                    use_source_declared_consumer_island=row.get('use_source_declared_consumer_island',False),
                    repair_aggregate_current_domain=row.get('repair_aggregate_current_domain',False),
                    retire_obsolete_terminal_vias=row.get('retire_obsolete_terminal_vias',False),
                    allow_qualified_local_vias=row.get('allow_qualified_local_vias',False))
            elif row['kind']=='sensitive_redundant_span':
                import cec_sensitive_redundant_span as receiving
                proof=receiving.receive(parent,row['candidate'],board_hint=board_hint,
                    retired_track_uuids=row['retired_track_uuids'],
                    allow_locked_source=row.get('allow_locked_source',False),
                    source_contained_trim=row.get('source_contained_trim'),timeout_s=remaining)
            elif row['kind'] == 'paired_fixed_port_shortening':
                import cec_pair_fixed_port_shortening as receiving
                proof=receiving.receive_literal_phase(parent,row['candidate'],board_hint=board_hint,
                    pair_name=row['pair_name'],kernel_track_uuids=row['kernel_track_uuids'],
                    allow_locked_source=row.get('allow_locked_source',False),timeout_s=remaining,
                    reference_mode=row.get('reference_mode','strict_source_deficit'))
            elif row['kind'] == 'paired_axis_miter':
                import cec_pair_axis_miter as receiving
                proof=receiving.receive(parent,row['candidate'],board_hint=board_hint,
                    pair_name=row['pair_name'],retired_track_uuids=row['retired_track_uuids'],retreat_nm=row['retreat_nm'],
                    allow_locked_source=row.get('allow_locked_source',False),
                    allow_existing_non_signal_face=row.get('allow_existing_non_signal_face',False),timeout_s=remaining)
            elif row['kind'] == 'full_current_planar_reflow':
                import cec_full_current_planar_reflow as receiving
                proof = receiving.receive(parent, row['candidate'], board_hint=board_hint,
                    retired_track_uuids=row['retired_track_uuids'], timeout_s=remaining,
                    max_source_track_mm=row.get('max_source_track_mm',8.),
                    max_source_cut_mm=row.get('max_source_cut_mm',32.))
            elif row['kind'] == 'support_pivot':
                # Reuse the existing strict fixed-land/orphan receiver. A
                # chain grants NO connected-land translation or general IC,
                # power/bypass motion. Reference/value poses may only replay
                # its bounded source-authored field rule.
                import cec_support_pivot_receiving as receiving
                proof = receiving.receive(parent,row['candidate'],board_hint=board_hint,
                    allow_support_field_reflow=row.get('allow_support_field_reflow',False),timeout_s=remaining)
            elif row['kind'] in ('force_landing','force_keeper'):
                import cec_shunt_force_landing as receiving
                proof=receiving.receive(parent,row['candidate'],board_hint=board_hint,
                    pad_uuid=row['pad_uuid'],zone_uuid=row['zone_uuid'],track_uuids=row['track_uuids'],timeout_s=remaining,
                    mode='existing_outer_keeper' if row['kind']=='force_keeper' else 'outer_reseat')
            elif row['kind']=='force_endcap':
                import cec_shunt_endcap_clearance as receiving
                proof=receiving.receive(parent,row['candidate'],board_hint=board_hint,
                    pad_uuid=row['pad_uuid'],track_uuid=row['track_uuid'],timeout_s=remaining)
            elif row['kind'] in ('ordinary', 'ordinary_exclusive_via_path', 'ordinary_redundant_cut'):
                import cec_ordinary_route_receiving as receiving
                via_scope = (dict(retired_via_uuids=row['retired_via_uuids'],
                    allow_locked_via_uuids=row['allow_locked_via_uuids'])
                    if row['kind'] == 'ordinary_exclusive_via_path' else {})
                if row['kind']=='ordinary_redundant_cut':
                    via_scope=dict(redundant_single_face_via_uuids=row['redundant_single_face_via_uuids'],
                        retired_via_uuids=row.get('retired_via_uuids',()),
                        allow_locked_via_uuids=row['allow_locked_via_uuids'],allow_redundant_cut_only=True)
                proof = receiving.receive(parent,row['candidate'],board_hint=board_hint,
                    retired_track_uuids=row['retired_track_uuids'],
                    allow_locked_track_uuids=row['allow_locked_track_uuids'],timeout_s=remaining,
                    **via_scope)
            else:
                proof = additive.receive(parent, row['candidate'], timeout_s=remaining)
            result['phase_receiving'].append(dict(kind=row['kind'], proof=proof))
            if proof.get('ok') is not True or proof.get('complete') is not True:
                raise ValueError('independent_typed_cut_phase_refused')
            if row['kind']=='manufacturer_land_pattern':
                land_replays.append(proof['proposal'])
                land_modified.update(proof['modified_native_uuids'])
            if row['kind'] in ('force_landing','force_keeper','force_endcap'):
                modified=set(proof['modified_native_uuids'])
                if modified&(force_modified|earlier_additions|retired_tracks|retired_vias):
                    raise ValueError('force_landing_cannot_modify_repeated_or_reconstructed_material')
                force_modified.update(modified);force_replays.append(proof['proposal'])
                force_added.update(proof['added_native_uuids'])
            if row['kind']=='support_pivot':
                native=pcbnew.LoadBoard(str(row['candidate']))
                for pivot in proof['pivots']:
                    uid=pivot['footprint_uuid']
                    if uid in posed:raise ValueError('cut_chain_support_pivot_repeated')
                    fp=native.FindFootprintByReference(pivot['ref'])
                    if fp is None or force._uid(fp)!=uid:
                        raise ValueError('received_cut_chain_support_identity_changed')
                    posed.add(uid);pose_replays.append(dict(ref=pivot['ref'],footprint_uuid=uid,
                        position_nm=list(fp.GetPosition()),orientation_deg=fp.GetOrientationDegrees(),
                        allow_support_field_reflow=row.get('allow_support_field_reflow',False)))
            tracks, vias = set(proof.get('retired_track_uuids', ())), set(proof.get('retired_via_uuids', ()))
            if (tracks | vias) & (earlier_additions|force_modified):
                raise ValueError('later_cut_cannot_retire_earlier_reconstruction')
            if (tracks | vias) & (retired_tracks | retired_vias):
                raise ValueError('cut_chain_retirement_repeated')
            retired_tracks.update(tracks); retired_vias.update(vias)
            local_factory_groups.update(proof.get('source_local_factory_group_uuids',()))
            earlier_additions.update(proof['added_native_uuids'])
            parent = row['candidate']
        _, old = additive._nodes(source); _, new = additive._nodes(candidate)
        retired = retired_tracks | retired_vias
        if old.keys() - new.keys() != retired:
            raise ValueError('whole_chain_retirement_differs_from_proved_original_cuts')
        incoming = new.keys() - old.keys()
        # A double-plane ground echo is a positively typed subtraction-only
        # operator: retaining both barrels and the independently covered planes
        # is the construction. Requiring a token new trace would defeat it.
        # Do not extend this to untyped cuts, no-ops, or other repair kinds.
        subtraction_only_echo = bool(retired_tracks) and not retired_vias and not incoming \
            and not earlier_additions and all(row['kind']=='ground_plane_echo' for row in rows)
        # A separately typed, nonempty ordinary or source-sensitive cut already
        # proves every original surviving land/junction and exact source
        # scope. Compose ONLY those re-received phases, never arbitrary cuts
        # or a caller success flag. No earlier newly constructed material may
        # be retired; existing original-source replay remains mandatory.
        subtraction_only_scalar = bool(retired_tracks|retired_vias) and not incoming \
            and not earlier_additions and all(row['kind'] in ('ordinary_redundant_cut','sensitive_redundant_span') for row in rows)
        if incoming != earlier_additions or not incoming and not (subtraction_only_echo or subtraction_only_scalar):
            raise ValueError('whole_chain_additions_differ_from_proved_phases')
        # The first manufacturer receiver has ALREADY replayed the complete
        # original native definition, not just its changed footprints. That
        # writer can spell a legal implicit text angle as explicit zero.
        # Compose from that exact received prefix; never compare its proven
        # serialization with the pre-writer AST and call it unowned motion.
        # No generic normalization/tolerance is introduced. Every prefix is
        # freshly re-received above, then all families/engine are rebound.
        projection_source=source;projection_old=old
        if land_replays:
            if len(land_replays)!=1 or rows[0]['kind']!='manufacturer_land_pattern':
                raise ValueError('one_independently_received_first_manufacturer_prefix_required')
            projection_source=rows[0]['candidate']
            _,projection_old=additive._nodes(projection_source)
            if projection_old.keys()!=old.keys():
                raise ValueError('manufacturer_prefix_cannot_change_original_population')
        result['independently_received_manufacturer_prefix_is_exact_projection_basis']=bool(land_replays)
        with tempfile.TemporaryDirectory(prefix='cec-source-cut-chain-') as work:
            projected = force._copy_family(projection_source, Path(work)/'projected')
            basis = pcbnew.LoadBoard(str(projected))
            for proposal in force_replays:
                if proposal['mode']=='single_source_endcap':
                    import cec_shunt_endcap_clearance as force_seat
                else:
                    import cec_shunt_force_landing as force_seat
                force_seat.materialize(basis,proposal)
                field._save_field_snapshot(basis,projected)
                force_seat.compile_saved(projected,proposal)
                basis=pcbnew.LoadBoard(str(projected))
            discard_items(basis, [t for t in basis.GetTracks() if force._uid(t) in retired])
            final=pcbnew.LoadBoard(str(candidate))
            for pose in pose_replays:
                fp=basis.FindFootprintByReference(pose['ref']);target=final.FindFootprintByReference(pose['ref'])
                if (fp is None or target is None or force._uid(fp)!=pose['footprint_uuid']
                        or force._uid(target)!=pose['footprint_uuid']
                        or list(target.GetPosition())!=pose['position_nm']
                        or target.GetOrientationDegrees()!=pose['orientation_deg']):
                    raise ValueError('whole_chain_received_support_pose_changed')
                fp.SetOrientationDegrees(target.GetOrientationDegrees());fp.SetPosition(target.GetPosition())
                if pose['allow_support_field_reflow']:
                    import cec_support_field_reflow as fields
                    fields.replay_poses(fp,target)
            if retired and not (force_replays or pose_replays):
                if local_factory_groups:
                    # Every group is independently retyped by an earlier
                    # receiver. Derive the literal member cut again from the
                    # actual original group; do not normalize other Source
                    # nodes during the whole-parent composition.
                    import cec_source_literal_group_retirement as literal_groups
                    member_cuts={u:sorted(additive._members(projection_old[u])&retired_vias)
                        for u in local_factory_groups}
                    result['literal_native_cut_projection']=literal_groups.write_native_projection(
                        projection_source,projected,retired,member_cuts,basis)
                else:
                    import cec_source_literal_retirement as literal_cut
                    result['literal_native_cut_projection']=literal_cut.write_native_projection(
                        projection_source,projected,retired,basis)
            elif force_replays or pose_replays:
                # Land/force/pose and independently proved factory-group
                # changes still require their original exact native replay.
                # The opaque subtraction helper cannot license those edits.
                field._save_field_snapshot(basis, projected)
            _, nodes = additive._nodes(projected)
            # Force keeper fills and consequent GND antipads are received by
            # a separate exact native compiler replay, not copied from child.
            allowed_recompiled=force_modified|force_added|{force._uid(z) for z in basis.Zones()
                if force_replays and not z.GetIsRuleArea() and z.GetNetname()=='GND'}
            import cec_bypass_return_reseat as bypass_return
            if nodes.keys() != (projection_old.keys()-retired)|force_added or any(
                    not bypass_return.exact_factory_group_subtraction(projection_old[u],nodes[u],retired_vias)
                    if u in local_factory_groups else
                    sexpr._freeze(nodes[u]) != sexpr._freeze(new[u] if u in posed or u in land_modified or u in force_modified or u in force_added else projection_old[u])
                    for u in nodes if u not in allowed_recompiled):
                raise ValueError('whole_cut_subtraction_changed_unowned_original_material')
            if any(sexpr._freeze(nodes[u])!=sexpr._freeze(new[u]) for u in force_modified|force_added):
                raise ValueError('whole_original_force_landing_differs_from_received_replay')
            remaining = min(timeout_s,deadline-time.monotonic())
            if remaining <= 0:
                raise ValueError('typed_cut_chain_whole_replay_deadline')
            replay = additive.receive(projected, candidate, timeout_s=remaining)
            result['whole_original_cut_additions_ground_and_rule_replay'] = replay
            if replay.get('ok') is not True or replay.get('complete') is not True:
                raise ValueError('whole_original_source_cut_delta_refused')
        current_families=[force._family(p, board_hint) for p in paths]
        current_epoch=force._code_identity()
        if (families != current_families or epoch != current_epoch
                or key != _cache_key(paths,current_families,current_epoch,board_hint,rows,per_phase_leases)):
            raise ValueError('cut_chain_saved_families_or_code_changed')
        if time.monotonic()>=deadline:raise ValueError('typed_cut_chain_final_binding_deadline')
        result.update(ok=True, complete=True, source_candidate_and_code_unchanged=True,
            retired_track_uuids=sorted(retired_tracks), retired_via_uuids=sorted(retired_vias),
            added_native_uuids=sorted(incoming), full_phase_lineage_received=True,
            independently_received_subtraction_only_ground_echo=subtraction_only_echo,
            independently_received_subtraction_only_ordinary_cleanup=subtraction_only_scalar and all(
                row['kind']=='ordinary_redundant_cut' for row in rows),
            independently_received_subtraction_only_source_typed_scalar_cleanup=subtraction_only_scalar,
            independently_received_source_sensitive_redundancy=any(row['kind']=='sensitive_redundant_span' for row in rows),
            source_pose_replays=pose_replays,
            source_manufacturer_land_pattern_replays=land_replays,
            manufacturer_modified_footprint_uuids=sorted(land_modified),
            strict_manufacturer_land_patterns_received=bool(land_replays),
            source_force_landing_replays=force_replays,modified_native_uuids=sorted(force_modified),
            source_local_factory_group_uuids=sorted(local_factory_groups),
            exact_source_force_collector_uuids=sorted(force_added),
            strict_source_owned_force_landing_received=bool(force_replays),
            strict_fixed_land_orphan_support_pivots_received=bool(pose_replays),
            whole_source_cuts_and_only_received_support_poses_replayed=True,
            independent_geometry_reused_with_fresh_content_binding=False)
        if key is not None:
            _RECEIVED[key]=copy.deepcopy(result);_RECEIVED.move_to_end(key)
            while len(_RECEIVED)>_MAX_RECEIVED:_RECEIVED.popitem(last=False)
    except Exception as exc:
        result.update(ok=False,complete=False)
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result
