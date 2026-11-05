# Joint power-transition search: H completion and bounded follow-up

## Accepted board, not a proposal

H's exact completion event was delivered and acknowledged. The service is no
longer running; the periodic heartbeat remains paused. H retained an actual
improvement from 371 to 366 opens, with unchanged five scorer-filtered
structural findings and two route-quality blockers. The 78 by 95 mm board,
paired authority, and existing protected copper were not changed. See
`docs/atx-event-driven-waves-2026-09-28.md` for its invocation and dashboard.

The retained ATX board is:

`build/event-driven-atx-20260928-h/atx-24pin-rev3/02-placement/board.kicad_pcb`

SHA256: `a953564dd236bde8b5b503aee7cf110abce0d07c5b362b342911716569a854f0`.

H is still placement-craft blocked, not signal-routed or fabrication-ready.
Three constructed/preserved rail objects do not certify full input-current
coverage, thermal performance or complete decoupling/ground returns.

## Measured causal chain and generic changes

1. **Footprint metadata parsing.** The fresh generator deleted entire lines
   while removing version/generator fields. The current slim M2 footprint
   puts its root layer on the same line, so generation failed before any rail
   construction. Root children are now located with the quote-aware balanced
   form reader. Only root metadata/old pose/UUID are removed. Exactly one root
   layer is required; the requested pose is inserted regardless of whitespace
   or child order. Nested pad/property geometry stays intact. The library was
   not reformatted to accommodate a brittle parser.

2. **No room versus inadequate search.** Native pad shapes still found at
   most three sites in H's original six-via transition portfolio; retained
   power tracks blocked most alternatives. Replacing pad circles alone was
   not a supported explanation for this plateau. The transition generator
   now optionally extends beyond the short pad neck at the full body width,
   with finite proposal and length bounds. Production uses two field-grid
   pitches (1.3/2.6 mm), retaining all widths and required vias. Shortening and
   extension families are interleaved so a time limit cannot systematically
   starve the new topology. The original short-neck length is not increased.

3. **Field-only refusal dispatch.** Previously, a clear primary conductor
   whose via field failed never invoked transition repair. It now enters the
   same bounded search as a colliding conductor. The combined time budget,
   native geometry, return-portal and protected-copper checks are unchanged.

4. **A clipped central site poisoned every compact subset.** The extended
   ATX proposal found seven barrel-clear sites for six required vias. Every
   compact subset selected a central site whose complete land was clipped by
   the conservative pour exclusions, while omitting a farther usable site.
   A necessary per-site landing screen now eliminates such sites *before*
   bounded subset selection. The whole-field connected-polygon/primary-path
   test and native filled-copper audit remain mandatory. The test does not
   reduce the via count, change clearances or substitute drawn copper for
   actual copper. The measured source field then admitted all six sites in
   the construction preview; this alone is not native board admission.

5. **Premature sink-array rejection.** Source planning tried the sink's
   original virtual array and refused the whole rail before the sink's own
   layer/face/transition portfolio could run. Sink fields are now evaluated
   against their actual proposed conductor, with proposed source copper and
   vias treated as foreign pending obstacles. Both sides are qualified before
   any native rail copper is committed. A field-only sink failure can also
   request transition repair.

6. **Actionable landing evidence.** Bounded diagnostics distinguish clipped
   lands, a split field, and a complete field disconnected from its primary
   conductor. They record the actual failing layer, required count, uncovered
   sites and up to four examples per filter. Evidence never grants admission.

No board/refdes/coordinate exception, changed load budget, narrower current
path, moved protected conductor, larger outline, or mating-interface change
was added. The shared core audit passes; 378 pre-existing legacy runtime
findings remain, so this is not a claim that the entire old pipeline is generic.

## Replays and honest stopping point

- `build/event-driven-atx-20260928-fullwidth-transition-probe`: 31.505 s,
  no gain, retained H. The field-only dispatch gap was still present.
- `build/event-driven-atx-20260928-fullwidth-transition-probe-v2`: 32.711 s,
  no gain, retained H. Field-family starvation and clipped-site subset
  selection were then investigated using disposable in-memory construction.
- `build/event-driven-atx-20260928-fullwidth-construction-forensic-v3`:
  seven barrel-clear sites, repeated `field_land_clipped` refusals. This
  separated land clipping from a lack of barrel capacity.
- `build/event-driven-atx-20260928-fullwidth-construction-forensic-v4`:
  six fully preview-usable source lands after prefiltering. It exposed the
  premature sink-array refusal. No native board was saved by these helpers.
- `build/event-driven-atx-20260928-fullwidth-transition-probe-v3`: 71.301 s,
  108 generated generic proposals, eight selected/tried, seven geometrically
  legal, zero monotonic craft improvements. One trial introduced overlap.
  The bounded trial budget was exhausted. Its output is byte-for-byte H.

The latest replay reaches the sink instead of stopping at the original
source field. Its principal layer is obstructed by retained standby copper;
other-layer routes encounter retained 5 V/3.3 V copper. A face alternative
exposes a movable button obstruction through the generic witness adapter,
but the eight tested moves did not produce an admissible complete rail.
This is a finite sampled result, **not a proof of geometric infeasibility**.

No I wave was launched: there is no newly admitted native gain to justify a
full identical replay. The next useful slice is joint source/sink topology
and reservation planning with complete-field feasibility, preserving the
incumbent and every final admission gate. Do not promote an isolated source
field, waive sink construction, or silently renegotiate protected buses.

## Validation scope

Focused parser tests passed 17 cases including a real current slim M2 mount,
shared-line metadata, reordered fields, CRLF/spaces/tabs, nested/quoted
parentheses, native pose/flip, and malformed/missing/duplicate root layers.
The first test draft incorrectly compared CRLF through universal-newline
reads and expected unrotated pad angles; those fixture assertions were fixed
and rerun. They were test defects, not ignored production failures.

The original broad legacy fresh-board test
`test_rail_walk_floor.py::TestEndToEndPitch::test_seg4_seed_pitches_and_refusal_classes`
advanced beyond its former parser exception into expensive placement search.
That combined diagnostic invocation was interrupted after 653.18 seconds;
the legacy end-to-end test remains **unverified**, not passed. Its earlier
fixture failures do not describe the final corrected focused tests.

Before the final joint-sink change, the resumed-path selection passed 483
tests and two subtests. The final focused rail/transition/landing selection
passed 75 tests and two subtests.

The final combined selection completed: **496 passed, one skipped and two
subtests passed in 114.02 seconds**. It includes the resumed-path regression,
parser fixtures, native flip tests and rail-walk floor derivation, but not
the interrupted legacy end-to-end fresh-generation test. Its log is
`/tmp/cec-h-final-slice-tests.log`. Changed-file whitespace checks passed.

Fresh immutable PCIe2 v103 control:
`build/event-driven-atx-20260928-joint-transition-pcie-control/control.json`.
It remains at zero scored structural DRC, zero opens, zero route-quality
blockers and zero non-octilinear routes; source bytes unchanged. SHA256:
`2f09d2765bacc5281a52fc7b6afaafa06078fb3aa1c1c2be037b708edd059388`.

Hub incumbent and active pair hashes are unchanged:

- Hub: `166b9b63d88fb7b06e6710d76f08157d3412e7bea8139992fd60d9d9a1277a87`.
- Active pair: `dfbeccb8eca4331c53c92c95b77d82dea03d4d8f396effda2860ca1d99882463`.

The custom completion listener already delivered H's event. It is not an
active recurring monitor and there is no new wave to watch. Do not resend H,
G or the previously observed acknowledgement-uncertain F event. Keep periodic
monitoring paused; the next justified pass can receive a new exact-invocation
one-shot listener while the PC, WSL and app remain running.
