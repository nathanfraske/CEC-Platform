# Route finish scheduling and a wider terminal-domain screen

## What happened to the nine-open candidate

`build/exact-hole-residual-followup-20260916/suite.json` records the prior
canonical attempt ending at **00:37:32Z**, after the 600-second job limit plus
process cleanup/publication. Intake, placement and route preflight passed.
Detailed routing did **not** finish or produce a journal-qualified winner.
All source/hierarchy and engine stability checks passed; all descendants have
exited. The candidate is not fab-ready and has not become the canonical source.

The certificate repair's own report records 221.586 seconds of work and **no
DRC/open-count improvement**: 0 DRC / 9 opens before and after. Its output
report was written after the outer campaign deadline, leaving no time for
the complete route-oracle qualification and journal. This is not a measured
board regression; the board's nine-open diagnostic remains independently
available. It is a failed end-to-end validation attempt.

The review publisher correctly refuses to select an unjournaled intermediate:
`pass-exact-hole-residual-followup-20260916-pcie-8pin-2port-830d32e023` is
explicitly **UNTRUSTWORTHY OUTPUT**, not a new board preview. Do not show its
placeholder as a routed board or recover a candidate by modification time.

## Generic scheduling repairs

1. `cec_operation_budget.optional_work_admission` requires the entire optional
   work allowance plus a configurable finish reserve to fit both the enclosing
   operation and campaign deadlines. A deferred repair is still an unresolved
   obligation, never physical success or proof that routing is impossible.
2. `_route_oracle_certificate_repair` now applies that rule before writing any
   trial files or dispatching a child. A normal 240-second search also reserves
   30 seconds for its report/cleanup and 120 seconds for the caller's final
   qualification. Its parent timeout is clamped to the same enclosing lease.
   Explicit short watchdogs and standalone behavior without deadlines remain.
3. The canonical route ensemble dispatches at most one worker cohort at a time,
   not all seeds into a blind queue. Before another cohort, it considers the
   measured previous cohort duration and the finish reserve. Unfunded seeds
   are reported as deferred; completed candidates remain eligible under the
   **unchanged physical selection rules**. The process watchdog is clamped to
   the available campaign time and is not renewed for each cohort.

No DRC, clearance, current, pair, decoupler, protected-prefix or fabrication
gate is weakened. These changes do not themselves claim improved connectivity,
nor do they guarantee a too-small campaign can complete mandatory work.

## Validation

- **296 tests pass** in the initial combined suite:
  `build/route-finish-budget-tests-20260916.log`.
- After tightening the nonrenewable generation watchdog, **151 tests pass**:
  `build/route-finish-budget-final-tests-20260916.log`. These overlap the prior
  suite; do not add the counts. Tests cover exact cutoff funding, nested
  deadlines, invalid budgets, no dispatch after expiry, unchanged source
  bytes, production-hook child timeouts, bounded one/two-worker cohorts,
  retained completed results, explicit deferrals and native-worker failures.
- The production refusal hook is replayed against all six explicit retained
  source identities with an exhausted lease. No subprocess starts, no board
  changes, and no family-specific exception is used. This is a **dispatch and
  identity** replay, not a native geometric qualification of those six boards:
  `build/route-finish-budget-source-replay-20260916.json`.
- Historical PCIe2 board bytes, complete regression and every probe match:
  `build/route-finish-budget-control-comparison-20260916.json`.
- The declared generic core passes; existing broader release holds remain:
  `build/route-finish-budget-generality-20260916.json`.

## Concurrent mechanical investigation

The earlier transverse pair screen stopped at 2 mm. A new disposable-copy
screen uses the **current hash-bound EPS/ATX inputs**, not the old spacing
study's sources, and tests ±3, ±4, ±6 and ±8 mm while retaining edge-axis pitch.

- EPS T340 and ATX T340 pairs still fail at 3, 4 and 6 mm; **8 mm transverse
  separation passes the pair-only native geometry check** in either direction.
- The ATX mixed terminal pair passes at 6 and 8 mm, and fails at 3 and 4 mm.
- Existing pitches remain 7.0 / 8.85 mm. All source boards remain unchanged.

Evidence: `build/terminal-transverse-domain-probe-20260916.json` (24 cases).
This only demonstrates a wider two-dimensional pair domain worth studying.
It is **not** a complete-row fit, board-outline fit, tolerance-stack analysis,
qualified main/daughterboard transform, contact-depth proof, or ECO approval.
Do not stagger only one mating half, increase dimensions, shrink lands, or
route these boards on the strength of this diagnostic. No scratch PCB was
published or retained as a candidate. EPS/ATX remain held.

## Completed end-to-end validation

`build/route-finish-budget-suite-20260916` tests the scheduling repair through
the canonical pipeline, using the exact same explicit nine-open PCIe2 input
**1e5755748bcc35b3a079b84c918e91df04145e89b75621c47545fd7fee14fd09**,
the same 600-second whole-job bound, two requested route seeds, one route worker,
two placement workers, four craft trials and two passes. The runner is
`tmp/route_finish_budget_followup_20260916.py`.

The run completed at **01:11:28Z** in **426.955 seconds**, without the earlier
600-second timeout. Intake, placement and preflight passed; detailed routing and
independent signoff both completed and correctly retained release holds. The
result is **0 native DRC / 9 opens**, 747 tracks and 386 vias. All local decoupler
cells and the Kelvin/differential-pair score checks pass. Placements, protected
copper and input bytes are unchanged. Gerbers were deliberately withheld.

One seed cohort took 218.136 seconds; the second was explicitly deferred because
189.001 seconds remained against 359.949 seconds of estimated work plus finish
reserve. The optional certificate search was also deferred when its full
allowance was unfunded. The route oracle returned and final qualification ran.
This validates the scheduling repair; it does **not** attribute the earlier
10-to-9-open improvement to scheduling or to the hole-domain change.

Independent evidence: `build/route-finish-budget-native-verification-20260916.json`.
Winner: `build/route-finish-budget-suite-20260916/pcie-8pin-2port/04-route/winner.kicad_pcb`,
SHA **10cf3682c1d7e5e62756733f4a6798fc51d818cf6a5c16d449a2ef41612ff0c9**.
The explicit successor plan is **`build/route-finish-next-inputs-20260916.json`**;
only the PCIe2 continuation row advances. It does not authorize another identical
wave (`launch_authorized: false`). No full cohort remains running.

The nine opens are +3V3 (3), +5VSB (2), /VBUS (2), U4_OV1 (1) and U4_SS (1).
Existing /VBUS covered-backtrack and a locked 112.5-degree GND segment remain,
along with constraint, hardware-qualification and thermal/release holds. Zero
native DRC is not manufacturing signoff.

The dashboard API confirms journal hash verification and the same winner SHA:
`http://localhost:8090/?id=pass-route-finish-budget-suite-20260916-pcie-8pin-2port-dde3edbe34`.
Top and bottom body-free previews were visually inspected; both say BLOCKED / NOT
FAB SIGNOFF. No scratch candidate or old board was substituted for this result.

## Generic duplicate-cleanup hardening

The completed attempt logged a rejected isolated fab-repair variant with exit
code -11. Four disposable replays on the final selected board all exited
normally; the exact pre-variant input was not retained. **That specific crash is
not reproduced or claimed solved.** Evidence:
`build/fab-native-crash-probe-20260916/report.json`.

Inspection nevertheless found two independently reproducible defects in
`cec_fab_repair.repair_backtracks`, repaired without board/refdes/net exceptions:

1. The duplicate key omitted width. Coincident centerlines of different widths
   could delete the wider copper. Width now participates in exact identity.
2. Permanent duplicate disposal used `board.Remove` on borrowed loaded objects.
   It now uses `cec_native_items.discard_items`, including group membership and
   native/SWIG lifetime handling.

Loaded-native subprocess regressions use renamed nets, translated vertical
bottom-layer tracks, a locked survivor and a group-owned victim. Eight repeated
cleanup/save/reload cycles preserve source bytes and registry balance. Negative
controls reproduce both the legacy width deletion and registry imbalance.
**56 tests pass**, including lifetime, admission, scheduling and generality
coverage: `build/fab-native-final-tests-20260916.log`. This count overlaps prior
suites and must not be summed with them.

Parallel private replay: `build/fab-duplicate-suite-replay-v2-20260916/report.json`.
Hub, PCIe2, PCIe3 and VHP preserve native DRC/open counts, pair/Kelvin results,
poses, power prefix and source hashes. VHP trims six redundant covered prefixes;
the other three are no-ops. These private diagnostics were not promoted.
EPS and ATX are **held before replay** by their existing unadmitted interface
ECOs; this is four native replays plus two preserved refusals, not six native
passes. The first harness run incorrectly treated the expected refusal as a
worker error; the successor records it explicitly without bypassing admission.

Historical PCIe2 control SHA, complete `board_regression` and all `probes` remain
identical to the preceding control. See
`build/fab-native-control-comparison-20260916.json`. Its existing broader release
holds remain; exit 1 does not indicate a new regression.

Next work remains distinct by family: residual PCIe2 connectivity/geometry;
Hub owner-pin/return craft; VHP priority USB flow-through; PCIe3 priority
Kelvin/pair escapes; and jointly qualified EPS/ATX mating geometry. Do not repeat
unchanged exhausted searches merely because these preventive fixes landed.
