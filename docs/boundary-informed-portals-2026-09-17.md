# Boundary-informed escape proposals — experimental, not promoted

## New finite domain

`scripts/cec_portal_boundary.py` is a **proposal-only helper, not wired into the
production router**. It intersects each existing paired-portal ray with the
inflated foreign reservation rectangles for both signal members. It adds
midpoint/inset samples only in clear lead intervals missed by the original
lead menu. Original rows, headings, polarity, lateral offsets and per-heading
lead bounds are retained. The same-net exemption applies to each individual
member, not the entire pair. Rectangles cannot admit copper or prove no-path;
all native via/fan-in/return/whole-route gates remain mandatory.

The bounded prototype tests translated/rotated geometry, overlap/tangency,
invalid policy inputs, exact member ownership, and loaded native all-layer
reservation guards. The latter demonstrate a narrow legal seat interval which
the original discrete leads miss without changing or removing parent copper.

## Completed native experiments

`build/power-boundary-domain-20260917/report.json`:

- PCIe3: the full bound power authority contains 258 reservation rectangles.
  The prototype adds 24 source-end proposals (12 per polarity); the native
  plated connector end is not given unnecessary signal vias. Two new local
  source fan-in/transition candidates qualify. One whole-edge proposal reaches
  86.4% coupled coverage, passes its graph and route-quality checks, but fails
  the existing 2.0 detour limit: N is 31.655573 mm / 14.208009 mm = 2.228009.
  This is **not** independent pair/board signoff. It is discarded exactly;
  zero new copper survives. The profiled probe took 7.005 seconds.
- VHP: no future reservation rectangles exist at this already materialized
  prefix, so this reservation-only hypothesis supplies no new domain. The
  unchanged route was deliberately not repeated.
- Six canonical source/hierarchy hashes and the historical PCIe2 control match.

`build/materialized-boundary-domain-20260917/report.json` separately tests VHP
using actual native track/pad envelopes **only for proposal generation**. It
does not replace native collision shapes or turn those boxes into guard
obstacles. It adds 105 proposals across the two endpoint/polarity domains.
Two start-side candidates qualify locally; a whole inner-layer ribbon is still
refused and another fan-in is not reproducible within the remaining deadline.
The 120.018-second probe expires with exact rollback, zero new copper and all
six source/hierarchy identities unchanged. No geometry, clearance or coupling
limit was waived.

## Deeper-beam experiment exposed a continuation limitation

`build/boundary-beam-diversity-20260917/report.json` requests two/four candidates
per endpoint in private wrappers. Neither is a demonstrated deeper complete
search: the current local screen breaks after a phase whenever an earlier
candidate already exists. Resuming a partially positive domain can therefore
keep returning that same subset without advancing to its remaining dogbone
phase. The saved scheduler visits show unchanged completed-query counts and
64-round limits, not a proof that a two/four-wide beam is exhausted.

Both wrappers finish refused (45.339 / 45.944 seconds) and restore exact parent
copper. Do **not** repeat them or promote the wrappers. The next generic solver
slice is explicit positive-frontier continuation and consumer-directed endpoint
diversity after whole-edge detour/skew refusal, with no-progress termination.
It must preserve known-good fast paths, exact rollback, unchanged total budgets,
and independent whole-pair admission. Integration of the boundary helper should
wait for that slice and cross-board validation; more identical seeds will not
test it.

## Small production evidence correction

The old refusal text formatted `clearance=0.2 mm` as `0.2R geometry`, claimed
**every** candidate hit a reserved corridor when only some recorded conflicts
existed, and promised that the fallback would route it. The shared message
builder now reports actual width/gap/clearance in mm, qualifies the failure as
an attempted-search result, lists conflicts as observations, and does not
promise fallback success. No geometry, admission or scheduling changed.
Historical receipts retain their original text; they have not been rewritten.

`build/portal-boundary-and-refusal-final-tests-20260917.log`: **96 focused tests
pass**, 15.46 seconds, overlapping the prior 486-test suite. The helper's 12
geometry/native cases are included. `build/boundary-final-parity-20260917`
contains the final six-source/hierarchy and historical PCIe2 control replay.
The production shape/routing policy remains unchanged except for the already
documented previous via-envelope fixes. These new prototypes are not automatic
route policy, not a new candidate and not a fabrication release.

No worker or newly promoted board/image remains. Keep
`build/additive-first-next-inputs-20260917.json` authoritative, Hub's 125-pose
history, PCIe2's five-open candidate and the pending EPS/ATX interface decision.
