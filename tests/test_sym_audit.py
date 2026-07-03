#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Unit tests for scripts/cec_sym_audit.py (T2, docs/schematic-quality-charter.md).
# Host-runnable, stdlib only (no pcbnew/KiCad dependency -- the auditor only
# ever reads .kicad_sym text, never opens a board).
#
# Per the charter's "teeth first" principle: a checker is trusted only after
# it demonstrably FAILS on a real bad example. TestFixtureTeeth below builds a
# deliberately mistyped symbol (a VDD pin typed 'passive', a GND pin left
# 'unspecified') and asserts the auditor catches BOTH at high confidence, then
# builds a correctly-typed twin and asserts it comes back clean.
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_sym_audit as A  # noqa: E402


def _wrap(symbol_body: str) -> str:
    return f'(kicad_symbol_lib (version 20251024) (generator "test") {symbol_body})'


def _pin(etype: str, name: str, number: str, x: str = "0", y: str = "0") -> str:
    return (
        f'(pin {etype} line (at {x} {y} 0) (length 2.54) '
        f'(name "{name}" (effects (font (size 1.27 1.27)))) '
        f'(number "{number}" (effects (font (size 1.27 1.27)))))'
    )


MISTYPED_SYMBOL = _wrap(f'''
(symbol "TEST_MISTYPE"
  (property "Reference" "U" (at 0 0 0))
  (symbol "TEST_MISTYPE_0_1"
    (rectangle (start -5 5) (end 5 -5) (stroke (width 0.254) (type default)) (fill (type background)))
  )
  (symbol "TEST_MISTYPE_1_1"
    {_pin("passive", "VDD", "1")}
    {_pin("unspecified", "GND", "2")}
    {_pin("input", "EN", "3")}
    {_pin("bidirectional", "SDA", "4")}
    {_pin("no_connect", "NC", "5")}
  )
)
''')

CLEAN_SYMBOL = _wrap(f'''
(symbol "TEST_CLEAN"
  (property "Reference" "U" (at 0 0 0))
  (symbol "TEST_CLEAN_0_1"
    (rectangle (start -5 5) (end 5 -5) (stroke (width 0.254) (type default)) (fill (type background)))
  )
  (symbol "TEST_CLEAN_1_1"
    {_pin("power_in", "VDD", "1")}
    {_pin("power_in", "GND", "2")}
    {_pin("input", "EN", "3")}
    {_pin("bidirectional", "SDA", "4")}
    {_pin("no_connect", "NC", "5")}
    {_pin("input", "RST_N", "6")}
    {_pin("output", "DOUT", "7")}
  )
)
''')

# The real-world false-positive shape this tool must NOT flag at high
# confidence: a quad-mode flash pin whose name bundles a control function
# (RESET) with a data-bus alternate (IO3) in the SAME '/'-alt segment. The
# only sane type for it is 'bidirectional' (already correct) -- the auditor
# must recognize the internal conflict and stay silent, not assert 'input'.
QUAD_PIN_SYMBOL = _wrap(f'''
(symbol "TEST_QUADPIN"
  (property "Reference" "U" (at 0 0 0))
  (symbol "TEST_QUADPIN_0_1"
    (rectangle (start -5 5) (end 5 -5) (stroke (width 0.254) (type default)) (fill (type background)))
  )
  (symbol "TEST_QUADPIN_1_1"
    {_pin("bidirectional", "/HOLD_/RESET_IO3", "1")}
  )
)
''')

# A GPIO/HSIO multi-function ball (FPGA/SoC-class part): bidirectional is
# already the right call and must not be second-guessed.
GPIO_SYMBOL = _wrap(f'''
(symbol "TEST_GPIO"
  (property "Reference" "U" (at 0 0 0))
  (symbol "TEST_GPIO_1_1"
    {_pin("bidirectional", "GPIO12PB1/CLKIN_S_4", "1")}
  )
)
''')


class TestParser(unittest.TestCase):
    def test_roundtrip_pin_counts(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".kicad_sym", delete=False) as fh:
            fh.write(CLEAN_SYMBOL)
            path = fh.name
        try:
            syms = A.load_symbols(path)
            self.assertEqual(len(syms), 1)
            self.assertEqual(syms[0].name, "TEST_CLEAN")
            self.assertEqual(len(syms[0].pins), 7)
            by_num = {p.number: p for p in syms[0].pins}
            self.assertEqual(by_num["1"].name, "VDD")
            self.assertEqual(by_num["1"].etype, "power_in")
        finally:
            os.unlink(path)

    def test_real_libraries_parse_and_pin_counts_match(self):
        # Calibration check (charter principle 3): the parser must recover
        # every pin, not an undercount from a fragile regex. These counts
        # were independently verified against the real files.
        expected = {
            "cec-ent-power.kicad_sym": 106,
            "cec-ent-net.kicad_sym": 106,
            "cec-ent-compute.kicad_sym": 484,
            "cec-ent-mcu.kicad_sym": 290,
        }
        libdir = os.path.join(ROOT, "lib")
        for fname, count in expected.items():
            path = os.path.join(libdir, fname)
            if not os.path.exists(path):
                self.skipTest(f"{fname} not present in this checkout")
            syms = A.load_symbols(path)
            total = sum(len(s.pins) for s in syms)
            self.assertEqual(total, count, f"{fname}: pin count mismatch")


class TestFixtureTeeth(unittest.TestCase):
    """The teeth: a real bad symbol must fail, a real clean symbol must pass."""

    def _findings_for(self, text):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".kicad_sym", delete=False) as fh:
            fh.write(text)
            path = fh.name
        try:
            syms = A.load_symbols(path)
            self.assertEqual(len(syms), 1)
            return A.audit_symbol(syms[0])
        finally:
            os.unlink(path)

    def test_mistyped_vdd_is_flagged_high_confidence(self):
        findings = self._findings_for(MISTYPED_SYMBOL)
        vdd = [f for f in findings if f.pin_name == "VDD"]
        self.assertEqual(len(vdd), 1, findings)
        self.assertEqual(vdd[0].current_type, "passive")
        self.assertEqual(vdd[0].proposed_type, "power_in")
        self.assertEqual(vdd[0].confidence, "high")

    def test_unspecified_gnd_is_flagged(self):
        findings = self._findings_for(MISTYPED_SYMBOL)
        gnd = [f for f in findings if f.pin_name == "GND"]
        self.assertEqual(len(gnd), 1, findings)
        self.assertEqual(gnd[0].current_type, "unspecified")
        self.assertEqual(gnd[0].proposed_type, "power_in")
        self.assertEqual(gnd[0].confidence, "high")

    def test_mistyped_symbol_has_no_other_false_positives(self):
        # EN/SDA/NC on the same fixture are already correctly typed and must
        # not generate noise.
        findings = self._findings_for(MISTYPED_SYMBOL)
        flagged_names = {f.pin_name for f in findings}
        self.assertEqual(flagged_names, {"VDD", "GND"})

    def test_clean_symbol_has_zero_findings(self):
        findings = self._findings_for(CLEAN_SYMBOL)
        self.assertEqual(findings, [], findings)

    def test_quad_mode_pin_not_falsely_asserted(self):
        # Regression guard for the real W25Q256JVFIQ false-positive found
        # during calibration: a RESET/IOn combo pin must NOT be flagged as a
        # high-confidence 'input' mismatch (it is genuinely bidirectional).
        findings = self._findings_for(QUAD_PIN_SYMBOL)
        high = [f for f in findings if f.confidence == "high"]
        self.assertEqual(high, [], high)

    def test_gpio_multifunction_pin_not_flagged(self):
        findings = self._findings_for(GPIO_SYMBOL)
        self.assertEqual(findings, [], findings)

    def test_master_side_cs_output_is_accepted(self):
        # Orientation-dependent classes (CS/RST): a deliberate input OR output
        # is a valid directional call (a bus MASTER's CS is an output -- the
        # MPFS MSS_DDR_CS0/1 + ESP32-P4 FLASH_CS hand overrides, 2026-07-03).
        # Only unspecified/bidirectional stay suspect for those rules.
        sym = _wrap(f'''
(symbol "TEST_MASTER_CS"
  (property "Reference" "U" (at 0 0 0))
  (symbol "TEST_MASTER_CS_0_1"
    (rectangle (start -5 5) (end 5 -5) (stroke (width 0.254) (type default)) (fill (type background)))
  )
  (symbol "TEST_MASTER_CS_1_1"
    {_pin("output", "FLASH_CS", "1")}
    {_pin("input", "CS2", "2")}
    {_pin("output", "RESET_DRV", "3")}
    {_pin("bidirectional", "CS3", "4")}
  )
)
''')
        findings = self._findings_for(sym)
        # pins 1-3 (deliberate input/output on CS/RST names): no finding at all
        for f in findings:
            self.assertNotIn(f.pin_number, ("1", "2", "3"), findings)
        # pin 4 (bidirectional CS) STAYS suspect -- the accept must not widen
        cs3 = [f for f in findings if f.pin_number == "4"]
        self.assertEqual(len(cs3), 1, findings)
        self.assertEqual(cs3[0].proposed_type, "input")


class TestCLI(unittest.TestCase):
    def test_audit_exit_code_high_confidence_gates(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".kicad_sym", delete=False) as fh:
            fh.write(MISTYPED_SYMBOL)
            bad_path = fh.name
        with tempfile.NamedTemporaryFile("w", suffix=".kicad_sym", delete=False) as fh:
            fh.write(CLEAN_SYMBOL)
            clean_path = fh.name
        try:
            self.assertEqual(A.main(["--audit", bad_path]), 1)
            self.assertEqual(A.main(["--audit", clean_path]), 0)
        finally:
            os.unlink(bad_path)
            os.unlink(clean_path)


if __name__ == "__main__":
    unittest.main()
