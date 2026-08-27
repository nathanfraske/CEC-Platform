#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fill and admit dedicated GND planes before detailed routing.

The decoupler priority stage deliberately reserves local through-via barrels
before a global router can occupy them.  Those vias are not electrically
complete until KiCad fills the already-declared dedicated GND planes.  This
stage owns that boundary and fails closed unless:

* every ground layer declared by the fabrication profile has a GND zone;
* each dedicated plane fills as one broad connected component;
* every required priority-via UUID touches filled GND copper on every plane it
  spans;
* zone declarations and routed copper are unchanged by the fill; and
* DRC, connectivity, Kelvin, and differential-pair state do not regress.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil

import pcbnew

import cec_fab_profile as fab
import cec_fr
import cec_stage_admission


MM = 1_000_000


def _dedicated_ground_layers(board, board_path=""):
    """Return ``[(layer_id, canonical_name), ...]`` for true GND planes."""
    enabled = {int(layer) for layer in board.GetEnabledLayers().CuStack()}
    profile_name = fab.active_profile_name(board, hint=board_path)
    if profile_name:
        profile = fab.get_profile(profile_name)
        roles = dict(zip(fab.COPPER_LAYERS, profile["roles"]))
        return [
            (int(layer_id), canonical)
            for layer_id, canonical in fab.COPPER_LAYER_IDS.items()
            if int(layer_id) in enabled and roles.get(canonical) == "GND"
        ], profile_name

    # Legacy boards have no named profile authority.  Infer only existing
    # inner GND-zone layers; never silently convert an arbitrary signal layer.
    inferred = {}
    for zone in board.Zones():
        if zone.GetIsRuleArea() or zone.GetNetname() != "GND":
            continue
        for layer in zone.GetLayerSet().CuStack():
            layer = int(layer)
            if layer not in (int(pcbnew.F_Cu), int(pcbnew.B_Cu)):
                inferred[layer] = fab.COPPER_LAYER_IDS.get(
                    layer, board.GetLayerName(layer))
    return sorted(inferred.items()), None


def _zone_declaration_signature(board):
    """Stable outline-only signature; saved fill polygons are excluded."""
    rows = []
    for zone in board.Zones():
        outline = zone.Outline()
        contours = []
        for index in range(outline.OutlineCount()):
            contour = outline.Outline(index)
            exterior = tuple(
                (contour.CPoint(point).x, contour.CPoint(point).y)
                for point in range(contour.PointCount()))
            holes = []
            for hole_index in range(outline.HoleCount(index)):
                hole = outline.Hole(index, hole_index)
                holes.append(tuple(
                    (hole.CPoint(point).x, hole.CPoint(point).y)
                    for point in range(hole.PointCount())))
            contours.append((exterior, tuple(holes)))
        rows.append((
            zone.m_Uuid.AsString(), zone.GetNetname(), zone.GetZoneName(),
            bool(zone.GetIsRuleArea()),
            tuple(int(layer) for layer in zone.GetLayerSet().CuStack()),
            tuple(contours),
        ))
    return tuple(sorted(rows))


def _track_signature(board):
    """Prove the plane fill did not add, remove, or move routed objects."""
    rows = []
    for item in board.GetTracks():
        common = (
            item.m_Uuid.AsString(), item.GetClass(), item.GetNetname(),
            item.GetStart().x, item.GetStart().y,
            item.GetEnd().x, item.GetEnd().y,
        )
        if item.GetClass() == "PCB_VIA":
            extra = (
                item.GetDrillValue(),
                item.GetWidth(item.TopLayer()),
                int(item.TopLayer()), int(item.BottomLayer()),
            )
        else:
            extra = (item.GetWidth(), int(item.GetLayer()))
        rows.append(common + extra)
    return tuple(sorted(rows))


def _filled_plane_rows(board, layers, *, gnd_net="GND"):
    bb = board.GetBoardEdgesBoundingBox()
    board_area = max(1, int(bb.GetWidth())) * max(1, int(bb.GetHeight()))
    rows = []
    for layer_id, canonical in layers:
        zones = [
            zone for zone in board.Zones()
            if (not zone.GetIsRuleArea()
                and zone.GetNetname() == gnd_net
                and zone.IsOnLayer(layer_id))
        ]
        components = 0
        area = 0
        for zone in zones:
            polys = zone.GetFilledPolysList(layer_id)
            if not polys:
                continue
            components += int(polys.OutlineCount())
            try:
                area += int(polys.Area())
            except Exception:                            # noqa: BLE001
                pass
        rows.append({
            "layer": canonical,
            "board_layer_name": board.GetLayerName(layer_id),
            "layer_id": layer_id,
            "zone_count": len(zones),
            "filled_components": components,
            "filled_area_mm2": round(area / 1e12, 3),
            "coverage_ratio": round(area / board_area, 6),
        })
    return rows


def audit_board(board, *, board_path="", required_via_uuids=(),
                minimum_coverage=0.50):
    """Audit filled dedicated planes and exact priority-via connectivity."""
    layers, profile_name = _dedicated_ground_layers(board, board_path)
    required = tuple(sorted(set(required_via_uuids or ())))
    plane_rows = _filled_plane_rows(board, layers)
    reasons = []
    if not layers:
        reasons.append("no dedicated GND plane layers are declared or inferable")
    for row in plane_rows:
        if row["zone_count"] == 0:
            reasons.append("%s has no GND zone" % row["layer"])
        elif row["filled_components"] == 0:
            reasons.append("%s GND zone has no saved fill" % row["layer"])
        elif row["filled_components"] != 1:
            reasons.append("%s GND plane has %d disconnected components" % (
                row["layer"], row["filled_components"]))
        if row["coverage_ratio"] < float(minimum_coverage):
            reasons.append("%s GND coverage %.3f is below %.3f" % (
                row["layer"], row["coverage_ratio"], minimum_coverage))

    by_uuid = {
        item.m_Uuid.AsString(): item for item in board.GetTracks()
        if item.GetClass() == "PCB_VIA"
    }
    via_rows = []
    for uuid in required:
        via = by_uuid.get(uuid)
        row = {"uuid": uuid, "layers": [], "ok": False}
        if via is None:
            row["reason"] = "required priority via is missing"
            reasons.append("required priority via %s is missing" % uuid)
            via_rows.append(row)
            continue
        if via.GetNetname() != "GND":
            row["reason"] = "required priority via is on %s" % via.GetNetname()
            reasons.append("required priority via %s is not GND" % uuid)
            via_rows.append(row)
            continue
        spanned = {int(layer) for layer in via.GetLayerSet().CuStack()}
        misses = []
        for layer_id, canonical in layers:
            if layer_id not in spanned:
                continue
            hit = False
            for zone in board.Zones():
                if (zone.GetIsRuleArea() or zone.GetNetname() != "GND"
                        or not zone.IsOnLayer(layer_id)):
                    continue
                polys = zone.GetFilledPolysList(layer_id)
                if polys and polys.Collide(via.GetPosition(), 0):
                    hit = True
                    break
            row["layers"].append({"layer": canonical, "connected": hit})
            if not hit:
                misses.append(canonical)
        if misses:
            row["reason"] = "not connected on %s" % ", ".join(misses)
            reasons.append("priority via %s misses %s" % (
                uuid, ", ".join(misses)))
        elif not row["layers"]:
            row["reason"] = "via spans no dedicated GND layer"
            reasons.append("priority via %s spans no GND plane" % uuid)
        else:
            row["ok"] = True
        via_rows.append(row)
    return {
        "schema": 1,
        "ok": not reasons,
        "fab_profile": profile_name,
        "ground_layers": plane_rows,
        "minimum_coverage": float(minimum_coverage),
        "required_via_count": len(required),
        "connected_via_count": sum(row["ok"] for row in via_rows),
        "vias": via_rows,
        "reasons": reasons,
    }


def fill_board(board, *, board_path="", required_via_uuids=(),
               minimum_coverage=0.50):
    """Refill existing zones and audit without changing declared geometry."""
    zones_before = _zone_declaration_signature(board)
    tracks_before = _track_signature(board)
    for zone in board.Zones():
        zone.UnFill()
    try:
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    except Exception as error:                            # noqa: BLE001
        return {
            "schema": 1, "ok": False,
            "reasons": ["zone filler failed: %s: %s" % (
                type(error).__name__, error)],
        }
    audit = audit_board(
        board, board_path=board_path,
        required_via_uuids=required_via_uuids,
        minimum_coverage=minimum_coverage)
    audit["zone_declarations_unchanged"] = (
        zones_before == _zone_declaration_signature(board))
    audit["routed_copper_unchanged"] = (
        tracks_before == _track_signature(board))
    if not audit["zone_declarations_unchanged"]:
        audit["reasons"].append("zone filler changed a declared zone outline")
    if not audit["routed_copper_unchanged"]:
        audit["reasons"].append("zone filler changed routed copper geometry")
    audit["ok"] = not audit["reasons"]
    return audit


def _drc_type_regression(before, after):
    kinds = set(before.drc_types) | set(after.drc_types)
    return {
        kind: after.drc_types.get(kind, 0) - before.drc_types.get(kind, 0)
        for kind in sorted(kinds)
        if after.drc_types.get(kind, 0) > before.drc_types.get(kind, 0)
    }


def fill_and_admit(source, destination, *, required_via_uuids=(),
                   minimum_coverage=0.50):
    """Transactional file wrapper for the pre-route GND plane-fill stage."""
    import cec_score

    os.makedirs(os.path.dirname(os.path.abspath(destination)), exist_ok=True)
    shutil.copy2(source, destination)
    cec_fr.copy_project_sidecars(source, destination)
    before = cec_score.score(source)
    board = pcbnew.LoadBoard(destination)
    report = fill_board(
        board, board_path=destination,
        required_via_uuids=required_via_uuids,
        minimum_coverage=minimum_coverage)
    pcbnew.SaveBoard(destination, board)
    after = cec_score.score(destination)
    drc_regression = _drc_type_regression(before, after)
    admission = cec_stage_admission.evaluate(before, after)
    regression = not admission["accepted"]
    report.update({
        "before": admission["before"],
        "after": admission["after"],
        "admission": admission,
        "drc_regression": drc_regression,
        "rolled_back": bool(regression or not report.get("ok")),
    })
    if regression or not report.get("ok"):
        shutil.copy2(source, destination)
        cec_fr.copy_project_sidecars(source, destination)
        report["ok"] = False
        if regression:
            report["reason"] = admission["decision"]
    return report


def required_vias_from_ground_report(report):
    """Read the exact via-identity contract produced by the prior stage."""
    declared = set(report.get("required_via_uuids") or ())
    if not declared:
        # Backward-compatible handoff for reports written before the explicit
        # top-level contract was added.  The per-cell records already carried
        # the same exact identities, so no coordinate or net inference occurs.
        declared = {
            entry.get("via_uuid")
            for row in (report.get("cells") or ())
            for entry in (row.get("owner_ground_return"),
                          row.get("ground_return"))
            if isinstance(entry, dict) and entry.get("via_uuid")
        }
    return tuple(sorted(declared))


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("destination")
    parser.add_argument("--ground-report")
    parser.add_argument("--report")
    parser.add_argument("--minimum-coverage", type=float, default=0.50)
    args = parser.parse_args(argv)
    ground_report = {}
    if args.ground_report:
        with open(args.ground_report, encoding="utf-8") as handle:
            ground_report = json.load(handle)
    report = fill_and_admit(
        args.source, args.destination,
        required_via_uuids=required_vias_from_ground_report(ground_report),
        minimum_coverage=args.minimum_coverage)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, sort_keys=True)
            handle.write("\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
