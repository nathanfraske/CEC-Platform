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


if __name__ == "__main__":
    unittest.main()
