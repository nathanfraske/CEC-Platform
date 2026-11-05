# Fair, resumable critical escape search

## Implemented

The paired-portal constructor now screens both endpoints and both lane
polarities before deepening an empty domain. `fair_screen_domains` in
`cec_portal_feedback.py` gives independent prerequisite domains bounded,
increasing time slices and yields when a complete endpoint group is available
for the shared trunk search. The domain schedule and completion status are
retained in the routing evidence.

The production screen in `cec_precision_route.py` retains its completed query
frontier, exact negative witnesses, accepted candidates, and cumulative work
counts across those slices. Interrupted queries are retried, not interpreted
as an exhausted geometric domain. Partial beams are not cached as exhaustive
negative results. The shared original route deadline remains authoritative.

Transition screening also proves both signal-via barrels before searching for
their reference-return field. A failed signal field cannot be repaired by a
ground via. Completed field refusals are reused across direct/dogbone phases
only within the same immutable-parent transaction, with exact, unrounded
geometry keys. A clear signal field still requires the ordinary qualified GND
return check. Both signal witnesses are retained even when one already fails.

These are scheduling/query-reuse changes, not clearance, coupling, skew,
width, via, current, placement or release waivers. They contain no board,
reference-designator or coordinate repair case.

## Native results before the full-suite replay

The retained Hub and 12VHPWR were exercised through the production critical
checkpoint constructor, with the same 240-second per-pair setting. The selected
USB transaction was refused on both boards and rolled back. No new routing
candidate is qualified by these tests.

| Measurement | Hub | 12VHPWR |
| --- | ---: | ---: |
| Constructor elapsed with fair screening | 230.35 s | 125.59 s |
| Native DRC after refusal | 0 | 3 inherited |
| Native opens after refill | 254 | 224 |

In the earlier 12VHPWR transition test, skipping wasted return-field work raised
source-side checked candidates from 174 to 551 in approximately the same
21-second screen allocation. That is increased local search throughput, not
whole-board routing improvement. The fair scheduler subsequently spent that
budget on all four domains instead of only the first empty source domain.
It discovered opposite-polarity endpoint beams and exercised shared-middle
attempts on a USB leg that the former schedule had not reached. The complete
pair still failed; this is not a connectivity or fabrication success claim.

Evidence:

- `build/transition-field-work-native-20260913/`
- `build/fair-domain-native-20260913/`
- `build/fair-domain-native-proof-20260913/report.json`

## Rejected experiment

A read-only PCIe 2-port experiment broadened native/manifold attachment-point
sampling within the exact free-space intersection. The same two current
corridors remained refused. Broad manifold sampling increased the measured
planner run from about 9.7 to 20.0 seconds without eliminating either failure.
It was **not integrated** into production. The fixed-terminal obstruction
certificate must not be dismissed as an endpoint-sampling artifact on this
evidence. This experiment does not prove global geometric infeasibility.

Evidence: `build/native-attach-20260913/`. No generated copper from this
experiment was published as a board candidate.

Four further disposable PCIe trials translated one complete mating-terminal
group by -4, -2, +2 and +4 mm, retaining its internal pitch, pinout, outline and
all existing copper. Both current-corridor failures remained. These explicit
unadmitted interface-ECO copies were not supplied to the production suite and
do not authorize an anchor change. Evidence:
`build/macro-current-probes-20260913/`.

## Regression

- 1,224 tests passed, 3 skipped, 10 subtests, one existing SWIG deprecation
  warning: `build/fair-domain-full-tests-20260913.log`.
- New synthetic scheduling tests cover a blocked first polarity, a viable
  alternate, finite-domain exhaustion, no-progress round limits, increasing
  retry budgets, invalid policy, native resumptions without completed-query
  replay, and preservation of all parent copper after failure.
- New transition tests require both signal witnesses, skip reference work
  only when a signal barrel fails, and preserve mandatory return admission.
- The additional preflight/evidence batch passed 38 tests:
  `build/fair-domain-preflight-tests-20260913.log`.
- All four protected PCIe control probes exactly equal
  `build/package-ranked-final-control-20260913.json`; fresh report:
  `build/fair-domain-control-20260913.json`. Its zero DRC/zero opens remain
  unchanged, as do its pre-existing broader release failures.

## Full-suite replay

`build/fair-domain-suite-20260913/` completed at 23:00:43 UTC on September 13,
2026. It exercised the six current BETA main boards from explicit retained
artifacts, with four board workers, 24 craft trials, four requested route
passes and 1,800-second job caps. All six receipts confirm unchanged source
boards, source inputs and engine signatures. None passed placement admission
to general routing. Requested route passes are not executed passes when an
earlier gate refuses admission.

| Board | Job time | Remaining admission blocker | Retained result |
| --- | ---: | --- | --- |
| 12VHPWR | 794.44 s | External CAN and USB pair qualification | Existing CAN-internal prefix preserved; two critical-only waves failed pair connectivity/physics; no new qualified copper |
| Hub | 574.64 s | CAN/USB qualification and two critical reachability edges | No accepted placement move or new qualified routing |
| PCIe 2-port candidate | 281.05 s | Two current-corridor failures, C1 HI/LO | No accepted craft repair; protected control is a separate artifact |
| PCIe 3-port candidate | 1,049.97 s | Three current-corridor failures, C1 HI/LO and C3 LO | Two fiducials relocated; no current-corridor closure |
| EPS rev3 | 12.74 s | Fixed terminal contact shorts | Early refusal; no new placement output |
| ATX 24-pin rev3 | 12.84 s | Fixed terminal contact shorts/clearance | Early refusal; no new placement output |

PCIe 3-port's second craft search followed an actual fiducial relocation and
changed PCB digest, not a retry against identical input. Its retained placement
digest is `5bced8c39f6d73b56330a5367cef27b5bd6d97d0c988fa38df01d72a94476ab9`.
Both 24-trial searches failed to improve the current-corridor gate. Internal
legal/rejection event counts include subsidiary trials and must not be treated
as mutually exclusive counts of the 24 selected top-level moves.

EPS and ATX remain blocked by native shorts between fixed terminal contacts.
The existing daughterboard span/width constraints remain unchanged. Resolving
those interfaces requires joint main/daughterboard geometry, not routing
around the short or shrinking vendor pads. An owner choice about allowing a
minimal verified joint-interface increase is pending. This document does not
claim all boards are route-ready or that any placement is a final fab candidate.

The 12VHPWR wave's actual immutable parent was rendered while it was routing and opened in
the desktop. Its image carries both the source digest and **critical-only
routing input, not final placement** status. It is not a substituted routed
board or a claim that residual routing passed:
`C:/Users/Admin/Documents/CEC-Board-Reviews/fair-domain-suite-20260913/12vhpwr-critical-entry-1b1da8a82c38.png`.

The completed review gallery is
`C:/Users/Admin/Documents/CEC-Board-Reviews/fair-domain-suite-20260913/all-boards-8564dd3af331292f.png`.
It shows four current blocked placements and explicit no-output cards for
EPS/ATX, without substituting older boards. All six corresponding dashboard
render endpoints returned HTTP 200 with nonempty PNG responses from Windows
after completion. These are review evidence, not final placements or fab signoff.

## Next decision and work

No unchanged-input campaign is left running. EPS/ATX require a joint mating
geometry decision: retain the existing hard span/width limits and investigate
another qualified arrangement/part, or authorize the smallest verified joint
interface increase. Sampled clear contact spacings need approximately 1.4 mm
and 2.2 mm more datum span, respectively, before additional margin and complete
fit/keying checks; these numbers are not a proven minimum board-width increase.
No expansion, pinout change, vendor-pad shrink or copper-short waiver was made.

The remaining software work is construction-aware placement for exact pair
escape obstructions and coordinated current-corridor placement. The completed
experiments do not establish that these boards are globally unroutable, nor
that larger time budgets alone would solve them.
