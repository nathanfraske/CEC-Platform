# Placement identity: diagnostic-output boundary

September 16, 2026. Generic implementation and native replay qualified.
No board geometry has been promoted by this slice.

## Proven cause

The PCIe3 power-replan support-group trial was being rejected as
`placement inputs changed during evaluation`. Compact identity deltas now
survive the coordinator's generic failure projection. A fresh production
reproduction identifies exactly one changed file role:
`environment.CEC_OPERATION_STACKS`. The supervisor's normal 60-second stack
sample appended to its log during the check. Board, policy and environment
values did not change. The old identity collector treated every file-valued
`CEC_*` variable as design authority, including this diagnostic output.

Evidence: `build/identity-delta-repro-20260916/report.json`, trial 1. The log
changed from the empty-file digest to a populated stack log; this is a
reproduced defect, not an inferred explanation for every historic failure.

## Shared correction

- `cec_operation_budget.DIAGNOSTIC_OUTPUT_ENV_KEYS` explicitly declares its
  two output sinks: progress and stack logs.
- `cec_placement_evidence_identity.capture` excludes only those sink bytes
  from authority hashing. Their path values remain hashed. Config aliases,
  unknown file-valued environment policy, boards, sidecars and other authority
  remain bound and still fail closed on mutation.
- `describe_change` supplies sorted changed roles, paths and digests, plus
  hashed policy/environment changes. No raw environment values are logged.
  The failed-checker shape survives existing generic failure reduction.
- `placement_craft_evidence` attaches that diagnostic on a true identity
  mismatch, still rejects the result, and does not cache it.

There are no board names, reference designators or coordinate special cases
in the fix. It does not change routing, fabrication or electrical limits.

## Validation and actual outcome

**290 tests pass** across identity, craft admission, endpoint roadmap and
operation budgeting. The tests cover both diagnostic sinks, file creation
and append, path changes, true authority mutation, alias protection, cache
behavior and preserved failure details. KiCad emits its existing SWIG
deprecation warning.

Concurrent replay performs **eight fresh native measurements** on PCIe2,
PCIe3, Hub and 12VHPWR. Each board's baseline and mid-measurement log mutation
have identical physical gate results; no false integrity rejection occurs.
The historical PCIe2 control retains identical board hash, regression score
and probes. EPS/ATX are explicitly held for their existing unadmitted interface
ECO, not counted as passing native placement tests. All six canonical sources
and schematic hierarchies remain unchanged. The frozen engine signature
matches the isolated reproduction and replay.

The **real supervised power-replan reproduction** completes in 114.743 s.
Its previously false-rejected support-group trial now reaches the actual
post-authority check. Both tested proposals fail the genuine U3.5 +3V3 local
ground-return access check. Neither is accepted; this fix improves correct
evaluation and diagnosis, not the board's route count or fabrication status.
No identical full-board wave was restarted and no unchanged image was
published as a new candidate.

Receipt: `build/identity-output-qualified-20260916.json`.
Reproducer: `tmp/identity_delta_repro_20260916.py`.
Cross-family replay: `tmp/identity_output_replay_20260916.py`.
Receipt verifier: `tmp/qualify_identity_output_fix_20260916.py`.
Native reports: `build/identity-output-fixed-repro-20260916/report.json` and
`build/identity-output-replay-20260916/report.json`.
Test log: `build/identity-output-boundary-tests-20260916.log`.

Static legacy debt remains **23 physical / 380 runtime findings**;
`full_pipeline_generic` and `release_ok` remain false. Do not confuse this
slice's regression qualification with whole-pipeline closure.

## Next bounded work

Keep `build/bound-return-next-inputs-20260916.json` as the canonical cohort.
Investigate coordinated supply/ground-return reconstruction after placement
authority rebuilds, shared by the PCIe3 witness and Hub blockers. Treat the
nine PCIe3 Kelvin range violations as group-placement work, not a reason to
relax the 9 mm policy or spend another identical ordinary routing wave.
Continue other boards only when their changed search domain or new evidence
justifies a bounded pass. EPS/ATX retain their coupled mechanical authority
hold; do not move one mating half or waive a terminal overlap.
