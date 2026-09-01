#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Matched pair-transition and nearby GND-return-via admission.

The detailed router may change layers for a critical pair, but that result is
not accepted merely because both nets are connected. Signal vias must form
matched physical transitions and every transition must have a nearby GND plane
entry. The pass may symmetrically shorten an over-wide matched transition neck
and add legal GND return vias.  Both changes are transactional: freshly filled
zones, KiCad DRC, and connectivity must all admit the resulting artifact.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import sys
import tempfile

import pcbnew

import cec_fr
import cec_gnd_fanout
import cec_precision_route
import cec_score
import cec_stage_admission


MM = 1_000_000


def _xy(item):
    pos = item.GetPosition()
    return pos.x / MM, pos.y / MM


def _minimum_bottleneck_match(left, right):
    """Globally match equal via sets by (worst spacing, total spacing).

    A nearest-neighbour greedy assignment can consume the only good mate for a
    later transition and falsely refuse an otherwise matched pair.  Critical
    pairs have very few transitions, so a deterministic bitmask dynamic
    program gives the exact assignment without a SciPy dependency.
    """
    left = sorted(left, key=lambda row: _xy(row))
    right = sorted(right, key=lambda row: _xy(row))
    if len(left) != len(right):
        return None
    if not left:
        return []
    if len(left) > 12:
        return None
    states = {0: (0.0, 0.0, ())}
    for item in left:
        next_states = {}
        for mask, (worst, total, chosen) in states.items():
            for index, mate in enumerate(right):
                bit = 1 << index
                if mask & bit:
                    continue
                distance = math.dist(_xy(item), _xy(mate))
                candidate = (max(worst, distance), total + distance,
                             chosen + ((item, mate, distance),))
                new_mask = mask | bit
                old = next_states.get(new_mask)
                if old is None or candidate[:2] < old[:2]:
                    next_states[new_mask] = candidate
        states = next_states
    final = states.get((1 << len(right)) - 1)
    return list(final[2]) if final else None


def _move_transition_necks(board, p_via, n_via, target_spacing_mm):
    """Move one P/N transition symmetrically and retarget attached necks."""
    px, py = _xy(p_via)
    nx, ny = _xy(n_via)
    dx, dy = nx - px, ny - py
    distance = math.hypot(dx, dy)
    if distance <= target_spacing_mm + 1e-9 or distance <= 1e-12:
        return None
    ux, uy = dx / distance, dy / distance
    cx, cy = (px + nx) / 2.0, (py + ny) / 2.0
    p_new = (cx - ux * target_spacing_mm / 2.0,
             cy - uy * target_spacing_mm / 2.0)
    n_new = (cx + ux * target_spacing_mm / 2.0,
             cy + uy * target_spacing_mm / 2.0)

    def move(via, old_xy, new_xy):
        old = pcbnew.VECTOR2I(int(round(old_xy[0] * MM)),
                              int(round(old_xy[1] * MM)))
        new = pcbnew.VECTOR2I(int(round(new_xy[0] * MM)),
                              int(round(new_xy[1] * MM)))
        attached = []
        for item in board.GetTracks():
            if item.GetClass() != "PCB_TRACK":
                continue
            if item.GetNetCode() != via.GetNetCode():
                continue
            changed = []
            if item.GetStart() == old:
                item.SetStart(new)
                changed.append("start")
            if item.GetEnd() == old:
                item.SetEnd(new)
                changed.append("end")
            if changed:
                attached.append({
                    "uuid": item.m_Uuid.AsString(), "ends": changed,
                })
        via.SetPosition(new)
        return attached

    return {
        "before_spacing_mm": round(distance, 4),
        "after_spacing_mm": round(target_spacing_mm, 4),
        "p_uuid": p_via.m_Uuid.AsString(),
        "n_uuid": n_via.m_Uuid.AsString(),
        "p_before_mm": [round(px, 4), round(py, 4)],
        "n_before_mm": [round(nx, 4), round(ny, 4)],
        "p_after_mm": [round(p_new[0], 4), round(p_new[1], 4)],
        "n_after_mm": [round(n_new[0], 4), round(n_new[1], 4)],
        "p_necks": move(p_via, (px, py), p_new),
        "n_necks": move(n_via, (nx, ny), n_new),
    }


def _refill_saved_zones(board_path):
    """Fresh-load, unfill, and refill zones after moving/adding copper.

    KiCad stores filled polygons in the board.  Moving a via without rebuilding
    those polygons leaves a stale plane at the via's new antipad, which creates
    real DRC errors in the serialized artifact even though the intended
    geometry is legal.  Loading a fresh board also avoids pcbnew's known
    in-memory double-fill instability.
    """
    board = pcbnew.LoadBoard(board_path)
    for zone in board.Zones():
        zone.UnFill()
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(board_path, board)


def synthesize_board(board, *, board_path="", max_pair_spacing_mm=1.5,
                     return_reach_mm=1.5, dia_mm=0.6, drill_mm=0.3,
                     clearance_mm=0.20, lock=True,
                     repair_signal_transitions=True,
                     target_pair_spacing_mm=1.20):
    """Add legal GND return vias for every matched pair transition in place."""
    pairs = cec_precision_route.derive_coupled_pairs(
        board_path or board.GetFileName() or "", board=board)
    by_net = {}
    gnd_vias = []
    for item in board.GetTracks():
        if item.GetClass() != "PCB_VIA":
            continue
        by_net.setdefault(item.GetNetname(), []).append(item)
        if item.GetNetname() == "GND":
            gnd_vias.append(item)
    gnd = board.FindNet("GND")
    if gnd is None:
        return {"schema": 1, "ok": False, "error": "board has no GND net",
                "pairs": [], "added": 0}

    boxes, segments = cec_gnd_fanout._foreign_obstacles(board)
    zone_fills = cec_gnd_fanout._foreign_zone_fills(board)
    bounds = board.GetBoardEdgesBoundingBox()
    edge = (bounds.GetLeft() / MM, bounds.GetTop() / MM,
            bounds.GetRight() / MM, bounds.GetBottom() / MM)
    r_need = dia_mm / 2.0 + clearance_mm
    rows = []
    added = []
    added_vias = []
    for pair in pairs:
        p_vias = list(by_net.get(pair["p"]) or ())
        n_vias = list(by_net.get(pair["n"]) or ())
        row = {
            "name": pair["name"], "p": pair["p"], "n": pair["n"],
            "vias_p": len(p_vias), "vias_n": len(n_vias),
            "transitions": [], "added": [],
            "via_positions_p_mm": [
                [round(value, 4) for value in _xy(via)] for via in p_vias],
            "via_positions_n_mm": [
                [round(value, 4) for value in _xy(via)] for via in n_vias],
            "signal_realignments": [],
        }
        if len(p_vias) != len(n_vias):
            row.update({
                "ok": False,
                "refused": "asymmetric signal via count P=%d N=%d" %
                           (len(p_vias), len(n_vias))})
            rows.append(row)
            continue
        matched = _minimum_bottleneck_match(p_vias, n_vias)
        if matched is None:
            row.update({
                "ok": False,
                "refused": "signal transition assignment is unavailable"})
            rows.append(row)
            continue
        if repair_signal_transitions:
            for p_via, n_via, spacing in matched:
                if spacing <= max_pair_spacing_mm + 1e-9:
                    continue
                realignment = _move_transition_necks(
                    board, p_via, n_via,
                    min(float(target_pair_spacing_mm),
                        float(max_pair_spacing_mm)))
                if realignment:
                    row["signal_realignments"].append(realignment)
            matched = _minimum_bottleneck_match(p_vias, n_vias)
        if (matched is None or any(
                spacing > max_pair_spacing_mm + 1e-9
                for _p, _n, spacing in matched)):
            best = max((spacing for _p, _n, spacing in (matched or ())),
                       default=None)
            row.update({
                "ok": False,
                "refused": (
                    "signal vias do not form matched transitions within "
                    "%.2fmm (best bottleneck=%s)" % (
                        max_pair_spacing_mm,
                        "n/a" if best is None else "%.3fmm" % best))})
            rows.append(row)
            continue
        row["ok"] = True
        for p_via, n_via, spacing in matched:
            px, py = _xy(p_via)
            nx, ny = _xy(n_via)
            cx, cy = (px + nx) / 2.0, (py + ny) / 2.0
            nearest = min((math.dist((cx, cy), _xy(via))
                           for via in gnd_vias), default=float("inf"))
            transition = {
                "p_uuid": p_via.m_Uuid.AsString(),
                "n_uuid": n_via.m_Uuid.AsString(),
                "center_mm": [round(cx, 4), round(cy, 4)],
                "pair_spacing_mm": round(spacing, 4),
                "return_before_mm": (
                    round(nearest, 4) if math.isfinite(nearest) else None),
            }
            if nearest <= return_reach_mm + 1e-9:
                transition["status"] = "covered"
                row["transitions"].append(transition)
                continue
            landed = None
            # Start perpendicular to the signal-via pair, then exhaust a full
            # deterministic ring. This keeps the return close to the pair
            # field while allowing real pad/track/zone obstacles to veto it.
            vx, vy = nx - px, ny - py
            length = math.hypot(vx, vy) or 1.0
            base_angle = math.atan2(vy / length, vx / length) + math.pi / 2.0
            for radius in (0.9, 1.1, 1.3, 1.45):
                for step in range(8):
                    angle = base_angle + step * math.pi / 4.0
                    x = cx + radius * math.cos(angle)
                    y = cy + radius * math.sin(angle)
                    if not cec_gnd_fanout._spot_legal(
                            x, y, r_need, boxes, segments, edge, zone_fills):
                        continue
                    via = pcbnew.PCB_VIA(board)
                    via.SetViaType(pcbnew.VIATYPE_THROUGH)
                    via.SetPosition(pcbnew.VECTOR2I(
                        int(round(x * MM)), int(round(y * MM))))
                    via.SetDrill(int(round(drill_mm * MM)))
                    via.SetWidth(int(round(dia_mm * MM)))
                    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
                    via.SetNetCode(gnd.GetNetCode())
                    via.SetLocked(bool(lock))
                    board.Add(via)
                    landed = via
                    gnd_vias.append(via)
                    bb = via.GetBoundingBox()
                    boxes.append((bb.GetLeft() / MM, bb.GetRight() / MM,
                                  bb.GetTop() / MM, bb.GetBottom() / MM))
                    break
                if landed is not None:
                    break
            if landed is None:
                transition["status"] = "refused"
                transition["reason"] = (
                    "no legal GND return via within %.2fmm" % return_reach_mm)
                row["ok"] = False
                row["refused"] = transition["reason"]
            else:
                x, y = _xy(landed)
                add = {"uuid": landed.m_Uuid.AsString(),
                       "at_mm": [round(x, 4), round(y, 4)]}
                transition["status"] = "added"
                transition["return_uuid"] = add["uuid"]
                row["added"].append(add)
                added.append(add)
                added_vias.append(landed)
            row["transitions"].append(transition)
        rows.append(row)
    local_pair_return_vias = cec_fr.group_local_pair_return_vias(
        board, added_vias)
    return {
        "schema": 1, "ok": all(row.get("ok") for row in rows),
        "pairs": rows, "added": len(added), "generated_items": added,
        "local_pair_return_vias": local_pair_return_vias,
        "signal_realignments": sum(
            len(row.get("signal_realignments") or ()) for row in rows),
    }


def _synthesize_once(board_path, out_path, **kwargs):
    """Run one target-spacing transaction; connectivity/DRC may not regress."""
    preserve_failed = bool(kwargs.pop("preserve_failed", False))
    board = pcbnew.LoadBoard(board_path)
    before = cec_score.score(board_path)
    report = synthesize_board(
        board, board_path=board_path, **kwargs)
    fd, probe = tempfile.mkstemp(prefix="cec-pair-return-",
                                 suffix=".kicad_pcb")
    os.close(fd)
    try:
        pcbnew.SaveBoard(probe, board)
        for ext in (".kicad_pro", ".kicad_dru"):
            source = board_path[:-len(".kicad_pcb")] + ext
            if os.path.isfile(source):
                shutil.copy2(source, probe[:-len(".kicad_pcb")] + ext)
        report["local_pair_return_rule"] = (
            cec_fr.ensure_local_pair_return_via_rule(probe, report))
        try:
            _refill_saved_zones(probe)
            report["zones_refilled"] = True
        except Exception as error:  # fail closed: stale fills are not signoff
            report["zones_refilled"] = False
            report["ok"] = False
            report["error"] = "zone refill failed: %s: %s" % (
                type(error).__name__, error)
        after = cec_score.score(probe)
        admission = cec_stage_admission.evaluate(before, after)
        regression = not admission["accepted"]
        report["admission"] = {
            **admission,
            "drc_types_before": dict(before.drc_types),
            "drc_types_after": dict(after.drc_types),
            "regression": bool(regression),
        }
        if regression:
            report["ok"] = False
            report["error"] = (
                "return-via transaction rejected: %s"
                % admission["decision"])
        if report.get("ok"):
            shutil.copy2(probe, out_path)
            for ext in (".kicad_pro", ".kicad_dru"):
                source = probe[:-len(".kicad_pcb")] + ext
                if os.path.isfile(source):
                    shutil.copy2(source, out_path[:-len(".kicad_pcb")] + ext)
        elif preserve_failed:
            # Diagnostic-only CLI option.  Production callers keep the strict
            # transaction and never publish a rejected board.
            shutil.copy2(probe, out_path)
            report["failed_probe"] = os.path.abspath(out_path)
        return report
    finally:
        for path in (probe, probe[:-len(".kicad_pcb")] + ".kicad_pro",
                     probe[:-len(".kicad_pcb")] + ".kicad_dru"):
            try:
                os.unlink(path)
            except OSError:
                pass


def _target_candidates(max_pair_spacing_mm, requested_target_mm):
    """Return least-movement-first transition targets with signoff margin."""
    limit = float(max_pair_spacing_mm)
    requested = min(float(requested_target_mm), limit)
    # Keep 50 um inside the hard gate so serialization/measurement tolerance
    # cannot turn an exactly-on-limit transition into a false refusal.
    guarded = max(requested, limit - min(0.05, limit * 0.05))
    candidates = []
    value = guarded
    while value > requested + 1e-9:
        candidates.append(round(value, 6))
        value -= 0.05
    candidates.append(round(requested, 6))
    return list(dict.fromkeys(candidates))


def synthesize(board_path, out_path, **kwargs):
    """Search transition necks transactionally, preferring least movement.

    A single target can collide with geometry that a slightly different,
    still-compliant neck avoids.  Each target is rebuilt from the unchanged
    input, zones are freshly filled, and the first DRC/connectivity-clean result
    wins.  No rejected intermediate is published by production callers.
    """
    preserve_failed = bool(kwargs.pop("preserve_failed", False))
    repair = bool(kwargs.get("repair_signal_transitions", True))
    limit = float(kwargs.get("max_pair_spacing_mm", 1.5))
    requested = float(kwargs.get("target_pair_spacing_mm", 1.20))
    targets = (_target_candidates(limit, requested) if repair else [requested])
    attempts = []
    last = None
    for index, target in enumerate(targets):
        trial_kwargs = dict(kwargs)
        trial_kwargs["target_pair_spacing_mm"] = target
        trial_kwargs["preserve_failed"] = bool(
            preserve_failed and index == len(targets) - 1)
        report = _synthesize_once(board_path, out_path, **trial_kwargs)
        attempts.append({
            "target_pair_spacing_mm": target,
            "ok": bool(report.get("ok")),
            "admission": report.get("admission"),
            "error": report.get("error"),
        })
        last = report
        if report.get("ok"):
            report["target_search"] = {
                "policy": "least-movement-first-drc-admitted",
                "selected_target_pair_spacing_mm": target,
                "attempts": attempts,
            }
            return report
    last = last or {"schema": 1, "ok": False,
                    "error": "no transition target was attempted"}
    last["target_search"] = {
        "policy": "least-movement-first-drc-admitted",
        "selected_target_pair_spacing_mm": None,
        "attempts": attempts,
    }
    return last


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("board")
    parser.add_argument("output")
    parser.add_argument("--json", dest="json_path", default="")
    parser.add_argument("--max-pair-spacing-mm", type=float, default=1.5)
    parser.add_argument("--target-pair-spacing-mm", type=float, default=1.2)
    parser.add_argument("--preserve-failed", action="store_true")
    args = parser.parse_args(argv)
    report = synthesize(
        args.board, args.output,
        max_pair_spacing_mm=args.max_pair_spacing_mm,
        target_pair_spacing_mm=args.target_pair_spacing_mm,
        preserve_failed=args.preserve_failed)
    if args.json_path:
        with open(args.json_path, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, sort_keys=True)
            handle.write("\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
