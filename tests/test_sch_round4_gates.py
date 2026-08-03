#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Tests for scripts/cec_sch_gates.py (round-4 checker/mutator toolkit) and
# the cec_sch_layout.power_ladder_runs geometry helper it builds on.
# HOST-RUNNABLE: needs only kicad-cli on PATH for the kicad-cli-gated tests
# (netlist/ERC ground truth); the pure-parser tests need nothing extra.
#
#   python3 -m unittest tests.test_sch_round4_gates -v
import os
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_sch                    # noqa: E402
import cec_sch_layout as L        # noqa: E402
import cec_sch_gates as G         # noqa: E402

HAVE_KICAD_CLI = True
try:
    subprocess.run(["kicad-cli", "version"], capture_output=True, check=True)
except Exception:
    HAVE_KICAD_CLI = False

# The teeth demos anchor to the LAST FLAT revision of the 12vhpwr sheet (the
# board the owner's round-4 complaint described: regions clipping each other
# + overrunning the page). The live board is hierarchical since Wave 3b and
# containment/bounds-CLEAN, so the real-bad-example is materialized from git
# history (self-contained flat file, embedded lib_symbols).
_FLAT_12VHPWR_REV = "e65b9f8"  # last commit before the 12vhpwr conversion
def _frozen_flat_12vhpwr():
    import subprocess, tempfile
    out = subprocess.run(
        ["git", "show", _FLAT_12VHPWR_REV +
         ":beta/12vhpwr-standard/12vhpwr-standard-module.kicad_sch"],
        capture_output=True, text=True, cwd=ROOT)
    if out.returncode != 0:
        raise unittest.SkipTest("flat 12vhpwr baseline rev unavailable")
    d = tempfile.mkdtemp(prefix="cec_gates_flat12v_")
    p = os.path.join(d, "12vhpwr-standard-module.kicad_sch")
    with open(p, "w") as fh:
        fh.write(out.stdout)
    return p
REAL_12VHPWR = None  # resolved lazily per-test via _frozen_flat_12vhpwr()


def _envelope(body, *, paper='"A4"', extra_footer=""):
    """Minimal but well-formed .kicad_sch text -- same skeleton style as
    tests/test_sch_layout.py's fixtures."""
    return (
        '(kicad_sch (version 20260306) (generator "test")\n'
        f'  (uuid "aaaaaaaa-0000-0000-0000-00000000000{0}")\n'
        f'  (paper {paper})\n'
        f'{body}\n'
        f'{extra_footer}'
        '  (sheet_instances (path "/" (page "1")))\n'
        '  (embedded_fonts no)\n)\n')


def _write(text):
    f = tempfile.NamedTemporaryFile("w", suffix=".kicad_sch", delete=False)
    f.write(text)
    f.close()
    return f.name


# A tiny 1-pin "passive" symbol (rectangle body + one pin) reused by several
# fixtures below, in the same hand-authored style as
# test_sch_layout.DirectionalMisrotTest's _FLAG_LIB. Kept as bare inner
# `(symbol ...)` blocks (no `(lib_symbols ...)` wrapper) so callers that need
# BOTH this part AND another symbol set (e.g. the ladder fixtures, which also
# want a foreign-obstacle part) can concatenate them into ONE lib_symbols
# block -- a real .kicad_sch may have only one such top-level clause.
_MINI_SYMBOL_DEF = """\
    (symbol "test:MINI"
      (pin_numbers (hide yes))
      (pin_names (offset 0) (hide yes))
      (property "Reference" "U" (at 0 0 0) (effects (font (size 1.27 1.27))))
      (property "Value" "MINI" (at 0 0 0) (effects (font (size 1.27 1.27))))
      (symbol "MINI_0_1"
        (rectangle (start -2 -2) (end 2 2)
          (stroke (width 0.254) (type default)) (fill (type none))))
      (symbol "MINI_1_1"
        (pin passive line (at 4 0 180) (length 2)
          (name "P1" (effects (font (size 1.27 1.27))))
          (number "1" (effects (font (size 1.27 1.27))))))
    )
"""

_GND_SYMBOL_DEF = """\
    (symbol "cec-power:GND"
      (power)
      (pin_numbers (hide yes))
      (pin_names (offset 0) (hide yes))
      (property "Reference" "#PWR" (at 0 0 0) (hide yes)
        (effects (font (size 1.27 1.27))))
      (property "Value" "GND" (at 0 3.81 0) (effects (font (size 1.27 1.27))))
      (symbol "GND_0_1"
        (polyline (pts (xy 0 0) (xy 0 1.27) (xy 1.27 1.27) (xy -1.27 1.27) (xy 0 1.27))
          (stroke (width 0) (type default)) (fill (type none))))
      (symbol "GND_1_1"
        (pin power_in line (at 0 0 90) (length 0)
          (name "~" (effects (font (size 1.27 1.27))))
          (number "1" (effects (font (size 1.27 1.27))))))
    )
"""

_MINI_PART_LIB = "  (lib_symbols\n" + _MINI_SYMBOL_DEF + _GND_SYMBOL_DEF + "  )\n"


def _part(ref, x, y, rot=0):
    return (
        '  (symbol\n'
        '    (lib_id "test:MINI")\n'
        f'    (at {x} {y} {rot})\n'
        '    (unit 1)\n'
        '    (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)\n'
        f'    (uuid "{cec_sch.u()}")\n'
        f'    (property "Reference" "{ref}" (at {x} {y - 3} 0)\n'
        '      (effects (font (size 1.27 1.27))))\n'
        f'    (property "Value" "MINI" (at {x} {y + 3} 0)\n'
        '      (effects (font (size 1.27 1.27))))\n'
        f'    (pin "1" (uuid "{cec_sch.u()}"))\n'
        f'    (instances (project "t" (path "/x" (reference "{ref}") (unit 1))))\n'
        '  )\n')


def _gnd_flag(ref_num, x, y):
    return (
        '  (symbol\n'
        '    (lib_id "cec-power:GND")\n'
        f'    (at {x} {y} 0)\n'
        '    (unit 1)\n'
        '    (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)\n'
        f'    (uuid "{cec_sch.u()}")\n'
        f'    (property "Reference" "#PWR{ref_num}" (at {x} {y - 2.5} 0) (hide yes)\n'
        '      (effects (font (size 1.27 1.27))))\n'
        f'    (property "Value" "GND" (at {x} {y + 3.81} 0)\n'
        '      (effects (font (size 1.27 1.27))))\n'
        f'    (pin "1" (uuid "{cec_sch.u()}"))\n'
        f'    (instances (project "t" (path "/x" (reference "#PWR{ref_num}") (unit 1))))\n'
        '  )\n')


def _region(title, x0, y0, x1, y1):
    """Same s-expr shape cec_sch.emit_section / cec_sch_compose.emit_region
    both produce -- a dashed rectangle + a bold title near its top-left."""
    return cec_sch.emit_section(title, x0, y0, x1, y1)


# ============================================================================
# Deliverable 1: check_region_containment
# ============================================================================
class RegionContainmentTest(unittest.TestCase):
    """Synthetic fixture: REGION-A (0,0)-(50,50) and REGION-B (40,10)-(60,60)
    overlap each other (REGION-OVERLAP). U1 sits fully inside A alone
    (clean). U2 sits far outside every region but still on the sheet
    (CONTAINMENT only). U3's extent straddles B's right edge while missing A
    entirely (CONTAINMENT + STRADDLE vs B). REGION-C (300,300)-(350,350) is
    placed on a 220x220 User sheet, so it overruns the paper edge
    (REGION-OVERRUN) without touching A/B/any part."""

    def _bad_fixture(self):
        body = (_MINI_PART_LIB
               + _region("REGION-A", 0, 0, 50, 50)
               + _region("REGION-B", 40, 10, 60, 60)
               + _region("REGION-C", 300, 300, 350, 350)
               + _part("U1", 25, 25)
               + _part("U2", 100, 100)
               + _part("U3", 58, 25))
        return _write(_envelope(body, paper='"User" 220 220'))

    def _clean_fixture(self):
        body = (_MINI_PART_LIB
               + _region("REGION-A", 0, 0, 50, 50)
               + _region("REGION-B", 60, 60, 100, 100)
               + _part("U1", 25, 25)
               + _part("U2", 80, 80))
        return _write(_envelope(body, paper='"User" 220 220'))

    def test_bad_fixture_fires_all_four_classes(self):
        p = self._bad_fixture()
        try:
            findings = G.check_region_containment(p)
            self.assertTrue(findings, "expected real findings on the bad fixture")
            classes = {f.split()[0] for f in findings}
            for want in ("CONTAINMENT", "STRADDLE", "REGION-OVERLAP", "REGION-OVERRUN"):
                self.assertIn(want, classes, findings)
            self.assertTrue(any("U2" in f for f in findings), findings)
            self.assertTrue(any("U3" in f for f in findings), findings)
            self.assertFalse(any(re.match(r'^\w+ U1 ', f) for f in findings), findings)
        finally:
            os.unlink(p)

    def test_clean_fixture_is_silent(self):
        p = self._clean_fixture()
        try:
            self.assertEqual(G.check_region_containment(p), [])
        finally:
            os.unlink(p)

    def test_no_regions_is_exempt(self):
        """A sheet with zero region frames is exempt entirely, even with a
        part sitting nowhere near anything sensible."""
        body = _MINI_PART_LIB + _part("U1", 9000, 9000)
        p = _write(_envelope(body, paper='"A4"'))
        try:
            self.assertEqual(G.check_region_containment(p), [])
        finally:
            os.unlink(p)

    def test_real_12vhpwr_has_measured_findings(self):
        """TEETH: the owner's report that 12vhpwr-standard's regions clip
        each other and overrun the sheet edge must show up as real findings
        -- not a hypothetical, the live board as of round 4."""
        findings = G.check_region_containment(_frozen_flat_12vhpwr())
        classes = {f.split()[0] for f in findings}
        self.assertIn("REGION-OVERLAP", classes, findings)
        self.assertIn("REGION-OVERRUN", classes, findings)
        # measured 2026-07-04: 8 regions, 15 findings (2 CONTAINMENT,
        # 5 STRADDLE, 4 REGION-OVERLAP, 4 REGION-OVERRUN) -- a hard floor,
        # not an exact pin, so a future partial fix doesn't spuriously fail.
        self.assertGreaterEqual(len(findings), 10, findings)


# ============================================================================
# Deliverable 2: check_sheet_bounds
# ============================================================================
class SheetBoundsTest(unittest.TestCase):
    def test_bad_fixture_fires(self):
        """A4 is 297x210mm; U1 sits far outside it, a wire runs off the
        right edge, and a free text note sits below the bottom edge."""
        body = (_MINI_PART_LIB
               + _part("U1", 500, 500)
               + '  (wire (pts (xy 100 100) (xy 400 100))\n'
                 '    (stroke (width 0) (type default)))\n'
               + '  (text "off sheet note" (at 50 400 0)\n'
                 '    (effects (font (size 1.27 1.27))))\n')
        p = _write(_envelope(body, paper='"A4"'))
        try:
            findings = G.check_sheet_bounds(p)
            self.assertTrue(any("U1" in f for f in findings), findings)
            self.assertTrue(any("wire endpoint" in f for f in findings), findings)
            self.assertTrue(any("off sheet note" in f for f in findings), findings)
        finally:
            os.unlink(p)

    def test_clean_fixture_is_silent(self):
        body = (_MINI_PART_LIB
               + _part("U1", 100, 100)
               + '  (wire (pts (xy 100 100) (xy 150 100))\n'
                 '    (stroke (width 0) (type default)))\n'
               + '  (text "on sheet note" (at 50 50 0)\n'
                 '    (effects (font (size 1.27 1.27))))\n')
        p = _write(_envelope(body, paper='"A4"'))
        try:
            self.assertEqual(G.check_sheet_bounds(p), [])
        finally:
            os.unlink(p)

    def test_paper_sizes_and_user_size(self):
        self.assertEqual(G._paper_rect('(paper "A4")')[:4], (0.0, 297.0, 0.0, 210.0))
        self.assertEqual(G._paper_rect('(paper "A3")')[:4], (0.0, 420.0, 0.0, 297.0))
        self.assertEqual(G._paper_rect('(paper "User" 123.4 56.7)')[:4],
                         (0.0, 123.4, 0.0, 56.7))
        # portrait swaps width/height
        self.assertEqual(G._paper_rect('(paper "A4" portrait)')[:4],
                         (0.0, 210.0, 0.0, 297.0))

    def test_real_12vhpwr_has_measured_findings(self):
        """TEETH: measured 2026-07-04 -- 423 findings (66 symbol extents,
        158 text/label glyphs, 199 wire endpoints) fall outside the A3
        sheet on the live board (e.g. J3/J4 sit at y=1391.92mm)."""
        findings = G.check_sheet_bounds(_frozen_flat_12vhpwr())
        self.assertGreaterEqual(len(findings), 300, findings[:5])
        self.assertTrue(any("J3" in f or "J4" in f for f in findings))


# ============================================================================
# Deliverable 3: inventory() / check_inventory_equal()
# ============================================================================
REAL_EPS = os.path.join(ROOT, "beta/eps-8pin-rev3/eps-8pin-rev3.kicad_sch")


class InventoryTest(unittest.TestCase):
    def _synthetic(self, *, dnp=False, drop_prop=False):
        extra = ""
        if not drop_prop:
            extra = '    (property "LCSC" "C123456" (at 0 0 0) (hide yes)\n' \
                    '      (effects (font (size 1.27 1.27))))\n'
        dnp_clause = "yes" if dnp else "no"
        body = (
            _MINI_PART_LIB
            + '  (symbol\n'
              '    (lib_id "test:MINI")\n'
              '    (at 25 25 0)\n'
              '    (unit 1)\n'
              '    (exclude_from_sim no) (in_bom yes) (on_board yes)'
              f' (dnp {dnp_clause})\n'
              f'    (uuid "{cec_sch.u()}")\n'
              '    (property "Reference" "U1" (at 25 22 0)\n'
              '      (effects (font (size 1.27 1.27))))\n'
              '    (property "Value" "MINI" (at 25 28 0)\n'
              '      (effects (font (size 1.27 1.27))))\n'
              f'{extra}'
              f'    (pin "1" (uuid "{cec_sch.u()}"))\n'
              '    (instances (project "t" (path "/x" (reference "U1") (unit 1))))\n'
              '  )\n')
        return _write(_envelope(body))

    @unittest.skipUnless(os.path.isfile(REAL_EPS), "eps-8pin schematic not present")
    def test_real_eps8pin_self_compare_is_equal(self):
        self.assertEqual(G.check_inventory_equal(REAL_EPS, REAL_EPS), [])
        inv = G.inventory(REAL_EPS)
        self.assertGreater(len(inv), 20)

    def test_dnp_flip_detected(self):
        a = self._synthetic(dnp=False)
        b = self._synthetic(dnp=True)
        try:
            findings = G.check_inventory_equal(a, b)
            self.assertTrue(any("U1.dnp" in f for f in findings), findings)
        finally:
            os.unlink(a)
            os.unlink(b)

    def test_dropped_property_detected(self):
        a = self._synthetic(drop_prop=False)
        b = self._synthetic(drop_prop=True)
        try:
            findings = G.check_inventory_equal(a, b)
            self.assertTrue(any("LCSC" in f and "dropped" in f for f in findings),
                            findings)
        finally:
            os.unlink(a)
            os.unlink(b)

    def test_missing_and_extra_ref(self):
        a_body = _MINI_PART_LIB + _part("U1", 25, 25) + _part("U2", 60, 25)
        b_body = _MINI_PART_LIB + _part("U1", 25, 25)
        a = _write(_envelope(a_body))
        b = _write(_envelope(b_body))
        try:
            findings = G.check_inventory_equal(a, b)
            self.assertTrue(any(f.startswith("MISSING U2") for f in findings), findings)
        finally:
            os.unlink(a)
            os.unlink(b)


# ============================================================================
# Deliverable 4: check_prose_preserved
# ============================================================================
class ProsePreservedTest(unittest.TestCase):
    def _sch_with_texts(self, *texts):
        body = _MINI_PART_LIB
        for i, t in enumerate(texts):
            esc = t.replace('"', '\\"')
            body += f'  (text "{esc}" (at {i * 10} {i * 10} 0)\n' \
                    '    (effects (font (size 1.27 1.27))))\n'
        return _write(_envelope(body))

    def test_all_preserved_is_silent(self):
        base = self._sch_with_texts("note one", "note   two")
        new = self._sch_with_texts("note one", "note two")   # ws-normalized match
        try:
            self.assertEqual(G.check_prose_preserved([base], [new]), [])
        finally:
            os.unlink(base)
            os.unlink(new)

    def test_dropped_prose_detected(self):
        base = self._sch_with_texts("keep this", "drop this one")
        new = self._sch_with_texts("keep this")
        try:
            missing = G.check_prose_preserved([base], [new])
            self.assertEqual(missing, ["drop this one"])
        finally:
            os.unlink(base)
            os.unlink(new)

    def test_waiver_suppresses(self):
        base = self._sch_with_texts("keep this", "drop this one")
        new = self._sch_with_texts("keep this")
        try:
            missing = G.check_prose_preserved([base], [new],
                                              waivers=["drop this one"])
            self.assertEqual(missing, [])
        finally:
            os.unlink(base)
            os.unlink(new)

    def test_baseline_and_new_can_span_multiple_files(self):
        base1 = self._sch_with_texts("from file one")
        base2 = self._sch_with_texts("from file two")
        new1 = self._sch_with_texts("from file one")
        new2 = self._sch_with_texts("from file two")
        try:
            self.assertEqual(
                G.check_prose_preserved([base1, base2], [new1, new2]), [])
        finally:
            for p in (base1, base2, new1, new2):
                os.unlink(p)


# ============================================================================
# Deliverable 5: cec_sch_layout.power_ladder_runs + cec_sch_gates.bus_power_ladder
# ============================================================================
def _ladder_lib(ic_name, n, pitch=2.54, *, with_mini=False):
    """A symbol with `n` GND-named pins in a vertical run (local x=10, y =
    -i*pitch, ang=180 so they read outward to +x at rot=0) -- the un-bused
    ladder shape, plus the same minimal cec-power:GND symbol used elsewhere
    in this file. `with_mini=True` also embeds test:MINI's definition in the
    SAME lib_symbols block (needed whenever a fixture also places a MINI
    part, e.g. the corridor-obstacle test -- a .kicad_sch has only one
    top-level lib_symbols clause)."""
    pins = "\n".join(
        f'        (pin passive line (at 10 {-i * pitch} 180) (length 2)\n'
        f'          (name "GND" (effects (font (size 1.27 1.27))))\n'
        f'          (number "{i + 1}" (effects (font (size 1.27 1.27)))))'
        for i in range(n))
    ic_def = f'''    (symbol "test:{ic_name}"
      (pin_numbers (hide yes))
      (pin_names (offset 0) (hide yes))
      (property "Reference" "U" (at 0 0 0) (effects (font (size 1.27 1.27))))
      (property "Value" "{ic_name}" (at 0 0 0) (effects (font (size 1.27 1.27))))
      (symbol "{ic_name}_0_1"
        (rectangle (start -2 2) (end 8 {-(n * pitch) - 2})
          (stroke (width 0.254) (type default)) (fill (type none))))
      (symbol "{ic_name}_1_1"
{pins}
      )
    )
'''
    mini_def = _MINI_SYMBOL_DEF if with_mini else ""
    return "  (lib_symbols\n" + ic_def + mini_def + _GND_SYMBOL_DEF + "  )\n"


def _build_ladder_sch(n, *, pitch=2.54, stub_len=3.81, ox=100.0, oy=100.0,
                      obstacle=False):
    """A ladder IC (U1, `n` GND pins) each with its own private stub+flag --
    the shape power_ladder_runs()/bus_power_ladder() consume. `obstacle=True`
    drops a foreign MINI part's body directly across the chain's corridor
    (between pins 2 and 3), for the corridor-blocked refusal test."""
    body = _ladder_lib("LADDER", n, pitch, with_mini=obstacle)
    body += (
        '  (symbol\n'
        '    (lib_id "test:LADDER")\n'
        f'    (at {ox} {oy} 0)\n'
        '    (unit 1)\n'
        '    (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)\n'
        f'    (uuid "{cec_sch.u()}")\n'
        f'    (property "Reference" "U1" (at {ox} {oy - 3} 0)\n'
        '      (effects (font (size 1.27 1.27))))\n'
        f'    (property "Value" "LADDER" (at {ox} {oy + 3} 0)\n'
        '      (effects (font (size 1.27 1.27))))\n'
        + "".join(f'    (pin "{i + 1}" (uuid "{cec_sch.u()}"))\n' for i in range(n))
        + '    (instances (project "t" (path "/x" (reference "U1") (unit 1))))\n'
          '  )\n')
    for i in range(n):
        px, py = ox + 10, oy + i * pitch
        fx, fy = px + stub_len, py
        body += (f'  (wire (pts (xy {px} {py}) (xy {fx} {fy}))\n'
                 '    (stroke (width 0) (type default)))\n')
        body += (
            '  (symbol\n'
            '    (lib_id "cec-power:GND")\n'
            f'    (at {fx} {fy} 0)\n'
            '    (unit 1)\n'
            '    (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)\n'
            f'    (uuid "{cec_sch.u()}")\n'
            f'    (property "Reference" "#PWR{i + 1}" (at {fx} {fy - 2.5} 0) (hide yes)\n'
            '      (effects (font (size 1.27 1.27))))\n'
            f'    (property "Value" "GND" (at {fx} {fy + 3.81} 0)\n'
            '      (effects (font (size 1.27 1.27))))\n'
            f'    (pin "1" (uuid "{cec_sch.u()}"))\n'
            f'    (instances (project "t" (path "/x" (reference "#PWR{i + 1}") (unit 1))))\n'
            '  )\n')
    if obstacle and n >= 3:
        # a foreign body straddling the pin1-pin2 leg of the chain corridor
        blockx, blocky = ox + 10, oy + 1.5 * pitch
        body += _part("UBLOCK", blockx, blocky)
    return _write(_envelope(body))


class PowerLadderRunsTest(unittest.TestCase):
    def test_finds_uniform_run(self):
        p = _build_ladder_sch(4)
        try:
            runs = L.power_ladder_runs(p, "U1", "GND")
            self.assertEqual(len(runs), 1)
            self.assertEqual(runs[0]["pins"], ["1", "2", "3", "4"])
            self.assertAlmostEqual(runs[0]["pitch"], 2.54, places=2)
        finally:
            os.unlink(p)

    def test_below_min_run_finds_nothing(self):
        p = _build_ladder_sch(2)
        try:
            self.assertEqual(L.power_ladder_runs(p, "U1", "GND"), [])
        finally:
            os.unlink(p)

    def test_accepts_raw_text_or_path(self):
        p = _build_ladder_sch(3)
        try:
            from_path = L.power_ladder_runs(p, "U1", "GND")
            from_text = L.power_ladder_runs(open(p).read(), "U1", "GND")
            self.assertEqual(from_path, from_text)
        finally:
            os.unlink(p)

    def test_unknown_ref_returns_empty(self):
        p = _build_ladder_sch(4)
        try:
            self.assertEqual(L.power_ladder_runs(p, "NOPE", "GND"), [])
        finally:
            os.unlink(p)


class BusPowerLadderTest(unittest.TestCase):
    def test_no_run_returns_unapplied(self):
        p = _build_ladder_sch(2)
        before = open(p).read()
        try:
            report = G.bus_power_ladder(p, "U1", "GND")
            self.assertFalse(report["applied"])
            self.assertEqual(open(p).read(), before)
        finally:
            os.unlink(p)

    def test_corridor_blocked_refuses_without_touching_file(self):
        p = _build_ladder_sch(4, obstacle=True)
        before = open(p).read()
        try:
            report = G.bus_power_ladder(p, "U1", "GND")
            self.assertFalse(report["applied"])
            self.assertTrue(report["refused"])
            self.assertIn("corridor blocked", report["refused"][0]["reason"])
            self.assertEqual(open(p).read(), before, "refusal must not touch the file")
        finally:
            os.unlink(p)

    def test_collapses_to_one_flag_and_chain_wire(self):
        p = _build_ladder_sch(5)
        try:
            report = G.bus_power_ladder(p, "U1", "GND")
            self.assertTrue(report["applied"], report)
            self.assertEqual(report["flags_removed"], 4)
            text = open(p).read()
            # exactly one kept flag INSTANCE remains (its lib_id reference)
            self.assertEqual(text.count('(lib_id "cec-power:GND")'), 1)
            # ...and its ref appears twice (Reference property + instances path)
            self.assertEqual(len(re.findall(r'#PWR\d+', text)), 2)
            self.assertEqual(L.power_ladder_runs(p, "U1", "GND"), [],
                             "the ladder must no longer be un-bused")
        finally:
            os.unlink(p)

    @unittest.skipUnless(HAVE_KICAD_CLI, "kicad-cli not on PATH")
    def test_netlist_identical_and_erc_not_worse(self):
        """The real ground-truth gate: kicad-cli's own netlist connectivity
        (name-aware) must be byte-for-byte the same group set before/after,
        and the ERC error count must not increase."""
        p = _build_ladder_sch(4)
        before_path = p[:-len(".kicad_sch")] + "-before.kicad_sch"
        import shutil
        shutil.copy(p, before_path)
        try:
            report = G.bus_power_ladder(p, "U1", "GND")
            self.assertTrue(report["applied"], report)

            def groups(path):
                out = path + ".net"
                subprocess.run(["kicad-cli", "sch", "export", "netlist",
                               "-o", out, path], capture_output=True, text=True)
                txt = open(out).read()
                g = {}
                for m in re.finditer(r'\(net\s+\(code', txt):
                    d, i = 0, m.start()
                    while True:
                        c = txt[i]
                        if c == '(':
                            d += 1
                        elif c == ')':
                            d -= 1
                            if d == 0:
                                break
                        i += 1
                    blk = txt[m.start():i + 1]
                    nm = re.search(r'\(name "([^"]*)"\)', blk)
                    mem = frozenset(re.findall(
                        r'\(ref "([^"]+)"\)\s*\(pin "([^"]+)"\)', blk))
                    if mem:
                        g[mem] = nm.group(1) if nm else "?"
                os.unlink(out)
                return g

            a, b = groups(before_path), groups(p)
            self.assertEqual(set(a), set(b))
            self.assertFalse([k for k in a if a[k] != b[k]], "no renames expected")

            def erc_errors(path):
                out = path + ".erc.json"
                subprocess.run(["kicad-cli", "sch", "erc", "--format", "json",
                               "-o", out, path], capture_output=True, text=True)
                import json
                d = json.load(open(out))
                n = sum(1 for sh in d.get("sheets", [])
                       for v in sh.get("violations", [])
                       if v.get("severity") == "error")
                os.unlink(out)
                return n

            self.assertLessEqual(erc_errors(p), erc_errors(before_path))
        finally:
            os.unlink(p)
            os.unlink(before_path)


class RealBoardLadderSanityTest(unittest.TestCase):
    """Lightweight regression pins for the round-4 apply step: hub-standard's
    WROOM-1 GND pins are coincident at one point (already a single stamp --
    nothing to bus), so bus_power_ladder must be a documented no-op there;
    24pin-rev3's U1 ladder was applied for real and must show no residual
    un-bused run."""
    HUB = os.path.join(ROOT, "beta/hub-standard-rev2/03-mcu-usb.kicad_sch")
    PIN24 = os.path.join(ROOT, "beta/atx-24pin-rev3/03-regulator-mcu.kicad_sch")

    @unittest.skipUnless(os.path.isfile(HUB), "hub-standard schematic not present")
    def test_hub_standard_u1_has_no_ladder(self):
        self.assertEqual(L.power_ladder_runs(self.HUB, "U1", "GND"), [])

    @unittest.skipUnless(os.path.isfile(PIN24), "24pin-rev3 schematic not present")
    def test_24pin_u1_ladder_already_bused(self):
        """The real board was mutated by this round; confirm no un-bused
        run remains (a regression pin, not a fresh finding)."""
        self.assertEqual(L.power_ladder_runs(self.PIN24, "U1", "GND"), [])
