"""Pure geometry and planning teeth for routing preflight."""

import os
import sys
import tempfile
import unittest
import json
from unittest import mock

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_route_preflight as rp  # noqa: E402


class RoutePreflightTest(unittest.TestCase):
    HUB_BOARD = os.path.join(
        ROOT, "beta", "hub-standard-rev2", "candidate",
        "hub-standard-rev2-candidate.kicad_pcb")

    def test_critical_probe_replays_kelvin_before_pairs_and_names_endpoints(self):
        precision = mock.Mock()
        precision.precision_route_board.return_value = {
            "pairs_ok": True,
            "kelvin": {
                "taps": 1, "segments": 2,
                "by_net": {"/SENSE_HI": ["RS1->U10.8"]},
                "refused": {"/SENSE_LO": [
                    "RS1->U10.9 OUT-OF-RANGE: 11.2mm > 9.0mm"]},
                "refused_details": [{
                    "net": "/SENSE_LO",
                    "reason": "RS1->U10.9 OUT-OF-RANGE: 11.2mm > 9.0mm",
                    "source_ref": "RS1", "target_ref": "U10",
                    "target_pad": "9",
                    "source_position_mm": [5.0, 5.0],
                    "target_position_mm": [16.2, 5.0],
                    "current_distance_mm": 11.2,
                    "max_distance_mm": 9.0,
                    "required_closer_mm": 2.2,
                    "reason_kind": "kelvin_path_blocked",
                    "mode": "legacy_ladder",
                    "inward_vector": [0.0, -1.0],
                    "target_inward_mm": 0.1,
                    "canonical_min_inward_mm": 0.3,
                    "blocker_refs": ["C10"],
                    "blocker_details": [{
                        "kind": "pad", "ref": "C10", "pad": "1",
                        "position_mm": [15.7, 5.2],
                        "bbox_mm": [15.4, 4.9, 16.0, 5.5],
                        "leg_start_mm": [10.0, 5.0],
                        "leg_end_mm": [16.2, 5.0],
                        "leg_index": 0, "path_kind": "canonical",
                    }],
                }]},
            "pairs": {"routed": [], "refused": []},
        }
        precision._pads_on_net.return_value = []
        fr = mock.Mock()
        fr.owned_locked_nets.return_value = ()
        with mock.patch.dict(sys.modules, {
                "cec_precision_route": precision, "cec_fr": fr}):
            result = rp._probe_critical_pairs_on_board(
                mock.Mock(), "board.kicad_pcb")
        kwargs = precision.precision_route_board.call_args.kwargs
        self.assertTrue(kwargs["do_kelvin"])
        self.assertTrue(kwargs["do_pairs"])
        self.assertFalse(result["critical_routes_ok"])
        self.assertTrue(result["pairs_ok"])
        self.assertFalse(result["kelvin_ok"])
        self.assertEqual(result["kelvin"]["refused"][0]["refs"],
                         ["RS1", "U10"])
        self.assertEqual(
            result["kelvin"]["refused"][0]["required_closer_mm"], 2.2)
        self.assertEqual(
            result["kelvin"]["refused"][0]["blocker_refs"], ["C10"])
        self.assertEqual(
            result["kelvin"]["refused"][0]["reason_kind"],
            "kelvin_path_blocked")
        self.assertEqual(rp.critical_route_refusal_count(result), 1)

    def test_critical_probe_preserves_pair_endpoint_stations_for_placement(self):
        precision = mock.Mock()
        stations = [
            {"id": "U2", "kind": "same-footprint-pair",
             "physical_refs": ["U2"], "center": [10.0, 10.0]},
            {"id": "R11|R12", "kind": "split-member-footprints",
             "physical_refs": ["R11", "R12"],
             "center": [30.0, 21.0]},
        ]
        precision.precision_route_board.return_value = {
            "pairs_ok": False,
            "kelvin": {"taps": 0, "segments": 0, "by_net": {},
                       "refused": {}},
            "pairs": {"routed": [], "refused": [{
                "name": "CAN", "p": "/CAN_H", "n": "/CAN_L",
                "refused": "detour", "endpoint_stations": stations,
            }]},
        }
        precision._pads_on_net.return_value = []
        fr = mock.Mock()
        fr.owned_locked_nets.return_value = ()

        with mock.patch.dict(sys.modules, {
                "cec_precision_route": precision, "cec_fr": fr}):
            result = rp._probe_critical_pairs_on_board(
                mock.Mock(), "board.kicad_pcb")

        self.assertEqual(result["refused"][0]["endpoint_stations"],
                         stations)
        compact = rp.compact_placement_evidence({
            "critical_routes": result})
        self.assertEqual(
            compact["critical_pair_refused"][0]["endpoint_stations"],
            stations)

    def test_critical_probe_does_not_promote_global_grid_blockers(self):
        precision = mock.Mock()
        certificate = {
            "schema": 1,
            "classification": ["middle_guard_refused"],
            "grid": {"explored_blocker_refs": ["X_GLOBAL"]},
            "dominant_blockers": [{
                "kind": "pad", "ref": "X_GLOBAL", "pad": "1"}],
        }
        precision.precision_route_board.return_value = {
            "pairs_ok": False,
            "kelvin": {"taps": 0, "segments": 0, "by_net": {},
                       "refused": {}},
            "pairs": {"routed": [], "refused": [{
                "name": "CAN", "p": "/CAN_H", "n": "/CAN_L",
                "refused": "no corridor",
                "portal_fallback": {"portal_evidence": {
                    "screened": {"start:+1": {
                        "accepted": 0, "blockers": [{
                            "kind": "pad", "ref": "C_LOCAL",
                            "pad": "1"}]}}}},
                "failure_certificate": certificate,
            }]},
        }
        precision._pads_on_net.return_value = []
        fr = mock.Mock()
        fr.owned_locked_nets.return_value = ()

        with mock.patch.dict(sys.modules, {
                "cec_precision_route": precision, "cec_fr": fr}):
            result = rp._probe_critical_pairs_on_board(
                mock.Mock(), "board.kicad_pcb")

        self.assertEqual(result["refused"][0]["blocker_refs"],
                         ["C_LOCAL"])
        self.assertEqual(result["refused"][0]["failure_certificate"],
                         certificate)

    def test_priority_compiler_honors_enabled_pour_reservations(self):
        reservation = {"enabled": True, "corridors": [{"net": "/PWR"}]}
        avoid = (((1.0, 2.0), (3.0, 4.0)),)
        with mock.patch.dict(sys.modules, {"pcbnew": mock.Mock()}), \
                mock.patch.object(rp, "compile_route_reservations",
                                  return_value=reservation), \
                mock.patch.object(rp, "precision_pair_avoid",
                                  return_value=avoid) as avoid_mock, \
                mock.patch.object(rp, "_probe_critical_pairs_on_board",
                                  return_value={"pairs_ok": True}) as probe:
            critical, compiled = rp.compile_priority_routes(
                "board.kicad_pcb", priority_policy="power-first")
        self.assertTrue(critical["pairs_ok"])
        self.assertEqual(probe.call_args.kwargs["avoid"], avoid)
        avoid_mock.assert_called_once_with("board.kicad_pcb", reservation)
        self.assertEqual(compiled["priority_order"], (
            "routed_power_objects", "critical_pairs", "residual_signals"))
        self.assertEqual(compiled["priority_policy"], "power-first")

    def test_priority_compiler_critical_first_replans_enabled_power_later(self):
        reservation = {"enabled": True, "corridors": [{"net": "/PWR"}]}
        with mock.patch.dict(sys.modules, {"pcbnew": mock.Mock()}), \
                mock.patch.object(rp, "compile_route_reservations",
                                  return_value=reservation), \
                mock.patch.object(rp, "precision_pair_avoid") as avoid_mock, \
                mock.patch.object(rp, "_probe_critical_pairs_on_board",
                                  return_value={"pairs_ok": True}) as probe:
            _critical, compiled = rp.compile_priority_routes(
                "board.kicad_pcb", priority_policy="critical-first")

        self.assertEqual(probe.call_args.kwargs["avoid"], ())
        avoid_mock.assert_not_called()
        self.assertEqual(compiled["priority_order"], (
            "critical_pairs", "routed_power_objects", "residual_signals"))
        self.assertEqual(compiled["priority_policy"], "critical-first")
        self.assertEqual(compiled["critical_pair_avoid_count"], 0)

    def test_reservation_compiler_consumes_complete_frozen_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "state.json")
            state = {
                "schema": 3, "placement_scope": "complete",
                "frozen_nets": ["/PWR"],
                "pours": [{"net": "/PWR", "provenance": "pourfirst"}],
                "corridors": [{"net": "/PWR", "layer": "F.Cu",
                               "x0": 1, "y0": 2, "x1": 3, "y1": 4}],
                "vias": [{"net": "/PWR", "x_mm": 5, "y_mm": 6}],
                "reserve_report": {"/PWR": {"reserved": True}},
                "report": {"/PWR": {"groups": {"delegated": 0}}},
            }
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(state, handle)
            with mock.patch.dict(os.environ, {
                    "CEC_POUR_RESERVE": "1",
                    "CEC_POURFIRST_STATE": path}, clear=False), \
                    mock.patch.dict(sys.modules, {
                        "pcbnew": mock.Mock(**{
                            "LoadBoard.return_value": mock.Mock()}),
                        "cec_fab_profile": mock.Mock(**{
                            "routing_layers.return_value": (
                                "F.Cu", "In2.Cu", "B.Cu")}),
                        "cec_slab_pour": mock.Mock(**{
                            "bridge_via_reservations.return_value": [{
                                "net": "/PWR", "layer": "F.Cu",
                                "kind": "bridge_via",
                                "x0": 4.35, "y0": 5.35,
                                "x1": 5.65, "y1": 6.65,
                            }]}),
                        "cec_constraints": mock.Mock(**{
                            "high_current_pour_regions.return_value": [{
                                "net": "/PWR", "layer": "F.Cu",
                                "x0": 1, "y0": 2, "x1": 3, "y1": 4,
                            }]}),
                        "cec_synth_pipeline": mock.Mock()}):
                result = rp.compile_route_reservations("board.kicad_pcb")
        self.assertTrue(result["enabled"])
        self.assertEqual(result["source"], "frozen_full_board")
        self.assertEqual(result["frozen_nets"], ["/PWR"])
        self.assertEqual(result["frozen_via_count"], 1)
        self.assertEqual(result["frozen_pour_rect_count"], 1)
        self.assertEqual(
            [row["kind"] for row in result["corridors"][-2:]],
            ["bridge_via", "frozen_pour"])

    def test_uniform_stamp_cannot_become_route_authority(self):
        synth = mock.Mock()
        synth._oracle_hints_pours.return_value = (
            [], [{"net": "/PWR", "provenance": "uniform_stamp"}], None)
        with mock.patch.dict(os.environ, {
                "CEC_POUR_RESERVE": "1", "CEC_POURFIRST_STATE": ""},
                clear=False), mock.patch.dict(sys.modules, {
                    "pcbnew": mock.Mock(), "cec_slab_pour": mock.Mock(),
                    "cec_synth_pipeline": synth}):
            with self.assertRaisesRegex(RuntimeError, "uniform_stamp"):
                rp.compile_route_reservations("board.kicad_pcb")

    def test_placement_preflight_replans_uniform_stamp_exactly(self):
        synth = mock.Mock()
        synth._oracle_hints_pours.return_value = (
            [], [{"net": "/PWR", "layer": "F.Cu",
                  "polygon": [(0, 0), (99, 0), (99, 99), (0, 99)],
                  "provenance": "uniform_stamp"}], None)
        synth._orthogonal_polygon_rectangles.return_value = (
            [(1.0, 2.0, 3.0, 4.0)], False)
        planner = mock.Mock()
        planner.plan_pours.return_value = (
            [{"net": "/PWR", "layer": "F.Cu", "name": "lane:/PWR",
              "polygon": [(1, 2), (3, 2), (3, 4), (1, 4)]}],
            [{"net": "/PWR", "x_mm": 2.0, "y_mm": 3.0}],
            {"/PWR": {"path_found": True}})
        slab = mock.Mock()
        slab.reservation_from_search.return_value = ([{
            "net": "/PWR", "layer": "F.Cu",
            "x0": 1, "y0": 2, "x1": 3, "y1": 4}], True)
        slab.bridge_via_reservations.return_value = [{
            "net": "/PWR", "layer": "In2.Cu", "kind": "bridge_via",
            "x0": 1.3, "y0": 2.3, "x1": 2.7, "y1": 3.7}]
        grid = object()

        def fill_collect(_board, asks, **kwargs):
            self.assertEqual(asks, [{
                "net": "/PWR", "layers": ("F.Cu",),
                "provenance": "prospective_route_preflight"}])
            # The 99 mm stamped polygon is intentionally absent: only design
            # intent may cross this authority boundary.
            self.assertNotIn("polygon", asks[0])
            kwargs["collect"].update({
                "_grid": grid,
                "/PWR": {"ok": True, "path_cells": {"F.Cu": mock.Mock()},
                           "bridges": [], "rcells": {}, "foreign": {}},
            })
            return planner.plan_pours.return_value

        planner.plan_pours.side_effect = fill_collect
        board = mock.Mock()
        with mock.patch.dict(os.environ, {
                "CEC_POUR_RESERVE": "1", "CEC_POURFIRST_STATE": "",
                "CEC_PROSPECTIVE_POUR_RESERVATIONS": "1"}, clear=False), \
                mock.patch.dict(sys.modules, {
                    "pcbnew": mock.Mock(**{"LoadBoard.return_value": board}),
                    "cec_fab_profile": mock.Mock(**{
                        "routing_layers.return_value": (
                            "F.Cu", "In2.Cu", "B.Cu")}),
                    "cec_pour_plan": planner,
                    "cec_slab_pour": slab,
                    "cec_synth_pipeline": synth}):
            result = rp.compile_route_reservations("board.kicad_pcb")
        self.assertTrue(result["enabled"])
        self.assertTrue(result["prospective"])
        self.assertEqual(result["source"], "prospective_full_board")
        self.assertEqual(result["reserved_nets"], ["/PWR"])
        self.assertEqual(result["pour_rect_count"], 1)
        self.assertEqual(result["bridge_via_count"], 1)
        self.assertEqual(planner.plan_pours.call_args.kwargs[
            "relief_diagnostics"], False)

    def test_precision_avoid_preserves_decomposed_front_pour_geometry(self):
        reservations = {"enabled": True, "corridors": [
            {"layer": "F.Cu", "net": "/PWR", "x0": 1, "y0": 2,
             "x1": 3, "y1": 4},
            {"layer": "F.Cu", "net": "/PWR", "x0": 3, "y0": 3,
             "x1": 5, "y1": 4},
            {"layer": "In3.Cu", "net": "/PWR", "x0": 0, "y0": 0,
             "x1": 9, "y1": 9},
        ]}
        self.assertEqual(rp.precision_pair_avoid(
            "board.kicad_pcb", reservations), (
                (1.0, 2.0, 3.0, 4.0, "/PWR", "F.Cu"),
                (3.0, 3.0, 5.0, 4.0, "/PWR", "F.Cu"),
                (0.0, 0.0, 9.0, 9.0, "/PWR", "In3.Cu")))

    def test_priority_compiler_keeps_signal_first_without_reservations(self):
        reservation = {"enabled": False, "corridors": []}
        with mock.patch.dict(sys.modules, {"pcbnew": mock.Mock()}), \
                mock.patch.object(rp, "compile_route_reservations",
                                  return_value=reservation), \
                mock.patch.object(rp, "precision_pair_avoid") as avoid_mock, \
                mock.patch.object(rp, "_probe_critical_pairs_on_board",
                                  return_value={"pairs_ok": True}) as probe:
            _critical, compiled = rp.compile_priority_routes("board.kicad_pcb")
        self.assertEqual(probe.call_args.kwargs["avoid"], ())
        avoid_mock.assert_not_called()
        self.assertEqual(compiled["priority_order"], (
            "critical_pairs", "routed_power_objects", "residual_signals"))

    def test_compact_placement_evidence_and_key(self):
        report = {
            "gate": False, "wall_s": 1.2,
            "fanout": {"blocked": 1},
            "pin_access": {"blocked_count": 2,
                           "blocked": [{"ref": "U1", "critical": True},
                                       {"ref": "U2", "critical": False}]},
            "critical_routes": {
                "pairs_ok": False, "critical_routes_ok": False,
                "kelvin": {"refused": [{
                    "net": "/SENSE_LO", "reason": "RS1->U10.9 refused",
                    "refs": ["RS1", "U10"],
                    "source_ref": "RS1", "target_ref": "U10",
                    "blocker_refs": ["C10", "U10"],
                    "blocker_details": [{
                        "kind": "pad", "ref": "C10", "pad": "1",
                        "position_mm": [8.0, 7.0],
                        "bbox_mm": [7.7, 6.7, 8.3, 7.3],
                        "leg_start_mm": [5.0, 5.0],
                        "leg_end_mm": [10.0, 5.0],
                        "leg_index": 0, "path_kind": "canonical",
                    }]}]},
                "route_quality": {"ok": False, "refused": [{
                    "type": "acute_backtrack", "net": "/DP",
                    "refs": ["D6", "U1"]}]},
                "refused": [{"p": "/DP", "n": "/DN",
                             "refs": ["J_USB", "D6", "U1"],
                             "blocker_refs": ["C8", "R10"]}]},
            "criticality": {"pin_access_blocked_count": 1,
                            "unroutable_count": 1},
            "stackup": {"blocked_cell_count": 7,
                        "blocked_cells_per_layer": [3, 4]},
            "congestion": {"unroutable_count": 3,
                           "unroutable_connections": [{"net": "/A"}],
                           "residual_overuse_escaped": 5,
                           "residual_overuse": 8},
            "future_congestion": {
                "critical_corridor_conflicts": 4,
                "reservation_crossings": 6,
                "reservation_refused_nets": ["/PWR"],
                "reservation_rect_count": 486,
                "reservation_cell_count": 123,
                "reservation_owned_nets": ["/VCC"],
                "overflow_units": 10,
                "corridor_obstacle_crossings": 2,
                "expected_via_count": 3,
                "wire_demand_units": 99},
        }
        evidence = rp.compact_placement_evidence(report)
        self.assertEqual(evidence["fanout_blocked_count"], 1)
        self.assertEqual(evidence["critical_pair_refused_count"], 1)
        self.assertEqual(evidence["critical_pair_refs"],
                         ["D6", "J_USB", "U1"])
        self.assertEqual(evidence["critical_pair_blocker_refs"],
                         ["C8", "R10"])
        self.assertEqual(evidence["critical_kelvin_blocker_refs"], ["C10"])
        self.assertEqual(
            evidence["critical_kelvin_blocker_details"][0]["ref"], "C10")
        self.assertEqual(evidence["critical_pair_flow_through_refs"], [])
        self.assertEqual(evidence["critical_kelvin_refused_count"], 1)
        self.assertEqual(evidence["critical_kelvin_refs"], ["RS1", "U10"])
        self.assertEqual(evidence["critical_route_quality_refused_count"], 1)
        self.assertEqual(evidence["critical_route_quality_refs"],
                         ["D6", "U1"])
        self.assertEqual(evidence["critical_route_refused_count"], 3)
        self.assertEqual(evidence["critical_pin_access_blocked_count"], 1)
        self.assertEqual(evidence["pin_access_blocked_count"], 2)
        self.assertEqual(evidence["unroutable_count"], 3)
        self.assertEqual(evidence["future_reservation_crossings"], 6)
        self.assertEqual(evidence["future_reservation_refused_count"], 1)
        self.assertEqual(evidence["future_reservation_rect_count"], 486)
        self.assertEqual(rp.placement_evidence_key(evidence),
                         (0, 3, 0, 1, 1, 1, 2, 3,
                          0, 1, 6, 4, 10, 2, 3, 99, 5.0, 8.0))
        self.assertGreater(rp.placement_evidence_key({"error": "boom"}),
                           rp.placement_evidence_key(evidence))

    def test_compact_pair_blockers_only_names_fully_refused_terminal(self):
        report = {
            "critical_routes": {"refused": [{
                "refs": ["J_USB", "D6", "U1"],
                "blocker_refs": ["F1", "C8", "R10"],
                "flow_leg_refusal": {"layers": [{"attempt": {
                    "portal_fallback": {"shallow": {
                        "portal_evidence": {
                            "axis": [-1.0, 0.0],
                            "normal": [0.0, -1.0],
                            "screened": {
                                "start:+1": {"accepted": 1, "blockers": [
                                    {"ref": "F1", "count": 9}]},
                                "start:-1": {"accepted": 0, "blockers": [
                                    {"ref": "F1", "count": 40}]},
                                "end:+1": {"accepted": 0, "blockers": [
                                    {"ref": "C8", "count": 50},
                                    {"ref": "R10", "count": 20}]},
                                "end:-1": {"accepted": 0, "blockers": [
                                    {"ref": "C8", "count": 60},
                                    {"ref": "R10", "count": 30},
                                    {"ref": "U1", "count": 4}]},
                            },
                        }}}}}],
                },
            }]},
        }

        evidence = rp.compact_placement_evidence(report)

        self.assertEqual(evidence["critical_pair_blocker_refs"],
                         ["C8", "R10"])
        self.assertEqual(
            [(row["ref"], row["endpoint"], row["count"])
             for row in evidence["critical_pair_blocker_relief"]],
            [("C8", "end", 110), ("R10", "end", 50)])

    def test_compact_pair_blockers_consumes_precision_relief_projection(self):
        report = {"critical_routes": {"refused": [{
            "name": "CAN", "refs": ["U1", "J1"],
            "blocker_refs": ["C8"],
            "blocker_relief": [{
                "ref": "C8", "endpoint": "target",
                "normal": [0.0, 1.0], "axis": [1.0, 0.0],
                "count": 17,
            }],
        }]}}

        evidence = rp.compact_placement_evidence(report)

        self.assertEqual(evidence["critical_pair_blocker_refs"], ["C8"])
        self.assertEqual(evidence["critical_pair_blocker_relief"], [{
            "ref": "C8", "endpoint": "target",
            "normal": [0.0, 1.0], "axis": [1.0, 0.0],
            "count": 17,
        }])

    def test_compact_pair_evidence_preserves_failure_certificate(self):
        certificate = {
            "schema": 1,
            "classification": ["reservation_barrier"],
            "reservation_owners": ["/RAIL"],
            "relief_vectors": [{
                "endpoint": "start", "direction": "normal-positive",
                "vector": [0.0, 1.0], "probe_steps_mm": [0.5, 1.0],
                "reason": "reservation_barrier",
            }],
        }
        evidence = rp.compact_placement_evidence({
            "critical_routes": {"refused": [{
                "name": "CAN", "refs": ["U1", "R1", "R2"],
                "failure_certificate": certificate,
            }]},
        })

        self.assertEqual(
            evidence["critical_pair_failure_certificates"], [{
                "name": "CAN", "certificate": certificate,
            }])
        self.assertEqual(
            evidence["critical_pair_refused"][0]["failure_certificate"],
            certificate)

    def test_segment_rectangle_intersection(self):
        rect = (2.0, 2.0, 4.0, 4.0)
        self.assertTrue(rp._segment_hits_rect(0, 3, 6, 3, rect))
        self.assertTrue(rp._segment_hits_rect(2, 0, 2, 6, rect))
        self.assertFalse(rp._segment_hits_rect(0, 0, 1, 1, rect))

    def test_blockage_witness_is_joined_to_residual_and_foreign_refs(self):
        rows = [{
            "kind": "over_capacity", "layer": "F.Cu",
            "layer_index": 0, "x": 2, "y": 3, "overuse": 1.0,
            "connections": [
                {"net": "/PAIR", "protected": True},
                {"net": "/GPIO", "protected": False}],
            "escape_directions": ("N", "S"),
        }]
        pin_access = {"pads": [
            {"ref": "U_PAIR", "pad": "1", "net": "/PAIR",
             "x": 2.5, "y": 3.5, "bbox": (2.4, 3.4, 2.6, 3.6)},
            {"ref": "R_GPIO", "pad": "1", "net": "/GPIO",
             "x": 2.5, "y": 3.5, "bbox": (2.4, 3.4, 2.6, 3.6)},
            {"ref": "C_BLOCK", "pad": "1", "net": "/OTHER",
             "x": 2.5, "y": 3.5, "bbox": (2.4, 3.4, 2.6, 3.6)},
        ]}
        result = rp._annotate_blockage_witnesses(
            rows, pin_access,
            {"grid_mm": 1.0, "grid_origin_mm": (0.0, 0.0)})[0]
        self.assertEqual(result["residual_nets"], ["/GPIO"])
        self.assertEqual(result["critical_nets"], ["/PAIR"])
        self.assertEqual(result["candidate_refs"][0]["ref"], "C_BLOCK")
        self.assertEqual(result["candidate_refs"][0]["role"],
                         "foreign_blocker")
        self.assertIn("R_GPIO", {
            row["ref"] for row in result["candidate_refs"]})

    def test_route_reservation_removes_owned_net_and_blocks_foreign_nets(self):
        conns = (
            ("/RAIL", (0, 1, 1), (0, 8, 1)),
            ("/SIG", (0, 1, 5), (0, 8, 5)),
        )
        stackup = {
            "layer_names": ("F.Cu", "B.Cu"),
            "grid_mm": 1.0, "grid_origin_mm": (0.0, 0.0),
            "allowed_layers_by_conn": ((True, True), (True, True)),
            "net_kinds": ("power", "signal"),
            "netclasses": ("Power", "Default"),
        }
        reservation = {
            "enabled": True, "fingerprint": "abc",
            "report": {"/RAIL": {"reserved": True}},
            "corridors": [{"net": "/RAIL", "layer": "F.Cu",
                           "x0": 4.0, "y0": 0.0,
                           "x1": 6.0, "y1": 10.0}],
        }
        filtered, meta, blocked, summary = rp.apply_route_reservations(
            conns, stackup, (set(), set()), reservation, 10, 10)
        self.assertEqual([row[0] for row in filtered], ["/SIG"])
        self.assertEqual(meta["reservation_connections_removed"], 1)
        self.assertEqual(meta["reservation_rect_count"], 1)
        self.assertEqual(summary["owned_nets"], ["/RAIL"])
        self.assertIn((0, 5, 4), blocked[0])
        self.assertNotIn((1, 5, 4), blocked[0])

    def _array_access(self):
        pads = []
        for y in range(8):
            for x in range(8):
                ns = "S" if y >= 4 else "N"
                ew = "E" if x >= 4 else "W"
                pads.append({
                    "ref": "U1", "pad": "%d" % (y * 8 + x + 1),
                    "net": "/N%d" % (y * 8 + x + 1),
                    "x": float(x), "y": float(y),
                    "mode": "trace", "directions": (ns + ew,),
                    "options": [], "pofv": True,
                })
        return {"pads": pads,
                "routing_layers": ("F.Cu", "In2.Cu", "B.Cu")}

    def test_array_fanout_is_deterministic_and_uses_pofv_for_deep_rings(self):
        first = rp.plan_array_fanouts(self._array_access())
        second = rp.plan_array_fanouts(self._array_access())
        self.assertEqual(first, second)
        array = first["arrays"][0]
        self.assertEqual(array["grid"], (8, 8))
        self.assertGreater(array["via_in_pad"], 0)
        self.assertGreater(array["dogbone"], 0)
        self.assertEqual(array["blocked"], 0)

    def test_hierarchical_tiers_are_disjoint(self):
        conns = [
            ("/USB_D_P", (0, 0, 0), (0, 1, 1)),
            ("/+5V", (0, 0, 0), (0, 1, 1)),
            ("/GPIO", (0, 0, 0), (0, 1, 1)),
        ]
        stack = {"net_kinds": ("high_speed", "power", "signal")}
        pins = {"constrained": [{"net": "/GPIO"},
                                 {"net": "unconnected-(U1-X-Pad1)"}],
                "blocked": []}
        tiers = rp.hierarchical_tiers(
            conns, stack, pins, declared_critical=("/GPIO",))
        flattened = [net for tier in tiers for net in tier["nets"]]
        self.assertEqual(set(flattened), {"/USB_D_P", "/+5V", "/GPIO"})
        self.assertEqual(len(flattened), len(set(flattened)))
        self.assertIn("/USB_D_P", tiers[0]["nets"])
        self.assertIn("/GPIO", tiers[1]["nets"])
        self.assertNotIn("unconnected-(U1-X-Pad1)", flattened)

    def test_short_signal_is_local_priority_without_name_heuristics(self):
        conns = [
            ("/LOCAL", (0, 2, 2), (0, 5, 6)),
            ("/LONG", (0, 0, 0), (0, 40, 0)),
        ]
        stack = {
            "net_kinds": ("signal", "signal"),
            "grid_mm": 1.0,
        }
        tiers = rp.hierarchical_tiers(
            conns, stack, {"constrained": [], "blocked": []},
            local_span_mm=6.0)
        by_name = {row["name"]: row["nets"] for row in tiers}
        self.assertEqual(by_name["local_interconnect"], ["/LOCAL"])
        self.assertEqual(by_name["residual_signals"], ["/LONG"])

    def test_critical_selector_is_exact_or_unambiguous_leaf(self):
        result = rp._resolve_critical_selectors(
            ("BLACKOUT_SENSE", "/SHEET/COMP_THRESH", "MISSING"),
            ("/BLACKOUT_SENSE", "/SHEET/COMP_THRESH", "/A/SENSE",
             "/B/SENSE"))
        self.assertEqual(result["resolved"],
                         ["/BLACKOUT_SENSE", "/SHEET/COMP_THRESH"])
        self.assertEqual(result["unresolved"], ["MISSING"])
        self.assertFalse(result["ok"])
        ambiguous = rp._resolve_critical_selectors(
            ("SENSE",), ("/A/SENSE", "/B/SENSE"))
        self.assertIn("SENSE", ambiguous["ambiguous"])

    def test_current_board_policy_supplies_critical_selectors_by_default(self):
        report = rp.analyze(
            self.HUB_BOARD, iters=0, run_congestion=False,
            run_critical_routes=False)
        criticality = report["criticality"]
        self.assertEqual(criticality["selectors"], [
            "BLACKOUT_SENSE", "COMP_THRESH", "PWR_FAIL_INT"])
        self.assertTrue(report["policy"]["fingerprint"])

    def test_explicit_empty_selectors_disable_policy_for_control_run(self):
        report = rp.analyze(
            self.HUB_BOARD, iters=0, run_congestion=False,
            run_critical_routes=False, critical_nets=())
        self.assertEqual(report["criticality"]["selectors"], [])

    def test_spatial_pin_access_matches_bruteforce_on_current_beta_hub(self):
        indexed = rp.analyze_pin_access(
            self.HUB_BOARD, use_spatial_index=True)
        brute = rp.analyze_pin_access(
            self.HUB_BOARD, use_spatial_index=False)
        indexed.pop("geometry", None)
        brute.pop("geometry", None)
        self.assertEqual(indexed, brute)

    def test_incremental_zero_delta_matches_ordinary_quick_screen(self):
        selectors = ("BLACKOUT_SENSE", "COMP_THRESH", "PWR_FAIL_INT")
        ordinary = rp.compact_placement_evidence(rp.analyze(
            self.HUB_BOARD, iters=0, run_congestion=False,
            run_critical_routes=False, critical_nets=selectors))
        context = rp.prepare_incremental_access(
            self.HUB_BOARD, critical_nets=selectors)
        incremental = rp.compact_placement_evidence(
            rp.analyze_incremental_access(context))
        ordinary.pop("wall_s", None)
        incremental.pop("wall_s", None)
        self.assertEqual(incremental, ordinary)

    def test_incremental_180_delta_matches_materialized_current_beta_hub(self):
        import pcbnew

        context = rp.prepare_incremental_access(self.HUB_BOARD, grid_mm=1.0)
        board = pcbnew.LoadBoard(self.HUB_BOARD)
        footprint = board.FindFootprintByReference("R37")
        self.assertIsNotNone(footprint)
        pos = footprint.GetPosition()
        target = (pos.x / 1e6, pos.y / 1e6,
                  (footprint.GetOrientationDegrees() + 180.0) % 360.0)
        incremental = rp.compact_placement_evidence(
            rp.analyze_incremental_access(
                context, placements={"R37": target}))
        with tempfile.TemporaryDirectory() as directory:
            rotated = os.path.join(directory, "rotated.kicad_pcb")
            footprint.SetOrientationDegrees(target[2])
            pcbnew.SaveBoard(rotated, board)
            materialized = rp.compact_placement_evidence(rp.analyze(
                rotated, grid_mm=1.0, iters=0, run_congestion=False,
                run_critical_routes=False))
        incremental.pop("wall_s", None)
        materialized.pop("wall_s", None)
        self.assertEqual(incremental, materialized)

    def test_incremental_90_access_delta_matches_materialized_current_beta_hub(self):
        import pcbnew

        context = rp.prepare_incremental_access(self.HUB_BOARD, grid_mm=1.0)
        board = pcbnew.LoadBoard(self.HUB_BOARD)
        footprint = board.FindFootprintByReference("R37")
        self.assertIsNotNone(footprint)
        pos = footprint.GetPosition()
        target = (pos.x / 1e6, pos.y / 1e6,
                  (footprint.GetOrientationDegrees() + 90.0) % 360.0)
        incremental = rp.compact_placement_evidence(
            rp.analyze_incremental_access(
                context, placements={"R37": target}))
        with tempfile.TemporaryDirectory() as directory:
            rotated = os.path.join(directory, "rotated.kicad_pcb")
            footprint.SetOrientationDegrees(target[2])
            pcbnew.SaveBoard(rotated, board)
            materialized = rp.compact_placement_evidence(rp.analyze(
                rotated, grid_mm=1.0, iters=0, run_congestion=False,
                run_critical_routes=False))
        for evidence in (incremental, materialized):
            evidence.pop("wall_s", None)
            # The access-only incremental contract does not yet own the global
            # obstacle raster; finalist KiCad analysis still recomputes it.
            evidence.pop("blocked_cell_count", None)
            evidence.pop("blocked_cells_per_layer", None)
        self.assertEqual(incremental, materialized)

    def test_incremental_future_congestion_matches_full_recompute_on_hub(self):
        context = rp.prepare_incremental_access(
            self.HUB_BOARD, critical_nets=(
                "BLACKOUT_SENSE", "COMP_THRESH", "PWR_FAIL_INT"),
            grid_mm=1.0)
        source = context.board_db.footprints["R37"]
        placements = {"R37": (
            source.x, source.y, (source.rotation + 90.0) % 360.0)}
        incremental = context.future_congestion.evaluate(placements)
        recomputed = context.future_congestion.recompute(placements)
        for report in (incremental, recomputed):
            report.pop("incremental", None)
        self.assertEqual(incremental, recomputed)

    def test_future_congestion_delta_matches_materialized_hub_rotation(self):
        import pcbnew

        selectors = ("BLACKOUT_SENSE", "COMP_THRESH", "PWR_FAIL_INT")
        context = rp.prepare_incremental_access(
            self.HUB_BOARD, critical_nets=selectors, grid_mm=1.0)
        source = context.board_db.footprints["R37"]
        target = (source.x, source.y, (source.rotation + 90.0) % 360.0)
        incremental = context.future_congestion.evaluate({"R37": target})
        board = pcbnew.LoadBoard(self.HUB_BOARD)
        board.FindFootprintByReference("R37").SetOrientationDegrees(target[2])
        with tempfile.TemporaryDirectory() as directory:
            rotated = os.path.join(directory, "rotated.kicad_pcb")
            pcbnew.SaveBoard(rotated, board)
            materialized = rp.analyze(
                rotated, grid_mm=1.0, iters=0, run_congestion=False,
                run_critical_routes=False, run_future_congestion=True,
                critical_nets=selectors)["future_congestion"]
        for report in (incremental, materialized):
            report.pop("incremental", None)
            report.pop("context_fingerprint", None)
        self.assertEqual(incremental, materialized)

    def test_congestion_heatmap_contains_all_layers(self):
        usage = np.zeros((4, 5, 6), dtype=np.float32)
        usage[0, 1, 1] = 1
        usage[3, 3, 4] = 3
        with tempfile.TemporaryDirectory() as directory:
            output = os.path.join(directory, "map.png")
            self.assertEqual(rp.render_congestion_map(
                usage, 1, ("F.Cu", "In2.Cu", "In3.Cu", "B.Cu"), output),
                output)
            from PIL import Image
            with Image.open(output) as image:
                self.assertGreater(image.width, image.height,
                                   "four layers render as a two-column panel")


if __name__ == "__main__":
    unittest.main()
