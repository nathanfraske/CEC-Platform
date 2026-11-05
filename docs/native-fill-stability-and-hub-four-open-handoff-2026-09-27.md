# Native fill stability and four-open Hub handoff — 2026-09-27

## Accepted result and scope

The current Hub has advanced from **five to four native unconnected items**,
with zero qualified structural DRC and no previously passing gate lost.
It is still **not fabrication ready**. This is not a new schematic/revision.
No BOM, outline, fabrication rule, power contour, priority, or stack geometry
was changed. ATX and the PCIe review artifact remain unchanged.

- Exact starting parent: archive `20260926-hub-standard-rev2-checkpoint-continuation-3e256527a3`.
  SHA256 `3e256527a31211cf3c11f39497a8f30c75a0f9cb081eb47bcf247a24ca4e84a0`.
- Accepted archive: `20260927-hub-standard-rev2-checkpoint-continuation-73f69a72cb`.
  SHA256 `73f69a72cb9f87e8881225792d7bf45bbfc1705d78b4c90a88a8aed58e6cd1ec`.
- Viewer: <http://localhost:8090/?id=20260927-hub-standard-rev2-checkpoint-continuation-73f69a72cb>.
- Evidence root: `build/fill-stability-20260927/`.

The connectivity gain comes from **revalidating the previously unaccepted
four-open proposal**, not from claiming that today's new waves discovered
another connection. A private copy receives the existing generic acute-vertex
cleanup and the corrected native refill, then the complete existing support
placement admission and fresh whole-board grading against the exact latest
five-open parent. The saved proposal and parent input families stay untouched.

`hub-saved-proposal/native-control.json` records acceptance, no gate
regressions, and five -> four opens. `revalidation/revalidation.json` records
the independently revalidated support rotation, preserved component/pad
definitions, rules, locked/pair/power authority and physical placement check.
The only removed parent copper is the independently proved support-owned
ground branch; all 316 surviving members of its original native component
remain connected. All **20 protected zone/layer entries lose zero polygons
and zero area**, with **zero tolerance**. Four shape advisories remain; the
recent cleanup was not undone.

## Root cause and generic fix

Six repeated no-edit native refills reproduced two corner shapes on one
unchanged protected zone. Five matched the saved shape; one lost the same
two 8,230 nm2 slivers seen in the rejected proposal. Self-subtraction is empty;
this is not merely a display artifact. No area tolerance was introduced.

The installed engine is KiCad 10.0.5. Its initial fill dependency graph tests
actual outline collision, while different-net knockout collection considers
bounding-box intersection. A higher-priority, disjoint zone can therefore
finish early enough to trigger an additional minimum-width pruning pass, or
finish too late. Rounded corners differ accordingly. The actual Hub has two
such higher-priority zones: expanded boxes intersect, but outline collision is
false (`dependency-mismatch.json`). The relevant native implementation is
[KiCad 10.0.5 zone_filler.cpp](https://gitlab.com/kicad/code/kicad/-/raw/10.0.5/pcbnew/zone_filler.cpp)
(`zone_fill_dependency`, `buildDifferentNetZoneClearances`,
`postKnockoutMinWidthPrune`); the native priority comparator also includes
teardrops and UUID tie-breaking in
[zone.cpp](https://gitlab.com/kicad/code/kicad/-/raw/10.0.5/pcbnew/zone.cpp).

`scripts/cec_zone_fill.py` is the shared workaround:

1. Run the normal complete native fill to establish whole-board connectivity.
2. Settle zones in native priority order, using only the real native filler.
3. Require exact filled-polygon fingerprints to agree across two ordered
   passes. A failed native operation or nonconvergence raises; there is no
   unbounded retry, contour patch, injected copper, or relaxed DRC rule.
4. Existing downstream preservation, placement, connectivity, pair and spacing
   checks still decide acceptance.

All 59 previous direct native fill call sites across 31 pipeline scripts now
use this boundary, including isolated fill workers, routing, repair, pouring,
thermal artifact preparation and placement. No board/refdes/coordinate special
case is in the helper. A regression scans pipeline Python call sites to stop
new direct native fill bypasses. Repair reports retain fill stability evidence.

The ordered scheduling prototypes passed 24 source/proposal trials; the actual
production helper passed 12 additional independently loaded source/proposal
trials. Every trial preserved protected copper exactly. Production fill time
was approximately 0.96–1.03 seconds per Hub and 0.46–0.51 seconds per PCIe
control in these measurements. This correctness workaround serializes zone
settling, not the entire routing campaign; large-zone-count scaling is not yet
benchmarked. Do not present it as a performance improvement.

## Regression and independent spacing evidence

- Main affected regression set: **626 passed, five skipped, 17 subtests**.
  Three initial failures were old test doubles mocking the native constructor;
  they now mock the shared fill boundary. Native behavior is tested separately.
- Supplemental routing/pour/repair tests: **342 passed**.
- Final focused stability/history/polish tests: **57 passed**.
  These sets overlap; their sum is not a unique-test count.
- Synthetic native fixtures cover renamed nets, translation, rotation,
  front/back copper, disjoint shapes with overlapping boxes, repeat stability,
  unchanged authored contours, real foreign-track copper loss, native failures
  and bounded nonconvergence. The existing 100 nm2-loss rejection still passes.
- PCIe two-port control: three stable refills, exact same PCB SHA256
  `2f09d2765bacc5281a52fc7b6afaafa06078fb3aa1c1c2be037b708edd059388`,
  zero opens and zero qualified structural DRC. Existing `pairs_ok: false` and
  thermal-not-qualified flags remain visible; this is not new fab approval.
- Hub spacing: **184,704 trace pairs**, 53 existing sub-nanometre shortfalls,
  minimum 0.199999927 mm at a 0.2 mm requirement, and **zero shortfalls >=1 nm**.
  The independent strict audit remains false, not hidden. Native clearance and
  short violations are absent. Raw structural entries remain 90 via-diameter,
  90 annular-width, 24 copper-edge and four hole-clearance records, qualified by
  existing process/geometry policy. No DRC exclusions were added.
- Models-off top/bottom and all six copper views were exported from the exact
  accepted PCB. The dashboard catalog identifies its hash-bound archive as
  latest, with no sync errors.

## What the fresh waves did, and what they did not do

The first 180-second residual lease made no connectivity gain. Its subsequent
global fallback ended without a final oracle under a 480-second external cap.
The Windows command returned exit 1, so the exact termination cause is not
established. An earlier progress message attributed it to the cap; only the
incomplete result is certain. It is not a completed canonical routing pass.

One replay harness omitted `candidate_origin`, so the production history
writer correctly refused to persist hints. That owned run was stopped, not
counted as learned progress. The harness now asserts persistence. The corrected
replay demonstrably received prior net outcomes and made the trapped support
eligible, but its two-pose breadth trial repeated rejected poses. Its later
negotiation lease exhausted without a gain. The global fallback was explicitly
stopped after the saved proposal passed revalidation at four opens. Neither
incomplete global fallback was promoted. Each has a diagnostic-stop record.

This exposes the next bounded generic improvement: **source/rule-scoped exact
placement-pose history through the compact coordinator handoff**. Net outcomes
survive, but `_prior_footprint_candidate_keys` consumes full prior reports;
the compact handoff does not preserve those keys. Two-pose breadth can restart
at the same refusals instead of advancing to the useful rotation. Add bounded,
validated pose identities, invalidate them on source/rule/algorithm changes,
and test real writer/reader round trips. This is a scheduling hint, never
authority to waive a placement gate or proof that no route exists. Do not run
indefinite duplicate global waves before addressing that gap.

## Remaining blockers and unchanged authority

The four open nets are `+3V3`, `/KVM_5V_IN`,
`/POWER INPUT + SOURCE SELECTION/U11_OV1`, and `/USB_VBUS`.
The existing C37 courtyard-to-edge shortfall (0.475 mm versus 0.8 mm), four
shape advisories, exact sub-nanometre spacing findings and thermal/injection
qualification remain unresolved release work.

Unchanged hashes:

- Active ATX/Hub pair manifest: `dfbeccb8eca4331c53c92c95b77d82dea03d4d8f396effda2860ca1d99882463`.
- ATX placement: `83799200c0dae6ddd158d66de1e43d548a34547bd59b8d29539d929ac3d7814b`.

All owned experimental routing processes were stopped or completed. No
unattended campaign, fabrication approval, commit or push is claimed.
