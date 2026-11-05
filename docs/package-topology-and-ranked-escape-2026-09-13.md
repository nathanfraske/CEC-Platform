# Package-local topology and exact ranked escape search

## Outcome and scope

Three reusable construction/search changes were implemented. Both retained
Hub and 12VHPWR inputs now construct all four USB package-local links, but
**neither trial admitted a complete new critical pair**. No residual-routing
wave, placement ECO, outline expansion, or fabrication promotion followed.
Failed transactions roll back their signal copper and supporting ground vias.

The final saved Hub trial is byte-identical to its refill-only control, not a
new routed board. The 12VHPWR trial is byte-identical to its input. Consequently
there is no new board image to present as routing progress.

## Root causes and generic repairs

1. **Local physical obligations were completed too late.** The previous Hub
   receipt recorded both external USB legs, then refused two duplicate-pad
   links at its reversible connector. A long owned signal occupied the
   duplicate's escape space. The intermediate protection array was closed
   first, but the terminal connector was not. On an in-memory copy of the
   same retained input, local-first construction closed all four links in
   0.117 seconds, with eight segments, zero vias and no local refusals.

   `precision_route_board` now calls the shared guarded same-footprint linker
   for the entire declared pair before constructing external legs. This is
   topology-selected, not a connector/refdes allowlist. The external router
   sees that real copper as an obstacle. Failure prevents external work or
   rolls back the whole new transaction; all incoming copper survives.
   Final physical ownership, geometry, skew, coupling, refill and independent
   checkpoint gates remain mandatory. The receipt is `package_pad_preclosure`.

2. **Pair identity was inferred inconsistently between stages.** The precision
   router recognizes `/USB_DP` and `/USB_DM`, while the old local linker
   recognized `_P/_N` and CAN spellings but silently skipped that USB spelling.
   The first 12VHPWR production replay reported zero local groups, not successful
   physical closure. The linker now accepts the caller's explicit
   `pair_declarations`. Arbitrary declared net names receive the same atomic
   behavior; conventional DP/DM and D+/D- spellings also work for legacy callers.

   Declarations require distinct nonempty names and unambiguous membership.
   A heuristic cannot capture a member assigned by explicit authority. Both
   members must be inside an explicit `include_nets` scope. Malformed or
   conflicting declarations fail before mutation. The corrected 12VHPWR native
   run constructs four local links instead of silently skipping them.

3. **Exact pair selection did unnecessary dominated work.** A live native
   stack sample found the solver in `_joint_endpoint_escape`'s pairwise crossing
   loop. Previously it tested all combinations, then minimized a score that
   already depended only on member lengths and headings. `_ranked_joint_escape`
   precomputes those metrics, sorts by the identical complete objective and
   deterministic path tie-breaks, and stops at the first mutually legal pair.
   This is the exhaustive argmin over the bounded candidate domain, not a
   heuristic replacement for collision checks. Crossing, spacing, coherence
   and wall-clock deadline guards still run before acceptance.

   Receipts distinguish available/ranked/actually checked combinations and
   objective-pruned combinations. The old `path_pairs_checked` was simply the
   Cartesian product size even if time ran out; it now counts actual checks.

No board-specific coordinates, reference designators, current budgets, trace
width exceptions, relaxed pair limits or manufacturing waivers were added.

## Validation and measured limits

- Synthetic native-package tests cover four orthogonal rotations, CAN names,
  conventional suffixes, DP/DM and arbitrary declared names; external-order
  observation; refusal before external work; signal/ground rollback; explicit
  net scope; invalid and conflicting declarations; and authority versus naming
  heuristics.
- Ranked-search tests compare against an exhaustive oracle with deterministic
  shuffled input order, five rotations, three skew policies, straight/crossed
  domains, strict spacing, heading and coherence constraints. Expired budgets
  return no unchecked result; completely blocked domains still receive every
  necessary check.
- The local-selector benchmark's open 32x32 domain falls from 1,024 checks to
  one, with identical output. Median time over 15 repetitions is 23.919 ms
  exhaustive versus 1.652 ms ranked (about 14.5x locally). The fully blocked
  domain cannot prune: 22.707 versus 24.409 ms, about 7.5% slower from ranking
  overhead. **This is not a whole-board speedup claim.**

Benchmark evidence: `build/ranked-escape-benchmark-20260913.json`.

### Native retained-board trials

| Board | Local USB closure | Saved result | Remaining blocker |
| --- | --- | --- | --- |
| Hub | Four links, eight segments, zero vias | 254 opens, zero structural DRC; refill-only, no added copper | Long protection-array-to-MCU leg; one bounded order completed the short leg before rollback |
| 12VHPWR | Four links, twelve segments, zero vias | 224 opens, three inherited structural DRC; unchanged PCB | External escapes and matched signal-via/ground-return field search |

Both production-constructor trials used a 240-second pair search cap and the
existing exact copper/placement inputs. Whole helper runtimes were 239.47 s
(Hub) and 129.22 s (12VHPWR). No new complete pair was selected. The 12VHPWR
inner/back-layer transition receipts show zero accepted source portals:
165/174 and 161/170 inspected candidates respectively failed signal-via-field
clearance, and three per layer failed the required nearby ground-return check.
The far endpoint was not screened in those exhausted phases. Endpoint POFV was
independently unqualified; its process check was not bypassed. These are bounded
search failures, **not a proof that either board is globally unroutable**.

Evidence:

- `build/package-ranked-native-20260913/hub/checkpoint.json`
- `build/package-ranked-native-20260913/12vhpwr/checkpoint.json`
- `build/package-ranked-proof-20260913/report.json`

The progress proof independently refills disposable controls and compares saved
PCB geometry. Hub's 27 raw-open reduction is entirely fill cache; both boards
receive zero qualified routing credit. No original board is refilled in place.

The large native trials preceded the final negative guard against heuristic
capture of an explicitly owned member and propagation of search counters to
compact receipts. Those two final changes received targeted tests; they are not
misrepresented as present inside earlier native trials.

### Protected control and regression

The archived PCIe control remains at SHA256
`d6bc7c2df081a5c9f8ec32da8586071464c5fe8ba8dc3383c17ffdcb809789ea`.
The ranked-engine control replay's four probes exactly equal the previous
baseline, including zero DRC/zero opens. Its broader release result remains
false; this work does not retroactively certify it for fabrication.

The combined regression before the final negative guard passed 1,166 tests
with three skips, one SWIG deprecation warning and ten subtests. A subsequent
targeted run passed 332 tests and ten subtests. Final combined results are
recorded below once complete.

Completed verification:

- Combined regression after the declaration guard and ranked-search counters:
  **1,167 passed**, three skipped, one SWIG warning, ten subtests, 116.65 seconds.
  Evidence: `build/package-ranked-final-complete-tests-20260913.log`.
- The final preflight handoff now preserves `package_pad_preclosure` in its
  compact receipt instead of discarding the renamed field. It retains support
  for historical flow-through receipts. The affected preflight, evidence,
  package, ranked-search and precision tests passed: **194 tests**, one SWIG
  warning, two subtests, 11.35 seconds. Evidence:
  `build/package-ranked-final-handoff-tests-20260913.log`.
- Protected-control replay immediately before that metadata-only handoff
  addition: all four probes exactly equal the prior control; generalization
  passes, broader release remains false. Evidence:
  `build/package-ranked-final-control-20260913.json`.
- Rechecked original hashes: Hub
  `630384765baf0d55b1a5cb8d019489e63c12ef51f274d7e977c063bbd56a84fd`;
  12VHPWR
  `1b1da8a82c3899d70ea3b81abd69be25f98a378dae72170281cc8c31009b85f6`.
  Both are unchanged from the retained inputs; protected PCIe hash is unchanged.
- `git diff --check` passes. Routing and regression jobs have completed. No
  unattended repetition was left running. The three main new native diagnostic
  directories total about 40 MiB; WSL has approximately 73 GiB free. No unrelated
  files were deleted, no dependencies installed, and no commit/push performed.

## Next constructive slice

Use the exact failed portal-field witnesses to build a bounded, clearance-aware
signal-via plus return-via placement search. Source/end polarity and layer
classes must receive fair opportunity without repeatedly spending their entire
budget on one blocked field. Couple this to continuation feasibility for the
Hub's long leg, preserving all local package copper and power-prefix authority.
Do not relax clearance/return requirements, promote a local link as a complete
pair, or rerun unchanged board-wide campaigns as a substitute for that repair.

PCIe current-corridor and EPS/ATX fixed mating-geometry blockers were not modified
or retested as new board-wide waves in this slice. Existing width and mechanical
limits remain in force. No old board fallback or replacement image was published.
