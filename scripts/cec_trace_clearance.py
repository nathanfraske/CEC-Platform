"""Independent integer-geometry audit of different-net straight trace gaps.

This checks declared netclass/floor clearances, with no pair-name exemption.
Native DRC remains authoritative for custom rules, pads, vias, zones and arcs.
The report is explicitly scoped; it is not a replacement for complete DRC.
"""
import math
from collections import defaultdict
from fractions import Fraction


def _orient(a, b, p):
    return (b[0]-a[0])*(p[1]-a[1]) - (b[1]-a[1])*(p[0]-a[0])


def _on(a, b, p):
    return (_orient(a, b, p) == 0 and min(a[0], b[0]) <= p[0] <= max(a[0], b[0])
            and min(a[1], b[1]) <= p[1] <= max(a[1], b[1]))


def _point_distance_sq(p, a, b):
    dx, dy = b[0]-a[0], b[1]-a[1]
    dot = (p[0]-a[0])*dx + (p[1]-a[1])*dy
    length_sq = dx*dx+dy*dy
    if dot <= 0 or length_sq == 0:
        return Fraction((p[0]-a[0])**2+(p[1]-a[1])**2)
    if dot >= length_sq:
        return Fraction((p[0]-b[0])**2+(p[1]-b[1])**2)
    return Fraction(_orient(a, b, p)**2, length_sq)


def segment_distance_sq(a, b, c, d):
    """Exact squared centreline distance in integer coordinate units."""
    ac, ad, ca, cb = _orient(a, b, c), _orient(a, b, d), _orient(c, d, a), _orient(c, d, b)
    if ((ac*ad < 0 and ca*cb < 0) or _on(a, b, c) or _on(a, b, d)
            or _on(c, d, a) or _on(c, d, b)):
        return Fraction(0)
    return min(_point_distance_sq(p, x, z)
               for p, x, z in ((a, c, d), (b, c, d), (c, a, b), (d, a, b)))


def analyze(board, *, netclass_resolver, minimum_clearance_mm=0.0, detail_limit=24):
    """Read-only trace-to-trace audit; no numerical tolerance weakens limits."""
    if not math.isfinite(minimum_clearance_mm) or minimum_clearance_mm < 0:
        raise ValueError('minimum clearance must be finite and nonnegative')
    by_layer = defaultdict(list)
    unsupported, errors, clearances = [], [], {}
    for item in board.GetTracks():
        if item.GetClass() == 'PCB_VIA':
            continue
        if item.GetClass() != 'PCB_TRACK':
            unsupported.append(str(item.m_Uuid.AsString()))
            continue
        net = str(item.GetNetname())
        if net not in clearances:
            spec = netclass_resolver(net)
            clearance = spec.get('clearance') if isinstance(spec, dict) else None
            if (not isinstance(clearance, (int, float)) or isinstance(clearance, bool)
                    or not math.isfinite(clearance) or clearance < 0):
                errors.append(dict(net=net, reason='missing_or_invalid_clearance'))
                clearances[net] = None
            else:
                clearances[net] = round(max(minimum_clearance_mm, clearance)*1e6)
        if clearances[net] is None:
            continue
        a, b = item.GetStart(), item.GetEnd()
        by_layer[int(item.GetLayer())].append(dict(net=net,
            code=int(item.GetNetCode()), uuid=str(item.m_Uuid.AsString()),
            a=(int(a.x), int(a.y)), b=(int(b.x), int(b.y)), width=int(item.GetWidth())))
    if not isinstance(detail_limit, int) or isinstance(detail_limit, bool) or detail_limit < 0:
        raise ValueError('detail limit must be a nonnegative integer')
    nearest, violations, tested, count, below_database_unit = [], [], 0, 0, 0
    for layer, rows in sorted(by_layer.items()):
        for i, a in enumerate(rows):
            for b in rows[i+1:]:
                if a['code'] == b['code'] and a['code'] > 0:
                    continue
                tested += 1
                distance_sq = segment_distance_sq(a['a'], a['b'], b['a'], b['b'])
                need = max(clearances[a['net']], clearances[b['net']])
                twice_need = 2*need+a['width']+b['width']
                violation = 4*distance_sq < twice_need*twice_need
                gap = (math.sqrt(distance_sq) - (a['width']+b['width'])/2)/1e6
                row = dict(layer=str(board.GetLayerName(layer)), nets=[a['net'], b['net']],
                    uuids=[a['uuid'], b['uuid']], gap_mm=round(gap, 9),
                    required_mm=need/1e6, margin_mm=round(gap-need/1e6, 9))
                if violation:
                    count += 1
                    # Keep the exact shortfall as a violation. Separately name
                    # sub-one-nanometre boundary rounding, so a 45-degree
                    # lattice boundary is not described as a macroscopic gap
                    # failure. This classification changes no acceptance rule.
                    if twice_need >= 2 and 4*distance_sq >= (twice_need-2)**2:
                        below_database_unit += 1
                    violations.append(row)
                    violations.sort(key=lambda r: (r['margin_mm'], r['uuids']))
                    del violations[max(0, detail_limit):]
                if detail_limit and (len(nearest) < detail_limit or row['margin_mm'] < nearest[-1]['margin_mm']):
                    nearest.append(row)
                    nearest.sort(key=lambda r: (r['margin_mm'], r['uuids']))
                    del nearest[max(0, detail_limit):]
    complete = not (unsupported or errors)
    return dict(schema=1, ok=complete and count == 0, complete=complete,
        scope='different-net same-layer straight trace pairs, netclass/floor clearance',
        release_authority=False, tested_pairs=tested, violation_count=count,
        sub_database_unit_shortfalls=below_database_unit,
        shortfalls_at_least_one_nm=count-below_database_unit,
        violations=violations, nearest=nearest, unsupported_arcs=unsupported,
        errors=errors, clearance_by_net_mm={k: v/1e6 for k, v in clearances.items() if v is not None})
