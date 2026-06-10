#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Unit tests for cec_policy (CL-10 loader + DF-05/07 anti-ratchet firewall + bound clamp).
# Dependency-free (no broker, no GPU, no pcbnew) -- runs on the host AND in the container:
#
#   python3 -m unittest tests.test_cec_policy -v
import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import cec_policy as P  # noqa: E402


class TestPolicyLoads(unittest.TestCase):
    def test_repo_policy_validates(self):
        """The committed cec-policy.json must load clean -- this is the CI gate."""
        policy = P.load_policy()
        self.assertTrue(P.assert_loadable(policy))

    def test_hash_is_stable(self):
        h1 = P.policy_sha256()
        h2 = P.policy_sha256()
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 64)


class TestBindingGuards(unittest.TestCase):
    def setUp(self):
        self.policy = P.load_policy()

    def test_license_false_on_load_bearing_refuses(self):
        pol = copy.deepcopy(self.policy)
        pol["bindings"]["worker"]["license_cleared"] = False
        with self.assertRaises(P.PolicyError) as cm:
            P.assert_loadable(pol)
        self.assertIn("license_cleared:false", str(cm.exception))

    def test_failed_gate_on_load_bearing_refuses(self):
        pol = copy.deepcopy(self.policy)
        pol["bindings"]["analyst"]["eval_gate"]["status"] = "failed"
        with self.assertRaises(P.PolicyError) as cm:
            P.assert_loadable(pol)
        self.assertIn("eval_gate", str(cm.exception))

    def test_absent_gate_on_NON_load_bearing_is_fine(self):
        """extractor/verifier/frontier/vision-judge carry absent gates by design and must
        NOT refuse the night (they simply can't be used load-bearing)."""
        P.assert_loadable(self.policy)  # repo policy already has absent gates on those roles

    def test_promoting_absent_gate_role_to_load_bearing_refuses(self):
        pol = copy.deepcopy(self.policy)
        pol["roles"]["extractor"]["load_bearing"] = True
        with self.assertRaises(P.PolicyError):
            P.assert_loadable(pol)


class TestAntiRatchetFirewall(unittest.TestCase):
    def setUp(self):
        self.banned = P.banned_fields(P.load_policy())

    def test_banned_field_as_key_is_caught(self):
        cfg = {"bandit": {"reward": {"acceptance_rate": 0.3}}}
        with self.assertRaises(P.PolicyError):
            P.assert_no_banned_reward_signals(cfg, self.banned, label="bandit reward")

    def test_banned_field_as_value_is_caught(self):
        cfg = {"reward_signal": "promotion-likelihood"}
        with self.assertRaises(P.PolicyError):
            P.assert_no_banned_reward_signals(cfg, self.banned)

    def test_consensus_agreement_banned(self):
        cfg = {"weights": {"consensus_agreement": 1.0}}
        with self.assertRaises(P.PolicyError):
            P.assert_no_banned_reward_signals(cfg, self.banned)

    def test_clean_reward_config_passes(self):
        cfg = {"reward": {"grade_1_physical": 1.0, "grade_2_deterministic": 0.4}}
        P.assert_no_banned_reward_signals(cfg, self.banned)  # no raise

    def test_prose_is_not_a_false_positive(self):
        """Equality on normalized tokens, never substring: a sentence containing 'rate'
        must not trip the firewall."""
        cfg = {"climb_gate_metric": "routing-attributed failure rate at target"}
        P.assert_no_banned_reward_signals(cfg, self.banned)  # no raise

    def test_repo_policy_has_no_banned_references_outside_denylist(self):
        pol = P.load_policy()
        hits = P.scan_banned(pol, P.banned_fields(pol), _skip_paths=("reward.banned_fields",))
        self.assertEqual(hits, [], f"unexpected banned-field references: {hits}")


class TestClamp(unittest.TestCase):
    def setUp(self):
        self.policy = P.load_policy()

    def test_clamp_high(self):
        # route_seeds max is 24 in the repo policy
        self.assertEqual(P.clamp(self.policy, "route_seeds", 999, log=False), 24)

    def test_clamp_low(self):
        self.assertEqual(P.clamp(self.policy, "route_seeds", 0, log=False), 1)

    def test_in_bounds_unchanged(self):
        self.assertEqual(P.clamp(self.policy, "route_seeds", 8, log=False), 8)

    def test_unknown_knob_raises(self):
        with self.assertRaises(P.PolicyError):
            P.clamp(self.policy, "no_such_knob", 1, log=False)


if __name__ == "__main__":
    unittest.main()
