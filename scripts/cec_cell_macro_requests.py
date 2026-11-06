"""Source-typed complete restoration demands for a native SMD macro.

Placement events may omit changed edges to look for space. That is NOT cut
authority. Retype every extra omission, project actual source-owned barrel
ports, and expose all original Ground fragments before routing can start.
This compiler writes no PCB and grants no saved, current or fab admission.
"""
import copy
import json
import math
from itertools import product
from pathlib import Path
import time
import contextvars
from contextlib import contextmanager
import pcbnew
import cec_cell_escape_replan as escape
import cec_cell_row_rebuild as row
import cec_cell_ground_cut_boundaries as ground
import cec_decoupler_cell as cells
import cec_device_power_roles as roles
import cec_force_current as force
import cec_fab_profile as fab
import cec_fr as fr
import cec_full_current_planar_reflow as full
import cec_ordinary_route_receiving as ordinary
import cec_smd_macro_transport as macro
from cec_native_items import discard_items


_compile_observer=contextvars.ContextVar('native_macro_compile_phase_observer',default=None)
_pose_observer=contextvars.ContextVar('native_macro_pose_phase_observer',default=None)
COMPILATION_PHASES=('source_ownership','native_frame_and_cuts','complete_endpoint_obligations')
NATIVE_POSE_PHASES=('actual_cut_copper_and_holes','fresh_uncut_priority_frame','independent_priority_ownership')


@contextmanager
def observe_native_pose_phases(callback):
    """Diagnostic timers only; no subproof is returned across a live seam."""
    if not callable(callback):raise ValueError('native_pose_phase_observer_required')
    token=_pose_observer.set(callback)
    try:yield
    finally:_pose_observer.reset(token)


def _pose_phase_budgets(value,timeout_s):
    if (type(timeout_s)not in(int,float)or not math.isfinite(timeout_s)or not 0<timeout_s<=10.
            or type(value)not in(list,tuple)or len(value)!=len(NATIVE_POSE_PHASES)
            or any(type(v)not in(int,float)or not math.isfinite(v)or not 0<v<=timeout_s for v in value)):
        raise ValueError('three_explicit_native_pose_constituents_within_existing_limit_required')
    return list(value)


def _native_pose_binding(board):
    """Full non-normalizing native serialization, not a partial XY signature.

    PCB_IO.Format(BOARD) is not a supported native writer. Use the existing
    reload-checked snapshot path; this includes hidden metadata, all via
    faces, land shapes, locks, groups, masks and native settings.
    """
    import tempfile
    import cec_field_coupling as field
    with tempfile.TemporaryDirectory(prefix='cec-native-pose-binding-')as work:
        path=Path(work)/'board.kicad_pcb'
        field._save_field_snapshot(board,path)
        return force._hash(path)


def _native_pose_fence(parent,posed,packet):
    """Private operation-local input identity; never role or cut authority."""
    import hashlib,os
    import _pcbnew
    if type(packet)is not dict or packet.get('scope')!='source_typed_complete_native_macro_requests':
        raise ValueError('fresh_typed_native_pose_packet_required')
    source=Path(packet['source']).resolve();hint=packet['source_plan']['board_hint']
    if force._hash(source)!=packet['source_sha256']or force._code_identity()!=packet['code_identity']:
        raise ValueError('native_pose_Source_or_code_epoch_changed')
    bindings={};visited=0
    def bind(path,sha):
        if type(path)is not str or type(sha)is not str:
            raise ValueError('literal_native_pose_input_binding_required')
        if path in bindings and bindings[path]!=sha:
            raise ValueError('conflicting_native_pose_input_binding')
        bindings[path]=sha
    def walk(value):
        nonlocal visited
        visited+=1
        if visited>262144:raise ValueError('bounded_native_pose_packet_required')
        if type(value)is dict:
            for key,item in value.items():
                if key in('schematic_files_sha256','evidence_files_sha256'):
                    if type(item)is not dict:raise ValueError('native_pose_file_binding_map_required')
                    for path,sha in item.items():bind(path,sha)
                elif key=='exporter'and type(item)is dict and 'exporter'in item:
                    bind(item['exporter'],item['exporter_sha256'])
                walk(item)
        elif type(value)is list:
            for item in value:walk(item)
    walk(packet)
    if any(force._hash(path)!=sha for path,sha in bindings.items()):
        raise ValueError('native_pose_Source_evidence_binding_changed')
    text=json.dumps(packet,sort_keys=True,separators=(',',':'),allow_nan=False)
    environment={k:v for k,v in os.environ.items()if k.startswith(('CEC_','KICAD'))or k=='PATH'}
    return dict(packet=hashlib.sha256(text.encode()).hexdigest(),
        source_sha256=force._hash(source),family=force._family(source,hint),code=force._code_identity(),
        native={str(Path(m.__file__).resolve()):force._hash(m.__file__)for m in(pcbnew,_pcbnew)},
        environment=hashlib.sha256(json.dumps(environment,sort_keys=True).encode()).hexdigest(),
        parent=_native_pose_binding(parent),posed=_native_pose_binding(posed),
        evidence=bindings)


class _NativePoseLeases:
    """Explicit ordered checks; default retains the one original deadline."""
    def __init__(self,timeout_s,phase_timeouts_s=None):
        if type(timeout_s)not in(int,float)or not math.isfinite(timeout_s)or not 0<timeout_s<=10.:
            raise ValueError('bounded_native_pose_screen_required')
        self.budgets=None if phase_timeouts_s is None else _pose_phase_budgets(phase_timeouts_s,timeout_s)
        self.index=0;self.finished=False;self.timings={};self.phase_started=time.monotonic()
        self.deadline=self.phase_started+(timeout_s if self.budgets is None else self.budgets[0])
        self._emit('start')

    def _emit(self,event):
        observer=_pose_observer.get()
        if observer is not None:observer(dict(event=event,index=self.index,phase=NATIVE_POSE_PHASES[self.index],
            deadline_monotonic=self.deadline,explicit_ordered_composition=self.budgets is not None))

    def remaining(self):
        left=self.deadline-time.monotonic()
        if self.finished or left<=0:raise ValueError('complete_macro_native_pose_deadline')
        return min(10.,left)

    def _seal(self,check):
        # Emit no acceptance certificate: the callback precedes the final
        # live-input validation and cannot mutate the last phase unnoticed.
        self.remaining();self._emit('finish');self.remaining()
        if not check():raise ValueError('native_pose_live_inputs_changed')
        self.remaining()
        self.timings[NATIVE_POSE_PHASES[self.index]]=time.monotonic()-self.phase_started

    def advance(self,name,check):
        if self.index>=2 or name!=NATIVE_POSE_PHASES[self.index+1]:
            raise ValueError('ordered_all_native_pose_constituents_required')
        self._seal(check);self.index+=1;self.phase_started=time.monotonic()
        if self.budgets is not None:self.deadline=self.phase_started+self.budgets[self.index]
        self._emit('start')

    def finish(self,check):
        if self.index!=2:raise ValueError('all_native_pose_constituents_required')
        self._seal(check);self.finished=True


def _preserve_endpoint_throats(retired,endpoint_cuts,supply_endpoint_cuts):
    """Cross-check the complete, independently derived retirement union."""
    fixed={u for q in [*endpoint_cuts,*supply_endpoint_cuts]
        for u in q['retained_throat_track_uuids']}
    if set(retired)&fixed:
        raise ValueError('complete_macro_retirement_intersects_retained_endpoint_throat')


def _compose_supply_endpoint_rows(proposal,supply_endpoint_cuts):
    """Replace only the exact retired input-lead contacts, never drop debt."""
    roots={u:q for q in supply_endpoint_cuts for u in q['retired_track_uuids']}
    rows=proposal['row_plan']['source_incident_boundaries'];kept=[];composed=[]
    for contact in rows:
        cut=roots.get(contact['track_uuid'])
        if cut is None:kept.append(contact);continue
        if (contact['pad_uuid']!=cut['pad_uuid']or contact['layer']!=cut['layer_id']
                or contact.get('net',cut['net'])!=cut['net']):
            raise ValueError('retired_supply_input_contact_not_exact_cut_root')
        composed.append(dict(original_source_contact=copy.deepcopy(contact),
            replacement_request_id='source_supply_lead:'+cut['retired_track_uuids'][0],
            source_retired_chain_uuids=cut['retired_track_uuids'],
            original_contact_restored_to_literal_full_width_throat=True))
    proposal['row_plan']['source_incident_boundaries']=kept
    return composed


@contextmanager
def observe_compilation_phases(callback):
    """Runtime diagnostics/outer hard timers, never replayable acceptance proof."""
    if not callable(callback):raise ValueError('compilation_phase_observer_required')
    token=_compile_observer.set(callback)
    try:yield
    finally:_compile_observer.reset(token)


def _phase_budgets(value):
    if (type(value)not in(list,tuple)or len(value)not in(3,4,6,8,9)
            or any(type(v)not in(int,float)or not math.isfinite(v)or not 0<v<=10 for v in value)):
        raise ValueError('three_four_six_eight_or_nine_explicit_bounded_macro_compilation_phases_required')
    return list(value)


def compilation_phases(phase_budgets=None):
    """Legacy work stays unchanged; extra independent stages are explicit.

    The six-stage mode does NOT extend an existing lease or reuse a passed
    Source check. It separates fresh Ground/partition derivation and final
    component inventory, each with its own unchanged-input boundary check.
    """
    count=None if phase_budgets is None else len(_phase_budgets(phase_budgets))
    if count==9:
        legacy=compilation_phases(phase_budgets[:8])
        return (legacy[0],'source_contact_ownership',*legacy[1:])
    if count in(4,6,8):
        phases=(*COMPILATION_PHASES[:2],'canonical_boundary_ownership',COMPILATION_PHASES[2])
        if count==8:
            phases=(*phases[:3],'canonical_ground_multiport_boundary','canonical_boundary_composition',phases[3])
        return (*phases,'independent_ground_endpoint_obligations','complete_component_inventory')if count in(6,8)else phases
    return COMPILATION_PHASES


class _CompilationLeases:
    """No phase borrowing, cached passes or prefix construction authority."""
    def __init__(self,timeout_s,phase_budgets):
        if type(timeout_s)not in(int,float)or not math.isfinite(timeout_s)or not 0<timeout_s<=10:
            raise ValueError('bounded_macro_request_compilation_required')
        self.budgets=None if phase_budgets is None else _phase_budgets(phase_budgets)
        self.phases=compilation_phases(self.budgets)
        self.started=time.monotonic();self.index=0;self.finished=False
        self.deadline=self.started+(timeout_s if self.budgets is None else self.budgets[0])
        self._emit('start')

    def _emit(self,event):
        callback=_compile_observer.get()
        if callback is not None:callback(dict(event=event,phase=self.phases[self.index],
            index=self.index,deadline_monotonic=self.deadline,
            explicit_ordered_composition=self.budgets is not None))

    def _seal(self,check):
        if self.finished or time.monotonic()>=self.deadline:
            raise ValueError('complete_macro_request_compilation_deadline:'+self.phases[self.index])
        if not check():raise ValueError('macro_request_source_or_code_changed')
        if time.monotonic()>=self.deadline:
            raise ValueError('complete_macro_request_compilation_deadline:'+self.phases[self.index])
        self._emit('finish')
        if time.monotonic()>=self.deadline:
            raise ValueError('complete_macro_request_compilation_deadline:'+self.phases[self.index])

    def advance(self,phase,check):
        if self.index>=len(self.phases)-1 or phase!=self.phases[self.index+1]:
            raise ValueError('ordered_complete_macro_compilation_phases_required')
        self._seal(check);self.index+=1
        if self.budgets is not None:self.deadline=time.monotonic()+self.budgets[self.index]
        self._emit('start')
        return self.deadline

    def finish(self,check):
        if self.index!=len(self.phases)-1:
            raise ValueError('all_macro_compilation_phases_required')
        self._seal(check);self.finished=True


def packet_options(packet):
    """Only explicit reconstructible inputs, never arbitrary packet kwargs."""
    options=packet.get('explicit_native_macro_options',{})
    if type(options) is not dict or set(options)-{'reuse_ground_barrels','ordinary_via_poses',
            'max_obstacle_track_mm','max_obstacle_tracks','required_ground_pad_entries','required_new_ground_dogbones',
            'stationary_ground_barrel_uuids','allow_octilinear_rotations','required_supply_departures',
            'local_signal_port_offsets','reference_group_uuids','required_ordinary_nets',
            'allow_full_width_supply_obstacles','compilation_phase_timeouts_s','control_shunt_ground_return_axes',
            'required_measurement_corridors','source_rc_input_prefixes','required_quiet_output_pad_uuids',
            'aggregate_capacitor_max_shift_mm','allow_linear_power_stage_reconstruction','shared_supply_root_pad_uuids'}:
        raise ValueError('unsupported_explicit_native_macro_option')
    if ('allow_full_width_supply_obstacles' in options
            and type(options['allow_full_width_supply_obstacles']) is not bool):
        raise ValueError('explicit_full_width_supply_obstacle_scope_required')
    if 'compilation_phase_timeouts_s'in options:_phase_budgets(options['compilation_phase_timeouts_s'])
    if 'aggregate_capacitor_max_shift_mm'in options:
        escape.aggregate_cap_shift_bound(options['aggregate_capacitor_max_shift_mm'])
    if ('allow_linear_power_stage_reconstruction'in options
            and type(options['allow_linear_power_stage_reconstruction'])is not bool):
        raise ValueError('linear_stage_explicit_boolean_opt_in_required')
    if 'shared_supply_root_pad_uuids'in options:
        escape.shared_fork.supply_root_ids(options['shared_supply_root_pad_uuids'])
    if 'required_measurement_corridors' in options:
        import cec_macro_measurement_corridor as corridor
        corridor.requests(options['required_measurement_corridors'])
    if 'required_quiet_output_pad_uuids' in options:
        import cec_macro_quiet_output as quiet_outputs
        quiet_outputs.ids(options['required_quiet_output_pad_uuids'])
    if 'source_rc_input_prefixes' in options:
        import cec_macro_rc_input_prefix as rc_prefix
        rc_prefix.requests(options['source_rc_input_prefixes'])
    try:return json.loads(json.dumps(options,allow_nan=False))
    except (ValueError,TypeError):raise ValueError('finite_json_native_macro_options_required') from None


def _frame(parent,source,proposal,*,reuse_ground_barrels=(),ordinary_via_poses=(),stationary_ground_barrel_uuids=(),
           local_signal_port_offsets=(),control_shunt_ground_return_axes=(),timeout_s=10.):
    deadline=time.monotonic()+timeout_s
    private=pcbnew.LoadBoard(str(source))
    reference_transports=proposal['row_plan'].get('source_reference_group_transports',{})
    if reference_transports:
        import cec_source_reference_group_transport as reference_transport
        requests=[]
        for ref,contract in reference_transports.items():
            first=proposal['row_plan']['source_poses'][ref];last=proposal['poses'][ref]
            turn=((last[2]-first[2])%360)/90
            if abs(turn-round(turn))>1e-8:
                raise ValueError('source_reference_group_cardinal_pose_required')
            requests.append((contract,round(turn)%4,tuple(round((last[k]-first[k])*1e6)for k in(0,1))))
        if any(turn for contract,turn,delta in requests):
            import cec_source_reference_group_cardinal_batch as cardinal
            cardinal.transform_many(private,requests,maximum_translation_mm=escape.complete_transport_shift_bound(proposal))
        else:reference_transport.transform_many(private,[(contract,delta)for contract,turn,delta in requests],
            maximum_translation_mm=escape.complete_transport_shift_bound(proposal))
    for ref,pose in proposal['poses'].items():
        if ref in reference_transports:continue
        fp=private.FindFootprintByReference(ref)
        fp.SetPosition(pcbnew.VECTOR2I(*(round(v*1e6) for v in pose[:2])))
        fp.SetOrientationDegrees(pose[2])
    reuse=[]
    if type(reuse_ground_barrels) not in (list,tuple) or len(reuse_ground_barrels)>16:
        raise ValueError('bounded_explicit_stationary_ground_barrel_reuse_required')
    if reuse_ground_barrels:
        import cec_projected_ground_contact as contact
        pads={force._uid(p):p for fp in parent.GetFootprints() for p in fp.Pads()};seen=set();owners=set()
        for q in reuse_ground_barrels:
            if (type(q) is not dict or set(q)!={'uuid','owner_pad_uuid'}
                    or type(q['uuid']) is not str or q['uuid'] in seen or q['owner_pad_uuid'] in owners
                    or q['owner_pad_uuid'] not in pads):
                raise ValueError('unique_literal_ground_barrel_reuse_request_required')
            ref=pads[q['owner_pad_uuid']].GetParentFootprint().GetReference()
            if ref not in proposal['poses']:raise ValueError('ground_barrel_reuse_owner_outside_cohort')
            reuse.append(contact.plan_barrel_reuse(parent,q['owner_pad_uuid'],q['uuid'],
                proposal['poses'][ref],board_hint=proposal['board_hint'],
                **({'allow_octilinear_rotations':True} if proposal.get('allow_octilinear_rotations',False) else {})))
            seen.add(q['uuid']);owners.add(q['owner_pad_uuid'])
    unwired=_unwired_moved_source_lands(parent,private)
    preserved_contact_frame=proposal.get('native_retained_bypass_contact_frame')
    if preserved_contact_frame is not None:
        import cec_retained_bypass_contact_frame as retained_bypass
        retained_bypass.observe(private,preserved_contact_frame)
    keep_source_tracks=unwired or preserved_contact_frame is not None
    seating={}
    if control_shunt_ground_return_axes:
        # The native consumer independently derives Source role, exclusive
        # barrel and class/shortening proof from these identity-only requests.
        # Do not export a producer proof or derive the same catalog twice.
        seating=dict(source_control_ground_return_axes=control_shunt_ground_return_axes,
            timeout_s=min(10.,max(.001,deadline-time.monotonic())))
    shift_bound=escape.complete_transport_shift_bound(proposal)
    transport=macro.apply(parent,private,**seating,maximum_shift_mm=shift_bound,
        **(dict(maximum_translation_mm=shift_bound)if shift_bound>64. else {}),
        source_path=source,board_hint=proposal['board_hint'],allow_cardinal_rotations=True,
        allow_octilinear_rotations=proposal.get('allow_octilinear_rotations',False),
        retained_ground_contacts=list(proposal.get('native_projected_ground_contacts',{}).values()),
        reused_ground_barrel_contacts=reuse,ordinary_via_poses=ordinary_via_poses,
        stationary_ground_barrel_uuids=stationary_ground_barrel_uuids,local_signal_port_offsets=local_signal_port_offsets,
        reference_group_uuids=proposal.get('reference_group_uuids',()),
        # A genuinely unwired Source land has no old conductor to transport.
        # Retain ALL old metal via the existing strict mode, rather than
        # inventing a changed conductor to satisfy a work-count minimum.
        # A separately proved wired bypass frame keeps its old graph too.
        # This never reclassifies it as unwired or qualifies its old return.
        retain_source_tracks=keep_source_tracks,
        rebuild_source_ground_endpoints=not keep_source_tracks,
        rebuild_source_supply_endpoints=not keep_source_tracks,
        source_rc_input_prefixes=proposal.get('source_rc_input_prefixes',()),
        allow_owned_locked_ground_endpoints=not keep_source_tracks and proposal.get('allow_owned_locked_escapes',False))
    if time.monotonic()>=deadline:raise ValueError('source_control_return_frame_deadline')
    import cec_existing_local_pofv_pad_rule as saved_pad_rule
    saved_pad_rule.bind_projected_source_poses(private,proposal['poses'],
        allow_octilinear_rotations=proposal.get('allow_octilinear_rotations',False))
    return private,transport


def _unwired_moved_source_lands(parent,child,*,timeout_s=2.):
    """Positive native absence of conductor contact, not a shared-net guess.

    This only chooses the EXISTING retain-all-copper transport mode. Every
    moved land still owes typed Source placement, future connections, all
    physical/partition/current/field/DRC receiving. Unknown fills refuse.
    """
    if type(timeout_s)not in(int,float)or not math.isfinite(timeout_s)or not 0<timeout_s<=10:
        raise ValueError('bounded_unwired_source_frame_required')
    deadline=time.monotonic()+timeout_s
    before={force._uid(f):f for f in parent.GetFootprints()}
    after={force._uid(f):f for f in child.GetFootprints()}
    if before.keys()!=after.keys():return False
    def pose(f):return tuple(f.GetPosition()),f.GetOrientationDegrees(),f.IsFlipped()
    moved=[f for u,f in before.items()if pose(f)!=pose(after[u])]
    pads=[p for f in moved for p in f.Pads()]
    material=[*(p for f in parent.GetFootprints()for p in f.Pads()),
        *parent.GetTracks(),*[z for z in parent.Zones()if not z.GetIsRuleArea()]]
    if not moved or not 1<=len(pads)<=256 or len(material)>16384:return False
    for pad in pads:
        if pad.HasHole()or pad.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD:return False
        for item in material:
            if force._uid(item)==force._uid(pad):continue
            if time.monotonic()>=deadline:raise ValueError('unwired_source_frame_deadline')
            for face in set(pad.GetLayerSet().CuStack())&set(item.GetLayerSet().CuStack()):
                if item.GetClass()=='ZONE':
                    if not item.IsFilled():return False
                    if item.GetFilledPolysList(face).Collide(pad.GetEffectiveShape(face),0):return False
                elif item.GetEffectiveShape(face).Collide(pad.GetEffectiveShape(face),0):return False
    return True


def _ground_boundary_typer(parent,transport,proposal,deadline):
    """Type an existing small lead at an actually moving Source terminal.

    This is restoration of the literal old low-power connection, not
    ownership of the shared Ground network. An existing address strap keeps
    its manufacturer address role; it never becomes a power-return pin.
    No arbitrary same-net branch, power stage, collector land or changed
    net receives this authority. Exact endpoints, widths, all old partitions
    and physical returns still need independent complete saved receiving.
    """
    # Private, same-call lazy replays only. Neither callers nor later
    # compilation phases can supply or retain a canonical role dictionary.
    initial=row._source_binding(parent);epoch=force._code_identity()
    source=Path(parent.GetFileName()).resolve();family=force._family(source,proposal.get('board_hint'))
    original=copy.deepcopy(proposal);original_transport=copy.deepcopy(transport)
    optional_context=None;programming_context=None;shunt_context=None;timing_context=None
    def typed(pad):
        nonlocal optional_context,programming_context,shunt_context,timing_context
        fp=pad.GetParentFootprint();ref=fp.GetReference()
        if (ref not in proposal['poses'] or pad.GetNetname()!='GND' or pad.HasHole()
                or pad.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD):return None
        if ref in proposal['selected_bypasses']:
            return dict(pad_uuid=force._uid(pad),ref=ref,role='source_selected_bypass_ground',
                selected_bypass=proposal['selected_bypasses'][ref])
        if ref in proposal.get('selected_control_shunts',{}):
            import cec_control_shunt_placement as control_shunt
            if shunt_context is None:
                shunt_context=control_shunt.plan(parent,proposal['poses'],board_hint=proposal['board_hint'],
                    reference_group_uuids=proposal.get('reference_group_uuids',()),
                    timeout_s=min(10.,max(.001,deadline-time.monotonic())))
            fresh=shunt_context
            proof=fresh.get(ref)
            if fresh!=proposal['selected_control_shunts'] or proof['ground_pad_uuid']!=force._uid(pad):
                raise ValueError('fresh_control_shunt_ground_boundary_authority_required')
            return dict(pad_uuid=force._uid(pad),ref=ref,role='source_control_shunt_ground',
                source_control_shunt=proof,no_power_bypass_or_current_reclassification=True)
        if ref in proposal.get('selected_programming_resistors',{}):
            import cec_programming_resistor_placement as programming
            if programming_context is None:
                programming_context=programming.plan(parent,proposal['poses'],board_hint=proposal['board_hint'],
                    reference_group_uuids=proposal.get('reference_group_uuids',()),
                    timeout_s=min(10.,max(.001,deadline-time.monotonic())),
                    **programming.replay_options(proposal))
            fresh=programming_context
            if fresh!=proposal['selected_programming_resistors']:
                raise ValueError('fresh_programming_resistor_Ground_boundary_authority_required')
            return programming.ground_root(fresh[ref],pad_uuid=force._uid(pad),reference=ref)
        if ref in proposal.get('selected_timing_capacitors',{}):
            import cec_source_timing_capacitor as timing
            if timing_context is None:
                timing_context=timing.plan(parent,proposal['poses'],board_hint=proposal['board_hint'],
                    reference_group_uuids=proposal.get('reference_group_uuids',()),
                    timeout_s=min(10.,max(.001,deadline-time.monotonic())),
                    **timing.replay_options(proposal))
            if timing_context!=proposal['selected_timing_capacitors']:
                raise ValueError('fresh_timing_capacitor_Ground_boundary_authority_required')
            return timing.ground_root(timing_context[ref],pad_uuid=force._uid(pad),reference=ref)
        model=roles.footprint_contract(fp)
        if (not model or model!=proposal['device_contracts'].get(ref)
                or set(model['pins'].values())&{'power_output','switch','feedback'}):return None
        role=model['pins'].get(pad.GetNumber())
        if role=='no_connect':
            # Restore existing externally attached metal ONLY after the
            # manufacturer's optional-Ground table and fresh canonical
            # schematic/export agree. This never turns an NC/DNC terminal
            # into a functional return, a bypass owner or a current path.
            attachment=roles.optional_ground_attachment_contract(fp,pad.GetNumber())
            if attachment is None:return None
            import cec_source_ground_leaf as source_ground
            import cec_source_netlist_semantics as source_semantics
            if optional_context is None:
                optional_context=source_ground.plan(parent,board_hint=proposal['board_hint'],
                    timeout_s=min(10.,max(.001,deadline-time.monotonic())))
            proof=optional_context.get('proofs',{}).get(force._uid(pad))
            if (optional_context.get('complete')is not True or optional_context.get('errors')
                    or type(proof)is not dict
                    or proof.get('kind')!='explicit_manufacturer_optional_ground_metal'
                    or proof.get('pad_uuid')!=force._uid(pad)or proof.get('owner')!=ref
                    or proof.get('pin')!=pad.GetNumber()or proof.get('net')!='GND'
                    or proof.get('manufacturer')!=attachment
                    or any(proof.get(k)is not False for k in
                        ('functional_ground_return','bypass_owner','current_authority','release_authority'))
                    or not source_ground.bindings_current([proof])):
                raise ValueError('fresh_source_optional_ground_attachment_required')
            canonical=source_semantics.replay_identity(proof)
            return dict(pad_uuid=force._uid(pad),ref=ref,role='source_optional_ground_attachment',
                primary_manufacturer_role='no_connect',manufacturer_source=model['source'],
                source_ground_attachment=canonical,functional_ground_return=False,
                current_authority=False,source_ground_strap_restored_without_role_or_current_reclassification=True)
        if role not in ('ground','reference','power_return','address'):return None
        if role=='address' and not any(p.GetNetname()=='GND'
                and model['pins'].get(p.GetNumber()) in ('ground','power_return') for p in fp.Pads()):
            return None
        return dict(pad_uuid=force._uid(pad),ref=ref,role=role,manufacturer_source=model['source'],
            source_ground_strap_restored_without_role_or_current_reclassification=True)
    def binding_files():
        """Only immutable input hashes from ACTUAL lazy canonical replays."""
        proofs=[q['source_proof']for context in(programming_context,shunt_context,timing_context)
            if context is not None for q in context.values()]
        if optional_context is not None:proofs.extend(optional_context.get('proofs',{}).values())
        bindings={}
        for proof in proofs:
            exporter=proof.get('exporter',{})
            for path,sha in [*proof.get('schematic_files_sha256',{}).items(),
                    *proof.get('evidence_files_sha256',{}).items(),
                    (exporter['exporter'],exporter['exporter_sha256'])]:
                if path in bindings and bindings[path]!=sha:
                    raise ValueError('macro_ground_boundary_conflicting_canonical_bindings')
                bindings[path]=sha
        return bindings
    def check():
        if time.monotonic()>=deadline:raise ValueError('macro_ground_boundary_typing_deadline')
        if (row._source_binding(parent)!=initial or force._code_identity()!=epoch
                or force._family(source,proposal.get('board_hint'))!=family
                or proposal!=original or transport!=original_transport):
            raise ValueError('macro_ground_boundary_same_call_inputs_changed')
        # Canonical hierarchy/exporter files can be outside the PCB's
        # saved family. Reuse no role after ANY of its fresh bindings
        # changes, including on an edge refused into the fallback.
        if any(force._hash(Path(p))!=sha for p,sha in binding_files().items()):
            raise ValueError('macro_ground_boundary_same_call_canonical_bindings_changed')
    def authority(edge):
        if (proposal.get('scope')!='source_typed_complete_cell_escape_proposal'
                or proposal.get('source_native_binding')!=initial):
            raise ValueError('changed_macro_ground_trunk_not_owned_by_cell_cut:'+force._uid(edge))
        check()
        try:return _ground_boundary_at_edge(parent,edge,transport,proposal,deadline,typed)
        finally:check()
    # No role/cut/current proof is exposed. The outer operation may retain
    # input identities after discarding this same-call lazy replay closure.
    authority.source_binding_hashes=binding_files
    authority.validate_source_inputs=check
    return authority


def _legacy_ground_boundary_authority(parent,edge,transport,proposal,deadline):
    """Standalone calls always derive a new private, single-call Source frame."""
    return _ground_boundary_typer(parent,transport,proposal,deadline)(edge)


def _ground_boundary_at_edge(parent,edge,transport,proposal,deadline,typed):
    """Unchanged per-edge native contacts, widths and singleton ownership."""
    pads={force._uid(p):p for fp in parent.GetFootprints() for p in fp.Pads()}
    live={force._uid(t):t for t in parent.GetTracks()}
    face=int(edge.GetLayer());ends=(edge.GetStart(),edge.GetEnd())
    roots=[]
    for pad in pads.values():
        if time.monotonic()>=deadline:raise ValueError('macro_ground_boundary_typing_deadline')
        if not pad.IsOnLayer(face) or pad.GetNetname()!='GND':continue
        if not edge.GetEffectiveShape(face).Collide(pad.GetEffectiveShape(face),0):continue
        proof=typed(pad)
        # Unknown/high-current lands anywhere on this small edge are not
        # silently acquired as though they were another low-power terminal.
        if proof is None:raise ValueError('changed_macro_ground_boundary_has_unowned_land:'+force._uid(pad))
        if any(pad.HitTest(at,0) for at in ends):roots.append(proof)
    barrel_roots=[]
    for barrel in transport['source_process_barrel_motion']:
        if time.monotonic()>=deadline:raise ValueError('macro_ground_boundary_typing_deadline')
        via=live[barrel['uuid']]
        if via.GetNetname()!='GND' or not any(at==via.GetPosition() for at in ends):continue
        owners=[typed(pads[u]) for u in barrel['source_owner_pad_uuids']]
        if not owners or any(p is None for p in owners):
            raise ValueError('changed_macro_ground_barrel_has_no_complete_low_power_owner')
        barrel_roots.append(dict(via_uuid=barrel['uuid'],source_terminal_owners=owners))
    if not roots and not barrel_roots:
        raise ValueError('changed_macro_ground_trunk_not_owned_by_cell_cut:'+force._uid(edge))
    # NETCLASS objects on a headless LoadBoard may belong to the last native
    # project opened in this process. The literal saved Source project, not
    # ambient Default state, owns this geometry floor. This supplies NO load
    # or aggregate Ground-current authority.
    source=Path(parent.GetFileName()).resolve(strict=True)
    import cec_route_dimensions as dimensions
    project=dimensions.project_path(source)
    if project is None:raise ValueError('saved_source_ground_class_geometry_required')
    spec=fr._project_netclass_resolver(str(source),board=parent)('GND') or {}
    canonical=fab.COPPER_LAYER_IDS[face]
    authored=spec.get('track_width')
    per_face=(spec.get('track_width_by_layer_mm')or{}).get(canonical,0.)
    if (type(authored)not in(int,float)or not math.isfinite(authored)or authored<=0
            or type(per_face)not in(int,float)or not math.isfinite(per_face)or per_face<0):
        raise ValueError('saved_source_ground_class_geometry_required')
    class_width=max(int(parent.GetDesignSettings().m_TrackMinWidth),
        math.ceil(authored*1e6),math.ceil(per_face*1e6))
    if not 0<edge.GetWidth()<=max(350000,class_width):
        raise ValueError('ground_boundary_exceeds_literal_source_class_width')
    return dict(kind='positive_existing_low_power_ground_boundary',native_source_uuid=force._uid(edge),
        source_pad_roots=roots,source_owned_barrel_roots=barrel_roots,
        source_width_nm=int(edge.GetWidth()),source_full_class_width_nm=class_width,
        source_class_geometry_origin='fresh_saved_source_project',
        source_class_project=str(project.resolve()),source_class_project_sha256=force._hash(project),
        source_width_preserved_not_aggregate_ground_injection_rating=True,
        every_source_partition_and_physical_return_still_requires_receiving=True,current_authority=False)


def _ground_boundary_authority(parent,edge,transport,proposal,deadline):
    """Standalone callers get a new private complete single-edge typer."""
    return _complete_ground_boundary_typer(parent,transport,proposal,deadline)(edge)


def _selected_cap_boundary_deadline(deadline):
    """Respect the narrower child operation without extending its parent."""
    now=time.monotonic()
    if (type(deadline)not in(int,float)or not math.isfinite(deadline)
            or not now<deadline<=now+10.):
        raise ValueError('bounded_inherited_ground_boundary_deadline_required')
    return min(deadline,now+9.7)


def _complete_ground_boundary_typer(parent,transport,proposal,deadline):
    """Keep legacy typing; extend only two positively rederived cap scopes.

    A fixed control port is not a Ground root. The existing whole macro,
    native components, local returns, current and saved observers still own
    construction/admission. Unknown fallback evidence retains the original
    refusal and its complete fresh failure cause.
    """
    legacy=_ground_boundary_typer(parent,transport,proposal,deadline)
    def authority(edge):
        try:
            try:return legacy(edge)
            except ValueError as original:
                if not str(original).startswith(('changed_macro_ground_boundary_has_unowned_land:',
                        'changed_macro_ground_trunk_not_owned_by_cell_cut:')):
                    raise
                from cec_selected_cap_ground_boundary import ownership
                try:proof=ownership(parent,proposal,[force._uid(edge)],
                    deadline=_selected_cap_boundary_deadline(deadline))
                except ValueError as fresh_failure:raise original from fresh_failure
                return proof['extras'][0]['authority']
        finally:legacy.validate_source_inputs()
    return authority


def _extra_ownership(parent,source,transport,proposal,deadline,held_factory_pickups=(),*,max_edges=8,
                     max_source_track_mm=8.,native_transport_options=None):
    """Legacy scopes consume both operations inside their ONE original lease."""
    steps=_extra_ownership_steps(parent,source,transport,proposal,deadline,held_factory_pickups,
        max_edges=max_edges,max_source_track_mm=max_source_track_mm,
        native_transport_options=native_transport_options)
    next(steps)
    return _finish_extra_ownership(steps,deadline)


def _finish_extra_ownership(steps,deadline):
    """No partial row/cut proof is returned before fresh singleton receiving."""
    import inspect,types
    if (type(steps)is not types.GeneratorType or steps.gi_code is not _extra_ownership_steps.__code__
            or inspect.getgeneratorstate(steps)!=inspect.GEN_SUSPENDED):
        raise ValueError('fresh_private_native_boundary_operation_required')
    try:steps.send(deadline)
    except StopIteration as complete:return complete.value
    raise ValueError('complete_ground_boundary_singleton_scopes_required')


def _extra_ownership_steps(parent,source,transport,proposal,deadline,held_factory_pickups=(),*,max_edges=8,
                     max_source_track_mm=8.,native_transport_options=None):
    """Two fixed operations, only explicitly composed by eight-stage compile.

    The suspended local frame is not an ownership certificate or an input
    cache. Every original singleton is still freshly checked; no incomplete
    extras escape, no old lease is reset, and all live inputs are fenced.
    """
    if type(max_edges) is not int or not 1<=max_edges<=64:
        raise ValueError('bounded_additional_macro_boundary_work_required')
    # This is the SAME explicit Source-work bound already available to
    # obstacle reconstruction. A transported boundary is not necessarily
    # shorter than an explicitly named obstacle. Retain the short default;
    # never infer a larger reach from pose distance, names or track width.
    if (type(max_source_track_mm)not in(int,float)or not math.isfinite(max_source_track_mm)
            or not 0<max_source_track_mm<=32.):
        raise ValueError('bounded_additional_macro_boundary_source_span_required')
    if time.monotonic()>=deadline:raise ValueError('macro_boundary_ownership_deadline')
    initial=row._source_binding(parent);epoch=force._code_identity()
    family_source=Path(parent.GetFileName()).resolve();family=force._family(family_source,proposal['board_hint'])
    proposal_snapshot=copy.deepcopy(proposal);original_transport=copy.deepcopy(transport);held=copy.deepcopy(held_factory_pickups)
    original_transport_options=copy.deepcopy(native_transport_options)
    import cec_source_ground_leaf as canonical_ground
    root=canonical_ground.source_nc._root(parent,proposal['board_hint']);canonical_files={};legacy_role_files={}
    if root is not None:
        _,canonical_files,_=canonical_ground._hierarchy(root,deadline)
    def check():
        if time.monotonic()>=deadline:raise ValueError('macro_boundary_ownership_deadline')
        if (initial!=row._source_binding(parent)or epoch!=force._code_identity()
                or family!=force._family(family_source,proposal['board_hint'])
                or proposal!=proposal_snapshot or transport!=original_transport or held_factory_pickups!=held
                or native_transport_options!=original_transport_options
                or any(force._hash(Path(p))!=sha for p,sha in [*canonical_files.items(),*legacy_role_files.items()])):
            raise ValueError('macro_boundary_ownership_live_inputs_changed')
    live={force._uid(t):t for t in parent.GetTracks()}
    ordinary_nets=ordinary.eligible_nets(parent,source,proposal['board_hint'])
    with force._thermal_hint(proposal['board_hint']):coupled_nets=set(fr.coupled_pair_nets(parent))
    owned=set(proposal['retired_track_uuids']);extras=[];pending=[];ground_typer=None
    # _frame independently derives this complete component from literal
    # Source on construction AND saved reconstruction. Never infer a carried
    # subset from the caller's changed-track list or from group membership.
    isolated={u for q in transport.get('rigid_isolated_selected_bypass_supply_components',[])
        for u in q['track_uuids']}
    if isolated&owned:raise ValueError('isolated_supply_transport_overlaps_source_planned_cut')
    for change in transport['changes']:
        if time.monotonic()>=deadline:raise ValueError('macro_boundary_ownership_deadline')
        uid=change['uuid'];t=live[uid]
        if uid in isolated:continue
        if (t.GetClass()!='PCB_TRACK' or t.GetParentGroup() is not None
                or uid in owned or uid in held_factory_pickups):continue
        points=change.get('source_nm')
        if (change.get('net')!=str(t.GetNetname()) or type(points) not in (list,tuple)
                or len(points)!=2 or any(type(p) not in (list,tuple) or len(p)!=2
                    or any(type(n) is not int for n in p) for p in points)
                or list(map(list,points))!=[list(t.GetStart()),list(t.GetEnd())]):
            raise ValueError('literal_macro_boundary_source_edge_changed')
        if (t.HasSolderMask() or not 0<t.GetWidth() or not 0<t.GetLength()<=max_source_track_mm*1e6):
            raise ValueError('changed_macro_boundary_not_a_bounded_small_source_edge:'+uid)
        if t.GetNetname()=='GND':
            try:
                if ground_typer is None:ground_typer=_ground_boundary_typer(parent,transport,proposal,deadline)
                authority=ground_typer(t)
            except ValueError as original:
                if not str(original).startswith(('changed_macro_ground_boundary_has_unowned_land:',
                        'changed_macro_ground_trunk_not_owned_by_cell_cut:')):
                    raise
                pending.append((len(extras),original));authority=None
        elif t.GetNetname()in coupled_nets:
            # A protected coupled member is neither an ordinary edge nor an
            # unrated supply. It needs a separately complete pair adapter;
            # never invent amperes or route just its inconvenient member.
            raise ValueError('complete_protected_pair_boundary_reconstruction_required:'+uid+':'+str(t.GetNetname()))
        elif t.GetNetname() in ordinary_nets:
            if t.GetWidth()>350000:
                raise ValueError('changed_ordinary_macro_boundary_exceeds_small_source_width:'+uid)
            authority=dict(kind='positive_source_ordinary',native_source_uuid=uid)
        else:
            work=({'max_source_track_mm':max_source_track_mm}if max_source_track_mm!=8. else {})
            try:
                plan=full.plan(parent,source,board_hint=proposal['board_hint'],retired_track_uuids=[uid],
                    timeout_s=min(10.,max(.001,deadline-time.monotonic())),**work)
            except ValueError as exc:
                # Unknown or paired contacts must never look like a request
                # to invent a supply budget. Preserve the actual physical
                # boundary/net and original complete fail stack for review.
                raise ValueError('macro_boundary_authority_required:'+uid+':'+str(t.GetNetname())+':'+str(exc))from exc
            authority=dict(kind='unchanged_full_current_source_edge',native_source_uuid=uid,source_plan=plan)
        extras.append(dict(change=change,authority=authority))
    if len(extras)>max_edges:raise ValueError('bounded_additional_macro_boundary_cohort_required')
    check()
    # Drop the per-operation lazy typer; no earlier role replay is reused by
    # the independent multiport observer in the next named operation.
    legacy_role_files={}if ground_typer is None else ground_typer.source_binding_hashes()
    ground_typer=None
    next_deadline=yield 'canonical_ground_multiport_boundary'
    if (type(next_deadline)not in(int,float)or not math.isfinite(next_deadline)
            or not time.monotonic()<next_deadline<=time.monotonic()+10.):
        raise ValueError('bounded_fresh_ground_multiport_operation_required')
    deadline=next_deadline
    check()
    try:
        if pending:
            # Original singleton cut/retained-port scope, fresh Source
            # proposal recompile, no supplied proof or union-cut shortcut.
            ids=[extras[index]['change']['uuid']for index,_ in pending]
            try:derived=_pending_ground_ownership(parent,proposal,ids,transport,
                deadline=_selected_cap_boundary_deadline(deadline),
                native_transport_options=native_transport_options)
            except ValueError as failure:raise pending[0][1] from failure
            by_uid={q['change']['uuid']:q['authority']for q in derived}
            for index,_ in pending:
                extras[index]['authority']=by_uid[extras[index]['change']['uuid']]
        return extras
    finally:check()


def _pending_ground_ownership(parent,proposal,ids,transport,*,deadline,native_transport_options):
    """Separate Source-stage contacts from the old selected-cap extension.

    Contact geometry selects a checker, never grants ownership. Each checker
    rederives its own complete Source, current and literal contact evidence.
    A power stage never silently becomes a legacy low-power Ground owner.
    """
    from cec_selected_cap_ground_boundary import single_edge_ownerships
    import cec_linear_stage_ground_boundary as linear_boundary
    live={force._uid(t):t for t in parent.GetTracks()}
    stage_refs=set(proposal.get('source_linear_power_stages',{}))
    pads=[p for f in parent.GetFootprints()if f.GetReference()in stage_refs
        for p in f.Pads()if p.GetNetname()=='GND']
    selected=[];linear=[]
    for uid in ids:
        edge=live[uid];face=int(edge.GetLayer())
        moving_stage_contact=any(p.IsOnLayer(face)
            and edge.GetEffectiveShape(face).Collide(p.GetEffectiveShape(face),0)for p in pads)
        (linear if moving_stage_contact else selected).append(uid)
    result=[]
    if linear:
        if native_transport_options is None:
            raise ValueError('independent_Source_stage_transport_intents_required')
        consent=([uid for uid in linear if live[uid].IsLocked()]
            if proposal.get('allow_owned_locked_escapes')is True else [])
        # Adjacent changed stage straps are one explicit cut cohort. Prove
        # every edge together so a peer cut is not fabricated as retained
        # copper. The component consumer requires the complete same cohort.
        derived=linear_boundary.ownership(parent,proposal,linear,
            deadline=_selected_cap_boundary_deadline(deadline),allow_locked_track_uuids=consent,
            native_transport_options=native_transport_options)['extras']
        if any(not linear_boundary.transport_matches(q['authority'],transport)for q in derived):
            raise ValueError('independent_Source_stage_transport_frame_changed')
        result.extend(derived)
    if selected:
        result.extend(single_edge_ownerships(parent,proposal,selected,
            deadline=_selected_cap_boundary_deadline(deadline)))
    if len(result)!=len(ids)or {q['change']['uuid']for q in result}!=set(ids):
        raise ValueError('complete_disjoint_ground_boundary_roles_required')
    return result


def _retained_ground_dogbones(parent,private,transport):
    """Carry a complete native source factory pickup instead of cutting it."""
    old={force._uid(t):t for t in parent.GetTracks()}
    new={force._uid(t):t for t in private.GetTracks()}
    old_pads={force._uid(p):p for f in parent.GetFootprints() for p in f.Pads()}
    pads={force._uid(p):p for f in private.GetFootprints() for p in f.Pads()}
    changes={q['uuid']:q for q in transport['changes']};result=[]
    for proof in transport['source_process_barrel_motion']:
        uid=proof['uuid'];via=old[uid]
        if via.GetNetname()!='GND':continue
        for owner in proof['source_owner_pad_uuids']:
            p,q=old_pads[owner],pads[owner];face=cells.cec_return_escape.smd_surface_layer(p)
            child_via=new[uid]
            if child_via.GetNetname()!=via.GetNetname()or q.GetNetname()!=p.GetNetname():
                raise ValueError('transported_source_ground_pickup_authored_net_changed')
            for key,t in old.items():
                change=changes.get(key)
                seat=proof.get('source_control_shunt_return_axis')
                role=None if type(seat)is not dict else seat.get('source_control_shunt')
                if type(seat)is dict and 'source_programming_resistor'in seat:
                    import cec_programming_resistor_placement as programming
                    item=seat['source_programming_resistor']
                    label=programming.ground_root(item,pad_uuid=owner,
                        reference=item['source_resistor_identity']['reference'])
                    if programming.ground_root_label(label):role=item
                controlled=(type(seat)is dict and seat.get('uuid')==uid
                    and seat.get('owner_pad_uuid')==owner and seat.get('source_tail_uuid')==key
                    and proof.get('source_dogbone_uuid')==key
                    and type(role)is dict and role.get('ground_pad_uuid')==owner)
                if (t.GetClass()!='PCB_TRACK' or t.GetNetname()!='GND' or t.GetLayer()!=face
                        or change is None or change['provisional_boundary_reconstruction_required']and not controlled):continue
                if controlled:
                    after=new[key]
                    if (t.GetWidth()!=seat['source_full_width_nm']or after.GetWidth()!=t.GetWidth()
                            or after.GetLayer()!=face
                            or after.GetLength()>seat['maximum_return_nm']
                            or after.GetLength()+10000>=t.GetLength()):
                        raise ValueError('exact_shorter_full_source_control_ground_pickup_required')
                ends=((t.GetStart(),t.GetEnd()),(t.GetEnd(),t.GetStart()))
                if not any(tuple(b)==tuple(via.GetPosition()) and fab.local_pofv_dogbone_matches(
                        p,a,b,face,via.GetNetCode()) for a,b in ends):continue
                after=new[key]
                if not any(tuple(b)==tuple(child_via.GetPosition()) and fab.local_pofv_dogbone_matches(
                        q,a,b,face,child_via.GetNetCode()) for a,b in
                        ((after.GetStart(),after.GetEnd()),(after.GetEnd(),after.GetStart()))):
                    raise ValueError('transported_source_ground_dogbone_not_reproved')
                result.append(dict(uuid=key,via_uuid=uid,owner_pad_uuid=owner,
                    source_factory_pickup_retained_not_retired=True))
    return sorted({q['uuid']:q for q in result}.values(),key=lambda q:q['uuid'])


def _project_port(parent,private,port,transport,retired):
    """An exact native source identity, never a nearest same-net target."""
    result=copy.deepcopy(port);uids=port.get('native_uuids')
    if not uids:return result
    old={force._uid(t):t for t in parent.GetTracks()}
    new={force._uid(t):t for t in private.GetTracks()}
    old.update({force._uid(p):p for f in parent.GetFootprints() for p in f.Pads()})
    new.update({force._uid(p):p for f in private.GetFootprints() for p in f.Pads()})
    moved={q['uuid'] for q in transport['source_process_barrel_motion']}
    moved.update(q['uuid'] for q in transport.get('explicit_source_typed_ordinary_barrel_motion',()))
    moved.update(q['uuid'] for q in transport.get('explicitly_reproved_private_signal_port_reseats',()))
    # These proofs are freshly rederived from literal Source and the actual
    # frame by macro.apply, including on independent saved reconstruction.
    # Keep the original mandatory contact; only its exact native position
    # follows the complete isolated component. This grants no new cut/join.
    isolated_motion={}
    for component in transport.get('rigid_isolated_selected_bypass_supply_components',()):
        import cec_source_supply_endpoint_cut as isolated_supply
        rows=component['tracks'];ids=component['track_uuids'];delta=component['delta_nm']
        pads=component['supply_pad_uuids']
        if (component.get('scope')!='rigid_complete_isolated_selected_bypass_supply_component'
                or len(set(ids))!=len(ids) or set(ids)!={q['uuid']for q in rows}
                or len(pads)!=2 or len(set(pads))!=2
                or set(ids)&set(retired) or len(delta)!=2 or any(type(v)is not int for v in delta)):
            raise ValueError('complete_retained_isolated_supply_port_scope_required')
        # Even this internal projection rechecks whole native connectivity;
        # a partial recorded component cannot manufacture a moved port.
        for native,items in ((parent,old),(private,new)):
            if any(u not in items or items[u].GetClass()!='PAD'for u in pads):
                raise ValueError('complete_isolated_supply_native_pad_identity_required')
            graph=fr._read_only_route_connectivity(native)
            reached={force._uid(i)for i in graph.GetConnectedItems(items[pads[0]])}|{pads[0]}
            if reached!=set(pads)|set(ids):
                raise ValueError('complete_isolated_supply_native_port_component_required')
        authority=component['source_selected_bypass']
        cap=parent.FindFootprintByReference(authority['cap_ref'])
        owner=parent.FindFootprintByReference(authority['owner'])
        if cap is None or owner is None:
            raise ValueError('literal_isolated_supply_native_owners_required')
        caplands=[p for p in cap.Pads()if force._uid(p)in pads]
        supply=owner.FindPadByNumber(authority['supply_pin'])
        if len(caplands)!=1 or supply is None or {force._uid(caplands[0]),force._uid(supply)}!=set(pads):
            raise ValueError('literal_isolated_supply_selected_lands_required')
        fresh_motion=isolated_supply.selected_component_motion(caplands[0],new[force._uid(caplands[0])],
            supply,new[force._uid(supply)],allow_cardinal_rotations=True)
        if (component['delta_nm']!=fresh_motion['delta_nm']
                or component.get('cardinal_transform')!=fresh_motion.get('cardinal_transform')):
            raise ValueError('fresh_isolated_supply_common_native_transform_required')
        for row in rows:
            uid=row['uuid'];a=old.get(uid);b=new.get(uid)
            if (uid in isolated_motion or a is None or b is None
                    or a.GetClass()!='PCB_TRACK' or b.GetClass()!='PCB_TRACK'
                    or a.GetNetname()!=b.GetNetname() or a.GetLayer()!=b.GetLayer()
                    or a.GetLayer()!=component['layer_id']
                    or a.GetWidth()!=row['width_nm'] or b.GetWidth()!=a.GetWidth()
                    or bool(a.IsLocked())!=row['locked'] or b.IsLocked()!=a.IsLocked()
                    or [list(a.GetStart()),list(a.GetEnd())]!=row['source_nm']
                    or [list(b.GetStart()),list(b.GetEnd())]!=row['candidate_nm']
                    or row['candidate_nm']!=[list(isolated_supply.component_point(fresh_motion,p))
                        for p in row['source_nm']]):
                raise ValueError('fresh_complete_isolated_supply_native_port_motion_required')
            isolated_motion[uid]=fresh_motion
    pickups=None
    points=set();layers=set();kept=[]
    for uid in uids:
        if uid in retired:continue
        if uid not in old or uid not in new:raise ValueError('macro_source_port_native_identity_missing')
        a,b=old[uid],new[uid]
        if a.GetNetname()!=b.GetNetname() or a.GetClass()!=b.GetClass():
            raise ValueError('macro_source_port_identity_changed')
        at=tuple(port['at_nm'])
        source_faces=[l for l in port['layers'] if a.IsOnLayer(l)
            and a.GetEffectiveShape(l).Collide(pcbnew.VECTOR2I(*at),0)]
        if not source_faces:raise ValueError('macro_source_port_has_no_literal_source_contact')
        if uid in moved:
            at=tuple(at[i]+b.GetPosition()[i]-a.GetPosition()[i] for i in (0,1))
        elif uid in isolated_motion:
            at=isolated_supply.component_point(isolated_motion[uid],at)
        elif a.GetClass()=='PCB_TRACK' and a.GetNetname()=='GND':
            # A retained factory dogbone follows the same rigid Source
            # owner as its barrel. Re-derive that ownership from the real
            # lands and pickup, never infer motion from the net or a port
            # label. A shared via/dogbone contact must not split into a
            # fictitious stationary attachment after the exact transform.
            if pickups is None:
                pickups={q['uuid']:q for q in _retained_ground_dogbones(parent,private,transport)}
            if uid in pickups:
                p=old[uid];owner=pickups[uid]['owner_pad_uuid']
                first=next(q for f in parent.GetFootprints() for q in f.Pads() if force._uid(q)==owner).GetParentFootprint()
                last=next(q for f in private.GetFootprints() for q in f.Pads() if force._uid(q)==owner).GetParentFootprint()
                turn=(last.GetOrientationDegrees()-first.GetOrientationDegrees())%360
                if turn not in (0,90,180,270):raise ValueError('source_pickup_port_needs_exact_cardinal_transform')
                c,s=round(math.cos(math.radians(turn))),round(math.sin(math.radians(turn)))
                x,y=at[0]-first.GetPosition().x,at[1]-first.GetPosition().y
                at=(last.GetPosition().x+c*x+s*y,last.GetPosition().y-s*x+c*y)
        for face in source_faces:
            if not b.IsOnLayer(face) or not b.GetEffectiveShape(face).Collide(pcbnew.VECTOR2I(*at),0):
                raise ValueError('projected_macro_port_not_on_actual_retained_native_copper')
            layers.add(int(face))
        points.add(at);kept.append(uid)
    if not kept or len(points)!=1:raise ValueError('macro_boundary_port_missing_or_disagreeing_native_projection:'+repr(uids))
    result.update(at_nm=list(next(iter(points))),layers=sorted(layers),native_uuids=sorted(kept))
    return result


def _edge_end(parent,private,at,net,face,transport,retired,*,separate_contacts=False):
    pads=[p for f in parent.GetFootprints() for p in f.Pads()
        if p.GetNetname()==net and p.IsOnLayer(face)
        and p.GetEffectiveShape(face).Collide(pcbnew.VECTOR2I(*at),0)]
    if len(pads)>1:raise ValueError('ambiguous_macro_source_edge_pad_contact')
    if pads:
        uid=force._uid(pads[0]);p=next(p for f in private.GetFootprints() for p in f.Pads() if force._uid(p)==uid)
        end=dict(pad_uuid=uid,at_nm=list(p.GetPosition()),
            layers=[int(l) for l in p.GetLayerSet().CuStack() if private.IsLayerEnabled(l)])
        return [end] if separate_contacts else end
    uids=[force._uid(t) for t in parent.GetTracks() if force._uid(t) not in retired
        and t.GetNetname()==net and t.IsOnLayer(face)
        and t.GetEffectiveShape(face).Collide(pcbnew.VECTOR2I(*at),0)]
    if not uids:raise ValueError('additional_macro_edge_has_no_literal_surviving_source_port')
    port=dict(at_nm=list(at),layers=[int(face)],native_uuids=sorted(uids))
    return (_project_contacts(parent,private,port,transport,retired) if separate_contacts else
        _project_port(parent,private,port,transport,retired))


def _project_contacts(parent,private,port,transport,retired):
    """Keep EVERY literal contact when one old port separates in a macro.

    A source via and a stationary track may share one original point. Once
    the owned via moves, they are two independent restoration targets, not
    a nearest-net substitution or permission to drag the stationary trace.
    The strict one-port primitive remains strict for all other callers.
    """
    uids=port.get('native_uuids')
    if not uids:return [_project_port(parent,private,port,transport,retired)]
    if (type(uids) not in (list,tuple) or not 1<=len(uids)<=16 or len(set(uids))!=len(uids)
            or any(type(u) is not str or not u for u in uids)):
        raise ValueError('bounded_literal_macro_source_contact_inventory_required')
    groups={}
    for uid in uids:
        if uid in retired:continue
        literal=dict(port,native_uuids=[uid])
        projected=_project_port(parent,private,literal,transport,retired)
        key=(tuple(projected['at_nm']),tuple(projected['layers']))
        if key not in groups:groups[key]=projected
        else:groups[key]['native_uuids']+=projected['native_uuids']
    if not groups:raise ValueError('macro_source_contact_has_no_retained_literal_target')
    return [groups[k] for k in sorted(groups)]


def _compose_retained_demands(parent,requests,extras,*,board_hint=None,deadline=None,source_proposal=None):
    """An old retained-edge target can become an explicit new edge demand.

    Consume it only when that SAME source edge has a positively typed new
    obligation at the SAME original pad endpoint. Interior taps, anonymous
    points, partial groups and merely same-net edges cannot substitute.
    """
    if deadline is None:deadline=time.monotonic()+10.
    if not time.monotonic()<deadline<=time.monotonic()+10.:
        raise ValueError('bounded_retained_contact_composition_lease_required')
    binding=row._source_binding(parent)
    by_id={q['change']['uuid']:q for q in extras};extra_ids=set(by_id)
    if len(by_id)!=len(extras):raise ValueError('unique_retained_contact_cut_ownership_required')
    tracks={force._uid(t):t for t in parent.GetTracks()}
    pads={force._uid(p):p for f in parent.GetFootprints() for p in f.Pads()}
    base=set(source_proposal.get('retired_track_uuids',[]))if type(source_proposal)is dict else set()
    remaining={};composed=[];inventories={};rail_contracts={};eligible=None
    for key,request in requests.items():
        if time.monotonic()>=deadline:raise ValueError('retained_contact_composition_deadline')
        target=request.get('b',{});uids=target.get('native_uuids',[])
        pad=pads.get(request.get('a',{}).get('pad_uuid'))
        legacy=key.startswith('retained:')
        contact=request.get('source_pad_track_contact')
        base_contact=(not legacy and contact is not None and len(uids)==1
            and uids[0]in base and uids[0]not in extra_ids)
        if ((not legacy and contact is None)or len(uids)!=1
                or uids[0]not in extra_ids and not base_contact or pad is None):
            remaining[key]=request;continue
        t=tracks[uids[0]];face=t.GetLayer()
        required_width=request['width_nm'];typed=None
        if not legacy:
            # A positively inventoried terminal contact is not tied to its
            # producer's request spelling. Independently re-inventory the
            # immutable Source land, then compose only the SAME actual edge
            # endpoint into an ALREADY owned complete cut component. This
            # acquires no copper and cannot consume an interior/nearby tap.
            import cec_pad_incident_tracks as incident
            puid=force._uid(pad)
            if puid not in inventories:
                inventories[puid]=incident.inspect(parent,[pad])
            observed=inventories[puid]
            if (request.get('kind')!='source_boundary'or request.get('net')=='GND'
                    or type(contact)is not dict or observed.get('ok')is not True
                    or contact not in observed['contacts']
                    or contact.get('pad_uuid')!=puid or contact.get('track_uuid')!=uids[0]
                    or contact.get('contact_nm')!=target.get('at_nm')
                    or target.get('layers')!=[int(face)]):
                raise ValueError('fresh_exact_source_pad_track_contact_required')
            if base_contact:
                replacement=requests.get('boundary:'+uids[0])
                if (source_proposal.get('scope')!='source_typed_complete_cell_escape_proposal'
                        or source_proposal.get('source_native_binding')!=binding
                        or pad.GetParentFootprint().GetReference()not in source_proposal.get('poses',{})
                        or type(replacement)is not dict or replacement.get('kind')!='source_boundary'
                        or replacement.get('net')!=request['net']
                        or replacement.get('width_nm',0)<request['width_nm']
                        or puid not in {replacement.get(end,{}).get('pad_uuid')for end in('a','b')}
                        or request.get('unchanged_full_rail_current_contract')is not None):
                    raise ValueError('same_existing_positive_source_base_endpoint_obligation_required')
                authority=dict(kind='positive_source_ordinary',native_source_uuid=uids[0])
                change=dict(net=t.GetNetname(),source_nm=[list(t.GetStart()),list(t.GetEnd())])
            else:
                authority=by_id[uids[0]].get('authority',{})
                change=by_id[uids[0]].get('change',{})
            points=change.get('source_nm')
            if (change.get('net')!=t.GetNetname()or type(points)not in(list,tuple)
                    or len(points)!=2 or any(type(p)not in(list,tuple)or len(p)!=2
                        or any(type(n)is not int for n in p)for p in points)
                    or list(map(list,points))!=[list(t.GetStart()),list(t.GetEnd())]):
                raise ValueError('literal_independently_owned_source_contact_edge_required')
            if authority.get('native_source_uuid')!=uids[0]:
                raise ValueError('independent_source_contact_cut_authority_required')
            if authority.get('kind')=='positive_source_ordinary':
                if eligible is None:
                    eligible=ordinary.eligible_nets(parent,Path(parent.GetFileName()),board_hint)
                if (request['net']not in eligible or authority!={
                        'kind':'positive_source_ordinary','native_source_uuid':uids[0]}
                        or request.get('unchanged_full_rail_current_contract')is not None):
                    raise ValueError('same_positive_ordinary_source_contact_required')
            elif authority.get('kind')=='unchanged_full_current_source_edge':
                if type(board_hint)is not str or not board_hint:
                    raise ValueError('full_current_contact_source_context_required')
                net=request['net']
                if net not in rail_contracts:
                    with force._thermal_hint(board_hint):
                        rail_contracts[net]=cells._supply_current_widths(parent,net)
                rail=rail_contracts[net];saved=authority.get('source_plan',{})
                stable=lambda value:json.loads(json.dumps(value,allow_nan=False))
                widths=rail.get('required_by_layer_nm')if type(rail)is dict else None
                if (type(widths)is not dict or int(face)not in widths
                        or type(widths[int(face)])is not int or widths[int(face)]<=0
                        or stable(rail)!=stable(request.get('unchanged_full_rail_current_contract'))
                        or saved.get('scope')!='exact_bounded_whole_current_planar_reflow'
                        or saved.get('retired_track_uuids')!=[uids[0]]or saved.get('net')!=net
                        or saved.get('layer_id')!=int(face)or saved.get('width_nm')!=t.GetWidth()
                        or type(saved.get('full_current_floor_nm'))is not int
                        or not widths[int(face)]<=saved['full_current_floor_nm']<=t.GetWidth()
                        or request['width_nm']<widths[int(face)]):
                    raise ValueError('same_fresh_full_current_source_contact_required')
                # The request's scalar width can reserve the largest inner
                # layer floor. It is not the width of this literal Source
                # face. Complete component demands retain the SAME contract
                # and independently enforce each routed layer's floor.
                required_width=widths[int(face)]
            else:raise ValueError('independent_source_contact_cut_authority_required')
            typed=dict(source_pad_track_contact=copy.deepcopy(contact),
                literal_source_face_width_floor_nm=required_width,
                independent_cut_authority_kind=authority['kind'])
        if (t.GetNetname()!=request['net'] or pad.GetNetname()!=request['net']
                or not pad.IsOnLayer(face) or t.GetWidth()<required_width
                or not any(tuple(v)==tuple(target['at_nm'])
                    and pad.GetEffectiveShape(face).Collide(pcbnew.SHAPE_CIRCLE(v,(t.GetWidth()+1)//2),0)
                    for v in (t.GetStart(),t.GetEnd()))):
            raise ValueError('retained_macro_demand_not_the_same_typed_source_edge_endpoint')
        composed.append(dict(original_request_id=key,original_request=request,
            required_replacement_request_id='macro_boundary:'+uids[0],source_pad_uuid=force._uid(pad),
            exact_source_edge_endpoint_obligation_composed_not_omitted=True))
        if base_contact:
            composed[-1].update(required_replacement_request_id='boundary:'+uids[0],
                required_replacement_request_ids=['boundary:'+uids[0]],
                source_existing_base_endpoint_obligation_composed_not_omitted=True)
        if typed is not None:composed[-1]['independent_native_terminal_contact_composition']=typed
    if row._source_binding(parent)!=binding or time.monotonic()>=deadline:
        raise ValueError('retained_contact_composition_source_changed_or_expired')
    return remaining,composed


def compile(source,poses,*,board_hint,max_shift_mm=6.,timeout_s=10.,allow_owned_locked_escapes=False,
            rebuild_projected_ground=False,additional_obstacle_track_uuids=(),reuse_ground_barrels=(),
            ordinary_via_poses=(),max_obstacle_track_mm=8.,max_obstacle_tracks=8,required_ground_pad_entries=(),
            stationary_ground_barrel_uuids=(),allow_octilinear_rotations=False,required_supply_departures=(),
            local_signal_port_offsets=(),reference_group_uuids=(),required_ordinary_nets=(),
            allow_full_width_supply_obstacles=False,compilation_phase_timeouts_s=None,required_new_ground_dogbones=(),
            control_shunt_ground_return_axes=(),required_measurement_corridors=(),source_rc_input_prefixes=(),
            required_quiet_output_pad_uuids=(),aggregate_capacitor_max_shift_mm=None,
            allow_linear_power_stage_reconstruction=False,shared_supply_root_pad_uuids=()):
    """Return an exact private frame and all positive reconstruction demands."""
    if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10.
            or type(rebuild_projected_ground) is not bool or type(allow_octilinear_rotations) is not bool
            or type(allow_full_width_supply_obstacles) is not bool
            or type(allow_linear_power_stage_reconstruction) is not bool
            or type(max_obstacle_track_mm) not in (int,float) or not math.isfinite(max_obstacle_track_mm)
            or not 0<max_obstacle_track_mm<=32.
            or type(max_obstacle_tracks) is not int
            or not (1<=max_obstacle_tracks<=16 or max_obstacle_tracks==32)
            or type(required_ordinary_nets) not in (tuple,list) or len(required_ordinary_nets)>4):
        raise ValueError('bounded_macro_request_compilation_required')
    escape.aggregate_cap_shift_bound(aggregate_capacitor_max_shift_mm)
    shared_supply_root_pad_uuids=escape.shared_fork.supply_root_ids(shared_supply_root_pad_uuids)
    explicit_obstacles=ordinary._ids(additional_obstacle_track_uuids,'additional_source_native_obstacle_cut',max_obstacle_tracks)
    import cec_macro_measurement_corridor as corridor
    required_measurement_corridors=corridor.requests(required_measurement_corridors)
    import cec_macro_rc_input_prefix as rc_prefix
    source_rc_input_prefixes=rc_prefix.requests(source_rc_input_prefixes)
    import cec_macro_quiet_output as quiet_outputs
    required_quiet_output_pad_uuids=quiet_outputs.ids(required_quiet_output_pad_uuids)
    leases=_CompilationLeases(timeout_s,compilation_phase_timeouts_s)
    deadline=leases.deadline;source=Path(source).resolve()
    epoch=force._code_identity();family=force._family(source,board_hint);parent=pcbnew.LoadBoard(str(source))
    parent_binding=row._source_binding(parent)
    def same_live_inputs():
        return (epoch==force._code_identity()and family==force._family(source,board_hint)
            and parent_binding==row._source_binding(parent))
    prepare=escape.prepare
    phase_options={}
    if len(leases.phases)==9:
        prepare=escape._prepare_split_source
        phase_options=dict(deadline=deadline,
            advance=lambda:leases.advance('source_contact_ownership',same_live_inputs))
    proposal=prepare(parent,poses,board_hint=board_hint,max_shift_mm=max_shift_mm,
        allow_owned_locked_escapes=allow_owned_locked_escapes,rebuild_projected_ground=rebuild_projected_ground,
        allow_octilinear_rotations=allow_octilinear_rotations,reference_group_uuids=reference_group_uuids,
        source_rc_input_prefixes=source_rc_input_prefixes,**phase_options,
        **(dict(aggregate_capacitor_max_shift_mm=aggregate_capacitor_max_shift_mm)
            if aggregate_capacitor_max_shift_mm is not None else {}),
        **(dict(allow_linear_power_stage_reconstruction=True)
            if allow_linear_power_stage_reconstruction else {}),
        **(dict(shared_supply_root_pad_uuids=shared_supply_root_pad_uuids)
            if shared_supply_root_pad_uuids else {}))
    deadline=leases.advance('native_frame_and_cuts',same_live_inputs)
    private,transport=_frame(parent,source,proposal,reuse_ground_barrels=reuse_ground_barrels,
        ordinary_via_poses=ordinary_via_poses,stationary_ground_barrel_uuids=stationary_ground_barrel_uuids,
        local_signal_port_offsets=local_signal_port_offsets,control_shunt_ground_return_axes=control_shunt_ground_return_axes,
        timeout_s=min(10.,max(.001,deadline-time.monotonic())))
    import cec_stationary_ground_forest as forest
    proposal=forest.refine(parent,private,proposal,
        timeout_s=min(10.,max(.001,deadline-time.monotonic())))
    import cec_macro_ground_ingress as ingress
    required_ground,_=ingress.plan(parent,private,proposal,required_ground_pad_entries,
        timeout_s=min(10.,max(.001,deadline-time.monotonic())))
    import cec_macro_new_ground_dogbone as dogbone
    required_new_ground,_=dogbone.plan(parent,private,proposal,required_new_ground_dogbones,
        timeout_s=min(10.,max(.001,deadline-time.monotonic())))
    if {p['pad_uuid']for p in required_ground}&{p['pad_uuid']for p in required_new_ground}:
        raise ValueError('distinct_new_and_preserved_ground_entry_intents_required')
    import cec_macro_supply_departure as departure
    required_supply,_=departure.plan(parent,private,proposal,required_supply_departures,
        timeout_s=min(10.,max(.001,deadline-time.monotonic())))
    required_corridors,_=corridor.plan(parent,private,proposal,required_measurement_corridors,
        timeout_s=min(10.,max(.001,deadline-time.monotonic())))
    pickups=_retained_ground_dogbones(parent,private,transport)
    retained_pickups={q['uuid'] for q in pickups}
    # A complete four-device cohort can have more than eight existing
    # input/output barrel boundaries. This is only an explicit work budget:
    # every edge still needs its independent Source/current ownership, and
    # the base cut stays capped at 64, the composite cut at 64+64, and
    # the total constructive request count remains capped at 64.
    boundary_work=({'max_source_track_mm':max_obstacle_track_mm}if max_obstacle_track_mm!=8. else {})
    if allow_linear_power_stage_reconstruction:
        boundary_work['native_transport_options']=dict(reuse_ground_barrels=reuse_ground_barrels,
            ordinary_via_poses=ordinary_via_poses,stationary_ground_barrel_uuids=stationary_ground_barrel_uuids,
            local_signal_port_offsets=local_signal_port_offsets,
            control_shunt_ground_return_axes=control_shunt_ground_return_axes)
    if len(leases.phases)in(4,6,8,9):
        deadline=leases.advance('canonical_boundary_ownership',same_live_inputs)
    if len(leases.phases)in(8,9):
        boundary_steps=_extra_ownership_steps(parent,source,transport,proposal,deadline,retained_pickups,
            max_edges=min(64,8*len(poses)),**boundary_work)
        if next(boundary_steps)!='canonical_ground_multiport_boundary':
            raise ValueError('ordered_native_boundary_operations_required')
        deadline=leases.advance('canonical_ground_multiport_boundary',same_live_inputs)
        extras=_finish_extra_ownership(boundary_steps,deadline)
        deadline=leases.advance('canonical_boundary_composition',same_live_inputs)
    else:
        extras=_extra_ownership(parent,source,transport,proposal,deadline,retained_pickups,
            max_edges=min(64,8*len(poses)),**boundary_work)
    if explicit_obstacles:
        import cec_macro_obstacle_cuts as obstacle_cuts
        extras+=obstacle_cuts.ownership(parent,private,source,proposal,sorted(explicit_obstacles),
            excluded_uuids=set(proposal['retired_track_uuids'])|retained_pickups|{q['change']['uuid'] for q in extras},
            transported_barrel_uuids=[q['uuid'] for q in [*transport['source_process_barrel_motion'],
                *transport['explicit_source_typed_ordinary_barrel_motion'],
                *transport['explicitly_reproved_private_signal_port_reseats']]],
            allow_locked=allow_owned_locked_escapes,deadline=deadline,max_source_track_mm=max_obstacle_track_mm,
            max_tracks=max_obstacle_tracks,required_ground_pad_entries=required_ground_pad_entries,
            required_supply_departures=required_supply_departures,
            required_new_ground_dogbones=required_new_ground_dogbones,
            required_measurement_corridors=required_measurement_corridors,
            allow_full_width_supply_obstacles=allow_full_width_supply_obstacles,
            existing_ground_cut_rows=[q for q in extras
                if q.get('authority',{}).get('kind')=='positive_existing_low_power_ground_boundary'])
    if len(extras)>64:raise ValueError('bounded_additional_macro_boundary_cohort_required')
    endpoint_cuts=transport.get('source_ground_endpoint_restoration_cuts',[])
    supply_endpoint_cuts=transport.get('source_supply_endpoint_restoration_cuts',[])
    endpoint_retirements={u for q in [*endpoint_cuts,*supply_endpoint_cuts] for u in q['retired_track_uuids']}
    isolated_supply={u for q in transport.get('rigid_isolated_selected_bypass_supply_components',[])
        for u in q['track_uuids']}
    if isolated_supply&(set(proposal['retired_track_uuids'])|{q['change']['uuid']for q in extras}|endpoint_retirements):
        raise ValueError('isolated_supply_component_cannot_be_dually_retired')
    if endpoint_retirements&retained_pickups:
        raise ValueError('source_ground_endpoint_cut_overlaps_retained_factory_pickup')
    retired=(set(proposal['retired_track_uuids'])|{q['change']['uuid'] for q in extras}|endpoint_retirements)-retained_pickups
    _preserve_endpoint_throats(retired,endpoint_cuts,supply_endpoint_cuts)
    rc_prefix.require_transport_retirements(proposal,transport,retired)
    if len(retired)>128:raise ValueError('bounded_complete_macro_retirement_required')
    preserved_contact_frame=proposal.get('native_retained_bypass_contact_frame')
    if (preserved_contact_frame is not None
            and retired & set(preserved_contact_frame['retained_track_uuids'])):
        raise ValueError('complete_macro_cut_intersects_retained_bypass_stroke_component')
    import cec_macro_boundary_composition as composition
    extras,rated_composed=composition.compose_rated_forks(parent,source,proposal,extras,retired,deadline=deadline)
    composed_supply_forks={q['original_fork_index']for q in rated_composed}
    discard_items(private,[t for t in private.GetTracks() if force._uid(t) in retired])
    if preserved_contact_frame is not None:
        import cec_retained_bypass_contact_frame as retained_bypass
        retained_bypass.observe(private,preserved_contact_frame)
    # Project only request endpoints; the original source plan and its
    # current/ownership evidence remain separately immutable in the packet.
    projected=copy.deepcopy(proposal)
    original_forks={}
    for key in ('source_owned_shared_supply_forks','source_owned_shared_scalar_input_forks'):
        for index,fork in enumerate(projected.get(key,[])):
            original_forks[key,index]=proposal[key][index]
            if key=='source_owned_shared_supply_forks'and index in composed_supply_forks:continue
            for port in fork['retained_native_ports']:
                q=_project_port(parent,private,dict(at_nm=port['at_nm'],layers=[port['layer_id']],
                    native_uuids=[port['native_uuid']]),transport,retired)
                port['at_nm']=q['at_nm']
    # Ground fragment comparison needs moved physical barrel identities.
    # Derive it separately below; never hide them as stationary old points.
    old={force._uid(t):t for t in parent.GetTracks()}
    projected['retired_track_uuids']=[u for u in proposal['retired_track_uuids'] if old[u].GetNetname()!='GND']
    deadline=leases.advance('complete_endpoint_obligations',same_live_inputs)
    composed_supply_endpoint_contacts=_compose_supply_endpoint_rows(projected,supply_endpoint_cuts)
    requests=escape._obligations(parent,private,projected,
        composed_supply_fork_tracks=[proposal['source_owned_shared_supply_forks'][i]['track_uuids']
            for i in sorted(composed_supply_forks)])
    if required_ordinary_nets:
        import cec_macro_ordinary_join_obligations as ordinary_joins
        incoming=ordinary_joins.plan(parent,source,proposal,required_ordinary_nets,
            timeout_s=min(10.,max(.001,deadline-time.monotonic())))
        if ({r['net'] for r in incoming.values()} & {r['net'] for r in requests.values()}):
            raise ValueError('explicit_ordinary_join_net_already_has_macro_restoration_obligations')
        requests.update(incoming)
    requests,extras,composed=composition.compose(parent,source,proposal,requests,extras,deadline=deadline)
    requests,retained_composed=_compose_retained_demands(parent,requests,extras,
        board_hint=board_hint,deadline=deadline,source_proposal=proposal)
    composed+=retained_composed
    expanded={}
    for request_id,request in requests.items():
        # Fork.connections consumed the already projected, native-validated
        # ports above. Other factories still name original source points.
        if 'source_typed_multiport_fork' not in request:
            endpoints={}
            for end in ('a','b'):
                if end not in request:continue
                try:endpoints[end]=_project_contacts(parent,private,request[end],transport,retired)
                except ValueError as exc:raise ValueError('macro_request_port_refused:'+request_id+':'+end+':'+str(exc)) from exc
            variants=list(product(*(endpoints[end] for end in endpoints)))
            if not 1<=len(variants)<=16:raise ValueError('bounded_separated_macro_contact_obligations_required')
            for index,values in enumerate(variants):
                replacement=copy.deepcopy(request)
                replacement.update(zip(endpoints,values))
                if len(variants)>1:
                    replacement['separated_literal_source_contacts']=dict(original_request_id=request_id,
                        original_endpoints={end:request[end] for end in endpoints},
                        every_original_retained_contact_restored_separately=True)
                expanded[request_id if not index else request_id+':source_contact:'+str(index)]=replacement
        if 'source_typed_multiport_fork' in request:
            candidate=request['source_typed_multiport_fork']
            original=next(q for q in original_forks.values() if q['track_uuids']==candidate['track_uuids'])
            request['source_typed_multiport_fork']=copy.deepcopy(original)
            request['projected_source_native_fork_ports']=copy.deepcopy(candidate['retained_native_ports'])
            expanded[request_id]=request
    requests=expanded
    for cut in supply_endpoint_cuts:
        pad=next(p for fp in private.GetFootprints()for p in fp.Pads()if force._uid(p)==cut['pad_uuid'])
        requests['source_supply_lead:'+cut['retired_track_uuids'][0]]=dict(kind='source_boundary',net=cut['net'],
            a=dict(pad_uuid=cut['pad_uuid'],at_nm=list(pad.GetPosition()),layers=[cut['layer_id']]),
            b=dict(at_nm=cut['retained_throat_nm'],layers=[cut['layer_id']],native_uuids=cut['retained_throat_track_uuids']),
            width_nm=cut['width_nm'],clearance_nm=cut['clearance_nm'],
            unchanged_full_rail_current_contract=cut['unchanged_full_rail_current_contract'],
            source_supply_pad_contact_lead_restoration=cut)
    for retained in transport.get('retained_source_supply_endpoint_throats',[]):
        for contact in retained['lost_moving_contacts']:
            for point in contact['source_contact_nm']:
                found=any(r['kind']=='source_boundary'and r['net']==retained['net']
                    and r.get('a',{}).get('pad_uuid')==contact['pad_uuid']
                    and r.get('b',{}).get('at_nm')==point
                    and retained['uuid']in r.get('b',{}).get('native_uuids',[])
                    for r in requests.values())
                # Exact projected contacts can be deduplicated later, but
                # never omitted merely because another path might reach it.
                if not found:
                    raise ValueError('fixed_supply_throat_moved_contact_restoration_missing')
    if len(leases.phases)in(6,8,9):
        deadline=leases.advance('independent_ground_endpoint_obligations',same_live_inputs)
    ground_barrels=[q for q in transport['source_process_barrel_motion'] if old[q['uuid']].GetNetname()=='GND']
    ground_proposal=copy.deepcopy(proposal);ground_proposal['retired_track_uuids']=sorted(retired)
    cut_ground=ground.requests(parent,private,ground_proposal,
        timeout_s=min(10.,max(.001,deadline-time.monotonic())),transported_source_barrels=ground_barrels,
        additional_source_ground_cut_rows=[q for q in extras if q.get('authority',{}).get('kind')in
            ('positive_existing_low_power_ground_boundary','positive_source_low_power_ground_continuation')])
    requests.update(cut_ground)
    if len(leases.phases)in(6,8,9):
        deadline=leases.advance('complete_component_inventory',same_live_inputs)
    import cec_stationary_owner_ground_obligations as stationary_ground
    requests=stationary_ground.merge(requests,
        stationary_ground.requests(parent,private,ground_proposal,cut_ground,
            timeout_s=min(10.,max(.001,deadline-time.monotonic()))))
    components=[]
    if extras:
        import cec_macro_cut_components as cut_components
        restored,components=cut_components.requests(parent,private,extras,retired,transport,
            project_contacts=_project_contacts,deadline=deadline)
        for component in components:
            if all(q['kind']=='positive_source_ordinary' for q in component['original_authorities']):
                import cec_macro_ordinary_join_obligations as ordinary_joins
                for key in component['request_ids']:
                    restored[key]['source_ordinary_boundary_scope']=ordinary_joins.boundary_scope(
                        parent,source,restored[key],board_hint=board_hint,
                        timeout_s=min(10.,max(.001,deadline-time.monotonic())))
            if any(q['kind']=='unchanged_full_current_source_edge' for q in component['original_authorities']):
                with force._thermal_hint(board_hint):contract=cells._supply_current_widths(parent,component['net'])
                if not contract:raise ValueError('positive_macro_component_current_contract_required')
                for key in component['request_ids']:restored[key]['unchanged_full_rail_current_contract']=contract
        for original in composed:
            if original.get('source_existing_base_endpoint_obligation_composed_not_omitted')is True:
                if original['required_replacement_request_id']not in requests:
                    raise ValueError('composed_source_base_endpoint_obligation_missing')
                continue
            uid=original['required_replacement_request_id'].split(':',1)[1]
            group=next(q for q in components if uid in q['source_extra_edge_uuids'])
            original['required_replacement_request_ids']=group['request_ids']
            original['required_replacement_request_id']=next(iter(group['request_ids']),None)
            original['source_edge_restored_by_exact_surviving_component_ports']=True
        requests.update(restored)
    for proof in required_ground:
        key='ground:'+proof['pad_uuid']
        if key not in requests or requests[key]['kind']!='ground':
            raise ValueError('mandatory_projected_ground_request_missing')
        requests[key]['required_projected_ground_entry']=proof
    for proof in required_new_ground:
        key='ground:'+proof['pad_uuid']
        if key not in requests or requests[key]['kind']!='ground':
            raise ValueError('mandatory_new_ground_dogbone_request_missing')
        requests[key]['required_new_ground_dogbone']=proof
    for proof in required_supply:
        requests['supply_departure:'+proof['pad_uuid']]=dict(kind='supply_departure',net=proof['net'],
            a=dict(pad_uuid=proof['pad_uuid'],at_nm=list(next(p for f in private.GetFootprints() for p in f.Pads()
                if force._uid(p)==proof['pad_uuid']).GetPosition()),layers=[proof['face']]),
            b=dict(at_nm=proof['point_nm'],layers=[proof['face']]),width_nm=proof['width_nm'],
            unchanged_full_rail_current_contract=proof['unchanged_full_rail_current_contract'],
            required_supply_departure=proof)
    for proof in required_corridors:
        key='isolated_measurement:'+proof['pad_uuid']
        request=requests.get(key)
        if (request is None or request['kind']!='isolated_measurement' or request['net']!=proof['net']
                or request['a'].get('pad_uuid')!=proof['pad_uuid']
                or request['b'].get('pad_uuid')!=proof['target_pad_uuid']
                or request['width_nm']!=proof['width_nm']):
            raise ValueError('mandatory_source_measurement_corridor_request_missing_or_mismatched')
        request['required_measurement_corridor']=proof
    rc_prefix.require_transport_retirements(proposal,transport,retired,draft=private,restored_requests=requests)
    if required_quiet_output_pad_uuids:
        incoming_quiet=quiet_outputs.plan(parent,private,proposal,required_quiet_output_pad_uuids,
            timeout_s=min(10.,max(.001,deadline-time.monotonic())))
        if {r['net'] for r in incoming_quiet.values()} & {r['net'] for r in requests.values()}:
            raise ValueError('quiet_output_cannot_alias_any_other_macro_restoration_scope')
        requests.update(incoming_quiet)
    import cec_retained_address_ground as address_ground
    requests=address_ground.convert(parent,private,proposal,requests,
        timeout_s=min(10.,max(.001,deadline-time.monotonic())))
    if not 1<=len(requests)<=64:raise ValueError('bounded_complete_macro_request_count_required')
    result=dict(schema=1,scope='source_typed_complete_native_macro_requests',source=str(source),
        source_sha256=force._hash(source),code_identity=epoch,source_plan=proposal,transport=transport,
        source_factory_ground_pickups_carried_without_retirement=pickups,
        source_ground_endpoint_restoration_cuts=endpoint_cuts,
        source_supply_endpoint_restoration_cuts=supply_endpoint_cuts,
        composed_original_supply_endpoint_contacts=composed_supply_endpoint_contacts,
        composed_original_rated_supply_forks=rated_composed,
        composed_original_retained_edge_demands=composed,
        additional_source_cut_components=components,
        explicit_additional_obstacle_track_uuids=sorted(explicit_obstacles),
        required_projected_ground_entries=required_ground,
        required_new_ground_dogbones=required_new_ground,
        additional_source_boundary_ownership=extras,retired_track_uuids=sorted(retired),requests=requests,
        private_draft_native_binding=row._source_binding(private),all_extra_omissions_positively_source_typed=True,
        ordinary_full_current_and_ground_scopes_not_interchangeable=True,
        no_new_copper_or_barrels_constructed=True,source_family_and_code_unchanged=True,
        routing_admitted=False,saved_candidate_authorized=False,fab_ready=False,release_authority=False)
    options={}
    if required_measurement_corridors:
        result['required_measurement_corridors']=required_corridors
        options['required_measurement_corridors']=required_measurement_corridors
    if control_shunt_ground_return_axes:options['control_shunt_ground_return_axes']=list(control_shunt_ground_return_axes)
    if source_rc_input_prefixes:options['source_rc_input_prefixes']=source_rc_input_prefixes
    if reuse_ground_barrels:options['reuse_ground_barrels']=list(reuse_ground_barrels)
    if ordinary_via_poses:options['ordinary_via_poses']=list(ordinary_via_poses)
    if max_obstacle_track_mm!=8.:options['max_obstacle_track_mm']=max_obstacle_track_mm
    if max_obstacle_tracks!=8:options['max_obstacle_tracks']=max_obstacle_tracks
    if required_ground_pad_entries:options['required_ground_pad_entries']=sorted(required_ground_pad_entries)
    if required_new_ground_dogbones:options['required_new_ground_dogbones']=list(required_new_ground_dogbones)
    if stationary_ground_barrel_uuids:options['stationary_ground_barrel_uuids']=sorted(stationary_ground_barrel_uuids)
    if allow_octilinear_rotations:options['allow_octilinear_rotations']=True
    if local_signal_port_offsets:options['local_signal_port_offsets']=list(local_signal_port_offsets)
    if reference_group_uuids:options['reference_group_uuids']=list(reference_group_uuids)
    if required_supply_departures:
        result['required_supply_departure_columns']=required_supply
        options['required_supply_departures']=list(required_supply_departures)
    if required_ordinary_nets:options['required_ordinary_nets']=list(required_ordinary_nets)
    if required_quiet_output_pad_uuids:
        options['required_quiet_output_pad_uuids']=required_quiet_output_pad_uuids
    if aggregate_capacitor_max_shift_mm is not None:
        options['aggregate_capacitor_max_shift_mm']=aggregate_capacitor_max_shift_mm
    if allow_linear_power_stage_reconstruction:options['allow_linear_power_stage_reconstruction']=True
    if shared_supply_root_pad_uuids:options['shared_supply_root_pad_uuids']=shared_supply_root_pad_uuids
    if allow_full_width_supply_obstacles:options['allow_full_width_supply_obstacles']=True
    if compilation_phase_timeouts_s is not None:
        options['compilation_phase_timeouts_s']=_phase_budgets(compilation_phase_timeouts_s)
    if options:result['explicit_native_macro_options']=options
    packet=json.loads(json.dumps(result,allow_nan=False))
    leases.finish(same_live_inputs)
    return private,packet


def identity_rebindings(parent,posed,packet,*,timeout_s=10.):
    """Comparison keys for an independently recompiled native macro frame.

    No unchanged conductor receives a geometric waiver. Only the literal
    source-owned barrels and retained factory pickups may use their old
    identity after the exact compiler transform; saved replay still checks
    their complete native definitions, process, count and every other item.
    """
    deadline=full._budget(timeout_s)
    if packet.get('scope')!='source_typed_complete_native_macro_requests':
        raise ValueError('typed_complete_native_macro_packet_required')
    before={force._uid(p):p for f in parent.GetFootprints() for p in f.Pads()}
    after={force._uid(p):p for f in posed.GetFootprints() for p in f.Pads()}
    if before.keys()!=after.keys():raise ValueError('macro_rebinding_pad_population_changed')
    refs=set(packet['source_plan']['poses'])
    mapping={force._item_key(after[u]):force._item_key(p) for u,p in before.items()
        if p.GetParentFootprint().GetReference() in refs}
    old={force._uid(t):t for t in parent.GetTracks()};new={force._uid(t):t for t in posed.GetTracks()}
    owned={q['uuid'] for q in packet['transport']['source_process_barrel_motion']}
    owned.update(q['uuid'] for q in packet['transport']['explicit_source_typed_ordinary_barrel_motion'])
    owned.update(q['uuid'] for q in packet['transport']['explicitly_reproved_private_signal_port_reseats'])
    owned|={q['uuid'] for q in packet['source_factory_ground_pickups_carried_without_retirement']}
    if len(owned)>32 or not owned<=old.keys() or not owned<=new.keys():
        raise ValueError('literal_bounded_source_macro_barrel_and_pickup_identities_required')
    for uid in sorted(owned):
        if time.monotonic()>=deadline:raise ValueError('macro_rebinding_identity_deadline')
        a,b=old[uid],new[uid]
        if a.GetClass()!=b.GetClass() or a.GetNetname()!=b.GetNetname():
            raise ValueError('macro_rebinding_native_identity_changed')
        mapping[force._item_key(b)]=force._item_key(a)
    return mapping


def pre_refill_barrel_screen(board,packet,*,timeout_s=10.):
    """Name actual layer conflicts before connectivity can normalize nets.

    This is not admission. Ground plane antipads are still refilled and the
    full native pose, priority, saved partitions and DRC checks still follow.
    The existing native via guard owns every copper face and drilled gap.
    """
    import cec_fr as fr
    deadline=full._budget(timeout_s)
    if type(packet) is not dict or packet.get('scope')!='source_typed_complete_native_macro_requests':
        raise ValueError('source_typed_complete_macro_barrel_screen_required')
    transport=packet['transport'];carried=[*transport['source_process_barrel_motion'],
        *transport['explicit_source_typed_ordinary_barrel_motion'],
        *transport['explicitly_reproved_private_signal_port_reseats'],
        *transport['explicitly_reproved_private_signal_return_reseats']]
    carried += [dict(uuid=q['source_reference_via']['uuid']) for q in
        transport.get('explicit_stationary_source_ground_barrels',[])]
    if len(carried)>64 or len({q['uuid'] for q in carried})!=len(carried):
        raise ValueError('unique_bounded_macro_carried_barrel_inventory_required')
    live={force._uid(t):t for t in board.GetTracks()};refusals=[]
    stationary={q['source_reference_via']['uuid']:q for q in transport.get('explicit_stationary_source_ground_barrels',[])}
    for proof in carried:
        if time.monotonic()>=deadline:raise ValueError('macro_pre_refill_barrel_screen_deadline')
        via=live.get(proof['uuid'])
        if via is None or via.GetClass()!='PCB_VIA':raise ValueError('literal_macro_carried_barrel_required')
        detail={}
        if proof['uuid'] in stationary:
            import cec_stationary_ground_barrel as kept
            detail=kept.clearance(board,stationary[proof['uuid']],timeout_s=min(10.,max(.001,deadline-time.monotonic())))
            if not detail['ok']:refusals.append(dict(uuid=proof['uuid'],diagnostics=detail))
            continue
        if not fr._via_spot_clear(board,via.GetPosition(),via.GetWidth(via.TopLayer()),
                max(200000,int(board.GetDesignSettings().m_MinClearance)),{via.GetNetCode()},
                drill_nm=via.GetDrillValue(),net_code=via.GetNetCode(),existing_via_uuid=proof['uuid'],report=detail):
            refusals.append(dict(uuid=proof['uuid'],diagnostics=detail))
    return dict(ok=not refusals,refusals=refusals,all_carried_barrels_examined=len(carried),
        pre_refill_literal_authored_nets_not_normalized=True,routing_admitted=False,release_authority=False)


def native_pose_screen(parent,posed,packet,*,timeout_s=10.,phase_timeouts_s=None,
                       ground_barrel_clearance_window_uuids=()):
    """Full native pose/barrel/priority guard, no admission or mutation."""
    import cec_cell_contact_frontier as contacts
    import cec_escape_pose_frontier as frontier
    import cec_macro_priority_preflight as priority
    import cec_macro_ground_barrel_window as windows
    from contextlib import nullcontext
    window_ids=windows.ids(ground_barrel_clearance_window_uuids)
    leases=_NativePoseLeases(timeout_s,phase_timeouts_s)
    remaining=leases.remaining
    explicit=leases.budgets is not None
    initial=_native_pose_fence(parent,posed,packet)if explicit else None
    uncut=None;uncut_binding=None
    def same_live_inputs():
        import cec_native_construction_frame as construction
        return not explicit or (_native_pose_fence(parent,posed,packet)==initial
            and(uncut is None or construction.binding(uncut,leases.deadline)==uncut_binding))
    proposal=packet['source_plan'];refs=set(proposal['poses'])
    moved={ref for ref in refs if tuple(parent.FindFootprintByReference(ref).GetPosition())
        !=tuple(posed.FindFootprintByReference(ref).GetPosition()) or
        parent.FindFootprintByReference(ref).GetOrientationDegrees()!=posed.FindFootprintByReference(ref).GetOrientationDegrees()}
    if not moved:raise ValueError('actual_macro_native_motion_required')
    with (windows.search_geometry(parent,posed,packet['transport'],window_ids,timeout_s=remaining())
            if window_ids else nullcontext()):
        courts=frontier.courtyard_screen(posed,moved)
        surface=frontier.surface_screen(posed,moved,selected_refs=refs,
            allow_native_ground_refill=True,timeout_s=remaining())
        barrels=contacts._barrel_refusals(posed,packet['transport'],deadline_monotonic=leases.deadline)
    # Explicit ordinary barrels carry the same six-face/hole obligations as
    # package-owned pickups. Their Source role is not a clearance exemption.
    live={force._uid(t):t for t in posed.GetTracks()}
    import cec_fr as fr
    extra_barrels=[*packet['transport']['explicit_source_typed_ordinary_barrel_motion'],
        *[dict(uuid=q['source_reference_via']['uuid']) for q in
            packet['transport'].get('explicit_stationary_source_ground_barrels',[])]]
    stationary={q['source_reference_via']['uuid']:q for q in packet['transport'].get('explicit_stationary_source_ground_barrels',[])}
    for proof in extra_barrels:
        remaining();via=live[proof['uuid']];detail={}
        if proof['uuid'] in stationary:
            import cec_stationary_ground_barrel as kept
            detail=kept.clearance(posed,stationary[proof['uuid']],timeout_s=remaining())
            if not detail['ok']:barrels['ordinary_barrel:'+proof['uuid']]=detail
            continue
        if not fr._via_spot_clear(posed,via.GetPosition(),via.GetWidth(via.TopLayer()),
                max(200000,int(posed.GetDesignSettings().m_MinClearance)),{via.GetNetCode()},
                drill_nm=via.GetDrillValue(),net_code=via.GetNetCode(),existing_via_uuid=proof['uuid'],report=detail):
            barrels['ordinary_barrel:'+proof['uuid']]=detail
    # Priority ownership compares a complete source/transported population,
    # not an already cut restoration draft. Reconstruct that exact frame;
    # the ordinary native surface/barrel checks above still use the REAL
    # source-owned cut, never provisional boundary edges as free copper.
    options=packet_options(packet)
    leases.advance('fresh_uncut_priority_frame',same_live_inputs)
    uncut,transport=_frame(parent,Path(packet['source']),proposal,
        reuse_ground_barrels=options.get('reuse_ground_barrels',()),ordinary_via_poses=options.get('ordinary_via_poses',()),
        stationary_ground_barrel_uuids=options.get('stationary_ground_barrel_uuids',()),
        local_signal_port_offsets=options.get('local_signal_port_offsets',()),
        control_shunt_ground_return_axes=options.get('control_shunt_ground_return_axes',()),
        timeout_s=remaining())
    if json.loads(json.dumps(transport,allow_nan=False))!=packet['transport']:
        raise ValueError('macro_priority_transport_epoch_changed')
    if explicit:
        # UNCUT is intentionally unfinished IR: it still contains obsolete
        # owned edges and old Ground fills. Bind every live native property;
        # never claim saved equivalence or normalize its authored nets. The
        # parent and actual posed board above keep strict saved bindings.
        import cec_native_construction_frame as construction
        uncut_binding=construction.binding(uncut,leases.deadline)
    leases.advance('independent_priority_ownership',same_live_inputs)
    fixed=priority.inspect(parent,uncut,transport,board_hint=proposal['board_hint'],timeout_s=remaining(),
        allow_contained_source_barrel_motion=True,
        source_measurement_leaves=proposal['measurement_leaves'],retired_source_track_uuids=packet['retired_track_uuids'],
        **(dict(source_reconstruction_packet=packet)if any(
            q.get('authority',{}).get('kind')=='unchanged_full_current_source_edge'
            for q in packet.get('additional_source_boundary_ownership',[]))else {}),
        **(dict(ground_barrel_clearance_window_uuids=window_ids,
            actual_ground_barrel_window_board=posed)if window_ids else {}))
    leases.finish(same_live_inputs)
    result=dict(ok=bool(courts['ok'] and surface['ok'] and not barrels and fixed['ok']),
        courtyards=courts,surface=surface,barrel_refusals=barrels,priority=fixed,
        all_actual_copper_faces_and_holes_checked=True,priority_copper_motion_not_authorized=True,
        routing_admitted=False,fab_ready=False,release_authority=False)
    if explicit:result['bounded_composition']=dict(constituents=list(NATIVE_POSE_PHASES),
        per_constituent_limits_s=leases.budgets,stage_timings_s=leases.timings,
        all_actual_native_and_Source_inputs_bound_across_seams=True)
    return result
