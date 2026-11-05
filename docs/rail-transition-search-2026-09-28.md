# Shared-rail transition search and layer-identity repair

## F accepted construction progress, not routing admission

F ran from the retained B suite in 234.815 seconds. Source board, input
families and engine were unchanged throughout. Hierarchical BETA source
intake and the paired interface both passed. Placement remains blocked;
there is no routing or fabrication admission.

Unlike D/E, F's composed reconstruction commit was accepted. The craft key
improved from `[3,0,0,0,0,0,0,0,0,0,0]` to
`[2,0,0,0,0,0,0,0,0,0,0]`. Native opens fell from 377 to 371 with the same
five scorer-filtered structural identities, no new foreign-pour incursions,
and the locked prefix intact. The retained PCB SHA is
`9181a3a43781b69cf20e3688ba17e1f90b772b23f90f5455cb0b13d81d75a016`.
It has two of four constructed rail objects, not four qualified current paths.
The added rail still lacks two input pickups. Do not equate a constructed
rail object with complete electrical, current or thermal qualification.

F's exact dashboard ID is
`pass-event-driven-atx-20260928-f-atx-24pin-rev3-5c7e0fce7f`. Its model-free
render was visually inspected and its image endpoint returned HTTP 200,
image/png, 65,932 bytes. The matching view was queued in this task's panel.

The custom callback reached this task. Its acknowledgement timed out, leaving
the Windows delivery receipt `delivery_unknown` at
`2026-09-28T20:43:40.641Z`. Receipt uncertainty did not mean non-delivery:
this continuation is direct evidence it arrived. Do not resend that event or
reuse its one-shot claim. The old periodic heartbeat remains paused.

## Causal fixes in this slice

### Uncommitted transition search

The constructor treated its generated face-to-inner via-field center as an
immutable physical contact. A pad-to-field stub could end under an unrelated
button pad; every layer retry kept the same blocked face endpoint.

`cec_rail_transition_search.candidates` proposes only a virtual degree-two
transition next to a declared physical contact. It retains every real contact,
width and layer tag, rotates at 45-degree increments, and never lengthens the
face neck. Branched or already physical/via-in-pad vertices do not move.
The finite proposal limit is 24. Required barrel counts are never reduced.
The force-rail adapter applies a two-second per-rail transition-search budget
and shares it across alternative layers rather than starving later layers.

Actual source/sink collision, complete via capacity, measured future returns,
and foreign pending source copper constrain the candidates. Native landing
fill and final composed DRC remain mandatory; an internally selected proposal
is not a board-level acceptance.

### Connected via-field pre-screen

Two individually clear barrels are not necessarily one usable landing field.
The first ATX diagnostic selected source barrels on opposite sides of an
obstruction. The native complete-field check correctly refused the result.

The constructor now tests at most 26 deterministic compact subsets of its
existing 25 legal candidate sites, without deleting required barrels or
changing diameter/drill. `cec_transition_landings.proposal_filter` rejects
fields whose conservatively clipped declarations cannot contain every full
landing and connect the entire field to the actual primary on both layers.
This is a necessary pre-screen, not a replacement for actual native filling.

### Actual-trunk pickup reattachment

A band narrowed on one layer was still excluding contacts after a different
layer's source path had been selected. Unresolved physical contacts now get
a bounded search to center-line targets on the actual selected trunk. The
declared pickup width is retained, and SMD contacts cannot silently attach
to an inner layer. A native synthetic layer-switch fixture now picks up both
contacts at the unchanged 1.4 mm width. ATX's remaining pickup escape is not
claimed solved by this fixture.

### Native layer identity, not display text

A diagnostic exposed a real crossing between new and retained power copper.
Retained In3.Cu was named `PWR`. The constructor indexed that display name
but compared it with the configured `In3.Cu` alias/relative `alt` tag, so it
missed that both tracks occupied the same layer. Native DRC caught the short.

Existing and newly emitted tracks are now indexed with actual board layer
names and compared through the board's native layer IDs. A renamed-layer
synthetic regression verifies that a locked foreign track cannot disappear
from collision detection. No electrical clearance or DRC rule was relaxed.

## Private replay disposition

`build/event-driven-atx-20260928-transition-probe-v3` was NOT accepted:
367 opens came with six structural findings (one new same-layer short) and
four route-quality findings. The landing check passed but was not sufficient.
This is why the final composed native guard is retained.

After fixing the layer identity, private v4 and v5 correctly refuse that
construction and retain F byte-for-byte. The v4 native replay is five
structural findings, 371 opens and two route-quality findings; v5's PCB has
the identical SHA above. The 97-item captured power prefix remains intact.
These safety fixes do not constitute further accepted ATX routing progress.

Evidence:

- `build/event-driven-atx-20260928-f/atx-24pin-rev3/02-placement/board.placement.json`
- `build/event-driven-atx-20260928-transition-probe-v3/native-drc.json`
- `build/event-driven-atx-20260928-transition-probe-v4-score/control.json`
- `build/event-driven-atx-20260928-transition-probe-v4/craft-summary.json`
- `build/event-driven-atx-20260928-transition-probe-v5/probe.json`
- `build/event-driven-atx-20260928-transition-control/control.json`

The immutable PCIe2 v103 control was freshly replayed read-only: zero scored
structural DRC, zero opens, zero route blocking, zero non-octilinear; SHA
`2f09d2765bacc5281a52fc7b6afaafa06078fb3aa1c1c2be037b708edd059388` unchanged.
The generic-core audit passes with legacy runtime findings unchanged at 378.
The new transition module is registered in the audited generic core. No
whole-legacy-pipeline genericity or new manufacturing release is claimed.

Focused validation currently passed 81 tests and two subtests. Fixtures cover
rotation/translation, fixed contacts, branched nodes, bounded refusal, both
source and sink moves with native landing fill, connected-field screening,
future/pending reservations, actual-layer collision and changed-layer pickup.
Synthetic component obstacles have explicit local courtyards rather than
using a fixture footprint-origin-spanning fallback box. Scoped diff checks
passed. The broader regression completed with **422 passed, two subtests
passed, one pre-existing Shapely deprecation warning**, in 137.41 seconds.
It includes portal/landing/mirror/rail/detour/transition tests plus bridge
feedback, reconstruction, full pipeline, frozen rematerialization, policy
seals, route prefixes, stage admission, evidence identity, event listener,
retained runner, over-under, frozen-via replay and pour termination tests.

## Next bounded verification and remaining work

One G pass from F is an end-to-end safety/composition verification of the
changed constructor, not an expectation of automatic closure. It must not be
followed by an identical or enlarged plateau retry. If construction remains
blocked, inspect the actual failed transition/array/detour certificates and
the absence of placement proposals before another run.

The remaining limits include missing physical input coverage, conservative
pad/channel models, source escape around the retained rail prefix, and the
constructor's restricted band/transition topology. Diagnose these generically;
do not narrow current widths, invent budgets, move individual named parts,
grow the board, or relax the mating/power constraints to get a lower count.
Do not count partial rail objects as fully qualified power networks. Preserve
the 78 x 95 mm outline, current hierarchical source, Hub pair and PCIe2 control.
