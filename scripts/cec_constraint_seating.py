"""Finite contact candidates for the intersection of local electrical limits.

Only proposal geometry lives here. A native whole-board evaluation must admit
every result. This is not a no-path proof, a replacement for ordinary local
search, or permission to change a power/return distance contract.
"""
import math


def _circle_intersections(a, ar, b, br):
    dx, dy = b[0]-a[0], b[1]-a[1]
    distance = math.hypot(dx, dy)
    if distance <= 1e-12 or distance > ar+br+1e-9 or distance < abs(ar-br)-1e-9:
        return []
    along = (ar*ar-br*br+distance*distance)/(2*distance)
    height = math.sqrt(max(0., ar*ar-along*along))
    x, y = a[0]+along*dx/distance, a[1]+along*dy/distance
    return [(x-height*dy/distance, y+height*dx/distance),
            (x+height*dy/distance, y-height*dx/distance)]


def _contacts(origin, disks, rectangles):
    """Boundary intersections and nearest-point projections, not a grid."""
    points = [origin]
    for center, radius in disks:
        points.append(center)
        dx, dy = origin[0]-center[0], origin[1]-center[1]
        distance = math.hypot(dx, dy)
        if distance:
            points.append((center[0]+radius*dx/distance, center[1]+radius*dy/distance))
        points.extend((center[0]+radius*dx, center[1]+radius*dy)
                      for dx, dy in ((1,0),(-1,0),(0,1),(0,-1)))
    points.extend(_circle_intersections(disks[0][0],disks[0][1],disks[1][0],disks[1][1]))
    # A feasible point nearest the old centre can lie on a courtyard edge,
    # at an electrical/edge intersection, or at two courtyard boundaries.
    xs = sorted({x for x0,y0,x1,y1 in rectangles for x in (x0,x1)})
    ys = sorted({y for x0,y0,x1,y1 in rectangles for y in (y0,y1)})
    for x in xs:
        points.append((x,origin[1]))
        for (cx,cy),radius in disks:
            h2 = radius*radius-(x-cx)**2
            if h2 >= -1e-12:
                h = math.sqrt(max(0.,h2)); points.extend(((x,cy-h),(x,cy+h)))
    for y in ys:
        points.append((origin[0],y))
        for (cx,cy),radius in disks:
            h2 = radius*radius-(y-cy)**2
            if h2 >= -1e-12:
                h = math.sqrt(max(0.,h2)); points.extend(((cx-h,y),(cx+h,y)))
    # Clip before taking the edge cross product; distant board furniture
    # must not create a quadratic whole-board placement cloud.
    (cx,cy),radius = disks[0]
    xs = [x for x in xs if abs(x-cx) <= radius+1e-9]
    ys = [y for y in ys if abs(y-cy) <= radius+1e-9]
    points.extend((x,y) for x in xs for y in ys)
    return points


def contact_poses(row, *, forbidden_centers, feasible=lambda pose: True,
                  target_margin_mm=.02, max_checks=128, max_results=2,
                  max_obstacles=64):
    """Seat a two-pad bypass in both supply and return disks at once.

    ``forbidden_centers(angle)`` supplies finite axis-aligned rectangles in
    x0,y0,x1,y1 order, already expanded by the rotated footprint courtyard.
    Four native orientations use measured terminal offsets. The caller keeps
    existing proposal families and performs full frozen-copper/craft checks.
    Unsupported loop contracts are left to their existing constructor.
    """
    if (not math.isfinite(target_margin_mm) or target_margin_mm < 0
            or any(type(v) is not int or v < 1 for v in
                   (max_checks,max_results,max_obstacles))):
        raise ValueError('invalid bounded contact-seating policy')
    report = dict(schema=1, checked=0, returned=0, population=0,
                  truncated_orientations=0, exhaustion_is_no_path_proof=False)
    if (row.get('pin_proximity_mode')!='isolated_tangent_supply'
            or row.get('return_gate_mode')!='absolute_ground_distance'):
        return [], dict(report,reason='unsupported_contract')
    try:
        def point(value):
            if not isinstance(value,(list,tuple)) or len(value)!=2:raise ValueError()
            result = tuple(float(v) for v in value)
            if not all(math.isfinite(v) for v in result):raise ValueError()
            return result
        origin = point(row.get('cap_position_mm'))
        supply_pad = point(row.get('cap_supply_position_mm'))
        return_pad = point(row.get('cap_ground_position_mm'))
        owner_supply = point(row.get('owner_supply_position_mm'))
        owner_returns = [point(p['position'] if isinstance(p,dict) else p)
                         for p in row.get('owner_ground_positions_mm') or ()]
        rotation = float(row['cap_orientation_deg'])
        tangent = row['tangent_target']
        ideal = float(tangent.get('proximity_supply_mm') if tangent.get('return_constrained')
                      else tangent['best_loop']['supply_mm'])
        allowance = float(row['pin_proximity_excess_limit_mm'])
        return_limit = float(row['return_limit_mm'])
        if (not owner_returns or not all(math.isfinite(v) for v in
                (rotation,ideal,allowance,return_limit)) or min(ideal,allowance,return_limit)<0):
            raise ValueError()
    except (ValueError,TypeError,KeyError,OverflowError):
        return [], dict(report,reason='invalid_or_missing_geometry')
    supply_radius = ideal+max(0.,allowance-target_margin_mm)
    return_radius = return_limit-target_margin_mm
    if supply_radius<=0 or return_radius<=0:
        return [], dict(report,reason='empty_margin_domain')
    from cec_placement_search_domain import rotate_board_point
    ranked,seen = [],set()
    for delta in (0,180,90,270):
        angle = (rotation+delta)%360
        rail = rotate_board_point(supply_pad,origin,delta)
        ret = rotate_board_point(return_pad,origin,delta)
        supply_center = tuple(s-r+o for s,r,o in zip(owner_supply,rail,origin))
        boxes = []
        for rectangle in forbidden_centers(angle):
            try:
                x0,y0,x1,y1 = map(float,rectangle)
                if not all(math.isfinite(v) for v in (x0,y0,x1,y1)) or x0>=x1 or y0>=y1:
                    raise ValueError()
            except (ValueError,TypeError):
                return [],dict(report,reason='invalid_courtyard_domain')
            if (x1<supply_center[0]-supply_radius or x0>supply_center[0]+supply_radius
                    or y1<supply_center[1]-supply_radius or y0>supply_center[1]+supply_radius):
                continue
            boxes.append((x0,y0,x1,y1))
        boxes = sorted(set(boxes))
        if len(boxes)>max_obstacles:
            report['truncated_orientations']+=1
            continue   # Do not silently drop an obstacle to meet the work cap.
        for ground in owner_returns:
            ground_center = tuple(g-r+o for g,r,o in zip(ground,ret,origin))
            disks = [(supply_center,supply_radius),(ground_center,return_radius)]
            if math.dist(supply_center,ground_center)>supply_radius+return_radius+1e-9:
                continue
            for x,y in _contacts(origin,disks,boxes):
                pose = (round(x,6),round(y,6),angle)
                if pose in seen:continue
                seen.add(pose)
                x,y=pose[:2]
                if delta==0 and math.dist((x,y),origin)<1e-8:continue
                if any(x0+1e-9<x<x1-1e-9 and y0+1e-9<y<y1-1e-9 for x0,y0,x1,y1 in boxes):
                    continue
                supply = math.dist((x,y),supply_center)
                back = min(math.dist((x+ret[0]-origin[0],y+ret[1]-origin[1]),g) for g in owner_returns)
                # Native coordinates round to 1 nm; keep the full 0.02 mm
                # design margin and only tolerate one rounding unit here.
                if supply>supply_radius+1e-6 or back>return_radius+1e-6:continue
                rank = (round(math.dist((x,y),origin),6),delta!=0,round(supply+back,6),delta,x,y)
                ranked.append((rank,dict(position=pose,predicted_supply_mm=supply,
                    predicted_ground_mm=back,predicted_proximity_excess_mm=max(0.,supply-ideal))))
    ranked.sort(key=lambda item:item[0]);report['population']=len(ranked)
    result=[]
    for _rank,proposal in ranked[:max_checks]:
        report['checked']+=1
        if feasible(proposal['position']):
            result.append(proposal)
            if len(result)>=max_results:break
    report['returned']=len(result)
    return result,report
