"""Rank local return seats without consuming neighbouring pin escape space.

This is a bounded proposal heuristic, not an electrical or fabrication waiver.
Only rays admitted against the existing native board are counted. Losing every
sampled ray is a useful congestion signal, never a proof of unroutability. The
caller still qualifies every proposed via, track, hole and endpoint exception.
"""
from __future__ import annotations

import math
from collections import Counter

MM = 1_000_000
DIRECTIONS = tuple((math.cos(math.radians(a)), math.sin(math.radians(a)))
                   for a in range(0, 360, 45))


def smd_surface_layer(pad):
    """Resolve a real single-surface SMD land, never PAD.GetLayer()'s hint.

    KiCad can report F.Cu from GetLayer() for a B.Cu-only pad, including after
    save/reload. Ambiguous, non-surface and non-SMD terminals have no inferred
    surface escape. Their separate native validity/connectivity gates remain.
    """
    import pcbnew
    if int(pad.GetAttribute()) != int(pcbnew.PAD_ATTRIB_SMD):
        return None
    layers = tuple(int(layer) for layer in pad.GetLayerSet().CuStack())
    return layers[0] if len(layers) == 1 and layers[0] in (pcbnew.F_Cu, pcbnew.B_Cu) else None


def point_segment_distance(point, start, end):
    dx, dy = end[0] - start[0], end[1] - start[1]
    length2 = dx*dx + dy*dy
    t = (max(0., min(1., ((point[0]-start[0])*dx +
                          (point[1]-start[1])*dy)/length2)) if length2 else 0.)
    return math.hypot(point[0]-start[0]-t*dx, point[1]-start[1]-t*dy)


def segment_distance(a, b, c, d):
    def cross(p, q, r):
        return (q[0]-p[0])*(r[1]-p[1]) - (q[1]-p[1])*(r[0]-p[0])
    ab_c, ab_d, cd_a, cd_b = cross(a, b, c), cross(a, b, d), cross(c, d, a), cross(c, d, b)
    if ((ab_c > 0 > ab_d or ab_c < 0 < ab_d)
            and (cd_a > 0 > cd_b or cd_a < 0 < cd_b)):
        return 0.
    return min(point_segment_distance(a, c, d), point_segment_distance(b, c, d),
               point_segment_distance(c, a, b), point_segment_distance(d, a, b))


def loss(ports, origin, at, *, diameter_mm, width_mm, layer, clearance_mm):
    """Capsule/disk obstruction cost; no mutation and no acceptance decision."""
    stranded, affected, lost, available = 0, 0, 0, 0
    for port in ports:
        rays = port['rays']
        removed = 0
        gap = max(clearance_mm, port['clearance_mm']) + port['width_mm']/2
        for start, end in rays:
            via_hit = point_segment_distance(at, start, end) < diameter_mm/2 + gap - 1e-9
            track_hit = (port['layer'] == layer and
                         segment_distance(origin, at, start, end) < width_mm/2 + gap - 1e-9)
            removed += bool(via_hit or track_hit)
        available += len(rays)
        lost += removed
        affected += removed > 0
        stranded += bool(rays) and removed == len(rays)
    return dict(newly_stranded_ports=stranded, affected_ports=affected,
                lost_rays=lost, baseline_rays=available, sampled_ports=len(ports),
                sampled_only=True, exhaustion_is_no_path_proof=False)


def cost(report):
    return tuple(report[k] for k in ('newly_stranded_ports', 'affected_ports', 'lost_rays'))


def capture(board, pad, *, reach_mm, diameter_mm, netclass, foreign_cache,
            max_ports=32, ray_scales=(.5, 1.)):
    """Capture bounded short and long exact-clear rays on foreign SMD ports.

    Every selected port uses its own netclass width and clearance. The return's
    clearance also participates when ranking its shadow. Cached native shapes
    are immutable for this one seat search. Through-hole pads already have
    layer access and do not need a speculative surface escape reservation.
    """
    import pcbnew
    import cec_fr
    if (not math.isfinite(reach_mm) or reach_mm <= 0
            or not math.isfinite(diameter_mm) or diameter_mm <= 0
            or not isinstance(max_ports, int) or not 1 <= max_ports <= 32
            or not 1 <= len(ray_scales) <= 3
            or any(not math.isfinite(s) or not 0 < s <= 1 for s in ray_scales)):
        raise ValueError('invalid bounded return escape policy')
    position = pad.GetPosition()
    candidates = []
    radius = 2*reach_mm + diameter_mm/2 + 1.
    pads = [p for footprint in board.GetFootprints() for p in footprint.Pads()]
    terminals = Counter(p.GetNetCode() for p in pads)
    for other in pads:
        if (other.GetAttribute() != pcbnew.PAD_ATTRIB_SMD or other.GetNetCode() <= 0
                or other.GetNetCode() == pad.GetNetCode()
                or terminals[other.GetNetCode()] < 2):
            continue
        p = other.GetPosition()
        distance = math.hypot(p.x-position.x, p.y-position.y)/MM
        if distance <= radius:
            candidates.append((distance, str(other.m_Uuid.AsString()), other))
    ports, initially_blocked, unresolved_surface = [], 0, 0
    for _, uid, other in sorted(candidates, key=lambda x: x[:2])[:max_ports]:
        layer = smd_surface_layer(other)
        if layer is None or not board.IsLayerEnabled(layer):
            unresolved_surface += 1
            continue
        spec = netclass(board, str(other.GetNetname()))
        width, clearance = int(spec['width']), int(spec['clearance'])
        if width <= 0 or clearance < 0:
            raise ValueError('invalid neighbour route dimensions')
        p = other.GetPosition()
        # A short legal exit may turn before a longer ray hits another object.
        # Sampling only the longest ray misses precisely this local access.
        lengths = sorted({max(reach_mm*scale,
            max(other.GetSize().x, other.GetSize().y)/MM/2 + .25) for scale in ray_scales})
        rays = []
        for ray_length in lengths:
            for dx, dy in DIRECTIONS:
                q = pcbnew.VECTOR2I(round(p.x + dx*ray_length*MM), round(p.y + dy*ray_length*MM))
                if (cec_fr._edge_leg_clear(board, p, q, width//2) and
                        cec_fr._tap_foreign_clear(board, p, q, width, layer, clearance,
                            {other.GetNetCode()}, foreign_cache=foreign_cache)):
                    rays.append(((p.x/MM, p.y/MM), (q.x/MM, q.y/MM)))
        if rays:
            ports.append(dict(uuid=uid, layer=layer, width_mm=width/MM,
                              clearance_mm=clearance/MM, rays=rays))
        else:
            initially_blocked += 1
    return dict(ports=ports, initially_blocked_ports=initially_blocked,
                unresolved_surface_ports=unresolved_surface,
                considered_ports=min(max_ports, len(candidates)),
                omitted_ports=max(0, len(candidates)-max_ports), rays_per_port_limit=8*len(ray_scales),
                exhaustion_is_no_path_proof=False)


def ranked_sites(context, origin, sites, *, diameter_mm, width_mm, layer, clearance_mm):
    """Keep original deterministic ordering when access cost ties."""
    ranked = []
    for index, (radius, at) in enumerate(sites):
        report = loss(context['ports'], origin, at, diameter_mm=diameter_mm,
                      width_mm=width_mm, layer=layer, clearance_mm=clearance_mm)
        ranked.append((cost(report), index, radius, at, report))
    ranked.sort(key=lambda row: (row[0], row[1]))
    return [(radius, at, dict(report, original_index=index))
            for _, index, radius, at, report in ranked]
