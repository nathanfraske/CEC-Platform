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


@unittest.skipUnless(HAVE_PCBNEW, "pcbnew required (real compile)")
class TestPlaceVariantSmoke(unittest.TestCase):
    def test_compile_only_produces_key(self):
        r = W._place_variant("eps-8pin", 96.0, 37.0, "plain", "compact", 0)
        self.assertIsNone(r.get("error"), r.get("error"))
        self.assertEqual(r["label"], "plain-compact-s0")
        self.assertIsInstance(r["place_key"], list)
        self.assertGreaterEqual(len(r["place_key"]), 3)
        self.assertIn("residual", r)


if __name__ == "__main__":
    unittest.main()
