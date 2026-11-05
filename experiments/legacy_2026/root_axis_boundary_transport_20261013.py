"""Canonical source-bound axis transport primitive, not copper acceptance.

Nonparallel boundary edges move as rigid components. Parallel stems may
lengthen/shorten without acquiring skew. Actual holes always remain rigid.
Bounds and topology are checked; native contacts/current/Kelvin/DRC remain
independent acceptance obligations. No board, net, reference or coordinate
case is embedded here.
"""
import hashlib,json,math
from shapely.geometry import Polygon,MultiPolygon


def plan(regions,window_nm,delta_nm,*,maximum_extension_nm=4000000,close_short_stems=False):
    def point(p):
        if (type(p) not in (list,tuple) or len(p)!=2
                or any(type(v) is not int or abs(v)>2000000000 for v in p)):
            raise ValueError('bounded_integer_native_boundary_point_required')
        return tuple(p)
    if (type(window_nm) not in (list,tuple) or len(window_nm)!=4
            or any(type(v) is not int or abs(v)>2000000000 for v in window_nm)
            or not window_nm[0]<window_nm[2] or not window_nm[1]<window_nm[3]):
        raise ValueError('bounded_native_transport_window_required')
    delta=point(delta_nm);dx,dy=delta
    if (not (dx==0)!=(dy==0) or max(abs(dx),abs(dy))>3000000
            or type(maximum_extension_nm) is not int or not 0<=maximum_extension_nm<=8000000):
        raise ValueError('finite_axis_transport_and_explicit_extension_required')
    if type(regions) is not list or not 1<=len(regions)<=4:
        raise ValueError('bounded_native_outer_region_inventory_required')
    if type(close_short_stems) is not bool:
        raise ValueError('explicit_short_boundary_stem_closure_policy_required')
    x0,y0,x1,y1=window_nm
    def inside(p):return x0<=p[0]<=x1 and y0<=p[1]<=y1
    def distance(p):return math.hypot(max(x0-p[0],0,p[0]-x1),max(y0-p[1],0,p[1]-y1))
    changed=[];target=[];vertices=0;source_shapes=[];target_shapes=[];closed=[];checks=0
    for ri,r in enumerate(regions):
        if (type(r) is not dict or set(r)!={'outer_nm','holes_nm'} or type(r['holes_nm']) is not list
                or len(r['holes_nm'])>32):raise ValueError('explicit_native_outer_and_hole_rings_required')
        moved_rings=[];old_rings=[]
        for hi,raw in enumerate([r['outer_nm'],*r['holes_nm']]):
            if type(raw) is not list or not 3<=len(raw)<=1024:
                raise ValueError('bounded_native_linear_boundary_ring_required')
            ring=[point(p) for p in raw];vertices+=len(ring)
            if vertices>8192 or len(set(ring))!=len(ring):raise ValueError('native_transport_vertex_bound')
            parent=list(range(len(ring)))
            def root(i):
                while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
                return i
            def join(a,b):
                a,b=root(a),root(b)
                if a!=b:parent[max(a,b)]=min(a,b)
            for i,(a,b) in enumerate(zip(ring,ring[1:]+ring[:1])):
                vx,vy=b[0]-a[0],b[1]-a[1]
                if hi==0 and (vx and vy and abs(vx)!=abs(vy)):
                    raise ValueError('source_outer_contour_is_not_canonical')
                # An axis-parallel edge may stretch. Every other edge must
                # translate both vertices together. Holes remain wholly rigid.
                if hi or (dx==0 and vx!=0) or (dy==0 and vy!=0):join(i,(i+1)%len(ring))
            if close_short_stems:
                while True:
                    selected={root(i) for i,p in enumerate(ring) if inside(p)}
                    merges=[]
                    for i,(a,b) in enumerate(zip(ring,ring[1:]+ring[:1])):
                        checks+=1
                        if checks>200000:
                            raise ValueError('bounded_short_boundary_stem_closure_work_exceeded')
                        j=(i+1)%len(ring)
                        if root(i)==root(j):continue
                        old=(b[0]-a[0],b[1]-a[1])
                        new=tuple(old[k]+(delta[k] if root(j) in selected else 0)-
                            (delta[k] if root(i) in selected else 0) for k in range(2))
                        if new==(0,0) or sum(v*w for v,w in zip(old,new))<=0:
                            merges.append((i,j))
                    if not merges:break
                    for i,j in merges:
                        join(i,j);closed.append(dict(region=ri,hole=hi-1,vertices=[i,j]))
            selected={root(i) for i,p in enumerate(ring) if inside(p)}
            transformed=[]
            for i,p in enumerate(ring):
                moving=root(i) in selected
                if moving and distance(p)>maximum_extension_nm:
                    raise ValueError('native_boundary_component_exceeds_requested_transport_extent')
                q=(p[0]+dx,p[1]+dy) if moving else p
                if max(map(abs,q))>2000000000:raise ValueError('native_transport_coordinate_overflow')
                transformed.append(q)
                if moving:changed.append(dict(region=ri,hole=hi-1,vertex=i,before_nm=list(p),after_nm=list(q),
                    closure_outside_requested_window=not inside(p)))
            for a,b,c,d in zip(ring,ring[1:]+ring[:1],transformed,transformed[1:]+transformed[:1]):
                v=(b[0]-a[0],b[1]-a[1]);w=(d[0]-c[0],d[1]-c[1])
                if w==(0,0) or v[0]*w[0]+v[1]*w[1]<=0:
                    raise ValueError('native_boundary_edge_collapsed_or_reversed')
                if hi==0 and w[0] and w[1] and abs(w[0])!=abs(w[1]):
                    raise ValueError('native_transport_outer_boundary_lost_canonical_direction')
            old_rings.append(ring);moved_rings.append(transformed)
        source_shapes.append(Polygon(old_rings[0],old_rings[1:]));target_shapes.append(Polygon(moved_rings[0],moved_rings[1:]))
        target.append(dict(outer_nm=[list(p) for p in moved_rings[0]],
            holes_nm=[[list(p) for p in ring] for ring in moved_rings[1:]]))
    for shapes in (source_shapes,target_shapes):
        geometry=shapes[0] if len(shapes)==1 else MultiPolygon(shapes)
        if not geometry.is_valid or geometry.is_empty or any(s.area<=0 for s in shapes):
            raise ValueError('native_transport_changed_or_invalid_region_topology')
    if not changed:raise ValueError('nonempty_native_boundary_transport_required')
    source=json.dumps(regions,sort_keys=True,separators=(',',':'))
    return dict(schema=1,scope='canonical_axis_boundary_construction_only',
        source_geometry_sha256=hashlib.sha256(source.encode()).hexdigest(),regions_nm=target,
        window_nm=list(window_nm),delta_nm=list(delta),maximum_extension_nm=maximum_extension_nm,
        transported_vertices=changed,copper_preservation_proved=False,contacts_preserved=False,
        closed_short_stem_edges=closed,short_stem_closure_checks=checks,
        current_qualified=False,release_authority=False)


def plan_strokes(nodes,edges,window_nm,delta_nm,*,rigid_links=(),fixed_nodes=(),
                 required_nodes=(),maximum_extension_nm=8000000,canonical_tolerance_nm=0,
                 close_short_stems=False,source_body_links=()):
    """Finite directional closure for real stroke junctions, not an autoroute.

    Nodes and links are source geometry supplied by the native caller. Only
    delta-parallel stems can stretch. Fixed or over-extent components are
    explicitly refused, never silently torn apart or electrically accepted.
    """
    if (type(nodes) is not list or not 2<=len(nodes)<=8192 or
            any(type(p) not in (list,tuple) or len(p)!=2 or
                any(type(v) is not int or abs(v)>2000000000 for v in p) for p in nodes)):
        raise ValueError('bounded_native_stroke_node_inventory_required')
    if (type(window_nm) not in (list,tuple) or len(window_nm)!=4 or
            any(type(v) is not int or abs(v)>2000000000 for v in window_nm) or
            not window_nm[0]<window_nm[2] or not window_nm[1]<window_nm[3]):
        raise ValueError('bounded_native_transport_window_required')
    if (type(delta_nm) not in (list,tuple) or len(delta_nm)!=2 or
            any(type(v) is not int for v in delta_nm) or
            not (delta_nm[0]==0)!=(delta_nm[1]==0) or max(map(abs,delta_nm))>3000000 or
            type(maximum_extension_nm) is not int or not 0<=maximum_extension_nm<=8000000):
        raise ValueError('finite_axis_transport_and_explicit_extension_required')
    if (type(edges) is not list or not 1<=len(edges)<=4096 or
            type(rigid_links) not in (tuple,list) or len(rigid_links)>8192 or
            type(source_body_links) not in (tuple,list) or len(source_body_links)>8192):
        raise ValueError('bounded_native_stroke_edge_inventory_required')
    if type(canonical_tolerance_nm) is not int or not 0<=canonical_tolerance_nm<=1000:
        raise ValueError('bounded_explicit_native_direction_distance_tolerance_required')
    if type(close_short_stems) is not bool:raise ValueError('explicit_short_stem_closure_policy_required')
    def index(i):
        if type(i) is not int or not 0<=i<len(nodes):raise ValueError('exact_native_stroke_node_index_required')
        return i
    def pair(p):
        if type(p) not in (list,tuple) or len(p)!=2:raise ValueError('exact_native_stroke_edge_pair_required')
        a,b=map(index,p)
        if a==b:raise ValueError('nonempty_native_stroke_edge_required')
        return a,b
    fixed={index(i) for i in fixed_nodes};required={index(i) for i in required_nodes}
    parent=list(range(len(nodes)))
    def root(i):
        while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
        return i
    def join(a,b):
        a,b=root(a),root(b)
        if a!=b:parent[max(a,b)]=min(a,b)
    dx,dy=delta_nm;checked=[]
    for raw in edges:
        a,b=pair(raw);vx,vy=nodes[b][0]-nodes[a][0],nodes[b][1]-nodes[a][1]
        if not (vx or vy) or min(abs(vx),abs(vy),abs(abs(vx)-abs(vy)))>canonical_tolerance_nm:
            raise ValueError('canonical_nonempty_source_strokes_required')
        if (dx==0 and abs(vx)>canonical_tolerance_nm) or (dy==0 and abs(vy)>canonical_tolerance_nm):join(a,b)
        checked.append((a,b))
    for raw in rigid_links:
        a,b=pair(raw)
        if tuple(nodes[a])!=tuple(nodes[b]):raise ValueError('rigid_barrel_link_requires_same_actual_point')
        join(a,b)
    # Explicit SOURCE-native interior contacts can have different centres.
    # Keep their entire motion equal rather than pretending they are barrels
    # at the same point. These links add exclusions only, no copper authority.
    for raw in source_body_links:
        a,b=pair(raw);join(a,b)
    x0,y0,x1,y1=window_nm
    def inside(p):return x0<=p[0]<=x1 and y0<=p[1]<=y1
    def distance(p):return math.hypot(max(x0-p[0],0,p[0]-x1),max(y0-p[1],0,p[1]-y1))
    closed=[];checks=0
    if close_short_stems:
        while True:
            members={}
            for i in range(len(nodes)):members.setdefault(root(i),[]).append(i)
            active={label for label,row in members.items() if any(inside(nodes[i]) or i in required for i in row)
                and not fixed & set(row) and all(distance(nodes[i])<=maximum_extension_nm for i in row)}
            merges=[]
            for a,b in checked:
                checks+=1
                if checks>200000:raise ValueError('bounded_short_stem_closure_work_exceeded')
                ra,rb=root(a),root(b)
                if ra==rb:continue
                old=[nodes[b][k]-nodes[a][k] for k in range(2)]
                new=[old[k]+(delta_nm[k] if rb in active else 0)-
                    (delta_nm[k] if ra in active else 0) for k in range(2)]
                if not any(new) or sum(x*y for x,y in zip(old,new))<=0:merges.append((a,b))
            if not merges:break
            for a,b in merges:join(a,b);closed.append([a,b])
    components={}
    for i in range(len(nodes)):components.setdefault(root(i),[]).append(i)
    selected={root(i) for i,p in enumerate(nodes) if inside(p) or i in required}
    motion=[[0,0] for _ in nodes];refusals=[]
    for label,members in sorted(components.items()):
        if label not in selected:continue
        reasons=[]
        if fixed & set(members):reasons.append('stationary_native_contact')
        if any(distance(nodes[i])>maximum_extension_nm for i in members):reasons.append('explicit_extension_exceeded')
        if reasons:
            refusals.append(dict(nodes=members,reasons=reasons,required_nodes=sorted(required & set(members))))
        else:
            for i in members:motion[i]=[dx,dy]
    target=[[p[0]+v[0],p[1]+v[1]] for p,v in zip(nodes,motion)]
    for a,b in checked:
        old=[nodes[b][k]-nodes[a][k] for k in range(2)]
        new=[target[b][k]-target[a][k] for k in range(2)]
        if (not any(new) or sum(x*y for x,y in zip(old,new))<=0 or
                min(abs(new[0]),abs(new[1]),abs(abs(new[0])-abs(new[1])))>canonical_tolerance_nm):
            raise ValueError('native_stroke_transport_collapsed_reversed_or_skewed_edge')
    if any(abs(v)>2000000000 for p in target for v in p):raise ValueError('native_transport_coordinate_overflow')
    return dict(schema=1,scope='canonical_axis_stroke_construction_only',nodes_nm=target,
        node_offsets_nm=motion,refused_components=refusals,transported_nodes=sum(any(v) for v in motion),
        window_nm=list(window_nm),delta_nm=list(delta_nm),maximum_extension_nm=maximum_extension_nm,
        canonical_tolerance_nm=canonical_tolerance_nm,
        closed_short_stem_edges=closed,short_stem_closure_checks=checks,
        source_body_links=[list(pair(p)) for p in source_body_links],
        actual_native_links_still_require_receiving=True,current_qualified=False,release_authority=False)
