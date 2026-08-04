import os
import shutil
import sys
import unittest
from unittest import mock


SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts")
sys.path.insert(0, SCRIPTS)

import cec_staged_fr as staged  # noqa: E402


class StagedRouterCleanupTests(unittest.TestCase):
    def test_default_run_removes_work_tree_after_copy_out(self):
        seen = {}

        def fake_route(_placed, _out, **kwargs):
            seen["work"] = kwargs["work"]
            self.assertTrue(os.path.isdir(seen["work"]))
            return {"tiers": [], "work": seen["work"], "total_wall_s": 0.0}

        with mock.patch.dict(os.environ,
                             {"CEC_STAGED_FR_KEEP_INTERMEDIATES": "0"}), \
             mock.patch.object(staged, "_route_tiered_in_work",
                               side_effect=fake_route):
            report = staged.route_tiered("in.kicad_pcb", "out.kicad_pcb")

        self.assertIsNone(report["work"])
        self.assertFalse(os.path.exists(seen["work"]))

    def test_default_run_removes_work_tree_on_failure(self):
        seen = {}

        def fail(_placed, _out, **kwargs):
            seen["work"] = kwargs["work"]
            raise RuntimeError("tier failed")

        with mock.patch.dict(os.environ,
                             {"CEC_STAGED_FR_KEEP_INTERMEDIATES": "0"}), \
             mock.patch.object(staged, "_route_tiered_in_work", side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, "tier failed"):
                staged.route_tiered("in.kicad_pcb", "out.kicad_pcb")

        self.assertFalse(os.path.exists(seen["work"]))

    def test_debug_flag_retains_work_tree(self):
        seen = {}

        def fake_route(_placed, _out, **kwargs):
            seen["work"] = kwargs["work"]
            return {"tiers": [], "work": seen["work"], "total_wall_s": 0.0}

        with mock.patch.dict(os.environ,
                             {"CEC_STAGED_FR_KEEP_INTERMEDIATES": "1"}), \
             mock.patch.object(staged, "_route_tiered_in_work",
                               side_effect=fake_route):
            report = staged.route_tiered("in.kicad_pcb", "out.kicad_pcb")

        self.assertEqual(report["work"], seen["work"])
        self.assertTrue(os.path.isdir(seen["work"]))
        shutil.rmtree(seen["work"])


if __name__ == "__main__":
    unittest.main()
