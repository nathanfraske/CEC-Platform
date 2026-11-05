"""Finite canonical SMD-face dogbones derived from the actual native land.

These are proposals only. Consumers must prove ownership, all-layer via and
hole clearance, trace clearance, length and edge limits with native guards.
"""
import math
import pcbnew


def candidates(pad, geometries, *, margin_nm=5000, reach_mm=1.5):
    if (type(margin_nm) is not int or not 1 <= margin_nm <= 50000
            or type(reach_mm) not in (int, float) or not math.isfinite(reach_mm)
            or not 0 < reach_mm <= 5):
        raise ValueError('bounded positive face-launch geometry required')
    if (pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD
            or pad.GetShape() not in (pcbnew.PAD_SHAPE_RECT, pcbnew.PAD_SHAPE_ROUNDRECT,
                pcbnew.PAD_SHAPE_CIRCLE, pcbnew.PAD_SHAPE_OVAL)):
        return []
    origin = pad.GetPosition(); owner = pad.GetParentFootprint().GetPosition()
    bb = pad.GetBoundingBox()
    directions = sorted(((1,0),(-1,0),(0,1),(0,-1)),
        key=lambda n: -((origin.x-owner.x)*n[0]+(origin.y-owner.y)*n[1]))
    result = []
    for diameter, drill in geometries:
        if not all(type(v) in (int,float) and math.isfinite(v) and v>0 for v in (diameter,drill)):
            continue
        radius = pcbnew.FromMM(diameter) / 2
        for nx, ny in directions:
            tx, ty = -ny, nx
            edge = max((x-origin.x)*nx+(y-origin.y)*ny
                for x in (bb.GetLeft(),bb.GetRight()) for y in (bb.GetTop(),bb.GetBottom()))
            distance = math.ceil(edge+radius+margin_nm)
            if distance <= 0 or distance > pcbnew.FromMM(reach_mm):
                continue
            transverse = bb.GetWidth() if tx else bb.GetHeight()
            for fraction in (0., .25, -.25):
                shift = round(transverse*fraction)
                start = origin + pcbnew.VECTOR2I(tx*shift,ty*shift)
                end = start + pcbnew.VECTOR2I(nx*distance,ny*distance)
                if (not pad.HitTest(start)
                        or math.hypot(end.x-origin.x,end.y-origin.y)>pcbnew.FromMM(reach_mm)):
                    continue
                result.append(dict(start=start,end=end,diameter=diameter,drill=drill,
                                   normal=(nx,ny),margin_nm=margin_nm))
    return result


def radial_candidates(pad,geometries,*,distances_mm,reach_mm=1.5):
    """Finite centre-owned 0/45-degree probes inside an existing reach.

    These are only additional geometric proposals. The consumer must retain
    its native pad/contact/hole/rule/current/field checks. A long permissible
    reach does not imply that any intervening or far copper is clear.
    """
    if(type(reach_mm)not in(int,float)or not math.isfinite(reach_mm)or not 0<reach_mm<=5
            or type(distances_mm)not in(list,tuple)or not 1<=len(distances_mm)<=4
            or any(type(v)not in(int,float)or not math.isfinite(v)or not 0<v<=reach_mm
                for v in distances_mm)or len(set(distances_mm))!=len(distances_mm)
            or type(geometries)not in(list,tuple)or not 1<=len(geometries)<=4):
        raise ValueError('finite_radial_face_launch_domain_required')
    if(pad.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD
            or pad.GetShape()not in(pcbnew.PAD_SHAPE_RECT,pcbnew.PAD_SHAPE_ROUNDRECT,
                pcbnew.PAD_SHAPE_CIRCLE,pcbnew.PAD_SHAPE_OVAL)):
        return []
    origin=pad.GetPosition();result=[];seen=set()
    for diameter,drill in geometries:
        if not all(type(v)in(int,float)and math.isfinite(v)and v>0 for v in(diameter,drill)):
            raise ValueError('positive_radial_face_launch_dimensions_required')
        for distance in sorted(distances_mm):
            for nx,ny in((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)):
                step=math.floor(distance*1e6/math.hypot(nx,ny))
                if step<=0:continue
                at=origin+pcbnew.VECTOR2I(nx*step,ny*step)
                if math.dist(tuple(at),tuple(origin))>reach_mm*1e6:continue
                key=(tuple(at),diameter,drill)
                if key in seen:continue
                seen.add(key)
                result.append(dict(start=origin,end=at,diameter=diameter,drill=drill,
                    normal=(nx,ny),radial_distance_mm=distance))
    return result
