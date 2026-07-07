# SPDX-License-Identifier: Apache-2.0
"""place(flip=True) must equal pcbnew's native Flip() -- the dual-sided placement
primitive (2026-07-08). The logo-era flip mirrored graphics only; real parts need pad
positions/angles mirrored about the footprint origin. This calibration is the TEETH:
if the textual transform ever drifts from KiCad's own flip semantics, this fails."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

try:
    import pcbnew
    HAVE_PCBNEW = True
except Exception:
    HAVE_PCBNEW = False

_LAYERS = ('(layers (0 "F.Cu" signal) (2 "B.Cu" signal) (9 "F.Fab" user) (11 "B.Fab" user) '
           '(5 "F.SilkS" user) (7 "B.SilkS" user) (1 "F.Paste" user) (3 "B.Paste" user) '
           '(4 "F.Mask" user) (6 "B.Mask" user) (44 "Edge.Cuts" user) (46 "F.CrtYd" user) '
           '(47 "B.CrtYd" user))')


@unittest.skipUnless(HAVE_PCBNEW, "pcbnew required")
class TestPlaceFlip(unittest.TestCase):
    def _pads(self, board_or_fp):
        fps = board_or_fp.GetFootprints() if hasattr(board_or_fp, "GetFootprints") else [board_or_fp]
        return {p.GetPadName(): (round(p.GetPosition().x / 1e6, 3),
                                 round(p.GetPosition().y / 1e6, 3))
                for fp in fps for p in fp.Pads()}

    def _board_doc(self, fp_str):
        return ('(kicad_pcb (version 20241229) (generator "t") (generator_version "9.0")'
                '(general (thickness 1.6)) ' + _LAYERS + ' (net 0 "")' + fp_str + ")")

    def _check(self, libid, rot):
        import tempfile
        import cec_pcb
        flipped = cec_pcb.place(libid, "U1", 50.0, 50.0, rot, {}, {"GND": 1}, flip=True)
        straight = cec_pcb.place(libid, "U1", 50.0, 50.0, rot, {}, {"GND": 1}, flip=False)
        f1 = tempfile.mkstemp(suffix=".kicad_pcb")[1]
        f2 = tempfile.mkstemp(suffix=".kicad_pcb")[1]
        open(f1, "w").write(self._board_doc(flipped))
        open(f2, "w").write(self._board_doc(straight))
        b1 = pcbnew.LoadBoard(f1)
        ours = self._pads(b1)
        fp2 = list(pcbnew.LoadBoard(f2).GetFootprints())[0]
        fp2.Flip(fp2.GetPosition(), False)
        native = self._pads(fp2)
        self.assertEqual(ours, native, f"{libid} rot={rot}")
        self.assertEqual(list(b1.GetFootprints())[0].GetLayerName(), "B.Cu")

    def test_vssop10_rot0(self):
        self._check("cec-Package_SO:VSSOP-10_3x3mm_P0.5mm", 0)

    def test_sot23_rot0(self):
        self._check("cec-Package_TO_SOT_SMD:SOT-23-6", 0)

    def test_r2512_rot270(self):
        # the shunt case: rotated + flipped (a back-side rail chain's shunt)
        self._check("cec-Resistor_SMD:R_2512_6332Metric", 270)


if __name__ == "__main__":
    unittest.main()
