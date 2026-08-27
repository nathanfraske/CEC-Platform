#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# v4 TERRITORY POUR PLANNER teeth (docs/slab-pour-design-2026-07-24.md v4).
# Host-runnable: the duck-typed fake boards from test_pour_first drive
# cec_pour_plan.plan_pours end-to-end (no pcbnew). The five task-mandated
# teeth: (1) a corridor between two manifolds is straight / one-bend on the
# obstacle-corner graph; (2) 2D overlap forces distinct layers (zero
# same-layer inter-net overlap is HARD); (3) a forced crossing yields
# exactly ONE compact via field at the defined crossing point; (4) the
# verifier rejects a deliberately-thin corridor (min-width invariant);
# (5) the route_overunder fallback fires ONLY on planner failure.
import math
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cec_pour_plan  # noqa: E402
from cec_pour_plan import plan_pours  # noqa: E402
from test_pour_first import _LAY, _Board, _FP, _Pad, _wall  # noqa: E402

MM = 1e6
B_CU = [_LAY["B.Cu"]]
IN2_CU = [_LAY["In2.Cu"]]


def test_power_net_order_preserves_current_priority_and_declared_peer_order():
    amps = {
        "/HEAVY": 60.0,
        "/C1_HI": 39.0,
        "/C1_LO": 39.0,
        "/C2_HI": 39.0,
        "/UNDECLARED": 39.0,
        "/LIGHT": 5.0,
    }

    order = cec_pour_plan.power_net_order(
        amps,
        amps.__getitem__,
        priority_nets=("/C2_HI", "/C1_HI", "/C1_LO"),
    )

    assert order == [
        "/HEAVY", "/C2_HI", "/C1_HI", "/C1_LO", "/UNDECLARED", "/LIGHT",
    ]


def test_power_net_order_reads_isolated_environment_policy():
    amps = {"/A": 10.0, "/B": 10.0}
    with mock.patch.dict(
            os.environ, {"CEC_POWER_ROUTE_PRIORITY_NETS": "/B,/A"},
            clear=False):
        assert cec_pour_plan.power_net_order(amps, amps.__getitem__) == [
            "/B", "/A"]


def test_broad_relief_minimizer_recovers_small_mixed_rank_cut():
    ranked = tuple("ABCDEFGHIJK")

    def exact_oracle(removed):
        removed = set(removed)
        if {"A", "K"}.issubset(removed):
            return {
                "owners": list(removed),
                "length_mm": float(len(removed)),
                "path_mm": [[0.0, 0.0], [1.0, 0.0]],
            }
        return None

    cuts = cec_pour_plan._greedy_minimized_relief_sets(
        ranked, exact_oracle, exact_oracle(ranked))

    assert cuts
    assert set(cuts[0]["owners"]) == {"A", "K"}
    assert cuts[0]["searched_from_owner_count"] == 11


def test_exact_clearance_clash_evidence_names_physical_owner():
    realized = cec_pour_plan._box(0.0, 0.0, 2.0, 2.0)
    records = [{
        "geometry": cec_pour_plan._box(1.0, 1.0, 3.0, 3.0),
        "owner": "U7", "kind": "footprint", "detail": "pad 3",
        "net": "/FOREIGN",
    }, {
        "geometry": cec_pour_plan._box(5.0, 5.0, 6.0, 6.0),
        "owner": "C9", "kind": "footprint", "detail": "pad 1",
        "net": "/OTHER",
    }]

    clashes = cec_pour_plan._exact_clearance_clash_evidence(
        realized, records)

    assert clashes == [{
        "owner": "U7", "kind": "footprint", "detail": "pad 3",
        "net": "/FOREIGN", "intersection_area_mm2": 1.0,
        "intersection_bounds_mm": [1.0, 1.0, 2.0, 2.0],
    }]


def test_exact_bundle_neck_does_not_unguard_exact_obstacle():
    region = cec_pour_plan._box(0.0, 0.0, 10.0, 10.0)
    obstacle = cec_pour_plan._box(4.0, 0.0, 6.0, 10.0)
    approach = region

    exact = cec_pour_plan._LayerSpace(
        region, [obstacle], 3.0, approach=approach,
        half_neck=cec_pour_plan.W_NECK / 2.0, neck_unguard=0.0)

    assert not exact.ok_line((2.0, 5.0), (8.0, 5.0))


def test_outer_pour_obstacles_include_foreign_component_courtyard():
    class Courtyard:
        def __init__(self, bounds):
            self._box = cec_pour_plan._box(*bounds)
            self._bbox = type("BBox", (), {
                "GetLeft": lambda _self: int(bounds[0] * MM),
                "GetTop": lambda _self: int(bounds[1] * MM),
                "GetRight": lambda _self: int(bounds[2] * MM),
                "GetBottom": lambda _self: int(bounds[3] * MM),
            })()

        def OutlineCount(self):
            return 1

        def BBox(self):
            return self._bbox

    class BodyFP(_FP):
        def __init__(self, ref, pads, bounds):
            super().__init__(ref, pads)
            self._courtyard = Courtyard(bounds)

        def IsFlipped(self):
            return False

        def GetCourtyard(self, _layer):
            return self._courtyard

    board = _Board(30, 20, [
        BodyFP("U7", [_Pad("/FOREIGN", 2, 11.0, 11.0)],
               (10.0, 10.0, 12.0, 12.0)),
        BodyFP("U8", [_Pad("+RAIL", 1, 16.0, 11.0)],
               (15.0, 10.0, 17.0, 12.0)),
        BodyFP("J9", [_Pad("/FOREIGN", 2, 21.0, 11.0)],
               (20.0, 10.0, 22.0, 12.0)),
    ], {1: "+RAIL", 2: "/FOREIGN"})

    records = cec_pour_plan._geo_obstacle_records(
        board, 1, ("F.Cu",), 0.2, 0.1)["F.Cu"]
    bodies = [row for row in records
              if row["kind"] == "footprint_body"]

    assert [row["owner"] for row in bodies] == ["U7"]
    assert tuple(round(value, 3)
                 for value in bodies[0]["geometry"].bounds) == (
                     9.7, 9.7, 12.3, 12.3)


def test_neck_main_clip_preserves_small_reserved_via_hole():
    region = cec_pour_plan._box(0.0, 0.0, 10.0, 10.0)
    obstacle = cec_pour_plan._box(4.5, 4.5, 5.5, 5.5)
    space = cec_pour_plan._LayerSpace(
        region, [obstacle], 3.0, approach=region,
        half_neck=cec_pour_plan.W_NECK / 2.0, neck_unguard=0.0)
    corridor = SimpleNamespace(ga=SimpleNamespace(), gb=SimpleNamespace())
    state = {"reqw": {"B.Cu": 6.0}, "spaces": {"B.Cu": space}}

    part = cec_pour_plan._cand_from_path(
        corridor, state, "B.Cu", [(3.0, 4.0), (7.0, 4.0)], 0,
        None, space=space)

    assert part is not None
    assert part["main"].intersection(obstacle).area <= 1e-9
    assert part["spine"].intersection(obstacle).area <= 1e-9


def _tht_col(net, nc, x, ys):
    return [_Pad(net, nc, x, y) for y in ys]


def _recorder():
    calls = []

    def fb(board, ask, sub):
        calls.append(ask.get("net"))
        return [], [], {"path_found": False, "reason": "recorded"}
    return calls, fb


class TestStraightCorridor(unittest.TestCase):
    def _board(self, with_wall=False):
        nc = 1
        fps = [_FP("J1", _tht_col("+5V_MAIN", nc, 6.0, [4.0, 7.0, 10.0, 13.0])),
               _FP("TB1", _tht_col("+5V_MAIN", nc, 34.0, [4.0, 7.0, 10.0,
                                                          13.0]))]
        if with_wall:
            # foreign THT picket x~19-21 leaving a gap only at the bottom
            fps.append(_FP("W1", _wall(2, 19.0, 21.0, 0.5, 12.0)))
        return _Board(40, 20, fps, {nc: "+5V_MAIN", 2: "GND"})

    def test_open_board_is_one_straight_corridor_no_fields(self):
        board = self._board()
        collect = {}
        pours, vias, rep = plan_pours(
            board, [{"net": "+5V_MAIN", "layers": ("In2.Cu",)}],
            collect=collect)
        e = rep["+5V_MAIN"]
        self.assertTrue(e["path_found"], e)
        self.assertEqual(e["corridors"], 1)
        self.assertEqual(e["bends"], 0, "two manifolds on an open board "
                                        "connect STRAIGHT")
        self.assertEqual(e["via_fields"], {"terminal": 0, "crossing": 0},
                         "THT manifolds anchor every layer: no via fields")
        self.assertEqual(vias, [])
        mine = [d for d in pours if d["net"] == "+5V_MAIN"]
        self.assertTrue(any(d["provenance"] == "pourplan" and
                            d["name"] == "pourplan:+5V_MAIN" for d in mine),
                        [d.get("name") for d in mine])
        self.assertTrue(any(str(d.get("name", "")).startswith("manifold:")
                            for d in mine), "stage-0 manifolds still lead")
        self.assertEqual(
            set(collect), {"_grid", "+5V_MAIN"},
            "collect is a legacy per-net state map; global diagnostics must "
            "not masquerade as a net entry")

    def test_wall_forces_one_bend_on_the_corner_graph(self):
        board = self._board(with_wall=True)
        pours, _v, rep = plan_pours(
            board, [{"net": "+5V_MAIN", "layers": ("In2.Cu",)}])
        e = rep["+5V_MAIN"]
        self.assertTrue(e["path_found"], e)
        self.assertEqual(e["corridors"], 1)
        self.assertGreaterEqual(e["bends"], 1, "the picket forces a bend")
        self.assertLessEqual(e["bends"], 2, "corner-graph path stays "
                                            "purposeful (L-ish), never a "
                                            "cell-walk staircase")
        for pour in pours:
            self.assertEqual(
                cec_pour_plan._diagonal_edges(pour["polygon"]), [],
                "%s must have exact 90-degree boundaries" %
                pour.get("name", pour.get("net")))

    def test_output_contract_rejects_diagonal_pour_edges(self):
        with self.assertRaisesRegex(RuntimeError, "non-Manhattan"):
            cec_pour_plan._assert_manhattan_pours([{
                "net": "/BAD", "layer": "B.Cu", "name": "test:/BAD",
                "polygon": [(0, 0), (2, 1), (2, 2), (0, 2), (0, 0)],
            }])

    def test_future_decoupler_via_column_blocks_every_spanned_layer(self):
        primitive = {
            "kind": "via", "net": "+3V3", "net_code": 7,
            "owner": "U1", "cap": "C1", "at_mm": [10.0, 12.0],
            "diameter_mm": 0.35,
            "layer_ids": [_LAY["F.Cu"], _LAY["B.Cu"]],
        }
        out = {"F.Cu": [], "B.Cu": []}
        cec_pour_plan._append_access_primitive_records(
            out, [primitive],
            {"F.Cu": _LAY["F.Cu"], "B.Cu": _LAY["B.Cu"]},
            3, 0.20, 0.0)
        self.assertEqual([len(out[layer]) for layer in out], [1, 1])
        self.assertEqual(
            {out[layer][0]["kind"] for layer in out},
            {"future_decoupler_access"})
        self.assertEqual(
            {out[layer][0]["owner"] for layer in out}, {"C1"})
        self.assertAlmostEqual(
            (out["F.Cu"][0]["geometry"].bounds[2]
             - out["F.Cu"][0]["geometry"].bounds[0]) / 2.0,
            0.35 / 2.0 + 0.20, places=6)

        ground_portal = dict(
            primitive, net="GND", net_code=3, owner="U2", cap=None,
            pad="8", purpose="ground_plane_access")
        attributed = {"F.Cu": [], "B.Cu": []}
        cec_pour_plan._append_access_primitive_records(
            attributed, [ground_portal],
            {"F.Cu": _LAY["F.Cu"], "B.Cu": _LAY["B.Cu"]},
            7, 0.20, 0.0)
        self.assertEqual(
            {attributed[layer][0]["owner"] for layer in attributed},
            {"U2"})
        self.assertEqual(
            {attributed[layer][0]["detail"] for layer in attributed},
            {"ground-plane-access:U2.8 via"})

        own_net = {"F.Cu": [], "B.Cu": []}
        cec_pour_plan._append_access_primitive_records(
            own_net, [primitive],
            {"F.Cu": _LAY["F.Cu"], "B.Cu": _LAY["B.Cu"]},
            7, 0.20, 0.0)
        self.assertEqual(own_net, {"F.Cu": [], "B.Cu": []})

    def test_priority_access_reserves_complete_bypass_cell(self):
        bypass = {
            "kind": "via", "net": "GND", "owner": "U1", "cap": "C1",
            "purpose": "bypass_cell",
        }
        supply = {
            "kind": "track", "net": "+3V3", "owner": "U1", "cap": "C1",
            "purpose": "bypass_cell",
        }
        portal = {
            "kind": "via", "net": "GND", "owner": "U2", "pad": "8",
            "purpose": "ground_plane_access",
        }

        immutable, deferred = cec_pour_plan._priority_access_primitives(
            [portal, bypass, supply])

        self.assertEqual(immutable, (bypass, supply))
        self.assertEqual(deferred, (portal,))

    def test_future_kelvin_reservation_blocks_only_foreign_rails(self):
        reservation = {
            "name": "tap_RS2_U11", "purpose": "future_kelvin_tap",
            "net": "/SENSEC2_LO", "source_ref": "RS2",
            "target_ref": "U11", "x0": 10.0, "y0": 4.0,
            "x1": 18.0, "y1": 5.0, "layers": ("F.Cu",),
        }
        foreign = {"F.Cu": [], "B.Cu": []}
        count = cec_pour_plan._append_owned_rect_reservation_records(
            foreign, [reservation], "/SENSEC2_HI",
            kind="future_kelvin_tap")
        self.assertEqual(count, 1)
        self.assertEqual(len(foreign["F.Cu"]), 1)
        self.assertEqual(foreign["F.Cu"][0]["net"], "/SENSEC2_LO")
        self.assertEqual(foreign["F.Cu"][0]["owner"], "U11")
        self.assertEqual(foreign["F.Cu"][0]["kind"],
                         "future_kelvin_tap")

        own = {"F.Cu": [], "B.Cu": []}
        own_count = cec_pour_plan._append_owned_rect_reservation_records(
            own, [reservation], "/SENSEC2_LO",
            kind="future_kelvin_tap")
        self.assertEqual(own_count, 0)
        self.assertEqual(own, {"F.Cu": [], "B.Cu": []})

    def test_power_reservation_halo_keeps_foreign_owned_route_notch(self):
        rows = [{
            "net": "/SENSEC2_HI", "layer": "F.Cu",
            "polygon": [(0.0, 0.0), (8.0, 0.0),
                        (8.0, 4.0), (0.0, 4.0)],
            "x0": 0.0, "y0": 0.0, "x1": 8.0, "y1": 4.0,
        }]
        future = [{
            "net": "/SENSEC2_LO", "layers": ("F.Cu",),
            "x0": 3.0, "y0": 1.0, "x1": 6.0, "y1": 3.0,
        }]
        clipped, count, dropped = (
            cec_pour_plan._sp.clip_reservations_around_owned_routes(
                rows, future))
        self.assertEqual((count, dropped), (1, 0))
        source = cec_pour_plan.Polygon(rows[0]["polygon"])
        notch = cec_pour_plan._box(3.0, 1.0, 6.0, 3.0)
        cover = cec_pour_plan.unary_union([
            cec_pour_plan.Polygon(row["polygon"]) for row in clipped])
        self.assertLessEqual(cover.intersection(notch).area, 1e-9)
        self.assertLessEqual(
            cover.symmetric_difference(source.difference(notch)).area,
            1e-9)

        own, own_count, own_dropped = (
            cec_pour_plan._sp.clip_reservations_around_owned_routes(
                rows, [dict(future[0], net="/SENSEC2_HI")]))
        self.assertEqual((own_count, own_dropped), (0, 0))
        self.assertEqual(own, rows)

    def test_diagonal_clip_uses_one_inside_elbow_not_a_staircase(self):
        poly = cec_pour_plan.Polygon(
            [(0, 0), (5, 0), (5, 5), (3, 5), (2, 4), (0, 4)])
        emitted = cec_pour_plan._emit_rectilinear(poly)
        self.assertEqual([], cec_pour_plan._diagonal_edges(
            emitted.exterior.coords))
        self.assertLessEqual(len(emitted.exterior.coords),
                             len(poly.exterior.coords) + 1)
        self.assertTrue(poly.buffer(1e-6).covers(emitted))

    def test_rectilinear_barrel_restore_is_additive_and_manhattan(self):
        original = cec_pour_plan._box(0, 0, 4, 4)
        rect = cec_pour_plan._box(0, 0, 3.7, 4)
        barrel = cec_pour_plan.Point(3.7, 2).buffer(0.2)
        restored = cec_pour_plan._restore_rectilinear_barrels(
            rect, original, [barrel], region=original)
        self.assertIsNotNone(restored)
        self.assertTrue(restored.buffer(0.01).covers(barrel))
        self.assertEqual([], cec_pour_plan._diagonal_edges(
            restored.exterior.coords))

    def test_rectilinear_barrel_restore_respects_foreign_clearance(self):
        original = cec_pour_plan._box(0, 0, 4, 4)
        rect = cec_pour_plan._box(0, 0, 3.7, 4)
        barrel = cec_pour_plan.Point(3.7, 2).buffer(0.2)
        forbidden = cec_pour_plan._box(3.75, 1.5, 4.0, 2.5)
        self.assertIsNone(cec_pour_plan._restore_rectilinear_barrels(
            rect, original, [barrel], forbidden=forbidden,
            region=original))

    def test_assignment_never_trades_a_valid_route_for_lower_cost_open(self):
        class Group:
            native = {"B.Cu", "F.Cu"}

        cor = cec_pour_plan._Corridor("/PWR", Group(), Group())
        cor.cands = [{
            "layer": "B.Cu",
            "bundle_layers": ("B.Cu", "F.Cu"),
            "bundle_parts": {
                "B.Cu": {"poly": cec_pour_plan._box(0, 0, 2, 20)},
                "F.Cu": {"poly": cec_pour_plan._box(0, 0, 2, 20)},
            },
            "poly": cec_pour_plan._box(0, 0, 2, 20),
            "bends": 100,
            "length": 1000.0,
        }]
        nets = {"/PWR": {"corridors": [cor]}}
        cec_pour_plan._assign_layers(nets, ["/PWR"])
        self.assertIsNotNone(
            cor.pick,
            "route completion must dominate every route-quality cost")

    def test_endpoint_alternates_optimize_success_not_only_failure(self):
        """A routable default endpoint must not freeze a needless dogleg."""
        space = cec_pour_plan._LayerSpace(
            cec_pour_plan._box(0, 0, 30, 20), [], 0.5)
        default_b = (24.0, 13.0)
        aligned_b = (24.0, 10.0)
        default, bends0 = cec_pour_plan._find_path(
            space, (4.0, 10.0), default_b)
        chosen, bends = cec_pour_plan._path_with_alternates(
            space, (4.0, 10.0), (), default_b, (aligned_b,))
        self.assertIsNotNone(default)
        self.assertEqual(bends0, 1)
        self.assertEqual(bends, 0)
        self.assertEqual(chosen[-1], aligned_b,
                         "joint endpoint selection should align the landing "
                         "with the trunk instead of accepting a routable L")

    def test_broad_terminal_projection_adds_exact_straight_pair(self):
        """Overlapping width-eroded terminals must not become a C staircase."""
        a = cec_pour_plan._Group(1)
        b = cec_pour_plan._Group(2)
        for g, bbox in ((a, (0.0, 0.0, 10.0, 6.0)),
                        (b, (2.0, 14.0, 12.0, 20.0))):
            g.bbox = bbox
            g.cx = (bbox[0] + bbox[2]) / 2.0
            g.cy = (bbox[1] + bbox[3]) / 2.0
            g.native = {"F.Cu"}
            g.attach = cec_pour_plan._box(*bbox)
        space = cec_pour_plan._LayerSpace(
            cec_pour_plan._box(-2, -2, 14, 22), [], 2.0)
        pairs = cec_pour_plan._projection_aligned_pairs(
            a, b, "F.Cu", {"reqw": {"F.Cu": 4.0},
                             "region": cec_pour_plan._box(-2, -2, 14, 22)},
            space)
        self.assertTrue(pairs)
        self.assertTrue(all(abs(pa[0] - pb[0]) <= 1e-6
                            for pa, pb in pairs))
        chosen, bends = cec_pour_plan._path_with_alternates(
            space, (2.0, 2.0), (), (10.0, 18.0), (), pairs)
        self.assertEqual(bends, 0)
        self.assertEqual(chosen[0][0], chosen[-1][0])

    def test_orthogonal_cleanup_flattens_shallow_patch_band(self):
        # Three same-net rectangles whose lower edges differ by 0.15/0.07 mm:
        # the exact real-board mechanism behind the visible shunt-pad dip.
        shape = cec_pour_plan.unary_union([
            cec_pour_plan._box(0, 0, 4, 10.00),
            cec_pour_plan._box(4, 0, 8, 10.15),
            cec_pour_plan._box(8, 0, 12, 10.08),
        ])
        clean, stats = cec_pour_plan._orthogonal_cleanup(
            shape, 0.2, region=cec_pour_plan._box(-1, -1, 13, 12))
        pts = list(clean.exterior.coords)
        minx, _miny, maxx, _maxy = clean.bounds
        micro_vertical = [
            (a, b) for a, b in zip(pts, pts[1:])
            if abs(a[0] - b[0]) <= 1e-6
            and minx + 1e-6 < a[0] < maxx - 1e-6
            and 1e-6 < abs(a[1] - b[1]) <= 0.25]
        self.assertEqual(micro_vertical, [])
        self.assertGreaterEqual(stats["micro_fills"], 2)
        self.assertGreater(clean.area, shape.area)

    def test_orthogonal_cleanup_fills_only_clear_inside_elbow(self):
        shape = cec_pour_plan._poly_of([
            (0, 0), (10, 0), (10, 4), (6, 4),
            (6, 8), (0, 8), (0, 0),
        ])
        region = cec_pour_plan._box(-1, -1, 11, 9)
        clean, stats = cec_pour_plan._orthogonal_cleanup(
            shape, 8.0, region=region, allow_elbow_fills=True)
        self.assertTrue(clean.equals(cec_pour_plan._box(0, 0, 10, 8)))
        self.assertEqual(stats["elbow_fills"], 1)
        blocked, stats2 = cec_pour_plan._orthogonal_cleanup(
            shape, 8.0, forbidden=cec_pour_plan._box(7, 5, 8, 6),
            region=region, allow_elbow_fills=True)
        self.assertEqual(blocked, shape)
        self.assertEqual(stats2["elbow_fills"], 0)

    def test_default_cleanup_preserves_large_placement_hook(self):
        shape = cec_pour_plan._poly_of([
            (0, 0), (10, 0), (10, 4), (6, 4),
            (6, 8), (0, 8), (0, 0),
        ])
        clean, stats = cec_pour_plan._orthogonal_cleanup(
            shape, 8.0, region=cec_pour_plan._box(-1, -1, 11, 9))
        self.assertTrue(clean.equals(shape))
        self.assertEqual(stats["elbow_fills"], 0)


class TestOverlapForcesLayers(unittest.TestCase):
    def test_crossing_nets_take_distinct_layers(self):
        # net A horizontal, net B vertical, crossing mid-board: candidate
        # capsules overlap in 2D, so zero-same-layer-overlap forces them
        # onto different layers -- and NO via field (different nets on
        # different layers cross for free).
        fps = [_FP("U1", [_Pad("/A", 1, 5.0, 10.0)]),
               _FP("U2", [_Pad("/A", 1, 35.0, 10.0)]),
               _FP("U3", [_Pad("/B", 3, 20.0, 3.0)]),
               _FP("U4", [_Pad("/B", 3, 20.0, 17.0)])]
        board = _Board(40, 20, fps, {1: "/A", 3: "/B"})
        _p, vias, rep = plan_pours(
            board, [{"net": "/A", "layers": ("In2.Cu",)},
                    {"net": "/B", "layers": ("In2.Cu",)}])
        self.assertTrue(rep["/A"]["path_found"], rep["/A"])
        self.assertTrue(rep["/B"]["path_found"], rep["/B"])
        la = set(rep["/A"]["layers_used"])
        lb = set(rep["/B"]["layers_used"])
        self.assertTrue(la.isdisjoint(lb),
                        "overlapping corridors must sit on distinct layers "
                        "(A=%s B=%s)" % (la, lb))
        self.assertEqual(vias, [], "THT terminals + distinct layers: no "
                                   "via field anywhere")


class TestForcedCrossing(unittest.TestCase):
    def test_split_yields_exactly_one_crossing_field(self):
        # /AVERT is forced onto In2 (B-only foreign walls swallow its pads
        # on B), /BVERT is forced onto B (In2-only walls), /XNET crosses
        # BOTH -- no single conflict-free layer exists, so it must SPLIT at
        # ONE defined crossing with ONE compact via field there. F.Cu is
        # choked away mid-board by a far-corner shunt.
        nc_x, nc_a, nc_b = 1, 3, 4
        fps = [
            _FP("U1", [_Pad("/XNET", nc_x, 4.0, 10.0)]),
            _FP("U2", [_Pad("/XNET", nc_x, 44.0, 10.0)]),
            _FP("U3", [_Pad("/AVERT", nc_a, 16.0, 2.0)]),
            _FP("U4", [_Pad("/AVERT", nc_a, 16.0, 18.0)]),
            _FP("U5", [_Pad("/BVERT", nc_b, 32.0, 2.0)]),
            _FP("U6", [_Pad("/BVERT", nc_b, 32.0, 18.0)]),
            # B-only walls around /AVERT's pads (gap at y~10 for /XNET)
            _FP("W1", _wall(5, 13.0, 19.0, 0.5, 6.5, half=0.7)),
            _FP("W2", _wall(5, 13.0, 19.0, 13.5, 19.5, half=0.7)),
            # In2-only walls around /BVERT's pads
            _FP("W3", _wall(6, 29.0, 35.0, 0.5, 6.5, half=0.7)),
            _FP("W4", _wall(6, 29.0, 35.0, 13.5, 19.5, half=0.7)),
            # far-corner shunt: F.Cu becomes shunt-neighborhood-only
            _FP("RS9", [_Pad("/SH_HI", 8, 43.5, 3.0),
                        _Pad("/SH_LO", 9, 45.5, 3.0)]),
        ]
        for fp in fps:
            if fp.GetReference() in ("W1", "W2"):
                for p in fp.Pads():
                    p._ls = type(p._ls)(B_CU)          # B-only foreign
            if fp.GetReference() in ("W3", "W4"):
                for p in fp.Pads():
                    p._ls = type(p._ls)(IN2_CU)        # In2-only foreign
        board = _Board(48, 20, fps,
                       {nc_x: "/XNET", nc_a: "/AVERT", nc_b: "/BVERT",
                        5: "GNDB", 6: "GNDI", 8: "/SH_HI", 9: "/SH_LO"})
        _p, vias, rep = plan_pours(
            board, [{"net": "/XNET", "layers": ("In2.Cu",)},
                    {"net": "/AVERT", "layers": ("In2.Cu",)},
                    {"net": "/BVERT", "layers": ("In2.Cu",)}])
        self.assertTrue(rep["/AVERT"]["path_found"], rep["/AVERT"])
        self.assertTrue(rep["/BVERT"]["path_found"], rep["/BVERT"])
        self.assertEqual(rep["/AVERT"]["layers_used"], ["In2.Cu"])
        self.assertEqual(rep["/BVERT"]["layers_used"], ["B.Cu"])
        ex = rep["/XNET"]
        self.assertTrue(ex["path_found"], ex)
        self.assertNotIn("fallback", ex, "a split is a PLAN, not a fallback")
        self.assertEqual(ex["via_fields"]["crossing"], 1,
                         "exactly ONE via field at the defined crossing: %r"
                         % ex)
        self.assertEqual(ex["via_fields"]["terminal"], 0,
                         "THT terminals need no fields")
        xv = [v for v in vias if v["net"] == "/XNET"]
        self.assertTrue(xv, "the crossing field lays real vias")
        self.assertTrue(all(4.0 < v["x_mm"] < 44.0 for v in xv),
                        "field sits at the crossing point, mid-run: %r" % xv)
        self.assertLessEqual(len(xv), 3, "COMPACT array, never smeared")


class TestVerifierRejectsThin(unittest.TestCase):
    def test_thin_corridor_fails_min_width_and_falls_back(self):
        # sabotage realization: capsules at quarter width. The exact
        # geometric erosion (min-width invariant) must reject every
        # corridor and the net must fall back -- loudly labeled.
        nc = 1
        fps = [_FP("J1", _tht_col("+5V", nc, 6.0, [8.0, 11.0])),
               _FP("TB1", _tht_col("+5V", nc, 34.0, [8.0, 11.0]))]
        board = _Board(40, 20, fps, {nc: "+5V"})
        calls, fb = _recorder()
        real = cec_pour_plan._capsule
        try:
            cec_pour_plan._capsule = lambda pts, hw: real(pts, hw / 4.0)
            _p, _v, rep = plan_pours(
                board, [{"net": "+5V", "layers": ("In2.Cu",)}], fallback=fb)
        finally:
            cec_pour_plan._capsule = real
        e = rep["+5V"]
        self.assertEqual(calls, ["+5V"], "fallback must fire for the net")
        self.assertEqual(e.get("fallback"), "route_overunder")
        self.assertIn("min-width", str(e.get("planner_reason")),
                      "the rejection names the violated invariant: %r" % e)


class TestFallbackOnlyOnFailure(unittest.TestCase):
    def test_healthy_net_plans_walled_net_falls_back(self):
        nc_h, nc_w = 1, 3
        fps = [
            _FP("U1", [_Pad("/H", nc_h, 5.0, 16.0)]),
            _FP("U2", [_Pad("/H", nc_h, 12.0, 16.0)]),
            _FP("U3", [_Pad("/W", nc_w, 5.0, 3.0)]),
            _FP("U4", [_Pad("/W", nc_w, 35.0, 3.0)]),
            # hermetic full-height THT wall between /W's pads (blocks every
            # layer; /H lives entirely left of it)
            _FP("W1", _wall(2, 19.0, 21.0, 0.5, 19.5)),
        ]
        board = _Board(40, 20, fps, {nc_h: "/H", nc_w: "/W", 2: "GND"})
        calls, fb = _recorder()
        _p, _v, rep = plan_pours(
            board, [{"net": "/H", "layers": ("In2.Cu",)},
                    {"net": "/W", "layers": ("In2.Cu",)}], fallback=fb)
        self.assertTrue(rep["/H"]["path_found"], rep["/H"])
        self.assertNotIn("fallback", rep["/H"],
                         "fallback NEVER fires on a planner success")
        self.assertEqual(calls, ["/W"],
                         "fallback fires for exactly the failed net")
        self.assertEqual(rep["/W"].get("fallback"), "route_overunder")

    def test_trivial_single_group_is_no_fallback(self):
        nc = 1
        fps = [_FP("U1", [_Pad("/T", nc, 5.0, 5.0)])]
        board = _Board(40, 20, fps, {nc: "/T"})
        calls, fb = _recorder()
        _p, _v, rep = plan_pours(
            board, [{"net": "/T", "layers": ("In2.Cu",)}], fallback=fb)
        self.assertEqual(calls, [])
        self.assertTrue(rep["/T"].get("trivial"))
        self.assertTrue(rep["/T"]["path_found"],
                        "single-cluster contract matches route_overunder")


class TestPourTermination(unittest.TestCase):
    """Pour-termination ruling (owner 2026-07-25): force copper stops AT
    the shunt pad inner edge; the inter-pad gap belongs to the taps."""

    def _rs_board(self, extra_fps=()):
        # RS1: HI pad at (10,10), LO pad at (16,10), half 0.6 -> bboxes
        # 9.4-10.6 and 15.4-16.6; gap = x 10.6..15.4
        fps = [_FP("RS1", [_Pad("/S_HI", 1, 10.0, 10.0,
                                layers=[_LAY["F.Cu"]], name="1"),
                           _Pad("/S_LO", 2, 16.0, 10.0,
                                layers=[_LAY["F.Cu"]], name="2")])]
        fps += list(extra_fps)
        nets = {1: "/S_HI", 2: "/S_LO"}
        for fp in extra_fps:
            for p in fp.Pads():
                nets.setdefault(p.GetNetCode(), p.GetNetname())
        return _Board(40, 20, fps, nets)

    def test_patch_clips_at_pad_inner_edge_not_mid_gap(self):
        import cec_slab_pour
        patches = cec_slab_pour.guaranteed_shunt_patches(self._rs_board())
        self.assertEqual({patch["priority"] for patch in patches}, {3})
        self.assertEqual({patch["owner_ref"] for patch in patches}, {"RS1"})
        by_net = {d["net"]: d["polygon"] for d in patches}
        hi_xs = [q[0] for q in by_net["/S_HI"]]
        lo_xs = [q[0] for q in by_net["/S_LO"]]
        self.assertAlmostEqual(max(hi_xs), 10.6, places=3,
                               msg="HI inner clip = the PAD INNER EDGE "
                                   "(mid-gap 12.85 is the retired rule)")
        self.assertAlmostEqual(min(lo_xs), 15.4, places=3)
        # outer/side margins keep covering the outboard via rows
        self.assertAlmostEqual(min(hi_xs), 10.0 - 0.6 - 4.5, places=3)
        ys = [q[1] for q in by_net["/S_HI"]]
        self.assertAlmostEqual(min(ys), 10.0 - 0.6 - 4.5, places=3)
        self.assertAlmostEqual(max(ys), 10.0 + 0.6 + 4.5, places=3)
        # the gap strip helper names the taps' exclusive territory
        halves = cec_slab_pour._shunt_pad_halves(self._rs_board())
        self.assertEqual(len(halves), 1)
        gx0, gy0, gx1, gy1 = halves[0]["gap"]
        self.assertAlmostEqual(gx0, 10.6, places=3)
        self.assertAlmostEqual(gx1, 15.4, places=3)

    def test_patch_margin_stops_before_foreign_pad(self):
        import cec_slab_pour
        blocker = _FP("C1", [_Pad("GND", 3, 7.0, 10.0,
                                   layers=[_LAY["F.Cu"]])])
        patches = cec_slab_pour.guaranteed_shunt_patches(
            self._rs_board(extra_fps=(blocker,)))
        hi = next(row for row in patches if row["net"] == "/S_HI")
        xs = [point[0] for point in hi["polygon"]]
        self.assertTrue(hi["obstacle_limited"])
        self.assertLess(hi["patch_margin_mm"], 4.5)
        self.assertGreaterEqual(min(xs), 7.0 + 0.6 + 0.20)
        self.assertEqual(hi["foreign_clearance_mm"], 0.20)

    def test_patch_margin_stops_before_foreign_component_courtyard(self):
        import cec_slab_pour

        class Courtyard:
            def __init__(self):
                self._bbox = type("BBox", (), {
                    "GetLeft": lambda _self: int(6.0 * MM),
                    "GetTop": lambda _self: int(9.0 * MM),
                    "GetRight": lambda _self: int(8.0 * MM),
                    "GetBottom": lambda _self: int(11.0 * MM),
                })()

            def OutlineCount(self):
                return 1

            def BBox(self):
                return self._bbox

        class BodyFP(_FP):
            def IsFlipped(self):
                return False

            def GetCourtyard(self, _layer):
                return Courtyard()

        blocker = BodyFP("C1", [
            _Pad("GND", 3, 6.5, 10.0, layers=[_LAY["F.Cu"]])])
        patches = cec_slab_pour.guaranteed_shunt_patches(
            self._rs_board(extra_fps=(blocker,)))
        hi = next(row for row in patches if row["net"] == "/S_HI")
        xs = [point[0] for point in hi["polygon"]]

        self.assertTrue(hi["obstacle_limited"])
        self.assertGreaterEqual(min(xs), 8.0 + 0.20)
        self.assertEqual(hi["foreign_clearance_mm"], 0.20)

    def test_planned_vias_stay_out_of_pads_and_gap(self):
        # a corridor arriving from the GAP side (TB trunk at x=32) must
        # attach the patch-covered shunt pad from the OUTER face: no via
        # in any pad, none in the inter-pad gap.
        tb = _FP("TB1", [_Pad("/S_HI", 1, 32.0, 8.0),
                         _Pad("/S_HI", 1, 32.0, 11.0)])
        board = self._rs_board(extra_fps=(tb,))
        pours, vias, rep = plan_pours(
            board, [{"net": "/S_HI", "layers": ("In2.Cu",)}])
        self.assertTrue(rep["/S_HI"]["path_found"], rep["/S_HI"])
        self.assertTrue(vias, "the F-only shunt pad needs a terminal field")
        pad_boxes = [(9.4, 9.4, 10.6, 10.6), (15.4, 9.4, 16.6, 10.6),
                     (31.4, 7.4, 32.6, 8.6), (31.4, 10.4, 32.6, 11.6)]
        for v in vias:
            x, y = v["x_mm"], v["y_mm"]
            for (x0, y0, x1, y1) in pad_boxes:
                self.assertFalse(x + 0.45 >= x0 and x - 0.45 <= x1 and
                                 y + 0.45 >= y0 and y - 0.45 <= y1,
                                 "via (%.2f,%.2f) overlaps pad box %s"
                                 % (x, y, (x0, y0, x1, y1)))
            self.assertFalse(10.6 < x < 15.4 and 9.4 < y < 10.6,
                             "via (%.2f,%.2f) sits in the inter-pad gap "
                             "(tap territory)" % (x, y))
        # every pourplan F polygon respects the pad inner edge line: no
        # pourplan copper in the gap strip
        for d in pours:
            if d.get("layer") != "F.Cu" or \
                    not str(d.get("name", "")).startswith("pourplan:"):
                continue
            for (x, y) in d["polygon"]:
                self.assertFalse(10.6 + 1e-6 < x < 15.4 - 1e-6
                                 and 9.4 < y < 10.6,
                                 "pourplan F copper vertex in the gap: %s"
                                 % ((x, y),))


class TestViaInPadReseat(unittest.TestCase):
    """Via-in-pad ruling (owner 2026-07-25): assembly-class exclusion +
    reseat-beside-the-pad, never a silent drop."""

    def test_field_vias_slide_past_a_pad(self):
        import cec_slab_pour
        grid = cec_slab_pour.Grid(_Board(40, 20, [], {}), 0.8)
        # field at ~(20,10), travel +x -> via line runs in y; a pad box
        # sits exactly on the +y base slot -> that via must SLIDE, not drop
        r, c = grid.iy(10.0), grid.ix(20.0)
        cx = grid.x0 + (c + 0.5) * grid.cell
        cy = grid.y0 + (r + 0.5) * grid.cell
        field = (r, c, "In2.Cu", "F.Cu", 1.0, 0.0)
        pad = (cx - 0.5, cy + 0.2, cx + 0.5, cy + 1.0)  # swallows +0.6 slot
        vias, reseated = cec_pour_plan._field_vias(
            field, 0.6, grid, [pad], [])
        self.assertEqual(len(vias), 2, "count preserved: reseat, not drop")
        self.assertGreater(reseated, 0, "the blocked slot was slid past")
        for (x, y) in vias:
            self.assertFalse(cec_pour_plan._pad_hit([pad], x, y,
                                                    0.45 + 0.05),
                             "reseated via still overlaps the pad")

    def test_all_slots_blocked_is_loud_empty_never_silent(self):
        import cec_slab_pour
        grid = cec_slab_pour.Grid(_Board(40, 20, [], {}), 0.8)
        r, c = grid.iy(10.0), grid.ix(20.0)
        cx = grid.x0 + (c + 0.5) * grid.cell
        cy = grid.y0 + (r + 0.5) * grid.cell
        field = (r, c, "In2.Cu", "F.Cu", 1.0, 0.0)
        pad = (cx - 3.0, cy - 3.0, cx + 3.0, cy + 3.0)  # swallows all slots
        vias, _rs = cec_pour_plan._field_vias(field, 0.6, grid, [pad], [])
        self.assertEqual(vias, [], "total exhaustion returns [] -- the "
                                   "attach-connectivity verifier then "
                                   "fails the net (loud), never a via in "
                                   "the pad")


class TestCollectContract(unittest.TestCase):
    def test_collect_carries_reservation_internals(self):
        nc = 1
        fps = [_FP("J1", _tht_col("+5V", nc, 6.0, [8.0, 11.0])),
               _FP("TB1", _tht_col("+5V", nc, 34.0, [8.0, 11.0]))]
        board = _Board(40, 20, fps, {nc: "+5V"})
        collect = {}
        plan_pours(board, [{"net": "+5V", "layers": ("In2.Cu",)}],
                   collect=collect)
        self.assertIn("_grid", collect)
        ci = collect["+5V"]
        self.assertTrue(ci["ok"])
        self.assertTrue(any(m.any() for m in ci["path_cells"].values()))
        self.assertIn("foreign", ci)
        self.assertIn("reqw", ci)
        # the reservation consumer runs on it unmodified
        import cec_slab_pour
        cors, reserved = cec_slab_pour.reservation_from_search(
            "+5V", ci["ok"], ci["path_cells"], ci["bridges"], ci["rcells"],
            ci["foreign"], collect["_grid"])
        self.assertTrue(reserved)
        self.assertTrue(all(c["net"] == "+5V" for c in cors))


_IN_CONTAINER = (os.path.exists("/.dockerenv")
                 or os.path.exists("/run/.containerenv"))
try:
    import pcbnew as _pcbnew_mod
except ImportError:
    _pcbnew_mod = None


@unittest.skipUnless(_pcbnew_mod is not None and _IN_CONTAINER,
                     "pcbnew + the routing container required")
class TestViaInPadExclusionRealBoard(unittest.TestCase):
    """cec_fr side of the via-in-pad ruling: _via_pad_excluded /
    _via_spot_clear / add_overunder_vias on a real mini board."""

    def _board(self, tmp):
        import pcbnew
        board = pcbnew.CreateEmptyBoard()
        for (a, b) in (((0, 0), (40, 0)), ((40, 0), (40, 20)),
                       ((40, 20), (0, 20)), ((0, 20), (0, 0))):
            seg = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_SEGMENT)
            seg.SetStart(pcbnew.VECTOR2I(int(a[0] * MM), int(a[1] * MM)))
            seg.SetEnd(pcbnew.VECTOR2I(int(b[0] * MM), int(b[1] * MM)))
            seg.SetLayer(pcbnew.Edge_Cuts)
            board.Add(seg)
        net = pcbnew.NETINFO_ITEM(board, "+5V_TEST")
        board.Add(net)
        fp = pcbnew.FOOTPRINT(board)
        fp.SetPosition(pcbnew.VECTOR2I(int(10 * MM), int(10 * MM)))
        pad = pcbnew.PAD(fp)
        pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(pcbnew.VECTOR2I(int(2.0 * MM), int(1.0 * MM)))
        pad.SetPosition(pcbnew.VECTOR2I(int(10 * MM), int(10 * MM)))
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetLayerSet(pcbnew.PAD.SMDMask())
        pad.SetNetCode(net.GetNetCode())
        fp.Add(pad)
        board.Add(fp)
        path = os.path.join(tmp, "viainpad-mini.kicad_pcb")
        _pcbnew_mod.SaveBoard(path, board)
        return _pcbnew_mod.LoadBoard(path), net.GetNetCode()

    def test_same_net_pad_refuses_and_beside_is_clear(self):
        import tempfile
        import pcbnew
        import cec_fr
        board, nc = self._board(tempfile.mkdtemp(prefix="cec_vip_"))
        in_pad = pcbnew.VECTOR2I(int(10 * MM), int(10 * MM))
        beside = pcbnew.VECTOR2I(int(13 * MM), int(10 * MM))
        self.assertIsNotNone(cec_fr._via_pad_excluded(board, in_pad,
                                                      int(0.9 * MM)))
        self.assertIsNone(cec_fr._via_pad_excluded(board, beside,
                                                   int(0.9 * MM)))
        # _via_spot_clear inherits it even with the pad's OWN net exempt
        self.assertFalse(cec_fr._via_spot_clear(board, in_pad,
                                                int(0.9 * MM),
                                                int(0.3 * MM), {nc}))
        self.assertTrue(cec_fr._via_spot_clear(board, beside,
                                               int(0.9 * MM),
                                               int(0.3 * MM), {nc}))
        # add_overunder_vias refuses the in-pad spot, lays the clear one
        added = cec_fr.add_overunder_vias(
            board, [{"net": "+5V_TEST", "x_mm": 10.0, "y_mm": 10.0},
                    {"net": "+5V_TEST", "x_mm": 13.0, "y_mm": 10.0}])
        self.assertEqual(len(added), 1)
        p = added[0].GetPosition()
        self.assertAlmostEqual(p.x / MM, 13.0, places=2)
        self.assertTrue(added[0].IsLocked())

    def test_overunder_ledger_accounts_for_existing_barrel_diameter(self):
        import tempfile
        import pcbnew
        import cec_fr
        board, _nc = self._board(tempfile.mkdtemp(prefix="cec_via_ledger_"))
        other = pcbnew.NETINFO_ITEM(board, "+OTHER")
        board.Add(other)
        old = pcbnew.PCB_VIA(board)
        old.SetPosition(pcbnew.VECTOR2I(int(20.0 * MM), int(10.0 * MM)))
        old.SetDrill(int(0.6 * MM))
        old.SetWidth(int(1.2 * MM))
        old.SetNetCode(other.GetNetCode())
        old.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        board.Add(old)
        added = cec_fr.add_overunder_vias(
            board, [{"net": "+5V_TEST", "x_mm": 21.1, "y_mm": 10.0}])
        self.assertEqual(added, [],
                         "1.2mm and 0.9mm barrels need 1.25mm centres at "
                         "0.20mm copper clearance")

    def test_force_vias_clear_a_long_shunt_pad(self):
        # the s464 root cause class: a LONG shunt pad swallowed the fixed
        # 1.6mm outboard base -> in-pad force vias. The fixed base pushes
        # past the pad extent and _via_pad_excluded guards each spot.
        import tempfile
        import pcbnew
        import cec_fr
        board = pcbnew.CreateEmptyBoard()
        for (a, b) in (((0, 0), (40, 0)), ((40, 0), (40, 20)),
                       ((40, 20), (0, 20)), ((0, 20), (0, 0))):
            seg = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_SEGMENT)
            seg.SetStart(pcbnew.VECTOR2I(int(a[0] * MM), int(a[1] * MM)))
            seg.SetEnd(pcbnew.VECTOR2I(int(b[0] * MM), int(b[1] * MM)))
            seg.SetLayer(pcbnew.Edge_Cuts)
            board.Add(seg)
        n_hi = pcbnew.NETINFO_ITEM(board, "/T_HI")
        n_lo = pcbnew.NETINFO_ITEM(board, "/T_LO")
        board.Add(n_hi)
        board.Add(n_lo)
        fp = pcbnew.FOOTPRINT(board)
        fp.SetReference("RS1")
        fp.SetPosition(pcbnew.VECTOR2I(int(20 * MM), int(10 * MM)))
        boxes = []
        for (name, net, cx) in (("1", n_hi, 17.5), ("2", n_lo, 22.5)):
            pad = pcbnew.PAD(fp)
            pad.SetName(name)
            pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetSize(pcbnew.VECTOR2I(int(3.4 * MM), int(1.2 * MM)))
            pad.SetPosition(pcbnew.VECTOR2I(int(cx * MM), int(10 * MM)))
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            pad.SetLayerSet(pcbnew.PAD.SMDMask())
            pad.SetNetCode(net.GetNetCode())
            fp.Add(pad)
            boxes.append((cx - 1.7, 10 - 0.6, cx + 1.7, 10 + 0.6))
        board.Add(fp)
        tmp = tempfile.mkdtemp(prefix="cec_fv_")
        path = os.path.join(tmp, "fv-mini.kicad_pcb")
        pcbnew.SaveBoard(path, board)
        board = pcbnew.LoadBoard(path)
        rep = cec_fr.synthesize_force_vias(
            board, kelvin_pairs=[("/T_HI", "/T_LO")])
        self.assertGreater(rep["vias"], 0, "vias still lay, just outboard")
        for t in board.GetTracks():
            if t.GetClass() != "PCB_VIA":
                continue
            q = t.GetPosition()
            x, y = q.x / MM, q.y / MM
            for (x0, y0, x1, y1) in boxes:
                self.assertFalse(x + 0.45 > x0 and x - 0.45 < x1 and
                                 y + 0.45 > y0 and y - 0.45 < y1,
                                 "force via (%.2f,%.2f) overlaps pad box %s"
                                 % (x, y, (x0, y0, x1, y1)))


class _Trk:
    """Fake PCB_TRACK (pre-connect teeth)."""
    def __init__(self, net, nc, x1, y1, x2, y2, w=1.5, lay="In2.Cu",
                 locked=True):
        from test_pour_first import _Pt
        self._net, self._nc, self._w = net, nc, w
        self._s, self._e = _Pt(x1, y1), _Pt(x2, y2)
        self._lay, self._locked = _LAY[lay], locked

    def GetClass(self):
        return "PCB_TRACK"

    def GetNetname(self):
        return self._net

    def GetNetCode(self):
        return self._nc

    def GetLayer(self):
        return self._lay

    def GetWidth(self):
        return int(self._w * MM)

    def GetStart(self):
        return self._s

    def GetEnd(self):
        return self._e

    def IsLocked(self):
        return self._locked


class _TrackBoard(_Board):
    def __init__(self, W, H, fps, nets_by_code, tracks=()):
        super().__init__(W, H, fps, nets_by_code)
        self._trk = list(tracks)

    def GetTracks(self):
        return list(self._trk)


class TestPreConnectedByExistingCopper(unittest.TestCase):
    """Mandate part 1 (2026-07-25, probe-measured on live skeletons): groups
    the board's own copper (locked force rails) already connects merge into
    ONE planning group -- /SENSE3V3_LO's five groups were ALL pre-connected
    and its 598mm2 s510 fallback amoeba re-solved a finished net."""

    def _board(self, with_rail):
        nc = 1
        fps = [_FP("J1", _tht_col("+5V_MAIN", nc, 6.0, [4.0, 7.0, 10.0,
                                                        13.0])),
               _FP("TB1", _tht_col("+5V_MAIN", nc, 34.0, [4.0, 7.0, 10.0,
                                                          13.0]))]
        trk = ([_Trk("+5V_MAIN", nc, 6.0, 8.5, 34.0, 8.5)]
               if with_rail else [])
        return _TrackBoard(40, 20, fps, {nc: "+5V_MAIN", 2: "GND"}, trk)

    def test_rail_connected_net_is_trivial_no_fallback(self):
        calls, fb = _recorder()
        _p, vias, rep = plan_pours(
            self._board(True), [{"net": "+5V_MAIN", "layers": ("In2.Cu",)}],
            fallback=fb)
        e = rep["+5V_MAIN"]
        self.assertTrue(e["path_found"], e)
        self.assertTrue(e.get("trivial"),
                        "rail-connected groups must merge to ONE planning "
                        "group (already-present corridor): %s" % e)
        self.assertEqual(calls, [], "no fallback for a finished net")
        self.assertEqual(vias, [])

    def test_without_the_rail_a_corridor_is_still_planned(self):
        _p, _v, rep = plan_pours(
            self._board(False), [{"net": "+5V_MAIN", "layers": ("In2.Cu",)}])
        e = rep["+5V_MAIN"]
        self.assertTrue(e["path_found"], e)
        self.assertFalse(e.get("trivial"))
        self.assertEqual(e["corridors"], 1)


class TestRegionClassNets(unittest.TestCase):
    """Mandate part 2 + single-owner 5a (2026-07-25): many-island logic
    nets take the POWER-PLANE doctrine -- ONE clean region polygon on the
    chosen inner/bottom layer + one compact terminal via field per island.
    No tree, no bridges, no snake; the ask's layer is a preference, never
    a mandate (the realized solution owns its layer)."""

    def _board(self, blanket_in2=False):
        nc = 1
        fps = [_FP("RS1", [_Pad("/S_HI", 2, 21.0, 25.5, half=1.2,
                                layers=[_LAY["F.Cu"]]),
                           _Pad("/S_LO", 3, 25.0, 25.5, half=1.2,
                                layers=[_LAY["F.Cu"]])])]
        spots = [(18, 21), (22, 21), (26, 21), (18, 25), (26, 25),
                 (18, 29), (22, 29), (26, 29)]
        for i, (x, y) in enumerate(spots):
            fps.append(_FP("C%d" % i, [_Pad("+3V3", nc, x, y, half=0.5,
                                            layers=[_LAY["F.Cu"]])]))
        if blanket_in2:
            fps.append(_FP("U9", [_Pad("GND", 9, 22.0, 25.0, half=13.0,
                                       layers=[_LAY["In2.Cu"]])]))
        return _Board(44, 44, fps, {nc: "+3V3", 2: "/S_HI", 3: "/S_LO",
                                    9: "GND"})

    def test_region_is_one_clean_plane_with_per_island_fields(self):
        pours, vias, rep = plan_pours(
            self._board(), [{"net": "+3V3", "layers": ("In2.Cu",)}])
        e = rep["+3V3"]
        self.assertTrue(e["path_found"], e)
        self.assertEqual(e.get("planner"), "territory-region", e)
        self.assertEqual(e["corridors"], 0, "no tree for a region net")
        self.assertEqual(e["via_fields"]["crossing"], 0)
        self.assertGreaterEqual(e["via_fields"]["terminal"], 6,
                                "one drop field per island")
        self.assertEqual(e.get("region_layer"), "In2.Cu")
        region = [d for d in pours if d["net"] == "+3V3"
                  and d["layer"] == "In2.Cu"]
        self.assertEqual(len(region), 1,
                         "ONE deliberate region polygon, not %d pieces"
                         % len(region))
        self.assertTrue(vias, "islands drop through via fields")

    def test_ask_layer_is_a_preference_not_a_mandate(self):
        # In2 fully blanketed by foreign copper -> the solve OWNS the layer
        # choice and lands on B; the In2-naming ask lays NO In2 copper.
        pours, _v, rep = plan_pours(
            self._board(blanket_in2=True),
            [{"net": "+3V3", "layers": ("In2.Cu",)}])
        e = rep["+3V3"]
        self.assertTrue(e["path_found"], e)
        self.assertEqual(e.get("region_layer"), "B.Cu", e)
        self.assertFalse([d for d in pours if d["net"] == "+3V3"
                          and d["layer"] == "In2.Cu"],
                         "the ask named In2 but the winning solution lives "
                         "on B -- no In2 copper may exist")


class TestWidthInfeasibleDiag(unittest.TestCase):
    def test_empty_free_space_is_the_honest_diag(self):
        # one mid-board obstacle inflated by an infeasible half-width (the
        # probe-measured In2 class: 1oz internal demands 16-46mm for the
        # heavy rails) swallows the whole region -> free space EMPTY, and
        # _make_candidates diags 'width-infeasible', never 'pa-blocked'
        from shapely.geometry import box as _sbox
        sp = cec_pour_plan._LayerSpace(
            _sbox(0, 0, 10, 10), [_sbox(4, 4, 6, 6)], 20.0)
        self.assertIsNone(sp._prep, "an obstacle inflated past the region "
                                    "span must yield EMPTY free space")


class TestOverlapViaDistribution(unittest.TestCase):
    def test_terminal_pofv_seed_is_same_net_profile_qualified(self):
        class G:
            x0 = y0 = 0.0
            cell = 1.0

        field = (2, 2, "In2.Cu", "F.Cu", 1.0, 0.0, "terminal")
        st = {
            "board": object(), "nc": 7,
            "pad_box_records": [{
                "owner": "RS1", "pad": "2", "net": "/RAIL",
                "box": (2.5, 2.5, 3.5, 3.5),
            }, {
                "owner": "U1", "pad": "4", "net": "/OTHER",
                "box": (2.0, 2.0, 3.0, 3.0),
            }],
        }
        with mock.patch.object(
                cec_pour_plan, "_pofv_spot_allowed",
                side_effect=lambda _st, point: point == (3.0, 3.0)), \
                mock.patch.object(
                    cec_pour_plan._sp, "via_clear_of_foreign_tracks",
                    return_value=True):
            self.assertEqual(
                cec_pour_plan._field_terminal_pofv_seed(
                    "/RAIL", field, st, G(), ()), [(3.0, 3.0)])
            self.assertEqual(
                cec_pour_plan._field_terminal_pofv_seed(
                    "/RAIL", field, st, G(), ((3.1, 3.0),)), [])
            self.assertEqual(
                cec_pour_plan._field_terminal_pofv_seed(
                    "/RAIL", field, st, G(), (),
                    allowed_refs={"U1"}), [])

    def test_layer_satellite_requires_pad_owned_copper_or_via_seed(self):
        from shapely.geometry import box

        component = box(0.0, 0.0, 2.0, 2.0)
        group = SimpleNamespace(
            native={"F.Cu"}, attach=box(3.0, 3.0, 4.0, 4.0))
        st = {"served": [group], "own_pours": []}
        field = (0, 0, "F.Cu", "B.Cu", 1.0, 0.0, "terminal")
        self.assertFalse(cec_pour_plan._component_physical_seeded(
            component, "B.Cu", st, [field], [[]]))
        self.assertTrue(cec_pour_plan._component_physical_seeded(
            component, "B.Cu", st, [field], [[(1.0, 1.0)]]))
        group.native.add("B.Cu")
        group.attach = box(1.0, 1.0, 3.0, 3.0)
        self.assertTrue(cec_pour_plan._component_physical_seeded(
            component, "B.Cu", st, [], []))

    def test_empty_terminal_field_is_seeded_from_proven_overlap(self):
        from shapely.geometry import Point, box

        class G:
            x0 = y0 = 0.0
            cell = 1.0

        field = (2, 2, "F.Cu", "B.Cu", 1.0, 0.0, "terminal")
        overlap = box(0.0, 0.0, 20.0, 8.0)
        seeded, moved, _before, _after = \
            cec_pour_plan._spread_field_over_overlap(
                field, [], overlap, G(), (), (), target_count=6)
        self.assertEqual(len(seeded), 6)
        self.assertEqual(moved, 6)
        self.assertTrue(all(overlap.covers(Point(p)) for p in seeded))
        xs = sorted({x for x, _y in seeded})
        ys = sorted({y for _x, y in seeded})
        self.assertEqual(len(xs) * len(ys), len(seeded))

    def test_narrow_overlap_retries_via_lattice_at_fine_phase(self):
        from shapely.geometry import Point, box

        class G:
            x0 = y0 = 0.0
            cell = 1.0

        field = (2, 2, "F.Cu", "B.Cu", 1.0, 0.0, "terminal")
        # After barrel-edge erosion this leaves x=1.50..1.70. The ordinary
        # globally phased 1.2 mm lattice has no x sample there; the bounded
        # 0.4 mm phase retry has x=1.6 and enough y extent for two barrels.
        overlap = box(1.05, 0.0, 2.15, 5.0)
        seeded, moved, _before, _after = \
            cec_pour_plan._spread_field_over_overlap(
                field, [], overlap, G(), (), (), target_count=2)
        self.assertEqual(len(seeded), 2)
        self.assertEqual(moved, 2)
        self.assertTrue(all(overlap.covers(Point(point))
                            for point in seeded))
        self.assertTrue(all(abs(x - 1.6) < 1e-6 for x, _y in seeded))

    def test_field_via_count_uses_margin_inclusive_layer_current(self):
        st = {"layer_amps": {"F.Cu": 24.375, "B.Cu": 24.375}}
        field = (2, 2, "F.Cu", "B.Cu", 1.0, 0.0, "terminal")
        self.assertEqual(
            cec_pour_plan._field_via_need(st, field, 3.2),
            cec_pour_plan._sp.vias_for_current(24.375, margin=1.0))
        self.assertEqual(
            cec_pour_plan._field_via_minimum(st, field),
            math.ceil(24.375 / cec_pour_plan._sp.VIA_AMPS))

    def test_terminal_field_becomes_uniform_overlap_lattice(self):
        from shapely.geometry import Point, box

        class G:
            x0 = y0 = 0.0
            cell = 1.0

        field = (2, 2, "F.Cu", "B.Cu", 1.0, 0.0, "terminal")
        original = [(2.0, 2.0), (3.0, 2.0), (2.0, 3.0),
                    (3.0, 3.0), (2.0, 4.0), (3.0, 4.0)]
        overlap = box(0.0, 0.0, 20.0, 8.0)
        spread, moved, before, after = \
            cec_pour_plan._spread_field_over_overlap(
                field, original, overlap, G(), (), ())
        self.assertEqual(len(spread), len(original),
                         "distribution must not add arbitrary drill count")
        self.assertGreater(moved, 0)
        self.assertGreater(after, before + 2.0,
                           "the lattice should spread beyond the compact field")
        self.assertEqual(len({x for x, _y in spread}), 3)
        self.assertEqual(len({y for _x, y in spread}), 2)
        xs = sorted({x for x, _y in spread})
        ys = sorted({y for _x, y in spread})
        self.assertEqual(set(spread), {(x, y) for x in xs for y in ys},
                         "every cell in the rectangular lattice must exist")
        self.assertAlmostEqual(xs[1] - xs[0], xs[2] - xs[1])
        self.assertAlmostEqual(xs[1] - xs[0], ys[1] - ys[0],
                               msg="lattice pitch should be isotropic")
        self.assertTrue(all(overlap.covers(Point(p)) for p in spread))

    def test_blocked_target_never_creates_staggered_near_lattice(self):
        from shapely.geometry import box

        class G:
            x0 = y0 = 0.0
            cell = 1.0

        field = (2, 2, "F.Cu", "B.Cu", 1.0, 0.0, "terminal")
        original = [(2.0, 2.0), (3.0, 2.0), (2.0, 3.0),
                    (3.0, 3.0), (2.0, 4.0), (3.0, 4.0)]
        # A pad removes some attractive central grid points. The old nearest-
        # legal assignment displaced only the affected point and emitted a
        # stagger; the replacement must translate or resize the WHOLE grid.
        blocked = ((8.0, 8.0, 10.0, 10.0),)
        spread, _moved, _before, _after = \
            cec_pour_plan._spread_field_over_overlap(
                field, original, box(0.0, 0.0, 18.0, 18.0), G(), blocked, ())
        xs = sorted({x for x, _y in spread})
        ys = sorted({y for _x, y in spread})
        self.assertEqual(len(xs) * len(ys), len(spread))
        self.assertEqual(set(spread), {(x, y) for x in xs for y in ys})
        if len(xs) > 2:
            self.assertEqual(len({round(xs[i + 1] - xs[i], 6)
                                  for i in range(len(xs) - 1)}), 1)
        if len(ys) > 2:
            self.assertEqual(len({round(ys[i + 1] - ys[i], 6)
                                  for i in range(len(ys) - 1)}), 1)

    def test_field_must_reseat_when_new_overlap_no_longer_covers_it(self):
        from shapely.geometry import Point, box

        class G:
            x0 = y0 = 0.0
            cell = 1.0

        field = (2, 2, "F.Cu", "B.Cu", 1.0, 0.0, "terminal")
        original = [(1.2, 1.2), (3.6, 1.2), (1.2, 3.6), (3.6, 3.6)]
        moved_overlap = box(10.0, 10.0, 20.0, 20.0)
        spread, moved, _before, _after = \
            cec_pour_plan._spread_field_over_overlap(
                field, original, moved_overlap, G(), (), ())
        self.assertGreater(moved, 0)
        self.assertNotEqual(spread, original)
        self.assertTrue(all(moved_overlap.covers(Point(p)) for p in spread))

    def test_crossing_field_remains_compact_at_defined_transition(self):
        from shapely.geometry import box

        class G:
            x0 = y0 = 0.0
            cell = 1.0

        field = (2, 2, "F.Cu", "B.Cu", 1.0, 0.0, "crossing")
        original = [(2.0, 2.0), (3.0, 2.0), (2.0, 3.0), (3.0, 3.0)]
        spread, moved, _before, _after = \
            cec_pour_plan._spread_field_over_overlap(
                field, original, box(0, 0, 20, 8), G(), (), ())
        self.assertEqual(spread, original)
        self.assertEqual(moved, 0)


if __name__ == "__main__":
    unittest.main()
