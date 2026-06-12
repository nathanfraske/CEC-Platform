# Deep dive — the auditor↔verifier disagreement (CL-24 in the loop)

**Observed:** 2026-06-11, eps-8pin full-stack *validation* run
(`docs/fullstack-run-2026-06-11-validation/`, PID 253518). Captured live, rounds 1–3.
**Status:** analysis only — no code/charter/schema changed yet. This is a backlog
deep-dive, not a landed fix. (Owner-queue §1; memory `loop-auditor-verifier-lesson`.)

## What happened

Every round the Sonnet **auditor** (T5/CL-24 finding) independently reaches the *same
correct physical diagnosis* and proposes the *same wrong class of intervention*; the
CL-24 **verifier** refutes it every round (`verifier=refute CONTENTION → rejected:
verifier_refuted`). Across rounds 1–3 this produced **0 admitted rules** — the guard is
working, but it is re-catching one systematic error each round at the cost of a full
auditor+verifier round-trip (~17 min of broker time per round on the single 5090).

### The shared (correct) diagnosis — bankable
- **R1:** "FR is routing signal traces through the 12V cable-net pour corridors; these
  incursions reduce effective copper cross-section and are the direct mechanism behind the
  over-temp flags." (`foreign_cross` 12/8/7/3 on the SENSEC nets → 4 FEM over-temp flags.)
- **R2:** sharpened to one culprit — "`/SENSEC2_LO` pour fragmentation, 2 islands and **16
  foreign crosses, highest by 2×** … signal traces severing pour continuity before the
  Kelvin sense can connect. DRC=14 and unconnected=6 are *downstream* of the same
  stranded-LO root cause." The `manager_rule` tightened too: R1 fired on
  `foreign_cross > 5`; R2 narrowed to `foreign_cross > 10` on the **LO net specifically**.

The causal chain (foreign-net incursion → pour fragmentation → stranded Kelvin →
DRC/unconnected as *symptoms*) is right and reusable.

### The wrong prescription — refuted
The auditor's lever each round is a **scorer reweight**:
- R1: penalize `max_T`, weight **15**
- R2: penalize `kelvin_unrouted`, weight **500** (a 33× jack between rounds)

The verifier refutes because this is the **actuation-space** violation the CL-24 charter
exists to catch: a scorer reweight only reorders the *existing* candidate population; it
cannot *create* a clean route. If every candidate strands cable-2's Kelvin, no weight on
`kelvin_unrouted` helps.

### The verifier side (corrects an earlier read) — `verifier/round-00{1,2,3}.json`
CL-24 is a **3-seat panel + arbiter**: `spec-conformance`, `evidence-provenance`,
`actuation-space`. Reading the seats' actual reasoning corrects an earlier draft of this
doc that called the bundled **GR-02 corridor-clear** "the lever that would survive":

- **actuation-space (the consistent killer).** It lists the loop's *owned levers* —
  `{router passes/opt_time, FR-02 waypoint intents, bake_hints keepouts, GR-02 repair
  battery (shift/swap/via), power pours}` — and rules in R2/R3 that **GR-02 itself does NOT
  own foreign-crossing control**: *"foreign crossings are controlled by the signal router
  or placement, not by power pour geometry or GR-02 repair tools."* So the auditor's GR-02
  corridor-clear `manager_rule` is **also** refuted, not just its scorer penalty. The real
  owned lever for the diagnosed problem is **FR-02 waypoint intents (T1) / placement** —
  i.e. route the offending signal nets *around* the SENSEC pour corridors at intent time.
  That tier is *already running live* (T1), which makes the fix a feedback-routing problem,
  not a missing capability.
- **evidence-provenance (zero-tolerance sourcing).** It refutes in R2/R3 because the
  auditor cites pour-fragmentation / `foreign_cross` / FEM facts that are **absent from the
  evidence bundle handed to the verifier** ("the evidence only confirms DRC=8 and
  unconnected=2"). This is an **evidence-plumbing gap**: the verifier is starved of the
  same T6 pour-integrity + FEM facts the auditor reasoned over, so it refutes a
  mechanically-correct finding on provenance grounds. In R1 this seat voted `support`
  while its own reason said the data was absent — the arbiter flagged that as
  self-contradictory and discounted it.
- **spec-conformance (dark).** Returns `uncertain` every round because the ratified-rules
  corpus handed in is empty `[]` (the `promoted/` corpus is unsigned). One of three seats
  is effectively silent for the whole run.

`contention=true` only in R1 (the provenance seat's stray `support` triggered the arbiter);
R2/R3 were unanimous refute, no arbiter. The arbiter's R1 verdict is itself a precise
lesson: *"the finding correctly diagnoses the mechanism (foreign_cross incursion) and …
the scorer_penalty targets a thermal proxy instead of the primary convergence gate … price
routing convergence directly (unconnected count, or a foreign_cross-weighted routing cost)
and reserve max_T for the thermal gate tier, not conflate them."*

This repeats the morning run's "r3 charter correctly refuted a placement-class failure
mispriced as a scorer penalty." It is the **same failure mode recurring**, which is the
signal that the *generator* (auditor charter) is under-specified — not that the verifier
is failing.

## Empirical centerpiece — the loop optimized its proxy *into a worse board* (rounds 1–4)

Human visual inspection of the per-round renders (`vision/pour-r{1,2,3,4}.png`) picked
**round 1 as the best board** — and the zone metrics confirm it. DRC (the scorer's proxy)
and pour integrity (the physical goal) move in **strict opposition** across the run:

| round | DRC (proxy, ↓="better") | pour islands (1/net=intact) | Σ pour copper mm² | cable-2 sense copper mm² |
|---|---|---|---|---|
| **1** | **28 (worst)** | **4 (all intact)** | **394 (most)** | **197 (most)** |
| 2 | 14 | 5 | 374 | 173 |
| 3 | 8 | 6 | 361 | 171 |
| 4 | **5 (best)** | **7 (fragmented)** | **352 (least)** | **155 (−21%)** |

Each round the optimizer pushed DRC down by **routing more signal through the cable-2 sense
corridor**, fragmenting the SENSEC2 pours: `SENSEC2_HI` went 1→1→2→**3 islands**, copper
**85→60 mm²**. Cable-1 stayed flat (197→197) — cable-2 was sacrificed to the metric. The
scorer's pick (round 4, lowest objective) and the human's pick (round 1) **disagree, and the
human is right**: the board got physically worse where it matters (Kelvin sense pour
integrity) every round the loop "improved." This is lesson 7 made visible, and it is *why*
the verifier refused all four rounds and 0 rules landed — the loop never possessed a lever
that improved the goal, so it correctly admitted nothing and rode the proxy downhill. (Plot:
`zone-progression.png` — generate in the `cec/routing:kicad10` container; matplotlib is not
on the host.)

## Learnable lessons (the deep-dive agenda)

1. **A repeated refute of the same *class* is a generator-prompt bug, not a verify win to
   celebrate.** When the verifier kills the same shape N rounds running, fix the auditor
   charter; don't keep paying the verifier to re-catch it. Detection: track refute
   *reason-class* frequency; same class ≥2 rounds → flag the charter.

2. **Make the actuation-space rule a precondition the auditor SEES, not a post-hoc
   filter.** Put the allowed-lever set in the auditor prompt — `{GR-02 corridor-clear,
   place_rotate, FR passes/effort, bake_hints keepout}` — and state explicitly that
   **scorer reweights are not levers**. Deterministic rejections belong in generation, not
   verification. (Move the constraint upstream from verify→generate.)

3. **Split diagnosis from prescription in the finding schema.** The auditor's `root_cause`
   is correct and bankable; its `scorer_penalty` is wrong. Today they're bundled, so a
   refute discards the good causal trace with the bad lever. Gate only the
   `proposed_lever` against actuation-space; let a verified `root_cause` persist (feeds
   the corpus / next round). Every refute is currently a total loss of a good diagnosis.

4. **Selection pressure ≠ generation (the deepest, most general one).** Reweighting a
   *selection* metric helps only if the population already contains a good candidate; it
   cannot make one. Worth encoding as a standing charter/corpus principle because it
   recurs on *any* metric, not just `kelvin_unrouted`. Candidate corpus rule:
   *"A scorer-weight change is admissible only when a gate-passing candidate already
   exists and the change is needed to rank it first; otherwise the lever must change the
   generator (placement / routing / keepout), not the scorer."*

5. **Cycling/repeating a scorer-metric lever across rounds is a self-detectable tell.**
   The auditor did NOT monotonically escalate — it **thrashed**: R1 `max_T` (w15) → R2
   `kelvin_unrouted` (w500) → **R3 back to `max_T`**. So the detector is "the proposed
   lever is a scorer-metric reweight that has already been refuted this run" (cycling or
   rising), not narrowly "rising weight." Either way → force a lever-class change, no LLM.

7. **Proxy-vs-goal miscalibration — a penalty the optimizer can minimize WITHOUT
   achieving the gate is a local-minimum trap.** Surfaced by the T8 V4 batch auditor
   (`round-003-v4batch.json`), which *correctly declined to add findings* (anti-epicycle
   discipline) but nailed the deepest diagnosis: "the optimizer is minimizing the DRC
   penalty (weight 50) rather than pursuing genuine routability … local minimum." DRC fell
   28→14→8 across rounds while `gates_pass` stayed false — the loop optimized the *proxy*
   (DRC count) not the *goal* (routability). Lesson: a scorer term must not be
   independently satisficeable below its gate; either couple it to the gate (no credit for
   DRC reduction while `gates_pass=false`) or make the gate itself the dominant objective.
   This is distinct from lesson 4 (selection≠generation): there the population lacked a
   winner; here the *objective shape* rewards the wrong progress.

8. **Route the diagnosis to the tier that owns the lever — and it's already running.**
   The actuation-space seat names the owned-lever set explicitly; foreign signal-net
   crossings are owned by **FR-02 waypoint intents (T1) / placement**, not by GR-02 or
   pour geometry. The auditor's correct diagnosis ("signal X crosses pour Y") should be
   compiled into a **T1 intent** for the next round — waypoint the offending net around the
   SENSEC corridor — not into a scorer penalty or a GR-02 rule. The closed-loop wiring is
   auditor.root_cause → T1.intent, and T1 is live, so this is a routing-of-feedback fix,
   not new capability. (Supersedes the earlier draft's "GR-02 is the surviving lever.")

9. **The citable-fact set and the verifier's bundle-fact set are ONE contract that has
    drifted apart (owner reframe, 2026-06-11).** The evidence-provenance seat refuted the
    auditor's *true* facts — `islands`, `area_mm2`, `foreign_cross` (T6 deterministic) + FEM
    flags — because the verifier's bundle held only `DRC`/`unconnected`/`kelvin_ok`. The seat's
    zero-tolerance rule ("not in my bundle ⇒ unsourced ⇒ refute") is **sound only while
    bundle ≡ citable set**; once they drift, the hallucination check becomes a **false-refute
    generator for verified facts** — *worse* than no check, because it wears the costume of
    discipline. The fix is NOT "add pour facts to the bundle" (patches one fact type; re-drifts
    the next time a tier emits a new fact). It is **one authoritative fact registry** that both
    the auditor's citable set and the verifier's bundle are projections of — ideally identical —
    so they cannot diverge by construction. Each fact carries its **source-stage provenance**
    (T6-deterministic / FEM / measurement); the provenance seat validates a citation against
    **the registry**, not a separately-built bundle, so "not in bundle" and "not in the
    canonical fact set" are distinguishable and only the latter is hallucination. The drift
    likely arose from two construction paths: the auditor context was enriched with T6/FEM
    facts while the verifier bundle was still built from the narrower gate-metric slice.

10. **The spec-conformance seat is dark until `promoted/` is signed.** Empty ratified
    corpus → `uncertain` every round, so the panel runs on 2 of 3 seats. Populating the
    promoted corpus (owner re-sign, the standing CL-02 item) lights it up; until then,
    don't read a unanimous refute as 3-seat consensus — it's 2 seats (actuation + provenance).

11. **A panel with ANY dark seat must return a QUORUM verdict, never a FULL one (owner rule,
    2026-06-11).** Current bug: `verifier/round-*.json` reports `final: "refute"` flat, with
    no marker that a seat abstained — yet `spec-conformance` was dark (empty-corpus
    `uncertain`) in **all 4 rounds**, and `status: error` (timeout) in round 2. So every
    "refute" this run was a **2-of-3 quorum** mislabeled as a full verdict. A dark seat is an
    **abstention, not a silent yes**, and a consumer cannot distinguish 3/3 consensus from
    2/3-with-one-blind. REQUIRED schema change: `final` carries a verdict **type** —
    `FULL` only iff every seat returned a substantive (non-dark) verdict; otherwise `QUORUM`,
    with a `live_seats`/`dark_seats` roster and the reason each seat went dark
    (`empty_corpus` / `timeout` / `error` / `seat_down`). Downstream (admit/reject, PC
    capture) must treat a QUORUM verdict as lower-confidence than a FULL one.

6. **The refute reason is being wasted — thread it back into the generator.** Refute →
   `rejected`, then next round the auditor starts fresh with no memory that "scorer
   reweights get refuted on this board." Carrying the prior refute reason into the next
   auditor's context is the cheapest fix and the one that would actually break the cycle.
   This is the closed-loop (PC/DF feedback) gap.

## Implementation status (PR #35, 2026-06-11) — the agent actionables landed

The retrospective's agent items (fix-plan §5 items 2–5) are implemented and host-tested; rounds
can restart after owner merge. Lesson → mechanism:

| Lesson(s) | Mechanism (where) | Test |
|---|---|---|
| 2 charter / 3 schema / 6 thread-refutes | `OWNED_LEVERS` set + "scorer reweights are not levers" + prior-refute context in the auditor prompt; finding schema split into bankable `root_cause` + gated `proposed_lever`; `inject()` banks `root_cause` even on refute (`cec_fullstack.py`) | parse + smoke |
| 4 selection≠generation / 7 proxy-vs-goal | `cec_score.objective_v2`: **no DRC credit while `gates_pass` false** + pour-integrity (island excess + sense copper) first-class; wired as the loop ranking objective | `tests/test_scorer_pour_integrity.py` — **round 1 wins** |
| 5 cycling-knob | deterministic tripwire: a refuted scorer metric re-proposed → auto-reject, **no verifier spend** (`inject()` + pre-verify skip) | parse |
| 8 route to the owned lever (untried) | `cec_fr02.offending_net_intents` / `clipped_corridor_rects` — waypoint the **OFFENDING foreign nets** around the clipped corridor (r3 only tried the victim Kelvin nets); carried round→round in the loop | `tests/test_offending_net_intents.py` |
| 9 fact-contract / 10 bundle | verifier evidence bundle now carries the pour/FEM facts the auditor cites; `bundle_gaps()` deterministic contract check | parse |
| 11 quorum-not-full | `VerifierResult.verdict_type` FULL/QUORUM + `live_seats`/`dark_seats` roster (`cec_verifier.py`) | smoke |

Corpus: 4 evidence-complete process rules staged (`corpus/staging/general/loop-discipline-2026-06-11.json`,
lint-clean) for owner sign — candidates 2/5/6/7. Owner half (promoted/ signing → lights the dark
spec-conformance seat; reasoning-sheet settle; vision-contention fix) tracked in `docs/owner-queue.md`.

## Vision-render hygiene (owner note, 2026-06-11) — strip component models before a VLM reads it

The per-round renders fed to the CL-22 vision seat are **3D-body top renders**
(`vision/pour-r*.png`) and carry the documented kicad-cli artifact: rotated footprints
render text/bodies at false angles, and headless renders can show phantom rotations/offsets
absent in the GUI (CLAUDE.md "Known kicad-cli artifact"). Feeding that to a VLM induces
**false findings** (it "sees" misplacements that don't exist) — the precise plausible-but-
wrong input the verifier must then refute. FIX for the vision render: feed a **model-free
copper/zone/edge plot**, not component bodies — either `kicad-cli pcb export svg` of
`F.Cu`/`B.Cu`/`Edge.Cuts` + zone fills, or the already-model-free `cec_pcb.routing_plan_png`
matplotlib plan. That removes the artifact source and shows exactly what the seat judges
(pour integrity, foreign crossings), matching what the deterministic facts already compute.
Applies whenever the vision seat is exercised live (it was down/timeout this whole run).

## Through-line

The verifier is working *perfectly*. A verifier that keeps catching the **same**
systematic error is a map of where to spend a generator-side fix so it stops having to.
The morning's 1→4 (guarded) vs 1→83 (unguarded) rule growth is the verifier's *value*;
this disagreement is the *location* of the cheapest improvement: tighten the auditor
charter (lessons 2–4), add the two deterministic detectors (1, 5), close the feedback
(6), and fix the objective shape so DRC reduction earns no credit while `gates_pass=false`
(7, the T8 V4 local-minimum call).

**Run-level result (rounds 1–4, eps validation):** 0 LLM rules admitted, **7 refused** (closed
ledger: 3 penalties + 4 rules; the "6" in an earlier draft was the rounds-1–3 snapshot)
(`live-rules.json`); active penalties are pre-seeded defaults only. Verifier discipline
absolute. T8 V4 seat 502'd and declined (anti-epicycle behaviour correct, seat still
un-exercised live). Vision seat down all run (timeouts). The validation's headline win is
that the guard held under sustained, plausible-but-wrong pressure; lessons above are the
cheapest way to stop paying for that hold every round.

## Evidence index — trace every claim to the raw output

All paths under `docs/fullstack-run-2026-06-11-validation/`. This run is the worked
corpus for a full-process deep dive; each tier's output is preserved per round.

**Per-round metrics spine** — `measurement.jsonl` (one row/round): `sha`, `intents_src`,
`passes`/`opt_time`, `panel`, `gates_pass`, `kelvin_ok`, `drc`, `unconnected`, `max_T`,
`objective`, `verifier_final`, `verifier_spent` (budget burn of 200), `n_rules`,
`pour_clipped(_nets)`, `pour_vision`, `v4_risk`. The quantitative timeline:

| R | intents | passes/opt | panel | kelvin | drc | unconn | max_T | objective | verifier | spent | rules | pour_clipped | vision | v4 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | model | 32/52 | repair   | ✓ | 28 | 2 | 103.8 | 28254 | refute | 4  | 0 | — | seat down | — |
| 2 | model | 46/72 | escalate | ✗ | 14 | 6 | 133.6 | 14653 | refute | 7  | 0 | /SENSEC2_LO | timeout | — |
| 3 | model | 60/92 | escalate | ✓ | 8  | 2 | 101.9 | 8254  | refute | 11 | 0 | /SENSEC2_HI,/SENSEC2_LO | timeout | high |

**Tier-by-tier artifacts (the pipeline T0→T8):**
- **T0 GR-01 congestion grid** — `gr01-grid.json` (20 hotspots; contested nets GND, +3V3,
  /I2C_SDA, +5VSB, /I2C_SCL, /THRESH). Seeds the round's net-priority order.
- **T1 FR-02 intent manager** (model, live) — `intents/round-00{1,2,3}.json`: per-round
  net selection + relational waypoints. R1 +5VSB//THRESH//DETC1//CAN_L; R2 I2C/CAN; R3 the
  failing Kelvin pair /SENSEC2_HI/_LO. **This is the owned lever for lesson 8.**
- **T2–T3.5 route+gate+FEM** — captured in `measurement.jsonl` (drc/kelvin/max_T/objective)
  and the run log `../fullstack-run-2026-06-11-validation.log` (the `T2-3.5:` lines).
- **T4 panel** — run log `T4 panel:` lines (safety/finishing/progress votes per round).
- **T5 auditor (Sonnet) findings** — `findings/round-00{1,2,3}-sonnet.json` (verdict,
  reasoning, failure_class, scorer_penalty, manager_rule) + the **full agent transcripts**
  `findings/round-00{1,2,3}-sonnet.stream.jsonl` (~116–127 KB each; the complete
  tool-call/thinking stream for a turn-by-turn read of the auditor's process).
- **T5 verifier (CL-24, 3 seats + arbiter)** — `verifier/round-00{1,2,3}.json`: per-seat
  verdict+reason (spec-conformance / evidence-provenance / actuation-space), `contention`,
  and `arbiter` (R1 only). **The corrective evidence for lessons 8–10.**
- **T6 pour integrity** — deterministic facts in the run log `T6 POUR` lines + the vision
  attempt `vision/pour-r00{1,2,3}.json` (each `"skipped"/"error"` → seat down/timeout) with
  the rendered board `vision/pour-r{1,2,3}.png` (the images the down seat *would* have read).
- **T8 V4 batch auditor** — `findings/round-003-v4batch.json` (declined, `local_minimum_
  risk: high`; the proxy-vs-goal call behind lesson 7). 502'd live; artifact preserved.
- **Admitted-state ledger** — `live-rules.json`: active `scorer_penalties` (pre-seeded
  defaults), `manager_rules: []`, `injections: []`, and the 6 `rejections` (3 penalties +
  3 rules, all `rejected:verifier_refuted`, rounds 1–3). The bottom line of the whole run.

**How to deep-dive the process end to end:** read `measurement.jsonl` as the spine, then
for any round open T1 intent → T5 sonnet `.json` (verdict) → `.stream.jsonl` (how it got
there) → `verifier/round-N.json` (why it was refused) → `live-rules.json` (what survived).
The `.stream.jsonl` files are the only place the auditor's *full* chain-of-work is captured.

## Cross-refs
- CL-24 verifier tier / Decision 9 charters — `docs/closed-loop-parity-plan.md` §1.
- DF anti-ratchet / PC capture — the refute-feedback gap (lessons 6, 8) lives here.
- Morning validation verdict — `current-work-handoff.md` (1→4 vs 1→83; r3 actuation-space refute).
- Actuation-space framing — Appendix D (agent-neutrality / evidence-over-local-intelligence).
- CL-02 promoted-corpus re-sign — the owner item that lights up the dark spec-conformance seat (lesson 10).
