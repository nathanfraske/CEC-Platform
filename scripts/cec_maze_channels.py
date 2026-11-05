"""Bounded obstacle-derived channel axes for an otherwise coarse route grid."""
from __future__ import annotations

import math


def checked_centerline_boxes(boxes):
    """Bounded caller-side contact exclusions, used as hints, never waivers.

    These boxes already include their OWN trace-radius/contact margin. Mixing
    them with foreign copper using one electrical-clearance inflation can erase
    a real narrow channel between a same-net pickup and a foreign pin.
    Exact native/contact predicates still decide every proposed route.
    """
    if (type(boxes) not in (tuple,list) or len(boxes)>64
            or any(type(b) not in (tuple,list) or len(b)!=4
                or any(type(v) not in (int,float) or not math.isfinite(v)
                    or abs(v)>2_000_000_000 for v in b)
                or b[0]>=b[2] or b[1]>=b[3] for b in boxes)):
        raise ValueError('bounded_centerline_contact_boxes_required')
    return tuple(tuple(b) for b in boxes)


def mixed_centerline_boxes(native_boxes, extra_boxes, *, inflation, target):
    """Normalize differing margins for finite gap-axis proposals only."""
    extra=checked_centerline_boxes(extra_boxes)
    if (not math.isfinite(inflation) or inflation<0 or len(native_boxes)>256
            or len(target)!=2 or not all(math.isfinite(v) for v in target)):
        raise ValueError('bounded_mixed_channel_geometry_required')
    native=[(b[0]-inflation,b[1]-inflation,b[2]+inflation,b[3]+inflation)
        for b in native_boxes]
    rank=lambda b:(((b[0]+b[2])/2-target[0])**2+
        ((b[1]+b[3])/2-target[1])**2,b)
    # Reserve the explicit contact hints instead of silently truncating them
    # behind a dense foreign pin field. The combined O(n^2) gap work stays
    # within the pre-existing 256-box limit.
    return sorted(set(native),key=rank)[:256-len(extra)]+list(extra)


def octilinear_neighbors(xs, ys, ix, iy):
    """Nearest exact 0/45/90 neighbours on a nonuniform Cartesian lattice.

    Adjacent *indices* are not necessarily a 45-degree neighbour when pad,
    obstacle and escape axes subdivide different coordinates. Intersect the
    positive coordinate distances in each diagonal quadrant instead. A hop
    may cross intermediate axes, but the caller must check its entire copper
    segment; this helper grants no obstacle or fabrication exemption.
    """
    directions = ((1, 0), (-1, 0), (0, 1), (0, -1),
                  (1, 1), (1, -1), (-1, 1), (-1, -1))
    for direction, (dx, dy) in enumerate(directions):
        nx, ny = ix + dx, iy + dy
        while 0 <= nx < len(xs) and 0 <= ny < len(ys):
            if not dx or not dy:
                yield direction, nx, ny
                break
            delta_x, delta_y = abs(xs[nx] - xs[ix]), abs(ys[ny] - ys[iy])
            if delta_x == delta_y:
                yield direction, nx, ny
                break
            if delta_x < delta_y:
                nx += dx
            else:
                ny += dy


def gap_axes(boxes, bounds, *, inflation, target, max_axes=8, center_bounds=None,
             minimum_span=0, minimum_axis_separation=0):
    """Sample the midpoint of real narrow gaps, not arbitrary finer grids.

    Coordinates share the caller's units. AABBs propose axes only; the native
    router must still check the complete shapes, edge clearance and every hop.
    Projections must overlap on the other axis, avoiding spurious far-away gaps.
    """
    if (inflation < 0 or max_axes < 1 or len(boxes) > 256
            or minimum_span < 0 or minimum_axis_separation < 0):
        raise ValueError('invalid or unbounded channel search')
    if not all(math.isfinite(float(v)) for v in
               (*bounds, inflation, minimum_span, minimum_axis_separation,
                *target, *(v for b in boxes for v in b))):
        raise ValueError('finite channel geometry required')
    results = []
    for axis in (0, 1):
        other = 1 - axis
        candidates = {}
        def offer(lo, hi):
            if lo >= hi or hi-lo < minimum_span:
                return
            mid = round((lo + hi) / 2)
            if bounds[axis] <= mid <= bounds[axis+2]:
                rank = (hi-lo, abs(mid-target[axis]), mid)
                candidates[mid] = min(candidates.get(mid, rank), rank)
        for i, a in enumerate(boxes):
            if center_bounds is not None:
                offer(center_bounds[axis], a[axis] - inflation)
                offer(a[axis+2] + inflation, center_bounds[axis+2])
            for b in boxes[i+1:]:
                # Copper clearance expands the collision projections too.
                # Staggered vias can create a real throat even when their
                # bare lands do not overlap in the perpendicular direction.
                if max(a[other]-inflation, b[other]-inflation) > min(
                        a[other+2]+inflation, b[other+2]+inflation):
                    continue
                left, right = (a, b) if a[axis] < b[axis] else (b, a)
                lo, hi = left[axis+2] + inflation, right[axis] - inflation
                offer(lo, hi)
        selected=[]
        for candidate in sorted(candidates, key=candidates.get):
            # Native rounding can produce several equivalent one-nanometre
            # slots around a single land. Do not let those aliases consume a
            # finite proposal menu before other real channels. Optional and
            # proposal-only: the legacy lattice/guards are never removed.
            if any(abs(candidate-prior)<minimum_axis_separation for prior in selected):
                continue
            selected.append(candidate)
            if len(selected)>=max_axes:break
        results.append(selected)
    return results


def native_obstacle_boxes(board, layer, exempt_codes, bounds, target, *, limit=256):
    """Bounded layer-aware proposals from pads AND routed track/via copper.

    Native boxes are only axis hints. Curved/rotated shapes, local clearance
    rules, zones and future power ownership remain exact caller-side guards.
    Same-net and other-layer surface copper cannot manufacture a false gap.
    """
    if type(limit) is not int or not 1 <= limit <= 256:
        raise ValueError('obstacle proposal limit must be 1..256')
    if not all(math.isfinite(float(v)) for v in (*bounds, *target)):
        raise ValueError('finite obstacle window required')
    rows = set()
    items = (p for fp in board.GetFootprints() for p in fp.Pads())
    def offer(item):
        if item.GetNetCode() in exempt_codes or not item.IsOnLayer(layer):
            return
        box = item.GetBoundingBox()
        row = (box.GetLeft(), box.GetTop(), box.GetRight(), box.GetBottom())
        if (row[2] >= bounds[0] and row[0] <= bounds[2]
                and row[3] >= bounds[1] and row[1] <= bounds[3]):
            rows.add(row)
    for item in items:
        offer(item)
    for item in board.GetTracks():
        offer(item)
    return sorted(rows, key=lambda r: (
        ((r[0]+r[2])/2-target[0])**2 + ((r[1]+r[3])/2-target[1])**2, r))[:limit]


def orthogonal_channel_paths(start, end, boxes, bounds, *, inflation, max_axes=8,
                             compound=False, independent_approaches=False):
    """Try short three-leg channel doglegs before an expensive grid maze.

    These are proposals, not routes. Every complete leg and total locality
    bound must still pass the caller's ordinary exact-copper admission.
    """
    if type(compound) is not bool or type(independent_approaches) is not bool:
        raise ValueError('explicit compound channel proposal mode required')
    if independent_approaches and (not compound or type(max_axes) is not int
                                  or not 1 <= max_axes <= 8):
        raise ValueError('bounded independent approach proposal mode required')
    xs, ys = gap_axes(boxes, bounds, inflation=inflation, target=end, max_axes=max_axes)
    sx, sy = start
    tx, ty = end
    paths = set()
    for points in [*((start, (x, sy), (x, ty), end) for x in xs),
                   *((start, (sx, y), (tx, y), end) for y in ys)]:
        clean = []
        for point in points:
            if not clean or clean[-1] != point:
                clean.append(point)
        if len(clean) >= 2:
            paths.add(tuple(clean))
    ranked=sorted(paths, key=lambda path: (
        sum(abs(b[0]-a[0])+abs(b[1]-a[1]) for a, b in zip(path, path[1:])),
        len(path), path))
    if not compound:return ranked
    # A source pickup's last segment may have to be approached from only one
    # direction. A three-leg dogleg cannot leave the pin row, change axis,
    # and re-enter that original channel. Add a finite paired-axis tier only
    # after the old candidates, keeping already working routes unchanged.
    # Native box boundaries plus a one-micrometre outward proposal offset
    # expose tight off-grid corners; exact guards still decide every leg.
    axes=[]
    for axis,values in enumerate((xs,ys)):
        proposals=set(values)
        for box in boxes:
            proposals.update((math.floor(box[axis]-inflation)-1000,
                              math.ceil(box[axis+2]+inflation)+1000))
        axes.append(sorted((v for v in proposals if bounds[axis]<=v<=bounds[axis+2]),
            key=lambda v:(min(abs(v-start[axis]),abs(v-end[axis])),v))[:max_axes])
    extra=set()
    for x in axes[0]:
        for y in axes[1]:
            for points in ((start,(sx,y),(x,y),(x,ty),end),
                           (start,(x,sy),(x,y),(tx,y),end)):
                clean=[]
                for point in points:
                    if not clean or clean[-1]!=point:clean.append(point)
                if len(clean)>=2 and tuple(clean) not in paths:extra.add(tuple(clean))
    key=lambda path:(sum(abs(b[0]-a[0])+abs(b[1]-a[1])
        for a,b in zip(path,path[1:])),len(path),path)
    prefix=[*ranked,*sorted(extra,key=key)]
    if not independent_approaches:return prefix
    # A pin-row departure and a source-owned pickup may BOTH force a
    # horizontal (or vertical) terminal approach. Changing only one cross
    # channel cannot get around a middle obstruction without crossing a
    # terminal land. Give the departure and arrival their own bounded axes.
    # At most 2 * max_axes**3 extra five-leg proposals, after every existing
    # candidate. These acquire no geometry, contact or routing authority.
    longer=set();known=set(prefix)
    for x in axes[0]:
        for z in axes[0]:
            for y in axes[1]:
                points=(start,(x,sy),(x,y),(z,y),(z,ty),end)
                clean=tuple(point for i,point in enumerate(points)
                    if not i or point!=points[i-1])
                if len(clean)>=2 and clean not in known:longer.add(clean)
    for y in axes[1]:
        for z in axes[1]:
            for x in axes[0]:
                points=(start,(sx,y),(x,y),(x,z),(tx,z),end)
                clean=tuple(point for i,point in enumerate(points)
                    if not i or point!=points[i-1])
                if len(clean)>=2 and clean not in known:longer.add(clean)
    return [*prefix,*sorted(longer,key=key)]


def perimeter_channel_paths(start, end, boxes, bounds, *, inflation, max_axes=8):
    """Finite outside-spine proposals after the historical local channels.

    Nearest-only axes can all lie inside one power-bus enclosure. Cover both
    window extremes and source/destination-side obstacle boundaries before
    their near-aliases. Bounds are a search window, NOT proof of board area;
    every complete segment still needs native copper/edge/contact guards.
    At most 4 * max_axes**2 paths, with exact integer Manhattan coordinates.
    """
    if (type(max_axes) is not int or not 2 <= max_axes <= 8
            or type(boxes) not in (tuple,list) or len(boxes) > 256
            or any(type(b) not in (tuple,list) or len(b)!=4
                or any(type(v) not in (int,float) or not math.isfinite(v) for v in b)
                or b[0]>=b[2] or b[1]>=b[3] for b in boxes)
            or len(bounds) != 4
            or bounds[0] >= bounds[2] or bounds[1] >= bounds[3]
            or len(start) != 2 or len(end) != 2
            or any(type(v) is not int for v in (*start, *end))
            or type(inflation) not in (int, float) or inflation < 0
            or not all(math.isfinite(v) for v in
                (*bounds, inflation, *(v for b in boxes for v in b)))):
        raise ValueError('bounded_native_perimeter_channel_proposals_required')
    axes=[]
    for axis in (0,1):
        lo,hi=math.ceil(bounds[axis]),math.floor(bounds[axis+2])
        candidates={lo,hi,start[axis],end[axis]}
        for b in boxes:
            candidates.update((math.floor(b[axis]-inflation)-1000,
                math.ceil(b[axis+2]+inflation)+1000))
        candidates={v for v in candidates if lo <= v <= hi}
        selected=[]
        # Give four physically different approach signatures first refusal.
        for target in (lo,hi,start[axis],end[axis]):
            if candidates:
                chosen=min(candidates,key=lambda v:(abs(v-target),v))
                selected.append(chosen);candidates.remove(chosen)
        while candidates and len(selected)<max_axes:
            chosen=max(candidates,key=lambda v:(min(abs(v-q) for q in selected),-v))
            selected.append(chosen);candidates.remove(chosen)
        axes.append(selected[:max_axes])
    sx,sy=start;tx,ty=end
    paths=set()
    for x in axes[0]:
        for y in axes[1]:
            for points in ((start,(x,sy),(x,y),(tx,y),end),
                    (start,(sx,y),(x,y),(x,ty),end)):
                clean=tuple(point for i,point in enumerate(points)
                    if not i or point!=points[i-1])
                if len(clean)>=2:paths.add(clean)
    # This tier is cheap exact proposals, not a shortest-path certificate.
    return sorted(paths,key=lambda path:(sum(abs(b[0]-a[0])+abs(b[1]-a[1])
        for a,b in zip(path,path[1:])),len(path),path))
