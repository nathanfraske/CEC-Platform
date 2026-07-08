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


class TestDualSideGuard(unittest.TestCase):
    """OWNER RULE teeth: connectors and the MCU can never reach the back set, even if an
    upstream side-assigner proposes them."""

    def test_guard_strips_connectors_and_mcu(self):
        import cec_synth_pipeline as sp
        back = {"RS3", "U12", "C15", "J3", "TB4", "U1", "U5"}
        anchors_roles = {"J3": "power_in", "TB4": "power_out"}
        comps = {"U1": "cec-RF_Module:ESP32-C6-MINI-1", "U12": "cec-Package_SO:VSSOP-10",
                 "RS3": "cec-Resistor_SMD:R_2512_6332Metric", "C15": "cec-Capacitor_SMD:C_0603",
                 "U5": "cec-Package_DFN_QFN:RUX0012A", "J3": "x:y", "TB4": "x:y"}
        keep, stripped = sp._dual_side_guard(back, anchors_roles, comps)
        self.assertEqual(stripped, {"J3", "TB4", "U1"})
        self.assertEqual(keep, {"RS3", "U12", "C15", "U5"})

    def test_real_board_back_set_clean(self):
        import cec_synth_pipeline as sp
        # the guard on the REAL 24-pin back set must strip nothing (construction is clean)
        # -- if this ever strips, the chain-builder regressed.
        import dataclasses
        try:
            cfg = sp.Config.load("atx-24pin-rev3")
        except FileNotFoundError:
            self.skipTest("board dir absent")
        if not HAVE_PCBNEW:
            self.skipTest("pcbnew required")
        cfg.params.update({"dual_sided": True, "mount_holes": "none",
                           "connector_overhang": "edge", "respect_antenna_keepout": False})
        cand = sp.synth_one(dataclasses.asdict(cfg), 100.0, 80.0, "dataflow", 0)
        self.assertTrue(cand.back_refs, "dual-sided board produced no back set")
        for r in cand.back_refs:
            self.assertFalse(r.startswith(("J", "TB")), r)
        self.assertNotIn("U1", cand.back_refs)


@unittest.skipUnless(HAVE_PCBNEW, "pcbnew required")
class TestSenseSideChecker(unittest.TestCase):
    """The dual-sided gate term: analog never crosses faces -- independently verified,
    N/A on single-sided boards (12VHPWR's lane vias must never false-fail)."""

    def test_na_on_single_sided(self):
        import cec_synth_pipeline as sp
        for p in ("tests/golden/fixtures/route-oracle/eps-rev3-n2.kicad_pcb",
                  "modules/12vhpwr-standard/12vhpwr-standard-module.kicad_pcb"):
            full = os.path.join(HERE, "..", p)
            if not os.path.isfile(full):
                continue
            r = sp._oracle_sense_side(full)
            self.assertFalse(r["applicable"], p)
            self.assertTrue(r["ok"], p)

    def test_fires_on_injected_sense_via(self):
        import shutil
        import tempfile
        import cec_synth_pipeline as sp
        src = os.path.join(HERE, "..", "build", "24pin-probe", "seed5c.kicad_pcb")
        if not os.path.isfile(src):
            self.skipTest("dual-sided probe board absent (build artifact)")
        tmp = tempfile.mkstemp(suffix=".kicad_pcb")[1]
        shutil.copy(src, tmp)
        b = pcbnew.LoadBoard(tmp)
        nets = [n for n in ("/SENSE3V3_HI", "/SENSE3V3_LO") if b.GetNetcodeFromNetname(n) > 0]
        self.assertTrue(nets)
        v = pcbnew.PCB_VIA(b)
        v.SetPosition(pcbnew.VECTOR2I(int(86.7e6), int(45e6)))
        v.SetNetCode(b.GetNetcodeFromNetname(nets[0]))
        b.Add(v)
        pcbnew.SaveBoard(tmp, b)
        r = sp._oracle_sense_side(tmp)
        self.assertTrue(r["applicable"])
        self.assertFalse(r["ok"], r)
