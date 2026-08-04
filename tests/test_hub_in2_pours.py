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
            "/MAIN_5V_RAW", "/+5V_HOLD",
            "/VCC_P1", "/VCC_P2", "/VCC_P3", "/VCC_P4",
        })
        for a in asks:
            self.assertEqual(tuple(a["layers"]), ("In3.Cu",),
                             f"pour ask {a['net']} must live on the approved "
                             "six-layer In3 power layer")
            self.assertFalse(a.get("evac", True),
                             "hub asks stay post-route additive (no eviction)")


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
        nc = board.GetNetcodeFromNetname("/MAIN_5V_RAW")
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

    def test_pickup_uses_power_netclass_geometry_before_clearance(self):
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
        self.assertEqual(via.GetWidth(via.TopLayer()), int(0.8e6))
        self.assertEqual(via.GetDrillValue(), int(0.4e6))

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
        stub = next(t for t in b.GetTracks()
                    if t.GetClass() == "PCB_TRACK")
        via = next(t for t in b.GetTracks()
                   if t.GetClass() == "PCB_VIA")
        self.assertEqual((result["vias"], result["stubs"]), (1, 1))
        self.assertEqual(stub.GetWidth(), int(0.2e6))
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

        # The later local-link pass joins both surface pads.  Only the left
        # pickup lands in the shaped In2 rail; the right one is redundant.
        add_track((5.0, 2.5), (7.0, 2.5))
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

    def test_post_fill_pickup_uses_filled_shape_not_zone_bbox(self):
        import pcbnew
        import cec_fr

        b = self._one_pad_board()
        net = b.GetNetInfo().GetNetItem("+5VSB")
        zone = pcbnew.ZONE(b)
        zone.SetNet(net)
        zone.SetLayer(pcbnew.In2_Cu)
        outline = zone.Outline()
        outline.NewOutline()
        # L shape: the pad at (5, 2.5) is inside the 0..10 x 0..5 bbox,
        # but outside real copper above the 1 mm bottom bar.
        for x, y in ((0, 0), (10, 0), (10, 1),
                     (1, 1), (1, 5), (0, 5)):
            outline.Append(pcbnew.VECTOR2I_MM(x, y))
        b.Add(zone)
        pcbnew.ZONE_FILLER(b).Fill(b.Zones())
        pad = next(iter(next(iter(b.GetFootprints())).Pads()))
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
    def test_hub_reserves_generated_signal_layer_pours_only(self):
        import cec_fr

        board = os.path.join(
            ROOT, "beta", "hub-standard-rev2", "candidate",
            "hub-standard-rev2-candidate.kicad_pcb")
        hints = cec_fr.laid_pipeline_pour_keepouts(board)
        self.assertTrue(hints)
        self.assertTrue(all(h["name"].startswith("laid-pour:") for h in hints))
        self.assertTrue(all(tuple(h["layers"]) != ("PWR",) for h in hints))
        self.assertTrue(all(len(h.get("polygon") or ()) >= 3 for h in hints))

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
    def _hub_board(self):
        import pcbnew

        return pcbnew.LoadBoard(os.path.join(
            ROOT, "beta", "hub-standard-rev2", "candidate",
            "hub-standard-rev2-candidate.kicad_pcb"))

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
        npth = {"description": "NPTH pad of J_USB"}
        a4 = {"description": "Pad A4 [/USB_VBUS] of J_USB on F.Cu"}
        a5 = {"description": "Pad A5 [/USB_CC1] of J_USB on F.Cu"}
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
            cec_fr.copy_project_sidecars(src, dst)
            with open(os.path.splitext(dst)[0] + ".kicad_pro", encoding="utf-8") as fh:
                pro = json.load(fh)
            self.assertEqual(pro["meta"]["filename"], "renamed.kicad_pro")
            self.assertTrue(os.path.isfile(os.path.splitext(dst)[0] + ".kicad_dru"))


if __name__ == "__main__":
    unittest.main()
