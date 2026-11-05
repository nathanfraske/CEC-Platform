"""Exact dead ground leaf at an unchanged, qualified in-pad return.

This is not ground-mesh pruning. A bounded unlocked linear leaf may contact
only one retained SMD land, its existing in-pad through barrel, and retained
ground leads whose ENTIRE contact with the leaf is inside that land. Those
leads must already contact the retained barrel and land without the leaf.
No live return, pad, barrel, plane, current rating or factory rule changes.
"""
import time
import pcbnew
import cec_force_current as force
import cec_fab_profile as fab
import cec_ground_dead_end_tail as tails
from cec_ground_dead_end_tree import tree_vertices
from cec_cell_row_rebuild import _source_binding
from cec_native_items import discard_items


def plan(board,seed_uuid,*,track_uuids,ground_net='GND',timeout_s=10.):
    deadline=tails._deadline(timeout_s)
    if (type(track_uuids) not in (list,tuple) or not 1<=len(track_uuids)<=8
            or any(type(u) is not str or not u for u in track_uuids)
            or len(set(track_uuids))!=len(track_uuids) or type(seed_uuid) is not str
            or seed_uuid not in track_uuids or type(ground_net) is not str or not ground_net):
        raise ValueError('bounded_exact_ground_inpad_leaf_scope_required')
    tracks=list(board.GetTracks());pads=[p for f in board.GetFootprints() for p in f.Pads()]
    zones=[z for z in board.Zones() if not z.GetIsRuleArea()]
    if len(tracks)+len(pads)+len(zones)>16384:raise ValueError('ground_inpad_leaf_native_inventory_bound')
    by_id={force._uid(t):t for t in tracks}
    if not set(track_uuids)<=by_id.keys():raise ValueError('source_ground_inpad_leaf_item_missing')
    material=[by_id[u] for u in sorted(track_uuids)]
    if any(t.GetClass()!='PCB_TRACK' for t in material):
        raise ValueError('actual_track_only_ground_inpad_leaf_required')
    layers={int(t.GetLayer()) for t in material}
    if len(layers)!=1:raise ValueError('one_outer_ground_inpad_leaf_face_required')
    face=next(iter(layers));widths={t.GetWidth() for t in material}
    grouped={force._uid(i) for g in board.Groups() for i in g.GetItems()}
    if (face not in (pcbnew.F_Cu,pcbnew.B_Cu) or len(widths)!=1 or not 0<next(iter(widths))<=350000
            or any(t.GetClass()!='PCB_TRACK' or t.GetNetname()!=ground_net or t.GetNetCode()<=0
                or t.IsLocked() or force._uid(t) in grouped or t.GetParentGroup() is not None for t in material)):
        raise ValueError('unlocked_ungrouped_uniform_small_outer_ground_leaf_required')
    length=sum(t.GetLength()/1e6 for t in material)
    if not 0<length<=12.:raise ValueError('ground_inpad_leaf_length_bound')
    degree=tree_vertices([(list(t.GetStart()),list(t.GetEnd())) for t in material])
    ends=[at for at,n in degree.items() if n==1]
    if len(ends)!=2 or any(n>2 for n in degree.values()):raise ValueError('one_endpoint_linear_ground_inpad_leaf_required')
    def tick():
        if time.monotonic()>=deadline:raise ValueError('ground_inpad_leaf_contact_deadline')
    def polygon(item,inside=False):
        poly=pcbnew.SHAPE_POLY_SET()
        item.TransformShapeToPolygon(poly,face,0,1000,pcbnew.ERROR_INSIDE if inside else pcbnew.ERROR_OUTSIDE,False)
        return poly
    outside=pcbnew.SHAPE_POLY_SET();inside=pcbnew.SHAPE_POLY_SET()
    for t in material:outside.BooleanAdd(polygon(t));inside.BooleanAdd(polygon(t,True))
    # Exact endpoint trees can still have a geometric loop or remote body
    # contact. Require one real simply connected inside sheet as well.
    import cec_kelvin_copper_cut as physical
    work=physical._Work(deadline);sheet=physical._poly(inside,work);physical._validate_linear_epochs(work)
    if sheet.geom_type!='Polygon' or sheet.is_empty or len(sheet.interiors):
        raise ValueError('ground_inpad_leaf_one_hole_free_native_sheet_required')
    contacts=[]
    for item in [*tracks,*pads,*zones]:
        tick()
        if force._uid(item) in track_uuids or not item.IsOnLayer(face):continue
        if item.GetClass()=='ZONE':
            if not item.IsFilled() or not item.HasFilledPolysForLayer(face):
                if item.Outline().Collide(outside,0):raise ValueError('ground_inpad_leaf_contact_fill_unknown')
                continue
            shape=item.GetFilledPolysList(face)
        else:shape=item.GetEffectiveShape(face)
        if not any(shape.Collide(t.GetEffectiveShape(face),0) for t in material):continue
        if item.GetNetname()!=ground_net:raise ValueError('ground_inpad_leaf_foreign_copper_contact')
        contacts.append(item)
    lands=[p for p in contacts if p.GetClass()=='PAD'];barrels=[v for v in contacts if v.GetClass()=='PCB_VIA']
    if len(lands)!=1 or len(barrels)!=1:raise ValueError('one_retained_actual_smd_land_and_return_barrel_required')
    pad,via=lands[0],barrels[0]
    if (pad.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD or tuple(pad.GetLayerSet().CuStack())!=(face,)
            or via.GetViaType()!=pcbnew.VIATYPE_THROUGH or via.TopLayer()!=pcbnew.F_Cu or via.BottomLayer()!=pcbnew.B_Cu):
        raise ValueError('actual_outer_smd_through_ground_return_required')
    ok,reason=fab.local_pofv_via_decision(board,via)
    if (not ok or reason!='fully contained same-net SMD POFV'
            or not fab._pad_contains_circle(pad,via.GetPosition(),via.GetWidth(via.TopLayer())/2+1000,tolerance_nm=0)):
        raise ValueError('positive_contained_factory_ground_return_required')
    root_ends=[at for at in ends if pad.HitTest(pcbnew.VECTOR2I(*at)) and via.HitTest(pcbnew.VECTOR2I(*at))]
    if len(root_ends)!=1:raise ValueError('one_exact_leaf_root_inside_retained_land_and_barrel_required')
    retained=[];pad_inside=polygon(pad,True)
    for item in contacts:
        if item is pad or item is via:continue
        tick()
        if (item.GetClass()!='PCB_TRACK' or not item.GetEffectiveShape(face).Collide(pad.GetEffectiveShape(face),0)
                or not item.GetEffectiveShape(face).Collide(via.GetEffectiveShape(face),0)):
            raise ValueError('retained_ground_contact_not_independently_rooted_at_same_land_and_barrel')
        overlap=pcbnew.SHAPE_POLY_SET(outside);overlap.BooleanIntersection(polygon(item));overlap.BooleanSubtract(pad_inside)
        if overlap.OutlineCount():raise ValueError('ground_leaf_contacts_retained_lead_outside_actual_root_land')
        retained.append(force._uid(item))
    planes=[]
    for zone in zones:
        if zone.GetNetname()!=ground_net:continue
        for layer in board.GetEnabledLayers().CuStack():
            tick()
            if not zone.IsOnLayer(layer):continue
            if not zone.IsFilled() or not zone.HasFilledPolysForLayer(layer):raise ValueError('ground_inpad_leaf_root_plane_unknown')
            if zone.GetFilledPolysList(layer).Collide(via.GetEffectiveShape(layer),0):planes.append((force._uid(zone),int(layer)))
    if not planes:raise ValueError('ground_inpad_leaf_has_no_retained_saved_plane_contact')
    return dict(schema=1,kind='whole_dead_ground_leaf_at_retained_inpad_return',seed_uuid=seed_uuid,
        source_binding=_source_binding(board),ground_net=ground_net,retired_track_uuids=sorted(track_uuids),
        retained_root_pad_uuid=force._uid(pad),retained_root_via_uuid=force._uid(via),
        retained_independent_root_lead_uuids=sorted(retained),root_position_nm=list(root_ends[0]),
        source_layer=face,source_width_nm=next(iter(widths)),source_length_mm=length,
        root_plane_contacts=[list(x) for x in sorted(set(planes))],inpad_process_geometry=reason,
        all_actual_pad_barrel_and_functional_return_geometry_retained=True,
        current_qualified=False,release_authority=False,independent_saved_receiving_required=True)


def subtract(board,proposal,*,timeout_s=10.):
    fresh=plan(board,proposal['seed_uuid'],track_uuids=proposal['retired_track_uuids'],
        ground_net=proposal['ground_net'],timeout_s=timeout_s)
    if fresh!=proposal:raise ValueError('ground_inpad_leaf_stale_or_forged_plan')
    discard_items(board,[t for t in board.GetTracks() if force._uid(t) in fresh['retired_track_uuids']])


def receive(source,candidate,proposal,*,board_hint,timeout_s=10.):
    return tails._receive_exact_subtraction(source,candidate,proposal,board_hint=board_hint,
        subtractor=subtract,timeout_s=timeout_s)
