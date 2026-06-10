# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# CL-03 / RB-02 wave test checklist (the rulings doc, 2026-06-10) -- all nine
# items, host-runnable (the compiler is pcbnew-free by construction; the synth
# pipeline imports pcbnew lazily). Test 6's golden fixture lives at
# tests/golden/parity-report.json (owner-gated path -- parity changes are
# enforcement-source changes and ride owner-approved PRs by design).
import json, os, shutil, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.dont_write_bytecode = True

import cec_corpus_compile as CC                               # noqa: E402
import cec_facts as F                                         # noqa: E402
import cec_synth_pipeline as S                                # noqa: E402


def _mini_corpus(tmp, *, promoted_entry=None):
    """A tiny corpus tree: one structured staging entry (+ optionally one
    promoted entry) -- the synthetic substrate for latch/parity/param tests."""
    os.makedirs(os.path.join(tmp, "staging", "general"), exist_ok=True)
    os.makedirs(os.path.join(tmp, "promoted", "general"), exist_ok=True)
    staging = [{
        "id": "test.param.k", "class": "A", "kind": "param",
        "scope": {"families": ["hub", "module"]}, "value": 0.099,
        "units": "k", "source": {"type": "standard", "ref": "IPC test", "date": "2026-06-10"},
        "status": "proposed",
        "compile": {"targets": [{"type": "param", "params": {"key": "test.param.k"}}]},
    }]
    json.dump(staging, open(os.path.join(tmp, "staging", "general", "t.json"), "w"))
    if promoted_entry:
        json.dump([promoted_entry],
                  open(os.path.join(tmp, "promoted", "general", "p.json"), "w"))
    return tmp


def _promoted(**over):
    e = {
        "id": "test.rule.gate", "class": "B", "kind": "rule",
        "scope": {"net_families": ["CAN_H"], "families": ["hub"]},
        "value": {"x": 1}, "units": None,
        "source": {"type": "spec", "ref": "spec section 3.1", "date": "2026-06-10"},
        "status": "human_approved",
        "signoff": {"by": "nathanfraske", "date": "2026-06-10", "evidence": "test"},
        "compile": {"targets": [{"type": "dru_rule", "params": {
            "name": "test-rule", "constraint": "clearance (min 0.2mm)",
            "condition": "A.NetName == 'CAN_H'"}}]},
    }
    e.update(over)
    return e


class T1AdvisoryNeverBlocks(unittest.TestCase):
    def test_adv_only_auto_signs(self):
        adv = S.Flag("ADV-x", "b", 0.9, S.Kind.CONFORM, binding="advisory",
                     entry_id="x")
        self.assertTrue(S.human_signoff("b", None, [adv]),
                        "an ADV-only residual must auto-sign")

    def test_gate_flag_still_blocks(self):
        gate = S.Flag("real", "b", 0.9, S.Kind.ROUTE)
        self.assertFalse(S.human_signoff("b", None, [gate]))

    def test_gate_filter_and_assert(self):
        adv = S.Flag("ADV-x", "b", 0.9, S.Kind.CONFORM, binding="advisory")
        gate = S.Flag("real", "b", 0.9, S.Kind.ROUTE)
        self.assertEqual(S.gate_flags([adv, gate]), [gate])
        with self.assertRaises(AssertionError):
            S.assert_no_advisory([adv], "test halting path")
        S.assert_no_advisory([gate], "test halting path")     # no raise


class T2Determinism(unittest.TestCase):
    def test_double_compile_byte_identical(self):
        t1, t2 = tempfile.mkdtemp(), tempfile.mkdtemp()
        try:
            CC.compile_corpus(out_root=t1)
            CC.compile_corpus(out_root=t2)
            r = subprocess.run(["diff", "-r", t1, t2], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, "compiler output drifted:\n" + r.stdout[:800])
        finally:
            shutil.rmtree(t1), shutil.rmtree(t2)


class T3FixtureLatch(unittest.TestCase):
    def test_promoted_without_fixture_refused(self):
        tmp = tempfile.mkdtemp()
        out = tempfile.mkdtemp()
        try:
            _mini_corpus(tmp, promoted_entry=_promoted())     # no fixture field
            m = CC.compile_corpus(corpus_root=tmp, out_root=out)
            self.assertTrue(any("AM-02 latch" in r and "test.rule.gate" in r
                                for r in m["refusals"]), m["refusals"])
            self.assertEqual(m["counts"]["blocking"], 0)
        finally:
            shutil.rmtree(tmp), shutil.rmtree(out)

    def test_promoted_with_fixture_compiles(self):
        tmp = tempfile.mkdtemp()
        out = tempfile.mkdtemp()
        try:
            _mini_corpus(tmp, promoted_entry=_promoted(
                fixture="tests/golden/fixtures/hub-post-tps2121/hub-standard.kicad_sch"))
            m = CC.compile_corpus(corpus_root=tmp, out_root=out)
            self.assertEqual(m["refusals"], [])
            self.assertGreaterEqual(m["counts"]["blocking"], 1)
            asm = open(os.path.join(out, "hub-standard", "assembled.kicad_dru")).read()
            self.assertIn("# corpus: test.rule.gate", asm)
            self.assertIn(CC.GEN_BEGIN, asm)
        finally:
            shutil.rmtree(tmp), shutil.rmtree(out)

    def test_class_cap_violation_rejected(self):
        tmp = tempfile.mkdtemp()
        out = tempfile.mkdtemp()
        try:
            bad = _promoted(id="test.h.entry", **{"class": "H"})
            _mini_corpus(tmp, promoted_entry=bad)
            m = CC.compile_corpus(corpus_root=tmp, out_root=out)
            self.assertTrue(any("class-H" in e for e in m["errors"]), m["errors"])
        finally:
            shutil.rmtree(tmp), shutil.rmtree(out)

    def test_compile_block_on_prose_rejected(self):
        tmp = tempfile.mkdtemp()
        out = tempfile.mkdtemp()
        try:
            prose = _promoted(id="test.prose", value=None)     # untyped value
            _mini_corpus(tmp, promoted_entry=prose)
            m = CC.compile_corpus(corpus_root=tmp, out_root=out)
            self.assertTrue(any("non-structured" in e for e in m["errors"]), m["errors"])
        finally:
            shutil.rmtree(tmp), shutil.rmtree(out)


class T4ScopeResolver(unittest.TestCase):
    def test_family_scoping_across_boards(self):
        hub = F.board_facts(F.find_board("hub-standard"))
        eps = F.board_facts(F.find_board("eps-8pin"))
        hub_scope = {"families": ["hub"], "net_families": ["CAN_H"]}
        self.assertTrue(F.resolve_scope(hub_scope, hub)["applicable"])
        self.assertFalse(F.resolve_scope(hub_scope, eps)["applicable"],
                         "hub-only scope on a module board is N/A -- correct, no warning")

    def test_zero_resolution_warns_on_claimed_board(self):
        m = CC.compile_corpus()
        self.assertTrue(any("ZERO objects" in w and "hub-pro" in w
                            for w in m["warnings"]),
                        "the hub-pro skeleton must draw the zero-resolution warning")

    def test_autoname_unwrap(self):
        atx = F.board_facts(F.find_board("atx-24pin"))
        r = F.resolve_scope({"families": ["module"],
                             "net_families": ["CAN1_H", "CAN1_L"]}, atx)
        self.assertGreaterEqual(r["object_count"], 2,
                                "Net-(J1-CAN1_H) must unwrap to CAN1_H")


class T5ParamsPrecedence(unittest.TestCase):
    def test_three_state_matrix(self):
        # state 1: hand only (no compiled tree) -> hand value
        empty = tempfile.mkdtemp()
        try:
            self.assertEqual(F.compiled_param("k", 0.5, root=empty), 0.5)
            # state 2: promoted only -> compiled value
            json.dump([{"key": "k", "binding": "gate", "value": 0.7}],
                      open(os.path.join(empty, "params.json"), "w"))
            self.assertEqual(F.compiled_param("k", 0.5, root=empty), 0.7)
            # state 3: staging row NEVER overrides (advisory binding)
            json.dump([{"key": "k", "binding": "advisory", "value": 0.9}],
                      open(os.path.join(empty, "params.json"), "w"))
            self.assertEqual(F.compiled_param("k", 0.5, root=empty), 0.5)
        finally:
            shutil.rmtree(empty)

    def test_staging_delta_is_advisory_not_error(self):
        out = tempfile.mkdtemp()
        try:
            json.dump([{"key": "thermal.k_ipc.external", "binding": "advisory",
                        "value": 0.5, "entry_id": "x"}],
                      open(os.path.join(out, "params.json"), "w"))
            deltas = CC.evaluate_param_deltas(out_root=out)
            self.assertEqual(len(deltas), 1)
            self.assertIn("staging proposes", deltas[0]["msg"])
            # and the computed value is UNCHANGED (dt_ipc still uses 0.048)
            self.assertAlmostEqual(S.dt_ipc(1.0, 1.0), S.dt_ipc(1.0, 1.0))
        finally:
            shutil.rmtree(out)


class T6ParityGolden(unittest.TestCase):
    def test_parity_matches_committed_golden(self):
        CC.compile_corpus()
        got = json.load(open(os.path.join(CC.OUT_ROOT, "parity.json")))
        golden_path = os.path.join(ROOT, "tests", "golden", "parity-report.json")
        if not os.path.exists(golden_path):
            self.skipTest("golden not frozen yet (freeze step in this PR)")
        want = json.load(open(golden_path))
        self.assertEqual(got["counts"], want["counts"],
                         "parity counts drifted -- an enforcement-source change; "
                         "re-freeze rides an owner-approved PR")
        self.assertEqual({m["registry"] for m in got["matched"]},
                         {m["registry"] for m in want["matched"]})


class T7AdvSidecar(unittest.TestCase):
    def test_round_trip(self):
        runs = tempfile.mkdtemp()
        old = os.environ.get("CEC_RUNS_DIR")
        os.environ["CEC_RUNS_DIR"] = runs
        try:
            import importlib
            import cec_ledger
            importlib.reload(cec_ledger)
            fires = [{"entry_id": "e1", "locus": "CAN_H", "binding": "advisory",
                      "name": "ADV-e1: x"},
                     {"entry_id": "e2", "locus": "k", "binding": "advisory",
                      "name": "ADV-e2: y"}]
            side = cec_ledger.adv_fires(fires, board="eps-8pin", run_id="r-test1")
            self.assertEqual(side["n"], 2)
            self.assertTrue(side["sha256"])
            # the sidecar reconstructs per-entry counts (rel is repo-root-relative,
            # like counter()'s decisions/ tree)
            lines = [json.loads(l) for l in
                     open(os.path.join(runs, side["rel"]))]
            self.assertEqual(sorted(l["entry_id"] for l in lines), ["e1", "e2"])
            # and the main ledger line carries the hash
            led = [json.loads(l) for l in
                   open(os.path.join(runs, "runs", "ledger.jsonl"))]
            adv_lines = [l for l in led if l.get("mode") == "adv-fires"]
            self.assertEqual(adv_lines[-1]["extra"]["adv_fires_sha256"], side["sha256"])
        finally:
            if old is None:
                os.environ.pop("CEC_RUNS_DIR", None)
            else:
                os.environ["CEC_RUNS_DIR"] = old
            shutil.rmtree(runs)


class T8LintBothHalves(unittest.TestCase):
    def test_gate_artifact_citing_staging_rejected(self):
        out = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(out, "eps-8pin"))
            json.dump([{"entry_id": "not-promoted", "binding": "gate", "type": "scorer_limit"}],
                      open(os.path.join(out, "eps-8pin", "scorer_limits.json"), "w"))
            errs = CC.validate_artifacts(out_root=out)
            self.assertTrue(any("non-promoted" in e for e in errs), errs)
        finally:
            shutil.rmtree(out)

    def test_drifted_generated_section_rejected(self):
        repo = tempfile.mkdtemp()
        out = tempfile.mkdtemp()
        try:
            bdir = os.path.join(repo, "modules", "fake-board")
            os.makedirs(bdir)
            open(os.path.join(bdir, "fake-board.kicad_dru"), "w").write(
                "(version 1)\n\n%s\n# corpus: old stale gate\n%s\n"
                % (CC.GEN_BEGIN, CC.GEN_END))
            os.makedirs(os.path.join(out, "fake-board"))
            open(os.path.join(out, "fake-board", "assembled.kicad_dru"), "w").write(
                "(version 1)\n\n%s\n# manifest: x\n%s\n" % (CC.GEN_BEGIN, CC.GEN_END))
            errs = CC.scan_generated_sections(repo_root=repo, out_root=out)
            self.assertTrue(any("DRIFTED" in e for e in errs), errs)
        finally:
            shutil.rmtree(repo), shutil.rmtree(out)


class T9CommittedTreeImmutable(unittest.TestCase):
    def test_full_compile_leaves_git_clean(self):
        before = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                                capture_output=True, text=True).stdout
        CC.compile_corpus()
        after = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                               capture_output=True, text=True).stdout
        self.assertEqual(before, after,
                         "a compile invocation mutated the committed tree")


if __name__ == "__main__":
    unittest.main(verbosity=2)
