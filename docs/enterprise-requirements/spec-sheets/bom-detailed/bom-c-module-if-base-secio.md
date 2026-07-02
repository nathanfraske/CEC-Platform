## BOM-C: Module interface + platform base + security I/O

Working-baseline detailed BOM for the CEC ENT Hub (PolarFire MPFS095TS, 8 module ports). Reused rows carry the exact LCSC part already validated on `hubs/hub-standard/bom/bom.csv`; new rows were verified this session against live LCSC listings. Status matches the parent doc: DRAFT, pre-schematic — this supersedes nothing until a real `.kicad_sch` exists for this board.

### 1. Module ports (×8, all SKUs)

| Ref-class | Qty | Value/Function | MPN | Mfr | Package | Unit@100q | Datasheet / LCSC | Notes |
|---|---|---|---|---|---|---|---|---|
| J_PORT1–8 | 8 | RJ-45 8P8C FTP, module port, SH1/SH2→GND | KH-RJ45-58-8P8C | Kinghelm | RJ45_FTP_Shielded_Horizontal | $0.60 | [LCSC C2683360](https://lcsc.com/product-detail/C2683360.html) | Platform-reuse = hub-standard J2–J5; §2.1 lock |
| R_DET1–8 | 8 | 10 kΩ, DETECT pull-up to 3V3 | 0402WGF1002TCE | UNI-ROYAL | 0402 | ~$0.005 [directional] | [LCSC C25744](https://www.lcsc.com/product-detail/C25744.html) | Platform-reuse = hub-standard R2 etc.; §2.3 code table |
| D_DET1–8 | 8 | PESD5V0S1BA, DETECT pin-8 ESD clamp | PESD5V0S1BA | Nexperia | SOD-323 | $0.03 | [LCSC C5261083](https://www.lcsc.com/product-detail/C5261083.html) | Platform-reuse = hub-standard D2–D5; §2.4 LOCKED |
| — | 8 | Per-port 5VSB distribution | (no part) | — | — | $0.00 | — | Direct RJ-45 VCC tap per §2.7 lock, no per-port limiting populated by default |
| *F_5VSB1–8 (option)* | *8* | *0.5 A hold / 1 A trip PPTC, per-port 5VSB* | *SMD0805-050/06N* | *BORN* | *0805* | *$0.0358* | *[LCSC C2687883](https://www.lcsc.com/datasheet/C2687883.pdf)* | *NOT populated by default — see Open Items* |

Subtotal (populated): **≈ $5.08**

### 2. CAN front end (×1, all SKUs)

| Ref-class | Qty | Value/Function | MPN | Mfr | Package | Unit@100q | Datasheet / LCSC | Notes |
|---|---|---|---|---|---|---|---|---|
| U_CAN | 1 | TJA1051T/3, classical CAN transceiver, VIO=3.3V | TJA1051T/3 | NXP | SOIC-8 | $0.40 | [LCSC C38695](https://www.lcsc.com/product-detail/C38695.html) | Platform-reuse = hub-standard U2; §3.1 LOCKED, 500k floor |
| R_CANT1/2 | 2 | 60.4 Ω, split termination | GR0402F60R4TAG00 | Viking Tech | 0402 | ~$0.02 | [LCSC C49654185](https://www.lcsc.com/product-detail/C49654185.html) | Platform-reuse = hub-standard R3/R4; 120.8Ω differential |
| C_CANT | 1 | 4n7, split-termination center cap | 0402B472K500NT | Fenghua | 0402 | ~$0.01 | [LCSC C1538](https://www.lcsc.com/product-detail/C1538.html) | Platform-reuse = hub-standard C7 |
| C_CANVCC/VIO | 2 | 100 nF, U_CAN VCC + VIO decoupling | CL05B104KO5NNNC | Samsung | 0402 | ~$0.004 | [LCSC C1525](https://www.lcsc.com/product-detail/C1525.html) | Platform-reuse pattern |

Subtotal: **≈ $0.46**

### 3. ~~RS-485 streaming receivers~~ — SUPERSEDED by survey 10 (T1-only, REQ-043)

_This section is retained for provenance only: the RS-485 receiver bank was DELETED from
the design when survey 10 resolved the module link to 100BASE-T1-only (2× LAN9370, priced
in the master BOM §5, which already subtracts this bank). OQ-5 is moot for the ENT hub.
Do not sum this subtotal into the SKU totals — the master's reconciliation governs._

| Ref-class | Qty | Value/Function | MPN | Mfr | Package | Unit@100q | Datasheet / LCSC | Notes |
|---|---|---|---|---|---|---|---|---|
| U_RS1–8 | 8 | Half-duplex RS-485/422 transceiver, receive-only (RE tied active, DE tied inactive) | THVD1450DR | Texas Instruments | SOIC-8 | **$0.6009** [VERIFIED LCSC qty100] | [TI PDF](https://www.ti.com/lit/ds/symlink/thvd1450.pdf) / [LCSC C2671361](https://www.lcsc.com/product-detail/C2671361.html) | NEW. 3.3–5.5V, ±18kV IEC ESD on bus pins, true receiver fail-safe (offset thresholds). One per port = the OQ-5 point-to-point baseline |
| R_RST1–8 | 8 | 120 Ω, line termination at Hub (far end from module driver) | 0402WGF1200TCE | UNI-ROYAL | 0402 | ~$0.005 | [LCSC C25079](https://jlcpcb.com/partdetail/25822-0402WGF1200TCE/C25079) | NEW value, same UNI-ROYAL 0402WGF family already qualified platform-wide |
| R_RSB1–16 | 16 | 10 kΩ ×2/port, weak external fail-safe bias (A pull-up / B pull-down) | 0402WGF1002TCE | UNI-ROYAL | 0402 | ~$0.005 | [LCSC C25744](https://www.lcsc.com/product-detail/C25744.html) | Platform-reuse part; belt-and-suspenders on top of THVD1450's internal fail-safe (defends a genuinely disconnected/floating module cable) |

Subtotal: **≈ $4.93** (topology-contingent — see Open Items)

### 4. Platform base (all SKUs unless noted)

| Ref-class | Qty | Value/Function | MPN | Mfr | Package | Unit@100q | Datasheet / LCSC | Notes |
|---|---|---|---|---|---|---|---|---|
| DL1–7 | 7 | SK6812MINI-E status LED chain | SK6812MINI-E | Opsco | PLCC4 3.5×3.5mm | ~$0.15 [directional] | [LCSC C5149201](https://www.lcsc.com/product-detail/C5149201.html) | Platform-reuse = hub-standard DL1–7 |
| C_DL1–7 | 7 | 100 nF, per-LED decoupling | CL05B104KO5NNNC | Samsung | 0402 | ~$0.004 | [LCSC C1525](https://www.lcsc.com/product-detail/C1525.html) | Platform-reuse |
| U_LVL | 1 | SN74AHCT1G08, 3.3V→5V LED data buffer | SN74AHCT1G08DBVR | TI | SOT-23-5 | ~$0.08 [directional] | [LCSC C113521](https://www.lcsc.com/product-detail/C113521.html) | Platform-reuse = hub-standard U6 |
| R_LED | 1 | 330 Ω, LED data series R | 0402WGF3300TCE | UNI-ROYAL | 0402 | ~$0.005 | [LCSC C25104](https://www.lcsc.com/product-detail/C25104.html) | Platform-reuse = hub-standard R14 |
| J_USB | 1 | USB-C receptacle, sensing/provisioning (NET) / primary local (AIR) | U262-16XN-4BVC11 | XKB | USB-C 16P | ~$0.40 [directional] | [LCSC C2765186](https://www.lcsc.com/product-detail/C2765186.html) | Platform-reuse = hub-standard J_USB; REQ-HUB-COMMON-032 |
| D_ESD_USB | 1 | USBLC6-2SC6, USB D+/D- ESD array | USBLC6-2SC6 | UMW | SOT-23-6 | ~$0.10 [directional] | [LCSC C2687116](https://www.lcsc.com/product-detail/C2687116.html) | Platform-reuse = hub-standard D6 |
| R_CC1/2 | 2 | 5.1 kΩ, USB-C CC1/CC2 pulldowns | 0402WGF5101TCE | UNI-ROYAL | 0402 | ~$0.005 | [LCSC C25905](https://www.lcsc.com/product-detail/C25905.html) | Platform-reuse |
| SW_RESET | 1 | Tactile switch → **DEVRST_N** (PolarFire hard reset) | TS-1088-AR02016 | XUNPU | SMD 4×3mm | ~$0.035 | [LCSC C720477](https://lcsc.com/product-detail/C720477.html) | Platform-reuse part, **rewired**: direct analog of ESP32 EN — see Open Items |
| SW_USER | 1 | Tactile switch → spare MSS GPIO (repurposed BOOT footprint) | TS-1088-AR02016 | XUNPU | SMD 4×3mm | ~$0.035 | [LCSC C720477](https://lcsc.com/product-detail/C720477.html) | Platform-reuse part, **function reassigned** — NOT a boot-mode strap on PolarFire — see Open Items |
| J_KVM | 1 | NanoKVM aux header (UART+5V+GND+3V3ref) | S5B-PH-K-S(LF)(SN) | JST | JST-PH 1×5 RA | ~$0.05 [directional] | [LCSC C157923](https://www.lcsc.com/product-detail/C157923.html) | Platform-reuse = hub-standard J_KVM. Header populated **all SKUs**; the NanoKVM daughter-module itself is NET-only (REQ-HUB-AIR-059), out of this BOM |
| R_KVMTX/RX | 2 | 33 Ω, UART series R into MSS UART | 0402WGF330JTCE | UNI-ROYAL | 0402 | ~$0.005 | [LCSC C25105](https://www.lcsc.com/product-detail/C25105.html) | Platform-reuse |
| R_KVM47k ×2 | 2 | 47 kΩ, ratiometric divider (KVM 3V3 leg + Hub 3V3 leg) | 0402WGF4702TCE | UNI-ROYAL | 0402 | ~$0.005 | [LCSC C25792](https://www.lcsc.com/product-detail/C25792.html) | Platform-reuse |
| R_KVM10k ×2 | 2 | 10 kΩ, ratiometric divider low leg | 0402WGF1002TCE | UNI-ROYAL | 0402 | ~$0.005 | [LCSC C25744](https://www.lcsc.com/product-detail/C25744.html) | Platform-reuse |
| TH1 | 1 | Board-temp NTC, 10k B25/50=3380K | NCP15XH103F03RC | Murata | 0402 | ~$0.09 [directional] | [LCSC C77131](https://www.lcsc.com/product-detail/C77131.html) | Platform-reuse |
| R_TH_BIAS | 1 | 10 kΩ, NTC divider | 0402WGF1002TCE | UNI-ROYAL | 0402 | ~$0.005 | [LCSC C25744](https://www.lcsc.com/product-detail/C25744.html) | Platform-reuse |
| C_TH | 1 | 100 nF, NTC node filter | CL05B104KO5NNNC | Samsung | 0402 | ~$0.004 | [LCSC C1525](https://www.lcsc.com/product-detail/C1525.html) | Platform-reuse |
| MH1–4 | 4 | M3 chassis-grounded mounting holes | (PCB feature) | — | — | $0.00 | — | Not a stocked line — plated mounting-hole/via pads per platform convention |
| FID1–3 | 3 | Fiducials | (PCB feature) | — | — | $0.00 | — | excl-BOM per platform convention (12VHPWR-Std precedent) |

Subtotal: **≈ $1.93**

### 5. RJ-11 security I/O (populated per SKU — see population note below)

| Ref-class | Qty | Value/Function | MPN | Mfr | Package | Unit@100q | Datasheet / LCSC | Notes |
|---|---|---|---|---|---|---|---|---|
| J_SEC | 1 | RJ-11 6P6C THT jack, right-angle unshielded, 125V/1.5A | KH-PCB-6P6C | Kinghelm | 6P6C TH R/A | **$0.08** [VERIFIED LCSC qty100] | [LCSC C2683354](https://lcsc.com/product-detail/C2683354.html) | NEW. Same Kinghelm family as platform RJ-45; -45–85°C. **Stock only 150 units — flag, see Open Items** |
| U_ALM | 1 | TLP172A PhotoMOS, isolated dry-contact ALARM_OUT (NO) | TLP172A(TP,F) | Toshiba | SOP-4 | **$1.4831** [VERIFIED LCSC qty100] | [LCSC C99477](https://datasheet.lcsc.com/lcsc/1808011925_TOSHIBA-TLP172A-TP-F_C99477.pdf) | NEW. 60V/400mA load, 2Ω max Ron, 1500Vrms isolation — pins 1/2 |
| R_ALMDRV | 1 | 330 Ω, TLP172A LED drive from MSS GPIO (~6.4mA) | 0402WGF3300TCE | UNI-ROYAL | 0402 | ~$0.005 | [LCSC C25104](https://www.lcsc.com/product-detail/C25104.html) | Platform-reuse (same value as R_LED) |
| U_CMP | 1 | LM393 dual comparator, EOL loop window-compare | LM393DR2G | onsemi | SOIC-8 | **$0.053** [VERIFIED LCSC qty100] | [LCSC C7955](https://www.lcsc.com/datasheet/lcsc_datasheet_2410121819_onsemi-LM393DR2G_C7955.pdf) | NEW — see "comparator note" below |
| R_LOOP | 1 | 10 kΩ, local pull from +3V3 into LOOP_IN_A sense node | 0402WGF1002TCE | UNI-ROYAL | 0402 | ~$0.005 | [LCSC C25744](https://www.lcsc.com/product-detail/C25744.html) | Platform-reuse. Same topology as DETECT (§2.3) |
| R_THA | 1 | 10 kΩ, threshold-ladder top leg | 0402WGF1002TCE | UNI-ROYAL | 0402 | ~$0.005 | [LCSC C25744](https://www.lcsc.com/product-detail/C25744.html) | Platform-reuse |
| R_THB | 1 | 5.1 kΩ, threshold-ladder mid leg | 0402WGF5101TCE | UNI-ROYAL | 0402 | ~$0.005 | [LCSC C25905](https://www.lcsc.com/product-detail/C25905.html) | Platform-reuse (same value as USB CC) |
| R_THC | 1 | 1 kΩ, threshold-ladder bottom leg | 0402WGF1001TCE | UNI-ROYAL | 0402 | ~$0.005 | [LCSC C11702](https://www.lcsc.com/product-detail/C11702.html) | NEW value, same UNI-ROYAL family |
| R_LPA/LPB | 2 | 1 kΩ, LOOP_IN_A/B series current-limit + surge R | 0402WGF1001TCE | UNI-ROYAL | 0402 | ~$0.005 | [LCSC C11702](https://www.lcsc.com/product-detail/C11702.html) | NEW value |
| D_LPA/LPB | 2 | PESD5V0S1BA, LOOP_IN_A/B ESD/surge clamp | PESD5V0S1BA | Nexperia | SOD-323 | $0.03 | [LCSC C5261083](https://www.lcsc.com/product-detail/C5261083.html) | Platform-reuse. **Sizing flagged, see Open Items** |
| D_AUX | 1 | SS14, AUX_ISO_5V reverse-block Schottky | SS14 | MDD | SMA | ~$0.025 [directional] | [LCSC C2480](https://www.lcsc.com/product-detail/C2480.html) | Platform-reuse = hub-standard D1; same §2.7/§2.9 reverse-isolation pattern |
| R_AUX | 1 | 330 Ω, AUX_ISO_5V current-limit | 0402WGF3300TCE | UNI-ROYAL | 0402 | ~$0.005 | [LCSC C25104](https://www.lcsc.com/product-detail/C25104.html) | Platform-reuse. ISO_GND (pin 6) kept off board GND per survey-3 |

Subtotal: **≈ $1.74**

**Comparator note (the "comparator-or-ADC" ask):** PolarFire SoC's MSS carries no documented general-purpose ADC peripheral (unlike the ESP32-S3's SAR ADC that the platform's DETECT/rail-sense pattern relies on everywhere else) — this is unconfirmed either way in the survey set and is a real open item, not just for this loop. Baseline chosen here: **LM393DR2G as a window comparator** — R_LOOP (10k) forms the same sense-divider topology as DETECT; a remote field-installed EOL resistor (not on this BOM — customer/installer-supplied, ~2.2 kΩ recommended, giving ~0.6V normal vs ~0V short / ~3.3V open); R_THA/B/C form a 3-resistor reference ladder giving ~0.24V and ~1.25V trip points that bracket the normal state with margin. Comparator A trips "short," comparator B trips "open," neither trips = "normal" — directly answers survey-3's tri-state ask. **Alternative not chosen**: a small I2C ADC (e.g., ADS7830IPWR, TI, 8-ch 8-bit, ~$1.00 [directional] — [LCSC C161747](https://www.lcsc.com/product-detail/C161747.html)) could consolidate DETECT×8 + this loop onto one bus-read part instead of per-channel comparators; worth an owner/firmware-team call once PolarFire's actual analog-read capability is confirmed.

---

## Cost roll-up (populated parts, 100q)

| Section | Subtotal |
|---|---|
| 1. Module ports ×8 | ≈ $5.08 |
| 2. CAN front end | ≈ $0.46 |
| 3. ~~RS-485 receivers ×8~~ (SUPERSEDED — T1-only, survey 10; master §5 subtracts) | ≈ $4.93 |
| 4. Platform base | ≈ $1.93 |
| 5. RJ-11 security I/O | ≈ $1.74 |
| **Subsystem C total** | **≈ $14.14** |

Reconciliation against `hub-ent-spec-sheet.md` §C+§E placeholders (**$16–22 + $2–3.5 = $18–25.5 combined**): real parts land **below** the placeholder range, mainly because the RS-485 receiver came in at $0.60/ea verified vs the doc's "$1 ea `[unv]`" guess (saves ~$3.2 across 8 ports), and the RJ-11 EOL/comparator network priced cheaper than the "$0.8–1.8" opto+EOL placeholder assumed. Recommend folding these verified numbers back into the spec sheet's §C/§E rows at the next revision.

## Open items

1. ~~OQ-5 topology sensitivity (RS-485)~~ **CLOSED for this BOM by survey 10**: the link is 100BASE-T1-only (REQ-HUB-COMMON-043), the §3 receiver bank is deleted, and OQ-5 no longer gates this subsystem (it remains open for the consumer Pro hub only). The T1 data plane (2× LAN9370 + port front-ends) is priced in the master BOM §5.
2. **Per-port 5VSB polyfuse — option, not populated by default.** Platform §2.7 lock is direct VCC distribution, no per-port limiting. `SMD0805-050/06N` (500mA hold/1A trip/6V, $0.036@100q) is a real, cheap, low-risk candidate if the owner wants port-level short isolation (one module's fault doesn't brown out the shared 5VSB rail / other ports) — adds $0.29/hub across 8 ports if adopted. No requirement currently calls for it; flagging per the task's ask, not recommending unprompted.
3. **BOOT/RESET button adaptation (MCU is PolarFire, not ESP32) — read carefully, this is a real behavioral change, not a relabeling:**
   - **RESET survives directly.** PolarFire SoC has a genuine hardware reset input (DEVRST_N); `SW_RESET` → DEVRST_N is a faithful analog of the ESP32 Hub's EN button.
   - **BOOT does NOT survive as a boot-mode strap.** ESP32's GPIO0-held-at-reset enters UART download mode — a runtime-sampled strap, pressed by a human at need. PolarFire's boot mode (Mode 0–3) is fixed at manufacture/programming time via the System Controller, not sampled from a GPIO each power-up — there is no PolarFire equivalent of "hold this button to enter download mode." `SW_USER` therefore keeps the same part/footprint but is **repurposed to a spare MSS GPIO for a firmware-defined function** (candidates: local service-mode entry, or the survey-3 runner-up "physical-presence/consent" input for Appendix-D Stage-5 gating — not decided here, flagging the option). Actual PolarFire firmware programming/recovery is via **JTAG/FlashPro** (a header, not a button) — that lives in compute subsystem A's BOM, not this one.
4. **RJ-11 surge protection may be under-specified.** Survey-3 itself flags this port as "the opposite of §2.4's rationale" — it's designed to leave the enclosure toward a facility panel with real surge exposure, yet this BOM (as instructed) reuses the platform's internal-grade PESD5V0S1BA. The NET uplink (§B) already gets a 3-electrode GDT for a similar externally-exposed port; RJ-11 currently does not. `hub-ent-spec-sheet.md` §4 open-row 7 already carries this as unresolved — not silently resolving it here; if the owner wants surge-class protection, candidate classes are a bidirectional TVS array with higher surge current (e.g., SMBJ-series) or a small 3-electrode GDT ahead of the PESD, on both LOOP_IN and the ALARM_OUT contacts.
5. **PolarFire analog-read path is an open cross-cutting question**, not unique to RJ-11: neither DETECT (×8, §1) nor the RJ-11 loop (§5) has a confirmed ADC peripheral to land on. This BOM answers RJ-11 with a discrete comparator (LM393DR2G); DETECT's read path is unaddressed by this BOM (out of the task's explicit scope) but shares the same open question. Worth a single owner/firmware decision (external ADC vs. per-channel comparators) rather than solving it twice, differently, per port.
6. **Stock-risk flag:** `KH-PCB-6P6C` (RJ-11 jack) shows only ~150 units in stock at LCSC — tight for a recurring 100-unit build. Same-family fallbacks exist at the same manufacturer: `KH-9801-6P6C` ([C2683355](https://lcsc.com/product-detail/C2683355.html)) and `KH-9752-6P6C` ([C2683356](https://lcsc.com/product-detail/C2683356.html)), or `PJ006-6P6C` (On-Shore Tech, [C7026652](https://www.lcsc.com/product-detail/C7026652.html)) as a second source. Re-quote before D-ENT-3 lock.
7. **Population note (per task):** RJ-11 security I/O (§5) populated by default on ENT-AIR (all availability tiers), populate-on-request on ENT-NET, per REQ-HUB-COMMON-033 and the SKU matrix. All other sections (§1–§4) are common to every SKU; the NanoKVM header itself is always populated, but the NanoKVM daughter-module is NET-only and is not part of this Hub's BOM.
8. **Directional-priced rows** (~30 of the resistor/passive/platform-reuse lines) were not individually re-verified at the exact 100q break this session — task scope directed WebSearch effort at NEW parts. They're commodity 0402 UNI-ROYAL resistors or already-validated platform parts, low pricing risk; flag for a formal RFQ pass alongside the rest of the platform BOM before D-ENT-3 lock.

## Sources

Internal (repo):
- `docs/enterprise-requirements/spec-sheets/hub-ent-spec-sheet.md` — §3.C/E baseline this BOM refines
- `docs/enterprise-requirements/hub-enterprise-requirements.md` — REQ-HUB-COMMON-033/040-045
- `docs/enterprise-requirements/research/phase2/survey-3-rj11-trust-channel.md` — RJ-11 function, pinout, threat model, isolation notes
- `docs/enterprise-requirements/research/phase2/survey-1-polarfire-sizing.md` — PolarFire SoC peripheral set (no ADC found), boot/JTAG context
- `docs/enterprise-requirements/research/phase2/survey-6-rtos-firmware-stack.md` — HSS/boot-mode confirmation (no runtime strap)
- `docs/enterprise-requirements/module-conformance-matrix.md`
- `hubs/hub-standard/bom/bom.csv` — platform-reused part source of truth

External (LCSC, fetched/verified this session):
- [THVD1450DR — LCSC C2671361](https://www.lcsc.com/product-detail/C2671361.html) / [TI datasheet](https://www.ti.com/lit/ds/symlink/thvd1450.pdf)
- [KH-PCB-6P6C — LCSC C2683354](https://lcsc.com/product-detail/C2683354.html)
- [TLP172A(TP,F) — LCSC C99477](https://lcsc.com/product-detail/SMD-Optocouplers_TOSHIBA_TLP172A-TP-F_TLP172A-TP-F_C99477.html)
- [LM393DR2G — LCSC C7955](https://www.lcsc.com/product-detail/C7955.html)
- [SMD0805-050/06N — LCSC C2687883](https://www.lcsc.com/product-detail/Resettable-Fuses_BORN-SMD0805-050-06N_C2687883.html)
- [0402WGF1200TCE (120Ω) — LCSC C25079](https://jlcpcb.com/partdetail/25822-0402WGF1200TCE/C25079)
- [0402WGF1001TCE (1kΩ) — LCSC C11702](https://www.lcsc.com/product-detail/C11702.html)
- [ADS7830IPWR — LCSC C161747](https://www.lcsc.com/product-detail/C161747.html) (alternative not chosen)
- TLV3011AIDBVR ([LCSC C2870632](https://www.lcsc.com/product-detail/C2870632.html)) evaluated and rejected in favor of LM393DR2G — only 56 units in stock at qty100 pricing, insufficient for a 100-unit build (16 needed/hub → 1,600/build)

**Verification honesty**: THVD1450DR, KH-PCB-6P6C, TLP172A(TP,F), LM393DR2G, and SMD0805-050/06N prices are LCSC-fetched qty100 numbers (high confidence). All UNI-ROYAL 0402WGF-family resistor prices and several platform-reuse IC/connector prices (SK6812MINI-E, SN74AHCT1G08DBVR, U262-16XN-4BVC11, USBLC6-2SC6, TS-1088-AR02016, S5B-PH-K-S, NCP15XH103F03RC, SS14) are directional estimates based on search snippets that likely reflect a different quantity tier than 100 — marked `[directional]` throughout and should be re-pulled at the formal RFQ pass.
