#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Tests for EI-02 (the SIGNED-ONLY control lane + A/B aggregation), EI-07 (real_anchor_ratio), and the
# EI-02 objective penalty-reweight seam. All host-runnable -- cec_fullstack lazily imports its
# pcbnew/broker dependencies, so the pure helpers exercised here need neither a container nor the GPU.
#
# These cover the host-testable seams the orchestrator wires together:
#   lane_for           -- every Nth round is the control lane (signed-only)
#   real_anchor_ratio  -- deterministic-vs-model evidence grounding (EI-07)
#   _penalty_weighted_base -- the augmented lane's injected-penalty reweight (control => base unchanged)
#   ab_aggregate / render_ab_table -- the standing control-vs-augmented A/B table

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_fullstack as fs           # noqa: E402  (lazy pcbnew/broker imports -- host-safe)


class TestLaneFor(unittest.TestCase):
    def test_every_nth_is_control(self):
        # default CONTROL_EVERY=4 -> rounds 4,8,12 are control; everything else augmented
        self.assertEqual([fs.lane_for(r, control_every=4) for r in range(1, 9)],
                         ["augmented", "augmented", "augmented", "control",
                          "augmented", "augmented", "augmented", "control"])

    def test_disabled_when_zero_or_negative(self):
        for r in range(1, 6):
            self.assertEqual(fs.lane_for(r, control_every=0), "augmented")
            self.assertEqual(fs.lane_for(r, control_every=-1), "augmented")

    def test_every_round_control(self):
        self.assertTrue(all(fs.lane_for(r, control_every=1) == "control" for r in range(1, 6)))


class TestRealAnchorRatio(unittest.TestCase):
    """EI-07: deterministic anchors (gates/DRC/pour-facts/FEM) vs model anchors (panel/auditor/verifier/V4/vision)."""

    REC = {"gates_pass": False, "kelvin_ok": False, "diffpair_ok": True, "drc": 12,
           "unconnected": 3, "plane_signal_mm": 0.0, "max_T": 81.0,
           "fem_flags": [{"name": "via_fusing"}], "pour_integrity_ok": True}
    POUR = {"facts": {"/SENSEC1_HI": {"islands": 1}, "/SENSEC1_LO": {"islands": 1},
                      "/SENSEC2_HI": {"islands": 1}, "/SENSEC2_LO": {"islands": 2}}}

    def test_deterministic_count(self):
        a = fs.real_anchor_ratio(self.REC, self.POUR)
        # 3 gates + 3 DRC scalars + 4 pour-fact nets + pour_integrity_ok + max_T + 1 fem flag = 13
        self.assertEqual(a["n_deterministic"], 13)
        self.assertEqual(a["n_model"], 0)               # no model seats supplied
        self.assertEqual(a["real_anchor_ratio"], 1.0)   # all deterministic

    def test_model_anchors_lower_ratio(self):
        a = fs.real_anchor_ratio(
            self.REC, self.POUR,
            panel_votes=[("safety", "repair", ""), ("finishing", "accept", ""), ("progress", "repair", "")],
            audit={"verdict": "repair"}, v4={"declined": False, "local_minimum_risk": "high"},
            vision_ran=True, verifier_ran=True)
        # model = 3 panel + 1 auditor + 3 verifier + 1 V4 + 1 vision = 9
        self.assertEqual(a["n_model"], 9)
        self.assertEqual(a["n_deterministic"], 13)
        self.assertAlmostEqual(a["real_anchor_ratio"], round(13 / 22, 4))

    def test_fallback_panel_vote_is_not_a_model_anchor(self):
        a = fs.real_anchor_ratio(self.REC, self.POUR, panel_votes=[("fallback", None, "")])
        self.assertEqual(a["n_model"], 0)               # the deterministic fallback vote is not model judgment

    def test_declined_v4_is_restraint_not_a_model_anchor(self):
        a = fs.real_anchor_ratio(self.REC, self.POUR, v4={"declined": True})
        self.assertEqual(a["n_model"], 0)

    def test_errored_auditor_not_counted(self):
        a = fs.real_anchor_ratio(self.REC, self.POUR, audit={"verdict": "repair", "error": "timeout"})
        self.assertEqual(a["n_model"], 0)

    def test_empty_is_none(self):
        a = fs.real_anchor_ratio({}, {})
        self.assertIsNone(a["real_anchor_ratio"])       # no anchors at all -> None, never a divide-by-zero


class TestPenaltyWeightedBase(unittest.TestCase):
    """EI-02: the augmented lane applies the injected scorer_penalties; the control lane (empty penalties)
    leaves the base soft cost unchanged."""

    REC = {"objective_base": 100.0, "drc": 4, "unconnected": 2, "plane_signal_mm": 1.5}

    def test_control_unchanged(self):
        self.assertEqual(fs._penalty_weighted_base(self.REC, {}), 100.0)

    def test_augmented_reweights(self):
        # drc*50 + unconnected*5 + plane*50 = 4*50 + 2*5 + 1.5*50 = 200 + 10 + 75 = 285 over base 100
        out = fs._penalty_weighted_base(self.REC, {"plane_signal_mm": 50.0, "drc": 50.0, "unconnected": 5.0})
        self.assertEqual(out, 100.0 + 285.0)

    def test_unknown_metric_ignored(self):
        self.assertEqual(fs._penalty_weighted_base(self.REC, {"not_a_metric": 99.0}), 100.0)

    def test_bad_weight_is_safe(self):
        self.assertEqual(fs._penalty_weighted_base(self.REC, {"drc": "oops"}), 100.0)


class TestABAggregate(unittest.TestCase):
    """EI-02 A/B: split rows by lane and aggregate the standing control-vs-augmented table."""

    ROWS = [
        {"lane": "augmented", "gates_pass": True, "kelvin_ok": True, "drc": 4, "plane_signal_mm": 0.0,
         "real_anchor_ratio": 0.6},
        {"lane": "augmented", "gates_pass": False, "kelvin_ok": True, "drc": 12, "plane_signal_mm": 2.0,
         "real_anchor_ratio": 0.5},
        {"lane": "control", "gates_pass": False, "kelvin_ok": False, "drc": 20, "plane_signal_mm": 5.0,
         "real_anchor_ratio": 0.9},
        {"lane": "control", "gates_pass": False, "kelvin_ok": True, "drc": 18, "plane_signal_mm": 4.0,
         "real_anchor_ratio": 0.85},
    ]

    def test_split_and_aggregate(self):
        ab = fs.ab_aggregate(self.ROWS)
        self.assertEqual(ab["augmented"]["n"], 2)
        self.assertEqual(ab["control"]["n"], 2)
        # augmented converges 1/2, control 0/2
        self.assertEqual(ab["augmented"]["convergence"], 0.5)
        self.assertEqual(ab["control"]["convergence"], 0.0)
        self.assertEqual(ab["augmented"]["gates_pass_rate"], 0.5)
        self.assertEqual(ab["control"]["gates_pass_rate"], 0.0)
        # means: augmented plane (0+2)/2=1.0, control (5+4)/2=4.5
        self.assertEqual(ab["augmented"]["plane_signal_mm_mean"], 1.0)
        self.assertEqual(ab["control"]["plane_signal_mm_mean"], 4.5)

    def test_delta_signs(self):
        ab = fs.ab_aggregate(self.ROWS)
        d = ab["delta"]
        self.assertEqual(d["convergence"], round(0.5 - 0.0, 4))            # augmented converges MORE (+)
        self.assertEqual(d["plane_signal_mm_mean"], round(1.0 - 4.5, 3))   # augmented carves LESS plane (-)
        self.assertEqual(d["gates_pass_rate"], 0.5)
        # EI-07 rollup is in the delta too
        self.assertIn("real_anchor_ratio_mean", d)

    def test_empty_axes_are_none_not_crash(self):
        ab = fs.ab_aggregate([{"lane": "augmented"}])     # no metrics on the only row
        self.assertEqual(ab["augmented"]["n"], 1)
        self.assertIsNone(ab["augmented"]["gates_pass_rate"])
        self.assertIsNone(ab["augmented"]["convergence"])
        self.assertEqual(ab["control"]["n"], 0)
        self.assertEqual(ab["delta"], {})                 # no comparable axis -> empty delta, no crash

    def test_render_table_is_text(self):
        t = fs.render_ab_table(fs.ab_aggregate(self.ROWS))
        self.assertIn("control", t)
        self.assertIn("augmented", t.replace("augmnt", "augmented"))   # header / column
        self.assertIn("convergence", t)
        self.assertIn("plane_signal_mm_mean", t)
        # the table renders without throwing on a None cell
        fs.render_ab_table(fs.ab_aggregate([{"lane": "augmented"}]))


class TestOutcomeSerialization(unittest.TestCase):
    """act_outcome_dict serializes a control-gated Outcome for the artifact + ledger extra."""

    def test_roundtrips_to_dict(self):
        import cec_fs_actuator as act
        d = act.Delta(id="D-r5-0", round=5, source="auditor", kind="avoid",
                      intent={"net": "/I2C_SDA", "avoid": [{"rect_mm": [1, 2, 3, 4]}]})
        oc = act.settle_outcome(d, {"root_cause": "x", "proposed_lever": {"lever": "avoid", "target": "/I2C_SDA"}},
                                {"objective": 950000, "gates_pass": False},
                                {"objective": 960000, "gates_pass": False},
                                corpus_state={"live_rules_sha": "abc"})
        out = fs.act_outcome_dict(oc)
        self.assertEqual(out["verdict"], "vindicated")
        self.assertEqual(out["delta_id"], "D-r5-0")
        self.assertEqual(out["corpus_state"]["live_rules_sha"], "abc")
        self.assertEqual(out["treatment"]["objective"], 950000)
        self.assertEqual(out["control"]["objective"], 960000)


class TestPlacementAnchor(unittest.TestCase):
    """PL-09: an APPLIED placement move is a DETERMINISTIC anchor (det+1), never a model anchor; a
    non-placement round is byte-identical to the no-kwarg call (default no-op)."""
    REC = TestRealAnchorRatio.REC
    POUR = TestRealAnchorRatio.POUR

    def test_placement_is_one_more_deterministic(self):
        a0 = fs.real_anchor_ratio(self.REC, self.POUR, placement_moved=False)
        a1 = fs.real_anchor_ratio(self.REC, self.POUR, placement_moved=True)
        self.assertEqual(a1["n_deterministic"], a0["n_deterministic"] + 1)
        self.assertEqual(a1["n_model"], a0["n_model"])   # never a model anchor (no double-count)

    def test_default_is_noop_pins_existing_count(self):
        self.assertEqual(fs.real_anchor_ratio(self.REC, self.POUR)["n_deterministic"], 13)
        self.assertEqual(fs.real_anchor_ratio(self.REC, self.POUR, placement_moved=False)["n_deterministic"], 13)


class TestPlacementSource(unittest.TestCase):
    """PL-05: the lane-gated route-source selector -- a CONTROL round NEVER sees the placement override."""
    def test_augmented_uses_override(self):
        self.assertEqual(fs._placement_source_for("augmented", "/x/placed-r5.kicad_pcb", "/c"),
                         "/x/placed-r5.kicad_pcb")
        self.assertEqual(fs._placement_source_for("augmented", None, "/c"), "/c")

    def test_control_never_sees_override(self):
        self.assertEqual(fs._placement_source_for("control", "/x/placed-r5.kicad_pcb", "/c"), "/c")
        self.assertEqual(fs._placement_source_for("control", None, "/c"), "/c")

    def test_exec_route_one_threads_override_arg(self):
        # the host route shim must append --board-pcb-override (container-translated) only when given one.
        import cec_overnight_directed as ovd
        captured = {}

        class _R:
            returncode = 0
            stdout = "RECORD_JSON={}"
            stderr = ""
        orig = ovd.subprocess.run if hasattr(ovd, "subprocess") else None
        import subprocess as _sp
        real = _sp.run

        def fake_run(cmd, *a, **k):
            captured["cmd"] = cmd
            return _R()
        _sp.run = fake_run
        try:
            ovd._exec_route_one("eps-8pin", 5, board_pcb_override="build/fullstack/placed-r5.kicad_pcb")
            with_ov = list(captured["cmd"])
            ovd._exec_route_one("eps-8pin", 5)
            without = list(captured["cmd"])
        finally:
            _sp.run = real
        self.assertIn("--board-pcb-override", with_ov)
        self.assertTrue(any(c.endswith("placed-r5.kicad_pcb") for c in with_ov))
        self.assertNotIn("--board-pcb-override", without)


class TestPlacementRow(unittest.TestCase):
    """PL-08: the placement fields ride the SAME lane+corpus_state-tagged measurement row + A/B table."""
    def test_augmented_row_fields(self):
        r = fs._placement_row_fields({"moved": True, "verdict": "placed", "ref": "U10",
                                      "refs": ["U10", "C40"], "moved_mm": 3.0}, "augmented")
        self.assertTrue(r["placement_moved"])
        self.assertEqual(r["placement_refs"], ["U10", "C40"])
        self.assertEqual(r["placement_verdict"], "placed")
        self.assertEqual(r["placement_ref"], "U10")

    def test_control_row_suppressed(self):
        r = fs._placement_row_fields({"moved": False, "verdict": "suppressed"}, "control", "refuted")
        self.assertFalse(r["placement_moved"])
        self.assertEqual(r["placement_verdict"], "suppressed")
        self.assertEqual(r["placement_settled"], "refuted")

    def test_row_field_keyset(self):
        r = fs._placement_row_fields({"moved": True}, "augmented")
        self.assertEqual(set(r), {"placement_moved", "placement_verdict", "placement_ref",
                                  "placement_refs", "placement_moved_mm", "placement_settled"})

    def test_ab_placement_moved_rate(self):
        rows = [{"lane": "augmented", "placement_moved": True, "placement_settled": "vindicated"},
                {"lane": "augmented", "placement_moved": True, "placement_settled": "refuted"},
                {"lane": "control", "placement_moved": False}]
        ab = fs.ab_aggregate(rows)
        self.assertEqual(ab["augmented"]["placement_moved_rate"], 1.0)
        self.assertEqual(ab["control"]["placement_moved_rate"], 0.0)      # control NEVER moves
        self.assertEqual(ab["augmented"]["placement_vindicated"], 1)
        self.assertEqual(ab["augmented"]["placement_refuted"], 1)
        self.assertIn("placement_moved_rate", fs.render_ab_table(ab))

    def test_ab_empty_axis_is_none_not_crash(self):
        ab = fs.ab_aggregate([{"lane": "augmented", "gates_pass": False}])    # no placement field
        self.assertIsNone(ab["augmented"]["placement_moved_rate"])


class TestPlacementKeepGuard(unittest.TestCase):
    """BLOCKER-01: the kind-aware launder guard. A placement move is kept/compounded ONLY if it settled
    vindicated AND held pour integrity -- a pour-FRAGMENTING move that reads 'vindicated' on the pour-blind
    objective_base (the both-gates-fail launder) is NEVER promoted."""
    def test_vindicated_pour_ok_keeps(self):
        self.assertTrue(fs._placement_keep("vindicated", True))

    def test_vindicated_but_fragmented_is_rejected(self):
        # THE LAUNDER: settle_outcome can return 'vindicated' on objective_base while the pour fragmented.
        self.assertFalse(fs._placement_keep("vindicated", False))

    def test_unknown_pour_integrity_allowed(self):
        self.assertTrue(fs._placement_keep("vindicated", None))   # not-False -> not the launder signal

    def test_refuted_never_keeps(self):
        self.assertFalse(fs._placement_keep("refuted", True))
        self.assertFalse(fs._placement_keep("overturned", True))


if __name__ == "__main__":
    unittest.main(verbosity=2)
