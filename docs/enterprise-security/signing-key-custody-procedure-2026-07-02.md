# CEC firmware signing-key custody procedure — DRAFT v0.1 (owner final sign-off pending)

> **STATUS: DRAFT PROCEDURE — direction ratified, procedure NOT yet final-signed.** The
> owner ratified the custody *direction* on the R7 item of
> `ratification/ratification-brief-2026-07-02.md` ("I agree with your recs" →
> "DIRECTION RATIFIED (offline M-of-N; procedure doc drafts next, final sign-off on the
> doc)"), per the recommendation in `ratification/briefs/signing-key-custody.md`. This
> document is that procedure draft. It satisfies REQ-HUB-COMMON-011 ("the signing-key
> custody procedure SHALL be documented and owner-ratified before first enterprise ship")
> **only once the sign-off box in §8 is completed** — until then this remains gate D-ENT-5,
> open. This document is executable-checklist style by design: every numbered step is
> something a person actually does on ceremony day or during an operational/compromise
> event, not architecture narrative. For the architecture this procedure implements, see
> `key-hierarchy-custody-2026-07-02.md` (deliverable #1) — this document does not restate
> that document's reasoning, only the concrete steps it left as an owner-ratified ceremony
> form. For the threat this procedure is the primary defense against, see
> `threat-model-2026-07-02.md` §3 (A6, supply-chain implant) — "the defense against a
> supply-chain implant is procedural (custody of the signing key, batch-manifest
> provenance)... more than cryptographic-protocol."

## 0. Scope — which key this procedure governs

This procedure governs the **platform firmware-signing root** only
(`key-hierarchy-custody-2026-07-02.md` §3, top row) — the offline, air-gapped key that
signs the root-of-trust anchor every Hub/module boot chain verifies against
(REQ-HUB-COMMON-010, REQ-MOD-COMMON-012). It also defines the **operational signing
sub-key** the root certifies for day-to-day use (§5), because the two are inseparable in
practice (the root exists specifically so it does NOT have to be invoked per release).

**Explicitly out of scope for this procedure** (governed elsewhere, cited not repeated):

- The PolarFire Hub's PUF-derived per-unit identity key and the ESP32-P4 module's injected
  per-unit device key — `key-hierarchy-custody-2026-07-02.md` §2, §3. This procedure's root
  signs the *manifest* that vouches for those keys at provisioning (§6); it does not
  generate or hold them.
- The heartbeat KDF key — derived from the module device key, not from this root
  (`key-hierarchy-custody-2026-07-02.md` §3, decision point 5).
- The tamper-log signing key — a separate KDF branch under the Hub's own PolarFire-rooted
  material, generated per-unit at manufacture, not a shared platform secret this ceremony
  produces (`key-hierarchy-custody-2026-07-02.md` §3, §4 decision point 7). Keeping it
  structurally separate from this root is precisely the point of that decision — do not
  fold tamper-log key custody into this procedure even for convenience.
- The signing algorithm/library choice itself (Ed25519 vs. ECDSA vs. wolfCrypt-validated
  RSA, etc.) is the crypto-agility policy's call (deliverable #8, not yet drafted) — this
  procedure is written to be algorithm-agnostic; wherever a step says "the keypair," it
  works unmodified once #8 names the algorithm.

## 1. Ceremony form (ratified) and the tunable parameter

**Ratified**: offline, air-gapped M-of-N ceremony for the root (R7, §above). **Not yet
ratified — flagged for the sign-off in §8**: the specific M and N values and the named
custodians. The workstream's recorded lean proposed 2-of-3 "at this company size" — this is
explicitly flagged as a size-dependent parameter, not a fixed design:

- **2-of-3 works cleanly** if there are at least 3 distinct trusted principals available to
  hold a share (e.g., the owner, a second engineering/security-cleared principal, and a
  neutral third-party escrow such as an attorney or bank safe-deposit box).
- **At a company small enough that fewer than 3 principals exist**, 2-of-3 SHOULD still be
  achieved by using an institutional custodian (attorney escrow, bank deposit box, or a
  dedicated hardware-security-module-as-a-share-holder) as one of the three shares, rather
  than reducing to a 1-of-N or 2-of-2 scheme that concentrates single-person or single-
  location risk — a scheme where the owner alone can reconstitute the root single-handedly
  defeats the point of M-of-N. **This is an explicit owner decision point, not assumed
  resolved by this document** (see §8).

## 2. Roles

| Role | Responsibility | Count |
|---|---|---|
| Ceremony lead | Runs the ceremony script, operates the air-gapped machine | 1 |
| Custodians | Each holds exactly one of the N shares | N |
| Witness | Observes the entire ceremony, does not touch key material, signs the ceremony log | ≥1, independent of the custodians where feasible |
| Scribe | Records the ceremony log contemporaneously (may be the witness) | 1 |

At the small-company scale this platform is at today, one person may hold more than one
*role* (e.g., the owner is both ceremony lead and a custodian) but SHALL NOT be more than
one *custodian* — no single person holds two of the N shares, or the M-of-N property is
fiction.

## 3. Pre-ceremony checklist

- [ ] Air-gapped machine identified and verified: no Wi-Fi/Bluetooth radio present or all
      radios physically disabled/removed, no network cable connected during the ceremony,
      freshly imaged OS from verified installation media (checksum-verified against a
      source fetched on a *different*, online machine beforehand).
- [ ] Ceremony software staged onto the air-gapped machine via a single-use, freshly
      formatted USB medium (key-generation tool + share-splitting tool + their checksums,
      verified against the checksums fetched online).
- [ ] N blank hardware tokens/smartcards (or N single-use encrypted USB media, if hardware
      tokens are not yet procured) acquired for the shares, one per custodian.
- [ ] Ceremony location booked with the witness and all custodians able to attend physically
      (a real M-of-N ceremony requires the shares to be split and distributed in the same
      physical session, not mailed out piecemeal).
- [ ] Ceremony log template prepared (date, participants, machine identity/checksums,
      steps performed, root public-key fingerprint once generated, share-receipt
      acknowledgments) — see §4 step 8 for what it must contain.
- [ ] Custody media (safe, safe-deposit box, escrow agreement) confirmed available for each
      custodian's share BEFORE the ceremony date, so no share leaves the ceremony room
      without its destination already arranged.

## 4. Ceremony-day procedure

1. **Verify the air gap.** Confirm no network interface is active (physically disconnect
   or disable in firmware/OS settings, verified by the witness, not just the ceremony lead).
   Log the verification.
2. **Generate the root keypair** on the air-gapped machine, using the algorithm named by
   the crypto-agility policy (deliverable #8) — if #8 has not yet named one at ceremony
   time, this step and the whole ceremony SHOULD be deferred rather than picking an
   algorithm ad hoc under time pressure; a re-ceremony to change algorithms later is exactly
   the "root rotation is a rare, ceremony-gated event" case
   `key-hierarchy-custody-2026-07-02.md` §6 already names as costly.
3. **Immediately compute the root public-key fingerprint** and read it aloud for the
   witness/scribe to record in the ceremony log verbatim — this is the value that gets
   committed into the repo and provisioning tooling later (§6), and it must be captured
   before the private key is ever split or touched further.
4. **Split the private key into N shares (Shamir's Secret Sharing or an equivalent
   documented threshold scheme) requiring M to reconstruct.** Use a well-reviewed, offline
   SSS implementation (do not hand-roll one for this ceremony). Write each of the N shares
   to its own token/medium immediately as it is produced — do not let multiple shares exist
   unencrypted on the generation machine's disk simultaneously any longer than the
   splitting operation requires.
5. **Verify reconstruction before destroying anything.** Using a *scratch, still-air-gapped*
   working area, feed exactly M of the N freshly-written shares back into the reconstruction
   tool and confirm the reconstructed private key's fingerprint matches step 3's recorded
   value. If it does not match, STOP — do not proceed to distribution; regenerate from step
   2. This is the single most important checkpoint in the ceremony: a share set that cannot
   reconstruct is worse than no ceremony at all, because it is only discovered the day it is
   needed.
6. **Securely erase all intermediate key material from the generation and scratch
   machines** — the assembled private key, temporary reconstruction outputs, and any
   scratch files, using the OS's secure-erase facility or full-disk wipe if the machine is
   dedicated to this purpose. Only the N distributed shares and the recorded public-key
   fingerprint SHALL survive the ceremony.
7. **Distribute shares to custodians, one each, with a signed receipt.** Each custodian
   signs (physically, on the ceremony log) an acknowledgment that they received exactly one
   share and know its designated storage location (§3's pre-arranged custody media). Shares
   SHOULD go to at least M distinct physical locations so no single location breach yields
   M shares (e.g., under a 2-of-3 scheme: not all 3 shares in the same office safe).
8. **Complete and sign the ceremony log**, containing at minimum: date/time, all
   participants and their roles, the air-gapped machine's identity and software checksums,
   the root public-key fingerprint, the M-of-N parameters used, each custodian's signed
   receipt, and the witness's signature attesting the above steps were followed in order.
   The log itself is a durable artifact — store a copy with each custodian's share package
   and a master copy in the company's permanent records (not solely on any single machine).
9. **Publish the root public-key fingerprint** into the repository (a CODEOWNERS-protected
   path, consistent with this repo's branch-protection posture for `cec-policy.json` and
   `promoted/**`) and into whatever provisioning/manufacturing tooling verifies signed
   manifests (§6) — the public fingerprint is not secret and having it under version control
   with review-gated changes is itself a control against a later, undetected root swap.

## 5. Operational signing tier (day-to-day releases)

The root from §4 is **never** used to sign an individual firmware release. It is invoked
exactly once per its own lifetime event: to certify an **operational signing sub-key**.

1. At a (much lighter-weight, non-M-of-N) session, reconstitute the root per §4 step 5's
   procedure (M custodians convene, reconstruct, use, re-erase — the root's private key
   material SHALL exist only transiently, for the duration of this certification step, and
   never persist assembled on any machine after).
2. Generate an operational sub-keypair and have the reconstituted root sign a certificate
   binding the sub-key to the platform (algorithm/format per deliverable #8, same note as
   ceremony step 2).
3. Re-erase the assembled root immediately after signing the sub-key certificate,
   identically to §4 step 6.
4. The **operational sub-key** — not the root — signs every day-to-day firmware release
   from this point forward. Custody of the operational sub-key:
   - **Lean (per `key-hierarchy-custody-2026-07-02.md` decision point 1)**: a lower-tier
     online HSM is justified *only if* EST/SCEP enrollment volume warrants it; at current
     volume, the operational sub-key SHOULD instead live on a single hardware security token
     held by a designated release engineer, access-controlled but not ceremony-gated —
     its blast radius is bounded, because a sub-key compromise is recoverable by revoking
     that sub-key and re-certifying a new one under the (still-offline, still-safe) root,
     without touching per-unit device keys or the root itself.
5. **Sub-key rotation cadence** — PROPOSED, not fixed by any REQ row found: rotate the
   operational sub-key on a fixed cadence (e.g., annually, or at each major release train,
   whichever is more frequent) as routine hygiene, independent of any compromise event.
   This cadence is a placeholder for the owner to set or delegate; treat it as tunable, not
   load-bearing security architecture.

## 6. Provisioning-line key-injection tie

This procedure's output feeds manufacturing exactly the way
`key-hierarchy-custody-2026-07-02.md` §5 and decision point 2 describe — as an
**offline-signed batch manifest**, never as live signing capability at the contract
manufacturer:

1. Per-unit key material (Hub PUF-derived identity enrollment records; ESP32-P4 module
   device keys generated off-device for injection at flashing) is assembled into a batch
   manifest listing serial numbers and their associated public identity/key material.
2. The manifest is signed **offline, by the operational sub-key (§5)** — not the root, and
   not live at the CM site. This is the load-bearing control against the supply-chain-
   implant adversary (threat-model §3, A6): a compromised or malicious CM never holds any
   signing capability, only a signed file it cannot forge or extend.
3. The signed manifest is delivered to the CM's flashing station as a file. Flashing
   tooling SHALL verify the manifest's signature against the operational sub-key's known
   public key (itself verifiable back to the published root fingerprint, §4 step 9) before
   injecting any key material or provisioning record for a unit — an unsigned or
   incorrectly-signed manifest SHALL cause the flashing station to refuse the batch, not
   proceed with a warning.
4. Completed-unit status (serial, injection timestamp, pass/fail) is reported back from the
   CM and recorded as the per-serial provisioning record — this record becomes the
   baseline REQ-MOD-COMMON-011's component-swap detection and REQ-HUB-COMMON-113's
   cross-surface validation compare against later
   (`key-hierarchy-custody-2026-07-02.md` §5).
5. **Known structural limit, stated plainly rather than assumed away**: a supply-chain
   implant introduced before this manifest record is created becomes the trusted baseline
   (threat-model §3, A6) — this procedure minimizes the *injection-time* attack surface
   (no live CM signing authority to abuse) but does not, and cannot by itself, catch an
   implant present earlier in the CM's own build process. That gap is named, not solved,
   here; it is the reason REQ-MOD-COMMON-043's power-signature screening exists as a
   (explicitly blind-spot-carrying) supplementary control.

## 7. Key-compromise and rotation runbook

### 7a. Suspected operational sub-key compromise

Trigger examples: the release engineer's hardware token lost/stolen, a build machine that
touched the sub-key found compromised, an unexplained firmware release appears signed that
the release process did not produce.

1. Treat as compromised immediately on suspicion — do not wait for confirmation before
   beginning revocation.
2. Reconstitute the root (§5 step 1) for the sole purpose of signing a revocation record
   for the compromised sub-key, then immediately certify a fresh replacement sub-key
   (§5 steps 1–3 in the same session, minimizing root-reconstitution events).
3. Distribute the new sub-key to a (potentially different) designated release engineer;
   destroy or physically disable the old hardware token.
4. Any firmware release signed by the compromised sub-key after the suspected-compromise
   date SHALL be treated as untrusted pending investigation — do not assume a signed
   release is safe merely because it verifies against a not-yet-revoked sub-key if the
   compromise window is uncertain.
5. Notify per REQ-HUB-COMMON-014/097's PSIRT posture if the compromise is assessed as
   security-relevant to customers (this runbook does not itself define the PSIRT
   notification thresholds — that is the compliance workstream's artifact).

### 7b. Suspected root compromise (the severe case)

1. This is an emergency M-of-N re-ceremony: assemble the required M custodians, generate an
   entirely new root keypair (§4 steps 1–9 in full, not abbreviated), and treat the old root
   as permanently revoked.
2. **Open risk, flagged rather than answered here**: if the platform's secure-boot trust
   anchor is written into one-time-programmable (OTP) fuses on already-fielded Hubs/modules
   with no revocation-counter or multi-root-slot mechanism, a root compromise may not be
   remotely recoverable on units already in the field — this procedure cannot determine
   from the documents available whether the PolarFire/ESP32-P4 secure-boot implementation
   (REQ-HUB-COMMON-010, REQ-MOD-COMMON-012) supports a root-revocation or multi-slot
   mechanism. **This SHOULD be confirmed with the firmware/fabric workstream before this
   procedure is treated as fully closing the "root compromise" case** — if no such mechanism
   exists, a root compromise on fielded units may require a hardware re-spin or a
   field-service action, not a signing-side fix alone, and that honest limit belongs in the
   threat model (§4) once confirmed, not silently assumed resolved here.
3. All future firmware releases (and the operational sub-key itself) are re-certified under
   the new root (§5).
4. All manufacturing batch manifests in flight are re-signed under the new operational
   sub-key before any further units are provisioned (§6).

### 7c. Rotation cadence summary

| Key | Rotation trigger | Cadence |
|---|---|---|
| Root | compromise only (§7b) | rare, ceremony-gated, no fixed schedule (`key-hierarchy-custody-2026-07-02.md` §6) |
| Operational sub-key | compromise (§7a) OR routine hygiene | PROPOSED annual/per-release-train (§5 step 5), tunable |
| Manufacturing batch manifest signature | every batch | per-batch by construction (§6) |
| Per-unit device/identity keys | not rotated in the field | revoked via the untrust/re-admission state machine (`untrust-state-machine-2026-07-02.md`), not rekeyed — the key is fused/injected and not practically field-replaceable |
| Tamper-log signing key | out of this procedure's scope | see `key-hierarchy-custody-2026-07-02.md` §4 decision point 7, §6 |

## 8. OWNER SIGN-OFF

This section is the completion gate for REQ-HUB-COMMON-011 / D-ENT-5. Check each box only
once actually confirmed; an unchecked box means this procedure is NOT yet ratified as final
and D-ENT-5 stays open.

- [ ] **Ceremony form** confirmed: offline, air-gapped M-of-N ceremony for the firmware-
      signing root (per R7, `ratification/ratification-brief-2026-07-02.md`).
- [ ] **M value**: ______  **N value**: ______ (workstream lean: 2-of-3; confirm or amend).
- [ ] **Named custodians** (one share each, no person holds two shares):
      1. ________________________
      2. ________________________
      3. ________________________ (add rows if N > 3)
- [ ] **Share storage locations** confirmed available and physically distinct (at minimum M
      distinct locations):
      1. ________________________
      2. ________________________
      3. ________________________
- [ ] **Ceremony date** scheduled: ________________________
- [ ] **Witness** named: ________________________
- [ ] **Operational sub-key custody** confirmed (§5): single hardware token / release
      engineer, name: ________________________ (or: online HSM, justified by stated EST/SCEP
      volume — describe: ________________________)
- [ ] **Root-compromise field-recoverability question** (§7b.2) confirmed answered by the
      firmware/fabric workstream before this procedure is treated as covering that case.
- [ ] **Sub-key rotation cadence** confirmed or amended from the §5/§7c proposal: ______

**Owner signature**: ________________________  **Date**: ________________________

Once every box above is checked and signed, this document supersedes its DRAFT status,
REQ-HUB-COMMON-011's gate closes, and `key-hierarchy-custody-2026-07-02.md` decision point 1
moves from "OWNER ACTION NEEDED" to ratified.

---
*Cites: REQ-HUB-COMMON-010/011/014/097; REQ-MOD-COMMON-011/012/043;
`ratification/ratification-brief-2026-07-02.md` (R7); `ratification/briefs/
signing-key-custody.md`; `key-hierarchy-custody-2026-07-02.md` §3–§7 (decision points 1, 2,
4, 5, 7); `threat-model-2026-07-02.md` §3 (A6); `untrust-state-machine-2026-07-02.md` §5;
`docs/enterprise-requirements/research/next-trajectory/scope-security-protocols.md`
deliverable #2, decision points 1–2, risk #4.*
