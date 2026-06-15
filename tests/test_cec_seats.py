#!/usr/bin/env python3
"""Host tests for cec_seats.select_seat_backend (the cloud/local residency resolver).
No broker / no container / no pcbnew -- pure policy resolution + precedence + fail-safe."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import cec_seats  # noqa: E402

_ENVS = ("CEC_HUB_SEATS", "CEC_JUDGE", "CEC_OVERNIGHT_HOURS_MIN",
         "CEC_HUB_MANAGER_MODEL", "CEC_HUB_WORKER_MODEL", "CEC_HUB_CLOUD_EFFORT")


class SeatResolver(unittest.TestCase):
    def setUp(self):
        self._saved = {k: os.environ.pop(k, None) for k in _ENVS}
        # Force the no-policy-block path so tests assert the hardcoded fallbacks deterministically.
        cec_seats._policy_block = lambda: {}

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    # ---- duration default (the owner rule) ----
    def test_overnight_long_is_local(self):
        r = cec_seats.select_seat_backend(hours=7, judge=None)
        self.assertEqual(r["backend"], "local")
        self.assertEqual(r["manager_model"], "cec-manager-fast")
        self.assertEqual(r["worker_model"], "cec-worker")
        self.assertIsNone(r["effort"])

    def test_at_threshold_is_local(self):
        self.assertEqual(cec_seats.select_seat_backend(hours=2.0, judge=None)["backend"], "local")

    def test_short_midday_is_cloud(self):
        r = cec_seats.select_seat_backend(hours=1, judge=None)
        self.assertEqual(r["backend"], "cloud")
        self.assertEqual(r["manager_model"], "opus")
        self.assertEqual(r["worker_model"], "sonnet")
        self.assertEqual(r["effort"], "max")        # owner: cloud effort = max in all cases

    def test_local_has_no_effort(self):
        self.assertIsNone(cec_seats.select_seat_backend(hours=7, judge=None)["effort"])

    def test_no_hours_defaults_cloud(self):
        # owner: "defaulting to cloud"
        self.assertEqual(cec_seats.select_seat_backend(hours=None, judge=None)["backend"], "cloud")

    # ---- explicit pins win over duration ----
    def test_explicit_local_wins_short(self):
        self.assertEqual(cec_seats.select_seat_backend(hours=1, judge="local")["backend"], "local")

    def test_explicit_cloud_wins_overnight(self):
        self.assertEqual(cec_seats.select_seat_backend(hours=7, judge="cloud")["backend"], "cloud")

    def test_off_is_deterministic(self):
        r = cec_seats.select_seat_backend(hours=7, judge="off")
        self.assertEqual(r["backend"], "off")
        self.assertIsNone(r["manager_model"])
        self.assertIsNone(r["worker_model"])

    def test_auto_falls_through(self):
        # judge='auto' must NOT pin -> duration decides
        self.assertEqual(cec_seats.select_seat_backend(hours=7, judge="auto")["backend"], "local")

    # ---- env precedence ----
    def test_env_hub_seats_pins(self):
        os.environ["CEC_HUB_SEATS"] = "local"
        self.assertEqual(cec_seats.select_seat_backend(hours=1, judge=None)["backend"], "local")

    def test_env_cec_judge_pins(self):
        os.environ["CEC_JUDGE"] = "cloud"
        self.assertEqual(cec_seats.select_seat_backend(hours=7, judge=None)["backend"], "cloud")

    def test_explicit_flag_beats_env(self):
        os.environ["CEC_HUB_SEATS"] = "local"
        self.assertEqual(cec_seats.select_seat_backend(hours=7, judge="cloud")["backend"], "cloud")

    # ---- threshold + model overrides ----
    def test_threshold_env_override(self):
        os.environ["CEC_OVERNIGHT_HOURS_MIN"] = "5"
        self.assertEqual(cec_seats.select_seat_backend(hours=4, judge=None)["backend"], "cloud")
        self.assertEqual(cec_seats.select_seat_backend(hours=6, judge=None)["backend"], "local")

    def test_per_tier_model_override(self):
        os.environ["CEC_HUB_MANAGER_MODEL"] = "haiku"
        r = cec_seats.select_seat_backend(hours=1, judge=None)   # cloud
        self.assertEqual(r["manager_model"], "haiku")
        self.assertEqual(r["worker_model"], "sonnet")            # unaffected

    # ---- fail-safe: the real policy reader must never raise (cec_policy may be absent/broken) ----
    def test_real_policy_block_never_raises(self):
        import importlib
        importlib.reload(cec_seats)                 # restore the REAL _policy_block (drop the stub)
        try:
            blk = cec_seats._policy_block()         # must swallow any cec_policy error -> {} or dict
            self.assertIsInstance(blk, dict)
            r = cec_seats.select_seat_backend(hours=1, judge=None)
            self.assertIn(r["backend"], ("cloud", "local", "off"))
        finally:
            cec_seats._policy_block = lambda: {}     # re-stub for any later test


if __name__ == "__main__":
    unittest.main()
