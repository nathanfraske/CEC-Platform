# Decision brief — apply spec revision v1.2.0 (the enterprise line)

**Ask size:** Real review, once — signature, not debate. **Sequencing:** the hinge; apply
only after N1 (RS-485 drop) and R1 (REQ-111) clear.

## Context

`docs/spec-revision-v1.2.0-draft-2026-07-02.md` is a complete, surgical 10-edit set that
promotes every 2026-07-01/02 owner ruling into `CEC-Platform-Ground-Truth-Spec.md`. It adds
the new §13 (ENT-NET/ENT-AIR on PolarFire), rewrites the §1 tier table, amends the
tier-agnostic phrasing to distinguish interface (LOCKED, unchanged) from build variant
(new), closes OQ-7 and the enterprise half of OQ-14, closes OQ-53..56 for the enterprise
tier, disentangles OQ-60 (RJ-11), and opens OQ-75..81. No LOCKED electrical decision is
touched — module link, pin table, CAN 500k, DETECT, shunt values, and connector locks all
stand per the semver rationale in the draft's header.

## Options

1. **Owner edits the spec directly.**
2. **Owner approves a PR containing exactly these edits** (CODEOWNERS flow, audit trail
   preserved in git history).

Both are "the owner's pen" under the repo's CODEOWNERS convention — this is not a
technical fork, just a mechanism choice.

## Trade-offs

- There is genuinely no open debate left in the content: every edit in the draft is a
  restatement of a ruling already made (the draft explicitly says so in its status line —
  "Decision boxes marked [OWNER] are the only unresolved choices; everything else is a
  recording of rulings already made"). The only remaining decision box the draft itself
  names is OQ-75 (CEC-KVM), which is a kickoff nod (N4), not a blocker to applying the rest.
- The PR route gives a reviewable diff and a permanent audit trail matching how every other
  ratified change in this repo has landed; direct editing is faster by one step but breaks
  from the CODEOWNERS discipline the rest of the program uses.
- **Do not apply before N1/R1 clear** — EDIT 4 (§13.2a) and EDIT 5 (§2.4-ENT) both assume
  specific answers to the RS-485 drop and the PD-uplink question. Applying first would bake
  in an undecided default, which the scope doc calls out as the primary drift risk.

## Recommendation

**Approve as a PR** containing exactly the 10 edits in the draft, after N1 and R1 are
resolved. This is a signature pass: read the draft's EDIT 1–10 once, confirm nothing has
moved since 2026-07-02, and merge.

## Evidence

- `docs/spec-revision-v1.2.0-draft-2026-07-02.md` — the complete edit set (EDIT 1–10) and
  its closing "Decision boxes for the owner, consolidated" section.
- `docs/enterprise-requirements/next-trajectory-2026-07-02.md` §4 — "(a) hinge" row.
- `docs/enterprise-requirements/research/next-trajectory/scope-ratification-package.md`
  row (a) and "Sequencing" — "(b) must clear BEFORE (a) merges."

## Downstream effect

Applying v1.2.0 is what unlocks: Phase-4 promotion of the `docs/enterprise-requirements/`
registers from DRAFT toward RATIFIED, the Phase-5 board-start gate (N5), and EDIT 10's
mechanical follow-ups (CLAUDE.md summary + tier table refresh, both hub READMEs, register
gate-flips, re-running `cec_req_lint`/`cec_corpus_lint` in the same change).
