#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""One monotonic admission contract for every physical-design mutation.

Count-only gates are unsafe for an iterative PCB pipeline.  A pass can remove
one old clearance, create a different short, and still look numerically better.
This module compares the identities behind those counts so every caller makes
the same decision and emits the same forensic evidence.

The contract deliberately uses the affected-net set for ratlines instead of
KiCad's selected endpoint pair.  KiCad may select a different representative
endpoint for an unchanged disconnected island after a save; net identity plus
ratline count is stable across that harmless re-selection.
"""
from __future__ import annotations

import json
from collections.abc import Mapping


SCHEMA = 1


def _value(source, name, default=None):
    if isinstance(source, Mapping):
        return source.get(name, default)
    return getattr(source, name, default)


def _detail(source):
    value = _value(source, "detail", {})
    return value if isinstance(value, Mapping) else {}


def _canonical_identity(violation):
    kind = str(violation.get("type") or "unknown")
    uuids = sorted(
        str(item.get("uuid") or "")
        for item in (violation.get("items") or ())
        if item.get("uuid"))
    if uuids:
        identity = [kind, "uuid", uuids]
    else:
        fallback = sorted([
            str(item.get("description") or ""),
            round(float((item.get("pos") or {}).get("x") or 0.0), 4),
            round(float((item.get("pos") or {}).get("y") or 0.0), 4),
        ] for item in (violation.get("items") or ()))
        identity = [kind, "fallback",
                    str(violation.get("description") or ""), fallback]
    return json.dumps(identity, sort_keys=True, separators=(",", ":"))


def structural_drc_identities(metrics):
    """Return stable, JSON-safe identities from scorer-authoritative DRC rows."""
    detail = _detail(metrics)
    return sorted({
        _canonical_identity(row)
        for row in (detail.get("structural_violations") or ())
    })


def snapshot(metrics):
    """Normalize a Metrics instance or legacy metric mapping for comparison."""
    detail = _detail(metrics)
    nets = (_value(metrics, "unconn_nets", None)
            or _value(metrics, "unconnected_nets", None)
            or detail.get("unconn_nets") or ())
    identities = _value(metrics, "structural_drc_identities", None)
    if identities is None:
        identities = structural_drc_identities(metrics)
    raw_types = _value(metrics, "drc_types", None)
    if raw_types is None:
        raw_types = {}
        for violation in (detail.get("structural_violations") or ()):
            kind = str(violation.get("type") or "unknown")
            raw_types[kind] = int(raw_types.get(kind, 0)) + 1
    return {
        "drc": int(_value(metrics, "drc", 0) or 0),
        "drc_types": {
            str(kind): int(count)
            for kind, count in dict(raw_types or {}).items()},
        "unconnected": int(_value(metrics, "unconnected", 0) or 0),
        "unconn_nets": sorted({str(net) for net in nets if net}),
        "kelvin_ok": bool(_value(metrics, "kelvin_ok", False)),
        "diffpair_ok": bool(_value(metrics, "diffpair_ok", False)),
        "structural_drc_identities": sorted({
            str(identity) for identity in (identities or ())}),
        "unconn_signature_sha256": str(
            _value(metrics, "unconn_signature_sha256", None)
            or detail.get("unconn_signature_sha256") or ""),
    }


def _identity_kind(identity):
    try:
        row = json.loads(identity)
    except (TypeError, ValueError):
        return ""
    return str(row[0] or "") if isinstance(row, list) and row else ""


def evaluate(before, after, *, require_strict=False,
             preserve_unconnected=False, allow_unconnected_growth=False,
             allowed_new_unconnected_nets=(), allowed_new_drc_types=()):
    """Compare two board scores and return a complete admission decision.

    ``require_strict`` is for repair candidates: at least one structural count
    must improve.  Finishing passes normally allow a debt-neutral mutation.
    ``preserve_unconnected`` is for cosmetic passes that have no authority to
    change routing topology at all.
    """
    old = snapshot(before)
    new = snapshot(after)
    old_nets = set(old["unconn_nets"])
    new_nets = set(new["unconn_nets"])
    old_faults = set(old["structural_drc_identities"])
    new_faults = set(new["structural_drc_identities"])
    allowed_nets = {str(net) for net in allowed_new_unconnected_nets if net}
    allowed_drc = {str(kind) for kind in allowed_new_drc_types if kind}
    all_new_unconnected_nets = sorted(new_nets - old_nets)
    new_unconnected_nets = sorted(
        set(all_new_unconnected_nets) - allowed_nets)
    all_new_drc_identities = sorted(new_faults - old_faults)
    new_drc_identities = sorted(
        identity for identity in all_new_drc_identities
        if _identity_kind(identity) not in allowed_drc)

    old_effective_drc = old["drc"] - sum(
        old["drc_types"].get(kind, 0) for kind in allowed_drc)
    new_effective_drc = new["drc"] - sum(
        new["drc_types"].get(kind, 0) for kind in allowed_drc)

    reasons = []
    if old["kelvin_ok"] and not new["kelvin_ok"]:
        reasons.append("kelvin_gate_regressed")
    if old["diffpair_ok"] and not new["diffpair_ok"]:
        reasons.append("diffpair_gate_regressed")
    if (new["unconnected"] > old["unconnected"]
            and not allow_unconnected_growth):
        reasons.append("unconnected_regressed")
    if new_unconnected_nets:
        reasons.append("new_unconnected_nets")
    if preserve_unconnected and (
            new["unconnected"] != old["unconnected"]
            or new_nets != old_nets):
        reasons.append("unconnected_identity_changed")
    if new_effective_drc > old_effective_drc:
        reasons.append("drc_regressed")
    if new_drc_identities:
        reasons.append("new_structural_drc_identity")
    if (require_strict and not reasons
            and (new["unconnected"], new["drc"])
            >= (old["unconnected"], old["drc"])):
        reasons.append("no_structural_improvement")

    decision = (reasons[0] if reasons else
                ("strict_structural_improvement" if require_strict
                 else "structural_debt_monotonic"))
    return {
        "schema": SCHEMA,
        "accepted": not reasons,
        "decision": decision,
        "reasons": reasons,
        "before": old,
        "after": new,
        "new_unconnected_nets": new_unconnected_nets,
        "allowed_new_unconnected_nets": sorted(
            set(all_new_unconnected_nets) & allowed_nets),
        "new_structural_drc_identities": new_drc_identities,
        "allowed_new_structural_drc_identities": sorted(
            set(all_new_drc_identities) - set(new_drc_identities)),
        # Endpoint hashes remain useful forensic evidence even though they are
        # intentionally not a hard gate (see module docstring).
        "unconn_endpoint_signature_changed": bool(
            old["unconn_signature_sha256"]
            and new["unconn_signature_sha256"]
            and old["unconn_signature_sha256"]
            != new["unconn_signature_sha256"]),
    }


def accepts(before, after, *, require_strict=False,
            preserve_unconnected=False, **kwargs):
    """Compatibility tuple for callers that only need yes/no plus reason."""
    result = evaluate(
        before, after, require_strict=require_strict,
        preserve_unconnected=preserve_unconnected, **kwargs)
    return bool(result["accepted"]), str(result["decision"])
