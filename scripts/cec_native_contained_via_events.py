"""Finite native land-area/barrel events, never fabrication or route authority.

Use actual pad copper and nearby all-layer native obstacles to propose interior
interval midpoints. A fixed inset stencil can miss a real narrow pocket. Every
consumer must still run its unchanged native process/containment/edge/hole and
foreign-copper guards; these polygons do not receive copper or relax a floor.
"""
import math
import time
import pcbnew
from shapely.geometry import LineString, Point, box
from shapely.ops import unary_union
import cec_assembly_envelope as assembly


def _polygon(shape,error,location):
    poly=pcbnew.SHAPE_POLY_SET();shape.TransformToPolygon(poly,error,location)
    result=assembly.polygon_from_native(poly)
    if result.is_empty or not result.is_valid:raise ValueError('positive_native_via_event_polygon_required')
    return result


def contains(pad,at,diameter_nm):
    """No tolerance: inside pad polygon covers an OUTSIDE via-circle polygon."""
    layers=list(pad.GetLayerSet().CuStack())
    if len(layers)!=1 or pad.HasHole()or pad.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD:return False
    if pad.GetShape()not in(pcbnew.PAD_SHAPE_RECT,pcbnew.PAD_SHAPE_ROUNDRECT,
        pcbnew.PAD_SHAPE_CIRCLE,pcbnew.PAD_SHAPE_OVAL):return False
    actual=_polygon(pad.GetEffectiveShape(layers[0]),16,pcbnew.ERROR_INSIDE)
    radius=diameter_nm/2e6
    circle=Point(at.x/1e6,at.y/1e6).buffer(radius/math.cos(math.pi/256),quad_segs=64)
    return bool(actual.covers(circle))


def candidates(board,pad,diameter_nm,clearance_nm,*,deadline,max_events=24,foreign_cache=None):
    """Four canonical axes; only exact physical guards can admit a midpoint."""
    import cec_fr as fr
    if(type(diameter_nm)is not int or not 0<diameter_nm<=2000000
        or type(clearance_nm)is not int or not 0<clearance_nm<=2000000
        or type(max_events)is not int or not 1<=max_events<=24
        or type(deadline)not in(int,float)or not math.isfinite(deadline)):
        raise ValueError('bounded_native_contained_via_events_required')
    result=dict(events=[],complete=False,native_shapes_examined=0,
        routing_admitted=False,release_authority=False,no_path_proof=False)
    layers=list(pad.GetLayerSet().CuStack())
    if (time.monotonic()>=deadline or len(layers)!=1 or pad.HasHole()
        or pad.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD or pad.GetNetCode()<=0
        or pad.GetShape()not in(pcbnew.PAD_SHAPE_RECT,pcbnew.PAD_SHAPE_ROUNDRECT,
            pcbnew.PAD_SHAPE_CIRCLE,pcbnew.PAD_SHAPE_OVAL)):
        return result
    pos=pad.GetPosition();origin=(pos.x/1e6,pos.y/1e6);radius=diameter_nm/2e6
    # This inward polygon/core can lose a tiny feasible site, never expand
    # a real pad. Final contains() uses an independently circumscribed circle.
    pad_shape=_polygon(pad.GetEffectiveShape(layers[0]),16,pcbnew.ERROR_INSIDE)
    core=pad_shape.buffer(-radius-32./1e6)
    if core.is_empty:result['complete']=True;return result
    bounds=pad_shape.bounds;halo=radius+clearance_nm/1e6+.002
    crop=box(bounds[0]-halo,bounds[1]-halo,bounds[2]+halo,bounds[3]+halo)
    bb=pad.GetBoundingBox();extent=round(halo*1e6)
    query=pcbnew.BOX2I(pcbnew.VECTOR2I(bb.GetLeft()-extent,bb.GetTop()-extent),
        pcbnew.VECTOR2I(bb.GetWidth()+2*extent,bb.GetHeight()+2*extent))
    cache={}if foreign_cache is None else foreign_cache;occupied=[]
    for layer in board.GetEnabledLayers().CuStack():
        for index in fr._foreign_shape_indexes(board,int(layer),{pad.GetNetCode()},cache=cache):
            for row in fr._indexed_shape_rows(index,query):
                if time.monotonic()>=deadline:return result
                result['native_shapes_examined']+=1
                if result['native_shapes_examined']>4096:return result
                shape=_polygon(row[0],16,pcbnew.ERROR_OUTSIDE).intersection(crop)
                if shape.is_empty:continue
                gap=max(clearance_nm,int(row[3])if len(row)>3 else 0)
                occupied.append(shape.buffer(radius+gap/1e6,quad_segs=64))
    if time.monotonic()>=deadline:return result
    free=core.difference(unary_union(occupied))
    if free.is_empty:result['complete']=True;return result
    reach=max(math.hypot(x-origin[0],y-origin[1])for x in(bounds[0],bounds[2])for y in(bounds[1],bounds[3]))+.001
    events={}
    for dx,dy in((1,0),(0,1),(1,1),(1,-1)):
        if time.monotonic()>=deadline:return result
        scale=reach/math.hypot(dx,dy)
        line=LineString([(origin[0]-dx*scale,origin[1]-dy*scale),
            (origin[0]+dx*scale,origin[1]+dy*scale)])
        pieces=line.intersection(free)
        pieces=[pieces]if pieces.geom_type=='LineString'else list(getattr(pieces,'geoms',()))
        for piece in pieces:
            if piece.geom_type!='LineString'or piece.is_empty:continue
            for fraction in(.5,.25,.75):
                at=piece.interpolate(fraction,normalized=True)
                # Canonical integer axes survive rounding, including 45s.
                distance=round(((at.x-origin[0])/dx if dx else(at.y-origin[1])/dy)*1e6)
                xy=(pos.x+dx*distance,pos.y+dy*distance)
                if xy==tuple(pos):continue
                point=pcbnew.VECTOR2I(*xy)
                if contains(pad,point,diameter_nm):
                    events[xy]=dict(at_nm=list(xy),distance_mm=math.dist(tuple(pos),xy)/1e6,
                        origin='native_contained_free_interval_midpoint',
                        strict_native_pad_containment=True)
    if time.monotonic()>=deadline:return result
    result.update(complete=True,events=sorted(events.values(),key=lambda q:(q['distance_mm'],q['at_nm']))[:max_events])
    return result
