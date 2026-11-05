"""Typed ordinary SMD-land corner refinement, not a launch-policy waiver.

Keep the global pad/via launch protection. Only this source-owned operation
may replace an exact two-edge, hole-free SMD corner. Every old adjacency and
the existing native pad-contact web witness must survive; pads, barrels,
widths, planes, settings and electrical roles stay fixed. Real visible native
material removal is required. Power/sensitive/pair nets gain no permission.
"""
from collections import Counter,defaultdict
import json,tempfile,time
from pathlib import Path
import pcbnew
import cec_additive_route_receiving as additive
import cec_cell_row_rebuild as binding
import cec_copper_echo as syntax
import cec_force_current as force
import cec_fr as fr
import cec_full_current_corner_finish as material
import cec_native_fill_geometry as fills
import cec_ordinary_route_receiving as ordinary
import cec_rated_supply_corner_finish as signatures
import cec_rectilinear_copper as copper
import cec_field_coupling as field
import cec_route_quality as quality
from cec_octilinear_corner import kind,coordinate_inset
from cec_route_corner_contacts import native_pad_anchor,preserve_contacts
from cec_route_corner_contacts import native_contact_polygon as _polygon,native_contact_radius
from cec_native_items import discard_items


def _contact_radius(pad,tracks,face,width,deadline):
    return native_contact_radius(pad,tracks,face,width,deadline)


def _candidates(board,source,board_hint,allow_locked_source,deadline):
    if type(allow_locked_source) is not bool or type(board_hint) is not str or not board_hint:
        raise ValueError('explicit_ordinary_smd_corner_context_required')
    if Path(board.GetFileName()).resolve()!=Path(source).resolve():
        raise ValueError('actual_native_ordinary_smd_corner_source_required')
    nets=ordinary.eligible_nets(board,source,board_hint);tracks=list(board.GetTracks())
    pads=[p for f in board.GetFootprints() for p in f.Pads()]
    if len(tracks)+len(pads)>16384:raise ValueError('pad_corner_native_inventory_bound')
    live={force._uid(t):t for t in tracks}
    if len(live)!=len(tracks):raise ValueError('pad_corner_duplicate_native_track_identity')
    by_point=defaultdict(list);rows=[];skips=Counter();hidden=[]
    for t in tracks:
        if t.GetClass()=='PCB_TRACK' and str(t.GetNetname()) in nets:
            for at in (tuple(t.GetStart()),tuple(t.GetEnd())):by_point[t.GetNetname(),int(t.GetLayer()),at].append(t)
    shapes=(pcbnew.PAD_SHAPE_RECT,pcbnew.PAD_SHAPE_ROUNDRECT,pcbnew.PAD_SHAPE_CIRCLE,pcbnew.PAD_SHAPE_OVAL)
    for (net,face,at),edges in sorted(by_point.items()):
        if time.monotonic()>=deadline:raise ValueError('pad_corner_inventory_deadline')
        if (len(edges)!=2 or face not in (pcbnew.F_Cu,pcbnew.B_Cu) or
                len({(t.GetWidth(),bool(t.IsLocked())) for t in edges})!=1 or
                not 0<edges[0].GetWidth()<500000 or any(t.HasSolderMask() or t.GetParentGroup() or
                    t.IsLocked() and not allow_locked_source or not 0<t.GetLength()<=32000000 for t in edges)):
            continue
        far=[t.GetEnd() if tuple(t.GetStart())==at else t.GetStart() for t in edges]
        if kind(*[(p.x-at[0],p.y-at[1]) for p in far]) is None:continue
        point=pcbnew.VECTOR2I(*at)
        anchors=[p for p in pads if p.GetNetname()==net and native_pad_anchor(p,point,layer_id=face)]
        if not anchors:continue
        if (not 1<=len(anchors)<=4 or any(p.HasHole() or p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD or
                p.GetShape() not in shapes or p.GetParentFootprint().IsDNP() for p in anchors)):
            skips['unsupported_or_drilled_anchor']+=1;continue
        # This owner has no barrel/contact or transition authority. A source
        # pad/via compound must use the separate physical annular owner.
        if any(t.GetClass()=='PCB_VIA' and t.GetNetname()==net and t.IsOnLayer(face) and
                any(t.GetEffectiveShape(face).Collide(p.GetEffectiveShape(face),0) for p in anchors) for t in tracks):
            skips['compound_pad_barrel_anchor_requires_other_owner']+=1;continue
        # Do not turn a real interior branch into a cosmetically simpler bend.
        if any(t.GetClass()=='PCB_TRACK' and t not in edges and t.GetNetname()==net and t.IsOnLayer(face)
                and t.GetEffectiveShape(face).Collide(point,0) for t in tracks):
            skips['retained_body_junction']+=1;continue
        cap=edges[0].Duplicate();cap.SetStart(point);cap.SetEnd(point)
        visible=copper._native_capsule(cap)
        for pad in anchors:visible.BooleanSubtract(_polygon(pad,face,deadline))
        if not visible.OutlineCount():
            hidden.append(dict(net=net,layer=face,at_nm=list(at),fixed_pad_uuids=sorted(force._uid(p) for p in anchors),
                complete_native_corner_cap_inside_actual_fixed_pad_copper=True));continue
        rows.append(dict(net=net,layer=face,at_nm=list(at),source_track_uuids=sorted(force._uid(t) for t in edges),
            anchor_pad_uuids=sorted(force._uid(p) for p in anchors)))
        if len(rows)>128:raise ValueError('pad_corner_candidate_bound')
    return dict(requests=rows,skipped=dict(skips),purposeful_fixed_pad_corners=hidden,
        complete=True,source_roles_unchanged=True,release_authority=False)


def _proposal(board,request,deadline):
    live={force._uid(t):t for t in board.GetTracks()};pads={force._uid(p):p for f in board.GetFootprints() for p in f.Pads()}
    old=[live[u] for u in request['source_track_uuids']];at=request['at_nm'];face=request['layer'];width=old[0].GetWidth()
    far=[t.GetEnd() if tuple(t.GetStart())==tuple(at) else t.GetStart() for t in old]
    vectors=[(p.x-at[0],p.y-at[1]) for p in far]
    source_web={u:_contact_radius(pads[u],old,face,width,deadline) for u in request['anchor_pad_uuids']}
    if any(r<=0 for r in source_web.values()):raise ValueError('positive_source_native_pad_contact_web_required')
    trials=[];seen=set()
    for maximum in (2000000,1000000,600000,200000,100000,50000):
        if time.monotonic()>=deadline:raise ValueError('pad_corner_proposal_deadline')
        step=coordinate_inset(*vectors,maximum_nm=maximum,minimum_nm=20000)
        if step is None or step in seen:continue
        seen.add(step)
        inner=[pcbnew.VECTOR2I(at[0]+(step if v[0]>0 else -step if v[0]<0 else 0),
            at[1]+(step if v[1]>0 else -step if v[1]<0 else 0)) for v in vectors]
        trial=dict(inset_nm=step,accepted=False);trials.append(trial)
        if (not fr._edge_leg_clear(board,inner[0],inner[1],(width+1)//2) or
                not fr._tap_foreign_clear(board,inner[0],inner[1],width,face,200000,{old[0].GetNetCode()})):
            trial['refusal']='foreign_copper_hole_rule_area_or_edge';continue
        legs=[(far[0],inner[0]),(inner[0],inner[1]),(inner[1],far[1])];new=[]
        for x,y in legs:
            t=old[0].Duplicate();t.SetStart(x);t.SetEnd(y);new.append(t)
        contacts=preserve_contacts(board,old,[t.GetEffectiveShape(face) for t in new],layer_id=face,
            net_code=old[0].GetNetCode(),deadline_monotonic=deadline,max_items=16384)
        if not contacts['ok']:trial['refusal']=contacts['reason'];continue
        web={u:_contact_radius(pads[u],new,face,width,deadline) for u in source_web}
        if any(web[u]<source_web[u] for u in source_web):
            trial['refusal']='native_pad_contact_web_would_shrink';continue
        try:visible=material._visible_removed(board,old,new,set(request['source_track_uuids']),deadline=deadline)
        except ValueError as exc:trial['refusal']=str(exc);continue
        trial['accepted']=True
        return dict(request=request,legs_nm=[dict(start_nm=list(x),end_nm=list(y)) for x,y in legs],
            width_nm=width,locked=bool(old[0].IsLocked()),inset_nm=step,trials=trials,
            old_native_anchor_contact_radius_nm=source_web,new_native_anchor_contact_radius_nm=web,
            native_source_contacts=contacts,actual_visible_native_material_removed=visible,
            contact_radius_is_native_geometry_witness_not_current_or_release_qualification=True)
    raise ValueError('no_visible_full_width_contact_preserving_pad_miter')


def discover(board,source,*,board_hint,allow_locked_source=False):
    deadline=time.monotonic()+10.;inventory=_candidates(board,source,board_hint,allow_locked_source,deadline)
    good=[];refusals=[]
    for request in inventory['requests']:
        try:proposal=_proposal(board,request,deadline);good.append(request)
        except ValueError as exc:refusals.append(dict(request=request,reason=str(exc)))
    if time.monotonic()>=deadline:raise ValueError('pad_corner_complete_inventory_deadline')
    return dict(inventory,requests=good,refusals=refusals,source_geometry_or_pad_or_barrel_changed=False)


def plan(board,source,requests,*,board_hint,allow_locked_source=False):
    if type(requests) is not list or not 1<=len(requests)<=8:raise ValueError('bounded_pad_corner_batch_required')
    deadline=time.monotonic()+10.;inventory=_candidates(board,source,board_hint,allow_locked_source,deadline)
    if (any(r not in inventory['requests'] for r in requests) or
            len({u for r in requests for u in r['source_track_uuids']})!=2*len(requests)):
        raise ValueError('literal_disjoint_source_pad_corner_requests_required')
    proposals=[_proposal(board,r,deadline) for r in requests]
    return dict(schema=1,source_sha256=force._hash(Path(source)),source_binding=binding._source_binding(board),
        requests=json.loads(json.dumps(requests)),corners=proposals,allow_locked_source=allow_locked_source,
        old_pad_and_barrel_geometry_unchanged=True,ordinary_role_override=False,release_authority=False)


def materialize(board,source,proposal,*,board_hint):
    if plan(board,source,proposal['requests'],board_hint=board_hint,
            allow_locked_source=proposal['allow_locked_source'])!=proposal:
        raise ValueError('stale_or_forged_native_pad_corner_plan')
    live={force._uid(t):t for t in board.GetTracks()};retired=[];added=[]
    for corner in proposal['corners']:
        old=[live[u] for u in corner['request']['source_track_uuids']]
        for i,leg in enumerate(corner['legs_nm']):
            t=old[0 if i<2 else 1].Duplicate();t.m_Uuid.Clone(pcbnew.KIID())
            t.SetStart(pcbnew.VECTOR2I(*leg['start_nm']));t.SetEnd(pcbnew.VECTOR2I(*leg['end_nm']));board.Add(t);added.append(force._uid(t))
        retired+=old
    retired_ids=sorted(force._uid(t) for t in retired)
    discard_items(board,retired);additive._ground_refill(board)
    return dict(retired_track_uuids=retired_ids,added_native_uuids=sorted(added),
        corners=len(proposal['corners']),new_vias=0,new_holes=0,pads_moved=0,release_authority=False)


def receive(source,candidate,proposal,*,board_hint):
    result=dict(ok=False,complete=False,errors=[],ordinary_role_override=False,current_qualified=False,release_authority=False)
    try:
        source,candidate=map(Path,(source,candidate));epoch=force._code_identity()
        families=[force._family(p,board_hint) for p in (source,candidate)];parent=pcbnew.LoadBoard(str(source))
        if plan(parent,source,proposal['requests'],board_hint=board_hint,
                allow_locked_source=proposal['allow_locked_source'])!=proposal:
            raise ValueError('saved_source_pad_corner_plan_changed')
        if (force._sidecars(source)!=force._sidecars(candidate) or
                force._preservation_snapshot(source)[1]!=force._preservation_snapshot(candidate)[1]):
            raise ValueError('pad_corner_source_metadata_or_sidecars_changed')
        _,old=additive._nodes(source);got_root,got=additive._nodes(candidate)
        retired=set(old)-set(got);added=set(got)-set(old)
        if retired!={u for r in proposal['requests'] for u in r['source_track_uuids']}:
            raise ValueError('exact_pad_corner_source_retirement_required')
        with tempfile.TemporaryDirectory(prefix='cec-native-pad-corner-') as tmp:
            path=force._copy_family(source,Path(tmp)/'expected');expected=pcbnew.LoadBoard(str(path))
            fresh=plan(expected,path,proposal['requests'],board_hint=board_hint,
                allow_locked_source=proposal['allow_locked_source'])
            made=materialize(expected,path,fresh,board_hint=board_hint);field._save_field_snapshot(expected,path)
            want_root,want=additive._nodes(path);new_ids=set(want)-set(old)
            if (signatures._header(want_root,want)!=signatures._header(got_root,got) or
                    set(want)&set(old)!=set(got)&set(old) or any(syntax._freeze(want[u])!=syntax._freeze(got[u]) for u in set(want)&set(old)) or
                    Counter(signatures._signature(want[u]) for u in new_ids)!=Counter(signatures._signature(got[u]) for u in added)):
                raise ValueError('exact_independent_saved_pad_corner_replay_differs')
        proof=ordinary.receive(source,candidate,board_hint=board_hint,retired_track_uuids=sorted(retired),
            allow_locked_track_uuids=sorted(retired),timeout_s=10.)
        result['independent_ordinary_source_delta_receiving']=proof
        if not proof['ok'] or not proof['complete']:raise ValueError('ordinary_pad_corner_receiving_refused:'+str(proof['errors']))
        child=pcbnew.LoadBoard(str(candidate));live={force._uid(t):t for t in parent.GetTracks()};incoming={force._uid(t):t for t in child.GetTracks()}
        delta=(sum(live[u].GetLength() for u in retired)-sum(incoming[u].GetLength() for u in added))/1e6
        if delta<=0:raise ValueError('native_pad_corner_must_strictly_shorten_actual_tracks')
        craft=quality.analyze_board(child,track_uuid_scope=added)
        if not craft['geometry_ok'] or not craft['craft_ok']:raise ValueError('pad_corner_canonical_craft_refused')
        if epoch!=force._code_identity() or families!=[force._family(p,board_hint) for p in (source,candidate)]:
            raise ValueError('pad_corner_source_candidate_or_code_changed')
        result.update(ok=True,complete=True,code_identity=epoch,source_sha256=force._hash(source),candidate_sha256=force._hash(candidate),
            source_family_and_code_unchanged=True,retired_track_uuids=sorted(retired),added_native_uuids=sorted(added),
            corners=made['corners'],saved_trace_length_mm=delta,native_anchor_contact_radius_non_decreasing=True,
            per_corner_native_contacts_and_visible_material_rederived=True,new_vias=0,new_holes=0,pads_moved=0,
            default_pad_and_via_launch_protection_unchanged=True,
            whole_native_current_fields_absolute_Kelvin_pair_stack_and_release_still_required=True)
    except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:result['errors'].append(type(exc).__name__+':'+str(exc))
    return result
