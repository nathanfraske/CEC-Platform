#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  Corpus governance -- EI-05/06/07 (evidence-integrity punchlist).
# ============================================================================
#  EI-06  source registry + OWNER-ONLY revocation: a revoked external root
#         POISONS every citing entry (lint refuses with a named reason; the
#         compile path refuses the blocking artifact); un-revoke -> compiles.
#  EI-05  staging-expiry / corroboration budget: a never-firing staging entry
#         that crosses N control-lane appearances (or M nights) with ZERO
#         untainted corroboration and no judge true-positive is stamped DORMANT
#         (a deprecation candidate). A passing fixture does NOT reset the budget.
#  EI-07  the monotone-tightening law is documented in corpus/SCHEMA.md (this
#         test asserts the law text is present and unchanged in spirit).
#
#  Host-runnable, pcbnew-free. Drives the real lint + registry entrypoints over
#  a TEMP corpus tree so the live corpus is never touched.
#
#    python3 -m py_compile tests/test_corpus_governance.py
#    python3 tests/test_corpus_governance.py
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
import cec_source_registry as SR                              # noqa: E402


# ---------------------------------------------------------------------------
# a self-contained temp corpus harness
# ---------------------------------------------------------------------------
class TempCorpus:
    """A throwaway corpus tree (staging+promoted) the lint runs over without
    touching the live corpus. Repoints every module-global path the checks read
    and restores them on exit."""

    def __init__(self):
        self.dir = tempfile.mkdtemp(prefix="cec-gov-")
        for z in ("staging", "promoted"):
            os.makedirs(os.path.join(self.dir, "corpus", z, "general"))
            os.makedirs(os.path.join(self.dir, "corpus", z, "extracted"))
        self.corpus = os.path.join(self.dir, "corpus")
        self.revocations = os.path.join(self.corpus, "promoted", "source-revocations.json")
        self.corroboration = os.path.join(self.corpus, "corroboration-budget.json")

    # -- writers -------------------------------------------------------------
    @staticmethod
    def _dump(obj, path):
        with open(path, "w") as fh:
            json.dump(obj, fh)

    def write_general(self, entries, zone="staging", fname="gov.json"):
        self._dump(entries, os.path.join(self.corpus, zone, "general", fname))

    def write_revocations(self, rows):
        self._dump(rows, self.revocations)

    def clear_revocations(self):
        if os.path.isfile(self.revocations):
            os.remove(self.revocations)

    def write_corroboration(self, mapping):
        self._dump(mapping, self.corroboration)

    # -- run the real lint over this tree -----------------------------------
    def run_lint(self):
        """Return (errors, warnings, dormant_candidates) from a full lint run
        scoped to this temp tree."""
        saved = {
            "ZONES": dict(L.ZONES),
            "SR_REV": SR.REVOCATIONS_PATH,
            "SR_CORP": SR.CORPUS_ROOT,
            "L_CORR": L.CORROBORATION_PATH,
            "L_LEGACY_G": L.LEGACY_GENERAL,
            "L_LEGACY_P": L.LEGACY_PROJECT,
        }
        L.ZONES.update({"staging": os.path.join(self.corpus, "staging"),
                        "promoted": os.path.join(self.corpus, "promoted")})
        SR.REVOCATIONS_PATH = self.revocations
        SR.CORPUS_ROOT = self.corpus
        L.CORROBORATION_PATH = self.corroboration
        # point the legacy-location checks at non-existent paths so they stay quiet
        L.LEGACY_GENERAL = os.path.join(self.dir, "_nope_dir")
        L.LEGACY_PROJECT = os.path.join(self.dir, "_nope_file")
        L.errors[:], L.warnings[:], L.dormant_candidates[:] = [], [], []
        L._REVOCATIONS, L._CORROBORATION = {}, {}
        try:
            L._load_ei_state()
            spec_text = L._spec_text()
            seen_ids, seen_scope = {}, {}
            zone_ids = {"staging": set(), "promoted": set()}
            for z in ("staging", "promoted"):
                L.lint_general(z, seen_ids, seen_scope, zone_ids, spec_text)
            for z in ("staging", "promoted"):
                L.lint_extracted(z, seen_ids, zone_ids, spec_text)
            L.lint_conflicts(zone_ids)
            return (list(L.errors), list(L.warnings), list(L.dormant_candidates))
        finally:
            L.ZONES.update(saved["ZONES"])
            SR.REVOCATIONS_PATH = saved["SR_REV"]
            SR.CORPUS_ROOT = saved["SR_CORP"]
            L.CORROBORATION_PATH = saved["L_CORR"]
            L.LEGACY_GENERAL = saved["L_LEGACY_G"]
            L.LEGACY_PROJECT = saved["L_LEGACY_P"]
            L.errors[:], L.warnings[:], L.dormant_candidates[:] = [], [], []
            L._REVOCATIONS, L._CORROBORATION = {}, {}

    def cleanup(self):
        shutil.rmtree(self.dir, ignore_errors=True)


# a clean class-A external-source-citing entry (compiles + lints clean on its own)
def _class_a_entry(eid="gov.ina240.gain", ref=None, src_type="datasheet"):
    return {
        "id": eid, "class": "A", "kind": "param",
        "value": 0.20, "units": "percent",
        "scope": {"families": ["module"]},
        "applies_to": ["judge"],
        "source": {"type": src_type,
                   "ref": ref or "TI INA240 datasheet SBOS662 (gain error 0.20% max)",
                   "date": "2026-06-10"},
        "status": "proposed",
        "fixture": "tests/test_corpus_governance.py",
    }


# ===========================================================================
# EI-06  revocation poisons citing entries
# ===========================================================================
class EI06Revocation(unittest.TestCase):

    def setUp(self):
        self.tc = TempCorpus()
        self.addCleanup(self.tc.cleanup)
        self.entry = _class_a_entry()
        self.tc.write_general([self.entry])
        # the root the entry resolves to (deterministic)
        self.root = SR.entry_root(self.entry)[0]

    def test_root_derivation_is_sane(self):
        self.assertTrue(self.root.startswith("datasheet:"), self.root)
        self.assertIn("sbos662", self.root)

    def test_clean_when_unrevoked(self):
        errs, _, _ = self.tc.run_lint()
        self.assertFalse([e for e in errs if "REVOKED" in e],
                         "no revocation -> entry must compile clean")

    def test_revoking_root_refuses_entry_with_named_reason(self):
        self.tc.write_revocations([{
            "root": self.root,
            "reason": "datasheet superseded by a newer revision; figures changed",
            "revoked_by": "nathanfraske",
            "revoked_date": "2026-06-13",
            "supersedes": "datasheet:sbos662c",
        }])
        errs, _, _ = self.tc.run_lint()
        refusals = [e for e in errs if "REFUSED" in e and self.entry["id"] in e]
        self.assertTrue(refusals, "a revoked root must REFUSE the citing entry: %r" % errs)
        # NAMED reason: the revocation's reason + who/when ride the refusal
        msg = refusals[0]
        self.assertIn("REVOKED", msg)
        self.assertIn("datasheet superseded", msg)
        self.assertIn("nathanfraske", msg)
        self.assertIn("2026-06-13", msg)
        self.assertIn("superseded by", msg)            # the supersedes pointer

    def test_unrevoking_restores_compile(self):
        # revoke -> refused
        self.tc.write_revocations([{
            "root": self.root, "reason": "test", "revoked_by": "owner",
            "revoked_date": "2026-06-13"}])
        errs, _, _ = self.tc.run_lint()
        self.assertTrue([e for e in errs if "REFUSED" in e])
        # un-revoke -> clean again, same entry, nothing else changed
        self.tc.clear_revocations()
        errs2, _, _ = self.tc.run_lint()
        self.assertFalse([e for e in errs2 if "REVOKED" in e],
                         "un-revoking the root restores the entry: %r" % errs2)

    def test_revocation_is_by_root_not_blanket(self):
        # a SECOND entry on a DIFFERENT root must be untouched by the revocation
        other = _class_a_entry(eid="gov.other.ipc",
                               ref="IPC-2221B section 6.2 external-conductor chart")
        self.tc.write_general([self.entry, other])
        self.tc.write_revocations([{
            "root": self.root, "reason": "only this one", "revoked_by": "owner",
            "revoked_date": "2026-06-13"}])
        errs, _, _ = self.tc.run_lint()
        self.assertTrue([e for e in errs if "REFUSED" in e and self.entry["id"] in e])
        self.assertFalse([e for e in errs if "REFUSED" in e and other["id"] in e],
                         "revocation must be scoped to the named root only")

    def test_malformed_revocation_record_is_error(self):
        self.tc.write_revocations([{"root": "datasheet:x"}])   # missing reason/by/date
        errs, _, _ = self.tc.run_lint()
        self.assertTrue([e for e in errs if "source-revocations" in e and "missing" in e],
                        "an incomplete revocation record is an error: %r" % errs)


# ===========================================================================
# EI-06  registry derivation + report
# ===========================================================================
class EI06RegistryReport(unittest.TestCase):

    def setUp(self):
        self.tc = TempCorpus()
        self.addCleanup(self.tc.cleanup)

    def test_normalize_root_strips_rev_and_is_deterministic(self):
        a = SR.normalize_root("standard", "IPC-2221B section 6.2 external chart")
        b = SR.normalize_root("standard", "IPC-2221 internal chart, different wording")
        self.assertEqual(a[0], "standard:ipc-2221")
        self.assertEqual(b[0], "standard:ipc-2221")    # same family, rev folded out
        self.assertEqual(a[1], "B")                    # rev captured in version field
        # deterministic
        self.assertEqual(SR.normalize_root("standard", "IPC-2221B x"),
                         SR.normalize_root("standard", "IPC-2221B x"))

    def test_internal_sources_are_not_external_roots(self):
        spec = {"id": "x", "source": {"type": "spec", "ref": "spec section 6"}}
        dec = {"id": "y", "source": {"type": "decision", "ref": "owner ruling"}}
        self.assertIsNone(SR.entry_root(spec))
        self.assertIsNone(SR.entry_root(dec))

    def test_registry_groups_dependents(self):
        e1 = _class_a_entry(eid="a1", ref="IPC-2221B chart", src_type="standard")
        e2 = _class_a_entry(eid="a2", ref="IPC-2221 other chart", src_type="standard")
        self.tc.write_general([e1, e2])
        reg = SR.build_registry(corpus_root=self.tc.corpus)
        self.assertIn("standard:ipc-2221", reg)
        self.assertEqual(sorted(reg["standard:ipc-2221"]["ids"]), ["a1", "a2"])

    def test_revocation_report_enumerates_dependents(self):
        e1 = _class_a_entry(eid="a1", ref="IPC-2221B chart", src_type="standard")
        self.tc.write_general([e1])
        self.tc.write_revocations([{
            "root": "standard:ipc-2221", "reason": "withdrawn", "revoked_by": "owner",
            "revoked_date": "2026-06-13"}])
        rep = SR.revocation_report(corpus_root=self.tc.corpus,
                                   revocations_path=self.tc.revocations,
                                   out_root=os.path.join(self.tc.dir, "_no_compiled"))
        self.assertEqual(rep["counts"]["revoked_roots"], 1)
        self.assertEqual(rep["counts"]["dependent_entries"], 1)
        rr = rep["revoked"][0]
        self.assertEqual(rr["root"], "standard:ipc-2221")
        self.assertEqual([d["id"] for d in rr["dependent_entries"]], ["a1"])
        self.assertFalse(rr["stale"])

    def test_stale_revocation_flagged(self):
        # revoke a root nothing cites
        self.tc.write_revocations([{
            "root": "datasheet:nonexistent", "reason": "x", "revoked_by": "o",
            "revoked_date": "2026-06-13"}])
        rep = SR.revocation_report(corpus_root=self.tc.corpus,
                                   revocations_path=self.tc.revocations,
                                   out_root=os.path.join(self.tc.dir, "_no_compiled"))
        self.assertTrue(rep["revoked"][0]["stale"])


# ===========================================================================
# EI-05  corroboration budget -> dormant
# ===========================================================================
class EI05Dormancy(unittest.TestCase):

    def setUp(self):
        self.tc = TempCorpus()
        self.addCleanup(self.tc.cleanup)
        # a seeded staging entry that never fires usefully
        self.entry = _class_a_entry(eid="gov.never.fires")
        self.tc.write_general([self.entry])

    def test_no_ledger_no_dormancy(self):
        _, _, dormant = self.tc.run_lint()
        self.assertEqual(dormant, [], "no corroboration ledger -> no dormant stamp")

    def test_under_budget_not_dormant(self):
        self.tc.write_corroboration({self.entry["id"]: {
            "first_seen": "2026-06-01", "control_appearances": 3, "nights": 2,
            "untainted_corroborations": 0, "judge_true_positives": 0}})
        _, _, dormant = self.tc.run_lint()
        self.assertEqual(dormant, [], "under budget -> not yet a dormant candidate")

    def test_crossing_appearances_budget_with_zero_corroboration_is_dormant(self):
        self.tc.write_corroboration({self.entry["id"]: {
            "first_seen": "2026-06-01",
            "control_appearances": L.BUDGET_N_APPEARANCES + 1, "nights": 1,
            "untainted_corroborations": 0, "judge_true_positives": 0}})
        errs, warns, dormant = self.tc.run_lint()
        ids = [d["id"] for d in dormant]
        self.assertIn(self.entry["id"], ids, "crossed the appearance budget -> dormant")
        self.assertTrue([w for w in warns if "DORMANT" in w and self.entry["id"] in w])
        self.assertFalse([e for e in errs if "DORMANT" in e],
                         "dormant is a WARN, never an error (staging never blocks)")

    def test_crossing_nights_budget_is_dormant(self):
        self.tc.write_corroboration({self.entry["id"]: {
            "first_seen": "2026-05-01", "control_appearances": 0,
            "nights": L.BUDGET_M_NIGHTS + 1,
            "untainted_corroborations": 0, "judge_true_positives": 0}})
        _, _, dormant = self.tc.run_lint()
        self.assertIn(self.entry["id"], [d["id"] for d in dormant])

    def test_untainted_corroboration_clears_dormancy(self):
        self.tc.write_corroboration({self.entry["id"]: {
            "first_seen": "2026-06-01",
            "control_appearances": L.BUDGET_N_APPEARANCES + 5, "nights": 0,
            "untainted_corroborations": 1, "judge_true_positives": 0}})
        _, _, dormant = self.tc.run_lint()
        self.assertEqual(dormant, [], "one untainted corroboration -> NOT dormant")

    def test_judge_true_positive_clears_dormancy(self):
        self.tc.write_corroboration({self.entry["id"]: {
            "first_seen": "2026-06-01",
            "control_appearances": L.BUDGET_N_APPEARANCES + 5, "nights": 0,
            "untainted_corroborations": 0, "judge_true_positives": 1}})
        _, _, dormant = self.tc.run_lint()
        self.assertEqual(dormant, [], "a judge true-positive -> NOT dormant")

    def test_passing_fixture_does_NOT_reset_budget(self):
        # the anti-self-justification rule: a passing fixture is NOT corroboration.
        # An over-budget entry with many fixture_passes but zero real corroboration
        # is STILL dormant.
        self.tc.write_corroboration({self.entry["id"]: {
            "first_seen": "2026-06-01",
            "control_appearances": L.BUDGET_N_APPEARANCES + 1, "nights": 0,
            "untainted_corroborations": 0, "judge_true_positives": 0,
            "fixture_passes": 999}})
        _, _, dormant = self.tc.run_lint()
        self.assertIn(self.entry["id"], [d["id"] for d in dormant],
                      "fixture passes must not reset the corroboration budget")

    def test_promoted_entry_is_out_of_scope(self):
        # move the same entry to promoted; even over-budget it is NOT a dormant
        # candidate (it cleared the owner gate).
        prom = dict(self.entry, status="promoted",
                    signoff={"by": "nathanfraske", "date": "2026-06-13",
                             "evidence": "ledger:x"})
        # fresh tree so it lives only in promoted/
        tc2 = TempCorpus()
        self.addCleanup(tc2.cleanup)
        tc2.write_general([prom], zone="promoted")
        tc2.write_corroboration({prom["id"]: {
            "first_seen": "2026-06-01",
            "control_appearances": L.BUDGET_N_APPEARANCES + 99, "nights": 99,
            "untainted_corroborations": 0, "judge_true_positives": 0}})
        _, _, dormant = tc2.run_lint()
        self.assertEqual(dormant, [], "promoted entries are out of EI-05 scope")


# ===========================================================================
# EI-06  the COMPILE PATH (CL-03 lint leg) also refuses a revoked-root blocking
#        artifact -- a promoted entry with a compile block citing a revoked root.
# ===========================================================================
class EI06CompilePathLatch(unittest.TestCase):

    def setUp(self):
        try:
            import cec_corpus_compile                          # noqa: F401
        except Exception as ex:                                # noqa: BLE001
            self.skipTest("cec_corpus_compile unavailable: %s" % ex)
        self.tc = TempCorpus()
        self.addCleanup(self.tc.cleanup)
        # a PROMOTED, signed entry with a compile block (=> a blocking artifact)
        self.entry = {
            "id": "gov.blocking.datasheet", "class": "A", "kind": "rule",
            "value": 0.20, "units": "percent",
            "scope": {"families": ["module"]},
            "applies_to": ["judge"], "status": "promoted",
            "source": {"type": "datasheet",
                       "ref": "TI INA240 datasheet SBOS662 (gain error 0.20% max)",
                       "date": "2026-06-10"},
            "signoff": {"by": "nathanfraske", "date": "2026-06-13",
                        "evidence": "ledger:x"},
            "fixture": "tests/test_corpus_governance.py",
            "compile": {"targets": [{"type": "review_note", "params": {}}]},
        }
        self.tc.write_general([self.entry], zone="promoted")
        self.root = SR.entry_root(self.entry)[0]

    def _run_cl03(self):
        """Run lint_cl03 with the lint zones AND the compiler's corpus root
        repointed at the temp tree; return the errors. OUT_ROOT is left at the
        real (gitignored) build dir so compile's write and the parity read agree
        (cec_corpus_compile binds OUT_ROOT as a default arg, so repointing the
        constant would split them)."""
        import cec_corpus_compile as CC
        saved = {"L_ZONES": dict(L.ZONES), "SR_REV": SR.REVOCATIONS_PATH,
                 "SR_CORP": SR.CORPUS_ROOT, "CC_CORP": CC.CORPUS_ROOT}
        L.ZONES.update({"staging": os.path.join(self.tc.corpus, "staging"),
                        "promoted": os.path.join(self.tc.corpus, "promoted")})
        SR.REVOCATIONS_PATH = self.tc.revocations
        SR.CORPUS_ROOT = self.tc.corpus
        CC.CORPUS_ROOT = self.tc.corpus
        L.errors[:], L.warnings[:] = [], []
        L._REVOCATIONS = SR.load_revocations()
        try:
            L.lint_cl03()
            return list(L.errors)
        finally:
            L.ZONES.update(saved["L_ZONES"])
            SR.REVOCATIONS_PATH = saved["SR_REV"]
            SR.CORPUS_ROOT = saved["SR_CORP"]
            CC.CORPUS_ROOT = saved["CC_CORP"]
            L.errors[:], L.warnings[:] = [], []
            L._REVOCATIONS = {}

    def test_compile_path_refuses_revoked_blocking_artifact(self):
        self.tc.write_revocations([{
            "root": self.root, "reason": "datasheet withdrawn",
            "revoked_by": "nathanfraske", "revoked_date": "2026-06-13"}])
        errs = self._run_cl03()
        latched = [e for e in errs if "EI-06" in e and self.entry["id"] in e
                   and "REFUSED" in e]
        self.assertTrue(latched, "compile path must refuse the revoked blocking "
                                 "artifact: %r" % errs)

    def test_compile_path_clean_when_unrevoked(self):
        errs = self._run_cl03()
        self.assertFalse([e for e in errs if "EI-06" in e and "REFUSED" in e],
                         "no revocation -> compile path is clean for the entry: %r" % errs)


# ===========================================================================
# EI-07  the monotone-tightening law is documented in SCHEMA.md
# ===========================================================================
class EI07SchemaLaw(unittest.TestCase):

    def test_law_text_present(self):
        with open(os.path.join(ROOT, "corpus", "SCHEMA.md"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("Monotone-tightening law", text)
        # the three load-bearing clauses of the EVALUATION rule
        for clause in ("MONOTONE-TIGHTENING ONLY", "Raise-only",
                       "PENALTY_MAX", "Base gates are untouchable"):
            self.assertIn(clause, text, "missing law clause: %s" % clause)
        # the GENERATION rule's two halves
        self.assertIn("GENERATION is UNRESTRICTED but LEDGER-ATTRIBUTED", text)
        # cross-reference to the enforcing function (the law documents existing code)
        self.assertIn("apply_findings", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
