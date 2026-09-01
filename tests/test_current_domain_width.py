"""Topology teeth for per-segment current-width ownership."""
import os
import sys
import tempfile
import unittest
from unittest import mock


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

try:
    import pcbnew
    import cec_constraints as constraints
    import cec_score
    HAVE_PCBNEW = True
except ImportError:
    HAVE_PCBNEW = False


@unittest.skipUnless(HAVE_PCBNEW, "pcbnew required")
class CurrentDomainWidthTests(unittest.TestCase):
    def _aggregate_board(self, path, *, narrow_trunk=False):
        board = pcbnew.BOARD()
        board.SetCopperLayerCount(6)
        props = board.GetProperties()
        props["CEC_FAB_PROFILE"] = "jlcpcb_6l_pofv_signal"
        board.SetProperties(props)
        net = pcbnew.NETINFO_ITEM(board, "+5VSB")
        board.Add(net)
        front = pcbnew.LSET(); front.AddLayer(pcbnew.F_Cu)

        def terminal(ref, x, y, size=6.0):
            fp = pcbnew.FOOTPRINT(board); fp.SetReference(ref)
            pad = pcbnew.PAD(fp); pad.SetPadName("1")
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetSize(pcbnew.VECTOR2I_MM(size, size))
            pad.SetPosition(pcbnew.VECTOR2I_MM(x, y))
            pad.SetLayerSet(front); pad.SetNet(net); fp.Add(pad); board.Add(fp)
            return pad

        terminal("U7", 5.0, 5.0)
        terminal("F1", 20.0, 5.0)
        terminal("C1", 12.0, 8.0, size=1.0)

        def track(start, end, width):
            item = pcbnew.PCB_TRACK(board)
            item.SetStart(pcbnew.VECTOR2I_MM(*start))
            item.SetEnd(pcbnew.VECTOR2I_MM(*end))
            item.SetWidth(pcbnew.FromMM(width))
            item.SetLayer(pcbnew.F_Cu); item.SetNet(net); board.Add(item)
            return item

        track((5.0, 5.0), (12.0, 5.0), 0.5 if narrow_trunk else 5.0)
        track((12.0, 5.0), (20.0, 5.0), 5.0)
        track((12.0, 5.0), (12.0, 8.0), 0.5)
        for start, end in (((0.0, 0.0), (25.0, 0.0)),
                           ((25.0, 0.0), (25.0, 12.0)),
                           ((25.0, 12.0), (0.0, 12.0)),
                           ((0.0, 12.0), (0.0, 0.0))):
            edge = pcbnew.PCB_SHAPE(board)
            edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
            edge.SetStart(pcbnew.VECTOR2I_MM(*start))
            edge.SetEnd(pcbnew.VECTOR2I_MM(*end))
            edge.SetLayer(pcbnew.Edge_Cuts); board.Add(edge)
        pcbnew.SaveBoard(path, board)
        return pcbnew.LoadBoard(path)

    @staticmethod
    def _domain_config(*_args, **_kwargs):
        return ({"+5VSB": 2.5}, None, {
            "+5VSB": {"refs_src": ["U7"], "refs_sink": ["F1"]},
        }, None)

    def test_current_gate_accepts_narrow_leaf_when_rated_subgraph_stays_connected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "hub-standard-rev2-leaf.kicad_pcb")
            board = self._aggregate_board(path)
            with mock.patch(
                    "cec_thermal_overlay.board_thermal_config",
                    side_effect=self._domain_config):
                ok, detail = constraints.CHECKERS["trace-width-high-current"](
                    board, path, {})[:2]
            self.assertTrue(ok, detail)
            self.assertIn("side-branch", detail)
            self.assertIn("1 aggregate current domain", detail)

    def test_current_gate_rejects_narrow_segment_needed_by_source_sink_path(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "hub-standard-rev2-trunk.kicad_pcb")
            board = self._aggregate_board(path, narrow_trunk=True)
            with mock.patch(
                    "cec_thermal_overlay.board_thermal_config",
                    side_effect=self._domain_config):
                ok, detail, payload = constraints.CHECKERS[
                    "trace-width-high-current"](board, path, {})
            self.assertFalse(ok, detail)
            self.assertIn("no source-to-sink path", detail)
            self.assertTrue(any(row.get("type") == "current_domain_path"
                                for row in payload))

    def test_current_gate_uses_domain_authority_for_anonymous_worker_path(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "anonymous-worker.kicad_pcb")
            board = self._aggregate_board(path)
            with mock.patch(
                    "cec_thermal_overlay.board_thermal_config",
                    side_effect=self._domain_config):
                ok, detail = constraints.CHECKERS[
                    "trace-width-high-current"](board, path, {})[:2]
            self.assertTrue(ok, detail)
            self.assertNotIn("no routed net", detail)
            self.assertIn("current-model trace segment", detail)

    def test_current_gate_can_prove_one_transactional_domain(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "hub-standard-rev2-scope.kicad_pcb")
            board = self._aggregate_board(path)
            with mock.patch(
                    "cec_thermal_overlay.board_thermal_config",
                    side_effect=self._domain_config):
                ok, detail = constraints.CHECKERS[
                    "trace-width-high-current"](
                        board, path,
                        {"current_domain_include_nets": ["+5VSB"]})[:2]
            self.assertTrue(ok, detail)

    def test_explicit_subamp_domain_is_not_demoted_to_signal_geometry(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "pcie-8pin-2port-usb.kicad_pcb")
            board = self._aggregate_board(path)

            def subamp(*_args, **_kwargs):
                return ({"+5VSB": 0.75}, None, {
                    "+5VSB": {"refs_src": ["U7"],
                               "refs_sink": ["F1"]},
                }, None)

            with mock.patch(
                    "cec_thermal_overlay.board_thermal_config",
                    side_effect=subamp):
                ok, detail = constraints.CHECKERS[
                    "trace-width-high-current"](board, path, {})[:2]
            self.assertTrue(ok, detail)
            self.assertIn("current-model trace segment", detail)
            self.assertNotIn("no routed net", detail)

    def test_current_prune_honors_project_width_above_ipc_width(self):
        import json
        import cec_current_topology
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "pcie-8pin-2port-usb.kicad_pcb")
            board = self._aggregate_board(path)
            # Make the first source-trunk segment smaller than the declared
            # Power class while retaining ample IPC width for a 750 mA outer
            # trace.  Project intent must still win.
            first = next(item for item in board.GetTracks()
                         if item.GetClass() != "PCB_VIA")
            first.SetWidth(pcbnew.FromMM(0.20))
            pcbnew.SaveBoard(path, board)
            with open(path.replace(".kicad_pcb", ".kicad_pro"),
                      "w", encoding="utf-8") as sink:
                json.dump({"net_settings": {
                    "classes": [
                        {"name": "Default", "track_width": 0.2,
                         "clearance": 0.2, "via_diameter": 0.6,
                         "via_drill": 0.3},
                        {"name": "Power", "track_width": 0.5,
                         "clearance": 0.2, "via_diameter": 0.8,
                         "via_drill": 0.4},
                    ],
                    "netclass_patterns": [
                        {"pattern": "+5VSB", "netclass": "Power"}],
                }}, sink)

            def subamp(*_args, **_kwargs):
                return ({"+5VSB": 0.75}, None, {
                    "+5VSB": {"refs_src": ["U7"],
                               "refs_sink": ["F1"]},
                }, None)

            board = pcbnew.LoadBoard(path)
            with mock.patch(
                    "cec_thermal_overlay.board_thermal_config",
                    side_effect=subamp):
                report = cec_current_topology.prune_undersized_current_tracks(
                    board, ["+5VSB"], board_hint=path)
            self.assertGreaterEqual(report["removed_count"], 1)
            row = next(item for item in report["removed"]
                       if item["actual_mm"] == 0.20)
            self.assertEqual(0.5, row["project_required_mm"])
            self.assertEqual(0.5, row["required_mm"])

    def test_power_terminal_raster_excludes_local_loads_from_aggregate_tree(self):
        import cec_slab_pour
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "hub-standard-rev2-raster.kicad_pcb")
            board = self._aggregate_board(path)
            # Remove copper so the terminal count itself is observable.
            for item in list(board.GetTracks()):
                board.Remove(item)
            grid = cec_slab_pour.Grid(board, 0.5)
            netcode = board.GetNetcodeFromNetname("+5VSB")
            _all_labels, all_count = cec_slab_pour.terminal_clusters(
                board, netcode, grid)
            _authority_labels, authority_count = cec_slab_pour.terminal_clusters(
                board, netcode, grid, terminal_refs={"U7", "F1"})
            self.assertEqual(all_count, 3)
            self.assertEqual(authority_count, 2)

    def test_explicit_board_identity_outranks_isolated_worker_path(self):
        import cec_current_topology
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "anonymous-worker.kicad_pcb")
            board = self._aggregate_board(path)
            with mock.patch.dict(
                    os.environ,
                    {"CEC_THERMAL_BOARD_HINT": "hub-standard-rev2"}), \
                    mock.patch(
                        "cec_thermal_overlay.board_thermal_config",
                        side_effect=self._domain_config) as configured:
                domain = cec_current_topology.current_domain(
                    board, "+5VSB", board_hint=path)
            self.assertTrue(domain["complete"])
            self.assertEqual(
                configured.call_args.kwargs["board_hint"],
                "hub-standard-rev2")

    def test_route_width_contract_covers_thinner_inner_signal_layer(self):
        import cec_current_topology
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "anonymous-worker.kicad_pcb")
            board = self._aggregate_board(path)
            with mock.patch(
                    "cec_thermal_overlay.board_thermal_config",
                    side_effect=self._domain_config):
                contract = cec_current_topology.route_width_contracts(
                    board, board_hint=path)["+5VSB"]
            by_layer = contract["required_by_layer_mm"]
            self.assertIn("F.Cu", by_layer)
            self.assertIn("In2.Cu", by_layer)
            self.assertGreater(by_layer["In2.Cu"], by_layer["F.Cu"])
            self.assertEqual(contract["minimum_track_width_mm"],
                             max(by_layer.values()))

    def test_priority_power_inventory_does_not_invent_missing_pours(self):
        import cec_synth_pipeline
        domains = {
            "+5VSB": {"complete": True, "amps": 2.5},
            "/LOGIC_REG_IN": {"complete": True, "amps": 0.5},
            "/KVM_5V_IN": {"complete": True, "amps": 1.1},
            "GND": {"complete": True, "amps": 2.5},
            "/STALE": {"complete": False, "amps": 1.0},
        }
        with mock.patch(
                "cec_current_topology.board_current_domains",
                return_value=domains):
            asks, actual = cec_synth_pipeline._priority_power_asks(
                object(), [{"net": "+5VSB", "layers": ("In2.Cu",)}],
                "anonymous-worker.kicad_pcb")

        by_net = {ask["net"]: ask for ask in asks}
        self.assertIs(actual, domains)
        self.assertEqual(by_net["+5VSB"]["layers"], ("In2.Cu",))
        self.assertEqual(by_net["+5VSB"]["provenance"], "placer_ask")
        self.assertNotIn("/KVM_5V_IN", by_net)
        self.assertNotIn("/LOGIC_REG_IN", by_net)
        self.assertNotIn("GND", by_net)
        self.assertNotIn("/STALE", by_net)

    def test_non_pour_current_inventory_routes_complete_domains_first(self):
        import cec_synth_pipeline
        domains = {
            "+5VSB": {"complete": True, "amps": 2.5},
            "/USB_VBUS": {"complete": True, "amps": 0.5},
            "/LOGIC_REG_IN": {"complete": True, "amps": 0.5},
            "/STALE": {"complete": False, "amps": 0.5},
            "GND": {"complete": True, "amps": 2.5},
        }
        with mock.patch(
                "cec_current_topology.board_current_domains",
                return_value=domains):
            route_nets, incomplete, actual = (
                cec_synth_pipeline._priority_trace_current_domains(
                    object(), {"+5VSB"}, "worker.kicad_pcb"))

        self.assertIs(actual, domains)
        self.assertEqual(route_nets, ["/LOGIC_REG_IN", "/USB_VBUS"])
        self.assertEqual(incomplete, ["/STALE"])

    def _filtered_kelvin_board(self, *, connector_tap=False):
        board = pcbnew.BOARD()
        nets = {}
        for name in ("+5VSB", "/IN_P", "/AFTER_SHUNT"):
            net = pcbnew.NETINFO_ITEM(board, name)
            board.Add(net); nets[name] = net

        def footprint(ref, value, pads):
            fp = pcbnew.FOOTPRINT(board)
            fp.SetReference(ref); fp.SetValue(value)
            for number, net_name, x, y in pads:
                pad = pcbnew.PAD(fp)
                pad.SetPadName(str(number))
                pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
                pad.SetShape(pcbnew.PAD_SHAPE_RECT)
                pad.SetSize(pcbnew.VECTOR2I_MM(0.6, 0.6))
                pad.SetPosition(pcbnew.VECTOR2I_MM(x, y))
                layers = pcbnew.LSET(); layers.AddLayer(pcbnew.F_Cu)
                pad.SetLayerSet(layers); pad.SetNet(nets[net_name])
                fp.Add(pad)
            board.Add(fp)
            return fp

        footprint("RS1", "1m", (
            ("1", "+5VSB", 5.0, 5.0),
            ("2", "/AFTER_SHUNT", 5.0, 3.0)))
        footprint("RF1", "10R", (
            ("1", "+5VSB", 7.0, 5.0),
            ("2", "/IN_P", 8.0, 5.0)))
        ina = footprint("U1", "INA240A3", (
            ("8", "/IN_P", 9.0, 5.0),
            ("1", "/AFTER_SHUNT", 9.0, 6.0)))
        if connector_tap:
            footprint("J1", "CONN", (("1", "+5VSB", 6.0, 5.0),))
        track = pcbnew.PCB_TRACK(board)
        track.SetStart(pcbnew.VECTOR2I_MM(5.0, 5.0))
        track.SetEnd(pcbnew.VECTOR2I_MM(7.0, 5.0))
        track.SetWidth(pcbnew.FromMM(0.25))
        track.SetLayer(pcbnew.F_Cu); track.SetNet(nets["+5VSB"])
        board.Add(track)
        return board, ina, track

    def _board(self, path, *, inner_ground_plane):
        board = pcbnew.BOARD()
        board.SetCopperLayerCount(6)
        props = board.GetProperties()
        props["CEC_FAB_PROFILE"] = "jlcpcb_6l_pofv_signal"
        board.SetProperties(props)
        ground = pcbnew.NETINFO_ITEM(board, "GND")
        board.Add(ground)
        track = pcbnew.PCB_TRACK(board)
        track.SetStart(pcbnew.VECTOR2I_MM(5.0, 5.0))
        track.SetEnd(pcbnew.VECTOR2I_MM(7.0, 5.0))
        track.SetWidth(pcbnew.FromMM(0.20))
        track.SetLayer(pcbnew.F_Cu)
        track.SetNet(ground)
        board.Add(track)
        if inner_ground_plane:
            zone = pcbnew.ZONE(board)
            zone.SetNet(ground)
            zone.SetLayer(pcbnew.In1_Cu)
            outline = zone.Outline(); outline.NewOutline()
            for x, y in ((2, 2), (10, 2), (10, 10), (2, 10)):
                outline.Append(pcbnew.VECTOR2I_MM(x, y))
            board.Add(zone)
        pcbnew.SaveBoard(path, board)
        board = pcbnew.LoadBoard(path)
        if inner_ground_plane:
            pcbnew.ZONE_FILLER(board).Fill(board.Zones())
            pcbnew.SaveBoard(path, board)
        return board

    def test_outer_ground_entries_delegate_only_with_a_real_inner_plane(self):
        with tempfile.TemporaryDirectory() as directory:
            without_path = os.path.join(
                directory, "hub-standard-rev2-no-plane.kicad_pcb")
            without = self._board(without_path, inner_ground_plane=False)
            ok, detail = constraints.CHECKERS["trace-width-high-current"](
                without, without_path, {})[:2]
            self.assertFalse(ok, detail)
            self.assertIn("current-model violation", detail)

            with_path = os.path.join(
                directory, "hub-standard-rev2-plane.kicad_pcb")
            with_plane = self._board(with_path, inner_ground_plane=True)
            ok, detail = constraints.CHECKERS["trace-width-high-current"](
                with_plane, with_path, {})[:2]
            self.assertTrue(ok, detail)
            self.assertIn("distributed GND entry", detail)

    def test_ina240_high_impedance_inputs_use_the_real_soic_pinout(self):
        _board, ina, _track = self._filtered_kelvin_board()
        self.assertEqual(cec_score.ina_highz_pad_names(ina), {"1", "8"})

    def test_filtered_kelvin_force_stub_requires_shunt_to_highz_topology(self):
        board, _ina, track = self._filtered_kelvin_board()
        self.assertEqual(
            constraints._filtered_kelvin_force_stub_uuids(board),
            {track.m_Uuid.AsString()})

        bypass, _ina, bypass_track = self._filtered_kelvin_board(
            connector_tap=True)
        self.assertNotIn(
            bypass_track.m_Uuid.AsString(),
            constraints._filtered_kelvin_force_stub_uuids(bypass))


if __name__ == "__main__":
    unittest.main()
