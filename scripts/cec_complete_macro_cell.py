"""Complete source-owned SMD cell/via reconstruction and saved receiving.

Recompile literal source cuts and factory-owned barrel transforms, restore
every old native partition and physical local return, then independently
receive the saved delta. No worker deletion list, guessed current, moved
power bus or weakened fabrication rule is accepted. Whole-board native DRC,
current, field, Kelvin and actual stack receiving are still mandatory.
"""
import math
from pathlib import Path
import tempfile
import time
import traceback

import pcbnew
import cec_additive_route_receiving as additive
import cec_cell_escape_replan as escape
import cec_cell_macro_requests as compiler
import cec_complete_cell_receiving as cell
import cec_field_coupling as field
import cec_force_current as force
import cec_ground_return_preservation as ground
import cec_ordinary_route_receiving as ordinary
import cec_route_quality as craft
import cec_source_no_connect as no_connect


def _reference_requests(proposal):
    rows=proposal['row_plan'];result=[]
    for ref,proof in rows.get('source_reference_group_transports',{}).items():
        first,last=rows['source_poses'][ref],proposal['poses'][ref]
        turn=(last[2]-first[2])%360
        if turn%90:raise ValueError('saved_macro_source_map_exact_cardinal_required')
        result.append((proof,int(turn)//90,tuple(round((last[k]-first[k])*1e6)for k in(0,1))))
    return result


def _cardinal_writer_signature(node):
    """Constructor-only known writer permutations; saved gate stays literal.

    KiCad orders UUID-bearing footprint children by changed world geometry.
    The exact same child inventory must survive; unknown fields/children,
    visibility, geometry and process settings are not ignored.
    """
    import copy
    import cec_source_reference_group_transport as reference
    item=copy.deepcopy(node)
    if item[0]=='gr_text':
        for at in item[1:]:
            if isinstance(at,list)and len(at)==4 and at[0]=='at'and at[3]in('0','0.0','-0','-0.0'):
                del at[3]
    if item[0]=='footprint':
        owned=[];positions=[]
        for index,sub in enumerate(item[1:],1):
            if not isinstance(sub,list):continue
            ids=[v[1]for v in sub[1:]if isinstance(v,list)and len(v)==2 and v[0]=='uuid']
            if not ids:continue
            if len(ids)!=1 or sub[0]not in('property','pad','fp_text','fp_line','fp_arc','fp_poly','fp_rect','fp_circle','fp_curve'):
                raise ValueError('unsupported_cardinal_writer_footprint_child')
            positions.append(index);owned.append((ids[0],sub))
        if len({u for u,n in owned})!=len(owned):raise ValueError('duplicate_cardinal_writer_child')
        for index,(uid,sub)in zip(positions,sorted(owned,key=lambda q:q[0])):item[index]=sub
    return reference._hidden_field_order(item)


def _save_cardinal_reference_nodes(candidate,requests,*,maximum_translation_mm=10.):
    """Restore Source-derived nodes ONLY after exact independent native replay."""
    import cec_source_reference_group_cardinal_batch as cardinal
    import cec_source_retaining_ses_import as raw
    import cec_copper_echo as syntax
    expected=cardinal.expected_nodes(requests,maximum_translation_mm=maximum_translation_mm);candidate=Path(candidate).resolve()
    source=Path(requests[0][0]['source']).resolve()
    if candidate==source:raise ValueError('distinct_private_cardinal_candidate_required')
    actual=additive._nodes(candidate)[1]
    if not set(expected)<=actual.keys():raise ValueError('missing_cardinal_candidate_node')
    for uid,node in expected.items():
        if _cardinal_writer_signature(node)!=_cardinal_writer_signature(actual[uid]):
            raise ValueError('cardinal_candidate_changed_beyond_exact_writer_permutation')
    source_text=raw.raw_text(source);spans=raw.inventory(source_text)
    for uid,node in sorted(expected.items(),key=lambda row:spans[row[0]][0],reverse=True):
        a,z=spans[uid];source_text=source_text[:a]+additive._render(node)+source_text[z:]
    # Normalize BOTH native boards only for an independent physical comparison.
    # Literal expected receiving below never uses this native normalization.
    with tempfile.TemporaryDirectory(prefix='cec-cardinal-macro-save-')as directory:
        path=Path(directory)/'expected.kicad_pcb';raw.write_raw(path,source_text)
        native_expected=pcbnew.LoadBoard(str(path));native_actual=pcbnew.LoadBoard(str(candidate))
        inventories=[]
        for index,board in enumerate((native_expected,native_actual)):
            snap=Path(directory)/(str(index)+'.kicad_pcb');field._save_field_snapshot(board,snap)
            inventories.append({u:_cardinal_writer_signature(n)for u,n in additive._nodes(snap)[1].items()if u in expected})
        if inventories[0]!=inventories[1]:raise ValueError('independent_native_cardinal_saved_map_differs')
    original=raw.raw_text(candidate);spans=raw.inventory(original);text=original
    for uid,node in sorted(expected.items(),key=lambda row:spans[row[0]][0],reverse=True):
        a,z=spans[uid];text=text[:a]+additive._render(node)+text[z:]
    try:
        raw.write_raw(candidate,text)
        saved=additive._nodes(candidate)[1]
        if actual.keys()!=saved.keys()or any(syntax._freeze(saved[u])!=syntax._freeze(expected.get(u,n))for u,n in actual.items()):
            raise ValueError('cardinal_literal_save_changed_unowned_node')
        with tempfile.TemporaryDirectory(prefix='cec-cardinal-macro-check-')as directory:
            path=Path(directory)/'restored.kicad_pcb';field._save_field_snapshot(pcbnew.LoadBoard(str(candidate)),path)
            after={u:_cardinal_writer_signature(n)for u,n in additive._nodes(path)[1].items()if u in expected}
        if after!=inventories[1]:raise ValueError('cardinal_literal_save_changed_native_map')
    except Exception:
        raw.write_raw(candidate,original);raise
    return dict(ok=True,complete=True,restored_source_literal_node_uuids=sorted(expected),
        independent_native_and_exact_writer_inventory_received=True,saved_receiving_not_relaxed=True,
        current_authority=False,routing_admitted=False,release_authority=False)


def screen(source,board,packet,*,board_hint,timeout_s=10.,measurement_bridges=True,
           include_power_layer=True,per_obligation_leases=True,allow_native_ground_refill=True,
           require_trace_craft_nonregression=True,cooperative_conflict_negotiation=False):
    if type(packet) is not dict or packet.get('scope')!='source_typed_complete_native_macro_requests':
        raise ValueError('complete_source_owned_macro_packet_required')
    result=escape.complete_connection_screen(source,board,packet['source_plan'],board_hint=board_hint,
        timeout_s=timeout_s,measurement_bridges=measurement_bridges,include_power_layer=include_power_layer,
        per_obligation_leases=per_obligation_leases,allow_native_ground_refill=allow_native_ground_refill,
        require_trace_craft_nonregression=require_trace_craft_nonregression,source_macro_packet=packet,
        cooperative_conflict_negotiation=cooperative_conflict_negotiation)
    result.update(scope='complete_private_source_owned_macro_connection_screen',
        transported_barrels_are_exact_source_owned_not_new_hole_authority=True)
    return result


def save_private(board,candidate,packet):
    """Native macro save with literal source reference ownership preserved.

    This is construction only. Full saved receiving and the enclosing
    current/field/DRC/stack admission remain independently mandatory.
    """
    if (packet.get('scope')!='source_typed_complete_native_macro_requests'
            or force._hash(Path(packet['source']))!=packet['source_sha256']
            or force._code_identity()!=packet['code_identity']):
        raise ValueError('fresh_source_macro_save_packet_required')
    field._save_field_snapshot(board,candidate)
    result=dict(saved_candidate_authorized=False,routing_admitted=False,release_authority=False)
    proposal=packet['source_plan'];contracts=proposal['row_plan'].get('source_reference_group_transports',{})
    if contracts:
        import cec_source_reference_group_transport as reference
        requests=_reference_requests(proposal)
        if any(turn for proof,turn,delta in requests):
            result['literal_source_reference_save']=_save_cardinal_reference_nodes(candidate,requests,
                maximum_translation_mm=escape.complete_transport_shift_bound(proposal))
        else:result['literal_source_reference_save']=reference.preserve_literal_hidden_field_order(candidate,
            [(proof,delta)for proof,turn,delta in requests],maximum_translation_mm=escape.complete_transport_shift_bound(proposal))
    # Materialized fine-pitch launches can introduce the first actual
    # endpoint group in a Source family. The independent exact replay emits
    # its literal rule too; omitting it here made a valid new device stub
    # depend on whether an unrelated older Source already had that rule.
    # Emission is not qualification: incoming members still owe every
    # bounded endpoint/current/native and saved-replay gate.
    result['local_endpoint_rule']=additive.bind_local_endpoint_rule(board,candidate)
    return result


class _ReceivingLease:
    """An explicit sequence of independently bounded receiving constituents."""
    def __init__(self,seconds,stages):
        self.seconds=seconds;self.stages=tuple(stages);self.index=0;self.timings={}
        self.started=self.phase_started=time.monotonic();self.deadline=self.started+seconds

    def remaining(self):
        left=self.deadline-time.monotonic()
        if left<=0:raise ValueError('saved_complete_macro_'+self.stages[self.index]+'_deadline')
        return min(10.,left)

    def _close_phase(self):
        self.remaining();self.timings[self.stages[self.index]]=time.monotonic()-self.phase_started

    def advance(self,name):
        if self.index+1>=len(self.stages)or self.stages[self.index+1]!=name:
            raise ValueError('explicit_saved_macro_receiving_stage_order_required')
        self._close_phase();self.index+=1
        self.phase_started=time.monotonic();self.deadline=self.phase_started+self.seconds

    def finish(self):
        if self.index!=len(self.stages)-1:raise ValueError('all_saved_macro_receiving_stages_required')
        self._close_phase()
        if time.monotonic()-self.started>=len(self.stages)*self.seconds:
            raise ValueError('saved_complete_macro_total_work_deadline')


def receive(source,candidate,*,board_hint,timeout_s=10.,max_shift_mm=6.,
            allow_owned_locked_escapes=False,rebuild_projected_ground=False,additional_obstacle_track_uuids=(),
            reuse_ground_barrels=(),ordinary_via_poses=(),max_obstacle_track_mm=8.,max_obstacle_tracks=8,
            required_ground_pad_entries=(),stationary_ground_barrel_uuids=(),allow_octilinear_rotations=False,
            required_supply_departures=(),local_signal_port_offsets=(),reference_group_uuids=(),required_ordinary_nets=(),
            allow_full_width_supply_obstacles=False,compilation_phase_timeouts_s=None,required_new_ground_dogbones=(),
            control_shunt_ground_return_axes=(),required_measurement_corridors=(),source_rc_input_prefixes=(),
            required_quiet_output_pad_uuids=(),aggregate_capacitor_max_shift_mm=None,
            allow_linear_power_stage_reconstruction=False,shared_supply_root_pad_uuids=(),
            native_pose_phase_timeouts_s=None,ground_barrel_clearance_window_uuids=(),
            pose_selection_phase_timeouts_s=None):
    if (type(board_hint) is not str or not board_hint or type(timeout_s) not in (int,float)
            or not math.isfinite(timeout_s) or not 0<timeout_s<=10.
            or type(max_shift_mm) not in (int,float) or not math.isfinite(max_shift_mm) or not 0<max_shift_mm<=32.
            or type(allow_owned_locked_escapes) is not bool or type(rebuild_projected_ground) is not bool
            or type(allow_octilinear_rotations) is not bool or type(allow_full_width_supply_obstacles) is not bool
            or type(allow_linear_power_stage_reconstruction) is not bool):
        raise ValueError('bounded_complete_saved_macro_receiving_required')
    escape.aggregate_cap_shift_bound(aggregate_capacitor_max_shift_mm)
    shared_supply_root_pad_uuids=escape.shared_fork.supply_root_ids(shared_supply_root_pad_uuids)
    import cec_macro_measurement_corridor as corridor
    required_measurement_corridors=corridor.requests(required_measurement_corridors)
    import cec_macro_rc_input_prefix as rc_prefix
    source_rc_input_prefixes=rc_prefix.requests(source_rc_input_prefixes)
    import cec_macro_quiet_output as quiet_outputs
    required_quiet_output_pad_uuids=quiet_outputs.ids(required_quiet_output_pad_uuids)
    import cec_macro_ground_barrel_window as windows
    window_ids=windows.ids(ground_barrel_clearance_window_uuids)
    compile_budgets=None if compilation_phase_timeouts_s is None else compiler._phase_budgets(compilation_phase_timeouts_s)
    if compile_budgets is not None and any(v>timeout_s for v in compile_budgets):
        raise ValueError('saved_macro_compilation_constituents_exceed_receiving_limit')
    pose_budgets=(None if native_pose_phase_timeouts_s is None else
        compiler._pose_phase_budgets(native_pose_phase_timeouts_s,timeout_s))
    selection_budgets=(None if pose_selection_phase_timeouts_s is None else
        cell.pose_selection_budgets(pose_selection_phase_timeouts_s))
    if selection_budgets is not None and any(v>timeout_s for v in selection_budgets):
        raise ValueError('saved_macro_pose_selection_constituents_exceed_receiving_limit')
    selection_stages=(['actual_pose_selection:'+name for name in cell.POSE_SELECTION_PHASES]
        if selection_budgets is not None else [])
    pose_stages=(['independent_native_pose:'+name for name in compiler.NATIVE_POSE_PHASES]
        if pose_budgets is not None else [])
    names=compiler.compilation_phases(compile_budgets)
    compile_stages=(['source_compilation:'+name for name in names]
        if compile_budgets is not None else ['source_compilation'])
    ground_stages=(['ground_source_compilation:'+name for name in names]
        if compile_budgets is not None else [])+['independent_ground_source_expectation']
    started=time.monotonic()
    stages=['actual_saved_source_identity_and_poses',*selection_stages,*compile_stages]
    if reference_group_uuids:stages.append('independent_source_reference_groups')
    native_stages=(['independent_native_prefill_and_refill',*pose_stages,'independent_native_terminals']
        if pose_budgets is not None else ['independent_native_frame'])
    stages+=[*(['independent_carried_Ground_barrel_antipads']if window_ids else []),*native_stages,'exact_saved_delta',
        *ground_stages,'actual_terminal_paths_and_native_partitions','physical_returns_and_trace_craft']
    quiet_stages=quiet_outputs.receiving_stages(
        dict(compilation_phase_timeouts_s=compile_budgets)if compile_budgets is not None else {},
        required_quiet_output_pad_uuids,timeout_s)if required_quiet_output_pad_uuids else []
    stages+=['independent_quiet:'+name for name in quiet_stages]
    lease=_ReceivingLease(timeout_s,stages)
    def remaining(stage):
        return lease.remaining()
    result=dict(ok=False,complete=False,errors=[],scope='independent_saved_source_owned_macro_cell',
        independent_stage_max_seconds=timeout_s,explicit_maximum_receiving_stages=len(stages),
        stage_timings_s=lease.timings,bounded_composition=dict(constituents=stages,
            per_constituent_limit_s=timeout_s,aggregate_limit_s=len(stages)*timeout_s),
        routing_admitted=False,fab_ready=False,release_authority=False,current_qualified=False,
        original_current_field_Kelvin_DRC_and_actual_stack_receiving_still_required=True)
    stage='actual_saved_source_identity_and_poses'
    try:
        paths=[Path(p).resolve() for p in (source,candidate)]
        if paths[0]==paths[1]:raise ValueError('distinct_saved_macro_source_and_candidate_required')
        epoch=force._code_identity();families=[force._family(p,board_hint) for p in paths]
        parent,child=[pcbnew.LoadBoard(str(p)) for p in paths]
        if selection_budgets is None:
            poses,moved=(cell._poses(parent,child,board_hint,reference_group_uuids)
                if reference_group_uuids else cell._poses(parent,child,board_hint))
        else:
            stage=selection_stages[0];lease.advance(stage)
            def observe_selection(event):
                nonlocal stage
                if event['event']=='start' and event['index']:
                    stage=selection_stages[event['index']];lease.advance(stage)
                lease.remaining()
            with cell.observe_pose_selection_phases(observe_selection):
                poses,moved=cell._poses(parent,child,board_hint,reference_group_uuids,
                    phase_timeouts_s=selection_budgets)
        lease.advance(compile_stages[0])
        stage=compile_stages[0]
        def compile_source():
            return compiler.compile(paths[0],poses,board_hint=board_hint,max_shift_mm=max_shift_mm,
            timeout_s=remaining('source'),allow_owned_locked_escapes=allow_owned_locked_escapes,
            rebuild_projected_ground=rebuild_projected_ground,
            additional_obstacle_track_uuids=additional_obstacle_track_uuids,reuse_ground_barrels=reuse_ground_barrels,
            ordinary_via_poses=ordinary_via_poses,max_obstacle_track_mm=max_obstacle_track_mm,
            max_obstacle_tracks=max_obstacle_tracks,required_ground_pad_entries=required_ground_pad_entries,
            required_new_ground_dogbones=required_new_ground_dogbones,
            control_shunt_ground_return_axes=control_shunt_ground_return_axes,
            stationary_ground_barrel_uuids=stationary_ground_barrel_uuids,
            allow_octilinear_rotations=allow_octilinear_rotations,required_supply_departures=required_supply_departures,
            local_signal_port_offsets=local_signal_port_offsets,reference_group_uuids=reference_group_uuids,
            required_ordinary_nets=required_ordinary_nets,
                allow_full_width_supply_obstacles=allow_full_width_supply_obstacles,
                compilation_phase_timeouts_s=compile_budgets,
                required_measurement_corridors=required_measurement_corridors,
                source_rc_input_prefixes=source_rc_input_prefixes,
                **(dict(required_quiet_output_pad_uuids=required_quiet_output_pad_uuids)
                    if required_quiet_output_pad_uuids else {}),
                **(dict(aggregate_capacitor_max_shift_mm=aggregate_capacitor_max_shift_mm)
                    if aggregate_capacitor_max_shift_mm is not None else {}),
                **(dict(allow_linear_power_stage_reconstruction=True)
                    if allow_linear_power_stage_reconstruction else {}),
                **(dict(shared_supply_root_pad_uuids=shared_supply_root_pad_uuids)
                    if shared_supply_root_pad_uuids else {}))
        if compile_budgets is None:projected,packet=compile_source()
        else:
            def observe_source(event):
                nonlocal stage
                if event['event']=='start'and event['index']:
                    stage=compile_stages[event['index']];lease.advance(stage)
                lease.remaining()
            with compiler.observe_compilation_phases(observe_source):projected,packet=compile_source()
        if reference_group_uuids:
            # Current-code macro compilation and independent Source annotation
            # reconstruction are DIFFERENT proofs. Each retains its own <=10s
            # limit; neither borrows time from a future constituent.
            lease.advance('independent_source_reference_groups')
            stage='independent_source_reference_groups'
            import cec_source_reference_group_transport as reference_transport
            import cec_copper_echo as source_syntax
            _,candidate_nodes=additive._nodes(paths[1])
            requests=_reference_requests(packet['source_plan'])
            if any(turn for proof,turn,delta in requests):
                import cec_source_reference_group_cardinal_batch as cardinal
                expected_sets=[cardinal.expected_nodes(requests,
                    maximum_translation_mm=escape.complete_transport_shift_bound(packet['source_plan']))]
            else:expected_sets=[reference_transport.expected_nodes(proof,delta_nm=delta,
                maximum_translation_mm=escape.complete_transport_shift_bound(packet['source_plan']))for proof,turn,delta in requests]
            for expected in expected_sets:
                if any(u not in candidate_nodes or source_syntax._freeze(candidate_nodes[u])!=source_syntax._freeze(n)
                       for u,n in expected.items()):
                    raise ValueError('saved_macro_source_reference_group_translation_differs')
        remaining('source')
        if window_ids:
            stage='independent_carried_Ground_barrel_antipads';lease.advance(stage)
            result['independent_carried_Ground_barrel_antipads']=windows.apply(parent,projected,
                packet['transport'],window_ids,timeout_s=remaining('Ground_windows'))
        stage=native_stages[0];lease.advance(stage)
        from contextlib import nullcontext
        with(windows.search_geometry(parent,projected,packet['transport'],window_ids,
                timeout_s=remaining('native_frame'))if window_ids else nullcontext()):
            prefill=compiler.pre_refill_barrel_screen(projected,packet,timeout_s=remaining('native_frame'))
        result['pre_refill_native_macro_barrels']=prefill
        if not prefill['ok']:raise ValueError('saved_complete_macro_pre_refill_native_barrel_collision')
        additive._ground_refill(projected)
        if pose_budgets is None:
            native=compiler.native_pose_screen(parent,projected,packet,timeout_s=remaining('native_frame'),
                **(dict(ground_barrel_clearance_window_uuids=window_ids)if window_ids else {}))
        else:
            stage=pose_stages[0];lease.advance(stage)
            def observe_pose(event):
                nonlocal stage
                if event['event']=='start'and event['index']:
                    stage=pose_stages[event['index']];lease.advance(stage)
                lease.remaining()
            with compiler.observe_native_pose_phases(observe_pose):
                native=compiler.native_pose_screen(parent,projected,packet,timeout_s=timeout_s,
                    phase_timeouts_s=pose_budgets,
                    **(dict(ground_barrel_clearance_window_uuids=window_ids)if window_ids else {}))
        result['independent_native_frame']=native
        if not native['ok']:raise ValueError('saved_complete_macro_native_frame_refused')
        if pose_budgets is not None:
            stage='independent_native_terminals';lease.advance(stage)
        retained_reference=[]
        for key,request in packet['requests'].items():
            proof=escape.retained_ground_reference_connection(projected,request,
                timeout_s=remaining('native_frame'))
            if proof is None:
                import cec_retained_ground_component as retained_ground
                proof=retained_ground.observe(projected,request,timeout_s=remaining('native_frame'))
            if proof is not None:retained_reference.append((key,request,proof))
        missing=escape.unplanned_source_terminals(parent,packet['source_plan'],packet['requests'],
            timeout_s=remaining('native_frame'),board=projected,
            **(dict(required_quiet_output_pad_uuids=required_quiet_output_pad_uuids)
                if required_quiet_output_pad_uuids else {}))
        result['inherited_unplanned_terminals']=missing
        if missing:raise ValueError('saved_complete_macro_has_unplanned_original_terminals')
        lease.advance('exact_saved_delta')
        stage='exact_saved_delta'
        with tempfile.TemporaryDirectory(prefix='cec-complete-saved-macro-') as work:
            expected=force._copy_family(paths[0],Path(work)/'expected')
            save_private(projected,expected,packet)
            replay=additive.receive(expected,paths[1],timeout_s=remaining('exact_delta'),board_hint=board_hint,
                allow_endpoint_neckdown_additions=True)
            result['independent_exact_source_cut_transform_and_additions']=replay
            if not replay['ok'] or not replay['complete']:
                raise ValueError('saved_complete_macro_exact_native_replay_refused:'+repr(replay['errors']))
        lease.advance(ground_stages[0])
        stage=ground_stages[0]
        source_ground_observer=None
        if compile_budgets is not None or any(r.get('kind')=='ground_boundary' or r.get('kind')=='source_boundary'and r.get('net')=='GND'
                and any(r.get(n,{}).get('pad_uuid')for n in('a','b'))for r in packet['requests'].values()):
            import cec_source_ground_boundary_connection as source_ground
            def observe_ground(event):
                nonlocal stage
                if event['event']=='expectation_start':
                    stage=ground_stages[-1];lease.advance(stage)
                elif event['event']=='start'and event['index']:
                    stage=ground_stages[event['index']];lease.advance(stage)
                lease.remaining()
            source_ground_observer=source_ground._prepare_observer(parent,packet['requests'],board_hint=board_hint,
                source_proposal=packet['source_plan'],source_macro_packet=packet,
                timeout_s=timeout_s if compile_budgets is not None else remaining('ground_source'),
                **(dict(compile_phase_observer=observe_ground)if compile_budgets is not None else {}))
        result['independent_ground_source_expectation_prepared']=source_ground_observer is not None
        lease.advance('actual_terminal_paths_and_native_partitions')
        stage='actual_terminal_paths_and_native_partitions'
        tracks={force._uid(t):t for t in child.GetTracks()}
        incoming=set(replay['added_native_uuids'])&tracks.keys()
        vias={u for u in incoming if tracks[u].GetClass()=='PCB_VIA'}
        native_ports={u for component in packet['additional_source_cut_components'] if component['net']!='GND'
            for contact in component['surviving_contacts'] for port in contact['projected_literal_ports']
            for u in port.get('native_uuids',[])}
        result['actual_native_terminal_paths']=cell._receive_paths(parent,child,packet['requests'],incoming,
            board_hint,lease.deadline,received_barrel_uuids=vias,received_source_port_uuids=native_ports,
            allow_retained_no_additions=not bool(incoming),source_proposal=packet['source_plan'],source_macro_packet=packet,
            source_ground_observer=source_ground_observer)
        if 'native_retained_bypass_contact_frame' in packet['source_plan']:
            import cec_retained_bypass_contact_frame as retained_bypass
            result['actual_saved_retained_bypass_contact_frame']=retained_bypass.observe(child,
                packet['source_plan']['native_retained_bypass_contact_frame'],timeout_s=remaining('partitions'))
        # Fresh saved-board observation, never a projected-board Boolean or
        # zone UUID. Local Ground obligations are independently mandatory.
        if any(r.get('kind')=='source_boundary' and r.get('net')=='GND'
                and any(r.get(n,{}).get('pad_uuid') for n in ('a','b'))
                for r in packet['requests'].values()):
            import cec_source_ground_boundary_connection as source_ground
            if source_ground_observer is None:raise ValueError('saved_macro_ground_source_expectation_missing')
            result['saved_source_smd_ground_boundary_observations']=source_ground_observer(
                child,timeout_s=remaining('partitions'))
        import cec_macro_ground_ingress as ingress
        result['actual_required_projected_ground_entries']=ingress.receive(child,
            packet.get('required_projected_ground_entries',[]),incoming,timeout_s=remaining('partitions'))
        import cec_macro_new_ground_dogbone as dogbone
        result['actual_required_new_ground_dogbones']=dogbone.receive(child,
            packet.get('required_new_ground_dogbones',[]),incoming,timeout_s=remaining('partitions'))
        import cec_macro_supply_departure as departure
        result['actual_required_supply_departures']=departure.receive(child,
            packet.get('required_supply_departure_columns',[]),incoming,timeout_s=remaining('partitions'))
        import cec_macro_measurement_corridor as corridor
        result['actual_required_measurement_corridors']=corridor.receive(child,
            packet.get('required_measurement_corridors',[]),incoming,timeout_s=remaining('partitions'),
            saved_path=paths[1])
        import cec_stationary_ground_barrel as stationary_ground
        result['actual_retained_stationary_ground_barrels']=stationary_ground.receive(child,
            packet['transport'].get('explicit_stationary_source_ground_barrels',[]),
            timeout_s=remaining('partitions'))
        result['retained_native_ground_reference_connections']={}
        for key,request,expected in retained_reference:
            observed=escape.retained_ground_reference_connection(child,request,timeout_s=remaining('partitions'))
            if observed is None:
                import cec_retained_ground_component as retained_ground
                observed=retained_ground.observe(child,request,timeout_s=remaining('partitions'))
            if observed!=expected:raise ValueError('saved_macro_retained_ground_reference_connection_changed')
            result['retained_native_ground_reference_connections'][key]=observed
        mapping=compiler.identity_rebindings(parent,child,packet,timeout_s=remaining('partitions'))
        rebindings=cell._pad_rebindings(parent,child,packet['source_plan']['poses'])
        if any(k[0]!='pad' and k!=v for k,v in mapping.items()):
            raise ValueError('saved_complete_macro_changed_copper_identity_key')
        if any(rebindings.get(k)!=v for k,v in mapping.items()if k[0]=='pad'):
            raise ValueError('saved_complete_macro_pad_identity_mismatch')
        import cec_native_partition_pair as partition_pair
        paired=partition_pair.compare(parent,child,timeout_s=remaining('partitions'),
            retired_uuids=set(packet['retired_track_uuids']),identity_rebindings=rebindings)
        lost=len(paired['demoted_parts'])
        if lost:raise ValueError('saved_complete_macro_lost_original_native_partition:'+str(lost))
        result['paired_actual_filled_island_preservation']={k:v for k,v in paired.items()
            if k not in ('source_parts','child_parts','demoted_parts')}
        result['all_original_surviving_native_partitions_preserved']=True
        remaining('partitions')
        lease.advance('physical_returns_and_trace_craft')
        stage='physical_returns_and_trace_craft'
        returns=ground.receive(parent,child,timeout_s=remaining('physical_returns'))
        result['all_original_physical_ground_returns']=returns
        if not returns['ok'] or not returns['complete']:
            raise ValueError('saved_complete_macro_ground_return_regression')
        old_quality,new_quality=[craft.analyze_board(b) for b in (parent,child)]
        result['trace_craft_before_after']=[old_quality['issue_count'],new_quality['issue_count']]
        if (new_quality['issue_count']>old_quality['issue_count']
                or new_quality['non_octilinear_count']>old_quality['non_octilinear_count']):
            raise ValueError('saved_complete_macro_trace_craft_regression')
        remaining('physical_returns')
        if required_quiet_output_pad_uuids:
            import cec_quiet_signal_completion as quiet
            quiet_options=compiler.packet_options(packet)
            if quiet_options.pop('required_quiet_output_pad_uuids',None)!=required_quiet_output_pad_uuids:
                raise ValueError('fresh_macro_quiet_opt_in_binding_changed')
            quiet_options.update(max_shift_mm=max_shift_mm,
                allow_owned_locked_escapes=allow_owned_locked_escapes,
                rebuild_projected_ground=rebuild_projected_ground,
                additional_obstacle_track_uuids=list(additional_obstacle_track_uuids))
            stage='independent_quiet:'+quiet_stages[0];lease.advance(stage)
            def observe_quiet(event):
                nonlocal stage
                if event['index']:
                    stage='independent_quiet:'+event['phase'];lease.advance(stage)
                lease.remaining()
            with quiet_outputs.observe_receiving_phases(observe_quiet):
                received_quiet=quiet.receive_projected(paths[0],paths[1],board_hint=board_hint,
                    required_quiet_output_pad_uuids=required_quiet_output_pad_uuids,
                    macro_options=quiet_options,timeout_s=timeout_s)
            result['independent_saved_projected_quiet_paths']=received_quiet
            if (received_quiet.get('ok')is not True or received_quiet.get('complete')is not True
                    or received_quiet.get('source_sha256')!=force._hash(paths[0])
                    or received_quiet.get('candidate_sha256')!=force._hash(paths[1])):
                raise ValueError('independent_saved_projected_quiet_path_refused_or_changed')
        if (families!=[force._family(p,board_hint) for p in paths] or epoch!=force._code_identity()
                or not no_connect.bindings_current(packet['source_plan'].get('source_explicit_schematic_no_connects',[]))
                or time.monotonic()-started>len(stages)*timeout_s):
            raise ValueError('saved_complete_macro_family_code_or_total_work_epoch_changed')
        lease.finish()
        result.update(ok=True,complete=True,source_sha256=force._hash(paths[0]),candidate_sha256=force._hash(paths[1]),
            source_macro_packet=packet,moved_refs=sorted(moved),added_native_uuids=sorted(incoming),
            retired_track_uuids=packet['retired_track_uuids'],source_candidate_families_and_code_unchanged=True,
            source_owned_barrel_count=len(packet['transport']['source_process_barrel_motion']),
            added_barrels_independently_received=len(vias))
    except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
        result['failed_stage']=stage
        frames=traceback.extract_tb(exc.__traceback__)
        result['failure_stack']=[dict(module=Path(f.filename).name,function=f.name,line=f.lineno)
            for f in frames[-24:]]
        result['failure_stack_truncated']=len(frames)>24
    result['elapsed_s']=time.monotonic()-started
    return result
