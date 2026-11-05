# Exact failed-step evidence for isolated fabrication repair

## Root cause of the missing forensic input

The earlier PCIe2 isolated `full` variant returned -11, but the five-variant
transaction retained only an exception string and then removed its temporary
directory. The final selected board was a different input from the failing
step. Replaying that selected board succeeded and could not diagnose the
original native failure. This was an evidence-retention defect; it does not
establish the cause of the original segfault.

## Generic implementation

`cec_failure_replay` captures the exact board, project/rules and explicit
generated-track ownership file **before each step**, retaining bytes in memory
while the step runs. `cec_fab_repair.repair_admitted` records independent stages
for repair, dangling cleanup, post-backtrack acute cleanup, sliver cleanup,
scoring, fabrication and laid-pour checks. Failure evidence describes the
immediately preceding input, not the original baseline or eventual winner.

On failure only, an immutable capsule retains:

- exact pre-step files with SHA-256 identities, options and baseline digest;
- variant/step identity and the Python-engine file digests;
- actual child command, return code and bounded stdout/stderr;
- explicit diagnostic-only / no-release-authority labels.

Native subprocesses enable fatal Python stack reporting. The typed exception
preserves the actual child result instead of only a 1,200-character string.
Verification refuses changed inputs, changed engine, altered identity or
undeclared files. It does not automatically execute a stored command. Retained
commands reference their original paths; manual replay must use a fresh copy
of the verified files and deliberately rebase those paths, never mutate the
immutable capsule.

Storage policy is bounded: 8 MiB input snapshots, 64 MiB per containing artifact
store, a 16 GiB free-space floor check and 32 KiB per log tail with explicit
truncation flags. Identical inputs/engine/context deduplicate. Concurrent writers
serialize the store quota; successful trials create no durable capsules.
Oversized inputs, low space, corruption and storage errors are explicit evidence
statuses, never a reason to accept a failed variant. Old evidence is not evicted.

This applies to exceptions within these fab transaction variants, not every
native operation in the whole pipeline. Baseline evaluation before variants,
outer hard-kills and other subsystems retain their existing diagnostics. The
original -11 remains unreproduced; this patch is not claimed to solve it.

## Verification and concurrent current-board replay

**71 tests pass** in `build/fab-failure-evidence-final-tests-20260916.log`.
This includes existing native lifetime, admission, scheduling and generality
regressions; do not add it to overlapping previous counts. New tests cover all
seven failure positions, partial file overwrite, ownership-file retention,
engine/input tampering, no storage on success, deduplication, concurrent quota
enforcement and free-space refusal. A separate loaded-native child is deliberately
terminated with SIGSEGV after corrupting its disposable PCB; core dumps are
disabled. The retained pre-crash board loads with its original track geometry
and includes the fatal stack/return code. No production board is fault-injected.

Current-source diagnostic cohort:
`build/fab-failure-evidence-suite-20260916/report.json` (four workers).
All four admitted source families run all five repair variants and independent
native postchecks; **none of the twenty variants crashes**. Poses, protected
power copper, source and hierarchy signatures, and engine identity are preserved.
The whole diagnostic directory is about 5.4 MiB. EPS/ATX are refused before
native execution by their unchanged interface-ECO gates.

| Family | Diagnostic selection | Native result |
| --- | --- | --- |
| PCIe2 | baseline | unchanged 0 DRC / 9 opens |
| Hub | baseline | unchanged 12 DRC / 242 opens in held placement |
| 12VHPWR | copper cleanup | unchanged 3 DRC / 220 opens; six covered prefixes trimmed |
| PCIe3 | copper cleanup/fill | 0 DRC; 254 to 223 reported opens after fill, **still zero tracks** |
| EPS / ATX | held before replay | no native transaction or route admission |

The PCIe3 difference is zone-fill connectivity on a placement, not 31 newly
routed traces, a new routing wave or a gain attributable to evidence capture.
None of these private diagnostic outputs is promoted or published as a board
candidate. Historical PCIe2 SHA, complete `board_regression` and all `probes`
exactly match the preceding control; generalization `ok` remains true with
existing broader `release_ok: false`. See
`build/fab-failure-evidence-control-comparison-20260916.json`.

## Continuation

No workers or full cohort remain running. Keep
**`build/route-finish-next-inputs-20260916.json`** and the existing verified
dashboard reviews. No repeat wave is justified by diagnostic retention alone.
Resume a distinct physical cause next: coordinated priority/package fan-in,
power-terminal dependency, or the coupled EPS/ATX mating arrangement. Do not
turn another heartbeat into an unchanged crash replay or a Hub distance loop.
