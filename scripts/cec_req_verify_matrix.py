#!/usr/bin/env python3
"""Requirements-verification matrix generator (docs/enterprise-validation/).

Parses every REQ row across the 6 enterprise requirements registers (the same
file discovery + row regex as scripts/cec_req_lint.py, reused via import),
cross-references them against docs/enterprise-validation/verification-map.json
(the human-maintained artifact assignment), and emits
docs/enterprise-validation/verification-matrix.md -- one row per REQ ID with
its verify tags, mapped artifact(s), status, and a statement-hash prefix.

Modes:
  (default)  parse registers + map -> write verification-matrix.md. Always
             succeeds (exit 0); an unmapped REQ or orphaned map entry is
             rendered into the matrix as a visible gap, not a hard failure --
             this mode is for humans reading the matrix, not CI.
  --check    validation only, no file written. Exit 1 if:
               (a) any current REQ ID has no map entry (unmapped),
               (b) any map entry's REQ ID no longer exists in the registers
                   (orphan -- references a retired/renamed ID), or
               (c) a mapped REQ's statement text changed since the map's
                   stored statement_hash was last stamped (verify-tag rot --
                   the artifact assignment may now be judging stale wording).
             Exit 0 and a clean summary otherwise. This is the check meant to
             be wired into CI/checklist.sh once reviewed (see the README note
             -- it is NOT wired in yet, deliberately).
  --freeze   re-stamp statement_hash for every REQ ID currently present in
             BOTH the registers and the map, to the REQ's current statement
             hash. This is the human-reviewed "I looked at this artifact
             mapping again, it still holds" act -- run it only after an
             actual review, never as a reflex to silence --check. Does NOT
             add missing REQ IDs or remove orphaned map entries; those need a
             human edit to verification-map.json.

Run from repo root:
  python3 scripts/cec_req_verify_matrix.py            # regenerate the matrix
  python3 scripts/cec_req_verify_matrix.py --check    # CI-style gate
  python3 scripts/cec_req_verify_matrix.py --freeze   # re-stamp after review
"""
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cec_req_lint as lint  # reuse: ROOT, REQ_DIR, ID_RE, UNIT_BY_FILE

ROOT = lint.ROOT
REQ_DIR = lint.REQ_DIR
ID_RE = lint.ID_RE
UNIT_BY_FILE = lint.UNIT_BY_FILE

VALIDATION_DIR = os.path.join(ROOT, "docs", "enterprise-validation")
MAP_PATH = os.path.join(VALIDATION_DIR, "verification-map.json")
MATRIX_PATH = os.path.join(VALIDATION_DIR, "verification-matrix.md")

STATUSES = ("planned", "drafted", "executed")


def normalize_statement(stmt):
    """Whitespace-normalize a requirement statement before hashing, so
    incidental reflow (line wraps, doubled spaces) doesn't read as rot."""
    return " ".join(stmt.split())


def statement_hash(stmt):
    return hashlib.sha256(normalize_statement(stmt).encode("utf-8")).hexdigest()[:12]


def parse_registers():
    """Parse every REQ row across the 6 registers, in file-then-line order.

    Same discovery (UNIT_BY_FILE-listed files in REQ_DIR) and the same row
    regex/column contract as cec_req_lint.lint_file: a table row whose first
    cell matches ID_RE and which has exactly 5 columns
    (ID | Requirement | Trace | Verify | Gate). Malformed rows are left to
    cec_req_lint.py to flag; this generator silently skips them (defensive --
    it should never be the thing that crashes on a register typo).

    Returns an ordered list of dicts: id, file, line, statement, trace,
    verify, gate, hash.
    """
    reqs = []
    seen = set()
    files = sorted(
        f for f in os.listdir(REQ_DIR) if f.endswith(".md") and f in UNIT_BY_FILE
    )
    for name in files:
        path = os.path.join(REQ_DIR, name)
        text = open(path).read()
        for lineno, line in enumerate(text.splitlines(), 1):
            if not line.lstrip().startswith("|"):
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if not cells:
                continue
            m = ID_RE.search(cells[0])
            if not m:
                continue
            if len(cells) != 5:
                continue
            rid = m.group(0)
            if rid in seen:
                continue  # duplicate ID is cec_req_lint's problem, not ours
            seen.add(rid)
            _, stmt, trace, verify, gate = cells
            reqs.append({
                "id": rid,
                "file": name,
                "line": lineno,
                "statement": stmt,
                "trace": trace,
                "verify": verify,
                "gate": gate,
                "hash": statement_hash(stmt),
            })
    return reqs


# --------------------------------------------------------------------------
# Seed-time artifact assignment (used only to BUILD the initial map; the map
# file itself, once written, is the source of truth for every later run).
# --------------------------------------------------------------------------

def _named_overrides():
    """Explicit REQ-ID -> artifact assignments straight off the scope doc's
    deliverable table (docs/enterprise-requirements/research/next-trajectory/
    scope-validation-compliance.md). A REQ may land in more than one
    artifact's bucket."""
    overrides = {}

    def add(ids, artifact):
        for i in ids:
            overrides.setdefault(i, [])
            if artifact not in overrides[i]:
                overrides[i].append(artifact)

    add(["REQ-HUB-COMMON-112", "REQ-HUB-COMMON-106", "REQ-MOD-COMMON-013"],
        "bench-sync-pin7")
    add(["REQ-HUB-COMMON-110", "REQ-MOD-COMMON-053"],
        "bench-misplug-injection")
    add(["REQ-HUB-COMMON-113", "REQ-HUB-COMMON-114", "REQ-MOD-COMMON-010",
         "REQ-MOD-COMMON-013"],
        "bench-heartbeat-adversarial")
    # common fail-passive/FMEA requirements apply to every family's template
    for fam in ("24pin", "eps", "pcie", "12vhpwr"):
        add(["REQ-MOD-COMMON-030", "REQ-MOD-COMMON-031", "REQ-MOD-COMMON-032"],
            f"fmea-{fam}")
    # Hub-side FMEA (host-coupled interfaces) is its own document -- distinct
    # scope from the per-module-family templates above.
    add(["REQ-HUB-COMMON-081"], "fmea-hub")
    # per-family FMEA deltas
    add(["REQ-24PIN-COMMON-012"], "fmea-24pin")
    add(["REQ-EPS-COMMON-010"], "fmea-eps")
    add(["REQ-PCIE-COMMON-010"], "fmea-pcie")
    add(["REQ-HPWR-COMMON-012"], "fmea-12vhpwr")
    # process docs (compliance rows)
    add(["REQ-HUB-COMMON-014", "REQ-HUB-COMMON-094", "REQ-HUB-COMMON-102",
         "REQ-MOD-COMMON-052"],
        "psirt-cvd-process")
    add(["REQ-HUB-COMMON-014", "REQ-HUB-COMMON-094", "REQ-MOD-COMMON-052"],
        "sbom-pipeline")
    add(["REQ-HUB-COMMON-095"], "emc-prescan-plan")
    add(["REQ-HUB-COMMON-097"], "fips-oe-engagement-brief")
    return overrides


def _fallback_artifact(verify):
    """Every REQ gets SOMETHING defensible even without a named bench/FMEA/
    process doc: register-inspection for pure-I rows, analysis-note for A
    rows, firmware-test for T rows without a bench, demonstration-note for
    D-only rows. Priority T > A > D > I mirrors "the strongest verify tag
    present drives the generic bucket" -- a row that includes T needs SOME
    kind of test evidence even if no dedicated bench exists yet."""
    tags = verify.split("+")
    if "T" in tags:
        return ["firmware-test"]
    if "A" in tags:
        return ["analysis-note"]
    if "D" in tags:
        return ["demonstration-note"]
    return ["register-inspection"]


def seed_map(reqs):
    """Build the initial verification-map.json content: every REQ mapped to
    a named artifact, status 'planned', statement_hash stamped now."""
    overrides = _named_overrides()
    entries = {}
    for r in reqs:
        artifacts = overrides.get(r["id"]) or _fallback_artifact(r["verify"])
        entries[r["id"]] = {
            "artifacts": artifacts,
            "status": "planned",
            "statement_hash": r["hash"],
        }
    return {
        "_meta": {
            "generator": "scripts/cec_req_verify_matrix.py",
            "seeded": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "note": (
                "statement_hash is stamped at seed/--freeze time; --check "
                "flags rot when a REQ's live statement text no longer "
                "matches it."
            ),
        },
        "requirements": entries,
    }


def load_map():
    if not os.path.isfile(MAP_PATH):
        return None
    with open(MAP_PATH) as f:
        return json.load(f)


def save_map(data):
    os.makedirs(VALIDATION_DIR, exist_ok=True)
    with open(MAP_PATH, "w") as f:
        json.dump(data, f, indent=2, sort_keys=False)
        f.write("\n")


# --------------------------------------------------------------------------
# Matrix rendering
# --------------------------------------------------------------------------

def render_matrix(reqs, map_data):
    entries = (map_data or {}).get("requirements", {})
    current_ids = {r["id"] for r in reqs}
    bucket_counts = {}
    status_counts = {"planned": 0, "drafted": 0, "executed": 0, "UNMAPPED": 0}

    lines = []
    lines.append("# Requirements verification matrix")
    lines.append("")
    lines.append(
        "_Generated by `scripts/cec_req_verify_matrix.py` -- do not hand-edit. "
        "Edit `docs/enterprise-validation/verification-map.json` and "
        "regenerate. Source: the 6 registers in "
        "`docs/enterprise-requirements/`._"
    )
    lines.append("")
    lines.append(
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d')} UTC "
        f"-- {len(reqs)} requirements parsed."
    )
    lines.append("")

    by_file = {}
    for r in reqs:
        by_file.setdefault(r["file"], []).append(r)

    for fname in sorted(by_file):
        lines.append(f"## {fname}")
        lines.append("")
        lines.append("| REQ ID | Verify | Artifact(s) | Status | Statement hash |")
        lines.append("|---|---|---|---|---|")
        for r in by_file[fname]:
            entry = entries.get(r["id"])
            if entry is None:
                artifacts = "**UNMAPPED**"
                status = "UNMAPPED"
                status_counts["UNMAPPED"] += 1
            else:
                artifacts = ", ".join(entry.get("artifacts", []) or ["UNMAPPED"])
                status = entry.get("status", "planned")
                status_counts[status] = status_counts.get(status, 0) + 1
                for a in entry.get("artifacts", []):
                    bucket_counts[a] = bucket_counts.get(a, 0) + 1
            lines.append(
                f"| {r['id']} | {r['verify']} | {artifacts} | {status} | "
                f"`{r['hash']}` |"
            )
        lines.append("")

    orphans = sorted(set(entries) - current_ids)
    lines.append("## Map hygiene")
    lines.append("")
    lines.append(f"- Requirements parsed: {len(reqs)}")
    lines.append(f"- Mapped: {len(reqs) - status_counts['UNMAPPED']}")
    lines.append(f"- Unmapped: {status_counts['UNMAPPED']}")
    lines.append(f"- Orphaned map entries (REQ ID no longer in any register): "
                  f"{len(orphans)}")
    if orphans:
        for o in orphans:
            lines.append(f"  - `{o}`")
    lines.append("")
    lines.append("### Status counts")
    lines.append("")
    for s in ("planned", "drafted", "executed"):
        lines.append(f"- {s}: {status_counts.get(s, 0)}")
    lines.append("")
    lines.append("### Artifact bucket counts")
    lines.append("")
    for a in sorted(bucket_counts):
        lines.append(f"- {a}: {bucket_counts[a]}")
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# --check
# --------------------------------------------------------------------------

def run_check(reqs, map_data):
    errors = []
    if map_data is None:
        print(f"ERROR verification-map.json not found at {MAP_PATH}")
        return 1
    entries = map_data.get("requirements", {})
    current_by_id = {r["id"]: r for r in reqs}

    for rid in current_by_id:
        if rid not in entries:
            errors.append(f"unmapped REQ: {rid} has no verification-map.json entry")

    for mid in entries:
        if mid not in current_by_id:
            errors.append(
                f"orphaned map entry: {mid} is in verification-map.json but "
                f"does not exist in any register (retired/renamed ID? "
                f"tombstone or remove the map entry)"
            )

    for rid, entry in entries.items():
        if rid not in current_by_id:
            continue  # already reported as orphan above
        live_hash = current_by_id[rid]["hash"]
        stored_hash = entry.get("statement_hash")
        if stored_hash != live_hash:
            errors.append(
                f"verify-tag rot: {rid} statement changed since the map was "
                f"last touched (stored {stored_hash!r} != live {live_hash!r}) "
                f"-- review the artifact assignment, then re-run with --freeze"
            )
        if entry.get("status") not in STATUSES:
            errors.append(
                f"bad status on {rid}: {entry.get('status')!r} "
                f"(expected one of {STATUSES})"
            )
        if not entry.get("artifacts"):
            errors.append(f"{rid} has an empty artifacts list")

    if errors:
        for e in errors:
            print(f"ERROR {e}")
        print(f"cec_req_verify_matrix --check: {len(errors)} error(s) across "
              f"{len(current_by_id)} requirement(s)")
        return 1
    print(f"cec_req_verify_matrix --check: OK -- {len(current_by_id)} "
          f"requirements, all mapped, no orphans, no statement-hash rot")
    return 0


# --------------------------------------------------------------------------
# --freeze
# --------------------------------------------------------------------------

def run_freeze(reqs, map_data):
    if map_data is None:
        print(f"ERROR verification-map.json not found at {MAP_PATH} -- "
              f"nothing to freeze")
        return 1
    entries = map_data.get("requirements", {})
    current_by_id = {r["id"]: r for r in reqs}
    restamped = 0
    for rid, entry in entries.items():
        if rid not in current_by_id:
            continue
        new_hash = current_by_id[rid]["hash"]
        if entry.get("statement_hash") != new_hash:
            entry["statement_hash"] = new_hash
            restamped += 1
    map_data.setdefault("_meta", {})["last_frozen"] = datetime.now(
        timezone.utc
    ).strftime("%Y-%m-%d")
    save_map(map_data)
    print(f"cec_req_verify_matrix --freeze: re-stamped {restamped} "
          f"statement hash(es); wrote {MAP_PATH}")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--check", action="store_true",
        help="validate only (no file written); exit 1 on unmapped REQ, "
             "orphaned map entry, or statement-hash rot",
    )
    parser.add_argument(
        "--freeze", action="store_true",
        help="re-stamp statement hashes in verification-map.json to match "
             "current register text (run after a human review)",
    )
    args = parser.parse_args()

    if args.check and args.freeze:
        print("ERROR --check and --freeze are mutually exclusive")
        return 2

    if not os.path.isdir(REQ_DIR):
        print(f"cec_req_verify_matrix: no {REQ_DIR} -- nothing to do")
        return 0

    reqs = parse_registers()
    map_data = load_map()

    if args.freeze:
        return run_freeze(reqs, map_data)

    if args.check:
        return run_check(reqs, map_data)

    matrix = render_matrix(reqs, map_data)
    os.makedirs(VALIDATION_DIR, exist_ok=True)
    with open(MATRIX_PATH, "w") as f:
        f.write(matrix)
    mapped = sum(1 for r in reqs if map_data and r["id"] in
                 (map_data.get("requirements", {})))
    print(f"cec_req_verify_matrix: wrote {MATRIX_PATH} -- {len(reqs)} "
          f"requirements, {mapped} mapped, {len(reqs) - mapped} unmapped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
