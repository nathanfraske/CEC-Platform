"""Validate an exact search walk, including legal vias at either endpoint.

Requiring the first TRACK to occupy the source face rejects a valid walk
whose first operation is a via. Conversely accepting that track without the
via would create a floating route. Track every coordinate/face transition.
This is only structural access evidence, not clearance/current/fab authority.
"""
import math


def validate(operations,*,start,end,faces,start_layers,end_layers,width_nm):
    def point(value):
        if (type(value) not in (list,tuple) or len(value)!=2
                or any(type(v) is not int or abs(v)>2000000000 for v in value)):
            raise ValueError('literal_bounded_native_route_point_required')
        return tuple(value)
    if (type(operations) not in (list,tuple) or not 1<=len(operations)<=256
            or type(width_nm) is not int or not 0<width_nm<=10000000
            or type(faces) not in (list,tuple) or not 1<=len(faces)<=6
            or len(set(faces))!=len(faces) or any(type(f) is not int for f in faces)
            or type(start_layers) not in (list,tuple) or type(end_layers) not in (list,tuple)
            or not start_layers or not end_layers or any(type(f) is not int for f in [*start_layers,*end_layers])
            or not set(start_layers)<=set(faces) or not set(end_layers)<=set(faces)):
        raise ValueError('bounded_exact_native_route_walk_required')
    at=point(start);target=point(end);active=set(start_layers);vias=0;tracks=0;last_via=False;length=0.
    for op in operations:
        if type(op) not in (list,tuple) or not op:raise ValueError('literal_native_route_operation_required')
        if op[0]=='trk':
            if len(op)!=5 or type(op[3]) is not int or op[3]!=width_nm or type(op[4]) is not int or op[4] not in active:
                raise ValueError('native_walk_stroke_width_or_face_changed')
            a,b=point(op[1]),point(op[2]);dx,dy=abs(a[0]-b[0]),abs(a[1]-b[1])
            if a!=at or a==b or dx and dy and dx!=dy:
                raise ValueError('native_walk_discontinuous_zero_or_noncanonical_stroke')
            active={op[4]};at=b;tracks+=1;last_via=False;length+=math.dist(a,b)
        elif op[0]=='via':
            if (len(op)!=4 or point(op[1])!=at or last_via
                    or any(type(v) not in (int,float) or not math.isfinite(v) for v in op[2:])
                    or not 0<op[2]<op[3]<=10):
                raise ValueError('native_walk_invalid_or_redundant_barrel_transition')
            # Search vias are native through barrels. Each must make an
            # actual face change; a decorative single-face pickup is not a hop.
            active={face for face in faces if any(face!=old for old in active)}
            if not active:raise ValueError('native_walk_barrel_has_no_actual_face_transition')
            vias+=1;last_via=True
        else:raise ValueError('unknown_native_route_walk_operation')
    if not tracks or at!=target or not active&set(end_layers):
        raise ValueError('native_walk_does_not_reach_actual_destination_face')
    return dict(ok=True,complete=True,track_count=tracks,via_count=vias,length_mm=length/1e6,
        starts_with_via=operations[0][0]=='via',ends_with_via=operations[-1][0]=='via',
        structural_access_only=True,geometry_clearance_or_current_qualified=False,release_authority=False)
