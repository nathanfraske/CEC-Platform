# Inline flow placement and route-admission slice

## Authority

Continue the hierarchical current BETA 12VHPWR, 58 x 72 mm, six-layer
checkpoint documented in `grounded-mounts-and-pair-admission-2026-09-09.md`.
Input: `build/12vhpwr-grounded-mount-routing-20260909/final-preparation-v2/board.kicad_pcb`,
SHA-256 `bcc97e34166f558344c922d3ab206facf2e0236471680b085f8281dd505181e0`.
No schematic, BOM, power-bus geometry or board outline is changed by this slice.

Evidence root: `build/12vhpwr-pair-search-20260909`.

## Root causes and reusable changes

1. **Edge admission ran before equivalent-copper normalization.** CAN_INT
   connected one tree edge, then rejected a short trace wholly covered by its
   already-proved runway as a covered backtrack. Final tree cleanup would have
   removed that duplicate, but was unreachable. The production edge gate now
   removes only wholly covered tracks created by that edge attempt before
   checking the composed graph. Earlier edges, junctions and authored copper
   remain immutable; genuine acute bends still refuse and roll back. The
   native synthetic regression exercises both acceptance and refusal through
   the actual layered-tree entry point.

2. **A locally clear inline station was assumed to be a good placement.**
   The current USB connector is at the lower-right area, but the flow-through
   array remained near the top. Its two required external legs totalled
   64.710008 mm against 12.886082 mm between the terminal centres (5.021698x).
   The launch checker measured only the first 3 mm from each bank; the route
   repair neighbourhood deliberately treated inline stations as anchors.
   The shared launch evidence now also grades the chain's geometric excursion,
   using actual topology-derived banks, not reference names. The default
   ratio limit is 2, configurable through `flow_through_excursion_max_ratio`.
   Invalid geometry/policy fails closed. This is a routing-placement quality
   bound, **not ESD, timing, impedance or EMC qualification**.

3. **The repair neighbourhood could not bring a displaced inline part back.**
   A single front-side inline station now receives bounded, real-courtyard
   contact-site proposals in its terminal corridor, with four orthogonal bank
   orientations. When necessary, a named small passive conflict is submitted
   to the existing bounded local-group legalization step. No obstacle is
   waived at final admission. Local launch-blocker moves use that same group
   legalizer, instead of stopping after one neighbour swap. Endpoints and power
   are not relocated by the new proposal primitive. Fixed parts, multiple
   inline stations and unsupported back-side reseating remain fail-closed.

4. **Failure reports recursively duplicated their entire search tree.**
   A USB leg's reason formatted the complete nested layer evidence into a
   string, then repeated it inside the upstream refusal and logs. It now lists
   concise per-layer reasons. Full attempts remain once in the structured
   `flow_leg_refusal.layers` evidence; no failure detail is discarded.

These mechanisms contain no product, reference-designator or coordinate
special case. Experiment harnesses name artifacts, not engine exceptions.

## Bounded experiments, not promoted results

The baseline exact CAN_INT replay took 15.45 s and reproduced the edge-quality
refusal. Early normalization let its whole tree connect and pass 92% coupled
coverage, but the independent detour gate correctly rejected 2.15x/3.15x
member lengths against the existing 2x limit. No route was retained.

A compact-junction menu did not improve that result. A physical-terminal tree
only achieved 35% coupled coverage; a temporary excessive-detour deferral also
failed. None of these experimental routing policies was integrated or promoted.
The permanent change is the consistent normalization/admission order, not a
relaxed geometry, coupling or detour gate.

The first production placement replay (`placement.json`) accepted an inline
relocation with two capacitor-seat adjustments. It reduced the USB external
leg sum to 24.220861 mm (1.879614x, 62.6% shorter), but still refused placement
because a nearby resistor occupied one launch. The second bounded replay is
`placement2.json`; consult its gates and `closeout.json` for final status.
Neither a lower geometric span nor a passed synthetic test is routing admission.

## Completed checkpoint and remaining admission blockers

The second production replay completed in 419.38 s. It legalized the inline
launch by moving two nearby resistors as a bounded group. Five footprints moved
across the two passes: D3, C5, C24, R17 and R14. The MCU, connectors, power buses
and outline did not move. The production placement-craft gate now passes, with
the existing C7 local supply interconnect explicitly assigned to the pre-route
local-interconnect stage; it is not claimed electrically complete.

The exact priority-route gate still refuses three pairs:

| Pair | Final production refusal |
| --- | --- |
| CAN_INT | Whole tree connects in the isolated probe, but member detours are 2.15x and 3.15x against the 2x limit. |
| CAN | No valid layered paired junction for R22/R23 on F.Cu. |
| USB | First flow-through leg exhausts the coupled-route deadline. |

Reported unresolved critical tree edges fell from 5 to 4. That is diagnostic
search progress, **not one newly retained electrical connection**: the pair
attempts remain atomic and failed routes are rolled back. The native checkpoint
score remains **4 DRC / 228 opens / 415 tracks / 12 vias / 837.8186 mm**.
No full signal-routing wave was started through the failed priority gate.

Final checkpoint: `build/12vhpwr-pair-search-20260909/checkpoint/board.kicad_pcb`.
SHA-256: `3a0deb439290e8b7646b1b736e2947d5c1a711d0b3e4f17b7919c0c5b3da0e28`.
`closeout.json` verifies all 199 original protected power primitives, all nine
lands of each of four grounded M2 mounts touching both ground planes, and the
unchanged hashes of all 12 hierarchical schematic files and four authority
controls. A native before/after comparison also confirmed identical footprint
identities, values, layers, pad numbers/nets, sizes and drills (110 footprints,
six copper layers). Placement is changed; electrical identity is not.

The native, no-body preview is tied to that exact SHA under
`review-3a0deb439290/`; its banner explicitly says **NOT ROUTING-ADMITTED**.
The dashboard artifact endpoint returned HTTP 200 with `image/png`, and the
matching Windows copy was visually inspected. This is a direct artifact view,
not a newly promoted dashboard fab-candidate entry.

Next work should address bounded terminal-orientation/paired-junction search
and use the USB deadline/blockage evidence to improve its search scheduling.
Do not enlarge the board or alter protected power to bypass these refusals.
The USB array's lower excursion is not a substitute for connector-side ESD
placement qualification. Also still open: proposal generation spent about 43 s
enumerating many route-owned decoupler moves even when the actionable defect
was a pair launch. That stage-ownership inefficiency was observed, not repaired
in this slice.

## Regression evidence

- `build/pair-search-final-tests-20260909.log`: 411 tests passed, including
  2 subtests, across routing, placement principles, pair topology, mounting,
  fiducials, ownership, generalization, full-pipeline and rendering tests.
- `build/pair-search-craft-tests-20260909.log`: 332 passed in the additional
  placement-craft/flow/routing suite. Counts overlap; they must not be summed.
- `build/pair-search-final-craft-20260909.log`: 232 passed after final policy
  plumbing and proposal-domain safeguards.
- `build/pair-search-pcie-regression-20260909.json`: immutable PCIe control
  score and broader blocker list exactly equal the previous replay: 0 DRC,
  0 opens, 615 tracks, 226 vias, 1242.073 mm. The 8 existing broader release
  blockers remain; this is not new unconditional fabrication approval.
- `crossboard-locality.json`: actual native USB geometry yields ratios 5.021698
  on the input 12VHPWR, 1.002935 on the PCIe control and 0.959379 on the Hub.
  The two controls pass the added excursion check without edits. This is not
  a full route replay or qualification of the unfinished Hub.

The existing engine still contains legacy generalization findings. This slice
does not certify the entire historical pipeline as generalized or fab-ready.
