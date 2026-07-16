# Decision brief — anti-tamper-radio (ATR) module family (OQ-78)

**Ask size:** Real review — genuine tension, not a formality. **Sequencing:** own-section
gate (D-ENT-5).

## Context

`research/tamper-module-roadmap-2026-07-02.md` proposes a whole-chassis tamper-sensing
module using anti-tamper radio (ATR): COTS UWB antennas (<$5 each) inside the metal case
detecting physical implant insertion at needle scale, retrofittable, far cheaper than a
security mesh (line 34; flagged as a candidate premium differentiator, line 1377). `OQ-78`
asks to adopt/decline this alongside the other tamper candidates (chassis-intrusion
switch, rollback-resistant log, device attestation, power-fingerprint screening).
`REQ-HUB-COMMON-073` already carries the gating text: "If the ATR module is adopted...
the Hub SHALL gate its RF emission by variant policy... emission with the policy unset
SHALL default OFF."

**The tension:** ATR is, by construction, an *intentional RF emitter*. ENT-AIR's whole
premise is a **radio-free build** — no network PHY populated, inspection-verifiable
without powering the unit, every ENT module MCU chosen specifically for no Wi-Fi/BLE
silicon (v1.2.0 draft §13.6). Fitting an intentional emitter into the one posture defined
by the absence of emitters is a direct contradiction unless carefully scoped.

## Options

1. **Adopt, NET-only, emission default OFF.**
2. **Decline** — no ATR family.
3. **Adopt fleet-wide**, relying on the emission-policy gate alone to keep ENT-AIR
   radio-free in practice.

## Trade-offs

Option 1 resolves the contradiction structurally — the emitter isn't present on the
posture that promises none — rather than relying on a runtime flag to satisfy an
inspection-verifiable claim (`REQ-HUB-AIR-101`: build state visually verifiable
*without powering the unit*; a populated-but-disabled radio fails that test). Option 3
keeps the tension alive at the population level even with emission off, contradicting the
"externally verifiable unpowered (part marking + BOM + no antenna keepout)" radio-free
standard (§13.6). Option 2 forgoes a differentiator the roadmap flags as filling a real
gap, at zero engineering risk. REQ-HUB-COMMON-073's conditional gating and its OFF-default
fail-safe should carry forward regardless of which option is chosen.

## Recommendation

**Adopt, NET-only, emission default OFF.** Keeps the differentiator where it creates no
contradiction, keeps ENT-AIR's radio-free promise intact by not populating the part at
all, and preserves the OFF-default fail-safe already drafted.

## Evidence

- `research/tamper-module-roadmap-2026-07-02.md` lines 34, 1377.
- `hub-enterprise-requirements.md` REQ-HUB-COMMON-073 (line 129), REQ-HUB-AIR-101
  (line 165).
- `spec-revision-v1.2.0-draft-2026-07-02.md` EDIT 9 OQ-78; EDIT 4 §13.6/§13.2.

## Downstream effect

If adopted NET-only: OQ-78 resolves to a posture-scoped family; REQ-HUB-COMMON-073's text
becomes definite for ENT-NET, moot for ENT-AIR. If declined: OQ-78 closes with no ATR
family; the roadmap's other candidates are unaffected.
