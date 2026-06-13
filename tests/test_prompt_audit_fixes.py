#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Host tests for the 2026-06-13 prompt-tier-audit fixes (docs/prompt-audit-2026-06-13/punchlist.md).
# No broker / no container: the T1 intent_manager's broker call is monkeypatched, so these assert the
# PROMPT GROUNDING (P1: manifest refs + sense corridor injected; P2: fence stated) and the GENERATION
# GUARD (P2: fenced-net / fenced-ref intents dropped) deterministically.
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_fullstack as fs            # noqa: E402
import cec_judge_local as jl          # noqa: E402

MANIFEST = {
    "outline_mm": [96.0, 35.0],
    "refs": {
        "U10": {"xy": [10.0, 12.0], "v": "INA181"}, "U11": {"xy": [14.0, 12.0], "v": "INA181"},
        "RS1": {"xy": [20.0, 8.0], "v": "shunt"}, "RS2": {"xy": [24.0, 8.0], "v": "shunt"},
        "U20": {"xy": [21.0, 10.0], "v": "INA238"}, "J1": {"xy": [90.0, 17.0], "v": "RJ45"},
    },
    "net_refs": {"/CAN_H": ["U2", "J1"], "/THRESH": ["U10", "U20"], "/DETC1": ["U10", "U11"]},
}
# fence shape is what cec_fs_actuator.is_fenced consumes: nets (slash-stripped) + refs sets.
FENCE = {"nets": set(), "refs": {"RS1", "RS2", "U20", "U21", "U2"}}


class WpRefs(unittest.TestCase):
    def test_extracts_ref_and_between(self):
        self.assertEqual(fs._wp_refs({"ref": "U1"}), ["U1"])
        self.assertEqual(fs._wp_refs({"between": ["U1", "U2"]}), ["U1", "U2"])
        self.assertEqual(fs._wp_refs({"ref": "U1", "between": ["U2", "U3"]}), ["U1", "U2", "U3"])
        self.assertEqual(fs._wp_refs({}), [])
        self.assertEqual(fs._wp_refs("garbage"), [])


class IntentManagerGrounded(unittest.TestCase):
    def setUp(self):
        self._orig = jl._chat_json
        self.captured = {}

        def stub(system, user, schema, **kw):
            self.captured["user"] = user
            return {"reasoning": "test", "intents": [
                {"net": "/SENSEC1_HI", "layers": ["F.Cu"], "waypoints": [{"ref": "U10"}]},   # fenced NET -> drop
                {"net": "/CAN_H", "layers": ["F.Cu"], "waypoints": [{"ref": "RS1"}]},          # only wp fenced REF -> drop
                {"net": "/THRESH", "layers": ["F.Cu"], "waypoints": [{"ref": "U10"}, {"ref": "RS2"}]},  # RS2 wp removed, keep
                {"net": "/DETC1", "layers": ["B.Cu"], "waypoints": [{"between": ["U10", "U11"]}]},       # keep
            ]}
        jl._chat_json = stub

    def tearDown(self):
        jl._chat_json = self._orig

    def _run(self):
        return fs.intent_manager("eps-8pin", {"contested": ["/CAN_H", "/THRESH"]},
                                 [], None, 1, manifest=MANIFEST, fence=FENCE)

    def test_p1_prompt_injects_manifest_corridor_and_fence(self):
        self._run()
        u = self.captured["user"]
        self.assertIn("BOARD FOOTPRINTS", u)
        self.assertIn("U10", u)                      # a real ref is offered to the seat
        self.assertIn("SENSE CORRIDOR", u)           # P1d corridor from fenced sense refs
        self.assertIn("FENCED", u)                   # P2 fence stated
        self.assertNotIn('"ref": "U2"', u)           # P1b: bare U2/U1 example replaced by real refs

    def test_p2_drops_fenced_net_and_fenced_ref_waypoints(self):
        intents, why, src, dropped = self._run()
        self.assertEqual(src, "model")
        nets = {i["net"] for i in intents}
        self.assertEqual(nets, {"/THRESH", "/DETC1"})            # fenced net + all-fenced-wp intent dropped
        thr = next(i for i in intents if i["net"] == "/THRESH")
        self.assertEqual(thr["waypoints"], [{"ref": "U10"}])     # the RS2 (fenced) waypoint was stripped

    def test_p1c_drops_unknown_net_and_ref_and_records(self):
        def stub(system, user, schema, **kw):
            return {"reasoning": "x", "intents": [
                {"net": "/CAN_H", "layers": ["F.Cu"], "waypoints": [{"ref": "U10"}]},     # valid -> keep
                {"net": "/NOPE", "layers": ["F.Cu"], "waypoints": [{"ref": "U10"}]},       # net not on board -> drop
                {"net": "/THRESH", "layers": ["F.Cu"], "waypoints": [{"ref": "U99"}]},     # ref not on board -> drop
            ]}
        jl._chat_json = stub
        intents, why, src, dropped = fs.intent_manager("eps-8pin", {}, [], None, 1,
                                                       manifest=MANIFEST, fence=FENCE)
        self.assertEqual({i["net"] for i in intents}, {"/CAN_H"})
        self.assertIn("/NOPE", dropped)                          # unknown net recorded for re-prompt
        self.assertIn("U99", dropped)                            # unknown ref recorded for re-prompt

    def test_p1c_reprompts_prior_invalid_tokens(self):
        self._run.__self__  # no-op to keep the stub set in setUp
        fs.intent_manager("eps-8pin", {}, [], None, 2, manifest=MANIFEST, fence=FENCE,
                          prev_dropped=["U5", "/FOO"])
        u = self.captured["user"]
        self.assertIn("INVALID refs/nets", u)
        self.assertIn("U5", u)

    def test_fallback_on_broker_error_returns_prev(self):
        def boom(*a, **k):
            raise RuntimeError("broker down")
        jl._chat_json = boom
        prev = [{"net": "/CAN_H", "layers": ["F.Cu"], "waypoints": [{"ref": "U10"}]}]
        intents, why, src, dropped = fs.intent_manager("eps-8pin", {}, prev, None, 1,
                                                       manifest=MANIFEST, fence=FENCE)
        self.assertEqual(src, "fallback")
        self.assertEqual(intents, prev)


if __name__ == "__main__":
    unittest.main()
