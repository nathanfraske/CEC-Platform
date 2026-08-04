#!/usr/bin/env python3
"""KiCad and Specctra integration checks for the six-layer profiles."""

import os
import json
import re
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

try:
    import pcbnew  # noqa: E402
except ImportError as exc:  # pragma: no cover
    raise unittest.SkipTest("KiCad pcbnew required") from exc

import cec_fab_profile as FAB  # noqa: E402
import cec_pcb  # noqa: E402
import cec_fr  # noqa: E402
import cec_router  # noqa: E402
import cec_constraints  # noqa: E402
import cec_score  # noqa: E402


class SixLayerGenerationTest(unittest.TestCase):
    def _board(self, directory, profile):
        netlist = os.path.join(directory, "fixture.net")
        board = os.path.join(directory, "fixture.kicad_pcb")
        with open(netlist, "w", encoding="utf-8") as handle:
            handle.write('(export (nets (net (code "1") (name "GND"))))\n')
        ok = cec_pcb.build_board(
            board, netlist, {}, [(5.0, 5.0)], None, 20.0, 20.0,
            force_argv=False, stackup_profile=profile)
        self.assertTrue(ok)
        return board

    def test_kicad_parses_profile_layers_properties_and_planes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._board(
                directory, "jlcpcb_6l_pofv_high_current")
            board = pcbnew.LoadBoard(path)
            enabled = FAB.enabled_copper_layers(board)
            self.assertEqual(enabled, FAB.COPPER_LAYERS)
            self.assertEqual(FAB.board_profile_name(board),
                             "jlcpcb_6l_pofv_high_current")
            self.assertEqual(FAB.routing_layers(board),
                             ("F.Cu", "In2.Cu", "In3.Cu", "B.Cu"))
            with open(path, encoding="utf-8") as source:
                text = source.read()
            self.assertIn("(capping yes)", text)
            self.assertIn("(filling yes)", text)
            plane_layers = set()
            for zone in board.Zones():
                if zone.GetNetname() == "GND":
                    plane_layers.update(FAB.COPPER_LAYER_IDS[int(lid)]
                                        for lid in zone.GetLayerSet().CuStack()
                                        if int(lid) in FAB.COPPER_LAYER_IDS)
            self.assertEqual(plane_layers, {"In1.Cu", "In4.Cu"})

    def test_exported_router_deck_exposes_four_route_layers(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._board(
                directory, "jlcpcb_6l_pofv_high_current")
            board = pcbnew.LoadBoard(path)
            aliases = {
                name: board.GetLayerName(board.GetLayerID(name))
                for name in FAB.COPPER_LAYERS
            }
            dsn = os.path.join(directory, "fixture.dsn")
            cec_fr.export_dsn(path, dsn, plane_to_power=True)
            with open(dsn, encoding="utf-8", errors="replace") as source:
                text = source.read()
            for name in FAB.COPPER_LAYERS:
                self.assertRegex(text, r"\(layer\s+\"?%s\"?\b" %
                                 re.escape(aliases[name]))
            for name in ("In1.Cu", "In4.Cu"):
                self.assertRegex(
                    text,
                    r"\(layer\s+\"?%s\"?\s+\(type\s+power\)" %
                    re.escape(aliases[name]))
            for name in ("F.Cu", "In2.Cu", "In3.Cu", "B.Cu"):
                self.assertRegex(
                    text,
                    r"\(layer\s+\"?%s\"?\s+\(type\s+signal\)" %
                    re.escape(aliases[name]))

    def test_exact_stackup_checker_accepts_generated_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._board(directory, "jlcpcb_6l_pofv_high_current")
            board = pcbnew.LoadBoard(path)
            ok, detail = cec_constraints._chk_high_current_stackup(
                board, path, {})
            self.assertTrue(ok, detail)
            ok, detail = cec_constraints._chk_through_vias_only(
                board, path, {})
            self.assertTrue(ok, detail)

    def test_generated_m2_lug_is_plated_and_grounded_on_all_layers(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._board(directory, "jlcpcb_6l_pofv_signal")
            board = pcbnew.LoadBoard(path)
            lug = next(fp for fp in board.GetFootprints()
                       if fp.GetReference() == "H1")
            self.assertIn("M2_Pad_Via", lug.GetFPIDAsString())
            pads = list(lug.Pads())
            self.assertTrue(pads)
            self.assertTrue(all(p.GetNetname() == "GND" for p in pads))
            self.assertTrue(all(p.GetDrillSize().x > 0 for p in pads))
            for layer in FAB.COPPER_LAYERS:
                self.assertTrue(all(p.IsOnLayer(board.GetLayerID(layer))
                                    for p in pads), layer)

    def test_any_unconnected_ratline_fails_route_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._board(directory, "jlcpcb_6l_pofv_signal")
            report = os.path.join(directory, "controlled-drc.json")
            with open(report, "w", encoding="utf-8") as handle:
                json.dump({"violations": [], "unconnected_items": [
                    {"description": "controlled open net /SIG"}
                ]}, handle)
            metrics = cec_score.score(path, drc_json=report)
            passed, reasons = cec_score.gate(metrics)
            self.assertFalse(passed)
            self.assertFalse(metrics.gates_pass)
            self.assertEqual(metrics.unconnected, 1)
            self.assertTrue(any("unconnected ratlines = 1" in r for r in reasons),
                            reasons)

    def test_qualified_pofv_is_allowed_and_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._board(directory, "jlcpcb_6l_pofv_high_current")
            board = pcbnew.LoadBoard(path)
            net = board.FindNet("GND")
            fp = pcbnew.FOOTPRINT(board)
            fp.SetReference("RTEST")
            fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(10),
                                           pcbnew.FromMM(10)))
            pad = pcbnew.PAD(fp)
            pad.SetPadName("1")
            pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetSize(pcbnew.VECTOR2I(pcbnew.FromMM(2.0),
                                        pcbnew.FromMM(2.0)))
            pad.SetPosition(fp.GetPosition())
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            pad.SetLayerSet(pcbnew.PAD.SMDMask())
            pad.SetNet(net)
            fp.Add(pad)
            board.Add(fp)
            via = pcbnew.PCB_VIA(board)
            via.SetViaType(pcbnew.VIATYPE_THROUGH)
            via.SetPosition(fp.GetPosition())
            via.SetWidth(pcbnew.FromMM(0.6))
            via.SetDrill(pcbnew.FromMM(0.3))
            via.SetLayerPair(board.GetLayerID("F.Cu"),
                             board.GetLayerID("B.Cu"))
            via.SetNet(net)
            board.Add(via)
            pcbnew.SaveBoard(path, board)

            self.assertIsNone(cec_fr._via_pad_excluded(
                board, via.GetPosition(), pcbnew.FromMM(0.6),
                pcbnew.FromMM(0.3), net.GetNetCode()))
            # A caller that omits the process proof stays fail-closed.
            self.assertIsNotNone(cec_fr._via_pad_excluded(
                board, via.GetPosition(), pcbnew.FromMM(0.6)))
            summary = cec_constraints.via_on_pad_summary(path)
            self.assertEqual(summary["same"], 0, summary)
            self.assertEqual(summary["diff"], 0, summary)
            self.assertEqual(summary["allowed_pofv"], 1, summary)

    def test_smd_via_guards_block_partial_lands_but_keep_pofv_core_open(self):
        """The router must not rediscover U2.3's narrow-pad via escape.

        A 0.6 mm Default-class land cannot fit in the 0.6 mm-tall oval once
        its full radius is considered, while the centre of a 2 mm square is a
        valid, declared POFV site.  The baked rule areas block vias only.
        """
        from shapely.geometry import Point, Polygon
        from shapely.ops import unary_union

        with tempfile.TemporaryDirectory() as directory:
            path = self._board(directory, "jlcpcb_6l_pofv_signal")
            board = pcbnew.LoadBoard(path)
            net = board.FindNet("GND")

            def add_smd(ref, x, size, shape):
                fp = pcbnew.FOOTPRINT(board)
                fp.SetReference(ref)
                pos = pcbnew.VECTOR2I_MM(x, 10.0)
                fp.SetPosition(pos)
                pad = pcbnew.PAD(fp)
                pad.SetPadName("1")
                pad.SetShape(shape)
                pad.SetSize(pcbnew.VECTOR2I_MM(*size))
                pad.SetPosition(pos)
                pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
                pad.SetLayerSet(pcbnew.PAD.SMDMask())
                pad.SetNet(net)
                fp.Add(pad)
                board.Add(fp)

            add_smd("USMALL", 9.0, (1.95, 0.6), pcbnew.PAD_SHAPE_OVAL)
            add_smd("UBIG", 14.0, (2.0, 2.0), pcbnew.PAD_SHAPE_RECT)
            pcbnew.SaveBoard(path, board)

            guards = cec_fr.smd_via_keepouts(path)
            self.assertTrue(guards)
            geom = unary_union([Polygon(g["polygon"], g.get("holes") or ())
                                for g in guards])
            self.assertTrue(geom.covers(Point(9.0, 10.0)),
                            "a via cannot fit anywhere in the narrow oval")
            self.assertFalse(geom.covers(Point(14.0, 10.0)),
                             "the fully-contained POFV core must stay open")
            self.assertTrue(geom.covers(Point(14.85, 10.0)),
                            "a partial land at the large pad edge is forbidden")
            self.assertTrue(all(g["allow_tracks"] and not g["allow_vias"]
                                and not g["block_fills"] for g in guards))
            self.assertTrue(all(set(g["layers"]) == {"F.Cu", "B.Cu"}
                                for g in guards))

            hinted = os.path.join(directory, "hinted.kicad_pcb")
            cec_fr.bake_hints(path, hinted, keepouts=guards)
            baked = pcbnew.LoadBoard(hinted)
            zones = [z for z in baked.Zones()
                     if z.GetZoneName().startswith("SMD_VIA_GUARD_")]
            self.assertEqual(len(zones), len(guards))
            self.assertTrue(all(not z.GetDoNotAllowTracks() for z in zones))
            self.assertTrue(all(z.GetDoNotAllowVias() for z in zones))
            self.assertTrue(all(not z.GetDoNotAllowZoneFills() for z in zones))

    def test_back_copper_logo_guard_does_not_block_front_routes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._board(directory, "jlcpcb_6l_pofv_signal")
            board = pcbnew.LoadBoard(path)
            fp = pcbnew.FOOTPRINT(board)
            fp.SetReference("LOGO1")
            fp.SetValue("CEC_Logo_Copper")
            shape = pcbnew.PCB_SHAPE(fp)
            shape.SetShape(pcbnew.SHAPE_T_RECT)
            shape.SetStart(pcbnew.VECTOR2I_MM(8.0, 8.0))
            shape.SetEnd(pcbnew.VECTOR2I_MM(12.0, 11.0))
            shape.SetLayer(pcbnew.B_Cu)
            fp.Add(shape)
            board.Add(fp)
            pcbnew.SaveBoard(path, board)

            guards = cec_fr.decorative_copper_keepouts(path)
            self.assertEqual(len(guards), 1)
            self.assertEqual(guards[0]["layers"], ("B.Cu",))
            self.assertFalse(guards[0]["allow_tracks"])
            self.assertFalse(guards[0]["allow_vias"])
            self.assertFalse(guards[0]["block_fills"])
            self.assertLessEqual(guards[0]["x0"], 7.7)
            self.assertGreaterEqual(guards[0]["x1"], 12.3)
            self.assertFalse(cec_fr._via_spot_clear(
                board, pcbnew.VECTOR2I_MM(8.0, 9.5),
                pcbnew.FromMM(0.6), pcbnew.FromMM(0.2), set(),
                drill_nm=pcbnew.FromMM(0.3), net_code=0))

    def test_non_through_via_fails_profile_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._board(directory, "jlcpcb_6l_pofv_high_current")
            board = pcbnew.LoadBoard(path)
            net = board.FindNet("GND")
            via = pcbnew.PCB_VIA(board)
            via.SetViaType(pcbnew.VIATYPE_BLIND)
            via.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(10),
                                            pcbnew.FromMM(10)))
            via.SetWidth(pcbnew.FromMM(0.6))
            via.SetDrill(pcbnew.FromMM(0.3))
            via.SetLayerPair(board.GetLayerID("F.Cu"),
                             board.GetLayerID("In2.Cu"))
            via.SetNet(net)
            board.Add(via)
            ok, detail = cec_constraints._chk_through_vias_only(
                board, path, {})
            self.assertFalse(ok, detail)

    def test_deterministic_router_uses_in3_when_other_layers_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._board(directory, "jlcpcb_6l_pofv_high_current")
            board = pcbnew.LoadBoard(path)
            sig = pcbnew.NETINFO_ITEM(board, "/SIG")
            block = pcbnew.NETINFO_ITEM(board, "/BLOCK")
            board.Add(sig)
            board.Add(block)
            for ref, x in (("P1", 3.0), ("P2", 17.0)):
                fp = pcbnew.FOOTPRINT(board)
                fp.SetReference(ref)
                pos = pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(10.0))
                fp.SetPosition(pos)
                pad = pcbnew.PAD(fp)
                pad.SetPadName("1")
                pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
                pad.SetSize(pcbnew.VECTOR2I(pcbnew.FromMM(1.8),
                                            pcbnew.FromMM(1.8)))
                pad.SetDrillSize(pcbnew.VECTOR2I(pcbnew.FromMM(0.9),
                                                 pcbnew.FromMM(0.9)))
                pad.SetPosition(pos)
                pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
                pad.SetLayerSet(pcbnew.PAD.PTHMask())
                pad.SetNet(sig)
                fp.Add(pad)
                board.Add(fp)
            for layer in ("F.Cu", "In2.Cu", "B.Cu"):
                track = pcbnew.PCB_TRACK(board)
                track.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(10),
                                               pcbnew.FromMM(0.6)))
                track.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(10),
                                             pcbnew.FromMM(19.4)))
                track.SetWidth(pcbnew.FromMM(0.5))
                track.SetLayer(board.GetLayerID(layer))
                track.SetNet(block)
                board.Add(track)
            used, laid = cec_router._route_blocked_net(
                board, "/SIG", width_mm=0.25, clear_mm=0.25)
            self.assertEqual(used, "direct_In3.Cu")
            self.assertTrue(laid)
            self.assertTrue(all(t.GetLayer() == board.GetLayerID("In3.Cu")
                                for t in laid))


if __name__ == "__main__":
    unittest.main()
