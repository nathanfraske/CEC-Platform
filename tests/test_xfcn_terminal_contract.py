#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Regression gates for the Standard Beta XFCN prototype integration."""

import json
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import cec_sch_gates  # noqa: E402
import cec_fr  # noqa: E402
import cec_current_topology  # noqa: E402
import cec_pour_plan  # noqa: E402
import cec_synth_pipeline  # noqa: E402
import cec_xfcn_contract as contract  # noqa: E402
import cec_xfcn_thermal_validate as thermal_validation  # noqa: E402
from splice_usb_ingress_common import find_symbol_block  # noqa: E402


class XfcnTerminalContractTest(unittest.TestCase):
    def test_all_live_sources_match_contract(self):
        self.assertEqual([], contract.audit_all())

    def test_release_is_fail_closed_until_objective_evidence_exists(self):
        status = json.loads(contract.QUALIFICATION_STATUS.read_text(encoding="utf-8"))
        self.assertEqual("PROTOTYPE_BLOCKED", status["release_status"])
        self.assertEqual(set(contract.REQUIRED_GATES), set(status["gates"]))
        self.assertTrue(all(row["passed"] is False for row in status["gates"].values()))

    def test_exact_terminal_counts_and_no_retired_interface_refs(self):
        expected_counts = {
            "atx-main": 6, "atx-db": 6, "eps-main": 8, "eps-db": 4,
            "pcie2-main": 4, "pcie3-main": 6, "pcie-db": 2,
        }
        for name, plan in contract.PROJECTS.items():
            with self.subTest(project=name):
                inventory = cec_sch_gates.inventory(str(contract.project_path(name, "root_schematic")))
                self.assertEqual(expected_counts[name], len(plan["refs"]))
                self.assertFalse(set(plan["remove_refs"]) & set(inventory))
                self.assertEqual(set(plan["refs"]), {
                    ref for ref, row in inventory.items()
                    if row["lib_id"].startswith(contract.LIB + ":")
                })

    def test_pcie_terminal_groups_share_one_compact_shunt_aligned_contract(self):
        """Every PCIe cable gets the same two-terminal mechanical cell.

        Each cable pair matches the daughterboard's M3 axes; adjacent pairs
        use the same minimum body/daughterboard clearance. This prevents a
        placer from recreating a loose row or compressing a pair until its
        two bolts no longer mate.
        """
        import pcbnew

        pitches = set()
        for name in ("pcie2-main", "pcie3-main"):
            plan = contract.PROJECTS[name]
            pitch = float(plan["terminal_pair_pitch_mm"])
            pitches.add(pitch)
            # This is a mating datum, not a compaction target: the bolt axes
            # must remain identical to the daughterboard contact-pad axes.
            self.assertEqual(14.0, pitch)
            board = pcbnew.LoadBoard(str(contract.project_path(name, "pcb")))
            footprints = {fp.GetReference(): fp for fp in board.GetFootprints()}
            row_x = sorted(
                footprints[ref].GetPosition().x / 1e6
                for ref in plan["refs"])
            inter = float(plan["terminal_inter_pair_pitch_mm"])
            expected_steps = [pitch if i % 2 == 0 else inter
                              for i in range(len(row_x) - 1)]
            self.assertEqual(
                [round(value, 2) for value in expected_steps],
                [round(right - left, 2)
                 for left, right in zip(row_x, row_x[1:])],
            )
            for ref, (x, y, angle) in (
                    plan.get("fixed_power_path_placements_mm") or {}).items():
                footprint = footprints[ref]
                position = footprint.GetPosition()
                self.assertAlmostEqual(x, position.x / 1e6, places=3)
                self.assertAlmostEqual(y, position.y / 1e6, places=3)
                self.assertAlmostEqual(
                    0.0,
                    (footprint.GetOrientationDegrees() - angle + 180.0)
                    % 360.0 - 180.0,
                    places=3,
                )
            for group in plan["terminal_groups"]:
                force = footprints[group["force_ref"]].GetPosition()
                ret = footprints[group["return_ref"]].GetPosition()
                self.assertAlmostEqual(abs(ret.x - force.x) / 1e6, pitch, places=2)
                self.assertEqual(
                    1 if ret.x > force.x else -1, group["return_side"])
            input_refs = sorted(
                (ref for ref in footprints if ref.startswith("J_IN")),
                key=lambda ref: footprints[ref].GetPosition().x)
            for left_ref, right_ref in zip(input_refs, input_refs[1:]):
                # Input bodies must leave a real current-corridor throat. The
                # former 0.53 mm gaps made their GND rows complete 8.6 mm-lane
                # walls even though the bolt row below was valid and compact.
                left = footprints[left_ref].GetBoundingBox()
                right = footprints[right_ref].GetBoundingBox()
                body_gap = (right.GetLeft() - left.GetRight()) / 1e6
                self.assertGreaterEqual(body_gap, 6.0)
        self.assertEqual({14.0}, pitches)

    def test_monolithic_terminal_legs_are_never_split_into_separate_pours(self):
        entries = [("TB11", 10.0, 20.0), ("TB11", 19.0, 20.0)]
        self.assertEqual(
            [[(10.0, 20.0), (19.0, 20.0)]],
            cec_fr._terminal_aware_x_clusters(entries, {"TB11": 2}),
        )

    def test_corridor_blade_heuristic_never_repacks_pinned_terminals(self):
        """A qualified terminal cell remains authoritative downstream.

        XFCN screw terminals intentionally match the historical broad blade
        classifier, but each two-leg body is one pinned mechanical component;
        the blade-field placer must not compress those bodies to tab pitch.
        """
        anchors = {
            "TB11": (30.9, 42.55, 0.0),
            "TB13": (18.9, 42.55, 0.0),
            "RS1": (30.9, 23.8, -90.0),
        }
        before = dict(anchors)
        cables = [({
            "j_out_blades": ["TB11", "TB13"],
            "shunt": "RS1",
        }, 30.9)]
        with mock.patch.object(cec_synth_pipeline, "_is_blade",
                               return_value=True):
            cec_synth_pipeline._seat_blade_fields(
                cables, anchors, None,
                {ref: "Terminal_XFCN" for ref in anchors}, W=86.5,
                pinned_refs=before)
        self.assertEqual(before, anchors)

    def test_pcie_source_has_no_pre_route_current_slabs(self):
        import pcbnew

        for name in ("pcie2-main", "pcie3-main"):
            plan = contract.PROJECTS[name]
            board = pcbnew.LoadBoard(str(contract.project_path(name, "pcb")))
            present = [zone.GetNetname() for zone in board.Zones()
                       if zone.GetNetname() in plan["managed_pour_nets"]]
            self.assertEqual([], present,
                             f"{name} retained stale pre-route force slabs")

    def test_both_pcie_skus_use_the_same_routed_object_pour_flow(self):
        required = {
            "inner_power_routing", "slab_pour", "overunder",
            "pour_reserve", "pour_first", "pour_plan",
            "power_pickup", "plane_tht_exclude", "lastmile",
        }
        configs = []
        for board_name, project_name in (
                ("pcie-8pin-2port", "pcie2-main"),
                ("pcie-8pin-3port", "pcie3-main")):
            params = cec_synth_pipeline.Config.load(board_name).params
            self.assertTrue(all(params.get(key) is True for key in required))
            self.assertEqual("In3.Cu", params["rail_alt_layer"])
            self.assertEqual(
                contract.power_path_anchor_placements(
                    contract.PROJECTS[project_name]),
                params["anchor_pins"],
            )
            self.assertEqual(("B.Cu", "F.Cu"),
                             params["power_parallel_layers"])
            self.assertEqual(0.50, params["power_parallel_fraction"])
            bundle = cec_pour_plan.parallel_layer_bundle(
                {
                    "parallel_layers": params["power_parallel_layers"],
                    "parallel_layer_fraction":
                        params["power_parallel_fraction"],
                    "parallel_min_amps": params["power_parallel_min_amps"],
                }, 39.0, ("F.Cu", "In2.Cu", "In3.Cu", "B.Cu"))
            self.assertEqual(("B.Cu", "F.Cu"), bundle["layers"])
            self.assertAlmostEqual(1.00,
                                   bundle["aggregate_capacity_fraction"])
            configs.append({key: params[key] for key in required})
        self.assertEqual(configs[0], configs[1])

    def test_pcie_pour_width_uses_the_margin_inclusive_design_current(self):
        for board_name in ("pcie-8pin-2port", "pcie-8pin-3port"):
            self.assertAlmostEqual(
                48.75,
                cec_pour_plan._design_current_amps(
                    "/SENSEC1_HI", board_hint=board_name),
                places=6,
            )

    def test_pcie_current_domain_excludes_kelvin_measurement_leaves(self):
        """Aggregate current belongs only to connector, shunt, and terminal."""
        import pcbnew

        board = pcbnew.LoadBoard(str(contract.project_path("pcie2-main", "pcb")))
        domains = cec_current_topology.board_current_domains(
            board, board_hint="pcie-8pin-2port")
        self.assertEqual(
            {"J_IN1", "RS1"},
            set(domains["/SENSEC1_HI"]["authority_refs"]),
        )
        self.assertEqual(
            {"RS1", "TB11"},
            set(domains["/SENSEC1_LO"]["authority_refs"]),
        )
        self.assertTrue(domains["/SENSEC1_HI"]["complete"])
        self.assertEqual("spec_series_topology",
                         domains["/SENSEC1_HI"]["source"])
        self.assertNotIn("U10", domains["/SENSEC1_HI"]["authority_refs"])
        self.assertNotIn("U20", domains["/SENSEC1_HI"]["authority_refs"])

    def test_every_project_registers_the_pinned_library(self):
        for name, plan in contract.PROJECTS.items():
            project_dir = contract.project_path(name, "root_schematic").parent
            depth = "../../../" if plan["kind"] == "daughterboard" else "../../"
            with self.subTest(project=name, table="symbol"):
                text = (project_dir / "sym-lib-table").read_text(encoding="utf-8")
                self.assertIn(f'(name "{contract.LIB}")', text)
                self.assertIn(f'${{KIPRJMOD}}/{depth}lib/vendor/Connector_Screw.kicad_sym', text)
            with self.subTest(project=name, table="footprint"):
                text = (project_dir / "fp-lib-table").read_text(encoding="utf-8")
                self.assertIn(f'(name "{contract.LIB}")', text)
                self.assertIn(f'${{KIPRJMOD}}/{depth}lib/vendor/Connector_Screw.pretty', text)

    def test_eps_keeps_hierarchical_post_shunt_outputs(self):
        text = contract.project_path("eps-main", "leaf_schematic").read_text(encoding="utf-8")
        for net in ("SENSEC1_LO", "SENSEC2_LO"):
            self.assertEqual(1, text.count(f'(hierarchical_label "{net}"'))

    def test_every_live_pcb_is_idempotently_integrated(self):
        for name in contract.PROJECTS:
            with self.subTest(project=name):
                process = subprocess.run(
                    [sys.executable, str(ROOT / "scripts/cec_xfcn_place.py"),
                     "--project", name, "--json"],
                    cwd=ROOT, capture_output=True, text=True)
                self.assertEqual(0, process.returncode, process.stderr + process.stdout)
                report = json.loads(process.stdout)[0]
                self.assertEqual("already-integrated", report["status"])

    def test_integrated_candidate_can_be_copied_without_mutating_authority(self):
        source = contract.project_path("pcie2-main", "pcb")
        before = source.read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "pcie2-xfcn-seed.kicad_pcb"
            process = subprocess.run(
                [sys.executable, str(ROOT / "scripts/cec_xfcn_place.py"),
                 "--project", "pcie2-main", "--input-board", str(source),
                 "--output-board", str(output), "--apply", "--json"],
                cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(0, process.returncode, process.stderr + process.stdout)
            self.assertTrue(output.is_file())
            report = json.loads(process.stdout)[0]
            self.assertEqual("already-integrated", report["status"])
            self.assertEqual(str(source.resolve()), report["source_pcb"])
        self.assertEqual(before, source.read_bytes())

    def test_surgical_helper_finds_column_zero_generated_symbols(self):
        text = (
            '(kicad_sch\n'
            '(symbol\n'
            '\t(lib_id "test:OnePin")\n'
            '\t(at 10 20 0)\n'
            '\t(property "Reference" "TB99" (at 10 20 0))\n'
            '\t(pin "1" (uuid "00000000-0000-0000-0000-000000000001"))\n'
            ')\n'
            ')\n')
        _start, block = find_symbol_block(text, "TB99")
        self.assertIn('(lib_id "test:OnePin")', block)

    def test_every_daughterboard_terminal_has_an_m3_clearance_hole(self):
        footprint_dir = ROOT / "lib/vendor/Connector_Screw.pretty"
        expected = {
            "XFCN_T34069_Daughterboard_BoltPad_M3_PROVISIONAL.kicad_mod": "6 5",
            "XFCN_TTR32100127-0600_Daughterboard_BoltPad_M3_PROVISIONAL.kicad_mod": "9 8",
        }
        for filename, copper_size in expected.items():
            with self.subTest(footprint=filename):
                text = (footprint_dir / filename).read_text(encoding="utf-8")
                self.assertIn('(pad "1" thru_hole', text)
                self.assertIn(f'(size {copper_size})', text)
                self.assertIn('(drill 3.4)', text)
                self.assertIn('(layers "*.Cu" "*.Mask")', text)
                self.assertNotIn("NO HOLE", text)
        self.assertFalse(
            (footprint_dir /
             "XFCN_T34069_Daughterboard_ClampLand_PROVISIONAL.kicad_mod").exists())

    def test_every_bolt_land_uses_solid_not_thermal_relief_copper(self):
        self.assertEqual([], contract.audit_daughterboard_solid_power_connections())

    def test_every_bolt_land_keeps_the_direct_enig_contact_contract(self):
        self.assertEqual([], contract.audit_daughterboard_contact_interfaces())
        for name, plan in contract.PROJECTS.items():
            if plan["kind"] != "daughterboard":
                continue
            self.assertEqual(contract.CONTACT_INTERFACE, plan["contact_interface"])

    def test_cold_current_field_rejects_connected_but_pinched_copper(self):
        for name in thermal_validation.PROJECTS:
            with self.subTest(project=name):
                self.assertTrue(thermal_validation.preflight_project(name)["pass"])
                diagnosis = thermal_validation._run_dcir_project(
                    {"project": name, "grid_mm": 0.25})
                failures = {
                    net: row for net, row in diagnosis["nets"].items()
                    if not row["copper_path_gate_pass"]
                }
                self.assertEqual({}, failures)
                self.assertTrue(diagnosis["copper_path_gate_pass"])

    def test_main_terminal_leg_geometry_matches_available_drawing_data(self):
        footprint_dir = ROOT / "lib/vendor/Connector_Screw.pretty"
        t340 = (footprint_dir / "XFCN_T34069_THT_M3_40A.kicad_mod").read_text(
            encoding="utf-8")
        ttr = (footprint_dir /
               "XFCN_TTR32100127-0600_THT_M3_60A.kicad_mod").read_text(
                   encoding="utf-8")
        self.assertEqual(4, t340.count('(drill oval 2 1.2)'))
        self.assertEqual(2, ttr.count('(drill oval 2 1.5)'))
        self.assertIn('(at -4.5 0 90)', ttr)
        self.assertIn('(at 4.5 0 90)', ttr)

    def test_atx_signal_companion_is_exact_2x2_pair_with_samtec_numbering(self):
        male = contract.PARTS[contract.ATX_SIGNAL_DB]
        female = contract.PARTS[contract.ATX_SIGNAL_MAIN]
        self.assertEqual("TSW-102-16-G-D-RA", male["mpn"])
        self.assertEqual("SSQ-102-03-G-D", female["mpn"])
        self.assertIn("8.13 mm mating length", male["description"])
        for part in (male, female):
            self.assertTrue(Path(part["datasheet"]).is_file())
            footprint = part["footprint"].split(":", 1)[1] + ".kicad_mod"
            text = (Path(part["footprint_dir"]) / footprint).read_text(
                encoding="utf-8")
            # Samtec double-row numbering is odd/even by column, not KiCad's
            # generic row-major 1,2 / 3,4 order.
            self.assertIn('(pad "1" thru_hole', text)
            self.assertIn('(pad "2" thru_hole', text)
            self.assertIn('(pad "3" thru_hole', text)
            self.assertIn('(pad "4" thru_hole', text)
            self.assertIn('(pad "2" thru_hole circle (at 0 2.54)', text)
            self.assertIn('(pad "3" thru_hole circle (at 2.54 0)', text)

    def test_compact_daughterboards_have_zero_hard_drc_and_no_unconnected(self):
        expected_outlines = {
            "atx-db": (54.0, 21.3),
            "eps-db": (28.0, 18.5),
            "pcie-db": (24.5, 20.0),
        }
        for name, (width, height) in expected_outlines.items():
            with self.subTest(project=name):
                plan = contract.PROJECTS[name]
                x0, y0, x1, y1 = plan["outline_rect_mm"]
                self.assertAlmostEqual(width, x1 - x0)
                self.assertAlmostEqual(height, y1 - y0)
                with tempfile.TemporaryDirectory() as directory:
                    report = Path(directory) / "drc.json"
                    process = subprocess.run(
                        ["kicad-cli", "pcb", "drc", "--format", "json",
                         "-o", str(report), str(contract.project_path(name, "pcb"))],
                        cwd=ROOT, capture_output=True, text=True)
                    self.assertEqual(
                        0, process.returncode, process.stderr + process.stdout)
                    payload = json.loads(report.read_text(encoding="utf-8"))
                hard = [row for row in payload["violations"]
                        if row.get("severity") == "error"]
                self.assertEqual([], hard)
                self.assertEqual([], payload["unconnected_items"])


if __name__ == "__main__":
    unittest.main()
