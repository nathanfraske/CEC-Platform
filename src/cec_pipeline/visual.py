"""Relevant native evidence coverage, not proof that a person/model looked.

Only saved copper is observed. This grants no electrical, current, thermal or
fabrication authority. Independent physical receivers remain mandatory.
"""

from __future__ import annotations

import time
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from .identity import digest, require
from .native import _native


def changed_copper(source, candidate, *, timeout_s=8.0):
    """Bind review regions to native material changes, including saved fills.

    Unchanged top-level objects cost no polygon work. A changed footprint is
    inspected pad by pad on every actual copper layer. Native set differences
    localize refill changes rather than demanding a whole-plane screenshot.
    Polygonization here is for conservative image framing, never clearance or
    material-capacity qualification; the native receivers provide that proof.
    """
    pcbnew, quiet = _native()
    import cec_additive_route_receiving as syntax
    import cec_native_fill_geometry as fills

    require(type(timeout_s) in (int, float) and 0 < timeout_s <= 10,
            "bounded_visual_observation_required")
    deadline = time.monotonic() + timeout_s
    boards = [pcbnew.LoadBoard(str(p)) for p in (source, candidate)]
    parsed = [syntax._nodes(p)[1] for p in (source, candidate)]
    changed = {u for u in parsed[0].keys() | parsed[1].keys()
               if parsed[0].get(u) != parsed[1].get(u)}
    require(len(changed) <= 4096, "bounded_visual_native_delta_required")
    layers = sorted({int(l) for b in boards for l in b.GetEnabledLayers().CuStack()})
    objects = []
    for board in boards:
        live = {str(i.m_Uuid.AsString()): i
                for i in [*board.GetTracks(), *board.GetFootprints(), *board.Zones()]}
        require(len(live) <= 24576, "bounded_visual_native_inventory_required")
        objects.append(live)

    def polygon(item, layer):
        require(time.monotonic() < deadline, "visual_native_delta_deadline")
        shape = pcbnew.SHAPE_POLY_SET()
        if item is None or not item.IsOnLayer(layer):
            return shape
        if item.GetClass() == "ZONE":
            if item.GetIsRuleArea():
                return shape
            require(item.IsFilled() and item.HasFilledPolysForLayer(layer),
                    "actual_saved_zone_fill_required_for_visual_review")
            return item.GetFilledPolysList(layer).CloneDropTriangulation()
        item.TransformShapeToPolygon(shape, layer, 0, 100,
                                     pcbnew.ERROR_OUTSIDE, False)
        return shape

    def box(shape):
        points = []
        for i in range(shape.OutlineCount()):
            ring = shape.COutline(i)
            points.extend((int(ring.CPoint(k).x), int(ring.CPoint(k).y))
                          for k in range(ring.PointCount()))
        require(points, "nonempty_changed_copper_region_required")
        return [min(x for x, y in points), min(y for x, y in points),
                max(x for x, y in points), max(y for x, y in points)]

    regions = []
    for uid in sorted(changed):
        old, new = [live.get(uid) for live in objects]
        if old is None and new is None:
            # Groups and text are not copper, and have their own transaction
            # ownership checks. They cannot supply copper review coverage.
            continue
        classes = {i.GetClass() for i in (old, new) if i is not None}
        require(len(classes) == 1, "visual_native_object_type_changed")
        kind = next(iter(classes))
        if kind == "FOOTPRINT":
            pads = [{str(p.m_Uuid.AsString()): p for p in f.Pads()} if f else {}
                    for f in (old, new)]
            pairs = [(p, pads[0].get(p), pads[1].get(p))
                     for p in sorted(pads[0].keys() | pads[1].keys())]
        else:
            require(kind in ("PCB_TRACK", "PCB_ARC", "PCB_VIA", "ZONE"),
                    "supported_native_visual_material_required")
            pairs = [(uid, old, new)]
        for item_uid, first, last in pairs:
            for layer in layers:
                a, b = [polygon(i, layer) for i in (first, last)]
                if fills.identity(a, deadline) == fills.identity(b, deadline):
                    continue
                removed = a.CloneDropTriangulation()
                removed.BooleanSubtract(b)
                inserted = b.CloneDropTriangulation()
                inserted.BooleanSubtract(a)
                for direction, shape in (("removed", removed), ("inserted", inserted)):
                    fills.identity(shape, deadline)
                    if shape.OutlineCount():
                        regions.append(dict(uuid=item_uid, owner_uuid=uid, kind=kind,
                                            layer=str(pcbnew.BOARD.GetStandardLayerName(layer)),
                                            direction=direction, region_nm=box(shape)))
    require(time.monotonic() < deadline, "visual_native_delta_deadline")
    require(regions, "actual_changed_copper_required_for_visual_review")
    result = dict(schema=1, complete=True, regions=regions,
                  scope="conservative_saved_copper_review_framing_only",
                  electrical_or_fabrication_qualified=False)
    result["sha256"] = digest(result)
    return result


def coverage(manifest, views):
    """Every material change must fit a relevant before/after native view.

    An overview on the wrong layer or a tiny unrelated crop cannot satisfy
    this. Several crops may cover separate objects; one crop must show each
    complete delta region so fragmented slivers cannot pretend to show a bend.
    """
    require(manifest.get("complete") is True and bool(manifest.get("regions")),
            "complete_native_visual_delta_required")
    require(type(views) is list and 1 <= len(views) <= 64,
            "bounded_native_visual_views_required")
    missing = []
    for row in manifest["regions"]:
        a, b, c, d = row["region_nm"]
        found = False
        for view in views:
            bounds = view.get("region_nm")
            if (view.get("layer") == row["layer"] and type(bounds) is list
                    and len(bounds) == 4 and all(type(v) is int for v in bounds)
                    and bounds[0] <= a and bounds[1] <= b
                    and bounds[2] >= c and bounds[3] >= d):
                found = True
                break
        if not found:
            missing.append(row)
    return dict(ok=not missing, complete=True, missing=missing,
                changed_regions=len(manifest["regions"]), views=len(views),
                evidence_relevance_only=True, model_attention_proved=False)


def default_region(manifest, *, padding_nm=1000000):
    rows = [r["region_nm"] for r in manifest["regions"]]
    return [min(r[0] for r in rows) - padding_nm,
            min(r[1] for r in rows) - padding_nm,
            max(r[2] for r in rows) + padding_nm,
            max(r[3] for r in rows) + padding_nm]


def verify_views(proof, manifest, directory):
    """Receive view metadata against the actual framed SVGs, not prose claims."""
    from .legacy import bootstrap

    bootstrap()
    import cec_suite_inspection as inspection

    require(proof.get("schema") == 2, "native_visual_coverage_schema_required")
    views = proof.get("views")
    covered = coverage(manifest, views)
    all_hashes = {}
    keys = set()
    for view in views:
        layer, region, guide = view.get("layer"), view.get("region_nm"), view.get("guide")
        require(layer in ("F.Cu", "In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu", "B.Cu")
                and guide in (None, "F.Fab", "B.Fab", "F.Silkscreen", "B.Silkscreen")
                and type(region) is list and len(region) == 4
                and all(type(v) is int and abs(v) <= 2000000000 for v in region)
                and region[0] < region[2] and region[1] < region[3],
                "literal_native_visual_view_required")
        key = digest(dict(layer=layer, region_nm=region, guide=guide))[:16]
        require(view.get("key") == key and key not in keys, "unique_bound_native_visual_view_required")
        keys.add(key)
        expected = {side + "-" + layer.replace(".", "-") + "-" + key + ".svg"
                    for side in ("before", "after")}
        hashes = view.get("plot_hashes")
        require(type(hashes) is dict and set(hashes) == expected,
                "exact_before_after_native_view_pair_required")
        for name, identity in hashes.items():
            target = Path(directory) / name
            require(type(identity) is str and re.fullmatch(r"[a-f0-9]{64}", identity)
                    and target.is_file() and inspection.sha(target) == identity,
                    "native_visual_plot_changed")
            try:
                root = ET.parse(target).getroot()
                raw = root.attrib["viewBox"].split()
                actual = [Decimal(v) * 1000000 for v in raw]
            except (ET.ParseError, KeyError, InvalidOperation) as exc:
                raise ValueError("native_visual_svg_viewport_required") from exc
            wanted = [region[0], region[1], region[2] - region[0], region[3] - region[1]]
            require(root.tag == "{http://www.w3.org/2000/svg}svg" and actual == wanted,
                    "native_visual_viewport_does_not_match_claimed_region")
            all_hashes[name] = identity
    require(proof.get("plot_hashes") == all_hashes,
            "native_visual_plot_inventory_must_match_views")
    require(covered["ok"], "changed_copper_not_covered_by_native_review_views")
    return covered
