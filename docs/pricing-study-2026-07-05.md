# Consumer-tier pricing study — Standard + Pro, landed vs. retail, bundles (2026-07-05)

**STUDY ONLY.** No spec, board, schematic, `CLAUDE.md`, or `docs/owner-queue.md` file is touched.
Answers the owner's 2026-07-05 ask: Standard/Pro Hub+Module pricing, landed vs. retail, bundles.
**Provenance key, used per figure:** **DIRECT** = fetched from the primary source this pass
(2026-07-05); **SOURCED** = relayed research, not independently re-checked (7/7 spot-checks of the
relay matched — high confidence); **OWNER** = owner-supplied ruling; **ALLOWANCE** = stated
assumption; **UNVERIFIED** = no reachable data, banded estimate.

## 0. Method

- **Quantities:** 100 (first run) and 1,000 (steady state) — the platform's own break points.
- **Landed** = parts + PCB fab + assembly + test/flash + packaging. Larger scope than the
  CLAUDE.md "BOM target" column — see §1.4.
- **Parts:** every line traces to the committed BOM CSVs. Real LCSC ladders (DIRECT/SOURCED,
  2026-07-05) now cover essentially every named part: ESP32-S3-WROOM $3.87@100/$3.72@650;
  ESP32-C6-MINI $2.85/$2.64; ESP32-S3-MINI $3.75/$3.50 (**OOS at LCSC**); INA228 $5.01@1→$3.58@1k
  (**OOS, reference-only ladder** — @100 interpolated $4.10); INA238 $1.65/$1.26 (stock 680);
  INA181A2 $0.26/$0.16; INA240A3 $2.73@1→$1.61@1k (@100 ~$2.20, stock 4,733); TJA1051 $0.40;
  TPS2121 $0.71 (stock 238, THIN); LP5907 $0.15; TLV7011 $0.35/$0.27; RJ45 C2683360 $0.27/$0.19;
  Keystone 3586 $0.3447@100, **no 1000-pc tier exists** (flat at 1k), stock 533; TE tab C86469
  $0.0795@100/$0.0644@2k (**the repo's "$0.04" figure is stale — actual ~2×**); 1mΩ shunt
  $0.3457/$0.2954; 4700µF $0.65@1k (stock 275); SK6812 ~$0.06; USB-C C319148 $0.25. Four jellybean
  passives (100nF/10k/1µF/10µF C-numbers) are **OOS reference-high** — in-stock alternates
  assumed at normal 0402/0603/0805 bands (cents). 0.5mΩ EPS/PCIe shunt: **LCSC line C1848841
  confirmed OOS** (DIRECT) — DigiKey-only, ~$0.45 band UNVERIFIED at tier.
- **Mini-Fit Jr connectors — OWNER RULING (2026-07-05, supersedes distributor pricing as the
  planning number):** owner acquires via MODDIY at **~$1/unit at volume** (24-pin J3, EPS
  87427-0802, PCIe 45586-0005). Verified-distributor reference band: 87427-0802 DIRECT DK
  $1.6709@100/$1.42@960 (stock 5,008); 45586-0005 SOURCED $3.47@100 (DK stock 0, 9wk — a supply
  footnote only, not a cost blocker, MODDIY path); 5569-24A1/A2 UNVERIFIED as literal PNs (fuzzy
  DK substitutes $2.24-4.79@100, unconfirmed crosswalks). Tables use **$1.00 OWNER/MODDIY**.
- **12V-2x6 (12VHPWR J3/J4):** whether it rides the MODDIY path is **UNCONFIRMED — priced both
  ways**. Tables use the verified figure: 2191161161 Cut-Tape DIRECT DK **$1.7637@100 /
  $1.5743@500**, stock 1,715, 15wk mfr lead (corrects this study's earlier "0 stock" flag — that
  was the tray sibling 2191160161). If MODDIY ~$1 confirms, shave ~$1.55/board.
- **PCB fab: UNVERIFIED for all boards** — JLC's quote calculator is JS-driven (static fetch
  shows $0.00); two web-synthesized reference figures were inconsistent and rejected. Fab columns
  are banded estimates (area-scaled, 4L; 2oz cable-board premium assumed). **Verified surcharges**
  (DIRECT, jlcpcb.com extra-charges page, updated 2026-01-27): small-board fee $0.02/pc (smallest
  side 1.5-3cm — hits the 81×17mm daughterboard; the 53×15 and 35×15 sit ON the 1.5cm boundary,
  ambiguous $0.02-0.05 band); ENIG >30%-area surcharge $0.8992/m² per 1% over (Hub is ENIG); V-cut
  surcharge <15mm/side in panel; large-board fee only >650cm² (largest board 72.5cm² — exempt).
- **Assembly — VERIFIED fee schedule** (DIRECT, JLC price page updated 2025-09-01, consignment
  page 2025-04-24), Economic class assumed: setup $8/order; stencil $1.50; SMT $0.0016/joint;
  Extended-part feeder $3/unique (Preferred-Extended exempt; Standard class $25/$50 setup +
  "$1.5" feeder line with a basic-vs-extended ambiguity — confirm at live quote); THT hand-solder
  $0.0157/joint (1-50k) → $0.0141 (50k-100k) + $3.50/order. **Consignment is supported incl.
  non-catalog parts** (engineer approval case-by-case, pre-ship to warehouse, no separate fee
  stated) — per the OWNER ruling it is **no longer gating**. Owner-acquired parts ≠ populated:
  tables carry JLC hand-solder THT fees; owner/local assembly is the zero-fee alternative (time,
  not dollars). Joint/Extended-part counts per board are this study's estimates (±20%).
- **Test/flash:** ALLOWANCE $1.25@100/$1.00@1k. **Packaging:** ALLOWANCE $0.75/$0.55. No
  enclosure/chassis costed (bare internally-mounted PCBAs; the repo has no enclosure design). No
  intentional-radiator cert (§6.14 subassembly posture); NRE/tooling excluded (§5).

## 1. Standard tier — landed unit cost

**1.1** Per spec §2.8 v1.4.0 the 24-pin/EPS/PCIe output rails cross to a passive daughterboard
per cable (24-pin ×1, EPS ×2, PCIe-2 ×2, PCIe-3 ×3); main-board Keystone clips (9/12/8/12) are in
the committed BOMs. **Parts column includes the daughterboard(s) all-in** (bare fab + tabs + THT
solder, per §1.2). Fab = main board only (UNVERIFIED band); Assembly = the verified JLC fee
schedule applied to estimated joint counts.

| Board | Parts+db @100 | @1k | Fab @100 | @1k | Assy @100 | @1k | Test+pkg @100 | @1k | **LANDED @100** | **@1k** |
|---|---|---|---|---|---|---|---|---|---|---|
| Hub Standard | $9.86 | $8.60 | $1.40 | $0.85 | $1.77 | $1.19 | $2.00 | $1.55 | **$15.05** | **$12.20** |
| 24-pin ATX (+1 db) | $30.98 | $27.18 | $1.30 | $0.80 | $2.03 | $1.41 | $2.00 | $1.55 | **$36.30** | **$30.95** |
| EPS 8-pin (+2 db) | $18.30 | $15.91 | $1.00 | $0.60 | $1.31 | $0.84 | $2.00 | $1.55 | **$22.60** | **$18.90** |
| PCIe 2-port (+2 db) | $16.66 | $14.33 | $1.05 | $0.65 | $1.33 | $0.86 | $2.00 | $1.55 | **$21.05** | **$17.40** |
| PCIe 3-port (+3 db) | $22.76 | $19.53 | $1.25 | $0.75 | $1.55 | $1.05 | $2.00 | $1.55 | **$27.55** | **$22.90** |
| 12VHPWR Standard | $28.95 | $23.00 | $1.25 | $0.75 | $1.78 | $1.23 | $2.75 | $2.05 | **$34.75** | **$27.05** |

**1.2 Daughterboards** (also feeds §4f accessories): bare fab est. $0.55@100/$0.35@1k (UNVERIFIED;
plus the DIRECT $0.02-0.05/pc small-board fee) + tabs + THT solder at the verified $0.0157/joint.
**Part note:** the db BOMs changed mid-task from the straight TE 63849-1 (C86469) to the
right-angle **TE 63951-1 (C591344)** — matches the perpendicular-card posture ruling; joint counts
unchanged. C591344 is unpriced anywhere (**UNVERIFIED — open item 2**); the C86469 ladder
($0.0795@100/$0.0644@2k DIRECT, stock ~43k) is the class anchor. All-in per db: ATX24 (9 tabs)
**$1.55@100/$1.18@1k**; EPS (6 tabs) **$1.22/$0.90** each; PCIe (4 tabs) **$1.00/$0.72** each. No
components on any db (BOM-confirmed).

**1.3 Cost drivers.** Hub — ESP32-WROOM $3.87 + 2×TPS2121 $1.42 + 4×RJ45 $1.08 + 4700µF ~$0.80.
**24-pin — 4×INA228 = $16.40@100, 53% of parts (OOS-reference ladder)** + 9 clips $3.10 + WSK2512
25mΩ $1.20 (DK band UNVERIFIED) + MODDIY header $1. EPS/PCIe — clips ($4.14/$2.76/$4.14 — **flat
at 1k, no tier exists**) + INA238 + 2-3 MODDIY headers + 0.5mΩ shunts (DK-only band). 12VHPWR-Std
— 6×INA240 $13.20@100 + 2×12V-2x6 $3.53 DIRECT + **pigtail assembly ALLOWANCE $4.00/$3.00** (wire
+ crimp female + labor — the D-7 "excluded" item, now carried) + 6×shunts $2.07. BOM-consistency
flag for the owner: EPS's USB-C is **C2765186 = a different part (SHOU HAN, $0.07)** while
PCIe/Hub/12VHPWR carry XKB C319148 $0.25 — a physical-part divergence, not a price break;
converge or bless.

**1.4 Reconciliation vs. CLAUDE.md "BOM targets"** (Hub $36, 24-pin $35*, EPS $32, PCIe-2 $38,
PCIe-3 ~$42, 12VHPWR-Std $49): the targets read as rough parts-only planning numbers; real
sourcing shows Hub parts $9.86@100 (the recorded ~$12.11 was ~1pc pricing), and 12VHPWR-Std lands
$34.75 vs. the $49 target even after adding the D-7 excluded items (consigned connectors,
pigtail, fab). **The 24-pin is the big correction:** the $35* footnote's own caveat ("expect a
modest increase over the INA238 baseline... revisit once the INA228 line is quoted") is now
quoted, and the increase is **not modest** — INA228 runs ~2.8× the INA238 per unit ($3.58 vs
$1.26 @1k), pushing 24-pin parts to ~$31 and landed to $36.30@100, coincidentally right at the
old $35 target *as a landed figure*. Sensitivity worth surfacing (owner's pen — INA228 is a
LOCKED spec §8 decision, not this study's call): the pin-compatible INA238 would cut ~$9.80/board
parts (~$34 at 3.5× retail) at the cost of the hardware energy/charge accumulators; the softer
lever is re-verifying INA228 at DigiKey before lock — the LCSC ladder is OOS-reference, and every
$1/unit there is $4/board ≈ $14 retail.

## 2. Pro tier — landed (Hub Pro/12VHPWR Pro schematics are 99-line skeletons; EPS/PCIe Pro don't exist)

| Board | Parts @100 | @1k | Fab @100 | @1k | Assy @100 | @1k | Test+pkg @100 | @1k | **LANDED @100** | **@1k** |
|---|---|---|---|---|---|---|---|---|---|---|
| Hub Pro (**estimate/floor**) | $15.89 | $13.34 | $1.70 | $1.00 | $2.00 | $1.45 | $2.00 | $1.55 | **$21.60** | **$17.35** |
| 12VHPWR Pro | $89.75 | $79.81 | $1.45 | $0.85 | $1.90 | $1.35 | $2.75 | $2.05 | **$95.85** | **$84.05** |
| EPS-Pro / PCIe-Pro (**bounded**) | — | — | — | — | — | — | — | — | **~$78-90** | **~$63-76** |

**2.1 Hub Pro** — delta over Hub Standard: ESP32-P4 core (bare P4NRW32 $4.47@100 SOURCED +
support ALLOWANCE → $5.50), +4 RJ45/ESD, 8× RS-485 receivers ($0.40 ea ALLOWANCE — no part chosen
anywhere in the repo). Sits well under the platform's $45 target — this delta model misses P4
board complexity (USB-HS SI, possible layer-count step). **Treat $45 as planning truth; $21.60 is
a floor.**

**2.2 12VHPWR Pro** — real bottom-up from the named parts list: P4 $5.50, 6×INA240 $13.20,
**LTC2358-18 $58.51@100 (DK, SOURCED via the max study; no LCSC listing at all; 1k tier unquoted,
~$55 ALLOWANCE) = 65% of parts — the defining Pro-tier economics fact**, REF3033 $0.34, RS-485
$0.40, 2×12V-2x6 $3.53 DIRECT, pigtail $4.00 ALLOWANCE, 6×shunt $2.07. Landed $95.85@100
reconciles with the platform's own $98-99 BOM target (that target evidently knew the ADC's cost —
unlike Hub Pro's).

**2.3 EPS/PCIe-Pro bound:** Standard landed (§1.1) + the Pro core delta ($95.85−$34.75 ≈ $61@100,
$57@1k), less a small allowance for fewer channels → **~$78-90@100**. A bound, not a design.

## 3. Retail

**3.1 Convention:** the only in-repo retail precedent is Max ($150-190 landed-scope BOM →
$499-599, ≈3.5×). Applying **3.5× on landed@100**, rounded to retail-natural points:

| Item | Landed @100 | ×3.5 | Retail (multiple) |
|---|---|---|---|
| Hub Standard | $15.05 | $52.7 | **$49** (3.3×) |
| 24-pin ATX | $36.30 | $127.1 | **$129** (3.6×) |
| EPS 8-pin | $22.60 | $79.1 | **$79** (3.5×) |
| PCIe 2-port | $21.05 | $73.7 | **$69** (3.3×) |
| PCIe 3-port | $27.55 | $96.4 | **$99** (3.6×) |
| 12VHPWR Standard | $34.75 | $121.6 | **$119** (3.4×) — or **$99** PMD2-match (2.8×), owner's call §3.2 |
| Hub Pro (est.) | $21.60 | $75.6 | **$79** (3.7×) |
| 12VHPWR Pro | $95.85 | $335.5 | **$329** (3.4×; clear of Max $499-599) |
| EPS/PCIe-Pro (bounded) | ~$78-90 | ~$273-315 | **$279-329 band, proposed/unpriced** |

**3.2 PMD2 anchor.** The only per-connector power-logging competitor, ElmorLabs PMD2, is **$99**
(single-connector logger, kHz-class "scope";
`docs/research/max-instrument-channel-decision-2026-06-11.md` §1 [I-6]). With real parts data,
12VHPWR-Std cost-plus lands **above** PMD2 at $119 — the honest choice: hold $119 and argue the
difference (one rail of a networked, always-on CAN system with per-pin current + NTC temperature,
not a standalone dongle), or match $99 as a deliberate 2.8×-margin beachhead SKU (defensible
*because* modules are attach revenue on an installed Hub). The whole-system comparison: base
bundle $149 (§4a) vs. PMD2 $99 buys four continuously-monitored rails plus a platform where the
next module is $69-119, not another instrument. If the MODDIY 12V-2x6 path confirms and INA240
re-verifies lower, $99 at ~3× becomes arithmetic, not a stretch.

## 4. Bundles

**Structural framing (owner correction, 2026-07-05):** the Hub is **not** hard-dependent on the
24-pin — the TPS2121 front-end ORs 5VSB/USB/MAIN_5V (§2.9), so a bare Hub runs on host USB. What
the 24-pin buys is **guaranteed, motherboard-independent standby telemetry** (USB soft-off power
is BIOS/ErP-dependent and unknowable pre-purchase) plus the four-rail INA228 story. The Hub
already senses its own power source (§2.9 dividers, IO9/IO10) — firmware can display
"USB-powered: add the 24-pin for always-on," a self-demonstrating upsell. The base bundle is the
**recommended** entry, not a forced minimum. Cable allowances (ALLOWANCE): RJ45 patch $5 retail
(~$1.50 landed) per module; JST 5VSB feed $4 (~$1.50 landed), only with a 24-pin.

| Item | Landed @100 | @1k | À la carte | In-bundle effective |
|---|---|---|---|---|
| Hub Standard (standalone) | $15.05 | $12.20 | $49 | $39 (base, −20%) |
| 24-pin ATX | $36.30 | $30.95 | $129 | $103 (base) |
| **(a) BASE — Hub + 24-pin + patch + feed ($9)** | $54.35 | $46.15 | 49+129+9 = **$187** | **$149 (−20%)** = 2.7× landed |
| EPS 8-pin | $22.60 | $18.90 | $79 | $67 (loaded, −15%) |
| PCIe 2-port | $21.05 | $17.40 | $69 | $59 (loaded) |
| 12VHPWR Standard | $34.75 | $27.05 | $119† | $101 (loaded) |
| **(c) COMPLETE SYSTEM, PCIe-2 config — Hub + 24-pin + EPS + PCIe-2 + 3 patch + feed ($19)** | $101.00 | $85.45 | 49+129+79+69+19 = **$345** | **$309 (−10%)** = 3.06× landed |
| **(c) COMPLETE SYSTEM, PCIe-3 config** (PCIe-3 swaps in) | $107.50 | $90.95 | **$375** | **$329 (−12%)** = 3.06× |
| **(c) COMPLETE SYSTEM, 12VHPWR config** (12VHPWR-Std swaps in) | $114.70 | $95.10 | **$395** | **$349 (−12%)** = 3.04× |
| **(d) LOADED — base + EPS + PCIe-2 + 12VHPWR + 3 patch ($15)** | $137.25 | $114.00 | 187+79+69+119+15 = **$469** | **$399 (−15%)** = 2.9× landed |
| Hub Pro (est.) | $21.60 | $17.35 | $79 | $71 (Pro, −11%) |
| 12VHPWR Pro | $95.85 | $84.05 | $329 | $294 (Pro) |
| **(e) PRO BENCH — Hub Pro + 12VHPWR Pro + patch ($5; no feed — no 24-pin, Hub runs on host USB)** | $118.95 | $102.90 | 79+329+5 = **$413** | **$369 (−11%)** = 3.1× landed |

† bundle tables use the $119 cost-plus figure; at the $99 PMD2-match option the loaded sum is
$449 → $379 (−16%) and the 12VHPWR complete-system config is $375 → $339, same shape throughout.

**(c) Complete System Bundle — source: OWNER follow-up, 2026-07-05 (verbatim): "What would a
complete system bundle standard retail for? Hub + 24 Pin + EPS + PCIe2 OR 3 OR 12VHPWR depending
on configuration of the user's system, configuration helper will probably be added later but
yeah."** Realized as ONE SKU, three GPU-path configurations, retailing **"from $309"** with +$20
config steps ($309 PCIe-2 / $329 PCIe-3 / $349 12VHPWR) — the flat steps map directly onto the
owner's config-helper concept (checkout picks the GPU path). Discounts sit inside the established
ladder (−10 to −12%) and every config holds >3× landed@100. A both-GPU-paths system (PCIe **and**
12VHPWR) is the LOADED bundle's territory at $399.

**(b) À la carte:** Hub $49 · 24-pin $129 · EPS $79 · PCIe-2 $69 · PCIe-3 $99 · 12VHPWR-Std $119
(or $99) · Hub Pro $79 est · 12VHPWR Pro $329.

**(f) Daughterboard+extension accessory SKUs (OQ-89):** db (§1.2) + wire + standard female
housing + retail pack (ALLOWANCE): 24-pin extension ~$4.10 landed → **$19.99**; EPS 2-set ~$6.00
→ **$24.99**; PCIe per-cable ~$2.75 → **$14.99** (pair $27.99). Retires the F-F 24-pin
bridging-cable SKU per v1.4.0.

**Margins:** base 2.74× / complete-system 3.04-3.06× / loaded 2.91× / Pro 3.10× landed@100 —
bundling costs discount dollars, not margin ratio. The base bundle is priced most aggressively on
purpose (platform beachhead); the complete-system SKU is the volume play; loaded's ~$262 gross
over landed is where the full-system sell pays.

## 5. Caveats, stock register, open items

- **Fab is the largest remaining uncertainty** — all base fab figures UNVERIFIED (JS-only quote
  calculator); only the surcharge schedule is DIRECT. Assembly uses the DIRECT fee schedule but
  this study's own joint/Extended-part counts (±20%), Economic class assumed.
- **Stock register (LCSC 2026-07-05, DIRECT/SOURCED):** TPS2121 **238** (Hub uses 2/board — 100
  Hubs = 200, MARGINAL); INA238 **680** (100 sets of EPS+both-PCIe need 700, MARGINAL); Keystone
  3586 **533** (<1 run of any family, known §8.10); 4700µF **275**; ESP32-S3-MINI **OOS**
  (12VHPWR-Std's MCU — beta 24-pin/EPS/PCIe are on C6, stock 2,220, unaffected); INA228 **OOS**
  (24-pin — priced off the reference ladder); 0.5mΩ shunt **OOS at LCSC** (EPS/PCIe → DigiKey);
  12V-2x6 CT **1,715** (covers a 100-run needing 200; 15wk mfr lead, single-source); 45586-0005
  DK **0** (MODDIY path covers it); jellybean R/C OOS (in-stock alternates, trivial).
- **Owner-acquired ≠ populated:** MODDIY connectors still need THT population — costed here via
  JLC's verified hand-solder fees (consignment supported, engineer approval case-by-case, no
  stated fee); owner/local soldering is the zero-fee alternative (time cost, unmodeled).
- **No NRE/tooling/cert amortized**; no enclosure costed; channel = direct-to-consumer (a
  distribution channel at 30-50%/tier would force higher MSRPs or compressed margin — unmodeled).
- **Pro tier:** Hub Pro and EPS/PCIe-Pro are estimates against boards that don't exist; 12VHPWR
  Pro is parts-list-real but unrouted. Directional, not quotable.
- **Open items before any BOM lock:** (1) live JLC gerber+BOM quote per board — the single
  biggest numeric uncertainty; (2) TE 63951-1 / C591344 price (db tab, currently class-anchored);
  (3) INA228 DigiKey re-verify + stock plan (biggest single-part sensitivity, $4/board per $1);
  (4) MODDIY 12V-2x6 confirm (~$1.55/board swing on both 12VHPWR boards); (5) 0.5mΩ
  CSS2H-2512R-L500F DK reel pricing at tier; (6) LTC2358-18 volume quote (65% of 12VHPWR-Pro
  parts); (7) USB-C part convergence (C2765186 vs C319148); (8) pigtail assembly real quote
  (ALLOWANCE $4 today); (9) JLC Standard-class feeder-fee ambiguity.

---

## Addendum (2026-07-05, post-study DigiKey re-verify — closes open item #3)

Live DigiKey pricing (fetched 2026-07-05, DIRECT) supersedes the LCSC OOS-reference INA228
ladder used above: **INA228AIDGSR $4.68@1 / $2.96@100 / $2.82@250 / $2.58@2,500 (T&R), stock
5,240** — the part is freely available, just not at LCSC. **INA238AIDGSR $3.26@1 / $2.02@100 /
$1.88@500 / $1.74@2,500, stock 1,753.** Consequences:

- The 24-pin's INA228 line is 4×$2.96 = **$11.84@100** (not $16.40): landed ≈ **$31.75**,
  retail at 3.5× ≈ $111 → **$109-119** band (not $129).
- The true INA228-over-INA238 premium is **$3.76/board @100q** ($0.84/part × 4 = $3.36 @2.5k),
  not ~$9.80 — the accumulator/20-bit premium is small at real sourcing.
- Complete System Bundle re-anchored: **keep-INA228 = $279 / $299 / $319** (3.0-3.1× landed);
  **INA238-swap = $259 / $279 / $299** (2.99-3.0×; $249 on config A = 2.87×, below the 3×
  convention but available as a marketing call).
- Accuracy/rate equivalence of the INA238 swap (why it stays on the table): same ±0.1%
  gain-error class, same conversion engine and rates, same VSSOP-10 land (drop-in). 16-bit vs
  20-bit changes current LSB 2.5mA vs 0.16mA on the 2mΩ shunts — both orders finer than the
  gain-error floor on 10-25A rails, so reported accuracy is gain-bound and equivalent. Energy
  reporting survives as firmware integration of the §6.10 1kHz stream (error likewise
  gain-bound); what is genuinely lost is only the hardware energy/charge accumulators
  (host-independent accumulation). Assembly note: JLC assembles from LCSC stock — a DigiKey-
  sourced INA228 becomes a consigned/pre-shipped line at JLC or moves the sensing ICs to the
  owner-population path; factor per the §2 consignment rules.
