#!/usr/bin/env python3
"""Transactional publication tests for fabrication cleanup."""

import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import cec_fab_repair as repair

try:
    import pcbnew
except ImportError as exc:  # pragma: no cover
    raise unittest.SkipTest("pcbnew required") from exc


class FabRepairAdmissionTest(unittest.TestCase):
    def test_only_all_sliver_generated_orthofill_is_removable(self):
        board = pcbnew.CreateEmptyBoard()
        net = pcbnew.NETINFO_ITEM(board, "/SIG")
        board.Add(net)
        zone = pcbnew.ZONE(board)
        layers = pcbnew.LSET()
        layers.AddLayer(board.GetLayerID("F.Cu"))
        zone.SetLayerSet(layers)
        zone.SetNet(net)
        zone.SetZoneName("orthofill:/SIG:F.Cu:1")
        zone.SetMinThickness(pcbnew.FromMM(0.01))
        if hasattr(pcbnew, "ISLAND_REMOVAL_MODE_NEVER"):
            zone.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_NEVER)
        outline = zone.Outline()
        outline.NewOutline()
        for x, y in ((1, 1), (3, 1), (3, 1.04), (1, 1.04)):
            outline.Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
        board.Add(zone)

        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "board.kicad_pcb")
            pcbnew.SaveBoard(path, board)
            loaded = pcbnew.LoadBoard(path)
            pcbnew.ZONE_FILLER(loaded).Fill(loaded.Zones())
            candidates = repair.sliver_only_orthofill_zones(
                loaded, sliver_mm=0.10)
            self.assertEqual(
                [row.GetZoneName() for row in candidates],
                ["orthofill:/SIG:F.Cu:1"])
            candidates[0].SetZoneName("pourplan:/SIG")
            self.assertEqual(
                repair.sliver_only_orthofill_zones(
                    loaded, sliver_mm=0.10), [])

    def test_backtrack_collapse_preserves_explicit_interior_junction(self):
        board = pcbnew.CreateEmptyBoard()
        net = pcbnew.NETINFO_ITEM(board, "/SIG")
        board.Add(net)

        def track(start, end):
            item = pcbnew.PCB_TRACK(board)
            item.SetStart(pcbnew.VECTOR2I_MM(*start))
            item.SetEnd(pcbnew.VECTOR2I_MM(*end))
            item.SetWidth(pcbnew.FromMM(0.20))
            item.SetLayer(board.GetLayerID("F.Cu"))
            item.SetNet(net)
            board.Add(item)
            return item

        short = track((1, 1), (3, 1))
        long = track((1, 1), (5, 1))
        branch = track((3, 1), (3, 3))

        self.assertEqual(repair.repair_backtracks(board), 1)
        self.assertEqual(long.GetStart(), short.GetEnd())
        self.assertEqual(branch.GetStart(), short.GetEnd())
        self.assertEqual(len(list(board.GetTracks())), 3)

    def test_wide_short_trunk_safely_absorbs_narrow_overlap(self):
        board = pcbnew.CreateEmptyBoard()
        net = pcbnew.NETINFO_ITEM(board, "/SIG")
        board.Add(net)

        def track(end, width):
            item = pcbnew.PCB_TRACK(board)
            item.SetStart(pcbnew.VECTOR2I_MM(1, 1))
            item.SetEnd(pcbnew.VECTOR2I_MM(*end))
            item.SetWidth(pcbnew.FromMM(width))
            item.SetLayer(board.GetLayerID("F.Cu"))
            item.SetNet(net)
            board.Add(item)
            return item

        wide_short = track((3, 1), 0.50)
        narrow_long = track((5, 1), 0.25)

        self.assertEqual(repair.repair_backtracks(board), 1)
        self.assertEqual(narrow_long.GetStart(), wide_short.GetEnd())
        self.assertEqual(narrow_long.GetWidth(), pcbnew.FromMM(0.25))

    def test_narrow_short_segment_cannot_absorb_wide_overlap(self):
        board = pcbnew.CreateEmptyBoard()
        net = pcbnew.NETINFO_ITEM(board, "/SIG")
        board.Add(net)

        def track(end, width):
            item = pcbnew.PCB_TRACK(board)
            item.SetStart(pcbnew.VECTOR2I_MM(1, 1))
            item.SetEnd(pcbnew.VECTOR2I_MM(*end))
            item.SetWidth(pcbnew.FromMM(width))
            item.SetLayer(board.GetLayerID("F.Cu"))
            item.SetNet(net)
            board.Add(item)
            return item

        narrow_short = track((3, 1), 0.25)
        wide_long = track((5, 1), 0.50)

        self.assertEqual(repair.repair_backtracks(board), 0)
        self.assertEqual(wide_long.GetStart(), narrow_short.GetStart())

    def test_near_collinear_fork_is_not_treated_as_covered_copper(self):
        board = pcbnew.CreateEmptyBoard()
        net = pcbnew.NETINFO_ITEM(board, "/SIG")
        board.Add(net)
        for end in ((5, 1), (5, 1.1)):
            item = pcbnew.PCB_TRACK(board)
            item.SetStart(pcbnew.VECTOR2I_MM(1, 1))
            item.SetEnd(pcbnew.VECTOR2I_MM(*end))
            item.SetWidth(pcbnew.FromMM(0.20))
            item.SetLayer(board.GetLayerID("F.Cu"))
            item.SetNet(net)
            board.Add(item)

        self.assertEqual(repair.repair_backtracks(board), 0)
        self.assertEqual(len(list(board.GetTracks())), 2)

    def test_unanchored_acute_vertex_moves_to_canonical_path(self):
        board = pcbnew.CreateEmptyBoard()
        net = pcbnew.NETINFO_ITEM(board, "/SIG")
        board.Add(net)

        def track(start, end):
            item = pcbnew.PCB_TRACK(board)
            item.SetStart(pcbnew.VECTOR2I_MM(*start))
            item.SetEnd(pcbnew.VECTOR2I_MM(*end))
            item.SetWidth(pcbnew.FromMM(0.20))
            item.SetLayer(board.GetLayerID("F.Cu"))
            item.SetNet(net)
            board.Add(item)
            return item

        first = track((10, 10), (8, 10))
        second = track((10, 10), (7, 13))
        self.assertEqual(repair.repair_acute_vertices(board), 1)
        self.assertEqual(first.GetStart(), second.GetStart())
        self.assertIn(first.GetStart(), (pcbnew.VECTOR2I_MM(7, 11),
                                        pcbnew.VECTOR2I_MM(8, 12)))
        self.assertEqual(first.GetEnd(), pcbnew.VECTOR2I_MM(8, 10))
        self.assertEqual(second.GetEnd(), pcbnew.VECTOR2I_MM(7, 13))

    def test_via_45_degree_hook_is_replaced_by_two_45_degree_bends(self):
        board = pcbnew.CreateEmptyBoard()
        net = pcbnew.NETINFO_ITEM(board, "/SIG")
        board.Add(net)

        def track(start, end):
            item = pcbnew.PCB_TRACK(board)
            item.SetStart(pcbnew.VECTOR2I_MM(*start))
            item.SetEnd(pcbnew.VECTOR2I_MM(*end))
            item.SetWidth(pcbnew.FromMM(0.20))
            item.SetLayer(board.GetLayerID("F.Cu"))
            item.SetNet(net)
            board.Add(item)
            return item

        track((10, 10), (13, 10))
        diagonal = track((10, 10), (12, 8))
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(pcbnew.VECTOR2I_MM(10, 10))
        via.SetWidth(pcbnew.FromMM(0.60))
        via.SetDrill(pcbnew.FromMM(0.30))
        via.SetLayerPair(board.GetLayerID("F.Cu"),
                         board.GetLayerID("B.Cu"))
        via.SetNet(net)
        board.Add(via)

        self.assertEqual(repair.repair_via_acute_fanouts(board), 1)
        routed = [item for item in board.GetTracks()
                  if item.GetClass() == "PCB_TRACK"]
        self.assertEqual(len(routed), 4)
        self.assertEqual(diagonal.GetStart(), pcbnew.VECTOR2I_MM(10, 10))
        self.assertEqual(diagonal.GetEnd(), pcbnew.VECTOR2I_MM(10, 9.8))
        headings = sorted(
            (abs(item.GetEnd().x - item.GetStart().x),
             abs(item.GetEnd().y - item.GetStart().y))
            for item in routed)
        self.assertTrue(all(dx == 0 or dy == 0 or dx == dy
                            for dx, dy in headings))

    def test_via_hook_repair_refuses_locked_or_unanchored_geometry(self):
        board = pcbnew.CreateEmptyBoard()
        net = pcbnew.NETINFO_ITEM(board, "/SIG")
        board.Add(net)
        for start, end, locked in (
                ((10, 10), (13, 10), False),
                ((10, 10), (12, 8), True)):
            item = pcbnew.PCB_TRACK(board)
            item.SetStart(pcbnew.VECTOR2I_MM(*start))
            item.SetEnd(pcbnew.VECTOR2I_MM(*end))
            item.SetWidth(pcbnew.FromMM(0.20))
            item.SetLayer(board.GetLayerID("F.Cu"))
            item.SetNet(net)
            item.SetLocked(locked)
            board.Add(item)

        self.assertEqual(repair.repair_via_acute_fanouts(board), 0)

    def test_safe_slice_wins_and_regressive_full_slice_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            board = os.path.join(td, "board.kicad_pcb")
            with open(board, "w", encoding="utf-8") as handle:
                handle.write("baseline")

            def score(path):
                name = os.path.basename(path)
                row = {"drc": 1, "unconnected": 20,
                       "kelvin_ok": True, "diffpair_ok": True,
                       "route_blocking": 0, "route_advisory": 5,
                       "objective": 4337.0}
                if "copper_cleanup" in name:
                    row.update(route_advisory=3, objective=3837.0)
                elif "full" in name:
                    row.update(route_advisory=3, unconnected=21,
                               objective=3937.0)
                return row

            def mutate(path, **_kwargs):
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write(os.path.basename(path))
                return {"backtracks": 2}

            with mock.patch.object(repair, "_score_isolated", side_effect=score), \
                    mock.patch.object(repair, "_fab_isolated", return_value={
                        "fab_blocking": 5, "fab_drc": 0,
                        "fab_unconnected": 0}), \
                    mock.patch.object(repair, "_foreign_isolated", return_value={
                        "foreign_status": "ok", "foreign_tracks": 0,
                        "foreign_vias": 0, "foreign_blocking": 0}), \
                    mock.patch.object(repair, "_repair_isolated", side_effect=mutate), \
                    mock.patch.object(
                        repair, "_dangling_cleanup_isolated",
                        return_value={"removed": 0}), \
                    mock.patch.object(
                        repair, "_post_backtrack_acute_isolated",
                        return_value={"acute_vertices": 0}), \
                    mock.patch.object(
                        repair, "_sliver_repair_isolated",
                        return_value={"sliver_zones_removed": 0}):
                report = repair.repair_admitted(board)

            self.assertTrue(report["adopted"])
            self.assertEqual(report["chosen"], "copper_cleanup")
            variants = {row["name"]: row for row in report["variants"]}
            self.assertTrue(variants["copper_cleanup"]["safe"])
            self.assertFalse(variants["full"]["safe"])
            self.assertEqual(report["after"]["unconnected"], 20)
            with open(board, encoding="utf-8") as handle:
                self.assertIn("copper_cleanup", handle.read())

    def test_lower_count_variant_with_new_drc_identity_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            board = os.path.join(td, "board.kicad_pcb")
            with open(board, "w", encoding="utf-8") as handle:
                handle.write("baseline")

            old_fault = '["clearance","uuid",["old-a","old-b"]]'
            new_fault = '["shorting_items","uuid",["new-a","new-b"]]'

            def score(path):
                name = os.path.basename(path)
                row = {
                    "drc": 1, "drc_types": {"clearance": 1},
                    "unconnected": 10, "unconn_nets": ["/OPEN"],
                    "kelvin_ok": True, "diffpair_ok": True,
                    "structural_drc_identities": [old_fault],
                    "route_blocking": 0, "route_advisory": 5,
                    "objective": 100.0,
                }
                if ("copper_cleanup" in name or "corner_polish" in name
                        or "track_polish" in name
                        or "fab_polish" in name or "full" in name):
                    row.update({
                        "drc": 1,
                        "drc_types": {"shorting_items": 1},
                        "unconnected": 9,
                        "structural_drc_identities": [new_fault],
                        "route_advisory": 2,
                        "objective": 50.0,
                    })
                return row

            with mock.patch.object(repair, "_score_isolated",
                                   side_effect=score), \
                    mock.patch.object(repair, "_fab_isolated", return_value={
                        "fab_blocking": 5, "fab_drc": 0,
                        "fab_unconnected": 0}), \
                    mock.patch.object(repair, "_foreign_isolated", return_value={
                        "foreign_status": "ok", "foreign_tracks": 0,
                        "foreign_vias": 0, "foreign_blocking": 0}), \
                    mock.patch.object(
                        repair, "_repair_isolated",
                        return_value={"backtracks": 1}), \
                    mock.patch.object(
                        repair, "_dangling_cleanup_isolated",
                        return_value={"removed": 0}), \
                    mock.patch.object(
                        repair, "_post_backtrack_acute_isolated",
                        return_value={"acute_vertices": 0}), \
                    mock.patch.object(
                        repair, "_sliver_repair_isolated",
                        return_value={"sliver_zones_removed": 0}):
                report = repair.repair_admitted(board)

            self.assertFalse(report["adopted"])
            self.assertEqual(report["chosen"], "baseline")
            self.assertTrue(all(not row["safe"]
                                for row in report["variants"]))
            self.assertTrue(all(
                row["admission"]["decision"]
                == "new_structural_drc_identity"
                for row in report["variants"]))
            with open(board, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "baseline")

    def test_variant_that_introduces_foreign_pour_copper_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            board = os.path.join(td, "board.kicad_pcb")
            with open(board, "w", encoding="utf-8") as handle:
                handle.write("baseline")

            score = {
                "drc": 0, "unconnected": 0,
                "kelvin_ok": True, "diffpair_ok": True,
                "route_blocking": 0, "route_advisory": 1,
                "objective": 10.0,
            }

            def foreign(path):
                if os.path.basename(path) == "board.kicad_pcb":
                    return {"foreign_status": "ok", "foreign_tracks": 0,
                            "foreign_vias": 0, "foreign_blocking": 0}
                return {"foreign_status": "ok", "foreign_tracks": 1,
                        "foreign_vias": 0, "foreign_blocking": 1}

            with mock.patch.object(repair, "_score_isolated",
                                   return_value=score), \
                    mock.patch.object(repair, "_fab_isolated", return_value={
                        "fab_blocking": 0, "fab_drc": 0,
                        "fab_unconnected": 0}), \
                    mock.patch.object(repair, "_foreign_isolated",
                                      side_effect=foreign), \
                    mock.patch.object(
                        repair, "_repair_isolated",
                        return_value={"backtracks": 1}), \
                    mock.patch.object(
                        repair, "_dangling_cleanup_isolated",
                        return_value={"removed": 0}), \
                    mock.patch.object(
                        repair, "_post_backtrack_acute_isolated",
                        return_value={"acute_vertices": 0}), \
                    mock.patch.object(
                        repair, "_sliver_repair_isolated",
                        return_value={"sliver_zones_removed": 0}):
                report = repair.repair_admitted(board)

            self.assertFalse(report["adopted"])
            self.assertEqual(report["chosen"], "baseline")
            self.assertTrue(all(not row["safe"]
                                for row in report["variants"]))


if __name__ == "__main__":
    unittest.main()
