"""Bounded reconstruction of a generated, invalid local POFV landing.

No board identities or hand-authored destinations. Actual overlapping SMD
lands propose seats; native shape, branch, ownership and independent signoff
proofs decide. This module never promotes a board: its caller owns admission.
"""
from __future__ import annotations

import math

MM = 1_000_000


def profile_geometry(board):
    import cec_fab_profile as fab
    name = fab.board_profile_name(board)
    profile = fab.get_profile(name) if name else None
    if not profile or not profile.get('pofv'):
        return None
    drill = float(profile['pofv_drill_min_mm'])
    diameter = drill + 2 * float(profile['pofv_annular_min_mm'])
    return (diameter, drill) if fab.pofv_dimensions(profile, diameter, drill)[0] else None


def plan(board_path, via_uuid, *, max_seats=8, radius_mm=1.5):
    import pcbnew
    import cec_constraints
    import cec_dimension_repair as repair
    import cec_fr
    if (not isinstance(max_seats, int) or max_seats < 0 or max_seats > 8
            or not math.isfinite(radius_mm) or not 0 < radius_mm <= 1.5):
        raise ValueError('invalid bounded local-via search policy')
    board = pcbnew.LoadBoard(str(board_path))
    via = next((v for v in board.GetTracks() if v.GetClass() == 'PCB_VIA'
                and repair.uid(v) == via_uuid), None)
    if via is None:
        return {'eligible': False, 'reason': 'local_via_missing'}
    same, foreign, _allowed = cec_constraints._via_pad_overlaps(board)
    if not any(row['via_uuid'] == via_uuid for row in same):
        return {'eligible': False, 'reason': 'no_live_local_via_assembly_failure'}
    if any(row['via_uuid'] == via_uuid for row in foreign):
        return {'eligible': False, 'reason': 'foreign_pad_contact_requires_topology_review'}
    precision = {net for _kind, p, n in cec_constraints._coupled_pair_names(board)
                 for net in (p, n)} | set(cec_fr._sense_input_nets(board))
    if via.GetNetname() in precision:
        return {'eligible': False, 'reason': 'precision_owner_recompile_required'}
    if int(via.GetViaType()) != int(pcbnew.VIATYPE_THROUGH):
        return {'eligible': False, 'reason': 'non_through_via_requires_stack_owner'}
    geometry = profile_geometry(board)
    if geometry is None:
        return {'eligible': False, 'reason': 'local_pofv_profile_missing'}
    bound = repair.boundary(board, via, max_contact_mm=radius_mm, local_pofv=True)
    if bound['refused']:
        return {'eligible': False, 'reason': 'local_boundary_refused', 'boundary': bound}
    if not bound['pads']:
        return {'eligible': False, 'reason': 'no_overlapping_smd_owner'}
    diameter, drill = (round(value * MM) for value in geometry)
    origin = bound['at_nm']
    candidates = set()
    selected = {p['uuid'] for p in bound['pads']}
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if repair.uid(pad) not in selected:
                continue
            center = (pad.GetPosition().x, pad.GetPosition().y)
            candidates.add(center)
            # Local envelope seats are proposals only, including round/custom
            # lands. The effective native shape must still contain the barrel.
            a = math.radians(pad.GetOrientationDegrees())
            ca, sa = math.cos(a), math.sin(a)
            dx, dy = origin[0] - center[0], origin[1] - center[1]
            u, v = ca * dx - sa * dy, sa * dx + ca * dy
            hx = (pad.GetSize().x - diameter) / 2 - 10_000
            hy = (pad.GetSize().y - diameter) / 2 - 10_000
            if hx < 0 or hy < 0:
                continue
            clamped = (max(-hx, min(hx, u)), max(-hy, min(hy, v)))
            for x, y in (clamped, (-hx, -hy), (-hx, hy), (hx, -hy), (hx, hy)):
                candidates.add((round(center[0] + ca*x + sa*y),
                                round(center[1] - sa*x + ca*y)))
    seats = sorted((p for p in candidates if 0 < math.dist(p, origin) <= radius_mm * MM),
                   key=lambda p: (math.dist(p, origin), p))[:max_seats]
    return {'eligible': bool(seats), 'reason': 'local_smd_seats' if seats else 'no_bounded_seat',
            'target': {'uuid': via_uuid, 'boundary': bound, 'owner_mode': 'local_pofv',
                       'diameter_nm': diameter, 'drill_nm': drill,
                       'seats_nm': [list(p) for p in seats]}}


def rebuild(board_path, via_uuid, *, max_seats=8, radius_mm=1.5):
    import cec_dimension_repair as repair
    planning = plan(board_path, via_uuid, max_seats=max_seats, radius_mm=radius_mm)
    result = {'changed': False, 'plan': planning, 'attempts': []}
    if not planning['eligible']:
        result['reason'] = planning['reason']
        return result
    target = planning['target']
    for seat in target['seats_nm']:
        mutation = repair.mutate(board_path, target, seat)
        result['attempts'].append({'seat_nm': seat, **mutation})
        if mutation['changed']:
            result.update(changed=True, reason='bounded_local_via_rebuilt')
            break
        if mutation['reason'] == 'stale_boundary_or_owner':
            break
    return result
