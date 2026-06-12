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


class TestBaselineSubtraction(unittest.TestCase):
    """The logo false-positive fix: anomalies that recur on the known-good reference are subtracted
    AFTER the fact -- never put as a prior in the prompt."""

    def test_recurring_anomaly_dropped(self):
        baseline = ["copper logo text in the lower-left corner"]
        cand = ["copper logo text in the lower left corner",          # same flag -> drop
                "a trace appears severed near the right shunt"]        # novel -> keep
        kept = vn.subtract_baseline(cand, baseline)
        self.assertEqual(kept, ["a trace appears severed near the right shunt"])

    def test_no_baseline_keeps_all(self):
        cand = ["something", "another thing"]
        self.assertEqual(vn.subtract_baseline(cand, []), cand)
        self.assertEqual(vn.subtract_baseline(cand, None), cand)

    def test_narrate_subtracts_baseline_and_preserves_raw(self):
        class _Stub:
            def __call__(self, model, text, png, schema=None, max_tokens=0, timeout=0, ctx=None):
                return {"region_narration": [], "anomalies": ["the intentional CEC logo on B.Cu"],
                        "note": "ok"}
        out = vn.narrate("x.png", None, chat=_Stub(),
                         baseline_anomalies=["intentional CEC logo on B Cu"])
        self.assertEqual(out["anomalies"], [])                        # logo subtracted
        self.assertEqual(out["anomalies_raw"], ["the intentional CEC logo on B.Cu"])  # raw retained


class TestOutlineSanity(unittest.TestCase):
    """The deterministic render-corruption backstop -- compares the rendered SVG geometry to the
    board's Edge.Cuts bbox, needs no reference."""
    import cec_render_diff as rd  # noqa: E402

    def _svg(self, w_mm, h_mm, vbw=None, vbh=None, span=1.0):
        vbw = vbw if vbw is not None else w_mm
        vbh = vbh if vbh is not None else h_mm
        # a minimal outline rectangle spanning `span` fraction of the viewBox
        x1, y1 = 0.0, 0.0
        x2, y2 = vbw * span, vbh * span
        return (f'<svg width="{w_mm}mm" height="{h_mm}mm" viewBox="0 0 {vbw} {vbh}">'
                f'<path d="M {x1} {y1} L {x2} {y1} L {x2} {y2} L {x1} {y2} Z"/></svg>')

    def _write(self, txt):
        import tempfile
        f = tempfile.NamedTemporaryFile("w", suffix=".svg", delete=False)
        f.write(txt)
        f.close()
        return f.name

    def test_clean_render_passes(self):
        p = self._write(self._svg(96.0, 35.0))
        r = self.rd.outline_sanity(p, 96.0, 35.0)
        self.assertTrue(r["ok"], r["reasons"])

    def test_anisotropic_width_caught(self):
        # the corrupt_svg corruption: declared width scaled 0.7x -> wrong size + wrong aspect
        p = self._write(self._svg(96.0 * 0.7, 35.0))
        r = self.rd.outline_sanity(p, 96.0, 35.0)
        self.assertFalse(r["ok"])
        self.assertTrue(any("width" in x or "aspect" in x for x in r["reasons"]))

    def test_truncated_outline_caught(self):
        # canvas declared full size but the drawn outline spans only ~half of it
        p = self._write(self._svg(96.0, 35.0, span=0.5))
        r = self.rd.outline_sanity(p, 96.0, 35.0)
        self.assertFalse(r["ok"])
        self.assertTrue(any("truncated" in x or "partial" in x for x in r["reasons"]))


if __name__ == "__main__":
    unittest.main()
