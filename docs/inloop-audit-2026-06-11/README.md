# In-loop self-correcting audit experiment (2026-06-11)

**Permanent, session-loss-resilient record.** If the originating agent session is lost,
a new agent can resume from this file. Everything here is on WSL ext4 (the repo), NOT
`/tmp` (which already ate the first V4 traces once).

Branch: `claude/corpus-experiential-intake`. Owner: nathanfraske.

---

## 1. What this is (the owner's reframe, 2026-06-11)

Started as: re-run the FR-04 blind-vs-informed routing bake-off on the corrected field,
wire the corpus to the model tiers, and do a 7h overnight directed-routing run.

Reframed by the owner mid-session into a **research experiment**:

> A deep auditor, run BLIND (raw data, no corpus), independently re-derived exactly the
> issues that previously needed a human in the loop (signal carved through the GND plane;
> the scorer not pricing it). If such an auditor runs **in-loop** and its findings are
> compiled back into the **manager and scorer tiers mid-run**, does the loop
> **(a) converge to a degenerate local minimum** (it games its own auditor — penalties
> inflate while the physical metrics plateau / one board repeats), or
> **(b) produce genuinely usable corpus entries** (distinct, sourced, ratifiable findings
> that actually move kelvin / plane-mm / drc)?

Owner design choices (locked this session):
- **Auditor seat = HYBRID**: a fast seat audits *every round* (Sonnet and/or gpt-oss-120b),
  V4 (deepseek-v4-flash / cec-manager-max) does a deep checkpoint every ~8th round.
- **Injection surface = BOTH** scorer weights AND manager rules.
- **Guardrail (non-negotiable, from CLAUDE.md "human-ratification boundary, SET IN STONE"
  + DF-05 anti-ratchet):** injections are **additive-only** (may add/raise a penalty or add
  a rule; may NEVER lower a weight or relax a ratified bound) and **advisory** — every
  finding is logged as a DF-01 / PC-03 *ratification candidate*, never auto-promoted. The
  human ratifies in the morning. This guardrail is also the instrument that makes the
  local-minima-vs-usable question measurable.
- **Also run Sonnet independently** on the same blind judge (no frontier model) to compare
  against V4 — done, see §3.

---

## 2. The originating finding (FR-04, owner-ratified earlier)

The free (blind) router beat the manager-directed (informed) router on the scorer's
objective (~4x) — but only because the free arm carved **61.7mm of /I2C_SDA + 45.0mm of
/I2C_SCL through the In1 GND plane** (return-path destruction the scorer didn't price).
The directed arm cut plane-layer I2C to 21.9/39.2mm via a B.Cu corridor — it delivered on
its actual dimension; the *contract was mispriced*. Owner verdict: "the manager actually
won this round." Fix = price the dimension + deny planes to the router, then re-settle.

**Landed this session (the fix the auditors independently re-derived):**
- `cec_fr.py` — LAYER POLICY: detected plane layers exported `(type power)` so FR won't
  route signals on them, + import-side strip of any plane-layer track. Env `CEC_FR_PLANE_POLICY`
  (default on). Verified: EPS plane layers `['GND','12V']` → denied; routed `plane_signal_mm=0`.
- `cec_score.py` — prices `plane_signal_mm` (per-net + total) at `plane_mm=50/mm` in the
  objective; surfaced on `Metrics`.
- `cec_fr02.py` — `clean_orphan_stubs` now TRIMS dangling spur tails (the 9× `track_dangling`),
  not just absorb/remove (`_end_connected` both-endpoint test).
- `cec_facts.py` — `corpus_briefing(board)`: assembles the routing/layer/plane-relevant
  ratified rule subset (63 rules for eps-8pin) + stackup facts + compiled DRU.
- `cec_judge_local.py` + `cec_router.py` — corpus WIRED to both tiers: in-loop manager sees
  `plane_signal_mm` + HARD RULE 5; out-of-loop reviewer gets `ratified_design_rules` +
  conformance dimension. Gated by `CEC_CORPUS_BRIEFING` (default on).
  Verified: FR-02 fixtures 10/10, scribe tests 8/8, imports clean.

---

## 3. Competence finding — V4 vs Sonnet, both BLIND (no corpus, no frontier model)

Traces: `traces/v4-blind.{reasoning.txt,answer.md,trace.json}`, `traces/sonnet-blind.answer.md`.

**V4 (deepseek-v4-flash, local 284B MoE, ~4 tok/s):** GENUINELY THINKING, not looping, not
gibberish. 6-gram repetition max ×2 over 1,774 unique 6-grams; self-corrects mid-trace
("So B increased ratlines? *Wait:*..."). At the 6400-token cap it OVERRAN (empty content);
at 14000 it converged — 2,560 reasoning tokens + a structured 4,523-char answer in 877s
(~15 min). **Unbounded-thinking verdict: beneficial — it needs ~4-5k tokens to land; the
6400 overrun was a budget-split artifact, not incompetence.** Blind, it re-derived the WHOLE
FR-04 finding AND proposed *exactly* the implemented fix: "a layer-specific weight (e.g.,
0 for F.Cu/B.Cu, 100 for GND)" ≈ `plane_mm=50/mm`.

**Sonnet (Claude mid-tier sub-agent, ~41s):** Convergent core (GND-plane carving is the
dominant scorer-invisible flaw; price GND-mm "on par with a kelvin gate failure"), plus
sharper independent calls: (a) credits ARM B's plane-integrity intent more — lands closer
to the owner's override-up; (b) diagnoses /THRESH + /DETC2 as **placement-class blockage**,
not routing (independently matches the GR-02 finding); (c) flags dangling stubs as active
stub-antenna hazards needing a pre-check (≈ the `clean_orphan_stubs` trim + `force_protect`).

**Read:** both seats are viable in-loop auditors; they converge on the core and contribute
complementary detail, so the loop won't merely echo one model. V4 = deep checkpoint
(slow, owner-gated, opt-in `CEC_VLLM_REVIEWER_MODEL=cec-manager-max`); Sonnet/gpt-oss = fast
per-round seat.

---

## 4. Status / what is built

- [x] Fixes landed (§2), verified in the `cec/routing:kicad10` container.
- [x] V4 + Sonnet blind judges run + persisted (§3).
- [x] `scripts/cec_overnight_directed.py` — directed-routing overnight base with Pareto-
      frontier finalist selection (split arch: route+score in-container worker via
      `docker compose exec routing ... --route-one`; review on host. CORRECTION 2026-06-11:
      the container CAN reach the broker — the earlier "firewall gap" was `curl` missing
      from the routing image, exit 127 misread as unreachable; verified with python3 urllib.
      The split stays as a design choice). Worker leg VERIFIED:
      one round routed directed (7 stubs, 5 absorbed, 2 trimmed), `plane_signal_mm=0`,
      DecisionLog archived. KNOWN ISSUE: a single FR pass at low `passes` does not close the
      Kelvin gate (drc=27, kelvin_ok=false) → the in-loop driver must ADAPT effort (manager
      `repair` → bump passes) to reach gate-passing boards.
- [x] `scripts/cec_inloop_audit.py` — THE EXPERIMENT. In-loop self-correcting orchestrator (§5).
      Shakeout (2 rounds) PASSED: Sonnet self-persisted findings, proposed `kelvin_unrouted:200`
      penalty + 2 manager rules (all additive-accepted), effort adapted (passes 18→24→30), measurement
      + DF-01 candidates produced. Guardrail verified (self-test caught Sonnet's sign-confused
      `weight:-0.8` "would reward the metric" → rejected). Shakeout artifacts archived under `shakeout/`.
- [x] **7h run LAUNCHED 2026-06-11 03:04 CT** (PID 140309, `nohup ... > run.log`). Sonnet-every-round;
      V4 checkpoints opportunistic+probe-only (V4 UNLOADED for the night to free ~160GB host RAM for
      the WSL2 routing container — broker `POST /broker/stop?model=deepseek-v4-flash` → `running=False`,
      which also validated the broker's previously-untested fixed stop-leg). So the night is Sonnet-only;
      the V4 hybrid component is the **morning pass** (§5a below).
- [ ] **Morning pass (do this):** (a) re-load V4 (`curl -s localhost:8080/v1/models` then a warm
      request, or just call it — broker auto-starts) and run a V4 **deep checkpoint on the night's
      Pareto finalists** (`morning-bundle.json` → `pareto_front`) for the hybrid deep view;
      (b) read `morning-bundle.json` `convergence_verdict` + `usable_candidates` and **ratify or reject**
      each (the DF-01 candidates are in the ledger `inloop-audit-candidate`); (c) commit the run artifacts.

### V4 / DeepSeek resource plan (the standing answer)
V4 pins ~160GB of the 191.5GB host RAM (mandatory exclusivity hack), drawn from the same pool the WSL2
routing container uses. **It cannot stay resident during a 7h routing run** (host settles ~3GB free with
V4 alone; routing's few GB would thrash). Plan: **unload V4 for the run**; the loop's V4 checkpoint is
**probe-only** (never cold-starts it; skips+logs if down). Hybrid V4 depth is delivered as a **bracketing
deep pass** (a few now if warm + the morning pass on finalists), not live every 8th round.

---

## 5. The in-loop driver design (`cec_inloop_audit.py`)

Host orchestrator, deadline-bounded. Per round:
1. **Route** a directed candidate in-container at the current adaptive effort
   (`cec_overnight_directed.route_one_worker` via compose-exec; host passes `--passes/--opt-time`).
2. **Live objective** = base `cec_score.objective` + Σ injected additive penalties over the
   record's metric keys (incl. derived `kelvin_unrouted`, `gate_fail`, `plane_signal_mm`).
3. **Manager verdict** (fast seat) on the candidate under the *current injected manager rules*
   → accept / repair / escalate. `repair` bumps next-round passes (the adaptation that should
   close Kelvin over rounds).
4. **Audit** — fast seat every round (Sonnet or gpt-oss-120b), V4 deep checkpoint every 8th —
   returns structured findings: `{issue, proposed_scorer_penalty:{metric,weight,rationale}?,
   proposed_manager_rule?, severity}` (schema-constrained; V4 via the
   `traces/v4_judge_lib.py` big-budget + miner→scribe pattern).
5. **Inject** — `apply_findings`: additive-only (guardrail refuses any lower-a-weight /
   relax-a-bound proposal — DF-05 `scan_banned` equality test), log each as a DF-01 candidate
   in the ledger + `findings/round-NNN.json`.
6. **Measure** — per round: `{n_findings, n_new_distinct, live_penalty_total,
   kelvin_ok, plane_signal_mm, drc, chosen_sha}`. **Local-minimum signal:** penalty_total
   rising while (kelvin/plane/drc) plateau AND chosen_sha repeats. **Usable signal:** distinct
   findings → physical metric improvement → findings taper with a set of distinct ratifiable rules.

Artifacts (ALL permanent — under this dir or a non-/tmp build dir copied here):
- `findings/round-NNN.json` — each round's audit findings + injections.
- `live-rules.json` — the evolving scorer penalties + manager rules.
- `measurement.jsonl` — the per-round convergence series.
- `morning-bundle.json` — Pareto finalists + final live-rules + the convergence verdict.

---

## 6. How to RESUME if the session is lost

1. Read this file + `memory/current-work-handoff.md` (the live handoff).
2. `git status` on `claude/corpus-experiential-intake` — the §2 fixes are uncommitted; the
   driver(s) are in `scripts/`.
3. Check the run: `cat build/inloop-audit/measurement.jsonl | tail`, `live-rules.json`,
   `ls findings/`. Is the 7h run still alive? `ps aux | grep cec_inloop_audit`.
4. V4 reachability: `curl -s localhost:8080/broker/models` → `deepseek-v4-flash.running`.
   It is host-side (`DESKTOP-1MO5R95.mshome.net:8007`), ~7min cold start, ~160GB host RAM,
   idle-reaped at 1800s. The fast seat (gpt-oss-120b `cec-manager-fast` / Sonnet) needs no
   special handling.
5. To re-run a blind judge: drivers are in `traces/` (`v4_blind_judge.py`, `v4_judge_lib.py`,
   `v4_briefing_context.txt`). Run on the HOST (broker at `localhost:8080`), not in-container.
6. The owner ratification queue (the usable-entry candidates) is the point — surface the
   distinct findings + the convergence verdict for the owner's morning review. Do NOT
   auto-promote anything to the ratified corpus.

## 7. Still-open ledger/handoff items (from before this experiment)

- FR-04 owner override-up: DF-01 LEDGERED 2026-06-11 (class override-up, ../cec-runs
  decisions.jsonl). Pin stays FR 1.7.0. Code committed d26651d.

## 8. FULL-STACK night plan (owner-requested 2026-06-11; next build)

Last night was deliberately LEAN (one auditor, deterministic everything else) so injection
effects were attributable. The full-stack night exercises every tier. **Firewall note: there
is NOTHING to fix** — the container reaches the broker (the "gap" was `curl` missing from the
image); the worker tier is unblocked as-is.

| # | Tier | Model / seat | Where | Cadence |
|---|------|-------------|-------|---------|
| 0 | Placement actuator (NEW — the local-minimum lesson) | deterministic `cec_loop` kelvin_tighten + GR-02 repair battery | container | on placement-class escalation |
| 1 | **Intent manager (the ASSISTED ROUTER — model-managed)** | a model seat (worker panel or Sonnet) reads the GR-01 congestion grid + the prior round's failures and EMITS the FR-02 relational waypoints (codifies `gr01_to_fr02_intents()`; replaces last night's STATIC intents dict) | host | every round |
| 2 | Route generation | Freerouting 1.7.0 + compiled FR-02 intents + layer policy + power pours at import | container | every round, BATCH of 4 seeds (R-01 spread) |
| 3 | Scoring + gates | `cec_score` (plane pricing) + CL-25 checkers — deterministic | container | every candidate |
| 3.5 | **FEM/FEA physics (was missing — owner catch)** | `cec_synth_pipeline.electrothermal_solve` + `physics_gates` (analytic IPC Picard: J→T→ρ(T), per-net cross-section, via split, shunt I²R) on poured candidates; max_T/J into the metrics + dashboard. CAVEAT: carries the known AM-04 model debt (segment-sum cross_mm2 ~5x optimistic on lanes) — gates stay advisory-tier until the PR-two debt fix | container | gate-passing candidates |
| 4 | Worker swarm (in-loop manager) | **cec-worker** = Qwen3.6-35B-A3B, 4 parallel slots, 3-lens panel (`make_manager_swarm`) — judges the batch incl. physics flags, drives FR effort | container→broker | every round |
| 5 | Fast auditor (injection) | **Sonnet** headless (stream-json → dashboard), + actuation-space check + novelty gate + rule cap | host | every round |
| 6 | Vision inspection | **cec-vision-judge** = Qwen3-VL-32B (nothink grammar calls; facts-alongside v2 protocol; structure/text only, never geometry) | host (renders from container) | each NEW Pareto finalist |
| 7 | Briefed reviewer (out-of-loop) | **cec-manager-fast** = gpt-oss-120b via `corpus_fit_review` w/ the ratified-rules briefing | host | each NEW Pareto finalist |
| 8 | Deep auditor | **V4** deepseek-v4-flash — opportunistic checkpoints (probe-only) + guaranteed MORNING pass on finalists | host→Windows | ~8th round IF up; morning always |
| 9 | Self-learning cycle | DecisionLogs→corpus, findings→DF-01 candidates, morning human ratification | host | continuous |

Tier-1 note (the "assisted router" question, answered): YES — assisted routing is model-managed
at two levels: the **intent manager** (tier 1) writes the route intents each round (the FR-02
waypoint mechanism — geometric judgment intent), and the **worker swarm** (tier 4) judges the
routed candidates and drives effort. Pareto axes gain `max_T` once tier 3.5 lands.

GPU choreography (single 5090, broker arbitrates): cec-worker (~9GB) resident; vision-judge
(~20GB) swaps in on finalist events (rare — batch vision+reviewer bursts to amortize the ~90s
swap); gpt-oss-120b (~6GB GPU + experts in RAM). **V4 stays excluded overnight** (pins ~160GB
host RAM against the WSL2 pool); its depth arrives as the morning pass.

Driver changes required (the convergence lessons baked in):
1. **Actuation-space check** before penalty escalation: "can any lever I own move this
   metric?" — placement-class failures route to tier 0, never to penalty inflation.
2. **Novelty gate** stronger than the fast seat's self-report (n-gram/semantic dedupe vs
   the standing ruleset; the night produced 76 rules, mostly rephrased epicycles).
3. **Rule cap + consolidation**: standing manager rules capped (~10); auditor must
   consolidate, not append.
4. Worker-swarm verdicts drive FR effort; the auditor only injects pricing/rules.

## 9. Live dashboard (built 2026-06-11, owner ask)

`scripts/cec_dashboard.py` — stdlib-only, read-only, **http://localhost:8090** (nohup'd;
log at `dashboard.log`). Panels: status header (alive/PID/rounds/final-verdict banner),
realtime step feed (run.log tail), latest-board render (auto re-rendered in-container when a
new candidate lands), live auditor thoughts (tails `findings/*-sonnet.stream.jsonl` —
`claude -p --output-format=stream-json --include-partial-messages` teed by `sonnet_audit`;
falls back to the newest finding's full reasoning + V4 checkpoint), convergence sparkline
(pen_total vs drc, red band = kelvin fail), injected ruleset. Restart:
`nohup python3 scripts/cec_dashboard.py --port 8090 > docs/inloop-audit-2026-06-11/dashboard.log 2>&1 &`
