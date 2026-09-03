#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# BLUEPRINT KELVIN TAP DISCIPLINE teeth (owner ruling 2026-07-25, recorded at the end of
# docs/slab-pour-design-2026-07-24.md; measured double-lay: wave s464 carried the tap
# synthesizer's LOCKED straight-DIAGONAL to the INA181 on top of every stamped cell's
# authored orthogonal taps, because cec_precision_route ran synthesize_kelvin_taps with
# no coverage handshake).
#
# The discipline under test (all inside cec_fr.synthesize_kelvin_taps, so EVERY caller
# inherits it -- precision, import_ses, direct):
#   1. COVERED-LEG SKIP: an IC input pad already contacted by LOCKED same-net copper
#      (endpoint HitTest at the track's half-width) is the stamped cell's authored tap;
#      the leg is skipped and reported under 'covered' -- never double-laid.
#   2. ENDPOINT TOLERANCE: _locked_pad_contact catches an authored tap whose endpoint
#      sits ON the pad edge (within half a track width), not only dead-center.
#   3. CANONICAL-OR-REFUSE on locked-copper pairs: no straight-diagonal, no dogleg, no
#      vbus bridge -- the textbook orthogonal shape or a LOUD named refusal.
#   4. LEGACY LADDER PRESERVED where the pair's nets carry no locked copper (the eps
#      golden path): the straight-diagonal fallback and the vbus bridge still lay.
#
# Container-only (pcbnew).
import math
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

try:
    import pcbnew
    from pcbnew import FromMM as MM, VECTOR2I
    import cec_fr
    HAVE = True
except Exception:                                              # noqa: BLE001
    HAVE = False

HI = "/SENSEC1_HI"
LO = "/SENSEC1_LO"
PAIR = [(HI, LO)]


def _fp(b, ref, val):
    fp = pcbnew.FOOTPRINT(b)
    fp.SetReference(ref)
    fp.SetValue(val)
    b.Add(fp)
    return fp


def _pad_smd(fp, name, net, x, y, wmm, hmm):
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


def _trk(b, net, p0, p1, wmm=0.25, locked=False):
    t = pcbnew.PCB_TRACK(b)
    t.SetStart(VECTOR2I(MM(p0[0]), MM(p0[1])))
    t.SetEnd(VECTOR2I(MM(p1[0]), MM(p1[1])))
    t.SetWidth(MM(wmm))
    t.SetLayer(pcbnew.F_Cu)
    t.SetNet(net)
    t.SetLocked(locked)
    b.Add(t)
    return t


def _snap(b):
    """{(sx, sy, ex, ey, net)} of every PCB_TRACK, mm-rounded."""
    out = set()
    for t in b.GetTracks():
        if t.GetClass() != "PCB_TRACK":
            continue
        s, e = t.GetStart(), t.GetEnd()
        out.add((round(s.x / 1e6, 4), round(s.y / 1e6, 4),
                 round(e.x / 1e6, 4), round(e.y / 1e6, 4), t.GetNetname()))
    return out


def _is_ortho(seg):
    sx, sy, ex, ey, _n = seg
    return abs(sx - ex) < 1e-6 or abs(sy - ey) < 1e-6


def _angle_deg(seg):
    sx, sy, ex, ey, _n = seg
    return abs(math.degrees(math.atan2(ey - sy, ex - sx))) % 180.0


class _Board:
    """The synthetic straddle-shunt + INA238 cell every case shares.

    RS1 pads: HI (10,10), LO (16,10), 1.8x3.4 -- pad axis +x.
    U20 (value INA238): pad 10/IN+ on HI at (13,6); pad 9/IN- on LO at (13,13.5);
    pad 8/Vbus on LO at (13,14.6). Canonical shapes exist for both legs:
      HI: (10.78,10) -> (11.68,10) -> (11.68,6) -> (13,6)
      LO: (15.22,10) -> (14.32,10) -> (14.32,13.5) -> (13,13.5)
    """

    def __init__(self):
        self.b = pcbnew.CreateEmptyBoard()
        self.hi = pcbnew.NETINFO_ITEM(self.b, HI, 1)
        self.b.Add(self.hi)
        self.lo = pcbnew.NETINFO_ITEM(self.b, LO, 2)
        self.b.Add(self.lo)
        self.gnd = pcbnew.NETINFO_ITEM(self.b, "GND", 3)
        self.b.Add(self.gnd)
        rs = _fp(self.b, "RS1", "0.5mOhm")
        _pad_smd(rs, "1", self.hi, 10.0, 10.0, 1.8, 3.4)
        _pad_smd(rs, "2", self.lo, 16.0, 10.0, 1.8, 3.4)
        ina = _fp(self.b, "U20", "INA238")
        self.p10 = _pad_smd(ina, "10", self.hi, 13.0, 6.0, 0.8, 0.8)
        self.p9 = _pad_smd(ina, "9", self.lo, 13.0, 13.5, 0.8, 0.8)
        self.p8 = _pad_smd(ina, "8", self.lo, 13.0, 14.6, 0.8, 0.8)

    def locked_trunk(self):
        """Locked HI copper far from every pad -- rails/stamped-cell presence marker."""
        _trk(self.b, self.hi, (5.0, 20.0), (6.0, 20.0), wmm=1.5, locked=True)

    def gnd_blocker(self):
        """A small GND pad dead-on the HI canonical vertical leg (x=11.68, y 6..10),
        placed to leave the straight diagonal (10.78,10)->(13,6) CLEAR."""
        r99 = _fp(self.b, "R99", "GND-blocker")
        _pad_smd(r99, "1", self.gnd, 11.68, 6.6, 0.4, 0.4)

    def gnd_canonical_wall(self):
        """Block every legal package-normal HI run while naming one obstacle."""
        r99 = _fp(self.b, "R99", "GND-canonical-wall")
        _pad_smd(r99, "1", self.gnd, 12.0, 8.0, 4.0, 0.4)

    def synth(self):
        return cec_fr.synthesize_kelvin_taps(self.b, kelvin_pairs=PAIR)


@unittest.skipUnless(HAVE, "needs pcbnew (run in the routing container)")
class CoveredSkip(unittest.TestCase):
    def test_different_sense_pad_requires_full_route_clearance(self):
        """A different sense net is not ordinary foreign copper, but it still
        must meet the board clearance; overlap-only checking is insufficient."""
        w = _Board()
        near_hi = _fp(w.b, "U98", "sense-neighbor")
        _pad_smd(near_hi, "1", w.hi, 15.0, 10.0, 1.0, 1.0)
        start = VECTOR2I(MM(13.0), MM(10.70))
        end = VECTOR2I(MM(17.0), MM(10.70))

        self.assertTrue(cec_fr._tap_pair_overlap_clear(
            w.b, start, end, MM(0.20), pcbnew.F_Cu,
            w.lo.GetNetCode(), {w.hi.GetNetCode(), w.lo.GetNetCode()}),
            "the legacy overlap-only probe sees the 0.10 mm gap")
        self.assertFalse(cec_fr._tap_pair_overlap_clear(
            w.b, start, end, MM(0.20), pcbnew.F_Cu,
            w.lo.GetNetCode(), {w.hi.GetNetCode(), w.lo.GetNetCode()},
            clearance_nm=MM(0.20)),
            "precision routing must reject the same sub-rule gap")

    def test_known_out_of_range_input_is_named_placement_refusal(self):
        """A router-excluded INA input may never disappear behind a distance filter."""
        w = _Board()
        far = _fp(w.b, "U99", "INA238")
        _pad_smd(far, "10", w.hi, 30.0, 30.0, 0.8, 0.8)
        _pad_smd(far, "9", w.lo, 30.0, 31.0, 0.8, 0.8)

        report = cec_fr.synthesize_kelvin_taps(
            w.b, kelvin_pairs=PAIR, max_ic_mm=9.0)

        hi = report.get("refused", {}).get(HI) or []
        lo = report.get("refused", {}).get(LO) or []
        self.assertTrue(any("RS1->U99.10 OUT-OF-RANGE" in row
                            for row in hi), report)
        self.assertTrue(any("RS1->U99.9 OUT-OF-RANGE" in row
                            for row in lo), report)
        details = {row["target_pad"]: row
                   for row in report["refused_details"]
                   if row["target_ref"] == "U99"}
        self.assertGreater(details["10"]["required_closer_mm"], 0.0)
        self.assertGreater(details["9"]["required_closer_mm"], 0.0)

    def test_pending_foreign_tap_crossing_is_detected_before_lay(self):
        w = _Board()
        pending = [
            ([VECTOR2I(MM(10), MM(10)), VECTOR2I(MM(20), MM(10))],
             w.hi.GetNetCode(), HI, "hi-leg", pcbnew.F_Cu)]
        crossing = [VECTOR2I(MM(15), MM(5)), VECTOR2I(MM(15), MM(15))]
        clear = [VECTOR2I(MM(15), MM(12)), VECTOR2I(MM(20), MM(12))]

        self.assertIn("pending Kelvin leg", cec_fr._tap_pending_collider(
            crossing, w.lo.GetNetCode(), pcbnew.F_Cu, pending,
            MM(0.25), MM(0.20)))
        self.assertIsNone(cec_fr._tap_pending_collider(
            clear, w.lo.GetNetCode(), pcbnew.F_Cu, pending,
            MM(0.25), MM(0.20)))
        self.assertIsNone(cec_fr._tap_pending_collider(
            crossing, w.hi.GetNetCode(), pcbnew.F_Cu, pending,
            MM(0.25), MM(0.20)), "same-net overlap is coalesced later")

    def test_future_power_reservation_blocks_only_foreign_current_net(self):
        path = [VECTOR2I(MM(10), MM(10)),
                VECTOR2I(MM(20), MM(10))]
        reservation = {
            "x0": 14.0, "y0": 9.5, "x1": 16.0, "y1": 10.5,
            "layer": "F.Cu", "net": HI, "name": "future-hi",
        }

        foreign = cec_fr._tap_reservation_hits(
            path, [reservation], net=LO, layer="F.Cu",
            width_nm=MM(0.25), clearance_nm=MM(0.20))
        own = cec_fr._tap_reservation_hits(
            path, [reservation], net=HI, layer="F.Cu",
            width_nm=MM(0.25), clearance_nm=MM(0.20))

        self.assertEqual(len(foreign), 1)
        self.assertEqual(foreign[0]["kind"],
                         "future_power_reservation")
        self.assertEqual(foreign[0]["net"], HI)
        self.assertEqual(own, [], "same-net tap must merge into its pour")

    def test_covered_pair_skips_synthesis_entirely(self):
        """Authored (locked, pad-contacting) taps on both legs -> nothing laid, both
        legs reported covered -- the s464 double-lay class is dead."""
        w = _Board()
        _trk(w.b, w.hi, (11.68, 6.0), (13.0, 6.0), locked=True)     # ends ON pad 10
        _trk(w.b, w.lo, (14.32, 13.5), (13.0, 13.5), locked=True)   # ends ON pad 9
        before = _snap(w.b)
        rep = w.synth()
        self.assertEqual(rep["taps"], 0, rep)
        self.assertEqual(_snap(w.b), before, "covered pair must lay NOTHING")
        cov = rep.get("covered", {})
        self.assertTrue(cov.get(HI) and cov.get(LO), "both legs reported covered: %s" % cov)
        self.assertFalse(rep["refused"], "coverage is not a refusal")

    def test_partially_covered_pair_lays_only_the_missing_leg(self):
        """Per-LEG grain: HI covered, LO not -> only the LO leg is laid (canonical --
        the pair is in locked mode via the covering track itself)."""
        w = _Board()
        _trk(w.b, w.hi, (11.68, 6.0), (13.0, 6.0), locked=True)     # HI covered
        before = _snap(w.b)
        rep = w.synth()
        new = _snap(w.b) - before
        self.assertTrue(rep.get("covered", {}).get(HI))
        self.assertTrue(all(n == LO for *_xy, n in new),
                        "only LO-leg copper may be laid: %s" % new)
        self.assertTrue(new, "the uncovered LO leg must still be handled")
        self.assertTrue(all(_is_ortho(s) for s in new),
                        "locked-mode legs are canonical (orthogonal): %s" % new)


@unittest.skipUnless(HAVE, "needs pcbnew (run in the routing container)")
class EndpointTolerance(unittest.TestCase):
    def test_edge_terminated_tap_detected_within_half_width(self):
        """Pad 10 spans y 5.6..6.4; a locked 0.4mm track ending at y=6.55 sits 0.15mm
        OFF the pad -- inside the half-width (0.2) tolerance -> covered."""
        w = _Board()
        t = _trk(w.b, w.hi, (13.0, 9.0), (13.0, 6.55), wmm=0.4, locked=True)
        self.assertTrue(cec_fr._locked_pad_contact(w.b, w.p10))
        rep = w.synth()
        self.assertTrue(rep.get("covered", {}).get(HI),
                        "edge-terminated authored tap must count as coverage: %s" % rep)
        t.SetWidth(MM(0.2))                       # half-width 0.1 < the 0.15 gap
        self.assertFalse(cec_fr._locked_pad_contact(w.b, w.p10),
                         "beyond half-width is NOT contact")

    def test_unlocked_contact_is_not_coverage(self):
        w = _Board()
        _trk(w.b, w.hi, (11.68, 6.0), (13.0, 6.0), locked=False)
        self.assertFalse(cec_fr._locked_pad_contact(w.b, w.p10))


@unittest.skipUnless(HAVE, "needs pcbnew (run in the routing container)")
class CanonicalOrRefuse(unittest.TestCase):
    def test_locked_mode_lays_canonical_only_all_orthogonal(self):
        w = _Board()
        w.locked_trunk()
        before = _snap(w.b)
        rep = w.synth()
        new = _snap(w.b) - before
        self.assertTrue(new, "canonical taps must lay")
        bad = [s for s in new if not _is_ortho(s)]
        self.assertFalse(bad, "locked-mode geometry must be textbook-orthogonal "
                              "(no 45s, no diagonals): %s" % bad)
        self.assertFalse(rep["refused"], rep)
        labels = [x for v in rep["by_net"].values() for x in v]
        self.assertTrue(all("(canonical)" in x for x in labels), labels)

    def test_locked_mode_tries_bounded_canonical_run_variants(self):
        """A blocked 0.9 mm lane may use another package-normal run length.

        This remains the same three-leg textbook topology; it is not permission
        to use the unrestricted dogleg/diagonal fallback on stamped cells.
        """
        w = _Board()
        w.locked_trunk()
        w.gnd_blocker()
        before = _snap(w.b)
        rep = w.synth()
        new = _snap(w.b) - before
        hi = [segment for segment in new if segment[4] == HI]
        self.assertTrue(hi, rep)
        self.assertTrue(all(_is_ortho(segment) for segment in hi), hi)
        self.assertFalse(rep["refused"].get(HI), rep)

    def test_locked_mode_suppresses_vbus_bridge(self):
        w = _Board()
        w.locked_trunk()
        before = _snap(w.b)
        w.synth()
        new = _snap(w.b) - before
        on_p8 = [s for s in new
                 if w.p8.HitTest(VECTOR2I(MM(s[0]), MM(s[1])))
                 or w.p8.HitTest(VECTOR2I(MM(s[2]), MM(s[3])))]
        self.assertFalse(on_p8, "no vbus-bridge shapes on a stamped cell: %s" % on_p8)

    def test_blocked_canonical_refuses_loud_named_no_diagonal(self):
        """The teeth against the owner's render evidence: canonical blocked -> the
        pre-fix behavior laid the straight DIAGONAL to the IN pad; now the pair
        REFUSES with the blocker NAMED and lays nothing on that net."""
        w = _Board()
        w.locked_trunk()
        w.gnd_canonical_wall()
        before = _snap(w.b)
        rep = w.synth()
        new = _snap(w.b) - before
        self.assertFalse([s for s in new if s[4] == HI],
                         "refused HI leg must lay NOTHING: %s" % new)
        self.assertFalse([s for s in new if not _is_ortho(s)],
                         "no diagonal may appear anywhere in locked mode")
        ref = rep["refused"].get(HI) or []
        self.assertTrue(ref, "HI must be refused: %s" % rep)
        self.assertIn("CANONICAL-REFUSED", ref[0])
        self.assertIn("R99", ref[0], "the refusal must NAME the blocking item: %s" % ref)
        details = [row for row in rep["refused_details"]
                   if row.get("net") == HI]
        self.assertEqual(len(details), 1, rep)
        self.assertEqual(details[0]["reason"], ref[0])
        self.assertEqual(details[0]["reason_kind"], "kelvin_path_blocked")
        self.assertIn("R99", details[0]["blocker_refs"])
        blocker = next(row for row in details[0]["blocker_details"]
                       if row.get("ref") == "R99")
        self.assertEqual(blocker["path_kind"], "canonical")
        self.assertEqual(len(blocker["leg_start_mm"]), 2)

    def test_legacy_board_keeps_the_fallback_ladder(self):
        """Same blocked-canonical geometry WITHOUT locked copper (the eps golden
        path): the straight-diagonal fallback still lays and the vbus bridge still
        lays -- golden behavior preserved by the locked-copper gate."""
        w = _Board()
        w.gnd_blocker()
        before = _snap(w.b)
        rep = w.synth()
        new = _snap(w.b) - before
        diag_hi = [s for s in new if s[4] == HI and not _is_ortho(s)]
        self.assertTrue(diag_hi, "legacy mode must still lay the straight fallback "
                                 "(diagonal): %s" % sorted(new))
        self.assertAlmostEqual(_angle_deg(diag_hi[0]) % 90.0,
                               _angle_deg(diag_hi[0]) % 90.0)  # smoke: angle computes
        on_p8 = [s for s in new
                 if w.p8.HitTest(VECTOR2I(MM(s[0]), MM(s[1])))
                 or w.p8.HitTest(VECTOR2I(MM(s[2]), MM(s[3])))]
        self.assertTrue(on_p8, "legacy vbus bridge must still lay")
        self.assertFalse(rep["refused"], rep)


TAPS_TPL = os.path.normpath(os.path.join(
    HERE, "..", "beta", "atx-24pin-rev3", "blueprints", "sense-rail-v0-taps.json"))


@unittest.skipUnless(os.path.isfile(TAPS_TPL), "authored-taps template required")
class AuthoredTapForm(unittest.TestCase):
    """The v5 TAP-FORM ruling (owner 2026-07-25, docs/slab-pour-design-2026-07-24.md
    'Tap-form ruling') on the COMMITTED template: each tap CONTACTS its shunt pad on
    the INNER edge (the recorded tap_form witness coordinates), runs PERPENDICULAR
    from that edge into the inter-pad gap, then its first turn is 90 OUTWARD. Pure
    JSON -- no pcbnew needed."""

    def setUp(self):
        import json
        with open(TAPS_TPL) as fh:
            self.t = json.load(fh)
        self.form = self.t.get("tap_form")
        self.tracks = [tr for tr in self.t["internal_tracks"]
                       if tr["net_role"] in ("CELL_HI", "CELL_LO")]

    def test_witness_present(self):
        self.assertTrue(self.form, "tap_form witness missing from the template")

    def test_all_orthogonal(self):
        for tr in self.t["internal_tracks"]:
            (sx, sy), (ex, ey) = tr["start_rel_mm"], tr["end_rel_mm"]
            self.assertTrue(abs(sx - ex) < 1e-6 or abs(sy - ey) < 1e-6,
                            "diagonal authored track: %s" % tr)

    def _entry_chain(self, role, edge_key, into_sign):
        """The tap's entry: a track starting AT the recorded inner edge, horizontal
        (perpendicular to the edge), heading INTO the gap; returns (stub, turn_x)."""
        ex, ey = self.form[edge_key]
        stubs = [tr for tr in self.tracks if tr["net_role"] == role
                 and abs(tr["start_rel_mm"][0] - ex) < 1e-6
                 and abs(tr["start_rel_mm"][1] - ey) < 1e-6]
        self.assertEqual(len(stubs), 1,
                         "%s must have exactly ONE inner-edge entry stub" % role)
        stub = stubs[0]
        self.assertAlmostEqual(stub["start_rel_mm"][1], stub["end_rel_mm"][1],
                               msg="entry stub must be perpendicular to the inner edge")
        dx = stub["end_rel_mm"][0] - stub["start_rel_mm"][0]
        self.assertGreater(dx * into_sign, 0,
                           "%s entry must run INTO the gap (toward the middle)" % role)
        return stub

    def test_hi_enters_inner_edge_then_90_outward(self):
        stub = self._entry_chain("CELL_HI", "hi_inner_edge", +1.0)
        self._assert_outward_turn("CELL_HI", stub)

    def test_lo_enters_inner_edge_then_90_outward(self):
        stub = self._entry_chain("CELL_LO", "lo_inner_edge", -1.0)
        self._assert_outward_turn("CELL_LO", stub)

    def _assert_outward_turn(self, role, stub):
        tx, ty = stub["end_rel_mm"]
        nxt = [tr for tr in self.tracks if tr["net_role"] == role
               and abs(tr["start_rel_mm"][0] - tx) < 1e-6
               and abs(tr["start_rel_mm"][1] - ty) < 1e-6]
        self.assertEqual(len(nxt), 1, "%s stub must continue in ONE 90 turn" % role)
        dy = nxt[0]["end_rel_mm"][1] - nxt[0]["start_rel_mm"][1]
        self.assertAlmostEqual(nxt[0]["start_rel_mm"][0], nxt[0]["end_rel_mm"][0],
                               msg="the turn leg must be vertical (a true 90)")
        self.assertGreater(dy * self.form["outward_y_sign"], 0,
                           "%s first turn must head OUTWARD (toward the bank)" % role)

    def test_stubs_clear_each_other_in_the_shared_gap(self):
        hi = self._entry_chain("CELL_HI", "hi_inner_edge", +1.0)
        lo = self._entry_chain("CELL_LO", "lo_inner_edge", -1.0)
        # same row -> clearance is the horizontal separation of the turn columns
        gap = lo["end_rel_mm"][0] - hi["end_rel_mm"][0]
        self.assertGreaterEqual(gap, 2 * (hi["width_mm"] / 2.0) + 0.2 - 1e-6,
                                "the two inner-edge stubs must clear each other")


if __name__ == "__main__":
    unittest.main(verbosity=2)
