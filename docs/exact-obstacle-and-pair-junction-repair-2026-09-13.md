# Exact obstacles and transaction-owned pair junctions

## Outcome and scope

Five reusable routing/placement/reporting changes were implemented. A full six-main-board campaign completed before the final junction-finishing integration. **No board was admitted to residual/general routing.** A subsequent native test of the integrated code independently admits the 12VHPWR CAN-internal pair, with four fewer opens and no added DRC findings. This is a partial critical-route proof, not a complete routed or fab-qualified board.

The campaign uses the current BETA manifest and explicit retained inputs. All six source-intake checks passed and every child reports unchanged source/engine signatures. No old schematic was substituted. No board outline, BOM, current requirement, copper width, terminal footprint or mating-width limit was changed. The protected PCIe 2-port control was not edited.

## Root causes and fixes

1. **Exact obstacle union.** `cec_fr._merge_tight_boxes` compared the bounding rectangle area with 1.15 times the sum of both input areas, double-counting their overlap. Repeated merges could fill genuinely empty routing space. On 12VHPWR, this created an F.Cu guard from approximately (0.95, 1.9295) to (41.7000, 50.0544) mm, covering both internal-CAN resistor branch pads. Merging now requires exact containment or a shared complete axis interval. Synthetic random-union tests and native replays prove that merged coverage equals raw obstacle coverage. Input track AABBs remain conservative; this does not claim exact curved/diagonal obstacle silhouettes.
2. **Bounded native tree orders.** The native-pad tree now tries topology-derived backbone-first and local-first orders under one shared deadline, with atomic rollback including supporting return vias. It still tests actual native layer domains before transitions and retains all whole-pair gates. In the measured 12VHPWR success, backbone-first exhausted its share; the local-first alternative found the compact transitioned route. The improvement must not be attributed to backbone-first alone. Runtime budgets still influence which candidate is found.
3. **Pre-rollback connectivity evidence.** Every completed native tier connectivity check can retain per-net copper counts, seed pad and unreached pad UUIDs/coordinates. The staged router attaches that evidence to later refusals and its durable journal. The original CAN backend had connected the transceiver to the choke but omitted the resistor branches; incomplete-net rollback then erased that unqualified prefix. Thus the final “no track segments” failure was a consequence, not the original cause. No connectivity gate was weakened.
4. **Complete-cut search allocation.** A multi-owner exact-envelope placement pack has its own evidence-derived budget group instead of competing only with cheap rotations of its first reference. This gives the complete ablation witness a bounded share of trial compute. The native PCIe 2-port pass evaluated four complete packs; none earned full admission. More proposals/legality are not represented as electrical closure.
5. **Transaction-end junction normalization.** `cec_terminal_overhang` trims only explicit newly generated straight-track overhangs outside the extrema of real same-net junctions. Pad/barrel/zone contacts veto trimming; every existing straight-track contact must remain. An exposed unanchored degree-two acute corner may then move to a guarded octilinear path with the same outer endpoints, width, net, layer and UUIDs. Exact foreign-copper, board-edge and reservation guards apply. This occurs only after the complete pair's physical-pad obligations exist, never while virtual portal legs are incomplete. Whole-pair ownership, geometry, detour, coupling and saved-board DRC remain authoritative. Existing copper is outside mutation scope.

These algorithms contain no product/refdes/coordinate repair case. References and coordinates in this document identify evidence, not production exceptions.

## Native before/after evidence

### Artificial guard removal

Production tier replay on the unchanged 12VHPWR input:

- Before: 570 guards; transceiver/choke connected, both resistor branches missing. Sanitization and octilinear cleanup removed zero items. Both nets correctly rolled back.
- After exact merging: 1,002 guards; all three pads of each CAN-internal member connected. Native completeness passes; the independent pair gate still rejects the ordinary backend's 4.57 mm skew and 5.1% coupling. The parent is retained.
- The newer tier journal records both nets complete before that pair-physics refusal, distinguishing it from the original branch-connectivity failure.

Evidence: `build/pair-tier-forensic-20260913/{hpwr,hpwr-exact-boxes,hpwr-journal}/`.

The read-only obstacle replay includes all six current main-board inputs plus the protected control. Exact/raw unions match on every layer. Current locked-net guards on the protected control had approximately 2,512.576 mm² of artificial extra blocked area summed across layers; 12VHPWR had approximately 1,247.397 mm². Other retained placements have no locked track prefix, so a separately labelled hypothetical-all-net-ownership replay exercises their nonempty pad domains. Those hypothetical results are not claims about currently active guards. Evidence: `build/obstacle-union-replay-20260913/`.

### Independently admitted CAN-internal prefix

The integrated production solver was tested from the retained current 12VHPWR placement, not from a hand-edited route. It completed in 54.573 seconds and generated 39 locked copper items including vias. Its normalizer trimmed one overhang and reseated one exposed corner.

Independent saved-artifact proof, after the normal project-rule finalization and zone refill:

| Check | Before | After |
| --- | ---: | ---: |
| Native DRC findings | 3 | 3 |
| Open connections | 228 | 224 |
| CAN-internal independent pair physics | Unrouted | Pass |
| Component placement / protected power prefix | Original | Unchanged |

The three retained DRC findings are pre-existing copper-edge clearances. Two dangling-end warnings first appeared in an unfinished diagnostic artifact; trimming alone cleared them but exposed an acute bend, which the pair gate correctly rejected. The combined guarded normalization passes both checks. A raw unrefilled diagnostic also produced stale plane/via collisions; normal production finalization clears those and is mandatory before comparison.

The canonical integrated result and proof are `build/pair-precision-forensic-20260913/hpwr-integrated/` and `build/pair-independent-proof-20260913/hpwr-integrated/`. Both input files remain unchanged. The independent proof has `pair_admitted=true`, but deliberately keeps `release_accepted=false`.

Separate 120-second-budget probes of the remaining external CAN and USB pairs still refuse after 57.512 and 68.667 seconds respectively. CAN's native tree cannot complete its remaining edge domain; USB's second flow-through leg remains unqualified. Successful CAN-internal copper was preserved in those input copies. These are bounded search failures, not proofs that the board is unroutable.

## Full six-board campaign

Campaign: `build/obstacle-backbone-suite-20260913/`. Four concurrent board jobs, 24 craft trials, four requested route passes, 1,200-second board-job limits. Junction finishing was integrated only after every campaign process finished.

| Main board | Elapsed | Result |
| --- | ---: | --- |
| Hub | 500.7 s | No accepted change. CAN still refuses; the route-awareness model also reports two unresolved critical PSU_5V_KVM edges. |
| 12VHPWR | 658.7 s | Constructive pair refusals fall from three to two. Critical-only fallback runs, but general routing remains blocked. Later integrated isolated proof admits CAN-internal as described above. |
| PCIe 2-port current candidate | 294.8 s | 24 trials, four complete joint packs; 21 legal trials, zero electrical improvements. Two power-corridor failures remain. Input retained. |
| PCIe 3-port | 1,145.3 s | Retained craft checkpoint clears three detection-cell findings and reduces decoupling findings from two to one. Three power-corridor failures remain. Final placement measurement had only 46.4 seconds left and exhausted that remaining operation budget. |
| EPS | 18.2 s | Native fixed terminal pad shorts stop intake to placement/routing. No replacement board generated. |
| ATX 24-pin | 17.5 s | Native fixed terminal pad shorts/clearances stop intake to placement/routing. No replacement board generated. |

The PCIe 3-port retained checkpoint is SHA256 `2f7299fd65576ae36759d2daaa98f0fe605c4005224aedc79641c6479107a83f`. Its checkpoint receipt distinguishes admitted local craft work from overall routing admission. No source or engine receipt changed during the campaign.

A fresh standalone native measurement of that exact checkpoint completed after the campaign. It confirms zero courtyard/native pad faults, three power-corridor failures, zero detection-cell violations and one decoupling finding. Source content remained unchanged. The craft gate still fails power-body clearance, so the timeout was not the only thing preventing routing. Evidence: `build/pcie3-checkpoint-measure-20260913.json`.

Review gallery: `C:/Users/Admin/Documents/CEC-Board-Reviews/obstacle-backbone-suite-20260913/all-boards-7a1ce8ce774c4dbd.png`. Native no-body views were visually inspected. All six dashboard pages and actual image endpoints returned HTTP 200 from Windows. EPS/ATX have explicit no-output cards; PCIe 3-port is labelled budget-exhausted checkpoint. These views are not represented as fully routed boards.

## Validation and remaining boundaries

- Initial combined tests: 730 passed, one KiCad SWIG deprecation warning, two subtests. Integration-focused tests: 161 passed, one warning, two subtests. The new native junction tests cover protected scope, contact retention, layer separation, plated pads, rotation/reflection, reservation/foreign-copper refusal and invalid policy input.
- Final integrated regression: **748 passed**, one KiCad SWIG deprecation warning, two subtests, 106.42 seconds. Log: `build/exact-junction-final-tests-20260913.log`. `git diff --check` passes. All launched campaigns and diagnostics have completed; no routing wave is left running.
- Final protected-control report: `build/exact-junction-final-control-20260913.json`. All four probes (`score`, `constraints`, `route_quality`, `fab`) exactly equal `build/terminal-geometry-control-final-20260912.json`. Protected board SHA256 remains `d6bc7c2df081a5c9f8ec32da8586071464c5fe8ba8dc3383c17ffdcb809789ea`, with zero DRC and zero opens.
- The historical full-pipeline generalization audit remains release-failing: 380 runtime findings and 23 physical findings. Passing the new generic regressions does not mean the whole historical implementation is now generalized or fab-qualified.
- The main campaign occupies approximately 31 MiB; the forensic folders are small tens of MiB. WSL retains approximately 74 GiB free. No new installation, commit, push or recurring automation was made.
- EPS/ATX require a joint main/daughterboard mating solution. Their existing width/datum limits remain unchanged. Larger isolated terminal pitches previously passed native samples, but those samples are not a complete mechanical fit qualification and do not authorize an outline increase.
- Next architectural boundary: retain independently qualified partial critical prefixes across recovery attempts without granting whole-board routing admission. The present preflight can prove one pair and still discard that useful in-memory construction when another pair fails; repeatedly rerouting the same proven prefix wastes compute. This needs an explicit hash-bound partial checkpoint, not an `ok=true` shortcut.
- Remaining routing work: external CAN/USB topology/escape search, Hub's two critical supply-access model refusals, and joint power-corridor/cell placement on both PCIe candidates. Do not start unrestricted residual routing merely to claim every board entered a router.
