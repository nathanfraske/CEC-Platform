# Standard-tier BETA LOCK REGISTER — 2026-07-03

_The owner's ask: "anything we need to lock for the standard hub and module design and BOM
that needs tweaks or refinements, alternative parts / redesign? I'm fine putting in redesign
work now if it will fix something long-term." Sources: the six-report review pass +
SYNTHESIS-beta-plan.md, the output-interface panel, and a 12-agent parts investigation
(6 web-enabled investigators, each adversarially verified — wf_7dfb54cb-dbd). Every claim
below marked VERIFIED was re-checked live by an independent second agent this session._

## A. LOCK NOW (verified; no further debate needed)

| # | Lock | Evidence |
|---|---|---|
| A1 | **Hub C1 = Samxon/Ymin VKMI2101C472MV, LCSC C487318** (the part already shipping in schematic/BOM/PCB). The Panasonic EEVFK1C472M in CLAUDE.md/README was documentation-only — and Panasonic is OUT OF STOCK ($1.09@100 when available) vs C487318 in stock (275 LCSC / 516 JLC, $0.73@100). Fix the DOCS to match the boards, not vice versa. | VERIFIED live both channels |
| A2 | **PCIe 45586-0005 stays; no pegless variant exists anywhere.** All 7 SKUs in the family (-0005…-1206) differ only in plating/resin/packaging; "PCB Retention: Yes" is fixed parametric. The EPS-style 44→35mm height win is NOT available by part swap. Optional mechanical deviation (delete the 2 peg NPTHs from the land, retention via 16 THT tails) is a board-specific owner call, not a part change. ~~Fab flag: 45586-0005 is 0-stock / 9-week lead at DigiKey today ($3.03@680)~~ **RETIRED (owner, 2026-07-03): male headers sourced from ModDIY, plentiful stock — lead time is a non-issue.** | VERIFIED live (Molex series chart + DigiKey) |
| A3 | **Sensor lines stay as specified** — no cross-vendor drop-in exists for any of INA240A3DR / INA228 / INA238 / INA181A2 / TLV7011. Stock today: INA240A3DR 13k+ (DigiKey, $1.93@500), INA228 healthy, INA181/TLV7011 healthy. | VERIFIED live |
| A4 | **Hub power-in consolidation part = JST S3B-XH-A, LCSC C157928** (3-pin XH RA THT, 3A/pin; curved-needle sibling C163036 40k stock as alternate). Pin order **MAIN_5V / GND(center) / 5VSB** — GND-center makes any misinsertion benign; XH shrouding already blocks reversal/offset. Same family as the existing 2-pin parts: no new assembly process. | VERIFIED live |

## B. DO NOW — no decision needed (hygiene/redesign under existing rulings)

| # | Work | Notes |
|---|---|---|
| B1 | **NEW DEFECT (found by the adversarial pass): Manufacturer↔LCSC field swap, SYSTEMIC** on eps8pin (39/31 swapped pairs), pcie-2port (39/31), pcie-3port (45/37) — C-numbers sit in the Manufacturer property, manufacturer names in the LCSC property, across ~the whole sourced BOM. Any JLC BOM import on those three boards fails wholesale. Hub + 12VHPWR clean. Mechanical fix + re-verify BOM exports. | Fix agent launched (W10) |
| B2 | **USB-C LCSC number is the wrong manufacturer's part**: boards carry C2765186 (Shou Han "TYPE-C 16PIN 2MD(073)") attached to an XKB footprint; the correct XKB part is **U262-161N-4BVC11 = LCSC C319148** (LCSC itself aliases 161N/16XN). Swap the sourcing line. | VERIFIED live; rides W10 |
| B3 | 12VHPWR U4↔U3 REF reposition (shipped defect); mirror lanes + 0.9/0.5 via upsizing (production bar per the quality-first tilt). | From review corpus (D-7) |
| B4 | 24-pin rev3: RS4 → true 4-terminal Kelvin land (WSK2512); resolve the J6 mezzanine netlist-vs-doc pin-map contradiction. | From hygiene-wave flags |
| B5 | EPS + PCIe×2: netclass/.kicad_dru + `_P/_N` prep (W5) then full routing passes (W6) through the tiered pipeline. | The bulk beta engineering |
| B6 | Hub beta layout pass: W9 antenna-keepout drop (ruled), final pours, and the A4 power-in consolidation splice (schematic + PCB). | Redesign scope verified: one connector replaces J_5VSB+J_5V; net names unchanged |
| B7 | Docs: C1 references (A1), stale connector text in EPS/PCIe BOM CSVs, EPS $32-vs-$34 reconciliation. | |

## C. QUALIFY / HEDGE (sourcing actions, cheap, do at BOM-freeze)

| # | Action | Why |
|---|---|---|
| C1 | Add **TI INA237AIDGSR as an approved alternate** on the EPS/PCIe INA238 BOM lines (TI-stated code/hardware equivalent, same VSSOP-10; sourcing-document edit only). | INA238 is the thinnest line: ~1.8k units at DigiKey, inside TI's 2026 repricing cycle |
| C2 | **Hedge/bonded-stock buy on INA238AIDGSR** sized to the first production run; price-lock the healthy TI lines via a distributor quote before the next repricing round. | Same |
| C3 | Watch TPS3839K33 stock (thin) — same-class supervisor alternates exist if it thins further (re-run the check at BOM-freeze). | From A-item investigation |

## D. OPEN — owner decisions (unchanged from the synthesis, updated state)

| # | Decision | State |
|---|---|---|
| D-5/D-5a | 24-pin beta scope + **output form**. Form menu now: owner lean (very short stub + order-time optional extension), **Option F perpendicular daughtercard** (vertical female on an edge-soldered card — machine-solderable/AOI-able, solves the panel's own top objection to hand-crimped pigtails; owner clarified: his hunt's vertical female is an UNQUALIFIED AliExpress-class DIY part — no MPN/spec/footprint — disqualifying for the sellable BOM; Option F revives only via a COMMISSIONED properly-spec'd part (see panel doc's provenance update: crimp assembly now, commissioned part as production endgame), Form B (12cm stub), incumbent C. NEW VERIFIED FACT strengthening the move off C: **no F-F 24-pin cable exists as a commodity product anywhere** (only DIY housings/terminals) — the incumbent always meant CEC fabricates a cable class with zero commercial supply chain. | OPEN, owner lean recorded |
| D-8 | rev2 erratum consumer disclosure. | OPEN |
| D-11 | USB-C footprint: the land is FAITHFUL to the manufacturer drawing (verified byte-identical to upstream); the violations are real vs JLC's 0.2mm NPTH floor (2 pads genuinely sub-floor). NEW: a community **"modforjlc" corrected variant of this exact footprint exists** (cadlab.io / git.rbts.co prior art) — track it down and vet against the XKB mechanical drawing BEFORE settling for a documented DRU exception. Owner picks: vetted corrected footprint (preferred under quality-first, IF dimensionally faithful) vs documented exception. | OPEN, sharpened |
| OQ-2 | 5VSB/LED budget number — finalizes the power netclass width everywhere. | OPEN (owner number) |
| — | 12VHPWR pigtail spec: length/gauge/strain + the confirmed white/black SKU split. | Owner bench + D-7 |

## E. Explicitly re-verified as fine (no action)

- The XKB USB-C footprint geometry itself (do NOT hand-edit the pads/pegs blind — it matches upstream; the fix path is D-11's vetted variant or an exception).
- INA240A3DR / INA228 supply for a 100–1k run.
- The 45586 connector choice (keying is safety-load-bearing; A2).
- Alternatives investigated and REJECTED with reasons on record: Amphenol Minitek HCC (male-on-board convention, same as Molex), Würth WR-MPC3 (3.0mm pitch, incompatible), 3PEAK/Microchip sensor crosses (not drop-in), JST VH for power-in (declined on merits), AliExpress-class "female ATX" parts (no credible listing; unqualified provenance).


## F. Base-level QoL shortlist (owner ask, 2026-07-03 — ranked, cheapest-per-delight first)

| # | Item | Cost | Vehicle |
|---|---|---|---|
| F1 | Cable-dress anchors (zip-tie slots) + a mounting story on EVERY module — fixes the "dangles in the channel" finding | Board-outline features, ~$0 | W6 routing/finishing passes + hub beta layout |
| F2 | Hub port-LED semantics (breathing=healthy / amber=event / red=fault) on the existing 7× SK6812 | Firmware only; FORCES the OQ-2 number | Firmware lane |
| F3 | Self-describing silk: port numbers, which-cable arrows, install-page QR + serial QR per module | ~$0 | W6/W8 silk passes |
| F4 | **Persist-on-fault as a shipped feature** (last ~2s pre-roll survives PC death; §2.9 hardware already built) — the highest-leverage consumer story on the list | OQ-56 bench + firmware surfacing | OQ-56 bench (owner) + firmware lane |
| F5 | Status LED per module (~$0.10 SK6812 + GPIO) so "amber=event" is visible at the module — NOTE: a status LED was DECLINED once on 12VHPWR (v3.7); this is a revisit-or-keep call, flagged not assumed | ~$0.10/module + owner call | Decision list (new D-12) |
| F6 | One-plug power (3-pin GND-center consolidation) — locked as A4; listed for the story | done | B6 |
| F7 | Single-point firmware updates: Hub USB updates all modules over CAN; module USB-C = service fallback only. Commit the architecture BEFORE module firmware ossifies | Firmware architecture commitment | Firmware lane, now |
| F8 | Kit ergonomics: pre-cut patch lengths per case class (answers OQ-4 as product), labeled per-module bags, D-8 insert | Packaging | Kit definition (D-1) |


## G. Owner confirmations (2026-07-03, follow-on to section F)

- **G1 (F7 CONFIRMED): single-point firmware updates via Hub USB is the intended architecture,
  already in progress in owner firmware.** NEW SYSTEM FACT: the Hub's USB is the whole system's
  main point of contact and connects to the **motherboard's INTERNAL USB header** (not a rear
  port) — the kit therefore carries an internal-USB-2.0-header → USB-C cable (commodity part,
  same class as front-panel USB-C adapter cables). Add as a D-1 kit line. QoL consequence: no
  cable exits the case.
- **G2 (F8/OQ-4): patch-cable direction set** — slim, very flexible, nicely braided RJ-45 patch
  cables; OWNER is tracking down the part himself (owner-queue item). Length catalog still rides
  the kit definition.
- **G3 (F4/OQ-56): hold-up architecture confirmed by owner** — firmware monitors the 5V input;
  on drop it interrupts the ESP and flushes; the hold-up cap feeds ONLY the LDO path (the D1
  Schottky isolation already on the board) so every mJ goes to the MCU, maximizing time.
  Rough budget: 4700µF × ~1.3V usable ΔV / ~100mA LDO load ≈ 60ms — comfortably above a
  ring-buffer flash flush IF the bench (OQ-56) confirms.
  **BETA CONSIDERATION (one circuit note, surfaced not assumed):** the existing sense dividers
  (47k/10k) put 5V-in at ~0.88V on IO9/IO10 — that is ADC territory, NOT a GPIO logic threshold,
  so a literal hardware INTERRUPT on 5V-drop cannot fire from the divider as built. Two honest
  paths: (a) firmware fast-poll/ULP on the ADC (~1kHz costs ~1ms detection vs the ~60ms budget —
  likely fine, zero BOM); (b) a TLV7011 comparator (already a platform part, ~$0.10) from the
  divider to a GPIO for a true sub-µs interrupt + crisp threshold. Owner picks at the hub beta
  pass; the bench (OQ-56) should measure BOTH detection latency and flush time either way.


## H. Owner rulings (2026-07-03, hold-up + standalone-module scope)

- **H1 (RULED): TLV7011 comparator on the hub's 5V-drop detect** — true hardware interrupt for
  the persist-on-fault trigger (replaces ADC-poll as the primary; divider threshold set at the
  beta splice). Rides the hub beta layout pass. → W12.
- **H2 (hold-up maximization menu, recorded with owner's supercap rejection —
  derating/inrush/aging all valid):** ladder is (1) FREE: pre-erased ring region (flush =
  program-only, tens of ms) + comparator-edge load-shed (low clock, peripherals off) — the
  existing ~68ms LDO window is likely sufficient with these; (2) ~$1: buck-boost (TPS63020-class)
  replaces the hold-up LDO path → drains the can to ~2.5V at ~90% eff ≈ 2× time; (3) ~$1.50:
  boost-charge the EXISTING 16V 4700µF can to ~12V (TPS61023-class, soft-start) + wide-Vin buck
  → V² ≈ 5× usable energy ≈ 600-900ms — the SSD power-loss-protection architecture, zero added
  bulk. DECISION POSTURE: (1)+H1 now, OQ-56 bench decides whether (2)/(3) populate; (3) stays
  the pre-designed fallback. Supercap REJECTED (owner).
- **H3 (RULED, new beta scope): MODULE STANDALONE MODE — every module usable independently of
  the hub via its USB-C.** Hardware delta per module: USBLC6-2SC6 on the USB data pair (hub
  parity — modules currently lack it), VBUS-side clamp, and a defensive ESD review of every
  externally-touchable line under the no-hub assumption ("ESD on everything, not just the hub").
  Firmware delta: USB CDC telemetry mode when no CAN master present. → W11; touches
  gen-modules BASE_PARTS + the hand-maintained EPS/12VHPWR schematics at their beta pass;
  aligns with the quality-first principle; ~$0.15/module.
  **H3a (owner addendum: "and ferrites, if needed")** — ferrite posture for the suite, judicious
  not blanket: (a) VBUS entry bead POPULATED (MPZ2012S601A-class, 600Ω@100MHz — the standard USB
  power-entry filter, same part family the Nuand reference sheets carry); (b) port-VCC (5VSB)
  entry on each module: bead position PROVISIONED, 0Ω by default, populate on EMC evidence;
  (c) CAN pair: common-mode-choke POSITION provisioned DNP as EMC insurance (never series beads
  on individual CAN lines); (d) USB D+/D- get NO series ferrites (SI killer) — CMC only if a
  pre-scan ever demands it. Rationale: standalone-USB use makes each module its own FCC 15B
  unintentional-radiator story, so provisioned filter positions are cheap insurance; empty
  positions cost pad area only.


## I. Tier board-sharing doctrine (RATIFIED by owner, 2026-07-03: "they're tuned for very different things... they deserve their own boards")

Owner asked: build the Pro variants by default and make Standard a no-pop population of the
same board? ASSESSMENT (recommendation, owner to ratify):

- **NO wherever the acquisition core diverges** — 12VHPWR Pro (P4 + LTC2358-18 + RS-485
  streaming vs S3 + ESP-ADC) and every P4-based Pro: MCUs can't be DNP'd across different
  lands, so a shared board = a dead second control-core region (+15-25% area, ~700-1000mm² on
  the 12VHPWR) on every Standard unit — contradicts the D-2 space doctrine ("an unstuffed
  option still occupies the footprint"). The classic shared-layout payoff (halved layout/qual)
  is weak here because layout is pipeline-automated; the dead area is a permanent per-unit cost.
- **YES for population-shaped deltas on the same core** — RS-485 transceiver + pair-2, DETECT
  code resistor swap, §6.13 fronts, the H3 standalone suite: all already DNP-friendly. If EPS
  Pro / PCIe Pro firm up as "Standard + fast path on the same MCU," a shared board with a Pro
  population is legitimate — keep that door open until their acquisition spec lands.
- **MAX is its own board, always** — FPGA acquisition + Rogowski-coil high-MHz di/dt is a
  different physics package; the coil's analog front end dictates its own layout. Nothing
  shareable below the connector.


## J. Housing directive + the 12VHPWR thermal interaction (owner, 2026-07-03)

- **J1 (DIRECTIVE): Standard tier ships ENCLOSED** — 3D-printed housings for initial runs, with
  built-in strain relief and RGB transparency; the Hub's RGB ring surrounds the CEC logo and
  shines through directly. Mechanical workstream opens: per-board shells, service cutouts
  (USB-C + BOOT/RESET per the H3 standalone ruling), M3 mounts become housing bosses, light
  pipes/windows. Strain relief moves INTO the shell (supersedes part of F1's board-edge-anchor
  proposal — anchors stay only where the shell doesn't cover).
- **J2 (CRITICAL INTERACTION, flagged): the 12VHPWR thermal PASS assumed a METAL case** —
  the validated 72.95°C/ΔT22.95 solve is conduction via TIM-on-shunts + M3 mounts into metal;
  still-air no-case = 151°C; a printed shell is WORSE than open air (insulator + blocks
  convection). Owner's own electrothermal solves agree (2.5mm/pin 2oz + mirror + vias still too
  hot in still air) → owner floated a small fan. MENU (quality-first order): (1) hybrid housing
  = printed shell + TIM-coupled ALUMINUM BASEPLATE under the shunt row — keeps the validated
  cooling model, silent, no wear item; (2) DNP fan provision regardless (2-pin header, powered
  from the 12V INPUT BUS upstream of the shunt row so fan draw never pollutes per-pin GPU-side
  measurement; NEVER from 5VSB/OQ-2 budget); (3) fan-primary (25-30mm) — works but adds a wear
  item; mitigation: TH1 shunt-row NTC + firmware overtemp alarm = the module alarms on its own
  cooling failure. RECOMMENDED: (1)+(2)+alarm. The housing task inherits the thermal spec as a
  REQUIREMENT. Other module housings: no equivalent concern at their dissipation (EPS/PCIe
  cable boards run cool; verify at their W6 electrothermal gates with the enclosed boundary
  condition, not open-air).
