"""Bounded exact identities for native filled polygons and hole bridges.

Identity hashes representation, not approximate geometry or current capacity.
Repeated bridge vertices are preserved verbatim. Identity never simplifies or
unfractures a shape. The separate decoder below can unwrap a PRIVATE clone
only after exact edge-inventory and bidirectional native-set verification.
"""


def identity(shape, deadline, *, max_vertices=200000):
    import cec_rectilinear_copper as native
    if type(max_vertices) is not int or not 32 <= max_vertices <= 200000:
        raise native.Refused('invalid_native_fill_identity_bound')
    polygons=[];vertices=0
    for i in range(shape.OutlineCount()):
        rings=[]
        for ring in [shape.Outline(i),*[shape.Hole(i,j) for j in range(shape.HoleCount(i))]]:
            native._check_deadline(deadline);count=ring.PointCount();vertices+=count
            if ring.ArcCount() or count<3 or vertices>max_vertices:
                raise native.Refused('bounded_native_fill_required')
            points=[(int(ring.CPoint(k).x),int(ring.CPoint(k).y)) for k in range(count)]
            if any(abs(v)>2000000000 for point in points for v in point):
                raise native.Refused('native_fill_coordinate_bound')
            lowest=min(points);anchors=[k for k,p in enumerate(points) if p==lowest]
            if len(anchors)>64:raise native.Refused('native_fill_bridge_anchor_bound')
            choices=[]
            for k in anchors:
                forward=points[k:]+points[:k]
                choices.extend([forward,[forward[0],*reversed(forward[1:])]])
            rings.append(min(choices))
        polygons.append([rings[0],*sorted(rings[1:])])
    native._check_deadline(deadline)
    return native._digest(sorted(polygons)),vertices


def snapshot(shape, deadline, *, max_vertices=200000, max_polygons=256):
    """Literal bounded native outlines/holes; retain fracture bridge vertices."""
    import cec_rectilinear_copper as native
    identity(shape,deadline,max_vertices=max_vertices)
    if not 1<=shape.OutlineCount()<=max_polygons:
        raise native.Refused('native_source_polygon_count_bound')
    return [
        [[[int(ring.CPoint(k).x),int(ring.CPoint(k).y)]
          for k in range(ring.PointCount())]
         for ring in [shape.Outline(i),*[shape.Hole(i,j) for j in range(shape.HoleCount(i))]]]
        for i in range(shape.OutlineCount())]


def reconstruct(polygons, deadline, *, max_vertices=200000, max_polygons=256):
    """Exact native topology from a validated literal source snapshot."""
    import pcbnew
    import cec_rectilinear_copper as native
    if type(polygons) is not list or not 1<=len(polygons)<=max_polygons:
        raise native.Refused('native_source_polygon_count_bound')
    shape=pcbnew.SHAPE_POLY_SET();count=0
    for polygon in polygons:
        native._check_deadline(deadline)
        if type(polygon) is not list or not 1<=len(polygon)<=256:
            raise native.Refused('native_source_hole_count_bound')
        index=shape.NewOutline()
        for j,points in enumerate(polygon):
            if type(points) is not list or len(points)<3:
                raise native.Refused('invalid_native_source_ring')
            count+=len(points)
            if count>max_vertices:raise native.Refused('bounded_native_fill_required')
            hole=-1 if j==0 else shape.NewHole(index)
            for point in points:
                if (type(point) is not list or len(point)!=2
                        or any(type(v) is not int or abs(v)>2_000_000_000 for v in point)):
                    raise native.Refused('invalid_native_source_point')
                shape.Append(point[0],point[1],index,hole)
    identity(shape,deadline,max_vertices=max_vertices)
    return shape


def source_fill(source, deadline):
    """Legacy single ring or explicit compound native source, never both."""
    import cec_rectilinear_copper as native
    if 'fill_nm' in source and 'fill_polygons_nm' not in source:
        return reconstruct([[source['fill_nm']]],deadline)
    if 'fill_polygons_nm' in source and 'fill_nm' not in source:
        return reconstruct(source['fill_polygons_nm'],deadline)
    raise native.Refused('ambiguous_native_source_fill_representation')


def decode_linear_hole_bridges(shape, deadline, *, max_vertices=200000):
    """Decode native zero-width bridges, with ZERO changed native copper.

    Never buffer/make-valid an invalid floating polygon. Only exactly paired
    reverse edges may be bridges. Every bridge must yield one actual hole or
    separate contour, the remaining literal boundary edges must be unchanged,
    and both native set differences must be empty. Source is never modified.
    Ambiguous/malformed rings stay unknown; this is not current authority.
    """
    from collections import Counter
    from math import gcd
    import cec_rectilinear_copper as native
    if type(max_vertices) is not int or not 32 <= max_vertices <= 200000:
        raise native.Refused('invalid_native_bridge_vertex_bound')

    def edges(item, permit_bridges):
        boundary = Counter(); bridges = 0; vertices = 0; holes = 0
        for i in range(item.OutlineCount()):
            holes += item.HoleCount(i)
            for ring in [item.Outline(i), *[item.Hole(i,j) for j in range(item.HoleCount(i))]]:
                native._check_deadline(deadline); count = ring.PointCount(); vertices += count
                if ring.ArcCount() or count < 3 or vertices > max_vertices:
                    raise native.Refused('bounded_linear_native_bridge_ring_required')
                points = [(int(ring.CPoint(k).x), int(ring.CPoint(k).y)) for k in range(count)]
                if len(points)>1 and points[0]==points[-1]: points=points[:-1]
                if any(abs(v)>2000000000 for point in points for v in point):
                    raise native.Refused('native_bridge_coordinate_bound')
                if not permit_bridges and len(set(points)) != len(points):
                    raise native.Refused('native_bridge_decode_still_has_repeated_vertices')
                directed = Counter(zip(points, points[1:]+points[:1]))
                if any(a == b or n != 1 for (a,b), n in directed.items()):
                    raise native.Refused('ambiguous_or_zero_native_bridge_edge')
                cancelled = set()
                for a,b in directed:
                    native._check_deadline(deadline)
                    if (a,b) in cancelled: continue
                    if (b,a) in directed:
                        if not permit_bridges: raise native.Refused('undecoded_reverse_native_edge')
                        cancelled.update(((a,b),(b,a))); bridges += 1
                    else:
                        boundary[tuple(sorted((a,b)))] += 1
        # Native Unfracture can remove a collinear bridge-attachment vertex.
        # Prove the SAME line intervals with integer endpoint events instead
        # of requiring the incidental split into two collinear segments.
        # No snapping, rounding, angle tolerance or displacement is allowed.
        lines = {}
        for (a,b), multiplicity in boundary.items():
            native._check_deadline(deadline)
            dx,dy = b[0]-a[0],b[1]-a[1]; divisor = gcd(abs(dx),abs(dy))
            ux,uy = dx//divisor,dy//divisor
            if ux<0 or ux==0 and uy<0: ux,uy=-ux,-uy
            key=(ux,uy,ux*a[1]-uy*a[0])
            lo,hi=sorted((ux*a[0]+uy*a[1],ux*b[0]+uy*b[1]))
            events=lines.setdefault(key,Counter()); events[lo]+=multiplicity; events[hi]-=multiplicity
        exact = {key:tuple(sorted((at,delta) for at,delta in events.items() if delta))
                 for key,events in lines.items()}
        return exact, bridges, vertices, holes

    first, bridge_count, input_vertices, old_holes = edges(shape, True)
    if not bridge_count:
        raise native.Refused('actual_paired_native_hole_bridges_required')
    decoded = shape.CloneDropTriangulation()
    native._check_deadline(deadline); decoded.Unfracture(); native._check_deadline(deadline)
    last, _, output_vertices, new_holes = edges(decoded, False)
    if (first != last or new_holes-old_holes+decoded.OutlineCount()-shape.OutlineCount() != bridge_count):
        raise native.Refused('native_bridge_contours_or_boundary_edges_changed')
    loss = shape.CloneDropTriangulation(); loss.BooleanSubtract(decoded)
    spill = decoded.CloneDropTriangulation(); spill.BooleanSubtract(shape)
    native._check_deadline(deadline)
    if loss.OutlineCount() or spill.OutlineCount():
        raise native.Refused('native_bridge_decoder_changed_copper')
    return decoded, dict(bridge_count=bridge_count, input_vertices=input_vertices,
        output_vertices=output_vertices, exact_native_boundary_edges_preserved=True,
        zero_native_loss=True, zero_native_spill=True, source_mutated=False,
        new_capacity_credited=False, release_authority=False)


def _boundary_containers(cycles, native_cycles, boundaries, deadline):
    """Exact integer broadphase only; native predicates decide every hit."""
    import pcbnew
    import cec_rectilinear_copper as native
    def bounds(points):
        return (min(p[0] for p in points),min(p[1] for p in points),
                max(p[0] for p in points),max(p[1] for p in points))
    def disjoint(a,b):
        # Strict separation ONLY: touching boxes still need native checks.
        return a[2]<b[0] or b[2]<a[0] or a[3]<b[1] or b[3]<a[1]
    boxes=[];edges=[]
    for points in cycles:
        native._check_deadline(deadline);boxes.append(bounds(points))
        edges.append([(a,b,bounds((a,b)))for a,b in zip(points,points[1:]+points[:1])])
    containers=[];counts=dict(disjoint_cycle_pairs=0,disjoint_edge_queries=0,
                             native_boundary_queries=0,native_containment_queries=0)
    for i,points in enumerate(cycles):
        parents=[]
        for j,poly in enumerate(native_cycles):
            native._check_deadline(deadline)
            if i==j:continue
            if disjoint(boxes[i],boxes[j]):
                counts['disjoint_cycle_pairs']+=1;continue
            for a,b,edge_box in edges[j]:
                native._check_deadline(deadline)
                if disjoint(boxes[i],edge_box):
                    counts['disjoint_edge_queries']+=1;continue
                counts['native_boundary_queries']+=1
                if boundaries[i].Collide(pcbnew.SEG(pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*b)),0):
                    raise native.Refused('touching_or_crossing_exact_native_boundaries')
            # Overlapping AABBs never establish containment.
            counts['native_containment_queries']+=1
            if poly.Contains(pcbnew.VECTOR2I(*points[0])):parents.append(j)
        if len(parents)>32:raise native.Refused('exact_native_boundary_depth_bound')
        containers.append(set(parents))
    return containers,counts


def decode_exact_hole_boundaries(shape, deadline, *, max_vertices=200000):
    """Unwrap paired bridges by literal integer edges, without Unfracture.

    KiCad's Unfracture can move boundary vertices of a saved linear fill.
    Here only exactly reverse-paired zero-width bridge edges are removed.
    Remaining directed edges must form disjoint simple native cycles. An
    exact native containment tree assigns their holes/islands. Cancelled
    bridges must be trees connecting real boundaries, not dangling folds.
    Independent native set subtraction still proves ZERO copper loss/spill.
    No snapping, buffering, fill replacement or current capacity is granted.
    """
    from collections import Counter
    import pcbnew
    import cec_rectilinear_copper as native
    if type(max_vertices) is not int or not 32 <= max_vertices <= 200000:
        raise native.Refused('invalid_exact_native_bridge_vertex_bound')
    boundary=Counter(); paired=set(); vertices=0; old_contours=0
    for i in range(shape.OutlineCount()):
        for ring in [shape.Outline(i),*[shape.Hole(i,j) for j in range(shape.HoleCount(i))]]:
            native._check_deadline(deadline);old_contours+=1;count=ring.PointCount();vertices+=count
            if ring.ArcCount() or count<3 or vertices>max_vertices:
                raise native.Refused('bounded_exact_native_bridge_ring_required')
            points=[(int(ring.CPoint(k).x),int(ring.CPoint(k).y)) for k in range(count)]
            if points[0]==points[-1]:points.pop()
            if any(abs(v)>2000000000 for point in points for v in point):
                raise native.Refused('exact_native_bridge_coordinate_bound')
            edges=Counter(zip(points,points[1:]+points[:1]))
            if any(a==b or n!=1 for (a,b),n in edges.items()):
                raise native.Refused('ambiguous_or_zero_exact_native_bridge_edge')
            for a,b in edges:
                native._check_deadline(deadline)
                if (b,a) in edges:paired.add(tuple(sorted((a,b))))
                else:boundary[a,b]+=1
    if not paired:raise native.Refused('actual_paired_exact_native_bridges_required')
    if any(n!=1 for n in boundary.values()):
        raise native.Refused('overlapping_exact_native_boundary_edge')
    outgoing={};incoming={}
    for a,b in boundary:
        native._check_deadline(deadline)
        if a in outgoing or b in incoming:
            raise native.Refused('ambiguous_exact_native_boundary_vertex')
        outgoing[a]=b;incoming[b]=a
    if outgoing.keys()!=incoming.keys():
        raise native.Refused('open_exact_native_boundary_cycle')
    remaining=set(outgoing);cycles=[];native_cycles=[];boundaries=[];exact_cycle_rechecks=[]
    while remaining:
        native._check_deadline(deadline)
        at=min(remaining);start=at;points=[]
        while True:
            native._check_deadline(deadline)
            if at not in remaining:raise native.Refused('revisited_exact_native_boundary_cycle')
            remaining.remove(at);points.append(at);at=outgoing[at]
            if at==start:break
        if len(points)<3 or not sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(points,points[1:]+points[:1])):
            raise native.Refused('nonpositive_exact_native_boundary_cycle')
        poly=native._poly(points)
        if poly.IsSelfIntersecting():
            # SEG::Collide(..., 0), used by KiCad 10.0.5's self-intersection
            # predicate, can report a crossing between strictly disjoint
            # nonadjacent edges around a one-native-unit edge. Do NOT move,
            # remove, snap or buffer that edge. Independently prove the
            # unchanged cycle with bounded integer orientation/intersection
            # predicates. A real crossing, touching boundary, reverse overlap
            # or exhausted proof remains a refusal. The literal directed-edge
            # inventory, containment tree and BOTH native set differences
            # below are still mandatory; this is not a native DRC exception.
            from cec_exact_outline_topology import require_one_polygon
            try:
                checked=require_one_polygon([[[list(p) for p in points]]],
                    deadline_monotonic=deadline)
            except ValueError as exc:
                raise native.Refused('self_intersecting_exact_native_boundary_cycle:'+str(exc)) from exc
            exact_cycle_rechecks.append(dict(cycle_index=len(cycles),
                native_predicate_reported_intersection=True,
                literal_cycle_sha256=native._digest(points),exact_integer_topology=checked))
        line=pcbnew.SHAPE_LINE_CHAIN()
        for x,y in [*points,points[0]]:line.Append(x,y)
        line.SetClosed(False)
        cycles.append(points);native_cycles.append(poly);boundaries.append(line)
        if len(cycles)>256:raise native.Refused('exact_native_boundary_cycle_bound')
    # A subdivided bridge remains ONE topological bridge. Count boundary
    # attachments in each cancelled-edge tree, not incidental segment count.
    bridge_graph={}
    for a,b in paired:
        bridge_graph.setdefault(a,set()).add(b);bridge_graph.setdefault(b,set()).add(a)
    unseen=set(bridge_graph);rank=0
    while unseen:
        native._check_deadline(deadline);component={min(unseen)};queue=list(component)
        while queue:
            native._check_deadline(deadline)
            peers=bridge_graph[queue.pop()]-component;component.update(peers);queue.extend(peers)
        unseen-=component;edge_count=sum(len(bridge_graph[p]) for p in component)//2
        attachments=component & outgoing.keys()
        if edge_count!=len(component)-1 or len(attachments)<2:
            raise native.Refused('native_bridge_must_be_boundary_attached_tree')
        rank+=len(attachments)-1
    if len(cycles)-old_contours!=rank:
        raise native.Refused('exact_native_bridge_contour_rank_changed')
    containers,broadphase=_boundary_containers(cycles,native_cycles,boundaries,deadline)
    parent=[]
    for i,ancestors in enumerate(containers):
        nearest=[j for j in ancestors if containers[j]==ancestors-{j}]
        if len(nearest)!=(1 if ancestors else 0):
            raise native.Refused('ambiguous_exact_native_boundary_nesting')
        parent.append(nearest[0] if nearest else None)
    decoded=pcbnew.SHAPE_POLY_SET();outer_ids={}
    for i,points in enumerate(cycles):
        native._check_deadline(deadline)
        if len(containers[i])%2:continue
        index=decoded.NewOutline();outer_ids[i]=index
        for x,y in points:decoded.Append(x,y,index,-1)
    for i,points in enumerate(cycles):
        native._check_deadline(deadline)
        if not len(containers[i])%2:continue
        index=outer_ids.get(parent[i])
        if index is None:raise native.Refused('exact_native_hole_owner_unavailable')
        hole=decoded.NewHole(index)
        for x,y in points:decoded.Append(x,y,index,hole)
    # A second literal inventory protects against construction/API errors.
    emitted=Counter()
    for i in range(decoded.OutlineCount()):
        for ring in [decoded.Outline(i),*[decoded.Hole(i,j) for j in range(decoded.HoleCount(i))]]:
            points=[(int(ring.CPoint(k).x),int(ring.CPoint(k).y)) for k in range(ring.PointCount())]
            emitted.update(zip(points,points[1:]+points[:1]))
    if emitted!=boundary:raise native.Refused('exact_native_boundary_edges_changed')
    loss=shape.CloneDropTriangulation();loss.BooleanSubtract(decoded)
    spill=decoded.CloneDropTriangulation();spill.BooleanSubtract(shape)
    native._check_deadline(deadline)
    if loss.OutlineCount() or spill.OutlineCount():
        raise native.Refused('exact_native_bridge_decoder_changed_copper')
    return decoded,dict(bridge_count=rank,paired_bridge_segments=len(paired),input_vertices=vertices,
        output_vertices=sum(map(len,cycles)),exact_native_boundary_edges_preserved=True,
        exact_native_directed_edges_preserved=True,native_containment_tree_received=True,
        exact_cycle_false_positive_rechecks=exact_cycle_rechecks,
        exact_integer_boundary_broadphase=broadphase,
        zero_native_loss=True,zero_native_spill=True,source_mutated=False,
        native_unfracture_used=False,new_capacity_credited=False,release_authority=False)
