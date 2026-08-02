#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Hub inner-layer rung teeth. The 2026-08-01 six-layer decision supersedes the
# earlier four-layer In2 pour rule: In2 remains a signal-routing layer, In3 is
# the power-pour layer, and In1/In4 are ground planes. Three fixes under test:
#   1. hub BOARD_PARAMS conformance: inner routing enabled and every power pour
#      ask on In3 (evac=False stays, so the pour remains post-route additive).
#   2. pour_polygons() per-layer emission: the old s.layers[0] truncation
#      silently dropped every layer past the first (measured: the hub's F+B
#      asks poured F.Cu ONLY on all 12 night waves).
#   3. synthesize_power_pickups exempt set {nc}: with set() every net --
#      including the stub's OWN -- counted as foreign, the stub collided with
#      its own pad at its own start point, and the stitch fired 0x across ~40
#      boards (the systematic false-refusal).
# Tests 1-2 are host-runnable; test 3 needs pcbnew (container-only skip).
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


class TestHubParamsConformance(unittest.TestCase):
    def setUp(self):
        import cec_fresh_wave as w
        self.p = w.BOARD_PARAMS["hub-standard-rev2"]

    def test_inner_power_routing_on(self):
        self.assertTrue(self.p.get("inner_power_routing"),
                        "hub must free In2 (2026-06-14 stackup ruling: one "
                        "inner GND plane, In2 = signal)")

    def test_pour_asks_live_on_in3(self):
        asks = self.p.get("pour_asks") or []
        self.assertEqual({a["net"] for a in asks}, {
            "+5VSB", "/5VSB_RAW", "/PSU_5V", "/PSU_5V_KVM",
            "/MAIN_5V_RAW", "/USB_VBUS", "/+5V_HOLD",
            "/VCC_P1", "/VCC_P2", "/VCC_P3", "/VCC_P4",
        })
        for a in asks:
            self.assertEqual(tuple(a["layers"]), ("In3.Cu",),
                             f"pour ask {a['net']} must live on the approved "
                             "six-layer In3 power layer")
            self.assertFalse(a.get("evac", True),
                             "hub asks stay post-route additive (no eviction)")


class TestPourPolygonsPerLayer(unittest.TestCase):
    def _plan(self, layers):
        import cec_pourplan as cp
        spec = cp._spec_from_dict({
            "net": "+5VSB", "layers": list(layers), "shape": "rect",
            "polygon": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0)],
            "provenance": "placer_ask"})
        return cp.PourPlan([spec])

    def test_multi_layer_spec_emits_one_dict_per_layer(self):
        out = self._plan(("F.Cu", "B.Cu")).pour_polygons()
        self.assertEqual([d["layer"] for d in out], ["F.Cu", "B.Cu"],
                         "the layers[0] truncation dropped the B half")
        self.assertEqual(out[0]["polygon"], out[1]["polygon"])
        self.assertEqual({d["net"] for d in out}, {"+5VSB"})

    def test_single_layer_spec_unchanged(self):
        out = self._plan(("In2.Cu",)).pour_polygons()
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["layer"], "In2.Cu")


class TestPickupOwnNetExempt(unittest.TestCase):
    """Container-only: a minimal one-pad board proves the stitch fires when the
    pad's own net is exempt and refuses under the old empty exempt set."""

    def setUp(self):
        try:
            import pcbnew                              # noqa: F401
        except ImportError:
            self.skipTest("pcbnew not available (container-only test)")

    def _one_pad_board(self):
        import pcbnew
        b = pcbnew.BOARD()
        b.SetCopperLayerCount(4)       # wave boards are 4-layer; a fresh BOARD
        ni = pcbnew.NETINFO_ITEM(b, "+5VSB")   # defaults to 2 (In2 disabled)
        b.Add(ni)
        fp = pcbnew.FOOTPRINT(b)
        fp.SetPosition(pcbnew.VECTOR2I(int(5e6), int(2.5e6)))
        pad = pcbnew.PAD(fp)
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(pcbnew.VECTOR2I(int(1e6), int(1e6)))
        pad.SetPosition(fp.GetPosition())
        ls = pcbnew.LSET()
        ls.AddLayer(pcbnew.F_Cu)
        pad.SetLayerSet(ls)
        pad.SetNet(ni)
        fp.Add(pad)
        b.Add(fp)
        return b

    def test_stitch_fires_with_own_net_exempt(self):
        import cec_fr
        b = self._one_pad_board()
        pours = [{"net": "+5VSB", "layer": "In2.Cu",
                  "polygon": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0)]}]
        r = cec_fr.synthesize_power_pickups(b, pours)
        self.assertEqual(r["vias"], 1,
                         "an isolated covered pad with clear space must be "
                         "stitched -- 0 here = the own-pad false-refusal")
        self.assertEqual(r["skipped"], 0)

    def test_declared_pofv_profile_prefers_contained_via_in_pad(self):
        import pcbnew
        import cec_fr

        b = self._one_pad_board()
        b.SetCopperLayerCount(6)
        props = b.GetProperties()
        props["CEC_FAB_PROFILE"] = "jlcpcb_6l_pofv_signal"
        b.SetProperties(props)
        pad = next(iter(next(iter(b.GetFootprints())).Pads()))
        pours = [{"net": "+5VSB", "layers": ("In3.Cu",)}]
        r = cec_fr.synthesize_power_pickups(b, pours)
        vias = [t for t in b.GetTracks() if t.GetClass() == "PCB_VIA"]
        self.assertEqual((r["vias"], r["pofv"], r["stubs"]), (1, 1, 0))
        self.assertEqual(vias[0].GetPosition(), pad.GetPosition())

    def test_via_spot_probe_spans_all_layers(self):
        # B2 short reproduction: a foreign track on In2 under the via spot.
        # The single-layer F.Cu probe passes (the hole that shorted); the
        # all-layer _via_spot_clear refuses.
        import pcbnew
        import cec_fr
        b = self._one_pad_board()
        led = pcbnew.NETINFO_ITEM(b, "/LED_DATA_DIN")
        b.Add(led)
        at = pcbnew.VECTOR2I(int(5.8e6), int(2.5e6))
        tr = pcbnew.PCB_TRACK(b)
        tr.SetStart(pcbnew.VECTOR2I(at.x, at.y - int(2e6)))
        tr.SetEnd(pcbnew.VECTOR2I(at.x, at.y + int(2e6)))
        tr.SetWidth(int(0.2e6))
        tr.SetLayer(b.GetLayerID("In2.Cu"))
        tr.SetNet(led)
        b.Add(tr)
        pad_nc = list(b.GetFootprints())[0].Pads()[0].GetNetCode()
        probe = pcbnew.VECTOR2I(at.x + 10000, at.y)
        f_only = cec_fr._tap_foreign_clear(b, at, probe, int(0.6e6),
                                           b.GetLayerID("F.Cu"),
                                           int(0.25e6), {pad_nc})
        all_l = cec_fr._via_spot_clear(b, at, int(0.6e6), int(0.25e6),
                                       {pad_nc})
        self.assertTrue(f_only, "the F.Cu-only probe misses the In2 track "
                                "(the measured B2 short)")
        self.assertFalse(all_l, "the all-layer probe must refuse it")

    def test_edge_keepout_layer_derivation_contract(self):
        # The strips must cover exactly FR's routable space: the frozen golden
        # EPS (In1 signal-typed but a PLANE; In2 power-kind) derives F/B only
        # -- so the golden route is untouched -- while a freed-In2 wave board
        # includes In2. Uses real boards; skips if either is absent.
        import cec_fr
        gold = os.path.join(ROOT, "tests", "golden", "eps-8pin",
                            "eps8pin-module.kicad_pcb")
        if not os.path.isfile(gold):
            self.skipTest("golden eps board absent")
        ks = cec_fr.edge_keepout(gold)
        lays = sorted({l for k in ks for l in k["layers"]})
        self.assertEqual(lays, ["B.Cu", "F.Cu"],
                         "plane/power inners must stay OUT of the strips")
        # freed-In2 inclusion leg on a SYNTHETIC pre-route board (2026-07-24:
        # the old newest-archive fixture broke honestly once the logic-rail
        # In2 floods landed -- a routed archive's majority-flooded In2 reads
        # as a plane, but the pipeline derives strips from the PLACED board
        # where post-route floods do not exist yet).
        import pcbnew
        b = pcbnew.BOARD()
        b.SetCopperLayerCount(4)
        for lid, kind in ((pcbnew.In1_Cu, pcbnew.LT_POWER),
                          (pcbnew.In2_Cu, pcbnew.LT_SIGNAL)):
            b.SetLayerType(lid, kind)
        for (ax, ay, bx, by) in ((0, 0, 40e6, 0), (40e6, 0, 40e6, 30e6),
                                 (40e6, 30e6, 0, 30e6), (0, 30e6, 0, 0)):
            sshape = pcbnew.PCB_SHAPE(b)
            sshape.SetShape(pcbnew.SHAPE_T_SEGMENT)
            sshape.SetStart(pcbnew.VECTOR2I(int(ax), int(ay)))
            sshape.SetEnd(pcbnew.VECTOR2I(int(bx), int(by)))
            sshape.SetLayer(pcbnew.Edge_Cuts)
            b.Add(sshape)
        ks2 = cec_fr.edge_keepout("", board=b)
        lays2 = sorted({l for k in ks2 for l in k["layers"]})
        self.assertIn("In2.Cu", lays2,
                      "a freed signal In2 must join the strips")
        self.assertNotIn("In1.Cu", lays2,
                         "a power-kind inner must stay out")

    def test_old_empty_exempt_set_refuses_own_pad(self):
        # The root-cause reproduction: the guard itself, called the OLD way
        # (empty exempt set), collides the stub with its own pad.
        import pcbnew
        import cec_fr
        b = self._one_pad_board()
        pad = list(b.GetFootprints())[0].Pads()[0]
        pos = pad.GetPosition()
        at = pcbnew.VECTOR2I(pos.x + int(0.8e6), pos.y)
        lay = b.GetLayerID("F.Cu")
        nc = pad.GetNetCode()
        old = cec_fr._tap_foreign_clear(b, pos, at, int(0.3e6), lay,
                                        int(0.25e6), set())
        new = cec_fr._tap_foreign_clear(b, pos, at, int(0.3e6), lay,
                                        int(0.25e6), {nc})
        self.assertFalse(old, "empty exempt set must self-collide (the bug)")
        self.assertTrue(new, "own-net exempt must clear an empty board")


if __name__ == "__main__":
    unittest.main()
