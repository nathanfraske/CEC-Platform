# Preserve precision-route ownership at final scalar completion

## Proven defect and generic repair

The final ordinary-net completer used a separate name heuristic to exclude
specialized buses. It recognized `CAN_H` / `CAN_L` and the `_BUS` spelling but
missed valid segmented names already recognized by the precision router.
Current PCIe2 and PCIe3 therefore included both `/CAN_H_J1` / `/CAN_L_J1` in
their scalar-completion candidate list; 12VHPWR included `/CAN_H_INT` /
`/CAN_L_INT`. This was an ownership mismatch, not evidence that these retained
boards actually acquired an incorrect new CAN route in the observed runs.

`cec_fr._ordinary_final_completion_nets` now consumes the same live
`cec_pair_semantics.coupled_pair_names` identity as the precision stage, plus
the existing device-qualified analog input contracts. A renamed current-input
net cannot become an ordinary scalar route just because its label lacks a
sense suffix. Existing Kelvin, power, clock and conservative name exclusions
remain. Shared-identity errors propagate instead of silently falling back.

There is no board/reference/coordinate exception, no new electrical limit,
and no relaxed pair coupling or clearance test. Ordinary CAN RX/TX, USB CC and
control nets retain their existing eligibility. This fixes stage dispatch,
not pair placement or route geometry.

## Qualification

**97 tests and eight subtests passed** in 3.71 s:
`build/ordinary-completion-ownership-final-tests-20260916.log`.
Loaded-native tests cover renamed hierarchy/branch suffixes, arbitrary device
input net names, translated/rotated footprints, scalar controls, default KiCad
pair dimensions, and propagated identity failure. A real final-completion
dispatch connects the control net while emitting no copper on either pair
member. Source bytes remain unchanged. An initial fixture incorrectly saved
orphan nets without terminals; KiCad discarded them. That failed test receipt
is retained; corrected fixtures provide live terminals before save/reload.

**Concurrent native four-family replay passes**, with two explicit interface
holds: `build/ordinary-completion-ownership-replay-20260916/report.json`.
The three pairs above leave scalar eligibility; Hub's set is unchanged. No
shared specialized member remains in any applicable scalar set. The bounded
real last-mile calls preserve DRC/open counts relative to their corresponding
prior diagnostic controls, original poses/copper and existing qualified pairs.
All six canonical source/hierarchy hashes and the frozen engine are unchanged.
Historical PCIe2 board hash, complete regression and all probes match exactly.

These are private diagnostic routes, **not** full-stage or release admission.
The source boards and canonical continuation cohort do not change. Existing
physical/runtime audit debt remains 23 / 380; `full_pipeline_generic` and
`release_ok` remain false. No full wave is warranted just to repeat the same
physical failure. There is no new dashboard candidate to publish.

## Bounded rejected search experiment

This defect was observed while screening a different possible repair:
`build/bounded-signal-dogbone-probe-20260916/report.json`.
A worker-local prototype offered existing process-qualified smaller barrels
only for a direct same-layer SMD dogbone within the existing 1.5-mm live-owner
rule. All-layer copper, pad, hole, edge, width and power guards stayed active;
ordinary and remote transitions retained their original dimensions. No
production dogbone search was changed.

Four-family baseline/prototype comparisons show **no extra closure**. PCIe2
remains 0 DRC / 9 opens after 72 extra qualified seat proposals. Hub, PCIe3 and
VHP each close the same four ordinary gaps in both modes; the extra domain
adds no benefit (37 / 19 / 34 additional seat proposals respectively).
Those proposals are not necessarily selected or emitted copper. EPS/ATX are
held before replay. Source/hierarchy and engine hashes match throughout.
The prototype is **not integrated**. Do not repeat it as a new wave or count
its scratch routes as new canonical board progress.

## Continuation

Keep `build/priority-coopt-next-inputs-20260916.json` and the separately
qualified craft-frontier scheduling repair. No workers from either experiment
remain. Windows dashboard root returns HTTP 200; approximately 65 GiB remains
free above the 16-GiB floor.

Next geometry work still needs a constructive exact endpoint/complete-cell
dependency witness. The earlier complete-cell return reconstruction already
showed that PCIe2's nearby generated return is not the sole soft-start blocker;
do not repeat isolated via removal, shrinkage or its unchanged cell-order
ablations. Preserve locked power, pair ownership and paired mating geometry.
