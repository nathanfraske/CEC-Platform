#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Smoke tests for scripts/cec_sch_compose.py (the shared hierarchical
# schematic-composition engine) + one archetype teeth case
# (scripts/cec_sch_archetypes.py). HOST-RUNNABLE: needs only kicad-cli on
# PATH (netlist export); no pcbnew, no GUI.
#
#   python3 -m unittest tests.test_sch_compose -v
import os
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_sch                       # noqa: E402
import cec_sch_compose as C          # noqa: E402
import cec_sch_archetypes as arch    # noqa: E402

HAVE_KICAD_CLI = True
try:
    subprocess.run(["kicad-cli", "version"], capture_output=True, check=True)
except Exception:
    HAVE_KICAD_CLI = False

LIBS = {
    "cec-vendor": open(os.path.join(ROOT, "lib/vendor/cec-vendor.kicad_sym")).read(),
    "power": open(os.path.join(ROOT, "lib/vendor/cec-power.kicad_sym")).read(),
}


def _netlist_groups(root_path):
    """Export the netlist via kicad-cli; return ({net_name: {(ref,pin)}}, stderr)."""
    out = root_path + ".net"
    r = subprocess.run(["kicad-cli", "sch", "export", "netlist", "-o", out, root_path],
                       capture_output=True, text=True)
    nets = {}
    txt = open(out).read()
    for m in re.finditer(r'\(net\s*\n\s*\(code "\d+"\)\s*\n\s*\(name "([^"]+)"\)'
                         r'(.*?)(?=\(net\s*\n\s*\(code|\Z)', txt, re.S):
        nodes = set(re.findall(r'\(ref "([^"]+)"\)\s*\n\s*\(pin "([^"]+)"\)', m.group(2)))
        if nodes:
            nets[m.group(1)] = nodes
    return nets, r.stderr


def _group_of(nets, node):
    for name, nodes in nets.items():
        if node in nodes:
            return name, nodes
    return None, set()


def _build_mini_hierarchy(td, lf, compose_fn, power_ports, powerflag_nets=()):
    """One leaf + a root-as-thin-parent (the ent-common shape), on disk in td.
    Returns the root path."""
    root_uuid = cec_sch.u()
    leaf_sym_uuid = cec_sch.u()
    leaf_own_uuid = cec_sch.u()
    c = C.Compose(lf, LIBS)
    compose_fn(c)
    c.done()
    C.build_leaf(
        lf.parts, lf.nets, lf.footprints, lf.props, lf.placement, lf.nc_skip,
        power_ports, list(powerflag_nets), lf.hier_exports, None,
        LIBS, "mini",
        path_prefix=f"{root_uuid}/{leaf_sym_uuid}",
        sheet_instances_path=leaf_sym_uuid,
        own_uuid=leaf_own_uuid, page="2",
        out_path=os.path.join(td, lf.filename), paper="A4",
        title=f"mini: {lf.sheetname}", comment1="test leaf", pwr_base=100,
        layout=lf.layout)
    root_path = os.path.join(td, "mini.kicad_sch")
    C.build_thin_parent(
        [{"id": lf.id, "sym_uuid": leaf_sym_uuid, "filename": lf.filename,
          "sheetname": lf.sheetname, "page": "2",
          "x": 25.4, "y": 25.4, "w": 63.5, "h": 38.1,
          "pins": [(n, shape, "right") for n, (shape, _a) in lf.hier_exports.items()]}],
        set(), "mini", root_uuid, None, root_uuid, out_path=root_path,
        title="mini root", paper="A4", libs=LIBS)
    return root_path


class ImportSmokeTest(unittest.TestCase):
    def test_engine_surface(self):
        self.assertIn("A4", C.PAPER)
        self.assertTrue(callable(C.build_leaf))
        self.assertTrue(callable(C.build_thin_parent))
        self.assertTrue(callable(C.build_root))
        lf = C.Leaf("t", "t.kicad_sch", "t", "test")
        lf.add_part("R1", "cec-vendor", "R_Small", "10k", 0, 0, "")
        lf.net("A", ("R1", "1"))
        self.assertEqual(lf.nets["A"], [("R1", "1")])
        c = C.Compose(lf, LIBS)
        c.place("R1", 80, 80)
        # pin math sanity: R_Small pin 1 sits 2 grid units above the origin
        self.assertEqual(c.pin("R1", "1"), (80, 78))

    def test_archetypes_import(self):
        for fn in (arch.divider_chain, arch.protection_chain, arch.pullup_hang,
                   arch.crystal_block, arch.decoupler_bank, arch.protected_rail):
            self.assertTrue(callable(fn))


class BuildLeafRoundtripTest(unittest.TestCase):
    """A 2-part leaf under a root-as-thin-parent must round-trip through
    kicad-cli's own netlist exporter with the expected connectivity and a
    clean stderr (no annotation errors)."""

    @unittest.skipUnless(HAVE_KICAD_CLI, "kicad-cli not on PATH")
    def test_two_part_leaf(self):
        lf = C.Leaf("t1", "t1-leaf.kicad_sch", "t1-leaf", "round-trip fixture")
        lf.add_part("R1", "cec-vendor", "R_Small", "10k", 0, 0, "")
        lf.add_part("C1", "cec-vendor", "C_Small", "100n", 0, 0, "")
        lf.net("A", ("R1", "1"))
        lf.net("MID", ("R1", "2"), ("C1", "1"))
        lf.net("B", ("C1", "2"))
        lf.hier_exports = {"A": ("output", ("R1", "1")),
                           "B": ("output", ("C1", "2"))}

        def compose(c):
            c.place("R1", 80, 80)
            c.place("C1", 90, 80)

        with tempfile.TemporaryDirectory() as td:
            root = _build_mini_hierarchy(td, lf, compose, {})
            nets, stderr = _netlist_groups(root)
            self.assertNotIn("error", stderr.lower(), f"netlist stderr: {stderr}")
            _n, mid = _group_of(nets, ("R1", "2"))
            self.assertEqual(mid, {("R1", "2"), ("C1", "1")})
            _n, a = _group_of(nets, ("R1", "1"))
            self.assertEqual(a, {("R1", "1")})           # exported, alone in the fixture
            _n, b = _group_of(nets, ("C1", "2"))
            self.assertEqual(b, {("C1", "2")})


class ProtectionChainTeethTest(unittest.TestCase):
    """Archetype teeth: protection_chain must produce a REAL series element
    (input node electrically distinct from the shunt node) and the shunt
    returns must land on GND -- verified via kicad-cli's netlist, not the
    generator's own bookkeeping."""

    @unittest.skipUnless(HAVE_KICAD_CLI, "kicad-cli not on PATH")
    def test_series_then_shunts(self):
        lf = C.Leaf("t2", "t2-leaf.kicad_sch", "t2-leaf", "protection-chain fixture")
        lf.add_part("R7", "cec-vendor", "R_Small", "10k", 0, 0, "")
        lf.add_part("D1", "cec-vendor", "D_Schottky", "PESD5V0S1BA", 0, 0, "")
        lf.add_part("R8", "cec-vendor", "R_Small", "10k", 0, 0, "")
        lf.net("RAW", ("R7", "1"))
        lf.net("NODE", ("R7", "2"), ("D1", "1"), ("R8", "1"))
        lf.net("GND", ("D1", "2"), ("R8", "2"))
        lf.hier_exports = {"RAW": ("output", ("R7", "1")),
                           "NODE": ("output", ("R7", "2"))}

        def compose(c):
            c.hier("RAW", 60, 60, 180)
            arch.protection_chain(c, (60, 60),
                                  [("series", "R7"), ("shunt", "D1"), ("shunt", "R8")],
                                  "NODE", out_kind="hier")

        with tempfile.TemporaryDirectory() as td:
            root = _build_mini_hierarchy(td, lf, compose, {"GND": "GND"})
            nets, stderr = _netlist_groups(root)
            self.assertNotIn("error", stderr.lower(), f"netlist stderr: {stderr}")
            _n, node = _group_of(nets, ("D1", "1"))
            self.assertEqual(node, {("R7", "2"), ("D1", "1"), ("R8", "1")},
                             "post-series node must carry both shunts")
            self.assertNotIn(("R7", "1"), node,
                             "series element must keep RAW off the shunt node")
            gname, gnd = _group_of(nets, ("D1", "2"))
            self.assertEqual(gname, "GND")
            self.assertEqual(gnd, {("D1", "2"), ("R8", "2")})


if __name__ == "__main__":
    unittest.main()
