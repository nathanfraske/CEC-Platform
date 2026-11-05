# Required-copper admission for late orientation changes — 2026-09-07

## Root cause and repair

The prior critical-supply cohort exposed a late-stage contract violation: a
pad-topology rotation could be body/legal and shorten its small nets while
preventing construction of required wide power copper. Persisting constructor
refusals made the missing copper visible, but only after the damaging change.

The orientation stage now sends the complete proposed pose map through
`cec_placement_commit.native_admit` before ratifying it. The new engine has no
product, reference-designator or corrective-coordinate selector. Its pure
transaction accepts an authoritative proof callback. The production adapter
reuses the existing native materializer and constructor reports; it does not
invent a second, looser approximation of legal power geometry.

The current integration applies when declared blueprint cells, force lanes or
force rails are enabled. It is **not** a replacement for every legacy pour,
route or SI admission check, and does not make the legacy force-lane producer
itself product-neutral. Ordinary boards without these constructor policies
retain their existing placement/routing checks.

## Transaction and evidence

1. Prove the previous pose map by fresh source materialization. An unqualified
   baseline permits no new orientation changes; it is not silently grandfathered
   into routing or release approval.
2. Prove the complete proposed batch. Passing batches need only two native
   probes, including the baseline.
3. If the batch fails, test each proposed footprint rotation against the
   cumulative accepted state, in deterministic reference order. A rotation
   cannot borrow a proof made before a conflicting rotation was accepted.
4. Keep only proved poses. The saved candidate and review record carry all
   attempted proofs, accepted/rejected identities, reasons and elapsed time.

The default bounds are `placement_commit_max_probes=32` and
`placement_commit_timeout_s=180`. Budget exhaustion preserves only the already
proved subset. Worker crashes, timeouts, missing/malformed replies and invalid
accounting retain the previous pose map. On WSL/POSIX a timeout kills the worker
process group, including its KiCad children. One warm worker amortizes imports;
each probe has a separate temporary board directory, so refused copper cannot
leak into the next proof. Successful workers remove their PID-owned net export.

The adapter forces a fresh export of the current schematic hierarchy rather
than consuming a possibly stale committed netlist. It requires complete
blueprint/force-lane evidence, complete force-rail evidence, native pad bounds
and native courtyard clearance. These are absolute placement/construction
requirements, not a comparison of truncated DRC lists. A required force-lane
policy with no blueprint report now fails rather than becoming not-applicable.

This entry point handles independent single-footprint pose proposals. It must
not split a rigid multi-footprint operation; those require a group transaction.
`ok=false` on the orientation report means the entire requested optimization
was not accepted, not that a proved subset is invalid. Final independent craft
and routing gates still decide whether that subset's candidate can proceed.

The module is registered in the neutral-engine anti-overfit audit and is reached
by the placement stage's transitive import fingerprint, so changes invalidate
cached placement evidence.

## Targeted saved-seat replays

`build/12vhpwr-power-aware-rotation-20260907/001/result.json` and
`002/result.json` execute the actual production orientation hook at saved final
centres, restoring all prior proposed angles before replay—not a named-part
repair. Both source PCBs remain byte-identical.

| Diagnostic outline | Rotations retained | Required power lanes before → after | Native proof time |
|---|---:|---:|---:|
| 58 × 72 mm | 10 of 11 | 5/6 → 6/6 | 23.003 s |
| 58 × 76 mm | 9 of 10 | 5/6 → 6/6 | 20.400 s |

The rejected identity in these reports is FB1, because the authoritative
constructor reports a foreign-pad conflict against lane 6. That identity is
evidence from the board, not an engine selector. Passing rotations are retained.
The reconstructed boards also pass native pad/courtyard checks and retain all
six sensing cells / 444 locked cell segments. These targeted replays are not
full new placements, routed candidates or fabrication approval.

## Cross-board scope and control

The immutable PCIe review control is
`build/board-archive/20260831T1619-pcie-8pin-2port-v113-zero-open-v43/board.kicad_pcb`,
SHA-256 `d6bc7c2df081a5c9f8ec32da8586071464c5fe8ba8dc3383c17ffdcb809789ea`.
`build/power-aware-rotation-pcie-regression-20260907.json` matches the previous
score and eight broader constraint blockers: **0 DRC, 0 opens, 615 tracks,
226 vias, 1242.073 mm**. Diff-pair and release gates remain false; this replay
is a non-regression result, not new fabrication approval.

Read-only production-hook replays are retained under
`build/12vhpwr-power-aware-rotation-20260907/portfolio`:

- The 24-pin retained candidate exercises rejection: current-source
  materialization finds obsolete terminal identities in its old pose map, so
  all 24 proposed rotations are withheld. This is useful fail-closed evidence,
  **not a successful new 24-pin placement**. Its manifest root is outline-less
  staging and cannot serve as a placed control either.
- Hub and PCIe hook compatibility replays do not enable this constructor-policy
  guard, as their current policies use other paths. Proposed poses exist only
  in diagnostic JSON; none is written to the routed/source board. They do not
  establish power-aware repair coverage for every pour implementation.

## Fresh full-placement cohort and independent saved-board check

The canonical entry point completed
`build/12vhpwr-power-aware-full-placement-20260907` from the current hierarchy:
fresh plain/seed-0 placement, explicit replacement authority, four evaluation
workers, candidate-review only. `power-aware-closeout.json` independently
measures the retained native boards and compares the preceding same-size cohort.

| Outline | Complete required power lanes before → after | Accepted rotations | Placement residual | Decoupling findings |
|---|---:|---:|---:|---:|
| 58 × 68 mm | 6/6 → 6/6 | 11/11 | 1, unchanged | 12, unchanged |
| 58 × 72 mm | 5/6 → 6/6 | 10/11 | 0, unchanged | 12, unchanged |
| 58 × 76 mm | 5/6 → 6/6 | 9/10 | 2, unchanged | 12, unchanged |
| 58 × 80 mm | 6/6 → 6/6 | 3/3 | 0, unchanged | 12, unchanged |

All four saved boards have the complete native net/layer/wide-track-width
inventory, six sensing cells and 444 locked cell segments. All pass source
intake and mechanical checks, retain four mandatory mounts and lower-right
outward-facing I/O, and contain 103 source components plus seven mechanical
footprints. All 16 supply-pad distances remain exactly unchanged and within
their source limits. Ground-return distance/access findings are not closed.

The 68/80 mm final poses are identical to their prior cohort. The only final
pose difference on 72/76 mm is the automatically withheld conflicting rotation;
all component centres are unchanged. No additional compaction was attempted or
claimed. The 64 mm connector-bank refusal remains in the search rejection log,
not a proof of the globally smallest possible board.

The complete required-power inventory improves from **2/4 to 4/4 candidates**.
The independent review selects 58 × 72 mm for illustration because it combines
zero placement residual with the smaller outline among those zero-residual
options. Residual is a placement metric, **not the number of unrouted nets**.
Detailed routing, plane qualification, thermal solves and fabrication release
were deliberately not entered with the twelve electrical-placement findings
still open.

The placement stage took **840.025 s**, versus 789.4 s previously (about 6.4%
longer). Native orientation proofs total 50.093 s: 3.736, 22.017, 20.560 and
3.780 s across the four sizes. This slice buys a correctness guarantee; it does
not claim a speed gain. The long legacy placement search remains separate.

Validation: the broad suite reports **652 passed / 14 existing skips**; the
subsequently added cache-dependency test also passes (30/30 tests in the new
module, **653 distinct passing tests overall**). Coverage includes renamed and
translated synthetic identities, interacting rotations, budgets, corrupt
responses, process-group timeout cleanup, actual-stage adapters for all three
constructor policies, isolated trial directories, and review serialization.
`build/power-aware-rotation-generalization-20260907.json` passes the declared
neutral core, including the new module; the full audit still reports 23 legacy
physical and 380 runtime selector findings. No full-pipeline-generic claim is
made.

The exact 72 mm saved PCB hash is
`1424f5ec273c8be995ab1cf191527a1913e111d5d1c0168b77e8d1c1b1883f67`.
Its no-body top/bottom renders carry an explicit diagnostic/not-promoted banner.
The top dashboard artifact endpoint was checked from Windows and returned 200;
Windows render copies were hash-compared to the native output. This is a
direct diagnostic artifact, not a new fab-review archive entry.

## Remaining boundary

Power-lane preservation is separate from local decoupling closure. The prior
native certificates identify the next causal seam: through-board ground-via
access for several sensing supply cells is blocked by locked back-layer power
tracks. POFV process permission does not authorize a barrel through a different
net. Ground-access reservations must participate in the power constructor's
planning, with exact current-width, clearance and connectivity checks on the
result. Do not waive the blockage or grow the board solely to hide it.

The older single-cap owner/follower grid is also still a runtime hotspot. A
live stack during the fresh cohort lands in `_p9b_device_bypass` /
`pads_clear_blueprint_copper`, not the new admission worker. The outline loop
currently generates sizes serially; four evaluation workers do not make that
Python search parallel. Replacing repeated geometric work with cached/spatial
queries and bounded independent searches is a separate performance slice.

No schematic, BOM, cooling assumption, interface direction, mandatory mounting
requirement, canonical PCB or immutable archive is changed by this repair.
