"""Native-fill look-ahead, without arbitrary-angle projection of new copper.

The exact old fills are always appended literally. Local windows are derived
from canonical authored pockets and the unchanged process feature dimension.
The source silhouette is an independent REJECTION constraint, never a shape
to clip into the emitted board. Every original whole-board gate remains due.
"""
import hashlib
import time
import pcbnew
import cec_force_current as force
import cec_rectilinear_copper as native
import cec_regional_fill as regional
import cec_reentrant_pocket_geometry as geometry

def fill_edge_direction(a,z):
    """Disclose a one-DBU fill tessellation class; never snap a track/edge."""
    if native._centerline_allowed(a,z,'chamfer45'):return 'literal_octilinear'
    dx,dy=[abs(z[k]-a[k]) for k in (0,1)]
    if min(dx,dy)>=1000 and abs(dx-dy)==1:return 'native_single_grid_45_tessellation'
    return 'noncanonical'

def emit(source,records,*,support_mode='local_overlap',refill_ground=True):
    before,after=[pcbnew.LoadBoard(str(source)) for _ in range(2)]
    original={force._uid(z):z for z in before.Zones()};zones={force._uid(z):z for z in after.Zones()}
    selected=pcbnew.ZONES()
    for row in records:
        z=zones[row['zone_uuid']];z.UnFill();z.Outline().RemoveAllContours();z.Outline().Append(native._poly(row['points_nm']));selected.append(z)
    import cec_zone_fill
    cec_zone_fill.compile_selected(after,selected,timeout_s=10.)
    for row in records:
        z=zones[row['zone_uuid']];old=original[row['zone_uuid']];c=row['source_configuration'];face=c['layers'][0]
        compiled=z.GetFilledPolysList(face).CloneDropTriangulation()
        compiled.BooleanIntersection(geometry.local_mask(old.GetFilledPolysList(face),row['source_points_nm'],row['points_nm'],c['min_thickness_nm']))
        result=regional._combine(before,compiled,row['regional_combination_contract'],time.monotonic()+10.)
        flags=row['regional_combination_contract']['regional_fill_binding']['source_islands']
        for i in reversed(range(result.OutlineCount()-len(flags),result.OutlineCount())):result.RemoveOutline(i)
        guard=geometry.addition_window(row['source_points_nm'],row['points_nm'],c['min_thickness_nm'])
        guard.Inflate(-1000,pcbnew.CORNER_STRATEGY_CHAMFER_ALL_CORNERS,1);result.BooleanIntersection(guard)
        if support_mode=='inset_copy':
            support=old.GetFilledPolysList(face).CloneDropTriangulation()
            support.Inflate(-1000,pcbnew.CORNER_STRATEGY_CHAMFER_ALL_CORNERS,1);result.BooleanAdd(support)
        elif support_mode!='local_overlap':raise ValueError('literal_native_preflight_support_mode_required')
        # No hull clipping: it generated new non-45-degree exterior chords.
        result=regional.anchored_native_additions(before,result,net=c['net'],layer=face,
            source_zone_uuids=[row['zone_uuid']],deadline=time.monotonic()+10.)
        result.Fracture();result.Append(old.GetFilledPolysList(face))
        z.UnFill();z.SetFilledPolysList(face,result);z.SetIsFilled(True)
        for i,flag in enumerate(flags):
            if flag:z.SetIsIsland(face,result.OutlineCount()-len(flags)+i)
    if refill_ground:
        faces={r['source_configuration']['layers'][0] for r in records};grounds=pcbnew.ZONES()
        for z in after.Zones():
            if not z.GetIsRuleArea() and z.GetNetname()=='GND' and any(z.IsOnLayer(face) for face in faces):grounds.append(z)
        if grounds.size():cec_zone_fill.compile_selected(after,grounds,timeout_s=10.)
    return after

def source_material(board,net,face,deadline):
    """Literal native old metal for hiding internal, already-existing edges."""
    out=pcbnew.SHAPE_POLY_SET();items=[*board.GetTracks(),*[p for fp in board.GetFootprints() for p in fp.Pads()],*board.Zones()]
    if len(items)>16384:raise ValueError('finite_preflight_source_material_inventory_required')
    count=0
    for item in items:
        native._check_deadline(deadline)
        if item.GetNetname()!=net or not item.IsOnLayer(face):continue
        if item.GetClass()=='ZONE':
            if item.GetIsRuleArea():continue
            if not item.IsFilled() or not item.HasFilledPolysForLayer(face):raise ValueError('preflight_source_fill_unknown')
            poly=item.GetFilledPolysList(face).CloneDropTriangulation()
        else:
            poly=pcbnew.SHAPE_POLY_SET();item.TransformShapeToPolygon(poly,face,0,1,pcbnew.ERROR_INSIDE,False)
            if item.GetClass()=='PCB_VIA' or item.GetClass()=='PAD' and item.HasHole():
                hole=pcbnew.SHAPE_POLY_SET();item.GetEffectiveHoleShape().TransformToPolygon(hole,1,pcbnew.ERROR_OUTSIDE);poly.BooleanSubtract(hole)
        count+=1
        if count>512:raise ValueError('finite_preflight_net_material_bound')
        out.Append(poly)
    return out

def observe(before,after,row,*,timeout_s=10.):
    """Reject spurs/long new noncanonical boundaries in real compiled fill.

    Short native fillet tessellation at the unchanged feature scale is not a
    substitute for straight-edge proof. All short edges stay disclosed and
    actual final visual review is mandatory; no manufacturing rule is waived.
    """
    deadline=time.monotonic()+timeout_s;c=row['source_configuration'];face=c['layers'][0]
    old=next(z for z in before.Zones() if force._uid(z)==row['zone_uuid'])
    new=next(z for z in after.Zones() if force._uid(z)==row['zone_uuid'])
    full=new.GetFilledPolysList(face);extra=full.CloneDropTriangulation();count=old.GetFilledPolysList(face).OutlineCount()
    for i in reversed(range(extra.OutlineCount()-count,extra.OutlineCount())):extra.RemoveOutline(i)
    fresh=extra.CloneDropTriangulation();fresh.BooleanSubtract(old.GetFilledPolysList(face))
    support=pcbnew.SHAPE_POLY_SET()
    for selected in row['selected_offers']:
        native._check_deadline(deadline)
        support.BooleanAdd(native._poly(geometry.visible_support_envelope(before,c['net'],face,selected['offer']['source_window_nm'])))
    spur=fresh.CloneDropTriangulation();spur.BooleanSubtract(support)
    if spur.OutlineCount():raise ValueError('native_fill_preflight_new_exterior_spur')
    material=source_material(before,c['net'],face,deadline)
    visible=fresh.CloneDropTriangulation();visible.BooleanSubtract(material)
    visible_area_mm2=visible.Area()/1e12
    if visible_area_mm2<.0025:raise ValueError('native_fill_preflight_no_actual_visible_interest_area')
    long=[];short=0;hidden=0;edges=0;native_grid=0
    for i in range(extra.OutlineCount()):
        for ring in [extra.Outline(i),*[extra.Hole(i,j) for j in range(extra.HoleCount(i))]]:
            points=[[ring.CPoint(j).x,ring.CPoint(j).y] for j in range(ring.PointCount())]
            if ring.ArcCount():raise ValueError('linear_native_preflight_boundary_required')
            for a,z in zip(points,points[1:]+points[:1]):
                native._check_deadline(deadline);edges+=1
                if edges>200000:raise ValueError('bounded_native_preflight_boundary_work_required')
                direction=fill_edge_direction(a,z)
                if a==z or direction=='literal_octilinear':continue
                if direction=='native_single_grid_45_tessellation':native_grid+=1;continue
                if sum((a[k]-z[k])**2 for k in (0,1))<=c['min_thickness_nm']**2:short+=1;continue
                witness=pcbnew.PCB_TRACK(before);witness.SetLayer(face);witness.SetWidth(100)
                witness.SetStart(pcbnew.VECTOR2I(*a));witness.SetEnd(pcbnew.VECTOR2I(*z))
                line=pcbnew.SHAPE_POLY_SET();witness.TransformShapeToPolygon(line,face,0,1,pcbnew.ERROR_INSIDE,False)
                line.BooleanSubtract(material)
                if line.OutlineCount():long.append(dict(start_nm=a,end_nm=z))
                else:hidden+=1
    if long:raise ValueError('native_fill_preflight_new_long_noncanonical_boundary:'+str(long[:2]))
    return dict(ok=True,complete=True,no_new_exterior_spur=True,no_new_long_noncanonical_exposed_boundary=True,
        native_fill_polygon_sha256=hashlib.sha256(full.Format().encode()).hexdigest(),boundary_edges_inspected=edges,
        short_noncanonical_native_edges_disclosed=short,old_material_hidden_long_edges=hidden,
        native_single_grid_45_filled_edges_disclosed=native_grid,
        actual_visible_interest_area_mm2=visible_area_mm2,track_centerline_angle_tolerance_nm=0,
        source_feature_scale_nm=c['min_thickness_nm'],arbitrary_angle_hull_projection_used=False,
        final_visual_and_all_whole_board_gates_still_required=True,release_authority=False)
