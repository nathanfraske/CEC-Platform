# PSU tester — BOM v1 (SOURCED) + full-retail roll-up

**v1.2 (2026-07-16, owner steer round):** (1) **P4 supply: owner RULED ride
out the blip** (Pro/Max are a distance from shipping) — §5.1 downgraded from
escalation to standing discipline; (2) **fans RULED → Arctic S12038-4K**
(11.45 mmH₂O beats the iPPC-3000's 7.63 at half the price; spec-sheet
checked) — Pro −$60, ST unify recommended; (3) **2 kW ballast RETIRED →
~3,000 W WORKSTATION tier** (Pro-W / Max-W, sketch §13) — first-cut BOMs in
new §3c; (4) **displays added** (owner: main load readout + one LCD per
module bay, off/logo when unpopulated — BOM-checked ~$3/bay, RULED IN) —
+$35 Pro-class. Totals: **Pro ≈ $1,064 / Max ≈ $1,357 / Pro-W ≈ $1,635 /
Max-W ≈ $1,955 / ST ≈ $545/$589**.

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
| MCU | ESP32-P4NRW32 (bare chip, in-pkg PSRAM; no module SKU exists) + flash/support | [LCSC] C22387510 | 1 | ~6.50 set | 6.50 | −2.50 | supply blip: **OWNER RULED 2026-07-16 ride it out** (ships far out); design against v3.x NRW32X — §5.1 |
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
| Fans | **Arctic S12038-4K — OWNER STEER 2026-07-16 (RULED)**: 120×120×**38 mm** server class, 11.45 mmH₂O / 106 CFM / 600–4000 rpm PWM / dual Japanese ball bearing / 3.96 W / 6-yr wty — MORE pressure than the round-2 Noctua iPPC-3000 pick (7.63) at HALF the price. Fallbacks retained: NF-F12 iPPC-3000 $29.95, San Ace 9GA1212P4G001 max-margin (37.3 mmH₂O, loud) | [Arctic/Amazon; value 3-packs ACFAN00303A] | 4 | 14.99 | 60.00 | +20.00 | duct P-Q at chassis proto is still the final lock (§6.8); 38 mm depth budgeted at the duct mouth |
| FET extrusion | 300 mm forced-air 6063 class | (q) | 1 | 45.00 | 45.00 | — | validated $35–60 via live Alibaba-class quotes |
| Chassis | sheet-metal console | (q) | 1 | 200.00 | 200.00 | — | fab-quote item |
| Slot deck field | 63951-1 blades ~40× $0.136 + J_SIG + rails (§12 posture) | [LCSC] C591344 | set | — | 40.00 | — | blades healthy; **module-side 63969-1 receptacle is now FULLY OOS — program-wide escalation, see §5** |
| 12 V aux jack | XKB DC-005-5A-2.0 | [LCSC] C381116 | 1 | 0.26 | 0.26 | — | 14.8 k; fit-check vs 5.5×2.1 plugs |
| Displays | **OWNER ADD 2026-07-16 (sketch §5)**: main 2.8″ IPS 320×240 SPI (~$5) + 8× bay 1.54″ IPS 240×240 SPI module class (~$3/bay — per-bay RULED IN at this cost) + 74HC595 CS glue + bezels/harness; IPS not OLED (static-readout burn-in) | [LCSC] (module class; MPNs at schematic) | set | — | 35.00 | +35.00 | commodity class, no supply risk; unpopulated bay = dark/logo splash |
| PCBs | main 4L 2 oz + slice + head | (q) | — | — | 75.00 | — | |
| AC sense pod | PARKED (owner) — removed from base BOM; +$20 option when un-parked | — | — | — | 0.00 | −20.00 | |
| Misc | passives/harness/hardware ~5 % | (~) | — | — | 45.00 | −10.00 | |
| **Tester Pro BOM v1.2** | | | | | **≈ $1,064** | **−$137 vs v0** | band **$980–1,280** (chassis quote the main swing; fans −$60 on the Arctic steer, displays +$35) |

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
| **Tester Max BOM v1.2** | | | **≈ $1,357** | −$150 | band $1,270–1,620 (2 kW ballast option RETIRED — owner 2026-07-16 → Workstation tier, §3c) |

## 3. Full retail roll-up (v1.2)

| | **Pro** | **Pro-W** | **Max** | **Max-W** |
|---|---|---|---|---|
| Tester BOM v1.2 (mid) | ~$1,064 | ~$1,635 | ~$1,357 | ~$1,955 |
| Tester landed (+19 %) | ~$1,266 | ~$1,945 | ~$1,615 | ~$2,325 |
| Tester list | $3,495 = **2.8×** | **$4,995 = 2.6×** (first-cut) | $5,995–6,995 = **3.7–4.3×** | **$7,995 = 3.4×** (first-cut) |
| Bundle all-in (landed, § 3b posture) | ~$1,420 | configurator-built | ~$1,930 + Max-Hub TBD | configurator-built |
| **Bundle list** | **$3,995 (2.8×)** | configurator (see note) | **$6,995 (≈3.4–3.6×)** | configurator (see note) |

**W bundles RULED (owner, 2026-07-16): configurator-built, not fixed
manifests** — the 4× 12VHPWR stack is an option line, priced per config
against the PORT LEDGER (sketch §13: tester + 24-pin + EPS + 4× HPWR +
PCIe-3 = 8 nodes = Hub Pro exactly full; overflow → standalone-USB or the
proposed deck CAN expansion jacks).

**Ladder:** ST-1000 $1,299 / ST-1300 $1,499 / Pro $3,495 (bundle $3,995) /
**Pro-W $4,995** / Max $5,995–6,995 / **Max-W $7,995**. Pro-W's 2.6× sits
below the platform 3× convention but above capital-equipment norms — the
standing owner margin call; $5,295–5,495 is the 3×-adjacent alternative.
Remaining swings: chassis quotes (now incl. the W two-lane console), AD9253
buy-ahead depth, W bundle module manifest.

## 3a. Standard tester value line (v1.2)

Fan SKU unified on the Arctic S12038-4K (owner steer; +$4–6 over P12 Max
buys one platform-wide spare SKU + pressure headroom) and displays added
(main + ~6 bay screens ≈ $28 — the "ready to go" face): **ST-1000 ≈ $545 /
ST-1300 ≈ $589** → landed ~$649/$700 → **$1,299 (2.0×) / $1,499 (2.1×)** —
single-SKU lists hold; margin-honesty note stands (2×-class, the standing
owner call). CONFIG RULED (owner, 2026-07-16 evening): **slot-bundle is the
ST architecture** — integrated-sensing carve-out RETIRED ("soldered is worse
in both repairability and cost"). PROPOSED on top (sketch §12a,
DOWNGRADED to optional headroom — owner: PCIe/12VHPWR are per-DUT
alternates, base 4-port ledger is sufficient): KVM-aux tester link docks
both GPU modules at once; 4-module bundle = configurator upsell
(≈$675 landed, $1,399-class), not the default.

## 3b. Slot-in bundle scenario — unchanged posture (sketch §12)

Bundle deltas ride the v1.2 numbers; field kit $39–49 and saver pigtails
$29–39 unchanged.

## 3c. WORKSTATION tier first-cut (~3,000 W; owner ruling 2026-07-16, sketch §13)

Pro-W = Tester Pro + this delta (population/scaling only — same board set,
shared W chassis platform); Max-W = Pro-W + the §2 Max delta + ~$25
(mux/shunt wiring for the extra heads).

| Delta line (over Pro v1.2) | Ext $ | Basis |
|---|---|---|
| R-banks +~56× 50 W paralleled units (→ ~6.0 kW installed @50 % derate) | +146 | C2923747 class @~$2.60 |
| Bank plates/metalwork | +40 | (q) |
| Bank switching (+FETs/drivers/fuses/holders) | +20 | commodity |
| Verniers +5× IXTH75N10L2 (8 → ~13 loops) | +66 | [DK] $13.17 |
| +1× DAC80508 + loop amps + trip-watch cells | +20 | 2× DAC = 16 ch |
| Loop shunts +5 | +2 | C4175647 |
| Fixture bay +3× 12V-2x6 heads + harness | +35 | 4-GPU reality |
| Slot-deck blade fields (4 HPWR slots) | +15 | §12 posture |
| SCP +2 crowbar blocks (extra HPWR rails) | +10 | §3b math unchanged |
| Chassis delta (two-lane duct, ~430×450×170) | +80 | (q) |
| FET extrusion 300 → ~500 mm class | +45 | (q) |
| Fans +2× S12038-4K (4 → 6) | +30 | §4 sketch, 263 CFM |
| Displays +3 bay screens + harness | +10 | 11 bays |
| PCBs (more slices, longer deck) | +30 | (q) |
| Misc/harness | +20 | ~5 % |
| **Pro-W delta** | **≈ +$570** | |
| **Tester Pro-W BOM v1.2** | **≈ $1,635** | band $1,500–1,900 |
| **Tester Max-W BOM v1.2** (+$293 Max delta +$25) | **≈ $1,955** | band $1,800–2,250 |

Optional W deck provision (owner pick pending, sketch §13 relief valve 2):
2–3 CAN-only expansion jacks (RJ-45 + DETECT ESD cell + switched 5VSB) ≈
**+$5 populated / $0 DNP** — preserves µs MARK timing for melt-watch
monitors past the 8-port Hub ledger.

Lists (first-cut, §3 ladder): **Pro-W $4,995 (2.6× landed) / Max-W $7,995
(3.4× landed)**. The 2 kW Max ballast option is RETIRED (owner: "over a US
breaker anyway" — a >1,800 W DUT already needs a 240 V/20 A drop, and that
shop is servicing the 3 kW workstation class; market anchor ASUS Pro WS
3000W Platinum ≈ $1,036 street). Whole-PSU 200 %/100 µs excursion honesty
fences per sketch §13 (per-head always covered; whole-PSU to ~1.1 kW label
on one fast channel, ~2 kW on Max-W's ganged pair; 10 ms+ steps recruit
banks to the full 3 kW delta).

## 3d. Price-check addendum (2026-07-16 night) — wall-cartridge hardware + ladder v1.1

Owner audit question: "price-checked the resistors and FETs, as well as the
bolt-on tabs?" Answer state + tonight's live checks:

- **Resistors — priced, family re-verified live tonight.** The v1.2 line
  stands (RX24/50W aluminum-shell class, LCSC, $1.71–3.24; C2923747 = the 5R
  line); live check confirms the family healthy at LCSC ($1.64-class VO-brand
  siblings on the shelf) and 6R is a stock family value industry-wide. The
  ONE standing confirm stays: the exact 6R LCSC SKU at BOM lock (5R fallback
  ruled acceptable in ladder v1.1).
- **FETs — all priced (v1.2 rows unchanged).** Bank switches AOD4184A $0.28
  (C99124, healthy); verniers IXTH75N10L2 $13.17 [DK 1,276 — no LCSC TO-247
  L2 exists, known consign line]; crowbars IRLB3034 UMW-brand (block sets $5,
  healthy); fast channel IXTK90N25L2 $28.05@25 [DK 953, OSEN fake-MPN trap
  flagged]. NEW jellybean from ladder v1.1: the 5VSB mini-CC DPAK FET
  (linear-derated logic-level class) ≈ $0.20–0.40 — noise; MPN at schematic.
- **Bolt-on tabs — were NOT priced (part born with the wall-cartridge form
  tonight); NOW CHECKED.** Class = screw/stud-mount .250″ male tab, brass,
  0.81 mm blade thickness = exactly the TE 63969-1 receptacle's design-centre
  (same blade class as the 63951-1 program tabs — one receptacle spec across
  everything). Verified western part: Keystone screw/rivet/stud family (e.g.
  1006: **$0.78@100 / $0.4449@1k, DK 1,783 + 19.3k factory**). Volume path:
  commodity China stamping $0.03–0.10 [wb at volume RFQ]. Qty = leg count
  (54 / 66 / ~75 / ~125) ⇒ $24–55/unit at Keystone prices, $4–13 at the
  volume path. Exact SKU at BOM lock (tab is bolt-on hardware, not a netlist
  item — the deck receptacle is the netlist part).
- **THE MULTIPLIER FIND — deck receptacles now scale with LEG COUNT.** The
  wall-cartridge form puts one 63969-1-class receptacle on the deck PER LEG
  (+54/66/~75/~125 per unit) ON TOP of the ~40-blade slot field. At the DK
  $0.30 line: +$16 (ST-1000) to +$38 (W-tier). Program-wide 63969-class
  demand is now modules + slot fields + BANK DECKS — the §5 item-2
  escalation (LCSC OOS, DK-depth-carried) and the 63968-1 LIF fallback
  (thin) both gain weight; LIF is ALSO the gang-force lever for wall
  seating (halves per-joint insertion force). Standing §6 item: the manual
  LCSC "Other Suppliers" RFQ on 63969-1 now carries tester volumes too.
- **Ladder v1.1 deltas** (minors overkill respec): +11 legs ≈ +$29
  resistors, +3 group switch/fuse sets ≈ +$4, mini-loop parts ≈ +$1.
- **Net §3a nudge**: ST-1000 BOM ≈ $545 → **≈ $620–640** (v1.1 legs + tabs
  + per-leg receptacles); ST-1300 similarly +~$80–100. At $1,299/$1,499
  list the margin reads ~2.0–2.1× — below the 3× convention like the rest
  of the ST value line, same standing owner call (§3a note).

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

1. **ESP32-P4 — OWNER RULED 2026-07-16: RIDE OUT THE BLIP** (Pro/Max are a
   distance from shipping — no buy action now). The round-2 facts stand as
   the standing discipline, not an escalation: mid-stream silicon transition,
   v3.x ships under NEW "X"-suffix MPNs (ESP32-P4NRW32X / NRW16X);
   **firmware images are NOT portable v1.x↔v3.x**; zero bare-chip stock or
   distributor listings today for either generation; no module SKU. STANDING
   POSTURE: design all new boards (testers, 12VHPWR Pro, Hub Pro) against
   **v3.x (NRW32X)**; watch C22387510 + C54540373; written revision
   confirmation on any eventual order; RE-CHECK the landscape at tester
   design lock (it will have moved by then).
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
5. **Fans — OWNER STEER 2026-07-16 (RULED): Arctic S12038-4K platform-wide.**
   Spec-sheet checked: 11.45 mmH₂O / 106 CFM / 600–4000 rpm PWM / dual
   Japanese ball bearing / 3.96 W / $14.99 — more pressure than the round-2
   Noctua iPPC-3000 pick at half the price (note: 38 mm deep, not 30 —
   budgeted at the duct mouth). ST unifies on it too (recommended, +$4–6:
   one spare-fan SKU across the line). Fallbacks retained: NF-F12 iPPC-3000,
   San Ace 9GA1212P4G001 (max-margin, loud). Final lock still gated on the
   duct P-Q measurement at the chassis prototype (§6.8); W tier runs 6×.
6. **Bimetal NC — RESOLVED.** LCSC has no verified-NC 120 °C part (KSD.301
   + KSD9700 attribute tables all read NO); the part is **Cantherm
   CS712025Y** [DK], SPST-NC explicit, 120 °C, $4.39@25, 506 stock. One
   manual check left: LCSC's unbrowsable Cantherm pool at BOM lock.
7. **L2 linear FETs — unchanged**: DigiKey-only class permanently
   (IXTH75N10L2 verniers, IXTK90N25L2 fast channel); consigned/hand-solder
   line; order-ahead posture.

## 6. Open items to the sourcing/pricing pass (carried)

1. Chassis + extrusion formal quotes (the remaining big swings) — now incl.
   the W two-lane console + ~500 mm extrusion class.
2. Max Hub pricing (Task-13; blocks Max-station all-in).
3. Replacement front-plate/field-kit SKU pricing at OQ-89 lock.
4. ADG1408 bandwidth confirmation (UNVERIFIED-by-table flag).
5. R-bank parallel-ladder value engineering (exact step table, §C.12) — now
   at two scales (Pro ~64 / W ~120 units).
6. Pod BOM when un-parked.
7. One manual LCSC "Other Suppliers" RFQ on 63969-1 (price the China path).
8. Duct P-Q measurement at chassis prototype → final fan lock (S12038-4K
   basis, 11.45 mmH₂O headroom; W duct needs the two-lane variant measured).
9. Display panel MPNs (main 2.8″ + bay 1.54″ IPS SPI module class) + bezel
   mechanicals at the chassis quote; S12038-4K volume/3-pack quote at order.
10. ~~W bundle module manifest~~ RULED 2026-07-16: configurator option
    against the port ledger (sketch §13). Remaining: owner pick on the deck
    CAN-expansion-jack DNP provision (relief valve 2) + configurator ledger
    rules incl. the ST 4-port case (Hub Standard = tester + 3 modules).
