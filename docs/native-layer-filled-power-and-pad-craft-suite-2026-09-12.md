# Cross-board native routing and placement repair slices

## Scope and safety

**Final outcome:** seven shared repair/reporting slices implemented; all six current Standard mains exercised. 12VHPWR reached and completed two critical-only routing waves, but no board was admitted to residual routing in these campaigns. All campaigns have stopped. EPS/ATX still need an authorized joint mating-layout resolution; none is fab-qualified by this work.

This work uses the six current Standard main boards from the BETA manifest. It does not substitute archived schematics or a protected review board for a current candidate. ARGB has no PCB in the current manifest; the output daughterboards are mechanical/electrical dependencies, not six additional signal-routing targets.

No BOM, power-budget assumptions, current requirements, outline dimensions, terminal pad/drill geometry or mating limits were changed. Native shorts and clearance failures remain hard gates. EPS and ATX are held for a joint main/daughterboard interface decision; increasing daughterboard width has not been authorized.

## Shared changes

1. **Native pair-tree layer search.** Each edge intersects the real terminal copper-layer domains. It tries common native layers without transitions before transition-enabled attempts, fairly divides a bounded deadline, and rolls failed additions back. Attempt evidence distinguishes refusal from exhausted search budget. This is not a forced-route bypass.
2. **Verified interface ECO dispatch.** The suite reads and verifies the input's interface-ECO status. A derived board whose route authority was invalidated goes through placement reconstruction using its retained seed. Ordinary derived inputs are unchanged; stale hash/rule status fails before launch.
3. **Post-fill rated-domain connectivity repair.** Exact-fill admission now attempts one bounded repair for each complete, available but disconnected current authority. Repairs run on disposable copies. Acceptance requires exact connectivity, preserved existing copper and placement, qualified current widths, and independent non-regressing DRC/structural scoring. The original current contracts remain authoritative. There is one total time budget, not a repeated unchanged repair loop.
4. **Native pad faults participate in craft repair.** Native pad-to-pad electrical findings now contribute to scoring, proposal generation, worker admission and blocker attribution. Conflict identities survive native UUID normalization. External conflicts move an owning device and assigned bypasses together; an internal owner/cap conflict can reseat the cap while complete pin-locality checks remain active. New pad-fault identities reject the trial even if its decoupling score improves.
5. **Fair critical-route fallback budgets and durable traces.** Legacy fanout no longer consumes all time before POFV, remote-layer portals and grid fallback are considered. Layer/transition flags, status and timing survive trace compaction. Budget exhaustion is not reported as proof of geometric impossibility.
6. **Bounded larger corridor cuts.** Exact ablation found a five-independent-owner obstruction on the current PCIe 2-port input, but craft repair silently limited wide cuts to four roots. Root count is now a policy parameter (default eight); complete combination coverage has a separate 4,096-state budget. Small products preserve exhaustive ordering; larger products use a deterministic displacement-ranked frontier. Native courtyard, protected-current, complete craft and electrical admission still decide acceptance. Search reports distinguish exhaustive from bounded coverage.
7. **Durable tier-failure checkpoints.** After the campaigns, the staged router gained an atomic `.tier-progress.json` beside its output, updated when a tier starts and whenever a tier result is appended. Recovery links to it before routing. It records the source hash, completed/refused tier details and current tier. An interrupted snapshot stays explicitly `running`/`progress_only`; even a finished journal has no fabrication-release authority. The returned report converts its internal checkpointing list to a plain list for process portability. A test exposed a missing output-directory creation, which was corrected; scratch DSN/SES retention is not required.

These changes contain no product/refdes/coordinate repair case. Test-board references below identify evidence only.

## Native proofs

- Hub's exact-fill power domain had three disconnected components: one attached to the regulator and two isolated contacts on the same mezzanine connector. The ordinary rated-domain worker closed it in approximately 1.51 seconds. Independent checks preserved all 16 existing copper items and every placement; current-width checks passed for 12 segments, including four contract-qualified neckdowns. The integrated production admission replay also passed with its source untouched. Evidence: `build/filled-authority-probe-20260912/hub-standard-rev2/` and `build/filled-power-admission-replay-20260912/hub-standard-rev2/report.json`.
- The 12VHPWR U5/C27 pad fault was **already present before the first pass**: 0.1708 mm against the actual 0.2 mm rule. The first pass did not introduce it. Evidence: `build/native-craft-transition-20260912.json`.

## First complete six-board pass

Campaign: `build/native-layer-suite-20260912/`. Four concurrent jobs, 24 craft trials, four route passes requested, 1,200-second per-board job limits. Only the first two changes above were active during this pass. Source and engine receipts remained unchanged for every child.

| Board | Elapsed | Result |
| --- | ---: | --- |
| Hub | 473.7 s | Placement craft passed; exact-fill power connectivity failed; CAN probe exhausted its budget. |
| 12VHPWR | 422.1 s | One craft improvement; pre-existing native pad-clearance fault remained. |
| PCIe 2-port current candidate | 353.9 s | Verified interface-ECO reconstruction passed; two power corridors remained blocked. |
| PCIe 3-port | 1,149.6 s | Work retained in a certified craft checkpoint; placement measurement ran out of operation budget. |
| EPS | 13.4 s | Rejected early for fixed terminal pad shorts. |
| ATX 24-pin | 13.5 s | Rejected early for fixed terminal pad shorts/clearances. |

No board entered residual routing. The review gallery labels blocked placements and checkpoints explicitly; EPS/ATX cards state that no new board was produced rather than substituting an older image.

## Second complete pass and larger-cut replay

Campaign: `build/native-craft-suite-20260912/`. Four concurrent jobs, eight trials, four passes requested, 600-second per-board limits; retained first-pass work was used as input. Engine changes were applied only between complete campaigns.

| Board | Elapsed | Change and remaining blocker |
| --- | ---: | --- |
| Hub | 375.5 s | Exact-fill route authority now passes. CAN still refuses with exhausted probe budget; two other critical connections are unresolved in the route-awareness model. Residual routing stays blocked. |
| 12VHPWR | 569.2 s | Native clearance proposal moved the conflicting capacitor 0.05 mm and cleared the pad fault while passing craft. Entered critical-only routing wave 0, with residual held. Only 62.56 seconds remained for recovery; operation deadline stopped it. |
| PCIe 2-port | 116.6 s | No accepted change; the same two power corridors remained blocked. |
| PCIe 3-port | 530.6 s | Accepted an independent decoupler batch. Retained rank changed from four power failures, three missing bypass assignments and ten decoupling findings to three power failures, zero missing assignments and two decoupling findings. Three detection-cell findings remain. No native pad/courtyard defects. |

PCIe 3-port before/after keys are retained in its `craft_repair.rounds` and checkpoint observation; the final live craft report independently confirms the remaining counts. This is progress, not full electrical admission.

The 12VHPWR worker log confirms actual router passes occurred, not merely that a stage was named routing. Its first pair tier was refused by pair-physics checks and the parent was retained. The interrupted recovery report only records the wave as in progress; detailed per-tier evidence is not yet durably streamed before the staged-router call returns. The deadline therefore prevents a complete failure report for this interrupted wave. Do not call the wave closed or assume more time alone fixes pair physics.

The subsequent larger-cut PCIe 2-port replay (`build/bounded-cut-suite-20260912/`) increased proposals from **6 to 282**, including 48 complete joint-envelope packs, with generation taking 2.63 seconds. Eight proposals were attempted; five passed placement legality versus zero before. None improved the full electrical key, so the input was retained byte-identically. This demonstrates added search coverage, not a routed-board improvement or exhaustive infeasibility proof.

12VHPWR's fresh-budget recovery in that campaign completed **two actual critical-routing waves** (45.96 and 47.07 seconds including validation). Both produced the same unadmitted copper geometry, so the existing repeated-geometry stop terminated recovery. No critical result was selected and residual routing remained held. Source board, BETA inputs, placements and engine were unchanged during recovery.

The complete final 12VHPWR invocation finished in 641.5 seconds and retained its input. Its native pad/courtyard checks and placement craft gate pass, with residual routing blocked by the important-route gate. The craft detail still carries route-dependent decoupler findings; a placement-gate pass is not full decoupling/routing signoff.

The full failure evidence is `build/bounded-cut-suite-20260912/12vhpwr-standard/02-placement/priority-recovery-_qyz0oxa/recovery.json`:

- Both CAN pair tiers: one or both legs had no surviving routed track segments. Octilinear cleanup reported zero removed items, so cleanup did not cause their absence.
- USB pair: 9.31 mm skew versus the configured 3.81 mm limit; unequal layer sets; three transition vias on one leg and zero on the other; missing local ground-return vias; 92.8% filled adjacent-ground coverage against the 95% requirement; only 15.1% coupled-route coverage against 80% required.
- These are current project-check thresholds, not newly invented universal PCB design limits. The tiers were rejected and their parent retained. No checker was disabled to claim completion.

## Next implementation boundaries

1. Trace CAN from exported terminal/obstacle geometry through route import and incomplete-prefix restoration; the latest complete logs rule out octilinear cleanup as the cause. Preserve the board's physical layer domains rather than inventing another per-board escape exception.
2. The fallback router can produce geometrically legal but electrically unqualified independent USB legs. It needs joint P/N topology and layer-transition planning before the final pair checker, not looser skew/coupling/reference thresholds or repeated seed changes.
3. Larger corridor cuts now reach real placement evaluation. Further work should improve joint-group selection/legalization and use fixed-obstacle certificates to distinguish movable-cell congestion from an endpoint/interface ECO. The eight evaluated variants are not an exhaustive search.
4. Exercise the new tier journal on the next native routing campaign. The interruption and tier-backend tests cover it, but it was implemented after this turn's native campaigns; it cannot retroactively recover the earlier interrupted wave's missing tier details.
5. Resolve EPS/ATX mating limits jointly with their daughterboards before routing. No amount of signal-router effort can fix a physical short between immutable terminal pads.

## Regression and resource evidence

- Initial combined replay: 644 tests passed. After the power-repair and native-craft changes: **658 tests passed**, one SWIG deprecation warning, two subtests, 107.43 seconds. Log: `build/native-craft-combined-tests-20260912.log`.
- Both fresh protected-control replays exactly match all four prior probes (`score`, `constraints`, `route_quality`, `fab`), not merely the headline DRC count. Reports: `build/native-layer-control-20260912.json`, `build/native-craft-control-20260912.json`; baseline: `build/terminal-geometry-control-final-20260912.json`.
- After larger-cut search: **679 tests passed**, one SWIG warning, two subtests, 114.79 seconds (`build/bounded-cut-combined-tests-20260912.log`). The focused cut/craft/packing batch passed 233 tests. A third protected-control replay (`build/bounded-cut-control-20260912.json`) again matches all four baseline probes exactly.
- **Final code, including tier journaling: 713 tests passed**, one SWIG warning, two subtests, 106.25 seconds (`build/large-slices-final-tests-20260912.log`). The final protected-control report (`build/tier-journal-control-20260912.json`) again matches all four baseline probes exactly. Source/engine receipts for every native campaign child remain unchanged. Consolidated evidence: `build/large-slices-final-receipt-20260912.json`.
- The declared generic core passes, but the full runtime audit still has **380 legacy findings** and `release_ok=false`: `build/native-craft-generalization-20260912.json`. This is not a claim that all historical modules are now generic.
- Protected control remains SHA256 `d6bc7c2df081a5c9f8ec32da8586071464c5fe8ba8dc3383c17ffdcb809789ea`, zero DRC errors and zero opens. Its pre-existing broader release findings remain failures, unchanged. This work does not relabel that legacy result as a current release pass.
- Campaign directories were approximately 25 MiB and 21 MiB during the second pass; the WSL filesystem still had about 74 GiB free. CPU jobs were bounded to four board jobs with two craft workers each; the Hub's route-awareness report selected the GPU backend for roughly 14 million work cells. No claim is made that every phase is GPU accelerated.
- All four second-pass dashboard pages and their actual image endpoints returned HTTP 200 from Windows; payload sizes were 48–67 KiB. Native images were visually inspected. Gallery: `C:/Users/Admin/Documents/CEC-Board-Reviews/native-craft-suite-20260912/all-boards-19b8016b645449b4.png`.
- The final consolidated review includes the latest attempted result for each main board, preserving each campaign identity and the explicit no-output EPS/ATX cards: `build/large-slices-review-20260912/suite.json`, mirrored at `C:/Users/Admin/Documents/CEC-Board-Reviews/large-slices-review-20260912/`. It is a review index, not a new routing campaign or qualification certificate.
- All six final dashboard pages and image endpoints were verified HTTP 200 from Windows. The three campaign folders total about 67 MiB; the consolidated review is under 1 MiB. `git diff --check` passes. No commit, push, new automation, changed outline or relaxed electrical rule was made.

## Open mechanical decision

The actual rotated terminal copper, not just courtyard outlines, still overlaps on EPS and ATX. Native pair-only samples pass at larger separations, but those samples are neither exact minimum-width proofs nor full mating qualification. Existing last-datum limits are retained pending joint main/daughterboard layout approval. Do not shrink annuli, alter the vendor footprint to make a test pass, waive native DRC, or route around a fixed terminal-to-terminal short.
