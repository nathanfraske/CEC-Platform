# Enterprise / Workstation Trust — reference architecture (PROPOSED addendum, 2026-06-30)

**Status: PROPOSED. Resolves-toward OQ-7 (Enterprise build); folds OQ-44 (identity/provenance),
OQ-47 (cross-domain timebase), OQ-50 (trust/privacy boundary), OQ-62 (plan signing).** Owner
ratifies before any board or firmware work. This is a design proposal, not a lock; the
`CEC-Platform-Ground-Truth-Spec.md` remains ground truth and precedes this file.

Trigger: a real customer for a **workstation** variant requiring full trust attestation and
**tamper-evident, cross-checkable timestamping** — the first-customer-requirement that OQ-7 was
deferred against. Owner direction (2026-06-30): design to **physical anti-tamper now with
certification (FIPS 140-3 / Common Criteria / eIDAS) as the roadmap goal**; prefer an **on-prem
RFC 3161 TSA or a GNSS grandmaster with graceful fallback**; **primary deployment is workstation
use**; **tamper-evidence is the top priority for this customer**; and the whole capability must be
**generalizable — integrate cleanly with anything the customer already runs**, no proprietary formats.

## Design direction confirmed with the owner (2026-06-30) — the working basis of this addendum

Decided in review; the basis here, still PROPOSED at the spec level until owner ratification folds it into OQ-7 ("enterprise is not an assume-MVP field"):
- **Module link = 100BASE-T1** on pair 2 (locked). RS-485 dropped as the floor, gigabit dropped as over-scope: 100BASE-T1 is native to the ESP32-P4, carries native 802.1AS **PTP sub-µs** timestamping, is reliable/bidirectional, and reuses the existing RJ-45 with no connector change. 1000BASE-T1 is retained ONLY as the optional Enterprise Hub→host uplink. (Feasibility: the ESP32-S3/C6 have no Ethernet MAC; the P4's EMAC is 100M-only, so gigabit-per-module would force a bigger module SoC — the reason it is out of scope.)
- **Per-module zero-trust root of trust — standard, not optional** (§13). Every module attests its own identity + firmware + liveness and is presumed compromised the instant any check fails: *do not trust the module just because it is reporting.*
- **Two Hub SKUs, both built** (§15): ESP32-P4 (~$94, less-stringent, tamper-EVIDENT) and PolarFire SoC (~$206, maximum-security, tamper-RESPONSIVE + FIPS/CC path).
- **Full multi-modal in-case tamper-sensing fabric** (vibration, airflow, particulate/air-quality, thermal, temperature, camera) as the cross-correlation mesh — which doubles as the zero-trust module-lie detector (§14).

---

## 1. Scope and goals

A trust-enabled Hub variant that produces a **tamper-evident, independently-timestamped,
cross-checkable record** of a single workstation's power/telemetry, verifiable by any external
system with off-the-shelf tools.

- **Primary deployment:** workstation-attached (USB HS host link), possibly air-gapped/restricted.
- **Priority order (customer):** (1) tamper-evidence, (2) generalizable interop, (3) attestation +
  physical anti-tamper now, (4) certification as the roadmap destination.
- **Non-goals:** proprietary formats, single-vendor lock-in, any dependency on the host being trusted.

## 2. Trust model — the Hub as an independent, host-uncforgeable witness

The security thesis for workstation use: the Hub is an **out-of-band recorder** that signs +
timestamps + hash-chains the electrical/telemetry record on its **own root of trust and timebase**,
powered from **5VSB (always-on — survives the host being off, asleep, or compromised)**.

**What it proves:** *"this telemetry stream, in this order, existed at these times, on this attested
device, unaltered."* — independent of the host.

**Threat model:**
- *Compromised/malicious host OS or user* → cannot forge, alter, backdate, reorder, or silently
  delete the record (the record lives behind the Hub's RoT, on the Hub's timebase, in an
  append-only hash chain the host never holds keys to). **This is the core promise.**
- *Physical attacker* → detected/resisted by anti-tamper (roadmap: key zeroization on tamper event;
  see §7). Ships as tamper-*evident* now; tamper-*responsive* on the certified part.
- *Device-key holder trying to rewrite history* → defeated by external anchoring of the log head
  (§6): the head is pinned externally, so any later fork is detectable even by an insider.

Host-side logging can make none of these claims about itself. That gap is the product.

## 3. The record pipeline — tamper-evidence (the heart)

1. Every telemetry record (event, FREEZE co-capture window, periodic snapshot, or streamed sample)
   is hashed and appended to an **RFC 6962-style hash-chained Merkle transparency log** — append-only,
   with each entry binding the prior head, so **integrity + monotonic ordering are cryptographic**.
2. Per **batch window**, the Merkle **root** is **signed** (COSE/JWS or CMS/PKCS#7) by the device key
   and **timestamped** (§5). Any individual record is provable with a **Merkle inclusion proof**
   against a signed+timestamped root — no per-record signature needed.
3. The signed log head is periodically **anchored externally** (§6).

**Load-bearing principle — tamper-evidence ⊥ time-traceability.** The hash chain proves integrity and
order *unconditionally*; it does **not** depend on the time source. The time source only sets the
*traceability class* (§5) of the wall-clock attribute on each record. So the time ladder can degrade
all the way to host-asserted and the record is **still provably unaltered and correctly ordered** — it
merely carries a lower time class. This is what lets "graceful time fallback" never weaken the promise.

## 4. "Attest everything" is feasible — Merkle-batched signing

You never sign per-sample; you sign a **root over a batch**, and any sample is provable by inclusion.
This decouples signing rate from data rate. Against the platform's own ceilings:

| Stage | Worst-case load | Ceiling | Headroom |
|---|---|---|---|
| Data to cover | ~10 MB/s aggregate (8 Pro ports full-streaming ~900 kB/s; most builds far below — event + 1 kHz averaged) | — | — |
| Hashing (every byte) | ~10 MB/s | HW SHA-256: hundreds of MB/s → GB/s | ~30–100× |
| Signing (one root/batch) | 100 ms → 10 sig/s; 10 ms → 100 sig/s | secure element ~10–50/s; crypto core thousands/s | ample |
| Trust metadata (roots + tokens) | ~1–2 KB/root × 1–10/s | storage | <1% of raw data |

**Conclusion: 100% of the data can be attested.** The limiter is hashing throughput (HW SHA sits
30–100× above full-stream); signing is per-batch and trivial; overhead <1%. The one design knob is
**batch cadence** (tighter = faster time-to-attestation, needs the crypto core for the sign rate;
looser runs on a bare secure element). A per-raw-sample RFC 3161 token is the *only* infeasible
variant — and never needed (the root token covers every sample under it transitively).

## 5. Time — a pluggable ladder with per-record traceability class

A time-source abstraction with graceful fallback; **every record carries the class + the proof** so a
cross-check system gets graduated, honest trust:

- **Class A — traceable/legal:** on-prem **RFC 3161 TSA** (in-enclave; optionally eIDAS-qualified).
  Token stored per root. Best.
- **Class B — traceable/local:** **GNSS-disciplined grandmaster** (GPS/GNSS → UTC), PPS in.
- **Class C — disciplined holdover:** the Hub's TCXO/RTC, disciplined while A/B were last present,
  drift-bounded (the bound is recorded, so the verifier knows the uncertainty).
- **Class D — host-asserted:** workstation NTP/NTS, marked **unverified** — a last resort that never
  blocks logging.

The ladder degrades gracefully; the chain (§3) stays intact regardless. **Air-gap:** A and B live
*inside* the enclave (on-prem TSA appliance / GNSS puck), C bridges outages, D uses the host with the
unverified mark. The **Hub can also act as a local RFC 3161 TSA** (its attested clock + RoT key issuing
standard tokens) — often the cleanest fit for a single air-gapped workstation, with traceability then
resting on the Hub's disciplined clock + the external anchor.

## 6. External anchoring — defeats even key compromise

Periodically publish the signed log head to a witness the device cannot control: the customer's own
**transparency log**, a **countersigning notary/TSA**, or — for air-gap — an **exported/couriered
receipt** on the next sneakernet sync. This pins the head at a time; a later attempt to fork or rewrite
history (even by a device-key holder) becomes detectable. Cadence and sink are configurable (§8).

## 7. Hardware

- **Lead part — Microchip PolarFire SoC** (the spec's Appendix B.3 consolidated candidate): on-die
  **anti-tamper**, DPA-resistant secure boot, **PUF** key storage, Athena crypto (CAVP-certified,
  CNSA), flash-based (no external bitstream to intercept), and a **FIPS 140-3 / Common Criteria path**
  for the certification roadmap. Folds RoT + crypto + (optional) data-plane fabric onto one die.
- **Cost variant — ESP32-P4 + secure element** (SE050 / ATECC608-class, tamper-detect) **+ a tamper
  mesh/enclosure.** Ships tamper-evidence *now*; ceilings below full certification — the on-ramp, not
  the destination.
- **Additions vs the summary Enterprise Hub:** a disciplined **RTC (TCXO)** + a **time input**
  (GNSS/PPS, PTP), **non-volatile secure log storage** (or stream to the on-prem log), and the RoT.
- **Workstation form factor:** USB HS host link (data egress + optional Class-D time), **5VSB
  always-on** (the independent-witness property), and the trust I/O (time-in; on-prem TSA reached over
  the enclave network *or* the Hub-as-local-TSA option).

## 8. Generality — integrate with anything (no CEC-specific verifier)

Open standards at **every** layer, with the *sources* configurable rather than baked:

- **Formats:** X.509 (identity), **RFC 3161** (time tokens), **COSE/JWS + CMS/PKCS#7** (signatures),
  **RFC 6962** (transparency log), canonical JSON (RFC 8785) / CBOR. Verifiable with openssl, standard
  CT tooling, COSE/CMS libraries — **no proprietary verifier ships to the customer**.
- **Pluggable trust anchor:** device birth cert chains to **their CA or ours** (config).
- **Pluggable time sources:** the §5 ladder, any subset present.
- **Pluggable export sinks:** SIEM (syslog / CEF / OpenTelemetry carrying the signed payload), their
  transparency log, or a file/receipt for air-gap. Adapters at the edge; the core is format-stable.

## 9. Firmware / PKI / ops build list

- **Firmware:** RoT key-gen + seal; secure-boot chain (MCUboot / PolarFire); the append-only
  hash-chain log engine; the Merkle batcher; the signer (COSE/CMS); the RFC 3161 client **and** the
  Hub-as-local-TSA option; the **time-ladder manager** (class tracking + holdover discipline + drift
  bounding); the export adapters. RTOS: Zephyr/FreeRTOS + wolfSSL FIPS (per Appendix B.3).
- **PKI / ops:** device provisioning (birth cert issuance); CA choice (theirs / ours); key custody,
  rotation, revocation; TSA choice; the anchor cadence + sink; retention policy.
- **Reuse from the existing framework:** `cec_ledger` already gives an append-only, SHA-256-hashed,
  determinism-manifested record with per-decision evidence/policy hashes — it becomes the *software
  half* of the log (extend it with prev-hash chaining + the device signature + the RFC 3161 token).
  The Hub's existing role as the **timestamping aggregator** and the **cross-module FREEZE common
  ~1 µs timeline** are the ingestion layer this signs over.

## 10. Open decisions (owner) and OQ mapping

- **Owner decisions:** part (PolarFire vs ESP32-P4 + SE + mesh); certification target + timeline
  (FIPS 140-3 vs CC vs eIDAS); batch cadence; the external-anchor sink; whether the Hub doubles as a
  local TSA; retention.
- **Customer dependency (surfaced by air-gap + TSA):** can they provide an **in-enclave traceable time
  source** (on-prem RFC 3161 TSA or a GNSS grandmaster)? If not, the Hub-as-local-TSA + Class-C
  holdover + external anchor is the fallback, at a stated traceability caveat.
- **OQ mapping:** resolves-toward **OQ-7** (Enterprise build); folds **OQ-44** (identity/provenance →
  device cert + signed log), **OQ-47** (cross-domain timebase → the class ladder), **OQ-50** (trust/
  privacy boundary), **OQ-62** (plan signing → same signing infrastructure).

## 11. One-paragraph pitch (for the customer)

An always-on, host-independent hardware witness bolted to the workstation: it records the machine's
power and telemetry into an append-only, hash-chained, cryptographically-signed log on its own root of
trust and timebase, timestamps it against your on-prem TSA or GNSS grandmaster (gracefully falling back
without ever weakening tamper-evidence), and emits everything in open standards (X.509, RFC 3161,
COSE/CMS, RFC 6962) so any system you already run can verify it independently — no proprietary tooling.
A compromised host cannot forge, backdate, reorder, or delete the record; a physical attacker trips the
tamper response; and every entry is cross-checkable against the rest of your infrastructure to the
microsecond.

## 12. Power and always-on architecture

The witness runs host-independent, so power taps the 24-pin via the §2.9 priority-OR — but the two 5V
sources have distinct roles:
- **+5VSB (standby)** — always-on (PSU plugged in), the LOCKED primary Hub feed (OQ-1). Carries the
  always-on trust CORE: RoT, RTC, the attestation/watch loop, the signed log, the light tamper floor.
  Mandatory — the independent-witness property depends on running when the host is off.
- **Main +5V** (S0-only, tapped AFTER the 24-pin 5V INA228 shunt per OQ-13 so the Hub's own draw is
  measured) — the opportunistic high-capacity source for the HEAVY load (PolarFire/FPGA fabric, camera,
  fan-based sensing), power-gated on 12V-present.

**Fallback ladder** (§2.9 OR): MAIN 5V → **5VSB** (the monitored system's own always-on rail — internal,
NOT an external input) → **4700 µF hold-up cap** (ms ride-through) → **coin-cell-backed RTC + secure
element** — trust-critical: the trusted clock + the SE monotonic counter MUST survive a full power loss,
or backdating/replay open up.

**NO external / wall-wart power input** (owner direction 2026-06-30). An external power port is both a new
attack vector (a physical ingress to glitch/inject/probe) and a standing dependency — so the witness draws
ONLY from the internal 5VSB, whose loss is itself a logged tamper signal. Forensic readout of a dead
machine uses the durable **NV-flash log** (survives power loss; read when the box is next powered from
5VSB) or an authorized, logged physical procedure through the tamper-evident enclosure — never a standing
external power port. This is a specific instance of the §17 minimize-ingress principle.

**Trust-tier hardening:** (1) **power loss is a logged tamper signal** — the hold-up cap buys the ms to
write a signed "power-cut at T" ledger entry, so the witness can't be silently killed; (2) the trust
core is **un-severable by a compromised module** — a hostile 24-pin cutting main 5V just drops to
5VSB/aux/battery and logs it; (3) budget the always-on core within the shared ~2.5 A 5VSB (OQ-2), gating
the fabric/camera onto main 5V.

## 13. Zero-trust per-module root of trust

Every module carries its OWN RoT (distinct from the Hub's), advertised over the DETECT reserved codes so
the Hub knows a port's attestation strength before the module talks. The RoT ladder (per-SKU populate):
- **RUNG 0 — ATECC608B (~$0.84):** non-exportable ECC-P256 identity + ECDSA challenge-response +
  monotonic counters. Crypto tamper-EVIDENCE; firmware measurement is MCU-self-asserted (no PCR). Volume floor.
- **RUNG 1 — SE050 (~$2.84):** + active tamper-DETECT zeroization + I2C secure-channel (defeats bus MITM).
- **RUNG 2 — OPTIGA TPM SLB9673 (~$4.2):** + measured-boot PCR banks + a standards-clean TPM2 quote — the
  first INDEPENDENT firmware measurement. The Enterprise-module RoT on the P4 Hub.
- **RUNG 3 — on-die PolarFire:** PUF keys (never stored) + DPA-resistant secure boot + tamper-mesh
  zeroization — the only tamper-RESPONSIVE rung + the FIPS/CC carrier.

**Continuous (per-round, not boot-only) attestation.** The Hub challenges each module with a fresh nonce;
the module RoT signs a quote over {identity ‖ firmware measurement ‖ nonce ‖ monotonic counter ‖ last-seen
ledger head}. The Hub verifies identity (cert chain), integrity (measurement on the allow-list), freshness
(nonce echo), and anti-rollback (counter strictly increased). Cadence ~1 s liveness / ~10-60 s full
re-measure. Monotonic counters are load-bearing — they defeat replay/clone/rollback across power cycles a
nonce alone can't. Signing is per-round (<1% overhead, §4). Every accept AND fail is appended to the ledger.

**Assume-bad (fail-SAFE).** A module is trusted to its class ONLY while every check holds; any failure
flips it to a signed, latched DISTRUSTED state. Triggers: failed/stale attestation (silence = compromise,
not benign dropout), counter regression/stall, nonce mismatch, cross-modal incoherence (§14),
physical-tamper assertion, or a DETECT/poke-and-ack port-swap anomaly. Response: (1) MARK in the
hash-chained ledger with the evidence window; (2) QUARANTINE the data (untrusted; excluded from
golden/energy/support; zero control authority; retained for forensics); (3) DEGRADE gracefully (the fleet
keeps running, the attack stays on the record); (4) ALERT out-of-band + drive the external anchor so the
distrust can't be rewritten out; (5) RE-ADMIT only on a fresh clean counter-advanced attestation (+ human
sign-off for a physical-tamper latch). Trust is re-earned per round, never assumed persistent.

## 14. The multi-modal in-case tamper-sensing fabric

A family of in-case sensor modules whose signals cross-correlate on the shared trusted timebase to
(a) detect physical tampering + environmental/health anomalies and (b) VERIFY other modules aren't lying.
Tiered family (cost says combine cheap sensors onto shared MCU/RoT overhead; zero-trust says keep
independent-RoT auditing families separate):
- **Distributed floor (on EVERY module, incl. the electrical sensors):** LIS2DW12 accel (~$0.55,
  wake-on-strike) + an NTC on an independent ADC + crypto-auth TMP1827 1-Wire thermal-map nodes.
  Multi-point coincidence a single subverted sensor can't reproduce.
- **Sentinel Sensor-Hub (workhorse):** ESP32-S3 + IIS3DWB wideband vibration ($18) + differential-pressure
  across the intake ($19, the case-open seal-collapse flagship) + BME688/SGP41 gas + a particulate head;
  on-module feature extraction, features over CAN, raw on FREEZE. Full ~$72-90 (Enterprise premium) /
  cost-down ~$44-52 (SEN55 + LIS3DH). Earns its BOM as chassis-health monitoring with zero attacks.
- **Optical Sentinel (deliberately separate RoT):** watcher (HM01B0 + ESP32-S3, events/hashes over CAN,
  bitmap never leaves the module) / forensic (OV5640 + ESP32-P4, full frames on 100BASE-T1 ONLY on a
  tamper trigger). The IR illuminator doubles as a randomized anti-replay strobe challenge.
- **Optional adds:** MLX90640 thermal imager (~$20, implant-hotspot localization), ultrasonic AE
  (ADXL1002 $57 or PVDF piezo $4 for drill/cut), out-of-band host-screen capture (its own USB/Ethernet
  path, OQ-50 privacy-bounded).

**Cross-correlation = coincidence, not any single trip.** A physical tamper radiates a COHERENT signature
across orthogonal physics within the co-capture window: case-open = gravity-step + latch impulse (accel) +
ΔP collapse + gas/particulate step + camera exposure spike; probe-attach = tap-transient + a persistent
shift in the board's fan-driven modal peaks (added clip mass detunes the resonance) + camera delta;
drilling = ultrasonic AE + coarse-particulate burst + friction hotspot. Spoofing requires physically
injecting energy that stays coherent across every modality and every module on the ~1 µs timebase — which
IS the tamper event. Direct sensor attacks self-incriminate (covered lens = exposure collapse; replayed
frame = fails the IR-strobe challenge; plugged vent = fan-state anomaly; swapped 1-Wire node = fails
SHA-256-HMAC).

**The same fusion is the zero-trust module-lie detector.** A compromised module can pass crypto
attestation and still lie in its payload — cross-modal verification catches exactly that, because the
auditors are separate modules with separate RoTs sensing independent physics. Each check is a physics law:
thermal ⟂ claimed I·V (an under-reported current can't cool away an implant's heat → a hotspot on a node
the liar doesn't own); vibration ⟂ load transients (a big electrical event with flat coil-whine is a lie);
airflow ⟂ power+thermal; particulate/VOC ⟂ thermal event (**the 12VHPWR melt case** — a failing pin arcs
and outgasses while per-pin current still looks balanced → caught before melt); camera ⟂ everything (LED
dark vs "healthy", board absent vs "present"). The checks run on the HUB (the verifier), so no compromised
module can suppress them. **Crypto proves who/what a module is; cross-modal fusion proves it is telling the
truth about the physical world.** All firmware/timebase over the LOCKED CAN FREEZE ~1 µs co-capture + PTP
on 100BASE-T1 ports — no respin; the accel/ΔP/thermal/camera INT pins OR into the same FREEZE the INA
sensors already use.

## 15. The two Hub SKUs — weighted decision matrix

Both ship; the matrix is a routing rule, not an elimination. At trust-tier weights (Security 0.25, Cert
0.20 dominant):

| Criterion | Weight | ESP32-P4 (~$94) | PolarFire (~$206) |
|---|---|---|---|
| Cost | 0.15 | 5 | 2 |
| Security / anti-tamper | 0.25 | 2.5 (tamper-evident) | 5 (tamper-responsive) |
| Certification path | 0.20 | 2 | 5 |
| Power / 5VSB budget | 0.10 | 4.5 | 2 |
| Integration | 0.12 | 2 | 5 |
| Dev / supply risk | 0.10 | 4 | 2 |
| Per-module RoT scaling | 0.08 | 4 | 5 |
| **TOTAL** | | **3.19** | **3.95** |

PolarFire leads at trust-tier weights; re-weight for cost/volume (Cost 0.35) and it flips to P4 (~3.7 vs
~3.1). That inversion IS why both ship. Routing: **default to the P4 Hub for the fleet** (data-integrity +
tamper-evidence + the full attestation/lie-detection assurance floor, which is firmware/timebase and
identical on both); **escalate to PolarFire** where a certificate, physical tamper-response, or a
nation-state physical adversary is actually in scope. The ~$112/Hub premium buys ONLY physical
tamper-response + certification the P4 path can't reach — the assurance FLOOR is identical.

## 16. Open decisions from the sensor / RoT scoping (owner)

1. **DETECT reserved-code assignment** — proposing the two reserved §2.3 codes (22 kΩ = RoT-attesting,
   47 kΩ = physical-anti-tamper/PolarFire-class) as trust-class advertisements. Consumes both remaining
   codes and grows the LOCKED §2.3 table → needs an explicit spec revision, not an assumption.
2. **Enrollment / golden-baseline lifecycle** — the tamper reference IS the commissioned healthy
   modal/thermal/ΔP fingerprint. Where stored, how re-enrollment is authorized after legitimate service
   (a technician touching the box fires every "structural delta"), and the AM-02-style anti-latch
   discipline so a re-baseline can't launder an implant into the golden reference. **Highest-risk item.**
3. **Active-ping challenge authority** — the quiescent-machine weakness is covered by the Hub driving a
   fan/coil and requiring the expected modal response; which SKU may actuate host hardware, and is that
   inside or outside the zero-trust boundary.
4. **Sentinel cost-vs-orthogonality** — accept the ~$72-90 full Sentinel as an explicit Enterprise premium
   module, or force in-class (SEN55/LIS3DH cost-down, losing light-clip modal-detune detection)? Minimum
   independent-RoT sensing families for the cross-modal check.
5. **The physical one-way mechanism + GNSS-or-not** (§17) — truly-one-way is easiest on TX-only serial/
   fiber (the record stream is low-rate); USB/Ethernet give only *logical* one-way (the PHY still
   receives) unless a real data diode is used. Which assurance level? And given minimize-ingress, default
   to NO GNSS (local holdover + customer receive-time anchoring), offering GNSS only as an opt-in.
   (The earlier "aux forensic power input" is RESOLVED — dropped, §12.)
6. **Particulate sourcing + fan duty** — SPS30 (traceable, $28) vs SEN55 (one blindable head, $26) vs
   PMS5003 (grey-market, $15); the fan duty-cycle schedule trades detection latency against 5VSB budget.
7. **Camera privacy boundary (OQ-50)** — default-store hashes/LED-vectors/structural-diffs; OCR-and-discard
   the host screen; full bitmaps only in a signed forensic buffer after a trigger.

## 17. Minimize ingress — the two boundary crossings (owner direction 2026-06-30)

Governing principle: **every input is attack surface AND a standing dependency, so drive ingress to near
zero.** The witness's integrity must depend ONLY on its own RoT + the internal physical sensors — never on
anything the host or the outside world sends. Two boundaries:

- **Inside the sealed enclosure** — the module↔Hub fabric (100BASE-T1 + CAN + PTP) stays BIDIRECTIONAL
  (the Hub challenges the modules; §13). That is all within the trust boundary and is fine.
- **Crossing to the outside world (Hub → host / customer)** — **ONE-WAY EGRESS ONLY, a data diode.** Signed,
  timestamped, tamper-evident records go OUT; nothing comes back — no queries, config, commands, or firmware.

Everything that looks like it needs a return path resolves without one:
- **Remote attestation freshness** — the box SELF-generates freshness (RoT TRNG nonce + monotonic counter +
  its own clock) and PUSHES signed quotes; the external verifier checks them. No inbound challenge.
- **Trusted timestamping** — the Hub is its OWN local RFC 3161 TSA (attested clock + RoT key); internal, no
  external round-trip.
- **Traceable-to-UTC time with ZERO ingress** — the box keeps a monotonic holdover clock; the **customer's
  receive-time on the one-way stream anchors it to UTC on their side** (they know when each record arrived).
  External time-traceability, no time port. (Consistent with tamper-evidence ⟂ time-traceability, §3/§5.)
- **"On-demand raw upload"** — under one-way there is no inbound "demand", so the box AUTONOMOUSLY decides
  what to egress (triggered events + features). This simplifies the uplink and removes the interactive-pull
  attack surface entirely.
- **External anchoring (§6)** — a fire-and-forget push of the log head; the customer holds it and verifies
  inclusion on their side. No receipt needed back.
- **Firmware / config** — physical, authenticated, rare, logged — NEVER through the uplink. A security win:
  no remote-update surface.

**Net:** a sealed, self-powered (from the monitored 5VSB, §12), one-way witness with essentially no
externally-reachable attack surface — and STILL fully cross-checkable, because the one-way stream carries
everything (X.509 + RFC 3161 + COSE/CMS signatures + Merkle proofs) for the customer's systems to verify
independently. One-way egress and "integrate with anything" (§8) are not in tension — external systems only
ever *receive* from us.

**Physical realization:** truly-one-way is easiest on a **TX-only serial or fiber** (the record stream is
low-rate, so bandwidth is not the constraint). USB/Ethernet are inherently bidirectional at the PHY, so
"one-way over USB" is only *logical* one-way — for high assurance prefer physical one-way (TX-only optics /
a real data diode), or place the diode on the customer's side. **Time discipline:** default to **no GNSS**
(a GNSS antenna is still an external RF ingress and is spoofable) — local holdover + customer receive-time
anchoring — offering GNSS only as an opt-in where on-box UTC is required.

### Collapsing the uplink count — count crossings, not ports

Naively this looks like three uplinks (system + egress + management); it is really TWO boundary crossings:
**OUT** (one signed stream — everyone *subscribes*) and a rare **authorized PHYSICAL-IN** (provisioning/
service). The three collapse:
- **"System" is not a separate uplink** — the untrusted host is a *consumer* of the one-way egress, not a
  trusted peer. Its only physical tie to the monitored machine is power (5VSB) + the sense taps, neither a
  data uplink.
- **Egress is ONE function; reaching all the customer's systems is THEIR fan-out.** The Hub emits one
  self-verifying signed stream to one trusted collector/network; the customer distributes it (SIEM, audit
  store, host app). One egress interface, N subscribers — not N uplinks.
- **Management splits by risk, and the dangerous majority is not a standing uplink** (§18): the
  trust-defining actions go on the **provisioning/service port (normally disconnected, physical-auth)**; the
  safe remainder needs no ingress (it receives egress) or rides a **bounded RoT-mailbox return on the egress
  wire**.

**Result: ONE standing external data port (egress) + power/sense (physical) + a normally-dark service port.**
The same egress port carries the assurance dial: max-security = a **physical one-way diode** (dangerous
management → the dark service port); remote-managed = **bidirectional to the provably-trusted OOB network**
(egress out + the bounded RoT-mailbox in) — so remote access + egress ride ONE wire, and the "separate
management uplink" is just egress with a bounded return.

## 18. Optional remote management — the separated control plane, and what must hold

Remote management can coexist with the sealed witness because **tamper-evidence is transport-independent**
(the record is self-verifying regardless of the wire) and the witness guarantee is enforced by the
**RoT/hardware boundary, not by the absence of a channel**. Structure (privilege separation):
- The **witness core** (RoT, log, clock, keys, sensor fusion, egress) is inviolable.
- A separate **management controller** terminates the bidirectional channel — on PolarFire a formally
  design-separated fabric partition, on the ESP32-P4 a physically separate MCU — firewalled from the core.
- **Management CAN** (each action itself logged): read the already-signed stream, adjust *cosmetic* config,
  stage a *signed* update to the *manageable* firmware, trigger diagnostics/re-attestation.
- **Management CANNOT** (RoT/hardware-enforced): alter/reorder/delete the log, touch the keys, set the clock
  backward, suppress a tamper event, or update the witness CORE firmware without physical/multi-party auth.

### What MUST hold for the separation to be honest (adversarial red-team, 2026-06-30)

A red-team assuming the management controller AND the "provably-trusted" network are fully compromised found
the boundary stops what it *precisely* claims (no software log-rewrite, no software key-extraction, no core-
firmware swap) but that the claim as first stated is **~60% there and overclaims** — the danger lives in the
*permitted* paths, not across the boundary (**a signature proves the core *recorded* something, not that it
is *true***). Five requirements make it honest:

1. **Independent sensor ingest + per-module signing.** The sensor→core path is physically independent of the
   management partition, and **each module signs its own data with its own RoT; the core verifies before
   recording** — so the record proves provenance, not just "the core saw bytes." (Closes authenticated-but-
   false ingest — the deepest integrity risk.)
2. **Everything trust-defining is security-tier, not "config."** Detection thresholds/floors, sensor
   duty-cycle floors, **golden baselines + module re-enrollment**, clock discipline, and the Port-A egress
   destination/rate/filter are multi-party/physical-auth; management may only *tighten* a threshold, never
   loosen; the *effective* threshold is stamped into each detection event. Only cosmetic config is
   management-safe. (Closes implant-laundering via re-baseline, detection-blinding, erase-by-egress-redirect.)
3. **Append-only means FAIL-SEAL, never wrap.** A reserved security-event partition config cannot shrink; a
   bounded log-generation rate; on near-full, a signed+egressed "degraded/flooded" event, drop only
   low-priority data; paced constant-rate egress. (Closes storage-exhaustion erasure and silent gaps.)
4. **External anchoring + cross-check make the network's max power *detectable denial*.** RFC-3161 TSA plus
   transparency/cosigning with enforced consistency proofs; Port A is authoritative; verifiers treat "no
   fresh anchor within T" and "Port A vs Port B divergence" as tamper. (Closes backdating, split-view/fork,
   forward-clock skew.)
5. **Keys in a discrete SCA-hardened vault; provisioning on-device with anchors pinned in OTP.** "Formal
   design-separation" covers digital info-flow ONLY — not DPA/EM/thermal side-channels or shared-resource
   covert channels, a HIGH key-confidentiality gap on single-die PolarFire; so keys live in a discrete
   secure element regardless, signing is DPA-hardened, shared resources partitioned, and **the two-MCU P4
   topology is actually *stronger* for confidentiality.** Keys generated on-device (never known to the
   maker); all attestation/TSA/management trust roots pinned in OTP under an audited ceremony (a field-
   mutable management root lets a compromised controller "provably trust" itself). Plus: the core↔management
   interface is a minimal, fixed-format, formally-verified hardware mailbox with no shared writable memory,
   core as paranoid parser (stops a Port-B RCE pivoting into the core).

Verdict: the separation is sound **only after** the four danger classes (authenticated-false ingest,
config-as-policy, availability-erasure, side-channel/supply-chain) are pulled inside the multi-party tier and
the physical gaps are funded. The boundary stops software from *editing the truth*; these five stop a
compromised manager from *authoring convenient truth at ingest*, *deleting truth via availability*,
*redefining "normal" via config*, or *reading truth out through the die's physics*.

## 19. Exploration — opt-in OS-event cross-check (the OS-logical modality)

PROPOSED / exploratory. Goal: ingest the monitored host's own software/OS events (Windows Event Log/ETW,
Linux auditd/journald/IMA) as an **opt-in cross-check** and backup to whatever remote monitoring the customer
already runs — WITHOUT weakening the witness.

The framing that keeps it consistent with everything above: **OS events are ingested as UNTRUSTED, ATTRIBUTED
CLAIMS, never as trusted data.** You do not ingest them to believe them — you ingest them to *catch the host
lying*. This is the §14 cross-modal principle applied to the host: the OS becomes the "OS-logical" vantage
(the spec's third vantage, Appendix C.7 / OQ-47), the LEAST-trusted modality — it adds semantic context ("what
software did") physics can't see, and the physical modalities *adjudicate* it.

You cannot make an untrusted host's claims TRUE; you make the **recording** trustworthy:
1. **Independent trusted timestamp** — the witness stamps arrival on ITS OWN clock (the OS clock is coarse,
   lagging, forgeable, recorded only as a claim). An OS event may optionally assert a **rate-limited FREEZE**
   (a benign request, the NanoKVM model) to co-register with the physical co-capture window at ~1 µs (OQ-47).
2. **Tamper-evident recording** — once ingested it is in the signed hash-chained log; the host can lie but
   cannot un-say or erase it afterward.
3. **Physical adjudication (the value)** — trustworthiness is EARNED per event by coherence with the
   independent electrical/physical record: an OS "clean shutdown at T" that coheres with a graceful power
   ramp = corroborated; one that contradicts an abrupt power cut = a signed DISCREPANCY = evidence of host
   compromise. **The killer use is the disagreement:** when a compromised host feeds the customer's OWN SIEM
   a clean story, the witness's independent physical record + independently-timestamped copy of the same
   events expose it, on the record, cross-checkable.
4. **OS-side attestation as a bar-raise (not a guarantee)** — if the host has TPM measured boot + a signed
   event log (Windows TPM event log; Linux IMA/EVM; systemd journald forward-secure sealing/FSS), the witness
   records the OS-side quote so a verifier can check the OS's OWN chain of trust. A runtime-compromised OS can
   still lie, so this attributes the claim to an attested boot STATE — it never makes it true.

Ingress safety (this IS an ingress): opt-in, available ONLY on the managed tier (§18) — it rides the existing
bidirectional link into the **bounded, hardened-parser untrusted-ingest zone in the management controller,
never the witness core**; NOT available on the pure one-way diode tier. A host-side agent (the Concierge,
Appendix C) forwards the events. Net: it adds NO port and cannot reach the core; its worst case is a
bounded-parser attack surface + a flood of "untrusted-claim" records — and its best case is catching the host
lying to its own operators. Open: the host-agent trust boundary + rate-limits (OQ-52-style), the OS-content
privacy boundary (OQ-50), the coherence-rule library (which OS event ⟂ which physical signature), and whether
a discrepancy auto-raises a tamper event or only a flag pending review.
