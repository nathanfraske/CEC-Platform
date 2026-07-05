# 24-pin ATX output daughterboard — BETA-1

Passive connector-daughterboard for the 24-pin ATX module's OUTPUT side, per
spec **§2.8 v1.4.0** (`CEC-Platform-Ground-Truth-Spec.md`) and the owner
ruling `docs/standard-tier-review/SYNTHESIS-beta-plan.md` §D-5a. Mates with
the main board's `TB1`–`TB9` Keystone 3586 universal blade clips (already
built, `modules/atx-24pin-rev3`, commit `b76a62a`) and reproduces the full
24-circuit ATX output pin map for a bare pigtail or a future MODDIY-class
vertical header. **No active or passive components** — connector bodies and
fan-out copper only, per the ratified "no components beyond the connector
body and its fan-out copper" text.

DRAFT (no fab yet — the OQ-86 physical fit-check sample gate is still open).

## Tab map (9 joints, TE 63849-1 / LCSC C86469)

| Ref | Net | ATX pins bundled | Matches main-board clip |
|---|---|---|---|
| J10 | +12V | 10, 11 | TB1 |
| J11 | +5V | (shares +5V net with J12) | TB2 |
| J12 | +5V | 4, 6, 21, 22, 23 | TB3 |
| J13 | +3V3 | 1, 2, 12, 13 | TB4 |
| J14 | +5VSB | 9 | TB5 |
| J15–J18 | GND | 3, 5, 7, 15, 17, 18, 19, 24 | TB6–TB9 |

Joint count and per-rail split (12V×1, 5V×2, 3.3V×1, 5VSB×1, GND×4) are the
spec-ratified §2.8 v1.4.0 numbers, and the tab ORDER (12V, 5V, 5V, 3.3V,
5VSB, GND×4) matches the already-built main board's `TB1`–`TB9` net sequence
1:1 — verified against `modules/atx-24pin-rev3/README.md`.

## Signal header (J20, 2×5 2.54 mm, `cec:CEC_CONN_2x5`)

Pin order matches the main board's `J_SIG` (same commit) exactly, so a
mating cable/header is not left to guess a 1↔2 swap:

| Pin | Net | Note |
|---|---|---|
| 1 | PS_ON# | |
| 2 | PWR_OK | |
| 3 | −12V | |
| 4 | GND | local reference |
| 5–10 | reserved | no-connect; sense-return provision (OQ-88), unpopulated |

No 5VSB-sense/remote-sense net exists on the main board's signal set today
(verified against the current netlist per that board's own README), so none
is carried here either.

## Output field (J1, `cec-Connector_Generic:ATX24_Daughterboard_Field_P4.20mm`)

Bare THT solder field, 24 positions, 2×12 @ 4.20 mm pitch / 5.5 mm row —
geometry measured off the vendored, verified Molex Mini-Fit Jr 5569-24A1
land (`lib/vendor/Connector_Molex.pretty`), same pitch family the study's §4
recommends for exactly this field. Reuses the platform's own `cec:CEC_ATX_24`
symbol (same pin names/map as J3 on the 24-pin module) so the electrical
identity is inherited verbatim; only the footprint differs — a bare pad
field, no male-header shroud. 20 of the 24 positions are power-class (1.8 mm
drill / 2.7×3.7 mm oval, the real Molex land, 16 AWG-class); the 4 non-power
ATX circuits (pin 8 PWR_OK, pin 14 −12V, pin 16 PS_ON#, pin 20 NC/reserved)
are downsized to 1.4 mm drill / 2.6 mm round (18 AWG-class, matching the TE
tab's own leg size).

**Population options** (same field serves all three, per the study §4 "one
field, two/three uses"):
1. **Bare pigtail** (default) — hand-solder 16 AWG (power) / 18 AWG (signal)
   wire directly into the field.
2. **MODDIY-class vertical female header** — dimensionally compatible
   (4.20 mm pitch, same "Molex 5557/5559 family" pitch the part claims), but
   **NOT placed here**: no MODDIY footprint is vendored in this library (no
   manufacturer name / MPN / datasheet — OQ-88's provenance gap), so nothing
   is invented. If the owner's physical sample proves the fit, populate by
   hand onto this same field; it is not a distinct PCB variant.
3. **Sellable daughterboard-plus-extension assembly** — same holes, wire
   soldered in with a chassis-anchored strain-relief bar, terminating in a
   standard female housing (OQ-89, SKU TBD).

## Keying

Blade tabs are grouped by rail with a **wider gap between rail groups
(15 mm) than within a group (9 mm)** and an **asymmetric group-size pattern
(1, 2, 1, 1, 4)** reading across the row — non-uniform and non-palindromic,
so a same-pitch subset from another family cannot align contact-for-contact.
Joint **count** (9) also differs from EPS (6) and PCIe (4). True keying
against a wrong-family mis-seat is a **joint property of both boards'** hole
patterns; this daughterboard's own asymmetric pattern is documented here so
the (separate, not-yet-built) main-board PCB layout can mirror it exactly.

## Layer stack / current

**4-layer** (F.Cu / In1.Cu / In2.Cu / B.Cu, 2 oz outer / 1 oz inner — the
platform's own interposer convention), chosen over 2-layer because this
board carries **8 electrically distinct nets** (5 power rails + 3 low-current
signals) whose physical positions interleave column-by-column on the real
ATX-24 pinout (verified: 7 of 12 columns have a different net top-row vs
bottom-row). A 2-layer board would force every rail to share both layers'
"vertical corridor" real estate with the others, so **GND floods In1.Cu as a
single full-board plane** (the largest, most-scattered net — 8 physical pins
— gets a free ride), and the remaining 7 rails each get their own
**non-overlapping horizontal band** on In2.Cu, fed by individual F.Cu stub
tracks (0.5 mm rail stubs / 0.4 mm signal-header stubs) + a via per pin.
Field-pin currents here are modest (24-pin design basis: 6 A/circuit, ATX
bar) — 0.5 mm 2 oz stub tracks and 0.9/0.5 mm vias are comfortably inside
that per-pin figure; the per-rail AGGREGATE current (up to ~30 A on the 5V
rail, per the study's §1 margin table) is what the **9 blade-clip joints on
the main board** are sized for, not this daughterboard's own individual
per-pin fan-out traces.

**Row-conflict fan-out rule** (why some field-pin stubs jog sideways): the
real ATX-24 pinout puts row-1 (pins 1–12) and row-2 (pins 13–24) on the
*same* 12 X-columns, so a straight vertical stub from a row-1 pin can run
directly into a *different-net* row-2 pad below it. Fixed by a **permanent
+2.1 mm (half the 4.20 mm pitch) sideways offset** on exactly the row-1 pins
whose column-mate differs — landing dead-centre in the gap between two
adjacent pad columns (~0.75 mm clear of both neighbours) — taken for the
pin's *entire* descent (never jogged back), which also keeps every column's
own stub on a unique X for its whole length. Row-2 pins and same-net columns
route straight down natively. Verified DRC-clean (see below).

## Electrothermal sanity — PENDING (W-item, not wired this pass)

The repo's `cec_synth_pipeline.physics.electrothermal_solve` (IPC-2221 Picard
solver) is not parametrized for this board's "per-pin stub + banded plane"
topology; wiring it up is not cheap within this pass's scope. Hand sanity
only: 0.5 mm/2 oz external-layer traces at a 10 °C rise carry roughly 2–3 A
by the standard IPC-2221 external-trace curve — comfortably above the
~6 A/circuit-shared, sub-amp-per-stub currents these individual field-pin
fan-out traces actually see (the real per-rail current rides the 9 blade
joints, sized separately per the study). Flagged as a **pending W-item**:
run the real solver once it is generalized to this topology, before treating
this board as production-ready.

## Sense-return provision

Per spec §2.8 v1.4.0 / OQ-88: a zero-component sense-return contact (a
downstream voltage tap per sensed rail, feeding a main-board resistor divider
and spare ADC — mirrors Hub Standard's `MAIN_5V_SENSE`/`5VSB_SENSE` pattern)
is a candidate designed-in monitor for this joint's fretting-corrosion
wear-out mode. **Not decided** whether it ships, when, or at what
granularity — this board **provisions** for it only: 6 of the J20 header's
10 positions are reserved/no-connect, physically available for a future
sense-return tap without a board respin. No components are added here.

## Verification (this pass)

- ERC: 0 errors (5 benign `lib_symbol_mismatch` warnings, the same
  documented-benign class every generated schematic in this repo produces).
- Static connectivity audit (`scripts/audit-sch.py`): clean.
- DRC: **0 violations at any severity** (fully clean, not just error-gated).
- Netlist-verified: every one of the 9 tabs lands on its mapped ATX rail;
  every header pin lands on its mapped signal/GND/reserved net; the field's
  24 positions reproduce the standard ATX-24 map exactly (pin 20 = NC).

## Library assets used / added this pass

- `cec-vendor:TE_63849-1_FASTON_Tab` / `cec-Connector_Blade:TE_63849-1_FASTON_Tab_250x032_THT` (pre-existing, LCSC C86469).
- `cec:CEC_ATX_24` (pre-existing, reused verbatim for the field connector's electrical identity).
- `cec:CEC_CONN_2x5` + `cec-Connector_PinHeader_2.54mm:PinHeader_2x05_P2.54mm_Vertical` (pre-existing from the main-board task; this project's own library-asset pass independently reproduced byte-identical geometry).
- `cec-Connector_Generic:ATX24_Daughterboard_Field_P4.20mm` (new this pass, `scripts/gen-daughterboard-libassets.py`).
- `cec-MountingHole:MountingHole_3.2mm_M3_Pad_Via` (pre-existing) — 4 corners, GND-tied.

Generator: `scripts/gen-output-daughterboard.py atx24-out-db`.
