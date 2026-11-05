"""Cut one pad-free dead spur, never its retained ground mesh or return.

Flooding all equal-width contacts wrongly treats a tiny dangling spur as
part of the adjacent cyclic mesh. Instead prove its one free native cap,
cluster every retained contact without the seed, and reach a real saved
plane through retained copper. Independent exact saved subtraction still
preserves every surviving partition and already-proved local ground return.
"""
from collections import deque
import time
import pcbnew
import cec_force_current as force
import cec_ground_dead_end_tail as tails
from cec_cell_row_rebuild import _source_binding
from cec_native_items import discard_items


def plan(board,seed_uuid,*,ground_net='GND',timeout_s=10.):
    deadline=tails._deadline(timeout_s)
    if type(seed_uuid) is not str or not seed_uuid or type(ground_net) is not str or not ground_net:
        raise ValueError('literal_ground_mesh_spur_scope_required')
    tracks=list(board.GetTracks());pads=[p for f in board.GetFootprints() for p in f.Pads()]
    zones=[z for z in board.Zones() if not z.GetIsRuleArea()]
    if len(tracks)+len(pads)+len(zones)>16384:raise ValueError('ground_mesh_spur_inventory_bound')
    live={force._uid(t):t for t in tracks};seed=live.get(seed_uuid)
    if (seed is None or seed.GetClass()!='PCB_TRACK' or seed.GetNetname()!=ground_net
            or seed.IsLocked() or seed.GetParentGroup() is not None
            or any(g.ContainsItem(seed) for g in board.Groups())
            or seed.GetLayer() not in (pcbnew.F_Cu,pcbnew.B_Cu)
            or not 0<seed.GetWidth()<=350000 or not 0<seed.GetLength()<=3500000):
        raise ValueError('one_small_unlocked_ungrouped_outer_ground_spur_required')
    layer=int(seed.GetLayer());width=int(seed.GetWidth());body=seed.GetEffectiveShape(layer)
    ends=[tuple(seed.GetStart()),tuple(seed.GetEnd())]
    caps=[pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*p),pcbnew.VECTOR2I(*p),width) for p in ends]
    def tick():
        if time.monotonic()>=deadline:raise ValueError('ground_mesh_spur_native_contact_deadline')
    planes=[]
    for item in [*pads,*zones]:
        tick()
        if item.GetClass()=='ZONE':
            if item.GetNetname()==ground_net:
                if not item.IsFilled():raise ValueError('ground_mesh_spur_saved_plane_unknown')
                planes.append(item)
            if not item.IsOnLayer(layer):continue
            if not item.HasFilledPolysForLayer(layer):
                if item.Outline().Collide(body,0):raise ValueError('ground_mesh_spur_contact_material_unknown')
                continue
            shape=item.GetFilledPolysList(layer)
        else:
            if not item.IsOnLayer(layer):continue
            shape=item.GetEffectiveShape(layer)
        if shape.Collide(body,0):raise ValueError('ground_mesh_spur_has_actual_land_or_zone_contact')
    if not planes:raise ValueError('ground_mesh_spur_saved_ground_plane_required')
    material={force._uid(t):t for t in sorted(tracks,key=force._uid) if force._uid(t)!=seed_uuid
        and t.GetNetname()==ground_net and t.IsOnLayer(layer)}
    shapes={u:t.GetEffectiveShape(layer) for u,t in material.items()}
    contacts=set();cap_contacts=[set(),set()]
    for item in tracks:
        tick();uid=force._uid(item)
        if uid==seed_uuid or not item.IsOnLayer(layer):continue
        shape=item.GetEffectiveShape(layer)
        if not shape.Collide(body,0):continue
        if item.GetNetname()!=ground_net:raise ValueError('ground_mesh_spur_foreign_copper_contact')
        contacts.add(uid)
        for i,cap in enumerate(caps):
            if shape.Collide(cap,0):cap_contacts[i].add(uid)
    if not contacts or sorted(map(len,cap_contacts))!=[0,len(contacts)]:
        raise ValueError('one_free_cap_and_one_retained_native_contact_cluster_required')
    root_index=next(i for i,c in enumerate(cap_contacts) if c)
    # Keep the mesh. Every seed contact must remain mutually connected by
    # actual native same-face bodies after subtraction, not through a pad,
    # a projected plane owner ID, or the removed spur itself.
    first=min(contacts);parents={first:None};queue=deque([first]);witness=None;plane_ids=[]
    while queue:
        tick();uid=queue.popleft();item=material[uid]
        if item.GetClass()=='PCB_VIA' and item.GetViaType()==pcbnew.VIATYPE_THROUGH:
            for zone in planes:
                for face in board.GetEnabledLayers().CuStack():
                    tick()
                    if (zone.IsOnLayer(face) and item.IsOnLayer(face)
                            and zone.HasFilledPolysForLayer(face)
                            and zone.GetFilledPolysList(face).Collide(item.GetEffectiveShape(face),0)):
                        if witness is None:witness=uid
                        if witness==uid:plane_ids.append(force._uid(zone))
        if witness is not None and contacts<=parents.keys():break
        for other,shape in shapes.items():
            tick()
            if other not in parents and shapes[uid].Collide(shape,0):
                parents[other]=uid;queue.append(other)
                if len(parents)>128:raise ValueError('ground_mesh_spur_retained_path_bound')
    if witness is None or not contacts<=parents.keys():
        raise ValueError('retained_contacts_not_one_saved_plane_connected_mesh')
    path=[witness]
    while parents[path[-1]] is not None:path.append(parents[path[-1]])
    path.reverse()
    return dict(schema=1,kind='one_pad_free_dead_spur_at_retained_ground_mesh',
        seed_uuid=seed_uuid,ground_net=ground_net,source_binding=_source_binding(board),
        retired_track_uuids=[seed_uuid],retained_root_via_uuid=witness,
        retained_contact_uuids=sorted(contacts),retained_plane_path_uuids=path,
        root_point_nm=list(ends[root_index]),free_point_nm=list(ends[1-root_index]),
        root_plane_uuids=sorted(set(plane_ids)),source_layer=layer,source_width_nm=width,
        source_length_mm=seed.GetLength()/1e6,retained_mesh_never_pruned=True,
        current_qualified=False,release_authority=False)


def subtract(board,proposal,*,timeout_s=10.):
    fresh=plan(board,proposal['seed_uuid'],ground_net=proposal['ground_net'],timeout_s=timeout_s)
    if fresh!=proposal:raise ValueError('ground_mesh_spur_stale_or_forged_source_plan')
    discard_items(board,[t for t in board.GetTracks() if force._uid(t)==fresh['seed_uuid']])


def receive(source,candidate,proposal,*,board_hint,timeout_s=10.):
    return tails._receive_exact_subtraction(source,candidate,proposal,board_hint=board_hint,
        subtractor=subtract,timeout_s=timeout_s)
