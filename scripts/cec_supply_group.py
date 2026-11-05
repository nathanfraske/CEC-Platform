"""Bounded combinatorial supply-group placement, independent of PCB identity.

Options, compatibility and final admission come from geometry/topology adapters.
No partial group is a solution. Search exhaustion is not geometric impossibility.
"""
from __future__ import annotations

import math


def layouts(options, compatible, *, verify=lambda group: True,
            beam_width=24, max_states=4096, max_solutions=12):
    if min(beam_width, max_states, max_solutions) < 1:
        raise ValueError("supply-group budgets must be positive")
    order = sorted(options, key=lambda ref: (len(options[ref]), ref))
    report = {"states": 0, "budget": max_states, "members": order,
              "complete": 0, "reason": "no_complete_group"}
    if not order or any(not options[r] for r in order):
        return [], report
    beam = [(0., {})]
    for ref in order:
        expanded = []
        for cost, group in beam:
            for option in options[ref]:
                if report["states"] >= max_states:
                    report["reason"] = "state_budget"
                    break
                report["states"] += 1
                if all(compatible(option, other) for other in group.values()):
                    value = float(option["cost"])
                    if not math.isfinite(value):
                        raise ValueError("supply-group cost must be finite")
                    expanded.append((cost + value, dict(group, **{ref: option})))
            if report["states"] >= max_states:
                break
        # Stable input order breaks equal-cost ties. Do not compare dictionaries.
        beam = sorted(expanded, key=lambda row: row[0])[:beam_width]
        if not beam:
            return [], report
    complete = [group for _cost, group in beam if set(group) == set(order) and verify(group)]
    report["complete"] = len(complete)
    if complete:
        report["reason"] = "complete_groups"
    return complete[:max_solutions], report


def owner_sites(origin, *, fixed=False, radius_mm=8., max_sites=196):
    """Stable multiscale rings cover a finite neighborhood without a dense grid."""
    if not math.isfinite(radius_mm) or radius_mm < 0 or max_sites < 1:
        raise ValueError("invalid owner search bounds")
    x, y, rot = map(float, origin)
    if not all(math.isfinite(v) for v in (x, y, rot)):
        raise ValueError("owner pose must be finite")
    if fixed:
        return [(x, y, rot)]
    deltas = [(0., 0.)]
    for scale in (.125, .25, .5, .75, 1.):
        radius = radius_mm * scale
        for dx, dy in ((1,0), (0,1), (-1,0), (0,-1), (1,1), (-1,1), (-1,-1), (1,-1)):
            length = math.hypot(dx, dy)
            deltas.append((radius*dx/length, radius*dy/length))
    seen, result = set(), []
    for dx, dy in deltas:
        for angle in (rot, rot+90., rot+180., rot+270.):
            pose = (x+dx, y+dy, angle % 360.)
            if pose not in seen:
                seen.add(pose); result.append(pose)
                if len(result) >= max_sites:
                    return result
    return result


def contact_owner_sites(layouts, origin, *, part_box, bounds, obstacles=(),
                        clearance=.10, max_sites=196):
    """Obstacle-derived fallback when a provisional origin is inside a keepout.

    All member rectangles participate in configuration-space subtraction.
    Bounds/obstacles use xmin/ymin/xmax/ymax; part_box returns that same order.
    Returning a site is only a proposal; the caller still checks every member,
    layer, pin escape, and authored-copper obstacle before atomic commitment.
    """
    from cec_cell_packing import contact_translation_sites
    if max_sites < 1:
        raise ValueError("contact site budget must be positive")
    x,y,rot = origin
    choices = set()
    for layout in layouts:
        for angle in (rot,rot+90.,rot+180.,rot+270.):
            parts = []
            a = math.radians(angle)
            for ref,(px,py,pr) in layout.items():
                # KiCad's positive rotation is clockwise in screen coordinates.
                dx = px*math.cos(a)+py*math.sin(a)
                dy = -px*math.sin(a)+py*math.cos(a)
                parts.append(part_box(ref,(dx,dy,(pr+angle)%360.)))
            domain = (bounds[0]-min(p[0] for p in parts),
                      bounds[1]-min(p[1] for p in parts),
                      bounds[2]-max(p[2] for p in parts),
                      bounds[3]-max(p[3] for p in parts))
            if domain[0] >= domain[2] or domain[1] >= domain[3]:
                continue
            for ox,oy in contact_translation_sites(parts,bounds=domain,
                    obstacles=obstacles,clearance=clearance,max_sites=32):
                choices.add((ox,oy,angle%360.))
    return sorted(choices,key=lambda p: (math.hypot(p[0]-x,p[1]-y),p))[:max_sites]


def seat(layouts, origin, *, part_box, bounds, obstacles=(), fixed=False,
         admit=lambda poses: True, max_sites=196, radius_mm=8., clearance=.1):
    """Reserve an entire group before its owner crosses a lock boundary.

    Geometry uses xmin/ymin/xmax/ymax. Failure leaves caller data untouched.
    External admission remains authoritative even for obstacle-derived sites.
    """
    sites=owner_sites(origin,fixed=fixed,radius_mm=radius_mm,max_sites=max_sites)
    if not fixed and layouts:
        contacts=contact_owner_sites(layouts,origin,part_box=part_box,bounds=bounds,
            obstacles=obstacles,clearance=clearance,max_sites=max_sites)
        sites += [p for p in contacts if p not in set(sites)]
    report={"proposals":0,"sites":len(sites),"ok":False}
    for x,y,angle in sites:
        a=math.radians(angle)
        for layout in layouts:
            report["proposals"]+=1
            posed={r:(x+px*math.cos(a)+py*math.sin(a),
                      y-px*math.sin(a)+py*math.cos(a),(rot+angle)%360.)
                   for r,(px,py,rot) in layout.items()}
            boxes=[part_box(r,p) for r,p in posed.items()]
            if any(b[0]<bounds[0] or b[1]<bounds[1] or b[2]>bounds[2] or b[3]>bounds[3]
                   for b in boxes):
                continue
            if any(b[0]-clearance<o[2] and b[2]+clearance>o[0]
                   and b[1]-clearance<o[3] and b[3]+clearance>o[1]
                   for b in boxes for o in obstacles):
                continue
            if not admit(posed):
                continue
            report.update(ok=True,positions=posed)
            return posed,report
    report["reason"]="no_complete_prelock_seat"
    return None,report
