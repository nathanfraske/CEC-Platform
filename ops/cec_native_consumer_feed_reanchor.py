"""Construct an existing generic reanchor transaction from native source scope.

The saved receiver is the original independent consumer-feed receiver. Source
removal must expose one positively typed input island. Only its actual local
floor may widen exclusive retained strokes; the aggregate rail, packages,
parts, real terminal, source barrels and other groups remain unchanged.
"""
import json,math,time,uuid
from pathlib import Path
import pcbnew
import cec_consumer_branch_reanchor as original
import cec_supply_consumer_branch as consumer
import cec_force_current as force
import cec_field_coupling as field
import cec_fab_profile as fab
import cec_existing_current_path_refinement as capacity
import cec_current_debt as debt
from cec_native_items import discard_items

POLICY='native-source-typed-existing-consumer-feed-reanchor-v1'
def require(value,message):
    if not value:raise ValueError(message)
def plain(v):return json.loads(json.dumps(v,allow_nan=False))


def terminal_approach_guard(board,net,face,width,terminals):
    """Retained endpoint rays constrain search, not just its final score.

    Near aliases require actual native copper contact. No endpoint is snapped
    or moved. Exposed acute approaches and covered collinear overlap fail;
    an angled join absorbed by actual same-net pad copper is not an exposed
    backtrack. This matches the independent route-quality observer.
    """
    sites={tuple(p) for p in terminals};tracks=list(board.GetTracks())
    require(len(sites)<=2 and len(tracks)<=16384,'bounded_native_terminal_approach_inventory_required')
    nearby={p:[] for p in sites}
    pad_capture={p:False for p in sites}
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetname()!=net or not pad.IsOnLayer(face):continue
            shape=pad.GetEffectiveShape(face)
            for p in sites:
                point=pcbnew.VECTOR2I(*p)
                if (shape.Contains(point) if hasattr(shape,'Contains') else shape.Collide(point)):
                    pad_capture[p]=True
    for t in tracks:
        if t.GetClass()!='PCB_TRACK' or t.GetNetname()!=net or int(t.GetLayer())!=face:continue
        for p in sites:
            for a,z in ((t.GetStart(),t.GetEnd()),(t.GetEnd(),t.GetStart())):
                if math.dist(tuple(a),p)<=1000:nearby[p].append((t,tuple(a),tuple(z)))
    def clear(a,z,ignored_width=None):
        a,z=tuple(a),tuple(z)
        for at,other in ((a,z),(z,a)):
            if at not in sites:continue
            probe=pcbnew.PCB_TRACK(board);probe.SetLayer(face);probe.SetWidth(width)
            probe.SetStart(pcbnew.VECTOR2I(*at));probe.SetEnd(pcbnew.VECTOR2I(*other))
            rays={force._uid(t):(p,q) for t,p,q in nearby[at]
                if t.GetEffectiveShape(face).Collide(probe.GetEffectiveShape(face),0)}
            if len(rays)!=1:continue
            p,q=next(iter(rays.values()));u=[q[i]-p[i] for i in (0,1)];v=[other[i]-at[i] for i in (0,1)]
            if sum(x*y for x,y in zip(u,v))>0:
                if u[0]*v[1]-u[1]*v[0] and pad_capture[at]:continue
                return False
        return True
    return clear


def single_tap_guard(board,scope,anchor_uuid,face,*,timeout_s=10.):
    """Protect shared same-net copper outside the real terminal aperture.

    A net-name match is not permission to contact the trunk along a route.
    The independent saved consumer receiver still rederives the exact tap.
    """
    deadline=time.monotonic()+timeout_s
    items=[*board.GetTracks(),*(p for fp in board.GetFootprints() for p in fp.Pads()),*board.Zones()]
    require(len(items)<=16384,'bounded_native_single_tap_inventory_required')
    live={force._uid(i):i for i in items};anchor=live[anchor_uuid];owned=set(scope['exclusive_source_island'])
    aperture=pcbnew.SHAPE_POLY_SET();anchor.TransformShapeToPolygon(aperture,face,0,1,pcbnew.ERROR_INSIDE,False)
    protected=pcbnew.SHAPE_POLY_SET()
    for item in items:
        require(time.monotonic()<deadline,'source_single_tap_guard_inventory_deadline')
        if force._uid(item) in owned or force._uid(item)==anchor_uuid or item.GetNetname()!=scope['net'] or not item.IsOnLayer(face):continue
        if item.GetClass()=='ZONE':
            if item.GetIsRuleArea():continue
            require(item.IsFilled() and item.HasFilledPolysForLayer(face),'complete_native_shared_rail_fill_required')
            poly=item.GetFilledPolysList(face)
        else:
            poly=pcbnew.SHAPE_POLY_SET();item.TransformShapeToPolygon(poly,face,0,1,pcbnew.ERROR_OUTSIDE,False)
        protected.BooleanAdd(poly)
    protected.BooleanSubtract(aperture)
    def clear(a,z,width):
        if time.monotonic()>=deadline:return False
        t=pcbnew.PCB_TRACK(board);t.SetStart(pcbnew.VECTOR2I(*a));t.SetEnd(pcbnew.VECTOR2I(*z));t.SetWidth(width);t.SetLayer(face)
        return not protected.Collide(t.GetEffectiveShape(face),0)
    return clear


def source_scope(source,*,board_hint,root_pad_uuid,retired_track_uuids,anchor_uuid):
    source=Path(source).resolve();b=pcbnew.LoadBoard(str(source));deadline=time.monotonic()+10.
    cut=original.ordinary._ids(retired_track_uuids,'native_consumer_feed_cut',8)
    live={force._uid(t):t for t in b.GetTracks()};pads={force._uid(p):p for fp in b.GetFootprints() for p in fp.Pads()}
    require(cut and cut<=live.keys() and root_pad_uuid in pads and anchor_uuid in {**live,**pads},
        'actual_consumer_feed_source_material_required')
    old=[live[u] for u in sorted(cut)]
    require(all(t.GetClass()=='PCB_TRACK' and not t.GetParentGroup() and not t.HasSolderMask()
        and 0<t.GetWidth()<=350000 and 0<t.GetLength()<=32000000
        and t.GetLayer() in (pcbnew.F_Cu,pcbnew.B_Cu) for t in old),
        'bounded_plain_outer_old_consumer_feed_required')
    prior=consumer.inventory(b,board_hint=board_hint,timeout_s=10.)
    rows=[p for p in prior['proofs'] if p['root_pad_uuid']==root_pad_uuid]
    require(prior['complete'] and len(rows)==1,'one_positive_existing_consumer_required')
    root=pads[root_pad_uuid];net=root.GetNetname();anchor={**live,**pads}[anchor_uuid]
    require(all(t.GetNetname()==net for t in old) and anchor.GetNetname()==net
        and anchor.GetClass() in ('PAD','PCB_VIA') and anchor_uuid!=rows[0]['anchor_uuid'],
        'one_new_unchanged_actual_same_net_terminal_capture_required')
    groups=[g for g in b.Groups() if g.GetName().startswith(consumer.PREFIX+root_pad_uuid+'|')]
    require(len(groups)==1 and not groups[0].GetParentGroup(),'one_unnested_existing_consumer_group_required')
    group=groups[0];members={force._uid(t) for t in group.GetItems()}
    chain=[list(p) for p in capacity.chains._chain(old)];old_length=sum(t.GetLength() for t in old)
    discard_items(b,old)
    native={force._uid(i):i for i in [*pads.values(),*b.GetTracks(),*[z for z in b.Zones() if not z.GetIsRuleArea()]] if i.GetNetname()==net}
    graph=consumer._graph(list(native.values()),deadline)
    island,monitors=consumer._island(b,root,graph,native,deadline)
    require(members<=island and anchor_uuid not in island,'complete_exclusive_native_input_island_required')
    budget=consumer._with_closed_monitor_loads(b,consumer.contract(b,root_pad_uuid,board_hint=board_hint),monitors)
    require(budget==rows[0]['budget'],'existing_input_design_budget_must_remain_exact')
    widenings=[];owned=set(rows[0]['track_requirements'])|set(rows[0]['retained_island_track_requirements'])
    for uid in sorted(island):
        item=native[uid]
        if item.GetClass()!='PCB_TRACK':continue
        # The old scope can contain independently typed monitor/control
        # leaves. Do not reinterpret its already-owned thin conductors as a
        # new whole-load feed merely because the upstream tap is changing.
        # Their exact original geometry and all current gates are retained.
        if uid in owned:continue
        face=int(item.GetLayer());floor=math.ceil(budget['required_by_layer_mm'][fab.COPPER_LAYER_IDS[face]]*1e6)
        if item.GetWidth()>=floor:continue
        require(face in (pcbnew.F_Cu,pcbnew.B_Cu) and (not item.GetParentGroup() or uid in owned)
            and floor-item.GetWidth()<=(10000 if uid in owned else 300000) and item.GetLength()<=32000000,
            'retained_input_widening_requires_exclusive_native_actual_floor_scope')
        widenings.append(dict(uuid=uid,old_width_nm=item.GetWidth(),width_nm=floor))
    require(len(widenings)<=16,'finite_exclusive_input_widening_scope_required')
    return b,plain(dict(source_sha256=force._hash(source),board_hint=board_hint,root_pad_uuid=root_pad_uuid,
        anchor_uuid=anchor_uuid,source_anchor_uuid=rows[0]['anchor_uuid'],retired_track_uuids=sorted(cut),
        group_uuid=force._uid(group),source_group_name=group.GetName(),source_group_members=sorted(members),
        source_via_csv=group.GetName()[len(consumer.PREFIX):].split('|')[2],net=net,budget=budget,
        source_points_nm=chain,source_length_nm=old_length,exclusive_source_island=sorted(island),
        exact_floor_widenings=widenings,source_current_reduced=False,branch_sharing_assumed=False,release_authority=False))


def plan(source,*,board_hint,root_pad_uuid,retired_track_uuids,anchor_uuid,layer,points_nm,launch_uuid=None):
    source=Path(source).resolve();epoch=force._code_identity();b,q=source_scope(source,board_hint=board_hint,
        root_pad_uuid=root_pad_uuid,retired_track_uuids=retired_track_uuids,anchor_uuid=anchor_uuid)
    require(type(layer) is int and layer in (int(pcbnew.F_Cu),int(pcbnew.B_Cu)), 'actual_outer_consumer_feed_face_required')
    points=[list(p) for p in capacity.geometry._points(points_nm)]
    all_native={force._uid(i):i for i in [*b.GetTracks(),*(p for fp in b.GetFootprints() for p in fp.Pads())]}
    if launch_uuid is None:
        require(points[0] in (q['source_points_nm'][0],q['source_points_nm'][-1]),'literal_retained_input_feed_port_required')
    else:
        require(type(launch_uuid) is str and launch_uuid in q['exclusive_source_island']
            and launch_uuid in all_native and all_native[launch_uuid].GetClass() in ('PAD','PCB_VIA')
            and all_native[launch_uuid].IsOnLayer(layer) and points[0]==list(all_native[launch_uuid].GetPosition()),
            'launch_must_be_actual_retained_terminal_in_the_source_proved_input_island')
    anchor=all_native[anchor_uuid]
    require(anchor.IsOnLayer(layer) and points[-1]==list(anchor.GetPosition()),'literal_retained_terminal_capture_centre_required')
    require(sum(math.dist(a,z) for a,z in zip(points,points[1:]))<=min(50000000,q['source_length_nm']+16000000),
        'finite_existing_consumer_feed_route_extension_required')
    width=math.ceil(q['budget']['required_by_layer_mm'][fab.COPPER_LAYER_IDS[layer]]*1e6)
    for r in q['exact_floor_widenings']:all_native[r['uuid']].SetWidth(r['width_nm'])
    tap=single_tap_guard(b,q,anchor_uuid,layer)
    approach=terminal_approach_guard(b,q['net'],layer,width,(points[0],points[-1]))
    spec=capacity.fr._project_netclass_resolver(str(source),board=b)(q['net']) or {}
    gap=max(b.GetDesignSettings().m_MinClearance,math.ceil(float(spec.get('clearance') or .2)*1e6))
    for a,z in zip(points,points[1:]):
        require(capacity.fr._edge_leg_clear(b,pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*z),(width+1)//2+gap)
            and capacity.fr._tap_foreign_clear(b,pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*z),width,layer,gap,{anchor.GetNetCode()})
            and tap(a,z,width) and approach(a,z,width),
            'new_full_local_floor_feed_native_clearance_or_edge_refused')
    require(epoch==force._code_identity(),'consumer_feed_source_runtime_changed')
    return plain(dict(policy=POLICY,authority_sha256=force._hash(Path(__file__)),code_identity=epoch,
        scope=q,layer=layer,width_nm=width,points_nm=points,launch_uuid=launch_uuid,
        new_vias_authorized=False,current_or_release_qualified=False))


def construct(source,proposal):
    q=proposal['scope'];b=pcbnew.LoadBoard(str(source));live={force._uid(t):t for t in b.GetTracks()}
    discard_items(b,[live[u] for u in q['retired_track_uuids']])
    for r in q['exact_floor_widenings']:live[r['uuid']].SetWidth(r['width_nm'])
    group=next(g for g in b.Groups() if force._uid(g)==q['group_uuid'])
    group.SetName(consumer.PREFIX+'|'.join((q['root_pad_uuid'],q['anchor_uuid'],q['source_via_csv'])))
    token=repr((POLICY,q['source_sha256'],q['retired_track_uuids'],proposal['points_nm']))
    for i,(a,z) in enumerate(zip(proposal['points_nm'],proposal['points_nm'][1:])):
        t=pcbnew.PCB_TRACK(b);t.SetLayer(proposal['layer']);t.SetNetCode(b.GetNetcodeFromNetname(q['net']))
        t.SetWidth(proposal['width_nm']);t.SetLocked(True);t.SetStart(pcbnew.VECTOR2I(*a));t.SetEnd(pcbnew.VECTOR2I(*z))
        t.m_Uuid.Clone(pcbnew.KIID(str(uuid.uuid5(uuid.NAMESPACE_URL,token+str(i)))));b.Add(t);group.AddItem(t)
    capacity.additive._ground_refill(b);return b


def receive(source,candidate,proposal,*,board_hint):
    result=dict(ok=False,complete=False,errors=[],current_or_barrel_qualified=False,release_authority=False)
    try:
        q=proposal['scope'];fresh=plan(source,board_hint=board_hint,root_pad_uuid=q['root_pad_uuid'],
            retired_track_uuids=q['retired_track_uuids'],anchor_uuid=q['anchor_uuid'],layer=proposal['layer'],
            points_nm=proposal['points_nm'],launch_uuid=proposal['launch_uuid'])
        require(fresh==proposal,'stale_or_forged_native_consumer_feed_proposal')
        proof=original.receive(source,candidate,board_hint=board_hint,root_pad_uuid=q['root_pad_uuid'],retired_track_uuids=q['retired_track_uuids'],timeout_s=10.)
        require(proof['ok'] and proof['complete'] and not proof['errors'],str(proof['errors']))
        require(proof['derived_unchanged_design_budget']==q['budget'],'saved_original_input_budget_changed')
        current=debt.receive(source,candidate,board_hint=board_hint)
        require(current['ok'] and current['complete'],'native_consumer_feed_whole_current_debt_regression_or_unknown')
        result.update(ok=True,complete=True,independent_original_consumer_feed_receiving=proof,
            whole_parent_current_receiving=current,retired_track_uuids=proof['retired_track_uuids'],
            added_native_uuids=proof['incoming_track_uuids'],exact_floor_widenings=proof['exclusive_exact_floor_widenings'],
            source_sha256=force._hash(Path(source)),candidate_sha256=force._hash(Path(candidate)),
            exact_native_source_reconstruction=True,all_surviving_native_partitions_preserved=True,
            existing_aggregate_and_input_budgets_exact=True,new_vias=0,pads_moved=0,
            independent_native_kelvin_field_ground_pair_stack_and_release_receiving_still_required=True)
    except (ValueError,RuntimeError,KeyError,TypeError,OSError) as exc:result['errors'].append(type(exc).__name__+':'+str(exc))
    return result
