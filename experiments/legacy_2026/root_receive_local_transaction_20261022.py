"""Finite typed local transaction plus actual selected-parent receiving.

No callback, external success flag, board/refdes rule or native warning
waiver is authority. Intermediate branches stay private, even if a later
typed step resolves a temporary native finding. The actual original selected
board still owes current, force/pair, field, Ground, contact/Kelvin, source
intake, parity, native-all-findings and craft receiving at the final boundary.
"""
import argparse
import json
from pathlib import Path
import re
import tempfile
import time
import traceback
import subprocess
import sys

import cec_swig_guard
cec_swig_guard.pin()
import wx
quiet=wx.LogNull()
import pcbnew
import cec_force_current as force
import cec_received_private_stage as stage
import cec_complete_macro_cell as macro
import cec_control_shunt_tail_cleanup as tails
import cec_source_mount_stitch_reconcile as mount
import cec_qualified_courtyard_restore as court
import cec_reference_field_seating as fields
import cec_mask_search_reference_mapping as maps
import cec_root_reference_seating as root_seats
import cec_field_coupling as coupling
import cec_current_debt as current
import cec_force_sense_evidence as sense
import cec_received_route_evidence as received_contact
import cec_ground_return_preservation as returns
import cec_native_drc_runner as native
import cec_placement_route_prefix as protected
import cec_fr as fr
import cec_additive_route_receiving as additive
import cec_synth_pipeline as synth
import cec_constraints as constraints
import cec_route_quality as quality
import cec_suite_annotation_transition as annotations
import cec_ordinary_signal_completion as ordinary_join
import cec_ordinary_route_receiving as ordinary_reflow
import cec_can_endpoint_join as can_join
import cec_isolated_measurement_completion as measurement_join
import cec_measurement_quiet_fanout as measurement_fanout
import cec_source_connector_feedthrough as connector_feedthrough
import cec_source_sideband_monitor_tap as sideband_monitor_tap
import cec_ground_access_completion as ground_entry
import cec_source_divider_ground_span as divider_ground
import cec_rc_return_pivot_receiving as rc_return_pivot
import cec_macro_measurement_evidence as macro_contact
import cec_saved_macro_tail_cleanup as macro_cleanup
import cec_equivalent_courtyard_serialization as equivalent_court
import cec_detached_ordinary_passive_translation as detached_passive
import cec_rated_branch_repair as rated_branch
import cec_root_caption_seating as caption_seats
import cec_source_pad_bank_stage as pad_bank_stage
import cec_retained_passive_pose_stage as retained_passive_pose
import cec_full_current_planar_reflow as full_current_planar
import cec_protected_current_reconstruction as protected_current
import cec_distributed_supply_stage as distributed_supply
import cec_coowned_ground_component_join as coowned_ground
import cec_distributed_supply_layer_join as distributed_layer_join
import cec_bypass_return_reseat as bypass_return
import cec_current_passive_cell as current_passive_cell
import cec_ordinary_barrel_reseat as ordinary_barrel
import cec_monitor_divider_ground_return as monitor_ground
import cec_quiet_input_pad_cleanup as quiet_pad_cleanup
import cec_saved_reference_cleanup_chain as reference_cleanup
import cec_auxiliary_attachment_current as auxiliary_attachment
import cec_source_class_ground_dead_end_tail as source_ground_tail
import cec_source_class_ground_land_root_spur as source_ground_land_spur
import cec_source_class_ground_literal_endpoint_tail as source_ground_literal_tail
import cec_redundant_source_ground_link as redundant_ground_link
import cec_quiet_signal_completion as quiet_signal_join
import cec_ground_via_clearance_window as ground_window
import cec_native_window_contact_preservation as window_contact
import cec_signal_via_clearance_window as signal_window
import cec_source_ordinary_barrel_kernel as ordinary_kernel
import cec_source_aggregate_capacitor_cell as aggregate_capacitor
import cec_source_rc_elbow_reflow as source_rc_elbow


KINDS={'complete_macro':{'options'},'control_shunt_tail':{'warning_uuids'},
    'auxiliary_attachment':{'attachment_id'},
    'source_class_ground_tail':{'seed_uuid','allow_locked_track_uuids'},
    'source_ground_literal_endpoint_tail':{'seed_uuid','allow_locked_track_uuids'},
    'source_ground_land_root_spur':{'seed_uuid','allow_locked_track_uuids'},
    'redundant_source_ground_link':{'track_uuids'},
    'saved_reference_cleanup':{'proposal'},
    'reference_fields':{'proposal'},'reference_map':{'proposal'},'root_reference_seat':{'proposal'},
    'mechanical_mount':{'mount_uuids'},'qualified_courtyard':{'proposal'},
    'print_context':{'proposal'},'ordinary_join':{'net'},'ordinary_columns':{'net'},
    'quiet_signal_join':{'net'},
    'ordinary_reflow':{'net','retired_track_uuids'},
    'macro_tail_cleanup':{'proposal'},'equivalent_courtyard':{'proposal'},
    'detached_passive_translation':{'proposal'},'rated_branch':{'retired_track_uuids','options'},
    'root_caption_seat':{'proposal'},'can_endpoint_join':{'net'},
    'isolated_measurement_join':{'pad_uuid'},
    'measurement_auxiliary_input_join':{'paired_pad_uuid'},
    'source_connector_feedthrough':{'pad_uuids'},
    'source_connector_native_frontier':{'pad_uuids','access_uuids'},
    'source_series_resistor_monitor_tap':{'connector_pad_uuids','target_pad_uuid'},
    'source_series_resistor_monitor_local_tap':{'connector_pad_uuids','target_pad_uuid'},
    'connected_footprint_pose':{'footprint_uuids'},
    'source_ordinary_resistor_reference_pose':{'footprint_uuid','reference_group_uuid'},
    'measurement_quiet_fanout':{'pad_uuid','peer_pad_uuid'},
    'source_local_bypass_return':{'pad_uuid','track_uuid'},
    'existing_local_ground_entry':{'pad_uuid'},
    'source_contained_ground_window':{'pad_uuid'},
    'source_local_return_window':{'pad_uuid'},
    'source_ordinary_signal_window':{'pad_uuid','position_nm'},
    'source_local_ground_dogbone':{'pad_uuid','position_nm'},
    'source_local_ground_polyline':{'pad_uuid','points_nm'},
    'coowned_input_control_ground':{'pad_uuid'},
    'source_pad_bank':{'proposal','zone_uuid'},
    'source_aggregate_capacitor_cell':{'proposal'},
    'source_rc_elbow_reflow':{'pad_uuid','span_uuids'},
    'retained_passive_pose':{'proposal'},
    'complete_current_passive_cell':{'proposal'},
    'ordinary_barrel_reseat':{'via_uuid'},
    'source_ordinary_barrel_reseat':{'via_uuid'},
    'source_ordinary_barrel_kernel':{'via_uuid'},
    'full_current_planar_reflow':{'retired_track_uuids'},
    'distributed_supply_join':{'net'},
    'distributed_supply_layer_join':{'net','pad_uuids'},
    'ordinary_source_reflow':{'net','retired_track_uuids','allow_locked_track_uuids'},
    'source_divider_ground_span':{'ground_pad_uuid','retired_track_uuids','points_nm'},
    'rc_return_pivot':set(),
    'monitor_divider_ground_return':{'pad_uuid'},
    'quiet_input_pad_cleanup':{'input_pad_uuid','peer_pad_uuid'}}

# Resource-composition limit, not physical permission. A coherent repair can
# need two independently received preclears, one complete macro, its exposed
# tail cleanup, one reference operation and final explicit print receiving.
# Every phase still owns its real saved boundary; no nesting/retry/callback
# or constituent deadline override is introduced by the larger finite chain.
MAX_LOCAL_PHASES=6
MAX_COMPLETE_MACROS=2


def record_progress(out,result,stage,started):
    """Non-authoritative last-stage evidence, even if native code exits.

    The final receiving.json remains the ONLY complete transaction result.
    This journal never converts a prefix gate into whole-board authority.
    """
    force._write(Path(out)/'progress.json',dict(scope='local_transaction_stage_journal',
        last_started_stage=stage,elapsed_s=time.monotonic()-started,
        baseline=result.get('baseline'),baseline_sha256=result.get('baseline_sha256'),
        candidate=result.get('candidate'),candidate_sha256=result.get('candidate_sha256'),
        finished_gates=dict(result.get('gates',{})),
        receiving_complete=False,admitted=False,release_authority=False))


def _sideband_ids(values,name,count):
    """Literal identities only; the saved public receiver proves their roles."""
    if (type(values)is not list or len(values)!=count
            or any(type(v)is not str or not v or len(v)>128 or v!=v.strip()
                or any(ord(c)<32 for c in v)for v in values)):
        raise ValueError('exact_'+name+'_identities_required')
    return ordinary_reflow._ids(values,name,count)


def validate_phases(phases):
    if type(phases)is not list or not 1<=len(phases)<=MAX_LOCAL_PHASES:raise ValueError('finite_one_to_six_typed_local_phases_required')
    kinds=[];ordinary_nets=set();measurement_inputs=set();feedthrough_pairs=set();distributed_layer_pairs=set()
    monitor_pairs=set();monitor_targets=set();posed_footprints=set();full_current_cuts=set();signal_window_pads=set()
    rc_elbow_cuts=set();ground_tail_seeds=set()
    ground_link_cuts=set();other_requested_cuts=set()
    for row in phases:
        kind=row.get('kind')if type(row)is dict else None
        expected=({'kind','candidate','candidate_sha256'}|KINDS[kind])if kind in KINDS else set()
        optional=({'allow_nonplane_power_role'}if kind in
            ('source_connector_feedthrough','source_connector_native_frontier')else set())
        if kind=='print_context':optional={'replay_origin'}
        if kind=='isolated_measurement_join':optional={'path_length_budget_nm'}
        if kind not in KINDS or not expected<=set(row)<=expected|optional:
            raise ValueError('exact_typed_local_phase_schema_required')
        if kind=='redundant_source_ground_link':
            values=row['track_uuids']
            if type(values)is not list or not 1<=len(values)<=8:
                raise ValueError('bounded_exact_Source_Ground_link_tracks_required')
            selected=_sideband_ids(values,'Source_Ground_link_tracks',len(values))
            if selected&(ground_link_cuts|other_requested_cuts):
                raise ValueError('disjoint_exact_Source_Ground_link_cuts_required')
            ground_link_cuts.update(selected)
        else:
            # This new owner cannot repeat an explicitly requested cut,
            # span or discovery seed elsewhere in the transaction. Other
            # operators retain their existing independent schema/receivers;
            # a seed never claims its undiscovered sibling edges here.
            requested=set()
            for key in ('retired_track_uuids','span_uuids'):
                values=row.get(key)
                if type(values)in(list,tuple,set)and all(type(v)is str for v in values):
                    requested.update(values)
            for key in ('seed_uuid','track_uuid'):
                if type(row.get(key))is str:requested.add(row[key])
            if requested&ground_link_cuts:
                raise ValueError('disjoint_exact_Source_Ground_link_cuts_required')
            other_requested_cuts.update(requested)
        if optional and type(row.get('allow_nonplane_power_role',False))is not bool:
            raise ValueError('explicit_boolean_Source_nonplane_recovery_policy_required')
        if kind=='print_context' and type(row.get('replay_origin',False))is not bool:
            raise ValueError('explicit_boolean_fresh_print_origin_mode_required')
        if kind=='auxiliary_attachment'and (type(row['attachment_id'])is not str
                or not 0<len(row['attachment_id'])<=1024
                or row['attachment_id']!=row['attachment_id'].strip()):
            raise ValueError('one_exact_Source_auxiliary_attachment_identity_required')
        if kind in ('source_contained_ground_window','source_local_return_window'):
            _sideband_ids([row['pad_uuid']],'Source_contained_Ground_window_land',1)
        if kind=='source_ordinary_signal_window':
            ids=_sideband_ids([row['pad_uuid']],'Source_ordinary_signal_window_land',1)
            if ids&signal_window_pads:
                raise ValueError('repeated_Source_signal_window_requires_a_separate_transaction')
            signal_window_pads.update(ids)
            if (type(row['position_nm'])is not list or len(row['position_nm'])!=2
                    or any(type(v)is not int or abs(v)>2000000000 for v in row['position_nm'])):
                raise ValueError('literal_integer_Source_signal_window_axis_required')
        if kind=='source_aggregate_capacitor_cell':
            value=row['proposal']
            if (type(value)is not str or not value or len(value)>4096 or value!=value.strip()
                    or any(ord(c)<32 for c in value)or not value.endswith('.json')):
                raise ValueError('one_exact_saved_Source_aggregate_capacitor_proposal_required')
        if kind=='source_rc_elbow_reflow':
            _sideband_ids([row['pad_uuid']],'Source_RC_elbow_input_land',1)
            selected=_sideband_ids(row['span_uuids'],'Source_RC_elbow_edges',3)
            if selected&rc_elbow_cuts:
                raise ValueError('repeated_Source_RC_elbow_cut_requires_separate_transaction')
            rc_elbow_cuts.update(selected)
        if kind in('connected_footprint_pose','source_ordinary_resistor_reference_pose'):
            if kind=='connected_footprint_pose':
                values=row['footprint_uuids']
                if type(values)is not list or not 1<=len(values)<=8:
                    raise ValueError('bounded_actual_connected_footprint_identities_required')
                selected=_sideband_ids(values,'connected_footprint',len(values))
            else:
                selected=_sideband_ids([row['footprint_uuid']],'Source_ordinary_reference_owner',1)
                _sideband_ids([row['reference_group_uuid']],'Source_ordinary_reference_group',1)
            if selected&posed_footprints:
                raise ValueError('repeated_connected_footprint_requires_separate_transaction')
            posed_footprints.update(selected)
        if kind in('source_class_ground_tail','source_ground_land_root_spur','source_ground_literal_endpoint_tail'):
            if not ordinary_reflow._ids([row['seed_uuid']],'Source_Ground_tail_seed',1):
                raise ValueError('one_exact_Source_Ground_tail_seed_required')
            if row['seed_uuid']in ground_tail_seeds:
                raise ValueError('repeated_Source_Ground_tail_seed_requires_separate_transaction')
            ground_tail_seeds.add(row['seed_uuid'])
            ordinary_reflow._ids(row['allow_locked_track_uuids'],'Source_Ground_tail_locks',8)
        if kind=='rated_branch':
            # Reuse the strict public typed-chain schema, not a caller
            # callback, worker receipt, timeout or board-identity override.
            options=rated_branch.reconstruction_options(row['options'])
            import cec_ordinary_route_receiving as ordinary
            if not ordinary._ids(row['retired_track_uuids'],'rated_local_source_tracks',
                    options.get('max_retired_tracks',8)):
                raise ValueError('nonempty_exact_rated_local_source_cut_required')
        if kind=='source_pad_bank':
            if (type(row['zone_uuid'])is not str or not row['zone_uuid']
                    or type(row['proposal'])is not str or not row['proposal']):
                raise ValueError('exact_saved_source_pad_bank_identity_required')
        if kind in ('ordinary_barrel_reseat','source_ordinary_barrel_reseat','source_ordinary_barrel_kernel'):
            # An identity only: the existing public receiver freshly proves
            # eligibility, exact departures and unchanged through geometry.
            # No caller current, width, ownership, lock or process flag.
            if not ordinary_reflow._ids([row['via_uuid']],'ordinary_Source_barrel',1):
                raise ValueError('one_exact_Source_ordinary_barrel_required')
        if kind=='monitor_divider_ground_return':
            if not ordinary_reflow._ids([row['pad_uuid']],'actual_monitor_divider_ground_land',1):
                raise ValueError('one_actual_monitor_divider_ground_identity_required')
        if kind=='quiet_input_pad_cleanup':
            ids=ordinary_reflow._ids([row['input_pad_uuid'],row['peer_pad_uuid']],
                'actual_source_quiet_cleanup_relationship',2)
            if len(ids)!=2:
                raise ValueError('distinct_actual_quiet_cleanup_relationship_required')
        if kind=='ordinary_source_reflow':
            import cec_ordinary_route_receiving as ordinary
            cuts=ordinary._ids(row['retired_track_uuids'],'exact_ordinary_Source_branch',8)
            locks=ordinary._ids(row['allow_locked_track_uuids'],'exact_ordinary_Source_locks',8)
            if not cuts or not locks<=cuts:
                raise ValueError('nonempty_ordinary_Source_branch_and_exact_lock_subset_required')
        if kind in ('ordinary_join','ordinary_columns','can_endpoint_join','ordinary_reflow',
                'ordinary_source_reflow','distributed_supply_join','quiet_signal_join'):
            if (type(row['net'])is not str or not row['net']or len(row['net'])>256
                    or any(ord(c)<32 for c in row['net'])):
                raise ValueError('explicit_literal_ordinary_join_net_required')
            # Independent net joins are useful in one bounded batch. The
            # explicit finite phase cap and every actual intermediate saved
            # receiver still apply; never repeat a net/attempt in this epoch.
            if row['net']in ordinary_nets:
                raise ValueError('repeated_local_operator_requires_a_separate_transaction')
            ordinary_nets.add(row['net'])
            if kind=='ordinary_reflow'and not ordinary_reflow._ids(
                    row['retired_track_uuids'],'exact_local_ordinary_source_cut',8):
                raise ValueError('nonempty_exact_local_ordinary_source_cut_required')
        elif kind=='distributed_supply_layer_join':
            # Only two exact old land identities and their literal rail.
            # The saved receiver freshly compiles existing aggregate, Source
            # terminal roles and full class/web obligations. No caller
            # current, layer, width, timeout or barrel-rating flag is accepted.
            pair=tuple(distributed_layer_join._ids(row['pad_uuids']))
            if (type(row['net'])is not str or not row['net']or len(row['net'])>256
                    or any(ord(c)<32 for c in row['net'])or pair in distributed_layer_pairs):
                raise ValueError('distinct_exact_distributed_layer_source_pair_required')
            distributed_layer_pairs.add(pair)
        elif kind=='measurement_auxiliary_input_join':
            # Only the literal paired-input identity is selected by the
            # caller. Fresh manufacturer/Source compilation owns the other
            # input, local signal geometry and actual isolated package land.
            selected=_sideband_ids([row['paired_pad_uuid']],
                'manufacturer_auxiliary_paired_input',1)
            if selected&measurement_inputs:
                raise ValueError('repeated_manufacturer_auxiliary_input_scope')
            measurement_inputs.update(selected)
        elif kind in('isolated_measurement_join','measurement_quiet_fanout'):
            # Only an actual manufacturer/schematic input identity is a
            # request. The saved receiver freshly compiles its shunt/pickup,
            # front-only policy and nonload width; caller nets/roles/paths
            # cannot be supplied here. Distinct inputs may share one finite
            # transaction, but an input cannot fund repeated retries.
            import cec_ordinary_route_receiving as ordinary
            ids=ordinary._ids([row['pad_uuid']],'isolated_measurement_input',1)
            if not ids or row['pad_uuid']in measurement_inputs:
                raise ValueError('repeated_local_operator_requires_a_separate_transaction')
            measurement_inputs.add(row['pad_uuid'])
            if kind=='isolated_measurement_join':
                measurement_join.path_length_work_limit(row.get(
                    'path_length_budget_nm',measurement_join.MAX_PATH_LENGTH_NM))
            if kind=='measurement_quiet_fanout':
                peer=ordinary._ids([row['peer_pad_uuid']],'source_quiet_measurement_peer',1)
                if not peer or row['peer_pad_uuid']==row['pad_uuid']:
                    raise ValueError('distinct_actual_quiet_input_peer_required')
        elif kind in('source_connector_feedthrough','source_connector_native_frontier'):
            # The request identifies two existing lands, not a caller net,
            # pin role, ampacity or barrel permission. Fresh saved receiving
            # compiles the selected Source part/channel and actual geometry.
            import cec_ordinary_route_receiving as ordinary
            ids=ordinary._ids(row['pad_uuids'],'source_connector_feedthrough_lands',2)
            if kind=='source_connector_native_frontier':
                ids=_sideband_ids(row['pad_uuids'],'Source_connector_lands',2)
                _sideband_ids(row['access_uuids'],'retained_Source_connector_access',2)
            pair=frozenset(ids)
            if len(ids)!=2 or len(pair)!=2:
                raise ValueError('two_distinct_existing_Source_feedthrough_lands_required')
            if pair in feedthrough_pairs or pair in monitor_pairs:
                raise ValueError('repeated_local_operator_requires_a_separate_transaction')
            feedthrough_pairs.add(pair)
        elif kind in('source_series_resistor_monitor_tap','source_series_resistor_monitor_local_tap'):
            # A connected canonical channel and one actual resistor land,
            # never a caller-selected GPIO role, net, via or current budget.
            pair=frozenset(_sideband_ids(row['connector_pad_uuids'],'Source_monitor_connectors',2))
            target=_sideband_ids([row['target_pad_uuid']],'Source_monitor_target',1)
            if target&pair or pair in monitor_pairs or target&monitor_targets:
                raise ValueError('distinct_once_only_Source_monitor_target_and_channel_required')
            monitor_pairs.add(pair);monitor_targets.update(target)
        elif kind=='source_local_bypass_return':
            import cec_ordinary_route_receiving as ordinary
            if not ordinary._ids([row['pad_uuid'],row['track_uuid']],'source_local_bypass_return_ids',2):
                raise ValueError('literal_distinct_Source_bypass_land_and_tail_required')
            if kind in kinds:raise ValueError('repeated_local_operator_requires_a_separate_transaction')
        elif kind=='source_ordinary_signal_window':
            # Each distinct Source land still receives its own complete saved
            # boundary. The finite transaction cap and final strict original-
            # parent progress gate prohibit a window-only success claim.
            pass
        elif kind in('existing_local_ground_entry','coowned_input_control_ground','source_local_ground_dogbone',
                     'source_local_ground_polyline'):
            import cec_ordinary_route_receiving as ordinary
            if not ordinary._ids([row['pad_uuid']],'existing_local_ground_land',1):
                raise ValueError('explicit_existing_Source_ground_land_required')
            if kind in kinds:raise ValueError('repeated_local_operator_requires_a_separate_transaction')
            if kind=='source_local_ground_dogbone' and (type(row['position_nm'])is not list
                    or len(row['position_nm'])!=2 or any(type(v)is not int
                        or abs(v)>2000000000 for v in row['position_nm'])):
                raise ValueError('literal_integer_Source_ground_dogbone_axis_required')
            if kind=='source_local_ground_polyline' and (type(row['points_nm'])is not list
                    or len(row['points_nm'])!=3 or any(type(p)is not list or len(p)!=2
                        or any(type(v)is not int or abs(v)>2000000000 for v in p)for p in row['points_nm'])):
                raise ValueError('three_literal_integer_Source_ground_polyline_points_required')
        elif kind=='full_current_planar_reflow':
            # Distinct physical obstructions may need separate full-current
            # reconstruction owners in one bounded coherent repair. Retire
            # no Source UUID twice; every immediate saved boundary still
            # independently proves its unchanged whole-current contract.
            cuts=ordinary_reflow._ids(row['retired_track_uuids'],'full_current_planar_cut',8)
            if not cuts or cuts&full_current_cuts:
                raise ValueError('distinct_nonempty_exact_full_current_planar_cuts_required')
            full_current_cuts.update(cuts)
        elif kind=='source_divider_ground_span':
            import cec_ordinary_route_receiving as ordinary
            if (not ordinary._ids([row['ground_pad_uuid']],'divider_Source_ground_land',1)
                    or not ordinary._ids(row['retired_track_uuids'],'divider_Source_tracks',8)
                    or type(row['points_nm'])is not list or not 2<=len(row['points_nm'])<=16
                    or any(type(p)not in(list,tuple)or len(p)!=2
                        or any(type(v)is not int or abs(v)>2000000000 for v in p)
                        for p in row['points_nm'])):
                raise ValueError('finite_exact_Source_divider_track_and_integer_path_request_required')
            if kind in kinds:raise ValueError('repeated_local_operator_requires_a_separate_transaction')
        elif kind in('source_class_ground_tail','source_ground_land_root_spur','source_ground_literal_endpoint_tail'):
            # Distinct Source seeds receive independently at their actual
            # saved parents. This is not a caller cut list or a cleanup loop;
            # the unchanged phase cap bounds the complete transaction.
            pass
        elif kind=='redundant_source_ground_link':
            # Only disjoint exact Source edges, never an unbounded cleanup
            # loop. The shared finite cap and every saved receiver remain.
            pass
        elif kind=='complete_macro':
            # A second complete cell is a distinct saved Source boundary,
            # not a retry or permission to normalize the whole transaction
            # into the final cell's pose. Contact composition below receives
            # both immediate parents independently and keeps their raw link.
            prior=[p for p in phases[:len(kinds)]if p.get('kind')==kind]
            if len(prior)>=MAX_COMPLETE_MACROS:
                raise ValueError('bounded_two_distinct_saved_macro_boundaries_required')
            if (type(row['options'])is not dict or any(
                    p['candidate']==row['candidate']or p['candidate_sha256']==row['candidate_sha256']
                    for p in prior)):
                raise ValueError('distinct_literal_saved_macro_boundary_and_options_required')
        elif kind in kinds:raise ValueError('repeated_local_operator_requires_a_separate_transaction')
        if 'print_context'in kinds:raise ValueError('typed_print_context_must_be_last')
        if kind=='control_shunt_tail'and 'complete_macro'not in kinds:raise ValueError('control_tail_requires_fresh_original_macro_scope')
        if kind=='macro_tail_cleanup'and (not kinds or kinds[-1]!='complete_macro'):
            raise ValueError('macro_tail_cleanup_requires_exact_immediate_saved_macro_boundary')
        if kind in('qualified_courtyard','equivalent_courtyard')and kinds:
            raise ValueError('source_courtyard_prerequisite_must_be_first')
        if kind in('detached_passive_translation','complete_current_passive_cell')and kinds:
            raise ValueError('detached_passive_source_pose_must_be_first')
        if 'mechanical_mount'in kinds:raise ValueError('mechanical_receiving_must_end_the_local_transaction')
        if kind in('reference_fields','reference_map','root_reference_seat','root_caption_seat','saved_reference_cleanup')and any(k in kinds for k in('reference_fields','reference_map','root_reference_seat','root_caption_seat','saved_reference_cleanup')):
            # One existing Source-owned root caption may be prepared before
            # the new map whose actual courtyard it vacates. Both distinct
            # saved phases are independently rederived/received; this does
            # not permit repeated annotation waves or a material shortcut.
            prior_references=[k for k in kinds if k in('reference_fields','reference_map','root_reference_seat','root_caption_seat')]
            if not(kind=='reference_map'and prior_references==['root_reference_seat']
                    and kinds[-1]=='root_reference_seat'):
                raise ValueError('one_explicit_readable_reference_strategy_per_transaction')
        if (type(row['candidate'])is not str or not row['candidate']
                or type(row['candidate_sha256'])is not str
                or re.fullmatch('[0-9a-f]{64}',row['candidate_sha256'])is None):
            raise ValueError('literal_saved_local_candidate_identity_required')
        json.dumps(row,allow_nan=False);kinds.append(kind)
    if 'quiet_input_pad_cleanup'in kinds:
        index=kinds.index('quiet_input_pad_cleanup')
        if (index+1>=len(phases)or phases[index+1]['kind']!='measurement_quiet_fanout'
                or phases[index]['input_pad_uuid']!=phases[index+1]['pad_uuid']
                or phases[index]['peer_pad_uuid']!=phases[index+1]['peer_pad_uuid']):
            raise ValueError('contained_quiet_cleanup_requires_its_immediate_exact_fanout')
    return kinds


def strict_current_repair_progress(report):
    """A fresh strict debt reduction is progress, never native-count closure.

    Routing-readiness still requires zero native findings. This lets an
    independently received undersized-feed repair be retained even when it
    preserves, rather than joins, its old conductor partitions. Every native
    non-regression and original-parent electrical/contact gate remains owed.
    """
    return (report.get('ok')is True and report.get('complete')is True
        and report.get('errors')==[]and report.get('new_faults')==[]
        and report.get('worsened_faults')==[]
        and type(report.get('before_fault_objects'))is int
        and type(report.get('after_fault_objects'))is int
        and 0<=report['after_fault_objects']<report['before_fault_objects'])


def field_geometry_scope(boards,paths,*,timeout_s=10.,maximum_native_items=16384):
    """The straight-segment field solver cannot silently omit related arcs."""
    deadline=time.monotonic()+timeout_s;checked=[]
    for board,path in zip(boards,paths):
        tracks=list(board.GetTracks());zones=list(board.Zones())
        if len(tracks)+len(zones)>maximum_native_items:
            raise ValueError('native_replacement_field_item_budget')
        resolver=fr._project_netclass_resolver(str(path));neutral=[]
        for item in tracks:
            if time.monotonic()>=deadline:raise ValueError('native_field_geometry_scope_deadline')
            if item.GetClass()in('PCB_TRACK','PCB_VIA'):continue
            role=coupling.classify_net(item.GetNetname(),
                netclass=coupling._netclass_name(resolver(item.GetNetname())))
            if role['aggressor']or role['victim']:
                raise ValueError('related_native_curved_copper_unsupported')
            neutral.append(force._uid(item))
        checked.append(dict(path=str(path),native_items=len(tracks)+len(zones),
            neutral_unsupported_geometry_uuids=neutral))
    return checked


def changed_native_nets(before,after):
    """Bound the real copper/terminal delta, never all pad net names.

    Same-UUID track changes and moved pads are included, as are actual zone
    outline/fill changes. The separately received phases authorize ownership;
    this inventory grants neither current nor contour-rebinding authority.
    """
    prior,child=map(coupling._field_snapshot_inventory,(before,after));nets=set()
    for key in prior.keys()|child.keys():
        left,right=prior.get(key),child.get(key)
        if left==right:continue
        for row in(left,right):
            if row is None:continue
            net=row[1]if key[0]=='track'else row[0]
            if type(net)is not str or not net:
                raise ValueError('changed_native_material_without_positive_net')
            nets.add(net)
    if len(nets)>64:raise ValueError('bounded_changed_native_net_scope_required')
    return sorted(nets)


def contact_manifest(parent,child,modified_nets):
    return (sense.native_copper_transform_inventory(parent,child,modified_nets=modified_nets)
        if modified_nets else [])


def strict_contact_transition(before,after,modified_nets,manifest):
    return (sense.compare_contour_preservation(before,after,modified_nets=modified_nets,
        native_copper_transforms=manifest)if modified_nets else sense.compare_contact_preservation(before,after))


def isolated_measurement_contact_transition(source,candidate,phases,evidence,*,board_hint,assembly_instance=None):
    """Repaired physical input legs need absolute AFTER proof, not a waiver.

    Derive the exact leg from independently recompiled saved measurement
    phases. Never take a caller net/ref/leg allowlist or edit raw replay
    packets. Existing absolute cut, inward-departure and unchanged-peer
    rules decide whether this actual previously open input can be received.
    All other original-parent gates remain independently mandatory.
    """
    kinds=validate_phases(phases)
    measurement_kinds={'isolated_measurement_join','measurement_quiet_fanout'}
    if not measurement_kinds.intersection(kinds):return None
    if (kinds[-1]!='print_context' or any(k not in {
            'rated_branch','ordinary_reflow','can_endpoint_join','source_local_bypass_return',
            'quiet_input_pad_cleanup',
            *measurement_kinds,'print_context'}for k in kinds)
            or any(k in ('rated_branch','ordinary_reflow','can_endpoint_join','source_local_bypass_return',
                         'quiet_input_pad_cleanup')
                   for k in kinds[min(i for i,k in enumerate(kinds)if k in measurement_kinds)+1:])):
        raise ValueError('exact_typed_measurement_endpoint_then_print_sequence_required')
    source,candidate=[Path(p).resolve(strict=True)for p in(source,candidate)]
    if source==candidate:raise ValueError('distinct_measurement_contact_endpoints_required')
    code=force._code_identity();families=[force._family(p,board_hint)for p in(source,candidate)]
    cursor=source;legs=[];replayed=[]
    for phase in phases:
        prior=cursor
        cursor,proof=receive_phase(source,prior,phase,board_hint,
            assembly_instance=stage.matched_instance(assembly_instance,prior))
        replayed.append(dict(kind=phase['kind'],candidate=str(cursor),receiving=proof))
        if phase['kind']not in measurement_kinds:continue
        fresh=proof['independently_compiled_source_scope']
        if phase['kind']=='measurement_quiet_fanout':
            if (fresh.get('complete')is not True
                    or fresh.get('peer_pad_uuid')!=phase['peer_pad_uuid']
                    or proof.get('exact_source_shunt_and_original_quiet_tree_retained')is not True):
                raise ValueError('exact_received_source_quiet_fanout_required')
            fresh=fresh['source_request']
        demand=fresh['request']['demand'];segment=demand['source_segment']
        if (fresh.get('complete')is not True or fresh.get('pad_uuid')!=phase['pad_uuid']
                or demand['pad_uuid']!=phase['pad_uuid']or segment['net']!=demand['net']
                or segment['leg']not in('p','n')):
            raise ValueError('fresh_exact_manufacturer_measurement_contact_leg_required')
        leg=(segment['start']['ref'],segment['leg'],segment['net'])
        if leg in legs:raise ValueError('duplicate_actual_measurement_contact_leg')
        legs.append(leg)
    if cursor!=candidate:raise ValueError('exact_measurement_contact_final_endpoint_required')
    boards=[pcbnew.LoadBoard(str(p))for p in(source,candidate)]
    modified=changed_native_nets(*boards);manifest=contact_manifest(*boards,modified)
    if 'measurement_quiet_fanout'in kinds:
        # Joining a Source-qualified quiet tree legitimately adds another
        # consumer to its *existing* input's native cut component/witness.
        # Re-use the established independent whole-cohort absolute receiver:
        # every affected input must pass AFTER, otherwise retain exact new
        # leg scope and strict unchanged-peer evidence. No raw packet is
        # normalized, no unknown/failing physical cut becomes qualified.
        result=received_contact._compare_input_repairs(*evidence,legs,modified,manifest)
    else:
        result=sense.compare_repaired_preservation(*evidence,
            repair_nets=sorted({k[2]for k in legs}),modified_nets=modified,
            repair_legs=legs,native_copper_transforms=manifest)
    result.update(independently_received_measurement_phases=replayed,
        actual_Source_derived_repair_legs=[list(k)for k in legs],
        raw_parent_and_candidate_evidence_not_rewritten=True)
    if (code!=force._code_identity()
            or families!=[force._family(p,board_hint)for p in(source,candidate)]):
        raise ValueError('measurement_contact_source_or_code_changed')
    return result


def complete_macro_chain_contact_transition(source,candidate,phases,evidence,*,board_hint,assembly_instance=None):
    """Two consecutive complete cells keep two immediate Source proofs.

    No final-cell allowlist is applied to the original parent. The exact
    raw AFTER of the first independently received macro is strictly compared
    with the exact raw BEFORE of the next macro on the *same saved board*.
    Non-macro prefix/suffix phases retain their own typed receiving and their
    original strict contact comparisons. This bounded form deliberately does
    not accept an interposed input repair or skip an intermediate boundary.
    """
    kinds=validate_phases(phases)
    indices=[i for i,k in enumerate(kinds)if k=='complete_macro']
    prefix_kinds={'source_ordinary_barrel_reseat','rated_branch','redundant_source_ground_link'}
    suffix_kinds={'reference_fields','reference_map','root_reference_seat',
        'macro_tail_cleanup','source_class_ground_tail','source_ground_land_root_spur',
        'source_ground_literal_endpoint_tail','redundant_source_ground_link'}
    if (len(indices)!=MAX_COMPLETE_MACROS or indices[1]!=indices[0]+1
            or kinds[-1]!='print_context'
            or any(k not in prefix_kinds for k in kinds[:indices[0]])
            or any(k not in suffix_kinds for k in kinds[indices[-1]+1:-1])):
        raise ValueError('two_consecutive_immediate_Source_macros_then_typed_cleanup_and_print_required')
    source,candidate=[Path(p).resolve(strict=True)for p in(source,candidate)]
    paths=[source]+[Path(p['candidate']).resolve(strict=True)for p in phases]
    if (candidate!=paths[-1]or len({(p.stat().st_dev,p.stat().st_ino)for p in paths})!=len(paths)
            or any(force._hash(path)!=row['candidate_sha256']for path,row in zip(paths[1:],phases))):
        raise ValueError('exact_distinct_saved_macro_chain_endpoints_required')
    families=[force._family(p,board_hint)for p in paths];code=force._code_identity()
    result=dict(scope='bounded_immediate_Source_macro_contact_chain',
        comparison_complete=False,same_evidence=False,macro_boundaries=[],
        independently_received_prefix_phases=[],independently_received_suffix_phases=[],
        source=str(source),source_sha256=force._hash(source),
        candidate=str(candidate),candidate_sha256=force._hash(candidate),
        macro_pose_or_input_repair_authority_not_applied_to_prefix_or_suffix=True,
        full_kelvin_qualification=False,release_authority=False)

    def typed(parent,index):
        row=phases[index]
        actual,proof=receive_phase(source,parent,row,board_hint,
            assembly_instance=stage.matched_instance(assembly_instance,parent))
        actual=Path(actual).resolve(strict=True)
        if (proof.get('ok')is not True or proof.get('complete')is not True
                or actual!=paths[index+1]or force._hash(actual)!=row['candidate_sha256']):
            raise ValueError('fresh_exact_typed_macro_chain_boundary_required')
        return actual,dict(kind=row['kind'],source=str(parent),candidate=str(actual),
            candidate_sha256=row['candidate_sha256'],receiving=proof)

    def strict_gap(left,right,before,after):
        started=time.monotonic()
        boards=[pcbnew.LoadBoard(str(p))for p in(left,right)]
        nets=changed_native_nets(*boards);manifest=contact_manifest(*boards,nets)
        proof=strict_contact_transition(before,after,nets,manifest)
        if time.monotonic()-started>10.:
            raise ValueError('native_macro_chain_strict_link_deadline')
        return proof,nets,manifest

    parent=source
    for index in range(indices[0]):
        parent,proof=typed(parent,index)
        result['independently_received_prefix_phases'].append(proof)
    before_path=source;before_raw=evidence[0]
    for index in indices:
        phase=phases[index];boundary=paths[index+1]
        received=macro_contact.receive(parent,boundary,board_hint=board_hint,
            macro_options=phase['options'],timeout_s=10.)
        row=dict(phase_index=index,source=str(parent),source_sha256=force._hash(parent),
            candidate=str(boundary),candidate_sha256=phase['candidate_sha256'],macro=received)
        result['macro_boundaries'].append(row)
        if not all(received.get(k)is True for k in('ok','complete','comparison_complete','same_evidence',
                'source_candidate_families_and_code_unchanged')):
            return result
        raw=received.get('raw_native_evidence')
        if type(raw)is not list or len(raw)!=2:
            raise ValueError('two_actual_raw_saved_macro_evidence_endpoints_required')
        match,nets,manifest=strict_gap(before_path,parent,before_raw,raw[0])
        row.update(source_evidence_match=match,strict_prefix_actual_modified_nets=nets,
            strict_prefix_native_copper_transforms=manifest)
        if not all(match.get(k)is True for k in('comparison_complete','same_evidence')):
            return result
        before_path=boundary;before_raw=raw[1];parent=boundary
    for index in range(indices[-1]+1,len(phases)):
        parent,proof=typed(parent,index)
        result['independently_received_suffix_phases'].append(proof)
    remainder,nets,manifest=strict_gap(before_path,candidate,before_raw,evidence[1])
    if (families!=[force._family(p,board_hint)for p in paths]or code!=force._code_identity()):
        raise ValueError('macro_chain_Source_candidate_or_code_changed')
    result.update(strict_macro_boundary_to_final=remainder,
        remainder_actual_modified_nets=nets,remainder_native_copper_transforms=manifest,
        all_immediate_Source_macro_boundaries_received=True,
        source_candidate_families_and_code_unchanged=True,
        comparison_complete=remainder.get('comparison_complete')is True,
        same_evidence=remainder.get('comparison_complete')is True and remainder.get('same_evidence')is True)
    return result


def complete_macro_contact_transition(source,candidate,phases,evidence,*,board_hint,assembly_instance=None):
    """Proof by exact saved boundaries, not a final net/pose allowlist.

    A macro owns ONLY its immediate saved parent's rigid-cell input replay.
    A preceding cooperative preclear must independently pass its exact typed
    saved receiver AND strict original-to-preclear contact/cut preservation.
    Later saved deltas owe strict macro-boundary-to-final comparison unless
    their own fresh typed measurement receiver derives an exact input repair
    and the existing absolute AFTER comparator independently accepts it.
    No prefix or suffix inherits macro pose normalization/repair authority.
    """
    kinds=validate_phases(phases)
    if kinds.count('complete_macro')==MAX_COMPLETE_MACROS:
        return complete_macro_chain_contact_transition(source,candidate,phases,evidence,
            board_hint=board_hint,assembly_instance=assembly_instance)
    if kinds.count('complete_macro')!=1:
        raise ValueError('one_exact_macro_contact_boundary_required')
    index=kinds.index('complete_macro');parent=Path(source).resolve()
    prefix=[]
    for row in phases[:index]:
        actual,proof=receive_phase(source,parent,row,board_hint,
            assembly_instance=stage.matched_instance(assembly_instance,parent))
        if proof.get('ok')is not True or proof.get('complete')is not True:
            raise ValueError('independently_received_macro_prefix_required')
        actual=Path(actual).resolve(strict=True)
        if actual!=Path(row['candidate']).resolve(strict=True)or force._hash(actual)!=row['candidate_sha256']:
            raise ValueError('exact_received_macro_prefix_endpoint_required')
        prefix.append(dict(kind=row['kind'],source=str(parent),candidate=str(actual),receiving=proof))
        parent=actual
    phase=phases[index];boundary=Path(phase['candidate']).resolve(strict=True)
    if force._hash(boundary)!=phase['candidate_sha256']:
        raise ValueError('macro_contact_boundary_changed')
    received=macro_contact.receive(parent,boundary,board_hint=board_hint,
        macro_options=phase['options'],timeout_s=10.)
    result=dict(comparison_complete=False,same_evidence=False,macro=received,
        full_kelvin_qualification=False,release_authority=False)
    if not received.get('ok')or not received.get('complete'):return result
    # The actual prefix receives only the original strict contour/contact
    # comparator. Do not normalize old raw witnesses to the macro pose or
    # allow that macro to repair inherited prefix debt retroactively.
    prefix_nets=[];prefix_manifest=[]
    if prefix:
        first,last=[pcbnew.LoadBoard(str(p))for p in(source,parent)]
        prefix_nets=changed_native_nets(first,last)
        prefix_manifest=contact_manifest(first,last,prefix_nets)
    window_operations={'source_contained_ground_window':'ground_island_join',
        'source_local_return_window':'ground_local_return',
        'source_ordinary_signal_window':'ordinary_signal'}
    if len(prefix)==1 and prefix[0]['kind'] in window_operations:
        # A checked antipad changes a literal power-fill fingerprint. It
        # cannot inherit the following cell's input-repair permission.
        # Re-receive this exact prefix and absolutely revalidate ONLY its
        # originally verified affected cuts, with strict unknown peers and
        # all guards/model/witness topology retained. Link both raw endpoints
        # independently to the caller and the immediate macro Source.
        first=phases[0]
        checked=window_contact.receive(source,parent,board_hint=board_hint,
            pad_uuid=first['pad_uuid'],operation=window_operations[first['kind']],
            **({'position_nm':first['position_nm']}if first['kind']=='source_ordinary_signal_window'else{}),
            timeout_s=10.)
        if checked.get('ok')is not True or checked.get('complete')is not True:
            raise ValueError('independent_checked_window_prefix_contacts_required:'+repr(checked.get('errors')))
        raw=checked['raw_native_evidence']
        links=[strict_contact_transition(evidence[0],raw[0],[],[]),
            strict_contact_transition(raw[1],received['raw_native_evidence'][0],[],[])]
        source_match=dict(comparison_complete=all(q.get('comparison_complete')is True for q in links),
            same_evidence=checked['same_evidence']is True and all(q.get('same_evidence')is True for q in links),
            independent_checked_window=checked,strict_raw_saved_endpoint_links=links,
            raw_prefix_fingerprints_not_assumed_equal=True,full_kelvin_qualification=False,
            release_authority=False)
    else:
        source_match=strict_contact_transition(evidence[0],received['raw_native_evidence'][0],
            prefix_nets,prefix_manifest)
    last_macro,child=[pcbnew.LoadBoard(str(p))for p in(boundary,candidate)]
    nets=changed_native_nets(last_macro,child);manifest=contact_manifest(last_macro,child,nets)
    suffix=phases[index+1:]
    if {'isolated_measurement_join','measurement_quiet_fanout'}.intersection(kinds[index+1:]):
        # Compose the existing receiver on ONLY the actual saved suffix. It
        # re-receives each boundary and derives its manufacturer input leg;
        # the macro cannot supply a leg/net allowlist or repair permission.
        remainder=isolated_measurement_contact_transition(boundary,candidate,suffix,
            [received['raw_native_evidence'][1],evidence[1]],board_hint=board_hint,
            assembly_instance=stage.matched_instance(assembly_instance,boundary))
        if type(remainder)is not dict:
            raise ValueError('independently_received_macro_measurement_suffix_required')
        result.update(independently_received_measurement_suffix=remainder,
            macro_boundary_to_final_comparison='fresh_typed_measurement_absolute_after')
    else:
        remainder=strict_contact_transition(received['raw_native_evidence'][1],evidence[1],nets,manifest)
        result.update(strict_macro_boundary_to_final=remainder,
            macro_boundary_to_final_comparison='strict_native_contact_preservation')
    result.update(source_evidence_match=source_match,
        independently_received_prefix_phases=prefix,actual_macro_parent=str(parent),
        strict_prefix_actual_modified_nets=prefix_nets,strict_prefix_native_copper_transforms=prefix_manifest,
        macro_pose_or_input_repair_authority_not_applied_to_prefix_or_suffix=True,
        remainder_actual_modified_nets=nets,remainder_native_copper_transforms=manifest,
        comparison_complete=all(q.get('comparison_complete')is True for q in(source_match,remainder)),
        same_evidence=all(q.get('same_evidence')is True for q in(source_match,remainder)))
    return result


def saved_craft(path,out,*,board_hint):
    """Fresh native ownership per saved file; a crash is a refused gate.

    Never reuse an old SWIG BOARD after the long native/annotation/intake
    session. This is the SAME unscoped whole-board quality analyzer, with
    identical default angles/heading tolerance and no ignored findings.
    """
    path=Path(path).resolve(strict=True);out=Path(out)
    assert not out.exists(),'fresh_isolated_craft_receipt_required'
    epoch=force._code_identity();family=force._family(path,board_hint)
    worker='''import faulthandler,json,sys
faulthandler.enable()
from pathlib import Path
import pcbnew
import cec_swig_guard
cec_swig_guard.pin()
import wx
quiet=wx.LogNull()
import cec_force_current as force
import cec_route_quality as quality
path,out=map(Path,sys.argv[1:3]);hint=sys.argv[3]
family=force._family(path,hint);code=force._code_identity()
report=quality.analyze(str(path))
assert family==force._family(path,hint)and code==force._code_identity()
force._write(out,dict(complete=True,source=str(path),source_family=family,code_identity=code,
    source_and_code_unchanged=True,report=report))
'''
    try:
        process=subprocess.run([sys.executable,'-c',worker,str(path),str(out),board_hint],
            stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=10.)
    except subprocess.TimeoutExpired as exc:
        force._write(out.with_suffix('.failure.json'),dict(complete=False,reason='native_craft_worker_timeout',
            timeout_s=10.,release_authority=False))
        raise ValueError('isolated_saved_craft_timed_out')from exc
    if process.returncode!=0 or not out.is_file():
        force._write(out.with_suffix('.failure.json'),dict(complete=False,
            reason='native_craft_worker_refused_or_crashed',exit_code=process.returncode,
            output_tail=process.stdout[-8000:],release_authority=False))
        raise ValueError('isolated_saved_craft_worker_refused_or_crashed')
    proof=json.loads(out.read_text())
    if (proof.get('complete')is not True or proof.get('source')!=str(path)
            or proof.get('source_family')!=family or proof.get('code_identity')!=epoch
            or proof.get('source_and_code_unchanged')is not True
            or family!=force._family(path,board_hint)or epoch!=force._code_identity()
            or proof.get('report',{}).get('board')!=str(path)
            or any(type(proof['report'].get(k))is not int or proof['report'][k]<0
                for k in('issue_count','non_octilinear_count'))):
        raise ValueError('fresh_bound_whole_saved_craft_report_required')
    return proof


def print_dependencies():
    global print_transition,print_op,print_runtime,print_origin
    import cec_print_context_transition as print_transition
    import cec_chained_annotation_transition as print_origin
    import cec_nonpolar_print_context as print_op
    import cec_optional_body_ink_contract as body
    # Exact sibling helper, not an ambient module with a matching filename.
    import importlib.util
    helper=Path(__file__).resolve().with_name('typed_print_runtime.py')
    spec=importlib.util.spec_from_file_location('cec_transaction_print_runtime',helper)
    print_runtime=importlib.util.module_from_spec(spec);spec.loader.exec_module(print_runtime)
    return {str(Path(m.__file__).resolve()):force._hash(Path(m.__file__))
        for m in(print_transition,print_origin,print_op,print_op.ink,print_op.ink.frame,body,print_runtime)}


def print_declaration(parent,row):
    return dict(source=dict(path=str(parent),sha256=force._hash(parent)),
        proposal=dict(path=str(Path(row['proposal']).resolve(strict=True)),sha256=force._hash(Path(row['proposal']))))


def receive_print_phase(parent,row,board_hint,assembly_instance=None):
    """Explicit public fresh-origin composition, never reuse an old grade.

    Default direct receiving is unchanged. The opt-in public replay has
    separately bounded native, map, plan, construction and live phases; it
    independently recreates the complete actual saved family. It is not a
    retry, an extended per-check lease or caller-supplied library authority.
    """
    validate_phases([row]);print_dependencies()
    operation=print_origin.receive_print_row if row.get('replay_origin',False) else print_transition.receive_row
    return operation(Path(row['candidate']).resolve(strict=True),print_declaration(parent,row),
        board_hint=board_hint,assembly_instance=assembly_instance,timeout_s=10.)


def same_print_phase(left,right,row):
    return (print_origin.same_print_replay(left,right) if row.get('replay_origin',False)
        else print_transition.same_replay(left,right))


def selected_source_annotation(source,row,*,board_hint,kinds):
    """Receive a selected private print context, never infer one from its URI.

    A material descendant must independently construct its own last print
    phase. The ancestor's context does not silently grant candidate authority.
    """
    if annotations.kind(row)is None:return None
    if 'print_context'not in kinds:
        raise ValueError('typed_source_requires_explicit_candidate_print_context')
    proof=annotations.receive_row(source,row,board_hint=board_hint,timeout_s=10.)
    if proof.get('ok')is not True or proof.get('complete')is not True:
        raise ValueError('selected_source_annotation_not_independently_received:'+str(proof.get('error')))
    return proof


def receive_phase(original,parent,row,hint,*,assembly_instance=None):
    if row.get('kind')in('source_connector_feedthrough','source_connector_native_frontier',
            'source_series_resistor_monitor_tap','source_series_resistor_monitor_local_tap',
            'connected_footprint_pose','source_ordinary_resistor_reference_pose',
            'measurement_auxiliary_input_join','quiet_signal_join','source_ordinary_signal_window',
            'source_ordinary_barrel_kernel','source_aggregate_capacitor_cell','source_rc_elbow_reflow',
            'redundant_source_ground_link'):
        # Standalone phase dispatch also rejects injected authority fields;
        # the complete transaction still validates sequence and all16 gates.
        validate_phases([row])
    child=Path(row['candidate']).resolve(strict=True)
    assert force._hash(child)==row['candidate_sha256']and child!=parent
    kind=row['kind']
    if kind in('source_connector_feedthrough','source_connector_native_frontier',
            'source_series_resistor_monitor_tap','source_series_resistor_monitor_local_tap',
            'connected_footprint_pose','source_ordinary_resistor_reference_pose',
            'measurement_auxiliary_input_join','quiet_signal_join','source_ordinary_signal_window',
            'source_ordinary_barrel_kernel','source_aggregate_capacitor_cell','source_rc_elbow_reflow',
            'redundant_source_ground_link'):
        if child.samefile(parent):raise ValueError('distinct_saved_Source_sideband_files_required')
    if kind=='complete_macro':
        options=dict(row['options']);assert options.pop('board_hint',hint)==hint
        result=macro.receive(parent,child,board_hint=hint,**options)
    elif kind=='auxiliary_attachment':
        # Identity only. Fresh Source policy/export/native topology owns the
        # exact minimum conductor geometry; aggregate current is unchanged.
        result=auxiliary_attachment.receive(parent,child,row['attachment_id'],
            board_hint=hint,timeout_s=10.)
    elif kind=='source_class_ground_tail':
        plan=source_ground_tail.plan(pcbnew.LoadBoard(str(parent)),parent,row['seed_uuid'],
            allow_locked_track_uuids=row['allow_locked_track_uuids'],timeout_s=10.)
        result=source_ground_tail.receive(parent,child,plan,board_hint=hint,timeout_s=10.)
    elif kind=='source_ground_literal_endpoint_tail':
        # Discover the WHOLE literal Source branch before accounting for
        # copper contacts. Each real external boundary must still be a
        # retained native reference landing; cap overlaps do not grant cuts.
        plan=source_ground_literal_tail.plan(pcbnew.LoadBoard(str(parent)),parent,row['seed_uuid'],
            allow_locked_track_uuids=row['allow_locked_track_uuids'],timeout_s=10.)
        result=source_ground_literal_tail.receive(parent,child,plan,board_hint=hint,timeout_s=10.)
    elif kind=='source_ground_land_root_spur':
        # The seed is discovery input, never a caller-supplied cut or role.
        # Re-prove the entire dead branch, every actual boundary and its
        # retained source land/reference component from this saved parent.
        plan=source_ground_land_spur.plan(pcbnew.LoadBoard(str(parent)),parent,row['seed_uuid'],
            allow_locked_track_uuids=row['allow_locked_track_uuids'],timeout_s=10.)
        result=source_ground_land_spur.receive(parent,child,plan,board_hint=hint,timeout_s=10.)
    elif kind=='redundant_source_ground_link':
        # Literal identities only. The public receiver freshly derives
        # the whole Source link, both independent roots and every retained
        # partition/known return. Four explicit constituents, not an outer
        # plan or a producer proof; each actual lease remains <=10 seconds.
        result=redundant_ground_link.receive(parent,child,board_hint=hint,
            track_uuids=row['track_uuids'],timeout_s=10.,
            receiving_phase_timeouts_s=(10.,10.,10.,10.))
    elif kind=='rated_branch':
        result=rated_branch.receive(parent,child,board_hint=hint,
            retired_track_uuids=row['retired_track_uuids'],timeout_s=10.,**row['options'])
    elif kind=='source_pad_bank':
        proposal=json.loads(Path(row['proposal']).read_text())
        result=pad_bank_stage.receive(parent,child,proposal,zone_uuid=row['zone_uuid'],
            board_hint=hint,timeout_s=10.)
    elif kind=='source_aggregate_capacitor_cell':
        proposal=json.loads(Path(row['proposal']).read_text())
        if proposal.get('board_hint')!=hint:
            raise ValueError('Source_aggregate_capacitor_phase_board_identity_changed')
        # Canonical unassigned ceramic, unchanged aggregate rail current,
        # closed Source map and both physical paths are freshly recompiled.
        # No caller load/width/parts/cut/role or placement-grade fields.
        result=aggregate_capacitor.receive(parent,child,proposal,timeout_s=10.)
    elif kind=='source_rc_elbow_reflow':
        # Only the literal Source land and three discovery IDs are input.
        # Fresh canonical topology, complete native contact apertures, exact
        # Source subtraction and the saved replacement own every permission.
        result=source_rc_elbow.receive(parent,child,board_hint=hint,
            pad_uuid=row['pad_uuid'],span_uuids=row['span_uuids'],timeout_s=10.)
    elif kind=='retained_passive_pose':
        proposal=json.loads(Path(row['proposal']).read_text())
        assert proposal.get('board_hint')==hint,'passive_pose_phase_board_hint_changed'
        # Exact Source reconstruction retains every track/arc and forbids
        # new conductors. Only re-proved own Ground barrels and an explicit
        # closed reference map may follow the bounded passive poses.
        result=retained_passive_pose.receive(parent,child,proposal,timeout_s=10.)
    elif kind=='complete_current_passive_cell':
        proposal=json.loads(Path(row['proposal']).read_text())
        if proposal.get('board_hint')!=hint:
            raise ValueError('complete_current_passive_phase_board_identity_changed')
        # Current, Source/isolation, exact native pose, every original
        # partition and both mandatory full-current named port connections
        # are freshly rederived. No caller width/current/role is a field.
        result=current_passive_cell.receive(parent,child,proposal,timeout_s=10.)
    elif kind=='full_current_planar_reflow':
        # Existing complete Source current authority only; unchanged exact
        # width and face, all old boundaries, no barrel/pour/pose changes.
        result=full_current_planar.receive(parent,child,board_hint=hint,
            retired_track_uuids=row['retired_track_uuids'],timeout_s=10.)
    elif kind=='ordinary_barrel_reseat':
        result=ordinary_barrel.receive(parent,child,board_hint=hint,
            via_uuid=row['via_uuid'],timeout_s=10.)
    elif kind=='source_ordinary_barrel_reseat':
        # Distinct explicit Source reconstruction, not an unlock operation.
        # The public receiver freshly derives the complete ordinary kernel
        # from this one old native identity. Every actual incident departure,
        # all surviving partitions, full project-sized barrel, old boundary,
        # literal cut and saved addition must replay. No caller lock list,
        # material scope, current, sizing or process permission is accepted.
        result=ordinary_barrel.receive(parent,child,board_hint=hint,
            via_uuid=row['via_uuid'],allow_owned_locked=True,timeout_s=10.)
    elif kind=='source_ordinary_barrel_kernel':
        # Fresh Source native contacts, not caller cut/lock/dimension lists.
        # Includes real tees under the existing exclusive ordinary receiver;
        # the endpoint-only barrel owner remains unchanged.
        result=ordinary_kernel.receive(parent,child,board_hint=hint,
            via_uuid=row['via_uuid'],timeout_s=10.)
    elif kind=='distributed_supply_join':
        # Existing complete Source load, actual full-width/prefix graph and
        # strict native component gain; caller names supply no numeric role.
        result=distributed_supply.receive(parent,child,board_hint=hint,net=row['net'],timeout_s=10.)
    elif kind=='source_local_bypass_return':
        # All ownership, complete Source width/cut, literal existing local
        # pad rule, native membership, reference contacts, short returns and
        # exact saved replay are freshly recompiled. No geometry/process/
        # current override is a phase field.
        with force._thermal_hint(hint):
            result=bypass_return.receive(parent,child,board_hint=hint,pad_uuid=row['pad_uuid'],
                track_uuid=row['track_uuid'],timeout_s=10.,allow_owned_locked=True,
                allow_qualified_local_vias=True,source_full_class=True,source_local_pad_entry=True)
    elif kind=='ordinary_join':
        # Public receiver independently rederives eligibility, exact Source
        # endpoints, authored dimensions, literal additions and connectivity.
        # A worker receipt, producer boolean or caller role is not authority.
        result=ordinary_join.receive(parent,child,board_hint=hint,net=row['net'],timeout_s=10.)
    elif kind=='monitor_divider_ground_return':
        result=monitor_ground.receive(parent,child,board_hint=hint,
            ground_pad_uuid=row['pad_uuid'],timeout_s=10.)
    elif kind=='quiet_input_pad_cleanup':
        # Source-owned physical-union equality only. No caller cuts/locks,
        # role waiver or repair-leg authority is inherited by the fanout.
        result=quiet_pad_cleanup.receive(parent,child,board_hint=hint,
            input_pad_uuid=row['input_pad_uuid'],peer_pad_uuid=row['peer_pad_uuid'],timeout_s=10.)
    elif kind in('ordinary_reflow','ordinary_source_reflow'):
        # One finite, literal Source net; never a role, worker success flag or
        # permission to retire a supply/pair/ground/measurement conductor.
        cuts=ordinary_reflow._ids(row['retired_track_uuids'],'exact_local_ordinary_source_cut',8)
        if not cuts:raise ValueError('nonempty_exact_local_ordinary_source_cut_required')
        before=pcbnew.LoadBoard(str(parent));after=pcbnew.LoadBoard(str(child))
        old_tracks={force._uid(t):t for t in before.GetTracks()}
        if (not cuts<=old_tracks.keys()or any(str(old_tracks[u].GetNetname())!=row['net']for u in cuts)):
            raise ValueError('ordinary_reflow_cut_must_equal_requested_source_net')
        old_nodes=additive._nodes(parent)[1];new_nodes=additive._nodes(child)[1]
        incoming=[t for t in after.GetTracks()if force._uid(t)in new_nodes.keys()-old_nodes.keys()]
        if not 1<=len(incoming)<=64 or any(str(t.GetNetname())!=row['net']for t in incoming):
            raise ValueError('ordinary_reflow_additions_must_equal_requested_source_net')
        options={}
        if kind=='ordinary_source_reflow':
            locks=ordinary_reflow._ids(row['allow_locked_track_uuids'],'exact_ordinary_Source_locks',8)
            if locks!={u for u in cuts if old_tracks[u].IsLocked()}:
                raise ValueError('lock_scope_must_equal_actual_selected_ordinary_Source_locks')
            # Source-generated route locks are not a role waiver. The
            # existing public receiver still independently types EVERY cut,
            # refuses groups/power/pairs/ground/unknown owners and restores
            # every actual native boundary and surviving partition.
            options['allow_locked_track_uuids']=row['allow_locked_track_uuids']
        result=ordinary_reflow.receive(parent,child,retired_track_uuids=row['retired_track_uuids'],
            board_hint=hint,timeout_s=10.,**options)
    elif kind=='can_endpoint_join':
        # Canonical CANH/CANL pins, real series lands, authored CAN class,
        # literal surface additions and actual native join rederive afresh.
        # Not ordinary routing or a grant of new pair-performance approval.
        result=can_join.receive(parent,child,board_hint=hint,net=row['net'],timeout_s=10.)
    elif kind=='quiet_signal_join':
        # Manufacturer-defined output and ADC-capable input roles, literal
        # saved Sense-class copper and a rooted native join are recompiled.
        # This is not ordinary routing, a force pickup or ADC qualification;
        # all original-parent current/field/contact/native gates still run.
        result=quiet_signal_join.receive(parent,child,board_hint=hint,
            net=row['net'],timeout_s=10.)
    elif kind=='isolated_measurement_join':
        # This is NOT an ordinary or whole-force-net join. Recompile the
        # actual input pin, its ratified front-only Kelvin policy, complete
        # nonbranching incoming chain and exact original shunt aperture.
        # All original-parent contact/current/native gates still run below.
        result=measurement_join.receive(parent,child,board_hint=hint,
            pad_uuid=row['pad_uuid'],timeout_s=10.,path_length_budget_nm=row.get(
                'path_length_budget_nm',measurement_join.MAX_PATH_LENGTH_NM))
    elif kind=='measurement_auxiliary_input_join':
        # A package-local, manufacturer-declared same-net strap is not an
        # external Kelvin pickup, whole-net force route or permission to
        # accept a bad retained shunt departure. All parent gates below
        # still independently receive the actual saved board.
        import cec_source_measurement_auxiliary_join as auxiliary_input_join
        result=auxiliary_input_join.receive(parent,child,board_hint=hint,
            paired_pad_uuid=row['paired_pad_uuid'],timeout_s=10.)
    elif kind=='measurement_quiet_fanout':
        # Same exact Source shunt, an immutable positively typed quiet tree,
        # and one actual input land/degree-two Source endpoint. No whole-net
        # target, arbitrary track interior, role, layer or current override.
        result=measurement_fanout.receive(parent,child,board_hint=hint,
            pad_uuid=row['pad_uuid'],peer_pad_uuid=row['peer_pad_uuid'],timeout_s=10.)
    elif kind=='source_connector_feedthrough':
        # Existing plated lands only. Source remap, exact selected parts,
        # nonpower channel, actual annular contact and native k -> k-1 join
        # are recompiled; no Default/passive/current reclassification.
        result=connector_feedthrough.receive(parent,child,board_hint=hint,
            pad_uuids=row['pad_uuids'],timeout_s=10.,
            **({'allow_nonplane_power_role':row['allow_nonplane_power_role']}
                if 'allow_nonplane_power_role'in row else{}))
    elif kind=='source_connector_native_frontier':
        # Distinct from direct connector contact: two positively compiled
        # old connector islands and two exact retained native access objects.
        # No new barrel, Source cut, role, geometry or process override.
        result=connector_feedthrough.receive_native_frontier(parent,child,board_hint=hint,
            pad_uuids=row['pad_uuids'],access_uuids=row['access_uuids'],timeout_s=10.,
            **({'allow_nonplane_power_role':row['allow_nonplane_power_role']}
                if 'allow_nonplane_power_role'in row else{}))
    elif kind in('source_series_resistor_monitor_tap','source_series_resistor_monitor_local_tap'):
        # Fresh selected resistor/GPIO and canonical connector-backbone proof,
        # exact additive receiving including native Ground-fill replay. This
        # is neither ordinary/quiet reclassification nor a current waiver.
        result=sideband_monitor_tap.receive(parent,child,board_hint=hint,
            connector_pad_uuids=row['connector_pad_uuids'],target_pad_uuid=row['target_pad_uuid'],
            timeout_s=10.,
            **({'allow_source_local_pofv':True}if kind=='source_series_resistor_monitor_local_tap'else{}))
    elif kind=='connected_footprint_pose':
        # Existing connected-pose receiving restores every original contact
        # and native partition. No Ground, group, neckdown or cut opt-in.
        import cec_pose_additive_reconstruction as connected_pose
        result=connected_pose.receive(parent,child,board_hint=hint,
            selected_footprint_uuids=row['footprint_uuids'],max_shift_mm=8.,timeout_s=10.)
    elif kind=='source_ordinary_resistor_reference_pose':
        # Fresh canonical ordinary resistor and exact closed Source ink only.
        # This never borrows the independent Ground-barrel transport tier.
        import cec_pose_additive_reconstruction as connected_pose
        result=connected_pose.receive(parent,child,board_hint=hint,
            selected_footprint_uuids=[row['footprint_uuid']],max_shift_mm=6.,
            reference_group_uuids=[row['reference_group_uuid']],
            allow_source_ordinary_resistor_reference_maps=True,timeout_s=10.)
    elif kind=='existing_local_ground_entry':
        # Reuse only an already authored exact-object process rule. A caller
        # cannot ask this phase to create a Ground-width/process exception.
        # These four checks are separately bounded, not one borrowed 40s
        # native lease. Source/delta/partitions/all-return proofs all remain.
        result=ground_entry.receive(parent,child,board_hint=hint,pad_uuid=row['pad_uuid'],
            use_existing_local_pad_rule=True,timeout_s=10.,
            receiving_phase_timeouts_s=(10.,10.,10.,10.))
    elif kind=='source_contained_ground_window':
        # Explicit checked local-window policy, not the default frozen-pour
        # search. Only a literal Source Ground land identity enters this
        # schema; the saved public receiver independently derives the exact
        # existing process, every native antipad and zero-length return.
        # No caller polygon, width, current or relaxed native gate is allowed.
        result=ground_window.receive(parent,child,board_hint=hint,pad_uuid=row['pad_uuid'],
            timeout_s=10.)
    elif kind=='source_local_return_window':
        # A separate explicit purpose: all old native partitions IDENTICAL,
        # absent/nonlocal Source return -> exact 0 mm Source-pad return.
        # No native-open progress or power/current qualification is inferred.
        result=ground_window.receive(parent,child,board_hint=hint,pad_uuid=row['pad_uuid'],
            purpose='local_return_completion',timeout_s=10.)
    elif kind=='source_ordinary_signal_window':
        # A literal Source land and proposed axis only. The public receiver
        # derives ordinary role, full dimensions, no Source surface crossing,
        # exact local native antipads and every unchanged Source partition.
        # No power/pair/Kelvin membership or caller polygon is admitted.
        result=signal_window.receive(parent,child,board_hint=hint,pad_uuid=row['pad_uuid'],
            position_nm=row['position_nm'],timeout_s=10.)
    elif kind=='source_local_ground_dogbone':
        # Axis only: never caller-supplied width, drill, current, local
        # exemption or power window. Recompile full ordinary Source GND
        # class/factory geometry and every reference-plane contact.
        result=ground_entry.receive(parent,child,board_hint=hint,pad_uuid=row['pad_uuid'],
            dogbone_position_nm=row['position_nm'],use_existing_local_pad_rule=False,timeout_s=10.,
            receiving_phase_timeouts_s=(10.,10.,10.,10.))
    elif kind=='source_local_ground_polyline':
        # Only an exact two-leg proposal. Source GND width, literal existing
        # local rule, unchanged process/reach, every real limb/plane contact,
        # selected-island join and all saved deltas are independently derived.
        result=ground_entry.receive(parent,child,board_hint=hint,pad_uuid=row['pad_uuid'],
            dogbone_points_nm=row['points_nm'],use_existing_local_pad_rule=True,timeout_s=10.,
            receiving_phase_timeouts_s=(10.,10.,10.,10.))
    elif kind=='coowned_input_control_ground':
        # Not a low-power alias: recompile every co-owned control and input
        # capacitor terminal, retain full Source GND class and all original
        # copper/part/partition/return gates. No new barrel or current budget.
        result=coowned_ground.receive(parent,child,board_hint=hint,
            pad_uuid=row['pad_uuid'],timeout_s=10.)
    elif kind=='distributed_supply_layer_join':
        # A distinct zero-cut distributed owner, never empty retirement fed
        # to a force replacement. Barrel capacity remains unknown; every
        # full original-parent current/field/Kelvin/native gate still runs.
        result=distributed_layer_join.receive(parent,child,board_hint=hint,net=row['net'],
            pad_uuids=row['pad_uuids'],timeout_s=10.)
    elif kind=='source_divider_ground_span':
        result=divider_ground.receive(parent,child,board_hint=hint,
            ground_pad_uuid=row['ground_pad_uuid'],retired_track_uuids=row['retired_track_uuids'],
            points_nm=row['points_nm'],timeout_s=10.)
    elif kind=='rc_return_pivot':
        # The public saved receiver derives every actual Source capacitor,
        # its fixed ordinary anchor and formerly isolated Ground land from
        # this immediate parent. No external owner/role/receipt, reach or
        # current-budget override enters the strict transaction schema.
        # Its bounded native pose, local qualified return and original
        # partitions are independently replayed; all final shared gates stay.
        result=rc_return_pivot.receive(parent,child,board_hint=hint,timeout_s=10.)
    elif kind=='ordinary_columns':
        # Independently rederive literal policy barrels, actual native
        # full-current cuts and every single-column loss from the saved pair.
        # A planner/worker receipt is never scope or capacity authority.
        # All actual-parent current/additive/field/return/native gates below
        # still run independently, outside this ten-second geometry phase.
        result=stage.column_scope_receive(parent,child,board_hint=hint,net=row['net'])
    elif kind=='print_context':
        result=receive_print_phase(parent,row,hint,assembly_instance)
    elif kind=='control_shunt_tail':
        result=tails.receive(original,parent,child,board_hint=hint,warning_uuids=row['warning_uuids'],timeout_s=10.)
    elif kind=='macro_tail_cleanup':
        proposal=json.loads(Path(row['proposal']).read_text())
        result=macro_cleanup.receive(original,parent,child,proposal,board_hint=hint,timeout_s=10.)
    elif kind=='equivalent_courtyard':
        proposal=json.loads(Path(row['proposal']).read_text())
        assert proposal.get('board_hint')==hint,'courtyard_phase_board_hint_changed'
        result=equivalent_court.receive(parent,child,proposal,timeout_s=10.)
    elif kind=='detached_passive_translation':
        proposal=json.loads(Path(row['proposal']).read_text())
        assert proposal.get('board_hint')==hint,'passive_phase_board_hint_changed'
        # The exact canonical/physical/literal receiver grants only this
        # detached pose. All original-parent route, current, return, field,
        # contact, stack, parity and native gates remain unchanged below.
        result=detached_passive.receive(parent,child,proposal,timeout_s=10.)
    elif kind=='saved_reference_cleanup':
        proposal=json.loads(Path(row['proposal']).read_text())
        result=reference_cleanup.receive(parent,child,proposal,board_hint=hint)
    elif kind in('reference_fields','reference_map','root_reference_seat','root_caption_seat'):
        proposal=json.loads(Path(row['proposal']).read_text())
        assert proposal.get('board_hint')==hint,'reference_phase_board_hint_changed'
        operation={'reference_fields':fields,'reference_map':maps,'root_reference_seat':root_seats,
            'root_caption_seat':caption_seats}[kind]
        result=operation.receive(parent,child,proposal)
        if kind=='reference_map':
            assert result.get('read_only_legacy_replay')is not True,'legacy_observational_annotation_scope_cannot_authorize_new_repair'
    elif kind=='mechanical_mount':
        proposal=mount.plan(parent,board_hint=hint,mount_uuids=row['mount_uuids'],timeout_s=10.)
        literal=mount.receive(parent,child,board_hint=hint,mount_uuids=row['mount_uuids'],timeout_s=10.)
        physical=mount.receive_physical(parent,child,proposal,timeout_s=10.)
        result=dict(ok=literal['ok']and physical['ok'],complete=literal['complete']and physical['complete'],
            literal=literal,physical=physical)
    else:
        proposal=json.loads(Path(row['proposal']).read_text())
        assert proposal.get('board_hint')==hint,'courtyard_phase_board_hint_changed'
        result=court.receive(parent,child,proposal,board_hint=hint,timeout_s=10.,literal_source=True)
    assert result.get('ok')is True and result.get('complete')is True,result
    return child,result


def reference_query_input_identity(source,candidate,phases,*,board_hint,assembly_instance=None):
    """Narrow pure-Reference relation, never a material-change fallback.

    Freshly receive the actual saved typed phases; imported success flags
    or phase names alone grant nothing. COMPLETE raw/native query inputs
    must match except unique Reference at/effects. Even an otherwise typed
    omitted ink stroke makes this narrower relation refuse. An inherited
    absolute Kelvin unknown remains unknown, not newly qualified.
    """
    kinds=validate_phases(phases)
    if kinds not in(['reference_fields'],['reference_fields','print_context']):return None
    source,candidate=map(lambda p:Path(p).resolve(strict=True),(source,candidate))
    if source==candidate:raise ValueError('distinct_reference_query_endpoints_required')
    cursor=source
    for row in phases:
        cursor,proof=receive_phase(source,cursor,row,board_hint,
            assembly_instance=stage.matched_instance(assembly_instance,cursor))
        if proof.get('ok')is not True or proof.get('complete')is not True:
            raise ValueError('fresh_reference_query_scope_not_received')
    if cursor!=candidate:raise ValueError('exact_reference_query_final_endpoint_required')
    import cec_reference_material_identity as reference_identity
    proof=reference_identity.receive(source,candidate,timeout_s=10.)
    if not(proof.get('ok')is True and proof.get('complete')is True
            and proof.get('comparison_complete')is True and proof.get('same_material')is True
            and proof.get('mutation_authority')is False and proof.get('full_kelvin_qualification')is False):
        raise ValueError('complete_reference_query_input_identity_refused:'+str(proof.get('error')))
    return proof


def print_query_input_identity(source,candidate,phases,*,board_hint):
    """Exact whole raw/native input identity under freshly received ink scope.

    The enclosing transaction must still receive the canonical library
    transition, original-parent current, field, Ground, intake, parity and
    native gates. This relation cannot qualify inherited absolute Kelvin
    unknowns or authorize any silk, physical, route or component change.
    """
    if validate_phases(phases)!=['print_context']:return None
    source,candidate=map(lambda p:Path(p).resolve(strict=True),(source,candidate))
    phase=phases[0]
    if (source==candidate or Path(phase['candidate']).resolve(strict=True)!=candidate
            or force._hash(candidate)!=phase['candidate_sha256']):
        raise ValueError('exact_print_query_final_endpoint_required')
    import cec_nonpolar_print_context as print_op
    import cec_ink_material_identity as material_identity
    proposal=json.loads(Path(phase['proposal']).read_text())
    if proposal.get('board_hint')!=board_hint:
        raise ValueError('exact_print_query_board_hint_required')
    scoped=print_op.receive(source,candidate,proposal,timeout_s=10.)
    if scoped.get('ok')is not True or scoped.get('complete')is not True:
        raise ValueError('fresh_literal_print_scope_not_received:'+str(scoped.get('error')))
    proof=material_identity.receive(source,candidate,timeout_s=10.)
    if not(proof.get('ok')is True and proof.get('complete')is True
            and proof.get('comparison_complete')is True and proof.get('same_material')is True
            and proof.get('ink_authority')is False and proof.get('new_route_authority')is False
            and proof.get('full_kelvin_qualification')is False):
        raise ValueError('complete_print_query_input_identity_refused:'+str(proof.get('error')))
    return proof


def caption_query_input_identity(source,candidate,phases,*,board_hint,assembly_instance=None):
    """Fresh complete caption-only relation, never a general ink exception."""
    kinds=validate_phases(phases)
    if kinds not in(['root_caption_seat'],['root_caption_seat','print_context']):return None
    source,candidate=map(lambda p:Path(p).resolve(strict=True),(source,candidate))
    first=phases[0];middle,_=receive_phase(source,source,first,board_hint,
        assembly_instance=stage.matched_instance(assembly_instance,source))
    proposal=json.loads(Path(first['proposal']).read_text())
    relation=caption_seats.query_input_identity(source,middle,proposal)
    assert all(relation.get(k)is True for k in('ok','complete','comparison_complete','same_material')),relation
    assert relation.get('mutation_authority')is False and relation.get('full_kelvin_qualification')is False
    cursor=middle;print_relation=None
    if len(phases)==2:
        cursor,_=receive_phase(source,middle,phases[1],board_hint,
            assembly_instance=stage.matched_instance(assembly_instance,middle))
        import cec_ink_material_identity as ink_identity
        print_relation=ink_identity.receive(middle,cursor,timeout_s=10.)
        assert all(print_relation.get(k)is True for k in('ok','complete','comparison_complete','same_material')),print_relation
    assert cursor==candidate,'exact_caption_query_final_endpoint_required'
    return dict(ok=True,complete=True,comparison_complete=True,same_material=True,
        scope='fresh_received_root_caption_and_optional_print_query_identity',
        caption=relation,printing=print_relation,mutation_authority=False,
        full_kelvin_qualification=False,inherited_electrical_debt='unchanged_not_evaluated')


def annotation_dependencies():
    return {**fields.dependencies(),**maps.dependencies(),**root_seats.dependencies(),**caption_seats.dependencies(),
        **reference_cleanup.dependencies()}


def equivalent_courtyard_query_input_identity(source,candidate,phases,*,board_hint,assembly_instance=None):
    """Fresh exact equal-court relation, not an absolute Kelvin waiver."""
    kinds=validate_phases(phases)
    if kinds not in(['equivalent_courtyard'],['equivalent_courtyard','print_context']):return None
    source,candidate=map(lambda p:Path(p).resolve(strict=True),(source,candidate))
    first=phases[0];middle,_=receive_phase(source,source,first,board_hint,
        assembly_instance=stage.matched_instance(assembly_instance,source))
    proposal=json.loads(Path(first['proposal']).read_text())
    relation=equivalent_court.query_input_identity(source,middle,proposal,timeout_s=10.)
    assert all(relation.get(k)is True for k in('ok','complete','comparison_complete','same_material')),relation
    assert relation.get('mutation_authority')is False and relation.get('full_kelvin_qualification')is False
    print_relation=None;cursor=middle
    if len(phases)==2:
        cursor,_=receive_phase(source,middle,phases[1],board_hint,
            assembly_instance=stage.matched_instance(assembly_instance,middle))
        import cec_ink_material_identity as ink_identity
        print_relation=ink_identity.receive(middle,cursor,timeout_s=10.)
        assert all(print_relation.get(k)is True for k in('ok','complete','comparison_complete','same_material')),print_relation
        assert print_relation.get('ink_authority')is False and print_relation.get('full_kelvin_qualification')is False
    assert cursor==candidate,'exact_equivalent_courtyard_query_final_endpoint_required'
    return dict(ok=True,complete=True,comparison_complete=True,same_material=True,
        scope='fresh_received_equal_courtyard_and_optional_print_query_identity',
        courtyard=relation,printing=print_relation,mutation_authority=False,
        full_kelvin_qualification=False,inherited_electrical_debt='unchanged_not_evaluated')


def protected_copper_reports(baseline,candidate,*,scope_source,board_hint,phases):
    """Compose an exact leading current repair, never waive a protected net.

    The literal original comparison stays visible. A changed prefix may only
    follow fresh public receiving of the existing whole-current owner; every
    untouched primitive and every replacement remains compulsory. Other
    phase kinds and selected-baseline bridges retain the old strict check.
    """
    frozen=protected.capture(baseline,include_local_authority=False)
    result=dict(source_copper=fr.check_copper_geometry_prefix(str(candidate),frozen),
        qualified_pairs=protected.check_qualified_pairs(candidate,frozen))
    prefix=[]
    for phase in phases:
        if phase['kind']!='full_current_planar_reflow':break
        prefix.append(phase)
    if (not result['source_copper']['ok'] and prefix
            and Path(scope_source).resolve()==Path(baseline).resolve()):
        received=protected_current.receive(baseline,candidate,board_hint=board_hint,
            phases=prefix,timeout_s=10.,per_phase_leases=True)
        result['typed_protected_current_reconstruction']=received
        result['literal_source_copper']=result['source_copper']
        if received.get('ok')is True and received.get('complete')is True:
            result['source_copper']=received['source_copper']
            # Recomputed from the original Source pair contract, not a
            # replacement's self-declared qualification or waiver.
            result['qualified_pairs']=received['qualified_pairs']
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--plan',type=Path,required=True)
    p.add_argument('--board',required=True);p.add_argument('--transaction',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    plan=json.loads(a.plan.read_text());rows={r['board']:r for r in plan['boards']};row=rows[a.board]
    baseline=Path(row['path']).resolve(strict=True);assert force._hash(baseline)==row['sha256']
    transaction=json.loads(a.transaction.read_text());kinds=validate_phases(transaction['phases'])
    original=Path(transaction['scope_source']['path']).resolve(strict=True)
    assert force._hash(original)==transaction['scope_source']['sha256']
    paths=[original,baseline]+[Path(r['candidate']).resolve(strict=True)for r in transaction['phases']]
    assert len(set(paths[2:]))==len(paths[2:])and not set(paths[:2])&set(paths[2:])
    code=force._code_identity();ops=annotation_dependencies();self_hash=force._hash(Path(__file__))
    print_deps=print_dependencies()if 'print_context'in kinds else {}
    source_annotation_deps=annotations.dependencies()if annotations.kind(row)is not None else {}
    families=[force._family(path,a.board)for path in paths];suite={k:force._family(Path(r['path']),k)for k,r in rows.items()}
    inputs={str(q.resolve()):force._hash(q)for q in(a.plan,a.transaction,Path(__file__))}
    for phase in transaction['phases']:
        if 'proposal'in phase:inputs[str(Path(phase['proposal']).resolve())]=force._hash(Path(phase['proposal']))
    result=dict(ok=False,complete=False,source_selected=False,admitted=False,release_authority=False,
        baseline=str(baseline),baseline_sha256=force._hash(baseline),scope_source=str(original),
        scope_source_sha256=force._hash(original),gates={},reports={},phases=[],code_identity=code,inputs=inputs,
        current_qualified=False,full_kelvin_qualification=False,factory_qualified=False,thermal_qualified=False)
    g=result['gates'];q=result['reports'];started=time.monotonic()
    try:
        record_progress(a.out,result,'selected_source_annotation',started)
        source_typed=selected_source_annotation(baseline,row,board_hint=a.board,kinds=kinds)
        if source_typed:q['typed_selected_source']=source_typed
        if original!=baseline:
            bridge=transaction.get('selected_baseline_bridge');assert type(bridge)is dict and set(bridge)=={'mount_uuids'}
            proposal=mount.plan(original,board_hint=a.board,mount_uuids=bridge['mount_uuids'],timeout_s=10.)
            q['selected_baseline_scope']=mount.receive(original,baseline,board_hint=a.board,mount_uuids=bridge['mount_uuids'],timeout_s=10.)
            q['selected_baseline_physical']=mount.receive_physical(original,baseline,proposal,timeout_s=10.)
            assert all(q[k]['ok']and q[k]['complete']for k in('selected_baseline_scope','selected_baseline_physical'))
        else:assert not transaction.get('selected_baseline_bridge')
        cursor=original;print_state=None
        for phase in transaction['phases']:
            record_progress(a.out,result,'typed_'+phase['kind'],started)
            prior=cursor
            prior_instance=stage.matched_instance(row.get('assembly_instance'),prior)
            cursor,proof=receive_phase(original,cursor,phase,a.board,assembly_instance=prior_instance)
            if phase['kind']=='print_context':print_state=(prior,phase,prior_instance,proof)
            result['phases'].append(dict(kind=phase['kind'],candidate=str(cursor),candidate_sha256=force._hash(cursor),receiving=proof))
        candidate=cursor;result.update(candidate=str(candidate),candidate_sha256=force._hash(candidate));g['typed_phases']=True
        source_instance=row.get('assembly_instance');child_instance=stage.matched_instance(source_instance,candidate)
        endpoints=[baseline,candidate];instances=[source_instance,child_instance]
        identities=[source_typed['candidate_identity']if source_typed else stage.identity(baseline,a.board,source_instance),
            print_state[3]['candidate_identity']if print_state else stage.identity(candidate,a.board,child_instance)]
        boards=[pcbnew.LoadBoard(str(path))for path in endpoints];parent,child=boards
        # Every allowed companion delta must already have passed the exact
        # typed macro/factory receiver; no global floor or budget is changed.
        record_progress(a.out,result,'current',started)
        q['current']=current.receive(baseline,candidate,board_hint=a.board)
        g['current']=q['current'].get('ok')is True and q['current'].get('complete')is True
        record_progress(a.out,result,'protected_copper_pairs',started)
        q.update(protected_copper_reports(baseline,candidate,scope_source=original,
            board_hint=a.board,phases=transaction['phases']))
        g['protected_copper_pairs']=q['source_copper']['ok']is True and q['qualified_pairs']['ok']is True
        record_progress(a.out,result,'field',started)
        q['field_geometry_scope']=field_geometry_scope(boards,endpoints)
        snapshots=[coupling.field_coupling_summary(str(baseline),board=parent,board_hint=a.board,
            _work=coupling._ProposalWork(time.monotonic()+10.,16384,1000000,1000000,16384))]
        with tempfile.TemporaryDirectory(prefix='cec-local-transaction-field-')as temp:
            saved=force._copy_family(candidate,Path(temp)/'private-ground-refill');private=pcbnew.LoadBoard(str(saved));additive._ground_refill(private)
            snapshots.append(coupling.field_coupling_summary(str(saved),board=private,board_hint=a.board,
                _work=coupling._ProposalWork(time.monotonic()+10.,16384,1000000,1000000,16384)))
        q['field']=snapshots;g['field']=not(coupling.blocker_keys(snapshots[1])-coupling.blocker_keys(snapshots[0]))
        record_progress(a.out,result,'ground_returns',started)
        q['ground_returns']=returns.receive(parent,child,timeout_s=10.)
        g['ground_returns']=q['ground_returns'].get('ok')is True and q['ground_returns'].get('complete')is True
        record_progress(a.out,result,'contact_kelvin_preservation',started)
        modified_nets=changed_native_nets(parent,child)
        reference_inputs=reference_query_input_identity(baseline,candidate,transaction['phases'],
            board_hint=a.board,assembly_instance=source_instance)
        pure_print=False;pure_courtyard=False;pure_caption=False
        if reference_inputs is None:
            reference_inputs=caption_query_input_identity(baseline,candidate,transaction['phases'],
                board_hint=a.board,assembly_instance=source_instance)
            pure_caption=reference_inputs is not None
        if reference_inputs is None:
            reference_inputs=equivalent_courtyard_query_input_identity(baseline,candidate,transaction['phases'],
                board_hint=a.board,assembly_instance=source_instance)
            pure_courtyard=reference_inputs is not None
        if reference_inputs is None:
            reference_inputs=print_query_input_identity(baseline,candidate,transaction['phases'],board_hint=a.board)
            pure_print=reference_inputs is not None
        if reference_inputs is not None:
            assert not modified_nets,'reference_query_relation_changed_physical_native_nets'
            q['contact_caption_query_identity'if pure_caption else'contact_equivalent_courtyard_query_identity'if pure_courtyard else
                'contact_print_query_identity'if pure_print else'contact_reference_query_identity']=reference_inputs
            q['absolute_kelvin_evaluation']=dict(performed=False,inherited_debt='unchanged_not_evaluated',
                reason=('fresh_reviewed_caption_scope_and_complete_raw_native_query_input_identity'if pure_caption else
                    'fresh_typed_equivalent_courtyard_scope_and_complete_raw_native_query_input_identity'if pure_courtyard else
                    'fresh_typed_pure_print_scope_and_complete_raw_native_query_input_identity'if pure_print else
                    'fresh_typed_pure_reference_scope_and_complete_raw_native_query_input_identity'),
                full_kelvin_qualification=False)
            q['sense']=[]
            q['clipped']=dict(same_evidence=True,comparison_complete=True,
                comparison=('exact_complete_query_inputs_under_fresh_reviewed_caption_scope'if pure_caption else
                    'exact_complete_query_inputs_under_fresh_equal_courtyard_scope'if pure_courtyard else
                    'exact_complete_query_inputs_under_fresh_print_scope'if pure_print else
                    'exact_complete_query_inputs_under_fresh_reference_scope'),
                inherited_debt='unchanged_not_evaluated',full_kelvin_qualification=False)
        else:
            evidence=[sense.replay(path,board_hint=a.board,timeout_s=10.)for path in endpoints];q['sense']=evidence
        manifest=contact_manifest(parent,child,modified_nets)
        q['actual_modified_nets']=modified_nets
        q['native_copper_transform_manifest']=manifest
        if reference_inputs is None:
            q['clipped']=(complete_macro_contact_transition(baseline,candidate,transaction['phases'],evidence,
                board_hint=a.board,assembly_instance=source_instance)if 'complete_macro'in kinds else
                isolated_measurement_contact_transition(baseline,candidate,transaction['phases'],evidence,
                    board_hint=a.board,assembly_instance=source_instance)
                if {'isolated_measurement_join','measurement_quiet_fanout'}.intersection(kinds)else
                strict_contact_transition(*evidence,modified_nets,manifest))
        g['contact_kelvin_preservation']=q['clipped'].get('same_evidence')is True and q['clipped'].get('comparison_complete')is True
        record_progress(a.out,result,'source_and_candidate_intakes',started)
        cfg=synth.Config.load(a.board);intakes,session=stage.receive_intakes(cfg,baseline,candidate,a.out,assembly_instance=source_instance);q.update(intakes)
        for label in('source','candidate'):g[label+'_intake']=q[label+'_intake'].get('ok')is True and q[label+'_intake'].get('intake',{}).get('ok')is True
        build=Path('/home/codex/.cache/cec/native-drc-10.0.5');native_profile=native._describe_build(build);reports=[]
        for label,path,identity in zip(('source','candidate'),endpoints,identities):
            record_progress(a.out,result,'native_'+label,started)
            args={'board_hint':a.board}
            if label=='source'and source_typed:
                record_progress(a.out,result,'post_native_source_annotation',started)
                args=source_typed['candidate_native_arguments']
            if label=='candidate'and print_state:
                record_progress(a.out,result,'post_native_candidate_print',started)
                args=print_state[3]['candidate_native_arguments']
            output=a.out/(label+'-native.json')
            if label=='source'and source_typed or label=='candidate'and print_state:
                producer,preserved=print_runtime.observe(path,a.out/(label+'-runtime'),
                    lambda:native.run(path,output,reporting_build=build,timeout_s=10.,**args))
                q[label+'_runtime_preservation']=preserved
            else:producer=native.run(path,output,reporting_build=build,timeout_s=10.,**args)
            stage.require_native_tool(producer,native_profile);context=producer.get('native_library_context',{})
            assert context.get('bound')is True and context.get('source_and_context_unchanged')is True
            assert stage.stable(context.get('authority'))==identity['native_library_authority']
            q[label+'_native_producer']=producer;reports.append(json.loads(output.read_text()))
            if label=='source'and source_typed:
                live_source=selected_source_annotation(baseline,row,board_hint=a.board,kinds=kinds)
                assert annotations.same_replay(live_source,source_typed),'post_native_selected_source_annotation_changed'
                q['selected_source_annotation_postnative']=live_source
            if label=='candidate'and print_state:
                pp,phase,pi,received=print_state
                live_print=receive_print_phase(pp,phase,a.board,pi)
                q['typed_print_postnative']=live_print
                assert same_print_phase(live_print,received,phase) and live_print['ok']and live_print['complete'],'post_native_typed_print_changed'
        record_progress(a.out,result,'native_delta',started)
        q['native_delta']=stage.native_findings_delta(*reports)
        q['native_counts']=[dict(opens=len(r['unconnected_items']),errors=sum(v['severity']=='error'for v in r['violations']),warnings=sum(v['severity']=='warning'for v in r['violations']),exclusions=len(r.get('excluded_violations',[])))for r in reports]
        old,new=q['native_counts'];g['native']=q['native_delta']['ok']is True and new['opens']<=old['opens']and new['errors']==0 and old['exclusions']==new['exclusions']==0
        q['progress_basis']=dict(native_opens_reduced=new['opens']<old['opens'],
            native_warnings_reduced=new['warnings']<old['warnings'],
            strict_current_fault_objects_reduced=strict_current_repair_progress(q['current']),
            source_courtyard_qualified='qualified_courtyard'in kinds)
        g['progress']=any(v is True for v in q['progress_basis'].values())
        record_progress(a.out,result,'parity',started)
        q['parity']=constraints._chk_sch_pcb_sync(child,str(candidate),{'sch':str(cfg.sch)});g['parity']=q['parity'][0]is True
        record_progress(a.out,result,'craft',started)
        q['saved_craft_receiving']=[saved_craft(path,a.out/(label+'-craft.json'),board_hint=a.board)
            for label,path in zip(('source','candidate'),endpoints)]
        q['craft']=[proof['report']for proof in q['saved_craft_receiving']]
        g['craft']=all(q['craft'][1][k]<=q['craft'][0][k]for k in('issue_count','non_octilinear_count'))
        if print_state:
            record_progress(a.out,result,'final_candidate_print',started)
            pp,phase,pi,received=print_state
            final_print=receive_print_phase(pp,phase,a.board,pi)
            assert same_print_phase(final_print,received,phase) and final_print['ok']and final_print['complete'],'final_typed_print_changed'
            live_identities=[source_typed['candidate_identity']if source_typed else stage.identity(baseline,a.board,source_instance),final_print['candidate_identity']]
            q['typed_print_dependencies']=print_deps
        else:live_identities=[stage.identity(path,a.board,instance)for path,instance in zip(endpoints,instances)]
        if source_typed:
            record_progress(a.out,result,'final_source_annotation',started)
            final_source=selected_source_annotation(baseline,row,board_hint=a.board,kinds=kinds)
            assert annotations.same_replay(final_source,source_typed),'final_selected_source_annotation_changed'
            live_identities[0]=final_source['candidate_identity']
            q['selected_source_annotation_final']=final_source
            q['selected_source_annotation_dependencies']=source_annotation_deps
        record_progress(a.out,result,'final_identity_live',started)
        g['live']=identities==live_identities
        g['all_phase_source_families_live']=families==[force._family(path,a.board)for path in paths]
        g['suite_live']=suite=={k:force._family(Path(r['path']),k)for k,r in rows.items()}
        g['code_and_inputs_live']=code==force._code_identity()and ops==annotation_dependencies()and all(force._hash(Path(p))==sha for p,sha in inputs.items())and self_hash==force._hash(Path(__file__))and(not print_state or print_deps==print_dependencies())and(not source_typed or source_annotation_deps==annotations.dependencies())
        result.update(ok=all(v is True for v in g.values()),complete=True)
    except Exception as exc:result.update(error=str(exc),failure_stack=traceback.format_exc())
    except BaseException as exc:
        result.update(error=type(exc).__name__+':'+str(exc),failure_stack=traceback.format_exc(),
            interrupted=True,ok=False,complete=False)
        raise
    finally:
        result['elapsed_s']=time.monotonic()-started;force._write(a.out/'receiving.json',result)
    print(json.dumps(dict(ok=result['ok'],gates=g,error=result.get('error'),counts=q.get('native_counts'))),flush=True)
    return 0 if result['ok']else 1


if __name__=='__main__':raise SystemExit(main())
