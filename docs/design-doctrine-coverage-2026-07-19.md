# Design-doctrine coverage — the four sheets vs the pipeline (2026-07-19)

_Owner ask (2026-07-18): "what is left to implement as the doctrine in the pipeline
citing from all the board's best practices and industry practices, check it against
what is there vs not." DERIVED VIEW — canonical: the four design sheets
(`docs/standard-tier-review/STANDARD-DESIGN-SHEET.md`, `docs/PRO-MAX-DESIGN-SHEET.md`,
`docs/enterprise-requirements/board-program/ENT-DESIGN-SHEET.md`,
`testers/DESIGN-SHEET.md`) and the live registry (`scripts/cec_constraints.py`,
42 rows + CL-25 classes), the advisory audits (`cec_impedance`), the oracle
conjunction (`route_oracle_grade`), and the §K wave-1 checkers (36ec3f62).
Update this file in the same change that lands a checker._

**Status legend:** ✅ MECHANIZED (named checker/gate/audit runs today) ·
◐ PARTIAL (machinery exists, the sheet's specific rule isn't asserted) ·
✗ MISSING (nothing runs) · 📋 non-code (process/fab-doc rule).

## 0. The cross-cutting gap: per-tier DESIGN PROFILE toggle (build FIRST)

The sheets are deliberately stricter per tier, and nothing in the pipeline can tell
boards apart by tier today — checkers self-gate on *geometry* only. Every tier-scoped
row below therefore needs ONE shared mechanism before it can arm:

- **`design_profile`** per board (extend `board-manifest.json`; values
  `standard | pro-max | ent | tester`; ABSENT = standard).
- `cec_constraints` gains a `profile:` scope on tier rows — a row armed for `ent`
  never fires on a Standard board (the "toggleable because they're a lot stricter"
  requirement made concrete).
- `write_netclasses`/`write_dru` gain per-profile class tables (§5 below).
- The oracle conjunction reads the profile for its gate set.
- **Inertness proof required at landing:** profiles defaulted → full host battery +
  SB-08 golden byte-identical. Teeth: a sabotaged profile mismatch must fire.

## 1. STANDARD sheet (§C/§D/§K) — the most-covered tier

| Sheet rule | Status | Mechanization / gap |
|---|---|---|
| C.1 shunt HI=upper, sense IC inner edge | ✅ | `kelvin-sense-from-inner-pad`, `kelvin-sense-adjacent-shunt`, corpus rule, kelvin HARD gate |
| C.2 four-wire Kelvin, 0.25 mm pair, stub exemption | ✅ | kelvin gates + `audit_kelvin_loops` (advisory) + DRU exemption |
| C.3 INA240 RC at the INA, **Rf ≤10 Ω value** | ◐ | placement/class covered; the Rf-value BOM assertion is not (S build: value rule on RFH/RFL rows) |
| C.4 §6.13 chain topology | ✅ | generator netlist assertions (regen-verified) |
| C.5 sense-vs-power ≥2 mm / no >10 mm parallel | ✅ | `audit_crosstalk` (advisory — flips gating under the profile) |
| C.6 high current = pours, pour-after-route | ✅ | `high-current-pour-present/-integrity`, `no-foreign-on-high-current-pour`, TPC pass-form |
| C.7 via fields counted, GND-barrel funnel | ✅ | `electrothermal_solve` per-via split + 2.5D thermal gate |
| C.8 thermal reliefs forbidden on high-current joints | ✅ | `netclass-geometry-conformance` (CL-25) |
| C.9 thin-lane anti-pad severing | ◐ | DRC unconnected catches it; the rule lives only in `route_atx24()` comments — no general lane-width-vs-antipad lint |
| C.10 Mini-Fit pin map (GND 1-4 / 12 V 5-8) | ✅ | CONFORMANCE pin-map suite |
| C.11/C.12 blade orientation, pitches, keying no-rigid-transform | ✅ | `check_output_daughterboards.py` (113 OKs, teeth verified) |
| C.13 FTP jack + DETECT 2.2 k + PESD pin 8 | ✅ | `rj45-link-pinmap`, `detect-resistor-code`, `detect-esd-diode-pin8` |
| C.14 TJA1051 + CAN impedance caveat | ✅ | `can-transceiver-tja1051t3` + `audit_impedance` (91–105 Ω finding logged) |
| C.15 USB 90 Ω front end | ✅ | `usb-diffpair-routed-coupled` + impedance audit (91.3 Ω validated) |
| C.16 LED chain buffered, order matches refdes | ◐ | power-class widths covered; chain-order-vs-refdes lint missing (LOW) |
| C.17 Hub front end | ✅ | netlist assertions (hand-maintained board) |
| C.18 24-pin specials (J1.1 NC, MAIN_5V tap) | ✅ | CONFORMANCE + netlist assertions |
| C.19/K.4 fiducial protocol (count/clear/asymmetry) | ✅ | `fiducials-present` + **`fiducial-protocol` (wave 1)** |
| K.1 placement order + grid/row alignment; MLCC-edge | ◐ | pass-form ladder encodes ORDER; **`mlcc-edge-orientation` (wave 1)** covers the flex-crack rule; grid/row-alignment lint missing (LOW — AOI nicety) |
| K.2 rotation protocol; **CPL-rotation-table lint** | ◐ | pad-angle normalization in generators; polarity-direction-uniformity + CPL-table-at-fab-snapshot lints MISSING (S) |
| K.3 silk protocol; **value-fit test in regenerators** | ◐ | silk score/fp oracle term exists (G7 #3); the generation-time value-fit test superseding unconditional Value→silk MISSING (S) |
| K.5 decoupling geometry; via order / no shared vias | ◐ | **`decoupler-adjacency-k5` (wave 1)** covers distance; PAD→CAP→VIA order + shared-via legs need routed-copper analysis (M) |
| K.6 stitching pitch + Hub edge-band ruling | ✗ | **gnd-stitch-pitch audit (perimeter ≤5 / field ≤10 / SH-tab 2-via) + hub-beta band assertion — the biggest §K hole** (M; calibrate on routed hub/12vhpwr; corpus row is Class H until then) |
| K.7 DFM floors; teardrops; stencil/tombstone | ◐ | dfm stage + netclass floors cover design floors; the consolidated **jlc-profile artifact** (FOLLOWUPS 2026-07-11) still owed; stencil/anti-tombstone = 📋 fab-doc rules |
| K.8 e-cap rules; **thermal-tag presence** | ◐ | **`ecap-edge-distance` (wave 1)** covers edge/V-cut; the §6.6 local-ambient thermal tag + reflow-profile pull are open ([wb]) |
| §D netclass table + DRU seeds | ✅ | committed .kicad_pro precedents + netclass→DSN carriage (405ba7c9) + `netclass-geometry-conformance` |
| §F gates (TPC, ERC/DRC, SB-08, intake, thermal) | ✅ | live (thermal determinism completed 2026-07-17; coarse-CPU knob 2026-07-19) |

**Standard remainder = 7 PARTIAL/1 MISSING**, all named in FOLLOWUPS "K-MECHANIZATION
REMAINDER". Highest value: K.6 stitch audit (M), K.3 value-fit (S), K.2 CPL lint (S).

## 2. PRO-MAX sheet — mostly MISSING (boards not yet captured; build with the pathfinder)

| Sheet rule | Status | Mechanization / gap |
|---|---|---|
| C.1 SAR analog island, AGND single tie | ✗ | analog-island/single-tie-point checker missing (M; net-topology + copper scan) |
| C.2 REF3033 ≤10 mm from REF pin | ✗ | simple adjacency checker (S — `kelvin-sense-adjacent-shunt` shape) |
| C.3 INA240 rules | ✅ | inherits Standard §C.1-3 unchanged |
| C.4 RS-485 named class, 120 Ω target, audit BEFORE route | ◐ | `audit_impedance` runs on named classes — the **RS485 class row isn't in the netclass seeds yet** (S; profile table §5) |
| C.5 P4 **`qfn-escape-completeness`** | ✗ | M — same shape as ENT's bga-escape; build once, parameterize package |
| C.6 AD9253→GW5A **LVDS lane + unbroken reference** | ✗ | **THE shared checker — ENT §D, tester-max §D, Max modules all cite it; build ONCE** (M) |
| C.7 slow-path matched bus length report | ◐ | pair-skew exists for _P/_N pairs; bus-class (6-net) length report missing (S) |
| C.8 Rogowski/fast-AFE guarded pairs + reserved position | ◐ | diff-pair machinery exists; FAST_AFE class + reserved-DNP BOM row lint missing (S) |
| C.11 USB_HS ±0.5 mm match | ◐ | S2 skew scorecard measures pairs; the tightened HS bound is a profile threshold (S) |
| C.12 supercap DNP provision lint + SPICE charge curve | ◐ | SPICE pilot exists (`cec_spice`); DNP-provision BOM lint missing (S); bench items stay 📋 |
| C.14 DETECT 4.7 k Pro row | ✅ | `detect-resistor-code` table already carries the platform codes |
| §F.1 impedance audit on RS485/LVDS/USB_HS pre-route | ◐ | audit exists; needs the named classes emitted (profile) |

## 3. ENT sheet — the ★ fab-gates are the clock-driven builds (~Aug demo)

| Sheet rule | Status | Mechanization / gap |
|---|---|---|
| ★ `isolation-moat-clearance` (uplink + RJ-11 moats) | ✗ | copper-to-copper across a named polygon; **REQUIRED before any hub fab** (M; geometric scan + moat def in the board) |
| ★ `bga-escape-completeness` + `via-in-pad-zone` | ✗ | every used ball reaches fan-out; Type VII list ↔ fab-notes match (M; needs the FCVG484 land — netlist half buildable now) |
| ★ `t1-mdi-chain-order` (hub ×8 + every module) | ✗ | topological order jack→CMC→caps→PESD→PHY + stub lengths (M; **netlist half testable TODAY against the 35 captured hub-ent sheets**) |
| `misplug-chain-order` (pin1→SS110→eFuse→LDO) | ✗ | pure netlist path assertion (S; testable today) |
| `pin7-conditioning-presence` (ENT boards only) | ✗ | S; needs the profile toggle (consumer pin-7 stays NC) |
| detect-resistor-code ENT 10 k row | ◐ | code table has 10 k (CAN+100BASE-T1); the per-profile EXPECTATION (ENT boards must read 10 k) needs the profile |
| `rgmii-bus-skew`, `emmc-bus-skew` | ✗ | length-class checkers (M; [wb] budgets frozen at layout kickoff) |
| watchdog private-CAN net isolation | ◐ | `check_hub_ent_sch.py` sheet-09 assertion exists (sch-level); PCB-level net-isolation lint missing (S) |
| PG-chain / per-port / DETECT-ladder assertions | ✅ | `check_hub_ent_sch.py` full-hierarchy blocks (sch-level of record) |
| Zone/moat keepout enforcement | ◐ | the corridor-keepout mechanism exists; ENT moat/zone polygon definitions not yet declared per board |
| Electrothermal: 5 V trunk + 1V0@7 A + PHY dissipation | ◐ | solver ready; the ENT board config (component_power inventory) not written |
| 6L + via-in-pad fab-class gate | 📋 | vendor quote + capability confirm before layout freeze |
| AIR-build self-describing silk gate | ✗ | S; silk/fab-note assertion on the unpopulated uplink land |

## 4. TESTER sheet (§F.5 + §C.26) — all-new checker family (F.5 rule: teeth before trust)

| Sheet rule | Status | Mechanization / gap |
|---|---|---|
| C.2 DAC ref-trace-crosses-load-pour lint | ✗ | S-M; same geometry scan as pour-integrity, victim=ref class |
| C.3 gate-length rule (≤15 mm main / ≤10 mm slice) | ◐ | netclass length rules exist in KiCad-10 DRU; the Gate-class seed + checker missing (S) |
| C.10 per-device NTC presence + ballast-match | ✗ | S each; `ntc-board-temp-by-shunt` is the pattern to extend per-L2-device |
| C.11 loop shunts Kelvin | ✅ | platform kelvin gates verbatim |
| C.13 SCP loop-area (<40 mm loop) | ◐ | `audit_kelvin_loops` machinery is the right shape; crowbar-loop variant missing (S) |
| C.14 star-ground single-junction topology | ✗ | netlist topology checker (S; pure graph assertion) |
| C.8 switcher-to-analog ≥15 mm spacing | ◐ | `audit_crosstalk` proxy near; the named spacing rule + threshold missing (S) |
| C.18 slot-deck keying (extend `check_output_daughterboards`) | ◐ | checker exists + teeth; deck extension (per-family congruence + deck rotations + J_SIG map) missing (M) |
| C.22b harness-count lint (≤3 connections/plate) | ✗ | S; BOM/netlist count per plate assembly |
| C.24 SCP transient: per-family I²t design assertion | ✗ | M; the envelope math is in sketch §3b — mechanize as a design-time assertion per docked family |
| C.24g arm-relay coil reachable ONLY from arm bit | ✗ | S; netlist reachability assertion |
| C.26 channelization (a)-(e): fences, per-slot fuse, isolation | ✗ | M; netlist-computed group-capacity sums vs §12c fence table — the biggest tester-specific build |
| §D LoadBus/KelvinSense/Gate/Analog classes + LVDS (Max) | ✗ | profile netclass table (§5) + the shared LVDS checker |
| §F.3 electrothermal at +25 % / 40 °C duct config | ◐ | solver ready; tester board config + duct ambient profile not written |
| §F.6 Stage-1 answers recorded | ✅ | recorded in the sheet; synth REQUIREMENTS consume them |
| Displays/BOM-lint (C.23), fan SKU rows | ◐ | generic BOM lint exists; panel-MPN-when-header-placed conditional missing (S) |

## 5. Netclass/DRU emission per profile (all ✗ until the profile lands)

`write_netclasses`/`write_dru` emit the Standard cable-board table today. Owed tables:
**pro-max** RS485 · LVDS · SAR_Analog · FAST_AFE · USB_HS · SCAP —
**ent** BGA_Fanout · SGMII · RGMII · T1_MDI · CLK_LVDS · EMMC · QSPI · SYNC7 ·
PWR_CORE · ISO-moat rule — **tester** LoadBus · KelvinSense · Gate · Analog ·
SPI/Digital · PD/VBUS (+ LVDS on Max). Each is a data row in the profile, not new
machinery; the DSN carriage (405ba7c9) then carries them into FR automatically.

## 6. Industry-practice citations — mechanized vs doc-only

Mechanized already: IPC-2152 (electrothermal solver k-params, corpus Class A) ·
IPC-2141A/Bogatin (audit_impedance closed-form) · Ott return-path/crosstalk
(audit_crosstalk + stagger-the-mirror lever) · TI INA layout (kelvin checker family) ·
IEC 61000-4-2 placement (detect-esd checker) · USB-IF (diffpair gate + audit) ·
TI SLLA270 (CAN term conformance) · IPC-7351B courtyards (DRC discipline) ·
IPC-A-610 silk legibility + MLCC flex-crack + e-cap vendor rules (**wave-1 checkers**).
Doc-only until their checkers land: IPC-7095/4761 (BGA/via-in-pad → ★ ENT) ·
RGMII v2.0 / JESD84-B51 (skew checkers) · IEEE 802.3bw/TC-8 (T1 chain) ·
IEEE 802.3 isolation + IPC-2221B Table 6-1 (moat) · SLLD009 LVDS (shared checker) ·
ADI MT-031/MT-101 (SAR island) · J-STD-001/IPC-CM-770E (📋 process docs).

## 7. Ranked build queue (teeth-first, AM-02 discipline on every row)

1. **Profile toggle + inertness proof** (S) — prerequisite for every tier-scoped row.
2. **Standard K remainder** (serves the shipping beta line): K.6 stitch audit (M) →
   K.3 value-fit (S) → K.2 CPL lint (S) → K.5 via legs (M) → K.8 thermal tag (S) →
   C.3 Rf-value lint (S).
3. **Shared LVDS plane-integrity checker** (M) — one build unblocks Pro-Max/ENT/tester-max.
4. **ENT ★ trio** (clock: ~Aug demo): `t1-mdi-chain-order` netlist half NOW (vs the 35
   captured sheets) → `misplug-chain-order` (S, now) → `bga-escape`/`via-in-pad-zone`
   (with the FCVG484 land) → `isolation-moat-clearance` (with the board's moat polygon).
5. **Pro-Max at the 12vhpwr-pro pathfinder capture**: RS485 class + audit wiring (S),
   REF3033/SAR adjacency (S), qfn-escape (M, shares the BGA-escape build).
6. **Tester family at its layout start**: channelization fences (M) → star-point (S) →
   ballast/NTC/loop-area/harness lints (S each) → I²t assertion (M) → deck keying (M).

Boards gate the geometric halves: tester + ENT PCBs don't exist yet, so their
geometric checkers land on synthetic micro-fixtures (the `test_kelvin_topology`
pattern) until first layout; every netlist-level row above marked "now" is testable
against captured schematics TODAY.
