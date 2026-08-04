#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""A scored routing wave keeps one durable dashboard-ready best candidate."""

import json
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_router  # noqa: E402


class TestRouteProgressSnapshot(unittest.TestCase):
    def test_best_candidate_and_metrics_are_overwritten_durably(self):
        metrics = SimpleNamespace(
            drc=3, unconnected=4, tracks=5, vias=6, length=7.0,
            kelvin_ok=True, diffpair_ok=False, cu12v=8.0, balance=0.5,
            gates_pass=False, drc_types={"clearance": 3}, plane_signal_mm=0.0)
        with tempfile.TemporaryDirectory() as td:
            source = os.path.join(td, "candidate.kicad_pcb")
            with open(source, "w", encoding="utf-8") as handle:
                handle.write("candidate-v1")
            spec = SimpleNamespace(out=os.path.join(td, "route", "hub-routed.kicad_pcb"))
            region = SimpleNamespace(name="all")
            candidate = SimpleNamespace(board=source)

            result = cec_router._persist_iteration_best(
                spec, region, 2, (candidate, metrics), [(candidate, metrics)])

            self.assertTrue(os.path.isfile(result))
            with open(result, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "candidate-v1")
            report = result[:-len(".kicad_pcb")] + ".json"
            with open(report, encoding="utf-8") as handle:
                data = json.load(handle)
            self.assertEqual((data["region"], data["iteration"]), ("all", 2))
            self.assertEqual(data["chosen"]["drc_types"], {"clearance": 3})
            self.assertEqual(len(data["candidates"]), 1)


if __name__ == "__main__":
    unittest.main()
