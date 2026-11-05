"""Retire redundant source-typed scalar signal paths, never a sole connection.

Local angle audits cannot see same-net topological cycles. This owner uses
the immutable source's actual GPIO/package and field semantics, retains all
lands, vias, force/pair/ground copper and settings, and proves every surviving
native component plus every source pad-to-pad explicit path non-worse.
No signal role, GPIO mode, load budget, thermal or release gate is inferred.
"""
import collections
import math
from pathlib import Path
import tempfile
import time
import pcbnew
import cec_sensitive_scalar_corner_stage as sensitive
import cec_force_current as force
import cec_field_coupling as field
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_ordinary_route_receiving as ordinary
import cec_decoupler_cell as cells
import cec_fab_profile as fab
import cec_route_quality as quality
from cec_native_items import discard_items


def _deadline(seconds):
    if type(seconds) not in (int,float) or not math.isfinite(seconds) or not 0<seconds<=10.:
        raise ValueError('bounded_source_sensitive_redundancy_budget_required')
    return time.monotonic()+seconds


def _chain(edges):
    incidence=collections.defaultdict(list)
    for t in edges:
        for p in (tuple(t.GetStart()),tuple(t.GetEnd())):incidence[p].append(t)
    ports=sorted(p for p,rows in incidence.items() if len(rows)==1)
    if len(ports)!=2 or any(len(rows)>2 for rows in incidence.values()):
        raise ValueError('one_bounded_two_port_sensitive_source_path_required')
    points=[ports[0]];seen=set()
    while points[-1]!=ports[1]:
        rows=[t for t in incidence[points[-1]] if force._uid(t) not in seen]
        if len(rows)!=1 or len(seen)>=16:raise ValueError('contiguous_sensitive_source_path_required')
        t=rows[0];seen.add(force._uid(t));a,z=tuple(t.GetStart()),tuple(t.GetEnd())
        points.append(z if points[-1]==a else a)
    if len(seen)!=len(edges):raise ValueError('no_unlisted_or_disconnected_sensitive_path_material')
    return points


def _terminals(before,after,net,deadline):
    pads=[p for fp in before.GetFootprints() for p in fp.Pads() if p.GetNetname()==net]
    following={force._uid(p):p for fp in after.GetFootprints() for p in fp.Pads() if p.GetNetname()==net}
    if not 2<=len(pads)<=16 or {force._uid(p) for p in pads}!=set(following):
        raise ValueError('bounded_complete_actual_sensitive_terminal_inventory_required')
    rows=[]
    for i,left in enumerate(pads):
        for right in pads[i+1:]:
            if time.monotonic()>=deadline:raise ValueError('sensitive_terminal_path_budget_exhausted')
            old=cells._shortest_track_path_mm(before,left,right)
            new=cells._shortest_track_path_mm(after,following[force._uid(left)],following[force._uid(right)])
            if old is None or new is None or not all(math.isfinite(v) and v>=0 for v in (old,new)):
                raise ValueError('complete_explicit_sensitive_terminal_path_required')
            if new>old+1e-9:raise ValueError('sensitive_retirement_would_lengthen_a_terminal_path')
            rows.append(dict(pads=sorted((force._uid(left),force._uid(right))),before_mm=old,after_mm=new))
    return sorted(rows,key=lambda q:q['pads'])


def _retained_ports(board,cut,points):
    ids={force._uid(t) for t in cut};net=cut[0].GetNetname();face=cut[0].GetLayer()
    copper=[t for t in board.GetTracks() if force._uid(t) not in ids and t.GetNetname()==net and t.IsOnLayer(face)]
    pads=[p for fp in board.GetFootprints() for p in fp.Pads() if p.GetNetname()==net and p.IsOnLayer(face)]
    shapes=[t.GetEffectiveShape(face) for t in copper]
    for port in (points[0],points[-1]):
        point=pcbnew.VECTOR2I(*port)
        if any(shape.Collide(point,0) for shape in shapes):continue
        if any(p.HitTest(point) and any(shape.Collide(p.GetEffectiveShape(face),0) for shape in shapes) for p in pads):continue
        return False
    return True


def _native_net_parts(board,net,retired=()):
    """Cheap exact-net native screen, never whole-board receiving authority."""
    retired=set(retired)
    items=[p for fp in board.GetFootprints() for p in fp.Pads() if p.GetNetname()==net]
    items += [t for t in board.GetTracks() if t.GetNetname()==net]
    if len(items)>2048:raise ValueError('bounded_sensitive_native_net_screen_required')
    conn=pcbnew.CONNECTIVITY_DATA();remaining={}
    for item in items:
        uid=force._uid(item)
        if uid in retired:continue
        if not conn.Add(item):raise ValueError('sensitive_native_net_screen_item_refused')
        remaining[uid]=item
    parts=[]
    while remaining:
        uid=min(remaining);reached={uid}|{force._uid(i) for i in conn.GetConnectedItems(remaining[uid])}
        own=set(remaining)&reached;parts.append(own)
        for u in own:del remaining[u]
    return parts


def trim_schema(value):
    if value is None:return
    keys={'source_track_uuid','keep_endpoint_nm','contact_point_nm','retained_contact_track_uuid'}
    if (type(value) is not dict or set(value)!=keys
            or any(type(value[k]) is not str or not value[k] for k in ('source_track_uuid','retained_contact_track_uuid'))
            or any(type(value[k]) is not list or len(value[k])!=2 or any(type(v) is not int or abs(v)>2000000000 for v in value[k])
                for k in ('keep_endpoint_nm','contact_point_nm'))):
        raise ValueError('exact_bounded_source_contained_sensitive_trim_required')


def _trim(board,ids,value,*,new_uuid=None):
    """Derive only a source subset ending at a retained exact line crossing."""
    trim_schema(value)
    if value is None:
        if new_uuid is not None:raise ValueError('no_trim_cannot_add_native_material')
        return None
    live={force._uid(t):t for t in board.GetTracks()}
    original=live.get(value['source_track_uuid']);other=live.get(value['retained_contact_track_uuid'])
    if (original is None or other is None or force._uid(original) not in ids or force._uid(other) in ids
            or original.GetClass()!='PCB_TRACK' or other.GetClass()!='PCB_TRACK'
            or original.GetNetCode()!=other.GetNetCode() or original.GetLayer()!=other.GetLayer()
            or other.GetWidth()<original.GetWidth()):
        raise ValueError('actual_source_trim_and_retained_same_face_contact_required')
    keep=tuple(value['keep_endpoint_nm']);at=tuple(value['contact_point_nm'])
    endpoints=[tuple(original.GetStart()),tuple(original.GetEnd())]
    if keep not in endpoints:raise ValueError('trim_must_retain_an_exact_original_endpoint')
    def on_line(t,p,*,strict):
        a,z=tuple(t.GetStart()),tuple(t.GetEnd());d=tuple(z[i]-a[i] for i in (0,1));q=tuple(p[i]-a[i] for i in (0,1))
        projection=sum(x*y for x,y in zip(d,q));length2=sum(x*x for x in d)
        return length2>0 and d[0]*q[1]==d[1]*q[0] and (0<projection<length2 if strict else 0<=projection<=length2)
    if (not on_line(original,at,strict=True) or not on_line(other,at,strict=False)
            or original.GetLength()/1e6-math.dist(keep,at)/1e6<=.01):
        raise ValueError('exact_interior_source_crossing_and_meaningful_trim_required')
    if not other.GetEffectiveShape(other.GetLayer()).Collide(pcbnew.VECTOR2I(*at),0):
        raise ValueError('retained_native_contact_not_physically_present')
    replacement=original.Duplicate();replacement.m_Uuid.Clone(pcbnew.KIID(new_uuid) if new_uuid else pcbnew.KIID())
    if endpoints[0]==keep:replacement.SetEnd(pcbnew.VECTOR2I(*at))
    else:replacement.SetStart(pcbnew.VECTOR2I(*at))
    if not quality.is_canonical_stroke(replacement.GetStart(),replacement.GetEnd(),tolerance_nm=0):
        raise ValueError('source_contained_trim_must_be_literal_octilinear')
    # Equal source width on a literal centreline subset is full capsule
    # containment. The unchanged, at-least-as-wide crossing contains its
    # round endpoint, avoiding the new overhanging bubble/stub failure.
    return replacement


def plan(source,*,board_hint,retired_track_uuids,allow_locked_source=False,timeout_s=10.,source_contained_trim=None):
    deadline=_deadline(timeout_s)
    if type(allow_locked_source) is not bool or type(board_hint) is not str or not board_hint:
        raise ValueError('explicit_sensitive_redundant_source_identity_required')
    ids=ordinary._ids(retired_track_uuids,'sensitive_redundant_tracks',16)
    trim_schema(source_contained_trim)
    if not ids:raise ValueError('nonempty_sensitive_source_retirement_required')
    source=Path(source).resolve();digest=force._hash(source)
    b=pcbnew.LoadBoard(str(source));live={force._uid(t):t for t in b.GetTracks()}
    if not ids<=live.keys():raise ValueError('actual_source_sensitive_tracks_required')
    cut=[live[u] for u in sorted(ids)]
    if any(t.GetClass()!='PCB_TRACK' for t in cut):raise ValueError('no_sensitive_barrel_or_arc_retirement')
    signatures={(str(t.GetNetname()),int(t.GetLayer()),t.GetWidth()) for t in cut}
    if len(signatures)!=1:raise ValueError('one_uniform_same_face_sensitive_path_required')
    net,face,width=next(iter(signatures));witness=sensitive.eligible_nets(b,source,board_hint)
    allowed={int(b.GetLayerID(n)) for n in fab.routing_layers(b,include_power=False)}
    if (net not in witness or face not in allowed or not 0<width<500000
            or any(t.GetParentGroup() or t.HasSolderMask() or t.IsLocked() and not allow_locked_source for t in cut)):
        raise ValueError('source_sensitive_nonpower_unowned_signal_path_required')
    points=_chain(cut);length=sum(t.GetLength() for t in cut)/1e6
    if not .01<length<=25.:raise ValueError('bounded_meaningful_sensitive_path_length_required')
    pads=[p for fp in b.GetFootprints() for p in fp.Pads() if p.GetNetname()==net]
    if not _retained_ports(b,cut,points):
        raise ValueError('each_source_sensitive_path_port_needs_retained_native_copper')
    conn=pcbnew.CONNECTIVITY_DATA()
    for item in [*pads,*[t for t in b.GetTracks() if t.GetNetname()==net]]:
        if not conn.Add(item):raise ValueError('source_sensitive_native_graph_refused')
    reached={force._uid(t) for t in conn.GetConnectedItems(cut[0])}
    if not reached&{q['pad_uuid'] for q in witness[net]}:
        raise ValueError('actual_retired_component_has_no_selected_GPIO_terminal')
    after=pcbnew.LoadBoard(str(source));replacement=_trim(after,ids,source_contained_trim)
    discard_items(after,[t for t in after.GetTracks() if force._uid(t) in ids])
    if replacement is not None:after.Add(replacement)
    before_parts=ordinary._partition(b,deadline,retired_uuids=ids)
    after_parts=ordinary._partition(after,deadline,retained_keys=set().union(*before_parts))
    if {frozenset(p) for p in before_parts}!={frozenset(p) for p in after_parts}:
        raise ValueError('sensitive_cut_loses_or_changes_surviving_native_component')
    distances=_terminals(b,after,net,deadline)
    if time.monotonic()>=deadline or force._hash(source)!=digest:
        raise ValueError('sensitive_redundancy_source_changed_or_budget_exhausted')
    return dict(source=str(source),source_sha256=digest,board_hint=board_hint,net=net,layer=face,width_nm=width,
        retired_track_uuids=sorted(ids),source_points_nm=[list(p) for p in points],
        retired_length_mm=length-(replacement.GetLength()/1e6 if replacement is not None else 0.),
        retired_source_centerline_mm=length,source_contained_trim=source_contained_trim,
        source_contained_replacement_length_mm=replacement.GetLength()/1e6 if replacement is not None else 0.,
        allow_locked_source=allow_locked_source,source_pin_witnesses=witness[net],terminal_paths=distances,
        every_original_retained_native_component_identical=True,
        no_current_budget_GPIO_mode_or_ordinary_reclassification=True,release_authority=False)


def construct(proposal,*,new_track_uuid=None):
    actual=plan(proposal['source'],board_hint=proposal['board_hint'],retired_track_uuids=proposal['retired_track_uuids'],
        allow_locked_source=proposal['allow_locked_source'],source_contained_trim=proposal.get('source_contained_trim'))
    if actual!=proposal:raise ValueError('sensitive_redundant_proposal_stale_or_forged')
    b=pcbnew.LoadBoard(proposal['source']);ids=set(proposal['retired_track_uuids'])
    replacement=_trim(b,ids,proposal.get('source_contained_trim'),new_uuid=new_track_uuid)
    discard_items(b,[t for t in b.GetTracks() if force._uid(t) in ids])
    if replacement is not None:b.Add(replacement)
    return b


def receive(source,candidate,*,board_hint,retired_track_uuids,allow_locked_source=False,timeout_s=10.,source_contained_trim=None):
    r=dict(ok=False,complete=False,errors=[],ordinary_reclassification=False,current_qualified=False,
        GPIO_mode_or_load_assumed=False,routing_admitted=False,fab_ready=False,release_authority=False,
        full_original_parent_current_field_Kelvin_native_and_release_receiving_still_required=True)
    try:
        deadline=_deadline(timeout_s);source,candidate=[Path(p).resolve() for p in (source,candidate)]
        epoch=force._code_identity();families=[force._family(p,board_hint) for p in (source,candidate)]
        proposal=plan(source,board_hint=board_hint,retired_track_uuids=retired_track_uuids,
            allow_locked_source=allow_locked_source,source_contained_trim=source_contained_trim,
            timeout_s=max(.001,min(10.,deadline-time.monotonic())))
        _,old=additive._nodes(source);_,new=additive._nodes(candidate);ids=set(proposal['retired_track_uuids'])
        incoming=new.keys()-old.keys()
        if old.keys()-new.keys()!=ids or len(incoming)!=(1 if source_contained_trim is not None else 0):
            raise ValueError('exact_sensitive_path_cut_and_optional_one_source_subset_required')
        parent,child=[pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
        ground={force._uid(z) for z in parent.Zones() if not z.GetIsRuleArea() and z.GetNetname()=='GND'}
        if any(syntax._freeze(node)!=syntax._freeze(new[u]) for u,node in old.items() if u not in ids|ground):
            raise ValueError('sensitive_retirement_changed_retained_original_native_material')
        if force._sidecars(source)!=force._sidecars(candidate) or force._preservation_snapshot(source)[1]!=force._preservation_snapshot(candidate)[1]:
            raise ValueError('source_sensitive_parts_rules_or_sidecars_changed')
        with tempfile.TemporaryDirectory(prefix='cec-sensitive-redundant-') as tmp:
            path=force._copy_family(source,Path(tmp)/'exact-source-minus-path')
            expected=construct(proposal,new_track_uuid=next(iter(incoming),None))
            additive._ground_refill(expected);field._save_field_snapshot(expected,path)
            _,nodes=additive._nodes(path)
            if nodes.keys()!=new.keys() or any(syntax._freeze(nodes[u])!=syntax._freeze(new[u]) for u in new):
                raise ValueError('source_exact_sensitive_cut_and_native_ground_replay_differs')
        before=ordinary._partition(parent,deadline,retired_uuids=ids)
        after=ordinary._partition(child,deadline,retained_keys=set().union(*before))
        if {frozenset(p) for p in before}!={frozenset(p) for p in after}:
            raise ValueError('saved_sensitive_cut_changes_native_partition')
        paths=_terminals(parent,child,proposal['net'],deadline)
        if (paths!=proposal['terminal_paths'] or time.monotonic()>=deadline or epoch!=force._code_identity()
                or families!=[force._family(p,board_hint) for p in (source,candidate)]):
            raise ValueError('saved_sensitive_source_paths_family_or_epoch_changed')
        r.update(ok=True,complete=True,code_identity=epoch,source_sha256=force._hash(source),candidate_sha256=force._hash(candidate),
            net=proposal['net'],retired_track_uuids=sorted(ids),added_native_uuids=sorted(incoming),proposal=proposal,
            replacement_is_only_exact_source_capsule_subset=source_contained_trim is not None,
            retired_length_mm=proposal['retired_length_mm'],source_family_and_code_unchanged=True,
            every_retained_native_component_identical=True,every_source_pad_pair_path_proved_nonworse=True)
    except Exception as exc:r['errors'].append(type(exc).__name__+':'+str(exc))
    return r


def discover(source,*,board_hint,max_candidates=16,allow_locked_source=False,timeout_s=10.,stop_after_first=False):
    deadline=_deadline(timeout_s)
    if (type(max_candidates) is not int or not 1<=max_candidates<=32 or type(allow_locked_source) is not bool
            or type(stop_after_first) is not bool):
        raise ValueError('bounded_sensitive_redundant_discovery_required')
    source=Path(source).resolve();digest=force._hash(source);b=pcbnew.LoadBoard(str(source))
    eligible=sensitive.eligible_nets(b,source,board_hint);tracks=list(b.GetTracks())
    if len(tracks)>16384:raise ValueError('bounded_native_sensitive_material_inventory_required')
    pads=[p for fp in b.GetFootprints() for p in fp.Pads()]
    candidate_edges=[t for t in tracks if t.GetClass()=='PCB_TRACK' and t.GetNetname() in eligible
        and 0<t.GetWidth()<500000 and not t.GetParentGroup() and not t.HasSolderMask()
        and (allow_locked_source or not t.IsLocked())]
    lengths={force._uid(t):t.GetLength() for t in candidate_edges}
    incidence=collections.defaultdict(list)
    for t in candidate_edges:
        for at in (tuple(t.GetStart()),tuple(t.GetEnd())):
            incidence[(str(t.GetNetname()),int(t.GetLayer()),t.GetWidth(),at)].append(t)
    chains={};enumeration_complete=True
    for first in candidate_edges:
        if time.monotonic()>=deadline or len(chains)>=4096:
            enumeration_complete=False;break
        for start in (tuple(first.GetStart()),tuple(first.GetEnd())):
            points=[start];selected=[];current=first
            while len(selected)<16:
                uid=force._uid(current)
                if uid in selected:break
                selected.append(uid);ends=(tuple(current.GetStart()),tuple(current.GetEnd()))
                at=ends[1] if points[-1]==ends[0] else ends[0];points.append(at)
                if len(selected)>=1:
                    ids=tuple(sorted(selected));chains[ids]=sum(lengths[u] for u in ids)
                key=(str(first.GetNetname()),int(first.GetLayer()),first.GetWidth(),at)
                rows=[t for t in incidence[key] if force._uid(t) not in selected]
                if len(rows)!=1:break
                point=pcbnew.VECTOR2I(*at)
                if any(p.GetNetCode()==first.GetNetCode() and p.IsOnLayer(first.GetLayer()) and p.HitTest(point) for p in pads):break
                current=rows[0]
    trials=[];plans=[];screened=collections.Counter();live={force._uid(t):t for t in candidate_edges};net_parts={}
    for ids,length in sorted(chains.items(),key=lambda q:(-q[1],q[0])):
        if len(trials)>=max_candidates or time.monotonic()>=deadline:break
        if not 10000<length<=25000000:
            screened['outside_existing_length_work_bound']+=1;continue
        cut=[live[u] for u in ids]
        try:points=_chain(cut)
        except ValueError:
            screened['not_exact_two_port_path']+=1;continue
        if not _retained_ports(b,cut,points):
            screened['port_has_no_retained_native_copper']+=1;continue
        net=str(cut[0].GetNetname())
        if net not in net_parts:net_parts[net]=_native_net_parts(b,net)
        before_parts=[part-set(ids) for part in net_parts[net] if part-set(ids)]
        after_parts=_native_net_parts(b,net,ids)
        if {frozenset(part) for part in before_parts}!={frozenset(part) for part in after_parts}:
            screened['exact_selected_net_native_component_split']+=1;continue
        row=dict(retired_track_uuids=list(ids),length_mm=length/1e6);trials.append(row)
        try:
            proposal=plan(source,board_hint=board_hint,retired_track_uuids=list(ids),allow_locked_source=allow_locked_source,
                timeout_s=max(.001,min(10.,deadline-time.monotonic())))
            plans.append(proposal);row['source_native_redundancy_proved']=True
            if stop_after_first:break
        except Exception as exc:row['refusal']=type(exc).__name__+':'+str(exc)
    if force._hash(source)!=digest:raise ValueError('source_sensitive_discovery_mutated_or_source_changed')
    return dict(source=str(source),source_sha256=digest,plans=plans,trials=trials,
        complete=enumeration_complete and time.monotonic()<deadline,syntactic_source_paths=len(chains),
        cheap_source_rejections_before_native_proof_budget=dict(screened),
        finite_native_frontier_limit=max_candidates,finite_frontier_limit_is_not_global_exhaustion=True,
        stop_after_first_proved_plan=stop_after_first,
        global_no_path_or_all_loops_absent_not_claimed=True,mutation_or_retirement_admission_granted=False)
