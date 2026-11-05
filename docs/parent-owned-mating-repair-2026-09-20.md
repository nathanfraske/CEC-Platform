# Parent-owned mating repair and daughterboard rebuild — 2026-09-20

**Continuation update:** [native assembly repair](native-assembly-repair-2026-09-20.md)
supersedes the main-board input selection below. Use
`build/native-assembly-next-inputs-20260920.json`: a replay now retains native-clean
88 × 40 mm EPS and 82 × 95 mm ATX. The old EPS overlap came from a later repair,
not the initial size choice. Daughterboard publication and qualification limits
in this document remain unchanged.

## Current result and authority

The owner explicitly authorized changing daughterboards to match their main
boards. The previously compressed EPS/ATX main rows have now been restored to
their established pitch, and both mating daughterboards have been changed and
rebuilt. This is an actual BETA CAD repair, not only an improved failure gate.
No main-board outline was enlarged. Schematics, selected parts, power budgets,
and manufacturing qualification requirements were not relaxed.

**Current next-input plan: `build/parent-owned-next-inputs-20260920.json`.**
It supersedes `build/safe-edge-next-inputs-20260920.json`. It is hash-bound and
not launch-authorized: complete the named generic repairs before another wave.
No release approval or automatic promotion is granted by this handoff.

## Shared geometry and published source changes

| Mating family | Restored main row | Old daughter outline | New daughter outline |
| --- | --- | --- | --- |
| EPS | 7.75 mm pitch | 28 × 18.5 mm | 30.25 × 18.5 mm |
| ATX | 8.00 mm small-terminal pitch; original mixed end gaps | 54 × 21.3 mm | 59.8 × 21.3 mm |

The ATX 59.8 mm width preserves the established parent pattern and its signal
companion. The earlier 57.56 mm figure was a minimum repacked-row screening
result, not that restored pattern. Only the daughters' right edges were
extended; their depths and other edges were preserved. PCIe's 14 mm pattern
was not changed.

The native source-board pad-copper report counts fell from 32 to 0 on EPS and
56 to 0 on ATX. These are reported pairs, not counts of unique physical shorts.
ATX's source assembly count fell from 6 to 0. EPS retains three unrelated source
assembly findings, which are not present in the recovered developed layout.
The canonical ATX source staging cloud is not the review placement.

Publication manifests and recoverable backups:

- `build/parent-owned-mating-source-backup-20260920/publication.json`: four
  source geometry changes, both mains and both daughters.
- `build/daughter-rebuild-source-backup-20260920/publication.json`: the two
  daughterboard copper rebuilds, published after native DRC checks.
- `build/parent-owned-mating-20260920/report.json`: before/after geometry.
- `build/daughter-rebuild-production-20260920/report.json`: rebuilt copper,
  DRC evidence, hashes, publication, and fresh dashboard IDs.

## Reusable implementation changes

1. `cec_mating_rows.shared_row_datums` preserves declared parent pitches and
   refuses conflicting parents for one daughter. `align_row` can explicitly
   recover an authorized original span without treating a compressed current
   row as the immutable maximum. Main outline enlargement is not inferred.
2. `cec_interface_eco` supports outward-only rectangular daughter outline
   changes and group publication with source/candidate hash checks, backups,
   and all-target pending markers before replacement. Interrupted publication
   remains blocked instead of accepting a half-published mating pair.
3. `cec_interface_routes.resolve_constructor_geometry` resolves declared
   edge-relative and rotated footprint-local route/via anchors. Specific
   references and intended clearances live in interface data, not special cases
   in the generic helper.
4. Constructor stitching cleanup matches exact native-coordinate signatures,
   including net, width, drill, and layer span. It removes old owned stamps
   after contact movement without deleting nearby unknown or foreign copper.
5. Native-precision outline rounding prevents false geometry changes such as
   `59.849999999999994` versus `59.85` during repeated construction.

Real rebuilding exposed stale stitching at old contacts, signal trunks at an
old board edge, and a standby-power trunk at an old contact X coordinate.
The first probe versions failed native DRC. Fixing their construction ownership
and anchors produced the results below; those failed probes are not accepted
outputs. Final native DRC remains mandatory for authored trunks as well as
router-generated tails.

## Daughterboard electrical geometry results

| Rebuilt board | Hard DRC errors | Unconnected items | Warnings |
| --- | ---: | ---: | ---: |
| EPS daughter | 0 | 0 | 14 |
| ATX daughter | 0 | 0 | 30 |

EPS warnings are six library-footprint and eight silkscreen-over-copper
findings. ATX warnings are eight library-footprint, twenty silkscreen-over-copper,
and two dangling-track findings. These remain visible; they were not waived to
obtain zero hard errors. The publication certificates continue to invalidate
release/route authority pending the remaining qualification stages.

**Not yet qualified:** new electrothermal solves, measured screw-axis and
tolerance-stack fit, and a positive physical anti-mismatch key. The nominal
paired audit still reports `cross_family_fit_not_excluded` for an EPS insert
against an ATX receiver. Identical M3 holes are not a key. No thermal approval
from an older geometry transfers to these new boards.

## Bounded main-board placement passes

Developed layouts were recovered from explicit, hash-verified earlier journals
instead of reusing a canonical staging cloud. These were geometry seeds only:
both then passed live current-hierarchy normalization and intake.
The pass used two parallel jobs, three workers per board, eight trials, two
rounds, one epoch, a 480-second deadline, and a 16 GiB free-space floor.

- **EPS:** about 244 seconds. The 92 × 40 mm normalized seed has zero pad-copper,
  pad-edge, and assembly findings. The attempted 88 × 40 mm compaction
  reintroduced one U3/C2 courtyard overlap and is **not** the retained input.
  The attempt also reports three power-corridor access failures:
  `/SENSEC1_LO`, `/SENSEC2_HI`, and `/SENSEC2_LO`. Retain the clean 92 mm seed.
- **ATX:** about 344 seconds. The developed 82 × 95 mm placement has zero
  pad-copper, pad-edge, and assembly findings. Placement admission still has
  two exhausted ground-return local-cell searches at U6.1 and U3.6, plus a
  U4.5 decoupling-loop proximity excess of 0.26 mm against the 0.25 mm limit.
  The four-decoupler repair certificate is intermediate evidence, not four
  additional independent final violations.

Neither board entered priority/residual routing. Priority routing was not run,
not unsuccessfully attempted. Their dashboard views are blocked diagnostic
placements, not routed boards or fab candidates.

The next generic changes are a non-regressing placement choice, power-corridor
access repair, and ground-return placement/search repair. The retained EPS
selection in this handoff is an explicit safeguard, not a claim that a generic
incumbent-selection defect has already been fixed.

## Verification and fresh views

- 92 focused tests plus 146 boundary tests and 41 boundary subtests passed
  (279 JUnit cases; zero errors/failures/skips).
- After publishing rebuilt daughter copper, 41 tests and 41 subtests passed
  again (`parent-owned-postpublication-tests-20260920.xml`).
- Six-board native replay: pad-copper, pad-edge, and assembly counts are zero
  for all selected current inputs; shared-interface dispatch checks pass.
  This narrow physical screen is not full placement/routing/fab admission.
- The historical PCIe two-port review control retains exact board hash,
  regression result, and probe parity. Its already-known sideways-Kelvin
  qualification defect remains; parity does not erase it.
- Generic core audit passes; engine/source hashes remained stable during the
  measured passes. Final next-input hashes were rechecked after daughter
  publication. No additional unchanged wave was left running.

Evidence: `build/parent-owned-final-replay-20260920/report.json`,
`build/parent-owned-followup-tests-20260920.xml`,
`build/parent-owned-final-boundary-tests-20260920.xml`.

Fresh no-body previews (each records its exact board SHA; no old-board fallback):

- [Retained EPS main](http://localhost:8090/?id=pass-parent-owned-retained-review-20260920-eps-8pin-rev3-986c20eb61)
- [ATX main placement](http://localhost:8090/?id=pass-parent-owned-placement-pass-20260920-atx-24pin-rev3-4d708b0505)
- [Rebuilt EPS daughter](http://localhost:8090/?id=pass-daughter-rebuild-production-20260920-eps-db-3e8f932a38)
- [Rebuilt ATX daughter](http://localhost:8090/?id=pass-daughter-rebuild-production-20260920-atx-db-da0ce1eca2)

The earlier main-pass gallery intentionally retains the rejected 88 mm EPS
trial for diagnosis. The current retained-input gallery is
`build/parent-owned-retained-review-20260920/retained-mains-50e0ab3a188d5c5a.png`.
