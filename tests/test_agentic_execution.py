"""Source observation caches never become changed-candidate certificates."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cec_pipeline import execution
from cec_pipeline.identity import inspection


class ExecutionTests(unittest.TestCase):
    def setup_workspace(self, folder):
        root = Path(folder)
        source = root / "source.kicad_pcb"
        source.write_text("immutable source")
        job = root / ("a" * 24)
        job.mkdir()
        candidate = job / "child.kicad_pcb"
        candidate.write_text("candidate one")
        data = dict(
            token="a" * 24,
            board="generic",
            source=str(source),
            source_sha256=inspection.sha(source),
            source_family={"source.kicad_pcb": inspection.sha(source)},
            code_identity={"code": "exact"},
            footprint_table_sha256="table",
            reporting_build="build",
            native_tool_identity={"engine": "v1"},
            candidate=str(candidate),
            request={},
        )
        path = job / "job.json"
        inspection.write_json(path, data)
        fake = type("Workbench", (), {})()
        fake.workspace = root
        fake._job = lambda token: (path, data)
        return fake, path, data

    def worker(self, path, data, *, payload=None):
        def complete(command, **kwargs):
            target = Path(command[-1])
            inspection.write_json(
                target,
                dict(
                    complete=True,
                    candidate_sha256=inspection.sha(data["candidate"]),
                    result=payload
                    or dict(
                        ok=True, complete=True, scope="synthetic source observation"
                    ),
                ),
            )
            return ""

        return complete

    def test_source_cache_rebinds_only_source_evidence_not_candidate_geometry(self):
        with tempfile.TemporaryDirectory() as folder:
            fake, path, data = self.setup_workspace(folder)
            with patch.object(
                inspection, "bounded", side_effect=self.worker(path, data)
            ) as worker:
                execution.run(fake, data["token"], "fields_source")
                (path.parent / "fields_source.json").unlink()
                Path(data["candidate"]).write_text("different candidate")
                reused = execution.run(fake, data["token"], "fields_source")
                self.assertTrue(reused["source_observation_reused"])
                self.assertEqual(
                    reused["candidate_sha256"], inspection.sha(data["candidate"])
                )
                self.assertEqual(worker.call_count, 1)
                execution.run(fake, data["token"], "fields_candidate")
                self.assertEqual(worker.call_count, 2)

    def test_code_or_tool_epoch_changes_do_not_reuse_old_source_cache(self):
        for field in (
            "code_identity",
            "native_tool_identity",
            "footprint_table_sha256",
            "source_family",
        ):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as folder:
                fake, path, data = self.setup_workspace(folder)
                with patch.object(
                    inspection, "bounded", side_effect=self.worker(path, data)
                ) as worker:
                    execution.run(fake, data["token"], "craft_source")
                    (path.parent / "craft_source.json").unlink()
                    data[field] = {"changed": "epoch"}
                    execution.run(fake, data["token"], "craft_source")
                    self.assertEqual(worker.call_count, 2)

    def test_changed_raw_report_cannot_be_reused_as_a_source_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            fake, path, data = self.setup_workspace(folder)
            report = Path(folder) / "native.json"
            report.write_text("{}")
            payload = dict(
                ok=True,
                complete=True,
                report=str(report),
                report_sha256=inspection.sha(report),
            )
            with patch.object(
                inspection,
                "bounded",
                side_effect=self.worker(path, data, payload=payload),
            ):
                execution.run(fake, data["token"], "native_source")
            (path.parent / "native_source.json").unlink()
            report.write_text("changed")
            with self.assertRaisesRegex(ValueError, "cached_source_report_changed"):
                execution.run(fake, data["token"], "native_source")

    def test_checklist_is_capability_specific_not_a_missing_receiver_bypass(self):
        ordinary = execution.required_gates(dict(ordinary_only=True))
        cell = execution.required_gates(
            dict(ordinary_only=False, transaction_kind="place_cell")
        )
        self.assertTrue(set(ordinary) < set(cell))
        self.assertIn("current_pair", cell)
        self.assertIn("kelvin_pair", cell)
        self.assertIn("assembly_pair", cell)
        with self.assertRaisesRegex(ValueError, "no_complete_independent_receiver"):
            execution.required_gates(
                dict(ordinary_only=False, transaction_kind="unknown")
            )

    def test_pending_receiver_is_not_restarted_and_has_no_success_claim(self):
        with tempfile.TemporaryDirectory() as folder:
            fake, path, data = self.setup_workspace(folder)
            process = type("Process", (), {"pid": 123})()
            with patch.object(
                execution.subprocess, "Popen", return_value=process
            ) as launch:
                first = execution.run(fake, data["token"], "ordinary_delta")
                again = execution.run(fake, data["token"], "ordinary_delta")
            self.assertEqual(launch.call_count, 1)
            self.assertFalse(first["complete"])
            self.assertFalse(again["complete"])
            self.assertEqual(again["status"], "running")


if __name__ == "__main__":
    unittest.main()
