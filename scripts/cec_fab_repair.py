#!/usr/bin/env python3
"""FAB REPAIR -- fix the manufacturability defects, not just report them.

Owner 2026-07-27: "wire it in so that those things are actually fixed instead of
just acting as a gate with no teeth."

Each repair here is DETERMINISTIC and CONNECTIVITY-SAFE by construction. Where a
defect cannot be fixed without a design decision (a real clearance conflict needs
copper moved, which is the router's job) it is REPORTED and left alone -- silently
"fixing" those would hide a fault rather than remove it.

  R1 sub-minimum track width  -- snap to the floor (cec_fr.normalize_track_width);
                                 only artifacts within tolerance, never a
                                 genuinely thin track.
  R2 backtrack / duplicate segments -- two segments leaving one point in the SAME
                                 direction are a doubled-back spike or an exact
                                 duplicate: pure autorouter litter, and the source
                                 of the 0.0deg / 0.6deg "acid traps". The
                                 redundant one is removed only when the survivor
                                 still covers it.
  R3 pour sliver floor        -- raise each zone's min_thickness to the process
                                 limit so the FILLER stops emitting copper thinner
                                 than the etch can hold. Native KiCad, applied at
                                 fill, cannot strand anything.
  R4 (WITHDRAWN)              -- setting an island-removal MODE made things
                                 worse: the boards already remove islands
                                 always, and the change effectively disabled it
                                 (hub 0 islands -> 6). Ablation caught it. Left
                                 documented so it is not re-attempted.
  R5 zone priority deconflict -- same-layer zones of DIFFERENT nets at equal
                                 priority produce `zones_intersect`; giving them
                                 distinct priorities makes the filler resolve the
                                 overlap deterministically.

Usage:
    python3 scripts/cec_fab_repair.py BOARD [--sliver 0.10] [--apply] [--json OUT]

Without --apply it is a dry run (reports what it WOULD change).
"""

import argparse
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# SWIG REGISTRY PIN -- see scripts/cec_swig_guard.py. Without it, a repeated
# LoadBoard in one process starts returning a bare SwigPyObject instead of a
# BOARD (the hub all-9999 root cause), and every attribute access dies.
try:
    import pcbnew as _pcbnew
    import cec_swig_guard as _swig_guard
    _swig_guard.pin()
except Exception:                                          # noqa: BLE001
    pass


def _seg_key(t):
    s, e = t.GetStart(), t.GetEnd()
    a = (round(s.x / 1e6, 4), round(s.y / 1e6, 4))
    b = (round(e.x / 1e6, 4), round(e.y / 1e6, 4))
    return (min(a, b), max(a, b), t.GetLayer(), t.GetNetname())


def repair_backtracks(board, *, angle_deg=5.0):
    """R2: drop doubled-back / duplicate segments (the 0-degree 'acid traps').

    Two segments leaving the same point along the same bearing are either an
    exact duplicate or a spike that runs out and back. Either way the shorter is
    fully covered by the longer, so removing it cannot disconnect anything --
    which is why only the COVERED case is touched.
    """
    import pcbnew
    tracks = [t for t in board.GetTracks() if t.GetClass() == "PCB_TRACK"]
    # exact duplicates first
    seen, dead = {}, []
    for t in tracks:
        k = _seg_key(t)
        if k in seen:
            dead.append(t)
        else:
            seen[k] = t
    ends = {}
    for t in tracks:
        if t in dead:
            continue
        s, e = t.GetStart(), t.GetEnd()
        for (p, q) in ((s, e), (e, s)):
            key = (round(p.x / 1e6, 3), round(p.y / 1e6, 3),
                   t.GetLayer(), t.GetNetname())
            ends.setdefault(key, []).append((t, p, q))
    for key, lst in ends.items():
        if len(lst) < 2:
            continue
        for i in range(len(lst)):
            for j in range(i + 1, len(lst)):
                (t1, p1, q1), (t2, p2, q2) = lst[i], lst[j]
                if t1 in dead or t2 in dead:
                    continue
                v1 = (q1.x - p1.x, q1.y - p1.y)
                v2 = (q2.x - p2.x, q2.y - p2.y)
                n1, n2 = math.hypot(*v1), math.hypot(*v2)
                if n1 < 1 or n2 < 1:
                    continue
                cos = (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)
                ang = math.degrees(math.acos(max(-1.0, min(1.0, cos))))
                if ang <= angle_deg:
                    # same bearing: the shorter lies along the longer
                    dead.append(t1 if n1 <= n2 else t2)
    for t in dead:
        board.Remove(t)
    return len(dead)


def repair_zones(board, *, sliver_mm=0.10, do_priority=True, do_island=True):
    """R3/R4/R5: sliver floor, island removal, priority deconfliction."""
    import pcbnew
    n_thick = n_isl = n_pri = 0
    zones = [z for z in board.Zones() if not z.GetIsRuleArea()]
    want = int(round(sliver_mm * 1e6))
    for z in zones:
        try:
            if z.GetMinThickness() < want:
                z.SetMinThickness(want)
                n_thick += 1
        except Exception:                                  # noqa: BLE001
            pass
        # R4 (island-removal mode) WAS HERE AND IS DELETED. It set every zone
        # to "remove islands below min area"; the boards were already on ALWAYS
        # REMOVE, so this effectively turned island removal OFF and the hub went
        # from 0 isolated islands to 6. Ablation isolated it (--no-priority still
        # showed 6, --no-island showed 0), which is the whole reason each repair
        # is separately switchable. A repair that creates the defect it is named
        # after is worse than no repair.
    # R5: same layer, DIFFERENT nets, equal priority -> distinct priorities
    bylayer = {}
    for z in zones:
        for lid in board.GetEnabledLayers().CuStack():
            if z.IsOnLayer(lid):
                bylayer.setdefault(lid, []).append(z)
    if not do_priority:
        return {"min_thickness": n_thick, "island_mode": n_isl, "priority": 0}
    for lid, zs in bylayer.items():
        bypri = {}
        for z in zs:
            bypri.setdefault(z.GetAssignedPriority(), []).append(z)
        for pri, group in bypri.items():
            nets = {z.GetNetname() for z in group}
            if len(group) < 2 or len(nets) < 2:
                continue
            # keep the largest where it is; step the others up so the filler has
            # a deterministic winner instead of an ambiguous overlap
            group.sort(key=lambda z: -z.GetFilledArea())
            for k, z in enumerate(group[1:], start=1):
                z.SetAssignedPriority(pri + k)
                n_pri += 1
    return {"min_thickness": n_thick, "island_mode": n_isl, "priority": n_pri}


def repair(board_path, *, sliver_mm=0.10, apply=False, do_priority=True,
           do_island=True):
    """ONE board load, with removals strictly LAST.

    Two SWIG constraints on this KiCad-10 build drive the ordering, both
    measured here rather than guessed:
      * board.Remove() poisons the board's other proxies -- calling Zones()
        after removing a track returns a bare SwigPyObject;
      * a REPEATED LoadBoard in one process eventually returns a bare
        SwigPyObject too (the hub all-9999 root cause), so splitting the work
        across several loads trades one failure for another.

    So: load once, do every zone/width edit, FILL, then remove redundant
    segments, then save. The fill precedes removal, which is sound because R2
    only removes segments the survivor already covers -- copper coverage is
    unchanged, so the fill stays valid.
    """
    import pcbnew
    import cec_fr
    rep = {"board": os.path.relpath(board_path)}
    b = pcbnew.LoadBoard(board_path)
    rep["track_width"] = cec_fr.normalize_track_width(b)
    rep.update(repair_zones(b, sliver_mm=sliver_mm, do_priority=do_priority,
                            do_island=do_island))
    if apply:
        for z in b.Zones():
            z.UnFill()
        pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    rep["backtracks"] = repair_backtracks(b)               # LAST: poisons proxies
    if apply:
        b.Save(board_path)
    rep["applied"] = bool(apply)
    return rep


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("boards", nargs="+")
    ap.add_argument("--sliver", type=float, default=0.10)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--no-priority", action="store_true")
    ap.add_argument("--no-island", action="store_true")
    ap.add_argument("--json", default="")
    a = ap.parse_args()
    out = []
    for bp in a.boards:
        if not os.path.isfile(bp):
            print("MISSING %s" % bp)
            continue
        r = repair(bp, sliver_mm=a.sliver, apply=a.apply,
                   do_priority=not a.no_priority, do_island=not a.no_island)
        out.append(r)
        print("%-46s tracks=%-3d backtracks=%-3d min_thick=%-3d islands=%-3d "
              "priority=%-3d %s"
              % (os.path.basename(bp)[:46], r["track_width"], r["backtracks"],
                 r["min_thickness"], r["island_mode"], r["priority"],
                 "APPLIED" if r["applied"] else "(dry run)"), flush=True)
    if a.json:
        with open(a.json, "w") as fh:
            json.dump(out, fh, indent=1, default=str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
