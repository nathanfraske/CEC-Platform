"""Ordinary plated reference entry for an isolated typed low-power GND island.

Unlike a local decoupler return or a power barrel, this explicitly joins an
existing island to saved Ground reference copper. No part/source conductor
moves, no tiny-process/current exception is granted, and a remote mesh entry
is never represented as an immediate capacitor/owner return certificate.
"""
import math
import time

import pcbnew
import cec_cell_row_rebuild as row
import cec_cell_endpoint_groups as endpoints
import cec_decoupler_cell as cells
import cec_fab_profile as fab
import cec_force_current as force
import cec_fr as fr
import cec_ground_component_join as join
import cec_ground_return_shortcut as ground
import cec_native_via_frontier as frontier
import cec_kelvin_copper_cut as cut
from cec_native_items import discard_items


def _geometry(board):
    spec=cells._netclass(board,'GND')
    dia,drill,_=fab.board_legal_through_via_geometry(board,
        max(.6,spec['via_dia']),max(.3,spec['via_drill']))
    return round(dia*1e6),round(drill*1e6)


def _receive_barrel(parent,child,via,deadline):
    """Actual source ordinary geometry and complete live all-layer guards."""
    join._tick(deadline);expected=_geometry(parent)
    if (via.GetClass()!='PCB_VIA' or via.GetNetname()!='GND'
            or via.GetViaType()!=pcbnew.VIATYPE_THROUGH
            or via.TopLayer()!=pcbnew.F_Cu or via.BottomLayer()!=pcbnew.B_Cu
            or (via.GetWidth(via.TopLayer()),via.GetDrillValue())!=expected
            or any(via.GetWidth(l)!=expected[0] for l in via.GetLayerSet().CuStack())):
        raise ValueError('source_ordinary_ground_barrel_dimensions_required')
    spec=cells._netclass(child,'GND');gap=max(200000,int(child.GetDesignSettings().m_MinClearance),int(spec['clearance']))
    uid=force._uid(via);pos=via.GetPosition()
    if (not fr._edge_leg_clear(child,pos,pos,expected[0]/2+gap)
            or not cells._hole_to_hole_clear(child,pos,expected[1]/1e6,ignore_via_uuids=(uid,))[0]
            or not fr._via_spot_clear(child,pos,expected[0],gap,{via.GetNetCode()},drill_nm=expected[1],
                net_code=via.GetNetCode(),existing_via_uuid=uid,report={})):
        raise ValueError('ordinary_ground_mesh_barrel_physical_clearance_refused')
    blocked,reason=fab.via_at_pad_conflicts(child,pos,expected[0],expected[1],via.GetNetCode())
    if blocked is not None:raise ValueError('ordinary_ground_mesh_barrel_pad_contact_refused:'+str(reason))
    contacts=ground._reference_contacts(child,via)
    _reference_envelopes(child,via,contacts,deadline)
    return dict(via_uuid=uid,diameter_nm=expected[0],drill_nm=expected[1],
        actual_saved_reference_contacts=contacts,full_native_reference_envelopes=True,
        source_ordinary_geometry_only=True,current_capacity_qualified=False,
        immediate_return_qualified=False,release_authority=False)


def _reference_envelopes(child,via,contacts,deadline):
    """Exact full annular cover for every declared reference, not centre hits."""
    # Require the full native annular envelope on every declared Ground
    # face, not merely a point/crescent. Do not demand copper in the bore.
    # Subtract only an INSIDE native bore bound from the OUTSIDE copper
    # bound, so approximation cannot hide a genuine missing annular region.
    for face in {l for _,l in contacts}:
        join._tick(deadline)
        metal=pcbnew.SHAPE_POLY_SET()
        for zone in child.Zones():
            if (not zone.GetIsRuleArea() and zone.GetNetname()=='GND' and zone.IsFilled()
                    and zone.IsOnLayer(face) and zone.HasFilledPolysForLayer(face)):
                metal.BooleanAdd(zone.GetFilledPolysList(face))
        outer=pcbnew.SHAPE_POLY_SET();via.TransformShapeToPolygon(outer,face,0,1,pcbnew.ERROR_OUTSIDE)
        bore=pcbnew.PCB_VIA(child);bore.SetPosition(via.GetPosition());bore.SetWidth(via.GetDrillValue());bore.SetDrill(0)
        bore.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        hole=pcbnew.SHAPE_POLY_SET();bore.TransformShapeToPolygon(hole,face,0,1,pcbnew.ERROR_INSIDE)
        outer.BooleanSubtract(hole)
        outer.BooleanSubtract(metal)
        if outer.OutlineCount():raise ValueError('ordinary_ground_mesh_full_reference_envelope_missing')


def _make(board,ops):
    import cec_cell_escape_replan as escape
    return escape._native_ops(board,ops,'GND')


def _island_deadline(deadline,remaining):
    """Fair remaining wall lease, not a geometry or impossibility decision."""
    if type(remaining)is not int or remaining<1:
        raise ValueError('positive_remaining_ground_island_count_required')
    now=time.monotonic()
    return min(deadline,now+max(0.,deadline-now)/remaining)


def _search_summary(diagnostics):
    """Bounded actual search evidence, never an exhaustive no-path claim."""
    observed=diagnostics.get('observed_segment_refusals',{})
    result=dict(scope='observed_bounded_source_ground_search',no_path_proof=False,
        refusal_counts=dict(observed.get('events',{})),
        refusal_samples=observed.get('samples',[])[:3],maze_tiers=[])
    for tier in diagnostics.get('maze_tiers',[])[:3]:
        row={k:tier[k]for k in('grid_mm','phase','status','elapsed_s','path_found','path_accepted',
            'same_outer_deadline','tier_lease_s')if k in tier}
        detail=tier.get('native_endpoint_check',tier.get('diagnostics',{}))
        for key in('expanded_states','exhausted','deadline_exceeded','nearest_expanded_point',
                'lattice_constructed','stop','search_counts','native_endpoint_caps','lattice_axis_counts'):
            if key in detail:row[key]=detail[key]
        result['maze_tiers'].append(row)
    return result


def plan(board,*,board_hint,timeout_s=10.,radius_mm=8.,max_sites=12,obstacle_aware=False,pad_uuid=None,
         focus_site_index=None):
    """Optionally fund one freshly derived site, inside the SAME outer lease.

    The index selects proposals, not geometry or permission. It requires one
    actual typed Source land and obstacle mode; no caller coordinate, width,
    via dimension, current role, alternate terminal or relaxed guard enters.
    Fresh saved receiving is still independent of this planning choice.
    """
    deadline=join._deadline(timeout_s);binding=row._source_binding(board)
    if (type(radius_mm) not in (int,float) or not math.isfinite(radius_mm) or not 0<radius_mm<=8.
            or type(max_sites) is not int or not 1<=max_sites<=12
            or type(obstacle_aware) is not bool
            or focus_site_index is not None and(type(focus_site_index)is not int
                or not 0<=focus_site_index<max_sites or not obstacle_aware
                or type(pad_uuid)is not str or not pad_uuid)):
        raise ValueError('bounded_ground_mesh_portfolio_required')
    result=dict(scope='source_typed_ordinary_ground_mesh_entry',complete=False,ops=[],
        board_hint=board_hint,source_native_binding=binding,radius_mm=radius_mm,max_sites=max_sites,
        routing_admitted=False,release_authority=False,current_qualified=False,
        immediate_return_qualified=False)
    result['obstacle_aware']=obstacle_aware
    if focus_site_index is not None:result['focus_site_index']=focus_site_index
    try:
        context=join._target_context(join._context(board,board_hint,deadline),pad_uuid);live=context['live']
        if pad_uuid is not None:result['target_pad_uuid']=pad_uuid
        result.update(source_ground_components=len(context['ground']),eligible_low_power_islands=len(context['islands']))
        spec=cells._netclass(board,'GND');width=max(200000,int(board.GetDesignSettings().m_TrackMinWidth),int(spec['width']))
        gap=max(200000,int(board.GetDesignSettings().m_MinClearance),int(spec['clearance']))
        dia,drill=_geometry(board);code=board.GetNetcodeFromNetname('GND')
        typed={r['a']['pad_uuid'] for r in context['requests'].values()};result['trials']=[]
        result['island_leases']=[]
        for island_index,island in enumerate(context['islands']):
            if obstacle_aware and time.monotonic()>=deadline:break
            begun=time.monotonic()
            local_deadline=(_island_deadline(deadline,len(context['islands'])-island_index)
                if obstacle_aware else deadline)
            lease=dict(island_index=island_index,budget_s=max(0.,local_deadline-begun),
                source_ports_attempted=0,sites_tested=0,complete=False)
            result['island_leases'].append(lease)
            starts=[];seen=set()
            for key in sorted(island,key=lambda k:(live[k].GetClass()!='PAD',k)):
                item=live[key]
                if focus_site_index is not None and force._uid(item)!=pad_uuid:continue
                if item.GetClass()=='PAD' and force._uid(item) not in typed:continue
                for at,faces,pad in join._ports(item):
                    for face in sorted(set(faces)&{int(pcbnew.F_Cu),int(pcbnew.B_Cu)}):
                        if (at,face) in seen:continue
                        seen.add((at,face));starts.append((key,at,face,pad))
            for key,at,face,pad in starts[:4]:
                if obstacle_aware and time.monotonic()>=local_deadline:break
                join._tick(deadline)
                lease['source_ports_attempted']+=1
                found=frontier.sites(board,code,at,clearance_nm=gap,radius_mm=radius_mm,
                    max_sites=max_sites,deadline=local_deadline,diverse=True,diameter_mm=dia/1e6,drill_mm=drill/1e6,
                    require_full_ground_reference=True)
                sites=found['sites_nm']
                trial=dict(source_port=list(key),source_port_nm=list(at),surface_layer=int(face),
                    sites=len(sites),proposed_sites_nm=[list(p)for p in sites],tested=0,seat_attempts=[])
                result['trials'].append(trial)
                if focus_site_index is not None:
                    if focus_site_index>=len(sites):
                        trial['reason']='focused_fresh_source_site_unavailable';continue
                    sites=[sites[focus_site_index]]
                escape=fr._pad_local_escape(pad,width,gap,max(200000,int(board.GetDesignSettings().m_TrackMinWidth))) if pad is not None else None
                for seat in sites:
                    if obstacle_aware and time.monotonic()>=local_deadline:break
                    join._tick(deadline);trial['tested']+=1
                    lease['sites_tested']+=1
                    seat_started=time.monotonic()
                    attempt=dict(at_nm=list(seat),canonical_found=False,maze_attempted=False,
                        focused=focus_site_index is not None,no_path_proof=False)
                    trial['seat_attempts'].append(attempt)
                    legs=fr._guarded_profiled_lastmile_legs(board,pcbnew.VECTOR2I(*at),pcbnew.VECTOR2I(*seat),
                        width,face,gap,code,lambda s,t,h:fr._edge_leg_clear(board,s,t,h+gap),
                        start_escape=escape,allow_maze=False,canonical_only=True,
                        deadline_monotonic=local_deadline,max_length_nm=12000000,
                        path_validator=lambda legs:join._endpoint_preview(board,legs,face,width,
                            terminal_barrel=(tuple(seat),dia,drill)))
                    attempt['canonical_found']=bool(legs)
                    if not legs and obstacle_aware and local_deadline-time.monotonic()>.05:
                        # A clear barrel is not necessarily reachable by one
                        # L or diagonal. Fund the real local obstacle path,
                        # not another unchanged nearest-seat retry. The same
                        # source/class/physical/endpoint predicates receive
                        # the whole path; this is never a via/width waiver.
                        trial['obstacle_path_attempts']=trial.get('obstacle_path_attempts',0)+1
                        diagnostics={};attempt['maze_attempted']=True
                        search_deadline=(local_deadline if focus_site_index is not None else
                            min(local_deadline,time.monotonic()+.5))
                        attempt['search_budget_s']=max(0.,search_deadline-time.monotonic())
                        legs=fr._guarded_profiled_lastmile_legs(board,pcbnew.VECTOR2I(*at),pcbnew.VECTOR2I(*seat),
                            width,face,gap,code,lambda s,t,h:fr._edge_leg_clear(board,s,t,h+gap),
                            start_escape=escape,allow_maze=True,refine_maze=True,compact_phase_jogs=True,
                            deadline_monotonic=search_deadline,max_length_nm=12000000,
                            search_diagnostics=diagnostics,
                            path_validator=lambda legs:join._endpoint_preview(board,legs,face,width,
                                terminal_barrel=(tuple(seat),dia,drill)))
                        attempt['search']=_search_summary(diagnostics)
                    attempt.update(path_found=bool(legs),elapsed_s=time.monotonic()-seat_started,
                        lease_exhausted=time.monotonic()>=local_deadline)
                    if not join._valid_legs(board,legs,face,gap,code):
                        attempt['reason']='no_complete_source_guarded_ground_legs';continue
                    ops=[('trk',tuple(s),tuple(t),int(w),face) for s,t,w in legs]
                    ops.append(('via',tuple(seat),drill/1e6,dia/1e6))
                    made=[]
                    try:
                        made=_make(board,ops);via=next(t for t in made if t.GetClass()=='PCB_VIA')
                        proof=_receive_barrel(board,board,via,deadline)
                        if not join._physical_root_reached(board,live[key],context,deadline):
                            attempt['reason']='actual_source_reference_component_not_reached';continue
                        lease.update(complete=True,elapsed_s=time.monotonic()-begun)
                        result.update(complete=True,ops=ops,source_port=list(key),
                            ordinary_barrel_proposal=proof,length_mm=sum(math.dist(tuple(s),tuple(t)) for s,t,w in legs)/1e6)
                        return result
                    except ValueError as exc:
                        trial['last_refusal']=str(exc);attempt['reason']=str(exc)
                    finally:discard_items(board,made)
            lease.update(elapsed_s=time.monotonic()-begun,
                lease_exhausted=time.monotonic()>=local_deadline,no_path_proof=False)
    except (ValueError,cut.Unknown) as exc:
        result['error']=str(exc)
        result['source_geometry_unknown']=isinstance(exc,cut.Unknown)
        result['no_path_proof']=False
    finally:
        if row._source_binding(board)!=binding:raise ValueError('ground_mesh_plan_changed_source')
    return result


def construct_private(board,proposal,*,board_hint):
    if (proposal.get('scope')!='source_typed_ordinary_ground_mesh_entry' or proposal.get('complete') is not True
            or proposal.get('board_hint')!=board_hint or row._source_binding(board)!=proposal.get('source_native_binding')
            or not 2<=len(proposal.get('ops',[]))<=128
            or sum(op[0]=='via' for op in proposal['ops'])!=1):
        raise ValueError('exact_complete_source_ground_mesh_proposal_required')
    old={force._uid(t) for t in board.GetTracks()};groups={force._uid(g):{force._uid(i) for i in g.GetItems()} for g in board.Groups()}
    try:
        made=_make(board,proposal['ops']);barrel=next(t for t in made if t.GetClass()=='PCB_VIA')
        _receive_barrel(board,board,barrel,time.monotonic()+10.)
        spec=cells._netclass(board,'GND');gap=max(200000,int(board.GetDesignSettings().m_MinClearance),int(spec['clearance']))
        if any(t.GetClass() not in ('PCB_TRACK','PCB_VIA') or t.GetClass()=='PCB_TRACK' and not join._valid_legs(board,
                [(t.GetStart(),t.GetEnd(),t.GetWidth())],int(t.GetLayer()),gap,t.GetNetCode()) for t in made):
            raise ValueError('ground_mesh_new_track_physical_geometry_refused')
        endpoints.group(board,made,board_hint=board_hint)
        return made
    except Exception:
        for group in list(board.Groups()):
            kept=groups.get(force._uid(group),set())
            for item in list(group.GetItems()):
                if force._uid(item) not in kept:group.RemoveItem(item)
            if force._uid(group) not in groups:discard_items(board,[group])
        discard_items(board,[t for t in board.GetTracks() if force._uid(t) not in old])
        raise


def receive(source,candidate,*,board_hint,timeout_s=10.):
    """One source-ordinary Ground hole; every saved join gate remains required."""
    return join._receive(source,candidate,board_hint=board_hint,timeout_s=timeout_s,ordinary_mesh_entry=True)
