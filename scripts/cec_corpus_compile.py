#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_corpus_compile -- the CL-03 corpus -> artifact COMPILER (RB-02 aware).
# ============================================================================
# Second, independent enforcement point at the consumer (CL-03): BLOCKING
# artifacts compile ONLY from corpus/promoted/ entries with complete signoff
# AND a passing AM-02 fixture (the latch is enforced HERE, at compile, not
# just at lint -- vacuously satisfied while promoted/ is empty, load-bearing
# automatically at the first promotion). Staging entries compile into the
# ADVISORY set (`ADV-<entry-id>` namespace): structured entries become the
# advisory-mode version of their deterministic artifact, prose becomes a
# review-bundle note. Advisory can never block (enforced at the aggregation
# points -- cec_synth_pipeline.human_signoff, the cascade predicates, the
# intake gate -- never by trusting producers).
#
# The implementation rulings this encodes (docs/cl03-rulings, 2026-06-10):
#   R1  compile block IN the entry; horizon COMPUTED from (target type, class)
#       against the RB-02 class caps -- a declared horizon could self-promote.
#   R2  registry parity report (matched / registry-orphan / corpus-only) = the
#       owner's re-sign worklist; REGISTRY stays the blocking set (phase 0);
#       retirement is never automatic (tombstones ride promotion PRs).
#   R3  build-time artifacts ONLY (build/corpus-compiled/, gitignored);
#       committed-file writes stay human-only (write_generated_section is the
#       explicit convenience command, lint scans for drift). Every compiled
#       rule carries an entry-id + content-hash annotation.
#   R5  pushdown table generated here; netclass_min emits TWO rows (intent at
#       generation, enforcement at DRC) so netclass emission is never read as
#       enforcement (FR ignores netclasses -- measured, conflict resolution 3).
#   R6  scope resolution through the ONE shared resolver (cec_facts);
#       zero-resolution on a claimed board is a compile WARNING.
#   R7  params.json with promoted-only binding; staging deltas are advisory
#       fires, promoted-vs-active-hand conflicts are lint ERRORS.
#   R8  pcbnew-FREE and deterministic (sorted iteration, stable hashes, no
#       timestamps in artifacts) -- CI compiles twice and requires
#       byte-identical output. The registry is AST-extracted from
#       cec_constraints.py, never imported (pcbnew chain).
#
#   python3 scripts/cec_corpus_compile.py compile [--out DIR]
#   python3 scripts/cec_corpus_compile.py validate          # lint regenerate-leg
#   python3 scripts/cec_corpus_compile.py parity|pushdown   # report views
#   python3 scripts/cec_corpus_compile.py fixtures          # AM-02 latch leg (container)
# ============================================================================
import argparse, ast, glob, hashlib, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import cec_facts                                              # noqa: E402  (pcbnew-free)

COMPILER_VERSION = "1.0.0"
CORPUS_ROOT = os.path.join(ROOT, "corpus")
OUT_ROOT = cec_facts.COMPILED_ROOT                            # build/corpus-compiled
CONSTRAINTS_PY = os.path.join(ROOT, "scripts", "cec_constraints.py")

GEN_BEGIN = "# === BEGIN CEC-CORPUS GENERATED (do not hand-edit; build-time assembly) ==="
GEN_END = "# === END CEC-CORPUS GENERATED ==="

# ---------------------------------------------------------------- horizons --
STAGES = ["generation", "placement", "routing", "drc", "review"]
TARGET_TYPES = {"dru_rule", "netlist_assert", "keep_apart", "scorer_limit",
                "param", "netclass_min", "checker_binding", "review_note"}
TARGET_HORIZON = {                       # R1: computed, never declared
    "netclass_min": "generation",        # + a paired DRC enforcement row (R5)
    "keep_apart": "placement",
    "dru_rule": "drc",
    "netlist_assert": "drc",
    "scorer_limit": "drc",
    "param": "drc",
    "checker_binding": "drc",
    "review_note": "review",
}
CLASS_EARLIEST = {"A": "generation", "B": "generation", "C": "drc", "H": "review"}
ENFORCED_BY = {"netclass_min": "netclass-geometry-conformance (DRC horizon)"}


def _sha(obj):
    """Stable content hash of a JSON-able object (sorted keys, no whitespace)."""
    return hashlib.sha256(json.dumps(obj, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


# ------------------------------------------------------------------ corpus --
def load_zone(corpus_root, zone):
    """All entries in a zone, each tagged with `_zone` and `_file`. Sorted by
    (file, index) for determinism; files themselves sorted."""
    out = []
    for path in sorted(glob.glob(os.path.join(corpus_root, zone, "**", "*.json"),
                                 recursive=True)):
        try:
            data = json.load(open(path, encoding="utf-8"))
        except Exception as e:                                # noqa: BLE001
            raise SystemExit("corpus parse error %s: %s" % (path, e))
        rows = data if isinstance(data, list) else [data]
        for r in rows:
            if isinstance(r, dict) and r.get("id"):
                r["_zone"], r["_file"] = zone, os.path.relpath(path, corpus_root)
                out.append(r)
    return sorted(out, key=lambda r: r["id"])


def is_structured(entry):
    """R1: kind rule|param, typed (non-null) value, SCHEMA-shape scope."""
    return (entry.get("kind") in ("rule", "param")
            and entry.get("value") is not None
            and cec_facts.is_schema_scope(entry.get("scope")))


def validate_compile_block(entry):
    """-> (targets, errors). A compile block is valid ONLY on a structured
    entry; every target must be a known type whose computed horizon respects
    the entry's class cap (R1)."""
    block = entry.get("compile")
    if block is None:
        return [], []
    errs = []
    if not is_structured(entry):
        errs.append("compile block on a non-structured entry (kind/value/scope)")
    targets = block.get("targets") if isinstance(block, dict) else None
    if not isinstance(targets, list) or not targets:
        return [], errs + ["compile.targets must be a non-empty list"]
    cls = entry.get("class", "H")
    earliest = CLASS_EARLIEST.get(cls, "review")
    ok = []
    for t in targets:
        ty = t.get("type") if isinstance(t, dict) else None
        if ty not in TARGET_TYPES:
            errs.append("unknown target type %r" % ty)
            continue
        hor = TARGET_HORIZON[ty]
        if STAGES.index(hor) < STAGES.index(earliest):
            errs.append("class-%s entry may not push to %s (target %s; earliest %s)"
                        % (cls, hor, ty, earliest))
            continue
        ok.append({"type": ty, "params": t.get("params") or {}, "horizon": hor})
    return (ok if not errs else []), errs


def fixture_latch(entry):
    """R5 wired-and-latched: a BLOCKING artifact requires a passing AM-02
    fixture. -> (ok, reason). Pass = fixture declared AND resolvable AND (when
    a results file exists) recorded passing. Vacuous while promoted/ is empty."""
    fx = entry.get("fixture")
    if not fx:
        return False, "no AM-02 fixture declared"
    if not isinstance(fx, str):
        return False, "fixture must be a path-or-inline string"
    if not fx.strip().startswith("{") and not os.path.exists(os.path.join(ROOT, fx)):
        return False, "fixture path does not resolve: %s" % fx
    results = os.path.join(OUT_ROOT, "..", "corpus-fixture-results.json")
    if os.path.isfile(results):
        try:
            rec = json.load(open(results)).get(entry["id"])
            if rec and rec.get("status") != "pass":
                return False, "fixture result is %r" % rec.get("status")
        except Exception:                                     # noqa: BLE001
            pass
    return True, ""


# ---------------------------------------------------------------- registry --
def extract_registry(constraints_py=CONSTRAINTS_PY):
    """AST-extract the hand-maintained REGISTRY literals from
    cec_constraints.py (R8: the compiler never imports it -- pcbnew chain).
    Returns rows of the literal kwargs of each C(...) call."""
    tree = ast.parse(open(constraints_py, encoding="utf-8").read())
    rows = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "C" and node.keywords):
            row = {}
            for kw in node.keywords:
                try:
                    row[kw.arg] = ast.literal_eval(kw.value)
                except Exception:                             # noqa: BLE001
                    row[kw.arg] = "<non-literal>"
            if row.get("id"):
                rows.append(row)
    return sorted(rows, key=lambda r: r["id"])


_STOP = {"the", "a", "of", "per", "cec", "in", "on", "from", "is"}
_SECREF = re.compile(r"(?:§|section\s+)(\d+(?:\.\d+)*)", re.I)


def _tokens(eid):
    return {t for t in eid.replace(".", "-").replace("_", "-").split("-")
            if t and t not in _STOP}


def parity_report(entries, registry):
    """R2 phase 0: the owner's re-sign worklist. Every registry row is matched
    or registry-orphan; every entry is matched or corpus-only. Tombstoned rows
    (superseded_by) report separately. Match tiers, strongest first (the tier
    rides the report -- parity is a WORKLIST, so likely candidates beat silent
    misses, labeled by confidence): linked (explicit corpus_id) > checker
    (existing_checker names the row) > exact-id > prefix > tokens (the
    registry ids were rewritten at curation; token overlap recovers the
    lineage; 161/258 extracted existing_checker fields are empty prose)."""
    by_id = {e["id"]: e for e in entries}
    matches, orphans, tombstones = [], [], []
    matched_entries = set()
    for row in registry:
        rid, checker = row["id"], row.get("checker") or row["id"]
        if row.get("superseded_by"):
            tombstones.append({"registry": rid, "superseded_by": row["superseded_by"]})
            matched_entries.add(row["superseded_by"])
            continue
        cand, tier = None, None
        if row.get("corpus_id") and row["corpus_id"] in by_id:
            cand, tier = by_id[row["corpus_id"]], "linked"
        if cand is None:
            for e in entries:
                ec = e.get("existing_checker") or ""
                if ec and (ec in (rid, checker) or rid in ec or checker in ec):
                    cand, tier = e, "checker"
                    break
        if cand is None and rid in by_id:
            cand, tier = by_id[rid], "exact-id"
        if cand is None:
            for e in entries:
                if e["id"].startswith(rid) or rid.startswith(e["id"]):
                    cand, tier = e, "prefix"
                    break
        if cand is None:
            rt = _tokens(rid)
            best, best_n = None, 0
            for e in entries:
                n = len(rt & _tokens(e["id"]))
                if n > best_n or (n == best_n and best and e["id"] < best["id"]):
                    best, best_n = e, n
            if best is not None and best_n >= max(2, (len(rt) + 1) // 2):
                cand, tier = best, "tokens"
        if cand:
            matches.append({"registry": rid, "entry": cand["id"], "zone": cand["_zone"],
                            "status": cand.get("status"), "tier": tier,
                            "linked": row.get("corpus_id") == cand["id"]})
            matched_entries.add(cand["id"])
        else:
            # same-spec-section HINTS (not matches): semantic lineage like
            # hot-sensitive-separation <-> ref3030-away-from-heat (both §6.6)
            # is the owner's call -- surface candidates, let corpus_id link.
            secs = set(_SECREF.findall(str(row.get("source", ""))))

            def _src_text(e):
                s = e.get("source")
                return s.get("ref", "") if isinstance(s, dict) else str(s or "")

            cands = sorted(e["id"] for e in entries if secs and
                           secs & set(_SECREF.findall(_src_text(e))))[:3]
            orphans.append({"registry": rid, "status": row.get("status"),
                            "action": "draft a corpus entry, then promote + tombstone",
                            "section_candidates": cands})
    corpus_only = [{"entry": e["id"], "zone": e["_zone"],
                    "checkable": e.get("deterministically_checkable", "n/a")}
                   for e in entries if e["id"] not in matched_entries]
    return {"matched": matches, "registry_orphan": orphans,
            "corpus_only": corpus_only, "tombstones": tombstones,
            "counts": {"registry": len(registry), "matched": len(matches),
                       "registry_orphan": len(orphans),
                       "corpus_only": len(corpus_only),
                       "tombstones": len(tombstones)}}


# ----------------------------------------------------------------- compile --
def _dru_text(entry, target, binding):
    """Render one dru_rule target as KiCad custom-rule text with the R3
    entry-id + content-hash annotation."""
    p = target["params"]
    body = p.get("rule_text") or '(rule "%s"\n\t(constraint %s)\n\t(condition "%s"))' % (
        p.get("name", entry["id"]), p.get("constraint", ""), p.get("condition", ""))
    return "# corpus: %s %s %s\n%s" % (entry["id"], _sha([entry["id"], p])[:12],
                                       binding, body)


def compile_corpus(corpus_root=CORPUS_ROOT, out_root=OUT_ROOT,
                   constraints_py=CONSTRAINTS_PY):
    """The full compile. Returns the in-memory result dict; writes the
    artifact tree. Deterministic: sorted inputs, sort_keys dumps, no times."""
    staging = load_zone(corpus_root, "staging")
    promoted = load_zone(corpus_root, "promoted")
    entries = sorted(staging + promoted, key=lambda e: e["id"])
    registry = extract_registry(constraints_py)
    boards = cec_facts.board_catalog()
    facts = {b["name"]: cec_facts.board_facts(b) for b in boards}

    errors, warnings, refusals = [], [], []
    artifacts = {b["name"]: {"dru": [], "adv_dru": [], "netlist_asserts": [],
                             "keep_apart": [], "scorer_limits": [], "params": [],
                             "checker_bindings": [], "notes": []} for b in boards}
    global_params, global_notes, pushdown = [], [], []
    n_blocking = n_advisory = 0

    for e in entries:
        zone = e["_zone"]
        binding = "gate" if zone == "promoted" else "advisory"
        targets, errs = validate_compile_block(e)
        for msg in errs:
            errors.append("%s: %s" % (e["id"], msg))
        structured = is_structured(e)

        # ---- promoted gatekeeping: signoff (lint also enforces) + fixture latch
        if zone == "promoted" and targets:
            sig = e.get("signoff") or {}
            if not (sig.get("by") and sig.get("date")):
                refusals.append("%s: promoted without complete signoff" % e["id"])
                targets = []
            else:
                ok, why = fixture_latch(e)
                if not ok:
                    refusals.append("%s: blocking artifact refused -- %s (AM-02 latch)"
                                    % (e["id"], why))
                    targets = []

        # ---- no valid block => advisory review note (R1: prose by construction)
        if not targets:
            note = {"id": "ADV-%s" % e["id"], "entry_id": e["id"], "zone": zone,
                    "binding": "advisory", "kind": "review_note",
                    "title": e.get("title") or e.get("rule") or e.get("notes", "")[:120],
                    "structured": structured}
            global_notes.append(note)
            pushdown.append({"entry_id": e["id"], "class": e.get("class", "H"),
                             "zone": zone, "target": "review_note",
                             "horizon": "review", "binding": "advisory",
                             "residual": True})
            n_advisory += 1
            continue

        # ---- targets -> artifacts, bound per board by the shared resolver (R6)
        applicable, vendor_unresolved = [], []
        for b in boards:
            res = cec_facts.resolve_scope(e.get("scope"), facts[b["name"]])
            if res.get("vendor_unresolved"):
                vendor_unresolved.append(b["name"])
            if not res["applicable"]:
                continue
            applicable.append(b["name"])
            if res["countable"] and res["object_count"] == 0:
                warnings.append("%s: resolves to ZERO objects on claimed board %s "
                                "(scope bug or board gap -- both deserve eyes)"
                                % (e["id"], b["name"]))
        if not applicable:
            warnings.append("%s: applicable to no board in the catalog" % e["id"])
        # owner ruling D2 (2026-06-10): a vendor-scoped entry on a board with no
        # declared fab target (or unknown tier) compiles to a REVIEW NOTE for
        # that board, never a bound artifact -- zero coverage, honest per RB-01.
        if vendor_unresolved:
            global_notes.append({
                "id": "ADV-%s--vendor-unresolved" % e["id"], "entry_id": e["id"],
                "zone": zone, "binding": "advisory", "kind": "review_note",
                "title": "vendor-scoped entry unresolved on %s (no fab_target / "
                         "unknown tier in board-manifest.json) -- zero coverage "
                         "per RB-01" % ", ".join(sorted(vendor_unresolved)),
                "structured": structured})

        for t in targets:
            ty = t["type"]
            row = {"id": ("" if binding == "gate" else "ADV-") + e["id"],
                   "entry_id": e["id"], "zone": zone, "binding": binding,
                   "type": ty, "params": t["params"],
                   "content_hash": _sha([e["id"], ty, t["params"], e.get("value")]),
                   "value": e.get("value"), "units": e.get("units"),
                   "boards": applicable}
            pushdown.append({"entry_id": e["id"], "class": e.get("class", "H"),
                             "zone": zone, "target": ty,
                             "horizon": t["horizon"], "binding": binding,
                             "residual": False})
            if ty == "netclass_min":                       # R5: the dual row
                pushdown.append({"entry_id": e["id"], "class": e.get("class", "H"),
                                 "zone": zone, "target": ty, "horizon": "drc",
                                 "binding": binding, "residual": False,
                                 "enforced_by": ENFORCED_BY[ty]})
                pushdown[-2]["enforced_by"] = ENFORCED_BY[ty]
            if ty == "param":
                prow = dict(row, key=t["params"].get("key", e["id"]))
                global_params.append(prow)
            for bn in applicable:
                slot = artifacts[bn]
                if ty == "dru_rule":
                    (slot["dru"] if binding == "gate" else slot["adv_dru"]).append(
                        _dru_text(e, t, binding))
                elif ty == "netlist_assert":
                    slot["netlist_asserts"].append(row)
                elif ty == "keep_apart":
                    slot["keep_apart"].append(row)
                elif ty == "scorer_limit":
                    slot["scorer_limits"].append(row)
                elif ty == "param":
                    slot["params"].append(dict(row, key=t["params"].get("key", e["id"])))
                elif ty == "checker_binding":
                    slot["checker_bindings"].append(row)
                elif ty == "review_note":
                    slot["notes"].append(dict(row, kind="review_note"))
            n_blocking += (binding == "gate")
            n_advisory += (binding == "advisory")

    # ---- emit ---------------------------------------------------------------
    os.makedirs(out_root, exist_ok=True)

    def dump(rel, obj):
        path = os.path.join(out_root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=1, sort_keys=True)
            f.write("\n")

    corpus_sha = _sha([{k: v for k, v in e.items() if not k.startswith("_")}
                       for e in entries])
    registry_sha = _sha(registry)
    parity = parity_report(entries, registry)

    for b in boards:
        bn, slot = b["name"], artifacts[b["name"]]
        committed_dru = (glob.glob(os.path.join(b["dir"], "*.kicad_dru")) or [None])[0]
        hand = open(committed_dru, encoding="utf-8").read().rstrip() \
            if committed_dru else "(version 1)"
        gen = "\n".join([GEN_BEGIN,
                         "# manifest: corpus %s compiler %s (%d blocking rule(s))"
                         % (corpus_sha[:12], COMPILER_VERSION, len(slot["dru"]))]
                        + slot["dru"] + [GEN_END])
        bdir = os.path.join(out_root, bn)
        os.makedirs(bdir, exist_ok=True)
        with open(os.path.join(bdir, "assembled.kicad_dru"), "w", encoding="utf-8") as f:
            f.write(hand + "\n\n" + gen + "\n")
        if slot["adv_dru"]:
            with open(os.path.join(bdir, "adv.kicad_dru"), "w", encoding="utf-8") as f:
                f.write("(version 1)\n\n" + "\n".join(slot["adv_dru"]) + "\n")
        for name in ("netlist_asserts", "keep_apart", "scorer_limits", "params",
                     "checker_bindings", "notes"):
            dump(os.path.join(bn, name + ".json"), slot[name])

    dump("params.json", global_params)
    dump("notes.json", global_notes)
    dump("pushdown.json", pushdown)
    dump("parity.json", parity)
    manifest = {"compiler_version": COMPILER_VERSION, "corpus_sha256": corpus_sha,
                "registry_sha256": registry_sha,
                "counts": {"entries": len(entries), "staging": len(staging),
                           "promoted": len(promoted), "blocking": n_blocking,
                           "advisory": n_advisory, "boards": len(boards),
                           "errors": len(errors), "warnings": len(warnings),
                           "refusals": len(refusals)},
                "errors": sorted(errors), "warnings": sorted(warnings),
                "refusals": sorted(refusals)}
    dump("manifest.json", manifest)
    return manifest


# -------------------------------------------------------- ADV evaluation --
# Hand values for code-resident constants (R7: the staging-delta baseline).
# These mirror the literals at their consumers (dt_ipc) -- the promotion PR
# that promotes a param entry reconciles the literal and tombstones the hand
# value; wave-3 CL-23 centralizes consumer defaults so this map retires.
HAND_DEFAULTS = {
    "thermal.k_ipc.external": 0.048,      # cec_synth_pipeline.dt_ipc external
    "thermal.k_ipc.internal": 0.024,      # cec_synth_pipeline.dt_ipc internal
}


def load_board_artifacts(board_name, out_root=OUT_ROOT):
    """The compiled artifact set for one board (empty dict when the compile
    has not run -- consumers degrade, never fail)."""
    bdir = os.path.join(out_root, board_name)
    out = {}
    for name in ("netlist_asserts", "keep_apart", "scorer_limits", "params",
                 "checker_bindings", "notes"):
        path = os.path.join(bdir, name + ".json")
        try:
            out[name] = json.load(open(path))
        except Exception:                                     # noqa: BLE001
            out[name] = []
    return out


def evaluate_param_deltas(out_root=OUT_ROOT):
    """R7: a STAGING param differing from the active value is an ADVISORY
    delta -- surfaced, never silently ignored, never an error (staging has no
    authority to conflict). -> [{entry_id, key, staging_value, active_value}]"""
    try:
        rows = json.load(open(os.path.join(out_root, "params.json")))
    except Exception:                                         # noqa: BLE001
        return []
    deltas = []
    for row in rows if isinstance(rows, list) else []:
        if row.get("binding") != "advisory":
            continue
        key = row.get("key")
        active = HAND_DEFAULTS.get(key)
        if active is not None and row.get("value") != active:
            deltas.append({"entry_id": row.get("entry_id"), "key": key,
                           "staging_value": row.get("value"),
                           "active_value": active,
                           "msg": "staging proposes %r against active %r"
                                  % (row.get("value"), active)})
    return sorted(deltas, key=lambda d: d["key"])


# ------------------------------------------------- lint legs + convenience --
def validate_artifacts(out_root=OUT_ROOT, corpus_root=CORPUS_ROOT):
    """Lint regenerate-leg (R8): every gate-binding artifact annotation must
    resolve to a promoted entry with complete signoff. -> error list."""
    promoted = {e["id"]: e for e in load_zone(corpus_root, "promoted")}
    errs = []
    for path in sorted(glob.glob(os.path.join(out_root, "**", "*.json"),
                                 recursive=True)):
        if os.path.basename(path) in ("manifest.json", "parity.json", "pushdown.json"):
            continue
        try:
            rows = json.load(open(path))
        except Exception:                                     # noqa: BLE001
            continue
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict) or row.get("binding") != "gate":
                continue
            e = promoted.get(row.get("entry_id"))
            if e is None:
                errs.append("%s: gate artifact cites non-promoted entry %r"
                            % (os.path.relpath(path, out_root), row.get("entry_id")))
            elif not ((e.get("signoff") or {}).get("by")):
                errs.append("%s: gate artifact cites promoted entry %s without signoff"
                            % (os.path.relpath(path, out_root), e["id"]))
    for path in sorted(glob.glob(os.path.join(out_root, "*", "assembled.kicad_dru"))):
        for line in open(path, encoding="utf-8"):
            if line.startswith("# corpus: ") and " gate" in line:
                eid = line.split()[2]
                if eid not in promoted:
                    errs.append("%s: gate dru rule cites non-promoted %s"
                                % (os.path.relpath(path, out_root), eid))
    return errs


def scan_generated_sections(repo_root=ROOT, out_root=OUT_ROOT):
    """Lint committed-file scan (R3/R8): every marked generated section in a
    COMMITTED .kicad_dru must byte-match the current compiled section for that
    board. Drift = stale convenience copy. -> error list."""
    errs = []
    for path in sorted(glob.glob(os.path.join(repo_root, "hubs", "*", "*.kicad_dru"))
                       + glob.glob(os.path.join(repo_root, "modules", "*", "*.kicad_dru"))):
        text = open(path, encoding="utf-8").read()
        if GEN_BEGIN not in text:
            continue
        committed = text[text.index(GEN_BEGIN):text.index(GEN_END) + len(GEN_END)] \
            if GEN_END in text else text[text.index(GEN_BEGIN):]
        board = os.path.basename(os.path.dirname(path))
        asm = os.path.join(out_root, board, "assembled.kicad_dru")
        if not os.path.isfile(asm):
            errs.append("%s: generated section but no compiled output for %s "
                        "(run the compiler)" % (path, board))
            continue
        atext = open(asm, encoding="utf-8").read()
        current = atext[atext.index(GEN_BEGIN):atext.index(GEN_END) + len(GEN_END)]
        if committed.strip() != current.strip():
            errs.append("%s: committed generated section DRIFTED from compiled output "
                        "(re-run the human write command or remove the section)" % path)
    return errs


def write_generated_section(board_name, out_root=OUT_ROOT):
    """R3 convenience path -- the HUMAN-run committed write (the write=True
    pattern): copy the current compiled generated section into the board's
    committed .kicad_dru. Never called by the compiler or any agent flow."""
    b = cec_facts.find_board(board_name)
    if not b:
        raise SystemExit("unknown board %s" % board_name)
    asm = os.path.join(out_root, board_name, "assembled.kicad_dru")
    atext = open(asm, encoding="utf-8").read()
    section = atext[atext.index(GEN_BEGIN):atext.index(GEN_END) + len(GEN_END)]
    dru = (glob.glob(os.path.join(b["dir"], "*.kicad_dru"))
           or [os.path.join(b["dir"], board_name + ".kicad_dru")])[0]
    text = open(dru, encoding="utf-8").read().rstrip() if os.path.isfile(dru) \
        else "(version 1)"
    if GEN_BEGIN in text:
        text = (text[:text.index(GEN_BEGIN)].rstrip()
                + "\n\n" + section
                + text[text.index(GEN_END) + len(GEN_END):])
    else:
        text = text + "\n\n" + section + "\n"
    open(dru, "w", encoding="utf-8").write(text)
    return dru


def validate_fixtures(corpus_root=CORPUS_ROOT):
    """Container leg: run every promoted entry's AM-02 fixture and record
    results (build/corpus-fixture-results.json). Vacuously green while
    promoted/ is empty. Fixture semantics: the bound check must FIRE on the
    fixture (known-bad makes the entry fire -- AM-02)."""
    promoted = load_zone(corpus_root, "promoted")
    results, failures = {}, []
    for e in promoted:
        if not e.get("compile"):
            continue
        fx = e.get("fixture")
        if not fx:
            results[e["id"]] = {"status": "missing"}
            failures.append("%s: no fixture" % e["id"])
            continue
        results[e["id"]] = {"status": "declared-unrun",
                            "note": "fixture runner binds at first promotion"}
    path = os.path.join(OUT_ROOT, "..", "corpus-fixture-results.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(results, open(path, "w"), indent=1, sort_keys=True)
    print("fixtures: %d promoted-with-block, %d failure(s)"
          % (len(results), len(failures)))
    return failures


def main(argv=None):
    ap = argparse.ArgumentParser(description="CL-03 corpus->artifact compiler")
    sub = ap.add_subparsers(dest="cmd", required=True)
    cp = sub.add_parser("compile")
    cp.add_argument("--out", default=OUT_ROOT)
    sub.add_parser("validate")
    sub.add_parser("parity")
    sub.add_parser("pushdown")
    sub.add_parser("fixtures")
    wp = sub.add_parser("write-section", help="HUMAN convenience write (R3)")
    wp.add_argument("board")
    a = ap.parse_args(argv)
    if a.cmd == "compile":
        m = compile_corpus(out_root=a.out)
        print(json.dumps(m["counts"], indent=1, sort_keys=True))
        for w in m["warnings"]:
            print("WARN:", w)
        for r in m["refusals"]:
            print("REFUSED:", r)
        for e in m["errors"]:
            print("ERROR:", e)
        return 2 if (m["errors"] or m["refusals"]) else 0
    if a.cmd == "validate":
        errs = validate_artifacts() + scan_generated_sections()
        for e in errs:
            print("ERROR:", e)
        print("validate: %d error(s)" % len(errs))
        return 1 if errs else 0
    if a.cmd == "parity":
        compile_corpus()
        print(json.dumps(json.load(open(os.path.join(OUT_ROOT, "parity.json"))),
                         indent=1, sort_keys=True))
        return 0
    if a.cmd == "pushdown":
        compile_corpus()
        rows = json.load(open(os.path.join(OUT_ROOT, "pushdown.json")))
        from collections import Counter
        print("pushdown rows: %d  by horizon: %s" %
              (len(rows), dict(Counter(r["horizon"] for r in rows))))
        return 0
    if a.cmd == "fixtures":
        return 1 if validate_fixtures() else 0
    if a.cmd == "write-section":
        print("wrote", write_generated_section(a.board))
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
