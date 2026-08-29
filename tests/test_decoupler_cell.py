import json
import os
import pickle
import tempfile
import sys
import unittest
from unittest import mock
from types import SimpleNamespace


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

try:
    import pcbnew
    import cec_decoupler_cell as cell
    HAVE_PCBNEW = True
except ImportError:
    HAVE_PCBNEW = False


@unittest.skipUnless(HAVE_PCBNEW, "pcbnew required")
class DecouplerCellTests(unittest.TestCase):
    def test_assigned_cell_order_is_electrical_not_serialization_order(self):
        class Owner:
            def __init__(self, pad_count):
                self._pads = [object()] * pad_count

            def Pads(self):
                return list(self._pads)

        class Board:
            owners = {"U2": Owner(8), "U10": Owner(10)}

            def FindFootprintByReference(self, ref):
                return self.owners.get(ref)

        rows = {
            "tja-vio": {
                "cap_ref": "C8",
                "requirement": {
                    "ref": "U2", "pin": "5", "return_rail": "+5VSB",
                },
            },
            "tja-vcc": {
                "cap_ref": "C4",
                "requirement": {
                    "ref": "U2", "pin": "3", "return_rail": "GND",
                },
            },
            "ina": {
                "cap_ref": "C10",
                "requirement": {
                    "ref": "U10", "pin": "6", "return_rail": "GND",
                },
            },
        }
        forward = {key: rows[key] for key in rows}
        reverse = {key: rows[key] for key in reversed(rows)}

        first = cell._ordered_assigned_cells(Board(), {"assigned": forward})
        second = cell._ordered_assigned_cells(Board(), {"assigned": reverse})

        self.assertEqual(
            [row["cap_ref"] for row in first], ["C4", "C8", "C10"])
        self.assertEqual(
            [row["cap_ref"] for row in first],
            [row["cap_ref"] for row in second],
        )

    def test_ground_access_exact_drc_prunes_only_implicated_terminal_group(self):
        class Uuid:
            def __init__(self, value):
                self.value = value

            def AsString(self):
                return self.value

        class Item:
            def __init__(self, uid, kind):
                self.m_Uuid = Uuid(uid)
                self.kind = kind

            def GetNetname(self):
                return "GND"

            def GetClass(self):
                return self.kind

        class Board:
            def __init__(self):
                self.items = [
                    Item("good-via", "PCB_VIA"),
                    Item("bad-stub", "PCB_TRACK"),
                    Item("bad-via", "PCB_VIA"),
                ]

            def GetTracks(self):
                return list(self.items)

            def Remove(self, item):
                self.items.remove(item)

        report = {
            "generated_items": [
                {"uuid": "good-via"}, {"uuid": "bad-stub"},
                {"uuid": "bad-via"},
            ],
            "terminals": [
                {"ref": "C1", "pad": "2", "status": "via-in-pad",
                 "via_uuid": "good-via",
                 "generated_item_uuids": ["good-via"]},
                {"ref": "D3", "pad": "2", "status": "dogbone",
                 "via_uuid": "bad-via",
                 "generated_item_uuids": ["bad-stub", "bad-via"]},
            ],
        }
        after = {"violations": [{
            "type": "clearance",
            "items": [{"uuid": "bad-stub"}, {"uuid": "zone"}],
        }]}

        result = cell._prune_ground_access_drc_groups(
            Board(), report, {"violations": []}, after)

        self.assertFalse(result["ok"])
        self.assertEqual(result["generated_item_count"], 1)
        self.assertEqual(result["required_via_uuids"], ["good-via"])
        self.assertEqual(
            [row["ref"] for row in result["refused"]], ["D3"])
        self.assertEqual(
            result["exact_group_admission"]
            ["removed_generated_item_uuids"],
            ["bad-stub", "bad-via"])

    def test_locality_budget_allows_one_class_width_escape_not_remote_dogleg(self):
        close_limit = cell._local_supply_limit_mm(1.067, 1.0, 0.25)
        remote_limit = cell._local_supply_limit_mm(3.17, 1.0, 0.25)

        self.assertGreaterEqual(close_limit, 2.292)
        self.assertLess(remote_limit, 5.725)
        self.assertGreaterEqual(
            cell._local_supply_limit_mm(3.295, 0.5, 0.2), 4.559)
        # A one-grid detour must not fail just beyond the 1.40 ratio.  This is
        # the same topology as a fine-pitch shared GND entry routed around one
        # already-owned supply escape.
        self.assertGreaterEqual(
            cell._local_supply_limit_mm(2.377, 0.5, 0.2), 3.362)

    def test_endpoint_neckdown_rule_is_group_scoped_and_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            board = os.path.join(directory, "board.kicad_pcb")
            dru = os.path.join(directory, "board.kicad_dru")
            with open(dru, "w", encoding="utf-8") as handle:
                handle.write("(version 1)\n(rule \"Power\"\n"
                             " (condition \"A.NetClass == 'Power'\")\n"
                             " (constraint track_width (min 0.5mm)))\n")
            report = {"cells": [{"supply": {"endpoint_neckdown": {
                "group": cell.ENDPOINT_NECKDOWN_GROUP,
                "min_width_mm": 0.2,
            }}}]}

            first = cell._ensure_endpoint_neckdown_rule(board, report)
            second = cell._ensure_endpoint_neckdown_rule(board, report)
            with open(dru, encoding="utf-8") as handle:
                text = handle.read()

            self.assertTrue(first["applicable"])
            self.assertFalse(second["written"])
            self.assertEqual(text.count(cell.ENDPOINT_NECKDOWN_RULE_BEGIN), 1)
            self.assertIn("memberOfGroup('CEC_LOCAL_ENDPOINT_NECKDOWN')", text)
            self.assertIn("track_width (min 0.200mm)", text)

    def test_ground_pair_retries_capacitor_first_after_greedy_owner_blocks(self):
        class Uuid:
            def __init__(self, value):
                self.value = value

            def AsString(self):
                return self.value

        class Item:
            def __init__(self, value):
                self.m_Uuid = Uuid(value)

        class Board:
            def __init__(self):
                self.items = []

            def GetTracks(self):
                return list(self.items)

            def Remove(self, item):
                self.items.remove(item)

            def BuildConnectivity(self):
                pass

        board = Board()
        owner, cap = object(), object()
        phase = {"cap_has_seat": False}

        def ground_return(fake_board, pad, **_kwargs):
            if pad is cap:
                if fake_board.items:
                    return None, "owner consumed the only seat"
                phase["cap_has_seat"] = True
                item = Item("cap")
                fake_board.items.append(item)
                return {"status": "dogbone", "items": [item]}, None
            if phase["cap_has_seat"]:
                item = Item("owner")
                fake_board.items.append(item)
                return {"status": "dogbone", "items": [item]}, None
            item = Item("owner-first")
            fake_board.items.append(item)
            return {"status": "dogbone", "items": [item]}, None

        with mock.patch.object(cell, "_add_ground_return",
                               side_effect=ground_return), \
                mock.patch.object(cell, "_add_supply_link",
                                  return_value=(None, "blocked")):
            owner_return, cap_return, link, error = \
                cell._add_ground_return_pair(
                    board, owner, cap, board_path="board.kicad_pcb",
                    reach_mm=1.5, lock=True)

        self.assertIsNone(error)
        self.assertEqual(owner_return["status"], "dogbone")
        self.assertEqual(cap_return["status"], "dogbone")
        self.assertEqual(link["seat_order"], "capacitor-first")
        self.assertEqual(sorted(item.m_Uuid.AsString()
                                for item in board.items), ["cap", "owner"])

    def test_guarded_shared_ground_link_uses_one_qualified_local_via(self):
        class Board:
            def GetTracks(self):
                return []

            def BuildConnectivity(self):
                pass

        board = Board()
        owner, cap = object(), object()
        portal = {"status": "via-in-pad", "via_uuid": "cap-via",
                  "items": []}

        def ground_return(_board, pad, **_kwargs):
            if pad is owner:
                return None, "owner pad centre obstructed"
            return dict(portal), None

        link = {"status": "linked", "length_mm": 1.503, "items": []}
        with mock.patch.object(
                cell, "_add_ground_return", side_effect=ground_return) as probe, \
                mock.patch.object(
                    cell, "_add_supply_link", return_value=(link, None)):
            owner_return, cap_return, shared, error = \
                cell._add_ground_return_pair(
                    board, owner, cap, board_path="board.kicad_pcb",
                    reach_mm=1.5, lock=True)

        self.assertIsNone(error)
        self.assertEqual(probe.call_count, 2)
        self.assertEqual(owner_return["status"], "shared-ground-entry")
        self.assertEqual(owner_return["via_uuid"], "cap-via")
        self.assertEqual(cap_return["status"], "via-in-pad")
        self.assertEqual(shared["portal_owner"], "cap")
        self.assertEqual(shared["length_mm"], 1.503)

    def test_reference_affinity_prevents_distance_rematching(self):
        board = pcbnew.BOARD()
        nets = {}
        for name in ("GND", "+3V3"):
            net = pcbnew.NETINFO_ITEM(board, name)
            board.Add(net); nets[name] = net

        def footprint(ref, value, supply_x):
            fp = pcbnew.FOOTPRINT(board)
            fp.SetReference(ref); fp.SetValue(value)
            pad_rows = (("5", "+3V3", supply_x, 10.0),
                        ("2", "GND", supply_x, 11.0)) \
                if ref.startswith("U") else \
                (("1", "+3V3", supply_x, 10.0),
                 ("2", "GND", supply_x, 11.0))
            for number, net_name, x, y in pad_rows:
                pad = pcbnew.PAD(fp); pad.SetPadName(number)
                pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
                pad.SetShape(pcbnew.PAD_SHAPE_RECT)
                pad.SetSize(pcbnew.VECTOR2I_MM(0.8, 0.8))
                pad.SetPosition(pcbnew.VECTOR2I_MM(x, y))
                layers = pcbnew.LSET(); layers.AddLayer(pcbnew.F_Cu)
                pad.SetLayerSet(layers); pad.SetNet(nets[net_name])
                fp.Add(pad)
            board.Add(fp)

        footprint("U11", "TLV7011DBVR", 20.0)
        footprint("U30", "TLV7011DBVR", 5.0)
        # Deliberately cross the physical seats.  A distance-only matcher
        # would silently declare both cells good with the wrong capacitor.
        footprint("C11", "100nF", 5.5)
        footprint("C30", "100nF", 20.5)

        assignment = cell.cec_constraints._device_bypass_assignment(board)
        self.assertEqual(assignment["assigned"], {})
        missing = {row["ref"]: row for row in assignment["missing"]}
        self.assertEqual(missing["U11"]["nearest_ref"], "C11")
        self.assertEqual(missing["U30"]["nearest_ref"], "C30")
        self.assertGreater(missing["U11"]["nearest_mm"], 3.5)
        self.assertGreater(missing["U30"]["nearest_mm"], 3.5)

    def test_tja1051_vio_bypass_is_assigned_between_vio_and_vcc(self):
        board = pcbnew.BOARD()
        nets = {}
        for name in ("GND", "+3V3", "+5VSB"):
            net = pcbnew.NETINFO_ITEM(board, name)
            board.Add(net); nets[name] = net

        def footprint(ref, value, pad_rows):
            fp = pcbnew.FOOTPRINT(board)
            fp.SetReference(ref); fp.SetValue(value)
            for number, net_name, x, y in pad_rows:
                pad = pcbnew.PAD(fp); pad.SetPadName(number)
                pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
                pad.SetShape(pcbnew.PAD_SHAPE_RECT)
                pad.SetSize(pcbnew.VECTOR2I_MM(0.8, 0.8))
                pad.SetPosition(pcbnew.VECTOR2I_MM(x, y))
                layers = pcbnew.LSET(); layers.AddLayer(pcbnew.F_Cu)
                pad.SetLayerSet(layers); pad.SetNet(nets[net_name])
                fp.Add(pad)
            board.Add(fp)
            return fp

        footprint("U2", "TJA1051T/3", (
            ("2", "GND", 10.0, 14.0),
            ("3", "+5VSB", 10.0, 13.0),
            ("5", "+3V3", 10.0, 12.0),
        ))
        footprint("C4", "100nF", (
            ("1", "+5VSB", 11.0, 13.0),
            ("2", "GND", 11.0, 14.0),
        ))
        footprint("C8", "100nF", (
            ("1", "+3V3", 11.0, 12.0),
            ("2", "+5VSB", 11.0, 13.0),
        ))

        assignment = cell.cec_constraints._device_bypass_assignment(board)
        u2 = {row["requirement"]["pin"]: row
              for row in assignment["assigned"].values()
              if row["requirement"]["ref"] == "U2"}
        self.assertEqual(set(u2), {"3", "5"})
        self.assertEqual(u2["3"]["cap_ref"], "C4")
        self.assertEqual(u2["5"]["cap_ref"], "C8")
        self.assertEqual(u2["5"]["requirement"]["return_pin"], "3")
        self.assertEqual(u2["5"]["requirement"]["return_rail"], "+5VSB")

    def test_rail_to_rail_cell_requires_both_explicit_local_legs(self):
        board = pcbnew.BOARD()
        nets = {}
        for name in ("+3V3", "+5VSB"):
            net = pcbnew.NETINFO_ITEM(board, name)
            board.Add(net); nets[name] = net

        def footprint(ref, pad_rows):
            fp = pcbnew.FOOTPRINT(board); fp.SetReference(ref)
            for number, net_name, x, y in pad_rows:
                pad = pcbnew.PAD(fp); pad.SetPadName(number)
                pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
                pad.SetShape(pcbnew.PAD_SHAPE_RECT)
                pad.SetSize(pcbnew.VECTOR2I_MM(0.8, 0.8))
                pad.SetPosition(pcbnew.VECTOR2I_MM(x, y))
                layers = pcbnew.LSET(); layers.AddLayer(pcbnew.F_Cu)
                pad.SetLayerSet(layers); pad.SetNet(nets[net_name])
                fp.Add(pad)
            board.Add(fp); return fp

        owner = footprint("U2", (
            ("3", "+5VSB", 10.0, 11.0),
            ("5", "+3V3", 10.0, 10.0),
        ))
        cap = footprint("C8", (
            ("1", "+3V3", 11.0, 10.0),
            ("2", "+5VSB", 11.0, 11.0),
        ))
        owner_vio = owner.FindPadByNumber("5")
        owner_vcc = owner.FindPadByNumber("3")
        cap_vio = cap.FindPadByNumber("1")
        cap_vcc = cap.FindPadByNumber("2")
        requirement = {
            "id": "U2:5:3:100n", "ref": "U2", "pin": "5",
            "pad": owner_vio, "rail": "+3V3", "kind": "100n",
            "return_pin": "3", "return_pad": owner_vcc,
            "return_rail": "+5VSB", "max_mm": 3.5,
        }
        assignment = {"requirements": [requirement], "missing": [],
                      "assigned": {requirement["id"]: {
                          "requirement": requirement, "cap_ref": "C8",
                          "distance_mm": 1.0}}}

        def add_track(start_pad, end_pad, net_name):
            track = pcbnew.PCB_TRACK(board)
            track.SetStart(start_pad.GetPosition())
            track.SetEnd(end_pad.GetPosition())
            track.SetWidth(pcbnew.FromMM(0.25))
            track.SetLayer(pcbnew.F_Cu)
            track.SetNetCode(nets[net_name].GetNetCode())
            board.Add(track)

        add_track(owner_vio, cap_vio, "+3V3")
        with mock.patch.object(
                cell.cec_constraints, "_device_bypass_assignment",
                return_value=assignment):
            incomplete = cell.audit_board(board)
        self.assertFalse(incomplete["ok"])
        self.assertIn("no explicit local +5VSB return copper",
                      incomplete["refused"][0]["reason"])

        add_track(owner_vcc, cap_vcc, "+5VSB")
        with mock.patch.object(
                cell.cec_constraints, "_device_bypass_assignment",
                return_value=assignment):
            complete = cell.audit_board(board)
        self.assertTrue(complete["ok"], complete["refused"])
        self.assertEqual(complete["cells"][0]["return_path_mm"], 1.0)
        self.assertIsNone(
            complete["cells"][0]["cap_ground_return_status"])

    def test_missing_assignment_provenance_distinguishes_range_and_bom(self):
        near = cell._missing_assignment_report({
            "ref": "REG", "pin": "1", "rail": "+V",
            "nearest_ref": "BYP", "nearest_mm": 3.7, "max_mm": 3.5,
        })
        self.assertEqual(near["assignment_failure"],
                         "compatible_component_out_of_range")
        self.assertEqual(near["assignment_gap_mm"], 0.2)
        self.assertEqual(near["cap"], "BYP")
        absent = cell._missing_assignment_report({
            "ref": "REG", "pin": "1", "rail": "+V",
            "nearest_ref": None, "nearest_mm": None, "max_mm": 3.5,
        })
        self.assertEqual(absent["assignment_failure"],
                         "no_compatible_component")

    def test_assignment_limit_absorbs_only_board_grid_numeric_noise(self):
        self.assertTrue(
            cell.cec_constraints._within_physical_distance_limit(
                3.5005, 3.5))
        self.assertFalse(
            cell.cec_constraints._within_physical_distance_limit(
                3.502, 3.5))
        boundary = cell._missing_assignment_report({
            "ref": "REG", "pin": "1", "rail": "+V",
            "nearest_ref": "BYP", "nearest_mm": 3.5005,
            "max_mm": 3.5,
        })
        self.assertEqual(boundary["assignment_failure"],
                         "distinct_component_contention")
        outside = cell._missing_assignment_report({
            "ref": "REG", "pin": "1", "rail": "+V",
            "nearest_ref": "BYP", "nearest_mm": 3.502,
            "max_mm": 3.5,
        })
        self.assertEqual(outside["assignment_failure"],
                         "compatible_component_out_of_range")

    def test_report_evidence_strips_live_pcbnew_items_recursively(self):
        board = pcbnew.BOARD()
        native = pcbnew.PCB_TRACK(board)
        report = cell._report_only({
            "status": "refused", "items": [native],
            "nested": {"items": [native], "reason": "blocked"},
        })
        self.assertNotIn("items", report)
        self.assertNotIn("items", report["nested"])
        self.assertEqual(report["nested"]["reason"], "blocked")
        pickle.dumps(report)

    def _board(self):
        board = pcbnew.BOARD()
        board.SetCopperLayerCount(6)
        props = board.GetProperties()
        props["CEC_FAB_PROFILE"] = "jlcpcb_6l_pofv_signal"
        board.SetProperties(props)
        nets = {}
        for name in ("GND", "+3V3"):
            net = pcbnew.NETINFO_ITEM(board, name)
            board.Add(net); nets[name] = net
        for a, b in (((0, 0), (30, 0)), ((30, 0), (30, 30)),
                     ((30, 30), (0, 30)), ((0, 30), (0, 0))):
            edge = pcbnew.PCB_SHAPE(board)
            edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
            edge.SetStart(pcbnew.VECTOR2I_MM(*a))
            edge.SetEnd(pcbnew.VECTOR2I_MM(*b))
            edge.SetLayer(pcbnew.Edge_Cuts); board.Add(edge)

        def footprint(ref, pads):
            fp = pcbnew.FOOTPRINT(board); fp.SetReference(ref)
            for number, net_name, x, y in pads:
                pad = pcbnew.PAD(fp)
                pad.SetPadName(str(number))
                pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
                pad.SetShape(pcbnew.PAD_SHAPE_RECT)
                pad.SetSize(pcbnew.VECTOR2I_MM(0.8, 0.8))
                pad.SetPosition(pcbnew.VECTOR2I_MM(x, y))
                layers = pcbnew.LSET(); layers.AddLayer(pcbnew.F_Cu)
                pad.SetLayerSet(layers); pad.SetNet(nets[net_name])
                fp.Add(pad)
            board.Add(fp)
            return fp

        owner = footprint("U1", ((1, "GND", 10.0, 11.0),
                                  (2, "+3V3", 10.0, 10.0)))
        cap = footprint("C1", ((1, "+3V3", 11.0, 10.0),
                                (2, "GND", 11.0, 11.0)))
        owner_supply = next(p for p in owner.Pads() if p.GetPadName() == "2")
        assignment = {
            "requirements": [{"id": "U1.2", "ref": "U1", "pin": "2",
                              "rail": "+3V3", "pad": owner_supply}],
            "assigned": {"U1.2": {
                "requirement": {"id": "U1.2", "ref": "U1", "pin": "2",
                                "rail": "+3V3", "pad": owner_supply},
                "cap_ref": "C1", "distance_mm": 1.0}},
            "missing": [],
        }
        return board, assignment

    def test_selected_jlc_profile_uses_pofv_for_both_ground_pads(self):
        board, assignment = self._board()
        with mock.patch.object(
                cell.cec_constraints, "_device_bypass_assignment",
                return_value=assignment):
            report = cell.synthesize_ground_returns_board(board)
        self.assertTrue(report["ok"], report["refused"])
        self.assertEqual(report["generated_item_count"], 2)
        self.assertEqual(
            {row["kind"] for row in report["generated_items"]}, {"PCB_VIA"})
        self.assertEqual(
            {row["ground_return"]["status"] for row in report["cells"]},
            {"via-in-pad"})
        self.assertEqual(len(report["required_via_uuids"]), 2)
        vias = [item for item in board.GetTracks()
                if item.GetClass() == "PCB_VIA"]
        expected_diameter, expected_drill = (0.35, 0.25)
        self.assertEqual({round(via.GetDrillValue() / cell.MM, 3)
                          for via in vias}, {round(expected_drill, 3)})
        self.assertEqual({round(via.GetWidth(pcbnew.F_Cu) / cell.MM, 3)
                          for via in vias}, {round(expected_diameter, 3)})
        returns = [row[key]
                   for row in report["cells"]
                   for key in ("ground_return", "owner_ground_return")]
        self.assertTrue(all(
            row["endpoint_limited_local_via"]
            and row["qualified_process_exception"]
            and row["diameter_mm"] == expected_diameter
            and row["drill_mm"] == expected_drill
            for row in returns))

    def test_preroute_admission_defers_only_dangling_reserved_vias(self):
        before = SimpleNamespace(drc_types={})
        deferred = SimpleNamespace(drc_types={"via_dangling": 8})
        unsafe = SimpleNamespace(drc_types={
            "via_dangling": 8, "clearance": 1})
        self.assertFalse(cell._drc_regressed_except(
            before, deferred, {"via_dangling"}))
        self.assertTrue(cell._drc_regressed_except(
            before, unsafe, {"via_dangling"}))

    def test_stage_drc_ignores_non_generated_baseline_reclassification(self):
        before = SimpleNamespace(
            drc_types={"tracks_crossing": 1},
            drc_loci=[{
                "type": "tracks_crossing",
                "where": "Track [/SENSE_HI] Track [/SENSE_LO]"}])
        after = SimpleNamespace(
            drc_types={"clearance": 1},
            drc_loci=[{
                "type": "clearance",
                "where": "Pad [/SENSE2_HI] Track [/SENSE_LO]"}])
        self.assertEqual(cell._stage_drc_regression(
            before, after, generated_nets={"GND"}), {})

    def test_stage_drc_rejects_generated_net_locus_or_count_growth(self):
        before = SimpleNamespace(
            drc_types={"tracks_crossing": 1},
            drc_loci=[{
                "type": "tracks_crossing",
                "where": "Track [/SENSE_HI] Track [/SENSE_LO]"}])
        generated_fault = SimpleNamespace(
            drc_types={"clearance": 1},
            drc_loci=[{
                "type": "clearance",
                "where": "Track [GND] Pad [/SIGNAL]"}])
        count_growth = SimpleNamespace(
            drc_types={"tracks_crossing": 1, "clearance": 1},
            drc_loci=before.drc_loci + [{
                "type": "clearance",
                "where": "Pad [/A] Track [/B]"}])
        self.assertEqual(cell._stage_drc_regression(
            before, generated_fault, generated_nets={"GND"}),
            {"clearance": 1})
        self.assertEqual(cell._stage_drc_regression(
            before, count_growth, generated_nets={"GND"}),
            {"clearance": 1})

    def test_hole_spacing_is_enforced_even_for_same_net_vias(self):
        board, _assignment = self._board()
        gnd = next(net for net in
                   board.GetNetInfo().NetsByNetcode().values()
                   if net.GetNetname() == "GND")
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(pcbnew.VECTOR2I_MM(10.0, 10.0))
        via.SetDrill(pcbnew.FromMM(0.25))
        via.SetWidth(pcbnew.FromMM(0.50))
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetNetCode(gnd.GetNetCode()); board.Add(via)
        clear, conflicts = cell._hole_to_hole_clear(
            board, pcbnew.VECTOR2I_MM(10.20, 10.0), 0.25)
        self.assertFalse(clear)
        self.assertTrue(conflicts)
        clear, conflicts = cell._hole_to_hole_clear(
            board, pcbnew.VECTOR2I_MM(11.0, 10.0), 0.25)
        self.assertTrue(clear, conflicts)

    def test_complete_preroute_wrapper_reports_partial_supply_ownership(self):
        board, assignment = self._board()
        with tempfile.TemporaryDirectory() as directory:
            source = os.path.join(directory, "source.kicad_pcb")
            destination = os.path.join(directory, "priority.kicad_pcb")
            pcbnew.SaveBoard(source, board)
            score = SimpleNamespace(
                drc=0, unconnected=2, kelvin_ok=True, diffpair_ok=True,
                drc_types={})
            synthesized = {
                "schema": 1, "ok": True, "requirements": 1,
                "owned": 1, "refused": [], "cells": [],
                "generated_items": [], "generated_item_count": 3,
                "protected_nets": ["GND"],
                "partial_supply_nets": ["+3V3"],
                "required_via_uuids": ["via-a", "via-b"],
            }
            with mock.patch.object(
                    cell, "synthesize_board",
                    return_value=synthesized), mock.patch(
                        "cec_score.score", return_value=score), \
                    mock.patch.object(
                        cell.cec_fr, "refill_zones") as refill:
                report = cell.synthesize_pre_route(source, destination)
        self.assertTrue(report["ok"], report.get("reason"))
        self.assertTrue(report["priority_complete"])
        refill.assert_called_once_with(destination)
        self.assertEqual(report["protected_nets"], ["GND"])
        self.assertEqual(report["partial_supply_nets"], ["+3V3"])
        self.assertEqual(len(report["required_via_uuids"]), 2)

    def test_complete_preroute_accepts_untouched_drc_reclassification(self):
        board, _assignment = self._board()
        with tempfile.TemporaryDirectory() as directory:
            source = os.path.join(directory, "source.kicad_pcb")
            destination = os.path.join(directory, "priority.kicad_pcb")
            pcbnew.SaveBoard(source, board)
            before = SimpleNamespace(
                drc=1, unconnected=2, kelvin_ok=False, diffpair_ok=True,
                drc_types={"tracks_crossing": 1},
                drc_loci=[{
                    "type": "tracks_crossing",
                    "where": "Track [/SENSE_HI] Track [/SENSE_LO]"}])
            after = SimpleNamespace(
                drc=1, unconnected=1, kelvin_ok=False, diffpair_ok=True,
                drc_types={"clearance": 1},
                drc_loci=[{
                    "type": "clearance",
                    "where": "Pad [/SENSE2_HI] Track [/SENSE_LO]"}])
            synthesized = {
                "schema": 1, "ok": True, "requirements": 1,
                "owned": 1, "refused": [], "cells": [],
                "generated_items": [{"net": "+3V3"}],
                "generated_item_count": 1,
                "protected_nets": ["GND"],
                "partial_supply_nets": ["+3V3"],
                "required_via_uuids": [],
            }
            with mock.patch.object(
                    cell, "synthesize_board",
                    return_value=synthesized), mock.patch(
                        "cec_score.score", side_effect=(before, after)):
                report = cell.synthesize_pre_route(source, destination)

        self.assertTrue(report["ok"], report.get("reason"))
        self.assertTrue(report["priority_complete"])
        self.assertEqual(report["drc_regression"], {})
        self.assertEqual(report["drc_reclassification"], {"clearance": 1})

    def test_routed_seed_ripup_is_local_and_preserves_locked_priority_copper(self):
        def add_foreign(board, *, locked):
            net = pcbnew.NETINFO_ITEM(
                board, "/LOCKED" if locked else "/ORDINARY")
            board.Add(net)
            track = pcbnew.PCB_TRACK(board)
            track.SetStart(pcbnew.VECTOR2I_MM(9.5, 11.0))
            track.SetEnd(pcbnew.VECTOR2I_MM(11.5, 11.0))
            track.SetWidth(pcbnew.FromMM(0.20))
            track.SetLayer(pcbnew.F_Cu)
            track.SetNetCode(net.GetNetCode())
            track.SetLocked(locked); board.Add(track)
            return track.m_Uuid.AsString()

        board, assignment = self._board()
        ordinary_uuid = add_foreign(board, locked=False)
        with mock.patch.object(
                cell.cec_constraints, "_device_bypass_assignment",
                return_value=assignment):
            report = cell.ripup_foreign_local_copper(board)
        self.assertEqual(report["removed_count"], 1)
        self.assertEqual(report["removed_items"][0]["uuid"], ordinary_uuid)

        protected_board, protected_assignment = self._board()
        locked_uuid = add_foreign(protected_board, locked=True)
        with mock.patch.object(
                cell.cec_constraints, "_device_bypass_assignment",
                return_value=protected_assignment):
            protected = cell.ripup_foreign_local_copper(protected_board)
        self.assertEqual(protected["removed_count"], 0)
        self.assertIn("/LOCKED", protected["protected_nets"])
        self.assertIn(locked_uuid, {
            item.m_Uuid.AsString() for item in protected_board.GetTracks()})

        demoted_board, demoted_assignment = self._board()
        demoted_uuid = add_foreign(demoted_board, locked=True)
        with mock.patch.object(
                cell.cec_constraints, "_device_bypass_assignment",
                return_value=demoted_assignment):
            demoted = cell.ripup_foreign_local_copper(
                demoted_board, demotable_nets={"/LOCKED"})
        self.assertEqual(demoted["removed_count"], 1)
        self.assertEqual(demoted["removed_items"][0]["uuid"], demoted_uuid)
        self.assertEqual(demoted["demotable_nets"], ["/LOCKED"])

        ground_board, _ground_assignment = self._board()
        ground_uuid = add_foreign(ground_board, locked=False)
        ground = cell.ripup_foreign_ground_access_copper(
            ground_board, [{"ref": "U1", "pad": "1"}])
        self.assertEqual(ground["removed_count"], 1)
        self.assertEqual(ground["removed_items"][0]["uuid"], ground_uuid)

    def test_preroute_forwards_explicit_demotable_access_nets(self):
        board, _assignment = self._board()
        with tempfile.TemporaryDirectory() as directory:
            source = os.path.join(directory, "source.kicad_pcb")
            destination = os.path.join(directory, "priority.kicad_pcb")
            pcbnew.SaveBoard(source, board)
            score = SimpleNamespace(
                drc=0, unconnected=1, kelvin_ok=True, diffpair_ok=True,
                drc_types={}, drc_loci=[])
            synthesized = {
                "schema": 1, "ok": True, "requirements": 0,
                "owned": 0, "refused": [], "cells": [],
                "generated_items": [], "generated_item_count": 0,
                "protected_nets": [], "partial_supply_nets": [],
                "required_via_uuids": [],
            }
            ripup = {
                "schema": 1, "removed_count": 1,
                "removed_nets": ["/ACCESS"],
                "demotable_nets": ["/ACCESS"],
            }
            with mock.patch.object(
                    cell, "_ripup_file_subprocess",
                    return_value=ripup) as ripup_worker, mock.patch.object(
                        cell, "synthesize_board",
                        return_value=synthesized), mock.patch(
                            "cec_score.score",
                            side_effect=(score, score)), mock.patch.object(
                                cell.cec_fr, "refill_zones"):
                report = cell.synthesize_pre_route(
                    source, destination, repair_existing_copper=True,
                    protected_nets=("/CRITICAL",),
                    demotable_nets=("/ACCESS",))

        self.assertTrue(report["priority_complete"])
        self.assertEqual(report["local_ripup"], ripup)
        self.assertEqual(
            ripup_worker.call_args.kwargs["protected_nets"],
            ("/CRITICAL",))
        self.assertEqual(
            ripup_worker.call_args.kwargs["demotable_nets"],
            ("/ACCESS",))

    def test_full_cell_has_short_supply_and_immediate_returns(self):
        board, assignment = self._board()
        with mock.patch.object(
                cell.cec_constraints, "_device_bypass_assignment",
                return_value=assignment):
            report = cell.synthesize_board(board)
            audit = cell.audit_board(board)
        self.assertTrue(report["ok"], report["refused"])
        self.assertTrue(audit["ok"], audit["refused"])
        row = audit["cells"][0]
        self.assertLessEqual(row["supply_path_mm"], 1.35)
        self.assertEqual(row["cap_ground_return_mm"], 0.0)
        self.assertEqual(row["owner_ground_return_mm"], 0.0)

    def test_final_audit_accepts_bounded_explicit_shared_ground_entry(self):
        board, assignment = self._board()
        owner = board.FindFootprintByReference("U1")
        cap = board.FindFootprintByReference("C1")
        owner_ground = owner.FindPadByNumber("1")
        cap_ground = cap.FindPadByNumber("2")
        cap_ground.SetPosition(pcbnew.VECTOR2I_MM(11.7, 11.0))

        def add_track(left, right, net):
            track = pcbnew.PCB_TRACK(board)
            track.SetStart(left); track.SetEnd(right)
            track.SetWidth(pcbnew.FromMM(0.25))
            track.SetLayer(pcbnew.F_Cu); track.SetNetCode(net.GetNetCode())
            board.Add(track)

        add_track(
            owner.FindPadByNumber("2").GetPosition(),
            cap.FindPadByNumber("1").GetPosition(),
            owner.FindPadByNumber("2").GetNet())
        add_track(owner_ground.GetPosition(), cap_ground.GetPosition(),
                  owner_ground.GetNet())
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(cap_ground.GetPosition())
        via.SetDrill(pcbnew.FromMM(0.25))
        via.SetWidth(pcbnew.FromMM(0.35))
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetNetCode(cap_ground.GetNetCode()); board.Add(via)

        with mock.patch.object(
                cell.cec_constraints, "_device_bypass_assignment",
                return_value=assignment):
            report = cell.audit_board(board)

        self.assertTrue(report["ok"], report["refused"])
        row = report["cells"][0]
        self.assertEqual(row["cap_ground_return_status"], "immediate-via")
        self.assertEqual(
            row["owner_ground_return_status"], "shared-ground-entry")
        self.assertEqual(
            row["owner_ground_return_evidence"]["via_uuid"],
            via.m_Uuid.AsString())

    def test_final_audit_rejects_shared_ground_entry_without_local_track(self):
        board, assignment = self._board()
        owner = board.FindFootprintByReference("U1")
        cap = board.FindFootprintByReference("C1")
        cap_ground = cap.FindPadByNumber("2")
        cap_ground.SetPosition(pcbnew.VECTOR2I_MM(11.7, 11.0))

        track = pcbnew.PCB_TRACK(board)
        track.SetStart(owner.FindPadByNumber("2").GetPosition())
        track.SetEnd(cap.FindPadByNumber("1").GetPosition())
        track.SetWidth(pcbnew.FromMM(0.25)); track.SetLayer(pcbnew.F_Cu)
        track.SetNetCode(owner.FindPadByNumber("2").GetNetCode())
        board.Add(track)
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(cap_ground.GetPosition())
        via.SetDrill(pcbnew.FromMM(0.25))
        via.SetWidth(pcbnew.FromMM(0.35))
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetNetCode(cap_ground.GetNetCode()); board.Add(via)

        with mock.patch.object(
                cell.cec_constraints, "_device_bypass_assignment",
                return_value=assignment):
            report = cell.audit_board(board)

        self.assertFalse(report["ok"])
        self.assertIn("owner GND pin has no connected via",
                      report["refused"][0]["reason"])

    def test_fine_pitch_bypass_link_keeps_class_width_body(self):
        board, _assignment = self._board()
        supply = next(net for net in
                      board.GetNetInfo().NetsByNetcode().values()
                      if net.GetNetname() == "+3V3")
        power = pcbnew.NETCLASS("Power")
        power.SetTrackWidth(pcbnew.FromMM(1.0))
        power.SetClearance(pcbnew.FromMM(0.20))
        power.SetViaDiameter(pcbnew.FromMM(0.8))
        power.SetViaDrill(pcbnew.FromMM(0.4))
        supply.SetNetClass(power)
        owner = board.FindFootprintByReference("U1")
        cap = board.FindFootprintByReference("C1")
        owner_supply = owner.FindPadByNumber("2")
        cap_supply = cap.FindPadByNumber("1")
        owner_supply.SetSize(pcbnew.VECTOR2I_MM(0.4, 0.4))
        cap_supply.SetSize(pcbnew.VECTOR2I_MM(0.4, 0.4))
        cap_supply.SetPosition(pcbnew.VECTOR2I_MM(13.0, 10.0))
        owner.FindPadByNumber("1").SetPosition(
            pcbnew.VECTOR2I_MM(10.0, 15.0))
        cap.FindPadByNumber("2").SetPosition(
            pcbnew.VECTOR2I_MM(13.0, 15.0))

        report, error = cell._add_supply_link(
            board, owner_supply, cap_supply, lock=True)

        self.assertIsNone(error)
        self.assertEqual(report["status"], "linked")
        widths = {item.GetWidth() for item in report["items"]}
        self.assertIn(pcbnew.FromMM(1.0), widths)
        self.assertIn(pcbnew.FromMM(0.2), widths)
        self.assertEqual(report["width_mm"], 1.0)

    def test_shared_ground_entry_uses_bounded_full_cell_neckdown(self):
        board, _assignment = self._board()
        ground = next(net for net in
                      board.GetNetInfo().NetsByNetcode().values()
                      if net.GetNetname() == "GND")
        ground_class = pcbnew.NETCLASS("Ground")
        ground_class.SetTrackWidth(pcbnew.FromMM(0.5))
        ground_class.SetClearance(pcbnew.FromMM(0.20))
        ground_class.SetViaDiameter(pcbnew.FromMM(0.9))
        ground_class.SetViaDrill(pcbnew.FromMM(0.5))
        ground.SetNetClass(ground_class)
        owner = board.FindFootprintByReference("U1").FindPadByNumber("1")
        cap = board.FindFootprintByReference("C1").FindPadByNumber("2")
        owner.SetSize(pcbnew.VECTOR2I_MM(0.3, 1.0))
        cap.SetSize(pcbnew.VECTOR2I_MM(0.6, 0.6))
        start, end = owner.GetPosition(), cap.GetPosition()
        narrow_path = [(start, end, pcbnew.FromMM(0.3))]

        with mock.patch.object(
                cell.cec_fr, "_guarded_profiled_lastmile_legs",
                side_effect=[None, narrow_path]), mock.patch.object(
                    cell, "_pofv_supply_bridge_ops",
                    return_value=(None, None)), mock.patch.object(
                        cell.cec_fr, "_lastmile_bridge",
                        return_value=None):
            report, error = cell._add_supply_link(
                board, owner, cap, lock=True,
                link_role="shared-ground-entry")

        self.assertIsNone(error)
        self.assertEqual(report["status"], "shared-ground-neckdown")
        self.assertEqual(report["width_mm"], 0.3)
        self.assertEqual(report["class_width_mm"], 0.5)
        self.assertLessEqual(report["length_mm"], report["max_local_mm"])
        self.assertEqual(
            report["endpoint_neckdown"]["group"],
            cell.ENDPOINT_NECKDOWN_GROUP)
        self.assertTrue(all(item.IsLocked() for item in report["items"]))

    def test_supply_access_preflight_uses_generator_and_is_read_only(self):
        board, assignment = self._board()
        before = len(list(board.GetTracks()))
        with mock.patch.object(
                cell.cec_constraints, "_device_bypass_assignment",
                return_value=assignment):
            report = cell.audit_supply_access_board(board)
        self.assertTrue(report["ok"], report["refused"])
        self.assertEqual(report["accessible"], 1)
        self.assertEqual(len(list(board.GetTracks())), before)
        self.assertGreater(report["cells"][0]["trial_item_count"], 0)

    def test_supply_access_reservations_cover_complete_cell_read_only(self):
        board, assignment = self._board()
        before_tracks = len(list(board.GetTracks()))
        before_groups = len(list(board.Groups()))
        with mock.patch.object(
                cell.cec_constraints, "_device_bypass_assignment",
                return_value=assignment):
            report = cell.supply_access_reservations_board(board)

        self.assertTrue(report["ok"], report["refused"])
        self.assertTrue(report["ground_access"]["ok"])
        self.assertGreater(len(report["primitives"]), 0)
        self.assertEqual(len(list(board.GetTracks())), before_tracks)
        self.assertEqual(len(list(board.Groups())), before_groups)
        self.assertEqual(
            {primitive["net"] for primitive in report["primitives"]},
            {"+3V3", "GND"})
        self.assertTrue(all(
            primitive["kind"] in {"track", "via"}
            for primitive in report["primitives"]))
        self.assertTrue(all(
            primitive.get("cap") or primitive.get("owner")
            for primitive in report["primitives"]))
        self.assertTrue(all(
            row.get("generated_item_uuids") is not None
            for row in report["ground_access"]["terminals"]
            if row.get("status") not in {"covered", "refused"}))
        self.assertEqual(
            sum(primitive["kind"] == "via"
                and primitive["net"] == "GND"
                for primitive in report["primitives"]), 2)

    def test_file_reservation_probe_is_process_isolated(self):
        expected = {"schema": 1, "ok": True, "primitives": []}
        completed = mock.Mock(returncode=0, stdout="", stderr="")
        with mock.patch.object(cell.tempfile, "mkstemp",
                               return_value=(9, "/tmp/report.json")), \
                mock.patch.object(cell.os, "close"), \
                mock.patch.object(cell.os, "unlink"), \
                mock.patch.object(cell.subprocess, "run",
                                   return_value=completed) as run, \
                mock.patch("builtins.open", mock.mock_open(
                    read_data=json.dumps(expected))):
            report = cell.supply_access_reservations_file(
                "/tmp/board.kicad_pcb")
        self.assertEqual(report, expected)
        command = run.call_args.args[0]
        self.assertIn("--reservation-worker", command)
        self.assertIn("/tmp/board.kicad_pcb", command)

    def test_supply_access_preflight_names_guarded_refusal(self):
        board, assignment = self._board()
        with mock.patch.object(
                cell.cec_constraints, "_device_bypass_assignment",
                return_value=assignment), mock.patch.object(
                    cell, "_add_supply_link",
                    return_value=(None, "no guarded local supply path")):
            report = cell.audit_supply_access_board(board)
        self.assertFalse(report["ok"])
        self.assertEqual(report["refused"][0]["owner"], "U1")
        self.assertIn("guarded", report["refused"][0]["reason"])

    def test_guarded_refusal_preserves_endpoint_neckdown_certificate(self):
        board, _assignment = self._board()
        supply = next(net for net in
                      board.GetNetInfo().NetsByNetcode().values()
                      if net.GetNetname() == "+3V3")
        power = pcbnew.NETCLASS("Power")
        power.SetTrackWidth(pcbnew.FromMM(1.0))
        power.SetClearance(pcbnew.FromMM(0.20))
        supply.SetNetClass(power)
        owner = board.FindFootprintByReference("U1").FindPadByNumber("2")
        cap = board.FindFootprintByReference("C1").FindPadByNumber("1")
        owner.SetSize(pcbnew.VECTOR2I_MM(0.4, 0.4))
        cap.SetSize(pcbnew.VECTOR2I_MM(0.6, 0.6))
        diagnostic = {}
        certificate = {
            "schema": 1, "search": {}, "dominant_blockers": [],
            "layers": []}
        with mock.patch.object(
                cell.cec_fr, "_guarded_profiled_lastmile_legs",
                return_value=None), mock.patch.object(
                    cell, "_pofv_supply_bridge_ops",
                    return_value=(None, None)), mock.patch.object(
                    cell.cec_fr, "_lastmile_bridge",
                    return_value=None), mock.patch.object(
                    cell.cec_fr, "_lastmile_refusal_certificate",
                    return_value=certificate) as explain:
            result, error = cell._add_supply_link(
                board, owner, cap, lock=True, diagnostics=diagnostic)
        self.assertIsNone(result)
        self.assertIn("guarded", error)
        self.assertEqual(diagnostic["schema"], 1)
        kwargs = explain.call_args.kwargs
        self.assertEqual(kwargs["start_escape"][0], pcbnew.FromMM(0.2))
        self.assertEqual(kwargs["end_escape"][0], pcbnew.FromMM(0.3))
        self.assertTrue(diagnostic["search"]["via_bridge"])
        self.assertTrue(diagnostic["search"]["via_bridge_layers"])

    def test_assigned_supply_link_uses_guarded_signal_layer_via_bridge(self):
        board, _assignment = self._board()
        owner = board.FindFootprintByReference("U1").FindPadByNumber("2")
        cap = board.FindFootprintByReference("C1").FindPadByNumber("1")
        start, end = owner.GetPosition(), cap.GetPosition()
        a = pcbnew.VECTOR2I_MM(10.0, 9.9)
        b = pcbnew.VECTOR2I_MM(11.0, 9.9)
        width = pcbnew.FromMM(0.25)
        ops = [
            ("trk", start, a, width, pcbnew.F_Cu),
            ("via", a, 0.3, 0.6),
            ("trk", a, b, width, pcbnew.In2_Cu),
            ("via", b, 0.3, 0.6),
            ("trk", b, end, width, pcbnew.F_Cu),
        ]
        with mock.patch.object(
                cell.cec_fr, "_guarded_profiled_lastmile_legs",
                return_value=None), mock.patch.object(
                    cell, "_pofv_supply_bridge_ops",
                    return_value=(None, None)), mock.patch.object(
                    cell.cec_fr, "_lastmile_bridge",
                    return_value=ops) as bridge:
            result, error = cell._add_supply_link(
                board, owner, cap, lock=True)
        self.assertIsNone(error)
        self.assertEqual(result["status"], "via-bridge")
        self.assertEqual(result["vias"], 2)
        self.assertEqual(len(result["items"]), 5)
        self.assertTrue(all(item.IsLocked() for item in result["items"]))
        self.assertIn("In2.Cu", result["layers"])
        bridge.assert_called_once()

    def test_supply_link_rejects_guarded_but_nonlocal_path_before_mutation(self):
        board, _assignment = self._board()
        owner = board.FindFootprintByReference("U1").FindPadByNumber("2")
        cap = board.FindFootprintByReference("C1").FindPadByNumber("1")
        start, end = owner.GetPosition(), cap.GetPosition()
        detour = pcbnew.VECTOR2I_MM(10.0, 6.0)
        width = pcbnew.FromMM(0.25)
        long_path = [
            (start, detour, width),
            (detour, end, width),
        ]
        diagnostic = {}
        certificate = {
            "schema": 1, "search": {}, "dominant_blockers": [],
            "layers": []}
        before = len(list(board.GetTracks()))
        with mock.patch.object(
                cell.cec_fr, "_guarded_profiled_lastmile_legs",
                return_value=long_path), mock.patch.object(
                    cell, "_pofv_supply_bridge_ops",
                    return_value=(None, None)), mock.patch.object(
                    cell.cec_fr, "_lastmile_bridge",
                    return_value=None), mock.patch.object(
                    cell.cec_fr, "_lastmile_refusal_certificate",
                    return_value=certificate):
            result, error = cell._add_supply_link(
                board, owner, cap, lock=True, diagnostics=diagnostic)

        self.assertIsNone(result)
        self.assertIn("locality", error)
        self.assertEqual(len(list(board.GetTracks())), before)
        rejected = diagnostic["locality"]["rejected_candidates"]
        self.assertTrue(any(row["kind"] == "same-layer" for row in rejected))
        self.assertGreater(rejected[0]["length_mm"],
                           diagnostic["locality"]["max_local_mm"])

    def test_assigned_supply_link_prefers_profile_qualified_pofv_bridge(self):
        board, _assignment = self._board()
        owner = board.FindFootprintByReference("U1").FindPadByNumber("2")
        cap = board.FindFootprintByReference("C1").FindPadByNumber("1")
        start, end = owner.GetPosition(), cap.GetPosition()
        ops = [
            ("via", start, 0.3, 0.6),
            ("trk", start, end, pcbnew.FromMM(0.25), pcbnew.In2_Cu),
            ("via", end, 0.3, 0.6),
        ]
        with mock.patch.object(
                cell.cec_fr, "_guarded_profiled_lastmile_legs",
                return_value=None), mock.patch.object(
                    cell, "_pofv_supply_bridge_ops",
                    return_value=(ops, {"fab_profile": "qualified"})), \
                mock.patch.object(
                    cell.cec_fr, "_lastmile_bridge") as dogbone:
            result, error = cell._add_supply_link(
                board, owner, cap, lock=True)
        self.assertIsNone(error)
        self.assertEqual(result["status"], "via-in-pad-bridge")
        self.assertTrue(result["via_in_pad"])
        self.assertEqual(result["fab_profile"], "qualified")
        dogbone.assert_not_called()

    def test_complete_cell_preflight_is_collective_and_read_only(self):
        board, assignment = self._board()
        before = len(list(board.GetTracks()))
        with mock.patch.object(
                cell.cec_constraints, "_device_bypass_assignment",
                return_value=assignment):
            report = cell.audit_pre_route_cells_board(board)
        self.assertTrue(report["ok"], report["refused"])
        self.assertTrue(report["read_only"])
        self.assertGreater(report["trial_item_count"], 0)
        self.assertEqual(len(list(board.GetTracks())), before)

    def test_short_locked_bypass_does_not_claim_whole_pour_authority(self):
        board, _assignment = self._board()
        supply = next(net for net in
                      board.GetNetInfo().NetsByNetcode().values()
                      if net.GetNetname() == "+3V3")
        remote = pcbnew.FOOTPRINT(board); remote.SetReference("J_REMOTE")
        remote_pad = pcbnew.PAD(remote); remote_pad.SetPadName("1")
        remote_pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        remote_pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        remote_pad.SetSize(pcbnew.VECTOR2I_MM(1.0, 1.0))
        remote_pad.SetPosition(pcbnew.VECTOR2I_MM(20.0, 20.0))
        layers = pcbnew.LSET(); layers.AddLayer(pcbnew.F_Cu)
        remote_pad.SetLayerSet(layers); remote_pad.SetNet(supply)
        remote.Add(remote_pad); board.Add(remote)
        local = pcbnew.PCB_TRACK(board)
        local.SetStart(pcbnew.VECTOR2I_MM(10.0, 10.0))
        local.SetEnd(pcbnew.VECTOR2I_MM(11.0, 10.0))
        local.SetWidth(pcbnew.FromMM(0.30)); local.SetLayer(pcbnew.F_Cu)
        local.SetNetCode(supply.GetNetCode()); local.SetLocked(True)
        board.Add(local)
        self.assertNotIn(
            "+3V3", cell.cec_fr.locked_pour_authority_nets_board(board))
        trunk = pcbnew.PCB_TRACK(board)
        trunk.SetStart(pcbnew.VECTOR2I_MM(12.0, 12.0))
        trunk.SetEnd(pcbnew.VECTOR2I_MM(16.0, 12.0))
        trunk.SetWidth(pcbnew.FromMM(1.0)); trunk.SetLayer(pcbnew.F_Cu)
        trunk.SetNetCode(supply.GetNetCode()); trunk.SetLocked(True)
        board.Add(trunk)
        self.assertIn(
            "+3V3", cell.cec_fr.locked_pour_authority_nets_board(board))

    def test_profile_without_pofv_uses_immediate_dogbones(self):
        board, assignment = self._board()
        props = board.GetProperties()
        props["CEC_FAB_PROFILE"] = "jlcpcb_4l_standard"
        board.SetProperties(props)
        with mock.patch.object(
                cell.cec_constraints, "_device_bypass_assignment",
                return_value=assignment):
            report = cell.synthesize_ground_returns_board(board)
        self.assertTrue(report["ok"], report["refused"])
        self.assertEqual(report["generated_item_count"], 4)
        self.assertEqual(
            {row["ground_return"]["status"] for row in report["cells"]},
            {"dogbone"})
        self.assertTrue(all(
            row["ground_return"]["distance_mm"] <= 1.5
            and row["owner_ground_return"]["distance_mm"] <= 1.5
            for row in report["cells"]))

    def test_ground_plane_access_owns_every_smd_ground_terminal(self):
        board, _assignment = self._board()

        report = cell.synthesize_ground_plane_access_board(board)

        self.assertTrue(report["ok"], report["refused"])
        self.assertEqual(report["pads"], 2)
        self.assertEqual(report["via_in_pad"], 2)
        self.assertEqual(len(report["required_via_uuids"]), 2)
        self.assertEqual(report["protected_nets"], ["GND"])

    def test_ground_dogbone_cannot_partially_overlap_source_pad(self):
        board, _assignment = self._board()
        props = board.GetProperties()
        props["CEC_FAB_PROFILE"] = "jlcpcb_4l_standard"
        board.SetProperties(props)
        pad = board.FindFootprintByReference("U1").FindPadByNumber("1")
        pad.SetSize(pcbnew.VECTOR2I_MM(1.05, 0.40))

        result, error = cell._add_ground_return(
            board, pad, board_path="", reach_mm=1.5, lock=True)

        self.assertIsNone(error)
        self.assertEqual(result["status"], "dogbone")
        same, different, _allowed = cell.cec_constraints._via_pad_overlaps(
            board)
        self.assertEqual(same, [])
        self.assertEqual(different, [])

    def test_existing_partial_pad_via_is_not_accepted_as_ground_access(self):
        board, _assignment = self._board()
        props = board.GetProperties()
        props["CEC_FAB_PROFILE"] = "jlcpcb_4l_standard"
        board.SetProperties(props)
        pad = board.FindFootprintByReference("U1").FindPadByNumber("1")
        pad.SetSize(pcbnew.VECTOR2I_MM(1.05, 0.40))
        gnd = next(net for net in
                   board.GetNetInfo().NetsByNetcode().values()
                   if net.GetNetname() == "GND")
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(pcbnew.VECTOR2I_MM(10.45, 11.0))
        via.SetDrill(pcbnew.FromMM(0.3))
        via.SetWidth(pcbnew.FromMM(0.6))
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetNetCode(gnd.GetNetCode()); board.Add(via)

        result, error = cell._add_ground_return(
            board, pad, board_path="", reach_mm=1.5, lock=True)

        self.assertIsNone(result)
        self.assertIn("not fabrication-qualified", error)

    def test_ground_plane_access_can_share_a_nearby_qualified_entry(self):
        board, _assignment = self._board()
        first = {
            "status": "via-in-pad", "distance_mm": 0.0,
            "via_uuid": "portal", "items": []}
        refused = "no legal immediate GND return"
        shared = {
            "status": "covered", "distance_mm": 1.0,
            "via_uuid": "portal", "items": []}
        portal_via = SimpleNamespace(
            GetPosition=lambda: pcbnew.VECTOR2I_MM(10.0, 11.0))
        existing = (0.0, portal_via)
        linked = {"status": "shared-ground-entry", "length_mm": 1.0}

        with mock.patch.object(
                cell, "_add_ground_return",
                side_effect=[(first, None), (None, refused)]), \
                mock.patch.object(
                    cell, "_existing_return", return_value=existing), \
                mock.patch.object(
                    cell, "_add_ground_return_pair",
                    return_value=(shared, first, linked, None)):
            report = cell.synthesize_ground_plane_access_board(board)

        self.assertTrue(report["ok"], report["refused"])
        self.assertEqual(report["shared_entries"], 1)
        shared_row = next(row for row in report["terminals"]
                          if row["status"] == "shared-ground-entry")
        self.assertEqual(shared_row["via_uuid"], "portal")
        self.assertIn("independent_refusal", shared_row)

    def test_ground_pin_gap_is_a_hard_pre_route_refusal(self):
        board, assignment = self._board()
        owner = board.FindFootprintByReference("U1")
        owner_gnd = next(p for p in owner.Pads() if p.GetPadName() == "1")
        owner_gnd.SetPosition(pcbnew.VECTOR2I_MM(10.0, 16.0))
        with mock.patch.object(
                cell.cec_constraints, "_device_bypass_assignment",
                return_value=assignment):
            report = cell.synthesize_ground_returns_board(board)
        self.assertFalse(report["ok"])
        self.assertIn("cap-to-owner GND gap", report["refused"][0]["reason"])

    def test_bulk_electrolytic_cannot_own_local_bypass_requirement(self):
        board, _assignment = self._board()
        owner = board.FindFootprintByReference("U1")
        owner.SetValue("TPS2121RUXR")
        owner.FindPadByNumber("2").SetNet(
            next(net for net in board.GetNetInfo().NetsByNetcode().values()
                 if net.GetNetname() == "+3V3"))
        owner.FindPadByNumber("1").SetNet(
            next(net for net in board.GetNetInfo().NetsByNetcode().values()
                 if net.GetNetname() == "GND"))
        ceramic = board.FindFootprintByReference("C1")
        ceramic.SetValue("1uF")
        ceramic.SetFPID(pcbnew.LIB_ID("Capacitor_SMD", "C_0603_1608Metric"))

        bulk = pcbnew.FOOTPRINT(board)
        bulk.SetReference("C_bulk1"); bulk.SetValue("470uF")
        bulk.SetFPID(pcbnew.LIB_ID("Capacitor_SMD", "CP_Elec_6.3x7.7"))
        nets = {net.GetNetname(): net
                for net in board.GetNetInfo().NetsByNetcode().values()}
        for number, net_name, x, y in (
                ("1", "+3V3", 10.1, 10.0), ("2", "GND", 10.1, 11.0)):
            pad = pcbnew.PAD(bulk); pad.SetPadName(number)
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetSize(pcbnew.VECTOR2I_MM(1.0, 1.0))
            pad.SetPosition(pcbnew.VECTOR2I_MM(x, y))
            layers = pcbnew.LSET(); layers.AddLayer(pcbnew.F_Cu)
            pad.SetLayerSet(layers); pad.SetNet(nets[net_name]); bulk.Add(pad)
        board.Add(bulk)

        assignment = cell.cec_constraints._device_bypass_assignment(board)
        owners = {row["cap_ref"] for row in assignment["assigned"].values()}
        self.assertIn("C1", owners)
        self.assertNotIn("C_bulk1", owners)


if __name__ == "__main__":
    unittest.main()
