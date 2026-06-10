#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_corpus_lint -- provenance discipline for the two-zone corpus (SB-13/14 + CL-01/03/05/06).
# ============================================================================
# Zones (corpus/SCHEMA.md, 2026-06-10): corpus/staging/** is agent-writable and
# compiles to ADVISORY (ADV-) checks only; corpus/promoted/** is human-only
# (CODEOWNERS) and is the ONLY source of blocking artifacts. Two entry shapes:
#   * general entries (SB-13 schema, JSON array per domain file) under
#     {staging,promoted}/general/
#   * extracted project rows (the PR #18 258-row corpus, migrated with ONLY
#     status+migrated stamped) under {staging,promoted}/extracted/
# Validates per shape (source whitelist, no model sources, Class C run refs,
# spec-section resolution, duplicate ids ACROSS zones), plus the zone rules:
#   * promoted/ requires status=human_approved + a complete signoff block
#     {by,date,evidence}; promoted EXTRACTED rows must also carry the full
#     SB-13 upgrade (class/kind/applies_to/typed source) -- promotion forces
#     the schema upgrade.
#   * Class B at promotion requires source.type == "spec" with resolving
#     section refs (the CL-06 rule under the AS-BUILT class taxonomy: B is the
#     spec-derived class here, NOT A -- the framework doc's letters were
#     inverted against corpus/general's seeded reality).
#   * AM-02: entries without "migrated": true must ship a fixture (error);
#     migrated rows warn only.
#   * CL-05 v1 conflicts: same id in both zones = error; a staging entry whose
#     "conflicts_with" names a promoted id = error (promotion blocker). (Full
#     semantic scope-overlap detection needs the CL-23 facts dimensions; v1 is
#     the mechanical subset.)
#   * Legacy locations (corpus/general/, scripts/constraints/corpus-extracted
#     .json) present = error: run scripts/cec_corpus_migrate.py.
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
ZONES = {"staging": os.path.join(ROOT, "corpus", "staging"),
         "promoted": os.path.join(ROOT, "corpus", "promoted")}
LEGACY_GENERAL = os.path.join(ROOT, "corpus", "general")
LEGACY_PROJECT = os.path.join(ROOT, "scripts", "constraints", "corpus-extracted.json")
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
# shared helpers
# ---------------------------------------------------------------------------
def _spec_text():
    return open(SPEC).read() if os.path.isfile(SPEC) else ""


def _secs_resolve(ref_text, spec_text, where):
    """Every cited spec section in ref_text must still exist in the CURRENT spec
    (mechanical SB-11 half; a spec rev that orphans a rule goes red here)."""
    if not spec_text:
        return
    for sec in re.findall(r"§\s*([0-9]+(?:\.[0-9]+)*)", str(ref_text)):
        if not re.search(rf"(^#+ .*\b{re.escape(sec)}\b|§{re.escape(sec)}\b|"
                         rf"\b[Ss]ection {re.escape(sec)}\b)", spec_text, re.M):
            err(f"{where}: cited spec section {sec} does not resolve in "
                f"{os.path.basename(SPEC)} -- stale after a spec rev?")


def _signoff_ok(e):
    s = e.get("signoff")
    return isinstance(s, dict) and all(s.get(k) for k in ("by", "date", "evidence"))


def _zone_rules(e, zone, where, spec_text, migrated):
    """CL-01/02/06 + AM-02 zone discipline, shared by both entry shapes."""
    if zone == "promoted":
        if e.get("status") != "human_approved":
            err(f"{where}: promoted/ requires status=human_approved (got {e.get('status')!r})")
        if not _signoff_ok(e):
            err(f"{where}: promoted/ requires a complete signoff block {{by,date,evidence}} "
                f"-- a model can write the field; the CODEOWNERS gate makes it real")
        # CL-06 under the AS-BUILT taxonomy: Class B (spec-derived) promotion requires a
        # spec source whose sections resolve -- the corpus never amends the spec sideways.
        if e.get("class") == "B":
            src = e.get("source") or {}
            if not (isinstance(src, dict) and src.get("type") == "spec"):
                err(f"{where}: Class B promotion requires source.type='spec' (spec-first: "
                    f"propose the spec revision, merge it, then cite the new line)")
            else:
                _secs_resolve(src.get("ref", ""), spec_text, where)
    else:  # staging
        if e.get("status") == "human_approved":
            if _signoff_ok(e):
                warn(f"{where}: human_approved + signoff in staging/ -- ready for the "
                     f"promotion PR (move to corpus/promoted/, id unchanged)")
            else:
                warn(f"{where}: human_approved without signoff -- owner re-sign required "
                     f"before promotion (Decision 2 migration state)")
    # AM-02: every NEW entry ships a minimal failing fixture; migrated rows warn only.
    # CLASS-H EXEMPTION (owner ruling D1, 2026-06-10, docs/corpus-experiential-intake-
    # 2026-06-10.md): AM-02's fixture requirement attaches to MECHANISMS, and Class H
    # has no mechanism (SCHEMA.md: H never compiles into deterministic gates), so a
    # firing fixture is impossible by construction. The exemption is CLASS-SCOPED,
    # never entry-scoped -- it keys on class AND on the absence of a compile block, so
    # the moment an H entry upgrades class or gains a compile block the requirement
    # re-engages automatically here, and the CL-03 Ruling 5 compiler latch bites as if
    # the entry were new. H entries MAY carry an optional future-fixture pointer (the
    # incident that burned you seeds the AM-02 fixture when the entry someday becomes
    # a checker_binding).
    h_exempt = e.get("class") == "H" and not e.get("compile")
    if not e.get("fixture") and not h_exempt:
        if migrated:
            warn(f"{where}: no fixture (migrated row -- add one to earn shadow evidence)")
        else:
            err(f"{where}: missing fixture (AM-02: every new entry ships a minimal "
                f"failing fixture that makes it fire; only fixture-less Class H "
                f"without a compile block is exempt -- ruling D1 2026-06-10)")


# ---------------------------------------------------------------------------
# general corpus (SB-13 entries)
# ---------------------------------------------------------------------------
def lint_general(zone, seen_ids, seen_scope, zone_ids, spec_text):
    files = sorted(glob.glob(os.path.join(ZONES[zone], "general", "*.json")))
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
            # --- vendor scope discipline (owner ruling D2, 2026-06-10) ---
            # vendor/service_tier scope keys exist for VENDOR-pile entries only; the
            # pile separation is mechanical, not editorial.
            sc = e.get("scope") if isinstance(e.get("scope"), dict) else {}
            v_keys = bool(sc.get("vendor")) or bool(sc.get("service_tier"))
            if sc.get("service_tier") and not sc.get("vendor"):
                err(f"{where}: scope.service_tier without scope.vendor -- a tier is "
                    f"meaningless unscoped to a vendor (ruling D2)")
            if v_keys and any(a == "physics" for a in ats):
                err(f"{where}: vendor-scoped entry applies to 'physics' -- vendor truth "
                    f"is not physics; an entry that genuinely mixes both SPLITS into "
                    f"two (ruling D2 pile separation)")
            if v_keys and os.path.basename(rel).endswith("-physics.json"):
                err(f"{where}: vendor key in a physics-pile file -- physics lessons "
                    f"generalize across vendors and carry NO vendor scope; move the "
                    f"entry to the vendor pile or split it (ruling D2)")
            if v_keys and isinstance(src, dict) and not src.get("date"):
                warn(f"{where}: vendor-scoped entry without source.date -- capability "
                     f"pages drift and an undated vendor rule rots invisibly; pin the "
                     f"observation date (D2 drafting note)")
            # --- heuristics never gate ---
            if e.get("class") == "H" and any(a in ("physics", "compiler", "preflight") for a in ats):
                err(f"{where}: a Class H (heuristic) entry may not apply to a deterministic "
                    f"consumer ({ats}) -- promotion to gate status is a human reclassification")
            if e.get("status") == "proposed" and any(a in ("physics", "compiler") for a in ats):
                warn(f"{where}: status 'proposed' -- visible to judges only; the compiler/"
                     f"physics must skip it until validated")
            # --- duplicates (ACROSS zones and shapes: CL-05 v1) ---
            if eid in seen_ids:
                err(f"{where}: duplicate id (also in {seen_ids[eid]})"
                    + (" -- same id in BOTH zones: promotion MOVES an entry, never copies"
                       if seen_ids[eid].split(":", 1)[0] != zone else ""))
            seen_ids[eid] = f"{zone}:{rel}"
            zone_ids[zone].add(eid)
            # Shadowing key: (kind, scope) for RULES (two rules on one scope =
            # a conflict). PARAMS are keyed by their compile param key (or id)
            # in the params channel -- two DIFFERENT parameters legitimately
            # share a scope (k_ipc + the 2152 reference set both scope
            # external-conductors); shadowing for params = same KEY.
            pkey = None
            if e.get("kind") == "param":
                tgt = ((e.get("compile") or {}).get("targets") or [{}])[0]
                pkey = (tgt.get("params") or {}).get("key", eid)
            skey = (e.get("kind"), pkey, json.dumps(e.get("scope"), sort_keys=True))
            if skey in seen_scope and e.get("status") != "deprecated":
                other = seen_scope[skey]
                err(f"{where}: duplicate (kind, scope) conflict with {other} -- supersede "
                    f"(supersedes + deprecate the old entry) instead of shadowing")
            if e.get("status") != "deprecated":
                seen_scope[skey] = f"{rel}:{eid}"
            # --- zone discipline ---
            _zone_rules(e, zone, where, spec_text, e.get("migrated") is True)
    return n


# ---------------------------------------------------------------------------
# extracted project corpus (migrated PR #18 rows; one file per category)
# ---------------------------------------------------------------------------
def lint_extracted(zone, seen_ids, zone_ids, spec_text):
    n = 0
    for f in sorted(glob.glob(os.path.join(ZONES[zone], "extracted", "*.json"))):
        rel = os.path.relpath(f, ROOT)
        try:
            rows = json.load(open(f))
        except json.JSONDecodeError as e:
            err(f"{rel}: not valid JSON ({e})")
            continue
        for i, r in enumerate(rows):
            n += 1
            where = f"{rel}:{r.get('id', i)}"
            for k in ("id", "title", "rule", "severity", "source"):
                if not r.get(k):
                    err(f"{where}: missing/empty required field {k!r}")
            if r.get("severity") and r["severity"] not in SEVERITIES:
                err(f"{where}: severity {r['severity']!r} not in {sorted(SEVERITIES)}")
            src = r.get("source", "")
            if isinstance(src, str) and src.strip().lower() in ("model", "model knowledge"):
                err(f"{where}: source 'model' REJECTED -- model knowledge is not a source")
            if isinstance(src, dict):
                if src.get("type") == "model":
                    err(f"{where}: source.type 'model' REJECTED -- model knowledge is not a source")
                elif src.get("type") and src["type"] not in SOURCE_TYPES:
                    err(f"{where}: source.type {src['type']!r} not in {sorted(SOURCE_TYPES)}")
            rid = r.get("id")
            if rid:
                if rid in seen_ids:
                    err(f"{where}: duplicate id (also in {seen_ids[rid]})"
                        + (" -- same id in BOTH zones: promotion MOVES an entry, never copies"
                           if seen_ids[rid].split(":", 1)[0] != zone else ""))
                seen_ids[rid] = f"{zone}:{rel}"
                zone_ids[zone].add(rid)
            _secs_resolve(src if isinstance(src, str) else src.get("ref", ""), spec_text, where)
            # zone discipline; promotion additionally FORCES the full SB-13 upgrade
            _zone_rules(r, zone, where, spec_text, r.get("migrated") is True)
            if zone == "promoted":
                for k in ("class", "kind", "applies_to"):
                    if not r.get(k):
                        err(f"{where}: promoted extracted row missing {k!r} -- promotion "
                            f"requires the full schema upgrade (corpus/SCHEMA.md)")
                if not isinstance(src, dict):
                    err(f"{where}: promoted extracted row needs a TYPED source object "
                        f"{{type,ref,date}}, not the migrated free-text string")
    return n


# ---------------------------------------------------------------------------
# CL-05 v1: explicit cross-zone conflict markers
# ---------------------------------------------------------------------------
def lint_conflicts(zone_ids):
    """A staging entry that names a promoted id in conflicts_with is a promotion
    blocker until a human resolves the contradiction (CL-05)."""
    for f in sorted(glob.glob(os.path.join(ZONES["staging"], "*", "*.json"))):
        rel = os.path.relpath(f, ROOT)
        try:
            data = json.load(open(f))
        except json.JSONDecodeError:
            continue                                  # already reported by the shape pass
        for e in data if isinstance(data, list) else []:
            for cid in (e.get("conflicts_with") or []):
                if cid in zone_ids["promoted"]:
                    err(f"{rel}:{e.get('id')}: declares conflicts_with promoted entry "
                        f"{cid!r} -- human resolution required; promotion blocked")


def lint_cl03():
    """CL-03 Rulings 1/2/7/8 lint legs (all host-runnable, pcbnew-free):
      - compile-block validity: block on a prose entry / class-violating
        target = ERROR (compiler computes; lint independently re-validates)
      - regenerate-and-validate: fresh compile, then every gate-binding
        artifact annotation must resolve to promoted + signed entries
      - committed-file scan: marked generated sections in committed .kicad_dru
        must byte-match current compiled output (stale convenience copy)
      - params: promoted-vs-active-hand conflict = ERROR (a reconciliation the
        promotion PR skipped); staging deltas are the compiler's ADV stream,
        not lint's business
      - registry link hygiene: a row whose matched entry has PROMOTED but
        which lacks corpus_id = warning (escalates after the grace window)"""
    try:
        import cec_corpus_compile as CC
    except Exception as e:                                    # noqa: BLE001
        warn(f"cl03 lint legs skipped (compiler unavailable: {e})")
        return
    # 1+2: compile fresh (validates blocks; emits the tree the next legs read)
    manifest = CC.compile_corpus()
    for msg in manifest["errors"]:
        err(f"compile: {msg}")
    for msg in manifest["refusals"]:
        err(f"compile latch: {msg}")
    for msg in CC.validate_artifacts():
        err(f"artifact: {msg}")
    # 3: committed generated-section drift
    for msg in CC.scan_generated_sections():
        err(f"generated-section: {msg}")
    # 4: promoted param vs still-active hand value
    promoted = {e["id"]: e for e in CC.load_zone(CC.CORPUS_ROOT, "promoted")}
    registry = CC.extract_registry()
    for e in promoted.values():
        for t in (e.get("compile") or {}).get("targets", []):
            if t.get("type") != "param":
                continue
            key = (t.get("params") or {}).get("key", e["id"])
            rp = (t.get("params") or {}).get("registry_param")
            if rp:
                row = next((r for r in registry if r["id"] == rp[0]
                            and not r.get("superseded_by")), None)
                if row and row.get("params", {}).get(rp[1]) != e.get("value"):
                    err(f"param conflict: promoted {e['id']} ({e.get('value')!r}) vs "
                        f"still-active registry {rp[0]}.{rp[1]} "
                        f"({row['params'].get(rp[1])!r}) -- the promotion PR must "
                        f"tombstone the hand value in the same diff")
            elif key in CC.HAND_DEFAULTS and CC.HAND_DEFAULTS[key] != e.get("value"):
                err(f"param conflict: promoted {e['id']} ({e.get('value')!r}) vs "
                    f"active hand default {CC.HAND_DEFAULTS[key]!r}")
    # 5: registry rows whose matched entry promoted but no corpus_id link yet
    parity = json.load(open(os.path.join(CC.OUT_ROOT, "parity.json")))
    for m in parity["matched"]:
        if m["zone"] == "promoted" and not m["linked"]:
            warn(f"registry {m['registry']}: matched entry {m['entry']} is PROMOTED "
                 f"but the row lacks corpus_id (grace window; set the link in the "
                 f"promotion PR)")


def main():
    # legacy locations are an error once the zones exist (run the one-shot migrator)
    for legacy, kind in ((LEGACY_GENERAL, "dir"), (LEGACY_PROJECT, "file")):
        present = os.path.isdir(legacy) if kind == "dir" else os.path.isfile(legacy)
        if present:
            err(f"legacy corpus location {os.path.relpath(legacy, ROOT)} still present -- "
                f"run scripts/cec_corpus_migrate.py (two-zone split, corpus/SCHEMA.md)")
    spec_text = _spec_text()
    seen_ids, seen_scope = {}, {}
    zone_ids = {"staging": set(), "promoted": set()}
    n_gen = sum(lint_general(z, seen_ids, seen_scope, zone_ids, spec_text) for z in ZONES)
    n_ext = sum(lint_extracted(z, seen_ids, zone_ids, spec_text) for z in ZONES)
    lint_conflicts(zone_ids)
    lint_cl03()
    for w in warnings:
        print(f"  warn: {w}")
    for e in errors:
        print(f"  FAIL: {e}", file=sys.stderr)
    print(f"corpus lint: {n_gen} general + {n_ext} extracted entries "
          f"(staging {len(zone_ids['staging'])} / promoted {len(zone_ids['promoted'])} ids) -- "
          f"{len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
