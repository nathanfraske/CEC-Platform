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
  R7 sliver-only orthofill   -- retire a pipeline-generated ``orthofill:`` zone
                                 only when every nonempty filled component is
                                 thinner than the process floor. Electrical,
                                 topology, and fab admission still decide whether
                                 that redundant filler can be published.

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
    """R2: collapse exact overlapping copper without deleting graph nodes.

    A common generated artifact is two collinear segments leaving one vertex,
    with the shorter endpoint used by another route segment.  Deleting the
    shorter copper is geometrically harmless but erases that explicit graph
    node; KiCad then reports the attached segment as dangling even though it
    touches the interior of the survivor.  Preserve the shorter segment and
    trim the longer one's overlapping endpoint to the shorter endpoint.  The
    copper union is unchanged, the junction remains explicit, and no route is
    specialized by net or board.  Near-collinear forks are not proof of overlap
    and are left for transactional rerouting.
    """
    tracks = [t for t in board.GetTracks() if t.GetClass() == "PCB_TRACK"]
    by_uuid = {t.m_Uuid.AsString(): t for t in tracks}
    dead = set()
    collapsed = 0
    tolerance_nm = 1_000                             # one micron geometric proof

    # Rebuild the endpoint index after every trim; one collapse can expose an
    # exact duplicate or a second contained prefix.  Work is bounded by the
    # finite segment count and each pass either trims one segment or retires one
    # duplicate.
    for _pass in range(max(1, len(tracks) * 2)):
        active = [t for uid, t in by_uuid.items() if uid not in dead]
        seen = {}
        duplicate_found = False
        for t in active:
            key = _seg_key(t)
            prior = seen.get(key)
            if prior is None:
                seen[key] = t
                continue
            # Prefer retaining authored/locked copper when only one duplicate
            # is locked; otherwise deterministic UUID order chooses survivor.
            pair = sorted((prior, t), key=lambda item: (
                not item.IsLocked(), item.m_Uuid.AsString()))
            survivor, victim = pair[0], pair[1]
            dead.add(victim.m_Uuid.AsString())
            seen[key] = survivor
            duplicate_found = True
            break
        if duplicate_found:
            continue

        ends = {}
        for t in active:
            s, e = t.GetStart(), t.GetEnd()
            for p, q, at_start in ((s, e, True), (e, s, False)):
                key = (round(p.x / 1e6, 4), round(p.y / 1e6, 4),
                       t.GetLayer(), t.GetNetname())
                ends.setdefault(key, []).append((t, p, q, at_start))

        changed = False
        for lst in ends.values():
            if len(lst) < 2:
                continue
            for i in range(len(lst)):
                for j in range(i + 1, len(lst)):
                    first, second = lst[i], lst[j]
                    t1, p1, q1, _start1 = first
                    t2, p2, q2, _start2 = second
                    if t1.GetWidth() != t2.GetWidth():
                        continue
                    v1 = (q1.x - p1.x, q1.y - p1.y)
                    v2 = (q2.x - p2.x, q2.y - p2.y)
                    n1, n2 = math.hypot(*v1), math.hypot(*v2)
                    if n1 < tolerance_nm or n2 < tolerance_nm:
                        continue
                    dot = v1[0] * v2[0] + v1[1] * v2[1]
                    if dot <= 0:
                        continue
                    cosang = dot / (n1 * n2)
                    angle = math.degrees(math.acos(
                        max(-1.0, min(1.0, cosang))))
                    # Angular similarity alone caused the original regression:
                    # a shallow fork is not overlapping copper.  Require the
                    # far endpoint's perpendicular distance from the other
                    # segment's infinite line to be within one micron too.
                    perpendicular = abs(v1[0] * v2[1] - v1[1] * v2[0]) / max(n1, n2)
                    if angle > angle_deg or perpendicular > tolerance_nm:
                        continue
                    if abs(n1 - n2) <= tolerance_nm:
                        continue
                    short, long = (first, second) if n1 < n2 else (second, first)
                    _short_t, _origin, short_far, _short_at_start = short
                    long_t, _long_origin, _long_far, long_at_start = long
                    # Trim the long segment to begin at the explicit shorter
                    # endpoint.  Keeping the short prefix preserves any branch,
                    # pad, or via attached there and leaves the copper union
                    # byte-for-byte equivalent geometrically.
                    if long_at_start:
                        long_t.SetStart(short_far)
                    else:
                        long_t.SetEnd(short_far)
                    collapsed += 1
                    changed = True
                    break
                if changed:
                    break
            if changed:
                break
        if not changed:
            break

    for uid in sorted(dead):
        t = by_uuid[uid]
        board.Remove(t)
    return collapsed + len(dead)


def repair_acute_vertices(board, *, angle_min_deg=5.0,
                          angle_max_deg=60.0):
    """R2b: relocate an unanchored acute vertex onto a canonical path.

    A degree-two vertex that is not inside a same-net pad/via is pure route
    geometry.  Move it between the same two outer endpoints so one leg is 45
    degrees and the other is cardinal.  Connectivity, width, layer, net, lock
    state, and both track UUIDs are retained.  Same-net land-covered junctions
    are already solid copper, and coupled pairs require coordinated treatment,
    so both are deliberately excluded.  Final transactional DRC still decides
    whether obstacle clearance admits the new local path.
    """
    import pcbnew
    import cec_fr

    tracks = [t for t in board.GetTracks() if t.GetClass() == "PCB_TRACK"]
    excluded_nets = set(cec_fr.coupled_pair_nets(board))
    ends = {}
    for track in tracks:
        start, end = track.GetStart(), track.GetEnd()
        for point, other, at_start in (
                (start, end, True), (end, start, False)):
            key = (round(point.x / 1e6, 4), round(point.y / 1e6, 4),
                   track.GetLayer(), track.GetNetname())
            ends.setdefault(key, []).append(
                (track, point, other, at_start))

    changed = 0
    used = set()
    for (_x, _y, layer, net), rows in sorted(ends.items()):
        if len(rows) != 2 or net in excluded_nets:
            continue
        first, second = rows
        t1, common, outer1, first_at_start = first
        t2, _common2, outer2, second_at_start = second
        ids = {t1.m_Uuid.AsString(), t2.m_Uuid.AsString()}
        if ids & used or t1.GetWidth() != t2.GetWidth():
            continue
        v1 = (outer1.x - common.x, outer1.y - common.y)
        v2 = (outer2.x - common.x, outer2.y - common.y)
        n1, n2 = math.hypot(*v1), math.hypot(*v2)
        if n1 < 1 or n2 < 1:
            continue
        cosine = (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)
        angle = math.degrees(math.acos(max(-1.0, min(1.0, cosine))))
        if not (angle_min_deg < angle < angle_max_deg):
            continue

        # A same-net land makes this a solid-copper junction rather than an
        # etched concavity.  Foreign or merely adjacent lands do not qualify.
        anchored = False
        for fp in board.GetFootprints():
            for pad in fp.Pads():
                if pad.GetNetname() != net or not pad.IsOnLayer(layer):
                    continue
                try:
                    if pad.GetEffectiveShape(layer).Collide(common, 0):
                        anchored = True
                        break
                except Exception:                          # noqa: BLE001
                    continue
            if anchored:
                break
        if not anchored:
            for item in board.GetTracks():
                if (item.GetClass() == "PCB_VIA"
                        and item.GetNetname() == net
                        and item.IsOnLayer(layer)):
                    pos = item.GetPosition()
                    if (abs(pos.x - common.x) <= 1_000
                            and abs(pos.y - common.y) <= 1_000):
                        anchored = True
                        break
        if anchored:
            continue

        dx, dy = outer2.x - outer1.x, outer2.y - outer1.y
        ax, ay = abs(dx), abs(dy)
        if ax < 1 or ay < 1:
            # Aligned outer endpoints are better handled by the collinear
            # graph cleanup; avoid manufacturing a zero-length leg here.
            continue
        sx = 1 if dx > 0 else -1
        sy = 1 if dy > 0 else -1
        diagonal = min(ax, ay)
        bend = pcbnew.VECTOR2I(
            outer1.x + sx * diagonal,
            outer1.y + sy * diagonal)
        if bend == outer1 or bend == outer2 or bend == common:
            continue
        if first_at_start:
            t1.SetStart(bend)
        else:
            t1.SetEnd(bend)
        if second_at_start:
            t2.SetStart(bend)
        else:
            t2.SetEnd(bend)
        used.update(ids)
        changed += 1
    return changed


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


def sliver_only_orthofill_zones(board, *, sliver_mm=0.10):
    """Return generated filler zones made entirely of sub-process fragments."""
    from shapely.geometry import Polygon

    candidates = []
    radius = float(sliver_mm) / 2.0
    for zone in board.Zones():
        if zone.GetIsRuleArea():
            continue
        name = zone.GetZoneName() or ""
        if not name.startswith("orthofill:"):
            continue
        total = slivers = 0
        for layer in board.GetEnabledLayers().CuStack():
            if not zone.IsOnLayer(layer):
                continue
            try:
                source = zone.GetFilledPolysList(layer)
            except Exception:                              # noqa: BLE001
                continue
            for index in range(source.OutlineCount()):
                outline = source.Outline(index)
                points = [(outline.CPoint(k).x / 1e6,
                           outline.CPoint(k).y / 1e6)
                          for k in range(outline.PointCount())]
                if len(points) < 3:
                    continue
                geometry = Polygon(points).buffer(0)
                if geometry.is_empty or geometry.area <= 0:
                    continue
                total += 1
                if geometry.buffer(-radius).is_empty:
                    slivers += 1
        if total and slivers == total:
            candidates.append(zone)
    return candidates


def repair_sliver_only_orthofill(board_path, *, sliver_mm=0.10,
                                 apply=False):
    """Remove only all-sliver generated filler zones from one board load."""
    import pcbnew

    board = pcbnew.LoadBoard(board_path)
    zones = sliver_only_orthofill_zones(board, sliver_mm=sliver_mm)
    names = sorted(zone.GetZoneName() or "" for zone in zones)
    if apply:
        # No proxy is accessed after the removals except Save(), avoiding the
        # KiCad SWIG invalidation that motivated the isolated repair process.
        for zone in zones:
            board.Remove(zone)
        board.Save(board_path)
    return {"board": os.path.relpath(board_path),
            "sliver_zones_removed": len(zones),
            "zone_names": names, "applied": bool(apply)}


def repair(board_path, *, sliver_mm=0.10, apply=False, do_priority=True,
           do_island=True, do_starved=True, do_acute=True,
           do_backtrack=True):
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
    rep["acute_vertices"] = repair_acute_vertices(b) if do_acute else 0
    if apply:
        for z in b.Zones():
            z.UnFill()
        pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    rep["backtracks"] = (repair_backtracks(b) if do_backtrack else 0)
    # Backtrack cleanup is LAST: retiring an exact duplicate poisons proxies.
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
        "import json,sys;sys.path.insert(0,sys.argv[2]);"
        "import cec_score,cec_stage_admission;"
        "m=cec_score.score(sys.argv[1]);q=m.detail.get('route_quality') or {};"
        "s=cec_stage_admission.snapshot(m);s.update({"
        "'route_blocking':int(q.get('blocking_count',0)),"
        "'route_advisory':int(q.get('advisory_count',0)),"
        "'objective':float(cec_score.objective(m))});"
        "print('CEC_FAB_SCORE='+json.dumps(s,sort_keys=True))")
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


def _fab_isolated(board_path):
    """Run the independent fabrication authority in a fresh process."""
    code = (
        "import json,sys;sys.path.insert(0,sys.argv[2]);"
        "import cec_fab_check as f;"
        "oz=f.board_outer_copper_oz(sys.argv[1]);"
        "r=f.check(sys.argv[1],'jlcpcb',oz,True);"
        "print('CEC_FAB='+json.dumps({"
        "'fab_blocking':int(f.blocking_count(r)),"
        "'fab_drc':int(r.get('drc_total',0)),"
        "'fab_unconnected':int(r.get('unconnected',0)),"
        "'fab_slivers':len(r.get('slivers') or ()),"
        "'fab_islands':len(r.get('islands') or ()),"
        "'fab_acid_traps':len(r.get('acid_traps') or ()),"
        "'fab_drill_aspect':len(r.get('drill_aspect') or ())},"
        "sort_keys=True))")
    proc = subprocess.run(
        [sys.executable, "-c", code, os.path.abspath(board_path), HERE],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    marker = next((line[len("CEC_FAB="):]
                   for line in reversed(proc.stdout.splitlines())
                   if line.startswith("CEC_FAB=")), None)
    if proc.returncode or marker is None:
        raise RuntimeError("isolated fab audit failed rc=%d: %s" %
                           (proc.returncode,
                            (proc.stderr or proc.stdout)[-1200:]))
    return json.loads(marker)


def _foreign_isolated(board_path):
    """Measure fabricated high-current-pour ownership in an isolated worker.

    A derived shunt corridor is a planning reservation, not copper present in
    Gerbers.  Final repair admission therefore uses the actual laid zone
    outlines.  Current cross-section and thermal gates independently prove
    that an orthogonal hook around a reserved planning rectangle remains
    adequate.
    """
    import cec_pour_clearance

    report = cec_pour_clearance.inspect_laid_file(board_path)
    status = str(report.get("status") or "error")
    parts = int(report.get("n_parts", 0) or 0)
    tracks = int(report.get("n_tracks", 0) or 0)
    vias = int(report.get("n_vias", 0) or 0)
    return {
        "foreign_status": status,
        "foreign_parts": parts,
        "foreign_tracks": tracks,
        "foreign_vias": vias,
        # An analysis error is itself blocking; otherwise every convicted
        # primitive is a blocker.  Keeping the aggregate explicit gives the
        # transactional selector one stable lexicographic term.
        "foreign_blocking": (1 if status == "error"
                             else parts + tracks + vias),
    }


def _repair_isolated(candidate, *, sliver_mm, kwargs, report_path):
    argv = [sys.executable, os.path.abspath(__file__), candidate,
            "--apply", "--sliver", str(sliver_mm), "--json", report_path]
    if not kwargs.get("do_priority", True):
        argv.append("--no-priority")
    if not kwargs.get("do_starved", True):
        argv.append("--no-starved")
    if not kwargs.get("do_acute", True):
        argv.append("--no-acute")
    if not kwargs.get("do_backtrack", True):
        argv.append("--no-backtrack")
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


def _sliver_repair_isolated(candidate, *, sliver_mm, report_path):
    argv = [sys.executable, os.path.abspath(__file__), candidate,
            "--apply", "--sliver", str(sliver_mm),
            "--sliver-only-orthofill", "--json", report_path]
    proc = subprocess.run(argv, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if proc.returncode or not os.path.isfile(report_path):
        raise RuntimeError("isolated sliver repair failed rc=%d: %s" %
                           (proc.returncode,
                            (proc.stderr or proc.stdout)[-1200:]))
    with open(report_path, encoding="utf-8") as handle:
        rows = json.load(handle)
    if not rows:
        raise RuntimeError("isolated sliver repair produced no report")
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
    baseline_row.update(_fab_isolated(board_path))
    baseline_row.update(_foreign_isolated(board_path))
    baseline = dict(baseline_row)
    parent = os.path.dirname(os.path.abspath(board_path)) or "."
    work = tempfile.mkdtemp(prefix=".cec-fab-admit-", dir=parent)
    stem = os.path.splitext(os.path.basename(board_path))[0]
    variants = []
    try:
        for name, kwargs in (
                ("copper_cleanup", {"do_priority": False,
                                    "do_starved": False,
                                    "do_acute": False}),
                ("track_polish", {"do_priority": False,
                                  "do_starved": False}),
                ("fab_polish", {"do_priority": False,
                                "do_starved": False,
                                "sliver_cleanup": True}),
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
                if kwargs.get("sliver_cleanup"):
                    sliver_report = os.path.join(
                        work, "%s-%s-slivers.json" % (stem, name))
                    changes = dict(changes)
                    changes["sliver_cleanup"] = _sliver_repair_isolated(
                        candidate, sliver_mm=sliver_mm,
                        report_path=sliver_report)
                score_row = _score_isolated(candidate)
                score_row.update(_fab_isolated(candidate))
                score_row.update(_foreign_isolated(candidate))
                snapshot = dict(score_row)
                # Import here rather than at module load so dry-run repair
                # primitives stay usable on hosts without the scoring stack.
                import cec_stage_admission
                admission = cec_stage_admission.evaluate(
                    baseline, snapshot)
                safe = (admission["accepted"]
                        and snapshot["route_blocking"]
                        <= baseline["route_blocking"]
                        and snapshot["foreign_status"] != "error"
                        and snapshot["foreign_blocking"]
                        <= baseline["foreign_blocking"]
                        and snapshot["fab_blocking"]
                        <= baseline["fab_blocking"]
                        and snapshot["fab_drc"] <= baseline["fab_drc"]
                        and snapshot["fab_unconnected"]
                        <= baseline["fab_unconnected"])
                variants.append({
                    "name": name, "path": candidate, "changes": changes,
                    "metrics": snapshot, "safe": bool(safe),
                    "admission": admission,
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
        baseline_key = (baseline["foreign_blocking"],
                        baseline["fab_blocking"],
                        baseline["route_blocking"], baseline["route_advisory"],
                        baseline["drc"], baseline["unconnected"],
                        float(baseline_row["objective"]), "baseline")
        chosen = None
        chosen_key = baseline_key
        for row in safe_variants:
            snap = row["metrics"]
            key = (snap["foreign_blocking"], snap["fab_blocking"],
                   snap["route_blocking"], snap["route_advisory"],
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
    ap.add_argument("--no-acute", action="store_true")
    ap.add_argument("--no-backtrack", action="store_true")
    ap.add_argument("--sliver-only-orthofill", action="store_true")
    ap.add_argument("--json", default="")
    a = ap.parse_args()
    out = []
    for bp in a.boards:
        if not os.path.isfile(bp):
            print("MISSING %s" % bp)
            continue
        if a.sliver_only_orthofill:
            r = repair_sliver_only_orthofill(
                bp, sliver_mm=a.sliver, apply=a.apply)
        else:
            r = repair(bp, sliver_mm=a.sliver, apply=a.apply,
                       do_priority=not a.no_priority,
                       do_island=not a.no_island,
                       do_starved=not a.no_starved,
                       do_acute=not a.no_acute,
                       do_backtrack=not a.no_backtrack)
        out.append(r)
        if a.sliver_only_orthofill:
            print("%-46s sliver_zones=%-3d %s"
                  % (os.path.basename(bp)[:46],
                     r["sliver_zones_removed"],
                     "APPLIED" if r["applied"] else "(dry run)"),
                  flush=True)
        else:
            print("%-46s tracks=%-3d backtracks=%-3d acute=%-3d min_thick=%-3d islands=%-3d "
                  "priority=%-3d starved=%-3d %s"
                  % (os.path.basename(bp)[:46], r["track_width"],
                     r["backtracks"], r["acute_vertices"],
                     r["min_thickness"], r["island_mode"], r["priority"],
                     r.get("starved", 0),
                     "APPLIED" if r["applied"] else "(dry run)"),
                  flush=True)
    if a.json:
        with open(a.json, "w") as fh:
            json.dump(out, fh, indent=1, default=str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
