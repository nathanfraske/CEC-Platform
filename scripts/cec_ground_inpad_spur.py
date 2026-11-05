"""Remove one source-proved dead GND spur at a retained in-pad return.

This does not rip up a mesh, shorten a real return, retire a via, or qualify
current/PI. The small unlocked/ungrouped track has one contact-free tip and
contacts ONLY one SMD GND land and its fully contained qualified return via.
The filled ground planes, land, via, all source partitions and every proved
short ground return must survive independent saved replay. Native DRC, field,
current, and release checks remain separate and mandatory.
"""
import time
import pcbnew
import cec_fab_profile as fab
import cec_force_current as force
import cec_ground_dead_end_tail as tails
from cec_cell_row_rebuild import _source_binding
from cec_native_items import discard_items


def plan(board, seed_uuid, *, ground_net='GND', timeout_s=10.):
    deadline=tails._deadline(timeout_s)
    if type(seed_uuid) is not str or not seed_uuid or type(ground_net) is not str or not ground_net:
        raise ValueError('explicit_ground_spur_source_identity_required')
    tracks=list(board.GetTracks());pads=[p for f in board.GetFootprints() for p in f.Pads()]
    zones=[z for z in board.Zones() if not z.GetIsRuleArea()]
    if len(tracks)+len(pads)+len(zones)>16384:raise ValueError('ground_spur_native_inventory_bound')
    matches=[t for t in tracks if force._uid(t)==seed_uuid]
    if len(matches)!=1:raise ValueError('unique_actual_ground_spur_required')
    edge=matches[0]
    if (edge.GetClass()!='PCB_TRACK' or str(edge.GetNetname())!=ground_net
            or edge.GetNetCode()<=0 or edge.IsLocked() or edge.GetParentGroup() is not None
            or any(g.ContainsItem(edge) for g in board.Groups())
            or not 0<edge.GetWidth()<=350000 or not 0<edge.GetLength()<=3500000
            or edge.GetLayer() not in (pcbnew.F_Cu,pcbnew.B_Cu)):
        raise ValueError('small_unlocked_ungrouped_outer_ground_spur_required')
    layer=int(edge.GetLayer());ends=[tuple(edge.GetStart()),tuple(edge.GetEnd())]
    actual=[];caps=[[],[]]
    for item in [*tracks,*pads,*zones]:
        if time.monotonic()>=deadline:raise ValueError('ground_spur_contact_deadline')
        if force._uid(item)==seed_uuid or not item.IsOnLayer(layer):continue
        if item.GetClass()=='ZONE':
            if not item.IsFilled() or not item.HasFilledPolysForLayer(layer):
                if item.Outline().Collide(edge.GetEffectiveShape(layer),0):
                    raise ValueError('ground_spur_saved_plane_material_unknown')
                continue
            shape=item.GetFilledPolysList(layer)
        else:shape=item.GetEffectiveShape(layer)
        if not shape.Collide(edge.GetEffectiveShape(layer),0):continue
        actual.append(item)
        for index,at in enumerate(ends):
            if shape.Collide(pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*at),pcbnew.VECTOR2I(*at),edge.GetWidth()),0):
                caps[index].append(force._uid(item))
    if len(actual)!=2 or sorted(map(len,caps))!=[0,2]:
        raise ValueError('one_free_tip_and_only_retained_land_via_contacts_required')
    root_pads=[i for i in actual if i.GetClass()=='PAD'];root_vias=[i for i in actual if i.GetClass()=='PCB_VIA']
    if len(root_pads)!=1 or len(root_vias)!=1:raise ValueError('retained_smd_land_and_inpad_via_required')
    pad,via=root_pads[0],root_vias[0]
    if (pad.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD or tuple(pad.GetLayerSet().CuStack())!=(layer,)
            or pad.GetNetCode()!=edge.GetNetCode() or via.GetNetCode()!=edge.GetNetCode()
            or via.GetViaType()!=pcbnew.VIATYPE_THROUGH
            or via.TopLayer()!=pcbnew.F_Cu or via.BottomLayer()!=pcbnew.B_Cu):
        raise ValueError('same_net_actual_outer_smd_through_return_required')
    root_index=next(i for i,c in enumerate(caps) if c)
    root=pcbnew.VECTOR2I(*ends[root_index])
    if not pad.HitTest(root) or not via.HitTest(root):
        raise ValueError('ground_spur_root_must_be_inside_actual_pad_and_via')
    ok,reason=fab.local_pofv_via_decision(board,via)
    if (not ok or reason!='fully contained same-net SMD POFV'
            or not fab._pad_contains_circle(pad,via.GetPosition(),via.GetWidth(via.TopLayer())/2+1000,tolerance_nm=0)):
        raise ValueError('positive_fully_contained_qualified_inpad_return_required')
    observed=[]
    for zone in zones:
        if zone.GetNetCode()!=edge.GetNetCode():continue
        for face in board.GetEnabledLayers().CuStack():
            if zone.IsOnLayer(face):
                if not zone.IsFilled() or not zone.HasFilledPolysForLayer(face):
                    raise ValueError('retained_ground_plane_fill_unknown')
                if zone.GetFilledPolysList(face).Collide(via.GetEffectiveShape(face),0):
                    observed.append((force._uid(zone),int(face)))
    if not observed:raise ValueError('retained_inpad_via_has_no_saved_ground_plane_contact')
    return dict(schema=1,kind='one_dead_ground_spur_at_retained_inpad_return',
        source_binding=_source_binding(board),seed_uuid=seed_uuid,ground_net=ground_net,
        retired_track_uuids=[seed_uuid],retained_root_via_uuid=force._uid(via),
        retained_root_pad_uuid=force._uid(pad),source_layer=layer,source_width_nm=edge.GetWidth(),
        removed_length_mm=edge.GetLength()/1e6,root_position_nm=list(root),
        inpad_process_geometry=reason,observed_plane_contacts=[list(row) for row in sorted(set(observed))],
        plane_contact_observation_is_not_independent_current_or_PI_qualification=True,
        independent_saved_receiving_required=True,current_qualified=False,release_authority=False)


def subtract(board,proposal,*,timeout_s=10.):
    fresh=plan(board,proposal['seed_uuid'],ground_net=proposal['ground_net'],timeout_s=timeout_s)
    if fresh!=proposal:raise ValueError('ground_spur_stale_or_forged_source_plan')
    discard_items(board,[t for t in board.GetTracks() if force._uid(t)==fresh['seed_uuid']])


def receive(source,candidate,proposal,*,board_hint,timeout_s=10.):
    return tails._receive_exact_subtraction(source,candidate,proposal,
        board_hint=board_hint,subtractor=subtract,timeout_s=timeout_s)
