# "Smoke Tester" — sacrificial first-contact triage box (owner riff, 2026-07-24)

**Owner ask (verbatim intent):** a new tester-family item. "The thing you plug into a
sketchy PSU FIRST", with replaceable fuses, so a PSU that "literally just exposes mains"
doesn't kill anything — you just replace a blade fuse. Bonus if the fuse literally
smokes, hence the name. Status: **PROPOSED — riff + decision list, no folder/board until
ratified** (the AC-sense-pod convention).

**One-line identity:** a cheap, dumb-by-design, deliberately sacrificial bouncer that
stands between a sketchy PSU and everything you own — every DUT conductor enters through
a replaceable fuse, every fault class is *converted into* a fuse-clearing event, and the
human is told the case is live before they touch it. The name is the product: it runs the
smoke test, and when the DUT is evil, *our* $0.10 part is the thing that smokes.

## 1. The physics that shapes it (why "just fuses" isn't enough — and what is)

1. **A fuse opens on current, not voltage.** Mains on the 12 V pin feeding a high-impedance
   measurement circuit draws milliamps — no fuse ever blows, the silicon dies, and worse,
   the box's innards sit at line potential looking innocent. The fix is the core
   architecture: **every rail way is fuse → crowbar**, where the crowbar (MOV/TVS class,
   clamp above rail nominal) deliberately converts overvoltage into overcurrent so the
   cheap replaceable element clears. Fuse = ablative armor; crowbar = trigger; lamp =
   the story. This is what makes the box generalize: OV, mains, reverse, cap-dump — every
   unknown fault funnels into the same outcome (a blown $0.10 part and a lamp naming the
   guilty rail).
2. **The blade-fuse honesty problem.** ATO/ATC automotive blades are **32 VDC** parts.
   Asked to interrupt 120/230 VAC they can sustain an **arc** — the element melts but the
   plasma keeps conducting and the housing burns. So the blades keep the *user-facing*
   role (rail shorts, cap dumps, everyday sacrifice — ubiquitous, color-coded, gas-station
   buyable, satisfying to swap) and each way gets a hidden series **5×20 mm HRC ceramic
   sand-filled 250 VAC backup fuse** (also replaceable, inside the case) that does the
   mains-class interruption. Breaker-panel coordination, miniaturized: the blade clears
   everything a blade can; the ceramic clears what the blade can't. Panel copy writes
   itself: *"If the hidden one blew, the PSU goes in the bin."*
3. **Safe smoke theater.** The pun ships without shipping a fire: per-way **flameproof
   fusible resistors** as witness elements — parts whose *actual datasheet spec* is to
   open with a benign puff and no flame — mounted in a vented, windowed, UL94V-0 chamber,
   plus a neon/LED blown-fuse indicator across every holder (lights only when its fuse is
   open and the rail is energized). At a genuine mains event the real interruption happens
   inside sand; the visible drama comes from the part *specified* to smoke safely, behind
   polycarbonate.

## 2. Architecture (all analog, zero firmware, nothing to fry twice)

```
24-pin receptacle (terminator — NOTHING downstream, ever)
  └─ per rail way (12V / 5V / 3V3 / 5VSB / −12V):
       ATO blade fuse (panel) → 5×20 HRC 250VAC (internal) → clamp bank
       (MOV scaled per rail; bidirectional on −12V) → window comparator → bicolor LED
  └─ PS_ON#: series R + clamp → RELAY contact (galvanic finger separation),
       armed by a missile-cover toggle; lid-open microswitch drops the relay
  └─ PWR_OK: series R + clamp → presence lamp + analog RC timing race
       ("PG EARLY / PG OK / PG LATE-NEVER" — two comparators + a latch)
  └─ hot-ground stage: DUT-GND (and each rail) → ~1 MΩ → NEON → earth reference.
       Neons strike at ~90 V: line potential lights a BIG red "CASE LIVE" lamp
       with zero electronics and zero power required. Ancient tech, on brand.
  └─ min-load bleeders (5–10 W ceramic, switchable) so min-load-needy DUTs regulate
```

**Two electrical domains, deliberately:** the measurement domain (comparators, LEDs)
rides DUT GND and is **battery/USB powered, floating** — so it works even when DUT GND
sits at line potential, and never borrows a volt from the DUT (the box must keep
indicating while the DUT is insane). The earth-referenced domain is *only* the neon
chain to the earth reference (3-wire inlet used for earth only, or an earth pigtail —
owner call; the pigtail avoids "why is there mains inside" optics). No copper connects
the two except through megohms and neon.

## 3. The fuse field (the user experience is the product)

- **Panel like a breaker box:** one ATO holder per rail, color-coded, blown-lamp per
  way, silk "coroner's map" naming each rail, a write-the-date flag area, and spare
  fuses molded into the lid. Blades sized SMALL (1–2 A) — the box's loads are bleeders
  and dividers, and a small fuse clears faster with lower let-through.
- **The sacrifice cartridge:** MOVs + fusible witness elements live on a small plug-in
  daughterboard (the platform's blade-tab ecosystem muscle, OQ-89 pattern — or a plain
  keyed header at this price point). Post-catastrophe service = swap fuses + a ~$3
  cartridge; the box itself is never the casualty. MOV degradation after events is real —
  the printed doctrine is "mains event = fuses AND cartridge," which also resets clamp
  tolerances.
- **Coordination is a bench-proven claim, not a datasheet vibe:** deliberately feed
  230 VAC into a way and film the blade-then-HRC sequence. That video is simultaneously
  the engineering evidence and the marketing asset ("we did this so you don't have to").

## 4. What it tests (and the fences)

Stage 1 (AC on, not armed): 5VSB in-window; every main rail QUIET (any rail live before
PS_ON = fault lamp); no line potential on GND/rails (neon stage). Stage 2 (arm + fire):
rails in ±5%-class windows on bicolor LEDs; PWR_OK present + coarse 100–500 ms timing;
−12 V presence; reverse-polarity latch. That's it. **Fences (family discipline):** no
metrology, no numbers, no load testing beyond min-load bleeders, no ripple, no OCP
hunts, no data link, no MCU, and **never inline with real equipment** — it terminates
the sketchy PSU, it does not shield a downstream bench (fuse contact resistance would
corrupt deck metrology, and the deck's §12c fences already assume a sane DUT). Green
lights here buy the DUT its interview with the module / ST deck; nothing more.

## 5. Family fit

The USB-fault study (2026-07-24) exposed the gap this fills: the tester family's entry
point implicitly assumed a DUT that doesn't bite. Workflow becomes **Smoke Tester →
module / ST deck → Pro/Max**, protecting the ~$665–700 ST BOM and $89–99 modules with a
~$20 box. Reuses: Mini-Fit Jr 24-ckt input (platform part), blade-tab cartridge
ecosystem, the arming-console/missile-cover aesthetic (SE thread precedent), and the
§3b mains-side analysis as the sibling study (its breaker/GFCI math applies; manual
recommends a GFCI-protected bench outlet). Census row added to `testers/DESIGN-SHEET.md`
§A as PROPOSED — per the AC-sense-pod convention, **no folder until ratified**.

## 6. BOM class and product framing

Connector ~$1–2, 6× ATO holders ~$1.50, 5×20 holders ~$1, fuse complement ~$1, MOV/TVS
bank ~$1, 2× LM339 + refs ~$1, neons/LEDs ~$1.50, relay + missile toggle ~$3, bleeders
~$2, case/panel $5–10 → **$18–25 landed class → $39–59 retail** (impulse-priced gate
item; candidate freebie/anchor in the ST bundle as the liability story). One-liner:
*"The $49 box that eats the mains so your $700 bench doesn't."*

## 7. Honesty flags

(a) **Compliance surface is real** — a product that advertises eating mains faults
invites scrutiny; an IEC 61010 CAT claim costs creepage/clearance discipline + test
budget, "professional tool" disclaimer posture costs less but is a legal/positioning
call, not an engineering one. (b) The 32 V-blade arc risk is *the* safety item; the
blade+HRC coordination bench (with video) gates any sale. (c) Neons strike ~90 V — a
48–90 V-class fault lights nothing (rare in ATX context; the window comparators still
flag gross OV; noted, not solved). (d) The smoke chamber ships only after a
flammability/venting review — fallback is blown-flag indicators, and the name survives
on the smoke-test pun alone. (e) MOV clamp tolerances drift with absorbed events —
covered by the cartridge doctrine, stated on the panel.

## 8. Owner decisions (numbered, decision-ready — refined values in §9, which supersedes
the original 6/9 recommendations)

1. Ratify the family slot (`testers/smoke-tester/`) and the PROPOSED census row.
2. Terminator-only fence (recommended: YES — never inline).
3. Blade + hidden-HRC coordination vs blades-only (recommended: coordination; blades-only
   fails honest mains interruption).
4. Smoke-theater witness chamber: yes/no pending safety review (name survives either way).
5. Earth reference form: IEC inlet (earth-only) vs earth pigtail.
6. v1 connector scope — REFINED §9.1: 24-pin core + one generic AUX adapter port; passive
   per-family adapters as accessories.
7. Pure-analog purity vs an optional isolated telemetry population (recommended: pure v1;
   the ST deck owns data). Readout REFINED §9.3: needle meter option, never pixels.
8. Compliance posture: CAT-rated claim vs professional-tool disclaimer.
9. BOM/price target — REFINED §9.4: ~$30–34 landed → $79 retail incl. the §9.5 starter kit.
10. Bundle position: standalone SKU vs ST-bundle anchor item.
11. (new) Ship a spare sacrifice brick in-box (recommended: YES, §9.5).
12. (new) Consumables line + pricing ladder ratify (§9.6).

## 9. Refinement pass (owner Q&A, 2026-07-24 — six questions)

### 9.1 Other connections beyond the 24-pin? The physics says no — modularity says adapter port

Connector census vs voltage domains: EPS, PCIe, SATA, and Molex add **zero** voltage
domains — every rail they carry (12/5/3.3) is the same secondary-side node family the
24-pin already exposes, and a mains-on-secondary or gross-OV fault appears on all
connectors of that rail simultaneously. The 24-pin alone covers every distinct domain
(12 V, 5 V, 3.3 V, 5VSB, −12 V) plus both control signals (PS_ON#, PWR_OK — and PS_ON#
is *required* to wake the DUT, so the 24-pin is the mandatory core regardless).

What the 24-pin does NOT cover is the **per-cable** fault class: mixed-vendor modular
cables with wrong PSU-side pinouts (the classic drive-killer: 12 V on a 5 V pin at the
device end), crimp shorts, pinched harnesses. That is a *wiring* test, not a domain
test — served by the **AUX adapter port**: 3–4 generic fuse+window ways (12 V-expected,
5 V-expected, 3.3 V-expected, GND-continuity) behind one keyed header, plus a family of
**purely passive adapters** (SATA / Molex / PCIe / EPS plug → the AUX header, each
adapter carrying its own pin mapping). A miswired cable puts 12 V on the 5 V-expected
way → RED. Adapters are $2–4 COGS accessories (§9.6); the box never grows connectors.
12VHPWR adapter: deferred — its real value (per-pin resistance, melt precursors) is
metrology and belongs to the 12VHPWR module/ST deck, not a lamp box (fence).

### 9.2 Super modular: the four sacrifice classes + the coordination rule

Design rule: **everything that can die is a consumable in a socket; the main board is
only allowed to carry things that survive** — and the guarantee that it survives is
structural: *no main-board copper sits electrically upstream of a sacrifice element*,
and the comparator/meter taps enter only through ≥1 MΩ dividers built from 300 V-rated
resistor strings (they survive mains by impedance, not sacrifice). Creepage on the way
copper laid out to 300 V-working class. The four consumables:

| # | Consumable | Form | COGS | Death cause |
|---|---|---|---|---|
| 1 | ATO blade fuses | panel sockets, standard parts ON PURPOSE (hardware-store refillable — say it loudly, it's the trust story) | $0.10 | everyday events: shorts, cap dumps |
| 2 | HRC 5×20 250 VAC ceramics | internal tool-less twist holders | $0.30–0.60 | mains-class interruption |
| 3 | **Sacrifice brick** — ALL clamp/witness elements (per-way MOVs, fusible-resistor witnesses, ESD bits) on ONE keyed plug-in PCB | socketed 2×N header, event-date write-in flag on the brick | $3–4 | any OV/mains event (doctrine: mains event ⇒ fuses AND brick, no diagnosing which MOV degraded) |
| 4 | **Snout** — the 24-pin receptacle on a passthrough paddle | keyed shrouded header | $4–6 | mating-cycle wear (Mini-Fit Jr tin ≈ 30 cycles; a shop does hundreds — worn contacts are how every cheap PSU tester dies lying) |

The case/panel is the platform: fuse-row pitch standardized, AUX ways use the same
holders, one enclosure across future variants. Battery economics refinement: the PS_ON
relay becomes a **latching (bistable) relay** — pulse coils, zero hold current, lid-open
microswitch pulses the release coil — so the whole box runs months on 2×AA (comparator
domain ~10 mA, powered by a held TEST action or a soft timer; neons need nothing).

### 9.3 Screen? No pixels — a needle

No LCD, no MCU: pixels violate the soul (firmware to fry, power dependency, compliance
surface) and metrology is the module/ST deck's job (deliberate upsell ladder — the
Smoke Tester is the bouncer, not the interview). The middle path that keeps the soul:
one **moving-coil needle meter** (+ rail-select rotary), reading the *already-divided*
node so it never sees more than a few volts regardless of what the DUT does, scale
printed accordingly. $4–5, zero silicon, survives anything, photographs beautifully,
and a needle slamming on a hiccuping PSU tells a story no lamp can. The second
"readout" is paper: panel silk printed as a verdict truth-table, plus a tear-off
**verdict card** pad (shop staples it to the customer's PSU — zero electronics, carries
the logo, doubles as marketing).

### 9.4 Target BOM and retail

100-unit-class landed estimate: snout paddle $2.5 · ATO holders+fuses $2.5 · HRC
holders+fuses $2 · sacrifice brick + socket $3.5 · comparators/refs/dividers $1.5 ·
neons+LEDs $2 · latching relay + missile toggle + rotary + microswitch $4 · bleeders
$2.5 · needle meter $4.5 · case/panel/print $8–10 · PCB $2 · power bits $1 →
**≈$30–34 landed** (lamps-only drops ~$5; ~$25 path at 1k). Retail: **$79** with the
§9.5 starter kit included (≈2.4× — between the module 2.5× and ST ~1.9× houses).
One SKU — a de-contented $49 "Lite" was considered and rejected (self-competition,
and the meter is the cheapest perceived-value dollar on the board). Bundle price
inside the ST bundle is decision 10.

### 9.5 Replacements in the retail pack: YES — it's the trust move

The product's story is "parts in here die on purpose"; shipping without spares betrays
it on day one. Starter kit (all in the lid): full spare blade set + extras of the small
values, 2× spare HRC ceramics, **1× spare sacrifice brick** (+$4 COGS that buys the
whole narrative — a day-one mains event doesn't brick the experience, and the spare
sitting in the lid is the standing ad for buying more), and the verdict-card pad. Not
included: spare snout (longer wear clock, its own SKU).

### 9.6 Selling more replacements — event-driven, honest razor-and-blades

Consumption is event-driven: a brick dies only when a bad PSU came in, so every spent
consumable maps to a specific averted disaster — that's why nobody resents the reorder
(the write-the-date flag on the brick reinforces it). The line: **Fuse & Flag refill
$9** (blades + HRCs + witness flags) · **Sacrifice brick 2-pack $12–15** · **Snout $9**
(gold-flash Pro snout option) · **AUX adapters $9–12 each / $39 family 4-pack**.
Blade fuses stay deliberately standard/hardware-store-refillable — the attach lives in
the brick/snout/adapters, which are ours alone; proprietary-izing the fuses would
poison the trust story. Mechanisms: QR on the panel and on every brick → reorder page
(brick carries a coupon code); "photo of your dead brick + the war story" → community
wall + discount (every consumable death generates content — the marketing flywheel);
bench/wall mount plate SKU pushes intake-counter placement, which drives per-unit
usage; pegboard-friendly hang-card packaging for distributors; consumables carry
retail-healthy margins. No subscription — wrong price class, nickel-and-dime optics.
Honesty line for planning: this is a $79 accessory with $9–15 refills — a
margin-healthy small line whose strategic job is guarding the expensive bench and the
brand, not a business by itself.

### 9.7 Power revision (owner no-disposables directive, same day — supersedes every
battery mention above: the 9 V/2×AA lines in §2/§9.2 are retired)

No battery of any chemistry. A 2S supercap store (2× 2.7 V 5 F radial + balance —
the Pro/Max supercap-provision cell pattern, shared sourcing; LCSC carries none per
the 2026-07-15 study gate, consigned line) harvests from the DUT's own 5VSB/5V ways
through a brick-mounted 33 Ω 2 W flameproof fusible + 5.6 V CV zener, with USB-C 5 V
as the dead-DUT cold-start. 23 J usable ≈ 12 min held-TEST ≈ 16 sessions; <60 s
recharge off any live rail; zero standby drain (latching relay + neons). Domain runs
direct from the store against a TLV431 absolute ref (rail 2.5–5.4 V). Storage is
load-bearing (the lamps must survive the DUT's collapse — the box's most important
moment); Li-ion was considered and rejected for this duty (UN38.3 shipping, BMS,
aging, and a fire-adjacent chemistry inside the fire-eating box). Board spec of
record: beta/smoke-tester/README.md §2.

**2026-07-25 addendum (owner first-use-UX challenge — "do I have to charge it up
before I use it at all?" — answer: NO, and now structurally no):** the domain rail
became a diode-OR of a second fused harvest-direct leg (RW_D 33 Ω on the brick →
D_DOM → Z_DOM/C_DOM) and the store (via D_ST2). First light ≈ instant (~ms) on any
live DUT rail or USB brick — no pre-charge ritual, no first-plug dark window; the
store's job narrows to ride-through + LAMP TEST depth. Same-day VE-2 had already
cut the cells 5 F→2 F, so the figures in the paragraph above are superseded twice:
current numbers are 1 F net, 5.0→2.8 V = 8.6 J ≈ ~4.5 min held-TEST ≈ ~5 sessions,
store usable ~30 s / full ~2 min. Spec of record unchanged:
beta/smoke-tester/README.md §2.

### 9.8 Platform-impact resolution (owner Q, 2026-07-25: "does tester use force every
platform input/output onto a daughterboard?") — NO, three-layer answer

The smoke tester's consumable-connector logic does NOT generalize backward onto the
platform, because the wear physics splits by duty:

1. **Consumer/inline modules: wear is moot by CYCLES.** An installed module sees a
   handful of matings ever (install count), regardless of current. Nothing changes.
2. **Tester-deck duty: wear is real** — unlike the smoke tester's 0.26 A megohm-divider
   reads (1.4 mW at spec-death), deck paths run 6–13 A/contact where a +20 mΩ worn
   contact = 0.7–3.4 W of heat and 0.3–1 V of drop at load. But the family ALREADY
   carries the layered answer, designed before this question was asked: (a) modules in
   the deck are themselves blade-socketed swappable fixtures (the module IS the deck's
   "snout"); (b) `hpwr-fixture-head` exists in the census precisely as "the per-test
   wear position; replaceable by design"; (c) tester 12d port-end Kelvin / dual-ended
   metrology makes the MEASUREMENT immune to contact drift (current is Kelvin-shunt
   native and never sees contact R at all); (d) the 12d live per-pin resistance map
   covers the FIXTURE path as well as the DUT cable — **the tester instruments its own
   wear** and can alarm "fixture contact drifting" in firmware, zero hardware.
3. **The missing cheap layer is a cable, not a board: CONNECTOR-SAVER pigtails**
   (standard aerospace/EMC-lab practice) — a $2–4 male↔female stub that absorbs 100%
   of DUT matings on a deck fixture and gets tossed on drift; sell as a tester
   accessory (FOLLOWUPS 2026-07-25). Zero board changes platform-wide.

Bounding note: the OUTPUT side of 24-pin/EPS/PCIe is ALREADY the daughterboard
architecture (v1.4.0, ratified for pin-mapping/productization, ~$3–5/board) — the
"everything gets a daughterboard and everything gets expensive" scenario is exactly
half-true already, adopted where it earns its keep, and stops there. Input headers
stay board-mounted platform-wide.

### 9.9 Correction to §9.8 (owner objections sustained, 2026-07-25): savers scoped WAY
down; the real deck answer is the GENERALIZED FIXTURE HEAD

Two §9.8 claims corrected:

1. **Connector-saver pigtails RETRACTED for 12VHPWR and for all metrology paths.**
   The owner's objection is exactly the platform's own §2.8 ruling: the 12VHPWR
   module soldered its pigtail specifically to REMOVE mated pairs from the melt-prone
   path — a saver adds one back, unmonitored, and instrumenting it would spawn a
   manufactured line item that defeats the "dumb cheap cable" point. More generally,
   an uninstrumented series resistance inside a metrology path contaminates DUT
   characterization (~20–30 mΩ fresh ≈ 0.2–0.3 V at 10 A ≈ 2%-class error on 12 V)
   unless baselined. Savers survive ONLY as a shop-optional accessory for lamp-class
   checks (smoke-tester regime), never on 12VHPWR, never inside ST/Pro/Max metrology.
2. **Module-as-the-wear-unit RETRACTED as doctrine.** Eating a $35 module is a poor
   consumable; eating a $600+ Pro/Max module is absurd. Modules-as-swappable is a
   last-resort serviceability fact, not the wear plan.

**The corrected deck doctrine — generalize the family's own existing pattern:** the
census already contains the answer in one row: `hpwr-fixture-head` = "the per-test
wear position; replaceable by design." Generalize it: **every deck slot family gets a
cheap passive FIXTURE HEAD** (atx24 / EPS / PCIe heads alongside the existing HPWR
head — family-keyed small board carrying the DUT-facing connector + sense contacts,
$3–10 class), and the measurement SENSES AT THE HEAD (the tester-12d port-end Kelvin
pattern + the OQ-88 sense-return contacts already queued). That one move buys all
three properties the owner demanded at once: (a) the per-DUT mating lands on a $3–10
part, so the $35–$600+ module NEVER accumulates matings (head↔deck mating cycles
only when a head is replaced — rare); (b) the head is INSTRUMENTED, not a blind
added joint — the 12d live per-pin resistance map was designed precisely to see
contact degradation at this position, so head wear is a trended, alarmed quantity
("replace head" is a firmware message with a number behind it); (c) head contact
drops sit outside the sense point, so DUT characterization stays honest as the head
wears. Cost honesty: per-family heads are new small SKUs (bounded: ~3 new boards,
shared across ST/Pro/Max decks) — but they were already half-built: the HPWR head
exists in the census, OQ-88 carries the sense-return contact provision, and 12d
carries the monitoring. The $600 module's remaining exposure in deck duty is DUT
violence, and that is bounded by the three cheaper layers in front of it: smoke
tester triage → per-slot fuses/fences (§12c) → the fixture head.

**Relationship to the v1.4.0 daughterboards (owner clarifier, 2026-07-25):** same
architectural family, different member — NOT the same board. The v1.4.0 output
daughterboards sit on the module's OUTPUT side (blade tabs + output field, female-
end role, pin-mapping/productization, consumer inline use; already assigned a deck
role too — the OQ-89 retail assembly as empty-slot filler, tester-standard README
Phase 2). The FIXTURE HEAD is the input-side sibling: essentially "the module's J3
male input header on its own small board," DUT-facing, with the OQ-88 sense-return
contacts POPULATED (the concept already exists as the SR1–6 DNP pads on
atx24-out-db). Genders/roles differ so they cannot be one PCB, but they share the
ecosystem: passive, keyed, cheap, blade/header-connected, fab-panelized together,
and the same sense-contact provision.

**§9.9 ruling update (owner, 2026-07-25):** the fixture head is RULED as a plain
STRAIGHT-THROUGH connector board, resold off-the-shelf (ModDIY class) for 24-pin/EPS/
PCIe; monitoring = per-head install baseline + ΔV/ΔI drift trend in the tester program;
the designed-PCB-with-sense-contacts version is demoted to an upgrade rung; 12VHPWR
keeps its designed fixture-head. Spec of record moved to testers/DESIGN-SHEET.md §A.

### 9.10 Intentional arcs — the spectacle riff (owner ask 2026-07-25, PROPOSED — decision #14)

Owner: the neon tubes suggest INTENTIONAL arcs inside the tester — make it a spectacle.
The riff, engineering-honest (12 V can't arc in air; spectacle needs either fault energy
or a contained HV source — both have legitimate versions):

1. **The REAL arc, framed: glass-bodied GDTs on the brick, in the witness window.** A
   gas-discharge tube IS a packaged spark gap — sealed, surge-rated, $0.15–0.40. Put
   GLASS-bodied GDTs (~90–150 V sparkover) across the ways on the sacrifice brick,
   visible through the witness window: on a mains event the GDT FIRES — a genuine
   orange-purple arc flash in a glass tube, powered by the fault's own energy — while
   the witness puffs and the fuses clear. And it is FUNCTIONAL, not decoration: a GDT
   is a harder, faster crowbar than the MOV for the mains class (arc voltage ~20 V →
   maximum fuse-clearing current; follow-current is exactly what we want and the
   blade+HRC series pair is the required disconnect — textbook GDT+fuse coordination).
   Coordination split: MOV keeps the 20–90 V OV class the GDT can't see; GDT takes
   ≥~90 V/mains; both die through the shared witness. Brick +$1–2. **Every photon is
   evidence** — the box never fakes drama at verdict time.
2. **The always-available show that is secretly a SAFETY SELF-TEST: LAMP TEST.** Neon
   bulbs die of old age — and a dead CASE-LIVE bulb is a silent safety failure on the
   most safety-critical indicator in the box. Add a momentary **LAMP TEST / SHOW**
   button: a tiny contained blocking-oscillator boost (~100 mW from the supercap
   store, runs ONLY while held) strikes every gas bulb — both earth-domain neons, the
   blown-fuse neons, and one **flicker-flame neon tube** (the candle-flame type: a big
   sealed electrode plate where the glow dances chaotically — a tiny contained plasma
   storm, the best-looking gas physics money can buy at $1–2) behind its own jewel.
   Shops get the counter demo ("this is what a lying PSU looks like") with no bad PSU
   required, and every press proves the safety lamps actually strike. Panel doctrine
   gets its one carve-out, printed: "a lit neon is ALWAYS bad news — unless you are
   holding LAMP TEST."
3. **Fences (named and hard):** sealed devices ONLY — no open spark gaps in air ever
   (ozone, ignition, EMI, and it IS the hazard the box exists to catch; Jacob's
   ladder named and REJECTED). No HV reachable at any user point; the boost is
   momentary-held, dies with the button, µA-per-bulb through megohms (same limiting
   class as the fault-driven paths); and the **never-generate-what-you-detect rule**:
   the instant LAMP TEST releases, the earth-domain neons are trustworthy again —
   no latched show modes, no ambiguity.
4. **The spectacle ladder this completes** (each tier honest): green way-cascade =
   good news → needle slam = weirdness → neon glow/flicker = danger → GDT arc flash +
   witness smoke = the event itself. BOM adder ≈$3–4 total (GDTs + flicker tube +
   boost); retail holds at $79.

**Decision #14 (owner):** adopt (a) glass GDTs on the brick + witness-window placement,
(b) LAMP TEST/SHOW button + flicker tube, (c) both, or (d) neither. Recommendation:
BOTH — (a) improves the mains-class crowbar while making the event visible, (b) turns
the show into a recurring safety self-test; together they are the product's soul made
visible. Board README/BOM untouched pending the nod.

### 9.11 The literal smoke, on demand — SMOKE SHOT (owner "I do want that," 2026-07-25)

The founding fantasy ("bonus if the fuse literally smokes") already happens on real
events — the brick witnesses puff behind the theater window, and that is never an
annoyance because when a witness smokes the brick was already dead (the smoke IS the
replace-me flag). What was missing: smoke you can SHOW someone without spending a $4
brick. Answer = a dedicated demo branch with cap-gun economics: 12 V input → 10 A
time-lag 5×20 HRC (0215010.MXP C142733, same family/holder as the way HRCs, fuse-first
at the branch head) → red horn-class SMOKE momentary (held-only) → a socketed pellet =
the SAME KNP 1 Ω 1 W flameproof witness part the brick carries (C1741442), in a
tool-less clip behind the window. 144 W into a 1 W flameproof part = the designed puff
in ~100 ms; the 10 A fuse carries the shot forever and only dies in the
mains-while-pressing corner (which it breaks safely at 1.5 kA/250 VAC — the identical
worst case the brick witnesses accept, same part). Reload = pull-and-press, ~$0.02 a
shot, 20-bag in the kit, 50-bag refill SKU. Consumable ⑤: the only part that dies on
purpose. Fences kept: held-only (LAMP TEST precedent), sacrifice-first branch,
flameproof puff not flame, #4 chamber review grows to demo cadence (vent sizing,
shots-per-minute silk), printed carve-out: "smoke is ALWAYS a real event — unless
you're holding SMOKE." Board spec: beta/smoke-tester/README.md §2 table row 5 + §4.

### 9.12 AUX adapter port — DESCOPED (owner scope objection SUSTAINED, 2026-07-25)

The owner caught a real inconsistency: the original refinement ruled 24-pin-only
scope, and the agent's later defense of the AUX port ("borrowed modular cables kill
drives — invisible until it kills") proves too much — by that logic the box would
need a port for every cable on the PSU. Ruling: checking other cables is a quick DMM
pinout job (or the metrology deck's — per-cable checking already lives there,
testers/DESIGN-SHEET.md §A), NOT this box's mission. AUX subsystem removed entirely
(port, 3 AUX ways, continuity way, adapter accessory SKUs; §9.1/§9.6 adapter text +
decision #6's port half are superseded); the safety framing is retracted on the
record. −$3.5–4 BOM (rollup ≈$39–41 @100), brick 2×8, LM339 back to 6 packages,
meter position 6 re-pointed to the supercap STORE. A standalone cable-pinout checker
remains a possible separate tiny product, someday, not this box.

### 9.13 Both grids, one box (owner Q, 2026-07-25)

120 VAC and 230+ VAC input PSUs need no variants and no switch: the tester touches
only DC outputs (identical either way); fuse CURRENT ratings key on the tester's own
input-agnostic draw; and every mains-facing element was specced at the 230 VAC /
325 Vpk worst case, which contains 120 V as the milder instance (250 VAC-class HRCs,
300 V-working dividers + creepage, 90 V strike points that fire from 170 Vpk up).
One distinct corner named honestly: the PSU's primary PFC bus (~380–400 VDC, no
zero-crossings) — real-world it arrives through the fault's own impedance, bounded
by the DUT's input fuse + bulk energy; proven at the arc bench (explicit DC-ingress
row). Spec: beta/smoke-tester/README.md §3 both-grids note.

### 9.14 How realistic is an incursion, and how the box handles the DC one (owner Q, 2026-07-25)

Realism ladder, most→least common in the sketchy-PSU population (adverse selection —
this box exists precisely because its clientele is the tail):

1. **Leakage / tracking (kΩ–MΩ path, µA–mA): REALISTIC and the dominant case.**
   Counterfeit non-Y "Y-caps" failing short-ish, moisture/condensation, conductive
   dust, carbon tracks from a prior surge, rodent damage. Presents as the chassis or
   a rail FLOATING toward mains potential — can't push current, but shocks humans
   and kills logic. The box handles it perfectly and undramatically TODAY: the ~90 V
   neons strike at zero current (CASE LIVE / RAIL LIVE), windows read wrong, no fuse
   even blows. This case is the CASE-LIVE neon's entire reason to exist, and it is
   the one that actually hurts people.
2. **Arcing / intermittent partial breakdown (tens–hundreds of Ω): plausible.**
   Energy bounded per flash; MOV/GDT clamp it, the witness puffs, fuses clear on the
   follow-through. The arc bench's 230 VAC row is this case's proof.
3. **Hard AC-mains connection to an output: rare but real** — the melted garbage
   PSU, the flood survivor. Designed case: 250 VAC sand-filled HRC breaks it; blade
   arc rides through to the HRC by intent (the founding coordination story).
4. **Stiff 400 VDC bulk-rail connection: the rarest**, requiring catastrophic
   multi-point transformer failure — and physics bounds it: the bulk is a 30–45 J
   capacitor bank behind the PSU's own input fuse, so the event is a
   tens-of-milliseconds droop-to-dead dump, never a continuous 400 V source.

Handling for case 4 (spec'd in README §3): the designed WITNESS-FIRST sequence — GDT
strikes and hogs current, the 1 Ω witness opens sub-ms and disconnects the clamp
leg, the way then floats behind megohm dividers (individually inside their voltage
ratings at 400 V) with neons/windows indicating — so no 32 VDC blade or 250 VAC HRC
is ever asked to break 400 VDC, PROVIDED min-load is out of circuit: hence the new
**FIRST-CONTACT RULE (MIN LOAD off until first green)** on silk + truth-table. With
MIN LOAD engaged the event is still dump-energy-bounded (blade arcs for the droop
duration, HRC + sand backstop). Both cases are explicit arc-bench DC rows. The
10×38 gPV solar-fuse upgrade (1000 VDC breaking, ~+$15–20, much larger board) was
evaluated and REJECTED as disproportionate. Bottom line: the case that is actually
common (leakage → hot chassis) is handled silently and perfectly; the case that is
theatrical (mains arc) is the designed show; the case that is rarest (stiff bulk
DC) is sequence-handled and bench-proven, not fuse-rated away.

### 9.15 Show for the STANDARD kill + mains-tier cost autopsy (owner Qs, 2026-07-25)

**A. The gap is real:** today's spectacle ladder reserves all the drama for the rare
events. A standard LV failure (short / cap dump / overload — the event the box eats
WEEKLY) blows a 1 A blade and lights one red LED. 12 V-class events physically cannot
strike a 90 V neon, fire a GDT, make a 22 V MOV conduct, or puff a witness — so the
common kill is silent. PHYSICS FENCE kept honest: a REAL arc only comes from real
fault energy (µA of boost makes a faint glow, not the 5 kA flash) — arcs stay
reserved for genuine mains events; faking them is out.

**PROPOSED — the "AFTERMATH SHOW" (~$0.35–0.40, pending owner nod; touches the #14
held-only fence DETAIL but preserves the fence itself):** when any event latch is set
(blown-fuse condition on any way ∨ any red-window latch ∨ reverse latch) AND TEST is
held, the existing LAMP-TEST boost is ALSO enabled (diode-OR of the button with the
latch signal, gated so HV still exists ONLY while a human holds TEST) into: (a) the
flicker-flame tube — it dances while you read the verdict ("the box is digesting");
and (b) ONE added EVENT neon wired as a classic RELAXATION BLINKER (boost → 4.7 MΩ →
470 nF/250 V → NE-2 ≈ 1–2 Hz flash at µA average) in the theater bay. So the standard
kill's ritual becomes: pop → hold TEST → dead way lamp + BF LED + dead needle + the
flame tube dancing + a blinking neon + the visibly blackened clear-window blade. New
parts: 1× NE-2 (consigned ~$0.10) + HV R/C (~$0.10) + enable diodes (~$0.05); the
flame tube, boost, and jewels already exist. FENCES: HV dies with the button
(held-only preserved — the latch alone never powers the boost); sealed devices only;
never-generate-what-you-detect intact — the earth-domain CASE-LIVE/RAIL-LIVE neons
stay zero-powered pure detectors, physically separate lamps from the show bay; "a lit
neon is ALWAYS bad news" still true (an event IS bad news). Decision: #15 (this
section) — nod turns it into README §4 + BOM lines.

**B. Mains-tier cost autopsy ("can we solve it cheaper, since it's super rare?"):**
what mains handling actually costs today, all-in ≈ **$2.3–2.5/box**: interrupter tier
6× HRC ($0.64) + 6 covered holders ($0.37) + 2 kit spares ($0.21) ≈ $1.2; clamp tier
5× GDT ($0.85) + 5× MOV (~$0.20) + 5× witness ($0.05) ≈ $1.1; creepage + 300 V
divider strings ≈ free (layout + parts already needed for measurement). Alternatives
EXAMINED AND REJECTED, each for a load-bearing reason: (1) delete the HRC tier and
bet on the witness-first race — loser scenario is a 32 VDC blade arcing at 325 Vpk
inside an unrated plastic ATO holder = a fire path inside the fire-eating box; the
founding #3 coordination ruling stands. (2) ONE shared HRC in the common GND return
(−$0.7) — interrupts everything at once, killing all indication mid-event (observing
the event is the box's #1 job) and floating the box after clearing. (3) Series
fusible-resistor ways instead of fuses — 0.26 A of legitimate bleeder current through
enough resistance to matter at mains = ~7 % measurement error, breaks the ±5 %
windows. (4) PCB-trace fuses — free but unserviceable, carbon-tracks FR4, violates
the hardware-store-refillable trust story. (5) MOV-only (drop the GDTs, −$0.85) —
loses crowbar hardness AND the show (contradicts question A). The one live lever:
covered BLX-A holders → bare solder clips (−$0.25) — declined under the quality
doctrine (covered, finger-safe, tool-less service on the mains-rated tier). VERDICT:
the mains tier is already at its honest floor, ~half of it is double-booked as the
show, and the real money was the AUX descope (−$3.5–4). Recommendation: no change.
