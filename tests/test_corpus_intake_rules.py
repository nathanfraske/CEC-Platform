#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  Owner rulings D1 + D2 (2026-06-10, docs/corpus-experiential-intake-2026-06-10.md):
#    D1 -- Class-H AM-02 fixture exemption, CLASS-scoped with automatic
#          re-engagement (class upgrade or compile block re-fires the check);
#    D2 -- vendor/service_tier scope keys: resolution against the board
#          manifest's fab_target block (no target => zero coverage, honest per
#          RB-01) + the mechanical pile-separation lint.
#  Host-runnable, pcbnew-free.
# ============================================================================
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_corpus_lint as L                                    # noqa: E402
import cec_facts as F                                          # noqa: E402


def _facts(fab_target=None, families=("module", "test-board")):
    return {"name": "test-board", "families": list(families),
            "nets": ["GND", "+3V3"], "refs": ["U1", "R1"], "lib_ids": [],
            "fab_target": fab_target}


def _entry(**over):
    e = {"id": "t.entry", "class": "H", "kind": "heuristic",
         "scope": {"families": ["module"]}, "applies_to": ["judge"],
         "source": {"type": "decision", "ref": "owner ruling", "date": "2026-06-10"},
         "status": "proposed"}
    e.update(over)
    return e


def _run_lint_general(entries, fname="burn-test.json"):
    """Run lint_general over a temp staging tree; return (errors, warnings)."""
    tmp = tempfile.mkdtemp()
    try:
        gen = os.path.join(tmp, "staging", "general")
        os.makedirs(gen)
        os.makedirs(os.path.join(tmp, "promoted", "general"))
        json.dump(entries, open(os.path.join(gen, fname), "w"))
        old_zones = dict(L.ZONES)
        L.ZONES.update({"staging": os.path.join(tmp, "staging"),
                        "promoted": os.path.join(tmp, "promoted")})
        L.errors[:], L.warnings[:] = [], []
        try:
            for z in ("staging", "promoted"):
                L.lint_general(z, {}, {}, {"staging": set(), "promoted": set()}, "")
            return list(L.errors), list(L.warnings)
        finally:
            L.ZONES.update(old_zones)
            L.errors[:], L.warnings[:] = [], []
    finally:
        shutil.rmtree(tmp)


class T1ClassHFixtureExemption(unittest.TestCase):
    """D1: fixture-less Class H is legal; anything else re-engages AM-02."""

    def test_h_without_fixture_is_clean(self):
        errs, _ = _run_lint_general([_entry()])
        self.assertFalse([e for e in errs if "fixture" in e], errs)

    def test_h_with_compile_block_reengages(self):
        e = _entry(kind="rule", value=1,
                   compile={"targets": [{"type": "review_note", "params": {}}]})
        errs, _ = _run_lint_general([e])
        self.assertTrue([x for x in errs if "fixture" in x],
                        "H + compile block must re-engage the AM-02 requirement")

    def test_class_upgrade_reengages(self):
        e = _entry()
        e["class"] = "C"
        e["source"] = {"type": "measurement", "ref": "run:R-test", "date": "2026-06-10"}
        errs, _ = _run_lint_general([e])
        self.assertTrue([x for x in errs if "fixture" in x],
                        "a class upgrade off H must re-engage the AM-02 requirement")

    def test_non_h_new_entry_still_errors(self):
        e = _entry()
        e["class"] = "B"
        e["source"] = {"type": "spec", "ref": "spec section x", "date": "2026-06-10"}
        errs, _ = _run_lint_general([e])
        self.assertTrue([x for x in errs if "fixture" in x])

    def test_h_optional_future_fixture_pointer_is_legal(self):
        errs, _ = _run_lint_general([_entry(fixture="board:U4 (future checker_binding)")])
        self.assertFalse([e for e in errs if "fixture" in e], errs)


class T2VendorPileSeparation(unittest.TestCase):
    """D2: the pile separation is mechanical, never editorial."""

    def test_tier_without_vendor_errors(self):
        e = _entry(scope={"families": ["module"], "service_tier": ["standard"]})
        errs, _ = _run_lint_general([e])
        self.assertTrue([x for x in errs if "service_tier without" in x], errs)

    def test_vendor_plus_physics_applies_to_errors(self):
        e = _entry(scope={"families": ["module"], "vendor": ["jlcpcb"]},
                   applies_to=["judge"])
        errs0, _ = _run_lint_general([e])
        self.assertFalse([x for x in errs0 if "vendor" in x.lower()], errs0)
        e2 = dict(e, applies_to=["physics"])
        e2["class"] = "A"   # H may not apply to physics anyway; isolate the vendor leg
        e2["source"] = {"type": "standard", "ref": "x", "date": "2026-06-10"}
        e2["fixture"] = "tests/test_corpus_intake_rules.py"
        errs, _ = _run_lint_general([e2])
        self.assertTrue([x for x in errs if "vendor truth is not physics" in x], errs)

    def test_vendor_key_in_physics_pile_file_errors(self):
        e = _entry(scope={"families": ["module"], "vendor": ["jlcpcb"]})
        errs, _ = _run_lint_general([e], fname="fab-lessons-physics.json")
        self.assertTrue([x for x in errs if "physics-pile" in x], errs)

    def test_vendor_without_source_date_warns(self):
        e = _entry(scope={"families": ["module"], "vendor": ["jlcpcb"]},
                   source={"type": "fab", "ref": "rev2 order"})
        _, warns = _run_lint_general([e])
        self.assertTrue([w for w in warns if "observation date" in w], warns)


class T3VendorScopeResolution(unittest.TestCase):
    """D2: vendor scope resolves against the manifest fab_target block."""

    def test_schema_accepts_vendor_dims(self):
        self.assertTrue(F.is_schema_scope({"vendor": ["jlcpcb"],
                                           "service_tier": ["standard"]}))

    def test_no_fab_target_is_unresolved_zero_coverage(self):
        res = F.resolve_scope({"vendor": ["jlcpcb"]}, _facts(fab_target=None))
        self.assertFalse(res["applicable"])
        self.assertTrue(res.get("vendor_unresolved"),
                        "absent fab target must read UNRESOLVED (review-note), "
                        "not a silent non-match")

    def test_vendor_match(self):
        res = F.resolve_scope({"vendor": ["jlcpcb"]},
                              _facts(fab_target={"vendor": "jlcpcb", "service_tier": None}))
        self.assertTrue(res["applicable"])

    def test_vendor_mismatch_is_resolved_nonmatch(self):
        res = F.resolve_scope({"vendor": ["pcbway"]},
                              _facts(fab_target={"vendor": "jlcpcb", "service_tier": None}))
        self.assertFalse(res["applicable"])
        self.assertFalse(res.get("vendor_unresolved"),
                         "a declared mismatching target is RESOLVED, not unresolved")

    def test_tier_unknown_is_unresolved(self):
        res = F.resolve_scope({"vendor": ["jlcpcb"], "service_tier": ["standard"]},
                              _facts(fab_target={"vendor": "jlcpcb", "service_tier": None}))
        self.assertFalse(res["applicable"])
        self.assertTrue(res.get("vendor_unresolved"))

    def test_tier_match_and_mismatch(self):
        ft = {"vendor": "jlcpcb", "service_tier": "standard"}
        self.assertTrue(F.resolve_scope(
            {"vendor": ["jlcpcb"], "service_tier": ["standard"]}, _facts(fab_target=ft))["applicable"])
        self.assertFalse(F.resolve_scope(
            {"vendor": ["jlcpcb"], "service_tier": ["economic"]}, _facts(fab_target=ft))["applicable"])

    def test_families_short_circuits_first(self):
        res = F.resolve_scope({"families": ["hub"], "vendor": ["jlcpcb"]},
                              _facts(fab_target=None))
        self.assertFalse(res["applicable"])
        self.assertFalse(res.get("vendor_unresolved"),
                         "family non-match resolves before the vendor leg")

    def test_rev2_manifest_carries_fab_target(self):
        b = F.find_board("atx-24pin-rev2")
        self.assertIsNotNone(b)
        facts = F.board_facts(b)
        self.assertEqual((facts.get("fab_target") or {}).get("vendor"), "jlcpcb")
        # tier deliberately unknown until the owner records the as-built tier
        self.assertIsNone(facts["fab_target"].get("service_tier"))


if __name__ == "__main__":
    unittest.main()
