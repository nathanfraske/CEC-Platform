# ENT product matrix — hubs + modules (tiering map)

_Status: DRAFT (2026-07-02, post-7th-ruling). One page of orderable truth: what exists,
what differs per SKU, what interoperates. Authority: hub register (REQ-105 SKU
identifiability), spec sheets, module registers, conformance matrix. Parts totals are
COST FLOORS at 100q [est/RFQ], never prices (D-ENT-3)._

## 1. Where ENT sits in the platform ladder

| Tier | Hub compute | Module link | Positioning |
|---|---|---|---|
| Standard | ESP32-S3, 4 ports | CAN 500k | Mainstream builders |
| Pro | ESP32-P4, 8 ports | CAN + RS-485 streaming | Overclockers, bench |
| Max (module SKUs, PROPOSED) | — | per OQ-20 | Spectral/HF capture ladder |
| **ENT (one line, SKU-differentiated)** | PolarFire SoC, 8 ports | CAN + **100BASE-T1** (bidir + sub-µs gPTP) + **pin-7 SYNC/heartbeat** | Regulated / tamper-mandated fleets |

Three orthogonal ENT axes: **posture** (NET / AIR) × **availability** (B / MC / MC-Max)
× **silicon** (base / HS). 6 base SKUs; HS is orderable on any of them → 12 configs.

## 2. Hub SKU matrix

| | NET-B | NET-MC | NET-MCX | AIR-B | AIR-MC | AIR-MCX |
|---|---|---|---|---|---|---|
| Posture | networked-hardened | ″ | ″ | **air-gapped, zero egress by design** | ″ | ″ |
| Uplink (1000BASE-T) | 1× | 2× | 2× | **none — no PHY populated** (inspection-verifiable) | none | none |
| Northbound | Redfish-subset + OpenMetrics + syslog-TLS, RBAC | ″ | ″ | local operator paths + removable export only | ″ | ″ |
| Independent compute watchdog | — | ● | ● | — | ● | ● |
| Fail-functional voting pair (2nd SoC, 2oo2 + watchdog arbiter, fabric/LVDS sync) | — | — | ● | — | — | ● |
| Redundancy pack (dual uplink / monitored sources) | option | ● | ● | option (sources) | ● | ● |
| RJ-11 security I/O (loop-in + dry-contact out) | on request | on request | on request | ● | ● | ● |
| NanoKVM aux | populated | populated | populated | header only (KVM excluded from base builds) | ″ | ″ |
| eMMC (one FBGA-153 land) | 8 GB | 8 GB | 8 GB | 32 GB (64 GB opt) | ″ | ″ |
| Parts floor [est] | $214–274 | $239–307 | $394–507 | $198–256 | $206–273 | $356–466 |

**Every hub SKU (common):** one PCB, population-differentiated (REQ-105, externally
identifiable); PolarFire SoC on the part-agnostic SerDes-free FCVG484 land; QSPI NOR
32 MB (A/B firmware + rollback-resistant tamper log); 3-source eFuse-fronted priority-OR
power with FULL/STANDBY postures + persist-on-fault; 8× RJ-45 FTP module ports (CAN
500k + per-port 100BASE-T1 via 2× LAN9370 + per-port pin-7 into fabric); mis-plug
fail-safe (live-switch/57 V PoE, self-recovering, port-local); Zephyr no-Linux; signed
A/B firmware + anti-rollback; IDevID identity; SBOM/PSIRT from first release.

**Silicon option (7th ruling):**

| | Base build | HS build (population option) |
|---|---|---|
| SoC fitted | **MPFS095TC** (Core; FAE-conditional) | **MPFS095TS** (S-grade) |
| Secure boot + PUF identity + tamper | ● | ● |
| Runtime crypto | wolfCrypt validated module (software) | ″ + **Athena TeraFire DPA-resistant hardware crypto** |
| Who buys it | default | high-assurance / defense channels; anyone specifying side-channel-hardened silicon |
| Density headroom | same land accepts 025/095/160/250 × T/TS/TC | ″ |

## 3. Module ENT builds (5 SKUs, 4 families)

All ENT modules share: **ESP32-P4** (radio-free, uniform — one toolchain), **100BASE-T1**
on pair 2 (DP83TC814S-Q1 + protection network) + CAN 500k, **DETECT 10 kΩ**
(CAN+100BASE-T1 class), gPTP participant + **pin-7 heartbeat responder** (miss →
auto-untrust), MCU-resident key identity (≈$0 silicon), TPS26621 mis-plug eFuse,
signed firmware, §6.10 pre-roll, tier-agnostic graceful degrade (locked §1/§8).

| Module SKU | Sensing | Family-specific | Parts class [est] (vs consumer) |
|---|---|---|---|
| 24-pin ATX ENT | 4× INA228 (energy/charge counters) + §6.13 front-end — unchanged | Bulk 5VSB source + MAIN_5V tap; mezzanine base (OQ-77); the fleet's power-signature validator | ~$40–42 (+$5–7) |
| EPS 8-pin ENT (= EPS Pro) | Per-cable INA238 ×2 + INA240 fast path + ADS131M08-class simultaneous ADC | 2-cable interposer | ~$45–52 (+$13–20) |
| PCIe 2-port ENT (= PCIe Pro) | As EPS, ×2 cables | GPU-rail pre-roll + per-cable attribution | ~$45–52 (+$13–20) |
| PCIe 3-port ENT | As EPS, ×3 cables | ″ + 3rd cable set | ~$49–58 (+$17–26) |
| 12VHPWR ENT (= Pro + deltas) | 6× INA240 per-pin + LTC2358-18 18-bit simultaneous + rail divider | Flagship forensics; pin-hog alarm; sideband monitor; RS-485→T1, DETECT 4.7k→10k | ~$99–102 (+$1–3) |

## 4. Cross-compatibility (the tier-agnostic guarantee)

| | Standard/Pro hub | ENT hub |
|---|---|---|
| Consumer Standard modules (2.2 kΩ) | native | CAN fully serviced; §6.13 FREEZE over CAN; class-level identity only (documented) |
| Consumer 12VHPWR Pro (4.7 kΩ, RS-485) | streams on Pro hub | CAN serviced; **RS-485 pair dark** (T1-only hub — same §8 pattern as on a Standard hub) |
| ENT modules | function fully on CAN; T1 + heartbeat + sync dormant; never fault the link | native: T1 streaming/sync + heartbeat + multi-surface validation |

Fleet-trust note: legacy modules on an ENT deployment sit at the class-level trust
floor (conformance matrix); full per-unit identity + heartbeat requires ENT builds.

## 5. Orderable summary

- **Hubs:** 6 SKUs × 2 silicon builds = 12 configs, one PCB. Naming axis:
  `ENT-{NET|AIR}-{B|MC|MCX}[-HS]`.
- **Modules:** 5 ENT SKUs (radio-free single build serves both postures — working
  recommendation, ratify at Phase 3/4). Platform cables/accessories unchanged.
- **Optional attach:** NanoKVM (NET), CEC-KVM (OQ-75, exploration), tamper-module
  family (OQ-78, pending), mezzanine integrated form (OQ-77, pending).
