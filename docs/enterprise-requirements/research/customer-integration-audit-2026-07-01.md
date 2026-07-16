# Enterprise + Mission Critical customer & integration audit — 2026-07-01

*Synthesis of eight verified audit lenses — dcim-ops, oob-mgmt, security-compliance, fleet-provisioning, mission-critical-verticals, procurement-lifecycle, oem-integrator, competitive-landscape. Each lens's skeptic drops/revisions have been applied: stale-against-plan-of-record recommendations demoted, duplicates merged, over-scoped severities re-tiered. Requirement tags follow the plan's `REQ-<UNIT>-<VARIANT>-###` schema with VARIANT ∈ {AIR, NET, COMMON}; the ENT-AIR/ENT-NET ↔ tier-3/tier-4 mapping is itself open (D-ENT-6), so variant tags supersede tier labels wherever the two conflict.*

---

## 1. Executive summary

Enterprise buyers do not buy monitoring hardware on the MCU inside it. They buy on the **operational surface wrapped around it** — can my existing tooling ingest it, can my security review pass it, can I deploy and support 500 of them, and can you prove the numbers. Across all eight lenses the same verdict recurs: **CEC's Enterprise/MC tiers today specify hardware nouns (secure element, optional 1000BASE-T1, RJ-11 trust channel, "redundant everything") and almost none of the software/lifecycle/evidence surface that enterprise procurement actually gates on.** The platform's *bones* are genuinely differentiated — 5VSB-powered host-independent operation is true out-of-band monitoring; INA228/REF-corrected accuracy can beat the ±1% billing-grade PDU benchmark; per-pin 12VHPWR transient forensics is data no BMC or PDU can see — but none of it is packaged as the table-stakes ops surface.

The 5–8 findings that most change the tier definitions:

1. **There is no northbound management/data model anywhere in either tier** (zero Redfish/SNMP/REST/syslog/MIB in the spec). As defined, the Enterprise Hub is a Pro Hub plus a secure element and cannot be onboarded by any DCIM, NMS, observability, or SIEM platform. *(dcim-ops, oob-mgmt, oem-integrator, fleet-provisioning, competitive-landscape — blocker for ENT-NET.)*

2. **The named uplink PHY is wrong for the market.** 1000BASE-T1 is automotive/industrial single-pair Ethernet (15 m standard, 40 m optional [unverified]); no enterprise access switch terminates it, so every networked deployment needs a media converter per node. The buyer expects standard 1000BASE-T RJ-45 (with the deferred OQ-14 over-voltage answer landing on that port) or SFP. *(All lenses — reframe Phase-2 research item 2 from "T1 PHY survey" to "standard-T-first, T1 optional".)*

3. **Security is a platform-wide legal floor, not a tier-3 differentiator.** The EU CRA makes secure-boot/signed-OTA, SBOM, PSIRT/CVD, and a declared support period mandatory for EU sale (reporting obligations 2026-09-11, full essential requirements 2027-12-11 [unverified — verify against OJ text]). This binds *every* tier including Standard; only mechanism *strength* (SE/PolarFire-rooted IDevID, measured-boot attestation, anti-tamper, 62443 SL-2) tiers up. The biggest blockers here are **process, not silicon**: no PSIRT, no signed-firmware requirement, no key-custody story for either firmware or Appendix-D plan signing (OQ-62). *(security-compliance, fleet, procurement, mc-verticals.)*

4. **A fail-passive guarantee is the first question for an in-power-path interposer and it is unanswered.** CEC modules sit in series with a 40–55 A DC path; every MC buyer asks "can your monitor take down my machine?" before anything else. No FMEA/FMEDA + fault-injection requirement exists. *(mission-critical-verticals — blocker.)*

5. **USB-primary contradicts both the agentless fleet-management norm and CEC's own host-independent value proposition** — telemetry that dies with the host throws away the platform's best OOB asset. On ENT-NET the network path must be the primary management plane (USB demoted to sensing/provisioning). **But this is variant-conditional:** ENT-AIR is "no network egress by design," where the local/USB/out-of-band path *is* the product. *(dcim, oob, oem, competitive, mc — split the recommendation by variant.)*

6. **"Redundant power/CAN/uplinks" is meaningless to an ops team until it is observable.** With modules LOCKED to a single RJ-45/CAN/DETECT chain, the sensing path stays a single point of failure — so the honest, sellable framing is **fail-detected redundancy** (every redundant element monitored, loss-of-redundancy alarmed, failover self-testable), not implied end-to-end fault tolerance. MC "redundant power" must also include a feed independent of the monitored PSU (the §2.9 three-source priority-OR, graduated to a binding requirement). *(dcim, oob, mc, oem, competitive, procurement.)*

7. **The tier definitions are bare-BOM rows; the $50/$80 targets never survived enterprise economics.** Owner direction has already re-baselined them to TBD (D-ENT-3) and resolved compute to PolarFire (D-ENT-2). This audit reinforces that the re-baseline must be **value-priced against comparables** ($1.5k–3k/unit metered PDUs and OOB appliances, ~$60–120/monitored point [unverified]) with the **compliance/certification/warranty/5-year-support tail** costed in — not parts-shaped. *(procurement, competitive, dcim, oob, fleet.)*

8. **A named target-fleet statement is required to resolve a live served-market contradiction.** The honest wedge is **BMC-less ATX-harness fleets** (GPU workstations, render farms, broadcast machines, trading-desk workstations, industrial PCs) whose PSUs expose nothing standard — *not* CRPS/12VO/busbar rack servers whose BMCs already export PMBus→Redfish PowerSubsystem data. The MC row's own named verticals (defense/broadcast/render) skew toward CRPS servers CEC physically cannot interpose, so either the roadmap commits a CRPS/PDB module family or the tier explicitly targets ATX-architecture machines. *(dcim, mc, oob, competitive.)*

---

## 2. Consolidated gap register

Deduped across lenses, most severe first. Severities re-tiered per skeptic verdicts (e.g. the CRA/PSIRT process gap is de-urgented from date-triggered blocker to "hard prerequisite of EU go-to-market"; the T1 uplink is scoped to ENT-NET; known-open items already scheduled in the plan are marked accordingly).

### Enterprise (ENT-NET unless noted; ENT-AIR carries the offline dual of each network item)

| Gap | Severity | Lens(es) | Implied requirement |
|---|---|---|---|
| No northbound management/data model at all (no Redfish/SNMP/REST/MIB/syslog); only network mention is an "optional" uplink | **Blocker** (ENT-NET) | dcim, oob, oem, fleet, competitive | Redfish service + SNMPv3 agent + published MIB + OpenMetrics endpoint + syslog(TLS); §6 register must add a "northbound management interface" + "fleet integration" slot (currently absent) |
| Uplink PHY is 1000BASE-T1 (automotive SPE), unusable on enterprise switching without per-node media converters | **Blocker** (ENT-NET) | all | Standard IEEE 802.3 1000BASE-T RJ-45 (magnetics + OQ-14 OV protection) or SFP; T1 at most a factory option/internal link |
| No security baseline: no signed-boot/OTA requirement, no TLS/cert enrollment, no RBAC, no audit log, no SBOM/PSIRT/CVD; "secure element" has no specified job | **Blocker** (process; binds all tiers for EU sale) | security, fleet, procurement, mc | Secure-boot chain, signed OTA + offline signed bundle, IDevID in PolarFire root-of-trust, EST/SCEP LDevID enrollment, SBOM per release, PSIRT/CVD, declared support period |
| No product lifecycle/EOL/warranty/spares/FRU policy for a tier literally named critical | **Blocker** | procurement | ≥5 yr availability, ≥5 yr spares/RMA post-EOS, ≥12 mo EOL notice, FRU catalog, warranty ≥3 yr (5 for MC) |
| USB-primary host link vs agentless OOB norm; telemetry dies with host; USB device-control review friction | **Blocker** (ENT-NET) | dcim, oob, oem, competitive, fleet | Network path primary for management on ENT-NET; host-down operation a verified test case; agent optional/enrichment only |
| No fleet provisioning/identity: no ZTP, no factory IDevID, no bulk config, no fleet firmware campaign, no CMDB export | **Blocker→Major** | fleet, dcim, oob, competitive | Factory 802.1AR IDevID (PolarFire-anchored), EST/BRSKI enrollment, DHCP/ZTP claim, staged-rollout OTA, machine-readable inventory export |
| No declared accuracy class / per-unit calibration / traceability / recalibration statement | Major | dcim, oob, mc, competitive, procurement | Publish system accuracy class (≤±1%, ≤±0.5% ref-corrected); per-unit factory calibration stored in module flash (route via per-family module registers, D-ENT-4); **no IEC 62053 conformance claim** (AC revenue-metering regime, wrong class) |
| No ops-facing alarm model (thresholds, hysteresis, assertion/deassertion, trap/syslog delivery); only internal ALERT/FREEZE capture triggers exist | Major | dcim, oob | Per-channel warning/critical thresholds + hysteresis; assertion/deassertion events on trap + syslog + API |
| No machine-level cumulative energy (kWh); accumulators exist only on 24-pin, explicitly partial (OQ-13) | Major | dcim | Total-system kWh aggregated across populated modules, power-cycle persistent, audited reset (PROPOSED resolution of OQ-13, owner-gated) |
| No time-sync/log-export requirement; Appendix-B PTP/timestamping is exploration, not a tier requirement | Major | all | NTP client + UTC event stamps + sync-status; PTP option for broadcast; syslog RFC 5424 (TLS) |
| No BMC/Redfish coexistence positioning ("my iDRAC already shows PSU watts"); no scope of the served fleet vs CRPS/12VO physical non-fit | Major | dcim, oob, oem, competitive | Document per-rail DC-side granularity as complementary to PMBus/PowerSupplyMetrics; register as Redfish AggregationSource; name the BMC-less served fleet |
| Appendix-D pipeline is consumer-shaped ($25 ticket, end-user consent, cloud swarm); no enterprise profile (ITSM/org consent, on-prem swarm, signed agent, anti-replay/expiry/machine-binding, SIEM export) | Major | security, oob, dcim, fleet, oem, mc | Enterprise deployment profile; org/policy consent + change-window scheduling; Authenticode-signed user-mode agent; plan signature verified against pinned key with nonce/expiry/target-binding; all stages exported to SIEM |
| No mechanical/mounting spec (bracket/tray/standoff, heights, clearances) and no cable-management program for the multi-RJ-45 + interposer fan-out (OQ-4) | Major | oem | Mounting-kit SKUs; fixed-length low-profile Cat5e/6 SKUs + routing/airflow guidance for tower/2U(target)/1U(stretch) |
| No in-chassis environmental envelope (ambient/airflow/vibration) or EMC class | Major | oem, mc | 0–55 °C local ambient + min-airflow/derating; EMC Class A min (Class B goal) |
| Weak module identity (DETECT + factory MAC, "weak anchor" per OQ-44); no offline-verifiable per-unit serial label, no anti-counterfeit anchor | Major | all | Label serial bound to MAC in manufacturing (CMDB/warranty); D-ENT-5 owner gate on §2.3 1-Wire/EEPROM adopt vs formally-declined-with-residual-risk |
| No white-label/ODM program (OEM VID/PID, branding, PCN, lifecycle/supply commitments); no internal USB-header attach option | Minor | oem, procurement | ODM program definition; internal USB 2.0 header cable option for chassis-closed installs |
| RJ-11 "trust channel" undefined (no protocol/threat model/consumer); no ecosystem counterpart; mis-plug hazard into telco lines | Minor (known-open) | all | Redefine trust as SE/PolarFire cryptographic (per OQ-60 migration); keep connector only per OQ-60 power/FREEZE with mismate protection, or cut. Phase-2 item 3 must be allowed to conclude "cut" |
| Country-of-origin/TAA/889 posture undocumented; module MCUs are Espressif (Chinese vendor), NanoKVM is Sipeed (Chinese) | Minor (Major for gov/ENT-AIR) | procurement, competitive | Per-SKU COO register + substantial-transformation analysis; Espressif not 889-covered (commercial OK); NanoKVM optional/excludable from gov configs. **Note: ESP32 dies are TSMC-Taiwan-fabbed — TAA outcome undetermined, not presumed disqualifying** [unverified — trade counsel] |

### Mission Critical (register-mapping to ENT-AIR/tier-4 pending D-ENT-6)

| Gap | Severity | Lens(es) | Implied requirement |
|---|---|---|---|
| No fail-passive/FMEA requirement for an interposer in series with a 40–55 A host power path | **Blocker** | mc | FMEA/FMEDA (open/short/overtemp of every in-path element) + physical fault-injection per module family; report is a customer deliverable |
| "Redundant power/CAN/uplinks/trust" has no specifying body: no failover semantics, no monitored/alarmed loss-of-redundancy, no degrade ladder — and the LOCKED single-RJ-45/CAN module chain keeps the sensing path a SPOF | **Blocker** | mc, dcim, oob, oem, competitive, procurement | Reframe as **fail-detected redundancy**: each redundant element individually sensed, loss alarmed ≤1–5 s on all channels, failover exercisable by BIST. (Confirms plan Phase-2 item 5; adds the observability requirement) |
| Module radio silicon (ESP32-S3/C6) vs defense/air-gap RF prohibition — "unused radio" is not an accepted answer | **Blocker** (ENT-AIR/defense) | mc, procurement, competitive, fleet | ENT-AIR carries no operable RF transmitter; module radio-free-MCU variant vs verifiable disable posture is an owner gate (plan §1a.5 / D-ENT-5) decided with customer-acceptable evidence |
| MC "redundant power" shares its source with the monitored PSU (§2.7 LOCKED 5VSB feed); §2.9 third source is PROPOSED, not bound | Major | oem, mc | Bind §2.9 three-source priority-OR (LTC4417-class) as MC requirement with specified ride-through + persist-on-fault flush |
| No reliability deliverables: no MTBF/FIT (Telcordia SR-332 / MIL-HDBK-217 [unverified as bid table-stakes]), no derating report, no ESS/burn-in | Major | mc, procurement | SR-332 MTBF prediction + derating analysis per SKU as standard evidence pack |
| No FIPS/62443 scoping (validated-crypto strategy, 62443-4-1 SDL, target 62443-4-2 SL) | Major | security, mc | Target 62443-4-2 SL-2 as design checklist; FIPS via validated library (wolfCrypt) or certified SE/TPM — **never own CMVP run** (12–18 mo queue [unverified]) |
| Component-level safety evidence absent for a high-current in-path device | Minor (revised from Major) | mc | UL94 V-0 power-path plastics, UL-recognized critical components, published connector current margins, abnormal-fault test data for the integrator's safety file — **not** an end-product 62368-1 listing (wrong class: modules are SELV DC accessories) |
| MC "trust" unsubstantiable end-to-end: no per-module cryptographic identity; telemetry cannot be attributed | Major | mc, security, fleet | D-ENT-5 adopt 1-Wire/EEPROM or CAN challenge-response (module MCUs have eFuse HMAC/ECDSA — no new HW), OR document "trust terminates at the Hub, module data Hub-attested only." **Note OQ-60's proposed second CAN-FD trust path collides with the LOCKED classical-CAN-500k floor — flag as OQ-7 spec-revision item** |
| Maintenance/MTTR model undocumented: in-path modules never hot-swap (powered-down window); Hub swappable live via §2.9 | Minor | mc, procurement | State MTTR + spares/bridging-cable strategy in datasheet |
| Mezzanine integrated appliance (Hub + 24-pin) exists only as draft/OQ; strongest OEM SKU but not a named product form | Minor | oem, fleet | IF D-ENT-5 adopts mezzanine participation, enterprise Hub rev SHALL retain the socket contract (connector ref + mount frame per 2026-06-24 design); FRU model must still decompose into separately orderable Hub + 24-pin |

*Out of scope note:* the medical vertical was introduced by one lens, not by the spec tier table (which names "Regulated/financial" and "Defense, broadcast, render"). Recommend an explicit "medical (IEC 60601-1) out of scope, or offered as a priced component-evidence pack" one-liner rather than a gap.

---

## 3. Integration surface map

Concrete protocols/ecosystems CEC must speak, grouped by plane. Network-plane items are **ENT-NET-conditional**; ENT-AIR carries the offline dual (local API + export-to-media + local time source) of each.

### 3.1 Telemetry ingestion

| Ecosystem | Protocol | What to implement |
|---|---|---|
| DCIM (Sunbird Power IQ/dcTrack, Nlyte, EcoStruxure IT, Device42) | SNMPv3 (authPriv) poll + traps; vendor device-definition/dynamic-plugin files | Published CEC enterprise MIB: per-rail V/I/P, kWh, temps/ΔT, per-pin imbalance, module inventory, alarm/failover state; supply Power IQ dynamic-plugin + EcoStruxure device-definition + Device42 discovery artifacts [unverified — confirm each vendor's onboarding-artifact mechanics before making them release criteria] *(dcim, oob)* |
| Observability (Prometheus/Grafana, VictoriaMetrics, OpenTelemetry, Datadog/Splunk O11y) | OpenMetrics `/metrics` (served on uplink or host exporter); OTLP | Stable, semver'd metric names/labels per unit + per module; OTel resource attributes (device ID, site, config class). Render-farm/trading fleets are more often Prometheus- than DCIM-monitored — high-adoption path for the actual served market *(dcim, oob, fleet, oem)* |
| Redfish ecosystem (BMC-adjacent tooling, PRTG-class NMS, DGX/Supermicro fleet mgrs) | Redfish DSP0266 over HTTPS (Sensor/PowerSubsystem/TelemetryService/EventService; OEM namespace for per-pin + transient-capture retrieval) | Native Redfish service on ENT-NET Hub (host-agent mapping acceptable at first release); pass DMTF Redfish-Service-Validator; registrable as AggregationSource. **DSP2056 (Redfish for Power Distribution Equipment) is the pattern to borrow, not an in-scope product class** *(dcim, oob, competitive)* |

### 3.2 Management plane

| Ecosystem | Protocol | What to implement |
|---|---|---|
| Enterprise network access control | 802.1X EAP-TLS using SE/PolarFire-held IDevID; DHCP/static, VLAN, proxy | Supplicant in Hub firmware; any populated Ethernet uplink must authenticate onto locked-down segments *(dcim, oob, security, fleet)* |
| Customer PKI | 802.1AR IDevID + EST (RFC 7030); BRSKI (RFC 8995) optional for ZTP | Factory-provisioned non-exportable keypair; operator LDevID enrollment/rotation/revocation; published manufacturing CA chain *(fleet, security)* |
| Fleet OTA | hawkBit DDI / Mender-class over HTTPS; MCUboot-verified signed images | Hub A/B or verified-rollback OTA client + campaign/staged-rollout server; Hub as signed-update proxy for module firmware over CAN (chunked, resumable, module-verified before activation — a ~1 MB image is minutes on shared 500 k CAN; if unacceptable, raise as a **new** input to the OQ-7-scoped CAN-FD decision, not an existing clause) *(fleet, oem)* |
| Config management / ITSM | CLI + JSON, REST webhooks | Headless-scriptable provisioning/firmware/config with machine-readable exit states (Ansible/Salt/factory lines); Appendix-D stages mirrorable as ServiceNow/Jira change records *(fleet, oem, security)* |
| Time sync | NTPv4 (both); IEEE 1588 PTP option (MC/broadcast ST 2059-2) | NTP client + sync-status reporting; PTP slaves the Hub timebase to plant time; document correlation bound for forensic captures vs host/BMC/SEL logs *(dcim, oob, mc, competitive)* |
| CMDB/ITAM (ServiceNow, Lansweeper) | REST inventory export / periodic push | Unit ID, BOM rev, Hub FW, per-port module {type, serial=MAC, FW, DETECT class, port binding}; module-serial-change-on-port = inventory event *(fleet, dcim)* |

### 3.3 Security / attestation

| Ecosystem | Protocol | What to implement |
|---|---|---|
| SIEM/audit (Splunk, Sentinel, QRadar, Elastic) | syslog RFC 5424 over TLS / CEF | Tamper-evident, append-only, cryptographically chained audit log (auth, config change, firmware update, identity ops, module-identity change, Appendix-D plan/consent events); on MC survives power/uplink failover *(security, dcim, oob, fleet)* |
| Vuln management / procurement | CycloneDX or SPDX SBOM; CSAF/VEX; ENISA CRA Art. 14 reporting (24 h/72 h/14 d [unverified dates]) | SBOM per firmware release wired into the release pipeline; VEX feed; PSIRT + published CVD; CRA support period per Art. 13 (≥5 yr default from placing-on-market, or expected lifetime) *(security, procurement, fleet, mc)* |
| Platform attestation (OCP-aligned/MC) | SPDM 1.x measurement retrieval; DICE/Caliptra-style measured boot | MC: measured-boot register + SE-signed quote over the host link (differentiator, scope to MC) *(security, competitive)* |
| Vendor third-party-risk | SIG/CAIQ, IEC 62443-4-1 evidence, SOC 2 Type II / ISO 27001 on the Appendix-D service | Standing answers pack: SDL description, key-custody model, support-pipeline data-flow diagram; SOC2/ISO scope for the hosted service. **OQ-62 already owns key custody/signature/audit-retention; OQ-74 owns legal posture — the genuinely-missing half is organizational attestation + a customer-facing data-flow/answers pack** *(security, procurement)* |

### 3.4 Host-side

| Ecosystem | Protocol | What to implement |
|---|---|---|
| Windows fleet (10/11, Server) | USB CDC-ACM or WinUSB via MS OS 2.0 descriptors; MSI/Intune | Driverless in-box enumeration; kernel drivers (if any) Microsoft-signed — cross-signing ended 2021, class devices sidestep it entirely; agent as silent-installable, Intune/SCCM/GPO-manageable, Authenticode-signed (WHQL only if a kernel-mode driver ships) *(oob, oem, security, fleet)* |
| Linux fleet (RHEL/Ubuntu LTS) | cdc-acm tty / hidraw + udev; .deb/.rpm | Mainline-driver enumeration; shipped udev rules + systemd agent in signed distro-native packages; document SELinux contexts for regulated builds *(oem, fleet)* |
| GPU/host tooling (nvidia-smi/DCGM, Prometheus node) | Host agent = enrichment layer only | Fuse per-pin 12VHPWR excursions with DCGM job/power context; the nvidia-smi "systematically overestimates / unreliable for power" critique is CEC's best sales exhibit and needs this integration to demonstrate. **Never a dependency for base telemetry** *(oob, competitive)* |
| Industrial/OT (SCADA/BMS, MC broadcast/industrial only) | OPC UA (preferred) or Modbus TCP; **BACnet explicitly out of scope** | Optional register/OPC-UA map on the host service layer; CEC is not facility equipment, so PDU/SNMP-MIB and BMS expectations do not transfer wholesale *(dcim, mc, oem)* |

---

## 4. Challenged assumptions

Every place the audit disputes a current CEC choice, with evidence and a single recommendation. Where an owner decision (plan §1a, 2026-07-01) has already moved, the challenge is reframed as *input to the open work* rather than a re-litigation.

**4.1 1000BASE-T1 as the enterprise uplink**
*Evidence:* 1000BASE-T1 is IEEE 802.3bp single-pair automotive/industrial Ethernet — 15 m standard reach, no ports on any enterprise access switch; bridging requires a media converter per node (Intrepid RAD-Moon2 / Phytools HMTD class, ~$300 [unverified]) and typically shielded cable to pass EMC. Every competing device (PDU, BMC, OOB console) presents standard 1000BASE-T/SFP. *(all lenses.)*
*Recommendation:* **Re-scope Phase-2 research item 2 from "1000BASE-T1 PHY survey" to "standard 1000BASE-T (RJ-45 + magnetics + OQ-14 OV protection) or SFP as default; T1 only as a documented factory option / internal link."** Firewall this from the legitimate module-side 100BASE-T1 usage (OQ-20/§6.11 Max link over RJ-45 pair 2) — that in-chassis single-pair application is not swept up in the verdict. Scope to ENT-NET (ENT-AIR may have no customer-switch uplink at all).

**4.2 USB as the primary host link**
*Evidence:* enterprise fleet management is agentless and network-attached; an in-band USB path requires software-qualification/USB-device-control review and loses telemetry exactly when the host fails — discarding the platform's best OOB asset. *(dcim, oob, oem, competitive, fleet.)* Skeptic correction: enterprise USB device-control is opt-in policy aimed mostly at removable storage, not a universal default-block of vendor CDC devices [unverified].
*Recommendation:* **Split by variant. On ENT-NET, the network port is the primary management plane and USB demotes to sensing/provisioning/debug — but USB stays a first-class *sensing/correlation* channel (it is the OS-logical vantage feeding Appendix-C fusion and the nvidia-smi comparison).** On ENT-AIR, the local/USB/out-of-band path *is* the product and network-primary is an anti-requirement.

**4.3 $50 / $80 BOM targets**
*Evidence:* the smallest PolarFire SoC (MPFS025T) lists ~$43–69 at low quantity across authorized distributors [unverified] — roughly the whole $50 budget in one part; comparable managed power-visibility gear sells at $1.5k–3k list / ~$60–120 per monitored point [unverified], and no product on the market delivers CEC's per-rail DC-side capability. *(procurement, competitive, dcim, oob, fleet.)*
*Recommendation:* **Confirmed superseded by owner direction (D-ENT-3 → TBD).** Feed Phase-2 costing with (a) the value-pricing comparables as an upper-bound existence proof requiring a real willingness-to-pay check, and (b) the *full cost model* — BOM + certification + compliance documentation + warranty reserve + the 5-year support/spares tail + factory PKI-provisioning ceremony (a manufacturing-line cost, not parts). Delete the stale rows from spec §1/§9 and both READMEs at the Phase-4 rewrite.

**4.4 RJ-11 "trust channel"**
*Evidence:* no DCIM/NMS/BMS/security tool consumes anything over RJ-11; an undefined, powered, telco-shaped jack is a security-questionnaire liability and a physical mis-plug foot-gun (telco battery/ring voltages — OQ-60(c) itself flags it). OQ-60 has already migrated the trust/attestation role onto the secure element (and a proposed second CAN-FD). *(all lenses.)*
*Recommendation:* **Trust is the SE/PolarFire cryptographic architecture (identity, attestation, signed plans/updates); the RJ-11 carries no trust function.** Keep the connector only per OQ-60 (Max power + open-drain FREEZE) with mismate protection, or cut it. Phase-2 research item 3 must be allowed to conclude "cut," and treat the *connector choice itself* as open (candidate relocations: USB, the Ethernet uplink, a keyed non-RJ connector). **Flag the OQ-60 second-CAN-FD trust path as an OQ-7 spec-revision item** — it sits in tension with the LOCKED classical-CAN-500k floor.

**4.5 Weak module identity (DETECT + factory MAC)**
*Evidence:* the spec's own words call the MAC a "weak anchor" (OQ-44); adequate for CMDB inventory (the MAC rides CAN enumeration and is Hub-readable with zero cloud), inadequate for MC provenance/anti-counterfeit and trusted RMA. The §2.3 1-Wire ID/EEPROM path exists but is explicitly not adopted. Module MCUs (C6/S3) already carry eFuse HMAC/ECDSA. *(all lenses; load-bearing for MC.)*
*Recommendation:* **Two moves. (1) Cheap, now: bind a scannable per-unit label serial to the MAC in manufacturing (covers warranty/CMDB/offline-audit). (2) Owner gate D-ENT-5 for MC: adopt 1-Wire/EEPROM OR a CAN-level challenge-response using the eFuse key (no board change) OR formally accept MAC-based identity with compensating controls (Hub-attested inventory, module-change alarming, controlled procurement) and a written residual-risk statement.** No silent default. Route calibration-record storage through the per-family module registers (D-ENT-4), not a blanket Hub SHALL — modules are tier-agnostic (LOCKED).

**4.6 PolarFire SoC vs ESP32-P4 + secure element**
*Evidence:* security-compliance and oob-mgmt argue Enterprise needs only P4 (Secure Boot v2, flash encryption, Key Manager/HUK, eFuse-keyed ECDSA) + a discrete certified SE — 100BASE-TX on the P4's native EMAC serves CEC's telemetry volume, so PolarFire's PUF/DPA/CAVP payload reads as an MC/federal play that "breaks the $50 BOM to solve a problem a $2 SE solves." competitive-landscape counters that transient-capture-in-fabric is the moat no PMBus/PDU product can follow. *(security, oob, fleet vs competitive.)*
*Recommendation:* **D-ENT-2 is RESOLVED by owner direction — both enterprise variants on PolarFire (plan §1a.1); do not re-litigate.** Carry the P4+SE analysis as *recorded context*: it is the security-sufficient fallback if the owner ever wants a cost-down Enterprise variant, and the "100 Mbit is enough" finding feeds PolarFire part *sizing/costing* (Phase-2 item 1) and the D-ENT-3 re-baseline (PolarFire also carries native Ethernet MACs, so standard 802.3 costs little there). If the synthesis is to surface any challenge-to-owner-direction, it is this cost consequence — presented explicitly, not silently averaged.

---

## 5. Requirement candidates

Deduped, tagged **[TS]** table-stakes / **[Δ]** differentiator, ready for the Phase-1 registers. Variant tags (AIR/NET/COMMON) supersede tier labels where they conflict; anything that resolves an open question is drafted as PROPOSED and carried through the D-gate/Phase-4 spec-revision ritual (open questions are never resolved by assumption).

### COMMON (both variants; the out-of-band guarantee, evidence, and lifecycle spine)

- **REQ-HUB-COMMON [TS]** — Hardware-rooted verified boot (PolarFire DPA-resistant boot), flash encryption, monotonic anti-rollback; unsigned/downgraded images SHALL NOT execute. *(security, fleet)*
- **REQ-HUB-COMMON [TS]** — Firmware updates SHALL be signed bundles verifiable on-device over both an online path and an offline (host/USB-delivered) path with rollback protection; demonstrated in an air-gapped cell. *(security, fleet, mc)*
- **REQ-HUB-COMMON [TS]** — Telemetry acquisition, thresholds, and alert delivery SHALL operate with the host OS down/absent (5VSB-powered); loss of the host link is itself an alertable event. Host-down operation is a verified test case, not a side effect. *(dcim, oob)*
- **REQ-HUB-COMMON [TS]** — Every telemetry channel SHALL support configurable upper/lower warning + critical thresholds with hysteresis; crossings generate assertion/deassertion events with severity, delivered via SNMP trap, syslog, and the API. *(dcim, oob)*
- **REQ-HUB-COMMON [TS]** — NTP sync + UTC event stamps + sync-status; tamper-evident, append-only, cryptographically chained audit log (auth, config, firmware, identity, module-identity change, Appendix-D actions) exportable in a documented schema. *(security, dcim, oob, fleet)*
- **REQ-HUB-COMMON [TS]** — Machine-level cumulative energy (kWh) aggregated across populated modules (PROPOSED resolution of OQ-13, owner-gated), power-cycle persistent, audited reset, 24-pin INA228 accumulators as anchor. *(dcim)*
- **REQ-HUB-COMMON [TS]** — Published per-channel accuracy class (≤±1% I/P, ≤±0.5% ref-corrected) verified by per-unit factory calibration (stored in module flash via per-family registers, D-ENT-4), stated traceability + recalibration interval; **NO IEC 62053 conformance claim**. *(dcim, oob, mc, competitive, procurement)*
- **REQ-HUB-COMMON [TS]** — All temperature sensors (Hub NTC, module NTCs, INA die temps) + 12VHPWR ΔT-above-ambient exposed as threshold-able sensor objects in the MIB/Redfish model. *(dcim, oob)*
- **REQ-HUB-COMMON [TS]** — Per-module inventory (SKU, serial=MAC, FW, DETECT class, port binding) as Redfish inventory + machine-readable CMDB export; module-serial-change-on-port = inventory event. *(fleet, dcim, oob)*
- **REQ-FLEET-COMMON [TS]** — Per-Hub factory 802.1AR IDevID (PolarFire-anchored, non-exportable), EST/BRSKI operator-LDevID enrollment; declarative bulk config with drift detection; staged-rollout fleet OTA + Hub-as-proxy for module firmware over CAN; RBAC on the management plane. *(fleet, dcim, oob, competitive)*
- **REQ-HUB-COMMON [TS]** — USB link SHALL enumerate via in-box class drivers (CDC-ACM / WinUSB + MS OS 2.0) on Win10+/mainline Linux; any driver package Microsoft-signed. *(oob, oem, fleet)*
- **REQ-ENV-COMMON [TS]** — In-chassis envelope 0–55 °C local ambient + min-airflow/derating curve; EMC Class A min. *(oem, mc)*
- **REQ-MECH-COMMON [TS]** — Mounting-kit SKUs (PCI bracket, drive-bay tray, standoff) + fixed-length low-profile Cat5e/6 SKUs + routing/airflow guidance for tower/2U(target)/1U(stretch), resolving OQ-4 for these tiers. *(oem)*
- **REQ-SEC-COMMON [TS]** — SBOM (CycloneDX/SPDX) per release; PSIRT + published CVD; CRA reporting readiness; declared security-support period per Art. 13 (≥5 yr default) — a prerequisite of first EU market placement for any tier. *(security, procurement, fleet, mc)*
- **REQ-PROG-COMMON [TS]** — Lifecycle policy: ≥5 yr availability, ≥5 yr spares/RMA post-EOS, ≥12 mo EOL notice + last-time-buy; component-longevity + second-source register (PolarFire client-driven-obsolescence, Espressif 12-yr [unverified]); authorized-distributor-only BOM with lot/date-code traceability; warranty ≥3 yr (5 for MC) + FRU catalog. *(procurement, mc)*
- **REQ-HUB-COMMON [Δ]** — Per-pin 12VHPWR / §6.13 EPS-PCIe transient captures exportable in a documented, integrity-protected (signed/hashed) format with pre-trigger context, retrievable via the API and the out-of-band/dead-system path — the forensic/RMA-evidence product no competitor has. *(competitive, oob, dcim)*
- **REQ-HUB-COMMON [Δ]** — Documented BMC-coexistence position (per-rail DC-side complementary to PMBus/PowerSupplyMetrics; registrable as Redfish AggregationSource), demonstrated ingestion into ≥1 Redfish tool + ≥1 Prometheus/Grafana stack. *(dcim, oob, oem, competitive)*

### NET (networked variant)

- **REQ-HUB-NET-001 [TS]** — Standard IEEE 802.3 1000BASE-T RJ-45 (magnetics + OQ-14 OV protection) or SFP management port as the primary telemetry/management interface; 1000BASE-T1 SHALL NOT be the sole/default uplink. *(dcim, oob, oem, competitive)*
- **REQ-HUB-NET-002 [TS]** — Redfish service (DSP0266/HTTPS, Sensor/PowerSubsystem/TelemetryService/EventService + OEM namespace) passing the Redfish-Service-Validator; SNMPv3 (authPriv) agent + published MIB + traps; OpenMetrics endpoint; syslog RFC 5424 (TLS). *(dcim, oob, competitive)*
- **REQ-HUB-NET-003 [TS]** — 802.1X EAP-TLS supplicant using the IDevID; TLS 1.2+ everywhere; customer X.509 provisioning (EST/SCEP). *(security, dcim, oob, fleet)*
- **REQ-HUB-NET-004 [Δ, owner gate]** — Evaluate 802.3af/at PoE powering so Hub power is independent of the monitored PSU; record interaction with the LOCKED §2.7 5VSB feed as a §2.9 priority-OR extension. *(oem)*

### AIR (air-gapped variant)

- **REQ-HUB-AIR [TS]** — All telemetry, APIs, alerting, and any adopted Appendix-D function operate with zero network egress: local-only APIs, export-to-removable-media evidence path, local time source (isolated-network NTP or local oscillator with stated holdover), on-prem/no plan generation. Verified on an egress-blocked network. *(oob, security, fleet, mc)*
- **REQ-HUB-AIR / module [TS, owner gate]** — No operable RF transmitter; module radio-free-MCU variant vs verifiable disable posture (eFuse/antenna-absent + third-party evidence) resolved at D-ENT-5, never assumed. *(mc, competitive, procurement)*

### Mission Critical

- **REQ-HUB-MC [TS]** — No single failure of any CEC element disrupts the host's power delivery/operation, verified by FMEA/FMEDA + fault-injection per module family; report is a customer deliverable. *(mc)*
- **REQ-HUB-MC [TS]** — Fail-detected redundancy: each redundant element (power feed, CAN A/B, uplink) individually monitored, loss alarmed ≤1–5 s on all channels, failover exercisable by BIST; audit log survives failover. *(mc, dcim, oob, competitive)*
- **REQ-HUB-MC [TS]** — Two independent power feeds (formalize §2.9 three-source priority-OR, LTC4417-class) with break-before-damage failover, per-feed sense, alarmed feed-loss, specified ride-through + persist-on-fault flush; ≥1 source independent of the monitored PSU. *(mc, oem)*
- **REQ-HUB-MC [TS]** — Two physically independent management uplinks of different media (network + USB) with automatic failover, bounded telemetry-loss budget, ≥1 path available host-down. *(oob, oem, mc)*
- **REQ-HUB-MC [TS]** — SR-332 MTBF prediction + derating report per SKU; component-level safety evidence pack (UL94 V-0, UL-recognized critical components, published connector current margins, abnormal-fault test data). *(mc, procurement)*
- **REQ-MC-SEC [Δ]** — Target IEC 62443-4-2 SL-2 as the design checklist (certification deferred to a named customer); FIPS via validated library or certified SE/TPM, never own CMVP; measured boot + SE-signed SPDM-compatible attestation quote. *(security, mc, competitive)*
- **REQ-MC [owner gate D-ENT-5]** — Module authenticity via 1-Wire/EEPROM or CAN challenge-response, OR documented Hub-attested-only identity with written residual risk. *(mc, security, fleet)*

### Enterprise (channel/packaging)

- **REQ-HUB-ENT [Δ]** — OEM/white-label program: OEM USB VID/PID + descriptor branding, configurable LED behavior, co-brandable docs, PCN commitments, ≥5 yr supply + security-update window; internal USB 2.0 header attach option for chassis-closed installs. *(oem, procurement)*
- **REQ-FORM-COMMON [Δ, conditional on D-ENT-5]** — IF mezzanine participation is adopted, the enterprise Hub rev SHALL retain the mezzanine socket contract (connector ref + mount frame per 2026-06-24 design); the appliance SKU must still decompose into separately orderable Hub + 24-pin FRUs. *(oem, fleet)*
- **REQ-ENT [Δ]** — Appendix-D enterprise profile: org/policy/ITSM consent in place of end-user consent; change-window scheduling; Authenticode-signed user-mode agent; plan signatures verified against a pinned key with nonce/expiry/target-machine binding; on-prem swarm/disable-actuation option; SIEM export of every stage. **Note OQ-62 already owns key custody/signature/retention and OQ-74 the legal posture; the additive requirement is SOC 2 Type II / ISO 27001 organizational attestation on the service + a customer-facing data-flow/answers pack (propose as a new OQ or D-ENT rider).** *(security, oob, dcim, fleet, oem, mc)*

---

## 6. Competitive positioning notes

- **No incumbent ships CEC's target capability.** Smart PDUs (Raritan, ServerTech, APC) own *AC-side per-outlet* metering with billing-grade ±1% and full SNMP/Redfish/DCIM integration — a different measurement plane. PMBus PSU telemetry via BMC/Redfish is table stakes in every server but is 100 ms–1 s averaged with no cable/pin visibility and "systematically overestimates" [unverified]. NVIDIA PCAT is reviewer-only (3 rails, 100 ms, not purchasable); nvidia-smi is documented-unreliable for power; Powenetics v2 is a lab rig, not a fleet product. *(competitive.)*
- **The moat is transient-capture-in-fabric + vendor-agnostic per-pin forensics.** AI-datacenter power-stabilization research (arXiv 2508.14318, EasyRider) documents multi-kW ms-scale swings nobody can see per-node — exactly CEC's sub-100 ms DC-side window. This is competitively why the PolarFire data plane is justified: no PMBus/PDU product can follow it. *(competitive.)*
- **The consumer flank is closing on "per-pin monitoring" alone.** ASUS ROG Astral ships per-pin 12V-2x6 sensing (single GPU SKU, ITE IT8915FN [unverified]) and Corsair PinProtect+ does per-pin OCP (Corsair PSUs+cables only [unverified]) — proving demand from the 4090/5090 melting saga. CEC's defensible four properties to lock in requirements: **vendor-agnostic + inline + pre-roll capture + fleet/audit-grade.** *(competitive, mc.)*
- **Position to the honest served market, which sharpens (not weakens) the case.** BMC-less ATX-harness fleets — GPU workstations, render farms, broadcast machines, trading-desk workstations, industrial PCs — have PSUs that expose nothing standard (Corsair iCUE-class links are proprietary/single-vendor). That is precisely where a standard Ethernet management port + DCIM/Prometheus integration is mandatory and where CEC is the only per-rail instrument. Low-latency/HFT trading machines specifically run overclocked ATX/EPS desktop platforms (Blackcore/Hypertec class [unverified]) — arguably CEC's best-fit vertical, not the CRPS-mismatch the mc-verticals lens first implied. *(dcim, oob, competitive, mc.)*
- **OOB visual + electrical fusion (NanoKVM) and dead-system forensic extraction have no counterpart** (PiKVM/BMC KVM do video only). Strong differentiator — but see §7 for the data-governance liability it creates. *(competitive, oob.)*
- **Price on forensic/fleet value, not BOM.** Defensible unit economics in the $500–2500 band [unverified], with the compliance/support tail dominating cost. *(competitive, procurement.)*

---

## 7. Coverage limits / next round

### 7.1 Segments / integration surfaces no lens covered

- **Telemetry-as-sensitive-data / privacy-DLP:** kHz power traces are a workload side-channel (crypto/trading-activity inference), and the NanoKVM vantage literally captures framebuffer/screen content — in the tier table's own financial/defense segments this makes **CEC itself a data-exfiltration and data-governance object** (classification, retention, GDPR/DLP review, per-customer data-flow disclosure). No lens produced requirements for it.
- **Host-machine warranty & install-liability:** does inserting an interposer void the GPU/PSU/system-OEM warranty; who carries liability for a connector event on a monitored machine; what is the per-machine install labor/qualification story at 1k units? (oem-integrator got closest, stopped at reliability skepticism.)
- **FPGA program lifecycle:** the PolarFire path drags in Libero toolchain licensing, bitstream signing/update-at-fleet-scale (distinct from firmware OTA), FPGA development schedule/staffing risk, single-vendor silicon dependence. Procurement priced the part; no lens covered the data-plane *development and update* lifecycle.
- **Upstream dependency sequencing:** both tiers inherit an **unbuilt Hub Pro base** (ESP32-P4, 8 ports, RS-485 receivers, **OQ-5 topology unresolved**); no lens assessed that the Enterprise/MC program stacks behind an unbuilt tier-2 board and an open RS-485 decision.
- **DCIM/NMS vendor-side partnership work:** device-library/certification submissions (Sunbird/Nlyte/Device42), Redfish interop testing, exporter maintenance — a staffing/GTM deliverable, not a firmware feature. Also uncovered: insurance/underwriter and hyperscaler/OCP-busbar segments as explicit in/out-of-scope calls.
- **Host OS support matrix for the agent path:** Linux headless servers, container/VM deployments, driver-signing beyond Windows — every lens critiqued USB-vs-network but none defined what hosts the in-band path must support.

### 7.2 Claims needing primary-source confirmation [unverified]

- **EU CRA dates/scope** (reporting 2026-09-11, essential requirements 2027-12-11, applicability to a telemetry Hub and to non-networked Standard) — repeated verbatim across four lenses from one another; verify against the OJ regulation text before it anchors any severity. Skeptics also stress CRA binds *first EU market placement*, not a calendar date, and the support period anchors to *placing-on-market* (not end-of-sale).
- **"Defense/broadcast/render/trading fleets are predominantly dual-CRPS with no ATX harness"** — an empirical claim that drives the module-family roadmap and contradicts other lenses' served-market framing; needs fleet-composition data, not assertion.
- **Priced/named facts:** MPFS025T ~$43–69 low-qty; Espressif 12-yr longevity; ~$300/node T1 media converters + T1 reach (15 m Type A, 40 m Type B variants exist); FIPS 140-3 CMVP queue 12–18 mo; ESP32-P4 native 10/100 EMAC; PolarFire Athena CAVP certificates + DPA-boot; Espressif absent from NDAA §889 covered list; ESP32 dies TSMC-Taiwan-fabbed.
- **Competitive-product claims:** ASUS Astral per-pin via "IT8915FN"; "Corsair PinProtect+" name/capability; PDU ±1% *certified* to IEC 62053-21 (a meter standard PDU vendors may only reference informally); NVIDIA PCAT specs; PMBus 100 ms–1 s averaging + "overestimates." These will be quoted to customers — verify against vendor primary sources.
- **MiFID II RTS 25 100 µs** — binds *reportable trading-event* timestamps (HFT-technique firms / <1 ms venues), **not** facility monitoring gear. A power-telemetry accessory records no reportable events; treat PTP as a correlation/forensics *capability*, not a legal requirement CEC inherits.
- **DCIM onboarding-artifact mechanics** (Sunbird dynamic-plugin format, EcoStruxure device-definition files, Device42 Redfish discovery depth) before they become release criteria.
- **Enterprise USB device-control posture** toward vendor CDC devices (policy-dependent, not default-block, per skeptic revision); one switch-vendor catalog check that zero enterprise access switches terminate 1000BASE-T1.

### 7.3 Cross-lens contradictions the synthesis reconciled (positions taken above)

- **PolarFire vs P4+SE** → §4.6: owner-resolved to PolarFire (both variants); P4+SE kept as recorded cost-down fallback + PolarFire-sizing input. The one legitimate challenge-to-owner-direction is the cost consequence, surfaced explicitly.
- **Served market (ATX-workstation vs CRPS-server)** → §1 finding 8 + §6: honest wedge is BMC-less ATX fleets; MC must either commit a CRPS/PDB module family or name ATX-architecture as its target class. A named target-fleet statement is required either way.
- **USB demotion vs ENT-AIR** → §4.2: split per variant (NET demotes USB to sensing/provisioning; AIR keeps local/USB as the product).
- **Time-sync scope** → §3.2: tie sync *class* to variant/vertical, not tier — NTP baseline everywhere, PTP for broadcast-MC and forensic-grade correlation; RTS 25 is not a CEC-binding driver.
- **RJ-11 disposition** → §4.4: single recommendation — trust is cryptographic (SE-rooted); RJ-11 keeps only the OQ-60 power/FREEZE function or is cut; Phase-2 item 3 must be free to conclude "cut."
- **D-ENT-5 module-identity default** → §4.5: MC register carries an *explicit adopt-or-formally-decline-with-residual-risk* gate (no silent default); label-serial-bound-to-MAC is the cheap universal baseline.
- **BOM re-baseline framing** → §4.3: value-priced + full-cost-model, feeding the already-open Phase-2 costing; the parts-costing-shaped Phase-2 item 1 should add the compliance/support tail as an explicit input.

---

## 8. Sources

*Repo (all lenses):* `CEC-Platform-Ground-Truth-Spec.md` §1, §2.3, §2.4, §2.5, §2.7, §2.9, §3.1, §6.1/6.5/6.6/6.11/6.13, §8, §9, §10 (OQ-7/13/14/20/44/49/52/54/60/62/66/74), Appendix B.3/B.5, Appendix C, Appendix D; `docs/enterprise-mc-requirements-plan-2026-07-01.md` (§1a owner direction, D-ENT-1..6 gate table, Phase-2 research items, REQUIREMENTS-FORMAT schema); `hubs/hub-enterprise/README.md`; `hubs/hub-mission-critical/README.md`; `docs/mezzanine-stack-design-2026-06-24.md`.

*Standards / regulation:* EU Cyber Resilience Act (digital-strategy.ec.europa.eu; CRA reporting + Single Reporting Platform); NIST IR 8259A; NIST CMVP / FIPS 140-3; IEC 62443-4-1 / 4-2 (ISASecure); DMTF Redfish DSP0266 / DSP2046 / DSP2056 / DSP0270; IEEE 802.1AR, 802.1X EAP-TLS; RFC 7030 (EST), RFC 8995 (BRSKI), RFC 5424 (syslog); IEEE 802.3ab / 802.3bp (1000BASE-T1); OCP Attestation / SPDM / Caliptra; CycloneDX / SPDX / CSAF-VEX; Telcordia SR-332 / MIL-HDBK-217; IPC-A-610 Class 3 / IPC-CC-830; IEC/UL 62368-1; EN 55032 / IEC 61000-6-2; SMPTE ST 2059-2 / ST 2110; MiFID II RTS 25; FAR 52.204-24/25, NDAA §889 / §5949, TAA; ESP-IDF ESP32-P4 security / Secure Boot v2; Microsoft WHQL/driver-signing; Linux cdc-acm.

*Products / market:* Raritan / Server Technology / APC intelligent PDUs; Sunbird Power IQ, Nlyte, Schneider EcoStruxure IT, Device42; OpenBMC PSU-monitoring; NVIDIA DGX Redfish, DCGM, PCAT; Powenetics v2 / Cybenetics; ASUS ROG Astral, Corsair iCUE / PinProtect / HXi PSU; Prometheus exporters (sapcc redfish-exporter, mrlhansen idrac_exporter, snmp_exporter); ZPE / OOB consoles; Eclipse hawkBit / Mender; Microchip PolarFire longevity, Espressif longevity commitment; DigiKey/Arrow/Newark MPFS025T pricing; Intrepid / Phytools / Technica 1000BASE-T1 media converters; Microsoft Defender Device Control.

*Research:* arXiv 2508.14318 (AI-datacenter power stabilization / EasyRider), arXiv 2312.02741 ("Part-time Power Measurements" nvidia-smi critique), arXiv 2604.15522; Uptime Institute — electrical considerations with large AI compute.

*(Every claim in §§1–6 is traceable to the lens abbreviations cited inline; items the skeptics flagged for primary-source confirmation are marked `[unverified]`.)*
