# Next-trajectory scoping — RATIFICATION PACKAGE workstream (raw agent return)

_Scoping fan-out 2026-07-02. One of five; synthesis in `../../next-trajectory-2026-07-02.md`. Agent: sonnet._

## Objectives

- Compress every open ENT decision into ONE minimal-friction, ordered queue so the owner can clear Phase 4 (spec promotion) and unblock Phase 5 (board start) in the fewest sittings.
- Separate "one-word nod" decisions (evidence assembled, default argued) from "real review" decisions (novel trade-offs) so bandwidth goes where needed.
- Pre-stage every artifact a decision depends on (RFQ-ready BOM extracts, cited KVM recs, per-decision briefs) so no decision blocks on research once it reaches the owner.
- Keep the CODEOWNERS PR ritual as the single approval mechanism — batch related edits into one PR per group.
- Build a ratification-readiness lint so nothing ships to Phase 5 with a dangling gate or unresolved OQ reference.

## The decision inventory

| Group | ID/Name | Unblocks | Options | Recommended default | Ask size |
|---|---|---|---|---|---|
| (a) v1.2.0 | Apply the spec revision | OQ-7 close, §1 tier table, Phase-4 promotion, Phase-5 gate | Direct owner edit vs approve exact-edit PR | Approve PR (audit trail, CODEOWNERS flow) | Real review (once) — rulings made; this is signature not debate |
| (b) Adopt/decline | REQ-HUB-NET-111 — PD-capable ENT-NET uplink | Whether the PD front-end + re-verified OQ-14 topology enters the design | Adopt / decline / defer | Decline now (no customer ask; adds a slot + re-verification) | Real review |
| (b) Adopt/decline | RS-485-compat-drop nod (REQ-043) | Hub port hardware finalization | Confirm drop vs require dual-mode | Confirm the drop (survey-10 case + $9–30/hub) | One-word nod |
| (c) D-ENT-5 | Provenance role | REQ-HUB-COMMON-007 tie, tamper-family scope | Evidence-source only vs also actuation-target | Evidence-source only | Real review |
| (c) D-ENT-5 | Mezzanine OQ-77 | REQ-HUB-COMMON-100 mechanical | Adopt / decline / defer | Adopt for ENT-AIR appliance packaging | Real review |
| (c) D-ENT-5 | ATR OQ-78 (RF tamper sensing vs radio-free) | REQ-HUB-COMMON-073 emission gating, tamper family | Adopt NET-only / decline / policy-gated-off | Adopt, NET only, emission default OFF | Real review (genuine tension) |
| (c) D-ENT-5 | Signing-key custody procedure | REQ-010/011 firmware signing, GA gate | HSM vs documented manual procedure | Draft procedure for sign-off first | Real review |
| (c) D-ENT-5 | SBOM format | REQ-014 / MOD-052 tooling | SPDX vs CycloneDX | SPDX (`west spdx` already named in -014) [NOTE: validation scope leans CycloneDX — conflicting agent leans, surface both] | One-word nod |
| (d) D-ENT-3 | Authorize the RFQ batch (PolarFire, LAN9370×2, T1 PHYs, eFuse fronts, watchdog, eMMC/QSPI) | BOM re-baseline (091/092/050), Phase-4 BOM | Full batch now vs staged | Authorize now — parts identified (surveys 1/3/4/9/10) | One-word nod |
| (e) Program gate | Board program start (Phase 5) | Opening the ENT KiCad projects | Strict gate behind Phase-4 vs parallel skeleton work | Strict gate (avoid rework on unratified text) | Real review (sequencing call) |
| (e) Program gate | OQ-75 CEC-KVM kickoff | KVM workstream; triggers the promised cited-recs list | Now vs post-board-start | Kick off now — recs list pre-staged | One-word nod |
| (e) Program gate | OQ-11 shunt part lock (R-vs-K suffix divergence found: CSS2H-2512R-1L00F as sourced vs spec text) | REQ-MOD-COMMON-051 — before ANY module board | Confirm -R after verifying C4175647's series; fix spec text | Confirm + fix text | Real review (small, board-blocking) |

## Deliverables

- **Ratification review brief** — the table above as an ordered, checkbox-able queue (nods first, real-reviews grouped), each row linking to its source doc/line. **M**
- **Per-decision one-page briefs** — for the 6 "real review" rows only. **M**
- **RFQ package prep** — quote-ready BOM extracts at 100q keyed to the sourcing survey per part. **M**
- **CEC-KVM cited-recommendations list** — the FOLLOWUPS-promised OQ-75 deliverable, produced proactively: SoC/SoM pick, carrier form, image/secure-boot approach, AIR no-NIC scope, PSIRT cost — each cited to tamper-module-roadmap §6 / plan §3a.6. **S**
- **Ratification-readiness lint** — extend `cec_req_lint.py`: every Gate resolves to `—` or a queued decision; OQ-75..81 collision-free; spec-draft §-refs stay resolvable post-application. **S**

## Sequencing

- (b) must clear BEFORE (a) merges — the draft already assumes the RS-485 drop and carries REQ-111 open; applying the spec first would bake in an undecided default.
- (a) is the hinge: nothing in Phase 4/5 formally proceeds without it.
- (c) items gate their own sections, not the spec edit — decide alongside, except mezzanine OQ-77 (feeds §12 mechanical in the same spec application; decide with (b)).
- (d) RFQ is fully independent — start immediately (vendor lead time is real clock time).
- (e) board-start is downstream of (a) + registers RATIFIED; OQ-11 is a separate parallel prerequisite for modules — resolve alongside (b)/(a), not after.
- **Minimal set that unblocks boards**: {REQ-111 decision, RS-485 nod} → apply v1.2.0 → {OQ-11 lock} → Phase-5 gate. Everything else in (c)/(d) can lag without blocking board start.

## Can start NOW vs GATED

- **NOW**: all five deliverables — none require an owner decision to author. OQ-11 part-number desk verification too.
- **GATED**: applying the v1.2.0 PR (needs (b)); opening Phase-5 KiCad projects (needs (a)+ratified registers); firmware signing work (needs custody); tamper-module board work (needs ATR + provenance decisions).

## Risks

- **Owner bandwidth is the actual bottleneck** — mitigate by front-loading artifacts (review a decision, not a research gap) and separating nods from real reviews.
- **CODEOWNERS latency compounds** if each decision is its own PR — batch: one PR for the (b)-adjusted v1.2.0 edit, one PR for register gate-flips once (c) decides; RFQ/KVM docs need no gated PR.
- **Spec/register drift** if (a) applies before (b) settles — strict sequencing + the readiness lint.
- **OQ-11 silently blocks all module boards** if the R/K suffix question is glossed — treat as a hard prerequisite in the minimal path, not folded into the D-ENT-5 pile.
- **RFQ vendor lead time becomes the hidden critical path** — authorize RFQs now, in parallel.
