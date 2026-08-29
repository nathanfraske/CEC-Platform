#!/usr/bin/env python3
"""Current-BETA and clean-machine dashboard regressions."""
import glob
import ast
import inspect
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import types
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_beta_manifest as manifest  # noqa: E402
import cec_dashboard as dashboard  # noqa: E402
import cec_render  # noqa: E402


class TestDashboard(unittest.TestCase):
    def test_archive_contract_keeps_executable_route_ownership_sidecars(self):
        self.assertIn(".pourplan.json", dashboard.ARCHIVE_BOARD_SIDECARS)
        self.assertIn(".pourfirst-state.json",
                      dashboard.ARCHIVE_BOARD_SIDECARS)
        self.assertIn(".railreport.json", dashboard.ARCHIVE_BOARD_SIDECARS)

    def test_every_archive_analyzer_receives_exact_power_environment(self):
        tree = ast.parse(textwrap.dedent(
            inspect.getsource(dashboard.archive_board)))
        analyzer_calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_container_run"]
        self.assertGreaterEqual(len(analyzer_calls), 2)
        self.assertTrue(all(any(keyword.arg == "env"
                                for keyword in call.keywords)
                            for call in analyzer_calls))

    def test_external_archive_hot_loads_with_browser_safe_urls(self):
        """A one-shot publisher must appear without restarting the dashboard."""
        with dashboard._archive_lock:
            saved_archive = list(dashboard._archive)
            saved_by_id = dict(dashboard._archive_by_id)
        saved_signature = dashboard._archive_disk_signature
        try:
            with tempfile.TemporaryDirectory() as directory, \
                    mock.patch.object(dashboard, "ARCHIVE_ROOT", directory):
                dashboard._archive_disk_signature = None
                with dashboard._archive_lock:
                    dashboard._archive.clear()
                    dashboard._archive_by_id.clear()

                def publish(aid, epoch):
                    target = os.path.join(directory, aid, "summary.json")
                    dashboard._write_json_atomic(target, {
                        "schema": 1, "id": aid, "name": aid,
                        "epoch": epoch, "panels": {"render": "render.png"},
                        "gates": {"ok": True, "kelvin_ok": True,
                                  "drc": 0, "unconnected": 0,
                                  "foreign": {"status": "na"}},
                        "thermal": {"ok": True, "verdict": "PASS",
                                    "geometry_source":
                                    dashboard.THERMAL_GEOMETRY_SOURCE},
                    })

                publish("first", 1)
                self.assertTrue(dashboard._load_archive(force=False))
                self.assertEqual([row["id"] for row in dashboard._archive],
                                 ["first"])

                publish("external-second", 2)
                self.assertTrue(dashboard._load_archive(force=False))
                self.assertEqual(dashboard._archive[0]["id"],
                                 "external-second")
                self.assertEqual(
                    dashboard._archive[0]["viewer_url"],
                    "/?id=external-second")
                self.assertEqual(
                    dashboard._archive[0]["panel_urls"]["render"],
                    "/img?id=external-second&panel=render")
                self.assertEqual(glob.glob(os.path.join(
                    directory, "*", ".summary-*.tmp")), [])
        finally:
            dashboard._archive_disk_signature = saved_signature
            with dashboard._archive_lock:
                dashboard._archive[:] = saved_archive
                dashboard._archive_by_id.clear()
                dashboard._archive_by_id.update(saved_by_id)

    def test_dashboard_deep_links_and_exposes_shareable_image(self):
        self.assertIn("const INITIAL_ID=INITIAL_QUERY.get('id')", dashboard.PAGE)
        self.assertIn("pick(INITIAL_ID,false)", dashboard.PAGE)
        self.assertIn('id="share"', dashboard.PAGE)
        self.assertIn('id="openpanel"', dashboard.PAGE)
        self.assertIn("/img?id=${encodeURIComponent(cur.id)}", dashboard.PAGE)

    @unittest.skipUnless(shutil.which("node"), "Node.js required for UI contract")
    def test_dashboard_escape_accepts_structured_analysis_fields(self):
        """A structured routing/thermal field must not abort panel selection."""
        start = dashboard.PAGE.index("function displayText")
        end = dashboard.PAGE.index("\nfunction vpill", start)
        contract = dashboard.PAGE[start:end]
        values = [89, {"rail": "open"}, 'A&B <C> "D" \'E\'']
        script = (contract + "\nconsole.log(JSON.stringify(" +
                  json.dumps(values) + ".map(esc)));\n")
        completed = subprocess.run(
            [shutil.which("node"), "-e", script], capture_output=True,
            text=True, timeout=10, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            json.loads(completed.stdout),
            ["89", "{&quot;rail&quot;:&quot;open&quot;}",
             "A&amp;B &lt;C&gt; &quot;D&quot; &#39;E&#39;"])

    def test_snapshot_selection_mounts_panels_before_badges(self):
        start = dashboard.PAGE.index("function pick(id,updateLocation=true)")
        end = dashboard.PAGE.index("\nfunction rerender", start)
        body = dashboard.PAGE[start:end]
        self.assertLess(body.index("fit();"), body.index("renderBadges();"))

    def test_render_validator_rejects_exit_zero_empty_frame(self):
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as directory:
            empty = os.path.join(directory, "empty.png")
            valid = os.path.join(directory, "valid.png")
            Image.new("RGB", (320, 240), (0, 0, 0)).save(empty)
            image = Image.new("RGB", (320, 240), (0, 0, 0))
            draw = ImageDraw.Draw(image)
            draw.rectangle((50, 30, 270, 210), fill=(30, 80, 55))
            draw.ellipse((100, 80, 120, 100), fill=(255, 210, 40))
            image.save(valid)
            self.assertFalse(cec_render._board_render_valid(empty))
            self.assertTrue(cec_render._board_render_valid(valid))

    def test_status_banner_keeps_failure_state_inside_exported_image(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "candidate-top.png")
            Image.new("RGB", (320, 200), (15, 25, 35)).save(path)
            self.assertEqual(
                cec_render.status_banner(
                    path, "routing failed - critical_pair_fallback"), path)
            with Image.open(path) as rendered:
                self.assertGreater(rendered.height, 200)
                self.assertEqual(rendered.getpixel((0, 0)), (142, 24, 31))

    def test_blended_overlays_include_six_layer_stack(self):
        import cec_thermal_overlay

        self.assertEqual(
            cec_thermal_overlay._BLEND_STACK_BU,
            ["B.Cu", "In4.Cu", "In3.Cu", "In2.Cu", "In1.Cu", "F.Cu"])
        for layer in ("In3.Cu", "In4.Cu"):
            self.assertIn(layer, cec_thermal_overlay._BLEND_LEDGE)
            self.assertIn(layer, cec_thermal_overlay._BLEND_LTINT)

    def test_blended_thermal_verdict_fails_closed_on_incomplete_injection(self):
        import cec_thermal_overlay

        incomplete = types.SimpleNamespace(
            max_T=50.5, ambient=50.0,
            nets_dropped={"/OPEN": "no terminal path"}, nets_absent={})
        complete = types.SimpleNamespace(
            max_T=50.5, ambient=50.0, nets_dropped={}, nets_absent={})
        self.assertEqual(
            cec_thermal_overlay._blend_thermal_verdict(incomplete, 40),
            ("FAIL", True))
        self.assertEqual(
            cec_thermal_overlay._blend_thermal_verdict(complete, 40),
            ("PASS", False))

    def test_analyzer_exposes_complete_six_layer_stack(self):
        self.assertEqual([panel for panel, _filename, _layers
                          in dashboard.COPPER_PLOTS],
                         ["plotf", "plot1", "plot2", "plot3", "plot4", "plotb"])
        self.assertEqual([layers.split(",")[0]
                          for _panel, _filename, layers in dashboard.COPPER_PLOTS],
                         ["F.Cu", "In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu", "B.Cu"])

    def test_back_plot_is_physical_bottom_view_only(self):
        back = dashboard._copper_plot_command(
            "board.kicad_pcb", "plot-b.svg",
            "B.Cu,Edge.Cuts,B.Silkscreen", "plotb")
        front = dashboard._copper_plot_command(
            "board.kicad_pcb", "plot-f.svg",
            "F.Cu,Edge.Cuts,F.Silkscreen", "plotf")
        self.assertIn("--mirror", back)
        self.assertNotIn("--mirror", front)
        self.assertEqual(back[-1], "board.kicad_pcb")
        self.assertIn("physical bottom view, mirrored", dashboard.PAGE)

    def test_ranked_hub_route_progress_is_auto_archived(self):
        self.assertIn(
            "build/hub-closure-wave*/route-cand*/*-progress.kicad_pcb",
            dashboard.WATCH_GLOBS)

    def test_route_angle_quality_is_visible(self):
        self.assertIn("unlocked_off45_tracks", dashboard.PAGE)
        self.assertIn("off-45", dashboard.PAGE)

    def test_routing_congestion_is_visible(self):
        self.assertIn("routing-congestion.png",
                      open(os.path.join(ROOT, "scripts", "cec_dashboard.py"),
                           encoding="utf-8").read())
        self.assertIn("congestion n/a", dashboard.PAGE)
        self.assertIn("ROUTING CONGESTION", dashboard.PAGE)

    def test_issue_evidence_extracts_nets_components_and_loci(self):
        evidence = dashboard._issue_tokens([{
            "items": [{
                "description": "Pad 2 [GND] of C15 on F.Cu",
                "uuid": "pad-uuid", "pos": {"x": 12.5, "y": 8.25}}, {
                "description": "Track [+5V_SYS] on F.Cu",
                "uuid": "track-uuid", "pos": {"x": 14.0, "y": 9.0}}]}])
        self.assertEqual(evidence["nets"], {"GND", "+5V_SYS"})
        self.assertEqual(evidence["refs"], {"C15"})
        self.assertEqual(evidence["uuids"], {"pad-uuid", "track-uuid"})
        self.assertEqual(len(evidence["positions"]), 2)

    def test_issue_map_uses_release_endpoint_neckdown_qualification(self):
        qualified = {"type": "track_width", "description": "qualified"}
        remaining = {"type": "clearance", "description": "blocking"}
        rows = [qualified, remaining]
        with mock.patch(
                "cec_score._drop_impossible_pad_artifacts",
                side_effect=lambda violations, _board: violations), \
                mock.patch(
                    "cec_score._drop_profile_qualified_pofv_geometry",
                    side_effect=lambda violations, _board: violations), \
                mock.patch(
                    "cec_score._drop_qualified_endpoint_neckdown_geometry",
                    return_value=[remaining]) as endpoint_filter:
            actual = dashboard._structural_issue_rows(
                {"violations": rows}, object())
        self.assertEqual(actual, [remaining])
        endpoint_filter.assert_called_once_with(rows, mock.ANY)

    def test_issue_map_is_a_first_class_analyzer_view_with_key(self):
        self.assertIn("id=\"m_issues\"", dashboard.PAGE)
        self.assertIn("mode==='all'?['issues'", dashboard.PAGE)
        self.assertIn("structural DRC", dashboard.PAGE)
        self.assertIn("implicated components", dashboard.PAGE)
        self.assertIn("route topology", open(
            os.path.join(ROOT, "scripts", "cec_dashboard.py"),
            encoding="utf-8").read())

    def test_current_density_is_a_first_class_dashboard_panel(self):
        self.assertIn("'current-density':'CURRENT DENSITY / COPPER NECKS", dashboard.PAGE)
        source = open(os.path.join(ROOT, "scripts", "cec_dashboard.py"),
                      encoding="utf-8").read()
        self.assertIn('summary["panels"]["current-density"]', source)
        self.assertIn('"top_current_bottlenecks"', source)

    def test_archive_recovers_board_hint_before_snapshot_rename(self):
        self.assertEqual(dashboard._thermal_board_hint(
            "/repo/build/angle-wave/hub-standard-rev2/winner.kicad_pcb"),
            "hub-standard-rev2")
        self.assertEqual(dashboard._thermal_board_hint(
            "/repo/beta/atx-24pin-rev3/candidate/board.kicad_pcb"),
            "atx-24pin-rev3")
        self.assertEqual(dashboard._thermal_board_hint(
            "/repo/output/review/atx-86x95-deadbug-r4.kicad_pcb"),
            "atx-24pin-rev3")
        self.assertEqual(dashboard._thermal_board_hint(
            "hub-s4011-craft-clean-placement"),
            "hub-standard-rev2")
        self.assertEqual(dashboard._thermal_board_hint(
            "/repo/beta/output-daughterboards/atx24-out-db/board.kicad_pcb"),
            "atx24-out-db")
        self.assertEqual(dashboard._thermal_board_hint(
            "/repo/beta/output-daughterboards/eps-out-db/board.kicad_pcb"),
            "eps-out-db")
        self.assertEqual(dashboard._thermal_board_hint(
            "/repo/beta/output-daughterboards/pcie-out-db/board.kicad_pcb"),
            "pcie-out-db")

    def test_thermal_injection_report_names_omitted_paths(self):
        result = types.SimpleNamespace(
            nets_requested={"/A": 1.0, "/B": 2.0, "/C": 3.0},
            nets_dropped={"/B": "open"}, nets_absent={"/C": "absent"})
        report = dashboard._thermal_injection_report(result)
        self.assertEqual(report["nets_injected"], 1)
        self.assertEqual(report["omitted"], ["/B", "/C"])

    def test_legacy_thermal_pass_is_invalid_without_geometry_proof(self):
        gates = {"ok": True, "kelvin_ok": True, "drc": 0, "unconnected": 0,
                 "foreign": {"status": "na"}}
        verdict, failing = dashboard._verdict(
            gates, {"ok": True, "verdict": "PASS", "dT": 1.0})
        self.assertEqual(verdict, "FAILED")
        self.assertEqual(failing, ["thermal-geometry"])

    def test_source_only_thermal_pass_can_be_clean(self):
        gates = {"ok": True, "kelvin_ok": True, "drc": 0, "unconnected": 0,
                 "foreign": {"status": "na"}}
        verdict, failing = dashboard._verdict(
            gates, {"ok": True, "verdict": "PASS",
                    "geometry_source": dashboard.THERMAL_GEOMETRY_SOURCE})
        self.assertEqual((verdict, failing), ("CLEAN", []))
        self.assertIn("geometry unproven", dashboard.PAGE)

    @unittest.skipUnless(shutil.which("kicad-cli") and shutil.which("rsvg-convert"),
                         "KiCad and rsvg-convert required for the real wave tile")
    def test_wave_tile_shows_added_in3_in4_without_temp_leak(self):
        from PIL import Image
        board = os.path.join(ROOT, "beta", "hub-standard-rev2", "candidate",
                             "hub-standard-rev2-candidate.kicad_pcb")
        with tempfile.TemporaryDirectory() as directory:
            output = os.path.join(directory, "six-layer.png")
            # Isolate the helper's temp root so the assertion remains stable if
            # unrelated tests also use /tmp.
            with mock.patch.object(cec_render.tempfile, "tempdir", directory):
                self.assertEqual(cec_render.hex_panel(board, output), output)
                self.assertEqual(glob.glob(os.path.join(directory, "cec_hex_*")), [])
            with Image.open(output) as image:
                self.assertGreaterEqual(image.width, 3000,
                                        "six layers require the 4-column tile")

    def test_beta_library_is_exactly_authoritative_manifest(self):
        boards = dashboard._beta_boards()
        self.assertEqual([board["name"] for board in boards],
                         list(manifest.CURRENT_BETA_BOARDS))
        self.assertEqual([board["name"] for board in boards
                          if os.path.basename(board["name"]).startswith("eps-8pin")],
                         ["eps-8pin-rev3"])

    def test_native_analysis_translates_workspace_paths(self):
        translated = dashboard._native_analysis_argv([
            "python3", "scripts/cec_dashboard.py",
            "/workspace/build/example/board.kicad_pcb",
        ])
        self.assertEqual(translated[:2], ["python3", "scripts/cec_dashboard.py"])
        self.assertEqual(translated[2],
                         os.path.join(ROOT, "build", "example", "board.kicad_pcb"))

    def test_native_analysis_preserves_environment_contract(self):
        with mock.patch.object(dashboard, "_docker_analysis_available",
                               return_value=False):
            completed = dashboard._container_run(
                [sys.executable, "-c",
                 "import os; print(os.environ['CEC_DASH_TEST'] + ' Ω')"],
                timeout=30, env={"CEC_DASH_TEST": "native"})
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout.strip(), "native Ω")

    def test_fem_and_gate_issue_evidence_use_separate_processes(self):
        source = open(os.path.join(ROOT, "scripts", "cec_dashboard.py"),
                      encoding="utf-8").read()
        analyzer = source[source.index("def _analyze_in_container"):
                          source.index("#  HOST half")]
        self.assertIn('"--analyze-gates"', analyzer)
        self.assertIn('encoding="utf-8", errors="replace"', analyzer)

    def test_foreign_pour_badge_separates_laid_and_reserved_authorities(self):
        source = open(os.path.join(ROOT, "scripts", "cec_dashboard.py"),
                      encoding="utf-8").read()
        gate = source[source.index("def _gate_issue_analysis"):
                      source.index("def _analyze_in_container")]
        self.assertIn("import cec_pour_clearance", gate)
        self.assertIn("cec_pour_clearance.inspect_file(board)", gate)
        self.assertIn('laid = dict(fp.get("laid") or {})', gate)
        self.assertIn('"reserved_corridor"', gate)
        self.assertNotIn("foreign_on_pour_summary(board)", gate)


if __name__ == "__main__":
    unittest.main()
