#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  Tests for scripts/cec_pcb_reconcile.py -- the flat->hierarchical PCB
#  reconciliation tool (docs/standard-tier-review/round4-hier-conversion-
#  2026-07-04.md). Host-runnable: needs kicad-cli + pcbnew (both present in
#  this container per CLAUDE.md's KiCad environment section); skips cleanly
#  if either is missing.
#
#  NEVER touches a committed board -- every mutating test works on a
#  tempfile.mkdtemp() scratch copy of a module directory, discarded on
#  teardown.
# ============================================================================
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, SCRIPTS)

import cec_toolchain as TC  # noqa: E402
import cec_pcb_reconcile as R  # noqa: E402

HAVE_CLI = TC.have_kicad_cli()
HAVE_PCBNEW = R.pcbnew is not None

HUB_STANDARD = os.path.join(ROOT, "hubs", "hub-standard")
EPS8PIN = os.path.join(ROOT, "modules", "eps-8pin")
HPWR12V = os.path.join(ROOT, "modules", "12vhpwr-standard")


def _copy_board(src_dir, dest_parent):
    """Copy a module/hub directory into a fresh scratch subdirectory and
    return the copy's path. Read-only on src_dir."""
    dest = os.path.join(dest_parent, os.path.basename(src_dir))
    shutil.copytree(src_dir, dest)
    return dest


def _find(board_dir, ext):
    matches = [p for p in os.listdir(board_dir) if p.endswith(ext)]
    assert len(matches) == 1, f"expected exactly one *{ext} in {board_dir}: {matches}"
    return os.path.join(board_dir, matches[0])


# ---------------------------------------------------------------- calibration
@unittest.skipUnless(HAVE_CLI, "kicad-cli not available")
class HubStandardCalibrationTest(unittest.TestCase):
    """symbol_paths() must reproduce EXACTLY what real KiCad/pcbnew already
    wrote into hub-standard's committed, FLAT-project PCB -- the calibration
    gate the task explicitly demands before trusting the walker on anything
    hierarchical. Read-only: parses the committed files directly, never
    copies or writes.

    Measured baseline this test pins (see cec_pcb_reconcile.py's header):
    91 footprints total, 75 carry a `(path ...)` field, 90 schematic
    components carry a footprint. Of the 75 PCB paths, 2 (J_5VSB, J_5V) are
    KNOWN-STALE -- the schematic consolidated them into a single J_PWR that
    the PCB has not been re-synced to yet (documented in CLAUDE.md's action
    item 0) -- so the exact-match set is the 73-ref intersection, not all 75.
    """

    def test_symbol_paths_matches_committed_pcb_exactly(self):
        sch = _find(HUB_STANDARD, ".kicad_sch")
        pcb = _find(HUB_STANDARD, ".kicad_pcb")

        sym_paths = R.symbol_paths(sch)
        self.assertGreater(len(sym_paths), 0)

        pcb_text = open(pcb, encoding="utf-8").read()
        fp_paths = {}
        for _s, _e, blk in R._iter_footprint_blocks(pcb_text):
            refm = R._FP_REF_RE.search(blk)
            pathm = R._PATH_RE.search(blk)
            if refm and pathm:
                fp_paths[refm.group(1)] = pathm.group(2)

        # Calibration pin: exact counts measured 2026-07-04. A change here
        # means either the committed board moved on (expected, update the
        # pin) or the walker regressed (investigate).
        self.assertEqual(len(fp_paths), 75, "hub-standard path-bearing footprint count moved")
        self.assertEqual(len(sym_paths), 90, "hub-standard schematic component count moved")

        common = set(sym_paths) & set(fp_paths)
        self.assertEqual(len(common), 73,
                          "expected exactly 73 refs in common (75 PCB paths minus the "
                          "2 known-stale J_5VSB/J_5V; see CLAUDE.md action item 0)")

        mismatches = {r: (sym_paths[r], fp_paths[r]) for r in common if sym_paths[r] != fp_paths[r]}
        self.assertEqual(mismatches, {}, f"symbol_paths disagreed with the committed PCB: {mismatches}")

        # the 2 documented-stale refs are exactly the delta, not something new
        stale = set(fp_paths) - set(sym_paths)
        self.assertEqual(stale, {"J_5VSB", "J_5V"})


# --------------------------------------------------------- build_rename_map
class BuildRenameMapTest(unittest.TestCase):
    def test_changed_pairs_only(self):
        old = {frozenset({("U1", "1")}): "/FOO",
               frozenset({("U2", "1")}): "+3V3"}
        new = {frozenset({("U1", "1")}): "/leaf1/FOO",
               frozenset({("U2", "1")}): "+3V3"}
        self.assertEqual(R.build_rename_map(old, new), {"/FOO": "/leaf1/FOO"})

    def test_missing_group_raises(self):
        old = {frozenset({("U1", "1")}): "/A",
               frozenset({("U2", "1")}): "/B"}
        new = {frozenset({("U1", "1")}): "/leaf/A"}
        with self.assertRaises(ValueError):
            R.build_rename_map(old, new)

    def test_extra_group_raises(self):
        old = {frozenset({("U1", "1")}): "/A"}
        new = {frozenset({("U1", "1")}): "/leaf/A",
               frozenset({("U2", "1")}): "/B"}
        with self.assertRaises(ValueError):
            R.build_rename_map(old, new)

    def test_non_bijection_collapse_raises(self):
        # two distinct old nets renamed onto the SAME new name -- a short/merge.
        old = {frozenset({("U1", "1")}): "/A",
               frozenset({("U2", "1")}): "/B"}
        new = {frozenset({("U1", "1")}): "/leaf/SAME",
               frozenset({("U2", "1")}): "/leaf/SAME"}
        with self.assertRaises(ValueError):
            R.build_rename_map(old, new)

    def test_disallowed_shape_terminal_segment_changed_raises(self):
        old = {frozenset({("U1", "1")}): "/A"}
        new = {frozenset({("U1", "1")}): "/leaf/DIFFERENT"}
        with self.assertRaises(ValueError):
            R.build_rename_map(old, new)

    def test_disallowed_shape_suffix_instead_of_prefix_raises(self):
        old = {frozenset({("U1", "1")}): "/A"}
        new = {frozenset({("U1", "1")}): "/A/leaf"}
        with self.assertRaises(ValueError):
            R.build_rename_map(old, new)

    def test_disallowed_shape_no_new_segment_raises(self):
        # new name equals old name with no leaf prefix inserted at all, but
        # a different top-level name -- not a valid "/X" -> "/<leaf>/X".
        old = {frozenset({("U1", "1")}): "/A"}
        new = {frozenset({("U1", "1")}): "/B"}
        with self.assertRaises(ValueError):
            R.build_rename_map(old, new)

    def test_unchanged_nets_never_appear(self):
        old = {frozenset({("U1", "1")}): "GND",
               frozenset({("U2", "1")}): "+3V3"}
        new = {frozenset({("U1", "1")}): "GND",
               frozenset({("U2", "1")}): "+3V3"}
        self.assertEqual(R.build_rename_map(old, new), {})


# ----------------------------------------------------- eps-8pin round trip
# eps-8pin is one of the three PLACEMENT-ONLY targets (zero copper, generator
# "cec-cec_pcb") -- measured (this session) to carry ZERO `(path ...)`
# footprint fields at all: none of its boards have ever been saved by real
# pcbnew, so path-relinking is a no-op there by construction (see
# cec_pcb_reconcile.py's CALIBRATION FINDINGS header and reconcile_pcb's
# `path_absent_known_ref` bucket). This class therefore exercises the NET-
# RENAME mechanics end to end (the part that DOES matter for these boards),
# plus the legacy zone `(net_name "...")` form its generator uses.
@unittest.skipUnless(HAVE_CLI and HAVE_PCBNEW, "kicad-cli + pcbnew required")
class EpsRoundTripTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cec_pcb_reconcile_test_eps_")
        self.board = _copy_board(EPS8PIN, self.tmp)
        self.pcb = _find(self.board, ".kicad_pcb")
        # post round-4 the boards are hierarchical (root + leaves in one
        # dir); resolve the ROOT the same way the tool does
        self.sch = R._find_root_sch(self.board)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_net_rename_round_trip(self):
        rename_map = {"/DETAMPC1": "/02-sensing/DETAMPC1",
                      "/DETC1": "/02-sensing/DETC1"}
        # identity path_map (the schematic itself is untouched in this test;
        # only the PCB's net strings are being exercised) -- still a
        # realistic call shape since symbol_paths() is how a real caller
        # would build it.
        path_map = R.symbol_paths(self.sch)

        before_text = open(self.pcb, encoding="utf-8").read()
        expected_renames = sum(before_text.count(f'"{old}"') for old in rename_map)
        self.assertGreater(expected_renames, 0, "fixture doesn't exercise the renamed nets")

        report = R.reconcile_pcb(self.pcb, rename_map, path_map)

        self.assertTrue(report["verified"])
        self.assertEqual(report["net_renames"], expected_renames)
        self.assertEqual(report["net_count_before"], report["net_count_after"])
        # every real (non-mechanical) component on this board today lacks a
        # path field -- documented, not a defect this tool introduces.
        self.assertGreater(len(report["path_absent_known_ref"]), 0)
        self.assertEqual(report["path_updates"], 0)

        after_text = open(self.pcb, encoding="utf-8").read()
        # scope the orphan/presence check to actual net-string CONSTRUCTS
        # (not a blind whole-file substring search, which can false-positive
        # on an unrelated field that happens to hold the same text).
        remaining = {m.group(2) for m in R._NET_STR_RE.finditer(after_text)}
        for old in rename_map:
            self.assertNotIn(old, remaining, f"stray old net name {old!r} left behind")
        for new in rename_map.values():
            self.assertIn(new, remaining)

        after_nets = R._pcbnew_net_names(self.pcb)
        for old in rename_map:
            self.assertNotIn(old, after_nets)
        for new in rename_map.values():
            self.assertIn(new, after_nets)

    def test_legacy_zone_net_name_form_rewritten(self):
        # eps-8pin's GND plane uses the OLDER paired zone form:
        # `(net 28)` (bare code, untouched) + `(net_name "GND")` (renamed).
        # Renaming GND itself is not representative of the real conversion
        # (GND is a global power net that keeps its name per policy) -- this
        # test fabricates the rename purely to exercise the net_name
        # substitution path the real conversion's other nets will hit.
        before_text = open(self.pcb, encoding="utf-8").read()
        self.assertIn('(net_name "GND")', before_text, "fixture assumption changed")

        rename_map = {"GND": "/local-leaf/GND"}
        path_map = {}
        report = R.reconcile_pcb(self.pcb, rename_map, path_map)
        self.assertTrue(report["verified"])
        self.assertGreater(report["net_renames"], 0)

        after_text = open(self.pcb, encoding="utf-8").read()
        self.assertNotIn('(net_name "GND")', after_text)
        self.assertIn('(net_name "/local-leaf/GND")', after_text)

    def test_dry_run_writes_nothing(self):
        rename_map = {"/DETAMPC1": "/02-sensing/DETAMPC1"}
        path_map = {}
        before_bytes = open(self.pcb, "rb").read()

        report = R.reconcile_pcb(self.pcb, rename_map, path_map, dry_run=True)

        self.assertTrue(report["dry_run"])
        self.assertIsNone(report["verified"])
        self.assertEqual(open(self.pcb, "rb").read(), before_bytes,
                          "dry_run must never write the file")


# ------------------------------------------------- 12vhpwr-standard round trip
# The highest-stakes future target: FULLY ROUTED, CI-gated (CLAUDE.md action
# item 4). Unlike eps-8pin it is generator "pcbnew" (a real native save), so
# it carries REAL `(path ...)` fields (measured 77/84 footprints) and its
# nets use the code-free native `(net "name")` form uniformly across pads,
# segments, vias, AND its one real filled zone (the GND pour). This class is
# the one that actually exercises path_updates and the native net-string form
# on real routed copper.
@unittest.skipUnless(HAVE_CLI and HAVE_PCBNEW, "kicad-cli + pcbnew required")
class Hpwr12vPathRelinkRoundTripTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cec_pcb_reconcile_test_12v_")
        self.board = _copy_board(HPWR12V, self.tmp)
        self.pcb = _find(self.board, ".kicad_pcb")
        # post round-4 the boards are hierarchical (root + leaves in one
        # dir); resolve the ROOT the same way the tool does
        self.sch = R._find_root_sch(self.board)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_path_relink_and_native_net_rename_round_trip(self):
        path_map = R.symbol_paths(self.sch)
        self.assertIn("TH1", path_map)
        self.assertIn("TH2", path_map)

        # Fabricate a plausible post-conversion path for two real refs, as
        # if they moved under a new leaf sheet uuid -- directly exercises
        # path_updates, which eps-8pin's boards (no path fields at all) can't.
        fake_sheet_uuid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        new_path_map = dict(path_map)
        new_path_map["TH1"] = f"/{fake_sheet_uuid}" + path_map["TH1"]
        new_path_map["TH2"] = f"/{fake_sheet_uuid}" + path_map["TH2"]

        # /TEMP1, /TEMP2 are the real NTC thermal-sense nets on this board --
        # fabricated as "leaf-internal" renames purely to drive the mechanics
        # (not a claim about the real conversion's actual sheet partition).
        rename_map = {"/TEMP1": "/03-thermal/TEMP1", "/TEMP2": "/03-thermal/TEMP2"}

        before_text = open(self.pcb, encoding="utf-8").read()
        self.assertIn(f'(path "{path_map["TH1"]}")', before_text)

        report = R.reconcile_pcb(self.pcb, rename_map, new_path_map)

        self.assertTrue(report["verified"])
        self.assertEqual(report["path_updates"], 2)
        self.assertGreater(report["net_renames"], 0)
        self.assertEqual(report["net_count_before"], report["net_count_after"])

        after_text = open(self.pcb, encoding="utf-8").read()
        self.assertIn(f'(path "{new_path_map["TH1"]}")', after_text)
        self.assertIn(f'(path "{new_path_map["TH2"]}")', after_text)
        self.assertNotIn(f'(path "{path_map["TH1"]}")', after_text)
        self.assertNotIn(f'(path "{path_map["TH2"]}")', after_text)

        # every OTHER ref's path is untouched (spot-check a handful)
        for ref in ("U1", "R20", "R21"):
            self.assertIn(f'(path "{path_map[ref]}")', after_text)

        remaining = {m.group(2) for m in R._NET_STR_RE.finditer(after_text)}
        for old in rename_map:
            self.assertNotIn(old, remaining, f"stray old net name {old!r} left behind")
        for new in rename_map.values():
            self.assertIn(new, remaining)

        after_nets = R._pcbnew_net_names(self.pcb)
        for old in rename_map:
            self.assertNotIn(old, after_nets)
        for new in rename_map.values():
            self.assertIn(new, after_nets)


# --------------------------------------------------------- reconcile_project
def _write_toy_pro(path, netclass_patterns):
    data = {"net_settings": {"classes": [{"name": "Default"}],
                             "netclass_patterns": netclass_patterns}}
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(data, indent=2, sort_keys=True))
    return path


class ReconcileProjectTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cec_pcb_reconcile_test_project_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_membership_restored_via_added_pattern(self):
        pro = _write_toy_pro(
            os.path.join(self.tmp, "toy.kicad_pro"),
            [{"netclass": "Power12V", "pattern": "/SENSEC*"}])
        rename_map = {"/SENSEC1_HI": "/02-sensing/SENSEC1_HI"}

        report = R.reconcile_project(pro, None, rename_map)

        self.assertEqual(report["unresolvable"], [])
        self.assertEqual(len(report["netclass_changes"]), 1)
        self.assertEqual(report["netclass_changes"][0]["action"], "added_explicit_pattern")

        with open(pro, encoding="utf-8") as f:
            data = json.load(f)
        patterns = data["net_settings"]["netclass_patterns"]
        self.assertIn({"netclass": "Power12V", "pattern": "/02-sensing/SENSEC1_HI"}, patterns)

        # membership equality actually holds now under the updated pattern set
        pats = [p["pattern"] for p in patterns if p["netclass"] == "Power12V"]
        self.assertTrue(R._fnmatch_any("/02-sensing/SENSEC1_HI", pats))

    def test_unaffected_pattern_produces_no_changes(self):
        pro = _write_toy_pro(
            os.path.join(self.tmp, "toy.kicad_pro"),
            [{"netclass": "CAN", "pattern": "/CAN_H"}])
        # a rename that has nothing to do with this pattern
        rename_map = {"/FOO": "/leaf/FOO"}
        report = R.reconcile_project(pro, None, rename_map)
        self.assertEqual(report["netclass_changes"], [])
        self.assertEqual(report["unresolvable"], [])

    def test_impossible_equality_raises_and_leaves_file_untouched(self):
        pro = _write_toy_pro(
            os.path.join(self.tmp, "toy.kicad_pro"),
            [{"netclass": "Signal", "pattern": "/02-sensing/*"}])
        before_bytes = open(pro, "rb").read()

        # old name doesn't match; new name accidentally does -- unresolvable
        # by pure pattern addition (no safe additive fix).
        rename_map = {"/FOO": "/02-sensing/FOO"}
        with self.assertRaises(ValueError):
            R.reconcile_project(pro, None, rename_map)

        self.assertEqual(open(pro, "rb").read(), before_bytes,
                          "a raised ValueError must never leave a partial write")

    def test_dru_literal_net_name_rewritten(self):
        pro = _write_toy_pro(os.path.join(self.tmp, "toy.kicad_pro"), [])
        dru = os.path.join(self.tmp, "toy.kicad_dru")
        with open(dru, "w", encoding="utf-8") as f:
            f.write('(version 1)\n\n(rule "toy"\n'
                    '\t(constraint track_width (min 0.5mm))\n'
                    '\t(condition "A.NetName == \'/FOO\'"))\n')

        rename_map = {"/FOO": "/leaf/FOO"}
        report = R.reconcile_project(pro, dru, rename_map)

        self.assertEqual(report["dru"]["changed"], 1)
        with open(dru, encoding="utf-8") as f:
            new_text = f.read()
        self.assertIn("'/leaf/FOO'", new_text)
        self.assertNotIn("'/FOO'", new_text)

    def test_dru_none_path_is_a_noop(self):
        pro = _write_toy_pro(os.path.join(self.tmp, "toy.kicad_pro"), [])
        report = R.reconcile_project(pro, None, {"/FOO": "/leaf/FOO"})
        self.assertEqual(report["dru"], {"changed": 0, "occurrences": []})

    def test_real_eps_dru_has_no_literal_net_names_today(self):
        # Read-only real-world check: every committed .kicad_dru in this repo
        # uses NetClass conditions only (verified by grep, this session) --
        # confirms the DRU path is presently inert on real boards, not just
        # in this synthetic test.
        dru = _find(EPS8PIN, ".kicad_dru")
        pro = _write_toy_pro(os.path.join(self.tmp, "toy.kicad_pro"), [])
        dru_copy = os.path.join(self.tmp, "eps_copy.kicad_dru")
        shutil.copy(dru, dru_copy)
        report = R.reconcile_project(
            pro, dru_copy, {"/DETAMPC1": "/02-sensing/DETAMPC1"})
        self.assertEqual(report["dru"]["changed"], 0)


# --------------------------------------------------------------- drc_parity
@unittest.skipUnless(HAVE_CLI, "kicad-cli not available")
class DrcParityTest(unittest.TestCase):
    """Identity case: DRC run against itself must report equal. This is the
    plumbing sanity check the task calls for ("DRC parity: run on the
    untouched scratch eps copy") -- reconcile_pcb's own round-trip tests
    above separately establish that an ACTUAL rename doesn't perturb
    anything DRC-visible on eps-8pin (no copper there to perturb) or on
    12vhpwr-standard's real copper (pcbnew net-count/name checks in
    Hpwr12vPathRelinkRoundTripTest); this test isolates drc_parity() itself
    from reconcile_pcb so a bug in one is not masked by the other."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cec_pcb_reconcile_test_drcparity_")
        self.board = _copy_board(EPS8PIN, self.tmp)
        self.pcb = _find(self.board, ".kicad_pcb")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_identity_is_equal(self):
        baseline = R.run_drc(self.pcb)
        report = R.drc_parity(self.pcb, baseline)
        self.assertTrue(report["equal"], report)
        self.assertEqual(report["only_before"], {})
        self.assertEqual(report["only_after"], {})
        self.assertEqual(report["before_total"], report["after_total"])
        self.assertGreater(report["before_total"], 0,
                            "fixture should have SOME violation/parity/unconnected entries")

    def test_baseline_from_json_file_path(self):
        baseline = R.run_drc(self.pcb)
        baseline_path = os.path.join(self.tmp, "baseline.json")
        with open(baseline_path, "w", encoding="utf-8") as f:
            json.dump(baseline, f)
        report = R.drc_parity(self.pcb, baseline_path)
        self.assertTrue(report["equal"])

    def test_schematic_parity_flag_detected(self):
        # kicad-cli 10.0.4 finding (this session): `pcb drc --help` DOES
        # advertise --schematic-parity. Pinned so a kicad-cli upgrade/
        # downgrade that drops it is noticed rather than silently degrading.
        self.assertTrue(R.schematic_parity_supported())


# ------------------------------------------------- reconcile_board (the CLI)
@unittest.skipUnless(HAVE_CLI, "kicad-cli not available")
class ReconcileBoardDriverTest(unittest.TestCase):
    """End-to-end plumbing check for the function main() wires up, run
    directly (not through argv) with dry_run=True and baseline_rev="HEAD"
    against the LIVE committed eps-8pin directory -- SAFE: dry_run=True means
    reconcile_pcb/reconcile_project never write, and with baseline==HEAD==the
    current committed tree the rename map must come out empty (netlist_groups
    of the same file against itself), so there is nothing to write even if
    dry_run were off. This is the one test that exercises git_show_tree +
    the full reconcile_board() driver without needing an actual
    flat->hierarchical conversion to exist yet."""

    def test_identity_baseline_yields_empty_rename_map(self):
        report = R.reconcile_board(EPS8PIN, "HEAD", dry_run=True)
        self.assertEqual(report["rename_map"], {})
        self.assertFalse(report["pcb"]["changed"])
        self.assertEqual(report["project"]["netclass_changes"], [])
        self.assertIsNone(report["drc_parity"])  # skipped under dry_run

        # confirm the committed files are untouched
        pcb = _find(EPS8PIN, ".kicad_pcb")
        diff = subprocess.run(["git", "diff", "--", pcb], capture_output=True,
                               text=True, cwd=ROOT).stdout
        self.assertEqual(diff, "", "dry_run must never modify the committed board")


if __name__ == "__main__":
    unittest.main()
