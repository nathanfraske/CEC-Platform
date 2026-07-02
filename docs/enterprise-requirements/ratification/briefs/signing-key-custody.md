# Decision brief — firmware signing-key custody procedure

**Ask size:** Real review. **Sequencing:** own-section gate (D-ENT-5); a GA gate —
required before first enterprise ship, not necessarily before Phase-5 board start.

## Context

`REQ-HUB-COMMON-011`: "Firmware updates SHALL be signed; the signing-key custody
procedure SHALL be documented and owner-ratified before first enterprise ship." Currently
an audit-identified process gap, gated D-ENT-5. The security-protocols workstream has
already drafted architecture-level options (key hierarchy per silicon class: PolarFire
PUF-derived root + Athena-backed signing key where fitted, ESP32-P4 MCU-resident device
key for modules; key types — firmware-signing, per-unit identity, heartbeat-derivation)
and flagged the custody *ceremony* as the specific decision this requirement awaits.

## Options

1. **HSM-managed service** — online or managed HSM holds the firmware-signing root,
   signs releases on demand.
2. **Documented offline procedure** — air-gapped M-of-N ceremony for the root key, with a
   lower-tier online HSM (if any) reserved for high-frequency operational signing only
   (e.g. per-unit issuing at manufacture) if volume warrants it.

## Trade-offs

Offline M-of-N avoids trusting network- or HSM-custody at a contract-manufacturer site at
CEC's current size — the workstream's explicit lean is "offline M-of-N for the root;
lower-tier online HSM only if EST/SCEP volume warrants," and for the manufacturing issuing
tier, "offline-signed batch manifest — avoids trusting network/HSM custody at a CM site at
this size." An HSM-managed service is simpler at high volume but adds a standing
managed-service dependency not justified yet. Adjacent, not this brief but relevant to its
scope: whether the tamper-log signing key is the same device key as heartbeat/identity or
a separate KDF-derived key — the workstream leans separate ("compromise of one must not
forge the other's evidence trail"), and this recommendation assumes that separation holds.
Drafting the full procedure now risks being thrown away if the ratified ceremony form
differs — the mitigation is to keep the architecture-level draft ready and defer the
detailed write-up until after ratification.

## Recommendation

**Draft the procedure for sign-off first** — confirm the offline M-of-N lean for the
firmware-signing root, confirm the separate tamper-log key, treat any online HSM as
lower-tier operational-signing-only if volume later justifies it. This ratifies direction,
not a ceremony to execute this sitting.

## Evidence

- `hub-enterprise-requirements.md` REQ-HUB-COMMON-011 (line 34).
- `research/next-trajectory/scope-security-protocols.md` — items 1/7, the "Key custody
  ceremony form" / "HSM vs offline CA" decision rows, and the "GATED on owner ratification"
  risk note.
- `enterprise-mc-requirements-plan-2026-07-01.md` §4 D-ENT-5 row.

## Downstream effect

Ratifying direction lets the workstream finalize items #1/#2/#5 (key hierarchy,
provisioning, tamper-log format) to final status, and satisfies REQ-HUB-COMMON-011's GA
gate once the detailed procedure is written against this ratified direction.
