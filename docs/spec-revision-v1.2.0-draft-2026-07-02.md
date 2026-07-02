# Spec revision draft — v1.1.0 → v1.2.0 (the enterprise line)

_Status: DRAFT FOR THE OWNER'S PEN (2026-07-02). Per the repo rule the spec is ground truth
and agents never amend it sideways — this document contains the complete, surgical edit set
for the owner to apply (or approve as a PR). Sources: the owner directions of 2026-07-01/02
(plan §1a + the resolve-all rulings), the requirement registers
(`docs/enterprise-requirements/`, 100 REQs, lint-green), the customer/integration audit, the
tamper-module research, and Phase-2 surveys 1–8. Decision boxes marked **[OWNER]** are the
only unresolved choices; everything else is a recording of rulings already made._

**Semver rationale (1.2.0, MINOR):** adds the enterprise-line section, closes OQ-7 and the
enterprise half of OQ-14, revises the §1 summary rows for the enterprise tiers, and amends
the tier-agnostic phrasing to distinguish interface-compatibility (unchanged, LOCKED) from
build variants (new). No LOCKED electrical decision is altered: the module link, pin table,
CAN 500k, DETECT, shunt values, connector locks all stand.

---

## EDIT 1 — Document control

Set `| Version | 1.2.0 |`, date of application, and append to the §11.1 revision log:

> **v1.2.0 (2026-07-0X, controlled).** THE ENTERPRISE LINE. Resolves OQ-7 (owner direction
> 2026-07-01/02): the enterprise tiers are specified now, as two deployment-posture variants
> — **ENT-NET (networked-but-hardened)** and **ENT-AIR (air-gapped)** — on a PolarFire SoC
> hub (S-suffix, Athena; MPFS095TS/FCVG484 working baseline). New Section 13. §1 tier table
> rewritten; enterprise uplink revised to standard IEEE 802.3 1000BASE-T (1000BASE-T1
> demoted to factory option); RJ-11 redefined from "trust channel" to a supervised
> physical-security I/O port; "redundant CAN" honesty-rewritten to fail-detected monitoring;
> enterprise module BUILD variants introduced (radio-free MCUs on ENT-AIR) without altering
> interface tier-agnosticism; enterprise half of OQ-14 closed (uplink protection topology);
> OQ-53..56 closed for the enterprise tier; OQ-75..78 opened. Requirements of record:
> `docs/enterprise-requirements/` registers.

## EDIT 2 — §1 tier table (REPLACE the four-row table)

Replace the current table (rows Standard/Pro/Enterprise/Mission Critical) with:

> | Tier | Role | Hub MCU | Host link | Distinguishing hardware |
> |---|---|---|---|---|
> | Standard | Mainstream builders | ESP32-S3 | USB Full Speed | CAN only, 4 ports |
> | Pro | Overclockers, bench users | ESP32-P4 | USB High Speed | plus RS-485 streaming, 8 ports |
> | Enterprise — ENT-NET (networked, hardened) | Regulated / financial / monitored fleets | PolarFire SoC (S-grade, Athena; MPFS095TS baseline) | Standard IEEE 802.3 1000BASE-T uplink (primary management plane) + USB (sensing/provisioning) | Hardened RTOS control plane (no Linux), PUF-rooted identity + secure boot, northbound Redfish-subset/OpenMetrics/syslog-TLS, RJ-11 security-I/O port, fail-detected redundancy pack (option) |
> | Enterprise — ENT-AIR (air-gapped) | Defense-adjacent, tamper-mandated, zero-egress sites | PolarFire SoC (S-grade, same base design) | Local operator paths only (USB + console/removable export); **zero network egress by design** | No network PHY populated (inspection-verifiable), radio-free module builds, RJ-11 security-I/O port (populated), tamper log custody, fail-detected redundancy pack (standard fit) |
>
> **[OWNER — D-ENT-6]** Label mapping onto the legacy tier-3/tier-4 names: RECOMMENDED —
> tier 3 "Enterprise" = ENT-NET; tier 4 "Mission Critical" = ENT-AIR **with the redundancy
> pack standard-fit** (and orderable as an option on ENT-NET, per the Phase-2 finding that
> the pack is a discrete scope knob). Alternative: keep "Mission Critical" as a separate
> future super-tier and rename rows 3/4 to the variant names outright. Pick one; the table
> above is written for the RECOMMENDED mapping.

## EDIT 3 — §1 tier-agnostic sentence (REPLACE)

Replace: "Modules are tier-agnostic: any module works in any Hub and degrades gracefully
(see Section 8)." with:

> Module **interfaces** are tier-agnostic and this is unchanged and LOCKED: any module works
> in any Hub over the universal RJ-45/CAN/DETECT interface and degrades gracefully (Section
> 8). v1.2.0 adds enterprise **build variants** of the module families (Section 13.6):
> same family, same interface, same graceful degrade — different build posture (radio-free
> MCU, per-unit identity, provenance-grade BOM). A build variant never changes what the
> Hub-facing interface promises.

## EDIT 4 — NEW Section 13: The enterprise line (INSERT as a new top-level section)

> ## 13. The enterprise line (ENT-NET / ENT-AIR) — v1.2.0
>
> Requirements of record: `docs/enterprise-requirements/` (register set, 100 requirements,
> DRAFT→RATIFIED lifecycle). This section states the architecture and the locked direction;
> the registers carry the testable detail. Owner rulings 2026-07-01/02 are the authority.
>
> **13.1 Compute and identity.** One PolarFire SoC base design serves both variants:
> S-suffix part (Athena coprocessor required), MPFS095TS in FCVG484 as the working baseline
> with the pin-compatible 025T/160T ladder as cost/headroom options (survey 1). No Linux:
> Zephyr-class RTOS control plane on the hard RISC-V complex, fabric reserved for the data
> plane (Appendix B.3/B.5 leaning, now adopted). Two-tier boot: the PolarFire System
> Controller + HSS chain for high-ceremony image changes, an A/B verified-update layer
> (MCUboot/wolfBoot-class) for routine firmware with anti-rollback. Per-device
> cryptographic identity (802.1AR-class IDevID) rooted in the PUF key store; the factory
> MAC + database scheme (§4) is insufficient at this tier. FIPS posture is
> embeds-a-validated-module (wolfCrypt-class), never an owned CMVP submission, and product
> claims never say "FIPS validated" (survey 6/7).
>
> **13.2 Host links and northbound surface.** ENT-NET's primary management plane is a
> standard IEEE 802.3 1000BASE-T uplink (SGMII PHY off the hardened MAC; VSC8662-class
> working baseline; integrated shielded magnetics ≥2× the 802.3 isolation floor; protection
> per §2.4-ENT below). 1000BASE-T1 (automotive SPE) is demoted to a factory option — it is
> not terminable on enterprise switching (audit finding 2). USB remains on both variants:
> sensing/provisioning on ENT-NET, a primary local path on ENT-AIR. Northbound (ENT-NET):
> Redfish-aligned REST subset + OpenMetrics + syslog-TLS; SNMPv3 deferred past GA or
> commercial-stack licensed (survey 6). ENT-AIR: zero network egress by design — no network
> PHY populated, build state inspection-verifiable without powering the unit; the same
> operational surface is served locally. Host-down operation is a verified test case in the
> STANDBY power posture (13.4).
>
> **13.3 The RJ-11 security-I/O port (renames the "trust channel").** A supervised
> physical-security I/O port: EOL-resistor-supervised tamper-loop input + galvanically
> isolated dry-contact alarm output to facility security, riding the always-on power domain
> and the rollback-resistant tamper log. Deliberately protocol-free — no parser, no path to
> CAN/DETECT. Populated by default on ENT-AIR, on request on ENT-NET. Identity/attestation
> lives on the PolarFire root, not this jack. The OQ-60 per-port Max sideband proposal no
> longer owns or shares this port's name (owner 2026-07-02); if adopted it renames.
>
> **13.4 Power.** The enterprise hub CANNOT run full compute on the shared 5VSB budget
> (survey 1). Two defined postures: **FULL** (MAIN_5V primary — complete compute + data
> plane) and **STANDBY** (5VSB and/or independent feed — telemetry acquisition, event
> logging, tamper capture, persist-on-fault guaranteed; northbound best-effort). The §2.9
> three-source priority-OR graduates from PROPOSED to binding at this tier, with a
> per-source eFuse-class monitor/protect front-end (TPS25940-class working baseline; PG/FLT
> hardware status per raw source, commanded-disable self-test, reverse blocking) feeding
> the priority cascade; a rear-bracket external power-in is mandatory (forensic/independent
> feed — closes OQ-54 for this tier).
>
> **13.5 Redundancy — fail-detected, stated honestly.** The module sensing chain is
> single-path by LOCKED platform design and is documented as such; no text may imply
> sensing-path fault tolerance. "Redundant CAN" means Hub-side fail-DETECTED monitoring:
> continuous bus-state + error-counter exposure, debounced alarms on error-passive/bus-off,
> explicit logged recovery, and loopback self-test scoped to the Hub's own half (real
> dual-bus CAN is foreclosed by the single-pair module link; the 125 kbps fault-tolerant
> transceiver class is below the LOCKED 500k floor — survey 5). "Redundant uplinks" means
> two independently-PHY'd Ethernet ports on the two hardened MACs, link-state
> active-standby default, LACP opt-in; USB is a heterogeneous local channel and never
> counts toward the loss-of-redundancy alarm. On ENT-AIR, redundancy means redundant LOCAL
> operator paths. The redundancy pack is a discrete option assignable per the EDIT-2
> mapping.
>
> **13.6 Enterprise module build variants.** Per module family (24-pin, EPS, PCIe,
> 12VHPWR), an enterprise build: fail-passive-in-the-power-path FMEA + fault-injection
> evidence (the first MC-buyer question), per-unit verifiable identity (mechanism = OQ-76),
> §6.10 pre-roll retained as a forensic feature, sensing at the Pro tier per §6.13, and on
> ENT-AIR a **radio-free MCU** — STM32G4-class working baseline (G431 digital families,
> G474 for 12VHPWR-Std), ESP32-P4 for Pro-tier builds (radio-free, already the platform Pro
> MCU). The fused-off-ESP32 posture is rejected on evidence: no Wi-Fi-disable eFuse exists
> on S3/C6, no radio-absent SKU exists, and it fails inspection-without-powering (survey
> 8). Radio-free builds are externally verifiable unpowered (part marking + BOM + no
> antenna keepout).
>
> **13.7 The NanoKVM boundary and the CEC-KVM direction.** The NanoKVM is an optional
> accessory, excluded from ENT-AIR base builds; a customer attaching a network-capable KVM
> steps outside the zero-egress guarantee by their own choice (owner 2026-07-02). The Hub
> treats any KVM — including a future CEC one — as an untrusted peripheral (the v3.7
> ratiometric stance, kept as defense in depth). A CEC-built, network-hardened KVM module
> following the NanoKVM trajectory (COTS encoder SoC on a CEC carrier, CEC-signed minimal
> image, TLS-only, no third-party cloud, own SBOM/PSIRT; an ENT-AIR variant with no network
> populated restoring the visual vantage without egress) is PROPOSED as OQ-75.
>
> **13.8 Compliance posture.** EU market entry is deferred but kept open (owner
> 2026-07-02): CRA obligations bind at first EU placement (reporting machinery per Art. 14
> — retroactive to placed units; full requirements per Art. 71; the Annex III
> "network management systems" classification is resolved via delegated act or counsel
> BEFORE first placement, never by assumption). Regardless of market: SBOM per release from
> the first enterprise release, PSIRT/CVD + declared security-support period before
> enterprise GA, EMC/safety evidence per hardware revision, IEC 62443-4-2 SL-2 (EDR) as an
> internal design target with "designed-to" claim wording, US federal-channel
> representations prepared on demand with the NDAA §5949 BOM exclusion adopted as a
> standing rule. Modules are separately-marketed components carrying their own SBOM/PSIRT
> coverage.

## EDIT 5 — §2.4 / OQ-14 enterprise closure (APPEND to §2.4)

> **Enterprise uplink protection (v1.2.0, closes the OQ-14 enterprise half).** The
> protection lands on the ENT-NET 1000BASE-T uplink, not the module RJ-45s (which inherit
> the consumer answer unchanged): magnetics galvanic isolation ≥2× the IEEE 802.3 1500 Vrms
> floor as the primary defense (survives compliant PSEs by absent-PD-signature and passive
> PoE injection by construction; Bob-Smith blocking caps rated ≥200 V), a low-capacitance
> TVS array on the PHY side of the magnetics (IEC 61000-4-2 ±8 kV contact class), and a
> 3-electrode GDT on the shield-to-chassis path sized to IEC 61000-4-5 Level 2 —
> office/rack grade by declared target fleet, NOT building-entrance grade (outdoor-plant
> deployments use an external in-line SPD accessory, documented, never a board respin).
> The uplink jack is visually distinct from module ports (bezel color + silkscreen +
> board-edge grouping); module ports stay locking-boot per §2.1.

## EDIT 6 — §3.1 (APPEND one paragraph)

> **Enterprise redundancy honesty (v1.2.0).** See §13.5: "redundant CAN" at any tier means
> Hub-side fail-detected monitoring of the one shared bus, never a second CAN medium — the
> locked single-pair module link forecloses dual-bus, and this document does not imply
> otherwise.

## EDIT 7 — §2.9 (APPEND one paragraph)

> **Enterprise graduation (v1.2.0).** On the enterprise line §2.9 is binding, not
> PROPOSED: MAIN_5V is the primary source (PolarFire-class load exceeds the 5VSB budget —
> the FULL/STANDBY posture split of §13.4), each raw source carries an eFuse-class
> monitor/protect front-end (per-source PG/FLT, commanded self-test, reverse blocking), and
> the rear-bracket external feed is mandatory. Consumer/Pro hubs are unchanged.

## EDIT 8 — OQ closures (§10 edits)

- **OQ-7** → mark RESOLVED (v1.2.0): "Resolved by owner direction 2026-07-01/02: the
  enterprise line is specified now as the ENT-NET/ENT-AIR variants on PolarFire (Section
  13); requirements of record in `docs/enterprise-requirements/`."
- **OQ-14** → update the Enterprise/MC sentence: enterprise half RESOLVED per §2.4's
  v1.2.0 protection topology on the 1000BASE-T uplink.
- **OQ-53..56** → mark "RESOLVED for the enterprise tier (v1.2.0, §13.4): eFuse-fronted
  priority cascade (OQ-55), mandatory rear-bracket feed (OQ-54), page-program-only
  persist-on-fault firmware commitment + modest hold-up upsize with supercap escalation
  gated on the OQ-56 bench item (OQ-56); module-rail scope (OQ-53) unchanged/deferred."
  Consumer-tier halves stay as-is.
- **OQ-60** → append: "(v1.2.0) The RJ-11 name and the one-per-Hub security-I/O function
  are resolved to §13.3; the Max per-port sideband connector, if adopted, is a DISTINCT
  connector and renames — the open calls (a)–(c) stand."

## EDIT 9 — New OQs (APPEND to §10)

> **OQ-75: CEC-KVM (hardened out-of-band console module).** Adopt/decline a CEC-built KVM
> module per §13.7 (COTS encoder SoC + CEC carrier + CEC-signed minimal image; ENT-AIR
> no-network variant). Open: SoC/SoM selection (RK3588-class secure-boot capable vs
> SG2002-class cost floor), carrier form (PCIe bracket vs bracketless), the standing
> Linux-image PSIRT cost, and whether Step-1 (CEC carrier + hardened image on COTS core)
> ships before the full SKU.
> **OQ-76: Enterprise module per-unit identity mechanism.** The §2.3 1-Wire ID/EEPROM
> upgrade path vs a CAN-based challenge/response against a module-resident secret vs
> DETECT-class-only + Hub census. Feeds REQ-MOD-COMMON-010/011.
> **OQ-77: Mezzanine integrated-stack option.** Formalize the Hub-on-24-pin mezzanine
> (docs/mezzanine-stack-design-2026-06-24.md) as an orderable form, incl. its enterprise
> fit; RJ-45 remains the default cabled PHY.
> **OQ-78: Tamper/physical-security module family.** Adopt/decline the plan §3a candidates
> (chassis-intrusion + rollback-resistant tamper-log module; ATR whole-chassis RF sensing —
> note the ATR-vs-ENT-AIR emission tension, an intentional emitter in a radio-free build;
> device inventory/attestation; power-fingerprint screening tier; environmental sensing
> folded into the intrusion module). The RJ-11 loop input (§13.3) is the Hub-side
> attachment point for the intrusion module's external half.

## EDIT 10 — Mechanical follow-ups at application time

§12 index rows for: ENT-NET/ENT-AIR, PolarFire SoC (extend), 1000BASE-T, RJ-11
security-I/O, radio-free MCU, STM32G4, fail-detected redundancy, CEC-KVM, OQ-75..78.
Tier-applicability lists gain Section 13. After the spec lands: update CLAUDE.md's summary
+ tier table, both hub READMEs (placeholder text → §13 pointer + register links), flip the
registers' "Phase-4 spec edit" gates, and re-run `cec_req_lint`/`cec_corpus_lint` (spec-ref
resolution) in the same change.

---

**Decision boxes for the owner, consolidated:** (1) EDIT 2 [D-ENT-6] tier-label mapping —
recommended: ENT-NET=tier 3 Enterprise, ENT-AIR=tier 4 Mission Critical with the redundancy
pack standard-fit on 4 / optional on 3. (2) OQ-75 CEC-KVM adopt + which step first.
(3) Apply as: owner edits the spec directly, or approves a PR containing exactly these
edits (either is "the owner's pen" under CODEOWNERS).
