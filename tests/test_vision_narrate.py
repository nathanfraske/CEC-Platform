"""Host tests for the re-roled VLM narration pass (owner ruling 2026-06-11). No GPU: a stub chat
captures the prompt and returns a schema-valid dict. Verifies the seat is NARRATION+ANOMALY only --
never fed the numeric facts / predetermining heuristic, and never emits a verdict."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import cec_vision_narrate as vn  # noqa: E402


class StubChat:
    def __init__(self):
        self.last_text = None

    def __call__(self, model, text, png, schema=None, max_tokens=0, timeout=0, ctx=None):
        self.last_text = text
        return {"region_narration": [{"region": 0, "observation": "a trace crosses the left fill"}],
                "anomalies": [], "note": "ok"}


class TestNarrate(unittest.TestCase):
    def test_no_facts_or_heuristic_in_prompt(self):
        stub = StubChat()
        regions = [{"bbox_px": [10, 20, 40, 55], "area_px": 300, "centroid_px": [25, 37]}]
        vn.narrate("x.png", regions, chat=stub)
        t = stub.last_text.lower()
        # the CL-21 failure: numeric facts / the predetermining rule fed alongside -> parroting
        for banned in ("islands", "foreign_cross", "area_mm2", "islands>1", "means clipped",
                       "intact vs clipped", "pours_intact"):
            self.assertNotIn(banned.lower(), t, f"prompt leaked '{banned}'")
        # it IS told to describe, not judge/measure
        self.assertIn("not a judge", t)
        self.assertTrue("describe" in t or "narrate" in t)

    def test_region_locations_passed_not_facts(self):
        stub = StubChat()
        regions = [{"bbox_px": [10, 20, 40, 55], "centroid_px": [25, 37]}]
        vn.narrate("x.png", regions, chat=stub)
        self.assertIn("[10, 20, 40, 55]", stub.last_text)        # the location IS given (geometry)

    def test_anomaly_only_when_no_reference(self):
        stub = StubChat()
        vn.narrate("x.png", None, chat=stub)
        self.assertIn("no reference render", stub.last_text.lower())
        self.assertIn("anomaly", stub.last_text.lower())

    def test_output_is_flag_not_verdict(self):
        stub = StubChat()
        out = vn.narrate("x.png", [{"bbox_px": [0, 0, 5, 5]}], chat=stub)
        self.assertEqual(out["role"], "narration+anomaly")
        for verdict_key in ("pours_intact", "clipped_nets", "intact", "verdict"):
            self.assertNotIn(verdict_key, out)
        self.assertIn("anomalies", out)
        self.assertIn("region_narration", out)

    def test_schema_forbids_a_boolean_verdict(self):
        # the schema makes the wrong job unexpressible (no boolean / net-list verdict field)
        props = vn.NARRATE_SCHEMA["properties"]
        self.assertEqual(set(props), {"region_narration", "anomalies", "note"})
        self.assertFalse(vn.NARRATE_SCHEMA.get("additionalProperties", True))


if __name__ == "__main__":
    unittest.main()
