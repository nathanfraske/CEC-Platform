"""Retrospective lesson 7 gate (goldens-first): re-score the 4 captured SENSEC2 rounds through
the pour-aware, gate-gated scorer (cec_score.objective_v2) and require ROUND 1 to win.

The live run rode its DRC proxy into a physically worse board (round 4: best DRC=5, worst pours,
-21% sense copper). The human and the zone-copper table both pick round 1 (intact pours, worst
DRC). With the fixed scorer the loop must agree. Data = the merged-to-main validation packet.
Pure-python (no pcbnew); host-runnable.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import cec_score                                              # noqa: E402

RUN = os.path.join(ROOT, "docs", "fullstack-run-2026-06-11-validation")


def _load_rounds():
    meas = {}
    with open(os.path.join(RUN, "measurement.jsonl")) as fh:
        for line in fh:
            if line.strip():
                r = json.loads(line)
                meas[r["round"]] = r
    rounds = []
    for n in sorted(meas):
        facts = json.load(open(os.path.join(RUN, "vision", f"pour-r{n:03d}.json"))).get("facts", {})
        islands_excess = sum(max(0, (v.get("islands", 1) or 1) - 1)
                             for v in facts.values() if isinstance(v, dict))
        sense_copper = sum((v.get("area_mm2", 0) or 0)
                           for v in facts.values() if isinstance(v, dict))
        rounds.append({"round": n, "gates_pass": meas[n]["gates_pass"], "drc": meas[n]["drc"],
                       "islands_excess": islands_excess, "sense_copper": round(sense_copper, 2)})
    return rounds


def _cost(r):
    # base mimics the old soft cost (≈1000*DRC) so the test proves the gate-gating, not the base.
    return cec_score.objective_v2(gates_pass=r["gates_pass"], drc=r["drc"],
                                  islands_excess=r["islands_excess"],
                                  sense_copper=r["sense_copper"], base=1000.0 * r["drc"])


def test_round1_wins_pour_aware_scorer():
    rounds = _load_rounds()
    assert len(rounds) == 4, f"expected 4 captured rounds, got {len(rounds)}"
    costs = {r["round"]: _cost(r) for r in rounds}
    winner = min(costs, key=costs.get)
    assert winner == 1, f"round 1 must win the pour-aware scorer; costs={costs}"


def test_drc_not_credited_while_failing():
    """Round 4 has the best DRC (5) but the worst pours; it must NOT outrank round 1."""
    rounds = {r["round"]: r for r in _load_rounds()}
    c1, c4 = _cost(rounds[1]), _cost(rounds[4])
    assert c1 < c4, f"DRC must not buy rank while gates fail: c1={c1} c4={c4}"


def test_gatepass_outranks_gatefail():
    """Any gate-passing board must rank below every gate-failing one regardless of pours."""
    failing = cec_score.objective_v2(gates_pass=False, drc=0, islands_excess=0, sense_copper=400.0)
    passing = cec_score.objective_v2(gates_pass=True, drc=4, islands_excess=3, sense_copper=100.0,
                                     base=4000.0)
    assert passing < failing


def test_copper_cannot_buy_rank_between_passing():
    """Review item 1: copper area must NOT reorder two gate-passing candidates (no proxy pressure
    in the PR that exists to kill proxy pressure). Same base + intact pours, differing only in
    sense copper -> identical cost."""
    a = cec_score.objective_v2(gates_pass=True, drc=0, islands_excess=0, sense_copper=200.0,
                               base=5000.0)
    b = cec_score.objective_v2(gates_pass=True, drc=0, islands_excess=0, sense_copper=400.0,
                               base=5000.0)
    assert a == b, f"copper area must not buy rank among passing boards: {a} vs {b}"


if __name__ == "__main__":
    test_round1_wins_pour_aware_scorer()
    test_drc_not_credited_while_failing()
    test_gatepass_outranks_gatefail()
    rounds = _load_rounds()
    print("round costs:", {r["round"]: round(_cost(r), 1) for r in rounds})
    print("scorer pour-integrity fixture: round 1 wins, DRC not credited while failing — PASS")
