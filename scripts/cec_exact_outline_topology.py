"""Bounded integer topology for literal linear outer contours and holes.

No clipping, snapping, buffering, area tolerance or repaired geometry. Each
ring is simple, every boundary is disjoint, holes are strictly inside their
own outer and outside every peer hole. This checks geometry, not electrical
connection, ampacity, current sharing, manufacturing or release readiness.
"""
import math
import time


def _cross(a,b,c):
    return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def _on(a,b,p):
    return (_cross(a,b,p)==0 and min(a[0],b[0])<=p[0]<=max(a[0],b[0])
        and min(a[1],b[1])<=p[1]<=max(a[1],b[1]))


def _intersect(a,b,c,d):
    if (max(a[0],b[0])<min(c[0],d[0]) or max(c[0],d[0])<min(a[0],b[0])
            or max(a[1],b[1])<min(c[1],d[1]) or max(c[1],d[1])<min(a[1],b[1])):
        return False
    ab_c,ab_d,cd_a,cd_b=_cross(a,b,c),_cross(a,b,d),_cross(c,d,a),_cross(c,d,b)
    return ((ab_c>0)!=(ab_d>0) and (cd_a>0)!=(cd_b>0)
        and all(v!=0 for v in (ab_c,ab_d,cd_a,cd_b))
        or ab_c==0 and _on(a,b,c) or ab_d==0 and _on(a,b,d)
        or cd_a==0 and _on(c,d,a) or cd_b==0 and _on(c,d,b))


def _inside(point,ring):
    winding=0
    for a,b in zip(ring,ring[1:]+ring[:1]):
        if _on(a,b,point):return False
        if a[1]<=point[1]<b[1] and _cross(a,b,point)>0:winding+=1
        elif b[1]<=point[1]<a[1] and _cross(a,b,point)<0:winding-=1
    return winding!=0


def require_one_polygon(polygons,*,deadline_monotonic,max_vertices=8192,max_pair_checks=2_000_000):
    """Require one strict signed polygon, or raise; never change input."""
    if (type(deadline_monotonic) not in (int,float) or not math.isfinite(deadline_monotonic)
            or type(max_vertices) is not int or not 4<=max_vertices<=8192
            or type(max_pair_checks) is not int or not 1<=max_pair_checks<=2_000_000
            or type(polygons) is not list or len(polygons)!=1
            or type(polygons[0]) is not list or not 1<=len(polygons[0])<=33):
        raise ValueError('bounded_exact_signed_outline_context_required')
    def check():
        if time.monotonic()>=deadline_monotonic:
            raise ValueError('exact_signed_outline_deadline')
    rings=[];count=0;edges=[]
    for ri,points in enumerate(polygons[0]):
        check()
        if (type(points) is not list or not 4<=len(points)<=1024
                or any(type(p) not in (list,tuple) or len(p)!=2
                    or any(type(v) is not int or abs(v)>2_000_000_000 for v in p) for p in points)):
            raise ValueError('literal_bounded_integer_outline_ring_required')
        ring=[tuple(p) for p in points];count+=len(ring)
        if count>max_vertices:raise ValueError('exact_signed_outline_vertex_bound')
        if len(set(ring))!=len(ring):raise ValueError('repeated_exact_outline_vertex')
        if not sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(ring,ring[1:]+ring[:1])):
            raise ValueError('zero_area_exact_outline_ring')
        for i,b in enumerate(ring):
            a,c=ring[i-1],ring[(i+1)%len(ring)]
            # Collinear FORWARD vertices do not alter the shape. A reverse
            # overlap/backtrack at an adjacent joint is never excused.
            if _cross(a,b,c)==0 and (a[0]-b[0])*(c[0]-b[0])+(a[1]-b[1])*(c[1]-b[1])>0:
                raise ValueError('adjacent_exact_outline_boundary_overlap')
            edges.append((ri,i,b,c))
        rings.append(ring)
    checks=0
    for k,(ri,i,a,b) in enumerate(edges):
        check()
        for rj,j,c,d in edges[k+1:]:
            checks+=1
            if checks>max_pair_checks:raise ValueError('exact_signed_outline_pair_bound')
            if checks%128==0:check()
            if ri==rj and ((i-j)%len(rings[ri])) in (1,len(rings[ri])-1):continue
            if _intersect(a,b,c,d):
                raise ValueError('intersecting_exact_outline_boundaries')
    for i,hole in enumerate(rings[1:],1):
        check()
        if not _inside(hole[0],rings[0]):raise ValueError('exact_outline_hole_not_strictly_inside_outer')
        if any(_inside(hole[0],other) or _inside(other[0],hole)
                for j,other in enumerate(rings[1:],1) if i!=j):
            raise ValueError('nested_exact_outline_holes')
    check()
    return dict(ok=True,complete=True,method='exact_integer_disjoint_signed_outline_topology',
        vertices=count,holes=len(rings)-1,pair_checks=checks,numeric_tolerance_nm=0,
        source_geometry_repaired=False,current_or_release_authority=False)


def partition_one_polygon(polygons,*,deadline_monotonic,max_pieces=4096):
    """Exact simple octilinear pieces for a consumer without a hole schema.

    Split at literal vertex x coordinates. Boundary order is constant within
    each open slab; pair its exact lower/upper crossings to retain outer-minus-
    holes. Cardinal/45-degree edges give integer slab endpoints. No convex
    hull, triangulation filter, bbox, floating clipping or tolerance is used.
    """
    from fractions import Fraction
    require_one_polygon(polygons,deadline_monotonic=deadline_monotonic)
    if type(max_pieces) is not int or not 1<=max_pieces<=4096:
        raise ValueError('bounded_exact_outline_partition_required')
    rings=polygons[0];edges=[(a,b) for ring in rings for a,b in zip(ring,ring[1:]+ring[:1])]
    if any(a[0]!=b[0] and a[1]!=b[1] and abs(a[0]-b[0])!=abs(a[1]-b[1]) for a,b in edges):
        raise ValueError('integer_cardinal_or_45deg_partition_required')
    xs=sorted({p[0] for ring in rings for p in ring});pieces=[]
    def area2(ring):return abs(sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(ring,ring[1:]+ring[:1])))
    def y_at(edge,x):
        a,b=edge
        return Fraction(a[1])+Fraction(b[1]-a[1],b[0]-a[0])*(x-a[0])
    for left,right in zip(xs,xs[1:]):
        if time.monotonic()>=deadline_monotonic:raise ValueError('exact_outline_partition_deadline')
        mid=Fraction(left+right,2)
        active=sorted((y_at(e,mid),e) for e in edges if min(e[0][0],e[1][0])<mid<max(e[0][0],e[1][0]))
        if len(active)%2:raise ValueError('unpaired_exact_outline_slab_boundaries')
        for lower,upper in zip(active[::2],active[1::2]):
            if lower[0]>=upper[0]:raise ValueError('unordered_exact_outline_slab_boundaries')
            values=[y_at(e,x) for e,x in ((lower[1],left),(lower[1],right),(upper[1],right),(upper[1],left))]
            if any(v.denominator!=1 for v in values):raise ValueError('noninteger_exact_outline_partition_vertex')
            pts=[[x,int(y)] for x,y in zip((left,right,right,left),values)]
            ring=[]
            for point in pts:
                if not ring or point!=ring[-1]:ring.append(point)
            if ring[0]==ring[-1]:ring.pop()
            if len(ring)<3 or not area2(ring):raise ValueError('degenerate_exact_outline_slab')
            pieces.append(ring)
            if len(pieces)>max_pieces:raise ValueError('exact_outline_partition_piece_bound')
    if sum(area2(r) for r in pieces)!=area2(rings[0])-sum(area2(r) for r in rings[1:]):
        raise ValueError('exact_outline_partition_area_identity_changed')
    if time.monotonic()>=deadline_monotonic:raise ValueError('exact_outline_partition_deadline')
    return pieces
