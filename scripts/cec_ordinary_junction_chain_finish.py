"""Source-owned ordinary junction chains; never a cosmetic launch waiver.

Near-parallel duplicate stems and tiny two-leg jogs can be part of a larger
native junction. Own a bounded complete source cut, keep every external
boundary/surviving conductor partition, and independently reconstruct the
saved subtraction/replacement. No pad, barrel, layer, width, electrical role,
current contract or default corner-contact policy is changed.
"""
from collections import defaultdict
import json,math,re,tempfile,time,uuid
from pathlib import Path
import pcbnew
import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_full_current_corner_finish as visible
import cec_ground_return_preservation as ground
import cec_ordinary_route_receiving as ordinary
import cec_rectilinear_copper as geometry
import cec_route_quality as quality
from cec_octilinear_corner import kind
from cec_native_items import discard_items

SCOPE='bounded_exact_source_ordinary_native_junction_chain'


def _settings(allow_locked_source):
    if type(allow_locked_source) is not bool:
        raise ValueError('explicit_junction_chain_lock_scope_required')


def _paths(a,b):
    dx,dy=[b[i]-a[i] for i in (0,1)];step=min(abs(dx),abs(dy))
    u=(dx>0)-(dx<0);v=(dy>0)-(dy<0);result=[]
    for point in ((a[0]+u*step,a[1]+v*step),(b[0]-u*step,b[1]-v*step)):
        path=[]
        for p in (a,point,b):
            if not path or tuple(p)!=tuple(path[-1]):path.append(list(p))
        if len(path)>=2 and path not in result:result.append(path)
    return result


def _chain_ports(tracks):
    endpoints=defaultdict(list)
    for t in tracks:
        for p in (tuple(t.GetStart()),tuple(t.GetEnd())):endpoints[p].append(t)
    ports=sorted(p for p,items in endpoints.items() if len(items)==1)
    if len(ports)!=2 or any(len(v)>2 for v in endpoints.values()):return None
    pending={force._uid(t) for t in tracks};queue=[tracks[0]];pending.remove(force._uid(tracks[0]))
    while queue:
        t=queue.pop()
        for p in (tuple(t.GetStart()),tuple(t.GetEnd())):
            for other in endpoints[p]:
                uid=force._uid(other)
                if uid in pending:pending.remove(uid);queue.append(other)
    return ports if not pending else None


def discover(board,source,*,board_hint,allow_locked_source=False):
    _settings(allow_locked_source);source=Path(source).resolve();deadline=time.monotonic()+10.
    if (type(board_hint) is not str or not board_hint or not source.is_file()
            or Path(board.GetFileName()).resolve()!=source):
        raise ValueError('literal_saved_junction_chain_source_required')
    eligible=ordinary.eligible_nets(board,source,board_hint);all_tracks=list(board.GetTracks())
    if len(all_tracks)+sum(f.GetPadCount() for f in board.GetFootprints())>16384:
        raise ValueError('bounded_native_junction_chain_inventory_required')
    owned={force._uid(t) for g in board.Groups() for t in g.GetItems()}
    def usable(t):
        return (t.GetClass()=='PCB_TRACK' and str(t.GetNetname()) in eligible
            and int(t.GetLayer()) in (pcbnew.F_Cu,pcbnew.B_Cu)
            and not t.GetParentGroup() and force._uid(t) not in owned and not t.HasSolderMask()
            and (not t.IsLocked() or allow_locked_source) and 0<t.GetWidth()<500000
            and 0<t.GetLength()<=32000000
            and quality.is_canonical_stroke(tuple(t.GetStart()),tuple(t.GetEnd()),tolerance_nm=0))
    tracks=[t for t in all_tracks if usable(t)];live={force._uid(t):t for t in tracks}
    by_point=defaultdict(list)
    for t in tracks:
        for p in (tuple(t.GetStart()),tuple(t.GetEnd())):
            by_point[str(t.GetNetname()),int(t.GetLayer()),p].append(t)
    requests=[];roots=[];seen=set()
    def offer(root,cut,points):
        selected=[live[u] for u in sorted(cut)]
        if (not 1<=len(selected)<=8 or sum(t.GetLength() for t in selected)>64000000
                or len({(t.GetNetname(),int(t.GetLayer()),t.GetWidth(),bool(t.IsLocked())) for t in selected})!=1):return
        width=selected[0].GetWidth();old=sum(t.GetLength() for t in selected)
        if points and any(max(abs(b[i]-a[i]) for i in (0,1))<max(20000,width)
                for a,b in zip(points,points[1:])):return
        length=sum(math.dist(a,b) for a,b in zip(points,points[1:]))
        if length>=old or old-length<1000:return
        identity=(tuple(sorted(cut)),tuple(map(tuple,points)))
        if identity in seen:return
        seen.add(identity)
        requests.append(dict(root=root,net=root['net'],layer=root['layer'],width_nm=width,
            retired_track_uuids=sorted(cut),mode='reflow' if points else 'redundant_cut',
            replacement_points_nm=points,estimated_centerline_removed_nm=old-length))
        if len(requests)>128:raise ValueError('bounded_junction_chain_request_inventory_required')
    for (net,face,at),edges in sorted(by_point.items()):
        if time.monotonic()>=deadline:raise ValueError('junction_chain_source_inventory_deadline')
        if len(edges)!=2 or len({t.GetWidth() for t in edges})!=1:continue
        far=[t.GetEnd() if tuple(t.GetStart())==at else t.GetStart() for t in edges]
        if kind(*[(p.x-at[0],p.y-at[1]) for p in far]) is None:continue
        bodies=[t for t in tracks if t not in edges and t.GetNetname()==net and int(t.GetLayer())==face
            and t.GetWidth()==edges[0].GetWidth() and t.GetEffectiveShape(face).Collide(pcbnew.VECTOR2I(*at),0)]
        if not 1<=len(bodies)<=2:continue
        root=dict(net=net,layer=face,at_nm=list(at),corner_track_uuids=sorted(force._uid(t) for t in edges),
            native_body_track_uuids=sorted(force._uid(t) for t in bodies));roots.append(root)
        seed={force._uid(t) for t in edges+bodies};selected=[live[u] for u in sorted(seed)]
        ports=_chain_ports(selected)
        if ports is not None:
            variants=[seed]
            for port in ports:
                peers=[t for t in by_point[net,face,port] if force._uid(t) not in seed]
                if len(peers)==1:variants.append(seed|{force._uid(peers[0])})
            for cut in variants:
                ports=_chain_ports([live[u] for u in sorted(cut)])
                if ports is None:continue
                offer(root,cut,[])
                for path in _paths(*ports):offer(root,cut,path)
        else:
            for t in edges:
                d=t.GetEnd()-t.GetStart()
                if any((other.GetEnd().x-other.GetStart().x)*d.y==(other.GetEnd().y-other.GetStart().y)*d.x
                    and other.GetEffectiveShape(face).Collide(t.GetEffectiveShape(face),0) for other in bodies):
                    offer(root,{force._uid(t)},[])
    if time.monotonic()>=deadline:raise ValueError('junction_chain_source_inventory_deadline')
    requests.sort(key=lambda q:(-q['estimated_centerline_removed_nm'],len(q['retired_track_uuids']),
        json.dumps(q,sort_keys=True)))
    return dict(ok=True,complete=True,requests=requests,source_roots=roots,
        source_ordinary_roles_only=True,no_same_net_contact_policy_override=True,
        native_source_boundaries_and_saved_receiving_required=True,release_authority=False)


def plan(source,*,board_hint,request,allow_locked_source=False):
    source=Path(source).resolve();b=pcbnew.LoadBoard(str(source))
    found=discover(b,source,board_hint=board_hint,allow_locked_source=allow_locked_source)
    if type(request) is not dict or request not in found['requests']:
        raise ValueError('literal_source_junction_chain_request_required')
    return json.loads(json.dumps(dict(schema=1,scope=SCOPE,source=str(source),source_sha256=force._hash(source),
        source_family=force._family(source,board_hint),
        board_hint=board_hint,request=request,allow_locked_source=allow_locked_source,
        source_current_or_signal_role_changed=False,new_holes=0,new_vias=0,release_authority=False),allow_nan=False))


def _args(proposal):return {k:proposal[k] for k in ('board_hint','request','allow_locked_source')}


def construct(proposal,*,incoming_uuids=None):
    if plan(proposal['source'],**_args(proposal))!=proposal:
        raise ValueError('stale_or_forged_junction_chain_plan')
    b=pcbnew.LoadBoard(proposal['source']);q=proposal['request'];ids=q['retired_track_uuids']
    live={force._uid(t):t for t in b.GetTracks()};old=[live[u] for u in ids]
    points=q['replacement_points_nm'];count=max(0,len(points)-1)
    if incoming_uuids is None:incoming_uuids=[str(uuid.uuid4()) for _ in range(count)]
    source_uuids=set(re.findall(r'\(uuid\s+"?([0-9a-fA-F-]{36})',Path(proposal['source']).read_text()))
    if (type(incoming_uuids) is not list or len(incoming_uuids)!=count or len(set(incoming_uuids))!=count
            or any(type(u) is not str or str(uuid.UUID(u))!=u for u in incoming_uuids)
            or set(incoming_uuids)&source_uuids):
        raise ValueError('fresh_exact_junction_chain_incoming_ids_required')
    for uid,a,z in zip(incoming_uuids,points,points[1:]):
        t=old[0].Duplicate();t.m_Uuid.Clone(pcbnew.KIID(uid))
        t.SetStart(pcbnew.VECTOR2I(*a));t.SetEnd(pcbnew.VECTOR2I(*z));b.Add(t)
    discard_items(b,old);additive._ground_refill(b)
    return b,dict(retired_track_uuids=ids,added_native_uuids=incoming_uuids,
        mode=q['mode'],new_holes=0,new_vias=0,source_pads_barrels_poses_and_widths_unchanged=True)


def receive(source,candidate,proposal,*,board_hint):
    r=dict(ok=False,complete=False,errors=[],current_authority=False,fab_ready=False,release_authority=False)
    try:
        source,candidate=[Path(p).resolve() for p in (source,candidate)]
        epoch=force._code_identity();families=[force._family(p,board_hint) for p in (source,candidate)]
        if str(source)!=proposal['source'] or board_hint!=proposal['board_hint'] or plan(source,**_args(proposal))!=proposal:
            raise ValueError('saved_source_junction_chain_plan_not_rederived')
        parent,child=[pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
        _,old=additive._nodes(source);_,actual=additive._nodes(candidate);q=proposal['request']
        cut=set(q['retired_track_uuids']);incoming=set(actual)-set(old)
        if set(old)-set(actual)!=cut:raise ValueError('exact_original_junction_chain_cut_required')
        rows={force._uid(t):t for t in child.GetTracks() if force._uid(t) in incoming}
        points=q['replacement_points_nm'];ordered=[]
        for a,z in zip(points,points[1:]):
            matches=[uid for uid,t in rows.items() if t.GetClass()=='PCB_TRACK'
                and list(t.GetStart())==a and list(t.GetEnd())==z]
            if len(matches)!=1:raise ValueError('unique_exact_source_junction_replacement_required')
            ordered.append(matches[0])
        if set(ordered)!=incoming:raise ValueError('unowned_source_junction_chain_addition')
        expected,made=construct(proposal,incoming_uuids=ordered)
        with tempfile.TemporaryDirectory(prefix='cec-junction-chain-exact-') as tmp:
            path=force._copy_family(source,Path(tmp)/'expected');field._save_field_snapshot(expected,path)
            if (force._preservation_snapshot(path)!=force._preservation_snapshot(candidate)
                    or force._sidecars(source)!=force._sidecars(candidate)):
                raise ValueError('entire_saved_junction_chain_reconstruction_differs')
        proof=ordinary.receive(source,candidate,board_hint=board_hint,retired_track_uuids=sorted(cut),
            allow_locked_track_uuids=sorted(cut) if proposal['allow_locked_source'] else [],
            allow_redundant_cut_only=q['mode']=='redundant_cut',timeout_s=10.,max_retired_tracks=8)
        r['independent_original_ordinary_receiving']=proof
        if not proof['ok'] or not proof['complete']:raise ValueError('source_junction_chain_delta_refused:'+str(proof['errors']))
        first,last=[quality.analyze_board(b) for b in (parent,child)]
        if any(last[k]>first[k] for k in ('issue_count','non_octilinear_count')):
            raise ValueError('whole_native_junction_chain_craft_regressed')
        if (not first['power_contours']['complete'] or not last['power_contours']['complete']
                or last['power_contours']['finding_count']>first['power_contours']['finding_count']):
            raise ValueError('whole_native_junction_chain_contours_regressed')
        r['all_source_ground_returns']=ground.receive(parent,child)
        if not r['all_source_ground_returns']['ok'] or not r['all_source_ground_returns']['complete']:
            raise ValueError('source_junction_chain_ground_return_regressed')
        live={force._uid(t):t for t in parent.GetTracks()}
        removed=[live[u] for u in cut];added=[rows[u] for u in ordered]
        delta=(sum(t.GetLength() for t in removed)-sum(t.GetLength() for t in added))/1e6
        if delta<=0:raise ValueError('source_junction_chain_actual_length_not_shorter')
        witness=visible._visible_removed(parent,removed,added,cut,deadline=time.monotonic()+10.)
        if epoch!=force._code_identity() or families!=[force._family(p,board_hint) for p in (source,candidate)]:
            raise ValueError('junction_chain_source_candidate_or_code_changed')
        r.update(ok=True,complete=True,source_sha256=force._hash(source),candidate_sha256=force._hash(candidate),
            code_identity=epoch,retired_track_uuids=sorted(cut),added_native_uuids=ordered,
            source_width_face_and_roles_exact=True,exact_entire_original_source_reconstruction=True,
            saved_trace_length_mm=delta,actual_visible_native_material_removed=witness,
            mode=q['mode'],new_holes=0,new_vias=0,
            whole_native_DRC_current_fields_absolute_Kelvin_pairs_stack_and_release_still_required=True)
    except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:r['errors'].append(type(exc).__name__+':'+str(exc))
    return r
