import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import cec_synth_pipeline as synth


class LocalPiPowerReplanTests(unittest.TestCase):
    def _frozen_state(self):
        return {
            "placement_scope": "complete",
            "frozen_nets": ["PWR"],
            "pours": [{"net": "PWR", "layer": "F.Cu",
                       "polygon": [[0, 0], [4, 0], [4, 4], [0, 4]]}],
            "corridors": [{"net": "PWR", "layer": "F.Cu",
                           "x0": 0, "y0": 0, "x1": 4, "y1": 4,
                           "polygon": [[0, 0], [4, 0], [4, 4], [0, 4]]}],
            "vias": [{"net": "PWR", "x_mm": 1.0, "y_mm": 1.0}],
        }

    def test_local_clip_preserves_vias_and_binds_admitted_state(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            board = temp / "board.kicad_pcb"
            board.write_text("board", encoding="utf-8")
            previous_state = temp / "old-power.json"
            previous_state.write_text(json.dumps(self._frozen_state()))
            clipped_pours = [{"net": "PWR", "layer": "F.Cu",
                              "polygon": [[0, 0], [3, 0], [3, 4], [0, 4]]}]
            clipped_corridors = [{
                "net": "PWR", "layer": "F.Cu",
                "x0": 0, "y0": 0, "x1": 3, "y1": 4,
                "polygon": [[0, 0], [3, 0], [3, 4], [0, 4]],
            }]
            clip_calls = []

            def clip(_board, rows, clearance_mm):
                clip_calls.append((list(rows), clearance_mm))
                return ((clipped_pours if len(clip_calls) == 1
                         else clipped_corridors), 1)

            def compile_power(_source, _pours, state_path, preview_path):
                state = json.loads(Path(state_path).read_text())
                state["exact_admission"] = {"passed": True}
                Path(state_path).write_text(json.dumps(state))
                Path(preview_path).write_text("preview")
                return state

            modules = {
                "cec_fr": SimpleNamespace(
                    _pourfirst_state=lambda: self._frozen_state()),
                "cec_pour_clearance": SimpleNamespace(
                    inspect_file=lambda _path: {
                        "status": "ok", "n_tracks": 0, "n_vias": 0}),
                "cec_slab_pour": SimpleNamespace(
                    _clip_pours_around_foreign_copper=clip,
                    prune_unseeded_pour_components=lambda _b, rows, _vias:
                        (rows, {"removed": 0, "detail": []}),
                    rectilinear_rows_to_rectangles=lambda rows: rows),
                "pcbnew": SimpleNamespace(LoadBoard=lambda _path: object()),
            }
            previous_env = os.environ.get("CEC_POURFIRST_STATE")
            os.environ["CEC_POURFIRST_STATE"] = str(previous_state)
            try:
                with mock.patch.dict(sys.modules, modules), mock.patch.object(
                        synth, "_compile_post_priority_power_state",
                        side_effect=compile_power), mock.patch.object(
                            synth, "read_placement",
                            return_value=SimpleNamespace(
                                P={"U1": (1.0, 2.0, 90.0)})):
                    report = (
                        synth._reconcile_frozen_power_authority_around_locked_prefix(
                            board, [{"net": "PWR"}], temp,
                            label="local-pi"))

                self.assertTrue(report["ok"])
                self.assertEqual(report["vias"], 1)
                self.assertEqual(report["strategy"],
                                 "preserve_current_vias_clip_vector_sources")
                self.assertEqual(len(clip_calls), 2)
                self.assertEqual(os.environ["CEC_POURFIRST_STATE"],
                                 report["state"])
                state = json.loads(Path(report["state"]).read_text())
                self.assertEqual(state["vias"], self._frozen_state()["vias"])
                self.assertEqual(state["corridors"], clipped_corridors)
            finally:
                if previous_env is None:
                    os.environ.pop("CEC_POURFIRST_STATE", None)
                else:
                    os.environ["CEC_POURFIRST_STATE"] = previous_env

    def test_failed_local_clip_restores_original_authority(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            board = temp / "board.kicad_pcb"
            board.write_text("board", encoding="utf-8")
            previous_state = temp / "old-power.json"
            previous_state.write_text(json.dumps(self._frozen_state()))
            modules = {
                "cec_fr": SimpleNamespace(
                    _pourfirst_state=lambda: self._frozen_state()),
                "cec_pour_clearance": SimpleNamespace(),
                "cec_slab_pour": SimpleNamespace(
                    _clip_pours_around_foreign_copper=lambda _b, rows, **_kw:
                        (list(rows), 0),
                    prune_unseeded_pour_components=lambda _b, rows, _vias:
                        (rows, {"removed": 0, "detail": []}),
                    rectilinear_rows_to_rectangles=lambda rows: rows),
                "pcbnew": SimpleNamespace(LoadBoard=lambda _path: object()),
            }
            previous_env = os.environ.get("CEC_POURFIRST_STATE")
            os.environ["CEC_POURFIRST_STATE"] = str(previous_state)
            try:
                with mock.patch.dict(sys.modules, modules), mock.patch.object(
                        synth, "_compile_post_priority_power_state",
                        side_effect=RuntimeError("exact refusal")), \
                        mock.patch.object(
                            synth, "read_placement",
                            return_value=SimpleNamespace(P={})):
                    with self.assertRaisesRegex(RuntimeError,
                                                "exact refusal"):
                        synth._reconcile_frozen_power_authority_around_locked_prefix(
                            board, [], temp)
                self.assertEqual(os.environ["CEC_POURFIRST_STATE"],
                                 str(previous_state))
            finally:
                if previous_env is None:
                    os.environ.pop("CEC_POURFIRST_STATE", None)
                else:
                    os.environ["CEC_POURFIRST_STATE"] = previous_env

    def test_replan_replaces_stale_state_and_binds_complete_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            board = temp / "board.kicad_pcb"
            board.write_text("board", encoding="utf-8")
            observed = {}

            def compile_power(source, pours, state_path, preview_path):
                observed["state_during_compile"] = os.environ.get(
                    "CEC_POURFIRST_STATE")
                Path(preview_path).write_text("preview", encoding="utf-8")
                return {
                    "frozen_nets": ["PWR"],
                    "pours": [{"net": "PWR"}],
                    "vias": [],
                    "corridors": [{"net": "PWR"}],
                    "exact_admission": {"passed": True},
                }

            previous = os.environ.get("CEC_POURFIRST_STATE")
            os.environ["CEC_POURFIRST_STATE"] = "stale-state.json"
            try:
                with mock.patch.object(
                        synth, "_compile_post_priority_power_state",
                        side_effect=compile_power), mock.patch.object(
                            synth, "read_placement",
                            return_value=SimpleNamespace(
                                P={"U1": (1.0, 2.0, 90.0)})):
                    report = synth._replan_power_authority_around_locked_prefix(
                        board, [{"net": "PWR"}], temp, label="local-pi")

                self.assertIsNone(observed["state_during_compile"])
                self.assertTrue(report["ok"])
                self.assertEqual(report["previous_state"],
                                 "stale-state.json")
                self.assertEqual(os.environ["CEC_POURFIRST_STATE"],
                                 report["state"])
                state = json.loads(Path(report["state"]).read_text())
                self.assertEqual(state["placement_scope"], "complete")
                self.assertEqual(state["placements"], {
                    "U1": [1.0, 2.0, 90.0],
                })
                self.assertEqual(state["replaces_state"],
                                 "stale-state.json")
            finally:
                if previous is None:
                    os.environ.pop("CEC_POURFIRST_STATE", None)
                else:
                    os.environ["CEC_POURFIRST_STATE"] = previous

    def test_failed_replan_restores_previous_state(self):
        with tempfile.TemporaryDirectory() as temp:
            board = Path(temp) / "board.kicad_pcb"
            board.write_text("board", encoding="utf-8")
            previous = os.environ.get("CEC_POURFIRST_STATE")
            os.environ["CEC_POURFIRST_STATE"] = "stale-state.json"
            try:
                with mock.patch.object(
                        synth, "_compile_post_priority_power_state",
                        side_effect=RuntimeError("no path")):
                    with self.assertRaisesRegex(RuntimeError, "no path"):
                        synth._replan_power_authority_around_locked_prefix(
                            board, [], temp, label="local-pi")
                self.assertEqual(os.environ["CEC_POURFIRST_STATE"],
                                 "stale-state.json")
            finally:
                if previous is None:
                    os.environ.pop("CEC_POURFIRST_STATE", None)
                else:
                    os.environ["CEC_POURFIRST_STATE"] = previous


if __name__ == "__main__":
    unittest.main()
