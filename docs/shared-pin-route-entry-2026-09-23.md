# Shared-pin placement and route-entry continuation — 2026-09-23

## Scope

Continue the exact current compact Hub/ATX pair toward routing. No canonical
board, schematic, BOM, active-pair manifest, or fab-review control is replaced.
All trials are under `build/hub-route-start-20260923/`. The source Hub is
`build/hub-atx-power-routing-20260922-v8/hub-standard-rev2/02-placement/board.kicad_pcb`;
the source ATX remains the 78 × 95 mm v3 compact placement, not the older wider
diagnostic.

## Generic shared-pin reference

The MCU's two assigned bypasses share the same physical supply pin. The old
gate required both to lie within 0.250 mm of their respective *isolated*
complete-loop optimum. A 0.025 mm lattice found 737 individually qualified
seats for one package and 713 for the other, but no nonoverlapping pair. Other
components blocked none of these seats. Repeating neighbourhood evictions
could not fix this contradictory independent objective.

`cec_shared_pin_reference.py` supplies a bounded, continuous two-capacitor
reference. Each sum-of-two-distances sublevel set is an ellipse. Exact axis
supports of the ellipse clipped to each legal side of the owner rectangle
provide a separating-axis feasibility test for the two capacitor rectangles.
Bisection brackets the minimum maximum excess over the isolated references.

The Hub's unavoidable excess is bracketed at **0.399549–0.399567 mm**. The gate
uses the **lower**, optimistic bound, not a sampled feasible upper bound.
The existing 0.250 mm placement margin is unchanged. Absolute supply/return
limits, actual construction of both via-in-pad returns, copper clearance,
native assembly checks, and full power admission remain independent.

Applicability is deliberately narrow and explicit: exactly two assigned
capacitors on the same physical pin and mounting face, qualified dual-via
returns, rectangular authored courtyards, and cardinal assembly orientations.
Unsupported populations and geometry retain the existing gate. Refdes,
product names, and absolute board coordinates do not participate in policy.
Native courtyard centre-lines are read directly: the cached envelope includes
pen width, which would overstate the packing lower bound.

The reference also supplies an atomic placement proposal and feeds the normal
joint lattice's objective. The canonical bounded repair selected a still
smaller displacement: **both capacitors moved 0.025 mm**. The failing loop
excess over the joint reference became **0.217 mm**, below the unchanged
0.250 mm margin. The companion remains within its limit. Bounds, native
courtyards, local copper construction, and placement constraints all pass.

The generic fiducial pass also moved two optical marks. A mezzanine coordinate
was normalized by one native unit (1 nm); all 18 paired contacts still align.
The MCU and board outline were not relocated or enlarged.

## Pair-coupling hot path

A runtime stack sample found repeated segment/segment distance work when the
query was only a point. `_polyline_coupling_coverage` now evaluates each unique
point/segment distance once, retaining endpoint and degenerate-segment
roundoff semantics. Sampling, gap thresholds, and admission are unchanged.

Random, rotated-path, crossing, endpoint, tiny-segment, and large-coordinate
fixtures retain exact coverage results. A small isolated benchmark is **2.57×**
faster; this is not a claim of a 2.57× whole-router speedup.

## Verified progress and first continuation

`full-pass-v1` passed physical placement and rebuilt **8/8 exact-connected
power domains**. It did not reach general routing: the CAN pair exhausted its
120-second probe budget and the USB flow-through probe refused a coupled path.
The measurement was also correctly invalidated because router code changed
during that probe. No invalid evidence was promoted. Subsequent continuation
freezes the code and uses an explicit 240-second pair budget and a bounded
20-minute overall run.

ATX investigation identified three generated power vias inside the preserved
bulk-cap vent keepout and a fiducial inside an opposing-cap body keepout. Those
regions were not deleted. A replacement-placement attempt correctly refused
to discard 38 unowned existing copper items; the follow-up preserves the
authored routed prefix instead of stripping it.

## Regression and mechanical evidence

- Combined placement/power/native regression: **747 tests + 10 subtests** pass.
- Final shared-pin suite: **18 tests** pass (including three additional
  invalid-bound cases after the combined run).
- Pair/flow-through/ribbon suite: **120 tests + 2 subtests** pass.
- Immutable PCIe two-port control remains **0 DRC, 0 opens**, with all
  non-regression terms retained. Its two existing release-constraint findings
  are not waived. A separate new-vs-isolated decoupler replay reports no
  findings in either mode and unchanged board bytes.
- Pair geometry/body/vent screen still passes with **18 aligned contacts**,
  unchanged source boards and unchanged active-pair manifest. Physical samples,
  hardware tolerances/load testing, and thermal/bench qualification remain open.
- Generic-core audit includes the new module. Legacy whole-pipeline special
  case debt still prevents claiming the entire pipeline is generic.

Evidence: `joint-domain.json`, `shared-reference-authored.json`,
`full-pass-v1/02-placement/board.placement.json`, `coupling-benchmark.json`,
`regression-tests.log`, `shared-final-tests.log`, `pair-tests.log`,
`pcie2-regression.json`, `pcie2-cell-replay.json`, `pair-validation/`, and
`generalization.json`, all beneath the slice root.

## Bounded routing continuation

The unchanged-engine `full-pass-v2` passed physical placement and all eight
exact power domains, but its first CAN attempt completed only three of six
tree edges. The nested scheduler was dividing the same pair budget twice,
leaving the primary tree only one quarter of the total. The generic scheduler
now reserves two thirds for the primary complete tree and divides/reclaims the
remainder among actual alternatives. Fake-clock tests prove both reservation
and the unchanged hard deadline. It does not enlarge a board or relax a gate.

With that change, `can-primary-budget-pinned` constructed all six CAN branches
and 157 new copper items in 125.7 seconds, passing its ownership, skew,
coupling, and route-quality checks. This was **not native routing admission**.
`full-pass-v3` passed source intake and preserved-prefix placement but stopped
at critical preflight. General/residual routing has not been admitted.

Independent native verification exposed two additional generator defects:

1. Four inner-layer CAN tracks crossed the top-left outline notch. The shared
   edge predicate checked a bounding box, arc boxes, and footprint-local
   apertures, but not straight concave board-level boundaries. Native polygon
   containment plus full capsule-to-boundary clearance now rejects these
   crossings, closed board-level holes, and via lands outside material. The
   final whole-pair graph audit repeats the check, independently of search.
2. A clearance-clean GND return sat in an antipad pocket with no filled-plane
   contact. The native plane stage rejected and rolled back that fill. A new
   disposable native reference preview filters candidate returns without
   changing the routing board; final native refill remains mandatory. An
   isolated ownership-scoped replay replaces only the failed generated return
   and proves all required contacts. The original invalid CAN prefix still
   fails four edge-clearance checks and 93.7% versus 95% plane coverage, so that
   replay is evidence for the return fix, not an accepted candidate.

The exact original return failure was generated during a pair transition, not
the final plated-terminal sweep (which initially reported the nearby via as
already covered). The same preview must therefore constrain both constructors;
filtering only the final sweep would add a valid return without removing the
earlier invalid required barrel. This distinction is retained in the evidence.

USB still refuses a complete coupled flow-through route. The generic placement
proposal domain now includes legal 180/90/270-degree **in-place** rotations
before translation/eviction. Tests cover transformed/renamed fixtures, fixed
references, collision checks, close-but-nonoverlapping courtyards, and finite
proposal limits. On this Hub it proposes a legal 180-degree protector rotation;
a measured trial with the exact local-PI copper still refuses USB. No failed
rotation trial has replaced the canonical placement or its power certificate.

`atx-preserved-full-pass` retained all 38 authored copper items, then stopped at
force-rail construction (one of four domains). Existing sense copper, a CAN
terminal, and a reset/enable pad obstruct its remaining constructors. No ATX
routing or dead-bug mechanical qualification is claimed from that attempt.

## Visible diagnostic and immutable controls

The dashboard diagnostic is
`http://localhost:8090/?id=20260923-hub-can-routing-progress-6a35872c27`.
Both its page and models-off image were fetched successfully. Its explicit
banner says **partial CAN routing trial, not fab ready**, **39 DRC / 260 opens**,
with USB and GND validation blocked. Those counts describe the actual saved
artifact after the failed ground-fill rollback, not a transient in-memory fill.
The later isolated return replay is not silently substituted for this image.

All original Hub/ATX source bytes, the active-pair manifest, and the PCIe
two-port fab-review archive remain unchanged. The native PCIe replay retains
0 DRC / 0 opens and its prior two independent release-constraint blockers:
one Kelvin departure and 80% versus 95% CAN reference-plane coverage. They are
reported as existing issues, not waived or called newly introduced regressions.

Additional evidence under the slice root: `full-pass-v2/`, `full-pass-v3/`,
`can-primary-budget-pinned/`, `can-reference-proof/`,
`can-reference-filtered/`, `return-preview-stage-proof-v2/`,
`usb-grid-transaction/`, `usb-inline-rotation/`,
`inline-rotation-final-domain.json`, `material-guard-tests-v2.log`,
`final-routing-tests-v3.log`, and `pcie2-reference-filter-regression.json`.

## Verified CAN checkpoint after both generator fixes

The final immutable-engine trial, `can-final-guarded`, routed all six CAN
branches in **162.5 seconds**, generating 174 protected copper items. Its
360-second pair budget was not exhausted. Transition-return generation now
shares a lazy, transaction-local native reference preview with the final
plated-terminal constructor; later invocations and exceptional exits cannot
inherit that snapshot. It is still proposal evidence, not signoff.

The saved `can-final-proof/board.kicad_pcb` passes native refill, every required
return contact, **0 native DRC**, and the independent CAN electrical geometry
and filled-reference-plane checks. The existing critical-checkpoint validator
admits it as a **partial critical-route checkpoint**. Against a separately
refilled immutable parent, opens decreased **282 → 199** (83 fewer, 29.4%).
All parent copper and every component placement are preserved. This includes
the early exact local-PI work; the improvement is not attributed solely to CAN.

The active-pair geometry screen still has **18 aligned contacts** and no
body/vent failures. No source/manifest or control-board bytes changed.
Latest regression suites: **589 tests + 10 subtests** for routing/decoupling,
and **298 tests** for authority, critical checkpoints, placement admission,
and immutable-control handling. The final native PCIe replay retains 0 DRC /
0 opens and the two previously listed release-constraint blockers.

The new models-off dashboard artifact supersedes the earlier invalid trial:
`http://localhost:8090/?id=20260923-hub-can-prefix-verified-965e13b59b`.
Both the page and image return HTTP 200. The artifact explicitly says **CAN
prefix verified; USB and residual routing incomplete; not fab ready**. Its
SHA-256 is `965e13b59b1597f887a0fa57bd08f39b8ea23354672dcfacb8d0e080e94a9fae`.
Do not confuse a successful partial checkpoint with full-board routing or
manufacturing admission. A normal bounded canonical continuation (`full-pass-v4`)
starts from this exact verified prefix and retains all ordinary stage gates.

The archive includes all six native copper SVGs as well as top/bottom models-off
renders; the inner-signal plot and catalog entry were also fetched successfully.

### Remaining placement-resume boundary (read-only diagnosis)

`can-final-proof/resume-coverage.json` proves the qualified CAN pair and its
12 identity-owned GND returns are retained by the placement materializer.
However, its existing retention contract covers only **208 of 271** copper
items. The other **63** are early local-PI copper on +3V3, LOGIC_REG_IN,
KVM_5V_IN, PSU_5V_KVM, USB_VBUS, and GND. They must not be discarded to make
the USB protector movable. A follow-up generic slice needs to transfer that
existing exact local-copper contract into placement-resume ownership, including
terminal geometry and group identity checks, or use a route-owned local ECO.
This is separate from CAN's now-passing electrical/native checkpoint.

### Canonical continuation outcome

`full-pass-v4` finished its bounded attempt. Source intake and placement pass;
placement output is byte-identical to the verified checkpoint. Route preflight
retains CAN as `preexisting-locked`, then refuses USB's connector-to-inline
protector leg under the unchanged 0.2 mm width, 0.34 mm gap, and 0.2 mm
clearance contracts. This was an exhausted finite candidate domain, not an
outer deadline expiry; merely increasing the budget is not a demonstrated fix.
The preflight also reports one ordinary pad without straight escape and three
ordinary unroutable coarse-grid connections as warnings. General routing did
not start, and no fabrication files were emitted. The next bounded generic
slice is local-PI-aware placement-resume ownership, followed by exact USB
escape/placement repair while preserving this qualified CAN prefix. ATX still
needs the force-rail/keepout conflicts described above resolved separately.

All runs in this foreground continuation have ended; no unattended wave is
being represented as running. The slice artifacts occupy approximately 301 MB.
