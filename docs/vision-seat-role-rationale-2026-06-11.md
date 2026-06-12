# Vision-seat role rationale — stop it judging geometry, give it a job it can do

**Status:** design rationale for review (proposal). Feeds the vision-seat eval binding in
`cec-policy.json` and a follow-up to PR #36 (which correctly gates the seat off on render
hygiene + leaves it non-load-bearing until its role is fixed).
**Trigger:** the PR #36 item-4 artifact (`docs/fullstack-run-2026-06-11-validation/vision-unify-evidence.json`)
showed the vision seat marking ALL four rounds "clipped" on the model-free render — flagging
intact round-1 as *worse* than fragmented round-4. It was parroting the fed `foreign_cross>0`
rule, not reading the render. CL-21 again: **VLM seats cannot measure geometry.**

## 1. The diagnosis (why it failed)

We asked the seat to **measure** — "is this pour clipped / fragmented?" — which is an absolute
geometric judgment. Two things follow:
- A VLM cannot reliably count islands or measure copper area from a raster. It approximates, and
  under the v2 facts-alongside protocol it short-circuits to **restating the numbers we fed it**.
- The deterministic checker (`pour_facts` / `pour_integrity_ok`) already computes those counts
  exactly, and **owns** that judgment (r1 pass / r4 fail, proven). So asking the VLM to re-derive
  them is both impossible for it and redundant with determinism.

**Principle (bake-off-established, CL-21):** the VLM is good at **selection/comparison** and
**reading structure/text**; it is bad at **absolute measurement**. Measurement stays with the
deterministic checkers. The seat is only worth running if its job plays to the first set.

## 2. The redesign — three jobs it CAN do, ranked

Give the seat the deterministic facts as **authoritative ground truth** (so it never needs to
derive geometry) and ask it ONLY for things determinism can't give:

1. **Consistency auditor (recommended primary).** Input: the model-free copper/zone render + the
   deterministic facts. Output (the ONLY thing it emits): *does the render CONTRADICT the facts, or
   show a feature NO fact describes?* — a discrepancy flag with a rough location, never a pour
   verdict. This catches the failure class determinism is **blind** to:
   - **stale-fill / export bugs** — the render shows a break the facts miss because the fill is
     stale (a real, known hazard: kicad-cli can't refill; DRC then reads false shorts);
   - **checker scope gaps** — a defect class no checker computes (slivers, acid traps, an
     unexpected keepout, a weird corridor) that a human would notice at a glance;
   - **the unknown-unknowns** a deterministic gate cannot enumerate by construction.
2. **Reference selection.** Input: candidate render + a frozen **known-good reference** render,
   facts alongside. Output: *same structure or degraded vs the reference, and where?* This is a
   selection task (A-vs-B), which the bake-off proved the seat CAN do — unlike absolute
   measurement. Use when you want a quality read, not just a contradiction flag.
3. **Anomaly surfacer (open-ended).** "What is in this render that no deterministic fact
   describes?" The novelty catch — lowest precision, highest coverage; everything it raises is
   re-checked (below).

## 3. The tools it needs

- **Authoritative facts** — already have (`pour_facts`): islands, `foreign_cross`, copper area per
  net. Hand them over as ground truth; the prompt states "the facts are authoritative for all
  counts; do NOT recount — your job is disagreement and the un-described."
- **A reference render** — for role 2: a model-free render of a frozen known-good board (a golden's
  intact-pour state) to compare against. Cheap to keep.
- **A deterministic RE-CHECK on every flag** — the safety envelope (below). When the seat flags a
  discrepancy, re-run the targeted deterministic check (refill + recompute the facts / a DRC) to
  confirm or dismiss it.
- **A constrained output** — `{discrepancy: bool, where: str, vs_facts: str, undescribed: [..]}` or
  a selection verdict — **never** a pour-integrity boolean. The schema makes the wrong job
  unexpressible.

## 4. Why this is safe and can't regress (the falsifiability envelope)

The whole reason the old design was dangerous: a VLM measurement claim could **block or mislead**
on a hallucination. The new design removes that by construction:

- The VLM **never measures and never gates.** The deterministic `pour_integrity_ok` gate decides
  pour integrity; the VLM only **raises a question**.
- **Every VLM flag is resolved by determinism.** A flagged discrepancy triggers a re-check:
  confirmed → a real find (a stale fill, a checker gap) that's genuinely valuable; not confirmed →
  silently dismissed. So a false positive costs one cheap re-check and nothing else; a
  hallucination can never survive to affect a decision.
- **Net asymmetry:** the seat can only *add* caught defects (the things determinism misses), never
  *subtract* trust from the deterministic gate. That is the only shape in which a non-measuring VLM
  earns a place next to exact checkers.

## 5. Recommendation

- Keep PR #36's posture: vision seat **gated** (render hygiene) and **non-load-bearing**; the eval
  binding records the failed measurement test honestly.
- Adopt **Role 1 (consistency auditor)** as the seat's job in a follow-up PR: facts-as-ground-truth
  + discrepancy-only output + a deterministic re-check on every flag. Re-run the item-4 style test
  under the new framing — pass bar becomes "does it catch a planted stale-fill / checker-gap that
  determinism misses," which is a job it can actually pass.
- Only after that test passes does the owner sign the vision-seat eval gate to load-bearing — and
  even then it is load-bearing for *discrepancy surfacing*, never for the pour verdict itself.

The one-line version: **determinism measures; the VLM only says "the picture disagrees here" or
"you didn't check that," and determinism gets the last word on whatever it raises.**
