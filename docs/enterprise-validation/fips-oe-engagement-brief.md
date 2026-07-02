# FIPS OE-extension engagement brief (wolfCrypt vendor one-pager)

Verification artifact for **REQ-HUB-COMMON-097**. `verification-map.json` artifact key:
`fips-oe-engagement-brief`. **Status: brief only — vendor engagement not yet started**;
trigger to start is firmware kickoff (§4), per REQ-097's own text.

## 1. What "embeds a validated cryptographic module" requires operationally

The platform's FIPS posture is **never** an owned CMVP submission. It is: ship a
wolfCrypt build that is *itself* a CMVP-validated module, run on an Operational
Environment (OE) that is on that certificate's tested/permitted-ported OE list — or
formally extend the OE list via the vendor's ported-OE process. Operationally this
means, before any FIPS-adjacent claim is made:

1. Identify the **exact validated wolfCrypt certificate** (module name + version) the
   build ships, not "wolfCrypt" generically.
2. Confirm the **build configuration matches** the certificate's tested configuration
   (compiler, compile flags, integrity-check self-test wiring) — a mismatched build
   is not the validated module, regardless of source-code identity.
3. Confirm the **OE (SoC + RTOS)** is either already on the certificate's tested/
   permitted-ported OE list, or pursue the vendor's OE-extension process (§2) before
   claiming coverage.
4. Re-verify all of the above at every wolfCrypt version bump — an OE-extension or
   validated-configuration claim does not automatically carry forward across versions.

## 2. The RISC-V / PolarFire OE gap

**No RISC-V-class Operational Environment currently exists on wolfCrypt's validated OE
list** — this is true for both silicon classes the platform uses: the Hub's PolarFire
SoC MSS RISC-V complex, and (per the key-hierarchy custody doc's decision point 6) the
module MCU class as well. Questions to raise with the vendor at engagement:

- Does an OE-extension/ported-OE request for a **PolarFire SoC MSS (RISC-V, Core line,
  MPFS095TC baseline per REQ-HUB-COMMON-001) + Zephyr** pairing have any precedent, or
  would this be a first-of-kind request?
- What evidence does the vendor's OE-extension process require (regression test
  results, build-environment attestation, compiler/toolchain version pinning)?
- What is the realistic timeline and cost for an OE-extension vs. waiting for the
  vendor to add RISC-V/Zephyr to their own tested-OE roadmap?
- Does the Athena (S-suffix, MPFS095TS) DPA-hardened silicon option change the OE
  question, or is OE scope silicon-class-independent of the DPA/side-channel hardware?

## 3. FIPS-claim scope: Hub only (ratified lean)

Per the key-hierarchy custody doc's decision point 6: **the FIPS-embedded-module claim
is scoped to the Hub only, for now.** Module cryptography (device-key operations, the
CAN/T1 challenge-response, the pin-7 heartbeat KDF) is correct-by-design but is **not**
FIPS-claimed — the module MCU class has the same missing-OE gap as the Hub, without
even a candidate engagement started. This scope is an owner-action-needed item, low
urgency (compliance-facing, not safety-facing) — do not let this brief be read as
already-ratified beyond that lean.

## 4. CAVP-vs-CMVP claim guardrail

**CAVP (algorithm) validation is not module validation.** A wolfCrypt build passing
CAVP algorithm testing (AES, SHA, HMAC, etc. correctness) proves nothing about CMVP
module-level validation (self-tests, key management, tamper evidence, physical
security level). Never cite a CAVP certificate number as if it were a CMVP module
certificate, and never let "the algorithms are CAVP-tested" stand in for "this build
embeds a validated module." See `compliance-claims-lint.md` for the mechanical check.

## 5. Engagement trigger

Per REQ-HUB-COMMON-097: **firmware kickoff** is the trigger to start the vendor
engagement (§2's questions) — not before. Writing this brief now is explicitly
authorized ahead of that trigger; opening the actual vendor conversation is not.
