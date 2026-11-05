# Bounded native pair-order transactions

## Implementation

The priority router can now backtrack the order of connected coupled-pair
segments inside an explicit transaction. `cec_pair_order_repair` derives a
shared series group from live opposite-pad identities on two native two-land
supports, not a product or reference-name allowlist. Translated, rotated and
renamed fixtures use the same derivation.

The incumbent topology-first schedule still runs first. If one newly generated
segment succeeds and a connected later segment fails, the engine tries the
failed segment first **once** for that group. Groups are limited to four pairs
and share one 120-second retry budget, clamped to the enclosing operation with
its completion reserve. Recursive retries are disabled. Already attempted
failed-first order, incomplete scope, ambiguous ownership and any group with
source copper on its pair nets are not retryable.

Only copper IDs actually created by those pair transactions are replaceable,
including their supporting ground vias. Native snapshots retain original
identity, geometry, conductor dimensions, locks and group membership. Every
other item remains a fixed obstacle. A failed, partial, timed-out or exceptional
trial restores the exact incumbent. Unexpected fixed-copper mutation is rejected
and restored, never accepted as a useful route. Empty groups created by a
rejected transaction are removed; original groups and their other members
remain. Loaded-native tests exercise these lifetime/rollback cases.

The existing complete precision ladder is the retry callback: package closure,
coupling, skew, topology, return fields, physical geometry and source guards are
not replaced by a raw connectivity score. Adoption requires every pair in the
group to qualify, preserves earlier coverage and rejects partial replacement.
Other pairs, high-current copper and placements are not opportunistically moved.
Whole-board physical/DRC and release admission remain downstream.

## Why the second bounded domain was necessary

The initial native order-only trial kept future-launch rectangles hard even
inside the atomic group. PCIe3's reverse order completed in 108.385 seconds but
still refused CAN_J1; CAN remained qualified, so the incumbent was restored
exactly. The full priority probe retained eight critical refusals in 194.991
seconds. The trial did not exhaust its overall search deadline.

That trial still included a synthetic approximation of the not-yet-routed
member. In the final v2 transaction, only **within-group synthetic future-launch
reservations** are deferred to actual complete-group routing. Source power,
native foreign pads/copper, other groups' reservations, widths, gaps, via rules
and all electrical/fabrication checks remain hard. The first member cannot be
published unless the second actually qualifies. Scope validation rejects this
mode outside a bounded, exact, non-recursive group transaction.

The dispatch regression verifies baseline A/B/independent followed by retry B/A,
that the unrelated reservation is retained, and that no recursive order loop
occurs. The order repair and bounded refusal search trace survive both preflight
projection boundaries.

## Validation status

**596 tests and two subtests pass in 29.94 seconds**:
`build/pair-order-joint-broad-tests-20260917.log`. This includes existing pair,
return, geometry, native ownership, residual, reservation and preflight suites.
The simpler first-domain run passed 595 tests before the additional scope guard.

The first concurrent suite completed with no board promotion:

| Board | Priority result | Wall time |
| --- | --- | --- |
| PCIe3 | Eight critical refusals remain; failed reverse order rolled back exactly | 194.991 s |
| 12VHPWR | One critical refusal remains | 77.564 s |
| Hub | One diagnostic priority refusal; three separate craft holds remain | 134.287 s |

Evidence: `build/pair-order-suite-20260917/report.json`. Native group derivation
recognizes shared supports in PCIe2, PCIe3, VHP and ATX. This is classification,
not authority to reroute source-owned pairs or route the mechanically held ATX.
EPS and Hub have no such current shared group. All six physical/source/hierarchy
checks and the historical PCIe2 control match. Generalization remains core-pass,
23 physical / 380 runtime legacy findings, `release_ok=false`.

The final v2 cohort completed. PCIe3 still has eight critical refusals after
152.285 seconds. The refused-first atomic retry took 68.386 seconds, qualified
CAN but not CAN_J1, and restored the incumbent's exact copper/group inventory.
Fixed copper is unchanged and no transaction was adopted. The overall retry
deadline was not exhausted; bounded portal searches rejected the available
transition candidates and endpoint POFV was not qualified. This does not prove
that a legal route is impossible, nor that more time alone would resolve it.

Fresh concurrent physical checks retain PCIe2/PCIe3/VHP passes and the Hub's
three craft holds. EPS/ATX remain mechanically unadmitted and were checked for
source/hierarchy identity and native group classification, not granted a new
physical pass. All six sources/hierarchies and the frozen engine are unchanged.
Historical PCIe2 board/hash/probe parity passes. Generalization is core-pass,
23 physical / 380 runtime legacy findings, `release_ok=false`.

Evidence: `build/pair-order-joint-suite-20260917/report.json`. All cohort workers
have finished; approximately 64 GiB remains free. Do not repeat this exhausted
ordering domain or the unchanged Hub/VHP priority searches. No source, board,
review image or continuation has been promoted. The authoritative inputs remain
`build/additive-first-next-inputs-20260917.json`.

## Independent Hub investigation for the next slice

Current native inspection explains part of the recurring ground-return refusal:
the affected mux ground lands are **0.20 mm wide**. Neither a 0.35 mm nor a
0.30 mm filled/capped via land can be fully contained in them. This is a real
containment refusal, not permission to waive the pad check. The nearby capacitor
land can contain those geometries, but that alone does not prove clearance to
surrounding copper. Evidence: `build/ground-pad-geometry-inventory-20260917.json`.

The generic return generator currently uses the compact process geometry at
pad centre, then switches to an ordinary board-legal dogbone of at least
0.60 / 0.30 mm. A separate existing `local_pofv_via_decision` can re-prove a
qualified compact off-pad SMD dogbone. Inspect this generator/qualification
domain mismatch next; reuse the existing fabrication/local-topology proof and
current-approved width/return rules. Do not simply shrink ordinary ground vias,
alter power budgets, enlarge pads or claim a thermal qualification.

The Hub's old `atomic_multirail.enabled=false` is **not** evidence that a
required feature was accidentally disabled: that mechanism is for simultaneous
power-rail planner failures, which this incumbent does not have. Its recorded
legal local-placement alternatives failed monotonic craft admission; it retains
109 visited poses. Do not switch on power replanning to repair local returns.
EPS/ATX still need the coupled mechanical ECO within the existing spans; their
native staging boards do not carry a POFV declaration, so the ground-pad
inventory records that separately from a physical pad-size refusal.
