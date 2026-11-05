"""Board-local policy must be identical across pipeline entry points."""

import json
import os
import sys
import tempfile
import unittest


HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_board_policy as policy  # noqa: E402


class BoardPolicyTest(unittest.TestCase):
    HUB = "hub-standard-rev2"
    HUB_PCB = os.path.join(
        ROOT, "beta", HUB, "candidate", "%s-candidate.kicad_pcb" % HUB)

    def test_name_path_and_archive_hint_resolve_same_contract(self):
        named = policy.load(self.HUB)
        by_path = policy.load(self.HUB_PCB)
        hinted = policy.load("/tmp/archive/board.kicad_pcb",
                             board_hint=self.HUB)
        self.assertEqual(named["fingerprint"], by_path["fingerprint"])
        self.assertEqual(named["fingerprint"], hinted["fingerprint"])
        self.assertEqual(policy.critical_net_selectors(self.HUB), (
            "BLACKOUT_SENSE", "COMP_THRESH", "PWR_FAIL_INT"))

    def test_merge_isolated_from_caller_and_policy(self):
        base = {"nested": {"keep": True}, "critical_route_nets": ["OLD"]}
        merged = policy.merge_params(base, self.HUB)
        merged["nested"]["keep"] = False
        merged["critical_route_nets"].append("MUTATED")
        self.assertTrue(base["nested"]["keep"])
        self.assertEqual(base["critical_route_nets"], ["OLD"])
        self.assertNotIn(
            "MUTATED", policy.params(self.HUB)["critical_route_nets"])

    def test_active_wired_only_policies_override_rf_inference_in_every_entry_point(self):
        for board in ('atx-24pin-rev3', 'hub-standard-rev2', '12vhpwr-standard',
                      'pcie-8pin-2port', 'pcie-8pin-3port', 'eps-8pin-rev3'):
            with self.subTest(board=board):
                merged = policy.merge_params({'respect_antenna_keepout': True}, board)
                self.assertIs(merged['respect_antenna_keepout'], False)
                archive = policy.params('/tmp/renamed/board.kicad_pcb', board_hint=board)
                self.assertIs(archive['respect_antenna_keepout'], False)

    def test_malformed_schema_and_identity_fail_closed(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = os.path.join(directory, policy.POLICY_FILENAME)
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"schema": 2, "board": os.path.basename(directory),
                           "params": {}}, handle)
            with self.assertRaises(policy.BoardPolicyError):
                policy.load(directory)
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"schema": 1, "board": "wrong", "params": {}},
                          handle)
            with self.assertRaises(policy.BoardPolicyError):
                policy.load(directory)

    def test_missing_policy_is_optional_or_explicitly_required(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            self.assertEqual(policy.load(directory), {})
            with self.assertRaises(FileNotFoundError):
                policy.load(directory, required=True)

    def test_renamed_build_artifact_resolves_from_path_identity(self):
        loaded = policy.load(
            os.path.join(ROOT, "build", "probe", self.HUB,
                         "candidate-v7.kicad_pcb"))
        self.assertEqual(loaded["board"], self.HUB)

    def test_legacy_identity_is_an_explicit_alias_not_an_engine_branch(self):
        loaded = policy.load("eps-8pin")
        self.assertEqual(loaded["board"], "eps-8pin-rev3")
        self.assertIn("eps-8pin", loaded["aliases"])

    def test_pcb_path_hint_matches_named_policy_without_relaxing_identity(self):
        named = policy.load(self.HUB)
        for hint in (self.HUB_PCB, os.path.join(ROOT, "beta", self.HUB),
                     os.path.join("beta", self.HUB, self.HUB + ".kicad_pcb")):
            with self.subTest(hint=hint):
                hinted = policy.load("/tmp/archive/board.kicad_pcb", board_hint=hint)
                self.assertEqual(named["fingerprint"], hinted["fingerprint"])

    def test_unresolved_path_hint_cannot_fall_back_to_an_unrelated_subject(self):
        with self.assertRaises(policy.BoardPolicyError):
            policy.load(self.HUB, board_hint="/tmp/not-a-board/board.kicad_pcb")
        with self.assertRaises(policy.BoardPolicyError):
            policy.load(self.HUB, board_hint="not-a-declared-board")

    def test_synthetic_owner_path_and_declared_alias_are_not_product_specific(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            owner = os.path.basename(directory)
            path = os.path.join(directory, policy.POLICY_FILENAME)
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"schema": 1, "board": "synthetic-owner", "aliases": [owner],
                           "params": {"mount_count": 4}}, handle)
            hinted = policy.load("/tmp/renamed/board.kicad_pcb",
                                 board_hint=os.path.join(directory, "candidate", "board.kicad_pcb"))
            self.assertEqual(hinted["params"]["mount_count"], 4)
            self.assertEqual(hinted["fingerprint"], policy.load(directory)["fingerprint"])
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"schema": 1, "board": "misfiled-owner", "params": {}}, handle)
            with self.assertRaises(policy.BoardPolicyError):
                policy.load(self.HUB, board_hint=directory)

    def test_malformed_identity_payload_does_not_crash_registry_lookup(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = os.path.join(directory, policy.POLICY_FILENAME)
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(["not", "a", "policy"], handle)
            self.assertEqual(policy._policy_identifiers(path), ())
            with self.assertRaises(policy.BoardPolicyError):
                policy.load(directory, board_hint=os.path.join(directory, "board.kicad_pcb"))


if __name__ == "__main__":
    unittest.main()
