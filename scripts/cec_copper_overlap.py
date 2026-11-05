"""Exact, provenance-scoped normalization of covered straight-copper prefixes."""
from collections import defaultdict


def trim_covered_prefixes(board, writable_track_uuids):
    """Trim only a generated long leg covered by a wider/equal short prefix.

    Both legs remain, with their UUIDs, widths, layers, nets and lock/group
    ownership intact. The shorter far endpoint becomes the explicit junction.
    Exact integer collinearity proves unchanged copper coverage. This is not a
    near-parallel simplifier, dangling-track remover, or authority to move
    inherited copper. Whole-board electrical/physical admission remains required.
    """
    import pcbnew
    scope = {str(value) for value in writable_track_uuids or ()}
    tracks = sorted((t for t in board.GetTracks() if t.GetClass() == 'PCB_TRACK'),
                    key=lambda t: t.m_Uuid.AsString())
    changes = []
    for _ in range(max(1, 2*len(tracks))):
        ends = defaultdict(list)
        for track in tracks:
            a, b = track.GetStart(), track.GetEnd()
            # Never retain live VECTOR2I aliases across a setter.
            a, b = (int(a.x), int(a.y)), (int(b.x), int(b.y))
            if a == b:
                continue
            for origin, far, at_start in ((a,b,True),(b,a,False)):
                ends[(origin, int(track.GetLayer()), int(track.GetNetCode()))].append(
                    (track, far, at_start))
        changed = False
        for (origin, _layer, _net), rows in ends.items():
            for i, first in enumerate(rows):
                for second in rows[i+1:]:
                    va = (first[1][0]-origin[0], first[1][1]-origin[1])
                    vb = (second[1][0]-origin[0], second[1][1]-origin[1])
                    la, lb = va[0]**2+va[1]**2, vb[0]**2+vb[1]**2
                    if (la == lb or va[0]*vb[1]-va[1]*vb[0] != 0
                            or va[0]*vb[0]+va[1]*vb[1] <= 0):
                        continue
                    short, long = (first, second) if la < lb else (second, first)
                    small, target = short[0], long[0]
                    uid = target.m_Uuid.AsString()
                    if uid not in scope or small.GetWidth() < target.GetWidth():
                        continue
                    new_end = short[1]
                    change = dict(uuid=uid, covering_uuid=small.m_Uuid.AsString(),
                        old_endpoint_nm=list(origin), new_endpoint_nm=list(new_end),
                        at_start=long[2], net=target.GetNetname(),
                        layer=board.GetLayerName(target.GetLayer()),
                        width_nm=int(target.GetWidth()), covering_width_nm=int(small.GetWidth()))
                    if long[2]:
                        target.SetStart(pcbnew.VECTOR2I(*new_end))
                    else:
                        target.SetEnd(pcbnew.VECTOR2I(*new_end))
                    changes.append(change)
                    changed = True
                    break
                if changed:
                    break
            if changed:
                break
        if not changed:
            break
    return dict(changed_count=len(changes), changes=changes, copper_coverage_preserved=True,
                policy='exact-owned-covered-prefix')
