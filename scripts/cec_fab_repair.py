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
import shutil
import subprocess
import sys
import tempfile

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


def repair_starved_thermal(board, *, fill_prefixes=("gndfill:",)):
    """R6: stop a SUPPLEMENTARY leftover fill from claiming pads it cannot serve.

    Measured on the hub: every `starved_thermal` error is a THT GND pad getting
    one spoke instead of two (or a spoke into an isolated island) from
    `gndfill:In2.Cu` -- the leftover-space GND fill on the SIGNAL inner layer.
    Those pads are NOT poorly connected: In1.Cu is a solid GND plane and a THT
    barrel pierces it. The supplementary fill is simply claiming pads it has no
    room to give proper thermal spokes to.

    So the fill is switched to pad connection NONE: it stays as fill copper
    joined through the stitching vias, and stops forming starved spokes. Applied
    ONLY to zones whose name marks them as this kind of fill -- never to a
    board's real plane, where removing pad connection WOULD strand pads.
    """
    n = 0
    for z in board.Zones():
        if z.GetIsRuleArea():
            continue
        nm = z.GetZoneName() or ""
        if not nm.startswith(fill_prefixes):
            continue
        try:
            import pcbnew
            if z.GetPadConnection() != pcbnew.ZONE_CONNECTION_NONE:
                z.SetPadConnection(pcbnew.ZONE_CONNECTION_NONE)
                n += 1
        except Exception:                                  # noqa: BLE001
            continue
    return n


def repair(board_path, *, sliver_mm=0.10, apply=False, do_priority=True,
           do_island=True, do_starved=True):
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
    rep["starved"] = repair_starved_thermal(b) if do_starved else 0
    if apply:
        for z in b.Zones():
            z.UnFill()
        pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    rep["backtracks"] = repair_backtracks(b)               # LAST: poisons proxies
    if apply:
        b.Save(board_path)
    rep["applied"] = bool(apply)
    return rep


def _admission_snapshot(metrics):
    quality = (metrics.detail.get("route_quality") or {})
    return {
        "drc": int(metrics.drc),
        "unconnected": int(metrics.unconnected),
        "kelvin_ok": bool(metrics.kelvin_ok),
        "diffpair_ok": bool(metrics.diffpair_ok),
        "route_blocking": int(quality.get("blocking_count", 0)),
        "route_advisory": int(quality.get("advisory_count", 0)),
    }


def _score_isolated(board_path):
    """Score in a fresh process so KiCad SWIG registry state cannot leak."""
    code = (
        "import json,sys;sys.path.insert(0,sys.argv[2]);import cec_score;"
        "m=cec_score.score(sys.argv[1]);q=m.detail.get('route_quality') or {};"
        "print('CEC_FAB_SCORE='+json.dumps({"
        "'drc':int(m.drc),'unconnected':int(m.unconnected),"
        "'kelvin_ok':bool(m.kelvin_ok),'diffpair_ok':bool(m.diffpair_ok),"
        "'route_blocking':int(q.get('blocking_count',0)),"
        "'route_advisory':int(q.get('advisory_count',0)),"
        "'objective':float(cec_score.objective(m))},sort_keys=True))")
    proc = subprocess.run(
        [sys.executable, "-c", code, os.path.abspath(board_path), HERE],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    marker = next((line[len("CEC_FAB_SCORE="):]
                   for line in reversed(proc.stdout.splitlines())
                   if line.startswith("CEC_FAB_SCORE=")), None)
    if proc.returncode or marker is None:
        raise RuntimeError("isolated score failed rc=%d: %s" %
                           (proc.returncode, (proc.stderr or proc.stdout)[-1200:]))
    return json.loads(marker)


def _repair_isolated(candidate, *, sliver_mm, kwargs, report_path):
    argv = [sys.executable, os.path.abspath(__file__), candidate,
            "--apply", "--sliver", str(sliver_mm), "--json", report_path]
    if not kwargs.get("do_priority", True):
        argv.append("--no-priority")
    if not kwargs.get("do_starved", True):
        argv.append("--no-starved")
    proc = subprocess.run(argv, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if proc.returncode or not os.path.isfile(report_path):
        raise RuntimeError("isolated repair failed rc=%d: %s" %
                           (proc.returncode, (proc.stderr or proc.stdout)[-1200:]))
    with open(report_path, encoding="utf-8") as handle:
        rows = json.load(handle)
    if not rows:
        raise RuntimeError("isolated repair produced no report")
    return rows[0]


def repair_admitted(board_path, *, sliver_mm=0.10):
    """Try repair slices transactionally and publish only a no-regression winner.

    The old wave publisher applied every repair in one mutation and only scored
    afterwards.  Forensic replay on the Hub showed why that is insufficient:
    segment cleanup safely removed two route artifacts, while zone-priority
    deconfliction in the same call created one new unconnected item.  A single
    combined artifact made the safe improvement inseparable from the regression.

    Evaluate a conservative copper-cleanup slice and the full slice on isolated
    copies, require DRC/connectivity/pair-gate non-regression, and choose the
    lexicographically cleanest accepted result.  The original board remains
    byte-for-byte available until a winner is selected.
    """
    baseline_row = _score_isolated(board_path)
    baseline = {k: baseline_row[k] for k in (
        "drc", "unconnected", "kelvin_ok", "diffpair_ok",
        "route_blocking", "route_advisory")}
    parent = os.path.dirname(os.path.abspath(board_path)) or "."
    work = tempfile.mkdtemp(prefix=".cec-fab-admit-", dir=parent)
    stem = os.path.splitext(os.path.basename(board_path))[0]
    variants = []
    try:
        for name, kwargs in (
                ("copper_cleanup", {"do_priority": False,
                                    "do_starved": False}),
                ("full", {})):
            candidate = os.path.join(work, "%s-%s.kicad_pcb" % (stem, name))
            shutil.copy2(board_path, candidate)
            for ext in (".kicad_pro", ".kicad_dru", ".kicad_prl"):
                source = board_path[:-len(".kicad_pcb")] + ext
                if os.path.isfile(source):
                    shutil.copy2(source, candidate[:-len(".kicad_pcb")] + ext)
            try:
                report_path = os.path.join(work, "%s-%s-repair.json" %
                                           (stem, name))
                changes = _repair_isolated(
                    candidate, sliver_mm=sliver_mm, kwargs=kwargs,
                    report_path=report_path)
                score_row = _score_isolated(candidate)
                snapshot = {k: score_row[k] for k in (
                    "drc", "unconnected", "kelvin_ok", "diffpair_ok",
                    "route_blocking", "route_advisory")}
                safe = (snapshot["drc"] <= baseline["drc"]
                        and snapshot["unconnected"] <= baseline["unconnected"]
                        and (not baseline["kelvin_ok"] or snapshot["kelvin_ok"])
                        and (not baseline["diffpair_ok"] or snapshot["diffpair_ok"])
                        and snapshot["route_blocking"] <= baseline["route_blocking"])
                variants.append({
                    "name": name, "path": candidate, "changes": changes,
                    "metrics": snapshot, "safe": bool(safe),
                    "objective": float(score_row["objective"]),
                })
            except Exception as exc:                         # noqa: BLE001
                variants.append({"name": name, "path": candidate,
                                 "safe": False,
                                 "error": "%s: %s" %
                                          (type(exc).__name__, exc)})

        safe_variants = [row for row in variants if row.get("safe")]
        # Prefer real topology cleanup, then electrical closure, then the
        # ordinary weighted objective.  Include the unchanged baseline as the
        # stable fallback so a neutral rewrite is never published gratuitously.
        baseline_key = (baseline["route_blocking"], baseline["route_advisory"],
                        baseline["drc"], baseline["unconnected"],
                        float(baseline_row["objective"]), "baseline")
        chosen = None
        chosen_key = baseline_key
        for row in safe_variants:
            snap = row["metrics"]
            key = (snap["route_blocking"], snap["route_advisory"],
                   snap["drc"], snap["unconnected"], row["objective"], row["name"])
            if key < chosen_key:
                chosen, chosen_key = row, key
        if chosen is not None:
            shutil.copy2(chosen["path"], board_path)
        return {
            "board": os.path.relpath(board_path),
            "baseline": baseline,
            "variants": [{k: v for k, v in row.items() if k != "path"}
                         for row in variants],
            "adopted": chosen is not None,
            "chosen": chosen["name"] if chosen is not None else "baseline",
            "after": chosen["metrics"] if chosen is not None else baseline,
        }
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("boards", nargs="+")
    ap.add_argument("--sliver", type=float, default=0.10)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--no-priority", action="store_true")
    ap.add_argument("--no-island", action="store_true")
    ap.add_argument("--no-starved", action="store_true")
    ap.add_argument("--json", default="")
    a = ap.parse_args()
    out = []
    for bp in a.boards:
        if not os.path.isfile(bp):
            print("MISSING %s" % bp)
            continue
        r = repair(bp, sliver_mm=a.sliver, apply=a.apply,
                   do_priority=not a.no_priority, do_island=not a.no_island,
                   do_starved=not a.no_starved)
        out.append(r)
        print("%-46s tracks=%-3d backtracks=%-3d min_thick=%-3d islands=%-3d "
              "priority=%-3d starved=%-3d %s"
              % (os.path.basename(bp)[:46], r["track_width"], r["backtracks"],
                 r["min_thickness"], r["island_mode"], r["priority"], r.get("starved", 0),
                 "APPLIED" if r["applied"] else "(dry run)"), flush=True)
    if a.json:
        with open(a.json, "w") as fh:
            json.dump(out, fh, indent=1, default=str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
