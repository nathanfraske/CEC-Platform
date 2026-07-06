# PCIe 8-pin output daughterboard (per-cable) — BETA-1

Passive connector-daughterboard for **one** PCIe 8-pin cable's OUTPUT side,
per spec **§2.8 v1.4.0**. **One design, shared unmodified by both the
2-port and 3-port SKUs** (the same board is instantiated once per cable —
2 boards for `pcie-8pin-2port`, 3 for `pcie-8pin-3port`; no per-SKU
variant). Mates with the main board's per-cable `TB{n}1`–`TB{n}4` Keystone
3586 clips (TB symbols exist in `modules/pcie-8pin-2port` / `-3port`'s
**schematics**, commit `b76a62a`; **no clip placement exists on any
main-board PCB yet** — this board's tab grid is the authoritative mating
drawing, see "Keying"). No active or passive components.


> **ITERATION 7 (2026-07-06, owner-ratified) — READ FIRST, supersedes the
> iteration-5 numbers below where they differ.** Main-board mate changed:
> Keystone **3557 clip → TE 63969-1 FASTON .250 PCB RECEPTACLE** (vertical/
> top entry; the DESIGNED mate for the 63951-1 blade — rev-E dwg note 3
> puts our 0.81 mm thickness at its design centre, retiring the
> 27%-over-centre fit item; 22.9 A @ 30 °C rise per TE 108-1706; 63968-1 =
> same-land low-insertion-force fallback; LCSC C2961150, stock ~5 =
> restock watch, DigiKey depth). **ORIENTATION (owner requirement, proven
> from `lib/datasheets/TE_63969_customer_drawing_revE.pdf` and
> checker-asserted):** the receptacle's two Ø1.40 holes at 5.08 mm pitch
> run **perpendicular to the row**, along the descending blade's plane —
> plan-congruent with the blade's own leg holes; the blade's bottom edge
> enters the slot edge-wise. Along-row footprint is therefore only the
> receptacle's ~3.7 mm across-thickness depth (UN-DIMENSIONED on rev E —
> **depth ≤ 4.0 mm is the #1 sample-gate item; above it, atx24 falls back
> to a 6.3 pitch**): pitch floor 3.7 + 0.5 = **4.2 mm**; pitches now
> **atx24 4.2 / eps 4.7 / pcie 5.2**. Joint counts re-ratified at
> 22.9 A/125% (18.32 A allowable per joint): **atx24 10 tabs** (3V3 gains a
> second joint at 24.0 A basis; GND ×4 = 18.0 A/joint = 127% hairline,
> surfaced), **eps holds 6/cable** (17.33 A = 132%), **pcie 6/cable**
> (3/polarity; 2/polarity was 19.5 A = 117% FAIL). Boards: **atx24 61.0 ×
> 21.4, eps 28.5 × 20.0, pcie 31.0 × 20.0 mm** (pcie GROWS — the +2
> ratified joints outweigh its pitch win; honest number). Seating: float
> 12.41 mm unchanged; the 8.38 mm receptacle top is cleared by **4.03 mm**;
> detent-hole engagement at nominal float is NOT established (retention may
> be spring-friction only — sample item, with gang insertion force). Full
> record: `docs/standard-tier-review/blade-fit-check-2026-07-04.md`
> **addenda 6–7**.

> **ITERATION 5 (2026-07-05, owner) — READ FIRST, supersedes the iteration-4
> numbers below where they differ.** Main-board clip part changed: Keystone
> **3586 (SMD) → 3557 bare top-entry clip** (THT, UL 30 A @ 500 V AC; the
> "3557-2" this repo vendored earlier is the 2-in-1 HOUSED holder, a
> different product — naming corrected; 3586 stays vendored as the SMD
> fallback). Clip rotated slot-perpendicular-to-wall; its **leg pair runs
> ALONG the row** (verified from the catalog mounting details — this
> contradicts the leg-parallel-to-jaw assumption and caps the win): pitch
> floor = 3.4 leg pitch + 2.4 pad + 0.5 solder web = **6.3 mm**, pitches now
> **atx24 6.3 / eps 6.7 / pcie 7.2** (keying margins 1.00/0.75/1.35, teeth
> re-verified). Boards: **atx24 69.5 × 21.4, eps 38.5 × 20.0, pcie 26.6 ×
> 20.0 mm**. Seating: uniform 4.34 mm leg row, float 12.41 mm at 1.0 mm tip
> clearance; the taller 10.2 mm clip's top is cleared by 2.21 mm; engagement
> now spans the clip's full interior. atx24 also swaps its signal stub: the
> 2×5 header is RETIRED for a **1×4 right-angle blind-mate pin header**
> (long-tail Dupont class, pins down past the edge parallel to the blades,
> single-motion drop-in; NEW pin map 1=−12V, 2=PS_ON#, 3=PWR_OK, 4=GND) plus
> **six DNP sense-return pads SR1–SR6** (OQ-88 provision form only). #1
> fit-check item: the 0.81 mm FASTON tab is ~27% over the clip's 0.64 mm
> fuse-blade design centre (inside the published .020–.032 acceptance, at
> its ceiling — stiffer grip expected, sample-gated). Full record:
> `docs/standard-tier-review/blade-fit-check-2026-07-04.md` **addendum 5**.

DRAFT (no fab yet — OQ-86 fit-check sample gate open).

## Posture — vertical card, tabs blade-DOWN (owner sketch, 2026-07-05)

This board is a small vertical card standing perpendicular to the main
board (unchanged). The connector form is settled by the **owner's sketch**
(the third and final same-day 2026-07-05 form — the two earlier ones are
retired, record in `docs/standard-tier-review/blade-fit-check-2026-07-04.md`
addendum 3; full geometry description in `atx24-out-db/README.md`
"Posture", identical here): the 4 **TE 63951-1** right-angle FASTON .250
tabs mount with their two legs **horizontal** through this board's face,
leg pitch (5.08 mm) **vertical** (legs stacked one above the other), so
each in-plane-L blade points **straight down**, descending past this
board's bottom edge at a 2.54–8.89 mm Z-standoff from the face. The whole
board drops vertically; the blades enter the main-board Keystone 3586
clips' **top-entry** jaws broadside, and the board's own bottom edge
**floats clear** of the main board — the tab does the reaching, not the
board. Board axes: X = length (FREE); Y = height — **the ≤15 mm cap is
EXPLICITLY RELAXED by the owner for the iteration-4 compact two-band form**
(see the 24-pin README's "Board axes" for the verbatim follow-up).

**Measured final size**: **26.6 × 20.0 mm**. Iteration 4 stacks the packed
tab row BELOW the field band (owner: "stack the blades right next to each
other and put them below the pinout"), cutting length 49.4 → 26.3 mm at an
honest height cost of 11.0 → 20.0 mm. Height decomposition: 0.4 top margin
+ 10.2 field + 0.25 band gap + 4.82 tab top-extent (carrier stub) +
3.79 pad lower half + 0.55 edge margin. Length is tab-row-driven
(4 × 7.1 mm pitch + margins).

## Mating geometry / seating model (iteration-4 numbers)

Same uniform model as the other two boards (one seating spec platform-wide,
asserted by `check_output_daughterboards.py`; derivation in the 24-pin
README):

- **Leg row**: **4.34 mm above the bottom edge** (uniform across families —
  the tab band is the lowest thing on every board; lower pad clears the
  0.5 mm copper-to-edge constraint by 0.05 mm, checker-asserted).
- **Blade standoff**: 2.54–8.89 mm off the front face; main-board clip slot
  centreline at **5.72 mm** from the wall plane, slot axis perpendicular
  to the wall line.
- **Descender reach**: blade tip 15.75 mm below the leg row → **11.41 mm
  below this board's bottom-edge level** (off-board at the standoff).
- **Seating**: the board **floats** (cannot edge-rest) — at the recommended
  1.0 mm tip clearance above the main-board surface (hard stop ≈0.4–0.5 mm,
  tip on the clip's own base metal), the bottom edge floats **12.41 mm**
  above the main board (now UNIFORM across families); top edge at
  **32.4 mm** (24-pin: 33.8). Blade engagement spans the clip's full
  7.16 mm interior. Legs protrude 2.21 mm out the back face.

## Mounting / retention — no mounting holes (owner directive, 2026-07-05)

Same ruling and rationale as the 24-pin board: retention is the Keystone
clip's own high insertion force (a feature) plus chassis strain relief on
the cable/assembly side (OQ-87 owns the numeric spec). No BOM/schematic
impact — mounts were a PCB-only mechanical footprint on this generator.

## Tab map (4 joints/cable, TE 63951-1 / LCSC C591344)

| Ref | Net | PCIe8 pins bundled |
|---|---|---|
| J10, J11 | +12V | 1, 2, 3 |
| J12, J13 | GND | 4, 5, 6, 7, 8 |

2 contacts/polarity — the spec §2.8 v1.4.0 ratified PCIe joint count (8 on
the 2-port module, 12 on the 3-port). Design-basis current: ~13 A/pin
theoretical, only 3×12V pins → ~39 A/cable sustained worst case → ~49 A
margin target (§1 of the study).

## Output field (J1, `cec-Connector_Generic:PCIe8_Daughterboard_Field_P4.20mm`)

Bare THT solder field, 8 positions, 2×4 @ 4.20 mm pitch / 5.5 mm row (same
Molex Mini-Fit Jr 5569-08A2 grid as the EPS field). Standard **PCIe CEM
motherboard-side map**: pins 1–3 = +12V, pins 4–6 = GND, **pins 7–8 =
SENSE1/SENSE0** — per spec §2.8 v1.4.0's "2 sense tied... on the
daughterboard copper" text, these two positions are simply wired onto the
same GND net as pins 4–6 **in this board's own copper** (no dedicated blade
tab — negligible current, purely a presence-indication strap, exactly what
a real 8-pin PCIe cable does at the GPU end to advertise "full 8-pin
present"). Pins 1–6 are power-class (1.8 mm drill / 2.7×3.7 mm oval,
16 AWG); pins 7–8 are downsized 18 AWG-class (1.4 mm/2.6 mm — negligible
current, matching the TE tab leg size). Reuses the generic `cec:CEC_CONN_2x4`
symbol.

**Population options** — identical menu to the other two boards: (1) bare
16 AWG pigtail, power positions + 18 AWG for the two sense straps (default);
(2) MODDIY-class vertical header, dimensionally compatible, **not placed**
(no footprint vendored); (3) sellable daughterboard-plus-extension assembly.

## Keying

**Single row of 4 tabs at 7.1 mm pitch — AT the packed floor**
(iteration 4), net order +12V×2 then GND×2 — the smallest joint count of
the three families. The pitch floor is the **main-board clip row**, not
the tab (each tab is ~0.84 mm thin along the row; its 2.5 mm pads →
4.6 mm tab pad gap, trivially clear): the Keystone 3586 rotated
slot-perpendicular-to-wall presents 3.81 mm body / 3.82 mm courtyard and a
**6.60 mm SMD pad span** along the row — **floor = 6.60 + 0.50 stated
adjacent-clip solder/paste clearance = 7.10 mm**, and this board sits
exactly on it. At 7.1 mm: **3.28 mm clip body gap, 0.50 mm pad gap** (the
pad gap IS the stated solder clearance) — asserted with printed numbers by
`check_output_daughterboards.py` §3b.

**The real safety property is proved geometrically, not by pitch alone.**
`scripts/check_output_daughterboards.py` takes every family's tab-centre
list from `pcb_placement()` (the committed board's own coordinates) and,
for every ORDERED pair, searches all 4 rotations (0/90/180/270°) × every
candidate translation for a rigid whole-set mapping onto a subset of
another family's grid, within 0.5 mm (exact bipartite match). All 6 ordered
pairs come back "cannot seat" — **re-proved at the iteration-4 packed
pitches (8.4/7.6/7.1)**. This family (only 3 gaps) is the keying-critical
one: its (G/2)×Δpitch end error vs. EPS's 7.6 mm is 0.75 mm and vs. the
24-pin's 8.4 mm is 1.95 mm — both clear the 0.5 mm tolerance (1.5×+), so
pitch differentiation survives at the packed floor and no pattern keying
was needed. The historic failure mode (a 0.1 mm delta seating this
family's 4 tabs inside EPS's grid at 0.15 mm end error) stays live in the
checker's teeth: a sabotaged 7.2 mm EPS pitch was re-verified this pass to
make the proof correctly FAIL. **This daughterboard's tab grid is the
authoritative main-board mating drawing** for the PCIe per-cable clip
pattern (TB clip
symbols exist in the main boards' schematics only; the future
clip-placement pass mirrors these X positions, the rotated-clip
orientation, and the 5.72 mm slot-centreline standoff).

**Dual-face tabs**: evaluated and rejected under the earlier flat-tab model
(see the 24-pin README); moot a fortiori under the sketch model — the row
pitch is clip/keying-limited, not tab-body-limited. Single-face, single-row
stands.

## Layer stack / current

**4-layer** (F.Cu / In1.Cu / In2.Cu / B.Cu, 2 oz outer / 1 oz inner) — same
2-net topology and reasoning as the EPS board: **GND floods both inner
layers** (In1.Cu + In2.Cu), **+12V floods both outer layers** (F.Cu + B.Cu),
zero explicit tracks/vias needed (every pad here is through-hole, so the
real `ZONE_FILLER`'s automatic pad-clearance/pad-connection handles the
whole fan-out). The doubled-layer-pair current margin is the reason 2-layer
was not used, same as EPS.

## Electrothermal sanity — not needed as a solver run

Same reasoning as EPS: both nets are full-board floods on doubled layer
pairs, no thin fan-out geometry on this board to check. The governing
current question is the blade-clip joint (OQ-86), not this board's copper.

> **CORRECTION (2026-07-06, blade-interconnect thermal audit): the claim
> above is falsified — the solver run WAS needed.** No thin neck (correct),
> but at the 39 A worst-case basis the board dissipates ~1.18 W on ~11 cm²
> of still air: the 2.5D coupled solve gives **dT 116.8 °C** in the
> enclosed/no-sink posture vs the 30 °C-rise policy — a board-LEVEL
> dissipation red, not a neck. Unmodelled conduction sinks are large and
> the basis is worst-case (dT ~ I²), so this is a gate red pending the
> OQ-86 thermal-soak datum, not a fusing defect. See
> `docs/standard-tier-review/blade-interconnect-thermal-2026-07-06.md` (F2).

## Sense-return provision

Not provisioned (no signal header on this board). The SENSE0/SENSE1 straps
above are a presence indicator, not a monitoring tap — they carry no
information back to the main board's sensing chain.

## Verification (this pass — 2026-07-05 iteration-4 compact two-band layout)

- ERC: 0 errors (2 benign `lib_symbol_mismatch` warnings).
- Static connectivity audit: clean.
- DRC: **0 errors, 0 unconnected** (`kicad-cli pcb drc --severity-error`).
  At full verbosity: 15 hits, ALL cosmetic silk (4 `silk_overlap` +
  11 `silk_over_copper` — the documented-benign class; counts rose with
  the denser two-band stack, no copper impact).
- `scripts/check_output_daughterboards.py`: all checks pass, including the
  updated sketch-model checks (tab rot 0 / legs vertical / the NEW uniform
  4.34 mm leg-row-above-edge seating invariant / clip-row gaps recomputed
  at the packed pitches, this board sitting exactly at the 0.5 mm pad-gap
  floor) and the geometric no-subset-seating proof re-run at 8.4/7.6/7.1
  (teeth re-verified at the floor via a sabotaged 7.2 mm EPS pitch — see
  the 24-pin README).
- Netlist-verified: all 4 tabs land on their mapped rail; the field's 8
  positions reproduce the standard PCIe CEM motherboard-side map, with
  pins 7/8 confirmed tied to the GND net. Net-group identity vs. the
  pre-rework baseline confirmed (2→2 groups).

## Library assets used

- **`cec-vendor:TE_63951-1_FASTON_Tab` / `cec-Connector_Blade:TE_63951-1_FASTON_Tab_250x032_RA_THT`
  (LCSC C591344, in stock, $0.099–$0.164/unit by qty)** — right-angle .250
  FASTON tab, footprint REWRITTEN this pass to the true in-plane-L geometry
  (legs stacked vertically at (0, ±2.54), blade descending +Y at the
  2.54–8.89 mm standoff) from TE dwg C=63951 rev L2
  (`lib/datasheets/TE_63951-1.pdf`); see the blade-fit-check addendum 3 for
  the retired interim model.
- `cec-vendor:TE_63849-1_FASTON_Tab` / `cec-Connector_Blade:TE_63849-1_FASTON_Tab_250x032_THT`
  — pre-existing, LCSC C86469, unreferenced by this generator (left
  vendored; harmless).
- `cec:CEC_CONN_2x4` (pre-existing generic connector symbol).
- `cec-Connector_Generic:PCIe8_Daughterboard_Field_P4.20mm` — tightened its
  Y-margin in an earlier pass (pad half-height instead of half the row
  pitch, `scripts/gen-daughterboard-libassets.py`), dropping its own
  courtyard height 13.0→10.2 mm. Unchanged this pass.
- No mounting-hole footprint — removed in an earlier pass (owner directive;
  see "Mounting / retention" above). Never a schematic/BOM part on this
  generator, so the BOM is unaffected.

Generator: `scripts/gen-output-daughterboard.py pcie-out-db`.
