# Enterprise Hub requirements register (PolarFire, ENT-AIR / ENT-NET)

_All sections DRAFT. Schema: `REQUIREMENTS-FORMAT.md`. Compute = PolarFire per owner
direction (plan §1a); the §1 tier-table rewrite and OQ-7 close are Phase-4 owner acts.
Variant↔tier mapping (and the home of the redundancy pack) is open — D-ENT-6._

## 1. Compute, identity & provenance — DRAFT

The audit's verdict: identity/attestation is bought as evidence, not silicon. PolarFire
supplies the root (PUF, DPA-resistant secure boot, Athena crypto); these rows make it an
operational identity story (OQ-44/62 both route hard provenance here).

| ID | Requirement | Trace | Verify | Gate |
|---|---|---|---|---|
| REQ-HUB-COMMON-001 | The Hub SHALL be built on a PolarFire SoC part selected by the Phase-2 sizing survey; the part SHALL provide secure boot rooted in on-die keys (PUF) and a crypto coprocessor. | plan §1a.1; spec App B.3/B.5 | I | D-ENT-2 (part #) |
| REQ-HUB-COMMON-002 | The Hub SHALL run without any Linux OS: an RTOS or bare-metal control plane, with data-plane offload in fabric. | spec App B.3/B.5 | I+D | — |
| REQ-HUB-COMMON-003 | Each Hub SHALL carry a per-device cryptographic identity (IDevID-class, 802.1AR-aligned) provisioned at manufacture and rooted in the PolarFire key store; the factory-MAC+database scheme (spec §4) is NOT sufficient at this tier. | audit §3/§5; spec §4 contrast; OQ-44 | I+T | — |
| REQ-HUB-NET-004 | The Hub SHALL support operator certificate enrollment (LDevID-class, EST or SCEP) without physical access to the device. | audit §3 (fleet) | T | — |
| REQ-HUB-AIR-005 | All identity/attestation functions SHALL be fully exercisable with no network connectivity: local enrollment and offline attestation-evidence export over the operator-facing local interface. | plan §1a.2; audit §5 | D | — |
| REQ-HUB-COMMON-006 | The Hub SHALL produce signed attestation evidence of its firmware measurement chain on demand, consumable by third-party tooling (format fixed in Phase-2 research item 1). | audit §3; OQ-44/OQ-62 | T | — |
| REQ-HUB-COMMON-007 | Appendix-D support-pipeline plan execution SHALL verify plan signatures against the Hub root of trust before actuation (the OQ-62 tie lands here). | spec App D; OQ-62 | T | — |

## 2. Firmware, boot & update security — DRAFT

Audit finding 3: this is a platform-wide legal floor (EU CRA), tiered up in strength here —
the gaps are process (PSIRT, key custody), not silicon.

| ID | Requirement | Trace | Verify | Gate |
|---|---|---|---|---|
| REQ-HUB-COMMON-010 | The Hub SHALL boot only firmware whose signature chains to the platform root; rollback protection SHALL be enforced by monotonic anti-rollback state. | audit §3; tamper §2 | T | — |
| REQ-HUB-COMMON-011 | Firmware updates SHALL be signed; the signing-key custody procedure SHALL be documented and owner-ratified before first enterprise ship. | audit §2 (process gap) | I | D-ENT-5 |
| REQ-HUB-NET-012 | OTA update SHALL be available over the northbound management interface with staged rollout and automatic rollback on failed health check. | audit §3 (fleet) | T | — |
| REQ-HUB-AIR-013 | Update SHALL be possible from a signed offline bundle applied via local media/interface, with the same signature+anti-rollback enforcement as OTA, and SHALL NOT require any network egress. | plan §1a.2; audit §1.5 | T+D | — |
| REQ-HUB-COMMON-014 | Every firmware release SHALL ship with an SBOM; a PSIRT/coordinated-vulnerability-disclosure process and a declared support period SHALL exist before enterprise GA (EU CRA floor — binds the whole platform, strength-tiered here). | audit §1.3/§2 | I | — |

## 3. Northbound management & data surface — DRAFT

Audit blocker #1: without this the enterprise Hub cannot be onboarded by anything. The
protocol set is drafted maximal here and pruned at Phase-3 review.

| ID | Requirement | Trace | Verify | Gate |
|---|---|---|---|---|
| REQ-HUB-NET-020 | The Hub SHALL expose its telemetry and health over at least: a Redfish-aligned REST model, SNMPv3 with a published MIB, and an OpenMetrics/Prometheus endpoint. | audit §1.1/§3 | T | D-ENT-5 (protocol prune) |
| REQ-HUB-NET-021 | Security/tamper events SHALL be forwardable as syslog (TLS) and SHALL be SIEM-ingestable without a host agent. | audit §3; tamper §2 | T | — |
| REQ-HUB-NET-022 | The network management plane SHALL be the primary operational interface; USB SHALL be demoted to sensing/provisioning roles on ENT-NET. | audit §1.5 | I+D | — |
| REQ-HUB-NET-023 | Management-plane access SHALL enforce authenticated, role-separated access (at minimum: viewer / operator / administrator) with an audit log of configuration changes. | audit §2 | T | — |
| REQ-HUB-AIR-024 | ENT-AIR SHALL provide the equivalent operational surface locally (operator port / console / removable export) with **zero network egress by design**, verifiable by inspection of the build (no PHY populated or PHY fused off — form decided with D-ENT-6). | plan §1a.2 | I+D | D-ENT-6 |
| REQ-HUB-COMMON-025 | Host-down operation SHALL be a verified test case: full telemetry acquisition, event logging, and (NET) northbound reporting with the host OS absent/crashed/powered down, on standby power. | audit §1.5/§1.6; spec §2.9 | T | — |

## 4. Host & uplink physical interfaces — DRAFT

Audit blocker #2: 1000BASE-T1 (automotive SPE) is unusable on enterprise switching; the
challenged assumption is adopted here as a draft reversal, pending owner ratification.

| ID | Requirement | Trace | Verify | Gate |
|---|---|---|---|---|
| REQ-HUB-NET-030 | The primary uplink SHALL be standard IEEE 802.3 Ethernet (1000BASE-T RJ-45 baseline; SFP option study in Phase 2), with magnetics and the OQ-14 enterprise over-voltage protection landing on this port. | audit §1.2/§4; OQ-14 | I+T | Phase-4 spec edit (supersedes §1 "optional 1000BASE-T1") |
| REQ-HUB-NET-031 | 1000BASE-T1 SHALL NOT be the default uplink; it MAY remain a factory option for embedded/OEM integrations. | audit §4 | I | — |
| REQ-HUB-COMMON-032 | The USB host link SHALL remain present on both variants for sensing/provisioning (ENT-NET) and as a primary local interface (ENT-AIR), per the platform base design. | audit §1.5; spec §4 | I | — |
| REQ-HUB-COMMON-033 | The RJ-11 trust channel SHALL either receive a concrete specified function (physical/protocol/threat model, Phase-2 research item 3) or be dropped from the tier definition — it SHALL NOT ship as an unspecified connector. | audit §4; spec §1 row | I | D-ENT-5 |

## 5. Module interface conformance (locked platform carry-ins) — DRAFT

The module-facing side is the LOCKED universal interface; the enterprise Hub inherits it
unchanged so every existing module works (§8 principle).

| ID | Requirement | Trace | Verify | Gate |
|---|---|---|---|---|
| REQ-HUB-COMMON-040 | Module ports SHALL be RJ-45 8P8C FTP per the locked pin allocation table (pins 1–8 incl. pin 7 reserved spare, pin 8 DETECT). | [LOCKED §2.1/§2.3] | I+T | — |
| REQ-HUB-COMMON-041 | CAN SHALL be classical 500 kbps with fixed 120 Ω split termination at the Hub; CAN-FD SHALL NOT be enabled by default (any enterprise CAN-FD case goes through the spec-revision door). | [LOCKED §3.1] | I+T | — |
| REQ-HUB-COMMON-042 | DETECT SHALL be read per the §2.3 code table (10 kΩ pull-up to 3.3 V; open=absent, short=fault) and each port SHALL carry the locked pin-8 ESD diode. | [LOCKED §2.3/§2.4] | I+T | — |
| REQ-HUB-COMMON-043 | The Hub SHALL service RS-485 streaming (pins 4/5) on all ports (receiver topology per OQ-5), so Pro/Max modules run native. | spec §3.2; OQ-5 | T | OQ-5 |
| REQ-HUB-COMMON-044 | Bulk power SHALL enter on the dedicated 2-pin +5VSB connector with per-port 5VSB distribution over RJ-45 VCC, per the locked §2.7 scheme, extended by the §2.9 multi-source priority-OR (see §7 below). | [LOCKED §2.7]; spec §2.9 | I+T | — |
| REQ-HUB-COMMON-045 | A module SHALL never fail to function when attached to the enterprise Hub; higher-tier module features degrade gracefully per §8 (see `module-conformance-matrix.md`). | [LOCKED §1/§8] | T | — |

## 6. Redundancy & fail-detected operation — DRAFT (placement pending D-ENT-6)

Audit finding 6: sellable redundancy is **fail-detected** redundancy — observable, alarmed,
self-testable — not implied end-to-end fault tolerance (the module chain stays single-path
by LOCKED design and is honestly declared as such).

| ID | Requirement | Trace | Verify | Gate |
|---|---|---|---|---|
| REQ-HUB-COMMON-050 | Every redundant element (power feed, uplink, CAN transceiver where fitted) SHALL be individually monitored; loss of redundancy SHALL raise an alarm within a bounded time even though service continues. | audit §1.6 | T | D-ENT-6 |
| REQ-HUB-COMMON-051 | Failover paths SHALL be self-testable on operator command without taking the monitored machine down. | audit §1.6 | D | D-ENT-6 |
| REQ-HUB-COMMON-052 | The Hub SHALL accept a power feed independent of the monitored PSU (the §2.9 third source, graduated from PROPOSED to binding at this tier) and SHALL ride through monitored-PSU loss while logging the event. | audit §1.6; spec §2.9; OQ-53..56 | T | D-ENT-6 |
| REQ-HUB-COMMON-053 | Documentation SHALL state explicitly that the module sensing chain (RJ-45/CAN/DETECT) is single-path by platform design; no marketing/spec text may imply sensing-path fault tolerance. | audit §1.6 honesty framing | I | — |

## 7. Power input & distribution — DRAFT

| ID | Requirement | Trace | Verify | Gate |
|---|---|---|---|---|
| REQ-HUB-COMMON-060 | The Hub SHALL implement the §2.9 three-source priority-OR (PSU main 5V > 5VSB > external/wall-wart via NanoKVM path) with firmware rail-sense and load budgeting; parts per OQ-53..56. | spec §2.9 | I+T | OQ-53..56 |
| REQ-HUB-COMMON-061 | Total 5VSB draw SHALL respect the OQ-2 budget with the LED cap enforced in firmware. | [LOCKED LED-cap intent]; OQ-2 | T | OQ-2 |
| REQ-HUB-COMMON-062 | A persist-on-fault flush of telemetry and event state to local flash SHALL complete on any power-source transition, sized against the hold-up capacity (OQ-56 bench item). | spec §2.9; tamper §2 | T | OQ-56 |

## 8. Tamper & physical security (hub-resident half) — DRAFT

From the tamper research; the sensor-bearing halves live in the module registers / the §3a
candidate modules. The Hub is the log custodian.

| ID | Requirement | Trace | Verify | Gate |
|---|---|---|---|---|
| REQ-HUB-COMMON-070 | The Hub SHALL maintain a tamper/security event log that is rollback-resistant (monotonic counter or equivalent in NVM), survives power-off and unplugging, and is exportable with integrity proof. | tamper §1/§2 | T | — |
| REQ-HUB-COMMON-071 | Tamper events SHALL be captured on standby power, and on total external-power loss the most recent state SHALL be recoverable via the persist-on-fault path (REQ-HUB-COMMON-062). | tamper §2; spec §2.9 | T | — |
| REQ-HUB-NET-072 | Tamper events SHALL be SIEM-forwardable (REQ-HUB-NET-021) with severity classification; ENT-AIR SHALL surface the same events on the local operational surface. | tamper §2; audit §3 | T | — |
| REQ-HUB-COMMON-073 | If the ATR (anti-tamper-radio) module is adopted (plan §3a.2), the Hub SHALL gate its RF emission by variant policy — the ENT-AIR radio posture decision (plan §1a.5) governs; emission with the policy unset SHALL default OFF. | plan §3a.2/§1a.5 | T | D-ENT-5 |

## 9. Reliability & fail-passive (interposer honesty at the platform level) — DRAFT

Audit blocker #4 lives mostly in the module registers (they sit in the power path); the Hub
carries the fleet-facing reliability evidence.

| ID | Requirement | Trace | Verify | Gate |
|---|---|---|---|---|
| REQ-HUB-COMMON-080 | The Hub SHALL publish MTBF/FIT predictions and a derating report per release hardware revision. | audit §2 (procurement) | A | — |
| REQ-HUB-COMMON-081 | Hub failure modes SHALL NOT disturb the monitored machine: an FMEA covering every host-coupled interface (5VSB tap, USB, module ports) with fault-injection test evidence SHALL exist before enterprise GA. | audit §1.4 | A+T | — |

## 10. Environmental, compliance & lifecycle — DRAFT

| ID | Requirement | Trace | Verify | Gate |
|---|---|---|---|---|
| REQ-HUB-COMMON-090 | The Hub SHALL meet a declared compliance baseline: EMC (as consumer line) plus the enterprise set fixed by Phase-2 research item 7 (candidates: IEC 62443 SL-target, FIPS 140-3 module boundary for the crypto, CRA conformity) — this row pins the decision obligation, not the final list. | audit §2; plan Phase 2.7 | I | Phase-2 output |
| REQ-HUB-COMMON-091 | Product lifecycle commitments SHALL be declared at GA: ≥5-year availability, spares/RMA policy, ≥12-month EOL notice, declared security-support period. | audit §2 (procurement blocker) | I | D-ENT-3 (pricing) |
| REQ-HUB-COMMON-092 | BOM/pricing SHALL be value-based per the D-ENT-3 re-baseline (comparables $1.5k–3k/unit class), costing in the compliance/warranty/support tail — not parts-plus-margin. | audit §1.7 | A | D-ENT-3 |
| REQ-HUB-COMMON-093 | A named target-fleet statement (BMC-less ATX-architecture machines as the wedge) SHALL be ratified and carried in the spec revision, resolving the served-market contradiction (CRPS rack servers are out of scope unless a PDB module family is committed). | audit §1.8 | I | Phase-4 spec edit |

## 11. Mechanical & packaging — DRAFT

| ID | Requirement | Trace | Verify | Gate |
|---|---|---|---|---|
| REQ-HUB-COMMON-100 | The Hub SHALL retain the platform mounting scheme (M3 chassis-grounded) and SHALL offer the mezzanine integrated-stack option (Hub-on-24-pin) if D-ENT-5 adopts it for the enterprise form. | docs/mezzanine-stack-design-2026-06-24.md | I | D-ENT-5 |
| REQ-HUB-AIR-101 | ENT-AIR build state (no network PHY / fused-off posture, radio policy) SHALL be visually verifiable at inspection without powering the unit (labeling + population differences documented). | plan §1a.2/§1a.5 | I | D-ENT-5/6 |
