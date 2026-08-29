#!/usr/bin/env python3
"""Regression teeth for profile-aware SI and the aggregate release gate."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

try:
    import pcbnew
except ImportError as exc:  # pragma: no cover
    raise unittest.SkipTest("KiCad pcbnew required") from exc

import cec_constraints as C  # noqa: E402
import cec_full_pipeline as FP  # noqa: E402
import cec_fab_check as DFM  # noqa: E402
import cec_fr  # noqa: E402
import cec_impedance as SI  # noqa: E402
import cec_pcb  # noqa: E402
import cec_router  # noqa: E402
import cec_score  # noqa: E402
import cec_synth_pipeline as CSP  # noqa: E402


class RequirementPrecedenceTest(unittest.TestCase):
    def test_headless_defaults_do_not_erase_board_contract(self):
        cfg = SimpleNamespace(params={
            "mount_holes": "4_corner",
            "respect_antenna_keepout": True,
        })
        CSP.elicit_requirements(cfg)
        self.assertEqual(cfg.params["mount_holes"], "4_corner")
        self.assertTrue(cfg.params["respect_antenna_keepout"])

        CSP.elicit_requirements(cfg, {"mount_holes": "2_diag"})
        self.assertEqual(cfg.params["mount_holes"], "2_diag")

    def test_pcie2_service_buttons_declare_late_corner_target(self):
        cfg = CSP.Config.load("pcie-8pin-2port")
        self.assertEqual(cfg.params["button_pair_corner"], "top_left")
        self.assertEqual(tuple(cfg.params["button_pair_target_mm"]),
                         (9.0, 14.0))


class AtomicRenderPublicationTest(unittest.TestCase):
    def test_render_is_published_only_from_completed_temporary_png(self):
        with tempfile.TemporaryDirectory() as td:
            board = os.path.join(td, "candidate.kicad_pcb")
            png = os.path.join(td, "candidate-top.png")
            Path(board).write_text("board", encoding="utf-8")
            rendered_to = []

            def fake_run(command, **_kwargs):
                out = command[command.index("-o") + 1]
                rendered_to.append(out)
                self.assertNotEqual(os.path.abspath(out), os.path.abspath(png))
                Path(out).write_bytes(b"complete-png")
                self.assertFalse(os.path.exists(png))
                return SimpleNamespace(returncode=0)

            with mock.patch.object(CSP._tc, "kicad_cli",
                                   return_value="kicad-cli"), \
                    mock.patch.object(CSP.subprocess, "run",
                                      side_effect=fake_run):
                self.assertTrue(CSP._render_pcb_atomic(board, png))

            self.assertEqual(Path(png).read_bytes(), b"complete-png")
            self.assertEqual(len(rendered_to), 1)
            self.assertFalse(os.path.exists(rendered_to[0]))


class FrozenPlacementContractTest(unittest.TestCase):
    def test_complete_state_detects_post_freeze_component_move(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "board.kicad_pcb")
            state_path = os.path.join(directory,
                                      "board.pourfirst-state.json")
            board = pcbnew.CreateEmptyBoard()
            footprint = pcbnew.FOOTPRINT(board)
            footprint.SetReference("F1")
            footprint.SetPosition(pcbnew.VECTOR2I_MM(10.0, 12.0))
            footprint.SetOrientationDegrees(90.0)
            board.Add(footprint)
            pcbnew.SaveBoard(path, board)
            with open(state_path, "w", encoding="utf-8") as handle:
                json.dump({"placement_scope": "complete",
                           "placements": {"F1": [10.0, 12.0, 90.0]}},
                          handle)

            self.assertTrue(FP._frozen_placement_contract(path)["ok"])
            board = pcbnew.LoadBoard(path)
            board.FindFootprintByReference("F1").SetPosition(
                pcbnew.VECTOR2I_MM(10.0, 13.0))
            pcbnew.SaveBoard(path, board)
            report = FP._frozen_placement_contract(path)
            self.assertTrue(report["applicable"])
            self.assertFalse(report["ok"])
            self.assertEqual(report["mismatches"][0]["ref"], "F1")

    def test_power_independent_postfreeze_move_updates_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "board.kicad_pcb")
            state_path = os.path.join(directory,
                                      "board.pourfirst-state.json")
            board = pcbnew.CreateEmptyBoard()
            signal = pcbnew.NETINFO_ITEM(board, "SIGNAL")
            board.Add(signal)
            footprint = pcbnew.FOOTPRINT(board)
            footprint.SetReference("F1")
            footprint.SetPosition(pcbnew.VECTOR2I_MM(11.0, 12.0))
            pad = pcbnew.PAD(footprint)
            pad.SetPadName("1")
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetSize(pcbnew.VECTOR2I_MM(1.0, 1.0))
            pad.SetPosition(footprint.GetPosition())
            pad.SetLayerSet(pcbnew.PAD.SMDMask())
            pad.SetNet(signal)
            footprint.Add(pad)
            board.Add(footprint)
            pcbnew.SaveBoard(path, board)
            with open(state_path, "w", encoding="utf-8") as handle:
                json.dump({"placement_scope": "complete",
                           "frozen_nets": ["POWER"],
                           "pours": [], "vias": [],
                           "placements": {"F1": [10.0, 12.0, 0.0]}},
                          handle)

            report = FP._sync_safe_postfreeze_placement_delta(path)
            self.assertTrue(report["ok"], report)
            self.assertTrue(report["updated"])
            self.assertEqual(report["refs"], ["F1"])
            state = json.loads(Path(state_path).read_text(encoding="utf-8"))
            self.assertEqual(state["placements"]["F1"], [11.0, 12.0, 0.0])


class ServiceControlReservationTest(unittest.TestCase):
    def test_reservation_uses_solved_courtyard_with_margin(self):
        candidate = SimpleNamespace(P={"SW1": (10.0, 12.0, 90.0)})
        nl = SimpleNamespace(comps={
            "SW1": SimpleNamespace(footprint="Button:SW_Test")})
        with mock.patch.object(
                cec_pcb, "courtyard_bbox",
                return_value=(8.5, 11.5, 9.0, 15.0)):
            rows = CSP._service_control_reservations(
                candidate, nl, ("SW1",), margin=0.4)

        self.assertEqual(rows, [{
            "ref": "SW1", "x0": 8.1, "x1": 11.9,
            "y0": 8.6, "y1": 15.4,
        }])


class RigidOwnerCellEvacuationTest(unittest.TestCase):
    def test_owner_and_followers_translate_together_out_of_reservation(self):
        comps = {ref: object() for ref in ("U1", "C1", "R1", "X1")}
        placement = {
            "U1": (10.0, 10.0, 0.0),
            "C1": (12.0, 10.0, 90.0),
            "R1": (10.0, 12.0, 180.0),
            "X1": (18.0, 10.0, 0.0),
        }
        before = dict(placement)
        reserved = [("service-control:SW1", 7.0, 13.5, 7.0, 13.5)]

        with mock.patch.object(
                CSP, "_courtyard_info",
                return_value=(0.0, 0.0, 0.5, 0.5)):
            moved, refused = CSP._rigid_evacuate_owned_cells(
                placement, comps, reserved, set(),
                {"U1": {"U1", "C1", "R1"}}, 30.0, 20.0,
                clr=0.2, edge_clear=0.5, grid=0.5)

        self.assertFalse(refused)
        self.assertEqual(set(moved["U1"]), {"U1", "C1", "R1"})
        delta = (placement["U1"][0] - before["U1"][0],
                 placement["U1"][1] - before["U1"][1])
        self.assertNotEqual(delta, (0.0, 0.0))
        for ref in ("C1", "R1"):
            self.assertEqual(
                (placement[ref][0] - before[ref][0],
                 placement[ref][1] - before[ref][1]), delta)
            self.assertEqual(placement[ref][2], before[ref][2])
        for ref in ("U1", "C1", "R1"):
            x, y = placement[ref][:2]
            self.assertFalse(7.0 - 0.2 < x + 0.5 and 13.5 + 0.2 > x - 0.5
                             and 7.0 - 0.2 < y + 0.5
                             and 13.5 + 0.2 > y - 0.5)

    def test_service_seed_uses_only_topology_proven_signal_followers(self):
        candidate = SimpleNamespace(P={
            "U1": (10.0, 10.0, 0.0),
            "R1": (11.0, 10.0, 90.0),
            "C1": (12.0, 10.0, 0.0),
        })
        nl = SimpleNamespace()
        reservations = [{"x0": 9.0, "x1": 11.5,
                         "y0": 9.0, "y1": 11.0}]
        spec = {"R1": ("U1", "5"), "C1": ("U1", "8")}
        with mock.patch.object(CSP, "_fp_of",
                               return_value={r: object() for r in candidate.P}), \
                mock.patch.object(CSP, "derive_passive_spec",
                                  return_value=(spec, {})), \
                mock.patch.object(CSP, "_local_signal_followers",
                                  return_value=[
                                      ("R1", "U1", "5", "SIG", 2)]), \
                mock.patch.object(cec_pcb, "courtyard_bbox",
                                  return_value=(9.5, 10.5, 9.5, 10.5)):
            seeds = CSP._service_displaced_owner_cell_seeds(
                candidate, nl, ("R1", "C1"), ("U1",), (), reservations)

        self.assertEqual(set(seeds["U1"]), {"U1", "R1"})
        self.assertNotIn("C1", seeds["U1"])


class McuAntennaEdgeSeatTest(unittest.TestCase):
    def test_declared_left_edge_rotates_antenna_outward(self):
        with mock.patch.object(
                CSP, "_courtyard_info",
                return_value=(0.0, 0.0, 4.0, 6.0)):
            placed, rotation = CSP._seat_mcu_macro(
                {"U1": (0.0, 0.0, 0.0)}, {"U1": "fp"},
                40.0, 20.0, antenna_ref="U1",
                antenna_overhang=5.0, antenna_edge="left", grid=1.0)

        self.assertIsNotNone(placed)
        self.assertEqual(rotation, 90.0)
        self.assertEqual(placed["U1"][2], 90.0)
        # The antenna courtyard may use the declared overhang, while its
        # opposite/body side remains inside the board.
        self.assertGreaterEqual(placed["U1"][0] - 4.0, -5.0)
        self.assertLessEqual(placed["U1"][0] + 4.0, 40.0)


class DetectionComparatorSeatTest(unittest.TestCase):
    def test_downstream_comparator_slides_along_current_axis_around_anchor(self):
        refs = {name: object() for name in ("U10", "U11", "J1")}
        anchors = {"U10": (10.0, 10.0, 0.0),
                   "J1": (15.0, 10.0, 0.0)}
        nl = SimpleNamespace(nets={
            "/DETAMP": [("U10", "OUT"), ("U11", "IN")],
        })

        def courtyard_info(comp, _rot, **_kwargs):
            ref = next(name for name, value in refs.items() if value is comp)
            half = (2.0, 3.0) if ref == "J1" else (1.0, 1.0)
            return (0.0, 0.0, half[0], half[1])

        def courtyard_bbox(comp, x, y, _rot):
            _cx, _cy, hw, hh = courtyard_info(comp, 0.0)
            return (x - hw, x + hw, y - hh, y + hh)

        with mock.patch.object(CSP, "_courtyard_info",
                               side_effect=courtyard_info), \
                mock.patch.object(cec_pcb, "courtyard_bbox",
                                  side_effect=courtyard_bbox), \
                mock.patch.object(cec_pcb, "local_pads",
                                  return_value={"IN": (0.0, 0.0)}), \
                mock.patch.object(
                    cec_pcb, "pad_global",
                    side_effect=lambda ref, _pad, positions, _comps:
                    positions[ref][:2]):
            seat = CSP._seat_detection_comparator(
                "U10", "U11", anchors, nl, refs,
                "/SENSE_HI", "/SENSE_LO",
                0.0, 1.0, 1.0, 0.0, 1.0, 30.0, 30.0)

        self.assertIsNotNone(seat)
        # The compact outboard x-seat is retained; only the non-Kelvin
        # comparator slides along the current axis to clear J1.
        self.assertAlmostEqual(seat[0], 12.5)
        self.assertGreater(abs(seat[1] - 10.0), 3.0)
        comparator = (seat[0] - 1.0, seat[0] + 1.0,
                      seat[1] - 1.0, seat[1] + 1.0)
        blocker = (13.0, 17.0, 7.0, 13.0)
        self.assertTrue(comparator[3] + 0.2 <= blocker[2]
                        or blocker[3] + 0.2 <= comparator[2])


class PinAwareOrientationTest(unittest.TestCase):
    def test_multi_pin_hi_lo_follower_detects_forced_crossing_and_flip(self):
        nl = SimpleNamespace(nets={
            "/SENSE1_HI": [("RS1", "1"), ("U1", "10")],
            "/SENSE1_LO": [("RS1", "2"), ("U1", "9")],
            "/OUT": [("U1", "1"), ("J1", "1")],
        })
        comps = {ref: object() for ref in ("RS1", "U1", "J1")}
        placements = {
            "RS1": (10.0, 10.0, 0.0),
            "U1": (5.0, 10.0, 180.0),
            "J1": (2.0, 15.0, 0.0),
        }
        local = {
            "RS1": {"1": (0.0, -3.0), "2": (0.0, 3.0)},
            "U1": {"10": (1.0, -1.0), "9": (1.0, 1.0),
                   "1": (-1.0, 0.0)},
            "J1": {"1": (0.0, 0.0)},
        }
        sizes = {ref: {pad: (0.4, 0.4) for pad in pads}
                 for ref, pads in local.items()}
        with mock.patch.object(
                cec_pcb, "local_pads",
                side_effect=lambda comp: local[next(
                    ref for ref, value in comps.items() if value is comp)]), \
                mock.patch.object(
                    cec_pcb, "local_pad_sizes",
                    side_effect=lambda comp: sizes[next(
                        ref for ref, value in comps.items()
                        if value is comp)]):
            evidence = CSP._critical_terminal_order_evidence(
                nl, comps, placements)

        self.assertFalse(evidence["ok"])
        self.assertEqual(evidence["crossing_count"], 1)
        self.assertEqual(len(evidence["violations"]), 1)
        violation = evidence["violations"][0]
        self.assertEqual((violation["anchor_ref"], violation["ref"]),
                         ("RS1", "U1"))
        self.assertEqual(violation["recommended_rotation_deg"], 0.0)
        self.assertLess(violation["best_direct_length_mm"],
                        violation["direct_length_mm"])

    def test_two_terminal_part_flips_toward_its_real_net_destinations(self):
        nl = SimpleNamespace(nets={
            "/A": [("R1", "1"), ("J1", "1")],
            "/B": [("R1", "2"), ("J2", "1")],
        })
        comps = {ref: object() for ref in ("R1", "J1", "J2")}
        placements = {
            "R1": (50.0, 50.0, 0.0),
            "J1": (60.0, 50.0, 0.0),
            "J2": (40.0, 50.0, 0.0),
        }
        local = {
            "R1": {"1": (-1.0, 0.0), "2": (1.0, 0.0)},
            "J1": {"1": (0.0, 0.0)},
            "J2": {"1": (0.0, 0.0)},
        }
        sizes = {ref: {pad: (0.4, 0.4) for pad in pads}
                 for ref, pads in local.items()}
        with mock.patch.object(cec_pcb, "local_pads",
                               side_effect=lambda comp: local[next(
                                   ref for ref, value in comps.items()
                                   if value is comp)]), \
                mock.patch.object(cec_pcb, "local_pad_sizes",
                                  side_effect=lambda comp: sizes[next(
                                      ref for ref, value in comps.items()
                                      if value is comp)]), \
                mock.patch.object(CSP, "_courtyard_info",
                                  return_value=(0.0, 0.0, 0.5, 0.25)):
            changed = CSP._pin_aware_two_terminal_orientations(
                nl, comps, placements, ["R1"], 100.0, 100.0)

        self.assertEqual(changed["R1"], (0.0, 180.0))
        self.assertEqual(placements["R1"][2], 180.0)

    def test_two_terminal_part_can_rotate_quarter_turn_for_vertical_demand(self):
        nl = SimpleNamespace(nets={
            "/A": [("R1", "1"), ("J1", "1")],
            "/B": [("R1", "2"), ("J2", "1")],
        })
        comps = {ref: object() for ref in ("R1", "J1", "J2")}
        placements = {
            "R1": (50.0, 50.0, 0.0),
            "J1": (50.0, 40.0, 0.0),
            "J2": (50.0, 60.0, 0.0),
        }
        local = {
            "R1": {"1": (-1.0, 0.0), "2": (1.0, 0.0)},
            "J1": {"1": (0.0, 0.0)},
            "J2": {"1": (0.0, 0.0)},
        }
        sizes = {ref: {pad: (0.4, 0.4) for pad in pads}
                 for ref, pads in local.items()}
        courtyard = {
            "R1": (0.0, 0.0, 0.8, 0.3),
            "J1": (0.0, 0.0, 0.2, 0.2),
            "J2": (0.0, 0.0, 0.2, 0.2),
        }
        with mock.patch.object(cec_pcb, "local_pads",
                               side_effect=lambda comp: local[next(
                                   ref for ref, value in comps.items()
                                   if value is comp)]), \
                mock.patch.object(cec_pcb, "local_pad_sizes",
                                  side_effect=lambda comp: sizes[next(
                                      ref for ref, value in comps.items()
                                      if value is comp)]), \
                mock.patch.object(CSP, "_courtyard_info",
                                  side_effect=lambda comp, _rot, **_kw:
                                  courtyard[next(
                                      ref for ref, value in comps.items()
                                      if value is comp)]):
            changed = CSP._pin_aware_two_terminal_orientations(
                nl, comps, placements, ["R1"], 100.0, 100.0)

        # KiCad footprint rotations use Y-down board coordinates: 270 degrees
        # places pad 1 toward the smaller-Y target and pad 2 toward larger Y.
        self.assertEqual(changed["R1"], (0.0, 270.0))
        self.assertEqual(placements["R1"][2], 270.0)

    def test_two_terminal_rotation_cannot_intrude_on_frozen_foreign_copper(self):
        nl = SimpleNamespace(nets={
            "/A": [("R1", "1"), ("J1", "1")],
            "/B": [("R1", "2"), ("J2", "1")],
        })
        comps = {ref: object() for ref in ("R1", "J1", "J2")}
        placements = {
            "R1": (50.0, 50.0, 0.0),
            "J1": (60.0, 50.0, 0.0),
            "J2": (40.0, 50.0, 0.0),
        }
        local = {
            "R1": {"1": (-1.0, 0.0), "2": (1.0, 0.0)},
            "J1": {"1": (0.0, 0.0)},
            "J2": {"1": (0.0, 0.0)},
        }
        sizes = {ref: {pad: (0.4, 0.4) for pad in pads}
                 for ref, pads in local.items()}
        with mock.patch.object(cec_pcb, "local_pads",
                               side_effect=lambda comp: local[next(
                                   ref for ref, value in comps.items()
                                   if value is comp)]), \
                mock.patch.object(cec_pcb, "local_pad_sizes",
                                  side_effect=lambda comp: sizes[next(
                                      ref for ref, value in comps.items()
                                      if value is comp)]), \
                mock.patch.object(CSP, "_courtyard_info",
                                  return_value=(0.0, 0.0, 0.5, 0.25)):
            changed = CSP._pin_aware_two_terminal_orientations(
                nl, comps, placements, ["R1"], 100.0, 100.0,
                avoid_boxes=[{"net": "/B", "x0": 50.7, "x1": 51.3,
                              "y0": 49.7, "y1": 50.3}])

        # The formerly optimal 180-degree flip would put /A on the /B
        # reservation.  Retaining 0 or choosing another legal orthogonal
        # orientation is acceptable; entering the foreign copper is not.
        self.assertNotEqual(placements["R1"][2], 180.0)

    def _flow_through_fixture(self):
        nl = SimpleNamespace(nets={
            "/USB_D_P": [("D1", "1"), ("D1", "6"),
                          ("J1", "P"), ("U1", "P")],
            "/USB_D_N": [("D1", "3"), ("D1", "4"),
                          ("J1", "N"), ("U1", "N")],
        })
        comps = {ref: object() for ref in ("D1", "J1", "U1")}
        placements = {
            "D1": (50.0, 50.0, 90.0),
            "J1": (65.0, 50.0, 0.0),
            "U1": (35.0, 50.0, 0.0),
        }
        local = {
            "D1": {"1": (-1.2, 0.5), "3": (-1.2, -0.5),
                   "4": (1.2, -0.5), "6": (1.2, 0.5)},
            "J1": {"P": (0.0, -0.4), "N": (0.0, 0.4)},
            "U1": {"P": (0.0, -0.4), "N": (0.0, 0.4)},
        }
        return nl, comps, placements, local

    def test_four_land_pair_protector_rotates_onto_endpoint_axis(self):
        nl, comps, placements, local = self._flow_through_fixture()
        with mock.patch.object(
                cec_pcb, "local_pads",
                side_effect=lambda comp: local[next(
                    ref for ref, value in comps.items() if value is comp)]), \
                mock.patch.object(
                    CSP, "_courtyard_info",
                    return_value=(0.0, 0.0, 1.5, 0.8)):
            changed = CSP._flow_through_pair_orientations(
                nl, comps, placements, 100.0, 100.0)
        self.assertIn("D1", changed)
        self.assertIn(placements["D1"][2], (0.0, 180.0))

    def test_flow_protector_aligns_lane_to_longer_harder_leg(self):
        nl, comps, placements, local = self._flow_through_fixture()
        placements.update({
            "D1": (50.0, 50.0, 0.0),
            "J1": (56.0, 50.0, 0.0),
            "U1": (5.0, 50.0, 0.0),
        })
        # The nearby connector retains a vertical pin field while the long IC
        # leg has a horizontal one.  Orient the station for the long leg; a
        # short local turn is materially safer than a board-scale crossover.
        local["U1"] = {"P": (0.4, 0.0), "N": (-0.4, 0.0)}
        with mock.patch.object(
                cec_pcb, "local_pads",
                side_effect=lambda comp: local[next(
                    ref for ref, value in comps.items() if value is comp)]), \
                mock.patch.object(
                    CSP, "_courtyard_info",
                    return_value=(0.0, 0.0, 1.5, 0.8)):
            changed = CSP._flow_through_pair_orientations(
                nl, comps, placements, 100.0, 100.0)

        self.assertIn("D1", changed)
        self.assertIn(placements["D1"][2], (90.0, 270.0))

    def test_policy_owned_flow_through_rotation_is_not_overridden(self):
        nl, comps, placements, local = self._flow_through_fixture()
        with mock.patch.object(
                cec_pcb, "local_pads",
                side_effect=lambda comp: local[next(
                    ref for ref, value in comps.items() if value is comp)]), \
                mock.patch.object(
                    CSP, "_courtyard_info",
                    return_value=(0.0, 0.0, 1.5, 0.8)):
            changed = CSP._flow_through_pair_orientations(
                nl, comps, placements, 100.0, 100.0,
                protected_refs={"D1"})
        self.assertEqual(changed, {})
        self.assertEqual(placements["D1"][2], 90.0)

    def test_flow_through_topology_requires_two_external_endpoints(self):
        nl, _comps, _placements, _local = self._flow_through_fixture()
        rows = CSP._flow_through_pair_topologies(nl)
        self.assertEqual(1, len(rows))
        self.assertEqual("D1", rows[0]["station_ref"])
        self.assertEqual(("J1", "U1"), rows[0]["endpoint_refs"])

        one_endpoint = SimpleNamespace(nets={
            net: [node for node in nodes if node[0] != "U1"]
            for net, nodes in nl.nets.items()
        })
        self.assertEqual([], CSP._flow_through_pair_topologies(one_endpoint))

    def test_reversible_connector_duplicate_lands_still_trigger_adjudication(self):
        nl = SimpleNamespace(nets={
            "/USB_D_P": [("J1", "A6"), ("J1", "B6"),
                          ("D1", "1"), ("D1", "6"), ("U1", "P")],
            "/USB_D_N": [("J1", "A7"), ("J1", "B7"),
                          ("D1", "3"), ("D1", "4"), ("U1", "N")],
        })
        refs = {row["station_ref"]
                for row in CSP._flow_through_pair_topologies(nl)}
        # Connectivity alone is intentionally conservative here: both the
        # reversible endpoint and inline protector qualify. Either is enough
        # to require exact multi-leg route adjudication; the precision router
        # resolves their geometric roles after materialization.
        self.assertEqual({"D1", "J1"}, refs)


class HubHierarchicalNetclassTest(unittest.TestCase):
    HUB = os.path.join(ROOT, "beta", "hub-standard-rev2", "candidate",
                       "hub-standard-rev2-candidate.kicad_pcb")
    PROJECTS = (
        os.path.join(ROOT, "beta", "hub-standard-rev2",
                     "hub-standard-rev2.kicad_pro"),
        os.path.join(ROOT, "beta", "hub-standard-rev2", "candidate",
                     "hub-standard-rev2-candidate.kicad_pro"),
    )

    @unittest.skipUnless(os.path.isfile(HUB), "current Hub candidate required")
    def test_current_hierarchical_rails_and_pairs_resolve_to_physical_classes(self):
        # KiCad sheet paths prefix the leaf net name.  Root-only patterns such
        # as `/PSU_5V_KVM` silently assign the real
        # `/POWER INPUT + SOURCE SELECTION/PSU_5V_KVM` net to Default, which lets a
        # 2.5 A rail route at 0.2 mm.  Exercise the actual current Hub names.
        board = pcbnew.LoadBoard(self.HUB)
        expected = {
            "+5VSB": ("Power", 1.0, 0.8, 0.4),
            "+5V_SYS": ("Power", 1.0, 0.8, 0.4),
            "/USB_VBUS": ("Power", 1.0, 0.8, 0.4),
            "/POWER INPUT + SOURCE SELECTION/PSU_5V_KVM":
                ("Power", 1.0, 0.8, 0.4),
            "/HOLD-UP + 3V3 REGULATOR/+5V_HOLD":
                ("Power", 1.0, 0.8, 0.4),
            "/CAN + FOUR MODULE PORTS + STACK/VCC_P4":
                ("Power", 1.0, 0.8, 0.4),
            "/CAN + FOUR MODULE PORTS + STACK/CAN_H":
                ("CAN", 0.25, 0.6, 0.3),
            "/MCU + USB SERVICE PORT/USB_D_P":
                ("USB", 0.20, 0.6, 0.3),
        }
        for net, want in expected.items():
            item = board.GetNetInfo().GetNetItem(net)
            self.assertIsNotNone(item, net)
            cls = item.GetNetClassSlow()
            got = (cls.GetName(), cls.GetTrackWidth() / 1e6,
                   cls.GetViaDiameter() / 1e6, cls.GetViaDrill() / 1e6)
            self.assertEqual(got, want, net)

    def test_materialization_donor_and_reference_share_wildcard_patterns(self):
        expected = {
            ("Power", "+5VSB"), ("Power", "+5V_SYS"),
            ("Power", "*+5V_HOLD"), ("Power", "*USB_VBUS"),
            ("Power", "*PSU_5V_KVM"), ("Power", "*VCC_P1"),
            ("Power", "*VCC_P2"), ("Power", "*VCC_P3"),
            ("Power", "*VCC_P4"), ("CAN", "*CAN_H"),
            ("CAN", "*CAN_L"), ("USB", "*USB_D_P"),
            ("USB", "*USB_D_N"),
        }
        observed = []
        for path in self.PROJECTS:
            with open(path, encoding="utf-8") as source:
                rows = json.load(source)["net_settings"]["netclass_patterns"]
            patterns = {(row["netclass"], row["pattern"]) for row in rows}
            self.assertEqual(patterns, expected, path)
            observed.append(patterns)
        self.assertEqual(observed[0], observed[1])


class RouteGeometryAdvisoryTest(unittest.TestCase):
    def test_unlocked_off_angle_is_reported_and_locked_authored_is_excluded(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "angles.kicad_pcb")
            board = pcbnew.CreateEmptyBoard()
            net = pcbnew.NETINFO_ITEM(board, "/A")
            board.Add(net)
            for y, locked in ((2.0, False), (5.0, True)):
                track = pcbnew.PCB_TRACK(board)
                track.SetStart(pcbnew.VECTOR2I_MM(1.0, y))
                track.SetEnd(pcbnew.VECTOR2I_MM(4.0, y + 2.0))
                track.SetWidth(pcbnew.FromMM(0.20))
                track.SetLayer(board.GetLayerID("F.Cu"))
                track.SetNet(net)
                track.SetLocked(locked)
                board.Add(track)
            pcbnew.SaveBoard(path, board)
            report = CSP._oracle_route_sanity(path)
            self.assertEqual(report["unlocked_off45_tracks"], 1)
            self.assertEqual(report["unlocked_off45_examples"][0]["net"], "/A")


class AssemblyRepairOwnershipTest(unittest.TestCase):
    def test_fiducial_clearance_becomes_route_keepout_not_part_nudge(self):
        report = {"violations": [{
            "type": "clearance",
            "description": "Clearance violation",
            "items": [
                {"description": "Pad [<no net>] of FID1 on F.Cu",
                 "pos": {"x": 71.05, "y": 4.95}},
                {"description": "Track [/EN] on F.Cu",
                 "pos": {"x": 70.0, "y": 5.0}},
            ],
        }]}

        def fake_run(args, **_kwargs):
            output = args[args.index("-o") + 1]
            with open(output, "w", encoding="utf-8") as destination:
                json.dump(report, destination)
            return mock.Mock(returncode=0)

        with mock.patch.object(cec_router._tc, "kicad_cli",
                               return_value="kicad-cli"), \
                mock.patch("subprocess.run", side_effect=fake_run):
            manager = cec_router.targeted_repair(
                "fixture.kicad_pcb", tier="manager")
            worker = cec_router.targeted_repair(
                "fixture.kicad_pcb", tier="worker")

        self.assertIsNone(manager,
                          "assembly fiducials are not post-route movable parts")
        self.assertEqual(worker["type"], "keepout")
        self.assertEqual(worker["tier"], "worker")


class CopperCrossingAcceptanceTest(unittest.TestCase):
    """Prove that apparent over-under crossings are legal, while a real
    same-layer, different-net crossing can never pass the route gate."""

    @staticmethod
    def _mm(value):
        return pcbnew.FromMM(value)

    def _board(self, directory, *, over_under):
        path = os.path.join(directory, "crossing.kicad_pcb")
        board = pcbnew.CreateEmptyBoard()
        for (x1, y1), (x2, y2) in (
                ((0, 0), (20, 0)), ((20, 0), (20, 20)),
                ((20, 20), (0, 20)), ((0, 20), (0, 0))):
            edge = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_SEGMENT)
            edge.SetStart(pcbnew.VECTOR2I(self._mm(x1), self._mm(y1)))
            edge.SetEnd(pcbnew.VECTOR2I(self._mm(x2), self._mm(y2)))
            edge.SetLayer(board.GetLayerID("Edge.Cuts"))
            edge.SetWidth(self._mm(0.1))
            board.Add(edge)
        net_a = pcbnew.NETINFO_ITEM(board, "A")
        net_b = pcbnew.NETINFO_ITEM(board, "B")
        board.Add(net_a)
        board.Add(net_b)

        def pad(ref, x, y, net):
            footprint = pcbnew.FOOTPRINT(board)
            footprint.SetReference(ref)
            pos = pcbnew.VECTOR2I(self._mm(x), self._mm(y))
            footprint.SetPosition(pos)
            item = pcbnew.PAD(footprint)
            item.SetPadName("1")
            item.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
            item.SetSize(pcbnew.VECTOR2I(self._mm(1.0), self._mm(1.0)))
            item.SetDrillSize(pcbnew.VECTOR2I(self._mm(0.5), self._mm(0.5)))
            item.SetPosition(pos)
            item.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
            item.SetLayerSet(pcbnew.PAD.PTHMask())
            item.SetNet(net)
            footprint.Add(item)
            board.Add(footprint)

        def track(net, start, end, layer):
            item = pcbnew.PCB_TRACK(board)
            item.SetStart(pcbnew.VECTOR2I(self._mm(start[0]), self._mm(start[1])))
            item.SetEnd(pcbnew.VECTOR2I(self._mm(end[0]), self._mm(end[1])))
            item.SetWidth(self._mm(0.25))
            item.SetLayer(board.GetLayerID(layer))
            item.SetNet(net)
            board.Add(item)

        pad("A1", 3, 10, net_a)
        pad("A2", 17, 10, net_a)
        pad("B1", 10, 3, net_b)
        pad("B2", 10, 17, net_b)
        track(net_a, (3, 10), (17, 10), "F.Cu")
        track(net_b, (10, 3), (10, 17), "B.Cu" if over_under else "F.Cu")
        pcbnew.SaveBoard(path, board)
        return path

    def test_same_layer_different_net_crossing_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._board(directory, over_under=False)
            metrics = cec_score.score(
                path, rules=cec_score.Rules(require_unconnected_zero=False))
            self.assertFalse(metrics.gates_pass, metrics.detail)
            self.assertGreater(metrics.drc_types.get("tracks_crossing", 0), 0,
                               metrics.drc_types)

    def test_different_layer_over_under_crossing_is_not_a_drc(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._board(directory, over_under=True)
            metrics = cec_score.score(
                path, rules=cec_score.Rules(require_unconnected_zero=False))
            self.assertTrue(metrics.gates_pass, metrics.detail)
            self.assertEqual(metrics.drc_types.get("tracks_crossing", 0), 0,
                             metrics.drc_types)


class ProfileAwareImpedanceTest(unittest.TestCase):
    def test_current_high_current_profile_replaces_historical_constants(self):
        s = SI.stackup_for_board("beta/12vhpwr-standard/current.kicad_pcb")
        self.assertEqual(s["profile"], "jlcpcb_6l_pofv_high_current")
        self.assertEqual(s["vendor_stackup"], "JLC06162H-3313")
        self.assertAlmostEqual(s["h_mm"], 0.0994, places=4)
        self.assertAlmostEqual(s["er"], 4.10, places=2)
        self.assertAlmostEqual(s["t_mm"], 0.070, places=3)
        self.assertNotEqual(s["h_mm"], SI.LEGACY_STACKUP["h_mm"])

    def test_hub_uses_one_ounce_outer_profile(self):
        s = SI.stackup_for_board("beta/hub-standard-rev2/current.kicad_pcb")
        self.assertEqual(s["profile"], "jlcpcb_6l_pofv_signal")
        self.assertAlmostEqual(s["t_mm"], 0.035, places=3)
        self.assertEqual(s["reference_layer"], "In1.Cu")

    def test_fab_audit_resolves_copper_weight_per_board(self):
        hpwr = DFM.board_outer_copper_oz(
            os.path.join(ROOT, "beta", "12vhpwr-standard",
                         "12vhpwr-standard-module.kicad_pcb"))
        hub = DFM.board_outer_copper_oz(
            os.path.join(ROOT, "beta", "hub-standard-rev2", "candidate",
                         "hub-standard-rev2-candidate.kicad_pcb"))
        self.assertAlmostEqual(hpwr, 2.0, delta=0.05)
        self.assertAlmostEqual(hub, 1.0, delta=0.05)

    def test_no_profile_is_explicitly_labelled_legacy(self):
        s = SI.stackup_for_board("misc/unknown-board.kicad_pcb")
        self.assertIsNone(s["profile"])
        self.assertIn("legacy", s["source"])
        self.assertIn("warning", s)


class AggregateReleaseGateTest(unittest.TestCase):
    def _constraint(self, cid, *, severity="hard", checkable="yes", status="ratified"):
        return C.Constraint(cid, cid, "test", severity, checkable, "none",
                            "rule", "test", status=status)

    def test_post_route_excludes_non_fabricated_planning_authorities(self):
        rows = [
            (self._constraint("sch-pcb-sync"), "FAIL", "no sibling schematic", None),
            (self._constraint("high-current-corridor-keepout"), "FAIL",
             "derived reservation", None),
            (self._constraint("no-foreign-on-high-current-pour"), "FAIL",
             "derived reservation", None),
            (self._constraint("decoupling-cap-owner"), "FAIL", "shared bypass", None),
            (self._constraint("soft-one", severity="soft"), "FAIL", "soft", None),
            (self._constraint("proposed-one", status="proposed"), "FAIL", "draft", None),
        ]
        blocked = C.blocking_rows(rows, phase="post_route")
        self.assertEqual([row[0].id for row in blocked], ["decoupling-cap-owner"])

    def test_checker_error_is_release_blocking(self):
        rows = [(self._constraint("route-check"), "ERROR", "crash", None)]
        self.assertEqual(len(C.blocking_rows(rows)), 1)


class HighSpeedPhysicalGateTest(unittest.TestCase):
    def test_hierarchical_can_names_are_discovered_in_their_own_sheet(self):
        class _Net:
            def __init__(self, name):
                self._name = name

            def GetNetname(self):
                return self._name

        class _Info:
            def NetsByNetcode(self):
                return {
                    1: _Net("/PORTS/CAN_H"),
                    2: _Net("/PORTS/CAN_L"),
                    3: _Net("/SERVICE/CAN_H"),
                    4: _Net("/SERVICE/CAN_L"),
                }

        class _Board:
            def GetNetInfo(self):
                return _Info()

        self.assertEqual(
            C._coupled_pair_names(_Board()),
            [
                ("can", "/PORTS/CAN_H", "/PORTS/CAN_L"),
                ("can", "/SERVICE/CAN_H", "/SERVICE/CAN_L"),
            ])

    def _board(self, directory, *, p_name="/USB_D_P", n_name="/USB_D_N",
               x0=2.0, x1=18.0, p_y=9.835, n_y=10.165):
        netlist = os.path.join(directory, "pair.net")
        path = os.path.join(directory, "pair.kicad_pcb")
        with open(netlist, "w", encoding="utf-8") as handle:
            handle.write('(export (nets (net (code "1") (name "GND"))))\n')
        self.assertTrue(cec_pcb.build_board(
            path, netlist, {}, [(5.0, 5.0)], None, 20.0, 20.0,
            force_argv=False, stackup_profile="jlcpcb_6l_pofv_signal"))
        board = pcbnew.LoadBoard(path)
        pnet = pcbnew.NETINFO_ITEM(board, p_name)
        nnet = pcbnew.NETINFO_ITEM(board, n_name)
        board.Add(pnet)
        board.Add(nnet)
        for net, y in ((pnet, p_y), (nnet, n_y)):
            track = pcbnew.PCB_TRACK(board)
            track.SetStart(pcbnew.VECTOR2I_MM(x0, y))
            track.SetEnd(pcbnew.VECTOR2I_MM(x1, y))
            track.SetWidth(pcbnew.FromMM(0.20))
            track.SetLayer(board.GetLayerID("F.Cu"))
            track.SetNet(net)
            board.Add(track)
        pcbnew.SaveBoard(path, board)
        board = pcbnew.LoadBoard(path)
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        pcbnew.SaveBoard(path, board)
        return path

    def test_clean_surface_pair_has_continuous_ground_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._board(directory)
            report = C.high_speed_pair_summary(path)
            self.assertTrue(report["applicable"])
            self.assertTrue(report["ok"], report)
            self.assertGreaterEqual(report["pairs"][0]["reference_coverage_pct"], 95.0)
            self.assertGreaterEqual(report["pairs"][0]["coupled_coverage_pct"], 80.0)

    def test_asymmetric_signal_via_and_missing_return_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._board(directory)
            board = pcbnew.LoadBoard(path)
            via = pcbnew.PCB_VIA(board)
            via.SetViaType(pcbnew.VIATYPE_THROUGH)
            via.SetPosition(pcbnew.VECTOR2I_MM(10.0, 9.835))
            # Keep the synthetic via clear of the partner trace; a larger land
            # would physically short the 0.33mm-spaced fixture and KiCad would
            # correctly merge the connected copper onto one net on reload.
            via.SetWidth(pcbnew.FromMM(0.30))
            via.SetDrill(pcbnew.FromMM(0.20))
            via.SetLayerPair(board.GetLayerID("F.Cu"), board.GetLayerID("B.Cu"))
            via.SetNet(board.FindNet("/USB_D_P"))
            board.Add(via)
            pcbnew.SaveBoard(path, board)
            report = C.high_speed_pair_summary(path)
            self.assertFalse(report["ok"])
            joined = " ".join(report["violations"])
            self.assertIn("asymmetric via count", joined)
            self.assertIn("lack a GND return via", joined)

    def test_qualified_endpoint_pofv_is_not_a_serial_route_transition(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._board(directory)
            board = pcbnew.LoadBoard(path)
            net = board.FindNet("/USB_D_P")
            centre = pcbnew.VECTOR2I_MM(3.0, 9.835)
            fp = pcbnew.FOOTPRINT(board)
            fp.SetReference("JPAIR")
            fp.SetPosition(centre)
            pad = pcbnew.PAD(fp)
            pad.SetPadName("A6")
            pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetSize(pcbnew.VECTOR2I_MM(0.55, 0.55))
            pad.SetPosition(centre)
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            pad.SetLayerSet(pcbnew.PAD.SMDMask())
            pad.SetNet(net)
            fp.Add(pad)
            board.Add(fp)
            endpoint = pcbnew.PCB_VIA(board)
            endpoint.SetPosition(centre)
            endpoint.SetWidth(pcbnew.FromMM(0.30))
            endpoint.SetDrill(pcbnew.FromMM(0.20))
            endpoint.SetLayerPair(board.GetLayerID("F.Cu"),
                                  board.GetLayerID("B.Cu"))
            endpoint.SetNet(net)
            board.Add(endpoint)
            serial = pcbnew.PCB_VIA(board)
            serial.SetPosition(pcbnew.VECTOR2I_MM(10.0, 9.835))
            serial.SetWidth(pcbnew.FromMM(0.60))
            serial.SetDrill(pcbnew.FromMM(0.30))
            serial.SetLayerPair(board.GetLayerID("F.Cu"),
                                board.GetLayerID("B.Cu"))
            serial.SetNet(net)
            board.Add(serial)

            endpoint_vias, route_vias = C._partition_pair_vias(
                board, [endpoint, serial])

            self.assertEqual(endpoint_vias, [endpoint])
            self.assertEqual(route_vias, [serial])

    def test_exact_courtyard_polygon_does_not_inherit_bbox_notch_area(self):
        polygon = [
            (0.0, 0.0), (4.0, 0.0), (4.0, 1.0),
            (2.0, 1.0), (2.0, 3.0), (0.0, 3.0),
        ]
        box = (1.5, 3.5, 0.5, 2.5)
        # Bounding-box overlap is 4 mm^2; the actual L-shaped courtyard owns
        # only 1.75 mm^2 of the exact rectangle.
        self.assertAlmostEqual(
            C._polygon_box_overlap_area(polygon, box), 1.75, places=6)

    def test_short_can_endpoint_cell_uses_bounded_uncoupled_length(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._board(
                directory, p_name="/CAN_H", n_name="/CAN_L",
                x0=8.0, x1=9.75, p_y=8.0, n_y=12.0)
            report = C.high_speed_pair_summary(path)
            self.assertTrue(report["ok"], report)
            row = report["pairs"][0]
            self.assertEqual(row["coupled_coverage_pct"], 0.0)
            self.assertEqual(row["uncoupled_length_mm"], 1.75)
            self.assertEqual(row["uncoupled_length_budget_mm"], 2.0)

    def test_uncoupled_length_budget_cannot_waive_long_can_route(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._board(
                directory, p_name="/CAN_H", n_name="/CAN_L",
                x0=6.0, x1=10.0, p_y=8.0, n_y=12.0)
            report = C.high_speed_pair_summary(path)
            self.assertFalse(report["ok"])
            self.assertIn(
                "coupled-route coverage",
                " ".join(report["violations"]))

    def test_pair_route_detour_is_bounded_by_endpoint_mst(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._board(directory)
            board = pcbnew.LoadBoard(path)
            for endpoint, x in enumerate((2.0, 18.0), start=1):
                footprint = pcbnew.FOOTPRINT(board)
                footprint.SetReference("JPAIR%d" % endpoint)
                footprint.SetPosition(pcbnew.VECTOR2I_MM(0.0, 0.0))
                for number, net_name, y in (
                        ("1", "/USB_D_P", 9.835),
                        ("2", "/USB_D_N", 10.165)):
                    pad = pcbnew.PAD(footprint)
                    pad.SetPadName(number)
                    pad.SetShape(pcbnew.PAD_SHAPE_RECT)
                    pad.SetSize(pcbnew.VECTOR2I_MM(0.5, 0.5))
                    pad.SetPosition(pcbnew.VECTOR2I_MM(x, y))
                    pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
                    pad.SetLayerSet(pcbnew.PAD.SMDMask())
                    pad.SetNet(board.FindNet(net_name))
                    footprint.Add(pad)
                board.Add(footprint)
            # Add an otherwise well-coupled redundant perimeter-length pair.
            # The physical gate must reject excessive copper length even when
            # skew and coupling alone look excellent.
            for net_name, pad_y, detour_y in (
                    ("/USB_D_P", 9.835, 0.0),
                    ("/USB_D_N", 10.165, 0.33)):
                points = ((2.0, pad_y), (2.0, detour_y),
                          (18.0, detour_y), (18.0, pad_y))
                for start, end in zip(points, points[1:]):
                    track = pcbnew.PCB_TRACK(board)
                    track.SetStart(pcbnew.VECTOR2I_MM(*start))
                    track.SetEnd(pcbnew.VECTOR2I_MM(*end))
                    track.SetWidth(pcbnew.FromMM(0.20))
                    track.SetLayer(board.GetLayerID("F.Cu"))
                    track.SetNet(board.FindNet(net_name))
                    board.Add(track)
            pcbnew.SaveBoard(path, board)

            report = C.high_speed_pair_summary(path)

        self.assertFalse(report["ok"], report)
        row = report["pairs"][0]
        self.assertGreater(row["detour_ratio_p"],
                           row["detour_ratio_limit"])
        self.assertIn("route detour", " ".join(report["violations"]))

    def test_ses_geometry_is_raised_to_assigned_netclass(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._board(directory)
            pro = path[:-len(".kicad_pcb")] + ".kicad_pro"
            with open(pro, "r", encoding="utf-8") as handle:
                project = json.load(handle)
            project["net_settings"] = {
                "classes": [
                    {"name": "Default", "track_width": 0.20,
                     "via_diameter": 0.45, "via_drill": 0.20},
                    {"name": "USB", "track_width": 0.25,
                     "via_diameter": 0.60, "via_drill": 0.30},
                ],
                "netclass_patterns": [{"netclass": "USB", "pattern": "*/USB_D_*"}],
                "netclass_assignments": {},
            }
            with open(pro, "w", encoding="utf-8") as handle:
                json.dump(project, handle)
            board = pcbnew.LoadBoard(path)
            via = pcbnew.PCB_VIA(board)
            via.SetPosition(pcbnew.VECTOR2I_MM(10.0, 8.5))
            via.SetWidth(pcbnew.FromMM(0.40))
            via.SetDrill(pcbnew.FromMM(0.20))
            via.SetLayerPair(board.GetLayerID("F.Cu"), board.GetLayerID("B.Cu"))
            via.SetNet(board.FindNet("/USB_D_P"))
            board.Add(via)
            result = cec_fr.normalize_netclass_geometry(board, path)
            self.assertEqual(result["tracks"], 2)
            self.assertEqual(result["vias"], 1)
            widths = [t.GetWidth() / 1e6 for t in board.GetTracks()
                      if t.GetClass() == "PCB_TRACK"]
            self.assertEqual(widths, [0.25, 0.25])
            self.assertAlmostEqual(via.GetWidth(via.TopLayer()) / 1e6, 0.60)
            self.assertAlmostEqual(via.GetDrillValue() / 1e6, 0.30)

    def test_precision_owned_pair_geometry_is_not_renormalized(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._board(directory)
            pro = path[:-len(".kicad_pcb")] + ".kicad_pro"
            with open(pro, "r", encoding="utf-8") as handle:
                project = json.load(handle)
            project["net_settings"] = {
                "classes": [
                    {"name": "Default", "track_width": 0.20,
                     "via_diameter": 0.45, "via_drill": 0.20},
                    {"name": "USB", "track_width": 0.30,
                     "diff_pair_width": 0.25, "diff_pair_gap": 0.13,
                     "via_diameter": 0.60, "via_drill": 0.30},
                ],
                "netclass_patterns": [
                    {"netclass": "USB", "pattern": "*/USB_D_*"}],
                "netclass_assignments": {},
            }
            with open(pro, "w", encoding="utf-8") as handle:
                json.dump(project, handle)
            board = pcbnew.LoadBoard(path)
            via = pcbnew.PCB_VIA(board)
            via.SetPosition(pcbnew.VECTOR2I_MM(10.0, 9.835))
            via.SetWidth(pcbnew.FromMM(0.30))
            via.SetDrill(pcbnew.FromMM(0.20))
            via.SetLayerPair(board.GetLayerID("F.Cu"),
                             board.GetLayerID("B.Cu"))
            via.SetNet(board.FindNet("/USB_D_P"))
            board.Add(via)

            result = cec_fr.normalize_netclass_geometry(
                board, path, preserve_nets=("/USB_D_P", "/USB_D_N"))

            self.assertEqual(result["tracks"], 0)
            self.assertEqual(result["vias"], 0)
            self.assertEqual(result["preserved_nets"],
                             ["/USB_D_N", "/USB_D_P"])
            widths = [item.GetWidth() / 1e6 for item in board.GetTracks()
                      if item.GetClass() == "PCB_TRACK"]
            self.assertEqual(widths, [0.20, 0.20])
            self.assertAlmostEqual(via.GetWidth(via.TopLayer()) / 1e6, 0.30)
            self.assertAlmostEqual(via.GetDrillValue() / 1e6, 0.20)

    def test_qualified_power_pofv_survives_normalization_and_conformance(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "power-pofv.kicad_pcb")
            pro = path[:-len(".kicad_pcb")] + ".kicad_pro"
            board = pcbnew.CreateEmptyBoard()
            board.SetCopperLayerCount(6)
            props = board.GetProperties()
            props["CEC_FAB_PROFILE"] = "jlcpcb_6l_pofv_signal"
            board.SetProperties(props)
            net = pcbnew.NETINFO_ITEM(board, "PWR")
            board.Add(net)
            footprint = pcbnew.FOOTPRINT(board)
            footprint.SetReference("U1")
            position = pcbnew.VECTOR2I_MM(10.0, 10.0)
            footprint.SetPosition(position)
            pad = pcbnew.PAD(footprint)
            pad.SetPadName("1")
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetSize(pcbnew.VECTOR2I_MM(1.0, 0.4))
            pad.SetPosition(position)
            layers = pcbnew.LSET(); layers.AddLayer(pcbnew.F_Cu)
            pad.SetLayerSet(layers); pad.SetNet(net)
            footprint.Add(pad); board.Add(footprint)
            via = pcbnew.PCB_VIA(board)
            via.SetPosition(position)
            via.SetWidth(pcbnew.FromMM(0.35))
            via.SetDrill(pcbnew.FromMM(0.25))
            via.SetLayerPair(board.GetLayerID("F.Cu"),
                             board.GetLayerID("B.Cu"))
            via.SetNet(net); board.Add(via)
            pcbnew.SaveBoard(path, board)
            with open(pro, "w", encoding="utf-8") as handle:
                json.dump({"net_settings": {
                    "classes": [
                        {"name": "Default", "track_width": 0.20,
                         "via_diameter": 0.60, "via_drill": 0.30},
                        {"name": "Power", "track_width": 1.00,
                         "via_diameter": 0.80, "via_drill": 0.40},
                    ],
                    "netclass_assignments": {"PWR": "Power"},
                    "netclass_patterns": [],
                }}, handle)

            board = pcbnew.LoadBoard(path)
            result = cec_fr.normalize_netclass_geometry(board, path)
            kept = next(item for item in board.GetTracks()
                        if item.GetClass() == "PCB_VIA")
            self.assertEqual(result["vias"], 0)
            self.assertEqual(result["qualified_pofv_vias"], 1)
            self.assertEqual(kept.GetWidth(kept.TopLayer()),
                             pcbnew.FromMM(0.35))
            self.assertEqual(kept.GetDrillValue(), pcbnew.FromMM(0.25))
            pcbnew.SaveBoard(path, board)
            ok, detail = C.CHECKERS["netclass-geometry-conformance"](
                pcbnew.LoadBoard(path), path, {})[:2]
            self.assertTrue(ok, detail)
            self.assertIn("1 profile-qualified POFV", detail)

    def test_power_width_neckdown_is_bounded_at_fine_pitch_smd_pad(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "neckdown.kicad_pcb")
            pro = path[:-len(".kicad_pcb")] + ".kicad_pro"
            board = pcbnew.CreateEmptyBoard()
            net = pcbnew.NETINFO_ITEM(board, "PWR")
            board.Add(net)

            fp = pcbnew.FOOTPRINT(board)
            fp.SetReference("U1")
            fp.SetLayer(pcbnew.F_Cu)
            fp.SetPosition(pcbnew.VECTOR2I_MM(10.0, 10.0))
            pad = pcbnew.PAD(fp)
            pad.SetPadName("1")
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetSize(pcbnew.VECTOR2I_MM(1.0, 0.4))
            pad.SetPosition(pcbnew.VECTOR2I_MM(10.0, 10.0))
            layers = pcbnew.LSET()
            layers.AddLayer(pcbnew.F_Cu)
            pad.SetLayerSet(layers)
            pad.SetNet(net)
            fp.Add(pad)
            board.Add(fp)

            def add_track(x0, x1):
                track = pcbnew.PCB_TRACK(board)
                track.SetStart(pcbnew.VECTOR2I_MM(x0, 10.0))
                track.SetEnd(pcbnew.VECTOR2I_MM(x1, 10.0))
                track.SetWidth(pcbnew.FromMM(0.20))
                track.SetLayer(pcbnew.F_Cu)
                track.SetNet(net)
                board.Add(track)

            add_track(10.0, 13.0)  # starts on the narrow SMD pad
            add_track(20.0, 23.0)  # ordinary rail: no neck-down entitlement
            pcbnew.SaveBoard(path, board)
            with open(pro, "w", encoding="utf-8") as handle:
                json.dump({"net_settings": {
                    "classes": [
                        {"name": "Default", "track_width": 0.20,
                         "via_diameter": 0.60, "via_drill": 0.30},
                        {"name": "Power", "track_width": 1.00,
                         "via_diameter": 0.80, "via_drill": 0.40},
                    ],
                    "netclass_assignments": {"PWR": "Power"},
                    "netclass_patterns": [],
                }}, handle)

            result = cec_fr.normalize_netclass_geometry(board, path)
            local = [t for t in board.GetTracks()
                     if t.GetClass() == "PCB_TRACK"
                     and t.GetStart().x / 1e6 < 14.0]
            remote = [t for t in board.GetTracks()
                      if t.GetClass() == "PCB_TRACK"
                      and t.GetStart().x / 1e6 >= 14.0]

            self.assertEqual(result["neckdown_split_tracks"], 1)
            self.assertEqual(result["neckdown_sections"], 1)
            self.assertEqual(sorted(round(t.GetWidth() / 1e6, 2) for t in local),
                             [0.20, 1.00])
            narrow_mm = sum(t.GetLength() / 1e6 for t in local
                            if round(t.GetWidth() / 1e6, 2) == 0.20)
            self.assertAlmostEqual(narrow_mm, 1.5, places=3)
            self.assertEqual([round(t.GetWidth() / 1e6, 2) for t in remote],
                             [1.00])
            before = [(t.GetStart().x, t.GetEnd().x, t.GetWidth())
                      for t in board.GetTracks()
                      if t.GetClass() == "PCB_TRACK"]
            second = cec_fr.normalize_netclass_geometry(board, path)
            after = [(t.GetStart().x, t.GetEnd().x, t.GetWidth())
                     for t in board.GetTracks()
                     if t.GetClass() == "PCB_TRACK"]
            self.assertEqual(second["neckdown_split_tracks"], 0)
            self.assertEqual(after, before)
            self.assertTrue(second["legal_neckdown_uuids"])
            pcbnew.SaveBoard(path, board)
            ok, detail = C.CHECKERS["netclass-geometry-conformance"](
                pcbnew.LoadBoard(path), path, {})[:2]
            self.assertTrue(ok, detail)

    def test_normalizer_never_shrinks_existing_power_copper(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "wide-escape.kicad_pcb")
            pro = path[:-len(".kicad_pcb")] + ".kicad_pro"
            board = pcbnew.CreateEmptyBoard()
            net = pcbnew.NETINFO_ITEM(board, "PWR")
            board.Add(net)
            fp = pcbnew.FOOTPRINT(board)
            fp.SetReference("U1")
            pad = pcbnew.PAD(fp)
            pad.SetPadName("1")
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetSize(pcbnew.VECTOR2I_MM(1.0, 0.4))
            pad.SetPosition(pcbnew.VECTOR2I_MM(10.0, 10.0))
            layers = pcbnew.LSET(); layers.AddLayer(pcbnew.F_Cu)
            pad.SetLayerSet(layers); pad.SetNet(net); fp.Add(pad); board.Add(fp)
            track = pcbnew.PCB_TRACK(board)
            track.SetStart(pcbnew.VECTOR2I_MM(10.0, 10.0))
            track.SetEnd(pcbnew.VECTOR2I_MM(11.0, 10.0))
            track.SetWidth(pcbnew.FromMM(1.0))
            track.SetLayer(pcbnew.F_Cu); track.SetNet(net); board.Add(track)
            pcbnew.SaveBoard(path, board)
            with open(pro, "w", encoding="utf-8") as handle:
                json.dump({"net_settings": {
                    "classes": [
                        {"name": "Default", "track_width": 0.20},
                        {"name": "Power", "track_width": 1.00},
                    ],
                    "netclass_assignments": {"PWR": "Power"},
                    "netclass_patterns": [],
                }}, handle)

            result = cec_fr.normalize_netclass_geometry(board, path)

            tracks = [item for item in board.GetTracks()
                      if item.GetClass() == "PCB_TRACK"]
            self.assertEqual(len(tracks), 1)
            self.assertEqual(tracks[0].GetWidth(), pcbnew.FromMM(1.0))
            self.assertEqual(result["neckdown_narrowed_sections"], 0)

    def test_locked_local_branch_is_not_widened_after_route_admission(self):
        """Post-SES normalization cannot rewrite an admitted frozen prefix."""
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "locked-local-branch.kicad_pcb")
            pro = path[:-len(".kicad_pcb")] + ".kicad_pro"
            board = pcbnew.CreateEmptyBoard()
            net = pcbnew.NETINFO_ITEM(board, "PWR")
            board.Add(net)

            def add_track(y, locked):
                track = pcbnew.PCB_TRACK(board)
                track.SetStart(pcbnew.VECTOR2I_MM(10.0, y))
                track.SetEnd(pcbnew.VECTOR2I_MM(13.0, y))
                track.SetWidth(pcbnew.FromMM(0.20))
                track.SetLayer(pcbnew.F_Cu)
                track.SetNet(net)
                track.SetLocked(locked)
                board.Add(track)
                return track

            frozen = add_track(10.0, True)
            ordinary = add_track(12.0, False)
            pcbnew.SaveBoard(path, board)
            with open(pro, "w", encoding="utf-8") as handle:
                json.dump({"net_settings": {
                    "classes": [
                        {"name": "Default", "track_width": 0.20},
                        {"name": "Power", "track_width": 1.00},
                    ],
                    "netclass_assignments": {"PWR": "Power"},
                    "netclass_patterns": [],
                }}, handle)

            result = cec_fr.normalize_netclass_geometry(board, path)

            self.assertEqual(frozen.GetWidth(), pcbnew.FromMM(0.20))
            self.assertEqual(ordinary.GetWidth(), pcbnew.FromMM(1.00))
            self.assertEqual(result["preserved_locked_tracks"], 1)
            self.assertEqual(result["tracks"], 1)

    def test_locked_fine_pad_neckdown_is_classified_without_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "locked-neckdown.kicad_pcb")
            pro = path[:-len(".kicad_pcb")] + ".kicad_pro"
            board = pcbnew.CreateEmptyBoard()
            net = pcbnew.NETINFO_ITEM(board, "PWR")
            board.Add(net)
            fp = pcbnew.FOOTPRINT(board); fp.SetReference("U1")
            pad = pcbnew.PAD(fp); pad.SetPadName("1")
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetSize(pcbnew.VECTOR2I_MM(1.0, 0.4))
            pad.SetPosition(pcbnew.VECTOR2I_MM(10.0, 10.0))
            layers = pcbnew.LSET(); layers.AddLayer(pcbnew.F_Cu)
            pad.SetLayerSet(layers); pad.SetNet(net); fp.Add(pad); board.Add(fp)
            track = pcbnew.PCB_TRACK(board)
            track.SetStart(pad.GetPosition())
            track.SetEnd(pcbnew.VECTOR2I_MM(11.0, 10.0))
            track.SetWidth(pcbnew.FromMM(0.20))
            track.SetLayer(pcbnew.F_Cu); track.SetNet(net)
            track.SetLocked(True); board.Add(track)
            track_id = track.m_Uuid.AsString()
            pcbnew.SaveBoard(path, board)
            with open(pro, "w", encoding="utf-8") as handle:
                json.dump({"net_settings": {
                    "classes": [
                        {"name": "Default", "track_width": 0.20},
                        {"name": "Power", "track_width": 1.00},
                    ],
                    "netclass_assignments": {"PWR": "Power"},
                    "netclass_patterns": [],
                }}, handle)

            result = cec_fr.normalize_netclass_geometry(board, path)

            self.assertEqual(track.GetWidth(), pcbnew.FromMM(0.20))
            self.assertEqual(result["tracks"], 0)
            self.assertIn(track_id, result["legal_neckdown_uuids"])

    def test_locked_track_beyond_neckdown_budget_is_not_exempted(self):
        """A UUID-level waiver cannot hide the long remainder of a frozen
        segment merely because one endpoint touches a fine-pitch pad."""
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "locked-long-neckdown.kicad_pcb")
            pro = path[:-len(".kicad_pcb")] + ".kicad_pro"
            board = pcbnew.CreateEmptyBoard()
            net = pcbnew.NETINFO_ITEM(board, "PWR")
            board.Add(net)
            fp = pcbnew.FOOTPRINT(board); fp.SetReference("U1")
            pad = pcbnew.PAD(fp); pad.SetPadName("1")
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetSize(pcbnew.VECTOR2I_MM(1.0, 0.4))
            pad.SetPosition(pcbnew.VECTOR2I_MM(10.0, 10.0))
            layers = pcbnew.LSET(); layers.AddLayer(pcbnew.F_Cu)
            pad.SetLayerSet(layers); pad.SetNet(net); fp.Add(pad); board.Add(fp)
            track = pcbnew.PCB_TRACK(board)
            track.SetStart(pad.GetPosition())
            track.SetEnd(pcbnew.VECTOR2I_MM(13.0, 10.0))
            track.SetWidth(pcbnew.FromMM(0.20))
            track.SetLayer(pcbnew.F_Cu); track.SetNet(net)
            track.SetLocked(True); board.Add(track)
            track_id = track.m_Uuid.AsString()
            pcbnew.SaveBoard(path, board)
            with open(pro, "w", encoding="utf-8") as handle:
                json.dump({"net_settings": {
                    "classes": [
                        {"name": "Default", "track_width": 0.20},
                        {"name": "Power", "track_width": 1.00},
                    ],
                    "netclass_assignments": {"PWR": "Power"},
                    "netclass_patterns": [],
                }}, handle)

            result = cec_fr.normalize_netclass_geometry(board, path)

            self.assertEqual(track.GetWidth(), pcbnew.FromMM(0.20))
            self.assertNotIn(track_id, result["legal_neckdown_uuids"])

    def test_power_width_neckdown_is_bounded_at_constrained_pth_pad(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "pth-neckdown.kicad_pcb")
            pro = path[:-len(".kicad_pcb")] + ".kicad_pro"
            board = pcbnew.CreateEmptyBoard()
            power = pcbnew.NETINFO_ITEM(board, "PWR")
            ground = pcbnew.NETINFO_ITEM(board, "GND")
            board.Add(power)
            board.Add(ground)

            fp = pcbnew.FOOTPRINT(board)
            fp.SetReference("J1")
            fp.SetPosition(pcbnew.VECTOR2I_MM(10.0, 10.0))

            def pth(number, net, x, y):
                pad = pcbnew.PAD(fp)
                pad.SetPadName(number)
                pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
                pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
                pad.SetSize(pcbnew.VECTOR2I_MM(1.524, 1.524))
                pad.SetDrillSize(pcbnew.VECTOR2I_MM(0.90, 0.90))
                pad.SetPosition(pcbnew.VECTOR2I_MM(x, y))
                pad.SetLayerSet(pcbnew.PAD.PTHMask())
                pad.SetNet(net)
                fp.Add(pad)
                return pad

            pth("1", power, 10.0, 10.0)
            pth("2", ground, 12.54, 11.27)  # staggered foreign-net pin
            pth("3", power, 20.0, 10.0)     # unconstrained comparison pin
            board.Add(fp)

            def add_track(start, end):
                track = pcbnew.PCB_TRACK(board)
                track.SetStart(pcbnew.VECTOR2I_MM(*start))
                track.SetEnd(pcbnew.VECTOR2I_MM(*end))
                track.SetWidth(pcbnew.FromMM(0.20))
                track.SetLayer(pcbnew.F_Cu)
                track.SetNet(power)
                board.Add(track)

            add_track((10.0, 10.0), (11.9475, 10.0))
            add_track((11.9475, 10.0), (15.6875, 6.26))
            add_track((20.0, 10.0), (23.0, 10.0))
            pcbnew.SaveBoard(path, board)
            with open(pro, "w", encoding="utf-8") as handle:
                json.dump({"net_settings": {
                    "classes": [
                        {"name": "Default", "track_width": 0.20,
                         "clearance": 0.20,
                         "via_diameter": 0.60, "via_drill": 0.30},
                        {"name": "Power", "track_width": 1.00,
                         "clearance": 0.20,
                         "via_diameter": 0.80, "via_drill": 0.40},
                    ],
                    "netclass_assignments": {"PWR": "Power"},
                    "netclass_patterns": [],
                }}, handle)

            result = cec_fr.normalize_netclass_geometry(board, path)
            local = [t for t in board.GetTracks()
                     if t.GetClass() == "PCB_TRACK"
                     and t.GetStart().x / 1e6 < 18.0]
            remote = [t for t in board.GetTracks()
                      if t.GetClass() == "PCB_TRACK"
                      and t.GetStart().x / 1e6 >= 18.0]

            self.assertEqual(result["neckdown_split_tracks"], 1)
            self.assertEqual(result["neckdown_sections"], 2)
            narrow_mm = sum(t.GetLength() / 1e6 for t in local
                            if round(t.GetWidth() / 1e6, 2) == 0.20)
            self.assertAlmostEqual(narrow_mm, 2.5, places=3)
            self.assertEqual(sorted(round(t.GetWidth() / 1e6, 2) for t in local),
                             [0.20, 0.20, 1.00])
            self.assertEqual([round(t.GetWidth() / 1e6, 2) for t in remote],
                             [1.00])
            before = [(t.GetStart().x, t.GetStart().y,
                       t.GetEnd().x, t.GetEnd().y, t.GetWidth())
                      for t in board.GetTracks()
                      if t.GetClass() == "PCB_TRACK"]
            second = cec_fr.normalize_netclass_geometry(board, path)
            after = [(t.GetStart().x, t.GetStart().y,
                      t.GetEnd().x, t.GetEnd().y, t.GetWidth())
                     for t in board.GetTracks()
                     if t.GetClass() == "PCB_TRACK"]
            self.assertEqual(second["neckdown_split_tracks"], 0)
            self.assertEqual(after, before)
            self.assertTrue(second["legal_neckdown_uuids"])
            pcbnew.SaveBoard(path, board)
            ok, detail = C.CHECKERS["netclass-geometry-conformance"](
                pcbnew.LoadBoard(path), path, {})[:2]
            self.assertTrue(ok, detail)

    def test_duplicate_board_item_uuids_are_repaired_without_geometry_change(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "duplicate-uuids.kicad_pcb")
            board = pcbnew.CreateEmptyBoard()
            net = pcbnew.NETINFO_ITEM(board, "SIG")
            board.Add(net)

            first = pcbnew.FOOTPRINT(board)
            first.SetReference("U1")
            first.SetPosition(pcbnew.VECTOR2I_MM(10.0, 10.0))
            pad = pcbnew.PAD(first)
            pad.SetPadName("1")
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetSize(pcbnew.VECTOR2I_MM(1.0, 0.5))
            pad.SetPosition(first.GetPosition())
            pad.SetLayerSet(pcbnew.PAD.SMDMask())
            pad.SetNet(net)
            first.Add(pad)
            board.Add(first)

            # The raw copy constructor preserves every persistent UUID.  This
            # models the generated-reference defect; FOOTPRINT.Duplicate would
            # correctly regenerate them and therefore cannot create the fixture.
            second = pcbnew.FOOTPRINT(first)
            second.SetReference("U2")
            second.SetPosition(pcbnew.VECTOR2I_MM(20.0, 10.0))
            board.Add(second)
            pcbnew.SaveBoard(path, board)

            def geometry(board_obj):
                return {fp.GetReference(): (
                    fp.GetPosition().x, fp.GetPosition().y,
                    fp.GetOrientationDegrees(), fp.GetLayer(),
                    [(p.GetNumber(), p.GetNetname(), p.GetPosition().x,
                      p.GetPosition().y, p.GetSize().x, p.GetSize().y)
                     for p in fp.Pads()])
                    for fp in board_obj.GetFootprints()}

            before = geometry(pcbnew.LoadBoard(path))
            report = cec_fr.ensure_unique_board_file_uuids(path)
            after = geometry(pcbnew.LoadBoard(path))
            self.assertGreater(report["duplicate_ids_before"], 0)
            self.assertGreater(report["rewritten"], 0)
            self.assertEqual(report["duplicate_ids_after"], 0)
            self.assertEqual(after, before)
            self.assertEqual(
                cec_fr.ensure_unique_board_file_uuids(path)["rewritten"], 0)

    def test_generated_zone_uuid_and_order_are_semantic_and_stable(self):
        authored_uuid = "11111111-1111-4111-8111-111111111111"
        zone_a = """\n  (zone (net 2) (net_name \"/A\") (layer \"F.Cu\")
    (uuid aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa)
    (name \"orthofill:/A:F.Cu:1\") (priority 3)
    (polygon (pts (xy 1 1) (xy 2 1) (xy 2 2) (xy 1 2))))"""
        zone_b = """\n  (zone (net 3) (net_name \"/B\") (layer \"B.Cu\")
    (uuid bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb)
    (name \"pourplan:/B\") (priority 2)
    (polygon (pts (xy 3 3) (xy 4 3) (xy 4 4) (xy 3 4))))"""
        authored = """\n  (zone (net 1) (net_name \"GND\") (layer \"F.Cu\")
    (uuid %s) (name \"authored-ground\")
    (polygon (pts (xy 0 0) (xy 5 0) (xy 5 5) (xy 0 5))))""" % authored_uuid

        with tempfile.TemporaryDirectory() as directory:
            first = os.path.join(directory, "first.kicad_pcb")
            second = os.path.join(directory, "second.kicad_pcb")
            with open(first, "w", encoding="utf-8") as handle:
                handle.write("(kicad_pcb" + zone_b + authored + zone_a + ")\n")
            with open(second, "w", encoding="utf-8") as handle:
                # Different random UUIDs and creation order, same semantics.
                handle.write("(kicad_pcb" + zone_a.replace(
                    "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                    "cccccccc-cccc-4ccc-8ccc-cccccccccccc") + authored
                    + zone_b.replace(
                        "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
                        "dddddddd-dddd-4ddd-8ddd-dddddddddddd") + ")\n")

            report = cec_fr.canonicalize_generated_zone_file(first)
            cec_fr.canonicalize_generated_zone_file(second)
            one = open(first, encoding="utf-8").read()
            two = open(second, encoding="utf-8").read()
            self.assertEqual(one, two)
            self.assertEqual(report["zones"], 2)
            self.assertIn(authored_uuid, one)
            self.assertEqual(
                cec_fr.canonicalize_generated_zone_file(first)[
                    "uuid_rewritten"], 0)

    def test_ses_import_reads_netclasses_from_staged_source_project(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self._board(directory)
            ses = os.path.join(directory, "candidate.ses")
            output = os.path.join(directory, "candidate.kicad_pcb")
            with open(ses, "w", encoding="utf-8") as handle:
                handle.write("(session candidate)\n")

            self.assertFalse(os.path.exists(
                output[:-len(".kicad_pcb")] + ".kicad_pro"))
            with mock.patch.object(pcbnew, "ImportSpecctraSES",
                                   return_value=True), \
                    mock.patch.object(cec_fr, "normalize_netclass_geometry",
                                      return_value={"tracks": 0, "vias": 0}) as normalize:
                cec_fr.import_ses(source, ses, output, fill_zones=False,
                                  power_pours=(), kelvin_taps=False)

            self.assertTrue(os.path.exists(output))
            self.assertGreaterEqual(normalize.call_count, 1)
            self.assertTrue(all(call.args[1] == source
                                for call in normalize.call_args_list))

    def test_ses_import_restores_router_mutated_footprint_placement(self):
        with tempfile.TemporaryDirectory() as directory:
            source = os.path.join(directory, "source.kicad_pcb")
            ses = os.path.join(directory, "candidate.ses")
            output = os.path.join(directory, "candidate.kicad_pcb")
            board = pcbnew.CreateEmptyBoard()
            footprint = pcbnew.FOOTPRINT(board)
            footprint.SetReference("F1")
            footprint.SetPosition(pcbnew.VECTOR2I_MM(12.345, 23.456))
            footprint.SetOrientationDegrees(90.0)
            footprint.SetLocked(True)
            board.Add(footprint)
            pcbnew.SaveBoard(source, board)
            with open(ses, "w", encoding="utf-8") as handle:
                handle.write("(session candidate)\n")

            def mutate_placement(imported, _session):
                moved = imported.FindFootprintByReference("F1")
                moved.SetPosition(pcbnew.VECTOR2I_MM(13.345, 22.456))
                moved.SetOrientationDegrees(180.0)
                moved.SetLocked(False)
                return True

            with mock.patch.object(
                    pcbnew, "ImportSpecctraSES",
                    side_effect=mutate_placement), \
                    mock.patch.object(
                        cec_fr, "normalize_netclass_geometry",
                        return_value={"tracks": 0, "vias": 0}):
                cec_fr.import_ses(
                    source, ses, output, fill_zones=False,
                    power_pours=(), kelvin_taps=False)

            routed = pcbnew.LoadBoard(output)
            restored = routed.FindFootprintByReference("F1")
            self.assertEqual(
                (restored.GetPosition().x, restored.GetPosition().y),
                (pcbnew.FromMM(12.345), pcbnew.FromMM(23.456)))
            self.assertEqual(restored.GetOrientationDegrees(), 90.0)
            self.assertTrue(restored.IsLocked())

    def test_ses_import_renormalizes_last_mile_geometry_before_scoring(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self._board(directory)
            ses = os.path.join(directory, "candidate.ses")
            output = os.path.join(directory, "candidate.kicad_pcb")
            with open(ses, "w", encoding="utf-8") as handle:
                handle.write("(session candidate)\n")

            lastmile = {"closed": 1, "legs": 1, "refused": 0,
                        "far": 0, "cross_layer": 0}
            with mock.patch.dict(os.environ, {"CEC_LASTMILE": "1"}), \
                    mock.patch.object(pcbnew, "ImportSpecctraSES",
                                      return_value=True), \
                    mock.patch.object(pcbnew, "ZONE_FILLER"), \
                    mock.patch.object(cec_fr, "synthesize_lastmile",
                                      return_value=lastmile), \
                    mock.patch.object(cec_fr, "normalize_netclass_geometry",
                                      return_value={"tracks": 1, "vias": 1}) as normalize:
                cec_fr.import_ses(source, ses, output, fill_zones=True,
                                  power_pours=(), kelvin_taps=False)

            self.assertEqual(normalize.call_count, 2)
            self.assertTrue(all(call.args[1] == source
                                for call in normalize.call_args_list))


if __name__ == "__main__":
    unittest.main()
