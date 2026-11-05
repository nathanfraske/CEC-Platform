# Current BETA 12VHPWR: right-facing lower I/O bank

2026-09-07. Owner corrected the previous bottom-facing RJ-45 experiment:
**RJ-45 faces right in the lower area; USB-C moves down alongside it.**
This is a placement review, not routing admission or fabrication release.
The earlier bottom-facing review is retained as history, not current intent.

## Reusable implementation

The board policy declares both interfaces on the right edge and selects
`edge_packing.right.alignment = "end"`. On a vertical edge, end means the
larger board-y end. The same rule supports start/center/end on all four edges;
there is no product, reference-designator or board-coordinate case in the
new `scripts/cec_edge_packing.py` engine.

The placer uses real rotated courtyard extents and pad-copper edge seating.
The finite interval solver subtracts mandatory mounting-hardware obstacles
and explicitly pinned components. It refuses impossible banks rather than
reducing hardware clearances or silently accepting an overlap.

Three concrete defects were exposed and repaired in this slice:

1. A historical force-lane preference always started right-edge ports at the
   top. Explicit edge-bank alignment now overrides that preference.
2. A later P2 clearance pass independently moved the RJ-45 against a
   provisional mid-board sensing row, undoing the bank before it was locked.
   Declared banks now retain upstream mechanical authority; movable cells must
   negotiate around them. Both lane and rail connector-tuck paths respect it.
3. The internally pinned fan header consumed an edge-bank slot before its
   explicit position was applied, creating a phantom inter-port gap. Pinned
   parts now obstruct the bank at their actual positions, not at unused seed
   seats. The two external connector courtyards retain the ordinary 2 mm gap.

Explicit pins and frozen-pour snapshots remain upstream authority. A connector
bank declaration is not permission to overwrite an existing frozen placement;
these trials use fresh placement from separately normalized source copies.

## Source and evidence

The manifest-selected hierarchical `beta/12vhpwr-standard/12vhpwr-standard-module.kicad_sch`
and its child sheets remain the source. No schematic, BOM or historical PCB
was changed in this slice. The fitted fan-header state, current USB circuitry,
direct LDO source and four mandatory M2 holes are retained.

Trials, each bounded to one seed and 80/76/72 mm height at 58 mm width:

- `build/12vhpwr-right-lower-io-20260907`: exposed the later RJ-45 re-seat.
- `build/12vhpwr-right-lower-io-owned-bank-20260907`: protected bank ownership,
  exposed the phantom slot left by the pinned fan header.
- `build/12vhpwr-right-lower-io-compact-bank-20260907`: corrected bank packing.

Each retains the exact PCB, source intake, candidate journal and native craft
evidence. The final run's `right-lower-io-review.json` and `closeout.json` compare
connector poses, hardware, local supply-pad distances, emitted power-track
widths/lengths and the prior retained 80/76 mm boards. Native renders contain
no 3D bodies and explicitly say **PLACEMENT ONLY**.

Shorter height moves the lower power interface with the outline and regenerates
power copper from the endpoints. No trace-width, copper-thickness, current,
thermal or fan-performance requirement was relaxed. A shorter visible bar is
not proof of a connected, thermally qualified power path.

## Final bounded results

| Size, mm | Placement residual | Pads/courtyards/mounts | Sensing cells / locked internals | Existing decoupling findings |
| --- | ---: | --- | --- | ---: |
| 58 x 80 | 0 | Pass | 6 / 444 | 11 |
| 58 x 76 | 5 | Pass | 6 / 444 | 12 |
| 58 x 72 | 20 | Fail | 4 / 296 | 12 |

Both ports face right and have a **2.0 mm courtyard gap**. Their end alignment
clears the bottom-right M2 hardware. The 80 mm board is the selected visual
review (`02-placement/candidates/002/board.kicad_pcb`); the smaller boards are
diagnostic trials, not admitted replacements.

The 76 mm trial is 5% less area. Power-terminal y separation decreases by 4 mm
(77.557 to 73.557 mm), and the emitted 2.5 mm-wide main-bar segments total
24 mm less length (393.552 to 369.552 mm). Main power widths are unchanged.
The full width inventory also contains a newly emitted 0.8 mm fan-branch
segment; do not claim every trace in these different placements is identical.

No option is electrically admitted. At 80 mm, C3 is 1.560 mm from U1.3, but
the explicitly owned C7 bulk capacitor remains 21.989 mm away. At 76 mm,
C3 is 44.769 mm away and C7 is 23.226 mm away. These C7 measurements expose
the known coverage gap and are additional to the automated counts above.
The 80 mm findings also include local ground-return/loop and sensing-cell
access failures. The 72 mm option additionally refuses two sensing-cell
stamps because of foreign-pad conflicts. No missing copper was forced through
those obstacles, and no failed trial was passed to detailed routing.

## Verification and remaining boundary

The focused regression suite passes **259 tests; 14 skipped**. Its 20 new
edge-packing tests include the real P2 overwrite path, pinned-component phantom
slots, all four edge orientations, impossible geometry, hardware obstacles and
read-only native-footprint replay on retained PCIe, Hub and 12VHPWR controls.
The skips are reported, not counted as passes. The entire repository suite was
not run.

Read-only PCIe fab-review replay preserves the measured score: 0 DRC violations,
0 opens, 615 tracks, 226 vias and 1242.073 mm length. Its eight existing release
blocker categories/details are unchanged; full generic-pipeline acceptance
remains false. This is regression evidence, not a new release approval.

The previous MCU macro-decomposition/local-bulk-ownership defect remains a
separate electrical-placement repair. The source's C3 and C7 ownership must be
honored physically; the review explicitly measures both, including C7 which
the existing selected-device matcher does not fully cover. Smaller candidates
must not be promoted merely because their courtyards and mounting holes fit.
No detailed routing or thermal solve was run on these placement-only trials.
