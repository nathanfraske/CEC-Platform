# Agent-directed overhaul, repository consolidation and main integration

Owner-authorized goal: finish the generic model-directed PCB workflow, make
the repository modular and inspectable, verify it, then push and merge all
reviewed project work to main. ARGB remains outside the nine-board PCB suite.

## Acceptance criteria

1. One canonical direct/MCP control plane owns observation, explicit route /
   connected-cell / power construction, independent checks, model visual
   review, selected checkpoints and review publication. Legacy search engines
   are optional bounded construction backends, not autonomous decision makers.
2. Connected placement reconstructs scoped copper, preserves pin ownership and
   decoupler/return intent, and receives connectivity, current, Kelvin, fields,
   native DRC and declared assembly contracts. Power operations include
   deliberate bank collectors, channels and symmetric via placement, with
   actual saved fill and source-derived requirements. Unknowns cannot pass.
3. Campaign state, jobs, event history, failed decisions and evidence bindings
   survive process restart. Identical failed decisions do not replay forever.
   Cached observations require exact source, family, code, library and tool
   identities; changed candidates never inherit geometry checks.
4. Tests cover positive and negative synthetic constructions, identity and
   recovery failures, direct/MCP parity, cross-board intake/replay and the
   preserved PCIe two-port control. All nine existing boards remain available
   through the laptop inspection viewer. Qualification debt stays visible.
5. The active control plane is a documented package with small modules and a
   stable CLI. Validators, domain data, experiments, generated output and
   historical notes have explicit homes. Compatibility imports are isolated.
   No valuable source, private artifact or historical control is discarded.
6. Capture a recoverable pre-cleanup inventory and working-tree archive.
   Review source and design changes before staging, exclude secrets/runtime
   files, run proportionate checks, commit coherently, push an integration
   branch, merge to main without force, and verify the remote main identity.

Passing these criteria establishes the software overhaul and integration,
not fabrication release or missing thermal/barrel/mating qualification.
No authentication policy, current budget or manufacturing rule is relaxed.

## Work sequence

* Inventory and recoverable checkpoint of the dirty checkout.
* Package the control plane and introduce capability-specific receiver adapters.
* Complete connected-cell and semantic power construction and admission.
* Add durable campaign/recovery, identity-safe observation reuse and issue maps.
* Exercise the full direct/MCP workflow and cross-board regressions.
* Consolidate the repository with compatibility, documentation and CI checks.
* Review commits, push, merge, verify main and hand off exact results.

The existing pass-1 children and the original zero-open/error controls are
immutable checkpoints. New code epochs produce new children, not edits to
those archives. Progress and evidence are recorded alongside each phase.

## Verified implementation and integration record

The package now provides one direct/MCP surface, a closed six-actuator catalog,
source-owned connected placement, source-retaining power geometry, additive
control/Ground connections, exact observation reuse, semantic/physical-peer
identity binding, durable campaign state, finite independent receiving and
model-reviewed selection/fork/publication. Native issue maps and route/copper
review overlays are available in the trackpad inspection viewer.

The pinned portable nine-board checkpoint is in `checkpoints/current.json`.
Its freshly measured native totals remain zero opens, zero errors, zero
exclusions and 283 warnings. Five recorded EPS coupling blockers remain
explicitly unqualified. The received/visually reviewed Hub pilot removes an
exposed reversal and saves 0.492476 mm without changing its native counts.
The PCB, original evidence, explicit work order, code epoch and exact native
before/after plots are retained. No manufacturing release was performed.

Recovery includes the original binary working diff, untracked source/runtime
archive and ignored-helper archive outside the checkout. Fifty-seven needed
historical helpers now have tracked source and origin hashes. Four unsuccessful
or superseded checkpoint export directories were moved to that recovery area,
not erased. Runtime output, local indexes, preferences, locks and caches are
excluded from staging. Native checkpoint writer bytes are preserved verbatim,
not normalized to make whitespace diagnostics look cleaner.

The active contracts and receiver-backend test results are recorded in the
closeout evidence. The broad historical sweep is **not a full pass**: it ran
14,593 tests across 526 modules before a single legacy module exceeded the
2 GiB owned-process limit. It recorded 150 failures, 58 errors and six skips;
code continued evolving during that diagnostic run, so its epoch also changed.
The initial 16 failures were reproduced in a recovered pre-overhaul dirty
checkout. A further replay of all 208 failing nodes found a real cleanup
regression: one sibling driver was missing from the recovered source. The
driver is now tracked byte-for-byte with provenance; all 94 tests in that
affected module pass. The paired replay and remaining historical failures
are explicit compatibility debt, not hidden by weakening manufacturing/current
rules or dropping tests.

The Standard-main electrical source report was regenerated from all six
manifest hierarchies and pinned separately: zero source-level blockers,
21 qualification warnings. The August audit remains clearly historical.
This does not qualify hot-plug, OVP transients, effective capacitance, hold-up,
thermal/current capacity, physical fit or fabrication release.

Remote integration remains a separate final step until the actual commit,
push and merge identities have been verified. This document is not evidence
that a push or merge has already happened.

## Clean-checkout verification, 2026-11-05

An archive of the exact staged Git tree was tested without ignored `build/`
source or local runtime output. The active contracts, inspection/dashboard,
current electrical-audit snapshot and recovered annotation worker tests passed:
224 tests, zero failures/errors/skips. The 17 independent receiving/backend
modules passed another 652 tests, zero failures/errors/skips, with unchanged
code and dependency identities and a 1.55 GiB peak owned RSS. The direct CLI
loaded all nine pinned boards from that clean tree. These are 876 tests in
explicit slices, **not** a claim that the whole historical corpus passes.

The remaining 145 failures in the 208-node historical replay also failed in
the recovered pre-overhaul checkout; two old failures now pass. The missing
neighbor accounted for the other 59 regressions and is covered by the passing
94-test worker module plus a generic adjacent-file/provenance closure test.
The retained broad sweep still does not establish a full legacy pass.

The compact identities and exact scope are retained in
`agent-directed-overhaul-verification-2026-11-05.json`. Raw XML and interrupted
diagnostics remain in the external review/recovery directory, not new source
hidden in build output. The existing main-branch hygiene script already
rejects Mini-Fit references that main itself contains; it is not weakened or
disabled to manufacture a green integration status.

The first GitHub contract run exposed dependencies absent from the stock
KiCad image: NumPy, SciPy, Shapely and pytest for fresh child interpreters. CI now
installs those using the native container's own package manager, instead of
passing host-Python dependencies through `PYTHONPATH`. This changes no PCB,
receiver predicate, resource bound or manufacturing rule.
