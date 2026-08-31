import json
import importlib.util
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import cec_full_pipeline as pipeline


class FullPipelineJournalTests(unittest.TestCase):
    def test_dashboard_stage_declares_pipeline_lineage_authority(self):
        cfg = SimpleNamespace(board="pcie-8pin-2port")
        with mock.patch(
                "cec_dashboard.archive_board",
                return_value={
                    "id": "archive-id", "verdict": "FAILED",
                    "panel_urls": {},
                }) as archive:
            result = pipeline._dashboard_stage(
                Path("winner.kicad_pcb"), cfg, Path("oracle.json"))

        self.assertTrue(result["ok"])
        self.assertEqual(archive.call_args.kwargs["archive_role"], "pipeline")

    @staticmethod
    def _outline_row(*, area, hard_route, soft_route=0.0):
        return (
            (0, 0, 0),                  # physical
            (0,) * 14,                  # full craft
            float(area),
            (0,),                       # proxy
            0, None, None, None, None,
            tuple(hard_route),
            tuple(hard_route) + (float(soft_route),),
            (0,) * 10,                  # blocking craft
        )

    def test_outline_floor_prefers_hard_routability_before_area(self):
        smaller_blocked = self._outline_row(
            area=90.0, hard_route=(0, 0, 0, 0, 0, 0, 0, 1))
        larger_clear = self._outline_row(
            area=100.0, hard_route=(0, 0, 0, 0, 0, 0, 0, 0))
        rows = sorted(
            [smaller_blocked, larger_clear],
            key=lambda row: pipeline._outline_selection_sort_key(
                row, route_probe=True))
        self.assertIs(rows[0], larger_clear)

    def test_candidate_pose_signature_measures_geometry_not_search_label(self):
        first = SimpleNamespace(
            P={"U1": (1.0, 2.0, 0.0), "C1": (3.0, 4.0, 90.0)},
            back_refs={"C1"}, strat="plain", seed=0)
        same_geometry = SimpleNamespace(
            P=dict(first.P), back_refs={"C1"}, strat="thermal", seed=9)
        moved = SimpleNamespace(
            P={**first.P, "C1": (3.1, 4.0, 90.0)},
            back_refs={"C1"}, strat="plain", seed=0)

        self.assertEqual(
            pipeline._candidate_position_signature(first),
            pipeline._candidate_position_signature(same_geometry))
        self.assertNotEqual(
            pipeline._candidate_position_signature(first),
            pipeline._candidate_position_signature(moved))

    def test_fiducial_craft_guard_rolls_back_exact_regression(self):
        with tempfile.TemporaryDirectory() as temp:
            board = Path(temp) / "board.kicad_pcb"
            board.write_bytes(b"before-board")
            cfg = SimpleNamespace()

            def move_fiducial(path, **_kwargs):
                Path(path).write_bytes(b"after-board")
                return {"schema": 1, "ok": True, "changed": True,
                        "moved": [{"ref": "FID1"}]}

            with mock.patch(
                    "cec_synth_pipeline.placement_craft_evidence",
                    side_effect=[{"rank": 0}, {"rank": 1}]), \
                    mock.patch(
                        "cec_synth_pipeline.placement_craft_key",
                        side_effect=lambda row: (row["rank"],)), \
                    mock.patch(
                        "cec_synth_pipeline.repair_fiducials_to_edge_band",
                        side_effect=move_fiducial):
                report = pipeline._transactional_fiducial_edge_repair(
                    cfg, board, reconsider_all=True)

            self.assertEqual(board.read_bytes(), b"before-board")
            self.assertFalse(report["changed"])
            self.assertTrue(report["rolled_back"])
            self.assertEqual(report["rollback_reason"],
                             "exact_craft_regression")
            self.assertFalse(report["craft_guard"]["accepted"])

    def test_changed_fiducials_get_one_bounded_craft_repair(self):
        with tempfile.TemporaryDirectory() as temp:
            board = Path(temp) / "board.kicad_pcb"
            board.write_bytes(b"open-placement")
            cfg = SimpleNamespace()
            loaded = SimpleNamespace(GetTracks=lambda: iter(()))
            candidate = SimpleNamespace(P={"C1": (1.0, 2.0, 0.0)})
            repair = {"schema": 1, "ok": True, "changed": True,
                      "accepted_count": 1}

            with mock.patch("pcbnew.LoadBoard", return_value=loaded), \
                    mock.patch(
                        "cec_synth_pipeline.placement_craft_evidence",
                        side_effect=[{"ok": False, "rank": 1},
                                     {"ok": True, "rank": 0}]), \
                    mock.patch(
                        "cec_synth_pipeline.placement_craft_key",
                        side_effect=lambda row: (row["rank"],)), \
                    mock.patch(
                        "cec_synth_pipeline.placement_candidate_from_board",
                        return_value=candidate), \
                    mock.patch(
                        "cec_synth_pipeline.repair_placement_craft_epochs",
                        return_value=(candidate, repair)) as bounded, \
                    mock.patch(
                        "cec_synth_pipeline.materialize") as materialize, \
                    mock.patch.object(
                        pipeline, "_placement_position_signature",
                        side_effect=["before", "after"]):
                report = pipeline._bounded_post_fiducial_craft_repair(
                    cfg, board,
                    {"schema": 1, "ok": True, "changed": True},
                    max_trials=7, rounds=2, epochs=1)

            bounded.assert_called_once_with(
                cfg, candidate, max_trials=7, rounds=2, epochs=1)
            materialize.assert_called_once_with(candidate, cfg, str(board))
            self.assertTrue(report["one_shot"])
            self.assertTrue(report["after_ok"])
            self.assertFalse(report["repeated_placement"])

    def test_unchanged_fiducials_do_not_repeat_craft_search(self):
        report = pipeline._bounded_post_fiducial_craft_repair(
            SimpleNamespace(), Path("unused.kicad_pcb"),
            {"schema": 1, "ok": True, "changed": False},
            max_trials=64, rounds=4, epochs=2)
        self.assertFalse(report["applicable"])
        self.assertEqual(report["reason"], "fiducials_unchanged")

    def test_late_fiducial_reseat_rolls_back_if_power_must_rebuild(self):
        with tempfile.TemporaryDirectory() as temp:
            board = Path(temp) / "board.kicad_pcb"
            board.write_bytes(b"before-board")
            cfg = SimpleNamespace(params={})

            def move_fiducial(_cfg, path, **_kwargs):
                Path(path).write_bytes(b"after-board")
                return {"schema": 1, "ok": True, "changed": True,
                        "moved": [{"ref": "FID1"}]}

            bound = SimpleNamespace(params={"pourfirst_state": "restored"})
            with mock.patch.object(
                    pipeline, "_transactional_fiducial_edge_repair",
                    side_effect=move_fiducial), \
                    mock.patch.object(
                        pipeline, "_ensure_placement_route_authority",
                        return_value={
                            "schema": 1, "ok": True, "applicable": True,
                            "reused": False, "placement_changed": False}), \
                    mock.patch(
                        "cec_synth_pipeline.config_with_board_route_authority",
                        return_value=(bound, {
                            "schema": 1, "ok": True, "bound": True})):
                report = pipeline._finalize_fiducials_after_route_authority(
                    cfg, board, priority_applicable=False)

            self.assertEqual(board.read_bytes(), b"before-board")
            self.assertFalse(report["changed"])
            self.assertTrue(report["rolled_back"])
            self.assertEqual(report["reason"], "exact_power_dependency")
            self.assertEqual(cfg.params["pourfirst_state"], "restored")

    def test_late_fiducial_reseat_accepts_reused_exact_power(self):
        with tempfile.TemporaryDirectory() as temp:
            board = Path(temp) / "board.kicad_pcb"
            board.write_bytes(b"before-board")
            cfg = SimpleNamespace(params={})

            def move_fiducial(_cfg, path, **_kwargs):
                Path(path).write_bytes(b"after-board")
                return {"schema": 1, "ok": True, "changed": True,
                        "moved": [{"ref": "FID1"}]}

            authority = {
                "schema": 1, "ok": True, "applicable": True,
                "reused": True, "placement_changed": False,
                "_artifacts": [],
            }
            bound = SimpleNamespace(params={"pourfirst_state": "accepted"})
            with mock.patch.object(
                    pipeline, "_transactional_fiducial_edge_repair",
                    side_effect=move_fiducial), \
                    mock.patch.object(
                        pipeline, "_ensure_placement_route_authority",
                        return_value=authority), \
                    mock.patch(
                        "cec_synth_pipeline.config_with_board_route_authority",
                        return_value=(bound, {
                            "schema": 1, "ok": True, "bound": True})):
                report = pipeline._finalize_fiducials_after_route_authority(
                    cfg, board, priority_applicable=False)

            self.assertEqual(board.read_bytes(), b"after-board")
            self.assertTrue(report["changed"])
            self.assertTrue(report["accepted"])
            self.assertEqual(report["reason"],
                             "late_global_fiducial_set_exactly_admitted")
            self.assertEqual(cfg.params["pourfirst_state"], "accepted")

    def test_stage_callable_signature_tracks_same_module_helper_body(self):
        with tempfile.TemporaryDirectory() as temp:
            module_path = Path(temp) / "coordinator_fixture.py"
            module_path.write_text(
                "def helper():\n    return 1\n\n"
                "def stage():\n    return helper()\n",
                encoding="utf-8")
            spec = importlib.util.spec_from_file_location(
                "coordinator_fixture", module_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            before = pipeline._callable_signature(module.stage)

            module_path.write_text(
                "def helper():\n    return 2\n\n"
                "def stage():\n    return helper()\n",
                encoding="utf-8")
            after = pipeline._callable_signature(module.stage)

        self.assertNotEqual(before, after)

    def test_outline_floor_prefers_area_before_soft_congestion(self):
        hard = (0, 0, 0, 0, 0, 0, 0, 0)
        smaller = self._outline_row(
            area=90.0, hard_route=hard, soft_route=20.0)
        larger = self._outline_row(
            area=100.0, hard_route=hard, soft_route=1.0)
        rows = sorted(
            [larger, smaller],
            key=lambda row: pipeline._outline_selection_sort_key(
                row, route_probe=True))
        self.assertIs(rows[0], smaller)

    def test_resumed_compaction_preserves_discovered_edge_membership(self):
        with tempfile.TemporaryDirectory() as temp:
            board = Path(temp) / "board.kicad_pcb"
            board.write_text("placeholder", encoding="utf-8")
            report = board.with_name("board.placement.json")
            report.write_text(json.dumps({
                "selected_outline_mm": [80.0, 50.0],
                "outline_compaction": {
                    "target_outline_mm": [80.0, 50.0],
                    "moved_refs": {
                        "J_EDGE": {"edge": "bottom"},
                        "H2": {"edge": "bottom"},
                    },
                },
            }), encoding="utf-8")
            policy, provenance = pipeline._continued_edge_follow_policy(
                board, (80.0, 50.0), {
                    "edge_follow": (
                        {"edge": "bottom", "margin_mm": 15.0},
                        {"edge": "bottom", "refs": ("USB1",)},
                    ),
                })

        self.assertEqual(
            policy["edge_follow"],
            ({"edge": "bottom", "refs": ("H2", "J_EDGE", "USB1"),
              "mode": "rigid", "clearance_mm": 0.0},))
        self.assertEqual(
            provenance["source"], "prior_admitted_membership")

    def test_resumed_compaction_releases_movable_corner_feature(self):
        with tempfile.TemporaryDirectory() as temp:
            board = Path(temp) / "board.kicad_pcb"
            board.write_text("placeholder", encoding="utf-8")
            board.with_name("board.placement.json").write_text(json.dumps({
                "selected_outline_mm": [80.0, 50.0],
                "outline_compaction": {
                    "target_outline_mm": [80.0, 50.0],
                    "moved_refs": {
                        "H2": {"edge": "bottom"},
                        "FID2": {"edge": "bottom"},
                    },
                },
            }), encoding="utf-8")
            policy, provenance = pipeline._continued_edge_follow_policy(
                board, (80.0, 50.0), {
                    "edge_follow_exclude_refs": ("FID2",),
                    "edge_follow": ({
                        "edge": "bottom", "refs": ("H2", "FID2"),
                    },),
                })

        self.assertEqual(
            policy["edge_follow"],
            ({"edge": "bottom", "refs": ("H2",),
              "mode": "rigid", "clearance_mm": 0.0},))
        self.assertEqual(provenance["released_refs"], ["FID2"])

    def test_design_source_signature_excludes_coordinator_implementation(self):
        cfg = SimpleNamespace(
            sch=str(ROOT / "does-not-exist.kicad_sch"),
            dir=str(ROOT / "does-not-exist"),
        )
        paths = pipeline._source_files(cfg, ROOT / "scripts" / "cec_pcb.py")
        self.assertNotIn(
            (ROOT / "scripts" / "cec_full_pipeline.py").resolve(), paths
        )

    def test_route_code_closure_includes_transitive_router_modules(self):
        names = {
            path.name for path in pipeline._local_code_closure(
                "cec_synth_pipeline.py", "cec_precision_route.py"
            )
        }
        self.assertIn("cec_fr.py", names)
        self.assertIn("cec_fab_profile.py", names)
        self.assertIn("cec_route_preflight.py", names)

    def test_resume_requires_matching_input_and_artifact_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            artifact = temp / "artifact.txt"
            calls = []

            def action():
                calls.append(1)
                artifact.write_text("run-%d" % len(calls), encoding="utf-8")
                return {"ok": True, "value": len(calls),
                        "_artifacts": [str(artifact)]}

            journal = pipeline.StageJournal(temp / "state.json", "hub",
                                            resume=True)
            first = journal.run("route", "input-a", action)
            second = journal.run("route", "input-a", action)
            self.assertEqual(first["value"], 1)
            self.assertEqual(second["value"], 1)
            self.assertEqual(len(calls), 1)

            artifact.write_text("tampered", encoding="utf-8")
            third = journal.run("route", "input-a", action)
            self.assertEqual(third["value"], 2)
            fourth = journal.run("route", "input-b", action)
            self.assertEqual(fourth["value"], 3)

    def test_failed_stage_is_durable_and_never_resumed(self):
        with tempfile.TemporaryDirectory() as temp:
            journal = pipeline.StageJournal(
                Path(temp) / "state.json", "hub", resume=True
            )
            with self.assertRaisesRegex(RuntimeError, "intentional"):
                journal.run("signoff", "x", lambda: (_ for _ in ()).throw(
                    RuntimeError("intentional")
                ))
            state = json.loads((Path(temp) / "state.json").read_text())
            self.assertEqual(state["stages"]["signoff"]["status"], "failed")
            self.assertIn("intentional", state["stages"]["signoff"]["error"])


class FullPipelineManifestTests(unittest.TestCase):
    def test_hub_config_resolves_only_manifest_candidate(self):
        import cec_synth_pipeline as synth

        cfg = synth.Config.load("hub-standard-rev2")
        self.assertEqual(
            Path(cfg.pcb).resolve(),
            (ROOT / "beta" / "hub-standard-rev2" / "candidate" /
             "hub-standard-rev2-candidate.kicad_pcb").resolve())
        self.assertEqual(tuple(cfg.pins["J6P"]), (73.0, 59.7, 90.0))
        self.assertEqual(tuple(cfg.pins["J6C"]), (18.0, 12.7, 90.0))
        self.assertEqual(tuple(cfg.pins["J6D"]), (18.0, 59.7, 90.0))

    def test_namespaced_beta_board_keeps_manifest_identity(self):
        import cec_synth_pipeline as synth

        cfg = synth.Config.load("output-daughterboards/pcie-out-db")
        self.assertEqual(cfg.board, "pcie-out-db")
        self.assertEqual(
            cfg.board_key, "output-daughterboards/pcie-out-db")
        self.assertEqual(
            pipeline._board_identity(cfg),
            "output-daughterboards/pcie-out-db")

    def test_pcie2_config_resolves_current_schematic_derived_candidate(self):
        import cec_synth_pipeline as synth

        cfg = synth.Config.load("pcie-8pin-2port")
        self.assertEqual(
            Path(cfg.pcb).resolve(),
            (ROOT / "beta" / "pcie-8pin-2port" / "candidate" /
             "pcie-8pin-2port-candidate.kicad_pcb").resolve())

    def test_placement_gate_hoists_mechanical_but_not_route_only_failure(self):
        mechanical = mock.Mock(
            id="mezzanine-segment-contract", category="mechanical",
            status="ratified", checkable="yes", severity="hard")
        route_only = mock.Mock(
            id="high-speed-pair-physical-integrity", category="EMC/RF",
            status="ratified", checkable="yes", severity="hard")
        mislabeled_route_time = mock.Mock(
            id="board-routing-complete", category="placement",
            status="ratified", checkable="yes", severity="strong")
        cfg = mock.Mock(sch="/current/root.kicad_sch")
        with mock.patch("cec_constraints.run", return_value=[
                (mechanical, "FAIL", "anchor moved", None),
                (route_only, "FAIL", "pair not routed yet", None),
                (mislabeled_route_time, "FAIL", "ratlines remain", None)]):
            result = pipeline._placement_constraint_gate(
                "/tmp/placed.kicad_pcb", cfg)
        self.assertFalse(result["ok"])
        self.assertEqual(result["checked"], 1)
        self.assertEqual(
            [row["id"] for row in result["blockers"]],
            ["mezzanine-segment-contract"])

    def test_routed_seed_defers_only_decoupler_local_access_copper(self):
        evidence = {
            "ok": False, "errors": [],
            "stranded": {"ok": True}, "pair_launch": {"ok": True},
            "decoupler": {"ok": False, "violations": [
                ("C1", "U1.3[+3V3] local-cell-access", 1.2),
            ]},
        }
        routed = pipeline._placement_craft_gate(
            evidence, routed_input=True)
        unrouted = pipeline._placement_craft_gate(
            evidence, routed_input=False)
        bad_geometry = dict(evidence)
        bad_geometry["decoupler"] = {
            "ok": False, "violations": [
                ("C1", "U1.GND[+3V3]", 4.2),
            ]}

        self.assertTrue(routed["ok"])
        self.assertEqual(routed["deferred_to_route"][0]["ref"], "C1")
        self.assertFalse(unrouted["ok"])
        self.assertFalse(pipeline._placement_craft_gate(
            bad_geometry, routed_input=True)["ok"])

    def test_derived_route_geometry_enables_repair_without_craft_defect(self):
        self.assertTrue(pipeline._route_access_repair_allowed(
            {"route_geometry_deferred": True},
            {"craft_gate": {"ok": True, "deferred_to_route": []}}))
        self.assertTrue(pipeline._route_access_repair_allowed(
            {"route_geometry_deferred": False},
            {"craft_gate": {"deferred_to_route": [{"ref": "C1"}]}}))
        self.assertFalse(pipeline._route_access_repair_allowed(
            {"route_geometry_deferred": False},
            {"craft_gate": {"ok": True, "deferred_to_route": []}}))

    def test_open_placement_fiducials_remain_reconsiderable(self):
        open_board = mock.Mock()
        open_board.GetTracks.return_value = []
        routed_board = mock.Mock()
        routed_board.GetTracks.return_value = [object()]
        with mock.patch("pcbnew.LoadBoard", side_effect=[
                open_board, routed_board]) as load:
            self.assertTrue(
                pipeline._placement_fiducials_reconsiderable("open.kicad_pcb"))
            self.assertFalse(
                pipeline._placement_fiducials_reconsiderable(
                    "routed.kicad_pcb"))
            self.assertTrue(
                pipeline._placement_fiducials_reconsiderable(
                    "replacement.kicad_pcb", replace=True))
        self.assertEqual(load.call_count, 2)

    def test_priority_route_gate_owns_critical_escape_and_fanout(self):
        refused = pipeline._placement_priority_route_gate({
            "critical_route_refused_count": 2,
            "critical_pin_access_blocked_count": 1,
            "fanout_blocked_count": 3,
            # An ordinary bent escape warning is intentionally not a hard
            # placement blocker.
            "pin_access_blocked_count": 8,
        })
        clean = pipeline._placement_priority_route_gate({
            "critical_route_refused_count": 0,
            "critical_pin_access_blocked_count": 0,
            "fanout_blocked_count": 0,
            "pin_access_blocked_count": 8,
        })

        self.assertFalse(refused["ok"])
        self.assertEqual(
            [row["term"] for row in refused["blockers"]],
            ["declared_priority_route", "critical_pin_escape",
             "package_fanout"])
        self.assertTrue(clean["ok"])

    def test_placement_preflight_uses_and_restores_production_owner_order(self):
        import cec_synth_pipeline as synth

        with mock.patch.dict(os.environ, {
                "CEC_PROSPECTIVE_POUR_RESERVATIONS": "before",
                "CEC_ROUTE_PRIORITY_POLICY": "power-first"}, clear=False):
            with synth._placement_route_preflight_env():
                self.assertEqual(
                    os.environ["CEC_PROSPECTIVE_POUR_RESERVATIONS"], "1")
                self.assertEqual(
                    os.environ["CEC_ROUTE_PRIORITY_POLICY"],
                    "critical-first")
            self.assertEqual(
                os.environ["CEC_PROSPECTIVE_POUR_RESERVATIONS"], "before")
            self.assertEqual(
                os.environ["CEC_ROUTE_PRIORITY_POLICY"], "power-first")

    def test_existing_open_placement_enters_exact_priority_repair(self):
        import contextlib
        import cec_synth_pipeline as synth

        cfg = SimpleNamespace(params={
            "placement_route_repair_trials": 16,
            "placement_route_repair_rounds": 2,
            "placement_route_repair_full_evals": 4,
            "placement_route_preflight_grid_mm": 1.0,
            "placement_route_preflight_iters": 4,
            "placement_route_preflight_backend": "cpu",
            "placement_route_preflight_multiresolution": True,
        })
        loaded = mock.Mock()
        loaded.GetTracks.return_value = []
        candidate = SimpleNamespace(route_preflight={})
        repaired = SimpleNamespace(route_preflight={
            "critical_route_refused_count": 0})
        with mock.patch("pcbnew.LoadBoard", return_value=loaded), \
                mock.patch.object(
                    synth, "config_with_board_route_authority",
                    return_value=(cfg, {"ok": True, "bound": False,
                                        "applicable": False})), \
                mock.patch.object(
                    synth, "placement_candidate_from_board",
                    return_value=candidate), \
                mock.patch.object(
                    synth, "_oracle_env",
                    side_effect=lambda _params: contextlib.nullcontext()), \
                mock.patch.object(
                    synth, "_placement_route_preflight_env",
                    side_effect=lambda: contextlib.nullcontext()), \
                mock.patch.object(
                    synth, "repair_route_preflight_iterative",
                    return_value=(repaired, {"changed": True,
                                             "accepted_count": 1})) as repair, \
                mock.patch.object(synth, "materialize") as materialize:
            completion_report = {"final_completion": {
                "refused_details": [{"certificate": {"net": "/N"}}]}}
            result = pipeline._repair_placement_priority_routes(
                cfg, "/tmp/open.kicad_pcb",
                completion_report=completion_report)

        self.assertTrue(result["ok"])
        self.assertTrue(result["changed"])
        self.assertEqual(result["result_evidence"][
            "critical_route_refused_count"], 0)
        repair.assert_called_once()
        self.assertIs(
            repair.call_args.kwargs["completion_report"],
            completion_report)
        materialize.assert_called_once_with(
            repaired, cfg, str(Path("/tmp/open.kicad_pcb").resolve()))

    def test_placement_power_authority_snapshot_rolls_back_as_one_unit(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            board = root / "board.kicad_pcb"
            state = root / "board.pourfirst-state.json"
            skeleton = root / "board.pourfirst-skeleton.kicad_pcb"
            board.write_text("placement-a", encoding="utf-8")
            state.write_text("state-a", encoding="utf-8")
            skeleton.write_text("skeleton-a", encoding="utf-8")
            snapshot = root / "snapshot"
            report = pipeline._snapshot_placement_authority(
                board, snapshot)

            board.write_text("placement-b", encoding="utf-8")
            state.write_text("state-b", encoding="utf-8")
            skeleton.write_text("skeleton-b", encoding="utf-8")
            generated_after_snapshot = root / "board.pourplan.json"
            generated_after_snapshot.write_text("stale", encoding="utf-8")
            restored = pipeline._restore_placement_authority(
                board, snapshot)

            self.assertEqual(board.read_text(encoding="utf-8"),
                             "placement-a")
            self.assertEqual(state.read_text(encoding="utf-8"), "state-a")
            self.assertEqual(skeleton.read_text(encoding="utf-8"),
                             "skeleton-a")
            self.assertFalse(generated_after_snapshot.exists())
            self.assertIn(board.name, report["files"])
            self.assertTrue(restored["ok"])

    def test_placement_power_authority_snapshot_rejects_incomplete_input(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            board = root / "board.kicad_pcb"
            board.write_text("placement", encoding="utf-8")
            snapshot = root / "snapshot"
            snapshot.mkdir()
            (snapshot / "manifest.json").write_text(json.dumps({
                "schema": 1, "files": ["board.pourfirst-state.json"],
            }), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "incomplete or unsafe"):
                pipeline._restore_placement_authority(board, snapshot)

    def test_placement_power_authority_payload_rehomes_exact_transaction(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            scratch = root / "trial-07.kicad_pcb"
            scratch.write_bytes(b"exact-board")
            scratch_skeleton = root / \
                "trial-07.pourfirst-skeleton.kicad_pcb"
            scratch_skeleton.write_bytes(b"exact-skeleton")
            (root / "trial-07.pourfirst-state.json").write_text(
                json.dumps({"skeleton": str(scratch_skeleton),
                            "geometry": [1, 2, 3]}),
                encoding="utf-8")
            target = root / "canonical.kicad_pcb"
            target.write_bytes(b"old-board")
            stale = root / "canonical.pourplan.json"
            stale.write_bytes(b"old-plan")

            payload = pipeline._capture_placement_authority_payload(
                scratch)
            published = pipeline._publish_placement_authority_payload(
                target, payload)

            self.assertEqual(target.read_bytes(), b"exact-board")
            state = json.loads(
                (root / "canonical.pourfirst-state.json").read_text(
                    encoding="utf-8"))
            self.assertEqual(
                state["skeleton"],
                str(root / "canonical.pourfirst-skeleton.kicad_pcb"))
            self.assertEqual(state["geometry"], [1, 2, 3])
            self.assertEqual(
                (root / "canonical.pourfirst-skeleton.kicad_pcb").read_bytes(),
                b"exact-skeleton")
            self.assertFalse(stale.exists())
            self.assertTrue(published["ok"])
            self.assertIn(".pourfirst-state.json", published["roles"])

    def test_stale_power_only_move_is_replanned_before_route_acceptance(self):
        import cec_route_preflight
        import cec_synth_pipeline as synth

        with tempfile.TemporaryDirectory() as temp:
            board = Path(temp) / "board.kicad_pcb"
            board.write_text("baseline", encoding="utf-8")
            stale_state = Path(temp) / "board.pourfirst-state.json"
            stale_state.write_text("stale", encoding="utf-8")
            cfg = SimpleNamespace(params={
                "placement_power_replan_candidates": 2,
                "pourfirst_state": "/stale/state.json",
                "pourfirst_avoid_boxes": [{"net": "/OLD"}],
            })
            ordinary = {
                "schema": 1, "ok": True, "changed": False,
                "accepted_count": 0, "baseline_key": [0, 2],
                "result_key": [0, 2], "rounds": [{
                    "power_replan_candidates": [
                        {"kind": "station", "placements": {
                            "U1": [2.0, 1.0, 0.0]}},
                        {"kind": "station", "placements": {
                            "U1": [3.0, 1.0, 0.0]}},
                    ],
                }],
            }

            def candidate(*_args):
                return SimpleNamespace(P={"U1": (1.0, 1.0, 0.0)})

            def materialize(_candidate, _cfg, path):
                Path(path).write_text("candidate", encoding="utf-8")

            with mock.patch.object(
                    synth, "placement_candidate_from_board",
                    side_effect=candidate), \
                    mock.patch.object(
                        synth, "materialize", side_effect=materialize), \
                    mock.patch.object(
                        synth, "_oracle_pads_in_bounds",
                        return_value={"ok": True}), \
                    mock.patch.object(
                        synth, "_oracle_courtyard_overlaps",
                        return_value={"ok": True}), \
                    mock.patch.object(
                        synth, "placement_craft_evidence",
                        return_value={"decoupler": {"ok": True}}), \
                    mock.patch.object(
                        pipeline, "_placement_craft_gate",
                        return_value={"ok": True}), \
                    mock.patch.object(
                        pipeline, "_placement_constraint_gate",
                        return_value={"ok": True}), \
                    mock.patch.object(
                        pipeline, "_ensure_placement_route_authority",
                        return_value={"ok": True}), \
                    mock.patch.object(
                        pipeline, "_measure_placement_priority_routes",
                        side_effect=[{"key": [0, 3]}, {"key": [0, 0]}]), \
                    mock.patch.object(
                        cec_route_preflight, "placement_evidence_key",
                        side_effect=lambda evidence: tuple(evidence["key"])):
                result = pipeline.\
                    _repair_placement_priority_routes_with_power_replan(
                        cfg, board, ordinary)

        self.assertTrue(result["changed"])
        self.assertTrue(result["power_replan"]["accepted"])
        self.assertEqual(result["power_replan"]["selected_index"], 1)
        self.assertEqual(result["result_key"], [0, 0])
        self.assertNotIn("pourfirst_state", cfg.params)
        self.assertNotIn("pourfirst_avoid_boxes", cfg.params)
        self.assertFalse(stale_state.exists())

    def test_priority_repair_history_names_post_kelvin_rejection_stage(self):
        report = {"rounds": [{
            "round": 1, "reason": "no_finalist", "attempted": 3,
            "legal": 2, "kelvin_screened": 2, "full_evaluated": 0,
            "kelvin_probe_results": [{
                "move_index": 0, "kind": "rotate_cell",
                "refs": ["U1", "C1"],
                "critical_route_refused_count": 0,
            }],
            "finalist_craft_rejected": [{
                "move_index": 0, "kind": "rotate_cell",
                "refs": ["U1", "C1"],
                "baseline_key": [0, 0], "candidate_key": [0, 1],
                "craft": {
                    "decoupler": {"ok": True},
                    "pour_territory": {"ok": False},
                },
            }],
            "finalist_stale_power_handoff": [{
                "move_index": 0, "kind": "rotate_cell",
                "old_authority_collision_count": 1,
            }],
            "power_replan_candidates": [{"kind": "rotate_cell"}],
        }]}

        summary = pipeline._compact_priority_repair_round_history(report)

        self.assertEqual(summary[0]["zero_refusal_candidates"][0][
            "move_index"], 0)
        self.assertEqual(summary[0]["craft_rejected"][0][
            "failed_terms"], ["pour_territory"])
        self.assertEqual(summary[0]["power_replan_candidate_count"], 1)

    def test_non_manifest_probe_requires_explicit_derived_input(self):
        import cec_synth_pipeline as synth

        cfg = synth.Config.load("hub-standard-rev2")
        with tempfile.TemporaryDirectory() as temp:
            probe = Path(temp) / "old-probe.kicad_pcb"
            probe.write_bytes(Path(cfg.pcb).read_bytes())
            report = Path(temp) / "intake.json"
            with mock.patch("cec_constraints.intake_gate",
                            return_value={"ok": True, "reasons": []}) as intake_gate, \
                 mock.patch("cec_beta_electrical_audit.audit",
                            return_value={"findings": []}):
                refused = pipeline._source_intake(cfg, probe, report)
                allowed = pipeline._source_intake(
                    cfg, probe, report, allow_derived_input=True)

        self.assertFalse(refused["ok"])
        self.assertFalse(refused["canonical_input"])
        self.assertIn("not the current manifest PCB",
                      " ".join(refused["manifest_errors"]))
        self.assertTrue(allowed["ok"])
        self.assertTrue(allowed["derived_input_allowed"])
        self.assertTrue(allowed["route_geometry_deferred"])
        self.assertEqual(
            [call.kwargs["defer_route_geometry"]
             for call in intake_gate.call_args_list],
            [False, True])

    def test_source_intake_fails_closed_on_board_electrical_blocker(self):
        import cec_synth_pipeline as synth

        cfg = synth.Config.load("hub-standard-rev2")
        blocker = {
            "board": "hub-standard-rev2 + hub-legacy-comparison",
            "severity": "BLOCKER",
            "code": "REGULATOR_HEADROOM_UNPROVEN",
            "ref": "U1",
            "message": "worst-case load exceeds the proven source budget",
        }
        unrelated = {
            "board": "pcie-8pin-2port",
            "severity": "BLOCKER",
            "code": "UNRELATED",
            "message": "belongs to another board",
        }
        with tempfile.TemporaryDirectory() as temp:
            report = Path(temp) / "intake.json"
            with mock.patch("cec_constraints.intake_gate",
                            return_value={"ok": True, "reasons": []}), \
                 mock.patch("cec_beta_electrical_audit.audit",
                            return_value={"findings": [blocker, unrelated]}):
                result = pipeline._source_intake(
                    cfg, Path(cfg.pcb), report)

        electrical = result["electrical_source_audit"]
        self.assertFalse(result["ok"])
        self.assertFalse(electrical["ok"])
        self.assertEqual(electrical["blocker_count"], 1)
        self.assertEqual(electrical["findings"], [blocker])
        self.assertIn("REGULATOR_HEADROOM_UNPROVEN U1",
                      " ".join(electrical["reasons"]))

    def test_content_manifest_detects_tampering(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            (temp / "board.kicad_pcb").write_text("board", encoding="utf-8")
            (temp / "gerbers").mkdir()
            copper = temp / "gerbers" / "board-F_Cu.gtl"
            copper.write_text("%TF.FileFunction,Copper,L1,Top*%", encoding="utf-8")
            manifest = pipeline.write_content_manifest(
                temp, board="hub", source_signature={"sha256": "source"},
                signoff={"ok": True}, extra={"release_class": "TEST"}
            )
            self.assertEqual(pipeline.verify_content_manifest(manifest),
                             (True, "verified"))
            copper.write_text("tampered", encoding="utf-8")
            ok, reason = pipeline.verify_content_manifest(manifest)
            self.assertFalse(ok)
            self.assertIn("artifact mismatch", reason)

    def test_deterministic_zip_is_byte_reproducible(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            package = temp / "package"
            package.mkdir()
            (package / "b.txt").write_text("b", encoding="utf-8")
            (package / "a.txt").write_text("a", encoding="utf-8")
            first = temp / "first.zip"
            second = temp / "second.zip"
            pipeline._deterministic_zip(package, first)
            pipeline._deterministic_zip(package, second)
            self.assertEqual(pipeline.sha256_file(first),
                             pipeline.sha256_file(second))

    def test_atomic_json_leaves_valid_complete_document(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "nested" / "value.json"
            pipeline.atomic_json(target, {"hello": [1, 2, 3]})
            self.assertEqual(json.loads(target.read_text()),
                             {"hello": [1, 2, 3]})


class FullPipelineRouteStageTests(unittest.TestCase):
    def test_power_authority_placement_delta_is_rotation_aware(self):
        delta = pipeline._placement_delta(
            {"J1": (10.0, 5.0, 359.0), "J2": (2.0, 3.0, 0.0)},
            {"J1": (14.0, 5.0, 1.0), "J2": (2.0, 3.0, 360.0)})

        self.assertEqual([row["ref"] for row in delta], ["J1"])
        self.assertEqual(delta[0]["dx_mm"], 4.0)
        self.assertEqual(delta[0]["rotation_delta_deg"], 2.0)

    def test_stage_route_params_prefers_copied_frozen_state(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            board = temp / "renamed.kicad_pcb"
            state = temp / "renamed.pourfirst-state.json"
            board.write_text("board", encoding="utf-8")
            state.write_text('{"schema":3}\n', encoding="utf-8")
            cfg = SimpleNamespace(params={
                "pourfirst_state": "/stale/original-state.json",
                "lastmile": True,
            })

            params = pipeline._route_params_for_board(cfg, board)

            self.assertEqual(params["pourfirst_state"], str(state.resolve()))
            self.assertTrue(params["lastmile"])
            self.assertEqual(cfg.params["pourfirst_state"],
                             "/stale/original-state.json")

    def test_exact_route_authority_reuses_matching_sibling(self):
        import cec_synth_pipeline as synth

        cfg = synth.Config.load("pcie-8pin-2port")
        source = Path(cfg.pcb)
        with tempfile.TemporaryDirectory() as temp:
            board = Path(temp) / "board.kicad_pcb"
            shutil.copy2(source, board)
            state = board.with_name("board.pourfirst-state.json")
            import pcbnew
            loaded = pcbnew.LoadBoard(str(board))
            placements = {
                fp.GetReference(): [
                    fp.GetPosition().x / 1e6,
                    fp.GetPosition().y / 1e6,
                    float(fp.GetOrientationDegrees()),
                ]
                for fp in loaded.GetFootprints()}
            state.write_text(json.dumps({
                "schema": 3,
                "placement_scope": "complete",
                "placements": placements,
                "pours": [{"net": "/RAIL", "provenance": "pourfirst",
                           "layer": "F.Cu", "poly": [[1, 1], [2, 1],
                                                       [2, 2], [1, 2]]}],
                "vias": [], "frozen_nets": ["/RAIL"],
                "corridors": [{"net": "/RAIL", "layer": "F.Cu",
                               "x0": 1, "y0": 1, "x1": 2, "y1": 2}],
                "exclude_pins": [],
                "reserve_report": {"/RAIL": {"reserved": True}},
            }), encoding="utf-8")

            exact = {
                "schema": 1, "ok": True, "applicable": True,
                "reason": "exact_filled_power_admitted",
                "open_before": [], "open_after": [],
            }
            with mock.patch.object(
                    pipeline, "_exact_admit_placement_route_authority",
                    return_value=exact) as admit:
                result = pipeline._ensure_placement_route_authority(
                    cfg, board)

            self.assertTrue(result["ok"], result)
            self.assertTrue(result["reused"])
            self.assertEqual(result["state"], str(state))
            self.assertEqual(result["exact_admission"], exact)
            admit.assert_called_once_with(cfg, board.resolve(),
                                          state.resolve())

    def test_stage_copy_preserves_executable_route_sidecars(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            source = temp / "source.kicad_pcb"
            destination = temp / "stage" / "board.kicad_pcb"
            source.write_text("board", encoding="utf-8")
            source.with_name("source.pourplan.json").write_text(
                '{"schema":1,"kind":"plan"}\n', encoding="utf-8")
            source.with_name("source.pourfirst-state.json").write_text(
                '{"schema":3,"kind":"frozen"}\n', encoding="utf-8")
            source.with_name("source.railreport.json").write_text(
                '{"schema":1,"kind":"evidence"}\n', encoding="utf-8")

            copied = pipeline._copy_sidecars(source, destination)

            self.assertEqual(destination.read_text(encoding="utf-8"),
                             "board")
            for suffix, kind in (
                    (".pourplan.json", "plan"),
                    (".pourfirst-state.json", "frozen"),
                    (".railreport.json", "evidence")):
                sidecar = destination.with_name("board" + suffix)
                self.assertTrue(sidecar.is_file(), suffix)
                self.assertEqual(json.loads(sidecar.read_text())["kind"],
                                 kind)
                self.assertIn(str(sidecar), copied)

    def test_stage_copy_restores_manifest_netclass_authority(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            canonical = temp / "canonical.kicad_pcb"
            canonical.write_text("canonical", encoding="utf-8")
            canonical.with_suffix(".kicad_pro").write_text(json.dumps({
                "meta": {"filename": "canonical.kicad_pro"},
                "net_settings": {
                    "classes": [
                        {"name": "Default", "clearance": 0.2},
                        {"name": "USB", "clearance": 0.2,
                         "diff_pair_gap": 0.13}],
                    "netclass_patterns": [
                        {"netclass": "USB", "pattern": "/USB_D_P"},
                        {"netclass": "USB", "pattern": "/USB_D_N"}],
                    "netclass_assignments": None,
                },
            }), encoding="utf-8")
            source = temp / "source.kicad_pcb"
            source.write_text("board", encoding="utf-8")
            source.with_suffix(".kicad_pro").write_text(json.dumps({
                "meta": {"filename": "source.kicad_pro"},
                "net_settings": {
                    "classes": [
                        {"name": "Default", "clearance": 0.25},
                        {"name": "Derived", "clearance": 0.3}],
                    "netclass_patterns": [
                        {"netclass": "Wrong", "pattern": "/USB_D_P"},
                        {"netclass": "Derived", "pattern": "/EXTRA"}],
                },
            }), encoding="utf-8")
            destination = temp / "stage" / "board.kicad_pcb"
            cfg = SimpleNamespace(pcb=str(canonical), dir=str(temp))

            pipeline._copy_sidecars(source, destination, cfg=cfg)

            project = json.loads(
                destination.with_suffix(".kicad_pro").read_text())
            classes = {
                row["name"]: row
                for row in project["net_settings"]["classes"]}
            self.assertEqual(classes["Default"]["clearance"], 0.2)
            self.assertEqual(classes["USB"]["diff_pair_gap"], 0.13)
            self.assertIn("Derived", classes)
            patterns = {
                (row["netclass"], row["pattern"])
                for row in project["net_settings"]["netclass_patterns"]}
            self.assertIn(("USB", "/USB_D_P"), patterns)
            self.assertNotIn(("Wrong", "/USB_D_P"), patterns)
            self.assertIn(("Derived", "/EXTRA"), patterns)
            self.assertEqual(project["meta"]["filename"],
                             "board.kicad_pro")

    def test_project_authority_reports_silent_default_only_regression(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            authority = temp / "authority.kicad_pro"
            target = temp / "target.kicad_pro"
            authority.write_text(json.dumps({"net_settings": {
                "classes": [{"name": "Default"}, {"name": "USB"}],
                "netclass_patterns": [
                    {"netclass": "USB", "pattern": "/USB_D_*"}],
            }}), encoding="utf-8")
            target.write_text(json.dumps({"net_settings": {
                "classes": [{"name": "Default"}],
                "netclass_patterns": [],
            }}), encoding="utf-8")

            report = pipeline._project_rule_authority_delta(
                authority, target)

            self.assertTrue(report["ok"])
            self.assertTrue(report["repair_required"])
            self.assertEqual(report["missing_classes"], ["USB"])
            self.assertEqual(report["missing_patterns"],
                             [["USB", "/USB_D_*"]])

    def test_parallel_route_worker_enables_real_seed_axis_and_restores(self):
        import cec_synth_pipeline as synth

        seen = {}

        def route_oracle(*_args, **kwargs):
            seen["axis"] = os.environ.get("CEC_FR_SEED_AXIS")
            seen["seed"] = kwargs["seed"]
            return {"gate": False, "routed": "/tmp/candidate.kicad_pcb"}

        payload = {
            "board": "/tmp/input.kicad_pcb",
            "board_name": "neutral-board",
            "params": {},
            "passes": 4,
            "opt": 5,
            "seed": 37,
            "timeout": 60,
            "thermal": "lazy",
            "work_dir": "/tmp/route-candidate-37",
            "allow_route_access_repair": False,
        }
        previous = os.environ.get("CEC_FR_SEED_AXIS")
        os.environ["CEC_FR_SEED_AXIS"] = "caller-value"
        try:
            with mock.patch.object(
                    synth.Config, "load",
                    return_value=SimpleNamespace(params={})) as load, \
                    mock.patch.object(
                        synth, "route_oracle_grade",
                        side_effect=route_oracle):
                result = pipeline._route_candidate_worker(payload)
            self.assertEqual(seen, {"axis": "1", "seed": 37})
            self.assertEqual(
                result["route_candidate_diversity"], {
                    "schema": 1,
                    "backend": "freerouting-cec-seed-axis",
                    "enabled": True,
                    "seed": 37,
                })
            self.assertEqual(os.environ.get("CEC_FR_SEED_AXIS"),
                             "caller-value")
            load.assert_called_once_with("neutral-board", params={})
        finally:
            if previous is None:
                os.environ.pop("CEC_FR_SEED_AXIS", None)
            else:
                os.environ["CEC_FR_SEED_AXIS"] = previous

    def test_route_stage_persists_structured_no_artifact_failures(self):
        import cec_synth_pipeline as synth

        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            source = temp / "in.kicad_pcb"
            source.write_text("source", encoding="utf-8")
            output = temp / "route"
            cfg = SimpleNamespace(
                board="neutral-board", dir=str(temp),
                params={"automatic_pin_escape_tier": True},
            )
            refusal = {
                "seed": 7, "gate": False, "routed": None,
                "failure_artifact": str(output / "priority.kicad_pcb"),
                "failure_stage": "decoupler_cell_priority",
                "error": "complete pre-route decoupler cell stage refused",
                "reasons": ["complete pre-route decoupler cell stage refused"],
                "gate_terms": {"routing_complete": False},
                "sort_key": [1, float("inf")],
            }
            with mock.patch.object(
                    synth, "route_oracle_grade", return_value=refusal):
                with self.assertRaisesRegex(
                        pipeline.PipelineBlocked,
                        "decoupler_cell_priority"):
                    pipeline._route_stage(
                        source, output, cfg, passes=1, opt=1,
                        seed=7, timeout=1, thermal="lazy")

            summary = json.loads(
                (output / "candidate-summary.json").read_text())
            self.assertIsNone(summary["winner_seed"])
            self.assertEqual(
                summary["candidates"][0]["failure_stage"],
                "decoupler_cell_priority")
            self.assertEqual(
                summary["candidates"][0]["failure_artifact"],
                str(output / "priority.kicad_pcb"))

    def test_route_probe_requires_and_reuses_admitted_placement(self):
        import cec_synth_pipeline as synth

        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            board = temp / "board.kicad_pcb"
            board.write_text("placement", encoding="utf-8")
            (temp / "board.placement.json").write_text(
                json.dumps({"ok": True}), encoding="utf-8")
            cfg = SimpleNamespace(board="neutral-board", params={})
            expected = {"ok": True, "board": str(board)}
            loaded_board = SimpleNamespace(GetTracks=lambda: [object()])
            with mock.patch.object(
                    synth.Config, "load", return_value=cfg) as load, \
                    mock.patch.object(
                        synth, "config_with_board_route_authority",
                        return_value=(cfg, {
                            "ok": True, "applicable": True, "bound": True,
                        })) as bind, \
                    mock.patch(
                        "pcbnew.LoadBoard", return_value=loaded_board), \
                    mock.patch.object(
                        synth, "placement_craft_evidence",
                        return_value={"ok": True}) as current_craft, \
                    mock.patch.object(
                        pipeline, "_route_stage",
                        return_value=expected) as route:
                result = pipeline.run_route_probe(
                    board_name="neutral-board", placement_board=board,
                    out_dir=temp / "probe", passes=3, opt=4,
                    route_seed=5, route_candidates=1,
                    route_timeout=60, thermal="lazy",
                    allow_route_access_repair=True)

            self.assertEqual(result, expected)
            load.assert_called_once_with("neutral-board")
            bind.assert_called_once_with(cfg, str(board.resolve()))
            current_craft.assert_called_once_with(
                str(board.resolve()), cfg=cfg, relief_diagnostics=False)
            self.assertEqual(route.call_args.args[0], board.resolve())
            self.assertEqual(
                route.call_args.args[1],
                (temp / "probe" / "04-route").resolve())
            self.assertTrue(
                route.call_args.kwargs["allow_route_access_repair"])

    def test_route_probe_revalidates_clean_placement_without_route_deferral(self):
        import cec_synth_pipeline as synth

        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            board = temp / "board.kicad_pcb"
            board.write_text("placement", encoding="utf-8")
            (temp / "board.placement.json").write_text(
                json.dumps({"ok": True}), encoding="utf-8")
            cfg = SimpleNamespace(board="neutral-board", params={})
            evidence = {
                "ok": False, "errors": [],
                "stranded": {"ok": True}, "pair_launch": {"ok": True},
                "critical_terminal_order": {"ok": True},
                "pour_territory": {"ok": True},
                "power_body_clearance": {"ok": True},
                "detection_cell": {"ok": True},
                "decoupler": {"ok": False, "violations": [
                    ("C1", "U1.3[+3V3] local-cell-access", 1.2),
                ]},
            }
            loaded_board = SimpleNamespace(GetTracks=lambda: [])
            with mock.patch.object(
                    synth.Config, "load", return_value=cfg), \
                    mock.patch.object(
                        synth, "config_with_board_route_authority",
                        return_value=(cfg, {
                            "ok": True, "applicable": True, "bound": True,
                        })), \
                    mock.patch(
                        "pcbnew.LoadBoard", return_value=loaded_board), \
                    mock.patch.object(
                        synth, "placement_craft_evidence",
                        return_value=evidence), \
                    mock.patch.object(pipeline, "_route_stage") as route:
                with self.assertRaisesRegex(
                        pipeline.PipelineBlocked,
                        "stale/non-admitted placement"):
                    pipeline.run_route_probe(
                        board_name="neutral-board", placement_board=board,
                        out_dir=temp / "probe",
                        allow_route_access_repair=True)
            route.assert_not_called()

    def test_verified_existing_placement_is_byte_preserved(self):
        import cec_synth_pipeline as synth

        source = (ROOT / "beta" / "output-daughterboards" /
                  "pcie-out-db" / "pcie-out-db-board.kicad_pcb")
        cfg = synth.Config.load("output-daughterboards/pcie-out-db")
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "board.kicad_pcb"
            result = pipeline._placement_stage(
                cfg, source, output, replace=False,
                strategies=("plain",), seeds=(0,), workers=1,
                craft_trials=1, craft_rounds=1, craft_epochs=1)
            self.assertTrue(result["ok"])
            self.assertFalse(result["craft_repair"]["changed"])
            self.assertEqual(
                pipeline.sha256_file(source), pipeline.sha256_file(output),
                "a no-op placement verification must preserve all copper and zones")

    def test_routed_canonical_input_never_enters_placement_rehydration(self):
        import cec_synth_pipeline as synth

        cfg = synth.Config.load("hub-standard-rev2")
        source = Path(cfg.pcb)
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "board.kicad_pcb"
            with mock.patch.object(
                    synth, "placement_candidate_from_board",
                    side_effect=AssertionError(
                        "routed input must remain read-only")):
                result = pipeline._placement_stage(
                    cfg, source, output, replace=False,
                    strategies=("plain",), seeds=(0,), workers=1,
                    craft_trials=1, craft_rounds=1, craft_epochs=1)
            self.assertEqual(
                result["craft_repair"]["skipped"],
                "routed_input_read_only")
            self.assertEqual(
                pipeline.sha256_file(source), pipeline.sha256_file(output))

    def test_canonical_route_enables_declared_winner_completion_and_fails_closed(self):
        import cec_synth_pipeline as synth

        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            source = temp / "in.kicad_pcb"
            routed = temp / "routed.kicad_pcb"
            source.write_text("source", encoding="utf-8")
            routed.write_text("routed", encoding="utf-8")
            cfg = SimpleNamespace(
                board="neutral-board", dir=str(temp),
                params={"lastmile_final_winner": True},
            )
            promoted = SimpleNamespace(
                board="neutral-board", dir=str(temp),
                params={"lastmile_final_winner": True,
                        "lastmile_final": True},
            )
            oracle = {
                "gate": False, "routed": str(routed), "drc": 1,
                "unconnected": 2, "gate_terms": {"drc": False},
            }
            seen = {}

            def route_oracle(*_args, **kwargs):
                seen["axis"] = os.environ.get("CEC_FR_SEED_AXIS")
                seen["seed"] = kwargs.get("seed")
                return oracle

            with mock.patch.object(
                    synth.Config, "load", return_value=promoted) as load, \
                    mock.patch.object(
                        synth, "route_oracle_grade", side_effect=route_oracle
                    ) as route:
                result = pipeline._route_stage(
                    source, temp / "work", cfg, passes=1, opt=1,
                    seed=0, timeout=1, thermal="lazy"
                )

            load.assert_called_once_with(
                "neutral-board",
                params={"lastmile_final_winner": True,
                        "lastmile_final": True,
                        "automatic_pin_escape_tier": True},
            )
            self.assertIs(route.call_args.kwargs["cfg"], promoted)
            self.assertEqual(seen, {"axis": "1", "seed": 0})
            self.assertTrue(result["winner_completion_enabled"])
            self.assertTrue(result["artifact_produced"])
            self.assertFalse(result["ok"])

    def test_gate_clean_route_runs_transactional_fab_polish(self):
        import cec_fab_repair
        import cec_synth_pipeline as synth

        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            source = temp / "in.kicad_pcb"
            routed = temp / "routed.kicad_pcb"
            source.write_text("source", encoding="utf-8")
            routed.write_text("routed", encoding="utf-8")
            cfg = SimpleNamespace(
                board="neutral-board", dir=str(temp),
                params={"automatic_pin_escape_tier": True})
            oracle = {
                "gate": True, "routed": str(routed), "drc": 0,
                "unconnected": 0, "kelvin_ok": True,
                "diffpair_ok": True, "gate_terms": {},
            }
            polish = {
                "schema": 1, "adopted": True, "chosen": "track_polish",
                "after": {"drc": 0, "unconnected": 0,
                          "kelvin_ok": True, "diffpair_ok": True},
            }
            with mock.patch.object(
                    synth, "route_oracle_grade", return_value=oracle), \
                    mock.patch.object(
                        cec_fab_repair, "repair_admitted",
                        return_value=polish) as repair_call:
                result = pipeline._route_stage(
                    source, temp / "work", cfg, passes=1, opt=1,
                    seed=0, timeout=1, thermal="lazy")

            repair_call.assert_called_once_with(str(routed))
            self.assertEqual(result["fab_repair"]["chosen"],
                             "track_polish")
            oracle_report = json.loads(
                (temp / "work" / "oracle.json").read_text())
            self.assertEqual(oracle_report["fab_repair"]["chosen"],
                             "track_polish")

    def test_incomplete_route_still_runs_monotonic_fab_polish(self):
        import cec_fab_repair
        import cec_synth_pipeline as synth

        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            source = temp / "in.kicad_pcb"
            routed = temp / "routed.kicad_pcb"
            source.write_text("source", encoding="utf-8")
            routed.write_text("routed", encoding="utf-8")
            cfg = SimpleNamespace(
                board="neutral-board", dir=str(temp),
                params={"automatic_pin_escape_tier": True})
            oracle = {
                "gate": False, "routed": str(routed), "drc": 0,
                "unconnected": 3, "kelvin_ok": True,
                "diffpair_ok": True,
                "gate_terms": {"routing_complete": False},
            }
            polish = {
                "schema": 1, "adopted": True,
                "chosen": "fab_polish",
                "after": {"drc": 0, "unconnected": 3,
                          "kelvin_ok": True, "diffpair_ok": True},
            }
            with mock.patch.object(
                    synth, "route_oracle_grade", return_value=oracle), \
                    mock.patch.object(
                        cec_fab_repair, "repair_admitted",
                        return_value=polish) as repair_call:
                result = pipeline._route_stage(
                    source, temp / "work", cfg, passes=1, opt=1,
                    seed=0, timeout=1, thermal="lazy")

            repair_call.assert_called_once_with(str(routed))
            self.assertFalse(result["ok"])
            self.assertEqual(result["fab_repair"]["chosen"], "fab_polish")


if __name__ == "__main__":
    unittest.main()
