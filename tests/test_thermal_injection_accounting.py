#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Injection-accounting regression (2026-07-22, the partial-injection mirage):
# a REQUESTED (I>0) net whose src/sink sit on disconnected copper islands used
# to be SILENTLY omitted from the Joule field -- so a board with OPEN rail
# circuits read COOLER the less complete it was (measured on the 24-pin chain:
# "dT~10.9 PASS" stamps on boards with +5V_MAIN/+5VSB still in unconn_critical,
# vs 61.8 on a sibling with partially-bridged rails). These tests pin:
#   1. the drop MECHANISM (_solve_net_electrical -> None on disconnected src/sink),
#   2. the ACCOUNTING classification in the _oracle_thermal stamp:
#      dropped (on-board, no path)  -> ok=False, INJECTION INCOMPLETE, named nets;
#      absent  (not on this board)  -> ok=False because configured heat was omitted;
#      clean                        -> accounting fields ride the stamp, verdict
#                                      unchanged.
import os
import sys
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

try:
    import numpy as np                                         # noqa: E402
    import cec_thermal2d as T2                                 # noqa: E402
    HAVE_SCIPY = True
except ImportError:                                            # CI host without scipy
    HAVE_SCIPY = False

if not HAVE_SCIPY:
    raise unittest.SkipTest("numpy/scipy required (thermal solver deps)")


F_PHYS = next(k for k, v in T2.STD_CU_LAYERS.items() if v == "F.Cu")
B_PHYS = next(k for k, v in T2.STD_CU_LAYERS.items() if v == "B.Cu")


def _grid(n=10):
    return T2.Grid(0.0, 0.0, n * 1.0, n * 1.0, 1.0)


def _solve(mask, src_xy, sink_xy, grid):
    """One-layer _solve_net_electrical call with centroid terminals."""
    src = [(F_PHYS, grid.idx(*src_xy))]
    sink = [(F_PHYS, grid.idx(*sink_xy))]
    return T2._solve_net_electrical(
        {F_PHYS: mask}, {}, src, sink, 1.0, grid,
        {F_PHYS: 1.0}, {"F.Cu": 0.0}, 25e-6, backend="cpu")


class TestDropMechanism(unittest.TestCase):
    """_solve_net_electrical returns None (not a partial fiction) on open circuits."""

    def test_disconnected_islands_return_none(self):
        g = _grid()
        m = np.zeros((g.ny, g.nx), dtype=bool)
        m[:, 0:4] = True                     # left island
        m[:, 6:10] = True                    # right island (cols 4-5 = the gap)
        self.assertIsNone(_solve(m, (1, 5), (8, 5), g),
                          "src/sink on disconnected islands must yield None")

    def test_bridged_islands_solve(self):
        g = _grid()
        m = np.zeros((g.ny, g.nx), dtype=bool)
        m[:, 0:4] = True
        m[:, 6:10] = True
        m[5, 4:6] = True                     # one-cell bridge closes the circuit
        sol = _solve(m, (1, 5), (8, 5), g)
        self.assertIsNotNone(sol, "a bridged net must solve")
        self.assertIn("links", sol)

    def test_current_field_keeps_spatial_link_coordinates(self):
        g = _grid(6)
        m = np.ones((g.ny, g.nx), dtype=bool)
        sol = _solve(m, (0, 3), (5, 3), g)
        fields, records = T2._current_field_from_solution(
            sol, g, oz_by_layer={F_PHYS: 2.0}, total_current_A=1.0,
            net="POWER")
        self.assertIn("F.Cu", fields)
        self.assertGreater(float(fields["F.Cu"].max()), 0.0)
        sheet = [row for row in records if row["kind"] == "sheet"]
        self.assertTrue(sheet)
        self.assertTrue(all(row["net"] == "POWER" for row in sheet))
        self.assertTrue(all("x_mm" in row and "y_mm" in row for row in sheet))

    def test_distributed_barrel_fractions_preserve_total_conductance(self):
        z = {"F.Cu": 0.0, "B.Cu": 1.6e-3}
        plating = 25e-6
        drill = 3.4
        one = T2._collect_vertical_links(
            [{"drill_mm": drill, "span": ["F.Cu", "B.Cu"]}],
            {"F.Cu", "B.Cu"}, z, plating)
        split = T2._collect_vertical_links(
            [{"drill_mm": drill, "span": ["F.Cu", "B.Cu"],
              "conductance_fraction": 0.25} for _ in range(4)],
            {"F.Cu", "B.Cu"}, z, plating)
        self.assertEqual(1, len(one))
        self.assertEqual(1, len(split))
        self.assertAlmostEqual(one[0][2], split[0][2], places=12)


class TestPhysicalContactLayerInjection(unittest.TestCase):
    """External terminal contacts may inject on one face of a multilayer PTH."""

    def setUp(self):
        self.pad_map = {
            "+12V": {
                "J_BOLT": [
                    ("F.Cu", 10), ("In1.Cu", 10),
                    ("In2.Cu", 10), ("B.Cu", 10),
                ],
            },
        }

    def test_omitted_layer_filter_preserves_all_layer_behavior(self):
        cells = T2._terminal_cells_for_refs(
            self.pad_map, "+12V", ["J_BOLT"])
        self.assertEqual(4, len(cells))

    def test_contact_face_filter_keeps_only_selected_layer(self):
        cells = T2._terminal_cells_for_refs(
            self.pad_map, "+12V", ["J_BOLT"], ["F.Cu"])
        self.assertEqual([("F.Cu", 10)], cells)

    def test_filter_does_not_leak_between_references(self):
        cells = T2._terminal_cells_for_refs(
            self.pad_map, "+12V", ["OTHER"], ["F.Cu"])
        self.assertEqual([], cells)

    def test_pad_equipotential_does_not_bypass_missing_barrel(self):
        grid = T2.Grid(0.0, 0.0, 2.0, 2.0, 1.0)
        mask = np.ones((grid.ny, grid.nx), dtype=bool)
        contact_cell = grid.idx(0, 0)
        result = T2._solve_net_electrical(
            {F_PHYS: mask, B_PHYS: mask}, {},
            [(F_PHYS, contact_cell)], [(B_PHYS, contact_cell)], 10.0, grid,
            {F_PHYS: 1.0, B_PHYS: 1.0},
            {"F.Cu": 0.0, "B.Cu": 1.6e-3}, 25e-6, backend="cpu",
            pad_cells_by_ref={"J1::0": [
                (F_PHYS, grid.idx(x, y)) for y in range(2) for x in range(2)
            ] + [
                (B_PHYS, grid.idx(x, y)) for y in range(2) for x in range(2)
            ]})
        self.assertIsNone(result, "pad-face spreading must not short PCB layers")


class _FakeRes:
    """Duck-typed ThermalResult carrying only what _oracle_thermal reads."""

    def __init__(self, dT, requested=None, dropped=None, absent=None, ambient=50.0,
                 geometry_proven=True):
        self.max_T = ambient + dT
        self.ambient = ambient
        self.nets_requested = requested or {}
        self.nets_dropped = dropped or {}
        self.nets_absent = absent or {}
        self.meta = ({"geometry_source": "source-declared-copper-only:v1",
                      "source_geometry_sha256": "same-fingerprint",
                      "analysis_geometry_sha256": "same-fingerprint"}
                     if geometry_proven else {})


class TestStampClassification(unittest.TestCase):
    """_oracle_thermal fails when any configured current was not injected."""

    def _stamp(self, res):
        import cec_synth_pipeline as csp
        stub = types.SimpleNamespace(
            _solve_thermal=lambda p, ambient, grid_mm: (res, p, "test-cooling"))
        real = sys.modules.get("cec_thermal_overlay")
        sys.modules["cec_thermal_overlay"] = stub
        try:
            return csp._oracle_thermal("fake.kicad_pcb", ambient=50.0,
                                       gate_dt=30.0, grid_mm=0.8)
        finally:
            if real is not None:
                sys.modules["cec_thermal_overlay"] = real
            else:
                sys.modules.pop("cec_thermal_overlay", None)

    def test_dropped_net_fails_with_names(self):
        # the mirage shape: healthy-LOOKING dT with an open 25A rail excluded
        st = self._stamp(_FakeRes(10.9,
                                  requested={"+5V_MAIN": 25.0, "GND": 62.0},
                                  dropped={"+5V_MAIN": "src/sink on disconnected "
                                                       "copper islands"}))
        self.assertFalse(st["ok"], "a dropped configured net must FAIL the stamp")
        self.assertIn("INJECTION INCOMPLETE", st.get("error", ""))
        self.assertIn("+5V_MAIN", st.get("error", ""))
        self.assertIn("+5V_MAIN", st.get("nets_dropped", {}))
        self.assertEqual(st["nets_requested"], 2)
        self.assertEqual(st["nets_injected"], 1)
        self.assertFalse(st["injection_complete"])
        self.assertTrue(st["injection_modeled"])

    def test_absent_requested_net_fails(self):
        st = self._stamp(_FakeRes(20.0,
                                  requested={"/FAN_12V": 8.33, "GND": 50.0},
                                  absent={"/FAN_12V": "no copper/pads on this board"}))
        self.assertFalse(st["ok"], "an absent requested net omits configured heat")
        self.assertIn("INJECTION INCOMPLETE", st.get("error", ""))
        self.assertIn("/FAN_12V", st.get("error", ""))
        self.assertIn("/FAN_12V", st.get("nets_absent", []))
        self.assertEqual(st["nets_injected"], 1)
        self.assertFalse(st["injection_complete"])

    def test_clean_fail_keeps_plain_verdict_with_accounting(self):
        st = self._stamp(_FakeRes(40.0, requested={"GND": 50.0}))
        self.assertFalse(st["ok"])           # 40 > gate 30: plain thermal fail
        self.assertNotIn("error", st)
        self.assertEqual(st["nets_requested"], 1)
        self.assertEqual(st["nets_injected"], 1)
        self.assertTrue(st["injection_complete"])
        self.assertTrue(st["injection_modeled"])

    def test_clean_pass_carries_accounting(self):
        st = self._stamp(_FakeRes(12.0, requested={"GND": 50.0}))
        self.assertTrue(st["ok"])
        self.assertEqual(st["nets_injected"], 1)
        self.assertTrue(st["injection_complete"])
        self.assertNotIn("nets_dropped", st)

    def test_unproven_geometry_fails_before_temperature_can_pass(self):
        st = self._stamp(_FakeRes(12.0, requested={"GND": 50.0},
                                  geometry_proven=False))
        self.assertFalse(st["ok"])
        self.assertFalse(st["injection_complete"])
        self.assertIn("THERMAL GEOMETRY UNPROVEN", st["error"])


if __name__ == "__main__":
    unittest.main()
