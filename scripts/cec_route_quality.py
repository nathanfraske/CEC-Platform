#!/usr/bin/env python3
"""Geometric route-quality audit for routed KiCad boards.

Connectivity and DRC are necessary but not sufficient route checks.  A trace
can be electrically connected and clearance-clean while doubling back through
an acute vertex, creating the connected ``pseudo-stub`` that escaped the Hub
USB review.  This module turns that visual defect into deterministic evidence.

The audit is deliberately conservative:

* only exact same-net, same-layer track junctions are considered;
* a vertex must have exactly two incident straight segments;
* a normal 90-degree or gentler route is accepted;
* an opening angle below 90 degrees is an acute backtrack;
* collinear/covered duplicates are reported separately.

No board is mutated here.  Generators use the result as a fail-closed admission
check and candidate scorers use it to reject protected-net regressions or rank
ordinary-net candidates.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import defaultdict


def _uuid(item):
    try:
        return item.m_Uuid.AsString()
    except Exception:  # noqa: BLE001 -- diagnostic identity is best effort
        return ""


def _point(value):
    return int(value.x), int(value.y)


def _layer_name(board, layer_id):
    try:
        return board.GetLayerName(layer_id)
    except Exception:  # noqa: BLE001
        return str(layer_id)


def _track_row(track):
    start, end = track.GetStart(), track.GetEnd()
    return {
        "track": track,
        "uuid": _uuid(track),
        "net": track.GetNetname() or "",
        "layer_id": int(track.GetLayer()),
        "start": _point(start),
        "end": _point(end),
        "width_mm": track.GetWidth() / 1e6,
        "length_mm": math.hypot(end.x - start.x, end.y - start.y) / 1e6,
    }


def analyze_board(board, *, critical_nets=(), min_open_angle_deg=89.0,
                  track_uuid_scope=None):
    """Return deterministic acute-backtrack evidence for an open board.

    ``critical_nets`` promotes matching rows to blocking issues.  When
    ``track_uuid_scope`` is supplied, only vertices touching at least one of
    those track UUIDs are returned; this lets an in-flight generator audit just
    the copper it created without blaming pre-existing board residue.
    """
    critical = set(critical_nets or ())
    scope = None if track_uuid_scope is None else set(track_uuid_scope)
    rows = []
    for item in board.GetTracks():
        if item.GetClass() != "PCB_TRACK":
            continue
        row = _track_row(item)
        if not row["net"] or row["start"] == row["end"]:
            continue
        rows.append(row)

    junctions = defaultdict(list)
    for row in rows:
        for at, other in ((row["start"], row["end"]),
                          (row["end"], row["start"])):
            junctions[(row["net"], row["layer_id"], at)].append((row, other))

    # A reversible connector or flow-through protector can intentionally join
    # duplicate same-net lands *inside* a pad.  The copper shape owns that
    # junction, so an acute angle there is neither an exposed discontinuity nor
    # the pseudo-stub this audit is meant to catch.  Use KiCad's effective pad
    # geometry rather than a bounding box so shaped/THT pads are handled.
    pads = defaultdict(list)
    duplicate_pad_boxes = defaultdict(list)
    for footprint in board.GetFootprints():
        ref = footprint.GetReference() or ""
        footprint_pad_counts = defaultdict(int)
        for pad in footprint.Pads():
            net = pad.GetNetname() or ""
            if not net:
                continue
            for layer_id in pad.GetLayerSet().CuStack():
                try:
                    pads[(net, int(layer_id))].append(
                        (ref, pad.GetEffectiveShape(layer_id)))
                    footprint_pad_counts[(net, int(layer_id))] += 1
                except Exception:  # noqa: BLE001 -- one exotic pad must not hide other evidence
                    pass
        for key, count in footprint_pad_counts.items():
            if count >= 2:
                duplicate_pad_boxes[key].append((ref, footprint.GetBoundingBox()))

    try:
        import pcbnew
    except ImportError:  # pragma: no cover - analyze_board requires pcbnew in production
        pcbnew = None

    def same_net_pad_refs(net, layer_id, at):
        if pcbnew is None:
            return set()
        point = pcbnew.VECTOR2I(*at)
        refs = set()
        for ref, shape in pads.get((net, layer_id), ()):
            try:
                # KiCad 9 exposed ``Contains`` on some effective-shape
                # bindings; KiCad 10's generic SHAPE exposes point membership
                # as ``Collide``. Do not let an API-shape mismatch silently
                # turn every intentional in-pad junction into an exposed
                # backtrack.
                contains = (shape.Contains(point)
                            if hasattr(shape, "Contains")
                            else shape.Collide(point))
                if contains:
                    refs.add(ref)
            except Exception:  # noqa: BLE001
                continue
        return refs

    def inside_duplicate_pad_footprint(net, layer_id, at):
        if pcbnew is None:
            return False
        point = pcbnew.VECTOR2I(*at)
        for _ref, box in duplicate_pad_boxes.get((net, layer_id), ()):
            try:
                contains = (box.Contains(point)
                            if hasattr(box, "Contains")
                            else box.Collide(point))
                if contains:
                    return True
            except Exception:  # noqa: BLE001
                continue
        return False

    issues = []
    for (net, layer_id, at), incident in sorted(junctions.items()):
        # Branch points need graph/topology reasoning of their own.  Restrict
        # this detector to an unambiguous two-segment path vertex.
        unique = {}
        for row, other in incident:
            unique[row["uuid"] or id(row["track"])] = (row, other)
        if len(unique) != 2:
            continue
        (a, ao), (b, bo) = list(unique.values())
        uuids = sorted(u for u in (a["uuid"], b["uuid"]) if u)
        if scope is not None and not (scope & set(uuids)):
            continue
        va = (ao[0] - at[0], ao[1] - at[1])
        vb = (bo[0] - at[0], bo[1] - at[1])
        na, nb = math.hypot(*va), math.hypot(*vb)
        if na <= 0 or nb <= 0:
            continue
        cosine = max(-1.0, min(1.0,
            (va[0] * vb[0] + va[1] * vb[1]) / (na * nb)))
        opening = math.degrees(math.acos(cosine))
        if opening + 1e-7 >= min_open_angle_deg:
            continue
        covered = opening <= 5.0
        # Pad copper may legitimately absorb an acute duplicate-land closure,
        # but it does not make two collinear traces leaving the same pad in the
        # same direction intentional.  A wholly/partly covered launch is still
        # an acid-trap artifact and must be normalized before lock/fabrication.
        if (not covered
                and (same_net_pad_refs(net, layer_id, at)
                     or inside_duplicate_pad_footprint(net, layer_id, at))):
            continue
        # A reversible connector commonly exposes two separated physical pads
        # for one logical member.  A short V/U-shaped link between two pads on
        # that *same footprint* is intentional duplicate-pad closure, not a
        # route that approached a destination and doubled back.  Recognize the
        # ownership geometrically at both outer ends instead of waiving a
        # connector family or reference name.
        if (not covered
                and (same_net_pad_refs(net, layer_id, ao)
                     & same_net_pad_refs(net, layer_id, bo))):
            continue
        issue_type = "covered_backtrack" if covered else "acute_backtrack"
        issues.append({
            "type": issue_type,
            "severity": "blocking" if net in critical else "advisory",
            "net": net,
            "layer": _layer_name(board, layer_id),
            "at_mm": [round(at[0] / 1e6, 6), round(at[1] / 1e6, 6)],
            "neighbors_mm": [[round(ao[0] / 1e6, 6), round(ao[1] / 1e6, 6)],
                               [round(bo[0] / 1e6, 6), round(bo[1] / 1e6, 6)]],
            "opening_angle_deg": round(opening, 3),
            "path_turn_deg": round(180.0 - opening, 3),
            "track_uuids": uuids,
            "segment_lengths_mm": [round(a["length_mm"], 6),
                                     round(b["length_mm"], 6)],
            "widths_mm": sorted({round(a["width_mm"], 6),
                                  round(b["width_mm"], 6)}),
            "message": (
                f"{net} doubles back at {at[0]/1e6:.3f},"
                f"{at[1]/1e6:.3f} on {_layer_name(board, layer_id)} "
                f"(opening {opening:.1f}deg, path turn {180.0-opening:.1f}deg)"),
        })

    issues.sort(key=lambda row: (row["net"], row["layer"], row["at_mm"],
                                 row["type"], row["track_uuids"]))
    blocking = [row for row in issues if row["severity"] == "blocking"]
    return {
        "ok": not blocking,
        "issue_count": len(issues),
        "blocking_count": len(blocking),
        "advisory_count": len(issues) - len(blocking),
        "critical_nets": sorted(critical),
        "issues": issues,
    }


def analyze(board_path, *, critical_nets=(), min_open_angle_deg=89.0,
            track_uuid_scope=None, board=None):
    import pcbnew
    loaded = board or pcbnew.LoadBoard(board_path)
    result = analyze_board(
        loaded, critical_nets=critical_nets,
        min_open_angle_deg=min_open_angle_deg,
        track_uuid_scope=track_uuid_scope)
    result["board"] = os.path.abspath(board_path)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("board")
    parser.add_argument("--critical-net", action="append", default=[])
    parser.add_argument("--min-open-angle", type=float, default=89.0)
    parser.add_argument("--json", default="")
    args = parser.parse_args(argv)
    result = analyze(args.board, critical_nets=args.critical_net,
                     min_open_angle_deg=args.min_open_angle)
    payload = json.dumps(result, indent=2, sort_keys=True)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            handle.write(payload + "\n")
    print(payload)
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
