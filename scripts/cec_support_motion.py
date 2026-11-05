"""Shared proposal/admission envelope for bounded route-time support moves.

This is a search filter, never placement or electrical release authority.
Exact physical placement, copper preservation and native grading still follow.
"""
import math

MAX_REFS = 4
MAX_SHIFT_MM = 6.0
MAX_OWNER_COPPER_PADS = 16


def limits(*, max_refs=MAX_REFS, max_shift_mm=MAX_SHIFT_MM, immutable_refs=(),
           max_owner_copper_pads=2):
    if (type(max_refs) is not int or not 1 <= max_refs <= MAX_REFS
            or type(max_shift_mm) not in (int, float)
            or not math.isfinite(max_shift_mm) or not 0 < max_shift_mm <= MAX_SHIFT_MM
            or type(max_owner_copper_pads) is not int
            or not 2 <= max_owner_copper_pads <= MAX_OWNER_COPPER_PADS
            or not isinstance(immutable_refs, (list, tuple, set))
            or any(not isinstance(ref, str) or not ref for ref in immutable_refs)):
        raise ValueError('invalid bounded support motion limits')
    return dict(max_refs=max_refs, max_shift_mm=float(max_shift_mm),
                immutable_refs=sorted(set(immutable_refs)),
                max_owner_copper_pads=max_owner_copper_pads)


def capture(board, target, policy):
    """Capture exact native origins and eligibility once per proposal menu."""
    import pcbnew
    policy = limits(**policy)
    refs = [target.get('ref'), *(target.get('companion_refs') or ())]
    grouped = {item.GetReference() for group in board.Groups()
               for item in group.GetItems() if item.GetClass() == 'FOOTPRINT'}
    members = {}
    for index, ref in enumerate(refs):
        fp = board.FindFootprintByReference(ref or '')
        pads = [p for p in fp.Pads() if p.IsOnCopperLayer()] if fp else []
        # The certified endpoint-owner stage may move one small IC. Its
        # companions remain two-terminal supports; the normal stage still
        # admits only two-terminal owners. This is not release authority.
        pad_limit = policy['max_owner_copper_pads'] if index == 0 else 2
        if (not fp or ref in members or fp.IsLocked() or ref in grouped
                or ref in policy['immutable_refs'] or not 2 <= len(pads) <= pad_limit
                or any(p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD or p.HasHole() for p in pads)):
            return dict(ok=False, reason='immutable_or_out_of_scope_component')
        at = fp.GetPosition()
        members[ref] = (at.x / 1e6, at.y / 1e6)
    if not 1 <= len(members) <= policy['max_refs']:
        return dict(ok=False, reason='outside_bounded_support_scope')
    return dict(ok=True, origin=members[refs[0]], members=members, policy=policy)


def evaluate(domain, candidate):
    """Check displacement of every member, including rotation about the owner."""
    if not domain.get('ok'):
        return dict(ok=False, reason=domain.get('reason'))
    try:
        dx, dy, angle = (float(candidate.get(key, 0))
                         for key in ('dx_mm', 'dy_mm', 'rotation_delta_deg'))
        if not all(math.isfinite(value) for value in (dx, dy, angle)):
            raise ValueError('nonfinite pose')
    except (ValueError, TypeError, OverflowError):
        return dict(ok=False, reason='invalid_support_pose')
    ox, oy = domain['origin']
    cosine, sine = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    movement = {ref: math.hypot(dx + (cosine-1)*(x-ox) + sine*(y-oy),
                               dy - sine*(x-ox) + (cosine-1)*(y-oy))
                for ref, (x, y) in domain['members'].items()}
    ok = all(distance <= domain['policy']['max_shift_mm'] for distance in movement.values())
    return dict(ok=ok, reason='within_support_envelope' if ok else 'support_shift_exceeds_limit',
                movement_mm={ref: round(distance, 6) for ref, distance in movement.items()})


def filter_candidates(board_path, target, candidates, policy):
    import pcbnew
    board = pcbnew.LoadBoard(str(board_path))
    domains, eligible, rejected = {}, [], []
    for candidate in candidates:
        effective = dict(target)
        if candidate.get('mobility_companion_refs') is not None:
            effective['companion_refs'] = list(candidate['mobility_companion_refs'])
        key = tuple(effective.get('companion_refs') or ())
        if key not in domains:
            domains[key] = capture(board, effective, policy)
        proof = evaluate(domains[key], candidate)
        if proof['ok']:
            eligible.append(candidate)
        else:
            rejected.append(dict(candidate=candidate, **proof))
    return dict(eligible=eligible, rejected=rejected, release_authority=False)
