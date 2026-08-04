#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Teeth for the wave PRUNE -> ADJUDICATE wiring (roadmap throughput lever 1,
# owner GO 2026-07-17): the decision function is pure and unit-tested here;
# _place_variant gets a real-compile smoke (pcbnew-gated). Fidelity contract
# under test: top-K by cheap key routes, placement ERRORS route anyway
# (fail-open), pruned variants are RETURNED for the report (no silent caps),
# CEC_WAVE_PRUNE=0 / small grids route everything.
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_fresh_wave as W                                     # noqa: E402

try:
    import pcbnew                                              # noqa: F401
    HAVE_PCBNEW = True
except ImportError:
    HAVE_PCBNEW = False


def _v(iname, strat, seed):
    return (iname, strat, seed, None)


def _row(iname, strat, seed, key):
    return {"label": f"{iname}-{strat}-s{seed}", "iname": iname, "strat": strat,
            "seed": seed, "place_key": key}


class TestPruneDecision(unittest.TestCase):
    def setUp(self):
        # These fixtures give every variant a UNIQUE intent class, so the
        # intent-class floor (2026-07-19: the raw top-K's first live firing
        # pruned all 12 seat proposals -- the winning class) would keep all
        # of them. Pin the RAW top-K arm here; the floor has its own teeth
        # in tests/test_thermal_coarse_cpu.py::TestPruneClassFloor.
        os.environ["CEC_WAVE_PRUNE_CLASS_FLOOR"] = "0"
        self.addCleanup(os.environ.pop, "CEC_WAVE_PRUNE_CLASS_FLOOR", None)
        self.variants = [_v("a", "dataflow", 0), _v("b", "dataflow", 0),
                         _v("c", "compact", 1), _v("d", "compact", 1)]
        self.rows = [_row("a", "dataflow", 0, [0, 3.0, 5.0, 100.0]),
                     _row("b", "dataflow", 0, [1, 0.0, 2.0, 90.0]),
                     _row("c", "compact", 1, [0, 1.0, 3.0, 80.0]),
                     _row("d", "compact", 1, [2, 9.0, 9.0, 999.0])]

    def test_top_k_by_key_routes(self):
        route, pruned = W._prune_variants(self.variants, self.rows, 2)
        labels = [f"{v[0]}-{v[1]}-s{v[2]}" for v in route]
        self.assertEqual(labels, ["c-compact-s1", "a-dataflow-s0"])   # keys (0,1..) < (0,3..)
        self.assertEqual({r["label"] for r in pruned},
                         {"b-dataflow-s0", "d-compact-s1"})
        self.assertTrue(all(r.get("pruned") for r in pruned))

    def test_k_zero_disables(self):
        route, pruned = W._prune_variants(self.variants, self.rows, 0)
        self.assertEqual(route, self.variants)
        self.assertEqual(pruned, [])

    def test_small_grid_routes_all(self):
        route, pruned = W._prune_variants(self.variants, self.rows, 4)
        self.assertEqual(route, self.variants)
        self.assertEqual(pruned, [])

    def test_place_error_routes_fail_open(self):
        rows = list(self.rows)
        rows[0] = {"label": "a-dataflow-s0", "iname": "a", "strat": "dataflow",
                   "seed": 0, "place_key": None, "error": "Boom: compile died"}
        route, pruned = W._prune_variants(self.variants, rows, 2)
        labels = {f"{v[0]}-{v[1]}-s{v[2]}" for v in route}
        self.assertIn("a-dataflow-s0", labels,
                      "an ERRORED placement must never be silently pruned")
        self.assertIn("c-compact-s1", labels)                 # best real key still kept
        self.assertEqual(len(route), 2)

    def test_missing_row_routes_fail_open(self):
        rows = [r for r in self.rows if r["iname"] != "b"]
        route, _ = W._prune_variants(self.variants, rows, 2)
        labels = {f"{v[0]}-{v[1]}-s{v[2]}" for v in route}
        self.assertIn("b-dataflow-s0", labels)

    def test_deterministic_tie_break(self):
        rows = [_row(i, "dataflow", 0, [0, 1.0, 1.0, 50.0]) for i in ("a", "b", "c", "d")]
        variants = [_v(i, "dataflow", 0) for i in ("a", "b", "c", "d")]
        r1, _ = W._prune_variants(variants, rows, 2)
        r2, _ = W._prune_variants(list(reversed(variants)), rows, 2)
        self.assertEqual({f"{v[0]}" for v in r1}, {f"{v[0]}" for v in r2},
                         "equal keys tie-break by label, order-independent")


class TestPublishedRescore(unittest.TestCase):
    def test_saved_artifact_metrics_replace_pre_repair_grade(self):
        best = {
            "gate": False, "gates_pass": False, "kelvin_ok": True,
            "diffpair_ok": True, "drc": 29, "unconnected": 95,
            "sort_key": (1, 0, 2, 0, 95, 29, 1e6),
            "foreign": {"tracks": 0, "vias": 0},
            "thermal": {"ok": False, "dT": None},
            "rails": {"total": 4, "laid": 4},
            "gate_terms": {"gates_pass": False, "routing_complete": False,
                           "foreign_ok": True, "thermal_ok": False},
            "reasons": [],
        }
        metrics = SimpleNamespace(
            gates_pass=False, kelvin_ok=True, diffpair_ok=True, drc=31,
            unconnected=97, drc_types={"tracks_crossing": 1}, vias=6,
            tracks=12, length=42.25,
            detail={"unconn_nets": ["GND", "/UART_TX"]},
        )
        with mock.patch.object(W.cec_score.Rules, "from_board", return_value=object()), \
                mock.patch.object(W.cec_score, "score", return_value=metrics), \
                mock.patch.object(W.csp, "_classify_unconnected",
                                  return_value=(["GND"], ["/UART_TX"])):
            W._rescore_published(best, __file__)

        self.assertEqual(best["drc"], 31)
        self.assertEqual(best["unconnected"], 97)
        self.assertEqual(best["drc_types"], {"tracks_crossing": 1})
        self.assertEqual(best["unconn_critical"], ["GND"])
        self.assertEqual(best["sort_key"], (1, 0, 1, 0, 97, 31, 1e6))
        self.assertFalse(best["gate"])
        self.assertIn("published-artifact rescore", best["reasons"][-1])

    def test_missing_complete_gate_record_fails_closed(self):
        best = {"gate": True, "foreign": {}, "thermal": {}, "reasons": []}
        metrics = SimpleNamespace(
            gates_pass=True, kelvin_ok=True, diffpair_ok=True, drc=0,
            unconnected=0, drc_types={}, vias=0, tracks=0, length=0.0,
            detail={"unconn_nets": []},
        )
        with mock.patch.object(W.cec_score.Rules, "from_board", return_value=object()), \
                mock.patch.object(W.cec_score, "score", return_value=metrics), \
                mock.patch.object(W.csp, "_classify_unconnected", return_value=([], [])):
            W._rescore_published(best, __file__)
        self.assertFalse(best["gate"], "copper-only score cannot waive missing oracle terms")


@unittest.skipUnless(HAVE_PCBNEW, "pcbnew required (real compile)")
class TestPlaceVariantSmoke(unittest.TestCase):
    def test_compile_only_produces_key(self):
        r = W._place_variant("eps-8pin-rev3", 96.0, 40.0, "plain", "compact", 0)
        self.assertIsNone(r.get("error"), r.get("error"))
        self.assertEqual(r["label"], "plain-compact-s0")
        self.assertIsInstance(r["place_key"], list)
        self.assertGreaterEqual(len(r["place_key"]), 3)
        self.assertIn("residual", r)


if __name__ == "__main__":
    unittest.main()
