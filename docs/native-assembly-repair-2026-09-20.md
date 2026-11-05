# Native assembly truth through placement repair — 2026-09-20

**Continuation:** [ATX/Hub dimensions and ordinary corridor feedback](atx-hub-size-and-ordinary-relief-2026-09-20.md)
implements the next feedback slice and records actual paired-stack access
failures. Use `build/ordinary-relief-next-inputs-20260920.json`; PCB selections
are unchanged. The missing-feedback section below describes the pre-fix state.

## Result and current continuation authority

The generic repair boundary now preserves native assembly findings as well as
pad copper and edge findings. A repeat of the EPS compaction keeps a clean
**88 × 40 mm** candidate instead of moving a component into a real collision.
This replaces the deliberately retained 92 × 40 mm seed, reducing area by
4.35%. The ATX developed placement remains **82 × 95 mm**. Neither board is
routing-admitted or a fab candidate.

Use **`build/native-assembly-next-inputs-20260920.json`**. It explicitly retains
the completed, hash-verified EPS and ATX outputs and preserves the other four
board inputs. It is not automatically launch- or release-authorized: another
unchanged wave will not resolve the remaining corridor and return-path defects.
No BETA source CAD, schematic, mating pitch, daughter outline, current budget,
or acceptance threshold was changed by this slice.

## Forensic correction: not a bad initial size choice

The previous EPS replacement evaluated both 88 × 40 and 92 × 40 mm as native
assembly/pad-copper/edge clean. Selecting the smaller legal candidate was correct.
A later repair treated an axis-aligned bounding-box overlap between J1 and U3
as a real collision. That envelope included empty space. The repair shifted
U3 upward by 0.41 mm into C2, creating one real native courtyard violation.

The proxy overlap count remained one, and its electrical objective improved.
The native regression projection only included pad-copper and pad-edge faults,
so it could not veto the newly introduced assembly fault. The size-ranking
hypothesis in the preceding handoff was therefore incomplete: the defect was
the mismatch between the repair's search proxy and its missing native assembly
acceptance coverage.

## Generalized changes

- `cec_placement_geometry.classify_drc` resolves assembly owners from native
  footprint/pad UUIDs, not localized descriptions.
- Version 2 craft geometry evidence declares assembly/pad-copper/pad-edge
  coverage. Missing assembly identities fail closed. Legacy pad-only evidence
  is not silently interpreted as an assembly-clean measurement.
- Repair scoring, incumbent certification, final scoring, and blocker dispatch
  use native assembly pairs when coverage is available. AABB overlaps remain
  conservative search prefilters, explicitly documented as proxies.
- Trial acceptance rejects newly introduced native fault identities, including
  a same-count swap from one collision to another. It is not only a total-count
  comparison. Ordinary, atomic, compound, and subsequent-generation evaluation
  paths consume this evidence.
- Repair rounds record proxy-only pairs and bounded samples of native-fault
  rejections, including the proposed move and native member evidence.

These changes contain no board/refdes/coordinate-specific repair rule. The
references above describe the forensic example only. Conservative proposal
prefilters can still reject legal moves; this slice does not claim to solve
all search completeness or runtime specialization issues.

## Verification

- **452 passing tests:** 52 native geometry/assembly/pad-edge tests and 400
  placement admission, evidence identity, checkpoint, commit, dependency,
  full-pipeline and generalization boundary tests. One pcbnew deprecation
  warning; no test failures.
- Synthetic regressions cover concave-courtyard empty space, a real neighboring
  collision, opposite PCB faces, UUID ownership, legacy coverage, missing
  identity, clean-to-collision regression and same-count fault replacement.
- Six current selected inputs replay native assembly/pad-copper/pad-edge clean,
  with source and hierarchy hashes unchanged. This is a physical replay, not
  six full routing/fabrication qualifications.
- The historical routed PCIe two-port control preserves its exact board hash,
  board-regression results and probe results. Its pre-existing sideways-Kelvin
  qualification defect remains visible, not waived.
- The previous bad EPS trial is now explicitly rejected for the C2/U3 native
  assembly conflict.

Evidence:

- `build/native-assembly-repair-tests-20260920.xml`
- `build/native-assembly-boundary-tests-20260920.xml`
- `build/native-assembly-crossboard-20260920/report.json`
- `build/native-assembly-final-review-20260920/report.json`

## Completed bounded production passes

| Pass | Result | Native assembly / pad copper / pad edge | Routing admission |
| --- | --- | --- | --- |
| EPS same-input replacement replay | Clean 88 × 40 mm retained; 112.94 s | 0 / 0 / 0 | Blocked: three power corridors |
| ATX developed-placement continuation | One bounded decoupler adjustment; 277.66 s | 0 / 0 / 0 | Blocked: same three craft blockers |

The EPS replay reports native overlap zero and proxy overlap one (J1/U3),
generates no bogus separation move, and preserves the legal compact placement.
An additional 92 mm continuation completed in 72.74 s but performed different
work; it is not a like-for-like compaction speed comparison. The previous
same-input compaction took approximately 244 s; this one replay is not a broad
performance benchmark.

ATX's accepted incremental decoupler move improves one aggregate ground-distance
objective from 12.08 to 12.05 mm. It **does not close a blocker**. Final admission
still reports exhausted local ground-return access at U6.1 and U3.6, and the
U4.5 complete-loop proximity excess of 0.26 mm against the unchanged 0.25 mm
limit. The intermediate certificate has four decoupler findings; do not count
them as four additional independent final admission blockers.

Both passes used the existing eight-trial, two-round bounded repair regime,
three workers per board and 480-second job deadline. Engine/source hashes
remained stable. Final published outputs were independently native-rechecked.
No repetitive wave remains running.

## Next causal repair: ordinary-layer corridor feedback is missing

EPS still fails `/SENSEC1_LO`, `/SENSEC2_HI`, and `/SENSEC2_LO`. These net names
refer to declared high-current paths in this design; do not weaken their widths
or neck constraints based on the word `SENSE`.

Its reports name blocked endpoints, no-path layers, and overlong necks, but
all three have `planner_bottleneck.relief = {}`. The repair dispatcher selects
`power_corridor_access` and then generates zero proposals.

Code inspection localizes a coverage gap: `_make_candidates` invokes
`_corridor_relief_evidence` on bundle path failure, but ordinary per-layer
path/neck failures continue without recording equivalent relief evidence.
The existing placement repair consumes those relief maps, so it has no named
obstacle/path witness to act on. This gap is diagnosed, **not implemented by
this slice**.

The next change should share bounded failure diagnosis across both planner
branches, preserving fixed mechanical owners, reserved copper, layer-specific
allowed regions, full current width and neck acceptance. Counterfactual removal
is diagnostic only: it must never delete protected objects or qualify copper.
Add ordinary-layer synthetic tests (including fixed/unattributed blockers,
disabled/light diagnosis, allowed-region and neck constraints), then replay
the EPS output and the routed PCIe control before another placement wave.
ATX needs a separate generic local-ground-return search/proposal improvement.

## Fresh review views

These are completed **placement** outputs, not routed boards. Both dashboard
image endpoints returned HTTP 200 with `image/png` from Windows, and the native
renders were visually inspected. No old-board fallback was used.

- [EPS 88 mm placement](http://localhost:8090/?id=pass-native-assembly-eps-compaction-20260920-eps-8pin-rev3-8689f09637)
- [ATX placement](http://localhost:8090/?id=pass-native-assembly-placement-pass-20260920-atx-24pin-rev3-c549511679)
- Immutable combined image: `build/native-assembly-final-review-20260920/retained-mains-9b0291f2bc9e80f8.png`.

The paired daughterboards' prior remaining thermal, measured-fit, physical-key,
library and cosmetic qualification work is unchanged. The absent ATX J3 STEP
model still prevents claiming complete modeled plug/latch/stack clearance.
