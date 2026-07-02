# Decision brief — provenance role (evidence-source vs. actuation-target)

**Ask size:** Real review. **Sequencing:** own-section gate (D-ENT-5) — decide alongside
v1.2.0, not after.

## Context

The Hub's PolarFire root of trust already has one requirement tying it to Appendix D of
the spec: `REQ-HUB-COMMON-007` — "Appendix-D support-pipeline plan execution SHALL verify
plan signatures against the Hub root of trust before actuation (the OQ-62 tie lands
here)." That requirement is narrowly scoped: the Hub *checks a signature* on an
already-generated actuation plan before it lets that plan execute. It does not, as
written, make the Hub itself a party that *authorizes* or *originates* actuation.

The open question is whether the enterprise line's provenance role should stay at that
scope (**evidence-source only** — the Hub signs and attests: tamper logs, telemetry,
device identity, plan-signature verification) or be widened to also make the Hub an
**actuation-target** (a node that can be commanded/authorized to actuate, not merely one
that checks a signature before letting an external plan run).

## Options

1. **Evidence-source only.** The Hub's cryptographic role is to produce trustworthy
   signed evidence (tamper log, telemetry, identity attestation) and to gate Appendix-D
   plan execution on a signature check. It never becomes a target that a remote actor
   authorizes to act.
2. **Also actuation-target.** The Hub's root of trust additionally becomes the anchor for
   authorizing inbound actuation commands more broadly than the single Appendix-D
   plan-signature check already specifies.

## Trade-offs

- Option 1 is a narrower trust boundary: it adds no new capability beyond what
  REQ-HUB-COMMON-007 already states, and it keeps the enterprise line's security story
  simple — the Hub is a sensor and an evidence-producer, full stop.
- Option 2 would reopen the Appendix-D trust boundary (who can command actuation, under
  what verification, with what revocation path) — a much larger design surface that isn't
  needed to close out this wave's registers, and isn't asked for by any requirement on
  record. Appendix D's support pipeline (`CEC-Platform-Ground-Truth-Spec.md` Appendix D)
  already places the actuation-authorization question at the plan-signing step, not at the
  Hub.
- Choosing option 1 keeps `REQ-HUB-COMMON-007` as the complete statement of the Hub's
  provenance responsibility; choosing option 2 would require drafting new requirements this
  wave doesn't currently carry.

## Recommendation

**Evidence-source only.** This matches what REQ-HUB-COMMON-007 already specifies and
avoids opening a wider actuation-authorization design (Appendix D trust boundary) that
nothing in the current registers or spec draft calls for.

## Evidence

- `docs/enterprise-requirements/hub-enterprise-requirements.md` REQ-HUB-COMMON-007 (line
  24).
- `docs/enterprise-mc-requirements-plan-2026-07-01.md` §2 — OQ-44/OQ-62 provenance tie
  ("hard provenance routes to the Enterprise secure element"; "Appendix D support-pipeline
  plan signing — same secure-element tie"), §4 D-ENT-5 row ("plan-signing provenance
  role" listed as a still-open line item).
- `docs/enterprise-requirements/research/next-trajectory/scope-ratification-package.md`
  row (c) "Provenance role."
- `CEC-Platform-Ground-Truth-Spec.md` Appendix D (the support-pipeline stages this
  requirement gates).

## Downstream effect

Confirms REQ-HUB-COMMON-007 needs no widening; the D-ENT-5 line item retires as decided
(evidence-source only) rather than staying open, and no new Appendix-D actuation
requirement needs drafting this wave.
