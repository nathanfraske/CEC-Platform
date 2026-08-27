"""General physical-placement and destructive-reconcile admission contracts."""

import copy
import math
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock


SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts")
sys.path.insert(0, SCRIPTS)

import cec_fr  # noqa: E402
import cec_synth_pipeline as synth  # noqa: E402
import pcbnew  # noqa: E402


class PlacementCraftAdmissionTests(unittest.TestCase):
    def test_route_monotonicity_accepts_boolean_gate_improvements_only(self):
        baseline = SimpleNamespace(
            drc=10, unconnected=20, kelvin_ok=False, diffpair_ok=False)
        improved = SimpleNamespace(
            drc=8, unconnected=15, kelvin_ok=True, diffpair_ok=True)
        self.assertTrue(synth._route_score_monotonic(baseline, improved))

        passing = SimpleNamespace(
            drc=8, unconnected=15, kelvin_ok=True, diffpair_ok=True)
        regressed = SimpleNamespace(
            drc=8, unconnected=15, kelvin_ok=True, diffpair_ok=False)
        self.assertFalse(synth._route_score_monotonic(passing, regressed))

    def test_route_monotonicity_rejects_equal_count_drc_debt_swap(self):
        baseline = SimpleNamespace(
            drc=1, unconnected=5, kelvin_ok=True, diffpair_ok=True,
            detail={"unconn_nets": ["/OPEN"],
                    "structural_violations": [{
                        "type": "clearance",
                        "items": [{"uuid": "old-a"},
                                  {"uuid": "old-b"}],
                    }]})
        swapped = SimpleNamespace(
            drc=1, unconnected=4, kelvin_ok=True, diffpair_ok=True,
            detail={"unconn_nets": ["/OPEN"],
                    "structural_violations": [{
                        "type": "shorting_items",
                        "items": [{"uuid": "new-a"},
                                  {"uuid": "new-b"}],
                    }]})

        self.assertFalse(synth._route_score_monotonic(baseline, swapped))
        decision = synth._route_score_admission(baseline, swapped)
        self.assertEqual(decision["decision"],
                         "new_structural_drc_identity")

    def test_tier_completion_partition_aggregates_adaptive_children(self):
        report = {"tiers": [
            {"completed_nets": ["A"], "incomplete_nets": ["B", "C"]},
            {"completed_nets": ["B"], "incomplete_nets": ["C"]},
            {"completed_nets": [], "incomplete_nets": ["C"]},
        ]}
        complete, incomplete = synth._tier_completion_partition(
            report, ["A", "B", "C"])
        self.assertEqual(complete, {"A", "B"})
        self.assertEqual(incomplete, {"C"})

    def test_tier_completion_partition_ignores_refused_rows(self):
        report = {"tiers": [
            {"completed_nets": ["A"]},
            {"completed_nets": ["B"], "refused": True},
        ]}
        complete, incomplete = synth._tier_completion_partition(
            report, ["A", "B"])
        self.assertEqual(complete, {"A"})
        self.assertEqual(incomplete, {"B"})

    def test_priority_repair_can_demote_only_declared_lower_tier(self):
        protected = {"PAIR_P", "PAIR_N", "+12V", "LOW_A", "LOW_B"}
        repair_protected = synth._priority_repair_protected(
            protected, {"LOW_A", "LOW_B"})

        self.assertEqual(
            repair_protected, ["+12V", "PAIR_N", "PAIR_P"])
        reconciled, removed = synth._reconcile_priority_repair(
            protected, {"local_ripup": {
                "removed_nets": ["LOW_B", "LOW_A", "NOT_PROTECTED"]}})
        self.assertEqual(removed, ["LOW_A", "LOW_B", "NOT_PROTECTED"])
        self.assertEqual(reconciled, ["+12V", "PAIR_N", "PAIR_P"])

    def test_incomplete_transactional_ground_access_defers_to_residual(self):
        admission = synth._ground_access_priority_admission(
            {"GND", "+12V", "PAIR_P", "PAIR_N"}, {
                "ok": False,
                "rolled_back": True,
                "refused": [{"ref": "U7", "pad": "3",
                              "reason": "no legal immediate return"}],
            })

        self.assertTrue(admission["admit"])
        self.assertFalse(admission["complete"])
        self.assertFalse(admission["promote_candidate"])
        self.assertEqual(
            admission["protected_nets"], ["+12V", "PAIR_N", "PAIR_P"])
        self.assertEqual(
            admission["deferred_terminals"][0]["ref"], "U7")

    def test_ground_access_can_remain_a_board_policy_hard_gate(self):
        admission = synth._ground_access_priority_admission(
            {"GND", "+12V"}, {"ok": False, "rolled_back": True},
            require_complete=True)

        self.assertFalse(admission["admit"])
        self.assertFalse(admission["complete"])
        self.assertEqual(admission["protected_nets"], ["+12V"])

    def test_complete_ground_access_keeps_protection_and_reconciles_ripup(self):
        admission = synth._ground_access_priority_admission(
            {"GND", "+12V", "LOW"}, {
                "ok": True,
                "priority_complete": True,
                "rolled_back": False,
                "protected_nets": ["GND"],
                "local_ripup": {"removed_nets": ["LOW"]},
            })

        self.assertTrue(admission["admit"])
        self.assertTrue(admission["complete"])
        self.assertTrue(admission["promote_candidate"])
        self.assertEqual(admission["protected_nets"], ["+12V", "GND"])
        self.assertEqual(admission["demoted_nets"], ["LOW"])

    def test_incomplete_live_ground_access_candidate_is_never_admitted(self):
        admission = synth._ground_access_priority_admission(
            {"GND", "+12V"}, {
                "ok": False,
                "rolled_back": False,
                "refused": [{"ref": "C7", "pad": "2"}],
            })

        self.assertFalse(admission["admit"])
        self.assertFalse(admission["complete"])
        self.assertFalse(admission["promote_candidate"])
        self.assertEqual(admission["protected_nets"], ["+12V"])

    def test_partial_exact_ground_access_promotes_without_protecting_gnd(self):
        admission = synth._ground_access_priority_admission(
            {"GND", "+12V", "PAIR_P"}, {
                "ok": False,
                "rolled_back": False,
                "partial_admission": True,
                "generated_item_count": 9,
                "refused": [{"ref": "D3", "pad": "2",
                              "reason": "no legal immediate return"}],
            })

        self.assertTrue(admission["admit"])
        self.assertFalse(admission["complete"])
        self.assertTrue(admission["promote_candidate"])
        self.assertEqual(admission["protected_nets"], ["+12V", "PAIR_P"])
        self.assertEqual(admission["deferred_terminals"][0]["ref"], "D3")

    def test_post_route_gnd_fanout_rolls_back_oracle_regression(self):
        with tempfile.TemporaryDirectory() as td:
            board = os.path.join(td, "board.kicad_pcb")
            with open(board, "wb") as sink:
                sink.write(b"proven-parent")
            scores = [
                SimpleNamespace(drc=0, unconnected=4,
                                kelvin_ok=True, diffpair_ok=True),
                SimpleNamespace(drc=2, unconnected=3,
                                kelvin_ok=True, diffpair_ok=True),
            ]

            def mutate(path):
                with open(path, "wb") as sink:
                    sink.write(b"speculative-fanout")
                return {"added": 2}

            with mock.patch.object(synth.cec_score, "score",
                                   side_effect=scores), \
                    mock.patch(
                        "cec_certificate_repair._run_drc",
                        side_effect=[{"violations": []},
                                     {"violations": []}]), \
                    mock.patch("cec_gnd_fanout.stitch_locked_islands",
                               return_value={"stitched": 0}), \
                    mock.patch("cec_gnd_fanout.synthesize",
                               side_effect=mutate), \
                    mock.patch.object(cec_fr, "refill_zones",
                                      return_value=True):
                report = synth._gnd_fanout_transactionally(board)

            with open(board, "rb") as source:
                self.assertEqual(source.read(), b"proven-parent")
            self.assertTrue(report["rolled_back"])
            self.assertFalse(report["accepted"])

    def test_post_route_gnd_fanout_rejects_equal_count_drc_debt_swap(self):
        with tempfile.TemporaryDirectory() as td:
            board = os.path.join(td, "board.kicad_pcb")
            with open(board, "wb") as sink:
                sink.write(b"proven-parent")
            metric = SimpleNamespace(
                drc=1, unconnected=4, kelvin_ok=True, diffpair_ok=True)
            old_drc = {"violations": [{
                "type": "clearance",
                "items": [{"uuid": "old-a"}, {"uuid": "old-b"}],
            }]}
            new_drc = {"violations": [{
                "type": "clearance",
                "items": [{"uuid": "new-a"}, {"uuid": "new-b"}],
            }]}

            def mutate(path):
                with open(path, "wb") as sink:
                    sink.write(b"equal-count-new-fault")
                return {"added": 1}

            with mock.patch.object(synth.cec_score, "score",
                                   side_effect=[metric, metric]), \
                    mock.patch(
                        "cec_certificate_repair._run_drc",
                        side_effect=[old_drc, new_drc]), \
                    mock.patch("cec_gnd_fanout.stitch_locked_islands",
                               return_value={"stitched": 0}), \
                    mock.patch("cec_gnd_fanout.synthesize",
                               side_effect=mutate), \
                    mock.patch.object(cec_fr, "refill_zones",
                                      return_value=True):
                report = synth._gnd_fanout_transactionally(board)

            with open(board, "rb") as source:
                self.assertEqual(source.read(), b"proven-parent")
            self.assertTrue(report["rolled_back"])
            self.assertEqual(report["reason"],
                             "new_structural_drc_identity")
            self.assertTrue(report["new_structural_drc_identities"])

    def test_pourfirst_seen_position_contract_is_exact_and_strict(self):
        positions = synth._pourfirst_seen_position_contract({
            "pourfirst_seen_placements": {
                "U1": [10, 20.5, 180],
                "C1": (11.25, 19, 90),
            },
        }, {"U1": "u-footprint", "C1": "c-footprint"})

        self.assertEqual(positions, {
            "C1": (11.25, 19.0, 90.0),
            "U1": (10.0, 20.5, 180.0),
        })
        with self.assertRaisesRegex(ValueError, "missing component"):
            synth._pourfirst_seen_position_contract({
                "pourfirst_seen_placements": {"STALE": [1, 2, 0]},
            }, {"U1": "u-footprint"})
        with self.assertRaisesRegex(ValueError, "must be"):
            synth._pourfirst_seen_position_contract({
                "pourfirst_seen_placements": {"U1": [1, 2]},
            }, {"U1": "u-footprint"})

    def test_pourfirst_hook_reservation_preserves_empty_pocket(self):
        # Exact L-shaped copper has area 7; its bounding box has area 16.  The
        # reservation must retain the legal 3x3 pocket instead of converting
        # the entire hook to a placement keepout.
        polygon = [(0.0, 0.0), (4.0, 0.0), (4.0, 1.0),
                   (1.0, 1.0), (1.0, 4.0), (0.0, 4.0)]
        boxes = synth._pourfirst_exact_avoid_boxes([{
            "net": "+VIN", "layer": "F.Cu", "name": "hook",
            "polygon": polygon,
        }])
        area = sum((row["x1"] - row["x0"])
                   * (row["y1"] - row["y0"]) for row in boxes)

        self.assertAlmostEqual(area, 7.0)
        self.assertEqual(len(boxes), 2)
        self.assertFalse(any(row["x0"] < 3.0 < row["x1"]
                             and row["y0"] < 3.0 < row["y1"]
                             for row in boxes))
        self.assertTrue(all(row["kind"] == "copper" for row in boxes))

    def test_non_manhattan_pour_reservation_falls_back_fail_safe(self):
        boxes = synth._pourfirst_exact_avoid_boxes([{
            "net": "+VIN", "layer": "F.Cu", "name": "diagonal",
            "polygon": [(0.0, 0.0), (2.0, 1.0), (0.0, 2.0)],
        }])

        self.assertEqual(len(boxes), 1)
        self.assertEqual([boxes[0][key] for key in
                          ("x0", "y0", "x1", "y1")],
                         [0.0, 0.0, 2.0, 2.0])
        self.assertEqual(boxes[0]["approximation"],
                         "bbox_non_orthogonal")

    def test_pourfirst_critical_seat_expands_to_support_cell(self):
        refs = synth._pourfirst_critical_cell_refs(
            {"SENSE", "CAN"},
            by_owner={
                "SENSE": [("FILTER", "3")],
                "UNRELATED": [("OTHER", "1")],
            },
            fixed_owner={"SENSE": [("DIVIDER", "2")]},
            bypass_assignments={
                "C_SENSE": {"owner": "SENSE"},
                "C_OTHER": {"owner": "UNRELATED"},
            })

        self.assertEqual(refs,
                         {"SENSE", "CAN", "FILTER", "DIVIDER", "C_SENSE"})

    def test_pourfirst_repair_promotes_complete_owner_cell(self):
        spec = {
            "C1": ("U1", "5"),
            "R1": ("U1", "6"),
            "C2": ("U2", "3"),
        }

        self.assertEqual(
            synth._pourfirst_repair_cell_closure({"U1"}, spec),
            {"U1", "C1", "R1"})
        self.assertEqual(
            synth._pourfirst_repair_cell_closure({"C1"}, spec),
            {"U1", "C1", "R1"})
        self.assertEqual(
            synth._pourfirst_repair_cell_closure({"MECH"}, spec),
            {"MECH"})

    def test_parallel_pour_failure_requires_real_bundle(self):
        contracts = {"/P1": {}, "/P2": {}, "/P3": {}, "/P4": {}}
        failed = synth._parallel_pour_failed_nets({
            "/P1": {"path_found": True,
                     "groups": {"delegated": 0},
                     "parallel_bundle": {"layers": ["F.Cu", "B.Cu"]}},
            "/P2": {"path_found": True, "fallback": "legacy",
                     "parallel_bundle": {"layers": ["F.Cu", "B.Cu"]}},
            "/P3": {"path_found": True},
            "/P4": {"path_found": True,
                     "groups": {"delegated": 2},
                     "parallel_bundle": {"layers": ["F.Cu", "B.Cu"]}},
        }, contracts)

        self.assertEqual(failed, ("/P2", "/P3"))

    def test_uncommitted_parallel_repair_fails_closed(self):
        self.assertIsNone(synth._parallel_pour_repair_failure({
            "applicable": False, "committed": False,
        }))
        self.assertIsNone(synth._parallel_pour_repair_failure({
            "applicable": True, "committed": True,
        }))
        self.assertEqual(
            synth._parallel_pour_repair_failure({
                "applicable": True, "committed": False,
                "result_failed": ["/RETURN"],
            }),
            "parallel routed-power placement repair did not close: /RETURN")

    def test_parallel_relief_expands_cells_and_requires_slide_permission(self):
        report = {
            "/PWR": {
                "planner_bottleneck": {"relief": {"F.Cu:1->2": {
                    "relief_sets": [{"owners": ["U1", "R2"]}],
                    "immovable_owners": ["J_LOCKED", "J_SLIDABLE"],
                }}}
            }
        }
        groups = synth._parallel_pour_relief_groups(
            report, ("/PWR",),
            {"C1": ("U1", "5"), "R2": ("U1", "6")},
            {"J_SLIDABLE": {"axis": "x"}})

        self.assertEqual(groups, [
            {"refs": ("R2", "U1"), "kind": "owner_signal_cell",
             "source_net": "/PWR"},
            {"refs": ("C1", "R2", "U1"), "kind": "owner_cell",
             "source_net": "/PWR"},
            {"refs": ("U1",), "kind": "planner_cut_owner",
             "source_net": "/PWR"},
            {"refs": ("R2",), "kind": "planner_cut_owner",
             "source_net": "/PWR"},
            {"refs": ("J_SLIDABLE",), "kind": "edge_anchor",
             "source_net": "/PWR"},
        ])

    def test_parallel_relief_filters_unknown_owner_and_exposes_raw_cut(self):
        groups = synth._parallel_pour_relief_groups({
            "/PWR": {"planner_bottleneck": {"relief": {"lane": {
                "relief_sets": [{"owners": ["U1", "D1", "?"]}],
            }}}},
        }, ("/PWR",), {"C1": ("U1", "5"), "R1": ("U1", "6")}, {})

        self.assertNotIn("?", {ref for group in groups
                                for ref in group["refs"]})
        self.assertIn({"refs": ("D1", "U1"),
                       "kind": "planner_cut_set",
                       "source_net": "/PWR"}, groups)
        self.assertIn({"refs": ("U1",),
                       "kind": "planner_cut_owner",
                       "source_net": "/PWR"}, groups)

    def test_parallel_relief_combines_independent_frontier_cuts(self):
        report = {"/PWR": {"planner_bottleneck": {"relief": {
            "left": {"relief_sets": [{"owners": ["C1"]}]},
            "right": {"relief_sets": [{"owners": ["C2"]}]},
        }}}}

        groups = synth._parallel_pour_relief_groups(
            report, ("/PWR",),
            {"C1": ("U1", "1"), "R1": ("U1", "2"),
             "C2": ("U2", "1"), "R2": ("U2", "2")}, {})

        self.assertIn({
            "refs": ("C1", "C2"),
            "kind": "compound_planner_cut_set",
            "source_net": "/PWR",
        }, groups)
        self.assertIn({
            "refs": ("C1", "C2", "R1", "R2", "U1", "U2"),
            "kind": "compound_owner_signal_cell",
            "source_net": "/PWR",
        }, groups)

    def test_parallel_relief_aggregates_alternative_realized_cuts(self):
        report = {"/PWR": {"planner_bottleneck": {"relief": {
            "throat": {"relief_sets": [
                {"owners": ["C1"]}, {"owners": ["C2"]},
            ]},
        }}}}

        groups = synth._parallel_pour_relief_groups(
            report, ("/PWR",), {}, {})

        self.assertIn({
            "refs": ("C1", "C2"),
            "kind": "aggregate_planner_cut_set",
            "source_net": "/PWR",
        }, groups)

    def test_parallel_relief_consumes_realized_clearance_owner(self):
        report = {
            "/PWR": {
                "planner_bottleneck": {
                    "kind": "realized_exact_clearance",
                    "clashes": [{"owner": "C1",
                                  "kind": "future_decoupler_access"}],
                }
            }
        }

        groups = synth._parallel_pour_relief_groups(
            report, ("/PWR",), {"C1": ("U1", "5"), "R1": ("U1", "6")},
            {})

        self.assertEqual(groups, [
            {"refs": ("C1",),
             "kind": "exact_clearance_primitive",
             "source_net": "/PWR"},
            {"refs": ("C1", "R1", "U1"),
             "kind": "exact_clearance_signal_cell",
             "source_net": "/PWR"},
        ])

    def test_parallel_relief_offsets_cover_asymmetric_sidestep(self):
        group = {"refs": ("FID1",), "kind": "owner_cell"}
        offsets = synth._parallel_pour_group_offsets(
            group, {}, step_mm=4.0, max_mm=8.0)
        self.assertIn((-8.0, 4.0), offsets)
        self.assertIn((0.0, -4.0), offsets)
        self.assertNotIn((0.0, 0.0), offsets)

        anchor = {"refs": ("J1",), "kind": "edge_anchor"}
        slides = synth._parallel_pour_group_offsets(
            anchor, {"J1": {"axis": "x", "step_mm": 4,
                             "max_mm": 8}})
        self.assertEqual(slides,
                         [(4.0, 0.0), (-4.0, 0.0),
                          (8.0, 0.0), (-8.0, 0.0)])

    def test_parallel_relief_uses_exact_clash_span_for_primitive_reseat(self):
        specs = synth._parallel_pour_relief_tangent_specs(
            {"refs": ("C1",), "kind": "exact_clearance_primitive",
             "source_net": "/PWR"},
            {"/PWR": {"planner_bottleneck": {
                "kind": "realized_exact_clearance",
                "clashes": [{
                    "owner": "C1",
                    "intersection_bounds_mm": [2.0, 3.0, 2.3, 4.5],
                }],
            }}},
            {"C1": (10.0, 20.0, 90.0)}, margin_mm=0.1)

        offsets = {(row["dx_mm"], row["dy_mm"]) for row in specs}
        self.assertIn((-0.4, 0.0), offsets)
        self.assertIn((0.4, 0.0), offsets)
        self.assertIn((0.0, -1.6), offsets)
        self.assertIn((0.0, 1.6), offsets)

    def test_parallel_craft_blocker_promotes_new_foreign_owner_cell(self):
        baseline = {
            "decoupler": {
                "violations": [("C_OLD", "U_OLD.GND[VCC]", 2.0)],
                "details": [{
                    "cap_ref": "C_OLD", "owner_ref": "U_OLD",
                    "actionable": True, "status": "assigned",
                    "supply_access_reason": "old blockage",
                    "supply_access_certificate": {
                        "dominant_blockers": [
                            {"ref": "OLD", "hit_count": 99}]},
                }],
            },
        }
        terminal = copy.deepcopy(baseline)
        terminal["decoupler"]["violations"].append(
            ("C_NEW", "U_NEW.1[VDD] local-cell-access", 1.0))
        terminal["decoupler"]["details"].append({
            "cap_ref": "C_NEW", "owner_ref": "U_NEW",
            "actionable": True, "status": "assigned",
            "supply_access_reason": "new blockage",
            "supply_access_certificate": {
                "dominant_blockers": [
                    {"ref": "C_BLOCK", "hit_count": 9},
                    {"ref": "U_MOVED", "hit_count": 4},
                ]},
        })

        groups = synth._parallel_pour_craft_blocker_groups(
            terminal, baseline,
            {"C_BLOCK": ("U_BLOCK", "5"),
             "R_BLOCK": ("U_BLOCK", "2")},
            excluded_refs={"U_MOVED"})

        self.assertEqual(groups, [{
            "refs": ("C_BLOCK", "R_BLOCK", "U_BLOCK"),
            "kind": "craft_blocker_cell",
            "source_caps": ("C_NEW",),
            "blocker_refs": ("C_BLOCK",),
            "hit_count": 9,
        }])

    def test_parallel_craft_blocker_never_moves_current_or_fixed_cell(self):
        terminal = {
            "decoupler": {
                "violations": [("C1", "U1.1[VDD] local-cell-access", 1)],
                "details": [{
                    "cap_ref": "C1", "owner_ref": "U1",
                    "actionable": True, "status": "assigned",
                    "supply_access_reason": "blocked",
                    "supply_access_certificate": {
                        "dominant_blockers": [
                            {"ref": "C_MOVED", "hit_count": 9},
                            {"ref": "C_FIXED", "hit_count": 8},
                        ]},
                }],
            },
        }
        spec = {
            "C_MOVED": ("U_MOVED", "1"),
            "C_FIXED": ("U_FIXED", "1"),
        }

        groups = synth._parallel_pour_craft_blocker_groups(
            terminal, {}, spec, excluded_refs={"U_MOVED"},
            fixed_refs={"U_FIXED"})

        self.assertEqual(groups, [])

    def test_parallel_craft_blocker_reseats_missing_owned_decoupler(self):
        terminal = {
            "decoupler": {
                "violations": [("C10", "U10.6[+3V3]", 7.72)],
                "details": [{
                    "cap_ref": "C10", "owner_ref": "U10",
                    "owner_pin": "6", "actionable": True,
                    "status": "missing", "nearest_compatible_mm": 7.72,
                    "assignment_limit_mm": 3.5,
                    "assignment_gap_mm": 4.22,
                    "supply_access_reason": None,
                }],
            },
        }

        groups = synth._parallel_pour_craft_blocker_groups(
            terminal, {}, {"C10": ("U10", "6")})

        self.assertEqual(groups, [{
            "refs": ("C10",),
            "kind": "craft_decoupler_reseat",
            "owner_ref": "U10",
            "owner_pin": "6",
            "source_caps": ("C10",),
            "blocker_refs": ("C10",),
            "hit_count": 4220,
            "assignment_gap_mm": 4.22,
            "assignment_limit_mm": 3.5,
            "ground_distance_mm": None,
            "loop_proxy_mm": None,
        }])

    def test_parallel_craft_blocker_does_not_reseat_fixed_decoupler(self):
        terminal = {
            "decoupler": {
                "violations": [("C1", "U1.1[VDD]", 6.0)],
                "details": [{
                    "cap_ref": "C1", "owner_ref": "U1",
                    "actionable": True, "status": "missing",
                    "nearest_compatible_mm": 6.0,
                    "assignment_limit_mm": 3.0,
                    "assignment_gap_mm": 3.0,
                }],
            },
        }

        self.assertEqual(
            synth._parallel_pour_craft_blocker_groups(
                terminal, {}, {"C1": ("U1", "1")},
                fixed_refs={"U1"}),
            [])

    def test_parallel_craft_blocker_reseats_assigned_bad_ground_return(self):
        terminal = {
            "decoupler": {
                "violations": [("C1", "U1.GND[VDD]", 5.349)],
                "details": [{
                    "cap_ref": "C1", "owner_ref": "U1",
                    "owner_pin": "6", "actionable": True,
                    "status": "assigned", "distance_mm": 2.663,
                    "ground_distance_mm": 2.686,
                    "loop_proxy_mm": 5.349,
                }],
            },
        }

        groups = synth._parallel_pour_craft_blocker_groups(
            terminal, {}, {"C1": ("U1", "6")})

        self.assertEqual(groups, [{
            "refs": ("C1",),
            "kind": "craft_decoupler_return_reseat",
            "owner_ref": "U1", "owner_pin": "6",
            "source_caps": ("C1",), "blocker_refs": ("C1",),
            "hit_count": 5349,
            "assignment_gap_mm": 0.0,
            "assignment_limit_mm": 0.0,
            "ground_distance_mm": 2.686,
            "loop_proxy_mm": 5.349,
        }])

    def test_parallel_decoupler_reseat_aims_at_owner_pin(self):
        group = {
            "refs": ("C1",), "kind": "craft_decoupler_reseat",
            "owner_ref": "U1", "owner_pin": "6",
            "assignment_limit_mm": 3.5,
        }
        templates = {
            "U1": ({"pad": "6", "local": (1.0, 0.0)},),
            "C1": ({"pad": "1", "local": (-0.5, 0.0)},
                   {"pad": "2", "local": (0.5, 0.0)}),
        }
        positions = {
            "U1": (10.0, 10.0, 0.0),
            "C1": (18.0, 6.0, 0.0),
        }

        offsets = synth._parallel_pour_decoupler_reseat_offsets(
            group, positions, templates, {"C1": ("U1", "6")})
        moved = {
            "U1": positions["U1"],
            "C1": (positions["C1"][0] + offsets[0][0],
                   positions["C1"][1] + offsets[0][1], 0.0),
        }
        geometry = synth._parallel_pour_passive_owner_geometry(
            moved, templates, {"C1": ("U1", "6")})

        self.assertTrue(offsets)
        self.assertLessEqual(geometry["key"][1], 3.5)

    def test_parallel_decoupler_pin_pair_reseat_uses_supply_and_ground(self):
        group = {
            "refs": ("C1",),
            "kind": "craft_decoupler_return_reseat",
            "owner_ref": "U1", "owner_pin": "6",
        }
        templates = {
            "U1": ({"pad": "6", "net": "+3V3",
                    "local": (-1.0, 0.0)},
                   {"pad": "5", "net": "GND",
                    "local": (-1.0, 1.0)}),
            "C1": ({"pad": "1", "net": "+3V3",
                    "local": (-0.5, 0.0)},
                   {"pad": "2", "net": "GND",
                    "local": (0.5, 0.0)}),
        }

        specs = synth._parallel_pour_decoupler_pin_pair_specs(
            group,
            {"U1": (10.0, 10.0, 0.0),
             "C1": (18.0, 6.0, 0.0)},
            templates, {"C1": ("U1", "6")})

        self.assertTrue(specs)
        self.assertEqual(specs[0]["search_family"], "pin_pair_reseat")
        self.assertLess(specs[0]["pin_pair_error_mm"], 2.0)
        self.assertIn(specs[0]["rotation_delta_deg"],
                      (0.0, 90.0, 180.0, 270.0))

    def test_parallel_compound_reflow_reseats_owned_decoupler_atomically(self):
        groups = [{
            "refs": ("C1",),
            "kind": "craft_decoupler_return_reseat",
            "owner_ref": "U1", "owner_pin": "6",
            "source_caps": ("C1",), "blocker_refs": ("C1",),
            "hit_count": 5000,
        }, {
            "refs": ("C1", "U1"),
            "kind": "critical_terminal_locality_cell",
            "source_caps": (), "blocker_refs": ("U1",),
            "source_relations": (("SHUNT", "U1"),),
            "direct_length_regression_mm": 4.0,
            "hit_count": 4000,
        }]
        positions = {
            "SHUNT": (20.0, 10.0, 0.0),
            "U1": (10.0, 10.0, 0.0),
            "C1": (11.0, 12.0, 0.0),
        }
        templates = {
            "U1": ({"pad": "6", "net": "+3V3",
                    "local": (1.0, 0.0)},
                   {"pad": "5", "net": "GND",
                    "local": (1.0, 1.0)}),
            "C1": ({"pad": "1", "net": "+3V3",
                    "local": (-0.5, 0.0)},
                   {"pad": "2", "net": "GND",
                    "local": (0.5, 0.0)}),
        }

        compounds = synth._parallel_pour_compound_owner_reseat_groups(
            groups, positions, templates, {"C1": ("U1", "6")}, {},
            step_mm=1.0, max_mm=6.0)

        self.assertEqual(len(compounds), 1)
        self.assertEqual(compounds[0]["refs"], ("C1", "U1"))
        self.assertEqual(compounds[0]["source_relations"],
                         (("SHUNT", "U1"),))
        transforms = compounds[0]["move_specs"]
        self.assertTrue(all(transform["search_family"] ==
                            "compound_owner_pin_pair"
                            for transform in transforms))
        self.assertTrue(any(transform["macro_search_family"] ==
                            "owner_rotation" for transform in transforms))
        translated = next(
            transform for transform in transforms
            if math.dist(transform["placements"]["U1"][:2],
                         positions["SHUNT"][:2])
            < math.dist(positions["U1"][:2], positions["SHUNT"][:2]))
        self.assertNotEqual(translated["placements"]["C1"],
                            (15.0, 12.0, 0.0))

    def test_parallel_craft_blocker_promotes_regressed_terminal_follower_cell(self):
        baseline = {
            "critical_terminal_order": {"details": [{
                "anchor_ref": "SHUNT", "ref": "SENSE",
                "direct_length_mm": 8.0,
            }]},
        }
        terminal = {
            "critical_terminal_order": {"details": [{
                "anchor_ref": "SHUNT", "ref": "SENSE",
                "direct_length_mm": 10.75,
            }]},
        }

        groups = synth._parallel_pour_craft_blocker_groups(
            terminal, baseline,
            {"C_SENSE": ("SENSE", "5"),
             "R_SENSE": ("SENSE", "6")})

        self.assertEqual(groups, [{
            "refs": ("C_SENSE", "R_SENSE", "SENSE"),
            "kind": "critical_terminal_locality_cell",
            "source_caps": (), "blocker_refs": ("SENSE",),
            "source_relations": (("SHUNT", "SENSE"),),
            "hit_count": 2750,
            "direct_length_regression_mm": 2.75,
        }])

    def test_parallel_craft_blocker_never_moves_fixed_terminal_follower(self):
        baseline = {
            "critical_terminal_order": {"details": [{
                "anchor_ref": "SHUNT", "ref": "SENSE",
                "direct_length_mm": 8.0,
            }]},
        }
        terminal = {
            "critical_terminal_order": {"details": [{
                "anchor_ref": "SHUNT", "ref": "SENSE",
                "direct_length_mm": 11.0,
            }]},
        }

        groups = synth._parallel_pour_craft_blocker_groups(
            terminal, baseline, {}, fixed_refs={"SENSE"})

        self.assertEqual(groups, [])

    def test_parallel_overlap_blocker_promotes_and_ranks_foreign_cells(self):
        groups = synth._parallel_pour_overlap_blocker_groups(
            {("R_CURRENT", "C_BLOCK"),
             ("U_CURRENT", "U_BLOCK"),
             ("U_CURRENT", "C_BLOCK")},
            {"C_BLOCK": ("U_BLOCK", "5"),
             "R_BLOCK": ("U_BLOCK", "2")},
            excluded_refs={"R_CURRENT", "U_CURRENT"})

        self.assertEqual(groups, [{
            "refs": ("C_BLOCK", "R_BLOCK", "U_BLOCK"),
            "kind": "overlap_blocker_cell",
            "source_pairs": (
                ("C_BLOCK", "R_CURRENT"),
                ("C_BLOCK", "U_CURRENT"),
                ("U_BLOCK", "U_CURRENT"),
            ),
            "blocker_refs": ("C_BLOCK", "U_BLOCK"),
            "coverage": 3,
        }, {
            "refs": ("C_BLOCK",),
            "kind": "overlap_passive_reseat",
            "owner_ref": "U_BLOCK",
            "source_pairs": (
                ("C_BLOCK", "R_CURRENT"),
                ("C_BLOCK", "U_CURRENT"),
            ),
            "blocker_refs": ("C_BLOCK",),
            "coverage": 2,
        }])

    def test_parallel_overlap_authority_reflow_is_causal_and_exact_scoped(self):
        groups = synth._parallel_pour_overlap_authority_groups(
            {("SENSE", "REG"), ("OTHER", "PASSIVE")}, ({
                "kind": "owner_cell", "source_net": "/CURRENT_LO",
                "refs": ["REG", "C_REG"],
            }, {
                # A later overlap move has no current-net provenance and must
                # never become authority merely because it is in the lineage.
                "kind": "overlap_blocker_cell", "refs": ["OTHER"],
            }))

        self.assertEqual(groups, [{
            "refs": ("C_REG", "REG"),
            "kind": "overlap_authority_reflow",
            "source_net": "/CURRENT_LO",
            "source_authority_kind": "owner_cell",
            "source_pairs": (("REG", "SENSE"),),
            "blocker_refs": ("REG",), "coverage": 1,
        }])

    def test_parallel_overlap_authority_reflow_never_moves_fixed_cell(self):
        groups = synth._parallel_pour_overlap_authority_groups(
            {("J_FIXED", "IC")}, ({
                "kind": "edge_anchor", "source_net": "/CURRENT_HI",
                "refs": ["J_FIXED"],
            },), fixed_refs={"J_FIXED"})

        self.assertEqual(groups, [])

    def test_parallel_passive_reseat_never_splits_fixed_owner_cell(self):
        groups = synth._parallel_pour_overlap_blocker_groups(
            {("CURRENT", "C_BLOCK")},
            {"C_BLOCK": ("U_BLOCK", "5"),
             "R_BLOCK": ("U_BLOCK", "2")},
            excluded_refs={"CURRENT"}, fixed_refs={"U_BLOCK"})

        self.assertEqual(groups, [])

    def test_parallel_passive_can_reseat_around_moved_authority_owner(self):
        groups = synth._parallel_pour_overlap_blocker_groups(
            {("CURRENT", "C_BLOCK")},
            {"C_BLOCK": ("U_BLOCK", "5")},
            excluded_refs={"CURRENT", "U_BLOCK"})

        self.assertEqual(groups, [{
            "refs": ("C_BLOCK",),
            "kind": "overlap_passive_reseat",
            "owner_ref": "U_BLOCK",
            "source_pairs": (("CURRENT", "C_BLOCK"),),
            "blocker_refs": ("C_BLOCK",),
            "coverage": 1,
        }])

    def test_parallel_rigid_cell_rotation_uses_topology_owner_pivot(self):
        group = {
            "refs": ("C1", "R1", "U1"),
            "kind": "overlap_blocker_cell",
        }
        positions = {
            "U1": (10.0, 10.0, 0.0),
            "C1": (12.0, 10.0, 90.0),
            "R1": (10.0, 12.0, 180.0),
        }

        specs = synth._parallel_pour_group_rotation_specs(
            group, positions,
            {"C1": ("U1", "5"), "R1": ("U1", "6")},
            deltas=(90.0,))

        self.assertEqual(len(specs), 1)
        self.assertEqual(specs[0]["pivot_ref"], "U1")
        self.assertEqual(specs[0]["search_family"], "rigid_rotation")
        self.assertEqual(specs[0]["placements"]["U1"],
                         (10.0, 10.0, 90.0))
        self.assertAlmostEqual(specs[0]["placements"]["C1"][0], 10.0)
        self.assertAlmostEqual(specs[0]["placements"]["C1"][1], 8.0)
        self.assertEqual(specs[0]["placements"]["C1"][2], 180.0)

    def test_parallel_initial_transforms_include_rotation_and_translation(self):
        group = {"refs": ("D1", "U1"), "kind": "planner_cut_set"}
        positions = {"U1": (10.0, 10.0, 0.0),
                     "D1": (6.0, 10.0, 90.0)}

        specs = synth._parallel_pour_initial_transform_specs(
            group, positions, {"D1": ("U1", "2")}, {},
            step_mm=4.0, max_mm=4.0)

        self.assertEqual(specs[0]["search_family"], "rigid_rotation")
        self.assertEqual(specs[0]["rotation_delta_deg"], 180.0)
        self.assertAlmostEqual(specs[0]["placements"]["D1"][0], 14.0)
        self.assertTrue(any(spec["search_family"] == "translation"
                            for spec in specs))
        self.assertTrue(any(spec.get("dx_mm") == -2.0
                            and spec.get("dy_mm") == 0.0
                            for spec in specs))

        anchor = synth._parallel_pour_initial_transform_specs(
            {"refs": ("J1",), "kind": "edge_anchor"},
            {"J1": (5.0, 5.0, 0.0)}, {},
            {"J1": {"axis": "x", "step_mm": 4.0, "max_mm": 4.0}},
            step_mm=4.0, max_mm=4.0)
        self.assertEqual([(spec["dx_mm"], spec["dy_mm"])
                          for spec in anchor],
                         [(4.0, 0.0), (-4.0, 0.0)])

    def test_parallel_rigid_cell_rotation_rejects_ambiguous_owner(self):
        specs = synth._parallel_pour_group_rotation_specs(
            {"refs": ("C1", "C2", "U1", "U2"),
             "kind": "overlap_blocker_cell"},
            {ref: (float(index), 0.0, 0.0) for index, ref in enumerate(
                ("C1", "C2", "U1", "U2"))},
            {"C1": ("U1", "1"), "C2": ("U2", "1")})

        self.assertEqual(specs, [])

    def test_parallel_passive_reseat_rotation_is_local(self):
        specs = synth._parallel_pour_group_rotation_specs(
            {"refs": ("C1",), "kind": "overlap_passive_reseat"},
            {"C1": (5.0, 6.0, 90.0)}, {"C1": ("U1", "1")},
            deltas=(90.0,))

        self.assertEqual(specs[0]["pivot_ref"], "C1")
        self.assertEqual(specs[0]["search_family"], "passive_reseat")
        self.assertEqual(specs[0]["placements"]["C1"],
                         (5.0, 6.0, 180.0))

    def test_parallel_singleton_cut_can_rotate_in_place(self):
        specs = synth._parallel_pour_group_rotation_specs(
            {"refs": ("C1",), "kind": "planner_cut_set"},
            {"C1": (5.0, 6.0, 90.0)}, {"C1": ("U1", "1")},
            deltas=(180.0,))

        self.assertEqual(len(specs), 1)
        self.assertEqual(specs[0]["pivot_ref"], "C1")
        self.assertEqual(specs[0]["search_family"], "rigid_rotation")
        self.assertEqual(specs[0]["placements"]["C1"],
                         (5.0, 6.0, 270.0))

    def test_parallel_relief_tangent_uses_restored_path_width(self):
        group = {"refs": ("U2",), "kind": "planner_cut_set",
                 "source_net": "/PWR"}
        report = {"/PWR": {"planner_bottleneck": {"relief": {
            "B.Cu:3->4": {
                "required_width_mm": 6.311234,
                "relief_sets": [{
                    "owners": ["U2"],
                    "owner_bounds_mm": {
                        "U2": [51.7, 28.32, 52.65, 29.27]},
                    "path_mm": [[51.799, 26.6], [51.799, 40.75]],
                }],
            },
        }}}}

        specs = synth._parallel_pour_relief_tangent_specs(
            group, report, {"U2": (50.0, 30.0, 90.0)}, max_mm=8.0)

        offsets = {(spec["dx_mm"], spec["dy_mm"]) for spec in specs}
        self.assertIn((3.354617, 0.0), offsets)
        self.assertIn((-4.106617, 0.0), offsets)
        self.assertIn((8.0, 0.0), offsets)
        self.assertIn((-8.0, 0.0), offsets)
        self.assertTrue(all(
            spec["search_family"] == "relief_tangent" for spec in specs))

    def test_parallel_relief_tangent_consumes_proven_wide_cut(self):
        group = {"refs": ("U1", "C1", "R1", "R2"),
                 "kind": "corridor_cut_cell", "source_net": "/PWR"}
        report = {"/PWR": {"planner_bottleneck": {"relief": {
            "F.Cu:1->2": {
                "required_width_mm": 6.0,
                "relief_sets": [],
                "wide_relief_sets": [{
                    "owners": ["U1", "C1", "R1", "R2"],
                    "owner_bounds_mm": {
                        "U1": [8.0, 8.0, 10.0, 12.0],
                        "C1": [10.0, 9.0, 11.0, 11.0],
                        "R1": [12.0, 9.0, 13.0, 11.0],
                        "R2": [14.0, 9.0, 15.0, 11.0],
                    },
                    "path_mm": [[0.0, 10.0], [20.0, 10.0]],
                    "search": "greedy_inclusion_minimal",
                }],
            },
        }}}}

        specs = synth._parallel_pour_relief_tangent_specs(
            group, report,
            {ref: (10.0, 10.0, 0.0) for ref in group["refs"]},
            max_mm=8.0)

        self.assertTrue(specs)
        self.assertIn((0.0, -8.0), {
            (spec["dx_mm"], spec["dy_mm"]) for spec in specs})

    def test_parallel_relief_tangent_requires_owned_cut(self):
        report = {"/PWR": {"planner_bottleneck": {"relief": {
            "lane": {"required_width_mm": 4.0, "relief_sets": [{
                "owners": ["OTHER"],
                "owner_bounds_mm": {"OTHER": [0, 0, 1, 1]},
                "path_mm": [[2, 0], [2, 5]],
            }]},
        }}}}
        self.assertEqual(synth._parallel_pour_relief_tangent_specs(
            {"refs": ("U2",), "kind": "planner_cut_set",
             "source_net": "/PWR"},
            report, {"U2": (5.0, 5.0, 0.0)}), [])

    def test_parallel_negotiated_cut_admits_new_layer_owner_wall(self):
        parent = {"/PWR": {"planner_bottleneck": {"relief": {
            "B.Cu:1->2": {"required_width_mm": 6.0,
                            "relief_sets": [{"owners": ["U2"]}]},
        }}}}
        trial = {"/PWR": {"planner_bottleneck": {"relief": {
            "F.Cu:1->2": {"required_width_mm": 6.0,
                            "relief_sets": [{"owners": ["U3", "C2"]}]},
        }}}}
        admitted = synth._parallel_pour_negotiated_cut_admission(
            ("/PWR",), parent, ("/PWR",), trial)
        self.assertTrue(admitted["accepted"])
        self.assertEqual(admitted["kind"], "new_cut")

        repeated = synth._parallel_pour_negotiated_cut_admission(
            ("/PWR",), parent, ("/PWR",), trial,
            {admitted["signature"]})
        self.assertFalse(repeated["accepted"])
        closed = synth._parallel_pour_negotiated_cut_admission(
            ("/PWR",), parent, (), {})
        self.assertTrue(closed["accepted"])
        self.assertEqual(closed["kind"], "bundle_count")

    def test_parallel_cut_signature_ignores_extra_relief_alternatives(self):
        light = {"/PWR": {"planner_bottleneck": {"relief": {
            "B.Cu:1->2": {"required_width_mm": 6.0,
                            "relief_sets": [{"owners": ["U2"]}]},
        }}}}
        full = {"/PWR": {"planner_bottleneck": {"relief": {
            "B.Cu:1->2": {"required_width_mm": 6.0,
                            "relief_sets": [
                                {"owners": ["U2"]},
                                {"owners": ["C4"]},
                                {"owners": ["C20"]},
                            ]},
        }}}}

        self.assertEqual(
            synth._parallel_pour_bottleneck_signature(
                light, ("/PWR",)),
            synth._parallel_pour_bottleneck_signature(
                full, ("/PWR",)))

    def test_parallel_lookahead_reserves_trials_for_later_depths(self):
        self.assertEqual(
            synth._parallel_pour_depth_trial_quota(12, 0, 0, 2), 6)
        self.assertEqual(
            synth._parallel_pour_depth_trial_quota(12, 4, 1, 2), 8)
        self.assertEqual(
            synth._parallel_pour_depth_trial_quota(12, 12, 1, 2), 0)

        # A deeper negotiated-congestion search still reserves one equal
        # tranche per remaining physical-cut depth.
        self.assertEqual(
            synth._parallel_pour_depth_trial_quota(96, 64, 4, 6), 16)

    def test_parallel_relief_group_visit_is_scoped_to_physical_cut(self):
        group = {"refs": ("C4", "U2"), "kind": "owner_cell",
                 "source_net": "/PWR"}
        first = {"/PWR": {"planner_bottleneck": {"relief": {
            "B.Cu:1->2": {"required_width_mm": 6.0,
                            "relief_sets": [{"owners": ["U2"]}]},
        }}}}
        next_cut = {"/PWR": {"planner_bottleneck": {"relief": {
            "F.Cu:1->2": {"required_width_mm": 6.0,
                            "relief_sets": [{"owners": ["U3", "C2"]}]},
        }}}}

        first_visit = synth._parallel_pour_group_use_signature(
            first, ("/PWR",), group)
        repeated_visit = synth._parallel_pour_group_use_signature(
            first, ("/PWR",), group)
        advanced_visit = synth._parallel_pour_group_use_signature(
            next_cut, ("/PWR",), group)

        self.assertEqual(first_visit, repeated_visit)
        self.assertNotEqual(first_visit, advanced_visit)

    def test_parallel_terminal_signature_tracks_complete_parent_state(self):
        baseline = {
            "ANCHOR": (10.0, 10.0, 0.0),
            "OWNER": (20.0, 20.0, 90.0),
        }
        left_parent = dict(baseline)
        left_parent["ANCHOR"] = (6.0, 10.0, 0.0)
        right_parent = dict(baseline)
        right_parent["ANCHOR"] = (14.0, 10.0, 0.0)
        # Both paths can end with the same final OWNER move; their complete
        # physical states must still remain distinct terminal candidates.
        left_parent["OWNER"] = (20.0, 16.0, 90.0)
        right_parent["OWNER"] = (20.0, 16.0, 90.0)

        left = synth._parallel_pour_placement_signature(
            left_parent, baseline, back_refs={"OWNER"})
        right = synth._parallel_pour_placement_signature(
            right_parent, baseline, back_refs={"OWNER"})

        self.assertNotEqual(left, right)
        self.assertEqual(left[1], ("OWNER",))
        self.assertEqual(len(left[0]), 2)

    def test_parallel_terminal_signature_collapses_alias_paths(self):
        baseline = {"A": (1.0, 2.0, 0.0), "B": (3.0, 4.0, 90.0)}
        first = dict(baseline)
        second = dict(baseline)
        first["B"] = (5.0, 4.0, 90.0)
        second["B"] = (5.0, 4.0, 90.0)

        self.assertEqual(
            synth._parallel_pour_placement_signature(first, baseline),
            synth._parallel_pour_placement_signature(second, baseline))

    def test_parallel_overlap_certificate_separates_hard_pairs(self):
        certificate = synth._parallel_pour_overlap_legalization_certificate(
            {("CURRENT", "FIXED"), ("CURRENT", "C_BLOCK")},
            {"C_BLOCK": ("U_BLOCK", "5"),
             "R_BLOCK": ("U_BLOCK", "2")},
            excluded_refs={"CURRENT"}, fixed_refs={"FIXED"})

        self.assertEqual(certificate["hard_pairs"],
                         (("CURRENT", "FIXED"),))
        self.assertEqual(certificate["covered_pairs"],
                         (("CURRENT", "C_BLOCK"),))
        self.assertEqual(certificate["groups"][0]["refs"],
                         ("C_BLOCK", "R_BLOCK", "U_BLOCK"))

    def test_parallel_overlap_certificate_ignores_inherited_pairs(self):
        certificate = synth._parallel_pour_overlap_legalization_certificate(
            {("CURRENT", "FIXED")}, {},
            excluded_refs={"CURRENT"}, fixed_refs={"FIXED"},
            allowed_pairs={("FIXED", "CURRENT")})

        self.assertEqual(certificate["active_pairs"], ())
        self.assertEqual(certificate["hard_pairs"], ())

    def test_parallel_overlap_tangent_offsets_clear_measured_pair(self):
        footprint = "cec-Resistor_SMD:R_0402_1005Metric"
        positions = {
            "MOVER": (10.0, 10.0, 0.0),
            "BLOCKER": (10.2, 10.0, 0.0),
        }
        comps = {ref: footprint for ref in positions}
        group = {
            "refs": ("MOVER",),
            "source_pairs": (("BLOCKER", "MOVER"),),
        }

        offsets = synth._parallel_pour_overlap_tangent_offsets(
            group, positions, comps, max_mm=4.0)

        self.assertTrue(offsets)
        self.assertTrue(any(not synth._overlap_pairs(
            {**positions,
             "MOVER": (positions["MOVER"][0] + dx,
                       positions["MOVER"][1] + dy, 0.0)},
            comps) for dx, dy in offsets))

    def test_parallel_overlap_tangent_offsets_are_bounded_and_unique(self):
        footprint = "cec-Resistor_SMD:R_0402_1005Metric"
        positions = {
            "A": (10.0, 10.0, 0.0),
            "B": (10.1, 10.0, 0.0),
            "C": (10.2, 10.0, 0.0),
        }
        group = {"refs": ("A", "B"),
                 "source_pairs": (("A", "C"), ("B", "C"))}
        offsets = synth._parallel_pour_overlap_tangent_offsets(
            group, positions, {ref: footprint for ref in positions},
            max_mm=1.5)

        self.assertEqual(len(offsets), len(set(offsets)))
        self.assertTrue(all(math.hypot(dx, dy) <= 1.5 + 1e-9
                            for dx, dy in offsets))

    def test_parallel_overlap_tangent_can_escape_beyond_local_grid(self):
        footprint = "cec-Resistor_SMD:R_0402_1005Metric"
        positions = {
            "MOVER": (10.0, 10.0, 0.0),
            "BLOCKER": (10.0, 10.0, 0.0),
        }
        comps = {ref: footprint for ref in positions}
        group = {
            "refs": ("MOVER",),
            "source_pairs": (("BLOCKER", "MOVER"),),
        }

        offsets = synth._parallel_pour_overlap_tangent_offsets(
            group, positions, comps, max_mm=0.1,
            separation_max_mm=2.0)

        self.assertTrue(any(math.hypot(dx, dy) > 0.1
                            for dx, dy in offsets))
        self.assertTrue(any(not synth._overlap_pairs(
            {**positions,
             "MOVER": (positions["MOVER"][0] + dx,
                       positions["MOVER"][1] + dy, 0.0)},
            comps) for dx, dy in offsets))

    def test_parallel_overlap_key_has_continuous_penetration_gradient(self):
        footprint = "cec-Resistor_SMD:R_0402_1005Metric"
        pairs = {("A", "B")}
        coincident = synth._parallel_pour_overlap_key(
            {"A": (10.0, 10.0, 0.0),
             "B": (10.1, 10.0, 0.0)},
            pairs, {"A": footprint, "B": footprint})
        separating = synth._parallel_pour_overlap_key(
            {"A": (10.0, 10.0, 0.0),
             "B": (10.8, 10.0, 0.0)},
            pairs, {"A": footprint, "B": footprint})

        self.assertEqual(coincident[0], separating[0])
        self.assertLess(separating[1], coincident[1])

    def test_parallel_overlap_negotiated_escape_changes_residual_pair_set(self):
        parent = {
            "overlap_key": (2, 3.0, 1.5),
            "best_overlap_key": (2, 3.0, 1.5),
            "pairs": {("A", "B"), ("C", "D")},
            "escape_debt": 0,
        }

        admission = synth._parallel_pour_negotiated_overlap_admission(
            parent, (3, 5.0, 2.0),
            {("A", "E"), ("C", "D"), ("F", "G")},
            pair_slack=1, area_growth_mm2=3.0, max_escape_depth=1)

        self.assertTrue(admission["admitted"])
        self.assertEqual(admission["kind"], "negotiated_escape")
        self.assertEqual(admission["escape_debt"], 1)
        self.assertTrue(admission["pair_set_changed"])

    def test_parallel_overlap_escape_cannot_walk_or_drift(self):
        parent = {
            "overlap_key": (3, 5.0, 2.0),
            "best_overlap_key": (2, 3.0, 1.5),
            "pairs": {("A", "E"), ("C", "D"), ("F", "G")},
            "escape_debt": 1,
        }
        second_escape = synth._parallel_pour_negotiated_overlap_admission(
            parent, (3, 4.5, 2.0),
            {("A", "H"), ("C", "D"), ("F", "G")})
        recovery = synth._parallel_pour_negotiated_overlap_admission(
            parent, (1, 2.0, 1.0), {("A", "H")})
        same_pairs = synth._parallel_pour_negotiated_overlap_admission(
            {**parent, "escape_debt": 0}, (3, 5.0, 2.0),
            parent["pairs"])

        self.assertFalse(second_escape["admitted"])
        self.assertFalse(same_pairs["admitted"])
        self.assertTrue(recovery["admitted"])
        self.assertEqual(recovery["kind"], "strict_improvement")
        self.assertEqual(recovery["escape_debt"], 0)

    def test_parallel_overlap_beam_preserves_cell_direction_diversity(self):
        def state(key, ref, dx, displacement):
            return {
                "overlap_key": key,
                "displacement": displacement,
                "moves": ({"kind": "overlap_blocker_cell",
                           "refs": [ref], "dx_mm": dx,
                           "dy_mm": 0.0},),
            }

        selected = synth._parallel_pour_select_overlap_beam([
            state((3, 1.0, 0.5), "U1", 1.0, 1.0),
            state((3, 1.1, 0.5), "U1", 2.0, 2.0),
            state((3, 1.2, 0.6), "U2", -1.0, 1.0),
            state((4, 0.1, 0.1), "U3", 1.0, 1.0),
        ], 3)

        self.assertEqual(len(selected), 3)
        self.assertEqual(
            {tuple(row["moves"][-1]["refs"]) for row in selected},
            {("U1",), ("U2",), ("U3",)})
        self.assertNotIn(2.0, [row["moves"][-1]["dx_mm"]
                               for row in selected])
        self.assertEqual(selected[0]["overlap_key"], (3, 1.0, 0.5))

    def test_parallel_overlap_beam_reserves_one_escape_lane(self):
        def state(ref, key, debt):
            return {
                "overlap_key": key, "escape_debt": debt,
                "moves": ({"kind": "overlap_blocker_cell",
                           "refs": [ref], "dx_mm": 1.0,
                           "dy_mm": 0.0},),
            }

        escape = state("ESCAPE", (3, 2.0, 1.0), 1)
        selected = synth._parallel_pour_select_overlap_beam([
            state("U1", (2, 1.0, 0.5), 0),
            state("U2", (2, 1.1, 0.5), 0),
            state("U3", (2, 1.2, 0.5), 0),
            escape,
        ], 3)

        self.assertEqual(len(selected), 3)
        self.assertIn(escape, selected)
        self.assertEqual(selected[0]["escape_debt"], 0)

        additive = synth._parallel_pour_select_overlap_beam([
            state("U1", (2, 1.0, 0.5), 0),
            state("U2", (2, 1.1, 0.5), 0),
            state("U3", (2, 1.2, 0.5), 0),
            state("U4", (2, 1.3, 0.5), 0),
            escape,
        ], 5)
        self.assertEqual(len(additive), 5)
        self.assertEqual(sum(not row["escape_debt"] for row in additive), 4)

    def test_parallel_overlap_transform_lanes_are_additive(self):
        def state(ref, key, family):
            return {
                "overlap_key": key, "escape_debt": 0,
                "moves": ({"kind": family, "search_family": family,
                           "refs": [ref], "dx_mm": 0.0,
                           "dy_mm": 0.0},),
            }

        translations = [
            state("T%d" % index, (2, 1.0 + index / 10.0, 0.5),
                  "translation")
            for index in range(4)]
        transforms = [
            state("R1", (1, 0.5, 0.5), "rigid_rotation"),
            state("P1", (1, 0.6, 0.5), "passive_reseat"),
        ]

        selected = synth._parallel_pour_select_overlap_lanes(
            translations + transforms, 4, transform_width=2)

        self.assertEqual(len(selected), 6)
        self.assertEqual(sum(
            row["moves"][-1]["search_family"] == "translation"
            for row in selected), 4)
        self.assertEqual(sum(
            row["moves"][-1]["search_family"] != "translation"
            for row in selected), 2)

    def test_parallel_overlap_risk_lane_keeps_shallow_pareto_state(self):
        def state(ref, key):
            return {
                "overlap_key": key, "escape_debt": 0,
                "moves": ({"kind": "overlap_blocker_cell",
                           "search_family": "translation",
                           "refs": [ref], "dx_mm": 1.0,
                           "dy_mm": 0.0},),
            }

        severe = state("SEVERE", (1, 22.0, 22.0))
        shallow = state("SHALLOW", (2, 2.0, 1.2))
        dominated = state("DOMINATED", (3, 4.0, 2.0))

        frontier = synth._parallel_pour_overlap_pareto_frontier(
            [severe, shallow, dominated])
        selected = synth._parallel_pour_select_overlap_lanes(
            [severe, shallow, dominated], 1, risk_width=1)

        self.assertEqual(frontier, [shallow, severe])
        self.assertIn(severe, selected)
        self.assertIn(shallow, selected)
        self.assertEqual(shallow["_overlap_lane"], "risk")
        self.assertTrue(shallow["risk_lineage"])

    def test_parallel_overlap_risk_lane_can_preserve_passive_reseat(self):
        def state(ref, key, family):
            return {
                "overlap_key": key, "escape_debt": 0,
                "moves": ({"kind": family, "search_family": family,
                           "refs": [ref], "dx_mm": 1.0,
                           "dy_mm": 0.0},),
            }

        primary = state("PRIMARY", (1, 22.0, 22.0), "translation")
        ordinary_transform = state(
            "ROTATE", (2, 3.0, 1.5), "rigid_rotation")
        safe_reseat = state(
            "CAP", (3, 2.0, 0.8), "passive_reseat")

        selected = synth._parallel_pour_select_overlap_lanes(
            [primary, ordinary_transform, safe_reseat], 1,
            transform_width=1, risk_width=1)

        self.assertEqual(len(selected), 3)
        self.assertEqual(primary["_overlap_lane"], "base")
        self.assertEqual(ordinary_transform["_overlap_lane"], "transform")
        self.assertEqual(safe_reseat["_overlap_lane"], "risk")
        self.assertTrue(safe_reseat["risk_lineage"])

    def test_parallel_overlap_rank_preserves_exact_current_corridor(self):
        safe = {
            "overlap_key": (2, 3.0, 2.0), "escape_debt": 0,
            "corridor_incursion_key": (0, 0.0, 0.0),
            "moves": ({"kind": "overlap_blocker_cell",
                       "search_family": "translation", "refs": ["SAFE"]},),
        }
        shorter_but_blocking = {
            "overlap_key": (1, 1.0, 1.0), "escape_debt": 0,
            "corridor_incursion_key": (1, 0.25, 0.25),
            "moves": ({"kind": "overlap_blocker_cell",
                       "search_family": "translation", "refs": ["BLOCK"]},),
        }

        selected = synth._parallel_pour_select_overlap_lanes(
            [shorter_but_blocking, safe], 1)

        self.assertEqual(selected, [safe])

    def test_parallel_overlap_rank_preserves_critical_terminal_locality(self):
        local = {
            "overlap_key": (1, 2.0, 2.0), "escape_debt": 0,
            "corridor_incursion_key": (0, 0.0, 0.0),
            "terminal_locality_key": (0, 0.0, 0.0),
            "moves": ({"kind": "overlap_blocker_cell",
                       "search_family": "translation", "refs": ["LOCAL"]},),
        }
        shallower_but_long = {
            "overlap_key": (1, 1.0, 1.0), "escape_debt": 0,
            "corridor_incursion_key": (0, 0.0, 0.0),
            "terminal_locality_key": (0, 4.5, 4.5),
            "moves": ({"kind": "overlap_blocker_cell",
                       "search_family": "translation", "refs": ["LONG"]},),
        }

        selected = synth._parallel_pour_select_overlap_lanes(
            [shallower_but_long, local], 1)

        self.assertEqual(selected, [local])

    def test_parallel_overlap_rank_preserves_owned_passive_locality(self):
        local = {
            "overlap_key": (1, 2.0, 2.0), "escape_debt": 0,
            "corridor_incursion_key": (0, 0.0, 0.0),
            "passive_locality_key": (0.0, 0.0),
            "moves": ({"kind": "overlap_passive_reseat",
                       "search_family": "translation", "refs": ["C1"]},),
        }
        shallower_but_scattered = {
            "overlap_key": (1, 1.0, 1.0), "escape_debt": 0,
            "corridor_incursion_key": (0, 0.0, 0.0),
            "passive_locality_key": (4.5, 4.5),
            "moves": ({"kind": "overlap_passive_reseat",
                       "search_family": "translation", "refs": ["C1"]},),
        }

        selected = synth._parallel_pour_select_overlap_lanes(
            [shallower_but_scattered, local], 1)

        self.assertEqual(selected, [local])

    def test_parallel_passive_owner_geometry_tracks_real_pad_distance(self):
        templates = {
            "U1": ({"pad": "6", "local": (1.0, 0.0)},),
            "C1": ({"pad": "1", "local": (-0.5, 0.0)},
                   {"pad": "2", "local": (0.5, 0.0)}),
        }
        baseline = synth._parallel_pour_passive_owner_geometry(
            {"U1": (10.0, 10.0, 0.0),
             "C1": (12.0, 10.0, 0.0)},
            templates, {"C1": ("U1", "6")})
        scattered = synth._parallel_pour_passive_owner_geometry(
            {"U1": (10.0, 10.0, 0.0),
             "C1": (17.0, 10.0, 0.0)},
            templates, {"C1": ("U1", "6")})
        delta = synth._parallel_pour_passive_owner_geometry_delta(
            baseline, scattered)

        self.assertEqual(baseline["key"], (0.5, 0.5))
        self.assertEqual(scattered["key"], (5.5, 5.5))
        self.assertEqual(delta["key"], (5.0, 5.0))
        self.assertEqual(delta["regressions"][0]["ref"], "C1")

    def test_parallel_critical_terminal_geometry_tracks_length_and_crossing(self):
        templates = {
            "ANCHOR": ({
                "pad": "1", "net": "/RAIL_HI", "local": (-1.0, 0.0),
            }, {
                "pad": "2", "net": "/RAIL_LO", "local": (1.0, 0.0),
            }),
            "FOLLOWER": ({
                "pad": "1", "net": "/RAIL_HI", "local": (-1.0, 0.0),
            }, {
                "pad": "2", "net": "/RAIL_LO", "local": (1.0, 0.0),
            }, {
                "pad": "3", "net": "GND", "local": (0.0, 1.0),
            }),
        }
        specs = ({
            "anchor_ref": "ANCHOR", "ref": "FOLLOWER",
            "family": "/RAIL",
            "nets": ("/RAIL_HI", "/RAIL_LO"),
        },)
        baseline = synth._parallel_pour_critical_terminal_geometry(
            {"ANCHOR": (0.0, 0.0, 0.0),
             "FOLLOWER": (0.0, 5.0, 0.0)}, templates, specs)
        rotated = synth._parallel_pour_critical_terminal_geometry(
            {"ANCHOR": (0.0, 0.0, 0.0),
             "FOLLOWER": (0.0, 5.0, 180.0)}, templates, specs)
        moved = synth._parallel_pour_critical_terminal_geometry(
            {"ANCHOR": (0.0, 0.0, 0.0),
             "FOLLOWER": (10.0, 5.0, 0.0)}, templates, specs)

        self.assertEqual(baseline["key"], (0, 10.0, 10.0))
        self.assertEqual(rotated["key"][0], 1)
        crossing_delta = \
            synth._parallel_pour_critical_terminal_geometry_delta(
                baseline, rotated)
        length_delta = \
            synth._parallel_pour_critical_terminal_geometry_delta(
                baseline, moved)
        self.assertEqual(crossing_delta["key"][0], 1)
        self.assertGreater(length_delta["key"][1], 12.0)
        self.assertEqual(length_delta["regressions"][0]["ref"], "FOLLOWER")

    def test_parallel_foreign_pad_incursion_is_incremental_and_net_aware(self):
        templates = {
            "IC": ({
                "pad": "1", "net": "/SIGNAL", "local": (0.0, 0.0),
                "size": (1.0, 1.0), "rotation_deg": 0.0,
                "layers": ("F.Cu",),
            }, {
                "pad": "2", "net": "/POWER", "local": (0.0, 2.0),
                "size": (1.0, 1.0), "rotation_deg": 0.0,
                "layers": ("F.Cu",),
            }),
        }
        corridors = ({
            "net": "/POWER", "layer": "F.Cu", "rect_index": 0,
            "x0": 4.0, "y0": -1.0, "x1": 6.0, "y1": 3.0,
        },)
        before = {"IC": (0.0, 0.0, 0.0)}
        after = {"IC": (5.0, 0.0, 0.0)}

        delta = synth._parallel_pour_foreign_pad_incursion_delta(
            before, after, ("IC",), templates, corridors)

        self.assertEqual(delta["key"], (1, 1.0, 1.0))
        self.assertEqual(delta["nets"], ("/POWER",))
        self.assertEqual(delta["hits"][0]["pad"], "1")
        self.assertEqual(delta["hits"][0]["pad_net"], "/SIGNAL")

    def test_parallel_foreign_pad_incursion_does_not_recharge_old_debt(self):
        templates = {
            "IC": ({
                "pad": "1", "net": "/SIGNAL", "local": (0.0, 0.0),
                "size": (1.0, 1.0), "rotation_deg": 0.0,
                "layers": ("F.Cu",),
            },),
        }
        corridors = ({
            "net": "/POWER", "layer": "F.Cu", "rect_index": 0,
            "x0": -1.0, "y0": -1.0, "x1": 2.0, "y1": 1.0,
        },)

        delta = synth._parallel_pour_foreign_pad_incursion_delta(
            {"IC": (0.0, 0.0, 0.0)}, {"IC": (1.0, 0.0, 0.0)},
            ("IC",), templates, corridors)

        self.assertEqual(delta["before_key"][0], 1)
        self.assertEqual(delta["after_key"][0], 1)
        self.assertEqual(delta["key"], (0, 0.0, 0.0))

    def test_parallel_overlap_exact_failure_keeps_causal_lane_stack(self):
        report = {}
        proposal = {
            "overlap_key": (2, 1.25, 0.75),
            "moves": ({
                "kind": "overlap_passive_reseat",
                "search_family": "passive_reseat",
                "refs": ["CAP"],
                "source_pairs": [["CAP", "IC"]],
            },),
        }

        first = synth._parallel_pour_record_overlap_exact_failure(
            report, proposal, ["/POWER_B", "/POWER_A"],
            terminal_index=1, round_index=5, lane="risk")
        second = synth._parallel_pour_record_overlap_exact_failure(
            report, proposal, ["/POWER_A"], terminal_index=1,
            round_index=6, lane="risk", cached=True)

        self.assertIs(first, second)
        self.assertEqual(second["total"], 2)
        self.assertEqual(second["cached"], 1)
        self.assertEqual(second["by_lane"], {"risk": 2})
        self.assertEqual(second["by_family"], {"passive_reseat": 2})
        self.assertEqual(second["by_net"], {
            "/POWER_A": 2, "/POWER_B": 1})
        self.assertEqual(second["by_lane_family_net"], {
            "risk|passive_reseat|/POWER_A": 2,
            "risk|passive_reseat|/POWER_B": 1,
        })
        self.assertEqual(second["samples"][0]["failed_nets"],
                         ["/POWER_A", "/POWER_B"])
        self.assertEqual(second["samples"][0]["refs"], ["CAP"])
        self.assertEqual(set(second["representatives"]), {
            "risk|passive_reseat|/POWER_A",
            "risk|passive_reseat|/POWER_B",
        })

    def test_parallel_overlap_exact_failure_representatives_bypass_cap(self):
        report = {}
        base = {
            "overlap_key": (1, 1.0, 1.0),
            "moves": ({"kind": "overlap_blocker_cell",
                       "search_family": "translation",
                       "refs": ["IC"]},),
        }
        passive = {
            "overlap_key": (1, 0.5, 0.5),
            "moves": ({"kind": "overlap_passive_reseat",
                       "search_family": "passive_reseat",
                       "refs": ["CAP"]},),
        }
        synth._parallel_pour_record_overlap_exact_failure(
            report, base, ["/A"], terminal_index=0, round_index=1,
            lane="base", sample_limit=1)
        summary = synth._parallel_pour_record_overlap_exact_failure(
            report, passive, ["/B"], terminal_index=0, round_index=2,
            lane="risk", sample_limit=1)

        self.assertEqual(len(summary["samples"]), 1)
        self.assertIn("risk|passive_reseat|/B",
                      summary["representatives"])
        self.assertEqual(
            summary["representatives"][
                "risk|passive_reseat|/B"]["refs"], ["CAP"])

    def test_parallel_overlap_budget_explores_then_exploits(self):
        limits = synth._parallel_pour_overlap_trial_limits(128, 4)

        self.assertEqual(limits, (48, 48, 16, 16))
        self.assertEqual(sum(limits), 128)
        self.assertTrue(all(limit > 0 for limit in limits))

    def test_parallel_overlap_additive_escape_budget_preserves_strict_share(self):
        strict = synth._parallel_pour_overlap_trial_limits(128, 4)
        with_escape = synth._parallel_pour_overlap_trial_limits(160, 4)

        self.assertEqual(with_escape, (60, 60, 20, 20))
        self.assertTrue(all(after >= before for after, before in
                            zip(with_escape, strict)))

    def test_parallel_overlap_transform_budget_is_separate_and_bounded(self):
        base = synth._parallel_pour_overlap_trial_limits(160, 4)
        transforms = synth._parallel_pour_overlap_trial_limits(48, 4)
        combined = tuple(left + right for left, right in
                         zip(base, transforms))

        self.assertEqual(transforms, (18, 18, 6, 6))
        self.assertEqual(combined, (78, 78, 26, 26))
        self.assertEqual(sum(combined), 208)

    def test_parallel_overlap_risk_budget_is_separate_and_bounded(self):
        base = synth._parallel_pour_overlap_trial_limits(160, 4)
        transforms = synth._parallel_pour_overlap_trial_limits(48, 4)
        risk = synth._parallel_pour_overlap_trial_limits(32, 4)
        combined = tuple(left + middle + right
                         for left, middle, right in zip(
                             base, transforms, risk))

        self.assertEqual(risk, (12, 12, 4, 4))
        self.assertEqual(combined, (90, 90, 30, 30))
        self.assertEqual(sum(combined), 240)

    def test_parallel_overlap_budget_never_exceeds_small_global_cap(self):
        limits = synth._parallel_pour_overlap_trial_limits(3, 4)

        self.assertEqual(sum(limits), 3)
        self.assertEqual(limits, (2, 1, 0, 0))

    def test_placement_craft_cache_uses_exact_content_and_returns_copies(self):
        with tempfile.TemporaryDirectory() as directory:
            board = os.path.join(directory, "placed.kicad_pcb")
            with open(board, "w", encoding="utf-8") as handle:
                handle.write("exact placement state")
            cfg = SimpleNamespace(
                params={"decoupler_ground_reach_mm": 1.5},
                pins={}, net="", sch="")
            synth._clear_placement_craft_cache()
            with mock.patch.object(
                    synth, "_placement_craft_evidence_uncached",
                    return_value={"ok": True, "details": []}) as compute:
                first = synth.placement_craft_evidence(board, cfg=cfg)
                first["details"].append("caller annotation")
                second = synth.placement_craft_evidence(board, cfg=cfg)

            self.assertEqual(compute.call_count, 1)
            self.assertEqual(second, {"ok": True, "details": []})
            self.assertEqual(synth.placement_craft_cache_stats()["hits"], 1)

    def test_placement_craft_cache_invalidates_on_policy_change(self):
        with tempfile.TemporaryDirectory() as directory:
            board = os.path.join(directory, "placed.kicad_pcb")
            with open(board, "w", encoding="utf-8") as handle:
                handle.write("same exact placement state")
            cfg = SimpleNamespace(params={"policy": 1}, pins={}, net="",
                                  sch="")
            synth._clear_placement_craft_cache()
            with mock.patch.object(
                    synth, "_placement_craft_evidence_uncached",
                    return_value={"ok": True}) as compute:
                synth.placement_craft_evidence(board, cfg=cfg)
                cfg.params["policy"] = 2
                synth.placement_craft_evidence(board, cfg=cfg)

            self.assertEqual(compute.call_count, 2)

    def test_placement_craft_cache_separates_relief_detail_modes(self):
        with tempfile.TemporaryDirectory() as directory:
            board = os.path.join(directory, "placed.kicad_pcb")
            with open(board, "w", encoding="utf-8") as handle:
                handle.write("same placement with two report detail modes")
            cfg = SimpleNamespace(params={}, pins={}, net="", sch="")
            synth._clear_placement_craft_cache()
            with mock.patch.object(
                    synth, "_placement_craft_evidence_uncached",
                    side_effect=lambda *_args, relief_diagnostics=True,
                    **_kwargs: {
                        "ok": True,
                        "relief_diagnostics": relief_diagnostics,
                    }) as compute:
                detailed = synth.placement_craft_evidence(
                    board, cfg=cfg, relief_diagnostics=True)
                admission = synth.placement_craft_evidence(
                    board, cfg=cfg, relief_diagnostics=False)
                detailed_again = synth.placement_craft_evidence(
                    board, cfg=cfg, relief_diagnostics=True)

            self.assertTrue(detailed["relief_diagnostics"])
            self.assertFalse(admission["relief_diagnostics"])
            self.assertEqual(detailed_again, detailed)
            self.assertEqual(compute.call_count, 2)

    def test_stranded_distance_uses_pad_edges_for_large_components(self):
        # A 16mm bulk capacitor and a 2mm destination whose centres are 29mm
        # apart have only an 11mm copper-launch gap; center-only gating would
        # falsely classify the deliberately large part as a 29mm orphan.
        gap = synth._rect_gap_mm((0.0, 0.0, 16.0, 16.0),
                                 (27.0, 7.0, 29.0, 9.0))

        self.assertEqual(gap, 11.0)
        self.assertLess(gap, 22.0)

    def test_failed_decoupler_cell_gets_generic_owner_and_cluster_moves(self):
        candidate = SimpleNamespace(P={
            "OWNER": (10.0, 10.0, 0.0),
            "CAP_A": (12.0, 10.0, 90.0),
            "CAP_B": (10.0, 12.0, 0.0),
        })
        rows = [
            {"owner_ref": "OWNER", "cap_ref": "CAP_A",
             "actionable": True, "supply_access_ok": False,
             "supply_access_reason": "blocked"},
            {"owner_ref": "OWNER", "cap_ref": "CAP_B",
             "actionable": False, "supply_access_ok": True},
        ]
        moves = synth._decoupler_owner_move_specs(candidate, rows)
        kinds = {move["kind"] for move in moves}
        self.assertEqual(kinds, {
            "decoupler_owner_rotate", "decoupler_cell_rotate",
            "decoupler_owner_toward_cap", "decoupler_cell_translate",
        })
        self.assertEqual([move["kind"] for move in moves[:4]], [
            "decoupler_owner_rotate", "decoupler_cell_rotate",
            "decoupler_owner_toward_cap", "decoupler_cell_translate",
        ])
        rotate = next(move for move in moves
                      if move["kind"] == "decoupler_cell_rotate"
                      and move["delta_deg"] == 90.0)
        self.assertEqual(rotate["placements"]["OWNER"],
                         (10.0, 10.0, 90.0))
        self.assertAlmostEqual(rotate["placements"]["CAP_A"][0], 10.0)
        self.assertAlmostEqual(rotate["placements"]["CAP_A"][1], 8.0)
        self.assertAlmostEqual(rotate["placements"]["CAP_A"][2], 180.0)
        self.assertAlmostEqual(rotate["placements"]["CAP_B"][0], 12.0)
        self.assertAlmostEqual(rotate["placements"]["CAP_B"][1], 10.0)
        self.assertAlmostEqual(rotate["placements"]["CAP_B"][2], 90.0)

    def test_explicitly_fixed_owner_blocks_cell_cooptimization(self):
        candidate = SimpleNamespace(P={
            "OWNER": (10.0, 10.0, 0.0),
            "CAP": (12.0, 10.0, 0.0),
        })
        rows = [{"owner_ref": "OWNER", "cap_ref": "CAP",
                 "actionable": True, "supply_access_ok": False}]
        self.assertEqual(synth._decoupler_owner_move_specs(
            candidate, rows, immovable={"OWNER"}), [])

    def test_explicitly_fixed_cap_blocks_owner_cell_cooptimization(self):
        candidate = SimpleNamespace(P={
            "OWNER": (10.0, 10.0, 0.0),
            "CAP": (12.0, 10.0, 0.0),
        })
        rows = [{"owner_ref": "OWNER", "cap_ref": "CAP",
                 "actionable": True, "supply_access_ok": False}]
        moves = synth._decoupler_owner_move_specs(
            candidate, rows, immovable={"CAP"})
        self.assertFalse(any(len(move["placements"]) > 1
                             for move in moves))

    def test_owner_rotation_solves_fresh_cap_seats_from_pad_geometry(self):
        candidate = SimpleNamespace(P={
            "OWNER": (10.0, 10.0, 0.0),
            "CAP": (12.0, 10.0, 0.0),
        })
        rows = [{
            "owner_ref": "OWNER", "cap_ref": "CAP",
            "actionable": True, "supply_access_ok": False,
            "owner_position_mm": [10.0, 10.0],
            "owner_supply_position_mm": [11.0, 10.0],
            "owner_ground_position_mm": [9.0, 10.0],
            "owner_ground_positions_mm": [
                {"pin": "G", "position": [9.0, 10.0]}],
            "cap_position_mm": [12.0, 10.0],
            "cap_supply_position_mm": [11.5, 10.0],
            "cap_ground_position_mm": [12.5, 10.0],
        }]
        moves = synth._decoupler_owner_move_specs(candidate, rows)
        reoriented = [move for move in moves
                      if move["kind"] == "decoupler_cell_reorient"]
        self.assertTrue(reoriented)
        self.assertTrue(all(set(move["placements"]) == {"OWNER", "CAP"}
                            for move in reoriented))
        self.assertTrue(any(
            move["placements"]["CAP"] != candidate.P["CAP"]
            for move in reoriented))
        self.assertTrue(any(
            move["delta_deg"] == 0.0
            and move["placements"]["OWNER"] == candidate.P["OWNER"]
            for move in reoriented),
            "the cell solver must be able to repack caps without rotating IC")

    def test_blocked_cell_can_translate_owner_then_reseat_cap(self):
        candidate = SimpleNamespace(P={
            "OWNER": (10.0, 10.0, 0.0),
            "CAP": (12.0, 8.0, 0.0),
        }, back_refs=())
        rows = [{
            "owner_ref": "OWNER", "cap_ref": "CAP",
            "actionable": True, "status": "assigned",
            "supply_access_ok": False,
            "supply_access_reason": "no guarded local supply path",
            "owner_position_mm": [10.0, 10.0],
            "owner_supply_position_mm": [11.0, 10.5],
            "owner_ground_position_mm": [11.0, 9.5],
            "owner_ground_positions_mm": [
                {"pin": "G", "position": [11.0, 9.5]}],
            "cap_position_mm": [12.0, 8.0],
            "cap_supply_position_mm": [12.48, 8.0],
            "cap_ground_position_mm": [11.52, 8.0],
        }]
        comps = {
            "OWNER": "cec-Package_SO:VSSOP-10_3x3mm_P0.5mm",
            "CAP": "cec-Capacitor_SMD:C_0402_1005Metric",
        }
        moves = synth._decoupler_owner_move_specs(
            candidate, rows, comps=comps)
        translated = [move for move in moves
                      if move["kind"] ==
                      "decoupler_owner_cell_reseat"]
        self.assertTrue(translated)
        self.assertTrue(all(set(move["placements"]) == {"OWNER", "CAP"}
                            for move in translated))
        self.assertTrue(any(
            move["placements"]["OWNER"] != candidate.P["OWNER"]
            and move["placements"]["CAP"] != candidate.P["CAP"]
            for move in translated))

    def test_joint_cell_legalizer_mixes_cap_ranks_to_avoid_collision(self):
        candidate = SimpleNamespace(P={
            "OWNER": (0.0, 0.0, 0.0),
            "CAP_A": (3.0, 0.0, 0.0),
            "CAP_B": (-3.0, 0.0, 0.0),
        }, back_refs=())
        options = {
            # Equal-ranked independent choices collide.  A legal macro must
            # select a different rank for one cap rather than discard the
            # whole owner orientation.
            "CAP_A": [((0.1, 0.2), (2.0, 0.0, 0.0)),
                      ((0.2, 0.3), (2.0, 2.0, 0.0))],
            "CAP_B": [((0.1, 0.2), (2.0, 0.0, 0.0)),
                      ((0.2, 0.3), (2.0, 2.0, 0.0))],
        }

        def bbox(_ref, position):
            x, y, _rotation = position
            return (x - 0.4, x + 0.4, y - 0.4, y + 0.4)

        variants = synth._select_local_cell_placements(
            candidate, "OWNER", candidate.P["OWNER"], options, {},
            bbox_fn=bbox)
        self.assertTrue(variants)
        for variant in variants:
            self.assertNotEqual(variant["placements"]["CAP_A"],
                                variant["placements"]["CAP_B"])

    def test_joint_cell_legalizer_projects_seat_outside_owner(self):
        candidate = SimpleNamespace(P={
            "OWNER": (0.0, 0.0, 0.0),
            "CAP": (3.0, 0.0, 0.0),
        }, back_refs=())
        options = {"CAP": [((0.1, 0.2), (0.3, 0.0, 0.0))]}

        def bbox(_ref, position):
            x, y, _rotation = position
            return (x - 0.5, x + 0.5, y - 0.5, y + 0.5)

        variants = synth._select_local_cell_placements(
            candidate, "OWNER", candidate.P["OWNER"], options, {},
            bbox_fn=bbox)
        self.assertTrue(variants)
        cap_x, cap_y, _rotation = variants[0]["placements"]["CAP"]
        self.assertGreaterEqual(max(abs(cap_x), abs(cap_y)), 1.05)
        self.assertEqual(variants[0]["external_blockers"], [])

    def test_joint_cell_legalizer_reports_single_external_blocker(self):
        candidate = SimpleNamespace(P={
            "OWNER": (0.0, 0.0, 0.0),
            "CAP": (3.0, 0.0, 0.0),
            "LOCAL_PASSIVE": (2.0, 0.0, 0.0),
        }, back_refs=())
        options = {"CAP": [((0.1, 0.2), (2.0, 0.0, 0.0)),
                           ((0.2, 0.3), (0.0, 2.0, 0.0))]}

        def bbox(_ref, position):
            x, y, _rotation = position
            return (x - 0.4, x + 0.4, y - 0.4, y + 0.4)

        variants = synth._select_local_cell_placements(
            candidate, "OWNER", candidate.P["OWNER"], options, {},
            bbox_fn=bbox)
        self.assertTrue(variants)
        self.assertEqual(variants[0]["external_blockers"],
                         ["LOCAL_PASSIVE"])
        self.assertTrue(any(not row["external_blockers"]
                            for row in variants))

    def test_owner_cooptimization_round_robins_failed_cells(self):
        candidate = SimpleNamespace(P={
            "OWNER_A": (10.0, 10.0, 0.0),
            "CAP_A": (12.0, 10.0, 0.0),
            "OWNER_B": (30.0, 10.0, 0.0),
            "CAP_B": (32.0, 10.0, 0.0),
        })
        rows = [
            {"owner_ref": "OWNER_A", "cap_ref": "CAP_A",
             "actionable": True, "supply_access_ok": False},
            {"owner_ref": "OWNER_B", "cap_ref": "CAP_B",
             "actionable": True, "supply_access_ok": False},
        ]
        moves = synth._decoupler_owner_move_specs(candidate, rows)
        self.assertEqual([move["owner_ref"] for move in moves[:4]],
                         ["OWNER_A", "OWNER_B", "OWNER_A", "OWNER_B"])

    def test_cluster_move_can_swap_one_local_blocker_into_vacated_seat(self):
        candidate = SimpleNamespace(P={
            "OWNER": (10.0, 10.0, 0.0),
            "CAP": (12.0, 10.0, 90.0),
            "R_BLOCK": (14.0, 10.0, 180.0),
        })
        placements = {
            "OWNER": (10.0, 10.0, 180.0),
            "CAP": (14.0, 10.0, 270.0),
        }
        variants = synth._placement_local_eviction_variants(
            candidate, placements, {("CAP", "R_BLOCK")},
            lambda ref: ref.startswith(("C", "R")))
        self.assertEqual(len(variants), 1)
        swapped, blocker = variants[0]
        self.assertEqual(blocker, "R_BLOCK")
        self.assertEqual(swapped["R_BLOCK"], (12.0, 10.0, 180.0))

    def test_cluster_eviction_refuses_nonlocal_or_multiple_blockers(self):
        candidate = SimpleNamespace(P={
            "OWNER": (10.0, 10.0, 0.0),
            "CAP": (12.0, 10.0, 90.0),
            "R_A": (14.0, 10.0, 0.0),
            "R_B": (14.0, 12.0, 0.0),
        })
        placements = {"OWNER": (11.0, 10.0, 0.0)}
        can_evict = lambda ref: ref.startswith(("C", "R"))
        self.assertEqual(synth._placement_local_eviction_variants(
            candidate, placements, {("OWNER", "CAP")}, can_evict), [])
        placements = {"CAP": (14.0, 11.0, 90.0)}
        self.assertEqual(synth._placement_local_eviction_variants(
            candidate, placements,
            {("CAP", "R_A"), ("CAP", "R_B")}, can_evict), [])

    def test_evicted_local_part_gets_union_tangent_seats(self):
        candidate = SimpleNamespace(P={
            "MOVABLE": (0.0, 0.0, 90.0),
            "BLOCK_A": (1.5, 0.0, 0.0),
            "BLOCK_B": (1.5, 1.0, 0.0),
        })
        placements = {"MOVABLE": (1.0, 0.0, 90.0)}

        def bbox(_ref, position):
            x, y, _rotation = position
            return (x - 0.5, x + 0.5, y - 0.5, y + 0.5)

        variants = synth._placement_tangent_relocation_variants(
            candidate, placements, "MOVABLE",
            {("MOVABLE", "BLOCK_A"), ("BLOCK_B", "MOVABLE")},
            {ref: ref for ref in candidate.P}, bbox_fn=bbox)
        self.assertEqual(len(variants), 4)
        relocated = {side: rows["MOVABLE"] for rows, side in variants}
        for actual, expected in (
                (relocated["left"], (0.45, 0.0, 90.0)),
                (relocated["right"], (2.55, 0.0, 90.0)),
                (relocated["above"], (1.0, -1.05, 90.0)),
                (relocated["below"], (1.0, 2.05, 90.0))):
            for value, want in zip(actual, expected):
                self.assertAlmostEqual(value, want)

    def test_one_step_legalizer_composes_tangent_with_passive_eviction(self):
        candidate = SimpleNamespace(P={
            "CAP": (0.0, 0.0, 0.0),
            "PASSIVE": (2.0, 0.0, 90.0),
        }, back_refs=())
        placements = {"CAP": (2.0, 0.0, 180.0)}
        swapped = {**placements, "PASSIVE": (0.0, 0.0, 90.0)}
        relocated = {**placements, "PASSIVE": (-1.0, 0.0, 90.0)}
        with mock.patch.object(
                synth, "_overlap_pairs",
                side_effect=[{("CAP", "PASSIVE")}, set()]), \
                mock.patch.object(
                    synth, "_placement_local_eviction_variants",
                    return_value=[(swapped, "PASSIVE")]), \
                mock.patch.object(
                    synth, "_placement_tangent_relocation_variants",
                    return_value=[(relocated, "left")]):
            variants = synth._placement_one_step_local_legalizations(
                candidate, placements, set(), {"CAP": object(),
                                                "PASSIVE": object()},
                lambda _ref: True)
        self.assertEqual(variants, [
            (swapped, "PASSIVE", "evicted_swap"),
            (relocated, "PASSIVE", "evicted_left"),
        ])

    def test_physical_only_footprints_join_fast_overlap_model(self):
        board = pcbnew.BOARD()
        for ref in ("MARK_A", "MARK_B"):
            footprint = pcbnew.FOOTPRINT(board)
            footprint.SetReference(ref)
            footprint.SetFPID(pcbnew.LIB_ID(
                "cec-Fiducial", "Fiducial_1mm_Mask2mm"))
            footprint.SetPosition(pcbnew.VECTOR2I_MM(10, 10))
            board.Add(footprint)
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "physical.kicad_pcb")
            pcbnew.SaveBoard(path, board)
            comps = synth._extend_footprint_map_from_board(
                {}, path, refs=("MARK_A", "MARK_B"))
        self.assertEqual(set(comps), {"MARK_A", "MARK_B"})
        pairs = synth._overlap_pairs({
            "MARK_A": (10.0, 10.0, 0.0),
            "MARK_B": (10.0, 10.0, 0.0),
        }, comps)
        self.assertEqual(pairs, {("MARK_A", "MARK_B")})

    def test_physical_overlap_repair_is_generic_and_hard_first(self):
        comps = {
            "DEVICE": "cec-Capacitor_SMD:CP_Elec_16x17.5",
            "DATUM": "cec-Fiducial:Fiducial_1mm_Mask2mm",
        }
        candidate = SimpleNamespace(P={
            "DEVICE": (10.0, 10.0, 0.0),
            "DATUM": (10.0, 10.0, 0.0),
        })
        pairs = synth._overlap_pairs(candidate.P, comps)
        moves = synth._courtyard_overlap_move_specs(
            candidate, pairs, comps, immovable={"DATUM"})
        self.assertEqual(len(moves), 4)
        self.assertTrue(all(move["ref"] == "DEVICE" for move in moves))
        self.assertTrue(all(move["blocker_ref"] == "DATUM"
                            for move in moves))
        repaired = dict(candidate.P)
        repaired["DEVICE"] = moves[0]["position"]
        self.assertFalse(synth._overlap_pairs(repaired, comps))

        clean_electrical = {
            "errors": [],
            "decoupler": {"details": [], "violations": []},
            "stranded": {"details": [], "violations": []},
            "pair_launch": {"violations": []},
        }
        self.assertLess(
            synth.placement_craft_repair_key(clean_electrical, 0),
            synth.placement_craft_repair_key(clean_electrical, 1))

    def test_unconstrained_physical_datum_yields_to_fixed_component(self):
        comps = {
            "FIXED_DEVICE": "cec-Capacitor_SMD:CP_Elec_16x17.5",
            "PHYSICAL_DATUM": "cec-Fiducial:Fiducial_1mm_Mask2mm",
        }
        candidate = SimpleNamespace(P={
            "FIXED_DEVICE": (10.0, 10.0, 0.0),
            "PHYSICAL_DATUM": (10.0, 10.0, 0.0),
        })
        moves = synth._courtyard_overlap_move_specs(
            candidate, synth._overlap_pairs(candidate.P, comps), comps,
            immovable={"FIXED_DEVICE"})
        self.assertTrue(moves)
        self.assertTrue(all(move["ref"] == "PHYSICAL_DATUM"
                            for move in moves))

    def test_craft_epochs_continue_only_from_monotonic_incumbent(self):
        cfg = SimpleNamespace(params={})
        first, second, clean = object(), object(), object()
        reports = [
            (second, {
                "schema": 1, "changed": True, "accepted_count": 1,
                "ok": False, "result_key": [0, 2],
                "rounds": [{"round": 1, "accepted": True}],
            }),
            (clean, {
                "schema": 1, "changed": True, "accepted_count": 1,
                "ok": True, "result_key": [0, 1],
                "rounds": [{"round": 1, "accepted": True}],
            }),
        ]
        with mock.patch.object(
                synth, "repair_placement_craft", side_effect=reports):
            result, report = synth.repair_placement_craft_epochs(
                cfg, first, max_trials=8, rounds=2, epochs=4)
        self.assertIs(result, clean)
        self.assertTrue(report["ok"])
        self.assertEqual(report["stop_reason"], "gate_clean")
        self.assertEqual(report["accepted_count"], 2)
        self.assertEqual([row["round"] for row in report["rounds"]], [1, 2])
        self.assertEqual([row["epoch"] for row in report["rounds"]], [1, 2])

    def test_craft_epochs_emit_plateau_certificate(self):
        cfg = SimpleNamespace(params={})
        first, incumbent = object(), object()
        reports = [
            (incumbent, {
                "schema": 1, "changed": True, "accepted_count": 1,
                "ok": False, "result_key": [0, 1],
                "rounds": [{"round": 1, "accepted": True}],
            }),
            (incumbent, {
                "schema": 1, "changed": False, "accepted_count": 0,
                "ok": False, "result_key": [0, 1],
                "rounds": [{"round": 1, "accepted": False,
                            "reason": "no_monotonic_legal_improvement"}],
            }),
        ]
        with mock.patch.object(
                synth, "repair_placement_craft", side_effect=reports):
            result, report = synth.repair_placement_craft_epochs(
                cfg, first, max_trials=8, rounds=2, epochs=4)
        self.assertIs(result, incumbent)
        self.assertFalse(report["ok"])
        self.assertEqual(report["stop_reason"], "plateau")
        self.assertEqual(len(report["epochs"]), 2)

    def test_epoch_that_improves_then_plateaus_is_not_restarted(self):
        cfg = SimpleNamespace(params={})
        first, incumbent = object(), object()
        epoch = {
            "schema": 1, "changed": True, "accepted_count": 1,
            "ok": False, "result_key": [0, 1],
            "stop_reason": "plateau",
            "rounds": [
                {"round": 1, "accepted": True},
                {"round": 2, "accepted": False},
            ],
        }
        with mock.patch.object(
                synth, "repair_placement_craft",
                return_value=(incumbent, epoch)) as repair:
            result, report = synth.repair_placement_craft_epochs(
                cfg, first, max_trials=8, rounds=2, epochs=4)
        self.assertIs(result, incumbent)
        self.assertEqual(repair.call_count, 1)
        self.assertEqual(report["stop_reason"], "plateau")
        self.assertEqual(len(report["epochs"]), 1)

    def test_craft_trial_evaluation_is_ordered_and_serial_for_one_worker(self):
        cfg = SimpleNamespace(params={"placement_craft_eval_workers": 1})
        jobs = [{"path": "b"}, {"path": "a"}]
        with mock.patch.object(
                synth, "_placement_craft_trial_worker",
                side_effect=lambda job: {"ok": True, "evidence": job["path"]}):
            results, runtime = synth._evaluate_placement_craft_trials(
                cfg, jobs)
        self.assertEqual([row["evidence"] for row in results], ["b", "a"])
        self.assertEqual(runtime["workers"], 1)
        self.assertFalse(runtime["isolated"])

    def test_craft_trial_omits_diagnostic_ablation_but_not_exact_evidence(self):
        payload = {
            "candidate": object(), "cfg": SimpleNamespace(params={}),
            "path": "trial.kicad_pcb",
        }
        with mock.patch.object(synth, "materialize"), \
                mock.patch.object(
                    synth, "placement_craft_evidence",
                    return_value={"ok": True}) as evidence:
            result = synth._placement_craft_trial_worker(payload)

        self.assertTrue(result["ok"])
        evidence.assert_called_once_with(
            "trial.kicad_pcb", cfg=payload["cfg"],
            relief_diagnostics=False)

    def test_craft_trial_pool_has_hard_worker_and_recycle_caps(self):
        captured = []

        class FakePool:
            def __init__(self, **kwargs):
                captured.append(kwargs)

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def map(self, fn, jobs):
                return [fn(job) for job in jobs]

        cfg = SimpleNamespace(params={
            "placement_craft_eval_workers": 999,
            "placement_craft_tasks_per_child": 999,
        })
        jobs = [{"sequence": index} for index in range(40)]
        with mock.patch.object(synth, "ProcessPoolExecutor", FakePool), \
                mock.patch.object(synth.os, "cpu_count", return_value=32), \
                mock.patch.object(
                    synth, "_placement_craft_trial_worker",
                    side_effect=lambda job: {
                        "ok": True, "evidence": job["sequence"]}):
            results, runtime = synth._evaluate_placement_craft_trials(
                cfg, jobs)
        self.assertEqual([row["max_workers"] for row in captured], [16])
        self.assertTrue(all("max_tasks_per_child" not in row
                            for row in captured))
        self.assertEqual(runtime["workers"], 16)
        self.assertEqual(runtime["tasks_per_worker_generation"], 4)
        self.assertEqual(runtime["jobs_per_generation"], 64)
        self.assertEqual(runtime["worker_generations"], 1)
        self.assertTrue(runtime["isolated"])
        self.assertEqual([row["evidence"] for row in results], list(range(40)))

    def test_real_craft_trials_run_in_recyclable_spawn_workers(self):
        cfg = synth.Config.load("pcie-out-db")
        if not os.path.isfile(cfg.pcb):
            self.skipTest("cross-board placement fixture unavailable")
        candidate = synth.placement_candidate_from_board(cfg, cfg.pcb)
        cfg.params["placement_craft_eval_workers"] = 2
        cfg.params["placement_craft_tasks_per_child"] = 1
        with tempfile.TemporaryDirectory() as directory:
            jobs = [
                {"candidate": candidate, "cfg": cfg,
                 "path": os.path.join(directory, "%d.kicad_pcb" % index)}
                for index in range(10)
            ]
            results, runtime = synth._evaluate_placement_craft_trials(
                cfg, jobs)
        self.assertTrue(runtime["isolated"])
        self.assertEqual(runtime["workers"], 2)
        self.assertEqual(runtime["tasks_per_worker_generation"], 1)
        self.assertEqual(runtime["jobs_per_generation"], 2)
        self.assertEqual(runtime["worker_generations"], 5)
        self.assertTrue(all(row.get("ok") for row in results), results)

    def test_pair_launch_blocker_gets_topology_directed_reseat(self):
        candidate = SimpleNamespace(P={
            "D6": (10.0, 10.0, 0.0),
            "C28": (12.0, 8.0, 180.0),
        })
        evidence = {
            "pair_launch": {"violations": [{
                "blocker_ref": "C28", "station_ref": "D6",
                "pair": "USB_D", "leg": 2,
                "perpendicular": [1.0, 0.0],
                "suggested_side": -1.0, "minimum_shift_mm": 0.4,
            }]},
            "decoupler": {"details": []},
            "stranded": {"details": []},
        }
        moves = synth._placement_craft_move_specs(candidate, evidence)
        self.assertTrue(moves)
        self.assertEqual(moves[0]["kind"], "pair_launch_reseat")
        self.assertEqual(moves[0]["owner_ref"], "D6")
        self.assertEqual(moves[0]["position"], (11.2, 8.0, 180.0))

    def test_legacy_power_body_tuple_is_non_crashing_evidence(self):
        candidate = SimpleNamespace(P={"U4": (10.0, 10.0, 0.0)})
        evidence = {
            "pour_territory": {"violations": []},
            "power_body_clearance": {
                "violations": [("U4", "/PWR", "F.Cu")]},
            "decoupler": {"details": []},
            "stranded": {"details": []},
        }
        # A legacy row has no displacement box, so it cannot authorize a
        # move. It must remain a reported blocker without aborting the whole
        # placement pipeline.
        self.assertEqual(synth._placement_craft_move_specs(
            candidate, evidence, comps={"U4": object()}), [])

    def test_fragmented_detection_cell_moves_with_its_bypass_cap(self):
        candidate = SimpleNamespace(P={
            "INA": (50.0, 20.0, 270.0),
            "CMP": (10.0, 20.0, 90.0),
            "C_CMP": (12.0, 21.0, 0.0),
        })
        evidence = {
            "detection_cell": {"ok": False, "violations": [
                ["CMP", "INA", "/DETAMP", 40.0],
            ]},
            "pour_territory": {"violations": []},
            "pair_launch": {"violations": []},
            "critical_terminal_order": {"violations": []},
            "decoupler": {"details": [{
                "owner_ref": "CMP", "cap_ref": "C_CMP",
                "status": "assigned",
            }]},
            "stranded": {"details": []},
        }

        moves = synth._placement_craft_move_specs(
            candidate, evidence,
            required_stages=["detection_cell_placement"])

        self.assertTrue(moves)
        self.assertEqual({move["kind"] for move in moves},
                         {"detection_cell_macro_reseat"})
        first = moves[0]
        self.assertEqual(set(first["placements"]), {"CMP", "C_CMP"})
        cmp_dx = first["placements"]["CMP"][0] - candidate.P["CMP"][0]
        cap_dx = first["placements"]["C_CMP"][0] - candidate.P["C_CMP"][0]
        cmp_dy = first["placements"]["CMP"][1] - candidate.P["CMP"][1]
        cap_dy = first["placements"]["C_CMP"][1] - candidate.P["C_CMP"][1]
        self.assertAlmostEqual(cmp_dx, cap_dx)
        self.assertAlmostEqual(cmp_dy, cap_dy)
        self.assertLessEqual(
            ((first["placements"]["CMP"][0] - candidate.P["INA"][0]) ** 2
             + (first["placements"]["CMP"][1]
                - candidate.P["INA"][1]) ** 2) ** 0.5,
            7.0)

    def test_decoupler_repair_proposes_around_actual_supply_pad(self):
        candidate = SimpleNamespace(P={
            "U1": (10.0, 10.0, 0.0),
            "C1": (20.0, 20.0, 0.0),
        })
        evidence = {
            "decoupler": {"details": [{
                "actionable": True,
                "cap_ref": "C1", "owner_ref": "U1",
                "owner_position_mm": [10.0, 10.0],
                "owner_supply_position_mm": [12.0, 10.0],
                "owner_ground_position_mm": [12.0, 11.0],
                "cap_position_mm": [20.0, 20.0],
                "cap_supply_position_mm": [20.5, 20.0],
            }]},
            "stranded": {"details": []},
        }
        moves = synth._placement_craft_move_specs(candidate, evidence)
        self.assertTrue(moves)
        self.assertEqual(moves[0]["kind"], "decoupler_pin_reseat")
        # The first target is 1.25 mm outside the actual x=12 supply pad,
        # minus the capacitor's 0.5 mm pad offset: centre x=12.75.  A legacy
        # body-centred proposal would be several millimetres from x=10.
        self.assertAlmostEqual(moves[0]["position"][0], 12.75, places=5)
        self.assertAlmostEqual(moves[0]["position"][1], 10.0, places=5)

    def test_access_certificate_places_cap_on_clear_owner_escape(self):
        candidate = SimpleNamespace(P={
            "REG": (0.0, 0.0, 0.0),
            "BYP": (2.0, 0.0, 0.0),
        })
        evidence = {
            "decoupler": {"details": [{
                "actionable": True, "status": "assigned",
                "cap_ref": "BYP", "owner_ref": "REG", "rail": "+V",
                "supply_access_ok": False,
                "supply_access_reason": "no guarded local supply path",
                "owner_position_mm": [0.0, 0.0],
                "owner_supply_position_mm": [0.0, 0.0],
                "owner_ground_position_mm": [0.0, 1.0],
                "owner_ground_positions_mm": [
                    {"pin": "G", "position": [0.0, 1.0]}],
                "cap_position_mm": [2.0, 0.0],
                "cap_supply_position_mm": [1.5, 0.0],
                "cap_ground_position_mm": [2.5, 0.0],
                "supply_access_certificate": {"layers": [{
                    "endpoint_escape": [{
                        "endpoint": "a", "clear_rays": ["W"],
                        "probe_width_mm": 0.2,
                    }],
                }]},
            }]},
            "pair_launch": {"violations": []},
            "stranded": {"details": []},
        }
        moves = synth._placement_craft_move_specs(candidate, evidence)
        move = moves[0]
        self.assertEqual(move["kind"], "decoupler_access_escape")
        self.assertEqual(move["certificate_direction"], "W")
        cx, cy, rotation = move["position"]
        self.assertEqual(rotation, 180.0)
        # At 180 degrees the rail land faces the owner and the GND land is
        # farther west/outboard, away from the current-carrying pin escape.
        rail_x = cx + 0.5
        ground_x = cx - 0.5
        self.assertAlmostEqual(rail_x, -0.85, places=5)
        self.assertLess(ground_x, rail_x)
        self.assertAlmostEqual(cy, 0.0, places=5)

    def test_access_certificate_relocates_one_movable_blocked_ray_owner(self):
        candidate = SimpleNamespace(P={
            "REG": (0.0, 0.0, 0.0),
            "BYP": (2.0, 0.0, 0.0),
            "C_NEIGHBOR": (-1.0, 0.7, 90.0),
        })
        evidence = {
            "decoupler": {"details": [{
                "actionable": True, "status": "assigned",
                "cap_ref": "BYP", "owner_ref": "REG", "rail": "+V",
                "owner_position_mm": [0.0, 0.0],
                "owner_supply_position_mm": [0.0, 0.0],
                "owner_ground_position_mm": [0.0, 1.0],
                "owner_ground_positions_mm": [
                    {"pin": "G", "position": [0.0, 1.0]}],
                "cap_position_mm": [2.0, 0.0],
                "cap_supply_position_mm": [1.5, 0.0],
                "cap_ground_position_mm": [2.5, 0.0],
                "supply_access_certificate": {"layers": [{
                    "endpoint_escape": [{
                        "endpoint": "a", "clear_rays": [],
                        "ray_details": [{
                            "direction": "W",
                            "status": "foreign_copper_blocked",
                            "blockers": [{
                                "kind": "pad", "ref": "C_NEIGHBOR",
                                "pad": "1", "net": "/OTHER",
                            }, {
                                "kind": "track", "net": "/OTHER",
                                "locked": True, "uuid": "generated-cell",
                            }],
                        }],
                    }],
                }]},
            }]},
            "pair_launch": {"violations": []},
            "stranded": {"details": []},
        }
        relocated = {
            "BYP": (-1.35, 0.0, 180.0),
            "C_NEIGHBOR": (-1.0, 1.8, 90.0),
        }
        with mock.patch.object(
                synth, "_placement_tangent_relocation_variants",
                return_value=[(relocated, "below")]) as tangent:
            moves = synth._placement_craft_move_specs(
                candidate, evidence, comps={"C_NEIGHBOR": object()})
        move = moves[0]
        self.assertEqual(move["kind"], "decoupler_access_escape")
        self.assertEqual(move["certificate_direction"], "W")
        self.assertEqual(move["access_blocker_ref"], "C_NEIGHBOR")
        self.assertEqual(move["placements"], relocated)
        tangent.assert_called()

        unsafe = copy.deepcopy(evidence)
        unsafe["decoupler"]["details"][0][
            "supply_access_certificate"]["layers"][0][
                "endpoint_escape"][0]["ray_details"][0][
                    "blockers"][1]["locked"] = False
        unsafe_moves = synth._placement_craft_move_specs(
            candidate, unsafe, comps={"C_NEIGHBOR": object()})
        self.assertFalse(any(
            row.get("kind") == "decoupler_access_escape"
            for row in unsafe_moves))

        owned = copy.deepcopy(evidence)
        owned["decoupler"]["details"].append({
            "actionable": False, "status": "assigned",
            "cap_ref": "C_NEIGHBOR", "owner_ref": "REG",
            "cap_position_mm": [-1.0, 0.7],
            "cap_supply_position_mm": [-1.0, 1.475],
        })
        with mock.patch.object(
                synth, "_placement_tangent_relocation_variants",
                return_value=[]):
            pivot_moves = synth._placement_craft_move_specs(
                candidate, owned, comps={"C_NEIGHBOR": object()})
        pivot = next(row for row in pivot_moves
                     if row.get("access_blocker_relocation")
                     == "rail_pivot_270.0")
        self.assertEqual(pivot["placements"]["BYP"][2], 180.0)
        self.assertEqual(pivot["placements"]["C_NEIGHBOR"][2], 270.0)
        # The blocker rail land stays fixed while its body/return flip sides.
        self.assertAlmostEqual(
            pivot["placements"]["C_NEIGHBOR"][1], 2.25, places=5)

    def test_decoupler_repair_solves_supply_and_ground_pads_together(self):
        candidate = SimpleNamespace(P={
            "U1": (10.0, 10.0, 0.0),
            "C1": (20.0, 20.0, 0.0),
        })
        evidence = {
            "decoupler": {"details": [{
                "actionable": True,
                "cap_ref": "C1", "owner_ref": "U1",
                "owner_position_mm": [10.0, 10.0],
                "owner_supply_position_mm": [12.0, 10.0],
                "owner_ground_position_mm": [14.0, 10.0],
                "owner_ground_positions_mm": [
                    {"pin": "2", "position": [14.0, 10.0]}],
                "cap_position_mm": [20.0, 20.0],
                "cap_supply_position_mm": [20.5, 20.0],
                "cap_ground_position_mm": [19.5, 20.0],
            }]},
            "stranded": {"details": []},
        }
        moves = synth._placement_craft_move_specs(candidate, evidence)
        balanced = next(move for move in moves
                        if move["kind"] == "decoupler_loop_balance")
        # With the capacitor rotated 180 degrees, its pad vector points from
        # the supply toward the owner's real GND pin.  The bisector seat leaves
        # only 0.5 mm at each end instead of optimizing one end in isolation.
        self.assertAlmostEqual(balanced["predicted_supply_mm"], 0.5,
                               places=4)
        self.assertAlmostEqual(balanced["predicted_ground_mm"], 0.5,
                               places=4)
        self.assertEqual(balanced["owner_ground_pin"], "2")

    def test_clean_margin_search_is_generic_and_explicitly_bounded(self):
        candidate = SimpleNamespace(P={
            "REG_A": (10.0, 10.0, 0.0),
            "BYP_A": (13.0, 10.0, 180.0),
            "REG_B": (40.0, 40.0, 0.0),
            "BYP_B": (40.5, 40.0, 0.0),
        })
        evidence = {
            "pair_launch": {"violations": []},
            "decoupler": {"details": [
                {
                    "actionable": False, "status": "assigned",
                    "cap_ref": "BYP_A", "owner_ref": "REG_A",
                    "rail": "+V_A", "loop_proxy_mm": 5.8,
                    "owner_position_mm": [10.0, 10.0],
                    "owner_supply_position_mm": [11.0, 10.0],
                    "owner_ground_position_mm": [11.0, 11.0],
                    "owner_ground_positions_mm": [
                        {"pin": "G", "position": [11.0, 11.0]}],
                    "cap_position_mm": [13.0, 10.0],
                    "cap_supply_position_mm": [13.5, 10.0],
                    "cap_ground_position_mm": [12.5, 10.0],
                },
                {
                    "actionable": False, "status": "assigned",
                    "cap_ref": "BYP_B", "owner_ref": "REG_B",
                    "rail": "+V_B", "loop_proxy_mm": 1.0,
                    "owner_position_mm": [40.0, 40.0],
                    "owner_supply_position_mm": [40.0, 40.0],
                    "owner_ground_position_mm": [41.0, 40.0],
                    "owner_ground_positions_mm": [
                        {"pin": "G", "position": [41.0, 40.0]}],
                    "cap_position_mm": [40.5, 40.0],
                    "cap_supply_position_mm": [40.0, 40.0],
                    "cap_ground_position_mm": [41.0, 40.0],
                },
            ]},
            "stranded": {"details": []},
        }
        self.assertEqual(
            synth._placement_craft_move_specs(candidate, evidence), [])
        moves = synth._placement_craft_move_specs(
            candidate, evidence, optimize_clean_margin=True,
            clean_margin_max_cells=1)
        self.assertTrue(moves)
        self.assertTrue(all(move["ref"] == "BYP_A" for move in moves))
        self.assertEqual(moves[0]["kind"], "decoupler_local_margin")
        self.assertTrue(moves[0]["margin_optimization"])

    def test_active_blocker_suppresses_clean_margin_polish(self):
        candidate = SimpleNamespace(P={
            "REG_BAD": (10.0, 10.0, 0.0),
            "BYP_BAD": (13.0, 10.0, 0.0),
            "REG_GOOD": (30.0, 30.0, 0.0),
            "BYP_GOOD": (33.0, 30.0, 0.0),
        })

        def row(owner, cap, actionable, loop):
            return {
                "actionable": actionable, "status": "assigned",
                "cap_ref": cap, "owner_ref": owner, "rail": "+V",
                "loop_proxy_mm": loop,
                "owner_position_mm": list(candidate.P[owner][:2]),
                "owner_supply_position_mm": [candidate.P[owner][0] + 1.0,
                                             candidate.P[owner][1]],
                "owner_ground_position_mm": [candidate.P[owner][0] + 1.0,
                                             candidate.P[owner][1] + 1.0],
                "owner_ground_positions_mm": [{
                    "pin": "G", "position": [candidate.P[owner][0] + 1.0,
                                               candidate.P[owner][1] + 1.0]}],
                "cap_position_mm": list(candidate.P[cap][:2]),
                "cap_supply_position_mm": [candidate.P[cap][0] + 0.5,
                                           candidate.P[cap][1]],
                "cap_ground_position_mm": [candidate.P[cap][0] - 0.5,
                                           candidate.P[cap][1]],
            }

        evidence = {
            "pair_launch": {"violations": []},
            "decoupler": {"details": [
                row("REG_BAD", "BYP_BAD", True, 5.0),
                row("REG_GOOD", "BYP_GOOD", False, 6.0),
            ]},
            "stranded": {"details": []},
        }
        moves = synth._placement_craft_move_specs(
            candidate, evidence, optimize_clean_margin=True,
            clean_margin_max_cells=3)
        self.assertTrue(moves)
        self.assertFalse(any(move.get("ref") == "BYP_GOOD"
                             for move in moves))

    def test_stage_dispatch_filters_unrelated_move_families(self):
        candidate = SimpleNamespace(P={
            "PAIR_BLOCK": (5.0, 5.0, 0.0),
            "LONELY": (20.0, 20.0, 0.0),
            "NEAR": (22.0, 20.0, 0.0),
        })
        evidence = {
            "pair_launch": {"violations": [{
                "blocker_ref": "PAIR_BLOCK", "station_ref": "PORT",
                "pair": "DATA", "leg": 1, "perpendicular": [1.0, 0.0],
                "suggested_side": 1.0, "minimum_shift_mm": 0.5,
            }]},
            "decoupler": {"details": []},
            "stranded": {"details": [{
                "ref": "LONELY", "nearest_ref": "NEAR"}]},
        }
        locality = synth._placement_craft_move_specs(
            candidate, evidence, required_stages=["component_locality"])
        self.assertTrue(locality)
        self.assertEqual({move["kind"] for move in locality},
                         {"stranded_rejoin"})
        pair = synth._placement_craft_move_specs(
            candidate, evidence, required_stages=["critical_pair_launch"])
        self.assertTrue(pair)
        self.assertEqual({move["kind"] for move in pair},
                         {"pair_launch_reseat"})

    def test_power_territory_reseat_preserves_assigned_local_cell(self):
        candidate = SimpleNamespace(P={
            "REG": (10.0, 10.0, 0.0),
            "BYP": (12.0, 10.0, 90.0),
        })
        evidence = {
            "pour_territory": {"violations": [{
                "ref": "REG", "net": "+VIN", "overlap_mm2": 4.0,
                "regions": [{
                    "index": 2, "box": [8.0, 8.0, 14.0, 14.0],
                    "overlap_mm2": 4.0,
                }],
            }]},
            "pair_launch": {"violations": []},
            "critical_terminal_order": {"violations": []},
            "decoupler": {"details": [{
                "owner_ref": "REG", "cap_ref": "BYP",
                "status": "assigned", "actionable": False,
            }]},
            "stranded": {"details": []},
        }
        with mock.patch(
                "cec_pcb.courtyard_bbox",
                return_value=(9.0, 11.0, 9.0, 11.0)):
            moves = synth._placement_craft_move_specs(
                candidate, evidence,
                comps={"REG": "Regulator", "BYP": "Capacitor"},
                required_stages=["power_territory_placement"])
        cell = next(move for move in moves
                    if move["kind"] == "power_territory_cell_reseat")
        self.assertEqual(set(cell["placements"]), {"REG", "BYP"})
        reg_dx = cell["placements"]["REG"][0] - candidate.P["REG"][0]
        cap_dx = cell["placements"]["BYP"][0] - candidate.P["BYP"][0]
        reg_dy = cell["placements"]["REG"][1] - candidate.P["REG"][1]
        cap_dy = cell["placements"]["BYP"][1] - candidate.P["BYP"][1]
        self.assertAlmostEqual(reg_dx, cap_dx)
        self.assertAlmostEqual(reg_dy, cap_dy)

    def test_power_territory_grid_searches_beyond_blocked_axis_exit(self):
        candidate = SimpleNamespace(
            P={"REG": (10.0, 10.0, 0.0),
               "BYP": (12.0, 10.0, 90.0)},
            W=40.0, H=30.0, back_refs=set())
        evidence = {
            "power_body_clearance": {
                "reserved_regions": [{
                    "net": "+VIN", "layer": "F.Cu",
                    "box": [8.0, 8.0, 14.0, 14.0],
                }, {
                    "net": "+ALT", "layer": "F.Cu",
                    "box": [14.0, 8.0, 18.0, 14.0],
                }],
                "violations": [{
                    "ref": "REG", "net": "+VIN", "layer": "F.Cu",
                    "component_nets": ["+3V3", "GND"],
                    "conflict_bbox": [9.0, 11.0, 9.0, 11.0],
                    "overlap_mm2": 4.0,
                    "regions": [{
                        "index": 0, "layer": "F.Cu",
                        "box": [8.0, 8.0, 14.0, 14.0],
                        "overlap_mm2": 4.0,
                    }],
                }],
            },
            "decoupler": {"details": [{
                "owner_ref": "REG", "cap_ref": "BYP",
                "status": "assigned", "actionable": False,
            }]},
            "pair_launch": {"violations": []},
            "critical_terminal_order": {"violations": []},
            "stranded": {"details": []},
        }

        def courtyard(_component, x, y, _rotation, **_kwargs):
            return (x - 1.0, x + 1.0, y - 1.0, y + 1.0)

        with mock.patch("cec_pcb.courtyard_bbox",
                        side_effect=courtyard), mock.patch.object(
                            synth, "_overlap_pairs", return_value=set()):
            moves = synth._placement_craft_move_specs(
                candidate, evidence,
                comps={"REG": "Regulator", "BYP": "Capacitor"},
                required_stages=["power_territory_placement"])
        grid = [move for move in moves if move["kind"] ==
                "power_territory_cell_clearance_grid"]
        self.assertTrue(grid)
        first = grid[0]
        self.assertEqual(set(first["placements"]), {"REG", "BYP"})
        # The complete cell is outside the measured corridor; the bypass
        # vector remains rigid under both translation and any rotation.
        for position in first["placements"].values():
            box = courtyard(None, *position)
            self.assertFalse(box[0] < 14.0 and box[1] > 8.0
                             and box[2] < 14.0 and box[3] > 8.0)
            self.assertFalse(box[0] < 18.0 and box[1] > 14.0
                             and box[2] < 14.0 and box[3] > 8.0)
        reg = first["placements"]["REG"]
        cap = first["placements"]["BYP"]
        self.assertAlmostEqual(math.hypot(cap[0] - reg[0],
                                         cap[1] - reg[1]), 2.0)

    def test_power_via_field_certificate_moves_named_neighbor_cell(self):
        candidate = SimpleNamespace(P={
            "U_NEAR": (12.0, 10.0, 0.0),
            "C_NEAR": (13.0, 10.0, 90.0),
            "RS_TERM": (10.0, 10.0, 0.0),
        })
        evidence = {
            "power_body_clearance": {
                "error": "exact territory unroutable",
                "planner_failures": {"/RAIL_LO": {
                    "planner_bottleneck": {
                        "kind": "via_field_access",
                        "fields": [{
                            "field_index": 1,
                            "centre_mm": [10.0, 10.0],
                            "terminal_refs": ["RS_TERM"],
                            "nearest_pad_obstacles": [{
                                "owner": "RS_TERM", "distance_mm": 0.0,
                                "fixed": False,
                            }, {
                                "owner": "U_NEAR", "distance_mm": 1.0,
                                "fixed": False,
                            }],
                        }],
                    },
                }},
            },
            "decoupler": {"details": [{
                "owner_ref": "U_NEAR", "cap_ref": "C_NEAR",
                "status": "assigned", "actionable": False,
            }]},
            "pair_launch": {"violations": []},
            "critical_terminal_order": {"violations": []},
            "stranded": {"details": []},
        }
        moves = synth._placement_craft_move_specs(
            candidate, evidence,
            comps={ref: object() for ref in candidate.P},
            required_stages=["power_via_field_access"])
        self.assertIn(
            "power_via_field_access",
            synth.placement_craft_blocker_certificate(
                evidence)["required_stages"])
        via_moves = [move for move in moves
                     if move["kind"] ==
                     "power_via_field_access_cell_reseat"]
        self.assertTrue(via_moves)
        self.assertEqual({move["ref"] for move in via_moves}, {"U_NEAR"})
        self.assertEqual(
            {move["distance_mm"] for move in via_moves[:5]},
            {1.0, 2.0, 3.5, 5.0, 7.0})
        first = via_moves[0]
        self.assertEqual(set(first["placements"]), {"U_NEAR", "C_NEAR"})
        owner_dx = (first["placements"]["U_NEAR"][0]
                    - candidate.P["U_NEAR"][0])
        cap_dx = (first["placements"]["C_NEAR"][0]
                  - candidate.P["C_NEAR"][0])
        owner_dy = (first["placements"]["U_NEAR"][1]
                    - candidate.P["U_NEAR"][1])
        cap_dy = (first["placements"]["C_NEAR"][1]
                  - candidate.P["C_NEAR"][1])
        self.assertAlmostEqual(owner_dx, cap_dx)
        self.assertAlmostEqual(owner_dy, cap_dy)

    def test_power_corridor_relief_moves_complete_owned_cell_off_path(self):
        candidate = SimpleNamespace(P={
            "U_REG": (10.0, 10.0, 0.0),
            "C_BLOCK": (11.0, 10.0, 90.0),
            "J_FIXED": (2.0, 10.0, 0.0),
        })
        evidence = {
            "power_body_clearance": {
                "error": "exact territory unroutable",
                "planner_failures": {"/RAIL_HI": {
                    "planner_bottleneck": {
                        "kind": "corridor_access",
                        "relief": {"B.Cu:1->2": {
                            "relief_sets": [{
                                "owners": ["C_BLOCK"],
                                "path_mm": [[0.0, 10.0], [20.0, 10.0]],
                            }],
                        }},
                    },
                }},
            },
            "decoupler": {"details": [{
                "owner_ref": "U_REG", "cap_ref": "C_BLOCK",
                "status": "assigned", "actionable": False,
            }]},
            "pair_launch": {"violations": []},
            "critical_terminal_order": {"violations": []},
            "stranded": {"details": []},
        }

        moves = synth._placement_craft_move_specs(
            candidate, evidence,
            comps={ref: object() for ref in candidate.P},
            required_stages=["power_corridor_access"])

        self.assertIn(
            "power_corridor_access",
            synth.placement_craft_blocker_certificate(
                evidence)["required_stages"])
        corridor_moves = [move for move in moves if move["kind"] ==
                          "power_corridor_relief_cell_reseat"]
        self.assertTrue(corridor_moves)
        self.assertEqual(
            {move["escape_basis"] for move in corridor_moves},
            {"normal", "tangent", "diagonal"})
        first = corridor_moves[0]
        self.assertEqual(first["relief_owner"], "C_BLOCK")
        self.assertEqual(set(first["placements"]), {"U_REG", "C_BLOCK"})
        for axis in (0, 1):
            self.assertAlmostEqual(
                first["placements"]["U_REG"][axis]
                - candidate.P["U_REG"][axis],
                first["placements"]["C_BLOCK"][axis]
                - candidate.P["C_BLOCK"][axis])

    def test_power_corridor_relief_uses_exact_complete_cell_envelope(self):
        candidate = SimpleNamespace(P={
            "U_REG": (10.0, 10.0, 0.0),
            "C_BLOCK": (11.0, 10.0, 90.0),
        })
        evidence = {
            "power_body_clearance": {
                "planner_failures": {"/RAIL": {
                    "planner_bottleneck": {"relief": {"F.Cu:1->2": {
                        "required_width_mm": 6.0,
                        "relief_sets": [{
                            "owners": ["U_REG", "C_BLOCK"],
                            "owner_bounds_mm": {
                                "U_REG": [9.0, 8.0, 11.0, 12.0],
                                "C_BLOCK": [10.5, 9.0, 11.5, 11.0],
                            },
                            "path_mm": [[0.0, 10.0], [20.0, 10.0]],
                        }],
                    }}},
                }},
            },
            "decoupler": {"details": [{
                "owner_ref": "U_REG", "cap_ref": "C_BLOCK",
                "status": "assigned",
            }]},
            "pair_launch": {"violations": []},
            "critical_terminal_order": {"violations": []},
            "stranded": {"details": []},
        }

        moves = synth._placement_craft_move_specs(
            candidate, evidence,
            comps={ref: object() for ref in candidate.P},
            required_stages=["power_corridor_access"],
            policy_params={"power_corridor_placement_max_mm": 8.0})
        envelope = [move for move in moves if move["kind"] ==
                    "power_corridor_relief_envelope_reseat"]

        self.assertTrue(envelope)
        self.assertTrue(all(set(move["placements"]) ==
                            {"U_REG", "C_BLOCK"} for move in envelope))
        self.assertTrue(all(move["escape_basis"] == "exact_envelope"
                            for move in envelope))
        self.assertIn((0.0, -5.1), {
            tuple(round(value, 1) for value in move["translation_mm"])
            for move in envelope})

    def test_power_corridor_corner_can_escape_along_path_tangent(self):
        candidate = SimpleNamespace(P={
            "U_BLOCK": (9.95, 8.0, 0.0),
            "C_BLOCK": (8.95, 8.0, 90.0),
        })
        evidence = {
            "power_body_clearance": {
                "planner_failures": {"/RAIL": {
                    "planner_bottleneck": {"relief": {"F.Cu:1->2": {
                        "relief_sets": [{
                            "owners": ["U_BLOCK"],
                            # U_BLOCK is closest to the corner.  Moving only
                            # on the horizontal segment normal can land it in
                            # the vertical leg; the tangent is a required
                            # independent repair degree of freedom.
                            "path_mm": [
                                [10.0, 0.0], [10.0, 5.0], [20.0, 5.0]],
                        }],
                    }}},
                }},
            },
            "decoupler": {"details": [{
                "owner_ref": "U_BLOCK", "cap_ref": "C_BLOCK",
                "status": "assigned",
            }]},
            "pair_launch": {"violations": []},
            "critical_terminal_order": {"violations": []},
            "stranded": {"details": []},
        }

        moves = synth._placement_craft_move_specs(
            candidate, evidence,
            comps={ref: object() for ref in candidate.P},
            required_stages=["power_corridor_access"])
        tangent = [move for move in moves
                   if move.get("escape_basis") == "tangent"]

        self.assertTrue(tangent)
        self.assertTrue(all(
            abs(move["translation_mm"][0])
            > abs(move["translation_mm"][1])
            for move in tangent))
        self.assertEqual({round(math.hypot(*move["translation_mm"]), 6)
                          for move in tangent},
                         {1.0, 2.0, 3.5, 5.0, 7.0})
        diagonal = [move for move in moves
                    if move.get("escape_basis") == "diagonal"]
        self.assertTrue(diagonal)
        self.assertTrue(all(
            abs(component) > 1e-6
            for move in diagonal
            for component in move["translation_mm"]))
        self.assertEqual(
            {tuple(sorted(abs(value) for value in
                          move["escape_components_mm"]))
             for move in diagonal},
            {(2.0, 2.0), (3.5, 3.5), (5.0, 5.0),
             (7.0, 7.0), (3.5, 7.0)})

    def test_bounded_macro_legalizer_reseats_complete_neighbor_cells(self):
        candidate = SimpleNamespace(
            P={
                "U_MOVE": (0.0, 0.0, 0.0),
                "C_MOVE": (0.0, 1.0, 0.0),
                "U_NEAR": (5.0, 0.0, 0.0),
                "C_NEAR": (5.0, 1.0, 0.0),
                "R_NEAR": (5.0, -1.0, 0.0),
            },
            W=20.0, H=20.0, back_refs=())
        placements = {
            "U_MOVE": (5.0, 0.0, 0.0),
            "C_MOVE": (5.0, 1.0, 0.0),
        }

        def bbox(_component, x, y, _rotation, **_kwargs):
            return (x - 0.4, x + 0.4, y - 0.4, y + 0.4)

        def overlaps(positions, _comps, **_kwargs):
            pairs = set()
            refs = sorted(positions)
            for index, left in enumerate(refs):
                left_box = bbox(None, *positions[left])
                for right in refs[index + 1:]:
                    right_box = bbox(None, *positions[right])
                    if not (left_box[1] <= right_box[0]
                            or right_box[1] <= left_box[0]
                            or left_box[3] <= right_box[2]
                            or right_box[3] <= left_box[2]):
                        pairs.add((left, right))
            return pairs

        with mock.patch.object(synth, "_overlap_pairs",
                               side_effect=overlaps):
            variants = synth._placement_bounded_macro_legalizations(
                candidate, placements, set(),
                {ref: object() for ref in candidate.P},
                {"C_MOVE": "U_MOVE", "C_NEAR": "U_NEAR"},
                {"U_MOVE": {"C_MOVE"}, "U_NEAR": {"C_NEAR"}},
                lambda ref: ref != "U_MOVE",
                bbox_fn=lambda ref, position: bbox(None, *position))

        self.assertTrue(variants)
        legalized, roots, tag = variants[0]
        self.assertEqual(tag, "macro_window")
        self.assertIn("U_NEAR", roots)
        self.assertEqual(
            legalized["C_NEAR"][0] - legalized["U_NEAR"][0], 0.0)
        self.assertAlmostEqual(
            legalized["C_NEAR"][1] - legalized["U_NEAR"][1], 1.0)

    def test_macro_legalizer_preserves_existing_edge_body_overhang(self):
        candidate = SimpleNamespace(
            P={"PRIMARY": (9.0, 7.0, 0.0),
               "J_EDGE": (9.5, 4.0, 0.0)},
            W=10.0, H=10.0, back_refs=())
        placements = {"PRIMARY": (9.0, 5.0, 0.0)}

        def bbox(ref, position):
            x, y, _rotation = position
            if ref == "J_EDGE":
                return (x - 1.0, x + 1.0, y - 1.0, y + 1.0)
            return (x - 0.5, x + 0.5, y - 0.5, y + 0.5)

        baseline = synth._placement_bbox_overlap_pairs(
            candidate.P, bbox)
        strict = synth._placement_bounded_macro_legalizations(
            candidate, placements, baseline,
            {ref: object() for ref in candidate.P}, {}, {},
            lambda ref: ref == "J_EDGE", bbox_fn=bbox,
            exact_bbox_overlap=True)
        preserved = synth._placement_bounded_macro_legalizations(
            candidate, placements, baseline,
            {ref: object() for ref in candidate.P}, {}, {},
            lambda ref: ref == "J_EDGE", bbox_fn=bbox,
            exact_bbox_overlap=True, preserve_existing_overhang=True)

        self.assertTrue(strict)
        strict_legalized, _strict_roots, _strict_tag = strict[0]
        self.assertLess(strict_legalized["J_EDGE"][0], 9.5)
        self.assertTrue(preserved)
        legalized, roots, _tag = preserved[0]
        self.assertEqual(roots, ["J_EDGE"])
        self.assertLess(legalized["J_EDGE"][1], 4.0)
        self.assertEqual(legalized["J_EDGE"][0], 9.5)

    def test_macro_tangent_uses_colliding_member_not_remote_follower(self):
        candidate = SimpleNamespace(
            P={
                "U_MOVE": (2.0, 5.0, 0.0),
                "U_NEAR": (5.0, 5.0, 0.0),
                "R_REMOTE": (20.0, 5.0, 0.0),
            },
            W=30.0, H=12.0, back_refs=())
        placements = {"U_MOVE": (5.0, 5.0, 0.0)}

        def bbox(_component, x, y, _rotation, **_kwargs):
            return (x - 0.4, x + 0.4, y - 0.4, y + 0.4)

        def overlaps(positions, _comps, **_kwargs):
            pairs = set()
            refs = sorted(positions)
            for index, left in enumerate(refs):
                left_box = bbox(None, *positions[left])
                for right in refs[index + 1:]:
                    right_box = bbox(None, *positions[right])
                    if not (left_box[1] <= right_box[0]
                            or right_box[1] <= left_box[0]
                            or left_box[3] <= right_box[2]
                            or right_box[3] <= left_box[2]):
                        pairs.add((left, right))
            return pairs

        with mock.patch.object(synth, "_overlap_pairs",
                               side_effect=overlaps):
            variants = synth._placement_bounded_macro_legalizations(
                candidate, placements, set(),
                {ref: object() for ref in candidate.P},
                {"R_REMOTE": "U_NEAR"},
                {"U_NEAR": {"R_REMOTE"}},
                lambda ref: ref == "U_NEAR",
                bbox_fn=lambda ref, position: bbox(None, *position))

        self.assertTrue(variants)
        legalized, roots, _tag = variants[0]
        shift = legalized["U_NEAR"][0] - candidate.P["U_NEAR"][0]
        self.assertLess(abs(shift), 2.0)
        self.assertAlmostEqual(
            legalized["R_REMOTE"][0] - candidate.P["R_REMOTE"][0], shift)
        self.assertEqual(roots, ["U_NEAR"])

    def test_bounded_macro_legalizer_reseats_cell_out_of_reserved_copper(self):
        candidate = SimpleNamespace(
            P={"U_MOVE": (2.0, 5.0, 0.0),
               "C_MOVE": (2.0, 6.0, 0.0)},
            W=12.0, H=12.0, back_refs=())
        placements = {
            "U_MOVE": (5.0, 5.0, 0.0),
            "C_MOVE": (5.0, 6.0, 0.0),
        }
        regions = [{"net": "/RAIL", "layer": "F.Cu",
                    "box": [4.5, 4.5, 5.5, 5.5]}]

        def bbox(_ref, position):
            x, y, _rotation = position
            return (x - 0.4, x + 0.4, y - 0.4, y + 0.4)

        with mock.patch.object(synth, "_overlap_pairs", return_value=set()):
            variants = synth._placement_bounded_macro_legalizations(
                candidate, placements, set(),
                {ref: object() for ref in candidate.P},
                {"C_MOVE": "U_MOVE"}, {"U_MOVE": {"C_MOVE"}},
                lambda _ref: True, bbox_fn=bbox,
                reserved_regions=regions,
                nets_by_ref={"U_MOVE": {"/SIG"}, "C_MOVE": {"GND"}},
                reserved_clearance_mm=0.1)

        self.assertTrue(variants)
        legalized, roots, tag = variants[0]
        self.assertEqual(tag, "macro_window")
        self.assertIn("U_MOVE", roots)
        self.assertAlmostEqual(
            legalized["C_MOVE"][0] - legalized["U_MOVE"][0], 0.0)
        self.assertAlmostEqual(
            legalized["C_MOVE"][1] - legalized["U_MOVE"][1], 1.0)
        self.assertEqual(synth._placement_reserved_copper_collisions(
            candidate, legalized,
            {ref: object() for ref in candidate.P}, regions,
            {"U_MOVE": {"/SIG"}, "C_MOVE": {"GND"}},
            clearance_mm=0.1, bbox_fn=bbox), [])

    def test_reserved_copper_collision_exempts_owning_net(self):
        candidate = SimpleNamespace(
            P={"C_RAIL": (5.0, 5.0, 0.0)}, back_refs=())
        regions = [{"net": "/RAIL", "layer": "F.Cu",
                    "box": [4.5, 4.5, 5.5, 5.5]}]

        def bbox(_ref, position):
            x, y, _rotation = position
            return (x - 0.4, x + 0.4, y - 0.4, y + 0.4)

        collisions = synth._placement_reserved_copper_collisions(
            candidate, {"C_RAIL": candidate.P["C_RAIL"]},
            {"C_RAIL": object()}, regions,
            {"C_RAIL": {"/RAIL", "GND"}}, bbox_fn=bbox)

        self.assertEqual(collisions, [])

    def test_power_corridor_minimum_cut_moves_all_blocking_cells(self):
        candidate = SimpleNamespace(P={
            "U1": (8.0, 9.0, 0.0), "C1": (9.0, 9.0, 0.0),
            "U2": (12.0, 11.0, 0.0), "C2": (13.0, 11.0, 0.0),
        })
        evidence = {
            "power_body_clearance": {
                "planner_failures": {"/RAIL": {
                    "planner_bottleneck": {"relief": {"F.Cu:1->2": {
                        "relief_sets": [{
                            "owners": ["C1", "U2"],
                            "path_mm": [[0.0, 10.0], [20.0, 10.0]],
                        }],
                    }}},
                }},
            },
            "decoupler": {"details": [{
                "owner_ref": "U1", "cap_ref": "C1",
                "status": "assigned",
            }, {
                "owner_ref": "U2", "cap_ref": "C2",
                "status": "assigned",
            }]},
            "pair_launch": {"violations": []},
            "critical_terminal_order": {"violations": []},
            "stranded": {"details": []},
        }

        moves = synth._placement_craft_move_specs(
            candidate, evidence,
            comps={ref: object() for ref in candidate.P},
            required_stages=["power_corridor_access"])
        joint = [move for move in moves if move["kind"] ==
                 "power_corridor_relief_joint_cell_reseat"]

        self.assertTrue(joint)
        self.assertEqual(set(joint[0]["cell_roots"]), {"U1", "U2"})
        self.assertEqual(set(joint[0]["placements"]),
                         {"U1", "C1", "U2", "C2"})
        self.assertEqual(set(joint[0]["relief_owners"]), {"C1", "U2"})

    def test_power_corridor_wide_cut_collapses_copper_owners_to_cells(self):
        candidate = SimpleNamespace(P={
            "U1": (8.0, 9.0, 0.0),
            "C1": (8.5, 9.0, 0.0),
            "C2": (8.0, 9.5, 0.0),
            "C3": (7.5, 9.0, 0.0),
            "R1": (12.0, 11.0, 0.0),
            "R2": (14.0, 11.0, 0.0),
        })
        evidence = {
            "power_body_clearance": {
                "planner_failures": {"/RAIL": {
                    "planner_bottleneck": {"relief": {"F.Cu:1->2": {
                        "relief_sets": [],
                        "wide_relief_sets": [{
                            "owners": ["U1", "C1", "C2", "C3",
                                       "R1", "R2"],
                            "path_mm": [[0.0, 10.0], [20.0, 10.0]],
                            "search": "all_movable_greedy",
                        }],
                    }}},
                }},
            },
            "decoupler": {"details": [{
                "owner_ref": "U1", "cap_ref": cap,
                "status": "assigned",
            } for cap in ("C1", "C2", "C3")]},
            "pair_launch": {"violations": []},
            "critical_terminal_order": {"violations": []},
            "stranded": {"details": []},
        }

        moves = synth._placement_craft_move_specs(
            candidate, evidence,
            comps={ref: object() for ref in candidate.P},
            required_stages=["power_corridor_access"])
        joint = [move for move in moves if move["kind"] ==
                 "power_corridor_relief_joint_cell_reseat"]

        self.assertTrue(joint)
        self.assertEqual(set(joint[0]["cell_roots"]), {"U1", "R1", "R2"})
        self.assertEqual(set(joint[0]["placements"]), set(candidate.P))
        self.assertEqual(joint[0]["relief_search_scope"], "wide")

    def test_joint_envelope_pack_uses_independent_cell_tangencies(self):
        candidate = SimpleNamespace(P={
            "U1": (16.0, 14.0, 0.0), "C1": (15.0, 13.0, 0.0),
            "R1": (15.0, 10.0, 0.0), "R2": (19.5, 16.0, 0.0),
        })
        cut = {
            "owners": ["U1", "C1", "R1", "R2"],
            "owner_bounds_mm": {
                "U1": [14.8, 12.7, 18.0, 16.3],
                "C1": [14.1, 10.7, 18.3, 14.7],
                "R1": [14.3, 8.8, 16.0, 11.4],
                "R2": [18.8, 15.1, 20.5, 17.7],
            },
            "path_mm": [
                [30.9, 3.3], [19.0, 3.3], [19.0, 14.1],
                [27.8, 14.1], [27.8, 20.5],
            ],
        }

        specs = synth._placement_relief_joint_envelope_specs(
            candidate, cut, 6.3, {"C1": "U1"}, {"U1": {"C1"}},
            comps=None, max_mm=8.0)

        self.assertTrue(specs)
        first = specs[0]
        self.assertEqual(set(first["translations_mm"]),
                         {"U1", "R1", "R2"})
        self.assertGreater(len({tuple(value) for value in
                                first["translations_mm"].values()}), 1)

    def test_joint_envelope_two_root_search_retains_farther_pockets(self):
        candidate = SimpleNamespace(P={
            "U1": (10.0, 10.0, 0.0), "U2": (20.0, 10.0, 0.0),
        })
        cut = {
            "owners": ["U1", "U2"],
            "owner_bounds_mm": {
                "U1": [8.0, 8.0, 12.0, 12.0],
                "U2": [18.0, 8.0, 22.0, 12.0],
            },
            "path_mm": [
                [0.0, 10.0], [30.0, 10.0], [30.0, 20.0],
                [0.0, 20.0],
            ],
        }

        specs = synth._placement_relief_joint_envelope_specs(
            candidate, cut, 4.0, {}, {}, comps=None,
            max_mm=8.0, max_specs=256)

        self.assertTrue(specs)
        # The cardinality-aware two-root beam must expose more than the old
        # eight-result neighborhood when exact bounds permit it.
        self.assertGreater(len(specs), 8)

    def test_joint_envelope_pack_avoids_already_closed_corridor(self):
        candidate = SimpleNamespace(P={
            "U1": (10.0, 10.0, 0.0), "U2": (20.0, 10.0, 0.0),
        }, back_refs=())
        cut = {
            "owners": ["U1", "U2"],
            "owner_bounds_mm": {
                "U1": [9.0, 9.0, 11.0, 11.0],
                "U2": [19.0, 9.0, 21.0, 11.0],
            },
            "path_mm": [[0.0, 10.0], [30.0, 10.0]],
        }
        protected = [{"net": "/OTHER", "layer": "F.Cu",
                      "box": [0.0, 0.0, 30.0, 7.5]}]

        specs = synth._placement_relief_joint_envelope_specs(
            candidate, cut, 4.0, {}, {}, comps=None,
            protected_regions=protected, max_specs=64)

        self.assertTrue(specs)
        self.assertTrue(all(
            all(9.0 + move[1] >= 7.5 for move in
                spec["translations_mm"].values())
            for spec in specs))

    def test_atomic_multirail_transition_uses_new_exact_failure(self):
        baseline = {"power_body_clearance": {
            "planner_failures": {"/C2_HI": {}},
            "successful_nets": ["/C1_HI", "/C1_LO", "/C2_LO"],
        }}
        trial = {"power_body_clearance": {
            "planner_failures": {
                "/C1_HI": {"planner_bottleneck": {
                    "kind": "via_field_access"}},
                "/C2_HI": {"planner_bottleneck": {
                    "kind": "reserved_copper_no_path"}},
            },
        }}

        transition = synth._placement_atomic_multirail_transition(
            baseline, trial, {"kind":
                              "power_corridor_relief_joint_envelope_pack"})

        self.assertEqual(transition["baseline_failed_nets"], ["/C2_HI"])
        self.assertEqual(transition["newly_failed_nets"], ["/C1_HI"])
        self.assertEqual(transition["original_failures_cleared"], [])

    def test_atomic_multirail_transition_rejects_unrelated_or_known_failure(self):
        baseline = {"power_body_clearance": {
            "planner_failures": {"/C2_HI": {}},
            "successful_nets": ["/C1_HI"],
        }}
        unchanged = {"power_body_clearance": {
            "planner_failures": {"/C2_HI": {}},
        }}
        new_failure = {"power_body_clearance": {
            "planner_failures": {"/C1_HI": {}, "/C2_HI": {}},
        }}

        self.assertIsNone(synth._placement_atomic_multirail_transition(
            baseline, unchanged, {"kind":
                                  "power_corridor_relief_envelope_reseat"}))
        self.assertIsNone(synth._placement_atomic_multirail_transition(
            baseline, new_failure, {"kind": "decoupler_cell_reorient"}))

    def test_atomic_multirail_primary_requires_exact_successful_peer(self):
        move = {"kind": "power_corridor_relief_joint_envelope_pack"}
        enabled = {"power_body_clearance": {
            "planner_failures": {"/C2_HI": {}},
            "successful_nets": ["/C1_HI"],
        }}
        isolated = {"power_body_clearance": {
            "planner_failures": {"/C2_HI": {}},
            "successful_nets": [],
        }}

        self.assertTrue(synth._placement_atomic_multirail_primary(
            move, enabled))
        self.assertFalse(synth._placement_atomic_multirail_primary(
            move, isolated))

    def test_atomic_corridor_budget_prioritizes_complete_cut_sets(self):
        moves = [
            {"kind": "power_corridor_relief_cell_reseat",
             "ref": "C%d" % index}
            for index in range(40)
        ] + [
            {"kind": "power_corridor_relief_joint_envelope_pack",
             "ref": "U1", "envelope_index": index}
            for index in range(30)
        ]

        selected = synth._placement_atomic_corridor_move_specs(moves, 16)
        joint = [move for move in selected if move["kind"] ==
                 "power_corridor_relief_joint_envelope_pack"]

        self.assertEqual(len(selected), 16)
        self.assertEqual(len(joint), 12)
        self.assertGreater(len({move["envelope_index"] for move in joint}),
                           8)

    def test_atomic_corridor_budget_falls_back_to_fair_sampler(self):
        moves = [{"kind": "power_via_field_access_reseat",
                  "ref": "U%d" % index} for index in range(20)]

        selected = synth._placement_atomic_corridor_move_specs(moves, 7)

        self.assertEqual(len(selected), 7)
        self.assertEqual(len({move["ref"] for move in selected}), 7)

    def test_atomic_anchor_relief_pack_preserves_declared_axis(self):
        moves = [{
            "kind": "power_corridor_declared_anchor_slide",
            "ref": "J_IN", "owner_ref": "J_IN", "net": "/RAIL",
            "axis": "x", "distance_mm": 4.0,
            "position": (14.0, 2.0, 0.0),
            "placements": {"J_IN": (14.0, 2.0, 0.0)},
            "declared_constrained_refs": ["J_IN"],
        }, {
            "kind": "power_corridor_relief_envelope_reseat",
            "ref": "C1", "owner_ref": "C1", "net": "/RAIL",
            "distance_mm": 3.0,
            "position": (20.0, 13.0, 90.0),
            "placements": {"C1": (20.0, 13.0, 90.0)},
        }]

        specs = synth._placement_atomic_anchor_relief_specs(moves)

        self.assertEqual(len(specs), 1)
        self.assertEqual(specs[0]["kind"],
                         "power_corridor_atomic_anchor_relief_pack")
        self.assertEqual(set(specs[0]["placements"]), {"J_IN", "C1"})
        self.assertEqual(specs[0]["declared_constrained_refs"], ["J_IN"])
        self.assertEqual(specs[0]["declared_slide_axes"], {"J_IN": "x"})

    def test_atomic_anchor_relief_pack_never_crosses_nets(self):
        moves = [{
            "kind": "power_corridor_declared_anchor_slide",
            "ref": "J1", "net": "/A", "axis": "x",
            "position": (1.0, 1.0, 0.0),
            "declared_constrained_refs": ["J1"],
        }, {
            "kind": "power_corridor_relief_cell_reseat",
            "ref": "C1", "net": "/B",
            "position": (2.0, 2.0, 0.0),
        }]

        self.assertEqual(
            synth._placement_atomic_anchor_relief_specs(moves), [])

    def test_power_corridor_uses_declared_edge_anchor_slide(self):
        candidate = SimpleNamespace(P={
            "J_IN": (20.0, 2.0, 0.0), "RS1": (20.0, 20.0, 0.0),
        })
        evidence = {
            "power_body_clearance": {
                "planner_failures": {"/RAIL": {
                    "planner_bottleneck": {"relief": {"B.Cu:1->2": {
                        "immovable_owners": ["J_IN"],
                        "relief_sets": [],
                    }}},
                }},
            },
            "decoupler": {"details": []},
            "pair_launch": {"violations": []},
            "critical_terminal_order": {"violations": []},
            "stranded": {"details": []},
        }

        moves = synth._placement_craft_move_specs(
            candidate, evidence, immovable={"J_IN"},
            comps={ref: object() for ref in candidate.P},
            required_stages=["power_corridor_access"],
            policy_params={"power_corridor_anchor_slides": {
                "J_IN": {"axis": "x", "step_mm": 4.0, "max_mm": 12.0},
            }})
        slides = [move for move in moves if move["kind"] ==
                  "power_corridor_declared_anchor_slide"]

        self.assertEqual(len(slides), 6)
        self.assertEqual({move["position"][1] for move in slides}, {2.0})
        self.assertEqual({move["distance_mm"] for move in slides},
                         {4.0, 8.0, 12.0})
        self.assertTrue(all(move["declared_constrained_refs"] == ["J_IN"]
                            for move in slides))

    def test_power_corridor_can_repack_named_decoupler_blocker(self):
        candidate = SimpleNamespace(P={
            "U1": (10.0, 10.0, 0.0), "C1": (11.0, 10.0, 0.0),
        })
        evidence = {
            "power_body_clearance": {"planner_failures": {"/RAIL": {
                "planner_bottleneck": {"relief": {"B.Cu:1->2": {
                    "relief_sets": [{
                        "owners": ["C1"],
                        "path_mm": [[0.0, 10.0], [20.0, 10.0]],
                    }],
                }}},
            }}},
            "decoupler": {"details": [{
                "owner_ref": "U1", "cap_ref": "C1",
                "status": "assigned", "actionable": False,
            }]},
            "pair_launch": {"violations": []},
            "critical_terminal_order": {"violations": []},
            "stranded": {"details": []},
        }
        reseat = {
            "kind": "decoupler_cell_reorient", "ref": "U1",
            "owner_ref": "U1", "position": candidate.P["U1"],
            "placements": {
                "U1": candidate.P["U1"], "C1": (10.0, 12.0, 90.0)},
        }

        with mock.patch.object(
                synth, "_decoupler_owner_move_specs",
                return_value=[reseat]):
            moves = synth._placement_craft_move_specs(
                candidate, evidence,
                comps={ref: object() for ref in candidate.P},
                required_stages=["power_corridor_access"])
        repacks = [move for move in moves if move["kind"] ==
                   "power_corridor_decoupler_cell_reseat"]

        self.assertEqual(len(repacks), 1)
        self.assertEqual(repacks[0]["relief_owner"], "C1")
        self.assertEqual(repacks[0]["placements"]["C1"],
                         (10.0, 12.0, 90.0))

    def test_exact_bundle_clearance_can_repack_named_decoupler(self):
        candidate = SimpleNamespace(P={
            "U1": (10.0, 10.0, 0.0), "C1": (11.0, 10.0, 0.0),
        })
        evidence = {
            "power_body_clearance": {"planner_failures": {"/RAIL": {
                "planner_bottleneck": {
                    "kind": "realized_exact_clearance",
                    "clashes": [{
                        "owner": "C1", "intersection_area_mm2": 0.05,
                        "intersection_bounds_mm": [10.9, 9.9, 11.1, 10.1],
                    }],
                },
            }}},
            "decoupler": {"details": [{
                "owner_ref": "U1", "cap_ref": "C1",
                "status": "assigned", "actionable": False,
            }]},
            "pair_launch": {"violations": []},
            "critical_terminal_order": {"violations": []},
            "stranded": {"details": []},
        }
        reseat = {
            "kind": "decoupler_cell_reorient", "ref": "U1",
            "owner_ref": "U1", "position": candidate.P["U1"],
            "placements": {
                "U1": candidate.P["U1"], "C1": (10.0, 12.0, 90.0)},
        }

        with mock.patch.object(
                synth, "_decoupler_owner_move_specs",
                return_value=[reseat]):
            moves = synth._placement_craft_move_specs(
                candidate, evidence,
                comps={ref: object() for ref in candidate.P},
                required_stages=["power_corridor_access"])

        repacks = [move for move in moves if move["kind"] ==
                   "power_corridor_exact_clearance_decoupler_reseat"]
        translations = [move for move in moves if move["kind"] ==
                        "power_corridor_exact_clearance_cell_reseat"]
        self.assertEqual(len(repacks), 1)
        self.assertTrue(translations)
        self.assertEqual(repacks[0]["clearance_owner"], "C1")
        self.assertEqual(repacks[0]["placements"]["C1"],
                         (10.0, 12.0, 90.0))

    def test_craft_key_rewards_each_restored_power_via_field(self):
        def evidence(failed):
            return {
                "errors": [],
                "power_body_clearance": {
                    "ok": False, "error": "exact territory unroutable",
                    "planner_failures": {
                        "/N%d" % index: {} for index in range(failed)},
                },
                "decoupler": {"violations": [], "details": []},
                "stranded": {"violations": [], "details": []},
                "pair_launch": {"violations": []},
            }
        self.assertLess(synth.placement_craft_key(evidence(1)),
                        synth.placement_craft_key(evidence(2)))

    def test_craft_key_optimizes_total_loop_after_worst_loop(self):
        base = {
            "errors": [],
            "decoupler": {"ok": True, "violations": [], "details": [
                {"loop_proxy_mm": 3.0}, {"loop_proxy_mm": 2.5}]},
            "stranded": {"ok": True, "violations": [], "details": []},
            "pair_launch": {"ok": True, "violations": []},
        }
        better = {
            **base,
            "decoupler": {"ok": True, "violations": [], "details": [
                {"loop_proxy_mm": 3.0}, {"loop_proxy_mm": 1.5}]},
        }
        self.assertLess(synth.placement_craft_key(better),
                        synth.placement_craft_key(base))

    def test_craft_key_does_not_polish_passing_cells_with_active_blockers(self):
        base = {
            "errors": [],
            "decoupler": {
                "ok": False,
                "violations": [("BYP_BAD", "REG.1[VCC]", 4.0)],
                "details": [
                    {"cap_ref": "BYP_BAD", "actionable": True,
                     "loop_proxy_mm": 4.0},
                    {"cap_ref": "BYP_GOOD", "actionable": False,
                     "loop_proxy_mm": 3.0},
                ],
            },
            "stranded": {"ok": True, "violations": [], "details": []},
            "pair_launch": {"ok": True, "violations": []},
        }
        polished = copy.deepcopy(base)
        polished["decoupler"]["details"][1]["loop_proxy_mm"] = 1.0
        self.assertEqual(synth.placement_craft_key(polished),
                         synth.placement_craft_key(base))

    def test_craft_key_prefers_active_blocker_over_clean_margin(self):
        base = {
            "errors": [],
            "decoupler": {
                "ok": False,
                "violations": [("BYP_BAD", "REG.1[VCC]", 4.0)],
                "details": [
                    {"cap_ref": "BYP_BAD", "actionable": True,
                     "loop_proxy_mm": 4.0},
                    {"cap_ref": "BYP_GOOD", "actionable": False,
                     "loop_proxy_mm": 1.0},
                ],
            },
            "stranded": {"ok": True, "violations": [], "details": []},
            "pair_launch": {"ok": True, "violations": []},
        }
        better = copy.deepcopy(base)
        better["decoupler"]["details"][0]["loop_proxy_mm"] = 3.9
        better["decoupler"]["details"][1]["loop_proxy_mm"] = 100.0
        self.assertLess(synth.placement_craft_key(better),
                        synth.placement_craft_key(base))

    def test_craft_key_never_trades_a_pair_launch_for_one_less_bypass(self):
        baseline = {
            "errors": [],
            "decoupler": {
                "ok": False,
                "violations": [("C%d" % i, "U1.VCC", 4.0)
                               for i in range(6)],
                "details": [{"cap_ref": "C%d" % i,
                             "actionable": True, "loop_proxy_mm": 4.0}
                            for i in range(6)],
            },
            "stranded": {"ok": True, "violations": [], "details": []},
            "pair_launch": {"ok": True, "violations": []},
        }
        regressed = copy.deepcopy(baseline)
        regressed["decoupler"]["violations"].pop()
        regressed["decoupler"]["details"].pop()
        regressed["pair_launch"] = {
            "ok": False,
            "violations": [{"pair": "DATA", "blocker_ref": "F1"}],
        }
        self.assertLess(synth.placement_craft_key(baseline),
                        synth.placement_craft_key(regressed))

    def test_craft_key_never_trades_crossed_critical_terminals_for_bypass(self):
        baseline = {
            "errors": [],
            "decoupler": {
                "ok": False,
                "violations": [("C1", "U1.1[VCC]", 4.0)],
                "details": [{"cap_ref": "C1", "actionable": True,
                             "loop_proxy_mm": 4.0}],
            },
            "stranded": {"ok": True, "violations": [], "details": []},
            "pair_launch": {"ok": True, "violations": []},
            "critical_terminal_order": {
                "ok": True, "violations": [], "direct_length_mm": 8.0},
        }
        crossed = copy.deepcopy(baseline)
        crossed["decoupler"] = {
            "ok": True, "violations": [], "details": []}
        crossed["critical_terminal_order"] = {
            "ok": False,
            "violations": [{"anchor_ref": "RS1", "ref": "U1"}],
            "direct_length_mm": 16.0,
        }
        self.assertLess(synth.placement_craft_key(baseline),
                        synth.placement_craft_key(crossed))

    def test_craft_key_never_trades_assigned_cell_for_missing_assignment(self):
        assigned = {
            "errors": [],
            "decoupler": {
                "ok": False,
                "violations": [
                    ("C1", "U1.GND[VCC]", 3.8),
                    ("C1", "U1.1[VCC] local-cell-access", 3.5),
                ],
                "details": [{
                    "cap_ref": "C1", "status": "assigned",
                    "actionable": True, "loop_proxy_mm": 7.3,
                }],
            },
            "stranded": {"ok": True, "violations": [], "details": []},
            "pair_launch": {"ok": True, "violations": []},
        }
        missing = copy.deepcopy(assigned)
        missing["decoupler"] = {
            "ok": False,
            "violations": [("C1", "U1.1[VCC]", 3.51)],
            "details": [{
                "cap_ref": "C1", "status": "missing",
                "actionable": True, "distance_mm": 3.51,
            }],
        }
        self.assertLess(synth.placement_craft_key(assigned),
                        synth.placement_craft_key(missing))

    def test_craft_key_quantizes_sub_ten_micron_score_noise(self):
        def evidence(loop):
            return {
                "errors": [],
                "decoupler": {"ok": True, "violations": [],
                              "details": [{"loop_proxy_mm": loop}]},
                "stranded": {"ok": True, "violations": [], "details": []},
                "pair_launch": {"ok": True, "violations": []},
            }
        self.assertEqual(synth.placement_craft_key(evidence(1.231)),
                         synth.placement_craft_key(evidence(1.234)))

    def test_route_blocking_key_ignores_clean_terminal_length_polish(self):
        baseline = {
            "errors": [],
            "decoupler": {"ok": True, "violations": [], "details": []},
            "stranded": {"ok": True, "violations": [], "details": []},
            "pair_launch": {"ok": True, "violations": []},
            "critical_terminal_order": {
                "ok": True, "violations": [], "direct_length_mm": 10.0},
        }
        longer = copy.deepcopy(baseline)
        longer["critical_terminal_order"]["direct_length_mm"] = 10.5

        self.assertGreater(synth.placement_craft_key(longer),
                           synth.placement_craft_key(baseline))
        self.assertEqual(synth.placement_craft_blocking_key(longer),
                         synth.placement_craft_blocking_key(baseline))

    def test_route_blocking_key_retains_critical_terminal_violation(self):
        baseline = {
            "errors": [],
            "decoupler": {"ok": True, "violations": [], "details": []},
            "stranded": {"ok": True, "violations": [], "details": []},
            "pair_launch": {"ok": True, "violations": []},
            "critical_terminal_order": {
                "ok": True, "violations": [], "direct_length_mm": 10.0},
        }
        crossed = copy.deepcopy(baseline)
        crossed["critical_terminal_order"] = {
            "ok": False,
            "violations": [{"anchor_ref": "RS1", "ref": "U1"}],
            "direct_length_mm": 9.0,
        }

        self.assertGreater(synth.placement_craft_blocking_key(crossed),
                           synth.placement_craft_blocking_key(baseline))

    def test_plateau_certificate_routes_blockers_to_generic_stages(self):
        evidence = {
            "decoupler": {
                "violations": [
                    ("C_MISSING", "U1.1[VCC]", 3.0),
                    ("C_PATH", "U2.2[VDD] local-cell-access", 2.0),
                    ("C_RETURN", "U3.GND[VIO]", 1.5),
                ],
                "details": [
                    {"cap_ref": "C_MISSING", "owner_ref": "U1",
                     "actionable": True, "status": "missing"},
                    {"cap_ref": "C_PATH", "owner_ref": "U2",
                     "actionable": True, "status": "assigned",
                     "supply_access_ok": False,
                     "supply_access_reason": "no guarded local supply path"},
                    {"cap_ref": "C_RETURN", "owner_ref": "U3",
                     "actionable": True, "status": "assigned",
                     "supply_access_ok": True, "ground_distance_mm": 2.5},
                ],
            },
            "stranded": {"violations": []},
            "pair_launch": {"violations": []},
        }
        certificate = synth.placement_craft_blocker_certificate(
            evidence, {
                "reason": "no_monotonic_legal_improvement",
                "blocking_refs": [{"ref": "U2", "hits": 4}],
                "rejection_counts": {"not_monotonic": 10},
            })
        self.assertTrue(certificate["neighborhood_exhausted"])
        self.assertTrue(certificate["upstream_action_required"])
        self.assertEqual(certificate["active_decoupler_count"], 3)
        self.assertEqual(certificate["required_stages"], [
            "component_selection_or_assignment",
            "guarded_local_interconnect",
            "return_path_placement",
        ])
        self.assertEqual(certificate["collision_blockers"],
                         [{"ref": "U2", "hits": 4}])

    def test_plateau_certificate_routes_out_of_range_cap_to_placement(self):
        evidence = {
            "decoupler": {
                "violations": [("BYP", "REG.1[VCC]", 3.7)],
                "details": [{
                    "cap_ref": "BYP", "owner_ref": "REG",
                    "owner_pin": "1", "rail": "VCC",
                    "actionable": True, "status": "missing",
                    "nearest_compatible_ref": "BYP",
                    "nearest_compatible_mm": 3.7,
                    "assignment_limit_mm": 3.5,
                    "assignment_gap_mm": 0.2,
                }],
            },
            "stranded": {"violations": []},
            "pair_launch": {"violations": []},
        }
        certificate = synth.placement_craft_blocker_certificate(evidence)
        self.assertEqual(certificate["required_stages"],
                         ["device_cell_placement"])
        blocker = certificate["active_decouplers"][0]
        self.assertEqual(blocker["assignment_gap_mm"], 0.2)
        self.assertEqual(blocker["nearest_compatible_ref"], "BYP")

    def test_craft_key_is_fail_closed_and_electrical_first(self):
        clean = {
            "errors": [],
            "decoupler": {"ok": True, "violations": [], "details": []},
            "stranded": {"ok": True, "violations": [], "details": []},
        }
        bad_bypass = {
            "errors": [],
            "decoupler": {
                "ok": False, "violations": [("C1", "U1.1[VCC]", 5.0)],
                "details": [{"distance_mm": 5.0}]},
            "stranded": {"ok": True, "violations": [], "details": []},
        }
        self.assertLess(synth.placement_craft_key(clean),
                        synth.placement_craft_key(bad_bypass))
        self.assertLess(synth.placement_craft_key(bad_bypass),
                        synth.placement_craft_key(None))

    def test_evidence_uses_one_shared_pair_of_checkers(self):
        with mock.patch.object(
                synth, "_oracle_decoupler_adjacency",
                return_value={"ok": True, "violations": [], "details": []}), \
                mock.patch.object(
                    synth, "_oracle_stranded_parts",
                    return_value={"ok": False, "violations": [("C9", 25.0)],
                                  "details": [{"ref": "C9",
                                               "distance_mm": 25.0}]}):
            evidence = synth.placement_craft_evidence("placed.kicad_pcb")
        self.assertFalse(evidence["ok"])
        self.assertEqual(synth.placement_craft_key(evidence)[:8],
                         (0, 0, 0, 0, 0, 0, 0, 1))

    def test_locked_reconcile_rolls_back_non_monotonic_result(self):
        with tempfile.TemporaryDirectory() as directory:
            board = os.path.join(directory, "board.kicad_pcb")
            with open(board, "w", encoding="utf-8") as handle:
                handle.write("original")

            def destructive(path):
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write("changed")
                return {"+5V": 4}

            scores = [SimpleNamespace(unconnected=2, drc=0),
                      SimpleNamespace(unconnected=3, drc=0)]
            with mock.patch.object(cec_fr, "reconcile_locked_nets",
                                   side_effect=destructive), \
                    mock.patch.object(synth.cec_score, "score",
                                      side_effect=scores):
                report = synth._reconcile_locked_nets_transactionally(board)
            self.assertTrue(report["rolled_back"])
            with open(board, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "original")

    def test_corner_finish_ignores_unstable_endpoint_hash_only(self):
        """pcbnew save may reselect a ratline endpoint without changing topology."""
        with tempfile.TemporaryDirectory() as directory:
            board = os.path.join(directory, "board.kicad_pcb")
            with open(board, "w", encoding="utf-8") as handle:
                handle.write("original")
            common = dict(unconnected=2, drc=0, kelvin_ok=True,
                          diffpair_ok=True)
            before = SimpleNamespace(
                **common, detail={"unconn_nets": ["/A"],
                                  "unconn_signature_sha256": "old"})
            after = SimpleNamespace(
                **common, detail={"unconn_nets": ["/A"],
                                  "unconn_signature_sha256": "new"})
            with mock.patch.object(
                    cec_fr, "chamfer_unlocked_right_angles",
                    return_value={"schema": 1, "chamfered": 3}), \
                    mock.patch.object(synth.cec_score, "score",
                                      side_effect=[before, after]):
                report, final_score = synth._chamfer_routes_transactionally(
                    board)
            self.assertFalse(report["rolled_back"], report)
            self.assertTrue(report["unconnected_nets_unchanged"])
            self.assertIs(final_score, after)

    def test_final_dangling_cleanup_consumes_exact_unlocked_uuid(self):
        violation = {
            "type": "track_dangling",
            "description": "Track has unconnected end",
            "items": [{"uuid": "dangling-uuid"}],
        }
        before = SimpleNamespace(
            unconnected=2, drc=1, kelvin_ok=True, diffpair_ok=True,
            detail={"unconn_nets": ["/CAN_RX"],
                    "structural_violations": [violation]})
        after = SimpleNamespace(
            unconnected=2, drc=0, kelvin_ok=True, diffpair_ok=True,
            detail={"unconn_nets": ["/CAN_RX"],
                    "structural_violations": []})
        with tempfile.TemporaryDirectory() as directory:
            board = os.path.join(directory, "board.kicad_pcb")
            with open(board, "w", encoding="utf-8") as handle:
                handle.write("original")
            mutation = {
                "removed": [{
                    "uuid": "dangling-uuid", "kind": "track_dangling",
                    "net": "/CAN_RX", "class": "PCB_TRACK",
                    "was_locked": True,
                }],
                "removed_count": 1,
            }
            with mock.patch.object(
                    synth, "_remove_structural_dangling_uuids_isolated",
                    return_value=mutation), \
                    mock.patch.object(synth.cec_score, "score",
                                      side_effect=[before, after]):
                report, final_score = (
                    synth._prune_structural_dangling_transactionally(board))
        self.assertFalse(report["rolled_back"], report)
        self.assertEqual(report["removed_count"], 1)
        self.assertIs(final_score, after)

    def test_edge_guard_has_no_implicit_connector_body_window(self):
        board = pcbnew.CreateEmptyBoard()
        for ax, ay, bx, by in ((0, 0, 20, 0), (20, 0, 20, 20),
                               (20, 20, 0, 20), (0, 20, 0, 0)):
            shape = pcbnew.PCB_SHAPE(board)
            shape.SetShape(pcbnew.SHAPE_T_SEGMENT)
            shape.SetStart(pcbnew.VECTOR2I_MM(ax, ay))
            shape.SetEnd(pcbnew.VECTOR2I_MM(bx, by))
            shape.SetLayer(pcbnew.Edge_Cuts)
            board.Add(shape)
        fp = pcbnew.FOOTPRINT(board)
        fp.SetReference("J1")
        fp.SetPosition(pcbnew.VECTOR2I_MM(10, 19.0))
        pad = pcbnew.PAD(fp)
        pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
        pad.SetSize(pcbnew.VECTOR2I_MM(1.5, 1.5))
        pad.SetPosition(fp.GetPosition())
        pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
        pad.SetLayerSet(pcbnew.LSET.AllCuMask())
        fp.Add(pad)
        board.Add(fp)

        guarded = cec_fr.edge_keepout("", board=board)
        bottom = [row for row in guarded
                  if row["name"].startswith("edge_bottom_")]
        self.assertTrue(any(row["x0"] <= 10 <= row["x1"]
                            for row in bottom))
        legacy = cec_fr.edge_keepout(
            "", board=board, access_windows=True)
        legacy_bottom = [row for row in legacy
                         if row["name"].startswith("edge_bottom_")]
        self.assertFalse(any(row["x0"] <= 10 <= row["x1"]
                             for row in legacy_bottom))

    def test_bounded_move_selection_spans_each_blockers_search_extent(self):
        moves = []
        for ordinal in range(12):
            moves.append({"ref": "C1", "kind": "reseat",
                          "ordinal": ordinal})
            moves.append({"ref": "C2", "kind": "reseat",
                          "ordinal": ordinal})
        selected = synth._bounded_diverse_move_specs(moves, 6)
        self.assertEqual(len(selected), 6)
        by_ref = {
            ref: [row["ordinal"] for row in selected if row["ref"] == ref]
            for ref in ("C1", "C2")
        }
        self.assertEqual(by_ref["C1"], [0, 6, 11])
        self.assertEqual(by_ref["C2"], [0, 6, 11])

    def test_bounded_move_selection_reassigns_exhausted_group_budget(self):
        moves = [{"ref": "C_SMALL", "kind": "reseat", "ordinal": 0}]
        moves.extend({"ref": "U_LARGE", "kind": "reseat",
                      "ordinal": ordinal} for ordinal in range(20))

        selected = synth._bounded_diverse_move_specs(moves, 10)
        evidence_selected = synth._bounded_evidence_move_specs(moves, 10)

        self.assertEqual(len(selected), 10)
        self.assertEqual(len(evidence_selected), 10)
        self.assertEqual(sum(row["ref"] == "C_SMALL"
                             for row in selected), 1)
        self.assertEqual(sum(row["ref"] == "U_LARGE"
                             for row in selected), 9)

    def test_assigned_ground_return_can_defer_to_mandatory_route_stage(self):
        evidence = {
            "ok": False, "errors": [],
            "decoupler": {
                "violations": [["C1", "U1.GND[+3V3]", 2.8]],
                "details": [{
                    "cap_ref": "C1", "status": "assigned",
                    "supply_access_ok": True,
                }],
            },
            "stranded": {"ok": True},
            "pair_launch": {"ok": True},
            "critical_terminal_order": {"ok": True},
            "pour_territory": {"ok": True},
        }
        refused = synth.placement_craft_admission(evidence)
        self.assertFalse(refused["ok"])
        admitted = synth.placement_craft_admission(
            evidence, allow_route_access_repair=True)
        self.assertTrue(admitted["ok"], admitted)
        self.assertEqual(
            admitted["deferred_to_route"][0]["repair"],
            "pre_route_ground_return")

    def test_distant_unassigned_ground_cell_never_defers(self):
        evidence = {
            "ok": False, "errors": [],
            "decoupler": {
                "violations": [["C1", "U1.GND[+3V3]", 8.0]],
                "details": [{
                    "cap_ref": "C1", "status": "assigned",
                    "supply_access_ok": False,
                }],
            },
            "stranded": {"ok": True},
            "pair_launch": {"ok": True},
            "critical_terminal_order": {"ok": True},
            "pour_territory": {"ok": True},
        }
        admitted = synth.placement_craft_admission(
            evidence, allow_route_access_repair=True)
        self.assertFalse(admitted["ok"])

    def test_promoted_stage_artifact_is_the_next_stage_input(self):
        self.assertEqual(
            synth._admitted_stage_artifact(
                "parent.kicad_pcb", "partial.kicad_pcb",
                {"promote_candidate": True}),
            "partial.kicad_pcb")
        self.assertEqual(
            synth._admitted_stage_artifact(
                "parent.kicad_pcb", "rejected.kicad_pcb",
            {"promote_candidate": False}),
            "parent.kicad_pcb")

    def test_route_tier_filters_nets_already_completed_upstream(self):
        score = SimpleNamespace(
            detail={"unconn_nets": ["/OPEN", "/POWER"]})
        self.assertEqual(
            synth._open_route_candidates(
                score, ["/DONE", "/OPEN", "/POWER"]),
            ["/OPEN", "/POWER"])
        unknown = SimpleNamespace(detail={})
        self.assertEqual(
            synth._open_route_candidates(unknown, ["/DONE", "/OPEN"]),
            ["/DONE", "/OPEN"])


if __name__ == "__main__":
    unittest.main()
