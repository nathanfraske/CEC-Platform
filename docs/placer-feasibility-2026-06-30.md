# Control-axes / intent-driven PLACER feasibility (2026-06-30)

Follow-on to the router study (`docs/router-feasibility-2026-06-30.md`), which found routing is
already solved and **placement is the real wall** (machine placers stall at corridor_cross=15-24
where a human hits cc=6 in minutes). This study asks: does applying the same control-axes /
intent + differential-oracle philosophy to the PLACER actually crack that wall? Six fronts.

## Verdict: CONDITIONAL GO — as a HUMAN-ASSIST capture surface graded by a real route-oracle, NOT a black box that "cracks" the min-cut

All six fronts converge on GO-with-scope (none NO-GO). But the condition is sharp and has three
non-negotiable parts:

1. **Add the one thing the prior attempt lacked: a GLOBAL, structure-first PARTITION** (peripherals
   to a half-plane, each INA into its band) enforced as proactive HARD containment, **driven by an
   AGENT** — not a re-weighted local simulated-anneal. Re-skinning the existing anneal with intent
   verbs will reproduce the documented cc=8-24 stall.
2. **The accept gate is the REAL post-route conjunction** — `kelvin_ok AND diffpair_ok AND
   drc-finishing-only AND foreign_on_pour==0 AND thermal-in-budget` — never HPWL/area, never
   corridor_cross alone. (kelvin_ok+DRC is a documented false summit at max_T ~181-300 C.)
3. **The autonomy claim is UNPROVEN and must be the milestone's primary, falsifiable test** — that
   an AGENT finds the intents a HUMAN found by hand this session, reliably, without seeding.

Honest ceiling: this reliably REACHES the per-board analytic floor (eps cc=6, channel-aware=0,
pour-clean) and escalates genuine density walls fast. It does **not** drive corridor_cross to 0 or
beat a topological/capacity floor — those are real and separate.

## The finding that matters most: this was already tried, and it stalled

A corridor-aware constructive reseed (min-cut rank term + spine seed + hard veto + SA domain cost)
was **built and 24-agent-audited on 2026-06-14** — and stalled at cc=8 best / 14-24 typical. Its
sub-floor "win" was a **measurement artifact on an illegal inflated-band placement**; the work
pivoted away and the nightly loop still runs nudge-only `cec_place.refine`. So a re-weighted anneal
with nicer verbs is a known dead end. The differentiator MUST be (a) **agent-driven global proactive
partition** (not reactive per-part evicts, not SA jitter) and (b) **route-oracle grading** (not
corridor_cross optimization). If the build reduces to a re-weighted anneal, kill it.

## The central risk: RELOCATION, not solution

An intent surface decomposes the NP-hard global min-cut into local verifiable commitments — but it
does **not solve** it. It **moves the solver to the agent.** A human found the right intents this
session; whether an agent does, reliably, without seeding, is the open question. Two more structural
causes the objective fix alone does NOT close: the **search** (coordinated cross-board discrete moves
that continuous SA reaches only by luck), and the need for a structure-aware representation (deferred).

So the bet is precisely: *can agentic fan-out over intent orderings, graded by a route-oracle, find
what the human finds?* If yes → a real autonomous placer for our boards. If no → you still ship a
**verifiable human-assist tool** (human authors the partition, machine legalizes, oracle grades) —
which is itself a clear win over the stalling anneal. Either way it's worth building; the milestone
must say which one we got.

## Recommended path (defer the engine rewrite)

> **STATUS 2026-06-30:** SLICE 1 is BUILT. (a) route-oracle grader = `route_oracle_grade` /
> `adjudicate_candidates` in cec_synth_pipeline (commit f73cace2, verified: eps-n2 grades tier-0
> clean, the lower-HPWL-but-broken eps-widegap-m grades tier-1 fail — the oracle inverts the proxy,
> correctly). (b) intent-compiler = `scripts/cec_placement_session.py` (`PlacementSession`) over a
> NEW gated `bounds` HARD-containment lever in `legalize_pack`/`synth_one` (partition=None PROVEN
> byte-identical → golden-safe). The partition is the proactive global lever the 2026-06-14 anneal
> lacked, graded by the oracle not corridor_cross. tests/test_placement_session.py 5/5 (inertness,
> hard-containment, teeth=forced-box). NEXT: SLICE 2 (wire `reseed_intent` into cec_loop) + the
> AUTONOMY fan-out (`autonomy_search()` harness exists; plug in an agent-proposed intent set).

- **SLICE 1 (paired, cheapest leverage):**
  - **(a) The route-oracle grader** — `confirm_winner` is genuinely ABSENT today. Build it in
    cec_synth_pipeline: candidate → derive_power_pours → corridor/kelvin keepouts → ONE
    `cec_fr.route_once(passes~8, opt~12)` on top-k → `cec_score` + `_chk_pour_integrity` + thermal →
    this REPLACES HPWL/area as the selection key. This is the single highest-value piece and is
    worth doing regardless of the rest.
  - **(b) A thin declarative `PlacementSession` / intent-compiler** (~few hundred lines, NO new
    engine) over primitives that ALREADY exist: `seat_kelvin`→tighten/spine-seed; `reserve_corridor`
    →corridor-model band + veto/keepout; `evacuate_foreign`→corridor-evict; `group`→auto_cluster;
    `mount_pattern`→place_mechanical; `assign(ref,region,face)`→the partition tile; with
    snapshot/rollback and the sense-IC fence (seats/keepouts HARD, only free parts move). The
    differentiator vs 2026-06-14: the agent issues a GLOBAL partition as first-class proactive
    containment, and grading is the route-oracle.
- **SLICE 2:** wire it into cec_loop as a `reseed_intent` candidate; make `_score` read the oracle
  gate (closes the reconciliation debt — nightly still runs nudge-only refine).
- **SLICE 3:** a floor-aware STOP (compute the analytic in-plane min-cut per board so it halts at
  cc=6, not an unreachable 0) + residual-area infeasibility detection (fast lever-2 escalation) +
  emit a LAYER intent for the cc residual (hand to the router's layer-assignment lever).
- **DEFER:** structure-aware B*-tree/SMT representation (research-grade), RL/analytic-GPU engines
  (overkill at ~45 parts), the 12VHPWR shared-bus variant, any PCIe-3port density "solution" (that
  is a lever-2 board-resource ratification). Keep classical SA as the lever-1 fallback for the
  structure-less Hub boards where HPWL genuinely IS the objective.

## First milestone & metric (days via fan-out)

Autonomous intent-to-gate on the 1-2 cable family (eps + PCIe-2port): an AGENT (not a human)
proposes structure-first intent — partition peripherals (ESP/CAN/USB/RJ45) to the right half-plane,
seat each INA against its shunt inner edge with the ~1.4 mm back-off, reserve each J_IN→shunt→J_OUT
corridor — the compiler legalizes with the fence, the channel-aware/kelvin/edge proxies prune to
top-k, the route-oracle grades the survivors. Fan out over intent ORDERINGS/GROUPINGS with
snapshot/rollback. PCIe-3port must gate clean OR emit a fast, specific lever-2 escalation naming the
binding pour/signal — not a silent cc=15-24 stall.

**Metric (falsifiable, graded only against the real post-route gate):** (1) eps + PCIe-2port reach
the FULL accept gate autonomously, matching the hand-intent session, no grow. (2) **PRIMARY AUTONOMY
METRIC** — across N fan-out intent variations, at least one reaches the gate WITHOUT a human
authoring the partition; if only human-authored intents pass, the honest result is "verifiable
assist tool, autonomy unproven." (3) PCIe-3port: gate-clean OR fast honest infeasibility escalation.
**Guards:** the grader can never pass what the real route fails (true by construction); re-validate
the channel-aware proxy on FORMED corridors (it reads false-clean 0 on a degenerate band — the
retracted Phase-1a artifact) with a labeled confusion matrix on ≥2 boards before trusting it to
prune; make the CL-13 outcome-label chain FIRE (0 labels in 160 runs today).

## Bottom line

Placement IS the leverage, confirmed. But the honest framing is **capture the human, don't assume
you replace them**: the intent surface relocates the global min-cut to the agent rather than solving
it, and the exact "smarter anneal" version has already failed. The win — and it's a real one — is
the **route-oracle grader** (a genuine missing piece worth building on its own) plus a thin
intent-compiler that lets an agent (or, falling back, a human) drive structure-first placement with
machine legalization and oracle grading. Whether the AGENT achieves what the human did is the
unproven crux, and the milestone is designed to answer exactly that.

*Full per-front assessments in the workflow transcript (wf_fa9bfa0f-29b).*
