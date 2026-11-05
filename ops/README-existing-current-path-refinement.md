# Existing physically sized current-path refinement

This scope is deliberately separate from the original preferred-width
full-current routing owner, whose behavior and defaults remain unchanged.
It refines an existing outer-face, ungrouped, plain uniform-width current
path without changing that width, face, current budget, pads, barrels,
project rules or routing preference. The source width must already meet
the positive manufacturer/process and actual-layer current contract. A
passing source-to-selected-sinks check is not a substitute for that floor.

The saved Hub rules explicitly describe `track_width` as a routing default;
actual custom minimums and the independent current/zone gates are separate.
The existing USB VBUS path has a 0.5 A authority with the unchanged 1.25
geometry margin and a 0.0806440616 mm modeled B.Cu current floor. Its existing
0.2 mm width also meets the actual factory floor. This does not permit the
same 0.2 mm width for the 2.5 A standby paths, which this scope refuses.
No new hardware load, thermals, capacitor inrush or barrel rating is inferred.

Visual review of a real candidate exposed a centerline-score blind spot: a
miter can close a triangular loop against retained same-net copper. Planning
now unions actual same-net native pads, tracks and saved fills, subtracts all
actual bores, and refuses any newly enclosed void by exact integer polygon
difference. No area epsilon or lower bend count can waive this guard. Tests
cover the retained-overlap counterexample on both faces and four rotations.

Planning requires exact source ownership, process fields, canonical 0/45
geometry, fixed literal ports, shorter length, all old native adjacencies,
boundary tangents, native foreign/hole/edge/rule-area clearance and the
unchanged complete current model. Saved receiving re-derives the plan,
reconstructs every node from the source, checks actual drilled terminals,
every surviving native component, all prior current-sized terminal joins,
source-control reservations and whole current-debt nonregression.

This receiver is not routing/fabrication admission. Native custom-rule DRC,
fields, pair/reference, clipped Kelvin, ground returns, dimensions and stack
must still pass independently. The finite construction driver rejects every
new native fault, even when the local geometry receiver passed. A real-native
test adds an actual 0.5 mm minimum rule and proves that same-width proposals
are refused rather than published. Other tests cover both faces, four
rotations, a higher retained preference, unknown/changed budgets, inadequate
source widths and unowned deltas. No board/refdes/coordinate policy is used.
