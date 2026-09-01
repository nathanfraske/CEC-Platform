#!/usr/bin/env python3
"""Project detailed-router refusal certificates back into placement search.

The detailed completion stage knows *why* a short connection was refused, but
placement historically discarded that evidence and began the next wave from
generic congestion alone.  This module converts certificate endpoints and
pad blockers into board-agnostic component hints.  It never accepts a move;
the ordinary exact courtyard, bypass, pair, and negotiated-capacity authorities
remain the adoption boundary.
"""

from __future__ import annotations

import copy
import json
import math
from collections import defaultdict


SCHEMA = 1
_DIRECTIONS = {"E", "NE", "N", "NW", "W", "SW", "S", "SE"}


def _payload(data):
    row = data or {}
    if not isinstance(row, dict):
        return {}
    if isinstance(row.get("best"), dict):
        row = row["best"]
    if isinstance(row.get("completion_report"), dict):
        row = row["completion_report"]
    if isinstance(row.get("import_report"), dict):
        row = row["import_report"]
    return row


def refusal_certificates(data):
    """Return unique certificate-bearing refusal details from any report form."""
    payload = _payload(data)
    reports = []
    for name in ("final_completion", "lastmile"):
        if isinstance(payload.get(name), dict):
            reports.append(payload[name])
    if isinstance(payload.get("refused_details"), list):
        reports.append(payload)
    rows, seen = [], set()
    for report in reports:
        for detail in report.get("refused_details") or ():
            certificate = detail.get("certificate") or {}
            if not isinstance(certificate, dict) or not certificate:
                continue
            key = json.dumps(certificate, sort_keys=True,
                             separators=(",", ":"), default=str)
            if key in seen:
                continue
            seen.add(key)
            rows.append((detail, certificate))
    rows.sort(key=lambda row: (
        float(row[0].get("distance_mm") or 1e9),
        str(row[1].get("net") or row[0].get("net") or "")))
    return rows


def _endpoint_clear_rays(certificate):
    rays = defaultdict(set)
    for layer in certificate.get("layers") or ():
        for escape in layer.get("endpoint_escape") or ():
            endpoint = str(escape.get("endpoint") or "")
            rays[endpoint].update(
                str(value) for value in (escape.get("clear_rays") or ())
                if str(value) in _DIRECTIONS)
    return rays


def placement_hints(data, *, critical_nets=()):
    """Return deterministic ref-level hints, without board-specific refdes rules."""
    critical = {str(net) for net in critical_nets or ()}
    aggregate = {}
    certificates = refusal_certificates(data)
    for detail, certificate in certificates:
        net = str(certificate.get("net") or detail.get("net") or "")
        distance = max(0.05, float(detail.get("distance_mm") or 1000.0))
        base = int(round(10000.0 / distance))
        if net in critical or net.rsplit("/", 1)[-1] in critical:
            base += 1000000
        endpoints = list(certificate.get("endpoints") or ())
        midpoint = None
        points = [(float(row["x_mm"]), float(row["y_mm"]))
                  for row in endpoints
                  if row.get("x_mm") is not None and row.get("y_mm") is not None]
        if points:
            midpoint = [sum(x for x, _y in points) / len(points),
                        sum(y for _x, y in points) / len(points)]
        clear_rays = _endpoint_clear_rays(certificate)
        for endpoint in endpoints:
            ref = str(endpoint.get("ref") or "")
            if not ref:
                continue
            key = (ref, "refused_endpoint")
            row = aggregate.setdefault(key, {
                "ref": ref, "role": "refused_endpoint", "score": 0,
                "nets": set(), "directions": set(), "anchors": []})
            row["score"] += base + 250000
            row["nets"].add(net)
            row["directions"].update(
                clear_rays.get(str(endpoint.get("endpoint") or ""), ()))
            if endpoint.get("x_mm") is not None and endpoint.get("y_mm") is not None:
                row["anchors"].append([
                    float(endpoint["x_mm"]), float(endpoint["y_mm"])])
        for blocker in certificate.get("dominant_blockers") or ():
            if blocker.get("kind") != "pad" or not blocker.get("ref"):
                continue
            ref = str(blocker["ref"])
            hits = max(1, int(blocker.get("hit_count") or 1))
            key = (ref, "foreign_pad_blocker")
            row = aggregate.setdefault(key, {
                "ref": ref, "role": "foreign_pad_blocker", "score": 0,
                "nets": set(), "directions": set(), "anchors": []})
            row["score"] += base + hits * 50000
            row["nets"].add(net)
            if midpoint is not None:
                row["anchors"].append(midpoint)
    hints = []
    for row in aggregate.values():
        hints.append({
            "ref": row["ref"], "role": row["role"],
            "score": int(row["score"]), "nets": sorted(row["nets"]),
            "directions": sorted(row["directions"]),
            "anchors": [[round(float(x), 6), round(float(y), 6)]
                        for x, y in row["anchors"][:8]],
        })
    hints.sort(key=lambda row: (-row["score"], row["ref"], row["role"]))
    return {"schema": SCHEMA, "certificate_count": len(certificates),
            "hint_count": len(hints), "hints": hints}


def power_planner_failures(data):
    """Recover compact exact-power failures from route or authority reports.

    Post-priority power planning happens after the placement preflight, so its
    exact via-field/corridor certificate is strictly more informed than the
    earlier empty-board raster.  Candidate summaries historically retained
    only the exception text and stranded that certificate in a sibling JSON
    artifact.  Accept the explicit feedback field as well as the native power
    authority shape so the same projection works for live results, imported
    reports, and forensic replay.
    """
    failures = {}
    visited = set()

    def accept(mapping):
        if not isinstance(mapping, dict):
            return
        for net, failure in sorted(mapping.items(), key=lambda row: str(row[0])):
            if not isinstance(failure, dict):
                continue
            bottleneck = failure.get("planner_bottleneck") or {}
            if not isinstance(bottleneck, dict) or not bottleneck.get("kind"):
                continue
            name = str(net or bottleneck.get("net") or "")
            if not name or name in failures:
                continue
            normalized = copy.deepcopy(failure)
            normalized_bottleneck = dict(normalized["planner_bottleneck"])
            normalized_bottleneck.setdefault("net", name)
            normalized["planner_bottleneck"] = normalized_bottleneck
            failures[name] = normalized

    def visit(row):
        if not isinstance(row, dict) or id(row) in visited:
            return
        visited.add(id(row))
        accept(row.get("power_planner_failures"))
        compile_failure = row.get("compile_failure") or {}
        if isinstance(compile_failure, dict):
            accept(compile_failure.get("report"))
        for key in ("blocker_evidence", "detail", "best",
                    "completion_report", "import_report"):
            visit(row.get(key))
        for candidate in row.get("candidates") or ():
            visit(candidate)
        for event in row.get("stage_trace") or ():
            visit(event)

    visit(data or {})
    return failures


def augment_placement_evidence(evidence, completion, *, critical_nets=()):
    """Attach downstream route certificates to placement evidence."""
    result = copy.deepcopy(dict(evidence or {}))
    projected = placement_hints(completion, critical_nets=critical_nets)
    power_failures = power_planner_failures(completion)
    projected["power_planner_failure_count"] = len(power_failures)
    projected["power_planner_failure_nets"] = sorted(power_failures)
    result["completion_evidence"] = projected
    if power_failures:
        power_body = dict(result.get("power_body_clearance") or {})
        merged = dict(power_body.get("planner_failures") or {})
        # Route-time evidence includes the actual locked priority prefix and
        # therefore supersedes a same-net empty-placement preflight result.
        merged.update(power_failures)
        power_body["planner_failures"] = merged
        power_body["error"] = power_body.get("error") or (
            "post-priority exact power planner refused")
        result["power_body_clearance"] = power_body
    return result
