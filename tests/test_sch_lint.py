#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Teeth for scripts/cec_sch_lint.py (T3, docs/schematic-quality-charter.md
# principle 2: "a checker is trusted only after it demonstrably FAILS on a
# real bad example"). Each fixture below is a small, hand-built, VALID
# .kicad_sch (stdlib only, no pcbnew needed -- this tool never touches
# pcbnew) constructed from the same primitives the real generators use
# (cec_sch.emit_wire/emit_symbol/emit_global_power, cec_sch_layout's
# emit_junction/emit_noconnect), so the fixtures exercise the real KiCad 10
# s-expr grammar, not a simplified stand-in.
#
#   python3 -m unittest tests.test_sch_lint -v
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import cec_sch                  # noqa: E402
import cec_sch_layout as csl    # noqa: E402
import cec_sch_lint as L        # noqa: E402

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# A minimal, self-contained 2-pin passive, geometry copied verbatim from the
# real lib/vendor/cec-vendor.kicad_sym R_Small (pin1 (0,2.54,270), pin2
# (0,-2.54,90)) so the fixtures use REAL, already-validated pin math rather
# than inventing new numbers.
_R2_LIB = '''(symbol "test:R2"
\t(pin_names (offset 0.254) (hide yes))
\t(exclude_from_sim no) (in_bom yes) (on_board yes)
\t(property "Reference" "R" (at 0 0 90) (effects (font (size 1.016 1.016))))
\t(property "Value" "R2" (at 1.778 0 90) (effects (font (size 1.27 1.27))))
\t(property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
\t(property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
\t(symbol "R2_0_1"
\t\t(rectangle (start -0.762 1.778) (end 0.762 -1.778)
\t\t\t(stroke (width 0.2032) (type default)) (fill (type none)))
\t)
\t(symbol "R2_1_1"
\t\t(pin passive line (at 0 2.54 270) (length 0.762)
\t\t\t(name "~" (effects (font (size 1.27 1.27))))
\t\t\t(number "1" (effects (font (size 1.27 1.27)))))
\t\t(pin passive line (at 0 -2.54 90) (length 0.762)
\t\t\t(name "~" (effects (font (size 1.27 1.27))))
\t\t\t(number "2" (effects (font (size 1.27 1.27)))))
\t)
)'''


def _power_lib_text():
    return open(os.path.join(_ROOT, "lib", "vendor", "cec-power.kicad_sym")).read()


def build_sch(path, project, lib_blocks, body_lines, paper="A4"):
    """Assemble a minimal valid .kicad_sch: header + lib_symbols(lib_blocks)
    + body_lines (already-rendered element strings) + sheet_instances."""
    root = cec_sch.u()
    content = (
        "(kicad_sch\n\t(version 20260306)\n\t(generator \"eeschema\")\n"
        "\t(generator_version \"10.0\")\n"
        f"\t(uuid \"{root}\")\n\t(paper \"{paper}\")\n"
        "\t(lib_symbols\n" + "\n".join(lib_blocks) + "\n\t)\n"
        + "\n".join(body_lines) + "\n"
        "\t(sheet_instances\n\t\t(path \"/\"\n\t\t\t(page \"1\")\n\t\t)\n\t)\n"
        "\t(embedded_fonts no)\n)\n")
    open(path, "w").write(content)
    return root


class OffGridEndpoint(unittest.TestCase):
    def test_off_grid_wire_endpoint_fires_sl01(self):
        """A wire endpoint at x=100.005 (not a multiple of 1.27mm) must fire
        SL-01, and -- since both ends terminate on a same-named label -- must
        NOT also fire SL-03 (dangling): this isolates the grid check."""
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "off_grid.kicad_sch")
            project = "off_grid"
            body = [
                cec_sch.emit_wire(0, 0, 100.005, 0),
                cec_sch.emit_label("NET1", 0, 0, 180),
                cec_sch.emit_label("NET1", 100.005, 0, 0),
            ]
            build_sch(path, project, [], body)
            sf = L.SchFile(path)
            findings, _metrics = L.lint_file(sf)
            ids = [f["id"] for f in findings]
            self.assertIn("SL-01", ids, f"expected SL-01 to fire; got {ids}")
            self.assertNotIn("SL-03", ids, f"off-grid-but-labeled ends must not read as dangling; got {ids}")


class FourWayJunction(unittest.TestCase):
    def test_four_way_junction_fires_sl02(self):
        """A junction with wires departing N/E/S/W (a true '+' cross) fires
        SL-02; each spoke's far end is labeled so nothing dangles."""
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "four_way.kicad_sch")
            cx, cy = 50.8, 50.8
            body = [
                cec_sch.emit_wire(cx, cy, cx, cy - 12.7),   # north
                cec_sch.emit_wire(cx, cy, cx, cy + 12.7),   # south
                cec_sch.emit_wire(cx, cy, cx + 12.7, cy),   # east
                cec_sch.emit_wire(cx, cy, cx - 12.7, cy),   # west
                csl.emit_junction(cx, cy),
                cec_sch.emit_label("N", cx, cy - 12.7, 90),
                cec_sch.emit_label("S", cx, cy + 12.7, 90),
                cec_sch.emit_label("E", cx + 12.7, cy, 0),
                cec_sch.emit_label("W", cx - 12.7, cy, 180),
            ]
            build_sch(path, "four_way", [], body)
            sf = L.SchFile(path)
            findings, _metrics = L.lint_file(sf)
            ids = [f["id"] for f in findings]
            self.assertIn("SL-02", ids, f"expected SL-02 (four-way junction) to fire; got {ids}")


class DanglingWire(unittest.TestCase):
    def test_dangling_wire_end_fires_sl03(self):
        """A wire with both ends touching NOTHING (no pin/label/junction/other
        wire) must fire SL-03 at (at least) one end."""
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "dangling.kicad_sch")
            body = [cec_sch.emit_wire(0, 0, 25.4, 0)]
            build_sch(path, "dangling", [], body)
            sf = L.SchFile(path)
            findings, _metrics = L.lint_file(sf)
            ids = [f["id"] for f in findings]
            self.assertIn("SL-03", ids, f"expected SL-03 (dangling wire end) to fire; got {ids}")
            # both ends are genuinely isolated here
            self.assertEqual(ids.count("SL-03"), 2)


class CleanMiniSheet(unittest.TestCase):
    def test_clean_sheet_has_zero_errors(self):
        """A small, deliberately well-formed circuit -- one on-grid part, a
        top-pin stub to a properly-oriented label, a bottom-pin stub to a
        GND port + an adjacent PWR_FLAG -- must report ZERO ERROR-severity
        findings (SL-01/SL-03). This is the 'generated == hand-authored'
        floor T3 measures against."""
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "clean.kicad_sch")
            project = "clean"
            root = cec_sch.u()
            libs = {"power": _power_lib_text()}
            gnd_block = cec_sch._power_block(libs, "GND")
            flag_block = cec_sch._power_block(libs, "PWR_FLAG")

            rx, ry = 63.5, 50.8          # symbol origin, on-grid
            pin1 = (rx, ry - 2.54)        # top pin (outward = further up)
            pin2 = (rx, ry + 2.54)        # bottom pin (outward = further down)
            stub_top = (rx, pin1[1] - 3.81)
            stub_bot = (rx, pin2[1] + 3.81)

            body = [
                cec_sch.emit_symbol("R1", "test", "R2", "100", rx, ry, ["1", "2"], project, root),
                cec_sch.emit_wire(pin1[0], pin1[1], stub_top[0], stub_top[1]),
                cec_sch.emit_label("RAIL", stub_top[0], stub_top[1], 90),
                cec_sch.emit_wire(pin2[0], pin2[1], stub_bot[0], stub_bot[1]),
                cec_sch.emit_global_power("GND", stub_bot[0], stub_bot[1], project, root, "#PWR01", 0),
                cec_sch.emit_global_power("PWR_FLAG", stub_bot[0], stub_bot[1], project, root, "#FLG01", 0),
            ]
            content = (
                "(kicad_sch\n\t(version 20260306)\n\t(generator \"eeschema\")\n"
                "\t(generator_version \"10.0\")\n"
                f"\t(uuid \"{root}\")\n\t(paper \"A4\")\n"
                f"{cec_sch.lib_symbols_section({}, [_R2_LIB, gnd_block, flag_block])}\n"
                + "\n".join(body) + "\n"
                "\t(sheet_instances\n\t\t(path \"/\"\n\t\t\t(page \"1\")\n\t\t)\n\t)\n"
                "\t(embedded_fonts no)\n)\n")
            open(path, "w").write(content)

            sf = L.SchFile(path)
            findings, metrics = L.lint_file(sf)
            errors = [f for f in findings if f["severity"] == "ERROR"]
            self.assertEqual(errors, [], f"expected zero ERROR findings on a clean sheet; got {errors}")


if __name__ == "__main__":
    unittest.main()
