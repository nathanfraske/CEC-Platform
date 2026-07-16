#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_source_registry -- the EXTERNAL-ROOT dependency graph + OWNER-ONLY
#  revocation list for the two-zone corpus (EI-06).
# ============================================================================
# Every Class-A pointer (source.type standard|datasheet|fab) and every
# spec/decision cite roots in EXTERNAL authority. This module derives, purely
# and deterministically from the live corpus tree, the set of external ROOTS
# the corpus depends on -- each root keyed by (type, normalized-identifier),
# carrying the document version/rev and observation date(s) of the citing
# entries. That graph answers two questions a paper needs to defend:
#   * "which entries rest on IPC-2221B?"  -> dependents(root)
#   * "which gates/notes fall if that root is found non-authoritative?"
#                                          -> revocation_report()
#
# Revocation is an OWNER-ONLY, promoted-zone act: the list lives at
# corpus/promoted/source-revocations.json (under the /corpus/promoted/
# CODEOWNERS gate -- a revocation carries the same unforgeable owner signature
# as a promotion). A revoked root POISONS every citing entry: cec_corpus_lint
# and the CL-03 compile path both REFUSE such an entry with a NAMED reason
# (mirroring the AM-02 fixture latch in cec_corpus_compile.fixture_latch).
#
# Dependency-free (stdlib only); host-runnable; pcbnew-free. Imported by
# cec_corpus_lint (refusal leg + report) and usable standalone:
#   python3 scripts/cec_source_registry.py registry      # the derived graph
#   python3 scripts/cec_source_registry.py revocations    # the owner list
#   python3 scripts/cec_source_registry.py report         # blast-radius report
# ============================================================================
import os
import re
import sys
import json
import glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS_ROOT = os.path.join(ROOT, "corpus")
ZONES = ("staging", "promoted")
# OWNER-ONLY: this path is under /corpus/promoted/ in .github/CODEOWNERS, so a
# revocation can only land through the owner's GitHub-verified approval.
REVOCATIONS_PATH = os.path.join(CORPUS_ROOT, "promoted", "source-revocations.json")
COMPILED_ROOT = os.path.join(ROOT, "build", "corpus-compiled")

# Root types that name an EXTERNAL authority (a thing that can be revoked). spec
# and decision cite the project's own spec/owner rulings -- internal, not an
# external root, so they are NOT registry roots (revoking the spec is a spec rev,
# not a source revocation). measurement cites a ledger run, also internal.
EXTERNAL_TYPES = {"standard", "datasheet", "fab"}


# ---------------------------------------------------------------------------
# normalization: ref string -> a stable, revocable root identifier
# ---------------------------------------------------------------------------
# A root id is (type, normalized-id). The normalized-id is the DOCUMENT family,
# version-agnostic at the family level but version-aware in the metadata, so an
# owner can revoke "IPC-2221" (all revs) or a specific datasheet doc number.
# Normalization is deterministic and conservative: pull a recognizable document
# token from the head of the ref, lowercase, strip a trailing single-letter rev
# (IPC-2221B -> ipc-2221) into the version field.
_WS = re.compile(r"\s+")
_REV_TAIL = re.compile(r"^(?P<base>[a-z0-9][a-z0-9-]*?)(?P<rev>[a-z])$")
# document-number-ish tokens at the head of a ref: IPC-2221B, SBOS662, GS-12-1031,
# document 336521, doc# 16495, N1702, 30100, EPS12V ...
_DOCTOKEN = re.compile(
    r"\b("
    r"ipc[- ]?\d{3,4}[a-z]?"            # IPC-2221B, IPC 2152
    r"|sbos\d+[a-z]?|sbvs\d+[a-z]?|snvs\d+[a-z]?"   # TI datasheet numbers
    r"|gs-\d+-\d+"                       # Amphenol GS-12-1031
    r"|ps-\d+-\d+"                       # Molex PS-5556-004
    r"|n\d{3,4}"                         # Bourns AN N1702
    r")\b", re.I)
# vendor/standards-body anchors used when no doc number is present
_VENDOR = [
    ("ti", re.compile(r"\b(texas instruments|ti\.com|\bti\b)\b", re.I)),
    ("molex", re.compile(r"\bmolex\b", re.I)),
    ("amphenol", re.compile(r"\bamphenol\b", re.I)),
    ("vishay", re.compile(r"\bvishay\b", re.I)),
    ("bourns", re.compile(r"\bbourns\b", re.I)),
    ("nichicon", re.compile(r"\bnichicon\b", re.I)),
    ("panasonic", re.compile(r"\bpanasonic\b", re.I)),
    ("littelfuse", re.compile(r"\blittelfuse\b", re.I)),
    ("onsemi", re.compile(r"\bon ?semi\b", re.I)),
    ("intel", re.compile(r"\bintel\b", re.I)),
    ("pcie-cem", re.compile(r"\b(pcie[- ]?cem|cem ?5)\b", re.I)),
    ("ipc", re.compile(r"\bipc\b", re.I)),
    ("jlcpcb", re.compile(r"\bjlc(pcb)?\b", re.I)),
    ("pcbway", re.compile(r"\bpcbway\b", re.I)),
]
_VERSION = re.compile(
    r"\b(rev(?:ision)?\.?\s*[0-9][0-9.]*|v[0-9][0-9.]*|version\s*[0-9][0-9.]*"
    r"|[0-9]{4}-[0-9]{2}-[0-9]{2})", re.I)


def _norm(s):
    return _WS.sub(" ", str(s or "")).strip()


def normalize_root(src_type, ref):
    """(type, ref) -> a stable root id 'type:normalized-id' plus the rev/version
    string lifted from the ref. Deterministic; same input -> same output."""
    ref = _norm(ref)
    base = None
    rev = None
    m = _DOCTOKEN.search(ref)
    if m:
        tok = m.group(1).lower().replace(" ", "-")
        tok = re.sub(r"^ipc-?", "ipc-", tok)        # IPC2221 / IPC 2221 -> ipc-2221
        rm = _REV_TAIL.match(tok)
        if rm and "-" in rm.group("base"):          # IPC-2221B -> base ipc-2221, rev B
            base, rev = rm.group("base"), rm.group("rev").upper()
        else:
            base = tok
    if base is None:
        for name, rx in _VENDOR:
            if rx.search(ref):
                base = name
                break
    if base is None:
        # last resort: the first meaningful token of the ref (stable, lowercased)
        toks = [t for t in re.split(r"[^a-z0-9]+", ref.lower()) if len(t) >= 3]
        base = toks[0] if toks else "unidentified"
    vm = _VERSION.search(ref)
    version = _norm(vm.group(1)) if vm else None
    return f"{src_type}:{base}", (rev or version)


# ---------------------------------------------------------------------------
# corpus loading (stdlib only; no pcbnew chain)
# ---------------------------------------------------------------------------
def load_entries(corpus_root=CORPUS_ROOT):
    """Every entry in both zones, tagged with `_zone` and `_file`. Robust to the
    two entry shapes (general arrays, extracted arrays) and to a bare object."""
    out = []
    for zone in ZONES:
        for path in sorted(glob.glob(os.path.join(corpus_root, zone, "**", "*.json"),
                                     recursive=True)):
            if os.path.basename(path) == "source-revocations.json":
                continue
            try:
                data = json.load(open(path, encoding="utf-8"))
            except Exception:                                  # noqa: BLE001
                continue                                       # lint's shape pass owns the error
            rows = data if isinstance(data, list) else [data]
            for r in rows:
                if isinstance(r, dict) and r.get("id"):
                    r = dict(r)
                    r["_zone"] = zone
                    r["_file"] = os.path.relpath(path, ROOT)
                    out.append(r)
    return sorted(out, key=lambda r: (r["_zone"], r["id"]))


def entry_source(entry):
    """-> (type, ref, date) for an entry. Both source shapes: a typed object
    {type,ref,date} OR a migrated free-text string (no type/date)."""
    src = entry.get("source")
    if isinstance(src, dict):
        return src.get("type"), src.get("ref", ""), src.get("date")
    if isinstance(src, str):
        return None, src, None
    return None, "", None


def entry_root(entry):
    """The EXTERNAL root an entry depends on, or None when its source is internal
    (spec/decision/measurement) or typeless-untyped. -> (root_id, version) | None."""
    styp, ref, _ = entry_source(entry)
    if styp not in EXTERNAL_TYPES:
        return None
    if not _norm(ref):
        return None
    return normalize_root(styp, ref)


# ---------------------------------------------------------------------------
# the registry: external roots -> dependents
# ---------------------------------------------------------------------------
def build_registry(entries=None, corpus_root=CORPUS_ROOT):
    """The external-root dependency graph. -> {root_id: {type, ids[], versions[],
    dates[], dependents:[{id,zone,file,version}]}}. Deterministic (sorted)."""
    if entries is None:
        entries = load_entries(corpus_root)
    reg = {}
    for e in entries:
        r = entry_root(e)
        if not r:
            continue
        root_id, version = r
        styp, _, date = entry_source(e)
        slot = reg.setdefault(root_id, {"type": styp, "versions": set(),
                                        "dates": set(), "dependents": []})
        if version:
            slot["versions"].add(version)
        if date:
            slot["dates"].add(date)
        slot["dependents"].append({"id": e["id"], "zone": e["_zone"],
                                   "file": e["_file"], "version": version})
    # freeze to sorted, JSON-able
    out = {}
    for root_id in sorted(reg):
        slot = reg[root_id]
        deps = sorted(slot["dependents"], key=lambda d: (d["zone"], d["id"]))
        out[root_id] = {"type": slot["type"],
                        "versions": sorted(slot["versions"]),
                        "dates": sorted(slot["dates"]),
                        "ids": sorted({d["id"] for d in deps}),
                        "dependents": deps}
    return out


def dependents(root_id, entries=None, corpus_root=CORPUS_ROOT):
    """Entry ids that cite a given root."""
    return build_registry(entries, corpus_root).get(root_id, {}).get("ids", [])


# ---------------------------------------------------------------------------
# revocation list (OWNER-ONLY, promoted-zone)
# ---------------------------------------------------------------------------
def load_revocations(path=None):
    """The owner's revocation list -> {root_id: revocation-record}. Absent file
    == nothing revoked (the common case). Bad shape is surfaced by lint, not
    here -- this loader fail-safes to {} so consumers never crash. `path=None`
    resolves to the current module global at CALL time (so a test can repoint
    REVOCATIONS_PATH after import)."""
    path = REVOCATIONS_PATH if path is None else path
    if not os.path.isfile(path):
        return {}
    try:
        data = json.load(open(path, encoding="utf-8"))
    except Exception:                                          # noqa: BLE001
        return {}
    rows = data if isinstance(data, list) else data.get("revocations", []) \
        if isinstance(data, dict) else []
    out = {}
    for r in rows if isinstance(rows, list) else []:
        if isinstance(r, dict) and r.get("root"):
            out[r["root"]] = r
    return out


REQUIRED_REVOCATION_FIELDS = ("root", "reason", "revoked_by", "revoked_date")


def lint_revocations(path=None):
    """Validate the revocation list shape -> error list. A malformed revocation
    record is an ERROR (it is an owner-gated, promoted-zone artifact)."""
    path = REVOCATIONS_PATH if path is None else path
    errs = []
    if not os.path.isfile(path):
        return errs
    try:
        data = json.load(open(path, encoding="utf-8"))
    except json.JSONDecodeError as e:
        return ["%s: not valid JSON (%s)" % (os.path.relpath(path, ROOT), e)]
    rows = data if isinstance(data, list) else data.get("revocations", []) \
        if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return ["%s: must be a JSON array of revocation records (or {revocations:[...]})"
                % os.path.relpath(path, ROOT)]
    rel = os.path.relpath(path, ROOT)
    seen = set()
    for i, r in enumerate(rows):
        where = "%s[%d]" % (rel, i)
        if not isinstance(r, dict):
            errs.append("%s: revocation is not an object" % where)
            continue
        for k in REQUIRED_REVOCATION_FIELDS:
            if not r.get(k):
                errs.append("%s: revocation missing/empty required field %r "
                            "(owner-gated record)" % (where, k))
        root = r.get("root")
        if root:
            if ":" not in str(root):
                errs.append("%s: revocation root %r is not a 'type:id' registry key"
                            % (where, root))
            if root in seen:
                errs.append("%s: duplicate revocation for root %r" % (where, root))
            seen.add(root)
    return errs


# ---------------------------------------------------------------------------
# the refusal leg (mirrors the AM-02 fixture latch)
# ---------------------------------------------------------------------------
def entry_revocation(entry, revocations=None, path=None):
    """If `entry` cites a REVOKED root, return its revocation record; else None.
    This is the AM-02-shaped latch: a revoked source poisons the citing entry."""
    if revocations is None:
        revocations = load_revocations(path)
    if not revocations:
        return None
    r = entry_root(entry)
    if not r:
        return None
    return revocations.get(r[0])


def refusal_reason(entry, revocations=None, path=None):
    """A NAMED refusal reason for a revoked-root entry, or None. The named reason
    quotes the revocation's reason + who/when (mirror of the fixture-latch
    refusal string)."""
    rev = entry_revocation(entry, revocations, path)
    if not rev:
        return None
    root = rev.get("root")
    sup = (" (superseded by %s)" % rev["supersedes"]) if rev.get("supersedes") else ""
    return ("source root %s REVOKED -- %s [revoked by %s on %s]%s" %
            (root, _norm(rev.get("reason")) or "no reason given",
             rev.get("revoked_by", "?"), rev.get("revoked_date", "?"), sup))


# ---------------------------------------------------------------------------
# the blast-radius report
# ---------------------------------------------------------------------------
def _compiled_artifacts_for(entry_ids, out_root=COMPILED_ROOT):
    """Every compiled artifact (build/corpus-compiled/) whose `entry_id` is in
    the given set, by (file, artifact-id, binding). Empty when the compiler has
    not run -- the report degrades, never fails."""
    hits = []
    ids = set(entry_ids)
    for path in sorted(glob.glob(os.path.join(out_root, "**", "*.json"),
                                 recursive=True)):
        try:
            rows = json.load(open(path, encoding="utf-8"))
        except Exception:                                      # noqa: BLE001
            continue
        for row in rows if isinstance(rows, list) else []:
            if isinstance(row, dict) and row.get("entry_id") in ids:
                hits.append({"file": os.path.relpath(path, ROOT),
                             "artifact_id": row.get("id"),
                             "entry_id": row.get("entry_id"),
                             "type": row.get("type") or row.get("kind"),
                             "binding": row.get("binding")})
    # also the per-board assembled DRU gate rules carry "# corpus: <id> ..."
    for path in sorted(glob.glob(os.path.join(out_root, "*", "assembled.kicad_dru"))):
        try:
            for line in open(path, encoding="utf-8"):
                if line.startswith("# corpus: "):
                    eid = line.split()[2]
                    if eid in ids:
                        hits.append({"file": os.path.relpath(path, ROOT),
                                     "artifact_id": "dru:" + eid, "entry_id": eid,
                                     "type": "dru_rule", "binding": "gate"})
        except Exception:                                      # noqa: BLE001
            pass
    return sorted(hits, key=lambda h: (h["file"], str(h["artifact_id"])))


def revocation_report(corpus_root=None, revocations_path=None, out_root=None):
    """The owner's before/after view of a revocation: each revoked root, every
    dependent entry (id+zone), and the compiled artifacts those entries produced.
    A revoked root with NO dependents is surfaced too (a stale revocation -- the
    owner may have already retired the entries, or mistyped the root key)."""
    corpus_root = CORPUS_ROOT if corpus_root is None else corpus_root
    revocations_path = REVOCATIONS_PATH if revocations_path is None else revocations_path
    out_root = COMPILED_ROOT if out_root is None else out_root
    entries = load_entries(corpus_root)
    reg = build_registry(entries, corpus_root)
    revs = load_revocations(revocations_path)
    by_id = {e["id"]: e for e in entries}
    report = {"revoked": [], "counts": {}}
    total_entries = total_artifacts = 0
    for root_id in sorted(revs):
        rev = revs[root_id]
        slot = reg.get(root_id, {})
        dep_ids = slot.get("ids", [])
        deps = [{"id": eid, "zone": by_id.get(eid, {}).get("_zone"),
                 "file": by_id.get(eid, {}).get("_file")}
                for eid in dep_ids]
        artifacts = _compiled_artifacts_for(dep_ids, out_root)
        total_entries += len(deps)
        total_artifacts += len(artifacts)
        report["revoked"].append({
            "root": root_id,
            "reason": _norm(rev.get("reason")),
            "revoked_by": rev.get("revoked_by"),
            "revoked_date": rev.get("revoked_date"),
            "supersedes": rev.get("supersedes"),
            "registered": bool(slot),
            "dependent_entries": deps,
            "compiled_artifacts": artifacts,
            "stale": not slot,                  # revoked a root nothing cites
        })
    report["counts"] = {"revoked_roots": len(revs),
                        "dependent_entries": total_entries,
                        "compiled_artifacts": total_artifacts,
                        "registry_roots": len(reg)}
    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0] if argv else "registry"
    if cmd == "registry":
        reg = build_registry()
        print(json.dumps(reg, indent=1, sort_keys=True))
        print("\n%d external root(s) over %d citing entries"
              % (len(reg), sum(len(v["ids"]) for v in reg.values())), file=sys.stderr)
        return 0
    if cmd == "revocations":
        revs = load_revocations()
        print(json.dumps(revs, indent=1, sort_keys=True))
        errs = lint_revocations()
        for e in errs:
            print("ERROR:", e, file=sys.stderr)
        return 1 if errs else 0
    if cmd == "report":
        rep = revocation_report()
        print(json.dumps(rep, indent=1, sort_keys=True))
        return 0
    print("usage: cec_source_registry.py [registry|revocations|report]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
