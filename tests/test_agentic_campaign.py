"""Recovery and replanning must not become a hidden retry/acceptance loop."""

from pathlib import Path
import sqlite3
import tempfile
import unittest

from cec_pipeline.campaign import Journal


class CampaignTests(unittest.TestCase):
    def test_restart_resumes_same_nonterminal_decision_and_preserves_chain(self):
        with tempfile.TemporaryDirectory() as folder:
            first = Journal(folder)
            made = first.begin(
                "opaque-job",
                "generic",
                "a" * 64,
                {"code": "b" * 64},
                {"intent": "explicit"},
            )
            first.transition("opaque-job", "checking")
            second = Journal(folder)
            resumed = second.begin(
                "different-job",
                "generic",
                "a" * 64,
                {"code": "b" * 64},
                {"intent": "explicit"},
            )
            self.assertEqual(resumed["job"], "opaque-job")
            self.assertTrue(resumed["resumed"])
            self.assertEqual(made["identity"], resumed["identity"])
            self.assertEqual(first.verify(), second.verify())

    def test_failure_requires_changed_design_or_new_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            journal = Journal(folder)
            journal.begin("a", "generic", "s", {"epoch": 1}, {"intent": "same"})
            journal.transition("a", "failed", "foreign pad blocks requested path")
            with self.assertRaisesRegex(ValueError, "identical_failed_decision"):
                journal.begin("a", "generic", "s", {"epoch": 1}, {"intent": "same"})
            changed = journal.begin(
                "b", "generic", "s", {"epoch": 1}, {"intent": "replanned"}
            )
            self.assertFalse(changed["resumed"])

    def test_parent_requires_selected_decision_not_a_model_claim(self):
        with tempfile.TemporaryDirectory() as folder:
            journal = Journal(folder)
            journal.begin("a", "generic", "s", {}, {})
            with self.assertRaises(ValueError):
                journal.set_parent("generic", "a", "c", {})
            journal.transition("a", "selected")
            journal.set_parent("generic", "a", "c", {"exact": "candidate"})
            self.assertEqual(Journal(folder).parent("generic"), {"exact": "candidate"})
            with self.assertRaisesRegex(ValueError, "terminal_decision"):
                journal.transition("a", "checking")

    def test_changed_journal_is_detected_without_promoting_history(self):
        with tempfile.TemporaryDirectory() as folder:
            journal = Journal(folder)
            journal.begin("a", "generic", "s", {}, {})
            with sqlite3.connect(str(journal.path)) as db:
                db.execute("UPDATE events SET payload='{}'")
            with self.assertRaisesRegex(ValueError, "integrity"):
                journal.verify()


if __name__ == "__main__":
    unittest.main()
