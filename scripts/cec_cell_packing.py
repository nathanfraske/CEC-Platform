"""Bounded cooperative packing of rigid geometry and a future macro.

The caller supplies actual courtyard/copper envelopes and a reservation oracle.
No product, reference, net or coordinate policy lives in this search primitive.
Translations preserve the whole group's pitch, rotations and relative copper.
This proposes placement only; exact downstream electrical admission still owns
the generated board. A failed finite search is not proof the outline must grow.
"""
from __future__ import annotations

import math
from shapely.affinity import translate
from shapely.geometry import box
from shapely.ops import unary_union

MAX_TRANSLATION_TRIALS = 65


def pack_context_translations(groups, fixed, *, interferes, clearance=.15,
                              max_nodes=2048, sites_per_group=24,
                              timeout_s=10., accept_translation=None, group_order=None,
                              shape_contact_sites=False, max_shape_contacts=100000):
    """Pack complete rigid cells with an explicit physical collision model.

    Every member is a dictionary with a valid ``geometry`` polygon and caller
    facts. All geometry is already in ONE common coordinate frame. Thus a
    matched multi-board cell translates as one object without treating two
    opposing low-height bodies as same-face courtyards. ``interferes(a,b)``
    must return an explicit boolean for each pair; no context, mating or
    height exemption is inferred by this primitive. The caller must source
    those facts and perform native paired receiving afterwards.

    ``group_order`` optionally gives a complete explicit permutation. A caller
    can bring a measured blocked cell forward on a bounded replay instead of
    repeating an expensive successful prefix. It never omits a cell, reuses a
    partial admission, increases a budget or changes the collision model.

    Actual-polygon proposal work has a separate finite contact budget. Its
    exhaustion returns an incomplete search receipt, never a pipeline crash,
    placement admission or assertion that the board has no legal placement.

    Only collision-relevant members generate contact sites. Unknown contexts
    cannot be silently ignored by a permissive default. Neither input facts
    nor geometry are mutated. Exhaustion is not permission to grow a board.
    """
    import time
    if (not callable(interferes) or type(timeout_s) not in (int, float)
            or not math.isfinite(timeout_s) or not 0 < timeout_s <= 10
            or type(max_nodes) is not int or not 1 <= max_nodes <= 32768
            or type(sites_per_group) is not int or not 1 <= sites_per_group <= 256
            or type(clearance) not in (int, float) or not math.isfinite(clearance)
            or clearance < 0 or not isinstance(groups, dict) or len(groups) > 64):
        raise ValueError('bounded explicit context packing contract required')
    if type(shape_contact_sites) is not bool:
        raise ValueError('explicit_polygon_contact_proposal_policy_required')
    if type(max_shape_contacts) is not int or not 1<=max_shape_contacts<=1000000:
        raise ValueError('bounded_polygon_contact_work_required')
    if group_order is not None and (not isinstance(group_order,(list,tuple))
            or len(group_order)!=len(groups) or len(set(group_order))!=len(group_order)
            or set(group_order)!=set(groups)):
        raise ValueError('context group order must be a complete unique permutation')
    deadline = time.monotonic() + timeout_s
    class PackingDeadline(Exception):
        pass

    def tick():
        if time.monotonic() >= deadline:
            raise PackingDeadline()

    def deadline_result(nodes=0):
        return dict(ok=False, translations={}, nodes=nodes, exhausted=False,
                    timed_out=True, reason='bounded_context_packing_deadline',
                    admission_authority=False)

    fixed = list(fixed)
    # A whole-board native inventory may have thousands of per-layer shapes
    # that cannot reach any member in this bounded translation domain. Retain
    # the SAME local search bound, but first reject only provably disjoint
    # swept bounding boxes. No role/layer exemption or collision waiver is
    # inferred, and invalid distant geometry still refuses during validation.
    if len(fixed) + sum(len(row['members']) for row in groups.values()) > 4096:
        from cec_translation_context_window import relevant_fixed
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return deadline_result()
        try:
            fixed, _ = relevant_fixed(groups, fixed, clearance=clearance,
                                      timeout_s=min(10., remaining))
        except ValueError as exc:
            if str(exc) == 'translation_context_window_deadline':
                return deadline_result()
            raise
    members = fixed + [m for row in groups.values() for m in row['members']]
    if len(members) > 4096:
        raise ValueError('context packing member inventory bound')
    for member in members:
        if (not isinstance(member, dict) or 'geometry' not in member
                or member['geometry'].is_empty or not member['geometry'].is_valid
                or member['geometry'].geom_type not in ('Polygon','MultiPolygon')
                or member['geometry'].area <= 0
                or not all(math.isfinite(v) for v in member['geometry'].bounds)):
            raise ValueError('valid complete context member geometry required')
    for row in groups.values():
        bounds = tuple(row['bounds'])
        preferred = tuple(row.get('preferred', (0., 0.)))
        sites = row.get('sites', ())
        if (not row['members'] or len(bounds) != 4 or len(preferred) != 2
                or not all(math.isfinite(v) for v in (*bounds, *preferred))
                or bounds[0] > bounds[2] or bounds[1] > bounds[3]
                or len(sites) > 256 or any(len(p) != 2
                    or not all(math.isfinite(v) for v in p) for p in sites)):
            raise ValueError('finite ordered context translation domain required')

    # Cache exact polygon bounds in private copies. Native pad/barrel contexts
    # contain many small per-layer shapes; recomputing Shapely bounds and
    # DE-9IM for thousands of distant pairs consumed the bounded search before
    # it reached the difficult cell. This is broad-phase rejection only: every
    # possibly colliding pair still consumes the explicit oracle and exact
    # polygon/clearance test. No caller fact or geometry is modified.
    def bounded_member(member):
        return dict(member,_context_bounds=tuple(member['geometry'].bounds))
    fixed=[bounded_member(member) for member in fixed]
    groups={key:dict(row,members=[bounded_member(m) for m in row['members']])
            for key,row in groups.items()}

    def required(a, b):
        tick()
        result = interferes(a, b)
        tick()
        if type(result) is not bool:
            raise ValueError('context collision model must return explicit bool')
        return result

    def conflicts(a, b):
        if not required(a, b):
            return False
        ax0,ay0,ax1,ay1=a['_context_bounds'];bx0,by0,bx1,by1=b['_context_bounds']
        if (ax1+clearance<bx0 or bx1+clearance<ax0
                or ay1+clearance<by0 or by1+clearance<ay0):
            return False
        ga, gb = a['geometry'], b['geometry']
        # Native courtyards may share an edge. At zero extra clearance, only
        # intersecting INTERIORS block a proposal; downstream native receiving
        # still decides the exact package/electrical rules.
        return ga.relate_pattern(gb, 'T********') or ga.distance(gb) < clearance - 1e-7

    # Internal conflicts cannot be repaired by a rigid-cell translation.
    try:
        for key,row in groups.items():
            local = row['members']
            for i, member in enumerate(local):
                for j,other in enumerate(local[i+1:],i+1):
                    if conflicts(member, other):
                        return dict(ok=False, translations={}, nodes=0,
                            exhausted=False, timed_out=False,
                            reason='rigid_context_cell_internal_collision',
                            group_key=key,member_indices=[i,j],
                            admission_authority=False)
    except PackingDeadline:
        return deadline_result()
    ordered = list(group_order) if group_order is not None else sorted(groups, key=lambda k: (
        (groups[k]['bounds'][2]-groups[k]['bounds'][0]) *
        (groups[k]['bounds'][3]-groups[k]['bounds'][1]), k))
    nodes = 0
    timed_out = False
    refused_by_group = {}
    blocker_samples = []
    best_prefix = {}
    blocked_group = None
    shape_site_counts = {}

    class ShapeBudget(Exception):
        pass
    class ShapeWork:
        contacts=0
        def tick(self):tick()
        def contact(self):
            tick()
            if self.contacts>=max_shape_contacts:
                raise ShapeBudget()
            self.contacts+=1
    shape_work=ShapeWork()

    def shape_sites(row,occupied,preferred):
        """Member bboxes expanded against ACTUAL relevant obstacle polygons.

        Member bboxes are conservative. Obstacles keep their real diagonals,
        concavities and holes. Every returned site still uses conflicts() and
        the caller's feasibility predicate; there is no admission exemption.
        """
        from shapely import affinity
        from shapely.geometry import Point,Polygon
        from shapely.ops import nearest_points
        from cec_translation_geometry import rectangular_sweep
        dx0,dy0,dx1,dy1=row['bounds']
        # Degenerate domains retain the existing one-dimensional event tier.
        if dx0==dx1 or dy0==dy1:return []
        domain=box(dx0,dy0,dx1,dy1);fences=[];tick()
        for member in row['members']:
            x0,y0,x1,y1=member['_context_bounds']
            cx,cy=(x0+x1)/2,(y0+y1)/2
            region=box(x0+dx0-.000002,y0+dy0-.000002,
                       x1+dx1+.000002,y1+dy1+.000002)
            relevant=[]
            for other in occupied:
                tick()
                if not required(member,other):continue
                ox0,oy0,ox1,oy1=other['_context_bounds']
                if (ox1+clearance<region.bounds[0] or ox0-clearance>region.bounds[2]
                        or oy1+clearance<region.bounds[1] or oy0-clearance>region.bounds[3]):continue
                clipped=other['geometry'].buffer(clearance+.000002,join_style=2).intersection(region)
                if not clipped.is_empty:relevant.append(clipped)
            if relevant:
                merged=unary_union(relevant);tick()
                fence=rectangular_sweep(merged,(x1-x0)/2,(y1-y0)/2,shape_work)
                fences.append(affinity.translate(fence,xoff=-cx,yoff=-cy))
        free=domain.difference(unary_union(fences)) if fences else domain
        tick();pieces=[free] if free.geom_type=='Polygon' else getattr(free,'geoms',())
        choices=set();origin=Point(*preferred)
        for piece in pieces:
            tick()
            if not isinstance(piece,Polygon) or piece.is_empty:continue
            inner=piece.buffer(-.000002)
            sub=[inner] if inner.geom_type=='Polygon' else getattr(inner,'geoms',())
            for poly in sub:
                tick()
                if poly.geom_type!='Polygon' or poly.is_empty:continue
                near=nearest_points(origin,poly)[1];middle=poly.representative_point()
                choices.update(((near.x,near.y),(middle.x,middle.y)))
                for ring in (poly.exterior,*poly.interiors):
                    for point in ring.coords[:-1]:
                        shape_work.contact();choices.add(tuple(point))
        return sorted(choices,key=lambda p:(math.dist(p,preferred),p))[:sites_per_group]

    def visit(index, occupied, poses):
        nonlocal nodes, timed_out, best_prefix, blocked_group
        if len(poses) >= len(best_prefix):
            best_prefix = dict(poses)
            blocked_group = ordered[index] if index < len(ordered) else None
        if time.monotonic() >= deadline:
            timed_out = True
            return None
        if index == len(ordered):
            return poses
        if nodes >= max_nodes:
            return None
        key = ordered[index]
        row = groups[key]
        preferred = tuple(row.get('preferred', (0., 0.)))
        def candidates():
            # Test the cheap preferred pose before building contact domains.
            # Generate the actual-polygon fallback only after all earlier
            # sites have failed (including downstream cooperative cells).
            # A successful prefix alone never bypasses the complete search.
            yield preferred
            per_member = max(1, sites_per_group // len(row['members']))
            for member in row['members']:
                if nodes >= max_nodes:
                    return
                tick()
                # Layer/body contexts stay separate in proposal geometry.
                obstacles = [m['_context_bounds'] for m in occupied
                             if required(member, m)]
                yield from contact_translation_sites([member['_context_bounds']],
                    bounds=row['bounds'], obstacles=obstacles, clearance=clearance,
                    max_sites=per_member, preferred_origin=preferred)
            yield from sorted((tuple(p) for p in row.get('sites', ())),
                              key=lambda p: (math.dist(p, preferred), p))
            if shape_contact_sites and nodes < max_nodes:
                tick()
                extra=shape_sites(row,occupied,preferred)
                shape_site_counts[key]=shape_site_counts.get(key,0)+len(extra)
                yield from extra
        seen = set()
        for delta in candidates():
            if delta in seen:
                continue
            if time.monotonic() >= deadline:
                timed_out = True
                return None
            if nodes >= max_nodes:
                return None
            seen.add(delta)
            nodes += 1
            x, y = delta
            x0, y0, x1, y1 = row['bounds']
            if not (x0 <= x <= x1 and y0 <= y <= y1):
                continue
            posed = [dict(m, geometry=translate(m['geometry'], x, y),
                          _context_bounds=(m['_context_bounds'][0]+x,m['_context_bounds'][1]+y,
                                           m['_context_bounds'][2]+x,m['_context_bounds'][3]+y))
                     for m in row['members']]
            blocked = next(((i,b) for i,a in enumerate(posed) for b in occupied
                            if conflicts(a,b)),None)
            if blocked is not None:
                refused_by_group[key] = refused_by_group.get(key,0)+1
                if len(blocker_samples)<16:
                    i,other=blocked
                    blocker_samples.append(dict(group_key=key,member_index=i,
                        translation_mm=list(delta),
                        posed_member_bounds_mm=list(posed[i]['_context_bounds']),
                        obstacle_bounds_mm=list(other['_context_bounds']),
                        member_facts={k:v for k,v in posed[i].items() if k not in ('geometry','_context_bounds')},
                        obstacle_facts={k:v for k,v in other.items() if k not in ('geometry','_context_bounds')}))
                continue
            if accept_translation is not None:
                accepted = accept_translation(key, (x, y))
                if type(accepted) is not bool:
                    raise ValueError('context translation oracle must return explicit bool')
                if not accepted:
                    continue
            answer = visit(index+1, occupied+posed, {**poses, key: list(delta)})
            if answer is not None:
                return answer
        return None

    try:
        poses = visit(0, fixed, {})
    except ShapeBudget:
        return dict(ok=False,translations={},nodes=nodes,exhausted=True,
            timed_out=False,reason='bounded_context_polygon_work_exhausted',
            geometry_work_contacts=shape_work.contacts,geometry_work_limit=max_shape_contacts,
            physical_feasibility='not_determined',refused_by_group=refused_by_group,
            blocker_samples=blocker_samples,furthest_proposed_prefix=best_prefix,
            blocked_group=blocked_group,partial_prefix_is_not_admitted=True,
            polygon_contact_proposals=shape_site_counts,admission_authority=False)
    except PackingDeadline:
        result = deadline_result(nodes)
        result.update(refused_by_group=refused_by_group,blocker_samples=blocker_samples,
            furthest_proposed_prefix=best_prefix,blocked_group=blocked_group,
            partial_prefix_is_not_admitted=True)
        if shape_contact_sites:
            result.update(polygon_contact_proposals=shape_site_counts,
                geometry_work_contacts=shape_work.contacts,geometry_work_limit=max_shape_contacts)
        return result
    result=dict(ok=poses is not None, translations=poses or {}, nodes=nodes,
                exhausted=nodes >= max_nodes, timed_out=timed_out,
                reason=None if poses is not None else
                    'bounded_context_packing_deadline' if timed_out else 'bounded_context_packing_refused',
                refused_by_group=refused_by_group,blocker_samples=blocker_samples,
                furthest_proposed_prefix=best_prefix if poses is None else {},
                blocked_group=blocked_group if poses is None else None,
                partial_prefix_is_not_admitted=True,
                admission_authority=False)
    if shape_contact_sites:
        result.update(polygon_contact_proposals=shape_site_counts,
            geometry_work_contacts=shape_work.contacts,geometry_work_limit=max_shape_contacts)
    return result


def pack_translations(groups, fixed, *, clearance=.15, max_nodes=2048,
                      sites_per_group=24, accept_translation=None):
    """Bounded cooperative translation of caller-declared rigid cells.

    Each group supplies member polygons, translation bounds and a preferred
    translation. Bounds encode edge seating and electrical reach limits.
    This is a proposal only: exact native DRC and electrical admission follow.
    No board/refdes exceptions, rotations or outline growth are inferred here.
    Optional bounded extra sites and an independent read-only translation
    oracle let native copper participate without turning other-layer copper
    into a blanket body keepout. A refused site is not an unroutability proof.
    """
    from shapely import affinity
    if (any(type(v) is not int or v < 1 for v in (max_nodes, sites_per_group))
            or not math.isfinite(clearance) or clearance < 0):
        raise ValueError('finite clearance and positive search budgets required')
    fixed = list(fixed)
    if any(g.is_empty or not g.is_valid for g in fixed):
        raise ValueError('valid fixed geometry required')
    for row in groups.values():
        bounds = tuple(row['bounds'])
        preferred = tuple(row.get('preferred', (0., 0.)))
        if (len(bounds) != 4 or len(preferred) != 2
                or not all(math.isfinite(v) for v in (*bounds, *preferred))
                or bounds[0] > bounds[2] or bounds[1] > bounds[3]):
            raise ValueError('finite ordered translation bounds and preferred point required')
        sites=row.get('sites',())
        if (len(sites)>256 or any(len(p)!=2 or not all(math.isfinite(v) for v in p)
                                 for p in sites)):
            raise ValueError('bounded finite supplemental translation sites required')
    ordered = sorted(groups, key=lambda k: (
        (groups[k]['bounds'][2]-groups[k]['bounds'][0]) *
        (groups[k]['bounds'][3]-groups[k]['bounds'][1]), k))
    for key in ordered:
        row=groups[key]
        if not row['members'] or any(g.is_empty or not g.is_valid for g in row['members']):
            raise ValueError('valid complete member geometry required')
    nodes=0
    def visit(index, occupied, poses):
        nonlocal nodes
        if index==len(ordered):return poses
        if nodes>=max_nodes:return None
        key=ordered[index];row=groups[key]
        preferred=tuple(row.get('preferred',(0.,0.)))
        candidates=[preferred]+contact_translation_sites(
            [g.bounds for g in row['members']],bounds=row['bounds'],
            obstacles=[g.bounds for g in occupied],clearance=clearance,
            max_sites=sites_per_group,preferred_origin=preferred)
        candidates+=sorted((tuple(p) for p in row.get('sites',())),
                           key=lambda p:(math.dist(p,preferred),p))
        seen=set()
        for delta in candidates:
            if delta in seen:continue
            if nodes >= max_nodes:return None
            seen.add(delta);nodes+=1
            x,y=delta;x0,y0,x1,y1=row['bounds']
            if not (x0<=x<=x1 and y0<=y<=y1):continue
            posed=[affinity.translate(g,x,y) for g in row['members']]
            if any(a.intersects(b) or a.distance(b)<clearance-1e-7
                   for a in posed for b in occupied):continue
            if accept_translation is not None:
                accepted=accept_translation(key,(x,y))
                if type(accepted) is not bool:
                    raise ValueError('independent translation oracle must return explicit bool')
                if not accepted:continue
            answer=visit(index+1,occupied+posed,{**poses,key:list(delta)})
            if answer is not None:return answer
        return None
    poses=visit(0,list(fixed),{})
    return dict(ok=poses is not None,translations=poses or {},nodes=nodes,
                exhausted=nodes>=max_nodes,admission_authority=False)


def bounded_translation_product(menus, *, max_combinations=4096):
    """Deterministic finite Cartesian search ordered by displacement cost.

    Small domains retain exhaustive Cartesian order. Large domains use a
    best-first index frontier, bounded in both output and queue growth, rather
    than discarding a cut because it has one more independent owner. This is
    search coverage only, never proof of placement or routing feasibility.
    """
    import heapq
    import itertools
    if not isinstance(max_combinations, int) or max_combinations < 1:
        raise ValueError('positive integer combination budget required')
    menus = tuple(tuple(tuple(map(float, choice)) for choice in menu)
                  for menu in menus)
    if any(len(choice) != 2 or not all(math.isfinite(v) for v in choice)
           for menu in menus for choice in menu):
        raise ValueError('finite two-dimensional translations required')
    if not menus or any(not menu for menu in menus):
        return
    if math.prod(len(menu) for menu in menus) <= max_combinations:
        yield from itertools.product(*menus)
        return
    menus = tuple(tuple(sorted(set(menu), key=lambda c:
                  (math.hypot(*c), abs(c[0])+abs(c[1]), c))) for menu in menus)

    def rank(indices):
        distances = [math.hypot(*menus[n][i]) for n, i in enumerate(indices)]
        return (max(distances), sum(distances), indices)

    start = (0,) * len(menus)
    queue = [rank(start)]
    seen = {start}
    for _ in range(max_combinations):
        if not queue:
            break
        _maximum, _total, indices = heapq.heappop(queue)
        yield tuple(menus[n][i] for n, i in enumerate(indices))
        for n in range(len(menus)):
            if indices[n]+1 >= len(menus[n]):
                continue
            neighbor = indices[:n] + (indices[n]+1,) + indices[n+1:]
            if neighbor not in seen:
                seen.add(neighbor)
                heapq.heappush(queue, rank(neighbor))


def essential_subgroup(owner, offsets, required_members):
    """Drop optional followers, never required electrical members of a macro."""
    refs = {owner, *required_members}
    missing = refs - set(offsets)
    if missing:
        raise ValueError("essential macro members missing: %s" % ", ".join(sorted(missing)))
    return {ref: offsets[ref] for ref in sorted(refs)}


def project_copper_obstacles(regions, component_layers):
    """Do not turn opposite-layer copper into a same-face body keepout.

    Untagged mechanical/cell obstacles and unknown/through-hole layer coverage
    always survive. Tags name the copper layer, not a board or net. This only
    projects placement obstacles: it never authorizes a via, track crossing,
    thermal result, or a missing signal-reference plane.
    """
    layers = set(component_layers or ())
    if not layers or "*" in layers:
        return list(regions)
    return [r for r in regions if not str(r[0]).startswith("copper-layer:")
            or str(r[0]).split(":", 1)[1] in layers
            or not str(r[0]).split(":", 1)[1].endswith(".Cu")]


def contact_translation_sites(parts, *, bounds, obstacles=(), clearance=0.3,
                              max_sites=256, max_exclusions=4096,
                              preferred_origin=None, reach_discs=(),
                              translation_halfplanes=(), member_obstacles=None):
    """Bounded sites in the legal translation space of a rectangular macro.

    Parts/obstacles are (xmin, ymin, xmax, ymax), with parts relative to the
    macro origin. Bounds constrain that origin, not the macro's outer box.
    Subtract Minkowski-expanded obstacles for every member, so a satellite
    cannot be omitted when reserving a cavity. This is a fallback to a coarse
    lattice, not an exhaustive packing or electrical-routing proof.

    Optional ``member_obstacles`` supplies one additional obstacle collection
    per member. Global obstacles still constrain EVERY member. This represents
    caller-proved context differences without incorrectly applying an owner's
    exemption to a satellite, or forbidding that owner's legitimate endpoint.
    """
    from shapely.geometry import Point, Polygon
    from cec_translation_halfplanes import normalized, clip_rectangle
    planes = normalized(translation_halfplanes)
    parts, obstacles = tuple(parts), tuple(obstacles)
    if member_obstacles is None:
        member_obstacles = tuple(() for _ in parts)
    else:
        member_obstacles = tuple(tuple(items) for items in member_obstacles)
        if len(member_obstacles) != len(parts):
            raise ValueError('one obstacle collection per translation member required')
    rectangles = (bounds, *parts, *obstacles,
                  *(r for items in member_obstacles for r in items))
    if any(len(r) != 4 or not all(math.isfinite(float(v)) for v in r)
           or r[2] < r[0] or r[3] < r[1] for r in rectangles):
        raise ValueError("translation rectangles must be finite and ordered")
    if not math.isfinite(clearance) or clearance < 0:
        raise ValueError("translation clearance must be finite and nonnegative")
    if preferred_origin is not None and (
            len(preferred_origin) != 2 or not all(math.isfinite(float(v))
                                                for v in preferred_origin)):
        raise ValueError("preferred origin must be finite")
    if not parts:
        return []
    if len(parts) * len(obstacles) + sum(map(len, member_obstacles)) > max_exclusions:
        return []  # bounded refusal; no obstacle is dropped to make room
    pairs = [(part, obstacle) for part in parts for obstacle in obstacles]
    pairs.extend((part, obstacle) for part, items in zip(parts, member_obstacles)
                 for obstacle in items)
    if bounds[0] == bounds[2] or bounds[1] == bounds[3]:
        # A connector bank may slide along ONE edge. Such domains have zero
        # area but are not empty. Generate boundary events on that segment,
        # retaining every caller constraint instead of inventing board growth.
        pad=clearance+1e-6
        xs={bounds[0],bounds[2]};ys={bounds[1],bounds[3]}
        if preferred_origin:
            xs.add(preferred_origin[0]);ys.add(preferred_origin[1])
        if bounds[0]!=bounds[2]:
            for p, o in pairs:xs.update((o[0]-pad-p[2],o[2]+pad-p[0]))
        if bounds[1]!=bounds[3]:
            for p, o in pairs:ys.update((o[1]-pad-p[3],o[3]+pad-p[1]))
        origin=preferred_origin or (bounds[0],bounds[1])
        candidates=[]
        for x in xs:
            for y in ys:
                if not (bounds[0]<=x<=bounds[2] and bounds[1]<=y<=bounds[3]):continue
                if any(a*x+b*y<c-1e-8 for a,b,c in planes):continue
                # Boundary events on vertically/horizontally irrelevant
                # obstacles used to consume the whole 1-D shortlist before
                # the nearest actually free contact. Screen complete native
                # member rectangles BEFORE truncation, just as the 2-D
                # Minkowski-difference domain does. This is conservative
                # proposal geometry, not a waiver of exact downstream gates.
                if any(x+p[0]<o[2]+pad-1e-10 and x+p[2]>o[0]-pad+1e-10
                       and y+p[1]<o[3]+pad-1e-10 and y+p[3]>o[1]-pad+1e-10
                       for p, o in pairs):continue
                # Existing reach-disc contract is handled by the regular
                # domain implementation; refuse rather than drop it here.
                if reach_discs:continue
                candidates.append((x,y))
        return sorted(candidates,key=lambda p:(math.dist(p,origin),p))[:max_sites]
    domain = box(*bounds)
    if planes:
        vertices = clip_rectangle(bounds, planes)
        if len(vertices) < 3:
            return []
        domain = Polygon(vertices)
    for centre, radius in reach_discs:
        if (len(centre) != 2 or not all(math.isfinite(float(v)) for v in centre)
                or not math.isfinite(float(radius)) or float(radius) <= 0):
            raise ValueError('reach discs require finite centres and positive radii')
        # Inscribed approximation only narrows proposal space. Callers still
        # measure exact native terminal distances before any admission.
        domain = domain.intersection(Point(*centre).buffer(float(radius), quad_segs=32))
    if domain.is_empty:
        return []
    forbidden = []
    pad = clearance + 1e-6  # conservative guard against round-off at contacts
    for (px0, py0, px1, py1), (ox0, oy0, ox1, oy1) in pairs:
        expanded = box(ox0-px1-pad, oy0-py1-pad,
                       ox1-px0+pad, oy1-py0+pad)
        if expanded.intersects(domain):
            forbidden.append(expanded)
    free = domain.difference(unary_union(forbidden)) if forbidden else domain
    regions = [free] if isinstance(free, Polygon) else list(getattr(free, "geoms", ()))
    regions = sorted((r for r in regions if isinstance(r, Polygon) and r.area > 1e-12),
                     key=lambda r: (-r.area, r.bounds))
    sites, seen = [], set()
    limit = min(256, max(1, int(max_sites)))
    # Visit each cavity before adding its corners; a large polygon must not
    # consume the whole budget before disconnected narrow cavities are tried.
    choices = [(r.representative_point().x, r.representative_point().y) for r in regions]
    choices += [tuple(p) for r in regions for p in r.exterior.coords[:-1]]
    choices += [tuple(p) for r in regions for ring in r.interiors
                for p in ring.coords[:-1]]
    if preferred_origin is not None:
        from shapely.geometry import Point
        from shapely.ops import nearest_points
        preferred = Point(*preferred_origin)
        # An occupied component is usually a hole in a large free polygon,
        # not its exterior. Include those contacts and the exact closest free
        # point before truncation; otherwise goal-directed local packing can
        # sample the outer board edge while missing the desired package edge.
        choices += [(p.x, p.y) for r in regions
                    for p in [nearest_points(preferred, r)[1]]]
        choices.sort(key=lambda p: (math.dist(p, preferred_origin), p))
    for x, y in choices:
        key = (round(x, 9), round(y, 9))
        if key not in seen:
            seen.add(key)
            sites.append((float(x), float(y)))
            if len(sites) >= limit:
                break
    return sites


def negotiate_translation(envelope, *, bounds, fixed=(), axis,
                          reserve, clearance=0.3, step_mm=1.0,
                          max_trials=MAX_TRANSLATION_TRIALS):
    """Find the nearest legal group translation with a future macro seat.

    ``reserve((dx, dy), moved_envelope)`` returns a reservation or None. It is
    called only for contained, obstacle-clear geometry; every attempted group
    seat consumes budget, even if physically refused. Search order is stable.
    ``bounds`` uses ordinary (xmin, ymin, xmax, ymax) Cartesian box ordering.
    """
    if axis not in (0, 1):
        raise ValueError("translation axis must be 0 or 1")
    if not math.isfinite(step_mm) or step_mm <= 0:
        raise ValueError("translation step must be finite and positive")
    if not math.isfinite(clearance) or clearance < 0:
        raise ValueError("clearance must be finite and nonnegative")
    if len(bounds) != 4 or not all(math.isfinite(float(v)) for v in bounds):
        raise ValueError("bounds must be finite")
    if bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
        raise ValueError("bounds must have positive area")
    if envelope.is_empty or not envelope.is_valid:
        raise ValueError("rigid envelope must be nonempty and valid")
    fixed = tuple(fixed)
    if any(shape.is_empty or not shape.is_valid for shape in fixed):
        raise ValueError("fixed envelopes must be nonempty and valid")
    obstacle = unary_union(fixed) if fixed else None
    limit = min(MAX_TRANSLATION_TRIALS, max(1, int(max_trials)))
    region = box(*bounds)
    report = {"schema": 1, "ok": False, "applied": False,
              "axis": axis, "step_mm": step_mm, "budget": limit,
              "trials": 0, "reservation_probes": 0,
              "rejections": {"bounds": 0, "fixed_obstacle": 0,
                             "reservation": 0},
              "original_bounds": list(envelope.bounds),
              "reason": "bounded_search_exhausted"}
    for index in range(limit):
        amount = 0.0 if index == 0 else (
            (-1.0 if index % 2 else 1.0) * ((index + 1) // 2) * step_mm)
        delta = (amount, 0.0) if axis == 0 else (0.0, amount)
        moved = translate(envelope, xoff=delta[0], yoff=delta[1])
        report["trials"] += 1
        if not region.covers(moved):
            report["rejections"]["bounds"] += 1
            continue
        if obstacle is not None and (
                moved.intersects(obstacle)
                or moved.distance(obstacle) < clearance - 1e-7):
            report["rejections"]["fixed_obstacle"] += 1
            continue
        report["reservation_probes"] += 1
        reservation = reserve(delta, moved)
        if reservation is None:
            report["rejections"]["reservation"] += 1
            continue
        report.update(ok=True, applied=index != 0, translation_mm=list(delta),
                      selected_bounds=list(moved.bounds), reservation=reservation,
                      reason="reserved" if index else "existing_group_has_room")
        return report
    return report


def rigid_envelope(*, courtyard_boxes=(), tracks=(), vias=()):
    """Union courtyards and actual-width copper (including rounded endcaps).

    Input boxes use xmin/ymin/xmax/ymax; tracks use start_mm/end_mm/width_mm,
    vias use at_mm/dia_mm. Copper is conservatively projected across layers:
    this floorplanner does not grant routing-layer crossings or net exemptions.
    """
    from shapely.geometry import LineString, Point
    shapes = [box(*b) for b in courtyard_boxes]
    for row in tracks:
        width = float(row["width_mm"])
        if not math.isfinite(width) or width <= 0:
            raise ValueError("copper width must be finite and positive")
        # GEOS' circumscribed buffer avoids understating round copper at the
        # polygon approximation's vertices. The <0.13% excess is conservative.
        radius = width / 2.0 / math.cos(math.pi / 64.0)
        shapes.append(LineString((row["start_mm"], row["end_mm"])).buffer(radius))
    for row in vias:
        diameter = float(row["dia_mm"])
        if not math.isfinite(diameter) or diameter <= 0:
            raise ValueError("via diameter must be finite and positive")
        shapes.append(Point(row["at_mm"]).buffer(
            diameter / 2.0 / math.cos(math.pi / 64.0)))
    result = unary_union(shapes)
    if result.is_empty or not result.is_valid:
        raise ValueError("cell has no valid physical envelope")
    return result
