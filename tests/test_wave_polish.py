"""Controlled deep-polish report plumbing is deterministic and spawn-safe."""
import os
import sys
import unittest
import tempfile
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_wave_polish as polish  # noqa: E402


class TestWavePolish(unittest.TestCase):
    def test_external_placed_row_is_absolute_and_preflighted(self):
        with tempfile.TemporaryDirectory() as directory:
            board = os.path.join(directory, "placed.kicad_pcb")
            with open(board, "w", encoding="utf-8") as handle:
                handle.write("fixture")
            with mock.patch.object(polish.wave, "_placement_params",
                                   return_value={"x": 1}), \
                    mock.patch.object(polish.wave, "_future_route_preflight",
                                      return_value={"gate": True}):
                row = polish.external_placed_row(
                    "hub-standard-rev2", board, 86, 74)
        self.assertEqual(row["placed"], os.path.abspath(board))
        self.assertEqual(row["cfg_params"], {"x": 1})
        self.assertEqual(row["future_route"], {"gate": True})

    def test_failed_nets_prefers_explicit_schema(self):
        report = {"best": {"unconn_nets": ["B", "A", "A"],
                           "unconn_signature": [{"nets": ["STALE"]}]}}
        self.assertEqual(polish.failed_nets(report), ["A", "B"])

    def test_failed_nets_falls_back_to_endpoint_signature(self):
        report = {"best": {"unconn_signature": [
            {"nets": ["B"]}, {"nets": ["A", "B"]}]}}
        self.assertEqual(polish.failed_nets(report), ["A", "B"])


if __name__ == "__main__":
    unittest.main()
