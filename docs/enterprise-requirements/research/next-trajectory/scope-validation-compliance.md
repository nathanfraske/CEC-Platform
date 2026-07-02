# Next-trajectory scoping — VALIDATION + COMPLIANCE workstream (raw agent return)

_Scoping fan-out 2026-07-02 (owner ask: "parallelize and scope the next trajectory on the
enterprise variants"). One of five workstream scopes; synthesis lands in
`docs/enterprise-requirements/next-trajectory-2026-07-02.md`. Agent: sonnet._

## Objectives

- Convert every verify tag (I/A/T/D) across the 114 REQs into a traceable, lint-enforced artifact assignment — no REQ ships to Phase-3 review without a named verification method.
- Stand up the three adversarial bench specs the registers already presuppose (sync/pin-7 latch, mis-plug injection, heartbeat challenge) as buildable rigs, ahead of hardware, so firmware/board teams design to known test points.
- Produce per-family FMEA/FMEDA templates that make REQ-MOD-COMMON-030/031/032 and REQ-HUB-COMMON-081 satisfiable with real fault-injection evidence, not analysis-only hand-waves.
- Draft the compliance-process documents (PSIRT/CVD, SBOM pipeline, EMC pre-scan plan, FIPS OE-extension brief) so REQ-HUB-COMMON-014/094/096/097/099 and REQ-MOD-COMMON-052 have an owner-actionable process behind the "SHALL" language.
- Keep the verification program self-auditing: every register edit re-runs the matrix generator so verify-tag rot (a REQ added/reworded without a corresponding test-plan update) is caught the same way `cec_req_lint.py` catches malformed IDs today.

## Deliverables

| Deliverable | One-liner | REQ IDs served |
|---|---|---|
| **Requirements-verification matrix generator** (`scripts/cec_req_verify_matrix.py`) | Parses all registers, emits one row per REQ ID → {verify-tag combo, planned artifact (bench spec / FMEA doc / process doc / analysis note), status (planned/drafted/executed), owner}; fails CI if any REQ lacks a mapped artifact or an artifact references a retired ID | ALL 114 (cross-cutting) |
| **Sync bench spec** (`docs/enterprise-validation/bench-sync-pin7.md`) | Pin-7 wired-OR/PPS latch bench: fixture to measure module-to-module skew, verify the ≤100 ns target, and exercise the fabric relay re-broadcast | REQ-HUB-COMMON-112, -106, REQ-MOD-COMMON-013 |
| **Mis-plug injection rig spec** (`docs/enterprise-validation/bench-misplug-injection.md`) | Formalizes survey-11 §h into a runnable procedure: source list, DUT list, both-polarity/both-duration protocol, instrumentation, pass criteria, repeat-cycle count | REQ-HUB-COMMON-110, REQ-MOD-COMMON-053 |
| **Heartbeat adversarial bench spec** (`docs/enterprise-validation/bench-heartbeat-adversarial.md`) | Challenge/response bench incl. relay-delay fixture (inserted wire-delay/proxy to prove the µs acceptance window rejects it) and a key-less-emulator fixture (a module clone without the device key, to prove REQ-HUB-COMMON-114's auto-untrust fires) | REQ-HUB-COMMON-113, -114, REQ-MOD-COMMON-010, -013 |
| **FMEA/FMEDA templates per module family** (`docs/enterprise-validation/fmea-template-{24pin,eps,pcie,12vhpwr}.md`) | Structured worksheet (failure mode, effect, detection, in-path element, fault-injection evidence field) instantiated per family from the common template | REQ-MOD-COMMON-030, -031, -032, REQ-HUB-COMMON-081 |
| **EMC pre-scan plan** (`docs/enterprise-validation/emc-prescan-plan.md`) | Defines a low-cost in-house pre-compliance scan (near-field probe + spectrum analyzer sweep) to run before committing to a paid EN 55032/55035 lab slot, plus the decision criteria for when to escalate to the lab | REQ-HUB-COMMON-095 |
| **PSIRT/CVD process doc** (`docs/enterprise-validation/psirt-cvd-process.md`) | Intake → triage → advisory → disclosure workflow, severity scale, response-time SLAs tied to REQ-HUB-COMMON-102's support-period commitment | REQ-HUB-COMMON-014, -094, -102, REQ-MOD-COMMON-052 |
| **SBOM pipeline** (`docs/enterprise-validation/sbom-pipeline.md` + `scripts/cec_sbom_gen.py` stub) | Per-release SBOM generation wired to firmware build (west-based), format decision left open pending owner (input to D-ENT-5), CI hook to attach SBOM as a release artifact | REQ-HUB-COMMON-014, -094, REQ-MOD-COMMON-052 |
| **FIPS OE-extension engagement brief** (`docs/enterprise-validation/fips-oe-engagement-brief.md`) | One-pager for the wolfCrypt vendor conversation: what "embeds a validated module" requires operationally, the RISC-V/PolarFire OE gap, questions to ask at firmware kickoff, and the CAVP-vs-CMVP claim-language guardrail | REQ-HUB-COMMON-097 |
| **Compliance claim-language guardrail** (`docs/enterprise-validation/compliance-claims-lint.md` + a `cec_req_lint.py` check) | Prevents any doc/marketing text from asserting "FIPS validated," "SL-2 certified," or CRA compliance for a market not yet entered — mechanically greps for banned phrasings the same way the anti-ratchet DF-05/07 scan works | REQ-HUB-COMMON-096, -097, -098, -094 |

## Can start NOW vs GATED

**Now (no hardware needed):**
- Verification matrix generator — pure text parsing of existing registers.
- All three bench SPECS (procedures, fixtures list, pass criteria, instrumentation plan) — writing the spec is not running the bench.
- FMEA/FMEDA templates — the worksheet structure and known failure modes (in-path elements are already named in the spec/BOM docs).
- PSIRT/CVD process doc, SBOM pipeline doc, EMC pre-scan plan, FIPS brief, claims-lint — all pure process/paperwork.
- `cec_req_lint.py` extension to enforce the matrix.

**Gated on hardware/firmware (execution, not authoring):**
- Actually running the mis-plug injection tests — gated on: a fabricated Hub port + one module per family with the survey-11 protection network populated (not yet on any BOM).
- Sync bench measurement of the ≤100 ns target — gated on: PolarFire fabric relay implemented in firmware + ≥2 module boards with pin-7 wired to the ENT hub.
- Heartbeat adversarial bench — gated on: device-key provisioning implemented (REQ-MOD-COMMON-010) + a firmware-defined challenge method actually coded; the key-less-emulator fixture also needs a real firmware image to clone-without-key against.
- FMEDA fault-injection evidence — gated on: physical shunts/connectors installed (OQ-11 shunt-part lock is itself a precondition per REQ-MOD-COMMON-051).
- EMC pre-scan and lab-run — gated on: a populated PCB revision.
- SBOM pipeline execution — gated on: a real firmware build tree existing (`west spdx`-class tooling needs a buildable image).
- FIPS OE engagement — the brief can be written now; the actual vendor engagement is gated on firmware kickoff starting (explicitly stated in REQ-HUB-COMMON-097).

## Dependencies on other workstreams

- **Board/layout workstream**: needs to reserve and document physical test points (pin-7 latch access, DETECT ADC node, CAN bus probe points, per-port current-sense taps) the mis-plug and sync benches assume — bench specs should name required test points now so board layout doesn't have to retrofit them.
- **Firmware workstream**: heartbeat challenge method(s), device-key provisioning/storage, and the pin-7 hardware-timer response path must be specified (even at interface level) before the heartbeat bench fixture design can be finalized; sync-bench fabric-relay timing depends on firmware's fabric design.
- **Security/protocol-spec workstream**: the CAN challenge-response protocol, T1-link attestation format, and pin-7 nonce-delivery framing (referenced by REQ-HUB-COMMON-113/114) need a written protocol spec before the adversarial bench's relay-delay and key-less-emulator fixtures can be built against a stable wire format — currently only described narratively in the registers.
- **BOM/sourcing workstream**: FMEA/FMEDA in-path element list depends on OQ-11 shunt lock and the survey-11 protection-network parts actually landing in a BOM.
- **Spec-revision (Phase-4) workstream**: several REQs carry `Gate: Phase-4 spec edit` (e.g., -112, -114, -056) — the verification matrix should flag these as blocked-on-ratification, not silently treat DRAFT text as final test scope.

## Decision points needing the owner

| # | Question | Options | Lean |
|---|---|---|---|
| D-ENT-5 (existing) | SBOM format | SPDX vs CycloneDX | Lean CycloneDX (native vuln/VEX linkage aids PSIRT integration); SPDX is the more common "west spdx"-class default — flag both tool-chain costs |
| — | Third-party lab vs in-house EMC pre-scan | Pay for full EN 55032/55035 pre-compliance run per revision vs in-house near-field probe/spectrum-analyzer triage first | Lean in-house triage before every hardware rev, paid lab only pre-GA and after any RF-relevant change (T1 PHY, uplink magnetics) |
| — | When to engage a 62443 assessor | Never (pure "designed to" self-declaration) vs engage now for a gap-assessment vs wait for named-customer demand (REQ-HUB-COMMON-096's own text) | Lean wait for named-customer demand, but do a lightweight internal gap-check against SL-2 now so "designed to" isn't empty |
| — | FMEA depth: quantitative FMEDA vs qualitative FMEA at Phase-2 | Full FMEDA (failure rates, diagnostic coverage %) now vs qualitative FMEA now + FMEDA once shunt/connector parts lock (OQ-11) | Lean qualitative now, upgrade to FMEDA once OQ-11 closes — avoids rework on TBD parts |
| — | Heartbeat bench: build real hardware fixture now vs simulate in firmware-in-the-loop first | Physical relay-delay/emulator rig vs software-only protocol simulation as a stopgap | Lean software-only protocol sim now (can run before any board exists), physical rig once REQ-MOD-COMMON-013 firmware lands |
| — | PSIRT: build in-house vs adopt a vendor CVD platform (e.g., a hosted disclosure inbox) | In-house process doc + email intake vs a managed CVD/bug-bounty platform | Lean in-house doc for GA, revisit managed platform if EU CRA entry (REQ-HUB-COMMON-094) proceeds — Art. 14 timelines may justify tooling spend |

## Effort class

- Requirements-verification matrix generator: **M**
- Sync bench spec: **S**
- Mis-plug injection rig spec: **S** (survey-11 §h already drafts the procedure — mostly formalization)
- Heartbeat adversarial bench spec: **M** (relay-delay + key-less-emulator fixtures need original design)
- FMEA/FMEDA templates (×4 families): **M**
- EMC pre-scan plan: **S**
- PSIRT/CVD process doc: **M**
- SBOM pipeline (doc + stub script): **M**
- FIPS OE-extension brief: **S**
- Compliance claim-language guardrail + lint extension: **S**

## Top 5 risks

1. **"Designed to SL-2" without assessor evidence is a credibility gap** — a sales conversation or auditor could read "designed to IEC 62443-4-2 SL-2" as a claim of conformance. *Mitigation*: the claim-language guardrail deliverable mechanically blocks unqualified certification language repo-wide, and the internal gap-check decision point above gives the phrase actual backing before it's ever spoken to a customer.
2. **Verify-tag rot as registers evolve** — REQs are still DRAFT and churning (114 rows added in one day per the changelog); a test plan written against today's wording can silently desync from a reworded REQ. *Mitigation*: the matrix generator hashes each REQ's statement text and flags any artifact whose referenced REQ text changed since the artifact was last touched — same mechanism as the existing spec-§-resolution check in `cec_req_lint.py`.
3. **Bench specs written ahead of protocol finalization become wrong specs, not early specs** — the heartbeat/sync benches depend on firmware framing that isn't locked (nonce delivery, challenge method agility). *Mitigation*: version each bench spec against the REQ text it targets and mark fixture designs "interface-tentative" until the security-protocol-spec workstream publishes a wire format; matrix generator surfaces these as "planned, not drafted."
4. **FMEA evidence deadline collides with OQ-11 (shunt part lock)** — REQ-MOD-COMMON-031/051 both gate on OQ-11, and GA-blocking fault-injection evidence can't be finalized on a TBD part. *Mitigation*: template the FMEA now with placeholder part rows, explicitly track OQ-11 as a blocking dependency in the matrix so it isn't lost among the other 113 rows.
5. **Injection-test scope creep vs bench budget** — survey-11 §h alone calls for 6 PoE/injector sources × multiple DUTs × 60-minute sustained runs × 5–10 repeat cycles; combined with the heartbeat and sync benches this is a real lab-time cost that could stall Phase-3. *Mitigation*: sequence execution (software/simulated checks first, physical rig only after board rev 1 exists) and treat the "repeat 5–10×" pass criterion as a GA-gate item, not a per-iteration requirement during bring-up.
