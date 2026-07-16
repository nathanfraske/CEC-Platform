# ENT board family — exhaustive design sheet (pipeline input)

_Owner ask (2026-07-16): "the same thing for all the Enterprise modules as you did the
tester — an exhaustive routing / placement / design rules spec for the pipeline to
implement and take into consideration." Companion to `testers/DESIGN-SHEET.md` (same
section skeleton). DERIVED VIEW — canonical sources: spec §13, the REQ registers,
`spec-sheets/hub-ent-variants-plan.md` (edge map, IO budget, stackup, SKU matrix),
`spec-sheets/module-ent-spec-sheets.md` (per-family deltas),
`fcvg484-breakout-study-2026-07-03.md` (BGA feasibility — its conditions are BINDING
here), `hubs/hub-enterprise/SCHEMATIC-PLAN.md`, BOM-A..D. Working-basis numbers are
tagged **[wb]** — freeze at layout kickoff, never silently._

## A. Board census (who exists and why)

| Board | SKUs served | Why it is its own board |
|---|---|---|
| `hubs/hub-enterprise/` | NET/AIR × B/MC/MCX (6) + TS HS-silicon fit — ONE PCB, DNP matrix (REQ-105) | FCVG484 BGA + T1 fabric + uplink isolation = a fab class above every other platform board |
| `modules/atx-24pin` ENT build | ENT-24 | rev3 copper + P4/T1/misplug deltas; INA228 sensing UNCHANGED; bulk-5VSB source role |
| `modules/eps-8pin` ENT build | ENT-EPS (= EPS Pro) | + ADS131M08 fast path + T1 stream; per-cable shunts unchanged |
| `modules/pcie-8pin-{2,3}port` ENT | ENT-PCIe ×2 SKUs | same as EPS pattern ×2/3 cables |
| `modules/12vhpwr-pro` ENT build | ENT-12VHPWR | the existing Pro board (P4 + per-pin INA240 + fast ADC) + common ENT deltas |
| `modules/ent-kvm-carrier/` | NET accessory | M.2 KVM compute + HDMI capture + USB gating — its own I/O set |
| `modules/ent-common/` (p4-t1-block) | — | NOT a board: the shared schematic block every family instantiates |

## B. Floorplan doctrine (zones)

**ENT modules — inherit the consumer condensed-board doctrine unchanged** (cable/shunt
column on the connector axis, sense band hard against the shunts, control core right,
RJ-45/USB mouths out the edge; §6.7/§6.8 Kelvin + corridor rules; both inner layers GND
on cable boards). ENT adds three zones ON TOP:

```
[Z-T1]   T1 front-end: RJ-45 pair-2 pins → CMC → AC caps → PESD → DP83TC814S,
         one straight chain at the jack, PHY ≤20 mm [wb] from jack pins 4/5;
         RMII PHY→P4 stays ≤40 mm [wb]. NOTHING crosses this chain's gap.
[Z-MISPLUG] pin-1 VCC entry: SS110 series + SMAJ58A + TPS26621 eFuse AHEAD of the
         LDO — first things after the jack, before any rail copper spreads.
[Z-P4]   ESP32-P4 core: external QSPI flash ≤12 mm [wb] (matched-length not
         required at QSPI speeds ≤80 MHz, keep the bus one-layer), native USB
         90 Ω pair to the flash/debug USB-C, RMII bus to the PHY.
```

**Hub — front→rear = ports→compute→isolation/power** (edge map is the variants-plan §4
ruling, restated as zones):

```
[H-PORTS  front] 8× RJ-45 FTP in two ganged 4-groups, SK6812 chain between;
                 per-port DETECT ladder + pin-7 conditioning + mis-plug parts AT
                 the jack; per-port T1 MDI front-end chains pointing rearward.
[H-FABRIC]       2× LAN9370 between the port field and the BGA — each switch
                 centered on its 4-port group; MDI forward, RGMII rearward.
[H-BGA center]   MPFS FCVG484 + decoupling field + core/bank rails ring; JTAG +
                 boot straps + DSC1123 clock at the NW quadrant (breakout study:
                 JTAG_SYSCTRL + SGMII are silicon-fixed there).
[H-STORAGE]      W25Q256 + eMMC on the MSS side of the BGA, short buses.
[H-UPLINK rear]  DP83869 + JXD1 MagJack + GDT/RClamp inside an ISOLATION MOAT;
                 blue-bezel jack on the rear edge. ×2 mirrored for MC dual-uplink.
[H-PWR rear]     EXT barrel + JST feeds + 3× TPS25940 eFuses + TPS2121 cascade +
                 2× 4700 µF hold-up + TLV62569; power flows rear→center.
[H-SECIO rear]   RJ-11 + LM393 loop sense + TLP172A dry contact — rear edge,
                 NEVER adjacent to module ports (edge-map rule).
[H-WD corner]    S32K watchdog + own LDO + private CAN at the SoC reset/strap
                 corner (MC/MCX population).
[H-INTERIOR]     NanoKVM aux JST, service button, NTC, 4× M3 chassis-GND.
```

- Zone boundaries are keepout-enforced in the pipeline (corridor mechanism, as on the
  testers sheet). AIR SKUs leave H-UPLINK **unpopulated bare land** — the inspection
  story — so its silk/fab must stay complete and self-describing on every build.

## C. Per-component placement rules (rule → why → pipeline check)

**Module side (all families — the p4-t1-block physical contract)**
1. **DP83TC814S-Q1** → Z-T1. MDI chain order jack→CMC→caps→PESD→PHY, chain length
   ≤20 mm [wb], PESD stub ≤3 mm, 100 Ω diff throughout, no plane split under the pair.
   Why: 100BASE-T1 is a single UTP pair — return-loss budget lives or dies at the
   front-end. Check: NEW `t1-mdi-chain-order` (topological order on the netlist +
   measured stub lengths) + diff-pair class gate. [practice I.4, I.11]
2. **ACT1210L CMC** → in-chain, pads along the pair axis, no via between CMC and jack
   [wb]. Check: chain-order checker's segment table.
3. **AC coupling caps** (≥100 V per survey 10) → between CMC and PESD, side-by-side,
   same layer. Check: chain order + BOM value/voltage lint.
4. **TPS26621 + SS110 + SMAJ58A** → Z-MISPLUG at pin-1 entry, eFuse BEFORE the LDO
   node; SMAJ58A return ≤5 mm to the GND pour. Why: REQ-MOD-COMMON-053 mis-plug
   fail-safe is a topology claim. Check: NEW `misplug-chain-order` (pin1 → SS110 →
   eFuse → LDO netlist path; TVS node placement).
5. **ESP32-P4 + QSPI flash** → Z-P4 per zone rule; flash CS/CLK same layer as the P4
   pads where possible. Check: length report + one-layer flag (advisory).
6. **DETECT** = 10 kΩ code (EVERY ENT family — 6th ruling) + PESD at pin 8. Check:
   existing detect-resistor-code checker taught the ENT 10 kΩ row.
7. **Pin-7 SYNC/FREEZE** conditioning (R_SYNC series + SMAJ58A) at the jack. Check:
   NEW `pin7-conditioning-presence` (ENT boards only; consumer pin-7 stays NC).
8. **Sensing corridors: UNCHANGED platform doctrine** — §6.4 shunt values, §6.8
   four-wire Kelvin from the shunt inner edges, high-current corridor keepouts, sense
   IC hard against its shunt. The existing checkers (kelvin-sense-from-inner-pad,
   high-current-pour-integrity, min-pour-cross-section) carry over UNMODIFIED.
   [practice I.12]
9. **ADS131M08** (EPS/PCIe fast path) → sense band, ≤15 mm [wb] from the farthest
   shunt tap it serves; its CLKIN/SPI routed away from the shunt Kelvin pairs (≥2 mm,
   no parallel >10 mm). **REF3033** (12VHPWR ENT) → ≤10 mm from its ADC ref pin,
   dedicated bypass. Check: Analog-class spacing rule + placement report.
10. **TJA1051T/3** → at jack pins 3/6 side, platform pattern unchanged.

**Hub side**
11. **MPFS FCVG484** → H-BGA. BINDING breakout-study conditions: (a) IPC-4761 Type VII
    via-in-pad on the bounded deep set (~35–50 balls: JTAG_SYSCTRL + SGMII ring 4–7 +
    MSSIO spill), dogbone escape everywhere else; (b) L4 reserves controlled-impedance
    area reachable from the NW quadrant; (c) the `BGA_Fanout` netclass below — the
    0.22 mm Signal class does NOT fit the 0.4 mm escape channel. Decoupling: per-bank
    cap ladder per BOM-A placed on the escape rings' free faces; package center is
    100 % power — core-rail entry from two opposite sides. Check: NEW
    `bga-escape-completeness` (every netlist-used ball reaches board fan-out; no
    silent stranding) + `via-in-pad-zone` (Type VII list ↔ fab-notes table match).
    [practice I.1]
12. **MIC22705 (VDD 1.0/1.05 V, 7 A)** → adjacent to the BGA core-rail entry side;
    switch loop ≤ minimal; remote sense to the BGA ball field edge; pour cross-section
    per the electrothermal gate at 7 A. Check: min-pour-cross-section + loop-area
    advisory. [practice I.13, I.14]
13. **MPM3833C ×5–6** → one per bank-rail edge nearest its load bank; switcher keepout
    ≥3 mm [wb] from SGMII/CLK_LVDS/eMMC classes. Check: Analog/RF spacing rule.
14. **PG chain / sequencing (03d)** → TPS3839 threshold parts at their rails; chain
    order asserted in the netlist. Check: check_hub_ent_sch PG-chain assertion block
    (exists per plan §2.2 — extend at capture).
15. **DSC1123BL5** → NW quadrant, LVDS 100 Ω pair to the MSS refclk balls, ≤40 mm
    [wb], unbroken reference plane. Check: CLK_LVDS class gate. [practice I.7]
16. **LAN9370 ×2** → H-FABRIC, one per 4-port group. RGMII to the fabric bank: 50 Ω SE,
    bus skew data-vs-clock ±2.5 mm [wb] (internal delay mode per straps — final skew
    budget owed from the full DS, watch item), length ≤60 mm [wb]. MDI ×4 forward to
    the port field, 100 Ω diff. EXTRES/T1_EXTRES 6.49 kΩ 0.1 % short to VSS. XI/XO
    crystal at the pins. Strap resistors adjacent to their pins, DNP-provisioned where
    the brief leaves values open (full DS is login-locked — LAN9371/72 family docs are
    the proxy; do NOT invent values). Check: NEW `rgmii-bus-skew` + strap-provision
    BOM lint.
17. **Port field** → 8× FTP jacks in 2×4 gangs, SH tabs → chassis-GND stitch vias at
    each tab; per-port DETECT ladder + PESD + SS110/SMAJ58A + R_SYNC at the jack
    (sheet-05 pattern is captured — layout mirrors it); SK6812 chain between gangs,
    LED data buffered per platform. Check: existing per-port netlist assertions +
    shield-stitch presence (silk/via count advisory).
18. **Uplink isolation moat** → JXD1 MagJack line-side + Bob-Smith network + GDT
    inside a copper-free moat; **moat clearance ≥2.0 mm [wb] to ANY non-line copper**
    (2250 VDC magnetics isolation — final number pends the compliance review, gate
    below); no plane of any layer crosses the moat; RClamp0524PA on the PHY side at
    the magnetics exit; DP83869 ≤25 mm [wb] from the jack; ABM3 crystal + TLV75801
    LDOs at the PHY. ×2 mirrored for MC. Check: NEW `isolation-moat-clearance`
    (copper-to-copper across a named moat polygon) — this checker is REQUIRED before
    any hub fab. [practice I.10, I.3]
19. **eMMC (FBGA-153) + W25Q256** → H-STORAGE at the MSS side. eMMC 8-bit bus:
    DAT[7:0]/CMD length-match to CLK ±2.5 mm [wb] (HS400-capable discipline), 50 Ω SE,
    VCCQ decoupling ladder at the balls; W25Q QSPI ≤40 mm [wb]. Check: NEW
    `emmc-bus-skew` + class gates. [practice I.6]
20. **eFuse front + cascade + hold-up** → H-PWR at the rear feeds; 2× 4700 µF cans
    placed for chassis clearance + the persist-path trace to the QSPI kept short
    (tamper-log flush). Check: power-class widths + electrothermal on the 5 V trunk.
21. **ADS7830 DETECT ADC** → central to the 8 DETECT ladders, analog class runs, one
    guard pour. (Part still P3/not-ratified — capture carries it as the working
    baseline per sheet 05c.)
22. **RJ-11 sec-I/O** → rear, isolated dry-contact side of TLP172A kept clear of SELV
    pours by ≥1.5 mm [wb]; never adjacent to module ports. Check: moat checker reuse
    (smaller moat polygon).
23. **Watchdog block** → SoC reset/strap corner; its private CAN transceiver + term
    NEVER ties the platform CAN nets (separate net names asserted). Check:
    check_hub_ent_sch assertion (sheet 09) + net-isolation lint.
24. **JTAG FTSH-105 + boot straps** → interior, reachable with the lid off; straps
    grouped at their bank with DNP jumper pattern per DS60001681H.
25. **M3 chassis-GND ×4** + NTC + service button → platform patterns unchanged.

**ent-kvm-carrier (accessory board)**
26. M.2 module: standard keying/standoff mechanics; HDMI capture front-end TMDS pairs
    100 Ω diff ≤50 mm [wb]; USB-C host + TS3USB221 gate per its sheets; USB 90 Ω.
    (Its footprint cluster + T2 pass is in the intake agent's queue — rules firm up
    at that landing.)

## D. Routing standards (netclass table — seeds .kicad_pro + .kicad_dru)

| Class | Nets | Width / rules |
|---|---|---|
| BGA_Fanout | FCVG484 escape segments only | 0.10–0.13 mm track [wb] in-field, neck-out to class width at ring exit; via-in-pad Type VII on the flagged ball list, 0.25/0.5 mm dogbone elsewhere (breakout study §2) |
| SGMII | MSS SGMII lanes (uplink, MCX sync opt) | 100 Ω diff, intra-pair ±0.125 mm, unbroken reference, L4 impedance area (study condition b) |
| RGMII | LAN9370↔fabric ×2 buses | 50 Ω SE, data-vs-clock ±2.5 mm [wb]/bus, ≤60 mm [wb], no cross-bus interleave |
| T1_MDI | all T1 pairs, hub + modules | 100 Ω diff, intra ±0.5 mm, stubs ≤3 mm, chain order enforced, no plane split |
| CLK_LVDS | DSC1123 → MSS | 100 Ω diff, ±0.25 mm, ≤40 mm [wb] |
| EMMC | DAT/CMD/CLK | 50 Ω SE, ±2.5 mm to CLK [wb] |
| QSPI | W25Q + P4-flash (modules) | 0.22 mm, ≤40 mm, one-layer preference |
| USB | D± every board | 90 Ω diff, platform cell |
| CAN | CAN_H/L (+ watchdog private pair, separate nets) | 0.25 mm coupled, platform standard |
| SYNC7 | pin-7 per-port | 0.25 mm, series R at jack, ESD stub ≤3 mm |
| DETECT/Analog | DETECT ladders, rail-sense, ADC refs, NTC | guarded, ≥2 mm from switcher loops, no parallel >10 mm with Gate/CLK classes |
| PWR_5V | 5 V trunk/eFuse paths | 1.0 mm min + pour, electrothermal-gated |
| PWR_CORE | 1.0/1.05 V @7 A | POUR only, min cross-section per gate, remote-sense pair in Analog class |
| PWR_BANK | 1.8/2.5/3.3 V | 0.5 mm min + pour |
| ISO (rule, not class) | uplink moat, RJ-11 isolated side | copper-free moat, ≥2.0 mm [wb] / ≥1.5 mm [wb]; NO layer crosses |

Module boards keep their existing consumer netclass files + add T1_MDI/SYNC7/QSPI rows.
DRU seeds: the platform pour-integrity, min-pour-cross-section, kelvin-from-inner-pad
checkers ARMED unchanged on modules; hub adds the new checkers in §F.3.

## E. Stackup per board

| Board | Stackup |
|---|---|
| hub-enterprise | **6L 1.6 mm (variants-plan §5, study-verified w/ conditions)**: L1 sig/BGA fanout · L2 GND · L3 pwr (core rails) · L4 pwr/sig **with reserved controlled-impedance area (NW-reachable)** · L5 GND · L6 sig. ENIG. Via-in-pad Type VII on the flagged set. **8-layer TRIGGERS (watch, re-quote if any fires): DDR populated / MSS USB ball lands outside the shallow pool (FAE Q7) / fab refuses via-in-pad / MCX growth** |
| ENT modules (all 4 families) | platform 4L 1.6 mm, 2 oz outer/1 oz inner; cable boards keep BOTH inners GND (doctrine); 24-pin keeps its inner power-routing layer exception |
| ent-kvm-carrier | 4L 1.6 mm, In1 GND unbroken under TMDS/USB |

## F. Pipeline gates (what must pass before any ENT fab)

1. ERC 0 / DRC severity-error 0 (platform CI posture; DRAFT until every sheet passes
   SCHEMATIC-PLAN §2 — schematic gates are that file's protocol, not re-stated here).
2. `check_hub_ent_sch.py` full-hierarchy + per-sheet assertion blocks green.
3. **NEW checkers to implement (scripts/cec_constraints rows) — the hub's fab is
   GATED on the starred ones:**
   - ★ `isolation-moat-clearance` (uplink + RJ-11 moats, copper-to-copper across polygon)
   - ★ `bga-escape-completeness` + `via-in-pad-zone` (flag-list ↔ fab-notes match)
   - ★ `t1-mdi-chain-order` (hub ports ×8 + every module)
   - `misplug-chain-order` (modules)
   - `rgmii-bus-skew`, `emmc-bus-skew`, diff-pair skew per class
   - `pin7-conditioning-presence` (ENT boards)
   - detect-resistor-code: ENT 10 kΩ row (extend existing)
   - watchdog private-CAN net-isolation lint
4. Electrothermal gate: hub 5 V trunk + 1V0@7 A pour + LAN9370/DP83869 dissipation
   [wb ~1 W + ~0.6 W each] under the enclosed-chassis model; module gates unchanged.
5. Fab-class gate: 6L ENIG + via-in-pad is a NEW vendor capability — quote + capability
   confirmation BEFORE layout freeze (cost note already in the spec sheet).
6. Stage-1 REQUIREMENTS answers (recorded here so the pipeline doesn't re-ask):
   radio-free everywhere → NO antenna keepouts on any ENT board; thermal_env =
   enclosed/passive [wb — chassis study owed]; placement_handoff_mode = hand-off
   (GUI finish legitimate); connector overhang = jacks may overhang their edges per
   platform practice; mounts = 4× M3 chassis-grounded (hub), module patterns unchanged.
7. AIR-build silk gate: unpopulated uplink land must remain self-describing (refs +
   "AIR: not populated" fab note) — the inspection story is a deliverable.

## G. Mechanical / assembly interface rules

- Edge map is BINDING (variants-plan §4): front = 8 ports; rear = uplink(s) + RJ-11 +
  USB-C + EXT + JST feeds; interior = KVM aux/JTAG/straps. Uplink bezel blue + silk
  distinct; RJ-11 color-distinct and physically separated from module ports.
- Port-gang pitch to the chassis drawing; SH tabs chassis-stitched.
- Hold-up cans: height + clearance vs lid; persist-path service note.
- ENT modules: identical mechanicals to their consumer siblings (same mounting, same
  connector positions — the ENT build is a population/BOM lineage, not a re-floorplan),
  EXCEPT the T1 front-end zone claims the pair-2 area that consumer boards leave dark.
- kvm-carrier: M.2 standoff + HDMI/USB edge per its README when the footprint cluster
  lands.

## H. Per-board deltas

- **hub-enterprise**: full §C.11–25; SKU deltas are DNP population per the variants-plan
  §6 matrix (never copper variants); MCX adds the mirrored 2nd-SoC region + sync lane
  (captured last, plan rule).
- **atx-24pin ENT**: consumer rev3 doctrine + Z-T1/Z-MISPLUG/Z-P4 + DETECT 10 kΩ;
  sensing corridors untouched (INA228 + §6.4 shunts); mezzanine header per OQ-77.
- **eps-8pin / pcie ENT**: + ADS131M08 rule §C.9; T1 stream is the fast path — MDI zone
  gets priority over the USB edge if they contend.
- **12vhpwr ENT**: the Pro board carries most of this already; apply Z-T1/Z-MISPLUG +
  DETECT 10 kΩ + REF3033 rule; per-pin lanes/Kelvin per the existing 12VHPWR doctrine.
- **ent-kvm-carrier**: §C.26; firm up at footprint-cluster landing.

## I. Industry best practices — routing + placement, with citations (owner add, 2026-07-16)

Each practice below is the EXTERNAL grounding for a rule in §C/§D/§E — cited so the
pipeline (and any reviewer) can check the rule against its source rather than trusting
this sheet. Standards are cited by number (purchase/library docs); vendor guides by
document ID with public URLs where verified live.

**I.1 BGA fanout + via-in-pad — IPC-7095 / IPC-4761 / Microchip UG series.**
IPC-7095 (Design and Assembly Process Implementation for BGAs) is the governing
practice for §C.11's escape strategy: dogbone fanout as the default at ≥0.8 mm pitch,
via-in-pad only where escape depth forces it, and then ONLY filled+capped per IPC-4761
Type VII (unfilled via-in-pad wicks solder and voids the joint). Microchip's own board
guides bind the part-specific rules: **UG0726 PolarFire FPGA Board Design User Guide**
(decoupling ladders "must be strictly followed", supply topologies, high-speed banks —
<https://ww1.microchip.com/downloads/aemDocuments/documents/FPGA/ProductDocuments/UserGuides/PolarFire_FPGA_Board_Design_UG0726_V11.pdf>)
and the SoC-specific **PolarFire SoC FPGA Board Design Guidelines**
(<https://ww1.microchip.com/downloads/aemDocuments/documents/FPGA/ProductDocuments/UserGuides/PolarFire_SoC_FPGA_Board_Design_Guidelines_User_Guide_VB.pdf>)
— sheet-02/03 capture and the H-BGA decoupling field take THESE as authority over any
generic rule here.

**I.2 Controlled impedance + differential pairs — IPC-2141A / Bogatin.** Impedance
targets and coupled-pair geometry per IPC-2141A (Design Guide for High-Speed Controlled
Impedance Circuit Boards); the working doctrine for §D's intra-pair match numbers and
"length-match what matters, not everything" is Bogatin, *Signal and Power Integrity —
Simplified* (3rd ed.): match to a fraction of the signal rise-time budget, don't
serpentine for cosmetic equality.

**I.3 Return paths and plane discipline — Ott.** "No plane split under a diff pair or
any high-speed SE bus" (§C.1, §C.15, §C.16, §D rows) is the return-current rule from
Ott, *Electromagnetic Compatibility Engineering* (Wiley 2009), ch. 16–17: the return
flows directly under the trace at HF; a split forces a loop and radiates. This is also
why the isolation moats (§C.18) must be honest voids — a moat a plane sneaks across is
an EMC antenna AND an isolation failure.

**I.4 100BASE-T1 MDI — IEEE 802.3bw clause 96 + OPEN Alliance TC-8 + TI layout
guidance.** The single-pair MDI channel/return-loss budget comes from 802.3bw (100 Ω
differential) with conformance test classes per OPEN Alliance TC-8; TI's DP83TC81x
datasheet layout-guidelines section is the applied practice §C.1–3 encodes: protection
and CMC in a straight chain at the connector, ESD stubs minimized, coupling caps
matched, no plane voids under the pair. (LAN9370-side: same electrical class; Microchip
full-DS layout section is the pending authority — owner-queue watch item.)

**I.5 RGMII — the RGMII v2.0 specification.** 50 Ω SE, source-synchronous bus with a
1.5–2.0 ns clock-to-data window; internal-delay (ID) mode moves the skew budget
on-chip, which is what makes §D's ±2.5 mm [wb] bus tolerance sane rather than heroic.
Verify the LAN9370's ID-mode straps against the full DS before freezing the number
(§J.2).

**I.6 eMMC — JEDEC JESD84-B51 + manufacturer design notes.** HS400 DDR timing at
200 MHz sets the CLK-referenced match class in §C.19/§D; JESD84-B51 is the electrical
authority; manufacturer hardware-design notes (Micron's e.MMC TN-52 family; the chosen
vendor's equivalent at MPN lock) carry the applied VCCQ decoupling + routing ladders.

**I.7 LVDS clocking — TI SLLD009.** The *LVDS Owner's Manual* is the practice source
for §C.15: 100 Ω pair, terminate at the receiver, reference-plane continuity,
length-match within the class table — a clock pair's jitter budget is mostly layout.

**I.8 USB 2.0 — USB-IF spec ch. 7.** 90 Ω ±15 % differential, common-mode choke only
if needed at compliance, no series ferrites on D± (already platform doctrine §6.14).

**I.9 CAN — TI SLLA270.** Stub-length and topology discipline for the shared bus
(§C.10, hub 05b split termination) per TI's *Controller Area Network Physical Layer
Requirements* application report — short stubs off the through-bus, single split
termination at the Hub (platform-locked, §3.1).

**I.10 Ethernet magnetics isolation — IEEE 802.3 §25/§33 isolation requirement +
IPC-2221B spacing.** The 1500 Vrms (here 2250 VDC part rating) magnetics barrier is an
IEEE 802.3 electrical-isolation requirement; the physical clearance/creepage across the
§C.18 moat derives from IPC-2221B Table 6-1 (B2/B4 columns) — the ≥2.0 mm [wb] figure
sits above the table's uncoated-external requirement for the working voltage class and
is finalized at the compliance review (§J.4). Bob-Smith termination network per the
MagJack vendor's application guidance (Pulse), kept line-side of the moat.

**I.11 ESD protection placement — IEC 61000-4-2 + protection-vendor guidance.** TVS/ESD
arrays as close as the pad geometry allows to the CONNECTOR (not the protected IC),
stub inductance minimized (§C.1's ≤3 mm stub; PESD/SMAJ/RClamp rows) — the discharge
must divert before it propagates; per Nexperia/Semtech datasheet placement guidance and
the platform's existing pin-8 ESD pattern (§2.4 locked).

**I.12 Current-sense Kelvin layout — TI INA24x/INA228/INA238 datasheet layout
sections.** Sense taps from the shunt's inner pad edges, matched symmetric traces, no
load current in the sense path, filter at the amplifier — §C.8's platform doctrine
(§6.8) matches TI's published layout guidelines for the exact parts used; the existing
kelvin checkers ARE this practice mechanized.

**I.13 Buck-converter loop placement — vendor datasheet layout sections (MIC22705 /
MPM3833C / TLV62569).** Minimize the hot switching loop (VIN cap → FET → catch path),
keep the FB/sense divider out of the loop and away from the inductor's fringe field,
remote-sense at the load for the 7 A core rail (§C.12–13). The MPM3833C's integrated
inductor shrinks but does not remove the loop rule.

**I.14 Conductor sizing + thermals — IPC-2152 (supersedes IPC-2221 charts for
current).** The electrothermal gate's copper-cross-section math (§F.4) keys to
IPC-2152 data as the platform already does (corpus Class A anchors); this sheet adds no
new thermal doctrine, only the hub's dissipation inventory (§J.7).

**I.15 MCU core layout — Espressif ESP32-P4 hardware design guidelines.** The Z-P4
zone rules (flash proximity, USB routing, decoupling, no antenna keepout on the
radio-free P4) defer to Espressif's published P4 hardware-design-guidelines document as
part authority at capture — same pattern as the platform's S3/C6 boards.

**I.16 Placement flow doctrine (zones-before-parts).** §B's airflow/signal-flow zoning
— connectors at edges by role, noisy power isolated from analog sense, protection at
entry points, one-direction power flow — is the composite of IPC-2221B §placement
guidance and the practices above; it is also exactly the platform's proven condensed-
board method (EPS/PCIe/12VHPWR), so the pipeline's corridor/keepout mechanism enforces
it the same way here.

## J. Open items on this sheet

1. Every **[wb]** number above — freeze at layout kickoff with a dated edit here.
2. LAN9370 full-DS gaps (straps, RGMII internal-delay/skew budget, thermal) — portal
   watch item in owner-queue; LAN9371/72 family docs are the proxy.
3. FAE answers feed §C.11/§E: Q7 MSS USB ball, SGMII-vs-RGMII uplink pin option.
4. Isolation moat final numbers vs the compliance review (2250 VDC magnetics + RJ-11) —
   ★ gate 3 checker ships with the [wb] values until then.
5. DETECT ADC ratification (ADS7830 is working-baseline, P3).
6. eMMC MPN (intake agent in flight 2026-07-16) + S32K watchdog MPN (owner gate).
7. Enclosed-chassis thermal study (MPFS + 2× LAN9370 + PHY dissipation) → gate 4 model.
8. New-checker implementations (gate 3 list) → cec_constraints rows + teeth tests.
9. MPFS FCVG484 3D STEP not vendored (cosmetic; Microchip may publish one).
