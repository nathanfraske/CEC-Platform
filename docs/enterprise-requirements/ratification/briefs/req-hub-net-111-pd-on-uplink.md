# Decision brief — REQ-HUB-NET-111: PD-capable ENT-NET uplink

**Ask size:** Real review. **Sequencing:** must clear before v1.2.0 (R2) merges — the
draft spec assumes an answer.

## Context

`REQ-HUB-NET-111` (`hub-enterprise-requirements.md`) is PROPOSED, owner exploration
2026-07-02: should the ENT-NET uplink jack also act as an 802.3af/at **powered device
(PD)**, so Hub power can be independent of the monitored PSU? If adopted, an isolated PD
controller/converter would feed a fourth, lowest-priority, eFuse-fronted slot of the §2.9
priority-OR (af ~13 W covers STANDBY, at ~25 W could reach FULL), gated by forensic policy.

## Options

1. **Adopt** — ENT-NET hubs powerable entirely from switch infrastructure.
2. **Decline** — uplink stays a pure 1000BASE-T data port; power stays on the existing
   three §2.9 sources (MAIN_5V, 5VSB, external feed).
3. **Defer** — leave PROPOSED, revisit if a customer asks.

## Trade-offs

Adopting costs an est. $5–10/unit adder (unverified) plus a **re-verification of the
OQ-14 uplink protection topology**: the current enterprise closure argument leans on "a
compliant PSE won't apply power without detecting our absent PD signature" — a real PD
front-end inverts that premise, so the protection analysis would need redoing for this
port. It also adds a fourth monitored input to REQ-HUB-COMMON-060. There is **no customer
requirement on record** driving this — it originated as an owner exploration; the related
audit row (REQ-HUB-NET-004, "evaluate 802.3af/at PoE powering") is itself tagged
`[Δ, owner gate]` `(oem)`, an optional evaluation item, not a stated buyer ask. ENT-AIR is
unaffected either way (no uplink jack on that posture).

## Recommendation

**Decline now.** No customer ask justifies the protection-topology rework and BOM adder;
the three-source §2.9 priority-OR already removes the single-PSU dependency. Revisit as a
documented, revisitable option (same posture as the SFP uplink study) if a fleet customer
asks for switch-powered operation.

## Evidence

- `hub-enterprise-requirements.md` — REQ-HUB-NET-111 (gate `D-ENT-5`).
- `research/customer-integration-audit-2026-07-01.md` line 179 — REQ-HUB-NET-004.
- `research/phase2/survey-2-ethernet-uplink.md` §"OQ-14 enterprise closure proposal" —
  the absent-PD-signature protection argument this decision would invalidate if adopted.
- `spec-revision-v1.2.0-draft-2026-07-02.md` EDIT 5 — §2.4 protection topology text.

## Downstream effect

**Decline (recommended):** no change needed to EDIT 5; R2 proceeds as drafted. **Adopt:**
EDIT 5's protection-topology paragraph needs a rewrite before R2 can apply, and
REQ-HUB-COMMON-060 needs a fourth-source amendment — pushes the v1.2.0 PR back a cycle.
