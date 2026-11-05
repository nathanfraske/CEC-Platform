"""Conservative visible net-addition observation INCLUDING native copper art.

This observes real progress only. It grants no electrical/current/reference
qualification and changes no clipped-cut gate. Source copper art of ANY net
is conservatively included as already occupied metal, never silently omitted.
"""
import math
import time
import pcbnew
from shapely.ops import unary_union
import cec_kelvin_copper_cut as physical
import cec_board_geometry as outline

def inventory(board,work):
    pads=[];graphics=[]
    for fp in board.GetFootprints():
        work.tick();pads.extend(fp.Pads());graphics.extend(fp.GraphicalItems());graphics.extend(fp.GetFields())
        if len(pads)+len(graphics)>physical.MAX_ITEMS:raise ValueError('graphic_progress_native_inventory_bound')
    tracks=list(board.GetTracks());zones=[z for z in board.Zones() if not z.GetIsRuleArea()]
    graphics.extend(board.GetDrawings())
    if len(pads)+len(tracks)+len(zones)+len(graphics)>physical.MAX_ITEMS:raise ValueError('graphic_progress_native_inventory_bound')
    return pads,tracks,zones,graphics

def compare(source,candidate,*,net,layer_ids,timeout_s=10.):
    result=dict(ok=False,complete=False,errors=[],faces=[],scope='conservative_native_graphic_aware_visible_net_addition',
        electrical_current_reference_or_release_qualified=False,original_clipped_cut_gate_changed=False,
        source_art_is_actual_native_polygon_not_a_bounding_box=True)
    try:
        if (type(net) is not str or not net or type(layer_ids) not in (list,tuple) or len(layer_ids)!=1
                or type(layer_ids[0]) is not int or type(timeout_s) not in (int,float)
                or not math.isfinite(timeout_s) or not 0<timeout_s<=10.):raise ValueError('finite_graphic_aware_progress_scope_required')
        face=layer_ids[0]
        if tuple(source.GetEnabledLayers().CuStack())!=tuple(candidate.GetEnabledLayers().CuStack()) or face not in source.GetEnabledLayers().CuStack():
            raise ValueError('same_actual_native_copper_stack_required')
        deadline=time.monotonic()+timeout_s;before=physical._Work(deadline);after=physical._Work(deadline)
        pads,tracks,zones,graphics=inventory(source,before)
        npads,ntracks,nzones,ngraphics=inventory(candidate,after)
        olditems=[i for i in pads+tracks if i.GetNetname()==net and i.IsOnLayer(face)]
        oldzones=[z for z in zones if z.GetNetname()==net and z.IsOnLayer(face)]
        newitems=[i for i in npads+ntracks if i.GetNetname()==net and i.IsOnLayer(face)]
        newzones=[z for z in nzones if z.GetNetname()==net and z.IsOnLayer(face)]
        if max(len(olditems)+len(oldzones),len(newitems)+len(newzones))>physical.MAX_NET_ITEMS:
            raise ValueError('graphic_progress_same_native_net_item_bound')
        occupied=[physical._shape(i,face,True,before) for i in olditems]
        occupied += [physical._filled_shape(z,face,True,before) for z in oldzones]
        art_count=0
        for item in graphics:
            before.tick()
            if not item.IsOnLayer(face):continue
            poly=pcbnew.SHAPE_POLY_SET()
            if hasattr(item,'TransformTextToPolySet'):item.TransformTextToPolySet(poly,0,physical.ERROR_NM,pcbnew.ERROR_OUTSIDE)
            else:item.TransformShapeToPolygon(poly,face,0,physical.ERROR_NM,pcbnew.ERROR_OUTSIDE)
            if poly.OutlineCount():occupied.append(physical._envelope(physical._poly(poly,before),True));art_count+=1
        new=[physical._shape(i,face,False,after) for i in newitems]
        new += [physical._filled_shape(z,face,False,after) for z in newzones]
        holes=[i for i in npads+ntracks if i.GetClass()=='PCB_VIA' and i.IsOnLayer(face)
            or i.GetClass()=='PAD' and i.HasHole()]
        drills=unary_union([physical._hole(i,True,after) for i in holes])
        substrate=physical._envelope(physical._poly(outline.outline_material(candidate),after),False)
        # Omitting source drills only OVERestimates occupied Source, making
        # this progress witness conservative. Candidate drills are all cut.
        source_upper=unary_union(occupied)
        candidate_lower=unary_union(new).difference(drills).intersection(substrate)
        added=candidate_lower.difference(source_upper)
        if not source_upper.is_valid or not candidate_lower.is_valid or not added.is_valid:
            raise ValueError('valid_graphic_aware_material_union_required')
        physical._validate_linear_epochs(before);physical._validate_linear_epochs(after)
        before.tick();after.tick()
        result.update(ok=True,complete=True,faces=[dict(net=net,layer_id=face,layer=source.GetLayerName(face),
            definitely_added_area_mm2=added.area/1e12,definitely_added_bounds_mm=([v/1e6 for v in added.bounds] if not added.is_empty else None),
            actual_source_copper_graphics_included=art_count,source_items=len(olditems),source_zones=len(oldzones),
            candidate_items=len(newitems),candidate_zones=len(newzones),actual_candidate_drills=len(holes),
            no_source_copper_art_or_drill_silently_removed=True)])
    except (ValueError,RuntimeError,TypeError,KeyError,IndexError,physical.Unknown) as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result
