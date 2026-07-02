# Decision brief — REQ-HUB-NET-111: PD-capable ENT-NET uplink

**Ask size:** Real review. **Sequencing:** must clear before v1.2.0 (R2) merges — the
draft spec assumes an answer.

## Context

`REQ-HUB-NET-111` (`hub-enterprise-requirements.md`) is currently PROPOSED, owner
exploration 2026-07-02: should the ENT-NET uplink jack additionally act as an 802.3af/at
**powered device (PD)**, so Hub power can be independent of the monitored PSU? If adopted,
a galvanically isolated PD controller + converter would feed a fourth, lowest-priority,
eFuse-fronted slot of the §2.9 source priority-OR (PSU-derived MAIN_5V > 5VSB > external
feed > PD), gated by forensic policy. Class mapping: 802.3af (~13 W) would cover the
STANDBY posture; 802.3at (~25 W) could reach FULL.

## Options

1. **Adopt.** ENT-NET hubs can be powered entirely from switch infrastructure, independent
   of the customer's PSU — useful if a customer wants the Hub live even when the monitored
   machine is off, or wants one fewer power cable in a rack.
2. **Decline.** No PD front-end; the uplink stays a pure 1000BASE-T data port. Power comes
   only from the existing three §2.9 sources (MAIN_5V, 5VSB, external feed).
3. **Defer.** Leave PROPOSED, revisit if a specific customer asks.

## Trade-offs

- Adopt costs an estimated $5–10/unit adder (survey estimate, unverified quote) plus a
  **re-verification of the OQ-14 uplink protection topology**: the existing enterprise
  closure argument (§2.4 EDIT 5 in the v1.2.0 draft) leans on "a standards-compliant PSE
  will not apply power without detecting our absent PD signature resistor" — i.e., the
  protection story is partly built on the Hub *not* presenting a PD signature. Adding a
  real PD front-end inverts that premise and the protection analysis would need to be
  redone for this specific port.
- Adopt also adds the PD path to the REQ-HUB-COMMON-060 per-source monitoring (a fourth
  monitored input, fourth PG/FLT pair, fourth priority rung in firmware).
- There is currently **no customer requirement on record** driving this — it originated as
  an owner exploration, not an audit finding. The customer-integration-audit's related row
  (REQ-HUB-NET-004, "evaluate 802.3af/at PoE powering... independent of the monitored PSU")
  is itself tagged `[Δ, owner gate]` / `(oem)` — an optional evaluation item, not a stated
  buyer ask.
- ENT-AIR is unaffected either way (no uplink jack exists on that posture).

## Recommendation

**Decline now.** No customer ask exists to justify the added protection-topology rework
and BOM adder; the three-source §2.9 priority-OR already gives the Hub power independent
of a single point of failure. Revisit as a documented, revisitable option (same posture as
the SFP uplink study) if a specific fleet customer asks for switch-powered operation.

## Evidence

- `docs/enterprise-requirements/hub-enterprise-requirements.md` — REQ-HUB-NET-111 (full
  text, gate `D-ENT-5`).
- `docs/enterprise-requirements/research/customer-integration-audit-2026-07-01.md` line
  179 — REQ-HUB-NET-004, tagged `[Δ, owner gate]` `(oem)`.
- `docs/enterprise-requirements/research/phase2/survey-2-ethernet-uplink.md` §"OQ-14
  enterprise closure proposal" — the absent-PD-signature protection argument this decision
  would invalidate if adopted.
- `docs/spec-revision-v1.2.0-draft-2026-07-02.md` EDIT 5 — the §2.4 protection topology
  text that assumes no PD front-end.

## Downstream effect

- **Decline (recommended):** no change to the v1.2.0 draft's EDIT 5 wording; R2 (apply
  v1.2.0) proceeds as drafted.
- **Adopt:** EDIT 5's protection-topology paragraph needs a rewrite before R2 can apply,
  and REQ-HUB-COMMON-060 (per-source monitoring) needs a fourth-source amendment — pushes
  the v1.2.0 PR back a cycle.
