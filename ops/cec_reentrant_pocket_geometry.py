"""Only true re-entrant pockets; do not square off purposeful convex chamfers."""
import pcbnew
import time
import cec_rectilinear_copper as native
import cec_shallow_copper_pocket_cover as shallow

def reentrant(offer):
    ring=offer['source_points_nm'];chain=offer['source_window_nm']
    orientation=sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(ring,ring[1:]+ring[:1]))
    if not orientation:raise ValueError('positive_area_source_ring_required')
    return any(((b[0]-a[0])*(c[1]-b[1])-(b[1]-a[1])*(c[0]-b[0]))*orientation<0
        for a,b,c in zip(chain,chain[1:],chain[2:]))

def merged(points, addition):
    """Exact native cover which strictly reduces the current boundary vertices."""
    result=native._poly(points);result.BooleanAdd(native._poly(addition))
    if result.OutlineCount()!=1 or result.HoleCount(0):raise ValueError('simple_batch_source_cover_required')
    r=result.Outline(0)
    candidate=shallow.compact([[r.CPoint(i).x,r.CPoint(i).y] for i in range(r.PointCount())])
    if not 4<=len(candidate)<len(shallow.compact(points)):raise ValueError('strict_batch_boundary_vertex_improvement_required')
    if not all(native._centerline_allowed(a,b,'chamfer45') for a,b in zip(candidate,candidate[1:]+candidate[:1])):
        raise ValueError('literal_octilinear_batch_boundary_required')
    lost=native._poly(points);lost.BooleanSubtract(native._poly(candidate))
    if lost.OutlineCount():raise ValueError('zero_native_batch_source_loss_required')
    return candidate

def local_mask(old_fill, old_points, new_points, min_thickness_nm):
    """Retain old metal, permitting fresh material only near planned pockets.

    The halo is derived from the UNCHANGED native minimum feature dimension,
    not a clearance waiver. All new material still needs actual native DRC.
    """
    patch=addition_window(old_points,new_points,min_thickness_nm)
    permitted=old_fill.CloneDropTriangulation();permitted.BooleanAdd(patch)
    return permitted

def addition_window(old_points,new_points,min_thickness_nm):
    if type(min_thickness_nm) is not int or not 1<=min_thickness_nm<=1000000:
        raise ValueError('bounded_source_native_minimum_feature_required')
    patch=native._poly(new_points);patch.BooleanSubtract(native._poly(old_points))
    patch.Inflate((min_thickness_nm+1)//2,pcbnew.CORNER_STRATEGY_CHAMFER_ALL_CORNERS,1)
    return patch

def visible_support_envelope(board,net,face,points,*,process_halo_nm=0,timeout_s=5.):
    """0/45 support bounds of ACTUAL local source metal, not owner outlines.

    A nominal pocket hidden by a real via/pad must not create a new exterior
    spur. Holes do not enlarge an outer support hull. This only constrains
    proposals; it establishes no conductor/current or manufacturing rating.
    """
    deadline=time.monotonic()+timeout_s
    x0=min(p[0] for p in points)-1000000;y0=min(p[1] for p in points)-1000000
    x1=max(p[0] for p in points)+1000000;y1=max(p[1] for p in points)+1000000
    window=native._poly([[x0,y0],[x1,y0],[x1,y1],[x0,y1]])
    source=pcbnew.SHAPE_POLY_SET();items=[*board.GetTracks(),*[p for fp in board.GetFootprints() for p in fp.Pads()],*board.Zones()]
    if len(items)>16384:raise ValueError('finite_actual_source_support_inventory_required')
    count=0
    for item in items:
        native._check_deadline(deadline)
        if item.GetNetname()!=net or not item.IsOnLayer(face):continue
        if item.GetClass()=='ZONE':
            if item.GetIsRuleArea():continue
            if not item.IsFilled() or not item.HasFilledPolysForLayer(face):raise ValueError('actual_source_support_fill_unavailable')
            poly=item.GetFilledPolysList(face).CloneDropTriangulation()
        else:
            poly=pcbnew.SHAPE_POLY_SET();item.TransformShapeToPolygon(poly,face,0,1,pcbnew.ERROR_OUTSIDE,False)
        if not poly.BBox().Intersects(window.BBox()):continue
        poly.BooleanIntersection(window)
        if not poly.OutlineCount():continue
        count+=1
        if count>512:raise ValueError('finite_local_actual_source_support_bound')
        source.Append(poly)
    if not source.OutlineCount():raise ValueError('positive_actual_source_support_required')
    cloud=set()
    for i in range(source.OutlineCount()):
        ring=source.Outline(i)
        if ring.ArcCount():raise ValueError('linear_native_source_support_required')
        cloud.update((ring.CPoint(j).x,ring.CPoint(j).y) for j in range(ring.PointCount()))
    if not 3<=len(cloud)<=200000:raise ValueError('bounded_native_source_support_point_cloud_required')
    # Integer monotone-chain hull: every vertex is an unchanged source point.
    # This is a read-only constraint, NOT geometry emitted as copper.
    ordered=sorted(cloud)
    def cross(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    halves=[]
    for seq in (ordered,list(reversed(ordered))):
        half=[]
        for point in seq:
            while len(half)>=2 and cross(half[-2],half[-1],point)<=0:half.pop()
            half.append(point)
        halves.append(half[:-1])
    hull=native._poly([*halves[0],*halves[1]])
    if type(process_halo_nm) is not int or not 0<=process_halo_nm<=500000:
        raise ValueError('bounded_source_process_offset_required')
    if process_halo_nm:hull.Inflate(process_halo_nm,pcbnew.CORNER_STRATEGY_CHAMFER_ALL_CORNERS,1)
    ring=hull.Outline(0)
    return [[ring.CPoint(i).x,ring.CPoint(i).y] for i in range(ring.PointCount())]
