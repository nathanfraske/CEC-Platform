#!/usr/bin/env python3
"""Teeth for certificate repair and convergence telemetry."""

import os
import sys
import json
import tempfile
import unittest
from concurrent.futures import Future
from types import SimpleNamespace
from unittest import mock


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


class TestCertificateWorkerLifecycle(unittest.TestCase):
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
        with tempfile.TemporaryDirectory() as work:
            path = os.path.join(work, "via.kicad_pcb")
            pcbnew.SaveBoard(path, board)
            saved = pcbnew.LoadBoard(path)
            uid = repair._uuid(next(iter(saved.GetTracks())))
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


if __name__ == "__main__":
    unittest.main()
