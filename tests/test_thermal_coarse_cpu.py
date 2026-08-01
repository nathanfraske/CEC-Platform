#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Teeth for the COARSE-ON-CPU thermal knobs (owner ask 2026-07-18: wave
# thermals run coarse on the CPU for now). Two halves:
#   1. cec_thermal2d._resolve_backend -- the CEC_THERMAL_BACKEND env override
#      resolves ONLY an 'auto' argument (explicit caller args always win;
#      junk values are ignored).
#   2. cec_fresh_wave._new_best_thermal -- CEC_WAVE_THERMAL_GRID_MM coarsens
#      the stamp's grid and the result carries PROVENANCE (grid_mm/backend,
#      plus a 'coarse' marker whenever the grid is coarser than the 0.4 mm
#      gate default) so a coarse CPU number can never be read as the gate
#      figure. Pure-logic, host-runnable (solve/env injected fakes -- the
#      test_wave_new_best_thermal pattern).
import contextlib
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_thermal2d as T2                                     # noqa: E402
import cec_fresh_wave as W                                     # noqa: E402
import cec_thermal_overlay as TOV                              # noqa: E402


@contextlib.contextmanager
def _env(**kv):
    old = {k: os.environ.get(k) for k in kv}
    try:
        for k, v in kv.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class TestResolveBackend(unittest.TestCase):
    def test_env_resolves_auto(self):
        with _env(CEC_THERMAL_BACKEND="cpu"):
            self.assertEqual(T2._resolve_backend("auto"), "cpu")
        with _env(CEC_THERMAL_BACKEND="gpu"):
            self.assertEqual(T2._resolve_backend("auto"), "gpu")

    def test_explicit_arg_wins_over_env(self):
        with _env(CEC_THERMAL_BACKEND="cpu"):
            self.assertEqual(T2._resolve_backend("gpu"), "gpu")

    def test_no_env_and_junk_env_stay_auto(self):
        with _env(CEC_THERMAL_BACKEND=None):
            self.assertEqual(T2._resolve_backend("auto"), "auto")
        with _env(CEC_THERMAL_BACKEND="quantum"):
            self.assertEqual(T2._resolve_backend("auto"), "auto")


class _Solve:
    def __init__(self):
        self.calls = []

    def __call__(self, path):
        self.calls.append(path)
        return {"ok": True, "dT": 21.0, "max_T": 71.0,
                "gate_dt": 30.0, "cooling": "fake"}


def _null_env(_params):
    return contextlib.nullcontext()


class TestWaveCoarseStamp(unittest.TestCase):
    def _best(self, routed):
        return {"sort_key": [0, 0], "routed": routed, "thermal": None}

    def _run(self, grid_env, backend_env):
        with tempfile.TemporaryDirectory() as d:
            routed = os.path.join(d, "b.kicad_pcb")
            open(routed, "w").write("(kicad_pcb)")
            best = self._best(routed)
            kv = {"CEC_WAVE_THERMAL_GRID_MM": grid_env,
                  "CEC_THERMAL_BACKEND": backend_env}
            with _env(**kv):
                W._new_best_thermal(best, d, {}, solve=_Solve(), env=_null_env)
            return best["thermal"]

    def test_default_grid_stamped_no_coarse_marker(self):
        th = self._run(None, None)
        self.assertEqual(th["grid_mm"], 0.4)
        self.assertEqual(th["backend"], "auto")
        self.assertNotIn("provenance", th)

    def test_coarse_grid_stamped_with_provenance(self):
        th = self._run("0.8", "cpu")
        self.assertEqual(th["grid_mm"], 0.8)
        self.assertEqual(th["backend"], "cpu")
        self.assertIn("coarse", th.get("provenance", ""))

    def test_solver_result_fields_never_clobbered(self):
        # setdefault semantics: a solver that already reports its own grid_mm
        # (future) must not be overwritten by the env stamp
        with tempfile.TemporaryDirectory() as d:
            routed = os.path.join(d, "b.kicad_pcb")
            open(routed, "w").write("(kicad_pcb)")
            best = self._best(routed)

            def solve(_p):
                return {"ok": True, "dT": 5.0, "max_T": 55.0, "grid_mm": 0.2}
            with _env(CEC_WAVE_THERMAL_GRID_MM="0.8"):
                W._new_best_thermal(best, d, {}, solve=solve, env=_null_env)
            self.assertEqual(best["thermal"]["grid_mm"], 0.2)


class TestBoardHint(unittest.TestCase):
    """CEC_THERMAL_BOARD_HINT (2026-07-19): wave variants (plain-dataflow-s1.kicad_pcb)
    carry no board name -> board_thermal_config missed and the new-best stamp
    mirage-FAILED dT~0 on its first live target. The hint resolves the config."""

    def test_variant_filename_misses_without_hint(self):
        nc, stack, ov, cool = TOV.board_thermal_config("/x/plain-dataflow-s1.kicad_pcb")
        self.assertIsNone(nc)
        self.assertIsNone(cool)

    def test_hint_resolves_12vhpwr_config(self):
        os.environ["CEC_THERMAL_BOARD_HINT"] = "12vhpwr-standard"
        try:
            nc, stack, ov, cool = TOV.board_thermal_config("/x/plain-dataflow-s1.kicad_pcb")
        finally:
            os.environ.pop("CEC_THERMAL_BOARD_HINT", None)
        self.assertIsNotNone(nc)                     # per-pin lane currents present
        self.assertIsNotNone(cool)                   # production case-cooling model
        self.assertTrue(any("SENSEP" in k for k in nc))

    def test_wave_board_params_carry_hint(self):
        p = W._board_params("12vhpwr-standard")
        self.assertEqual(p.get("thermal_board_hint"), "12vhpwr-standard")


class TestPruneClassFloor(unittest.TestCase):
    """First-live-firing fix: the raw top-K pruned ALL seat-proposal variants
    (the winning class since 2026-07-14). Every intent class keeps its
    best-by-key variant; CEC_WAVE_PRUNE_CLASS_FLOOR=0 restores raw top-K."""

    def _mk(self, intents, key_of):
        variants, rows = [], []
        for i, iname in enumerate(intents):
            v = (iname, "compact", 0, None)
            variants.append(v)
            rows.append({"label": f"{iname}-compact-s0", "place_key": key_of(iname, i)})
        return variants, rows

    def test_class_floor_keeps_best_of_each_intent(self):
        intents = ["plain", "plain2", "propA", "propB"]
        # plains score best -> raw top-2 would drop BOTH proposal classes
        variants, rows = self._mk(intents, lambda n, i: (0, i) if n.startswith("plain") else (9, i))
        route, pruned = W._prune_variants(variants, rows, 2)
        kept = {v[0] for v in route}
        self.assertEqual(kept, {"plain", "plain2", "propA", "propB"})
        self.assertEqual(len(route), 4)              # top-2 + one floor rep per missing class
        self.assertEqual(len(pruned), 0)

    def test_floor_adds_only_class_best(self):
        intents = ["plain", "propA", "propA2", "propB"]
        variants, rows = self._mk(intents, lambda n, i: (0, 0) if n == "plain" else (9, i))
        # k=1 -> plain kept; floor adds best of propA/propA2/propB classes (all distinct)
        route, pruned = W._prune_variants(variants, rows, 1)
        self.assertEqual({v[0] for v in route}, {"plain", "propA", "propA2", "propB"})

    def test_env_zero_restores_raw_topk(self):
        intents = ["plain", "plain2", "propA", "propB"]
        variants, rows = self._mk(intents, lambda n, i: (0, i) if n.startswith("plain") else (9, i))
        os.environ["CEC_WAVE_PRUNE_CLASS_FLOOR"] = "0"
        try:
            route, pruned = W._prune_variants(variants, rows, 2)
        finally:
            os.environ.pop("CEC_WAVE_PRUNE_CLASS_FLOOR", None)
        self.assertEqual({v[0] for v in route}, {"plain", "plain2"})
        self.assertEqual(len(pruned), 2)

    def test_k_zero_and_small_sets_unchanged(self):
        variants, rows = self._mk(["plain", "propA"], lambda n, i: (i,))
        self.assertEqual(W._prune_variants(variants, rows, 0)[0], variants)
        self.assertEqual(W._prune_variants(variants, rows, 5)[0], variants)


if __name__ == "__main__":
    unittest.main()
