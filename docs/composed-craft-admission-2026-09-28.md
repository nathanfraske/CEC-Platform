# Composed craft acceptance and event pass C, 2026-09-28

## Actual C outcome: mixed, not an incumbent promotion

C completed in 211.543 seconds. Its completion callback was delivered once
at 19:27:42.788 UTC. Source PCB, source inputs and engine were unchanged
during the run. Source intake and paired-interface compilation passed;
placement remained blocked. No detailed signal routing or release occurred.

| Measurement | B retained incumbent | C unadmitted experiment |
| --- | ---: | ---: |
| Constructor rails (not qualified power paths) | 1/4 | 2/4 |
| Unconnected items | 377 | 371 |
| Scorer structural routing findings | 5 | 8 |
| Immediate decoupling return-access failures | 0 | 2 |
| Native pad/assembly/edge placement conflicts | 0 | 0 |

The 38 protected +5 V copper primitives remained unchanged. C's extra rail
is still incomplete (reported pin pickup 2/4) and is not current/thermal
qualification. Its SHA is
`6cc88570fdd51a5a69ae15e0fdafb3e4bf9a66509976cb6cdba2d41f329619df`.
Keep C for forensic review, not as the next accepted incumbent.

The structural count is explicitly the scorer's filtered category, not all
native warnings/errors. C's raw KiCad report has 563 violation rows (6 error,
557 warning), plus 371 unconnected rows. Categories include 4 hole-clearance
rows, 2 items-not-allowed rows, 129 library issues, 422 silk findings, 3
dangling tracks and 3 dangling vias. No broader fabrication pass is claimed.

Evidence:

- `build/event-driven-atx-20260928-b-native-score/control.json`
- `build/event-driven-atx-20260928-c-native-score/control.json`
- `build/event-driven-atx-20260928-c-native-score/native-drc.json`
- `build/event-driven-atx-20260928-composed-replay/replay.json`
- Dashboard: `pass-event-driven-atx-20260928-c-atx-24pin-rev3-2c8335a935`
  (actual PNG endpoint verified HTTP 200).

## Why this passed the search but did not qualify

Fresh baseline evidence worked: both rounds measured the reconstructed board,
not B's stale report. However, the reconstruction-only guard was entered only
when no pose change was accepted. Two small decoupler proposals improved the
already-rebuilt baseline's local score and caused the ordinary placement
commit path to bypass the new composed guard. The high-priority rail term also
outranked new return-access failures in the search's lexicographic key.

Search candidates may be exploratory; publication as retained progress may
not use a different, weaker acceptance path. The same transactional composed
guard now runs for normal, frozen and post-fiducial resumed craft commits,
including candidates with pose changes. It checks the actual pre-rebuild
incumbent against the final rebuilt artifact. Native copper/DRC/connectivity,
source intake, protected power, frozen authority and active craft terms
cannot regress. Ordinary clean-placement polish can still improve a tie-break
without changing active defects. A source board is not silently overwritten
when these checks reject a proposal.

For a movable candidate, the immutable-domain hash uses native pad-relative
geometry and separately proves every final footprint pose against the
candidate. Sides, component population, pad/net geometry, copper layer count
and complete outline/cutout contours remain immutable in this craft scope.
No board/refdes/net-name/coordinate exceptions or relaxed rules were added.

## Validation and next boundary

- 117 reconstruction/full-pipeline tests passed (32 focused reconstruction
  cases), plus 64 identity/prefix/frozen-policy/admission/event tests.
- Real read-only B-to-C replay now rejects C for both non-Pareto craft
  regression and new native DRC identities. Neither archived board changed.
- Immutable PCIe2 v103 replay remains 0 structural DRC / 0 opens /
  0 route-blocking / 0 non-octilinear, with identical source SHA.
- Generic-core audit passes; the broader inherited inventory remains 378
  findings. This is not a claim that the entire legacy runtime is clean.

The remaining constructor issues need real geometry work, not more identical
waves. C added two dangling 3.3 V array vias and a dangling mirrored track;
its new inner rail also blocks two immediate ground returns. Investigate
landing-patch coverage/fill on both actual transition layers, optional patch
emission in `_commit_array`, the materializer's landing-zone filters, and
preservation of validated local return access during rail generation. These
are hypotheses for the causal construction repair, not permission to delete
vias, narrow current paths or move protected buses arbitrarily.

Pass D starts from B, not C, and tests the corrected commit boundary with 32
trials per round (two rounds, one epoch) inside the same finite 900-second
board budget. If it only reconfirms this refusal, do not repeat it: implement
and test the evidenced constructor/return-access fix before another wave.
