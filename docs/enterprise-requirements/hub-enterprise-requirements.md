# Enterprise Hub requirements register (PolarFire, ENT-AIR / ENT-NET)

_All sections DRAFT. Schema: `REQUIREMENTS-FORMAT.md`. Compute = PolarFire per owner
direction (plan §1a); the §1 tier-table rewrite and OQ-7 close are Phase-4 owner acts
(drafted: `docs/spec-revision-v1.2.0-draft-2026-07-02.md`). D-ENT-6 RESOLVED 2026-07-02:
one ENT line, SKU differentiators — posture (NET/AIR) × availability (base / MC = watchdog
+ redundancy pack / MC-Max = fail-functional voting pair); see REQ-HUB-COMMON-103..105._

## 1. Compute, identity & provenance — DRAFT

The audit's verdict: identity/attestation is bought as evidence, not silicon. PolarFire
supplies the root (PUF, DPA-resistant secure boot, Athena crypto); these rows make it an
operational identity story (OQ-44/62 both route hard provenance here).

| ID | Requirement | Trace | Verify | Gate |
|---|---|---|---|---|
| REQ-HUB-COMMON-001 | The Hub SHALL be built on a PolarFire SoC providing secure boot rooted in on-die keys (PUF) and the Athena crypto coprocessor — i.e. an S-suffix part (owner-confirmed 2026-07-02). Working baseline: MPFS095TS in FCVG484, preserving the pin-compatible 025T/160T ladder as cost/headroom options. | plan §1a.1; spec App B.3/B.5; survey 1 | I | — |
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
| REQ-HUB-COMMON-014 | Every firmware release SHALL ship with an SBOM (from the first enterprise release; `west spdx`-class tooling); a PSIRT/CVD process and a declared support period SHALL exist before enterprise GA. If any product is placed on the EU market these become CRA-bound on the Art. 14/71 calendar per REQ-HUB-COMMON-094 — EU entry is deferred but kept open (owner ruling 2026-07-02). | audit §1.3/§2; survey 6/7 | I | — |

## 3. Northbound management & data surface — DRAFT

Audit blocker #1: without this the enterprise Hub cannot be onboarded by anything. The
protocol set is drafted maximal here and pruned at Phase-3 review.

| ID | Requirement | Trace | Verify | Gate |
|---|---|---|---|---|
| REQ-HUB-NET-020 | The Hub SHALL expose its telemetry and health over at least a Redfish-aligned REST subset (full DSP0266 conformance is a non-goal at GA) and an OpenMetrics/Prometheus endpoint. SNMPv3 + published MIB SHALL be deferred past GA or fulfilled via a licensed commercial agent stack (no mature RTOS implementation exists) — prune adopted per owner ruling 2026-07-02. | audit §1.1/§3; survey 6 | T | — |
| REQ-HUB-NET-021 | Security/tamper events SHALL be forwardable as syslog (TLS) and SHALL be SIEM-ingestable without a host agent. | audit §3; tamper §2 | T | — |
| REQ-HUB-NET-022 | The network management plane SHALL be the primary operational interface; USB SHALL be demoted to sensing/provisioning roles on ENT-NET. | audit §1.5 | I+D | — |
| REQ-HUB-NET-023 | Management-plane access SHALL enforce authenticated, role-separated access (at minimum: viewer / operator / administrator) with an audit log of configuration changes. | audit §2 | T | — |
| REQ-HUB-AIR-024 | ENT-AIR SHALL provide the equivalent operational surface locally (operator port / console / removable export) with **zero network egress by design**, verifiable by inspection of the build (no network PHY populated — the inspection-verifiable form, per the SKU identifiability rule REQ-HUB-COMMON-105). | plan §1a.2; owner ruling 2026-07-02 | I+D | — |
| REQ-HUB-COMMON-025 | Host-down operation SHALL be a verified test case: telemetry acquisition, event logging, tamper capture, and (NET) northbound reporting with the host OS absent/crashed/powered down, exercised in the STANDBY power posture defined by REQ-HUB-COMMON-026. | audit §1.5/§1.6; spec §2.9; survey 1 | T | — |
| REQ-HUB-COMMON-026 | The Hub SHALL define two power postures and its guarantees per posture: FULL (MAIN_5V primary — complete compute + data plane) and STANDBY (5VSB and/or independent feed — telemetry acquisition, event logging, tamper capture, and persist-on-fault guaranteed; northbound service best-effort within the 5VSB budget). PolarFire-class full compute SHALL NOT be assumed on the 5VSB budget. | survey 1 (5VSB collision); spec §2.9; OQ-2 | A+T | — |

## 4. Host & uplink physical interfaces — DRAFT

Audit blocker #2: 1000BASE-T1 (automotive SPE) is unusable on enterprise switching; the
challenged assumption is adopted here as a draft reversal, pending owner ratification.

| ID | Requirement | Trace | Verify | Gate |
|---|---|---|---|---|
| REQ-HUB-NET-030 | The primary uplink SHALL be standard IEEE 802.3 Ethernet (1000BASE-T RJ-45 baseline; SFP option study in Phase 2), with magnetics and the OQ-14 enterprise over-voltage protection landing on this port. | audit §1.2/§4; OQ-14 | I+T | Phase-4 spec edit (supersedes §1 "optional 1000BASE-T1") |
| REQ-HUB-NET-031 | 1000BASE-T1 SHALL NOT be the default uplink; it MAY remain a factory option for embedded/OEM integrations. | audit §4 | I | — |
| REQ-HUB-COMMON-032 | The USB host link SHALL remain present on both variants for sensing/provisioning (ENT-NET) and as a primary local interface (ENT-AIR), per the platform base design. | audit §1.5; spec §4 | I | — |
| REQ-HUB-COMMON-033 | The RJ-11 SHALL be a supervised physical-security I/O port (renamed off "trust channel"): an EOL-resistor-supervised tamper-loop input plus a galvanically isolated dry-contact alarm output, riding the Hub's always-on power domain and writing into the REQ-HUB-COMMON-070 log; no data protocol, no parser, no path to CAN/DETECT. Populated by default on ENT-AIR, populate-on-request on ENT-NET. The OQ-60 per-port Max sideband proposal SHALL NOT reuse this port's name or identity (one-shell/two-owners resolved in favor of the security port, owner 2026-07-02; OQ-60's connector renames at its own decision point). | survey 3; owner ruling 2026-07-02; tamper §1/§2 | I+T | — |

## 5. Module interface conformance (locked platform carry-ins) — DRAFT

The module-facing side is the LOCKED universal interface; the enterprise Hub inherits it
unchanged so every existing module works (§8 principle).

| ID | Requirement | Trace | Verify | Gate |
|---|---|---|---|---|
| REQ-HUB-COMMON-040 | Module ports SHALL be RJ-45 8P8C FTP per the locked pin allocation table (pins 1–8 incl. pin 7 reserved spare, pin 8 DETECT). | [LOCKED §2.1/§2.3] | I+T | — |
| REQ-HUB-COMMON-041 | CAN SHALL be classical 500 kbps with fixed 120 Ω split termination at the Hub; CAN-FD SHALL NOT be enabled by default (any enterprise CAN-FD case goes through the spec-revision door). | [LOCKED §3.1] | I+T | — |
| REQ-HUB-COMMON-042 | DETECT SHALL be read per the §2.3 code table (10 kΩ pull-up to 3.3 V; open=absent, short=fault) and each port SHALL carry the locked pin-8 ESD diode. | [LOCKED §2.3/§2.4] | I+T | — |
| REQ-HUB-COMMON-043 | The Hub SHALL service the module streaming pair (pins 4/5) on all ports in DUAL MODE, selected per port by the DETECT class: **100BASE-T1** (primary — ENT modules, DETECT 10 kΩ, bidirectional, fabric MAC/switch data plane) and RS-485 receive (backward compat for Pro-tier consumer modules, DETECT 4.7 kΩ) — unless the owner explicitly drops RS-485 compat (sub-choice, survey 10). | owner ruling 2026-07-02 (3rd); spec §2.3 10 kΩ class; OQ-20 (ENT-resolved) | T | OQ-5 (RS-485 leg) |
| REQ-HUB-COMMON-044 | Bulk power SHALL enter on the dedicated 2-pin +5VSB connector with per-port 5VSB distribution over RJ-45 VCC, per the locked §2.7 scheme, extended by the §2.9 multi-source priority-OR (see §7 below). | [LOCKED §2.7]; spec §2.9 | I+T | — |
| REQ-HUB-COMMON-045 | A module SHALL never fail to function when attached to the enterprise Hub; higher-tier module features degrade gracefully per §8 (see `module-conformance-matrix.md`). | [LOCKED §1/§8] | T | — |

## 6. Redundancy, availability ladder & fail-detected operation — DRAFT (D-ENT-6 RESOLVED 2026-07-02: one ENT line, SKU differentiators — redundancy pack standard on MC/MC-Max SKUs, orderable on base)

Audit finding 6: sellable redundancy is **fail-detected** redundancy — observable, alarmed,
self-testable — not implied end-to-end fault tolerance (the module chain stays single-path
by LOCKED design and is honestly declared as such).

| ID | Requirement | Trace | Verify | Gate |
|---|---|---|---|---|
| REQ-HUB-COMMON-050 | Every redundant element (power feed, uplink, CAN transceiver where fitted, watchdog, voting-pair member) SHALL be individually monitored; loss of redundancy SHALL raise an alarm within a bounded, debounced time even though service continues. | audit §1.6; survey 5 §3 | T | — |
| REQ-HUB-COMMON-051 | Failover paths SHALL be self-testable on operator command without taking the monitored machine down. | audit §1.6 | D | — |
| REQ-HUB-COMMON-052 | The Hub SHALL accept a power feed independent of the monitored PSU (the §2.9 third source, graduated from PROPOSED to binding at this tier) and SHALL ride through monitored-PSU loss while logging the event. | audit §1.6; spec §2.9; OQ-53..56 | T | — |
| REQ-HUB-COMMON-053 | Documentation SHALL state explicitly that the module sensing chain (RJ-45/CAN/DETECT) is single-path by platform design; no marketing/spec text may imply sensing-path fault tolerance. | audit §1.6 honesty framing | I | — |
| REQ-HUB-COMMON-054 | The Hub's CAN interface SHALL continuously expose bus state (error-active/error-passive/bus-off) and TEC/REC error counters as monitored, thresholdable objects; a transition to error-passive or bus-off SHALL raise a debounced alarm (northbound on NET, local surface on AIR) within a bounded, alerting-pipeline-dominated time. | survey 5 §1.3; spec §3.1 TWAI precedent | T | — |
| REQ-HUB-COMMON-055 | The Hub SHALL support an operator-invocable CAN self-test via controller internal loopback that never injects traffic onto the live shared module bus; documentation SHALL state it validates only the Hub-side half of the chain. | survey 5 §1.3 | D | — |
| REQ-HUB-COMMON-056 | The Phase-4 spec revision SHALL rewrite the tier-table phrase "redundant CAN" to name the actual mechanism (fail-detected monitoring + alarm + scoped self-test per REQ-HUB-COMMON-054/055) — real dual-bus CAN is foreclosed by the locked single-pair module link and SHALL NOT be implied. | survey 5 §1.1/§1.4; audit §1.6 | I | Phase-4 spec edit |
| REQ-HUB-COMMON-057 | On MC/MC-Max SKUs (and orderable on base ENT-NET), the Hub SHALL provide two independently-PHY'd Ethernet uplinks, each on one of the PolarFire's two hardened MSS MACs; default failover SHALL be switch-agnostic link-state active-standby, with 802.3ad/LACP active-active operator-selectable. | survey 5 §2.1; survey 2 (dual-port PHY headroom) | A+T | — |
| REQ-HUB-COMMON-058 | USB SHALL be documented as a heterogeneous local/enrichment channel and SHALL NOT count as a redundant peer toward the uplink loss-of-redundancy alarm (its functional path requires a live host OS/agent, contributing nothing to the host-down guarantee). | survey 5 §2.2; audit finding 5 | I | — |
| REQ-HUB-AIR-059 | ENT-AIR base builds SHALL exclude the NanoKVM module (the aux header MAY remain populated); documentation SHALL state that attaching a network-capable KVM or other egress-capable accessory is a customer decision outside the ENT-AIR zero-egress guarantee (owner ruling 2026-07-02). "Redundant uplink" on ENT-AIR SHALL be read as redundant LOCAL operator paths consistent with REQ-HUB-AIR-024. | survey 5 §2.3; owner ruling 2026-07-02 | I+D | — |
| REQ-HUB-COMMON-103 | MC-SKU Hubs SHALL carry an independent compute watchdog: separate silicon with its OWN OSCILLATOR and its own regulated supply rail — physically distinct from the main SoC's clock tree and local power sequencing, fed from the already-arbitrated §2.9 rail (not a new physical source) and itself PG-monitored — monitoring main-SoC liveness/health (challenge-response + health telemetry) with TWO-TIER escalation: soft reset first, then hard force to the safe STANDBY posture via the §2.9 eFuse commanded-disable lever after N consecutive missed challenges; every action logged to the tamper/event log + loss-of-compute alarm raised. The watchdog SHALL NOT sit in the sensing or northbound data path. Part-class = owner gate (survey 9 recommends S32K3-class non-lockstep [Zephyr-native]; Hercules TMS570/AURIX = precedented alternatives; optional TPS3813-class backstop watching the watchdog ~$1.5). | owner ruling 2026-07-02 (2nd); survey 9 §1; spec App B.3 | A+T | OQ-79 |
| REQ-HUB-COMMON-104 | The MC-Max SKU SHALL offer FAIL-FUNCTIONAL compute as an option: a voting pair of main SoCs (2oo2 + the independent watchdog as arbiter) with a DEFINED voted-output boundary — tamper-log writes and Appendix-D actuation triggers voted before commit; northbound and CAN service active/standby with continuous checkpointed state sync (inter-SoC PCIe/NTB link [MSS NTB support = firmware confirm] + a private 3-node CAN segment for heartbeat/arbitration; no shared boot flash or DDR between members). State sync SHALL be checkpointed, NOT lockstep (cycle-accurate lockstep across two discrete SoCs is unachievable and SHALL NOT be implied). Takeover: CAN acquisition session-continuous (both members always bus-listening); northbound sessions reconnect-tolerated (virtual-IP + fast reconnect); failover self-testable as a commanded, logged-as-drill exercise per REQ-HUB-COMMON-051. Firmware rollout SHALL be diversity-staged across the pair (N / N-1 canary) as a common-mode MITIGATION — documentation SHALL state that identical-firmware common-mode faults are not covered. Scope: Hub compute plane only — module sensing stays single-path per REQ-HUB-COMMON-053. | owner ruling 2026-07-02 (2nd); survey 9 §2 | A+T | OQ-79 |
| REQ-HUB-COMMON-106 | The module-facing 100BASE-T1 links SHALL provide fleet-wide TIME SYNCHRONIZATION to sub-microsecond accuracy (PTP/gPTP-class with hardware timestamping in the fabric data plane), so multi-module captures are correlatable at sub-µs; documentation SHALL state that sub-µs applies to SYNC, not message latency (frame time ~7 µs at 100 Mb/s — the nanosecond FREEZE path remains the OQ-60 hardware-trigger proposal, out of scope here). | owner ruling 2026-07-02 (3rd); spec App B.5 TSN leaning | T | OQ-20 |
| REQ-HUB-COMMON-107 | Storage SHALL be two-tier by role: (a) QSPI NOR (32 MB class) for A/B firmware slots + the rollback-resistant tamper/audit log (page-program-only persist path, endurance-managed separately from bulk data); (b) an eMMC 5.1 device (FBGA-153 land, MSS MMC controller) for the bulk telemetry store — ONE land, density populated per SKU (REQ-108/109). Bulk-store contents SHALL be encrypted at rest with keys held in the PolarFire root (the unit is stealable), and stored segments SHALL carry integrity metadata (signed segment chain) so exported data is tamper-evident. | owner ask 2026-07-02; survey 1 (MMC 5.1); REQ-070 | I+T | — |
| REQ-HUB-NET-108 | ENT-NET SHALL provision ≥8 GB eMMC as a store-and-forward buffer: full-rate summarized telemetry + event captures retained locally through northbound outages for ≥72 h (working math: 8 modules × ~2 kB/s summarized ≈ 1.4 GB/day → 72 h ≈ 4.2 GB; 8 GB ≈ 5+ days), oldest-first overwrite, flush-on-reconnect. | owner ask 2026-07-02 | A+T | — |
| REQ-HUB-AIR-109 | ENT-AIR SHALL provision ≥32 GB eMMC (64 GB factory option) as the LOCAL RETENTION store: ≥30 days of summarized fleet telemetry at the defined aggregate profile (working math: 8 modules × ~2 kB/s ≈ 1.4 GB/day → 30 d ≈ 41 GB at the high profile, ~21 GB at 1 kB/s — the retention window vs rate profile is a firmware-configurable trade the operator sets) + ≥1,000 §6.10 event pre-roll captures (~2 MB each ≈ 2 GB) + the tamper log; retention policy SHALL be oldest-first with protected event/tamper classes never auto-evicted; export via the local operator paths (USB / removable) with the REQ-107 integrity chain. If a CEC-KVM AIR variant (OQ-75) is attached, continuous video SHALL be stored on the KVM's own storage, never the Hub store — the Hub keeps event-triggered stills/clips only. | owner ask 2026-07-02; REQ-024 | A+T | — |
| REQ-HUB-COMMON-105 | The enterprise line SHALL be ONE product line with orthogonal SKU differentiators — posture (ENT-NET / ENT-AIR) × availability (base = fail-detected; MC = + independent watchdog + redundancy pack; MC-Max = + fail-functional voting pair) — and the fitted SKU SHALL be externally identifiable (labeling + BOM/population differences, incl. the watchdog part on the REQ-HUB-AIR-101-style inspection documentation). | owner ruling 2026-07-02 (2nd, resolves D-ENT-6); survey 9 §6 | I | — |

## 7. Power input & distribution — DRAFT

| ID | Requirement | Trace | Verify | Gate |
|---|---|---|---|---|
| REQ-HUB-COMMON-060 | The Hub SHALL implement the §2.9 three-source priority-OR (MAIN_5V primary > 5VSB > external feed) with a per-source eFuse-class monitor/protect front-end on each raw input providing hardware PG/FLT status, commanded-disable self-test (REQ-HUB-COMMON-051's lever), and reverse-current blocking. Working baseline: TPS25940-class fronts into the kept TPS2121 cascade (LTC4417 recorded as the owner-selectable single-chip alternative). Each raw source SHALL be individually sensed — the as-built combined PSU_5V sense point does not satisfy this. | spec §2.9; survey 4 (incl. the 5VSB_SENSE granularity gap); survey 1 (MAIN_5V primary) | I+T | OQ-53..56 (formal close at Phase-4) |
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

_Retired 2026-07-02: REQ-HUB-COMMON-090 (omnibus compliance row) — split into the per-regime
rows 094–099 below per survey 7; REQ-HUB-COMMON-091 narrowed to commercial lifecycle with the
security-support period moved to REQ-HUB-COMMON-102 (IDs never reused)._

| ID | Requirement | Trace | Verify | Gate |
|---|---|---|---|---|
| REQ-HUB-COMMON-091 | Commercial lifecycle commitments SHALL be declared at GA: ≥5-year availability, spares/RMA policy, ≥12-month EOL notice, warranty terms. | audit §2 (procurement blocker); survey 7 | I | D-ENT-3 (pricing) |
| REQ-HUB-COMMON-094 | If and when any CEC product is placed on the EU market, the platform SHALL meet the EU CRA: Art. 14 reporting/PSIRT from 2026-09-11 (retroactive to already-placed units), full Annex I essential requirements + CE technical file from 2027-12-11; the Annex III "network management systems" classification question (self-assessment vs notified body) SHALL be resolved via the delegated act or counsel BEFORE first EU placement, never by assumption. EU entry is deferred but kept open (owner ruling 2026-07-02); REQ-HUB-COMMON-014's SBOM discipline is maintained regardless so the entry path stays short. | survey 7 (primary-sourced dates); owner ruling 2026-07-02 | I | EU-entry |
| REQ-HUB-COMMON-095 | Each Hub hardware revision SHALL carry EMC emissions/immunity evidence (EN 55032/55035-class per target market) and IEC 62368-1 safety evidence before that revision's GA; industrial immunity uplift (EN 61000-6-2) SHALL be added only for a named customer environment. | survey 7 | T | — |
| REQ-HUB-COMMON-096 | The Hub SHALL be designed to the IEC 62443-4-2 SL-2 technical requirements (EDR component profile) as an internal target; formal ISASecure-class certification SHALL be pursued only on named-customer demand, and all claims SHALL use "designed to" wording absent a certificate on file. | survey 7 | A | — |
| REQ-HUB-COMMON-097 | The FIPS posture SHALL be "embeds a validated cryptographic module" (wolfCrypt-class; the exact validated build + tested/permitted-ported operating environment verified at ship time) — never an owned CMVP submission, and never "FIPS validated/certified/compliant" product-level claims. The library-vendor OE-extension engagement (no RISC-V on the current validated OE list) SHALL start at firmware kickoff if this posture is retained. | survey 6/7 (CAVP ≠ module validation) | I | — |
| REQ-HUB-COMMON-098 | ENT-AIR build-state evidence SHALL be the inspection/documentation pack per REQ-HUB-AIR-101 — no air-gap certification regime exists to cite (verified). | survey 7 | I | — |
| REQ-HUB-COMMON-099 | US federal-channel representations (NDAA §889/§5949, TAA, 800-171/CMMC posture) SHALL be prepared as conditional sales-enablement artifacts on demand; the §5949 SMIC/CXMT/YMTC exclusion SHALL be adopted now as a standing BOM-lint rule for government-bound builds. | survey 7 | I | — |
| REQ-HUB-COMMON-102 | The platform SHALL declare a per-product security-support period from the first enterprise release, set no shorter than the REQ-HUB-COMMON-091 commercial commitment (the CRA 5-year floor binds at EU entry per REQ-HUB-COMMON-094). | survey 7; owner ruling 2026-07-02 | I | — |
| REQ-HUB-COMMON-092 | BOM/pricing SHALL be value-based per the D-ENT-3 re-baseline (comparables $1.5k–3k/unit class), costing in the compliance/warranty/support tail — not parts-plus-margin. | audit §1.7 | A | D-ENT-3 |
| REQ-HUB-COMMON-093 | A named target-fleet statement (BMC-less ATX-architecture machines as the wedge) SHALL be ratified and carried in the spec revision, resolving the served-market contradiction (CRPS rack servers are out of scope unless a PDB module family is committed). | audit §1.8 | I | Phase-4 spec edit |

## 11. Mechanical & packaging — DRAFT

| ID | Requirement | Trace | Verify | Gate |
|---|---|---|---|---|
| REQ-HUB-COMMON-100 | The Hub SHALL retain the platform mounting scheme (M3 chassis-grounded) and SHALL offer the mezzanine integrated-stack option (Hub-on-24-pin) if D-ENT-5 adopts it for the enterprise form. | docs/mezzanine-stack-design-2026-06-24.md | I | D-ENT-5 |
| REQ-HUB-AIR-101 | ENT-AIR build state (no network PHY / fused-off posture, radio policy) SHALL be visually verifiable at inspection without powering the unit (labeling + population differences documented). | plan §1a.2/§1a.5 | I | D-ENT-5 |
