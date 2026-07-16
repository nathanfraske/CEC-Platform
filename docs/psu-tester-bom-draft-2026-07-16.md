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
| Fans | **real price is $16–26, not $10**: Sunon MFC0251V2 $16.33@50 (2.9 k stock, 59 CFM quiet-class) — the 120 CFM Delta AFB1212HJ is OOS/40-wk; re-select for static pressure at order, budget 4× | [DK] | 4 | 16.33 | 70.00 | +30.00 | airflow margin re-check w/ quiet-class fans (§4 sketch: 141 CFM delivered target) |
| FET extrusion | 300 mm forced-air 6063 class | (q) | 1 | 45.00 | 45.00 | — | validated $35–60 via live Alibaba-class quotes |
| Chassis | sheet-metal console | (q) | 1 | 200.00 | 200.00 | — | fab-quote item |
| Slot deck field | 63951-1 blades ~40× $0.136 + J_SIG + rails (§12 posture) | [LCSC] C591344 | set | — | 40.00 | — | blades healthy; **module-side 63969-1 receptacle is now FULLY OOS — program-wide escalation, see §5** |
| 12 V aux jack | XKB DC-005-5A-2.0 | [LCSC] C381116 | 1 | 0.26 | 0.26 | — | 14.8 k; fit-check vs 5.5×2.1 plugs |
| PCBs | main 4L 2 oz + slice + head | (q) | — | — | 75.00 | — | |
| AC sense pod | PARKED (owner) — removed from base BOM; +$20 option when un-parked | — | — | — | 0.00 | −20.00 | |
| Misc | passives/harness/hardware ~5 % | (~) | — | — | 45.00 | −10.00 | |
| **Tester Pro BOM v1** | | | | | **≈ $1,039** | **−$162 vs v0** | band **$950–1,250** (chassis quote, fan re-pick, P4 risk) |

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
| **Tester Max BOM v1** | | | **≈ $1,332** | −$175 | band $1,250–1,600 (+$100–150 2 kW option) |

## 3. Full retail roll-up (v1)

| | **Pro station** | **Max station** |
|---|---|---|
| Tester BOM v1 (mid) | ~$1,039 | ~$1,332 |
| Tester landed (+19 %) | ~$1,236 | ~$1,585 |
| Ruled tester list | $3,495 = **2.8×** landed | $5,995–6,995 = **3.8–4.4×** landed |
| Bundle all-in (per §3b posture: + module set + Hub + spares, landed) | ~$1,390 | ~$1,900 + Max-Hub TBD |
| **Bundle list** | **$3,995 (2.9×)** | **$6,995 (≈3.4–3.7×)** |

**v1 margin picture: the sourced BOM came in UNDER the v0 estimate** (−$162
Pro / −$175 Max — the DigiKey fast-FET price and cheaper control silicon beat
the fan/resistor/AFE increases), so the ruled list prices now sit at or above
the platform 3× convention at the bundle level. The margin-honesty caveat
from v0 softens accordingly; the remaining swings are the chassis quote and
the P4 availability answer.

## 3a. Standard tester value line (v1-scaled)

ST shares every Pro savings it has lines for (silicon −$25-ish) and every
increase (fans +$13 at 2×, resistor pivot ≈ neutral, bimetal +$7): **ST-1000
≈ $520 / ST-1300 ≈ $565** — within noise of v0; the $1,299/$1,499 single-SKU
lists hold at ~2.05–2.15×, and the §3b slot-bundle math is unchanged.

## 3b. Slot-in bundle scenario — unchanged from v0 (sketch §12)

Bundle deltas ride the same v1 numbers; table retained from v0 with totals
now ~$80–160 more favorable across the line. Field kit $39–49 and saver
pigtails $29–39 unchanged.

## 4. Sourcing-pass results summary (what the agents verified)

- 10+ recommended parts vendored with symbol+footprint+3D+datasheet into
  `lib/vendor/psu-tester-staging/` (exceptions: 88Q2110 + KSD9700 have no
  EasyEDA CAD — hand-vendor at schematic; TPS55289 has no 3D).
- Traps recorded: OPA2277 plain-"U" 6–10× pricing trap; OSEN fake-MPN
  "IXTK90N25L2" (different part, TO-3PL, 360 W); MINI-vs-ATOF fuse-holder
  size trap; jlcsearch stale-stock cache (TPS55289 "380" ghost stock).

## 5. SUPPLY-RISK REGISTER (owner attention, ranked)

1. **ESP32-P4NRW32 — OOS, no module SKU exists anywhere, no confirmed
   distributor fallback.** Hits both testers AND the 12VHPWR Pro / Hub Pro
   programs. Watch item + owner ping; possible "ESP32-P4X" successor line
   spotted on DigiKey (unverified relationship — follow up).
2. **TE 63969-1 receptacle — fully OOS at LCSC** (was ~5-unit restock-watch;
   now zero, "Notify Me"). This is the MODULE-side half of the blade
   architecture — affects daughterboards + main boards platform-wide, not
   the tester. Escalate before the OQ-86 fit-check/fab gate; 63968-1 LIF
   fallback not confirmed on LCSC either.
3. **TPS55289 (RULED OVP part) — OOS at LCSC.** Recommendation: design the
   OVP stage on the in-stock TPS55288RPMR from the start (pre-schematic =
   the footprint change is free); DK bridge $6.42 if the 55289 is preferred.
   Needs owner nod since the part was named in a ruling context.
4. **AD9253-80 price doubled** ($41.67 → $80.18); -105 grade now cheaper at
   $61.84/$58.33@30 — grade-flip decision for the owner (affects the Max
   MODULE program too, not just the tester).
5. **Fans**: high-CFM Delta class OOS/40-week; quiet-class Sunon in stock at
   ~2× the v0 price. Re-select for duct static pressure at order time.
6. **Bimetal NC verification**: LCSC's cheap KSD9700 listings read NO
   (normally-open); the safety chain needs NC. Verify with vendor or pay
   the $5.38 Cantherm line.
7. **L2 linear FETs are a DigiKey-only class now** (LCSC carries zero
   genuine TO-247 L2; the one TO-264 flipped OOS) — consigned/hand-solder
   line permanently; order-ahead posture.

## 6. Open items to the sourcing/pricing pass (carried)

1. Chassis + extrusion formal quotes (the remaining big swings).
2. Max Hub pricing (Task-13; blocks Max-station all-in).
3. Replacement front-plate/field-kit SKU pricing at OQ-89 lock.
4. ADG1408 bandwidth confirmation (UNVERIFIED-by-table flag).
5. R-bank parallel-ladder value engineering (exact step table, §C.12).
6. Pod BOM when un-parked.
