#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Last-mile completer teeth (2026-07-23, from the s120 residual autopsy: 13 of
# 30 unconnected gaps were <=5mm same-net pad/via/track gaps FR left in dense
# clusters -- incl. both GND criticals). The completer closes them post-fill
# with guarded canonical 0/45/90 legs or the over-the-top bridge; it must refuse
# blocked and edge-hugging gaps and leave far gaps alone. pcbnew required
# (container-only skip).
import os
import math
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


def _board(pads, edge=None):
    """Minimal 4-layer board: pads = [(x_mm, y_mm, net), ...] one SMD pad per
    footprint on F.Cu; edge = (x0, y0, x1, y1) optional Edge.Cuts rect."""
    import pcbnew
    b = pcbnew.BOARD()
    b.SetCopperLayerCount(4)
    nets = {}
    for index, (x, y, net) in enumerate(pads, 1):
        if net not in nets:
            ni = pcbnew.NETINFO_ITEM(b, net)
            b.Add(ni)
            nets[net] = ni
        fp = pcbnew.FOOTPRINT(b)
        fp.SetReference("X%d" % index)
        fp.SetPosition(pcbnew.VECTOR2I(int(x * 1e6), int(y * 1e6)))
        p = pcbnew.PAD(fp)
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetShape(pcbnew.PAD_SHAPE_RECT)
        p.SetSize(pcbnew.VECTOR2I(int(0.8e6), int(0.8e6)))
        p.SetPosition(fp.GetPosition())
        ls = pcbnew.LSET()
        ls.AddLayer(pcbnew.F_Cu)
        p.SetLayerSet(ls)
        p.SetNet(nets[net])
        fp.Add(p)
        b.Add(fp)
    if edge:
        x0, y0, x1, y1 = [int(v * 1e6) for v in edge]
        for (ax, ay, bx, by) in ((x0, y0, x1, y0), (x1, y0, x1, y1),
                                 (x1, y1, x0, y1), (x0, y1, x0, y0)):
            s = pcbnew.PCB_SHAPE(b)
            s.SetShape(pcbnew.SHAPE_T_SEGMENT)
            s.SetStart(pcbnew.VECTOR2I(ax, ay))
            s.SetEnd(pcbnew.VECTOR2I(bx, by))
            s.SetLayer(pcbnew.Edge_Cuts)
            b.Add(s)
    return b


def _bypass_board():
    """Power bypass C1/U1 plus a Default-class signal RC C2/U2."""
    import pcbnew

    board = pcbnew.BOARD()
    board.SetCopperLayerCount(6)
    nets = {}
    for name in ("GND", "/POWER", "/SENSE"):
        nets[name] = pcbnew.NETINFO_ITEM(board, name)
        board.Add(nets[name])
    front = pcbnew.LSET()
    front.AddLayer(pcbnew.F_Cu)

    def add(ref, pads):
        footprint = pcbnew.FOOTPRINT(board)
        footprint.SetReference(ref)
        for number, x, y, net in pads:
            pad = pcbnew.PAD(footprint)
            pad.SetPadName(str(number))
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetSize(pcbnew.VECTOR2I_MM(0.4, 0.4))
            pad.SetPosition(pcbnew.VECTOR2I_MM(x, y))
            pad.SetLayerSet(front)
            pad.SetNet(nets[net])
            footprint.Add(pad)
        board.Add(footprint)

    add("C1", ((1, 5, 5, "/POWER"), (2, 5, 6, "GND")))
    add("U1", ((1, 9, 5, "/POWER"),))
    add("C2", ((1, 5, 10, "/SENSE"), (2, 5, 11, "GND")))
    add("U2", ((1, 9, 10, "/SENSE"),))
    return board


class TestLastmile(unittest.TestCase):
    def test_exact_component_count_tracks_live_closure_not_refusal_rows(self):
        import cec_fr

        board = _board([(5, 5, "/N"), (7, 5, "/N")])
        net_code = board.GetNetcodeFromNetname("/N")
        board.BuildConnectivity()
        self.assertEqual(
            cec_fr.net_connectivity_component_count(board, net_code), 2)
        report = cec_fr.synthesize_lastmile(
            board, max_mm=5.0, min_w=0.2, clearance=0.2,
            include_nets={"/N"}, maze_max_mm=0.0)
        board.BuildConnectivity()
        self.assertEqual(report["closed"], 1)
        self.assertEqual(
            cec_fr.net_connectivity_component_count(board, net_code), 1)

    def test_plane_detection_uses_polygon_area_not_long_thin_bbox(self):
        import cec_fr

        edges = mock.Mock()
        edges.GetWidth.return_value = 100
        edges.GetHeight.return_value = 100
        layer_set = mock.Mock()
        layer_set.CuStack.return_value = [2]

        def zone(area):
            item = mock.Mock()
            item.GetIsRuleArea.return_value = False
            item.GetLayerSet.return_value = layer_set
            item.Outline.return_value.Area.return_value = area
            bbox = mock.Mock()
            bbox.GetWidth.return_value = 90
            bbox.GetHeight.return_value = 90
            item.GetBoundingBox.return_value = bbox
            return item

        board = mock.Mock()
        board.GetBoardEdgesBoundingBox.return_value = edges
        board.GetLayerName.return_value = "B.Cu"
        board.Zones.return_value = [zone(1000)]
        self.assertEqual(cec_fr.plane_layers(board), [])
        board.Zones.return_value = [zone(6000)]
        self.assertEqual(cec_fr.plane_layers(board), ["B.Cu"])

    def test_bounded_nearest_anchor_pairs_match_exhaustive_top_k(self):
        import cec_fr

        # Metadata after x/y deliberately differs; the helper must preserve
        # the original anchor rows while ranking only their exact coordinates.
        left = [
            (0, 0, "L0"),
            (8_000_000, 0, "L1"),
            (20_000_000, 0, "L2"),
        ]
        right = [
            (1_000_000, 0, "R0"),
            (9_500_000, 0, "R1"),
            (40_000_000, 0, "R2"),
        ]
        got = cec_fr._bounded_nearest_anchor_pairs(
            left, right, limit=3, max_mm=25.0)
        expected = sorted(
            ((math.hypot(a[0] - b[0], a[1] - b[1]) / 1e6, a, b)
             for a in left for b in right
             if math.hypot(a[0] - b[0], a[1] - b[1]) <= 25e6),
            key=lambda row: (
                row[0], left.index(row[1]), right.index(row[2])))[:3]
        self.assertEqual(got, expected)

    def test_multi_island_candidates_interleave_anchor_depth(self):
        import cec_fr

        rows = [
            (1, 1.1, 0, 1, "pair-01-second"),
            (0, 10.0, 0, 2, "pair-02-first"),
            (0, 1.0, 0, 1, "pair-01-first"),
            (2, 1.2, 0, 1, "pair-01-third"),
        ]
        ordered = cec_fr._interleave_component_pair_candidates(rows)

        self.assertEqual([row[-1] for row in ordered], [
            "pair-01-first",
            "pair-02-first",
            "pair-01-second",
            "pair-01-third",
        ])

    def test_route_aware_anchor_order_prefers_existing_layer_access(self):
        import cec_fr

        surface = (0, 0, frozenset((0,)), None, {"kind": "pad"})
        remote = (1_000_000, 0, frozenset((0,)), None,
                  {"kind": "pad"})
        existing_via = (200_000, 0, frozenset((0, 2, 4, 31)), None,
                        {"kind": "via"})
        rows = [
            (1.0, surface, remote),
            (1.2, existing_via, remote),
        ]

        ordered = cec_fr._route_aware_anchor_pair_order(rows)

        self.assertIs(ordered[0][1], existing_via)

    def test_route_aware_anchor_order_preserves_pad_escape_authority(self):
        import cec_fr

        remote_via = (0, 0, frozenset((0, 2, 4, 31)), None,
                      {"kind": "via"})
        point = (1_000_000, 0)
        raw_track = (*point, frozenset((0,)), None, {"kind": "trk"})
        fine_pad = (*point, frozenset((0,)), (200_000, 1_500_000),
                    {"kind": "pad", "ref": "U1", "pad": "1"})

        ordered = cec_fr._route_aware_anchor_pair_order([
            (1.0, remote_via, raw_track),
            (1.0, remote_via, fine_pad),
        ])

        self.assertIs(ordered[0][2], fine_pad)

    def test_bounded_route_portfolio_reserves_existing_via_candidate(self):
        import cec_fr

        remote = (0, 0, frozenset((0,)), None, {"kind": "pad"})
        surface = [
            (index * 10_000, 0, frozenset((0,)), None,
             {"kind": "trk", "index": index})
            for index in range(12)
        ]
        existing_via = (
            500_000, 0, frozenset((0, 2, 4, 31)), None,
            {"kind": "via"})
        left = surface + [existing_via]

        ordered = cec_fr._bounded_route_aware_anchor_pairs(
            left, [remote], limit=4, max_mm=2.0)

        self.assertTrue(any(row[1] is existing_via for row in ordered))
        self.assertIs(ordered[0][1], existing_via)

    def test_bounded_route_portfolio_reserves_via_to_via_pair(self):
        import cec_fr

        left_surface = [
            (index * 10_000, 0, frozenset((0,)), None,
             {"kind": "trk", "index": index})
            for index in range(12)
        ]
        right_surface = [
            (1_000_000 + index * 10_000, 0, frozenset((0,)), None,
             {"kind": "trk", "index": index})
            for index in range(12)
        ]
        left_via = (0, 500_000, frozenset((0, 2, 4, 31)), None,
                    {"kind": "via"})
        right_via = (1_000_000, 500_000, frozenset((0, 2, 4, 31)), None,
                     {"kind": "via"})

        ordered = cec_fr._bounded_route_aware_anchor_pairs(
            left_surface + [left_via], right_surface + [right_via],
            limit=4, max_mm=2.0)

        self.assertTrue(any(
            row[1] is left_via and row[2] is right_via
            for row in ordered))
        self.assertIs(ordered[0][1], left_via)
        self.assertIs(ordered[0][2], right_via)

    def test_fine_pad_to_large_rail_portfolio_samples_multiple_vias(self):
        import cec_fr

        fine_pad = (0, 0, frozenset((0,)), (200_000, 1_500_000),
                    {"kind": "pad", "ref": "U1", "pad": "1"})
        # These closer surface aliases all belong to one connected rail and
        # expose the same layer/corridor.  They must not starve the fourth
        # existing via when the fixed search budget is four candidates.
        surface = [
            (100_000 + index * 10_000, 0, frozenset((0,)), None,
             {"kind": "trk", "index": index})
            for index in range(12)
        ]
        vias = [
            ((index + 1) * 500_000, 250_000,
             frozenset((0, 2, 4, 31)), None,
             {"kind": "via", "index": index})
            for index in range(6)
        ]

        ordered = cec_fr._bounded_route_aware_anchor_pairs(
            [fine_pad], surface + vias, limit=4, max_mm=5.0)

        self.assertEqual(len(ordered), 4)
        self.assertEqual(
            [row[2][4]["index"] for row in ordered], [0, 1, 2, 3])
        self.assertTrue(all(len(row[2][2]) > 1 for row in ordered))

    def test_dogbone_lattice_samples_off_ray_fine_pitch_pocket(self):
        import cec_fr

        offsets = cec_fr._dogbone_lattice_offsets_mm(1.5)
        self.assertIn((-0.375, -0.75), offsets)
        self.assertEqual(offsets[0], (0.0, -0.125))
        distances = [round(dx * dx + dy * dy, 9)
                     for dx, dy in offsets]
        self.assertEqual(distances, sorted(distances))

    def test_board_scale_maze_uses_coarse_grid_unless_explicitly_pinned(self):
        import cec_fr

        self.assertEqual(cec_fr._adaptive_maze_grid_mm(9_000_000), 0.5)
        self.assertEqual(cec_fr._adaptive_maze_grid_mm(12_000_000), 0.75)
        self.assertEqual(cec_fr._adaptive_maze_grid_mm(25_000_000), 1.0)
        self.assertEqual(cec_fr._adaptive_maze_grid_mm(40_000_000), 1.5)
        self.assertEqual(
            cec_fr._adaptive_maze_grid_mm(40_000_000, 0.5), 0.5)

    def test_multilayer_maze_changes_layers_inside_fixed_corridor(self):
        import pcbnew
        import cec_fr

        board = _board([], edge=(0, 0, 6, 4))
        start = pcbnew.VECTOR2I_MM(1.0, 2.0)
        end = pcbnew.VECTOR2I_MM(5.0, 2.0)
        split_x = pcbnew.FromMM(3.0)

        # F.Cu is usable only on the left and B.Cu only on the right.  No
        # single-layer maze can connect the endpoints; a legal route must use
        # the one qualified through-via transition at x=3 mm.
        def foreign_clear(A, B, _width, _clearance, layer, _copper):
            if layer == pcbnew.F_Cu:
                return max(A.x, B.x) <= split_x
            if layer == pcbnew.B_Cu:
                return min(A.x, B.x) >= split_x
            return False

        with mock.patch.object(
                cec_fr, "_foreign_shape_indexes",
                side_effect=lambda _board, layer, _codes, cache=None:
                    (layer, [])), mock.patch.object(
                cec_fr, "_snapshot_foreign_clear",
                side_effect=foreign_clear), mock.patch.object(
                cec_fr, "_via_spot_clear",
                side_effect=lambda _board, at, *_args, **_kwargs:
                    at.x == split_x):
            operations = cec_fr._multilayer_maze_lastmile_ops(
                board, start, end, 1, (pcbnew.F_Cu, pcbnew.B_Cu),
                pcbnew.FromMM(0.2),
                lambda _a, _b, _half: True,
                width_for_layer=lambda _layer: pcbnew.FromMM(0.25),
                start_layers=(pcbnew.F_Cu,), end_layers=(pcbnew.B_Cu,),
                grid_mm=0.5, margin_mm=1.0, max_vias=1)

        self.assertIsNotNone(operations)
        self.assertEqual(sum(op[0] == "via" for op in operations), 1)
        self.assertEqual(
            {op[4] for op in operations if op[0] == "trk"},
            {pcbnew.F_Cu, pcbnew.B_Cu})
        for op in operations:
            if op[0] != "trk":
                continue
            _kind, A, B, _width, _layer = op
            self.assertTrue(A.x == B.x or A.y == B.y)

    def test_maze_preserves_escape_budgets_and_proves_wide_throat(self):
        import pcbnew
        import cec_fr

        board = _board([], edge=(0, 0, 10, 10))
        start = pcbnew.VECTOR2I_MM(4.0, 5.0)
        end = pcbnew.VECTOR2I_MM(5.0, 5.0)
        path = cec_fr._maze_lastmile_legs(
            board, start, end, pcbnew.FromMM(1.0), pcbnew.F_Cu,
            pcbnew.FromMM(0.2), 1, lambda _a, _b, _half: True,
            start_escape=(pcbnew.FromMM(0.2), pcbnew.FromMM(1.5)),
            end_escape=(pcbnew.FromMM(0.3), pcbnew.FromMM(1.5)),
            grid_mm=0.25, margin_mm=2.0)
        self.assertTrue(path)
        total = sum(math.hypot(b.x - a.x, b.y - a.y)
                    for a, b, _width in path) / 1e6
        wide = sum(math.hypot(b.x - a.x, b.y - a.y)
                   for a, b, width in path
                   if width == pcbnew.FromMM(1.0)) / 1e6
        start_narrow = 0.0
        for a, b, width in path:
            if width == pcbnew.FromMM(1.0):
                break
            start_narrow += math.hypot(b.x - a.x, b.y - a.y) / 1e6
        # A one-millimetre direct link cannot retain the 1.5mm source escape
        # and a class-width throat.  The maze must detour, remain inside the
        # real endpoint budget, and prove the throat before entering target.
        # An octilinear hop may end the narrow prefix before (never after) the
        # exact scalar budget boundary.
        self.assertGreater(total, 1.5)
        self.assertGreater(start_narrow, 0.0)
        self.assertLessEqual(start_narrow, 1.5 + 1e-6)
        self.assertGreaterEqual(wide, 0.25)

    def test_local_maze_can_use_exact_45_degree_pin_escape(self):
        import pcbnew
        import cec_fr

        board = _board([], edge=(0, 0, 6, 6))
        start = pcbnew.VECTOR2I_MM(1.0, 1.0)
        end = pcbnew.VECTOR2I_MM(3.0, 3.0)

        def diagonal_only(_a, _b, _width, _clearance, _zones, _copper):
            dx = abs(_b.x - _a.x)
            dy = abs(_b.y - _a.y)
            return dx > 0 and dx == dy

        with mock.patch.object(
                cec_fr, "_foreign_shape_indexes", return_value=([], [])), \
                mock.patch.object(
                    cec_fr, "_snapshot_foreign_clear",
                    side_effect=diagonal_only):
            path = cec_fr._maze_lastmile_legs(
                board, start, end, pcbnew.FromMM(0.25), pcbnew.F_Cu,
                pcbnew.FromMM(0.2), 1,
                lambda _a, _b, _half: True,
                grid_mm=0.5, margin_mm=1.0)

        self.assertTrue(path)
        for a, b, _width in path:
            self.assertEqual(abs(b.x - a.x), abs(b.y - a.y))

    def test_bridge_search_keeps_alternate_qualified_seat_pairs(self):
        import cec_fr
        via = [("via", object())]
        seats_a = [((0, 0), via), ((40, 0), via)]
        seats_b = [((0, 0), via), ((20, 0), via)]
        pairs = cec_fr._ranked_bridge_seat_pairs(seats_a, seats_b, 15)
        coordinates = [(a[0], b[0]) for a, b in pairs]

        self.assertEqual(len(pairs), 3)
        self.assertNotIn(((0, 0), (0, 0)), coordinates,
                         "two newly drilled seats must respect separation")
        self.assertIn(((0, 0), (20, 0)), coordinates,
                      "a rejected first pairing must not hide alternates")

    def test_bridge_search_ranks_total_escape_length_not_inner_span(self):
        import pcbnew
        import cec_fr

        def track(ax, ay, bx, by):
            return ("trk", pcbnew.VECTOR2I(ax, ay),
                    pcbnew.VECTOR2I(bx, by), 1, pcbnew.F_Cu)

        # The inward seats make the bridge itself shortest, but require long
        # face-layer stubs through the connector breakout. Perpendicular seats
        # are the shorter complete route and must rank first.
        seats_a = [((0, 10), [track(0, 0, 0, 10)]),
                   ((40, 0), [track(0, 0, 0, 60),
                              track(0, 60, 40, 0)])]
        seats_b = [((100, 10), [track(100, 0, 100, 10)]),
                   ((60, 0), [track(100, 0, 100, 60),
                              track(100, 60, 60, 0)])]
        pairs = cec_fr._ranked_bridge_seat_pairs(seats_a, seats_b, 1)

        self.assertEqual((pairs[0][0][0], pairs[0][1][0]),
                         ((0, 10), (100, 10)))

    def setUp(self):
        try:
            import pcbnew                          # noqa: F401
        except ImportError:
            self.skipTest("pcbnew not available (container-only test)")

    def test_short_gap_closes_straight(self):
        import cec_fr
        b = _board([(5, 5, "/A"), (7, 5, "/A")])
        r = cec_fr.synthesize_lastmile(b)
        self.assertEqual(r["closed"], 1)
        self.assertGreaterEqual(r["legs"], 1)
        segs = [t for t in b.GetTracks() if t.GetClass() != "PCB_VIA"]
        self.assertTrue(segs, "a closure must lay real copper")

    def test_project_clearance_can_replace_historical_global_floor(self):
        import cec_fr

        board = _board([(5, 5, "/A"), (7, 5, "/A")])
        original = cec_fr._guarded_profiled_lastmile_legs
        with mock.patch.object(
                cec_fr, "_guarded_profiled_lastmile_legs",
                wraps=original) as guarded:
            result = cec_fr.synthesize_lastmile(
                board, clearance=0.0,
                netclass_resolver=lambda _net: {
                    "track_width": 0.2, "clearance": 0.2})

        self.assertEqual(result["closed"], 1, result)
        self.assertTrue(guarded.call_args_list)
        self.assertTrue(all(
            call.args[5] == int(0.2e6)
            for call in guarded.call_args_list))

    def test_completed_net_is_not_touched_by_lastmile(self):
        import cec_fr

        board = _board([(5, 5, "/OWNED"), (7, 5, "/OWNED")])
        result = cec_fr.synthesize_lastmile(
            board, exclude_nets={"/OWNED"})

        self.assertEqual(result["closed"], 0)
        self.assertFalse(list(board.GetTracks()))

    def test_terminal_completion_does_not_apply_aggregate_current_to_every_leaf(self):
        import pcbnew
        import cec_fr

        b = _board([(5, 5, "+5VSB"), (12, 5, "+5VSB")],
                   edge=(0, 0, 20, 10))
        props = b.GetProperties()
        props["CEC_FAB_PROFILE"] = "jlcpcb_6l_pofv_signal"
        b.SetProperties(props)
        for footprint in b.GetFootprints():
            next(iter(footprint.Pads())).SetSize(
                pcbnew.VECTOR2I_MM(6.0, 6.0))
        with mock.patch.dict(
                os.environ,
                {"CEC_THERMAL_BOARD_HINT": "hub-standard-rev2"}), \
                mock.patch(
                    "cec_thermal_overlay.board_thermal_config",
                    return_value=(
                        {"+5VSB": 2.5}, None,
                        {"+5VSB": {"refs_src": ["X1"],
                                    "refs_sink": ["X2"]}}, None)):
            result = cec_fr.synthesize_lastmile(
                b, max_mm=10.0,
                netclass_resolver=lambda _net: {"track_width": 1.0})

        self.assertEqual(result["closed"], 1, result)
        self.assertEqual(
            result["aggregate_current_domains"]["+5VSB"]["authority_refs"],
            ["X1", "X2"])
        widths = [track.GetWidth() / 1e6 for track in b.GetTracks()
                  if track.GetClass() != "PCB_VIA"]
        self.assertTrue(widths)
        self.assertTrue(all(abs(width - 1.0) < 0.001 for width in widths))

    def test_priority_completion_scopes_graph_to_authority_refs(self):
        import pcbnew
        import cec_fr

        board = _board([(5, 5, "/POWER"), (10, 5, "/POWER"),
                        (7.5, 8, "/POWER")], edge=(0, 0, 15, 12))
        result = cec_fr.synthesize_lastmile(
            board, max_mm=10.0, lock=True,
            terminal_refs_by_net={"/POWER": {"X1", "X2"}})

        self.assertEqual(result["closed"], 1, result)
        board.BuildConnectivity()
        pads = {fp.GetReference(): next(iter(fp.Pads()))
                for fp in board.GetFootprints()}
        connected = {
            (item.GetParentFootprint().GetReference()
             if item.GetClass() == "PAD" else None)
            for item in board.GetConnectivity().GetConnectedItems(pads["X1"])}
        self.assertIn("X2", connected)
        self.assertNotIn("X3", connected)

    def test_profiled_path_neckdown_is_bounded_at_both_ends(self):
        import pcbnew
        import cec_fr

        points = [pcbnew.VECTOR2I_MM(0, 0), pcbnew.VECTOR2I_MM(4, 0)]
        legs = cec_fr._profiled_lastmile_path(
            points, int(1.0e6),
            start_escape=(int(0.25e6), int(1.5e6)),
            end_escape=(int(0.25e6), int(1.5e6)))
        self.assertEqual([width for _a, _b, width in legs],
                         [int(0.25e6), int(1.0e6), int(0.25e6)])
        self.assertEqual(legs[0][0], points[0])
        self.assertEqual(legs[-1][1], points[-1])

    def test_power_neckdowns_leave_a_full_width_throat(self):
        """Two nearby fine-pitch power escapes must not overlap across the
        entire link and silently turn a class-width rail into a bottleneck."""
        import pcbnew
        import cec_fr

        points = [pcbnew.VECTOR2I_MM(0, 0), pcbnew.VECTOR2I_MM(0.779, 0)]
        legs = cec_fr._profiled_lastmile_path(
            points, int(1.0e6),
            start_escape=(int(0.20e6), int(1.5e6)),
            end_escape=(int(0.20e6), int(1.5e6)))

        widths = [width for _a, _b, width in legs]
        self.assertEqual(widths, [int(0.20e6), int(1.0e6), int(0.20e6)])

    def test_fine_pitch_power_gap_uses_local_neckdowns(self):
        """A class-width trunk must not make a physically routable SMD pin
        escape look blocked; only bounded endpoint prefixes may narrow."""
        import pcbnew
        import cec_fr

        b = _board([(5, 5, "/POWER"), (7, 5, "/POWER"),
                    (6, 5.9, "/BLOCK")])
        power_pads = [p for fp in b.GetFootprints() for p in fp.Pads()
                      if p.GetNetname() == "/POWER"]
        for pad in power_pads:
            pad.SetSize(pcbnew.VECTOR2I_MM(0.4, 0.4))
        b.BuildConnectivity()

        with mock.patch.object(cec_fr, "_lastmile_bridge", return_value=None):
            result = cec_fr.synthesize_lastmile(
                b, netclass_resolver=lambda net: {
                    "track_width": 1.0 if net == "/POWER" else 0.25})
        self.assertEqual(result["closed"], 1)
        power_tracks = [t for t in b.GetTracks()
                        if t.GetNetname() == "/POWER"]
        self.assertTrue(power_tracks)
        widths = {t.GetWidth() for t in power_tracks}
        self.assertIn(int(1.0e6), widths,
                      "fine-pitch escapes still require a class-width throat")
        self.assertTrue(any(width < int(1.0e6) for width in widths),
                        "the pad-local escape may neck down where required")
        self.assertEqual(result["endpoint_neckdown"]["group"],
                         cec_fr.ENDPOINT_NECKDOWN_GROUP)
        group = next(group for group in b.Groups()
                     if group.GetName() == cec_fr.ENDPOINT_NECKDOWN_GROUP)
        narrow = [track for track in power_tracks
                  if track.GetWidth() < int(1.0e6)]
        self.assertTrue(narrow)
        self.assertTrue(all(group.ContainsItem(track) for track in narrow))

        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "neckdown.kicad_pcb")
            pcbnew.SaveBoard(path, b)
            rule = cec_fr.ensure_endpoint_neckdown_rule(path, result)
            self.assertTrue(rule["applicable"])
            with open(path[:-len(".kicad_pcb")] + ".kicad_dru",
                      encoding="utf-8") as handle:
                rules = handle.read()
            self.assertIn("memberOfGroup('CEC_LOCAL_ENDPOINT_NECKDOWN')",
                          rules)

    def test_long_narrow_route_cannot_claim_endpoint_exception(self):
        """A generated label must not exempt a board-scale skinny leg."""
        import pcbnew
        import cec_fr

        board = _board([(5, 5, "/POWER")], edge=(0, 0, 15, 10))
        pad = next(iter(next(iter(board.GetFootprints())).Pads()))
        pad.SetSize(pcbnew.VECTOR2I_MM(0.4, 0.4))
        net = board.GetNetInfo().GetNetItem("/POWER")
        narrow = pcbnew.PCB_TRACK(board)
        narrow.SetStart(pcbnew.VECTOR2I_MM(5, 5))
        narrow.SetEnd(pcbnew.VECTOR2I_MM(8, 5))
        narrow.SetWidth(pcbnew.FromMM(0.2))
        narrow.SetLayer(pcbnew.F_Cu); narrow.SetNet(net); board.Add(narrow)
        trunk = pcbnew.PCB_TRACK(board)
        trunk.SetStart(narrow.GetEnd())
        trunk.SetEnd(pcbnew.VECTOR2I_MM(10, 5))
        trunk.SetWidth(pcbnew.FromMM(0.5))
        trunk.SetLayer(pcbnew.F_Cu); trunk.SetNet(net); board.Add(trunk)

        report = cec_fr.group_endpoint_neckdowns(
            board, [narrow], pcbnew.FromMM(0.5))

        self.assertEqual(report["tracks"], 0, report)
        self.assertEqual(report["rejected"][0]["reason"],
                         "escape_budget_exceeded")
        self.assertFalse(any(
            group.GetName() == cec_fr.ENDPOINT_NECKDOWN_GROUP
            for group in board.Groups()))

    def test_elongated_pad_neckdown_uses_physical_flare_budget(self):
        """Qualification mirrors the synthesizer's land-clearance budget."""
        import pcbnew
        import cec_fr

        board = _board([(5, 5, "/POWER")], edge=(0, 0, 15, 10))
        pad = next(iter(next(iter(board.GetFootprints())).Pads()))
        pad.SetSize(pcbnew.VECTOR2I_MM(1.4, 0.4))
        pad.SetLocalClearance(pcbnew.FromMM(0.2))
        net = board.GetNetInfo().GetNetItem("/POWER")
        narrow = pcbnew.PCB_TRACK(board)
        narrow.SetStart(pcbnew.VECTOR2I_MM(5, 5))
        narrow.SetEnd(pcbnew.VECTOR2I_MM(6.1, 5))
        narrow.SetWidth(pcbnew.FromMM(0.2))
        narrow.SetLayer(pcbnew.F_Cu); narrow.SetNet(net); board.Add(narrow)
        trunk = pcbnew.PCB_TRACK(board)
        trunk.SetStart(narrow.GetEnd())
        trunk.SetEnd(pcbnew.VECTOR2I_MM(8, 5))
        trunk.SetWidth(pcbnew.FromMM(0.5))
        trunk.SetLayer(pcbnew.F_Cu); trunk.SetNet(net); board.Add(trunk)

        report = cec_fr.group_endpoint_neckdowns(
            board, [narrow], pcbnew.FromMM(0.5))

        self.assertEqual(report["tracks"], 1, report)
        self.assertEqual(report["rejected"], [], report)

    def test_hierarchical_patterns_become_exact_kicad_assignments(self):
        import json
        import pcbnew
        import cec_fr

        board = _board([(5, 5, "/sheet/+3V3"),
                        (8, 5, "/sheet/VBUS_F")])
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "candidate.kicad_pcb")
            project = path.replace(".kicad_pcb", ".kicad_pro")
            pcbnew.SaveBoard(path, board)
            with open(project, "w", encoding="utf-8") as sink:
                json.dump({"net_settings": {
                    "classes": [
                        {"name": "Default", "track_width": 0.2},
                        {"name": "Power", "track_width": 0.5}],
                    "netclass_patterns": [
                        {"netclass": "Power", "pattern": "+3V3"}],
                    "netclass_assignments": {},
                }}, sink)

            report = cec_fr.materialize_hierarchical_netclass_assignments(
                path, current_nets=("/sheet/VBUS_F",))
            with open(project, encoding="utf-8") as source:
                assignments = json.load(source)["net_settings"][
                    "netclass_assignments"]

        self.assertTrue(report["written"], report)
        self.assertEqual(assignments["/sheet/+3V3"], "Power")
        self.assertEqual(assignments["/sheet/VBUS_F"], "Power")

    def test_split_endpoint_taper_recovers_group_membership(self):
        import pcbnew
        import cec_fr

        board = _board([(5, 5, "/POWER")])
        pad = next(iter(next(iter(board.GetFootprints())).Pads()))
        # Both ends of the inner fragment lie inside this elongated land, as
        # happens when an import/reconcile pass splits a pad-centre escape.
        pad.SetSize(pcbnew.VECTOR2I_MM(1.05, 0.4))
        net = board.GetNetInfo().GetNetItem("/POWER")

        inner = pcbnew.PCB_TRACK(board)
        inner.SetStart(pcbnew.VECTOR2I_MM(5.0, 5.0))
        inner.SetEnd(pcbnew.VECTOR2I_MM(4.65, 5.0))
        inner.SetWidth(pcbnew.FromMM(0.25))
        inner.SetLayer(pcbnew.F_Cu); inner.SetNet(net); board.Add(inner)
        outer = pcbnew.PCB_TRACK(board)
        outer.SetStart(pcbnew.VECTOR2I_MM(4.65, 5.0))
        outer.SetEnd(pcbnew.VECTOR2I_MM(4.3, 5.0))
        outer.SetWidth(pcbnew.FromMM(0.25))
        outer.SetLayer(pcbnew.F_Cu); outer.SetNet(net); board.Add(outer)
        trunk = pcbnew.PCB_TRACK(board)
        trunk.SetStart(pcbnew.VECTOR2I_MM(4.3, 5.0))
        trunk.SetEnd(pcbnew.VECTOR2I_MM(3.0, 5.0))
        trunk.SetWidth(pcbnew.FromMM(1.0))
        trunk.SetLayer(pcbnew.F_Cu); trunk.SetNet(net); board.Add(trunk)
        cec_fr.group_endpoint_neckdowns(board, [outer], pcbnew.FromMM(1.0))

        report = cec_fr.reconcile_endpoint_neckdown_groups(
            board, netclass_resolver=lambda _net: {"track_width": 1.0})
        group = next(group for group in board.Groups()
                     if group.GetName() == cec_fr.ENDPOINT_NECKDOWN_GROUP)

        self.assertEqual(report["recovered"], 1, report)
        self.assertTrue(group.ContainsItem(inner))
        self.assertTrue(group.ContainsItem(outer))

    def test_split_ungrouped_taper_recovers_as_one_bounded_component(self):
        import pcbnew
        import cec_fr

        board = _board([(5, 5, "/POWER")])
        pad = next(iter(next(iter(board.GetFootprints())).Pads()))
        pad.SetSize(pcbnew.VECTOR2I_MM(0.4, 0.4))
        net = board.GetNetInfo().GetNetItem("/POWER")
        group = pcbnew.PCB_GROUP(board)
        group.SetName(cec_fr.ENDPOINT_NECKDOWN_GROUP)
        board.Add(group)

        inner = pcbnew.PCB_TRACK(board)
        inner.SetStart(pcbnew.VECTOR2I_MM(5.0, 5.0))
        inner.SetEnd(pcbnew.VECTOR2I_MM(4.5, 5.0))
        inner.SetWidth(pcbnew.FromMM(0.20))
        inner.SetLayer(pcbnew.F_Cu); inner.SetNet(net); board.Add(inner)
        outer = pcbnew.PCB_TRACK(board)
        outer.SetStart(pcbnew.VECTOR2I_MM(4.5, 5.0))
        outer.SetEnd(pcbnew.VECTOR2I_MM(4.25, 5.0))
        outer.SetWidth(pcbnew.FromMM(0.20))
        outer.SetLayer(pcbnew.F_Cu); outer.SetNet(net); board.Add(outer)
        trunk = pcbnew.PCB_TRACK(board)
        trunk.SetStart(pcbnew.VECTOR2I_MM(4.25, 5.0))
        trunk.SetEnd(pcbnew.VECTOR2I_MM(3.0, 5.0))
        trunk.SetWidth(pcbnew.FromMM(0.50))
        trunk.SetLayer(pcbnew.F_Cu); trunk.SetNet(net); board.Add(trunk)

        report = cec_fr.reconcile_endpoint_neckdown_groups(
            board, netclass_resolver=lambda _net: {"track_width": 0.5})

        self.assertEqual(report["recovered"], 2, report)
        self.assertTrue(group.ContainsItem(inner))
        self.assertTrue(group.ContainsItem(outer))
        self.assertTrue(inner.IsLocked())
        self.assertTrue(outer.IsLocked())

    def test_pad_limited_ground_dogbone_recovers_at_full_width_via(self):
        import pcbnew
        import cec_fr

        board = _board([(5, 5, "/POWER")])
        pad = next(iter(next(iter(board.GetFootprints())).Pads()))
        pad.SetSize(pcbnew.VECTOR2I_MM(1.45, 0.30))
        net = board.GetNetInfo().GetNetItem("/POWER")
        group = pcbnew.PCB_GROUP(board)
        group.SetName(cec_fr.ENDPOINT_NECKDOWN_GROUP)
        board.Add(group)
        dogbone = pcbnew.PCB_TRACK(board)
        dogbone.SetStart(pcbnew.VECTOR2I_MM(5.0, 5.0))
        dogbone.SetEnd(pcbnew.VECTOR2I_MM(6.45, 5.0))
        dogbone.SetWidth(pcbnew.FromMM(0.30))
        dogbone.SetLayer(pcbnew.F_Cu)
        dogbone.SetNet(net)
        board.Add(dogbone)
        via = pcbnew.PCB_VIA(board)
        via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetPosition(dogbone.GetEnd())
        via.SetWidth(pcbnew.FromMM(0.90))
        via.SetDrill(pcbnew.FromMM(0.50))
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetNet(net)
        board.Add(via)

        report = cec_fr.reconcile_endpoint_neckdown_groups(
            board, netclass_resolver=lambda _net: {"track_width": 0.5})

        self.assertEqual(report["recovered"], 1, report)
        self.assertEqual(
            report["items"][0]["reason"], "fine_pad_to_full_width_via")
        self.assertTrue(group.ContainsItem(dogbone))
        self.assertTrue(dogbone.IsLocked())

    def test_pofv_dogbone_recovers_only_with_opposite_layer_full_width(self):
        """A profile-qualified small barrel can end a bounded power launch
        only when it immediately becomes a real class-width route."""
        import pcbnew
        import cec_fr

        board = _board([(5, 5, "/POWER")])
        pad = next(iter(next(iter(board.GetFootprints())).Pads()))
        pad.SetSize(pcbnew.VECTOR2I_MM(0.30, 1.15))
        net = board.GetNetInfo().GetNetItem("/POWER")
        dogbone = pcbnew.PCB_TRACK(board)
        dogbone.SetStart(pcbnew.VECTOR2I_MM(5.0, 5.0))
        dogbone.SetEnd(pcbnew.VECTOR2I_MM(4.25, 5.0))
        dogbone.SetWidth(pcbnew.FromMM(0.20))
        dogbone.SetLayer(pcbnew.F_Cu); dogbone.SetNet(net)
        board.Add(dogbone)
        via = pcbnew.PCB_VIA(board)
        via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetPosition(dogbone.GetEnd())
        via.SetWidth(pcbnew.FromMM(0.35))
        via.SetDrill(pcbnew.FromMM(0.25))
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetNet(net); board.Add(via)
        trunk = pcbnew.PCB_TRACK(board)
        trunk.SetStart(via.GetPosition())
        trunk.SetEnd(pcbnew.VECTOR2I_MM(2.45, 5.0))
        trunk.SetWidth(pcbnew.FromMM(0.50))
        trunk.SetLayer(pcbnew.B_Cu); trunk.SetNet(net)
        board.Add(trunk)
        pofv_group = pcbnew.PCB_GROUP(board)
        pofv_group.SetName(cec_fr.LOCAL_POFV_SIGNAL_VIA_GROUP)
        board.Add(pofv_group); pofv_group.AddItem(via)

        with mock.patch.object(
                cec_fr._fab, "board_profile_name",
                return_value="qualified"), mock.patch.object(
                cec_fr._fab, "get_profile",
                return_value={"pofv": {"enabled": True}}), \
                mock.patch.object(
                    cec_fr._fab, "pofv_dimensions",
                    return_value=(True, "qualified")):
            report = cec_fr.reconcile_endpoint_neckdown_groups(
                board, netclass_resolver=lambda _net: {
                    "track_width": 0.5})

        self.assertEqual(report["recovered"], 1, report)
        self.assertEqual(report["items"][0]["reason"],
                         "fine_pad_to_profiled_via_throat")
        endpoint_group = next(
            group for group in board.Groups()
            if group.GetName() == cec_fr.ENDPOINT_NECKDOWN_GROUP)
        self.assertTrue(endpoint_group.ContainsItem(dogbone))
        self.assertTrue(dogbone.IsLocked())

    def test_pofv_dogbone_without_full_width_continuation_is_refused(self):
        import pcbnew
        import cec_fr

        board = _board([(5, 5, "/POWER")])
        pad = next(iter(next(iter(board.GetFootprints())).Pads()))
        pad.SetSize(pcbnew.VECTOR2I_MM(0.30, 1.15))
        net = board.GetNetInfo().GetNetItem("/POWER")
        dogbone = pcbnew.PCB_TRACK(board)
        dogbone.SetStart(pcbnew.VECTOR2I_MM(5.0, 5.0))
        dogbone.SetEnd(pcbnew.VECTOR2I_MM(4.25, 5.0))
        dogbone.SetWidth(pcbnew.FromMM(0.20))
        dogbone.SetLayer(pcbnew.F_Cu); dogbone.SetNet(net)
        board.Add(dogbone)
        via = pcbnew.PCB_VIA(board)
        via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetPosition(dogbone.GetEnd())
        via.SetWidth(pcbnew.FromMM(0.35))
        via.SetDrill(pcbnew.FromMM(0.25))
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetNet(net); board.Add(via)
        pofv_group = pcbnew.PCB_GROUP(board)
        pofv_group.SetName(cec_fr.LOCAL_POFV_SIGNAL_VIA_GROUP)
        board.Add(pofv_group); pofv_group.AddItem(via)

        with mock.patch.object(
                cec_fr._fab, "board_profile_name",
                return_value="qualified"), mock.patch.object(
                cec_fr._fab, "get_profile",
                return_value={"pofv": {"enabled": True}}), \
                mock.patch.object(
                    cec_fr._fab, "pofv_dimensions",
                    return_value=(True, "qualified")):
            report = cec_fr.reconcile_endpoint_neckdown_groups(
                board, netclass_resolver=lambda _net: {
                    "track_width": 0.5})

        self.assertEqual(report["recovered"], 0, report)
        self.assertFalse(any(
            group.GetName() == cec_fr.ENDPOINT_NECKDOWN_GROUP
            for group in board.Groups()))

    def test_nested_domain_neckdown_evidence_writes_scoped_rule(self):
        import cec_fr

        report = {"repair": {"domains": {"/VBUS": {
            "endpoint_neckdown": {
                "group": cec_fr.ENDPOINT_NECKDOWN_GROUP,
                "tracks": 2,
                "min_width_mm": 0.2,
            }}}}}
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "candidate.kicad_pcb")
            rule = cec_fr.ensure_endpoint_neckdown_rule(path, report)
            self.assertTrue(rule["applicable"], rule)
            with open(rule["path"], encoding="utf-8") as handle:
                text = handle.read()
        self.assertIn("track_width (min 0.200mm)", text)

    def test_same_footprint_fine_pad_bridge_is_owned_without_trunk(self):
        import pcbnew
        import cec_fr

        board = pcbnew.BOARD()
        board.SetCopperLayerCount(4)
        net = pcbnew.NETINFO_ITEM(board, "/VBUS")
        board.Add(net)
        footprint = pcbnew.FOOTPRINT(board)
        footprint.SetReference("J1")
        front = pcbnew.LSET()
        front.AddLayer(pcbnew.F_Cu)
        for number, y in (("A4", 5.0), ("B9", 5.3)):
            pad = pcbnew.PAD(footprint)
            pad.SetPadName(number)
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetSize(pcbnew.VECTOR2I_MM(0.3, 1.15))
            pad.SetPosition(pcbnew.VECTOR2I_MM(5.0, y))
            pad.SetLayerSet(front)
            pad.SetNet(net)
            footprint.Add(pad)
        board.Add(footprint)
        group = pcbnew.PCB_GROUP(board)
        group.SetName(cec_fr.ENDPOINT_NECKDOWN_GROUP)
        board.Add(group)
        bridge = pcbnew.PCB_TRACK(board)
        bridge.SetStart(pcbnew.VECTOR2I_MM(5.0, 5.0))
        bridge.SetEnd(pcbnew.VECTOR2I_MM(5.0, 5.3))
        bridge.SetWidth(pcbnew.FromMM(0.20))
        bridge.SetLayer(pcbnew.F_Cu); bridge.SetNet(net); board.Add(bridge)

        report = cec_fr.reconcile_endpoint_neckdown_groups(
            board, netclass_resolver=lambda _net: {"track_width": 0.5})

        self.assertEqual(report["recovered"], 1, report)
        self.assertEqual(report["items"][0]["reason"], "local_pad_bridge")
        self.assertTrue(group.ContainsItem(bridge))
        self.assertTrue(bridge.IsLocked())

    def test_cloned_same_net_pad_uuids_do_not_collapse_clusters(self):
        import pcbnew
        import cec_fr

        b = pcbnew.BOARD()
        b.SetCopperLayerCount(4)
        net = pcbnew.NETINFO_ITEM(b, "/A")
        b.Add(net)
        first = pcbnew.FOOTPRINT(b)
        first.SetReference("U1")
        first.SetPosition(pcbnew.VECTOR2I_MM(5.0, 5.0))
        pad = pcbnew.PAD(first)
        pad.SetPadName("1")
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(pcbnew.VECTOR2I_MM(0.8, 0.8))
        pad.SetPosition(first.GetPosition())
        front = pcbnew.LSET()
        front.AddLayer(pcbnew.F_Cu)
        pad.SetLayerSet(front)
        pad.SetNet(net)
        first.Add(pad)
        b.Add(first)

        # The copy constructor preserves the child UUID, reproducing the Hub
        # reference's cloned-footprint defect on two pads of the same net.
        second = pcbnew.FOOTPRINT(first)
        second.SetReference("U2")
        second.SetPosition(pcbnew.VECTOR2I_MM(7.0, 5.0))
        b.Add(second)
        pads = [p for fp in b.GetFootprints() for p in fp.Pads()]
        self.assertEqual(pads[0].m_Uuid.AsString(), pads[1].m_Uuid.AsString())

        b.BuildConnectivity()
        result = cec_fr.synthesize_lastmile(b)
        self.assertEqual(result["closed"], 1)
        self.assertTrue(list(b.GetTracks()))

    def test_arbitrary_offset_uses_only_canonical_angles(self):
        import cec_fr
        b = _board([(5, 5, "/A"), (8, 7, "/A")])
        r = cec_fr.synthesize_lastmile(b)
        self.assertEqual(r["closed"], 1)
        segs = [t for t in b.GetTracks() if t.GetClass() != "PCB_VIA"]
        self.assertGreaterEqual(len(segs), 2)
        for track in segs:
            dx = track.GetEnd().x - track.GetStart().x
            dy = track.GetEnd().y - track.GetStart().y
            angle = abs(math.degrees(math.atan2(dy, dx))) % 90.0
            self.assertLess(min(angle, abs(45.0 - angle), abs(90.0 - angle)),
                            1e-6, "last-mile copper must be 0/45/90 degrees")

    def test_lastmile_cannot_cross_future_frozen_power_corridor(self):
        import json
        import pcbnew
        import cec_fr

        board = _board([(1, 5, "/SIG"), (9, 5, "/SIG")],
                       edge=(0, 0, 10, 10))
        net = board.GetNetcodeFromNetname("/SIG")
        state = {"corridors": [{
            "net": "/POWER", "layer": "B.Cu",
            "x0": 4.0, "y0": 0.0, "x1": 6.0, "y1": 10.0,
        }]}
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "power-state.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(state, handle)
            with mock.patch.dict(
                    os.environ, {"CEC_POURFIRST_STATE": path}, clear=False):
                legs = cec_fr._guarded_profiled_lastmile_legs(
                    board, pcbnew.VECTOR2I_MM(1.0, 5.0),
                    pcbnew.VECTOR2I_MM(9.0, 5.0),
                    pcbnew.FromMM(0.5), pcbnew.B_Cu,
                    pcbnew.FromMM(0.2), net,
                    lambda start, end, half: cec_fr._edge_leg_clear(
                        board, start, end, half),
                    allow_maze=False)

        self.assertIsNone(legs)

    def test_through_via_cannot_pierce_future_frozen_power_corridor(self):
        import json
        import pcbnew
        import cec_fr

        board = _board([(2, 2, "/SIG")], edge=(0, 0, 10, 10))
        net = board.GetNetcodeFromNetname("/SIG")
        state = {"corridors": [{
            "net": "/POWER", "layer": "B.Cu",
            "x0": 4.0, "y0": 4.0, "x1": 6.0, "y1": 6.0,
        }]}
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "power-state.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(state, handle)
            with mock.patch.dict(
                    os.environ, {"CEC_POURFIRST_STATE": path}, clear=False):
                clear = cec_fr._via_spot_clear(
                    board, pcbnew.VECTOR2I_MM(5.0, 5.0),
                    pcbnew.FromMM(0.6), pcbnew.FromMM(0.2), {net},
                    drill_nm=pcbnew.FromMM(0.3), net_code=net)

        self.assertFalse(clear)

    def test_full_width_endpoints_can_use_bounded_maze(self):
        import pcbnew
        import cec_fr

        board = _board([(5, 5, "/A"), (8, 7, "/A")])
        start = pcbnew.VECTOR2I_MM(5.0, 5.0)
        end = pcbnew.VECTOR2I_MM(8.0, 7.0)
        code = board.GetNetcodeFromNetname("/A")
        legs = cec_fr._maze_lastmile_legs(
            board, start, end, int(0.2e6), pcbnew.F_Cu,
            int(0.2e6), code,
            lambda _start, _end, _half: True,
            start_escape=None, end_escape=None)

        self.assertTrue(legs,
                        "the maze is a general detour, not only a neck-down tool")
        self.assertEqual(legs[0][0], start)
        self.assertEqual(legs[-1][1], end)

    def test_long_eligible_gap_does_not_expand_local_maze(self):
        """A wide completion radius must not make the 0.5 mm-grid fallback
        raster the whole board. Canonical guarded closure remains eligible."""
        import cec_fr

        board = _board([(5, 5, "/A"), (25, 5, "/A")])
        with mock.patch.object(
                cec_fr, "_maze_lastmile_legs", wraps=cec_fr._maze_lastmile_legs
        ) as maze:
            result = cec_fr.synthesize_lastmile(
                board, max_mm=50.0, maze_max_mm=8.0)

        self.assertEqual(result["closed"], 1)
        maze.assert_not_called()

    def test_lastmile_bridge_uses_bounded_alternate_seats(self):
        """The bridge helper must receive the same bounded retry budget as
        the anchor-pair search; a single individually valid seat can still
        form a blocked or drill-too-close pair."""
        import cec_fr

        board = _board([(5, 5, "/A"), (7, 5, "/A")])
        with mock.patch.object(
                cec_fr, "_guarded_profiled_lastmile_legs", return_value=None
        ), mock.patch.object(
                cec_fr, "_lastmile_bridge", return_value=None
        ) as bridge:
            cec_fr.synthesize_lastmile(board, attempts_per_pair=6)

        self.assertTrue(bridge.called)
        self.assertEqual(bridge.call_args.kwargs["seat_limit"], 6)

    def test_bridge_prefers_fabrication_qualified_endpoint_vias(self):
        import pcbnew
        import cec_fr

        board = _board([], edge=(0, 0, 8, 4))
        start = pcbnew.VECTOR2I_MM(1.0, 2.0)
        end = pcbnew.VECTOR2I_MM(7.0, 2.0)
        qualified = {(start.x, start.y), (end.x, end.y)}
        with mock.patch.object(
                cec_fr, "_via_spot_clear",
                side_effect=lambda _board, at, *_args, **_kwargs:
                    (at.x, at.y) in qualified), mock.patch.object(
                cec_fr, "_guarded_lastmile_legs",
                return_value=[(start, end)]), mock.patch.object(
                cec_fr, "_guarded_profiled_lastmile_legs",
                return_value=None):
            operations = cec_fr._lastmile_bridge(
                board, (start.x, start.y), {pcbnew.F_Cu},
                (end.x, end.y), {pcbnew.F_Cu},
                pcbnew.FromMM(0.25), 1, [pcbnew.B_Cu],
                pcbnew.FromMM(0.2),
                leg_ok=lambda _a, _b, _half: True,
                seat_limit=8, allow_maze=False)

        self.assertIsNotNone(operations)
        vias = [op for op in operations if op[0] == "via"]
        self.assertEqual([(op[1].x, op[1].y) for op in vias],
                         [(start.x, start.y), (end.x, end.y)])
        self.assertFalse([
            op for op in operations
            if op[0] == "trk" and op[4] == pcbnew.F_Cu
        ], "qualified endpoint vias need no offset dogbone stubs")

    def test_bridge_uses_declared_pofv_geometry_at_pad_origin(self):
        import pcbnew
        import cec_fr

        board = _board([], edge=(0, 0, 8, 4))
        start = pcbnew.VECTOR2I_MM(1.0, 2.0)
        end = pcbnew.VECTOR2I_MM(7.0, 2.0)
        qualified = {(start.x, start.y), (end.x, end.y)}
        calls = []

        def via_clear(_board, at, diameter, _clearance, _nets, **kwargs):
            calls.append((at.x, at.y, diameter, kwargs.get("drill_nm")))
            return ((at.x, at.y) in qualified
                    and diameter == pcbnew.FromMM(0.35)
                    and kwargs.get("drill_nm") == pcbnew.FromMM(0.25))

        with mock.patch.object(
                cec_fr._fab, "board_profile_name",
                return_value="jlcpcb_6l_pofv_signal"), \
                mock.patch.object(
                    cec_fr._fab, "via_at_pad_conflicts",
                    return_value=(None, [{"ref": "U1", "pad": "1"}])), \
                mock.patch.object(cec_fr, "_via_spot_clear",
                               side_effect=via_clear), \
                mock.patch.object(cec_fr, "_guarded_lastmile_legs",
                                  return_value=[(start, end)]), \
                mock.patch.object(
                    cec_fr, "_guarded_profiled_lastmile_legs",
                    return_value=None):
            operations = cec_fr._lastmile_bridge(
                board, (start.x, start.y), {pcbnew.F_Cu},
                (end.x, end.y), {pcbnew.F_Cu},
                pcbnew.FromMM(0.25), 1, [pcbnew.B_Cu],
                pcbnew.FromMM(0.2), drill=0.3, dia=0.6,
                leg_ok=lambda _a, _b, _half: True,
                seat_limit=8, allow_maze=False)

        vias = [op for op in operations if op[0] == "via"]
        self.assertEqual([(op[2], op[3]) for op in vias],
                         [(0.25, 0.35), (0.25, 0.35)])
        self.assertTrue(calls)

    def test_bridge_reserves_pofv_geometry_for_offset_from_bare_endpoint(self):
        import pcbnew
        import cec_fr

        board = _board([], edge=(0, 0, 8, 4))
        settings = board.GetDesignSettings()
        settings.m_ViasMinSize = pcbnew.FromMM(0.50)
        settings.m_MinThroughDrill = pcbnew.FromMM(0.30)
        settings.m_ViasMinAnnularWidth = pcbnew.FromMM(0.10)
        start = pcbnew.VECTOR2I_MM(1.0, 2.0)
        end = pcbnew.VECTOR2I_MM(7.0, 2.0)
        calls = []

        def via_clear(_board, at, diameter, _clearance, _nets, **kwargs):
            calls.append((diameter, kwargs.get("drill_nm")))
            return True

        with mock.patch.object(
                cec_fr._fab, "board_profile_name",
                return_value="jlcpcb_6l_pofv_signal"), \
                mock.patch.object(
                    cec_fr._fab, "via_at_pad_conflicts",
                    return_value=(None, [])), \
                mock.patch.object(cec_fr, "_via_spot_clear",
                                  side_effect=via_clear), \
                mock.patch.object(cec_fr, "_guarded_lastmile_legs",
                                  return_value=[(start, end)]), \
                mock.patch.object(
                    cec_fr, "_guarded_profiled_lastmile_legs",
                    return_value=None):
            operations = cec_fr._lastmile_bridge(
                board, (start.x, start.y), {pcbnew.F_Cu},
                (end.x, end.y), {pcbnew.F_Cu},
                pcbnew.FromMM(0.25), 1, [pcbnew.B_Cu],
                pcbnew.FromMM(0.2), drill=0.20, dia=0.30,
                leg_ok=lambda _a, _b, _half: True,
                seat_limit=8, allow_maze=False)

        vias = [op for op in operations if op[0] == "via"]
        self.assertEqual([(op[2], op[3]) for op in vias],
                         [(0.30, 0.50), (0.30, 0.50)])
        # The bare endpoint itself is not a via-in-pad qualification, so its
        # origin candidate remains ordinary.  A selected filled/capped board
        # process may still use its profile geometry at a guarded offset
        # dogbone seat.
        self.assertEqual(calls[0],
                         (pcbnew.FromMM(0.50), pcbnew.FromMM(0.30)))
        self.assertIn(
            (pcbnew.FromMM(0.35), pcbnew.FromMM(0.25)), calls)

    def test_bridge_clamps_offset_vias_to_board_drc_minima(self):
        import pcbnew
        import cec_fr

        board = _board([], edge=(0, 0, 8, 4))
        settings = board.GetDesignSettings()
        settings.m_ViasMinSize = pcbnew.FromMM(0.50)
        settings.m_MinThroughDrill = pcbnew.FromMM(0.30)
        settings.m_ViasMinAnnularWidth = pcbnew.FromMM(0.10)
        start = pcbnew.VECTOR2I_MM(1.0, 2.0)
        end = pcbnew.VECTOR2I_MM(7.0, 2.0)

        def via_clear(_board, at, diameter, _clearance, _nets, **kwargs):
            # Refuse endpoint-origin seats so the ordinary offset dogbone
            # path is exercised.  Only board-legal geometry is accepted.
            is_origin = ((at.x, at.y) in {
                (start.x, start.y), (end.x, end.y)})
            return (not is_origin
                    and diameter == pcbnew.FromMM(0.50)
                    and kwargs.get("drill_nm") == pcbnew.FromMM(0.30))

        with mock.patch.object(
                cec_fr._fab, "board_profile_name", return_value=None), \
                mock.patch.object(cec_fr, "_via_spot_clear",
                                  side_effect=via_clear), \
                mock.patch.object(
                    cec_fr, "_guarded_profiled_lastmile_legs",
                    side_effect=lambda _board, a, b, width, *_args,
                    **_kwargs: [(a, b, width)]), \
                mock.patch.object(
                    cec_fr, "_guarded_lastmile_legs",
                    return_value=[(start, end)]):
            operations = cec_fr._lastmile_bridge(
                board, (start.x, start.y), {pcbnew.F_Cu},
                (end.x, end.y), {pcbnew.F_Cu},
                pcbnew.FromMM(0.25), 1, [pcbnew.B_Cu],
                pcbnew.FromMM(0.2), drill=0.20, dia=0.30,
                leg_ok=lambda _a, _b, _half: True,
                seat_limit=8, allow_maze=False)

        self.assertIsNotNone(operations)
        vias = [op for op in operations if op[0] == "via"]
        self.assertEqual([(op[2], op[3]) for op in vias],
                         [(0.30, 0.50), (0.30, 0.50)])

    def test_bridge_seat_ladder_clears_passive_ring_and_power_trunk(self):
        import pcbnew
        import cec_fr

        board = _board([], edge=(0, 0, 10, 10))
        start = pcbnew.VECTOR2I_MM(1.0, 3.0)
        end = pcbnew.VECTOR2I_MM(9.0, 3.0)
        qualified = {
            (start.x, start.y + pcbnew.FromMM(3.0)),
            (end.x, end.y + pcbnew.FromMM(3.0)),
        }

        with mock.patch.object(
                cec_fr._fab, "board_profile_name", return_value=None), \
                mock.patch.object(
                    cec_fr, "_via_spot_clear",
                    side_effect=lambda _board, at, *_args, **_kwargs:
                    (at.x, at.y) in qualified), \
                mock.patch.object(
                    cec_fr, "_guarded_profiled_lastmile_legs",
                    side_effect=lambda _board, a, b, width, *_args,
                    **_kwargs: [(a, b, width)]), \
                mock.patch.object(
                    cec_fr, "_guarded_lastmile_legs",
                    side_effect=lambda _board, a, b, *_args, **_kwargs:
                    [(a, b)]):
            operations = cec_fr._lastmile_bridge(
                board, (start.x, start.y), {pcbnew.F_Cu},
                (end.x, end.y), {pcbnew.F_Cu},
                pcbnew.FromMM(0.25), 1, [pcbnew.B_Cu],
                pcbnew.FromMM(0.2), drill=0.3, dia=0.6,
                leg_ok=lambda _a, _b, _half: True,
                seat_limit=8, allow_maze=False)

        self.assertIsNotNone(operations)
        vias = [op for op in operations if op[0] == "via"]
        self.assertEqual({(op[1].x, op[1].y) for op in vias}, qualified)

    def test_bridge_seat_ladder_samples_eighth_millimetre_window(self):
        import pcbnew
        import cec_fr

        board = _board([], edge=(0, 0, 10, 6))
        start = pcbnew.VECTOR2I_MM(1.0, 2.0)
        end = pcbnew.VECTOR2I_MM(9.0, 2.0)
        qualified = {
            (start.x, start.y + pcbnew.FromMM(0.625)),
            (end.x, end.y + pcbnew.FromMM(0.625)),
        }
        with mock.patch.object(
                cec_fr._fab, "board_profile_name", return_value=None), \
                mock.patch.object(
                    cec_fr, "_via_spot_clear",
                    side_effect=lambda _board, at, *_args, **_kwargs:
                    (at.x, at.y) in qualified), \
                mock.patch.object(
                    cec_fr, "_guarded_profiled_lastmile_legs",
                    side_effect=lambda _board, a, b, width, *_args,
                    **_kwargs: [(a, b, width)]), \
                mock.patch.object(
                    cec_fr, "_guarded_lastmile_legs",
                    side_effect=lambda _board, a, b, *_args, **_kwargs:
                    [(a, b)]):
            operations = cec_fr._lastmile_bridge(
                board, (start.x, start.y), {pcbnew.F_Cu},
                (end.x, end.y), {pcbnew.F_Cu},
                pcbnew.FromMM(0.2), 1, [pcbnew.B_Cu],
                pcbnew.FromMM(0.2), drill=0.3, dia=0.6,
                leg_ok=lambda _a, _b, _half: True,
                seat_limit=8, allow_maze=False)

        self.assertIsNotNone(operations)
        self.assertEqual(
            {(op[1].x, op[1].y) for op in operations if op[0] == "via"},
            qualified)

    def test_endpoint_owned_plane_is_never_a_bridge_signal_layer(self):
        import pcbnew
        import cec_fr

        board = _board([], edge=(0, 0, 10, 6))
        board.SetLayerName(pcbnew.In1_Cu, "GND")
        layers = cec_fr._endpoint_bridge_layers(
            board, {pcbnew.F_Cu, pcbnew.In1_Cu}, {pcbnew.F_Cu},
            [pcbnew.B_Cu])
        self.assertEqual(layers, [])

    def test_authoritative_netclass_width_beats_unrouted_fallback(self):
        import cec_fr

        board = _board([(2, 2, "/A"), (5, 2, "/A")])
        result = cec_fr.synthesize_lastmile(
            board, min_w=0.25,
            netclass_resolver=lambda _net: {
                "track_width": 0.2, "clearance": 0.2,
                "via_diameter": 0.6, "via_drill": 0.3,
            })

        self.assertEqual(result["closed"], 1, result)
        self.assertEqual(
            {round(track.GetWidth() / 1e6, 3)
             for track in board.GetTracks()
             if track.GetClass() == "PCB_TRACK"},
            {0.2})

    def test_canonical_path_helper_covers_octants(self):
        import cec_fr
        for end in ((3, 2), (-3, 2), (2, -3), (-2, -3), (3, 3), (0, 3)):
            with self.subTest(end=end):
                paths = cec_fr._canonical_45_xy_paths((0, 0), end)
                self.assertTrue(paths)
                for path in paths:
                    self.assertEqual(path[0], (0, 0))
                    self.assertEqual(path[-1], end)
                    for (ax, ay), (bx, by) in zip(path, path[1:]):
                        dx, dy = abs(bx - ax), abs(by - ay)
                        self.assertTrue(dx == 0 or dy == 0 or dx == dy,
                                        "every candidate leg must be octilinear")

    def test_far_gap_untouched(self):
        import cec_fr
        b = _board([(5, 5, "/A"), (25, 5, "/A")])
        r = cec_fr.synthesize_lastmile(b)
        self.assertEqual(r["closed"], 0)
        self.assertGreaterEqual(r["far"], 1)
        self.assertEqual(r["far_details"][0]["net"], "/A")
        self.assertEqual(r["far_details"][0]["reason"],
                         "outside_completion_distance_budget")
        self.assertAlmostEqual(r["far_details"][0]["nearest_gap_mm"],
                               20.0, places=3)
        self.assertFalse(list(b.GetTracks()))

    def test_aggregate_wall_timeout_is_structured_and_non_mutating(self):
        import cec_fr

        board = _board([(5, 5, "/A"), (9, 5, "/A")])
        result = cec_fr.synthesize_lastmile(board, wall_timeout_s=0.0)

        self.assertTrue(result["timed_out"], result)
        self.assertEqual(result["timeout_s"], 0.0)
        self.assertEqual(
            result["timeout_detail"]["reason"],
            "aggregate_wall_clock_budget_exhausted")
        self.assertEqual(result["closed"], 0)
        self.assertFalse(list(board.GetTracks()))

    def test_per_net_timeout_skips_stubborn_net_without_starving_later_nets(self):
        import cec_fr

        board = _board([
            (5, 5, "/A"), (9, 5, "/A"),
            (5, 10, "/B"), (9, 10, "/B"),
        ])
        result = cec_fr.synthesize_lastmile(
            board, wall_timeout_s=10.0, per_net_timeout_s=0.0)

        self.assertFalse(result["timed_out"], result)
        self.assertEqual(
            {row["net"] for row in result["net_timeouts"]},
            {"/A", "/B"})
        self.assertEqual(result["closed"], 0)
        self.assertFalse(list(board.GetTracks()))

    def test_blocked_straight_takes_bridge_or_L(self):
        # a foreign pad dead-center between the pair blocks the straight; the
        # completer must still close (L around it, or the over-the-top bridge)
        import cec_fr
        b = _board([(5, 5, "/A"), (9, 5, "/A"), (7, 5, "/BLOCK")])
        r = cec_fr.synthesize_lastmile(b)
        self.assertEqual(r["closed"], 1,
                         "blocked straight must fall through to L/bridge")

    def test_blocked_straight_takes_guarded_same_layer_detour(self):
        import cec_fr

        b = _board([(5, 5, "/A"), (9, 5, "/A"), (7, 5, "/BLOCK")])
        with mock.patch.object(cec_fr, "_lastmile_bridge", return_value=None):
            result = cec_fr.synthesize_lastmile(b)
        self.assertEqual(result["closed"], 1)
        tracks = [t for t in b.GetTracks() if t.GetNetname() == "/A"]
        self.assertGreaterEqual(len(tracks), 3,
                                "the closure should route around the blocker")
        self.assertTrue(any(t.GetStart().y != t.GetEnd().y for t in tracks))

    def test_edge_hugging_gap_refused(self):
        # pads 0.3mm from the outline: any leg would violate the 0.5 edge rule
        import cec_fr
        b = _board([(1.0, 0.3, "/A"), (3.0, 0.3, "/A")],
                   edge=(0, 0, 20, 10))
        r = cec_fr.synthesize_lastmile(b)
        self.assertEqual(r["closed"], 0,
                         "edge-hugging closure must be refused (the +4 "
                         "copper_edge regression class)")
        certificate = r["refused_details"][0]["certificate"]
        self.assertEqual(
            certificate["conclusion"],
            "bounded_search_exhausted_not_global_impossibility")
        self.assertEqual({row["ref"] for row in certificate["endpoints"]},
                         {"X1", "X2"})
        self.assertTrue(any(not layer["direct_edge_clear"]
                            for layer in certificate["layers"]))

    def test_refusal_certificate_names_exact_foreign_pad_blocker(self):
        import pcbnew
        import cec_fr

        board = _board([(5, 5, "/A"), (9, 5, "/A"),
                        (7, 5, "/BLOCK")])
        certificate = cec_fr._lastmile_refusal_certificate(
            board, pcbnew.VECTOR2I_MM(5, 5), pcbnew.VECTOR2I_MM(9, 5),
            pcbnew.FromMM(0.25), pcbnew.FromMM(0.25),
            board.GetNetcodeFromNetname("/A"), [pcbnew.F_Cu],
            endpoint_a={"kind": "pad", "ref": "X1", "pad": ""},
            endpoint_b={"kind": "pad", "ref": "X2", "pad": ""})
        blockers = certificate["layers"][0]["direct_blockers"]
        self.assertTrue(any(row.get("kind") == "pad"
                            and row.get("ref") == "X3"
                            and row.get("net") == "/BLOCK"
                            for row in blockers), blockers)

    def test_refusal_certificate_preserves_each_escape_ray_blocker(self):
        import pcbnew
        import cec_fr

        board = _board([(5, 5, "/A"), (9, 5, "/A"),
                        (6.0, 5, "/BLOCK")])
        certificate = cec_fr._lastmile_refusal_certificate(
            board, pcbnew.VECTOR2I_MM(5, 5), pcbnew.VECTOR2I_MM(9, 5),
            pcbnew.FromMM(0.25), pcbnew.FromMM(0.20),
            board.GetNetcodeFromNetname("/A"), [pcbnew.F_Cu],
            start_escape=(pcbnew.FromMM(0.20), pcbnew.FromMM(1.5)))
        endpoint = certificate["layers"][0]["endpoint_escape"][0]
        self.assertEqual(len(endpoint["ray_details"]), 8)
        east = next(row for row in endpoint["ray_details"]
                    if row["direction"] == "E")
        self.assertEqual(east["status"], "foreign_copper_blocked")
        self.assertTrue(any(row.get("kind") == "pad"
                            and row.get("ref") == "X3"
                            for row in east["blockers"]), east)

    def test_internal_edge_cutout_is_not_crossed(self):
        import pcbnew
        import cec_fr

        b = _board([(5, 5, "/A"), (9, 5, "/A")],
                   edge=(0, 0, 20, 10))
        fp = pcbnew.FOOTPRINT(b)
        fp.SetReference("DL1")
        cut = pcbnew.PCB_SHAPE(fp)
        cut.SetShape(pcbnew.SHAPE_T_RECT)
        cut.SetStart(pcbnew.VECTOR2I_MM(6.0, 4.0))
        cut.SetEnd(pcbnew.VECTOR2I_MM(8.0, 6.0))
        cut.SetLayer(pcbnew.Edge_Cuts)
        fp.Add(cut)
        b.Add(fp)
        with mock.patch.object(cec_fr, "_lastmile_bridge", return_value=None):
            result = cec_fr.synthesize_lastmile(b)
        self.assertEqual(result["closed"], 1,
                         "a guarded dogleg may route around the LED hole")
        tracks = [t for t in b.GetTracks() if t.GetNetname() == "/A"]
        self.assertTrue(tracks)
        self.assertTrue(all(
            cec_fr._edge_leg_clear(b, t.GetStart(), t.GetEnd(),
                                   t.GetWidth() // 2)
            for t in tracks),
            "post-route last-mile must honor reverse-LED holes")

    def test_bridge_uses_final_netclass_via_geometry(self):
        """A bridge seat must be judged at the size it will ship, not at the
        smaller router default that normalize_netclass_geometry later grows."""
        import pcbnew
        import cec_fr

        b = _board([(5, 5, "/POWER"), (7, 5, "/POWER")])
        pads = [p for fp in b.GetFootprints() for p in fp.Pads()]
        back = pcbnew.LSET()
        back.AddLayer(pcbnew.B_Cu)
        pads[1].SetLayerSet(back)  # no common layer: force over-the-top bridge

        with mock.patch.object(cec_fr, "_lastmile_bridge", return_value=None) as bridge:
            cec_fr.synthesize_lastmile(
                b, netclass_resolver=lambda _net: {
                    "via_diameter": 0.8, "via_drill": 0.4},
                wall_timeout_s=10.0)
        self.assertTrue(bridge.called)
        self.assertEqual(bridge.call_args.kwargs["dia"], 0.8)
        self.assertEqual(bridge.call_args.kwargs["drill"], 0.4)
        self.assertIsNotNone(
            bridge.call_args.kwargs["deadline_monotonic"])

    def test_local_power_bypass_links_only_power_class_and_locks(self):
        import cec_fr

        board = _bypass_board()
        resolve = lambda net: {  # noqa: E731 - compact test resolver
            "name": "Power" if net == "/POWER" else "Default",
            "track_width": 1.0 if net == "/POWER" else 0.25,
            "clearance": 0.25,
        }
        result = cec_fr.synthesize_local_power_bypass_links(
            board, netclass_resolver=resolve)

        self.assertEqual((result["pairs"], result["linked"],
                          result["refused"]), (1, 1, 0))
        power = [track for track in board.GetTracks()
                 if track.GetNetname() == "/POWER"]
        signal = [track for track in board.GetTracks()
                  if track.GetNetname() == "/SENSE"]
        self.assertTrue(power)
        self.assertFalse(signal, "Default-class signal RC capacitors are not "
                                 "pre-routed as power bypasses")
        self.assertTrue(all(track.IsLocked() for track in power))
        self.assertIn(int(1.0e6), {track.GetWidth() for track in power},
                      "the middle of a 4 mm power link keeps class width")
        self.assertIn(int(0.2e6), {track.GetWidth() for track in power},
                      "fine SMD endpoints use bounded neck-downs")

    def test_local_power_bypass_is_idempotent(self):
        import cec_fr

        board = _bypass_board()
        resolve = lambda net: {  # noqa: E731 - compact test resolver
            "track_width": 1.0 if net == "/POWER" else 0.25,
            "clearance": 0.25,
        }
        first = cec_fr.synthesize_local_power_bypass_links(
            board, netclass_resolver=resolve)
        count = len(list(board.GetTracks()))
        second = cec_fr.synthesize_local_power_bypass_links(
            board, netclass_resolver=resolve)

        self.assertEqual(first["linked"], 1)
        self.assertEqual(second["linked"], 0)
        self.assertEqual(len(list(board.GetTracks())), count)
        self.assertEqual(second["detail"][0]["status"], "already-connected")

    def test_local_power_bypass_uses_guarded_bridge_when_face_is_blocked(self):
        import pcbnew
        import cec_fr

        board = _bypass_board()
        resolve = lambda net: {  # noqa: E731 - compact test resolver
            "track_width": 1.0 if net == "/POWER" else 0.25,
            "clearance": 0.25,
            "via_diameter": 0.8, "via_drill": 0.4,
        }
        guarded = cec_fr._guarded_profiled_lastmile_legs

        def block_long_face_route(board_, start, end, width, layer, *args,
                                  **kwargs):
            if (layer == pcbnew.F_Cu
                    and math.hypot(end.x - start.x, end.y - start.y)
                    > int(3.0e6)):
                return None
            return guarded(board_, start, end, width, layer, *args, **kwargs)

        with mock.patch.object(cec_fr, "_guarded_profiled_lastmile_legs",
                               side_effect=block_long_face_route), \
                mock.patch.object(cec_fr, "_lastmile_bridge",
                                  wraps=cec_fr._lastmile_bridge) as bridge:
            result = cec_fr.synthesize_local_power_bypass_links(
                board, netclass_resolver=resolve)

        self.assertEqual((result["pairs"], result["linked"],
                          result["refused"]), (1, 1, 0))
        self.assertEqual(result["vias"], 2)
        power = [item for item in board.GetTracks()
                 if item.GetNetname() == "/POWER"]
        self.assertTrue(any(item.GetClass() == "PCB_VIA" for item in power))
        self.assertTrue(any(item.GetClass() != "PCB_VIA"
                            and item.GetLayer() != pcbnew.F_Cu
                            for item in power))
        self.assertTrue(all(item.IsLocked() for item in power))
        self.assertEqual(bridge.call_args.kwargs["seat_limit"], 48,
                         "local bypass repair expands the seat search")

    def test_local_signal_links_only_private_low_fanout_ic_network(self):
        import cec_fr

        board = _bypass_board()
        resolve = lambda net: {  # noqa: E731 - compact test resolver
            "track_width": 1.0 if net == "/POWER" else 0.20,
            "clearance": 0.20,
        }
        result = cec_fr.synthesize_local_signal_links(
            board, netclass_resolver=resolve)

        self.assertEqual((result["networks"], result["linked"],
                          result["refused"]), (1, 1, 0))
        signal = [track for track in board.GetTracks()
                  if track.GetNetname() == "/SENSE"]
        power = [track for track in board.GetTracks()
                 if track.GetNetname() == "/POWER"]
        self.assertTrue(signal)
        self.assertFalse(power, "distributed/power-width nets remain the "
                         "global router's responsibility")
        self.assertTrue(all(track.IsLocked() for track in signal))

    def test_local_signal_uses_guarded_bridge_when_face_escape_is_blocked(self):
        import pcbnew
        import cec_fr

        board = _bypass_board()
        resolve = lambda net: {  # noqa: E731 - compact test resolver
            "track_width": 1.0 if net == "/POWER" else 0.20,
            "clearance": 0.20,
            "via_diameter": 0.60, "via_drill": 0.30,
        }
        # Model a dense surface channel that has no guarded F.Cu route.  The
        # same collision-aware over-the-top primitive used by last-mile must
        # be tried before refusing a private local control net.
        guarded = cec_fr._guarded_profiled_lastmile_legs

        def block_long_face_route(board_, start, end, width, layer, *args,
                                  **kwargs):
            if (layer == pcbnew.F_Cu
                    and math.hypot(end.x - start.x, end.y - start.y)
                    > int(3.0e6)):
                return None
            return guarded(board_, start, end, width, layer, *args, **kwargs)

        with mock.patch.object(cec_fr, "_guarded_profiled_lastmile_legs",
                               side_effect=block_long_face_route), \
                mock.patch.object(cec_fr, "_lastmile_bridge",
                                  wraps=cec_fr._lastmile_bridge) as bridge:
            result = cec_fr.synthesize_local_signal_links(
                board, netclass_resolver=resolve)

        self.assertEqual((result["networks"], result["linked"],
                          result["refused"]), (1, 1, 0))
        self.assertEqual(result["vias"], 2)
        signal = [item for item in board.GetTracks()
                  if item.GetNetname() == "/SENSE"]
        self.assertTrue(any(item.GetClass() == "PCB_VIA" for item in signal))
        self.assertTrue(any(item.GetClass() != "PCB_VIA"
                            and item.GetLayer() != pcbnew.F_Cu
                            for item in signal))
        self.assertTrue(all(item.IsLocked() for item in signal))

    def test_local_signal_include_nets_limits_fail_driven_retry_scope(self):
        import cec_fr

        board = _bypass_board()
        resolve = lambda net: {  # noqa: E731 - compact test resolver
            "track_width": 1.0 if net == "/POWER" else 0.20,
            "clearance": 0.20,
        }
        excluded = cec_fr.synthesize_local_signal_links(
            board, netclass_resolver=resolve, include_nets={"/NOT_SENSE"})
        self.assertEqual((excluded["networks"], excluded["linked"]), (0, 0))
        self.assertFalse(list(board.GetTracks()))

        selected = cec_fr.synthesize_local_signal_links(
            board, netclass_resolver=resolve, include_nets={"/SENSE"})
        self.assertEqual((selected["networks"], selected["linked"],
                          selected["refused"]), (1, 1, 0))

    def test_layer_junction_via_heals_roundtrip_but_skips_tht(self):
        import pcbnew
        import cec_fr

        def fixture(with_pth=False):
            board = pcbnew.BOARD()
            board.SetCopperLayerCount(6)
            net = pcbnew.NETINFO_ITEM(board, "/PWR")
            board.Add(net)
            p0 = pcbnew.VECTOR2I_MM(5.0, 5.0)
            # Reproduce SES decimal round-trip drift: endpoints differ by
            # 0.00005 mm but are visually the same layer transition.
            for layer, end in ((pcbnew.F_Cu, pcbnew.VECTOR2I_MM(7.0, 5.0)),
                               (pcbnew.In2_Cu,
                                pcbnew.VECTOR2I_MM(7.00005, 5.00005))):
                track = pcbnew.PCB_TRACK(board)
                track.SetStart(p0 if layer == pcbnew.F_Cu else end)
                track.SetEnd(end if layer == pcbnew.F_Cu
                             else pcbnew.VECTOR2I_MM(9.0, 5.0))
                track.SetWidth(pcbnew.FromMM(0.5))
                track.SetLayer(layer)
                track.SetNet(net)
                board.Add(track)
            if with_pth:
                fp = pcbnew.FOOTPRINT(board)
                fp.SetReference("J1")
                pad = pcbnew.PAD(fp)
                pad.SetPadName("1")
                pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
                pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
                pad.SetSize(pcbnew.VECTOR2I_MM(1.2, 1.2))
                pad.SetDrillSize(pcbnew.VECTOR2I_MM(0.6, 0.6))
                pad.SetPosition(pcbnew.VECTOR2I_MM(7.0, 5.0))
                pad.SetLayerSet(pcbnew.PAD.PTHMask())
                pad.SetNet(net)
                fp.Add(pad)
                board.Add(fp)
            return board

        resolve = lambda _net: {"via_diameter": 0.8, "via_drill": 0.4,
                                "clearance": 0.2}
        board = fixture()
        repaired = cec_fr.synthesize_missing_layer_junction_vias(
            board, netclass_resolver=resolve)
        self.assertEqual((repaired["candidates"], repaired["added"],
                          repaired["refused"]), (1, 1, 0))
        self.assertEqual(len([item for item in board.GetTracks()
                              if item.GetClass() == "PCB_VIA"]), 1)

        tht_board = fixture(with_pth=True)
        skipped = cec_fr.synthesize_missing_layer_junction_vias(
            tht_board, netclass_resolver=resolve)
        self.assertEqual((skipped["candidates"], skipped["added"]), (0, 0))

    def test_pipeline_power_zone_split_islands_get_guarded_bridge(self):
        import pcbnew
        import cec_fr

        board = _board([], edge=(0, 0, 20, 20))
        net = pcbnew.NETINFO_ITEM(board, "/POWER")
        board.Add(net)
        zone = pcbnew.ZONE(board)
        zone.SetLayer(pcbnew.B_Cu)
        zone.SetNet(net)
        zone.SetZoneName("overunder:/POWER")
        outline = zone.Outline()
        outline.NewOutline()
        for x, y in ((5, 5), (15, 5), (15, 10), (5, 10)):
            outline.Append(int(x * 1e6), int(y * 1e6))
        filled = pcbnew.SHAPE_POLY_SET()
        for rect in (((5, 5), (9, 5), (9, 10), (5, 10)),
                     ((10, 5), (15, 5), (15, 10), (10, 10))):
            index = filled.NewOutline()
            for x, y in rect:
                filled.Outline(index).Append(int(x * 1e6), int(y * 1e6))
        zone.SetFilledPolysList(pcbnew.B_Cu, filled)
        zone.SetIsFilled(True)
        board.Add(zone)

        result = cec_fr.synthesize_pipeline_zone_island_bridges(
            board, netclass_resolver=lambda _net: {
                "track_width": 1.0, "clearance": 0.25})

        self.assertEqual((result["added"], result["refused"]), (1, 0))
        tracks = [track for track in board.GetTracks()
                  if track.GetNetname() == "/POWER"]
        self.assertTrue(tracks)
        self.assertTrue(all(track.GetLayer() == pcbnew.B_Cu
                            for track in tracks))

    def test_post_cleanup_zone_repair_reloads_refills_and_saves_artifact(self):
        import pcbnew
        import cec_fr

        board = _board([], edge=(0, 0, 20, 20))
        net = pcbnew.NETINFO_ITEM(board, "/POWER")
        board.Add(net)
        zone = pcbnew.ZONE(board)
        zone.SetLayer(pcbnew.B_Cu)
        zone.SetNet(net)
        zone.SetZoneName("overunder:/POWER")
        outline = zone.Outline()
        outline.NewOutline()
        for x, y in ((5, 5), (15, 5), (15, 10), (5, 10)):
            outline.Append(int(x * 1e6), int(y * 1e6))
        filled = pcbnew.SHAPE_POLY_SET()
        for rect in (((5, 5), (9, 5), (9, 10), (5, 10)),
                     ((10, 5), (15, 5), (15, 10), (10, 10))):
            index = filled.NewOutline()
            for x, y in rect:
                filled.Outline(index).Append(int(x * 1e6), int(y * 1e6))
        zone.SetFilledPolysList(pcbnew.B_Cu, filled)
        zone.SetIsFilled(True)
        board.Add(zone)

        with mock.patch.object(cec_fr.pcbnew, "LoadBoard",
                               return_value=board) as load, \
                mock.patch.object(cec_fr.pcbnew, "SaveBoard") as save:
            result = cec_fr.repair_post_cleanup_zone_islands(
                "final.kicad_pcb", netclass_resolver=lambda _net: {
                    "track_width": 1.0, "clearance": 0.25})

        self.assertEqual((result["added"], result["refused"]), (1, 0))
        load.assert_called_once_with("final.kicad_pcb")
        save.assert_called_once_with("final.kicad_pcb", board)
        self.assertTrue(any(track.GetNetname() == "/POWER"
                            for track in board.GetTracks()))

    def test_maze_shape_snapshot_matches_authoritative_foreign_guard(self):
        import pcbnew
        import cec_fr

        board = _board([(5, 5, "/A"), (7, 5, "/A"),
                        (6, 5, "/BLOCK")])
        start = pcbnew.VECTOR2I_MM(5.0, 5.0)
        blocked = pcbnew.VECTOR2I_MM(7.0, 5.0)
        clear = pcbnew.VECTOR2I_MM(5.0, 7.0)
        code = board.GetNetcodeFromNetname("/A")
        zones, copper = cec_fr._layer_foreign_shapes(
            board, pcbnew.F_Cu, {code})
        for end in (blocked, clear):
            with self.subTest(end=(end.x, end.y)):
                expected = cec_fr._tap_foreign_clear(
                    board, start, end, int(0.2e6), pcbnew.F_Cu,
                    int(0.2e6), {code})
                actual = cec_fr._snapshot_foreign_clear(
                    start, end, int(0.2e6), int(0.2e6), zones, copper)
                self.assertEqual(actual, expected)
                indexed = cec_fr._tap_foreign_clear(
                    board, start, end, int(0.2e6), pcbnew.F_Cu,
                    int(0.2e6), {code}, foreign_cache={})
                self.assertEqual(indexed, expected)

    def test_maze_shape_snapshot_honors_stricter_zone_local_clearance(self):
        import pcbnew
        import cec_fr

        board = _board([(2, 5, "/A"), (8, 5, "/A")],
                       edge=(0, 0, 10, 10))
        foreign = pcbnew.NETINFO_ITEM(board, "/BLOCK")
        board.Add(foreign)
        zone = pcbnew.ZONE(board)
        zone.SetLayer(pcbnew.F_Cu)
        zone.SetNet(foreign)
        zone.SetZoneName("pourplan:/BLOCK")
        zone.SetLocalClearance(int(0.5e6))
        outline = zone.Outline()
        outline.NewOutline()
        for x, y in ((4, 5.35), (6, 5.35), (6, 8), (4, 8)):
            outline.Append(int(x * 1e6), int(y * 1e6))
        board.Add(zone)

        start = pcbnew.VECTOR2I_MM(2.0, 5.0)
        end = pcbnew.VECTOR2I_MM(8.0, 5.0)
        code = board.GetNetcodeFromNetname("/A")
        zones, copper = cec_fr._layer_foreign_shapes(
            board, pcbnew.F_Cu, {code})

        # The route's own 0.20 mm rule would pass this 0.25 mm edge gap;
        # the foreign zone's explicit 0.50 mm rule is the controlling one.
        self.assertFalse(cec_fr._snapshot_foreign_clear(
            start, end, int(0.2e6), int(0.2e6), zones, copper))
        identified = cec_fr._identified_foreign_shape_indexes(
            board, pcbnew.F_Cu, {code})
        blockers = cec_fr._snapshot_foreign_blockers(
            start, end, int(0.2e6), int(0.2e6), *identified)
        self.assertTrue(any(
            row.get("kind") == "zone"
            and row.get("contact") == "zone_clearance"
            for row in blockers))

    def test_foreign_shape_index_is_reused_only_for_same_layer_and_exempt_net(self):
        import pcbnew
        import cec_fr

        board = _board([(5, 5, "/A"), (7, 5, "/A"),
                        (6, 5, "/BLOCK")])
        code_a = board.GetNetcodeFromNetname("/A")
        code_block = board.GetNetcodeFromNetname("/BLOCK")
        cache = {}
        with mock.patch.object(
                cec_fr, "_layer_foreign_shapes",
                wraps=cec_fr._layer_foreign_shapes) as snapshot:
            first = cec_fr._foreign_shape_indexes(
                board, pcbnew.F_Cu, {code_a}, cache=cache)
            second = cec_fr._foreign_shape_indexes(
                board, pcbnew.F_Cu, {code_a}, cache=cache)
            other_net = cec_fr._foreign_shape_indexes(
                board, pcbnew.F_Cu, {code_block}, cache=cache)
            other_layer = cec_fr._foreign_shape_indexes(
                board, pcbnew.B_Cu, {code_a}, cache=cache)

        self.assertIs(first, second)
        self.assertIsNot(first, other_net)
        self.assertIsNot(first, other_layer)
        self.assertEqual(snapshot.call_count, 3)

    def test_lastmile_guards_treat_copper_artwork_as_foreign(self):
        import pcbnew
        import cec_fr

        board = _board([(5, 5, "/A"), (9, 5, "/A")])
        logo = pcbnew.FOOTPRINT(board)
        logo.SetReference("LOGO1")
        shape = pcbnew.PCB_SHAPE(logo)
        shape.SetShape(pcbnew.SHAPE_T_RECT)
        shape.SetStart(pcbnew.VECTOR2I_MM(6.0, 4.0))
        shape.SetEnd(pcbnew.VECTOR2I_MM(8.0, 6.0))
        shape.SetLayer(pcbnew.B_Cu)
        logo.Add(shape)
        board.Add(logo)

        start = pcbnew.VECTOR2I_MM(5.0, 5.0)
        end = pcbnew.VECTOR2I_MM(9.0, 5.0)
        code = board.GetNetcodeFromNetname("/A")
        self.assertFalse(cec_fr._tap_foreign_clear(
            board, start, end, int(0.2e6), pcbnew.B_Cu,
            int(0.2e6), {code}))
        zones, copper = cec_fr._layer_foreign_shapes(
            board, pcbnew.B_Cu, {code})
        self.assertFalse(cec_fr._snapshot_foreign_clear(
            start, end, int(0.2e6), int(0.2e6), zones, copper))

    def test_lastmile_guards_apply_board_clearance_to_npth_holes(self):
        import pcbnew
        import cec_fr

        board = _board([(5, 5, "/A"), (9, 5, "/A")])
        board.GetDesignSettings().m_HoleClearance = pcbnew.FromMM(0.25)
        fixture = pcbnew.FOOTPRINT(board)
        fixture.SetReference("J1")
        hole = pcbnew.PAD(fixture)
        hole.SetNumber("H1")
        hole.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
        hole.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
        hole.SetSize(pcbnew.VECTOR2I_MM(1.0, 1.0))
        hole.SetDrillSize(pcbnew.VECTOR2I_MM(1.0, 1.0))
        hole.SetPosition(pcbnew.VECTOR2I_MM(7.0, 5.6))
        fixture.Add(hole)
        board.Add(fixture)

        start = pcbnew.VECTOR2I_MM(5.0, 5.0)
        end = pcbnew.VECTOR2I_MM(9.0, 5.0)
        code = board.GetNetcodeFromNetname("/A")
        self.assertFalse(cec_fr._tap_foreign_clear(
            board, start, end, pcbnew.FromMM(0.2), pcbnew.F_Cu,
            pcbnew.FromMM(0.2), {code}))
        zones, copper = cec_fr._layer_foreign_shapes(
            board, pcbnew.F_Cu, {code})
        self.assertFalse(cec_fr._snapshot_foreign_clear(
            start, end, pcbnew.FromMM(0.2), pcbnew.FromMM(0.2),
            zones, copper))
        identified = cec_fr._identified_foreign_shape_indexes(
            board, pcbnew.F_Cu, {code})
        blockers = cec_fr._snapshot_foreign_blockers(
            start, end, pcbnew.FromMM(0.2), pcbnew.FromMM(0.2),
            *identified)
        self.assertTrue(any(
            row.get("kind") == "npth_hole"
            and row.get("contact") == "hole_clearance"
            for row in blockers), blockers)

    def test_wave_plumbing(self):
        import cec_fresh_wave as w
        params = w.BOARD_PARAMS["hub-standard-rev2"]
        self.assertTrue(params.get("lastmile"))
        self.assertEqual(params.get("lastmile_attempts"), 4)
        self.assertEqual(params.get("lastmile_final_attempts"), 8)
        self.assertTrue(params.get("lastmile_final_winner"))
        import cec_synth_pipeline as csp
        with csp._oracle_env({**params, "lastmile_final": True}):
            self.assertEqual(os.environ.get("CEC_LASTMILE"), "1")
            self.assertEqual(os.environ.get("CEC_LASTMILE_ATTEMPTS"), "4")
            self.assertEqual(os.environ.get("CEC_LASTMILE_FINAL_ATTEMPTS"), "8")
            self.assertEqual(os.environ.get("CEC_LASTMILE_FINAL"), "1")
            self.assertEqual(os.environ.get("CEC_LASTMILE_FINAL_MAX_MM"), "100.0")
            self.assertEqual(os.environ.get(
                "CEC_LASTMILE_FINAL_MAZE_MAX_MM"), "100.0")
            self.assertEqual(os.environ.get(
                "CEC_LASTMILE_FINAL_MAZE_MARGIN_MM"), "8.0")
        self.assertNotEqual(os.environ.get("CEC_LASTMILE"), "1")

    def test_final_completion_filter_excludes_vital_topologies(self):
        import cec_fr
        board = _board([
            (2, 2, "/GPIO"), (3, 2, "/GPIO"),
            (2, 3, "/USB_CC1"), (3, 3, "/USB_CC1"),
            (2, 4, "/USB_D_P"), (3, 4, "/USB_D_P"),
            (2, 5, "+3V3"), (3, 5, "+3V3"),
            (2, 6, "/CURRENT_SENSE"), (3, 6, "/CURRENT_SENSE"),
        ])
        eligible = cec_fr._ordinary_final_completion_nets(
            board, lambda _net: {"track_width": 0.2})
        self.assertIn("/GPIO", eligible)
        self.assertIn("/USB_CC1", eligible)
        self.assertNotIn("/USB_D_P", eligible)
        self.assertNotIn("+3V3", eligible)
        self.assertNotIn("/CURRENT_SENSE", eligible)

    def test_final_completion_ignores_default_diff_pair_dimensions(self):
        """KiCad's Default class has pair dimensions even for scalar nets."""
        import cec_fr
        board = _board([
            (2, 2, "/TEMP_HUB"), (3, 2, "/TEMP_HUB"),
            (2, 3, "/USB_D_P"), (3, 3, "/USB_D_P"),
        ])
        default_class = lambda _net: {
            "name": "Default", "track_width": 0.2,
            "diff_pair_width": 0.2, "diff_pair_gap": 0.25,
        }
        eligible = cec_fr._ordinary_final_completion_nets(
            board, default_class)
        self.assertEqual(eligible, ("/TEMP_HUB",))


if __name__ == "__main__":
    unittest.main()
