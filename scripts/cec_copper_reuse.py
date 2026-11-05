"""Exact reuse of retained straight copper, without changing any source item.

Subtract only collinear centre-line intervals carried by a same-net, same-layer
straight segment at least as wide as the proposal. Thus the entire omitted
capsule is already present in native copper. Arcs, pads, fills, drills, nearby
metal and skinny traces confer no authority here. Connectivity, craft, current
and field receiving remain independent obligations of the calling constructor.
"""
from __future__ import annotations


def _point(value):
    if (not isinstance(value, (list, tuple)) or len(value) != 2
            or any(isinstance(n, bool) or not isinstance(n, int) for n in value)):
        raise ValueError('integer_native_point_required')
    return tuple(value)


def _validate(row):
    if not isinstance(row, dict) or not isinstance(row.get('net'), str) or not row['net']:
        raise ValueError('exact_net_required')
    for key in ('layer', 'width_nm'):
        if isinstance(row.get(key), bool) or not isinstance(row.get(key), int):
            raise ValueError('integer_native_' + key + '_required')
    if row['width_nm'] <= 0:
        raise ValueError('positive_native_width_required')
    return _point(row['start_nm']), _point(row['end_nm'])


class RetainedCopper:
    """Bounded index of an immutable native straight-track inventory."""
    def __init__(self, retained, *, max_items=8192):
        self.by_net_layer = {}
        for index, row in enumerate(retained):
            if index >= max_items:
                raise ValueError('retained_copper_inventory_budget')
            a, b = _validate(row)
            if a == b:
                continue
            self.by_net_layer.setdefault((row['net'], row['layer']), []).append(
                (a, b, row['width_nm'], row.get('uuid')))

    def subtract(self, proposed, *, max_checks=262144, max_proposed=512):
        """Return uncovered proposal primitives in their original direction.

        Integer collinearity is mandatory, without a snapping tolerance. Cuts
        occur at retained segment endpoints on the same exact line. The result
        plus retained copper has the identical material union as the original
        proposal plus retained copper; this is never a virtual connection.
        """
        result, checks, reused, changed = [], 0, set(), 0
        input_count = 0
        for index, row in enumerate(proposed):
            if index >= max_proposed:
                raise ValueError('copper_reuse_proposal_budget')
            input_count += 1
            a, b = _validate(row)
            if a == b:
                result.append(dict(row))
                continue
            dx, dy = b[0]-a[0], b[1]-a[1]
            axis = 0 if abs(dx) >= abs(dy) else 1
            sign = 1 if b[axis] > a[axis] else -1
            extent = abs(b[axis]-a[axis])
            covered = []
            for c, d, width, uid in self.by_net_layer.get((row['net'], row['layer']), ()):
                checks += 1
                if checks > max_checks:
                    raise ValueError('copper_reuse_intersection_budget')
                if width < row['width_nm']:
                    continue
                if ((c[0]-a[0])*dy != (c[1]-a[1])*dx
                        or (d[0]-a[0])*dy != (d[1]-a[1])*dx):
                    continue
                lo, hi = sorted((sign*(c[axis]-a[axis]), sign*(d[axis]-a[axis])))
                lo, hi = max(0, lo), min(extent, hi)
                if lo < hi:
                    covered.append((lo, hi))
                    if uid:reused.add(uid)
            if not covered:
                result.append(dict(row))
                continue
            changed += 1
            merged = []
            for lo, hi in sorted(covered):
                if merged and lo <= merged[-1][1]:
                    merged[-1] = (merged[-1][0], max(hi, merged[-1][1]))
                else:
                    merged.append((lo, hi))
            def point(t):
                out = []
                for origin, delta in zip(a, (dx, dy)):
                    offset, remainder = divmod(delta*t, extent)
                    if remainder:
                        raise ValueError('nonintegral_retained_endpoint')
                    out.append(origin+offset)
                return out
            cursor = 0
            for lo, hi in [*merged, (extent, extent)]:
                if cursor < lo:
                    result.append(dict(row, start_nm=point(cursor), end_nm=point(lo)))
                cursor = max(cursor, hi)
        return result, dict(complete=True, changed_segments=changed,
            proposed_segments=input_count, emitted_segments=len(result),
            intersection_checks=checks, reused_native_uuids=sorted(reused),
            source_mutated=False, inferred_pad_or_barrel_connection=False,
            release_authority=False)


def native_inventory(board):
    """Read only actual native straight tracks. Unsupported shapes stay fixed."""
    for track in board.GetTracks():
        if track.GetClass() != 'PCB_TRACK' or not track.GetNetname():
            continue
        a, b = track.GetStart(), track.GetEnd()
        yield dict(net=str(track.GetNetname()), layer=int(track.GetLayer()),
            start_nm=[int(a.x), int(a.y)], end_nm=[int(b.x), int(b.y)],
            width_nm=int(track.GetWidth()), uuid=str(track.m_Uuid.AsString()))


def normalize_native_ops(board, ops, net, *, inventory=None):
    """Bridge/last-mile adapter. Keep all proposed vias and original ordering."""
    retained = inventory or RetainedCopper(native_inventory(board))
    result, changed, reused = [], 0, set()
    for op in ops:
        if op[0] == 'via':
            result.append(op)
            continue
        _kind, a, b, width, layer = op
        rows, proof = retained.subtract([dict(net=net, layer=int(layer),
            start_nm=[int(a.x), int(a.y)], end_nm=[int(b.x), int(b.y)], width_nm=int(width))])
        changed += proof['changed_segments']
        reused.update(proof['reused_native_uuids'])
        for row in rows:
            # Construct through the native point type already owned by the
            # caller; this module's integer core needs no KiCad dependency.
            result.append((_kind, type(a)(*row['start_nm']), type(b)(*row['end_nm']), width, layer))
    return result, dict(complete=True, changed_segments=changed,
        reused_native_uuids=sorted(reused),source_mutated=False)
