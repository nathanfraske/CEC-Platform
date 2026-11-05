"""Fixed-port reflow of a positively source-typed sensitive scalar path.

Unlike cosmetic two-edge mitering, this owner can remove a whole monotone
staircase. It does not classify an ADC/GPIO as ordinary, infer firmware mode
or current, move a barrel/part, or own a power/pair/plane route. Every old
native adjacency, surviving component and explicit pad-pair path is proved
again on the exact saved child. Whole current/field/cut/native admission is
still mandatory; no production or fabrication authority is granted here.
"""
import collections
import math
from pathlib import Path
import tempfile
import time
import pcbnew
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_decoupler_cell as cells
import cec_fab_profile as fab
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_ordinary_route_receiving as ordinary
import cec_route_quality as quality
import cec_sensitive_redundant_span as sensitive_path
import cec_sensitive_scalar_corner_stage as sensitive
from cec_native_items import discard_items


def _points(value):
    if (type(value) is not list or not 2<=len(value)<=16
            or any(type(p) not in (list,tuple) or len(p)!=2 or any(type(v) is not int
                or abs(v)>2000000000 for v in p) for p in value)):
        raise ValueError('bounded_literal_sensitive_path_points_required')
    points=[tuple(p) for p in value]
    if len(set(points))!=len(points):raise ValueError('sensitive_path_cannot_repeat_a_vertex')
    for a,b in zip(points,points[1:]):
        if not quality.is_canonical_stroke(a,b,tolerance_nm=0):
            raise ValueError('literal_nonzero_octilinear_sensitive_path_required')
    for a,b,c in zip(points,points[1:],points[2:]):
        u=(b[0]-a[0],b[1]-a[1]);v=(c[0]-b[0],c[1]-b[1])
        dot=sum(x*y for x,y in zip(u,v));cross=u[0]*v[1]-u[1]*v[0]
        if dot<=0 or abs(cross)>dot:
            raise ValueError('sensitive_path_turns_must_not_exceed_45_degrees')
    def cross(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    def on(a,b,p):return cross(a,b,p)==0 and all(min(a[i],b[i])<=p[i]<=max(a[i],b[i]) for i in (0,1))
    for i,(a,b) in enumerate(zip(points,points[1:])):
        for j in range(i+2,len(points)-1):
            c,d=points[j:j+2];ab=[cross(a,b,p) for p in (c,d)];cd=[cross(c,d,p) for p in (a,b)]
            if ((ab[0]*ab[1]<0 and cd[0]*cd[1]<0) or on(a,b,c) or on(a,b,d) or on(c,d,a) or on(c,d,b)):
                raise ValueError('sensitive_path_cannot_self_intersect')
    return points


def _source_contacts(board,cut,deadline):
    ids={force._uid(t) for t in cut};face=cut[0].GetLayer();code=cut[0].GetNetCode();width=cut[0].GetWidth()
    old=[t.GetEffectiveShape(face) for t in cut]
    items=[*board.GetTracks(),*(p for f in board.GetFootprints() for p in f.Pads()),*board.Zones()]
    if len(items)>16384:raise ValueError('sensitive_path_contact_inventory_bound')
    contacts=[]
    for item in items:
        if time.monotonic()>=deadline:raise ValueError('sensitive_path_contact_deadline')
        if force._uid(item) in ids or item.GetNetCode()!=code or not item.IsOnLayer(face):continue
        if item.GetClass()=='ZONE':
            if item.GetIsRuleArea():continue
            if not item.IsFilled() or not item.HasFilledPolysForLayer(face):
                if any(item.GetBoundingBox().Intersects(t.GetBoundingBox()) for t in cut):
                    raise ValueError('source_sensitive_path_adjacent_fill_unknown')
                continue
        shape=item.GetEffectiveShape(face)
        if not any(s.Collide(shape,0) for s in old):continue
        contacts.append((force._uid(item),shape))
    return contacts


def _contacts(board,cut,points,deadline,*,source_contacts=None):
    """New bounded-path contract; the old two-edge corner guard is unchanged.

    Discovery may reuse only immutable, in-memory source contact geometry.
    Independent saved receiving always re-derives the actual source contacts.
    """
    width=cut[0].GetWidth()
    new=[pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*b),width) for a,b in zip(points,points[1:])]
    contacts=_source_contacts(board,cut,deadline) if source_contacts is None else source_contacts
    for uid,shape in contacts:
        if time.monotonic()>=deadline:raise ValueError('sensitive_path_contact_deadline')
        if not any(s.Collide(shape,0) for s in new):
            raise ValueError('sensitive_path_would_lose_native_side_contact:'+uid)
    return sorted(uid for uid,shape in contacts)


def _heading(a,b):
    q=quality.canonical_heading(a,b,tolerance_nm=1000)
    if not q['ok'] or q['family']=='degenerate':raise ValueError('sensitive_path_source_boundary_heading_unknown')
    sign=lambda v:1 if v>0 else -1 if v<0 else 0
    dx,dy=b[0]-a[0],b[1]-a[1]
    return ((sign(dx),0) if q['family']=='0' else (0,sign(dy)) if q['family']=='90' else (sign(dx),sign(dy)))


def _boundary_turns(board,cut,points,deadline):
    ids={force._uid(t) for t in cut};net=cut[0].GetNetCode();face=cut[0].GetLayer();result=[]
    retained=[t for t in board.GetTracks() if t.GetClass()=='PCB_TRACK'
        and force._uid(t) not in ids and t.GetNetCode()==net and t.IsOnLayer(face)]
    for at,next_at in ((points[0],points[1]),(points[-1],points[-2])):
        point=pcbnew.VECTOR2I(*at);peers=[];bodies=[]
        for t in retained:
            if time.monotonic()>=deadline:raise ValueError('sensitive_path_boundary_heading_deadline')
            if not t.GetEffectiveShape(face).Collide(point,0):continue
            ends=[tuple(t.GetStart()),tuple(t.GetEnd())]
            near=[i for i,p in enumerate(ends) if math.dist(at,p)<=1000]
            if len(near)==1:peers.append((t,ends[near[0]],ends[1-near[0]]))
            else:bodies.append(force._uid(t))
        row=dict(at_nm=list(at),retained_endpoint_peers=sorted(force._uid(t) for t,a,b in peers),
            retained_native_body_contacts=sorted(bodies),two_edge_boundary_tangent_required=len(peers)==1 and not bodies)
        if row['two_edge_boundary_tangent_required']:
            t,a,b=peers[0];u=_heading(a,b);v=_heading(at,next_at)
            dot=sum(x*y for x,y in zip(u,v))
            if dot>=0 or 2*dot*dot<sum(x*x for x in u)*sum(x*x for x in v):
                raise ValueError('sensitive_path_new_boundary_hard_turn:'+force._uid(t))
            row.update(retained_outgoing_heading=list(u),new_outgoing_heading=list(v),maximum_path_turn_degrees=45)
        result.append(row)
    return result


def _tangent_paths(source_points):
    """Finite 0/45 source-heading lead-ins, never moved boundary ports."""
    ring=((1,0),(1,1),(0,1),(-1,1),(-1,0),(-1,-1),(0,-1),(1,-1))
    start,end=source_points[0],source_points[-1]
    def leads(at,inside,step):
        direction=_heading(at,inside);distance=math.dist(at,inside)
        if step*math.hypot(*direction)>=distance:return []
        first=tuple(at[i]+step*direction[i] for i in (0,1));rows=[[at,first]]
        index=ring.index(direction)
        for turn in (-1,1):
            steer=ring[(index+turn)%8]
            rows.append([at,first,tuple(first[i]+step*steer[i] for i in (0,1))])
        return rows
    policies=[([start],[end])]
    for step in (100000,250000,500000):
        first=leads(start,source_points[1],step);last=leads(end,source_points[-2],step)
        policies.extend((p,[end]) for p in first);policies.extend(([start],q) for q in last)
        policies.extend((p,q) for p in first for q in last)
    seen=set();result=[]
    for pre,reverse_tail in policies:
        for middle in fr._canonical_45_xy_paths(pre[-1],reverse_tail[-1]):
            path=[*pre[:-1],*middle,*list(reversed(reverse_tail))[1:]]
            points=[]
            for at in path:
                if not points or tuple(at)!=tuple(points[-1]):points.append(list(at))
            key=tuple(map(tuple,points))
            if key in seen:continue
            seen.add(key)
            try:_points(points)
            except ValueError:continue
            if len(points)<len(source_points):result.append(points)
    return sorted(result,key=lambda p:(sum(math.dist(a,b) for a,b in zip(p,p[1:])),len(p),p))


def _clear_path(board,cut,points,deadline,foreign_cache):
    """Native collision rejection, reusable only on an immutable board.

    Discovery can cheaply reject blocked templates before loading another
    board and deriving source roles again. Independent planning/receiving
    always calls this guard on its own freshly loaded source and fresh cache.
    """
    net=str(cut[0].GetNetname());face=cut[0].GetLayer();width=cut[0].GetWidth()
    clearance=max(int(board.GetDesignSettings().m_MinClearance),int(cells._netclass(board,net)['clearance']))
    for a,b in zip(points,points[1:]):
        a,b=pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*b)
        if time.monotonic()>=deadline:raise ValueError('sensitive_path_geometry_deadline')
        if (not fr._edge_leg_clear(board,a,b,(width+1)//2+clearance)
                or not fr._tap_foreign_clear(board,a,b,width,face,clearance,{cut[0].GetNetCode()},foreign_cache=foreign_cache)):
            raise ValueError('sensitive_path_foreign_copper_or_board_edge_clearance')


def plan(source,*,board_hint,retired_track_uuids,points_nm,allow_locked_source=False,timeout_s=10.):
    deadline=sensitive_path._deadline(timeout_s)
    if type(board_hint) is not str or not board_hint or type(allow_locked_source) is not bool:
        raise ValueError('explicit_source_sensitive_path_identity_required')
    ids=ordinary._ids(retired_track_uuids,'source_sensitive_path_tracks',16)
    if not 2<=len(ids)<=16:raise ValueError('bounded_nonempty_source_sensitive_path_required')
    points=_points(points_nm);source=Path(source).resolve();digest=force._hash(source)
    board=pcbnew.LoadBoard(str(source));live={force._uid(t):t for t in board.GetTracks()}
    if not ids<=live.keys():raise ValueError('actual_source_sensitive_path_tracks_required')
    cut=[live[u] for u in sorted(ids)]
    if any(t.GetClass()!='PCB_TRACK' for t in cut):raise ValueError('sensitive_path_cannot_retire_vias_or_arcs')
    kinds={(str(t.GetNetname()),int(t.GetLayer()),t.GetWidth(),bool(t.IsLocked())) for t in cut}
    if len(kinds)!=1:raise ValueError('uniform_sensitive_path_face_width_and_process_required')
    net,face,width,locked=next(iter(kinds));witness=sensitive.eligible_nets(board,source,board_hint)
    grouped={force._uid(i) for g in board.Groups() for i in g.GetItems()}
    allowed={int(board.GetLayerID(n)) for n in fab.routing_layers(board,include_power=False)}
    if (net not in witness or face not in allowed or not 0<width<500000 or locked and not allow_locked_source
            or any(force._uid(t) in grouped or t.GetParentGroup() or t.HasSolderMask() for t in cut)):
        raise ValueError('source_typed_scalar_path_not_power_pair_ground_group_or_implicit_lock')
    original=sensitive_path._chain(cut)
    if [points[0],points[-1]]!=[original[0],original[-1]]:
        raise ValueError('exact_unchanged_sensitive_path_boundary_ports_required')
    before=sum(t.GetLength() for t in cut);after=sum(math.dist(a,b) for a,b in zip(points,points[1:]))
    if not .01e6<before<=25e6 or before-after<=10000 or len(points)>=len(original):
        raise ValueError('strictly_shorter_sensitive_path_with_fewer_native_strokes_required')
    contacts=_contacts(board,cut,points,deadline)
    tangents=_boundary_turns(board,cut,points,deadline)
    conn=pcbnew.CONNECTIVITY_DATA()
    items=[p for f in board.GetFootprints() for p in f.Pads() if p.GetNetname()==net]
    items += [t for t in board.GetTracks() if t.GetNetname()==net]
    if len(items)>2048:raise ValueError('source_sensitive_path_native_net_bound')
    for item in items:
        if time.monotonic()>=deadline or not conn.Add(item):raise ValueError('source_sensitive_path_native_graph_unknown')
    reached={force._uid(t) for t in conn.GetConnectedItems(cut[0])}
    if not reached&{w['pad_uuid'] for w in witness[net]}:
        raise ValueError('source_sensitive_path_has_no_actual_scalar_terminal')
    _clear_path(board,cut,points,deadline,{})
    if force._hash(source)!=digest:raise ValueError('sensitive_path_source_changed')
    return dict(source=str(source),source_sha256=digest,board_hint=board_hint,retired_track_uuids=sorted(ids),
        replacement_points_nm=[list(p) for p in points],source_points_nm=[list(p) for p in original],
        net=net,layer=face,width_nm=width,source_locked=locked,allow_locked_source=allow_locked_source,
        source_pin_witnesses=witness[net],retained_native_contacts=contacts,
        native_boundary_tangents=tangents,
        source_length_nm=before,replacement_length_nm=after,release_authority=False)


def construct(proposal,*,incoming_uuids=None):
    fresh=plan(proposal['source'],board_hint=proposal['board_hint'],retired_track_uuids=proposal['retired_track_uuids'],
        points_nm=proposal['replacement_points_nm'],allow_locked_source=proposal['allow_locked_source'])
    if fresh!=proposal:raise ValueError('stale_or_forged_sensitive_path_proposal')
    if incoming_uuids is not None and (type(incoming_uuids) is not list or len(incoming_uuids)!=len(proposal['replacement_points_nm'])-1
            or len(set(incoming_uuids))!=len(incoming_uuids) or any(type(u) is not str or not u for u in incoming_uuids)):
        raise ValueError('exact_sensitive_path_reconstruction_ids_required')
    board=pcbnew.LoadBoard(proposal['source']);cut=[t for t in board.GetTracks() if force._uid(t) in proposal['retired_track_uuids']]
    exemplar=cut[0].Duplicate();discard_items(board,cut)
    for i,(a,b) in enumerate(zip(proposal['replacement_points_nm'],proposal['replacement_points_nm'][1:])):
        t=exemplar.Duplicate();t.m_Uuid.Clone(pcbnew.KIID(incoming_uuids[i]) if incoming_uuids else pcbnew.KIID())
        t.SetStart(pcbnew.VECTOR2I(*a));t.SetEnd(pcbnew.VECTOR2I(*b));board.Add(t)
    return board


def _preserved_ground_material(before,after,deadline):
    """Every old filled GND polygon survives; no area/distance waiver.

    Exact source reconstruction already retains every original ground land,
    track and barrel. Containment of each old zone fill on each actual copper
    layer therefore preserves EVERY prior surface-return path, even ones a
    bounded shortest-path observer could not find. Added ground material is
    not credited as current, Kelvin, impedance or thermal qualification.
    """
    old=[z for z in before.Zones() if not z.GetIsRuleArea() and z.GetNetname()=='GND']
    new={force._uid(z):z for z in after.Zones() if not z.GetIsRuleArea() and z.GetNetname()=='GND'}
    if len(old)>256 or {force._uid(z) for z in old}!=set(new):
        raise ValueError('exact_bounded_source_ground_zone_inventory_required')
    checked=[]
    for zone in old:
        following=new[force._uid(zone)]
        if not zone.IsFilled() or not following.IsFilled():raise ValueError('sensitive_path_ground_fill_unknown')
        for face in before.GetEnabledLayers().CuStack():
            if not zone.IsOnLayer(face):continue
            if time.monotonic()>=deadline:raise ValueError('sensitive_path_ground_containment_deadline')
            if not zone.HasFilledPolysForLayer(face):
                raise ValueError('sensitive_path_source_ground_layer_fill_unknown')
            if not following.IsOnLayer(face) or not following.HasFilledPolysForLayer(face):
                raise ValueError('sensitive_path_source_ground_layer_missing')
            missing=pcbnew.SHAPE_POLY_SET(zone.GetFilledPolysList(face))
            missing.BooleanSubtract(following.GetFilledPolysList(face))
            if missing.OutlineCount():raise ValueError('sensitive_path_removed_existing_filled_ground_copper')
            checked.append(dict(zone_uuid=force._uid(zone),layer_id=int(face),native_source_minus_candidate_empty=True))
    return dict(ok=True,complete=True,layers=checked,area_or_distance_waiver_used=False,
        unchanged_nonzone_ground_primitives_required_by_exact_source_replay=True,
        every_preexisting_ground_return_path_material_preserved=True,current_or_release_qualified=False)


def receive(source,candidate,*,board_hint,retired_track_uuids,points_nm,allow_locked_source=False,timeout_s=10.):
    result=dict(ok=False,complete=False,errors=[],ordinary_reclassification=False,GPIO_mode_or_load_assumed=False,
        full_current_fields_absolute_cuts_uncapped_native_DRC_and_release_still_required=True,
        current_qualified=False,fab_ready=False,release_authority=False)
    try:
        deadline=sensitive_path._deadline(timeout_s);epoch=force._code_identity()
        source,candidate=[Path(p).resolve() for p in (source,candidate)]
        families=[force._family(p,board_hint) for p in (source,candidate)]
        proposal=plan(source,board_hint=board_hint,retired_track_uuids=retired_track_uuids,points_nm=points_nm,
            allow_locked_source=allow_locked_source,timeout_s=max(.001,deadline-time.monotonic()))
        _,old=additive._nodes(source);_,new=additive._nodes(candidate);ids=set(proposal['retired_track_uuids'])
        incoming=new.keys()-old.keys()
        if old.keys()-new.keys()!=ids or len(incoming)!=len(proposal['replacement_points_nm'])-1:
            raise ValueError('exact_source_sensitive_path_retirement_and_replacement_required')
        before,after=[pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
        tracks={force._uid(t):t for t in after.GetTracks()}
        if not incoming<=tracks.keys():raise ValueError('sensitive_path_can_only_add_native_tracks')
        ordered=[]
        for a,b in zip(proposal['replacement_points_nm'],proposal['replacement_points_nm'][1:]):
            hits=[u for u in incoming if tuple(tracks[u].GetStart())==tuple(a) and tuple(tracks[u].GetEnd())==tuple(b)]
            if len(hits)!=1:raise ValueError('exact_ordered_sensitive_path_geometry_required')
            ordered+=hits
        if len(set(ordered))!=len(incoming):raise ValueError('no_unowned_sensitive_path_replacement_material')
        if force._preservation_snapshot(source)[1]!=force._preservation_snapshot(candidate)[1] or force._sidecars(source)!=force._sidecars(candidate):
            raise ValueError('sensitive_path_source_rules_parts_or_sidecars_changed')
        with tempfile.TemporaryDirectory(prefix='cec-sensitive-path-replay-') as work:
            expected=force._copy_family(source,Path(work)/'family');board=construct(proposal,incoming_uuids=ordered)
            additive._ground_refill(board);field._save_field_snapshot(board,expected);_,actual=additive._nodes(expected)
            if actual.keys()!=new.keys() or any(syntax._freeze(actual[u])!=syntax._freeze(new[u]) for u in new):
                raise ValueError('source_sensitive_path_exact_native_process_and_refill_replay_differs')
        ground=_preserved_ground_material(before,after,deadline)
        parts=ordinary._partition(before,deadline,retired_uuids=ids)
        following=ordinary._partition(after,deadline,retained_keys=set().union(*parts))
        if {frozenset(p) for p in parts}!={frozenset(p) for p in following}:
            raise ValueError('source_sensitive_path_changed_surviving_native_component')
        paths=sensitive_path._terminals(before,after,proposal['net'],deadline)
        qualities=[quality.analyze_board(b) for b in (before,after)]
        corner_counts=[len(sensitive.geometry.inventory(b,{proposal['net']},minimum_nm=20000,
            geometry_policy='right_angle_chamfer')['selected']) for b in (before,after)]
        if (qualities[1]['issue_count']>qualities[0]['issue_count'] or
                qualities[1]['non_octilinear_count']>qualities[0]['non_octilinear_count'] or corner_counts[1]>corner_counts[0]):
            raise ValueError('sensitive_path_whole_board_craft_regression')
        if time.monotonic()>=deadline or epoch!=force._code_identity() or families!=[force._family(p,board_hint) for p in (source,candidate)]:
            raise ValueError('sensitive_path_sources_code_or_budget_changed')
        result.update(ok=True,complete=True,code_identity=epoch,source_sha256=force._hash(source),candidate_sha256=force._hash(candidate),
            net=proposal['net'],retired_track_uuids=sorted(ids),added_native_uuids=ordered,proposal=proposal,
            every_source_native_contact_and_component_preserved=True,every_source_pad_pair_path_proved_nonworse=True,
            source_candidate_and_code_unchanged=True,terminal_paths=paths,
            native_ground_material_preservation=ground,
            selected_net_right_angle_findings_before_after=corner_counts,
            shortened_centerline_mm=(proposal['source_length_nm']-proposal['replacement_length_nm'])/1e6,
            native_strokes_before_after=[len(ids),len(incoming)])
    except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:result['errors'].append(type(exc).__name__+':'+str(exc))
    return result


def discover(source,*,board_hint,allow_locked_source=False,maximum_candidates=8,
        stop_after_first=False,timeout_s=10.):
    deadline=sensitive_path._deadline(timeout_s)
    if (type(allow_locked_source) is not bool or type(stop_after_first) is not bool
            or type(maximum_candidates) is not int or not 1<=maximum_candidates<=16):
        raise ValueError('bounded_explicit_sensitive_reflow_discovery_required')
    source=Path(source).resolve();digest=force._hash(source);board=pcbnew.LoadBoard(str(source))
    witness=sensitive.eligible_nets(board,source,board_hint)
    grouped={force._uid(i) for g in board.Groups() for i in g.GetItems()}
    allowed={int(board.GetLayerID(n)) for n in fab.routing_layers(board,include_power=False)}
    tracks={force._uid(t):t for t in board.GetTracks() if t.GetClass()=='PCB_TRACK'
        and str(t.GetNetname()) in witness and int(t.GetLayer()) in allowed and 0<t.GetWidth()<500000
        and not t.HasSolderMask() and not t.GetParentGroup() and force._uid(t) not in grouped
        and (not t.IsLocked() or allow_locked_source)}
    if len(tracks)>2048:raise ValueError('source_sensitive_path_discovery_track_bound')
    incidence=collections.defaultdict(list)
    def key(t,p):return (str(t.GetNetname()),int(t.GetLayer()),t.GetWidth(),bool(t.IsLocked()),p)
    for uid,t in tracks.items():
        for point in (tuple(t.GetStart()),tuple(t.GetEnd())):incidence[key(t,point)].append(uid)
    chains=set()
    for first,t in sorted(tracks.items()):
        if time.monotonic()>=deadline:break
        for begin in (tuple(t.GetStart()),tuple(t.GetEnd())):
            cursor=begin;ids=[];uid=first
            while uid not in ids and len(ids)<16:
                edge=tracks[uid];a,b=tuple(edge.GetStart()),tuple(edge.GetEnd())
                cursor=b if cursor==a else a;ids.append(uid)
                if len(ids)>=2:chains.add(tuple(sorted(ids)))
                if len(chains)>4096:raise ValueError('source_sensitive_path_discovery_chain_bound')
                peers=[u for u in incidence[key(t,cursor)] if u not in ids]
                if len(peers)!=1:break
                uid=peers[0]
    menu=[]
    for ids in sorted(chains):
        if time.monotonic()>=deadline:break
        try:old=sensitive_path._chain([tracks[u] for u in ids])
        except ValueError:continue
        length=sum(tracks[u].GetLength() for u in ids)
        if length>25e6:continue
        for points in fr._canonical_45_xy_paths(old[0],old[-1]):
            if len(points)>=len(old):continue
            gain=length-sum(math.dist(a,b) for a,b in zip(points,points[1:]))
            if gain>10000:menu.append((gain,ids,[list(p) for p in points]))
    menu.sort(key=lambda q:(-q[0],q[1],q[2]));plans=[];trials=[];seen_chains=set();cheap_refusals=collections.Counter()
    # Only this read-only source board owns this cache. No constructed child
    # or saved-source receiver receives it, and every funded plan starts fresh.
    foreign_cache={}
    for gain,ids,_ in menu:
        if time.monotonic()>=deadline or len(plans)>=maximum_candidates or len(trials)>=64:break
        if ids in seen_chains:continue
        seen_chains.add(ids);cut=[tracks[u] for u in ids];original=sensitive_path._chain(cut)
        try:contacts=_source_contacts(board,cut,deadline);options=_tangent_paths(original)
        except (ValueError,RuntimeError) as exc:cheap_refusals[str(exc).split(':')[0]]+=1;continue
        for points in options:
            if time.monotonic()>=deadline or len(plans)>=maximum_candidates or len(trials)>=64:break
            gain=sum(t.GetLength() for t in cut)-sum(math.dist(a,b) for a,b in zip(points,points[1:]))
            if gain<=10000:continue
            try:
                _contacts(board,cut,points,deadline,source_contacts=contacts)
                _boundary_turns(board,cut,points,deadline)
                _clear_path(board,cut,points,deadline,foreign_cache)
            except (ValueError,RuntimeError) as exc:cheap_refusals[str(exc).split(':')[0]]+=1;continue
            trial=dict(retired_track_uuids=list(ids),predicted_gain_mm=gain/1e6);trials.append(trial)
            try:
                q=plan(source,board_hint=board_hint,retired_track_uuids=list(ids),points_nm=points,
                    allow_locked_source=allow_locked_source,timeout_s=max(.001,deadline-time.monotonic()))
                plans.append(q)
                if stop_after_first:break
            except (ValueError,RuntimeError) as exc:trial['refusal']=str(exc)
        if plans and stop_after_first:break
    if force._hash(source)!=digest:raise ValueError('sensitive_path_discovery_changed_source')
    return dict(source=str(source),source_sha256=digest,plans=plans,trials=trials,
        syntactic_source_chains=len(chains),syntactic_candidate_paths=len(menu),
        deadline_reached=time.monotonic()>=deadline,
        bounded_portfolio_complete=time.monotonic()<deadline,
        all_syntactic_paths_examined=False,source_tangent_templates_enabled=True,
        immutable_native_collision_prefilter_enabled=True,
        source_chains_funded=len(seen_chains),cheap_geometry_refusals=dict(cheap_refusals),
        source_geometry_mutated=False,finite_portfolio_not_no_path_proof=True,release_authority=False)


def run(source,outdir,*,board_hint,expected_source_sha256,reporting_build,
        allow_locked_source=False,maximum_candidates=4):
    """Bounded generic stage; only an entirely received private child wins."""
    if (type(board_hint) is not str or not board_hint or type(expected_source_sha256) is not str
            or len(expected_source_sha256)!=64 or type(allow_locked_source) is not bool
            or type(maximum_candidates) is not int or not 1<=maximum_candidates<=8 or reporting_build is None):
        raise ValueError('explicit_bounded_sensitive_path_stage_context_required')
    source,outdir=[Path(p).resolve() for p in (source,outdir)]
    if outdir.exists() or not source.is_file() or force._hash(source)!=expected_source_sha256:
        raise ValueError('fresh_output_and_literal_sensitive_path_source_required')
    epoch=force._code_identity();family=force._family(source,board_hint);outdir.mkdir(parents=True)
    discovery=discover(source,board_hint=board_hint,allow_locked_source=allow_locked_source,
        maximum_candidates=maximum_candidates)
    result=dict(ok=True,complete=True,changed=False,errors=[],source=str(source),source_sha256=expected_source_sha256,
        candidate=str(source),candidate_sha256=expected_source_sha256,code_identity=epoch,
        discovery=discovery,attempts=[],records=[],source_selected=False,routing_admitted=False,fab_ready=False,release_authority=False)
    import cec_current_debt as current
    import cec_force_sense_evidence as sense
    import cec_native_drc_runner as native
    import cec_stage_admission as admission
    def observe(path,label):
        shadow=force._copy_family(path,outdir/(label+'-native-input'));dest=outdir/(label+'.drc.json')
        producer=native.run(shadow,dest,reporting_build=reporting_build,timeout_s=10.)
        if not producer['ok'] or not producer['complete'] or producer['native_inventory']['potentially_truncated']:
            raise ValueError('complete_uncapped_sensitive_path_native_report_required')
        import json
        return json.loads(dest.read_text()),producer
    baseline=None
    for index,proposal in enumerate(discovery['plans']):
        row=dict(proposal=proposal,accepted=False,errors=[]);result['attempts'].append(row)
        try:
            board=construct(proposal);child=force._copy_family(source,outdir/('UNADMITTED-sensitive-path-'+str(index)))
            additive._ground_refill(board);field._save_field_snapshot(board,child)
            params=dict(retired_track_uuids=proposal['retired_track_uuids'],points_nm=proposal['replacement_points_nm'],
                allow_locked_source=allow_locked_source)
            proof=receive(source,child,board_hint=board_hint,**params);row['independent_saved_phase']=proof
            if not proof['ok'] or not proof['complete']:raise ValueError('source_sensitive_path_saved_receiving:'+str(proof['errors']))
            debt=current.receive(source,child,board_hint=board_hint);row['whole_parent_current']=debt
            if not debt['ok'] or not debt['complete']:raise ValueError('source_sensitive_path_current_nonregression_required')
            with force._thermal_hint(board_hint):
                delta=sorted(field.blocker_keys(field.field_coupling_summary(str(child)))-field.blocker_keys(field.field_coupling_summary(str(source))))
            row['new_field_blockers']=delta
            if delta:raise ValueError('source_sensitive_path_new_field_blocker')
            if baseline is None:baseline,producer=observe(source,'source');result['source_native_producer']=producer
            after,producer=observe(child,'candidate-'+str(index));row['candidate_native_producer']=producer
            faults=sorted({admission._canonical_identity(v) for v in after['violations']}-
                {admission._canonical_identity(v) for v in baseline['violations']})
            row.update(new_native_fault_ids=faults,opens=len(after['unconnected_items']))
            if faults or row['opens']:raise ValueError('source_sensitive_path_new_native_fault_or_open')
            cuts0,cuts1=[sense.replay(p,board_hint=board_hint,timeout_s=40.) for p in (source,child)]
            cuts=sense.compare_contour_preservation(cuts0,cuts1,modified_nets=[proposal['net'],'GND'],
                native_copper_transforms=sense.native_copper_transform_inventory(pcbnew.LoadBoard(str(source)),board,
                    modified_nets=[proposal['net'],'GND']))
            row['whole_parent_clipped_preservation']=cuts
            if not cuts['same_evidence'] or not cuts['comparison_complete']:raise ValueError('source_sensitive_path_absolute_cuts_changed')
            row['accepted']=True
            result.update(changed=True,candidate=str(child),candidate_sha256=force._hash(child),
                records=[dict(plan=params,materialized=dict(retired_track_uuids=proof['retired_track_uuids'],
                    added_native_uuids=proof['added_native_uuids']))],shortened_centerline_mm=proof['shortened_centerline_mm'],
                native_strokes_before_after=proof['native_strokes_before_after'])
        except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:row['errors'].append(type(exc).__name__+':'+str(exc))
        if result['changed']:break
    result['source_family_and_code_unchanged']=epoch==force._code_identity() and family==force._family(source,board_hint)
    if not result['source_family_and_code_unchanged']:
        result.update(ok=False,complete=False,changed=False,candidate=str(source),candidate_sha256=expected_source_sha256)
        result['errors'].append('source_sensitive_path_source_or_code_changed')
    force._write(outdir/'stage.json',result);return result


def main():
    import argparse,json
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('source','out','reporting-build'):p.add_argument('--'+k,type=Path,required=True)
    for k in ('board-hint','expected-source-sha256'):p.add_argument('--'+k,required=True)
    p.add_argument('--allow-locked-source',action='store_true');p.add_argument('--maximum-candidates',type=int,default=4)
    a=p.parse_args();import cec_swig_guard;cec_swig_guard.pin()
    import wx;quiet=wx.LogNull()
    r=run(a.source,a.out,board_hint=a.board_hint,expected_source_sha256=a.expected_source_sha256,
        reporting_build=a.reporting_build,allow_locked_source=a.allow_locked_source,maximum_candidates=a.maximum_candidates)
    print(json.dumps({k:r.get(k) for k in ('ok','complete','changed','candidate','candidate_sha256','shortened_centerline_mm','native_strokes_before_after','errors')}),flush=True)
    return 0 if r['ok'] and r['complete'] else 1


if __name__=='__main__':raise SystemExit(main())
