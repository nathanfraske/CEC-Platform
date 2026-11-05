"""Bounded fixed-port full-current path simplification, not a signal waiver.

Every removed source edge retains its exact width, face and complete current
contract. End ports stay fixed; retained contacts must have an exact shared
full-width native capsule kernel at a port. The explicit retained-barrel
policy may preserve an existing circular via entry, never its current rating.
Pads, pours and interior side taps are not owned. Candidate turns are <=45 degrees and actual visible
copper plus exact radical length must improve. Full saved native/current/
field/Kelvin/stack receiving remains mandatory; no new rating is inferred.
"""
from collections import Counter,defaultdict,deque
import json,math,tempfile,time
from pathlib import Path
import pcbnew
import cec_additive_route_receiving as additive
import cec_cell_row_rebuild as binding
import cec_copper_echo as syntax
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_full_current_corner_finish as material
import cec_full_current_planar_reflow as full
import cec_native_track_ports as ports
import cec_pair_local_reference_refinement as chain
import cec_precision_route as precision
import cec_rated_supply_corner_finish as signatures
import cec_route_quality as quality
import cec_sensitive_scalar_path_reflow as geometry
import cec_source_guided_ordinary_detour as lengths
from cec_native_items import discard_items


def _source(board,source,ids,board_hint,allow_locked_source,deadline):
    if (type(board_hint) is not str or not board_hint or type(allow_locked_source) is not bool or
            Path(board.GetFileName()).resolve()!=Path(source).resolve()):
        raise ValueError('explicit_actual_full_current_path_source_required')
    ids=full.ordinary._ids(ids,'full_current_path_cut',8)
    if not 2<=len(ids)<=8:raise ValueError('two_to_eight_full_current_source_edges_required')
    live={force._uid(t):t for t in board.GetTracks()}
    if not ids<=live.keys():raise ValueError('full_current_path_source_edges_stale')
    cut=[live[u] for u in sorted(ids)]
    if (any(t.GetClass()!='PCB_TRACK' or t.HasSolderMask() or t.GetParentGroup() or
            t.IsLocked() and not allow_locked_source for t in cut) or
            len({(str(t.GetNetname()),int(t.GetLayer()),int(t.GetWidth()),bool(t.IsLocked())) for t in cut})!=1):
        raise ValueError('uniform_ungrouped_full_current_path_process_required')
    net=str(cut[0].GetNetname())
    if net=='GND' or net in {n for p in precision.derive_coupled_pairs(str(source),board=board) for n in (p['p'],p['n'])}:
        raise ValueError('no_ground_or_pair_full_current_path_authority')
    old=[list(p) for p in chain._chain(cut)];lengths.length_terms(old)
    if len({tuple(p) for p in old})!=len(old):raise ValueError('source_full_current_path_must_not_be_cycle')
    _,nodes=additive._nodes(source);process=chain._process(nodes[force._uid(cut[0])])
    if any(chain._process(nodes[force._uid(t)])!=process for t in cut):
        raise ValueError('all_source_full_current_path_process_fields_must_match')
    if time.monotonic()>=deadline:raise ValueError('full_current_path_source_deadline')
    return cut,old


def _contacts(board,cut,points,deadline,port_policy='tracks_only'):
    """Only unchanged native fixed-port full-width kernels are owned here."""
    ids={force._uid(t) for t in cut};face=int(cut[0].GetLayer());net=cut[0].GetNetCode();width=cut[0].GetWidth()
    old=[t.GetEffectiveShape(face) for t in cut];ends=[tuple(points[0]),tuple(points[-1])]
    protected={p:[] for p in ends};rows=[]
    items=[*board.GetTracks(),*(p for f in board.GetFootprints() for p in f.Pads()),*board.Zones()]
    if len(items)>16384:raise ValueError('full_current_path_contact_inventory_bound')
    for item in items:
        if time.monotonic()>=deadline:raise ValueError('full_current_path_contact_deadline')
        uid=force._uid(item)
        if uid in ids or item.GetNetCode()!=net or not item.IsOnLayer(face):continue
        if item.GetClass()=='ZONE':
            if item.GetIsRuleArea():continue
            if not item.IsFilled() or not item.HasFilledPolysForLayer(face):
                if any(item.GetBoundingBox().Intersects(t.GetBoundingBox()) for t in cut):
                    raise ValueError('full_current_path_source_fill_unknown')
                continue
            shape=item.GetFilledPolysList(face)
        else:shape=item.GetEffectiveShape(face)
        if not any(s.Collide(shape,0) for s in old):continue
        if item.GetClass()=='PCB_VIA' and port_policy=='source_circular_barrels' and tuple(item.GetPosition()) in ends:
            import cec_retained_current_barrel_port as barrels
            source_points=[list(p) for p in chain._chain(cut)]
            record=barrels.contact(board,item,face,source_points,points,width,deadline)
            protected[tuple(item.GetPosition())].append(uid);rows.append(record);continue
        matching=[p for p in ends if item.GetClass()=='PCB_TRACK' and item.GetWidth()==width and ports.on_centerline(item,p)]
        if not matching:raise ValueError('full_current_path_unowned_pad_barrel_pour_or_interior_tap:'+uid)
        for at in matching:protected[at].append(uid)
        rows.append(dict(uuid=uid,fixed_ports_nm=[list(p) for p in matching],unchanged_native_contact_disk_diameter_nm=int(width)))
    if not all(protected.values()):raise ValueError('full_current_path_two_retained_native_port_kernels_required')
    return rows


def _candidate_port_contacts(board,cut,old,points,contacts,deadline,port_policy):
    if port_policy=='tracks_only':return contacts
    import cec_retained_current_barrel_port as barrels
    live={force._uid(t):t for t in board.GetTracks()};out=[]
    for row in contacts:
        if row.get('kind')=='PCB_VIA':
            out.append(barrels.contact(board,live[row['uuid']],int(cut[0].GetLayer()),old,points,cut[0].GetWidth(),deadline))
        else:out.append(row)
    return out


def _candidate_paths(board,cut,old,contacts,port_policy,deadline):
    """Protect real terminal escapes before simplifying the middle path."""
    result=geometry._tangent_paths(old)
    if port_policy=='tracks_only':return result
    via_rows=[r for r in contacts if r.get('kind')=='PCB_VIA' and
        r['source_contact']['method']=='identical_actual_native_annular_escape_fragments']
    live={force._uid(t):t for t in board.GetTracks()};face=int(cut[0].GetLayer());width=cut[0].GetWidth()
    left,right=0,len(old)-1
    for row in via_rows:
        via=live[row['uuid']];at=tuple(via.GetPosition());touched=[];shape=via.GetEffectiveShape(face)
        for i,(a,b) in enumerate(zip(old,old[1:])):
            if time.monotonic()>=deadline:raise ValueError('native_barrel_escape_template_deadline')
            if shape.Collide(pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*b),width),1):touched.append(i)
        if at==tuple(old[0]) and touched:left=max(left,max(touched)+1)
        elif at==tuple(old[-1]) and touched:right=min(right,min(touched))
    if left<right:
        middle=old[left:right+1]
        choices=[list(map(list,p)) for p in fr._canonical_45_xy_paths(middle[0],middle[-1])]
        if len(middle)>2:choices+=geometry._tangent_paths(middle)
        for path in choices:
            points=[*old[:left],*path,*old[right+1:]]
            try:points=[list(p) for p in geometry._points(points)]
            except ValueError:continue
            if len(points)<len(old):result.append(points)
    unique={tuple(map(tuple,p)):p for p in result}
    return sorted(unique.values(),key=lambda p:(sum(math.dist(a,b) for a,b in zip(p,p[1:])),len(p),p))


def _shape(board,cut,old,points,deadline,foreign_cache=None,source_contacts=None,port_policy='tracks_only'):
    points=[list(p) for p in geometry._points(points)]
    if points[0]!=old[0] or points[-1]!=old[-1]:raise ValueError('actual_source_full_current_path_ports_must_stay_fixed')
    if len(points)>=len(old) or not lengths.strictly_shorter(points,old):
        raise ValueError('full_current_path_must_strictly_shorten_and_remove_strokes')
    contacts=(_contacts(board,cut,points,deadline,port_policy) if source_contacts is None else
        _candidate_port_contacts(board,cut,old,points,source_contacts,deadline,port_policy))
    turns=geometry._boundary_turns(board,cut,points,deadline)
    geometry._clear_path(board,cut,points,deadline,{} if foreign_cache is None else foreign_cache)
    new=[]
    for a,b in zip(points,points[1:]):
        t=cut[0].Duplicate();t.SetStart(pcbnew.VECTOR2I(*a));t.SetEnd(pcbnew.VECTOR2I(*b));new.append(t)
    visible=material._visible_removed(board,cut,new,{force._uid(t) for t in cut},deadline=deadline)
    return dict(points_nm=points,native_port_contacts=contacts,boundary_turns=turns,actual_visible_native_material_removed=visible)


def plan(board,source,*,board_hint,retired_track_uuids,points_nm,allow_locked_source=False,port_policy='tracks_only'):
    if type(port_policy) is not str or port_policy not in ('tracks_only','source_circular_barrels'):
        raise ValueError('explicit_known_full_current_path_port_policy_required')
    deadline=time.monotonic()+10.
    cut,old=_source(board,source,retired_track_uuids,board_hint,allow_locked_source,deadline)
    current=full.plan(board,source,board_hint=board_hint,retired_track_uuids=sorted(force._uid(t) for t in cut),
        max_source_track_mm=32.,max_source_cut_mm=48.,timeout_s=max(.001,deadline-time.monotonic()))
    shape=_shape(board,cut,old,points_nm,deadline,port_policy=port_policy)
    if time.monotonic()>=deadline:raise ValueError('full_current_path_plan_deadline')
    result=dict(schema=1,source_sha256=force._hash(Path(source)),source_binding=binding._source_binding(board),
        retired_track_uuids=sorted(force._uid(t) for t in cut),source_points_nm=old,shape=shape,
        full_current_proposal=json.loads(json.dumps(current)),allow_locked_source=allow_locked_source,
        source_current_width_face_and_roles_unchanged=True,release_authority=False)
    if port_policy!='tracks_only':result['port_policy']=port_policy
    return result


def materialize(board,source,proposal,*,board_hint):
    if plan(board,source,board_hint=board_hint,retired_track_uuids=proposal['retired_track_uuids'],
            points_nm=proposal['shape']['points_nm'],allow_locked_source=proposal['allow_locked_source'],port_policy=proposal.get('port_policy','tracks_only'))!=proposal:
        raise ValueError('stale_or_forged_full_current_path_plan')
    live={force._uid(t):t for t in board.GetTracks()};cut=[live[u] for u in proposal['retired_track_uuids']];new=[]
    for a,b in zip(proposal['shape']['points_nm'],proposal['shape']['points_nm'][1:]):
        t=cut[0].Duplicate();t.m_Uuid.Clone(pcbnew.KIID());t.SetStart(pcbnew.VECTOR2I(*a));t.SetEnd(pcbnew.VECTOR2I(*b));board.Add(t);new.append(force._uid(t))
    discard_items(board,cut);additive._ground_refill(board)
    return dict(retired_track_uuids=proposal['retired_track_uuids'],added_native_uuids=new,new_holes=0,new_vias=0,pads_moved=0,release_authority=False)


def receive(source,candidate,proposal,*,board_hint):
    result=dict(ok=False,complete=False,errors=[],current_qualified=False,release_authority=False)
    try:
        source,candidate=map(Path,(source,candidate));epoch=force._code_identity()
        families=[force._family(p,board_hint) for p in (source,candidate)];parent=pcbnew.LoadBoard(str(source))
        params=dict(board_hint=board_hint,retired_track_uuids=proposal['retired_track_uuids'],
            points_nm=proposal['shape']['points_nm'],allow_locked_source=proposal['allow_locked_source'],port_policy=proposal.get('port_policy','tracks_only'))
        if plan(parent,source,**params)!=proposal:raise ValueError('saved_source_full_current_path_plan_changed')
        if force._sidecars(source)!=force._sidecars(candidate) or force._preservation_snapshot(source)[1]!=force._preservation_snapshot(candidate)[1]:
            raise ValueError('full_current_path_source_metadata_or_sidecars_changed')
        _,old=additive._nodes(source);got_root,got=additive._nodes(candidate);retired=set(old)-set(got);added=set(got)-set(old)
        if retired!=set(proposal['retired_track_uuids']) or len(added)!=len(proposal['shape']['points_nm'])-1:
            raise ValueError('exact_full_current_path_source_retirement_and_replacement_required')
        with tempfile.TemporaryDirectory(prefix='cec-full-current-path-') as tmp:
            path=force._copy_family(source,Path(tmp)/'expected');board=pcbnew.LoadBoard(str(path));fresh=plan(board,path,**params)
            materialize(board,path,fresh,board_hint=board_hint);field._save_field_snapshot(board,path)
            want_root,want=additive._nodes(path);new_ids=set(want)-set(old)
            if (signatures._header(want_root,want)!=signatures._header(got_root,got) or set(want)&set(old)!=set(got)&set(old)
                    or any(syntax._freeze(want[u])!=syntax._freeze(got[u]) for u in set(want)&set(old))
                    or Counter(signatures._signature(want[u]) for u in new_ids)!=Counter(signatures._signature(got[u]) for u in added)):
                raise ValueError('independent_saved_full_current_path_replay_differs')
        typed=full.receive(source,candidate,board_hint=board_hint,retired_track_uuids=sorted(retired),
            max_source_track_mm=32.,max_source_cut_mm=48.,timeout_s=10.)
        result['independent_full_current_receiving']=typed
        if not typed['ok'] or not typed['complete']:raise ValueError('full_current_path_receiving_refused:'+str(typed['errors']))
        if epoch!=force._code_identity() or families!=[force._family(p,board_hint) for p in (source,candidate)]:
            raise ValueError('full_current_path_source_candidate_or_code_changed')
        saved=(sum(math.dist(a,b) for a,b in zip(proposal['source_points_nm'],proposal['source_points_nm'][1:]))-
            sum(math.dist(a,b) for a,b in zip(proposal['shape']['points_nm'],proposal['shape']['points_nm'][1:])))/1e6
        result.update(ok=True,complete=True,code_identity=epoch,source_sha256=force._hash(source),candidate_sha256=force._hash(candidate),
            retired_track_uuids=sorted(retired),added_native_uuids=sorted(added),saved_trace_length_mm=saved,
            native_strokes_before_after=[len(retired),len(added)],net=proposal['full_current_proposal']['net'],
            source_width_face_current_ports_and_native_contacts_preserved=True,source_family_and_code_unchanged=True,
            new_vias=0,new_holes=0,pads_moved=0,power_pours_changed=False,
            receiving_components_have_individual_unchanged_ten_second_leases=True)
    except Exception as exc:result['errors'].append(type(exc).__name__+':'+str(exc))
    return result


def _fair_menu(menu):
    """Round-robin native owners and distinct source series corridors.

    Overlapping windows of one blocked feeder cannot consume the entire
    portfolio before another net/face or independent series path is tried.
    Gain ranks only WITHIN a source corridor; no electrical rule is changed.
    """
    owners=defaultdict(lambda:defaultdict(list))
    for row in sorted(menu,key=lambda q:(-q[0],q[1])):owners[row[3][:3]][row[3][3]].append(row)
    queues={k:deque(deque(v) for f,v in sorted(groups.items(),key=lambda q:(-q[1][0][0],q[0]))) for k,groups in owners.items()}
    out=[]
    while any(queues.values()):
        for key in sorted(queues):
            q=queues[key]
            if not q:continue
            family=q.popleft();out.append(family.popleft())
            if family:q.append(family)
    return out


def discover(board,source,*,board_hint,allow_locked_source=False,maximum_candidates=4,port_policy='tracks_only'):
    if (type(maximum_candidates) is not int or not 1<=maximum_candidates<=8 or type(board_hint) is not str or not board_hint
            or type(allow_locked_source) is not bool or Path(board.GetFileName()).resolve()!=Path(source).resolve()
            or type(port_policy) is not str or port_policy not in ('tracks_only','source_circular_barrels')):
        raise ValueError('bounded_actual_full_current_path_discovery_required')
    deadline=time.monotonic()+10.;groups=defaultdict(list)
    with force._thermal_hint(board_hint):
        domains=full.topology.board_current_domains(board,board_hint)
        distributed=full.topology.distributed_supply_contracts(board,board_hint,
            netclass_resolver=fr._project_netclass_resolver(str(source),board=board))
    typed_nets=(set(domains)|set(distributed['contracts']))-{'GND'}
    for t in board.GetTracks():
        if (t.GetClass()=='PCB_TRACK' and str(t.GetNetname()) in typed_nets and not t.HasSolderMask()
                and not t.GetParentGroup() and (allow_locked_source or not t.IsLocked())):
            groups[str(t.GetNetname()),int(t.GetLayer()),int(t.GetWidth()),bool(t.IsLocked())].append(t)
    if sum(map(len,groups.values()))>4096:raise ValueError('bounded_full_current_path_discovery_track_inventory')
    menu=[];models={};refusals=Counter();windows=set()
    pairnets={n for p in precision.derive_coupled_pairs(str(source),board=board) for n in (p['p'],p['n'])}
    for (net,face,width,locked),edges in sorted(groups.items()):
        if time.monotonic()>=deadline:break
        if not net or net=='GND' or net in pairnets:continue
        if net not in models:
            try:models[net]=full._model(board,source,net,board_hint)
            except ValueError as exc:models[net]=str(exc)
        if type(models[net]) is str:continue
        try:floor=full._source_width_floor(board,source,models[net][2],face)
        except ValueError:continue
        if not floor<=width<=10000000:continue
        live={force._uid(t):t for t in edges};incidence=defaultdict(list)
        for uid,t in live.items():
            for point in (tuple(t.GetStart()),tuple(t.GetEnd())):incidence[point].append(uid)
        neighbors=defaultdict(set)
        for peers in incidence.values():
            if len(peers)==2:
                neighbors[peers[0]].add(peers[1]);neighbors[peers[1]].add(peers[0])
        pending=set(live);families={}
        while pending:
            seen_group={pending.pop()};todo=list(seen_group)
            while todo:
                at=todo.pop()
                for uid in neighbors[at]&pending:pending.remove(uid);seen_group.add(uid);todo.append(uid)
            key=(net,face,width,tuple(sorted(seen_group)))
            for uid in seen_group:families[uid]=key
        for first,t in sorted(live.items()):
            for begin in (tuple(t.GetStart()),tuple(t.GetEnd())):
                at=begin;ids=[];uid=first
                while uid not in ids and len(ids)<8:
                    edge=live[uid];at=tuple(edge.GetEnd()) if tuple(edge.GetStart())==at else tuple(edge.GetStart());ids.append(uid)
                    key=tuple(sorted(ids))
                    if len(ids)>=2 and key not in windows:
                        windows.add(key);cut=[live[u] for u in key]
                        if any(t.GetLength()>32000000 for t in cut) or sum(t.GetLength() for t in cut)>48000000:break
                        try:old=[list(p) for p in chain._chain(cut)];lengths.length_terms(old)
                        except ValueError:break
                        shortest=max(abs(old[-1][i]-old[0][i]) for i in (0,1))+(math.sqrt(2)-1)*min(abs(old[-1][i]-old[0][i]) for i in (0,1))
                        gain=sum(t.GetLength() for t in cut)-shortest
                        if gain>20000:menu.append((gain,key,old,families[first]))
                    peers=incidence[at]
                    if len(peers)!=2:break
                    uid=next(u for u in peers if u!=uid)
                if len(windows)>8192:raise ValueError('full_current_path_discovery_window_bound')
    offered=[];trials=0;seen=set();foreign={};frontier=[]
    for gain,ids,old,family in _fair_menu(menu):
        if time.monotonic()>=deadline or len(offered)>=maximum_candidates or trials>=64:break
        if ids in seen:continue
        seen.add(ids);cut=[t for t in board.GetTracks() if force._uid(t) in ids]
        row=dict(net=str(cut[0].GetNetname()),layer=int(cut[0].GetLayer()),width_nm=int(cut[0].GetWidth()),
            source_track_uuids=list(ids),source_points_nm=old,predicted_upper_gain_mm=gain/1e6,
            source_series_family=list(family[3]),native_candidates_checked=0,cheap_boundary_refusals=0,refusals=[],refused_candidate_paths=[])
        if len(frontier)<128:frontier.append(row)
        try:contacts=_contacts(board,cut,old,deadline,port_policy)
        except ValueError as exc:
            refusals[str(exc).split(':')[0]]+=1;row['refusals'].append(str(exc));continue
        for points in _candidate_paths(board,cut,old,contacts,port_policy,deadline):
            if (time.monotonic()>=deadline or len(offered)>=maximum_candidates or trials>=64
                    or row['native_candidates_checked']>=4):break
            try:
                if not lengths.strictly_shorter(points,old):continue
                # Invalid external tangents are structural rejections, not
                # funded native collision trials. Do not spend all64 trials
                # on lead-in variants of the same obstructed source window.
                try:geometry._boundary_turns(board,cut,points,deadline)
                except ValueError:
                    row['cheap_boundary_refusals']+=1;continue
                try:_candidate_port_contacts(board,cut,old,points,contacts,deadline,port_policy)
                except ValueError as exc:
                    row.setdefault('cheap_barrel_launch_refusals',0);row['cheap_barrel_launch_refusals']+=1
                    refusals[str(exc).split(':')[0]]+=1;continue
                trials+=1;row['native_candidates_checked']+=1
                _shape(board,cut,old,points,deadline,foreign,source_contacts=contacts,port_policy=port_policy)
                offered.append(dict(retired_track_uuids=list(ids),points_nm=points,predicted_gain_mm=(
                    sum(t.GetLength() for t in cut)-sum(math.dist(a,b) for a,b in zip(points,points[1:])))/1e6))
                row['accepted_geometry_points_nm']=points
                break
            except (ValueError,RuntimeError) as exc:
                refusals[str(exc).split(':')[0]]+=1;row['refusals'].append(str(exc))
                row['refused_candidate_paths'].append(dict(points_nm=points,reason=str(exc)))
    return dict(complete=time.monotonic()<deadline,requests=offered,source_windows=len(windows),ranked_source_detours=len(menu),
        windows_examined=len(seen),candidate_paths_examined=trials,refusals=dict(refusals),
        source_bound_frontier=frontier,frontier_sample_complete=len(frontier)==len(seen),
        maximum_native_trials_per_window=4,maximum_native_trials=64,
        owner_and_native_series_family_round_robin=True,
        port_policy=port_policy,
        bounded_portfolio_not_no_path_proof=True,source_geometry_mutated=False,release_authority=False)
