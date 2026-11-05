# Paired bypass-link ownership and placement

Later correction: this V8 checkpoint inherited an input-bus detour from V6.
Use the corrected checkpoint documented in
`power-trunk-priority-preservation-2026-09-09.md` for subsequent work; retain V8
as historical evidence, not the next placement baseline.

## Scope

Continue the verified hierarchical 12VHPWR 58 x 72 mm candidate from
`build/12vhpwr-route-ready-v6-20260909`. No schematic, BOM, footprint library,
mechanical contract, canonical PCB or immutable PCIe control is edited.

## Root cause

The current CAN source declares an optional DNP four-terminal choke with two
populated zero-ohm links across its windings. The placer treated those links
as unrelated passives. Nearest-peer and courtyard checks did not constrain
both ends to the intended device, and the critical-follower checker returned
early when no critical-net selectors were configured.

The router independently paired split-member footprints using package and
distance heuristics. When the links were roughly 20 mm apart, that heuristic
did not even recognize their shared station. Thus the missing relationship
affected both placement and the routing feedback used to repair placement.

## Generic implementation

`cec_parallel_links` derives a group only when two source-populated, exact
zero-resistance links cover the four distinct one-pin nets of one unique
four-terminal device. It retains both pin-to-pin mappings. Shared-rail shapes,
nonzero parts, DNP links and ambiguous ownership do not become invented groups.
The discovery has an explicit pair-count budget and no board, reference,
net-name, part-number or coordinate selector.

The existing critical-follower gate now incorporates these source relationships
even without declared critical nets. Each link is graded against both real
owner lands. Missing pad geometry is an error, not a footprint-origin fallback.
Native placement records carry two extra courtyard-size fields; the evidence
boundary now normalizes these records to x/y/rotation before all follower
measurements, including the pre-existing declared-net checks.

Joint proposals use actual library courtyards, free-space contact sites, four
orthogonal rotations, and necessary pairwise support before domain truncation.
They leave the owner and fixed references untouched. Every proposed link must
satisfy the existing configurable follower-distance limit at both ends. The
default 5 mm locality limit is an optimization/admission contract, not a claim
of high-speed or EMC qualification. Native physical, electrical, priority-route
and release checks remain mandatory. Back-face joint reseating is currently
conservatively skipped by this proposal adapter.

Routing consumes the same topology primitive from native pad/net/assembly data.
It can now report a displaced split station to placement without a reference-
prefix assumption. Recognizing that station for feedback does not relax the
router's existing 8 mm split-terminal fanout bound or permit wide uncoupled
routes. Ordinary non-bypass split-terminal discovery remains unchanged.

Rejected candidate records now preserve the complete critical-follower and
required-mount evidence as well as the existing geometry/refusal records.

## Validation

- Pure and native regressions cover exact zero-value parsing, bare/boolean DNP
  flags, arbitrary reference/net names, ambiguous owners, shared rails, both
  pin mappings, missing physical pads, fixed members, joint placement, live
  versus saved-board pose formats, and far-away native station feedback.
- `build/parallel-links-final-suite-20260909.log`: 472 passed.
- `build/parallel-link-native-record-regression-20260909.log`: focused replay
  of the extended native-record assertion added after that suite.
- `build/parallel-link-crossboard-20260909.json`: source/native ownership agrees
  on 12VHPWR, the PCIe control and Hub. The latter two correctly derive no such
  group and have no new group violations. This is not a claim that every
  electrical or fabrication check on those boards passes.
- `build/parallel-links-final-pcie-regression-20260909.json`: immutable PCIe
  replay; its 0 DRC/0 opens geometry and existing broader blockers must remain
  equal to the prior control replay.

The first production replay (`v7`) refused all relevant candidates because the
new strict adapter unpacked the extended native pose records incorrectly.
Nothing was promoted. The reproducer is retained under
`build/parallel-link-native-refusal-20260909`; tuple normalization and a
live/saved-record equivalence regression fix that adapter error.

## Completed production replay

The corrected bounded replay is `build/12vhpwr-parallel-links-v8-20260909`.
It finished in 512.88 seconds with two accepted craft repairs. Extra priority
placement repair trials were set to zero; the exact priority-route probe still
ran. This avoids repeating a repair search after the targeted ownership slice
has been measured.

| Measurement | Input V6 | Output V8 |
| --- | ---: | ---: |
| Bypass-link center spacing | 19.467 mm | 2.580 mm |
| Worst link-to-owner pin distance | 19.046 mm | 3.964 mm |
| New paired-link locality violations | 2 | 0 |
| Priority-route refusals | 3 | 3 |
| Native DRC / unconnected | 12 / 246 | 12 / 246 |

The owner footprint did not move. The final changed poses are the joint link
group plus two 0.025 mm supply-cell adjustments. The placement craft and
mechanical/placement constraint gates pass. One existing local supply access
repair remains explicitly deferred to pre-route local interconnect; this is
not a claim that all decoupler interconnect is finished.

Routing admission remains **false**, and this checkpoint was not promoted:

- CAN internal: no layered paired junction for the choke station; the probe
  does not report a search-budget exhaustion.
- CAN external: no layered paired junction for the connector station; also
  not reported as a search-budget exhaustion.
- USB: the second protection-device flow-through leg exhausts the coupled
  route/portal deadline. That is a bounded-search failure, not proof that no
  legal route exists.

Thus this slice repairs missing placement ownership and produces substantially
better locality, but does **not** reduce the route refusal, DRC or open counts.
The next slice should inspect the shared paired-junction/flow-through access
generation and its failure witnesses, including the placer/router pair-name
recognition mismatch. It must not simply waive the refusal or increase runtime
without identifying which search state or obstacle is preventing progress.

`slice-closeout.json` verifies all 12 hierarchical source hashes, protected
control hashes, frozen anchors, and all 110 footprint pad/net/size identities.
The immutable PCIe replay has exactly the prior score and broader blocker list:
0 DRC, 0 opens, 615 tracks, 226 vias, 1242.073 mm, with its 8 existing broader
release blockers unchanged. The generic-core audit passes; the full runtime
still reports 380 legacy findings. This does not certify the entire existing
pipeline as fully generalized.

Final board SHA-256:
`c3fd785993bf06b8adb65f0170ae5f199d66a8e19dd2117c478a4f0ac080fe54`.
The reviewed no-body image is generated from a byte-identical snapshot under
`review-c3fd785993bf`; the dashboard artifact endpoint returned HTTP 200.
Completed `stage.json`, `slice-closeout.json`, `native-score.json` and the
snapshot's `review.json` retain the machine-readable evidence. Test counts and
the screenshot must not be used in place of their admission verdicts.
