"""Bounded stationary ordinary escape and foreign-branch reconstruction.

A positive ordinary source land can reserve a full-class canonical escape.
Only literal unlocked, ungrouped ordinary source tracks intersecting that
escape can be detoured. Fixed pads, holes, pours, rated and specialized
routes are never acquired. Exact old boundaries AND surviving native
partitions must survive. Construction is untrusted; all shared saved gates
remain mandatory. A failed finite corridor is not a global no-path proof.
"""
import math
from pathlib import Path
import time


def _vectors(vector):
    if vector is None:
        return [(x*1500000,y*1500000) for x,y in
            ((1,0),(0,1),(-1,0),(0,-1),(1,1),(-1,1),(-1,-1),(1,-1))]
    if (type(vector) not in (list,tuple) or len(vector)!=2
            or any(type(x) is not int for x in vector)
            or not 500000<=max(map(abs,vector))<=3000000
            or vector[0] and vector[1] and abs(vector[0])!=abs(vector[1])):
        raise ValueError('bounded_exact_canonical_escape_vector_required')
    return [tuple(vector)]


def _clearance(board,resolver,net):
    return max(int(board.GetDesignSettings().m_MinClearance),
        round(float((resolver(net) or {}).get('clearance',0))*1e6))


def _reservation(board,pad,vector,width):
    import pcbnew
    t=pcbnew.PCB_TRACK(board);t.SetStart(pad.GetPosition())
    t.SetEnd(pcbnew.VECTOR2I(t.GetStart().x+vector[0],t.GetStart().y+vector[1]))
    t.SetWidth(width);t.SetLayer(_pad_face(pad));t.SetNetCode(pad.GetNetCode())
    board.Add(t)
    return t


def _pad_face(pad):
    # PAD.GetLayer() may remain F.Cu on a flipped native SMD pad. Its actual
    # copper LSET, not that nominal scalar, owns electrical face access.
    faces=list(map(int,pad.GetLayerSet().CuStack()))
    if len(faces)!=1 or faces[0] not in (0,2):raise ValueError('one_actual_surface_copper_face_required')
    return faces[0]


def plan(board,source,*,board_hint,net,pad_uuid,escape_vector_nm=None,timeout_s=10.):
    import pcbnew
    import cec_force_current as force
    import cec_fr as fr
    import cec_field_coupling as field
    import cec_ordinary_signal_completion as signal
    import cec_reserved_corridor_track_scope as scope
    from cec_native_items import discard_items
    deadline=time.monotonic()+signal._budget(timeout_s,10.)
    source=Path(source).resolve(strict=True);vectors=_vectors(escape_vector_nm)
    if type(pad_uuid) is not str or not pad_uuid:raise ValueError('actual_source_escape_land_required')
    parent=pcbnew.LoadBoard(str(source))
    if field._field_snapshot_inventory(parent)!=field._field_snapshot_inventory(board):
        raise ValueError('exact_unmodified_native_escape_source_required')
    initial=signal.plan(parent,source,board_hint=board_hint,net=net,
        timeout_s=min(3.,max(.001,deadline-time.monotonic())))
    result=dict(scope='ordinary_source_escape_corridor',complete=False,offers=[],refused=[],
        source_sha256=force._hash(source),net=net,pad_uuid=pad_uuid,routing_admitted=False,
        current_qualified=False,release_authority=False,no_path_proof=False)
    if not initial['complete']:result['reason']=initial.get('reason');return result
    request=initial['request'];ends=signal._pads(parent,request)
    pad=next((p for p in ends if force._uid(p)==pad_uuid),None)
    if pad is None or pad.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD:
        raise ValueError('one_actual_source_join_surface_land_required')
    _pad_face(pad)
    resolver=fr._project_netclass_resolver(str(source));width=request['width_nm']
    for vector in vectors:
        if time.monotonic()>=deadline:break
        scratch=pcbnew.LoadBoard(str(source));land=next(p for fp in scratch.GetFootprints()
            for p in fp.Pads() if force._uid(p)==pad_uuid)
        reservation=_reservation(scratch,land,vector,width)
        row=dict(escape_vector_nm=list(vector))
        try:
            inventory=scope.plan(parent,scratch,[reservation],source_path=source,board_hint=board_hint,
                clearance_for=lambda n:_clearance(parent,resolver,n),maximum_tracks=4,
                timeout_s=min(2.,max(.001,deadline-time.monotonic())))
            cuts=inventory['additional_source_ordinary_tracks']
            if not inventory['all_foreign_track_obstructions_scoped'] or not cuts:
                raise ValueError('no_complete_positive_ordinary_foreign_cut_scope')
            if len({c['net'] for c in cuts})>2 or any(c['source_locked'] for c in cuts):
                raise ValueError('at_most_two_unlocked_foreign_ordinary_nets_required')
            ids=sorted(c['uuid'] for c in cuts);live={force._uid(t):t for t in scratch.GetTracks()}
            if any(live[u].HasSolderMask() or live[u].GetParentGroup() for u in ids):
                raise ValueError('plain_ungrouped_foreign_source_tracks_required')
            discard_items(scratch,[live[u] for u in ids])
            a,z=reservation.GetStart(),reservation.GetEnd();layer=int(reservation.GetLayer())
            if not (fr._edge_leg_clear(scratch,a,z,width//2) and
                    fr._tap_foreign_clear(scratch,a,z,width,layer,request['clearance_nm'],{land.GetNetCode()})):
                raise ValueError('fixed_native_pad_hole_pour_or_outline_blocks_escape')
            result['offers'].append(dict(net=net,pad_uuid=pad_uuid,escape_vector_nm=list(vector),
                retired_track_uuids=ids,foreign_tracks=[{k:v for k,v in c.items() if k!='witnesses'} for c in cuts],source_signal_request=request,
                source_sha256=result['source_sha256']))
        except (ValueError,RuntimeError) as exc:
            row['reason']=str(exc);result['refused'].append(row)
    result['offers'].sort(key=lambda r:(len(r['retired_track_uuids']),r['escape_vector_nm']))
    result['complete']=bool(result['offers']);result['elapsed_s']=timeout_s-(deadline-time.monotonic())
    return result


def _escape_boards(source,proposal,*,board_hint,deadline):
    """Reserve a reachable legal barrel BEFORE detouring foreign branches.

    A narrow line ending in a cul-de-sac is not a usable layer portal. Every
    seat is sourced from actual all-layer foreign/edge/hole/factory geometry,
    every full-width approach gets the unchanged field/native predicates, and
    the real new barrel becomes an obstacle for each reconstructed foreign
    branch. No trace or fixed-land ownership beyond the original cut expands.
    """
    import pcbnew
    import cec_force_current as force
    import cec_fr as fr
    import cec_native_via_frontier as frontier
    import cec_field_search as search
    from cec_native_items import discard_items
    ids=set(proposal['retired_track_uuids']);request=proposal['source_signal_request'];net=proposal['net']
    def fresh():
        b=pcbnew.LoadBoard(str(source));discard_items(b,[t for t in b.GetTracks() if force._uid(t) in ids])
        pad=next(p for f in b.GetFootprints() for p in f.Pads() if force._uid(p)==proposal['pad_uuid'])
        return b,pad
    b,pad=fresh();face=_pad_face(pad);resolver=fr._project_netclass_resolver(str(source))
    spec=resolver(net) or {}
    dia=float(spec.get('via_diameter') or .6);drill=float(spec.get('via_drill') or .3)
    with force._thermal_hint(board_hint):
        seats=frontier.sites(b,pad.GetNetCode(),tuple(pad.GetPosition()),clearance_nm=request['clearance_nm'],
            radius_mm=3.,max_sites=4,deadline=min(deadline,time.monotonic()+2.),diverse=True,
            diameter_mm=dia,drill_mm=drill)
    for at in seats['sites_nm']:
        if time.monotonic()>=deadline:break
        b,pad=fresh();end=pcbnew.VECTOR2I(*at)
        guard=search.PlanarSearchGuard(b,net,netclass_resolver=resolver,board_hint=board_hint,
            conservative_cross_layer_proposals=True)
        with force._thermal_hint(board_hint):
            legs=fr._guarded_profiled_lastmile_legs(b,pad.GetPosition(),end,request['width_nm'],face,
                request['clearance_nm'],pad.GetNetCode(),lambda a,z,r:fr._edge_leg_clear(b,a,z,r),foreign_cache={},
                deadline_monotonic=min(deadline,time.monotonic()+1.),maze_margin_mm=1.,refine_maze=True,
                refinement_grids_mm=(.2,.1),endpoint_detail_grid_mm=.1,compact_phase_jogs=True,
                run_guard=lambda a,z,w:guard(a,z,w,face))
        if not legs:continue
        for a,z,w in legs:
            if w!=request['width_nm']:raise ValueError('source_class_escape_width_changed')
            t=pcbnew.PCB_TRACK(b);t.SetStart(a);t.SetEnd(z);t.SetWidth(w);t.SetLayer(face);t.SetNetCode(pad.GetNetCode());b.Add(t)
        via=pcbnew.PCB_VIA(b);via.SetPosition(end);via.SetWidth(round(seats['diameter_mm']*1e6))
        via.SetDrill(round(seats['drill_mm']*1e6));via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetNetCode(pad.GetNetCode());b.Add(via)
        yield b,dict(kind='source_legal_ordinary_barrel_and_full_width_approach',at_nm=list(at),
            diameter_mm=seats['diameter_mm'],drill_mm=seats['drill_mm'],capacity_qualified=False,
            field_and_saved_native_receiving_still_required=True)
    if time.monotonic()<deadline:
        b,pad=fresh();_reservation(b,pad,proposal['escape_vector_nm'],request['width_nm'])
        yield b,dict(kind='full_class_trace_only_fallback',capacity_qualified=False)


def construct_private(source,candidate,proposal,*,board_hint,timeout_s=40.):
    """One hard lease for TWO finite stages, not a restarted search timeout.

    Reconstructing and receiving the foreign branch precedes the additive
    target search. Sharing the single-net20s allocation starved that second
    stage's native validation/save/import overhead. This atomic two-net scope
    has an explicit40s outer ceiling; individual searches/native checks stay
    <=10s, with the unchanged120s shared worker/admission ceiling outside.
    """
    import pcbnew
    import cec_force_current as force
    import cec_fr as fr
    import cec_field_search as search
    import cec_ordinary_signal_completion as signal
    import cec_ordinary_route_receiving as ordinary
    import cec_additive_pair_repair as additions
    import cec_source_literal_retirement as literal_cut
    import cec_source_retaining_ses_import as raw
    import cec_certificate_repair as repair
    import cec_native_portal_geometry as geometry
    from cec_native_items import discard_items
    deadline=time.monotonic()+signal._budget(timeout_s,40.)
    source,candidate=[Path(p).resolve(strict=True) for p in (source,candidate)]
    if source==candidate or force._hash(source)!=force._hash(candidate):
        raise ValueError('exact_private_corridor_source_copy_required')
    epoch=force._code_identity();family=force._family(source,board_hint)
    parent=pcbnew.LoadBoard(str(source));board=pcbnew.LoadBoard(str(source))
    fresh=plan(parent,source,board_hint=board_hint,net=proposal['net'],pad_uuid=proposal['pad_uuid'],
        escape_vector_nm=proposal['escape_vector_nm'],timeout_s=min(3.,max(.001,deadline-time.monotonic())))
    if proposal not in fresh['offers']:raise ValueError('independently_recompiled_corridor_scope_required')
    ids=set(proposal['retired_track_uuids']);live={force._uid(t):t for t in board.GetTracks()}
    original_ids=set(live);source_cuts={force._uid(t):t for t in parent.GetTracks() if force._uid(t) in ids}
    prototypes={u:live[u].Duplicate() for u in ids}
    request=proposal['source_signal_request'];net=proposal['net'];resolver=fr._project_netclass_resolver(str(source))
    attempts=[];built=False;portal=None
    for board,portal in _escape_boards(source,proposal,board_hint=board_hint,deadline=min(deadline-7.,time.monotonic()+7.)):
        restored=True
        for uid in sorted(ids):
            old=prototypes[uid];width=int(old.GetWidth());layer=int(old.GetLayer());diagnostics={}
            guard=search.PlanarSearchGuard(board,old.GetNetname(),netclass_resolver=resolver,board_hint=board_hint,
                conservative_cross_layer_proposals=True)
            if time.monotonic()>=deadline-7.:restored=False;break
            with force._thermal_hint(board_hint):
                legs=fr._guarded_profiled_lastmile_legs(board,old.GetStart(),old.GetEnd(),width,layer,
                    max(request['clearance_nm'],_clearance(parent,resolver,old.GetNetname())),old.GetNetCode(),
                    lambda a,z,r:fr._edge_leg_clear(board,a,z,r),foreign_cache={},
                    deadline_monotonic=min(deadline-7.,time.monotonic()+1.5),maze_margin_mm=2.,
                    refine_maze=True,refinement_grids_mm=(.2,.1),endpoint_detail_grid_mm=.1,
                    compact_phase_jogs=True,run_guard=lambda a,z,w:guard(a,z,w,layer),search_diagnostics=diagnostics)
            attempts.append(dict(source_track_uuid=uid,portal=portal,path_found=bool(legs),diagnostics=diagnostics))
            if not legs:restored=False;break
            for a,z,w in legs:
                if w!=width:raise ValueError('foreign_corridor_source_width_changed')
                t=old.Duplicate();t.m_Uuid.Clone(pcbnew.KIID());t.SetStart(a);t.SetEnd(z);board.Add(t)
        if restored:built=True;break
    if not built:return dict(complete=False,reason='bounded_reserved_barrel_or_branch_detour_unavailable',attempts=attempts)
    # Restore EVERY original branch boundary and retained junction, not only
    # the two ends of a geometric segment. This is still construction only.
    ordinary._boundaries(parent,board,list(source_cuts.values()),deadline,
        ordinary_source=source,board_hint=board_hint)
    old_parts=ordinary._partition(parent,deadline,retired_uuids=ids)
    new_parts=ordinary._partition(board,deadline,retained_keys=set().union(*old_parts))
    if any(not any(p<=q for q in new_parts) for p in old_parts):
        raise ValueError('corridor_detour_lost_surviving_native_junction')
    raw.write_raw(candidate,literal_cut.subtract(raw.raw_text(source),ids))
    save={};additions.save_native_additions(candidate,board,save,original_ids-ids,board_hint=board_hint)
    saved_cut=ordinary.receive(source,candidate,board_hint=board_hint,retired_track_uuids=sorted(ids),timeout_s=10.)
    if not saved_cut['ok'] or not saved_cut['complete']:
        return dict(complete=False,reason='saved_corridor_branch_reconstruction_refused',receiving=saved_cut,attempts=attempts)
    remaining=deadline-time.monotonic()
    if remaining<=3.:return dict(complete=False,reason='corridor_join_lease',attempts=attempts)
    ends=signal._pads(parent,request)
    target=dict(target_net=net,width_mm=request['width_nm']/1e6,clearance_mm=request['clearance_nm']/1e6,
        retained_same_face_track_ends=True,retained_barrel_face_access=True,route_endpoints=[dict(uuid=force._uid(p),kind='pad',
            x_mm=p.GetPosition().x/1e6,y_mm=p.GetPosition().y/1e6) for p in ends])
    outer=repair._WORKER_DEADLINE.get()
    token=repair._WORKER_DEADLINE.set(min(deadline,outer) if outer is not None else deadline)
    try:
        joined=repair._spawn_apply(geometry.apply_native_portals,(str(candidate),target,min(10.,remaining-2.)),
            timeout_s=remaining,search_budget_arg=2)
    finally:repair._WORKER_DEADLINE.reset(token)
    if epoch!=force._code_identity() or family!=force._family(source,board_hint):
        raise ValueError('corridor_source_or_code_epoch_changed')
    return dict(complete=bool(joined.get('closed')) and time.monotonic()<deadline,attempts=attempts,
        join=joined,reserved_portal=portal,branch_reconstruction=saved_cut,request=proposal,routing_admitted=False,release_authority=False)


def receive(source,candidate,*,board_hint,net,pad_uuid,timeout_s=10.):
    import pcbnew
    import cec_force_current as force
    import cec_fr as fr
    import cec_ordinary_signal_completion as signal
    import cec_ordinary_route_receiving as ordinary
    import cec_additive_route_receiving as additive
    import cec_source_literal_additions as literal
    deadline=time.monotonic()+signal._budget(timeout_s,10.)
    result=dict(ok=False,complete=False,errors=[],whole_shared_stage_still_required=True,
        current_qualified=False,routing_admitted=False,release_authority=False)
    try:
        source,candidate=[Path(p).resolve(strict=True) for p in (source,candidate)]
        epoch=force._code_identity();families=[force._family(p,board_hint) for p in (source,candidate)]
        parent,child=[pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
        fresh=plan(parent,source,board_hint=board_hint,net=net,pad_uuid=pad_uuid,timeout_s=min(3.,timeout_s))
        _,old=additive._nodes(source);_,new=additive._nodes(candidate);retired=set(old)-set(new);incoming=set(new)-set(old)
        offers=[q for q in fresh['offers'] if set(q['retired_track_uuids'])==retired]
        if not offers:raise ValueError('actual_source_ordinary_corridor_cut_required')
        request=offers[0]['source_signal_request'];cuts={force._uid(t):t for t in parent.GetTracks() if force._uid(t) in retired}
        widths={net:request['width_nm']}
        for t in cuts.values():
            n=str(t.GetNetname());w=int(t.GetWidth())
            if n in widths and widths[n]!=w:raise ValueError('uniform_source_corridor_width_required')
            widths[n]=w
        names=literal.incoming_copper_nets(candidate.read_text(),incoming)
        if not set(names.values())<=widths.keys():raise ValueError('unscoped_incoming_corridor_net')
        material={force._uid(t):t for t in child.GetTracks() if force._uid(t) in incoming}
        if not material or set(material)!=incoming or any(t.GetClass() not in ('PCB_TRACK','PCB_VIA')
                or t.GetClass()=='PCB_TRACK' and t.GetWidth()!=widths[str(t.GetNetname())] for t in material.values()):
            raise ValueError('corridor_incoming_kind_or_source_width_changed')
        graph=fr._read_only_route_connectivity(child);ends=signal._pads(child,request)
        reached={force._uid(ends[0])}|{force._uid(i) for i in graph.GetConnectedItems(ends[0])}
        target_additions={u for u,t in material.items() if t.GetNetname()==net}
        if force._uid(ends[1]) not in reached or not target_additions<=reached:
            raise ValueError('corridor_target_not_one_complete_native_join')
        counts=[fr.net_connectivity_component_count(b,b.GetNetcodeFromNetname(net)) for b in (parent,child)]
        if counts[1]>=counts[0]:raise ValueError('corridor_target_component_count_not_reduced')
        for u,t in material.items():
            contacts={u}|{force._uid(i) for i in graph.GetConnectedItems(t)}
            if not contacts&(set(old)-retired):raise ValueError('corridor_incoming_orphan_component')
        replay=ordinary.receive(source,candidate,board_hint=board_hint,retired_track_uuids=sorted(retired),
            timeout_s=min(10.,max(.001,deadline-time.monotonic())))
        if not replay['ok'] or not replay['complete']:raise ValueError('independent_saved_ordinary_reconstruction_refused:'+str(replay['errors']))
        if families!=[force._family(p,board_hint) for p in (source,candidate)] or epoch!=force._code_identity() or time.monotonic()>=deadline:
            raise ValueError('corridor_source_candidate_code_or_deadline_changed')
        result.update(ok=True,complete=True,retired_track_uuids=sorted(retired),added_native_uuids=sorted(incoming),
            source_components=counts[0],candidate_components=counts[1],independent_source_delta=replay)
    except (ValueError,RuntimeError,KeyError,TypeError,OSError) as exc:result['errors'].append(type(exc).__name__+':'+str(exc))
    return result


def invariants(source,candidate,*,board_hint):
    """Original-parent invariants for a separately received ordinary cut.

    Not an additive waiver: exact subtract/add replay, whole old partitions
    and cut boundaries come from a fresh ordinary receiver. Protected/current
    and qualified-pair checks always use the ORIGINAL immutable source.
    """
    import pcbnew
    import cec_additive_route_receiving as additive
    import cec_ordinary_route_receiving as ordinary
    import cec_current_debt as current_debt
    import cec_placement_route_prefix as prefix
    import cec_fr as fr
    _,old=additive._nodes(source);_,new=additive._nodes(candidate)
    replay=ordinary.receive(source,candidate,board_hint=board_hint,retired_track_uuids=sorted(set(old)-set(new)),timeout_s=10.)
    frozen=prefix.capture(source,include_local_authority=False)
    current=current_debt.receive(source,candidate,board_hint=board_hint)
    terms=dict(exact_ordinary_source_delta=replay.get('ok') is True and replay.get('complete') is True,
        protected_copper_exact=fr.check_copper_geometry_prefix(candidate,frozen)['ok'],
        qualified_pairs_exact=prefix.check_qualified_pairs(candidate,frozen)['ok'],
        exact_current_debt_nonregression=current.get('ok') is True and current.get('complete') is True)
    return dict(ok=all(terms.values()),complete=True,terms=terms,native_replay=replay,
        current_debt={k:v for k,v in current.items() if k not in ('before_result','after_result')},release_authority=False)
