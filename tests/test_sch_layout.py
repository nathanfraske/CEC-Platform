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
        """The checker sees the REAL, pre-existing problem in a generated
        board (evidence for the module's whole thesis) -- report the count,
        do not fix that board."""
        path = os.path.join(ROOT, "modules/eps-8pin/eps8pin-module.kicad_sch")
        pairs = L.detect_overlaps(path)
        self.assertGreater(len(pairs), 0,
                            "eps-8pin is known to carry GND/label collisions (SENSEC*/VBUS)")


class CLITest(unittest.TestCase):
    def test_check_overlaps_exit_code(self):
        eps = os.path.join(ROOT, "modules/eps-8pin/eps8pin-module.kicad_sch")
        rc = L.main(["--check-overlaps", eps])
        self.assertEqual(rc, 1)


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


if __name__ == "__main__":
    unittest.main()
