#!/usr/bin/env python3
"""Typed, deterministic constraint intermediate representation.

The existing registry remains the authored source of design knowledge. This
module compiles it into a strict, immutable representation shared by placement,
routing, reporting, and release gates. It also owns fail-closed selector
resolution so a short hierarchical net name cannot acquire different meanings
in different physical-design stages.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass


SEVERITIES = frozenset({"hard", "strong", "soft", "advisory"})
CHECKABILITY = frozenset({"yes", "partial", "no"})
STATUSES = frozenset({"ratified", "proposed"})
DIRECTIVES = frozenset({
    "pin", "adjacent", "region", "keepout", "separate", "align",
    "inner_tap", "power_escape", "none",
})


def _freeze(value):
    if isinstance(value, dict):
        return tuple((str(key), _freeze(item))
                     for key, item in sorted(value.items()))
    if isinstance(value, (list, tuple, set, frozenset)):
        rows = [_freeze(item) for item in value]
        if isinstance(value, (set, frozenset)):
            rows.sort(key=repr)
        return tuple(rows)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _thaw(value):
    if (isinstance(value, tuple) and value
            and all(isinstance(row, tuple) and len(row) == 2
                    and isinstance(row[0], str) for row in value)):
        return {key: _thaw(item) for key, item in value}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


@dataclass(frozen=True)
class Provenance:
    source: str
    source_kind: str
    status: str
    corpus_id: str = ""
    superseded_by: str = ""

    def as_dict(self):
        return {
            "source": self.source,
            "source_kind": self.source_kind,
            "status": self.status,
            "corpus_id": self.corpus_id,
            "superseded_by": self.superseded_by,
        }


@dataclass(frozen=True)
class ConstraintIR:
    id: str
    title: str
    category: str
    severity: str
    enforcement: str
    checkability: str
    directive: str
    scope: str
    rule: str
    params: tuple
    applicability: tuple
    checker: str
    provenance: Provenance

    @property
    def release_blocking(self):
        return (self.provenance.status == "ratified"
                and not self.provenance.superseded_by
                and self.checkability == "yes"
                and self.severity in ("hard", "strong"))

    def as_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "category": self.category,
            "severity": self.severity,
            "enforcement": self.enforcement,
            "checkability": self.checkability,
            "directive": self.directive,
            "scope": self.scope,
            "rule": self.rule,
            "params": _thaw(self.params),
            "applicability": _thaw(self.applicability),
            "checker": self.checker,
            "release_blocking": self.release_blocking,
            "provenance": self.provenance.as_dict(),
        }


@dataclass(frozen=True)
class ConstraintBundle:
    schema: int
    records: tuple[ConstraintIR, ...]
    fingerprint: str

    def as_dict(self, *, include_records=True):
        result = {
            "schema": self.schema,
            "count": len(self.records),
            "release_blocking_count": sum(
                row.release_blocking for row in self.records),
            "fingerprint": self.fingerprint,
        }
        if include_records:
            result["records"] = [row.as_dict() for row in self.records]
        return result


def _validate_text(value, label, constraint_id=""):
    text = str(value or "").strip()
    if not text:
        suffix = " for %s" % constraint_id if constraint_id else ""
        raise ValueError("missing %s%s" % (label, suffix))
    return text


def compile_registry(registry):
    """Compile authored registry objects into a strict canonical bundle."""
    records = []
    seen = set()
    for source in registry:
        constraint_id = _validate_text(getattr(source, "id", ""), "id")
        if constraint_id in seen:
            raise ValueError("duplicate constraint id %s" % constraint_id)
        seen.add(constraint_id)
        severity = _validate_text(
            getattr(source, "severity", ""), "severity", constraint_id)
        checkability = _validate_text(
            getattr(source, "checkable", ""), "checkability", constraint_id)
        directive = _validate_text(
            getattr(source, "directive", ""), "directive", constraint_id)
        status = str(getattr(source, "status", "proposed") or "proposed")
        if severity not in SEVERITIES:
            raise ValueError("%s has unknown severity %s" %
                             (constraint_id, severity))
        if checkability not in CHECKABILITY:
            raise ValueError("%s has unknown checkability %s" %
                             (constraint_id, checkability))
        if directive not in DIRECTIVES:
            raise ValueError("%s has unknown directive %s" %
                             (constraint_id, directive))
        if status not in STATUSES:
            raise ValueError("%s has unknown status %s" %
                             (constraint_id, status))
        provenance = Provenance(
            source=_validate_text(
                getattr(source, "source", ""), "source", constraint_id),
            source_kind=str(getattr(
                source, "source_kind", "design_registry")
                            or "design_registry"),
            status=status,
            corpus_id=str(getattr(source, "corpus_id", "") or ""),
            superseded_by=str(getattr(
                source, "superseded_by", "") or ""))
        records.append(ConstraintIR(
            id=constraint_id,
            title=_validate_text(
                getattr(source, "title", ""), "title", constraint_id),
            category=_validate_text(
                getattr(source, "category", ""), "category", constraint_id),
            severity=severity,
            enforcement=("hard_gate" if severity in ("hard", "strong")
                         else "preference" if severity == "soft"
                         else "advisory"),
            checkability=checkability,
            directive=directive,
            scope=str(getattr(source, "scope", "board") or "board"),
            rule=_validate_text(
                getattr(source, "rule", ""), "rule", constraint_id),
            params=_freeze(getattr(source, "params", {}) or {}),
            applicability=_freeze(
                getattr(source, "applicability", {}) or {}),
            checker=str(getattr(source, "checker", "") or constraint_id),
            provenance=provenance))
    records.sort(key=lambda row: row.id)
    payload = [row.as_dict() for row in records]
    fingerprint = hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":")).encode(
            "utf-8")).hexdigest()
    return ConstraintBundle(schema=1, records=tuple(records),
                            fingerprint=fingerprint)


def resolve_net_selectors(selectors, available_nets):
    """Resolve exact or unique hierarchical leaf selectors without guessing."""
    available = {str(net) for net in available_nets if str(net)}
    selected = set()
    unresolved = []
    ambiguous = {}
    provenance = []
    for selector in selectors or ():
        raw = str(selector or "").strip()
        if not raw:
            continue
        if raw in available:
            selected.add(raw)
            provenance.append({"selector": raw, "net": raw,
                               "resolution": "exact"})
            continue
        leaf = raw.lstrip("/")
        matches = sorted(net for net in available
                         if net.rsplit("/", 1)[-1] == leaf)
        if len(matches) == 1:
            selected.add(matches[0])
            provenance.append({"selector": raw, "net": matches[0],
                               "resolution": "unique_leaf"})
        elif matches:
            ambiguous[raw] = matches
        else:
            unresolved.append(raw)
    canonical = {
        "resolved": sorted(selected),
        "unresolved": sorted(unresolved),
        "ambiguous": {key: ambiguous[key] for key in sorted(ambiguous)},
        "provenance": sorted(
            provenance, key=lambda row: (row["selector"], row["net"])),
    }
    canonical["ok"] = not canonical["unresolved"] and not canonical["ambiguous"]
    canonical["fingerprint"] = hashlib.sha256(json.dumps(
        canonical, sort_keys=True, separators=(",", ":")).encode(
            "utf-8")).hexdigest()
    return canonical
