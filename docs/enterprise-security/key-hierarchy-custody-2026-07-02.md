# CEC Enterprise key hierarchy & custody plan — DRAFT v0.1

> **STATUS: DRAFT — pre-ratification working draft, ARCHITECTURE LEVEL ONLY.** This is
> Security Workstream deliverable **#1**
> (`docs/enterprise-requirements/research/next-trajectory/scope-security-protocols.md`,
> "Can start NOW" — needs only the silicon facts already ratified). It is deliberately
> written above the procedure level: **every custody ceremony, HSM-vs-offline choice, and
> per-family cert-chain decision below is a FLAGGED OWNER DECISION POINT, not a baked
> design.** REQ-HUB-COMMON-011 requires the firmware-signing key custody procedure to be
> "documented and owner-ratified before first enterprise ship" (gate D-ENT-5) — nothing in
> this document satisfies that gate; it exists so the ratification has a concrete proposal
> to ratify or amend. Where this document names a "Lean," that is the workstream scope's
> recorded lean, not a decision.
>
> This document assumes the threat model in `threat-model-2026-07-02.md` and cites it
> rather than restating its honest-limits language (§4 of that document in particular:
> the ESP32-P4 no-SE residual, the surface-independence classification, the TC-baseline
> DPA statement, and the two-chip fallback seam all bear directly on what follows).

## 1. Why one hierarchy, not two

The platform has two silicon classes carrying keys — the PolarFire-class ENT Hub and the
ESP32-P4 ENT modules — with very different root-of-trust hardware (PUF + Athena option vs.
MCU-resident eFuse). The workstream scope's objective is explicit: "Define ONE key
hierarchy spanning both silicon classes... so identity, signing, and heartbeat crypto are
consistent platform-wide, not per-family improvisation." This document is that hierarchy.
It does NOT mean the two silicon classes derive from a shared key — they have separate
hardware roots by necessity (§2) — it means one *architecture* governs how every key,
regardless of which silicon it lives on, is typed, derived, rotated, and revoked.

## 2. Roots of trust, per silicon class

### 2a. PolarFire (Hub)

- **Hardware root**: PolarFire SoC PUF (present on both the S-suffix and, pending FAE
  confirmation, the TC Core baseline per REQ-HUB-COMMON-001 — see the threat model §4c for
  the DPA-posture caveat that applies regardless of PUF presence).
- **Device identity**: an IDevID-class, 802.1AR-aligned certificate rooted in the PolarFire
  key store, provisioned at manufacture (REQ-HUB-COMMON-003). This is a genuine hardware
  root distinct from the platform's existing consumer-tier "factory-MAC + database" scheme,
  which REQ-HUB-COMMON-003 states explicitly is NOT sufficient at this tier.
- **Operator enrollment**: LDevID-class certificates via EST or SCEP, issued post-deployment
  without requiring physical access (REQ-HUB-NET-004).
- **DPA posture**: Athena (S-suffix) is an HS population OPTION on the same land, not
  assumed present. Every design below MUST be evaluated for both the TC (no Athena) and TS
  (Athena) populations, per REQ-HUB-COMMON-001 and threat-model §4c.

### 2b. ESP32-P4 (ENT modules)

- **Hardware root**: no secure element (threat-model §4a — cite, do not restate). Device key
  lives in MCU-resident key storage.
- **Decision point 4 (scope doc)** — **ESP32-P4 key storage mechanism**: eFuse OTP block vs.
  flash-encryption-wrapped key.
  **Lean (owner not yet asked): eFuse read-protected key block as the base, WITH flash
  encryption ALSO enabled — belt-and-suspenders at ~$0 marginal cost.** Both mechanisms
  active simultaneously is the proposed baseline, not a fallback choice between them — the
  cost is negligible and each covers a different extraction path (eFuse read-protect vs. an
  attacker imaging flash directly).
  **OWNER ACTION NEEDED**: ratify this as the baseline mechanism, or direct otherwise.
- No identity certificate chain is proposed for modules at manufacture (see §4, decision
  point 3) — the module root is a raw device key, not an X.509 identity.

## 3. Key types and derivation map

| Key type | Lives on | Purpose | Derivation | Custody tier (proposed) |
|---|---|---|---|---|
| **Platform firmware-signing root** | Offline, air-gapped (not on any shipped device) | Signs the root-of-trust anchor that every Hub/module boot chain verifies against (REQ-HUB-COMMON-010, REQ-MOD-COMMON-012) | Root-generated, not derived | Root tier — see §4, decision point 1 |
| **Hub per-unit identity key** | PolarFire PUF-backed key store | IDevID-class device identity (REQ-HUB-COMMON-003) | PUF-derived at manufacture | Issuing tier, PolarFire-rooted |
| **Module per-unit device key** | ESP32-P4 eFuse block (+ flash encryption, decision point 4) | Identity for CAN/T1 challenge-response (REQ-MOD-COMMON-010) | Injected at flashing (§5), not silicon-derived (no PUF on ESP32-P4) | Issuing tier, injected not rooted-in-silicon |
| **Heartbeat derivation key (KDF)** | Derived from the module device key, module-side; corresponding value held by the Hub from provisioning | Produces the pin-7 heartbeat's hardware-timed response (REQ-MOD-COMMON-013 / REQ-HUB-COMMON-114) | KDF from the module device key — see decision point 5 for the response-method choice this key must support | Same tier as the module device key it derives from |
| **Tamper-log signing key** | Hub-side, separate from the Hub's identity/heartbeat-verification key material | Signs tamper/security-event log segments (REQ-HUB-COMMON-070) | **Proposed separate KDF-derived key, NOT the same key used for heartbeat verification or identity** — see decision point 7 | A dedicated sub-tier under the Hub's root, isolated from the module-facing challenge/verification key |

The heartbeat KDF key and the tamper-log signing key are called out separately because they
are the two places the scope document's decision points most directly shape the
architecture (points 5 and 7 below) — both remain proposals, not ratified designs.

## 4. Owner decision points (verbatim leans from the workstream scope, mapped to this hierarchy)

Every decision point below is copied from
`research/next-trajectory/scope-security-protocols.md` §"Decision points needing the
owner" and mapped onto where it binds in this hierarchy. **None of these are ratified.**
This section exists so the owner ratification pass (REQ-HUB-COMMON-011, D-ENT-5) has one
place to work through them.

### Decision point 1 — Key custody ceremony form

**Question**: offline air-gapped M-of-N ceremony vs. managed HSM service, for the
firmware-signing root.

**Lean**: offline M-of-N for the root; lower-tier online HSM for high-frequency operational
signing only if EST/SCEP volume warrants it.

**Where it binds**: this is the top of the hierarchy — the platform firmware-signing root
in §3. Everything else (Hub identity, module device keys, the heartbeat KDF, the tamper-log
key) ultimately chains to or is issued under this root, so this is the single highest-
consequence decision in the whole plan (risk #4 in the workstream scope: *"Key hierarchy
designed before the owner ratifies custody... could be thrown away"* — this is why this
document stays architecture-level and does not attempt to write the M-of-N ceremony
procedure itself).

**OWNER ACTION NEEDED.** Not assumed; §5 (provisioning) below is written to be compatible
with either outcome.

### Decision point 2 — HSM vs. offline CA for the issuing tier at manufacture

**Question**: what signs the per-unit identity/device-key material at the point of
manufacture — an HSM at the contract-manufacturer site, or an offline-signed batch process.

**Lean**: offline-signed batch manifest — avoids trusting network/HSM custody at a CM site
at this size.

**Where it binds**: the provisioning tie-in (§5) — specifically, whether per-unit key
material is signed live at the CM (requiring network/HSM trust at that site) or is
pre-computed/batch-signed offline and delivered as a manifest the CM's flashing station
consumes without itself holding signing authority. The lean favors the latter, which is
also the lower-attack-surface choice against the supply-chain-implant adversary
(threat-model §3, A6) — an offline batch manifest process gives a compromised or malicious
CM no live signing capability to abuse.

**OWNER ACTION NEEDED.**

### Decision point 3 — Per-family vs. per-unit cert chains

**Question**: full X.509 chain per module vs. raw device key + signed manifest.

**Lean**: raw key + signed manifest for modules; reserve full X.509/IDevID for the
PolarFire Hub, where 802.1AR alignment is already explicit (REQ-HUB-COMMON-003).

**Where it binds**: this is the split already reflected in §2/§3 above — the Hub carries a
genuine IDevID-class certificate chain (REQ-HUB-COMMON-003 requires this outright, it is
not optional), while modules are proposed to carry only a raw device key plus a signed
manifest entry (no per-module X.509 chain). This is a real architectural asymmetry between
the two silicon classes and should be stated as such rather than implied to be symmetric:
**the Hub has a certificate; the module has a key and a manifest row that vouches for it.**
The manifest itself must be signed by whatever the decision-point-2 outcome produces.

**OWNER ACTION NEEDED**, though this lean is lower-consequence than points 1/2 (it can be
revisited per-family without touching the root).

### Decision point 4 — ESP32-P4 key storage mechanism

Covered in §2b above. **Lean: eFuse read-protected block + flash encryption together.**
**OWNER ACTION NEEDED.**

### Decision point 5 — Heartbeat response-method default

**Question**: HMAC-SHA256-derived pulse pattern vs. ECDSA-P256-derived timing, for the
pin-7 heartbeat response REQ-HUB-COMMON-114/REQ-MOD-COMMON-013 describe.

**Lean**: HMAC-SHA256 as the only method at ship; keep the method-menu field open for
future options. Rationale (from the scope doc): asymmetric crypto buys little here because
the Hub already holds the symmetric key from provisioning, and compute-then-respond already
removes crypto compute time from the timed path — so ECDSA's asymmetric-key advantage
(Hub doesn't need the module's private key) is not actually needed in a scheme where the
Hub is the one who provisioned the key in the first place.

**Where it binds**: the heartbeat KDF key in §3. If HMAC-SHA256 is ratified as the sole
method at ship, the KDF key is a symmetric secret shared between module and Hub (derived at
provisioning, §5) — simpler custody than an asymmetric keypair would require, but it does
mean the Hub-side copy of every module's heartbeat key must itself be protected with
custody rigor proportionate to what it can forge (a compromised Hub could impersonate any
of its own modules' heartbeats). REQ-HUB-COMMON-114's "method-select field" and firmware-
defined method agility are preserved architecturally even if only one method ships first —
see the crypto-agility policy (deliverable #8, not this document) for how a method gets
added post-ship.

**OWNER ACTION NEEDED** (though the lean is well-reasoned and low-risk to defer, since the
method-menu field keeps the door open regardless of which default ships first).

### Decision point 6 — wolfCrypt build/OE scope

**Question**: FIPS posture on both silicon classes vs. Hub-only.

**Lean**: scope FIPS-embedded-module language to the Hub only for now; module crypto is
correct-by-design but not FIPS-claimed until the OE-extension picture is clearer (no
RISC-V-class OE currently exists on the validated list for the module's own MCU class
either, compounding the same gap REQ-HUB-COMMON-097 already names for the Hub).

**Where it binds**: this affects what claim can be made about the module device key and
heartbeat KDF key's cryptographic implementation (§3) in any compliance-facing document —
it does NOT change the key hierarchy's architecture, only which parts of it can carry a
FIPS-embedded-module claim. Recorded here so the two documents (this one and the eventual
crypto-agility policy, deliverable #8) don't drift on which silicon carries the claim.

**OWNER ACTION NEEDED**, lower urgency (compliance-facing, not safety-facing).

### Decision point 7 — Tamper-log signing key tier

**Question**: same device key as heartbeat/identity, or a separate log key.

**Lean**: separate KDF-derived log-signing key — compromise of one must not forge the
other's evidence trail.

**Where it binds**: directly the tamper-log signing key row in §3. This is the decision
point with the clearest security rationale to adopt as proposed: threat-model §3 (A7,
insider operator) identifies this exact key-separation as the property that keeps a
compromised heartbeat/identity key (or a privileged insider with access to it) from also
being able to forge the tamper log's own evidence trail retroactively — i.e., the log stays
trustworthy evidence of an incident even if the incident itself involved a key compromise.
**This document proposes the log-signing key be derived independently (its own KDF branch
off the Hub's PolarFire-rooted key material, not shared with or derivable from the module
challenge/heartbeat verification key held Hub-side).**

**OWNER ACTION NEEDED** to formally ratify, though this is the one decision point this
document recommends adopting as-leaned without much reservation — the alternative (shared
key) has a concrete, named failure mode (forgeable evidence) and no offsetting benefit
identified in the scope research.

## 5. Provisioning tie-in (architecture level only — full flow is deliverable #2, GATED on this document)

This section states only how provisioning must interact with the hierarchy above; the
step-by-step factory flow is explicitly out of scope here (workstream scope: deliverable #2
is "GATED on #1: needs the key hierarchy decided first — can't script injection before
knowing what's injected").

- **PolarFire Hub**: IDevID enrollment at manufacture, rooted in the PUF-backed key store
  (REQ-HUB-COMMON-003). Whatever signs that enrollment record is the decision-point-2
  outcome (HSM-at-CM vs. offline batch manifest).
- **ESP32-P4 module**: device-key injection happens "at the flashing step" per the scope
  document's own phrasing — i.e., the key is generated off-device and written into the
  module's eFuse/flash-encrypted storage during manufacture, NOT derived from module
  silicon (no PUF exists to derive from). This makes the injection process itself a
  higher-trust step than the Hub's PUF-rooted enrollment: **whoever performs the injection
  step has, for a brief window, custody of plaintext key material that will become
  permanent device identity.** This is exactly why decision point 2's lean (offline-signed
  batch manifest, no live network/HSM trust at the CM) matters most for the module side of
  the hierarchy — it minimizes the window and the parties who see key material in the
  clear.
- **Per-serial record**: whatever is recorded per serial number at provisioning (device
  public identity / manifest entry / issuance timestamp) must be sufficient to support
  REQ-MOD-COMMON-011's component-swap detection and REQ-HUB-COMMON-113's cross-surface
  validation later — i.e., the provisioning record IS the baseline that later attestation
  compares against. A supply-chain implant present before this record is created becomes
  the trusted baseline (threat-model §3, A6) — this is a structural limit of any
  provisioning-time record, not a gap specific to this design.
- **LDevID/EST-SCEP operator enrollment** (REQ-HUB-NET-004, Hub-side only): happens
  post-deployment, without physical access, and is separate from the manufacture-time
  identity above — an operator certificate proves "this Hub is enrolled to this operator's
  fleet," not "this Hub is genuine silicon," which the manufacture-time IDevID already
  covers.

## 6. Rotation and revocation (architecture-level)

- **Firmware-signing root**: rotation of the root itself is a rare, ceremony-gated event
  (tied to decision point 1's custody form) — out of scope to schedule here, but the
  hierarchy must support it: every downstream certificate/manifest needs a defined
  revalidation path if the root ever rotates, not an assumption that the root is permanent.
- **Per-unit identity/device keys**: not expected to rotate over a unit's service life under
  normal operation (they are the hardware-rooted or injected identity anchor) — compromise
  of one unit's key is handled via **revocation** (REQ-HUB-COMMON-114's untrust/
  re-admission state machine, deliverable #6) rather than rotation of that unit's key,
  since the key is fused/injected and not practically replaceable in the field on either
  silicon class.
- **Heartbeat KDF key**: inherits the module device key's non-rotation posture (§3 — it is
  derived from that key), so its revocation path is the same as the device key's:
  untrust/quarantine at the protocol level (REQ-HUB-COMMON-114), not a rekey.
- **Tamper-log signing key**: if adopted as its own KDF branch (decision point 7), it
  inherits rotation from whatever tier of the Hub's root it is derived under — no separate
  rotation schedule is proposed here; flagged for the eventual crypto-agility policy
  (deliverable #8) to specify a cadence if one is wanted.
- **Firmware-update signing key** (distinct from the platform root — an operational signing
  key used per release, not the root itself): this is the "lower-tier online HSM for
  high-frequency operational signing" the decision-point-1 lean allows for IF EST/SCEP
  volume warrants it. Proposed but not ratified: an operational signing sub-key, itself
  certified by the offline root, used for routine firmware releases so the root ceremony is
  not invoked per release. This is the standard "keep the root cold, use a certified
  intermediate for volume operations" pattern and is offered here as the natural fit for
  decision point 1's two-tier lean, not as a new decision.

## 7. Summary table — decision points at a glance

| # | Decision | Lean | Binds to | Status |
|---|---|---|---|---|
| 1 | Custody ceremony form (root) | Offline M-of-N; online HSM only for high-volume operational signing if warranted | Platform firmware-signing root (§3, §6) | **OWNER ACTION NEEDED — highest consequence** |
| 2 | HSM vs. offline CA at manufacture | Offline-signed batch manifest | Provisioning (§5), issuing tier under the root | **OWNER ACTION NEEDED** |
| 3 | Per-family vs. per-unit cert chains | Raw key + manifest for modules; full X.509/IDevID for the Hub | §2/§3 module vs. Hub asymmetry | **OWNER ACTION NEEDED** |
| 4 | ESP32-P4 key storage mechanism | eFuse read-protected block + flash encryption together | §2b module root | **OWNER ACTION NEEDED** |
| 5 | Heartbeat response-method default | HMAC-SHA256 only at ship; method-menu field kept open | §3 heartbeat KDF key | **OWNER ACTION NEEDED** (low risk to defer) |
| 6 | wolfCrypt FIPS scope | Hub-only FIPS-embedded-module claim for now | Compliance framing, not architecture | **OWNER ACTION NEEDED** (low urgency) |
| 7 | Tamper-log signing key tier | Separate KDF-derived log key, never shared with heartbeat/identity key | §3 tamper-log signing key | **OWNER ACTION NEEDED — recommended to adopt as leaned** |

## 8. What this document does NOT do

- It does not write the custody ceremony procedure (that is the D-ENT-5-gated act
  REQ-HUB-COMMON-011 requires, and per risk #4 in the workstream scope, deliberately not
  attempted before ratification).
- It does not specify the provisioning factory flow step-by-step (deliverable #2, gated on
  this document).
- It does not specify wire formats for the CAN/T1 challenge or the heartbeat frame
  (deliverable #3).
- It does not specify the tamper-log segment format (deliverable #5, gated on this document
  and deliverable #3).
- It does not restate the threat model's honest-limits language — see
  `threat-model-2026-07-02.md` §4 for the ESP32-P4 no-SE residual, the surface-independence
  classification, the TC-baseline DPA statement, and the two-chip fallback seam, all of
  which constrain what any key in this hierarchy can actually be trusted to prove.

---
*Cites: REQ-HUB-COMMON-001/003/004/010/011/070/097/113/114; REQ-MOD-COMMON-010/011/012/013;
`threat-model-2026-07-02.md`; `docs/enterprise-requirements/research/next-trajectory/
scope-security-protocols.md` deliverable #1 and decision points 1-7.*
