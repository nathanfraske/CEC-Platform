#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Unit tests for the CL-11 golden-fixture runner (scripts/cec_golden_fixtures.py).
# Host-runnable: manifest integrity + the net-scoped counter; the full invariant
# verification runs in CI / the container (python3 scripts/cec_golden_fixtures.py).
#
#   python3 -m unittest tests.test_golden_fixtures -v
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_golden_fixtures as GF  # noqa: E402  (stdlib-only at import time)


class TestManifest(unittest.TestCase):
    def setUp(self):
        self.m = GF.load_manifest()

    def test_four_audit_states_present(self):
        ids = {f["id"] for f in self.m["fixtures"]}
        self.assertEqual(ids, {"12vhpwr-pre-lanevias", "12vhpwr-post-lanevias",
                               "hub-pre-tps2121", "hub-post-tps2121"})

    def test_fixture_files_exist(self):
        for fx in self.m["fixtures"]:
            self.assertTrue(os.path.isfile(GF.fixture_board(fx)),
                            f"{fx['id']}: frozen file missing")

    def test_expected_fail_marker_is_visible_not_silent(self):
        pre = next(f for f in self.m["fixtures"] if f["id"] == "hub-pre-tps2121")
        self.assertIn("Class B", pre["expected_fail"])  # names the missing entry
        self.assertNotIn("invariants", pre)             # no vacuous invariant masking the gap

    def test_known_bad_asserts_fire_and_band(self):
        pre = next(f for f in self.m["fixtures"] if f["id"] == "12vhpwr-pre-lanevias")
        modes = {i["assert"] for i in pre["invariants"]}
        self.assertIn("fires", modes)
        scoped = next(i for i in pre["invariants"] if i["assert"] == "net_scoped")
        self.assertGreaterEqual(scoped["min"], 100)     # the lane-via band floor

    def test_known_good_asserts_zero_vias(self):
        post = next(f for f in self.m["fixtures"] if f["id"] == "12vhpwr-post-lanevias")
        scoped = next(i for i in post["invariants"] if i["assert"] == "net_scoped")
        self.assertEqual((scoped["min"], scoped["max"]), (0, 0))


class TestNetScopedCounter(unittest.TestCase):
    PAYLOAD = [
        {"net": "/SENSEP1_HI", "class": "Power12V", "kind": "via_dia", "count": 10},
        {"net": "/SENSEP1_HI", "class": "Power12V", "kind": "via_drill", "count": 10},
        {"net": "/SENSEP2_LO", "class": "Power12V", "kind": "track", "count": 5},
        {"net": "GND", "class": "GND", "kind": "via_dia", "count": 7},
    ]

    def test_scoped_to_lane_vias(self):
        n = GF._net_scoped_counts(self.PAYLOAD, ["/SENSEP*"], ["via_dia", "via_drill"])
        self.assertEqual(n, 20)  # track kind and GND net excluded

    def test_wildcard_all(self):
        n = GF._net_scoped_counts(self.PAYLOAD, ["*"], ["via_dia", "via_drill"])
        self.assertEqual(n, 27)

    def test_empty_payload(self):
        self.assertEqual(GF._net_scoped_counts(None, ["*"], ["via_dia"]), 0)


if __name__ == "__main__":
    unittest.main()
