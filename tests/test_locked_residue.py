#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Teeth for the 2026-07-14 locked-cell bulldozing round's RESIDUE items
# (cec_fr): (b) partial_locked_keepouts -- partially-owned nets' lane copper
# bakes as keepouts with pad-access windows; (a) locked_mutual_collisions --
# the locked lay is audited against ITSELF. Synthetic boards via the
# test_kelvin_topology construction pattern; pcbnew-gated.
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

try:
    import pcbnew
    from pcbnew import VECTOR2I
    HAVE_PCBNEW = True
    import cec_fr
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


def _trk(b, net, p0, p1, *, locked, wmm=2.0):
    t = pcbnew.PCB_TRACK(b)
    t.SetStart(VECTOR2I(MM(p0[0]), MM(p0[1])))
    t.SetEnd(VECTOR2I(MM(p1[0]), MM(p1[1])))
    t.SetWidth(MM(wmm))
    t.SetLayer(pcbnew.F_Cu)
    t.SetNet(net)
    t.SetLocked(locked)
    b.Add(t)
    return t


def _save(b):
    fd, path = tempfile.mkstemp(suffix=".kicad_pcb")
    os.close(fd)
    pcbnew.SaveBoard(path, b)
    return path


def _covers(rects, x_mm, y_mm, layer="F.Cu"):
    return any(r["x0"] <= x_mm <= r["x1"] and r["y0"] <= y_mm <= r["y1"]
               for r in rects if layer in r["layers"])


@unittest.skipUnless(HAVE_PCBNEW, "pcbnew required")
class TestPartialLockedKeepouts(unittest.TestCase):
    def _fan_board(self):
        """/FAN-shaped net: locked lane (10,10)->(30,10); pad A at the lane start
        (COVERED by the endpoint), pad B mid-lane at (20,10) with NO endpoint
        touching it (UNCOVERED -- the fan-gate spur class FR must still reach)."""
        b = pcbnew.CreateEmptyBoard()
        fan = pcbnew.NETINFO_ITEM(b, "/FAN_12V", 1)
        b.Add(fan)
        fp = _fp(b, "J2")
        _pad(fp, "1", fan, 10.0, 10.0)          # covered (lane endpoint)
        _pad(fp, "2", fan, 20.0, 10.0)          # uncovered mid-lane spur pad
        _trk(b, fan, (10.0, 10.0), (30.0, 10.0), locked=True)
        return _save(b)

    def test_lane_covered_except_pad_window(self):
        p = self._fan_board()
        try:
            ko = cec_fr.partial_locked_keepouts(p)
        finally:
            os.unlink(p)
        self.assertTrue(ko, "partial net's locked lane must produce keepouts")
        self.assertTrue(_covers(ko, 14.0, 10.0), "lane body left of the window stays covered")
        self.assertTrue(_covers(ko, 26.0, 10.0), "lane body right of the window stays covered")
        self.assertFalse(_covers(ko, 20.0, 10.0),
                         "the uncovered pad's ACCESS WINDOW must be open (FR reaches it)")

    def test_fully_owned_net_excluded(self):
        p = self._fan_board()
        try:
            ko = cec_fr.partial_locked_keepouts(p, exclude_nets={"/FAN_12V"})
        finally:
            os.unlink(p)
        self.assertEqual(ko, [], "fully-owned nets are locked_copper_keepouts' business")

    def test_unlocked_copper_ignored(self):
        b = pcbnew.CreateEmptyBoard()
        n = pcbnew.NETINFO_ITEM(b, "/X", 1)
        b.Add(n)
        fp = _fp(b, "R1")
        _pad(fp, "1", n, 5.0, 5.0)
        _pad(fp, "2", n, 40.0, 40.0)
        _trk(b, n, (5.0, 5.0), (15.0, 5.0), locked=False)
        p = _save(b)
        try:
            self.assertEqual(cec_fr.partial_locked_keepouts(p), [])
        finally:
            os.unlink(p)


@unittest.skipUnless(HAVE_PCBNEW, "pcbnew required")
class TestLockedMutualCollisions(unittest.TestCase):
    def _two_net_board(self, *, cross):
        b = pcbnew.CreateEmptyBoard()
        na = pcbnew.NETINFO_ITEM(b, "/LANE_A", 1)
        nb = pcbnew.NETINFO_ITEM(b, "/LANE_B", 2)
        b.Add(na)
        b.Add(nb)
        fp = _fp(b, "J1")
        _pad(fp, "1", na, 10.0, 10.0)
        _pad(fp, "2", nb, 20.0, 5.0)
        _trk(b, na, (10.0, 10.0), (30.0, 10.0), locked=True)
        if cross:
            _trk(b, nb, (20.0, 5.0), (20.0, 15.0), locked=True)     # crosses A
        else:
            _trk(b, nb, (10.0, 30.0), (30.0, 30.0), locked=True)    # far away
        return _save(b)

    def test_crossing_locked_nets_fire(self):
        p = self._two_net_board(cross=True)
        try:
            hits = cec_fr.locked_mutual_collisions(p)
        finally:
            os.unlink(p)
        self.assertGreaterEqual(len(hits), 1)
        self.assertEqual({hits[0]["a"], hits[0]["b"]}, {"/LANE_A", "/LANE_B"})

    def test_separated_locked_nets_clean(self):
        p = self._two_net_board(cross=False)
        try:
            self.assertEqual(cec_fr.locked_mutual_collisions(p), [])
        finally:
            os.unlink(p)

    def test_same_net_never_fires(self):
        b = pcbnew.CreateEmptyBoard()
        n = pcbnew.NETINFO_ITEM(b, "/LANE_A", 1)
        b.Add(n)
        fp = _fp(b, "J1")
        _pad(fp, "1", n, 10.0, 10.0)
        _trk(b, n, (10.0, 10.0), (30.0, 10.0), locked=True)
        _trk(b, n, (20.0, 5.0), (20.0, 15.0), locked=True)
        p = _save(b)
        try:
            self.assertEqual(cec_fr.locked_mutual_collisions(p), [])
        finally:
            os.unlink(p)


if __name__ == "__main__":
    unittest.main()
