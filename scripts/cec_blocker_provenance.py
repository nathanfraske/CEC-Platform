#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Evidence-qualified blocker records for PCB pipeline failures.

KiCad final DRC says what is wrong. Placement preflight, precision routing,
detailed routing, repair, and signoff say when related evidence was observed.
Those are not automatically the same thing: a final clearance violation does
not prove which pass created either copper item. This module keeps that
distinction explicit while giving waves and the dashboard one joinable schema.

Each causal-chain row is observed, attributed by exact UUID, or merely
associated by a shared net/reference. The module is JSON-only so host-side
dashboard code can import it without initializing pcbnew.
"""
from __future__ import annotations

import hashlib
import json
import re


SCHEMA = 1
JOIN_DETAIL_INLINE_BYTES = 4096
_NET_RE = re.compile(r"\[([^\]]+)\]")
_REF_RE = re.compile(r"\bof\s+([^\s,;]+)")


def _json_key(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, default=str)


def _stable_id(kind, rule, items):
    identity = {
        "kind": kind,
        "rule": rule,
        "items": [{
            "uuid": row.get("uuid"),
            "description": row.get("description"),
            "pos": row.get("pos"),
        } for row in items],
    }
    return "blk-" + hashlib.sha256(
        _json_key(identity).encode("utf-8")).hexdigest()[:16]


def _tokens(items):
    nets, refs, uuids, positions = set(), set(), set(), []
    clean = []
    for source in items or ():
        row = dict(source or {})
        description = str(row.get("description") or "")
        nets.update(_NET_RE.findall(description))
        refs.update(_REF_RE.findall(description))
        if row.get("uuid"):
            uuids.add(str(row["uuid"]))
        pos = row.get("pos") or {}
        try:
            positions.append([float(pos["x"]), float(pos["y"])])
        except (KeyError, TypeError, ValueError):
            pass
        clean.append({key: row.get(key) for key in
                      ("uuid", "description", "pos")
                      if row.get(key) is not None})
    return {
        "nets": sorted(nets), "refs": sorted(refs),
        "uuids": sorted(uuids), "positions_mm": positions,
        "items": clean,
    }


def _final_blocker(kind, rule, description, items, *, authority,
                   severity="blocking"):
    evidence = _tokens(items)
    blocker_id = _stable_id(kind, rule, evidence["items"])
    event = {
        "stage": "final_signoff", "status": "failed",
        "authority": authority, "certainty": "observed",
        "message": description or rule,
        "nets": evidence["nets"], "refs": evidence["refs"],
        "uuids": evidence["uuids"],
    }
    return {
        "schema": SCHEMA, "id": blocker_id, "kind": kind,
        "rule": rule, "message": description or rule,
        **evidence, "causal_chain": [event],
        "severity": str(severity),
        "blocking": str(severity) == "blocking",
        "origin_known": False,
        "next_action": "trace generated item ownership or repair final geometry",
    }


def final_blockers(drc_data, *, topology=None, structural_filter=None):
    """Build exact final blockers from one KiCad DRC authority."""
    violations = list((drc_data or {}).get("violations") or ())
    if structural_filter is not None:
        violations = list(structural_filter(violations) or ())
    blockers = []
    for violation in violations:
        blockers.append(_final_blocker(
            "structural_drc", str(violation.get("type") or "unknown"),
            str(violation.get("description") or violation.get("type") or
                "structural DRC violation"),
            violation.get("items") or (), authority="kicad_drc"))
    for violation in (drc_data or {}).get("unconnected_items") or ():
        blockers.append(_final_blocker(
            "unconnected",
            str(violation.get("type") or "unconnected_items"),
            str(violation.get("description") or "unconnected copper"),
            violation.get("items") or (), authority="kicad_connectivity"))
    for issue in (topology or {}).get("issues") or ():
        pos = issue.get("at_mm") or ()
        pos = ({"x": pos[0], "y": pos[1]} if len(pos) == 2 else None)
        items = [{"uuid": uuid, "description": issue.get("message"),
                  "pos": pos}
                 for uuid in (issue.get("track_uuids") or ())]
        if not items:
            items = [{"description": issue.get("message"), "pos": pos}]
        blocker = _final_blocker(
            ("route_topology" if issue.get("severity") == "blocking"
             else "route_topology_advisory"),
            str(issue.get("kind") or "route_topology"),
            str(issue.get("message") or "route topology defect"), items,
            authority="cec_route_quality",
            severity=("blocking" if issue.get("severity") == "blocking"
                      else "advisory"))
        if issue.get("net"):
            blocker["nets"] = sorted(set(blocker["nets"]) |
                                     {str(issue["net"])})
            blocker["causal_chain"][0]["nets"] = blocker["nets"]
        blockers.append(blocker)
    blockers.sort(key=lambda row: (row["kind"], row["rule"], row["id"]))
    return blockers


def observed_blocker(kind, rule, message, *, authority, nets=(), refs=(),
                     uuids=(), detail=None, severity="blocking"):
    """Create a non-DRC final observation with the same joinable schema."""
    items = [{"uuid": uuid, "description": message}
             for uuid in sorted({str(value) for value in uuids if value})]
    if not items:
        items = [{"description": message}]
    row = _final_blocker(
        str(kind), str(rule), str(message), items,
        authority=str(authority), severity=severity)
    row["nets"] = sorted({str(value) for value in nets if value})
    row["refs"] = sorted({str(value) for value in refs if value})
    row["causal_chain"][0]["nets"] = row["nets"]
    row["causal_chain"][0]["refs"] = row["refs"]
    # Unlike a raw final DRC row, this record is emitted by the stage that owns
    # the failing authority (thermal injection, placement craft, route gate,
    # and so on).  Its origin is therefore exact even when the failure has no
    # copper UUID, such as a dropped current source.
    row["origin_known"] = True
    row["causal_chain"][0]["certainty"] = "attributed"
    row["next_action"] = (
        "repair or rerun the attributed authority, then repeat signoff")
    if detail is not None:
        row["detail"] = detail
    return row


def normalize_event(stage, status, message, *, authority="pipeline",
                    nets=(), refs=(), uuids=(), artifact=None,
                    certainty="observed", detail=None):
    """Create a compact, JSON-safe pipeline event."""
    row = {
        "stage": str(stage), "status": str(status),
        "authority": str(authority), "certainty": str(certainty),
        "message": str(message),
        "nets": sorted({str(value) for value in (nets or ()) if value}),
        "refs": sorted({str(value) for value in (refs or ()) if value}),
        "uuids": sorted({str(value) for value in (uuids or ()) if value}),
    }
    if artifact:
        row["artifact"] = str(artifact)
    if detail is not None:
        row["detail"] = detail
    return row


def join_events(blockers, events):
    """Attach upstream evidence without overclaiming causal origin.

    A detailed-route refusal can carry tens of kilobytes of exact search
    certificates.  The authoritative copy already lives in ``stage_trace``;
    embedding it again in every blocker on the same net made one modest Hub
    oracle exceed 50 MiB.  Large details are therefore joined by a stable
    stage-trace reference and digest.  Small details remain inline so compact
    consumers retain the convenient self-contained record.
    """
    out = [dict(row, causal_chain=list(row.get("causal_chain") or ()))
           for row in (blockers or ())]
    for event_index, source in enumerate(events or ()):
        event = dict(source or {})
        if "detail" in event:
            serialized = _json_key(event["detail"]).encode("utf-8")
            if len(serialized) > JOIN_DETAIL_INLINE_BYTES:
                event.pop("detail", None)
                event["detail_ref"] = {
                    "scope": "stage_trace",
                    "index": event_index,
                    "sha256": hashlib.sha256(serialized).hexdigest(),
                    "bytes": len(serialized),
                }
        event_uuids = set(event.get("uuids") or ())
        event_nets = set(event.get("nets") or ())
        event_refs = set(event.get("refs") or ())
        for blocker in out:
            uuid_match = bool(event_uuids & set(blocker.get("uuids") or ()))
            weak_match = bool(event_nets & set(blocker.get("nets") or ()) or
                              event_refs & set(blocker.get("refs") or ()))
            if not uuid_match and not weak_match:
                continue
            joined = dict(event)
            joined["certainty"] = (
                "attributed" if uuid_match else "associated")
            blocker["causal_chain"].insert(0, joined)
            if uuid_match:
                blocker["origin_known"] = True
                blocker["next_action"] = (
                    "repair or rerun the attributed stage, then repeat signoff")
    return out


def failure_blocker(stage_trace, error):
    """Represent a fail-closed run that produced no final board."""
    error = str(error or "pipeline produced no board")
    stage = str(stage_trace[-1].get("stage")
                if stage_trace else "pipeline")
    blocker_id = "blk-" + hashlib.sha256(
        (stage + "\0" + error).encode("utf-8")).hexdigest()[:16]
    return {
        "schema": SCHEMA, "id": blocker_id, "kind": "pipeline_refusal",
        "rule": stage, "message": error,
        "nets": [], "refs": [], "uuids": [], "positions_mm": [], "items": [],
        "causal_chain": list(stage_trace or ()),
        "origin_known": bool(stage_trace),
        "next_action": (
            "resolve the last failed stage and rerun from its input artifact"),
    }


def compact_summary(blockers):
    blockers = list(blockers or ())
    by_kind = {}
    known = 0
    blocking = []
    for row in blockers:
        kind = row.get("kind", "unknown")
        by_kind[kind] = by_kind.get(kind, 0) + 1
        known += bool(row.get("origin_known"))
        if row.get("blocking", True):
            blocking.append(row)
    blocking_known = sum(bool(row.get("origin_known")) for row in blocking)
    return {
        "schema": SCHEMA, "count": len(blockers), "by_kind": by_kind,
        "blocking_count": len(blocking),
        "advisory_count": len(blockers) - len(blocking),
        "origin_attributed": known,
        "origin_unattributed": len(blockers) - known,
        "full_fail_stack": bool(blocking) and blocking_known == len(blocking),
    }
