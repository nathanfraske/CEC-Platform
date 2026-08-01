#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# THE ABSOLUTE high-current-pour keepout (owner directive 2026-06-27): the high-current pour
# (cec_fr.derive_power_pours) is reserved for its OWN net's copper plus the inner-edge Kelvin tap --
# NO foreign-net track/via may cross it, EVER (GND/power INCLUDED). This is ONE region-keyed rule the
# placer + router obey, FAIL-gated in cec_router.route()'s accept verdict (independent_drc) and the
# intake gate. KiCad DRC is BLIND to foreign-through-pour (the zone filler carves a silent antipad),
# so the gate is GEOMETRIC, never DRC-derived.
#
# TEETH: a CLEAN cable floorplan PASSes; inject ONE foreign GND track across a SENSEC pour and the
# checker FAILs + independent_drc forces gates_pass=False. Shared-bus per-pin/per-rail boards N/A.

import os
import sys
import shutil
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

EPS = os.path.join(ROOT, "beta", "eps-8pin-rev3", "eps-8pin-rev3.kicad_pcb")
HPWR = os.path.join(ROOT, "beta", "12vhpwr-standard", "12vhpwr-standard-module.kicad_pcb")
ATX = os.path.join(ROOT, "beta", "atx-24pin-rev3", "24pin-module.kicad_pcb")

try:
    import pcbnew                                              # noqa: F401
    import cec_constraints as K                                # noqa: E402  (imports pcbnew)
    HAVE = True
except Exception:                                              # noqa: BLE001
    HAVE = False

CID = "no-foreign-on-high-current-pour"


def _fresh_copy(src_pcb, tmpdir):
    """Copy a committed board (+ its project files) to a UNIQUE tmp path. pcbnew shares a cached
    BOARD per path (documented KiCad-10 SWIG behaviour), so a sibling test that loaded+mutated the
    committed path in the same process can poison a re-load; loading a fresh path sidesteps that."""
    dst = os.path.join(tmpdir, os.path.basename(src_pcb))
    shutil.copy(src_pcb, dst)
    for ext in (".kicad_pro", ".kicad_dru", ".kicad_prl"):
        s = src_pcb[:-len(".kicad_pcb")] + ext
        if os.path.isfile(s):
            shutil.copy(s, dst[:-len(".kicad_pcb")] + ext)
    return dst


def _inject_foreign_track(src_pcb, dst_pcb, *, foreign_net="GND", box_index=0):
    """Copy `src_pcb` to `dst_pcb` and lay ONE straight `foreign_net` track ACROSS the
    `box_index`-th derive_power_pours box on the box's layer. Returns the pour net name."""
    import pcbnew
    shutil.copy(src_pcb, dst_pcb)
    for ext in (".kicad_pro", ".kicad_dru", ".kicad_prl"):
        s = src_pcb[:-len(".kicad_pcb")] + ext
        if os.path.isfile(s):
            shutil.copy(s, dst_pcb[:-len(".kicad_pcb")] + ext)
    b = pcbnew.LoadBoard(dst_pcb)
    boxes, _allowed = K._derive_pour_boxes(b, dst_pcb)
    net, lid, x0, x1, y0, y1 = boxes[box_index]
    fnet = next((n for n in b.GetNetInfo().NetsByNetcode().values()
                 if n.GetNetname() == foreign_net), None)
    assert fnet is not None, "%s net not on the board" % foreign_net
    cy = (y0 + y1) / 2.0
    t = pcbnew.PCB_TRACK(b)
    t.SetStart(pcbnew.VECTOR2I(int((x0 - 2.0) * 1e6), int(cy * 1e6)))
    t.SetEnd(pcbnew.VECTOR2I(int((x1 + 2.0) * 1e6), int(cy * 1e6)))
    t.SetLayer(lid)
    t.SetWidth(int(0.25 * 1e6))
    t.SetNet(fnet)
    b.Add(t)
    b.Save(dst_pcb)
    return net


@unittest.skipUnless(HAVE and os.path.isfile(EPS), "pcbnew + eps-8pin-rev3 required")
class TestForeignOnPourGate(unittest.TestCase):
    def test_clean_floorplan_passes(self):
        # the committed EPS floorplan has no routed tracks -> PASS (the rule never false-refuses a
        # clean placement at intake). applicable=True because the pour region IS derivable.
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        eps = _fresh_copy(EPS, tmp)
        b = pcbnew.LoadBoard(eps)
        ok, detail = K.CHECKERS[CID](b, eps, {})[:2]
        self.assertIs(ok, True, detail)
        s = K.foreign_on_pour_summary(eps)
        self.assertTrue(s["applicable"])
        self.assertEqual((s["n_tracks"], s["n_vias"]), (0, 0))
        self.assertGreaterEqual(s["n_pours"], 2)               # eps = 2 SENSEC pairs -> 4 boxes

    def test_injected_foreign_track_fails(self):
        tmp = tempfile.mkdtemp()
        try:
            dst = os.path.join(tmp, "inj.kicad_pcb")
            pour = _inject_foreign_track(EPS, dst, foreign_net="GND")
            b = pcbnew.LoadBoard(dst)
            ok, detail, payload = K.CHECKERS[CID](b, dst, {})
            self.assertIs(ok, False, "a GND track across the %s pour must FAIL" % pour)
            self.assertIn("ABSOLUTE keepout", detail)
            s = K.foreign_on_pour_summary(dst)
            self.assertGreaterEqual(s["n_tracks"], 1)
            self.assertIn(pour, s["by_pour"])
            self.assertIn("GND", s["by_pour"][pour])
            # the FAIL emits a keepout directive the placer/router consume
            self.assertTrue(any(p.get("reserve") == "high-current-pour-foreign" for p in payload))
        finally:
            shutil.rmtree(tmp)

    def test_injected_track_forces_route_gate_fail(self):
        # the wiring: a foreign-on-pour board can never pass route()'s INDEPENDENT accept verdict,
        # even though KiCad DRC stays clean (the antipad is invisible to DRC).
        import cec_router
        import cec_score
        tmp = tempfile.mkdtemp()
        try:
            dst = os.path.join(tmp, "inj.kicad_pcb")
            _inject_foreign_track(EPS, dst, foreign_net="GND")
            v = cec_router.independent_drc(dst, cec_score.Rules.from_board(dst))
            self.assertFalse(v["gates_pass"], "foreign-on-pour must force gates_pass=False")
            self.assertTrue(v["foreign_on_pour"]["applicable"])
            self.assertGreaterEqual(v["foreign_on_pour"]["tracks"], 1)
            self.assertTrue(any("foreign-on-pour" in r for r in v["reasons"]))
        finally:
            shutil.rmtree(tmp)


@unittest.skipUnless(HAVE, "pcbnew required")
class TestForeignOnPourScope(unittest.TestCase):
    def test_shared_bus_boards_are_na(self):
        # 12VHPWR (per-pin off shared J3/J4) packs its lanes with the sense chain by design
        # -> N/A, identical to high-current-corridor-keepout. NOTE (re-baselined 2026-07-07):
        # the 24-pin rev3 used to be the second shared-bus exemplar, but the owner's new rev3
        # PCB (beta D-5a output-daughterboard architecture, J4 dropped) carries REAL per-rail
        # pour corridors -- the checker legitimately reads it APPLICABLE now; it is asserted
        # clean in test_new_24pin_rev3_is_applicable_and_clean below.
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        checked = 0
        for src in (HPWR,):
            if not os.path.isfile(src):
                continue
            checked += 1
            p = _fresh_copy(src, tmp)
            b = pcbnew.LoadBoard(p)
            ok, detail = K.CHECKERS[CID](b, p, {})[:2]
            self.assertIsNone(ok, "%s must be N/A (shared-bus), got %r (%s)"
                              % (os.path.basename(p), ok, detail))
            self.assertFalse(K.foreign_on_pour_summary(p)["applicable"])
        self.assertGreaterEqual(checked, 1, "at least one shared-bus board must be exercised")

    @unittest.skipUnless(HAVE and os.path.isfile(ATX), "pcbnew + atx-24pin-rev3 required")
    def test_new_24pin_rev3_is_applicable_and_clean(self):
        # The owner's rev3 PCB (2026-07 beta): per-rail J3->shunt->out-field corridors with
        # actual pours -> the foreign-on-pour gate APPLIES and the committed board is clean.
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        p = _fresh_copy(ATX, tmp)
        s = K.foreign_on_pour_summary(p)
        self.assertTrue(s["applicable"])
        self.assertGreaterEqual(s["n_pours"], 2)
        self.assertEqual((s["n_tracks"], s["n_vias"]), (0, 0), s)


@unittest.skipUnless(HAVE, "pcbnew required")
class TestForeignOnPourRegistry(unittest.TestCase):
    def test_registry_entry_hard_and_wired(self):
        c = next((c for c in K.REGISTRY if c.id == CID), None)
        self.assertIsNotNone(c, "registry entry missing")
        self.assertEqual(c.severity, "hard")
        self.assertEqual(c.checkable, "yes")
        self.assertEqual(c.directive, "keepout")
        self.assertIn(CID, K.CHECKERS, "no checker registered")
        self.assertIn(CID, K.INTAKE_CHECKS, "not wired into the intake gate")


if __name__ == "__main__":
    unittest.main()
