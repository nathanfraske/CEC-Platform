#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""The standalone Hub runner may publish only a complete accepted artifact."""

import os
import pickle
import sys
import unittest
import contextlib
from types import SimpleNamespace
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_constraints  # noqa: E402
import cec_router  # noqa: E402
import cec_slab_pour  # noqa: E402
import hub_pipeline_run as H  # noqa: E402


class TestHubAcceptance(unittest.TestCase):
    def test_physics_requires_clean_closed_route(self):
        self.assertEqual(
            H._physics_route_prerequisite({"drc": 0, "unconnected": 0}),
            (True, {"drc": 0, "unconnected": 0}))
        self.assertEqual(
            H._physics_route_prerequisite({"drc": 2, "unconnected": 7}),
            (False, {"drc": 2, "unconnected": 7}))

    def test_materialization_spawns_workers_inside_candidate_policy(self):
        params = {"power_pour_layers": ("In3.Cu", "B.Cu", "F.Cu"),
                  "pour_reserve": True}
        active = {"value": False}
        applied = []

        @contextlib.contextmanager
        def policy(received):
            self.assertEqual(received, params)
            active["value"] = True
            try:
                yield
            finally:
                active["value"] = False

        class Pool:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                pass

            def apply(self, function, args):
                self.assert_policy()
                applied.append(function.__name__)
                if function is H._copy_reference_worker:
                    return {"rewritten": 0}
                if function is H._reposition_worker:
                    return 125
                if function is H._prepare_repour_worker:
                    return {"pickup": {"vias": 3}}
                if function is H._repour_worker:
                    return {"rails": 10}
                if function is H._fill_worker:
                    return {"areas": 36}
                if function is H._cleanup_zones_worker:
                    return 0
                return {}

            @staticmethod
            def assert_policy():
                if not active["value"]:
                    raise AssertionError("worker spawned outside candidate policy")

        fake_ctx = SimpleNamespace(Pool=lambda _size: Pool())
        candidate = SimpleNamespace(P={"U1": (1.0, 2.0, 0.0)})
        with mock.patch.object(H.S, "_oracle_env", side_effect=policy) as env, \
                mock.patch("multiprocessing.get_context", return_value=fake_ctx), \
                mock.patch.object(H, "_stage_reference_sidecars"), \
                mock.patch.object(H, "_hub_pour_nets", return_value=("/PWR",)):
            _out, moved, report = H.materialize_onto_reference(
                candidate, "reference.kicad_pcb", "candidate.kicad_pcb",
                params=params)

        env.assert_called_once_with(params)
        self.assertEqual(moved, 125)
        self.assertEqual(report["pre_route_finish"]["floating_zones_removed"], 0)
        self.assertEqual(applied, [
            "_copy_reference_worker", "_reposition_worker",
            "_prepare_repour_worker", "_preroute_connector_power_worker",
            "_repour_worker", "_fill_worker",
            "_cleanup_zones_worker"])

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
                self.assertTrue(H._is_pipeline_rail_zone_name(
                    H.BOOTSTRAP_ENVELOPE_PREFIX + prefix + "/PWR"))
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
        self.assertEqual(report["rails"], 8)
        self.assertEqual(report["vias"], 1)
        self.assertTrue(all(row["path_found"] for row in report["paths"].values()))
        solve.assert_called_once()
        add_pours.assert_called_once()
        add_vias.assert_called_once()

    def test_hub_usb_satellites_reserve_the_pair_breakout(self):
        import cec_fresh_wave

        seats = cec_fresh_wave._board_params(
            "hub-standard-rev2")["anchor_local_placements"]
        self.assertEqual(set(seats), {"D6", "R9", "R10"})
        self.assertEqual(seats["D6"]["owner"], "J_USB")
        self.assertEqual(seats["D6"]["rotation"], 270.0)
        # CC pull-downs flank the protector/pair centreline.
        self.assertLess(seats["R9"]["offset"][0], seats["D6"]["offset"][0])
        self.assertGreater(seats["R10"]["offset"][0], seats["D6"]["offset"][0])
        self.assertEqual(abs(seats["R9"]["offset"][0]),
                         abs(seats["R10"]["offset"][0]))

    def test_hub_led_ring_orientations_keep_data_and_bypass_lands_local(self):
        import math
        import pcbnew
        import cec_fresh_wave

        board = pcbnew.LoadBoard(os.path.join(ROOT, H.REF))
        offsets = cec_fresh_wave._board_params(
            "hub-standard-rev2")["rigid_groups"][0]["offsets"]
        for ref, (x, y, rotation) in offsets.items():
            footprint = board.FindFootprintByReference(ref)
            self.assertIsNotNone(footprint, ref)
            footprint.SetPosition(pcbnew.VECTOR2I(
                int((x + 30.0) * 1e6), int((y + 30.0) * 1e6)))
            footprint.SetOrientationDegrees(rotation)

        def pad_distance(a_ref, a_pad, b_ref, b_pad):
            a = board.FindFootprintByReference(a_ref).FindPadByNumber(a_pad)
            b = board.FindFootprintByReference(b_ref).FindPadByNumber(b_pad)
            self.assertIsNotNone(a, "%s.%s" % (a_ref, a_pad))
            self.assertIsNotNone(b, "%s.%s" % (b_ref, b_pad))
            pa, pb = a.GetPosition(), b.GetPosition()
            return math.hypot(pa.x - pb.x, pa.y - pb.y) / 1e6

        chain = zip(("DL1", "DL2", "DL3", "DL4", "DL5"),
                    ("DL2", "DL3", "DL4", "DL5", "DL7"))
        self.assertLessEqual(max(
            pad_distance(source, "1", sink, "3")
            for source, sink in chain), 8.0)

        # The four LEDs whose bodies were rotated tangentially need their
        # associated +5VSB bypass land within one short local-link reach.
        for led, cap in (("DL1", "C29"), ("DL2", "C30"),
                         ("DL5", "C33"), ("DL7", "C34")):
            with self.subTest(led=led, cap=cap):
                self.assertLessEqual(pad_distance(led, "4", cap, "1"), 2.5)

    def test_fill_worker_synthesizes_pickups_against_real_rail_fill(self):
        import cec_fr
        import cec_precision_route
        import pcbnew

        class Zone:
            def UnFill(self):
                pass

        class Board:
            def Zones(self):
                return [Zone()]

            def Save(self, _out):
                pass

            def GetAreaCount(self):
                return 7

            def GetTracks(self):
                return []

            def BuildConnectivity(self):
                pass

        board = Board()
        filler = mock.Mock()
        pickup = {"pads": 3, "vias": 3, "stubs": 2, "pofv": 1,
                  "skipped": 0, "skipped_detail": []}
        bypass = {"pairs": 2, "linked": 2, "legs": 4, "refused": 0,
                  "ignored": 1, "detail": []}
        signal = {"networks": 3, "linked": 3, "legs": 5, "refused": 0,
                  "ignored": 7, "detail": []}
        same_footprint = {"groups": 4, "linked": 4, "legs": 4,
                          "refused": 0, "ignored": 8, "detail": []}
        rail_finish = {"closed": 0, "legs": 0, "refused": 0,
                       "far": 0, "cross_layer": 0}
        precision = {"pairs_ok": True, "locked_nets": ["P", "N"],
                     "n_locked_segments": 12,
                     "pairs": {"routed": [{"name": "USB"}], "refused": []}}
        events = []

        def precision_side_effect(*_args, **_kwargs):
            events.append("precision")
            return precision

        def signal_side_effect(*_args, **_kwargs):
            events.append("local-signal")
            return signal

        def pickup_side_effect(*_args, **_kwargs):
            events.append("pickup")
            return pickup

        def footprint_side_effect(*_args, **_kwargs):
            events.append("local-footprint")
            return same_footprint

        with mock.patch.object(pcbnew, "LoadBoard", return_value=board), \
                mock.patch.object(pcbnew, "ZONE_FILLER", return_value=filler), \
                mock.patch.object(cec_precision_route, "precision_route_board",
                                  side_effect=precision_side_effect) as precision_route, \
                mock.patch.object(cec_fr, "synthesize_power_pickups",
                                  side_effect=pickup_side_effect) as synth, \
                mock.patch.object(cec_fr, "synthesize_same_footprint_links",
                                  side_effect=footprint_side_effect) as local_fp, \
                mock.patch.object(cec_fr, "synthesize_local_power_bypass_links",
                                  return_value=bypass) as local_bypass, \
                mock.patch.object(cec_fr, "synthesize_local_signal_links",
                                  side_effect=signal_side_effect) as local_signal, \
                mock.patch.object(cec_fr, "synthesize_lastmile",
                                  return_value=rail_finish) as finish_rail, \
                mock.patch.object(cec_fr, "_project_netclass_resolver",
                                  return_value="resolver") as resolver, \
                mock.patch.object(cec_fr, "normalize_netclass_geometry",
                                  return_value={"tracks": 2, "vias": 0}) as normalize, \
                mock.patch.object(cec_fr, "prune_redundant_dangling_pickups",
                                  return_value={"vias": 0, "stubs": 0,
                                                "detail": []}) as prune:
            result = H._fill_worker("fixture.kicad_pcb", ("/PWR",))

        synth.assert_called_once_with(
            board, (), plane_nets=("GND",), filled_zone_nets=("/PWR",),
            lock=True)
        precision_route.assert_called_once_with(
            board, board_path="fixture.kicad_pcb", do_kelvin=False,
            pair_grid=True, verbose=False)
        resolver.assert_called_once_with("fixture.kicad_pcb")
        self.assertEqual(local_fp.call_count, 2)
        local_fp.assert_has_calls([
            mock.call(board, lock=True, netclass_resolver="resolver"),
            mock.call(board, lock=True, netclass_resolver="resolver"),
        ])
        local_bypass.assert_called_once_with(
            board, lock=True, netclass_resolver="resolver")
        local_signal.assert_called_once_with(
            board, lock=True, netclass_resolver="resolver")
        self.assertEqual(events, ["precision", "local-footprint",
                                  "local-signal", "pickup",
                                  "local-footprint"])
        finish_rail.assert_called_once_with(
            board, max_mm=8.0, cap=80, netclass_resolver="resolver",
            include_nets=("/PWR", "GND"), lock=True)
        self.assertEqual(normalize.call_count, 3)
        normalize.assert_has_calls([
            mock.call(board, "fixture.kicad_pcb", preserve_nets=("N", "P")),
            mock.call(board, "fixture.kicad_pcb", preserve_nets=("N", "P")),
            mock.call(board, "fixture.kicad_pcb", preserve_nets=("N", "P")),
        ])
        prune.assert_called_once_with(
            board, set(), discover_nets=("/PWR",),
            discover_pofv_nets=("/PWR",))
        self.assertEqual(filler.Fill.call_count, 4)
        self.assertEqual(result["areas"], 7)
        self.assertEqual(result["power_pickups"], pickup)
        self.assertEqual(result["precision"], precision)
        self.assertEqual(result["same_footprint_links"], same_footprint)
        self.assertEqual(result["post_pickup_same_footprint_links"],
                         same_footprint)
        self.assertEqual(result["local_power_bypass"], bypass)
        self.assertEqual(result["local_signal_links"], signal)
        self.assertEqual(result["local_rail_finish"], rail_finish)

    def test_early_connector_power_includes_unpoured_power_banks(self):
        import cec_fr
        import pcbnew

        class Pad:
            def __init__(self, net):
                self.net = net

            def GetNetCode(self):
                return 1

            def GetNetname(self):
                return self.net

            def GetAttribute(self):
                return pcbnew.PAD_ATTRIB_SMD

        class Fpid:
            def GetLibItemName(self):
                return "USB_C_Receptacle"

        class Footprint:
            def IsDNP(self):
                return False

            def GetReference(self):
                return "J_USB"

            def GetFPID(self):
                return Fpid()

            def Pads(self):
                return [Pad("/USB_VBUS"), Pad("/USB_VBUS"),
                        Pad("/POURED_RAIL"), Pad("/POURED_RAIL")]

        class Board:
            def __init__(self):
                self.saved = None

            def GetFootprints(self):
                return [Footprint()]

            def Save(self, path):
                self.saved = path

        board = Board()
        report = {"groups": 1, "linked": 1, "legs": 1, "vias": 0,
                  "refused": 0, "ignored": 0, "pair_groups": 0,
                  "pair_linked": 0, "pair_legs": 0,
                  "pair_refused": 0, "detail": []}
        resolver = lambda _net: {"track_width": 1.0}
        with mock.patch.object(pcbnew, "LoadBoard", return_value=board), \
                mock.patch.object(cec_fr, "_project_netclass_resolver",
                                  return_value=resolver), \
                mock.patch.object(cec_fr, "synthesize_same_footprint_links",
                                  return_value=report) as synth:
            result = H._preroute_connector_power_worker(
                "fixture.kicad_pcb", ("/POURED_RAIL",))

        synth.assert_called_once_with(
            board, lock=True, netclass_resolver=resolver,
            include_refs={"J_USB"},
            include_nets={"/POURED_RAIL", "/USB_VBUS"})
        self.assertEqual(result["selected_nets"],
                         ["/POURED_RAIL", "/USB_VBUS"])
        self.assertEqual(board.saved, "fixture.kicad_pcb")

    def test_bootstrap_rail_pickups_are_locked_before_old_zones_are_removed(self):
        import cec_fr
        import pcbnew

        class Box:
            def GetX(self):
                return 1_000_000

            def GetY(self):
                return 2_000_000

            def GetWidth(self):
                return 3_000_000

            def GetHeight(self):
                return 4_000_000

        class Zone:
            def GetZoneName(self):
                return "overunder:/PWR"

            def GetNetname(self):
                return "/PWR"

            def GetBoundingBox(self):
                return Box()

        class Board:
            def __init__(self):
                self.zone = Zone()
                self.removed = []

            def Zones(self):
                return [self.zone]

            def Remove(self, item):
                self.removed.append(item)

        board = Board()
        pickup_report = {"vias": 1}
        with mock.patch.object(pcbnew, "LoadBoard", return_value=board), \
                mock.patch.object(pcbnew, "SaveBoard"), \
                mock.patch.object(cec_fr, "synthesize_power_pickups",
                                  return_value=pickup_report) as synth:
            result = H._prepare_repour_worker("fixture.kicad_pcb", ("/PWR",))

        args, kwargs = synth.call_args
        self.assertIs(args[0], board)
        self.assertEqual(args[1], ({"net": "/PWR", "layers": ("In3.Cu",)},))
        self.assertEqual(kwargs["plane_nets"], ("/PWR",))
        self.assertTrue(kwargs["lock"])
        self.assertEqual(board.removed, [board.zone])
        self.assertEqual(result["zones_removed"], 1)
        self.assertEqual(result["pickup"], pickup_report)

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
            # Electrical macros must remain craft-placeable; only mechanical
            # and user-access datums belong in the hard-anchor table.
            self.assertNotIn("C1", params["anchor_pins"])
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

    def test_pre_route_gate_refuses_contact_and_open_copper_faults(self):
        types = {"clearance": 2, "via_dangling": 31,
                 "isolated_copper": 7, "copper_edge_clearance": 2}
        loci = [{"type": kind, "where": kind} for kind in types]
        with mock.patch.object(H.cec_score, "drc_types",
                               return_value=(types, loci)), \
                mock.patch.object(H.cec_constraints,
                                  "laid_pour_incursion_summary",
                                  return_value={"n_parts": 0, "n_tracks": 0,
                                                "n_vias": 0, "items": []}):
            result = H._pre_route_materialization_gate("fixture.kicad_pcb")
        self.assertFalse(result["ok"])
        self.assertEqual(result["fatal"], {
            "clearance": 2, "via_dangling": 31, "isolated_copper": 7})
        self.assertEqual(result["loci"],
                         [{"type": kind, "where": kind}
                          for kind in ("clearance", "via_dangling",
                                       "isolated_copper")])

    def test_pre_route_gate_refuses_dangling_and_isolated_generated_copper(self):
        types = {"via_dangling": 31, "track_dangling": 2,
                 "isolated_copper": 7,
                 "copper_edge_clearance": 2}
        with mock.patch.object(H.cec_score, "drc_types",
                               return_value=(types, [])), \
                mock.patch.object(H.cec_constraints,
                                  "laid_pour_incursion_summary",
                                  return_value={"n_parts": 0, "n_tracks": 0,
                                                "n_vias": 0, "items": []}):
            result = H._pre_route_materialization_gate("fixture.kicad_pcb")
        self.assertFalse(result["ok"])
        self.assertEqual(result["fatal"], {
            "via_dangling": 31, "track_dangling": 2,
            "isolated_copper": 7})

    def test_pre_route_gate_refuses_foreign_copper_inside_pour_outline(self):
        incursion = {"n_parts": 2, "n_tracks": 1, "n_vias": 0,
                     "items": [{"kind": "pad", "ref": "U1", "net": "SIG",
                                "pour": "overunder:PWR"}]}
        with mock.patch.object(H.cec_score, "drc_types",
                               return_value=({}, [])), \
                mock.patch.object(H.cec_constraints,
                                  "laid_pour_incursion_summary",
                                  return_value=incursion):
            result = H._pre_route_materialization_gate("fixture.kicad_pcb")
        self.assertFalse(result["ok"])
        self.assertEqual(result["fatal"], {"laid_pour_incursion": 3})
        self.assertIn("U1", result["loci"][0]["where"])

    def test_pre_route_gate_defers_blocked_local_bypass_escape_to_router(self):
        finish = {"local_power_bypass": {"detail": [
            {"cap": "C10", "net": "/USB_VBUS", "status": "refused",
             "reason": "no guarded path"},
            {"cap": "C1", "net": "/HOLD", "status": "refused",
             "reason": "no local IC/LED pad"},
        ]}}
        with mock.patch.object(H.cec_score, "drc_types",
                               return_value=({}, [])), \
                mock.patch.object(H.cec_constraints,
                                  "laid_pour_incursion_summary",
                                  return_value={"n_parts": 0, "n_tracks": 0,
                                                "n_vias": 0, "items": []}):
            result = H._pre_route_materialization_gate(
                "fixture.kicad_pcb", finish)
        self.assertTrue(result["ok"])
        self.assertEqual(result["fatal"], {})
        self.assertEqual(result["types"], {
            "local_power_bypass_deferred": 1})
        self.assertIn("C10", result["loci"][0]["where"])

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
            self.assertEqual(H._hub_route_parallelism(32, 23 * gib), 6)
            self.assertEqual(H._hub_route_parallelism(8, 8 * gib), 1)
            self.assertEqual(H._hub_route_parallelism(2, 3 * gib), 1)

    def test_route_parallelism_override_cannot_exceed_safe_ceiling(self):
        gib = 1024**3
        with mock.patch.dict(os.environ, {"CEC_HUB_ROUTE_WORKERS": "12"}):
            self.assertEqual(H._hub_route_parallelism(32, 23 * gib), 6)
        with mock.patch.dict(os.environ, {"CEC_HUB_ROUTE_WORKERS": "99"}):
            self.assertEqual(H._hub_route_parallelism(32, 23 * gib), 6)

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

    def test_materialization_rejection_has_ranked_fallbacks(self):
        placed = ["first", "second", "third", "fourth"]
        self.assertEqual(H._placement_probe_pool(placed, 1),
                         ["first", "second", "third"])
        self.assertEqual(H._placement_probe_pool(placed, 3), placed)
        self.assertEqual(H._placement_probe_pool([], 1), [])

    def test_materialization_fallbacks_preserve_outline_diversity(self):
        small_a = (object(), 86.1, 74.1, object())
        small_b = (object(), 86.1, 74.1, object())
        medium = (object(), 89.1, 77.1, object())
        large = (object(), 92.1, 80.1, object())
        placed = [small_a, small_b, medium, large]

        self.assertEqual(H._placement_probe_pool(
            placed, 1, fallbacks=2), [small_a, small_b, medium])

    def test_materialization_fallbacks_deduplicate_identical_geometry(self):
        def candidate(x):
            return SimpleNamespace(P={"U1": (x, 2.0, 0.0)})

        small_a = (candidate(1.0), 86.1, 74.1, object())
        small_alias = (candidate(1.0), 86.1, 74.1, object())
        small_b = (candidate(3.0), 86.1, 74.1, object())
        medium = (candidate(4.0), 89.1, 77.1, object())
        large = (candidate(5.0), 92.1, 80.1, object())

        self.assertEqual(H._placement_probe_pool(
            [small_a, small_alias, small_b, medium, large],
            1, fallbacks=3), [small_a, small_b, medium, large])

    def test_board_spec_carries_worker_timeout(self):
        import tempfile
        import cec_router

        board = os.path.join(ROOT, H.REF)
        with tempfile.TemporaryDirectory() as out:
            spec, _ = cec_router.board_spec(
                board, out, seeds=(0,), fr_timeout=17,
                precision=True, precision_pair_grid=True)
        self.assertEqual(spec.regions[0].fr_params["timeout"], 17)
        self.assertTrue(spec.precision)
        self.assertTrue(spec.precision_pair_grid)
        self.assertTrue(any(
            str(hint.get("name", "")).startswith("assembly_fiducial_")
            for hint in spec.regions[0].hints
        ), "production board_spec must carry assembly fiducial keepouts")

    def test_precision_base_is_protected_in_every_route_worker(self):
        import shutil
        import tempfile
        import cec_precision_route
        import cec_router

        board = os.path.join(ROOT, H.REF)

        def fake_precision(src, dst, **kwargs):
            shutil.copy2(src, dst)
            for ext in (".kicad_pro", ".kicad_dru"):
                side = src[:-len(".kicad_pcb")] + ext
                if os.path.exists(side):
                    shutil.copy2(side, dst[:-len(".kicad_pcb")] + ext)
            self.assertTrue(kwargs["pair_grid"])
            return {"locked_nets": ["/USB_D_P", "/USB_D_N"],
                    "n_locked_segments": 8,
                    "pairs": {"routed": [{"name": "USB"}], "refused": []}}

        with tempfile.TemporaryDirectory() as out, \
                mock.patch.dict(os.environ, {"CEC_SKIP_INTAKE": "1"}), \
                mock.patch.object(cec_precision_route, "precision_route",
                                  side_effect=fake_precision), \
                mock.patch.object(cec_router.cec_fr, "generate_batch",
                                  return_value=[]) as generate:
            spec, _ = cec_router.board_spec(
                board, out, seeds=(0,), max_iters=1, fr_timeout=5,
                precision=True, precision_pair_grid=True)
            final, _log = cec_router.route(
                board, spec, verbose=False, work_dir=os.path.join(out, "work"))

        self.assertIsNone(final)
        kwargs = generate.call_args.kwargs
        self.assertEqual(set(kwargs["protect_nets"]),
                         {"/USB_D_P", "/USB_D_N"})
        self.assertTrue(kwargs["skip_locked_taps"])

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

    def test_route_intake_binds_canonical_schematic_for_generated_board(self):
        import tempfile

        board = os.path.join(ROOT, H.REF)
        schematic = os.path.join(ROOT, H.REF_SCH)
        refused = {"ok": False, "reasons": ["synthetic stop"]}
        with tempfile.TemporaryDirectory() as out, \
                mock.patch.dict(os.environ, {"CEC_SKIP_INTAKE": ""}), \
                mock.patch.object(cec_constraints, "intake_gate",
                                  return_value=refused) as intake:
            spec, _ = cec_router.board_spec(
                board, out, seeds=(0,), max_iters=1,
                source_schematic=schematic)
            with self.assertRaisesRegex(RuntimeError, "synthetic stop"):
                cec_router.route(board, spec, verbose=False,
                                 work_dir=os.path.join(out, "work"))
        self.assertEqual(intake.call_args.args[0], board)
        self.assertEqual(intake.call_args.args[1], {"sch": schematic})


if __name__ == "__main__":
    unittest.main()
