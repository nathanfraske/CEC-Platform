"""Bounded native source-corridor hints, never retirement/current authority.

A source guide is only a geometric search hint. Integer 45-degree/cardinal
bypasses are checked on the CURRENT native board, including actual future
track-rule areas. No conductor is moved, width reduced, hole added or result
admitted here. Existing saved ordinary/current/field/native receivers remain
mandatory. Source-owned single cuts can try these before an unrestricted maze.
"""
import math
import time
import hashlib
from pathlib import Path
import pcbnew
import cec_fr as fr
import cec_native_rule_areas as rules
import cec_route_quality as quality

SCOPE='source_guided_strict_ordinary_chain_shortening'


def length_terms(points):
    """Exact integer a+b*sqrt(2) length; no rounded non45 permission."""
    if (type(points) not in (list,tuple) or not 2<=len(points)<=32
            or any(type(p) not in (list,tuple) or len(p)!=2
                or any(type(v) is not int or abs(v)>2000000000 for v in p) for p in points)):
        raise ValueError('bounded_native_integer_guide_points_required')
    cardinal=diagonal=0
    for a,b in zip(points,points[1:]):
        x,y=[abs(b[i]-a[i]) for i in (0,1)]
        if not (x or y) or x and y and x!=y:raise ValueError('nonzero_exact_octilinear_guide_required')
        if x and y:diagonal+=x
        else:cardinal+=x+y
    return dict(cardinal_nm=cardinal,diagonal_component_nm=diagonal)


def strictly_shorter(candidate,source):
    """Strict exact radical comparison, not a float-length waiver."""
    a,b=[length_terms(q) for q in (candidate,source)]
    c=a['cardinal_nm']-b['cardinal_nm'];d=a['diagonal_component_nm']-b['diagonal_component_nm']
    return c<0 if d==0 else (c<0 and c*c>2*d*d if d>0 else c<=0 or c*c<2*d*d)


def _clean(points):
    result=[]
    for p in points:
        p=list(p)
        if result and p==result[-1]:continue
        while len(result)>1:
            u=[result[-1][i]-result[-2][i] for i in (0,1)]
            v=[p[i]-result[-1][i] for i in (0,1)]
            if u[0]*v[1]!=u[1]*v[0] or sum(x*y for x,y in zip(u,v))<=0:break
            result.pop()
        result.append(p)
    return result


def guide_bypass(points,lo_nm,hi_nm,height_nm,side):
    """Monotone <=45deg corridor bypass; every station is an exact integer."""
    length_terms(points)
    if len(points)!=2:raise ValueError('one_straight_native_guide_required')
    a,b=points;delta=[b[i]-a[i] for i in (0,1)];extent=max(abs(v) for v in delta)
    if (any(type(v) is not int for v in (lo_nm,hi_nm,height_nm,side))
            or not 0<lo_nm<hi_nm<extent or not 0<height_nm<hi_nm-lo_nm or side not in (0,1)):
        raise ValueError('proper_bounded_interior_guide_bypass_required')
    u=[(v>0)-(v<0) for v in delta]
    p=[a[i]+lo_nm*u[i] for i in (0,1)];q=[a[i]+hi_nm*u[i] for i in (0,1)]
    if all(u):
        axis=side;other=1-axis
        first=p[:];first[axis]+=u[axis]*height_nm
        last=q[:];last[other]-=u[other]*height_nm
    else:
        if 2*height_nm>=hi_nm-lo_nm:raise ValueError('positive_cardinal_guide_middle_required')
        axis=0 if u[0] else 1;normal=1-axis;sign=1 if side else -1
        first=p[:];first[axis]+=u[axis]*height_nm;first[normal]+=sign*height_nm
        last=q[:];last[axis]-=u[axis]*height_nm;last[normal]+=sign*height_nm
    result=_clean([a,p,first,last,q,b]);length_terms(result)
    edges=[[z[i]-x[i] for i in (0,1)] for x,z in zip(result,result[1:])]
    if any(sum(x*y for x,y in zip(u,v))<=0 for u,v in zip(edges,edges[1:])):
        raise ValueError('guide_bypass_contains_hard90_or_backtracking')
    return result


def propose(board,guide_points,*,net_code,layer,width_nm,clearance_nm,deadline=None,
            samples=64,max_checked=256,max_returned=4,max_offset_nm=2000000,
            max_padding_nm=2000000,validate=None,run_guard=None):
    """Read-only fully native-checked options; hints grant no source ownership.

    Sampling locates a finite search window, NEVER qualifies a route. Every
    returned full-width segment passes exact current foreign-copper, board
    edge, rule-area, proposed-craft and optional field/transaction guards.
    Budget exhaustion may leave search incomplete, not a no-path proof; no
    partially checked candidate is returned.
    """
    now=time.monotonic();deadline=now+10. if deadline is None else deadline
    if (type(deadline) not in (int,float) or not math.isfinite(deadline) or not now<deadline<=now+10.01
            or type(net_code) is not int or net_code<=0 or board.FindNet(net_code) is None
            or type(layer) is not int or layer not in board.GetEnabledLayers().CuStack()
            or type(width_nm) is not int or not board.GetDesignSettings().m_TrackMinWidth<=width_nm<500000
            or type(clearance_nm) is not int or not board.GetDesignSettings().m_MinClearance<=clearance_nm<=10000000
            or any(type(v) is not int or not lo<=v<=hi for v,lo,hi in
                ((samples,8,128),(max_checked,1,512),(max_returned,1,16),
                 (max_offset_nm,100000,4000000),(max_padding_nm,100000,4000000)))
            or validate is not None and not callable(validate) or run_guard is not None and not callable(run_guard)):
        raise ValueError('bounded_native_guide_search_context_required')
    length_terms(guide_points)
    if len(guide_points)!=2:raise ValueError('one_straight_native_guide_required')
    a,b=[list(p) for p in guide_points];delta=[b[i]-a[i] for i in (0,1)]
    extent=max(abs(v) for v in delta)
    if not 200000<=extent<=64000000:raise ValueError('bounded_native_guide_extent_required')
    u=[(v>0)-(v<0) for v in delta]
    zones,copper=fr._foreign_shape_indexes(board,layer,{net_code})
    forbidden=[r['shape'] for r in rules.areas(board,'tracks') if layer in r['layers']]
    net=board.FindNet(net_code).GetNetname();checked=0;options=[];seen=set()
    def leg_clear(x,z):
        if time.monotonic()>=deadline:raise TimeoutError('native_guide_search_budget_exhausted')
        start,end=pcbnew.VECTOR2I(*x),pcbnew.VECTOR2I(*z)
        return (fr._edge_leg_clear(board,start,end,(width_nm+1)//2)
            and fr._snapshot_foreign_clear(start,end,width_nm,clearance_nm,zones,copper)
            and not any(p.Collide(pcbnew.SHAPE_SEGMENT(start,end,width_nm),0) for p in forbidden)
            and (run_guard is None or run_guard(start,end,width_nm)))
    def check(points):
        nonlocal checked
        key=tuple(map(tuple,points))
        if key in seen or checked>=max_checked:return
        seen.add(key);checked+=1
        # An integer-exact1nm launch is not a useful physical corner. Keep
        # each new phase at least one actual trace width (and20um) long;
        # this is search style, not a clearance or source-loss tolerance.
        if any(max(abs(z[i]-x[i]) for i in (0,1))<max(20000,width_nm)
                for x,z in zip(points,points[1:])):return
        if not all(leg_clear(x,z) for x,z in zip(points,points[1:])):return
        rows=[dict(net=net,layer=layer,width_nm=width_nm,start_nm=x,end_nm=z) for x,z in zip(points,points[1:])]
        craft=quality.assess_proposed_route(board,rows,deadline=deadline,max_proposed=8)
        if not craft['ok'] or not craft['complete']:return
        if validate is not None and not validate(points):return
        options.append(dict(points_nm=points,length=length_terms(points),
            all_legs_native_clear=True,craft=craft,caller_validation_positive=validate is not None))
    complete=True;blocked=[]
    try:
        check([a,b])
        if not options:
            for i in range(samples):
                left=i*extent//samples;right=(i+1)*extent//samples
                x=[a[k]+left*u[k] for k in (0,1)];z=[a[k]+right*u[k] for k in (0,1)]
                if not leg_clear(x,z):blocked.append([left,right])
            if blocked:
                candidates=[]
                for padding in sorted({min(max_padding_nm,v) for v in (100000,200000,400000,800000,1200000,2000000)}):
                    lo=max(width_nm,blocked[0][0]-padding);hi=min(extent-width_nm,blocked[-1][1]+padding)
                    for height in range(100000,max_offset_nm+1,100000):
                        for side in (0,1):
                            try:points=guide_bypass([a,b],lo,hi,height,side)
                            except ValueError:continue
                            terms=length_terms(points)
                            rank=terms['cardinal_nm']+terms['diagonal_component_nm']*math.sqrt(2)
                            candidates.append((rank,hi-lo,len(points),points))
                for _,_,_,points in sorted(candidates):
                    check(points)
                    if len(options)>=max_returned:break
                    if checked>=max_checked:complete=False;break
    except TimeoutError:complete=False
    return dict(ok=bool(options),complete=complete,options=options,checked_candidates=checked,
        blocked_guide_intervals_nm=blocked,sampling_is_search_only_not_clearance_proof=True,
        all_returned_paths_fully_native_guarded=True,native_copper_mutated=False,
        source_retirement_or_current_or_route_admission=False,no_path_proof=False,release_authority=False)


def _source_contacts(board,selected,points,deadline):
    """Preserve every actual same-face side tap, not just chain endpoints."""
    import cec_force_current as force
    ids={force._uid(t) for t in selected};face=int(selected[0].GetLayer());code=selected[0].GetNetCode()
    shapes=[pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*b),selected[0].GetWidth())
        for a,b in zip(points,points[1:])]
    old=[t.GetEffectiveShape(face) for t in selected]
    items=[*board.GetTracks(),*[p for f in board.GetFootprints() for p in f.Pads()]]
    if len(items)>16384:raise ValueError('bounded_native_guide_contact_inventory_required')
    for item in items:
        if time.monotonic()>=deadline:raise TimeoutError('native_guide_contact_budget_exhausted')
        if force._uid(item) in ids or item.GetNetCode()!=code or not item.IsOnLayer(face):continue
        shape=item.GetEffectiveShape(face)
        if any(q.Collide(shape,0) for q in old) and not any(q.Collide(shape,0) for q in shapes):return False
    return True


def plan(source,guide_source,guide_track_uuid,retired_track_uuids,*,board_hint,
         allow_locked_track_uuids=(),timeout_s=10.):
    """An exact current ordinary chain is authority; an old route is a hint."""
    import cec_force_current as force
    import cec_ordinary_route_receiving as ordinary
    import cec_additive_route_receiving as additive
    import cec_cell_row_rebuild as binding
    import cec_pair_local_reference_refinement as chain
    import cec_fab_profile as fab
    if (type(board_hint) is not str or not board_hint or type(timeout_s) not in (int,float)
            or not math.isfinite(timeout_s) or not 0<timeout_s<=10
            or type(guide_track_uuid) is not str or not guide_track_uuid):
        raise ValueError('bounded_source_owned_ordinary_guide_context_required')
    deadline=time.monotonic()+timeout_s
    source,guide_source=[Path(p).resolve() for p in (source,guide_source)]
    digests=[force._hash(p) for p in (source,guide_source)]
    ids=ordinary._ids(retired_track_uuids,'ordinary_guide_retired_scope',16)
    unlock=ordinary._ids(allow_locked_track_uuids,'ordinary_guide_locked_scope',16)
    if not ids:raise ValueError('nonempty_current_ordinary_guide_scope_required')
    board,historical=[pcbnew.LoadBoard(str(p)) for p in (source,guide_source)]
    current={force._uid(t):t for t in board.GetTracks()};hints={force._uid(t):t for t in historical.GetTracks()}
    if len(current)>16384 or len(hints)>16384 or not ids<=current.keys() or guide_track_uuid not in hints:
        raise ValueError('bounded_actual_ordinary_guide_inventory_required')
    selected=[current[u] for u in sorted(ids)];guide=hints[guide_track_uuid]
    grouped={force._uid(i) for g in board.Groups() for i in g.GetItems()}
    if (any(t.GetClass()!='PCB_TRACK' or force._uid(t) in grouped for t in selected)
            or unlock!={force._uid(t) for t in selected if t.IsLocked()}
            or len({(t.GetNetname(),int(t.GetLayer()),t.GetWidth()) for t in selected})!=1):
        raise ValueError('one_uniform_ungrouped_explicitly_locked_ordinary_chain_required')
    net=selected[0].GetNetname();face=int(selected[0].GetLayer());width=selected[0].GetWidth()
    if (net not in ordinary.eligible_nets(board,source,board_hint)
            or face not in {board.GetLayerID(n) for n in fab.routing_layers(board,include_power=False)}
            or not board.GetDesignSettings().m_TrackMinWidth<=width<500000):
        raise ValueError('positive_current_ordinary_signal_role_and_face_required')
    if (guide.GetClass()!='PCB_TRACK' or guide.GetNetname()!=net or int(guide.GetLayer())!=face
            or guide.GetWidth()!=width):raise ValueError('matching_native_guide_is_hint_only_required')
    _,nodes=additive._nodes(source)
    signature=chain._process(nodes[force._uid(selected[0])])
    if any(chain._process(nodes[force._uid(t)])!=signature for t in selected):
        raise ValueError('all_source_ordinary_process_fields_must_match')
    points=[list(p) for p in chain._chain(selected)];length_terms(points)
    hint=[list(guide.GetStart()),list(guide.GetEnd())];length_terms(hint)
    if hint[0]!=points[0]:hint.reverse()
    if [points[0],points[-1]]!=hint:raise ValueError('exact_current_chain_boundary_ports_required')
    direction=lambda a,b:tuple((b[i]>a[i])-(b[i]<a[i]) for i in (0,1))
    tangent=direction(*hint)
    if direction(*points[:2])!=tangent or direction(*points[-2:])!=tangent:
        raise ValueError('unchanged_actual_current_launch_tangents_required')
    resolver=fr._project_netclass_resolver(str(source));spec=resolver(net) or {}
    gap=max(int(board.GetDesignSettings().m_MinClearance),fr._nm(float(spec.get('clearance') or 0)))
    class View:
        def GetTracks(self):return [t for t in board.GetTracks() if force._uid(t) not in ids]
        def __getattr__(self,name):return getattr(board,name)
    initial=binding._source_binding(board)
    options=propose(View(),hint,net_code=selected[0].GetNetCode(),layer=face,width_nm=width,clearance_nm=gap,
        deadline=deadline,validate=lambda new:strictly_shorter(new,points) and _source_contacts(board,selected,new,deadline))
    if not options['options']:raise ValueError('bounded_native_guide_has_no_received_shortening_option')
    chosen=options['options'][0]['points_nm']
    if initial!=binding._source_binding(board) or digests!=[force._hash(p) for p in (source,guide_source)]:
        raise ValueError('ordinary_guide_source_changed')
    r=dict(schema=1,scope=SCOPE,source=str(source),source_sha256=digests[0],source_binding=initial,
        guide_source=str(guide_source),guide_source_sha256=digests[1],guide_track_uuid=guide_track_uuid,
        retired_track_uuids=sorted(ids),allow_locked_track_uuids=sorted(unlock),board_hint=board_hint,
        net=net,layer=face,width_nm=width,clearance_nm=gap,source_points_nm=points,guide_points_nm=hint,
        candidate_points_nm=chosen,source_length=length_terms(points),candidate_length=length_terms(chosen),
        exact_radical_strict_shortening=True,unchanged_fixed_source_ports_and_tangents=True,
        every_actual_source_same_net_side_contact_preserved=True,
        source_process_sha256=hashlib.sha256(repr(signature).encode()).hexdigest(),
        guide_grants_no_retirement_or_process_authority=True,source_selected=False,routing_admitted=False,release_authority=False)
    import cec_rectilinear_copper as owner
    r['plan_sha256']=owner._digest(r);return r


def construct(board,proposal):
    """Private source-bound materialization; saved receiving still required."""
    import cec_force_current as force
    import cec_cell_row_rebuild as binding
    import cec_rectilinear_copper as owner
    from cec_native_items import discard_items
    packet=dict(proposal);digest=packet.pop('plan_sha256',None)
    if digest!=owner._digest(packet) or proposal.get('scope')!=SCOPE:
        raise ValueError('source_guide_plan_identity_required')
    if binding._source_binding(board)!=proposal['source_binding']:
        raise ValueError('actual_source_guide_native_board_changed')
    fresh=plan(proposal['source'],proposal['guide_source'],proposal['guide_track_uuid'],proposal['retired_track_uuids'],
        board_hint=proposal['board_hint'],allow_locked_track_uuids=proposal['allow_locked_track_uuids'])
    if fresh!=proposal:raise ValueError('ordinary_guide_not_independently_source_derived')
    selected=[t for t in board.GetTracks() if force._uid(t) in proposal['retired_track_uuids']]
    prototype=selected[0].Duplicate();made=[]
    for a,b in zip(proposal['candidate_points_nm'],proposal['candidate_points_nm'][1:]):
        edge=prototype.Duplicate();edge.m_Uuid.Clone(pcbnew.KIID())
        edge.SetStart(pcbnew.VECTOR2I(*a));edge.SetEnd(pcbnew.VECTOR2I(*b));made.append(edge)
    discard_items(board,selected)
    for edge in made:board.Add(edge)
    return dict(incoming_track_uuids=[force._uid(t) for t in made],retired_track_uuids=proposal['retired_track_uuids'],
        full_source_width_and_process_preserved=True,private_unadmitted=True,release_authority=False)


def receive(source,candidate,proposal,*,board_hint):
    """Independently derive geometry, exact process, saved subtraction/addition."""
    import cec_force_current as force
    import cec_ordinary_route_receiving as ordinary
    import cec_additive_route_receiving as additive
    import cec_pair_local_reference_refinement as chain
    result=dict(ok=False,complete=False,errors=[],full_native_current_field_cut_receiving_required=True,
        source_selected=False,routing_admitted=False,release_authority=False)
    try:
        if Path(source).resolve()!=Path(proposal['source']).resolve() or board_hint!=proposal['board_hint']:
            raise ValueError('same_exact_current_ordinary_guide_source_required')
        fresh=plan(source,proposal['guide_source'],proposal['guide_track_uuid'],proposal['retired_track_uuids'],
            board_hint=board_hint,allow_locked_track_uuids=proposal['allow_locked_track_uuids'])
        if fresh!=proposal:raise ValueError('saved_source_guide_recipe_changed')
        before,after=[pcbnew.LoadBoard(str(path)) for path in (source,candidate)]
        old={force._uid(t):t for t in before.GetTracks()};new={force._uid(t):t for t in after.GetTracks()}
        incoming=new.keys()-old.keys();retired=old.keys()-new.keys()
        if retired!=set(proposal['retired_track_uuids']) or not 1<=len(incoming)<=8:
            raise ValueError('exact_ordinary_guide_retired_and_incoming_scope_required')
        if any(new[u].GetClass()!='PCB_TRACK' for u in incoming):raise ValueError('guide_cannot_add_a_barrel')
        points=[list(p) for p in chain._chain([new[u] for u in incoming])]
        if points!=proposal['candidate_points_nm'] or not strictly_shorter(points,proposal['source_points_nm']):
            raise ValueError('saved_native_guide_geometry_or_exact_shortening_differs')
        _,old_nodes=additive._nodes(source);_,new_nodes=additive._nodes(candidate)
        process=chain._process(old_nodes[proposal['retired_track_uuids'][0]])
        if any(chain._process(new_nodes[u])!=process for u in incoming):
            raise ValueError('saved_ordinary_guide_process_or_width_changed')
        proof=ordinary.receive(source,candidate,retired_track_uuids=proposal['retired_track_uuids'],
            allow_locked_track_uuids=proposal['allow_locked_track_uuids'],board_hint=board_hint)
        if not proof['ok'] or not proof['complete']:raise ValueError('whole_source_ordinary_guide_replay_refused:'+str(proof['errors']))
        result.update(ok=True,complete=True,independent_ordinary_receiving=proof,
            exact_radical_strict_shortening=True,source_length=proposal['source_length'],candidate_length=proposal['candidate_length'])
    except (ValueError,RuntimeError,KeyError,TypeError,OSError,TimeoutError) as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result
