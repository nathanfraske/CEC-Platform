"""Receive actual craft defects, not interchangeable aggregate counts.

UUIDs, prose and serialization order are not defect identities. Native loci,
net, face and defect kind are. Moving an unresolved defect is not repairing it.
This is conservative aesthetic nonregression, not electrical qualification.
"""

from __future__ import annotations

import math

from .identity import digest, require


def _number(value):
    require(type(value) in (int, float) and math.isfinite(value),
            "finite_craft_measurement_required")
    return value


def _point(value):
    require(type(value) in (list, tuple) and len(value) == 2,
            "exact_craft_location_required")
    # Picometres preserve half-nanometre junction midpoints without a snapping
    # tolerance that could move a defect onto its innocent neighbour.
    return [round(_number(v) * 1_000_000_000) for v in value]


def _rows(report):
    require(type(report) is dict and report.get("complete") is True
            and report.get("track_uuid_scope") is None and not report.get("error"),
            "complete_whole_board_craft_observation_required")
    contours = report.get("power_contours")
    require(type(contours) is dict and contours.get("complete") is True
            and not contours.get("error"), "complete_power_contour_observation_required")
    result = []
    for family, container, key, count in (
        ("route", report, "issues", "issue_count"),
        ("heading", report, "non_octilinear", "non_octilinear_count"),
        ("power", contours, "findings", "finding_count"),
    ):
        values = container.get(key)
        require(type(values) is list and len(values) <= 4096
                and type(container.get(count)) is int and container[count] == len(values),
                "complete_consistent_craft_inventory_required")
        for row in values:
            require(type(row) is dict, "typed_craft_finding_required")
            result.append((family, row))
    return result


def inventory(report, board=None):
    """Canonical typed observations with exact native fallback for arcs/zones.

    Most diagnostics already carry physical loci. Native objects are needed
    only for the older arc and rounded-zone diagnostics lacking coordinates.
    No refill, mutation, route search or extra native board load occurs here.
    """
    tracks = zones = None
    records = []
    for family, row in _rows(report):
        kind, net, layer = (row.get(k) for k in ("type", "net", "layer"))
        require(all(type(v) is str and v for v in (kind, net, layer)),
                "literal_craft_kind_net_face_required")
        if row.get("at_mm") is not None:
            locus = dict(at_pm=_point(row["at_mm"]))
        elif row.get("start_mm") is not None and row.get("end_mm") is not None:
            locus = dict(ends_pm=sorted((_point(row["start_mm"]), _point(row["end_mm"]))))
        elif kind == "curved_trace" and board is not None:
            if tracks is None:
                tracks = {str(t.m_Uuid.AsString()): t for t in board.GetTracks()}
            item = tracks.get(row.get("uuid"))
            require(item is not None and item.GetClass() == "PCB_ARC",
                    "native_craft_arc_required")
            locus = dict(ends_nm=sorted(([int(p.x), int(p.y)] for p in
                                        (item.GetStart(), item.GetEnd()))),
                         mid_nm=[int(item.GetMid().x), int(item.GetMid().y)])
        elif kind == "rounded_compact_zone_landing" and board is not None:
            if zones is None:
                zones = {str(z.m_Uuid.AsString()): z for z in board.Zones()}
            ids = row.get("zone_uuids")
            require(type(ids) is list and len(ids) == 1 and ids[0] in zones,
                    "native_craft_zone_required")
            box = zones[ids[0]].Outline().BBox()
            locus = dict(bounds_nm=[int(box.GetX()), int(box.GetY()),
                                    int(box.GetRight()), int(box.GetBottom())],
                         outline_sha256=digest(zones[ids[0]].Outline().Format()))
        else:
            raise ValueError("unlocated_craft_finding_refuses_nonregression:" + kind)
        # Each score is badness: greater is worse. No weighted sum lets one
        # symptom compensate for another. Unknown new diagnostics must acquire
        # explicit semantics rather than silently gaining an acceptance rule.
        metrics = {}
        if kind in {"acute_backtrack", "covered_backtrack", "acute_branch_junction",
                    "offset_covered_contact", "offset_acute_contact"}:
            require("opening_angle_deg" in row, "complete_craft_opening_angle_required")
        if kind == "non_octilinear_segment":
            require("heading_error_nm" in row, "complete_craft_heading_error_required")
        if "opening_angle_deg" in row:
            metrics["acute_angle_deficit_deg"] = max(0, 90 - _number(row["opening_angle_deg"]))
        if "heading_error_nm" in row:
            metrics["heading_error_nm"] = _number(row["heading_error_nm"])
        if kind == "short_wide_capsule":
            metrics["cap_extension_mm"] = _number(row["cap_extension_mm"])
            metrics["length_width_deficit"] = 1 - _number(row["length_width_ratio"])
        if kind == "unequal_width_round_join":
            narrow = _number(row["narrow_width_mm"])
            require(narrow > 0, "positive_craft_join_width_required")
            metrics["width_ratio"] = _number(row["width_mm"]) / narrow
        if kind == "rounded_compact_zone_landing":
            metrics["noncanonical_edges"] = _number(row["noncanonical_edges"])
        if kind == "reverse_diagonal_jog":
            lengths = row.get("segment_lengths_mm")
            require(type(lengths) is list and len(lengths) == 3,
                    "complete_craft_jog_lengths_required")
            metrics["reverse_run_mm"] = _number(lengths[1])
        known = {"acute_backtrack", "covered_backtrack", "acute_branch_junction",
                 "offset_covered_contact", "offset_acute_contact", "reverse_diagonal_jog",
                 "non_octilinear_segment", "curved_trace", "short_wide_capsule",
                 "unequal_width_round_join", "wide_round_elbow", "wide_exposed_terminal_cap",
                 "rounded_compact_zone_landing"}
        require(kind in known, "craft_finding_has_no_receiving_semantics:" + kind)
        severity = row.get("severity")
        require(severity in ("review", "advisory", "blocking"),
                "typed_craft_severity_required")
        metrics["blocking"] = int(severity == "blocking")
        anchor = dict(family=family, type=kind, net=net, layer=layer, **locus)
        # Geometry which lacks an ordered badness metric may not silently
        # change under an inherited identity. UUIDs and human prose are never
        # used. Dimension lists are sorted to ignore incident iteration order.
        residual = {key: row[key] for key in ("width_mm", "widths_mm", "narrow_width_mm",
                    "neighbors_mm", "junction_degree", "reversed_axes") if key in row}
        for key in ("widths_mm", "neighbors_mm", "reversed_axes"):
            if key in residual:
                residual[key] = sorted(residual[key])
        # Hashing also rejects non-finite nested geometry.
        row["semantic_id"] = digest(anchor)
        records.append(dict(id=digest(anchor), anchor=anchor, metrics=metrics,
                            residual_sha256=digest(residual)))
    records.sort(key=digest)
    return dict(schema=1, complete=True, findings=records,
                finding_count=len(records), release_authority=False)


def compare(before, after, *, target_ids=()):
    """Reject new/worsened symptoms and require explicit targets to disappear."""
    try:
        for value in (before, after):
            require(type(value) is dict and type(value.get("schema")) is int and value["schema"] == 1
                    and value.get("complete") is True
                    and type(value.get("findings")) is list
                    and type(value.get("finding_count")) is int
                    and value["finding_count"] == len(value["findings"])
                    and len(value["findings"]) <= 12288,
                    "complete_semantic_craft_inventory_required")
            for row in value["findings"]:
                require(type(row) is dict and set(row) ==
                        {"id", "anchor", "metrics", "residual_sha256"}
                        and row["id"] == digest(row["anchor"])
                        and type(row["metrics"]) is dict
                        and type(row["residual_sha256"]) is str
                        and len(row["residual_sha256"]) == 64,
                        "exact_semantic_craft_record_required")
                for score in row["metrics"].values():
                    _number(score)
        require(type(target_ids) in (list, tuple) and len(target_ids) <= 32
                and len(set(target_ids)) == len(target_ids)
                and all(type(key) is str and len(key) == 64 for key in target_ids),
                "bounded_exact_craft_targets_required")
        old = {}
        for row in before["findings"]:
            old.setdefault(row["id"], []).append(row)
        new_ids = {row["id"] for row in after["findings"]}
        require(set(target_ids) <= old.keys(), "craft_target_not_in_exact_source")
        unmatched = []
        for row in after["findings"]:
            matches = old.get(row["id"], [])
            # Preserve multiplicity and exact dimensions; no global count
            # compensation or nearest-neighbour matching across the board.
            winner = next((i for i, prior in enumerate(matches)
                if prior["residual_sha256"] == row["residual_sha256"]
                and prior["metrics"].keys() == row["metrics"].keys()
                and all(score <= prior["metrics"][key]
                        for key, score in row["metrics"].items())), None)
            if winner is None:
                unmatched.append(row)
            else:
                matches.pop(winner)
        remaining = sorted(set(target_ids) & new_ids)
        return dict(ok=not unmatched and not remaining, complete=True,
                    new_or_worsened=unmatched, uncleared_targets=remaining,
                    cleared_ids=sorted({r["id"] for r in before["findings"]} - new_ids),
                    inherited_finding_count=len(after["findings"]) - len(unmatched),
                    source_finding_count=before["finding_count"],
                    candidate_finding_count=after["finding_count"],
                    review_nonregression_only=True, release_authority=False)
    except (ValueError, TypeError, KeyError) as exc:
        return dict(ok=False, complete=False, errors=[str(exc)], release_authority=False)
