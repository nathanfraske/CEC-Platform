"""Bounded nominal-pitch trunks with constructive octilinear fan-in.

Pure proposals: native foreign-copper, width, spacing, heading, coupling and
whole-board admission remain mandatory in the precision-router caller.
"""
import math


def candidates(pair, p_start, p_end, n_start, n_end, *, limit=128, deadline=None,
               existing_signed_skew_mm=0., max_skew=None):
    # Runtime import keeps the geometry implementation shared with its exact
    # caller, without introducing an import-time precision-router cycle.
    import cec_precision_route as route
    limit = min(128, int(limit))
    if limit <= 0:
        return []
    width, gap = float(pair['width']), float(pair['gap'])
    existing_signed_skew_mm = float(existing_signed_skew_mm)
    if (not math.isfinite(existing_signed_skew_mm)
            or (max_skew is not None and
                (not math.isfinite(float(max_skew)) or float(max_skew) < 0))):
        raise ValueError('invalid ribbon skew objective')
    points = (p_start, p_end, n_start, n_end)
    if (not all(math.isfinite(float(v)) for point in points for v in point)
            or not math.isfinite(width) or width <= 0
            or not math.isfinite(gap) or gap < 0):
        raise ValueError('invalid ribbon geometry')
    pitch = width + gap

    def launches(p, n):
        dx, dy = n[0]-p[0], n[1]-p[1]
        span = math.hypot(dx, dy)
        values = [(0., 0.)]
        if span > 1e-9:
            for reach in (0.6, 1.0):
                for sign in (-1., 1.):
                    delta = (-dy/span*reach*sign, dx/span*reach*sign)
                    if route._segment_is_octilinear((0., 0.), delta):
                        values.append(delta)
        return values

    def clean(points):
        result = []
        for point in points:
            if not result or route._dist(result[-1], point) > 1e-9:
                result.append(tuple(point))
        return result

    def taper(start, target, axis, diagonal_first):
        dx, dy = target[0]-start[0], target[1]-start[1]
        forward = dx*axis[0] + dy*axis[1]
        lateral = -dx*axis[1] + dy*axis[0]
        if forward + 1e-8 < abs(lateral):
            return None
        distance = abs(lateral) if diagonal_first else max(0., forward-abs(lateral))
        bend = (start[0]+distance*axis[0], start[1]+distance*axis[1])
        if diagonal_first:
            bend = (bend[0]-lateral*axis[1], bend[1]+lateral*axis[0])
        return clean([start, bend, target])

    raw = {}
    directions = [(math.cos(index*math.pi/4), math.sin(index*math.pi/4))
                  for index in range(8)]
    for start_delta in launches(p_start, n_start):
        ps, ns = [(point[0]+start_delta[0], point[1]+start_delta[1])
                  for point in (p_start, n_start)]
        for end_delta in launches(p_end, n_end):
            pe, ne = [(point[0]+end_delta[0], point[1]+end_delta[1])
                      for point in (p_end, n_end)]
            for axis in directions:
                if route._deadline_expired(deadline):
                    return []
                normal = (-axis[1], axis[0])
                def uv(point):
                    return (point[0]*axis[0]+point[1]*axis[1],
                            point[0]*normal[0]+point[1]*normal[1])
                sp, sn, ep, en = map(uv, (ps, ns, pe, ne))
                start_v, end_v = (sp[1]+sn[1])/2, (ep[1]+en[1])/2
                for mid_v in sorted({start_v, end_v, (start_v+end_v)/2}):
                    for sign in (-1., 1.):
                        pv, nv = mid_v+sign*pitch/2, mid_v-sign*pitch/2
                        # Both members need enough forward distance for their
                        # lateral pitch change at a legal 45-degree slope.
                        first = max(sp[0]+abs(pv-sp[1]), sn[0]+abs(nv-sn[1]))
                        last = min(ep[0]-abs(pv-ep[1]), en[0]-abs(nv-en[1]))
                        if last-first < pitch-1e-9:
                            continue
                        def xy(u, v):
                            return (u*axis[0]+v*normal[0], u*axis[1]+v*normal[1])
                        pa, na, pb, nb = xy(first,pv), xy(first,nv), xy(last,pv), xy(last,nv)
                        for diagonal_first in (False, True):
                            p_in, n_in = taper(ps,pa,axis,diagonal_first), taper(ns,na,axis,diagonal_first)
                            reverse = (-axis[0], -axis[1])
                            p_out, n_out = taper(pe,pb,reverse,diagonal_first), taper(ne,nb,reverse,diagonal_first)
                            if any(row is None for row in (p_in,n_in,p_out,n_out)):
                                continue
                            p = route._chamfer_axis_path(clean([p_start]+p_in+list(reversed(p_out))+[p_end]))
                            n = route._chamfer_axis_path(clean([n_start]+n_in+list(reversed(n_out))+[n_end]))
                            if (not route._polyline_is_octilinear(p) or not route._polyline_is_octilinear(n)
                                    or min(route._polyline_min_opening_angle(p),route._polyline_min_opening_angle(n)) < 89.
                                    or not route._polys_no_cross(p,n)
                                    or not route._pair_min_clear(p,n,-1,-1,width,gap,strict_pair_gap=True)):
                                continue
                            pl = sum(route._dist(a,b) for a,b in zip(p,p[1:]))
                            nl = sum(route._dist(a,b) for a,b in zip(n,n[1:]))
                            key = (tuple((round(x,6),round(y,6)) for x,y in p),
                                   tuple((round(x,6),round(y,6)) for x,y in n))
                            raw[key] = dict(p=p,n=n,geometry='octilinear-shared-trunk',
                                axis=list(axis),normal=list(normal),polarity_sign=int(sign),
                                preferred_polarity=sign == (1. if sp[1]+ep[1]>=sn[1]+en[1] else -1.),
                                p_length_mm=pl,n_length_mm=nl,trunk_length_mm=last-first,
                                projected_whole_skew_mm=abs(existing_signed_skew_mm+pl-nl))
    # Bound sampling cost before ranking against the existing physical
    # contract. This geometric proxy chooses proposals; it cannot admit them.
    frontier = sorted(raw.values(), key=lambda row:(
        -row['trunk_length_mm']/max(row['p_length_mm'],row['n_length_mm']),
        row['p_length_mm']+row['n_length_mm'], tuple(row['p']),tuple(row['n'])))[:limit]
    for row in frontier:
        if route._deadline_expired(deadline):
            return []
        row['coupling'] = route._polyline_coupling_coverage(row['p'],row['n'],width,gap)
        row['coupling_contract'] = route._pair_coupling_contract(pair,row['coupling'],
            {pair['p']:row['p_length_mm'],pair['n']:row['n_length_mm']})
    frontier.sort(key=lambda row:(
        max(0.,row['projected_whole_skew_mm']-float(max_skew)) if max_skew is not None else 0.,
        not row['coupling_contract']['ok'],
        -row['coupling']['fraction'],row['p_length_mm']+row['n_length_mm'],
        tuple(row['p']),tuple(row['n'])))
    return frontier
