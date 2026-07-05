# 24-pin ATX output daughterboard — BETA-1

Passive connector-daughterboard for the 24-pin ATX module's OUTPUT side, per
spec **§2.8 v1.4.0** (`CEC-Platform-Ground-Truth-Spec.md`) and the owner
ruling `docs/standard-tier-review/SYNTHESIS-beta-plan.md` §D-5a. Mates with
the main board's `TB1`–`TB9` Keystone 3586 universal blade clips (TB symbols
exist in `modules/atx-24pin-rev3`'s **schematic**, commit `b76a62a`; **no
clip placement exists on any main-board PCB yet** — this board's tab grid is
the authoritative mating drawing, see "Keying") and reproduces the full
24-circuit ATX output pin map for a bare pigtail or a future MODDIY-class
vertical header. **No active or passive components** — connector bodies and
fan-out copper only, per the ratified "no components beyond the connector
body and its fan-out copper" text.

DRAFT (no fab yet — the OQ-86 physical fit-check sample gate is still open).

## Posture — vertical card, tabs blade-DOWN (owner sketch, 2026-07-05)

This board is a small vertical card standing perpendicular to the main board
(owner ruling 2026-07-04/05, unchanged). The connector form went through
three same-day iterations on 2026-07-05 and is settled by the **owner's
sketch** (the final ruling; the two earlier forms — TE 63849-1
straight-tab/side-entry, then a mis-modeled "blade hangs past the edge
in-plane" reading of the 63951-1 — are retired, record in
`docs/standard-tier-review/blade-fit-check-2026-07-04.md` addendum 3):

The tabs are **TE 63951-1** (RIGHT-ANGLE FASTON .250 — "the blade that has
the 90 degree rotation in it," owner). The part is a flat in-plane **L
stamping**: the blade runs along the leg-pitch axis past the blade-side leg,
standing **2.54–8.89 mm off its seating face** (TE dwg C=63951 rev L2,
`lib/datasheets/TE_63951-1.pdf`). Mounted per the sketch: the two legs go
**horizontally** through this board's face, the 5.08 mm leg pitch runs
**vertically** (legs stacked one above the other), and the blade therefore
points **straight down**, descending past this board's bottom edge at the
2.54–8.89 mm Z-standoff — *"It needs to align vertically so it can actually
point down and slot into the clip."* The whole assembly drops vertically;
each blade enters its main-board Keystone 3586 clip's **top-entry** jaws
broadside (the clip's native auto-blade-fuse mode, Keystone dwg 3586). The
board's own bottom edge **floats clear of the main board** — *"the TAB does
the reaching down, not the board"* — no board material or copper crosses
Edge.Cuts; only the tab's off-board descender passes below the edge level,
offset from the board plane with no conflict.

**Board axes** (unchanged): X = length (FREE dimension, minimized
opportunistically); Y = height (**ruled cap ≤15 mm "or so"**, owner).

**Measured final size**: **145.1 × 13.6 mm** (length × height). Height
DROPPED 16.6 → 13.6 mm (now inside the ≤15 cap proper) because the tab row
no longer stacks below the field — it sits BESIDE the field/header sharing
the same Y band, its descenders leaving through the bottom edge at no height
cost. Length roughly doubled (81 → 145 mm) as the direct trade: the 9-tab
row at the ratified 8.9 mm pitch now adds ~74 mm of X beside the ~50 mm
field instead of underneath it — the sanctioned direction under the standing
"never at the expense of Y" axis rule.

## Mating geometry / seating model (replaces both prior seating analyses)

All numbers from `scripts/gen-output-daughterboard.py seating_report()` and
the two vendored drawings; the leg-row height is **uniform across all three
families** (one seating spec platform-wide, asserted by the check script):

- **Leg row** (leg-pair midpoint): 5.22 mm below the board's top edge =
  **8.38 mm above this board's bottom edge** (H 13.6). Lower leg pad keeps
  a measured 4.19 mm of copper-to-edge margin.
- **Blade standoff**: the descender hangs 2.54–8.89 mm off this board's
  front face; the main-board **clip slot centreline sits 5.72 mm** from the
  daughterboard's front face plane, slot axis PERPENDICULAR to the wall
  line. Blade width 6.35 mm (along the wall normal) vs. the clip's rated
  .110–.250 in (up to 6.4 mm) accepted-tab range — fits; slot opening
  1.57 mm vs. blade thickness 0.77–0.83 mm — ~2× clearance.
- **Descender reach**: blade tip 15.75 mm below the leg row (drawing-derived
  chain dim, flagged in the footprint descr) → the tip descends **7.37 mm
  below this board's bottom-edge level**, off-board at the Z-standoff.
- **Seating**: the board **cannot and does not edge-rest** — it floats,
  hanging on the clip grip (+ chassis strain relief, OQ-87). Seated with
  the recommended **1.0 mm tip clearance** above the main-board surface
  (hard stop ≈0.4–0.5 mm when the tip meets the clip's own SMT base metal),
  this board's bottom edge floats **8.4 mm** above the main board and its
  top edge sits **21.97 mm** above it (that total is identical for all three
  families by construction — it is pure tab geometry plus the shared
  top-margin band). **Engagement**: the blade spans the clip's full 7.16 mm
  interior from the tip clearance up (and protrudes above the clip top,
  fuse-like) — the jaw contact is covered wherever it sits in the body,
  the deepest engagement this part can give. Legs protrude 2.21 mm out the
  board's back face (3.81 mm legs − 1.6 mm board); keep that clear behind
  the wall.

## Mounting / retention — no mounting holes (owner directive, 2026-07-05)

Earlier drafts of this pass carried 4× M3 corner mounts; the owner cut them:
*"they don't need a ton of mounting holes either... that can probably go
away."* Retention is instead:
1. The Keystone 3586 clip's own **high insertion force** — a deliberate
   **feature**, not a shortfall, per the owner's 2026-07-04 ruling on this
   connector family: these joints are not meant for casual swapping, and
   mis-seat/pull-out (which hardware would be there to prevent) is exactly
   the failure a stiff joint rejects.
2. **Chassis strain relief** on the cable/assembly side (spec §2.8 v1.4.0);
   OQ-87 still owns the numeric pull-force/flex-cycle spec for that
   interface.
No footprint or BOM line changed because of this — mounts were never a
schematic/BOM part on this generator (PCB-only mechanical footprints), so
removing them only touched the PCB placement code.

## Tab map (9 joints, TE 63951-1 / LCSC C591344)

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
   is invented. On the standing-board posture the header's own pins point
   horizontally (same direction as the tabs), so — unlike an earlier,
   since-corrected concern about a parallel-mezzanine framing — there is no
   height-budget conflict with a vertical header option here; population
   stays an owner decision pending the physical fit check (OQ-86/88).
3. **Sellable daughterboard-plus-extension assembly** — same holes, wire
   soldered in with a chassis-anchored strain-relief bar, terminating in a
   standard female housing (OQ-89, SKU TBD). Wire dress runs parallel to the
   main board (the natural consequence of the field's pins exiting
   perpendicular to a *standing* board — i.e. horizontally).

## Keying

**Single row of 9 tabs at 8.9 mm pitch** (mm centre-to-centre), net order
unchanged from the original design (12V, 5V, 5V, 3.3V, 5VSB, GND×4) — see
the tab map above. Under the sketch model the pitch floor is no longer the
tab body at all (each tab is only ~0.84 mm thin along the row, stamping
plane perpendicular to the face; its 2.5 mm pads are its widest row-axis
feature → tab-to-tab pad gap 6.4 mm — trivially clear). The binding floor
is the **main-board clip row**: the Keystone 3586 rotated per the sketch
(slot axis perpendicular to the wall) presents its narrow dimension along
the row — 3.81 mm body / 3.82 mm courtyard (measured off the vendored
footprint; Keystone dwg 3586 `.150 in`) and a 6.60 mm SMD pad span. At
8.9 mm pitch: **5.08 mm clip-to-clip body gap, 2.30 mm pad-to-pad gap** —
asserted with printed numbers by `check_output_daughterboards.py` §3b.
Pitches were deliberately KEPT at the ratified 8.9/8.6/8.2 values (they
could shrink under the new floor, but that would re-open the keying-delta
derivation for no asked-for gain).

**The real safety property is proved, not assumed.**
`scripts/check_output_daughterboards.py` computes every family's tab-centre
list from its own `pcb_placement()` (the exact coordinates on the committed
board) and, for every ORDERED pair of families, searches all 4 rotations
(0/90/180/270°) × every candidate translation for a rigid mapping that seats
one family's whole tab set onto a subset of another's, within 0.5 mm
(bipartite exact-match, not a coincidence heuristic) — see that script for
the algorithm. All 6 ordered pairs come back "cannot seat" — re-proved on
the sketch-model coordinates, not carried over. An earlier pitch set
(8.6/8.3/8.2) PASSED the count/pitch checks but MEASURABLY FAILED this proof
(PCIe's 4 tabs seated within the 0.5 mm tolerance as a subset of EPS's
6-tab grid — a 0.1 mm/step difference over only 3 gaps accumulates to just
0.15 mm) — corrected by widening the per-family deltas until every pair
clears (G/2)×Δpitch > 0.5 mm at G = the smaller family's gap count; see
`scripts/gen-output-daughterboard.py`'s `TAB_PITCH` comment. **This
daughterboard's tab grid is the authoritative main-board mating drawing** —
the four main boards carry TB clip SYMBOLS in their schematics only (no PCB
placement exists on this branch), so the future main-board clip-placement
pass mirrors these exact X positions, the rotated-clip orientation, and the
5.72 mm slot-centreline standoff from the wall plane.

**Dual-face tabs**: evaluated and REJECTED under the earlier flat-tab model
(cross-face interleaving relieved only pad-to-pad clearance, ~11 %, not the
assumed ~50 % — full math retained in this section's git history). Under
the sketch model the question is moot a fortiori: the row pitch is
clip-limited and keying-limited, not tab-body-limited (each tab is ~0.84 mm
thin along the row), so a second face would buy nothing. Single-face,
single-row stands.

## Layer stack / routing

**4-layer** (F.Cu / In1.Cu / In2.Cu / B.Cu, 2 oz outer / 1 oz inner — the
platform's own interposer convention). GND floods **In1.Cu alone**, a
single full-board plane (the largest, most-scattered net; GND tabs and GND
field pins connect through it with zero explicit tracks). Of the remaining
7 nets, only **4 are real multi-point busses** — +12V, +5V, +3V3, +5VSB
(several field pins, one or two tabs each) — and only THOSE get a lane. The
other 3 (−12V, PWR_OK, PS_ON#) are a plain 2-terminal net apiece (exactly
one field pin to the matching `J20` header pin, no tab at all,
netlist-verified), so they route as direct point-to-point tracks with no
lane at all — see the two design notes below.

**The 4 BUS lanes live in a short CORRIDOR** below the field's bottom row,
on **In2.Cu only** — 4 thin zones (0.3 mm wide, 0.65 mm pitch) spanning the
full board width. Each bus field-pin runs a 0.5 mm F.Cu stub down to its
own lane + a 0.3/0.5 mm via (smaller than this platform's usual 0.5/0.9 mm
power via — the 0.65 mm slot pitch cannot safely hold a 0.9 mm via without
adjacent slots' vias overlapping). Each rail TAB — sitting BESIDE the field
in the shared top band, legs stacked vertically per the sketch model —
bridges its two leg pads (both numbered "1" but with no internal copper
between them in the footprint) with a vertical 0.5 mm F.Cu track, then
continues that track DOWN from the lower leg into its own lane + the same
0.3/0.5 mm via. The stub crosses the corridor's foreign lanes on F.Cu only
(different layer); its via sits at its own lane's centreline, clearing the
0.65 mm-pitch neighbours by the same measured 0.25 mm the field vias rely
on. The board's bottom margin below the corridor is sized off the DEEPEST
COPPER (via/track edges 0.25 mm past the last lane centreline + the 0.5 mm
board-setup copper-to-edge constraint), which is what the 13.6 mm height
lands on.

**DESIGN NOTE — a two-layer lane split does NOT help here, though it looks
like it should** (a first pass built one, then reverted it once DRC caught
the result). Splitting the 4 (or originally, all 7) lanes across In2.Cu
*and* B.Cu, thinking two layers halve the stack depth, is unsafe for a
zone this thin: a via is a THROUGH feature, so a B.Cu-target via also
crosses In2.Cu at that (x,y), and KiCad's `ZONE_FILLER` auto-clears
(anti-pads) it there — normally harmless (exactly how a signal via safely
crosses a GND plane everywhere on this platform) *only* because a plane is
wide in both directions and copper can route around the hole. A 0.3 mm-tall
lane has no "around": a via whose keepout diameter (~0.9 mm here) exceeds
the lane's own height clears its FULL height at that one X, severing it
into two islands — measured as a real `unconnected_items` DRC hit between
two ends of what should obviously be one zone. Offsetting the two layers'
Y by half a pitch does not fix it either: the safe stand-off a via needs
from a foreign-LAYER lane it merely passes near
(`via_keepout_radius + lane_half_height + min_width`, ≈0.8 mm here) is the
same separation the lanes already need from EACH OTHER on one layer — two
layers buy nothing once every slot carries a via. The actual fix was fewer
lanes (drop the 3 point-to-point signals out of the scheme entirely), not
more layers.

**The 3 point-to-point signals (−12V/PWR_OK/PS_ON#) route on B.Cu**,
deliberately NOT F.Cu: the bus field-pins' dodge-then-descend stubs (below)
are on F.Cu and physically transit this same row-gap band on their way to
the corridor, at up to 12 different X's, so putting the point-to-point
runs on the otherwise-empty B.Cu avoids that whole family of crossings in
one move. No via is needed at either end (both the field pins and the
header pins are through-hole). The three runs still share one layer with
each other, so each gets its own dedicated Y inside the field's row-gap
(0.42 mm steps, a 0.2 mm track — thinner than the platform-default 0.4 mm,
because the safe row-gap window is only ~1.1 mm wide once the 0.25 mm
GND-class clearance and each pad's own 1.85 mm half-height are accounted
for), assigned by which row each signal approaches from so no two runs'
occupied (X, Y) actually coincide — worked out and commented in
`route_atx24()`, `scripts/gen-output-daughterboard.py`.

**Row-conflict fan-out rule** (why some bus field-pin stubs jog sideways):
the real ATX-24 pinout puts row0 (pins 1–12) and row1 (pins 13–24) on the
*same* 12 X-columns, so a straight vertical stub from a row0 pin can run
directly into a *different-net* row1 pad below it. Fixed by a **permanent
+2.1 mm (half the 4.20 mm pitch) sideways offset** on exactly the row0 pins
whose column-mate differs — landing dead-centre in the gap between two
adjacent pad columns (~0.75 mm clear of both neighbours) — taken for the
pin's *entire* descent (never jogged back), which also keeps every column's
own stub on a unique X for its whole length. Row1 pins and same-net columns
route straight down natively.

Field-pin currents here are modest (24-pin design basis: 6 A/circuit, ATX
bar) — 0.5 mm 2 oz stub tracks are comfortably inside that per-pin figure;
the per-rail AGGREGATE current (up to ~30 A on the 5V rail, per the study's
§1 margin table) is what the **9 blade-clip joints on the main board** are
sized for, not this daughterboard's own individual per-pin fan-out traces.
Verified DRC-clean (see below).

## Electrothermal sanity — PENDING (W-item, not wired this pass)

The repo's `cec_synth_pipeline.physics.electrothermal_solve` (IPC-2221 Picard
solver) is not parametrized for this board's "per-pin stub + thin lane"
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

## Verification (this pass — 2026-07-05 sketch-geometry rework)

- ERC: 0 errors (5 benign `lib_symbol_mismatch` warnings, the same
  documented-benign class every generated schematic in this repo produces).
- Static connectivity audit (`scripts/audit-sch.py`): clean.
- DRC: **0 violations at error severity, 0 unconnected** (`kicad-cli pcb drc
  --severity-error`, and every `unconnected_items` slot is empty — the real
  gate `check_output_daughterboards.py` enforces). At full (all-severity)
  verbosity: 23 hits, ALL cosmetic silk (2 `silk_overlap` +
  21 `silk_over_copper` — the documented-benign class every generated board
  here carries; the earlier revisions' `silk_edge_clearance` category is
  GONE, since the sketch-model footprint keeps its silk between the leg pads
  and nothing overhangs the edge but the off-board descender's fab art).
  A first regeneration of this geometry DID fail with 4 real
  `copper_edge_clearance` errors (deepest lane's stubs/vias 0.30 mm from the
  new, tighter bottom edge vs the 0.5 mm board constraint) — fixed by
  deriving the bottom margin from the deepest copper, not the corridor
  outline; recorded here because it is exactly the class of thing a
  height-minimizing pass can silently break.
- `scripts/check_output_daughterboards.py`: **all checks pass**, including
  the NEW sketch-model checks (every tab rot 0 with legs stacked vertically
  at (0, ±2.54) re-parsed from the footprint file; uniform 5.22 mm leg-row
  height across families; clip-row body/pad gaps at each pitch) and the
  geometric no-subset-seating proof re-run on the new coordinates. Teeth
  re-verified: a deliberately sabotaged EPS pitch (8.3 mm) makes the proof
  correctly FAIL (PCIe seats as a subset), same as the historic failure.
- Netlist-verified: every one of the 9 tabs lands on its mapped ATX rail;
  every header pin lands on its mapped signal/GND/reserved net; the field's
  24 positions reproduce the standard ATX-24 map exactly (pin 20 = NC).
  Net-group identity vs. the pre-rework baseline confirmed (15→15 groups,
  0 missing/extra/renamed).

## Library assets used / added this pass

- **`cec-vendor:TE_63951-1_FASTON_Tab` / `cec-Connector_Blade:TE_63951-1_FASTON_Tab_250x032_RA_THT`
  (LCSC C591344, in stock, $0.099–$0.164/unit by qty)** — the right-angle
  .250 FASTON tab, footprint REWRITTEN this pass to the true in-plane-L
  geometry (legs at (0, ±2.54) stacked vertically, blade descending +Y past
  the board edge at the 2.54–8.89 mm standoff; thin projection-band
  courtyard/fab incl. the below-edge descender, drawn honestly) from TE's
  own customer drawing C=63951 rev L2 (`lib/datasheets/TE_63951-1.pdf`).
  The pass's first footprint modeled the L wrongly (blade perpendicular to
  the leg row, hanging past the edge in-plane) — retired by the owner's
  sketch; see `docs/standard-tier-review/blade-fit-check-2026-07-04.md`
  addendum 3.
- `cec-vendor:TE_63849-1_FASTON_Tab` / `cec-Connector_Blade:TE_63849-1_FASTON_Tab_250x032_THT`
  — pre-existing, LCSC C86469, **unreferenced by this generator** (left
  vendored; harmless).
- `cec:CEC_ATX_24` (pre-existing, reused verbatim for the field connector's electrical identity).
- `cec:CEC_CONN_2x5` + `cec-Connector_PinHeader_2.54mm:PinHeader_2x05_P2.54mm_Vertical` (pre-existing from the main-board task; this project's own library-asset pass independently reproduced byte-identical geometry).
- `cec-Connector_Generic:ATX24_Daughterboard_Field_P4.20mm` (this family's
  own field footprint; its Y-margin was tightened in an earlier pass —
  `scripts/gen-daughterboard-libassets.py`'s `solder_field()` now uses actual
  pad half-height instead of half the row pitch, dropping the field's own
  courtyard height 13.0→10.2 mm, the single biggest lever in fitting this
  board under the height cap — see that script for the reasoning).
  Unchanged this pass.
- No mounting-hole footprint — removed in an earlier pass (owner directive;
  see "Mounting / retention" above). Never a schematic/BOM part on this
  generator, so the BOM is unaffected.

Generator: `scripts/gen-output-daughterboard.py atx24-out-db`.
