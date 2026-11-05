"""Normalize collinear route coverage without changing the copper union.

No tolerance, polygon approximation, or net-name heuristic is used. A straight
track is a centreline swept by a disk of half its width. A subinterval of that
centreline is redundant only when a same-net/layer track of at least that width
covers it. Trimming to an existing endpoint therefore preserves the complete
union, including rounded caps, not merely centreline connectivity.
"""

from collections import defaultdict
from math import gcd

from cec_native_items import discard_items


def _row(item):
    # PCB_ARC inherits track methods but is not a straight capsule. Vias, arcs,
    # netless graphics and zero-length objects need different proofs.
    if item.GetClass() != "PCB_TRACK" or item.GetNetCode() <= 0:
        return None
    a, b = item.GetStart(), item.GetEnd()
    ax, ay, bx, by = int(a.x), int(a.y), int(b.x), int(b.y)
    dx, dy = bx - ax, by - ay
    divisor = gcd(dx, dy)
    width = int(item.GetWidth())
    if not divisor or width <= 0:
        return None
    ux, uy = dx // divisor, dy // divisor
    if ux < 0 or (ux == 0 and uy < 0):
        ux, uy = -ux, -uy
    ta, tb = ax * ux + ay * uy, bx * ux + by * uy
    return dict(item=item, uuid=str(item.m_Uuid.AsString()),
                key=(int(item.GetNetCode()), int(item.GetLayer()),
                     ux, uy, ux * ay - uy * ax),
                net=str(item.GetNetname()), width=width,
                locked=bool(item.IsLocked()), lo=min(ta, tb), hi=max(ta, tb),
                forward=ta < tb, points={ta: (ax, ay), tb: (bx, by)})


def normalize(board, *, track_uuid_scope=None, protected_uuids=(),
              exclude_nets=(), max_changes=1024):
    """Remove/trim covered unlocked straight segments in one bounded pass.

    Earlier survivors can cover later tracks, never the reverse. Width-first
    order proves all covering segments at least as wide as the candidate;
    locked and out-of-scope objects are immutable even if redundant. Interior
    coverage is deliberately left intact: no splitting or new objects is
    required. Return certificates before permanently destroying native items.
    Callers must not retain track proxies across this mutation and must still
    run their ordinary independent native DRC/admission checks.
    """
    import pcbnew

    if not isinstance(max_changes, int) or isinstance(max_changes, bool) or max_changes < 0:
        raise ValueError("max_changes must be a nonnegative integer")
    scope = None if track_uuid_scope is None else set(track_uuid_scope)
    protected = set(protected_uuids)
    excluded = set(exclude_nets)
    groups = defaultdict(list)
    for item in board.GetTracks():
        row = _row(item)
        if row:
            groups[row["key"]].append(row)
    changes, removed = [], []
    for key in sorted(groups):
        rows = sorted(groups[key], key=lambda r: (
            -r["width"], not r["locked"], -(r["hi"] - r["lo"]), r["uuid"]))
        survivors = []
        for row in rows:
            eligible = (not row["locked"] and row["uuid"] not in protected
                        and row["net"] not in excluded
                        and (scope is None or row["uuid"] in scope))
            if not eligible or len(changes) >= max_changes:
                survivors.append(row)
                continue
            lo, hi = row["lo"], row["hi"]
            covering = [r for r in survivors if r["width"] >= row["width"]
                        and r["lo"] < hi and r["hi"] > lo]
            points = dict(row["points"])
            for cover in covering:
                points.update(cover["points"])
            # Coverage chains may span multiple retained segments. Advancing
            # only to their existing endpoints avoids any coordinate rounding.
            new_lo, new_hi = lo, hi
            for cover in sorted(covering, key=lambda r: (r["lo"], -r["hi"])):
                if cover["lo"] <= new_lo < cover["hi"]:
                    new_lo = min(hi, cover["hi"])
            if new_lo < hi:
                for cover in sorted(covering, key=lambda r: (-r["hi"], r["lo"])):
                    if cover["lo"] < new_hi <= cover["hi"]:
                        new_hi = max(new_lo, cover["lo"])
            if (new_lo, new_hi) == (lo, hi):
                survivors.append(row)
                continue
            deleted = new_lo >= new_hi
            before = [points[lo], points[hi]]
            after = [] if deleted else [points[new_lo], points[new_hi]]
            changes.append(dict(uuid=row["uuid"], net=row["net"],
                layer=int(key[1]), width_nm=row["width"],
                before_xy_nm=before, after_xy_nm=after,
                mode="remove" if deleted else "trim",
                coverage_uuids=sorted(r["uuid"] for r in covering),
                proof="same_line_same_net_layer_at_least_same_width"))
            if deleted:
                removed.append(row["item"])
                continue
            start, end = after if row["forward"] else list(reversed(after))
            row["item"].SetStart(pcbnew.VECTOR2I(*start))
            row["item"].SetEnd(pcbnew.VECTOR2I(*end))
            row.update(lo=new_lo, hi=new_hi, points={new_lo: points[new_lo],
                                                     new_hi: points[new_hi]})
            survivors.append(row)
    if removed:
        discard_items(board, removed)
    if changes:
        board.BuildConnectivity()
    return dict(schema=1, changed=bool(changes), changes=changes,
                removed=len(removed), trimmed=len(changes)-len(removed),
                max_changes=max_changes, copper_union_preserved=True,
                locked_geometry_preserved=True)
