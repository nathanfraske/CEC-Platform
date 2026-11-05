# Placement continuation and routing-admission work — 2026-09-09

This continues from the current-source 58 × 72 mm 12VHPWR placement, not from
either historical root/candidate PCB. The experiment verifies the 12 current
hierarchical schematic hashes and the protected PCIe, Hub and 12VHPWR artifacts
before running. No schematic, BOM, footprint, board policy or fabrication
allowance is changed by these slices.

## Forensic: review checkpoints silently skipped repair

The real production placement-stage replay returned
`existing-routed-beta-placement-verified` and `routed_input_read_only` for the
saved **initial placement review**. Its authored power/template tracks caused
the routed-board safety boundary to fire. The review path returns before the
route-admitted stage journal/checkpoint, so the continuation did not recognize
the separate certificate already written beside this artifact.

`_placement_stage_artifact_provenance` now accepts that existing certificate
only when its role, schema, exact path, exact SHA-256, successful source intake
and successful worker evaluation match. Both routing/release admission flags
must still be explicitly false. Bad physical findings are deliberately retained:
permission to resume repair is not permission to route. Changed bytes, another
path, absent digest, failed worker/source checks and malformed certificates
remain untrusted. Current source intake still runs independently on continuation.

The pre-fix production result and unchanged failure stack are retained in
`build/12vhpwr-route-ready-20260909/stage.json`.

## Generic precision-template / supply-cell ownership partition

Six bypass capacitors were rigid members of legacy sensing templates. Their
relative seats violate today's complete-loop proximity rule, but moving one
member would invalidate its authored copper. The template also carried obsolete
auxiliary supply/ground routing that the newer native cell planner should own.

`cec_blueprint_ownership.partition_supply` compiles a new template from live
source assignments. It releases only fully recorded, two-terminal bypasses
whose owner belongs to the template and whose recorded supply/return lands
match current source nets. A role touching an unassigned part (for example a
force terminal or precision filter) is retained. Shared-role exclusions reach
a finite fixed point before any data is removed. Unknown topology is not
guessed away. A released internal supply net becomes a routing port so ideal
internal synthesis cannot recreate the old copper.

Fresh stamping, resumed stamping and immutable-member discovery consume the
same compiled template. The source component population is unchanged. All
released caps still face ordinary source-derived placement and exact native
supply/ground construction. Retained precision tracks, widths, pad positions
and mapping are unchanged as data; full-board admission remains independent.

On this source, each of six templates retains its five precision members and
49 precision segments; one bypass and 25 auxiliary segments leave template
ownership. Actual materialization lays **294 precision segments**, all six
cells and all six required force lanes, with no cell/lane refusal. The removed
150 auxiliary segments are not a routing completion claim: the local-cell
constructor must replace the needed connections using current process rules.
Partition certificates: `build/blueprint-partition-20260909.json`.

## Exact lazy beam and avoid unused rotation solves

A live sampling trace found proposal generation spending time in the local
cell beam, before any routing. The beam built a Cartesian successor list and
then sorted/discarded most of it. `cec_ranked_frontier.take_ranked` now merges
ordered, lazily admitted successor streams. Ordering uses the *actual next
state key*, not an approximate cost; ties retain the former stable source
order. Geometric rejection happens before a proposal can occupy the beam.

Synthetic replay compares the complete selector against exhaustive sorting
with differing scores, orientations, projections, ties and blockers. A dense
2,048 × 2,048 synthetic frontier needs at most 4,096 stream reads instead of
materializing 4,194,304 combinations. This is not a universal runtime bound:
an infeasible stream may still need exhaustive rejection to prove no seat.

Owner translation also formerly computed four rotated local menus but consumed
only the unrotated one. Translation subcalls now compute that one menu; the
outer unshifted family still examines all four rotations. A synthetic check
proves identical consumed reseats and **68 → 20** selector invocations for
four base rotations plus sixteen translations. No search result that the
caller formerly consumed is dropped. Proposal-generation time and population
are now recorded and printed per repair round.

## Batch read-only native connectivity lookups

The ground portal fallback rebuilt the entire native connectivity graph for
every candidate pad even though the discovery loop did not mutate the board.
It now rebuilds once per terminal scan; actual edits and rollback remain after
the scan, and the next terminal refreshes its graph. A synthetic test checks
that mutation between terminals cannot leak a stale connectivity snapshot.

On identical source bytes, a native before/after replay fell from **91.074 s
to 15.843 s** (5.75× faster), and from **2,029 to 161** connectivity rebuilds.
Normalized output geometry and verdicts are identical. This is a measured
reservation-query improvement, not a claimed full-pipeline speedup. Evidence:
`build/ground-scan-legacy-20260909.json` and
`build/ground-scan-batched-20260909.json`.

## Fine local closure before wholesale relocation

An exactly reproduced rejected sensing-capacitor move overlapped retained
Kelvin copper on `/IN1_N`; the complete template correctly refused to stamp.
The coarse proposal menu never evaluated a small, safe displacement that met
the existing proximity limit. `cec_local_seating.closure_poses` now searches a
bounded fine lattice and the measured tangent segment, ranking electrically
qualified poses by displacement. Its adapter screens actual native pad shapes
against incumbent foreign copper and courtyards. This is conservative proposal
selection only: broader families remain, and full-board regeneration/admission
is mandatory. No proximity limit or preserved precision geometry is relaxed.

On this board, the screen found 0.05 mm sensing-cap corrections and a regulator
cap correction in 3.3 seconds. The completed v4 replay reduced decoupling
findings from **9 to 2**, leaving only the MCU supply/return pair of findings.
All six precision cells and force lanes remained constructible. The exact
failure log now also retains blueprint/force refusals and top-level evidence
errors alongside the proposed transform.

## Collective hard-domain support before beam truncation

Two additional generic defects affected multi-cap packages:

- The constructor used both an isolated supply-leg limit and a complete-loop
  limit, although the qualified checker uses the complete-loop objective.
  Proposal bounds now use the same qualified mode; final checker limits are
  unchanged. An explicit positive/negative regression covers the distinction.
- Dense grids supplied hundreds of individually good poses that had no legal
  partner in the other capacitor's shortlist. An exhaustive diagnostic found
  **1,129 non-overlapping zero-excess pairings**, but truncation discarded them.
  `cec_cell_domains.supported_boxes` removes poses without peer support in the
  zero-excess domain before truncation. It uses blocked array comparisons with
  an explicit comparison budget. Untested relationships retain their poses;
  budget exhaustion is never represented as infeasibility. Opposite faces are
  not treated as same-face conflicts. The full collective beam and native
  admission still own acceptance, including higher-order conflicts.

The broad heuristic domain remains a fallback. Courtyard geometry is cached
across the hard-domain subpass so the new preselection does not duplicate
native footprint reads. Synthetic tests include a dense misleading cloud,
renamed/translated geometry, incomplete budgets and a three-part/two-seat
example where pair support correctly does **not** claim a full packing.

## Free-space locality repair

Remaining stranded-part moves sampled straight lines through occupied
courtyards. The repair now reuses `contact_translation_sites` to propose actual
free cavities near connected peers, considering four orthogonal orientations
and preserving fixed endpoints. The contact primitive now includes interior
obstacle boundaries and an optional preferred origin before its finite site
limit; a component is often a hole in the free polygon, not its outer edge.

An additional score tie-break records total stranded distance after the
existing worst-distance metric. Improving a non-worst failing relation can
therefore make quantized, monotonic progress without changing any earlier hard
priority, count or no-new-stranded-ref invariant.

## Validation and status

The completed placement-wide run passed **879 tests, 14 existing skips and
8 subtests** (`build/route-ready-final-all-slices-tests-20260909.log`). After the
critical-pair changes, a 28-file broad selection passed **671 tests, 1 skip**
and the final precision/preflight/generalization selection passed **166 tests**.
Those selections overlap and must not be added as unique-test totals. Logs:
`build/route-ready-closeout-broad-tests-20260909.log` and
`build/priority-final-tests-20260909.log`.

The immutable
PCIe control replay remains **0 DRC, 0 opens, 615 tracks,
226 vias, 1242.073 mm**. Its eight broader constraint blockers and failed
broader release/differential-pair verdict are unchanged, not silently waived.
The complete regression payload equals the prior replay, not only its count
summary. See `build/priority-final-pcie-regression-20260909.json`.

Completed placement continuations are retained separately under
`build/12vhpwr-route-ready-v3-20260909` and
`build/12vhpwr-route-ready-v4-20260909`. Neither is routing-admitted. v3 reduced
11 decoupling/3 stranded findings to 9/2; v4 reduced these to 2/2 at the same
58 × 72 mm outline. No historical/canonical/control board was promoted or
overwritten. v5 then closed the remaining MCU supply-distance/return-placement
findings through a native-admitted joint capacitor move and bounded eviction;
the MCU stayed fixed. v6 closed both stranded findings. Its pads-in-bounds,
courtyards, mechanical/placement constraints and placement-craft gate all pass.
The one remaining craft warning is the route-owned local-cell-access check;
the priority probe's exact supply authority reports 16/16 accessible cells.

**v6 is not routing-admitted.** Its completed priority gate still refuses USB,
CAN and CAN_INT. The seven exact placement-repair probes accepted no improving
candidate, and the bounded loop stopped. `build/12vhpwr-route-ready-v6-20260909/`
contains the unchanged candidate, `stage.json`, native score, `closeout.json`
and visibly labelled top/bottom placement renders. The checkpoint has 12 native
structural DRC findings and 246 unconnected items; broad signal routing has not
run. These are not a routed-board closure result. No fabrication or thermal
qualification is claimed.

The production continuation is bounded and uses independent native workers.
An interrupted diagnostic attempt is not a result or a promoted board. Final
routing admission must be taken from the completed placement and preflight
reports, never the review certificate, template compilation count or unit tests.

## Critical-pair forensic continuation

The failed exact probes exposed further reusable defects:

1. The router chose physical terminals using the farthest-package heuristic.
   An off-corridor four-land protection array could become an endpoint while
   a single-contact IC became a multidrop branch. `cec_pair_banks` now proves
   parallel, transverse two-bank geometry and recognizes an unambiguous
   two-terminal chain before applying the legacy fallback. Interleaved
   reversible-connector contacts are not banks. Tests vary names, translation,
   rotation, enumeration and station displacement, and reject malformed or
   ambiguous fields. The actual USB probe now preserves the protection station
   in the external route chain. That fixes topology, not its final routability.
2. The multidrop planner checked for three common-footprint terminals *before*
   discovering paired split-member terminals. The count gate now applies to
   the complete discovered terminal set. A two-common-plus-one-split synthetic
   regression covers the previously unreachable case. Existing split-distance
   and compatibility constraints remain unchanged.
3. Return-field searches rebuilt identical foreign-copper geometry for every
   seat. The exact indexes are now scoped to a read-only candidate field and
   rebuilt immediately after mutation. The conventional escape scan also uses
   an invocation-local exact index. Native tests compare cached/uncached
   decisions, check inner copper, and prove the mutation boundary. On the actual
   candidate one return-field query changed from **0.864187 s to 0.025750 s**
   (33.6x), with identical verdicts and via position. This is not a full-run
   speedup claim. Evidence: `build/pair-return-field-benchmark-20260909.json`.
4. The preflight projection discarded junction rejection counts and samples.
   It now retains `candidate_prefilter`; a projection regression proves this
   cause survives both compacting boundaries.

Post-fix focused native probes remain refused. Internal CAN finishes its finite
search without an admissible corridor; this is explicitly **not proof of global
impossibility**. External CAN and the difficult USB flow-through leg exhaust
their budgets. Evidence: `build/priority-can-cache-grid-20260909.json` and
`build/priority-usb-all-caches-20260909.json`. Earlier diagnostic files without
`grid` in their names did not enable the production grid fallback and are not
route-admission evidence.

The next placement contract to address is source-topology ownership of paired
series/bypass links. The current hierarchical CAN sheet explicitly declares an
unpopulated optional choke and two populated zero-ohm winding bypasses. In the
current placement those bypasses are roughly 20 mm apart; ordinary courtyard
and nearest-peer checks do not keep them together at the relevant four-net
device. Moving either named resistor by hand would hide the defect. A generic
connectivity-derived owner/group contract must drive their joint placement and
the same physical terminal graph must feed routing. Likewise the flow-through
placement helpers still recognize only `_P/_N` spellings while routing also
recognizes `_DP/_DM`; reconcile that pair identity boundary before more blind
waves. Do not increase the outline or waive priority-route acceptance to hide
these missing relationships.
