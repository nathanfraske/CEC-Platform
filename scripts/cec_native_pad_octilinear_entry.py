"""Finite full-width native SMD entry points; geometry, never electrical scope.

The box only supplies candidate integer intervals. Every returned start disk
must independently fit the actual native pad shape with ZERO tolerance. No
pad movement, narrow neckdown, new via floor or fabrication waiver is granted.
"""
import math
import time
import pcbnew
import cec_fab_profile as fab
import cec_force_current as force


def choose(pad,axis_nm,*,width_nm,maximum_leg_nm=1500000,deadline=None):
    now=time.monotonic()
    if(type(width_nm)is not int or not 0<width_nm<=1000000
            or type(maximum_leg_nm)is not int or not 0<maximum_leg_nm<=1500000
            or type(axis_nm)not in(list,tuple)or len(axis_nm)!=2
            or any(type(v)is not int or abs(v)>2000000000 for v in axis_nm)
            or deadline is not None and(type(deadline)not in(int,float)or not math.isfinite(deadline)or not now<deadline<=now+10.)):
        raise ValueError('bounded_full_width_native_pad_entry_required')
    end=now+10. if deadline is None else deadline
    faces=tuple(map(int,pad.GetLayerSet().CuStack()))
    if(pad.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD or pad.HasHole()or pad.GetParentFootprint().IsDNP()
            or len(faces)!=1 or faces[0]not in(0,2)):
        raise ValueError('one_populated_surface_SMD_entry_required')
    centre=tuple(pad.GetPosition());radius=(width_nm+1)//2;box=pad.GetBoundingBox()
    low=(box.GetLeft()+radius,box.GetTop()+radius);high=(box.GetRight()-radius,box.GetBottom()-radius)
    if any(a>b for a,b in zip(low,high)):raise ValueError('no_full_width_native_pad_entry')
    options=[];examined=0;seen=set()
    for unit in((1,0),(1,1),(0,1),(-1,1),(-1,0),(-1,-1),(0,-1),(1,-1)):
        norm=sum(v*v for v in unit);lo,hi=1,math.isqrt(maximum_leg_nm**2//norm)
        for i in(0,1):
            if unit[i]==0:
                if not low[i]<=axis_nm[i]<=high[i]:hi=0;break
            else:
                a=(low[i]-axis_nm[i])*unit[i];b=(high[i]-axis_nm[i])*unit[i]
                lo=max(lo,min(a,b));hi=min(hi,max(a,b))
        if lo>hi:continue
        projection=sum((centre[i]-axis_nm[i])*unit[i]for i in(0,1))
        closest=projection//norm
        values={lo,hi,(lo+hi)//2,max(lo,min(hi,closest)),max(lo,min(hi,closest+1))}
        for value in sorted(values):
            if time.monotonic()>=end:raise ValueError('native_pad_entry_deadline')
            start=tuple(axis_nm[i]+value*unit[i]for i in(0,1))
            if start in seen:continue
            seen.add(start);examined+=1
            if fab._pad_contains_circle(pad,pcbnew.VECTOR2I(*start),radius,tolerance_nm=0):
                options.append((sum((start[i]-centre[i])**2 for i in(0,1)),value*value*norm,start,unit))
    if not options:raise ValueError('no_full_width_native_pad_entry')
    _,squared,start,unit=min(options)
    if time.monotonic()>=end:raise ValueError('native_pad_entry_deadline')
    return dict(start_nm=list(start),at_nm=list(axis_nm),source_pad_uuid=force._uid(pad),source_pad_centre_nm=list(centre),
        width_nm=width_nm,start_cap_radius_nm=radius,maximum_leg_nm=maximum_leg_nm,
        actual_native_start_disk_contained=True,containment_tolerance_nm=0,
        canonical_heading_from_axis=list(unit),leg_squared_nm2=squared,candidate_native_tests=examined,
        electrical_scope=False,routing_admitted=False,release_authority=False)
