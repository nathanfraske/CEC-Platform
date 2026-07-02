# CEC Enterprise threat model — DRAFT v0.1

> **STATUS: DRAFT — pre-ratification working draft.** This is Security Workstream
> deliverable **#7** (`docs/enterprise-requirements/research/next-trajectory/scope-security-protocols.md`,
> "Can start NOW" — no dependencies). It has NOT been reviewed by the owner and carries no
> ratification. Nothing in this document overrides a locked platform decision
> (`CLAUDE.md`) or a REQ row; where this document and a REQ register disagree, the REQ
> register wins and this document should be corrected.
>
> **This document is the CANONICAL source of the platform's honest-limits security
> language.** Every downstream security/marketing/spec document that needs to state what
> the ENT security architecture does or does not defend against SHALL cite this document
> by section, not restate or re-derive its own version of these claims (risk #1 in the
> workstream scope: *"ESP32-P4 key-extraction honesty gets quietly dropped in later
> marketing/spec language... the threat-model doc is the canonical source of this
> language; every downstream doc cites it rather than restating"*). If a claim in this
> document needs to change, change it here first.

## 0. Scope and method

This threat model covers the ENT Hub (PolarFire SoC) ↔ ENT module (ESP32-P4) trust
relationship and the physical/network attack surfaces the platform's security protocol
elements (DETECT + poke-and-ack, CAN challenge-response, T1-link attestation, the pin-7
heartbeat, the tamper log, secure boot) are meant to address. It does NOT re-derive the
firmware/PSIRT/CRA compliance posture (REQ-HUB-COMMON-014/094-099) or the FMEA/fail-passive
power-path analysis (REQ-MOD-COMMON-030-032) — those are separate registers with their own
verification.

Method: for each adversary class, state (a) what capability the adversary has, (b) which
protocol elements are in scope to resist it, (c) what each element actually buys, and (d)
the residual risk in plain language. Every claim here is written to be falsifiable and
citable — no "hardened," "secure," or "tamper-proof" without a specific mechanism attached.

## 1. Adversary classes

| Class | Capability assumed | Access model |
|---|---|---|
| A1 — Evil-maid physical | Unsupervised physical access to a fielded Hub or module for a bounded window (minutes–hours); may open the enclosure, probe test points, desolder/replace a part, or re-flash via a debug/programming interface. No prior key material. | Physical, offline, time-boxed |
| A2 — CAN-bus insider node | Controls or has compromised one legitimate node on the shared CAN bus (a module or a rogue device wired onto pins 3/6). Can inject, replay, or withhold frames on the shared medium; cannot control pin-7 (point-to-point) or the T1 link of another port. | Logical, on-bus, persistent |
| A3 — Extracted-device-key relay/replay | Has physically extracted a specific module's MCU-resident device key (via A1-class access or a lab-grade attack) and now runs it in an emulator or relay device, attempting to impersonate that module from a *different* physical location/port. | Logical, key-possessing, remote-relay |
| A4 — T1-path compromise | Controls or has inserted a device on the 100BASE-T1 pair (pins 4/5) — a bridge, tap, or compromised switch-equivalent function — able to observe, delay, or manipulate T1 traffic without controlling CAN or pin-7. | Logical, on-link (single surface) |
| A5 — Pin-7 jamming | Can hold, short, or flood the pin-7 line at a single port (physical access to that port's wiring) but does not possess any cryptographic key. Goal is denial-of-service or forcing a fail-open condition, not impersonation. | Physical/logical, single-port DoS |
| A6 — Supply-chain implant | Introduces a hardware or firmware modification during manufacture or in the distribution channel (rogue component, backdoored firmware image, substituted part) before the unit ever reaches the field. | Manufacturing/logistics, pre-deployment |
| A7 — Insider operator | Holds legitimate operator/administrator credentials on the northbound management plane (REQ-HUB-NET-023) or physical console access, and abuses that legitimate access (configuration change, evidence tampering, unauthorized re-admission) rather than attacking the crypto. | Logical/physical, authorized-but-malicious |

These map directly to the scope document's named classes (evil-maid, CAN-bus insider,
extracted-device-key relay/replay, T1-path compromise, jamming) plus two the register work
already surfaces as load-bearing: supply-chain implant (REQ-MOD-COMMON-043's screening-tier
carve-out; REQ-HUB-COMMON-099's NDAA §889/§5949 exclusion) and insider operator
(REQ-HUB-COMMON-023's role separation + audit log).

## 2. Protocol elements under evaluation

| Element | Requirement | What it is |
|---|---|---|
| DETECT analog class + poke-and-ack | REQ-HUB-COMMON-042; REQ-MOD-COMMON-010 | Pin-8 resistor-divider link-capability code (§2.3) plus a liveness poke/acknowledge exchange on the same analog line. Physical-layer, no cryptographic key. |
| CAN challenge-response | REQ-HUB-COMMON-113; REQ-MOD-COMMON-010 | Hub-issued challenge answered by the module over the shared CAN bus (pins 3/6), keyed to the module's MCU-resident device key. |
| T1-link attestation/behavioral checks | REQ-HUB-COMMON-113; REQ-MOD-COMMON-003 | Attestation and behavioral-consistency checks carried over the per-port 100BASE-T1 link. |
| Pin-7 heartbeat (challenge + hardware-timed response) | REQ-HUB-COMMON-112/114; REQ-MOD-COMMON-013 | Per-port point-to-point challenge; module answers with a hardware-timer-scheduled edge/pulse pattern derived from its device key + a per-challenge nonce. Compute-then-respond: crypto time is off the timed path. |
| Tamper/security event log | REQ-HUB-COMMON-070/071 | Rollback-resistant, signed, persist-on-fault event log at the Hub. |
| Secure boot + anti-rollback | REQ-HUB-COMMON-010; REQ-MOD-COMMON-012 | Signature-chained boot to a platform root; monotonic anti-rollback state. |

## 3. Per-adversary analysis

### A1 — Evil-maid physical

| Protocol element | Defends? | Why / residual |
|---|---|---|
| DETECT poke-and-ack | Partial | Detects a module physically removed/replaced with a different or absent module (class code / liveness changes) — but only if the swap actually changes the DETECT line's electrical behavior. A like-for-like swap with an identical resistor code is invisible to DETECT alone. |
| CAN challenge-response | Partial | If the attacker cannot read the device key off the original part before swapping it, a substituted module fails the challenge and is caught at the next cycle. If the attacker DID extract the key first (→ A3), this element alone does not distinguish original from clone. |
| Pin-7 heartbeat | Strong, for in-place tampering | An evil-maid who opens the case but leaves the module in its port faces the full timing-bound challenge on every heartbeat interval (default N=3 @ 1 Hz, REQ-HUB-COMMON-114) — any interposer device inserted inline to intercept/relay adds latency and fails the single-digit-µs acceptance window (see §5, distance-bounding-lite). |
| Secure boot | Strong, for firmware modification | Blocks booting a re-flashed image that isn't signed to the platform root; anti-rollback blocks reverting to a known-vulnerable signed image. |
| Tamper log | Evidentiary, not preventive | Records the event (chassis-open sensors, DETECT/CAN/heartbeat anomalies) with rollback-resistant, persist-on-fault integrity — but does not prevent the physical act itself. |

**Residual**: an evil-maid with enough time and lab equipment to (a) extract a device key
without disturbing DETECT/tamper sensors and (b) fabricate a like-for-like electrical/CAN
twin defeats DETECT and CAN alone. The pin-7 heartbeat is the element that still catches
this case, because it demands the key be exercised in hardware-timed real time from the
physical port — see §5. Physical chassis tamper sensing (module/hub enclosure switches) is
out of this document's scope (tamper research register) but feeds the same log.

### A2 — CAN-bus insider node

| Protocol element | Defends? | Why / residual |
|---|---|---|
| CAN challenge-response alone | **Insufficient for high-trust operations** | CAN is a shared bus (pins 3/6); any node on it can observe a challenge and, if it possesses (or can relay to) the correct key, answer. This is exactly risk #2 in the workstream scope: *"CAN-shared-bus replay/relay surface undermines the identity challenge if pin-7 heartbeat is treated as optional."* Per that scope's mitigation and REQ-HUB-COMMON-114, CAN-only challenge-response is explicitly declared **NOT sufficient** for MC-Max voting/actuation-class trust decisions; pin-7 is the required gating surface for those. |
| Pin-7 heartbeat | Strong complement | Pin-7 is per-port point-to-point at the ENT hub (REQ-HUB-COMMON-112 realization) — a node on the shared CAN bus cannot observe or answer another port's pin-7 challenge, because it has no electrical path to that wire. An insider CAN node can relay a *nonce it overhears on CAN* to a colluding device physically wired to the target port, but that relay path is exactly what the heartbeat's timing bound is built to catch (§5). |
| Tamper log + cross-surface validation | Detective | REQ-HUB-COMMON-113 requires the Hub to cross-validate at least two independent surfaces and alarm on inconsistency — a module answering CAN correctly but failing/missing its pin-7 heartbeat is flagged rather than silently trusted. |

**Residual**: a CAN insider that also controls (or colludes with a device on) the specific
target port's physical pins can attempt a full relay; whether that succeeds depends
entirely on whether the relay path adds enough latency to trip the pin-7 timing window
(§5) — this is the honest boundary, not "CAN is safe."

### A3 — Extracted-device-key relay/replay

This is the central case the ESP32-P4 no-SE residual (§4a) exists to be honest about.

| Protocol element | Defends? | Why / residual |
|---|---|---|
| DETECT poke-and-ack | No | Key-independent (§4b) — it validates presence/class, not identity, so a key-extraction attack is entirely outside its detection surface either way. |
| CAN challenge-response | No, alone | Once the key is extracted, an emulator answers CAN challenges correctly from anywhere with bus access. This is why REQ-HUB-COMMON-114 exists as an independent check, not a redundant one. |
| Pin-7 heartbeat | **Yes — this is the specific defense** | The heartbeat does not attempt to prove the key was never extracted (it cannot — see §4a). It proves the answering party is answering **from the physical port, in hardware real time**. An extracted key run in a relay/proxy/tunnel device physically elsewhere must get the nonce (over CAN/T1), compute the response, and get the response edge back to the challenged port — REQ-HUB-COMMON-114's stated design point is that this round trip costs "≥tens of µs" against a single-digit-µs acceptance window, i.e. relay/proxy/tunnel insertion measurably fails even with a perfectly correct key. This is explicitly a distance-bounding-lite property, not a key-secrecy property (§5). |
| Tamper log | Evidentiary | The transition to UNTRUSTED (missed/invalid heartbeats, N=3@1Hz default) is logged with the challenge transcript (REQ-HUB-COMMON-114) — forensically distinguishes "key was fine, port went dark" from "key answered correctly but not from this port." |

**Residual (stated plainly, per REQ-MOD-COMMON-010's honesty framing)**: an attacker who
extracts a module's device key AND can install a relay device physically wired into the
*same port* the original module occupied (not just anywhere on the bus) defeats the
heartbeat's distance bound — the timing-bound property only holds across a real
transmission-line/relay latency delta, not against a device co-located at the port. Nothing
in the current protocol set is designed to catch a same-port physical substitute holding a
valid extracted key; that case ultimately reduces back to A1 (evil-maid), where DETECT
class-code drift and the tamper log's physical-open evidence are the remaining backstops.

### A4 — T1-path compromise

| Protocol element | Defends? | Why / residual |
|---|---|---|
| T1-link attestation/behavioral checks | Partial, single-surface | Detects certain link-level anomalies but is itself the compromised surface in this scenario — REQ-HUB-COMMON-113 explicitly does not let the Hub trust a single surface. |
| Pin-7 heartbeat | **Independent, per REQ-HUB-COMMON-114** | The heartbeat is explicitly designed as "a port-bound surface INDEPENDENT of the T1 stack... the heartbeat is the port-bound cross-check that does NOT share fate with a dark, misconfigured, or compromised T1 path" (REQ-HUB-COMMON-114). A T1-path compromise that blinds or manipulates T1-carried attestation does not, by itself, give the attacker any way to forge pin-7 responses, because pin-7 does not depend on T1 for the timed portion of the exchange (only the nonce delivery may ride CAN/T1 ahead of the window; a T1 compromise that also controls CAN can delay nonce delivery, which is a denial/delay case, not a forgery case). |
| CAN challenge-response | Partial | Unaffected by a T1-only compromise (different wire pair, different transceiver) unless the attacker also controls CAN (→ A2). |

**Residual**: T1 is a rich, protocol-heavy link (802.1AS/1588v2, LAN9370 switching) and is
inherently a larger and less-audited surface than CAN or the analog pin-7 line; the design
intentionally does not make T1 the sole or even primary trust anchor for exactly this
reason. A T1 compromise combined with a CAN compromise (attacker controls both shared
surfaces) still leaves the per-port pin-7 timing bound as the last independent check.

### A5 — Pin-7 jamming

| Protocol element | Defends? | Why / residual |
|---|---|---|
| Pin-7 heartbeat | Fail-secure, not fail-available | REQ-HUB-COMMON-114 states this directly: "Jamming is fail-secure: a held/shorted pin 7 fails that port's heartbeats → auto-untrust + alarm (port-local, per REQ-HUB-COMMON-110 containment)." A jammed port loses trust and is quarantine-tagged, not silently bypassed. |
| REQ-HUB-COMMON-110 containment | Yes | A fault at one port (including a 57 V mis-plug insult) cannot reach the shared sync/heartbeat domain or disturb other ports — jamming is inherently port-local by the per-port pin-7 architecture. |
| Media-access discipline | Yes | REQ-HUB-COMMON-114 requires heartbeat slots never mask or delay a FREEZE assertion — a jamming attacker cannot use heartbeat traffic to suppress the platform's own safety-critical trigger. |

**Residual**: jamming is a denial-of-service against that one module's trust status (it
gets quarantine-tagged, telemetry continues but is flagged, and the module is excluded
from MC-Max voting/actuation) — not a way to gain trust, forge identity, or disturb other
ports. This is an intentional design trade (fail-secure over fail-available) and should be
stated as such to operators: an attacker who cannot break the crypto can still take one
module's *trust status* offline by shorting a wire, and that is treated as expected,
alarmed behavior, not a gap.

### A6 — Supply-chain implant

| Protocol element | Defends? | Why / residual |
|---|---|---|
| Secure boot + anti-rollback | Partial | Blocks a *firmware*-only implant from running unsigned/rolled-back code post-manufacture — but if the implant is introduced BEFORE the signing step (a compromised build pipeline, a malicious contract manufacturer inserting extra hardware, or key material stolen during provisioning), secure boot verifies a legitimately-signed-but-compromised image correctly and offers no defense. |
| Key hierarchy / provisioning custody | The actual control point | This adversary class is why `key-hierarchy-custody-2026-07-02.md` §5 (provisioning tie-in) and the owner-ratified signing-key custody procedure (REQ-HUB-COMMON-011, D-ENT-5) exist — the defense against a supply-chain implant is procedural (custody of the signing key, batch-manifest provenance, BOM lint per REQ-HUB-COMMON-099) more than cryptographic-protocol. |
| Power-signature fingerprinting (REQ-MOD-COMMON-043) | Screening only, explicit blind spot | REQ-MOD-COMMON-043 requires documentation to state the verified blind spot: "dormant implants not exercised during profiling are invisible." This document adopts that same honesty framing rather than restating it differently — see §4 pattern. |
| Tamper log + attestation (REQ-MOD-COMMON-011) | Detective, post-deployment | Component-swap detection catches a *later* substitution against the manufacture-time baseline, but cannot catch an implant present at first attestation (it becomes the trusted baseline). |

**Residual**: this class is the least addressed by the runtime protocol elements in §2 and
the most addressed by process (manufacturing custody, provisioning discipline, BOM
sourcing exclusions). Flagged for the crypto-agility/compliance workstreams
(scope-doc deliverable #8/#9) rather than solved here.

### A7 — Insider operator

| Protocol element | Defends? | Why / residual |
|---|---|---|
| Role-separated access + audit log (REQ-HUB-NET-023) | Detective | An administrator abusing legitimate access is logged, but role separation does not prevent an administrator-level account from doing administrator-level damage — it bounds a lower-privileged (viewer/operator) account. |
| Re-admission requiring full identity re-attestation (REQ-HUB-COMMON-114) | Yes, specifically against one insider move | An insider cannot re-admit an untrusted/quarantined module by merely resuming its heartbeat — REQ-HUB-COMMON-114 requires full re-attestation (REQ-MOD-COMMON-010), which an operator-level account cannot fabricate without the device key. |
| Tamper log signing key separate from device/heartbeat key (custody doc lean #7) | Load-bearing here | If an insider with operator access could forge tamper-log entries using the same key material used elsewhere, they could erase evidence of their own actions. A separate log-signing key (proposed, not yet ratified — see custody doc §4) means compromising operator credentials or even a device key does not by itself let the insider forge the log's evidence trail. |

**Residual**: this class is bounded by access control and log integrity design, not by the
challenge-response protocols in §2 (which authenticate modules to the Hub, not operators to
the Hub). It is included here because REQ-HUB-COMMON-113's cross-surface validation and the
tamper log's integrity guarantee are meaningless if the log itself can be edited by a
privileged insider — the separate-signing-key lean directly addresses that.

## 4. Required honest-limits statements (verbatim source language)

These four statements are the canonical language for this platform's security posture.
Downstream documents (marketing, spec, sales, compliance) MUST cite this section rather
than write their own version.

### (a) ESP32-P4 no-secure-element residual

> The ENT module MCU (ESP32-P4) has **no dedicated secure element**. Its device key lives
> in MCU-resident key storage (eFuse OTP block, with flash encryption also enabled per the
> key-hierarchy custody doc's lean #4 — "belt-and-suspenders," not two independent secure
> elements). This is a **raise-the-bar** protection, not a secure-element-grade one: it
> resists casual firmware-level extraction and opportunistic probing, but a well-resourced
> attacker with lab-grade physical access (decapsulation, fault injection, side-channel
> analysis against the MCU's own crypto) should be assumed able to extract the key given
> enough time and equipment. This is the same honesty framing REQ-MOD-COMMON-010 and the
> workstream scope require, and it is why the pin-7 heartbeat's timing bound (§3, A3) — not
> secrecy of the key alone — is the mechanism that keeps a key extraction from silently
> becoming a remote impersonation. **No claim of secure-element-grade key protection SHALL
> be made for any ENT module**, on any silicon, absent an actual secure element being added
> to a future design.

### (b) Surface-independence classification

> Not every "independent surface" in REQ-HUB-COMMON-113's cross-validation list is
> cryptographically independent — some are merely *physically* independent (different wire,
> same key). This distinction matters because a compromise of one key-bearing surface can
> silently compromise every surface that shares its key, defeating the point of
> cross-validation.
>
> - **DETECT analog class + poke-and-ack is KEY-INDEPENDENT.** It carries no cryptographic
>   material at all — it is a resistor-divider code and a liveness poke on an analog line.
>   Its failure mode is unrelated to any key compromise; it can be defeated by a class-code
>   twin (electrically identical resistor) but never by extracting or forging a
>   cryptographic key, because it uses none.
> - **CAN challenge-response and the pin-7 heartbeat are NOT key-independent of each
>   other** — per the current design, both are keyed to the same MCU-resident device key
>   (REQ-MOD-COMMON-010, REQ-MOD-COMMON-013). A device-key compromise (A3) compromises
>   both surfaces' identity-proving power simultaneously. What pin-7 adds over CAN is
>   **relay/replay independence via the timing bound** (§3, §5) — a distinct, real security
>   property — but it is NOT key independence, and cross-validating "CAN passed AND pin-7
>   passed" should not be read as two independent keys agreeing. It should be read as: one
>   key answered correctly on a shared bus, AND the same key's holder proved it is
>   physically at this port in real time.
> - Consequence for REQ-HUB-COMMON-113: the Hub's cross-surface validation genuinely
>   diversifies against *some* attacks (T1-only compromise, CAN-only compromise, physical
>   presence spoofing) but does **not** diversify against a full device-key extraction the
>   way independent-key surfaces would. If true key independence across surfaces is wanted
>   in a future revision, it requires either per-surface derived keys (see custody doc §4)
>   or an actual second root of trust — neither is in the current design.

### (c) TC-baseline DPA / side-channel statement

> The production baseline Hub silicon per REQ-HUB-COMMON-001 (7th ruling) is
> **MPFS095TC (PolarFire SoC Core)**. The Core line has **no Athena (S-suffix) DPA-hardened
> crypto option**. On this baseline:
>
> - Runtime cryptographic operations (the CAN/T1 challenge-response, the pin-7 heartbeat
>   HMAC/derivation, evidence and log signing at the Hub) run as **software wolfCrypt** on
>   the MSS RISC-V complex — the same validated-module posture already declared for FIPS
>   purposes (REQ-HUB-COMMON-097).
> - **Side-channel (power/EM/timing) resistance on this runtime crypto is explicitly NOT
>   claimed on base (TC/non-S) builds.** A base-tier Hub's runtime crypto operations should
>   be assumed observable via standard DPA/side-channel techniques by an adversary with the
>   requisite physical access and equipment (overlaps with A1, evil-maid).
> - What the base build DOES still provide, per REQ-HUB-COMMON-001: SRAM-PUF-rooted secure
>   boot, user-accessible TRNG, and tamper detectors from the Core line's base security
>   block (conditional on FAE confirmation — if that confirmation fails, REQ-HUB-COMMON-001
>   reverts to the S-suffix ladder and reopens the ruling). These are boot-integrity and
>   identity anchors, not runtime-crypto side-channel protections, and should not be
>   conflated with DPA hardening in any claim.
> - **The Athena (S-suffix, MPFS095TS) part is the HS population option** that restores
>   hardware DPA-resistant crypto, on the same board land, for high-assurance/defense
>   channels or any customer specifying side-channel-hardened silicon. The security
>   architecture is explicitly required (REQ-HUB-COMMON-001) to **not depend on** Athena
>   being present — it is an upgrade, not a load-bearing assumption, and no claim of DPA
>   resistance may be made for a shipped unit unless that unit is actually populated with
>   the S-suffix part.

### (d) Two-chip fallback seam (PIC64GX + MPF050TC)

> `docs/enterprise-requirements/research/sourcing-alternatives-2026-07-02.md` documents
> **PIC64GX1000 + MPF050TC** as the designed two-chip fallback if the single-chip MPFS
> family's supply situation forecloses it. This shape introduces a **new attack surface
> that does not exist in the single-chip MPFS design**: in the single-chip part, the MSS
> (RISC-V complex, PUF, key store) and the FPGA fabric communicate over an **on-die AXI
> interconnect** — physically inaccessible to an external adversary short of decapsulation.
> In the two-chip shape, that same MSS↔fabric link is realized as **board traces**
> (RGMII/SPI/parallel, per the sourcing survey) between two separate BGA packages.
>
> This is a genuine security-relevant delta, not merely a bring-up cost:
> - A board-trace link is **probeable** with commodity test equipment (logic analyzer,
>   oscilloscope) without decapsulating anything — an adversary with A1-class (evil-maid)
>   physical access to an opened enclosure has direct electrical access to a link that, on
>   the single-chip part, they would not have at all short of destructive silicon analysis.
>   This shifts part of the trust boundary from "requires lab-grade decap" to "requires
>   board-level probing," a materially lower bar.
> - Whatever key material or attestation data crosses that link (challenge nonces, PUF-
>   derived values, signed evidence en route between the MSS and fabric-side logic) SHOULD
>   be treated as **exposed on that link** for threat-modeling purposes, not assumed
>   protected by die-level isolation the way it would be on the single-chip part.
> - Per the sourcing survey's own recommendation, this seam is flagged for
>   **security review before the fallback is ever needed** — it should not be adopted as a
>   silent drop-in substitute for the single-chip design without an explicit review of
>   what crosses the MSS↔fabric board link and whether it needs its own protection
>   (encryption/authentication of the inter-chip traffic, physical shielding/potting, or
>   accepting the residual and documenting it, per the same honesty discipline as (a)-(c)
>   above). **This document treats the two-chip fallback as NOT yet security-equivalent to
>   the single-chip baseline until that review happens.**

## 5. The pin-7 timing bound, stated once (referenced throughout §3)

REQ-HUB-COMMON-114 / REQ-MOD-COMMON-013 give the pin-7 heartbeat a specific, narrow
property, restated here once so §3 can reference it without re-deriving it each time:

- The nonce is delivered **ahead of time** over CAN or T1 (not on the timed path).
- The module computes its response (crypto time — HMAC/derivation) **before** the timed
  window opens — "compute-then-respond."
- The response itself is a **hardware-timer-scheduled edge/pulse**, not a firmware-loop
  action — determinism is a timer-peripheral property (ESP32-P4 timer + ETM/output-compare
  class), not a software-latency property.
- The acceptance window is **single-digit microseconds**; module timer precision is
  "tens of ns" (comfortably inside); a relay, proxy, or tunnel insertion between the
  legitimate key-holder and the challenged port is asserted to add "≥tens of µs" —
  distance-bounding-lite.
- **What this proves**: key possession + port presence + real-time liveness, **at that
  specific port, in that instant**.
- **What this does NOT prove** (REQ-HUB-COMMON-114's own honest-residual clause, adopted
  verbatim here): firmware integrity — that is secure boot's job (REQ-MOD-COMMON-012), not
  the heartbeat's.
- **Status flag**: the timing-budget analysis and the "single-digit-µs" / "tens of ns" /
  "≥tens of µs" figures above are **PROVISIONAL** per the workstream scope's own gating
  note (deliverable #3 is GATED on real ESP32-P4 timer/ETM jitter and CAN/T1
  propagation-delay measurements from firmware/hardware bring-up). Risk #3 in the scope
  document names the consequence directly: a timing budget drafted against assumed jitter
  that ships wrong could cause false-positive auto-untrust at fleet scale. **This threat
  model's conclusions in §3 that depend on the timing bound (A1, A2, A3, A4) are therefore
  provisional until that re-validation gate clears** — the mitigation the scope document
  specifies (mark the section provisional; define a must-re-verify-before-GA gate) is
  adopted here rather than restated differently.

## 6. Summary matrix

| | A1 Evil-maid | A2 CAN insider | A3 Key extraction+relay | A4 T1 compromise | A5 Pin-7 jam | A6 Supply-chain | A7 Insider operator |
|---|---|---|---|---|---|---|---|
| DETECT + poke-and-ack | Partial | N/A (different surface) | No (key-independent either way) | N/A | N/A | No | N/A |
| CAN challenge-response | Partial | **Insufficient alone** | No, alone | Partial | N/A | No | N/A |
| T1 attestation | N/A | N/A | No, alone | Partial (is the compromised surface) | N/A | No | N/A |
| Pin-7 heartbeat (timing-bound) | Strong (in-place) | Strong complement | **Yes — the specific defense** (not same-port substitute) | Strong (independent of T1) | Fail-secure (not fail-available) | No | N/A |
| Secure boot + anti-rollback | Strong (firmware mod) | N/A | N/A | N/A | N/A | Partial (post-signing only) | N/A |
| Tamper log | Evidentiary | Detective | Evidentiary | N/A | Logged/alarmed | Detective, post-deploy only | Load-bearing IF log key separate |
| Role separation + audit | N/A | N/A | N/A | N/A | N/A | N/A | Detective only |

*Legend: Strong = mechanism specifically designed to resist this class; Partial =
resists some instances, documented gap remains; Detective/Evidentiary = does not prevent,
provides forensic record; No = not a defense against this class; N/A = surface not
applicable to this adversary's access model.*

## 7. Open items / not yet covered

- Physical chassis-tamper sensor characteristics (switch types, defeat resistance) — owned
  by the tamper research register (`research/tamper-module-roadmap-2026-07-02.md`), not
  re-derived here.
- The MC-Max voting-pair trust model when one member is itself compromised (as opposed to
  a module) — flagged for the untrust/re-admission state machine (deliverable #6), not
  solved in this document.
- Formal timing-bound validation against measured ESP32-P4 jitter (§5) — GATED per the
  workstream scope; do not treat §3/§5's conclusions as final until that gate clears.
- Crypto-agility (deliverable #8) and the compliance crosswalk (deliverable #9) are
  explicitly out of scope for this document per the workstream's own sequencing.

---
*Cites: REQ-HUB-COMMON-001/010/042/070/071/097/110/112/113/114; REQ-HUB-NET-023;
REQ-MOD-COMMON-001/003/010/011/012/013/043; `docs/enterprise-requirements/research/
sourcing-alternatives-2026-07-02.md`; `docs/enterprise-requirements/research/
next-trajectory/scope-security-protocols.md` deliverable #7 and risks #1-#5.*
