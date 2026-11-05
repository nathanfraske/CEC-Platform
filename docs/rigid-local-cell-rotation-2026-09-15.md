# Preserve complete local cells during measured endpoint rotation

## Completed pass and actual outcome

`build/search-domain-followup-suite-20260915/suite.json` finished **20:58:12Z**.
The PCIe3 worker took 786.89 seconds. Source, hierarchy and engine guards passed,
all descendants exited, and the final board was restored byte-identically to
input **400ffdd8635e**. It still has **12 critical-route placement failures**.
The apparent 12 -> 11 pair improvement did not survive final post-power physical
admission. No main routing or fab-ready result was produced. Do not rerun this
cohort unchanged.

Its immutable body-free placement review was API-verified and visually checked:
`pass-search-domain-followup-suite-20260915-pcie-8pin-3port-df32ef18c6`.
The Windows mirror is
`C:/Users/Admin/Documents/CEC-Board-Reviews/search-domain-followup-suite-20260915/pcie-8pin-3port/render.png`.
It is labeled BLOCKED/placement/not fab signoff and is the unchanged current
input, not a newly routed board.

## Root cause and repair

The new search domain exposed a previously unreachable range-rotation defect.
In `operation-priority-repair-69me3g9w/report.json`, round two's rotated endpoint
cell reduces scoped Kelvin refusals nine -> eight, but its final craft evidence
names a **6.31-mm C10/U10.6 bypass violation**. The range move rotated only the
owner footprint and translated its unrotated capacitor. It also predicted the
sense-pad rotation with Cartesian upward-Y math, opposite to KiCad's board
coordinates. Thus both the local bypass geometry and predicted reach could be
wrong. This was a producer defect correctly rejected by the craft gate, not a
reason to weaken that gate.

Implemented reusable `rotate_board_point` and `rigid_cell_transform` in
`cec_placement_search_domain`. The complete selected group rotates about its
owner, including every follower position and orientation, then receives the
measured translation. Both Kelvin path-rotation and range-rotation producers
use this transform; fixed followers remain immovable. Range prediction uses
the same native coordinate convention. No board/reference/coordinate special
case, bus alteration, new manufacturing limit or broadened unlock authority.
Other independent orientation producers are not claimed audited by this slice.

## Verification

- Loaded-native synthetic fixtures compare every actual transformed pad against
  the geometric prediction, on front and back, at 90/180/270 and arbitrary 37
  degree rotations. Bypass pad distances stay invariant; fixed peers do not
  move. Generated range rotations land within the declared radius in native
  geometry and preserve the local bypass vector's length.
- `build/rigid-range-integration-tests-20260915.log`: **388 passed**, 13 skipped,
  16 subtests passed in 97.46 seconds. Includes placement, full-pipeline admission, dependency recovery,
  generalization and repeated native repair cleanup. The 13 old Hub-fixture
  tests remain unavailable; no skipped test is presented as passed.
- `build/rigid-range-suite-replay-20260915/report.json`: six hash-bound current
  lineages in three workers; all source/hierarchy/engine guards hold. Four
  admitted boards run fresh native Kelvin proposal analysis; EPS/ATX retain
  their interface ECO hold. PCIe3's 52 proposals undergo **568 native pad-position
  checks**, all within 5 nm of prediction. Other admitted boards have no range
  refusals and no transformed proposals. This is not placement admission.
- `build/rigid-range-control-comparison-20260915.json`: protected PCIe2 PCB,
  complete regression and probes unchanged; only generalization evidence differs.
  The regression command's exit 1 is its pre-existing release holds.

## Next bounded run and independent holds

Canonical affected-stage full-pass journal:
`build/rigid-range-followup-suite-20260915/suite.json`. Read its current state and
live process tree before shared engine edits. The dispatcher requires passing
integration, six-family replay and unchanged historical control, then uses
exact PCIe3 400ff, four workers and the normal 1200-second cap. It tests this
specific producer correction; do not extend or repeat it unchanged.

PCIe2's complete local ownership receipts, Hub's return access, VHP's critical
flow-through escape and EPS/ATX's coupled mechanical/authority admission remain
independent work. This slice neither clears those holds nor justifies rerunning
their unchanged exhausted cohorts. No schematic, load budget, interface, fixed
power bus or thermal qualification was changed.
