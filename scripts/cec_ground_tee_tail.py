"""Retire a pad-free dead GND leaf at a retained, plane-connected junction.

The old via-root tail operator stays unchanged. This distinct source owner
can stop at actual retained track copper, never traverse a live tee or delete
a load. No lock, group, pad, plane, via, mesh cycle or current budget is owned.
Every surviving native partition and proved short return is independently
received. Native DRC, fields, current and release gates remain separate.
"""
import time,math
import pcbnew
import cec_force_current as force
import cec_ground_dead_end_tail as tails
import cec_ground_return_shortcut as reference
import cec_ordinary_route_receiving as ordinary
from cec_cell_row_rebuild import _source_binding
from cec_native_items import discard_items


def plan(board,seed_uuid,*,ground_net='GND',timeout_s=10.,allow_locked_track_uuids=()):
    deadline=tails._deadline(timeout_s)
    if type(seed_uuid) is not str or not seed_uuid or type(ground_net) is not str or not ground_net:
        raise ValueError('literal_ground_tee_leaf_seed_required')
    allowed=ordinary._ids(allow_locked_track_uuids,'ground_tee_leaf_exact_source_lock_scope',8)
    tracks=list(board.GetTracks());pads=[p for f in board.GetFootprints() for p in f.Pads()]
    zones=[z for z in board.Zones() if not z.GetIsRuleArea()]
    if len(tracks)+len(pads)+len(zones)>16384:raise ValueError('ground_tee_leaf_inventory_bound')
    live={force._uid(t):t for t in tracks};seed=live.get(seed_uuid)
    if seed is None or seed.GetClass()!='PCB_TRACK' or seed.GetNetname()!=ground_net:
        raise ValueError('one_actual_source_ground_tee_leaf_track_required')
    face=int(seed.GetLayer());width=seed.GetWidth()
    if face not in (pcbnew.F_Cu,pcbnew.B_Cu) or not 0<width<=350000:
        raise ValueError('small_outer_ground_tee_leaf_required')
    grouped={force._uid(t) for g in board.Groups() for t in g.GetItems()}
    shapes={force._uid(t):t.GetEffectiveShape(face) for t in tracks if t.IsOnLayer(face)}
    def tick():
        if time.monotonic()>=deadline:raise ValueError('ground_tee_leaf_native_deadline')
    def peers(edge,point=None):
        shape=edge.GetEffectiveShape(face) if point is None else pcbnew.SHAPE_SEGMENT(
            pcbnew.VECTOR2I(*point),pcbnew.VECTOR2I(*point),width)
        return [t for uid,t in live.items() if uid!=force._uid(edge) and uid in shapes and shape.Collide(shapes[uid],0)]
    free=[tuple(p) for p in (seed.GetStart(),seed.GetEnd()) if not peers(seed,tuple(p))]
    if len(free)!=1:raise ValueError('one_actual_free_ground_leaf_tip_required')
    current=seed;point=free[0];retired=[];length=0.;root=None;contacts=None
    while True:
        tick();uid=force._uid(current);ends=[tuple(current.GetStart()),tuple(current.GetEnd())]
        if (current.GetClass()!='PCB_TRACK' or current.GetNetname()!=ground_net
                or current.IsLocked() and uid not in allowed or uid in grouped or current.GetParentGroup() or current.HasSolderMask()
                or current.GetWidth()!=width or current.GetLayer()!=face or point not in ends
                or ends[0]==ends[1] or uid in retired):
            raise ValueError('unlocked_ungrouped_uniform_pad_free_ground_leaf_required')
        retired.append(uid);length+=current.GetLength()/1e6
        if len(retired)>8 or length>12.:raise ValueError('ground_tee_leaf_scope_bound')
        shape=current.GetEffectiveShape(face)
        for item in [*pads,*zones]:
            tick()
            if not item.IsOnLayer(face):continue
            if item.GetClass()=='ZONE':
                if not item.IsFilled() or not item.HasFilledPolysForLayer(face):
                    if item.Outline().Collide(shape,0):raise ValueError('ground_tee_leaf_plane_fill_unknown')
                    continue
                other=item.GetFilledPolysList(face)
            else:other=item.GetEffectiveShape(face)
            if shape.Collide(other,0):raise ValueError('ground_tee_leaf_has_actual_land_or_plane_contact')
        far=ends[1] if point==ends[0] else ends[0]
        following=[t for t in peers(current) if force._uid(t) not in retired]
        if not following:raise ValueError('ground_tee_leaf_has_no_retained_root')
        if any(t.GetNetname()!=ground_net for t in following):raise ValueError('ground_tee_leaf_foreign_copper_contact')
        endpoint_peers=[t for t in following if t.GetClass()=='PCB_TRACK' and far in (
            tuple(t.GetStart()),tuple(t.GetEnd()))]
        # Sub-width connector caps can also touch the NEXT source edge. Walk
        # the literal endpoint path first, then independently inspect EVERY
        # retained native body contact against the final cut below. No actual
        # contact is rounded, omitted or mistaken for a second root.
        if len(endpoint_peers)==1:
            current,point=endpoint_peers[0],far;continue
        if any(t.GetClass()!='PCB_TRACK' for t in following):raise ValueError('retained_track_junction_not_barrel_or_land_required')
        for t in following:
            a,b=tuple(t.GetStart()),tuple(t.GetEnd());u=[b[i]-a[i] for i in (0,1)];v=[far[i]-a[i] for i in (0,1)]
            if u[0]*v[1]!=u[1]*v[0] or not 0<=sum(x*y for x,y in zip(u,v))<=sum(x*x for x in u):
                raise ValueError('literal_integer_retained_tee_contact_required')
        root=far;contacts=following;break
    cap=pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*root),pcbnew.VECTOR2I(*root),width)
    for uid in retired:
        for t in peers(live[uid]):
            tick()
            if force._uid(t) in retired:continue
            if (force._uid(t) not in {force._uid(p) for p in contacts}
                    or root not in (tuple(live[uid].GetStart()),tuple(live[uid].GetEnd()))
                    or not cap.Collide(shapes[force._uid(t)],0)):
                raise ValueError('ground_tee_leaf_has_unowned_retained_body_contact')
    if allowed!={u for u in retired if live[u].IsLocked()}:
        raise ValueError('only_exact_retired_ground_tee_leaf_source_locks_may_be_authorized')
    sheet=pcbnew.SHAPE_POLY_SET()
    for uid in retired:
        tick();part=pcbnew.SHAPE_POLY_SET()
        live[uid].TransformShapeToPolygon(part,face,0,1000,pcbnew.ERROR_INSIDE)
        sheet.BooleanAdd(part)
    import cec_kelvin_copper_cut as physical
    try:actual=physical._poly(sheet,physical._Work(deadline))
    except physical.Unknown as exc:raise ValueError('ground_tee_leaf_native_inside_sheet_unknown') from exc
    if actual.geom_type!='Polygon' or actual.is_empty or len(actual.interiors):
        raise ValueError('one_hole_free_native_ground_tee_leaf_required')
    # The retained source, with the complete leaf absent, must still reach a
    # real unchanged through barrel and every declared saved GND reference.
    graph=pcbnew.CONNECTIVITY_DATA();ground_items=[t for t in [*tracks,*pads,*zones]
        if t.GetNetname()==ground_net and force._uid(t) not in retired]
    for item in ground_items:
        tick()
        if item.GetClass()=='ZONE' and not item.IsFilled():raise ValueError('retained_ground_tee_reference_fill_unknown')
        if not graph.Add(item):raise ValueError('retained_ground_tee_native_graph_unknown')
    reached={force._uid(t) for t in graph.GetConnectedItems(contacts[0])}|{force._uid(contacts[0])}
    if not {force._uid(t) for t in contacts}<=reached:raise ValueError('retained_ground_tee_contacts_are_not_one_native_component')
    vias=[t for t in tracks if force._uid(t) in reached and t.GetClass()=='PCB_VIA'
        and t.GetViaType()==pcbnew.VIATYPE_THROUGH]
    witness=None
    for via in sorted(vias,key=lambda v:(math.dist(tuple(v.GetPosition()),root),force._uid(v))):
        tick()
        try:planes=reference._reference_contacts(board,via)
        except ValueError:continue
        witness=(via,planes);break
    if witness is None:raise ValueError('retained_ground_tee_has_no_actual_saved_reference_entry')
    tick()
    return dict(schema=1,kind='pad_free_dead_ground_leaf_at_retained_native_tee',seed_uuid=seed_uuid,
        ground_net=ground_net,source_binding=_source_binding(board),retired_track_uuids=retired,
        allow_locked_track_uuids=sorted(allowed),
        retained_tee_track_uuids=sorted(force._uid(t) for t in contacts),root_position_nm=list(root),
        retained_root_via_uuid=force._uid(witness[0]),root_plane_contacts=witness[1],
        source_layer=face,source_width_nm=width,source_length_mm=length,
        actual_inside_sheet_outlines=1,actual_inside_sheet_holes=0,
        no_live_terminal_or_retained_ground_mesh_owned=True,current_qualified=False,release_authority=False)


def subtract(board,proposal,*,timeout_s=10.):
    fresh=plan(board,proposal['seed_uuid'],ground_net=proposal['ground_net'],timeout_s=timeout_s,
        allow_locked_track_uuids=proposal['allow_locked_track_uuids'])
    if fresh!=proposal:raise ValueError('ground_tee_leaf_stale_or_forged_plan')
    discard_items(board,[t for t in board.GetTracks() if force._uid(t) in fresh['retired_track_uuids']])


def receive(source,candidate,proposal,*,board_hint,timeout_s=10.):
    return tails._receive_exact_subtraction(source,candidate,proposal,board_hint=board_hint,
        subtractor=subtract,timeout_s=timeout_s)
