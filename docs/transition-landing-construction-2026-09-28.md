# Complete transition landings, 2026-09-28

## D outcome: rejection correctly retained the incumbent

Wave D completed in 468.193 seconds. Its callback was acknowledged once at
19:47:07.944 UTC. The board job exited 2 (placement blocked), although the
suite service completed successfully. Two proposed craft changes were rolled
back by the composed acceptance guard: `no_pareto_craft_improvement` and
`native_copper_regression`. The final PCB is byte-identical to B:
`c7ce02137aecaf7c937d3365638754d667d8dcd7741b842d49ddbf8354d09035`.

D is not accepted routing progress. It still has 377 unconnected items,
5 scorer structural routing findings, and 0 immediate return-access failures.
The dashboard shows that exact retained artifact, not the rejected proposal:
`pass-event-driven-atx-20260928-d-atx-24pin-rev3-36710239b9`.

## Proven constructor causes and reusable repairs

The private trace in `build/event-driven-atx-20260928-array-forensic/probe.json`
proves that `_commit_array` suppressed both front landings while emitting all
20 required barrels. It tested a rectangular patch as a round-ended thick
segment, exaggerating the end clearance envelope. The source rectangle was
actually clear. The sink rectangle needs native clipping around foreign pads;
its legal vias survive that clipping. The old alternate tag also checked an
escape-layer patch against the primary alternate layer instead of its actual
layer.

`cec_transition_landings` now declares both actual layers unconditionally and
uses the shared native pour policy/filler. It reuses the existing complete-land
checker against **actual filled polygons**, with holes retained, verifies each
required barrel's dimensions and layer span, and proves the entire field joins
a primary same-net conductor on each layer. Missing, clipped, wrong-layer,
wrong-net, unfilled and ablated landings fail closed. Neither materializer path
may swallow that failure and save/report successfully constructed rails. The
central shunt/top-copper restriction remains in force; no exemption was added.
Integer-nanometre via positions now round rather than truncate floating-point
arithmetic.

`cec_parallel_copper` screens optional mirror proposals before emission. It
normalizes overlapping collinear runs at their existing endpoints, retaining
the widest proposed copper, prunes unanchored leaves and rejects components
without two primary contacts. The trace exposed two overlapping pickup drops
that falsely supported one another's free end after a different dangling
mirror was excluded. The normalized candidate now retains the actual
pad-to-pad mirror and emits no free-ended extension. No existing protected
copper, required vias or required current widths were removed or reduced.

Both new modules are registered in the product-neutral core audit. They have
no board/refdes/net-name/coordinate selectors. The broader inherited runtime
inventory remains 378 findings; this is not a claim that all legacy code is
generic or defect-free.

## Real-board diagnostic result, not an accepted release

`build/event-driven-atx-20260928-array-native-v4` is a private construction replay
from B, not a promoted candidate. Both fields retain all 10 required vias, with
verified F.Cu/In3.Cu and F.Cu/In2.Cu native landings respectively.

| Measurement | Retained B/D | Private repaired constructor |
| --- | ---: | ---: |
| Constructed rail objects, not qualified current paths | 1/4 | 2/4 |
| Unconnected items | 377 | 371 |
| Scorer structural routing findings | 5 | 5 |
| Route-quality blocking findings | 2 | 2 |
| Non-octilinear findings | 0 | 0 |
| Immediate return-access failures | 0 | 2 |

The protected copper-prefix check passes, and source and diagnostic board
hashes were unchanged by measurement. Board outline and poses were not moved.
The rail is still only partially picked up (2/4 input pads): landing continuity
does not establish full current sharing, effective cross-section or thermal
qualification. The new inner rail still obstructs two immediate ground-return
accesses. That is an active, unwaived blocker; these six fewer opens alone do
not justify retaining the candidate.

The next bounded suite pass tests this different constructor through the full
materializer and craft-search/commit boundary. If it plateaus or is refused
again, do not repeat/enlarge the same portfolio. The next causal slice is
preservation/co-planning of measured immediate return access during rail
construction, with explicit prefix ownership; do not hand-move particular
capacitors or narrow/delete the approved power paths.

Evidence:

- `build/event-driven-atx-20260928-d/suite.json` and its
  `02-placement/board.placement.json` reconstruction receipt.
- `build/event-driven-atx-20260928-array-native-v4/probe.json`,
  `craft-summary.json` and `craft-evidence.json`.
- `build/event-driven-atx-20260928-array-native-v4-score/control.json`.
- `build/event-driven-atx-20260928-landing-control/control.json`: immutable
  PCIe2 v103 remains 0 structural DRC / 0 opens / 0 route-quality blockers /
  0 non-octilinear, SHA
  `2f09d2765bacc5281a52fc7b6afaafa06078fb3aa1c1c2be037b708edd059388`.

Hub and pairing authority hashes remain unchanged. No fab release is claimed.

## Regression evidence

Final combined run: **364 passed**, one Shapely deprecation warning, 140.23 s.
It includes transition/mirror fixtures, existing rail/detour/bridge tests,
composed craft commit, full pipeline, frozen rematerialization, materialized
policy seal, protected prefixes, native stage admission, evidence identity,
the one-shot service watcher, over-under generation, frozen-via replay and
pour termination. The two new modules contribute translated/actual-layer and
endpoint-reversal cases, native omission/clipping/hole/wrong-net/wrong-layer
failures, no-save materializer rollback, and overlapping mirror normalization.
`py_compile` and scoped `git diff --check` passed.

Local test transcript: `/tmp/cec-landing-final-tests.log` (ephemeral; this
document preserves the result). Native control/replay evidence is under the
build directories listed above. There is no board-specific repair rule.
