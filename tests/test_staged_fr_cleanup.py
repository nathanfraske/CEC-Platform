import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock


SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts")
sys.path.insert(0, SCRIPTS)

import cec_staged_fr as staged  # noqa: E402
import cec_fr  # noqa: E402
import cec_fr02  # noqa: E402
import cec_route_preflight  # noqa: E402
import pcbnew  # noqa: E402


class StagedRouterCleanupTests(unittest.TestCase):
    def test_tier_admission_rejects_the_historical_plus_six_drc_tolerance(self):
        old_fault = '["clearance","uuid",["old-a","old-b"]]'
        new_fault = '["shorting_items","uuid",["new-a","new-b"]]'
        before = {
            "drc": 1, "drc_types": {"clearance": 1},
            "unconnected": 12, "unconn_nets": ["/OPEN"],
            "kelvin_ok": True, "diffpair_ok": True,
            "structural_drc_identities": [old_fault],
        }
        # Numerically this is only +1 DRC and would have passed the former
        # ``delta <= +6`` tier gate.  It is still a new physical fault.
        after = {
            "drc": 2,
            "drc_types": {"clearance": 1, "shorting_items": 1},
            "unconnected": 11, "unconn_nets": ["/OPEN"],
            "kelvin_ok": True, "diffpair_ok": True,
            "structural_drc_identities": [old_fault, new_fault],
        }

        result = staged._tier_admission(before, after)

        self.assertFalse(result["accepted"])
        self.assertIn("drc_regressed", result["reasons"])
        self.assertIn("new_structural_drc_identity", result["reasons"])

    def test_xvfb_invocation_exposes_private_display_and_authority(self):
        self.assertEqual(
            cec_fr._xvfb_display_authority([
                "xvfb-run", "-a", "-n", "22828", "-f",
                "/tmp/private.xauth", "java", "-jar", "router.jar"]),
            (":22828", "/tmp/private.xauth"))
        self.assertIsNone(cec_fr._xvfb_display_authority(
            ["java", "-jar", "router.jar"]))

    def test_hidden_freerouting_exception_dialog_is_detected(self):
        probe = mock.Mock(
            stdout='0x2001e9 "Exception Occurred": ("fr" "fr")\n')
        cmd = ["xvfb-run", "-n", "42", "-f", "/tmp/auth",
               "java", "-jar", "router.jar"]
        with mock.patch.object(cec_fr.shutil, "which",
                               return_value="/usr/bin/xwininfo"), \
                mock.patch.object(cec_fr.subprocess, "run",
                                  return_value=probe) as run:
            self.assertTrue(cec_fr._fr_headless_exception_dialog(cmd))
        self.assertEqual(run.call_args.kwargs["env"]["DISPLAY"], ":42")
        self.assertEqual(
            run.call_args.kwargs["env"]["XAUTHORITY"], "/tmp/auth")

    def test_headless_exception_detector_ignores_normal_xvfb_windows(self):
        probe = mock.Mock(
            stdout='0x20002c "Board Layout": ("fr" "fr")\n')
        cmd = ["xvfb-run", "-n", "42", "-f", "/tmp/auth", "java"]
        with mock.patch.object(cec_fr.shutil, "which",
                               return_value="/usr/bin/xwininfo"), \
                mock.patch.object(cec_fr.subprocess, "run",
                                  return_value=probe):
            self.assertFalse(cec_fr._fr_headless_exception_dialog(cmd))

    def test_backend_failure_refuses_only_current_tier_and_keeps_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source.kicad_pcb")
            output = os.path.join(tmp, "output.kicad_pcb")
            work = os.path.join(tmp, "work")
            os.makedirs(work)
            with open(source, "w", encoding="utf-8") as handle:
                handle.write("proven-prefix")
            fake_board = mock.Mock()
            fake_board.GetTracks.return_value = []

            def export(_board, dsn):
                with open(dsn, "w", encoding="utf-8") as handle:
                    handle.write("dsn")

            with mock.patch.object(cec_fr, "ensure_jar",
                                   return_value="router.jar"), \
                    mock.patch.object(cec_fr, "copy_project_sidecars",
                                      return_value=[]), \
                    mock.patch.object(cec_fr, "export_dsn",
                                      side_effect=export), \
                    mock.patch.object(staged, "compile_tier_keepouts",
                                      return_value=[]), \
                    mock.patch.object(staged, "_dsn_restrict_to_nets",
                                      return_value=(1, 0)), \
                    mock.patch.object(cec_fr, "run_freerouting",
                                      side_effect=RuntimeError(
                                          "hidden GUI exception")), \
                    mock.patch.object(pcbnew, "LoadBoard",
                                      return_value=fake_board):
                report = staged._route_tiered_in_work(
                    source, output, work=work, tiers=[["/POWER"]],
                    include_residual=False, verbose=False)

            with open(output, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "proven-prefix")
            self.assertEqual(len(report["tiers"]), 1)
            self.assertTrue(report["tiers"][0]["refused"])
            self.assertEqual(
                report["tiers"][0]["reason"], "routing_backend_error")
            self.assertIn("hidden GUI exception",
                          report["tiers"][0]["error"])

    def test_adaptive_retry_chunks_are_bounded_and_deterministic(self):
        self.assertEqual(
            staged.adaptive_retry_chunks(["/D", "/B", "/A", "/C"]),
            [["/A", "/B"], ["/C", "/D"]])
        self.assertEqual(staged.adaptive_retry_chunks(["/ONLY"]),
                         [["/ONLY"]])
        self.assertEqual(staged.adaptive_retry_chunks([]), [])

    def test_adaptive_retry_requires_retained_topology_change(self):
        self.assertFalse(staged.adaptive_retry_warranted(
            ["/OPEN"], [], retry_depth=0, max_depth=2))
        self.assertTrue(staged.adaptive_retry_warranted(
            ["/OPEN"], ["/CLOSED"], retry_depth=0, max_depth=2))
        self.assertFalse(staged.adaptive_retry_warranted(
            ["/OPEN"], ["/CLOSED"], retry_depth=2, max_depth=2))

    def test_staged_delta_restores_every_parent_net_outside_active_tier(self):
        def track(net):
            item = mock.Mock()
            item.GetNetname.return_value = net
            return item

        board = mock.Mock()
        board.GetTracks.return_value = [
            track("/ACTIVE"), track("/ORDINARY"), track("/LOCKED"),
            track(""),
        ]

        self.assertEqual(
            staged.parent_copper_nets_outside_tier(board, {"/ACTIVE"}),
            {"/ORDINARY", "/LOCKED"})

    def test_empty_tier_delta_skips_import_sanitation(self):
        with mock.patch.dict(sys.modules, {"cec_synth_pipeline": None}):
            report, score = staged.sanitize_tier_import(
                "candidate.kicad_pcb", "parent.kicad_pcb", set())

        self.assertTrue(report["accepted"])
        self.assertEqual(report["reason"], "no_generated_copper")
        self.assertIsNone(score)

    def test_dsn_tier_filter_never_rewrites_wiring_net_references(self):
        deck = (
            "(pcb sample\n"
            "  (network\n"
            "    (net /KEEP (pins A-1 B-1))\n"
            "    (net /DROP (pins C-1 D-1))\n"
            "  )\n"
            "  (wiring\n"
            "    (wire (path F.Cu 100 0 0 10 0) (net /DROP) (type fix))\n"
            "    (via V 10 0 (net /DROP) (type fix))\n"
            "  )\n"
            ")\n")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "tier.dsn")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(deck)
            kept, stripped = staged._dsn_restrict_to_nets(path, {"/KEEP"})
            with open(path, encoding="utf-8") as handle:
                result = handle.read()

        self.assertEqual((kept, stripped), (1, 1))
        self.assertIn("(net /KEEP (pins A-1 B-1))", result)
        self.assertEqual(result.count("(net /DROP (pins))"), 1)
        self.assertIn("(wire (path F.Cu 100 0 0 10 0) (net /DROP) (type fix))",
                      result)
        self.assertIn("(via V 10 0 (net /DROP) (type fix))", result)

    def test_dsn_power_layer_rewrite_accepts_bare_and_quoted_aliases(self):
        with tempfile.TemporaryDirectory() as tmp:
            deck = os.path.join(tmp, "layers.dsn")
            with open(deck, "w", encoding="utf-8") as handle:
                handle.write(
                    '(structure\n'
                    ' (layer PWR (type signal))\n'
                    ' (layer "Inner Power" (type signal))\n'
                    ' (layer GND (type power))\n)')
            changed = cec_fr._dsn_force_power_layers(
                deck, ["PWR", "Inner Power", "GND"])
            self.assertEqual(changed, ["PWR", "Inner Power"])
            with open(deck, encoding="utf-8") as handle:
                text = handle.read()
            self.assertRegex(text, r'\(layer PWR \(type power\)\)')
            self.assertRegex(text,
                             r'\(layer "Inner Power" \(type power\)\)')

    def test_dsn_boundary_rejects_truncation_before_freerouting(self):
        with tempfile.TemporaryDirectory() as tmp:
            valid = os.path.join(tmp, "valid.dsn")
            with open(valid, "w", encoding="utf-8") as handle:
                handle.write('(pcb board (property "quoted ( text )"))\n')
            self.assertTrue(cec_fr.validate_dsn_structure(valid)["ok"])

            truncated = os.path.join(tmp, "truncated.dsn")
            with open(truncated, "w", encoding="utf-8") as handle:
                handle.write('(pcb board (structure (layer F.Cu (type signal)))\n')
            with self.assertRaisesRegex(RuntimeError, "truncated/unbalanced"):
                cec_fr.validate_dsn_structure(truncated)

    def test_dsn_boundary_accepts_specctra_quote_declaration(self):
        with tempfile.TemporaryDirectory() as tmp:
            valid = os.path.join(tmp, "valid-parser.dsn")
            with open(valid, "w", encoding="utf-8") as handle:
                handle.write(
                    '(pcb "board.dsn"\n'
                    '  (parser\n'
                    '    (string_quote ")\n'
                    '    (space_in_quoted_tokens on)\n'
                    '  )\n'
                    ')\n')
            report = cec_fr.validate_dsn_structure(valid)
        self.assertTrue(report["ok"])

    def test_dsn_rewriters_commit_by_atomic_replace(self):
        with tempfile.TemporaryDirectory() as tmp:
            deck = os.path.join(tmp, "route.dsn")
            with open(deck, "w", encoding="utf-8") as handle:
                handle.write(
                    '(pcb board\n'
                    ' (network (net /KEEP (pins A-1 B-1)))\n'
                    ' (wiring (wire (path F.Cu 100 0 0 1 0) '
                    '(net /KEEP) (type fix))))\n')
            cec_fr02.force_protect_in_dsn(deck, ["/KEEP"])
            cec_fr02.exclude_net_pins_in_dsn(deck, ["/KEEP"])
            self.assertTrue(cec_fr.validate_dsn_structure(deck)["ok"])
            with open(deck, encoding="utf-8") as handle:
                text = handle.read()
            self.assertIn("(type protect)", text)
            self.assertIn("(pins A-1)", text)
            self.assertFalse(any(
                name.startswith(".cec-dsn-") for name in os.listdir(tmp)))

    def test_new_tier_relocks_every_prior_owned_net(self):
        locked_calls = []
        sidecar_calls = []

        def spawn(worker, args):
            if worker is staged._import_stage_worker:
                cur, _ses, nxt, _final, _pours, _skip = args
                shutil.copy(cur, nxt)
                return None
            if worker is staged._lock_stage_worker:
                _board, nets = args
                locked_calls.append(tuple(nets))
                return len(nets)
            if worker is staged.restore_protected_copper_prefix:
                return {"nets": list(args[2]), "removed": 0,
                        "restored": 0}
            if worker is staged._route_quality_stage_worker:
                return {"ok": True, "issues": [], "refused_nets": [],
                        "removed_generated_items": 0}
            if worker is staged._refill_stage_worker:
                return True
            self.fail("unexpected staged worker")

        def export(_board, dsn):
            with open(dsn, "w", encoding="utf-8") as handle:
                handle.write("dsn")

        def run(_dsn, ses, **_kwargs):
            self.assertEqual(_kwargs["threads"], 4)
            with open(ses, "w", encoding="utf-8") as handle:
                handle.write("ses")

        signature = lambda _board, nets: {  # noqa: E731
            "sha256": "stable", "nets": sorted(nets), "items": 1}

        def copy_sidecars(source, destination):
            sidecar_calls.append((source, destination))
            return []

        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source.kicad_pcb")
            output = os.path.join(tmp, "output.kicad_pcb")
            with open(source, "w", encoding="utf-8") as handle:
                handle.write("board")
            work = os.path.join(tmp, "work")
            os.makedirs(work)
            fake_board = mock.Mock()
            fake_board.GetTracks.return_value = []
            with mock.patch.object(cec_fr, "ensure_jar",
                                   return_value="router.jar"), \
                    mock.patch.object(cec_fr, "copy_project_sidecars",
                                      side_effect=copy_sidecars), \
                    mock.patch.object(cec_fr, "export_dsn",
                                      side_effect=export), \
                    mock.patch.object(staged, "_dsn_restrict_to_nets",
                                      return_value=(2, 1)), \
                    mock.patch.object(cec_fr02,
                                      "force_protect_in_dsn"), \
                    mock.patch.object(cec_fr, "run_freerouting",
                                      side_effect=run), \
                    mock.patch.object(staged, "_spawn_apply",
                                      side_effect=spawn), \
                    mock.patch.object(staged, "_stage_score",
                                      return_value={
                                          "drc": 0, "drc_types": {},
                                          "unconnected": 0,
                                          "unconn_nets": [],
                                          "kelvin_ok": True,
                                          "diffpair_ok": True,
                                          "structural_drc_identities": [],
                                      }), \
                    mock.patch.object(staged, "fully_connected_nets",
                                      return_value=({"/CONTROL"}, set())), \
                    mock.patch.object(staged, "foreign_pour_admission",
                                      return_value={"ok": True,
                                                    "applicable": False,
                                                    "tracks": 0, "vias": 0}), \
                    mock.patch.object(cec_fr,
                                      "copper_geometry_signature",
                                      side_effect=signature), \
                    mock.patch.object(cec_fr,
                                      "locked_copper_keepouts",
                                      return_value=[]), \
                    mock.patch.object(cec_fr, "edge_keepout",
                                      return_value=[]), \
                    mock.patch.object(cec_fr, "smd_via_keepouts",
                                      return_value=[]), \
                    mock.patch.object(cec_fr,
                                      "decorative_copper_keepouts",
                                      return_value=[]), \
                    mock.patch.object(cec_fr, "fiducial_keepouts",
                                      return_value=[]), \
                    mock.patch.object(pcbnew, "LoadBoard",
                                      return_value=fake_board):
                staged._route_tiered_in_work(
                    source, output, work=work,
                    tiers=[["/CONTROL"]], pre_locked_nets=["/USB_D_P"],
                    threads=4, include_residual=False)
        self.assertEqual(locked_calls,
                         [("/CONTROL", "/USB_D_P")])
        self.assertEqual(sidecar_calls[0],
                         (source, os.path.join(work, "t0.kicad_pcb")))
        self.assertEqual(sidecar_calls[-1][1], output)

    def test_tier_keepouts_include_edge_fiducial_and_deduplicate(self):
        locked = {"name": "locked", "x0": 0, "y0": 0,
                  "x1": 1, "y1": 1, "layers": ("F.Cu",)}
        edge = {"name": "edge_top", "x0": 0, "y0": 0,
                "x1": 10, "y1": 1.25, "layers": ("F.Cu",)}
        via = {"name": "smd_via_guard", "x0": 2, "y0": 2,
               "x1": 3, "y1": 3, "layers": ("F.Cu",)}
        artwork = {"name": "decorative_LOGO1", "x0": 8, "y0": 8,
                   "x1": 9, "y1": 9, "layers": ("B.Cu",)}
        fiducial = {"name": "assembly_fiducial_FID1", "x0": 5,
                    "y0": 5, "x1": 7, "y1": 7,
                    "layers": ("F.Cu",)}
        with mock.patch.object(cec_fr, "locked_copper_keepouts",
                               return_value=[locked]), \
                mock.patch.object(cec_fr, "edge_keepout",
                                  return_value=[edge]), \
                mock.patch.object(cec_fr, "smd_via_keepouts",
                                  return_value=[via]), \
                mock.patch.object(cec_fr,
                                  "decorative_copper_keepouts",
                                  return_value=[artwork]), \
                mock.patch.object(cec_fr, "fiducial_keepouts",
                                  return_value=[fiducial]):
            rows = staged.compile_tier_keepouts(
                "board.kicad_pcb", {"/CONTROL"}, {"/USB_D_P"},
                hints=[fiducial])
        self.assertEqual(rows, [locked, fiducial, edge, via, artwork])

    def test_tier_keepouts_can_ablate_locked_geometry_but_keep_reservations(self):
        frozen_via = {
            "net": "/PWR", "kind": "bridge_via", "layer": "In2.Cu",
            "x0": 4.35, "y0": 5.35, "x1": 5.65, "y1": 6.65,
        }
        with mock.patch.dict(
                os.environ, {"CEC_LOCKED_COPPER_KEEPOUTS": "0"}), \
                mock.patch.object(cec_fr, "locked_copper_keepouts") as locked, \
                mock.patch.object(
                    cec_route_preflight, "compile_route_reservations",
                    return_value={"enabled": True,
                                  "corridors": [frozen_via]}), \
                mock.patch.object(cec_fr, "edge_keepout", return_value=[]), \
                mock.patch.object(cec_fr, "smd_via_keepouts", return_value=[]), \
                mock.patch.object(cec_fr, "decorative_copper_keepouts",
                                  return_value=[]), \
                mock.patch.object(cec_fr, "fiducial_keepouts", return_value=[]):
            rows = staged.compile_tier_keepouts(
                "board.kicad_pcb", {"/CONTROL"}, {"/LOCKED"})

        locked.assert_not_called()
        self.assertEqual(rows, [{
            "name": "route_reservation_bridge_via_0",
            "layers": ("In2.Cu",),
            "allow_tracks": False,
            "allow_vias": False,
            "x0": 4.35, "y0": 5.35, "x1": 5.65, "y1": 6.65,
        }])

    def test_tier_keepouts_include_exact_foreign_route_reservations(self):
        frozen_via = {
            "net": "/PWR", "kind": "bridge_via", "layer": "In2.Cu",
            "x0": 4.35, "y0": 5.35, "x1": 5.65, "y1": 6.65,
        }
        same_net = {
            "net": "/CONTROL", "kind": "frozen_pour", "layer": "F.Cu",
            "x0": 7.0, "y0": 8.0, "x1": 9.0, "y1": 10.0,
        }
        with mock.patch.object(cec_fr, "locked_copper_keepouts",
                               return_value=[]), \
                mock.patch.object(cec_route_preflight,
                                  "compile_route_reservations",
                                  return_value={"enabled": True,
                                                "corridors": [frozen_via,
                                                              same_net]}), \
                mock.patch.object(cec_fr, "edge_keepout", return_value=[]), \
                mock.patch.object(cec_fr, "smd_via_keepouts",
                                  return_value=[]), \
                mock.patch.object(cec_fr, "decorative_copper_keepouts",
                                  return_value=[]), \
                mock.patch.object(cec_fr, "fiducial_keepouts",
                                  return_value=[]):
            rows = staged.compile_tier_keepouts(
                "board.kicad_pcb", {"/CONTROL"}, set())

        self.assertEqual(rows, [{
            "name": "route_reservation_bridge_via_0",
            "layers": ("In2.Cu",),
            "allow_tracks": False,
            "allow_vias": False,
            "x0": 4.35, "y0": 5.35, "x1": 5.65, "y1": 6.65,
        }])

    def test_default_run_removes_work_tree_after_copy_out(self):
        seen = {}

        def fake_route(_placed, _out, **kwargs):
            seen["work"] = kwargs["work"]
            self.assertTrue(os.path.isdir(seen["work"]))
            return {"tiers": [], "work": seen["work"], "total_wall_s": 0.0}

        with mock.patch.dict(os.environ,
                             {"CEC_STAGED_FR_KEEP_INTERMEDIATES": "0"}), \
             mock.patch.object(staged, "_route_tiered_in_work",
                               side_effect=fake_route):
            report = staged.route_tiered("in.kicad_pcb", "out.kicad_pcb")

        self.assertIsNone(report["work"])
        self.assertFalse(os.path.exists(seen["work"]))

    def test_default_run_removes_work_tree_on_failure(self):
        seen = {}

        def fail(_placed, _out, **kwargs):
            seen["work"] = kwargs["work"]
            raise RuntimeError("tier failed")

        with mock.patch.dict(os.environ,
                             {"CEC_STAGED_FR_KEEP_INTERMEDIATES": "0"}), \
             mock.patch.object(staged, "_route_tiered_in_work", side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, "tier failed"):
                staged.route_tiered("in.kicad_pcb", "out.kicad_pcb")

        self.assertFalse(os.path.exists(seen["work"]))

    def test_debug_flag_retains_work_tree(self):
        seen = {}

        def fake_route(_placed, _out, **kwargs):
            seen["work"] = kwargs["work"]
            return {"tiers": [], "work": seen["work"], "total_wall_s": 0.0}

        with mock.patch.dict(os.environ,
                             {"CEC_STAGED_FR_KEEP_INTERMEDIATES": "1"}), \
             mock.patch.object(staged, "_route_tiered_in_work",
                               side_effect=fake_route):
            report = staged.route_tiered("in.kicad_pcb", "out.kicad_pcb")

        self.assertEqual(report["work"], seen["work"])
        self.assertTrue(os.path.isdir(seen["work"]))
        shutil.rmtree(seen["work"])


if __name__ == "__main__":
    unittest.main()
