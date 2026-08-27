#!/usr/bin/env python3
"""Candidate selection must reject via-in-pad before the release choke point."""

import os
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_router  # noqa: E402


def _metrics(objective):
    return types.SimpleNamespace(
        gates_pass=True, detail={}, objective=objective,
        drc=0, unconnected=0, length=0.0, vias=0, tracks=0)


class CandidateViaOnPadGateTest(unittest.TestCase):
    def test_clean_candidate_outranks_lower_objective_via_in_pad(self):
        with tempfile.TemporaryDirectory() as directory:
            bad = os.path.join(directory, "bad.kicad_pcb")
            clean = os.path.join(directory, "clean.kicad_pcb")
            with open(bad, "w", encoding="utf-8") as handle:
                handle.write("bad")
            with open(clean, "w", encoding="utf-8") as handle:
                handle.write("clean")
            candidates = [
                types.SimpleNamespace(ok=True, board=bad),
                types.SimpleNamespace(ok=True, board=clean),
            ]
            bad_m, clean_m = _metrics(1), _metrics(10)
            summaries = [
                {"same": 1, "diff": 0, "allowed_pofv": 0,
                 "same_detail": [{"ref": "U2"}], "diff_detail": []},
                {"same": 0, "diff": 0, "allowed_pofv": 0,
                 "same_detail": [], "diff_detail": []},
            ]
            with mock.patch.object(cec_router.cec_score, "score",
                                   side_effect=[bad_m, clean_m]), \
                    mock.patch.object(cec_router.cec_score, "objective",
                                      side_effect=lambda m, _w: m.objective), \
                    mock.patch("cec_constraints.via_on_pad_summary",
                               side_effect=summaries), \
                    mock.patch("cec_constraints.high_speed_pair_summary",
                               return_value={"applicable": False, "ok": True,
                                             "violations": []}):
                ranked = cec_router._candidate_pool(candidates, None, {})

        self.assertIs(ranked[0][0], candidates[1])
        self.assertFalse(bad_m.gates_pass)
        self.assertEqual(bad_m.detail["via_on_pad"]["same_net"], 1)

    def test_checker_failure_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            board = os.path.join(directory, "candidate.kicad_pcb")
            with open(board, "w", encoding="utf-8") as handle:
                handle.write("candidate")
            candidate = types.SimpleNamespace(ok=True, board=board)
            metrics = _metrics(1)
            with mock.patch.object(cec_router.cec_score, "score",
                                   return_value=metrics), \
                    mock.patch.object(cec_router.cec_score, "objective",
                                      return_value=1), \
                    mock.patch("cec_constraints.via_on_pad_summary",
                               side_effect=RuntimeError("checker unavailable")), \
                    mock.patch("cec_constraints.high_speed_pair_summary",
                               return_value={"applicable": False, "ok": True,
                                             "violations": []}):
                cec_router._candidate_pool([candidate], None, {})

        self.assertFalse(metrics.gates_pass)
        self.assertIn("checker unavailable", metrics.detail["via_on_pad"]["error"])

    def test_physical_pair_quality_breaks_equal_open_count_ties(self):
        with tempfile.TemporaryDirectory() as directory:
            poor = os.path.join(directory, "poor.kicad_pcb")
            sound = os.path.join(directory, "sound.kicad_pcb")
            for path, text in ((poor, "poor"), (sound, "sound")):
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write(text)
            candidates = [types.SimpleNamespace(ok=True, board=poor),
                          types.SimpleNamespace(ok=True, board=sound)]
            poor_m, sound_m = _metrics(1), _metrics(10)
            clean_vop = {"same": 0, "diff": 0, "allowed_pofv": 0,
                         "same_detail": [], "diff_detail": []}
            pair_rows = [
                {"applicable": True, "ok": False,
                 "violations": ["USB skew", "USB coupling"]},
                {"applicable": True, "ok": True, "violations": []},
            ]
            clean_field = {"applicable": True, "ok": True,
                           "blocking_count": 0, "violations": []}
            with mock.patch.object(cec_router.cec_score, "score",
                                   side_effect=[poor_m, sound_m]), \
                    mock.patch.object(cec_router.cec_score, "objective",
                                      side_effect=lambda m, _w: m.objective), \
                    mock.patch("cec_constraints.via_on_pad_summary",
                               return_value=clean_vop), \
                    mock.patch("cec_constraints.high_speed_pair_summary",
                               side_effect=pair_rows), \
                    mock.patch("cec_field_coupling.field_coupling_summary",
                               return_value=clean_field):
                ranked = cec_router._candidate_pool(candidates, None, {})

        self.assertIs(ranked[0][0], candidates[1])
        self.assertFalse(poor_m.gates_pass)
        self.assertEqual(poor_m.detail["external_gate_reasons"],
                         ["USB skew", "USB coupling"])


if __name__ == "__main__":
    unittest.main()
