# CEC closed-loop corpus governance — paper track

This directory is the **paper track** for the CEC closed-loop corpus-governance system: the
research artifacts that turn the running pipeline into a falsifiable, reproducible result. It is
deliberately separate from the engineering punchlists (the EVIDENCE-INTEGRITY list EI-01..EI-08
and the PAPER-TRACK list PP-01..PP-13) — those say *what to build*; the docs here say *what we
will claim, how each claim could be killed, and which number comes from which mechanism*.

Everything here is **commit-timestamped on purpose**. A preregistration (PP-06) is only worth the
bytes if it lands in git BEFORE the data it governs exists. Read `git log -- docs/research/` to
check ordering before trusting any "we predicted X" statement.

## The framing: at most two claims

We make **at most two** claims. More than two and none of them gets the evidence it needs from an
N=1 team running a single board family.

1. **C1 — Signature-gated corpus custody gives a dark-seat property and exact, ledger-level
   evidence taint.** This is the strongest claim. The promotion gate is a server-side signature
   (CODEOWNERS + branch protection on `corpus/promoted/**`), not a convention; an unsigned corpus
   makes the spec-conformance verifier seat go *dark* (declared, not silently degraded); and every
   round/run carries a `corpus_state` pin (git tree ids of the ratified + staging corpus, plus
   content hashes of the live rules that actually steered routing) so any downstream measurement
   can be partitioned exactly into knowledge-influenced vs uninfluenced rounds.

2. **C2 — The evaluation is determinism-dominant: the hard gates and physical metrics are
   produced by deterministic checkers, and the LLM seats are confined to roles that do not measure
   geometry.** The vision seat *cannot* measure (CL-21, demonstrated on our own boards); the
   manager/auditor seats propose, the deterministic checkers gate. The claim is that a
   determinism-dominant loop is the design that survived contact with the failure modes — and that
   its measured behaviour (gate-pass governed by checkers, not by seat enthusiasm) is reproducible.

The one-page version of each, with its kill experiment, is in **`claims.md` (PP-01)**.

## Index

| Doc | Punchlist | What it is |
|---|---|---|
| `claims.md` | PP-01 | The ≤2 claims, each one falsifiable sentence + its kill experiment + the cite gaps still open. |
| `negative-results.md` | PP-04 | Negative results + limitations, drafted now to discipline the claims (the docs above are written against these). |
| `prereg-control-lane.md` | PP-06 | Preregistration of the EI-02 control-vs-augmented A/B, locked BEFORE its first night of lane-tagged data. |
| `instrumentation-inventory.md` | PP-07 | One table: every number the paper will claim → the mechanism that produces it → its current status. No "hope to compute later" rows. |
| `README.md` | — | This index + the framing + the milestone ladder. |

## Milestone ladder

The paper is gated on these four milestones, in order. We do not write the discussion section
before M3.

- **M1 — first signed promotion.** A `corpus/promoted/**` entry merged through the real signature
  gate (owner GitHub-verified review, machine account unable to self-approve — EI-08 DONE). This is
  the existence proof for C1's custody half. Until M1, the spec-conformance seat has only ever run
  dark, so C1's dark-seat property is observed but its *signed* counterpart is untested.
- **M2 — 30-night control dataset.** The EI-02 control lane (PP-06) run to its preregistered
  round/night count, with every round carrying a `corpus_state` pin and a control/augmented tag.
  This is the dataset both claims are measured on.
- **M3 — ablation.** The augmented tier removed and re-run on held-out rounds; the difference (if
  any) on the preregistered metrics is C2's quantitative content and the test of whether the
  augmented tier *buys* anything. A null result here is a publishable negative (see
  `negative-results.md`) and does not invalidate C1.
- **M4 — preprint.** Claims, negative results, prereg, and the instrumentation table reconciled
  against the actual M2/M3 data; related-work cites filled (see the cite-gap list in `claims.md`);
  external-replication limitation stated honestly.

## Status honesty

As of this writing: M1 not yet reached (no signed promotion — `corpus/promoted/` holds migrated
entries pending the owner re-sign ritual). The single multi-round dataset we have
(`docs/fullstack-run-2026-06-13/`, 34 rounds, 0 gate-passing, verdict `local_minimum`) is a
*pre-lane* run and is used here ONLY as negative-result and instrumentation evidence, never as a
control-lane result. The actuator that the augmented tier would use to escape that local minimum
was found this session to have been **silently dead** (the item4 corridor-avoid lever had zero
callers) — see `negative-results.md`. That finding is why M2 cannot start until the lever is
verified live in-loop.
