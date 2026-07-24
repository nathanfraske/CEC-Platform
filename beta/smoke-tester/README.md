# Smoke Tester — sacrificial first-contact PSU triage box (beta line)

**Status: DRAFT, sketch-stage — no schematic capture yet** (the `tester-standard`
convention: folder + design basis first, gated capture as its own phase). Stood up on
the beta line by owner directive 2026-07-24 ("make a new beta module… put all the
design spec in there"), which executes decision #1 of the concept doc's list. Design
basis of record: `docs/smoke-tester-concept-2026-07-24.md` (§1–§9) + this README (the
board-level spec). Sketches: `assets/` (block diagram, per-way schematic sketch,
control/indication sketch). BOM: `bom/bom.csv` (+ JLC-format skeleton). Zero firmware
by design — no `firmware/` entry will ever exist for this board.

**One-liner:** the thing you plug a sketchy PSU into FIRST. Every DUT conductor enters
through a replaceable fuse; every fault class — overvoltage, mains-on-a-rail, reverse,
cap dump — is *converted* into a fuse-clearing current event by a sacrificial clamp;
the human is told the case is live before touching it. All triage, zero metrology:
the bouncer in front of the module / ST-deck bench, at a price where its own death is
a shrug.

## 1. Mission and fences

- **Does:** connector-domain triage of an unknown/suspect ATX PSU: 5VSB sanity,
  rails-quiet-before-PS_ON, rails-in-window after, PWR_OK presence + coarse timing,
  −12 V presence, hot-ground ("CASE LIVE") detection, modular-cable pinout check via
  the AUX adapter port. Survives mains-on-any-output by design; repair = consumables.
- **Never:** metrology (±5 %-class lamp windows only), load testing beyond min-load
  bleeders, ripple, OCP hunts, data links, MCUs, inline operation. It TERMINATES the
  DUT — nothing of ours ever sits downstream of it. Green lights here earn the DUT
  its interview with the 24-pin module / ST deck; that is the whole product ladder.
- 24-pin only, deliberately: no other PSU connector adds a voltage domain (EPS/PCIe/
  SATA/Molex are the same secondary nodes), and PS_ON# lives on the 24-pin, which
  makes it the mandatory core. Per-cable wiring faults are the AUX port's job (§5).

## 2. Architecture — three domains, four consumables, one structural rule

See `assets/smoke-tester-block.svg`.

**Domains.** (a) THE SACRIFICE PATH (DUT copper): snout → blade fuse → HRC backup →
clamp brick → way node → bleeders/dividers. (b) THE FLOATING MEASUREMENT DOMAIN:
comparators + lamps + meter, powered by a 9 V battery (or USB-C 5 V), referenced to
DUT GND and floating relative to earth — it keeps indicating even when DUT GND rides
line potential. (c) THE EARTH-NEON DOMAIN: nothing but neon bulbs and megohms
between DUT nodes and the earth reference — zero powered electronics, strikes at
~90 V, lights **CASE LIVE**.

**The structural rule (what makes "modular" true):** *no main-board copper sits
electrically upstream of a sacrifice element, and measurement taps enter only through
≥900 kΩ of series 300 V-rated resistance.* The main board survives by impedance and
by coordination, never by luck. Way copper is laid out to 300 V-working creepage
(≥3.2 mm) — a layout gate, recorded in §9.

**The four consumables (all socketed):**

| # | Part | Where | COGS | Dies from |
|---|---|---|---|---|
| 1 | ATO blade fuses, **1 A fast, one value everywhere** | panel sockets | ~$0.10 | everyday overcurrent (shorts, cap dumps) |
| 2 | HRC 5×20 ceramic sand-filled, **2 A time-lag, 250 VAC, 1.5 kA breaking** | internal twist holders | ~$0.35 | mains-class interruption (what a 32 V blade cannot break without arcing) |
| 3 | **Sacrifice brick SB1** — all 8 MOVs + 8 fusible witness resistors on one keyed plug-in PCB | 2×10 socket pair | ~$3 | any OV/mains event (doctrine: mains event ⇒ fuses AND brick) |
| 4 | **Snout SN1** — the 24-pin male header on a passthrough paddle | keyed 2×13 shrouded header | ~$3 | mating-cycle wear (Mini-Fit Jr tin ≈ 30 cycles; a shop does hundreds) |

**Coordination story (why two fuses in series):** the 1 A fast blade clears every
low-voltage event first (selectivity by rating ratio 1:2 and speed class F vs T).
In a mains event the blade opens but can sustain an arc (it is a 32 VDC part); the
current continuing through the arc cooks the 2 A time-lag HRC, which is built to
break 250 VAC into sand. The witness resistor (1 Ω flameproof fusible, in series
with its MOV) opens with its designed benign puff — that is the safe smoke — and
disconnects the spent MOV so a failed-short varistor cannot latch the way.

## 3. Per-way electrical spec

See `assets/smoke-tester-way-sketch.svg`. Eight fused ways (5 core + 3 AUX) + one
resistive continuity way. All windows ±5 % nominal, LM339 comparator pairs against a
TL431-derived ladder; taps measure DOWNSTREAM of the sacrifice chain (post-event a
way honestly reads dead).

| Way | Blade | HRC | MOV (brick) | Witness | Divider (to DUT GND) | Window at node |
|---|---|---|---|---|---|---|
| 12 V | 1 A F | 2 A T | S14K14-class (14 VRMS / ~22 V VV) | 1 Ω 1 W fusible | 903 k / 100 k (÷10.03) | 1.137–1.257 V |
| 5 V | 1 A F | 2 A T | S14K6-class | 1 Ω 1 W fusible | 903 k / 100 k | 0.474–0.524 V |
| 3.3 V | 1 A F | 2 A T | S14K4-class | 1 Ω 1 W fusible | 903 k / 100 k | 0.313–0.346 V |
| 5VSB | 1 A F | 2 A T | S14K6-class | 1 Ω 1 W fusible | 903 k / 100 k | 0.474–0.524 V |
| −12 V | 1 A F | 2 A T | S14K14-class (MOVs are bidirectional = free reverse clamp) | 1 Ω 1 W fusible | 100 k to +2.5 V bias / 15 k / 903 k string | level-shifted window, healthy/absent/OV separable |
| AUX-12 / AUX-5 / AUX-3V3 | 1 A F | 2 A T | as their rail | 1 Ω | as their rail | as their rail |
| AUX-GND (continuity) | — | — | — | — | 1 kΩ 350 V series → LED | lamp: "GND IS NOT GROUND" if any voltage present |

Divider top legs are 3 × 301 kΩ 1206 in series (voltage sharing — each sees ≤110 V at
230 VAC on the way; 1206 rated 200 V, string rated 600 V). Mains math sanity: 230 VAC
onto a way drives the MOV into conduction at tens–hundreds of amps → both fuses clear
in ≤ a half-cycle, witness opens, comparator node never exceeds ~2.4 V through the
÷10 string even mid-event.

Min-load bleeders (switchable, "MIN LOAD" DPST): 47 Ω 10 W on 12 V (~0.26 A) + 10 Ω
5 W on 5 V (~0.5 A) — enough for group-regulated antiques to regulate, small enough
that 1 A blades never see >0.6 A legitimate.

## 4. Controls and indication

See `assets/smoke-tester-ctl-sketch.svg`.

- **Arm/fire:** missile-cover toggle → RC pulse → SET coil of K1, a **dual-coil
  latching DPDT relay** (zero hold current — months on one 9 V). Pole A closes
  PS_ON# → GND through 100 Ω with a PESD5V0S1BA clamp (platform part, LCSC C5261083).
  Lid-open microswitch or DISARM pulses the RESET coil: **an open fuse door IS the
  safe state.** The user's finger never touches DUT copper.
- **PWR_OK race (all analog):** K1 pole B starts a 100 ms / 500 ms two-tap RC; two
  comparator sections latch PWR_OK's rising edge against the taps → PG EARLY / PG OK
  / PG LATE-NEVER lamps (ATX spec window, coarse by design).
- **Hot-ground:** NE-2 neon chains through 2×470 kΩ 0.5 W each: DUT-GND ↔ EARTH
  ("CASE LIVE") and an OR of the four positive ways through 1 MΩ each into a second
  neon ("RAIL LIVE"). Earth reference = rear earth pigtail (or earth-only IEC inlet —
  open decision #5). Strikes ~90 V; a 48–90 V fault lights nothing (known limit,
  concept §7c — the window comparators still show gross OV).
- **Needle meter:** 100 µA moving-coil panel meter + 1P6T rotary reading the
  *already-divided* node (it can never see more than a few volts, whatever the DUT
  does), scale printed ×10. No pixels, no MCU — numbers are the module/ST deck's job.
- **Lamps:** per-way green (in-window) / red (out), blown-fuse indicator across every
  blade position (lights only when its fuse is open AND the way upstream is live),
  battery-OK dot. Panel silk = the verdict truth-table; tear-off verdict-card pad
  ships in the lid.

## 5. AUX adapter port

One keyed 2×5 shrouded header exposing the 3 AUX fused ways + the continuity way +
DUT GND. Passive per-family adapters (SATA / Molex / PCIe / EPS plug → header, each
carrying its own pin map) put the *expected* voltage on the matching way — a
miswired modular cable puts 12 V on the 5 V-expected way → RED. Adapters are
accessory SKUs (concept §9.6); the box never grows connectors. 12VHPWR adapter
deferred to the metrology tiers (fence).

## 6. BOM rollup (sketch-stage, 100-qty estimates — `bom/bom.csv` is the line list)

| Block | Est |
|---|---|
| Snout paddle (Mini-Fit Jr 24-ckt male, consigned + paddle PCB + header pair) | $3.10 |
| 8× ATO holders + installed 1 A blades | $2.60 |
| 8× 5×20 holders + installed 2 A-T HRCs | $4.40 |
| Sacrifice brick SB1 (8 MOV + 8 witness + PCB + socket) | $3.00 |
| Measurement domain (4× LM339, TL431, HT7550-class LDO, divider strings, RC race) | $1.60 |
| Lamps (16 way-LEDs + 8 blown-fuse + 2 NE-2 chains) | $1.10 |
| K1 latching DPDT + missile toggle + rotary + microswitch + TEST/LOAD switches | $5.60 |
| Bleeders (47 Ω 10 W + 10 Ω 5 W, chassis) | $1.20 |
| Needle meter (85C1-class, consigned) | $3.50 |
| Power (9 V holder, USB-C 5 V power-only, ORing) | $0.60 |
| Main PCB + FR4 front panel (panel-as-PCB: silk truth-table is free with the fab) | $3.00 |
| Case w/ lid fuse storage (quote TBD) | $7.00 |
| Verdict pad + print | $0.50 |
| **Starter kit** (full spare blade set + 2 HRC + **1 spare brick**) | $4.30 |
| **Landed rollup** | **≈$36.50** |

Honest delta vs the concept §9.4 target ($30–34): this rolls up ~$36.5 at 100-qty
with the starter kit in-box; the target recovers at 1 k qty + the case quote (the two
soft lines). Levers if needed: meter-delete (−$3.50, hurts perceived value most per
dollar — don't), case class (−$2–3), holder consolidation. **Retail $79** incl.
starter kit (concept §9.4, one SKU, no Lite). Consumables ladder: refill $9 / brick
2-pack $12–15 / snout $9 / adapters $9–12 or $39 4-pack (concept §9.6).

LCSC discipline: only platform-verified numbers appear in `bom/bom.csv` (today:
PESD5V0S1BA C5261083); every other line is deliberately LCSC-blank pending the
sourcing pass — no invented part numbers. Heavy THT (snout connector, meter, holders,
switches) is consigned-class like every Mini-Fit Jr on the platform.

## 7. Mechanical / panel

Front panel is itself an FR4 PCB (holders mount through it; silk = coroner's map +
truth table + QR to the reorder page). Fuse-row pitch standardized so AUX ways and
future variants share the panel tooling. Lid molds the starter kit (blade set, HRCs,
spare brick, verdict pad). Creepage: 300 V-working class (≥3.2 mm) on all way copper
and the brick; the brick connector keying prevents reversed insertion. No mounting
of anything conductive reachable from outside; fuse door interlock per §4.

## 8. Capture plan (next phase, ST-tester pattern)

Phase A: promote/pull the CAD library (ATO holder, 5×20 holder, NE-2, 85C1 meter,
latching relay, MOV discs, missile toggle — none vendored today) into `cec-tester`
or a `cec-smoke` lib. Phase B: sheets 01-ways (8× the way cell + brick socket),
02-controls (arm/relay/race), 03-indication (windows/lamps/meter), 04-power
(battery/LDO/USB) — flat or 4-leaf hierarchical, gen-script optional (the way cell
is 8 stamps of one pattern: a generator earns its keep). Gates: ERC 0, netlist
conformance vs §3's table, the DESIGN-SHEET §F pipeline gates, DRAFT marker drops
only after the **arc-coordination bench** (feed 230 VAC into a way, film blade→HRC→
witness sequence — the #1 gate AND the marketing video). Owner decisions still open:
concept §8 #2–#12 (this standup executed #1).

## 9. Open items

- [ ] Phase A library pass (parts list in §8) — nothing vendored yet.
- [ ] Case + meter + holder sourcing quotes (the three consigned-class soft lines).
- [ ] Arc-coordination bench protocol draft (gates DRAFT-drop; safety review for the
      witness chamber rides it — concept decision #4).
- [ ] AUX adapter pin-map table per family (SATA/Molex/PCIe/EPS) — one page, feeds
      both the adapter PCBs and the manual.
- [ ] Compliance posture ruling (concept decision #8) before any listing goes live.
- [ ] Panel truth-table copy + verdict-card layout (marketing-adjacent, owner voice).
