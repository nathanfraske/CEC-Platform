"""Add a bounded low-power Ground island to its actual saved reference mesh.

This is distinct from return-shortening cleanup: joining source components
is the explicit objective here. No source copper, part, pose, hole or power
zone is removed or moved. Native connectivity alone is not local-return,
aggregate current, thermal, Kelvin or fabrication qualification.
"""
import math
import time
from pathlib import Path

import pcbnew
import cec_additive_route_receiving as additive
import cec_cell_endpoint_groups as endpoints
import cec_cell_row_rebuild as row
import cec_constraints as constraints
import cec_decoupler_cell as cells
import cec_device_power_roles as roles
import cec_force_current as force
import cec_fr as fr
import cec_ground_return_preservation as preservation
import cec_ground_return_shortcut as shortcut
import cec_ordinary_route_receiving as ordinary
import cec_native_partition_pair as partitions
import cec_route_quality as quality
from cec_native_items import discard_items


def _deadline(timeout_s):
    if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
            or not 0<timeout_s<=10.):
        raise ValueError('bounded_ground_join_deadline_required')
    return time.monotonic()+timeout_s


def _tick(deadline):
    if time.monotonic()>=deadline:raise ValueError('ground_component_join_deadline')


def _typed_requests(board,hint,*,deadline=None,with_source_export=False):
    """Positive manufacturer roles and actual selected ceramic returns only."""
    if type(hint) is not str or not hint:raise ValueError('ground_join_source_context_required')
    eligible={};selected=set()
    with force._thermal_hint(hint):
        assignments=constraints._device_bypass_assignment(board,project_max_mm=3.5)
    for fp in board.GetFootprints():
        if fp.IsDNP():continue
        model=roles.footprint_contract(fp)
        if (not model or set(model['pins'].values())&{'power_output','switch','feedback'}):continue
        for pad in fp.Pads():
            if (pad.GetNetname()=='GND' and not pad.HasHole()
                    and pad.GetAttribute()==pcbnew.PAD_ATTRIB_SMD
                    and model['pins'].get(str(pad.GetNumber())) in
                        ('ground','power_return','reference','address')):
                eligible[force._uid(pad)]=pad
        selected.update(r['cap_ref'] for r in assignments['assigned'].values()
            if r['requirement']['ref']==fp.GetReference()
            and model['pins'].get(str(r['requirement']['pin']))=='power_input')
    import cec_device_bypass as bypass
    for ref in sorted(selected):
        cap=board.FindFootprintByReference(ref)
        if cap is None or cap.IsDNP():continue
        pads=list(cap.Pads())
        if (len(pads)!=2 or any(p.HasHole() or p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD for p in pads)
                or not bypass.capacitor_identity(cap.GetReference(),cap.GetFPIDAsString())
                or not bypass.local_bypass_technology(cap.GetValue(),cap.GetFPIDAsString())):continue
        ground=[p for p in pads if p.GetNetname()=='GND']
        if len(ground)==1:eligible[force._uid(ground[0])]=ground[0]
    import cec_source_ground_leaf as leaf
    remaining=10. if deadline is None else min(10.,deadline-time.monotonic())
    snapshot=None
    if with_source_export and remaining>0:
        leaves,snapshot=leaf.plan_with_export(board,board_hint=hint,timeout_s=remaining)
    else:
        leaves=leaf.plan(board,board_hint=hint,timeout_s=remaining) if remaining>0 else {'proofs':{},'complete':False}
    proofs=leaves['proofs'] if leaves['complete'] else {}
    pads={force._uid(p):p for f in board.GetFootprints() for p in f.Pads()}
    eligible.update({u:pads[u] for u in proofs})
    requests={'ground:'+u:dict(kind='ground',net='GND',a={'pad_uuid':u},
        **({'source_external_ground_leaf':proofs[u]} if u in proofs else {})) for u in sorted(eligible)}
    return (requests,leaves,snapshot) if with_source_export else requests


def _context(board,hint,deadline,*,coowned_input_control=False):
    physical=partitions._inventory(board,deadline,dict(items=16384,polygons=4096,vertices=200000))
    material=physical['objects']
    live={force._item_key(i):i for i in material}
    if len(live)!=len(material):raise ValueError('ground_join_unique_native_identity_required')
    parts=physical['components']
    ground=[p for p in parts if all(live[k].GetNetname()=='GND' for k in p)]
    if any(any(live[k].GetNetname()=='GND' for k in p) and p not in ground for p in parts):
        raise ValueError('ground_join_source_native_short')
    faces={board.GetLayerID(n) for n in fr.plane_layers(board)}
    roots=[]
    for part in ground:
        covered={int(live[k].GetLayer())for k in part if live[k].GetClass()=='ZONE'}&faces
        if not faces or covered!=faces:continue
        for k in sorted(part):
            _tick(deadline);item=live[k]
            if item.GetClass()!='PCB_VIA':continue
            try:
                contacts=shortcut._reference_contacts(board,item)
                import cec_ground_mesh_entry as mesh
                mesh._reference_envelopes(board,item,contacts,deadline)
            except ValueError:continue
            roots.append((part,[force._uid(item)]));break
    if len(roots)!=1:raise ValueError('unique_saved_all_reference_ground_component_required')
    root,barrels=roots[0]
    if coowned_input_control:
        requests,source,snapshot=_typed_requests(board,hint,deadline=deadline,with_source_export=True)
        import cec_source_capacitor_control_ground as coowned
        cohorts=coowned.derive(board,hint,source,snapshot,ground,live,root,deadline)
        for cohort in cohorts:
            for proof in cohort['proof']['input_capacitor_ground_proofs']:
                uid=proof['pad_uuid']
                requests['ground:'+uid]=dict(kind='ground',net='GND',a={'pad_uuid':uid},
                    source_coowned_input_capacitor_ground=proof)
    else:
        requests=_typed_requests(board,hint,deadline=deadline);cohorts=[]
    allowed={r['a']['pad_uuid'] for r in requests.values()}
    optional={}
    for item in live.values():
        _tick(deadline)
        if item.GetClass()!='PAD' or item.GetNetname()!='GND':continue
        proof=roles.optional_ground_attachment_contract(item.GetParentFootprint(),item.GetNumber())
        if proof is not None and force._uid(item) not in allowed:optional[force._uid(item)]=proof
    def low_power(part):
        pads=[live[k] for k in part if live[k].GetClass()=='PAD']
        if not (len(part)<=32 and all(live[k].GetClass() in ('PAD','PCB_TRACK','PCB_VIA') for k in part)
                and all(force._uid(p) in allowed or force._uid(p) in optional for p in pads)):
            return False
        for pad in pads:
            if force._uid(pad) not in optional:continue
            owner=pad.GetParentFootprint();model=roles.footprint_contract(owner)
            # The reserved land must ALREADY be joined by literal source
            # copper to this same package's actual Ground terminal. It does
            # not become a new required endpoint or an internal return path.
            if not any(force._uid(peer) in allowed and peer.GetParentFootprint()==owner
                    and model['pins'].get(peer.GetNumber())=='ground' for peer in pads):
                return False
        return True
    return dict(live=live,parts=parts,ground=ground,root=root,
        islands=([c['component']for c in cohorts]if coowned_input_control else
            [p for p in ground if p!=root and low_power(p)]),requests=requests,
        reference_barrel_uuids=barrels,optional_attached_ground_lands=optional,
        coowned_input_control_cohorts=[c['proof']for c in cohorts])


def _target_context(context,pad_uuid):
    """Narrow planning, never the source partition or request authority."""
    if pad_uuid is None:return context
    if type(pad_uuid) is not str or not pad_uuid:
        raise ValueError('explicit_source_ground_pad_uuid_required')
    pads=[v for v in context['live'].values()
        if v.GetClass()=='PAD' and force._uid(v)==pad_uuid]
    allowed={r['a']['pad_uuid'] for r in context['requests'].values()}
    islands=[p for p in context['islands'] if any(
        context['live'][k].GetClass()=='PAD' and force._uid(context['live'][k])==pad_uuid for k in p)]
    if (len(pads)!=1 or pad_uuid not in allowed or len(islands)!=1
            or pads[0].GetNetname()!='GND'
            or pads[0].GetParentFootprint().IsDNP()):
        raise ValueError('fresh_typed_detached_source_ground_land_required')
    return dict(context,islands=islands,target_pad_uuid=pad_uuid)


def receive_target(source,candidate,*,board_hint,pad_uuid,timeout_s=10.):
    """Additional target-progress proof; never replaces the whole saved receiver."""
    deadline=_deadline(timeout_s)
    try:
        parent=pcbnew.LoadBoard(str(source));child=pcbnew.LoadBoard(str(candidate))
        context=_target_context(_context(parent,board_hint,deadline),pad_uuid)
        transition,root=_paired_root(parent,child,context,deadline)
        if not context['islands'][0]<=root:
            raise ValueError('requested_source_ground_component_not_rooted')
        return dict(ok=True,complete=True,target_pad_uuid=pad_uuid,
            all_source_partitions_preserved=True,whole_saved_receiver_still_required=True)
    except Exception as exc:
        return dict(ok=False,complete=False,error=str(exc))


def _paired_root(parent,child,context,deadline):
    _tick(deadline)
    transition=partitions.compare(parent,child,timeout_s=min(10.,deadline-time.monotonic()))
    if not transition['preserved']:raise ValueError('ground_join_source_native_partition_demoted')
    uid=context['reference_barrel_uuids'][0]
    key=next(k for k in context['root']if force._uid(context['live'][k])==uid)
    roots=[p for p in transition['child_parts']if key in p]
    source_roots=[p for p in transition['source_parts']if key in p]
    if len(roots)!=1 or len(source_roots)!=1 or not source_roots[0]<=roots[0]:
        raise ValueError('ground_join_original_reference_mesh_lost')
    return transition,roots[0]


def _physical_root_reached(board,item,context,deadline):
    """Plan-local exact proxy regraph after a reversible construction trial."""
    physical=partitions._inventory(board,deadline,dict(items=16384,polygons=4096,vertices=200000))
    key=force._item_key(item)
    if key not in physical['component_of']:return False
    return context['root']<=physical['components'][physical['component_of'][key]]


def _ports(item,toward=None):
    if item.GetClass()=='PCB_TRACK':
        points=[tuple(item.GetStart()),tuple(item.GetEnd())]
        if toward is not None:
            points=shortcut._native_track_entry_points(item,toward)
        return [(p,[int(item.GetLayer())],None) for p in points]
    if item.GetClass() in ('PAD','PCB_VIA'):
        return [(tuple(item.GetPosition()),list(map(int,item.GetLayerSet().CuStack())),
            item if item.GetClass()=='PAD' else None)]
    return []


def _valid_legs(board,legs,face,gap,net_code):
    cache={};minimum=max(200000,int(board.GetDesignSettings().m_TrackMinWidth))
    return bool(legs and all(w>=minimum and s!=t
        and quality.is_canonical_stroke(tuple(s),tuple(t),tolerance_nm=0)
        and fr._edge_leg_clear(board,s,t,w/2+gap)
        and fr._tap_foreign_clear(board,s,t,w,face,gap,{net_code},foreign_cache=cache)
        for s,t,w in legs))


def _endpoint_preview(board,legs,face,width,*,terminal_barrel=None):
    """Qualify a complete proposed narrow component before choosing it.

    Search may otherwise stop on its first geometrically clear path whose
    two endpoint allowances consume the whole body. A mesh caller may preview
    its exact proposed terminal barrel as the real full-width throat. The
    independent saved mesh receiver still owns dimensions, all-layer/hole
    clearance, reference envelopes and necessity. No trial item survives.
    """
    made=[]
    try:
        if terminal_barrel is not None:
            if (type(terminal_barrel) not in (list,tuple) or len(terminal_barrel)!=3
                    or not legs):raise ValueError('exact_terminal_ground_barrel_preview_required')
            at,dia,drill=terminal_barrel
            if (type(at) not in (list,tuple) or len(at)!=2
                    or any(type(v) is not int for v in at)
                    or type(dia) is not int or type(drill) is not int
                    or not 0<drill<dia or dia<width
                    or tuple(legs[-1][1])!=tuple(at)):
                raise ValueError('full_width_actual_terminal_ground_barrel_required')
            via=pcbnew.PCB_VIA(board);via.SetPosition(pcbnew.VECTOR2I(*at))
            via.SetWidth(dia);via.SetDrill(drill);via.SetNetCode(board.GetNetcodeFromNetname('GND'))
            via.SetViaType(pcbnew.VIATYPE_THROUGH);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
            board.Add(via);made.append(via)
        for s,t,w in legs:
            item=pcbnew.PCB_TRACK(board);item.SetNetCode(board.GetNetcodeFromNetname('GND'))
            item.SetLayer(face);item.SetWidth(w);item.SetStart(s);item.SetEnd(t);board.Add(item);made.append(item)
        tracks=[t for t in made if t.GetClass()=='PCB_TRACK']
        qualified,rejected=fr._qualified_endpoint_neckdown_tracks(board,tracks,width,
            required_clearance=max(200000,int(board.GetDesignSettings().m_MinClearance),
                int(cells._netclass(board,'GND')['clearance'])))
        return not rejected and {force._uid(t) for t in qualified}=={
            force._uid(t) for t in tracks if t.GetWidth()<width}
    finally:
        discard_items(board,made)


def _plan(board,*,board_hint,timeout_s=10.,max_pairs=24,max_length_mm=12.,pad_uuid=None,
          coowned_input_control=False):
    deadline=_deadline(timeout_s);binding=row._source_binding(board)
    if (type(max_pairs) is not int or not 1<=max_pairs<=64
            or type(max_length_mm) not in (int,float) or not math.isfinite(max_length_mm)
            or not 0<max_length_mm<=12.):raise ValueError('bounded_ground_join_portfolio_required')
    result=dict(scope=('source_typed_coowned_input_control_ground_join'if coowned_input_control else
        'source_typed_additive_ground_component_join'),complete=False,ops=[],
        source_native_binding=binding,board_hint=board_hint,max_length_mm=max_length_mm,
        max_pairs=max_pairs,routing_admitted=False,release_authority=False,new_holes=0)
    try:
        context=_target_context(_context(board,board_hint,deadline,
            coowned_input_control=coowned_input_control),pad_uuid);live=context['live']
        if coowned_input_control:result['coowned_input_control_cohorts']=context['coowned_input_control_cohorts']
        if pad_uuid is not None:result['target_pad_uuid']=pad_uuid
        result.update(source_ground_components=len(context['ground']),
            eligible_low_power_islands=len(context['islands']),
            reference_barrel_uuids=context['reference_barrel_uuids'])
        floor=max(200000,int(board.GetDesignSettings().m_TrackMinWidth),int(cells._netclass(board,'GND')['width']))
        gap=max(200000,int(board.GetDesignSettings().m_MinClearance),int(cells._netclass(board,'GND')['clearance']))
        outer={int(pcbnew.F_Cu),int(pcbnew.B_Cu)};cohorts=[];seen=set()
        typed={r['a']['pad_uuid'] for r in context['requests'].values()}
        for island in context['islands']:
            pairs=[]
            for key in sorted(island,key=lambda k:(live[k].GetClass()!='PAD',k)):
                _tick(deadline);start=live[key]
                if start.GetClass()=='PAD' and force._uid(start) in context['optional_attached_ground_lands']:continue
                for at,layers,pad in _ports(start):
                    targets=[]
                    for other in context['root']:
                        _tick(deadline)
                        target=live[other]
                        if target.GetClass()=='PAD' and force._uid(target) in context['optional_attached_ground_lands']:continue
                        for end,faces,last in _ports(target,at):
                            common=sorted(set(layers)&set(faces)&outer)
                            distance=math.dist(at,end)
                            if common and 0<distance<=max_length_mm*1e6:
                                targets.append((distance,other,end,common,last))
                        # Only a bounded nearest attachment portfolio is
                        # retained, rather than the whole large-board mesh.
                        if len(targets)>32:
                            targets=sorted(targets,key=lambda q:(q[0],q[1],q[2]))[:8]
                    for distance,other,end,common,last in sorted(targets,key=lambda q:(q[0],q[1],q[2]))[:8]:
                        for face in common:
                            # A real fine land and an old track endpoint can
                            # occupy the same coordinate. They are not the
                            # same launch authority: retain the positive pad
                            # identity rather than losing its bounded escape
                            # to the lexicographically earlier copper alias.
                            signature=(at,end,face,
                                force._uid(pad) if pad is not None and force._uid(pad) in typed else None,
                                force._uid(last) if last is not None and force._uid(last) in typed else None)
                            if signature in seen:continue
                            seen.add(signature);pairs.append((distance,key,other,at,end,face,pad,last))
            if pairs:cohorts.append(sorted(pairs,key=lambda p:(p[0],p[6] is None,p[7] is None,
                p[1],p[2],p[3],p[4],p[5])))
        # Fund each actual detached component before one blocked package's
        # endpoint aliases consume the entire portfolio. This is scheduling,
        # not a declaration that any untried component has no legal path.
        cohorts.sort(key=lambda rows:rows[0][0]);pairs=[]
        for index in range(max((len(c) for c in cohorts),default=0)):
            for cohort in cohorts:
                if index<len(cohort):pairs.append(cohort[index])
                if len(pairs)>=max_pairs:break
            if len(pairs)>=max_pairs:break
        result['actual_native_pairs']=len(pairs);result['trials']=[]
        for maze in (False,True):
            for index,(_,left,right,a,b,face,pad,last) in enumerate(pairs):
                _tick(deadline)
                escapes=[]
                for p in (pad,last):
                    escapes.append(fr._pad_local_escape(p,floor,gap,
                        max(200000,int(board.GetDesignSettings().m_TrackMinWidth)))
                        if p is not None and force._uid(p) in typed else None)
                lease=min(deadline,time.monotonic()+max(.02,(deadline-time.monotonic())/
                    max(1,(min(8,len(pairs))-index)))) if maze else deadline
                legs=fr._guarded_profiled_lastmile_legs(board,pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*b),
                    floor,face,gap,board.GetNetcodeFromNetname('GND'),
                    lambda s,t,h:fr._edge_leg_clear(board,s,t,h+gap),
                    start_escape=escapes[0],end_escape=escapes[1],allow_maze=maze,
                    canonical_only=not maze,deadline_monotonic=lease,max_length_nm=max_length_mm*1e6,
                    path_validator=lambda legs:_endpoint_preview(board,legs,face,floor))
                result['trials'].append(dict(left=list(left),right=list(right),maze=maze,found=bool(legs)))
                if not _valid_legs(board,legs,face,gap,board.GetNetcodeFromNetname('GND')):continue
                if not _endpoint_preview(board,legs,face,floor):continue
                result.update(complete=True,ops=[('trk',tuple(s),tuple(t),int(w),face) for s,t,w in legs],
                    source_ports=[list(left),list(right)],length_mm=sum(math.dist(tuple(s),tuple(t)) for s,t,w in legs)/1e6)
                return result
                # Neither a failed finite portfolio nor its deadline proves
                # there is no physical route. Other typed operators may act.
    except ValueError as exc:
        result['error']=str(exc)
    finally:
        if row._source_binding(board)!=binding:raise ValueError('ground_join_plan_changed_source')
    return result


def _construct_private(board,proposal,*,board_hint,coowned_input_control=False):
    expected=('source_typed_coowned_input_control_ground_join'if coowned_input_control else
        'source_typed_additive_ground_component_join')
    if (proposal.get('scope')!=expected
            or proposal.get('complete') is not True or proposal.get('board_hint')!=board_hint
            or row._source_binding(board)!=proposal.get('source_native_binding')
            or not 1<=len(proposal.get('ops',[]))<=128):
        raise ValueError('exact_complete_source_ground_join_proposal_required')
    before={force._uid(t) for t in board.GetTracks()};groups={force._uid(g):{force._uid(i) for i in g.GetItems()} for g in board.Groups()}
    made=[]
    try:
        spec=cells._netclass(board,'GND');gap=max(200000,int(board.GetDesignSettings().m_MinClearance),int(spec['clearance']))
        total=0
        for op in proposal['ops']:
            if (len(op)!=5 or op[0]!='trk' or op[4] not in (pcbnew.F_Cu,pcbnew.B_Cu)):
                raise ValueError('ground_join_surface_tracks_only')
            s,t=pcbnew.VECTOR2I(*op[1]),pcbnew.VECTOR2I(*op[2]);total+=math.dist(tuple(s),tuple(t))
            if not _valid_legs(board,[(s,t,op[3])],op[4],gap,board.GetNetcodeFromNetname('GND')):
                raise ValueError('ground_join_actual_track_geometry_refused')
            track=pcbnew.PCB_TRACK(board);track.SetNetCode(board.GetNetcodeFromNetname('GND'))
            track.SetLayer(op[4]);track.SetWidth(op[3]);track.SetStart(s);track.SetEnd(t);board.Add(track);made.append(track)
        if total>min(12.,proposal['max_length_mm'])*1e6:raise ValueError('ground_join_bounded_path_required')
        endpoints.group(board,made,board_hint=board_hint)
        return made
    except Exception:
        for group in list(board.Groups()):
            kept=groups.get(force._uid(group),set())
            for item in list(group.GetItems()):
                if force._uid(item) not in kept:group.RemoveItem(item)
            if force._uid(group) not in groups:discard_items(board,[group])
        discard_items(board,[t for t in board.GetTracks() if force._uid(t) not in before])
        raise


def _receive(source,candidate,*,board_hint,timeout_s=10.,ordinary_mesh_entry=False,local_pad_uuid=None,
             coowned_input_control_pad_uuid=None):
    result=dict(ok=False,complete=False,errors=[],current_qualified=False,release_authority=False,
        new_immediate_returns_qualified=False,reference_plane_integrity_qualified=False)
    try:
        deadline=_deadline(timeout_s);paths=[Path(p).resolve() for p in (source,candidate)]
        if paths[0]==paths[1]:raise ValueError('separate_saved_ground_join_candidate_required')
        epoch=force._code_identity();families=[force._family(p,board_hint) for p in paths]
        parent,child=[pcbnew.LoadBoard(str(p)) for p in paths]
        coowned=coowned_input_control_pad_uuid is not None
        if coowned and (ordinary_mesh_entry or local_pad_uuid is not None):
            raise ValueError('separate_coowned_ground_surface_join_scope_required')
        context=_context(parent,board_hint,deadline,coowned_input_control=coowned)
        if coowned:context=_target_context(context,coowned_input_control_pad_uuid)
        old={force._uid(t) for t in parent.GetTracks()}
        added=[t for t in child.GetTracks() if force._uid(t) not in old]
        if (type(ordinary_mesh_entry) is not bool
                or local_pad_uuid is not None and (ordinary_mesh_entry
                    or type(local_pad_uuid) is not str or not local_pad_uuid)):
            raise ValueError('typed_ground_join_receiver_required')
        allowed_classes={'PCB_TRACK','PCB_VIA'} if ordinary_mesh_entry or local_pad_uuid else {'PCB_TRACK'}
        if not 1<=len(added)<=128 or any(t.GetClass() not in allowed_classes or t.GetNetname()!='GND' for t in added):
            raise ValueError('bounded_new_ground_tracks_only')
        barrels=[t for t in added if t.GetClass()=='PCB_VIA']
        if ordinary_mesh_entry:
            if len(barrels)!=1:raise ValueError('one_new_ordinary_ground_mesh_axis_required')
            import cec_ground_mesh_entry as mesh
            result['ordinary_ground_mesh_barrel']=mesh._receive_barrel(parent,child,barrels[0],deadline)
        elif local_pad_uuid:
            if len(barrels)!=1:raise ValueError('one_source_local_ground_mesh_axis_required')
            import cec_ground_local_mesh_entry as local_mesh
            result['source_local_ground_barrel']=local_mesh._receive_barrel(
                parent,child,barrels[0],local_pad_uuid,board_hint,deadline)
        requests=context['requests']
        proof=endpoints.receive(parent,child,requests,added,board_hint=board_hint,deadline=deadline)
        narrow=set(proof['track_uuids']);width=max(200000,int(child.GetDesignSettings().m_TrackMinWidth),
            int(cells._netclass(child,'GND')['width']))
        gap=max(200000,int(child.GetDesignSettings().m_MinClearance),int(cells._netclass(child,'GND')['clearance']))
        if coowned and any(t.GetWidth()<width for t in added):
            raise ValueError('coowned_ground_join_full_source_class_required')
        if sum(t.GetLength() for t in added if t.GetClass()=='PCB_TRACK')>12000000:raise ValueError('ground_join_saved_path_too_long')
        for t in added:
            _tick(deadline)
            if t.GetClass()=='PCB_VIA':continue
            if (t.GetLayer() not in (pcbnew.F_Cu,pcbnew.B_Cu)
                    or t.GetWidth()<width and force._uid(t) not in narrow
                    or not _valid_legs(child,[(t.GetStart(),t.GetEnd(),t.GetWidth())],int(t.GetLayer()),gap,t.GetNetCode())):
                raise ValueError('ground_join_saved_geometry_or_width_refused')
        # Exact source replay independently retains power, poses, source
        # tracks, holes and settings. Only existing Ground fills and exact
        # qualified endpoint-group additions may change.
        delta=additive.receive(paths[0],paths[1],board_hint=board_hint,
            timeout_s=min(10.,max(.001,deadline-time.monotonic())),allow_endpoint_neckdown_additions=True)
        if not delta['ok'] or not delta['complete']:raise ValueError('ground_join_exact_source_replay_refused:'+str(delta['errors']))
        transition,merged=_paired_root(parent,child,context,deadline)
        final=transition['child_parts']
        joined=[p for p in context['islands']if p<=merged]
        if not joined or any(p not in context['islands'] for p in joined):
            raise ValueError('ground_join_requires_strict_typed_low_power_rooted_progress')
        expected=len(transition['source_parts'])-len(joined)
        if len(final)!=expected:raise ValueError('ground_join_unrelated_source_components_merged')
        if coowned:
            import cec_source_capacitor_control_ground as cohort_source
            if len(joined)!=1:raise ValueError('one_complete_coowned_ground_island_join_required')
            result['coowned_surface_chain']=cohort_source.receive_chain(
                added,joined[0],context['root'],context['live'],deadline)
        if barrels:
            # _partition's retired_uuids removes comparison vertices, NOT
            # native graph edges: ordinary rip-up receiving needs the old
            # paths to establish its source obligations. For this distinct
            # necessity counterfactual exclude the new axis from the graph
            # itself, without deleting it or changing that shared contract.
            excluded=force._uid(barrels[0])
            class WithoutNewAxis:
                def GetTracks(self):
                    return [t for t in child.GetTracks() if force._uid(t)!=excluded]
                def __getattr__(self,name):return getattr(child,name)
            _,root_without=_paired_root(parent,WithoutNewAxis(),context,deadline)
            if any(p<=root_without for p in joined):
                raise ValueError('new_ground_mesh_barrel_is_not_necessary_to_source_join')
        graph=fr._read_only_route_connectivity(child)
        native={force._item_key(i):i for i in [*(p for f in child.GetFootprints() for p in f.Pads()),
            *child.GetTracks(),*child.Zones()]}
        root=next(i for i in child.GetTracks()if force._uid(i)==context['reference_barrel_uuids'][0])
        reached={force._uid(i) for i in graph.GetConnectedItems(root)}|{force._uid(root)}
        if any(force._uid(t) not in reached for t in added):raise ValueError('ground_join_unrooted_new_conductor')
        local=preservation.receive(parent,child,timeout_s=min(10.,max(.001,deadline-time.monotonic())))
        if not local['ok'] or not local['complete']:raise ValueError('ground_join_worsened_known_local_return')
        craft=[quality.analyze_board(b) for b in (parent,child)]
        if any(craft[1][k]>craft[0][k] for k in ('issue_count','non_octilinear_count')):
            raise ValueError('ground_join_worsened_route_craft')
        import cec_source_ground_leaf as source_leaf
        source_proofs=[r['source_external_ground_leaf'] for r in requests.values()
            if 'source_external_ground_leaf' in r]
        if not source_leaf.bindings_current(source_proofs):
            raise ValueError('ground_join_recompiled_source_leaf_epoch_changed')
        if coowned:
            import cec_source_capacitor_control_ground as cohort_source
            proofs=context['coowned_input_control_cohorts']
            if not cohort_source.bindings_current(proofs):
                raise ValueError('coowned_ground_join_source_epoch_changed')
            result.update(coowned_input_control_cohorts=proofs,
                class_only=True,low_power_classification=False,
                capacitor_ripple_current_qualified=False,ampacity_qualified=False)
        _tick(deadline)
        if epoch!=force._code_identity() or families!=[force._family(p,board_hint) for p in paths]:
            raise ValueError('ground_join_source_family_or_code_changed')
        result.update(ok=True,complete=True,source_sha256=force._hash(paths[0]),candidate_sha256=force._hash(paths[1]),
            joined_source_ground_components=len(joined),all_source_partitions_preserved=True,
            original_reference_root_retained=True,independent_additive_receiving=delta,
            endpoint_receiving=proof,all_known_local_returns=local,new_holes=len(barrels),
            unchanged_optional_ground_sidecar_permissions=context['optional_attached_ground_lands'],
            independently_recompiled_source_ground_leaves=source_proofs,
            modified_nets=['GND'],whole_native_DRC_current_field_Kelvin_and_release_still_required=True)
    except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result


def receive(source,candidate,*,board_hint,timeout_s=10.):
    """Surface-only source join; a new hole needs the separate mesh receiver."""
    return _receive(source,candidate,board_hint=board_hint,timeout_s=timeout_s)


def plan(board,*,board_hint,timeout_s=10.,max_pairs=24,max_length_mm=12.,pad_uuid=None):
    """Unchanged legacy low-power island scope; no implicit bulk-cap alias."""
    return _plan(board,board_hint=board_hint,timeout_s=timeout_s,max_pairs=max_pairs,
        max_length_mm=max_length_mm,pad_uuid=pad_uuid)


def construct_private(board,proposal,*,board_hint):
    return _construct_private(board,proposal,board_hint=board_hint)
