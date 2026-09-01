#!/usr/bin/env python3
"""Teeth for certificate repair and convergence telemetry."""

import copy
import os
import sys
import json
import tempfile
import unittest
from concurrent.futures import Future
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


class TestCertificateWorkerLifecycle(unittest.TestCase):
    def test_exact_pair_closure_defines_plane_authority_locally(self):
        source = Path(os.path.join(ROOT, "scripts",
                                   "cec_certificate_repair.py")).read_text(
                                       encoding="utf-8")
        function = source[source.index("def _close_certificate_pair"):
                          source.index("def _close_negotiation_worker")]
        self.assertIn("for layer_name in cec_fr.plane_layers(board)",
                      function)
        self.assertIn(
            "((start_layers & end_layers) & same_layer_authority) - plane",
            function)
        self.assertIn("remaining_s / remaining_layers", function)
        self.assertIn("same_layer_phase_deadline", function)
        self.assertIn("bridge_ops(deadline)", function)

    def test_helper_closed_target_preserves_pre_target_order_snapshot(self):
        source = Path(os.path.join(ROOT, "scripts",
                                   "cec_certificate_repair.py")).read_text(
                                       encoding="utf-8")
        relocation = source[
            source.index("def _attempt_route_certificate_via_clearance"):
            source.index("def _attempt_alternate_placement_route_order")]
        parent = source[
            source.index("def _attempt_footprint_relocation"):
            source.index("def _relocation_support_nets")]

        self.assertGreaterEqual(
            relocation.count('"target_route_baseline_path"'), 3)
        self.assertGreaterEqual(
            parent.count('"target_route_baseline_path"'), 3)
        self.assertIn('row["post_placement_dangling_cleanup"]', parent)
        self.assertIn('row["target_net_completion"]', parent)

    def test_broad_canonical_worker_uses_fast_breadth_before_negotiation(self):
        import cec_certificate_repair as repair

        board = mock.Mock()
        report = {"closed": 0}
        with mock.patch.object(
                repair.pcbnew, "LoadBoard", return_value=board), \
                mock.patch.object(
                    repair.cec_fr, "_project_netclass_resolver",
                    return_value="resolver"), \
                mock.patch.object(
                    repair.cec_fr, "synthesize_lastmile",
                    return_value=report) as synthesize:
            got = repair._broad_canonical_worker(
                "candidate.kicad_pcb", ("+3V3",))

        self.assertIs(got, report)
        self.assertTrue(synthesize.call_args.kwargs["bridge_fast"])
        self.assertEqual(synthesize.call_args.kwargs["maze_max_mm"], 0.0)

    def test_single_net_lastmile_uses_complete_caller_budget(self):
        import cec_certificate_repair as repair

        board = mock.Mock()
        report = {"closed": 0}
        with mock.patch.object(
                repair.pcbnew, "LoadBoard", return_value=board), \
                mock.patch.object(
                    repair.cec_fr, "_project_netclass_resolver",
                    return_value="resolver"), \
                mock.patch.object(
                    repair.cec_fr, "synthesize_lastmile",
                    return_value=report) as synthesize:
            got = repair._lastmile_worker(
                "candidate.kicad_pcb", ("+3V3",), 24, 8.0,
                wall_timeout_s=90.0)

        self.assertIs(got, report)
        self.assertEqual(
            synthesize.call_args.kwargs["per_net_timeout_s"], 90.0)
        self.assertEqual(synthesize.call_args.kwargs["min_w"], 0.2)

    def test_post_placement_whole_net_completion_uses_route_portfolio(self):
        source = Path(os.path.join(ROOT, "scripts",
                                   "cec_certificate_repair.py")).read_text(
                                       encoding="utf-8")
        parent = source[
            source.index("def _attempt_footprint_relocation"):
            source.index("def _relocation_support_nets")]

        self.assertIn(
            "(trial, (effective_target.target_net,), 24, 8.0, True,",
            parent)

    def test_deep_route_portfolio_precedes_destructive_negotiation(self):
        source = Path(os.path.join(ROOT, "scripts",
                                   "cec_certificate_repair.py")).read_text(
                                       encoding="utf-8")
        deep = source.index('"stage": "deep_route_portfolio"')
        negotiate = source.index(
            "# Always negotiate from the latest refusal certificates")

        self.assertLess(deep, negotiate)
        self.assertIn(
            '"schedule": "additive_route_before_destructive_negotiation"',
            source)

    def test_route_portfolio_does_not_discard_deep_search_budget(self):
        source = Path(os.path.join(ROOT, "scripts",
                                   "cec_certificate_repair.py")).read_text(
                                       encoding="utf-8")
        worker = source[
            source.index("def _lastmile_worker"):
            source.index("def _exact_relocated_connections_worker")]

        self.assertIn(
            "4.0, remaining / max(1, len(unresolved))",
            worker)
        self.assertNotIn(
            "min(35.0, remaining / max(1, len(unresolved)))",
            worker)

    def test_live_probe_worker_persists_proven_partial_closure(self):
        import cec_certificate_repair as repair

        board = mock.Mock()
        board.Zones.return_value = []
        report = {"closed": 2, "refused_details": []}
        with mock.patch.object(
                repair.pcbnew, "LoadBoard", return_value=board), \
                mock.patch.object(
                    repair.cec_fr, "_project_netclass_resolver",
                    return_value="resolver"), \
                mock.patch.object(
                    repair.cec_fr, "synthesize_lastmile",
                    return_value=report), \
                mock.patch.object(
                    repair, "_save_with_reconciled_endpoint_neckdowns") \
                as save:
            got = repair._live_refusal_probe_worker(
                "scratch.kicad_pcb", ("/I2C_SCL",))

        self.assertIs(got, report)
        save.assert_called_once_with("scratch.kicad_pcb", board, report)

    def test_composite_save_rederives_group_minimum_before_sidecar_rule(self):
        import cec_certificate_repair as repair

        board = mock.Mock()
        board.Zones.return_value = []
        board.GetTracks.return_value = []
        evidence = {
            "applicable": True,
            "group": repair.cec_fr.ENDPOINT_NECKDOWN_GROUP,
            "tracks": 12,
            "min_width_mm": 0.2,
        }
        report = {"closed": 4, "endpoint_neckdown": {
            "group": repair.cec_fr.ENDPOINT_NECKDOWN_GROUP,
            "tracks": 2,
            "min_width_mm": 0.25,
        }}
        with mock.patch.object(
                repair.cec_fr, "_project_netclass_resolver",
                return_value="resolver"), mock.patch.object(
                    repair.cec_fr, "reconcile_endpoint_neckdown_groups",
                    return_value=evidence) as reconcile, mock.patch.object(
                        repair.cec_fr, "group_local_pofv_signal_vias",
                        return_value={"vias": 2, "uuids": ["a", "b"]}
                    ) as group_pofv, mock.patch.object(
                        repair.pcbnew, "SaveBoard") as save, mock.patch.object(
                            repair.cec_fr, "ensure_endpoint_neckdown_rule",
                            return_value={"min_width_mm": 0.2}) as ensure, \
                mock.patch.object(
                    repair.cec_fr, "ensure_local_pofv_signal_via_rule",
                    return_value={"applicable": True}) as ensure_pofv:
            repair._save_with_reconciled_endpoint_neckdowns(
                "candidate.kicad_pcb", board, report)

        reconcile.assert_called_once_with(board, netclass_resolver="resolver")
        save.assert_called_once_with("candidate.kicad_pcb", board)
        self.assertEqual(report["zone_refill"], {
            "performed": False, "zone_count": 0})
        self.assertEqual(report["endpoint_neckdown"]["min_width_mm"], 0.2)
        self.assertEqual(
            ensure.call_args.args[1]["endpoint_neckdown"]["tracks"], 12)
        group_pofv.assert_called_once()
        self.assertEqual(
            ensure_pofv.call_args.args[1]["local_pofv_signal_vias"]["vias"],
            2)

    def test_spawn_apply_uses_bounded_shutdown_after_result(self):
        import cec_certificate_repair as repair

        future = Future()
        future.set_result({"status": "ok"})
        pool = mock.Mock()
        pool._processes = {}
        pool.submit.return_value = future
        with mock.patch.object(
                repair, "ProcessPoolExecutor", return_value=pool), \
                mock.patch.object(
                    repair.cec_process_pool, "shutdown_process_pool",
                    return_value={"clean": True}) as shutdown:
            result = repair._spawn_apply(str, ("value",))
        self.assertEqual(result, {"status": "ok"})
        pool.submit.assert_called_once_with(str, "value")
        shutdown.assert_called_once_with(
            pool, force=False, grace_s=2.0)

    def test_spawn_apply_forces_shutdown_when_worker_stalls(self):
        import cec_certificate_repair as repair

        future = Future()
        pool = mock.Mock()
        pool._processes = {}
        pool.submit.return_value = future
        with mock.patch.object(
                repair, "ProcessPoolExecutor", return_value=pool), \
                mock.patch.object(
                    repair.cec_process_pool, "watched_as_completed",
                    side_effect=repair.cec_process_pool.WorkerPoolStalled(
                        "stalled")), \
                mock.patch.object(
                    repair.cec_process_pool, "shutdown_process_pool",
                    return_value={"clean": True}) as shutdown:
            with self.assertRaisesRegex(
                    repair.cec_process_pool.WorkerPoolStalled, "stalled"):
                repair._spawn_apply(str, ("value",))
        self.assertTrue(future.cancelled())
        shutdown.assert_called_once_with(
            pool, force=True, grace_s=2.0)

    def test_spawn_apply_caps_child_to_active_transaction_deadline(self):
        import cec_certificate_repair as repair

        future = Future()
        pool = mock.Mock()
        pool._processes = {}
        pool.submit.return_value = future
        token = repair._WORKER_DEADLINE.set(105.0)
        try:
            with mock.patch.object(repair.time, "monotonic", return_value=100.0), \
                    mock.patch.object(
                        repair, "ProcessPoolExecutor", return_value=pool), \
                    mock.patch.object(
                        repair.cec_process_pool, "watched_as_completed",
                        side_effect=repair.cec_process_pool.WorkerPoolStalled(
                            "stalled")) as watched, \
                    mock.patch.object(
                        repair.cec_process_pool, "shutdown_process_pool",
                        return_value={"clean": True}):
                with self.assertRaisesRegex(
                        repair.cec_process_pool.WorkerPoolStalled, "stalled"):
                    repair._spawn_apply(str, ("value",), timeout_s=300.0)
        finally:
            repair._WORKER_DEADLINE.reset(token)
        self.assertEqual(watched.call_args.kwargs["wall_timeout_s"], 5.0)

    def test_spawn_apply_refuses_worker_after_transaction_deadline(self):
        import cec_certificate_repair as repair

        token = repair._WORKER_DEADLINE.set(99.0)
        try:
            with mock.patch.object(repair.time, "monotonic", return_value=100.0), \
                    self.assertRaisesRegex(
                        repair.cec_process_pool.WorkerPoolStalled,
                        "wall budget exhausted"):
                repair._spawn_apply(str, ("value",))
        finally:
            repair._WORKER_DEADLINE.reset(token)


class TestCertificateRepairPolicy(unittest.TestCase):
    def test_live_probe_replaces_nested_stale_refusal_geometry(self):
        import cec_certificate_repair as repair

        stale = {"completion_report": {
            "final_completion": {"refused_details": [{
                "net": "/OLD", "certificate": {"net": "/OLD"},
            }]},
            "lastmile": {"refused_details": [{
                "net": "/ALSO_OLD", "certificate": {"net": "/ALSO_OLD"},
            }]},
        }}
        live = {"refused_details": [{
            "net": "/LIVE", "certificate": {"net": "/LIVE"},
        }]}
        payload = repair._planning_completion_with_live_report(
            stale, ["/LIVE"], live)

        self.assertEqual(payload["unconn_nets"], ["/LIVE"])
        self.assertNotIn("lastmile", payload)
        self.assertEqual(
            [row["certificate"]["net"]
             for row in repair.refusal_certificates(payload)],
            ["/LIVE"])

    def test_failed_live_probe_retains_supplied_certificate_for_admission(self):
        import cec_certificate_repair as repair

        supplied = {"refused_details": [{
            "net": "/LIVE", "certificate": {"net": "/LIVE"},
        }]}
        payload = repair._planning_completion_with_live_report(
            supplied, ["/LIVE"], None)

        self.assertEqual(payload["unconn_nets"], ["/LIVE"])
        self.assertEqual(
            [row["certificate"]["net"]
             for row in repair.refusal_certificates(payload)],
            ["/LIVE"])

    def test_exact_completion_worker_wrapper_exposes_refusal_certificate(self):
        import cec_certificate_repair as repair

        wrapped = {"completion": {"refused_details": [{
            "net": "/TRAPPED", "certificate": {"net": "/TRAPPED"},
        }]}}
        self.assertEqual(
            [row["certificate"]["net"]
             for row in repair.refusal_certificates(wrapped)],
            ["/TRAPPED"])

    def test_atomic_timeout_certificate_survives_attempt_ledger(self):
        import cec_certificate_repair as repair

        report = {
            "attempts": [{
                "window": {"net": "/PIN_ESCAPE", "distance_mm": 3.25},
                "phases": {"close": {
                    "completion": {
                        "closed": 0, "refused": 1, "timed_out": True,
                        "refused_details": [],
                    },
                    "exact_pair_refusal": {
                        "refusal": "certificate_pair_search_timeout",
                        "certificate": {
                            "net": "/PIN_ESCAPE",
                            "endpoints": [{"kind": "pad", "ref": "U1",
                                           "pad": "7", "x_mm": 1.0,
                                           "y_mm": 2.0}],
                        },
                    },
                }},
            }],
            "final": {"unconn_nets": ["/PIN_ESCAPE"]},
            "plan": {},
        }

        payload = repair._repair_attempt_completion_payload(report)

        self.assertEqual(payload["refused"], 1)
        detail = payload["refused_details"][0]
        self.assertEqual(detail["net"], "/PIN_ESCAPE")
        self.assertEqual(detail["distance_mm"], 3.25)
        self.assertEqual(detail["source"], "atomic_exact_pair_refusal")

    def test_rejected_target_close_does_not_erase_live_refusal(self):
        import cec_certificate_repair as repair

        certificate = {
            "net": "GND",
            "endpoints": [{"kind": "via", "uuid": "gnd-via",
                           "x_mm": 1.0, "y_mm": 2.0}],
            "dominant_blockers": [{"kind": "via", "uuid": "sda-via"}],
        }
        report = {
            "attempts": [
                {"accepted": False, "completion": {
                    "closed_details": [],
                    "refused_details": [{"net": "GND",
                                           "certificate": certificate}],
                }},
                {"accepted": False, "phases": {"close": {"completion": {
                    "closed_details": [{"net": "GND"}],
                    "refused_details": [],
                }}}},
            ],
            "final": {"unconn_nets": ["GND"]},
            "plan": {},
        }

        payload = repair._repair_attempt_completion_payload(report)

        self.assertEqual(payload["refused"], 1)
        self.assertEqual(
            payload["refused_details"][0]["certificate"], certificate)

    def test_single_net_closure_ranks_certified_short_residual_first(self):
        import cec_certificate_repair as repair

        completion = {"refused_details": [
            {"net": "/FAR", "distance_mm": 12.0,
             "certificate": {"net": "/FAR"}},
            {"net": "/LOCAL", "distance_mm": 1.5,
             "certificate": {"net": "/LOCAL"}},
        ]}
        self.assertEqual(
            repair._rank_single_net_closure_targets(
                ["/UNKNOWN", "/FAR", "/LOCAL"], completion),
            ["/LOCAL", "/FAR", "/UNKNOWN"])

    def test_single_net_timeout_preserves_supplied_live_certificate(self):
        import cec_certificate_repair as repair

        supplied = {"refused_details": [{
            "net": "/TRAPPED", "distance_mm": 2.0,
            "certificate": {"net": "/TRAPPED", "marker": "supplied"},
        }]}
        merged = repair._merge_single_net_completion_reports(
            ["/TRAPPED"], [{
                "net": "/TRAPPED", "timeout": True,
                "error": "bounded worker timeout",
            }], supplied)

        self.assertEqual(merged["isolated_timeouts"][0]["net"], "/TRAPPED")
        self.assertEqual(
            merged["refused_details"][0]["certificate"]["marker"],
            "supplied")

    def test_fresh_single_net_refusal_replaces_stale_certificate(self):
        import cec_certificate_repair as repair

        supplied = {"refused_details": [{
            "net": "/A", "certificate": {"net": "/A", "marker": "old"},
        }]}
        fresh = {"refused_details": [{
            "net": "/A", "certificate": {"net": "/A", "marker": "new"},
        }]}
        merged = repair._merge_single_net_completion_reports(
            ["/A"], [{"net": "/A", "completion": fresh}], supplied)

        self.assertEqual(len(merged["refused_details"]), 1)
        self.assertEqual(
            merged["refused_details"][0]["certificate"]["marker"], "new")

    def test_support_relocation_defers_to_smaller_route_transaction(self):
        import cec_certificate_repair as repair

        footprint = {"targets": [{"ref": "C42"}]}
        negotiation = {"windows": [{
            "net": "/SS", "blocker_uuids": ["route-1"],
        }]}
        self.assertTrue(
            repair._defer_support_relocation(footprint, negotiation))
        self.assertFalse(
            repair._defer_support_relocation(footprint, {"windows": []}))

    def test_support_relocation_runs_after_every_current_window_timed_out(self):
        import cec_certificate_repair as repair

        footprint = {"targets": [{"ref": "C1"}]}
        negotiation = {"windows": [
            {"net": "/A", "priority": [0]},
            {"net": "/B", "priority": [1]},
        ]}
        prior = {"algorithm_revision": repair.REPAIR_ALGORITHM_REVISION,
                 "attempts": [
            {"stage": "atomic_negotiation", "window": {"net": net},
             "decision": "blocked_net_search_timeout",
             "phases": {"close": {"completion": {"timed_out": True}}}}
            for net in ("/A", "/B")
        ]}

        self.assertFalse(repair._defer_support_relocation(
            footprint, negotiation, prior))

    def test_support_relocation_runs_after_finite_route_portfolio_exhausts(self):
        import cec_certificate_repair as repair

        footprint = {"targets": [{"ref": "C42"}]}
        negotiation = {"windows": [{"net": "/SS", "priority": [0]}]}
        prior = {
            "algorithm_revision": repair.REPAIR_ALGORITHM_REVISION,
            "plan": {"negotiation_sweep": {
                "stop": "no_admissible_negotiation"}},
            "attempts": [
                {"stage": "atomic_negotiation", "variant": variant,
                 "window": {"net": "/SS"},
                 "decision": "blocked_net_still_refused",
                 "phases": {"close": {"completion": {"closed": 0}}}}
                for variant in range(4)
            ],
        }

        ordered, evidence = repair._prioritize_windows_by_proven_close(
            negotiation["windows"], prior)
        self.assertEqual([row["net"] for row in ordered], ["/SS"])
        self.assertEqual(evidence["exhausted_nets"], ["/SS"])
        self.assertFalse(repair._defer_support_relocation(
            footprint, negotiation, prior))

    def test_prior_footprint_candidate_keys_survive_nested_wave_report(self):
        import cec_certificate_repair as repair

        report = {"algorithm_revision": repair.REPAIR_ALGORITHM_REVISION,
                  "plan": {"footprint_relocation": {"sweep": {
            "attempts": [{
                "stage": "footprint_relocation",
                "target": {"ref": "C42"},
                "candidate": {"rotation_delta_deg": 90.0,
                              "dx_mm": 0.5, "dy_mm": -0.25},
            }],
        }}}}

        self.assertEqual(repair._prior_footprint_candidate_keys(report), {
            ("C42", 90.0, 0.5, -0.25),
        })
        self.assertTrue(repair._prior_has_footprint_attempts(report))
        stale = {**report, "algorithm_revision": "older"}
        self.assertEqual(repair._prior_footprint_candidate_keys(stale), set())
        self.assertTrue(repair._prior_has_footprint_attempts(stale))

        report["plan"]["placement_candidate_history"] = [
            ["U4", 180.0, 0.0, 0.0]]
        self.assertIn(("U4", 180.0, 0.0, 0.0),
                      repair._prior_footprint_candidate_keys(report))

        timed_out = copy.deepcopy(report)
        timed_out["plan"]["endpoint_owner_relocation"] = {"sweep": {
            "attempts": [{
                "stage": "endpoint_owner_relocation",
                "target": {"ref": "U4"},
                "candidate": {"rotation_delta_deg": 180.0,
                              "dx_mm": 0.0, "dy_mm": 0.0},
                "decision": "component_transaction_worker_error",
                "error": "WorkerPoolStalled: bounded support timeout",
            }],
        }}
        self.assertNotIn(("U4", 180.0, 0.0, 0.0),
                         repair._prior_footprint_candidate_keys(timed_out))
        bounded_restore = copy.deepcopy(timed_out)
        bounded_restore["plan"]["endpoint_owner_relocation"]["sweep"][
            "attempts"][0][
                "placement_copper_restoration_budget_s"] = 25.0
        self.assertIn(
            ("U4", 180.0, 0.0, 0.0),
            repair._prior_footprint_candidate_keys(bounded_restore))

        footprint = {"targets": [{"ref": "C42"}]}
        negotiation = {"windows": [{"net": "/OPEN"}]}
        self.assertFalse(repair._defer_support_relocation(
            footprint, negotiation, {**report, "changed": False}))
        self.assertTrue(repair._defer_support_relocation(
            footprint, negotiation,
            {**report, "algorithm_revision": "older", "changed": False}))

    def test_exhausted_placement_frontier_falls_through_to_routing(self):
        import cec_certificate_repair as repair

        exhausted_support = {
            "targets": [{"ref": "C1"}],
            "attempts": [],
            "accepted": [],
        }
        exhausted_owner = {
            "targets": [{"ref": "U1"}],
            "attempts": [],
            "accepted": [],
        }
        self.assertFalse(repair._placement_frontier_advanced(
            exhausted_support, exhausted_owner))
        self.assertFalse(repair._placement_frontier_advanced(
            {**exhausted_support, "attempts": [{"decision": "refused"}]},
            exhausted_owner))
        self.assertTrue(repair._placement_frontier_advanced(
            exhausted_support,
            {**exhausted_owner, "accepted": [{"ref": "U1"}]}))

    def test_placement_candidate_history_merges_prior_and_partial_attempts(self):
        import cec_certificate_repair as repair

        prior = {("C1", 0.0, 0.25, 0.0)}
        plan = {"footprint_relocation": {"sweep": {"attempts": [{
            "stage": "footprint_relocation",
            "target": {"ref": "C2"},
            "candidate": {
                "rotation_delta_deg": 180.0,
                "dx_mm": -0.5,
                "dy_mm": 0.75,
            },
        }]}}}

        history = repair._persist_placement_candidate_history(plan, prior)

        self.assertEqual({tuple(row) for row in history}, {
            ("C1", 0.0, 0.25, 0.0),
            ("C2", 180.0, -0.5, 0.75),
        })
        self.assertEqual(plan["placement_candidate_history"], history)

    def test_mobility_cell_signature_prevents_candidate_aliasing(self):
        import cec_certificate_repair as repair

        pose = {"rotation_delta_deg": 180.0,
                "dx_mm": 0.5, "dy_mm": -0.25}
        base = repair._footprint_candidate_key("C42", pose)
        expanded = repair._footprint_candidate_key("C42", {
            **pose, "mobility_companion_refs": ["C43", "C6"],
        })

        self.assertNotEqual(base, expanded)
        self.assertEqual(expanded[0], "C42|C43,C6")

    def test_placement_conflict_classifier_separates_pipeline_copper(self):
        import pcbnew
        import cec_certificate_repair as repair

        board = pcbnew.CreateEmptyBoard()
        moved_net = pcbnew.NETINFO_ITEM(board, "/OPEN")
        blocker_net = pcbnew.NETINFO_ITEM(board, "/BLOCK")
        board.Add(moved_net); board.Add(blocker_net)

        def footprint(ref, x_mm, net):
            item = pcbnew.FOOTPRINT(board)
            item.SetReference(ref)
            pad = pcbnew.PAD(item)
            pad.SetPadName("1")
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetSize(pcbnew.VECTOR2I_MM(1.0, 1.0))
            pad.SetPosition(pcbnew.VECTOR2I_MM(x_mm, 5.0))
            pad.SetLayerSet(pcbnew.PAD.SMDMask())
            pad.SetNet(net)
            item.Add(pad); board.Add(item)
            return item, pad

        _moved, moved_pad = footprint("C2", 5.0, moved_net)
        _fixed, fixed_pad = footprint("U1", 6.0, blocker_net)
        track = pcbnew.PCB_TRACK(board)
        track.SetStart(pcbnew.VECTOR2I_MM(4.0, 5.0))
        track.SetEnd(pcbnew.VECTOR2I_MM(7.0, 5.0))
        track.SetWidth(pcbnew.FromMM(0.25))
        track.SetLayer(pcbnew.F_Cu)
        track.SetNet(blocker_net)
        track.SetLocked(True)
        board.Add(track)
        track_uuid = repair._uuid(track)
        drc = {"violations": [
            {"type": "clearance", "items": [
                {"uuid": repair._uuid(moved_pad), "description": "moved"},
                {"uuid": track_uuid, "description": "generated route"},
            ]},
            {"type": "courtyards_overlap", "items": [
                {"uuid": repair._uuid(moved_pad), "description": "moved"},
                {"uuid": repair._uuid(fixed_pad), "description": "fixed"},
            ]},
        ]}
        target = repair.asdict(repair.FootprintRepairTarget(
            ref="C2", target_net="/OPEN", endpoint_ref="U1",
            endpoint_pad="1", endpoint_x_mm=6.0, endpoint_y_mm=5.0,
            hit_count=1, distance_mm=1.0, priority=(0,),
            motion="toward_endpoint"))

        with mock.patch.object(repair.pcbnew, "LoadBoard", return_value=board):
            report = repair._classify_placement_conflicts_worker(
                "candidate.kicad_pcb", drc, target, {}, (track_uuid,))

        self.assertEqual(report["movable_track_uuids"], [track_uuid])
        self.assertEqual(report["movable_via_uuids"], [])
        self.assertEqual(report["fixed_conflict_count"], 1)
        self.assertEqual(report["root_causes"], {
            "pipeline_copper_collision": 1,
            "stationary_component_collision": 1,
        })

    def test_placement_conflict_classifier_emits_via_displacement_target(self):
        import pcbnew
        import cec_certificate_repair as repair

        board = pcbnew.CreateEmptyBoard()
        moved_net = pcbnew.NETINFO_ITEM(board, "/OPEN")
        via_net = pcbnew.NETINFO_ITEM(board, "/BLOCK")
        board.Add(moved_net); board.Add(via_net)
        footprint = pcbnew.FOOTPRINT(board)
        footprint.SetReference("R2")
        pad = pcbnew.PAD(footprint)
        pad.SetPadName("1")
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(pcbnew.VECTOR2I_MM(1.0, 1.0))
        pad.SetPosition(pcbnew.VECTOR2I_MM(5.0, 5.0))
        pad.SetLayerSet(pcbnew.PAD.SMDMask())
        pad.SetNet(moved_net)
        footprint.Add(pad); board.Add(footprint)
        via = pcbnew.PCB_VIA(board)
        via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetPosition(pcbnew.VECTOR2I_MM(7.0, 5.0))
        via.SetWidth(pcbnew.FromMM(0.6))
        via.SetDrill(pcbnew.FromMM(0.3))
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetNet(via_net)
        via.SetLocked(True)
        board.Add(via)
        via_uuid = repair._uuid(via)
        drc = {"violations": [{"type": "clearance", "items": [
            {"uuid": repair._uuid(pad), "description": "moved pad"},
            {"uuid": via_uuid, "description": "generated via"},
        ]}]}
        target = repair.asdict(repair.FootprintRepairTarget(
            ref="R2", target_net="/OPEN", endpoint_ref="U1",
            endpoint_pad="1", endpoint_x_mm=4.0, endpoint_y_mm=5.0,
            hit_count=1, distance_mm=1.0, priority=(0,),
            motion="toward_endpoint"))

        with mock.patch.object(repair.pcbnew, "LoadBoard", return_value=board):
            report = repair._classify_placement_conflicts_worker(
                "candidate.kicad_pcb", drc, target, {}, (via_uuid,))

        self.assertEqual(report["movable_via_uuids"], [via_uuid])
        self.assertEqual(len(report["movable_via_targets"]), 1)
        via_target = report["movable_via_targets"][0]
        self.assertEqual(via_target["uuid"], via_uuid)
        self.assertEqual(via_target["counterpart_uuids"], (
            repair._uuid(pad),))
        self.assertEqual(via_target["drc_types"], ("clearance",))
        self.assertEqual(via_target["away_dx"], pcbnew.FromMM(2.0))
        self.assertEqual(via_target["away_dy"], 0)

    def test_route_certificate_expands_only_eligible_support_obstacle(self):
        import pcbnew
        import cec_certificate_repair as repair

        board = pcbnew.CreateEmptyBoard()
        net = pcbnew.NETINFO_ITEM(board, "/OPEN")
        ground = pcbnew.NETINFO_ITEM(board, "GND")
        board.Add(net); board.Add(ground)

        def support(ref, x_mm):
            footprint = pcbnew.FOOTPRINT(board)
            footprint.SetReference(ref)
            footprint.SetPosition(pcbnew.VECTOR2I_MM(x_mm, 5.0))
            for number, pad_net in (("1", net), ("2", ground)):
                pad = pcbnew.PAD(footprint)
                pad.SetPadName(number)
                pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
                pad.SetShape(pcbnew.PAD_SHAPE_RECT)
                pad.SetSize(pcbnew.VECTOR2I_MM(0.8, 0.8))
                pad.SetPosition(pcbnew.VECTOR2I_MM(
                    x_mm + (0.5 if number == "2" else 0.0), 5.0))
                pad.SetLayerSet(pcbnew.PAD.SMDMask())
                pad.SetNet(pad_net)
                footprint.Add(pad)
            board.Add(footprint)
            return footprint

        support("C2", 5.0)
        support("C3", 6.5)
        certificate = {
            "endpoints": [
                {"endpoint": "a", "ref": "U1", "pad": "1"},
                {"endpoint": "b", "ref": "C2", "pad": "1"},
            ],
            "layers": [{"layer": "F.Cu", "endpoint_escape": [{
                "endpoint": "a", "clear_rays": [], "ray_details": [
                    {"status": "foreign_copper_blocked",
                     "blockers": [{"kind": "pad", "ref": "C3",
                                    "pad": "1"}]},
                    {"status": "foreign_copper_blocked",
                     "blockers": [{"kind": "pad", "ref": "C3",
                                    "pad": "2"}]},
                ],
            }]}],
        }
        target = repair.asdict(repair.FootprintRepairTarget(
            ref="C2", target_net="/OPEN", endpoint_ref="U1",
            endpoint_pad="1", endpoint_x_mm=4.0, endpoint_y_mm=5.0,
            hit_count=2, distance_mm=1.0, priority=(0,),
            motion="toward_endpoint"))

        with mock.patch.object(repair.pcbnew, "LoadBoard", return_value=board):
            blockers = repair._route_certificate_soft_obstacle_refs(
                "candidate.kicad_pcb", certificate, target)

        self.assertEqual(blockers, [{
            "ref": "C3", "hit_count": 2,
            "distance_mm": 1.5, "pads": ["1", "2"],
        }])

    def test_route_certificate_track_ripup_respects_protected_net_policy(self):
        import pcbnew
        import cec_certificate_repair as repair

        board = pcbnew.CreateEmptyBoard()

        def track(net_name, y_mm):
            net = pcbnew.NETINFO_ITEM(board, net_name)
            board.Add(net)
            item = pcbnew.PCB_TRACK(board)
            item.SetStart(pcbnew.VECTOR2I_MM(1.0, y_mm))
            item.SetEnd(pcbnew.VECTOR2I_MM(4.0, y_mm))
            item.SetWidth(pcbnew.FromMM(0.22))
            item.SetLayer(pcbnew.F_Cu)
            item.SetNet(net)
            board.Add(item)
            return item

        movable = track("/ORDINARY", 2.0)
        protected = track("/SENSEC1_HI", 3.0)
        certificate = {"layers": [{"endpoint_escape": [{
            "endpoint": "a", "clear_rays": [], "ray_details": [{
                "status": "foreign_copper_blocked", "blockers": [
                    {"kind": "track", "uuid": repair._uuid(movable)},
                    {"kind": "track", "uuid": repair._uuid(protected)},
                ],
            }],
        }]}]}

        with mock.patch.object(repair.pcbnew, "LoadBoard", return_value=board):
            uuids = repair._route_certificate_movable_track_uuids(
                "candidate.kicad_pcb", certificate)

        self.assertEqual(uuids, [repair._uuid(movable)])

    def test_prior_repair_report_replays_latest_live_refusal_only(self):
        import cec_certificate_repair as repair

        def refusal(net, marker):
            return {
                "net": net,
                "certificate": {
                    "net": net, "marker": marker,
                    "endpoints": [
                        {"ref": "U1", "pad": "1", "x_mm": 1, "y_mm": 2},
                        {"ref": "C1", "pad": "1", "x_mm": 3, "y_mm": 4},
                    ],
                },
            }

        report = {
            "final": {"unconn_nets": ["/SS"]},
            "attempts": [
                {"completion": {"refused_details": [
                    refusal("/SS", "old"), refusal("/DONE", "old"),
                ]}},
                {"phases": {"close": {"completion": {
                    "closed": 1,
                    "closed_details": [{"net": "/DONE"}],
                    "refused_details": [],
                }}}},
                {"phases": {"close": {"completion": {
                    "refused_details": [refusal("/SS", "fresh")],
                }}}},
            ],
        }
        rows = repair.refusal_certificates(report)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["certificate"]["net"], "/SS")
        self.assertEqual(rows[0]["certificate"]["marker"], "fresh")

    def test_placement_only_wave_preserves_fresh_probe_for_next_wave(self):
        import cec_certificate_repair as repair

        detail = {
            "net": "/OPEN",
            "certificate": {
                "net": "/OPEN",
                "endpoints": [
                    {"kind": "pad", "ref": "U1", "pad": "1",
                     "x_mm": 1.0, "y_mm": 2.0},
                    {"kind": "trk", "uuid": "live", "x_mm": 3.0,
                     "y_mm": 4.0},
                ],
            },
        }
        report = {
            "final": {"unconn_nets": ["/OPEN"]},
            "plan": {
                "planning_refusal_evidence": {
                    "refused_details": [detail]},
                "live_refusal_probe": {
                    "error": "bounded probe timeout",
                    "refused_details": []},
            },
            "attempts": [{"stage": "footprint_relocation",
                          "decision": "candidate_exhausted"}],
        }

        rows = repair.refusal_certificates(report)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["certificate"]["net"], "/OPEN")
        self.assertEqual(rows[0]["certificate"]["endpoints"][1]["uuid"],
                         "live")

    def test_escape_corridor_promotes_low_hit_stub_on_cheapest_surface_ray(self):
        import cec_certificate_repair as repair

        certificate = {
            "layers": [{
                "layer": "F.Cu",
                "endpoint_escape": [{
                    "endpoint": "b",
                    "clear_rays": [],
                    "ray_details": [
                        {
                            "direction": "E",
                            "blockers": [
                                {"kind": "pad", "ref": "U1", "pad": "2"},
                                {"kind": "track", "uuid": "popular",
                                 "hit_count": 9},
                            ],
                        },
                        {
                            "direction": "S",
                            "blockers": [
                                {"kind": "track", "uuid": "short-stub",
                                 "hit_count": 1},
                            ],
                        },
                    ],
                }],
            }],
        }
        rows = repair._escape_corridor_blocker_rows(
            certificate, {"b": {"F.Cu"}}, {"b"})

        self.assertEqual([row["uuid"] for row in rows], ["short-stub"])
        self.assertTrue(rows[0]["escape_corridor"])

    def test_negotiation_schedule_gives_each_net_a_first_window(self):
        import cec_certificate_repair as repair

        def window(net, priority):
            return repair.NegotiationWindow(
                net=net, distance_mm=1.0, width_mm=0.2,
                clearance_mm=0.2, blocker_uuids=(net + str(priority),),
                blocker_nets=("/BLOCK",), blocker_hits=1,
                omitted_movable_blockers=0, fixed_blocker_hits=0,
                trapped_endpoints=0, endpoints=(), priority=(priority,))

        scheduled = repair._fair_negotiation_window_schedule([
            window("/I2C_SCL", 0), window("/I2C_SCL", 1),
            window("/I2C_SCL", 2), window("/VBUS_J5", 3),
        ], 3)

        self.assertEqual([row.net for row in scheduled],
                         ["/I2C_SCL", "/VBUS_J5", "/I2C_SCL"])

    def test_open_coupled_pairs_requires_both_members(self):
        import cec_certificate_repair as repair

        pairs = [
            {"name": "USB_D", "p": "/USB_D_P", "n": "/USB_D_N"},
            {"name": "CAN", "p": "/CAN_H", "n": "/CAN_L"},
        ]
        selected = repair._open_coupled_pairs(
            pairs, ["/USB_D_P", "/USB_D_N", "/CAN_H"])
        self.assertEqual([row["name"] for row in selected], ["USB_D"])

    def test_partial_coupled_pairs_selects_exactly_one_open_member(self):
        import cec_certificate_repair as repair

        pairs = [
            {"name": "USB_D", "p": "/USB_D_P", "n": "/USB_D_N"},
            {"name": "CAN_J1", "p": "/CAN_H_J1", "n": "/CAN_L_J1"},
            {"name": "CAN", "p": "/CAN_H", "n": "/CAN_L"},
        ]
        selected = repair._partial_open_coupled_pairs(
            pairs, ["/USB_D_P", "/USB_D_N", "/CAN_H_J1"])
        self.assertEqual([row["name"] for row in selected], ["CAN_J1"])

    def test_split_pair_support_swap_is_identical_bounded_and_polarity_driven(self):
        import pcbnew
        import cec_certificate_repair as repair

        board = pcbnew.CreateEmptyBoard()
        nets = {}
        for name in ("/PAIR_P", "/PAIR_N", "/UP_P", "/UP_N"):
            net = pcbnew.NETINFO_ITEM(board, name)
            board.Add(net)
            nets[name] = net

        def add_support(ref, pair_net, upstream_net, y):
            footprint = pcbnew.FOOTPRINT(board)
            footprint.SetReference(ref)
            footprint.SetValue("0R")
            footprint.SetPosition(pcbnew.VECTOR2I_MM(5.0, y))
            for number, net_name, x in (
                    ("1", pair_net, 5.0), ("2", upstream_net, 4.0)):
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
            return footprint

        p_support = add_support("R11", "/PAIR_P", "/UP_P", 9.8)
        n_support = add_support("R12", "/PAIR_N", "/UP_N", 10.2)
        for net_name, y in (("/UP_P", 9.8), ("/UP_N", 10.2)):
            track = pcbnew.PCB_TRACK(board)
            track.SetStart(pcbnew.VECTOR2I_MM(4.0, y))
            track.SetEnd(pcbnew.VECTOR2I_MM(2.0, y))
            track.SetWidth(pcbnew.FromMM(0.2))
            track.SetLayer(pcbnew.F_Cu)
            track.SetNet(nets[net_name])
            board.Add(track)
        terminal = pcbnew.FOOTPRINT(board)
        terminal.SetReference("J1")
        for number, net_name, y in (
                ("1", "/PAIR_P", 10.2), ("2", "/PAIR_N", 9.8)):
            pad = pcbnew.PAD(terminal)
            pad.SetPadName(number)
            pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetSize(pcbnew.VECTOR2I_MM(0.5, 0.5))
            pad.SetPosition(pcbnew.VECTOR2I_MM(20.0, y))
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            pad.SetLayerSet(pcbnew.PAD.SMDMask())
            pad.SetNet(nets[net_name])
            terminal.Add(pad)
        board.Add(terminal)
        pair = {"name": "PAIR", "p": "/PAIR_P", "n": "/PAIR_N",
                "width": 0.2, "gap": 0.2}

        changed, evidence = repair._swap_reversible_split_pair_station(
            board, pair)

        self.assertTrue(changed, evidence)
        self.assertEqual(evidence["displaced_nets"], ["/UP_N", "/UP_P"])
        self.assertEqual(evidence["removed_incident_tracks"], 2)
        self.assertEqual(len(evidence["preserved_anchors"]), 2)
        self.assertEqual(len(list(board.GetTracks())), 0)
        self.assertNotEqual(evidence["preferred_signs_before"]["start"],
                            evidence["preferred_signs_before"]["end"])
        self.assertEqual(evidence["preferred_signs_after"]["start"],
                         evidence["preferred_signs_after"]["end"])
        self.assertAlmostEqual(p_support.GetPosition().y / 1e6, 10.2)
        self.assertAlmostEqual(n_support.GetPosition().y / 1e6, 9.8)

    def test_coupled_pair_worker_saves_only_complete_atomic_route(self):
        import cec_certificate_repair as repair

        board = mock.Mock()
        route = mock.Mock(return_value={
            "pairs_ok": True,
            "critical_routes_ok": True,
            "pairs": {"routed": [{"name": "USB_D"}], "refused": []},
        })
        precision = SimpleNamespace(precision_route_board=route)
        with mock.patch.dict(sys.modules, {"cec_precision_route": precision}), \
                mock.patch.object(
                    repair.pcbnew, "LoadBoard", return_value=board), \
                mock.patch.object(repair.pcbnew, "SaveBoard") as save:
            changed, report = repair._coupled_pair_closure_worker(
                "trial.kicad_pcb", "USB_D", True)

        self.assertTrue(changed, report)
        save.assert_called_once_with("trial.kicad_pcb", board)
        self.assertEqual(route.call_args.kwargs["include_pair_names"],
                         {"USB_D"})
        self.assertTrue(route.call_args.kwargs["pair_grid"])

    def test_effort_budget_caps_stage_without_consuming_later_reserve(self):
        import cec_certificate_repair as repair

        budget = repair.RepairEffortBudget(
            max_attempts=4, wall_budget_s=60, started=10.0)
        with mock.patch.object(repair.time, "monotonic", return_value=10.0):
            self.assertTrue(budget.claim("drc", stage_limit=1))
            self.assertFalse(budget.claim("drc", stage_limit=1))
            self.assertTrue(budget.claim("negotiation", stage_limit=2))
        report = budget.report()
        self.assertEqual(report["attempts_started"], 2)
        self.assertEqual(report["stage_stops"]["drc"],
                         "stage_attempt_budget")
        self.assertIsNone(report["stop_reason"])

    def test_effort_budget_stops_the_whole_ladder_at_wall_limit(self):
        import cec_certificate_repair as repair

        budget = repair.RepairEffortBudget(
            max_attempts=10, wall_budget_s=5, started=10.0)
        with mock.patch.object(repair.time, "monotonic", return_value=15.1):
            self.assertFalse(budget.claim("via", stage_limit=4))
        report = budget.report()
        self.assertEqual(report["stop_reason"], "wall_budget")
        self.assertEqual(report["stop_stage"], "via")
        self.assertEqual(report["attempts_started"], 0)

    def test_effort_budget_reserve_stops_only_early_stage(self):
        import cec_certificate_repair as repair

        budget = repair.RepairEffortBudget(
            max_attempts=10, wall_budget_s=100, started=10.0,
            attempts_started=7)
        with mock.patch.object(repair.time, "monotonic", return_value=75.0):
            self.assertFalse(budget.claim_before_reserve(
                "canonical", reserve_wall_s=30, reserve_attempts=2,
                trial_wall_s=6))
            self.assertTrue(budget.claim("negotiation", stage_limit=2))
        report = budget.report()
        self.assertEqual(report["stage_stops"]["canonical"],
                         "later_stage_wall_reserve")
        self.assertIsNone(report["stop_reason"])
        self.assertEqual(report["stage_attempts"]["negotiation"], 1)

    def test_effort_budget_attempt_reserve_preserves_later_claim(self):
        import cec_certificate_repair as repair

        budget = repair.RepairEffortBudget(
            max_attempts=4, wall_budget_s=100, started=10.0,
            attempts_started=2)
        with mock.patch.object(repair.time, "monotonic", return_value=10.0):
            self.assertFalse(budget.claim_before_reserve(
                "canonical", reserve_attempts=2))
            self.assertTrue(budget.claim("negotiation", stage_limit=2))
        self.assertEqual(
            budget.report()["stage_stops"]["canonical"],
            "later_stage_attempt_reserve")

    def test_atomic_close_timeout_is_smaller_than_transaction_allowance(self):
        import cec_certificate_repair as repair

        with mock.patch.dict(
                os.environ,
                {"CEC_CERTIFICATE_NEGOTIATION_TIMEOUT_S": "90",
                 "CEC_CERTIFICATE_NEGOTIATION_CLOSE_TIMEOUT_S": "25"},
                clear=False):
            self.assertEqual(repair._atomic_close_timeout_s(12, 4.0), 25.0)
            self.assertEqual(repair._atomic_close_timeout_s(24, 12.0), 45.0)
            self.assertEqual(
                repair._atomic_negotiation_timeout_s(12, 4.0), 90.0)

    def test_live_probe_budget_reserves_transaction_time(self):
        import cec_certificate_repair as repair

        self.assertEqual(repair._live_probe_budget_s(60, 60, 90), 12.0)
        self.assertEqual(repair._live_probe_budget_s(240, 15, 90), 15.0)
        self.assertEqual(repair._live_probe_budget_s(10, 60, 90), 4.0)

    def test_placement_restoration_budget_preserves_wave_breadth(self):
        import cec_certificate_repair as repair

        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                repair._placement_restoration_timeout_s(1), 25.0)
            self.assertEqual(
                repair._placement_restoration_timeout_s(20), 45.0)
        with mock.patch.dict(
                os.environ,
                {"CEC_CERTIFICATE_PLACEMENT_RESTORE_TIMEOUT_S": "40"},
                clear=True):
            self.assertEqual(
                repair._placement_restoration_timeout_s(1), 40.0)
        with mock.patch.dict(
                os.environ,
                {"CEC_CERTIFICATE_PLACEMENT_RESTORE_TIMEOUT_S": "invalid"},
                clear=True):
            self.assertEqual(
                repair._placement_restoration_timeout_s(1), 25.0)

    def test_prior_target_close_precedes_untried_and_timeout_windows(self):
        import cec_certificate_repair as repair

        windows = [
            {"net": "/TIMEOUT", "priority": [0]},
            {"net": "/UNTRIED", "priority": [1]},
            {"net": "/PROVEN", "priority": [2]},
        ]
        prior = {
            "algorithm_revision": repair.REPAIR_ALGORITHM_REVISION,
            "attempts": [
            {"stage": "atomic_negotiation",
             "window": {"net": "/TIMEOUT"},
             "decision": "blocked_net_search_timeout",
             "phases": {"close": {"completion": {"timed_out": True}}}},
            {"stage": "atomic_negotiation",
             "window": {"net": "/PROVEN"},
             "decision": "drc_regressed",
             "phases": {"close": {"completion": {"closed": 2}}}},
        ]}

        ordered, evidence = repair._prioritize_windows_by_proven_close(
            windows, prior)

        self.assertEqual([row["net"] for row in ordered],
                         ["/PROVEN", "/UNTRIED", "/TIMEOUT"])
        self.assertEqual(evidence["proven_close_nets"], ["/PROVEN"])

    def test_prior_schedule_evidence_survives_bounded_wave(self):
        import cec_certificate_repair as repair

        prior = {
            "algorithm_revision": repair.REPAIR_ALGORITHM_REVISION,
            "plan": {"negotiation": {"prior_schedule_evidence": {
                "algorithm_revision": repair.REPAIR_ALGORITHM_REVISION,
                "policy": "proven_close_then_untried_then_prior_timeout",
                "proven_close_nets": ["/PROVEN"],
                "timed_out_nets": ["/TIMEOUT"],
            }}}}
        windows = [
            {"net": "/TIMEOUT", "priority": [0]},
            {"net": "/PROVEN", "priority": [1]},
        ]

        ordered, evidence = repair._prioritize_windows_by_proven_close(
            windows, prior)

        self.assertEqual([row["net"] for row in ordered],
                         ["/PROVEN", "/TIMEOUT"])
        self.assertEqual(evidence["proven_close_nets"], ["/PROVEN"])

    def test_prior_route_plateau_is_invalidated_by_algorithm_revision(self):
        import cec_certificate_repair as repair

        prior = {
            "algorithm_revision": "older-router",
            "attempts": [{
                "stage": "atomic_negotiation",
                "window": {"net": "/TIMEOUT"},
                "decision": "blocked_net_search_timeout",
                "phases": {"close": {"completion": {"timed_out": True}}},
            }],
        }
        windows = [
            {"net": "/TIMEOUT", "priority": [0]},
            {"net": "/UNTRIED", "priority": [1]},
        ]

        ordered, evidence = repair._prioritize_windows_by_proven_close(
            windows, prior)

        self.assertEqual([row["net"] for row in ordered],
                         ["/TIMEOUT", "/UNTRIED"])
        self.assertEqual(evidence["timed_out_nets"], [])

    def test_footprint_candidate_cap_is_per_certified_target(self):
        import cec_certificate_repair as repair

        budget = repair.RepairEffortBudget(
            max_attempts=4, wall_budget_s=60, started=10.0)
        row = repair.asdict(repair.FootprintRepairTarget(
            ref="R1", target_net="/OPEN", endpoint_ref="U1",
            endpoint_pad="1", endpoint_x_mm=1.0, endpoint_y_mm=1.0,
            hit_count=1, distance_mm=2.0, priority=(0,),
            motion="toward_endpoint"))
        with mock.patch.object(repair.time, "monotonic", return_value=10.0), \
                mock.patch.object(
                    repair, "_footprint_relocation_candidates",
                    return_value=[{"rotation_delta_deg": 0.0,
                                   "dx_mm": 0.0, "dy_mm": 0.0}]), \
                mock.patch.object(repair, "_copy_board_family"), \
                mock.patch.object(
                    repair, "_spawn_apply",
                    return_value=(False, {"refusal": "test"})):
            first = repair._attempt_footprint_relocation(
                "board.kicad_pcb", {}, row, work_dir="/tmp", token="00",
                effort=budget, max_candidates=1)
            second = repair._attempt_footprint_relocation(
                "board.kicad_pcb", {}, row, work_dir="/tmp", token="01",
                effort=budget, max_candidates=1)

        self.assertEqual(len(first["attempts"]), 1)
        self.assertEqual(len(second["attempts"]), 1)
        self.assertEqual(first["attempts"][0]["elapsed_s"], 0.0)
        self.assertEqual(second["attempts"][0]["elapsed_s"], 0.0)
        self.assertEqual(budget.report()["attempts_started"], 2)

    def test_pose_local_restoration_timeout_is_consumed_not_retried(self):
        import cec_certificate_repair as repair

        target = repair.asdict(repair.FootprintRepairTarget(
            ref="C1", target_net="/OPEN", endpoint_ref="U1",
            endpoint_pad="1", endpoint_x_mm=1.0, endpoint_y_mm=1.0,
            hit_count=1, distance_mm=2.0, priority=(0,),
            motion="toward_endpoint"))
        candidate = {"rotation_delta_deg": 180.0,
                     "dx_mm": 0.5, "dy_mm": 0.0}
        classify_calls = 0

        def fake_spawn(func, _args, **_kwargs):
            nonlocal classify_calls
            if func is repair._relocate_footprint_worker:
                return True, {"affected_nets": ["/OPEN", "/SIDE"]}
            if func is repair._refill_worker:
                return True
            if func is repair._classify_placement_conflicts_worker:
                classify_calls += 1
                if classify_calls == 1:
                    return {"fixed_conflict_count": 0,
                            "movable_track_uuids": ["track-1"],
                            "movable_via_targets": []}
                return {"fixed_conflict_count": 0,
                        "movable_track_uuids": [],
                        "movable_via_targets": []}
            if func is repair._score_worker:
                return {}
            if func is repair._evacuate_placement_copper_worker:
                return True, {"removed": 1}, [{"net": "/SIDE"}]
            if func is repair._exact_relocated_connections_worker:
                return {"target_closed": True,
                        "support_closed_nets": ["/SIDE"],
                        "refused": []}
            if func is repair._restore_negotiation_worker:
                raise repair.cec_process_pool.WorkerPoolStalled(
                    "pose replay budget")
            self.fail("unexpected worker %s" % func.__name__)

        def fake_drc(_board, destination):
            Path(destination).write_text(
                '{"violations": []}', encoding="utf-8")
            return {"violations": []}

        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(repair, "_copy_board_family"), \
                mock.patch.object(repair, "_run_drc",
                                  side_effect=fake_drc), \
                mock.patch.object(repair, "_spawn_apply",
                                  side_effect=fake_spawn), \
                mock.patch.object(
                    repair, "_placement_preflight_accepts",
                    side_effect=[
                        (False, "placement_preflight_drc_regressed",
                         ["fault"]),
                        (True, "placement_preflight_clear", []),
                    ]):
            result = repair._attempt_footprint_relocation(
                "board.kicad_pcb", {}, target, work_dir=directory,
                token="bounded", max_candidates=1,
                candidate_override=(candidate,))

        self.assertFalse(result["adopted"])
        attempt = result["attempts"][0]
        self.assertEqual(
            attempt["decision"],
            "placement_copper_restoration_timeout")
        self.assertEqual(
            attempt["placement_copper_restoration"]["refusal"],
            "placement_restoration_budget_exhausted")
        self.assertGreaterEqual(attempt["elapsed_s"], 0.0)

    def test_alternate_placement_route_order_requires_composite_closure(self):
        import cec_certificate_repair as repair

        calls = []

        def fake_spawn(func, _args, **_kwargs):
            calls.append(func)
            if func is repair._restore_negotiation_worker:
                return True, {"stage": "restore_blockers", "restored": [
                    {"net": "/SIDE", "mode": "network_lastmile"}]}
            if func is repair._exact_relocated_connections_worker:
                return {"target_closed": True, "closed": 1,
                        "support_closed_nets": ["/SIDE"]}
            self.fail("unexpected worker %s" % func.__name__)

        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(repair, "_copy_board_family") as copy, \
                mock.patch.object(repair, "_spawn_apply",
                                  side_effect=fake_spawn):
            accepted, evidence, exact = \
                repair._attempt_alternate_placement_route_order(
                    "before-target.kicad_pcb", "trial.kicad_pcb",
                    [{"net": "/SIDE"}], {"target_net": "/OPEN"},
                    {"affected_nets": ["/OPEN", "/SIDE"]},
                    work_dir=directory, token="order",
                    restoration_timeout_s=25.0)

        self.assertTrue(accepted)
        self.assertTrue(exact["target_closed"])
        self.assertEqual(evidence["decision"],
                         "alternate_order_composite_closed")
        self.assertEqual(calls, [
            repair._restore_negotiation_worker,
            repair._exact_relocated_connections_worker,
        ])
        self.assertEqual(copy.call_count, 2)

    def test_alternate_placement_route_order_rejects_target_failure(self):
        import cec_certificate_repair as repair

        def fake_spawn(func, _args, **_kwargs):
            if func is repair._restore_negotiation_worker:
                return True, {"stage": "restore_blockers"}
            if func is repair._exact_relocated_connections_worker:
                return {"target_closed": False, "refused": [
                    {"net": "/OPEN"}]}
            self.fail("unexpected worker %s" % func.__name__)

        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(repair, "_copy_board_family") as copy, \
                mock.patch.object(repair, "_spawn_apply",
                                  side_effect=fake_spawn):
            accepted, evidence, exact = \
                repair._attempt_alternate_placement_route_order(
                    "before-target.kicad_pcb", "trial.kicad_pcb",
                    [{"net": "/SIDE"}], {"target_net": "/OPEN"}, {},
                    work_dir=directory, token="order",
                    restoration_timeout_s=25.0)

        self.assertFalse(accepted)
        self.assertFalse(exact["target_closed"])
        self.assertEqual(evidence["decision"],
                         "alternate_target_still_refused")
        self.assertEqual(copy.call_count, 1)

    def test_via_move_retargets_only_exact_same_net_anchor(self):
        import cec_certificate_repair as repair

        anchors, evidence = \
            repair._retarget_preserved_anchors_for_via_move([
                {"ref": "R19", "pad": "2", "net": "/STRAP",
                 "x_mm": 22.3512, "y_mm": 22.04},
                {"ref": "R20", "pad": "2", "net": "/OTHER",
                 "x_mm": 22.3512, "y_mm": 22.04},
                {"ref": "R21", "pad": "2", "net": "/STRAP",
                 "x_mm": 22.36, "y_mm": 22.04},
            ], net="/STRAP", via_uuid="via-1",
                old_mm=[22.3512, 22.04], new_mm=[20.9512, 22.04])

        self.assertEqual((anchors[0]["x_mm"], anchors[0]["y_mm"]),
                         (20.9512, 22.04))
        self.assertEqual(anchors[0]["anchor_via_uuid"], "via-1")
        self.assertEqual((anchors[1]["x_mm"], anchors[1]["y_mm"]),
                         (22.3512, 22.04))
        self.assertEqual((anchors[2]["x_mm"], anchors[2]["y_mm"]),
                         (22.36, 22.04))
        self.assertEqual(len(evidence), 1)

    def test_via_move_with_invalid_geometry_preserves_anchors(self):
        import cec_certificate_repair as repair

        source = [{"net": "/STRAP", "x_mm": 1.0, "y_mm": 2.0}]
        anchors, evidence = \
            repair._retarget_preserved_anchors_for_via_move(
                source, net="/STRAP", via_uuid="via-1",
                old_mm=[], new_mm=[3.0, 4.0])

        self.assertEqual(anchors, source)
        self.assertEqual(evidence, [])

    def test_placement_via_ladder_interleaves_owner_and_escape_radii(self):
        import cec_certificate_repair as repair

        target = repair.ViaRepairTarget(
            uuid="via-1", net="/STRAP", x_nm=0, y_nm=0,
            diameter_nm=350000, drill_nm=250000,
            counterpart_uuids=(), drc_types=("clearance",),
            away_dx=-1, away_dy=0, priority=(0,))
        rows = list(repair._placement_via_offset_candidates(
            target, owner_directions=((1, -1),)))[:8]

        self.assertEqual([row[3] for row in rows], [
            (1, -1), (-1, 0), (1, -1), (-1, 0),
            (1, -1), (-1, 0), (1, -1), (-1, 0),
        ])
        self.assertEqual([row[2] for row in rows], [
            0.20, 0.20, 0.45, 0.45, 0.80, 0.80, 1.40, 1.40,
        ])

    def test_placement_preflight_ignores_expected_opens_but_not_new_faults(self):
        import cec_certificate_repair as repair

        before = {
            "unconnected": 2,
            "structural_drc_identities": [
                '["clearance","uuid",["old"]]'],
            "diffpair_ok": True,
            "kelvin_ok": True,
            "route_topology_fault_nets": [],
        }
        open_only = {
            **before,
            "unconnected": 19,
        }
        self.assertEqual(
            repair._placement_preflight_accepts(before, open_only),
            (True, "placement_preflight_clear", []))

        collision = {
            **open_only,
            "structural_drc_identities": [
                '["clearance","uuid",["old"]]',
                '["shorting_items","uuid",["new-short"]]'],
        }
        self.assertEqual(
            repair._placement_preflight_accepts(before, collision),
            (False, "placement_preflight_drc_regressed",
             ['["shorting_items","uuid",["new-short"]]']))

        transient_route_state = {
            **open_only,
            "diffpair_ok": False,
            "kelvin_ok": False,
            "route_topology_fault_nets": ["/MOVED"],
            "structural_drc_identities": [
                '["clearance","uuid",["old"]]',
                '["track_dangling","uuid",["removed-branch"]]'],
        }
        self.assertEqual(
            repair._placement_preflight_accepts(before, transient_route_state),
            (True, "placement_preflight_clear", []))

    def test_close_negotiation_can_enumerate_surface_first_topology(self):
        import cec_certificate_repair as repair

        window = repair.NegotiationWindow(
            net="/OPEN", distance_mm=2.0, width_mm=0.25,
            clearance_mm=0.2, blocker_uuids=("blocker",),
            blocker_nets=("/BLOCK",), blocker_hits=4,
            omitted_movable_blockers=0, fixed_blocker_hits=0,
            trapped_endpoints=0, endpoints=(), priority=(0,),
            unlock_uuids=("blocker",), local_pin_escape=True)
        board = mock.Mock()
        with mock.patch.object(
                repair.cec_fr, "_project_netclass_resolver",
                return_value=lambda _net: {}), \
                mock.patch.object(
                    repair.cec_fr, "synthesize_lastmile",
                    return_value={"closed": 1}) as synthesize:
            changed, evidence = repair._close_negotiation_target(
                board, window, board_path="board.kicad_pcb",
                attempt_budget=12, maze_margin_mm=4.0,
                prefer_bridge=False)

        self.assertTrue(changed, evidence)
        self.assertFalse(synthesize.call_args.kwargs["prefer_bridge"])

    def test_atomic_negotiation_orders_surface_before_optional_bridge(self):
        import cec_certificate_repair as repair

        base = dict(
            net="/OPEN", distance_mm=2.0, width_mm=0.25,
            clearance_mm=0.2, blocker_uuids=("blocker",),
            blocker_nets=("/BLOCK",), blocker_hits=4,
            omitted_movable_blockers=0, fixed_blocker_hits=0,
            trapped_endpoints=0, endpoints=(), priority=(0,),
            unlock_uuids=("blocker",))
        local = repair.NegotiationWindow(**base, local_pin_escape=True)
        ordinary = repair.NegotiationWindow(**base, local_pin_escape=False)

        self.assertEqual(
            repair._atomic_negotiation_variants(local, False),
            [(12, 4.0, 2, False), (12, 4.0, 2, True)])
        self.assertEqual(
            repair._atomic_negotiation_variants(ordinary, False),
            [(12, 4.0, 2, False)])

    def test_close_negotiation_keeps_power_trunk_width_out_of_escape_floor(self):
        import cec_certificate_repair as repair

        window = repair.NegotiationWindow(
            net="+3V3", distance_mm=1.5, width_mm=0.50,
            clearance_mm=0.2, blocker_uuids=("blocker",),
            blocker_nets=("/BLOCK",), blocker_hits=2,
            omitted_movable_blockers=0, fixed_blocker_hits=0,
            trapped_endpoints=0, endpoints=(), priority=(0,),
            unlock_uuids=(), local_pin_escape=True)
        board = mock.Mock()
        with mock.patch.object(
                repair.cec_fr, "_project_netclass_resolver",
                return_value=lambda _net: {}), \
                mock.patch.object(
                    repair.cec_fr, "synthesize_lastmile",
                    return_value={"closed": 1}) as synthesize:
            changed, evidence = repair._close_negotiation_target(
                board, window, board_path="board.kicad_pcb",
                attempt_budget=12, maze_margin_mm=4.0)

        self.assertTrue(changed, evidence)
        self.assertEqual(synthesize.call_args.kwargs["min_w"], 0.25)
        self.assertEqual(synthesize.call_args.kwargs["clearance"], 0.0)
        self.assertTrue(synthesize.call_args.kwargs["prefer_bridge"])

    def test_atomic_negotiation_accepts_proven_redundant_blocker_prune(self):
        import cec_certificate_repair as repair

        window = repair.NegotiationWindow(
            net="/OPEN", distance_mm=2.0, width_mm=0.25,
            clearance_mm=0.2, blocker_uuids=("blocker",),
            blocker_nets=("+3V3",), blocker_hits=4,
            omitted_movable_blockers=0, fixed_blocker_hits=0,
            trapped_endpoints=0, endpoints=(), priority=(0,))
        before = {
            "drc": 0, "unconnected": 2,
            "unconn_nets": ["/KEEP", "/OPEN"],
            "structural_drc_identities": [],
            "kelvin_topology_faults": [],
            "route_topology_fault_nets": [],
            "kelvin_ok": True, "diffpair_ok": True,
        }
        after = {**before, "unconnected": 1,
                 "unconn_nets": ["/KEEP"]}
        calls = []

        def fake_spawn(func, args, **_kwargs):
            calls.append(func)
            if func is repair._remove_negotiation_worker:
                return True, {"stage": "remove_blockers"}, [{"saved": True}]
            if func is repair._close_negotiation_worker:
                return True, {"stage": "close_blocked_net"}
            if func is repair._refill_worker:
                return True
            if func is repair._drc_dangling_cleanup_worker:
                return False, {"stop": "settled", "removed_count": 0}
            if func is repair._score_worker:
                return after
            self.fail("unexpected worker %s" % func.__name__)

        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(repair, "_copy_board_family"), \
                mock.patch.object(repair, "_run_drc", return_value={}), \
                mock.patch.object(repair, "_spawn_apply",
                                  side_effect=fake_spawn):
            result = repair._attempt_atomic_negotiation(
                os.path.join(directory, "board.kicad_pcb"), before,
                repair.asdict(window), work_dir=directory, token="test",
                deep_retry=False, max_detour_ratio=2.0)

        self.assertTrue(result["adopted"], result)
        accepted = result["accepted"]
        self.assertEqual(accepted["decision"],
                         "strict_structural_improvement")
        self.assertTrue(accepted["phases"][
            "redundant_blocker_prune"]["accepted"])
        self.assertNotIn(repair._restore_negotiation_worker, calls)

    def test_atomic_negotiation_expands_long_corridor_before_anchor_depth(self):
        import cec_certificate_repair as repair

        window = repair.NegotiationWindow(
            net="/OPEN", distance_mm=38.0, width_mm=0.5,
            clearance_mm=0.2, blocker_uuids=("blocker",),
            blocker_nets=("/BLOCK",), blocker_hits=4,
            omitted_movable_blockers=0, fixed_blocker_hits=2,
            trapped_endpoints=0, endpoints=(), priority=(0,))
        before = {
            "drc": 0, "unconnected": 1, "unconn_nets": ["/OPEN"],
            "structural_drc_identities": [], "kelvin_topology_faults": [],
            "route_topology_fault_nets": [], "kelvin_ok": True,
            "diffpair_ok": True,
        }
        after = {**before, "unconnected": 0, "unconn_nets": []}
        close_args = []

        def fake_spawn(func, args, **_kwargs):
            if func is repair._remove_negotiation_worker:
                return True, {"stage": "remove_blockers"}, [{"saved": True}]
            if func is repair._close_negotiation_worker:
                close_args.append(args)
                if len(close_args) < 3:
                    return False, {"refusal": "bounded"}
                return True, {"stage": "close_blocked_net"}
            if func is repair._refill_worker:
                return True
            if func is repair._drc_dangling_cleanup_worker:
                return False, {"stop": "settled", "removed_count": 0}
            if func is repair._score_worker:
                return after
            self.fail("unexpected worker %s" % func.__name__)

        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(repair, "_copy_board_family"), \
                mock.patch.object(repair, "_run_drc", return_value={}), \
                mock.patch.object(repair, "_spawn_apply",
                                  side_effect=fake_spawn):
            result = repair._attempt_atomic_negotiation(
                os.path.join(directory, "board.kicad_pcb"), before,
                repair.asdict(window), work_dir=directory, token="breadth",
                deep_retry=True, max_detour_ratio=2.0)

        self.assertTrue(result["adopted"], result)
        self.assertEqual(close_args[0][2:4], (12, 4.0))
        self.assertEqual(close_args[1][2:4], (1, 20.0))
        self.assertEqual(close_args[2][2:4], (4, 25.0))

    def test_atomic_negotiation_can_reroute_displaced_nets_as_a_set(self):
        import cec_certificate_repair as repair

        window = repair.NegotiationWindow(
            net="/OPEN", distance_mm=3.0, width_mm=0.25,
            clearance_mm=0.2, blocker_uuids=("blocker",),
            blocker_nets=("/MOVE",), blocker_hits=4,
            omitted_movable_blockers=0, fixed_blocker_hits=0,
            trapped_endpoints=0, endpoints=(), priority=(0,))
        before = {
            "drc": 0, "unconnected": 2,
            "unconn_nets": ["/KEEP", "/OPEN"],
            "structural_drc_identities": [],
            "kelvin_topology_faults": [],
            "route_topology_fault_nets": [],
            "kelvin_ok": True, "diffpair_ok": True,
        }
        pruned = {**before, "unconnected": 3,
                  "unconn_nets": ["/KEEP", "/MOVE", "/OPEN"]}
        improved = {**before, "unconnected": 1,
                    "unconn_nets": ["/KEEP"]}
        score_rows = iter((pruned, improved))
        calls = []

        def fake_spawn(func, args, **_kwargs):
            calls.append((func, args))
            if func is repair._remove_negotiation_worker:
                return True, {"stage": "remove_blockers"}, [
                    {"net": "/MOVE", "saved": True}]
            if func is repair._close_negotiation_worker:
                return True, {"stage": "close_blocked_net"}
            if func is repair._restore_negotiation_worker:
                return False, {"refusal": "displaced_net_unrestorable"}
            if func is repair._lastmile_worker:
                self.assertEqual(args[1], ("/MOVE",))
                return {"closed": 1, "refused": 0}
            if func is repair._refill_worker:
                return True
            if func is repair._drc_dangling_cleanup_worker:
                return False, {"stop": "settled", "removed_count": 0}
            if func is repair._score_worker:
                return next(score_rows)
            self.fail("unexpected worker %s" % func.__name__)

        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(repair, "_copy_board_family"), \
                mock.patch.object(repair, "_run_drc", return_value={}), \
                mock.patch.object(repair, "_spawn_apply",
                                  side_effect=fake_spawn):
            result = repair._attempt_atomic_negotiation(
                os.path.join(directory, "board.kicad_pcb"), before,
                repair.asdict(window), work_dir=directory, token="fallback",
                deep_retry=False, max_detour_ratio=2.0)

        self.assertTrue(result["adopted"], result)
        accepted = result["accepted"]
        fallback = accepted["phases"]["displaced_net_completion"]
        self.assertTrue(fallback["accepted"], fallback)
        self.assertEqual(fallback["nets"], ["/MOVE"])

    def test_restore_skips_track_fragment_wholly_inside_same_pad(self):
        import pcbnew
        import cec_certificate_repair as repair

        board = pcbnew.CreateEmptyBoard()
        net = pcbnew.NETINFO_ITEM(board, "GND")
        board.Add(net)
        footprint = pcbnew.FOOTPRINT(board)
        footprint.SetReference("C1")
        pad = pcbnew.PAD(footprint)
        pad.SetPadName("2")
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(pcbnew.VECTOR2I_MM(1.0, 1.5))
        pad.SetPosition(pcbnew.VECTOR2I_MM(5.0, 5.0))
        pad.SetLayerSet(pcbnew.PAD.SMDMask())
        pad.SetNet(net)
        footprint.Add(pad)
        board.Add(footprint)
        snapshot = {
            "requested_uuid": "pad-internal",
            "removed_uuids": ("pad-internal",),
            "net": "GND", "net_code": net.GetNetCode(),
            "layer": pcbnew.F_Cu, "width": pcbnew.FromMM(0.5),
            "start": pcbnew.VECTOR2I_MM(5.0, 4.6),
            "end": pcbnew.VECTOR2I_MM(5.0, 5.4),
            "start_escape": None, "end_escape": None,
            "source_length_nm": pcbnew.FromMM(0.8),
            "relock": True, "endpoint_neckdown_group": False,
        }

        with mock.patch.object(
                repair.cec_fr, "_project_netclass_resolver",
                return_value=lambda _net: {}):
            changed, evidence = repair._restore_displaced_branch(
                board, snapshot, board_path="board.kicad_pcb",
                maze_margin_mm=4.0)

        self.assertTrue(changed, evidence)
        self.assertEqual(evidence["mode"], "same_pad_redundant")
        self.assertEqual(evidence["anchor"], {
            "ref": "C1", "pad": "2", "layer": "F.Cu"})
        self.assertEqual(len(list(board.GetTracks())), 0)

    def test_negotiation_coalesces_certificate_named_duplicate_tracks(self):
        import pcbnew
        import cec_certificate_repair as repair

        board = pcbnew.CreateEmptyBoard()
        blocked = pcbnew.NETINFO_ITEM(board, "/OPEN")
        blocker = pcbnew.NETINFO_ITEM(board, "/BLOCK")
        board.Add(blocked)
        board.Add(blocker)

        def track():
            item = pcbnew.PCB_TRACK(board)
            item.SetStart(pcbnew.VECTOR2I_MM(2, 3))
            item.SetEnd(pcbnew.VECTOR2I_MM(7, 3))
            item.SetWidth(pcbnew.FromMM(0.2))
            item.SetLayer(pcbnew.F_Cu)
            item.SetNet(blocker)
            board.Add(item)
            return item

        first, second = track(), track()
        ids = (repair._uuid(first), repair._uuid(second))
        window = repair.NegotiationWindow(
            net="/OPEN", distance_mm=5.0, width_mm=0.2,
            clearance_mm=0.2, blocker_uuids=ids,
            blocker_nets=("/BLOCK", "/BLOCK"), blocker_hits=2,
            omitted_movable_blockers=0, fixed_blocker_hits=0,
            trapped_endpoints=0, endpoints=(), priority=(0,))

        changed, evidence, snapshots = \
            repair._remove_negotiation_blockers(board, window)

        self.assertTrue(changed, evidence)
        self.assertEqual(evidence["removed_tracks"], 2)
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(set(snapshots[0]["removed_uuids"]), set(ids))
        self.assertEqual(snapshots[0]["source_length_nm"],
                         pcbnew.FromMM(5.0))
        self.assertEqual(len(list(board.GetTracks())), 0)

    def test_drc_dangling_cleanup_follows_exact_uuid_cascade(self):
        import pcbnew
        import cec_certificate_repair as repair

        board = pcbnew.CreateEmptyBoard()
        net = pcbnew.NETINFO_ITEM(board, "/GPIO")
        board.Add(net)

        def track(x0, x1):
            item = pcbnew.PCB_TRACK(board)
            item.SetStart(pcbnew.VECTOR2I_MM(x0, 2))
            item.SetEnd(pcbnew.VECTOR2I_MM(x1, 2))
            item.SetWidth(pcbnew.FromMM(0.25))
            item.SetLayer(pcbnew.F_Cu)
            item.SetNet(net)
            item.SetLocked(True)
            board.Add(item)
            return item

        first = track(1, 2)
        second = track(2, 3)
        innocent = track(6, 7)
        first_id = repair._uuid(first)
        second_id = repair._uuid(second)
        innocent_id = repair._uuid(innocent)
        reports = [
            {"violations": [{"type": "track_dangling", "items": [{
                "description": "Track [/GPIO] on F.Cu", "uuid": first_id}]}]},
            {"violations": [{"type": "track_dangling", "items": [{
                "description": "Track [/GPIO] on F.Cu", "uuid": second_id}]}]},
            {"violations": []},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "dangling.kicad_pcb")
            pcbnew.SaveBoard(path, board)
            with mock.patch.object(repair, "_run_drc",
                                   side_effect=reports):
                changed, evidence = repair._drc_dangling_cleanup_worker(path)
            saved = pcbnew.LoadBoard(path)
        remaining = {repair._uuid(item) for item in saved.GetTracks()}
        self.assertTrue(changed)
        self.assertEqual(evidence["stop"], "settled")
        self.assertEqual(evidence["removed_count"], 2)
        self.assertNotIn(first_id, remaining)
        self.assertNotIn(second_id, remaining)
        self.assertIn(innocent_id, remaining)

    def test_board_family_copy_preserves_executable_route_sidecars(self):
        import cec_certificate_repair as repair

        with tempfile.TemporaryDirectory() as directory:
            source = os.path.join(directory, "source.kicad_pcb")
            destination = os.path.join(directory, "trial.kicad_pcb")
            with open(source, "w", encoding="utf-8") as handle:
                handle.write("(kicad_pcb (version 20240108))\n")
            with open(source[:-len(".kicad_pcb")] + ".kicad_pro", "w",
                      encoding="utf-8") as handle:
                json.dump({"meta": {"filename": "source.kicad_pro"}},
                          handle)
            for suffix in (".pourplan.json", ".railreport.json",
                           ".pourfirst-state.json"):
                with open(source[:-len(".kicad_pcb")] + suffix, "w",
                          encoding="utf-8") as handle:
                    json.dump({"source": suffix}, handle)

            repair._copy_board_family(source, destination)

            for suffix in (".kicad_pro", ".pourplan.json",
                           ".railreport.json", ".pourfirst-state.json"):
                self.assertTrue(os.path.isfile(
                    destination[:-len(".kicad_pcb")] + suffix), suffix)

    def test_completion_payload_deduplicates_certificates(self):
        import cec_certificate_repair as repair

        cert = {"schema": 1, "net": "/OPEN", "endpoints": [],
                "dominant_blockers": []}
        detail = {"net": "/OPEN", "distance_mm": 2.0,
                  "certificate": cert}
        payload = {"completion_report": {
            "lastmile": {"refused_details": [detail]},
            "final_completion": {"refused_details": [detail]}}}
        rows = repair.refusal_certificates(payload)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["certificate"]["net"], "/OPEN")

    def test_trapped_endpoint_promotes_only_foreign_pad_blockers(self):
        import cec_certificate_repair as repair

        payload = {"unconn_nets": ["/SS"], "final_completion": {
            "refused_details": [{
                "net": "/SS", "distance_mm": 8.0,
                "certificate": {
                    "net": "/SS",
                    "endpoints": [{
                        "endpoint": "b", "kind": "pad", "ref": "U4",
                        "pad": "11", "x_mm": 7.0, "y_mm": 12.0,
                    }],
                    "layers": [{"layer": "F.Cu", "endpoint_escape": [{
                        "endpoint": "b", "clear_rays": [],
                        "ray_details": [{
                            "status": "foreign_copper_blocked",
                            "blockers": [
                                {"kind": "pad", "ref": "U4", "pad": "10"},
                                {"kind": "pad", "ref": "C6", "pad": "1"},
                            ],
                        }, {
                            "status": "foreign_copper_blocked",
                            "blockers": [{"kind": "pad", "ref": "C6",
                                          "pad": "1"}],
                        }],
                    }]}],
                },
            }],
        }}
        rows = repair._trapped_foreign_pad_blockers(payload)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["ref"], "C6")
        self.assertEqual(rows[0]["hit_count"], 2)
        self.assertEqual(rows[0]["endpoint_ref"], "U4")

    def test_footprint_blocker_is_suppressed_when_another_layer_escapes(self):
        import cec_certificate_repair as repair

        blocked = {
            "endpoint": "b", "clear_rays": [],
            "ray_details": [{
                "status": "foreign_copper_blocked",
                "blockers": [{"kind": "pad", "ref": "C6"}],
            }],
        }
        payload = {"final_completion": {"refused_details": [{
            "net": "/SS", "distance_mm": 8.0,
            "certificate": {
                "net": "/SS",
                "endpoints": [{
                    "endpoint": "b", "kind": "pad", "ref": "U4",
                    "pad": "11", "x_mm": 7.0, "y_mm": 12.0,
                }],
                "layers": [
                    {"layer": "F.Cu", "endpoint_escape": [blocked]},
                    {"layer": "SIG2", "endpoint_escape": [{
                        "endpoint": "b", "clear_rays": ["N"],
                        "ray_details": [],
                    }]},
                ],
            },
        }]}}
        self.assertEqual(repair._trapped_foreign_pad_blockers(payload), [])

    def test_footprint_plan_admits_only_small_unlocked_smd_support(self):
        import cec_certificate_repair as repair

        def pad(net):
            return mock.Mock(IsOnCopperLayer=mock.Mock(return_value=True),
                             HasHole=mock.Mock(return_value=False),
                             GetNetCode=mock.Mock(return_value=net))

        cap = mock.Mock()
        cap.GetReference.return_value = "C6"
        cap.IsLocked.return_value = False
        cap.Pads.return_value = [pad(1), pad(2)]
        board = mock.Mock()
        board.GetFootprints.return_value = [cap]
        blocker = {
            "ref": "C6", "target_net": "/SS",
            "endpoint_ref": "U4", "endpoint_pad": "11",
            "endpoint_x_mm": 7.0, "endpoint_y_mm": 12.0,
            "layer": "F.Cu", "hit_count": 3, "distance_mm": 8.0,
        }
        with mock.patch.object(repair.pcbnew, "LoadBoard",
                               return_value=board), \
                mock.patch.object(
                    repair, "_trapped_foreign_pad_blockers",
                    return_value=[blocker]):
            plan = repair.plan_footprint_repairs(
                "board.kicad_pcb", {"unconn_nets": ["/SS"]})
        self.assertEqual([row["ref"] for row in plan["targets"]], ["C6"])
        self.assertEqual(plan["immutable"], [])

    def test_footprint_plan_can_move_refused_passive_endpoint_toward_owner(self):
        import cec_certificate_repair as repair

        def pad(net):
            return mock.Mock(IsOnCopperLayer=mock.Mock(return_value=True),
                             HasHole=mock.Mock(return_value=False),
                             GetNetCode=mock.Mock(return_value=net))

        cap = mock.Mock()
        cap.GetReference.return_value = "C42"
        cap.IsLocked.return_value = False
        cap.Pads.return_value = [pad(1), pad(2)]
        owner = mock.Mock()
        owner.GetReference.return_value = "U4"
        owner.IsLocked.return_value = False
        owner.Pads.return_value = [pad(index + 10) for index in range(12)]
        board = mock.Mock()
        board.GetFootprints.return_value = [cap, owner]
        payload = {"unconn_nets": ["/SS"], "final_completion": {
            "refused_details": [{
                "net": "/SS", "distance_mm": 3.7,
                "certificate": {
                    "net": "/SS",
                    "endpoints": [
                        {"endpoint": "a", "kind": "pad", "ref": "U4",
                         "pad": "11", "x_mm": 66.2, "y_mm": 32.0},
                        {"endpoint": "b", "kind": "pad", "ref": "C42",
                         "pad": "1", "x_mm": 63.0, "y_mm": 33.7},
                    ],
                    "dominant_blockers": [{"kind": "track",
                                              "hit_count": 4}],
                },
            }],
        }}
        with mock.patch.object(repair.pcbnew, "LoadBoard",
                               return_value=board), \
                mock.patch.object(
                    repair, "_trapped_foreign_pad_blockers",
                    return_value=[]):
            plan = repair.plan_footprint_repairs(
                "board.kicad_pcb", payload)

        self.assertEqual([row["ref"] for row in plan["targets"]], ["C42"])
        self.assertEqual(plan["targets"][0]["motion"], "toward_endpoint")
        self.assertEqual(plan["targets"][0]["endpoint_ref"], "U4")

    def test_exclusive_support_can_move_beside_trapped_owner(self):
        import cec_certificate_repair as repair

        def pad(number, net):
            return mock.Mock(
                IsOnCopperLayer=mock.Mock(return_value=True),
                HasHole=mock.Mock(return_value=False),
                GetNumber=mock.Mock(return_value=str(number)),
                GetNetCode=mock.Mock(return_value=net))

        cap = mock.Mock()
        cap.GetReference.return_value = "C42"
        cap.GetPosition.return_value = SimpleNamespace(x=63_000_000,
                                                       y=34_000_000)
        cap.IsLocked.return_value = False
        cap.Pads.return_value = [pad(1, 1), pad(2, 2)]
        owner = mock.Mock()
        owner.GetReference.return_value = "U4"
        owner.GetPosition.return_value = SimpleNamespace(x=66_000_000,
                                                         y=32_000_000)
        owner.IsLocked.return_value = False
        owner.Pads.return_value = [pad(11, 1)] + [
            pad(index, index + 10) for index in range(1, 12)]
        board = mock.Mock()
        board.GetFootprints.return_value = [cap, owner]
        board.GetNetcodeFromNetname.return_value = 1
        payload = {"unconn_nets": ["/SS"], "final_completion": {
            "refused_details": [{
                "net": "/SS", "distance_mm": 6.3,
                "certificate": {
                    "net": "/SS",
                    "endpoints": [
                        {"endpoint": "a", "kind": "pad", "ref": "U4",
                         "pad": "11", "x_mm": 66.2, "y_mm": 32.0},
                        {"endpoint": "b", "kind": "pad", "ref": "C42",
                         "pad": "1", "x_mm": 63.0, "y_mm": 34.0},
                    ],
                    "layers": [{"layer": "F.Cu"}],
                    "dominant_blockers": [{"kind": "track",
                                              "hit_count": 4}],
                },
            }],
        }}
        with mock.patch.object(repair.pcbnew, "LoadBoard",
                               return_value=board), \
                mock.patch.object(
                    repair, "_trapped_foreign_pad_blockers",
                    return_value=[]), \
                mock.patch.object(
                    repair, "_surface_trapped_endpoint_labels",
                    return_value={"a"}):
            plan = repair.plan_footprint_repairs(
                "board.kicad_pcb", payload)

        self.assertIn("C42", [row["ref"] for row in plan["targets"]])

    def test_footprint_relocation_ladder_contains_quarter_turn_away_seat(self):
        import cec_certificate_repair as repair

        footprint = mock.Mock()
        footprint.GetPosition.return_value = SimpleNamespace(
            x=5_500_000, y=10_500_000)
        board = mock.Mock()
        board.FindFootprintByReference.return_value = footprint
        target = repair.asdict(repair.FootprintRepairTarget(
            ref="C6", target_net="/SS", endpoint_ref="U4",
            endpoint_pad="11", endpoint_x_mm=7.0, endpoint_y_mm=12.0,
            hit_count=2, distance_mm=8.0, priority=(0,)))
        with mock.patch.object(repair.pcbnew, "LoadBoard",
                               return_value=board):
            rows = repair._footprint_relocation_candidates(
                "board.kicad_pcb", target)
        self.assertIn({"rotation_delta_deg": 90.0,
                       "dx_mm": -0.5, "dy_mm": -0.75}, rows)

    def test_footprint_relocation_ladder_moves_endpoint_toward_owner(self):
        import cec_certificate_repair as repair

        footprint = mock.Mock()
        footprint.GetPosition.return_value = SimpleNamespace(
            x=63_000_000, y=34_000_000)
        board = mock.Mock()
        board.FindFootprintByReference.return_value = footprint
        target = repair.asdict(repair.FootprintRepairTarget(
            ref="C42", target_net="/SS", endpoint_ref="U4",
            endpoint_pad="11", endpoint_x_mm=66.0, endpoint_y_mm=32.0,
            hit_count=2, distance_mm=3.7, priority=(0,),
            motion="toward_endpoint"))
        with mock.patch.object(repair.pcbnew, "LoadBoard",
                               return_value=board):
            rows = repair._footprint_relocation_candidates(
                "board.kicad_pcb", target)

        self.assertEqual(rows[0], {"rotation_delta_deg": 180.0,
                                   "dx_mm": 0.0, "dy_mm": -0.0})
        self.assertGreater(rows[1]["dx_mm"], 0.0)
        self.assertLess(rows[1]["dy_mm"], 0.0)

    def test_occupancy_candidates_rank_locked_copper_before_total_hits(self):
        source = Path(os.path.join(
            ROOT, "scripts", "cec_certificate_repair.py")).read_text(
                encoding="utf-8")
        occupancy = source[
            source.index("def _occupancy_relocation_candidates"):
            source.index("def _combined_footprint_relocation_candidates")]
        combined = source[
            source.index("def _combined_footprint_relocation_candidates"):
            source.index("def _relocate_footprint_worker")]

        self.assertIn('"locked_copper_hits": locked_copper_hits', occupancy)
        self.assertLess(
            occupancy.index("locked_copper_hits,\n                 copper_hits"),
            occupancy.index("round(endpoint_distance, 6)"))
        self.assertLess(
            combined.index('int(score.get("locked_copper_hits") or 0)'),
            combined.index('int(score.get("copper_hits") or 0)'))

    def test_support_cluster_ladder_includes_rigid_lane_reversal(self):
        import cec_certificate_repair as repair

        footprint = mock.Mock()
        footprint.GetPosition.return_value = SimpleNamespace(
            x=66_000_000, y=36_000_000)
        board = mock.Mock()
        board.FindFootprintByReference.return_value = footprint
        target = repair.asdict(repair.FootprintRepairTarget(
            ref="R15", target_net="/OV", endpoint_ref="U4",
            endpoint_pad="5", endpoint_x_mm=66.0, endpoint_y_mm=29.0,
            hit_count=4, distance_mm=7.0, priority=(0,),
            motion="toward_endpoint", companion_refs=("R16",)))
        with mock.patch.object(repair.pcbnew, "LoadBoard",
                               return_value=board):
            rows = repair._footprint_relocation_candidates(
                "board.kicad_pcb", target)

        self.assertEqual(len(rows), 16)
        self.assertEqual({row["rotation_delta_deg"] for row in rows},
                         {0.0, 180.0})
        self.assertTrue(all(row["dy_mm"] < 0.0 for row in rows))

    def test_relocated_support_cell_must_reconnect_ground(self):
        import cec_certificate_repair as repair

        self.assertEqual(
            repair._relocation_support_nets(
                {"affected_nets": ["/SS", "GND", "+3V3"]}, "/SS"),
            ("+3V3", "GND"))

    def test_certificate_node_at_exact_smd_pad_keeps_pin_escape(self):
        import pcbnew
        import cec_certificate_repair as repair

        board = pcbnew.CreateEmptyBoard()
        net = pcbnew.NETINFO_ITEM(board, "+3V3")
        board.Add(net)
        footprint = pcbnew.FOOTPRINT(board)
        footprint.SetReference("U10")
        pad = pcbnew.PAD(footprint)
        pad.SetPadName("6")
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(pcbnew.VECTOR2I_MM(1.45, 0.30))
        pad.SetPosition(pcbnew.VECTOR2I_MM(5.0, 5.0))
        pad.SetLayerSet(pcbnew.PAD.SMDMask())
        pad.SetNet(net)
        footprint.Add(pad)
        board.Add(footprint)
        track = pcbnew.PCB_TRACK(board)
        track.SetStart(pcbnew.VECTOR2I_MM(5.0, 5.0))
        track.SetEnd(pcbnew.VECTOR2I_MM(4.5, 5.5))
        track.SetWidth(pcbnew.FromMM(0.20))
        track.SetLayer(pcbnew.F_Cu)
        track.SetNet(net)
        board.Add(track)

        anchor = repair._certificate_endpoint_anchor(
            board, {"kind": "node", "x_mm": 5.0, "y_mm": 5.0},
            net.GetNetCode(), pcbnew.FromMM(0.50), pcbnew.FromMM(0.20),
            pcbnew.FromMM(0.20))

        self.assertIsNotNone(anchor)
        self.assertEqual(anchor[3].GetClass(), "PAD")
        self.assertEqual(str(anchor[3].GetNumber()), "6")
        self.assertEqual(anchor[2][0], pcbnew.FromMM(0.20))
        self.assertGreater(anchor[2][1], pcbnew.FromMM(0.6))

    def test_target_endpoint_retreat_is_bounded_to_a_live_leaf_prefix(self):
        import pcbnew
        import cec_certificate_repair as repair

        board = pcbnew.CreateEmptyBoard()
        net = pcbnew.NETINFO_ITEM(board, "/OPEN")
        board.Add(net)
        footprint = pcbnew.FOOTPRINT(board)
        footprint.SetReference("U1")
        pad = pcbnew.PAD(footprint)
        pad.SetPadName("1")
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(pcbnew.VECTOR2I_MM(0.6, 0.4))
        pad.SetPosition(pcbnew.VECTOR2I_MM(4.0, 5.0))
        pad.SetLayerSet(pcbnew.PAD.SMDMask())
        pad.SetNet(net)
        footprint.Add(pad)
        board.Add(footprint)

        track_uuids = []
        for x0, x1 in ((1.0, 2.0), (2.0, 3.0), (3.0, 4.0)):
            item = pcbnew.PCB_TRACK(board)
            item.SetStart(pcbnew.VECTOR2I_MM(x0, 5.0))
            item.SetEnd(pcbnew.VECTOR2I_MM(x1, 5.0))
            item.SetWidth(pcbnew.FromMM(0.20))
            item.SetLayer(pcbnew.F_Cu)
            item.SetNet(net)
            board.Add(item)
            track_uuids.append(repair._uuid(item))
        target = repair.asdict(repair.FootprintRepairTarget(
            ref="C1", target_net="/OPEN", endpoint_ref="",
            endpoint_pad="", endpoint_x_mm=1.0, endpoint_y_mm=5.0,
            hit_count=2, distance_mm=3.0, priority=(0,)))
        certificate = {"endpoints": [
            {"kind": "node", "x_mm": 1.0, "y_mm": 5.0},
            {"kind": "pad", "ref": "C1", "pad": "1",
             "x_mm": 0.0, "y_mm": 5.0},
        ]}
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "retreat.kicad_pcb")
            pcbnew.SaveBoard(path, board)
            access = repair._target_endpoint_access_candidates_worker(
                path, target, certificate, max_hops=4)
            plan = repair._target_endpoint_retreat_candidates_worker(
                path, target, certificate, max_hops=4)
            changed, evidence = repair._apply_target_endpoint_retreat_worker(
                path, "/OPEN", plan["candidates"][1])
            saved = pcbnew.LoadBoard(path)

        self.assertEqual(len(access["candidates"]), 3)
        self.assertEqual(
            access["candidates"][0]["access_path_uuids"], track_uuids[:1])
        self.assertEqual(
            access["candidates"][2]["endpoint"]["kind"], "pad")
        self.assertEqual(len(plan["candidates"]), 3)
        self.assertEqual(
            plan["candidates"][0]["removed_uuids"], track_uuids[:1])
        self.assertEqual(
            plan["candidates"][1]["removed_uuids"], track_uuids[:2])
        self.assertEqual(plan["candidates"][2]["endpoint"]["kind"], "pad")
        self.assertEqual(plan["candidates"][2]["endpoint"]["ref"], "U1")
        self.assertTrue(changed, evidence)
        self.assertEqual(len(saved.GetTracks()), 1)

        target["endpoint_x_mm"] = 4.0
        pad_certificate = {"endpoints": [
            {"kind": "node", "x_mm": 4.0, "y_mm": 5.0},
            certificate["endpoints"][1],
        ]}
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "pad-origin.kicad_pcb")
            pcbnew.SaveBoard(path, board)
            refusal = repair._target_endpoint_retreat_candidates_worker(
                path, target, pad_certificate)
        self.assertEqual(refusal["refusal"], "retreat_origin_is_pad")

    def test_connected_endpoint_access_generates_route_aware_support_seat(self):
        import cec_certificate_repair as repair

        target = repair.asdict(repair.FootprintRepairTarget(
            ref="R19", target_net="+3V3", endpoint_ref="U10",
            endpoint_pad="6", endpoint_x_mm=5.0, endpoint_y_mm=5.0,
            hit_count=4, distance_mm=3.0, priority=(0,),
            motion="toward_endpoint"))
        owner = mock.Mock()
        owner.GetPosition.return_value = SimpleNamespace(
            x=2_000_000, y=2_000_000)
        board = mock.Mock()
        board.FindFootprintByReference.return_value = owner
        board.GetFootprints.return_value = [owner]
        board.Groups.return_value = []

        def seats(_path, row, limit=32):
            endpoint = float(row["endpoint_x_mm"])
            return [{
                "rotation_delta_deg": 90.0,
                "dx_mm": endpoint, "dy_mm": 0.0,
                "occupancy_score": {
                    "outside_mm2": 0.0, "footprint_overlap_count": 0,
                    "footprint_overlap_mm2": 0.0, "copper_hits": 0,
                    "endpoint_distance_mm": 1.0,
                },
            }]

        access = {"candidates": [{
            "endpoint": {"kind": "node", "x_mm": 6.0, "y_mm": 5.0},
            "access_path_uuids": ["stub"], "hops": 1,
        }]}
        with mock.patch.object(repair.pcbnew, "LoadBoard",
                               return_value=board), \
                mock.patch.object(
                    repair, "_occupancy_relocation_candidates",
                    side_effect=seats), \
                mock.patch.object(
                    repair, "_target_endpoint_access_candidates_worker",
                    return_value=access), \
                mock.patch.object(
                    repair, "_footprint_relocation_candidates",
                    return_value=[]):
            rows = repair._combined_footprint_relocation_candidates(
                "board.kicad_pcb", target)

        route_row = next(row for row in rows
                         if row.get("route_access_endpoint"))
        self.assertEqual(route_row["generator"],
                         "occupancy_connected_endpoint")
        self.assertEqual(route_row["route_access_path_uuids"], ["stub"])
        self.assertEqual(route_row["route_access_endpoint"]["x_mm"], 6.0)

    def test_board_rotation_uses_kicad_clockwise_positive_convention(self):
        import cec_certificate_repair as repair

        x, y = repair._rotate_board_vector(1.0, 0.0, 90.0)
        self.assertAlmostEqual(x, 0.0, places=9)
        self.assertAlmostEqual(y, -1.0, places=9)
        x, y = repair._rotate_board_vector(0.0, 1.0, 90.0)
        self.assertAlmostEqual(x, 1.0, places=9)
        self.assertAlmostEqual(y, 0.0, places=9)

    def test_footprint_reseat_preserves_copper_beyond_direct_pad_stub(self):
        import pcbnew
        import cec_certificate_repair as repair

        board = pcbnew.CreateEmptyBoard()
        net = pcbnew.NETINFO_ITEM(board, "/SIGNAL")
        board.Add(net)
        footprint = pcbnew.FOOTPRINT(board)
        footprint.SetReference("U4")
        footprint.SetPosition(pcbnew.VECTOR2I_MM(5, 5))
        pad = pcbnew.PAD(footprint)
        pad.SetPadName("1")
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(pcbnew.VECTOR2I_MM(0.6, 0.2))
        pad.SetPosition(pcbnew.VECTOR2I_MM(5, 5))
        pad.SetLayerSet(pcbnew.PAD.SMDMask())
        pad.SetNet(net)
        footprint.Add(pad)
        board.Add(footprint)

        def track(start, end):
            item = pcbnew.PCB_TRACK(board)
            item.SetStart(pcbnew.VECTOR2I_MM(*start))
            item.SetEnd(pcbnew.VECTOR2I_MM(*end))
            item.SetWidth(pcbnew.FromMM(0.2))
            item.SetLayer(pcbnew.F_Cu)
            item.SetNet(net)
            item.SetLocked(True)
            board.Add(item)
            return item

        pad_stub = track((5, 5), (6, 5))
        preserved = track((6, 5), (10, 5))
        pad_stub_uuid = repair._uuid(pad_stub)
        preserved_uuid = repair._uuid(preserved)
        target = repair.FootprintRepairTarget(
            ref="U4", target_net="/SIGNAL", endpoint_ref="U4",
            endpoint_pad="1", endpoint_x_mm=5.0, endpoint_y_mm=5.0,
            hit_count=3, distance_mm=4.0, priority=(0,))
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "reseat.kicad_pcb")
            pcbnew.SaveBoard(path, board)
            changed, evidence = repair._relocate_footprint_worker(
                path, repair.asdict(target), {
                    "rotation_delta_deg": 0.0,
                    "dx_mm": 0.5,
                    "dy_mm": 0.0,
                }, generated_locked_uuids=(pad_stub_uuid, preserved_uuid))
            saved = pcbnew.LoadBoard(path)

        remaining = {repair._uuid(item) for item in saved.GetTracks()}
        self.assertTrue(changed, evidence)
        self.assertEqual(evidence["removed_tracks"], 1)
        self.assertNotIn(pad_stub_uuid, remaining)
        self.assertIn(preserved_uuid, remaining)
        self.assertEqual(evidence["preserved_anchors"][0]["x_mm"], 6.0)

    def test_footprint_reseat_preserves_locked_pad_via_as_route_anchor(self):
        import pcbnew
        import cec_certificate_repair as repair

        board = pcbnew.CreateEmptyBoard()
        signal = pcbnew.NETINFO_ITEM(board, "/SIGNAL")
        ground = pcbnew.NETINFO_ITEM(board, "GND")
        board.Add(signal)
        board.Add(ground)
        footprint = pcbnew.FOOTPRINT(board)
        footprint.SetReference("C42")
        footprint.SetPosition(pcbnew.VECTOR2I_MM(5, 5))
        for number, net, x in (("1", signal, 5.0), ("2", ground, 6.0)):
            pad = pcbnew.PAD(footprint)
            pad.SetPadName(number)
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetSize(pcbnew.VECTOR2I_MM(0.6, 0.4))
            pad.SetPosition(pcbnew.VECTOR2I_MM(x, 5.0))
            pad.SetLayerSet(pcbnew.PAD.SMDMask())
            pad.SetNet(net)
            footprint.Add(pad)
        board.Add(footprint)
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(pcbnew.VECTOR2I_MM(6, 5))
        via.SetWidth(pcbnew.FromMM(0.5))
        via.SetDrill(pcbnew.FromMM(0.25))
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetNet(ground)
        via.SetLocked(True)
        board.Add(via)
        via_uuid = repair._uuid(via)
        target = repair.FootprintRepairTarget(
            ref="C42", target_net="/SIGNAL", endpoint_ref="U4",
            endpoint_pad="11", endpoint_x_mm=8.0, endpoint_y_mm=5.0,
            hit_count=3, distance_mm=3.0, priority=(0,))
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "locked-pad-via.kicad_pcb")
            pcbnew.SaveBoard(path, board)
            changed, evidence = repair._relocate_footprint_worker(
                path, repair.asdict(target), {
                    "rotation_delta_deg": 0.0,
                    "dx_mm": 1.0,
                    "dy_mm": 0.0,
                })
            saved = pcbnew.LoadBoard(path)

        self.assertTrue(changed, evidence)
        saved_via = next(item for item in saved.GetTracks()
                         if repair._uuid(item) == via_uuid)
        self.assertAlmostEqual(saved_via.GetPosition().x / repair.MM, 6.0)
        self.assertEqual(
            evidence["preserved_locked_pad_via_uuids"], [via_uuid])
        self.assertTrue(any(
            row.get("kind") == "authored_locked_pad_via"
            and row.get("net") == "GND"
            for row in evidence["preserved_anchors"]))

    def test_footprint_reseat_preserves_locked_incident_trace_as_anchor(self):
        import pcbnew
        import cec_certificate_repair as repair

        board = pcbnew.CreateEmptyBoard()
        net = pcbnew.NETINFO_ITEM(board, "/SIGNAL")
        board.Add(net)
        footprint = pcbnew.FOOTPRINT(board)
        footprint.SetReference("C46")
        footprint.SetPosition(pcbnew.VECTOR2I_MM(5, 5))
        pad = pcbnew.PAD(footprint)
        pad.SetPadName("1")
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(pcbnew.VECTOR2I_MM(0.6, 0.4))
        pad.SetPosition(pcbnew.VECTOR2I_MM(5, 5))
        pad.SetLayerSet(pcbnew.PAD.SMDMask())
        pad.SetNet(net)
        footprint.Add(pad)
        board.Add(footprint)
        trace = pcbnew.PCB_TRACK(board)
        trace.SetStart(pcbnew.VECTOR2I_MM(5, 5))
        trace.SetEnd(pcbnew.VECTOR2I_MM(8, 5))
        trace.SetWidth(pcbnew.FromMM(0.2))
        trace.SetLayer(pcbnew.F_Cu)
        trace.SetNet(net)
        trace.SetLocked(True)
        board.Add(trace)
        trace_uuid = repair._uuid(trace)
        target = repair.FootprintRepairTarget(
            ref="C46", target_net="/SIGNAL", endpoint_ref="U4",
            endpoint_pad="1", endpoint_x_mm=9.0, endpoint_y_mm=5.0,
            hit_count=2, distance_mm=4.0, priority=(0,))
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "locked-trace-anchor.kicad_pcb")
            pcbnew.SaveBoard(path, board)
            changed, evidence = repair._relocate_footprint_worker(
                path, repair.asdict(target), {
                    "rotation_delta_deg": 0.0,
                    "dx_mm": 1.0,
                    "dy_mm": 0.0,
                })
            saved = pcbnew.LoadBoard(path)

        self.assertTrue(changed, evidence)
        saved_trace = next(item for item in saved.GetTracks()
                           if repair._uuid(item) == trace_uuid)
        self.assertAlmostEqual(saved_trace.GetStart().x / repair.MM, 5.0)
        self.assertEqual(evidence["removed_tracks"], 0)
        self.assertTrue(any(
            row.get("kind") == "authored_locked_incident_branch"
            and row.get("track_uuid") == trace_uuid
            and row.get("x_mm") == 5.0
            for row in evidence["preserved_anchors"]))

    def test_passive_cluster_reseat_translates_every_member(self):
        import pcbnew
        import cec_certificate_repair as repair

        board = pcbnew.CreateEmptyBoard()
        net = pcbnew.NETINFO_ITEM(board, "/DIV")
        board.Add(net)
        for ref, x in (("R15", 5.0), ("R16", 6.5)):
            footprint = pcbnew.FOOTPRINT(board)
            footprint.SetReference(ref)
            footprint.SetPosition(pcbnew.VECTOR2I_MM(x, 5.0))
            pad = pcbnew.PAD(footprint)
            pad.SetPadName("1")
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetSize(pcbnew.VECTOR2I_MM(0.6, 0.4))
            pad.SetPosition(pcbnew.VECTOR2I_MM(x, 5.0))
            pad.SetLayerSet(pcbnew.PAD.SMDMask())
            pad.SetNet(net)
            footprint.Add(pad)
            board.Add(footprint)
        internal = pcbnew.PCB_TRACK(board)
        internal.SetStart(pcbnew.VECTOR2I_MM(5.0, 5.0))
        internal.SetEnd(pcbnew.VECTOR2I_MM(6.5, 5.0))
        internal.SetWidth(pcbnew.FromMM(0.2))
        internal.SetLayer(pcbnew.F_Cu)
        internal.SetNet(net)
        board.Add(internal)
        internal_uuid = repair._uuid(internal)
        target = repair.FootprintRepairTarget(
            ref="R15", target_net="/DIV", endpoint_ref="U4",
            endpoint_pad="5", endpoint_x_mm=5.0, endpoint_y_mm=2.0,
            hit_count=3, distance_mm=3.0, priority=(0,),
            motion="toward_endpoint", companion_refs=("R16",))
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "cluster.kicad_pcb")
            pcbnew.SaveBoard(path, board)
            changed, evidence = repair._relocate_footprint_worker(
                path, repair.asdict(target), {
                    "rotation_delta_deg": 0.0,
                    "dx_mm": 0.5,
                    "dy_mm": -1.0,
                })
            saved = pcbnew.LoadBoard(path)

        self.assertTrue(changed, evidence)
        self.assertEqual(evidence["companion_refs"], ["R16"])
        self.assertEqual(evidence["moved_internal_tracks"], 1)
        self.assertEqual(evidence["removed_tracks"], 0)
        self.assertAlmostEqual(
            saved.FindFootprintByReference("R15").GetPosition().x / 1e6,
            5.5)
        self.assertAlmostEqual(
            saved.FindFootprintByReference("R16").GetPosition().x / 1e6,
            7.0)
        self.assertAlmostEqual(
            saved.FindFootprintByReference("R16").GetPosition().y / 1e6,
            4.0)
        moved = next(item for item in saved.GetTracks()
                     if repair._uuid(item) == internal_uuid)
        self.assertAlmostEqual(moved.GetStart().x / 1e6, 5.5)
        self.assertAlmostEqual(moved.GetStart().y / 1e6, 4.0)
        self.assertAlmostEqual(moved.GetEnd().x / 1e6, 7.0)
        self.assertAlmostEqual(moved.GetEnd().y / 1e6, 4.0)

        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "cluster-rotated.kicad_pcb")
            pcbnew.SaveBoard(path, saved)
            changed, evidence = repair._relocate_footprint_worker(
                path, repair.asdict(target), {
                    "rotation_delta_deg": 180.0,
                    "dx_mm": 0.0,
                    "dy_mm": 0.0,
                })
            rotated = pcbnew.LoadBoard(path)

        self.assertTrue(changed, evidence)
        self.assertAlmostEqual(
            rotated.FindFootprintByReference("R15").GetPosition().x / 1e6,
            5.5)
        self.assertAlmostEqual(
            rotated.FindFootprintByReference("R16").GetPosition().x / 1e6,
            4.0)
        rotated_track = next(item for item in rotated.GetTracks()
                             if repair._uuid(item) == internal_uuid)
        self.assertAlmostEqual(rotated_track.GetStart().x / 1e6, 5.5)
        self.assertAlmostEqual(rotated_track.GetEnd().x / 1e6, 4.0)

        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "cluster-quarter-turn.kicad_pcb")
            pcbnew.SaveBoard(path, board)
            changed, evidence = repair._relocate_footprint_worker(
                path, repair.asdict(target), {
                    "rotation_delta_deg": 90.0,
                    "dx_mm": 0.0,
                    "dy_mm": 0.0,
                })
            quarter = pcbnew.LoadBoard(path)

        self.assertTrue(changed, evidence)
        self.assertAlmostEqual(
            quarter.FindFootprintByReference("R16").GetPosition().x / 1e6,
            5.0)
        self.assertAlmostEqual(
            quarter.FindFootprintByReference("R16").GetPosition().y / 1e6,
            3.5)
        quarter_track = next(item for item in quarter.GetTracks()
                             if repair._uuid(item) == internal_uuid)
        self.assertAlmostEqual(quarter_track.GetEnd().x / 1e6, 5.0)
        self.assertAlmostEqual(quarter_track.GetEnd().y / 1e6, 3.5)

    def test_refusal_named_generated_via_is_relocation_target(self):
        import pcbnew
        import cec_certificate_repair as repair

        board = pcbnew.CreateEmptyBoard()
        blocker = pcbnew.NETINFO_ITEM(board, "/VCC")
        board.Add(blocker)
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(pcbnew.VECTOR2I_MM(5, 5))
        via.SetWidth(pcbnew.FromMM(0.6))
        via.SetDrill(pcbnew.FromMM(0.3))
        via.SetNet(blocker)
        via.SetLocked(True)
        board.Add(via)
        branch = pcbnew.PCB_TRACK(board)
        branch.SetStart(pcbnew.VECTOR2I_MM(5, 5))
        branch.SetEnd(pcbnew.VECTOR2I_MM(4, 4))
        branch.SetWidth(pcbnew.FromMM(0.25))
        branch.SetLayer(pcbnew.F_Cu)
        branch.SetNet(blocker)
        board.Add(branch)
        with tempfile.TemporaryDirectory() as work:
            path = os.path.join(work, "via.kicad_pcb")
            pcbnew.SaveBoard(path, board)
            saved = pcbnew.LoadBoard(path)
            uid = repair._uuid(next(item for item in saved.GetTracks()
                                    if item.GetClass() == "PCB_VIA"))
            payload = {"unconn_nets": ["/OPEN"], "final_completion": {
                "refused_details": [{
                    "net": "/OPEN", "distance_mm": 4.0,
                    "certificate": {
                        "net": "/OPEN",
                        "endpoints": [{
                            "endpoint": "a", "kind": "pad", "ref": "U1",
                            "pad": "1", "x_mm": 4.0, "y_mm": 5.0,
                        }],
                        "dominant_blockers": [{
                            "kind": "via", "uuid": uid, "hit_count": 3,
                        }],
                    },
                }],
            }}
            denied = repair.plan_congestion_via_repairs(path, payload)
            allowed = repair.plan_congestion_via_repairs(
                path, payload, generated_locked_uuids={uid})

        self.assertEqual(denied["targets"], [])
        self.assertEqual(denied["immutable"][0]["reason"],
                         "authored_locked_via")
        self.assertEqual(allowed["targets"][0]["via"]["uuid"], uid)
        self.assertGreater(allowed["targets"][0]["via"]["away_dx"], 0)
        self.assertEqual(allowed["targets"][0]["owner_directions"],
                         [[-1, -1]])

    def test_surgery_policy_protects_authored_and_sensitive_copper(self):
        import cec_certificate_repair as repair

        self.assertEqual(repair.protected_net_reason(
            "/USB_D_P", width_mm=0.2), "coupled_pair")
        self.assertEqual(repair.protected_net_reason(
            "/SENSE1_HI", width_mm=0.2), "kelvin_or_sense")
        self.assertEqual(repair.protected_net_reason(
            "+12V", width_mm=2.5), "wide_or_high_current")
        self.assertEqual(repair.protected_net_reason(
            "/SIG", width_mm=0.2, locked=True), "locked_copper")
        self.assertIsNone(repair.protected_net_reason(
            "/USB_VBUS", width_mm=1.0, layer="F.Cu"))
        self.assertIsNone(repair.protected_net_reason(
            "+3V3", width_mm=0.5, layer="PWR"))

    def test_adoption_is_strictly_monotonic(self):
        import cec_certificate_repair as repair

        base = {"unconnected": 13, "drc": 1,
                "kelvin_ok": True, "diffpair_ok": True}
        self.assertEqual(repair._accepts(
            base, {**base, "drc": 0}),
            (True, "strict_structural_improvement"))
        self.assertEqual(repair._accepts(
            base, {**base, "unconnected": 14, "drc": 0})[1],
            "unconnected_regressed")
        self.assertEqual(repair._accepts(
            base, {**base, "kelvin_ok": False, "drc": 0})[1],
            "kelvin_gate_regressed")

    def test_adoption_rejects_connectivity_debt_swap(self):
        import cec_certificate_repair as repair

        base = {"unconnected": 3, "unconn_nets": ["/OLD"], "drc": 1,
                "kelvin_ok": True, "diffpair_ok": True}
        after = {**base, "unconnected": 2, "unconn_nets": ["/NEW"]}
        self.assertEqual(repair._accepts(base, after),
                         (False, "new_unconnected_nets"))

    def test_adoption_rejects_drc_identity_debt_swap(self):
        import cec_certificate_repair as repair

        base = {"unconnected": 3, "unconn_nets": ["/OPEN"], "drc": 2,
                "kelvin_ok": True, "diffpair_ok": True,
                "structural_drc_identities": ["clearance-old", "short-old"]}
        after = {**base, "unconnected": 2, "drc": 1,
                 "structural_drc_identities": ["short-new"]}
        self.assertEqual(repair._accepts(base, after),
                         (False, "new_structural_drc_identity"))

    def test_drc_named_track_is_repair_target_without_certificate(self):
        import pcbnew
        import cec_certificate_repair as repair

        board = pcbnew.CreateEmptyBoard()
        net = pcbnew.NETINFO_ITEM(board, "/GPIO")
        board.Add(net)
        track = pcbnew.PCB_TRACK(board)
        track.SetStart(pcbnew.VECTOR2I_MM(1, 1))
        track.SetEnd(pcbnew.VECTOR2I_MM(4, 1))
        track.SetWidth(pcbnew.FromMM(0.25))
        track.SetLayer(pcbnew.F_Cu)
        track.SetNet(net)
        board.Add(track)
        uid = repair._uuid(track)
        drc = {"violations": [{
            "type": "clearance", "items": [{
                "description": "Track [/GPIO] on F.Cu", "uuid": uid,
            }],
        }]}
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "drc-target.kicad_pcb")
            pcbnew.SaveBoard(path, board)
            plan = repair.plan_repairs(path, {}, drc_data=drc, limit=4)

        self.assertEqual(plan["certificates"], 0)
        self.assertEqual([row["uuid"] for row in plan["targets"]], [uid])
        self.assertTrue(plan["targets"][0]["drc_conflict"])

    def test_sensitive_plan_only_releases_exact_ungrouped_sense_clearance(self):
        import pcbnew
        import cec_certificate_repair as repair

        board = pcbnew.CreateEmptyBoard()
        nets = {}
        for name in ("/SENSE1_LO", "/SENSE2_HI", "/USB_D_P", "+12V"):
            nets[name] = pcbnew.NETINFO_ITEM(board, name)
            board.Add(nets[name])

        def locked_track(name, y, width=0.25):
            item = pcbnew.PCB_TRACK(board)
            item.SetStart(pcbnew.VECTOR2I_MM(1, y))
            item.SetEnd(pcbnew.VECTOR2I_MM(5, y))
            item.SetWidth(pcbnew.FromMM(width))
            item.SetLayer(pcbnew.F_Cu)
            item.SetNet(nets[name])
            item.SetLocked(True)
            board.Add(item)
            return item

        eligible = locked_track("/SENSE1_LO", 1)
        grouped = locked_track("/SENSE2_HI", 2)
        coupled = locked_track("/USB_D_P", 3)
        wide = locked_track("+12V", 4, width=2.0)
        group = pcbnew.PCB_GROUP(board)
        group.SetName("AUTHORED_SENSE")
        board.Add(group)
        group.AddItem(grouped)
        board.BuildConnectivity()
        drc = {"violations": [{
            "type": "clearance",
            "items": [{"description": "Track [test] on F.Cu",
                       "uuid": repair._uuid(item)}
                      for item in (eligible, grouped, coupled, wide)],
        }]}
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "sensitive-plan.kicad_pcb")
            pcbnew.SaveBoard(path, board)
            plan = repair.plan_sensitive_drc_repairs(path, drc, limit=8)

        self.assertEqual([row["uuid"] for row in plan["targets"]],
                         [repair._uuid(eligible)])
        self.assertTrue(plan["targets"][0]["sensitive_repair"])
        immutable = {row["uuid"]: row["reason"]
                     for row in plan["immutable"]}
        self.assertEqual(immutable[repair._uuid(grouped)],
                         "explicit_group_ownership")
        # The long-lived KiCad SWIG test process can occasionally reload a
        # synthetic track without its slash-prefixed net name.  Either label
        # is fail-closed; the separate policy test above proves that a named
        # USB pair is classified specifically as coupled copper.
        self.assertIn(immutable[repair._uuid(coupled)],
                      ("coupled_pair", "authored_locked_copper"))
        self.assertEqual(immutable[repair._uuid(wide)],
                         "wide_or_high_current")

    def test_sensitive_mutation_relocks_every_replacement_object(self):
        import pcbnew
        import cec_certificate_repair as repair

        board = pcbnew.CreateEmptyBoard()
        net = pcbnew.NETINFO_ITEM(board, "/SENSE1_LO")
        board.Add(net)
        for start, end in [((0, 0), (10, 0)), ((10, 0), (10, 10)),
                           ((10, 10), (0, 10)), ((0, 10), (0, 0))]:
            edge = pcbnew.PCB_SHAPE(board)
            edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
            edge.SetStart(pcbnew.VECTOR2I_MM(*start))
            edge.SetEnd(pcbnew.VECTOR2I_MM(*end))
            edge.SetLayer(pcbnew.Edge_Cuts)
            board.Add(edge)
        track = pcbnew.PCB_TRACK(board)
        track.SetStart(pcbnew.VECTOR2I_MM(2, 5))
        track.SetEnd(pcbnew.VECTOR2I_MM(8, 5))
        track.SetWidth(pcbnew.FromMM(0.25))
        track.SetLayer(pcbnew.F_Cu)
        track.SetNet(net)
        track.SetLocked(True)
        board.Add(track)
        target = repair.RepairTarget(
            uuid=repair._uuid(track), net="/SENSE1_LO", layer="F.Cu",
            hit_count=1, blocked_nets=(), reservations=(),
            drc_types=("clearance",), drc_conflict=True,
            priority=(-1, repair._uuid(track)), sensitive_repair=True)
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "sensitive-reroute.kicad_pcb")
            pcbnew.SaveBoard(path, board)
            changed, evidence = repair._mutate_worker(
                path, repair.asdict(target), "same_layer", 2.0)
            saved = pcbnew.LoadBoard(path)

        self.assertTrue(changed, evidence)
        self.assertTrue(evidence["sensitive_repair"])
        self.assertTrue(evidence["new_geometry"]["locked"])
        self.assertTrue(evidence["new_geometry"]["uuids"])
        self.assertTrue(all(item.IsLocked() for item in saved.GetTracks()))

    def test_drc_named_unlocked_via_is_lower_authority_repair_target(self):
        import pcbnew
        import cec_certificate_repair as repair

        board = pcbnew.CreateEmptyBoard()
        gnd = pcbnew.NETINFO_ITEM(board, "GND")
        signal = pcbnew.NETINFO_ITEM(board, "/LOCKED")
        board.Add(gnd); board.Add(signal)
        track = pcbnew.PCB_TRACK(board)
        track.SetStart(pcbnew.VECTOR2I_MM(2, 4.5))
        track.SetEnd(pcbnew.VECTOR2I_MM(8, 4.5))
        track.SetWidth(pcbnew.FromMM(0.25))
        track.SetLayer(pcbnew.F_Cu)
        track.SetNet(signal)
        track.SetLocked(True)
        board.Add(track)
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(pcbnew.VECTOR2I_MM(5, 5))
        via.SetWidth(pcbnew.FromMM(0.6))
        via.SetDrill(pcbnew.FromMM(0.3))
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetNet(gnd)
        board.Add(via)
        drc = {"violations": [{
            "type": "clearance", "items": [
                {"description": "Track [/LOCKED] on F.Cu",
                 "uuid": repair._uuid(track)},
                {"description": "Via [GND] on F.Cu - B.Cu",
                 "uuid": repair._uuid(via)},
            ],
        }]}
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "via-target.kicad_pcb")
            pcbnew.SaveBoard(path, board)
            plan = repair.plan_via_repairs(path, drc)

        self.assertEqual(plan["eligible"], 1)
        target = plan["targets"][0]
        self.assertEqual(target["uuid"], repair._uuid(via))
        self.assertEqual((target["away_dx"], target["away_dy"]), (0, 1))

    def test_via_relocation_rebuilds_incident_stub_canonically(self):
        import pcbnew
        import cec_certificate_repair as repair

        board = pcbnew.CreateEmptyBoard()
        gnd = pcbnew.NETINFO_ITEM(board, "GND")
        board.Add(gnd)
        # Exact rectangular outline is needed by the ordinary edge guard.
        for start, end in [((0, 0), (10, 0)), ((10, 0), (10, 10)),
                           ((10, 10), (0, 10)), ((0, 10), (0, 0))]:
            edge = pcbnew.PCB_SHAPE(board)
            edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
            edge.SetStart(pcbnew.VECTOR2I_MM(*start))
            edge.SetEnd(pcbnew.VECTOR2I_MM(*end))
            edge.SetLayer(pcbnew.Edge_Cuts)
            board.Add(edge)
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(pcbnew.VECTOR2I_MM(5, 5))
        via.SetWidth(pcbnew.FromMM(0.6))
        via.SetDrill(pcbnew.FromMM(0.3))
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetNet(gnd)
        board.Add(via)
        stub = pcbnew.PCB_TRACK(board)
        stub.SetStart(pcbnew.VECTOR2I_MM(4, 5))
        stub.SetEnd(via.GetPosition())
        stub.SetWidth(pcbnew.FromMM(0.25))
        stub.SetLayer(pcbnew.F_Cu)
        stub.SetNet(gnd)
        board.Add(stub)
        target = repair.ViaRepairTarget(
            uuid=repair._uuid(via), net="GND",
            x_nm=via.GetPosition().x, y_nm=via.GetPosition().y,
            diameter_nm=via.GetWidth(via.TopLayer()),
            drill_nm=via.GetDrillValue(),
            counterpart_uuids=("locked-track",),
            drc_types=("clearance",), away_dx=0, away_dy=1,
            priority=(0, -1, repair._uuid(via)))
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "relocate.kicad_pcb")
            pcbnew.SaveBoard(path, board)
            changed, evidence = repair._relocate_via_worker(
                path, repair.asdict(target), 0, pcbnew.FromMM(0.3))
            saved = pcbnew.LoadBoard(path)

        self.assertTrue(changed, evidence)
        moved = next(item for item in saved.GetTracks()
                     if repair._uuid(item) == target.uuid)
        self.assertAlmostEqual(moved.GetPosition().y / repair.MM, 5.3, places=3)
        self.assertTrue(evidence["generated_tracks"])
        for row in evidence["generated_tracks"]:
            dx = abs(row["end"][0] - row["start"][0])
            dy = abs(row["end"][1] - row["start"][1])
            self.assertTrue(dx == 0 or dy == 0 or abs(dx - dy) < 1e-6)

    def test_composite_via_recovery_selects_only_exact_generated_tracks(self):
        import pcbnew
        import cec_certificate_repair as repair

        board = pcbnew.CreateEmptyBoard()
        generated_net = pcbnew.NETINFO_ITEM(board, "/GENERATED")
        target_net = pcbnew.NETINFO_ITEM(board, "GND")
        board.Add(generated_net); board.Add(target_net)
        generated = pcbnew.PCB_TRACK(board)
        generated.SetStart(pcbnew.VECTOR2I_MM(1, 1))
        generated.SetEnd(pcbnew.VECTOR2I_MM(5, 1))
        generated.SetWidth(pcbnew.FromMM(0.2))
        generated.SetLayer(pcbnew.F_Cu)
        generated.SetNet(generated_net)
        generated.SetLocked(True)
        board.Add(generated)
        authored = pcbnew.PCB_TRACK(board)
        authored.SetStart(pcbnew.VECTOR2I_MM(1, 2))
        authored.SetEnd(pcbnew.VECTOR2I_MM(5, 2))
        authored.SetWidth(pcbnew.FromMM(0.2))
        authored.SetLayer(pcbnew.F_Cu)
        authored.SetNet(target_net)
        authored.SetLocked(True)
        board.Add(authored)
        identity = json.dumps([
            "clearance", "uuid",
            sorted([repair._uuid(generated), repair._uuid(authored)]),
        ], separators=(",", ":"))
        before = {"structural_drc_identities": []}
        after = {"structural_drc_identities": [identity]}
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "composite.kicad_pcb")
            pcbnew.SaveBoard(path, board)
            evidence = repair._new_generated_track_conflicts_worker(
                path, before, after, (repair._uuid(generated),), ("GND",))

        self.assertEqual(evidence["generated_track_uuids"],
                         [repair._uuid(generated)])
        self.assertEqual(
            evidence["repairable_identities"][0]["generated_track_uuids"],
            [repair._uuid(generated)])

    def test_unattached_stitch_via_requires_explicit_mode(self):
        import pcbnew
        import cec_certificate_repair as repair

        board = pcbnew.CreateEmptyBoard()
        gnd = pcbnew.NETINFO_ITEM(board, "GND")
        board.Add(gnd)
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(pcbnew.VECTOR2I_MM(5, 5))
        via.SetWidth(pcbnew.FromMM(0.6))
        via.SetDrill(pcbnew.FromMM(0.3))
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetNet(gnd)
        board.Add(via)
        target = repair.ViaRepairTarget(
            uuid=repair._uuid(via), net="GND",
            x_nm=via.GetPosition().x, y_nm=via.GetPosition().y,
            diameter_nm=via.GetWidth(pcbnew.F_Cu),
            drill_nm=via.GetDrillValue(), counterpart_uuids=(),
            drc_types=(), away_dx=1, away_dy=0,
            priority=(0, repair._uuid(via)))
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "stitch.kicad_pcb")
            pcbnew.SaveBoard(path, board)
            refused, refusal = repair._relocate_via_worker(
                path, repair.asdict(target), pcbnew.FromMM(0.2), 0)
            changed, evidence = repair._relocate_via_worker(
                path, repair.asdict(target), pcbnew.FromMM(0.2), 0,
                (), True)
            saved = pcbnew.LoadBoard(path)

        self.assertFalse(refused)
        self.assertEqual(refusal["refusal"], "no_incident_route_stub")
        self.assertTrue(changed, evidence)
        self.assertEqual(evidence["mode"], "unattached_stitch_via")
        moved = next(item for item in saved.GetTracks()
                     if repair._uuid(item) == target.uuid)
        self.assertAlmostEqual(moved.GetPosition().x / repair.MM,
                               5.2, places=3)

    def test_pad_owned_oversized_via_normalizes_to_declared_pofv(self):
        import pcbnew
        import cec_certificate_repair as repair

        board = pcbnew.CreateEmptyBoard()
        properties = board.GetProperties()
        properties["CEC_FAB_PROFILE"] = "jlcpcb_6l_pofv_signal"
        board.SetProperties(properties)
        gnd = pcbnew.NETINFO_ITEM(board, "GND")
        board.Add(gnd)
        footprint = pcbnew.FOOTPRINT(board)
        footprint.SetReference("U1")
        pad = pcbnew.PAD(footprint)
        pad.SetPadName("12")
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(pcbnew.VECTOR2I_MM(0.8, 0.8))
        pad.SetPosition(pcbnew.VECTOR2I_MM(5.0, 5.0))
        pad.SetLayerSet(pcbnew.PAD.SMDMask())
        pad.SetNet(gnd)
        footprint.Add(pad)
        board.Add(footprint)
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(pcbnew.VECTOR2I_MM(5.0, 5.0))
        via.SetWidth(pcbnew.FromMM(0.9))
        via.SetDrill(pcbnew.FromMM(0.5))
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetNet(gnd)
        board.Add(via)
        via_uuid = repair._uuid(via)

        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "pofv.kicad_pcb")
            pcbnew.SaveBoard(path, board)
            changed, evidence = \
                repair._normalize_pad_owned_via_to_profile_worker(
                    path, via_uuid)
            saved = pcbnew.LoadBoard(path)
            normalized = next(item for item in saved.GetTracks()
                              if repair._uuid(item) == via_uuid)
            for group in list(saved.Groups()):
                saved.Remove(group)
            pcbnew.SaveBoard(path, saved)
            rule_path = os.path.splitext(path)[0] + ".kicad_dru"
            if os.path.exists(rule_path):
                os.remove(rule_path)
            refreshed, refresh_evidence = \
                repair._refresh_transaction_pofv_rule_worker(
                    path, (via_uuid,))
            drc = repair._run_drc(
                path, os.path.join(directory, "pofv-drc.json"))

        self.assertTrue(changed, evidence)
        self.assertEqual(evidence["owner_ref"], "U1")
        self.assertEqual(evidence["owner_pad"], "12")
        self.assertTrue(evidence["rule"]["written"])
        self.assertTrue(refreshed, refresh_evidence)
        self.assertTrue(refresh_evidence["rule"]["written"])
        self.assertAlmostEqual(normalized.GetWidth(normalized.TopLayer()) /
                               repair.MM, 0.3, places=3)
        self.assertAlmostEqual(normalized.GetDrillValue() / repair.MM,
                               0.2, places=3)
        self.assertTrue(normalized.IsLocked())
        pofv_faults = {
            row.get("type") for row in drc.get("violations") or ()
            if any(item.get("uuid") == via_uuid
                   for item in row.get("items") or ())}
        self.assertFalse(
            pofv_faults.intersection({"via_diameter", "drill_out_of_range"}),
            pofv_faults)

    def test_short_smd_dogbone_via_normalizes_to_declared_pofv(self):
        import pcbnew
        import cec_certificate_repair as repair

        board = pcbnew.CreateEmptyBoard()
        properties = board.GetProperties()
        properties["CEC_FAB_PROFILE"] = "jlcpcb_6l_pofv_signal"
        board.SetProperties(properties)
        gnd = pcbnew.NETINFO_ITEM(board, "GND")
        board.Add(gnd)
        footprint = pcbnew.FOOTPRINT(board)
        footprint.SetReference("U1")
        pad = pcbnew.PAD(footprint)
        pad.SetPadName("12")
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(pcbnew.VECTOR2I_MM(0.6, 0.2))
        pad.SetPosition(pcbnew.VECTOR2I_MM(5.0, 5.0))
        pad.SetLayerSet(pcbnew.PAD.SMDMask())
        pad.SetNet(gnd)
        footprint.Add(pad)
        board.Add(footprint)
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(pcbnew.VECTOR2I_MM(5.95, 5.0))
        via.SetWidth(pcbnew.FromMM(0.9))
        via.SetDrill(pcbnew.FromMM(0.5))
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetNet(gnd)
        board.Add(via)
        stub = pcbnew.PCB_TRACK(board)
        stub.SetStart(pad.GetPosition())
        stub.SetEnd(via.GetPosition())
        stub.SetWidth(pcbnew.FromMM(0.2))
        stub.SetLayer(pcbnew.F_Cu)
        stub.SetNet(gnd)
        board.Add(stub)
        via_uuid = repair._uuid(via)

        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "dogbone.kicad_pcb")
            pcbnew.SaveBoard(path, board)
            changed, evidence = \
                repair._normalize_pad_owned_via_to_profile_worker(
                    path, via_uuid)
            saved = pcbnew.LoadBoard(path)
            normalized = next(item for item in saved.GetTracks()
                              if repair._uuid(item) == via_uuid)

            board.Remove(stub)
            evacuated_path = os.path.join(
                directory, "evacuated-dogbone.kicad_pcb")
            pcbnew.SaveBoard(evacuated_path, board)
            snapshot = {
                "net": "GND",
                "start_xy": [pad.GetPosition().x, pad.GetPosition().y],
                "end_xy": [via.GetPosition().x, via.GetPosition().y],
            }
            evacuated_changed, evacuated_evidence = \
                repair._normalize_pad_owned_via_to_profile_worker(
                    evacuated_path, via_uuid, (snapshot,))

        self.assertTrue(changed, evidence)
        self.assertEqual(evidence["ownership_mode"], "local_dogbone")
        self.assertAlmostEqual(normalized.GetWidth(normalized.TopLayer()) /
                               repair.MM, 0.3, places=3)
        self.assertAlmostEqual(normalized.GetDrillValue() / repair.MM,
                               0.2, places=3)
        self.assertTrue(evacuated_changed, evacuated_evidence)
        self.assertEqual(evacuated_evidence["ownership_mode"],
                         "evacuated_local_dogbone")

    def test_structural_identity_filter_ignores_nonroute_geometry_noise(self):
        import cec_certificate_repair as repair

        data = {"violations": [
            {"type": "annular_width", "items": [{"uuid": "via-noise"}]},
            {"type": "clearance", "items": [{"uuid": "track-live"}]},
        ]}
        identities = repair._structural_drc_identities(data)
        self.assertEqual(len(identities), 1)
        self.assertIn("track-live", identities[0])

    def test_negotiation_plan_uses_only_certificate_named_movable_tracks(self):
        import pcbnew
        import cec_certificate_repair as repair

        board = pcbnew.CreateEmptyBoard()
        nets = {}
        for name in ("/OPEN", "/BLOCK", "/USB_D_P"):
            nets[name] = pcbnew.NETINFO_ITEM(board, name)
            board.Add(nets[name])

        def track(net, y):
            item = pcbnew.PCB_TRACK(board)
            item.SetStart(pcbnew.VECTOR2I_MM(2, y))
            item.SetEnd(pcbnew.VECTOR2I_MM(8, y))
            item.SetWidth(pcbnew.FromMM(0.25))
            item.SetLayer(board.GetLayerID("F.Cu"))
            item.SetNet(nets[net])
            board.Add(item)
            return item

        movable = track("/BLOCK", 3)
        protected = track("/USB_D_P", 4)
        with tempfile.TemporaryDirectory() as work:
            path = os.path.join(work, "plan.kicad_pcb")
            pcbnew.SaveBoard(path, board)
            cert = {
                "schema": 1, "net": "/OPEN", "width_mm": 0.25,
                "clearance_mm": 0.2,
                "endpoints": [
                    {"kind": "pad", "ref": "J1", "pad": "1",
                     "x_mm": 1.0, "y_mm": 3.0},
                    {"kind": "pad", "ref": "U1", "pad": "1",
                     "x_mm": 9.0, "y_mm": 3.0},
                ],
                "dominant_blockers": [
                    {"kind": "track", "uuid": repair._uuid(movable),
                     "hit_count": 4},
                    {"kind": "track", "uuid": repair._uuid(protected),
                     "hit_count": 9},
                ],
            }
            payload = {"final_completion": {"refused_details": [
                {"net": "/OPEN", "distance_mm": 8.0,
                 "certificate": cert}]}}
            plan = repair.plan_negotiations(path, payload)

        self.assertEqual(len(plan["windows"]), 1, plan)
        self.assertEqual(plan["windows"][0]["blocker_nets"], ("/BLOCK",))
        self.assertTrue(any(row.get("net") == "/USB_D_P"
                            and row.get("reason") == "coupled_pair"
                            for row in plan["immutable"]), plan)

    def test_generated_locked_blocker_requires_authored_baseline_authority(self):
        import pcbnew
        import cec_certificate_repair as repair

        board = pcbnew.CreateEmptyBoard()
        opened = pcbnew.NETINFO_ITEM(board, "/OPEN")
        blocker = pcbnew.NETINFO_ITEM(board, "/BLOCK")
        board.Add(opened); board.Add(blocker)
        item = pcbnew.PCB_TRACK(board)
        item.SetStart(pcbnew.VECTOR2I_MM(2, 3))
        item.SetEnd(pcbnew.VECTOR2I_MM(8, 3))
        item.SetWidth(pcbnew.FromMM(0.25))
        item.SetLayer(pcbnew.F_Cu)
        item.SetNet(blocker)
        item.SetLocked(True)
        board.Add(item)
        with tempfile.TemporaryDirectory() as work:
            path = os.path.join(work, "locked.kicad_pcb")
            pcbnew.SaveBoard(path, board)
            saved = pcbnew.LoadBoard(path)
            uid = repair._uuid(next(iter(saved.GetTracks())))
            payload = {"unconn_nets": ["/OPEN"], "final_completion": {
                "refused_details": [{
                    "net": "/OPEN", "distance_mm": 6.0,
                    "certificate": {
                        "schema": 1, "net": "/OPEN", "width_mm": 0.25,
                        "clearance_mm": 0.2,
                        "dominant_blockers": [{
                            "kind": "track", "uuid": uid, "hit_count": 3,
                        }],
                    },
                }],
            }}
            denied = repair.plan_negotiations(path, payload)
            allowed = repair.plan_negotiations(
                path, payload, generated_locked_uuids={uid})

        self.assertEqual(denied["windows"], [])
        self.assertEqual(denied["immutable"][0]["reason"], "locked_copper")
        self.assertEqual(allowed["windows"][0]["unlock_uuids"], (uid,))
        self.assertEqual(allowed["generated_locked_authority_count"], 1)

    def test_pofv_vertical_window_names_every_all_layer_track_blocker(self):
        import pcbnew
        import cec_certificate_repair as repair

        board = pcbnew.CreateEmptyBoard()
        props = board.GetProperties()
        props["CEC_FAB_PROFILE"] = "jlcpcb_6l_pofv_signal"
        board.SetProperties(props)
        nets = {}
        for name in ("/OPEN", "/MOVE_A", "/MOVE_B"):
            nets[name] = pcbnew.NETINFO_ITEM(board, name)
            board.Add(nets[name])

        owner = pcbnew.FOOTPRINT(board)
        owner.SetReference("U1")
        pad = pcbnew.PAD(owner)
        pad.SetPadName("25")
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(pcbnew.VECTOR2I_MM(0.8, 0.4))
        pad.SetPosition(pcbnew.VECTOR2I_MM(5.0, 5.0))
        pad.SetLayerSet(pcbnew.PAD.SMDMask())
        pad.SetNet(nets["/OPEN"])
        owner.Add(pad)
        board.Add(owner)

        anchors = pcbnew.FOOTPRINT(board)
        anchors.SetReference("J1")
        for number, net_name, x in (
                ("1", "/MOVE_A", 2.0), ("2", "/MOVE_B", 3.0)):
            anchor = pcbnew.PAD(anchors)
            anchor.SetPadName(number)
            anchor.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            anchor.SetShape(pcbnew.PAD_SHAPE_RECT)
            anchor.SetSize(pcbnew.VECTOR2I_MM(0.5, 0.5))
            anchor.SetPosition(pcbnew.VECTOR2I_MM(x, 2.0))
            anchor.SetLayerSet(pcbnew.PAD.SMDMask())
            anchor.SetNet(nets[net_name])
            anchors.Add(anchor)
        board.Add(anchors)

        def blocker(net, start, end, locked=False):
            item = pcbnew.PCB_TRACK(board)
            item.SetStart(pcbnew.VECTOR2I_MM(*start))
            item.SetEnd(pcbnew.VECTOR2I_MM(*end))
            item.SetWidth(pcbnew.FromMM(0.2))
            item.SetLayer(pcbnew.B_Cu)
            item.SetNet(nets[net])
            item.SetLocked(locked)
            board.Add(item)
            return item

        move_a = blocker("/MOVE_A", (4.0, 5.0), (6.0, 5.0))
        move_b = blocker(
            "/MOVE_B", (5.0, 4.0), (5.0, 6.0), locked=True)
        move_a_uuid = repair._uuid(move_a)
        move_b_uuid = repair._uuid(move_b)
        certificate = {
            "schema": 1, "net": "/OPEN", "width_mm": 0.2,
            "clearance_mm": 0.2,
            "endpoints": [{
                "endpoint": "b", "kind": "pad", "ref": "U1", "pad": "25",
                "x_mm": 5.0, "y_mm": 5.0,
            }],
            "dominant_blockers": [],
        }
        payload = {"unconn_nets": ["/OPEN"], "final_completion": {
            "refused_details": [{
                "net": "/OPEN", "distance_mm": 1.5,
                "certificate": certificate,
            }],
        }}
        with tempfile.TemporaryDirectory() as work:
            path = os.path.join(work, "vertical.kicad_pcb")
            pcbnew.SaveBoard(path, board)
            saved = pcbnew.LoadBoard(path)
            vertical = repair._pofv_endpoint_blocker_rows(
                saved, certificate)
            denied = repair.plan_negotiations(path, payload)
            allowed = repair.plan_negotiations(
                path, payload,
                generated_locked_uuids={move_b_uuid})

        self.assertEqual(len(vertical), 1, vertical)
        self.assertEqual(
            {row["uuid"] for row in vertical[0]["blockers"]},
            {move_a_uuid, move_b_uuid})
        self.assertEqual(denied["windows"], [])
        self.assertTrue(any(
            row.get("uuid") == move_b_uuid
            and row.get("reason") == "locked_copper"
            and row.get("role") == "vertical_pofv_blocker"
            for row in denied["immutable"]), denied)
        self.assertEqual(allowed["pofv_vertical_candidates"], 1)
        self.assertEqual(len(allowed["windows"]), 1, allowed)
        window = allowed["windows"][0]
        self.assertTrue(window["vertical_pofv_escape"])
        self.assertEqual(set(window["blocker_uuids"]),
                         {move_a_uuid, move_b_uuid})
        self.assertEqual(window["unlock_uuids"], (move_b_uuid,))
        self.assertEqual(window["vertical_blocker_layers"], ("B.Cu",))

    def test_generated_endpoint_neckdown_group_remains_negotiable(self):
        import pcbnew
        import cec_certificate_repair as repair

        board = pcbnew.CreateEmptyBoard()
        net = pcbnew.NETINFO_ITEM(board, "/BLOCK")
        board.Add(net)
        item = pcbnew.PCB_TRACK(board)
        item.SetStart(pcbnew.VECTOR2I_MM(2, 3))
        item.SetEnd(pcbnew.VECTOR2I_MM(4, 3))
        item.SetWidth(pcbnew.FromMM(0.2))
        item.SetLayer(pcbnew.F_Cu)
        item.SetNet(net)
        item.SetLocked(True)
        board.Add(item)
        group = pcbnew.PCB_GROUP(board)
        group.SetName(repair.cec_fr.ENDPOINT_NECKDOWN_GROUP)
        board.Add(group)
        group.AddItem(item)
        with tempfile.TemporaryDirectory() as work:
            path = os.path.join(work, "grouped.kicad_pcb")
            pcbnew.SaveBoard(path, board)
            saved = pcbnew.LoadBoard(path)
            uid = repair._uuid(next(iter(saved.GetTracks())))
            payload = {"unconn_nets": ["/OPEN"], "final_completion": {
                "refused_details": [{
                    "net": "/OPEN", "distance_mm": 2.0,
                    "certificate": {
                        "net": "/OPEN", "width_mm": 0.25,
                        "clearance_mm": 0.2,
                        "dominant_blockers": [{
                            "kind": "track", "uuid": uid, "hit_count": 3,
                        }],
                    },
                }],
            }}
            plan = repair.plan_negotiations(
                path, payload, generated_locked_uuids={uid})

        self.assertEqual(plan["windows"][0]["unlock_uuids"], (uid,))

    def test_generated_local_pin_escape_precedes_residual_power_window(self):
        import pcbnew
        import cec_certificate_repair as repair

        board = pcbnew.CreateEmptyBoard()
        nets = {}
        for name in ("/LOCKED_BLOCK", "/POWER_BLOCK"):
            nets[name] = pcbnew.NETINFO_ITEM(board, name)
            board.Add(nets[name])

        def add_track(net, y, locked):
            item = pcbnew.PCB_TRACK(board)
            item.SetStart(pcbnew.VECTOR2I_MM(2, y))
            item.SetEnd(pcbnew.VECTOR2I_MM(8, y))
            item.SetWidth(pcbnew.FromMM(0.25))
            item.SetLayer(pcbnew.F_Cu)
            item.SetNet(nets[net])
            item.SetLocked(locked)
            board.Add(item)
            return item

        locked = add_track("/LOCKED_BLOCK", 2, True)
        power = add_track("/POWER_BLOCK", 4, False)
        with tempfile.TemporaryDirectory() as work:
            path = os.path.join(work, "priority.kicad_pcb")
            pcbnew.SaveBoard(path, board)
            saved = pcbnew.LoadBoard(path)
            by_net = {item.GetNetname(): repair._uuid(item)
                      for item in saved.GetTracks()}

            def detail(net, distance, blocker):
                return {
                    "net": net, "distance_mm": distance,
                    "certificate": {
                        "schema": 1, "net": net, "width_mm": 0.25,
                        "clearance_mm": 0.2,
                        "search": {"escape_probe_mm": 1.25},
                        "endpoints": [
                            {"endpoint": "a", "kind": "pad", "ref": "R1",
                             "pad": "1", "x_mm": 1.0, "y_mm": 2.0},
                            {"endpoint": "b", "kind": "pad", "ref": "U1",
                             "pad": "1", "x_mm": 2.5, "y_mm": 2.0},
                        ],
                        "dominant_blockers": [{
                            "kind": "track", "uuid": by_net[blocker],
                            "hit_count": 2,
                        }],
                    },
                }

            payload = {
                "unconn_nets": ["/LOCAL", "+3V3"],
                "final_completion": {"refused_details": [
                    detail("+3V3", 1.0, "/POWER_BLOCK"),
                    detail("/LOCAL", 2.0, "/LOCKED_BLOCK"),
                ]},
            }
            plan = repair.plan_negotiations(
                path, payload,
                generated_locked_uuids={by_net["/LOCKED_BLOCK"]})

        self.assertEqual([row["net"] for row in plan["windows"]],
                         ["/LOCAL", "+3V3"])
        self.assertTrue(plan["windows"][0]["local_pin_escape"])

    def test_surface_trapped_smd_is_pin_escape_even_with_inner_clear_ray(self):
        import pcbnew
        import cec_certificate_repair as repair

        pad = mock.Mock()
        pad.GetNumber.return_value = "5"
        pad.HasHole.return_value = False
        pad.IsOnLayer.side_effect = lambda layer: layer == pcbnew.F_Cu
        footprint = mock.Mock()
        footprint.Pads.return_value = [pad]
        board = mock.Mock()
        board.FindFootprintByReference.return_value = footprint
        certificate = {
            "endpoints": [{
                "endpoint": "b", "kind": "pad", "ref": "U4", "pad": "5",
            }],
            "layers": [
                {"layer": "F.Cu", "endpoint_escape": [{
                    "endpoint": "b", "clear_rays": [],
                }]},
                {"layer": "SIG2", "endpoint_escape": [{
                    "endpoint": "b", "clear_rays": ["N"],
                }]},
            ],
        }
        self.assertEqual(
            repair._surface_trapped_endpoint_labels(board, certificate),
            {"b"})

    def test_generated_locked_authority_does_not_override_pair_policy(self):
        import pcbnew
        import cec_certificate_repair as repair

        board = pcbnew.CreateEmptyBoard()
        opened = pcbnew.NETINFO_ITEM(board, "/OPEN")
        pair = pcbnew.NETINFO_ITEM(board, "/USB_D_P")
        board.Add(opened); board.Add(pair)
        item = pcbnew.PCB_TRACK(board)
        item.SetStart(pcbnew.VECTOR2I_MM(2, 3))
        item.SetEnd(pcbnew.VECTOR2I_MM(8, 3))
        item.SetWidth(pcbnew.FromMM(0.25))
        item.SetLayer(pcbnew.F_Cu)
        item.SetNet(pair)
        item.SetLocked(True)
        board.Add(item)
        with tempfile.TemporaryDirectory() as work:
            path = os.path.join(work, "pair.kicad_pcb")
            pcbnew.SaveBoard(path, board)
            saved = pcbnew.LoadBoard(path)
            uid = repair._uuid(next(iter(saved.GetTracks())))
            payload = {"unconn_nets": ["/OPEN"], "final_completion": {
                "refused_details": [{
                    "net": "/OPEN", "distance_mm": 6.0,
                    "certificate": {
                        "schema": 1, "net": "/OPEN", "width_mm": 0.25,
                        "clearance_mm": 0.2,
                        "dominant_blockers": [{
                            "kind": "track", "uuid": uid, "hit_count": 3,
                        }],
                    },
                }],
            }}
            plan = repair.plan_negotiations(
                path, payload, generated_locked_uuids={uid})

        self.assertEqual(plan["windows"], [])
        self.assertEqual(plan["immutable"][0]["reason"], "coupled_pair")

    def test_negotiation_plan_prioritizes_trapped_pin_escape(self):
        import pcbnew
        import cec_certificate_repair as repair

        board = pcbnew.CreateEmptyBoard()
        blocker_net = pcbnew.NETINFO_ITEM(board, "/BLOCK")
        board.Add(blocker_net)
        blockers = []
        for y in (2, 4):
            item = pcbnew.PCB_TRACK(board)
            item.SetStart(pcbnew.VECTOR2I_MM(2, y))
            item.SetEnd(pcbnew.VECTOR2I_MM(8, y))
            item.SetWidth(pcbnew.FromMM(0.25))
            item.SetLayer(pcbnew.F_Cu)
            item.SetNet(blocker_net)
            board.Add(item)
            blockers.append(item)

        def detail(net, item, rays):
            return {
                "net": net, "distance_mm": 1.0,
                "certificate": {
                    "schema": 1, "net": net, "width_mm": 0.25,
                    "clearance_mm": 0.2,
                    "layers": [{"endpoint_escape": [
                        {"endpoint": "A", "clear_rays": rays},
                        {"endpoint": "B", "clear_rays": rays},
                    ]}],
                    "dominant_blockers": [{
                        "kind": "track", "uuid": repair._uuid(item),
                        "hit_count": 2,
                    }],
                },
            }

        payload = {
            "unconn_nets": ["/FREE", "/TRAPPED"],
            "final_completion": {"refused_details": [
                detail("/FREE", blockers[0], ["E"]),
                detail("/TRAPPED", blockers[1], []),
            ]},
        }
        with tempfile.TemporaryDirectory() as work:
            path = os.path.join(work, "trapped.kicad_pcb")
            pcbnew.SaveBoard(path, board)
            plan = repair.plan_negotiations(path, payload)

        self.assertEqual([row["net"] for row in plan["windows"]],
                         ["/TRAPPED", "/FREE"])

    def test_generated_locked_snapshot_is_exact_and_restored_locked(self):
        import pcbnew
        import cec_certificate_repair as repair

        board = pcbnew.CreateEmptyBoard()
        net = pcbnew.NETINFO_ITEM(board, "/BLOCK")
        board.Add(net)
        items = []
        for x0, x1 in ((1, 2), (2, 3), (3, 4)):
            item = pcbnew.PCB_TRACK(board)
            item.SetStart(pcbnew.VECTOR2I_MM(x0, 2))
            item.SetEnd(pcbnew.VECTOR2I_MM(x1, 2))
            item.SetWidth(pcbnew.FromMM(0.25))
            item.SetLayer(pcbnew.F_Cu)
            item.SetNet(net)
            item.SetLocked(True)
            board.Add(item)
            items.append(item)
        target = items[1]
        with tempfile.TemporaryDirectory() as work:
            path = os.path.join(work, "restore.kicad_pcb")
            pcbnew.SaveBoard(path, board)
            snapshot, refusal = repair._snapshot_displaced_branch(
                board, repair._uuid(target), max_hops=2,
                allow_generated_locked=True)
            self.assertIsNone(refusal)
            self.assertEqual(snapshot["removed_uuids"],
                             (repair._uuid(target),))
            self.assertTrue(snapshot["relock"])
            board.Remove(target)
            board.BuildConnectivity()
            restored, evidence = repair._restore_displaced_branch(
                board, snapshot, board_path=path, maze_margin_mm=2.0)

        self.assertTrue(restored, evidence)
        restored_items = [item for item in board.GetTracks()
                          if item.GetNetname() == "/BLOCK"
                          and repair._uuid(item) not in {
                              repair._uuid(items[0]), repair._uuid(items[2])}]
        self.assertTrue(restored_items)
        self.assertTrue(all(item.IsLocked() for item in restored_items))

    def test_restore_falls_back_to_live_net_topology_and_relocks(self):
        import pcbnew
        import cec_certificate_repair as repair

        board = pcbnew.CreateEmptyBoard()
        net = pcbnew.NETINFO_ITEM(board, "/BLOCK")
        board.Add(net)
        snapshot_row = {
            "requested_uuid": "old-segment", "net": "/BLOCK",
            "net_code": net.GetNetCode(), "layer": pcbnew.F_Cu,
            "width": pcbnew.FromMM(0.25), "start_escape": None,
            "end_escape": None, "source_length_nm": 2_000_000,
            "removed_uuids": ("old-segment",), "relock": True,
            "start_xy": [pcbnew.FromMM(1), pcbnew.FromMM(2)],
            "end_xy": [pcbnew.FromMM(3), pcbnew.FromMM(2)],
        }

        def close_live_net(live_board, **_kwargs):
            item = pcbnew.PCB_TRACK(live_board)
            item.SetStart(pcbnew.VECTOR2I_MM(1, 2))
            item.SetEnd(pcbnew.VECTOR2I_MM(3, 2))
            item.SetWidth(pcbnew.FromMM(0.25))
            item.SetLayer(pcbnew.F_Cu)
            item.SetNet(net)
            live_board.Add(item)
            return {"closed": 1, "refused": 0,
                    "closed_details": [{"net": "/BLOCK"}]}

        with mock.patch.object(
                repair, "_restore_displaced_branch",
                return_value=(False, {"refusal":
                                      "displaced_branch_unrestorable"})), \
                mock.patch.object(
                    repair.cec_fr, "_project_netclass_resolver",
                    return_value=lambda _net: {}), \
                mock.patch.object(
                    repair.cec_fr, "synthesize_lastmile",
                    side_effect=close_live_net):
            restored, evidence = repair._restore_negotiation_blockers(
                board, [snapshot_row], board_path="board.kicad_pcb",
                maze_margin_mm=4.0, max_detour_ratio=2.0)

        self.assertTrue(restored, evidence)
        self.assertEqual(evidence["restored"][0]["mode"],
                         "network_lastmile")
        self.assertEqual(evidence["restored"][0]["branch_refusal"][
            "refusal"], "displaced_branch_unrestorable")
        self.assertTrue(all(item.IsLocked() for item in board.GetTracks()))

    def test_restore_can_route_easiest_branch_first(self):
        import pcbnew
        import cec_certificate_repair as repair

        def snapshot(net, width_mm, length_mm, x_mm):
            return {
                "requested_uuid": net, "net": net, "net_code": 1,
                "layer": pcbnew.F_Cu,
                "width": pcbnew.FromMM(width_mm),
                "start_escape": None, "end_escape": None,
                "source_length_nm": pcbnew.FromMM(length_mm),
                "removed_uuids": (net,), "relock": False,
                "start_xy": [pcbnew.FromMM(x_mm), pcbnew.FromMM(1)],
                "end_xy": [pcbnew.FromMM(x_mm + length_mm),
                           pcbnew.FromMM(1)],
            }

        rows = [snapshot("/WIDE", 0.50, 8.0, 1.0),
                snapshot("/NARROW", 0.20, 2.0, 12.0)]
        order = []

        def restore_branch(_board, item, **_kwargs):
            order.append(item["net"])
            return True, {"net": item["net"], "mode": "same_layer"}

        board = mock.Mock()
        with mock.patch.object(
                repair, "_restore_displaced_branch",
                side_effect=restore_branch):
            restored, evidence = repair._restore_negotiation_blockers(
                board, rows, board_path="board.kicad_pcb",
                maze_margin_mm=4.0, max_detour_ratio=2.0,
                order_mode="easiest_first")

        self.assertTrue(restored, evidence)
        self.assertEqual(order, ["/NARROW", "/WIDE"])
        self.assertEqual(evidence["order_mode"], "easiest_first")

    def test_restore_tries_exact_boundaries_before_grouped_net_fallback(self):
        import pcbnew
        import cec_certificate_repair as repair

        def row(uid, length_mm):
            return {
                "requested_uuid": uid, "net": "/SCL", "net_code": 1,
                "layer": pcbnew.F_Cu, "width": pcbnew.FromMM(0.25),
                "start_escape": None, "end_escape": None,
                "source_length_nm": pcbnew.FromMM(length_mm),
                "removed_uuids": (uid,), "relock": True,
                "endpoint_neckdown_group": False,
                "start_xy": [pcbnew.FromMM(1), pcbnew.FromMM(1)],
                "end_xy": [pcbnew.FromMM(2), pcbnew.FromMM(1)],
            }

        board = mock.Mock()
        with mock.patch.object(
                repair, "_restore_displaced_net",
                return_value=(True, {"net": "/SCL",
                                     "mode": "network_lastmile"})) as live, \
                mock.patch.object(
                    repair, "_restore_displaced_branch",
                    return_value=(True, {"net": "/SCL",
                                         "mode": "same_layer"})) as exact:
            restored, evidence = repair._restore_negotiation_blockers(
                board, [row("a", 1.0), row("b", 2.0)],
                board_path="board.kicad_pcb", maze_margin_mm=4.0,
                max_detour_ratio=2.0)

        self.assertTrue(restored, evidence)
        self.assertEqual(exact.call_count, 2)
        live.assert_not_called()
        self.assertEqual(evidence["restored"][0]["snapshot_count"], 2)
        self.assertEqual(evidence["restored"][0]["mode"],
                         "boundary_group_lastmile")

    def test_restore_groups_live_topology_only_after_boundary_refusal(self):
        import pcbnew
        import cec_certificate_repair as repair

        def row(uid, x_mm):
            return {
                "requested_uuid": uid, "net": "/SCL", "net_code": 1,
                "layer": pcbnew.F_Cu, "width": pcbnew.FromMM(0.25),
                "start_escape": None, "end_escape": None,
                "source_length_nm": pcbnew.FromMM(1.0),
                "removed_uuids": (uid,), "relock": False,
                "endpoint_neckdown_group": False,
                "start_xy": [pcbnew.FromMM(x_mm), pcbnew.FromMM(1)],
                "end_xy": [pcbnew.FromMM(x_mm + 1), pcbnew.FromMM(1)],
            }

        board = mock.Mock()
        with mock.patch.object(
                repair, "_restore_displaced_branch",
                side_effect=[
                    (True, {"net": "/SCL", "mode": "same_layer"}),
                    (False, {"net": "/SCL",
                             "refusal": "displaced_branch_unrestorable"}),
                ]) as exact, mock.patch.object(
                    repair, "_restore_displaced_net",
                    return_value=(True, {"net": "/SCL",
                                         "mode": "network_lastmile"})) as live:
            restored, evidence = repair._restore_negotiation_blockers(
                board, [row("a", 1.0), row("b", 3.0)],
                board_path="board.kicad_pcb", maze_margin_mm=4.0,
                max_detour_ratio=2.0)

        self.assertTrue(restored, evidence)
        self.assertEqual(exact.call_count, 2)
        live.assert_called_once()
        combined = live.call_args.args[1]
        self.assertEqual(set(combined["removed_uuids"]), {"a", "b"})
        self.assertEqual(evidence["restored"][0]["snapshot_count"], 2)
        self.assertEqual(evidence["restored"][0]["mode"],
                         "network_group_lastmile")

    def test_restore_prioritizes_pin_boundary_inside_same_net_group(self):
        import pcbnew
        import cec_certificate_repair as repair

        def row(uid, length_mm, escape=None):
            return {
                "requested_uuid": uid, "net": "/SDA", "net_code": 1,
                "layer": pcbnew.F_Cu, "width": pcbnew.FromMM(0.22),
                "start_escape": escape, "end_escape": None,
                "source_length_nm": pcbnew.FromMM(length_mm),
                "removed_uuids": (uid,), "relock": False,
                "endpoint_neckdown_group": bool(escape),
                "start_xy": [pcbnew.FromMM(1), pcbnew.FromMM(1)],
                "end_xy": [pcbnew.FromMM(2), pcbnew.FromMM(1)],
            }

        order = []

        def exact(_board, item, **_kwargs):
            order.append(item["requested_uuid"])
            return True, {"net": item["net"], "mode": "same_layer"}

        board = mock.Mock()
        with mock.patch.object(
                repair, "_restore_displaced_branch", side_effect=exact), \
                mock.patch.object(repair, "_restore_displaced_net") as live:
            restored, evidence = repair._restore_negotiation_blockers(
                board, [row("long", 20.0),
                        row("pin", 2.0, (150_000, 1_000_000))],
                board_path="board.kicad_pcb", maze_margin_mm=4.0,
                max_detour_ratio=2.0)

        self.assertTrue(restored, evidence)
        self.assertEqual(order, ["pin", "long"])
        live.assert_not_called()

    def test_negotiation_plan_drops_intermediate_refusal_after_final_close(self):
        import cec_certificate_repair as repair

        payload = {
            "unconn_nets": ["/STILL_OPEN"],
            "final_completion": {"refused_details": [{
                "net": "/ALREADY_CLOSED", "distance_mm": 2.0,
                "certificate": {"schema": 1, "net": "/ALREADY_CLOSED",
                                "dominant_blockers": []},
            }]},
        }
        with mock.patch.object(repair.pcbnew, "LoadBoard") as load:
            load.return_value.GetTracks.return_value = []
            plan = repair.plan_negotiations("board.kicad_pcb", payload)
        self.assertEqual(plan["windows"], [])

    def test_negotiation_plan_prioritizes_reference_continuity(self):
        import pcbnew
        import cec_certificate_repair as repair

        board = pcbnew.CreateEmptyBoard()
        blockers = []
        for index, name in enumerate(("/BLOCK_GND", "/BLOCK_GPIO")):
            net = pcbnew.NETINFO_ITEM(board, name)
            board.Add(net)
            item = pcbnew.PCB_TRACK(board)
            item.SetStart(pcbnew.VECTOR2I_MM(2, 2 + index))
            item.SetEnd(pcbnew.VECTOR2I_MM(8, 2 + index))
            item.SetWidth(pcbnew.FromMM(0.25))
            item.SetLayer(pcbnew.F_Cu)
            item.SetNet(net)
            board.Add(item)
            blockers.append(item)

        details = []
        # Give GPIO the shorter gap so role ordering, rather than distance,
        # must promote ground reference continuity.
        for net, distance, blocker in (
                ("/GPIO", 1.0, blockers[1]),
                ("GND", 8.0, blockers[0])):
            details.append({
                "net": net, "distance_mm": distance,
                "certificate": {
                    "schema": 1, "net": net, "width_mm": 0.25,
                    "clearance_mm": 0.2,
                    "endpoints": [
                        {"kind": "pad", "ref": "J1", "pad": "1",
                         "x_mm": 1.0, "y_mm": 2.0},
                        {"kind": "pad", "ref": "U1", "pad": "1",
                         "x_mm": 9.0, "y_mm": 2.0},
                    ],
                    "dominant_blockers": [{
                        "kind": "track", "uuid": repair._uuid(blocker),
                        "hit_count": 2,
                    }],
                },
            })
        payload = {
            "unconn_nets": ["/GPIO", "GND"],
            "final_completion": {"refused_details": details},
        }
        with tempfile.TemporaryDirectory() as work:
            path = os.path.join(work, "priority.kicad_pcb")
            pcbnew.SaveBoard(path, board)
            plan = repair.plan_negotiations(path, payload)

        self.assertEqual([row["net"] for row in plan["windows"]],
                         ["GND", "/GPIO"])

    def test_overlapping_degree2_blocker_snapshots_coalesce(self):
        import pcbnew
        import cec_certificate_repair as repair

        board = pcbnew.CreateEmptyBoard()
        net = pcbnew.NETINFO_ITEM(board, "/BLOCK")
        board.Add(net)

        def track(x0, x1):
            item = pcbnew.PCB_TRACK(board)
            item.SetStart(pcbnew.VECTOR2I_MM(x0, 2))
            item.SetEnd(pcbnew.VECTOR2I_MM(x1, 2))
            item.SetWidth(pcbnew.FromMM(0.25))
            item.SetLayer(board.GetLayerID("F.Cu"))
            item.SetNet(net); board.Add(item)
            return item

        a, b, c = track(1, 2), track(2, 3), track(3, 4)
        common = {"net": "/BLOCK", "net_code": net.GetNetCode(),
                  "layer": board.GetLayerID("F.Cu"),
                  "width": pcbnew.FromMM(0.25), "start_escape": None,
                  "end_escape": None, "source_length_nm": 2_000_000}
        rows = [
            {**common, "requested_uuid": repair._uuid(a),
             "removed_uuids": (repair._uuid(a), repair._uuid(b)),
             "_track_objects": (a, b)},
            {**common, "requested_uuid": repair._uuid(c),
             "removed_uuids": (repair._uuid(b), repair._uuid(c)),
             "_track_objects": (b, c)},
        ]
        merged, refusal = repair._merge_overlapping_snapshots(rows)
        self.assertIsNone(refusal)
        self.assertEqual(len(merged), 1)
        self.assertEqual(set(merged[0]["removed_uuids"]),
                         {repair._uuid(a), repair._uuid(b), repair._uuid(c)})

    def test_adjacent_generated_blockers_coalesce_without_junction(self):
        import pcbnew
        import cec_certificate_repair as repair

        board = pcbnew.CreateEmptyBoard()
        net = pcbnew.NETINFO_ITEM(board, "/BLOCK")
        board.Add(net)

        def track(x0, y0, x1, y1):
            item = pcbnew.PCB_TRACK(board)
            item.SetStart(pcbnew.VECTOR2I_MM(x0, y0))
            item.SetEnd(pcbnew.VECTOR2I_MM(x1, y1))
            item.SetWidth(pcbnew.FromMM(0.25))
            item.SetLayer(pcbnew.F_Cu)
            item.SetNet(net); board.Add(item)
            return item

        a = track(1, 2, 2, 2)
        b = track(2, 2, 3, 2)
        common = {"net": "/BLOCK", "net_code": net.GetNetCode(),
                  "layer": pcbnew.F_Cu, "width": pcbnew.FromMM(0.25),
                  "start_escape": None, "end_escape": None,
                  "source_length_nm": 1_000_000, "relock": True}
        rows = [{
            **common, "requested_uuid": repair._uuid(item),
            "removed_uuids": (repair._uuid(item),),
            "_track_objects": (item,),
        } for item in (a, b)]

        merged, refusal = repair._merge_overlapping_snapshots(
            rows, board=board)
        self.assertIsNone(refusal)
        self.assertEqual(len(merged), 1)
        self.assertEqual(set(merged[0]["removed_uuids"]),
                         {repair._uuid(a), repair._uuid(b)})
        self.assertTrue(merged[0]["relock"])

    def test_adjacent_generated_blockers_do_not_bypass_junction(self):
        import pcbnew
        import cec_certificate_repair as repair

        board = pcbnew.CreateEmptyBoard()
        net = pcbnew.NETINFO_ITEM(board, "/BLOCK")
        board.Add(net)

        def track(x0, y0, x1, y1):
            item = pcbnew.PCB_TRACK(board)
            item.SetStart(pcbnew.VECTOR2I_MM(x0, y0))
            item.SetEnd(pcbnew.VECTOR2I_MM(x1, y1))
            item.SetWidth(pcbnew.FromMM(0.25))
            item.SetLayer(pcbnew.F_Cu)
            item.SetNet(net); board.Add(item)
            return item

        a = track(1, 2, 2, 2)
        b = track(2, 2, 3, 2)
        track(2, 2, 2, 3)
        common = {"net": "/BLOCK", "net_code": net.GetNetCode(),
                  "layer": pcbnew.F_Cu, "width": pcbnew.FromMM(0.25),
                  "start_escape": None, "end_escape": None,
                  "source_length_nm": 1_000_000, "relock": True}
        rows = [{
            **common, "requested_uuid": repair._uuid(item),
            "removed_uuids": (repair._uuid(item),),
            "_track_objects": (item,),
        } for item in (a, b)]

        merged, refusal = repair._merge_overlapping_snapshots(
            rows, board=board)
        self.assertIsNone(refusal)
        self.assertEqual(len(merged), 2)

    def test_production_hook_adopts_isolated_repair_artifact(self):
        import cec_synth_pipeline as pipeline

        completion = {"final_completion": {"refused_details": [
            {"net": "/OPEN", "certificate": {"schema": 1,
             "net": "/OPEN", "dominant_blockers": []}}]}}
        with tempfile.TemporaryDirectory() as work:
            source = os.path.join(work, "source.kicad_pcb")
            with open(source, "w", encoding="utf-8") as sink:
                sink.write("source")

            def run(command, **_kwargs):
                repaired = command[3]
                report = command[command.index("--report") + 1]
                with open(repaired, "w", encoding="utf-8") as sink:
                    sink.write("repaired")
                with open(report, "w", encoding="utf-8") as sink:
                    json.dump({"schema": 1, "changed": True,
                               "improvement": {"drc": -1},
                               "wall_s": 0.1}, sink)
                return SimpleNamespace(returncode=0, stdout="", stderr="")

            with mock.patch.object(pipeline.subprocess, "run",
                                   side_effect=run) as run_mock:
                output, report = pipeline._route_oracle_certificate_repair(
                    source, completion, work)
            self.assertNotEqual(output, source)
            self.assertTrue(report["changed"])
            with open(output, encoding="utf-8") as result:
                self.assertEqual(result.read(), "repaired")
            command = run_mock.call_args.args[0]
            self.assertIn("--max-windows", command)
            self.assertIn("--max-blockers-per-window", command)
            self.assertIn("--max-attempts", command)
            self.assertIn("--wall-budget-s", command)
            self.assertIn("--no-deep-retry", command)
            child_env = run_mock.call_args.kwargs["env"]
            self.assertGreaterEqual(
                float(child_env["CEC_CERTIFICATE_WORKER_TIMEOUT_S"]), 120.0)

    def test_production_hook_forwards_authored_baseline(self):
        import cec_synth_pipeline as pipeline

        completion = {"final_completion": {"refused_details": [
            {"net": "/OPEN", "certificate": {"schema": 1,
             "net": "/OPEN", "dominant_blockers": []}}]}}
        with tempfile.TemporaryDirectory() as work:
            source = os.path.join(work, "source.kicad_pcb")
            baseline = os.path.join(work, "placed.kicad_pcb")
            for path in (source, baseline):
                with open(path, "w", encoding="utf-8") as sink:
                    sink.write(path)

            def run(command, **_kwargs):
                report = command[command.index("--report") + 1]
                with open(report, "w", encoding="utf-8") as sink:
                    json.dump({"schema": 1, "changed": False}, sink)
                return SimpleNamespace(returncode=0, stdout="", stderr="")

            with mock.patch.object(pipeline.subprocess, "run",
                                   side_effect=run) as run_mock:
                pipeline._route_oracle_certificate_repair(
                    source, completion, work,
                    authored_baseline=baseline)

        command = run_mock.call_args.args[0]
        self.assertEqual(command[command.index("--authored-baseline") + 1],
                         baseline)

    def test_production_hook_times_out_without_mutating_caller_board(self):
        import subprocess
        import cec_synth_pipeline as pipeline

        completion = {"final_completion": {"refused_details": [
            {"net": "/OPEN", "certificate": {"schema": 1,
             "net": "/OPEN", "dominant_blockers": []}}]}}
        with tempfile.TemporaryDirectory() as work:
            source = os.path.join(work, "source.kicad_pcb")
            with open(source, "w", encoding="utf-8") as sink:
                sink.write("source")
            with mock.patch.object(
                    pipeline.subprocess, "run",
                    side_effect=subprocess.TimeoutExpired("repair", 7)):
                output, report = pipeline._route_oracle_certificate_repair(
                    source, completion, work, timeout_s=7)
        self.assertEqual(output, source)
        self.assertEqual(report["skipped"], "timeout")
        self.assertEqual(report["timeout_s"], 7)

    def test_production_hook_skips_certificate_free_board(self):
        import cec_synth_pipeline as pipeline

        with mock.patch.object(pipeline.subprocess, "run") as run:
            output, report = pipeline._route_oracle_certificate_repair(
                "board.kicad_pcb", {}, ".")
        self.assertEqual(output, "board.kicad_pcb")
        self.assertEqual(report["skipped"], "no_refusal_certificates")
        run.assert_not_called()

    def test_atomic_negotiation_inherits_coordinated_worker_budget(self):
        import cec_certificate_repair as repair

        with mock.patch.dict(
                os.environ,
                {"CEC_CERTIFICATE_WORKER_TIMEOUT_S": "120"}, clear=False):
            self.assertEqual(
                repair._atomic_negotiation_timeout_s(12, 4.0), 120.0)
            self.assertEqual(
                repair._atomic_negotiation_timeout_s(4, 12.0), 120.0)

        with mock.patch.dict(
                os.environ,
                {"CEC_CERTIFICATE_NEGOTIATION_TIMEOUT_S": "35"}, clear=False):
            self.assertEqual(
                repair._atomic_negotiation_timeout_s(12, 4.0), 35.0)
            self.assertEqual(
                repair._atomic_negotiation_timeout_s(4, 12.0), 45.0)

    def test_moved_cell_support_budget_scales_past_single_net_cap(self):
        import cec_certificate_repair as repair

        with mock.patch.dict(
                os.environ,
                {"CEC_CERTIFICATE_WORKER_TIMEOUT_S": "240"}, clear=False):
            self.assertEqual(
                repair._support_completion_timeout_s(1, 24, 8.0), 240.0)
            self.assertEqual(
                repair._support_completion_timeout_s(9, 24, 8.0), 255.0)

        with mock.patch.dict(
                os.environ,
                {"CEC_CERTIFICATE_WORKER_TIMEOUT_S": "90"}, clear=False):
            self.assertEqual(
                repair._support_completion_timeout_s(1, 24, 8.0), 90.0)
            self.assertEqual(
                repair._support_completion_timeout_s(9, 24, 8.0), 255.0)


class TestNegotiationTelemetry(unittest.TestCase):
    def test_route_problem_publishes_bounded_deterministic_trace(self):
        import cec_coord_router as router

        conns = [
            ("/A", (0, 1, 0), (0, 1, 4)),
            ("/B", (0, 0, 2), (0, 2, 2)),
        ]
        kwargs = dict(backend="cpu", L=2, grid_mm=0.5, iters=5,
                      cost_mode="fixed", early_stop_plateau=True,
                      plateau_patience=2)
        first = router.route_problem(conns, 3, 5, **kwargs)
        second = router.route_problem(conns, 3, 5, **kwargs)
        self.assertEqual(first["paths_by_conn"], second["paths_by_conn"])
        self.assertEqual(first["negotiation"], second["negotiation"])
        trace = first["negotiation"]["trace"]
        self.assertLessEqual(len(trace), 64)
        self.assertTrue(trace)
        self.assertIn("best_iteration", first["negotiation"])
        self.assertIn("stall_age", first["negotiation"])

    def test_multiresolution_keeps_fine_level_authoritative(self):
        import cec_route_preflight as preflight

        def report_for(_board, *, grid_mm, **_kwargs):
            return {
                "gate": grid_mm <= 0.5,
                "critical_routes": {"critical_routes_ok": True},
                "route_reservations": {"enabled": False},
                "congestion": {
                    "backend": "cpu", "wall_s": grid_mm,
                    "iters": 2, "unroutable_count": int(grid_mm > 0.5),
                    "residual_overuse": grid_mm * 10,
                    "residual_overuse_escaped": grid_mm * 5,
                    "hotspots": [],
                    "negotiation": {"plateau": False,
                                    "best_iteration": 1, "stall_age": 0},
                },
                "wall_s": grid_mm,
            }

        with mock.patch.object(preflight, "analyze",
                               side_effect=report_for) as analyze_mock:
            result = preflight.analyze_multiresolution(
                "board.kicad_pcb", grid_mm=0.5, iters=4,
                coarse_factor=2.0)
        self.assertTrue(result["gate"])
        levels = result["multiresolution"]["levels"]
        self.assertEqual([row["grid_mm"] for row in levels], [1.0, 0.5])
        self.assertFalse(levels[0]["authoritative"])
        self.assertTrue(levels[1]["authoritative"])
        self.assertFalse(result["multiresolution"]["agreement"])
        self.assertIsNone(
            analyze_mock.call_args_list[0].kwargs[
                "compiled_priority_routes"])
        self.assertEqual(
            analyze_mock.call_args_list[1].kwargs[
                "compiled_priority_routes"],
            ({"critical_routes_ok": True}, {"enabled": False}))


class TestIterativePlacementRepair(unittest.TestCase):
    def test_rehydrated_candidate_measures_baseline_before_monotonic_key(self):
        import cec_synth_pipeline as pipeline

        start = SimpleNamespace(route_preflight={})
        measured = SimpleNamespace(route_preflight={
            "critical_pair_refused_count": 1,
            "residual_overuse": 10,
        })
        improved = SimpleNamespace(route_preflight={
            "critical_pair_refused_count": 0,
            "residual_overuse": 9,
        })
        with mock.patch.object(
                pipeline, "rerank_route_preflight",
                return_value=[measured]) as rerank, \
                mock.patch.object(
                    pipeline, "repair_route_preflight",
                    side_effect=[
                        (improved, {"accepted": True,
                                    "move": {"ref": "R1"}}),
                        (improved, {"accepted": False,
                                    "reason": "no_improvement"}),
                    ]):
            result, report = pipeline.repair_route_preflight_iterative(
                SimpleNamespace(), start, rounds=2)
        rerank.assert_called_once()
        self.assertIs(result, improved)
        self.assertEqual(report["accepted_count"], 1)
        self.assertEqual(report["stop_reason"], "no_improvement")

    def test_remeasures_until_first_non_acceptance(self):
        import cec_synth_pipeline as pipeline

        def candidate(overuse):
            return SimpleNamespace(
                route_preflight={
                    "fanout_blocked_count": 0,
                    "pin_access_blocked_count": 0,
                    "unroutable_count": 0,
                    "residual_overuse_escaped": overuse,
                    "residual_overuse": overuse,
                })

        start, first, second = candidate(10), candidate(8), candidate(7)
        responses = [
            (first, {"accepted": True, "move": {"ref": "R1"}}),
            (second, {"accepted": True, "move": {"ref": "R2"}}),
            (second, {"accepted": False, "reason": "no_improvement"}),
        ]
        with mock.patch.object(pipeline, "repair_route_preflight",
                               side_effect=responses):
            result, report = pipeline.repair_route_preflight_iterative(
                SimpleNamespace(), start, rounds=5)
        self.assertIs(result, second)
        self.assertEqual(report["accepted_count"], 2)
        self.assertEqual(report["rounds_run"], 3)
        self.assertEqual(report["stop_reason"], "no_improvement")
        self.assertEqual([row.get("move", {}).get("ref")
                          for row in result.route_repair_history[:2]],
                         ["R1", "R2"])


class TestViaCandidateScheduling(unittest.TestCase):
    def test_finite_prefix_covers_full_radius_ladder_away_from_conflict(self):
        import cec_certificate_repair as repair

        target = repair.ViaRepairTarget(
            uuid="via", net="/S", x_nm=0, y_nm=0,
            diameter_nm=600_000, drill_nm=300_000,
            away_dx=0, away_dy=1, counterpart_uuids=(),
            drc_types=(), priority=())
        candidates = list(repair._via_offset_candidates(target))

        self.assertEqual(
            [row[2] for row in candidates[:7]],
            [0.20, 0.30, 0.45, 0.60, 0.80, 1.00, 1.40])
        self.assertEqual(
            {row[3] for row in candidates[:7]}, {(0, 1)})
        self.assertNotEqual(candidates[7][3], (0, 1))

    def test_congestion_prefix_includes_anisotropic_owner_escape(self):
        import cec_certificate_repair as repair

        target = repair.ViaRepairTarget(
            uuid="via", net="/SDA", x_nm=0, y_nm=0,
            diameter_nm=350_000, drill_nm=250_000,
            away_dx=1, away_dy=-1, counterpart_uuids=(),
            drc_types=(), priority=())
        candidates = list(repair._congestion_via_offset_candidates(
            target, owner_directions=((-1, -1), (0, -1))))

        self.assertIn((-800_000, -450_000),
                      [(row[0], row[1]) for row in candidates[:8]])
        self.assertIn((-450_000, -800_000),
                      [(row[0], row[1]) for row in candidates[:8]])


if __name__ == "__main__":
    unittest.main()
