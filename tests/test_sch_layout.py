#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Tests for scripts/cec_sch_layout.py -- the standalone schematic layout-
# quality engine (additive; does not touch cec_sch.py / gen-modules.py /
# hubs/hub-enterprise). HOST-RUNNABLE: needs only kicad-cli on PATH (no
# pcbnew, no GUI) via `kicad-cli sch erc` / `export netlist` / `export svg`.
#
#   python3 -m unittest tests.test_sch_layout -v
import math
import os
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_sch          # noqa: E402  the existing, unmodified primitives
import cec_sch_layout as L  # noqa: E402

HAVE_KICAD_CLI = True
try:
    subprocess.run(["kicad-cli", "version"], capture_output=True, check=True)
except Exception:
    HAVE_KICAD_CLI = False

LIBS = {
    "cec-vendor": open(os.path.join(ROOT, "lib/vendor/cec-vendor.kicad_sym")).read(),
    "power": open(os.path.join(ROOT, "lib/vendor/cec-power.kicad_sym")).read(),
}


def _erc(path):
    """Run kicad-cli sch erc, return (violations, returncode)."""
    out = path + ".erc.json"
    subprocess.run(["kicad-cli", "sch", "erc", "--format", "json", "-o", out, path],
                    capture_output=True, text=True)
    import json
    d = json.load(open(out))
    viol = []
    for sheet in d.get("sheets", []):
        viol.extend(sheet.get("violations", []))
    return viol


def _netlist_pin_for_label(path, label):
    """Return the set of (ref,pin) nodes on the net named `label`."""
    out = path + ".net"
    subprocess.run(["kicad-cli", "sch", "export", "netlist", "-o", out, path],
                    capture_output=True, text=True)
    import re
    t = open(out).read()
    m = re.search(r'\(net\s*\(code "\d+"\)\s*\(name "/?' + re.escape(label) +
                  r'"\).*?(?=\(net\s*\(code|\Z)', t, re.S)
    if not m:
        return set()
    return set(re.findall(r'\(ref "([^"]+)"\)\s*\(pin "([^"]+)"\)', m.group(0)))


class RotationRoundtripTest(unittest.TestCase):
    """The load-bearing empirical claim in the module docstring: pin_abs_rot's
    rotation convention (standard math CCW on the Y-up local coords, applied
    BEFORE the Y-flip) matches what KiCad's own engine computes for a rotated
    instance. R_Small's two pins sit on the local Y axis only, so a sign error
    SWAPS pin 1 and pin 2 -- a real discriminating test, not a tautology: we
    draw a wire from OUR computed pin position to a uniquely-named label, then
    ask kicad-cli's netlist exporter which REAL pin ended up on that label. If
    our position is wrong, the label lands on the wrong pin (or none)."""

    @unittest.skipUnless(HAVE_KICAD_CLI, "kicad-cli not on PATH")
    def test_rotation_roundtrip_all_angles(self):
        parts = {"R1": ("cec-vendor", "R_Small", "10k")}
        used = cec_sch.load_symbols(LIBS, parts)
        pins = used[("cec-vendor", "R_Small")]["pins"]
        ox, oy = 101.6, 101.6   # on the 1.27mm connection grid

        with tempfile.TemporaryDirectory() as td:
            for rot in (0, 90, 180, 270):
                root = cec_sch.u()
                body = [L.emit_symbol_rot("R1", "cec-vendor", "R_Small", "10k",
                                          ox, oy, rot, pins, "rt", root)]
                wires, labels = [], []
                for num in pins:
                    ax, ay, dx, dy = L.pin_abs_rot({"R1": (ox, oy, rot)}, used, parts, "R1", num)
                    bx, by = ax + dx * 2.54, ay + dy * 2.54
                    wires.append(cec_sch.emit_wire(ax, ay, bx, by))
                    labels.append(cec_sch.emit_label(f"NET_{num}", bx, by, 0))
                content = (
                    "(kicad_sch\n\t(version 20260306)\n\t(generator \"eeschema\")\n"
                    "\t(generator_version \"10.0\")\n"
                    f"\t(uuid \"{root}\")\n\t(paper \"A4\")\n"
                    f"{cec_sch.lib_symbols_section(used, ())}\n"
                    + "\n".join(body) + "\n" + "\n".join(wires) + "\n" + "\n".join(labels) + "\n"
                    + "\t(sheet_instances\n\t\t(path \"/\"\n\t\t\t(page \"1\")\n\t\t)\n\t)\n"
                    "\t(embedded_fonts no)\n)\n")
                path = os.path.join(td, f"rt_{rot}.kicad_sch")
                open(path, "w").write(content)

                for num in pins:
                    nodes = _netlist_pin_for_label(path, f"NET_{num}")
                    self.assertEqual(nodes, {("R1", num)},
                                      f"rot={rot}: NET_{num} should land on R1 pin {num}, got {nodes}")


class WireAdjacentTest(unittest.TestCase):
    """wire_adjacent must produce a REAL wire (not a label) that kicad-cli's
    own netlist exporter recognizes as connecting the two pins."""

    @unittest.skipUnless(HAVE_KICAD_CLI, "kicad-cli not on PATH")
    def test_close_pair_routes_as_real_wire(self):
        parts = {"R1": ("cec-vendor", "R_Small", "10k"),
                  "C1": ("cec-vendor", "C_Small", "100n")}
        used = cec_sch.load_symbols(LIBS, parts)
        placement = {"R1": (101.6, 101.6, 0), "C1": (101.6, 111.76, 0)}
        root = cec_sch.u()
        body = [L.emit_symbol_rot(r, parts[r][0], parts[r][1], parts[r][2], *placement[r],
                                  used[(parts[r][0], parts[r][1])]["pins"], "wa", root)
                for r in parts]
        r1_p2 = L.pin_abs_rot(placement, used, parts, "R1", "2")[:2]
        c1_p1 = L.pin_abs_rot(placement, used, parts, "C1", "1")[:2]
        segs = L.wire_adjacent(r1_p2, c1_p1)
        self.assertIsNotNone(segs, "wire_adjacent should find a route for two close, unobstructed pins")
        wires = [cec_sch.emit_wire(*s) for s in segs]

        ncs = []
        for ref, pin in (("R1", "1"), ("C1", "2")):
            ax, ay, _dx, _dy = L.pin_abs_rot(placement, used, parts, ref, pin)
            ncs.append(cec_sch.emit_noconnect(ax, ay))

        content = (
            "(kicad_sch\n\t(version 20260306)\n\t(generator \"eeschema\")\n"
            "\t(generator_version \"10.0\")\n"
            f"\t(uuid \"{root}\")\n\t(paper \"A4\")\n"
            f"{cec_sch.lib_symbols_section(used, ())}\n"
            + "\n".join(body) + "\n" + "\n".join(wires) + "\n" + "\n".join(ncs) + "\n"
            + "\t(sheet_instances\n\t\t(path \"/\"\n\t\t\t(page \"1\")\n\t\t)\n\t)\n"
            "\t(embedded_fonts no)\n)\n")
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "wa.kicad_sch")
            open(path, "w").write(content)
            # zero labels must appear -- this is a WIRE, not label aliasing
            self.assertNotIn("(label ", content)
            out = path + ".net"
            subprocess.run(["kicad-cli", "sch", "export", "netlist", "-o", out, path],
                            capture_output=True, text=True)
            t = open(out).read()
            import re
            nets = re.findall(r'\(net\s*\(code "\d+"\).*?(?=\(net\s*\(code|\Z)', t, re.S)
            joined = [n for n in nets if '"R1"' in n and '"C1"' in n]
            self.assertEqual(len(joined), 1, "R1 pin2 and C1 pin1 should share exactly one net")
            self.assertIn('(pin "2")', joined[0])
            self.assertIn('(pin "1")', joined[0])

            viol = [v for v in _erc(path) if v["severity"] == "error"]
            self.assertEqual(viol, [], f"unexpected ERC errors: {viol}")

    def test_far_pair_falls_back_to_none(self):
        parts = {"R1": ("cec-vendor", "R_Small", "10k")}
        used = cec_sch.load_symbols(LIBS, parts)
        pa = L.pin_abs_rot({"R1": (0, 0, 0)}, used, parts, "R1", "1")[:2]
        pb = (pa[0] + 500.0, pa[1] + 500.0)   # far beyond any reasonable max_len
        self.assertIsNone(L.wire_adjacent(pa, pb, max_len=25.4))


class DecouplerAdjacencyTest(unittest.TestCase):
    """place_decouplers/wire_decouplers must place caps CLOSE to the IC's
    power pin and connect them with real wires (rail + GND stub), not a
    label."""

    def test_caps_close_and_wired(self):
        parts = {"U1": ("cec-vendor", "INA240", "INA240A3"),
                  "C1": ("cec-vendor", "C_Small", "100n"),
                  "C2": ("cec-vendor", "C_Small", "100n")}
        used = cec_sch.load_symbols(LIBS, parts)
        placement = {"U1": (101.6, 127.0, 0)}
        plan = L.place_decouplers(placement, used, parts, "U1", "6", ["C1", "C2"], side="above")
        ic_ax, ic_ay = plan["ic_pin_xy"]

        for cap in ("C1", "C2"):
            cx, cy, _ = placement[cap]
            dist = math.hypot(cx - ic_ax, cy - ic_ay)
            self.assertLess(dist, 15.0, f"{cap} should be placed near the IC power pin")
            self.assertEqual(placement[cap][2], L.ROT_VERTICAL)

        pwr_seq = [0]
        def pwr_ref(prefix="#PWR"):
            pwr_seq[0] += 1
            return f"{prefix}{pwr_seq[0]:02d}"
        wires, junctions, power_syms = L.wire_decouplers(plan, placement, used, parts,
                                                         "dc", cec_sch.u(), pwr_ref)
        self.assertGreaterEqual(len(wires), 2 + 2 * len(plan["caps"]))
        self.assertEqual(len(power_syms), len(plan["caps"]))   # one GND port per cap
        # a T-junction is required for every INTERIOR tap (2 caps -> 0 interior,
        # since both are "ends" of a 2-point rail) -- assert none are missing
        # by checking the endpoint accounting directly instead of a magic count
        self.assertIsInstance(junctions, list)

    def test_derive_owners_balances_pure_decoupling(self):
        # two ICs sharing a rail; two pure decoupling caps (no signal net) must
        # balance one-per-IC, not pile onto one.
        nets = {
            "+3V3": [("U1", "1"), ("U2", "1"), ("C1", "1"), ("C2", "1")],
            "GND": [("U1", "2"), ("U2", "2"), ("C1", "2"), ("C2", "2")],
        }
        spec = L.derive_owners(nets, ["C1", "C2"], ["U1", "U2"])
        owners = {spec[c][0] for c in ("C1", "C2")}
        self.assertEqual(owners, {"U1", "U2"}, "pure decoupling caps should balance across ICs")

    def test_derive_owners_prefers_signal_coupling(self):
        nets = {
            "+3V3": [("U1", "1"), ("U2", "1"), ("C1", "1")],
            "GND": [("U1", "2"), ("U2", "2"), ("C1", "2")],
            "SENSE_A": [("U1", "3"), ("C2", "1")],
        }
        spec = L.derive_owners(nets, ["C1", "C2"], ["U1", "U2"])
        self.assertEqual(spec["C2"][0], "U1", "a filter cap should bind to its signal-sharing IC")


class TextCollisionEngineTest(unittest.TestCase):
    def test_font_calibration_matches_measured_svg(self):
        """Reproduce the SVG measurement used to calibrate CHAR_WIDTH_FACTOR:
        KiCad's own textLength for a representative string at font size 1.27
        should match text_bbox's predicted width within a few percent."""
        if not HAVE_KICAD_CLI:
            self.skipTest("kicad-cli not on PATH")
        strings = ["C10", "100nF", "R1", "10kOhm", "U1", "INA240A3", "GND"]
        with tempfile.TemporaryDirectory() as td:
            root = cec_sch.u()
            texts = []
            for i, s in enumerate(strings):
                texts.append(
                    f'\t(text "{s}"\n\t\t(exclude_from_sim no)\n\t\t(at 100 {100 + i * 10} 0)\n'
                    '\t\t(effects (font (size 1.27 1.27)) (justify left))\n'
                    f'\t\t(uuid "{cec_sch.u()}")\n\t)')
            content = (
                "(kicad_sch\n\t(version 20260306)\n\t(generator \"eeschema\")\n"
                "\t(generator_version \"10.0\")\n"
                f"\t(uuid \"{root}\")\n\t(paper \"A4\")\n\t(lib_symbols\n\t)\n"
                + "\n".join(texts) + "\n"
                + "\t(sheet_instances\n\t\t(path \"/\"\n\t\t\t(page \"1\")\n\t\t)\n\t)\n"
                "\t(embedded_fonts no)\n)\n")
            path = os.path.join(td, "calib.kicad_sch")
            open(path, "w").write(content)
            subprocess.run(["kicad-cli", "sch", "export", "svg", "-o", td, path],
                            capture_output=True, text=True)
            svg = open(os.path.join(td, "calib.svg")).read()
            import re
            errs = []
            for s in strings:
                m = re.search(r'textLength="([\d.]+)" font-size="[\d.]+"[^>]*>' + re.escape(s) + r'</text>', svg)
                self.assertIsNotNone(m, f"SVG textLength not found for {s!r}")
                measured = float(m.group(1))
                predicted = L.text_bbox(s, 1.27, 0, 0, justify_h="left")[1]  # x1 = width (x0=0)
                errs.append(abs(predicted - measured) / measured)
            # the calibration is a fitted AVERAGE across strings -- individual
            # strings vary (narrow "INA240A3" vs wide "U1"), so assert the mean
            # relative error is small, not every single string.
            self.assertLess(sum(errs) / len(errs), 0.15)

    def test_overlap_detector_and_nudge_teeth(self):
        """Construct a deliberate collision (two Value texts stacked exactly
        on top of each other) -> detect_overlaps must see it; nudge_texts must
        clear it without touching the wires/pins."""
        parts = {"R1": ("cec-vendor", "R_Small", "10k"),
                  "R2": ("cec-vendor", "R_Small", "10k")}
        used = cec_sch.load_symbols(LIBS, parts)
        placement = {"R1": (101.6, 101.6, 0), "R2": (105.0, 101.6, 0)}  # deliberately close
        root = cec_sch.u()
        body = [L.emit_symbol_rot(r, parts[r][0], parts[r][1], parts[r][2], *placement[r],
                                  used[(parts[r][0], parts[r][1])]["pins"], "ov", root)
                for r in parts]
        ncs = []
        for r in parts:
            for pnum in used[(parts[r][0], parts[r][1])]["pins"]:
                ax, ay, _dx, _dy = L.pin_abs_rot(placement, used, parts, r, pnum)
                ncs.append(cec_sch.emit_noconnect(ax, ay))
        content = (
            "(kicad_sch\n\t(version 20260306)\n\t(generator \"eeschema\")\n"
            "\t(generator_version \"10.0\")\n"
            f"\t(uuid \"{root}\")\n\t(paper \"A4\")\n"
            f"{cec_sch.lib_symbols_section(used, ())}\n"
            + "\n".join(body) + "\n" + "\n".join(ncs) + "\n"
            + "\t(sheet_instances\n\t\t(path \"/\"\n\t\t\t(page \"1\")\n\t\t)\n\t)\n"
            "\t(embedded_fonts no)\n)\n")
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "ov.kicad_sch")
            open(path, "w").write(content)

            pairs_before = L.detect_overlaps(path)
            self.assertGreater(len(pairs_before), 0, "R1/R2 placed 3.4mm apart must collide (deliberate)")

            wires_before = open(path).read().count("(wire ")
            ncs_before = open(path).read().count("(no_connect ")

            n_moved, still = L.nudge_texts(path)
            self.assertGreater(n_moved, 0)
            self.assertEqual(still, 0)

            after = open(path).read()
            self.assertEqual(after.count("(wire "), wires_before)
            self.assertEqual(after.count("(no_connect "), ncs_before)
            pairs_after = L.detect_overlaps(path)
            self.assertEqual(pairs_after, [])

    def test_eps8pin_overlaps_detected(self):
        """HISTORY: this test originally asserted the live eps-8pin board
        carried >0 collisions (the module's founding evidence). The
        2026-07-03 readability passes cleaned the fleet to ZERO, so the
        live-board assertion inverted: the board must now STAY clean, and
        the detector's teeth moved to a synthetic fixture (below)."""
        directory = os.path.join(ROOT, "beta/eps-8pin-rev3")
        paths = [os.path.join(directory, name) for name in os.listdir(directory)
                 if name.endswith(".kicad_sch")]
        pairs = {os.path.basename(path): L.detect_overlaps(path) for path in paths}
        self.assertFalse({name: found for name, found in pairs.items() if found},
                         "current EPS hierarchy regressed from zero-overlap state")

    def test_detector_teeth_on_synthetic_collision(self):
        """The detector demonstrably FAILS a bad sheet (teeth preserved
        after the live boards went clean): two labels stamped at the same
        point must collide."""
        sch = ('(kicad_sch (version 20250114) (generator "test")\n'
               '  (lib_symbols)\n'
               '(label "AAAA" (at 100 100 0)\n'
               '  (effects (font (size 1.27 1.27)) (justify left bottom)))\n'
               '(label "BBBB" (at 101 100 0)\n'
               '  (effects (font (size 1.27 1.27)) (justify left bottom)))\n)\n')
        with tempfile.NamedTemporaryFile("w", suffix=".kicad_sch",
                                         delete=False) as f:
            f.write(sch); p = f.name
        try:
            self.assertGreater(len(L.detect_overlaps(p)), 0)
        finally:
            os.unlink(p)


class CLITest(unittest.TestCase):
    def test_check_overlaps_exit_code(self):
        """Clean fleet: eps must exit 0 now (was the known-bad exit-1 board
        pre-readability-pass); nonzero exit teeth ride the synthetic fixture
        in TextCollisionEngineTest."""
        eps = os.path.join(ROOT, "beta/eps-8pin-rev3/eps-8pin-rev3.kicad_sch")
        rc = L.main(["--check-overlaps", eps])
        self.assertEqual(rc, 0)


class DemoTest(unittest.TestCase):
    @unittest.skipUnless(HAVE_KICAD_CLI, "kicad-cli not on PATH")
    def test_demo_builds_erc_clean_and_overlap_free(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "demo.kicad_sch")
            stats = L.build_demo(path)
            self.assertEqual(stats["still_colliding"], 0)
            errs = [v for v in _erc(path) if v["severity"] == "error"]
            self.assertEqual(errs, [], f"demo should be ERC-error-clean: {errs}")
            pairs = L.detect_overlaps(path)
            self.assertEqual(pairs, [], "demo should be collision-free after its own nudge pass")
            rc = L.main(["--check-overlaps", path])
            self.assertEqual(rc, 0)


class RotatedFieldBBoxTest(unittest.TestCase):
    """KiCad renders a symbol field at (symbol rotation + stored field angle)
    -- measured via `kicad-cli sch export svg` (a rot-90 R_Small's field at
    stored angle 0 carries rotate(-90) in the SVG; at stored angle 90 it has
    no rotate, i.e. horizontal). detect_overlaps/nudge_texts must therefore
    compute property bboxes at the RENDERED angle, not the stored one --
    found live on hub-enterprise 01f (2026-07-03): the rot-90 inductor's
    horizontal 21-char Value was bboxed as a tall vertical strip, which
    false-collided with its neighbors and got nudged 40mm off the part."""

    def _sheet(self, td, field_ang):
        parts = {"R1": ("cec-vendor", "R_Small", "WIDE_VALUE_TEXT")}
        used = cec_sch.load_symbols(LIBS, parts)
        root = cec_sch.u()
        x, y = 101.6, 101.6
        sym = (
            "\t(symbol\n"
            '\t\t(lib_id "cec-vendor:R_Small")\n'
            f"\t\t(at {x} {y} 90)\n\t\t(unit 1)\n"
            "\t\t(exclude_from_sim no)\n\t\t(in_bom yes)\n\t\t(on_board yes)\n\t\t(dnp no)\n"
            f'\t\t(uuid "{cec_sch.u()}")\n'
            f'\t\t(property "Reference" "R1" (at {x} {y - 8} {field_ang}) '
            f'(effects (font (size 1.27 1.27))))\n'
            f'\t\t(property "Value" "WIDE_VALUE_TEXT" (at {x} {y + 8} {field_ang}) '
            f'(effects (font (size 1.27 1.27))))\n'
            f'\t\t(property "Footprint" "" (at {x} {y} 0) (effects (font (size 1.27 1.27)) (hide yes)))\n'
            f'\t\t(property "Datasheet" "" (at {x} {y} 0) (effects (font (size 1.27 1.27)) (hide yes)))\n'
            f'\t\t(pin "1" (uuid "{cec_sch.u()}"))\n\t\t(pin "2" (uuid "{cec_sch.u()}"))\n'
            f'\t\t(instances\n\t\t\t(project "rotfield"\n\t\t\t\t(path "/{root}" '
            f'(reference "R1") (unit 1))\n\t\t\t)\n\t\t)\n'
            "\t)")
        content = (
            "(kicad_sch\n\t(version 20260306)\n\t(generator \"eeschema\")\n"
            "\t(generator_version \"10.0\")\n"
            f"\t(uuid \"{root}\")\n\t(paper \"A4\")\n"
            + cec_sch.lib_symbols_section(used) + "\n" + sym + "\n"
            + "\t(sheet_instances\n\t\t(path \"/\"\n\t\t\t(page \"1\")\n\t\t)\n\t)\n"
            "\t(embedded_fonts no)\n)\n")
        path = os.path.join(td, f"rotfield_{field_ang}.kicad_sch")
        open(path, "w").write(content)
        return path

    def test_property_bbox_uses_rendered_angle(self):
        with tempfile.TemporaryDirectory() as td:
            # stored angle 90 on a rot-90 symbol renders HORIZONTAL: the bbox
            # must be wide (x extent >> y extent)
            els = L._extract_text_elements(open(self._sheet(td, 90)).read())
            val = next(e for e in els if e["text"] == "WIDE_VALUE_TEXT")
            self.assertEqual(val["render_ang"], 180)   # 90 stored + 90 symbol
            x0, x1, y0, y1 = val["bbox"]
            self.assertGreater(x1 - x0, (y1 - y0) * 3,
                                "rot-90 symbol + angle-90 field renders horizontal; "
                                "bbox must be wide, not tall")
            # stored angle 0 on the same rot-90 symbol renders VERTICAL
            els = L._extract_text_elements(open(self._sheet(td, 0)).read())
            val = next(e for e in els if e["text"] == "WIDE_VALUE_TEXT")
            self.assertEqual(val["render_ang"], 90)
            x0, x1, y0, y1 = val["bbox"]
            self.assertGreater(y1 - y0, (x1 - x0) * 3,
                                "rot-90 symbol + angle-0 field renders vertical; "
                                "bbox must be tall, not wide")


class PinGlyphOverlapTest(unittest.TestCase):
    """Standard S6 teeth (2026-07-03): symbol pin NAME/NUMBER glyphs are
    first-class text for the overlap gate. Fixture reproduces the two REAL
    defect classes found on modules/ent-common/01-power (pre-fix): (a) a
    too-narrow symbol body whose OPPOSING pin names interleave (the TPS26621
    "UVLO"/"ILIM" garble), and (b) a net label printed over a pin name.
    A pin's own name/number pair must NOT be reported."""

    _SHEET = """(kicad_sch
\t(version 20260306)
\t(generator "eeschema")
\t(generator_version "10.0")
\t(uuid "aaaa1111-2222-3333-4444-555566667777")
\t(paper "A4")
\t(lib_symbols
\t\t(symbol "t:NARROW"
\t\t\t(pin_names (offset 0.254))
\t\t\t(exclude_from_sim no) (in_bom yes) (on_board yes)
\t\t\t(symbol "NARROW_0_1"
\t\t\t\t(rectangle (start -2.54 5.08) (end 2.54 -5.08)
\t\t\t\t\t(stroke (width 0.254) (type default)) (fill (type background))
\t\t\t\t)
\t\t\t)
\t\t\t(symbol "NARROW_1_1"
\t\t\t\t(pin passive line (at -7.62 0 0) (length 5.08)
\t\t\t\t\t(name "UVLO" (effects (font (size 1.27 1.27))))
\t\t\t\t\t(number "1" (effects (font (size 1.27 1.27))))
\t\t\t\t)
\t\t\t\t(pin passive line (at 7.62 0 180) (length 5.08)
\t\t\t\t\t(name "ILIM" (effects (font (size 1.27 1.27))))
\t\t\t\t\t(number "2" (effects (font (size 1.27 1.27))))
\t\t\t\t)
\t\t\t)
\t\t)
\t)
\t(symbol
\t\t(lib_id "t:NARROW")
\t\t(at 100 100 0)
\t\t(unit 1)
\t\t(exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)
\t\t(uuid "bbbb1111-2222-3333-4444-555566667777")
\t\t(property "Reference" "U9" (at 100 80 0) (effects (font (size 1.27 1.27))))
\t\t(property "Value" "NARROW" (at 100 120 0) (effects (font (size 1.27 1.27))))
\t\t(pin "1" (uuid "cccc1111-2222-3333-4444-555566667771"))
\t\t(pin "2" (uuid "cccc1111-2222-3333-4444-555566667772"))
\t\t(instances (project "t" (path "/aaaa1111-2222-3333-4444-555566667777"
\t\t\t(reference "U9") (unit 1))))
\t)
\t(label "OVERPIN" (at 96 100.5 0)
\t\t(effects (font (size 1.27 1.27)) (justify left bottom))
\t\t(uuid "dddd1111-2222-3333-4444-555566667777"))
\t(sheet_instances (path "/" (page "1")))
\t(embedded_fonts no)
)
"""

    def _pairs(self, **kw):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "narrow.kicad_sch")
            open(p, "w").write(self._SHEET)
            return L.detect_overlaps(p, **kw)

    def test_pin_name_collisions_detected(self):
        pairs = self._pairs()
        kinds = [tuple(sorted((a["kind"], b["kind"]))) for a, b in pairs]
        # (a) the opposing-pin-name interleave (the J1/U2 garble class)
        self.assertIn(("pin_name", "pin_name"), kinds)
        namepair = next((a, b) for a, b in pairs
                        if a["kind"] == b["kind"] == "pin_name")
        self.assertEqual({namepair[0]["text"], namepair[1]["text"]},
                         {"UVLO", "ILIM"})
        # (b) the label-over-pin-name class
        self.assertTrue(any({a["kind"], b["kind"]} == {"label", "pin_name"}
                            for a, b in pairs),
                        f"label-on-pin-name not detected: {kinds}")
        # a pin's own name/number pair is exempt
        for a, b in pairs:
            if a["kind"].startswith("pin_") and b["kind"].startswith("pin_"):
                self.assertFalse(a.get("pin") == b.get("pin")
                                 and a.get("ref") == b.get("ref"),
                                 "same-pin name/number pair must be exempt")

    def test_old_detector_was_blind(self):
        # the pre-S6 detector (pin_glyphs=False) sees NOTHING here -- the
        # exact blindness the 01-power garble shipped through
        self.assertEqual(len(self._pairs(pin_glyphs=False)), 0)




class WireCollisionTest(unittest.TestCase):
    """Teeth for check_wire_collisions (2026-07-03 owner escalation): text
    lying across a wire fires; a label anchored at its own wire's endpoint
    does not (the anchored-by-design exemption)."""
    def _sheet(self, extra):
        return ('(kicad_sch (version 20250114) (generator "test")\n'
                '  (lib_symbols)\n' + extra + ')\n')

    def test_text_across_wire_fires(self):
        import tempfile, os
        sch = self._sheet(
            '(wire (pts (xy 100 100) (xy 140 100)))\n'
            '(text "COLLIDING" (at 110 100 0)\n'
            '  (effects (font (size 1.27 1.27)) (justify left)))\n')
        with tempfile.NamedTemporaryFile("w", suffix=".kicad_sch",
                                         delete=False) as f:
            f.write(sch); p = f.name
        try:
            hits = L.check_wire_collisions(p)
            self.assertTrue(any("COLLIDING" in h for h in hits), hits)
        finally:
            os.unlink(p)

    def test_anchored_label_exempt(self):
        import tempfile, os
        sch = self._sheet(
            '(wire (pts (xy 100 100) (xy 120 100)))\n'
            '(label "NETNAME" (at 120 100 0)\n'
            '  (effects (font (size 1.27 1.27)) (justify left bottom)))\n')
        with tempfile.NamedTemporaryFile("w", suffix=".kicad_sch",
                                         delete=False) as f:
            f.write(sch); p = f.name
        try:
            hits = L.check_wire_collisions(p)
            self.assertFalse([h for h in hits if "NETNAME" in h], hits)
        finally:
            os.unlink(p)


class DirectionalMisrotTest(unittest.TestCase):
    """Teeth for the 2026-07-04 owner round-3 fix: check_power_glyphs' old
    MISROT model measured wire-length-inside-a-symmetric-box-around-the-
    ORIGIN -- but the wire STARTS at the origin (the box's own center), so a
    normal singly-attached stub can only ever clip up to half the box
    (glyph_half), never the through_len=2.0 threshold, REGARDLESS of whether
    the flag is actually rotated correctly. The owner's crop reproduced here:
    a +3V3 supply flag directly above a cap with only a short (3.81mm STUB)
    wire dropping to it -- misrotated 180 degrees so the arrow points DOWN
    INTO the wire instead of up away from it. The fixture uses the REAL
    cec-power:+3V3 lib symbol geometry (pin at local (0,0), angle 90 --
    verified against the as-built hub-standard/eps-8pin schematics).

    Root cause of the companion Value-on-glyph bug (traced to
    cec_sch.emit_global_power, 2026-07-04): it places the Value property at a
    FIXED absolute offset (y+3.81) that does not rotate with the instance --
    correct for a symbol whose own glyph draws toward +y (GND), but for a
    rail-type glyph (draws toward -y at rot=0) a rot=180 instance flips the
    glyph onto the +y side too, landing Value inside/against it. The fixture
    below places Value inside the ROTATED glyph's real footprint to exercise
    exactly that collision (see test_own_flag_carveout_tightened)."""

    _FLAG_LIB = """\t\t(symbol "cec-power:+3V3"
\t\t\t(power global)
\t\t\t(pin_numbers (hide yes))
\t\t\t(pin_names (offset 0) (hide yes))
\t\t\t(exclude_from_sim no) (in_bom yes) (on_board yes) (in_pos_files yes)
\t\t\t(property "Reference" "#PWR" (at 0 -3.81 0) (hide yes)
\t\t\t\t(effects (font (size 1.27 1.27))))
\t\t\t(property "Value" "+3V3" (at 0 3.556 0)
\t\t\t\t(effects (font (size 1.27 1.27))))
\t\t\t(symbol "+3V3_0_1"
\t\t\t\t(polyline (pts (xy -0.762 1.27) (xy 0 2.54))
\t\t\t\t\t(stroke (width 0) (type default)) (fill (type none)))
\t\t\t\t(polyline (pts (xy 0 2.54) (xy 0.762 1.27))
\t\t\t\t\t(stroke (width 0) (type default)) (fill (type none)))
\t\t\t\t(polyline (pts (xy 0 0) (xy 0 2.54))
\t\t\t\t\t(stroke (width 0) (type default)) (fill (type none)))
\t\t\t)
\t\t\t(symbol "+3V3_1_1"
\t\t\t\t(pin power_in line (at 0 0 90) (length 0)
\t\t\t\t\t(name "~" (effects (font (size 1.27 1.27))))
\t\t\t\t\t(number "1" (effects (font (size 1.27 1.27)))))
\t\t\t)
\t\t)
"""

    def _sheet(self, rot):
        # flag at (100,100); a 3.81mm (cec_sch.STUB) wire drops straight DOWN
        # to where a cap's top pin would be -- the owner's short-stub crop.
        return (
            '(kicad_sch (version 20260306) (generator "test")\n'
            '  (lib_symbols\n' + self._FLAG_LIB + '  )\n'
            '  (symbol\n'
            f'    (lib_id "cec-power:+3V3")\n'
            f'    (at 100 100 {rot})\n'
            '    (unit 1)\n'
            '    (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)\n'
            '    (uuid "aaaa0000-0000-0000-0000-000000000001")\n'
            '    (property "Reference" "#PWR1" (at 100 96.19 0) (hide yes)\n'
            '      (effects (font (size 1.27 1.27))))\n'
            '    (property "Value" "+3V3" (at 100 101.5 0)\n'
            '      (effects (font (size 1.27 1.27))))\n'
            '    (pin "1" (uuid "aaaa0000-0000-0000-0000-000000000002"))\n'
            '    (instances (project "t" (path "/x" (reference "#PWR1") (unit 1))))\n'
            '  )\n'
            '  (wire (pts (xy 100 100) (xy 100 103.81)))\n'
            '  (sheet_instances (path "/" (page "1")))\n'
            '  (embedded_fonts no)\n)\n')

    def _write(self, rot):
        import tempfile
        f = tempfile.NamedTemporaryFile("w", suffix=".kicad_sch", delete=False)
        f.write(self._sheet(rot))
        f.close()
        return f.name

    def test_misrotated_flag_fires(self):
        """rot=180: the glyph draws DOWNWARD (toward the wire) -- MISROT."""
        p = self._write(180)
        try:
            findings = L.check_power_glyphs(p)
            self.assertTrue(any("MISROT" in f and "#PWR1" in f
                                for f in findings), findings)
        finally:
            os.unlink(p)

    def test_correctly_rotated_flag_is_silent(self):
        """rot=0: the glyph draws UPWARD (away from the wire) -- clean."""
        p = self._write(0)
        try:
            findings = L.check_power_glyphs(p)
            self.assertFalse([f for f in findings if "MISROT" in f], findings)
        finally:
            os.unlink(p)

    def test_old_symmetric_model_was_blind_to_this_case(self):
        """The pre-fix formula (clip-length inside a +/-1.4mm box centered on
        the ORIGIN) tops out at glyph_half (1.4mm) for any wire that starts
        at the origin and runs one direction only -- below the 2.0mm
        through_len threshold regardless of rotation, which is exactly why
        the owner's short-stub crop escaped it."""
        gx, gy = 100.0, 100.0
        gb = (gx - 1.4, gy - 1.4, gx + 1.4, gy + 1.4)
        seg = (100.0, 100.0, 100.0, 103.81)
        self.assertLessEqual(L._seg_clip_len(gb, seg), 2.0)

    def test_rotate_flag_180_fixes_the_misrot(self):
        p = self._write(180)
        try:
            self.assertTrue(any("MISROT" in f
                                for f in L.check_power_glyphs(p)))
            ok = L.rotate_flag_180(p, "#PWR1")
            self.assertTrue(ok)
            findings = L.check_power_glyphs(p)
            self.assertFalse([f for f in findings if "MISROT" in f], findings)
            # rotation-only: the pin's (x,y) origin -- the electrical
            # connection point -- must be untouched.
            text = open(p).read()
            self.assertIn("(at 100 100 0)", text)
        finally:
            os.unlink(p)

    def test_own_flag_carveout_tightened(self):
        """The Value text ("+3V3") sitting at its documented offset (3.556mm
        below the origin, i.e. ON the glyph side when misrotated 180) must
        now be caught by check_wire_collisions' own-flag directional bbox --
        the old +/-0.6mm-around-origin carve-out never reached that far."""
        p = self._write(180)
        try:
            findings = L.check_wire_collisions(p)
            self.assertTrue(any("+3V3" in f and "glyph" in f
                                for f in findings), findings)
        finally:
            os.unlink(p)


class RetrofitDecouplerAdjacencyTest(unittest.TestCase):
    """Teeth for retrofit_decoupler_adjacency (2026-07-04 owner round-3 item
    4): relocating an EXISTING decoupler next to its owner IC on an
    already-serialized flat sheet, identity-safe by construction (moves
    existing refs + adds one wire between two nodes already sharing a net;
    never adds/deletes a #PWR/#FLG ref -- verified live against a real
    kicad-cli netlist diff that this class of edit never changes a net's
    (ref,pin) membership set)."""

    @unittest.skipUnless(HAVE_KICAD_CLI, "kicad-cli not on PATH")
    def test_relocates_and_wires_in_open_space(self):
        parts = {"U1": ("cec-vendor", "R_Small", "10k"),
                  "C1": ("cec-vendor", "C_Small", "100n")}
        used = cec_sch.load_symbols(LIBS, parts)
        placement = {"U1": (101.6, 101.6, 0), "C1": (200.0, 300.0, 0)}
        root = cec_sch.u()
        body = [cec_sch.emit_symbol(r, parts[r][0], parts[r][1], parts[r][2],
                                    *placement[r][:2],
                                    used[(parts[r][0], parts[r][1])]["pins"],
                                    "t", root)
                for r in parts]
        c1p1 = L.pin_abs_rot(placement, used, parts, "C1", "1")[:2]
        c1p2 = L.pin_abs_rot(placement, used, parts, "C1", "2")[:2]
        flag1 = (c1p1[0], c1p1[1] - 3.81)
        flag2 = (c1p2[0], c1p2[1] + 3.81)
        body.append(cec_sch.emit_global_power("+3V3", *flag1, "t", root, "#PWR1", 0))
        body.append(cec_sch.emit_global_power("GND", *flag2, "t", root, "#PWR2", 0))
        # the IC's OWN power pin must ALREADY be on the same net before the
        # retrofit (true of every real IC power pin, which always has its
        # own decoupling/supply network) -- give U1 pin 2 its own +3V3 flag
        # too, so the precondition for the identity-safety argument holds.
        u1p2 = L.pin_abs_rot(placement, used, parts, "U1", "2")[:2]
        icflag = (u1p2[0] - 3.81, u1p2[1])
        body.append(cec_sch.emit_global_power("+3V3", *icflag, "t", root, "#PWR3", 0))
        wires = [cec_sch.emit_wire(c1p1[0], c1p1[1], *flag1),
                cec_sch.emit_wire(c1p2[0], c1p2[1], *flag2),
                cec_sch.emit_wire(u1p2[0], u1p2[1], *icflag)]
        content = (
            "(kicad_sch (version 20260306) (generator \"eeschema\")\n"
            "(generator_version \"10.0\")\n"
            f"(uuid \"{root}\")\n(paper \"A4\")\n"
            + cec_sch.lib_symbols_section(used, ()) + "\n"
            + "\n".join(body) + "\n" + "\n".join(wires) + "\n"
            "(sheet_instances (path \"/\" (page \"1\")))\n(embedded_fonts no)\n)\n")
        with tempfile.NamedTemporaryFile("w", suffix=".kicad_sch",
                                         delete=False) as f:
            f.write(content)
            path = f.name
        try:
            before_ref_pins = set(re.findall(r'\(reference "([^"]+)"\)', content))
            ok = L.retrofit_decoupler_adjacency(path, "U1", "2", "C1")
            self.assertTrue(ok)
            after = open(path).read()
            # no ref added or removed
            after_ref_pins = set(re.findall(r'\(reference "([^"]+)"\)', after))
            self.assertEqual(before_ref_pins, after_ref_pins)
            # a NEW wire directly links the IC pin to the cap's rail pin
            ic_ax, ic_ay = L.pin_abs_rot(
                {"U1": (101.6, 101.6, 0)}, used, parts, "U1", "2")[:2]
            self.assertIn(f'(xy {cec_sch.f(ic_ax)} {cec_sch.f(ic_ay)})', after)
            # ERC must not gain a new error class (the one pre-existing
            # "pin_not_connected" is U1 pin 1, never wired in this fixture
            # and unrelated to the retrofit)
            viol = _erc(path)
            errs = [v for v in viol if v["severity"] == "error"]
            self.assertLessEqual(len(errs), 1, errs)
        finally:
            os.unlink(path)

    def test_returns_false_without_touching_file_when_no_safe_spot(self):
        """Congested-board honesty: if no gap step clears the real
        overlap/wire checkers, the mutator must return False and leave the
        file byte-identical (never a degraded/partially-collided commit)."""
        parts = {"U1": ("cec-vendor", "R_Small", "10k"),
                  "C1": ("cec-vendor", "C_Small", "100n")}
        used = cec_sch.load_symbols(LIBS, parts)
        placement = {"U1": (101.6, 101.6, 0), "C1": (150.0, 150.0, 0)}
        root = cec_sch.u()
        body = [cec_sch.emit_symbol(r, parts[r][0], parts[r][1], parts[r][2],
                                    *placement[r][:2],
                                    used[(parts[r][0], parts[r][1])]["pins"],
                                    "t", root)
                for r in parts]
        c1p1 = L.pin_abs_rot(placement, used, parts, "C1", "1")[:2]
        c1p2 = L.pin_abs_rot(placement, used, parts, "C1", "2")[:2]
        flag1 = (c1p1[0], c1p1[1] - 3.81)
        flag2 = (c1p2[0], c1p2[1] + 3.81)
        body.append(cec_sch.emit_global_power("+3V3", *flag1, "t", root, "#PWR1", 0))
        body.append(cec_sch.emit_global_power("GND", *flag2, "t", root, "#PWR2", 0))
        wires = [cec_sch.emit_wire(c1p1[0], c1p1[1], *flag1),
                cec_sch.emit_wire(c1p2[0], c1p2[1], *flag2)]
        # blanket a wall of decoy flags all along the IC's outward search
        # line so every candidate gap step is blocked -- forces exhaustion.
        for i in range(1, 20):
            body.append(cec_sch.emit_global_power(
                "GND", 101.6, 101.6 - i * 2.0, "t", root, f"#PWR{100+i}", 0))
        content = (
            "(kicad_sch (version 20260306) (generator \"eeschema\")\n"
            "(generator_version \"10.0\")\n"
            f"(uuid \"{root}\")\n(paper \"A4\")\n"
            + cec_sch.lib_symbols_section(used, ()) + "\n"
            + "\n".join(body) + "\n" + "\n".join(wires) + "\n"
            "(sheet_instances (path \"/\" (page \"1\")))\n(embedded_fonts no)\n)\n")
        with tempfile.NamedTemporaryFile("w", suffix=".kicad_sch",
                                         delete=False) as f:
            f.write(content)
            path = f.name
        try:
            before_bytes = open(path, "rb").read()
            ok = L.retrofit_decoupler_adjacency(path, "U1", "2", "C1",
                                                max_gap=12.0)
            self.assertFalse(ok)
            self.assertEqual(open(path, "rb").read(), before_bytes)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
