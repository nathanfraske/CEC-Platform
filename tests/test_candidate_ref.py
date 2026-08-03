"""Teeth for the per-board candidate reference (owner directive 2026-07-25).

The rules under test are the ones that keep the reference TRUSTWORTHY:
a better winner replaces it, a worse one does not, a placement-only winner never
overwrites real copper, and exactly one board file ever lives in the folder.
Each is asserted in BOTH directions -- a test that only proves the happy path
would not have caught a reference silently regressing.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_fresh_wave as w                                # noqa: E402


class CandidateRefTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cec_cand_")
        self._refs_prev = (w._netlist_refs, w._board_refs)
        self.board = "unit-test-board"
        # _candidate_update writes under ROOT/beta/<board>/candidate
        self._root_prev = w.ROOT
        w.ROOT = self.tmp
        os.makedirs(os.path.join(self.tmp, "beta", self.board), exist_ok=True)
        self.cdir = os.path.join(self.tmp, "beta", self.board, "candidate")

    def tearDown(self):
        w.ROOT = self._root_prev
        w._netlist_refs, w._board_refs = self._refs_prev
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- helpers ----------------------------------------------------------
    def _pcb(self, name, text="(kicad_pcb)"):
        p = os.path.join(self.tmp, name + ".kicad_pcb")
        with open(p, "w") as fh:
            fh.write(text)
        for ext in (".kicad_pro", ".kicad_dru"):
            with open(os.path.join(self.tmp, name + ext), "w") as fh:
                fh.write("{}")
        return p

    def _publish(self, name, sort_key, routed=True, text=None):
        src = self._pcb(name, text or f"(kicad_pcb {name})")
        best = {"label": name, "sort_key": list(sort_key),
                "routed": src if routed else None, "drc": 1, "unconnected": 2}
        return w._candidate_update(self.board, src, best)

    def _meta(self):
        with open(os.path.join(self.cdir, "candidate.json")) as fh:
            return json.load(fh)

    def _body(self):
        with open(os.path.join(self.cdir, f"{self.board}-candidate.kicad_pcb")) as fh:
            return fh.read()

    # -- the rules --------------------------------------------------------
    def test_first_publish_creates_reference_with_sidecars(self):
        self.assertIsNotNone(self._publish("w1", (1, 5)))
        self.assertTrue(os.path.isfile(os.path.join(self.cdir, f"{self.board}-candidate.kicad_pcb")))
        for ext in (".kicad_pro", ".kicad_dru"):
            self.assertTrue(os.path.isfile(os.path.join(self.cdir, f"{self.board}-candidate{ext}")),
                            f"missing sidecar {ext} -- the reference would not open with its netclasses")
        self.assertEqual(self._meta()["reason"], "first candidate")

    def test_better_sort_key_replaces(self):
        self._publish("w1", (1, 5))
        self.assertIsNotNone(self._publish("w2", (1, 4)))
        self.assertIn("w2", self._body())
        self.assertEqual(self._meta()["sort_key"], [1, 4])

    def test_worse_sort_key_is_refused(self):
        self._publish("w1", (1, 4))
        self.assertIsNone(self._publish("w2", (1, 9)),
                          "a WORSE winner must not overwrite the reference")
        self.assertIn("w1", self._body())
        self.assertEqual(self._meta()["sort_key"], [1, 4])

    def test_equal_sort_key_is_refused(self):
        self._publish("w1", (2, 2))
        self.assertIsNone(self._publish("w2", (2, 2)))
        self.assertIn("w1", self._body())

    def test_placement_only_never_overwrites_routed(self):
        self._publish("routed1", (5, 5), routed=True)
        # Better key, but no copper: must still be refused.
        self.assertIsNone(self._publish("placed1", (0, 0), routed=False),
                          "a placement-only winner must never clobber real copper")
        self.assertIn("routed1", self._body())
        self.assertTrue(self._meta()["routed"])

    def test_routed_replaces_placement_only_even_on_worse_key(self):
        self._publish("placed1", (0, 0), routed=False)
        self.assertFalse(self._meta()["routed"])
        self.assertIsNotNone(self._publish("routed1", (7, 7), routed=True))
        self.assertIn("routed1", self._body())
        self.assertTrue(self._meta()["routed"])
        self.assertEqual(self._meta()["reason"], "routed beats placement-only")

    def test_exactly_one_board_file_survives(self):
        self._publish("w1", (3, 3))
        # a stale board file left in the folder by any other path
        with open(os.path.join(self.cdir, "leftover.kicad_pcb"), "w") as fh:
            fh.write("(kicad_pcb stale)")
        self._publish("w2", (2, 2))
        pcbs = [f for f in os.listdir(self.cdir) if f.endswith(".kicad_pcb")]
        self.assertEqual(pcbs, [f"{self.board}-candidate.kicad_pcb"],
                         f"exactly one board file must remain, found {pcbs}")

    # -- schematic freshness outranks score --------------------------------
    def _fake_refs(self, want, per_board):
        """Stub the netlist + board ref readers (pcbnew is not on the host)."""
        w._netlist_refs = lambda board: set(want)

        def refs(path):
            for frag, val in per_board.items():
                if frag in str(path):
                    return set(val)
            return None
        w._board_refs = refs

    def test_staler_board_refused_even_with_better_score(self):
        """The 12VHPWR case inverted: the reference carries today's schematic,
        and an older-netlist board scores better. Score must not win."""
        self._publish("postingress", (5, 5))
        # reference (the installed copy) has all 3; the challenger predates U5/F1
        self._fake_refs({"U1", "U5", "F1"},
                        {"candidate": {"U1", "U5", "F1"}, "preingress": {"U1"}})
        self.assertIsNone(self._publish("preingress", (0, 0)),
                          "a board missing current-schematic parts must not become the reference "
                          "just because it scored better")
        self.assertIn("postingress", self._body())

    def test_fresher_board_wins_on_worse_score(self):
        self._publish("preingress", (0, 0))
        self._fake_refs({"U1", "U5", "F1"},
                        {"candidate": {"U1"}, "postingress": {"U1", "U5", "F1"}})
        self.assertIsNotNone(self._publish("postingress", (9, 9)),
                             "a board carrying the current schematic must replace a stale "
                             "reference even on a worse score")
        self.assertIn("postingress", self._body())
        meta = self._meta()
        self.assertEqual(meta["schematic_match"], 1.0)
        self.assertTrue(meta["schematic_exact"])
        self.assertIn("current schematic", meta["reason"])

    def test_equal_freshness_falls_through_to_score(self):
        self._publish("w1", (1, 4))
        self._fake_refs({"U1"}, {"candidate": {"U1"}, "w2": {"U1"}, "w3": {"U1"}})
        self.assertIsNone(self._publish("w2", (1, 9)))       # worse score, same freshness
        self.assertIsNotNone(self._publish("w3", (1, 1)))    # better score, same freshness
        self.assertIn("w3", self._body())

    def test_current_mezz_datum_replaces_obsolete_datum_despite_worse_score(self):
        self._publish("oldmech", (0, 0))
        with mock.patch.object(
                w, "_mezz_contract_status",
                side_effect=lambda path: False if "candidate" in str(path) else True):
            self.assertIsNotNone(self._publish("newmech", (9, 9)))
        self.assertIn("newmech", self._body())
        self.assertTrue(self._meta()["mezzanine_contract_ok"])
        self.assertIn("mechanical datum", self._meta()["reason"])

    def test_obsolete_mezz_datum_cannot_replace_current_datum(self):
        self._publish("currentmech", (9, 9))
        with mock.patch.object(
                w, "_mezz_contract_status",
                side_effect=lambda path: True if "candidate" in str(path) else False):
            self.assertIsNone(self._publish("oldmech", (0, 0)))
        self.assertIn("currentmech", self._body())

    def test_status_refresh_marks_candidate_stale_after_schematic_change(self):
        self._publish("w1", (1, 1))
        self._fake_refs({"U1", "L1"}, {"candidate": {"U1"}})
        meta = w.refresh_candidate_metadata(self.board)
        self.assertEqual(meta["schematic_match"], 0.5)
        self.assertFalse(meta["schematic_exact"])
        self.assertEqual(meta["schematic_status"], "stale")
        self.assertIn("freshness_checked", meta)

    def test_same_reference_with_changed_footprint_is_stale(self):
        want = {
            "C50": ("2u2", "C_0603_1608Metric", (("1", "/SS"), ("2", "GND"))),
        }
        have = {
            "C50": ("2u2", "C_0402_1005Metric", (("1", "/SS"), ("2", "GND"))),
        }
        w._board_refs = lambda _path: have
        self.assertEqual(w._schematic_match("candidate.kicad_pcb", want), 0.0)

    def test_same_reference_with_changed_pin_net_is_stale(self):
        want = {
            "U5": ("TPS2121RUXR", "RUX0012A", (("3", "GND"),)),
        }
        have = {
            "U5": ("TPS2121RUXR", "RUX0012A", (("3", "/IN2"),)),
        }
        w._board_refs = lambda _path: have
        self.assertEqual(w._schematic_match("candidate.kicad_pcb", want), 0.0)

    def test_netlist_freshness_excludes_nonphysical_power_symbols(self):
        net = self._pcb("dummy-net", text="netlist placeholder")
        parsed = SimpleNamespace(
            comps={
                "U1": SimpleNamespace(value="IC", footprint="lib:IC"),
                "PWR201": SimpleNamespace(value="GND", footprint=""),
            },
            nets={"GND": [("U1", "2"), ("PWR201", "1")]},
        )
        cfg = SimpleNamespace(net=net)
        with mock.patch.object(w.csp.Config, "load", return_value=cfg), \
                mock.patch.object(w.csp, "_ensure_netlist_path", return_value=net), \
                mock.patch.object(w.csp.Netlist, "from_file", return_value=parsed):
            signatures = w._netlist_refs("unit-test-board")
        self.assertEqual(set(signatures), {"U1"})

    def test_unknown_board_is_never_invented(self):
        best = {"label": "x", "sort_key": [1], "routed": None}
        src = self._pcb("orphan")
        self.assertIsNone(w._candidate_update("no-such-board", src, best))
        self.assertFalse(os.path.isdir(os.path.join(self.tmp, "beta", "no-such-board")),
                         "must not create a board directory that does not exist")

    def test_missing_source_is_a_noop(self):
        self.assertIsNone(w._candidate_update(self.board, None, {"sort_key": [1]}))
        self.assertIsNone(w._candidate_update(self.board, "/nonexistent.kicad_pcb",
                                              {"sort_key": [1]}))
        self.assertFalse(os.path.isdir(self.cdir))


if __name__ == "__main__":
    unittest.main()
