# ENT module build variants — spec sheets + BOM deltas (DRAFT)

_Status: DRAFT (2026-07-02) — "start drafting" per owner ask. Authority: module registers
(`../module-requirements-*.md`) + spec §6.x locked sensing facts + surveys 7/8. The
consumer/Pro BOMs in `modules/<family>/bom/` are the BASE; this sheet specifies the
enterprise DELTAS per family. Boards start only after register ratification (owner ruling:
requirements now, boards after). Prices [est] 100q, 2026-07-02; `[RFQ]`/`[unv]` as marked._

## 0. Deltas common to every ENT module family

**Working recommendation (flagged, not yet owner-ratified): ONE radio-free ENT build per
family serves both postures** — AIR requires radio-free (REQ-MOD-AIR-020, resolved); NET
doesn't forbid it; two builds per family would double the SKU matrix for no buyer benefit.

| Delta | Change vs consumer build | BOM effect [est] | Trace |
|---|---|---|---|
| MCU (radio-free + RMII MAC) | **ALL FOUR families: ESP32-P4** (radio-free, RMII MAC + HW 1588/PPS) — 6th ruling extends T1 to the 24-pin, so the MCU is uniform (one toolchain, one firmware base, the 12VHPWR Pro reference design); STM32H5-class = documented fallback; the 24-pin's earlier G431 pick is SUPERSEDED | P4 $4.47 vs C6 ~$3-4; T1 front-end ~$3.0-4.2/module (survey 10) | survey 8/10; owner ruling 2026-07-02 (6th); REQ-MOD-COMMON-003 |
| Per-unit identity | **RESOLVED (5th ruling)**: MCU-resident device key + Hub challenge-response over CAN/T1 + DETECT poke-and-ack liveness — NO identity hardware (1-Wire path OUT); provisioning = key injection at the flashing step. ADOPTED addition (6th ruling): **pin-7 heartbeat responder** (REQ-MOD-COMMON-013) — port-bound hardware-timed challenge-response, independent of the T1 stack; miss → auto-untrust at the Hub | **≈$0 parts** (firmware + provisioning step; heartbeat = GPIO + existing timer) | REQ-MOD-COMMON-010/011/013; OQ-76 resolved |
| Firmware signing | Same custody/anti-rollback discipline as the Hub (MCUboot on STM32G4 is mature) | $0 parts | REQ-MOD-COMMON-012 |
| Link & DETECT | UNCHANGED (locked): RJ-45 FTP, CAN 500k via TJA1051T/3, DETECT code per class, pin-8 ESD | $0 | REQ-MOD-COMMON-001 |
| Telemetry integrity | Sequence+timestamp metadata (firmware); §6.10 pre-roll retained | $0 parts | REQ-MOD-COMMON-041/042 |
| Provenance-grade BOM | Locked shunts (OQ-11 must close first), §5949-clean sourcing rule for gov-bound builds, per-family SBOM/PSIRT | process, $0 | REQ-MOD-COMMON-051/052; survey 7 |
| Fail-passive evidence | FMEA/FMEDA + fault-injection per family (deliverable, not BOM) | NRE only | REQ-MOD-COMMON-030..032 |
| Inspection story | Distinct MCU marking + no antenna keepout = unpowered verifiability | $0 | REQ-MOD-AIR-021 |
| Mis-plug fail-safe (4th ruling) | TPS26621 60 V auto-retry eFuse ahead of the LDO + DETECT series R + pin-7 treatment + T1 CMC/caps/TVS (every family carries the T1 network per the 6th ruling) | +$2.7 every family | REQ-MOD-COMMON-053; survey 11 |

Enterprise sensing tier = **Pro-class characterization** per family where §6.13 defines it
(REQ-MOD-COMMON-040): the fast-ADC path, streamed over **100BASE-T1** (3rd ruling). DETECT
moves 2.2 kΩ → **10 kΩ** (the locked CAN+100BASE-T1 class) on EVERY ENT family — the
24-pin included per the 6th ruling (its T1 carries sync/attestation/logistics, not a
fast-ADC stream; sensing stays INA228).

## 1. 24-pin ATX — ENT build

Role: energy accountant + Hub bulk-5VSB source + mezzanine base. No Pro SKU exists for
this family; the ENT build = rev3 design + common deltas (sensing stays INA228). 6th
ruling (2026-07-02): the family joins the T1 fabric — its T1 carries sync, attestation
surfaces, and fleet logistics (firmware/evidence off the shared CAN bus), NOT a fast-ADC
stream; the rationale is that this module is the fleet's most load-bearing validator
(REQ-HUB-COMMON-113's power-signature surface is built on ITS rail data).

| Spec | Value | Trace |
|---|---|---|
| Sensing | 4× INA228 (12V/5V/3V3/5VSB; hardware energy/charge counters), §6.4 shunts (2 mΩ ×3, 25 mΩ) — UNCHANGED | REQ-24PIN-001/002 |
| Transient detection | §6.13 front-end (INA181A2 + TLV7011 per rail → FREEZE) — retained | REQ-24PIN-003 |
| MCU | **ESP32-P4** (uniform ENT MCU, 6th ruling — GPIO budget moot; supersedes the survey-8 STM32G431 pick) | owner ruling 2026-07-02 (6th); REQ-MOD-COMMON-003 |
| Streaming/link | **100BASE-T1** on pair 2 (DP83TC814S-Q1 + CMC/caps/PESD, same front-end as the streaming families) — gPTP participant | REQ-MOD-COMMON-003; survey 10 |
| Power topology | Bulk 5VSB source (JST) + J1.1 open + MAIN_5V tap downstream of the 5V shunt — UNCHANGED locked | REQ-24PIN-010/011 |
| DETECT | **10 kΩ** (CAN+100BASE-T1 — was 2.2 kΩ CAN-only pre-6th-ruling) | §2.3; owner ruling 2026-07-02 (6th) |
| Mezzanine | Male stack header populated if OQ-77 adopts the integrated form | REQ-24PIN-020 |

BOM delta vs `modules/atx-24pin-rev3`: −ESP32-C6-MINI-1-N4 (~$3.5) / +ESP32-P4 ($4.47) +
external QSPI flash + support (~$1–1.5) / +100BASE-T1 front-end (DP83TC814S-Q1 $2.39 +
CMC/caps/PESD ≈ $3.0–4.2 total) / identity ≈$0 (5th ruling — MCU-resident key) / DETECT R
swap ($0) / native-USB flashing retained (P4 has USB, no bridge). **Net delta ≈ +$5–7**
→ ENT-24-pin parts class ≈ **$40–44** (vs the $35* consumer target). The hub-side cost of
this flip is $0 — all 8 ENT ports already terminate T1 (REQ-HUB-COMMON-043).

## 2. EPS 8-pin — ENT build (= EPS Pro per §6.13)

| Spec | Value | Trace |
|---|---|---|
| Sensing | Per-cable INA238 (2 cables, 0.5 mΩ) + INA240 fast path + **simultaneous fast ADC** + §6.13 detection floor | REQ-EPS-001/002; spec §6.13 |
| Fast ADC | **ADS131M08-class** working baseline (8-ch simultaneous 24-bit ΔΣ, ~$5–8 `[unv]`); LTC2358-18 is the spec'd alternative (~$18–25 `[unv]`) — choice mirrors OQ-21 | spec §6.13 |
| Streaming | **100BASE-T1** (pins 4/5, bidirectional + sub-µs sync): DP83TC814S-Q1 ($2.39) + OPEN-Alliance CMC + PESD2ETH100 ≈ $3.0–4.2/module (survey 10; TJA1103 $1.49+1588 = NDA-flagged alt) | survey 10; REQ-MOD-COMMON-003/HUB-106 |
| MCU | **ESP32-P4** (survey 10 resolved: uniform across streaming families — RMII + HW 1588/PPS confirmed, reuses the 12VHPWR Pro reference design; STM32H563 documented fallback; no MAC-integrated T1 part exists to rescue G474) | survey 10; REQ-MOD-COMMON-003 |
| DETECT | **10 kΩ** (CAN+100BASE-T1 — the locked reserved class) | §2.3 |
| Events | §6.10 pre-roll + per-cable attribution into the Hub tamper/event log | REQ-EPS-003 |

BOM delta vs `modules/eps-8pin-rev2` (consumer ≈ $32-class): −C6-MINI (+$3.5 back) /
+G474 ($3.93) + support (~$0.8) / +ADS131M08 ($5–8) + ref/filters (~$1) / +INA240 ×2
(~$1.9 ea if per-cable fast path; count per §6.13 detail) / +100BASE-T1 PHY (~$2-4 [survey 10]) / +identity
(TBD) / DETECT R swap ($0). **Net delta ≈ +$12–19** → ENT-EPS parts class ≈ **$45–55**,
consistent with the spec's §6.13 Pro indicative $85–110 retail-class positioning.

## 3. PCIe 8-pin (2-port / 3-port) — ENT builds (= PCIe Pro)

Identical architecture to §2 with 2 or 3 cables (3 = spec upper bound):

| Spec | Value | Trace |
|---|---|---|
| Sensing | Per-cable INA238 ×2/×3 + INA240 fast path + ADS131M08-class + §6.13 floor | REQ-PCIE-001/002 |
| MCU / streaming / DETECT | As EPS ENT (RMII MCU per survey 10; 100BASE-T1; 10 kΩ) | survey 8/10; §2.3 |
| Events | GPU-rail §6.10 pre-roll + per-cable attribution (named differentiator) | REQ-PCIE-003 |

BOM delta vs `modules/pcie-8pin-{2,3}port-rev2`: as EPS **+$12–19**, plus the 3rd-cable
INA238/INA240/shunt set on the 3-port (≈ +$4–6). In-path FMEA covers the Molex 45586
headers + shunt verticals per OQ-10/12 (deliverable).

## 4. 12VHPWR — ENT build (= the existing 12VHPWR Pro design + common deltas)

The flagship forensic family; the Pro board (`modules/12vhpwr-pro/`, $98–99 target,
schematic stage) IS the enterprise baseline — already ESP32-P4 (radio-free, survey 8).

| Spec | Value | Trace |
|---|---|---|
| Sensing | 6× INA240A3 per-pin (1 mΩ) + **LTC2358-18** 8-ch simultaneous 18-bit + 47k/10k rail divider + REF3033; streaming moves RS-485 → **100BASE-T1** for ENT (3rd ruling; the P4 MAC serves it — RS-485 stays on the consumer Pro SKU) | REQ-HPWR-001/002; spec §6.9; REQ-MOD-COMMON-003 |
| MCU | **ESP32-P4** (unchanged — radio-free; QFN-104, external flash) | survey 8 |
| DETECT | ENT build: 10 kΩ (CAN+100BASE-T1); consumer Pro keeps 4.7 kΩ | §2.3 |
| Pin-hog alarm | Sustained per-pin outlier detection (the 58%-instant-electrical-outlier signature) | REQ-HPWR-003 |
| Sideband | S1..S4 pass-through + monitored (v3.4 taps) | REQ-HPWR-010 |
| Deltas to reach ENT | + identity device (OQ-76); + NTC board/ambient pair if carried over from Std (Pro TBD); + provenance BOM pass; graduate the board out of DRAFT (ERC/DRC-clean) before ratification cites it | REQ-HPWR-002; common §0 |

BOM delta vs the Pro target: **≈ +$1–3** (identity + NTC pair + margin) → parts class
stays ≈ **$99–102** `[existing $98–99 target + deltas; RFQ at board completion]`. The
CEM5.1 +12V/GND row verification remains a pre-power checklist item on every rev
(REQ-HPWR-011).

## 5. Cross-family open rows

1. ~~OQ-76 identity mechanism~~ RESOLVED (5th ruling): MCU-resident key + challenge-response
   + poke-and-ack, ≈$0; the provisioning-fixture implication (key injection at the flashing
   step) remains a factory-process deliverable.
2. **One-build-serves-both-postures** recommendation (§0) — owner ratify or split SKUs.
3. **Fast-ADC choice** (ADS131M08 vs LTC2358-18) for EPS/PCIe ENT — cost-vs-precision,
   mirrors OQ-21; 12VHPWR Pro keeps LTC2358 as designed.
4. **INA240 count per cable** on EPS/PCIe Pro (§6.13 detail) — sets the fast-path BOM rows.
5. **OQ-11 shunts** — must close before any ENT module board starts (REQ-MOD-COMMON-051).
6. **12VHPWR Pro DRAFT graduation** — ERC/DRC-clean is a prerequisite to citing it as the
   ENT baseline (REQ-HPWR-002).
7. **Mezzanine population** on the 24-pin ENT — rides OQ-77.
