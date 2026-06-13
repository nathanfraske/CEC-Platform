# Claims (PP-01)

The one-page claims document. **At most two claims.** Each is one falsifiable sentence, with the
single experiment that would kill it and the current evidence and cite gaps. Nothing here is
asserted that the instrumentation inventory (`instrumentation-inventory.md`, PP-07) does not have a
named mechanism for.

---

## C1 — Signature-gated corpus custody yields a dark-seat property and exact, ledger-level evidence taint

**Falsifiable claim (one sentence):**
> A corpus-governed agentic loop in which promotion is enforced by a server-side cryptographic
> signature gate (CODEOWNERS + branch protection on `corpus/promoted/**`, with agents on a machine
> account that cannot self-approve) makes every piece of evidence exactly partitionable into
> knowledge-influenced vs uninfluenced rounds via a per-round `corpus_state` pin, AND causes a
> verifier seat whose authority derives from unsigned knowledge to declare itself *dark* rather than
> emit a confident verdict from un-ratified material.

**Why it is the strongest claim.** It rests on mechanisms that already exist and are checkable
without any new run: the signature gate is real branch protection, not a convention (EI-08 DONE,
machine account `nathanfraske-bot` cannot approve owner-path PRs); the taint partition is the
`corpus_state` record written on every ledger append and every measurement row (EI-01 DONE,
`scripts/cec_ledger.py:corpus_state`); the dark-seat behaviour is the documented contract that any
seat reading an empty/unsigned `corpus/promoted/` must contribute to a QUORUM verdict typed as
lower-confidence, never a flat full verdict.

**The experiment that would kill it.** Take the 30-night dataset (M2) and attempt to find a single
gate-passing promotion whose supporting evidence was produced by a round whose `corpus_state` pin
does NOT distinguish it from the uninfluenced control — i.e. show the partition is not exact, that
an influenced round can masquerade as a control. Equivalently: demonstrate the spec-conformance
verifier emitting a confident, non-dark verdict while `corpus/promoted/` is unsigned, or
demonstrate the machine account merging an owner-path change without owner review. **Any one of
these kills C1.** (The partition exactness is the load-bearing sub-claim; the `live_rules_sha` /
`manager_rules_sha` / `adv_set_sha` content hashes are what make it falsifiable rather than
hand-wavy — they pin the *effective* steering knowledge, not just the commit tree.)

**Current evidence.**
- Custody mechanism: `.github/CODEOWNERS` + branch protection on `/corpus/promoted/`,
  `/cec-policy.json`, `/tests/golden/`, `/corpus/SCHEMA.md`; machine account live (EI-08).
- Taint pin: `corpus_state()` on every `cec_ledger.append` and on every measurement row in
  `cec_fullstack` / `cec_inloop_audit` / `cec_overnight_directed` (EI-01 DONE).
- Dark-seat contract: spec-conformance seat dark every round of the 2026-06-11 eps run; QUORUM-not-FULL
  rule (owner, 2026-06-11) recorded in `docs/owner-queue.md` and `docs/auditor-verifier-disagreement-deep-dive-2026-06-11.md`.

**What is NOT yet shown (honesty gate before M4).** No *signed* promotion has happened yet (M1
unreached) — so the dark→live transition of the spec-conformance seat is observed only on the dark
side. C1's custody half is an existence-pending claim until M1.

**Cite gaps (do NOT invent these).**
- [CITE NEEDED] Prior art on signature/attestation-gated data or model-update pipelines (supply-chain
  attestation, signed datasets) to position "server-side signature gate" as novel-in-application here,
  not novel-in-mechanism.
- [CITE NEEDED] Prior art on provenance/lineage tracking for ML training or agentic memory, to
  position `corpus_state` taint partitioning relative to data-provenance and experiment-tracking work.
- [CITE NEEDED] The notion of a "dark seat" / abstention-under-missing-authority — relate to selective
  prediction / abstention and to quorum/Byzantine-style degraded-confidence voting.

---

## C2 — The evaluation is determinism-dominant: hard gates and physical metrics come from deterministic checkers, and LLM seats are confined to roles they can perform

**Falsifiable claim (one sentence):**
> In this loop the gate-pass decision and all physical metrics (`kelvin_ok`, `plane_signal_mm`,
> `drc`, `unconnected`) are computed by deterministic checkers and the LLM seats are restricted to
> narration, selection/comparison, and lever *proposal* — so the loop's pass/fail behaviour is
> governed by the deterministic checkers and is reproducible to byte-identity on temp-0 seats,
> independent of seat enthusiasm or seat model swaps.

**Why it is the second claim, not the first.** Determinism-dominance is a design stance we adopted
*because* the alternative failed measurably (CL-21: VLM seats cannot measure geometry — see
`negative-results.md`). The claim's strength is that it is reproducible and that the seat-model
swap (Sonnet auditor → DeepSeek-V4 auditor) did not move the gate-pass behaviour. Its weakness is
that "determinism-dominant is *better*" needs the M3 ablation to have any quantitative content.

**The experiment that would kill it.** Run the same board family through the loop with the LLM
seats given measurement authority over the gates (the pre-CL-21 protocol: ask the seat "is this
pour clipped?" and let its answer gate). If the gate-pass rate or the convergence-verdict
distribution becomes *equal-or-better* and reproducible across seat swaps, then determinism was not
load-bearing and C2 is false. Conversely, if swapping the auditor seat (Sonnet↔V4↔a third model)
moves the gate-pass rate on identical inputs, the "independent of seat" half of C2 is false.
**Either result kills C2.**

**Current evidence.**
- Gates are deterministic: `cec_score` computes `kelvin_ok` / `diffpair_ok` / `drc` / `unconnected`;
  `pour_integrity_ok` / `plane_signal_mm` from `pour_facts`; the 34-round run shows gate-pass governed
  by these (0 gate-passing over 34 rounds while the auditor repeatedly proposed levers — the seats
  could not "talk the board" past the checkers).
- Seat confinement: CL-21 redesign restricts the vision seat to narration + anomaly-surfacing
  (`docs/decisions/owner-ruling-vlm-detection-pipeline-2026-06-11.md`,
  `docs/research/grounding-cl21-vlm-seat-redesign-2026-06-11.md`); the auditor's `root_cause` is bankable but
  its `proposed_lever` is gated (verifier-refutable).
- Seat-swap invariance (partial): Sonnet→V4 auditor swap (commit `cbb9ef0`, owner 2026-06-11) changed
  *which* model audits, not the deterministic gate computation.

**What is NOT yet shown.** Byte-identity of temp-0 seats is asserted from the FR/router determinism
work, not yet measured end-to-end across an auditor swap on identical inputs (that measurement is an
M3 prerequisite). The "independent of seat" half is currently a design property, not a measured one.

**Cite gaps (do NOT invent these).**
- [CITE NEEDED] LLM-as-judge reliability / failure-mode literature, to position CL-21 ("seats cannot
  measure geometry") against known judge-reliability findings.
- [CITE NEEDED] Neuro-symbolic / verifier-in-the-loop design literature, to position
  "determinism-dominant, LLM-proposes-checker-disposes" as a recognised pattern.
- [CITE NEEDED] Reproducibility-of-LLM-pipelines work, for the seat-swap-invariance sub-claim.

---

## Scope discipline

- We do NOT claim the loop produces a *better board* than a human (it does not — the one multi-round
  run converged to a `local_minimum`, see `negative-results.md`). C2 is about *governance and
  reproducibility of the evaluation*, not board quality.
- We do NOT claim the FEM thermal numbers are accurate — they are uncalibrated until bench (AM-04;
  see `negative-results.md` and `instrumentation-inventory.md`).
- Both claims are stated over **one board family** by **one team** with **one reviewer**. The
  external-validity limitation is in `negative-results.md` and must appear in the paper's abstract,
  not buried.
