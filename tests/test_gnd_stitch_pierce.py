#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Tooth for cec_gnd_fanout.stitch_locked_islands' PIERCE path -- the branch that
# actually creates + locks a via. The original teeth never reached it (no
# pierceable island in the fixture), which is how `v.SetIsLocked(True)` -- a
# method PCB_VIA does not have in KiCad 10 -- shipped and CRASHED every
# production stitch, silently (the route path's fail-safe except swallowed it;
# found by the wave-14b GND forensic, 2026-07-19: 23 GND island edges on the
# published best; 11 pierced after the one-line fix).
#
# Synthetic board (test_kelvin_topology construction pattern; pcbnew-gated,
# runs in the routing container, skips on the host): a filled GND zone on
# F.Cu + a LOCKED GND track island well inside it but electrically separate
# (the stamped-cell GND stub shape). The stitch must add >=1 via, the via
# must be LOCKED (the exact line that was broken), and the report must count
# the island.
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

try:
    import pcbnew                                            # noqa: F401
    HAVE_PCBNEW = True
except ImportError:
    HAVE_PCBNEW = False

# Fixture builds in TWO subprocesses (the two-process fill rule -- in-process
# ZONE_FILLER + continued work is the documented pcbnew segfault footgun, and
# the edges+track+fill COMBINATION segfaults even standalone on KiCad 10):
#   stage 1: board + In1.Cu GND plane zone + fill + save   (production shape:
#            the plane lives on an inner layer)
#   stage 2: load, add Edge.Cuts + the LOCKED F.Cu GND stub (the stamped-cell
#            island shape -- over the plane, touching nothing on F.Cu), save.
_BUILD1 = textwrap.dedent("""
    import sys
    import pcbnew
    MM = lambda v: int(v * 1e6)
    path = sys.argv[1]
    b = pcbnew.CreateEmptyBoard()
    gnd = pcbnew.NETINFO_ITEM(b, "GND")
    b.Add(gnd)
    z = pcbnew.ZONE(b)
    z.SetNet(gnd)
    z.SetLayer(pcbnew.In1_Cu)
    ol = z.Outline()
    ol.NewOutline()
    for (x, y) in ((2, 2), (38, 2), (38, 38), (2, 38)):
        ol.Append(MM(x), MM(y))
    b.Add(z)
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    pcbnew.SaveBoard(path, b)
    sys.stdout.write("STAGE1")
    sys.stdout.flush()
    import os
    os._exit(0)
""")

_BUILD2 = textwrap.dedent("""
    import sys
    import pcbnew
    from pcbnew import VECTOR2I
    MM = lambda v: int(v * 1e6)
    path = sys.argv[1]
    b = pcbnew.LoadBoard(path)
    for (x0, y0, x1, y1) in ((0, 0, 40, 0), (40, 0, 40, 40),
                             (40, 40, 0, 40), (0, 40, 0, 0)):
        seg = pcbnew.PCB_SHAPE(b)
        seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
        seg.SetStart(VECTOR2I(MM(x0), MM(y0)))
        seg.SetEnd(VECTOR2I(MM(x1), MM(y1)))
        seg.SetLayer(pcbnew.Edge_Cuts)
        b.Add(seg)
    gnd = b.GetNetsByName().find("GND").value()[1]
    t = pcbnew.PCB_TRACK(b)
    t.SetStart(VECTOR2I(MM(18), MM(20)))
    t.SetEnd(VECTOR2I(MM(22), MM(20)))
    t.SetWidth(MM(0.3))
    t.SetLayer(pcbnew.F_Cu)
    t.SetNet(gnd)
    t.SetLocked(True)
    b.Add(t)
    pcbnew.SaveBoard(path, b)
    sys.stdout.write("STAGE2")
    sys.stdout.flush()
    import os
    os._exit(0)
""")


@unittest.skipUnless(HAVE_PCBNEW, "pcbnew required (routing container)")
class TestStitchPierce(unittest.TestCase):
    def test_fanout_candidate_angles_are_canonical(self):
        import cec_gnd_fanout
        for direction in ((1, 0), (-1, 0), (0, 1), (0, -1),
                          (1, 1), (-1, 1), (1, -1), (-1, -1)):
            with self.subTest(direction=direction):
                x, y = cec_gnd_fanout._fanout_candidate_nm(
                    10_000_000, 20_000_000,
                    direction[0], direction[1], 0.7, 1.1)
                dx, dy = abs(x - 10_000_000), abs(y - 20_000_000)
                self.assertTrue(dx == 0 or dy == 0 or dx == dy,
                                "GND fanout stubs must be 0/45/90 degrees")

    def test_pierce_creates_locked_via(self):
        import cec_gnd_fanout
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "island.kicad_pcb")
            r = subprocess.run([sys.executable, "-c", _BUILD1, p],
                               capture_output=True, text=True, timeout=120)
            self.assertIn("STAGE1", r.stdout, "stage1 failed rc=%s: %s" % (r.returncode, r.stderr[-400:]))
            r = subprocess.run([sys.executable, "-c", _BUILD2, p],
                               capture_output=True, text=True, timeout=120)
            self.assertIn("STAGE2", r.stdout, "stage2 failed rc=%s: %s" % (r.returncode, r.stderr[-400:]))
            rep = cec_gnd_fanout.stitch_locked_islands(p)
            self.assertGreaterEqual(rep.get("stitched", 0), 1,
                                    "pierceable island must gain a via: %r" % rep)
            out = subprocess.run(
                [sys.executable, "-c", textwrap.dedent("""
                    import sys, pcbnew
                    b = pcbnew.LoadBoard(sys.argv[1])
                    vias = [t for t in b.GetTracks() if t.GetClass() == "PCB_VIA"]
                    ok = bool(vias) and all(v.IsLocked() for v in vias)
                    sys.stdout.write("VIAS=%d LOCKED=%s" % (len(vias), ok))
                    sys.stdout.flush()
                    import os
                    os._exit(0)
                """), p], capture_output=True, text=True, timeout=120)
            self.assertIn("LOCKED=True", out.stdout,
                          "stitch vias must exist and be LOCKED: %s" % out.stdout)


if __name__ == "__main__":
    unittest.main()
