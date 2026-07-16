# Phase-2 surveys — index + cross-survey synthesis (2026-07-02)

_All eight Phase-2 research items (plan §Phase-2) are DONE. One Sonnet agent per survey,
sources cited, prices dated 2026-07-02, unconfirmed claims marked [unverified] in each file.
This index consolidates the recommendations, the cross-survey findings, the register edit
queue, and the D-gate feeds for the owner's Phase-3 review._

## Survey verdicts (one line each)

1. **PolarFire sizing** — MPFS095TS in FCVG484 (pin-compatible 025T↔160T ladder on one land
   pattern); S-suffix carries Athena; compute subsystem ~$150–190 @100q [extrapolated, RFQ
   needed]; flash fabric = no config PROM; DDR possibly skippable (L2 LIM mode).
2. **Ethernet uplink** — MSS-SGMII → VSC8662 (Icicle-precedent; dual-port = free 2nd-uplink
   headroom); integrated MagJack ≥2× isolation floor; OQ-14 closure = magnetics + PHY-side
   TVS + shield GDT at office grade; SFP studied-and-deferred; ~$6–18/unit.
3. **RJ-11 trust channel** — define-as supervised tamper-loop IN + dry-contact facility
   alarm OUT (UPS-EPO pattern), rename off "trust channel"; populate ENT-AIR by default;
   footprint population gated on tamper-module adopt; MUST be decided jointly with OQ-60.
4. **Redundant power** — keep TPS2121 cascade; add per-source TPS25940 eFuse front-ends
   (hardware PG/FLT per source + EN-pin simulate-loss self-test + true reverse block);
   ~$8–9/unit; LTC4417 recorded as owner-selectable alternative; OQ-53..56 closures drafted.
5. **Redundant CAN + uplinks** — real dual-bus CAN is FORECLOSED by the locked single-pair
   module link (all precedent needs a 2nd medium; FT transceivers cap at 125k < locked
   500k); deliverable = fail-DETECTED monitoring (TEC/REC + bus-off alarm + scoped loopback
   self-test); uplinks: dual hardened GEMs → genuine dual-Ethernet (active-standby default,
   LACP opt-in, PRP/HSR declined); USB is NOT a redundant peer; 6 REQ candidates (054–059).
6. **RTOS/firmware** — Zephyr (in-tree PolarFire) over FreeRTOS; two-tier boot (HSS
   high-ceremony + MCUboot/wolfBoot A/B for OTA — Microchip's own IAP path is not
   power-loss-atomic); wolfCrypt-FIPS = the module boundary (CAVP ≠ FIPS validation);
   SNMPv3 = the protocol to prune or buy; `west spdx` feeds the SBOM requirement.
7. **Compliance regime** — CRA dates CONFIRMED against primary text (reporting 2026-09-11
   — RETROACTIVE to units already EU-market-placed; full requirements 2027-12-11);
   harmonized-standard schedule risk (Generic Security Requirements due 6 weeks before the
   deadline); NEW: Annex III Class I "network management systems" classification gray zone
   forks self-assessment vs notified-body; FIPS wording rules; per-regime cost classes.
8. **Radio-free MCU** — option (a) radio-free MCU WINS: STM32G4 primary (G431 digital
   modules / G474 12VHPWR-Std — could absorb §6.13 comparators on-die); ESP32-P4 confirmed
   radio-free (12VHPWR Pro already compliant) but no SIP module exists + leaves the
   China-origin axis open; option (b) fused-off ESP32 is DEAD on evidence (no Wi-Fi-disable
   eFuse exists on S3/C6; DoD guidance wants physical absence; fails inspect-unpowered).

9. **MC availability ladder (survey 9, post-ruling)** — watchdog = small safety-MCU class
   (S32K3 non-lockstep rec, Zephyr-native; Hercules/AURIX precedented alternatives;
   TPS3813 backstop option); 2oo2 + watchdog-arbiter VALIDATED over 2oo3 (serviceable
   appliance, not spacecraft); checkpointed-not-lockstep state sync over free on-die
   PCIe(NTB?)+CAN1; voted boundary = tamper-log + Appendix-D actuation only; northbound
   reconnect-tolerated, CAN session-continuous; N/N-1 rollout diversity as the common-mode
   mitigation; MC adder ~$22-35, MC-Max +$150-195 (+PCB class). No SIL/ASIL claims.

## Cross-survey load-bearing findings

1. **The 5VSB power-budget collision (survey 1, corroborated by 6).** A PolarFire-class Hub
   cannot run its full compute load on the shared/capped 5VSB rail the way ESP32-class Hubs
   do. Consequence: MAIN_5V becomes the primary source; 5VSB covers a defined minimal
   standby posture only. REQ-HUB-COMMON-025 must split ("full telemetry on standby" vs
   "full compute on standby"), and the §2.9/OQ-53..56 arithmetic reruns at PolarFire load.
2. **The redundancy story is now honest and concrete.** CAN = fail-detected (architecture
   ceiling, not a compromise — survey 5 grounds why); power = eFuse-fronted cascade with
   commanded self-test (survey 4, which also found the as-built granularity gap:
   5VSB_SENSE reads the OR'd node, so three sources are not independently monitorable
   today); uplink = genuine dual-Ethernet off the two hardened GEMs (survey 5 + free
   headroom from survey 2's dual-port VSC8662).
3. **Two live ENT-AIR contradictions need owner rulings (D-ENT-5/6):**
   (a) the NanoKVM forensic egress path (its own Ethernet/WiFi) silently violates
   "zero network egress by design" — gate it policy-disabled-by-default or remove it on
   AIR builds (survey 5, REQ-HUB-AIR-059 draft);
   (b) the ATR tamper-module candidate is an intentional RF emitter (plan §3a.2) while
   survey 8 kills the fused-off-radio posture — the radio ruling must cover both.
4. **One connector, two owners:** the RJ-11 definition (survey 3) and OQ-60's per-port Max
   sideband proposal want the same 6P6C shell with different cardinality — resolve as ONE
   decision at D-ENT-5, or rename one connector.
5. **Compliance is calendar-driven, not GA-driven.** CRA Art. 14 reporting machinery
   (PSIRT/CVD) is due 2026-09-11 for ANY in-scope unit already EU-market-placed — that
   binds Standard/Pro timing, not just enterprise GA. REQ-HUB-COMMON-014 must re-anchor to
   the calendar. And the FIPS path has its own clock: wolfCrypt's validated OE list has no
   RISC-V today, and CMVP queues run 12–18 months — the wolfSSL OE-extension conversation
   starts at Phase 3, not after a board exists.
6. **The part picks compose into one coherent hub front-end:** MPFS095TS (FCVG484) +
   VSC8662 on MSS-SGMII (fabric stays free for the data plane) + TPS25940 eFuse fronts into
   the kept TPS2121 cascade + Zephyr/HSS/MCUboot-or-wolfBoot/wolfCrypt. Nothing in any
   survey contradicts another survey's pick.

## Register edit queue (Phase-3 actions, all DRAFT edits pending owner review)

- REQ-HUB-COMMON-025: split standby-posture vs full-compute host-down guarantees (survey 1).
- REQ-HUB-COMMON-060..062: re-scope to eFuse-fronted architecture + PolarFire load; adopt
  survey 4's OQ-53..56 closure language.
- Adopt survey 5's REQ-HUB-COMMON-054/055/056/058, REQ-HUB-MC-057, REQ-HUB-AIR-059.
- REQ-HUB-COMMON-090: split into 090a–f per-regime rows (survey 7 table).
- REQ-HUB-COMMON-091: split 091a (CRA 5-yr support floor, gate: none) / 091b (commercial
  lifecycle, gate: D-ENT-3).
- REQ-HUB-COMMON-014: re-anchor to CRA calendar dates; mark platform-wide.
- module-requirements-common.md §6: add the per-module-family SBOM/PSIRT row (modules are
  separately-marketed components under CRA).
- REQ-HUB-COMMON-033: rewrite per survey 3's define-as + joint-OQ-60 gate.
- REQ-MOD-AIR-020: resolve toward option (a); name STM32G4 (families) + ESP32-P4 (Pro) as
  the candidate parts; strike option (b) with survey 8's evidence cited.
- REQ-HUB-NET-020: apply the D-ENT-5 protocol prune (SNMPv3 defer-or-license; keep
  Redfish-aligned subset + OpenMetrics + syslog-TLS).

## D-gate feeds

- **D-ENT-3 (BOM)** adders @100q, all [estimate/RFQ-needed]: compute $150–190 (095TS build;
  $60–90 for the 025TS floor), uplink $6–18, redundant-power pack $8–9 (+$2–8 if LTC4417),
  2nd MC uplink PHY+magjack ~+$6–9, plus the PCB-class jump (6+ layer, controlled
  impedance, BGA assembly) that belongs in value-pricing, not parts math.
- **D-ENT-5 line items, now fully enumerable:** 1-Wire module identity; CAN-FD stance
  (unchanged: locked classical); provenance role; mezzanine form; radio posture → survey 8
  option (a); RJ-11 function + OQ-60 merge; SNMPv3 prune; ATR emission policy; NanoKVM
  AIR-egress gate; signing-key custody procedure; SPDX-vs-CycloneDX SBOM format.
- **D-ENT-6:** the redundancy pack is a discrete scope knob (survey 4/5 both note it can
  land Enterprise-only, MC-only, or both without redesign); ENT-AIR "redundant uplink" =
  redundant local paths; CRA Annex III classification interacts with what ENT-NET claims
  to be.
- **New owner-queue items from this phase:** CRA Annex III "network management systems"
  classification (needs the delegated act or counsel — forks the conformity route); CRA
  2026-09-11 applicability check (is anything EU-market-placed?); wolfSSL FIPS OE-extension
  early engagement; S-suffix (Athena) confirmation against REQ-HUB-COMMON-001 wording.
