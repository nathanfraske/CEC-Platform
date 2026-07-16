# PSU tester — BOM v1 (SOURCED) + full-retail roll-up

**v1 (2026-07-16, evening): four-agent live sourcing pass integrated** — every
line now carries a real MPN/LCSC#/price/stock verified against lcsc.com
product pages today (DigiKey where LCSC has nothing), superseding the v0
class estimates (kept as the Δ column). Assets (symbols/footprints/3D/
datasheets) staged under `lib/vendor/psu-tester-staging/{load-semis,
control-silicon,max-lane,electromech}/`. Tags: **[LCSC]** live-verified
today, **[DK]** DigiKey consigned, **[P]** platform part, **(q)** quote item.
Qty pricing = the ~25–50 break (small-batch build basis). Still
pre-schematic — freeze at schematic.

## 1. Tester Pro — itemized (v1 sourced)

| Subsystem | Part | Src | Qty | Unit $ | Ext $ | v0 Δ | Stock note |
|---|---|---|---|---|---|---|---|
| MCU | ESP32-P4NRW32 (bare chip, in-pkg PSRAM; no module SKU exists) + flash/support | [LCSC] C22387510 | 1 | ~6.50 set | 6.50 | −2.50 | **OOS TODAY, no confirmed distributor fallback — RISK #1** (also hits 12VHPWR Pro / Hub Pro) |
| CAN | TJA1051T/3 + jack/DETECT 4.7 kΩ/PESD | [P] | set | 2.00 | 2.00 | — | healthy |
| RS-485 TX | THVD1450DR (50 Mbps, ±18 kV; candidate for 12VHPWR-Pro reuse) | [LCSC] C2671361 | 1 | 0.70 | 0.70 | −0.50 | 4.7–7.2 k |
| USB/PD | CH224K + XKB USB-C C319148 + USBLC6 | [LCSC] C970725/C319148 | set | 1.00 | 1.00 | −2.50 | deep stock; CH224K beat AP33772 (thin stock) |
| Setpoint DAC | DAC80508ZRTER (2.5 V ref 2 ppm/°C typ) | [LCSC] C2679499 | 1 | 14.09 | 14.09 | +2.09 | 236 pcs — LCSC-stocked after all; **use the Z-grade reel SKU** |
| CC loop amps | OPA2277UA/2K5 (dual; **reel SKU only** — the plain "U" listing is identical silicon at 6–10×) | [LCSC] C24460 | 8 | 0.54 | 4.32 | −11.68 | 8 k; ADA4522-2 ($2.49, 31 k) = zero-drift upgrade path |
| Fast loop | TPH2502-SR (120 MHz, 290 mA drive — outmuscles OPA810) + BJT class-AB gate buffer | [LCSC] C118223 | set | 2.50 | 2.50 | −3.50 | 14.9 k |
| Trip watch | INA181A2 + TLV7011 ×8 | [P] | 16 | — | 7.20 | — | platform cells |
| Vernier FETs | IXTH75N10L2 (TO-247 Linear-L2, 400 W) | **[DK]** (no LCSC TO-247 L2 exists) | 8 | 13.17 | 105.36 | −6.64 | DK 1,276; hand-solder THT line |
| Fast-ch FETs | IXTK90N25L2 (TO-264 L2) | **[DK]** $28.05@25 (LCSC C2831650 flipped to OOS @$66.49) | 4 | 28.05 | 112.20 | −49.32 | DK 953; **OSEN fake-MPN trap on LCSC — do not substitute** |
| Ballast/gate | precision R + networks | (~) | — | — | 10.00 | — | jellybean |
| Loop shunts | CSS2H-2512R-1L00F (1 mΩ ±1 % 50 ppm — the platform OQ-11 pick) | [LCSC] C4175647 | 9 | 0.40 | 3.60 | −8.10 | 2.1 k; family thin at other values |
| R-banks | **STRATEGY PIVOT: paralleled 50 W units** (HoRX-50W-5R class $1.71–3.24, healthy) instead of single low-ohm 100–450 W parts ($14–22, stock 5–18!) — finer steps free | [LCSC] C2923747 + ladder | ~64 | ~2.60 | 170.00 | +10 | volume order needed; single big-part path documented as fallback |
| Bank plates | mounting/insulators | (q) | — | — | 50.00 | — | metalwork |
| Bank switching | AOD4184A ×24 ($0.28!) + drivers + Littelfuse 0287 ATOF fuses + **Keystone 3557-10 holders** (ATOF size — the MINI-size 178.6764 holder does NOT fit, trap flagged) | [LCSC] C99124/C142683../C3205403 | set | — | 30.00 | −12.00 | all healthy |
| SCP crowbars | IRLB3034(UMW) ×8 + surge shunts + SMCJ15A TVS + time-fuses | [LCSC] C19100597/C135138 | 4 blk | 5.00 | 20.00 | −14.00 | TVS 2 orders over the ½LI² need — no margin issue |
| OVP-A stage | **TPS55288RPMR** (in stock, 16 A superset) — RECOMMEND designing on it from the start; ruled TPS55289 is OOS at LCSC (DK bridge $6.42) and no layout exists yet, so the "footprint change" is free | [LCSC] C2864583 | set | 10.00 | 10.00 | −10.00 | 6.2 k; + VLS6045EX-2R2N L ($0.09, Isat 7.5 A vs 6.35 A limit = fine) + HFD4/5-SR relays ×3 |
| Thermal | NTC [P] + bimetal 120 °C NC — **LCSC KSD9700 is listed NO not NC**: verify contact form or budget Cantherm CS7115/13025Y [DK] $5.38 ×2 | mixed | — | — | 11.00 | +7.00 | verification item before lock |
| Aux rails | TPS54331DR ×3 + L/C | [LCSC] C9865 | 3 | 0.35 | 3.00 | −2.00 | 47 k |
| Fans | **Noctua NF-F12 industrialPPC-3000 PWM** (7.63 mmH₂O — the duct-honest pick; round-2 verdict). Options: Arctic P12 Max $12.99 value (4.35 mmH₂O — pressure-margin risk on the 1600 W duct; FINE for ST's smaller duct), San Ace 9GA1212P4G001 max-margin (37.3 mmH₂O, 936 DK stock, $52@30, 57 dBA loud). Both named Deltas are dead (obsolete / non-PWM+OOS) | [DK/direct] | 4 | 29.95 | 120.00 | +80.00 | static pressure is THE spec in a resistor duct |
| FET extrusion | 300 mm forced-air 6063 class | (q) | 1 | 45.00 | 45.00 | — | validated $35–60 via live Alibaba-class quotes |
| Chassis | sheet-metal console | (q) | 1 | 200.00 | 200.00 | — | fab-quote item |
| Slot deck field | 63951-1 blades ~40× $0.136 + J_SIG + rails (§12 posture) | [LCSC] C591344 | set | — | 40.00 | — | blades healthy; **module-side 63969-1 receptacle is now FULLY OOS — program-wide escalation, see §5** |
| 12 V aux jack | XKB DC-005-5A-2.0 | [LCSC] C381116 | 1 | 0.26 | 0.26 | — | 14.8 k; fit-check vs 5.5×2.1 plugs |
| PCBs | main 4L 2 oz + slice + head | (q) | — | — | 75.00 | — | |
| AC sense pod | PARKED (owner) — removed from base BOM; +$20 option when un-parked | — | — | — | 0.00 | −20.00 | |
| Misc | passives/harness/hardware ~5 % | (~) | — | — | 45.00 | −10.00 | |
| **Tester Pro BOM v1.1** | | | | | **≈ $1,089** | **−$112 vs v0** | band **$1,000–1,300** (chassis quote, P4 risk; fans now the honest iPPC pick) |

## 2. Tester Max — delta over Pro (v1 sourced)

| Subsystem | Part | Src | Ext $ | v0 Δ | Note |
|---|---|---|---|---|---|
| Fast ADC | **AD9253BCPZ-105** — GRADE FLIP RECOMMENDED: the -80 doubled to $76.82@30 while the faster -105 now costs LESS | [LCSC] C514281 | 58.33 | +16.66 | -80 = $80.18@1 (2× the 07-05 study); -105 stock 186 |
| FPGA | GW5A-25 MG121 | [LCSC] C45617374 | 44.55 | −2.33 | rock-stable, exact match to the 07-05 study |
| AFE | ADA4930-1YCPZ-R7 ×4 ($8.55 — THS4541 OOS) + ADG1408YRUZ mux ($6.90; **BW unverified-by-table** — confirm ≥20 MHz before lock) + passives | [LCSC] C578938/C148081 | 49.00 | +23.00 | honest re-base: AFE silicon ~2× the v0 guess |
| T1 link | 88Q2110-A2 (dual-rate superset; ex-Marvell → Infineon rebrand pending) — the ONLY in-stock T1 PHY today (DP83TC811 + LAN8770 both OOS) | [LCSC] C39105882 | 4.08 | −1.92 | 1,470 pcs; no EasyEDA CAD — footprint gets hand-vendored at schematic |
| 2nd fast channel | IXTK ×4 [DK] @28.05 + loop | [DK] | 122.00 | −48.00 | |
| PCB delta | digitizer lane | (q) | 15.00 | — | |
| **Max delta v1** | | | **≈ $293** | −$13 | |
| **Tester Max BOM v1.1** | | | **≈ $1,382** | −$125 | band $1,300–1,650 (+$100–150 2 kW option) |

## 3. Full retail roll-up (v1.1)

| | **Pro station** | **Max station** |
|---|---|---|
| Tester BOM v1.1 (mid) | ~$1,089 | ~$1,382 |
| Tester landed (+19 %) | ~$1,296 | ~$1,645 |
| Ruled tester list | $3,495 = **2.7×** landed | $5,995–6,995 = **3.6–4.3×** landed |
| Bundle all-in (§3b posture: + module set + Hub + spares, landed) | ~$1,450 | ~$1,960 + Max-Hub TBD |
| **Bundle list** | **$3,995 (2.8×)** | **$6,995 (≈3.3–3.6×)** |

**The sourced BOM still lands UNDER the v0 estimate** (−$112 Pro / −$125 Max
after taking the honest fan pick), and the ruled lists hold at ≥2.7× landed
— at or above the platform convention at bundle level. Remaining swings:
chassis quote, P4 availability, AD9253 buy-ahead depth.

## 3a. Standard tester value line (v1.1)

ST's smaller duct (~88–115 CFM) tolerates the Arctic P12 Max value fans
($12.99, in stock): **ST-1000 ≈ $513 / ST-1300 ≈ $555** → landed ~$610/$660
→ **$1,299 (2.1×) / $1,499 (2.3×)** — the single-SKU lists hold with margin
slightly improved vs v1.

## 3b. Slot-in bundle scenario — unchanged posture (sketch §12)

Bundle deltas ride the v1.1 numbers; field kit $39–49 and saver pigtails
$29–39 unchanged.

## 4. Sourcing-pass results (rounds 1 + 2)

- Round 1: ~15 parts vendored with symbol+footprint+3D+datasheet into
  `lib/vendor/psu-tester-staging/` (exceptions: 88Q2110 + KSD9700 have no
  EasyEDA CAD; TPS55289 no 3D). Traps: OPA2277 plain-"U" 6–10× pricing trap;
  OSEN fake-MPN "IXTK90N25L2" (different part); MINI-vs-ATOF fuse-holder
  size trap; jlcsearch stale-stock cache.
- Round 2 (owner-directed dig): LCSC "marketplace" for the TE parts is the
  RFQ-gated "Other Suppliers" program (no browsable stock/price; szlcsc
  blocked automated checks) — the depth is in WESTERN DISTRIBUTION instead
  (see §5.2). DigiKey got WORSE for AD9253 (-80 $191.73; -105 zero-stock,
  backorders blocked) — LCSC is the only live channel. Both candidate Delta
  fans are dead ends (obsolete / non-PWM+OOS). LCSC confirmed to have NO
  verified-NC 120 °C bimetal (three listings' attribute tables checked);
  one unbrowsable Cantherm pool on LCSC left for a manual look at BOM lock.
  Findings note: `lib/vendor/psu-tester-staging/round2/`.

## 5. SUPPLY-RISK REGISTER v2 (post round-2; owner attention, ranked)

1. **ESP32-P4 — ESCALATED (platform-wide, owner decision needed).** Not a
   restock lag: a mid-stream silicon transition. v3.x ships under NEW
   "X"-suffix MPNs (ESP32-P4NRW32X / NRW16X, per Espressif's v3.x user
   guide); **firmware images are NOT portable v1.x↔v3.x** (pin-54 change,
   50+ register/hardware deltas); Espressif briefly shipped new silicon
   under the OLD SKU (documented channel confusion); TODAY there is ZERO
   bare-chip stock and zero distributor listings for EITHER generation
   (Mouser/DK/Arrow don't even list it), while other Espressif lines are
   healthy. No module SKU exists. POSTURE: (a) OWNER: rule the target
   revision now — recommend v3.x (NRW32X, LCSC C54540373) for all new
   designs (testers, 12VHPWR Pro, Hub Pro); (b) watch C22387510 + C54540373;
   (c) written revision confirmation on any order; (d) buy several
   build-cycles deep at first restock — no backstop channel exists.
2. **TE 63969-1 — DOWNGRADED to routine.** LCSC-direct is empty, but the
   depth is in mainstream Western distribution: DigiKey 30,855 ready-to-ship
   ($0.152@vol), Arrow 16,800 ($0.147), Farnell/Newark 8,400 each, TE direct
   79,215. The owner's LCSC-marketplace recollection maps to the RFQ-gated
   "Other Suppliers" program (not browsable; worth ONE manual RFQ to price
   the China-side path). Buy DigiKey/Arrow for fit-check + first runs.
   63951-1 healthy everywhere (DK 185k, TE 327k). NEW thin item: **63968-1
   LIF fallback is genuinely dry** (DK 0, 16-wk) — the fallback has no
   fallback; fine while 63969-1 depth holds.
3. **TPS55288RPMR — RESOLVED, dual-sourced.** LCSC primary ($2.08@30,
   6,175) + DigiKey $6.08 ships-today + Mouser listing exists. Recommend
   final: design the OVP stage on TPS55288 (owner nod recorded when given;
   TPS55289 remains the DK-bridge alternative).
4. **AD9253 — grade flip now effectively FORCED + buy-ahead.** -105 (LCSC
   C514281, $58.33@30, stock 186↑) is the only in-class, in-stock quad path
   anywhere: DK has -80 at $191.73 (2.4× LCSC) and -105 at ZERO with
   backorders blocked; every alternative fails (AD9633 broker-only/pricier/
   ~5 units, AD9257 wrong channel count + no LCSC, ADS4245 unfindable,
   HMCAD1511 8-bit out-of-class). OWNER: nod the -105 grade (affects the
   Max MODULE program too) and set a buy-ahead quantity against the
   186-unit single-channel pool.
5. **Fans — RESOLVED with a tiered answer.** Duct-honest pick = Noctua
   NF-F12 industrialPPC-3000 PWM ($29.95, 7.63 mmH₂O) for Pro/Max; Arctic
   P12 Max ($12.99, 4.35 mmH₂O) fine for ST's smaller duct; San Ace
   9GA1212P4G001 (37.3 mmH₂O, 936 DK stock, 57 dBA) is the max-margin/loud
   option. Verify against the real duct P-Q at the chassis prototype.
6. **Bimetal NC — RESOLVED.** LCSC has no verified-NC 120 °C part (KSD.301
   + KSD9700 attribute tables all read NO); the part is **Cantherm
   CS712025Y** [DK], SPST-NC explicit, 120 °C, $4.39@25, 506 stock. One
   manual check left: LCSC's unbrowsable Cantherm pool at BOM lock.
7. **L2 linear FETs — unchanged**: DigiKey-only class permanently
   (IXTH75N10L2 verniers, IXTK90N25L2 fast channel); consigned/hand-solder
   line; order-ahead posture.

## 6. Open items to the sourcing/pricing pass (carried)

1. Chassis + extrusion formal quotes (the remaining big swings).
2. Max Hub pricing (Task-13; blocks Max-station all-in).
3. Replacement front-plate/field-kit SKU pricing at OQ-89 lock.
4. ADG1408 bandwidth confirmation (UNVERIFIED-by-table flag).
5. R-bank parallel-ladder value engineering (exact step table, §C.12).
6. Pod BOM when un-parked.
7. One manual LCSC "Other Suppliers" RFQ on 63969-1 (price the China path).
8. Duct P-Q measurement at chassis prototype → final fan lock.
