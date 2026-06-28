#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Tests for the 2026-06-13 trio: (A) the item4 corridor-avoid lever fix (polygon->rect_mm derivation),
# (B) EI-01 corpus_state knowledge pinning (shadow-evidence partition), (C) vision gating to finalists.
# All host-runnable (no pcbnew/container) -- the pcbnew-dependent edges are stubbed.

import os
import sys
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

# cec_fr does an unconditional top-level `import pcbnew`; the lever tests monkeypatch
# cec_fr.derive_power_pours so the real engine is never exercised -- stub pcbnew so these stay
# host-runnable (no container needed). A real pcbnew (in-container) shadows the stub harmlessly.
sys.modules.setdefault("pcbnew", types.ModuleType("pcbnew"))


class TestLeverFix(unittest.TestCase):
    """A: clipped_corridor_rects must derive rect_mm from derive_power_pours' 'polygon' key.
    The bug it fixes: the consumer read rect_mm/rect, the producer emits polygon -> {} every round ->
    the item4 corridor-avoid lever fired ZERO times across a 34-round run."""

    def setUp(self):
        # these tests STUB cec_fr.derive_power_pours; save + restore it so the monkeypatch does not
        # LEAK into the rest of the suite (a leaked stub poisoned every downstream caller --
        # test_foreign_on_pour_gate, test_gr_fr02_fixtures, and even this module's own later tests).
        import cec_fr
        self._orig_dpp = cec_fr.derive_power_pours

    def tearDown(self):
        import cec_fr
        cec_fr.derive_power_pours = self._orig_dpp

    def _stub_pours(self):
        # exactly the shape cec_fr.derive_power_pours emits (cec_fr.py:617-618): net/layer/polygon
        return [
            {"net": "/SENSEC2_LO", "layer": "F.Cu",
             "polygon": [(10.0, 20.0), (30.0, 20.0), (30.0, 50.0), (10.0, 50.0)]},
            {"net": "/SENSEC2_HI", "layer": "F.Cu",
             "polygon": [(12.0, 22.0), (28.0, 22.0), (28.0, 48.0), (12.0, 48.0)]},
            {"net": "/+3V3", "layer": "F.Cu",  # not a clipped sense net -> must be excluded
             "polygon": [(0.0, 0.0), (5.0, 0.0), (5.0, 5.0), (0.0, 5.0)]},
        ]

    def test_polygon_to_rect(self):
        import cec_fr
        import cec_fr02
        cec_fr.derive_power_pours = lambda *a, **k: self._stub_pours()       # patch the producer
        out = cec_fr02.clipped_corridor_rects("dummy.kicad_pcb", ["/SENSEC2_LO", "/SENSEC2_HI"])
        # BEFORE the fix this was {} (rect_mm/rect absent on a polygon dict). Now it derives the bbox.
        self.assertIn("/SENSEC2_LO", out)
        self.assertIn("/SENSEC2_HI", out)
        self.assertNotIn("/+3V3", out)                                       # not requested -> excluded
        self.assertEqual(out["/SENSEC2_LO"]["rect_mm"], [10.0, 20.0, 30.0, 50.0])  # bbox of the polygon
        # T3: the corridor avoid-region covers BOTH copper layers (the post-route pour is F.Cu + B.Cu
        # mirror); the producer's 'layer' key is honored (widened), not silently dropped.
        self.assertEqual(out["/SENSEC2_LO"]["layers"], ["B.Cu", "F.Cu"])

    def test_lever_produces_avoid_intents(self):
        """End-to-end lever flow: clipped rects -> offending_net_intents -> non-empty FR-02 avoid intents."""
        import cec_fr
        import cec_fr02
        cec_fr.derive_power_pours = lambda *a, **k: self._stub_pours()
        corridors = cec_fr02.clipped_corridor_rects("dummy.kicad_pcb", ["/SENSEC2_LO"])
        intents = cec_fr02.offending_net_intents(corridors, ["/+3V3", "GND", "/SENSEC2_LO"])
        self.assertTrue(intents, "lever produced NO avoid-intents (regression: item4 dead again)")
        nets = {i["net"] for i in intents}
        self.assertIn("/+3V3", nets)
        self.assertIn("GND", nets)
        self.assertNotIn("/SENSEC2_LO", nets)            # sense nets belong in the pour, never steered out
        self.assertTrue(all(i.get("avoid") for i in intents))   # each carries the corridor avoid-region

    def test_back_compat_rect_mm(self):
        """A pour that already carries rect_mm/rect still works (backward compatible)."""
        import cec_fr
        import cec_fr02
        cec_fr.derive_power_pours = lambda *a, **k: [
            {"net": "/SENSEC1_HI", "rect_mm": [1.0, 2.0, 3.0, 4.0]}]
        out = cec_fr02.clipped_corridor_rects("dummy.kicad_pcb", ["/SENSEC1_HI"])
        self.assertEqual(out["/SENSEC1_HI"]["rect_mm"], [1.0, 2.0, 3.0, 4.0])


class TestCorpusStatePartition(unittest.TestCase):
    """B / EI-01: corpus_state pins the knowledge a round saw; an injection changes live_rules_sha
    (and the isolating sub-hashes) while the commit-time corpus trees stay constant."""

    def test_structure(self):
        import cec_ledger
        st = cec_ledger.corpus_state({"manager_rules": [], "scorer_penalties": {}})
        for k in ("promoted_tree", "staging_tree", "live_rules_sha", "manager_rules_sha", "adv_set_sha"):
            self.assertIn(k, st)

    def test_none_is_tree_only(self):
        import cec_ledger
        st = cec_ledger.corpus_state(None)
        self.assertIsNone(st["live_rules_sha"])
        self.assertIsNone(st["manager_rules_sha"])

    def test_tree_pins_resolve(self):
        """T1: the partition's commit-time anchor must resolve to REAL git tree ids in-repo -- else a
        silently-broken pin (path typo / renamed corpus dir) ships green and the partition is dead."""
        import subprocess
        import cec_ledger
        in_git = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"],
                                capture_output=True, cwd=ROOT).returncode == 0
        if not in_git:
            self.skipTest("not a git checkout")
        st = cec_ledger.corpus_state(None)
        for tk in ("promoted_tree", "staging_tree"):
            self.assertRegex(st[tk] or "", r"^[0-9a-f]{40}$")

    def test_injection_boundary(self):
        import cec_ledger
        lr_before = {"manager_rules": ["drc not improving"],
                     "scorer_penalties": {"drc": 50.0}}
        lr_after = {"manager_rules": ["drc not improving", "local_minimum_risk"],   # a rule injected
                    "scorer_penalties": {"drc": 50.0}}
        a = cec_ledger.corpus_state(lr_before)
        b = cec_ledger.corpus_state(lr_after)
        # the round-time knowledge changed ...
        self.assertNotEqual(a["live_rules_sha"], b["live_rules_sha"])
        self.assertNotEqual(a["manager_rules_sha"], b["manager_rules_sha"])
        # ... while the advisory penalties did NOT (isolation), and the commit-time trees did NOT.
        self.assertEqual(a["adv_set_sha"], b["adv_set_sha"])
        self.assertEqual(a["promoted_tree"], b["promoted_tree"])
        self.assertEqual(a["staging_tree"], b["staging_tree"])

    def test_penalty_isolates_to_adv(self):
        import cec_ledger
        a = cec_ledger.corpus_state({"manager_rules": [], "scorer_penalties": {"drc": 50.0}})
        b = cec_ledger.corpus_state({"manager_rules": [], "scorer_penalties": {"drc": 80.0}})
        self.assertNotEqual(a["adv_set_sha"], b["adv_set_sha"])         # advisory penalty changed
        self.assertEqual(a["manager_rules_sha"], b["manager_rules_sha"])  # rules did not


class TestVisionGate(unittest.TestCase):
    """C: vision_pour_check(run_vlm=False) computes the deterministic facts (which feed the gate + lever)
    but SKIPS the advisory VLM narrate -- and never touches the render/VLM path."""

    def test_gated_round_skips_vlm(self):
        import cec_fullstack as fs

        fs.pour_facts = lambda routed: {"/SENSEC2_LO": {"islands": 2, "area_mm2": 90.0},
                                        "/SENSEC2_HI": {"islands": 1, "area_mm2": 80.0}}

        def _boom(*a, **k):
            raise AssertionError("render_copper_zone called on a GATED round -- VLM not gated")
        fs.render_copper_zone = _boom

        out = fs.vision_pour_check({"routed": "x.kicad_pcb", "board": "eps-8pin"}, 1, run_vlm=False)
        self.assertEqual(out["vlm_gated"], "non-finalist")
        self.assertEqual(out["det_clipped_nets"], ["/SENSEC2_LO"])     # deterministic detection intact
        self.assertNotIn("anomalies", out)                            # no VLM output

    def test_vision_required_unmet_logic(self):
        """T2: a GATED round is never a false 'seat down'; a genuinely-attempted-but-silent VLM is."""
        import cec_fullstack as fs
        self.assertFalse(fs._vision_required_unmet({"vlm_gated": "non-finalist"}, 9))  # gated -> skip
        self.assertTrue(fs._vision_required_unmet({"facts": {}}, 9))      # attempted, no anomalies, big shift
        self.assertFalse(fs._vision_required_unmet({"anomalies": ["x"]}, 9))   # attempted + produced output
        self.assertFalse(fs._vision_required_unmet({"facts": {}}, 1))     # shift below threshold


if __name__ == "__main__":
    unittest.main(verbosity=2)
