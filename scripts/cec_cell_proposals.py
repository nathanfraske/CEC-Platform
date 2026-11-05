"""Deterministic ranking of measured local-cell proposals, never admission."""
import math


def ranked_joint_proposals(proposals, incumbent):
    """Compare complete cell poses across orientations before probe truncation.

    The joint solver ranks each orientation independently. Concatenating those
    menus makes a bounded downstream probe depend on orientation enumeration,
    rather than the already-measured hard excess. Keep every alternative but
    prefer zero-eviction cells, then lower joint excess, then smaller movement.
    Unknown/malformed scores carry no proof and retain their relative order at
    the end. Geometry, copper, and electrical admission remain mandatory.
    """
    def key(move):
        score = move.get('joint_rank')
        try:
            if not isinstance(score, (list, tuple)) or len(score) != 3:
                raise ValueError('missing joint rank')
            score = tuple(float(v) for v in score)
            if any(not math.isfinite(v) or v < 0 for v in score):
                raise ValueError('invalid joint rank')
            distance, rotation = 0., 0.
            for ref, pose in move['placements'].items():
                old = incumbent[ref]
                values = tuple(float(v) for v in (*pose[:3], *old[:3]))
                if len(values) != 6 or not all(math.isfinite(v) for v in values):
                    raise ValueError('invalid pose')
                distance += math.hypot(values[0]-values[3], values[1]-values[4])
                rotation += abs((values[2]-values[5]+180.) % 360.-180.)
            blockers = move.get('external_blockers')
            if not isinstance(blockers, (tuple, list)):
                raise ValueError('missing blocker evidence')
            return (0, len(set(blockers)), *score,
                    round(distance, 6), round(rotation, 6))
        except (KeyError, TypeError, ValueError, OverflowError):
            return (1,)

    return sorted(proposals, key=key)
