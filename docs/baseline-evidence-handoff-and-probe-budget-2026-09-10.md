# Verified baseline handoff and bounded proposal screening

## Problem and implementation

The canonical placement stage measured important-route feasibility, then
called an isolated repair that rehydrated the same placement without carrying
that evidence. The repair spent approximately four minutes constructing its
baseline again before it could evaluate alternate placements. The old
process-local finalist cache also bound only PCB bytes and a small set of
analysis settings, omitting executable sidecars and environment overrides.

`cec_route_evidence` now provides a versioned, content-bound certificate for a
completed placement-route measurement. It binds the exact PCB artifact
family, declared schematic hierarchy (including nested sheets), project rules,
footprint/template sources, explicit file-valued recipe dependencies,
configuration, routing environment, all Python engine files, and runtime
versions. Missing optional sidecars are represented, so adding one changes
the fingerprint. Solver effort remains part of the context; execution-only
deadline/diagnostic variables do not. Excluding an already-tried future move
does not invalidate the incumbent's measurement.

The certificate also binds the measurement payload. Incomplete, failed,
modified, missing, or mismatched evidence cannot be reused. A completed
negative result may be reused as negative evidence; this never turns it into
an admission pass. No geometry is rounded and no persistent/global disk cache
is introduced.

The canonical stage passes its certificate to the isolated repair. The
coordinator verifies it against the current source, makes its existing
disposable board-family copy, and issues a receipt bound to that copy. The
worker independently checks the receipt before seeding its baseline. A
changed source during staging or changed dependency during the worker blocks
promotion. Unchanged baselines skip the duplicate constructive solve; stale
or missing baselines take the ordinary fresh-analysis path. The stage also
retains its already-measured original baseline when no new move is accepted.

Isolation now transports explicit configuration fields as well as params:
source netlist selection (including `net=None`), schematic/project paths,
pins, and profile. Reloading only the policy slug previously risked replacing
those explicit choices with loader defaults.

The existing small memory-only finalist cache now uses the same expanded
artifact/source/environment/engine binding. Worker errors and empty results
are not cached.

## Screening versus qualification effort

Native workers receive their enclosing operation deadline. Disposable pair
probes divide a configurable fraction of remaining time across queued batches
and refused pairs, reserving time for exact finalists. The default allocation
uses half of the time remaining after a 60-second reserve; requested per-pair
effort remains the upper bound. If less than the minimum five-second probe
allowance fits, that probe is explicitly not run and cannot pass.

This affects only proposal screening. Exact finalist routing, saved-board
physical/electrical checks, and final-route effort are unchanged. The hard
outer deadline still protects against native work that does not cooperate.
Allocation details, baseline-reuse decisions, and changed dependency sections
are recorded in the normal repair evidence.

## Generality and safety

The new core uses no product, reference-designator, or coordinate selector.
It is registered in the anti-overfit gate. Synthetic regressions exercise
new/changed copper and sidecars, nested and missing sheets, source identity,
netlist selection, policy/environment/engine edits, payload modification,
copy receipts, dependency changes during a worker, and bounded probe batches.

The protected 12VHPWR input and archived PCIe 2-port control remain test inputs,
not targets of manual placement edits. A reusable baseline is not a routed or
fabrication-qualified board; all existing admission gates still apply.

## Additional defect exposed by the native replay

The first unchanged-engine replay (`build/baseline-handoff-20260910-v2`)
measured the baseline in 220.387 seconds. The repair verified/reused it at
3.914 seconds and started its first round at 3.915 seconds. It screened all
16 proposals, completed 14 pair probes, and fully evaluated a finalist. That
round accepted a strict improvement after 543.218 seconds of round work.

The outer loop immediately began round two despite having only approximately
50 seconds left in its 600-second operation allowance. The supervisor killed
it at 600.167 seconds while screening the fourth proposal of that new round.
The final operation report had not yet been written, so the correctly isolated
worker promoted nothing. The source board and engine were unchanged. This
was a lost-progress scheduling defect, not a failed first-round repair, and
not an admitted board improvement. The phase journal makes that distinction
observable.

The generic iterative repair now checks the nearest operation/campaign
deadline before each round. Subsequent-round admission estimates cost from
the preceding measured round with a configurable 1.1 time margin and a
60-second return/save reserve. It returns the already evaluated incumbent
when another round cannot fit; it does not shorten exact routing effort or
pretend that budget exhaustion closes a route. The hard native-process limit
still applies if an individual round overruns its estimate.

After strict outer-loop monotonic verification, one atomic diagnostic
checkpoint retains the accepted poses, full route evidence, and completed
round history. It is explicitly `promotion_allowed: false`; incomplete or
interrupted operations cannot automatically resume/promote from it. The
normal completed worker report and source/dependency checks remain the
promotion boundary. Diagnostic write failure is reported without discarding
an otherwise valid result.

The regression simulates a 543-second accepted round followed by only 55
seconds remaining: exactly one round runs, the improved incumbent is
returned, and a diagnostic checkpoint is retained. A nominally accepted but
non-monotonic result is neither adopted nor checkpointed as an improvement.

## Regression evidence

The final focused suite after the round-budget correction reports **393
passed, 13 skips, and 10 subtests passed** in 61.76 seconds. The only
warning is KiCad's existing SWIG API deprecation. Evidence:
`build/baseline-handoff-final-tests-20260910-v3.log`.

All 13 skips are the old `TestOracleOnHub` class, which references the absent
`hubs/hub-standard/hub-standard.kicad_pcb` fixture and asserts its old physical
layout. KiCad itself is available. These are **not** current-Hub validation
passes, and substituting a current board into those obsolete geometry
assertions would be misleading. A manifest-driven current-suite replacement
is remaining test-coverage work. The exact skip inventory is retained in
`build/baseline-handoff-skips-20260910.log`.

The final PCIe 2-port replay retains the identical board SHA-256, complete
score, and complete constraint report: **0 DRC / 0 opens / 615 tracks / 226
vias / 1242.073 mm**. Its eight pre-existing broader release blockers remain;
it is not newly fabrication-qualified. Evidence:
`build/baseline-handoff-pcie-control-20260910-v3.json`.

The selected generic-core audit is clean. This does not certify the entire
legacy runtime as generic: the broader audit still reports 23 physical-engine
and 380 runtime selector findings, unchanged from the prior control. Its
explicit maturity remains `generic_core_with_legacy_physical_and_integration_debt`.
These scanner findings require separate classification/repair and are not
393 additional tests or fabrication passes.

The earlier invalidation experiment (`build/baseline-handoff-20260910`)
changed the engine during measurement. It correctly returned
`inputs_changed_during_priority_measurement`, issued no certificate, and
launched no repair. The source stayed unchanged. This is evidence of the
invalidation guard, not a successful routing run.

## Final native confirmation and saved-board result

`build/baseline-handoff-20260910-v3` completed the cold measurement in
**220.320 seconds** and the actual isolated repair in **555.858 seconds**,
inside the same 600-second limit. It reused the verified baseline, screened
16 proposals, ran 14 exact pair probes, fully evaluated one finalist, and
retained one accepted round. The next round was refused by the scheduler
with `remaining_budget_preserves_incumbent`, rather than starting and losing
the completed work. The source hierarchy and engine signatures stayed fixed.

This is a limited placement improvement, not critical-route closure. The
automatically generated parallel-link-group proposal reseated two members;
there is no selector or coordinate exception for them in the new code.
Forecast overflow fell from 224,823 to 223,304 units (about **0.68%**), and
residual overuse fell from 89 to 86. **All three critical-pair refusals remain**
(CAN_INT, CAN, and USB in this test input); remaining pair-edge count remains
three. These are route-preflight metrics, not saved-board DRC/open counts.

Independent fresh-process checks of the saved candidate report:

- Pad bounds, courtyards, placement-craft admission, and placement constraints
  pass before and after.
- All **199 protected power-copper primitives** survive with zero missing
  members. Outline and component inventory are unchanged.
- The saved score is unchanged: **4 DRC / 228 opens / 415 tracks / 12 vias**.
  The DRC types remain one clearance and three copper-edge-clearance findings.
- Only the generic proposal's two component poses changed. The protected
  incumbent is byte-identical, and the read-only audits did not change the
  candidate.

Candidate: `build/baseline-handoff-20260910-v3/board.kicad_pcb`, SHA-256
`eb56de3d1173b0a3aa706045c805d228221aef0ecf865cf5e94199d3daf89408`.
Evidence: `result.json`, `repair.json`, and `saved-audit.json` in the same
directory. This remains a placement experiment, not a routed/fabrication
candidate; it has not replaced a canonical BETA board or the PCIe control.

## Actual critical-routing check and next bottleneck

The accepted placement then entered the existing canonical critical-recovery
adapter on another disposable copy, with two waves and a 180-second limit.
It completed normally in **127.877 seconds**; the routing phases took 46.155
and 45.126 seconds. Both waves were blocked by `pair_connectivity` and
`pair_physics`, retained **4 DRC / 228 opens**, and preserved the protected
prefix and footprint poses. The adapter stopped on
`repeated_unadmitted_geometry`; exit 2 means completed search rejection,
not a crash or admission. Source inputs and engine stayed unchanged.
Evidence: `build/baseline-repaired-recovery-20260910/result.json`.

The confirmed gain is therefore safe evidence reuse and retaining a completed
placement improvement inside the bounded operation. It is **not** a reduction
in saved-board violations or critical-pair refusals. Further work should target
the actual coupled-pair failures (internal-tree detour rejection, layered
trunk/escape rejection, and the flow-through pair's exhausted escape search),
using their witnesses and complete physical admission. Repeating identical
routing waves or counting forecast-only placement gains as closure would
misrepresent the result.

Combined comparison: `build/baseline-handoff-closeout-20260910.json`. All
confirmation jobs are finished; no new unbounded campaign was launched.
