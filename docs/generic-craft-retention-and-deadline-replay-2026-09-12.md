# Generic craft retention and deadline replay — 2026-09-12

## Outcome and scope

The production pipeline now retains a revalidated monotonic craft-round winner before optional work can consume the remaining campaign budget. The same 420-second PCIe 3-port comparison that previously retained only an unchanged seed now retains a changed, source-checked **craft checkpoint**: decoupler violations **9 → 8**, with zero courtyard overlaps. This is useful resumable work, **not routing or fabrication admission**.

A separate native replay of the previously generated joint-cell proposal reached **9 → 6** and survived abrupt process exit after checkpoint publication. That is a diagnostic replay, not the automatic campaign's result. The automatic search did not yet reproduce the stronger result within its bounded evaluation prefix.

Hub and 12VHPWR retained byte-identical boards. Neither advanced to residual routing. The protected PCIe 2-port control was not edited. No schematic, BOM, load budget, operating mode, board outline, connector geometry, or electrical limit was changed in this slice.

## Generic changes

- `cec_operation_budget.generation_admission`: honor the tightest enclosing operation/job deadline; reserve configurable certification time (production default 120 seconds); estimate the next cohort from observed elapsed time with margin. No deadline means the requested effort is unchanged.
- `_evaluate_placement_craft_trials`: finite cohorts return completed results in proposal order. Deadline-controlled serial evaluation also uses an isolated worker so it cannot escape the supervisor. Completed peers survive another worker's timeout; deferred proposals are explicitly unevaluated.
- Native trial telemetry records materialization, evidence, total time, cohort duration, funded timeout, and remaining work. Scheduling does not alter the admission key or grant a route.
- `_certify_craft_incumbent`: materialize through the existing frozen-copper guards, regenerate full diagnostic evidence, reject key drift or increased overlap, then invoke the coordinator-only checkpoint callback.
- `cec_placement_checkpoint`: add a `craft` phase between selection and final placement. It uses the existing two-slot, hash-verified, source-checked store. Routing and release flags remain false. Lower phases cannot overwrite a craft checkpoint.
- Main full-pipeline craft entry points carry the callback without serializing it into configuration or native worker jobs. Epochs stop on a depleted evaluation budget instead of restarting.
- After the comparison run, a reporting follow-up propagates exhaustion from atomic, grandchild, and compound lookahead, not only the primary sweep. Otherwise an unfunded lookahead could be labelled a plateau. This follow-up has synthetic coverage; the captured campaign's primary exhaustion already evaluates identically under the new aggregation.

The new scheduling and retention rules contain no product/refdes/coordinate choices. Inputs retain manifest/hierarchy authority and the current derived anchor context. This does **not** mean the entire older runtime is generic: the audit still reports 23 physical-engine and 380 runtime selector findings, unchanged from the preceding audit. The declared generic core passes.

## Validation

The final post-follow-up test run passed **421 tests** in 90.75 seconds, covering craft admission, deadlines, checkpoint corruption/crash recovery, full-pipeline integration, frozen copper, source ECO boundaries, previews, suite continuation, generalization, and the protected fab control. There are 21 new parametrized regression cases in this slice. Evidence: `build/craft-retention-final-tests-20260912.log`. The only warning is the installed KiCad SWIG API's deprecation notice. `git diff --check` passes.

New regressions include:

- Deadline selection, reserved finish time, invalid limits, and ordered completed prefixes with one or multiple workers.
- No launch after an expired deadline; no promotion of a timed-out trial; completed peers remain usable.
- Full native diagnostic-key drift, overlap regression, or materialization failure cannot reach checkpoint publication.
- Coordinator callbacks stay outside worker configuration; exhausted epochs do not restart.
- Two unrelated synthetic families recover committed craft work after abrupt child exit; earlier phases cannot supersede it.
- Exhaustion at each of four evaluation depths remains unproved rather than an exhaustive plateau.

### Native crash/recovery witness

Evidence: `build/craft-retention-native-20260912/report.json`.

- Input is the hash-verified PCIe 3-port checkpoint from `build/current-suite-20260911-d`, SHA256 `8e4a7c148507a917466b87a31b8ed45adb734c771f213c75eb9fd78ae6e69d0b`.
- Replays the prior generated/ranked joint proposal, not hand-authored repair coordinates.
- Production trial materialization took 0.901 / 0.789 seconds; evidence took 22.549 / 23.110 seconds. Both jobs completed in one 24.147-second cohort.
- Full diagnostic certification confirmed 9 → 6 decoupler violations, zero overlaps, and no newly stranded references. The five current-corridor failures remained.
- The process deliberately exited without normal cleanup after publication. A separate process successfully read and verified the complete checkpoint family and current sources.
- Retained SHA256: `09f37aeed1cfa45f9b30a82537b85be976f8d8ee67695eec2c106ab83beb158e`; `source_intake_ok=true`, `routing_admitted=false`, `release_accepted=false`. The input remained unchanged.

## Automatic three-board replay

Evidence: `build/craft-retention-pass-20260912/suite.json`.

Inputs are explicit previously verified current-suite artifacts, not a latest-filename search. Three jobs ran concurrently, with two evaluation workers per board, 12 selected proposals, two rounds/one epoch, and a 420-second cap per board. The legalized evaluation pool can contain more jobs than the selected proposal count. All source and engine signatures were stable for the entire run; no engine editing occurred during it. No artifact was promoted.

| Board | Prior same-cap retained result | This pass | Remaining blocker |
| --- | --- | --- | --- |
| PCIe 3-port | Unchanged seed; 9 decoupler violations | Certified craft checkpoint; **8 violations**, zero overlaps; 420.035 s overall cap | Five current-corridor failures and other craft blockers; final placement stage still unfinished |
| Standard Hub | Unchanged board; priority key `[1,0,0,2,0]` | Byte-identical board; same key; 262.994 s | One declared-priority route refusal and two global reachability failures |
| 12VHPWR | Unchanged seed; priority recovery exhausted | Byte-identical seed; recovery exhausted; 405.288 s | Priority-route checks and bounded critical recovery; no retained repair |

PCIe evaluated 12 of 19 legalized jobs in six cohorts (18.085–24.419 seconds), with **zero timed-out evaluations** and seven explicitly deferred jobs. It reserved the final check, published the improved craft winner, and was later stopped during subsequent placement work. The retained board SHA256 is `6169acff66d450fcc2ce290fca09ba098df05b9d48f6139376f18381f638b8ee`. Proposal generation itself still cost 58.327 seconds for 10,142 proposals.

The measurable improvement here is **retained progress under the same cap**, not a speedup or fab closure. The full automatic path improved one violation; the stronger diagnostic replay improved three. Do not combine those into one automatic result.

Hub's priority measurement consumed 173.155 seconds and proposed no accepted placement move. 12VHPWR's priority measurement consumed 249.692 seconds, leaving only 61.963 seconds for critical recovery, which exhausted that allowance. These costs are upstream of residual routing, not evidence that a full residual routing wave failed.

The production continuation resolver was checked after completion: PCIe resolves the craft checkpoint, Hub the completed-but-blocked placement, and 12VHPWR the verified seed. All subsequent gates still rerun.

## Protected control

Never mutate `build/board-archive/20260831T1619-pcie-8pin-2port-v113-zero-open-v43/board.kicad_pcb`.

Both the initial replay and the final post-follow-up replay at `build/craft-retention-final-control-20260912.json` exactly matched all four prior payloads (`score`, `constraints`, `route_quality`, `fab`) from `build/cell-ranking-control-replay-20260911.json`. The board remains at 0 DRC errors / 0 opens, with its original SHA256 `d6bc7c2df081a5c9f8ec32da8586071464c5fe8ba8dc3383c17ffdcb809789ea`. Broader release acceptance was already false and remains false; that is not waived.

## Review delivery

Fresh native, no-body previews were rendered from the exact retained PCB artifacts, visually inspected, and published with explicit blocked/budget-exhausted labels and hashes. All three Windows dashboard pages and render endpoints returned HTTP 200. Hub and 12VHPWR images represent unchanged retained geometry, not claimed new layouts.

- [PCIe 3-port craft checkpoint](http://localhost:8090/?id=pass-craft-retention-pass-20260912-pcie-8pin-3port-4bd8af45ac)
- [Standard Hub](http://localhost:8090/?id=pass-craft-retention-pass-20260912-hub-standard-rev2-75cbe1cc8c)
- [12VHPWR](http://localhost:8090/?id=pass-craft-retention-pass-20260912-12vhpwr-standard-a1a472fe2e)

Desktop gallery: `C:/Users/Admin/Documents/New project/review-output/craft-retention-pass-20260912/all-boards-619410bdea7b571d.png`.

The campaign used 14 MiB and the native witness 2.2 MiB before archive/render copies. WSL free space remained about 74 GiB. Runs are complete; no unattended campaign was left running by this slice.

## Next bounded work

1. Trace and reduce repeated priority-route geometry work, particularly native shape/portal queries. Cache only immutable, correctly keyed geometry with explicit mutation invalidation and cross-board replay; never cache a success across copper changes.
2. Improve budget-aware proposal coverage so a measured useful joint-cell family reaches exact evaluation earlier without starving other failure families. Keep bounded search and complete-craft admission; do not special-case the diagnostic owner or its references.
3. Resume from the retained craft checkpoint rather than the earlier seed. Preserve frozen power copper and separate placement craft, important-route admission, residual routing, and final fab review.
