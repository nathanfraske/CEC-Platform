## BOM-B: GbE uplink — detailed table

Research conducted 2026-07-02 via direct WebFetch of manufacturer datasheets/schematics (TI DP83869HM datasheet SNLS614E rev. April 2026; Microchip VSC8662 datasheet VMDS-10312 Rev 4.3; **Microchip's own current PolarFire SoC Icicle Kit reference schematic**, read page-by-page) and live distributor pages (DigiKey, LCSC, Mouser). All prices are 100-piece, dated 2026-07-02.

| Ref-class | Qty/uplink | Value/Function | MPN | Mfr | Package | Unit@100q [2026-07-02] | Datasheet | Notes (population) |
|---|---|---|---|---|---|---|---|---|
| **PHY** |
| U1 | 1 | GbE PHY, SGMII↔copper, **PRIMARY** (promoted from fallback — see verdict below) | **DP83869HMRGZR** | Texas Instruments | VQFN-48 (RGZ), 7×7mm | **$7.98** (DigiKey) | [dp83869hm.pdf](https://www.ti.com/lit/ds/symlink/dp83869hm.pdf) | NET-B ×1 / NET-MC+ ×2 / AIR ×0 |
| — | (0) | GbE PHY, dual-port SGMII↔copper, **historical primary — NOT populated, kept for record only** | VSC8662XIC-03 | Microchip (ex-Vitesse/Microsemi) | 256-ball BGA, 17×17mm | $22.44 @25pc — **no 100pc break offered** | [VMDS-10312.pdf](https://ww1.microchip.com/downloads/en/DeviceDoc/VMDS-10312.pdf) | **DO NOT USE** — see verdict |
| **PHY power support (2-supply mode: skip the optional 1.8V VDDA1P8 rail entirely, per TI's own recommendation)** |
| U2 | 1 | LDO, adjustable, set to 1.1V (VDD1P1 core) via FB divider | **TLV75801PDBVR** | Texas Instruments | SOT-23-5 (SC-74A) | $0.1644 | [tlv758p.pdf](https://www.ti.com/lit/ds/symlink/tlv758p.pdf) | all populated SKUs |
| U3 | 1 | LDO, adjustable, set to 2.5V (VDDA2P5 analog) via FB divider — same part as U2 for one-SKU kitting | **TLV75801PDBVR** | Texas Instruments | SOT-23-5 (SC-74A) | $0.1644 | same as above | all populated SKUs; fixed-output alt: Diodes Inc **AP2112K-2.5TRG1**, SOT-25, ~$0.23 (qty tier not independently re-confirmed) [unverified qty break] |
| R1,R2 | 2 (1 pair/LDO) | FB divider resistors, 0402 1% | *TBD at layout — value from TI's LDO design-tool for 1.1V/2.5V outputs* | — | 0402 | negligible | — | [open — layout task] |
| C1–C7 | 7 (1/VDD pin) | 0.1µF, X7R, decoupling (closest to pin per TI layout note) | **CL05B104KO5NNNC** | Samsung | 0402 | ~$0.003 (platform std) | — | LCSC **C1525** — reused platform-standard part |
| C8–C14 | 7 (1/VDD pin) | 1µF, X7R, decoupling | **CC0603KRX7R8BB105** | Yageo | 0603 | ~$0.012 | [LCSC datasheet](https://datasheet.lcsc.com/lcsc/2409272231_YAGEO-CC0603KRX7R8BB105_C106858.pdf) | LCSC C106858 |
| C15–C17 | 3 (1/rail entry) | 10µF, X7R, bulk | **TCC0805X7R106K160FT** | CCTC | 0805 | ~$0.03 [directional] | — | LCSC C380347 |
| C18–C20 | 3 (1/rail entry) | 10nF, X7R, bulk (paired w/ above) | **CC0402KRX7R9BB103** | Yageo | 0402 | $0.0004 | — | LCSC C60133 |
| **PHY bias / clock / strap** |
| R3 | 1 | RBIAS, 11kΩ ±1% (RBIAS pin → GND, per datasheet Table 5-1) | **RC0402FR-0711KL** | Yageo | 0402 | $0.0005 | — | LCSC C138063 |
| Y1 | 1 | 25MHz crystal (XI/XO pins; datasheet: "25MHz oscillator or crystal input," ±100ppm ceiling) | **ABM3-25.000MHZ-B2-T** | Abracon | SMD 5.0×3.2mm, 2-pad | $0.7005 | [DigiKey listing](https://www.digikey.com/en/products/detail/abracon-llc/ABM3-25.000MHZ-B2-T/535-9108-1-ND/675625) | ±20ppm — comfortably clears spec |
| C21,C22 | 2 | 18pF C0G/NP0 crystal load caps | **GRM1555C1H180JA01D** | Murata | 0402 | $0.0011 | — | LCSC C33149 |
| R4 | 1 | MDIO_0/1 pull-up, 1.5kΩ ±1% (datasheet-specified value) | Yageo RC0402FR-07-1K5L pattern | Yageo | 0402 | negligible | — | value confirmed from datasheet; **exact LCSC# not individually re-verified this pass [unverified SKU]** |
| R5 | 1 | INT_N/PWDN_N pull-up, 2.2kΩ recommended to VDDIO | Yageo RC0402FR-07-2K2L pattern | Yageo | 0402 | negligible | — | **[unverified SKU]**, same caveat as R4 |
| R6,C23 | 1+1 | RESET_N power-on-reset RC: 100Ω series + 47µF to GND | *TBD* | — | 0402 / 0805-1206 | negligible | — | value from datasheet; **[unverified exact MPN]** — layout-stage sourcing |
| R7 | 1 | Unused-strap pulldown, 10kΩ ±1% (per pin as needed) | **0402WGF1002TCE** | UNI-ROYAL | 0402 | ~$0.001 (platform std) | — | LCSC C25744 — reused platform-standard part |
| **Magnetics / jack** |
| J1 | 1 | Integrated shielded GbE MagJack w/ 2 LEDs, built-in Bob-Smith network | **JXD1-0001NL** | Pulse Electronics (Yageo Group) | THT, right-angle, shielded, Tab-Up | **$5.95** (DigiKey 553-3266-ND) | [Pulse datasheet](https://productfinder.pulseelectronics.com/api/open/part-attachments/datasheet/jxd1-0001nl) | NET-B ×1 / NET-MC+ ×2 / AIR ×0. Isolation **2250 VDC** (>1500Vrms floor w/ real margin — see caveat below). 2nd source: Halo **HFJ11-1G01E-L12RL** ($5.01@100, 3103pc stock, but exactly at the 1500Vrms floor) |
| **Bob-Smith termination (reference MPNs only — DO NOT POPULATE separately; built into J1)** |
| R8–R11 | 0 (ref) | 75Ω ±1%, Bob-Smith common-mode network | **RC0402FR-0775RL** | Yageo | 0402 | $0.0097 | — | LCSC C114757. **DNP** — internal to J1 |
| C24 | 0 (ref) | 1nF, 2kV, X7R, Bob-Smith safety cap | **C1206C102KGRACTU** | Kemet | 1206 | $0.5067 | [Kemet HV X7R](https://content.kemet.com/datasheets/KEM_C1010_X7R_HV_SMD.pdf) | **DNP** — internal to J1. Higher-margin alt (3kV, verified in Microchip's own Icicle Kit BOM): Johanson **302S43W102KV4E**, LCSC C3833519, ~$0.106 |
| **Protection** |
| U4,U5 | 2 (covers 4 pairs/8 lines) | Low-C TVS array, 4 I/O lines/pkg, differential-pair, PHY-side of magnetics | **RClamp0524PA.TCT** | Semtech | DFN-10 (SLP2510P8) | $0.0532 ea | [Semtech RClamp0524PA](https://www.semtech.com/products/circuit-protection/low-capacitance/rclamp0524pa) | 0.30pF/line, ±17kV air/±12kV contact. LCSC C40960. Active successor to obsolete RClamp0524P — **do not spec the base part** |
| GDT1 | 1 | 3-electrode SMD GDT, shield→chassis earth | **2038-15-SM-RPLF** | Bourns | SMD, 3-pole cylinder | $1.5154 | [Bourns 2038-xx-SM](https://www.bourns.com/docs/Product-Datasheets/2038-xx-SM.pdf) | 150V spark-over, 5kA (8/20µs), <1pF. LCSC C720636 (~$0.84, cross-distributor spread). Alt: CITEL BMSQ CMS 90/20 (90V) — LCSC stock gap flagged |
| **LEDs** |
| — | 0 | Link/activity indication | — | — | — | — | — | **No discrete parts needed** — confirmed integrated (G/Y) into J1's magjack module |

---

### Per-uplink cost roll-up (100pc, real verified prices)

| Group | Cost |
|---|---|
| PHY (DP83869HMRGZR) | $7.9800 |
| MagJack (JXD1-0001NL) | $5.9500 |
| GDT (2038-15-SM-RPLF) | $1.5154 |
| 25MHz crystal + load caps | $0.7027 |
| 2× LDO (TLV75801PDBVR) | $0.3288 |
| 2× TVS array (RClamp0524PA) | $0.1064 |
| Decoupling + bulk caps (~20 pcs) | ~$0.19 |
| RBIAS + strap/pulldown resistors | ~$0.01 |
| **Total (Bob-Smith not separately populated — built into J1)** | **≈ $16.78/uplink** |

This is meaningfully above the working spec sheet's placeholder ("$6–14/uplink," §3.B) and the Phase-2 survey's SGMII-vendor-matched estimate ("≈$6.40–14.00"). The gap is almost entirely two now-*verified* (not guessed) prices: the MagJack ($5.95 real vs. $1.50–3.00 guessed) and the GDT ($1.52 real vs. bundled into a $0.60–1.40 combined-protection guess). **Recommend the owner update the spec sheet's §3.B placeholder figures to this verified range at the next revision** — this is a pricing-accuracy correction, not a scope change.

MC/MC-Max note: because the PHY swap below eliminates the dual-port chip, the "×2" on MC+ is a **literal full duplication of every row in this table** (2 discrete PHYs, each needing its own MDIO/PHY address and SGMII lane pair from the PolarFire SoC), not "1 shared PHY + 1 extra magjack" as the VSC8662 dual-port plan would have allowed — flag for whoever integrates subsystem A (compute) with this subsystem.

---

### Primary-vs-fallback PHY note — VSC8662 lifecycle verdict

**VSC8662 sourcing is dead for a new design. DP83869HM is promoted to primary**, per the task's own explicit instruction for this condition. Evidence, strongest first:

1. **Smoking gun, primary source**: Microchip's own *current* PolarFire SoC Icicle Kit reference schematic (`PolarFire_SoC_ICICLE_KIT_Schematics0725.pdf`, DVP-102-000536-001 Rev 1.0) — the exact reference design the Phase-2 survey cited as justification for choosing VSC8662 — prints, verbatim, directly on the VSC8662 schematic block: *"VSC8662XIC is not UNH compliant for all tests"* and *"Not recommended for new design. Please use VSC8552."* Microchip is telling its own reference-design customers not to design this part into new boards.
2. **Real distributor data** (independently confirmed by both my own direct DigiKey fetch and the dedicated research agent): "Active" lifecycle label, but only 50–52 units in stock, no backorders accepted ("temporary constrained supply"), **no 100-piece price break offered by any distributor**, RS Components/Farnell carry it at all, and the datasheet (VMDS-10312) hasn't been revised since **April 2019** — vs. DP83869HM's datasheet, revised as recently as **April 2026**.
3. **Price reality**: $22–30 at 1–25pc — 3–5× the survey's original "$4–9 [unverified]" guess, and still not sold at BOM-relevant volume.
4. A closely related sibling, VSC8541XMV-01, is independently confirmed **Obsolete** with a DigiKey substitute link — the exact risk the original survey flagged, now proven to extend to VSC8662 itself.
5. Microchip's own suggested migration part, **VSC8552** (VSC8552XKS family), was checked and does *not* fix the underlying problem — same 256-BGA Vitesse/Microsemi-heritage silicon generation, similarly priced (~$20–25). This is flagged as an **open item for owner awareness**, not silently adopted as a replacement (re-deriving the dual-port SGMII architecture is out of this BOM's scope).

DP83869HM by contrast: Active, 1,439 units in stock, $7.98@100pc, actively-maintained datasheet, and — a bonus finding not asked for — its real qualified temp range is **−40°C to +125°C**, wider than the task brief's assumed −40 to 85°C.

**One correction surfaced along the way**: the task assumed a 25MHz reference clock for "the" PHY. That's correct for **DP83869HM** (confirmed directly from its datasheet: "25MHz oscillator or crystal input," XI/XO pins). It would have been *wrong* for VSC8662 specifically — the real Icicle Kit design feeds VSC8662 a **125MHz** active oscillator (Microchip DSC1123BL5-125.0000 MEMS XO) via its high-speed reference-clock mode, not a 25MHz crystal — moot now that VSC8662 isn't the pick, but worth recording so the historical row above isn't a source of confusion later.

---

### Open items

1. **FB-divider resistor values** for U2/U3 (TLV75801PDBVR set to 1.1V/2.5V) — needs TI's adjustable-LDO design-tool output at layout time; not fabricated here.
2. **R4/R5 exact LCSC SKUs** (1.5kΩ MDIO pull-up, 2.2kΩ INT_N/PWDN_N pull-up) — datasheet-confirmed values, but I did not individually re-verify a specific distributor SKU for these two exact resistances this pass (the Yageo RC0402FR-07-xxx series they'd come from is confirmed real and in-stock for half a dozen *other* values used elsewhere in this BOM).
3. **RESET_N RC network** (100Ω + 47µF) — value is datasheet-specified, exact MPNs not sourced.
4. **MagJack stock depth**: JXD1-0001NL shows only 400 units at DigiKey (vs. 2,400–3,100+ for the two runner-up candidates) — comfortable for a 100pc BOM run but worth a distributor conversation before scaling to a larger production quantity. Halo HFJ11-1G01E-L12RL is the strongest deep-stock second source if that becomes a constraint.
5. **GDT voltage** (150V Bourns, mainstream-stocked, vs. 90V CITEL, closer to literature-typical but currently stock-constrained at LCSC and absent from DigiKey/Mouser) — owner call if 90V margin is specifically wanted.
6. **SGMII AC-coupling** on the copper-side trace between DP83869HM and the PolarFire SoC's MSS-SGMII pins — TI's datasheet only shows AC-coupling caps for the fiber/SFP-facing side; whether the same is needed board-side is a subsystem-A/B integration question, not resolved here.
7. **CDSOD323 / RClamp0524P / RClamp0554P**, as originally named in the task brief, were checked and found to be either wrong-shaped (single-channel, not an array) or non-existent/obsolete exact SKUs — corrected to RClamp0524PA above; flagging so the correction isn't silently lost.
8. Per this platform's CLAUDE.md conventions, PESD5V0S1BA-class per-pin DETECT protection and the platform CAN/DETECT scheme are **module-interface (§2.1–2.4) concerns, not this uplink port** — this uplink is genuine IEEE 802.3 Ethernet, deliberately out of scope here (see the survey's "confusion-proofing" section on why the two RJ-45 families on this board must not be conflated).

### Sources

- [DP83869HM datasheet SNLS614E (TI, rev. April 2026)](https://www.ti.com/lit/ds/symlink/dp83869hm.pdf)
- [DP83869HMRGZR — DigiKey](https://www.digikey.com/en/products/detail/texas-instruments/DP83869HMRGZR/10448297)
- [VSC8662 datasheet VMDS-10312 Rev 4.3 (Microchip)](https://ww1.microchip.com/downloads/en/DeviceDoc/VMDS-10312.pdf)
- [VSC8662XIC-03 — DigiKey](https://www.digikey.com/en/products/detail/microchip-technology/VSC8662XIC-03/6131497)
- [PolarFire SoC Icicle Kit Schematics, Rev 1.0 (Microchip, primary source for the NRND finding + real VSC8662 support-circuit values)](https://ww1.microchip.com/downloads/aemDocuments/documents/FPGA/ProductDocuments/BoardDesignFiles/PolarFire_SoC_ICICLE_KIT_Schematics0725.pdf)
- [TLV758P datasheet (TI)](https://www.ti.com/lit/ds/symlink/tlv758p.pdf)
- [Pulse JXD1-0001NL datasheet](https://productfinder.pulseelectronics.com/api/open/part-attachments/datasheet/jxd1-0001nl)
- [Halo HFJ11-1G01E-L12RL family — Halo Electronics](https://www.haloelectronics.com/pdf/fastjack-gigabit.pdf)
- [Bel Fuse 0826-1G1T-23-F](https://www.belfuse.com/products/ethernet/magjacks-icms/0826-1g1t-23-f)
- [Semtech RClamp0524PA](https://www.semtech.com/products/circuit-protection/low-capacitance/rclamp0524pa)
- [Bourns 2038-xx-SM 3-electrode GDT datasheet](https://www.bourns.com/docs/Product-Datasheets/2038-xx-SM.pdf)
- [Kemet High-Voltage X7R MLCC datasheet](https://content.kemet.com/datasheets/KEM_C1010_X7R_HV_SMD.pdf)
- Internal grounding: `/home/user/CEC-Platform/docs/enterprise-requirements/spec-sheets/hub-ent-spec-sheet.md` §3.B, `/home/user/CEC-Platform/docs/enterprise-requirements/research/phase2/survey-2-ethernet-uplink.md`, `/home/user/CEC-Platform/docs/enterprise-requirements/hub-enterprise-requirements.md` (REQ-HUB-NET-030/031, REQ-HUB-AIR-024)
