# Union-aware local-return placement proposals

## Native obstruction and bounded counterfactual

The retained PCIe3 post-power failure is caused by the C2 ground-return portal
for U3.5 encountering two adjacent B.Cu `/SENSEC3_HI` reservation rectangles.
The native refusal names `[63.7, 11.7, 82.1, 18.1]` and
`[64.5, 18.1, 82.1, 18.9]` mm. These coordinates are diagnostic evidence only;
none are embedded in the implementation. Original artifact identity remains
`52c46b345034021c335698faa70a7480a1728d5ca40ea839ffec5d6c627bd50a`.

`build/post-power-cell-screen-20260916/report.json` tests the existing complete
craft repair at this boundary with 16 proposals, one round and one epoch.
It evaluates 20 legal variants and accepts none. Therefore simply wiring that
same repair into every power transaction is not an evidenced improvement.
The current post-authority automatic craft hook only recognizes body/pour
failures, not structured return failures, but broadening that hook alone would
add cost without resolving this observed case. It was not broadened.

The proposal generator did reveal a reusable geometric defect: it computed an
exit from each failed reservation rectangle independently. Leaving one tile
can enter the next tile of the same conductor. Repeating that operation spends
trials on known-invalid return portals rather than the conductor's actual edge.

## Generic change

`axis_exits_from_rect_union` in `cec_placement_search_domain.py` merges inflated
forbidden intervals along each axis through a proposed portal. It selects the
ends of the connected interval containing that portal. This preserves concave
open space and genuine gaps rather than replacing the whole union with one
oversized bounding box.

`cec_local_return_feedback.move_specs` uses the union of valid, structured
reservation rectangles from that failed cell's native certificates. A rotated
portal is checked against the whole known union too. Single-rectangle cases
retain their prior proposal geometry. Fixed owners, full-cell transforms,
displacement limits, finite trial limits and exact full-board admission remain
unchanged. `reservation_union=False` exists for controlled A/B experiments;
production uses the union by default. These are proposed endpoints, not proof
of a legal stub, swept path, via, complete cell or rebuilt power layout.

No board identity, refdes, net name, coordinate, new fabrication limit or
clearance waiver is part of the algorithm. Its synthetic tests include tiling
invariance, tile order, concave unions, true gaps, gap closure by clearance,
invalid geometry, full-cell ownership, fixed members and bounded budgets.

## Evidence and limitations

`build/return-union-qualified-comparison-20260916.json` records 68 unique native
portal/rotation domains; 25 expose single-tile exits into another known tile.
The union endpoints avoid those known rectangles. This is proposal-quality
evidence, not 25 solved board failures.

The same 16-trial full craft screen under the new generator evaluates 22 legal
variants instead of 20, but still accepts **zero**. The ground-return blocker
remains. Evidence: `build/post-power-cell-union-screen-20260916/report.json`.
Do not rerun this unchanged screen or claim an accepted PCIe3 improvement.
The best refused *moved* finalist and its complete native certificate are now
retained in `build/return-union-refused-finalist-20260916`. They expose a third
B.Cu reservation rectangle, `[74.1, 18.9, 82.1, 27.7]` mm, that was absent from
the original truncated first-blocker samples. A proposed dogbone near
`[74.416217, 19.599999]` clears the two known tiles but meets this third one.
This is another reservation conflict, not evidence that the ground gate is
overly strict. The via guard consumes `cec_power_guard_geometry.reservations`,
including the complete frozen reservation geometry; body/pour evidence is a
different projection and must not be substituted casually.

Next work is to feed that same complete, identity-bound reservation set into
placement proposal generation rather than relying solely on the truncated
native refusal sample. The current union improvement is deliberately described
as **known** reservations, not complete obstacle discovery. Do not rerun this
screen until that missing dependency has actually been addressed. No guard was
weakened, no reserved bus moved and no failed finalist promoted.

Four current board families were replayed concurrently through native physical
admission; complete before/after reports are identical. Hub receives the same
48-proposal cap, while the currently craft-clean PCIe2/PCIe3/VHP inputs generate
no ground-territory proposals. EPS/ATX remain explicitly interface-held and are
not admitted to downstream routing. All six source and hierarchy signatures
are unchanged. Receipt: `build/return-union-replay-20260916/report.json`.

The protected historical PCIe2 control's PCB hash, complete probes, regression
and generalization reports are identical to the preceding control. Its existing
broader release holds remain; parity is not fab approval.
`build/return-union-control-20260916.json` and the qualified comparison contain
the receipts. No geometry is promoted and no new preview is published because
there is no accepted changed board. Keep the current canonical continuation
plan and the existing six-board review gallery.

**343 tests pass** in 510.18 seconds, including loaded-native decoupler and
frozen-domain regressions. Test log: `build/return-union-tests-20260916.log`.
Initial focused suite: 80 tests pass. All workers finished; 66 GiB remains free.
