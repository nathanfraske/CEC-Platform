# Joint terminal range and launch-aware placement — 2026-09-19

## Generic implementation

The rigid-cell proposal solver previously considered terminal distance and
crossing order, but ignored measured wrong-direction Kelvin launches. A device
could be inside the permitted radius yet sit behind a shunt's inward face.
Repairing one input independently could also spoil its mate.

`cec_terminal_range` now intersects all supplied reach discs with directional
translation halfplanes. Both analytic boundary witnesses and native courtyard
cavity sampling use the same intersection before truncating the proposal menu.
The complete device/bypass cell rotates and translates together; source shunts,
power polygons, dimensions, clearances and budgets remain fixed.

The native adapter binds measured source, target, pin, net, launch point, normal
and signed distance to the actual loaded pads and poses. It derives the mate's
approach from the same two-terminal source, even if only one input was refused.
Stale or malformed certificates do not authorize a move. Out-of-range generator
receipts now retain launch geometry too, through the existing preflight evidence
projection. Within-range wrong-launch refusals therefore enter the same joint
repair path instead of disappearing from this proposal family.

This is **forward canonical-access proposal space**, not a global prohibition on
a legal inward-first route that later doubles back, nor proof that an empty
finite domain is physically unroutable. Independent native departure, physical,
frozen-authority and complete routing gates remain unchanged. The small reusable
halfplane primitive is protected by the generic-engine audit. No board, refdes,
net-name or coordinate exception was added to production code.

## Tests and six-board replay

`build/terminal-approach-wide-tests-20260919.log`: **493 tests and two subtests
pass** in 28.58 seconds. The 268-test focused run is overlapping coverage, not
an additional total. New coverage includes bounded disc/line intersections,
empty and malformed domains, obstacle-aware sampling, arbitrary rotations,
loaded/saved front/back native footprints, rigid followers, both input obligations
and stale certificate refusal. Existing range-only behavior remains supported.

`build/terminal-approach-suite-20260919/report.json` replays all six hash-bound
current inputs concurrently, including the independent historical PCIe2 control:

- PCIe3: 48 joint proposals across six sense devices, versus 40 range-only
  proposals. 35 fail courtyard overlap, eight fail frozen-power independence,
  five pass the existing physical/craft gates. Four of these reduce the Kelvin
  constructor's refusal count from 11 to 10; the fifth does not improve it.
- Current PCIe2: no Kelvin proposals or added copper; existing five-open
  continuation remains unchanged.
- Hub: no applicable Kelvin proposals; its two bounded ground-return failures
  and regulator-input decoupling proximity failure remain.
- 12VHPWR: no Kelvin proposals or added copper; its unrelated USB escape and
  local-return work remains. This is not new qualification of filtered sensing.
- EPS/ATX: held before downstream work by the unchanged coupled-interface ECO.
- Historical PCIe2: source hash, board-regression result and every probe match
  the newer independent-departure baseline. Its already exposed sideways Kelvin
  branch remains a blocker; it was not waived or edited.

All six source/hierarchy identities remain unchanged. Core generic audit passes;
the inherited broader audit still reports **23 physical / 380 runtime issues**.

## Full priority compiler and independent native evidence

`build/terminal-approach-priority-20260919` contains four concurrent, bounded full
priority-compiler trials of the physically accepted improvements. All retain the
three pair constructors (USB, CAN, CAN_J1), clean generated heading geometry,
and ten Kelvin refusals. Each compiler run took about 16 seconds. These are
**partial routing trials, not accepted continuation or fabrication candidates**.

Authoritative independent proof is
`build/terminal-approach-native-proof-20260919/report.json`. It loads the saved
boards, compares all copper geometry, checks native departures and actual input
contact, measures pair physics, and saves fresh raw KiCad DRC plus connectivity.

| Measured private prefix | Previous | New trials |
|---|---:|---:|
| Kelvin input pads reached by valid native departures | 1 | 2 |
| Kelvin constructor refusals | 11 | 10 |
| Open connections on the partial board | 243 | 242 |
| Counted DRC | 2 | 2 |
| Copper objects | 87 | 89 |

The two counted DRCs are unchanged dangling return vias. All previous pair
geometry is preserved. A relocated cell's old three-segment Kelvin branch is
regenerated into five segments reaching both of its inputs; therefore **not all
old private Kelvin geometry is retained**. The canonical source had no such
private prefix, and no canonical copper was removed. Original frozen power
polygon equality, original-state independence and exact authority checks pass.

The new native departures are inward and have no heading issues, but ten other
input connections remain absent. All three differential paths still lack their
required filled adjacent-ground reference coverage. Those independent failures
prevent promotion; adding one connection is not board closure.

Evidence correction: the priority harness's `prior_prefix_preserved` and
`prior_pairs_preserved` fields came from **locked-only checks that were N/A** on
the unlocked private prefix. They are not all-copper proof. Use the independent
native-proof report above, which explicitly records the changed Kelvin geometry
and preserved pair geometry. Earlier `terminal-approach-postflight*` output is
superseded: an output-path override initially was not forwarded to spawned
workers. The corrected final native-proof directory is self-contained and was
produced without rerouting or modifying any saved board.

## Continuation

Do not repeat these same 48 placements or four compiler trials unchanged. The
next placement problem is cooperative free-space recovery around the remaining
joint access cells, with fixed power authority and electrically owned followers.
Use the measured courtyard/power rejection split to select a changed search
domain, not individual reference-coordinate nudges. In parallel, advance the
Hub's recorded 125-pose local-return dependency and the Hub/VHP USB endpoint
geometry using genuinely new domains. No unchanged exhausted pair waves.

Keep `build/additive-first-next-inputs-20260917.json` canonical. All trial boards
remain private; no board/image was promoted. EPS/ATX still await the same paired
interface decision. No routing workers remain. About 64 GiB is free; these
bounded diagnostic outputs consume tens of MiB, not a new large campaign.
