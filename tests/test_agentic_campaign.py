"""Recovery and replanning must not become a hidden retry/acceptance loop."""

from pathlib import Path
import hashlib
import sqlite3
import tempfile
import unittest

from cec_pipeline.campaign import Journal, canonical


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

    def test_failure_requires_changed_action_not_changed_rationale(self):
        with tempfile.TemporaryDirectory() as folder:
            journal = Journal(folder)
            operation = {"kind": "replace_chain", "points_nm": [[0, 0], [10, 10]]}
            request = dict(intent="same", operations=[operation])
            journal.begin("a", "generic", "s", {"epoch": 1}, request)
            journal.transition("a", "failed", "foreign pad blocks requested path")
            with self.assertRaisesRegex(ValueError, "identical_failed_decision"):
                journal.begin("a", "generic", "s", {"epoch": 1}, request)
            with self.assertRaisesRegex(ValueError, "identical_failed_decision"):
                journal.begin(
                    "b", "generic", "s", {"epoch": 1},
                    dict(request, intent="A more elaborate explanation is not a new path"),
                )
            changed = journal.begin(
                "b", "generic", "s", {"epoch": 1},
                dict(intent="replanned", operations=[
                    dict(operation, points_nm=[[0, 0], [10, 0], [20, 10]])
                ]),
            )
            self.assertFalse(changed["resumed"])
            self.assertFalse(changed["reevaluation"])

    def test_mapping_order_normalizes_but_operation_and_path_order_do_not(self):
        with tempfile.TemporaryDirectory() as folder:
            journal = Journal(folder)
            first = dict(kind="replace_chain", points_nm=[[0, 0], [10, 10]])
            second = dict(kind="replace_chain", points_nm=[[20, 0], [30, 10]])
            journal.begin("a", "board", "source", {}, dict(operations=[first, second]))
            journal.transition("a", "failed", "blocked")
            reordered_keys = {"points_nm": [[0, 0], [10, 10]], "kind": "replace_chain"}
            with self.assertRaisesRegex(ValueError, "identical_failed_decision"):
                journal.begin("b", "board", "source", {},
                              dict(intent="new prose", operations=[reordered_keys, second]))
            sequential = journal.begin("c", "board", "source", {},
                                       dict(operations=[second, first]))
            reversed_path = journal.begin("d", "board", "source", {}, dict(operations=[
                dict(first, points_nm=[[10, 10], [0, 0]]), second
            ]))
            self.assertFalse(sequential["resumed"])
            self.assertFalse(reversed_path["resumed"])

    def test_changed_receiving_context_is_reevaluation_not_geometric_replanning(self):
        for changed in ("code", "source_family", "footprint_table_sha256"):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as folder:
                journal = Journal(folder)
                request = dict(intent="original", operations=[dict(kind="place_cell")],
                               source_family={"board.kicad_pcb": "source"},
                               footprint_table_sha256="library")
                original = journal.begin("a", "board", "source", {"epoch": 1}, request)
                journal.transition("a", "failed", "receiver refusal")
                revised = dict(request, intent="same geometry under corrected context")
                code = {"epoch": 1}
                if changed == "code":
                    code = {"epoch": 2}
                elif changed == "source_family":
                    revised[changed] = {"board.kicad_pcb": "source", "board.kicad_pro": "new"}
                else:
                    revised[changed] = "updated-library"
                result = journal.begin("b", "board", "source", code, revised)
                self.assertEqual(original["action_identity"], result["action_identity"])
                self.assertNotEqual(original["context_identity"], result["context_identity"])
                self.assertTrue(result["reevaluation"] and result["context_changed"])
                journal.transition("b", "failed", "still refused")
                with self.assertRaisesRegex(ValueError, "identical_failed_decision"):
                    journal.begin("c", "board", "source", code, dict(revised, intent="again"))

    def test_legacy_failed_rows_cannot_be_bypassed_or_rewrite_hash_chain(self):
        with tempfile.TemporaryDirectory() as folder:
            journal = Journal(folder)
            payload = dict(board="board", source_sha256="source", code_identity={},
                           request=dict(intent="legacy", operations=[dict(kind="replace_chain")]))
            identity = hashlib.sha256(canonical(payload).encode()).hexdigest()
            with journal.connection() as db:
                db.execute("INSERT INTO decisions VALUES(?,?,?,?,?,?)",
                           (identity, "old-job", "board", "failed", canonical(payload), "blocked"))
                journal._event(db, "decision_staged",
                               dict(identity=identity, job="old-job", board="board"))
                journal._event(db, "decision_failed", dict(job="old-job", reason="blocked"))
            original_chain = journal.verify()
            with self.assertRaisesRegex(ValueError, "identical_failed_decision"):
                Journal(folder).begin("new-job", "board", "source", {},
                                      dict(payload["request"], intent="new explanation"))
            self.assertEqual(Journal(folder).verify(), original_chain)
            with journal.connection() as db:
                self.assertEqual(db.execute("SELECT identity,payload FROM decisions").fetchone(),
                                 (identity, canonical(payload)))

    def test_legacy_selected_identity_and_receipt_survive_exact_resume(self):
        with tempfile.TemporaryDirectory() as folder:
            journal = Journal(folder)
            payload = dict(board="board", source_sha256="source", code_identity={}, request={})
            identity = hashlib.sha256(canonical(payload).encode()).hexdigest()
            with journal.connection() as db:
                db.execute("INSERT INTO decisions VALUES(?,?,?,?,?,?)",
                           (identity, "old-job", "board", "selected", canonical(payload), ""))
                journal._event(db, "decision_staged",
                               dict(identity=identity, job="old-job", board="board"))
                journal._event(db, "decision_selected", dict(job="old-job", reason=""))
            journal.set_parent("board", "old-job", "candidate", {"receipt": "original"})
            original_chain = journal.verify()
            reopened = Journal(folder)
            result = reopened.begin("new-job", "board", "source", {}, {})
            self.assertEqual((result["identity"], result["job"], result["state"]),
                             (identity, "old-job", "selected"))
            self.assertEqual(reopened.parent("board"), {"receipt": "original"})
            self.assertEqual(reopened.verify(), original_chain)

    def test_replanning_uses_three_latest_per_board_source_despite_interleaving(self):
        with tempfile.TemporaryDirectory() as folder:
            journal = Journal(folder)
            for index in range(3):
                job = "a" + str(index)
                journal.begin(job, "board-a", "source-a", {}, dict(step=index))
                journal.transition(job, "failed", "blocked")
                other = "b" + str(index)
                journal.begin(other, "board-b", "source-b", {}, dict(step=index))
                journal.transition(other, "selected")
            state = journal.state(limit=1)
            self.assertTrue(state["needs_replanning"])
            self.assertEqual(len(state["decisions"]), 1)
            self.assertEqual([(s["board"], s["source_sha256"]) for s in state["replanning_scopes"]],
                             [("board-a", "source-a")])
            self.assertEqual([d["job"] for d in state["replanning_scopes"][0]["decisions"]],
                             ["a2", "a1", "a0"])
            journal.begin("new-design", "board-a", "source-a", {}, dict(step=3))
            self.assertFalse(journal.state()["needs_replanning"])

    def test_unrelated_board_and_source_failures_do_not_create_a_plateau(self):
        for scopes in ((('a', 's'), ('b', 's'), ('c', 's')),
                       (('a', 's'), ('a', 's'), ('a', 'new-source'))):
            with self.subTest(scopes=scopes), tempfile.TemporaryDirectory() as folder:
                journal = Journal(folder)
                for index, (board, source) in enumerate(scopes):
                    job = str(index)
                    journal.begin(job, board, source, {}, dict(step=index))
                    journal.transition(job, "failed", "blocked")
                self.assertFalse(journal.state()["needs_replanning"])
                self.assertEqual(journal.state()["replanning_scopes"], [])

    def test_old_source_plateau_remains_historical_not_an_active_warning(self):
        with tempfile.TemporaryDirectory() as folder:
            journal = Journal(folder)
            for index in range(3):
                job = "old" + str(index)
                journal.begin(job, "board", "old-source", {}, dict(step=index))
                journal.transition(job, "failed", "old-source obstruction")
            self.assertTrue(journal.state()["needs_replanning"])
            journal.begin("new", "board", "new-source", {}, dict(step=0))
            state = Journal(folder).state(limit=1)
            self.assertFalse(state["needs_replanning"])
            self.assertEqual(state["replanning_scopes"], [])
            self.assertEqual([scope["source_sha256"]
                              for scope in state["historical_replanning_scopes"]], ["old-source"])
            self.assertEqual(len(state["historical_replanning_scopes"][0]["decisions"]), 3)

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
