# Consumer-tier pricing study — Standard + Pro, landed vs. retail, bundles (2026-07-05)

**STUDY ONLY.** No spec, board, schematic, `CLAUDE.md`, or `docs/owner-queue.md` file is touched.
Answers the owner's 2026-07-05 ask: Standard/Pro Hub+Module pricing, landed vs. retail, and bundle
structure. All parts figures trace to the committed BOM CSVs or a named repo doc; everything else
is a stated estimate. Web prices pulled 2026-07-05; **UNVERIFIED** marks anything a source couldn't
confirm.

## 0. Method (read before the tables)

- **Quantities:** 100 units (first production run) and 1,000 units (steady-state), the platform's
  own break points (`docs/max-part-selection-2026-07-05.md` §6-7 uses the same pair).
- **Landed cost** = parts + PCB fab + assembly (incl. consigned-part handling) + test/flash + packaging.
  This is a materially larger scope than the CLAUDE.md board-table "BOM target" column — see §1.4.
- **Parts pricing method:** every line traces to the board's committed BOM CSV (reference,
  qty, LCSC#). Where this repo already records a real LCSC/Digi-Key quote (Keystone 3586 blade
  clip C238113, TE 63849-1 tab C86469, CSS2H-2512R-1L00F shunt C4175647, INA240A3DR, LTC2358-18,
  REF3030/3033, RJ45 FTP jack, ESP32-P4NRW32 — all cited in `docs/max-part-selection-2026-07-05.md`
  and `docs/standard-tier-review/output-daughterboard-study-2026-07-04.md` §8.9-8.10), that figure
  is used directly. For the ~40 generic small passives/protection parts per board with no cached
  $ figure, unit price is **banded by package/class** (0402 R/C ≈$0.002-0.004@100q; SOT-23 small
  IC ≈$0.10-0.15@100q; connectors per class) and cross-checked against this repo's own real
  1pc→100pc break ratios where both are known: Keystone 3586 $0.6178→$0.3447 (-44%), AD7606B
  $18.91→$14.66 (-22%), ESP32-P4NRW32 $5.72→$4.47 (-22%), RTL8211F $1.52→$1.04 (-32%). Banded
  low-value passives use the steeper end of that range at 100q, ICs/modules the shallower end.
  Consigned parts (no LCSC line — Mini-Fit Jr headers, the 12V-2x6) are priced from general
  Digi-Key/Mouser bands. **One got a real quote this pass:** the 12V-2x6 (Molex 2191161161/
  2191160161) is a live Digi-Key break — $1.99@1 / $1.44@100 / ~$1.22@1k tray — used directly below,
  well under this study's own earlier band estimate; **that same listing shows 0 stock, 15-week
  lead time**, a real supply flag (§5). The Mini-Fit Jr headers (24-pin J3, EPS/PCIe J_IN*)
  couldn't be priced live this pass (Mouser blocked the fetch, Digi-Key search missed the exact
  part) and stay **UNVERIFIED band estimates — reverify at BOM lock**.
- **PCB fab:** 4-layer FR4 at the measured board sizes (`docs/standard-tier-review/routing-foundation-2026-07-04.md`
  §1 stackup + this pass's own `pcbnew`-free bounding-box read of each committed `.kicad_pcb`), 2oz
  outer per the cable-board convention (24-pin is 1oz outer, a flagged deviation). Fab $ are
  estimated from typical JLCPCB 4-layer small-board bands. **One live reference found:** a JLCPCB
  pricing page reports $70.60 for a 100×100mm 4-layer board at 100pc (ENIG/2oz spec-match
  unconfirmed, likely a base HASL/1oz figure), i.e. ~$0.71/board per 10,000mm² before any
  ENIG/2oz/complexity premium — suggests the estimates below may run conservative (high) for the
  mostly-sub-10,000mm² Standard boards; treated as a ceiling check, not re-derived from one point.
  **Still UNVERIFIED against this project's exact specs** — a live gerber quote is the real next step.
- **Assembly** = SMT setup/joint fees + a THT/consigned-connector handling adder, banded from
  JLCPCB's published SMT fee structure (setup fee amortized per unique part, near-zero per-joint
  for Basic-library parts, an added fee per Extended-library or off-catalog part) — UNVERIFIED,
  not a live quote.
- **Test/flash:** stated assumption, $1.25@100 / $1.00@1k (functional test + firmware flash).
- **Packaging:** stated assumption, $0.75@100 / $0.55@1k — antistatic bag + small box/label +
  mounting hardware. **No enclosure/chassis is costed**: every board here is a bare PCBA that
  mounts inside the PC case (M3 chassis-ground standoffs), not a boxed standalone product — this
  repo has no enclosure design or cost anywhere (confirmed by search).
- FCC-15B: no intentional-radiator certification is amortized (Standard/Pro carry no Wi-Fi;
  §6.14 posture is subassembly/unintentional-radiator). NRE/tooling/stencil costs are excluded
  throughout — see §5.

## 1. Standard tier — landed unit cost

**1.1 Main boards + their mandatory output daughterboard(s).** Per spec §2.8 v1.4.0, 24-pin/EPS/
PCIe now ship output rails through a passive daughterboard per cable (24-pin ×1, EPS ×2,
PCIe-2 ×2, PCIe-3 ×3) — main-board Keystone 3586 clips are already in the committed BOMs
(9/12/8/12 joints, matching `output-daughterboard-study-2026-07-04.md` §8.9 exactly).

| Board | Parts @100q | Parts @1k | PCB fab @100q | @1k | Assembly+consigned @100q | @1k | Test+pkg @100q | @1k | **LANDED @100q** | **LANDED @1k** |
|---|---|---|---|---|---|---|---|---|---|---|
| Hub Standard | $8.60 | $7.05 | $1.20 | $0.70 | $2.20 | $0.75 | $2.00 | $1.55 | **$14.00** | **$10.05** |
| 24-pin ATX (+1 db) | $17.70 | $15.00 | $1.55 | $0.93 | $3.20 | $1.10 | $2.00 | $1.55 | **$24.45** | **$18.58** |
| EPS 8-pin (+2 db) | $13.00 | $10.90 | $1.80 | $1.11 | $2.80 | $0.95 | $2.00 | $1.55 | **$19.60** | **$14.51** |
| PCIe 2-port (+2 db) | $11.80 | $9.82 | $1.85 | $1.14 | $2.80 | $0.95 | $2.00 | $1.55 | **$18.45** | **$13.46** |
| PCIe 3-port (+3 db) | $15.90 | $13.24 | $2.40 | $1.47 | $3.00 | $1.00 | $2.00 | $1.55 | **$23.30** | **$17.26** |
| 12VHPWR Standard | $17.58 | $14.56 | $1.10 | $0.65 | $3.50 | $1.20 | $2.75 | $2.05 | **$24.93** | **$18.46** |

**1.2 Daughterboard unit reference** (feeds §1.1 above and the accessory SKUs in §3e): board fab
(4L 2oz, tiny — 500-1341mm², est. $0.55@100/$0.35@1k) + TE FASTON tabs + THT hand/wave-solder
allowance. **Part note:** the three daughterboard BOMs changed underneath this pass, mid-task, from
the straight TE 63849-1 (C86469, priced at "from $0.0405" in `output-daughterboard-study-2026-07-04.md`
§8.10) to the **right-angle TE 63951-1 (C591344)** — matches the boards' own "stands perpendicular,
tabs exit the board face" posture ruling; joint counts unchanged (9/6-per-board/4-per-board).
C591344 has no cached price here; same TE FASTON class is assumed (~$0.045@100/$0.035@1k each) but
**UNVERIFIED — reverify C591344 specifically** (a right-angle stamped tab can price a few cents
above the straight part this repo priced). ATX24-db (81×17mm, 9 tabs) ≈$1.05@100/$0.72@1k; EPS-db
(53×15mm, 6 tabs, ×2/module) ≈$0.72@100/$0.51@1k each; PCIe-db (35×15mm, 4 tabs, ×2-3/module)
≈$0.63@100/$0.44@1k each. No active/passive components on any daughterboard (BOM-confirmed).

**1.3 Biggest cost drivers, by board:** Hub — ESP32-S3-WROOM-1-N16R8 (~45% of parts) + 4×RJ45 FTP
jack + 7×SK6812. 24-pin — 4×INA228 + 9×Keystone clip (~$3.10@100) + the Mini-Fit Jr J3 input header
(consigned, est. $1.20@100 — UNVERIFIED, no live quote reached). EPS/PCIe — Keystone clips
(12/8/12 × $0.345@100) rival the sense ICs. 12VHPWR-Std — 6×INA240A3DR ($8.10@100, the single
largest BOM-line cost on the board) + 2×Molex 12V-2x6 J3/J4 (**real Digi-Key quote found this
pass**, part 2191160161, the tray-pack sibling of the schematic's 2191161161 T&R: $1.44@100 /
~$1.22@1k each — well below this study's earlier $3.00@100 estimate; **flag: Digi-Key shows 0
stock, 15-week lead time** on that exact listing, a real supply risk, not just a price question)
+ 6×CSS2H shunt.

**1.4 Reconciliation against CLAUDE.md board-table "BOM target"s.** Those targets (Hub $36, 24-pin
$35*, EPS $32, PCIe-2 $38, PCIe-3 ~$42, 12VHPWR-Std $49) predate this repo's own real sourcing
passes and the v1.4.0 daughterboard architecture. Two are already measured stale, independent of
this study: Hub's recorded sourcing-pass total was **~$12.11 parts-only** (`CLAUDE.md`, 2026-06-05
— reads as ~1pc-equivalent pricing, consistent with our $8.60@100 after typical qty breaks), and
12VHPWR-Standard's was flagged **"$21 parts EXCLUDES consigned J3/J4 + pigtail assembly + 4L/2oz
fab — re-price the $49"** (`SYNTHESIS-beta-plan.md` D-7). This study's $24.93@100 landed figure is
the first pass at that re-price (parts alone excl. J3/J4 recompute to ~$14.70@100, still below the
documented $21, again consistent with $21 being ~1pc pricing), and it still lands under the old
$49 — **"BOM target" here has always meant a rough parts-only number, not a landed cost**, and the
gap predates daughterboards. 24-pin and EPS/PCIe never had a computed BOM at all (targets were
placeholders) — their landed figures here (24-pin $24.45, EPS $19.60, PCIe $18.45-23.30 @100q) are
the first grounded numbers for these boards.

## 2. Pro tier — landed unit cost (no built board for Hub Pro; EPS/PCIe Pro are proposed, unpriced SKUs)

| Board | Parts @100q | Parts @1k | Fab @100q | @1k | Assy+consigned @100q | @1k | Test+pkg @100q | @1k | **LANDED @100q** | **LANDED @1k** |
|---|---|---|---|---|---|---|---|---|---|---|
| Hub Pro (**estimate**) | $14.86 | $12.30 | $1.60 | $0.95 | $3.00 | $1.00 | $2.00 | $1.55 | **$21.46** | **$15.80** |
| 12VHPWR Pro | $79.54 | $67.44 | $1.30 | $0.75 | $3.50 | $1.20 | $2.75 | $2.05 | **$87.09** | **$71.44** |
| EPS-Pro (**bounded**) | — | — | — | — | — | — | — | — | **~$75-92** | **~$60-72** |
| PCIe-Pro (**bounded**) | — | — | — | — | — | — | — | — | **~$78-98** | **~$62-77** |

**2.1 Hub Pro** has no schematic content (`hubs/hub-pro/hub-pro.kicad_sch` is a 99-line skeleton,
one placeholder connector — confirmed by reading the file). Constructed as a delta over Hub
Standard: ESP32-P4 module-class MCU (est. $5.50@100 vs. WROOM's $3.90, using the Max study's bare
ESP32-P4NRW32 $4.47@100 + support-part allowance), doubled RJ45/DETECT-ESD for 8 ports, and 8×
RS-485 streaming receivers (new subsystem, allowance ~$0.40/receiver — no part chosen anywhere in
the repo). **This $21.46 sits well under the platform's own $45 Hub Pro target** — likely because
this delta model doesn't capture P4-specific board complexity (USB-HS signal integrity, a possibly
higher layer count, larger connector footprint) that a real Hub Pro layout would add. Treat $45 as
the more trustworthy planning number until a board exists; this $21.46 is a floor, not a point
estimate.

**2.2 12VHPWR Pro** has a full named parts list (`modules/12vhpwr-pro/README.md`, CLAUDE.md) even
though its schematic is likewise a 99-line skeleton — so this is a real bottom-up build, not a pure
delta: ESP32-P4 (~$5.50), 6×INA240A3DR (~$8.10, same as Standard), **LTC2358-18 ($58.51@100,
Digi-Key — `max-part-selection-2026-07-05.md` §1 — no LCSC listing at all)**, REF3033 (~$0.32,
same class as Standard's REF3030), RS-485 transceiver (~$0.40 allowance), 2×12V-2x6 (real Digi-Key
quote, $1.44@100 each — §1.3), 6×shunt (~$2.07), CAN/USB/RJ45/misc (~$2.30). **The LTC2358-18 alone
is ~74% of this board's parts cost** — the defining economics fact of the Pro tier. This study's
$87.09@100 landed figure reconciles closely with the platform's own $98-99 BOM target (a rare case
where the old target appears to have been set with real knowledge of the ADC's cost), unlike Hub
Pro's target.

**2.3 EPS-Pro/PCIe-Pro bound** (no project exists — confirmed, no `eps-8pin-pro`/`pcie-*-pro`
directory in the repo): method is Standard-tier landed cost (§1.1) **plus** the 12VHPWR-Pro-over-
Standard "Pro electronics core" delta (P4 MCU + LTC2358-18 + REF3033 + RS-485, ≈$62@100/$53@1k —
$87.09 minus $24.93, a delta the connector-price correction leaves unchanged since it subtracts out
of both), less a modest discount for fewer sense channels per cable than 12VHPWR's 6-pin array.
This is a bound, not a design — these SKUs are proposed only, per the brief.

## 3. Retail pricing

**3.1 Multiplier convention.** The only in-repo retail precedent is the Max tier: $140-170 BOM →
$499-599 retail, i.e. **≈3.5× on a landed-cost basis** (the Max study's own "$150-190 BOM" already
folds in PCB-fab and connector allowances — the same scope as this study's "landed," not a
parts-only figure). Applying **3.5× to the @100q landed cost**, rounded to a retail-natural point:

| Item | Landed @100q | ×3.5 | Retail |
|---|---|---|---|
| Hub Standard | $14.00 | $49.0 | **$49** |
| 24-pin ATX | $24.45 | $85.6 | **$89** |
| EPS 8-pin | $19.60 | $68.6 | **$69** |
| PCIe 2-port | $18.45 | $64.6 | **$69** |
| PCIe 3-port | $23.30 | $81.6 | **$79** |
| 12VHPWR Standard | $24.93 | $87.3 | **$89** (cost-plus) — or **$99** at deliberate PMD2-parity (§3.2), a 4.0× multiple |
| Hub Pro (est.) | $21.46 | $75.1 | **$79** |
| 12VHPWR Pro | $87.09 | $304.8 | **$299** (3.4×, leaves headroom under Max's $499-599) |
| EPS-Pro / PCIe-Pro (bounded) | ~$75-98 | ~$263-343 | **$269-349 band, unpriced/proposed** |

**3.2 PMD2 sanity anchor.** The only per-connector power-logging competitor found, ElmorLabs PMD2,
sells at **$99** as a self-contained single-connector logger with a slow-logger "scope" mode
(`docs/research/max-instrument-channel-decision-2026-06-11.md` §1, [I-6]). Cost-plus arithmetic
puts 12VHPWR-Std at $89 (§3.1) — genuinely cheaper than PMD2 for a rail-level current+voltage+
temperature instrument. Real choice, not one number: sell at $89 (honest cost-plus), or hold **$99
flat parity with PMD2** (4.0×, still defensible — the $10 is easy extra margin an anchor buyer
already expects). Either way, position it honestly: **12VHPWR-Std is one rail of a networked,
always-on, CAN-bus system**, not a standalone dongle. The fairer comparison is Hub+24-pin ($49+$89=
$138 à la carte, or the $119 base bundle, §4a) vs. PMD2: for about the same money plus a modest
premium, the customer gets four continuously-monitored rails instead of PMD2's one, plus a
CAN-networked platform where further modules cost far less than $99 each (the MCU/USB/host cost is
already sunk in the Hub) — that marginal-module economy is the core bundle argument in §4.

## 4. Bundle structure

**Structural correction (owner, 2026-07-05):** the Hub is **not** hard-dependent on the 24-pin.
The Hub's TPS2121 front-end ORs 5VSB / USB VBUS / MAIN_5V (§2.9), so a bare Hub runs on host USB
power alone. What the 24-pin actually buys is **guaranteed, motherboard-independent standby
telemetry** (S5/soft-off persistence, RTC-wake) plus the four-rail INA228 system-power story —
USB-only standby power is BIOS/ErP-dependent and not universal, and not knowable before purchase.
One nice built-in fact: the Hub already senses which source is powering it (§2.9 rail-sense
dividers into IO9/IO10) — firmware can literally tell the customer *"USB-powered: standby telemetry
unavailable — add the 24-pin module for always-on"* at runtime. The upsell is self-demonstrating,
not a sales pitch. Bundle structure below reflects this: the base bundle is the **recommended**
entry point on value grounds, not a forced minimum.

Cable retail allowances (stated assumption, not sourced — see note**): one RJ45 patch cable
(module-to-Hub link, every module needs exactly one regardless of cable count) ≈$5 retail; the one
JST 5VSB feed cable (24-pin-to-Hub bulk power, needed only when a 24-pin is present) ≈$4 retail.

| Item | Landed @100q | Landed @1k | À la carte retail | In-bundle effective |
|---|---|---|---|---|
| Hub Standard (standalone)* | $14.00 | $10.05 | $49 | — (à la carte only) |
| 24-pin ATX | $24.45 | $18.58 | $89 | $73 (base bundle) |
| **(a) BASE bundle — Hub + 24-pin + 1 patch + 1 feed cable ($9)** | $41.45 | $30.63 | $49+89+9=**$147** sum | **$119 (-19%)** |
| EPS 8-pin | $19.60 | $14.51 | $69 | $59 (loaded) |
| PCIe 2-port | $18.45 | $13.46 | $69 | $59 (loaded) |
| 12VHPWR Standard | $24.93 | $18.46 | $99† | $84 (loaded) |
| **(c) LOADED bundle — base bundle + EPS + PCIe-2 + 12VHPWR-Std + 3 more patch cables ($15)** | ~$109 | ~$80 | $147+69+69+99+15=**$399** sum | **$339 (-15%)** |
| Hub Pro (est.) | $21.46 | $15.80 | $79 | $71 (Pro bundle) |
| 12VHPWR Pro | $87.09 | $71.44 | $299 | $265 (Pro bundle) |
| **(d) PRO BENCH bundle — Hub Pro + 12VHPWR Pro + 1 patch cable ($5, no feed cable: no 24-pin in this bundle, Hub runs on host USB)** | ~$111 | ~$88 | $79+299+5=**$383** sum | **$349 (-9%)** |

† bundle/à-la-carte tables use the $99 PMD2-parity price (§3.2) as the chosen retail figure for
12VHPWR-Std, not the $89 cost-plus alternative — pick one before publishing a price list.

\* Hub-only ships functional on host USB power; it loses standby-state telemetry unless the
motherboard keeps USB powered at soft-off (not universal, not discoverable pre-purchase) — one-line
disclosure the product page/firmware should carry.
\*\* cable landed cost is folded into the "Landed" column above via the per-cable retail allowance
at roughly a 3× markdown to landed (consistent with the rest of this study's multiplier); the
allowance itself is a stated assumption, not a sourced figure — panel-connector cost is noted at
~$0.20/connector in this repo's own D-1 kit review (`SYNTHESIS-beta-plan.md`), plus wire and
crimp/mold labor on top.

**(b) À la carte, all modules:** Hub $49 · 24-pin $89 · EPS $69 · PCIe-2 $69 · PCIe-3 $79 ·
12VHPWR-Std $99 · Hub Pro $79(est.) · 12VHPWR Pro $299.

**(e) Daughterboard+extension accessory SKUs (OQ-89, accessory revenue, no repo pricing precedent —
fresh estimate).** Landed (§1.2) + longer pigtail wire + a standard female output housing +
retail packaging: 24-pin extension ≈$3-4 landed → **$19.99**; EPS extension (2-cable set) ≈$5-6
landed → **$24.99**; PCIe extension (per-cable, 2- or 3-packs) ≈$2-3 landed each → **$14.99 each /
$27.99 pair**. These retire the LOCKED-today F-F 24-pin bridging-cable SKU per the v1.4.0 ruling.

**Margin retained at each tier** (bundle price minus landed cost): base bundle retains ~$78 gross
over ~$41 landed (real margin even at an aggressive 19% discount); loaded bundle retains ~$230 over
~$109 landed; Pro bench retains ~$238 over ~$111 landed. Bundling costs the platform discount
dollars, not margin ratio — every bundle here still clears >2.8× landed cost.

## 5. Honest caveats

- **Quantities:** 100-unit and 1,000-unit tiers assumed throughout, matching the platform's own
  convention; no per-part MOQ/reel-quantity friction is modeled (several parts, e.g. the Keystone
  clip at 533 pcs LCSC stock, do not comfortably clear a single 100-module production run without
  order-ahead — `output-daughterboard-study-2026-07-04.md` §8.10).
- **JLCPCB PCB-fab and SMT-assembly fee figures in this study are banded estimates, not live
  quotes** (date-stamped 2026-07-05; a real quote needs uploaded gerbers/BOM per board). Re-price
  before any BOM lock — this is the single largest source of numeric uncertainty in §1-2.
- **Consigned-part handling is a real, unresolved cost and schedule risk**, not just a price gap:
  Mini-Fit Jr headers (24-pin J3, EPS/PCIe J_IN*) and the 12V-2x6 (12VHPWR J3/J4) carry **no LCSC
  line at all**, so JLCPCB's LCSC-sourced SMT flow doesn't cover them — customer consignment (fee +
  lead time) or a separate manual step is required; this study's flat "assembly+consigned" line is
  an allowance, not a quote. **Concrete, not hypothetical:** Digi-Key shows the 12V-2x6 (2191160161)
  at **0 stock, 15-week lead time** right now — every 12VHPWR-Standard/Pro unit needs two; secure
  supply (or a second source) before quoting delivery on either board.
- **No NRE, tooling, or certification cost is amortized** — stencils, fixtures, and any voluntary
  EMC/safety testing (even for an unintentional-radiator posture, §6.14) are excluded from unit cost.
- **No enclosure/chassis is costed** (see §0) — these are internally-mounted PCBAs, not boxed
  standalone products; if the product strategy changes to a boxed/external form, add a real
  enclosure BOM line.
- **Channel model: direct-to-consumer assumed.** The 3.5× multiplier is sized for DTC margin. A
  retail channel (distributor + retailer, each typically 30-50%) would need a higher MSRP at the
  same DTC margin, or a compressed margin at the same shelf price — not modeled here.
- **Pro-tier figures for Hub Pro and EPS/PCIe-Pro are estimates against boards that do not exist**
  (confirmed empty 99-line schematic skeletons for Hub Pro and 12VHPWR Pro; no EPS-Pro/PCIe-Pro
  directory exists at all) — treat §2 as directional, not quotable.
- **Bundle cable allowances (§4) are stated assumptions**, not sourced cable-assembly quotes.
