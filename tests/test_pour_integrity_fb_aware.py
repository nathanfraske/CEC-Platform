"""SB-08 item 2 escalation regression: the pour-integrity gate is now F+B-mirror-AWARE
(prefers the connected-component count over the raw F.Cu island count). The non-negotiable
property (owner): the validation-run R4 shape (3 F.Cu islands, no B.Cu mirror / no stitching ->
3 components) MUST still FAIL, while the synthesize_power_copper board (3 F.Cu islands stitched
into 1 component by the via field + THT pads) PASSES.

Host-only: exercises the gate logic on pour_facts dicts. The component VALUES are what
cec_score.sense_pour_components computes in-container -- empirically verified 2026-06-12 on the
synth eps golden: SENSEC2_LO = 3 F.Cu islands but 1 connected component (21 via/pad bridges)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import cec_score  # noqa: E402


class TestFBAwarePourIntegrity(unittest.TestCase):
    def test_R4_shape_still_fails(self):
        # R4: a clipped single-layer pour -- 3 F.Cu islands, NO mirror/stitch -> 3 components
        facts = {"/SENSEC2_HI": {"islands": 3, "components": 3, "area_mm2": 60.0}}
        ok, reasons = cec_score.pour_integrity_ok(facts)
        self.assertFalse(ok, "R4 (3 components) must FAIL under any new definition")
        self.assertIn("3 components", reasons[0])

    def test_synth_shape_passes(self):
        # synth board: 3 F.Cu islands BUT stitched into 1 component via the via field + THT pads
        facts = {"/SENSEC2_LO": {"islands": 3, "components": 1, "area_mm2": 70.0}}
        ok, reasons = cec_score.pour_integrity_ok(facts)
        self.assertTrue(ok, "synth board (1 component) must PASS even with 3 raw F.Cu islands")
        self.assertEqual(reasons, [])

    def test_component_count_preferred_over_islands(self):
        # the F.Cu island count alone would (wrongly) fail this; components==1 rescues it
        facts = {"/SENSEC1_LO": {"islands": 4, "components": 1}}
        self.assertTrue(cec_score.pour_integrity_ok(facts)[0])

    def test_back_compat_falls_back_to_islands(self):
        # old facts without a 'components' key still use the raw F.Cu island count (no regression)
        self.assertFalse(cec_score.pour_integrity_ok({"/SENSEC1_HI": {"islands": 2}})[0])
        self.assertTrue(cec_score.pour_integrity_ok({"/SENSEC1_HI": {"islands": 1}})[0])

    def test_genuinely_fragmented_components_fail(self):
        # a real fragmentation that the mirror did NOT rescue -> components 2 -> FAIL
        facts = {"/SENSEC2_LO": {"islands": 2, "components": 2, "area_mm2": 40.0}}
        ok, reasons = cec_score.pour_integrity_ok(facts)
        self.assertFalse(ok)
        self.assertIn("2 components", reasons[0])

    def test_vacuous_pass_no_sense_pours(self):
        self.assertTrue(cec_score.pour_integrity_ok({"GND": {"islands": 5}})[0])


if __name__ == "__main__":
    unittest.main()
