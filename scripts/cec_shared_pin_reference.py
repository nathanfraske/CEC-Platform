"""Continuous two-capacitor shared-pin packing reference, independent of ECAD.

An isolated loop optimum is not simultaneously attainable when two bypasses
share a pin. Each sum-of-two-distances sublevel set is an ellipse. Clip that
ellipse to the four legal sides of a rectangular owner courtyard and evaluate
its exact axis supports. Two rectangular capacitors can coexist iff one of
their four separating-axis inequalities is feasible. Bisection therefore
bounds the minimum *maximum excess over the individual loop references*.

The lower bound is deliberately optimistic: other components, board edges,
absolute leg limits, and copper are absent. They can only make placement
harder. This bound must never qualify those independent checks. A witness is
a placement proposal, not copper or assembly admission. Unsupported larger
cells are not guessed; their existing independent checks remain authoritative.
"""
from __future__ import annotations

import math


def _finite(values):
    return all(math.isfinite(float(v)) for v in values)


def _support(focus_a, focus_b, length, axis, sign, clip_axis, clip_sign, clip_value):
    """Support point of a (closed) ellipse intersected with h.p <= k.

    Degenerate segments use the same formula with zero conditional variance.
    Small roundoff is handled conservatively; it cannot increase the returned
    infeasibility lower bound beyond the separate bisection safety deduction.
    """
    mx, my = ((focus_a[i] + focus_b[i]) / 2 for i in (0, 1))
    dx, dy = ((focus_b[i] - focus_a[i]) / 2 for i in (0, 1))
    c2 = dx * dx + dy * dy
    a2 = (length / 2) ** 2
    if a2 < c2 - 1e-12:
        return None
    b2 = max(0., a2 - c2)
    q = ((b2 + dx * dx, dx * dy), (dx * dy, b2 + dy * dy))
    m = (mx, my)
    radius = math.sqrt(max(0., q[axis][axis]))
    point = tuple(m[i] + (sign * q[i][axis] / radius if radius else 0.) for i in (0, 1))
    if clip_sign * point[clip_axis] <= clip_value + 1e-12:
        return point
    variance = q[clip_axis][clip_axis]
    delta = clip_value - clip_sign * m[clip_axis]
    if variance <= 1e-20 or delta < -math.sqrt(variance) - 1e-12:
        return None
    factor = max(0., 1. - delta * delta / variance)
    center = tuple(m[i] + q[i][clip_axis] * clip_sign * delta / variance for i in (0, 1))
    conditional = tuple(q[i][axis] - q[i][clip_axis] * q[clip_axis][axis] / variance for i in (0, 1))
    radius = math.sqrt(max(0., factor * conditional[axis]))
    return tuple(center[i] + (sign * factor * conditional[i] / radius if radius > 1e-15 else 0.) for i in (0, 1))


def _domains(owner_box, supply, grounds, cell, excess, gap):
    """Attained support points over each orientation's union of legal regions."""
    domains = []
    length = cell['ideal_loop_mm'] + excess
    for orientation in cell['orientations']:
        box = orientation['box']
        rail, ground = orientation['supply_offset'], orientation['ground_offset']
        f1 = tuple(supply[i] - rail[i] for i in (0, 1))
        clips = ((0, 1, owner_box[0] - box[1] - gap),
                 (0, -1, -(owner_box[1] - box[0] + gap)),
                 (1, 1, owner_box[2] - box[3] - gap),
                 (1, -1, -(owner_box[3] - box[2] + gap)))
        supports = {}
        for gp in grounds:
            f2 = tuple(gp[i] - ground[i] for i in (0, 1))
            for clip_axis, clip_sign, clip_value in clips:
                for axis in (0, 1):
                    for sign in (-1, 1):
                        point = _support(f1, f2, length, axis, sign,
                                         clip_axis, clip_sign, clip_value)
                        if point is None:
                            continue
                        key = axis, sign
                        old = supports.get(key)
                        if old is None or sign * point[axis] > sign * old[axis]:
                            supports[key] = point
        if len(supports) == 4:
            domains.append((orientation, supports))
    return domains


def _witness(owner_box, supply, grounds, cells, excess, gap):
    domains = [_domains(owner_box, supply, grounds, cell, excess, gap) for cell in cells]
    for a, sa in domains[0]:
        for b, sb in domains[1]:
            for axis in (0, 1):
                lo, hi = 2 * axis, 2 * axis + 1
                for reversed_order in (False, True):
                    left, sl, right, sr = (b, sb, a, sa) if reversed_order else (a, sa, b, sb)
                    pl, pr = sl[axis, -1], sr[axis, 1]
                    if pl[axis] + left['box'][hi] + gap <= pr[axis] + right['box'][lo] + 1e-12:
                        rows = [(left, pl), (right, pr)]
                        if reversed_order:
                            rows.reverse()
                        return {cell['id']: [point[0], point[1], orientation['angle_deg']]
                                for cell, (orientation, point) in zip(cells, rows)}
    return None


def shared_pin_reference(owner_box, supply, grounds, cells, *, gap_mm=0.,
                         max_excess_mm=2., tolerance_mm=0.00001):
    """Return a certified optimistic lower bound plus an independent witness.

    Exactly two same-face rectangular capacitor courtyards and four cardinal
    orientations are supported. IDs are opaque result keys, never policy.
    Callers retain the actual per-device leg limits and local copper proofs.
    """
    if (len(cells) != 2 or len({str(c['id']) for c in cells}) != 2
            or len(owner_box) != 4 or len(supply) != 2 or not grounds
            or any(len(p) != 2 for p in grounds)
            or not _finite([*owner_box, *supply, *(x for p in grounds for x in p),
                            gap_mm, max_excess_mm, tolerance_mm])
            or not (0 <= gap_mm and 0 < tolerance_mm <= 0.001 and
                    tolerance_mm < max_excess_mm <= 10.)
            or owner_box[0] >= owner_box[1] or owner_box[2] >= owner_box[3]):
        raise ValueError('invalid bounded shared-pin reference geometry')
    for cell in cells:
        if (not math.isfinite(cell['ideal_loop_mm']) or cell['ideal_loop_mm'] <= 0
                or len(cell['orientations']) != 4):
            raise ValueError('invalid shared-pin cell')
        angles = set()
        for o in cell['orientations']:
            if (len(o['box']) != 4 or len(o['supply_offset']) != 2 or len(o['ground_offset']) != 2
                    or not _finite([*o['box'], *o['supply_offset'], *o['ground_offset'], o['angle_deg']])
                    or o['box'][0] >= o['box'][1] or o['box'][2] >= o['box'][3]
                    or abs(o['angle_deg'] % 90.) > 1e-8):
                raise ValueError('invalid shared-pin orientation')
            angles.add(o['angle_deg'] % 360.)
        if len(angles) != 4:
            raise ValueError('four distinct cardinal orientations required')
    witness = _witness(owner_box, supply, grounds, cells, 0., gap_mm)
    lo = hi = 0.
    iterations = 0
    if witness is None:
        hi = max_excess_mm
        witness = _witness(owner_box, supply, grounds, cells, hi, gap_mm)
        if witness is None:
            return {'ok': False, 'reason': 'bounded_reference_unavailable',
                    'max_excess_mm': max_excess_mm}
        while hi - lo > tolerance_mm:
            middle = (lo + hi) / 2.
            trial = _witness(owner_box, supply, grounds, cells, middle, gap_mm)
            if trial is None:
                lo = middle
            else:
                hi, witness = middle, trial
            iterations += 1
    # A tangent witness may touch a neighbour exactly. Offer a slightly
    # interior proposal without using that extra gap to inflate the bound.
    interior = _witness(owner_box, supply, grounds, cells, hi + 0.05, gap_mm + 0.01)
    return {'schema': 1, 'ok': True,
            'mode': 'two_cap_shared_pin_continuous_minimax',
            'lower_bound_mm': max(0., lo - tolerance_mm),
            'upper_bound_mm': hi, 'bracket_mm': hi - max(0., lo - tolerance_mm),
            'tolerance_mm': tolerance_mm, 'iterations': iterations,
            'placements': witness, 'interior_placements': interior,
            'scope': 'optimistic_geometry_reference_not_copper_or_assembly_admission',
            'excluded_constraints': ['other_components', 'board_edges', 'absolute_leg_limits', 'copper']}


def _authored_rectangle(footprint):
    """Read courtyard centre-lines; KiCad's cached envelope adds pen width."""
    import pcbnew
    if abs(footprint.GetOrientationDegrees() % 90.) > 1e-8:
        return None
    layer = pcbnew.B_CrtYd if footprint.IsFlipped() else pcbnew.F_CrtYd
    shapes = [g for g in footprint.GraphicalItems() if g.GetLayer() == layer]
    edges = []
    for shape in shapes:
        start, end = shape.GetStart(), shape.GetEnd()
        a, b = (start.x, start.y), (end.x, end.y)
        if shape.GetShape() == pcbnew.SHAPE_T_RECT and len(shapes) == 1:
            x0,x1 = sorted((a[0],b[0])); y0,y1 = sorted((a[1],b[1]))
            if x0 < x1 and y0 < y1:
                return [x0/1e6,x1/1e6,y0/1e6,y1/1e6]
        if shape.GetShape() != pcbnew.SHAPE_T_SEGMENT or a == b or (a[0] != b[0] and a[1] != b[1]):
            return None
        edges.append(frozenset((a,b)))
    if len(edges) != 4:
        return None
    points = {p for edge in edges for p in edge}
    if len(points) != 4:
        return None
    xs,ys = sorted({p[0] for p in points}),sorted({p[1] for p in points})
    if len(xs) != 2 or len(ys) != 2:
        return None
    x0,x1=xs; y0,y1=ys
    required = {frozenset(((x0,y0),(x1,y0))), frozenset(((x1,y0),(x1,y1))),
                frozenset(((x1,y1),(x0,y1))), frozenset(((x0,y1),(x0,y0)))}
    if set(edges) != required:
        return None
    return [x0/1e6,x1/1e6,y0/1e6,y1/1e6]


def references_from_board(board, assigned, access, tangent_fn, *, tangent_gap_mm=0.1,
                          ground_max_mm=2.5):
    """Optional reference only for exactly two proven dual-via shared-pin cells.

    Missing/irregular courtyard geometry or unsupported populations leave the
    original gate unchanged. No library/refdes/board-name exception is used.
    """
    from collections import defaultdict
    import pcbnew
    from cec_decoupler_cell import qualified_via_in_pad_return, _cell_return_pads
    groups = defaultdict(list)
    for item in assigned.values():
        req = item['requirement']
        groups[(req.get('ref'),str(req.get('pin')),req.get('rail'),req.get('return_rail') or 'GND')].append(item)
    result = {}
    xy = lambda pad: [pad.GetPosition().x/1e6,pad.GetPosition().y/1e6]
    for (owner_ref,pin,rail,return_rail), items in groups.items():
        if len(items) != 2:
            continue
        physical_pins = [item['requirement'].get('pad') for item in items]
        if any(p is None for p in physical_pins) or xy(physical_pins[0]) != xy(physical_pins[1]):
            continue
        owner = board.FindFootprintByReference(owner_ref)
        caps = [board.FindFootprintByReference(item.get('cap_ref')) for item in items]
        if owner is None or any(c is None or c.IsFlipped() != owner.IsFlipped() for c in caps):
            continue
        proofs = [access.get((owner_ref,pin,item.get('cap_ref'))) or {} for item in items]
        if any(p.get('status') == 'refused' or not qualified_via_in_pad_return(p.get('ground_return'))
               or not qualified_via_in_pad_return(p.get('owner_ground_return')) for p in proofs):
            continue
        owner_box = _authored_rectangle(owner)
        if owner_box is None:
            continue
        return_sets = [_cell_return_pads(item['requirement'], owner, cap)[2]
                       for item, cap in zip(items, caps)]
        common_ids = set.intersection(*(
            {p.m_Uuid.AsString() for p in rows} for rows in return_sets))
        grounds = [p for p in return_sets[0] if p.m_Uuid.AsString() in common_ids]
        if not grounds:
            continue
        cells,tangents = [],{}
        for item,cap in zip(items,caps):
            req=item['requirement']
            supply = next((p for p in cap.Pads() if p.GetNetname()==rail),None)
            ground = next((p for p in cap.Pads() if p.GetNetname()==return_rail),None)
            if supply is None or ground is None or req.get('pad') is None:
                break
            tangent = tangent_fn(owner,cap,req['pad'],supply,grounds,ground,
                                 gap_mm=tangent_gap_mm,ground_max_mm=ground_max_mm)
            if not (tangent or {}).get('best_loop'):
                break
            orientations = []
            for angle in (0.,90.,180.,270.):
                detached = pcbnew.FOOTPRINT(cap)
                detached.SetPosition(pcbnew.VECTOR2I(0,0))
                detached.SetOrientationDegrees(angle)
                box = _authored_rectangle(detached)
                if box is None:
                    break
                pads = {p.GetNumber():p for p in detached.Pads()}
                orientations.append(dict(angle_deg=angle,box=box,
                    supply_offset=xy(pads[supply.GetNumber()]),ground_offset=xy(pads[ground.GetNumber()])))
            if len(orientations)!=4:
                break
            cells.append(dict(id=item['cap_ref'],ideal_loop_mm=tangent['best_loop']['loop_proxy_mm'],orientations=orientations))
            tangents[item['cap_ref']]=tangent
        if len(cells)!=2:
            continue
        reference=shared_pin_reference(owner_box,xy(items[0]['requirement']['pad']),[xy(p) for p in grounds],cells)
        if not reference.get('ok'):
            continue
        reference.update(owner=owner_ref,pin=pin,members=sorted(c['id'] for c in cells),
                         geometry_basis='native_authored_rectangular_courtyard_centerlines')
        for item in items:
            result[(owner_ref,pin,item['cap_ref'])]={'reference':reference,'tangent':tangents[item['cap_ref']]}
    return result
