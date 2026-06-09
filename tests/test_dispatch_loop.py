#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Unit tests for the cec_dispatch agent_route edge branches (punchlist R-08) and the
# R-01 per-seed params spread. Uses the request_fn injection hook -- no Freerouting,
# no kicad-cli. NEEDS pcbnew importable (cec_dispatch imports cec_score), so run it
# inside the cec/routing:kicad10 container or on a box with KiCad 10 python bindings:
#
#   docker compose -f docker/compose.yaml run --rm --no-deps routing \
#       bash -lc 'cd /workspace && python3 -m unittest discover -s tests -v'
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import cec_dispatch as d  # noqa: E402


def _cm(seed, **kw):
    base = dict(seed=seed, params={"passes": 8, "opt_time": 12, "threads": 1},
                board=f"/tmp/cand_{seed}.kicad_pcb", drc=0, unconnected=0,
                kelvin_ok=True, diffpair_ok=True, gates_pass=True, tracks=100, vias=10,
                drc_types={}, drc_loci=[], unconn_nets=[])
    base.update(kw)
    return d.CandidateMetrics(**base)


def _tier(script):
    """A scripted tier: pops the next Verdict on each call."""
    seq = list(script)

    def decide(ctx):
        return seq.pop(0)
    decide.tier_name = "scripted"
    return decide


class AgentRouteEdges(unittest.TestCase):
    def test_accept_with_no_candidates_coerces_to_escalate(self):
        """R-08 branch 1: 'accept' against an empty candidate list must NOT return None as
        if accepted -- it escalates, and the coercion is recorded in the log."""
        t0 = _tier([d.Verdict("accept", reason="hallucinated accept")])
        t1 = _tier([d.Verdict("escalate", reason="give up")])
        best, log = d.agent_route("x.kicad_pcb", tiers=[t0, t1], budget=1,
                                  request_fn=lambda p, s: [], verbose=False)
        self.assertIsNone(best)
        self.assertEqual(log[0].get("note"), "accept-with-no-candidates coerced to escalate")
        self.assertEqual(len(log), 2)        # the loop moved UP a tier, not out

    def test_unknown_seed_accept_falls_back_with_note(self):
        """R-08 branch 2: an accept naming an unknown seed uses the best candidate but the
        fallback is logged so the tier's stated intent is not lost."""
        cands = [_cm(0), _cm(1, drc=2)]
        t0 = _tier([d.Verdict("accept", seed=99, reason="names a ghost seed")])
        best, log = d.agent_route("x.kicad_pcb", tiers=[t0], budget=1,
                                  request_fn=lambda p, s: list(cands), verbose=False)
        self.assertIsNotNone(best)
        self.assertEqual(best.seed, 0)
        self.assertIn("seed fallback", log[0].get("note", ""))

    def test_budget_coerced_escalate_is_recorded(self):
        """R-08 branch 3: request_more with budget 0 is coerced to escalate AND the log says
        the tier asked for more -- the stated intent survives."""
        t0 = _tier([d.Verdict("request_more", params={"opt_time": 50}, reason="more!"),
                    d.Verdict("request_more", params={"opt_time": 99}, reason="MORE!")])
        t1 = _tier([d.Verdict("escalate", reason="human")])
        cands = [_cm(0, gates_pass=False, kelvin_ok=False)]
        best, log = d.agent_route("x.kicad_pcb", tiers=[t0, t1], budget=1,
                                  request_fn=lambda p, s: list(cands), verbose=False)
        self.assertIsNone(best)
        coerced = [e for e in log if e.get("note") == "budget-coerced escalate (tier requested more with budget 0)"]
        self.assertEqual(len(coerced), 1)
        # and the first request_more (budget 1 -> 0) actually changed the params
        self.assertEqual(log[1]["params"]["opt_time"], 50)


class SpreadParams(unittest.TestCase):
    def test_multi_seed_spread_resolves_distinct_opt_times(self):
        """R-01: a single params dict expands to a 0.5x..1.5x opt_time spread, recorded
        per seed (FR is deterministic; constant params = identical candidates)."""
        resolved = d._spread_params({"passes": 5, "opt_time": 10, "threads": 1}, (0, 1, 2, 3))
        ots = [resolved[s]["opt_time"] for s in (0, 1, 2, 3)]
        self.assertEqual(ots, [5, 8, 12, 15])
        self.assertTrue(all(resolved[s]["passes"] == 5 for s in resolved))

    def test_single_seed_keeps_params_untouched(self):
        resolved = d._spread_params({"passes": 5, "opt_time": 10}, (0,))
        self.assertEqual(resolved[0], {"passes": 5, "opt_time": 10})


if __name__ == "__main__":
    unittest.main()
