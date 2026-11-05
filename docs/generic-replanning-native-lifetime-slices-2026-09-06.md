# Bounded replanning and native discard lifecycle — closed slices

Date: 2026-09-06. Status: both implementation slices completed and tested.
This closes the two scoped features, not the boards' fabrication release.
All hardware experiments use copies; no original or archived control was
replaced, and no proposal was promoted to fabrication review.

## Slice 1: dependency-aware bounded replanning

Root cause: the dimension actuator captured all local boundaries before the
first repair. An admitted whole-cell reconstruction could legitimately change
a later target's incident tracks or ownership. That target then failed the
stale-boundary check and was abandoned, although a fresh legal cell could be
constructed. The stale check was correct; the scheduler lacked a refresh path.

`scripts/cec_dimension_repair.py` now supports a targeted fresh plan after a
stale refusal, with these constraints:

- Only an **already admitted** board generation can authorize the refresh.
  An unexplained stale result on an unchanged generation is deferred.
- Replanning uses the same native dimension classifier, owner checks, exact
  graph boundary, and seat generator on the current admitted board.
- The refresh is restricted to the original target UUID; it cannot substitute
  a different target or expand the initial population.
- Default limits remain eight targets, 32 seat probes per target, a 2 mm local
  radius, and the existing wall deadline. One replan per target is allowed by
  default through the parameter `max_replans_per_target`.
- The stale probe consumes the original seat budget. A refresh never resets
  that budget or the deadline. Repeated target fingerprints and missing
  current spatial targets cause explicit deferral.
- A refreshed proposal passes the same independent DRC/connectivity,
  dimension/assembly identity, other-constraint, route-quality, and fabrication
  admission checks. Refreshing ownership evidence does not grant an exemption.

Reports retain `replans`, `deferred_targets`, generation numbers, target
fingerprints, consumed seat counts, and the fresh planning result. The existing
production dimension-repair stage automatically uses this behavior. Search
workers retain the eight-seat native-state bound introduced in the prior slice.

No broad retry loop was added: already exhausted targets are not continually
reopened merely because another candidate exists. This slice covers stale
local boundaries encountered in the bounded initial queue.

## Slice 2: permanent-discard ownership, applied beyond one repair

The previous slice isolated a KiCad 10 lifetime defect when a borrowed track
proxy was handed to Python ownership by `Remove()` and later finalized. This
slice audited the corresponding decoupler and routing cleanup paths instead
of treating the first failing via as unique.

`scripts/cec_native_items.py::discard_items` is the shared permanent-discard
operation. It snapshots/deduplicates selected UUIDs before mutation, removes
their group membership, calls native `Delete`, and does not return reusable
native handles. It does **not** decide which copper may be removed: electrical
selection, locks, precision ownership, and admission remain with each caller.

Twenty detach-for-discard call sites in `cec_fr.py` and
`cec_decoupler_cell.py` were migrated. The dimension actuator also uses the
shared operation. Audited operations include:

- read-only decoupler feasibility trials and preview cleanup;
- rejected supply/ground cells and alternate ground-entry ordering;
- rejected per-terminal grounding copper;
- policy-selected local rip-up;
- superseded generated pours and dead pickup vias/stubs;
- temporary paired-route probes;
- redundant-pour-trace trials, degenerate tracks, plane-policy removal, and
  dangling-track pruning.

None of these sites reattaches the removed native objects. Where rollback is
required, it uses the existing saved board or regeneration path. This is not
a repository-wide blind replacement of `Remove`: true detach/reuse operations
outside these audited modules have not been changed or declared verified.

Tests exercise duplicate aliases, mixed tracks/vias/zones, retained group
members, loaded borrowed proxies, repeated destruction, registry-reference
balance, and normal child-process exit. An AST regression prevents these three
audited modules from reintroducing board `Remove` calls. Existing decoupler and
routing tests retain the original physical selection and rollback expectations.

## Measured PCIe replay

Evidence: `build/replan-native-pcie2-v1/report.json`.
Source: `build/board-archive/20260831T1619-pcie-8pin-2port-v113-zero-open-v43/board.kicad_pcb`.

| Metric | Archived control | Previous cell slice | These slices |
| --- | ---: | ---: | ---: |
| Dimension findings | 50 | 38 | 36 |
| Via/pad overlap findings | 7 | 2 | 1 |
| Structural DRC | 0 | 0 | 0 |
| Unconnected | 0 | 0 | 0 |
| Tracks | 615 | 612 | 605 |
| Vias | 226 | 226 | 226 |
| Route length, mm | 1242.073 | 1245.030 | 1247.080 |

The full-control replay took **88.947 seconds**, consumed 148 seat probes,
and admitted six repairs. Five were already demonstrated by the prior slice;
**one additional cell was repaired after its stale boundary was refreshed**.
The refresh consumed one stale probe and stayed within the original per-target
seat allowance. No replan budget, wall deadline, or worker failure stopped the
run. One other target remained geometrically unroutable within its bounded
search. There was no repeated-refresh loop.

The incremental gain is **38 to 36 dimension findings and 2 to 1 assembly
overlaps**, with seven fewer track primitives and 2.050 mm additional route
length. Cumulative improvement from the archived control is 50 to 36 dimension
findings and 7 to 1 overlaps. No new blocker category appeared, and per-repair
admission also checked individual fault identities and detailed other failures.

The eight existing release-blocker categories, one fab acid-trap finding,
five route-craft advisories, and nine non-octilinear track findings remain.
Zero DRC/opens does not imply complete fabrication qualification.

## Hub nonregression replay

Evidence: `build/replan-native-hub-v1/report.json`, using the manifest's current
`beta/hub-standard-rev2/candidate/hub-standard-rev2-candidate.kicad_pcb`.

The spatial planner has no eligible targets. The existing normalizer removes
the netclass-geometry blocker, as in the prior replay, but these two slices add
no further physical repair on this board. Structural DRC remains **5**,
unconnected remains **13**, via/pad overlaps remain **1**, and fab blocking DRC
remains **4**. No new blocker category appears. This is a cross-board negative
control, not positive proof that the Hub's remaining blockers are solved.

Verified original PCB hashes are unchanged:

- PCIe: `d6bc7c2df081a5c9f8ec32da8586071464c5fe8ba8dc3383c17ffdcb809789ea`
- Hub: `769f20bed0f0735c7ad86dbc97c315e8333c7318d3e05ff065d84130ba6f67dc`

## Closeout checks and remaining scope

- `build/replan-native-integration-tests.log`: **676 tests and 11 subtests
  passed**, in 76.02 seconds.
- `build/replan-native-new-tests.log`: 64 focused cases passed, including the
  existing dimension/cell tests and 19 new replanning/native-lifetime cases.
- Python compilation and `git diff --check` passed.
- `build/replan-native-generic-audit.json`: declared generic core passes with
  zero product/refdes selectors. Full-pipeline generic acceptance remains
  **false**, with 23 inherited physical-engine selectors and 380 runtime
  occurrences across 99 checked runtime modules. No selector debt was hidden
  or relabeled as completed.

No new thermal, electrical-budget, or mechanical qualification was performed.
Further work should address additional explicitly supported precision-owner
reconstruction and the remaining release-blocker classes, not keep replaying
these now-closed scheduling/lifetime slices without new evidence.
