# Smoke Tester — sacrificial first-contact PSU triage box (beta line)

**Status: DRAFT, sketch-stage, SIGNED OFF — sourced, capture next** (the
`tester-standard` convention: folder + design basis first, gated capture as its own
phase). Stood up 2026-07-24 (decision #1); **OWNER SIGN-OFF 2026-07-25 ("I approve of
your recommendations on all counts")**: decisions #2 terminator fence, #3 blade+HRC
coordination, #5 earth pigtail, #9 $79 retail, #11 spare brick in-box, #12 consumables
ladder, #13 keep snout paddle, **#14 arcs BOTH** (GDTs + LAMP TEST) = RULED; #4 smoke
chamber = adopted pending the flammability/venting review; #8 = pro-tool disclaimer
posture v1; **#10 bundle position remains OPEN** (no recommendation was offered).
BOM = LCSC-primary sourcing pass done 2026-07-25 (jlcsearch-verified, §6). Sub-boards
live in their own folders: `brick/`, `snout/`, `faceplate/` (§8 structure). Design
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
  −12 V presence, hot-ground ("CASE LIVE") detection. Survives mains-on-any-output
  by design; repair = consumables.
- **Never:** metrology (±5 %-class lamp windows only), load testing beyond min-load
  bleeders, ripple, OCP hunts, data links, MCUs, inline operation. It TERMINATES the
  DUT — nothing of ours ever sits downstream of it. Green lights here earn the DUT
  its interview with the 24-pin module / ST deck; that is the whole product ladder.
- 24-pin only, deliberately: no other PSU connector adds a voltage domain (EPS/PCIe/
  SATA/Molex are the same secondary nodes), and PS_ON# lives on the 24-pin, which
  makes it the mandatory core. Per-cable wiring faults are a DMM / metrology-deck
  job, NOT this box's (owner re-ruling 2026-07-25 — AUX port DESCOPED, §5).

## 2. Architecture — three domains, four consumables, one structural rule

See `assets/smoke-tester-block.svg` (electrical) and
`assets/smoke-tester-board-map.svg` (physical boards + connectors).

**Domains.** (a) THE SACRIFICE PATH (DUT copper): snout → blade fuse → HRC backup →
clamp brick → way node → bleeders/dividers. (b) THE FLOATING MEASUREMENT DOMAIN:
comparators + lamps + meter, powered by the **batteryless instant-on supply**
(harvest-direct ⊕ supercap store, below),
referenced to DUT GND and floating relative to earth — it keeps indicating even when
DUT GND rides line potential. (c) THE EARTH-NEON DOMAIN: nothing but neon bulbs and
megohms between DUT nodes and the earth reference — zero powered electronics, strikes
at ~90 V, lights **CASE LIVE**.

**Power — batteryless, self-charging, INSTANT-ON (owner no-disposables directive
2026-07-24; harvest-direct bypass added on the owner's first-use-UX challenge,
2026-07-25):** no battery of any chemistry — and **no charge-before-first-use
ritual**. Harvest front end: 5VSB-way ⊕ 5V-way ⊕ USB-C 5 V through ORing Schottkys
(D_H1..D_H3) onto one common node. Off that node hang TWO independently fused legs
(both fusibles on the brick — the harvest tap's protection is sacrificial like
everything else): **RW_H 33 Ω 2 W → Z_ST 5.6 V CV clamp → the 2S supercap store**
(2× 2.7 V 2 F radials + 2× 100 kΩ balance — the EXACT Pro/Max-provision cell class,
one shared buy; VE-2 2026-07-25, was 5 F), and **RW_D 33 Ω 2 W → D_DOM → Z_DOM
clamp + C_DOM → the domain rail directly**. The domain rail is the diode-OR of that
harvest-direct leg and the store (via D_ST2): the instant ANY source is live — a DUT
rail or a phone brick — the panel is up in ~ms (only C_DOM charges, not the farad),
while the store fills behind RW_H in parallel (usable ~30 s, full ~2 min; ~150 mA
initial, 0.76 W in the 2 W part). The OR hands over by itself: when the DUT sags or
collapses, D_ST2 conducts and the lamps/latches ride straight through the exact
event they are reporting — the load-bearing storage property, preserved and now the
store's WHOLE job (ride-through + LAMP TEST depth), no longer the first-light path.
Store math: 1 F net, 5.0→2.8 V usable (D_ST2's diode drop raises the old 2.5 V
floor) = 8.6 J ≈ **~4.5 min of held-TEST ≈ ~5 DUT sessions** of reserve; zero
standby drain (latching relay + neons need nothing at rest). No LDO anywhere: all
thresholds compare against a TLV431 1.24 V absolute reference, so the rail may ride
2.5–5 V; way lamps are 2 mA high-efficiency red / 570 nm yellow-green (Vf ≤2.1 V)
so indication holds to the rail floor. First-light timeline: earth-domain neons
0 s, always (they need no power, ever); comparator panel ~ms on any live rail or
USB; the ONLY dark panel is store-empty AND nothing-live — which is itself a
verdict (no 5VSB = dead standby), and the **STORE OK** tick — now the bottom step
of the §4 six-step CHARGE bar (store >2.9 V while TEST held) — disambiguates
dead-box from dead-DUT; any phone brick arbitrates. Why supercap (vs Li-ion): the energy need is tiny and refilled
every use; EDLC ships with no UN38.3 lithium compliance, has no BMS, no aging
cliff, 10+ year life — and no recharge chore ever, because using the tool charges
it.

**The structural rule (what makes "modular" true):** *no main-board copper sits
electrically upstream of a sacrifice element, and measurement taps enter only through
≥900 kΩ of series 300 V-rated resistance.* The main board survives by impedance and
by coordination, never by luck. Way copper is laid out to 300 V-working creepage
(≥3.2 mm) — a layout gate, recorded in §9.

**The consumables (all socketed) — four that die from faults, one that dies on
purpose:**

| # | Part | Where | COGS | Dies from |
|---|---|---|---|---|
| 1 | ATO blade fuses, **1 A fast, one value everywhere** | panel sockets | ~$0.10 | everyday overcurrent (shorts, cap dumps) |
| 2 | HRC 5×20 ceramic sand-filled, **2 A time-lag, 250 VAC, 1.5 kA breaking** | internal twist holders | ~$0.35 | mains-class interruption (what a 32 V blade cannot break without arcing) |
| 3 | **Sacrifice brick SB1** — 5 MOVs (uniform 22 V, see brick/README) + ◆5 GDTs (VE-1; the visible mains crowbar) + 5 witness fusibles + 2 harvest fusibles (store leg + instant-on domain leg), one keyed plug-in PCB | 2×8 socket pair | ~$3.50 | any OV/mains event (doctrine: mains event ⇒ fuses AND brick) |
| 4 | **Snout SN1** — the 24-pin male header on a passthrough paddle (standard tin) | keyed 2×13 shrouded header | ~$3.1 | **mechanical damage only** (bent pins, broken latch, mangled DUT connectors) — cycle WEAR ruled functionally irrelevant at this box's duty; see the resolution note below |
| 5 | **◆ SMOKE pellet** — the same brick-witness KNP 1 Ω flameproof, in a tool-less panel clip behind the theater window (§4 SMOKE SHOT) | 2-point clip | ~$0.02 | **the SMOKE button** — the only part that dies on purpose (the demo; real-event smoke still comes free from the brick witnesses) |

**Physical partitioning — what is a daughterboard and what isn't (owner Q,
2026-07-24):** the consumables are deliberately NOT one combined sacrificial
daughterboard — they are partitioned by DEATH CAUSE so you never throw away good
parts with dead ones. Blades (everyday-event clock) and HRCs (mains-event clock) are
bare socketed fuses, not boards — keeping the blades in standard panel sockets is
what keeps them hardware-store-refillable (the trust story). The BRICK is the one
true plug-in daughterboard: it groups exactly the parts that die TOGETHER in a
single event class (a mains event degrades the MOV and opens its witness in the same
half-cycle — undiagnosable individually without gear, so the service unit is the $3
board). The SNOUT is the second plug-in board — and its justification is now DAMAGE ONLY.
CYCLE-WEAR RESOLUTION (owner bench pushback, 2026-07-24 — owner RIGHT, resolved
with numbers): the Molex durability specs (30 cycles std PS-5556 / 100 cycles HMC
gold PS-444850001) qualify a low-level-contact-resistance floor (+10–20 mΩ class)
that matters at HIGH-CURRENT duty (at 6 A real-PSU use, 20 mΩ = 0.72 W of heat in
one contact — that is what the spec protects). This box reads voltage through
megohm dividers at ≤0.26 A: a contact would have to degrade to **2.3 Ω — 115×
worse than spec end-of-life — before a ±5% window lamp even reaches its edge**
(0.26 A × 2.3 Ω = the 0.6 V window half-width; a spec-dead 20 mΩ contact
dissipates 1.4 mW here). Owner bench experience (hundreds of matings on PSU
testers, zero issues) is exactly what this physics predicts. CONSEQUENCES:
wear-based snout replacement is RETIRED from the consumables story and forecast;
the HMC/gold adder is DROPPED (standard tin is correct at this duty); the snout
survives only as a DAMAGE/SERVICE spare — bent pins from cross-insertion, broken
latch, a mangled DUT connector chewing ours — plus a production sub-assembly
convenience (the consigned Mini-Fit hand-solder happens on a $0.6 paddle, not the
main board). Open decision #13: KEEP the paddle (recommended — damage repair
without board rework, ~$1.3 delta) vs board-mount the connector directly (−$1.3,
one less board, damage = main-board rework). Connector tech: keyed 0.1 in header
sockets, NOT the platform TE-blade ecosystem — the module output daughterboards
carry 18–52 A continuous (30 A blade joints earned); the brick carries ≤0.6 A
continuous and big current only as fault transients. Pulse math for the socket: a
230 VAC clearing event pushes ~50–150 A through one pin pair for <10 ms ≈ 0.5 J ≈
+13 K adiabatic in a brass pin — inside a 3 A-rated pin's pulse capability, events
are rare by definition, and the brick pinout doubles the GND return pins anyway
(2×8 = 16 positions: 5 ways + 5 returns + harvest node in + store & domain legs
out + 2 key/spare). Contact-pitting
after repeated mains events is a first-article bench watch item, not a redesign.

**Blade format (ruled at refinement): full-size ATO/ATC (19 mm)** — not Mini/ATM or
Micro2/3. Reasons: the most universal automotive format on earth (the trust story),
the best panel-holder availability, glove-friendly handling, standard color code
(brown = 1 A everywhere), and panel real-estate is not the constraint. Mini would
save ~40% panel width at the cost of fiddlier handling and thinner corner-store
coverage.

**Coordination story (why two fuses in series):** the 1 A fast blade clears every
low-voltage event first (selectivity by rating ratio 1:2 and speed class F vs T).
In a mains event the blade opens but can sustain an arc (it is a 32 VDC part); the
current continuing through the arc cooks the 2 A time-lag HRC, which is built to
break 250 VAC into sand. The witness resistor (1 Ω flameproof fusible, in series
with its MOV) opens with its designed benign puff — that is the safe smoke — and
disconnects the spent MOV so a failed-short varistor cannot latch the way.

## 3. Per-way electrical spec

See `assets/smoke-tester-way-sketch.svg`. Five fused ways (core only — the 3 AUX
ways + continuity way were DESCOPED with the AUX port, owner ruling 2026-07-25, §5).
All windows ±5 % nominal, LM339 comparator pairs against a TLV431-derived ladder; taps measure DOWNSTREAM of the sacrifice chain (post-event a
way honestly reads dead).

| Way | Blade | HRC | MOV (brick) | Witness | Divider (to DUT GND) | Window at node |
|---|---|---|---|---|---|---|
| 12 V | 1 A F | 2 A T | S14K14-class (14 VRMS / ~22 V VV) | 1 Ω 1 W fusible | 903 k / 100 k (÷10.03) | 1.137–1.257 V |
| 5 V | 1 A F | 2 A T | S14K6-class | 1 Ω 1 W fusible | 903 k / 100 k | 0.474–0.524 V |
| 3.3 V | 1 A F | 2 A T | S14K4-class | 1 Ω 1 W fusible | 903 k / 100 k | 0.313–0.346 V |
| 5VSB | 1 A F | 2 A T | S14K6-class | 1 Ω 1 W fusible | 903 k / 100 k | 0.474–0.524 V |
| −12 V | 1 A F | 2 A T | S14K14-class (MOVs are bidirectional = free reverse clamp) | 1 Ω 1 W fusible | 100 k to +2.5 V bias / 15 k / 903 k string | level-shifted window, healthy/absent/OV separable |

**MOV column SUPERSEDED at sourcing (2026-07-25):** the brick populates a UNIFORM
14D220K (22 V) disc on every way — LCSC carries no low-voltage 14D discs in depth,
and one value = one brick pattern. Consequence recorded honestly: the 6–25 V OV band
on minor rails is DETECT-ONLY (windows lamp red); crowbar action begins where the
22 V MOV conducts, and the ◆GDT (~90 V sparkover) + fuses take the mains class. −12 V
shares the same bidirectional disc. Full brick detail: `brick/README.md`.

Divider top legs are 3 × 301 kΩ 1206 in series (voltage sharing — each sees ≤110 V at
230 VAC on the way; 1206 rated 200 V, string rated 600 V). Mains math sanity: 230 VAC
onto a way drives the MOV into conduction at tens–hundreds of amps → both fuses clear
in ≤ a half-cycle, witness opens, comparator node never exceeds ~2.4 V through the
÷10 string even mid-event.

Min-load bleeders (switchable, "MIN LOAD" DPST): 47 Ω 10 W on 12 V (~0.26 A) + 10 Ω
5 W on 5 V (~0.5 A) — enough for group-regulated antiques to regulate, small enough
that 1 A blades never see >0.6 A legitimate. **FIRST-CONTACT RULE (owner Q
follow-through, 2026-07-25): MIN LOAD stays OFF for first contact — throw it only
after the first green read.** With the bleeders out of circuit, the only conduction
paths during the riskiest window are the self-disconnecting clamp legs (witness
opens in sub-ms) and the megohm dividers — a DC incursion then has NO low-impedance
path that would force the 32 VDC-class blades into a breaking role at 400 V. Panel
silk + the truth-table card carry the rule.

**Both grids, one box (owner Q, 2026-07-25):** the tester touches only the DUT's DC
outputs, so whether the PSU eats 120 VAC or 230+ VAC changes NOTHING in normal
operation — the secondary rails are the same 12/5/3.3 V either way, and the fuse
CURRENT ratings key on the tester's own draw (bleeders + microamp taps), which is
input-agnostic. Input voltage matters only for the mains-on-a-rail FAULT class, and
every mains-facing element is specced at the 230 VAC / 325 Vpk worst case, which
covers 120 V automatically as the milder instance: 250 VAC-class HRC interrupters
(ways + smoke branch), 300 V-working divider strings + ≥3.2 mm creepage, and strike
points (GDT/neon ~90 V) that fire from 120's 170 Vpk just as well. Same fuses, both
grids, no switch, no variant. The one distinct ingress is the PSU's PRIMARY PFC BUS
(~380–400 VDC, no zero-crossings — harder to break than AC): in the real fault it
arrives through the failure's own impedance and is bounded by the DUT's input fuse +
bulk-cap energy; the arc bench carries an explicit DC-ingress row (§9) to prove the
HRC/GDT chain there rather than hand-wave it.

**DC-incursion handling — the designed sequence (owner Q, 2026-07-25).** A stiff,
continuous 400 V source is not a physical PSU presentation: the bulk rail is a
CAPACITOR BANK (~390–560 µF at ~400 V ≈ 30–45 J) behind the PSU's own input fuse —
a hard primary-to-secondary breakdown delivers a tens-of-milliseconds droop-to-dead
dump, not a lab supply. The box's designed response ORDER exploits that: (1) GDT
strikes (arc ~20 V) and hogs the current off the MOV; (2) the 1 Ω witness — the
lowest-value, fastest element in the chain — opens in sub-ms at dump currents and
DISCONNECTS the clamp leg; (3) the way then floats at fault potential behind ≥900 kΩ
dividers (3×301k 1206 = 133 V/element at 400 V, inside their 200 V rating, 59 mW
each) while neons + red windows scream — with MIN LOAD off (first-contact rule
below) there is NO path left that asks a 32 VDC blade or 250 VAC HRC to break DC at
400 V. If MIN LOAD was engaged when the DUT let go, the event is still bounded by
the dump energy (blade arcs for the tens-of-ms droop, HRC + sand as backstop) — the
bench DC row proves both cases. UPGRADE PATH EVALUATED AND REJECTED: 10×38 gPV
solar fuses (1000 VDC breaking, the cheap high-DC commodity) on every way ≈ +$15–20
and a much larger board — disproportionate for a corner that physics already bounds
and the sequence already handles; recorded so the decision is visible (realism
ladder: concept §9.14).

## 4. Controls and indication

See `assets/smoke-tester-ctl-sketch.svg`.

- **Arm/fire:** missile-cover toggle → RC pulse → SET coil of K1, a **latching relay**
  (zero hold current — the store never drains at rest). SIMPLIFIED AT SOURCING
  (2026-07-25): K1 = Hongfa **HF3F-L/5 single-pole latching** (C190594) — the DPDT's
  pole B is retired because the PG-race t=0 is taken from the **PS_ON# node itself**
  (a spare LM339 section watches the line cross low — more truthful than a relay
  pole). The contact closes PS_ON# → GND through 100 Ω with a PESD5V0S1BA clamp
  (C5261083). Lid-open microswitch or DISARM pulses the RESET coil: **an open fuse
  door IS the safe state.** The user's finger never touches DUT copper.
- **◆ LAMP TEST / SHOW (decision #14, RULED 2026-07-25):** momentary button →
  contained blocking-oscillator boost (SS8050 + coupled inductor + M7, ~100 mW from
  the domain rail — store ⊕ harvest-direct, so it works on the very first plug —
  alive ONLY while held) strikes every gas bulb + the flicker-flame tube.
  The show doubles as the safety self-test for the CASE-LIVE bulb (a dead neon is a
  silent safety failure). Fences: sealed devices only, HV only while held OR while
  a live event condition holds the panel awake (#15 amendment, 2026-07-25),
  never-generate-what-you-detect; panel carve-out printed: "a lit neon is ALWAYS bad
  news — unless you're holding LAMP TEST." ◆ Glass-check GDTs live on the brick (§2
  table) behind the theater-bay window.
- **◆ SMOKE SHOT (owner "I do want that", 2026-07-25) — the literal smoke, on demand,
  cap-gun economics:** a DEDICATED demo branch so a show never costs a brick or a
  blade: 12 V input node → F_SMK **10 A time-lag 5×20 HRC 250 VAC** (0215010.MXP,
  C142733 — same family/holder as the way HRCs, fuse-first at the branch head) →
  SW_SMK chunky red horn-class momentary (held-only) → PELLET1, the SAME KNP 1 Ω 1 W
  flameproof witness part the brick uses (C1741442), in an OFF-THE-SHELF
  button-release spring terminal (KF141V-2.54-2P, C475114 — press, slot, done;
  owner easy-slot ask 2026-07-25) behind the theater window. Physics: 12 V ÷ 1 Ω ≈ 12 A → 144 W into a 1 W
  flameproof part = the designed puff in ~50–150 ms; the 10 A time-lag fuse carries
  the ~1.2× shot without noticing and is ~never consumed; the needle dips under the
  shot (free showmanship). Reload = pull the spent pellet, press in a fresh one —
  same UX as a blade fuse, ~5 s, **~$0.02/shot** (kit ships a 20-bag; 50-bag refill
  SKU). Pathological corner (mains on 12 V while pressing): ~230 A first loop — the
  10 A HRC (1.5 kA breaking) clears it safely; pellet + fuse die contained, the same
  worst case the brick witnesses already accept, same part. Fences: held-only (dies
  with the button, LAMP TEST precedent), pellet is the sacrifice element at its own
  branch head, flameproof puff not flame, rides the #4 chamber/venting review (which
  now also covers demo cadence), and the printed carve-out extends: "smoke is ALWAYS
  a real event — unless you're holding SMOKE." Needs a live 12 V (the demo runs on
  the DUT's own power). Adder ≈ $1.
- **◆ AFTERMATH SHOW (#15 RULED AS AMENDED, 2026-07-25 — automatic):** when a blade
  pops, the box tells you ITSELF. The blown-fuse condition (a passive across-blade
  signal, live only when fuse-open ∧ way-live) diode-ORs (D_AW1..5) into **Q_AUTO**,
  which parallels the TEST switch — the whole comparator domain WAKES on any pop:
  every lamp lights, and the show enable (event ∧ domain-awake, diode-OR'd with the
  LAMP TEST button via D_EN1/2) runs the flicker-flame tube + a dedicated **EVENT
  neon relaxation blinker** (boost → 4.7 MΩ → 470 nF 250 V → NE_EVT, ~1–2 Hz) for as
  long as the condition lives. No button, no ritual: pop → panel wakes → flame
  dances → blinker blinks → dead way lamp + BF LED + the blackened clear blade name
  the way. Power is the DUT's own harvest BY CONSTRUCTION (blown ∧ live guarantees a
  live way feeding the instant-on leg); in the corner where harvest is truly dead
  the store carries ~minutes of panel, then the passive BF LED + blown blade still
  hold the verdict. Kill the PSU or swap the fuse → the condition clears → the box
  sleeps again: zero-standby is preserved EXACTLY, because the wake signal
  physically requires a live way. **FENCE #14 AMENDED (owner-authorized with this
  ruling):** "HV dies with the button" becomes **"HV exists only while LAMP TEST is
  held OR while a live event condition holds the panel awake — and never with the
  fuse door open"** (the same lid microswitch that disarms K1 kills the boost
  enable). The fence's purpose — no HV during service, no HV without cause — is
  intact. Honest boundary: the AUTO path triggers on POPS (the passive signal);
  rails-weird-but-nothing-popped verdicts still show on an ordinary held-TEST read.
  Adds: NE_EVT + blinker RC + Q_AUTO + 7 small-signal diodes ≈ **$0.50 all-in**.
- **PWR_OK race (all analog):** PS_ON#-assert starts a 100 ms / 500 ms two-tap RC; two
  comparator sections latch PWR_OK's rising edge against the taps → PG EARLY / PG OK
  / PG LATE-NEVER lamps (ATX spec window, coarse by design).
- **Hot-ground:** NE-2 neon chains through 2×470 kΩ 0.5 W each: DUT-GND ↔ EARTH
  ("CASE LIVE") and an OR of the four positive ways through 1 MΩ each into a second
  neon ("RAIL LIVE"). Earth reference = rear earth pigtail (or earth-only IEC inlet —
  open decision #5). Strikes ~90 V; a 48–90 V fault lights nothing (known limit,
  concept §7c — the window comparators still show gross OV). Panel note: the neons
  sit behind large amber jewel lenses — deliberately the most beautiful lamps on the
  box, and a lit one is ALWAYS bad news (the good-news show is the green way-cascade
  and the needle). Near-threshold leakage makes a neon FLICKER (relaxation behavior)
  — eerie and diagnostic: a flickering CASE LIVE means marginal leakage, not a hard
  fault.
- **Needle meter:** 100 µA moving-coil panel meter + 1P6T rotary reading the
  *already-divided* node (it can never see more than a few volts, whatever the DUT
  does), scale printed ×10. No pixels, no MCU — numbers are the module/ST deck's job.
  Positions: 12 V · 5 V · 3.3 V · 5VSB · −12 V · **STORE** (the sixth position
  re-pointed from AUX to the supercap store at the descope — numeric store voltage
  on demand).
- **Lamps:** per-way green (in-window) / red (out), blown-fuse indicator across every
  blade position (lights only when its fuse is open AND the way upstream is live).
  Panel silk = the verdict truth-table; tear-off verdict-card pad ships in the lid.
- **◆ CHARGE bar (owner ask, RULED 2026-07-25):** six 2 mA 3 mm LEDs in a tight
  5 mm-pitch vertical VU column — **2 red / 2 yellow / 2 green, bottom-up** (owner
  color ruling 2026-07-25: fuel-gauge read — red = awake but thin, yellow = partial,
  green = full sessions banked; all XL-302 diffused family, Vf ≤2.1 V, per-color
  series-R trim at capture if brightness wants matching) — hold TEST with anything live (DUT rail or USB
  brick) and watch the store fill, ~20–40 s a step, full bar ~2 min. All-analog in
  the house pattern, zero new part types: one 7-resistor sense string across the
  STORE node (taps at 1.24 V/V_th fractions) into six LM339 sections against the
  TLV431 reference — bar mode falls out free (every step below the level is lit,
  open-collector per-LED), 1 MΩ hysteresis per step so the top LED never chatters
  at the asymptote. The string grounds through a TEST-gated SS8050 (Q_CHG), so the
  sense path drains NOTHING at rest — the zero-standby property survives. Steps
  ≈ 2.9 / 3.3 / 3.7 / 4.1 / 4.4 / 4.65 V ≈ wakes · 20 · 40 · 60 · 80 % · FULL of
  usable reserve; the 2.9 V step wears the **OK** silk tick and ABSORBS the old
  battery-OK dot (STORE-OK = the bar's bottom step; a lone red lit reads honestly
  as "awake, thin reserve — keep it plugged in"). Watching a charge is
  harvest-powered (costs the store nothing); on store-only reserve a full bar adds
  ≤12 mA and sheds itself as the store drains — worst-case held-TEST ~4.5 →
  ~3.5–4 min, session count untouched. Bottom step rides the LM339 common-mode
  limit at deep-sag rails (<~2.8 V) — by then the bar honestly reads near-empty
  anyway; exact scaling binds at capture with the window ladder. Parts: +1 LM339
  (U7, $0.09) + 2R/2Y/2G LED + 6× 1k + jellybean string ≈ **$0.35**.

## 5. AUX adapter port — DESCOPED (owner ruling, 2026-07-25)

REMOVED from the box. The port + 3 AUX fused ways + continuity way + the adapter
accessory SKUs are out: the owner sustained the scope objection — checking OTHER
cables (SATA/Molex/PCIe/EPS, incl. the borrowed-modular-cable pinout case) is a DMM
job or the metrology deck's (the deck already owns per-cable checking by ruling,
testers/DESIGN-SHEET.md §A), and a port-per-cable completeness argument proves too
much — the original 24-pin-only scope ruling stands. The agent's earlier
"safety-necessity" framing of this port is RETRACTED on the record (it was an
accessory/revenue feature; the VE pass's declined "AUX DNP" is superseded with it).
Bought back: 3 ways' worth of blade holders/blades/HRCs/MOVs/witnesses/windows + the
2×5 header ≈ **−$3.5–4 BOM**, a simpler panel, brick shrinks 2×11 → 2×8, 6
comparator sections freed (LM339 back to 6 packages, 4 spare). Kept: the meter
selector's 6th position now reads the SUPERCAP STORE instead of AUX. If a standalone
cable-pinout checker is ever wanted, it is its own tiny product, not this box.
Re-adding ways later is a generator parameter (the way cell is a stamp), so this is
cheap to reverse.

## 6. BOM — sourced (LCSC-primary pass, jlcsearch-verified 2026-07-25)

`bom/bom.csv` is the box rollup (54 lines, margin passives/decouplers included per
active device); `brick/bom/` and `snout/bom/` carry the sub-board BOMs. Verified LCSC
anchor lines: LM339DR **C7948** ($0.09, 84k) · TLV431AIDBZR **C56765** · 5×20 holders
**C3131** ($0.06, 133k) · Littelfuse 215 HRCs **C142716** (2 A-T ways) / **C142733** (10 A-T smoke branch) · ATO holders Bussmann
**C3207132** (watch: 997) · MOV 14D220K **C6793760** (watch: 800; 3 same-family alts
listed) · GDT 2R090TA-5 **C48642402** (glass-body check at sample) · KNP 1 Ω witness
**C1741442** · latching relay HF3F-L/5 **C190594** (watch: 749) · SMAZ5V6 **C110526** ·
301k-1206 **C873534** · 470k-2010 **C2960931** · LEDs **C2895476/C2895470/C2895472** (grn/red/yel) · SS8050
**C2150** · M7 **C95872** · 5.1k **C23186** · 1k **C21190** · bleeders **C349125**
(watch: 124) / **C1527341** — plus platform-verified reuse: PESD **C5261083**, SS34
**C8678**, USB-C **C2765186**, 100nF **C1525**. Jellybean R/C marked "JLC basic — bind
at capture." CONSIGNED SET (no honest LCSC line): NE-2 neons, flicker-flame tube, 85C1
meter, missile toggle + panel switches, supercaps (study-gate 2026-07-15), Mini-Fit Jr
24-ckt, case, 1 A ATO fuse bulk (hardware-store on purpose), boost coupled inductor
(Phase A pick). Datasheets vendored to `lib/datasheets/`: LM339, TLV431A, SMAZ series
(Littelfuse 215/297 + Hongfa fetch-blocked 403/404 — FOLLOWUPS).

**VE pass (owner ask, 2026-07-25) — applied without sacrificing anything load-bearing:**
VE-1 GDTs on the 5 CORE ways only (AUX ways kept MOV+fuse coordination — the pre-#14
signed-safe architecture; those ways since DESCOPED entirely 2026-07-25, §5;
−$1.70 across installed + spare brick). VE-2 supercaps 5 F→2 F
Pro-provision cells (−$1.00; ~6 sessions/charge — ~5 after the 2026-07-25 instant-on
OR raised the store floor to 2.8 V; recharge-to-usable ~30 s). VE-3
redundant NE_BF option deleted (−$0.15). Plus one CORRECTION the audit surfaced: LM339
count was under-provisioned (16 sections vs 21 needed) → 6 packages (+$0.25). Net
≈ −$2.60. DECLINED as false economies (each examined): meter (perceived-value king),
flicker tube (#14 soul), 3-resistor divider strings (surge margin IS the product),
10 W bleeder→5 W (61% dissipation vs the ~50% derate doctrine), HRC class, kit spare
brick, AUX subsystem DNP — since SUPERSEDED: owner descoped AUX entirely 2026-07-25, §5. OPEN
LEVERS, not BOM edits: generic ATO clip pairs (−$2.0–2.4 — NO LCSC line exists, 3
searches; consigned hunt rides the sample order, Bussmann stands until proven),
missile-toggle generic+cover (−$1.00, brand call — owner's), case engineering at quote
(−$2–3: faceplate-as-structural-top, printed lid insert — folded into the case RFQ).

**Landed rollup at verified prices, post-VE + AUX descope: ≈$39–41 @100 with the
starter kit** (descope −$3.5–4: three ways of holders/fuses/clamps/windows + the 2×5
header; recount at capture); ~$31–33 path @1k after the case quote. **Retail $79 (RULED #9)** —
2.1× at 100-qty worst, healthy at 1k. Consumables (RULED #12): Fuse+Flag $9 · brick
2-pack $12–15 · snout $9 · smoke-pellet 50-bag ~$3 (AUX adapter SKUs descoped, §5).

## 7. Mechanical / panel

Front panel is itself an FR4 PCB used as a FACEPLATE ONLY — **zero copper in the
fault path** (refined 2026-07-24): the ATO holders, lamps, and switches mount on the
MAIN board and protrude through faceplate apertures, so way current never crosses a
panel interconnect and the faceplate needs no connector at all. Its job is mechanical
+ graphic: silk = coroner's map + truth table + QR to the reorder page. Fuse-row pitch standardized so future
variants share the panel tooling. Lid molds the starter kit (blade set, HRCs,
spare brick, verdict pad). Creepage: 300 V-working class (≥3.2 mm) on all way copper
and the brick; the brick connector keying prevents reversed insertion. No mounting
of anything conductive reachable from outside; fuse door interlock per §4.

## 8. Capture plan (next phase, ST-tester pattern)

**Folder/inheritance structure (owner Q, 2026-07-25):** each physical PCB gets its
OWN folder and, at Phase B, its own KiCad project — `./` (main), `brick/`, `snout/`,
`faceplate/` — because KiCad is one-project-per-board; there is no literal schematic
inheritance across projects. The SHARED layer is (a) the generator
(`gen_smoke_tester.py`, Phase B) emitting all four from one source — the way cell is
8 stamps of one pattern, the brick is its mirror — and (b) the platform lib via
`${KIPRJMOD}` depth-3 paths (`beta/output-daughterboards/*` precedent). All four
panelize into ONE fab order.

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
- [ ] Supercap cell sourcing: LCSC carries NO supercaps (owner-verified gate, supercap
      study 2026-07-15) — consigned/DigiKey-class line, same cells as the Pro/Max 2S
      provision (shared buy).
- [ ] Arc-coordination bench protocol draft (gates DRAFT-drop; safety review for the
      witness chamber rides it — concept decision #4 — now incl. SMOKE-SHOT demo
      cadence: vent sizing, shots-per-minute silk). Rows now also incl. worst-case DC
      ingress (~400 VDC PFC-bus through representative fault impedance, no
      zero-crossings — proves HRC/GDT breaking beyond the AC rating; §3 both-grids
      note) + the witness-first disconnection sequence (clamp leg opens before any
      blade/HRC carries the DC event; repeat with MIN LOAD engaged = the bounded
      worst case).
- [~] AUX adapter pin-map table — OBSOLETE (AUX descoped 2026-07-25, §5).
- [ ] Compliance posture ruling (concept decision #8) before any listing goes live.
- [ ] Panel truth-table copy + verdict-card layout (marketing-adjacent, owner voice).
