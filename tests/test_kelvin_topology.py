#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Kelvin FOUR-WIRE TOPOLOGY gate (cec_score.kelvin_topology_faults, folded into kelvin_ok).
#
# THE HOLE: on a cable interposer the cable connector pad (J_IN/J_OUT), the shunt terminal pad
# (RS*) and the current-sense IC input pad (INA*) are ALL the same net (/SENSEC*_HI|_LO). The
# pre-existing kelvin_ok gate (cec_score._check_pairs) passes a leg on routed>=1 track + 0
# ratlines, so the router can satisfy the INA input by tying it to the NEAREST net point -- the
# connector -- and kelvin_ok still reads True. That is NOT a four-wire Kelvin: the sense then
# spans the connector->shunt force trace + contact R and carries load current.
#
# THE GATE: build the conductor graph (tracks + vias, ZONES EXCLUDED), CUT the shunt pad, and
# FAIL when an INA current-sense input (Vin+/Vin-; the INA226/228/238 Vbus high-Z pad is
# excluded) still reaches a cable-connector pad -- a parallel sense-through-connector path.
#
# TEETH (container, needs pcbnew): a synthetic board with proper inner-edge stubs + a legit
# high-Z Vbus->connector route PASSES (kelvin_ok True, 0 topology faults); add ONE parallel
# Vin+->connector bypass and the gate FAILs (kelvin_ok flips False). N/A on a board with no
# per-cable connector/shunt/INA triple.

import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

try:
    import pcbnew
    import cec_score
    from pcbnew import FromMM as MM, VECTOR2I
    HAVE = True
except Exception:                                              # noqa: BLE001
    HAVE = False

HI = "/SENSEC1_HI"
LO = "/SENSEC1_LO"
PAIR = [(HI, LO)]


def _pad_smd(fp, name, net, x, y, wmm, hmm):
    p = pcbnew.PAD(fp)
    p.SetNumber(name)
    p.SetShape(pcbnew.PAD_SHAPE_RECT)
    p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    p.SetSize(VECTOR2I(MM(wmm), MM(hmm)))
    ls = pcbnew.LSET(); ls.AddLayer(pcbnew.F_Cu); p.SetLayerSet(ls)
    p.SetPosition(VECTOR2I(MM(x), MM(y)))
    p.SetNet(net)
    fp.Add(p)


def _pad_pth(fp, name, net, x, y, dmm=1.5, padmm=2.36):
    p = pcbnew.PAD(fp)
    p.SetNumber(name)
    p.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    p.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    p.SetSize(VECTOR2I(MM(padmm), MM(padmm)))
    p.SetDrillSize(VECTOR2I(MM(dmm), MM(dmm)))
    p.SetLayerSet(pcbnew.LSET.AllCuMask())
    p.SetPosition(VECTOR2I(MM(x), MM(y)))
    p.SetNet(net)
    fp.Add(p)


def _trk(b, net, p0, p1, layer=None, wmm=0.25):
    layer = pcbnew.F_Cu if layer is None else layer
    t = pcbnew.PCB_TRACK(b)
    t.SetStart(VECTOR2I(MM(p0[0]), MM(p0[1])))
    t.SetEnd(VECTOR2I(MM(p1[0]), MM(p1[1])))
    t.SetWidth(MM(wmm)); t.SetLayer(layer); t.SetNet(net)
    b.Add(t)


def _fp(b, ref, val):
    fp = pcbnew.FOOTPRINT(b)
    fp.SetReference(ref); fp.SetValue(val)
    b.Add(fp)
    return fp


def _build(path, *, bad, triple=True):
    """EPS-cable-shaped board. triple=True -> J connector / 2-pad shunt / INA238 with Vin+ on _HI,
    Vin- + Vbus on _LO; GOOD = force-to-shunt + inner-edge stubs + a legit Vbus->connector route;
    bad=True adds a parallel Vin+->connector bypass. triple=False omits the shunt -> N/A board."""
    b = pcbnew.CreateEmptyBoard()
    hi = pcbnew.NETINFO_ITEM(b, HI, 1); b.Add(hi)
    lo = pcbnew.NETINFO_ITEM(b, LO, 2); b.Add(lo)
    jin = _fp(b, "J_IN1", "Molex");  _pad_pth(jin, "5", hi, 40.0, 7.0)
    jout = _fp(b, "J_OUT1", "Molex"); _pad_pth(jout, "5", lo, 40.0, 33.0)
    ina = _fp(b, "U10", "INA238")
    _pad_smd(ina, "10", hi, 37.0, 19.0, 1.45, 0.30)            # Vin+ (current sense)
    _pad_smd(ina, "9",  lo, 37.0, 20.5, 1.45, 0.30)            # Vin- (current sense)
    _pad_smd(ina, "8",  lo, 37.0, 22.0, 1.45, 0.30)            # Vbus (high-Z voltage tap)
    if triple:
        rs = _fp(b, "RS1", "0.5mOhm")
        _pad_smd(rs, "1", hi, 40.0, 16.5, 1.23, 3.35)         # HI terminal (y 14.8..18.2)
        _pad_smd(rs, "2", lo, 40.0, 23.0, 1.23, 3.35)         # LO terminal (y 21.3..24.7)
        _trk(b, hi, (40.0, 7.0),  (40.0, 16.5))               # force: connector -> shunt HI
        _trk(b, lo, (40.0, 33.0), (40.0, 23.0))               # force: connector -> shunt LO
        _trk(b, hi, (40.0, 18.0), (37.0, 19.0))               # GOOD stub: shunt HI inner -> Vin+
        _trk(b, lo, (40.0, 21.5), (37.0, 20.5))               # GOOD stub: shunt LO inner -> Vin-
        # legit high-Z Vbus tap routed to the connector (must NOT be flagged)
        _trk(b, lo, (37.0, 22.0), (34.0, 22.0))
        _trk(b, lo, (34.0, 22.0), (34.0, 33.0))
        _trk(b, lo, (34.0, 33.0), (40.0, 33.0))
    if bad:
        # the bug: parallel sense-through-connector path on _HI, avoiding the shunt (x<=33)
        _trk(b, hi, (37.0, 19.0), (33.0, 19.0))
        _trk(b, hi, (33.0, 19.0), (33.0, 7.0))
        _trk(b, hi, (33.0, 7.0),  (40.0, 7.0))
    pcbnew.SaveBoard(path, b)
    return path


@unittest.skipUnless(HAVE, "needs pcbnew (run in the routing container)")
class KelvinTopology(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cec_kelvin_topo_")

    def _path(self, name):
        return os.path.join(self.tmp, name + ".kicad_pcb")

    def test_good_tap_passes(self):
        b = pcbnew.LoadBoard(_build(self._path("good"), bad=False))
        fn, reasons, detail, checked = cec_score.kelvin_topology_faults(b, PAIR)
        self.assertEqual(checked, 2, "both _HI and _LO carry the connector/shunt/INA triple")
        self.assertEqual(len(detail), 0, "clean four-wire tap has no topology fault: %s" % reasons)

    def test_good_tap_kelvin_ok_true(self):
        m = cec_score.score(_build(self._path("good2"), bad=False))
        self.assertTrue(m.kelvin_ok, "a clean tap (0 ratlines, no bypass) must read kelvin_ok=True")
        self.assertEqual(m.detail["kelvin_topology_checked"], 2)
        self.assertEqual(m.detail["kelvin_topology_faults"], [])

    def test_bypass_is_caught(self):
        b = pcbnew.LoadBoard(_build(self._path("bad"), bad=True))
        fn, reasons, detail, checked = cec_score.kelvin_topology_faults(b, PAIR)
        self.assertIn(HI, fn, "the Vin+ parallel-to-connector bypass must fault /SENSEC1_HI")
        self.assertTrue(any("U10.10" in r and "J_IN1" in r for r in reasons), reasons)

    def test_bypass_flips_kelvin_ok_false(self):
        # THE TEETH: the same board passes _check_pairs (routed, 0 ratlines) but the topology gate
        # must drag kelvin_ok (and gates_pass) to False.
        m = cec_score.score(_build(self._path("bad2"), bad=True))
        self.assertFalse(m.kelvin_ok, "a current-carrying sense must fail kelvin_ok")
        self.assertFalse(m.gates_pass)
        self.assertTrue(m.detail["kelvin_topology_faults"])

    def test_vbus_not_flagged(self):
        # the GOOD board routes the INA238 Vbus (pad 8, high-Z) straight to the connector; that is a
        # legitimate voltage tap and must NOT be reported as a current-carrying-sense fault.
        b = pcbnew.LoadBoard(_build(self._path("vbus"), bad=False))
        _fn, _r, detail, _c = cec_score.kelvin_topology_faults(b, PAIR)
        self.assertFalse(any(d["ina"].endswith(".8") for d in detail),
                         "Vbus (pad 8) must be excluded from the Kelvin current-sense gate")

    def test_summary_na_without_triple(self):
        # no shunt -> no per-cable triple -> the gate is N/A (vacuous), never a false-fail.
        s = cec_score.kelvin_topology_summary(_build(self._path("na"), bad=False, triple=False))
        self.assertFalse(s["applicable"])
        self.assertEqual(s["n_faults"], 0)

    def test_summary_reports_faults(self):
        s = cec_score.kelvin_topology_summary(_build(self._path("badsum"), bad=True))
        self.assertTrue(s["applicable"])
        self.assertGreaterEqual(s["n_faults"], 1)
        self.assertIn(HI, s["by_net"])


if __name__ == "__main__":
    unittest.main()
