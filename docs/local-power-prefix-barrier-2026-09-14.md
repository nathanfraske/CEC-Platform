# Local PI, Kelvin and power composition barrier

## Scope and status

This slice fixes stage composition, not a particular component placement. No
reference designator, board name, coordinate, outline expansion or relaxed
electrical requirement is used by the new `cec_local_power_prefix` module.
Source PCB files and the historical PCIe2 review control remain immutable.
These are partial routing results, not fabrication approval.

The production schedule now owns complete pin-local decoupling copper, builds
Kelvin taps, constructs exact power around that local prefix, admits its ground
returns, and only then routes long differential pairs around the admitted
power. Downstream stages revalidate the existing power rather than creating
its zones a second time. Non-applicable and explicitly selected diagnostic
schedules retain their existing path.

## Root cause and corrections

1. The initial hypothesis that local PI and Kelvin alone conflict was disproved
   by a native same-board probe. Both coexist before power construction.
2. Independently passing local, pair and power probes did not establish that
   their combined saved copper could coexist. The new barrier requires that
   combined proof before advancing to long pairs.
3. The first normal entrypoint replay built all three pairs, then an old
   unconditional power-reconciliation stage redeclared power and introduced
   five `zones_intersect` violations into a zero-DRC artifact. That run was
   deliberately interrupted before spending another duplicate candidate.
4. The new reuse boundary checks the original PCB and power-authority hashes,
   saved power-zone declarations, preserved local copper, footprint positions,
   qualified pairs, native source/sink power connectivity, fresh zone fill and
   independent score admission. It does not waive the five violations or
   treat a cached passing report as sufficient evidence.

Both construction and reuse select a disposable output only on success. The
reports explicitly retain `release_accepted=false` and
`residual_allowed=false`; the later full pipeline still owns those decisions.

## Native evidence

| Checkpoint | Result | Evidence |
| --- | --- | --- |
| Original-placement local PI + Kelvin | Both coexist; initial hypothesis disproved | `build/pi-kelvin-composition-20260914/baseline.json` |
| Local PI, Kelvin, exact power and ground | 0 DRC, 137 opens; 10.314 s | `build/pi-kelvin-power-atomic-v2-20260914/report.json` |
| All three critical pairs added | 0 DRC, 125 opens; 41.083 s pair campaign | `build/pi-kelvin-power-pairs-atomic-20260914/campaign.json` |
| Standalone production barrier | Admitted, 10.306 s | `build/local-power-prefix-production-20260914/report.json` |
| First full-entrypoint barrier | Admitted, 10.094 s; placement and preflight passed | `build/local-power-barrier-full-suite-20260914/pcie-8pin-2port/04-route/candidate-000000/local-power-prefix/report.json` |
| Defective later reconstruction | 0 to 5 DRC; 125 opens unchanged; rejected | `build/local-power-barrier-full-suite-20260914/pcie-8pin-2port/04-route/candidate-000000/critical-prefix-clipped-power-authority.json` |
| Native saved-power reuse | Admitted, 0 DRC, 125 opens; all 140 parent copper items retained | `build/local-power-reuse-native-20260914/report.json` |

The first full run is recorded as interrupted (`exit_code=-15`, 246.121 s),
not as a completed full pass. Its automatically generated missing-output
placeholder is not a board preview. The replacement end-to-end run starts
from the same original placement in
`build/local-power-reuse-full-suite-20260914`, not from a hand-composed routed
checkpoint. Its completed outcome is recorded below.

### Replacement full-entrypoint outcome

`build/local-power-reuse-full-suite-20260914/suite.json` completed in 325.016 s
with `exit_code=2` (blocked, not interrupted). Source PCB, electrical inputs
and engine hashes all stayed unchanged. Placement passed in 43.869 s,
preflight in 60.881 s, and the bounded two-candidate route ensemble finished
in 204.420 s. Both candidates built all three pairs and reached 0 DRC / 102
opens, but both refused `/07-usb-flash/VBUS_F` at the rated-current boundary.
The prior zone-intersection failure did not recur. Ordinary residual routing
and release stages were not reached. The late power-reuse call is downstream
of this refusal, so its success is currently demonstrated by native isolated
replay, not a fully completed production invocation.

The independent `build/current-before-signals-probe-20260914/report.json`
replay tried the same current-domain transaction immediately after pairs,
before ordinary signals. It still refused the same 69.060 mm fuse-to-bead
connection (9.839 s). Thus ordinary-signal congestion alone does not explain
that refusal. The exact-search report names legal layers, endpoint access and
real pour/pad/copper blockers; a bounded refusal is not proof that no route
exists. Both candidate seeds reached the same blocker, so another unchanged
wave is not a justified next experiment.

### Additional preservation failure found by the new gate

`build/local-power-reuse-current-native-20260914/report.json` replays reuse on
the latest 102-open partial artifact. It refuses despite 0 DRC, unchanged
power-zone declarations, connected power domains and preserved pairs: three
parent `/VBUS` copper objects were removed by the earlier current-width prune.
This is an intended detection, not a pass.

The current-stage report identifies two locked 0.500 mm `In2.Cu` tracks and
one orphaned via removed by that prune. The carried rated-current contract
requires 0.845075 mm on that layer, while local-cell generation used the
0.500 mm project-class width. The generator currently obtains width from
`cec_decoupler_cell._netclass`; the later current checker applies layer-specific
current widths. The next generic repair must give these stages consistent
width/topology authority at construction time. Simply exempting locked PI
copper from current requirements or deleting it after admission is not a fix.
Do not infer the aggregate trunk current through every capacitor branch
without topology evidence; preserve existing current-budget decisions.

The later gate successfully catches this disagreement, but does not make the
partially generated artifact eligible for residual routing or fabrication.

Original placement SHA-256:
`43e2ae6f0866ad76f1225b95728efbe4ab4672a654493e35339d91412f9e3789`.

## Cross-board checks and diagnostic correction

An early Hub diagnostic retained future-power reservations while constructing
local PI. Production intentionally releases those advisory reservations first,
then must reconcile exact power around the admitted local copper. Therefore
`hub-local-power-crossboard-20260914` is not a production-equivalent PI failure.

The corrected order, recorded in
`build/hub-local-power-correct-order-20260914/report.json`, admits all 14 local
PI cells with zero DRC and reduces opens from 242 to 202. The source is
unchanged. The following production barrier refuses at exact power because
the power authority conflicts with protected CAN/local-return geometry:
`build/hub-local-power-production-barrier-20260914/report.json`.
This proves the reusable refusal boundary on a second board; it does not prove
Hub routing closure. No protected CAN copper or power requirement was removed.

The corrected 12VHPWR replay still refuses the U1 pin 3/C7 local supply path:
`build/hpwr-local-power-correct-order-20260914/report.json`. It rolls back with
the source unchanged. Its post-failure clearance counts must not be described
as independent placement defects: the PI wrapper skips final refill after a
construction refusal, so partially generated vias are scored against old zone
fills. The constructive refusal is the actionable result. A future diagnostic
improvement should either refill the failed disposable trial or explicitly
mark those post-failure DRC rows as based on stale fill.

## Regression evidence

- Final run `build/local-power-reuse-final-tests-20260914.log`: **146 passed,
  4 skipped**, 73.42 s, covering the new boundary, route oracle and full
  pipeline tests together. Only the existing pcbnew deprecation warning.
- `build/local-power-reuse-tests-20260914.log`: 137 passed, 4 skipped.
- Additional focused run after hostile-reuse cases were added: all 30 tests in
  `tests/test_local_power_prefix.py` passed. Counts overlap and are not summed.
- Reuse tests independently reject a changed authority hash, changed power
  geometry, missing parent copper, moved placement, pair regression, score
  regression, failed source/sink connection and failed refill.
- `build/local-power-reuse-control-20260914.json`: all four native probes
  exactly match `build/fixed-relief-control-20260913.json`; PCB SHA unchanged,
  0 DRC, 0 opens, 615 tracks, 226 vias, 1242.073 mm. Existing broader
  pair/release flags remain false; this is nonregression, not renewed signoff.
- `build/local-power-reuse-generalization-20260914.json`: 56 core modules,
  zero core violations. The broader audit still reports 380 runtime-policy
  violations and 23 physical-engine violations. Whole-pipeline generic and
  release completion are not claimed.

## Review artifact

Dashboard ID: `20260914-pcie2-automatic-local-power-barrier`.
This is the automatic pre-long-pair checkpoint: 0 DRC, 137 opens.
It is explicitly labelled partial routing, not a completed routed board.
Windows image:
`C:/Users/Admin/Documents/CEC-Board-Reviews/20260914-pcie2-automatic-local-power-barrier/render.png`.

Latest full-attempt diagnostic ID:
`20260914-pcie2-local-power-critical-current-partial`, 0 DRC / 102 opens.
Its image is explicitly labelled partial/not released and carries its saved
PCB hash. It is not substituted for the full pipeline's rejected output.
Windows image:
`C:/Users/Admin/Documents/CEC-Board-Reviews/20260914-pcie2-local-power-critical-current-partial/render.png`.
Dashboard HTTP 200 was reverified after publication.

EPS and ATX dimensions and mating geometry have not been changed in this
slice. Their previously observed fixed-terminal native conflicts remain an
independent mechanical/electrical blocker; no routing result overrides them.
