#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Host tests for the 2026-06-13 prompt-tier-audit fixes (docs/prompt-audit-2026-06-13/punchlist.md).
# No broker / no container: the T1 intent_manager's broker call is monkeypatched, so these assert the
# PROMPT GROUNDING (P1: manifest refs + sense corridor injected; P2: fence stated) and the GENERATION
# GUARD (P2: fenced-net / fenced-ref intents dropped) deterministically.
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_fullstack as fs            # noqa: E402
import cec_judge_local as jl          # noqa: E402
import cec_verifier                   # noqa: E402

MANIFEST = {
    "outline_mm": [96.0, 35.0],
    "refs": {
        "U10": {"xy": [10.0, 12.0], "v": "INA181"}, "U11": {"xy": [14.0, 12.0], "v": "INA181"},
        "RS1": {"xy": [20.0, 8.0], "v": "shunt"}, "RS2": {"xy": [24.0, 8.0], "v": "shunt"},
        "U20": {"xy": [21.0, 10.0], "v": "INA238"}, "J1": {"xy": [90.0, 17.0], "v": "RJ45"},
    },
    "net_refs": {"/CAN_H": ["U2", "J1"], "/THRESH": ["U10", "U20"], "/DETC1": ["U10", "U11"],
                 "/SENSEC1_HI": ["RS1", "U20"]},     # a sense net so the M1 corridor block is produced
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

    def test_p1c_net_membership_is_slash_tolerant(self):
        # pcbnew mixes forms: bare GND/+3V3, slash-prefixed /CAN_H. The model may add/drop a slash.
        manifest = {"refs": {"U10": {"xy": [1, 1], "v": "x"}},
                    "net_refs": {"GND": ["U10"], "+3V3": ["U10"], "/CAN_H": ["U10"]}}

        def stub(system, user, schema, **kw):
            return {"reasoning": "x", "intents": [
                {"net": "/GND", "layers": ["F.Cu"], "waypoints": [{"ref": "U10"}]},    # slash added vs bare key -> keep
                {"net": "+3V3", "layers": ["F.Cu"], "waypoints": [{"ref": "U10"}]},    # bare matches bare -> keep
                {"net": "CAN_H", "layers": ["F.Cu"], "waypoints": [{"ref": "U10"}]},   # bare vs slash key -> keep
                {"net": "/NOPE", "layers": ["F.Cu"], "waypoints": [{"ref": "U10"}]},   # genuinely unknown -> drop
            ]}
        jl._chat_json = stub
        intents, why, src, dropped = fs.intent_manager("eps-8pin", {}, [], None, 1,
                                                       manifest=manifest, fence=FENCE)
        self.assertEqual({i["net"] for i in intents}, {"/GND", "+3V3", "CAN_H"})
        self.assertIn("/NOPE", dropped)

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


class P4SpecExcerpt(unittest.TestCase):
    """P4 fix: the locked-decision spine + fence + unratified relabel must reach the CL24
    spec-conformance charter even though _slice_spec truncates the (large) rules_excerpt."""

    def test_spine_leads_so_it_survives_old_truncation(self):
        big_corpus = "RATIFIED CORPUS (...):\n" + ("- [x] filler corpus entry\n" * 600)
        self.assertGreater(len(big_corpus), 9000)            # bigger than the old 4000 cap
        ex = fs._spec_rules_excerpt(big_corpus, fs.LOCKED_DECISIONS_BRIEF,
                                    {"nets": set(), "refs": {"RS1", "RS2"}}, [])
        head = ex[:4000]                                     # what the OLD cap would have kept
        self.assertIn("LOCKED DECISIONS", head)             # spine survives even the old cap now
        self.assertIn("FENCE (never steer)", head)
        self.assertIn("IN-RUN STANDING RULES (unratified", head)
        self.assertIn("RS1", head)
        self.assertIn("filler corpus entry", ex)            # corpus still present, after the spine

    def test_slice_spec_surfaces_the_spine(self):
        ex = fs._spec_rules_excerpt("X" * 9000, fs.LOCKED_DECISIONS_BRIEF,
                                    {"nets": set(), "refs": {"RS1"}}, ["some-in-run-rule"])
        out = cec_verifier._slice_spec({"issue": "test"}, {"rules_excerpt": ex})
        self.assertIn("LOCKED DECISIONS", out)
        self.assertIn("FENCE (never steer)", out)
        self.assertIn("IN-RUN STANDING RULES (unratified", out)
        self.assertIn("some-in-run-rule", out)              # the relabeled standing rule reaches the seat
        self.assertIn("pin allocation pin1=VCC", out)       # a specific locked decision reaches the seat


class MergeAuditFixes(unittest.TestCase):
    """M1/M3/M4/M5 from the PR #56 merge audit."""

    # ---- M1: SENSE CORRIDOR derived from sense refs only, excludes the CAN transceiver ----
    def test_m1_corridor_excludes_can_transceiver(self):
        manifest = {
            "outline_mm": [96, 35],
            "refs": {"RS1": {"xy": [20, 8], "v": "shunt"}, "U20": {"xy": [21, 10], "v": "INA238"},
                     "U2": {"xy": [60, 17], "v": "TJA1051"}, "U10": {"xy": [10, 12], "v": "x"}},
            "net_refs": {"/SENSEC1_HI": ["RS1", "U20"], "/CAN_H": ["U2"], "/THRESH": ["U10"]},
        }
        fence = {"nets": set(), "refs": {"RS1", "U20", "U2"}}      # U2 is fenced but is the CAN xcvr
        cap = {}

        def stub(system, user, schema, **kw):
            cap["user"] = user
            return {"reasoning": "x", "intents": []}
        orig = jl._chat_json
        jl._chat_json = stub
        try:
            fs.intent_manager("eps-8pin", {}, [], None, 1, manifest=manifest, fence=fence)
        finally:
            jl._chat_json = orig
        u = cap["user"]
        corridor = next(ln for ln in u.splitlines() if "SENSE CORRIDOR" in ln)
        self.assertIn("'RS1'", corridor)
        self.assertIn("'U20'", corridor)
        self.assertNotIn("'U2'", corridor)                        # the CAN xcvr is NOT in the corridor
        self.assertIn("FENCED", u)                                # U2 still appears in the fence line

    # ---- M3: board_manifest parses the in-container output; fail-safe to {} ----
    def test_m3_board_manifest_parse_and_failsafe(self):
        payload = {"outline_mm": [96.0, 35.0], "refs": {"U1": {"xy": [1, 2], "v": "ESP32"}},
                   "net_refs": {"GND": ["U1"]}}
        orig = fs._exec_py
        fs._exec_py = lambda code, timeout=120: (0, "noise\nMANIFEST_JSON=" + json.dumps(payload) + "\n")
        try:
            self.assertEqual(fs.board_manifest("eps-8pin"), payload)
        finally:
            fs._exec_py = orig

        def boom(code, timeout=120):
            raise RuntimeError("container down")
        fs._exec_py = boom
        try:
            self.assertEqual(fs.board_manifest("eps-8pin"), {})    # fail-safe, never raises
        finally:
            fs._exec_py = orig

    # ---- M4: lane-gated carry-forward never leaks augmented state into a control round ----
    def test_m4_lane_carry_helper(self):
        self.assertEqual(fs._lane_carry("augmented", ["a"], ["seed"]), ["a"])
        self.assertEqual(fs._lane_carry("control", ["a"], ["seed"]), ["seed"])
        self.assertEqual(fs._lane_carry("control", ["a"], ()), ())

    def test_m4_carry_forward_invariant(self):
        seed = ["S"]
        intents_aug = seed
        model_out = {1: ["A1"], 2: ["A2"], 3: ["C3"], 4: ["A4"]}
        seen = {}
        for rnd, lane in [(1, "augmented"), (2, "augmented"), (3, "control"), (4, "augmented")]:
            seen[rnd] = fs._lane_carry(lane, intents_aug, seed)   # what T1 sees as prev_intents
            if lane == "augmented":                               # run()'s update rule (augmented only)
                intents_aug = list(model_out[rnd])
        self.assertEqual(seen[1], seed)                           # first augmented: the seed
        self.assertEqual(seen[2], ["A1"])                         # carries the prior augmented plan
        self.assertEqual(seen[3], seed)                           # CONTROL: the seed, NOT ["A2"]
        self.assertEqual(seen[4], ["A2"])                         # augmented resumes from last augmented

    # ---- M5: promoted_corpus_brief in-family scoping + relevance-ordered truncation + cache key ----
    def test_m5_in_family_only_drops_off_family(self):
        full = fs.promoted_corpus_brief("eps-8pin")
        gen = fs.promoted_corpus_brief("eps-8pin", in_family_only=True)
        self.assertTrue(full.startswith("RATIFIED CORPUS"))
        self.assertTrue(gen.startswith("RATIFIED CORPUS"))
        self.assertNotIn("[scope:", gen)                          # off-family entries dropped for gen seats
        if "[scope:" in full:                                     # off-family entries exist in the corpus
            self.assertLess(len(gen), len(full))
        self.assertIsNot(full, gen)                               # distinct cache entries
        self.assertIs(full, fs.promoted_corpus_brief("eps-8pin"))  # same key -> cached object

    def test_m5_truncation_drops_off_family_tail_first(self):
        trunc = fs.promoted_corpus_brief("eps-8pin", max_chars=400)   # max_chars in cache key (M5)
        self.assertIn("brief truncated", trunc)                       # truncation fired
        head = trunc[:trunc.index("brief truncated")]
        self.assertNotIn("[scope:", head)                            # in-family ordered first -> head is in-family


if __name__ == "__main__":
    unittest.main()
