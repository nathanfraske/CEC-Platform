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


class _RoutingBoard:
    """Minimal project settings shared by synthetic routing doubles."""
    def Groups(self):
        return []

    def Delete(self,item):
        # Test double only: production permanent discard uses native Delete.
        return self.Remove(item)

    def GetDesignSettings(self):
        from types import SimpleNamespace
        return SimpleNamespace(m_MinClearance=0)


class PrecisionSerializationTests(unittest.TestCase):
    def test_saved_precision_board_refills_before_return(self):
        events = []
        board = object()
        route_report = {
            "critical_routes_ok": True,
            "pairs_ok": True,
            "locked_nets": ["/PAIR_P", "/PAIR_N"],
        }

        with mock.patch.object(precision.pcbnew, "LoadBoard",
                               return_value=board), \
                mock.patch.object(precision.pcbnew, "SaveBoard",
                                  side_effect=lambda *_args: events.append(
                                      "saved")), \
                mock.patch.object(precision.cec_fr, "owned_locked_nets",
                                  return_value=()), \
                mock.patch.object(precision, "precision_route_board",
                                  return_value=route_report), \
                mock.patch.object(precision.cec_fr, "copy_project_sidecars",
                                  return_value={}), \
                mock.patch.object(
                    precision.cec_fr, "ensure_local_pair_return_via_rule",
                    return_value={}), \
                mock.patch.object(
                    precision.cec_fr, "refill_zones",
                    side_effect=lambda _path: events.append("refilled") or True):
            report = precision.precision_route(
                "placed.kicad_pcb", "precision.kicad_pcb", verbose=False)

        self.assertEqual(events, ["saved", "refilled"])
        self.assertTrue(report["zones_refilled"])
        self.assertEqual(report["zone_refill_policy"],
                         "fresh-load-before-exact-admission")

    def test_failed_precision_refill_refuses_before_exact_admission(self):
        board = object()
        route_report = {"critical_routes_ok": True, "pairs_ok": True}

        with mock.patch.object(precision.pcbnew, "LoadBoard",
                               return_value=board), \
                mock.patch.object(precision.pcbnew, "SaveBoard"), \
                mock.patch.object(precision.cec_fr, "owned_locked_nets",
                                  return_value=()), \
                mock.patch.object(precision, "precision_route_board",
                                  return_value=route_report), \
                mock.patch.object(precision.cec_fr, "copy_project_sidecars",
                                  return_value={}), \
                mock.patch.object(
                    precision.cec_fr, "ensure_local_pair_return_via_rule",
                    return_value={}), \
                mock.patch.object(precision.cec_fr, "refill_zones",
                                  return_value=False):
            with self.assertRaises(precision.PrecisionRouteRefused) as raised:
                precision.precision_route(
                    "placed.kicad_pcb", "precision.kicad_pcb",
                    verbose=False)

        self.assertIn("zone refill failed", str(raised.exception))


class PrecisionFlowThroughTests(unittest.TestCase):
    def test_pair_schedule_routes_multidrop_before_shorter_flow_through(self):
        multidrop = {"name": "BUS", "p": "BUS_P", "n": "BUS_N"}
        flow = {"name": "USB", "p": "USB_P", "n": "USB_N"}
        plan = {
            "terminals": ["A", "B", "C", "D"],
            "edges": [
                {"layers": ["F.Cu", "B.Cu"]},
                {"layers": ["F.Cu"]},
                {"layers": ["F.Cu", "B.Cu"]},
            ],
        }
        with mock.patch.object(
                precision, "_flow_through_pair_legs",
                side_effect=lambda _board, pair: (
                    ([(0, 1)], ["X"]) if pair is flow else None)), \
                mock.patch.object(
                    precision, "_multidrop_pair_plan",
                    side_effect=lambda _board, pair: (
                        plan if pair is multidrop else None)), \
                mock.patch.object(
                    precision, "_pair_route_span",
                    side_effect=lambda _board, pair: (
                        80.0 if pair is multidrop else 20.0)):
            scheduled, evidence = precision._scheduled_coupled_pairs(
                object(), [flow, multidrop])

        self.assertEqual(scheduled, [multidrop, flow])
        self.assertEqual(evidence[0]["topology"], "multidrop")
        self.assertEqual(evidence[0]["constrained_edge_count"], 1)
        self.assertEqual(evidence[1]["topology"], "flow-through")
        self.assertTrue(all(row["ordering_policy"] ==
                            "topology-constrained-first"
                            for row in evidence))

    def test_precision_emitter_refuses_raw_diagonal(self):
        import pcbnew

        board = pcbnew.BOARD()
        net = pcbnew.NETINFO_ITEM(board, "SIG")
        board.Add(net)
        with self.assertRaisesRegex(ValueError, "non-octilinear"):
            precision._lay(
                board, net.GetNetCode(), [(0.0, 0.0), (2.0, 0.5)],
                pcbnew.FromMM(0.2), pcbnew.F_Cu)
        self.assertEqual(len(list(board.GetTracks())), 0)

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
            local_search={"selected": {"maximum_member_detour_ratio": 3.0}},
            route_reports=[{
                "graph_role": "trunk_edge", "edge": ["J1", "J2"],
                "layer": "F.Cu", "length_mm": 34.0,
            }],
            tree_edges=[{"a": "J1", "b": "J2", "length_mm": 16.0}])
        self.assertEqual(certificate["classification"],
                         ["excessive_detour"])
        self.assertEqual(len(certificate["copper_witness"]), 6)
        self.assertEqual(set(certificate["endpoints"]), {"start", "end"})
        self.assertEqual(len(certificate["relief_vectors"]), 4)
        self.assertEqual(certificate["route_legs"][0]["edge"],
                         ["J1", "J2"])
        self.assertEqual(certificate["tree_edges"][0]["length_mm"], 16.0)

    def test_pair_detour_counts_only_repeated_local_layer_articulation(self):
        reports = [
            {"graph_role": "terminal_stub", "terminal": "J1",
             "layer": "F.Cu", "length_mm": 2.0},
            {"graph_role": "terminal_stub", "terminal": "J1",
             "layer": "In2.Cu", "length_mm": 3.0},
            {"graph_role": "terminal_stub", "terminal": "J1",
             "layer": "In2.Cu", "length_mm": 4.0},
            {"graph_role": "junction_runway", "terminal": "J1",
             "layer": "F.Cu", "length_mm": 1.0},
            {"graph_role": "junction_runway", "terminal": "J1",
             "layer": "In2.Cu", "length_mm": 1.5},
            {"graph_role": "trunk_edge", "terminal": "J1",
             "layer": "B.Cu", "length_mm": 100.0},
        ]

        allowance, detail = precision._pair_local_articulation_allowance(
            reports)

        self.assertAlmostEqual(allowance, 4.5)
        self.assertEqual(len(detail), 2)
        self.assertEqual(
            {row["graph_role"] for row in detail},
            {"terminal_stub", "junction_runway"})
        self.assertNotIn("trunk_edge", {
            row["graph_role"] for row in detail})

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

    def test_pair_geometry_uses_assigned_default_class_authority(self):
        width, gap = precision._pair_geometry({
            "default": {"diff_width": 0.20, "diff_gap": 0.25,
                        "clearance": 0.20}}, "usb")
        self.assertEqual(width, 0.20)
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

        class Board(_RoutingBoard):
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

    def test_hierarchical_can_mate_is_resolved_only_in_its_own_sheet(self):
        class Net:
            def __init__(self, name):
                self.name = name

            def GetNetname(self):
                return self.name

        class Nets:
            def values(self):
                return [Net("/A/CAN_H"), Net("/B/CAN_H"),
                        Net("/A/CAN_L")]

        class Board(_RoutingBoard):
            def GetNetInfo(self):
                return type("I", (), {"NetsByNetcode": lambda _self: Nets()})()

        with mock.patch.object(precision, "_netclass_geometry",
                               return_value={}), \
                mock.patch.object(
                    precision.cec_score.Rules, "from_board",
                    return_value=type("R", (), {"diff_pairs": []})()):
            pairs = precision.derive_coupled_pairs(
                "neutral.kicad_pcb", board=Board())
        self.assertEqual([(row["p"], row["n"]) for row in pairs],
                         [("/A/CAN_H", "/A/CAN_L")])

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

        class Board(_RoutingBoard):
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

    def test_track_template_replay_preserves_via_geometry(self):
        import pcbnew

        source = pcbnew.BOARD()
        source_net = pcbnew.NETINFO_ITEM(source, "PAIR_P")
        source.Add(source_net)
        original = pcbnew.PCB_VIA(source)
        original.SetPosition(pcbnew.VECTOR2I_MM(4.0, 5.0))
        original.SetWidth(pcbnew.FromMM(0.50))
        original.SetDrill(pcbnew.FromMM(0.25))
        original.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
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
        self.assertEqual(replayed[0].GetClass(), "PCB_VIA")
        self.assertEqual(replayed[0].GetPosition(), original.GetPosition())
        self.assertEqual(replayed[0].GetDrillValue(),
                         original.GetDrillValue())
        self.assertEqual(replayed[0].GetWidth(replayed[0].TopLayer()),
                         original.GetWidth(original.TopLayer()))
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
        self.assertTrue(precision._polyline_is_octilinear(p_path))
        self.assertTrue(precision._polyline_is_octilinear(n_path))
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

        class Board(_RoutingBoard):
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

    def test_multidrop_betweenness_routes_backbone_before_leaf_drop(self):
        edges = [
            {"a": "A", "b": "B"}, {"a": "B", "b": "C"},
            {"a": "C", "b": "D"}, {"a": "D", "b": "E"},
            {"a": "C", "b": "DROP"},
        ]

        scores = precision._multidrop_edge_betweenness(edges)

        self.assertEqual(scores[("B", "C")], 8)
        self.assertEqual(scores[("C", "D")], 8)
        self.assertEqual(scores[("C", "DROP")], 5)
        self.assertGreater(scores[("B", "C")], scores[("A", "B")])

    def test_dissimilar_pth_pair_fields_are_scarce_interface_transitions(self):
        ports = {
            "J1": {"through": True, "p": (0.0, -2.0),
                   "n": (0.0, 2.0)},
            "J2": {"through": True, "p": (10.0, -0.5),
                   "n": (10.0, 0.5)},
            "U1": {"through": False, "p": (20.0, -0.5),
                   "n": (20.0, 0.5)},
        }

        transformed = precision._multidrop_edge_interface_difficulty(
            {"a": "J1", "b": "J2"}, ports)
        package_leaf = precision._multidrop_edge_interface_difficulty(
            {"a": "J2", "b": "U1"}, ports)

        self.assertTrue(transformed["pth_transition"])
        self.assertTrue(transformed["constrained"])
        self.assertGreater(transformed["score"], 0.0)
        self.assertEqual(transformed["pitch_ratio"], 4.0)
        self.assertFalse(package_leaf["constrained"])
        self.assertEqual(precision._multidrop_edge_attempt_seconds(
            {"a": "J1", "b": "J2", "layers": ["B.Cu", "In2.Cu"]},
            ports), 60.0)
        self.assertEqual(precision._multidrop_edge_attempt_seconds(
            {"a": "J2", "b": "U1", "layers": ["B.Cu", "In2.Cu"]},
            ports), 30.0)
        self.assertEqual(precision._multidrop_edge_attempt_seconds(
            {"a": "J2", "b": "U1", "layers": ["F.Cu"]}, ports), 60.0)
        self.assertEqual(precision._multidrop_edge_attempt_seconds(
            {"a": "J2", "b": "U1", "layers": ["F.Cu"]}, ports,
            forced=True), 90.0)

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

    def test_pair_portals_include_exact_reverse_launch_without_lane_swap(self):
        plan = precision._paired_portal_candidates(
            (0.0, -2.0), (0.0, 2.0),
            (20.0, -0.5), (20.0, 0.5),
            width=0.25, gap=0.20)

        for sign in (1, -1):
            start_rows = plan["by_sign"][sign]["start"]
            end_rows = plan["by_sign"][sign]["end"]
            start_forward = next(
                row for row in start_rows
                if row["lateral_mm"] == 0.0
                and not row["reverse_launch"])
            start_reverse = next(
                row for row in start_rows
                if row["lead_mm"] == start_forward["lead_mm"]
                and row["lateral_mm"] == 0.0
                and row["reverse_launch"])
            end_forward = next(
                row for row in end_rows
                if row["lateral_mm"] == 0.0
                and not row["reverse_launch"])
            self.assertGreater(start_forward["center"][0], 0.0)
            self.assertLess(start_reverse["center"][0], 0.0)
            self.assertEqual(start_forward["route_heading"], (1.0, 0.0))
            self.assertEqual(start_reverse["route_heading"], (-1.0, -0.0))
            # Reversing only the launch also reverses its local left/right
            # frame.  The end portal retains the same traversal-frame P/N
            # ordering, so the shared ribbon can turn around the package
            # without requesting a crossover.
            forward_lane = start_forward["p"][1] - start_forward["n"][1]
            reverse_lane = start_reverse["p"][1] - start_reverse["n"][1]
            end_lane = end_forward["p"][1] - end_forward["n"][1]
            self.assertLess(forward_lane * reverse_lane, 0.0)
            self.assertGreater(forward_lane * end_lane, 0.0)

    def test_portal_screen_order_samples_longer_escape_before_local_depth(self):
        rows = [
            {"lead_mm": lead, "reverse_launch": reverse, "rank": rank}
            for lead in (1.3, 3.0)
            for reverse in (False, True)
            for rank in (0, 1)
        ]
        ordered = precision._fair_portal_screen_order(
            rows, lambda row: row["rank"])
        self.assertEqual(
            {(row["lead_mm"], row["reverse_launch"])
             for row in ordered[:4]},
            {(1.3, False), (1.3, True), (3.0, False), (3.0, True)})
        self.assertTrue(all(row["rank"] == 0 for row in ordered[:4]))

    def test_equal_pinfield_peer_topology_seeds_endpoint_screen(self):
        rows = [
            {"lead_mm": 1.3, "lateral_mm": 0.0,
             "reverse_launch": False, "name": "generic"},
            {"lead_mm": 2.0, "lateral_mm": -3.0,
             "reverse_launch": True, "name": "mirrored"},
            {"lead_mm": 2.0, "lateral_mm": 3.0,
             "reverse_launch": True, "name": "same-sign"},
        ]
        proven = [{"lead_mm": 2.0, "lateral_mm": 3.0,
                   "reverse_launch": True}]
        ordered = precision._symmetry_seeded_portal_screen_order(
            rows, proven)
        self.assertEqual(
            [row["name"] for row in ordered],
            ["mirrored", "same-sign", "generic"])

    def test_portal_combination_prefers_endpoint_rank_before_shorter_fanin(self):
        end = {
            "reverse_launch": False,
            "score": (0, 0),
            "fanin_length_mm": 1.0,
            "lateral_mm": 0.0,
        }
        proven_escape = {
            "reverse_launch": False,
            "score": (1, 0),
            "fanin_length_mm": 4.0,
            "lateral_mm": 0.6,
        }
        shorter_bad_escape = {
            "reverse_launch": False,
            "score": (2, 0),
            "fanin_length_mm": 1.0,
            "lateral_mm": 0.0,
        }
        reverse_escape = {
            "reverse_launch": True,
            "score": (0, 0),
            "fanin_length_mm": 0.5,
            "lateral_mm": 0.0,
        }

        self.assertLess(
            precision._portal_combination_score(proven_escape, end),
            precision._portal_combination_score(shorter_bad_escape, end))
        self.assertLess(
            precision._portal_combination_score(shorter_bad_escape, end),
            precision._portal_combination_score(reverse_escape, end))

    def test_pair_edge_detour_ratio_uses_mean_member_lower_bound(self):
        endpoints = ((0.0, 0.0), (10.0, 0.0),
                     (0.0, 1.0), (10.0, 1.0))
        self.assertEqual(
            precision._pair_edge_detour_ratio(endpoints, 15.0), 1.5)

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
        class Board(_RoutingBoard):
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

    def test_dissimilar_pinfield_escalates_portal_grid_before_legacy_fan(self):
        class Board(_RoutingBoard):
            def GetLayerID(self, _layer):
                return 0

            def GetNetcodeFromNetname(self, net):
                return {"P": 1, "N": 2}[net]

        pair = {"name": "BUS", "kind": "can", "p": "P", "n": "N",
                "width": 0.25, "gap": 0.20, "ztarget": 120.0}
        endpoints = ((0.0, -2.0), (20.0, -0.25),
                     (0.0, 2.0), (20.0, 0.25))
        with mock.patch.object(
                precision, "_route_coupled_via_portals",
                side_effect=({"refused": "grid exhausted"},
                             {"route_mode": "paired-portals"})) as portal:
            report = precision.route_coupled_pair(
                Board(), pair, endpoints=endpoints, pair_grid=True,
                layer="F.Cu", deadline=time.monotonic() + 30.0)

        self.assertEqual(report["portal_search_phase"], "deep-retry")
        self.assertEqual(
            [call.kwargs["max_grid_visited"]
             for call in portal.call_args_list],
            [10000, 120000])

    def test_one_prequalified_throat_is_forwarded_to_portal_router(self):
        class Board(_RoutingBoard):
            def GetLayerID(self, _layer):
                return 0

            def GetNetcodeFromNetname(self, net):
                return {"P": 1, "N": 2}[net]

        pair = {"name": "BUS", "kind": "can", "p": "P", "n": "N",
                "width": 0.25, "gap": 0.20, "ztarget": 120.0}
        endpoints = ((0.0, -0.28125), (20.0, -2.0),
                     (0.0, 0.28125), (20.0, 2.0))
        throat = {"center": (0.0, 0.0),
                  "p": endpoints[0], "n": endpoints[2],
                  "route_heading": [1.0, 0.0]}
        accepted = {"route_mode": "paired-portals", "segments": 4,
                    "length_mm": 20.0, "coupled_len_mm": 19.0}
        with mock.patch.object(
                precision, "_route_coupled_via_portals",
                return_value=accepted) as portal:
            report = precision.route_coupled_pair(
                Board(), pair, endpoints=endpoints, pair_grid=True,
                layer="F.Cu", start_prequalified=throat,
                deadline=time.monotonic() + 30.0)

        self.assertEqual(report["route_mode"], "paired-portals")
        self.assertIs(portal.call_args.kwargs["start_prequalified"], throat)

    def test_surface_exhaustion_escalates_to_atomic_multilayer_portal(self):
        class Board(_RoutingBoard):
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
                "coupled_coverage_pct": 100.0,
                "handoff_member_coherence": 1.0,
                "handoff_route_heading": [1.0, 0.0]}
        middle = {"route_mode": "octilinear-grid", "segments": 2,
                  "length_mm": 15.0, "coupled_len_mm": 15.0,
                  "coupled_coverage_pct": 100.0}
        quality = {"ok": True, "geometry_ok": True,
                   "blocking_count": 0, "issues": []}
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
                    {"TEST": {"pofv": True, "pofv_drill_min_mm": 0.20,
                              "pofv_annular_min_mm": 0.05}}, clear=False), \
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
            via.GetWidth() == pcbnew.FromMM(0.5)
            and via.GetDrillValue() == pcbnew.FromMM(0.3)
            for via in signal_vias))
        # The native menu was clamped to ordinary .5/.3 dimensions; this
        # transaction must not claim a smaller-barrel process exception.
        self.assertFalse(report["pofv"]["qualified_process_exception"])

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
            "center": [5.0, 5.0],
            "p_contacts": [{"ref": "R1", "pad": "1", "point_mm": [5.0,4.8]}],
            "n_contacts": [{"ref": "R2", "pad": "1", "point_mm": [5.0,5.2]}]}]
        future_endpoints = ((5.0, 4.8), (15.0, 4.8),
                            (5.0, 5.2), (15.0, 5.2))
        diagnostics = {}

        def stations(_board, pair):
            return current_stations if pair is current else future_stations

        with mock.patch.object(precision, "_pair_endpoint_stations",
                               side_effect=stations), \
                mock.patch.object(precision, "_shared_series_launch_contract",
                                  return_value={"ok": False, "reason": "synthetic unavailable native proof", "reservations": []}), \
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
        self.assertEqual(routed[0]["package_pad_preclosure"]["pair_linked"], 2)
        self.assertEqual(routed[0]["local_pad_closure"]["pair_linked"], 0)
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
                p_start=(2.0, 9.73), n_start=(2.0, 10.27),
                p_end=(28.0, 9.73), n_end=(28.0, 10.27),
                layer_id=pcbnew.F_Cu, width=0.20, gap=0.34,
                clearance=0.20, own=set(),
                foreign_shape_cache=shape_cache,
            )
            repeated = precision._grid_coupled_path(
                board,
                start_center=(2.0, 10.0), end_center=(28.0, 10.0),
                p_start=(2.0, 9.73), n_start=(2.0, 10.27),
                p_end=(28.0, 9.73), n_end=(28.0, 10.27),
                layer_id=pcbnew.F_Cu, width=0.20, gap=0.34,
                clearance=0.20, own=set(),
                foreign_shape_cache=shape_cache,
            )
        self.assertIsNotNone(repeated)
        self.assertEqual(shapes.call_count, 1)
        self.assertIsNotNone(result)
        p_points, n_points, _length = result
        self.assertTrue(precision._pair_min_clear(
            p_points, n_points, -1, -1, 0.20, 0.34,
            strict_pair_gap=True))
        for points in (p_points, n_points):
            self.assertTrue(all(
                precision.cec_fr._edge_leg_clear(
                    board, precision._v(*a), precision._v(*b),
                    precision._nm(0.20) // 2, edge_mm=0.5)
                for a, b in zip(points, points[1:])))

    def test_portal_grid_allows_one_octilinear_turn_at_each_throat(self):
        """A proved portal is a throat, not an infinitely long straight."""
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

        def exact_clear(a, b, *_args, **_kwargs):
            ax, ay = a.x / precision.MM, a.y / precision.MM
            bx, by = b.x / precision.MM, b.y / precision.MM
            horizontal = abs(ay - 10.0) < 1e-6 and abs(by - 10.0) < 1e-6
            first_straight = horizontal and min(ax, bx) < 2.25
            last_straight = horizontal and max(ax, bx) > 27.75
            return not (first_straight or last_straight)

        diagnostics = {}
        with mock.patch.object(
                precision.cec_fr, "_layer_foreign_shapes",
                return_value=((), ())), mock.patch.object(
                precision.cec_fr, "_snapshot_foreign_clear",
                side_effect=exact_clear):
            result = precision._grid_coupled_path(
                board,
                start_center=(2.0, 10.0), end_center=(28.0, 10.0),
                p_start=(1.809081, 10.190919),
                n_start=(2.190919, 9.809081),
                p_end=(27.809081, 9.809081),
                n_end=(28.190919, 10.190919),
                layer_id=pcbnew.F_Cu, width=0.20, gap=0.34,
                clearance=0.20, own=set(), portal_mode=True,
                portal_start_heading=(1.0, 0.0),
                portal_end_heading=(1.0, 0.0),
                initial_turn_steps=1, terminal_turn_steps=1,
                diagnostics=diagnostics)

        self.assertIsNotNone(result, diagnostics)
        self.assertNotIn(diagnostics.get("status"), {
            "grid_exhausted", "deadline_exhausted"})

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
        self.assertEqual(taper["taper_geometry"], "straight-plus-45")
        self.assertTrue(precision._polyline_is_octilinear(taper["p"]))
        self.assertTrue(precision._polyline_is_octilinear(taper["n"]))
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

    def test_portal_taper_skips_a_locally_clear_reverse_core_join(self):
        taper = precision._portal_pair_taper_escape(
            (0.0, 0.35), (0.0, -0.35),
            [(0.0, 0.165), (-1.0, 0.165), (2.0, 0.165)],
            [(0.0, -0.165), (-1.0, -0.165), (2.0, -0.165)],
            width=0.20, gap=0.13,
            segment_clear=lambda _a, _b: True,
            require_forward_continuation=True)

        self.assertIsNotNone(taper)
        self.assertEqual(taper["middle_index"], 2)
        self.assertFalse(precision._polyline_has_reverse_bend(taper["p"]))
        self.assertFalse(precision._polyline_has_reverse_bend(taper["n"]))

    def test_portal_taper_rejects_departure_against_existing_runway(self):
        taper = precision._portal_pair_taper_escape(
            (0.0, 0.35), (0.0, -0.35),
            [(0.0, 0.165), (-1.0, 0.165), (-2.0, 0.165)],
            [(0.0, -0.165), (-1.0, -0.165), (-2.0, -0.165)],
            width=0.20, gap=0.13,
            segment_clear=lambda _a, _b: True,
            require_forward_continuation=True,
            portal_heading=(1.0, 0.0))

        self.assertIsNone(taper)

    def test_portal_taper_admits_quantized_index_zero_handoff(self):
        taper = precision._portal_pair_taper_escape(
            (0.0, 0.0), (0.318198, 0.318198),
            [(-0.1, 0.1), (-1.1, 1.1)],
            [(0.218198, 0.418198), (-0.781802, 1.418198)],
            width=0.20, gap=0.25,
            segment_clear=lambda _a, _b: True,
            require_forward_continuation=True,
            portal_heading=(-1.0, 1.0))

        self.assertIsNotNone(taper)
        self.assertEqual(taper["middle_index"], 0)
        self.assertFalse(precision._polyline_has_reverse_bend(taper["p"]))
        self.assertFalse(precision._polyline_has_reverse_bend(taper["n"]))

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

    def test_flow_station_orientation_minimizes_external_chain_not_pad_order(self):
        pads = {
            "P": [
                ("J", "1", (20.0, 0.0), None),
                # Deliberately enumerate the nearer bank first.  Both banks
                # have identical projection on the horizontal terminal axis.
                ("D", "6", (10.0, 1.0), None),
                ("D", "1", (10.0, 3.0), None),
                ("U", "1", (0.0, 0.0), None),
            ],
            "N": [
                ("J", "2", (20.0, 0.5), None),
                ("D", "4", (11.0, 1.0), None),
                ("D", "3", (11.0, 3.0), None),
                ("U", "2", (0.0, 0.5), None),
            ],
        }
        with mock.patch.object(precision, "_pads_on_net",
                               side_effect=lambda _board, net: pads[net]):
            legs, stations = precision._flow_through_pair_legs(
                object(), {"p": "P", "n": "N"})

        self.assertEqual(stations, ["D"])
        # Protect the long, constrained U-side leg before shaving distance
        # from the short connector escape.  This selects the y=1 bank toward
        # U even though the footprint enumerated it first as the inbound bank.
        self.assertEqual(legs[0], ((20.0, 0.0), (10.0, 3.0),
                                   (20.0, 0.5), (11.0, 3.0)))
        self.assertEqual(legs[1], ((10.0, 1.0), (0.0, 0.0),
                                   (11.0, 1.0), (0.0, 0.5)))

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

    def test_two_common_terminals_plus_split_station_are_three_terminals(self):
        pads = {
            "P": [("A", "1", (0, 0), None),
                  ("B", "1", (10, 0), None),
                  ("X8", "1", (5, 2), None)],
            "N": [("A", "2", (0, .5), None),
                  ("B", "2", (10, .5), None),
                  ("X9", "1", (5, 3), None)],
        }
        with mock.patch.object(precision, "_pads_on_net",
                               side_effect=lambda board, net: pads[net]):
            plan = precision._multidrop_pair_plan(object(), {"p": "P", "n": "N"})
        self.assertEqual(plan["terminals"], ["A", "B", "X8|X9"])
        self.assertEqual(len(plan["edges"]), 2)

    def test_layered_multidrop_uses_pth_pad_as_layer_articulation(self):
        class Board(_RoutingBoard):
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
                 "layers": ["B.Cu"],
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
        self.assertEqual(report["junctions"], {})
        self.assertEqual(
            [row["selected_layer"] for row in report["tree_edges"]],
            ["F.Cu", "B.Cu"])

    def test_only_wide_pth_multidrop_leaves_require_local_breakout(self):
        pair = {"width": 0.25, "gap": 0.20}
        edge = [{"a": "A", "b": "B"}]
        plan = {"ports": {
            "wide_pth": {"p": (0.0, 0.0), "n": (2.54, 0.0),
                         "through": True},
            "compact_pth": {"p": (0.0, 0.0), "n": (0.45, 0.0),
                            "through": True},
            "wide_smd": {"p": (0.0, 0.0), "n": (2.54, 0.0),
                         "through": False},
        }}

        self.assertTrue(precision._multidrop_leaf_breakout_required(
            plan, pair, "wide_pth", "B.Cu", edge))
        self.assertFalse(precision._multidrop_leaf_breakout_required(
            plan, pair, "compact_pth", "B.Cu", edge))
        self.assertFalse(precision._multidrop_leaf_breakout_required(
            plan, pair, "wide_smd", "F.Cu", edge))

    def test_multidrop_leaf_inherits_adjacent_planar_component_orientation(self):
        edge = {"a": "LEAF", "b": "JUNCTION"}
        incident = {
            ("LEAF", "In2.Cu"): [edge],
            ("JUNCTION", "In2.Cu"): [edge, {"a": "JUNCTION", "b": "B"}],
        }
        embedding = {
            ("JUNCTION", "In2.Cu"): {
                "component": 3, "lane_axis": [0.0, 1.0]},
        }

        owner = precision._multidrop_orientation_owner(
            embedding, incident, "LEAF", "In2.Cu")

        self.assertEqual(owner["component"], 3)
        self.assertEqual(owner["lane_axis"], [0.0, 1.0])
        self.assertIsNone(precision._multidrop_orientation_owner(
            embedding, incident, "LEAF", "B.Cu"))

    def test_leaf_breakout_sampler_reserves_every_escape_depth(self):
        plan = {
            "ports": {
                "A": {"p": (5.0, 8.0), "n": (7.54, 8.0),
                      "center": (6.27, 8.0), "through": True},
                "B": {"p": (30.0, 8.0), "n": (30.45, 8.0),
                      "center": (30.225, 8.0), "through": True},
            },
            "edges": [{"a": "A", "b": "B", "length_mm": 23.955}],
        }
        rows = precision._multidrop_leaf_throat_candidates(
            plan, {"width": 0.25, "gap": 0.20}, "A", plan["edges"],
            max_candidates=10)

        self.assertEqual(len(rows), 10)
        self.assertGreaterEqual(len({row["distance_mm"] for row in rows}), 5)
        throat = rows[0]["_junction_throats"]["B"]
        self.assertTrue(throat["clear_runway"])
        self.assertEqual(
            throat["_runway_origin"]["center"], rows[0]["center"])
        self.assertGreaterEqual(throat["length_mm"], 0.75)
        self.assertGreater(
            precision._dist(rows[0]["center"], throat["center"]), 0.0)

    def test_bounded_portal_screen_preserves_both_physical_lane_orders(self):
        rows = [dict(lead_mm=depth, reverse_launch=False,
                     p=(sign * 0.225, lateral), n=(-sign * 0.225, lateral),
                     cost=(0 if sign == 1 else 100) + lateral)
                for depth in (2.0, 3.0, 4.0, 5.0)
                for sign in (1, -1) for lateral in range(20)]
        sampled = precision._fair_portal_screen_order(
            rows, lambda row: row["cost"])[:8]
        for depth in (2.0, 3.0, 4.0, 5.0):
            self.assertEqual({row["p"][0] < row["n"][0]
                              for row in sampled if row["lead_mm"] == depth},
                             {True, False})

    def test_pair_portals_sample_narrow_short_span_escape_window(self):
        plan = precision._paired_portal_candidates(
            (0.0, -1.905), (0.0, 1.905),
            (4.314, -0.225), (4.314, 0.225),
            width=0.25, gap=0.20)

        rows = [row for row in plan["by_sign"][1]["start"]
                if row["escape_heading_step"] == 0]
        leads = {row["lead_mm"] for row in rows}
        self.assertTrue(leads)
        self.assertGreaterEqual(min(leads), 1.5)
        self.assertLessEqual(max(leads), 1.657)

    def test_pair_portals_keep_reverse_escape_when_forward_span_is_too_short(self):
        plan = precision._paired_portal_candidates(
            (0.0, 0.0), (2.54, 3.81),
            (4.314, 1.68), (4.764, 1.68),
            width=0.25, gap=0.20)

        rows = [row for row in plan["by_sign"][1]["start"]
                if row["escape_heading_step"] in (0, 4)]
        self.assertTrue(rows)
        self.assertTrue(all(row["reverse_launch"] for row in rows))
        self.assertGreaterEqual(min(row["lead_mm"] for row in rows), 1.9)

    def test_directed_portal_lane_compatibility_rejects_required_crossover(self):
        start = {"p": (0.0, -0.225), "n": (0.0, 0.225),
                 "route_heading": (1.0, 0.0)}
        compatible_end = {
            "p": (10.0, 0.225), "n": (10.0, -0.225),
            "route_heading": (1.0, 0.0)}
        crossing_end = {
            "p": (10.0, -0.225), "n": (10.0, 0.225),
            "route_heading": (1.0, 0.0)}

        self.assertTrue(precision._paired_portal_lane_compatible(
            start, compatible_end))
        self.assertFalse(precision._paired_portal_lane_compatible(
            start, crossing_end))

    def test_layered_multidrop_sends_long_edge_straight_to_global_pair_router(self):
        class Board(_RoutingBoard):
            def GetTracks(self):
                return []

            def Remove(self, _item):
                raise AssertionError("nothing should be removed")

        pair = {"name": "BUS", "p": "P", "n": "N",
                "width": 0.25, "gap": 0.20}
        plan = {
            "terminals": ["J1", "J2", "J3"],
            "preferred_signal_layers": ["B.Cu"],
            "ports": {
                ref: {"p": (index * 20.0, 0.0),
                      "n": (index * 20.0, 0.45),
                      "center": (index * 20.0, 0.225),
                      "layers": ["B.Cu"], "through": True}
                for index, ref in enumerate(("J1", "J2", "J3"))
            },
            "edges": [
                {"a": "J1", "b": "J2", "length_mm": 20.0,
                 "layers": ["B.Cu"], "through_hole_edge": True},
                {"a": "J2", "b": "J3", "length_mm": 20.0,
                 "layers": ["B.Cu"], "through_hole_edge": True},
            ],
        }
        accepted = {"segments": 2, "length_mm": 20.0,
                    "coupled_len_mm": 20.0}
        local_spans = []

        def local_route(_board, _pair, endpoints, **_kwargs):
            local_spans.append(max(
                precision._dist(endpoints[0], endpoints[1]),
                precision._dist(endpoints[2], endpoints[3])))
            return {"segments": 2, "length_mm": 1.0,
                    "coupled_len_mm": 1.0}

        with mock.patch.object(precision, "_route_paired_stub",
                               side_effect=local_route), \
                mock.patch.object(precision, "route_coupled_pair",
                                  return_value=accepted) as global_pair, \
                mock.patch.object(precision, "_pair_graph_geometry",
                                  return_value={"ok": True, "issues": []}), \
                mock.patch.object(precision, "_pair_coupling_summary",
                                  return_value={
                                      "total_samples": 1,
                                      "fraction": 1.0,
                                      "coverage_pct": 100.0,
                                      "minimum_pct": 35.0}), \
                mock.patch("cec_route_quality.analyze_board",
                           return_value={
                               "ok": True, "geometry_ok": True,
                               "issue_count": 0}):
            report = precision._route_layered_multidrop_pair_tree(
                Board(), pair, plan)

        self.assertFalse(report.get("refused"), report)
        self.assertTrue(local_spans)
        self.assertEqual(global_pair.call_count, 2)

    def test_layered_multidrop_inserts_one_stub_per_same_layer_junction(self):
        class Board(_RoutingBoard):
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
                mock.patch.object(
                    precision, "_route_prequalified_pair_portals",
                    return_value={"segments": 2, "length_mm": 10.0,
                                  "coupled_len_mm": 10.0}), \
                mock.patch.object(
                    precision, "route_coupled_pair",
                    return_value={"segments": 2, "length_mm": 10.0,
                                  "coupled_len_mm": 10.0}), \
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

    def test_layer_assignment_keeps_high_betweenness_backbone_continuous(self):
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

        self.assertEqual(report["score"]["backbone_discontinuities"], 0)
        self.assertEqual(report["score"]["same_layer_junction_excess"], 1)
        selected = report["selected_layers"]
        self.assertEqual(selected[1], selected[2])
        self.assertNotEqual(selected[0], selected[1])
        self.assertNotEqual(selected[3], selected[2])

    def test_wide_pth_backbone_prefers_articulation_over_local_junction(self):
        refs = ["A", "B", "C", "D"]
        plan = {
            "preferred_signal_layers": ["F.Cu", "In2.Cu", "B.Cu"],
            "ports": {
                ref: {"through": True, "p": (index * 10.0, 0.0),
                      "n": (index * 10.0 + 2.54, 3.81)}
                for index, ref in enumerate(refs)},
        }
        edges = [
            {"a": refs[index], "b": refs[index + 1],
             "length_mm": 10.0,
             "layers": ["F.Cu", "In2.Cu", "B.Cu"]}
            for index in range(3)]

        report = precision._assign_multidrop_edge_layers(
            plan, edges, pair={"width": 0.25, "gap": 0.20})

        selected = report["selected_layers"]
        self.assertNotEqual(selected[0], selected[1])
        self.assertNotEqual(selected[1], selected[2])
        self.assertEqual(report["score"]["wide_pth_junction_excess"], 0)

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

    def test_dissimilar_pth_transition_prefers_available_inner_signal_layer(self):
        plan = {
            "preferred_signal_layers": ["B.Cu", "F.Cu", "In2.Cu"],
            "ports": {
                "J1": {"through": True, "p": (0.0, -2.0),
                       "n": (0.0, 2.0)},
                "J2": {"through": True, "p": (10.0, -0.5),
                       "n": (10.0, 0.5)},
            },
        }
        edges = [{
            "a": "J1", "b": "J2", "length_mm": 10.0,
            "layers": ["B.Cu", "F.Cu", "In2.Cu"],
        }]

        report = precision._assign_multidrop_edge_layers(plan, edges)

        self.assertEqual(report["selected_layers"], ["In2.Cu"])
        self.assertEqual(report["score"]["interface_outer_layer_cost"], 0)

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
        self.assertEqual(report["selected_layers"],
                         ["In2.Cu", "In2.Cu", "In2.Cu"])
        self.assertEqual(report["score"]["backbone_discontinuities"], 0)
        self.assertEqual(report["score"]["same_layer_junction_excess"], 2)

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
        class Board(_RoutingBoard):
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
        class Board(_RoutingBoard):
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
        self.assertEqual(first["handoff_route_heading"], [1.0, 0.0])
        self.assertEqual(first["handoff_member_coherence"], 1.0)
        self.assertEqual(shapes.call_count, 1)

    def test_escape_boolean_probes_reuse_geometry_without_rebuilding_diagnostics(self):
        class Board(_RoutingBoard):
            def GetLayerID(self, _layer): return 0
            def GetLayerName(self, _layer): return 'F.Cu'
            def GetNetcodeFromNetname(self, name): return {'P': 1, 'N': 2}[name]
            def GetFootprints(self): return []
            def GetTracks(self): return []

        pair = dict(name='BUS', p='P', n='N', width=.25, gap=.20)
        endpoints = ((0., 0.), (2., 0.), (0., .45), (2., .45))
        def search(*args, **kwargs):
            for _ in range(20):
                self.assertFalse(kwargs['p_segment_clear']((0., 0.), (2., 0.)))
            return None
        with mock.patch.object(precision.cec_fr, '_edge_leg_clear', return_value=True), \
                mock.patch.object(precision.cec_fr, '_foreign_shape_indexes', return_value=((), ())), \
                mock.patch.object(precision.cec_fr, '_identified_foreign_shape_indexes', return_value=((), ())), \
                mock.patch.object(precision.cec_fr, '_snapshot_foreign_clear', return_value=False) as clear, \
                mock.patch.object(precision.cec_fr, '_snapshot_foreign_blockers', return_value=[{'kind':'pad'}]) as blockers, \
                mock.patch.object(precision, '_partner_pads_clear', return_value=True), \
                mock.patch.object(precision, '_partner_tracks_clear', return_value=True), \
                mock.patch.object(precision, '_short_pair_ribbon_candidates', return_value=()), \
                mock.patch('cec_pair_ribbon.candidates', return_value=()), \
                mock.patch.object(precision, '_joint_endpoint_escape', side_effect=search):
            report = precision._route_paired_stub(Board(), pair, endpoints)
        self.assertIn('refused', report)
        self.assertEqual(blockers.call_count, 2)  # P and N direct refusal witnesses remain.
        self.assertEqual(clear.call_count, 3)  # Two detailed probes and one cached boolean probe.
        self.assertEqual(report['admission']['direct']['p']['foreign_blockers'], [{'kind':'pad'}])

    def test_short_pair_uses_local_cell_before_portal_or_global_search(self):
        class Board(_RoutingBoard):
            def GetTracks(self):
                return []

            def GetFootprints(self):
                return []

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

    def test_wide_pinfield_junction_adds_only_local_clearance_margin(self):
        plan = {"ports": {
            "J": {"center": (0.0, 0.0),
                  "p": (0.0, -2.25), "n": (0.0, 2.25)},
            "A": {"center": (-10.0, 0.0)},
            "B": {"center": (10.0, 0.0)},
        }}
        pair = {"width": 0.25, "gap": 0.20}
        junction = {"center": (0.0, 2.0), "p": (0.0, 1.775),
                    "n": (0.0, 2.225), "embedding_sign": 1}
        edges = [
            {"a": "A", "b": "J", "length_mm": 10.0},
            {"a": "J", "b": "B", "length_mm": 10.0},
        ]
        embedding = {("J", "B.Cu"): {"through": ["A", "B"]}}

        cell = precision._mitered_junction_candidate(
            plan, pair, "J", "B.Cu", junction, edges, embedding)

        self.assertEqual(cell["junction_pair_scale"], 1.25)
        self.assertAlmostEqual(cell["junction_pair_spacing_mm"], 0.5625)
        for throat in cell["_junction_throats"].values():
            self.assertAlmostEqual(
                precision._dist(throat["p"], throat["n"]), 0.5625)
            self.assertEqual(len(throat["route_heading"]), 2)
            self.assertTrue(throat["clear_runway"])
            self.assertGreaterEqual(throat["length_mm"], 2.25)

    def test_noncanonical_neighbor_bearings_emit_canonical_junction_runways(self):
        # Physical endpoint bearings need not be router headings.  A direct-
        # only runway at e.g. 17 degrees can never pass the octilinear guard.
        plan = {"ports": {
            "J": {"center": (0.0, 0.0)},
            "A": {"center": (-10.0, 3.0)},
            "B": {"center": (6.0, 10.0)},
        }}
        pair = {"width": 0.25, "gap": 0.20}
        junction = {"center": (0.0, 0.0), "p": (-0.225, 0.0),
                    "n": (0.225, 0.0), "embedding_sign": 1}
        edges = [{"a": "J", "b": peer, "length_mm": 12.0}
                 for peer in ("A", "B")]
        embedding = {("J", "F.Cu"): {"through": ["A", "B"]}}
        cell = precision._mitered_junction_candidate(
            plan, pair, "J", "F.Cu", junction, edges, embedding)
        for throat in cell["_junction_throats"].values():
            for member in ("p", "n"):
                origin = throat["_runway_origin"][member]
                self.assertTrue(precision._polyline_is_octilinear(
                    [origin, throat[member]]))
            self.assertAlmostEqual(precision._dist(
                throat["p"], throat["n"]), 0.45, places=6)

    def test_local_star_cleanup_exposes_hidden_acute_junction_before_trunks(self):
        import cec_route_quality
        pcbnew = precision.pcbnew
        board = pcbnew.BOARD()
        net = pcbnew.NETINFO_ITEM(board, "/ARBITRARY_P", 1)
        board.Add(net)
        for end in ((1, 1), (0, 2), (0, 1)):
            track = pcbnew.PCB_TRACK(board)
            track.SetNet(net)
            track.SetLayer(pcbnew.F_Cu)
            track.SetWidth(200000)
            track.SetStart(pcbnew.VECTOR2I(0, 0))
            track.SetEnd(pcbnew.VECTOR2I(
                int(end[0] * 1e6), int(end[1] * 1e6)))
            board.Add(track)
        # Whole-copper craft analysis now catches the covered acute junction
        # before normalization too. Never restore the former blind spot just
        # to satisfy this legacy fixture: both stages must refuse the shape.
        before = cec_route_quality.analyze_board(
            board, critical_nets=("/ARBITRARY_P",))
        self.assertFalse(before["ok"])
        self.assertGreater(before["blocking_count"], 0)
        result = precision._normalized_pair_star_quality(
            board, {"p": "/ARBITRARY_P", "n": "/ARBITRARY_N"}, set())
        self.assertFalse(result["ok"])
        self.assertEqual(result["normalization"]["removed_count"], 1)
        self.assertEqual(result["issues"][0]["type"], "acute_backtrack")
        self.assertEqual(len(list(board.GetTracks())), 2)

    def test_layered_edge_normalizes_new_overlap_before_composed_admission(self):
        # Exercise the production edge path, not only the deduplication helper.
        # A false covered backtrack must disappear, but a genuine acute turn
        # must still refuse and roll back without removing prior copper.
        import pcbnew
        for acute in (False, True):
            with self.subTest(acute=acute):
                board = pcbnew.BOARD()
                nets = {}
                for name in ("BUS_P", "BUS_N"):
                    nets[name] = pcbnew.NETINFO_ITEM(board, name)
                    board.Add(nets[name])

                def add(name, a, b):
                    track = pcbnew.PCB_TRACK(board)
                    track.SetNet(nets[name])
                    track.SetLayer(pcbnew.F_Cu)
                    track.SetWidth(pcbnew.FromMM(0.2))
                    track.SetStart(pcbnew.VECTOR2I_MM(*a))
                    track.SetEnd(pcbnew.VECTOR2I_MM(*b))
                    board.Add(track)
                    return track.m_Uuid.AsString()

                prior = {add(name, (1, y), (3, y))
                         for name, y in (("BUS_P", 1), ("BUS_N", 1.45))}
                pair = {"name": "BUS", "p": "BUS_P", "n": "BUS_N",
                        "width": 0.2, "gap": 0.25}
                plan = {
                    "terminals": ["SOURCE", "LOAD"],
                    "preferred_signal_layers": ["F.Cu"],
                    "ports": {
                        ref: {"p": (x, 1), "n": (x, 1.45),
                              "center": (x, 1.225),
                              "layers": ["F.Cu"], "through": False}
                        for ref, x in (("SOURCE", 1), ("LOAD", 4))},
                    "edges": [{"a": "SOURCE", "b": "LOAD",
                               "length_mm": 3, "layers": ["F.Cu"]}],
                }

                def emit(*_args, **_kwargs):
                    for name, y in (("BUS_P", 1), ("BUS_N", 1.45)):
                        add(name, (1, y), (2, y))  # covered by prior runway
                        add(name, (3, y), (4, y))
                        if acute:
                            add(name, (4, y), (3.5, y + 0.5))
                    return {"segments": 4, "length_mm": 3,
                            "coupled_len_mm": 3}

                with mock.patch.object(precision, "_route_paired_stub",
                                       side_effect=emit), \
                        mock.patch.object(precision, "_pair_graph_geometry",
                                          return_value={"ok": True, "issues": []}):
                    result = precision._route_layered_multidrop_pair_tree(
                        board, pair, plan)
                remaining = {t.m_Uuid.AsString() for t in board.GetTracks()}
                self.assertTrue(prior <= remaining)
                if acute:
                    self.assertIn("route quality", result["failed_edge_detail"]["refused"])
                    self.assertEqual(remaining, prior)
                else:
                    self.assertFalse(result.get("refused"), result)
                    edge = next(row for row in result["legs"]
                                if row["graph_role"] == "trunk_edge")
                    self.assertEqual(edge["edge_normalization"]["removed_count"], 2)
                    self.assertEqual(edge["segments"], 2)
                    self.assertEqual(len(remaining), 4)

    def test_prequalified_pair_portals_bypass_package_fanin_search(self):
        class Board(_RoutingBoard):
            def GetFileName(self):
                return ""

            def GetLayerID(self, layer):
                return 0 if layer == "B.Cu" else -1

            def GetNetcodeFromNetname(self, net):
                return {"P": 1, "N": 2}[net]

        pair = {"name": "BUS", "p": "P", "n": "N",
                "width": 0.25, "gap": 0.20}
        start = {"center": (0.0, 0.0), "p": (0.0, -0.225),
                 "n": (0.0, 0.225), "route_heading": [1.0, 0.0]}
        end = {"center": (10.0, 0.0), "p": (10.0, -0.225),
               "n": (10.0, 0.225), "route_heading": [-1.0, 0.0]}
        grid = ([(0.0, -0.225), (10.0, -0.225)],
                [(0.0, 0.225), (10.0, 0.225)], 10.0)

        # Unit-isolate the corridor service, not the native field predicate.
        # Native end-to-end field feedback has its own unmocked regressions.
        with mock.patch("cec_pair_field_search.coupled_path", return_value=grid) as route, \
                mock.patch.object(precision, "_lay",
                                  side_effect=([object()], [object()])):
            report = precision._route_prequalified_pair_portals(
                Board(), pair, start, end, layer="B.Cu")

        self.assertEqual(report["route_mode"],
                         "prequalified-junction-portal-grid")
        self.assertEqual(report["length_mm"], 10.0)
        self.assertEqual(route.call_count, 1)
        self.assertEqual(
            route.call_args.kwargs["initial_turn_steps"], 0)
        self.assertEqual(
            route.call_args.kwargs["terminal_turn_steps"], 0)
        self.assertTrue(
            route.call_args.kwargs["strict_taper_continuation"])

    def test_layered_tree_backtracks_component_lane_order_once(self):
        class Board(_RoutingBoard):
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
                mock.patch.object(precision, "_junction_continuation_rank",
                                  return_value=(0, 0, 0)) as rank_mock, \
                mock.patch.object(precision, "_expand_junction_trunk_signs",
                                  side_effect=expand), \
                mock.patch.object(precision, "_route_paired_stub",
                                  return_value={"segments": 2,
                                                "length_mm": 1.0,
                                                "coupled_len_mm": 1.0}) as stub_mock, \
                mock.patch.object(
                    precision, "_route_prequalified_pair_portals",
                    return_value={"segments": 2, "length_mm": 10.0,
                                  "coupled_len_mm": 10.0}), \
                mock.patch.object(
                    precision, "route_coupled_pair",
                    return_value={"segments": 2, "length_mm": 10.0,
                                  "coupled_len_mm": 10.0}), \
                mock.patch.object(precision, "_pair_graph_geometry",
                                  return_value={"ok": True, "issues": []}):
            report = precision._route_layered_multidrop_pair_tree(
                Board(), pair, plan)

            # Ranking a later feasible candidate must affect the production
            # selection, not merely annotate the first greedy choice.  Here
            # it also avoids the deliberately constructed sign backtrack.
            rank_mock.side_effect = lambda _b, _pair, _plan, _ref, cell, *_: (
                0 if cell.get("embedding_sign") == -1 else 1, 0, 0)
            stub_mock.reset_mock()
            ranked = precision._route_layered_multidrop_pair_tree(
                Board(), pair, plan)
            snapshots = [id(call.kwargs["foreign_shape_cache"])
                         for call in stub_mock.call_args_list
                         if "foreign_shape_cache" in call.kwargs]
            # Screening shares an immutable foreign snapshot; emitting or
            # reselecting stars after trunks may encounter new return vias.
            assert len(set(snapshots)) > 1
            assert len(set(snapshots)) < len(snapshots)

        self.assertFalse(report.get("refused"), report)
        self.assertEqual(report["junctions"]["B@B.Cu"]["embedding_sign"],
                         -1)
        self.assertEqual(report["junctions"]["C@B.Cu"]["embedding_sign"],
                         -1)
        self.assertEqual(report["orientation_backtracking"][0]["retry_sign"],
                         -1)
        self.assertFalse(ranked.get("refused"), ranked)
        self.assertEqual(ranked["junctions"]["B@B.Cu"]["embedding_sign"], -1)
        self.assertNotIn("orientation_backtracking", ranked)
        self.assertEqual(ranked["candidate_prefilter"]["B@B.Cu"]["admissible_count"], 2)

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

        class Board(_RoutingBoard):
            def GetTracks(self):
                return [own, partner]

        self.assertFalse(precision._partner_tracks_clear(
            Board(), (0.0, 0.0), (2.0, 0.0), 200000, 0, 2,
            clearance_nm=200000))
        self.assertEqual(partner.shape.clearance, 199999)
        # The same-member trace is not the partner and remains reusable.
        self.assertTrue(precision._partner_tracks_clear(
            Board(), (0.0, 0.0), (2.0, 0.0), 200000, 0, 3))

    def test_existing_partner_copper_snapshot_uses_indexed_clearance(self):
        indexed = {"rows": (), "cell": 2_000_000,
                   "buckets": {}, "global": (), "max_clearance": 0}
        with mock.patch.object(
                precision.cec_fr, "_snapshot_foreign_clear",
                return_value=True) as clear:
            self.assertTrue(precision._partner_tracks_clear(
                object(), (0.0, 0.0), (2.0, 0.0), 200000, 0, 2,
                clearance_nm=200000, partner_shapes=indexed))
        clear.assert_called_once()
        self.assertEqual(clear.call_args.args[3], 199999)

    def test_paired_stub_indexes_partner_tracks_once_per_member(self):
        class Board(_RoutingBoard):
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

        cache = {}
        pair = {"name": "BUS", "p": "P", "n": "N",
                "width": 0.25, "gap": 0.20}
        endpoints = ((0.0, 0.0), (2.0, 0.0),
                     (0.0, 0.45), (2.0, 0.45))
        with mock.patch.object(precision.cec_fr, "_edge_leg_clear",
                               return_value=True), \
                mock.patch.object(precision, "_lay", return_value=[1]):
            report = precision._route_paired_stub(
                Board(), pair, endpoints, partner_shape_cache=cache)

        self.assertNotIn("refused", report)
        self.assertNotIn(("tracks", 0, 1), cache)
        self.assertNotIn(("tracks", 0, 2), cache)
        self.assertIn(("pads", 0, 1), cache)
        self.assertIn(("pads", 0, 2), cache)


if __name__ == "__main__":
    unittest.main()
