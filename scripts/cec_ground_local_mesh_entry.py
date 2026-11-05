"""Join typed low-power islands using the actual saved local pad dimensions.

Distinct from the ordinary remote mesh entry. Only an unchanged source SMD
owner, a <=1.5mm actual 0/45 path and a source-local rule AT OR ABOVE every
ordinary board floor qualify. No new rule or sub-setup dimension is granted.
All saved reference annuli, native source partitions, endpoint widths and
all-layer/fab/hole checks remain independent admission obligations.
"""
import math
import time

import pcbnew
import cec_cell_endpoint_groups as endpoints
import cec_cell_row_rebuild as row
import cec_additive_portal_compaction as portal
import cec_decoupler_cell as cells
import cec_fab_profile as fab
import cec_force_current as force
import cec_fr as fr
import cec_ground_access_completion as access
import cec_ground_component_join as join
import cec_ground_mesh_entry as mesh
import cec_ground_return_shortcut as ground
import cec_native_via_frontier as frontier
import cec_native_contained_via_events as contained
from cec_native_items import discard_items


def _source_geometry(board,pad):
    context,group,geometry=access._existing_pad_rule(board,pad)
    if context.get('all_local_dimensions_at_or_above_ordinary_setup') is not True:
        raise ValueError('local_ground_entry_requires_all_ordinary_setup_floors')
    return context,group,tuple(round(v*1e6) for v in geometry)


def _owner(context,uid):
    allowed={r['a']['pad_uuid'] for r in context['requests'].values()}
    pad=next((i for i in context['live'].values()
        if i.GetClass()=='PAD' and force._uid(i)==uid),None)
    if (pad is None or uid not in allowed or not any(force._item_key(pad) in q
            for q in context['islands'])):
        raise ValueError('actual_detached_source_typed_low_power_ground_pad_required')
    return pad


def _receive_barrel(parent,child,via,pad_uuid,hint,deadline):
    context=join._context(parent,hint,deadline);pad=_owner(context,pad_uuid)
    _,group,expected=_source_geometry(parent,pad)
    if (via.GetClass()!='PCB_VIA' or via.GetNetname()!='GND'
            or via.GetViaType()!=pcbnew.VIATYPE_THROUGH
            or via.TopLayer()!=pcbnew.F_Cu or via.BottomLayer()!=pcbnew.B_Cu
            or (via.GetWidth(via.TopLayer()),via.GetDrillValue())!=expected
            or any(via.GetWidth(l)!=expected[0] for l in via.GetLayerSet().CuStack())
            or math.dist(tuple(pad.GetPosition()),tuple(via.GetPosition()))>1500000):
        raise ValueError('exact_source_local_ground_barrel_dimensions_and_reach_required')
    gaps=cells._netclass(child,'GND');gap=max(200000,int(gaps['clearance']),int(child.GetDesignSettings().m_MinClearance))
    at=via.GetPosition();uid=force._uid(via)
    if (not fr._edge_leg_clear(child,at,at,expected[0]/2+gap)
            or not cells._hole_to_hole_clear(child,at,expected[1]/1e6,ignore_via_uuids=(uid,))[0]
            or not fr._via_spot_clear(child,at,expected[0],gap,{via.GetNetCode()},
                drill_nm=expected[1],net_code=via.GetNetCode(),existing_via_uuid=uid,report={})
            or fab.via_at_pad_conflicts(child,at,*expected,via.GetNetCode())[0] is not None):
        raise ValueError('source_local_ground_barrel_live_native_process_or_clearance_refused')
    # This remains an actual source-owned local entry, not a remote smaller
    # field. Additive saving may bind it to the EXISTING exact group only.
    groups=[g for g in child.Groups() if g.ContainsItem(via)]
    if any(force._uid(g)!=group for g in groups):
        raise ValueError('source_local_ground_barrel_has_unrelated_group_owner')
    saved_pad=next(p for f in child.GetFootprints() for p in f.Pads() if force._uid(p)==pad_uuid)
    actual=cells._existing_return(child,saved_pad,1.5,allow_native_track_body=True)
    if actual is None or force._uid(actual[1])!=uid:
        raise ValueError('source_local_ground_pad_requires_actual_bounded_return_to_new_axis')
    contacts=ground._reference_contacts(child,via)
    mesh._reference_envelopes(child,via,contacts,deadline)
    return dict(pad_uuid=pad_uuid,via_uuid=uid,diameter_nm=expected[0],drill_nm=expected[1],
        all_local_dimensions_at_or_above_ordinary_setup=True,
        actual_saved_reference_contacts=contacts,full_native_reference_envelopes=True,
        current_capacity_qualified=False,release_authority=False)


def plan(board,*,board_hint,timeout_s=10.,pad_uuid=None):
    deadline=join._deadline(timeout_s);binding=row._source_binding(board)
    result=dict(scope='source_typed_local_ground_mesh_entry',board_hint=board_hint,
        source_native_binding=binding,complete=False,ops=[],trials=[],
        routing_admitted=False,current_qualified=False,release_authority=False,no_path_proof=False)
    try:
        context=join._target_context(join._context(board,board_hint,deadline),pad_uuid)
        if pad_uuid is not None:result['target_pad_uuid']=pad_uuid
        spec=cells._netclass(board,'GND');width=max(200000,int(spec['width']),int(board.GetDesignSettings().m_TrackMinWidth))
        gap=max(200000,int(spec['clearance']),int(board.GetDesignSettings().m_MinClearance))
        code=board.GetNetcodeFromNetname('GND');allowed={r['a']['pad_uuid'] for r in context['requests'].values()}
        for index,island in enumerate(context['islands']):
            local_deadline=mesh._island_deadline(deadline,len(context['islands'])-index)
            pads=sorted((context['live'][k] for k in island if context['live'][k].GetClass()=='PAD'
                and force._uid(context['live'][k]) in allowed),key=force._uid)
            for pad in pads[:4]:
                if time.monotonic()>=local_deadline:break
                trial=dict(pad_uuid=force._uid(pad),sites_tested=0);result['trials'].append(trial)
                try:_,_,(dia,drill)=_source_geometry(board,pad)
                except ValueError as exc:trial['refusal']=str(exc);continue
                face=cells.cec_return_escape.smd_surface_layer(pad)
                if face is None:continue
                start=pad.GetPosition();escape=fr._pad_local_escape(pad,width,gap,max(200000,int(board.GetDesignSettings().m_TrackMinWidth)))
                seats=[tuple(start)]
                # Actual Source-local dimensions already passed EVERY setup
                # floor above. A centre-blocking buried track need not rule
                # out the whole SMD land: try strictly contained native free
                # intervals before remote mesh sites. This grants no smaller
                # geometry, Source cut, reference-plane or current credit.
                interior=contained.candidates(board,pad,dia,gap,
                    deadline=min(local_deadline,time.monotonic()+.5))
                if interior['complete']:
                    seats.extend(tuple(e['at_nm'])for e in interior['events'])
                trial['native_contained_events']={k:v for k,v in interior.items()if k!='events'}
                found=frontier.sites(board,code,tuple(start),clearance_nm=gap,radius_mm=1.5,
                    max_sites=12,deadline=local_deadline,diverse=True,diameter_mm=dia/1e6,drill_mm=drill/1e6,
                    prefer_axis_aligned=True,require_full_ground_reference=True,preserve_requested_geometry=True)
                seats.extend(tuple(p) for p in found['sites_nm'] if tuple(p)!=tuple(start))
                seats=list(dict.fromkeys(seats))
                for seat in seats:
                    if time.monotonic()>=local_deadline:break
                    trial['sites_tested']+=1;at=pcbnew.VECTOR2I(*seat)
                    if (not fr._edge_leg_clear(board,at,at,dia/2+gap)
                            or not cells._hole_to_hole_clear(board,at,drill/1e6)[0]
                            or not fr._via_spot_clear(board,at,dia,gap,{code},drill_nm=drill,net_code=code,report={})):
                        continue
                    # A real source-local bounded canonical path. A fine land
                    # can retain its bounded endpoint width only when the
                    # actual terminal via supplies a full-width throat.
                    legs=[]
                    wholly_contained=contained.contains(pad,at,dia)
                    if tuple(start)!=seat and not wholly_contained:
                        legs=fr._guarded_profiled_lastmile_legs(board,start,at,width,face,gap,code,
                            lambda s,t,h:fr._edge_leg_clear(board,s,t,h+gap),start_escape=escape,
                            allow_maze=True,refine_maze=True,compact_phase_jogs=True,
                            deadline_monotonic=min(local_deadline,time.monotonic()+.25),max_length_nm=1500000,
                            path_validator=lambda legs:join._endpoint_preview(board,legs,face,width,
                                terminal_barrel=(seat,dia,drill)))
                        if not join._valid_legs(board,legs,face,gap,code):continue
                    ops=[];covered=[]
                    for s,t,w in legs:
                        probe=pcbnew.PCB_TRACK(board);probe.SetNetCode(code);probe.SetLayer(face)
                        probe.SetStart(s);probe.SetEnd(t);probe.SetWidth(w)
                        witness=portal._covered_by_source(probe,board.GetTracks())
                        if witness:covered.append(dict(source_capsule_uuid=witness,start_nm=list(s),end_nm=list(t),width_nm=w))
                        else:ops.append(('trk',tuple(s),tuple(t),w,face))
                    ops.append(('via',seat,drill/1e6,dia/1e6))
                    made=[]
                    try:
                        made=mesh._make(board,ops);via=next(t for t in made if t.GetClass()=='PCB_VIA')
                        proof=_receive_barrel_source_context(board,via,pad,dia,drill,gap,deadline)
                        if not join._physical_root_reached(board,pad,context,deadline):continue
                        result.update(complete=True,ops=ops,pad_uuid=force._uid(pad),source_local_barrel=proof,
                            source_capsule_covered_leads_suppressed=covered,
                            strict_native_contained_via_without_redundant_lead=wholly_contained)
                        return result
                    except ValueError as exc:trial['last_refusal']=str(exc)
                    finally:discard_items(board,made)
    except ValueError as exc:result['error']=str(exc)
    finally:
        if row._source_binding(board)!=binding:raise ValueError('local_ground_mesh_plan_changed_source')
    return result


def _receive_barrel_source_context(board,via,pad,dia,drill,gap,deadline):
    actual=cells._existing_return(board,pad,1.5,allow_native_track_body=True)
    if actual is None or force._uid(actual[1])!=force._uid(via):
        raise ValueError('actual_bounded_source_pad_ground_path_required')
    contacts=ground._reference_contacts(board,via)
    mesh._reference_envelopes(board,via,contacts,deadline)
    return dict(diameter_nm=dia,drill_nm=drill,full_native_reference_envelopes=True,
        current_capacity_qualified=False,release_authority=False)


def construct_private(board,proposal,*,board_hint):
    if (proposal.get('scope')!='source_typed_local_ground_mesh_entry' or not proposal.get('complete')
            or proposal.get('board_hint')!=board_hint or row._source_binding(board)!=proposal['source_native_binding']):
        raise ValueError('complete_exact_source_local_ground_entry_required')
    context=join._context(board,board_hint,time.monotonic()+10.);pad=_owner(context,proposal['pad_uuid'])
    _source_geometry(board,pad);made=[]
    parent=pcbnew.LoadBoard(board.GetFileName())
    groups={force._uid(g):{force._uid(i) for i in g.GetItems()} for g in board.Groups()}
    try:
        made=mesh._make(board,proposal['ops']);vias=[t for t in made if t.GetClass()=='PCB_VIA']
        if len(vias)!=1:raise ValueError('one_source_local_ground_axis_required')
        _receive_barrel(parent,board,vias[0],proposal['pad_uuid'],board_hint,time.monotonic()+10.)
        endpoints.group(board,made,board_hint=board_hint)
        return made
    except Exception:
        for group in list(board.Groups()):
            kept=groups.get(force._uid(group),set())
            for item in list(group.GetItems()):
                if force._uid(item) not in kept:group.RemoveItem(item)
            if force._uid(group) not in groups:discard_items(board,[group])
        discard_items(board,made);raise


def receive(source,candidate,*,board_hint,timeout_s=10.):
    deadline=join._deadline(timeout_s)
    parent,child=[pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
    before={force._uid(t) for t in parent.GetTracks()}
    vias=[t for t in child.GetTracks() if force._uid(t) not in before and t.GetClass()=='PCB_VIA']
    result=dict(ok=False,complete=False,errors=[],release_authority=False)
    if len(vias)!=1:result['errors'].append('one_new_local_ground_axis_required');return result
    try:context=join._context(parent,board_hint,deadline)
    except ValueError as exc:result['errors'].append(str(exc));return result
    candidates=[force._uid(i) for q in context['islands'] for k in q
        if (i:=context['live'][k]).GetClass()=='PAD'
        and ('ground:'+force._uid(i)) in context['requests']
        and math.dist(tuple(i.GetPosition()),tuple(vias[0].GetPosition()))<=1500000]
    for uid in sorted(set(candidates))[:16]:
        remaining=deadline-time.monotonic()
        if remaining<=0:result['errors'].append('local_ground_mesh_saved_receiver_deadline');break
        result=join._receive(source,candidate,board_hint=board_hint,timeout_s=min(10.,remaining),local_pad_uuid=uid)
        if result['ok'] and result['complete']:return result
    return result
