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


def _via(b, net, x, y, *, locked, diameter_mm=0.9, drill_mm=0.5):
    v = pcbnew.PCB_VIA(b)
    v.SetPosition(VECTOR2I(MM(x), MM(y)))
    v.SetWidth(MM(diameter_mm))
    v.SetDrill(MM(drill_mm))
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    v.SetNet(net)
    v.SetLocked(locked)
    b.Add(v)
    return v


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

    def test_pad_window_never_erases_locked_via_barrel(self):
        b = pcbnew.CreateEmptyBoard()
        net = pcbnew.NETINFO_ITEM(b, "/PARTIAL", 1)
        b.Add(net)
        fp = _fp(b, "U1")
        _pad(fp, "1", net, 10.0, 10.0)
        _pad(fp, "2", net, 20.0, 10.0)
        _trk(b, net, (10.0, 10.0), (15.0, 10.0), locked=True,
             wmm=0.25)
        _via(b, net, 20.0, 10.0, locked=True)
        path = _save(b)
        try:
            rows = cec_fr.partial_locked_keepouts(path)
        finally:
            os.unlink(path)

        self.assertTrue(_covers(rows, 20.0, 10.0, "F.Cu"), rows)
        self.assertTrue(_covers(rows, 20.0, 10.0, "B.Cu"), rows)
        self.assertTrue(any(row["name"].startswith("lockedvia-part-")
                            for row in rows), rows)

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

    def test_fully_owned_keepouts_include_unlocked_physical_copper(self):
        b = pcbnew.CreateEmptyBoard()
        owned = pcbnew.NETINFO_ITEM(b, "/OWNED", 1)
        other = pcbnew.NETINFO_ITEM(b, "/OTHER", 2)
        b.Add(owned)
        b.Add(other)
        owned_fp = _fp(b, "U1")
        _pad(owned_fp, "1", owned, 40.0, 40.0)
        other_fp = _fp(b, "U2")
        _pad(other_fp, "1", other, 40.0, 30.0)
        _trk(b, owned, (5.0, 5.0), (15.0, 5.0), locked=True)
        _trk(b, owned, (20.0, 5.0), (30.0, 5.0), locked=False)
        _trk(b, other, (5.0, 20.0), (15.0, 20.0), locked=False)
        p = _save(b)
        try:
            owned_rows = cec_fr.locked_copper_keepouts(
                p, only_nets={"/OWNED"})
            legacy_rows = cec_fr.locked_copper_keepouts(p)
        finally:
            os.unlink(p)

        self.assertTrue(_covers(owned_rows, 10.0, 5.0))
        self.assertTrue(_covers(owned_rows, 25.0, 5.0),
                        "owned unlocked copper must remain a foreign obstacle")
        self.assertTrue(_covers(owned_rows, 40.0, 40.0),
                        "DSN-excluded owned pads must remain physical obstacles")
        self.assertFalse(_covers(owned_rows, 10.0, 20.0))
        self.assertFalse(_covers(owned_rows, 40.0, 30.0))
        self.assertTrue(_covers(legacy_rows, 10.0, 5.0))
        self.assertFalse(_covers(legacy_rows, 25.0, 5.0),
                         "no ownership set retains locked-only semantics")


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
