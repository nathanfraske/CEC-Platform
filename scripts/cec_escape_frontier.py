"""Bounded, geometry-only proposals for an exhausted local via launch search.

No copper, fabrication or release authority lives here. The caller must prove
every barrel, complete launch and middle route against the native board.
"""
from __future__ import annotations

import math


def annular_offsets_mm(radius_mm=8.0, *, inner_mm=4.0, step_mm=.5):
    """Coarse exceptional ring, never a globally finer routing grid."""
    if (not all(math.isfinite(float(v)) for v in (radius_mm, inner_mm, step_mm))
            or not 4.0 <= inner_mm <= radius_mm <= 8.0
            or not .5 <= step_mm <= 2.0):
        raise ValueError('finite bounded launch annulus required')
    extent = math.floor(radius_mm / step_mm)
    rows = []
    for iy in range(-extent, extent + 1):
        for ix in range(-extent, extent + 1):
            distance2 = (ix * ix + iy * iy) * step_mm * step_mm
            if inner_mm * inner_mm < distance2 <= radius_mm * radius_mm:
                rows.append((distance2, abs(ix) + abs(iy), iy, ix,
                             round(ix * step_mm, 6), round(iy * step_mm, 6)))
    rows.sort()
    return tuple((row[4], row[5]) for row in rows)


def sector_frontier(points, origin, *, limit=32):
    """Round-robin nearest legal barrels by direction, with stable ties.

Nearest-only selection can spend every expensive attempt behind the same
obstacle. At most sixteen directional buckets share the bounded maze budget.
This is diversity of already guarded proposals, not a no-path certificate.
"""
    points = list(points)
    if (type(limit) is not int or not 1 <= limit <= 64 or len(points) > 1024
            or not all(math.isfinite(float(v)) for p in [origin, *points] for v in p)
            or any(len(p) != 2 for p in [origin, *points])):
        raise ValueError('finite bounded planar frontier required')
    buckets = {}
    for point in sorted(set(map(tuple, points))):
        dx, dy = point[0] - origin[0], point[1] - origin[1]
        sector = int((math.atan2(dy, dx) + math.pi) * 8 / math.pi) % 16
        buckets.setdefault(sector, []).append((dx * dx + dy * dy, point))
    ordered = [sorted(buckets[sector]) for sector in sorted(buckets)]
    result = []
    rank = 0
    while ordered and len(result) < limit:
        active = []
        for bucket in ordered:
            if rank < len(bucket):
                result.append(bucket[rank][1])
                active.append(bucket)
                if len(result) == limit:
                    break
        ordered = active
        rank += 1
    return result


def native_escape_sites(board, origin, net_code, *, radius_nm, diameter_nm,
                        clearance_nm, stub_layer, stub_width_nm, max_axes=8):
    """Finite off-grid barrel proposals outside actual all-layer obstacles.

    A wide inner bus and a surface pin row have different exclusion margins.
    Their independently inflated native edges provide escape axes; neither
    boxes nor this menu grant drill, copper, zone, contact or field authority.
    At most 64 sites and 256 native boxes participate, regardless of board size.
    Stub width and landing diameter are exact native construction inputs,
    not search budgets.
    Wide inner-layer buses must not abort the entire bridge portfolio merely
    because their required width exceeds a signal-oriented 2 mm assumption.
    Positive KiCad integer widths/diameters retain the same radius/site bounds;
    every returned seat and full-width stub still needs independent guards.
    """
    if (type(origin) not in (tuple, list) or len(origin)!=2
            or any(type(v) is not int for v in origin)
            or type(net_code) is not int or type(stub_layer) is not int
            or type(max_axes) is not int or not 2<=max_axes<=8
            or any(type(v) is not int for v in
                (radius_nm,diameter_nm,clearance_nm,stub_width_nm))
            or not 0<radius_nm<=8_000_000 or not 0<diameter_nm<=2_147_483_647
            or not 0<=clearance_nm<=2_000_000 or not 0<stub_width_nm<=2_147_483_647):
        raise ValueError('bounded_native_escape_geometry_required')
    from cec_maze_channels import native_obstacle_boxes
    bounds=(origin[0]-radius_nm,origin[1]-radius_nm,
            origin[0]+radius_nm,origin[1]+radius_nm)
    layers=tuple(map(int,board.GetEnabledLayers().CuStack()))
    if stub_layer not in layers:raise ValueError('enabled_escape_face_required')
    rows=set()
    for layer in layers:
        for box in native_obstacle_boxes(board,layer,{net_code},bounds,origin):
            rows.add((box,diameter_nm/2+clearance_nm))
            if layer==stub_layer:rows.add((box,stub_width_nm/2+clearance_nm))
    rank=lambda row:(sum((max(row[0][i]-origin[i],0,origin[i]-row[0][i+2]))**2
        for i in (0,1)),row)
    rows=sorted(rows,key=rank)[:256]
    axes=[]
    for axis in (0,1):
        values={origin[axis]}
        shadow_edges=set()
        for box,margin in rows:
            edges=(math.floor(box[axis]-margin)-1000,
                   math.ceil(box[axis+2]+margin)+1000)
            values.update(edges)
            if all(box[i]-margin<=origin[i]<=box[i+2]+margin for i in (0,1)):
                shadow_edges.update(edges)
        values={v for v in values if bounds[axis]<=v<=bounds[axis+2]}
        shadow_edges&=values
        # Preserve both directions before letting aliases around one nearby
        # pin consume the finite proposal budget.
        halves=[sorted((v for v in values if v<origin[axis]),reverse=True),
                sorted(v for v in values if v>origin[axis])]
        selected=[origin[axis]]
        # Reserve actual exits from the origin's multilayer shadow. Otherwise
        # tiny aliases around many surface pads can evict every wide-bus edge
        # before the cross-product is considered, recreating the blind disk.
        shadow_halves=[sorted((v for v in shadow_edges if v<origin[axis]),reverse=True),
                       sorted(v for v in shadow_edges if v>origin[axis])]
        for offset in range(2):
            for half in shadow_halves:
                if offset<len(half) and all(abs(half[offset]-p)>=2000 for p in selected):
                    selected.append(half[offset])
                if len(selected)>=max_axes:break
            if len(selected)>=max_axes:break
        for offset in range(max_axes):
            for half in halves:
                for v in half[offset:]:
                    if all(abs(v-p)>=2000 for p in selected):
                        selected.append(v);break
                if len(selected)>=max_axes:break
            if len(selected)>=max_axes:break
        axes.append(selected)
    sites={(x,y) for x in axes[0] for y in axes[1]
        if (x,y)!=tuple(origin) and math.dist((x,y),origin)<=radius_nm}
    return sector_frontier(sites,origin,limit=64)
