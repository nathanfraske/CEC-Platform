"""Keep router-derived physical pair stations intact during collateral eviction.

These are proposal constraints, not routing or release certificates. Deliberate
primary station re-seating retains its own solver; a local bystander eviction
may translate a station but must not silently split or rotate one member.
"""
import hashlib
import math
from pathlib import Path


def station_groups(stations):
    """Transitive, deterministic closure of overlapping physical stations."""
    groups = []
    for station in stations:
        refs = {str(ref) for ref in station.get('physical_refs', ()) if ref}
        if len(refs) < 2:
            continue
        remaining = []
        for group in groups:
            if group & refs:
                refs.update(group)
            else:
                remaining.append(group)
        groups = remaining + [refs]
    return sorted(tuple(sorted(group)) for group in groups)


def from_board(board_path):
    """Use the precision router's actual pair membership, not name heuristics.

    The caller's incumbent is materialized once per round. Capture its identity
    so diagnostics identify the board from which collateral ownership was read.
    An unreadable/changing incumbent cannot yield permission for free eviction.
    """
    import pcbnew
    import cec_precision_route as precision
    path = Path(board_path)
    try:
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        board = pcbnew.LoadBoard(str(path))
        if board is None:
            raise ValueError('incumbent board unloadable')
        stations = [station
                    for pair in precision.derive_coupled_pairs(str(path), board=board)
                    for station in precision._pair_endpoint_stations(board, pair)]
        if hashlib.sha256(path.read_bytes()).hexdigest() != before:
            raise ValueError('incumbent changed during station derivation')
        return dict(ok=True, groups=station_groups(stations), board_sha256=before,
                    scope='collateral proposal restriction; no route admission')
    except Exception as exc:
        return dict(ok=False, groups=[], error=f'{type(exc).__name__}: {exc}')


def complete_eviction(positions, primary, variant, context, *, immovable=()):
    """Complete secondary translations, or refuse an inconsistent transaction.

    Only additions to a primary proposal trigger this rule. Intentional primary
    pair re-seating is not frozen into its old geometry. When a secondary group
    also contains a primary member, every supplied pose must already agree with
    the same translation; never overwrite a deliberate primary transformation.
    All propagated members still face the caller's exact bounds, power, craft,
    pad, courtyard and protected-route checks. This helper admits no geometry.
    """
    result = dict(variant)
    changed = lambda ref: ref not in positions or any(
        not math.isclose(float(a), float(b), abs_tol=1e-8, rel_tol=0.0)
        for a, b in zip(result[ref], positions[ref]))
    secondary = {ref for ref in result if ref not in primary and changed(ref)}
    if not secondary:
        return dict(ok=True, placements=result, added_refs=[], groups=[])
    if not context.get('ok'):
        return dict(ok=False, reason='station_context_unavailable')
    locked = set(immovable)
    affected = [group for group in context.get('groups', ())
                if secondary.intersection(group)]
    added = []
    for group in affected:
        if any(ref not in positions for ref in group):
            return dict(ok=False, reason='station_member_missing', refs=list(group))
        if locked.intersection(group):
            return dict(ok=False, reason='station_member_immovable', refs=list(group))
        ref = min(secondary.intersection(group))
        dx, dy = (float(result[ref][i]) - float(positions[ref][i]) for i in (0, 1))
        for member in group:
            x, y, rotation = positions[member]
            target = (x + dx, y + dy, rotation)
            pose = result.get(member, target)
            # Eviction is translation-only. The primary pair solver owns any
            # deliberate rotations or changes to the internal lane spacing.
            if (not all(math.isfinite(float(value)) for value in pose)
                    or not all(math.isclose(float(pose[i]), target[i],
                        abs_tol=1e-8, rel_tol=0.0) for i in (0, 1))
                    or abs((float(pose[2]) - rotation + 180.) % 360. - 180.) > 1e-8):
                return dict(ok=False, reason='station_transform_conflict', refs=list(group))
            if member not in result:
                added.append(member)
            result[member] = target
    return dict(ok=True, placements=result, added_refs=sorted(added),
                groups=[list(group) for group in affected])
