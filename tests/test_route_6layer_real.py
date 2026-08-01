#!/usr/bin/env python3
"""Explicit opt-in end-to-end proof that Freerouting can use In3.Cu."""

import importlib.util
import os
import tempfile
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROBE_PATH = os.path.join(
    ROOT, "scripts", "probes", "route_6layer_smoke.py")

try:
    import pcbnew  # noqa: F401
    HAVE_PCBNEW = True
except ImportError:
    HAVE_PCBNEW = False


@unittest.skipUnless(HAVE_PCBNEW and os.environ.get("CEC_RUN_REAL_ROUTER") == "1",
                     "set CEC_RUN_REAL_ROUTER=1 for the real Java router smoke")
class RealSixLayerRouteTest(unittest.TestCase):
    def test_forced_route_uses_in3_and_imports_connected(self):
        spec = importlib.util.spec_from_file_location(
            "route_6layer_smoke", PROBE_PATH)
        probe = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(probe)
        with tempfile.TemporaryDirectory() as directory:
            result = probe.run(directory, passes=4, opt_time=5, timeout=300)
        self.assertTrue(result["pass"], result)
        self.assertEqual(result["signal_tracks_by_layer"], {"In3.Cu": 1})
        self.assertEqual(result["unconnected"], 0)
        self.assertEqual(result["dsn_layer_types"]["In1.Cu"], "power")
        self.assertEqual(result["dsn_layer_types"]["In4.Cu"], "power")


if __name__ == "__main__":
    unittest.main()
