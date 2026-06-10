#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_corpus_migrate -- ONE-SHOT migration into the two-zone corpus (CL-01).
# ============================================================================
# Decision record (owner, 2026-06-10): Decision 1a = corpus/ at repo root;
# Decision 2 = EVERYTHING migrates to corpus/staging/ -- no entry is
# grandfathered into corpus/promoted/ without a signoff the owner adds in a
# later re-sign pass. Entry IDs are stable across the move.
#
# What it does (deterministic, reversible via git):
#   1. corpus/general/*.json  ->  corpus/staging/general/<same>.json
#      (SB-13 entries, moved verbatim + {"migrated": true} appended per entry;
#       corpus/general/README.md's schema role is superseded by corpus/SCHEMA.md
#       and the README moves alongside the entries for provenance)
#   2. scripts/constraints/corpus-extracted.json (258 rows) ->
#      corpus/staging/extracted/<category-slug>.json, one file per category,
#      each row + {"status": "proposed", "migrated": true}. NOTHING else is
#      synthesized: no derived class, no typed source, no kind/applies_to --
#      fabricated metadata is model knowledge, which is not a source. The
#      full-schema upgrade (class, typed source, signoff, fixture) happens at
#      promotion time and is lint-enforced there.
#   3. Deletes the legacy locations (lint errors on them afterwards).
#
# Refuses to run if the zones are already populated (one-shot guard).
# ============================================================================
import json
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GENERAL = os.path.join(ROOT, "corpus", "general")
EXTRACTED = os.path.join(ROOT, "scripts", "constraints", "corpus-extracted.json")
STG_GENERAL = os.path.join(ROOT, "corpus", "staging", "general")
STG_EXTRACTED = os.path.join(ROOT, "corpus", "staging", "extracted")


def slug(s):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s.lower())).strip("-")


def main():
    if os.path.isdir(STG_GENERAL) or os.path.isdir(STG_EXTRACTED):
        print("zones already populated -- one-shot migration refused (git revert to redo)")
        return 1
    if not os.path.isdir(GENERAL) or not os.path.isfile(EXTRACTED):
        print("legacy locations absent -- nothing to migrate")
        return 1

    os.makedirs(STG_GENERAL)
    os.makedirs(STG_EXTRACTED)

    # 1. general corpus: move verbatim, stamp migrated
    n_gen = 0
    for f in sorted(os.listdir(GENERAL)):
        src = os.path.join(GENERAL, f)
        if f.endswith(".json"):
            entries = json.load(open(src))
            for e in entries:
                e["migrated"] = True
            with open(os.path.join(STG_GENERAL, f), "w") as out:
                json.dump(entries, out, indent=1, ensure_ascii=False)
                out.write("\n")
            n_gen += len(entries)
        else:
            shutil.copy2(src, os.path.join(STG_GENERAL, f))   # README.md rides along
        os.remove(src)
    os.rmdir(GENERAL)

    # 2. extracted project corpus: split by category, stamp status+migrated
    rows = json.load(open(EXTRACTED))
    by_cat = {}
    for r in rows:
        r.setdefault("status", "proposed")
        r["migrated"] = True
        by_cat.setdefault(slug(r.get("category", "uncategorized")), []).append(r)
    for cat, cat_rows in sorted(by_cat.items()):
        with open(os.path.join(STG_EXTRACTED, f"{cat}.json"), "w") as out:
            json.dump(cat_rows, out, indent=1, ensure_ascii=False)
            out.write("\n")
    os.remove(EXTRACTED)
    try:
        os.rmdir(os.path.dirname(EXTRACTED))                  # scripts/constraints/ if empty
    except OSError:
        pass

    print(f"migrated: {n_gen} general entries -> staging/general/, "
          f"{len(rows)} extracted rows -> staging/extracted/ ({len(by_cat)} category files)")
    print("promoted/ is EMPTY by design (Decision 2: owner re-sign pass promotes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
