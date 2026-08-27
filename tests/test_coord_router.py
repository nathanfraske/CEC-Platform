"""Determinism and multi-layer teeth for the negotiated-congestion router."""

import locale
import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_coord_router as ccr  # noqa: E402
import cec_route_awareness_service as awareness_service  # noqa: E402


def _problem():
    return [
        ("/A", (0, 1, 1), (3, 6, 7)),
        ("/B", (3, 1, 7), (0, 6, 1)),
        ("/C", (0, 3, 1), (0, 3, 7)),
    ]


class CoordinatedRouterDeterminismTest(unittest.TestCase):
    def _route(self, backend):
        return ccr.route_problem(
            _problem(), 8, 9, backend=backend, L=4, iters=8,
            max_sweeps=40, cost_mode="fixed", cost_scale=100,
            chunk_min=1, chunk_frac=0.5)

    def test_fixed_point_cpu_is_repeatable(self):
        first = self._route("cpu")
        second = self._route("cpu")
        self.assertEqual(first["paths_by_conn"], second["paths_by_conn"])
        np.testing.assert_array_equal(first["usage"], second["usage"])
        self.assertEqual(first["residual_overuse"],
                         second["residual_overuse"])

    def test_zero_iteration_budget_returns_named_unroutable_evidence(self):
        result = ccr.route_problem(
            _problem(), 8, 9, backend="cpu", L=4, iters=0,
            cost_mode="fixed", connection_priorities=[0, 1, 2],
            protected_priority_max=0)

        self.assertEqual(result["iters_used"], 0)
        self.assertEqual(result["unroutable_count"], len(_problem()))
        self.assertEqual(result["paths_by_conn"], [None] * len(_problem()))
        self.assertEqual(set(result["paths"]), {"/A", "/B", "/C"})
        self.assertTrue(result["negotiation"][
            "budget_exhausted_before_route"])
        self.assertEqual(result["blockage_witnesses"][0]["kind"],
                         "unroutable")

    def test_four_layer_descent_emits_only_grid_or_through_via_moves(self):
        result = self._route("cpu")
        for conn, path in zip(_problem(), result["paths_by_conn"]):
            self.assertEqual(path[0], conn[2])
            self.assertEqual(path[-1], conn[1])
            for left, right in zip(path, path[1:]):
                dl = abs(left[0] - right[0])
                planar = abs(left[1] - right[1]) + abs(left[2] - right[2])
                self.assertTrue((dl == 0 and planar == 1)
                                or (dl > 0 and planar == 0),
                                (left, right))

    @unittest.skipUnless(ccr._cp is not None, "CuPy unavailable")
    def test_fixed_point_cpu_gpu_paths_are_identical(self):
        try:
            ccr._cp.cuda.Device(0).compute_capability
        except Exception as exc:  # pragma: no cover - hardware-dependent
            self.skipTest("CUDA unavailable: %s" % exc)
        encoding_before = locale.getencoding()
        cpu = self._route("cpu")
        gpu = self._route("gpu")
        self.assertEqual(locale.getencoding(), encoding_before)
        self.assertEqual(cpu["paths_by_conn"], gpu["paths_by_conn"])
        np.testing.assert_array_equal(cpu["usage"], gpu["usage"])
        self.assertEqual(cpu["residual_overuse"], gpu["residual_overuse"])

    def test_unknown_cost_mode_refuses(self):
        with self.assertRaises(ValueError):
            ccr.route_problem(_problem(), 8, 9, backend="cpu", L=4,
                              iters=1, cost_mode="approximate")

    def test_per_connection_layer_policy_is_hard(self):
        conn = [("/PAIR_P", (0, 1, 1), (3, 5, 6))]
        result = ccr.route_problem(
            conn, 7, 8, backend="cpu", L=4, iters=2,
            max_sweeps=32, cost_mode="fixed",
            allowed_layers=[(True, False, False, True)])
        self.assertTrue(result["paths_by_conn"][0])
        self.assertTrue(all(point[0] in (0, 3)
                            for point in result["paths_by_conn"][0]))

    def test_layer_policy_shape_mismatch_refuses(self):
        with self.assertRaisesRegex(ValueError, "allowed_layers shape"):
            ccr.route_problem(_problem(), 8, 9, backend="cpu", L=4,
                              iters=1, allowed_layers=[(True, False)])

    def test_priority_tiers_are_sequential_and_protected_after_first_route(self):
        conns = [
            ("/PAIR_P", (0, 1, 0), (0, 1, 6)),
            ("/CONTROL", (0, 0, 1), (0, 4, 1)),
            ("/RESIDUAL", (0, 0, 3), (0, 4, 3)),
        ]
        result = ccr.route_problem(
            conns, 5, 7, backend="cpu", L=2, iters=5,
            max_sweeps=32, cost_mode="fixed", chunk_min=1,
            connection_priorities=[0, 1, 4],
            protected_priority_max=1)
        policy = result["negotiation"]["priority_routing"]
        self.assertTrue(policy["enabled"])
        self.assertEqual(policy["protected_connection_count"], 2)
        self.assertEqual(policy["protected_retries_after_initial"], 0)
        self.assertEqual(
            [row["priority"] for row in policy["levels"]], [0, 1, 4])
        self.assertEqual(
            list(result["negotiation"]["trace"][0][
                "active_by_priority"]), ["0", "1", "4"])

    def test_priority_contract_fails_closed_on_shape_or_missing_policy(self):
        with self.assertRaisesRegex(ValueError, "connection_priorities shape"):
            ccr.route_problem(
                _problem(), 8, 9, backend="cpu", L=4, iters=1,
                connection_priorities=[0])
        with self.assertRaisesRegex(ValueError, "protected priority requires"):
            ccr.route_problem(
                _problem(), 8, 9, backend="cpu", L=4, iters=1,
                protected_priority_max=1)

    def test_foreign_copper_wall_is_reported_unroutable_not_force_closed(self):
        conn = [("/A", (0, 2, 0), (0, 2, 4))]
        wall = {(0, y, 2) for y in range(5)}
        result = ccr.route_problem(
            conn, 5, 5, backend="cpu", L=1, iters=2,
            max_sweeps=20, cost_mode="fixed",
            blocked_cells_by_conn=[wall])
        self.assertIsNone(result["paths_by_conn"][0])
        self.assertEqual(result["unroutable_count"], 1)
        self.assertEqual(result["unroutable_connections"][0]["net"], "/A")
        witness = result["blockage_witnesses"][0]
        self.assertEqual(witness["kind"], "unroutable")
        self.assertEqual(witness["net"], "/A")
        self.assertEqual(witness["failure_scope"], "corridor_blocked")
        self.assertTrue(all(row["open_neighbor_count"] > 0
                            for row in witness["terminals"]))

    def test_over_capacity_witness_names_owners_and_perpendicular_escape(self):
        conns = [
            ("/CRITICAL", (0, 2, 0), (0, 2, 4)),
            ("/RESIDUAL", (0, 2, 0), (0, 2, 4)),
        ]
        result = ccr.route_problem(
            conns, 5, 5, backend="cpu", L=1, iters=1,
            max_sweeps=20, cost_mode="fixed", cap=1,
            chunk_min=1, connection_priorities=[0, 4],
            protected_priority_max=1)
        hot = next(row for row in result["blockage_witnesses"]
                   if row["kind"] == "over_capacity")
        self.assertEqual([row["net"] for row in hot["connections"]],
                         ["/CRITICAL", "/RESIDUAL"])
        self.assertTrue(hot["connections"][0]["protected"])
        self.assertFalse(hot["connections"][1]["protected"])
        self.assertEqual(tuple(hot["escape_directions"]), ("N", "S"))

    def test_foreign_wall_can_be_escaped_on_another_legal_layer(self):
        conn = [("/A", (0, 2, 0), (0, 2, 4))]
        wall = {(0, y, 2) for y in range(5)}
        result = ccr.route_problem(
            conn, 5, 5, backend="cpu", L=2, iters=2,
            max_sweeps=30, cost_mode="fixed",
            blocked_cells_by_conn=[wall],
            allowed_layers=[(True, True)])
        self.assertEqual(result["unroutable_count"], 0)
        self.assertTrue(result["paths_by_conn"][0])
        self.assertFalse(any(point in wall
                             for point in result["paths_by_conn"][0]))

    def test_congestion_summary_is_compact_and_layer_named(self):
        usage = np.zeros((2, 3, 4), dtype=np.float32)
        usage[1, 2, 3] = 4
        summary = ccr.summarize_congestion(
            usage, 1, layer_names=("F.Cu", "B.Cu"), top_k=4)
        self.assertEqual(summary["layers"][1]["name"], "B.Cu")
        self.assertEqual(summary["layers"][1]["overused_cells"], 1)
        self.assertEqual(summary["hotspots"], [{
            "layer": "B.Cu", "layer_index": 1, "x": 3, "y": 2,
            "usage": 4.0, "overuse": 3.0}])

    def test_auto_backend_keeps_small_tensor_on_cpu(self):
        result = ccr.route_problem(
            _problem(), 8, 9, backend="auto", L=4, iters=1,
            max_sweeps=20, cost_mode="fixed")
        self.assertEqual(result["backend"], "cpu")
        self.assertEqual(result["backend_requested"], "auto")
        self.assertLess(result["backend_work_cells"],
                        result["auto_gpu_floor"])

    def test_auto_service_failure_falls_back_to_deterministic_cpu(self):
        old = os.environ.get("CEC_COORD_SERVICE_SOCKET")
        os.environ["CEC_COORD_SERVICE_SOCKET"] = "/tmp/cec-does-not-exist.sock"
        try:
            result = ccr.route_problem(
                _problem(), 8, 9, backend="auto", auto_gpu_floor=1,
                L=4, iters=1, max_sweeps=20, cost_mode="fixed")
        finally:
            if old is None:
                os.environ.pop("CEC_COORD_SERVICE_SOCKET", None)
            else:
                os.environ["CEC_COORD_SERVICE_SOCKET"] = old
        self.assertEqual(result["backend"], "cpu")
        self.assertEqual(result["route_awareness_service"]["fallback"], "cpu")

    def test_forced_gpu_service_failure_is_not_silently_downgraded(self):
        old = os.environ.get("CEC_COORD_SERVICE_SOCKET")
        os.environ["CEC_COORD_SERVICE_SOCKET"] = "/tmp/cec-does-not-exist.sock"
        try:
            with self.assertRaisesRegex(
                    RuntimeError, "persistent CUDA route service failed"):
                ccr.route_problem(
                    _problem(), 8, 9, backend="gpu", L=4, iters=1,
                    max_sweeps=20, cost_mode="fixed")
        finally:
            if old is None:
                os.environ.pop("CEC_COORD_SERVICE_SOCKET", None)
            else:
                os.environ["CEC_COORD_SERVICE_SOCKET"] = old

    @unittest.skipUnless(ccr._cp is not None, "CuPy unavailable")
    def test_persistent_service_reuses_context_and_exact_result(self):
        try:
            ccr._cp.cuda.Device(0).compute_capability
        except Exception as exc:  # pragma: no cover - hardware-dependent
            self.skipTest("CUDA unavailable: %s" % exc)
        old_socket = os.environ.pop("CEC_COORD_SERVICE_SOCKET", None)
        old_mode = os.environ.get("CEC_COORD_SERVICE")
        os.environ["CEC_COORD_SERVICE"] = "1"
        try:
            state = awareness_service.ensure_service()
            first = ccr.route_problem(
                _problem(), 8, 9, backend="auto", auto_gpu_floor=1,
                L=4, iters=2, max_sweeps=30, cost_mode="fixed",
                connection_priorities=[0, 1, 2],
                protected_priority_max=0)
            second = ccr.route_problem(
                _problem(), 8, 9, backend="auto", auto_gpu_floor=1,
                L=4, iters=2, max_sweeps=30, cost_mode="fixed",
                connection_priorities=[0, 1, 2],
                protected_priority_max=0)
            after = awareness_service.health()
            self.assertEqual(first["paths_by_conn"], second["paths_by_conn"])
            np.testing.assert_array_equal(first["usage"], second["usage"])
            self.assertEqual(first["route_awareness_service"]["pid"],
                             state["pid"])
            self.assertFalse(first["route_awareness_service"]["cache_hit"])
            self.assertTrue(second["route_awareness_service"]["cache_hit"])
            self.assertTrue(first["negotiation"][
                "priority_routing"]["enabled"])
            self.assertEqual(first["negotiation"][
                "priority_routing"]["protected_connection_count"], 1)
            self.assertEqual(after["jobs"], 1)
            self.assertEqual(after["cache_hits"], 1)
        finally:
            awareness_service._shutdown_owned()
            os.environ.pop("CEC_COORD_SERVICE_SOCKET", None)
            if old_socket is not None:
                os.environ["CEC_COORD_SERVICE_SOCKET"] = old_socket
            if old_mode is None:
                os.environ.pop("CEC_COORD_SERVICE", None)
            else:
                os.environ["CEC_COORD_SERVICE"] = old_mode


if __name__ == "__main__":
    unittest.main()
