# Octilinear paired ribbons and supported-menu audit — 2026-09-15

## Completed three-board cohort

`build/cumulative-escape-suite-20260915/suite.json` finished at
2026-09-15T05:24:41Z. PCIe3: 238.569 s; Hub: 681.659 s;
12VHPWR: 1074.022 s. All outputs identical to their hash-bound inputs,
all source/hierarchy and engine checks unchanged, no newly admitted board.
Hub remains at 1/6 CAN tree edges in its two funded reconstruction trials.
VHP reproduces the fixed 3.876134-mm skew, then fails 33.3% coupling;
PCIe3's two power-handoff trials fail physical checks. These are failed
bounded searches, not proofs of infeasibility.

Final immutable body-free gallery:
`C:/Users/Admin/Documents/CEC-Board-Reviews/cumulative-escape-suite-20260915/all-boards-dda473d698d699b3.png`.
Reviews are BLOCKED placement snapshots, not routed or fabrication releases.

## Implemented generic proposal repair

The straight-axis ribbon generator joins arbitrary station centres, producing
arbitrary-angle middle runs and tapers. Later octilinearity checks correctly
reject these; independent per-member detours can then lose coupling.

`scripts/cec_pair_ribbon.py` adds an explicit correlated alternative: shared
nominal-pitch straight trunks on eight permitted headings, with constructive
45-degree fan-in at both ends. The runway inequalities consider both members
simultaneously. Station-normal launches, midpoint alternatives and polarity
are geometry-derived, not board/refdes/coordinate overrides. Candidate count
is capped at 128, with existing deadline checks; a bounded geometric frontier
precedes sampling against the existing coupling contract. Projected signed
whole-pair mismatch also participates in ranking. No coordinates are snapped
after native clearance checks and no copper is emitted by this module.

The precision-router caller uses this only after its legacy ribbon menu fails.
Already successful fast paths and disabled-detour behavior are preserved.
Exact foreign copper, pair spacing, heading, turn quality, layer, width,
coupling, prefix and final whole-board gates remain unchanged. Compact logs
now identify how many candidates of each ribbon geometry were evaluated.

This is a bounded straight-trunk domain, **not** arbitrary bent-corridor or
maze-based joint routing. Returning no proposal is not an infeasibility proof.

## Test results and limitations

`build/octilinear-pair-ribbon-integrated-tests-20260915.log`: **316 passed,
18 subtests**, one existing KiCad SWIG warning. Synthetic geometry covers
rotations, exchanged members, exact endpoints, octilinearity, minimum spacing,
crossings, turns, deterministic bounds/deadlines and nonfinite inputs.
Native synthetic routing succeeds where all legacy ribbons fail the angle
rule; a foreign-copper wall still blocks emission; successful legacy paths
never invoke the new fallback. Other tests cover cumulative skew, priority
ownership, fixed-share probes and retained prefixes. The initial test run
needed one existing cache-probe test to mock the additional proposal source;
no expectation of safety or output quality was weakened.

`build/octilinear-pair-ribbon-control-20260915.json` exactly matches the preceding
PCIe2 SHA, board regression and all probes. Its pre-existing stricter release
failures remain; this is not new fabrication signoff.

`build/octilinear-ribbon-native-audit-20260915.json` checks six source families
unchanged and nine short, physical single-contact station-pair cases:
VHP 4, Hub 3, PCIe2 1, PCIe3 1. EPS/ATX have no such short unambiguous case in
these inputs. PCIe2 yields 4 geometric proposals (4 meet the coupling
contract); PCIe3 yields 8 (7 meet it). VHP/Hub yield none in this sampled
straight-trunk domain. All emitted proposals meet endpoint, angle, crossing
and mutual-gap assertions. This audit does NOT include foreign-copper or full
board admission. Longest per-case generation was approximately 0.010 s.

The exact retained VHP reconstruction in
`build/octilinear-pair-ribbon-replay-20260915/` completed in 16.112 s,
sources/diagnostic family/engine unchanged. Both final branches generated no
new ribbon; final skew and coupling are identical to the preceding replay.
The new feature therefore has **no measured closure improvement on that VHP
case**. It does solve the synthetic generator/checker mismatch and produces
cross-board native-contact candidates; do not inflate that into board progress.

## Next cause under test, not yet a production repair

`build/parallel-link-domain-audit-20260915-c.json` independently replays the
existing topology-owned link placement menu using actual footprint geometry.
Library and serialized native pin geometry agree for the affected owner and
both links; this is not another stale-footprint explanation.

Only 2 of the first 32 joint placement proposals survive retained-copper
screening. Among the first 256, 10 survive: **eight additional offers are
hidden below the current early cap**. The native screen keeps all protected
power and unrelated owned copper; eligibility is NOT physical or route
admission. The additional offers still need the same exact transaction checks.
No source position or mating geometry was modified by this audit.

The next bounded diagnostic selects the first two surviving offers beyond
the old cap using the same sorted menu, then reconstructs through the normal
isolated power/dependency handoff. It does not manually invent placements,
promote a result or change the production menu size. If useful, implement
generic retained-constraint filtering before beam truncation, with bounded
predicate work and synthetic/cross-board regressions. Do not merely raise the
final trial budget or waive power/physical checks.

## Active follow-ups

* Canonical PCIe3: `build/octilinear-ribbon-suite-20260915/suite.json`.
  Started 2026-09-15T05:40:46Z; coordinator PID 3285778 / board PID 3285780,
  verified live.
  New native-contact candidates justify this replay. One job, two workers,
  original 1200-s priority / 1800-s board limits; immutable pass previews.
* Native VHP support diagnostic: `build/link-support-replay-20260915/`.
  Parent PID 3286094 / native worker PID 3286095, verified live.
  Offers bound by `build/link-support-replay-offers-20260915.json`; input
  lineage and exact retained-copper checks are recorded. At most two offers,
  600-s isolated operation limit, **no promotion authority**.

Check journals AND live processes before dispatch or shared script edits;
do not duplicate these jobs. The cumulative three-board cohort and the
octilinear retained-case replay are complete. Do not rerun unchanged Hub/VHP
full waves for this straight-trunk slice. PCIe2 remains at 0 DRC / 12 opens in
its partial continuation and protected in regression. EPS/ATX require a
qualified paired mating ECO; no dimension, edge-span or pad compromise is
authorized. Free space remains about 70 GiB, with a 16-GiB campaign floor.
The final three-board gallery was visually inspected and Windows dashboard
HTTP returned 200 during this continuation.
