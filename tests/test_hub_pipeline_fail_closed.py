#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""The standalone Hub runner may publish only a complete accepted artifact."""

import os
import pickle
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_constraints  # noqa: E402
import cec_router  # noqa: E402
import cec_slab_pour  # noqa: E402
import hub_pipeline_run as H  # noqa: E402


class TestHubAcceptance(unittest.TestCase):
    def test_router_timeout_retries_back_off_instead_of_increasing_work(self):
        state = SimpleNamespace(fr={"passes": 20, "opt_time": 50})
        timed_out = [SimpleNamespace(ok=False,
                                     err="run_freerouting timed out after 282s")
                     for _ in range(4)]
        verdict = cec_router.generation_timeout_backoff(timed_out, state)
        self.assertEqual(verdict.tier, "deterministic:timeout-backoff")
        self.assertEqual(verdict.edit["set"], {"passes": 12, "opt_time": 30})
        self.assertIsNone(cec_router.generation_timeout_backoff(
            [SimpleNamespace(ok=False, err="DSN export failed")], state))

    def test_repour_uses_current_ask_contract(self):
        nets = H._hub_pour_nets()
        self.assertIn("/POWER INPUT + SOURCE SELECTION/PSU_5V_KVM", nets)
        self.assertIn("/HOLD-UP + 3V3 REGULATOR/+5V_HOLD", nets)
        self.assertIn("/CAN + FOUR MODULE PORTS + STACK/VCC_P4", nets)
        self.assertNotIn("/PSU_5V_KVM", nets)
        self.assertEqual(len(nets), len(set(nets)))

    def test_repour_ask_names_exist_exactly_on_current_board(self):
        import pcbnew

        board = pcbnew.LoadBoard(os.path.join(ROOT, H.REF))
        board_nets = {str(name) for name in board.GetNetsByName().keys()}
        self.assertTrue(set(H._hub_pour_nets()).issubset(board_nets))

    def test_generated_rail_zone_names_are_version_independent(self):
        for prefix in H.PIPELINE_RAIL_ZONE_PREFIXES:
            with self.subTest(prefix=prefix):
                self.assertTrue(H._is_pipeline_rail_zone_name(prefix + "/PWR"))
        self.assertFalse(H._is_pipeline_rail_zone_name("GND Plane"))
        self.assertFalse(H._is_pipeline_rail_zone_name("hand-authored:+5V"))
        self.assertFalse(H._is_pipeline_rail_zone_name(None))

    def test_net_resolution_fails_closed_on_missing_or_ambiguous(self):
        board = os.path.join(ROOT, H.REF)
        with self.assertRaisesRegex(RuntimeError, "missing"):
            H._resolve_board_net_names(board, ("/DOES_NOT_EXIST",))

    def test_slab_failure_survives_worker_serialization(self):
        source = cec_slab_pour.SlabAllocationError(
            (("/PWR", "In3.Cu"),), {("/PWR", "In3.Cu"): {"reason": "fixture"}})
        restored = pickle.loads(pickle.dumps(source))
        self.assertEqual(restored.failures, source.failures)
        self.assertEqual(restored.report, source.report)
        self.assertEqual(str(restored), str(source))

    def test_route_environment_enables_diversity_and_restores_process(self):
        keys = ("CEC_FR_SEED_AXIS", "CEC_FR_PLATEAU_KILL", "CEC_FR_PLATEAU_FLOOR")
        before = {key: os.environ.get(key) for key in keys}
        try:
            for key in keys:
                os.environ.pop(key, None)
            with H._freerouting_wave_environment({"wave_plateau_floor": 150}):
                self.assertEqual(os.environ["CEC_FR_SEED_AXIS"], "1")
                self.assertEqual(os.environ["CEC_FR_PLATEAU_KILL"], "4")
                self.assertEqual(os.environ["CEC_FR_PLATEAU_FLOOR"], "150")
            self.assertTrue(all(key not in os.environ for key in keys))
        finally:
            for key, value in before.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_hub_repour_uses_live_overunder_contract(self):
        import cec_fr
        import cec_fresh_wave
        import cec_slab_pour
        import pcbnew

        self.assertTrue(cec_fresh_wave._board_params("hub-standard-rev2")["overunder"])
        nets = H._hub_pour_nets()
        rows = {net: {"path_found": True, "segments": 1, "bridges": 0,
                      "layers_used": ["In3.Cu"]} for net in nets}
        with mock.patch.object(pcbnew, "LoadBoard", return_value=object()), \
                mock.patch.object(pcbnew, "SaveBoard"), \
                mock.patch.object(cec_slab_pour, "synthesize_overunder_pours",
                                  return_value=([{"net": nets[0]}], [(nets[0], 1, 2)], rows)) as solve, \
                mock.patch.object(cec_fr, "add_power_pours") as add_pours, \
                mock.patch.object(cec_fr, "add_overunder_vias",
                                  return_value=[object()]) as add_vias:
            report = H._repour_worker("fixture.kicad_pcb", nets)
        self.assertEqual(report["planner"], "overunder")
        self.assertEqual(report["rails"], 10)
        self.assertEqual(report["vias"], 1)
        self.assertTrue(all(row["path_found"] for row in report["paths"].values()))
        solve.assert_called_once()
        add_pours.assert_called_once()
        add_vias.assert_called_once()

    def test_dedicated_runner_uses_live_size_specific_mezzanine_pins(self):
        import cec_fresh_wave

        for width, height in ((86.1, 74.1), (89.1, 77.1)):
            params = cec_fresh_wave._placement_params(  # noqa: SLF001
                "hub-standard-rev2", width, height)
            expected = cec_fresh_wave.mating_frame_pins(
                width, height, cec_fresh_wave.MEZZ_HUB_24PIN,
                "hub-standard-rev2")["anchor_pins"]
            for ref in ("J6P", "J6C", "J6D"):
                self.assertEqual(params["anchor_pins"][ref], expected[ref])
            self.assertTrue(params["overunder"])
            self.assertTrue(params["power_pickup"])
            self.assertTrue(params["lastmile"])

    def test_all_terms_are_required(self):
        args = ({"gates_pass": True}, 0, [], True, True)
        terms, accepted = H._acceptance_terms(*args)
        self.assertTrue(accepted)
        self.assertTrue(all(terms.values()))
        mutations = [
            ({"gates_pass": False}, 0, [], True, True),
            ({"gates_pass": True}, 1, [], True, True),
            ({"gates_pass": True}, 0, [object()], True, True),
            ({"gates_pass": True}, 0, [], False, True),
            ({"gates_pass": True}, 0, [], True, False),
        ]
        for values in mutations:
            with self.subTest(values=values):
                self.assertFalse(H._acceptance_terms(*values)[1])

    def test_pre_route_gate_refuses_contact_faults_not_expected_open_copper(self):
        types = {"clearance": 2, "via_dangling": 31,
                 "isolated_copper": 7, "copper_edge_clearance": 2}
        loci = [{"type": kind, "where": kind} for kind in types]
        with mock.patch.object(H.cec_score, "drc_types",
                               return_value=(types, loci)):
            result = H._pre_route_materialization_gate("fixture.kicad_pcb")
        self.assertFalse(result["ok"])
        self.assertEqual(result["fatal"], {"clearance": 2})
        self.assertEqual(result["loci"],
                         [{"type": "clearance", "where": "clearance"}])

    def test_pre_route_gate_allows_expected_unrouted_findings(self):
        types = {"via_dangling": 31, "isolated_copper": 7,
                 "copper_edge_clearance": 2}
        with mock.patch.object(H.cec_score, "drc_types",
                               return_value=(types, [])):
            result = H._pre_route_materialization_gate("fixture.kicad_pcb")
        self.assertTrue(result["ok"])
        self.assertEqual(result["fatal"], {})

    def test_conformance_exception_is_a_failure(self):
        messages = []
        cfg = type("Cfg", (), {"params": {}})()
        with mock.patch.object(cec_constraints, "run", side_effect=RuntimeError("boom")):
            count, rows = H._conformance("fixture.kicad_pcb", cfg, messages.append)
        self.assertEqual(count, 1)
        self.assertEqual(rows[0]["status"], "ERROR")
        self.assertIn("boom", rows[0]["detail"])

    def test_reference_intake_binds_parent_schematic(self):
        result = {"ok": False, "reasons": ["fixture"]}
        with mock.patch.object(cec_constraints, "intake_gate",
                               return_value=result) as intake:
            self.assertIs(H._reference_intake(), result)
        board_arg = os.path.normpath(intake.call_args.args[0])
        sch_arg = os.path.normpath(intake.call_args.kwargs["ctx"]["sch"])
        self.assertEqual(board_arg, os.path.normpath(os.path.join(ROOT, H.REF)))
        self.assertEqual(sch_arg, os.path.normpath(os.path.join(ROOT, H.REF_SCH)))

    def test_route_timeout_divides_remaining_window(self):
        self.assertEqual(H._route_iteration_timeout(150, 3), 40)
        with self.assertRaises(RuntimeError):
            H._route_iteration_timeout(20, 3)

    def test_route_parallelism_uses_compute_but_reserves_memory(self):
        gib = 1024**3
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CEC_HUB_ROUTE_WORKERS", None)
            self.assertEqual(H._hub_route_parallelism(32, 23 * gib), 16)
            self.assertEqual(H._hub_route_parallelism(8, 8 * gib), 4)
            self.assertEqual(H._hub_route_parallelism(2, 3 * gib), 1)

    def test_route_parallelism_override_cannot_exceed_safe_ceiling(self):
        gib = 1024**3
        with mock.patch.dict(os.environ, {"CEC_HUB_ROUTE_WORKERS": "12"}):
            self.assertEqual(H._hub_route_parallelism(32, 23 * gib), 12)
        with mock.patch.dict(os.environ, {"CEC_HUB_ROUTE_WORKERS": "99"}):
            self.assertEqual(H._hub_route_parallelism(32, 23 * gib), 16)

    def test_short_wide_route_uses_depth_that_can_finish(self):
        self.assertEqual(H._hub_route_passes(283, 16, requested=12), 7)
        self.assertEqual(H._hub_route_passes(283, 8, requested=12), 9)
        self.assertEqual(H._hub_route_passes(400, 16, requested=12), 7)
        self.assertEqual(H._hub_route_passes(582, 16, requested=12), 7)
        self.assertEqual(H._hub_route_passes(700, 16, requested=12), 12)
        self.assertEqual(H._hub_route_passes(283, 16, requested=6), 6)

    def test_closure_prefers_smallest_equally_legal_outline(self):
        def candidate(score, residual=0, crossings=0):
            return SimpleNamespace(
                residual=residual, corridor_cross=crossings,
                corridor_cross_aware=crossings,
                proxy={"proxy_score": score})

        small = (candidate(101.0), 86.1, 74.1, object())
        large = (candidate(99.0), 89.1, 77.1, object())
        self.assertLess(H._closure_placement_key(small),
                        H._closure_placement_key(large))

        # Area is never allowed to conceal a real legality improvement.
        illegal_small = (candidate(1.0, residual=1), 86.1, 74.1, object())
        self.assertLess(H._closure_placement_key(large),
                        H._closure_placement_key(illegal_small))

    def test_board_spec_carries_worker_timeout(self):
        import tempfile
        import cec_router

        board = os.path.join(ROOT, H.REF)
        with tempfile.TemporaryDirectory() as out:
            spec, _ = cec_router.board_spec(board, out, seeds=(0,), fr_timeout=17)
        self.assertEqual(spec.regions[0].fr_params["timeout"], 17)

    def test_empty_route_batch_returns_controlled_failure(self):
        import tempfile

        board = os.path.join(ROOT, H.REF)
        with tempfile.TemporaryDirectory() as out, \
                mock.patch.dict(os.environ, {"CEC_SKIP_INTAKE": "1"}), \
                mock.patch.object(cec_router.cec_fr, "generate_batch", return_value=[]):
            spec, _ = cec_router.board_spec(
                board, out, seeds=(0,), max_iters=1, fr_timeout=5)
            final, log = cec_router.route(board, spec, verbose=False,
                                          work_dir=os.path.join(out, "work"))
        self.assertIsNone(final)
        self.assertFalse(log.final["verdict"]["gates_pass"])

    def test_segmented_reference_is_not_truncated_by_repair_parser(self):
        desc = "Pad 1 [/PWR] of J6P; Pad 2 [/OTHER] of U32"
        self.assertEqual(cec_router._drc_item_references(desc), ["J6P", "U32"])

    def test_invalid_advisory_reference_is_refused_without_aborting(self):
        board = os.path.join(ROOT, H.REF)
        region = cec_router.Region("fixture")
        state = cec_router.RegionState(region, board, (0,))
        log = cec_router.DecisionLog()
        edit = {"type": "place_nudge", "ref": "J_DOES_NOT_EXIST",
                "delta": (0.4, 0.4)}
        self.assertFalse(cec_router._apply_edit_guarded(state, edit, log, region, 1))
        self.assertEqual(log.entries[-1]["note"], "invalid-edit-reference")
        self.assertEqual(log.entries[-1]["verdict"]["action"], "refuse")

    def test_router_refuses_to_nudge_locked_mechanical_footprint(self):
        import shutil
        import tempfile
        import pcbnew

        source = os.path.join(ROOT, H.REF)
        with tempfile.TemporaryDirectory() as out:
            board = os.path.join(out, "locked.kicad_pcb")
            shutil.copy(source, board)
            loaded = pcbnew.LoadBoard(board)
            fp = loaded.FindFootprintByReference("J6P")
            self.assertIsNotNone(fp)
            before = fp.GetPosition()
            fp.SetLocked(True)
            pcbnew.SaveBoard(board, loaded)

            region = cec_router.Region("fixture")
            state = cec_router.RegionState(region, board, (0,))
            log = cec_router.DecisionLog()
            edit = {"type": "place_nudge", "ref": "J6P",
                    "delta": (0.4, 0.4)}
            self.assertFalse(cec_router._apply_edit_guarded(
                state, edit, log, region, 1))
            self.assertEqual(log.entries[-1]["note"], "fixed-footprint-edit")
            after = pcbnew.LoadBoard(board).FindFootprintByReference(
                "J6P").GetPosition()
            self.assertEqual((after.x, after.y), (before.x, before.y))

    def test_route_intake_exception_refuses(self):
        import tempfile

        board = os.path.join(ROOT, H.REF)
        with tempfile.TemporaryDirectory() as out, \
                mock.patch.dict(os.environ, {"CEC_SKIP_INTAKE": ""}), \
                mock.patch.object(cec_constraints, "intake_gate",
                                  side_effect=RuntimeError("synthetic intake crash")):
            spec, _ = cec_router.board_spec(board, out, seeds=(0,), max_iters=1)
            with self.assertRaisesRegex(RuntimeError, "failed closed"):
                cec_router.route(board, spec, verbose=False,
                                 work_dir=os.path.join(out, "work"))


if __name__ == "__main__":
    unittest.main()
