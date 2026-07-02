# Decision brief — provenance role (evidence-source vs. actuation-target)

**Ask size:** Real review. **Sequencing:** own-section gate (D-ENT-5) — decide alongside
v1.2.0, not after.

## Context

The Hub's PolarFire root of trust has one requirement tying it to spec Appendix D:
`REQ-HUB-COMMON-007` — "Appendix-D support-pipeline plan execution SHALL verify plan
signatures against the Hub root of trust before actuation (the OQ-62 tie lands here)."
That's narrowly scoped: the Hub *checks a signature* on an already-generated actuation
plan before letting it run. It does not make the Hub itself a party that *authorizes* or
*originates* actuation.

The question: should the enterprise line's provenance role stay at that scope
(**evidence-source only** — signs/attests tamper logs, telemetry, identity, and gates
plan execution on a signature check) or widen to also make the Hub an **actuation-target**
(an anchor for authorizing inbound actuation more broadly than the single plan-signature
check already specifies)?

## Options

1. **Evidence-source only** — no new capability beyond REQ-HUB-COMMON-007.
2. **Also actuation-target** — widens the Hub's root of trust to authorize inbound
   actuation commands generally.

## Trade-offs

Option 1 keeps a narrow, simple trust boundary: the Hub is a sensor and evidence-producer,
full stop. Option 2 reopens the whole Appendix-D actuation-authorization question (who can
command actuation, under what verification, with what revocation path) — a much larger
design surface not needed to close this wave's registers and not asked for by any
requirement on record; Appendix D already places actuation authorization at the
plan-signing step, not at the Hub. Option 2 would also require drafting new requirements
this wave doesn't currently carry.

## Recommendation

**Evidence-source only.** Matches what REQ-HUB-COMMON-007 already specifies; avoids
opening a wider actuation-authorization design nothing in the current registers calls for.

## Evidence

- `hub-enterprise-requirements.md` REQ-HUB-COMMON-007 (line 24).
- `enterprise-mc-requirements-plan-2026-07-01.md` §2 (OQ-44/OQ-62 provenance tie — "hard
  provenance routes to the Enterprise secure element"; "Appendix D... same secure-element
  tie") and §4 D-ENT-5 row ("plan-signing provenance role" still open).
- `research/next-trajectory/scope-ratification-package.md` row (c) "Provenance role."
- `CEC-Platform-Ground-Truth-Spec.md` Appendix D — the support-pipeline stages this
  requirement gates.

## Downstream effect

REQ-HUB-COMMON-007 needs no widening; the D-ENT-5 line item retires as decided
(evidence-source only) rather than staying open, and no new Appendix-D actuation
requirement needs drafting this wave.
