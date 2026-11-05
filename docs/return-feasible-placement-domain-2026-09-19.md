# Return-feasible decoupler references and electrical contact placement

## Result and limits

The current Hub's three craft blockers reduce to **two**, without changing
its PCB or schematics. The removed blocker was an internally contradictory
reference target, not newly repaired copper. The two U7 local-ground-return
failures remain real constructor refusals; the board is still blocked from
routing admission. No candidate was promoted or marked fab-ready.

Canonical inputs remain `build/additive-first-next-inputs-20260917.json`.
Complete final physical replay is
`build/contact-seating-suite-20260919-qualified/report.json`.
All six source/hierarchy hashes and the historical PCIe2 control's PCB hash,
regression result and probes match. PCIe2's five opens, PCIe3's critical-route
debt, 12VHPWR's deferred C7 interconnect and EPS/ATX interface holds remain.
The historical control's already-known sideways Kelvin departure defect is
retained, not silently waived.

## Root cause: an inadmissible ideal placement

The old courtyard-tangent reference minimized the complete two-leg distance
without applying the hard ground-distance limit to that reference. The Hub's
U3/C2 reference had supply distance 0.550 mm but ground distance 2.912 mm,
which fails the existing 2.500 mm return limit. It nevertheless supplied the
0.550 mm reference for the independent supply-proximity gate. The actual C2
has supply distance 1.275 mm and ground distance 2.417 mm, and its native
local-cell construction already succeeds.

The generic reference solver now constrains each tangent's free axis to the
distance disk of a real owner ground pad. It calculates supply-minimizing and
convex complete-loop-minimizing seats along that interval. This domain is
used only when the previous reference violates the existing return limit.
Already-feasible reference results remain unchanged. Missing feasible seats
fail closed. Non-GND rail-to-rail topology retains its separate contract.

For an affected ordinary surface-return cell, the proximity gate uses the
**shortest return-feasible supply** reference, not the supply leg of a longer
complete-loop tradeoff. This prevents a shorter ground leg from licensing
an unnecessarily long supply connection. The Hub's corrected reference is
1.420 mm; the existing 0.250 mm proximity margin, 2.500 mm ground limit,
component assignment limits and native route/POFV checks are unchanged.
The original rejected reference is retained in the evidence.

## Generic placement search addition

`scripts/cec_constraint_seating.py` generates finite candidate centers from
the intersection of supply/return distance disks and courtyard boundaries.
The production incremental decoupler repair supplements its existing lattice
with these boundary contacts. It does not replace existing successful search
families, move an owner, alter a power bus, or relax admission.

Each of four orientations uses measured native terminal offsets. Courtyard
obstacles are expanded by the rotated capacitor outline. Native pad/copper
screening follows, then the ordinary frozen-power and full physical gates.
Candidate checks and obstacle population are bounded; exceeding the latter
does not authorize dropping obstacles. This is a proposal domain, never a
proof that no route exists. Complete-loop-only contracts remain with their
existing constructor.

One new Hub pose passed the frozen-power guard but retained both return
failures. It was rejected, and its work was added to the **158-pose** history:

`build/contact-seating-suite-20260919-qualified/hub-standard-rev2/board.placement-search.json`

Seed that history instead of the older 157-pose copy. Do not promote or
re-run the unchanged failed pose as a new routing candidate.

## Investigations not integrated

- A complete-population retry did not rescue either Hub cell. No new retry
  loop was added (`build/late-return-dependency-probe-20260919`).
- Instrumenting shared-ground links confirmed that the available U7.3 return
  is not an immediate sibling portal under the existing reach check. No
  ground-reach extension or new via qualification was inferred
  (`build/sibling-return-link-probe-20260919`).
- Counterfactual fixed-terminal poses produced no new admissible proposal;
  the immutable-owner guard was not weakened
  (`build/frozen-terminal-pose-probe-20260919`).
- Boundary-informed via-seat sampling did not resolve the Hub. A successful
  alternate PCIe3 return occurred on an already-passing baseline and is not
  a connectivity improvement (`build/return-boundary-probe-20260919`).

## Validation and remaining work

New tests cover renamed/translated/rotated geometry, loaded native front/back
footprints, finite work, obstacle overflow, malformed evidence, conflicting
distance limits, unchanged feasible references and impossible return domains.
The focused final run passes **366 tests**. The wider 47-file run finishes
with **1,104 passed, 19 skipped, three passing subtests and two failures**
in the legacy EPS placement-session integration described below. It is not
reported as an all-green suite.
The static generic-core audit includes the new module and passes. Its broader
legacy inventory remains **23 physical / 380 runtime findings**; this does
not make the entire historical pipeline fully generic.

Evidence paths:

- `build/contact-seating-suite-20260919-qualified/generalization-final.json`
- `build/contact-seating-suite-20260919-qualified/completion.json`
- `build/contact-seating-wide-tests-qualified-20260919.log`
- `build/contact-seating-targeted-final-20260919.log`
- `build/contact-seating-legacy-test-isolation-20260919.log`
- `build/contact-seating-legacy-order-isolation-20260919.log`

The wider test run exposed a separate existing EPS placement-session fixture:
its hard-containment test expects zero placement residual but produces seven.
An isolated replay with all three new placement/tangent entry points replaced
by failing sentinels reproduces that assertion with **zero calls to the new
code**. It is not hidden as a pass. A different mocked route-preflight test
was repaired to provide its missing dependency context; no production binding
check was bypassed.

The second wider-suite failure is `TestIntentLevers.test_order_bites`:
`p10_intents` attempts to move only an owner from a supply group already owned
by `p3_critical_seats`. The existing cell-ownership guard rejects that move.
Do not weaken that guard to satisfy the old test; the ordering request needs
to reach the owning stage or replan the complete cell. This is distinct from
the new contact proposal and tangent-reference code.
Its isolated sentinel replay likewise reproduces the ownership exception with
zero calls to the new code. Both integration failures remain open.

No board geometry changed, so an unchanged render was not republished as a
new winner. Next constructive work remains the Hub's frozen-owner ground
access dependency and PCIe3's critical input escapes. Do not solve them by
relaxing ground reach, moving frozen power, or independently shifting a mating
half. EPS/ATX need the coupled interface rebuild before ordinary routing.
