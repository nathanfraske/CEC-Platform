"""Bounded, width-preserving detours for an already declared rail graph.

This proposes centerlines only. It never changes terminals, layers, current
ratings, or via fields. Native whole-board admission is still required.
"""
import math
import time


def contact_targets(point, trunk, layer, *, limit=16):
    """Nearest actual centre-line attachments, not the obsolete planned band."""
    from shapely.geometry import LineString, Point
    if type(limit) is not int or limit<0:
        raise ValueError('invalid contact target limit')
    targets=set()
    for s in trunk:
        if s[5]!=layer or math.dist(s[:2],s[2:4])<1e-6: continue
        line=LineString((s[:2],s[2:4]))
        p=line.interpolate(line.project(Point(*point)))
        targets.add((round(p.x,6),round(p.y,6)))
    return sorted(targets,key=lambda p:(math.dist(p,point),p))[:limit]


def _anchor_chains(plan, points, anchors):
    """Contract only virtual degree-two, equal-width, same-layer vertices.

    Physical contacts/array sites are explicit anchors. Branches, width steps,
    layer transitions and cycles remain fixed. A generated elbow is routing
    intent, not another terminal that must stay inside an obstruction.
    """
    from collections import defaultdict
    from shapely.geometry import LineString, Point

    edges = []
    incident = defaultdict(list)
    layers_at = defaultdict(set)
    for index, row in enumerate(plan):
        line = LineString((row[:2], row[2:4]))
        joints = sorted({row[:2], row[2:4]} |
                        {p for p in points if line.distance(Point(p)) < 1e-8},
                        key=lambda p: line.project(Point(p)))
        pairs = list(zip(joints, joints[1:])) or [(row[:2], row[2:4])]
        for a, b in pairs:
            edge_id = len(edges)
            edges.append((index, (*a, *b, row[4], row[5])))
            for p in (a, b):
                incident[(p, row[5])].append(edge_id)
                layers_at[p].add(row[5])

    def fixed(point, layer):
        ids = incident[(point, layer)]
        return (point in anchors or len(set(ids)) != 2 or len(layers_at[point]) != 1
                or edges[ids[0]][1][4] != edges[ids[1]][1][4])

    visited = set()
    chains = []
    for first, (index, row) in enumerate(edges):
        if first in visited:
            continue
        a, b, width, layer = row[:2], row[2:4], row[4], row[5]
        # Find a fixed end even when declaration order starts inside a chain.
        point, edge_id = a, first
        back_seen = set()
        while not fixed(point, layer) and edge_id not in back_seen:
            back_seen.add(edge_id)
            edge_id = next(i for i in incident[(point, layer)] if i != edge_id)
            part = edges[edge_id][1]
            point = part[2:4] if part[:2] == point else part[:2]
        start = point
        parts, chain_points, indices = [], [start], []
        while edge_id not in visited:
            visited.add(edge_id)
            source_index, part = edges[edge_id]
            end = part[2:4] if part[:2] == point else part[:2]
            parts.append((*point, *end, width, layer))
            chain_points.append(end)
            indices.append(source_index)
            point = end
            if fixed(point, layer):
                break
            edge_id = next(i for i in incident[(point, layer)] if i != edge_id)
        if chain_points[0] == chain_points[-1]:
            # A free cycle is not permission to delete copper or an anchor.
            chains.extend((i, [s], [s[:2], s[2:4]], [])
                          for i, s in zip(indices, parts))
        else:
            chains.append((min(indices), parts,
                           [chain_points[0], chain_points[-1]], chain_points[1:-1]))
    return chains


def _chain_backtracks(segments):
    for first,second in zip(segments,segments[1:]):
        if first[2:4]!=second[:2]:
            continue
        a=(first[0]-first[2],first[1]-first[3])
        b=(second[2]-second[0],second[3]-second[1])
        length=math.hypot(*a)*math.hypot(*b)
        if length>1e-12 and a[0]*b[0]+a[1]*b[1]>length*1e-9:
            return True  # Outgoing opening angle below 90 degrees.
    return False


def has_virtual_backtrack(plan, *, anchors=()):
    """Only unanchored degree-two/equal-width/same-layer chain bends count."""
    plan=[tuple(row) for row in plan]
    points={p for row in plan for p in (row[:2],row[2:4])}
    anchors={tuple(point) for point in anchors}
    return any(_chain_backtracks(parts) for _,parts,_,_ in
               _anchor_chains(plan,points|anchors,anchors))


def repair_plan(plan, *, region, obstacles_for, collision, anchors=(),
                deadline=None, max_corners=96, relax_unanchored_bends=False,
                repair_topology=False):
    """Return a complete replacement or refuse without a partial graph.

    Split obstructed edges at every tap, crossing and transition endpoint
    before searching. Merely routing the two extremes would orphan the
    intermediate branches of a bus. All dimensions are in millimetres.
    Obstacle geometry already includes the caller's electrical clearance.
    With explicit caller consent, virtual same-width/layer elbows may move;
    every physical contact and via field must then be supplied in ``anchors``.
    ``repair_topology`` additionally re-routes a clear but acute virtual chain,
    as can occur when an uncommitted transition moves past its old body elbow.
    """
    from shapely.geometry import LineString, Point
    from cec_pour_plan import _LayerSpace, _find_path, _ReliefBudgetExceeded
    from cec_precision_route import _chamfer_axis_path
    plan=[tuple(row) for row in plan]
    deadline=time.monotonic()+1.0 if deadline is None else float(deadline)
    report=dict(schema=1,changed=False,detours=[],admitted=False)
    if any(len(s)!=6 or not all(math.isfinite(float(v)) for v in s[:5])
           or s[4]<=0 for s in plan):
        raise ValueError('invalid declared rail geometry')
    anchors={tuple(p) for p in anchors}
    if any(len(p)!=2 or not all(math.isfinite(float(v)) for v in p) for p in anchors):
        raise ValueError('invalid fixed rail anchor')
    points=set(anchors)
    for s in plan:points.update((s[:2],s[2:4]))
    # Include same-layer segment crossings even if neither declares a vertex.
    for i,a in enumerate(plan):
        for b in plan[i+1:]:
            if a[5]!=b[5]:continue
            cross=LineString((a[:2],a[2:4])).intersection(LineString((b[:2],b[2:4])))
            if cross.geom_type=='Point':points.add((cross.x,cross.y))
    groups=[]
    if relax_unanchored_bends:
        groups=_anchor_chains(plan, points, anchors)
    else:
        for index,s in enumerate(plan):
            line=LineString((s[:2],s[2:4]))
            joints=sorted({s[:2],s[2:4]}|{p for p in points if line.distance(Point(p))<1e-8},
                          key=lambda p:line.project(Point(p)))
            groups.append((index,[s],joints,[]))
    result=[];spaces={}
    try:
        for index,segments,joints,virtual_bends in groups:
            blocked=collision(segments)
            backtrack=bool(repair_topology and relax_unanchored_bends
                           and _chain_backtracks(segments))
            if blocked is None and not backtrack:
                result.extend(segments);continue
            if time.monotonic()>=deadline:raise _ReliefBudgetExceeded('rail_detour_budget')
            width,tag=segments[0][4:]
            key=(width,tag)
            if key not in spaces:
                spaces[key]=_LayerSpace(region.buffer(-width/2,join_style=2),
                                       list(obstacles_for(tag)),width/2)
            space=spaces[key];replacement=[]
            for start,end in zip(joints,joints[1:]):
                path,_=_find_path(space,start,end,max_corners=max_corners,deadline=deadline)
                if not path:
                    return None,{**report,'reason':'fixed_terminal_or_channel_blocked',
                                 'segment':index,'start':start,'end':end,'layer':tag,
                                 'start_legal':space.ok_pt(start),'end_legal':space.ok_pt(end),
                                 'virtual_bends':[list(p) for p in virtual_bends]}
                # Polishing is subordinate to width/clearance and cannot
                # trim across an obstruction at an outside corner.
                chamfered=_chamfer_axis_path(path)
                if all(space.ok_line(x,y) for x,y in zip(chamfered,chamfered[1:])):
                    path=chamfered
                replacement.extend((*x,*y,width,tag) for x,y in zip(path,path[1:])
                                   if math.dist(x,y)>1e-8)
            refusal=collision(replacement)
            if refusal:
                return None,{**report,'reason':'independent_collision_guard','detail':str(refusal)}
            result.extend(replacement)
            report['detours'].append(dict(segment=index,width_mm=width,layer=tag,
                fixed_junctions=[list(p) for p in joints],segments=len(replacement),
                virtual_bends=[list(p) for p in virtual_bends],
                trigger='collision' if blocked is not None else 'acute_virtual_backtrack'))
    except _ReliefBudgetExceeded:
        return None,{**report,'reason':'bounded_search_exhausted'}
    if collision(result):
        return None,{**report,'reason':'whole_plan_collision'}
    if repair_topology and relax_unanchored_bends and has_virtual_backtrack(result,anchors=anchors):
        return None,{**report,'reason':'virtual_backtrack_unresolved'}
    return result,{**report,'changed':bool(report['detours']),'reason':'proposal'}


def native_region(board, *, edge_clearance_mm):
    """Exact native edge domain, including slots; no bounding-box fallback."""
    import pcbnew
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    outline=pcbnew.SHAPE_POLY_SET()
    if not board.GetBoardPolygonOutlines(outline,False):return None
    def ring(chain):
        return [(chain.CPoint(i).x/1e6,chain.CPoint(i).y/1e6)
                for i in range(chain.PointCount())]
    polygons=[Polygon(ring(outline.Outline(i)),
                      [ring(outline.Hole(i,j)) for j in range(outline.HoleCount(i))])
              for i in range(outline.OutlineCount())]
    if not polygons or any(not p.is_valid for p in polygons):return None
    return unary_union(polygons).buffer(-float(edge_clearance_mm),join_style=2)
