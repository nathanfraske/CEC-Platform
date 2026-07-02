# Decision brief — anti-tamper-radio (ATR) module family (OQ-78)

**Ask size:** Real review — genuine tension, not a formality. **Sequencing:** own-section
gate (D-ENT-5).

## Context

`docs/enterprise-requirements/research/tamper-module-roadmap-2026-07-02.md` proposes a
whole-chassis tamper-sensing module using anti-tamper radio (ATR): a handful of COTS UWB
antennas (under $5 each) inside the metal case, detecting physical implant insertion at
needle scale, retrofittable, far cheaper than a security mesh — pitched as a strong
differentiator between weak tamper switches and costly HSM mesh solutions (roadmap line
34; identified as a candidate premium differentiator in the roadmap's closing open
question, line 1377). `OQ-78` (spec-draft EDIT 9) asks to adopt/decline this alongside the
other tamper-module candidates (chassis-intrusion switch, rollback-resistant tamper log,
device attestation, power-fingerprint screening). `REQ-HUB-COMMON-073` already carries the
conditional gating text: "If the ATR module is adopted... the Hub SHALL gate its RF
emission by variant policy... emission with the policy unset SHALL default OFF."

**The tension:** ATR is, by construction, an *intentional RF emitter* (UWB radar-class
sensing). ENT-AIR's entire premise is a **radio-free build** — no network PHY populated,
inspection-verifiable without powering the unit, and every ENT module MCU chosen
specifically because it has no Wi-Fi/BLE-capable silicon (v1.2.0 draft §13.6). Fitting an
intentional emitter into the one posture defined by the absence of emitters is a direct
contradiction unless carefully scoped.

## Options

1. **Adopt, NET-only, emission default OFF.** ATR ships only on ENT-NET builds (which have
   no radio-free mandate to begin with); the RF emission is policy-gated and defaults
   disabled until explicitly turned on.
2. **Decline.** No ATR module family; tamper detection stays limited to chassis-intrusion
   switches, the rollback-resistant log, and device attestation.
3. **Adopt fleet-wide** (both postures), relying solely on the emission-policy gate to keep
   ENT-AIR radio-free in practice.

## Trade-offs

- Option 1 resolves the contradiction structurally (the emitter simply isn't present on the
  posture that promises no emitters) rather than relying on a runtime policy flag to make
  an inspection-verifiable claim ("build state SHALL be visually verifiable at inspection
  without powering the unit," `REQ-HUB-AIR-101`) — a populated-but-disabled radio does not
  satisfy an unpowered visual inspection the way an unpopulated radio does.
- Option 3 keeps the tension alive at the population level: even with emission defaulted
  off, a populated ATR antenna is physically present on an ENT-AIR chassis, which
  contradicts the "radio-free build... externally verifiable unpowered (part marking + BOM
  + no antenna keepout)" standard the module-build-variant text sets (v1.2.0 draft §13.6).
- Option 2 forgoes a differentiator the roadmap flags as filling a real gap (between weak
  switches and expensive mesh) at zero incremental risk, but it's the only option requiring
  no new engineering.
- Whichever is chosen, `REQ-HUB-COMMON-073`'s conditional gating text and its "policy unset
  = OFF" fail-safe default should carry forward regardless — it's sound however OQ-78
  resolves.

## Recommendation

**Adopt, NET-only, emission default OFF.** This keeps the differentiator alive where it
creates no contradiction (ENT-NET has no radio-free requirement to violate), keeps
ENT-AIR's inspection-verifiable radio-free promise intact by not populating the part at
all on that posture, and preserves the emission-default-OFF fail-safe already drafted in
REQ-HUB-COMMON-073 for whichever variant does carry it.

## Evidence

- `docs/enterprise-requirements/research/tamper-module-roadmap-2026-07-02.md` line 34 (ATR
  proposal), line 1377 (open question framing it as a premium differentiator vs.
  table-stakes).
- `docs/enterprise-requirements/hub-enterprise-requirements.md` REQ-HUB-COMMON-073 (line
  129).
- `docs/spec-revision-v1.2.0-draft-2026-07-02.md` EDIT 9, OQ-78; EDIT 4 §13.6 (radio-free
  module build standard) and §13.2 (ENT-AIR "no network PHY populated,
  inspection-verifiable without powering the unit").
- `docs/enterprise-requirements/hub-enterprise-requirements.md` REQ-HUB-AIR-101 (line
  165) — the unpowered visual-verification requirement this recommendation protects.

## Downstream effect

If adopted NET-only: OQ-78 resolves to a posture-scoped module family, REQ-HUB-COMMON-073's
conditional text becomes definite for ENT-NET and moot (never populated) for ENT-AIR, and
the tamper-module roadmap's candidate list gets its first adopted item. If declined: OQ-78
closes with no ATR family, and the roadmap's remaining candidates (chassis-intrusion,
tamper log, attestation, power-fingerprint screening) are unaffected either way.
