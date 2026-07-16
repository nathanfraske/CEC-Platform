# PSU tester — BOM draft v0 + full-retail roll-up (2026-07-16)

Itemized from the architecture sketch (REV B + §3d OVP-A RULED + §10 quality
refinements). Prices: **[V]** = verified this week (LCSC/vendor page, see the
component-research doc), **[P]** = platform part already priced in the repo,
**(~)** = class estimate to firm at the sourcing pass. Quantities are the
sketch's channel plan. This is a pre-schematic BOM — freeze at schematic.

## 1. Tester Pro — itemized

| Subsystem | Part / class | Qty | Unit $ | Ext $ |
|---|---|---|---|---|
| MCU | ESP32-P4 module (PSRAM variant) (~) | 1 | 9.00 | 9.00 |
| CAN | TJA1051T/3 [P] + jack/DETECT/PESD [P] | 1 set | 2.00 | 2.00 |
| RS-485 stream TX | THVD1450-class (~) | 1 | 1.20 | 1.20 |
| USB | PD sink ctrl (AP33772-class) + USB-C + USBLC6 (~) | 1 set | 3.50 | 3.50 |
| Setpoints | DAC80508 (int. ref 2 ppm/°C typ) (~ verify LCSC) | 1 | 12.00 | 12.00 |
| CC loops | OPA2277-class precision op-amps | 8 | 2.00 | 16.00 |
| Fast loop | OPA810-class + gate stage (~) | 1 set | 6.00 | 6.00 |
| Trip watch | INA181A2 [P] + TLV7011 [P] | 8+8 | 0.55/0.35 | 7.20 |
| Vernier FETs | TO-247 Linear-L2 (IXTH75N10L2-class ladder) (~) | 8 | 14.00 | 112.00 |
| Fast-channel FETs | IXTK90N25L2 **[V] LCSC C2831650** | 4 | 40.38 | 161.52 |
| Ballast/gate networks | precision R + networks (~) | — | — | 10.00 |
| Loop shunts | CSS2H-2512 family [P] + fast Kelvin shunt | 9 | 1.30 | 11.70 |
| R-banks | 100 W alu-shell WW (~3.2 kW installed) (~) | 32 | 5.00 | 160.00 |
| Bank plates/hardware | mounting, insulators (~) | — | — | 50.00 |
| Bank switching | commodity NFETs + drivers + fuses/holders (~) | 24+ | — | 42.00 |
| SCP crowbars | switch-FETs ∥ + surge shunts + TVS + fuses (§3b) (~) | 4 blk | 8.50 | 34.00 |
| OVP-A stage (RULED) | TPS55289 + L/C + relays + protection (~) | 1 set | 20.00 | 20.00 |
| Thermal sensing | NCP15XH103 [P] ×16 + bimetal switches ×2 | — | — | 4.00 |
| Aux rails | bucks 12 V→5/3.3, gate rail (~) | — | — | 5.00 |
| Fans | dual-ball 120 mm PWM w/ tach (§10.5) (~) | 4 | 10.00 | 40.00 |
| FET extrusion | 300 mm forced-air class (~) | 1 | 45.00 | 45.00 |
| Chassis | sheet-metal console + duct + grilles, low-qty (~) | 1 | 200.00 | 200.00 |
| Fixture heads | OQ-89 assemblies + replaceable front plate (~) | 1 set | 100.00 | 100.00 |
| PCBs | main 4L 2 oz + fast-channel/fixture boards (~) | — | — | 75.00 |
| AC sense pod | pickup + clamp CT + comparator (parked w/ owner, §3c) (~) | 1 | 20.00 | 20.00 |
| Misc | passives, harness, hardware (≈5 %) (~) | — | — | 55.00 |
| **Tester Pro BOM** | | | | **≈ $1,201** |

Band honesty: the L2 SKU-ladder swing (TO-247 at ~$8–15 vs all-TO-264 at
$40) and chassis quotes put the honest band at **$1,050–1,500**, mid ≈ $1,200
— consistent with sketch §8a and the canonical §6 class band.

## 2. Tester Max — delta over Pro

| Subsystem | Part / class | Qty | Unit $ | Ext $ |
|---|---|---|---|---|
| Fast ADC | AD9253-80 **[V] LCSC C578831** | 1 | 41.67 | 41.67 |
| FPGA | GW5A-25 MG121 **[V] LCSC C45617374** | 1 | 46.88 | 46.88 |
| AFE | 4× 20 MHz AC-coupled front ends + mux (~) | 4 | 6.50 | 26.00 |
| T1 link | 100BASE-T1 PHY (module pattern) (~) | 1 | 6.00 | 6.00 |
| 2nd fast channel | L2 ×4 + fast loop + switch/fixture slice (~) | 1 | 170.00 | 170.00 |
| PCB delta | digitizer lane routing/layers (~) | — | — | 15.00 |
| **Max delta** | | | | **≈ $306** |
| **Tester Max BOM** | | | | **≈ $1,507** (band $1,350–1,900; +$100–150 for the 2 kW ballast option) |

## 3. Full retail roll-up (what a shop actually pays)

Landed = BOM +19 % (assembly/test/freight, canonical convention). Module/Hub
retails from `docs/pricing-study-2026-07-05.md` (Hub Pro $79, 12VHPWR Pro
$329, Complete-System class $309–349, patches ~$5).

| | **Pro station** | **Max station** |
|---|---|---|
| Tester BOM (mid) | ~$1,200 | ~$1,505 |
| Tester landed | ~$1,430 | ~$1,790 |
| Ruled tester list | $3,495 (2.4× landed mid) | $5,995–6,995 (3.3–3.9× mid; 2.2–2.6× at band-top landed) |
| + instrumentation | standard module set (+$500 list class) → **$3,995 w/ modules (ruled)** | Pro-class module set incl. 12VHPWR Pro (+$650–800 list class) — inside the ruled $5,995–6,995 w/ modules |
| + Hub Pro (REV B suite needs RS-485 termination) | +$79 | Max Hub — unpriced (Task-13 BOM item; interim: Hub Pro runs the suite with the tester's T1 dark) |
| + patches/pod/plate spare | ~$45–75 | ~$45–75 |
| **Turnkey station street** | **≈ $4,119–4,149** → suggest a **PRO STATION SKU at $4,199** (one box, one price) | **≈ $6,995 top-config as ruled**; Max-Hub pricing is the open lever |
| Consumable | replacement front plate: ~$30–45 landed → **$79–99 retail** (the recurring line; price at OQ-89 lock) | same |

Margin picture at the itemized mids: Pro station ≈ **2.4–2.6× landed all-in**
(healthy, above the capital-equipment floor, below the platform 3× — as the
canonical margin-honesty note anticipated); Max ≈ 2.6–3.3× depending on the
Max-Hub answer. The two swings that matter at pricing lock: the L2 SKU
ladder (±$150 on Pro BOM) and the chassis quote (±$100).

## 3a. Standard tester value line (un-shelved, owner 2026-07-16 — sketch §11)

| | **ST-1000** | **ST-1300** |
|---|---|---|
| BOM (integrated instrumentation incl. 12VHPWR per-pin INA240 bank) | ≈ $537 | ≈ $585 |
| Landed (+19 %) | ≈ $639 | ≈ $696 |
| **List (single SKU, nothing else to buy)** | **$1,299** (2.03×) | **$1,499** (2.15×) |
| Feature fence | static + regulation verdict, T1/T3/T6, cross-load corner, OCP-by-steps, SCP, 5VSB peak, −12 V, per-pin 12VHPWR soak, report | same |
| Not present (the Pro upsell) | transient engine, OVP check, RS-485 stream, module composability story | same |

Sits above the $750–950 DIY-Kunkin floor and at dead-SunMoon money; ~2×
multiples are test-gear-normal but below platform convention — owner call at
pricing lock alongside the Pro/Max margin question.

## 3b. Slot-in bundle scenario (sketch §12 — PROPOSED, recommended)

If the blade slot field is adopted: fixture plate ($85–100) → blade field +
rails (~$40); bundles ship modules factory-slotted without retail
daughterboards; OQ-89 assemblies sell separately as the un-dock "field kit."

| Bundle | Tester BOM Δ | Bundle landed (tester + modules + Hub) | List | × |
|---|---|---|---|---|
| **ST-1000 BUNDLE** (Std modules + Hub Std slotted/docked) | $537 → ~$457 | ~$645 | **$1,299** | 2.0 |
| **ST-1300 BUNDLE** | $585 → ~$505 | ~$700 | **$1,499** | 2.1 |
| **PRO BUNDLE** (Std set + Hub Pro; 12VHPWR-Pro optional +$329) | $1,201 → ~$1,146 | ~$1,495 | **$3,995** | 2.7 |
| **MAX BUNDLE** (Pro-class set + Max Hub TBD) | $1,507 → ~$1,452 | ~$1,900 + Max-Hub | **$6,995** | ~2.8–3.2 |
| Field kit (OQ-89 daughterboard + extension, per module) | — | ~$12–18 | **$39–49** | — |
| Input-saver pigtail set (the new per-test wear consumable) | — | ~$8–12 | **$29–39** | — |

Margins IMPROVE ~0.2–0.4× across the line vs separate-pieces pricing while
the customer gets a nicer product — the rare win-win. Supersedes §3a's
integrated-ST sensing scenario if adopted (same price, real modules).

## 4. Open items feeding the sourcing/pricing pass

1. L2 ladder quotes (TO-247 IXTH class × 8) + pulse-SOA check on the
   fast-channel TO-264s — the single biggest BOM swing.
2. DAC80508 LCSC/JLC availability (TI stocking is patchy there).
3. Chassis + extrusion low-qty quotes (2nd biggest swing).
4. Max Hub pricing (blocks the Max-station all-in; Task-13 item).
5. Replacement-plate SKU pricing at OQ-89 lock (the consumable annuity).
6. Fan MPN (dual-ball, tach, PWM, 40 °C-rated life class).
7. Pod BOM firm-up when the owner un-parks it (§3c).
8. ST line: integrated-sensing carve-out — LIKELY SUPERSEDED by the §3b
   slot-bundle scenario (owner sign-off); R-bank volume pricing (the ST BOM
   is resistor-and-chassis dominated).
9. Slot-bundle mechanicals (sketch §12): gang-insertion answer (factory
   press vs cam assist), blade-field tolerance stack across 10 joints,
   module support rails — extends the OQ-86 sample gate; field-kit + saver
   pigtail SKU pricing.
