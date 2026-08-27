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


class TestCertificateRepairPolicy(unittest.TestCase):
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
