#!/usr/bin/env python3
"""Transactional repair for routed aggressor/victim field-coupling faults.

The field audit can convict a route which is perfectly legal to the ordinary
clearance DRC: a long victim segment may run beside an aggressor, or an
unshielded crossing may be too oblique.  This module repairs the common,
general case without knowing component references or board coordinates:

* select the straight victim segment named by the physical interaction;
* move its middle run perpendicular to the aggressor, away from the field;
* join the original endpoints with 45-degree entry/exit legs;
* try a bounded family of offsets on isolated board copies; and
* adopt only a candidate which reduces field blockers without regressing DRC,
  connectivity, Kelvin/differential integrity, or route-craft gates.

The original endpoints and net graph are unchanged.  This is intentionally a
post-route repair, not a waiver: the independent field checker must prove that
the interaction is gone before copper is published.
"""

from __future__ import annotations

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


def _point_mm(point):
    return (point.x / 1e6, point.y / 1e6)


def _uuid(item):
    return str(item.m_Uuid.AsString())


def offset_straight_track(board, track_uuid: str, offset_mm: float):
    """Offset one straight run while preserving its two graph endpoints.

    The longitudinal inset equals the perpendicular offset, so both joining
    legs are exactly 45 degrees.  The existing object becomes the first leg
    and keeps its UUID; two new same-net/same-layer objects complete the run.
    No item is removed, avoiding the KiCad SWIG invalidation hazard.
    """
    import pcbnew

    track = next((item for item in board.GetTracks()
                  if item.GetClass() == "PCB_TRACK"
                  and _uuid(item) == str(track_uuid)), None)
    if track is None:
        raise ValueError("track UUID not found: %s" % track_uuid)
    start = track.GetStart()
    end = track.GetEnd()
    dx = end.x - start.x
    dy = end.y - start.y
    horizontal = abs(dy) <= 1_000
    vertical = abs(dx) <= 1_000
    if not (horizontal or vertical) or (horizontal and vertical):
        raise ValueError("only nonzero horizontal/vertical tracks are eligible")

    shift_nm = int(round(float(offset_mm) * 1e6))
    inset_nm = abs(shift_nm)
    length_nm = abs(dx) if horizontal else abs(dy)
    if inset_nm < 10_000:
        raise ValueError("offset is below 0.01 mm")
    if length_nm <= 2 * inset_nm + 10_000:
        raise ValueError("track is too short for 45-degree offset legs")

    if horizontal:
        direction = 1 if dx > 0 else -1
        first = pcbnew.VECTOR2I(start.x + direction * inset_nm,
                               start.y + shift_nm)
        second = pcbnew.VECTOR2I(end.x - direction * inset_nm,
                                end.y + shift_nm)
    else:
        direction = 1 if dy > 0 else -1
        first = pcbnew.VECTOR2I(start.x + shift_nm,
                               start.y + direction * inset_nm)
        second = pcbnew.VECTOR2I(end.x + shift_nm,
                                end.y - direction * inset_nm)

    original_end = pcbnew.VECTOR2I(end.x, end.y)
    track.SetEnd(first)
    created = []
    for leg_start, leg_end in ((first, second), (second, original_end)):
        leg = pcbnew.PCB_TRACK(board)
        leg.SetStart(leg_start)
        leg.SetEnd(leg_end)
        leg.SetWidth(track.GetWidth())
        leg.SetLayer(track.GetLayer())
        leg.SetNetCode(track.GetNetCode())
        leg.SetLocked(track.IsLocked())
        board.Add(leg)
        created.append(leg)
    return {
        "source_uuid": str(track_uuid),
        "offset_mm": round(float(offset_mm), 6),
        "net": track.GetNetname() or "",
        "layer": board.GetLayerName(track.GetLayer()),
        "start_mm": [round(v, 6) for v in _point_mm(start)],
        "end_mm": [round(v, 6) for v in _point_mm(end)],
        "replacement_uuids": [_uuid(track)] + [_uuid(item) for item in created],
    }


def _xy_key(point):
    return (int(point.x), int(point.y))


def relayer_track_component(board, track_uuid: str, target_layer_name: str):
    """Move one same-net/same-layer track island between conductive anchors.

    The island boundary must be seated on a via or through-hole pad belonging
    to the same net.  Consequently changing every track in the island to a new
    copper layer cannot invent an open endpoint.  Blind layer changes at SMD
    pads or arbitrary graph vertices are refused.
    """
    import pcbnew

    seed = next((item for item in board.GetTracks()
                 if item.GetClass() == "PCB_TRACK"
                 and _uuid(item) == str(track_uuid)), None)
    if seed is None:
        raise ValueError("track UUID not found: %s" % track_uuid)
    target_layer = board.GetLayerID(str(target_layer_name))
    if target_layer < 0 or not pcbnew.IsCopperLayer(target_layer):
        raise ValueError("target is not an enabled copper layer: %s" %
                         target_layer_name)
    if target_layer == seed.GetLayer():
        raise ValueError("target layer equals source layer")

    pool = [item for item in board.GetTracks()
            if item.GetClass() == "PCB_TRACK"
            and item.GetNetCode() == seed.GetNetCode()
            and item.GetLayer() == seed.GetLayer()]
    by_point = {}
    for item in pool:
        by_point.setdefault(_xy_key(item.GetStart()), []).append(item)
        by_point.setdefault(_xy_key(item.GetEnd()), []).append(item)
    component = {}
    queue = [seed]
    while queue:
        item = queue.pop()
        uid = _uuid(item)
        if uid in component:
            continue
        component[uid] = item
        for point in (item.GetStart(), item.GetEnd()):
            queue.extend(by_point.get(_xy_key(point), ()))

    degrees = {}
    point_objects = {}
    for item in component.values():
        for point in (item.GetStart(), item.GetEnd()):
            key = _xy_key(point)
            degrees[key] = degrees.get(key, 0) + 1
            point_objects[key] = point
    boundaries = [point_objects[key] for key, degree in degrees.items()
                  if degree == 1]
    if len(boundaries) < 2:
        raise ValueError("track island has fewer than two boundary anchors")

    vias = [item for item in board.GetTracks()
            if item.GetClass() == "PCB_VIA"
            and item.GetNetCode() == seed.GetNetCode()]
    pads = [pad for footprint in board.GetFootprints()
            for pad in footprint.Pads()
            if pad.GetNetCode() == seed.GetNetCode()
            and pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH]

    def anchored(point):
        key = _xy_key(point)
        for via in vias:
            if _xy_key(via.GetPosition()) == key:
                layers = via.GetLayerSet()
                if layers.Contains(seed.GetLayer()) and layers.Contains(
                        target_layer):
                    return True
        for pad in pads:
            if pad.HitTest(point):
                layers = pad.GetLayerSet()
                if layers.Contains(seed.GetLayer()) and layers.Contains(
                        target_layer):
                    return True
        return False

    unanchored = [point for point in boundaries if not anchored(point)]
    if unanchored:
        raise ValueError("track island has %d unanchored boundary endpoint(s)" %
                         len(unanchored))
    source_layer = board.GetLayerName(seed.GetLayer())
    for item in component.values():
        item.SetLayer(target_layer)
    return {
        "source_uuid": str(track_uuid),
        "net": seed.GetNetname() or "",
        "source_layer": source_layer,
        "target_layer": board.GetLayerName(target_layer),
        "track_uuids": sorted(component),
        "track_count": len(component),
        "boundary_mm": [[round(point.x / 1e6, 6),
                         round(point.y / 1e6, 6)] for point in boundaries],
    }


def perpendicular_endpoint_departure(board, victim_uuid: str,
                                     aggressor_uuid: str,
                                     required_edge_gap_mm: float,
                                     margin_mm: float = 0.10):
    """Make an anchored aggressor leave a straight victim perpendicularly.

    This handles the common pin/via escape topology ``anchor -> 45deg ->
    straight continuation``.  The diagonal is moved downstream along the
    continuation, creating an initial 90-degree field crossing while retaining
    0/45/90 route craft.  The joint being moved must have degree two and the
    other endpoint must be a via/PTH anchor, so no branch can be stranded.
    """
    import pcbnew

    tracks = [item for item in board.GetTracks()
              if item.GetClass() == "PCB_TRACK"]
    by_uuid = {_uuid(item): item for item in tracks}
    victim = by_uuid.get(str(victim_uuid))
    aggressor = by_uuid.get(str(aggressor_uuid))
    if victim is None or aggressor is None:
        raise ValueError("victim/aggressor track UUID is unavailable")
    vs, ve = victim.GetStart(), victim.GetEnd()
    victim_horizontal = abs(ve.y - vs.y) <= 1_000
    victim_vertical = abs(ve.x - vs.x) <= 1_000
    if not (victim_horizontal or victim_vertical):
        raise ValueError("victim must be horizontal or vertical")
    ags, age = aggressor.GetStart(), aggressor.GetEnd()
    adx, ady = age.x - ags.x, age.y - ags.y
    if abs(abs(adx) - abs(ady)) > 1_000 or abs(adx) < 10_000:
        raise ValueError("aggressor endpoint leg must be 45 degrees")

    net_layer = [item for item in tracks
                 if item.GetNetCode() == aggressor.GetNetCode()
                 and item.GetLayer() == aggressor.GetLayer()]
    endpoint_map = {}
    for item in net_layer:
        endpoint_map.setdefault(_xy_key(item.GetStart()), []).append(item)
        endpoint_map.setdefault(_xy_key(item.GetEnd()), []).append(item)

    vias = [item for item in board.GetTracks()
            if item.GetClass() == "PCB_VIA"
            and item.GetNetCode() == aggressor.GetNetCode()]
    pads = [pad for footprint in board.GetFootprints()
            for pad in footprint.Pads()
            if pad.GetNetCode() == aggressor.GetNetCode()
            and pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH]

    def is_anchor(point):
        key = _xy_key(point)
        return (any(_xy_key(via.GetPosition()) == key for via in vias)
                or any(pad.HitTest(point) for pad in pads))

    options = []
    for anchor, joint in ((ags, age), (age, ags)):
        at_joint = [item for item in endpoint_map.get(_xy_key(joint), ())
                    if _uuid(item) != _uuid(aggressor)]
        if not is_anchor(anchor) or len(at_joint) != 1:
            continue
        continuation = at_joint[0]
        cs, ce = continuation.GetStart(), continuation.GetEnd()
        other = ce if _xy_key(cs) == _xy_key(joint) else cs
        cdx, cdy = other.x - joint.x, other.y - joint.y
        continuation_perpendicular = (
            (victim_vertical and abs(cdy) <= 1_000 and abs(cdx) > 10_000)
            or (victim_horizontal and abs(cdx) <= 1_000
                and abs(cdy) > 10_000))
        if continuation_perpendicular:
            options.append((anchor, joint, continuation, other))
    if len(options) != 1:
        raise ValueError("endpoint topology is not one anchored 45/straight escape")
    anchor, joint, continuation, other = options[0]
    # These are SWIG views into the tracks.  Copy coordinates before mutating
    # the aggressor; otherwise its old endpoint proxy changes in place and the
    # continuation's wrong end is shortened.
    anchor = pcbnew.VECTOR2I(anchor.x, anchor.y)
    joint = pcbnew.VECTOR2I(joint.x, joint.y)
    other = pcbnew.VECTOR2I(other.x, other.y)

    # Departure direction is along the existing continuation.  It must also
    # move away from the victim; otherwise this topology cannot be repaired by
    # delaying its diagonal turn.
    if victim_vertical:
        direction = 1 if other.x > joint.x else -1
        victim_axis = (vs.x + ve.x) / 2
        current_center = abs(anchor.x - victim_axis) / 1e6
        away = ((anchor.x - victim_axis) * direction) >= 0
        diag_span = abs(joint.y - anchor.y)
    else:
        direction = 1 if other.y > joint.y else -1
        victim_axis = (vs.y + ve.y) / 2
        current_center = abs(anchor.y - victim_axis) / 1e6
        away = ((anchor.y - victim_axis) * direction) >= 0
        diag_span = abs(joint.x - anchor.x)
    if not away:
        raise ValueError("continuation heads toward the victim")
    victim_half = victim.GetWidth() / 2e6
    aggressor_half = aggressor.GetWidth() / 2e6
    needed_center = (float(required_edge_gap_mm) + victim_half
                     + aggressor_half + float(margin_mm))
    departure_mm = max(0.15, needed_center - current_center)
    departure_nm = int(math.ceil(departure_mm * 1e6 / 10_000.0) * 10_000)

    if victim_vertical:
        turn = pcbnew.VECTOR2I(anchor.x + direction * departure_nm,
                              anchor.y)
        new_joint = pcbnew.VECTOR2I(
            turn.x + direction * diag_span, joint.y)
        within = ((other.x - new_joint.x) * direction >= 10_000)
    else:
        turn = pcbnew.VECTOR2I(anchor.x,
                              anchor.y + direction * departure_nm)
        new_joint = pcbnew.VECTOR2I(
            joint.x, turn.y + direction * diag_span)
        within = ((other.y - new_joint.y) * direction >= 10_000)
    if not within:
        raise ValueError("continuation is too short for perpendicular departure")

    # Keep the aggressor UUID on the new perpendicular departure.  Add the
    # shifted 45-degree leg and shorten the continuation at its joint.
    if _xy_key(aggressor.GetStart()) == _xy_key(anchor):
        aggressor.SetEnd(turn)
    else:
        aggressor.SetStart(turn)
    diagonal = pcbnew.PCB_TRACK(board)
    diagonal.SetStart(turn)
    diagonal.SetEnd(new_joint)
    diagonal.SetWidth(aggressor.GetWidth())
    diagonal.SetLayer(aggressor.GetLayer())
    diagonal.SetNetCode(aggressor.GetNetCode())
    diagonal.SetLocked(aggressor.IsLocked())
    board.Add(diagonal)
    if _xy_key(continuation.GetStart()) == _xy_key(joint):
        continuation.SetStart(new_joint)
    else:
        continuation.SetEnd(new_joint)
    return {
        "victim_uuid": str(victim_uuid),
        "aggressor_uuid": str(aggressor_uuid),
        "net": aggressor.GetNetname() or "",
        "layer": board.GetLayerName(aggressor.GetLayer()),
        "departure_mm": round(departure_nm / 1e6, 6),
        "turn_mm": [round(turn.x / 1e6, 6), round(turn.y / 1e6, 6)],
        "new_joint_mm": [round(new_joint.x / 1e6, 6),
                         round(new_joint.y / 1e6, 6)],
        "created_uuid": _uuid(diagonal),
        "continuation_uuid": _uuid(continuation),
    }


def _worker(source, output, track_uuid, offset_mm):
    import pcbnew
    import cec_swig_guard

    cec_swig_guard.pin()
    board = pcbnew.LoadBoard(source)
    change = offset_straight_track(board, track_uuid, offset_mm)
    for zone in board.Zones():
        zone.UnFill()
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.Save(output)
    return change


def _relayer_worker(source, output, track_uuid, target_layer):
    import pcbnew
    import cec_swig_guard

    cec_swig_guard.pin()
    board = pcbnew.LoadBoard(source)
    change = relayer_track_component(
        board, track_uuid, str(target_layer))
    for zone in board.Zones():
        zone.UnFill()
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.Save(output)
    return change


def _departure_worker(source, output, victim_uuid, aggressor_uuid,
                      required_edge_gap_mm, margin_mm):
    import pcbnew
    import cec_swig_guard

    cec_swig_guard.pin()
    board = pcbnew.LoadBoard(source)
    change = perpendicular_endpoint_departure(
        board, victim_uuid, aggressor_uuid,
        float(required_edge_gap_mm), float(margin_mm))
    for zone in board.Zones():
        zone.UnFill()
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.Save(output)
    return change


def _score_isolated(board_path):
    import cec_fab_repair
    return cec_fab_repair._score_isolated(board_path)


def _field_isolated(board_path):
    code = (
        "import json,sys;sys.path.insert(0,sys.argv[2]);"
        "import cec_field_coupling as f;"
        "r=f.field_coupling_summary(sys.argv[1]);"
        "print('CEC_FIELD='+json.dumps(r,sort_keys=True))")
    proc = subprocess.run(
        [sys.executable, "-c", code, os.path.abspath(board_path), HERE],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    marker = next((line[len("CEC_FIELD="):]
                   for line in reversed(proc.stdout.splitlines())
                   if line.startswith("CEC_FIELD=")), None)
    if proc.returncode or marker is None:
        raise RuntimeError("isolated field audit failed rc=%d: %s" %
                           (proc.returncode,
                            (proc.stderr or proc.stdout)[-1200:]))
    return json.loads(marker)


def _copy_board_family(source, output):
    shutil.copy2(source, output)
    for ext in (".kicad_pro", ".kicad_dru", ".kicad_prl"):
        src = source[:-len(".kicad_pcb")] + ext
        if os.path.isfile(src):
            shutil.copy2(src, output[:-len(".kicad_pcb")] + ext)


def _worker_isolated(source, output, track_uuid, offset_mm):
    report = output + ".change.json"
    # DRC ownership lives in the project/rules sidecars.  A board-only trial
    # silently drops the scoped POFV rules and fabricates annular/drill faults,
    # so every isolated candidate must retain the complete board family.
    _copy_board_family(source, output)
    proc = subprocess.run(
        [sys.executable, os.path.abspath(__file__), "--worker", source,
         output, str(track_uuid), str(offset_mm), "--json", report],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode or not os.path.isfile(output):
        raise RuntimeError("offset worker failed rc=%d: %s" %
                           (proc.returncode,
                            (proc.stderr or proc.stdout)[-1200:]))
    with open(report, encoding="utf-8") as handle:
        return json.load(handle)


def _relayer_worker_isolated(source, output, track_uuid, target_layer):
    report = output + ".change.json"
    _copy_board_family(source, output)
    proc = subprocess.run(
        [sys.executable, os.path.abspath(__file__), "--relayer-worker",
         source, output, str(track_uuid), str(target_layer),
         "--json", report], capture_output=True, text=True,
        encoding="utf-8", errors="replace")
    if proc.returncode or not os.path.isfile(output):
        raise RuntimeError("relayer worker failed rc=%d: %s" %
                           (proc.returncode,
                            (proc.stderr or proc.stdout)[-1200:]))
    with open(report, encoding="utf-8") as handle:
        return json.load(handle)


def _routing_layers_isolated(board_path):
    code = (
        "import json,sys;sys.path.insert(0,sys.argv[2]);"
        "import pcbnew,cec_swig_guard;cec_swig_guard.pin();"
        "b=pcbnew.LoadBoard(sys.argv[1]);counts={};"
        "[(counts.__setitem__(t.GetLayer(),counts.get(t.GetLayer(),0)+1)) "
        "for t in b.GetTracks() if t.GetClass()=='PCB_TRACK'];"
        "rows=[b.GetLayerName(i) for i in range(64) "
        "if b.IsLayerEnabled(i) and pcbnew.IsCopperLayer(i) "
        "and (i in counts or b.GetLayerName(i) in ('F.Cu','B.Cu')) "
        "and all(x not in b.GetLayerName(i).upper() "
        "for x in ('GND','PWR','POWER','PLANE'))];"
        "print('CEC_LAYERS='+json.dumps(rows))")
    proc = subprocess.run(
        [sys.executable, "-c", code, os.path.abspath(board_path), HERE],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    marker = next((line[len("CEC_LAYERS="):]
                   for line in reversed(proc.stdout.splitlines())
                   if line.startswith("CEC_LAYERS=")), None)
    if proc.returncode or marker is None:
        raise RuntimeError("could not enumerate routing layers")
    return json.loads(marker)


def _relayer_trials(current, target, baseline_score, baseline_field, work,
                    round_index):
    nets = list(target.get("nets") or ())
    uuids = list(target.get("track_uuids") or ())
    ordered = []
    # At a cross-layer interaction, moving the aggressor island is often much
    # smaller than moving a long sensitive trunk.  Still try both identities;
    # independent admission decides rather than this heuristic.
    for role in (target.get("aggressor"), target.get("victim")):
        if role in nets:
            value = str(uuids[nets.index(role)])
            if value not in ordered:
                ordered.append(value)
    trials = []
    for uid in ordered:
        for layer in _routing_layers_isolated(current):
            candidate = os.path.join(
                work, "r%02d-relayer-%s-%s.kicad_pcb" %
                (round_index + 1, uid[:8],
                 layer.replace(".", "-").replace("/", "-")))
            try:
                change = _relayer_worker_isolated(
                    current, candidate, uid, layer)
                score = _score_isolated(candidate)
                field = _field_isolated(candidate)
                safe = _safe_no_regression(baseline_score, score)
                reduced = (int(field.get("blocking_count", 999999))
                           < int(baseline_field.get(
                               "blocking_count", 999999)))
                trials.append({
                    "path": candidate, "track_uuid": uid,
                    "target_layer": layer, "change": change,
                    "score": score,
                    "field_blocking": int(field.get(
                        "blocking_count", 999999)),
                    "field_violations": field.get("violations", []),
                    "safe": bool(safe), "reduced": bool(reduced),
                })
            except Exception as exc:                         # noqa: BLE001
                trials.append({"track_uuid": uid,
                               "target_layer": layer,
                               "safe": False, "reduced": False,
                               "error": "%s: %s" %
                                        (type(exc).__name__, exc)})
    return trials


def _safe_no_regression(baseline, candidate):
    return (
        int(candidate["drc"]) <= int(baseline["drc"])
        and int(candidate["unconnected"]) <= int(baseline["unconnected"])
        and bool(candidate["kelvin_ok"])
        and bool(candidate["diffpair_ok"])
        and int(candidate.get("route_blocking", 0))
        <= int(baseline.get("route_blocking", 0))
        and int(candidate.get("route_non_octilinear", 0))
        <= int(baseline.get("route_non_octilinear", 0)))


def _victim_uuid(interaction):
    nets = list(interaction.get("nets") or ())
    uuids = list(interaction.get("track_uuids") or ())
    victim = str(interaction.get("victim") or "")
    if len(nets) != 2 or len(uuids) != 2 or victim not in nets:
        return None
    return str(uuids[nets.index(victim)])


def _away_sign(interaction, board_path, victim_uuid):
    """Return the perpendicular sign which moves victim away from aggressor."""
    code = (
        "import json,sys;sys.path.insert(0,sys.argv[4]);"
        "import pcbnew,cec_swig_guard;cec_swig_guard.pin();"
        "b=pcbnew.LoadBoard(sys.argv[1]);u={sys.argv[2],sys.argv[3]};"
        "rows={};"
        "[(rows.__setitem__(str(t.m_Uuid.AsString()),"
        "[t.GetStart().x/1e6,t.GetStart().y/1e6,"
        "t.GetEnd().x/1e6,t.GetEnd().y/1e6])) "
        "for t in b.GetTracks() if str(t.m_Uuid.AsString()) in u];"
        "print('CEC_GEOM='+json.dumps(rows,sort_keys=True))")
    other = next((str(value) for value in interaction.get("track_uuids", ())
                  if str(value) != str(victim_uuid)), "")
    proc = subprocess.run(
        [sys.executable, "-c", code, os.path.abspath(board_path),
         str(victim_uuid), other, HERE], capture_output=True, text=True,
        encoding="utf-8", errors="replace")
    marker = next((line[len("CEC_GEOM="):]
                   for line in reversed(proc.stdout.splitlines())
                   if line.startswith("CEC_GEOM=")), None)
    if proc.returncode or marker is None:
        raise RuntimeError("could not inspect interaction geometry")
    rows = json.loads(marker)
    victim = rows[str(victim_uuid)]
    aggressor = rows[other]
    vm = ((victim[0] + victim[2]) / 2, (victim[1] + victim[3]) / 2)
    am = ((aggressor[0] + aggressor[2]) / 2,
          (aggressor[1] + aggressor[3]) / 2)
    horizontal = abs(victim[3] - victim[1]) <= 0.001
    return (1 if vm[1] >= am[1] else -1) if horizontal else (
        1 if vm[0] >= am[0] else -1)


def repair_admitted(board_path, output_path=None, *, max_rounds=6,
                    margin_mm=0.10):
    """Reduce field blockers with bounded, fail-closed offset trials."""
    source = os.path.abspath(board_path)
    output = os.path.abspath(output_path or board_path)
    parent = os.path.dirname(output) or "."
    os.makedirs(parent, exist_ok=True)
    work = tempfile.mkdtemp(prefix=".cec-field-repair-", dir=parent)
    current = os.path.join(work, "current.kicad_pcb")
    _copy_board_family(source, current)
    history = []
    try:
        for round_index in range(max(1, int(max_rounds))):
            baseline_score = _score_isolated(current)
            baseline_field = _field_isolated(current)
            blockers = [row for row in baseline_field.get("interactions", ())
                        if row.get("blocking")]
            if not blockers:
                break
            # Long same-layer parallel runs are the most consequential and the
            # most deterministic to separate; otherwise use the first victim
            # straight segment reported by the physical checker.
            blockers.sort(key=lambda row: (
                row.get("reason") != "unshielded parallel aggressor/victim run",
                -float(row.get("parallel_overlap_mm") or 0.0),
                str(row.get("victim") or "")))
            target = blockers[0]
            target_uuid = _victim_uuid(target)
            if not target_uuid:
                history.append({"round": round_index + 1,
                                "accepted": False,
                                "reason": "victim_uuid_unavailable"})
                break
            sign = _away_sign(target, current, target_uuid)
            needed = max(0.15,
                         float(target.get("interaction_reach_mm") or 1.0)
                         - float(target.get("edge_gap_mm") or 0.0)
                         + float(margin_mm))
            magnitudes = sorted({round(value, 3) for value in (
                needed, needed + 0.15, needed + 0.35,
                max(0.5, needed), max(0.8, needed), max(1.0, needed))})
            trials = []
            for trial_index, magnitude in enumerate(magnitudes):
                for direction in (sign, -sign):
                    offset = round(direction * magnitude, 3)
                    candidate = os.path.join(
                        work, "r%02d-t%02d-%s.kicad_pcb" %
                        (round_index + 1, trial_index + 1,
                         "p" if offset > 0 else "m"))
                    try:
                        change = _worker_isolated(
                            current, candidate, target_uuid, offset)
                        score = _score_isolated(candidate)
                        field = _field_isolated(candidate)
                        safe = _safe_no_regression(baseline_score, score)
                        reduced = (int(field.get("blocking_count", 999999))
                                   < int(baseline_field.get(
                                       "blocking_count", 999999)))
                        trials.append({
                            "path": candidate, "offset_mm": offset,
                            "change": change, "score": score,
                            "field_blocking": int(field.get(
                                "blocking_count", 999999)),
                            "field_violations": field.get("violations", []),
                            "safe": bool(safe), "reduced": bool(reduced),
                        })
                    except Exception as exc:                 # noqa: BLE001
                        trials.append({"offset_mm": offset, "safe": False,
                                       "reduced": False,
                                       "error": "%s: %s" %
                                                (type(exc).__name__, exc)})
            accepted = [row for row in trials
                        if row.get("safe") and row.get("reduced")]
            if not accepted:
                relayer = _relayer_trials(
                    current, target, baseline_score, baseline_field, work,
                    round_index)
                accepted = [row for row in relayer
                            if row.get("safe") and row.get("reduced")]
                if not accepted:
                    history.append({
                        "round": round_index + 1, "accepted": False,
                        "target_uuid": target_uuid, "interaction": target,
                        "offset_trials": trials,
                        "relayer_trials": relayer,
                    })
                    break
                trials = relayer
            winner = min(accepted, key=lambda row: (
                row["field_blocking"],
                row["score"].get("route_advisory", 999999),
                row["score"].get("objective", math.inf),
                abs(row.get("offset_mm", 0.0)),
                row.get("offset_mm", 0.0),
                row.get("target_layer", "")))
            shutil.copy2(winner["path"], current)
            history.append({
                "round": round_index + 1, "accepted": True,
                "target_uuid": target_uuid, "interaction": target,
                "winner": {key: value for key, value in winner.items()
                           if key != "path"},
                "trial_count": len(trials),
            })

        final_score = _score_isolated(current)
        final_field = _field_isolated(current)
        _copy_board_family(current, output)
        return {
            "schema": "cec-field-coupling-repair-v1",
            "source": source, "output": output,
            "history": history,
            "final_score": final_score,
            "final_field": final_field,
            "closed": int(final_field.get("blocking_count", 999999)) == 0,
        }
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("board", nargs="?")
    parser.add_argument("output", nargs="?")
    parser.add_argument("--json")
    parser.add_argument("--max-rounds", type=int, default=6)
    parser.add_argument("--margin-mm", type=float, default=0.10)
    parser.add_argument("--worker", nargs=4,
                        metavar=("SOURCE", "OUTPUT", "UUID", "OFFSET_MM"))
    parser.add_argument("--relayer-worker", nargs=4,
                        metavar=("SOURCE", "OUTPUT", "UUID", "LAYER"))
    parser.add_argument("--departure-worker", nargs=6,
                        metavar=("SOURCE", "OUTPUT", "VICTIM_UUID",
                                 "AGGRESSOR_UUID", "EDGE_GAP_MM",
                                 "MARGIN_MM"))
    args = parser.parse_args(argv)
    if args.worker:
        source, output, track_uuid, offset = args.worker
        report = _worker(source, output, track_uuid, float(offset))
    elif args.relayer_worker:
        source, output, track_uuid, layer = args.relayer_worker
        report = _relayer_worker(source, output, track_uuid, layer)
    elif args.departure_worker:
        source, output, victim, aggressor, edge_gap, margin = (
            args.departure_worker)
        report = _departure_worker(
            source, output, victim, aggressor,
            float(edge_gap), float(margin))
    else:
        if not args.board:
            parser.error("BOARD is required")
        report = repair_admitted(
            args.board, args.output, max_rounds=args.max_rounds,
            margin_mm=args.margin_mm)
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
