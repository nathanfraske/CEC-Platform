"""After-staging observation of Source-typed SMD Ground boundary contacts.

No route, hole, aggregate Ground current, remote return or release authority.
Old track/barrel-only observers are unchanged. Every SMD port separately owes
its freshly compiled mandatory physical local return, even when a filled
reference island already connects the named boundary contacts.
"""
import json
import copy
import math
import time
import weakref
from dataclasses import dataclass
from pathlib import Path
import pcbnew
import cec_force_current as force
import cec_cell_row_rebuild as row
import cec_cell_escape_replan as escape
import cec_cell_macro_requests as compiler
import cec_decoupler_cell as cells
import cec_native_partition_pair as partitions
import cec_device_power_roles as roles
import cec_ground_return_shortcut as reference
import cec_fab_profile as fab


def _stable(value):return json.dumps(value,sort_keys=True,allow_nan=False)


_ISSUED_OBSERVERS=weakref.WeakSet()


@dataclass(frozen=True,eq=False)
class _PreparedObserver:
    """Private immutable Source expectation, never a saved child witness."""
    observe_live:object
    context:tuple

    def __call__(self,board,*,timeout_s=10.):
        return self.observe_live(board,timeout_s=timeout_s)

    def matches(self,parent,requests,*,board_hint,source_proposal,source_macro_packet):
        return self in _ISSUED_OBSERVERS and self.context==_observer_context(
            parent,requests,board_hint,source_proposal,source_macro_packet)


def _issue_observer(observe_live,context):
    result=_PreparedObserver(observe_live,context);_ISSUED_OBSERVERS.add(result)
    return result


def _observer_context(parent,requests,hint,proposal,macro_packet):
    return (str(Path(parent.GetFileName()).resolve()),row._source_binding(parent),force._code_identity(),
        hint,_stable(requests),_stable(proposal),_stable(macro_packet))


def _tick(deadline):
    if time.monotonic()>=deadline:raise ValueError('source_ground_boundary_observer_deadline')


def _metal(item):
    if item.GetClass()=='PCB_TRACK':return (item.GetClass(),item.GetNetname(),int(item.GetLayer()),
        tuple(item.GetStart()),tuple(item.GetEnd()),int(item.GetWidth()),bool(item.IsLocked()))
    if item.GetClass()=='PCB_VIA':return (item.GetClass(),item.GetNetname(),tuple(item.GetPosition()),
        int(item.GetViaType()),int(item.TopLayer()),int(item.BottomLayer()),int(item.GetDrillValue()),
        tuple((int(l),int(item.GetWidth(l)))for l in item.GetLayerSet().CuStack()),bool(item.IsLocked()))
    return None


def _pad_contact_identity(pad):
    fp=pad.GetParentFootprint()
    return (force._item_key(pad),force._uid(fp),fp.GetFPIDAsString(),fp.GetValue(),
        tuple(sorted((f.GetName(),f.GetText())for f in fp.GetFields())),bool(fp.IsFlipped()),
        pad.GetNetname(),int(pad.GetAttribute()),int(pad.GetShape()),tuple(pad.GetSize()),
        tuple(pad.GetDrillSize()),tuple(pad.GetOffset()),float(pad.GetOrientationDegrees()),
        float(pad.GetRoundRectRadiusRatio()),tuple(map(int,pad.GetLayerSet().CuStack())))


def _observe_cut_one(parent,board,request,*,board_hint,context,deadline):
    """Literal compiler-rederived cut contacts, including actual fill islands.

    This does not infer a return from a shared Ground label or zone owner.
    The original cut request must match the private Source recompile. Every
    named real contact must be on the same native filled-copper component;
    moving typed Ground terminals still owe their own bounded local return.
    """
    if (request.get('kind')!='ground_boundary'or request.get('net')!='GND'
            or not any(_stable(request)==_stable(r)for r in context['cut_ground'].values())):return None
    source=request.get('retained_source_ground_fragment')or {}
    if (source.get('actual_fixed_source_contacts_not_same_net_proximity')is not True
            or source.get('whole_original_current_plane_and_saved_partition_receiving_required')is not True):return None
    enabled=set(map(int,board.GetEnabledLayers().CuStack()));named=[];local=[]
    simple=(pcbnew.PAD_SHAPE_RECT,pcbnew.PAD_SHAPE_ROUNDRECT,pcbnew.PAD_SHAPE_CIRCLE,pcbnew.PAD_SHAPE_OVAL)
    # A single custom-pad item may contain disconnected primitives. Do not
    # let native whole-item identity bridge those islands in this observer.
    if any(p.GetNetname()=='GND'and p.GetShape()not in simple
            for f in board.GetFootprints()for p in f.Pads()):return None
    for name in('a','b'):
        _tick(deadline);port=request.get(name,{})
        point=port.get('at_nm');faces=port.get('layers')
        if (type(point)is not list or len(point)!=2 or any(type(v)is not int for v in point)
                or type(faces)is not list or not faces or len(set(faces))!=len(faces)
                or any(type(v)is not int or v not in enabled for v in faces)):return None
        uid=port.get('pad_uuid')
        if uid is not None:
            expected=context['projected_pads'].get(uid);pad=context['live_pads'].get(uid)
            if (uid in context['ambiguous_pad_uuids']or expected is None or pad is None
                    or port.get('native_uuids')is not None
                    or _pad_contact_identity(expected)!=_pad_contact_identity(pad)
                    or list(pad.GetPosition())!=point or pad.GetNetname()!='GND'
                    or sorted(map(int,pad.GetLayerSet().CuStack()))!=sorted(faces)):return None
            items=[pad]
            ground=context['ground'].get('ground:'+uid)
            if name=='a'and ground is None:return None
            if ground is not None:
                if ground['a']!=port:return None
                immediate=cells._existing_return(board,pad,ground['reach_mm'],allow_native_track_body=True)
                if immediate is None:
                    import cec_saved_ground_hierarchy as hierarchy
                    try:evidence=hierarchy.receive(parent,board,ground,context['ground'],board_hint=board_hint,
                        deadline=deadline,source_proposal=context['fresh'])
                    except ValueError:return None
                    via=context['live'].get(evidence.get('via_uuid'))
                    evidence=dict(hierarchy=evidence)
                else:
                    via=immediate[1];evidence=dict(return_mm=immediate[0],max_return_mm=ground['reach_mm'])
                if via is None:return None
                local.append(dict(evidence,pad_uuid=uid,via_uuid=force._uid(via),
                    original_physical_return_and_via_process_receiving_still_required=True))
        else:
            ids=port.get('native_uuids')
            if (type(ids)is not list or not 1<=len(ids)<=16 or len(set(ids))!=len(ids)
                    or any(type(u)is not str or u not in context['old']or u not in context['live']for u in ids)):return None
            items=[context['live'][u]for u in ids]
            if any(force._uid(i)not in context['projected_tracks']
                    or _metal(context['projected_tracks'][force._uid(i)])is None
                    or _metal(context['projected_tracks'][force._uid(i)])!=_metal(i)for i in items):return None
        for item in items:
            if (item.GetNetname()!='GND'or item.GetNetCode()<=0 or any(not item.IsOnLayer(face)
                    or not item.GetEffectiveShape(face).Collide(pcbnew.VECTOR2I(*point),0)for face in faces)):return None
            named.append(force._item_key(item))
    _tick(deadline)
    if context['inventory']is None:
        context['inventory']=partitions._inventory(board,deadline,dict(items=16384,polygons=4096,vertices=200000))
    actual=context['inventory']['component_of']
    if any(key not in actual for key in named)or len({actual[key]for key in named})!=1:return None
    return dict(scope='source_recompiled_ground_cut_endpoint_connection',all_named_contacts_connected=True,
        actual_native_filled_island_connectivity_proved=True,whole_zone_uuid_connectivity_credit=False,
        independently_received_local_ground_returns=local,new_copper=0,new_holes=0,
        remote_smd_return_not_inferred=True,original_source_partitions_and_current_receiving_still_required=True,
        current_qualified=False,routing_admitted=False,release_authority=False)


def _observe_one(parent,board,request,requests,*,board_hint,context,deadline):
    if type(request)is dict and request.get('kind')=='ground_boundary':
        return _observe_cut_one(parent,board,request,board_hint=board_hint,context=context,deadline=deadline)
    if (type(request)is not dict or request.get('kind')!='source_boundary'or request.get('net')!='GND'
            or request.get('every_surviving_source_component_port_mandatory')is not True
            or type(requests)is not dict or not 1<=len(requests)<=64
            or not any(_stable(request)==_stable(v)for v in requests.values())):return None
    authorities=request.get('exact_additional_macro_component_source_ownership')
    if type(authorities)is not list or not 1<=len(authorities)<=64:return None
    if not any(type(request.get(n))is dict and request[n].get('pad_uuid')for n in('a','b')):return None
    fresh=context['fresh'];pads=context['pads'];live_pads=context['live_pads']
    old=context['old'];live=context['live'];expected_ground=context['ground']
    roots={};fixed_controls={};widths=[];seen=set()
    for authority in authorities:
        _tick(deadline)
        if (type(authority)is not dict
                or type(authority.get('native_source_uuid'))is not str):return None
        uid=authority['native_source_uuid'];edge=old.get(uid)
        if uid in seen or edge is None or edge.GetClass()!='PCB_TRACK'or edge.GetNetname()!='GND':return None
        seen.add(uid)
        import cec_source_ground_continuation as continuation
        if authority.get('kind')==continuation.KIND:
            # Only the private observer's independent WHOLE Source compile
            # may supply this distinct authority. A continuation is not
            # falsely described as pad-incident or trusted from a request.
            expected=context['continuation_authority_cache'].get(uid)
            root_authorities=continuation.ground_root_authorities(expected)
            if root_authorities is None:return None
            pad_roots=[r for a in root_authorities for r in a['source_pad_roots']]
        else:
            if authority.get('source_owned_barrel_roots')!=[]:return None
            if uid not in context['authority_cache']:
                try:context['authority_cache'][uid]=compiler._ground_boundary_authority(parent,edge,
                    dict(source_process_barrel_motion=[]),fresh,deadline)
                except ValueError:return None
            expected=context['authority_cache'][uid]
            pad_roots=expected.get('source_pad_roots',[])if type(expected)is dict else []
        if type(expected)is not dict:return None
        if _stable(expected)!=_stable(authority):return None
        try:
            from cec_retained_ground_control_port import retained_control_ports
            fixed_controls.update(retained_control_ports(parent,board,expected,context,deadline))
        except ValueError:return None
        for root in pad_roots:
            import cec_programming_resistor_placement as programming
            if root['role']==programming.GROUND_ROLE:
                if not programming.ground_root_label(root):return None
            elif root['role']not in('ground','reference','power_return','address','source_selected_bypass_ground'):return None
            roots[root['pad_uuid']]=root
        widths.extend([expected['source_width_nm'],expected['source_full_class_width_nm']])
    if not roots or type(request.get('width_nm'))is not int or request['width_nm']!=max(widths):return None
    enabled=set(map(int,board.GetEnabledLayers().CuStack()));named=[];local=[]
    for name in('a','b'):
        _tick(deadline);port=request.get(name)
        if type(port)is not dict:return None
        point=port.get('at_nm');faces=port.get('layers')
        if (type(point)is not list or len(point)!=2 or any(type(v)is not int for v in point)
                or type(faces)is not list or not faces or len(set(faces))!=len(faces)
                or any(type(v)is not int or v not in enabled for v in faces)):return None
        uid=port.get('pad_uuid')
        if uid is not None:
            if uid in fixed_controls:
                pad=live_pads.get(uid)
                if (pad is None or port.get('native_uuids')is not None
                        or list(pad.GetPosition())!=point
                        or sorted(map(int,pad.GetLayerSet().CuStack()))!=sorted(faces)):return None
                named.append(force._item_key(pad));continue
            if uid not in roots or port.get('native_uuids')is not None:return None
            source=pads.get(uid);pad=live_pads.get(uid)
            if (source is None or pad is None or pad.HasHole()or source.HasHole()
                    or pad.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD or pad.GetNetname()!='GND'
                    or pad.GetNumber()!=source.GetNumber()
                    or list(pad.GetPosition())!=point
                    or sorted(map(int,pad.GetLayerSet().CuStack()))!=sorted(faces)
                    or list(pad.GetLayerSet().CuStack())!=list(source.GetLayerSet().CuStack())):return None
            first,last=source.GetParentFootprint(),pad.GetParentFootprint()
            if (force._uid(first)!=force._uid(last)or first.GetFPIDAsString()!=last.GetFPIDAsString()
                    or context['source_population'].get(first.GetReference())!=
                    context['saved_population'].get(last.GetReference())
                    or {f.GetName():f.GetText()for f in first.GetFields()}!=
                    {f.GetName():f.GetText()for f in last.GetFields()}):return None
            model=roles.footprint_contract(first)
            if roots[uid]['role']!='source_selected_bypass_ground'and roles.footprint_contract(last)!=model:return None
            ground=expected_ground.get('ground:'+uid)
            if ground is None or ground['a']!=port:return None
            if uid in context['return_cache']:
                local.append(context['return_cache'][uid]);named.append(force._item_key(pad));continue
            immediate=cells._existing_return(board,pad,ground['reach_mm'],allow_native_track_body=True)
            if immediate is None:
                import cec_saved_ground_hierarchy as hierarchy
                try:proof=hierarchy.receive(parent,board,ground,expected_ground,board_hint=board_hint,
                    deadline=deadline,source_proposal=fresh)
                except ValueError:return None
                via=live.get(proof.get('via_uuid'));evidence=dict(hierarchy=proof)
            else:via=immediate[1];evidence=dict(return_mm=immediate[0],max_return_mm=ground['reach_mm'])
            if via is None:return None
            diameter,drill=via.GetWidth(via.TopLayer())/1e6,via.GetDrillValue()/1e6
            if (fab.board_legal_through_via_geometry(board,diameter,drill)[:2]!=(diameter,drill)
                    and not fab.local_pofv_via_decision(board,via,allow_source_track_body=True)[0]):return None
            try:contacts=reference._reference_contacts(board,via)
            except ValueError:return None
            evidence.update(pad_uuid=uid,via_uuid=force._uid(via),actual_filled_reference_contacts=contacts)
            context['return_cache'][uid]=evidence
            local.append(evidence);named.append(force._item_key(pad))
        else:
            ids=port.get('native_uuids')
            if (type(ids)is not list or not 1<=len(ids)<=16 or len(set(ids))!=len(ids)
                    or any(type(u)is not str or u not in old or u not in live for u in ids)):return None
            for uid in ids:
                source,item=old[uid],live[uid]
                if (_metal(source)is None or _metal(source)!=_metal(item)or item.GetNetname()!='GND'
                        or any(not item.IsOnLayer(face)or not item.GetEffectiveShape(face).Collide(
                            pcbnew.VECTOR2I(*point),0)for face in faces)):return None
                named.append(force._item_key(item))
    _tick(deadline)
    if context['inventory']is None:
        context['inventory']=partitions._inventory(board,deadline,dict(items=16384,polygons=4096,vertices=200000))
    inventory=context['inventory']
    if any(key not in inventory['component_of']for key in named):return None
    if len({inventory['component_of'][key]for key in named})!=1:return None
    _tick(deadline)
    return dict(scope='source_recompiled_smd_ground_boundary_connection',all_named_contacts_connected=True,
        actual_native_filled_island_connectivity_proved=True,whole_zone_uuid_connectivity_credit=False,
        independently_received_local_ground_returns=local,source_width_preserved_not_current_rating=True,
        fixed_retained_control_ports=[fixed_controls[u]for u in sorted(fixed_controls)],
        new_copper=0,new_holes=0,new_hole_admission_authority=False,remote_smd_return_not_inferred=True,
        whole_original_current_field_native_and_saved_receiving_still_required=True,
        current_qualified=False,routing_admitted=False,release_authority=False)


def _prepare_observer(parent,requests,*,board_hint,source_proposal,timeout_s=10.,source_macro_packet=None,
                      compile_phase_observer=None):
    """Private fresh Source expectation; never accepts a caller cache/proof.

    The returned closure owns immutable Source expectations only. Every call
    reconstructs live copper, filled-island and local-return evidence.
    """
    if (type(timeout_s)not in(int,float)or not math.isfinite(timeout_s)or not 0<timeout_s<=10
            or type(board_hint)is not str or not board_hint):
        raise ValueError('bounded_source_ground_boundary_observer_context_required')
    if compile_phase_observer is not None and not callable(compile_phase_observer):
        raise ValueError('source_ground_compilation_phase_observer_required')
    if type(requests)is not dict or not 1<=len(requests)<=64 or any(type(r)is not dict for r in requests.values()):
        raise ValueError('bounded_source_ground_boundary_requests_required')
    requests=copy.deepcopy(requests);source_proposal=copy.deepcopy(source_proposal)
    result={key:None for key in requests};deadline=time.monotonic()+timeout_s
    expectation_context=_observer_context(parent,requests,board_hint,source_proposal,source_macro_packet)
    def refused():return _issue_observer(lambda board,timeout_s=10.:dict(result),expectation_context)
    if type(source_proposal)is not dict:return refused()
    binding=row._source_binding(parent);code=force._code_identity()
    family=force._family(parent.GetFileName(),board_hint)
    import cec_route_placement_admission as placement
    source_population=placement._population(parent)
    authority_cache={};continuation_authority_cache={}
    try:
        if source_proposal.get('board_hint')!=board_hint:raise ValueError('source_ground_boundary_hint_mismatch')
        projected=pcbnew.LoadBoard(parent.GetFileName())
        if projected is None or row._source_binding(projected)!=binding:raise ValueError('source_ground_boundary_source_mismatch')
        # apply_private itself freshly recompiles and EXACTLY compares the
        # entire proposal before applying its owned cut. Do not repeat that
        # expensive Source compilation for every boundary or once more here.
        if source_macro_packet is None:
            escape.apply_private(projected,source_proposal)
            fresh=source_proposal
            source_requests=escape.obligations(parent,projected,fresh)
        else:
            # Recompile the WHOLE native macro, including its positively
            # owned transported barrels and extra cuts. The base SMD cut is
            # not an equivalent expectation for a transformed source root.
            # A caller's macro packet is only reconstructible input; compare
            # every field against this independent Source compilation.
            if type(source_macro_packet)is not dict:raise ValueError('source_ground_macro_packet_required')
            options=compiler.packet_options(source_macro_packet)
            budgets=options.get('compilation_phase_timeouts_s')
            if budgets is not None and any(v>timeout_s for v in budgets):
                raise ValueError('source_ground_compilation_constituents_exceed_observer_limit')
            def compile_source():
                return compiler.compile(parent.GetFileName(),source_proposal['poses'],board_hint=board_hint,
                max_shift_mm=source_proposal['max_shift_mm'],timeout_s=max(.001,deadline-time.monotonic()),
                allow_owned_locked_escapes=source_proposal.get('allow_owned_locked_escapes',False),
                rebuild_projected_ground=source_proposal.get('rebuild_projected_ground',False),
                additional_obstacle_track_uuids=source_macro_packet.get('explicit_additional_obstacle_track_uuids',[]),
                    **options)
            if budgets is None:projected,compiled=compile_source()
            else:
                original_started=deadline-timeout_s
                def observe(event):
                    nonlocal deadline
                    if event['event']=='start':
                        if event['index']:
                            _tick(deadline);deadline=time.monotonic()+budgets[event['index']]
                        else:deadline=min(deadline,original_started+budgets[0])
                    _tick(deadline)
                    if compile_phase_observer is not None:compile_phase_observer(event)
                with compiler.observe_compilation_phases(observe):projected,compiled=compile_source()
                _tick(deadline);deadline=time.monotonic()+timeout_s
                if compile_phase_observer is not None:compile_phase_observer(dict(event='expectation_start'))
            if (_stable(compiled)!=_stable(source_macro_packet)
                    or _stable(compiled['source_plan'])!=_stable(source_proposal)):
                raise ValueError('source_ground_macro_packet_source_recompile_differs')
            fresh=compiled['source_plan'];source_requests=compiled['requests']
            def component_ground(values):
                return {k:r for k,r in values.items()
                    if r.get('kind')=='source_boundary'and r.get('net')=='GND'}
            # Bind the complete original port obligations even if a caller
            # strips the continuation marker and tries the legacy path.
            if _stable(component_ground(requests))!=_stable(component_ground(source_requests)):
                raise ValueError('source_ground_complete_component_requests_differ')
            import cec_source_ground_continuation as continuation
            for item in compiled['additional_source_boundary_ownership']:
                authority=item['authority']
                if authority.get('kind')!=continuation.KIND:continue
                if continuation.ground_root_authorities(authority)is None:
                    raise ValueError('source_ground_fresh_continuation_roots_required')
                uid=authority['native_source_uuid']
                if uid in continuation_authority_cache:
                    raise ValueError('source_ground_unique_fresh_continuation_required')
                continuation_authority_cache[uid]=copy.deepcopy(authority)
        ground={k:r for k,r in source_requests.items()if r['kind']=='ground'}
        cut_ground={k:r for k,r in source_requests.items()if r['kind']=='ground_boundary'}
        if _stable(ground)!=_stable({k:r for k,r in requests.items()if r.get('kind')=='ground'}):
            raise ValueError('source_ground_boundary_mandatory_requests_differ')
        old={force._uid(t):t for t in parent.GetTracks()}
        import cec_source_ground_continuation as continuation
        for request in requests.values():
            if request.get('kind')!='source_boundary' or request.get('net')!='GND':continue
            for authority in request.get('exact_additional_macro_component_source_ownership',[]):
                _tick(deadline)
                uid=authority.get('native_source_uuid') if type(authority)is dict else None
                edge=old.get(uid)
                if type(authority)is dict and authority.get('kind')==continuation.KIND:
                    # This has already been freshly recompiled as a complete
                    # continuation, not an incident pad lead. Reclassifying it
                    # through the legacy pad/cap fallback is both redundant
                    # and wrong; only the exact independent cache may supply
                    # its authority. _observe_one still rechecks live copper,
                    # filled islands and EVERY actual local return.
                    expected=continuation_authority_cache.get(uid)
                    if type(expected)is not dict or _stable(expected)!=_stable(authority):
                        raise ValueError('source_ground_fresh_typed_continuation_required')
                    continue
                if edge is not None and uid not in authority_cache:
                    try:authority_cache[uid]=compiler._ground_boundary_authority(parent,edge,
                        dict(source_process_barrel_motion=[]),fresh,deadline)
                    except ValueError:authority_cache[uid]=None
        _tick(deadline)
        if (code!=force._code_identity() or binding!=row._source_binding(parent)
                or family!=force._family(parent.GetFileName(),board_hint)):
            raise ValueError('source_ground_boundary_observer_epoch_or_geometry_changed')
    except ValueError as exc:
        if 'deadline'in str(exc) or 'epoch_or_geometry_changed'in str(exc):raise
        return refused()

    def observe_live(board,*,timeout_s=10.):
        if type(timeout_s)not in(int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10:
            raise ValueError('bounded_source_ground_boundary_observer_context_required')
        deadline=time.monotonic()+timeout_s;live_binding=row._source_binding(board)
        def current():
            return (code==force._code_identity() and binding==row._source_binding(parent)
                and family==force._family(parent.GetFileName(),board_hint))
        if not current():raise ValueError('source_ground_boundary_observer_epoch_or_geometry_changed')
        answer=dict(result)
        if (fab.board_profile_name(parent)!=fab.board_profile_name(board)
                or tuple(parent.GetEnabledLayers().CuStack())!=tuple(board.GetEnabledLayers().CuStack())
                or cells._netclass(parent,'GND')!=cells._netclass(board,'GND')
                or parent.GetDesignSettings().m_TrackMinWidth!=board.GetDesignSettings().m_TrackMinWidth
                or parent.GetDesignSettings().m_MinClearance!=board.GetDesignSettings().m_MinClearance):return answer
        for ref,pose in fresh['poses'].items():
            before=parent.FindFootprintByReference(ref);after=board.FindFootprintByReference(ref)
            if (before is None or after is None or before.IsFlipped()!=after.IsFlipped()
                    or tuple(after.GetPosition())!=tuple(round(v*1e6)for v in pose[:2])
                    or (after.GetOrientationDegrees()-pose[2])%360!=0):return answer
        projected_pad_rows=[p for f in projected.GetFootprints()for p in f.Pads()]
        actual_pad_rows=[p for f in board.GetFootprints()for p in f.Pads()]
        counts={}
        for p in [*projected_pad_rows,*actual_pad_rows]:counts[force._uid(p)]=counts.get(force._uid(p),0)+1
        context=dict(fresh=fresh,ground=ground,cut_ground=cut_ground,projected_board_owner=projected,
            projected_pads={force._uid(p):p for p in projected_pad_rows},
            projected_tracks={force._uid(t):t for t in projected.GetTracks()},
            ambiguous_pad_uuids={uid for uid,count in counts.items()if count!=2},
            inventory=None,authority_cache=dict(authority_cache),
            continuation_authority_cache=copy.deepcopy(continuation_authority_cache),return_cache={},
            pads={force._uid(p):p for f in parent.GetFootprints()for p in f.Pads()},
            live_pads={force._uid(p):p for f in board.GetFootprints()for p in f.Pads()},
            old=old,live={force._uid(t):t for t in board.GetTracks()})
        context.update(source_population=source_population,saved_population=placement._population(board))
        if len(context['pads'])+len(old)>16384 or len(context['live_pads'])+len(context['live'])>16384:return answer
        for key,request in requests.items():
            _tick(deadline)
            answer[key]=_observe_one(parent,board,request,requests,board_hint=board_hint,context=context,deadline=deadline)
        _tick(deadline)
        if not current() or live_binding!=row._source_binding(board):
            raise ValueError('source_ground_boundary_observer_epoch_or_geometry_changed')
        return answer
    return _issue_observer(observe_live,expectation_context)


def observe_many(parent,board,requests,*,board_hint,source_proposal,timeout_s=10.,source_macro_packet=None):
    """Saved observers always freshly prepare their OWN Source expectation."""
    started=time.monotonic()
    observe_live=_prepare_observer(parent,requests,board_hint=board_hint,
        source_proposal=source_proposal,timeout_s=timeout_s,source_macro_packet=source_macro_packet)
    remaining=timeout_s-(time.monotonic()-started)
    if remaining<=0:raise ValueError('source_ground_boundary_observer_deadline')
    return observe_live(board,timeout_s=remaining)


def observe(parent,board,request,requests,*,board_hint,source_proposal,timeout_s=10.):
    """Convenience wrapper; batch API is preferred for complete selections."""
    if type(requests)is not dict:return None
    keys=[k for k,r in requests.items()if _stable(r)==_stable(request)]
    if not keys:
        # Validate even an ineligible request's explicit timeout contract.
        if type(timeout_s)not in(int,float)or not math.isfinite(timeout_s)or not 0<timeout_s<=10:
            raise ValueError('bounded_source_ground_boundary_observer_context_required')
        return None
    return observe_many(parent,board,requests,board_hint=board_hint,source_proposal=source_proposal,
        timeout_s=timeout_s)[keys[0]]
