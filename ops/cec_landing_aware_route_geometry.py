"""Native landing-aware search geometry, never electrical/retirement authority."""
import math,time
import pcbnew
import cec_existing_current_path_refinement as capacity
import cec_force_current as force

def require(value,message):
    if not value:raise ValueError(message)

def hidden_landing_miter(board,old,*,minimum_flat_nm=20000):
    require(type(minimum_flat_nm) is int and 20000<=minimum_flat_nm<=200000
        and len(old)==2 and all(t.GetClass()=='PCB_TRACK' and not t.HasSolderMask() for t in old)
        and len({(t.GetNetname(),int(t.GetLayer()),t.GetWidth()) for t in old})==1,
        'bounded_uniform_native_landing_miter_required')
    source=[list(p) for p in capacity.chains._chain(old)];start,at,end=source
    u=[start[i]-at[i] for i in (0,1)];v=[end[i]-at[i] for i in (0,1)]
    require(u[0]*u[1]==v[0]*v[1]==0 and sum(x*y for x,y in zip(u,v))==0,
        'literal_axis_aligned_source_right_angle_required')
    lengths=[math.dist(start,at),math.dist(end,at)];width=old[0].GetWidth();face=int(old[0].GetLayer())
    require(0<width<=1000000 and max(lengths)<=32000000,'bounded_literal_landing_miter_span_required')
    inset=(width+math.isqrt(2*minimum_flat_nm**2)+3)//2+1000
    require(inset<min(lengths),'no_room_for_positive_full_width_landing_miter')
    points=[start,[at[i]+round(u[i]*inset/lengths[0]) for i in (0,1)],
        [at[i]+round(v[i]*inset/lengths[1]) for i in (0,1)],end]
    capacity.geometry._points(points);witnesses=[];deadline=time.monotonic()+10.
    items=[*(p for fp in board.GetFootprints() for p in fp.Pads()),*board.GetTracks()]
    require(len(items)<=16384,'bounded_native_landing_host_inventory_required')
    for (a,z),length in ((points[:2],lengths[0]),(points[-2:],lengths[1])):
        if inset*2<=length:continue
        t=old[0].Duplicate();t.SetStart(pcbnew.VECTOR2I(*a));t.SetEnd(pcbnew.VECTOR2I(*z))
        cap=pcbnew.SHAPE_POLY_SET();t.TransformShapeToPolygon(cap,face,0,1,pcbnew.ERROR_OUTSIDE,False)
        hosts=[]
        for item in items:
            require(time.monotonic()<deadline,'native_landing_containment_deadline')
            if item.GetClass() not in ('PAD','PCB_VIA') or item.GetNetname()!=t.GetNetname() or not item.IsOnLayer(face):continue
            silhouette=pcbnew.SHAPE_POLY_SET();item.TransformShapeToPolygon(silhouette,face,0,1,pcbnew.ERROR_INSIDE,False)
            missing=cap.CloneDropTriangulation();missing.BooleanSubtract(silhouette)
            if not missing.OutlineCount():hosts.append(force._uid(item))
        require(hosts,'short_remainder_not_entirely_inside_actual_retained_native_landing')
        witnesses.append(dict(leg_nm=[a,z],native_host_uuids=sorted(hosts),
            literal_capsule_inside_actual_landing_silhouette=True,drilled_contact_or_current_capacity_qualified=False))
    require(witnesses,'ordinary_half_leg_miter_does_not_need_landing_extension')
    return dict(source_points_nm=source,points_nm=points,inset_nm=inset,minimum_flat_nm=minimum_flat_nm,
        landing_witnesses=witnesses,search_geometry_only=True,release_authority=False)

def source_departure_paths(source_points,departure,width_nm):
    """Extend a lead beyond a short first edge, not beyond a native receiver.

    The caller must positively rederive the typed source witness and retain
    its departure start/exit/heading. Complete original-parent Kelvin input
    planning and fresh saved clipping still decide every proposed path.
    """
    require(type(width_nm) is int and 0<width_nm<=400000,'bounded_source_departure_width_required')
    original=[list(p) for p in source_points];require(3<=len(original)<=9,'bounded_whole_departure_path_required')
    start=[round(v*1e6) for v in departure['departure_start_mm']]
    exit=[round(v*1e6) for v in departure['contact_exit_mm']]
    direction=departure['inward_direction']
    require(direction in ([1.,0.],[-1.,0.],[0.,1.],[0.,-1.]),'literal_cardinal_source_departure_required')
    reverse=original[-1]==start
    if reverse:original.reverse()
    require(original[0]==start,'actual_whole_path_source_departure_port_required')
    delta=[exit[i]-start[i] for i in (0,1)];travel=sum(delta[i]*direction[i] for i in (0,1))
    require(travel>0 and delta[0]*direction[1]-delta[1]*direction[0]==0,
        'native_source_exit_must_lie_on_actual_straight_departure')
    steps=sorted({math.ceil(travel)+width_nm+1000,math.ceil(travel)+2*width_nm+1000})
    before=sum(math.dist(a,z) for a,z in zip(original,original[1:]));paths=[];seen=set()
    ring=((1,0),(1,1),(0,1),(-1,1),(-1,0),(-1,-1),(0,-1),(1,-1))
    def steer(at,vector,step):
        index=ring.index(tuple(vector))
        return [[at[i]+step*ring[(index+turn)%8][i] for i in (0,1)] for turn in (-1,1)]
    tails=[[original[-1]]]
    last_delta=[original[-2][i]-original[-1][i] for i in (0,1)]
    last_direction=capacity.geometry._heading(original[-1],original[-2])
    for step in (width_nm,2*width_nm):
        if step*math.hypot(*last_direction)>=math.hypot(*last_delta):continue
        first=[original[-1][i]+step*last_direction[i] for i in (0,1)]
        tails.append([original[-1],first])
        tails.extend([original[-1],first,p] for p in steer(first,last_direction,width_nm))
    for step in steps:
        lead=[start[i]+round(step*direction[i]) for i in (0,1)]
        pres=[[start,lead],*[[start,lead,p] for p in steer(lead,direction,width_nm)]]
        for pre in pres:
            for tail in tails:
                for middle in capacity.fr._canonical_45_xy_paths(pre[-1],tail[-1]):
                    raw=[*pre[:-1],*map(list,middle),*list(reversed(tail))[1:]];points=[]
                    for at in raw:
                        if points and at==points[-1]:continue
                        while len(points)>=2:
                            u=[points[-1][i]-points[-2][i] for i in (0,1)];v=[at[i]-points[-1][i] for i in (0,1)]
                            if u[0]*v[1]-u[1]*v[0] or sum(x*y for x,y in zip(u,v))<=0:break
                            points.pop()
                        points.append(at)
                    key=tuple(map(tuple,points))
                    if key in seen:continue
                    seen.add(key)
                    try:capacity.geometry._points(points)
                    except ValueError:continue
                    length=sum(math.dist(a,z) for a,z in zip(points,points[1:]))
                    if length+10000<before:paths.append(points)
    paths.sort(key=lambda p:(sum(math.dist(a,z) for a,z in zip(p,p[1:])),len(p),p))
    return [list(reversed(p)) if reverse else p for p in paths[:32]]

def source_exit_corner_paths(source_points,departure,width_nm):
    """Small fixed-port miters that retain the actual straight source exit.

    This only ranks geometry. Fresh input-island ownership, native clipping,
    exact departure observations and clearance still decide admission.
    """
    require(type(width_nm) is int and 0<width_nm<=400000 and len(source_points)==3,
        'bounded_typed_source_exit_corner_required')
    original=[list(p) for p in source_points];start=[round(v*1e6) for v in departure['departure_start_mm']]
    exit=[round(v*1e6) for v in departure['contact_exit_mm']];direction=departure['inward_direction']
    require(direction in ([1,0],[-1,0],[0,1],[0,-1]),'literal_cardinal_source_departure_required')
    reverse=original[-1]==start
    if reverse:original.reverse()
    require(original[0]==start,'actual_source_exit_corner_port_required')
    a,at,z=original;u=[a[i]-at[i] for i in (0,1)];v=[z[i]-at[i] for i in (0,1)]
    require(u[0]*u[1]==v[0]*v[1]==0 and sum(x*y for x,y in zip(u,v))==0,
        'actual_axis_source_exit_right_angle_required')
    advance=[at[i]-a[i] for i in (0,1)]
    require(advance[0]*direction[1]-advance[1]*direction[0]==0
        and sum(advance[i]*direction[i] for i in (0,1))>0,
        'literal_source_first_edge_must_follow_actual_departure_heading')
    first=math.dist(a,at);last=math.dist(at,z);delta=[exit[i]-a[i] for i in (0,1)]
    travel=sum(delta[i]*direction[i] for i in (0,1))
    require(delta[0]*direction[1]-delta[1]*direction[0]==0 and 0<travel<first,
        'actual_source_exit_must_precede_this_native_corner')
    room=math.floor(first-travel);paths=[]
    for inset in sorted({room//2,(room*4)//5}):
        if inset<=0 or inset>=min(first,last):continue
        points=[a,[at[i]+round(u[i]*inset/first) for i in (0,1)],
            [at[i]+round(v[i]*inset/last) for i in (0,1)],z]
        capacity.geometry._points(points)
        gain=first+last-sum(math.dist(x,y) for x,y in zip(points,points[1:]))
        if gain>=10000:paths.append(list(reversed(points)) if reverse else points)
    return paths
