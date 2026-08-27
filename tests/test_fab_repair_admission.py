#!/usr/bin/env python3
"""Transactional publication tests for fabrication cleanup."""

import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import cec_fab_repair as repair


class FabRepairAdmissionTest(unittest.TestCase):
    def test_safe_slice_wins_and_regressive_full_slice_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            board = os.path.join(td, "board.kicad_pcb")
            with open(board, "w", encoding="utf-8") as handle:
                handle.write("baseline")

            def score(path):
                name = os.path.basename(path)
                row = {"drc": 1, "unconnected": 20,
                       "kelvin_ok": True, "diffpair_ok": True,
                       "route_blocking": 0, "route_advisory": 5,
                       "objective": 4337.0}
                if "copper_cleanup" in name:
                    row.update(route_advisory=3, objective=3837.0)
                elif "full" in name:
                    row.update(route_advisory=3, unconnected=21,
                               objective=3937.0)
                return row

            def mutate(path, **_kwargs):
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write(os.path.basename(path))
                return {"backtracks": 2}

            with mock.patch.object(repair, "_score_isolated", side_effect=score), \
                    mock.patch.object(repair, "_repair_isolated", side_effect=mutate):
                report = repair.repair_admitted(board)

            self.assertTrue(report["adopted"])
            self.assertEqual(report["chosen"], "copper_cleanup")
            self.assertTrue(report["variants"][0]["safe"])
            self.assertFalse(report["variants"][1]["safe"])
            self.assertEqual(report["after"]["unconnected"], 20)
            with open(board, encoding="utf-8") as handle:
                self.assertIn("copper_cleanup", handle.read())


if __name__ == "__main__":
    unittest.main()
