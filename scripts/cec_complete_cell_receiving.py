"""Independently receive a saved, source-typed complete owner/bypass rebuild.

Infer the bounded cell from the immutable manufacturer's bypass assignment,
replay its exact cut and native poses, then receive additions, every surviving
source partition and physical local returns. No caller supplies a deletion
allowlist or a current rating. This is not macro-barrel transport, full-board
DRC/current/field/Kelvin/assembly qualification, or release authority.
"""
import json
import math
import tempfile
import time
from pathlib import Path
from contextlib import contextmanager
from contextvars import ContextVar

import pcbnew
import cec_additive_route_receiving as additive
import cec_cell_escape_replan as escape
import cec_constraints as constraints
import cec_decoupler_cell as cells
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_ground_return_preservation as ground
import cec_ordinary_route_receiving as ordinary
import cec_native_partition_pair as partitions


POSE_SELECTION_PHASES=('actual_inventory_and_bypass', 'source_passive_role_plans',
    'source_passive_role_requests', 'actual_owner_pose_result')
_POSE_SELECTION_OBSERVER=ContextVar('complete_cell_pose_selection_observer',default=None)
_pose_clock=time.monotonic


def pose_selection_budgets(values):
    if (type(values) not in (list,tuple) or len(values)!=len(POSE_SELECTION_PHASES)
            or any(type(v) not in (int,float) or not math.isfinite(v) or not 0<v<=10 for v in values)):
        raise ValueError('explicit_bounded_complete_pose_selection_phases_required')
    return tuple(values)


@contextmanager
def observe_pose_selection_phases(callback):
    if not callable(callback):raise ValueError('callable_pose_selection_observer_required')
    token=_POSE_SELECTION_OBSERVER.set(callback)
    try:yield
    finally:_POSE_SELECTION_OBSERVER.reset(token)


class _PoseSelectionLease:
    """Optional composition; no role, source or child check is omitted."""
    def __init__(self,budgets):
        self.budgets=None if budgets is None else pose_selection_budgets(budgets)
        self.index=0;self.started=self.phase_started=_pose_clock()
        self._emit('start')

    def _emit(self,event):
        observer=_POSE_SELECTION_OBSERVER.get()
        if observer is not None:
            observer(dict(event=event,index=self.index,phase=POSE_SELECTION_PHASES[self.index]))

    def _seal(self):
        if self.budgets is not None and _pose_clock()-self.phase_started>=self.budgets[self.index]:
            raise ValueError('complete_pose_selection_deadline:'+POSE_SELECTION_PHASES[self.index])
        self._emit('finish')

    def advance(self,name):
        if self.index+1>=len(POSE_SELECTION_PHASES) or name!=POSE_SELECTION_PHASES[self.index+1]:
            raise ValueError('explicit_complete_pose_selection_phase_order_required')
        self._seal();self.index+=1;self.phase_started=_pose_clock();self._emit('start')

    def finish(self):
        if self.index!=len(POSE_SELECTION_PHASES)-1:
            raise ValueError('all_complete_pose_selection_phases_required')
        self._seal()
        if self.budgets is not None and _pose_clock()-self.started>=sum(self.budgets):
            raise ValueError('complete_pose_selection_total_deadline')


def _assignments(board,hint):
    with force._thermal_hint(hint):
        assignment=constraints._device_bypass_assignment(board,project_max_mm=3.5)
    result={}
    for key,row in assignment['assigned'].items():
        req=row['requirement']
        result[str(key)]=(row['cap_ref'],req['ref'],str(req['pin']),req['rail'],
            req.get('return_rail') or 'GND')
    return result


def _bounded_explicit_ground_return_mm(board, pad, via, reach_mm):
    """Actual local copper length, not a pad/barrel centre-distance proxy.

    Only a recompiled typed Ground request may call this from receiving.
    The native envelope is a rejection-only work bound; no plane/zone or
    caller witness participates in the explicit saved path observation.
    Process, full-class/endpoint, exact Source scope and native admission
    remain separate mandatory gates.
    """
    if (type(reach_mm) not in (int,float) or not math.isfinite(reach_mm)
            or not 0 < reach_mm <= 1.5):
        raise ValueError('unchanged_bounded_explicit_ground_reach_required')
    if (pad.GetNetname() != 'GND' or via.GetClass() != 'PCB_VIA'
            or via.GetNetname() != 'GND' or pad.GetNetCode() != via.GetNetCode()
            or cells._return_path_aabb_lower_bound_mm(pad,via) > reach_mm):
        return None
    path = cells._shortest_track_path_mm(board,pad,via,snap_mm=.000001)
    return path if path is not None and path <= reach_mm else None


def _stationary_bypass_return_peers(parent,child,assigned,refs):
    """Infer stationary Source cells from ACTUAL new bounded return copper.

    A moved cell may strand its fixed neighbor's selected bypass. Saved
    receiving cannot recover that neighbor from footprint motion alone.
    Recompile its immutable assignment and require a new real Ground barrel
    with an explicit (zone-free) bounded path to its unchanged selected cap.
    This extends identity/return expectations only, never motion, cut, current
    or barrel-process authority. Full independent macro receiving stays due.
    """
    import cec_device_power_roles as roles
    import cec_ground_return_policy as policy
    old={force._uid(t)for t in parent.GetTracks()}
    vias=[t for t in child.GetTracks()if force._uid(t)not in old
        and t.GetClass()=='PCB_VIA'and t.GetNetname()=='GND']
    if not vias:return set()
    if len(vias)>32 or len(assigned)>256:raise ValueError('bounded_stationary_bypass_return_scope_required')
    counts={}
    for r in assigned.values():counts[r[0]]=counts.get(r[0],0)+1
    result=set();deadline=time.monotonic()+1.
    for cap_ref,owner_ref,pin,rail,return_rail in sorted(assigned.values()):
        if time.monotonic()>=deadline:raise ValueError('stationary_bypass_return_scope_deadline')
        if cap_ref in refs or counts[cap_ref]!=1 or return_rail!='GND':continue
        first=parent.FindFootprintByReference(cap_ref);last=child.FindFootprintByReference(cap_ref)
        owner=parent.FindFootprintByReference(owner_ref);after_owner=child.FindFootprintByReference(owner_ref)
        if any(f is None or f.IsLocked()or f.IsDNP()for f in(first,last,owner,after_owner)):continue
        def signature(f):
            return (force._uid(f),f.GetReference(),f.GetValue(),f.GetFPIDAsString(),
                tuple(f.GetPosition()),f.GetOrientationDegrees(),bool(f.IsFlipped()),
                tuple(sorted((field.GetName(),field.GetText())for field in f.GetFields())),
                tuple(sorted((force._uid(p),p.GetNumber(),p.GetNetname(),tuple(p.GetPosition()),
                    tuple(p.GetSize()),int(p.GetShape()),int(p.GetAttribute()),tuple(p.GetDrillSize()),
                    tuple(p.GetOffset()),p.GetOrientationDegrees(),p.GetRoundRectRadiusRatio(),
                    tuple(p.GetLayerSet().CuStack()))for p in f.Pads())))
        model=roles.footprint_contract(owner)
        if (signature(first)!=signature(last)or signature(owner)!=signature(after_owner)
                or not model or model['pins'].get(pin)not in('power_input','power_output')
                or set(model['pins'])!={p.GetNumber()for p in owner.Pads()}
                or len(list(first.Pads()))!=2 or {p.GetNetname()for p in first.Pads()}!={rail,'GND'}):continue
        grounds=[p for p in last.Pads()if p.GetNetname()=='GND'and not p.HasHole()
            and p.GetAttribute()==pcbnew.PAD_ATTRIB_SMD]
        if len(grounds)!=1:continue
        pad=grounds[0];reach=policy.reach(pad,{})
        for via in vias:
            path=_bounded_explicit_ground_return_mm(child,pad,via,reach)
            if path is not None:
                result.update((cap_ref,owner_ref));break
    if time.monotonic()>=deadline:raise ValueError('stationary_bypass_return_scope_deadline')
    return result


def _poses(parent,child,hint,reference_group_uuids=(),*,phase_timeouts_s=None):
    lease=_PoseSelectionLease(phase_timeouts_s)
    before={force._uid(f):f for f in parent.GetFootprints()}
    after={force._uid(f):f for f in child.GetFootprints()}
    if before.keys()!=after.keys():raise ValueError('complete_cell_population_changed')
    def pose(f):return (tuple(f.GetPosition()),f.GetOrientationDegrees(),f.IsFlipped())
    moved={before[u].GetReference() for u in before if pose(before[u])!=pose(after[u])}
    if not 1<=len(moved)<=8:raise ValueError('bounded_actual_cell_motion_required')
    assigned=_assignments(parent,hint)
    if assigned!=_assignments(child,hint):raise ValueError('original_bypass_assignments_changed')
    rows=[r for r in assigned.values() if r[0] in moved or r[1] in moved]
    refs={ref for r in rows for ref in r[:2]}
    refs|=_stationary_bypass_return_peers(parent,child,assigned,refs)
    unowned=moved-refs
    lease.advance('source_passive_role_plans')
    if unowned:
        import cec_control_shunt_placement as shunt
        actual={}
        # Positive IC/bypass cells are part of this same saved rigid cohort.
        # A passive's shared bus peer may be one of those moving ICs; passing
        # only unowned refs would incorrectly demand it remain stationary.
        for ref in sorted(refs|unowned):
            old=parent.FindFootprintByReference(ref);new=child.FindFootprintByReference(ref)
            if old is None or new is None or old.IsFlipped()!=new.IsFlipped():
                raise ValueError('same_native_cell_surface_required')
            actual[ref]=[new.GetPosition().x/1e6,new.GetPosition().y/1e6,new.GetOrientationDegrees()]
        selected=shunt.plan(parent,actual,board_hint=hint,reference_group_uuids=reference_group_uuids)
        import cec_control_pullup_placement as pullup
        pullups=pullup.complete_plan(parent,actual,board_hint=hint,reference_group_uuids=reference_group_uuids)
        import cec_control_gate_bias_placement as gate_bias
        gate_biases=gate_bias.plan(parent,actual,board_hint=hint,reference_group_uuids=reference_group_uuids)
        import cec_programming_resistor_placement as programming
        programming_resistors=programming.plan(parent,actual,board_hint=hint,reference_group_uuids=reference_group_uuids)
        programming_refs=programming.participant_refs(programming_resistors)
        import cec_source_series_link_placement as series_link
        series_links=series_link.plan(parent,actual,board_hint=hint,reference_group_uuids=reference_group_uuids)
        import cec_source_signal_bias_placement as signal_bias
        bias_resistors=signal_bias.plan(parent,actual,board_hint=hint,reference_group_uuids=reference_group_uuids,
            excluded_refs=set(selected)|set(pullups)|set(gate_biases)|programming_refs|set(series_links))
        import cec_additional_aggregate_macro as aggregate_caps
        additional=aggregate_caps.collect(parent,actual,board_hint=hint,
            reference_group_uuids=reference_group_uuids,require_explicit_owner=False,
            excluded_refs=set(selected)|set(pullups)|set(gate_biases)|programming_refs|set(bias_resistors)|set(series_links))
        # Recover the unique canonical owner from original Source intent,
        # never a constructor-provided refdes. Its saved pose must remain
        # exactly stationary; a power-stage relocation is not authorized.
        for proof in additional.values():
            ref=proof['source_locality_owner']['owner_ref']
            old=parent.FindFootprintByReference(ref);new=child.FindFootprintByReference(ref)
            if old is None or new is None or pose(old)!=pose(new):
                raise ValueError('saved_additional_capacitor_owner_must_remain_stationary')
            refs.add(ref)
            actual[ref]=[new.GetPosition().x/1e6,new.GetPosition().y/1e6,new.GetOrientationDegrees()]
        passive_roles=(set(selected),set(pullups),set(gate_biases),set(bias_resistors),programming_refs,set(additional),set(series_links))
        if (sum(map(len,passive_roles))!=len(set().union(*passive_roles))
                or set().union(*passive_roles)!=unowned):
            raise ValueError('actual_motion_not_complete_source_selected_cells')
        lease.advance('source_passive_role_requests')
        # Independently recheck the actual saved child (including stationary
        # manufacturer owner and pad/net/CuStack), not worker-supplied IDs.
        shunt.requests(parent,child,dict(poses=actual,selected_control_shunts=selected,board_hint=hint,
            reference_group_uuids=reference_group_uuids))
        pullup.requests(parent,child,dict(poses=actual,selected_control_pullups=pullups,board_hint=hint,
            reference_group_uuids=reference_group_uuids))
        gate_bias.requests(parent,child,dict(poses=actual,selected_control_gate_biases=gate_biases,board_hint=hint,
            reference_group_uuids=reference_group_uuids))
        programming.requests(parent,child,dict(poses=actual,selected_programming_resistors=programming_resistors,
            board_hint=hint,reference_group_uuids=reference_group_uuids))
        series_link.requests(parent,child,dict(poses=actual,selected_source_series_links=series_links,
            board_hint=hint,reference_group_uuids=reference_group_uuids))
        signal_bias.requests(parent,child,dict(poses=actual,selected_signal_bias_resistors=bias_resistors,
            selected_control_shunts=selected,selected_control_pullups=pullups,
            selected_control_gate_biases=gate_biases,selected_programming_resistors=programming_resistors,
            selected_source_series_links=series_links,
            board_hint=hint,reference_group_uuids=reference_group_uuids))
        if additional:
            aggregate_caps.requests(parent,child,dict(poses=actual,additional_aggregate_capacitors=additional,
                additional_aggregate_excluded_refs=sorted(set(selected)|set(pullups)|set(gate_biases)|set(bias_resistors)|programming_refs|set(series_links)),
                board_hint=hint,reference_group_uuids=reference_group_uuids))
        refs|=set().union(*passive_roles)
    else:
        lease.advance('source_passive_role_requests')
    lease.advance('actual_owner_pose_result')
    if not moved<=refs or not 1<=len(refs)<=8:
        raise ValueError('actual_motion_not_complete_source_selected_cells')
    poses={}
    for ref in sorted(refs):
        old=parent.FindFootprintByReference(ref);new=child.FindFootprintByReference(ref)
        if old is None or new is None or old.IsFlipped()!=new.IsFlipped():
            raise ValueError('same_native_cell_surface_required')
        poses[ref]=[new.GetPosition().x/1e6,new.GetPosition().y/1e6,new.GetOrientationDegrees()]
    lease.finish()
    return poses,moved


def _receive_paths(parent,child,requests,incoming,hint,deadline,*,received_barrel_uuids=(),
                   received_source_port_uuids=(),allow_retained_no_additions=False,source_proposal=None,
                   source_macro_packet=None,source_ground_observer=None):
    # Request packets are JSON stable; native layer IDs therefore have
    # string keys after serialization. Compare complete normalized values,
    # never a subset or a current-rating-only approximation.
    def stable(value):return json.loads(json.dumps(value,allow_nan=False))
    if source_ground_observer is not None:
        import cec_source_ground_boundary_connection as source_ground
        if (type(source_ground_observer)is not source_ground._PreparedObserver
                or not source_ground_observer.matches(parent,requests,board_hint=hint,
                    source_proposal=source_proposal,source_macro_packet=source_macro_packet)):
            raise ValueError('fresh_private_source_ground_expectation_required')
    pads={force._uid(p):p for fp in child.GetFootprints() for p in fp.Pads()}
    tracks={force._uid(t):t for t in child.GetTracks()}
    if (type(allow_retained_no_additions) is not bool or
            not incoming and not allow_retained_no_additions or len(incoming)>256 or not incoming<=tracks.keys()):
        raise ValueError('bounded_native_cell_conductor_additions_required')
    if not incoming and (not requests or any(r.get('kind') not in ('source_boundary','local_supply','ground','ground_boundary','source_retained_address_ground_connection')
            for r in requests.values())):
        raise ValueError('explicit_retained_terminal_requests_required_without_additions')
    if (type(received_barrel_uuids) not in (tuple,list,set,frozenset) or len(received_barrel_uuids)>32
            or not set(received_barrel_uuids)<=incoming
            or any(tracks[u].GetClass()!='PCB_VIA' for u in received_barrel_uuids)):
        raise ValueError('literal_independently_received_cell_barrel_context_required')
    old_tracks={force._uid(t):t for t in parent.GetTracks()}
    if (type(received_source_port_uuids) not in (tuple,list,set,frozenset)
            or len(received_source_port_uuids)>128
            or not set(received_source_port_uuids)<=old_tracks.keys()&tracks.keys()
            or set(received_source_port_uuids)&incoming):
        raise ValueError('literal_independently_recompiled_source_port_context_required')
    source_roots={}
    for request in requests.values():
        authorities=request.get('exact_additional_macro_component_source_ownership')
        if request.get('kind')!='source_boundary' or not authorities or request['net']=='GND':continue
        if (type(authorities) is not list or not 1<=len(authorities)<=64
                or any(q.get('kind') not in ('positive_source_ordinary','unchanged_full_current_source_edge')
                    or q.get('native_source_uuid') not in old_tracks for q in authorities)):
            raise ValueError('positive_recompiled_native_component_port_authority_required')
        for end in ('a','b'):
            port=request.get(end,{})
            for uid in port.get('native_uuids',[]):
                if uid not in received_source_port_uuids:continue
                item=tracks[uid]
                if (old_tracks[uid].GetClass()!=item.GetClass() or item.GetNetname()!=request['net']
                        or old_tracks[uid].GetNetname()!=request['net'] or not port.get('layers')
                        or any(not item.IsOnLayer(face) or not item.GetEffectiveShape(face).Collide(
                            pcbnew.VECTOR2I(*port['at_nm']),0) for face in port['layers'])):
                    raise ValueError('literal_recompiled_source_component_port_contact_lost')
                source_roots.setdefault(request['net'],set()).add(uid)
    def anchors(net):
        pads_at_roots={r[e]['pad_uuid'] for r in requests.values() if r['net']==net
            for e in ('a','b') if 'pad_uuid' in r.get(e,{})}
        # Independently compiled, literal surviving trace/barrel ports may
        # root non-Ground reconstruction without fabricating a pad at a
        # retired bend. Ground still requires its typed physical terminals;
        # a shared plane is never permission for an arbitrary new return.
        return pads_at_roots|source_roots.get(net,set())
    nets={r['net'] for r in requests.values()};proofs=[];contracts={};foreign={};face_widths={}
    if not incoming:
        for net in sorted(nets-{'GND'}):
            with force._thermal_hint(hint):
                first=cells._supply_current_widths(parent,net);last=cells._supply_current_widths(child,net)
            if stable(first)!=stable(last):raise ValueError('retained_cell_original_current_contract_changed')
            for request in requests.values():
                expected=request.get('unchanged_full_rail_current_contract')
                if request['net']==net and expected is not None and stable(expected)!=stable(first):
                    raise ValueError('retained_cell_rederived_source_current_contract_mismatch')
    graph=fr._read_only_route_connectivity(child)
    import cec_cell_endpoint_groups as endpoint_groups
    endpoints=endpoint_groups.receive(parent,child,requests,[tracks[u] for u in incoming],
        board_hint=hint,deadline=deadline,source_proposal=source_proposal)
    endpoint_ids=set(endpoints['track_uuids'])
    proofs.extend(endpoints['proofs'])
    for uid in sorted(incoming):
        if time.monotonic()>=deadline:raise ValueError('complete_cell_path_receiving_deadline')
        item=tracks[uid];net=str(item.GetNetname())
        if net not in nets or item.GetClass() not in ('PCB_TRACK','PCB_VIA') or (
                item.GetClass()=='PCB_VIA' and uid not in received_barrel_uuids):
            raise ValueError('new_cell_barrels_or_untyped_conductors_need_separate_receiving')
        if item.GetClass()=='PCB_VIA':
            # The enclosing macro receiver has independently received the
            # full additive process/group/rule delta. Recheck the real
            # through barrel here as well; no via diameter is interpreted
            # as a current rating or substituted for a track width.
            import cec_fab_profile as fab
            import cec_route_dimensions as dimensions
            dia=item.GetWidth(item.TopLayer());drill=item.GetDrillValue()
            ordinary=dimensions.ordinary_via_geometry({},dimensions.board_limits(child),
                requested=(dia/1e6,drill/1e6))
            process=fab.local_pofv_via_decision(child,item,allow_source_track_body=True)
            if (tuple(round(v*1e6) for v in ordinary)!=(dia,drill) and not process[0]
                    or not cells._hole_to_hole_clear(child,item.GetPosition(),drill/1e6,ignore_via_uuids=(uid,))[0]
                    or not fr._via_spot_clear(child,item.GetPosition(),dia,
                        max(200000,int(cells._netclass(child,net)['clearance'])),{item.GetNetCode()},
                        drill_nm=drill,net_code=item.GetNetCode(),existing_via_uuid=uid,report={})):
                raise ValueError('saved_macro_added_barrel_process_or_physical_clearance_refused:'+uid)
            reached={force._uid(t) for t in graph.GetConnectedItems(item)}
            if not reached&anchors(net):raise ValueError('new_cell_barrel_not_rooted_in_typed_terminal')
            if net=='GND':
                # A shared plane connects every remote stitch to every
                # terminal. That does not make an arbitrary extra hole a
                # typed local-return operation. Require an actual bounded
                # explicit-copper path from one rederived Ground request;
                # no zone/plane edge participates in this path proof.
                owned=False
                for request in requests.values():
                    if request['kind']!='ground':continue
                    pad=pads.get(request.get('a',{}).get('pad_uuid'))
                    reach=request['reach_mm']
                    if pad is None:continue
                    path=_bounded_explicit_ground_return_mm(child,pad,item,reach)
                    if path is not None:
                        owned=True;break
                if not owned:raise ValueError('new_cell_ground_barrel_has_no_bounded_typed_local_return:'+uid)
            proofs.append(dict(kind='independently_received_added_barrel',uuid=uid,
                current_capacity_inferred=False,through_layers=list(map(int,item.GetLayerSet().CuStack()))))
            continue
        layer=int(item.GetLayer());gap=max(200000,int(cells._netclass(child,net)['clearance']))
        import cec_source_face_widths as source_widths
        if net=='GND' and net not in face_widths:
            face_widths[net]=source_widths.envelope(parent,requests,net,None)
        if net!='GND':
            if net not in contracts:
                with force._thermal_hint(hint):
                    contracts[net]=cells._supply_current_widths(parent,net)
                    current=cells._supply_current_widths(child,net)
                if stable(contracts[net])!=stable(current):raise ValueError('cell_original_current_contract_changed')
                face_widths[net]=source_widths.envelope(parent,requests,net,contracts[net])
            contract=contracts[net]
            for request in requests.values():
                expected=request.get('unchanged_full_rail_current_contract')
                if request['net']==net and expected is not None and stable(expected)!=stable(contract):
                    raise ValueError('cell_rederived_source_current_contract_mismatch')
            if contract:
                if layer not in contract['required_by_layer_nm']:
                    raise ValueError('cell_current_layer_not_authorized')
        width=max(face_widths[net][layer],int(child.GetDesignSettings().m_TrackMinWidth),
            int(cells._netclass(child,net)['width']))
        start,end=item.GetStart(),item.GetEnd();dx,dy=abs(start.x-end.x),abs(start.y-end.y)
        if (start==end or item.GetWidth()<width and uid not in endpoint_ids or dx and dy and dx!=dy
                or not fr._edge_leg_clear(child,start,end,item.GetWidth()/2+gap)
                or not fr._tap_foreign_clear(child,start,end,item.GetWidth(),layer,gap,
                    {item.GetNetCode()},foreign_cache=foreign)):
            raise ValueError('actual_cell_track_geometry_width_or_clearance_refused:'+uid)
        reached={force._uid(t) for t in graph.GetConnectedItems(item)}
        if not reached&anchors(net):raise ValueError('new_cell_conductor_not_rooted_in_typed_terminal')
    source_ground_observations=None
    for key,request in requests.items():
        if time.monotonic()>=deadline:raise ValueError('complete_cell_terminal_receiving_deadline')
        kind=request['kind'];first=request.get('a',{});last=request.get('b',{})
        a=pads.get(first.get('pad_uuid'))
        if kind=='ground_boundary':
            if source_proposal is None:raise ValueError('saved_ground_cut_source_recompile_required')
            if source_ground_observations is None:
                import cec_source_ground_boundary_connection as source_ground
                if source_ground_observer is not None:
                    source_ground_observations=source_ground_observer(child,
                        timeout_s=min(10.,max(.001,deadline-time.monotonic())))
                else:
                    source_ground_observations=source_ground.observe_many(parent,child,requests,
                        board_hint=hint,source_proposal=source_proposal,
                        timeout_s=min(10.,max(.001,deadline-time.monotonic())),source_macro_packet=source_macro_packet)
            proof=source_ground_observations.get(key)
            if proof is None:raise ValueError('saved_ground_cut_exact_endpoints_not_connected')
            proofs.append(dict(request=key,kind=kind,source_recompiled_ground_cut=proof))
        if not incoming and kind=='source_boundary':
            proof=escape.retained_native_boundary_connection(child,request,
                timeout_s=min(10.,max(.001,deadline-time.monotonic())))
            if proof is None:
                proof=escape.retained_ground_reference_connection(child,request,
                    timeout_s=min(10.,max(.001,deadline-time.monotonic())))
            if proof is None:
                import cec_retained_ground_component as retained_ground
                proof=retained_ground.observe(child,request,
                    timeout_s=min(10.,max(.001,deadline-time.monotonic())))
            if proof is None and request.get('net')=='GND' and source_proposal is not None:
                if source_ground_observations is None:
                    import cec_source_ground_boundary_connection as source_ground
                    if source_ground_observer is not None:
                        source_ground_observations=source_ground_observer(child,
                            timeout_s=min(10.,max(.001,deadline-time.monotonic())))
                    else:
                        source_ground_observations=source_ground.observe_many(parent,child,requests,
                            board_hint=hint,source_proposal=source_proposal,
                            timeout_s=min(10.,max(.001,deadline-time.monotonic())),source_macro_packet=source_macro_packet)
                proof=source_ground_observations.get(key)
            if proof is None:raise ValueError('saved_cell_retained_literal_boundary_not_connected')
            proofs.append(dict(request=key,kind=kind,retained_native_boundary=proof))
        if kind=='source_retained_address_ground_connection':
            import cec_retained_address_ground as address_ground
            proof=address_ground.observe(child,request,requests,
                timeout_s=min(10.,max(.001,deadline-time.monotonic())))
            proofs.append(dict(request=key,kind=kind,retained_logical_connection=proof))
        if kind=='ground':
            if a is None:raise ValueError('cell_ground_pad_identity_missing')
            result=cells._existing_return(child,a,request['reach_mm'],allow_native_track_body=True)
            if result is None:
                import cec_saved_ground_hierarchy as hierarchy
                fallback=hierarchy.receive(parent,child,request,requests,board_hint=hint,deadline=deadline,
                    source_proposal=source_proposal)
                proofs.append(dict(request=key,kind=kind,source_ground_hierarchy=fallback))
            else:
                proofs.append(dict(request=key,kind=kind,return_mm=result[0],via_uuid=force._uid(result[1])))
        elif kind=='local_supply':
            b=pads.get(last.get('pad_uuid'))
            if a is None or b is None:raise ValueError('cell_local_supply_pad_identity_missing')
            length=cells._shortest_track_path_mm(child,a,b,snap_mm=.000001)
            direct=math.dist(tuple(a.GetPosition()),tuple(b.GetPosition()))/1e6
            net=request['net'];gap=max(200000,int(cells._netclass(child,net)['clearance']))
            width=max(request['width_nm'],int(cells._netclass(child,net)['width']))
            limit=escape.local_supply_path_limit(request,direct,width/1e6,gap/1e6)
            if length is None or length>limit:raise ValueError('saved_cell_local_supply_loop_refused')
            proofs.append(dict(request=key,kind=kind,saved_path_mm=length,limit_mm=limit))
        elif kind=='measurement':
            import cec_macro_rc_input_prefix as rc_prefix
            source_leaf=request.get('source_leaf',{})
            if source_leaf.get('scope')==rc_prefix.SCOPE:
                proofs.append(dict(request=key,kind='Source_canonical_fixed_port_RC_input_prefix',
                    independent_saved_prefix=rc_prefix.receive_paths(parent,child,source_leaf,incoming,
                        deadline=deadline)))
    # Recompile-derived FULL requests, not a worker's canonical routing view.
    # New copper does not excuse an exact duplicate's original endpoints.
    import cec_exact_connection_aliases as aliases
    alias_paths=aliases.receive_paths(child,requests,
        timeout_s=min(10.,max(.001,deadline-time.monotonic())))
    if alias_paths['witnesses']:
        proofs.append(dict(kind='every_original_exact_alias_native_endpoint_connection',
            independent_saved_native_paths=alias_paths))
    if source_proposal is not None and source_proposal.get('additional_aggregate_capacitors'):
        import cec_additional_aggregate_macro as aggregate_caps
        observation=aggregate_caps.observe(parent,child,source_proposal,
            timeout_s=min(10.,max(.001,deadline-time.monotonic())))
        if not observation['complete']or not observation['ok']:
            raise ValueError('saved_Source_additional_aggregate_capacitor_paths_or_returns_refused:'+repr(observation.get('errors')))
        proofs.append(dict(kind='Source_additional_aggregate_capacitor_actual_saved_local_paths_and_returns',
            independent_saved_paths=observation))
    return proofs


def _pad_rebindings(parent,child,poses):
    """Exact native keys, not permission to move this cell population."""
    def pads(board):
        result={}
        for fp in board.GetFootprints():
            if fp.GetReference() not in poses:continue
            for pad in fp.Pads():
                # Cloned footprint children can share a UUID. Preserve the
                # actual native owner and pin, not a last-writer UID map.
                key=(force._uid(fp),force._uid(pad),str(pad.GetNumber()))
                if key in result:raise ValueError('complete_cell_ambiguous_native_pad_identity')
                result[key]=pad
        return result
    old,new=pads(parent),pads(child)
    if old.keys()!=new.keys():raise ValueError('complete_cell_native_pad_identity_changed')
    return {force._item_key(new[k]):force._item_key(p) for k,p in old.items()
        if p.GetNetCode()>0}


def _preserve_partitions(parent,child,poses,retired,deadline):
    """Compare real filled islands after separately received native motion.

    An approved refill may change an island hash, but a whole zone UUID is
    never a bridge between its disconnected polygons. PAD coordinate keys
    may be rebound only for the exact already-received cell population.
    This helper grants no motion, cut, current or routing authority itself.
    """
    rebindings=_pad_rebindings(parent,child,poses)
    remaining=min(10.,deadline-time.monotonic())
    if remaining<=0:raise ValueError('complete_cell_partition_receiving_deadline')
    proof=partitions.compare(parent,child,timeout_s=remaining,
        retired_uuids=retired,identity_rebindings=rebindings)
    if not proof['preserved']:
        raise ValueError('saved_cell_original_terminal_or_copper_partition_lost:'+str(len(proof['demoted_parts'])))
    # Comparison tokens are internal sets, not caller-supplied authority or
    # persistent identities. Keep the saved receipt JSON-safe and compact.
    return {k:v for k,v in proof.items() if k not in ('source_parts','child_parts','demoted_parts')}


def _receive_reference_transports(candidate,plan):
    """Rebuild exact annotation AST from source proofs, never candidate claims."""
    import cec_source_reference_group_transport as reference_transport
    import cec_copper_echo as source_syntax
    _,candidate_nodes=additive._nodes(candidate)
    for ref,contract in plan['row_plan']['source_reference_group_transports'].items():
        first=plan['row_plan']['source_poses'][ref];last=plan['row_plan']['target_poses'][ref]
        turn=(last[2]-first[2])%360
        if turn%90:
            raise ValueError('saved_source_reference_group_cardinal_rotation_required')
        expected=reference_transport.expected_cardinal_nodes(contract,
            quarter_turns=int(turn)//90,delta_nm=tuple(
                round((last[k]-first[k])*1e6) for k in (0,1)),
            maximum_translation_mm=escape.complete_transport_shift_bound(plan))
        if any(u not in candidate_nodes or source_syntax._freeze(candidate_nodes[u])!=source_syntax._freeze(n)
               for u,n in expected.items()):
            raise ValueError('saved_source_reference_group_cardinal_transport_differs')


def _save_literal_projection(source, expected, projected, plan, moved_refs, *, source_macro_packet=None):
    """Receive native scope first, then preserve every unowned Source AST.

    The private expected board is not a writer-normalization waiver. Compare
    both native serializations BEFORE restoring Source nodes so restoration
    cannot conceal an accidental mutation of stationary geometry or process.
    """
    import copy
    import cec_copper_echo as syntax
    import cec_source_retaining_ses_import as raw
    source = Path(source).resolve()
    expected = Path(expected).resolve()
    if source == expected:
        raise ValueError('distinct_source_literal_projection_required')
    source_root, source_nodes = additive._nodes(source)
    original = pcbnew.LoadBoard(str(source))
    by_ref = {fp.GetReference(): force._uid(fp) for fp in original.GetFootprints()}
    if not set(moved_refs) <= by_ref.keys():
        raise ValueError('fresh_actual_projection_owners_required')
    owned = {by_ref[ref] for ref in moved_refs}
    retired = set(plan['retired_track_uuids'])
    if source_macro_packet is not None:
        packet = source_macro_packet
        if (packet.get('scope') != 'source_typed_complete_native_macro_requests'
                or Path(packet['source']).resolve() != source
                or packet['source_sha256'] != force._hash(source)
                or packet['code_identity'] != force._code_identity()
                or syntax._freeze(packet['source_plan']) != syntax._freeze(plan)):
            raise ValueError('fresh_source_macro_literal_projection_required')
        retired = set(packet['retired_track_uuids'])
        transported = set(plan.get('row_plan', {}).get('transformed_track_uuids', []))
        for name in ('changes', 'source_process_barrel_motion',
                     'explicit_source_typed_ordinary_barrel_motion',
                     'explicitly_reproved_private_signal_port_reseats',
                     'explicitly_reproved_private_signal_return_reseats'):
            transported.update(row['uuid'] for row in packet['transport'].get(name, []))
        transported.update(row['uuid'] for row in packet.get(
            'source_factory_ground_pickups_carried_without_retirement', []))
        if any(uid not in source_nodes or source_nodes[uid][0] not in ('segment', 'via')
               for uid in transported):
            raise ValueError('native_macro_transport_must_be_actual_source_copper')
        owned.update(transported-retired)
    if any(uid not in source_nodes or source_nodes[uid][0] != 'segment' for uid in retired):
        raise ValueError('exact_source_projection_track_cuts_required')
    if plan.get('reference_group_uuids'):
        import cec_complete_macro_cell as macro
        import cec_source_reference_group_cardinal_batch as cardinal
        owned.update(cardinal.expected_nodes(macro._reference_requests(plan),
            maximum_translation_mm=escape.complete_transport_shift_bound(plan)))
    ground = {force._uid(zone) for zone in original.Zones()
              if not zone.GetIsRuleArea() and zone.GetNetname() == 'GND'}
    with tempfile.TemporaryDirectory(prefix='cec-literal-projection-') as directory:
        source_native = Path(directory)/'source.kicad_pcb'
        projection_native = Path(directory)/'projection.kicad_pcb'
        field._save_field_snapshot(original, source_native)
        field._save_field_snapshot(projected, projection_native)
        old_root, old = additive._nodes(source_native)
        new_root, new = additive._nodes(projection_native)
        if set(new) != set(old)-retired:
            raise ValueError('unexpected_native_projection_population_delta')
        def globals_only(root, nodes):
            objects = {id(node) for node in nodes.values()}
            return syntax._freeze([node for node in root if id(node) not in objects])
        if globals_only(old_root, old) != globals_only(new_root, new):
            raise ValueError('native_projection_changed_unowned_global_context')
        pruned_groups = set()
        for uid, node in old.items():
            if uid in retired or uid in owned:
                continue
            if uid in ground:
                if additive._without(node, 'filled_polygon') != additive._without(new[uid], 'filled_polygon'):
                    raise ValueError('native_projection_changed_ground_nonfill_context')
            elif syntax._freeze(node) != syntax._freeze(new[uid]):
                # Native deletion removes retired conductors from their
                # existing groups. Only that exact subtraction is owned.
                if (source_macro_packet is not None and node[0] == 'group'
                        and additive._without(node, 'members') == additive._without(new[uid], 'members')
                        and additive._members(new[uid]) == additive._members(node)-retired):
                    pruned_groups.add(uid)
                else:
                    raise ValueError('native_projection_changed_unowned_source_context')
        replacements = {uid: new[uid] for uid in owned}
        for uid in pruned_groups:
            node = copy.deepcopy(source_nodes[uid])
            members = next(part for part in node if isinstance(part, list) and part and part[0] == 'members')
            members[:] = ['members', *[value for value in members[1:] if value.strip('"') not in retired]]
            replacements[uid] = node
        for uid in ground:
            node = copy.deepcopy(source_nodes[uid])
            node = [part for part in node if not
                    (isinstance(part, list) and part and part[0] == 'filled_polygon')]
            node.extend(copy.deepcopy(part) for part in new[uid]
                        if isinstance(part, list) and part and part[0] == 'filled_polygon')
            replacements[uid] = node
        text = raw.raw_text(source)
        spans = raw.inventory(text)
        for uid in sorted(owned | retired | ground | pruned_groups, key=lambda value: spans[value][0], reverse=True):
            start, end = spans[uid]
            text = text[:start] + ('' if uid in retired else additive._render(replacements[uid])) + text[end:]
        raw.write_raw(expected, text)
    return dict(ok=True, complete=True, owned_native_uuids=sorted(owned),
                retired_native_uuids=sorted(retired), ground_fill_uuids=sorted(ground),
                native_unowned_context_independently_unchanged=True,
                source_literal_unowned_context_preserved=True)


def receive(source,candidate,*,board_hint,timeout_s=10.,max_shift_mm=6.,
            allow_owned_locked_escapes=False,rebuild_projected_ground=False,allow_octilinear_rotations=False,
            reference_group_uuids=(),aggregate_capacitor_max_shift_mm=None,
            allow_linear_power_stage_reconstruction=False,shared_supply_root_pad_uuids=()):
    """Three explicit <=10-s native stages; no worker-authored source scope."""
    if (type(board_hint) is not str or not board_hint
            or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10.
            or type(max_shift_mm) not in (int,float) or not math.isfinite(max_shift_mm) or not 0<max_shift_mm<=32.
            or type(allow_owned_locked_escapes) is not bool or type(rebuild_projected_ground) is not bool
            or type(allow_octilinear_rotations) is not bool
            or type(allow_linear_power_stage_reconstruction) is not bool):
        raise ValueError('bounded_complete_saved_cell_receiving_required')
    escape.aggregate_cap_shift_bound(aggregate_capacitor_max_shift_mm)
    shared_supply_root_pad_uuids=escape.shared_fork.supply_root_ids(shared_supply_root_pad_uuids)
    started=time.monotonic();r=dict(ok=False,complete=False,errors=[],routing_admitted=False,
        fab_ready=False,release_authority=False,current_qualified=False,
        independent_stage_max_seconds=timeout_s,explicit_maximum_receiving_stages=3,
        whole_original_current_field_pair_Kelvin_DRC_and_stack_receiving_still_required=True)
    try:
        paths=[Path(p).resolve() for p in (source,candidate)]
        if paths[0]==paths[1]:raise ValueError('distinct_saved_cell_source_and_candidate_required')
        families=[force._family(p,board_hint) for p in paths];epoch=force._code_identity()
        deadline=time.monotonic()+timeout_s
        parent,child=[pcbnew.LoadBoard(str(p)) for p in paths]
        poses,moved=_poses(parent,child,board_hint,reference_group_uuids)
        plan=escape.prepare(parent,poses,board_hint=board_hint,max_shift_mm=max_shift_mm,
            allow_owned_locked_escapes=allow_owned_locked_escapes,rebuild_projected_ground=rebuild_projected_ground,
            allow_octilinear_rotations=allow_octilinear_rotations,reference_group_uuids=reference_group_uuids,
            **(dict(aggregate_capacitor_max_shift_mm=aggregate_capacitor_max_shift_mm)
                if aggregate_capacitor_max_shift_mm is not None else {}),
            **(dict(allow_linear_power_stage_reconstruction=True)
                if allow_linear_power_stage_reconstruction else {}),
            **(dict(shared_supply_root_pad_uuids=shared_supply_root_pad_uuids)
                if shared_supply_root_pad_uuids else {}))
        # Source-rederive each exact whole annotation group. The complete
        # cell still owes all normal copper/current/ground/pose receiving.
        if reference_group_uuids:
            _receive_reference_transports(paths[1],plan)
        projected=pcbnew.LoadBoard(str(paths[0]));escape.apply_private(projected,plan)
        requests=escape.obligations(parent,projected,plan)
        r['inherited_unplanned_terminals']=escape.unplanned_source_terminals(parent,plan,requests,board=projected)
        if r['inherited_unplanned_terminals']:
            raise ValueError('isolated_source_terminals_have_no_complete_saved_routing_obligation')
        with tempfile.TemporaryDirectory(prefix='cec-complete-saved-cell-') as work:
            expected=force._copy_family(paths[0],Path(work)/'expected')
            additive._ground_refill(projected)
            r['literal_source_projection_context'] = _save_literal_projection(
                paths[0], expected, projected, plan, moved)
            if reference_group_uuids:
                import cec_complete_macro_cell as complete_macro
                row_plan=plan['row_plan']
                requests_to_save=[(proof,
                    int((row_plan['target_poses'][ref][2]-row_plan['source_poses'][ref][2])%360)//90,
                    tuple(round((row_plan['target_poses'][ref][k]-row_plan['source_poses'][ref][k])*1e6)
                        for k in (0,1)))
                    for ref,proof in row_plan['source_reference_group_transports'].items()]
                complete_macro._save_cardinal_reference_nodes(expected,requests_to_save,
                    maximum_translation_mm=escape.complete_transport_shift_bound(plan))
            remaining=min(10.,deadline-time.monotonic())
            if remaining<=0:raise ValueError('complete_cell_source_replay_deadline')
            proof=additive.receive(expected,paths[1],timeout_s=remaining,board_hint=board_hint,
                allow_endpoint_neckdown_additions=True)
            r['independent_exact_cut_pose_and_additions']=proof
            if not proof['ok'] or not proof['complete']:
                raise ValueError('complete_cell_exact_saved_replay_refused:'+str(proof['errors']))
        deadline=time.monotonic()+timeout_s
        native_tracks={force._uid(t) for t in child.GetTracks()}
        incoming=set(proof['added_native_uuids'])&native_tracks
        r['actual_native_terminal_paths']=_receive_paths(parent,child,requests,incoming,board_hint,deadline,
            allow_retained_no_additions=not incoming and not plan['retired_track_uuids'],
            source_proposal=plan)
        r['paired_actual_filled_island_preservation']=_preserve_partitions(
            parent,child,poses,set(plan['retired_track_uuids']),deadline)
        r['all_original_surviving_native_partitions_preserved']=True
        returns=ground.receive(parent,child,timeout_s=timeout_s);r['all_source_ground_returns']=returns
        if not returns['ok'] or not returns['complete']:raise ValueError('saved_cell_ground_nonregression_refused')
        import cec_source_no_connect as no_connect
        if (families!=[force._family(p,board_hint) for p in paths] or epoch!=force._code_identity()
                or not no_connect.bindings_current(plan.get('source_explicit_schematic_no_connects',[]))
                or time.monotonic()-started>timeout_s*3):
            raise ValueError('saved_cell_identity_or_explicit_work_bound_changed')
        r.update(ok=True,complete=True,source_sha256=force._hash(paths[0]),candidate_sha256=force._hash(paths[1]),
            source_plan=plan,moved_refs=sorted(moved),retired_track_uuids=plan['retired_track_uuids'],
            added_native_uuids=sorted(incoming),source_candidate_families_and_code_unchanged=True)
    except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:
        r['errors'].append(type(exc).__name__+':'+str(exc))
    r['elapsed_s']=time.monotonic()-started
    return r
