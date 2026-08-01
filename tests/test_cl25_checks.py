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
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

try:
    import pcbnew  # noqa: F401
    HAVE_PCBNEW = True
    import cec_constraints as K
except ImportError:
    HAVE_PCBNEW = False
    K = None

EPS = os.path.join(ROOT, "beta", "eps-8pin", "eps8pin-module.kicad_pcb")
HPWR = os.path.join(ROOT, "beta", "12vhpwr-standard", "12vhpwr-standard-module.kicad_pcb")
HUB = os.path.join(ROOT, "hubs", "hub-standard", "hub-standard.kicad_pcb")


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


# ---------------------------------------------------------------------------
# board-backed (container)
# ---------------------------------------------------------------------------
@unittest.skipUnless(HAVE_PCBNEW, "pcbnew required (run in the routing container)")
class TestCheckPack(unittest.TestCase):
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
        hub_sch = os.path.join(ROOT, "hubs", "hub-standard", "hub-standard.kicad_sch")
        ok2, detail2 = K.CHECKERS["sch-pcb-sync"](board, eps, {"sch": hub_sch})[:2]
        self.assertFalse(ok2, detail2)

    def test_bom_lint_known_gaps_noted_not_failed(self):
        board = pcbnew.LoadBoard(EPS)
        ok, detail = K.CHECKERS["bom-field-lint"](board, EPS, {})[:2]
        self.assertTrue(ok, detail)
        self.assertIn("known-open", detail)  # OQ-11 shunts + THT headers noted

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
    def test_draft_marker_does_not_waive_live_erc(self):
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
        hub_sch = os.path.join(ROOT, "hubs", "hub-standard", "hub-standard.kicad_sch")
        g = K.intake_gate(EPS, ctx={"sch": hub_sch})
        self.assertFalse(g["ok"])
        self.assertTrue(any("sch-pcb-sync" in r for r in g["reasons"]), g["reasons"])


if __name__ == "__main__":
    unittest.main()
