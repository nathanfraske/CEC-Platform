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
import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest import mock

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

    def test_signal_layer_is_not_a_power_pour_fallback(self):
        self.assertEqual(self.p.get("power_pour_layers"),
                         ("In3.Cu", "B.Cu", "F.Cu"))
        self.assertNotIn("In2.Cu", self.p.get("power_pour_layers", ()),
                         "Hub In2 is the high-speed signal layer above GND1, "
                         "not spare territory for a power corridor")

    def test_pour_corridors_are_reserved_before_freerouting(self):
        self.assertTrue(self.p.get("pour_reserve"),
                        "routed-object pours must become Freerouting keepouts "
                        "before ordinary signals are routed")

    def test_pour_asks_live_on_in3(self):
        asks = self.p.get("pour_asks") or []
        self.assertEqual({a["net"] for a in asks}, {
            "+5VSB", "+5V_SYS", "/PSU_5V_KVM", "/+5V_HOLD",
            "/VCC_P1", "/VCC_P2", "/VCC_P3", "/VCC_P4",
        })
        for a in asks:
            self.assertEqual(tuple(a["layers"]), ("In3.Cu",),
                             f"pour ask {a['net']} must live on the approved "
                             "six-layer In3 power layer")
            self.assertFalse(a.get("evac", True),
                             "hub asks stay post-route additive (no eviction)")

    def test_short_ask_resolves_current_hierarchical_net_name(self):
        import cec_pourplan

        prepared = {
            "/POWER INPUT + SOURCE SELECTION/PSU_5V_KVM": [
                ("U1", 10.0, 10.0, False),
                ("J1", 20.0, 12.0, True),
            ]
        }
        spec = cec_pourplan._ask_spec(
            {"net": "/PSU_5V_KVM", "layers": ("In3.Cu",),
             "provenance": "placer_ask", "evac": False},
            prepared, (0.0, 0.0, 30.0, 20.0), 1.0)
        self.assertIsNotNone(spec)
        self.assertEqual(spec.net,
                         "/POWER INPUT + SOURCE SELECTION/PSU_5V_KVM")
        self.assertEqual(spec.layers, ("In3.Cu",))

    def test_overunder_asks_are_not_dropped_before_lane_synthesis(self):
        import cec_fr

        derived = {"net": "+12V", "provenance": "derived"}
        asked = {"net": "+5VSB", "provenance": "placer_ask"}
        rail = {"net": "+5V_SYS", "provenance": "rail_compiler"}
        now, deferred = cec_fr.partition_prebond_pours(
            [derived, asked, rail], overunder=True)
        self.assertEqual(now, [derived, rail])
        self.assertEqual(deferred, [asked])
        now, deferred = cec_fr.partition_prebond_pours(
            [derived, asked, rail], overunder=False)
        self.assertEqual(now, [derived, asked, rail])
        self.assertEqual(deferred, [])

    def test_complete_rail_contract_owns_surface_pads(self):
        import cec_slab_pour

        with mock.patch.dict(os.environ, {
                "CEC_OVERUNDER": "1", "CEC_POWER_PICKUP": "1"}):
            self.assertTrue(cec_slab_pour._reservation_owns_pad(
                object(), []))


class TestHubMaterializationSidecars(unittest.TestCase):
    def test_sidecars_are_staged_and_rebound_before_board_workers(self):
        import hub_pipeline_run as hub

        with tempfile.TemporaryDirectory() as tmp:
            candidate = os.path.join(tmp, "candidate", "hub-standard-rev2-candidate.kicad_pcb")
            output = os.path.join(tmp, "wave", "hub-cand0.kicad_pcb")
            os.makedirs(os.path.dirname(candidate))
            os.makedirs(os.path.dirname(output))
            open(candidate, "w", encoding="utf-8").close()
            with open(os.path.splitext(candidate)[0] + ".kicad_pro", "w",
                      encoding="utf-8") as fh:
                json.dump({"meta": {"filename": "stale.kicad_pro"}}, fh)
            with open(os.path.splitext(candidate)[0] + ".kicad_dru", "w",
                      encoding="utf-8") as fh:
                fh.write("(version 1)\n")

            copied = hub._stage_reference_sidecars(candidate, output)

            self.assertEqual(len(copied), 2)
            with open(os.path.splitext(output)[0] + ".kicad_pro",
                      encoding="utf-8") as fh:
                project = json.load(fh)
            self.assertEqual(project["meta"]["filename"], "hub-cand0.kicad_pro")
            self.assertTrue(os.path.isfile(os.path.splitext(output)[0] + ".kicad_dru"))


class TestOverunderViaNetPersistence(unittest.TestCase):
    def test_bridge_via_cannot_pierce_foreign_critical_track(self):
        try:
            import pcbnew
            import cec_fr
        except ImportError:
            self.skipTest("pcbnew not available")

        mm = lambda value: int(round(value * 1e6))
        board = pcbnew.CreateEmptyBoard()
        board.SetCopperLayerCount(6)
        rail = pcbnew.NETINFO_ITEM(board, "+5V_TEST")
        pair = pcbnew.NETINFO_ITEM(board, "/USB_D_N")
        board.Add(rail)
        board.Add(pair)
        track = pcbnew.PCB_TRACK(board)
        track.SetStart(pcbnew.VECTOR2I(mm(5.0), mm(10.0)))
        track.SetEnd(pcbnew.VECTOR2I(mm(25.0), mm(10.0)))
        track.SetWidth(mm(0.2))
        track.SetLayer(pcbnew.F_Cu)
        track.SetNet(pair)
        track.SetLocked(True)
        board.Add(track)

        added = cec_fr.add_overunder_vias(board, [
            {"net": "+5V_TEST", "x_mm": 15.0, "y_mm": 10.0},
            {"net": "+5V_TEST", "x_mm": 15.0, "y_mm": 13.0},
        ])
        self.assertEqual(len(added), 1)
        self.assertAlmostEqual(added[0].GetPosition().y / 1e6, 13.0)

    def test_blocked_frozen_field_member_reseats_inside_two_layer_overlap(self):
        try:
            import pcbnew
            import cec_fr
        except ImportError:
            self.skipTest("pcbnew not available")

        mm = lambda value: int(round(value * 1e6))
        board = pcbnew.CreateEmptyBoard()
        board.SetCopperLayerCount(6)
        rail = pcbnew.NETINFO_ITEM(board, "+5V_TEST")
        pair = pcbnew.NETINFO_ITEM(board, "/USB_D_N")
        board.Add(rail)
        board.Add(pair)
        track = pcbnew.PCB_TRACK(board)
        track.SetStart(pcbnew.VECTOR2I(mm(5.0), mm(10.0)))
        track.SetEnd(pcbnew.VECTOR2I(mm(25.0), mm(10.0)))
        track.SetWidth(mm(0.2))
        track.SetLayer(pcbnew.F_Cu)
        track.SetNet(pair)
        track.SetLocked(True)
        board.Add(track)
        polygon = [[5.0, 5.0], [25.0, 5.0],
                   [25.0, 15.0], [5.0, 15.0]]
        pours = [
            {"net": "+5V_TEST", "layer": "F.Cu", "polygon": polygon},
            {"net": "+5V_TEST", "layer": "B.Cu", "polygon": polygon},
        ]
        frozen = [
            {"net": "+5V_TEST", "field_index": 0,
             "field_kind": "terminal", "x_mm": 15.0, "y_mm": 10.0},
            {"net": "+5V_TEST", "field_index": 0,
             "field_kind": "terminal", "x_mm": 15.0, "y_mm": 13.0},
        ]

        reseated, report = cec_fr.reseat_overunder_vias(
            board, frozen, pours)

        self.assertTrue(report["ok"])
        self.assertTrue(report["changed"])
        self.assertEqual(report["reseated"], 1)
        self.assertEqual(len(reseated), len(frozen))
        self.assertNotEqual(reseated[0]["y_mm"], 10.0)
        self.assertEqual(reseated[1], frozen[1])
        self.assertEqual(len(cec_fr.add_overunder_vias(board, reseated)), 2)

    def test_stale_filled_ground_plane_cannot_steal_rail_via_net(self):
        try:
            import pcbnew
        except ImportError:
            self.skipTest("pcbnew not available")

        build = textwrap.dedent("""
            import os, sys, pcbnew
            path = sys.argv[1]
            mm = lambda value: int(value * 1e6)
            board = pcbnew.CreateEmptyBoard()
            board.SetCopperLayerCount(6)
            gnd = pcbnew.NETINFO_ITEM(board, "GND")
            rail = pcbnew.NETINFO_ITEM(board, "+5V_TEST")
            board.Add(gnd); board.Add(rail)
            footprint = pcbnew.FOOTPRINT(board)
            footprint.SetReference("J1")
            pad = pcbnew.PAD(footprint)
            pad.SetNumber("1")
            pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetSize(pcbnew.VECTOR2I(mm(2), mm(2)))
            pad.SetPosition(pcbnew.VECTOR2I(mm(5), mm(5)))
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            pad.SetLayerSet(pcbnew.PAD.SMDMask())
            pad.SetNet(rail)
            footprint.Add(pad); board.Add(footprint)
            zone = pcbnew.ZONE(board)
            zone.SetNet(gnd)
            zone.SetLayer(pcbnew.In1_Cu)
            outline = zone.Outline(); outline.NewOutline()
            for x, y in ((2, 2), (38, 2), (38, 38), (2, 38)):
                outline.Append(mm(x), mm(y))
            board.Add(zone)
            pcbnew.ZONE_FILLER(board).Fill(board.Zones())
            pcbnew.SaveBoard(path, board)
            os._exit(0)
        """)
        add = textwrap.dedent("""
            import os, sys, pcbnew
            sys.path.insert(0, sys.argv[2])
            import cec_fr
            path = sys.argv[1]
            board = pcbnew.LoadBoard(path)
            added = cec_fr.add_overunder_vias(
                board, [{"net": "+5V_TEST", "x_mm": 20.0, "y_mm": 20.0}])
            if len(added) != 1:
                raise RuntimeError("expected one bridge via, got %d" % len(added))
            pcbnew.SaveBoard(path, board)
            os._exit(0)
        """)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "stale-plane.kicad_pcb")
            subprocess.run([sys.executable, "-c", build, path], check=True)
            subprocess.run([sys.executable, "-c", add, path,
                            os.path.join(ROOT, "scripts")], check=True)
            board = pcbnew.LoadBoard(path)
            vias = [item for item in board.GetTracks()
                    if item.GetClass() == "PCB_VIA"]
            self.assertEqual(len(vias), 1)
            self.assertEqual(vias[0].GetNetname(), "+5V_TEST")
            self.assertTrue(vias[0].IsLocked())


class TestOverunderInternalCutoutRaster(unittest.TestCase):
    def test_reverse_led_edge_cutouts_block_every_copper_layer(self):
        try:
            import pcbnew
            import cec_slab_pour
        except ImportError:
            self.skipTest("pcbnew/scipy not available")

        path = os.path.join(
            ROOT, "beta", "hub-standard-rev2", "candidate",
            "hub-standard-rev2-candidate.kicad_pcb")
        board = pcbnew.LoadBoard(path)
        grid = cec_slab_pour.Grid(board)
        # An unrelated rail must see all apertures. +5VSB itself owns an LED
        # pad around each aperture and is deliberately allowed a filler-clipped
        # local terminal approach; field-via seating remains blocked for it.
        nc = board.GetNetcodeFromNetname("+5V_SYS")
        foreign, _anchors = cec_slab_pour.rasterize(
            board, nc, board.GetLayerID("In3.Cu"), grid)
        cutouts = [item for fp in board.GetFootprints()
                   for item in fp.GraphicalItems()
                   if item.GetLayer() == pcbnew.Edge_Cuts]
        self.assertEqual(len(cutouts), 6)
        for item in cutouts:
            center = item.GetBoundingBox().GetCenter()
            self.assertTrue(
                foreign[grid.iy(center.y / 1e6), grid.ix(center.x / 1e6)],
                "internal Edge.Cuts aperture must be foreign to the pour search")

        # Owning a surface pad exempts only that pad's copper layer.  The old
        # footprint-wide exemption also erased the physical through-cutout on
        # B.Cu/inner copper, so the raster accepted a rail that KiCad split
        # during exact zone fill.
        own_nc = board.GetNetcodeFromNetname("+5VSB")
        own_inner, _anchors = cec_slab_pour.rasterize(
            board, own_nc, board.GetLayerID("In3.Cu"), grid)
        for item in cutouts:
            center = item.GetBoundingBox().GetCenter()
            self.assertTrue(
                own_inner[grid.iy(center.y / 1e6), grid.ix(center.x / 1e6)],
                "surface-pad ownership must not erase a through-cutout on inner copper")


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

    def test_large_power_land_keeps_full_requested_pickup_width(self):
        """A neck-down is a physical exception, never the default launch."""
        import pcbnew
        import cec_fr

        board = self._one_pad_board()
        pours = [{"net": "+5VSB", "layer": "In2.Cu",
                  "polygon": [(0.0, 0.0), (10.0, 0.0),
                              (10.0, 5.0), (0.0, 5.0)]}]
        result = cec_fr.synthesize_power_pickups(
            board, pours, stub_w=1.0, lock=True)
        tracks = [item for item in board.GetTracks()
                  if item.GetClass() == "PCB_TRACK"]

        self.assertEqual((result["stubs"], result["skipped"]), (1, 0))
        self.assertEqual(len(tracks), 1)
        self.assertEqual(tracks[0].GetWidth(), pcbnew.FromMM(1.0))
        self.assertTrue(tracks[0].IsLocked())

    def test_surface_linked_local_cell_still_gets_one_stack_pickup(self):
        """Local same-net copper is not proof of an inner-layer portal."""
        import pcbnew
        import cec_fr

        board = self._one_pad_board()
        first_fp = next(iter(board.GetFootprints()))
        first_fp.SetReference("C_LOCAL")
        first = next(iter(first_fp.Pads()))
        first.SetPadName("1")
        net = first.GetNet()

        owner = pcbnew.FOOTPRINT(board)
        owner.SetReference("U_LOCAL")
        owner.SetPosition(pcbnew.VECTOR2I_MM(7.0, 2.5))
        second = pcbnew.PAD(owner)
        second.SetPadName("1")
        second.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        second.SetShape(pcbnew.PAD_SHAPE_RECT)
        second.SetSize(pcbnew.VECTOR2I_MM(1.0, 1.0))
        second.SetPosition(owner.GetPosition())
        layers = pcbnew.LSET(); layers.AddLayer(pcbnew.F_Cu)
        second.SetLayerSet(layers)
        second.SetNet(net)
        owner.Add(second)
        board.Add(owner)

        local = pcbnew.PCB_TRACK(board)
        local.SetStart(first.GetPosition())
        local.SetEnd(second.GetPosition())
        local.SetWidth(pcbnew.FromMM(0.3))
        local.SetLayer(pcbnew.F_Cu)
        local.SetNet(net)
        local.SetLocked(True)
        board.Add(local)

        result = cec_fr.synthesize_power_pickups(
            board, [{"net": "+5VSB", "layer": "In2.Cu",
                     "polygon": [(0.0, 0.0), (10.0, 0.0),
                                 (10.0, 5.0), (0.0, 5.0)]}],
            lock=True)
        vias = [item for item in board.GetTracks()
                if item.GetClass() == "PCB_VIA"]

        self.assertEqual((result["vias"], result["skipped"]), (1, 0))
        self.assertEqual(len(vias), 1,
                         "one portal promotes the whole connected cell")

    def test_pickup_extends_guarded_search_beyond_legacy_rays(self):
        import pcbnew
        import cec_fr

        board = self._one_pad_board()
        pad = next(iter(next(iter(board.GetFootprints())).Pads()))
        pad.GetParentFootprint().SetPosition(pcbnew.VECTOR2I_MM(1.0, 2.5))
        pad.SetPosition(pcbnew.VECTOR2I_MM(1.0, 2.5))
        foreign = pcbnew.NETINFO_ITEM(board, "/FOREIGN")
        board.Add(foreign)
        blocker = pcbnew.PCB_TRACK(board)
        blocker.SetStart(pcbnew.VECTOR2I_MM(1.3, 2.5))
        blocker.SetEnd(pcbnew.VECTOR2I_MM(1.9, 2.5))
        blocker.SetWidth(pcbnew.FromMM(0.2))
        blocker.SetLayer(pcbnew.In2_Cu)
        blocker.SetNet(foreign)
        board.Add(blocker)
        pours = [{"net": "+5VSB", "layer": "In2.Cu",
                  "polygon": [(1.0, 2.1), (10.0, 2.1),
                              (10.0, 2.9), (1.0, 2.9)]}]

        result = cec_fr.synthesize_power_pickups(board, pours)
        vias = [item for item in board.GetTracks()
                if item.GetClass() == "PCB_VIA"]

        self.assertEqual((result["vias"], result["skipped"]), (1, 0))
        self.assertGreater(vias[0].GetPosition().x - pad.GetPosition().x,
                           pcbnew.FromMM(1.2))

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

    def test_pickup_uses_profile_pofv_geometry_not_power_via_geometry(self):
        import pcbnew
        import cec_fr

        b = self._one_pad_board()
        b.SetCopperLayerCount(6)
        props = b.GetProperties()
        props["CEC_FAB_PROFILE"] = "jlcpcb_6l_pofv_signal"
        b.SetProperties(props)
        power = pcbnew.NETCLASS("Power")
        power.SetTrackWidth(int(1.0e6))
        power.SetViaDiameter(int(0.8e6))
        power.SetViaDrill(int(0.4e6))
        b.GetNetInfo().GetNetItem("+5VSB").SetNetClass(power)
        pours = [{"net": "+5VSB", "layers": ("In3.Cu",)}]

        result = cec_fr.synthesize_power_pickups(b, pours)
        via = next(t for t in b.GetTracks() if t.GetClass() == "PCB_VIA")
        self.assertEqual((result["vias"], result["pofv"]), (1, 1))
        self.assertEqual(via.GetWidth(via.TopLayer()), int(0.35e6))
        self.assertEqual(via.GetDrillValue(), int(0.25e6))

    def test_compact_same_net_pad_bank_shares_qualified_pofv(self):
        """A tiny package land may neck to its adjacent, POFV-capable peer.

        The recovery must be topology based: the same board without the mate's
        qualified via remains skipped by the existing fail-closed contract.
        """
        import pcbnew
        import cec_fr

        board = self._one_pad_board()
        board.SetCopperLayerCount(6)
        props = board.GetProperties()
        props["CEC_FAB_PROFILE"] = "jlcpcb_6l_pofv_signal"
        board.SetProperties(props)
        footprint = next(iter(board.GetFootprints()))
        footprint.SetReference("U_TEST")
        tiny = next(iter(footprint.Pads()))
        tiny.SetPadName("6")
        tiny.SetSize(pcbnew.VECTOR2I_MM(0.60, 0.20))

        anchor = pcbnew.PAD(footprint)
        anchor.SetPadName("7")
        anchor.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        anchor.SetShape(pcbnew.PAD_SHAPE_RECT)
        anchor.SetSize(pcbnew.VECTOR2I_MM(1.05, 0.40))
        anchor.SetPosition(pcbnew.VECTOR2I(
            tiny.GetPosition().x + pcbnew.FromMM(0.90),
            tiny.GetPosition().y))
        layers = pcbnew.LSET()
        layers.AddLayer(pcbnew.F_Cu)
        anchor.SetLayerSet(layers)
        anchor.SetNet(tiny.GetNet())
        footprint.Add(anchor)

        result = cec_fr.synthesize_power_pickups(
            board, [{"net": "+5VSB", "layers": ("In3.Cu",)}],
            lock=True)
        vias = [item for item in board.GetTracks()
                if item.GetClass() == "PCB_VIA"]
        links = [item for item in board.GetTracks()
                 if item.GetClass() == "PCB_TRACK"]

        self.assertEqual((result["pads"], result["vias"], result["pofv"],
                          result["stubs"], result["skipped"]),
                         (2, 1, 1, 1, 0))
        self.assertEqual(result["cluster_recovered"], 1)
        self.assertEqual(result["cluster_links"][0]["from_pad"], "6")
        self.assertEqual(result["cluster_links"][0]["to_pad"], "7")
        self.assertEqual(vias[0].GetPosition(), anchor.GetPosition())
        self.assertEqual(links[0].GetWidth(), pcbnew.FromMM(0.20))
        self.assertEqual(
            {(point.x, point.y)
             for point in (links[0].GetStart(), links[0].GetEnd())},
            {(point.x, point.y)
             for point in (tiny.GetPosition(), anchor.GetPosition())})
        self.assertTrue(all(item.IsLocked() for item in vias + links))

    def test_authority_pin_can_share_nearby_decoupler_pofv(self):
        """A current terminal may use its local bypass pad as the portal.

        The terminal filter deliberately excludes the capacitor from ordinary
        pickup enumeration; recovery must still discover the compact cell,
        prove the POFV independently, and commit the link transactionally.
        """
        import pcbnew
        import cec_fr

        board = self._one_pad_board()
        board.SetCopperLayerCount(6)
        props = board.GetProperties()
        props["CEC_FAB_PROFILE"] = "jlcpcb_6l_pofv_signal"
        board.SetProperties(props)
        switch = next(iter(board.GetFootprints()))
        switch.SetReference("U_SWITCH")
        source = next(iter(switch.Pads()))
        source.SetPadName("2")
        source.SetSize(pcbnew.VECTOR2I_MM(1.05, 0.40))

        cap = pcbnew.FOOTPRINT(board); cap.SetReference("C_IN")
        mate = pcbnew.PAD(cap); mate.SetPadName("1")
        mate.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        mate.SetShape(pcbnew.PAD_SHAPE_RECT)
        mate.SetSize(pcbnew.VECTOR2I_MM(0.90, 0.95))
        mate.SetPosition(pcbnew.VECTOR2I(
            source.GetPosition().x - pcbnew.FromMM(1.30),
            source.GetPosition().y))
        layers = pcbnew.LSET(); layers.AddLayer(pcbnew.F_Cu)
        mate.SetLayerSet(layers); mate.SetNet(source.GetNet())
        cap.Add(mate); board.Add(cap)

        real_spot_clear = cec_fr._via_spot_clear

        def only_decoupler_portal(board_arg, at, *args, **kwargs):
            if at == mate.GetPosition():
                return real_spot_clear(board_arg, at, *args, **kwargs)
            return False

        with mock.patch.object(
                cec_fr, "_via_spot_clear",
                side_effect=only_decoupler_portal):
            result = cec_fr.synthesize_power_pickups(
                board, [{"net": "+5VSB", "layers": ("In3.Cu",)}],
                terminal_refs_by_net={"+5VSB": {"U_SWITCH"}}, lock=True)

        vias = [item for item in board.GetTracks()
                if item.GetClass() == "PCB_VIA"]
        self.assertEqual((result["skipped"], result["cluster_recovered"],
                          result["pofv"]), (0, 1, 1))
        self.assertEqual(vias[0].GetPosition(), mate.GetPosition())
        self.assertEqual(result["cluster_links"][0]["to_ref"], "C_IN")
        self.assertEqual(result["cluster_links"][0]["anchor_type"],
                         "PCB_VIA")

    def test_compact_pad_bank_shares_offset_component_portal(self):
        """A duplicate pin may share a sibling's guarded offset dogbone.

        The portal is deliberately not inside either package land.  A foreign
        inner-layer obstruction prevents every new through barrel around the
        orphan pin while leaving the short same-layer pin-bank link legal.
        Recovery must follow the sibling's real connectivity component rather
        than require a via-in-pad coincidence.
        """
        import pcbnew
        import cec_fr

        board = self._one_pad_board()
        board.SetCopperLayerCount(6)
        props = board.GetProperties()
        props["CEC_FAB_PROFILE"] = "jlcpcb_6l_pofv_signal"
        board.SetProperties(props)
        footprint = next(iter(board.GetFootprints()))
        footprint.SetReference("U_BANK")
        orphan = next(iter(footprint.Pads()))
        orphan.SetPadName("8")
        orphan.SetSize(pcbnew.VECTOR2I_MM(1.05, 0.40))
        net = orphan.GetNet()
        power = pcbnew.NETCLASS("Power")
        power.SetTrackWidth(pcbnew.FromMM(1.0))
        power.SetViaDiameter(pcbnew.FromMM(0.8))
        power.SetViaDrill(pcbnew.FromMM(0.4))
        net.SetNetClass(power)

        mate = pcbnew.PAD(footprint)
        mate.SetPadName("1")
        mate.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        mate.SetShape(pcbnew.PAD_SHAPE_RECT)
        mate.SetSize(pcbnew.VECTOR2I_MM(1.05, 0.40))
        mate.SetPosition(pcbnew.VECTOR2I(
            orphan.GetPosition().x - pcbnew.FromMM(1.35),
            orphan.GetPosition().y))
        layers = pcbnew.LSET(); layers.AddLayer(pcbnew.F_Cu)
        mate.SetLayerSet(layers)
        mate.SetNet(net)
        footprint.Add(mate)

        portal = pcbnew.PCB_VIA(board)
        portal.SetPosition(pcbnew.VECTOR2I_MM(0.5, 2.5))
        portal.SetWidth(pcbnew.FromMM(0.8))
        portal.SetDrill(pcbnew.FromMM(0.4))
        portal.SetNet(net)
        portal.SetLocked(True)
        board.Add(portal)
        local = pcbnew.PCB_TRACK(board)
        local.SetStart(mate.GetPosition())
        local.SetEnd(portal.GetPosition())
        local.SetWidth(pcbnew.FromMM(1.0))
        local.SetLayer(pcbnew.F_Cu)
        local.SetNet(net)
        local.SetLocked(True)
        board.Add(local)

        foreign = pcbnew.NETINFO_ITEM(board, "/INNER_BLOCKER")
        board.Add(foreign)
        blocker = pcbnew.PCB_TRACK(board)
        blocker.SetStart(pcbnew.VECTOR2I_MM(5.0, -1.0))
        blocker.SetEnd(pcbnew.VECTOR2I_MM(5.0, 6.0))
        blocker.SetWidth(pcbnew.FromMM(6.0))
        blocker.SetLayer(pcbnew.In2_Cu)
        blocker.SetNet(foreign)
        board.Add(blocker)

        result = cec_fr.synthesize_power_pickups(
            board, [{"net": "+5VSB", "layer": "In3.Cu",
                     "polygon": [(-1.0, -1.0), (10.0, -1.0),
                                 (10.0, 6.0), (-1.0, 6.0)]}],
            plane_nets=(), lock=True)
        links = [item for item in board.GetTracks()
                 if item.GetClass() == "PCB_TRACK"
                 and item.GetNetCode() == net.GetNetCode()
                 and item.m_Uuid.AsString() != local.m_Uuid.AsString()]

        self.assertEqual((result["pads"], result["vias"],
                          result["cluster_recovered"], result["skipped"]),
                         (1, 0, 1, 0))
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].GetWidth(), pcbnew.FromMM(0.40))
        self.assertEqual(result["cluster_links"][0]["anchor_type"],
                         "PCB_VIA")
        self.assertEqual(result["cluster_links"][0]["anchor_portal"],
                         portal.m_Uuid.AsString())

    def test_pickup_refusal_records_guard_stage_counts(self):
        """A refusal certificate identifies the exhausted physical gates."""
        import pcbnew
        import cec_fr

        board = self._one_pad_board()
        foreign = pcbnew.NETINFO_ITEM(board, "/BLOCK_ALL_VIAS")
        board.Add(foreign)
        blocker = pcbnew.PCB_TRACK(board)
        blocker.SetStart(pcbnew.VECTOR2I_MM(5.0, -1.0))
        blocker.SetEnd(pcbnew.VECTOR2I_MM(5.0, 6.0))
        blocker.SetWidth(pcbnew.FromMM(7.0))
        blocker.SetLayer(pcbnew.In2_Cu)
        blocker.SetNet(foreign)
        board.Add(blocker)

        result = cec_fr.synthesize_power_pickups(
            board, [{"net": "+5VSB", "layer": "In2.Cu",
                     "polygon": [(0.0, 0.0), (10.0, 0.0),
                                 (10.0, 5.0), (0.0, 5.0)]}],
            plane_nets=())
        guard = result["skipped_detail"][0]["guard_summary"]

        self.assertEqual(result["skipped"], 1)
        self.assertGreater(guard["probes"], 0)
        self.assertEqual(guard["placed"], 0)
        self.assertGreater(guard["via_spot_clearance"], 0)

    def test_enclosed_power_terminal_gets_guarded_escape_fanout(self):
        import pcbnew
        import cec_fr

        board = self._one_pad_board()
        board.SetCopperLayerCount(6)
        props = board.GetProperties()
        props["CEC_FAB_PROFILE"] = "jlcpcb_6l_pofv_signal"
        board.SetProperties(props)
        footprint = next(iter(board.GetFootprints()))
        footprint.SetReference("U_ESCAPE")
        pad = next(iter(footprint.Pads()))
        pad.SetPadName("2")
        pickup = cec_fr.synthesize_power_pickups(
            board, [{"net": "+5VSB", "layers": ("In3.Cu",)}], lock=True)
        self.assertEqual((pickup["pofv"], pickup["skipped"]), (1, 0))

        result = cec_fr.synthesize_power_escape_fanouts(
            board,
            [{"net": "+5VSB", "polygon": [
                (0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0)]}],
            [{"ref": "U_ESCAPE", "pad": "2", "net": "+5VSB"}],
            stub_w=0.6, lock=True)
        vias = [item for item in board.GetTracks()
                if item.GetClass() == "PCB_VIA"]
        tracks = [item for item in board.GetTracks()
                  if item.GetClass() == "PCB_TRACK"]

        self.assertEqual((result["placed"], result["refused"]), (1, 0))
        self.assertEqual(len(vias), 2)
        self.assertEqual(len(tracks), 2)
        self.assertEqual(
            sorted(round(track.GetWidth() / cec_fr.MM, 3)
                   for track in tracks), [0.6, 0.6])
        self.assertEqual(len(result["detail"][0]["track_uuids"]), 2)
        self.assertGreater(result["detail"][0]["offset_mm"], 0.8)
        self.assertTrue(all(item.IsLocked() for item in vias + tracks))

    def test_escape_fanout_refuses_terminal_without_qualified_pofv(self):
        import cec_fr

        board = self._one_pad_board()
        footprint = next(iter(board.GetFootprints()))
        footprint.SetReference("U_ESCAPE")
        pad = next(iter(footprint.Pads()))
        pad.SetPadName("2")
        result = cec_fr.synthesize_power_escape_fanouts(
            board,
            [{"net": "+5VSB", "polygon": [
                (0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0)]}],
            [{"ref": "U_ESCAPE", "pad": "2", "net": "+5VSB"}])

        self.assertEqual((result["placed"], result["refused"]), (0, 1))
        self.assertEqual(result["refused_detail"][0]["reason"],
                         "no qualified POFV anchor")

    def test_adjacent_fine_pitch_power_pads_can_each_receive_pofv(self):
        import pcbnew
        import cec_fr

        b = self._one_pad_board()
        b.SetCopperLayerCount(6)
        props = b.GetProperties()
        props["CEC_FAB_PROFILE"] = "jlcpcb_6l_pofv_signal"
        b.SetProperties(props)
        footprint = next(iter(b.GetFootprints()))
        first = next(iter(footprint.Pads()))
        first.SetSize(pcbnew.VECTOR2I_MM(0.40, 0.40))
        second = pcbnew.PAD(footprint)
        second.SetPadName("2")
        second.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        second.SetShape(pcbnew.PAD_SHAPE_RECT)
        second.SetSize(pcbnew.VECTOR2I_MM(0.40, 0.40))
        second.SetPosition(pcbnew.VECTOR2I(
            first.GetPosition().x + pcbnew.FromMM(0.50),
            first.GetPosition().y))
        layers = pcbnew.LSET(); layers.AddLayer(pcbnew.F_Cu)
        second.SetLayerSet(layers)
        second.SetNet(first.GetNet())
        footprint.Add(second)

        result = cec_fr.synthesize_power_pickups(
            b, [{"net": "+5VSB", "layers": ("In3.Cu",)}])
        vias = [item for item in b.GetTracks()
                if item.GetClass() == "PCB_VIA"]
        self.assertEqual((result["vias"], result["pofv"]), (2, 2))
        self.assertEqual({(item.GetPosition().x, item.GetPosition().y)
                          for item in vias},
                         {(first.GetPosition().x, first.GetPosition().y),
                          (second.GetPosition().x, second.GetPosition().y)})

    def test_pickup_neckdown_fits_narrow_power_pad(self):
        import pcbnew
        import cec_fr

        b = self._one_pad_board()
        pad = next(iter(next(iter(b.GetFootprints())).Pads()))
        pad.SetSize(pcbnew.VECTOR2I(int(1.0e6), int(0.4e6)))
        power = pcbnew.NETCLASS("Power")
        power.SetTrackWidth(int(1.0e6))
        power.SetViaDiameter(int(0.8e6))
        power.SetViaDrill(int(0.4e6))
        b.GetNetInfo().GetNetItem("+5VSB").SetNetClass(power)
        pours = [{"net": "+5VSB", "layer": "In2.Cu",
                  "polygon": [(0.0, 0.0), (10.0, 0.0),
                              (10.0, 5.0), (0.0, 5.0)]}]

        result = cec_fr.synthesize_power_pickups(b, pours)
        stubs = [t for t in b.GetTracks()
                 if t.GetClass() == "PCB_TRACK"]
        via = next(t for t in b.GetTracks()
                   if t.GetClass() == "PCB_VIA")
        self.assertEqual((result["vias"], result["stubs"]), (1, 2))
        self.assertEqual({stub.GetWidth() for stub in stubs},
                         {int(0.2e6), int(1.0e6)})
        narrow_length = sum(stub.GetLength() for stub in stubs
                            if stub.GetWidth() == int(0.2e6))
        self.assertLessEqual(narrow_length, int(0.6e6))
        self.assertEqual(via.GetWidth(via.TopLayer()), int(0.8e6))
        self.assertEqual(via.GetDrillValue(), int(0.4e6))

    def test_pre_route_pickup_can_be_fixed_without_locking_whole_net(self):
        import cec_fr

        b = self._one_pad_board()
        pours = [{"net": "+5VSB", "layer": "In2.Cu",
                  "polygon": [(0.0, 0.0), (10.0, 0.0),
                              (10.0, 5.0), (0.0, 5.0)]}]
        result = cec_fr.synthesize_power_pickups(b, pours, lock=True)
        pickup_items = list(b.GetTracks())

        self.assertEqual((result["vias"], result["stubs"]), (1, 1))
        self.assertTrue(pickup_items)
        self.assertTrue(all(item.IsLocked() for item in pickup_items))

    def test_same_footprint_duplicate_smd_pins_are_locally_joined(self):
        import pcbnew
        import cec_fr

        board = self._one_pad_board()
        footprint = next(iter(board.GetFootprints()))
        net = board.GetNetInfo().GetNetItem("+5VSB")
        first = next(iter(footprint.Pads()))
        first.SetNumber("1")
        second = pcbnew.PAD(footprint)
        second.SetNumber("2")
        second.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        second.SetShape(pcbnew.PAD_SHAPE_RECT)
        second.SetSize(pcbnew.VECTOR2I(int(1e6), int(1e6)))
        second.SetPosition(pcbnew.VECTOR2I(int(7e6), int(2.5e6)))
        layers = pcbnew.LSET(); layers.AddLayer(pcbnew.F_Cu)
        second.SetLayerSet(layers); second.SetNet(net); footprint.Add(second)

        result = cec_fr.synthesize_same_footprint_links(board)

        tracks = [item for item in board.GetTracks()
                  if item.GetClass() == "PCB_TRACK"]
        self.assertEqual((result["groups"], result["linked"],
                          result["refused"]), (1, 1, 0))
        self.assertTrue(tracks)
        self.assertEqual(tracks[0].GetNetname(), "+5VSB")

    def test_same_footprint_filter_limits_preselected_topology(self):
        import pcbnew
        import cec_fr

        board = self._one_pad_board()
        footprint = next(iter(board.GetFootprints()))
        footprint.SetReference("U1")
        net = board.GetNetInfo().GetNetItem("+5VSB")
        first = next(iter(footprint.Pads()))
        first.SetNumber("1")
        second = pcbnew.PAD(footprint)
        second.SetNumber("2")
        second.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        second.SetShape(pcbnew.PAD_SHAPE_RECT)
        second.SetSize(pcbnew.VECTOR2I(int(1e6), int(1e6)))
        second.SetPosition(pcbnew.VECTOR2I(int(7e6), int(2.5e6)))
        layers = pcbnew.LSET(); layers.AddLayer(pcbnew.F_Cu)
        second.SetLayerSet(layers); second.SetNet(net); footprint.Add(second)

        skipped = cec_fr.synthesize_same_footprint_links(
            board, include_nets={"+5VSB"}, include_refs={"U2"})
        self.assertEqual((skipped["groups"], skipped["linked"]), (0, 0))
        self.assertFalse(list(board.GetTracks()))

        selected = cec_fr.synthesize_same_footprint_links(
            board, include_nets={"+5VSB"}, include_refs={"U1"})
        self.assertEqual((selected["groups"], selected["linked"]), (1, 1))

    def test_connector_power_bank_uses_bounded_wider_local_span(self):
        """Repeated connector power lands remain one local bank even when
        they span farther than a compact IC's ordinary join limit."""
        import pcbnew
        import cec_fr

        board = self._one_pad_board()
        footprint = next(iter(board.GetFootprints()))
        footprint.SetReference("J1")
        net = board.GetNetInfo().GetNetItem("+5VSB")
        first = next(iter(footprint.Pads()))
        first.SetNumber("A4")
        first.SetPosition(pcbnew.VECTOR2I_MM(5.0, 2.5))
        second = pcbnew.PAD(footprint)
        second.SetNumber("B4")
        second.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        second.SetShape(pcbnew.PAD_SHAPE_RECT)
        second.SetSize(pcbnew.VECTOR2I_MM(1.0, 1.0))
        second.SetPosition(pcbnew.VECTOR2I_MM(9.5, 2.5))
        layers = pcbnew.LSET(); layers.AddLayer(pcbnew.F_Cu)
        second.SetLayerSet(layers); second.SetNet(net); footprint.Add(second)

        result = cec_fr.synthesize_same_footprint_links(
            board, netclass_resolver=lambda _net: {
                "track_width": 1.0, "clearance": 0.2,
                "via_diameter": 0.8, "via_drill": 0.4})

        self.assertEqual((result["groups"], result["linked"],
                          result["refused"]), (1, 1, 0))
        self.assertTrue(list(board.GetTracks()))

    def test_connector_power_bank_owns_elongated_land_neckdowns(self):
        """A connector bank may flare only after clearing the real land span,
        and every resulting sub-class prefix must carry the scoped DRC rule
        ownership used by later candidate copies."""
        import pcbnew
        import cec_fr

        board = self._one_pad_board()
        board.SetCopperLayerCount(6)
        footprint = next(iter(board.GetFootprints()))
        footprint.SetReference("J1")
        net = board.GetNetInfo().GetNetItem("+5VSB")
        first = next(iter(footprint.Pads()))
        first.SetNumber("B4")
        first.SetSize(pcbnew.VECTOR2I_MM(1.15, 0.30))
        first.SetPosition(pcbnew.VECTOR2I_MM(3.0, 2.5))
        second = pcbnew.PAD(footprint)
        second.SetNumber("B9")
        second.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        second.SetShape(pcbnew.PAD_SHAPE_RECT)
        second.SetSize(pcbnew.VECTOR2I_MM(1.15, 0.30))
        second.SetPosition(pcbnew.VECTOR2I_MM(7.0, 2.5))
        layers = pcbnew.LSET(); layers.AddLayer(pcbnew.F_Cu)
        second.SetLayerSet(layers); second.SetNet(net); footprint.Add(second)

        result = cec_fr.synthesize_same_footprint_links(
            board, min_w=0.2, clearance=0.25,
            netclass_resolver=lambda _net: {
                "track_width": 0.5, "clearance": 0.25,
                "via_diameter": 0.6, "via_drill": 0.3})

        self.assertEqual((result["linked"], result["refused"]), (1, 0))
        evidence = result["endpoint_neckdown"]
        self.assertEqual(evidence["group"],
                         cec_fr.ENDPOINT_NECKDOWN_GROUP)
        self.assertEqual(evidence["min_width_mm"], 0.2)
        self.assertGreaterEqual(evidence["max_length_mm"], 1.0)
        group = next(group for group in board.Groups()
                     if group.GetName() == cec_fr.ENDPOINT_NECKDOWN_GROUP)
        narrow = [item for item in board.GetTracks()
                  if item.GetClass() == "PCB_TRACK"
                  and item.GetWidth() < pcbnew.FromMM(0.5)]
        self.assertTrue(narrow)
        self.assertTrue(all(group.ContainsItem(item) for item in narrow))

    def test_same_footprint_uses_guarded_bridge_when_face_is_blocked(self):
        import math
        import pcbnew
        import cec_fr
        from unittest import mock

        board = self._one_pad_board()
        board.SetCopperLayerCount(6)
        footprint = next(iter(board.GetFootprints()))
        footprint.SetReference("U1")
        net = board.GetNetInfo().GetNetItem("+5VSB")
        first = next(iter(footprint.Pads()))
        first.SetNumber("1")
        second = pcbnew.PAD(footprint)
        second.SetNumber("2")
        second.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        second.SetShape(pcbnew.PAD_SHAPE_RECT)
        second.SetSize(pcbnew.VECTOR2I(int(1e6), int(1e6)))
        second.SetPosition(pcbnew.VECTOR2I(int(7e6), int(2.5e6)))
        layers = pcbnew.LSET(); layers.AddLayer(pcbnew.F_Cu)
        second.SetLayerSet(layers); second.SetNet(net); footprint.Add(second)
        guarded = cec_fr._guarded_profiled_lastmile_legs

        def block_long_face_route(board_, start, end, width, layer, *args,
                                  **kwargs):
            if (layer == pcbnew.F_Cu
                    and math.hypot(end.x - start.x, end.y - start.y)
                    > int(1.5e6)):
                return None
            return guarded(board_, start, end, width, layer, *args, **kwargs)

        with mock.patch.object(
                cec_fr, "_guarded_profiled_lastmile_legs",
                side_effect=block_long_face_route):
            result = cec_fr.synthesize_same_footprint_links(board)

        self.assertEqual((result["groups"], result["linked"],
                          result["refused"]), (1, 1, 0))
        self.assertEqual(result["vias"], 2)
        items = [item for item in board.GetTracks()
                 if item.GetNetname() == "+5VSB"]
        self.assertTrue(any(item.GetClass() == "PCB_VIA" for item in items))
        self.assertTrue(any(item.GetClass() != "PCB_VIA"
                            and item.GetLayer() != pcbnew.F_Cu
                            for item in items))
        self.assertTrue(all(item.IsLocked() for item in items))

    def test_same_footprint_diff_pair_leg_waits_for_atomic_pair_router(self):
        import pcbnew
        import cec_fr

        board = self._one_pad_board()
        footprint = next(iter(board.GetFootprints()))
        diff_net = pcbnew.NETINFO_ITEM(board, "/USB_D_P")
        board.Add(diff_net)
        first = next(iter(footprint.Pads()))
        first.SetNumber("A6"); first.SetNet(diff_net)
        second = pcbnew.PAD(footprint)
        second.SetNumber("B6")
        second.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        second.SetShape(pcbnew.PAD_SHAPE_RECT)
        second.SetSize(pcbnew.VECTOR2I(int(1e6), int(1e6)))
        second.SetPosition(pcbnew.VECTOR2I(int(6e6), int(2.5e6)))
        layers = pcbnew.LSET(); layers.AddLayer(pcbnew.F_Cu)
        second.SetLayerSet(layers); second.SetNet(diff_net); footprint.Add(second)

        result = cec_fr.synthesize_same_footprint_links(board)

        self.assertEqual((result["groups"], result["linked"]), (0, 0))
        self.assertFalse(list(board.GetTracks()))

    def test_interleaved_duplicate_pair_pads_are_joined_atomically(self):
        import pcbnew
        import cec_fr

        board = self._one_pad_board()
        footprint = next(iter(board.GetFootprints()))
        p_net = pcbnew.NETINFO_ITEM(board, "/USB_D_P")
        n_net = pcbnew.NETINFO_ITEM(board, "/USB_D_N")
        board.Add(p_net); board.Add(n_net)
        first = next(iter(footprint.Pads()))
        first.SetNumber("A6"); first.SetNet(p_net)
        first.SetSize(pcbnew.VECTOR2I(int(0.3e6), int(1.15e6)))
        first.SetPosition(pcbnew.VECTOR2I(int(5.0e6), int(2.5e6)))
        layers = pcbnew.LSET(); layers.AddLayer(pcbnew.F_Cu)

        for number, net, x in (("B6", p_net, 6.0),
                               ("B7", n_net, 4.5),
                               ("A7", n_net, 5.5)):
            pad = pcbnew.PAD(footprint)
            pad.SetNumber(number)
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetSize(pcbnew.VECTOR2I(int(0.3e6), int(1.15e6)))
            pad.SetPosition(pcbnew.VECTOR2I(int(x * 1e6), int(2.5e6)))
            pad.SetLayerSet(layers); pad.SetNet(net); footprint.Add(pad)

        result = cec_fr.synthesize_same_footprint_links(board)

        tracks = [item for item in board.GetTracks()
                  if item.GetClass() == "PCB_TRACK"]
        self.assertEqual((result["pair_groups"], result["pair_linked"]),
                         (1, 2))
        self.assertEqual((result["groups"], result["linked"]), (2, 2))
        self.assertEqual({track.GetNetname() for track in tracks},
                         {"/USB_D_P", "/USB_D_N"})
        self.assertTrue(all(track.IsLocked() for track in tracks))
        again = cec_fr.synthesize_same_footprint_links(board)
        self.assertEqual(again["pair_linked"], 0)
        self.assertEqual(len(list(board.GetTracks())), len(tracks))

    def test_preconnected_pair_member_allows_guarded_missing_member_completion(self):
        import pcbnew
        import cec_fr

        board = self._one_pad_board()
        footprint = next(iter(board.GetFootprints()))
        p_net = pcbnew.NETINFO_ITEM(board, "/USB_D_P")
        n_net = pcbnew.NETINFO_ITEM(board, "/USB_D_N")
        board.Add(p_net); board.Add(n_net)
        first = next(iter(footprint.Pads()))
        first.SetNumber("A6"); first.SetNet(p_net)
        first.SetSize(pcbnew.VECTOR2I_MM(0.3, 1.15))
        first.SetPosition(pcbnew.VECTOR2I_MM(5.0, 2.5))
        layers = pcbnew.LSET(); layers.AddLayer(pcbnew.F_Cu)
        created = {"A6": first}
        for number, net, x in (("B6", p_net, 6.0),
                               ("B7", n_net, 4.5),
                               ("A7", n_net, 5.5)):
            pad = pcbnew.PAD(footprint)
            pad.SetNumber(number)
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetSize(pcbnew.VECTOR2I_MM(0.3, 1.15))
            pad.SetPosition(pcbnew.VECTOR2I_MM(x, 2.5))
            pad.SetLayerSet(layers); pad.SetNet(net); footprint.Add(pad)
            created[number] = pad

        # Model a precision route that already joined the N duplicates around
        # one side of the row.  P remains genuinely open.
        n_points = [(4.5, 2.5), (4.5, 1.0),
                    (5.5, 1.0), (5.5, 2.5)]
        for a, b in zip(n_points, n_points[1:]):
            track = pcbnew.PCB_TRACK(board)
            track.SetStart(pcbnew.VECTOR2I_MM(*a))
            track.SetEnd(pcbnew.VECTOR2I_MM(*b))
            track.SetWidth(pcbnew.FromMM(0.2))
            track.SetLayer(pcbnew.F_Cu); track.SetNet(n_net)
            track.SetLocked(True); board.Add(track)

        result = cec_fr.synthesize_same_footprint_links(board)

        self.assertEqual(result["pair_refused"], 0, result)
        self.assertEqual(result["pair_linked"], 1, result)
        completion = next(row for row in result["detail"]
                          if row.get("asymmetric_completion"))
        self.assertEqual(completion["net"], "/USB_D_P")
        self.assertEqual(completion["preconnected_mate"], "/USB_D_N")
        board.BuildConnectivity()
        connectivity = board.GetConnectivity()
        connected = connectivity.GetConnectedItems(created["A6"])
        self.assertTrue(any(item.GetClass() == "PAD"
                            and item.GetNumber() == "B6"
                            for item in connected))

    def test_parallel_duplicate_pair_rows_are_joined_atomically(self):
        import pcbnew
        import cec_fr

        board = self._one_pad_board()
        footprint = next(iter(board.GetFootprints()))
        p_net = pcbnew.NETINFO_ITEM(board, "/USB_D_P")
        n_net = pcbnew.NETINFO_ITEM(board, "/USB_D_N")
        board.Add(p_net); board.Add(n_net)
        first = next(iter(footprint.Pads()))
        first.SetNumber("1"); first.SetNet(p_net)
        first.SetSize(pcbnew.VECTOR2I(int(1.0e6), int(0.5e6)))
        first.SetPosition(pcbnew.VECTOR2I(int(5.0e6), int(2.0e6)))
        layers = pcbnew.LSET(); layers.AddLayer(pcbnew.F_Cu)
        for number, net, x, y in (("6", p_net, 7.0, 2.0),
                                  ("3", n_net, 5.0, 3.5),
                                  ("4", n_net, 7.0, 3.5)):
            pad = pcbnew.PAD(footprint)
            pad.SetNumber(number)
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetSize(pcbnew.VECTOR2I(int(1.0e6), int(0.5e6)))
            pad.SetPosition(pcbnew.VECTOR2I(int(x * 1e6), int(y * 1e6)))
            pad.SetLayerSet(layers); pad.SetNet(net); footprint.Add(pad)

        result = cec_fr.synthesize_same_footprint_links(board)

        tracks = [item for item in board.GetTracks()
                  if item.GetClass() == "PCB_TRACK"]
        self.assertEqual((result["pair_groups"], result["pair_linked"]),
                         (1, 2))
        self.assertEqual(len(tracks), 2)
        self.assertEqual({track.GetNetname() for track in tracks},
                         {"/USB_D_P", "/USB_D_N"})

    def test_redundant_dangling_pickup_is_pruned_after_local_cluster_link(self):
        import pcbnew
        import cec_fr

        b = self._one_pad_board()
        net = b.GetNetInfo().GetNetItem("+5VSB")
        fp = next(iter(b.GetFootprints()))
        second = pcbnew.PAD(fp)
        second.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        second.SetShape(pcbnew.PAD_SHAPE_RECT)
        second.SetSize(pcbnew.VECTOR2I(int(1e6), int(1e6)))
        second.SetPosition(pcbnew.VECTOR2I(int(7e6), int(2.5e6)))
        layers = pcbnew.LSET(); layers.AddLayer(pcbnew.F_Cu)
        second.SetLayerSet(layers); second.SetNet(net); fp.Add(second)

        def add_track(start, end):
            track = pcbnew.PCB_TRACK(b)
            track.SetStart(pcbnew.VECTOR2I(*(int(v * 1e6) for v in start)))
            track.SetEnd(pcbnew.VECTOR2I(*(int(v * 1e6) for v in end)))
            track.SetWidth(int(0.3e6)); track.SetLayer(pcbnew.F_Cu)
            track.SetNet(net); track.SetLocked(True); b.Add(track)
            return track

        def add_via(at):
            via = pcbnew.PCB_VIA(b)
            via.SetPosition(pcbnew.VECTOR2I(*(int(v * 1e6) for v in at)))
            via.SetWidth(int(0.6e6)); via.SetDrill(int(0.3e6))
            via.SetNet(net); b.Add(via)
            return via

        # The later local-link pass joins both surface pads.  Its bend touches
        # the annulus of the right pickup without terminating at the barrel
        # centre, reproducing the C14/U6 Wave-48 topology.  Only the left
        # pickup lands in the shaped In2 rail; the right one is redundant.
        add_track((5.0, 2.5), (6.7, 3.3))
        add_track((6.7, 3.3), (7.0, 2.5))
        valid_stub = add_track((5.0, 2.5), (5.0, 3.3))
        valid_via = add_via((5.0, 3.3))
        dead_stub = add_track((7.0, 2.5), (7.0, 3.3))
        dead_via = add_via((7.0, 3.3))
        zone = pcbnew.ZONE(b); zone.SetNet(net); zone.SetLayer(pcbnew.In2_Cu)
        outline = zone.Outline(); outline.NewOutline()
        for x, y in ((4.0, 3.0), (6.0, 3.0), (6.0, 4.0), (4.0, 4.0)):
            outline.Append(pcbnew.VECTOR2I(int(x * 1e6), int(y * 1e6)))
        b.Add(zone); pcbnew.ZONE_FILLER(b).Fill(b.Zones())
        # The normalizer may re-key the fine pad-to-via stub while retaining
        # its generated lock state; the original pickup via UUID remains the
        # provenance root.
        pickup_ids = {item.m_Uuid.AsString()
                      for item in (valid_stub, valid_via, dead_via)}
        valid_stub_id = valid_stub.m_Uuid.AsString()
        valid_via_id = valid_via.m_Uuid.AsString()
        dead_stub_id = dead_stub.m_Uuid.AsString()
        dead_via_id = dead_via.m_Uuid.AsString()

        result = cec_fr.prune_redundant_dangling_pickups(
            b, pickup_ids, discover_nets=("+5VSB",))

        remaining = {item.m_Uuid.AsString() for item in b.GetTracks()}
        self.assertEqual((result["vias"], result["stubs"]), (1, 1))
        self.assertIn(valid_via_id, remaining)
        self.assertIn(valid_stub_id, remaining)
        self.assertNotIn(dead_via_id, remaining)
        self.assertNotIn(dead_stub_id, remaining)

    def test_just_generated_pofv_is_removed_when_final_fill_does_not_land(self):
        import pcbnew
        import cec_fr

        board = self._one_pad_board()
        board.SetCopperLayerCount(6)
        props = board.GetProperties()
        props["CEC_FAB_PROFILE"] = "jlcpcb_6l_pofv_signal"
        board.SetProperties(props)
        pad = next(iter(next(iter(board.GetFootprints())).Pads()))
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(pad.GetPosition())
        via.SetWidth(pcbnew.FromMM(0.35))
        via.SetDrill(pcbnew.FromMM(0.25))
        via.SetNet(pad.GetNet())
        board.Add(via)
        via_id = via.m_Uuid.AsString()
        footprint = next(iter(board.GetFootprints()))
        other = pcbnew.PAD(footprint)
        other.SetPadName("2")
        other.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        other.SetShape(pcbnew.PAD_SHAPE_RECT)
        other.SetSize(pcbnew.VECTOR2I_MM(0.4, 0.4))
        other.SetPosition(pcbnew.VECTOR2I(
            pad.GetPosition().x + pcbnew.FromMM(0.5),
            pad.GetPosition().y))
        layers = pcbnew.LSET(); layers.AddLayer(pcbnew.F_Cu)
        other.SetLayerSet(layers); other.SetNet(pad.GetNet())
        footprint.Add(other)
        surface_link = pcbnew.PCB_TRACK(board)
        surface_link.SetStart(pad.GetPosition())
        surface_link.SetEnd(other.GetPosition())
        surface_link.SetWidth(pcbnew.FromMM(0.2))
        surface_link.SetLayer(pcbnew.F_Cu)
        surface_link.SetNet(pad.GetNet())
        board.Add(surface_link)
        surface_link_id = surface_link.m_Uuid.AsString()

        # Bootstrap pickups are created before the fresh over-under zones in a
        # separate pcbnew process, so their UUIDs cannot be carried into the
        # final-fill pruner. The explicit rail discovery scope is the ownership
        # proof for that materialization-only case.
        result = cec_fr.prune_redundant_dangling_pickups(
            board, set(), discover_pofv_nets=("+5VSB",))

        remaining = {item.m_Uuid.AsString() for item in board.GetTracks()}
        self.assertEqual((result["vias"], result["stubs"],
                          result["unlanded_pofv"]), (1, 0, 1))
        self.assertNotIn(via_id, remaining)
        self.assertIn(surface_link_id, remaining)
        self.assertEqual(result["detail"][0]["replacement"],
                         "none-unlanded-pofv")

    def test_file_cleanup_reconciles_pofv_after_zone_reaper(self):
        import pcbnew
        import cec_fr

        board = self._one_pad_board()
        board.SetCopperLayerCount(6)
        props = board.GetProperties()
        props["CEC_FAB_PROFILE"] = "jlcpcb_6l_pofv_signal"
        board.SetProperties(props)
        pad = next(iter(next(iter(board.GetFootprints())).Pads()))
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(pad.GetPosition())
        via.SetWidth(pcbnew.FromMM(0.35))
        via.SetDrill(pcbnew.FromMM(0.25))
        via.SetNet(pad.GetNet())
        via.SetLocked(True)
        board.Add(via)
        via_id = via.m_Uuid.AsString()

        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "post-reaper.kicad_pcb")
            pcbnew.SaveBoard(path, board)
            result = cec_fr.prune_post_cleanup_power_pickups(
                path, ("+5VSB",))
            saved = pcbnew.LoadBoard(path)
            remaining = {item.m_Uuid.AsString()
                         for item in saved.GetTracks()}

        self.assertEqual((result["vias"], result["stubs"],
                          result["unlanded_pofv"]), (1, 0, 1))
        self.assertNotIn(via_id, remaining)
        self.assertEqual(result["detail"][0]["replacement"],
                         "none-unlanded-pofv")

    def test_generated_zone_and_locked_via_cannot_keep_each_other_alive(self):
        import pcbnew
        import cec_fr

        board = pcbnew.BOARD()
        board.SetCopperLayerCount(4)
        net = pcbnew.NETINFO_ITEM(board, "+RAIL")
        board.Add(net)
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(pcbnew.VECTOR2I_MM(5, 5))
        via.SetWidth(pcbnew.FromMM(0.9))
        via.SetDrill(pcbnew.FromMM(0.5))
        via.SetNet(net)
        via.SetLocked(True)
        board.Add(via)
        zone = pcbnew.ZONE(board)
        zone.SetNet(net)
        zone.SetLayer(pcbnew.F_Cu)
        zone.SetZoneName("pourfirst:+RAIL:dead")
        outline = zone.Outline(); outline.NewOutline()
        for x, y in ((4, 4), (6, 4), (6, 6), (4, 6)):
            outline.Append(pcbnew.VECTOR2I_MM(x, y))
        board.Add(zone)
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())

        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "dead-pair.kicad_pcb")
            pcbnew.SaveBoard(path, board)
            report = cec_fr.settle_generated_power_artifact(
                path, ("+RAIL",))
            saved = pcbnew.LoadBoard(path)

        self.assertTrue(report["converged"])
        self.assertEqual(len(saved.GetTracks()), 0)
        self.assertEqual(len(saved.Zones()), 0)

    def test_power_settlement_retries_empty_worker_report_from_clean_input(self):
        import cec_fr

        calls = []
        with tempfile.TemporaryDirectory() as td:
            board_path = os.path.join(td, "candidate.kicad_pcb")
            with open(board_path, "w", encoding="utf-8") as sink:
                sink.write("ORIGINAL")

            def worker(command, **_kwargs):
                phase = command[2]
                calls.append(phase)
                with open(board_path, encoding="utf-8") as source:
                    self.assertEqual(source.read(), "ORIGINAL")
                report_path = command[command.index("--report") + 1]
                if calls == ["via"]:
                    with open(board_path, "w", encoding="utf-8") as sink:
                        sink.write("PARTIAL")
                    return mock.Mock(returncode=0, stdout="", stderr="")
                value = ({"vias": 0, "detail": []}
                         if phase == "via" else {"removed": 0})
                with open(report_path, "w", encoding="utf-8") as sink:
                    json.dump(value, sink)
                return mock.Mock(returncode=0, stdout="", stderr="")

            with mock.patch.object(
                    cec_fr.subprocess, "run", side_effect=worker):
                report = cec_fr.settle_generated_power_artifact(
                    board_path, ["RAIL"], max_rounds=1)

            with open(board_path, encoding="utf-8") as source:
                self.assertEqual(source.read(), "ORIGINAL")

        self.assertEqual(calls, ["via", "via", "floating", "nowhere"])
        self.assertTrue(report["converged"])

    def test_post_fill_pickup_uses_filled_shape_not_zone_bbox(self):
        import pcbnew
        import cec_fr

        b = self._one_pad_board()
        fp = next(iter(b.GetFootprints()))
        pad = next(iter(fp.Pads()))
        fp.SetPosition(pcbnew.VECTOR2I_MM(8.0, 4.5))
        pad.SetPosition(pcbnew.VECTOR2I_MM(8.0, 4.5))
        net = b.GetNetInfo().GetNetItem("+5VSB")
        zone = pcbnew.ZONE(b)
        zone.SetNet(net)
        zone.SetLayer(pcbnew.In2_Cu)
        outline = zone.Outline()
        outline.NewOutline()
        # L shape: the pad at (8, 4.5) is inside the 0..10 x 0..5 bbox,
        # but outside real copper and beyond the bounded 3 mm pickup reach.
        for x, y in ((0, 0), (10, 0), (10, 1),
                     (1, 1), (1, 5), (0, 5)):
            outline.Append(pcbnew.VECTOR2I_MM(x, y))
        b.Add(zone)
        pcbnew.ZONE_FILLER(b).Fill(b.Zones())
        self.assertTrue(zone.GetBoundingBox().Contains(pad.GetPosition()))
        self.assertFalse(zone.GetFilledPolysList(pcbnew.In2_Cu).Contains(
            pad.GetPosition()))

        result = cec_fr.synthesize_power_pickups(
            b, (), plane_nets=(), filled_zone_nets=("+5VSB",))
        self.assertEqual((result["vias"], result["skipped"]), (0, 1))
        self.assertEqual(result["skipped_detail"][0]["reason"],
                         "no guarded via slot in filled copper")

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

    def test_fiducial_keepout_owns_only_its_assembly_side(self):
        import pcbnew
        import cec_fr

        board = pcbnew.CreateEmptyBoard()
        fiducial = pcbnew.FOOTPRINT(board)
        fiducial.SetReference("FID1")
        fiducial.SetLayer(pcbnew.F_Cu)
        fiducial.SetPosition(pcbnew.VECTOR2I_MM(10.0, 10.0))
        pad = pcbnew.PAD(fiducial)
        pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
        pad.SetSize(pcbnew.VECTOR2I_MM(1.0, 1.0))
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        layers = pcbnew.LSET()
        layers.AddLayer(pcbnew.F_Cu)
        layers.AddLayer(pcbnew.F_Mask)
        pad.SetLayerSet(layers)
        pad.SetPosition(fiducial.GetPosition())
        fiducial.Add(pad)
        board.Add(fiducial)

        keepouts = cec_fr.fiducial_keepouts("", board=board)

        self.assertEqual(len(keepouts), 1)
        keepout = keepouts[0]
        self.assertEqual(keepout["name"], "assembly_fiducial_FID1")
        self.assertEqual(keepout["layers"], ("F.Cu",))
        self.assertFalse(keepout["allow_vias"])
        self.assertTrue(keepout["block_fills"])
        self.assertLess(keepout["x0"], 10.0)
        self.assertGreater(keepout["x1"], 10.0)

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


class TestLaidPipelinePourKeepouts(unittest.TestCase):
    def test_post_cleanup_scope_includes_pre_materialized_rail_zones(self):
        import cec_fr

        class Zone:
            def __init__(self, name, net, rule=False):
                self.name, self.net, self.rule = name, net, rule
            def GetIsRuleArea(self): return self.rule
            def GetZoneName(self): return self.name
            def GetNetname(self): return self.net
        class Board:
            def Zones(self):
                return [Zone("overunder:/RAIL_A", "/RAIL_A"),
                        Zone("manifold:J1:/RAIL_B", "/RAIL_B"),
                        Zone("hand-authored-signal", "/SIG"),
                        Zone("overunder:/RULE", "/RULE", rule=True)]

        self.assertEqual(
            cec_fr._pipeline_power_pickup_nets(
                Board(), ({"net": "/RAIL_C"},)),
            {"GND", "/RAIL_A", "/RAIL_B", "/RAIL_C"})

    def test_current_hub_candidate_contains_no_pre_topology_pours(self):
        import cec_fr

        board = os.path.join(
            ROOT, "beta", "hub-standard-rev2", "candidate",
            "hub-standard-rev2-candidate.kicad_pcb")
        hints = cec_fr.laid_pipeline_pour_keepouts(board)
        self.assertEqual(
            hints, [],
            "the rev3 J_PWR retirement changed connectivity, so the reference "
            "must not carry pre-topology copper into a new route wave")

    def test_baked_keepout_preserves_nonrectangular_outline(self):
        import pcbnew
        import cec_fr

        polygon = [(1.0, 1.0), (6.0, 1.0), (6.0, 2.0),
                   (2.0, 2.0), (2.0, 6.0), (1.0, 6.0)]
        with tempfile.TemporaryDirectory() as directory:
            source = os.path.join(directory, "source.kicad_pcb")
            output = os.path.join(directory, "hinted.kicad_pcb")
            pcbnew.SaveBoard(source, pcbnew.BOARD())
            cec_fr.bake_hints(
                source, output, copy_pro=False,
                keepouts=[{"name": "exact-L", "polygon": polygon,
                           "layers": ("F.Cu",)}])
            board = pcbnew.LoadBoard(output)
            zones = list(board.Zones())
            self.assertEqual(len(zones), 1)
            contour = zones[0].Outline().Outline(0)
            got = [(contour.CPoint(k).x / 1e6,
                    contour.CPoint(k).y / 1e6)
                   for k in range(contour.PointCount())]
            self.assertEqual(got, polygon)

    def test_baked_keepout_preserves_interior_route_window(self):
        import pcbnew
        import cec_fr

        polygon = [(1.0, 1.0), (8.0, 1.0), (8.0, 8.0), (1.0, 8.0)]
        hole = [(3.0, 3.0), (3.0, 6.0), (6.0, 6.0), (6.0, 3.0)]
        with tempfile.TemporaryDirectory() as directory:
            source = os.path.join(directory, "source.kicad_pcb")
            output = os.path.join(directory, "hinted.kicad_pcb")
            pcbnew.SaveBoard(source, pcbnew.BOARD())
            cec_fr.bake_hints(
                source, output, copy_pro=False,
                keepouts=[{"name": "exact-donut", "polygon": polygon,
                           "holes": [hole], "layers": ("F.Cu",)}])
            outline = list(pcbnew.LoadBoard(output).Zones())[0].Outline()
            self.assertEqual(outline.HoleCount(0), 1)
            contour = outline.Hole(0, 0)
            got = [(contour.CPoint(k).x / 1e6,
                    contour.CPoint(k).y / 1e6)
                   for k in range(contour.PointCount())]
            self.assertEqual(got, hole)

    def test_laid_pour_hint_round_trips_interior_route_window(self):
        import pcbnew
        import cec_fr

        mm = lambda value: int(value * 1e6)
        with tempfile.TemporaryDirectory() as directory:
            source = os.path.join(directory, "laid.kicad_pcb")
            board = pcbnew.BOARD()
            zone = pcbnew.ZONE(board)
            zone.SetLayer(pcbnew.F_Cu)
            zone.SetZoneName("overunder:test")
            outline = zone.Outline()
            oi = outline.NewOutline()
            for x, y in ((1, 1), (8, 1), (8, 8), (1, 8)):
                outline.Append(mm(x), mm(y))
            hi = outline.NewHole(oi)
            for x, y in ((3, 3), (3, 6), (6, 6), (6, 3)):
                outline.Append(mm(x), mm(y), oi, hi)
            board.Add(zone)
            pcbnew.SaveBoard(source, board)

            hints = cec_fr.laid_pipeline_pour_keepouts(source)
            self.assertEqual(len(hints), 1)
            self.assertEqual(len(hints[0]["holes"]), 1)
            self.assertEqual(hints[0]["holes"][0],
                             [(3.0, 3.0), (3.0, 6.0),
                              (6.0, 6.0), (6.0, 3.0)])

    def test_hub_edge_hints_reserve_reverse_led_apertures(self):
        import pcbnew
        import cec_fr

        board = os.path.join(
            ROOT, "beta", "hub-standard-rev2", "candidate",
            "hub-standard-rev2-candidate.kicad_pcb")
        hints = cec_fr.edge_keepout(board)
        cuts = [h for h in hints if h["name"].startswith("edge_cutout_DL")]
        self.assertEqual(len(cuts), 6)
        self.assertTrue(all(c["allow_vias"] is False for c in cuts))
        board_obj = pcbnew.LoadBoard(board)
        dl1 = next(fp for fp in board_obj.GetFootprints()
                   if fp.GetReference() == "DL1")
        edge_item = next(item for item in dl1.GraphicalItems()
                         if item.GetLayer() == pcbnew.Edge_Cuts)
        bb = edge_item.GetBoundingBox()
        dl1_hint = next(c for c in cuts
                        if c["name"].startswith("edge_cutout_DL1_"))
        self.assertEqual(
            (dl1_hint["x0"], dl1_hint["y0"], dl1_hint["x1"], dl1_hint["y1"]),
            (round(bb.GetLeft() / 1e6 - 0.5, 2),
             round(bb.GetTop() / 1e6 - 0.5, 2),
             round(bb.GetRight() / 1e6 + 0.5, 2),
             round(bb.GetBottom() / 1e6 + 0.5, 2)))

    def test_hub_u2_pickup_overlap_is_blocked_by_guard(self):
        import pcbnew
        import cec_fab_profile as fab
        import cec_fr

        path = os.path.join(
            ROOT, "beta", "hub-standard-rev2", "candidate",
            "hub-standard-rev2-candidate.kicad_pcb")
        board = pcbnew.LoadBoard(path)
        u2 = next(fp for fp in board.GetFootprints()
                  if fp.GetReference() == "U2")
        pad = next(p for p in u2.Pads() if p.GetPadName() == "3")
        # Wave 13/15 reproduction: the adjacent pickup chose the 0.55 mm east
        # seat. Its 0.8 mm land clips the 1.95 x 0.60 oval.
        at = pcbnew.VECTOR2I(pad.GetPosition().x + int(0.55e6),
                            pad.GetPosition().y)
        blocking, _allowed = fab.via_at_pad_conflicts(
            board, at, int(0.8e6), int(0.4e6), pad.GetNetCode())
        self.assertIsNotNone(blocking)
        self.assertFalse(cec_fr._via_spot_clear(
            board, at, int(0.8e6), int(0.25e6), {pad.GetNetCode()},
            drill_nm=int(0.4e6), net_code=pad.GetNetCode()))


class TestRouteArtifactContracts(unittest.TestCase):
    @staticmethod
    def _export_stub(_board_path, dsn_path, **_kwargs):
        with open(dsn_path, "w", encoding="utf-8") as handle:
            handle.write("(pcb board)\n")
        return dsn_path

    def _hub_board(self):
        import pcbnew

        return pcbnew.LoadBoard(os.path.join(
            ROOT, "beta", "hub-standard-rev2", "candidate",
            "hub-standard-rev2-candidate.kicad_pcb"))

    def test_route_once_backstops_fiducial_guard_for_custom_planners(self):
        import cec_fr

        source = os.path.join(
            ROOT, "beta", "hub-standard-rev2", "candidate",
            "hub-standard-rev2-candidate.kicad_pcb")
        with tempfile.TemporaryDirectory() as work, \
                mock.patch.object(cec_fr, "ensure_jar", return_value="fake.jar"), \
                mock.patch.object(cec_fr, "smd_via_keepouts", return_value=[]), \
                mock.patch.object(cec_fr, "decorative_copper_keepouts", return_value=[]), \
                mock.patch.object(cec_fr, "bake_hints") as bake, \
                mock.patch.object(cec_fr, "export_dsn",
                                  side_effect=self._export_stub), \
                mock.patch.object(cec_fr, "run_freerouting"), \
                mock.patch.object(cec_fr, "import_ses"):
            candidate = cec_fr.route_once(
                source, os.path.join(work, "out.kicad_pcb"),
                hints=(), workdir=work)

        self.assertTrue(candidate.ok)
        names = {str(hint.get("name", ""))
                 for hint in bake.call_args.kwargs["keepouts"]}
        self.assertTrue(any(name.startswith("assembly_fiducial_")
                            for name in names))

    def test_route_once_excludes_and_propagates_completed_net_contract(self):
        import cec_fr
        import cec_fr02

        source = os.path.join(
            ROOT, "beta", "hub-standard-rev2", "candidate",
            "hub-standard-rev2-candidate.kicad_pcb")
        with tempfile.TemporaryDirectory() as work, \
                mock.patch.object(cec_fr, "ensure_jar", return_value="fake.jar"), \
                mock.patch.object(cec_fr, "smd_via_keepouts", return_value=[]), \
                mock.patch.object(cec_fr, "decorative_copper_keepouts", return_value=[]), \
                mock.patch.object(cec_fr, "locked_copper_keepouts", return_value=[]), \
                mock.patch.object(cec_fr, "partial_locked_keepouts", return_value=[]), \
                mock.patch.object(cec_fr, "owned_locked_nets", return_value=set()), \
                mock.patch.object(cec_fr, "bake_hints"), \
                mock.patch.object(cec_fr, "export_dsn",
                                  side_effect=self._export_stub), \
                mock.patch.object(cec_fr, "run_freerouting"), \
                mock.patch.object(cec_fr02, "force_protect_in_dsn") as protect, \
                mock.patch.object(cec_fr02, "exclude_net_pins_in_dsn",
                                  return_value=1) as exclude, \
                mock.patch.object(cec_fr, "import_ses") as import_ses:
            candidate = cec_fr.route_once(
                source, os.path.join(work, "out.kicad_pcb"),
                completed_nets={"GND"}, workdir=work)

        self.assertTrue(candidate.ok)
        protect.assert_called_once_with(
            os.path.join(work, "board.dsn"), ["GND"])
        exclude.assert_called_once_with(
            os.path.join(work, "board.dsn"), ["GND"])
        self.assertEqual(import_ses.call_args.kwargs["completed_nets"],
                         {"GND"})

    def test_route_once_can_ablate_geometry_keepouts_without_dropping_protect(self):
        import cec_fr
        import cec_fr02

        source = os.path.join(
            ROOT, "beta", "hub-standard-rev2", "candidate",
            "hub-standard-rev2-candidate.kicad_pcb")
        with tempfile.TemporaryDirectory() as work, \
                mock.patch.dict(os.environ,
                                {"CEC_LOCKED_COPPER_KEEPOUTS": "0"}), \
                mock.patch.object(cec_fr, "ensure_jar", return_value="fake.jar"), \
                mock.patch.object(cec_fr, "smd_via_keepouts", return_value=[]), \
                mock.patch.object(cec_fr, "decorative_copper_keepouts", return_value=[]), \
                mock.patch.object(cec_fr, "locked_copper_keepouts") as locked, \
                mock.patch.object(cec_fr, "partial_locked_keepouts") as partial, \
                mock.patch.object(cec_fr, "owned_locked_nets",
                                  return_value={"GND"}), \
                mock.patch.object(cec_fr, "bake_hints"), \
                mock.patch.object(cec_fr, "export_dsn",
                                  side_effect=self._export_stub), \
                mock.patch.object(cec_fr, "run_freerouting"), \
                mock.patch.object(cec_fr02, "force_protect_in_dsn") as protect, \
                mock.patch.object(cec_fr02, "exclude_net_pins_in_dsn",
                                  return_value=1), \
                mock.patch.object(cec_fr, "import_ses"):
            candidate = cec_fr.route_once(
                source, os.path.join(work, "out.kicad_pcb"),
                completed_nets={"GND"}, workdir=work)

        self.assertTrue(candidate.ok)
        self.assertFalse(candidate.params["locked_copper_keepouts"])
        locked.assert_not_called()
        partial.assert_not_called()
        protect.assert_called_once_with(
            os.path.join(work, "board.dsn"), ["GND"])

    def test_reverse_led_aperture_waiver_is_pad_only_and_geometry_bounded(self):
        import cec_score

        board = self._hub_board()
        edge = {"description": "Rectangle of DL1 on Edge.Cuts"}
        pad = {"description": "Pad 1 [Net-(DL1-DOUT)] of DL1 on F.Cu"}
        track = {"description": "Track [Net-(DL1-DOUT)] on F.Cu, length 1.0 mm"}
        qualified = {
            "type": "copper_edge_clearance",
            "description": "Board edge clearance violation (actual 0.3542 mm)",
            "items": [edge, pad],
        }
        too_close = {
            "type": "copper_edge_clearance",
            "description": "Board edge clearance violation (actual 0.2000 mm)",
            "items": [edge, pad],
        }
        routed = {
            "type": "copper_edge_clearance",
            "description": "Board edge clearance violation (actual 0.3542 mm)",
            "items": [edge, track],
        }
        kept = cec_score._drop_impossible_pad_artifacts(
            [qualified, too_close, routed], board)
        self.assertEqual(kept, [too_close, routed])

    def test_usbc_vendor_hole_waiver_is_land_and_geometry_bounded(self):
        import cec_score

        board = self._hub_board()
        board.FindFootprintByReference("J_USB").SetReference("J99")
        npth = {"description": "NPTH pad of J99"}
        a4 = {"description": "Pad A4 [/USB_VBUS] of J99 on F.Cu"}
        a5 = {"description": "Pad A5 [/USB_CC1] of J99 on F.Cu"}
        qualified = {
            "type": "hole_clearance",
            "description": "Hole clearance violation (actual 0.2005 mm)",
            "items": [a4, npth],
        }
        too_close = {
            "type": "hole_clearance",
            "description": "Hole clearance violation (actual 0.1400 mm)",
            "items": [a4, npth],
        }
        wrong_land = {
            "type": "hole_clearance",
            "description": "Hole clearance violation (actual 0.2005 mm)",
            "items": [a5, npth],
        }
        routed = {
            "type": "hole_clearance",
            "description": "Hole clearance violation (actual 0.2005 mm)",
            "items": [{"description": "Track [/USB_VBUS] on F.Cu"}, npth],
        }
        kept = cec_score._drop_impossible_pad_artifacts(
            [qualified, too_close, wrong_land, routed], board)
        self.assertEqual(kept, [too_close, wrong_land, routed])

    def test_sidecar_copy_rebinds_project_and_keeps_rules(self):
        import cec_fr

        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "source.kicad_pcb")
            dst = os.path.join(tmp, "renamed.kicad_pcb")
            open(src, "w", encoding="utf-8").close()
            with open(os.path.splitext(src)[0] + ".kicad_pro", "w", encoding="utf-8") as fh:
                json.dump({"meta": {"filename": "stale.kicad_pro", "version": 3}}, fh)
            with open(os.path.splitext(src)[0] + ".kicad_dru", "w", encoding="utf-8") as fh:
                fh.write("(version 1)\n")
            with open(os.path.splitext(src)[0] + ".pourplan.json", "w",
                      encoding="utf-8") as fh:
                json.dump({"board_sig": "owned", "specs": []}, fh)
            with open(os.path.splitext(src)[0] + ".railreport.json", "w",
                      encoding="utf-8") as fh:
                json.dump({"laid": 2}, fh)
            with open(os.path.splitext(src)[0] + ".pourfirst-state.json", "w",
                      encoding="utf-8") as fh:
                json.dump({"placement_scope": "complete",
                           "frozen_nets": ["+VIN"]}, fh)
            cec_fr.copy_project_sidecars(src, dst)
            with open(os.path.splitext(dst)[0] + ".kicad_pro", encoding="utf-8") as fh:
                pro = json.load(fh)
            self.assertEqual(pro["meta"]["filename"], "renamed.kicad_pro")
            self.assertTrue(os.path.isfile(os.path.splitext(dst)[0] + ".kicad_dru"))
            with open(os.path.splitext(dst)[0] + ".pourplan.json",
                      encoding="utf-8") as fh:
                self.assertEqual(json.load(fh)["board_sig"], "owned")
            with open(os.path.splitext(dst)[0] + ".railreport.json",
                      encoding="utf-8") as fh:
                self.assertEqual(json.load(fh)["laid"], 2)
            with open(os.path.splitext(dst)[0] + ".pourfirst-state.json",
                      encoding="utf-8") as fh:
                self.assertEqual(
                    json.load(fh)["frozen_nets"], ["+VIN"])



if __name__ == "__main__":
    unittest.main()
