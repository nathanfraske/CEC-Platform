import math
import os
import sys
import time
import unittest
from unittest import mock


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import cec_precision_route as precision


class PrecisionFlowThroughTests(unittest.TestCase):
    def test_pair_endpoint_stations_group_adjacent_split_members(self):
        import pcbnew

        board = pcbnew.CreateEmptyBoard()
        nets = {}
        for name in ("/PAIR_P", "/PAIR_N"):
            net = pcbnew.NETINFO_ITEM(board, name)
            board.Add(net)
            nets[name] = net

        def add_ref(ref, rows):
            footprint = pcbnew.FOOTPRINT(board)
            footprint.SetReference(ref)
            for number, net_name, x, y in rows:
                pad = pcbnew.PAD(footprint)
                pad.SetPadName(number)
                pad.SetShape(pcbnew.PAD_SHAPE_RECT)
                pad.SetSize(pcbnew.VECTOR2I_MM(0.5, 0.5))
                pad.SetPosition(pcbnew.VECTOR2I_MM(x, y))
                pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
                pad.SetLayerSet(pcbnew.PAD.SMDMask())
                pad.SetNet(nets[net_name])
                footprint.Add(pad)
            board.Add(footprint)

        add_ref("U1", (("1", "/PAIR_P", 2.0, 9.8),
                       ("2", "/PAIR_N", 2.0, 10.2)))
        add_ref("R11", (("1", "/PAIR_P", 18.0, 9.8),))
        add_ref("R12", (("1", "/PAIR_N", 18.0, 10.2),))

        stations = precision._pair_endpoint_stations(
            board, {"p": "/PAIR_P", "n": "/PAIR_N"})

        self.assertEqual(len(stations), 2)
        self.assertIn({"U1"},
                      [set(row["physical_refs"]) for row in stations])
        split = next(row for row in stations
                     if row["kind"] == "split-member-footprints")
        self.assertEqual(set(split["physical_refs"]), {"R11", "R12"})
        self.assertAlmostEqual(split["member_separation_mm"], 0.4)
        self.assertEqual(split["member_axis"], [0.0, 1.0])
        self.assertEqual(split["p_center"], [18.0, 9.8])
        self.assertEqual(split["n_center"], [18.0, 10.2])
        self.assertAlmostEqual(split["member_pitch_mm"], 0.4)
        self.assertEqual(split["p_contacts"], [{
            "ref": "R11", "pad": "1", "point_mm": [18.0, 9.8]}])
        self.assertEqual(split["n_contacts"], [{
            "ref": "R12", "pad": "1", "point_mm": [18.0, 10.2]}])

    def test_precision_pair_transaction_rejects_perimeter_detour(self):
        import pcbnew

        board = pcbnew.CreateEmptyBoard()
        nets = {}
        for name in ("/PAIR_P", "/PAIR_N"):
            net = pcbnew.NETINFO_ITEM(board, name)
            board.Add(net)
            nets[name] = net
        for endpoint, x in enumerate((2.0, 18.0), start=1):
            footprint = pcbnew.FOOTPRINT(board)
            footprint.SetReference("J%d" % endpoint)
            for number, name, y in (
                    ("1", "/PAIR_P", 9.8),
                    ("2", "/PAIR_N", 10.2)):
                pad = pcbnew.PAD(footprint)
                pad.SetPadName(number)
                pad.SetShape(pcbnew.PAD_SHAPE_RECT)
                pad.SetSize(pcbnew.VECTOR2I_MM(0.5, 0.5))
                pad.SetPosition(pcbnew.VECTOR2I_MM(x, y))
                pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
                pad.SetLayerSet(pcbnew.PAD.SMDMask())
                pad.SetNet(nets[name])
                footprint.Add(pad)
            board.Add(footprint)
        for name, pad_y, detour_y in (
                ("/PAIR_P", 9.8, 0.0),
                ("/PAIR_N", 10.2, 0.4)):
            points = ((2.0, pad_y), (2.0, detour_y),
                      (18.0, detour_y), (18.0, pad_y))
            for start, end in zip(points, points[1:]):
                track = pcbnew.PCB_TRACK(board)
                track.SetStart(pcbnew.VECTOR2I_MM(*start))
                track.SetEnd(pcbnew.VECTOR2I_MM(*end))
                track.SetWidth(pcbnew.FromMM(0.2))
                track.SetLayer(pcbnew.F_Cu)
                track.SetNet(nets[name])
                board.Add(track)

        report = precision._pair_transaction_detour(
            board, {"p": "/PAIR_P", "n": "/PAIR_N"})

        self.assertFalse(report["ok"], report)
        self.assertTrue(all(row["ratio"] > report["limit"]
                            for row in report["members"]))
        pair = {"name": "TEST", "p": "/PAIR_P", "n": "/PAIR_N"}
        certificate = precision._pair_detour_failure_certificate(
            board, pair, report,
            {track.m_Uuid.AsString() for track in board.GetTracks()},
            precision._pair_endpoint_stations(board, pair),
            local_search={"selected": {"maximum_member_detour_ratio": 3.0}})
        self.assertEqual(certificate["classification"],
                         ["excessive_detour"])
        self.assertEqual(len(certificate["copper_witness"]), 6)
        self.assertEqual(set(certificate["endpoints"]), {"start", "end"})
        self.assertEqual(len(certificate["relief_vectors"]), 4)

    def test_pair_coupling_contract_matches_final_absolute_length_policy(self):
        can = {"kind": "can"}
        usb = {"kind": "usb"}

        short_can = precision._pair_coupling_contract(
            can, {"fraction": 0.0, "total_samples": 4},
            {"/CAN_H": 1.8, "/CAN_L": 2.0})
        long_can = precision._pair_coupling_contract(
            can, {"fraction": 0.0, "total_samples": 16},
            {"/CAN_H": 5.8, "/CAN_L": 8.6})
        usb_coverage = precision._pair_coupling_contract(
            usb, {"fraction": 0.846, "total_samples": 100},
            {"/USB_D_P": 64.8, "/USB_D_N": 66.1})

        self.assertTrue(short_can["ok"], short_can)
        self.assertFalse(long_can["ok"], long_can)
        self.assertTrue(usb_coverage["ok"], usb_coverage)
        self.assertEqual(long_can["minimum_coupled_coverage_pct"], 60.0)
        self.assertEqual(long_can["uncoupled_length_budget_mm"], 2.0)

        forced_local = precision._pair_coupling_contract(
            can, {"fraction": 0.0, "total_samples": 16},
            {"/CAN_H": 6.4, "/CAN_L": 6.2},
            endpoint_stations=[
                {"kind": "same-footprint-pair", "center": [0.0, 0.0]},
                {"kind": "split-member-footprints", "center": [4.0, 0.0]},
            ])
        self.assertTrue(forced_local["ok"], forced_local)
        self.assertTrue(forced_local["forced_endpoint_fanout"])
        self.assertEqual(forced_local["uncoupled_length_budget_mm"], 8.0)

    def test_short_pair_ribbon_normalizes_dissimilar_endpoint_pitch(self):
        pair = {"name": "CAN", "kind": "can",
                "p": "/CAN_H", "n": "/CAN_L",
                "width": 0.25, "gap": 0.25}

        rows = precision._short_pair_ribbon_candidates(
            pair,
            (43.76, 18.406), (46.474, 21.7028),
            (43.76, 19.676), (45.964, 23.5128))

        self.assertTrue(rows)
        selected = rows[0]
        self.assertTrue(selected["preferred_polarity"])
        self.assertTrue(selected["coupling_contract"]["ok"], selected)
        self.assertGreaterEqual(selected["coupling"]["coverage_pct"], 60.0)
        self.assertTrue(precision._polys_no_cross(
            selected["p"], selected["n"]))
        self.assertTrue(precision._pair_min_clear(
            selected["p"], selected["n"], 1, 1, 0.25, 0.25,
            strict_pair_gap=True))
        self.assertLess(abs(selected["p_length_mm"]
                            - selected["n_length_mm"]), 0.05)

    def test_pair_geometry_never_undercuts_class_clearance(self):
        width, gap = precision._pair_geometry({
            "usb": {"diff_width": 0.20, "diff_gap": 0.13,
                    "clearance": 0.20}}, "usb")
        self.assertEqual(width, 0.20)
        self.assertEqual(gap, 0.20)

    def test_pair_geometry_preserves_wider_authored_gap(self):
        _width, gap = precision._pair_geometry({
            "usb": {"diff_width": 0.20, "diff_gap": 0.25,
                    "clearance": 0.20}}, "usb")
        self.assertEqual(gap, 0.25)

    def test_reserved_corridor_uses_exact_segment_intersection(self):
        avoid = ((0.0, 1.5, 0.4, 1.9, "POWER"),)

        # The diagonal's bounding box overlaps POWER, but the copper passes
        # well outside its lower-right corner.
        self.assertIsNone(precision._crosses_avoid(
            ((0.0, 0.0), (2.0, 2.0)), avoid, 0.0))
        self.assertEqual(precision._crosses_avoid(
            ((0.0, 1.7), (2.0, 1.7)), avoid, 0.0), "POWER")

    def test_reserved_corridor_failure_retains_exact_hit_geometry(self):
        avoid = ((1.0, 1.5, 3.0, 1.9, "POWER", "F.Cu"),)

        hits = precision._crosses_avoid_details(
            ((0.0, 1.7), (4.0, 1.7)), avoid, 0.2)

        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["reservation"], "POWER")
        self.assertEqual(hits[0]["layer"], "F.Cu")
        self.assertEqual(hits[0]["segment_mm"],
                         [[0.0, 1.7], [4.0, 1.7]])
        self.assertEqual(hits[0]["inflated_rect_mm"],
                         [0.9, 1.4, 3.1, 2.0])

    def test_pair_failure_certificate_names_barrier_and_portal_vectors(self):
        reservation_hit = {
            "reservation": "/RAIL", "layer": "F.Cu",
            "segment_mm": [[0.0, 0.0], [4.0, 0.0]],
            "rect_mm": [1.0, -0.1, 3.0, 0.1],
            "inflated_rect_mm": [0.875, -0.225, 3.125, 0.225],
            "route_width_mm": 0.25,
        }
        portal = {"shallow": {"portal_evidence": {
            "screened": {
                "start:+1": {
                    "checked": 2, "accepted": 0,
                    "rejection_counts": {"blocked": 2},
                    "nearest_rejected": [{
                        "portal": {"center": [0.5, 0.5]},
                        "reason": "blocked"}],
                },
                "start:-1": {
                    "checked": 2, "accepted": 0,
                    "rejection_counts": {"blocked": 2}},
                "end:+1": {
                    "checked": 2, "accepted": 0,
                    "rejection_counts": {"blocked": 2}},
                "end:-1": {
                    "checked": 2, "accepted": 0,
                    "rejection_counts": {"blocked": 2}},
            }}}}

        certificate = precision._pair_route_failure_certificate(
            {"name": "PAIR", "p": "/P", "n": "/N"},
            ((0.0, 0.0), (4.0, 0.0),
             (0.0, 0.5), (4.0, 0.5)),
            layer="F.Cu", width=0.25, gap=0.25, clearance=0.2,
            short_pair_refusal={
                "refused": "entered reservation /RAIL",
                "reservation_hits": [reservation_hit]},
            portal_refusal=portal,
            conventional_diagnostics={
                "middle_guard_refused": 3,
                "reservation_hits": [reservation_hit]},
            grid_failure_diagnostics=[{
                "grid": {"status": "grid_exhausted",
                         "frontier_gap_mm": 1.5,
                         "nearest_frontier_mm": [2.5, 0.25]}}],
            corridor_rejects={"/RAIL"})

        self.assertIn("reservation_barrier",
                      certificate["classification"])
        self.assertIn("endpoint_escape_refused",
                      certificate["classification"])
        self.assertIn("middle_guard_refused",
                      certificate["classification"])
        self.assertEqual(certificate["reservation_owners"], ["/RAIL"])
        self.assertGreater(
            certificate["reservation_barriers"][0]
            ["projected_normal_displacement"]["minimum_mm"], 0.0)
        self.assertTrue(certificate["endpoints"]["start"]
                        ["nearest_rejected_portals"])
        self.assertEqual(len(certificate["relief_vectors"]), 4)

    def test_tagged_reservations_only_block_their_copper_layer(self):
        avoid = (
            (0.0, 1.5, 2.0, 1.9, "FRONT_POWER", "F.Cu"),
            (0.0, 3.5, 2.0, 3.9, "INNER_POWER", "In2.Cu"),
        )

        front = precision._avoid_for_layer(avoid, "F.Cu")
        inner = precision._avoid_for_layer(avoid, "In2.Cu")
        back = precision._avoid_for_layer(avoid, "B.Cu")

        self.assertEqual(len(front), 1)
        self.assertEqual(len(inner), 1)
        self.assertEqual(back, ())
        self.assertEqual(precision._crosses_avoid(
            ((0.0, 1.7), (2.0, 1.7)), front, 0.0), "FRONT_POWER")
        self.assertIsNone(precision._crosses_avoid(
            ((0.0, 1.7), (2.0, 1.7)), inner, 0.0))

    def test_precision_consumes_only_authoritative_corridor_keepouts(self):
        avoid = precision.corridor_avoid_from_hints([
            {"name": "corr_SENSEC1_LO", "x0": 1, "y0": 2,
             "x1": 3, "y1": 4, "layers": ("F.Cu",)},
            {"name": "board_edge_top", "x0": 0, "y0": 0,
             "x1": 10, "y1": 1},
            {"name": "corr_incomplete", "x0": 0},
        ])

        self.assertEqual(
            avoid, ((1.0, 2.0, 3.0, 4.0, "corr_SENSEC1_LO"),))

    def test_authoritative_pour_adapter_uses_checker_geometry(self):
        with mock.patch.object(
                precision.cec_constraints, "high_current_pour_regions",
                return_value=[{
                    "net": "/SENSEC1_LO", "layer": "F.Cu",
                    "x0": 9.45, "y0": 25.7625,
                    "x1": 31.9012, "y1": 43.85,
                }]):
            avoid = precision.pour_avoid_from_board("board.kicad_pcb")
        self.assertEqual(
            avoid,
            ((9.45, 25.7625, 31.9012, 43.85,
              "pour_SENSEC1_LO_F.Cu"),))

    def test_hierarchical_can_pair_is_discovered_by_unique_leaf(self):
        class Net:
            def __init__(self, name):
                self.name = name

            def GetNetname(self):
                return self.name

        class Nets:
            def values(self):
                return [
                    Net("/CAN + PORTS/CAN_H"),
                    Net("/CAN + PORTS/CAN_L"),
                    Net("/CAN_RX"), Net("/CAN_TX"),
                ]

        class NetInfo:
            def NetsByNetcode(self):
                return Nets()

        class Board:
            def GetNetInfo(self):
                return NetInfo()

        with mock.patch.object(precision, "_netclass_geometry",
                               return_value={}), \
                mock.patch.object(
                    precision.cec_score.Rules, "from_board",
                    return_value=type("R", (), {"diff_pairs": []})()):
            pairs = precision.derive_coupled_pairs(
                "neutral.kicad_pcb", board=Board())
        self.assertIn({
            "name": "CAN", "kind": "can",
            "p": "/CAN + PORTS/CAN_H",
            "n": "/CAN + PORTS/CAN_L",
            "width": 0.25, "gap": 0.20, "ztarget": 120.0,
        }, pairs)

    def test_ambiguous_hierarchical_can_leaf_is_not_guessed(self):
        class Net:
            def __init__(self, name):
                self.name = name

            def GetNetname(self):
                return self.name

        class Nets:
            def values(self):
                return [Net("/A/CAN_H"), Net("/B/CAN_H"),
                        Net("/A/CAN_L")]

        class Board:
            def GetNetInfo(self):
                return type("I", (), {"NetsByNetcode": lambda _self: Nets()})()

        with mock.patch.object(precision, "_netclass_geometry",
                               return_value={}), \
                mock.patch.object(
                    precision.cec_score.Rules, "from_board",
                    return_value=type("R", (), {"diff_pairs": []})()):
            pairs = precision.derive_coupled_pairs(
                "neutral.kicad_pcb", board=Board())
        self.assertFalse(any(row["kind"] == "can" for row in pairs))

    def test_connector_side_can_suffix_is_a_distinct_coupled_pair(self):
        class Net:
            def __init__(self, name):
                self.name = name

            def GetNetname(self):
                return self.name

        class Nets:
            def values(self):
                return [Net("/CAN_H"), Net("/CAN_L"),
                        Net("/CAN_H_J1"), Net("/CAN_L_J1")]

        class Board:
            def GetNetInfo(self):
                return type("I", (), {"NetsByNetcode":
                                      lambda _self: Nets()})()

        with mock.patch.object(precision, "_netclass_geometry",
                               return_value={}), \
                mock.patch.object(
                    precision.cec_score.Rules, "from_board",
                    return_value=type("R", (), {"diff_pairs": []})()):
            pairs = precision.derive_coupled_pairs(
                "neutral.kicad_pcb", board=Board())
        self.assertIn({
            "name": "CAN_J1", "kind": "can",
            "p": "/CAN_H_J1", "n": "/CAN_L_J1",
            "width": 0.25, "gap": 0.20, "ztarget": 120.0,
        }, pairs)

    def test_pad_escape_rejects_connected_hairpin_and_ranks_shortest(self):
        direct = [(0.0, 0.0), (10.0, 0.0)]
        monotonic = [(0.0, 0.0), (3.0, 1.0), (10.0, 0.0)]
        hairpin = [(0.0, 0.0), (-3.0, 0.0), (10.0, 0.0)]
        reversal = [(0.0, 0.0), (7.0, 1.0), (5.0, 0.0)]

        self.assertIsNone(precision._escape_candidate_quality(hairpin))
        self.assertIsNone(precision._escape_candidate_quality(reversal))
        self.assertLess(precision._escape_candidate_quality(direct),
                        precision._escape_candidate_quality(monotonic))

    def test_pair_polyline_rejects_only_reverse_bends(self):
        self.assertTrue(precision._polyline_has_reverse_bend(
            [(0.0, 0.0), (-1.0, 0.0), (3.0, 0.0)]))
        self.assertFalse(precision._polyline_has_reverse_bend(
            [(0.0, 0.0), (1.0, 0.0), (1.0, 2.0), (0.0, 2.0)]))

    def test_generated_covered_track_is_dropped_without_touching_other_copper(self):
        import pcbnew

        board = pcbnew.BOARD()
        net = pcbnew.NETINFO_ITEM(board, "PAIR_P")
        other_net = pcbnew.NETINFO_ITEM(board, "OTHER")
        board.Add(net); board.Add(other_net)

        def add_track(net_item, start, end, width=0.25):
            track = pcbnew.PCB_TRACK(board)
            track.SetStart(pcbnew.VECTOR2I_MM(*start))
            track.SetEnd(pcbnew.VECTOR2I_MM(*end))
            track.SetWidth(pcbnew.FromMM(width))
            track.SetLayer(pcbnew.F_Cu)
            track.SetNet(net_item)
            board.Add(track)
            return track

        long_track = add_track(net, (1.0, 1.0), (1.0, 5.0))
        covered = add_track(net, (1.0, 3.0), (1.0, 4.0))
        covered_narrow = add_track(
            net, (1.0, 2.0), (1.0, 2.5), width=0.20)
        partial = add_track(net, (1.0, 4.5), (1.0, 6.0))
        different_width = add_track(net, (1.0, 3.0), (1.0, 4.0), 0.30)
        different_net = add_track(other_net, (1.0, 3.0), (1.0, 4.0))
        scope = {item.m_Uuid.AsString() for item in board.GetTracks()}

        report = precision._drop_fully_covered_tracks(board, scope)
        remaining = {item.m_Uuid.AsString() for item in board.GetTracks()}

        self.assertEqual(report["removed_count"], 2)
        self.assertNotIn(covered.m_Uuid.AsString(), remaining)
        self.assertNotIn(covered_narrow.m_Uuid.AsString(), remaining)
        for item in (long_track, partial, different_width, different_net):
            self.assertIn(item.m_Uuid.AsString(), remaining)

    def test_generated_track_can_be_covered_by_prior_priority_copper(self):
        import pcbnew

        board = pcbnew.BOARD()
        net = pcbnew.NETINFO_ITEM(board, "PAIR_P")
        board.Add(net)

        def add_track(start, end, width):
            track = pcbnew.PCB_TRACK(board)
            track.SetStart(pcbnew.VECTOR2I_MM(*start))
            track.SetEnd(pcbnew.VECTOR2I_MM(*end))
            track.SetWidth(pcbnew.FromMM(width))
            track.SetLayer(pcbnew.F_Cu)
            track.SetNet(net)
            board.Add(track)
            return track

        priority = add_track((1.0, 1.0), (5.0, 1.0), 0.25)
        generated = add_track((1.0, 1.0), (2.0, 1.0), 0.20)
        report = precision._drop_fully_covered_tracks(
            board, {generated.m_Uuid.AsString()})

        remaining = {item.m_Uuid.AsString() for item in board.GetTracks()}
        self.assertEqual(report["removed_count"], 1)
        self.assertIn(priority.m_Uuid.AsString(), remaining)
        self.assertNotIn(generated.m_Uuid.AsString(), remaining)

    def test_track_template_replay_preserves_exact_geometry_without_uuid(self):
        import pcbnew

        source = pcbnew.BOARD()
        source_net = pcbnew.NETINFO_ITEM(source, "PAIR_P")
        source.Add(source_net)
        original = pcbnew.PCB_TRACK(source)
        original.SetStart(pcbnew.VECTOR2I_MM(1.25, 2.5))
        original.SetEnd(pcbnew.VECTOR2I_MM(6.75, 8.0))
        original.SetWidth(pcbnew.FromMM(0.25))
        original.SetLayer(pcbnew.In2_Cu)
        original.SetNet(source_net)
        original.SetLocked(True)
        source.Add(original)
        template = precision._capture_track_template(
            source, {original.m_Uuid.AsString()})

        target = pcbnew.BOARD()
        target.Add(pcbnew.NETINFO_ITEM(target, "PAIR_P"))
        created = precision._replay_track_template(target, template)
        replayed = list(target.GetTracks())

        self.assertEqual(len(created), 1)
        self.assertEqual(len(replayed), 1)
        self.assertNotEqual(replayed[0].m_Uuid.AsString(),
                            original.m_Uuid.AsString())
        self.assertEqual(replayed[0].GetStart(), original.GetStart())
        self.assertEqual(replayed[0].GetEnd(), original.GetEnd())
        self.assertEqual(replayed[0].GetWidth(), original.GetWidth())
        self.assertEqual(replayed[0].GetLayer(), original.GetLayer())
        self.assertTrue(replayed[0].IsLocked())

    def test_joint_escape_routes_swapped_pad_order_without_crossing(self):
        # The coupled lane reaches the package with P left of N while the two
        # package pads expose P right of N. Independent shortest escapes cross.
        # The atomic endpoint solver must take one member around the end and
        # keep every emitted corner chamfered.
        result = precision._joint_endpoint_escape(
            (20.9136, 30.035), (21.2436, 30.035),
            (21.4786, 28.785), (20.6786, 28.785),
            width=0.20, gap=0.13,
            segment_clear=lambda _a, _b: True,
            max_detour=4.0)
        self.assertIsNotNone(result)
        p_path, n_path = result
        self.assertTrue(precision._polys_no_cross(p_path, n_path))
        self.assertTrue(precision._pair_min_clear(
            p_path, n_path, -1, -1, 0.20, 0.13))
        self.assertFalse(precision._polyline_has_reverse_bend(p_path))
        self.assertFalse(precision._polyline_has_reverse_bend(n_path))
        for path in (p_path, n_path):
            for a, b, c in zip(path, path[1:], path[2:]):
                va = (b[0] - a[0], b[1] - a[1])
                vb = (c[0] - b[0], c[1] - b[1])
                # A true bend may be 45 degrees, never a hard 90.
                if abs(va[0] * vb[1] - va[1] * vb[0]) > 1e-9:
                    self.assertNotAlmostEqual(
                        va[0] * vb[0] + va[1] * vb[1], 0.0)

    def test_joint_escape_treats_skew_limit_as_bound_not_zero_target(self):
        p_path, n_path = precision._joint_endpoint_escape(
            (0.0, 0.0), (0.0, 1.0),
            (10.0, 0.0), (8.0, 1.0),
            width=0.25, gap=0.20,
            segment_clear=lambda _a, _b: True,
            max_detour=4.0, max_skew=4.0)

        self.assertEqual(p_path, [(0.0, 0.0), (10.0, 0.0)])
        self.assertEqual(n_path, [(0.0, 1.0), (8.0, 1.0)])

    def test_joint_escape_score_prefers_member_detour_bound_over_shorter_sum(self):
        # Candidate A has the shorter aggregate, but one member violates the
        # final 2x transaction gate. Candidate B is slightly longer in total
        # and keeps both members within the same physical bound.
        one_long_member = precision._bounded_pair_choice_score(
            5.0, 8.1, 4.0, 4.0, skew=3.1, max_skew=4.0,
            heading_shortfall=0.0)
        balanced = precision._bounded_pair_choice_score(
            7.0, 7.0, 4.0, 4.0, skew=0.0, max_skew=4.0,
            heading_shortfall=0.0)

        self.assertLess(balanced, one_long_member)
        self.assertGreater(sum((7.0, 7.0)), sum((5.0, 8.1)))

    def test_connector_breakout_budget_scales_but_stays_bounded(self):
        self.assertEqual(
            precision._pair_escape_budget((0.0, 0.0), (0.5, 0.0)),
            6.0)
        self.assertAlmostEqual(
            precision._pair_escape_budget((0.0, 0.0), (4.58, 0.0)),
            6.87)
        self.assertEqual(
            precision._pair_escape_budget((0.0, 0.0), (100.0, 0.0)),
            12.0)

    def test_flow_through_schedules_congested_leg_first(self):
        class Position:
            def __init__(self, x, y):
                self.x = int(x * precision.MM)
                self.y = int(y * precision.MM)

        class Pad:
            def GetNetCode(self):
                return 99

            def GetPosition(self):
                return Position(5.0, 10.2)

        class Footprint:
            def Pads(self):
                return [Pad()]

        class Board:
            def GetNetcodeFromNetname(self, name):
                return {"P": 1, "N": 2}[name]

            def GetFootprints(self):
                return [Footprint()]

            def GetTracks(self):
                return []

        pair = {"p": "P", "n": "N", "width": 0.2, "gap": 0.13}
        open_leg = ((0.0, 0.0), (10.0, 0.0),
                    (0.0, 0.5), (10.0, 0.5))
        congested_leg = ((0.0, 10.0), (10.0, 10.0),
                         (0.0, 10.5), (10.0, 10.5))

        scheduled = precision._scheduled_flow_legs(
            Board(), pair, [open_leg, congested_leg])

        self.assertEqual([row[0] for row in scheduled], [1, 0])
        self.assertEqual(scheduled[0][2][0], 1)

    def test_fair_subdeadline_reserves_time_for_remaining_legs(self):
        self.assertEqual(
            precision._fair_subdeadline(120.0, 2, now=20.0), 70.0)
        self.assertEqual(
            precision._fair_subdeadline(120.0, 1, now=20.0), 120.0)

    def test_dissimilar_pin_fields_reduce_to_aligned_octilinear_portals(self):
        plan = precision._paired_portal_candidates(
            (0.0, -2.0), (0.0, 2.0),
            (20.0, -0.5), (20.0, 0.5),
            width=0.25, gap=0.20)

        self.assertEqual(plan["axis"], (1.0, 0.0))
        self.assertEqual(plan["normal"], (0.0, 1.0))
        self.assertEqual(plan["preferred_signs"], {
            "start": -1, "end": -1})
        for sign in (1, -1):
            start = plan["by_sign"][sign]["start"][0]
            end = plan["by_sign"][sign]["end"][0]
            self.assertAlmostEqual(
                precision._dist(start["p"], start["n"]), 0.45)
            self.assertAlmostEqual(
                precision._dist(end["p"], end["n"]), 0.45)
            start_lane = (start["p"][1] - start["n"][1])
            end_lane = (end["p"][1] - end["n"][1])
            self.assertGreater(start_lane * end_lane, 0.0)
            self.assertGreater(start["center"][0], 0.0)
            self.assertLess(end["center"][0], 20.0)
            self.assertTrue(any(
                row["lateral_mm"] == 3.0
                for row in plan["by_sign"][sign]["start"]))
            self.assertTrue(any(
                row["lead_mm"] == 5.5
                for row in plan["by_sign"][sign]["start"]))

    def test_transition_portals_widen_for_real_via_lands(self):
        plan = precision._paired_portal_candidates(
            (0.0, -2.0), (0.0, 2.0),
            (20.0, -0.5), (20.0, 0.5),
            width=0.20, gap=0.13, portal_separation=0.70)

        self.assertEqual(plan["portal_separation_mm"], 0.70)
        for sign in (1, -1):
            for side in ("start", "end"):
                row = plan["by_sign"][sign][side][0]
                self.assertAlmostEqual(
                    precision._dist(row["p"], row["n"]), 0.70)

    def test_return_via_search_prefers_flank_then_package_side(self):
        axis = (1.0, 0.0)
        corridor_half = 0.82

        self.assertEqual(
            precision._return_via_route_rank(
                (0.0, 0.9), axis, corridor_half, "start")[0],
            0)
        self.assertEqual(
            precision._return_via_route_rank(
                (-0.9, 0.0), axis, corridor_half, "start")[0],
            1)
        self.assertEqual(
            precision._return_via_route_rank(
                (0.9, 0.0), axis, corridor_half, "start")[0],
            2)
        self.assertEqual(
            precision._return_via_route_rank(
                (0.9, 0.0), axis, corridor_half, "end")[0],
            1)

    def test_dissimilar_pinfield_uses_shallow_portal_beam_before_legacy_fan(self):
        class Board:
            def GetLayerID(self, _layer):
                return 0

            def GetNetcodeFromNetname(self, net):
                return {"P": 1, "N": 2}[net]

        pair = {"name": "BUS", "kind": "can", "p": "P", "n": "N",
                "width": 0.25, "gap": 0.20, "ztarget": 120.0,
                "via_diameter": 0.80, "via_drill": 0.40}
        endpoints = ((0.0, -2.0), (20.0, -0.25),
                     (0.0, 2.0), (20.0, 0.25))
        with mock.patch.object(
                precision, "_route_coupled_via_portals",
                return_value={"route_mode": "paired-portals"}) as portal:
            report = precision.route_coupled_pair(
                Board(), pair, endpoints=endpoints,
                pair_grid=True, layer="F.Cu")

        self.assertEqual(report["portal_search_phase"], "shallow-first")
        self.assertEqual(portal.call_args.kwargs["max_grid_visited"], 10000)
        self.assertEqual(
            portal.call_args.kwargs["signal_via_diameter_mm"], 0.80)
        self.assertEqual(
            portal.call_args.kwargs["signal_via_drill_mm"], 0.40)
        self.assertEqual(portal.call_count, 1)

    def test_surface_exhaustion_escalates_to_atomic_multilayer_portal(self):
        class Board:
            def GetLayerID(self, _layer):
                return 0

            def GetNetcodeFromNetname(self, net):
                return {"P": 1, "N": 2}[net]

            def GetFileName(self):
                return "synthetic.kicad_pcb"

        pair = {"name": "BUS", "kind": "usb", "p": "P", "n": "N",
                "width": 0.20, "gap": 0.13, "ztarget": 90.0}
        endpoints = ((0.0, -1.0), (20.0, -0.2),
                     (0.0, 1.0), (20.0, 0.2))

        def portal(_board, _pair, _endpoints, **kwargs):
            if kwargs.get("middle_layer") == "In2.Cu":
                return {"route_mode": "paired-portals-atomic-layer-transition"}
            return {"refused": "surface corridor exhausted"}

        with mock.patch.object(precision, "_route_coupled_via_portals",
                               side_effect=portal) as routed, \
                mock.patch.object(precision.cec_fr, "_edge_leg_clear",
                                  return_value=False), \
                mock.patch.object(
                    precision.cec_fab_profile, "referenced_signal_layers",
                    return_value=("F.Cu", "In2.Cu")):
            absolute_deadline = time.monotonic() + 20.0
            report = precision.route_coupled_pair(
                Board(), pair, endpoints=endpoints,
                pair_grid=True, layer="F.Cu",
                deadline=absolute_deadline)

        self.assertEqual(report["portal_search_phase"], "atomic-multilayer")
        self.assertEqual(report["layer_transition_attempts"][-1], {
            "layer": "In2.Cu", "status": "accepted"})
        self.assertTrue(any(
            call.kwargs.get("middle_layer") == "In2.Cu"
            for call in routed.call_args_list))
        surface_deadlines = [
            call.kwargs["deadline"] for call in routed.call_args_list
            if call.kwargs.get("middle_layer") is None]
        inner_deadline = next(
            call.kwargs["deadline"] for call in routed.call_args_list
            if call.kwargs.get("middle_layer") == "In2.Cu")
        self.assertTrue(all(value < absolute_deadline
                            for value in surface_deadlines))
        self.assertGreater(inner_deadline, max(surface_deadlines))

    def test_atomic_multilayer_portal_owns_signal_and_return_vias(self):
        import pcbnew

        board = pcbnew.BOARD()
        settings = board.GetDesignSettings()
        settings.m_MinThroughDrill = pcbnew.FromMM(0.30)
        settings.m_ViasMinSize = pcbnew.FromMM(0.50)
        settings.m_ViasMinAnnularWidth = pcbnew.FromMM(0.10)
        for a, b in (((0, 0), (30, 0)), ((30, 0), (30, 20)),
                     ((30, 20), (0, 20)), ((0, 20), (0, 0))):
            edge = pcbnew.PCB_SHAPE(board)
            edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
            edge.SetStart(pcbnew.VECTOR2I_MM(*a))
            edge.SetEnd(pcbnew.VECTOR2I_MM(*b))
            edge.SetLayer(pcbnew.Edge_Cuts)
            board.Add(edge)
        for name in ("GND", "P", "N"):
            board.Add(pcbnew.NETINFO_ITEM(board, name))
        board.SetCopperLayerCount(6)
        pair = {"name": "BUS", "kind": "usb", "p": "P", "n": "N",
                "width": 0.20, "gap": 0.13, "ztarget": 90.0}
        # Deliberately use dissimilar terminal pitches.  The local connector
        # dogbone may need an orthogonal (subsequently chamfered) handoff; a
        # spread ratio must not turn that quality preference into a hard ban.
        endpoints = ((3.0, 9.0), (27.0, 7.0),
                     (3.0, 11.0), (27.0, 13.0))
        stub = {"route_mode": "paired-terminal-stub", "segments": 2,
                "length_mm": 2.0, "coupled_len_mm": 2.0,
                "coupled_coverage_pct": 100.0}
        middle = {"route_mode": "octilinear-grid", "segments": 2,
                  "length_mm": 15.0, "coupled_len_mm": 15.0,
                  "coupled_coverage_pct": 100.0}
        quality = {"ok": True, "blocking_count": 0, "issues": []}
        coupling = {"coverage_pct": 100.0}

        with mock.patch.object(precision, "_route_paired_stub",
                               return_value=stub) as route_stub, \
                mock.patch.object(precision, "route_coupled_pair",
                                  return_value=middle), \
                mock.patch.object(precision.cec_fr, "_via_spot_clear",
                                  return_value=True), \
                mock.patch.object(precision, "_pair_graph_geometry",
                                  return_value={"ok": True, "issues": []}), \
                mock.patch.object(precision, "_pair_coupling_summary",
                                  return_value=coupling), \
                mock.patch("cec_route_quality.analyze_board",
                           return_value=quality), \
                mock.patch.object(precision.cec_impedance,
                                  "stackup_for_board",
                                  return_value={"h_mm": 0.1, "er": 4.1,
                                                "t_mm": 0.035}), \
                mock.patch.object(precision.cec_impedance,
                                  "zdiff_edge_coupled", return_value=90.0):
            report = precision._route_coupled_via_portals(
                board, pair, endpoints, layer="F.Cu",
                middle_layer="In2.Cu", max_fanins_per_side=1,
                max_portal_pairs=1)

        self.assertEqual(
            report["route_mode"],
            "paired-portals-atomic-layer-transition")
        self.assertGreater(report["portal_evidence"]["pinfield_spread_ratio"],
                           2.0)
        self.assertEqual(report["portal_evidence"][
            "minimum_handoff_alignment"], 0.0)
        self.assertTrue(all(
            call.kwargs["minimum_end_heading_alignment"] == 0.0
            for call in route_stub.call_args_list))
        vias = [item for item in board.GetTracks()
                if item.GetClass() == "PCB_VIA"]
        self.assertEqual(sum(via.GetNetname() in ("P", "N") for via in vias), 4)
        self.assertEqual(sum(via.GetNetname() == "GND" for via in vias), 2)
        self.assertTrue(all(
            via.GetDrillValue() >= pcbnew.FromMM(0.30)
            for via in vias))
        self.assertEqual(report["portal_evidence"]["signal_via"]["drill_mm"],
                         0.30)
        self.assertEqual(
            report["portal_evidence"]["signal_via"]["pair_spacing_mm"],
            0.75)
        self.assertEqual(len(report["transitions"]), 2)
        for transition in report["transitions"]:
            center = tuple((p + n) / 2.0 for p, n in zip(
                transition["p_at_mm"], transition["n_at_mm"]))
            return_at = transition["return_at_mm"]
            # This fixture routes horizontally. A reference return belongs
            # beside the pair field, never directly in the future corridor.
            self.assertGreater(
                abs(return_at[1] - center[1]),
                abs(return_at[0] - center[0]))
            returns = transition["return_vias_at_mm"]
            self.assertTrue(returns)
            for signal in (transition["p_at_mm"], transition["n_at_mm"]):
                self.assertLessEqual(min(
                    math.dist(signal, ground) for ground in returns), 1.5)

    def test_endpoint_pofv_routes_critical_pair_before_return_field(self):
        import pcbnew

        board = pcbnew.CreateEmptyBoard()
        board.SetCopperLayerCount(6)
        nets = {}
        for name in ("GND", "P", "N"):
            net = pcbnew.NETINFO_ITEM(board, name)
            board.Add(net)
            nets[name] = net

        def add_pad(ref, number, net_name, point, *, through=False):
            footprint = pcbnew.FOOTPRINT(board)
            footprint.SetReference(ref)
            pad = pcbnew.PAD(footprint)
            pad.SetPadName(number)
            pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetSize(pcbnew.VECTOR2I_MM(0.8, 0.8))
            pad.SetPosition(pcbnew.VECTOR2I_MM(*point))
            pad.SetNet(nets[net_name])
            if through:
                pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
                pad.SetLayerSet(pcbnew.LSET.AllCuMask())
            else:
                pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
                pad.SetLayerSet(pcbnew.PAD.SMDMask())
            footprint.Add(pad)
            board.Add(footprint)

        add_pad("RP", "1", "P", (3.0, 5.0))
        add_pad("RN", "1", "N", (3.0, 5.8))
        add_pad("J1P", "1", "P", (17.0, 5.0), through=True)
        add_pad("J1N", "1", "N", (17.0, 5.8), through=True)
        pair = {"name": "BUS", "kind": "can", "p": "P", "n": "N",
                "width": 0.2, "gap": 0.2}
        endpoints = ((3.0, 5.0), (17.0, 5.0),
                     (3.0, 5.8), (17.0, 5.8))
        events = []
        return_reaches = []

        def routed(*_args, **_kwargs):
            events.append("route")
            return {"route_mode": "paired-portals-shared-centreline"}

        def returns(*_args, **kwargs):
            events.append("returns")
            return_reaches.append(kwargs["return_reach_mm"])
            return [], "covered"

        with mock.patch.object(
                precision.cec_fab_profile, "board_profile_name",
                return_value="TEST"), \
                mock.patch.dict(
                    precision.cec_fab_profile.PROFILES,
                    {"TEST": {"pofv": True}}, clear=False), \
                mock.patch.object(
                    precision.cec_fab_profile, "preferred_pofv_geometry",
                    return_value=(0.35, 0.25)), \
                mock.patch.object(
                    precision.cec_fab_profile,
                    "board_legal_through_via_geometry",
                    return_value=(0.5, 0.3, {"test": True})), \
                mock.patch.object(
                    precision.cec_fab_profile, "pofv_dimensions",
                    return_value=(True, "test process qualified")), \
                mock.patch.object(
                    precision.cec_fab_profile, "via_at_pad_conflicts",
                    return_value=(None, [{"qualified": True}])), \
                mock.patch.object(
                    precision.cec_fr, "_via_spot_clear", return_value=True), \
                mock.patch.object(
                    precision, "route_coupled_pair", side_effect=routed), \
                mock.patch.object(
                    precision, "_add_pair_transition_returns",
                    side_effect=returns):
            report = precision._route_coupled_endpoint_pofv(
                board, pair, endpoints, target_layer="In2.Cu")

        self.assertFalse(report.get("refused"), report)
        self.assertEqual(events, ["route", "returns"])
        self.assertEqual(return_reaches, [1.5])
        self.assertTrue(report["route_mode"].startswith(
            "paired-pofv-endpoint-"))
        signal_vias = [item for item in board.GetTracks()
                       if item.GetClass() == "PCB_VIA"
                       and item.GetNetname() in ("P", "N")]
        self.assertEqual(len(signal_vias), 2)
        self.assertTrue(all(
            via.GetWidth() == pcbnew.FromMM(0.35)
            and via.GetDrillValue() == pcbnew.FromMM(0.25)
            for via in signal_vias))
        self.assertTrue(report["pofv"]["qualified_process_exception"])

    def test_future_pair_reservation_suppresses_only_shared_series_endpoint(self):
        current = {"name": "BUS_IN", "p": "P_IN", "n": "N_IN",
                   "width": 0.2, "gap": 0.2}
        future = {"name": "BUS_OUT", "p": "P_OUT", "n": "N_OUT",
                  "width": 0.2, "gap": 0.2}
        current_stations = [{
            "kind": "split-member-footprints", "physical_refs": ["R1", "R2"],
            "center": [5.0, 5.0]}]
        future_stations = [{
            "kind": "split-member-footprints", "physical_refs": ["R2", "R1"],
            "center": [5.2, 5.0]}]
        future_endpoints = ((5.0, 4.8), (15.0, 4.8),
                            (5.0, 5.2), (15.0, 5.2))
        diagnostics = {}

        def stations(_board, pair):
            return current_stations if pair is current else future_stations

        with mock.patch.object(precision, "_pair_endpoint_stations",
                               side_effect=stations), \
                mock.patch.object(precision, "_flow_through_pair_legs",
                                  return_value=([future_endpoints], [])):
            rows = precision._future_pair_launch_reservations(
                object(), [future], current_pair=current,
                diagnostics=diagnostics)

        self.assertEqual(len(rows), 1)
        self.assertIn(":target", rows[0][4])
        self.assertEqual(
            diagnostics["suppressed_shared_support_count"], 1)
        self.assertIn(":source", diagnostics[
            "suppressed_shared_support"][0]["reservation"])

    def test_successful_pair_closes_and_owns_reversible_connector_lands(self):
        import pcbnew

        board = pcbnew.BOARD()
        for a, b in (((0, 0), (20, 0)), ((20, 0), (20, 15)),
                     ((20, 15), (0, 15)), ((0, 15), (0, 0))):
            edge = pcbnew.PCB_SHAPE(board)
            edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
            edge.SetStart(pcbnew.VECTOR2I_MM(*a))
            edge.SetEnd(pcbnew.VECTOR2I_MM(*b))
            edge.SetLayer(pcbnew.Edge_Cuts)
            board.Add(edge)
        p_net = pcbnew.NETINFO_ITEM(board, "/USB_D_P")
        n_net = pcbnew.NETINFO_ITEM(board, "/USB_D_N")
        gnd_net = pcbnew.NETINFO_ITEM(board, "GND")
        board.Add(p_net); board.Add(n_net); board.Add(gnd_net)
        props = board.GetProperties()
        props["CEC_FAB_PROFILE"] = "jlcpcb_6l_pofv_signal"
        board.SetProperties(props)
        layers = pcbnew.LSET(); layers.AddLayer(pcbnew.F_Cu)

        def add_pad(footprint, number, net, x, y):
            pad = pcbnew.PAD(footprint)
            pad.SetNumber(number)
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetSize(pcbnew.VECTOR2I_MM(0.3, 1.15))
            pad.SetPosition(pcbnew.VECTOR2I_MM(x, y))
            pad.SetLayerSet(layers); pad.SetNet(net); footprint.Add(pad)
            return pad

        connector = pcbnew.FOOTPRINT(board); connector.SetReference("J_USB")
        pads = {
            "B7": add_pad(connector, "B7", n_net, 4.5, 10.0),
            "A6": add_pad(connector, "A6", p_net, 5.0, 10.0),
            "A7": add_pad(connector, "A7", n_net, 5.5, 10.0),
            "B6": add_pad(connector, "B6", p_net, 6.0, 10.0),
        }
        board.Add(connector)
        remote = pcbnew.FOOTPRINT(board); remote.SetReference("U1")
        remote_p = add_pad(remote, "14", p_net, 6.0, 2.0)
        remote_n = add_pad(remote, "13", n_net, 5.5, 2.0)
        board.Add(remote)

        def route_selected_terminal(board_, pair, **_kwargs):
            for net, start, end in (
                    (p_net, pads["B6"], remote_p),
                    (n_net, pads["A7"], remote_n)):
                track = pcbnew.PCB_TRACK(board_)
                track.SetStart(start.GetPosition())
                track.SetEnd(end.GetPosition())
                track.SetWidth(pcbnew.FromMM(0.2))
                track.SetLayer(pcbnew.F_Cu)
                track.SetNet(net); board_.Add(track)
            return {"name": pair["name"], "p": pair["p"],
                    "n": pair["n"], "segments": 2}

        pair = {"name": "USB", "kind": "usb", "p": "/USB_D_P",
                "n": "/USB_D_N", "width": 0.2, "gap": 0.34,
                "ztarget": 90.0}
        with mock.patch.object(precision, "derive_coupled_pairs",
                               return_value=[pair]), \
                mock.patch.object(precision, "_flow_through_pair_legs",
                                  return_value=None), \
                mock.patch.object(precision, "route_coupled_pair",
                                  side_effect=route_selected_terminal):
            report = precision.precision_route_board(
                board, board_path="dummy.kicad_pcb", do_kelvin=False)

        routed = report["pairs"]["routed"]
        self.assertEqual(len(routed), 1)
        self.assertTrue(routed[0]["fully_owned"])
        self.assertGreaterEqual(
            routed[0]["local_pad_closure"]["pair_linked"], 2)
        # Interleaved duplicate lands plus two already-owned southbound trunks
        # cannot both use a legal one-layer U.  The generic atomic fallback
        # keeps one surface fanout and bridges its mate on another signal
        # layer instead of accepting a P/N overlap or covered backtrack.
        self.assertGreaterEqual(
            routed[0]["local_pad_closure"]["vias"], 2)
        self.assertGreaterEqual(sum(
            row.get("return_vias", 0)
            for row in routed[0]["local_pad_closure"]["detail"]), 2)
        self.assertTrue(routed[0]["post_closure_geometry"]["ok"])
        self.assertTrue(report["route_quality"]["ok"])
        self.assertNotIn("GND", report["locked_nets"])
        self.assertEqual(
            precision.cec_fr.owned_locked_nets_board(board),
            {"/USB_D_P", "/USB_D_N"})

    def test_grid_pair_routes_around_internal_edge_cutout(self):
        import pcbnew

        board = pcbnew.BOARD()
        for a, b in (((0, 0), (30, 0)), ((30, 0), (30, 20)),
                     ((30, 20), (0, 20)), ((0, 20), (0, 0))):
            edge = pcbnew.PCB_SHAPE(board)
            edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
            edge.SetStart(pcbnew.VECTOR2I_MM(*a))
            edge.SetEnd(pcbnew.VECTOR2I_MM(*b))
            edge.SetLayer(pcbnew.Edge_Cuts)
            board.Add(edge)
        footprint = pcbnew.FOOTPRINT(board)
        footprint.SetReference("DL1")
        cutout = pcbnew.PCB_SHAPE(footprint)
        cutout.SetShape(pcbnew.SHAPE_T_RECT)
        cutout.SetStart(pcbnew.VECTOR2I_MM(8.0, 8.0))
        cutout.SetEnd(pcbnew.VECTOR2I_MM(12.0, 12.0))
        cutout.SetLayer(pcbnew.Edge_Cuts)
        footprint.Add(cutout)
        board.Add(footprint)

        shape_cache = {}
        with mock.patch.object(
                precision.cec_fr, "_layer_foreign_shapes",
                wraps=precision.cec_fr._layer_foreign_shapes) as shapes:
            result = precision._grid_coupled_path(
                board,
                start_center=(2.0, 10.0), end_center=(28.0, 10.0),
                p_start=(2.0, 9.75), n_start=(2.0, 10.25),
                p_end=(28.0, 9.75), n_end=(28.0, 10.25),
                layer_id=pcbnew.F_Cu, width=0.20, gap=0.34,
                clearance=0.20, own=set(),
                foreign_shape_cache=shape_cache,
            )
            repeated = precision._grid_coupled_path(
                board,
                start_center=(2.0, 10.0), end_center=(28.0, 10.0),
                p_start=(2.0, 9.75), n_start=(2.0, 10.25),
                p_end=(28.0, 9.75), n_end=(28.0, 10.25),
                layer_id=pcbnew.F_Cu, width=0.20, gap=0.34,
                clearance=0.20, own=set(),
                foreign_shape_cache=shape_cache,
            )
        self.assertIsNotNone(repeated)
        self.assertEqual(shapes.call_count, 1)
        self.assertIsNotNone(result)
        p_points, n_points, _length = result
        for points in (p_points, n_points):
            self.assertTrue(all(
                precision.cec_fr._edge_leg_clear(
                    board, precision._v(*a), precision._v(*b),
                    precision._nm(0.20) // 2, edge_mm=0.5)
                for a, b in zip(points, points[1:])))

    def test_wide_via_portal_tapers_to_nominal_pair_pitch(self):
        p_middle = [(0.0, 0.165), (1.0, 0.165), (3.0, 0.165)]
        n_middle = [(0.0, -0.165), (1.0, -0.165),
                    (3.0, -0.165)]

        taper = precision._portal_pair_taper_escape(
            (0.0, 0.35), (0.0, -0.35), p_middle, n_middle,
            width=0.20, gap=0.13,
            segment_clear=lambda _a, _b: True)

        self.assertIsNotNone(taper)
        self.assertEqual(taper["middle_index"], 1)
        self.assertEqual(taper["p"][0], (0.0, 0.35))
        self.assertEqual(taper["n"][0], (0.0, -0.35))
        self.assertTrue(precision._pair_min_clear(
            taper["p"], taper["n"], -1, -1, 0.20, 0.13,
            strict_pair_gap=True))

    def test_wide_via_portal_taper_fails_closed_on_blocked_member(self):
        taper = precision._portal_pair_taper_escape(
            (0.0, 0.35), (0.0, -0.35),
            [(0.0, 0.165), (1.0, 0.165)],
            [(0.0, -0.165), (1.0, -0.165)],
            width=0.20, gap=0.13,
            segment_clear=lambda a, _b: a[1] < 0.0)

        self.assertIsNone(taper)

    def test_usb_esd_array_becomes_two_ordered_pair_legs(self):
        p_net = "/USB_D_P"
        n_net = "/USB_D_N"
        pads = {
            p_net: [
                ("J_USB", "A6", (49.7, 67.855), None),
                ("J_USB", "B6", (50.7, 67.855), None),
                ("D6", "1", (51.75, 61.9625), None),
                ("D6", "6", (51.75, 64.2375), None),
                ("U1", "14", (34.25, 26.0), None),
            ],
            n_net: [
                ("J_USB", "A7", (50.2, 67.855), None),
                ("J_USB", "B7", (49.2, 67.855), None),
                ("D6", "3", (49.85, 61.9625), None),
                ("D6", "4", (49.85, 64.2375), None),
                ("U1", "13", (34.25, 24.73), None),
            ],
        }
        with mock.patch.object(precision, "_pads_on_net",
                               side_effect=lambda _board, net: pads[net]):
            result = precision._flow_through_pair_legs(
                object(), {"p": p_net, "n": n_net})

        legs, stations = result
        self.assertEqual(stations, ["D6"])
        self.assertEqual(legs, [
            ((50.7, 67.855), (51.75, 64.2375),
             (50.2, 67.855), (49.85, 64.2375)),
            ((51.75, 61.9625), (34.25, 26.0),
             (49.85, 61.9625), (34.25, 24.73)),
        ])

    def test_pair_without_inline_four_pad_station_uses_normal_router(self):
        pads = {
            "P": [("J", "1", (0.0, 0.0), None),
                  ("U", "1", (20.0, 0.5), None)],
            "N": [("J", "2", (0.0, 1.0), None),
                  ("U", "2", (20.0, 1.5), None)],
        }
        with mock.patch.object(precision, "_pads_on_net",
                               side_effect=lambda _board, net: pads[net]):
            self.assertIsNone(precision._flow_through_pair_legs(
                object(), {"p": "P", "n": "N"}))

    def test_pair_with_only_one_common_footprint_uses_normal_router(self):
        pads = {
            "P": [("J_P", "1", (0.0, 0.0), None),
                  ("U1", "1", (10.0, 0.0), None)],
            "N": [("J_N", "1", (0.0, 1.0), None),
                  ("U1", "2", (10.0, 1.0), None)],
        }
        with mock.patch.object(precision, "_pads_on_net",
                               side_effect=lambda _board, net: pads[net]):
            self.assertIsNone(precision._flow_through_pair_legs(
                object(), {"p": "P", "n": "N"}))

    def test_multidrop_pair_builds_deterministic_paired_terminal_mst(self):
        pads = {
            "P": [
                ("J1", "3", (0.0, 0.0), None),
                ("J2", "3", (10.0, 0.0), None),
                ("J3", "3", (20.0, 0.0), None),
                ("U1", "1", (10.0, 8.0), None),
            ],
            "N": [
                ("J1", "6", (0.0, 0.5), None),
                ("J2", "6", (10.0, 0.5), None),
                ("J3", "6", (20.0, 0.5), None),
                ("U1", "2", (10.0, 8.5), None),
            ],
        }
        with mock.patch.object(precision, "_pads_on_net",
                               side_effect=lambda _board, net: pads[net]):
            first = precision._multidrop_pair_legs(
                object(), {"p": "P", "n": "N"})
            second = precision._multidrop_pair_legs(
                object(), {"p": "P", "n": "N"})

        self.assertEqual(first, second)
        legs, refs, edges = first
        self.assertEqual(refs, ["J1", "J2", "J3", "U1"])
        self.assertEqual(len(legs), 3)
        self.assertEqual(
            {(row["a"], row["b"]) for row in edges},
            {("J1", "J2"), ("J2", "J3"), ("J2", "U1")})
        self.assertTrue(all(row["layers"] == ["F.Cu"] for row in edges))
        for p0, p1, n0, n1 in legs:
            self.assertAlmostEqual(
                precision._dist(p0, p1), precision._dist(n0, n1))

    def test_multidrop_plan_includes_split_member_terminal_footprints(self):
        pads = {
            "P": [
                ("J1", "1", (0.0, 0.0), None),
                ("J2", "1", (10.0, 0.0), None),
                ("J3", "1", (20.0, 0.0), None),
                ("R3", "1", (20.0, 5.0), None),
            ],
            "N": [
                ("J1", "2", (0.0, 0.45), None),
                ("J2", "2", (10.0, 0.45), None),
                ("J3", "2", (20.0, 0.45), None),
                ("R4", "1", (20.0, 6.0), None),
            ],
        }
        board = type("Board", (), {
            "GetFileName": lambda _self: "",
            "GetFootprints": lambda _self: [],
        })()
        with mock.patch.object(precision, "_pads_on_net",
                               side_effect=lambda _board, net: pads[net]), \
                mock.patch.object(
                    precision.cec_fab_profile,
                    "referenced_signal_layers",
                    return_value=("F.Cu", "B.Cu")):
            plan = precision._multidrop_pair_plan(
                board, {"p": "P", "n": "N"})

        self.assertIn("R3|R4", plan["terminals"])
        virtual = plan["ports"]["R3|R4"]
        self.assertEqual(virtual["p"], (20.0, 5.0))
        self.assertEqual(virtual["n"], (20.0, 6.0))
        self.assertEqual(virtual["terminal_kind"],
                         "split-member-footprints")
        fanout = next(
            row for row in plan["edges"]
            if "R3|R4" in (row["a"], row["b"]))
        self.assertTrue(fanout["bounded_terminal_fanout"])
        self.assertEqual(fanout["split_terminal_refs"], ["R3|R4"])
        self.assertEqual(fanout["terminal_fanout_limit_mm"], 8.0)

    def test_layered_multidrop_uses_pth_pad_as_layer_articulation(self):
        class Board:
            def GetTracks(self):
                return []

            def Remove(self, _item):
                raise AssertionError("nothing should be removed")

        pair = {"name": "BUS", "p": "P", "n": "N",
                "width": 0.25, "gap": 0.20}
        plan = {
            "terminals": ["U1", "J1", "J2"],
            "preferred_signal_layers": ["F.Cu", "B.Cu"],
            "ports": {
                "U1": {"p": (0.0, 0.0), "n": (0.0, 0.45),
                       "layers": ["F.Cu"], "through": False},
                "J1": {"p": (10.0, 0.0), "n": (10.0, 0.45),
                       "layers": ["F.Cu", "B.Cu"], "through": True},
                "J2": {"p": (20.0, 0.0), "n": (20.0, 0.45),
                       "layers": ["F.Cu", "B.Cu"], "through": True},
            },
            "edges": [
                {"a": "U1", "b": "J1", "length_mm": 10.0,
                 "layers": ["F.Cu"], "through_hole_edge": False},
                {"a": "J1", "b": "J2", "length_mm": 10.0,
                 "layers": ["B.Cu", "F.Cu"],
                 "through_hole_edge": True},
            ],
        }

        routed_layers = []

        def route_stub(_board, _pair, _endpoints, *, layer, **_kwargs):
            routed_layers.append(layer)
            return {"segments": 2, "length_mm": 10.0,
                    "coupled_len_mm": 10.0}

        with mock.patch.object(precision, "_route_paired_stub",
                               side_effect=route_stub), \
                mock.patch.object(precision, "_pair_graph_geometry",
                                  return_value={"ok": True, "issues": []}):
            report = precision._route_layered_multidrop_pair_tree(
                Board(), pair, plan)

        self.assertEqual(report["route_mode"],
                         "layered-paired-trunk-short-stub")
        self.assertEqual(set(routed_layers), {"F.Cu", "B.Cu"})
        self.assertEqual(routed_layers[:2], ["F.Cu", "B.Cu"])
        self.assertEqual(report["junctions"], {})
        self.assertEqual(
            [row["selected_layer"] for row in report["tree_edges"]],
            ["F.Cu", "B.Cu"])

    def test_layered_multidrop_inserts_one_stub_per_same_layer_junction(self):
        class Board:
            def GetTracks(self):
                return []

            def Remove(self, _item):
                raise AssertionError("nothing should be removed")

        pair = {"name": "BUS", "p": "P", "n": "N",
                "width": 0.25, "gap": 0.20}
        refs = ["J1", "J2", "J3", "J4"]
        plan = {
            "terminals": refs,
            "preferred_signal_layers": ["B.Cu"],
            "ports": {
                ref: {"p": (index * 10.0, 0.0),
                      "n": (index * 10.0, 0.45),
                      "center": (index * 10.0, 0.225),
                      "layers": ["B.Cu"], "through": True}
                for index, ref in enumerate(refs)
            },
            "edges": [
                {"a": refs[index], "b": refs[index + 1],
                 "length_mm": 10.0, "layers": ["B.Cu"],
                 "through_hole_edge": True}
                for index in range(3)
            ],
        }
        candidates = {
            "J2": [{"ref": "J2", "p": (10.0, 2.0),
                    "n": (10.0, 2.45), "center": (10.0, 2.225)}],
            "J3": [{"ref": "J3", "p": (20.0, 2.0),
                    "n": (20.0, 2.45), "center": (20.0, 2.225)}],
        }
        calls = []

        def route_stub(_board, _pair, endpoints, *, layer, **_kwargs):
            calls.append((endpoints, layer))
            return {"segments": 2, "length_mm": 1.0,
                    "coupled_len_mm": 1.0}

        with mock.patch.object(
                    precision, "_multidrop_junction_candidates",
                    side_effect=lambda _board, _plan, ref, _pair:
                        candidates[ref]), \
                mock.patch.object(precision, "_route_paired_stub",
                                  side_effect=route_stub), \
                mock.patch.object(precision, "_pair_graph_geometry",
                                  return_value={"ok": True, "issues": []}):
            report = precision._route_layered_multidrop_pair_tree(
                Board(), pair, plan)

        self.assertEqual(report["route_mode"],
                         "layered-paired-trunk-short-stub")
        self.assertEqual(set(report["junctions"]), {"J2@B.Cu", "J3@B.Cu"})
        production_legs = report["legs"]
        self.assertEqual(
            sum(row["graph_role"] == "terminal_stub"
                for row in production_legs), 2)
        self.assertEqual(
            sum(row["graph_role"] == "trunk_edge"
                for row in production_legs), 3)

    def test_planar_embedding_propagates_one_lane_order_along_tree_diameter(self):
        refs = ["A", "B", "C", "D"]
        centers = [(0.0, 0.0), (10.0, 0.0),
                   (18.0, 6.0), (28.0, 6.0)]
        plan = {
            "ports": {
                ref: {"p": (center[0], center[1] - 0.225),
                      "n": (center[0], center[1] + 0.225),
                      "center": center}
                for ref, center in zip(refs, centers)
            }}
        edges = [
            {"a": refs[index], "b": refs[index + 1],
             "length_mm": precision._dist(
                 centers[index], centers[index + 1]),
             "selected_layer": "B.Cu"}
            for index in range(3)]

        embedding = precision._multidrop_planar_embedding(plan, edges)

        self.assertEqual(set(embedding), {("B", "B.Cu"),
                                          ("C", "B.Cu")})
        self.assertEqual(set(embedding[("B", "B.Cu")]["through"]),
                         {"A", "C"})
        self.assertEqual(set(embedding[("C", "B.Cu")]["through"]),
                         {"B", "D"})
        b_axis = embedding[("B", "B.Cu")]["lane_axis"]
        c_axis = embedding[("C", "B.Cu")]["lane_axis"]
        self.assertGreater(b_axis[0] * c_axis[0] + b_axis[1] * c_axis[1],
                           0.0)

        rows = [
            {"ref": "B", "center": (10.0, 2.0),
             "p": (9.0, 2.0), "n": (11.0, 2.0)},
            {"ref": "B", "center": (10.0, 2.0),
             "p": (10.0, 1.0), "n": (10.0, 3.0)},
        ]
        oriented = precision._orient_junction_candidates(
            rows, b_axis, {"width": 0.25, "gap": 0.20})
        self.assertEqual(len(oriented), 1)
        lane = (oriented[0]["n"][0] - oriented[0]["p"][0],
                oriented[0]["n"][1] - oriented[0]["p"][1])
        self.assertAlmostEqual(precision._dist(
            oriented[0]["p"], oriented[0]["n"]), 0.45)
        self.assertGreater(lane[0] * b_axis[0] + lane[1] * b_axis[1], 0.0)

    def test_layer_assignment_alternates_pth_chain_to_remove_junctions(self):
        refs = ["A", "B", "C", "D", "E"]
        plan = {
            "preferred_signal_layers": ["B.Cu", "F.Cu"],
            "ports": {
                ref: {"through": True} for ref in refs},
        }
        edges = [
            {"a": refs[index], "b": refs[index + 1],
             "length_mm": 10.0, "layers": ["B.Cu", "F.Cu"]}
            for index in range(len(refs) - 1)]

        report = precision._assign_multidrop_edge_layers(plan, edges)

        self.assertEqual(report["score"]["same_layer_junction_excess"], 0)
        self.assertEqual(report["selected_layers"],
                         ["B.Cu", "F.Cu", "B.Cu", "F.Cu"])

    def test_layer_assignment_preserves_non_pth_internal_continuity(self):
        plan = {
            "preferred_signal_layers": ["B.Cu", "F.Cu"],
            "ports": {
                "A": {"through": True},
                "B": {"through": False},
                "C": {"through": True},
            },
        }
        edges = [
            {"a": "A", "b": "B", "length_mm": 10.0,
             "layers": ["B.Cu", "F.Cu"]},
            {"a": "B", "b": "C", "length_mm": 10.0,
             "layers": ["B.Cu", "F.Cu"]},
        ]

        report = precision._assign_multidrop_edge_layers(plan, edges)

        self.assertEqual(report["selected_layers"], ["B.Cu", "B.Cu"])

    def test_pth_edge_fallback_uses_only_endpoint_conflict_free_layers(self):
        target = {"a": "B", "b": "C", "selected_layer": "F.Cu",
                  "layers": ["F.Cu", "In2.Cu", "B.Cu"]}
        edges = [
            {"a": "A", "b": "B", "selected_layer": "In2.Cu"},
            target,
            {"a": "C", "b": "D", "selected_layer": "In2.Cu"},
        ]

        alternatives = precision._conflict_free_edge_layers(
            target, edges, ["F.Cu", "In2.Cu", "B.Cu"])

        self.assertEqual(alternatives, ["B.Cu"])

    def test_forced_route_layer_recolors_adjacent_pth_edges(self):
        refs = ["A", "B", "C", "D"]
        plan = {
            "preferred_signal_layers": ["F.Cu", "In2.Cu", "B.Cu"],
            "ports": {ref: {"through": True} for ref in refs},
        }
        edges = [
            {"a": refs[index], "b": refs[index + 1],
             "length_mm": 10.0,
             "layers": ["F.Cu", "In2.Cu", "B.Cu"]}
            for index in range(3)]

        report = precision._assign_multidrop_edge_layers(
            plan, edges, forced_layers={("B", "C"): "In2.Cu"})

        self.assertEqual(report["selected_layers"][1], "In2.Cu")
        self.assertNotEqual(report["selected_layers"][0], "In2.Cu")
        self.assertNotEqual(report["selected_layers"][2], "In2.Cu")
        self.assertEqual(report["score"]["same_layer_junction_excess"], 0)

    def test_layer_assignment_learns_from_prior_route_evidence(self):
        refs = ["A", "B", "C", "D"]
        plan = {
            "preferred_signal_layers": ["F.Cu", "In2.Cu", "B.Cu"],
            "ports": {ref: {"through": True} for ref in refs},
        }
        edges = [
            {"a": refs[index], "b": refs[index + 1],
             "length_mm": 10.0,
             "layers": ["F.Cu", "In2.Cu", "B.Cu"]}
            for index in range(3)
        ]
        evidence = {
            ("A", "B"): {"F.Cu": {"successes": 1}},
            ("B", "C"): {
                "In2.Cu": {"refusals": 1},
                "B.Cu": {"successes": 1},
            },
            ("C", "D"): {"F.Cu": {"successes": 1}},
        }

        report = precision._assign_multidrop_edge_layers(
            plan, edges, route_layer_evidence=evidence)

        self.assertEqual(report["selected_layers"],
                         ["F.Cu", "B.Cu", "F.Cu"])
        self.assertEqual(report["score"]["same_layer_junction_excess"], 0)
        self.assertEqual(report["score"]["learned_refusals"], 0)
        self.assertEqual(report["score"]["learned_successes"], 3)

    def test_package_native_breakout_is_classified_without_reorientation(self):
        rows = [
            {"ref": "J", "center": (2.0, 3.0),
             "p": (1.0, 2.0), "n": (3.0, 4.0)},
            {"ref": "J", "center": (2.0, 3.0),
             "p": (3.0, 4.0), "n": (1.0, 2.0)},
        ]

        classified = precision._classify_junction_candidates(
            rows, (1.0, 0.0))

        self.assertEqual([row["embedding_sign"] for row in classified],
                         [1, -1])
        self.assertEqual(classified[0]["p"], rows[0]["p"])
        self.assertEqual(classified[0]["n"], rows[0]["n"])
        self.assertEqual(
            precision._classify_junction_candidates(
                rows, (1.0, 0.0), orientation_sign=-1),
            [classified[1]])

        expanded = precision._expand_junction_trunk_signs(
            rows[:1], (1.0, 0.0), trunk_sign=-1)
        self.assertEqual(expanded[0]["local_embedding_sign"], 1)
        self.assertEqual(expanded[0]["embedding_sign"], -1)
        self.assertEqual(expanded[0]["p"], rows[0]["p"])

    def test_paired_stub_can_run_a_direct_only_prefilter(self):
        class Board:
            def GetLayerID(self, _layer):
                return 0

            def GetLayerName(self, _layer):
                return "F.Cu"

            def GetNetcodeFromNetname(self, name):
                return {"P": 1, "N": 2}[name]

            def GetFootprints(self):
                return []

        pair = {"name": "BUS", "p": "P", "n": "N",
                "width": 0.25, "gap": 0.20}
        endpoints = ((0.0, 0.0), (1.0, 1.0),
                     (0.0, 0.45), (1.0, 1.45))
        with mock.patch.object(precision.cec_fr, "_edge_leg_clear",
                               return_value=False), \
                mock.patch.object(precision.cec_fr, "_foreign_shape_indexes",
                                  return_value=((), ())), \
                mock.patch.object(precision.cec_fr, "_snapshot_foreign_clear",
                                  return_value=True), \
                mock.patch.object(precision, "_partner_pads_clear",
                                  return_value=True), \
                mock.patch.object(
                    precision, "_short_pair_ribbon_candidates") as ribbon, \
                mock.patch.object(precision, "_joint_endpoint_escape") as solve:
            report = precision._route_paired_stub(
                Board(), pair, endpoints, allow_detour=False)

        self.assertEqual(report["refused"],
                         "no clear direct paired terminal stub")
        self.assertTrue(report["admission"]["detour"]["skipped"])
        ribbon.assert_not_called()
        solve.assert_not_called()

    def test_paired_stub_reuses_exact_foreign_shape_index(self):
        class Board:
            def GetLayerID(self, _layer):
                return 0

            def GetLayerName(self, _layer):
                return "F.Cu"

            def GetNetcodeFromNetname(self, name):
                return {"P": 1, "N": 2}[name]

            def Zones(self):
                return []

            def GetFootprints(self):
                return []

            def GetTracks(self):
                return []

        board = Board()
        pair = {"name": "BUS", "p": "P", "n": "N",
                "width": 0.25, "gap": 0.20}
        endpoints = ((0.0, 0.0), (2.0, 0.0),
                     (0.0, 0.45), (2.0, 0.45))
        foreign_cache = {}
        partner_cache = {}
        with mock.patch.object(precision.cec_fr, "_edge_leg_clear",
                               return_value=True), \
                mock.patch.object(
                    precision.cec_fr, "_layer_foreign_shapes",
                    wraps=precision.cec_fr._layer_foreign_shapes) as shapes, \
                mock.patch.object(precision, "_lay", return_value=[1]):
            first = precision._route_paired_stub(
                board, pair, endpoints,
                foreign_shape_cache=foreign_cache,
                partner_shape_cache=partner_cache)
            second = precision._route_paired_stub(
                board, pair, endpoints,
                foreign_shape_cache=foreign_cache,
                partner_shape_cache=partner_cache)

        self.assertNotIn("refused", first)
        self.assertNotIn("refused", second)
        self.assertEqual(shapes.call_count, 1)

    def test_short_pair_uses_local_cell_before_portal_or_global_search(self):
        class Board:
            def GetLayerID(self, _layer):
                return 0

            def GetNetcodeFromNetname(self, name):
                return {"P": 1, "N": 2}[name]

        pair = {"name": "BUS", "p": "P", "n": "N",
                "width": 0.25, "gap": 0.20, "ztarget": 90.0}
        endpoints = ((0.0, 0.0), (3.0, 0.0),
                     (0.0, 0.45), (3.0, 0.45))
        local = {"route_mode": "paired-terminal-stub", "segments": 2,
                 "length_mm": 3.0, "coupled_coverage_pct": 100.0}
        with mock.patch.object(precision, "_route_paired_stub",
                               return_value=local) as stub, \
                mock.patch.object(precision, "_route_coupled_via_portals") as portal:
            report = precision.route_coupled_pair(
                Board(), pair, endpoints=endpoints, pair_grid=True,
                minimum_coupled_fraction=0.35)

        self.assertEqual(report["route_mode"], "short-pair-local-cell")
        self.assertEqual(report["short_pair_span_mm"], 3.0)
        self.assertEqual(report["ztarget"], 90.0)
        self.assertEqual(
            stub.call_args.kwargs["minimum_coupled_fraction"], 0.35)
        self.assertTrue(
            stub.call_args.kwargs["allow_terminal_gap_taper"])
        portal.assert_not_called()

    def test_polyline_coupling_rejects_parallel_but_distant_members(self):
        close = precision._polyline_coupling_coverage(
            [(0.0, 0.0), (10.0, 0.0)],
            [(0.0, 0.45), (10.0, 0.45)], 0.25, 0.20)
        distant = precision._polyline_coupling_coverage(
            [(0.0, 0.0), (10.0, 0.0)],
            [(0.0, 2.0), (10.0, 2.0)], 0.25, 0.20)

        self.assertEqual(close["coverage_pct"], 100.0)
        self.assertEqual(distant["coverage_pct"], 0.0)

    def test_joint_escape_honors_expired_absolute_deadline(self):
        import time
        diagnostics = {}
        result = precision._joint_endpoint_escape(
            (0.0, 0.0), (0.0, 0.45),
            (10.0, 0.0), (10.0, 0.45),
            width=0.25, gap=0.20,
            segment_clear=lambda _a, _b: True,
            diagnostics=diagnostics,
            deadline=time.monotonic() - 1.0)

        self.assertIsNone(result)
        self.assertTrue(diagnostics["deadline_exhausted"])

    def test_local_star_throats_use_component_order_not_package_axis(self):
        plan = {
            "ports": {
                "J": {"center": (0.0, 0.0)},
                "A": {"center": (-10.0, 0.0)},
                "B": {"center": (10.0, 0.0)},
            }}
        pair = {"width": 0.25, "gap": 0.20}
        junction = {
            "center": (0.0, 2.0),
            "p": (-0.2, 2.0), "n": (0.2, 2.0),
            "embedding_sign": -1,
        }
        edges = [
            {"a": "A", "b": "J", "length_mm": 10.0},
            {"a": "J", "b": "B", "length_mm": 10.0},
        ]
        embedding = {("J", "B.Cu"): {"lane_axis": (0.0, 1.0)}}

        throats = precision._multidrop_junction_throats(
            plan, pair, "J", "B.Cu", junction, edges, embedding)

        self.assertEqual(set(throats), {"A", "B"})
        for throat in throats.values():
            self.assertAlmostEqual(
                precision._dist(throat["p"], throat["n"]), 0.45)
            self.assertGreater(throat["p"][1], throat["n"][1])

    def test_mitered_junction_uses_offset_ribbon_vertices(self):
        plan = {"ports": {
            "J": {"center": (0.0, 0.0)},
            "A": {"center": (-10.0, 0.0)},
            "B": {"center": (0.0, 10.0)},
        }}
        pair = {"width": 0.25, "gap": 0.20}
        junction = {"center": (0.0, 0.0), "p": (-0.225, 0.0),
                    "n": (0.225, 0.0), "embedding_sign": 1}
        edges = [
            {"a": "A", "b": "J", "length_mm": 10.0},
            {"a": "J", "b": "B", "length_mm": 10.0},
        ]
        embedding = {("J", "B.Cu"): {"through": ["A", "B"]}}

        cell = precision._mitered_junction_candidate(
            plan, pair, "J", "B.Cu", junction, edges, embedding)

        self.assertEqual(cell["junction_geometry"],
                         "mitered-offset-ribbon")
        self.assertEqual(set(cell["_junction_throats"]), {"A", "B"})
        self.assertAlmostEqual(precision._dist(cell["p"], cell["n"]),
                               0.45 * 2 ** 0.5, places=5)

    def test_layered_tree_backtracks_component_lane_order_once(self):
        class Board:
            def GetTracks(self):
                return []

            def Remove(self, _item):
                raise AssertionError("nothing should be removed")

        pair = {"name": "BUS", "p": "P", "n": "N",
                "width": 0.25, "gap": 0.20}
        plan = {
            "terminals": ["A", "B", "C", "D"],
            "preferred_signal_layers": ["B.Cu"],
            "ports": {
                ref: {"p": (i * 10.0, 0.0),
                      "n": (i * 10.0, 0.45),
                      "center": (i * 10.0, 0.225),
                      "layers": ["B.Cu"], "through": True}
                for i, ref in enumerate(("A", "B", "C", "D"))},
            "edges": [
                {"a": "A", "b": "B", "length_mm": 10.0,
                 "layers": ["B.Cu"]},
                {"a": "B", "b": "C", "length_mm": 10.0,
                 "layers": ["B.Cu"]},
                {"a": "C", "b": "D", "length_mm": 10.0,
                 "layers": ["B.Cu"]},
            ],
        }
        rows = {
            "B": [{"ref": "B", "center": (10.0, 2.0),
                   "p": (10.0, 1.775), "n": (10.0, 2.225)}],
            "C": [{"ref": "C", "center": (20.0, 2.0),
                   "p": (20.0, 1.775), "n": (20.0, 2.225)}],
        }

        # B selects sign +1 first; C refuses it.  The recursive retry forces
        # -1 for both and succeeds.  Mock routing keeps this a topology test.
        def expand(values, _axis, *, trunk_sign=None):
            ref = values[0]["ref"]
            available = ([1, -1] if ref == "B" else [-1])
            if trunk_sign is not None:
                available = [s for s in available
                             if s == trunk_sign]
            return [dict(values[0], embedding_sign=s) for s in available]

        with mock.patch.object(
                    precision, "_multidrop_junction_candidates",
                    side_effect=lambda _b, _p, ref, _pair: rows[ref]), \
                mock.patch.object(precision, "_expand_junction_trunk_signs",
                                  side_effect=expand), \
                mock.patch.object(precision, "_route_paired_stub",
                                  return_value={"segments": 2,
                                                "length_mm": 1.0,
                                                "coupled_len_mm": 1.0}), \
                mock.patch.object(precision, "_pair_graph_geometry",
                                  return_value={"ok": True, "issues": []}):
            report = precision._route_layered_multidrop_pair_tree(
                Board(), pair, plan)

        self.assertFalse(report.get("refused"), report)
        self.assertEqual(report["junctions"]["B@B.Cu"]["embedding_sign"],
                         -1)
        self.assertEqual(report["junctions"]["C@B.Cu"]["embedding_sign"],
                         -1)
        self.assertEqual(report["orientation_backtracking"][0]["retry_sign"],
                         -1)

    def test_existing_partner_copper_uses_exact_pair_clearance(self):
        class Shape:
            def Collide(self, _segment, clearance):
                self.clearance = clearance
                return True

        class Track:
            def __init__(self, code):
                self.code = code
                self.shape = Shape()

            def GetNetCode(self):
                return self.code

            def Type(self):
                return -1

            def GetLayer(self):
                return 0

            def GetEffectiveShape(self, _layer):
                return self.shape

        partner = Track(2)
        own = Track(1)

        class Board:
            def GetTracks(self):
                return [own, partner]

        self.assertFalse(precision._partner_tracks_clear(
            Board(), (0.0, 0.0), (2.0, 0.0), 200000, 0, 2,
            clearance_nm=200000))
        self.assertEqual(partner.shape.clearance, 199999)
        # The same-member trace is not the partner and remains reusable.
        self.assertTrue(precision._partner_tracks_clear(
            Board(), (0.0, 0.0), (2.0, 0.0), 200000, 0, 3))


if __name__ == "__main__":
    unittest.main()
