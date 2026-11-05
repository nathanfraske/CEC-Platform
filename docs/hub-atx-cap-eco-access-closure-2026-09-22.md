# Hub / ATX capacitor ECO and planar-access closure

## Status

The CAD repair slice passes. **The complete physical stack is not qualified.**
Use the exact paired studies in `hub-atx-stack-placement-inputs-20260922.json`
for further placement work, with replacement placement/route-authority rebuild.
They are not routed winners and must not replace an archived fab candidate.
No supplier certification, order, hardware measurement or bench test occurred.

## Implemented

- Current hierarchical Hub C1+C37 now form the actual isolated 9400 uF nominal
  bank: 2 x Lelon VZH472M1CTR-1816 / C249940. Both BOMs and PCB pad nets agree.
  Pin 1 is positive on `/+5V_HOLD`, pin 2 GND. The new polarized symbol and
  manufacturer-based footprint replace the placeholder rectangles.
- Standard TR recommended lands use G=6, Y=8, X=3.2 mm: centers +/-7 mm,
  8 x 3.2 mm pads. This is **not** the alternate vibration-resistant V drawing.
  The conservative courtyard remains 23.2 x 20.2 mm. Maximum can height is
  17 mm, before the proposed 0.2 mm seating allocation. No new STEP is claimed.
- Both H1 lugs use the slim plated M2 land: 2.2 mm hole, 4.4 mm exposed ground
  ring and provisional 6 mm hardware envelope. Exact support/screws remain TBD.
- Hub envelope shrank from 84 x 80 to **84 x 72.2 mm** (9.75% smaller bounding
  area). ATX stays **82 x 95 mm**. A 9.4 mm wide, 6.5 mm deep recess with 0.5 mm
  inside radii exposes J_SIG1 without moving that daughterboard interface.
- The four RJ45 mouths remain native-left / assembly-right after reflection.
  Edge ports were repacked; native clearances pass. USB/KVM stay edge-facing.
  LED pattern, logo and debug-switch seats remain unchanged.
- J6P moved upward 1.2 mm on both boards, preserving every contact. ATX's USB
  ingress capacitor pair moves as one bounded cell, without moving output
  screw terminals or J_SIG1. ATX copper declarations are unchanged from the
  preceding mechanical study. Original retained boards remain hash-identical.

## Validation

| Check | Result |
| --- | --- |
| Native placement-geometry findings | ATX 0; Hub 0 |
| Same-number, same-role reflected contacts | 18/18 pass |
| Production assembly-datum/lug gate | Both pass |
| ATX input/output planar access | All 8 pass at required 1.2 mm |
| TB6 / TB9 minimum gap | 1.305 mm each |
| J_SIG1 recess minimum gap | 1.375 mm |
| ATX J3 input minimum gap | 1.405 mm |
| Live hierarchy: missing PCB refs / mismatched pad nets | 0 / 0 on both |
| Distinct local bypass assignments | ATX 25; Hub 14; none missing |
| Current six-main-board electrical audit | 0 blockers; 21 warnings retained |
| Focused regression tests | 99 pass, plus 7 subtests |
| Integration/generalization tests | 140 pass |

Native placement checking retains the existing explicitly classified LED-window
edge-clearance cases (24 Hub rows); zero here does **not** mean zero complete
routing DRC, zero opens, or final fabrication signoff. Local bypass assignment
is a distance/topology screen, not proof of the still-unrouted supply/return
copper. Source/receipt identities are recorded in:

- `build/hub-atx-access-compaction-20260922/pair-receipt.json`
- `build/hub-atx-access-compaction-20260922/validation.json`
- `build/hub-atx-access-compaction-20260922/search.json`
- `build/hub-atx-access-compaction-20260922/electrical-audit.json`
- `build/hub-atx-access-compaction-20260922/integration-tests.log`

## Electrical results, preserving the reviewed load decisions

The model keeps the existing 195.654 mA 3V3 load including 20% margin, 85%
conversion floor, 4.15 V reservoir starting bound, 3.45 V regulation floor and
10 ms persistence budget. Fresh minimum C is 7520 uF; the -20% initial and -30%
endurance envelopes combine multiplicatively to 5264 uF. Ideal hold-up is
26.334 ms fresh / **18.434 ms aged**, before ESR, leakage and software latency.
Existing dropout-detector topology and thresholds are unchanged: it senses the
selected 5VSB upstream of D1, not regulator dropout.

The old ~10 ms ramp note was incorrect for fitted CSS2/CSS3=2.2 uF. The
[TI TPS2121 Rev F table 9-1](https://www.ti.com/lit/ds/symlink/tps2121.pdf),
5 V entries, gives 88 V/s at 1 uF and 8.8 V/s at 10 uF. Inverse-C interpolation
gives about 40 V/s, or 125 ms to 5 V. At maximum reservoir capacitance that is
0.4512 A reservoir charging current alone. This is a **typical estimate**, not
a worst-case startup pass: source sharing, other capacitance/load, leakage,
CSS tolerance/DC bias and actual waveforms remain required. No soft-start value
was changed to manufacture more margin.

Capacitor dimensions/lands were visually checked in the
[official Lelon 2026 catalog](https://www.lelon.com.tw/upload/guides/2026%20Capacitor%20Catalog20260409094538.pdf),
printed pages 15 and 115. The spreadsheet workflow retained native CSV schemas;
column counts and the two BOM bank entries were checked, rather than converting
the project BOMs to another format.

## Reusable changes and regression limits

1. Bounded cooperative rigid-cell translations accept caller geometry and
   explicit domains, preserve local cells, and cannot grant admission. Invalid
   domains and exhausted budgets fail closed; search never exceeds its limit.
2. Rounded edge-recess geometry supports any orthogonal edge orientation and
   retains endpoints. Native outline/pad-edge and assembly access must recheck.
3. Reservoir-bank qualification checks actual population, BOM inclusion,
   capacitance, exact selection, footprint and polarity before counting energy.
4. Both mating placement and checking use an **explicit assembly datum**, not
   the mutable outline minimum. The compact outline exposed the remaining
   origin-coupling bug; synthetic and native tests now exercise shifted edges.

These helpers are on the generic-core selector audit list and pass that gate.
This is not a claim that every legacy module in the repository is generic.
Study refdes/group/seat choices remain board configuration, not shared solver
exceptions. The study is not an automatic whole-stack synthesis implementation.

The immutable PCIe2 final-fab-review-v103 control remains hash-identical,
with 0 DRC, 0 opens, 0 fabrication blockers and 0 route-craft issues. Full release
replay nevertheless fails today's inner-shunt-departure and CAN adjacent-ground
coverage checks (80% vs required 95%). Those checker modules were not changed in
this slice. Therefore the replay is **not** reported as an overall pass and the
control is not silently requalified or altered.

## Why complete stack qualification is still withheld

- Select and bound the exact conductive 22 mm M2 support/screws; qualify the
  6 mm head/washer envelope and local gap including seating/board bow.
- Obtain connector REF housing/capture limits, finished-hole tolerances, and
  qualify the three fields mating simultaneously. SSQ-03 long tails still need
  outward clearance or a coordinated short-tail selection.
- The prior **conditional** 21.5-22.5 mm local-gap study gives 4.3 mm minimum
  vent space and 3.894-5.900 mm insertion. Proposed seating/housing allocations
  are not supplier guarantees. Current VZH vent requirements, final opposing
  copper/mask and unobstructed discharge path remain open.
- Qualify actual opposing bodies, RJ45 model/revision, plugs/latches and tool
  access. Planar courtyard success cannot supply their missing Z dimensions.
- Complete OQ-56 cold/aged ESR, full-load startup, brownout and durable-commit
  bench tests; inspect an assembled first article.

`hub-atx-stack-qualification-status.json` intentionally remains
`PROTOTYPE_BLOCKED`, with no qualified release pair. Placement investigation can
continue under these explicit reservations; manufacturing cannot.

## Reproduction and review

The scoped drivers are `tmp/stack_eco_20260922.py`,
`tmp/stack_compact_probe_20260922.py`, `tmp/validate_stack_eco_pair_20260922.py`
and `tmp/publish_stack_study_20260922.py`. The shared primitives and active ECO
are in the repository's scripts, library and current BETA hierarchy/BOMs.
The hash-bound handoff prevents substituting an older schematic or preview.
Retain the entire generated study directory with the input manifest.

Both native no-body views are published to the dashboard as **UNROUTED STACK
ECO STUDY**, never as a routing wave or fab winner. Windows localhost:8090 and
the archive API were checked and both exact study IDs were present.
