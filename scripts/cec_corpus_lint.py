#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_corpus_lint -- provenance discipline for both corpora (SB-13/SB-14).
# ============================================================================
# Validates:
#   1. corpus/general/*.json against the SB-13 schema (one JSON array per
#      domain file). REJECTS: missing/empty source, source.type == "model"
#      (model knowledge is not a source), unknown class/status/applies_to,
#      duplicate ids, duplicate (kind, scope) conflicts, Class C entries not
#      citing a ledger run. WARNS: stale source dates per class cadence
#      (A: 180 d, C: 365 d), `proposed` entries (judge-visible, never compiled).
#   2. scripts/constraints/corpus-extracted.json (the PROJECT corpus, 269 rows):
#      required fields, non-empty source, unique ids, severity vocabulary, and
#      that every cited spec section (the "section N.N" / unicode-section refs)
#      still RESOLVES in CEC-Platform-Ground-Truth-Spec.md -- the mechanical
#      half of SB-11's traceability (a spec rev that orphans a rule goes red
#      here instead of drifting silently).
#
# Dependency-free; wired into scripts/checklist.sh so it runs in CI with no
# KiCad. Exit nonzero on errors; warnings do not fail the build.
# ============================================================================
import os
import re
import sys
import json
import glob
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GENERAL_DIR = os.path.join(ROOT, "corpus", "general")
PROJECT_CORPUS = os.path.join(ROOT, "scripts", "constraints", "corpus-extracted.json")
SPEC = os.path.join(ROOT, "CEC-Platform-Ground-Truth-Spec.md")

CLASSES = {"A", "B", "C", "H"}
KINDS = {"param", "rule", "heuristic", "profile"}
STATUSES = {"proposed", "sim_validated", "bringup_validated", "human_approved", "deprecated"}
SOURCE_TYPES = {"standard", "datasheet", "fab", "spec", "decision", "measurement"}
APPLIES_TO = {"physics", "compiler", "preflight", "judge", "informational"}
SEVERITIES = {"hard", "strong", "soft", "advisory"}
STALE_DAYS = {"A": 180, "C": 365}            # re-verification cadence by class

errors, warnings = [], []


def err(msg):
    errors.append(msg)


def warn(msg):
    warnings.append(msg)


# ---------------------------------------------------------------------------
# general corpus
# ---------------------------------------------------------------------------
def lint_general():
    files = sorted(glob.glob(os.path.join(GENERAL_DIR, "*.json")))
    seen_ids = {}
    seen_scope = {}
    n = 0
    for f in files:
        rel = os.path.relpath(f, ROOT)
        try:
            data = json.load(open(f))
        except json.JSONDecodeError as e:
            err(f"{rel}: not valid JSON ({e})")
            continue
        if not isinstance(data, list):
            err(f"{rel}: must be a JSON array of entries (one file per domain)")
            continue
        for i, e in enumerate(data):
            n += 1
            where = f"{rel}[{i}]"
            if not isinstance(e, dict):
                err(f"{where}: entry is not an object")
                continue
            eid = e.get("id")
            where = f"{rel}:{eid or i}"
            # --- required fields ---
            for k in ("id", "class", "kind", "scope", "applies_to", "source", "status"):
                if k not in e:
                    err(f"{where}: missing required field {k!r}")
            if not eid:
                continue
            # --- vocabularies ---
            if e.get("class") not in CLASSES:
                err(f"{where}: class {e.get('class')!r} not in {sorted(CLASSES)}")
            if e.get("kind") not in KINDS:
                err(f"{where}: kind {e.get('kind')!r} not in {sorted(KINDS)}")
            if e.get("status") not in STATUSES:
                err(f"{where}: status {e.get('status')!r} not in lifecycle {sorted(STATUSES)}")
            ats = e.get("applies_to") or []
            if not isinstance(ats, list) or not ats:
                err(f"{where}: applies_to must be a non-empty list")
            else:
                for a in ats:
                    if a not in APPLIES_TO:
                        err(f"{where}: applies_to {a!r} not in {sorted(APPLIES_TO)}")
            # --- provenance (the point of the linter) ---
            src = e.get("source")
            if not isinstance(src, dict) or not src.get("ref") or not src.get("type"):
                err(f"{where}: source must be an object with non-empty type+ref -- "
                    f"an entry with no resolvable source does not enter the corpus")
            else:
                if src["type"] == "model":
                    err(f"{where}: source.type 'model' REJECTED -- model knowledge is not "
                        f"a source (draft is fine; provenance is mandatory)")
                elif src["type"] not in SOURCE_TYPES:
                    err(f"{where}: source.type {src['type']!r} not in {sorted(SOURCE_TYPES)}")
                # Class C must cite a measurement run in the ledger
                if e.get("class") == "C":
                    if src.get("type") != "measurement" or "run:" not in str(src.get("ref", "")):
                        err(f"{where}: Class C entries must cite a measurement run "
                            f"(source.type=measurement, ref containing 'run:R-...')")
                # stale-date cadence
                cad = STALE_DAYS.get(e.get("class"))
                if cad and src.get("date"):
                    try:
                        age = (time.time() - time.mktime(time.strptime(src["date"], "%Y-%m-%d"))) / 86400
                        if age > cad:
                            warn(f"{where}: source.date {src['date']} older than the class-"
                                 f"{e['class']} cadence ({cad} d) -- re-verify against the source")
                    except ValueError:
                        warn(f"{where}: source.date {src['date']!r} not YYYY-MM-DD")
            # --- heuristics never gate ---
            if e.get("class") == "H" and any(a in ("physics", "compiler", "preflight") for a in ats):
                err(f"{where}: a Class H (heuristic) entry may not apply to a deterministic "
                    f"consumer ({ats}) -- promotion to gate status is a human reclassification")
            if e.get("status") == "proposed" and any(a in ("physics", "compiler") for a in ats):
                warn(f"{where}: status 'proposed' -- visible to judges only; the compiler/"
                     f"physics must skip it until validated")
            # --- duplicates ---
            if eid in seen_ids:
                err(f"{where}: duplicate id (also in {seen_ids[eid]})")
            seen_ids[eid] = rel
            skey = (e.get("kind"), json.dumps(e.get("scope"), sort_keys=True))
            if skey in seen_scope and e.get("status") != "deprecated":
                other = seen_scope[skey]
                err(f"{where}: duplicate (kind, scope) conflict with {other} -- supersede "
                    f"(supersedes + deprecate the old entry) instead of shadowing")
            if e.get("status") != "deprecated":
                seen_scope[skey] = f"{rel}:{eid}"
    return n


# ---------------------------------------------------------------------------
# project corpus
# ---------------------------------------------------------------------------
def lint_project():
    if not os.path.isfile(PROJECT_CORPUS):
        warn("project corpus scripts/constraints/corpus-extracted.json absent")
        return 0
    rel = os.path.relpath(PROJECT_CORPUS, ROOT)
    try:
        rows = json.load(open(PROJECT_CORPUS))
    except json.JSONDecodeError as e:
        err(f"{rel}: not valid JSON ({e})")
        return 0
    spec_text = open(SPEC).read() if os.path.isfile(SPEC) else ""
    seen = {}
    for i, r in enumerate(rows):
        where = f"{rel}:{r.get('id', i)}"
        for k in ("id", "title", "rule", "severity", "source"):
            if not r.get(k):
                err(f"{where}: missing/empty required field {k!r}")
        if r.get("severity") and r["severity"] not in SEVERITIES:
            err(f"{where}: severity {r['severity']!r} not in {sorted(SEVERITIES)}")
        src = str(r.get("source", ""))
        if src.strip().lower() in ("model", "model knowledge"):
            err(f"{where}: source 'model' REJECTED -- model knowledge is not a source")
        rid = r.get("id")
        if rid:
            if rid in seen:
                err(f"{where}: duplicate id (also row {seen[rid]})")
            seen[rid] = i
        # spec-section resolution (mechanical SB-11 half): every cited section must
        # still exist in the CURRENT spec file, else the rule has gone stale.
        if spec_text:
            for sec in re.findall(r"§\s*([0-9]+(?:\.[0-9]+)*)", src):
                if not re.search(rf"(^#+ .*\b{re.escape(sec)}\b|§{re.escape(sec)}\b|"
                                 rf"\b[Ss]ection {re.escape(sec)}\b)", spec_text, re.M):
                    err(f"{where}: cited spec section {sec} does not resolve in "
                        f"{os.path.basename(SPEC)} -- stale after a spec rev?")
    return len(rows)


def main():
    n_gen = lint_general()
    n_prj = lint_project()
    for w in warnings:
        print(f"  warn: {w}")
    for e in errors:
        print(f"  FAIL: {e}", file=sys.stderr)
    print(f"corpus lint: {n_gen} general + {n_prj} project entries -- "
          f"{len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
