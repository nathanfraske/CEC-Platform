# Mezzanine mounting rework — structural connector segments (owner riff, 2026-07-22)

_Owner asks (2026-07-22): (a) "lower the mounts to M2s… place them in the 4 corners… 4 mirrored
on the 24-pin"; (b) "better idea… more compact stability that doesn't involve 4 massive screw
holes at inopportune or asymmetric ugly places?"; (c) "split the mezzanine into 2 or 3 segments
and have the stability derive from that — riff on that." This doc is the riff + the measured
facts + the recommendation. DRAFT — the mounting scheme is a mechanical/product ruling
(owner-queue row filed); nothing here edits the datum contract until ruled._

## Measured facts the options must live with

1. **All four 24-pin edges are owned.** Top = J3 (2×12 Mini-Fit, ~63 of 74mm). Bottom = the TB
   blade row. Left = the J1/J2 jack lands (present even when the stacked build DNPs them —
   holes/lands exist in copper). Right = the J6 mezz flank. Corners are therefore the WORST
   real estate on this board — TL=J3∩jacks, BL=TB∩jacks, BR=TB∩J6, TR=J3∩J6. This is why the
   2026-07-20 joint-legality probe produced the asymmetric 3-point datum the owner dislikes:
   symmetric corners aren't blocked by mount SIZE, they're blocked by the board's anatomy.
   **M2 vs M3 does not unlock corners** (it shaves ~1mm of keepout radius against multi-mm
   anchor bands). M2 is mechanically fine for this load class (hub ~50-60g; M2 standoffs carry
   far more) — the size answer is yes, the position answer is no.
2. **The mezz hardware is a measured placement-blocker on BOTH boards.** The 2026-07-22 prop
   wave's two headline proposals both refused pre-route on mezz hardware pairs:
   `prop-c1-anchor-periph-split` on **C1|H1** (the hold-up cap vs a datum STANDOFF) + D3|C1;
   `prop-kelvin-relax-adjacency` on **J6|U10** (the mezz field vs a sense IC) + the known
   FID3|J5. The chain forensic separately counted J6|D8/D9 as the hub's #1 courtyard collider
   (8 of 29). Deleting the standoffs and splitting/shrinking the J6 field dissolves the C1|H1
   and J6|U10 classes outright.
3. **The mezz right-flank block is part of the measured routing hardness** (2026-07-20
   attribution matrix: "tuck density + mezz right-flank + new rail geometry"). All 16 mezz nets
   funnel to one flank today; distributing them shortens runs on both boards.
4. **The real J6/J_MEZZ 16-pin map** (stack doc, netlist-verified): +5V_SYS ×3, GND ×7,
   CAN_H/L, STREAM_P/N, DETECT, RSVD. It splits cleanly by function.

## R1 — STRUCTURAL SEGMENTED MEZZ (the owner's idea, engineered; RECOMMENDED)

Split J6 into **three keyed THT 2.54mm segments** that ARE the mounting system (zero screws):

| Segment | Size | Nets | Shared-frame seat (start point) |
|---|---|---|---|
| J6P (power) | 2×3 | +5V_SYS ×3 alternated with GND ×3 | left flank (~the old BL region — near hub power entry / 24-pin 5VSB source) |
| J6C (comms) | 2×4 | GND-flanked CAN_H/L + GND-flanked STREAM_P/N | right flank upper (~old TR) |
| J6D (ID) | 2×2 | DETECT, RSVD, GND ×2 | right flank lower (~old BR) |

- **Stability**: the three mated pin fields form the same ~65×30 support triangle the screw
  datum proved, with wider effective feet (each segment's own 2-row base). Mated retention ≈
  18 contacts × ~0.7-1.5N (machined-pin sockets) = **13-27N pull-out** + insulator friction vs
  a ~0.6N board weight — >20× static, and a ~20g shock (~12N) stays inside. The weak axis is
  corner PEEL (lever ~2:1 across the span → a ~25N corner yank could start peeling the nearest
  segment) — see the bench gate below.
- **Keying for free**: three DIFFERENT sizes cannot be mis-assembled or rotated into a wrong
  seat (the same property the out-db tab keying proves per family).
- **Electrical win**: power lands by power, comms by comms — the 16-net right-flank funnel
  (measured hardness contributor) disperses; +5V_SYS×3/GND return loop shortens.
- **Placement win**: H1-H3 deleted (C1|H1 class gone), the 14mm J6 field replaced by three
  smaller fields (J6|U10 class eased/gone); the anneal gets three small anchors instead of
  one large + three keepout-ringed holes.
- **Cost/assembly**: 3 header+socket pairs ≈ $0.6-1.5/stack vs standoffs+6 screws ≈ $0.9-1.5 —
  a wash; stack assembly becomes a press, no screwdriver. Stack height unchanged (~11-13mm,
  same class as the standoffs), so the no-flip thermal posture is untouched.
- **XOR note**: stacked-build DNP of J1/J2 unchanged; segments live in the overlap zone under
  the same rule.
- **Bench gate (the one open risk)**: a peel/shake test on a mated 3-segment sample — pull-out
  per segment, corner-peel force, and a transport-vibe shake. If retention disappoints →
  drop to R2 (no board respin needed if the R2 hole is provisioned — see below).

## R2 — SEGMENTS + ONE M2 (conservative fallback)

Same three segments + **one M2 standoff** at the triangle's weakest vertex (the left flank,
where a peel lever is longest). One small (Ø2.2 drill / Ø4.3 pad) hole per board, placed in
measured-free space, DNP-able. **Provision this hole in R1's layout from day one** (a single
M2 land in legal space costs ~16mm² and makes the bench gate a population decision instead of
a respin).

## Complements / dismissed

- **Case ribs (complement, enclosed build)**: a foam-tipped rib over the hub's far corner in
  the beta enclosure adds shock margin with zero board features. Pairs with R1 naturally.
- **Case-datum alone (both boards on bosses, blind-mate)**: cleanest boards, but the bare
  stack (bench/kit handling, the OQ-77-adjacent mezz SKU outside its case) would be floppy —
  rejected as the primary scheme, folded into the rib complement.
- **Double-duty holes (datum = chassis mounts)**: keeps 3-4 holes; strictly worse than R1 on
  the owner's own criteria — kept only if R1+R2 both fail the bench.
- **Edge clips / PCB interlock tabs**: zero holes but bench-hack aesthetics, edge keepouts,
  FR4 weakening — dismissed.

## Implementation plan on a GO (wave-compatible, ~1 session)

1. Schematic: split J6/J_MEZZ into J6P/J6C/J6D on both `atx-24pin-rev3` and
   `hub-standard-rev2` per the table (this ABSORBS the owed no-flip pin-map re-verification —
   the per-segment map is defined fresh under bottom-mounted-socket convention, closing that
   FOLLOWUPS item). ERC + netlist teeth.
2. `MEZZ_HUB_24PIN`: `conn_dc` → a segment LIST `[{ref, dc, rot, size}]`; `mount_dc` → empty
   (R1) or one M2 point (R2 provision); `mating_frame_pins` generalized (it already returns an
   anchor_pins dict — extend to N conn refs). Joint-legality probe re-run for the three seats;
   the R2 hole placed from the probe's free map.
3. Wave: relaunch both boards' waves on the new contract; expect the C1|H1 and J6|U10 refusal
   classes to vanish from the ERR streams (the measurable success criterion).
4. Owner bench: the R1 peel/shake gate on the first mated sample (parts orderable same-day —
   generic 2.54 machined-pin strips).

## Appendix A — EXACT implementation contract (owner GO 2026-07-22; both boards IDENTICAL)

Symbols (in `lib/cec.kicad_sym`, pre-staged): `cec:CEC_CONN_2x3` (J6P), `cec:CEC_CONN_2x4`
(J6C), `cec:CEC_CONN_2x2` (J6D). Footprints (vendored from pinned KiCad-10 stock):
`cec-Connector_PinHeader_2.54mm:PinHeader_2x0{3,4,2}_P2.54mm_Vertical`.

Roles derive from the stack-doc 16-pin role table (pins 1,2,3 = the +5V role;
4,7,10,12,14,15,16 = GND; 5=CAN_H; 6=CAN_L; 8=STREAM_P; 9=STREAM_N; 11=DETECT;
13=RSVD). **Preserve each board's ACTUAL net names** (no renames). A role a board
does not carry (the Standard hub has no STREAM_P/N or RSVD nets) maps to an
explicitly-flagged no-connect pin — forward-compat pins ride as copper, unwired.

**SUPERSESSION RECORD (2026-07-22, surfaced by the hub splice agent's stop-rule):**
the hub-rev2 J6 had been remapped 2026-07-15 to a COLUMN-PAIRED 2×08 scheme
(wide-ganged +5VSB×4 / CAN pairs / DETECT1 pairs) whose sole premise was
FLIP-INVARIANT mating ("the 3×5V map is NOT flip-safe"), with a pending conjugate
rewire of the 24-pin (FOLLOWUPS 2026-07-15, now retired). The owner's 2026-07-19
NO-FLIP ruling killed that premise, and this contract defines the map fresh under
no-flip — the column-paired map and its pending conjugate contract are SUPERSEDED;
the doubled signal pins collapse to one per signal. Per-board role→net as built:
hub-standard-rev2: +5V→`+5VSB`, GND→`GND`, CAN→its CAN_H/CAN_L nets,
DETECT→`/DETECT1` (port-1 detect — the stacked 24-pin replaces the port-1 cable),
STREAM_P/N + RSVD→NC. atx-24pin-rev3: +5V→`/+5V_SYS_PORT`,
CAN→`/CAN_H_BUS`/`/CAN_L_BUS`, DETECT→`/DETECT`, STREAM_P/N + RSVD→unconnected
(as today). Mating joins ROLES, not names.

| New ref | Pin | Role | | New ref | Pin | Role |
|---|---|---|---|---|---|---|
| J6P (2×3) | 1 | +5V | | J6C (2×4) | 1 | GND |
| | 2 | GND | | | 2 | GND |
| | 3 | +5V | | | 3 | CAN_H |
| | 4 | GND | | | 4 | STREAM_P |
| | 5 | +5V | | | 5 | CAN_L |
| | 6 | GND | | | 6 | STREAM_N |
| J6D (2×2) | 1 | DETECT | | | 7 | GND |
| | 2 | GND | | | 8 | GND |
| | 3 | RSVD | | | 9-... | — |
| | 4 | GND | | | | |

(Column-pair physical layout: odd/even numbering = columns (1,2),(3,4),(5,6),(7,8) —
J6C row A reads GND,CAN_H,CAN_L,GND and row B reads GND,STREAM_P,STREAM_N,GND: each
diff pair adjacent along its row, GND at both ends.) Totals: 18 pins (+5V×3, GND×9 —
two more GND contacts than the 16-pin form, a retention/return bonus — plus the 6
signals). The old J6 instance is REMOVED (the CEC_MEZZANINE_16P symbol stays in the
lib, unreferenced, per repo precedent). BOM/DNP posture: the three new refs carry
EXACTLY the properties the old J6 carried (DNP/exclusion flags). Mate consistency is
by construction: both boards implement this same table, so mated pin N↔N carries the
same role.
