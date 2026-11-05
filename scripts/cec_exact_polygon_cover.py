"""Bounded rational coverage of literal linear native polygon sets.

No integer clipping, rounding, raster sampling, area cutoff or geometry repair
decides coverage. All endpoint and crossing x-coordinates partition the plane
into slabs where boundary order is invariant; exact rational interval coverage
at each slab midpoint is therefore a complete area-set inclusion proof for
closed polygonal regions. Reverse fracture bridges cancel by signed winding.
Explicit holes subtract from their own outer, never another polygon's fill.

This proves the supplied polygon model only. It grants no physical field,
current, thermal, manufacturing or release qualification.
"""
from collections import defaultdict
from fractions import Fraction
import math
import time


def _check(deadline):
    if time.monotonic() >= deadline:
        raise ValueError('exact_polygon_coverage_deadline')


def _prepare(polygons, budget):
    if type(polygons) is not list or not 1 <= len(polygons) <= 1024:
        raise ValueError('bounded_literal_native_polygon_set_required')
    result=[]
    for polygon in polygons:
        if type(polygon) is not list or not 1 <= len(polygon) <= 256:
            raise ValueError('bounded_literal_native_polygon_holes_required')
        rings=[]
        for points in polygon:
            _check(budget['deadline'])
            if type(points) is not list or len(points) < 3:
                raise ValueError('literal_linear_native_ring_required')
            budget['vertices'] += len(points)
            if budget['vertices'] > budget['max_vertices']:
                raise ValueError('exact_polygon_input_vertex_bound')
            if any(type(p) not in (list,tuple) or len(p)!=2 or
                   any(type(v) is not int or abs(v)>2_000_000_000 for v in p) for p in points):
                raise ValueError('literal_integer_native_polygon_points_required')
            points=[tuple(p) for p in points]
            if points[0]==points[-1]:points=points[:-1]
            edges=list(zip(points,points[1:]+points[:1]))
            if (len(set(points)) < 3 or any(a==b for a,b in edges)
                    or not sum(a[0]*b[1]-a[1]*b[0] for a,b in edges)):
                raise ValueError('nondegenerate_linear_native_ring_required')
            rings.append(edges)
        result.append(rings)
    return result


def _union(rows):
    result=[]
    for lo,hi in sorted(rows):
        if lo>=hi:continue
        if result and lo<=result[-1][1]:
            result[-1]=(result[-1][0],max(hi,result[-1][1]))
        else:result.append((lo,hi))
    return result


def _subtract(rows,clips):
    result=[];clips=_union(clips)
    for lo,hi in rows:
        tip=lo
        for start,end in clips:
            if end<=tip:continue
            if start>=hi:break
            if start>tip:result.append((tip,min(start,hi)))
            tip=max(tip,end)
            if tip>=hi:break
        if tip<hi:result.append((tip,hi))
    return result


def _ring_intervals(edges,x,deadline):
    events=defaultdict(int)
    for index,(a,b) in enumerate(edges):
        if index%128==0:_check(deadline)
        if not min(a[0],b[0]) <= x < max(a[0],b[0]):continue
        y=Fraction(a[1])+(x-a[0])*Fraction(b[1]-a[1],b[0]-a[0])
        events[y]+=1 if b[0]>a[0] else -1
    winding=0;previous=None;rows=[]
    for y,delta in sorted(events.items()):
        if previous is not None and winding and previous<y:rows.append((previous,y))
        winding+=delta;previous=y
    if winding:raise ValueError('open_native_polygon_winding')
    return _union(rows)


def _intervals(polygons,x,deadline):
    result=[]
    for rings in polygons:
        outer=_ring_intervals(rings[0],x,deadline)
        holes=[row for ring in rings[1:] for row in _ring_intervals(ring,x,deadline)]
        result.extend(_subtract(outer,holes))
    return _union(result)


def _cross(a,b):return a[0]*b[1]-a[1]*b[0]


def _critical_x(edges,box,budget):
    x0,y0,x1,y1=box;events={Fraction(x0),Fraction(x1)};active=[]
    for a,b in edges:
        _check(budget['deadline'])
        if (max(a[0],b[0])<x0 or min(a[0],b[0])>x1
                or max(a[1],b[1])<y0 or min(a[1],b[1])>y1):continue
        active.append((a,b))
        for x,_ in (a,b):
            if x0<x<x1:events.add(Fraction(x))
        # Exact intersections with the query's horizontal box boundaries.
        if a[1]!=b[1]:
            for y in (y0,y1):
                if min(a[1],b[1])<=y<=max(a[1],b[1]):
                    x=Fraction(a[0])+Fraction(y-a[1],b[1]-a[1])*(b[0]-a[0])
                    if x0<x<x1:events.add(x)
    if len(active)>budget['max_active_edges']:
        raise ValueError('exact_polygon_active_boundary_bound')
    for i,(a,b) in enumerate(active):
        for c,d in active[i+1:]:
            budget['pair_checks']+=1
            if budget['pair_checks']>budget['max_pair_checks']:
                raise ValueError('exact_polygon_boundary_pair_bound')
            if budget['pair_checks']%128==0:_check(budget['deadline'])
            if (max(a[0],b[0])<min(c[0],d[0]) or max(c[0],d[0])<min(a[0],b[0])
                    or max(a[1],b[1])<min(c[1],d[1]) or max(c[1],d[1])<min(a[1],b[1])):continue
            u=(b[0]-a[0],b[1]-a[1]);v=(d[0]-c[0],d[1]-c[1]);den=_cross(u,v)
            if not den:continue  # Collinear order changes only at endpoints.
            delta=(c[0]-a[0],c[1]-a[1]);s=Fraction(_cross(delta,v),den);t=Fraction(_cross(delta,u),den)
            if not 0<=s<=1 or not 0<=t<=1:continue
            x=Fraction(a[0])+s*u[0];y=Fraction(a[1])+s*u[1]
            if x0<x<x1 and y0<=y<=y1:events.add(x)
            if len(events)>budget['max_slabs']+1:raise ValueError('exact_polygon_slab_bound')
    if len(events)>budget['max_slabs']+1:raise ValueError('exact_polygon_slab_bound')
    return sorted(events),len(active)


def cover(subjects,supports,*,timeout_s=10.,max_vertices=200000,
          max_active_edges=2048,max_slabs=4096,max_pair_checks=2_000_000):
    """Certify literal closed polygon inclusion, or return a rational gap."""
    result=dict(ok=False,complete=False,errors=[],method='exact_rational_nonzero_winding_slab_cover',
        numeric_tolerance_nm=0,area_omission_threshold=0,integer_boolean_clipping_used=False,
        source_geometry_repaired=False,release_authority=False,slabs_checked=0)
    started=time.monotonic()
    try:
        if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10.
                or any(type(v) is not int or not lo<=v<=hi for v,lo,hi in (
                    (max_vertices,32,200000),(max_active_edges,4,4096),
                    (max_slabs,1,8192),(max_pair_checks,1,4_000_000)))):
            raise ValueError('bounded_exact_polygon_coverage_context_required')
        budget=dict(deadline=started+timeout_s,vertices=0,max_vertices=max_vertices,
            max_active_edges=max_active_edges,max_slabs=max_slabs,pair_checks=0,max_pair_checks=max_pair_checks)
        source=_prepare(subjects,budget);support=_prepare(supports,budget)
        all_support=[e for rings in support for edges in rings for e in edges]
        for rings in source:
            boundary=[e for edges in rings for e in edges]
            points=[p for edge in boundary for p in edge]
            box=(min(x for x,y in points),min(y for x,y in points),
                 max(x for x,y in points),max(y for x,y in points))
            xs,active=_critical_x(boundary+all_support,box,budget)
            # Keep every boundary crossing the query x-range, including far
            # above/below it: these determine the exact baseline winding.
            def local(polygons):return [[
                [(a,b) for a,b in edges if max(a[0],b[0])>=box[0] and min(a[0],b[0])<=box[2]]
                for edges in poly] for poly in polygons]
            local_source=local([rings]);local_support=local(support)
            for left,right in zip(xs,xs[1:]):
                _check(budget['deadline']);x=(left+right)/2
                required=_intervals(local_source,x,budget['deadline'])
                available=_intervals(local_support,x,budget['deadline'])
                missing=_subtract(required,available);result['slabs_checked']+=1
                if missing:
                    y=(missing[0][0]+missing[0][1])/2
                    result.update(complete=True,uncovered_witness=dict(
                        x=[x.numerator,x.denominator],y=[y.numerator,y.denominator],
                        slab_x=[[v.numerator,v.denominator] for v in (left,right)],
                        gap_y=[[v.numerator,v.denominator] for v in missing[0]]))
                    return result
        _check(budget['deadline'])
        result.update(ok=True,complete=True,all_literal_subject_polygons_covered=True,
            input_vertices=budget['vertices'],boundary_pair_checks=budget['pair_checks'])
    except (ValueError,TypeError,KeyError,OverflowError,ZeroDivisionError) as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    finally:result['elapsed_s']=round(time.monotonic()-started,6)
    return result


def native_polygons(shape):
    """Copy literal native linear outlines/holes; no Boolean or unfracture."""
    result=[];count=0
    for i in range(shape.OutlineCount()):
        polygon=[]
        for ring in [shape.Outline(i),*[shape.Hole(i,j) for j in range(shape.HoleCount(i))]]:
            count+=ring.PointCount()
            if ring.ArcCount() or ring.PointCount()<3 or count>200000:
                raise ValueError('bounded_linear_native_cover_input_required')
            polygon.append([[int(ring.CPoint(k).x),int(ring.CPoint(k).y)] for k in range(ring.PointCount())])
        result.append(polygon)
    return result


def _distance_sq(point,a,b):
    dx,dy=b[0]-a[0],b[1]-a[1];px,py=point[0]-a[0],point[1]-a[1]
    length2=dx*dx+dy*dy;dot=px*dx+py*dy
    if dot<=0:return px*px+py*py
    if dot>=length2:return (point[0]-b[0])**2+(point[1]-b[1])**2
    return Fraction((px*dy-py*dx)**2,length2)


def capsules_covered(subjects,supports,*,timeout_s=10.,max_triangle_checks=4096):
    """Sufficient exact physical straight-capsule union certificate.

    Endpoint discs must fit old same-net/face capsules analytically. The real
    rectangular sweep is enclosed OUTWARDS by a rational canonical rectangle;
    a finite fan triangulation receives each triangle in one convex old
    capsule using exact squared distances. No old polygon approximation or
    tolerated uncovered fringe supports this proof. Failure is unproven,
    never a claim that an actual path is impossible.
    """
    r=dict(ok=False,complete=False,errors=[],method='exact_rational_physical_capsule_fan_cover',
        numeric_tolerance_nm=0,curve_approximation_accepted_as_source=False,
        source_geometry_repaired=False,new_reference_deficit_qualified=False,release_authority=False,
        triangle_checks=0,proofs=[])
    started=time.monotonic()
    try:
        if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10.
                or type(max_triangle_checks) is not int or not 1<=max_triangle_checks<=16384):
            raise ValueError('bounded_physical_capsule_certificate_required')
        deadline=started+timeout_s
        def validate(rows):
            if type(rows) is not list or not 1<=len(rows)<=64:
                raise ValueError('bounded_literal_physical_capsules_required')
            for q in rows:
                if (type(q) is not dict or set(q)!={'net','layer','start_nm','end_nm','width_nm'}
                        or type(q['net']) is not str or not q['net'] or type(q['layer']) is not int
                        or type(q['width_nm']) is not int or not 0<q['width_nm']<=1000000
                        or any(type(q[k]) not in (list,tuple) or len(q[k])!=2 or
                               any(type(v) is not int or abs(v)>2000000000 for v in q[k])
                               for k in ('start_nm','end_nm'))
                        or tuple(q['start_nm'])==tuple(q['end_nm'])):
                    raise ValueError('exact_positive_native_capsule_geometry_required')
        validate(subjects);validate(supports)
        def inside(p,q,disc=0):
            gap=q['width_nm']-disc
            return gap>=0 and 4*_distance_sq(p,q['start_nm'],q['end_nm'])<=gap*gap
        for row in subjects:
            _check(deadline);a,b=tuple(row['start_nm']),tuple(row['end_nm']);w=row['width_nm']
            owners=[q for q in supports if (q['net'],q['layer'])==(row['net'],row['layer'])]
            if not owners or not all(any(inside(p,q,w) for q in owners) for p in (a,b)):
                raise ValueError('physical_endpoint_disc_cover_unproven')
            if any(all(inside(p,q,w) for p in (a,b)) for q in owners):
                r['proofs'].append(dict(mode='one_unchanged_convex_capsule',net=row['net'],layer=row['layer']))
                continue
            dx,dy=b[0]-a[0],b[1]-a[1];radius=Fraction(w,2)
            if dx==0:offset=(radius,0)
            elif dy==0:offset=(0,radius)
            elif abs(dx)==abs(dy):
                step=math.isqrt(w*w//8)
                if 8*step*step<w*w:step+=1
                offset=(-step if dy>0 else step,step if dx>0 else -step)
            else:raise ValueError('canonical_rectangle_capsule_certificate_required')
            polygon=[(p[0]+sign*offset[0],p[1]+sign*offset[1]) for p,sign in ((a,1),(b,1),(b,-1),(a,-1))]
            anchor=(Fraction(a[0]+b[0],2),Fraction(a[1]+b[1],2))
            fan_owners=[q for q in owners if inside(anchor,q)]
            if not fan_owners:raise ValueError('physical_capsule_fan_anchor_unproven')
            def edge(first,last,depth=0):
                _check(deadline);r['triangle_checks']+=1
                if r['triangle_checks']>max_triangle_checks:
                    raise ValueError('physical_capsule_fan_work_bound')
                if any(inside(first,q) and inside(last,q) for q in fan_owners):return
                if depth>=16 or not all(any(inside(p,q) for q in fan_owners) for p in (first,last)):
                    raise ValueError('physical_capsule_triangle_cover_unproven')
                # Preserve exact rationals even for initially integral edges.
                middle=(Fraction(first[0]+last[0],2),Fraction(first[1]+last[1],2))
                edge(first,middle,depth+1);edge(middle,last,depth+1)
            for first,last in zip(polygon,polygon[1:]+polygon[:1]):edge(first,last)
            r['proofs'].append(dict(mode='outward_rectangle_and_exact_endpoint_discs',net=row['net'],
                layer=row['layer'],endpoint_discs_in_original_material=True,
                every_fan_triangle_in_one_convex_original_capsule=True))
        _check(deadline);r.update(ok=True,complete=True,all_actual_new_capsules_in_old_material=True)
    except (ValueError,TypeError,KeyError,OverflowError,ZeroDivisionError) as exc:
        r['errors'].append(type(exc).__name__+':'+str(exc))
    r['elapsed_s']=round(time.monotonic()-started,6)
    return r
