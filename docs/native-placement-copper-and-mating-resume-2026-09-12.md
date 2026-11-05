# Native placement copper admission and mating-resume repair

## Outcome

Five shared pipeline changes are implemented and tested. EPS and ATX still require a joint main/daughterboard interface revision; neither is routed or fab-admitted. No board dimensions, footprint pad/drill geometry, BOM, schematic or power-budget assumptions were changed in this slice. Existing board artifacts and the protected PCIe control remain byte-identical.

1. **Native pad-copper admission before route probes.** The existing courtyard oracle ran KiCad DRC but discarded pad-to-pad shorts/clearance findings. `cec_placement_geometry.py` now classifies native pad identities, honors their actual layers/nets/project rules, and retains pad-copper failures as well as assembly failures. The complete structured findings and native report-row counts are retained; only the UI summary is capped at ten entries. The legacy courtyard entry point delegates to this broader check.
2. **Unique generated identities before admission.** Both materialization paths normalize duplicate item IDs before protected-copper admission. Read-only diagnostics normalize only a bounded disposable copy and verify that removing UUID fields makes its PCB text identical to the original. Source files and rule hashes are checked for changes. No clearance rule or physical geometry is modified by identity repair.
3. **Mechanical constraints survive continuation.** New placement-review records carry family, source hashes, resolved pins and outline context. Resumes check that context against current sources/native outline and rebind current declarative interface anchors before repair. Legacy reviews also rebind those anchors. Native position drift fails with per-reference before/after evidence instead of silently unlocking terminals. Whole-turn rotations are equivalent.
4. **Fixed-pad conflicts stop impossible repair loops.** A pad-copper violation within one footprint, or between two fixed anchors, cannot be resolved by ordinary component translation. The full pipeline now fails early with `fixed_pad_copper_conflict` and routes the finding to footprint/joint-interface ECO work. Conflicts involving movable neighboring components remain repairable; they are not blanket-blocked by this rule.
5. **Actual copper envelopes in mating review.** The shared interface audit now checks native terminal pad DRC and measures actual rotated pad extents in the declared row frame. The generic row-envelope screen reports whether conservative separating intervals fit the existing last-datum limit. It does not silently enlarge a daughterboard. Projection is deliberately not represented as proof of exact fit or infeasibility for staggered pads or unknown mixed-part screw-axis offsets.

Reusable code changes are in `cec_placement_geometry.py`, `cec_mating_rows.py`, `cec_full_pipeline.py`, and the existing materialization/audit adapters. The new geometry module is included in the anti-overfit gate. No product/refdes-specific move was added to the reusable engine.

## Native cross-board replay

| Artifact | Courtyard intersections | PTH-in-courtyard rows | Pad-copper rows | New geometry gate |
| --- | ---: | ---: | ---: | --- |
| EPS selected compact trial | 0 | 0 | 48 | Blocked |
| EPS final prior replay | 2 | 8 | 48 | Blocked |
| ATX final prior replay | 0 | 0 | 60 | Blocked |
| Inspected current PCIe two-port | 0 | 0 | 0 | Pass |
| Inspected current PCIe three-port | 0 | 0 | 0 | Pass |
| Protected PCIe two-port control | 0 | 0 | 0 | Pass |

Pad-copper counts are native report rows, including repeated layer findings, not counts of unique short sites. ATX's 60 rows comprise 36 shorts and 24 clearance findings. A pass here is limited to this geometry check, not whole-board release.

Evidence: `build/terminal-geometry-replay-20260912.json`.

Native resume replay restores all eight EPS terminal anchors and the ATX terminal/signal/mezzanine constraints. The regressed EPS final artifact is refused specifically because TB11 and TB21 moved by -0.6 mm; the selected predecessor is accepted by the anchor-consistency check but still refused by the independent pad-copper gate. Evidence: `build/mating-context-replay-20260912.json`.

## Full entry-point replay

Both current compact review inputs passed current-source intake and then failed at the intended immutable-pad boundary, before craft repair or routing:

| Board | Entire invocation | Placement-stage refusal | Source/engine unchanged |
| --- | ---: | ---: | --- |
| EPS | 13.944 s | 0.587 s | Yes |
| ATX | 14.093 s | 0.685 s | Yes |

The roughly 11.4-second source intake remains part of each invocation. These timings demonstrate early failure attribution on these inputs, not a general router speedup. No new routing artifact was created. Logs, pipeline-state failure evidence and the receipt are under `build/fixed-pad-admission-20260912/`.

## Spacing probes and remaining mechanical decision

Twenty-three native pair-only spacing probes were run on disposable copies with the actual project rules and installed orientations. They do not qualify a full row, either board, a mated assembly or a manufacturing tolerance stack.

| Pair class tested | Failing pitches tested | Smallest passing pitch tested |
| --- | --- | ---: |
| EPS T340 force/return | 7.0, 7.5 mm | 7.7 mm |
| EPS T340 same rail | None among 7.0/7.5/7.75 mm | 7.0 mm |
| ATX T340 different rails | 7.0, 7.5 mm | 7.7 mm |
| ATX mixed terminal pair, either end | 8.85 mm | 9.0 mm |

These are sampled passing values, not an exact minimum or a recommended production pitch. Combining those tested pitches as a provisional row allocation would put EPS's last datum at 25.9 mm against its 24.5 mm limit, and ATX's at 46.1 mm against its 43.9 mm limit. That is 1.4 mm and 2.2 mm additional last-datum travel respectively, **before added design margin**. It is not a finalized board-width increase: edge lands, the signal companion, contact-axis offsets and the mated assembly still need joint qualification.

Therefore this is no longer ordinary route cleanup. The next mechanical work must reconcile both mating boards, not move only main-board terminals. Retain the current fixed dimensions unless the owner approves relaxing them; alternatively revisit the qualified footprint/terminal implementation. Do not shrink pads or drill annuli, waive DRC, or claim prototype terminal geometry is sample-qualified.

Evidence: `build/terminal-pitch-probes-20260912.json`. No scratch spacing board was published to the dashboard or retained as a candidate. The small diagnostic harness initially stalled during executor worker recycling; it was stopped and rerun successfully in explicit bounded worker generations. This was not a production routing run.

## Regression evidence and limitations

- **526 tests passed**, one existing KiCad SWIG deprecation warning, 101.04 s: `build/terminal-geometry-combined-tests-20260912.log`.
- New native tests cover different-net overlap, same-net overlap, opposite copper layers, explicit custom clearance, rotated/translated copper envelopes, immutable/movable conflicts, and source/context drift. A fixture initially omitted the `mm` suffix; correcting that fixture made the intended custom-rule test effective. Production rule files were not changed. KiCad documents explicit physical units and native internal units in its [custom-rule syntax](https://docs.kicad.org/master/en/pcbnew/pcbnew.html#custom_design_rules).
- All four fresh protected-control probes exactly match `build/eps-atx-compaction-control-20260912.json`. The PCB SHA256 remains `d6bc7c2df081a5c9f8ec32da8586071464c5fe8ba8dc3383c17ffdcb809789ea`, with zero DRC errors, zero unconnected items, 615 tracks and 226 vias. Current evidence: `build/terminal-geometry-control-final-20260912.json`.
- The protected control's broader release/route-craft findings were already failing under current checks and remain unchanged. They are not hidden by the zero-DRC statement.
- The declared generic core passes the anti-overfit gate. The full runtime still has 380 legacy findings and remains `release_ok=false`; this slice does not claim the entire historical engine is fully generic.
- `git diff --check` passes. No commit, push, automation or unattended routing campaign was started.
