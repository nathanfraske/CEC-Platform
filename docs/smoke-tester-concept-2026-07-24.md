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

## 8. Owner decisions (numbered, decision-ready)

1. Ratify the family slot (`testers/smoke-tester/`) and the PROPOSED census row.
2. Terminator-only fence (recommended: YES — never inline).
3. Blade + hidden-HRC coordination vs blades-only (recommended: coordination; blades-only
   fails honest mains interruption).
4. Smoke-theater witness chamber: yes/no pending safety review (name survives either way).
5. Earth reference form: IEC inlet (earth-only) vs earth pigtail.
6. v1 connector scope: 24-pin only vs +EPS/PCIe ways (+$ per way; recommended 24-pin-only v1).
7. Pure-analog purity vs an optional isolated telemetry population (recommended: pure v1;
   the ST deck owns data).
8. Compliance posture: CAT-rated claim vs professional-tool disclaimer.
9. BOM/price target ratify ($18–25 landed / $39–59 retail class).
10. Bundle position: standalone SKU vs ST-bundle anchor item.
