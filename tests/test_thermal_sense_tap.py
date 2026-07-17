#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# KELVIN SENSE-TAP current exclusion in the 2.5D electro-thermal solver
# (cec_thermal2d.solve_board_thermal + _kelvin_sense_drop_cells).
#
# THE BUG: the solver injects a current-carrying sense net's cable current across the ENTIRE
# net's copper, including the high-impedance KELVIN SENSE-TAP copper (the INA current-sense
# INPUT pads + the thin traces reaching them) that physically carries ZERO current. On a board
# whose Kelvin sense is MIS-ROUTED as a thin 0.2 mm strip bridging the connector and the shunt,
# the old solver drove the full cable current through that strip -> a fabricated ~1000 C hot
# neck while the wide force POUR sat cool and unused. Bad routing masqueraded as a thermal fail.
#
# THE FIX: on a high-current sense net that carries a high-Z INA input AND has a force pour, the
# current must flow ONLY along the force path (connector -> POUR -> shunt). Every routed-TRACK-
# only conductor on the net (the Kelvin tap, a mis-routed sense strip, stray copper) is dropped
# from the CURRENT graph; the filled ZONE and ALL PAD copper are kept. klat (heat conduction) is
# untouched. The Kelvin mis-route itself stays a routing fault caught by kelvin_topology_faults.
#
# TEETH (container, needs pcbnew): a board with a filled HI force pour whose shunt SINK is reached
# only through a thin mis-routed connector->shunt strip. WITH the fix the strip is no current
# carrier, so max_T stays sane (~ambient); WITHOUT it the strip is driven with the full cable
# current and max_T explodes to hundreds of C. Adding/removing the strip does not move max_T.

import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

try:
    import numpy as np
    import pcbnew
    import cec_thermal2d as t2
    from pcbnew import FromMM as MM, VECTOR2I
    HAVE = True
except Exception:                                            # noqa: BLE001
    HAVE = False

HI = "/SENSEC1_HI"
LO = "/SENSEC1_LO"
AMB = 50.0


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


def _trk(b, net, p0, p1, layer=None, wmm=0.20):
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


def _zone(b, net, x0, y0, x1, y1, layer=None):
    layer = pcbnew.F_Cu if layer is None else layer
    z = pcbnew.ZONE(b)
    ls = pcbnew.LSET(); ls.AddLayer(layer); z.SetLayerSet(ls)
    z.SetNet(net)
    z.SetLocalClearance(MM(0.2))
    z.SetMinThickness(MM(0.2))
    z.SetAssignedPriority(0)
    z.SetIsFilled(False)
    o = z.Outline()
    o.NewOutline()
    for (x, y) in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        o.Append(MM(x), MM(y))
    b.Add(z)
    return z


def _edge(b, x0, y0, x1, y1):
    g = pcbnew.PCB_SHAPE(b)
    g.SetShape(pcbnew.SHAPE_T_SEGMENT)
    g.SetLayer(pcbnew.Edge_Cuts)
    g.SetStart(VECTOR2I(MM(x0), MM(y0)))
    g.SetEnd(VECTOR2I(MM(x1), MM(y1)))
    b.Add(g)


def _build(path, *, strip):
    """EPS-cable-shaped board with a FILLED HI force pour. The pour covers the connector
    (PTH at y=7) but ENDS at y=20, leaving the shunt HI pad (y=25) OUTSIDE the pour -- the
    real bug's pour<->shunt gap. strip=True adds a thin 0.20 mm mis-routed connector->shunt
    sense strip (the only galvanic path to the shunt sink); strip=False omits it. INA238 with
    Vin+ on _HI taps the shunt (so the net carries a high-Z sense input -> the fix arms)."""
    b = pcbnew.CreateEmptyBoard()
    for x0, y0, x1, y1 in ((10, 0, 40, 0), (40, 0, 40, 40), (40, 40, 10, 40), (10, 40, 10, 0)):
        _edge(b, x0, y0, x1, y1)
    hi = pcbnew.NETINFO_ITEM(b, HI, 1); b.Add(hi)
    lo = pcbnew.NETINFO_ITEM(b, LO, 2); b.Add(lo)
    jin = _fp(b, "J_IN1", "Molex"); _pad_pth(jin, "5", hi, 25.0, 7.0)
    jout = _fp(b, "J_OUT1", "Molex"); _pad_pth(jout, "5", lo, 25.0, 35.0)
    rs = _fp(b, "RS1", "0.5mOhm")
    _pad_smd(rs, "1", hi, 25.0, 25.0, 1.23, 3.35)            # HI shunt terminal (OUTSIDE the pour)
    _pad_smd(rs, "2", lo, 25.0, 30.0, 1.23, 3.35)            # LO shunt terminal
    ina = _fp(b, "U10", "INA238")
    _pad_smd(ina, "10", hi, 28.0, 25.0, 1.45, 0.30)         # Vin+ (high-Z current sense)
    _pad_smd(ina, "9",  lo, 28.0, 27.0, 1.45, 0.30)         # Vin- (high-Z current sense)
    _pad_smd(ina, "8",  lo, 28.0, 29.0, 1.45, 0.30)         # Vbus (high-Z voltage tap)
    # FORCE POUR on _HI: covers the connector but stops short of the shunt (y<=20).
    _zone(b, hi, 18.0, 3.0, 32.0, 20.0)
    # legit thin Kelvin stub shunt-inner -> Vin+ (dead-ends at the high-Z INA input)
    _trk(b, hi, (25.0, 26.5), (28.0, 25.0))
    if strip:
        # THE BUG: a thin 0.20 mm sense strip bridges the pour edge to the shunt SINK -- the only
        # galvanic path connector->shunt, so the old solver funnels the whole cable current here.
        _trk(b, hi, (25.0, 20.0), (25.0, 25.0))
    # ZONE_FILLER segfaults on a freshly-created board; save + reload (so design settings init)
    # then fill, the same way the production tooling does it.
    pcbnew.SaveBoard(path, b)
    b = pcbnew.LoadBoard(path)
    b.BuildConnectivity()
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    pcbnew.SaveBoard(path, b)
    return path


@unittest.skipUnless(HAVE, "needs pcbnew (run in the routing container)")
class ThermalSenseTap(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cec_thermal_sense_")

    def _path(self, name):
        return os.path.join(self.tmp, name + ".kicad_pcb")

    def _solve(self, path):
        return t2.solve_board_thermal(
            path, net_currents={HI: 14.6}, grid_mm=0.4, ambient=AMB,
            h_eff=15.0, verbose=False)

    def test_mis_routed_strip_does_not_fabricate_a_neck(self):
        # THE TEETH: the full cable current must NOT be driven through the thin sense strip.
        res = self._solve(_build(self._path("strip"), strip=True))
        self.assertLess(res.max_T, AMB + 60.0,
                        "a mis-routed Kelvin sense strip must not fabricate a hot neck "
                        "(got max_T=%.1f C); current must stay on the force pour" % res.max_T)

    def test_thermal_independent_of_sense_strip(self):
        # The board's thermal is the SAME whether or not the thin sense-tap strip exists.
        t_with = self._solve(_build(self._path("with"), strip=True)).max_T
        t_without = self._solve(_build(self._path("without"), strip=False)).max_T
        self.assertAlmostEqual(
            t_with, t_without, delta=2.0,
            msg="max_T must not depend on the presence of the sense-tap strip "
                "(with=%.1f without=%.1f)" % (t_with, t_without))

    def test_drop_keeps_zones_and_pads_drops_tracks(self):
        # Unit-level: _kelvin_sense_drop_cells keeps pour + pad cells, drops only track-only cells.
        ny, nx = 6, 6

        class G:
            def __init__(s):
                s.nx = nx; s.ny = ny

            def idx(s, ix, iy):
                return iy * s.nx + ix
        g = G()
        full = np.zeros((ny, nx), bool); full[1:4, 1:4] = True   # net copper block
        zone = np.zeros((ny, nx), bool); zone[1:3, 1:3] = True   # pour
        pad = np.zeros((ny, nx), bool);  pad[3, 3] = True        # a pad cell
        # remaining net copper that is neither zone nor pad == track-only -> must be dropped
        drop = t2._kelvin_sense_drop_cells({0: full}, {0: zone}, {0: pad}, g)
        dropped = {c for (ph, c) in drop}
        self.assertIn(g.idx(3, 1), dropped, "track-only cell must be dropped")
        self.assertNotIn(g.idx(1, 1), dropped, "pour (zone) cell must be kept")
        self.assertNotIn(g.idx(3, 3), dropped, "pad cell must be kept")


if __name__ == "__main__":
    unittest.main()
