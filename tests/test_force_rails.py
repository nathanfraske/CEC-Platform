#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Teeth for cec_force_rails (the 24-pin zone creator, owner GO 2026-07-19).
# Synthetic mini-boards, test_locked_residue construction pattern; pcbnew-gated
# (runs in the routing container, skips on the host).
#
# Covered: (1) name-independent straddle DISCOVERY incl. a rail whose post-shunt
# net breaks every SENSE* pattern (+5V_MAIN class); (2) the amps ladder;
# (3) a clean LAY commits LOCKED segs on the shunt's face with all pins picked;
# (4) a foreign barrel under one pin column drops ONLY that pin (per-pin
# refusal, rail still lays); (5) a foreign pad dead on the source band refuses
# the WHOLE rail loud (rail-fatal, nothing committed for it).
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

try:
    import pcbnew
    from pcbnew import VECTOR2I
    HAVE_PCBNEW = True
    import cec_force_rails as FR
except ImportError:
    HAVE_PCBNEW = False


def MM(v):
    return int(v * 1e6)


def _fp(b, ref):
    fp = pcbnew.FOOTPRINT(b)
    fp.SetReference(ref)
    b.Add(fp)
    return fp


def _pad(fp, name, net, x, y, wmm=1.5, hmm=1.5):
    p = pcbnew.PAD(fp)
    p.SetNumber(name)
    p.SetShape(pcbnew.PAD_SHAPE_RECT)
    p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    p.SetSize(VECTOR2I(MM(wmm), MM(hmm)))
    ls = pcbnew.LSET()
    ls.AddLayer(pcbnew.F_Cu)
    p.SetLayerSet(ls)
    p.SetPosition(VECTOR2I(MM(x), MM(y)))
    p.SetNet(net)
    fp.Add(p)
    return p


def _pad_tht(fp, name, net, x, y, wmm=1.7, hmm=1.7):
    p = pcbnew.PAD(fp)
    p.SetNumber(name)
    p.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    p.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    p.SetSize(VECTOR2I(MM(wmm), MM(hmm)))
    p.SetDrillSize(VECTOR2I(MM(0.9), MM(0.9)))
    p.SetLayerSet(pcbnew.LSET.AllCuMask(4))
    p.SetPosition(VECTOR2I(MM(x), MM(y)))
    p.SetNet(net)
    fp.Add(p)
    return p


def _mkboard_alt(*, foreign_smd_on_band=None):
    """4-layer board, THT J3/TB barrels (the real 24-pin shape) for alt-mode:
    one 5V rail, J3 pins at y=-6, RS2 straddle SMD at (20,28.5/31.5), TB THT
    at (20,48). Optional SMD foreign pad ON the band path (alt must pass
    UNDER it)."""
    b = pcbnew.CreateEmptyBoard()
    b.SetCopperLayerCount(4)
    nets = {}
    for n in ("/SENSE5V_HI", "+5V_MAIN", "/FOREIGN"):
        ni = pcbnew.NETINFO_ITEM(b, n)
        b.Add(ni)
        nets[n] = ni
    j3 = _fp(b, "J3")
    _pad_tht(j3, "4", nets["/SENSE5V_HI"], 16.0, -6.0)
    _pad_tht(j3, "6", nets["/SENSE5V_HI"], 24.0, -6.0)
    rs = _fp(b, "RS2")
    _pad(rs, "1", nets["/SENSE5V_HI"], 20.0, 28.5, 2.0, 1.2)
    _pad(rs, "2", nets["+5V_MAIN"], 20.0, 31.5, 2.0, 1.2)
    tb = _fp(b, "TB2")
    _pad_tht(tb, "1", nets["+5V_MAIN"], 20.0, 48.0, 2.5, 2.5)
    if foreign_smd_on_band is not None:
        f = _fp(b, "U9")
        _pad(f, "1", nets["/FOREIGN"], foreign_smd_on_band[0], foreign_smd_on_band[1])
    return b


def _mkboard(*, foreign_at=None, src_net="/SENSE5V_HI", snk_net="+5V_MAIN"):
    """One rail: J3 pins 4,6 on *src_net* at y=-6 -> RS2 straddle at (20,30) ->
    *snk_net* -> TB2 tab at (20,48). Optionally a foreign pad at *foreign_at*."""
    b = pcbnew.CreateEmptyBoard()
    nets = {}
    for n in (src_net, snk_net, "/FOREIGN"):
        ni = pcbnew.NETINFO_ITEM(b, n)
        b.Add(ni)
        nets[n] = ni
    j3 = _fp(b, "J3")
    _pad(j3, "4", nets[src_net], 16.0, -6.0)
    _pad(j3, "6", nets[src_net], 24.0, -6.0)
    rs = _fp(b, "RS2")
    _pad(rs, "1", nets[src_net], 20.0, 28.5, 2.0, 1.2)
    _pad(rs, "2", nets[snk_net], 20.0, 31.5, 2.0, 1.2)
    tb = _fp(b, "TB2")
    _pad(tb, "1", nets[snk_net], 20.0, 48.0, 2.5, 2.5)
    if foreign_at is not None:
        f = _fp(b, "U9")
        _pad(f, "1", nets["/FOREIGN"], foreign_at[0], foreign_at[1])
    return b


@unittest.skipUnless(HAVE_PCBNEW, "pcbnew required (routing container)")
class TestDiscovery(unittest.TestCase):
    def test_name_independent_straddle(self):
        b = _mkboard()
        rails = FR.discover_rails(b)
        self.assertEqual(len(rails), 1)
        rl = rails[0]
        self.assertEqual(rl["rs"], "RS2")
        self.assertEqual(rl["src_net"], "/SENSE5V_HI")     # the J3 side
        self.assertEqual(rl["snk_net"], "+5V_MAIN")        # the TB side, no SENSE name
        self.assertEqual(len(rl["j3"]), 2)
        self.assertEqual(len(rl["tb"]), 1)
        self.assertEqual(rl["amps"], 25.0)                 # 5V bar

    def test_amps_ladder(self):
        self.assertEqual(FR._amps_for(["/SENSE5VSB_LO", "+5VSB"]), 5.0)
        self.assertEqual(FR._amps_for(["/SENSE3V3_HI", "/SENSE3V3_LO"]), 20.0)
        self.assertEqual(FR._amps_for(["/SENSE12V_HI", "/SENSE12V_LO"]), 12.0)
        self.assertEqual(FR._amps_for(["/SENSE5V_HI", "+5V_MAIN"]), 25.0)


@unittest.skipUnless(HAVE_PCBNEW, "pcbnew required (routing container)")
class TestLay(unittest.TestCase):
    def _laid(self, b):
        return [t for t in b.GetTracks() if t.GetClass() == "PCB_TRACK"]

    def test_clean_lay_locked_all_pins(self):
        b = _mkboard()
        rep = FR.lay_force_rails(b, verbose=False)
        r = rep["RS2"]
        self.assertIsInstance(r, dict, r)
        self.assertEqual(r["pins"], "2/2")
        segs = self._laid(b)
        self.assertGreaterEqual(len(segs), 5)              # band+spine+2 drops+snk
        self.assertTrue(all(t.IsLocked() for t in segs))
        nets = {t.GetNetname() for t in segs}
        self.assertEqual(nets, {"/SENSE5V_HI", "+5V_MAIN"})

    def test_foreign_barrel_drops_only_that_pin(self):
        # drop-only blocking needs a NARROW rail (a fat band's collider reach
        # swallows the whole 2.5mm drop): the 5VSB rail (w=1.5, band reach
        # 1.75) leaves the drop's top 0.75mm clear of the band -- a foreign
        # pad there blocks ONLY J3.4's pickup (band_y = -6+2.5 = -3.5;
        # foreign at y=-5.5 is 2.0 from the band, dead on the drop column).
        b = _mkboard(foreign_at=(16.0, -5.5),
                     src_net="/SENSE5VSB_HI", snk_net="/SENSE5VSB_LO")
        rep = FR.lay_force_rails(b, verbose=False)
        r = rep["RS2"]
        self.assertIsInstance(r, dict, r)
        self.assertEqual(r["pins"], "1/2")
        self.assertTrue(any("J3.4" in d for d in r["dropped_pins"]))

    def test_foreign_on_band_refuses_rail_loud(self):
        # foreign pad dead on the source band row (plan_bands center for the
        # single w=6 rail: j3_bot(-6) + 2.5 + w/2 = -0.5)
        b = _mkboard(foreign_at=(18.0, -0.5))
        rep = FR.lay_force_rails(b, verbose=False)
        r = rep["RS2"]
        if isinstance(r, dict):                            # geometry drifted -> fail loud
            self.fail("expected rail-fatal refusal, got lay: %r" % r)
        self.assertIn("REFUSED", r)
        self.assertEqual(len(self._laid(b)), 0)


@unittest.skipUnless(HAVE_PCBNEW, "pcbnew required (routing container)")
class TestAltLayer(unittest.TestCase):
    """§2.3 layer-crossing (owner GO 2026-07-19): bands/sinks on the inner
    power-routing layer, direct into THT barrels, via arrays at the SMD shunt
    stubs; In1 stays GND (the owner ruling -- exercised via In2 as alt)."""

    def test_alt_lays_with_arrays_and_inner_copper(self):
        b = _mkboard_alt()
        rep = FR.lay_force_rails(b, verbose=False, alt_layer="In2.Cu")
        r = rep["RS2"]
        self.assertIsInstance(r, dict, r)
        self.assertTrue(r.get("alt"), r)
        # 5V = 25A -> ceil(25/2) = 13 vias per array x2 arrays... clamped by
        # the offsets table (9 sites max) -> the array REFUSES if it cannot
        # seat n; 25A needs 13 > 9 -> this fixture would refuse. Use the
        # report to assert the honest behavior instead of guessing: either it
        # laid with vias, or it refused on array capacity -- but for the 5V
        # rail the class table caps at 9 sites, so assert the refusal names
        # the array. (The real 24-pin rails: 12V->6, 3V3->10>9!, 5VSB->3 --
        # the offsets table must grow; see the assertion below.)
        self.assertGreater(r.get("vias", 0), 0)
        in2 = b.GetLayerID("In2.Cu")
        alt_segs = [t for t in b.GetTracks()
                    if t.GetClass() == "PCB_TRACK" and t.GetLayer() == in2]
        vias = [t for t in b.GetTracks() if t.GetClass() == "PCB_VIA"]
        self.assertTrue(alt_segs, "no inner-layer rail copper laid")
        self.assertTrue(all(t.IsLocked() for t in alt_segs + vias))

    def test_alt_passes_under_smd_foreign_on_band(self):
        # the same foreign position that rail-fatally REFUSED the face-mode
        # band (test_foreign_on_band_refuses_rail_loud) -- alt passes UNDER it
        b = _mkboard_alt(foreign_smd_on_band=(18.0, -0.5))
        rep = FR.lay_force_rails(b, verbose=False, alt_layer="In2.Cu")
        self.assertIsInstance(rep["RS2"], dict, rep["RS2"])

    def test_tht_foreign_on_band_still_refuses(self):
        # a THT barrel pierces every layer -- the alt band must refuse it
        b = _mkboard_alt()
        f = _fp(b, "U9")
        nets = {str(k): v for k, v in b.GetNetInfo().NetsByName().items()}
        _pad_tht(f, "1", nets["/FOREIGN"], 18.0, -0.5)
        rep = FR.lay_force_rails(b, verbose=False, alt_layer="In2.Cu")
        self.assertNotIsInstance(rep["RS2"], dict, rep["RS2"])
        self.assertIn("REFUSED", rep["RS2"])


if __name__ == "__main__":
    unittest.main()
