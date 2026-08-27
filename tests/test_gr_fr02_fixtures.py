#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  Verify fixtures for the assisted-routing build (closed-loop list Parts
#  10/11), per the sheet's own VERIFY clauses:
#    GR-02 "the seeded movable-blocker fixture repairs mechanically; the
#           repair claim settles at Grade 2 in the same run"
#    GR-01 "a seeded two-net congestion fixture: detection flags the channel"
#    FR-02 compiler mechanics (resolution, legality nudge, stub materialize,
#          hygiene) on the synthetic board; the full route-through verify runs
#          on eps-8pin in-container (scripts/cec_fr02_verify run).
#  CONTAINER-ONLY (pcbnew); skips cleanly on the host.
# ============================================================================
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

try:
    import pcbnew
    HAVE_PCBNEW = True
except ImportError:
    HAVE_PCBNEW = False


def _mk_board(path):
    """Synthetic 2-net fixture: net A's pads at (5,10)/(25,10); net B = a
    short STACKED blocker (F.Cu + B.Cu segments) crossing A's corridor at
    x=15, y in [8,12] -- the seeded movable blocker. 30x20 outline."""
    board = pcbnew.CreateEmptyBoard()
    # outline
    for (x1, y1), (x2, y2) in (((0, 0), (30, 0)), ((30, 0), (30, 20)),
                               ((30, 20), (0, 20)), ((0, 20), (0, 0))):
        seg = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_SEGMENT)
        seg.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x1), pcbnew.FromMM(y1)))
        seg.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x2), pcbnew.FromMM(y2)))
        seg.SetLayer(board.GetLayerID("Edge.Cuts"))
        seg.SetWidth(pcbnew.FromMM(0.1))
        board.Add(seg)
    netA = pcbnew.NETINFO_ITEM(board, "NETA")
    netB = pcbnew.NETINFO_ITEM(board, "NETB")
    board.Add(netA)
    board.Add(netB)

    def _pad_fp(ref, x, y, net, tht=False):
        fp = pcbnew.FOOTPRINT(board)
        fp.SetReference(ref)
        fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
        pad = pcbnew.PAD(fp)
        pad.SetSize(pcbnew.VECTOR2I(pcbnew.FromMM(1), pcbnew.FromMM(1)))
        if tht:                                   # THT: reaches BOTH layers, so
            pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)  # the stacked F+B blocker is
            pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)  # legitimately connected
            pad.SetLayerSet(pcbnew.PAD.PTHMask())
            pad.SetDrillSize(pcbnew.VECTOR2I(pcbnew.FromMM(0.5), pcbnew.FromMM(0.5)))
        else:
            pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            pad.SetLayerSet(pcbnew.PAD.SMDMask())
        pad.SetPosition(fp.GetPosition())
        pad.SetNet(net)
        pad.SetNumber("1")
        fp.Add(pad)
        board.Add(fp)
        return fp

    _pad_fp("A1", 5, 10, netA)
    _pad_fp("A2", 25, 10, netA)
    _pad_fp("B1", 15, 8, netB, tht=True)
    _pad_fp("B2", 15, 12, netB, tht=True)
    for layer in ("F.Cu", "B.Cu"):                      # the stacked blocker
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(15), pcbnew.FromMM(8)))
        t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(15), pcbnew.FromMM(12)))
        t.SetWidth(pcbnew.FromMM(0.25))
        t.SetLayer(board.GetLayerID(layer))
        t.SetNet(netB)
        board.Add(t)
    pcbnew.SaveBoard(path, board)
    return path


@unittest.skipUnless(HAVE_PCBNEW, "pcbnew required (run in the routing container)")
class T1GR02Battery(unittest.TestCase):
    def test_movable_blocker_repairs_mechanically(self):
        import cec_router
        work = tempfile.mkdtemp()
        src = _mk_board(os.path.join(work, "fixture.kicad_pcb"))
        out = os.path.join(work, "repaired.kicad_pcb")
        res = cec_router.gr02_repair_battery(src, out, blocked_net="NETA")
        self.assertTrue(res["repaired"], res)
        self.assertTrue(any(m["move"] == "shift" for m in res["moves_tried"]),
                        "the movable blocker should fall to the SHIFT rung")
        self.assertEqual(res["drc"], 0, "full DRC is the judge")
        # the claim settles Grade 2 in the same run (the sheet's verify clause)
        self.assertEqual(res["claim"]["settlement"]["grade"], 2)
        self.assertEqual(res["claim"]["settlement"]["state"], "settled")
        self.assertTrue(res["claim"]["settled_value"])

    def test_immovable_blocker_is_respected(self):
        """Mobility model: a net listed immovable (template/locked tier) is
        never shifted -- the battery must fail without touching it."""
        import cec_router
        work = tempfile.mkdtemp()
        src = _mk_board(os.path.join(work, "fixture.kicad_pcb"))
        out = os.path.join(work, "repaired.kicad_pcb")
        res = cec_router.gr02_repair_battery(src, out, blocked_net="NETA",
                                             immovable=("NETB",))
        self.assertFalse(any(m["move"] == "shift" and m["net"] == "NETB"
                             for m in res["moves_tried"]))
        # failed claims still SETTLE (DF-06: tested-and-failed is settled,
        # with the outcome in settled_value -- panel-adjudicated)
        if not res["repaired"]:
            self.assertEqual(res["claim"]["settlement"]["state"], "settled")
            self.assertFalse(res["claim"]["settled_value"])
            # CONTRACT: repaired=False => out_path is the PRISTINE input
            self.assertEqual(open(src, "rb").read(), open(out, "rb").read(),
                             "total failure must restore the pristine board")


@unittest.skipUnless(HAVE_PCBNEW, "pcbnew required (run in the routing container)")
class T2GR01Grid(unittest.TestCase):
    def test_seeded_congestion_flags_the_channel(self):
        import cec_router
        work = tempfile.mkdtemp()
        src = _mk_board(os.path.join(work, "fixture.kicad_pcb"))
        # blocker tracks count NETB as routed; strip them so BOTH nets are
        # unrouted demand through the same channel
        b = pcbnew.LoadBoard(src)
        for t in list(b.GetTracks()):
            b.Remove(t)
        pcbnew.SaveBoard(src, b)
        res = cec_router.gr01_congestion_grid(src, cell_mm=2.0,
                                              hotspot_factor=1.2)
        self.assertTrue(res["hotspots"], "the shared channel must flag")
        self.assertIn("NETA", res["contested"])
        self.assertIn("NETB", res["contested"])
        # contested nets route FIRST -- the assignment order exists
        self.assertEqual(set(res["order"]), {"NETA", "NETB"})


@unittest.skipUnless(HAVE_PCBNEW, "pcbnew required (run in the routing container)")
class T3FR02CompilerMechanics(unittest.TestCase):
    def test_resolve_and_materialize(self):
        import cec_fr02
        work = tempfile.mkdtemp()
        src = _mk_board(os.path.join(work, "fixture.kicad_pcb"))
        out = os.path.join(work, "directed.kicad_pcb")
        intents = [{"net": "NETA",
                    "waypoints": [{"between": ["A1", "A2"]},
                                  {"ref": "A1", "offset_mm": [3, -3]},
                                  {"at_mm": [20, 6]}]}]
        res = cec_fr02.compile_intents(src, intents, out)
        self.assertEqual(len(res["stubs"]), 3, res["failures"])
        self.assertEqual(res["failures"], [])
        self.assertEqual(len(res["claims"]), 1)
        b = pcbnew.LoadBoard(out)
        locked = [t for t in b.GetTracks()
                  if t.GetClass() == "PCB_TRACK" and t.IsLocked()]
        self.assertEqual(len(locked), 3, "3 LOCKED stubs materialized")
        self.assertTrue(all(t.GetNetname() == "NETA" for t in locked))

    def test_blocked_waypoint_nudges_within_tolerance(self):
        """A waypoint inside the thin blocker NUDGES clear within the declared
        tolerance (the designed behavior) -- the stub lands off the obstacle."""
        import cec_fr02
        work = tempfile.mkdtemp()
        src = _mk_board(os.path.join(work, "fixture.kicad_pcb"))
        out = os.path.join(work, "directed.kicad_pcb")
        intents = [{"net": "NETA", "waypoints": [{"at_mm": [15, 10]}]}]
        res = cec_fr02.compile_intents(src, intents, out)
        self.assertEqual(len(res["stubs"]), 1, res["failures"])
        (x1, _), (x2, _) = res["stubs"][0]["ends"]
        self.assertNotAlmostEqual((x1 + x2) / 2 / 1e6, 15.0, places=1,
                                  msg="the stub must sit OFF the blocker")

    def test_preflight_waypoint_and_compiler_share_exact_geometry(self):
        """A coordinator can preflight a compact protected stub, then hand the
        returned centre to the compiler without a second-stage rejection."""
        import cec_fr02
        work = tempfile.mkdtemp()
        src = _mk_board(os.path.join(work, "fixture.kicad_pcb"))
        b = pcbnew.LoadBoard(src)
        at = cec_fr02.find_clear_waypoint_mm(
            b, "NETA", "F.Cu", [15, 10], stub_len_mm=0.6,
            width_mm=0.22, nudge_mm=1.0)
        self.assertIsNotNone(at)
        out = os.path.join(work, "directed.kicad_pcb")
        res = cec_fr02.compile_intents(src, [{
            "net": "NETA", "layers": ["F.Cu"],
            "waypoints": [{"at_mm": at}], "stub_len_mm": 0.6,
            "width_mm": 0.22, "nudge_mm": 0.0}], out)
        self.assertEqual(len(res["stubs"]), 1, res["failures"])

    def test_blocked_beyond_tolerance_fails_named(self):
        """The FR-03 discipline: blocked beyond tolerance = FAIL with the
        spot named, never a creative detour (tolerance shrunk to force it)."""
        import cec_fr02
        work = tempfile.mkdtemp()
        src = _mk_board(os.path.join(work, "fixture.kicad_pcb"))
        out = os.path.join(work, "directed.kicad_pcb")
        old = cec_fr02.NUDGE_MM
        cec_fr02.NUDGE_MM = 0.2
        try:
            res = cec_fr02.compile_intents(
                src, [{"net": "NETA", "waypoints": [{"at_mm": [15, 10]}]}], out)
        finally:
            cec_fr02.NUDGE_MM = old
        self.assertEqual(len(res["stubs"]), 0)
        self.assertEqual(len(res["failures"]), 1)
        self.assertIn("no clear spot", res["failures"][0]["why"])

    def test_ring_offsets_cover_full_perimeter(self):
        """Panel-caught: the old spiral visited only corners+axes for
        ring>=2. The full Chebyshev perimeter is 8*ring cells."""
        import cec_fr02
        self.assertEqual(cec_fr02._ring_offsets(0), [(0, 0)])
        for ring in (1, 2, 5, 8):
            offs = cec_fr02._ring_offsets(ring)
            self.assertEqual(len(offs), 8 * ring)
            self.assertTrue(all(max(abs(dx), abs(dy)) == ring for dx, dy in offs))

    def test_relational_only_mode_rejects_at_mm(self):
        """The sheet's vocabulary: relational, never coordinates -- at_mm is
        the HUMAN escape hatch; a model-tier caller turns it off."""
        import cec_fr02
        work = tempfile.mkdtemp()
        src = _mk_board(os.path.join(work, "fixture.kicad_pcb"))
        res = cec_fr02.compile_intents(
            src, [{"net": "NETA", "waypoints": [{"at_mm": [10, 4]}]}],
            os.path.join(work, "x.kicad_pcb"), allow_at_mm=False)
        self.assertEqual(len(res["stubs"]), 0)
        self.assertIn("relational-only", res["failures"][0]["why"])

    def test_bad_ref_fails_named(self):
        import cec_fr02
        work = tempfile.mkdtemp()
        src = _mk_board(os.path.join(work, "fixture.kicad_pcb"))
        res = cec_fr02.compile_intents(
            src, [{"net": "NETA", "waypoints": [{"ref": "NOPE"}]}],
            os.path.join(work, "x.kicad_pcb"))
        self.assertEqual(len(res["failures"]), 1)
        self.assertIn("NOPE", res["failures"][0]["why"])

    def test_orphan_hygiene(self):
        """A stub on a net that failed to route is removed; on a routed net
        it is absorbed (unlocked)."""
        import cec_fr02
        work = tempfile.mkdtemp()
        src = _mk_board(os.path.join(work, "fixture.kicad_pcb"))
        out = os.path.join(work, "directed.kicad_pcb")
        res = cec_fr02.compile_intents(
            src, [{"net": "NETA", "waypoints": [{"at_mm": [10, 4]}]}], out)
        self.assertEqual(len(res["stubs"]), 1)
        # NETA is unrouted on this board -> the stub is an ORPHAN
        hyg = cec_fr02.clean_orphan_stubs(out, res)
        self.assertEqual(hyg["removed_orphans"], 1)
        b = pcbnew.LoadBoard(out)
        self.assertFalse([t for t in b.GetTracks()
                          if t.GetClass() == "PCB_TRACK" and t.IsLocked()])


if __name__ == "__main__":
    unittest.main()
