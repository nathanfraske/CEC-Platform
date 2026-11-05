"""Exact constant-width union of proposed straight strokes, never source edits.

Collinear equal-width capsules on one layer merge only when their centreline
intervals overlap or touch. Endpoints are copied from the input, not rounded
or projected. Different widths/layers, positive gaps and all via geometry
stay distinct. This is material construction, not current or release authority.
"""
from math import gcd


def normalize(operations):
    if not isinstance(operations,(list,tuple)) or not 1<=len(operations)<=144:
        raise ValueError('bounded_proposed_stroke_packet_required')
    groups={};vias=[];count=0
    for op in operations:
        if not isinstance(op,(tuple,list)) or not op:raise ValueError('typed_proposed_operation_required')
        if op[0]=='via':
            if len(op)!=4:raise ValueError('literal_proposed_via_required')
            vias.append(tuple(op));continue
        if op[0]!='trk' or len(op)!=5:raise ValueError('straight_proposed_strokes_required')
        _,a,b,w,l=op;a,b=tuple(a),tuple(b)
        if (len(a)!=2 or len(b)!=2 or any(type(v)is not int for p in(a,b)for v in p)
                or type(w)is not int or w<=0 or type(l)is not int):
            raise ValueError('literal_proposed_stroke_dimensions_required')
        dx,dy=b[0]-a[0],b[1]-a[1];d=gcd(dx,dy)
        if not d or dx and dy and abs(dx)!=abs(dy):raise ValueError('nonzero_octilinear_proposed_stroke_required')
        ux,uy=dx//d,dy//d
        if ux<0 or ux==0 and uy<0:ux,uy=-ux,-uy
        ta,tb=a[0]*ux+a[1]*uy,b[0]*ux+b[1]*uy
        key=(l,w,ux,uy,ux*a[1]-uy*a[0])
        groups.setdefault(key,[]).append((min(ta,tb),max(ta,tb),{ta:a,tb:b}));count+=1
    output=[]
    for (layer,width,*_),rows in groups.items():
        merged=[]
        for lo,hi,points in sorted(rows,key=lambda r:(r[0],r[1])):
            if merged and lo<=merged[-1][1]:
                last=merged[-1];last[1]=max(last[1],hi);last[2].update(points)
            else:merged.append([lo,hi,dict(points)])
        output.extend(('trk',points[lo],points[hi],width,layer)for lo,hi,points in merged)
    output.extend(vias)
    return output,dict(schema=1,source_items_inspected_or_mutated=False,
        input_strokes=count,output_strokes=len(output)-len(vias),
        exact_equal_width_collinear_capsule_union_preserved=True,
        original_endpoint_coordinates_only=True,via_geometry_unchanged=True,
        current_qualified=False,release_authority=False)
