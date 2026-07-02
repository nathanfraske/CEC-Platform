# Decision brief — firmware signing-key custody procedure

**Ask size:** Real review. **Sequencing:** own-section gate (D-ENT-5); a GA gate —
`REQ-HUB-COMMON-011` requires this be "documented and owner-ratified before first
enterprise ship," so it must clear before enterprise GA, not necessarily before Phase-5
board start.

## Context

`REQ-HUB-COMMON-011`: "Firmware updates SHALL be signed; the signing-key custody procedure
SHALL be documented and owner-ratified before first enterprise ship." This is currently an
audit-identified process gap (`audit §2`), gated D-ENT-5. The security-protocols
workstream has already drafted the architecture-level options (key hierarchy per silicon
class: PolarFire PUF-derived root + Athena-backed signing key where fitted, ESP32-P4
MCU-resident device key for modules; key types — firmware-signing, per-unit identity,
heartbeat-derivation) and flagged the custody *ceremony* as the specific owner decision
this requirement is waiting on.

## Options

1. **HSM-managed service** — an online or managed hardware security module holds the
   firmware-signing root and signs releases on demand.
2. **Documented offline procedure** — an air-gapped M-of-N ceremony (multiple
   custodians, threshold signing) for the root key, with a lower-tier online HSM (if any)
   reserved for high-frequency operational signing only (e.g., per-unit issuing at
   manufacture) if volume warrants it.

## Trade-offs

- Offline M-of-N avoids trusting network- or HSM-custody at a contract-manufacturer site
  at CEC's current size — the security-protocols workstream's explicit lean is "offline
  M-of-N for the root; lower-tier online HSM for high-frequency operational signing only
  if EST/SCEP volume warrants," and separately, for the manufacturing issuing tier, "offline-
  signed batch manifest — avoids trusting network/HSM custody at a CM site at this size."
- An HSM-managed service is operationally simpler once volume is high (no ceremony
  logistics per release) but introduces a standing managed-service trust dependency and
  cost that isn't justified at current or near-term ship volumes.
- A related, adjacent decision (not this brief, but worth flagging alongside it): whether
  the tamper-log signing key is the *same* device key used for heartbeat/identity, or a
  *separate* KDF-derived key. The security-protocols workstream's lean is a separate log
  key — "compromise of one must not forge the other's evidence trail" — and this brief's
  recommendation is written assuming that separation holds, since it changes how many keys
  the custody procedure needs to cover.
- Drafting the full procedure now risks being thrown away if the ratified ceremony form
  differs from the draft's assumption — the workstream's own mitigation is to keep the
  architecture-level draft (key hierarchy, key types) ready now and defer the detailed
  procedure write-up until after this ratification.

## Recommendation

**Draft the procedure for sign-off first** (don't jump straight to standing up either an
HSM service or a fully detailed ceremony document): confirm the offline M-of-N lean for
the firmware-signing root, confirm the separate tamper-log signing key, and treat any
online HSM as a lower-tier operational-signing-only component if manufacturing volume
later justifies it. This is a ratification of direction, not a request to execute a
ceremony this sitting.

## Evidence

- `docs/enterprise-requirements/hub-enterprise-requirements.md` REQ-HUB-COMMON-011 (line
  34).
- `docs/enterprise-requirements/research/next-trajectory/scope-security-protocols.md` —
  item 1 ("Key hierarchy & custody plan"), item 7 ("Tamper-log signing key tier"), the
  "Key custody ceremony form" and "HSM vs offline CA for the issuing tier" decision rows,
  and the "GATED on owner ratification" / "keep #1 architecture-level... detailed procedure
  write-up only after ratification" risk note.
- `docs/enterprise-mc-requirements-plan-2026-07-01.md` §4 D-ENT-5 row ("signing-key
  custody ratification" listed as a still-open line item).

## Downstream effect

Ratifying the direction (offline M-of-N root, separate log key) lets the security-protocols
workstream finalize items #1/#2/#5 (key hierarchy, provisioning, tamper-log format) to
final (not draft) status, and satisfies REQ-HUB-COMMON-011's GA gate once the detailed
procedure document is subsequently written against this ratified direction.
