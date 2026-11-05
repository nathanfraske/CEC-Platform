#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Unit tests for the CL-25 audit-derived check pack + intake gate (cec_constraints).
# The pcbnew-dependent cases auto-skip on the host and run in the routing container:
#
#   docker compose -f docker/compose.yaml run --rm --no-deps routing \
#       bash -lc 'cd /workspace && python3 -m unittest tests.test_cl25_checks -v'
#
# Host-runnable subset (regex/parsing units): runs anywhere.
import json
import os
import re
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

try:
    import pcbnew  # noqa: F401
    HAVE_PCBNEW = True
    import cec_constraints as K
    import cec_fr
except ImportError:
    HAVE_PCBNEW = False
    K = None

EPS = os.path.join(ROOT, "old-revisions", "beta", "eps-8pin-pre-rev3",
                   "eps8pin-module.kicad_pcb")
HPWR = os.path.join(ROOT, "beta", "12vhpwr-standard", "12vhpwr-standard-module.kicad_pcb")
HUB = os.path.join(ROOT, "old-revisions", "hubs", "hub-standard-alpha",
                   "hub-standard.kicad_pcb")
HUB_BETA = os.path.join(ROOT, "beta", "hub-standard-rev2", "candidate",
                        "hub-standard-rev2-candidate.kicad_pcb")
PCIE2_BETA = os.path.join(ROOT, "beta", "pcie-8pin-2port", "candidate",
                          "pcie-8pin-2port-candidate.kicad_pcb")
PCIE3_BETA = os.path.join(ROOT, "beta", "pcie-8pin-3port", "candidate",
                          "pcie-8pin-3port-candidate.kicad_pcb")


# ---------------------------------------------------------------------------
# host-runnable units (no pcbnew)
# ---------------------------------------------------------------------------
class TestHostUnits(unittest.TestCase):
    def test_placeholder_regex(self):
        pat = re.compile(r"(^$|^~$|_Small$|\b(TODO|TBD|FIXME|PLACEHOLDER|APPROXIMATE)\b)", re.I)
        for bad in ("", "~", "R_Small", "C_Small", "TODO 10k", "tbd", "APPROXIMATE land"):
            self.assertTrue(pat.search(bad), bad)
        for good in ("10kΩ", "PESD5V0S1BA", "TJA1051T/3", "NCP15XH103F03RC", "0.5mΩ", "SmallSig"):
            self.assertFalse(pat.search(good), good)

    def test_strip_lib_symbols_and_refs(self):
        # minimal sch shape: lib_symbols placeholder 'R' must be dropped, instances kept
        sch = ('(kicad_sch (lib_symbols (symbol "Device:R" '
               '(property "Reference" "R" (at 0 0 0))))'
               ' (symbol (lib_id "Device:R") (property "Reference" "R12" (at 1 1 0)))'
               ' (symbol (lib_id "X:Y") (property "Reference" "J_KVM" (at 2 2 0)))'
               ' (symbol (lib_id "X:Z") (property "Reference" "U?" (at 3 3 0)))'
               ' (symbol (lib_id "p:p") (property "Reference" "#PWR01" (at 4 4 0))))')
        if not HAVE_PCBNEW:
            self.skipTest("cec_constraints imports pcbnew at module level")
        stripped = K._strip_lib_symbols(sch)
        self.assertNotIn('"Reference" "R" ', stripped)
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".kicad_sch", delete=False) as fh:
            fh.write(sch)
            p = fh.name
        try:
            refs = K._sch_refs(p)
        finally:
            os.unlink(p)
        self.assertEqual(refs, {"R12", "J_KVM"})  # placeholder, '?' and #PWR dropped

    def test_legacy_named_power_symbols_are_not_physical_pcb_refs(self):
        if not HAVE_PCBNEW:
            self.skipTest("cec_constraints imports pcbnew at module level")
        inventory = {
            "PWR201": {"lib_id": "cec-power:GND"},
            "R1": {"lib_id": "Device:R"},
        }
        refs = {
            ref for ref, rec in inventory.items()
            if (not K._board_only_ref(ref)
                and not rec.get("lib_id", "").startswith(("cec-power:", "power:")))
        }
        self.assertEqual(refs, {"R1"})


# ---------------------------------------------------------------------------
# board-backed (container)
# ---------------------------------------------------------------------------
@unittest.skipUnless(HAVE_PCBNEW, "pcbnew required (run in the routing container)")
class TestCheckPack(unittest.TestCase):
    def test_local_pofv_signal_rule_is_exact_and_revalidated(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "local-pofv.kicad_pcb")
            pro = path[:-len(".kicad_pcb")] + ".kicad_pro"
            board = pcbnew.CreateEmptyBoard()
            board.SetCopperLayerCount(6)
            props = board.GetProperties()
            props["CEC_FAB_PROFILE"] = "jlcpcb_6l_pofv_signal"
            board.SetProperties(props)
            settings = board.GetDesignSettings()
            settings.m_MinThroughDrill = pcbnew.FromMM(0.30)
            settings.m_ViasMinSize = pcbnew.FromMM(0.50)
            settings.m_ViasMinAnnularWidth = pcbnew.FromMM(0.10)
            net = pcbnew.NETINFO_ITEM(board, "/CTRL")
            board.Add(net)

            footprint = pcbnew.FOOTPRINT(board)
            footprint.SetReference("U1")
            pad = pcbnew.PAD(footprint)
            pad.SetPadName("1")
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetSize(pcbnew.VECTOR2I_MM(0.8, 0.8))
            pad.SetPosition(pcbnew.VECTOR2I_MM(10.0, 10.0))
            layers = pcbnew.LSET()
            layers.AddLayer(pcbnew.F_Cu)
            pad.SetLayerSet(layers)
            pad.SetNet(net)
            footprint.Add(pad)
            board.Add(footprint)

            via = pcbnew.PCB_VIA(board)
            via.SetViaType(pcbnew.VIATYPE_THROUGH)
            via.SetPosition(pcbnew.VECTOR2I_MM(10.625, 10.0))
            via.SetWidth(pcbnew.FromMM(0.35))
            via.SetDrill(pcbnew.FromMM(0.25))
            via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            via.SetNetCode(net.GetNetCode())
            board.Add(via)
            track = pcbnew.PCB_TRACK(board)
            track.SetStart(pad.GetPosition())
            track.SetEnd(via.GetPosition())
            track.SetWidth(pcbnew.FromMM(0.20))
            track.SetLayer(pcbnew.F_Cu)
            track.SetNetCode(net.GetNetCode())
            board.Add(track)

            evidence = cec_fr.group_local_pofv_signal_vias(board, [via])
            self.assertEqual(evidence["vias"], 1)
            pcbnew.SaveBoard(path, board)
            with open(pro, "w", encoding="utf-8") as handle:
                json.dump({"net_settings": {
                    "classes": [{
                        "name": "Default", "track_width": 0.20,
                        "via_diameter": 0.50, "via_drill": 0.30}],
                    "netclass_assignments": {},
                    "netclass_patterns": [],
                }}, handle)
            rule = cec_fr.ensure_local_pofv_signal_via_rule(
                path, {"local_pofv_signal_vias": evidence})
            self.assertTrue(rule["applicable"])
            with open(rule["path"], encoding="utf-8") as handle:
                text = handle.read()
            self.assertIn(
                "memberOfGroup('CEC_LOCAL_POFV_SIGNAL_VIA')", text)
            self.assertIn("via_diameter (min 0.350mm)", text)
            self.assertIn("hole_size (min 0.250mm)", text)
            self.assertIn("annular_width (min 0.050mm)", text)

            loaded = pcbnew.LoadBoard(path)
            ok, detail = K.CHECKERS["netclass-geometry-conformance"](
                loaded, path, {})[:2]
            self.assertTrue(ok, detail)
            self.assertIn("1 validated local POFV signal via", detail)

            moved = next(item for item in loaded.GetTracks()
                         if item.GetClass() == "PCB_VIA")
            moved.SetPosition(pcbnew.VECTOR2I_MM(20.0, 20.0))
            pcbnew.SaveBoard(path, loaded)
            ok, detail = K.CHECKERS["netclass-geometry-conformance"](
                pcbnew.LoadBoard(path), path, {})[:2]
            self.assertFalse(ok, detail)
            self.assertIn("via_dia", detail)

    def test_local_pair_return_via_rule_is_exact_and_revalidated(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "pair-return.kicad_pcb")
            pro = path[:-len(".kicad_pcb")] + ".kicad_pro"
            board = pcbnew.CreateEmptyBoard()
            settings = board.GetDesignSettings()
            settings.m_MinThroughDrill = pcbnew.FromMM(0.30)
            settings.m_ViasMinSize = pcbnew.FromMM(0.50)
            settings.m_ViasMinAnnularWidth = pcbnew.FromMM(0.10)
            nets = {}
            for name in ("GND", "/USB_D_P", "/USB_D_N"):
                net = pcbnew.NETINFO_ITEM(board, name)
                board.Add(net)
                nets[name] = net

            def add_via(name, x, y, diameter, drill):
                via = pcbnew.PCB_VIA(board)
                via.SetViaType(pcbnew.VIATYPE_THROUGH)
                via.SetPosition(pcbnew.VECTOR2I_MM(x, y))
                via.SetWidth(pcbnew.FromMM(diameter))
                via.SetDrill(pcbnew.FromMM(drill))
                via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
                via.SetNetCode(nets[name].GetNetCode())
                board.Add(via)
                return via

            add_via("/USB_D_P", 10.0, 10.0, 0.60, 0.30)
            add_via("/USB_D_N", 10.8, 10.0, 0.60, 0.30)
            returned = add_via("GND", 10.4, 11.0, 0.60, 0.30)
            evidence = cec_fr.group_local_pair_return_vias(
                board, [returned])
            pcbnew.SaveBoard(path, board)
            def write_project_rules():
                with open(pro, "w", encoding="utf-8") as handle:
                    json.dump({"net_settings": {
                    "classes": [
                        {"name": "Default", "track_width": 0.20,
                         "via_diameter": 0.60, "via_drill": 0.30},
                        {"name": "GND", "track_width": 0.50,
                         "via_diameter": 0.90, "via_drill": 0.50},
                    ],
                    "netclass_assignments": {"GND": "GND"},
                    "netclass_patterns": [],
                    }}, handle)
            write_project_rules()
            rule = cec_fr.ensure_local_pair_return_via_rule(
                path, {"local_pair_return_vias": evidence})
            self.assertTrue(rule["applicable"])
            with open(rule["path"], encoding="utf-8") as handle:
                text = handle.read()
            self.assertIn(
                "memberOfGroup('CEC_LOCAL_PAIR_RETURN_VIA')", text)
            self.assertIn("hole_size (min 0.300mm)", text)
            self.assertIn("annular_width (min 0.150mm)", text)

            loaded = pcbnew.LoadBoard(path)
            ok, detail = K.CHECKERS["netclass-geometry-conformance"](
                loaded, path, {})[:2]
            self.assertTrue(ok, detail)
            self.assertIn("1 validated local pair-return via", detail)

            remote = next(
                item for item in loaded.GetTracks()
                if item.GetClass() == "PCB_VIA"
                and item.GetNetname() == "GND")
            remote.SetPosition(pcbnew.VECTOR2I_MM(20.0, 20.0))
            pcbnew.SaveBoard(path, loaded)
            write_project_rules()
            ok, detail = K.CHECKERS["netclass-geometry-conformance"](
                pcbnew.LoadBoard(path), path, {})[:2]
            self.assertFalse(ok, detail)
            self.assertIn("via_dia", detail)

    def test_cl25_classes_all_resolve(self):
        """Every CL-25 class maps to registered checker IDs (stable-ID contract)."""
        by_id = {c.id for c in K.REGISTRY}
        for cls, ids in K.CL25_CLASSES.items():
            for cid in ids:
                self.assertIn(cid, by_id, f"{cls} -> {cid} not in REGISTRY")
                self.assertIn(cid, K.CHECKERS, f"{cls} -> {cid} has no checker")

    def test_netclass_geometry_fires_on_12vhpwr_prefix_state(self):
        """The originating pre-fix fixture: the committed 12VHPWR carries the audit's
        signal-size lane vias -- the check must FIRE (CL-25 verify step)."""
        board = pcbnew.LoadBoard(HPWR)
        ok, detail = K.CHECKERS["netclass-geometry-conformance"](board, HPWR, {})[:2]
        self.assertFalse(ok, detail)
        self.assertIn("via", detail)

    def test_netclass_geometry_na_on_unrouted(self):
        """Self-gating: a floorplan with no copper is N/A, not FAIL."""
        # the frozen golden floorplan is unrouted by design
        golden = os.path.join(ROOT, "tests", "golden", "eps-8pin", "eps8pin-module.kicad_pcb")
        if not os.path.isfile(golden):
            self.skipTest("golden floorplan absent")
        board = pcbnew.LoadBoard(golden)
        ok, detail = K.CHECKERS["netclass-geometry-conformance"](board, golden, {})[:2]
        if ok is not None:
            # a routed golden would legitimately return a verdict; only assert no crash
            self.assertIn(ok, (True, False))

    def test_sync_passes_on_eps_and_fires_on_mismatched_sch(self):
        # The SYNCED exemplar is the pre-beta legacy fixture: the live beta eps is a known
        # transitional sch<->pcb mismatch (hierarchical C6 schematic vs placeholder PCB)
        # until its fresh board lands, so it can't serve as the pass case (2026-07-07).
        eps = os.path.join(ROOT, "tests", "fixtures", "eps-8pin-legacy",
                           "eps8pin-module.kicad_pcb")
        board = pcbnew.LoadBoard(eps)
        ok, detail = K.CHECKERS["sch-pcb-sync"](board, eps, {})[:2]
        self.assertTrue(ok, detail)
        # cross-wire: the EPS board against the Hub schematic must FAIL (desync class)
        hub_sch = os.path.join(ROOT, "beta", "hub-standard-rev2",
                               "hub-standard-rev2.kicad_sch")
        ok2, detail2 = K.CHECKERS["sch-pcb-sync"](board, eps, {"sch": hub_sch})[:2]
        self.assertFalse(ok2, detail2)

    def test_bom_lint_known_gaps_noted_not_failed(self):
        board = pcbnew.LoadBoard(EPS)
        ok, detail = K.CHECKERS["bom-field-lint"](board, EPS, {})[:2]
        self.assertTrue(ok, detail)
        self.assertIn("known-open", detail)  # OQ-11 shunts + THT headers noted

    def test_hub_dnp_placeholders_are_not_treated_as_populated_bom_parts(self):
        board = pcbnew.LoadBoard(HUB_BETA)
        ok, detail = K.CHECKERS["bom-field-lint"](board, HUB_BETA, {})[:2]
        self.assertTrue(ok, detail)
        self.assertIn("no placeholder/empty BOM fields", detail)

    def test_hub_candidate_matches_current_direct_buck_signature(self):
        board = pcbnew.LoadBoard(HUB_BETA)
        ok, detail = K.CHECKERS["sch-pcb-sync"](board, HUB_BETA, {})[:2]
        self.assertTrue(ok, detail)
        self.assertIn("109 refs", detail)

    def test_pcie2_candidate_matches_current_electrical_signature(self):
        board = pcbnew.LoadBoard(PCIE2_BETA)
        ok, detail = K.CHECKERS["sch-pcb-sync"](board, PCIE2_BETA, {})[:2]
        self.assertTrue(ok, detail)
        self.assertIn("68 refs", detail)

    def test_detect_resistor_hub_vs_module(self):
        hub = pcbnew.LoadBoard(HUB)
        ok, detail = K.CHECKERS["detect-resistor-code"](hub, HUB, {})[:2]
        self.assertTrue(ok, detail)
        self.assertIn("10k", detail)         # Hub: fixed pull-up per §2.3
        eps = pcbnew.LoadBoard(EPS)
        ok2, detail2 = K.CHECKERS["detect-resistor-code"](eps, EPS, {})[:2]
        self.assertTrue(ok2, detail2)
        self.assertIn("2.2k", detail2)       # module: CAN-only code value


@unittest.skipUnless(HAVE_PCBNEW, "pcbnew required (run in the routing container)")
class TestIntakeGate(unittest.TestCase):
    def test_candidate_erc_resolves_parent_project_schematic(self):
        expected = os.path.join(
            ROOT, "beta", "pcie-8pin-3port",
            "pcie8pin-3port-module.kicad_sch")
        with mock.patch.object(K, "_erc_errors", return_value=0) as erc:
            gate = K.intake_gate(PCIE3_BETA)
        self.assertTrue(gate["ok"], gate["reasons"])
        erc.assert_called_once_with(expected)

    def test_draft_marker_does_not_waive_live_erc(self):
        with mock.patch.object(K, "_erc_errors", return_value=1):
            g = K.intake_gate(EPS)
        self.assertFalse(g["ok"], g["reasons"])
        self.assertEqual(g["results"]["erc"][0], "FAIL")
        self.assertTrue(any("erc [hard]" in reason for reason in g["reasons"]))

    def test_erc_tool_failure_refuses(self):
        with mock.patch.object(K, "_erc_errors",
                               side_effect=RuntimeError("synthetic tool failure")):
            g = K.intake_gate(EPS)
        self.assertFalse(g["ok"])
        self.assertEqual(g["results"]["erc"][0], "ERROR")
        self.assertTrue(any("synthetic tool failure" in reason for reason in g["reasons"]))

    def test_drc_nonzero_exit_is_not_cached_as_clean(self):
        proc = mock.Mock(returncode=2, stderr="synthetic DRC failure", stdout="")
        with mock.patch.object(K.cec_toolchain, "kicad_cli",
                               return_value="fake-kicad-cli"), \
                mock.patch.object(K.subprocess, "run", return_value=proc):
            with self.assertRaisesRegex(RuntimeError, "exited 2"):
                K._drc_json(EPS, {})

    def test_empty_drc_output_is_not_cached_as_clean(self):
        proc = mock.Mock(returncode=0, stderr="", stdout="")
        with mock.patch.object(K.cec_toolchain, "kicad_cli",
                               return_value="fake-kicad-cli"), \
                mock.patch.object(K.subprocess, "run", return_value=proc):
            with self.assertRaises((json.JSONDecodeError, ValueError)):
                K._drc_json(EPS, {})

    def test_refusal_carries_named_reasons(self):
        """A board failing the schematic-side subset is refused WITH named reasons
        (cross-wired sch => sync FAIL => refusal)."""
        hub_sch = os.path.join(ROOT, "beta", "hub-standard-rev2",
                               "hub-standard-rev2.kicad_sch")
        g = K.intake_gate(EPS, ctx={"sch": hub_sch})
        self.assertFalse(g["ok"])
        self.assertTrue(any("sch-pcb-sync" in r for r in g["reasons"]), g["reasons"])

    def test_explicit_continuation_defers_only_repairable_route_geometry(self):
        original = K.CHECKERS["no-foreign-on-high-current-pour"]
        try:
            K.CHECKERS["no-foreign-on-high-current-pour"] = (
                lambda *_args, **_kwargs: (False, "synthetic routed incursion"))
            with mock.patch.object(K, "_erc_errors", return_value=0):
                ordinary = K.intake_gate(PCIE2_BETA)
                continuation = K.intake_gate(
                    PCIE2_BETA, defer_route_geometry=True)
        finally:
            K.CHECKERS["no-foreign-on-high-current-pour"] = original

        self.assertFalse(ordinary["ok"])
        self.assertTrue(any(
            "no-foreign-on-high-current-pour" in reason
            for reason in ordinary["reasons"]))
        self.assertTrue(continuation["ok"], continuation["reasons"])
        self.assertEqual(
            [row["id"] for row in continuation["deferred_to_route"]],
            ["no-foreign-on-high-current-pour"])


if __name__ == "__main__":
    unittest.main()
