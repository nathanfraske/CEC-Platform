# Locked-copper cleanup and source provenance

## Completed parallel pass: a modest real gain, still withheld

`build/locked-connectivity-followup-suite-20260915/suite.json` finished
**14:37:54Z**. All three processes/descendants have exited; source/hierarchy
and engine signatures passed. The selected PCIe2 **seed 0** improves 12 opens
to **10**, with **zero structural DRC errors**. Seed 1 has 12 opens: the final
log line described that losing candidate, not the winner. Always read selected
candidate and independent signoff, not the last console metric.

| Independent metric | Prior partial | Selected winner |
|---|---:|---:|
| DRC errors | 0 | 0 |
| Unconnected | 12 | 10 |
| Tracks | 681 | 726 |
| Vias | 321 | 382 |
| Trace length mm | 1488.503 | 1572.851 |

Winner SHA `905f961c625743053efccb6b46a73f4115aef31f2bcc819db8b161d682b03b22`.
Both existing Kelvin/differential boolean probes remain true, but full release
is **WITHHELD**: connectivity, source-draft, hardware qualification, constraint,
route geometry/oracle and independent-score terms still fail. The two-open
gain comes during certificate repair, not initial final-completion (zero gaps
closed there). +5VSB and I2C_SDA are no longer falsely excluded, but remain
open; do not attribute the two closed gaps to closing those nets. The extra
61 vias/84.348 mm are a cost, not automatically a routing-quality improvement.

Hub retained two further small adjustments, SHA `ce61d1a11de36b52f248c2fc86071e1f10aa24299eef8a085cb2fd31aca0fe3d`,
still five craft failures. PCIe3 retains identical 400ff geometry and one
failure. VHP remains at its escape barrier; EPS/ATX at coupled-interface
geometry/authority holds. Do not repeat unchanged exhausted placement waves.

## Verified reviews

Dashboard `/api/archive` includes
`pass-locked-connectivity-followup-suite-20260915-pcie-8pin-2port-8047fc0498`.
Top gallery and PCIe2 bottom native panels were visually inspected and label
the board **BLOCKED / precision_detailed_route / NOT FAB SIGNOFF**. The final
three-board gallery replaces the prior running placeholder:
`C:/Users/Admin/Documents/CEC-Board-Reviews/locked-connectivity-followup-suite-20260915/all-boards-a23d68cbccdf847f.png`,
SHA `a23d68cbccdf847fd1a160714085f8e8037656081b422e2f3aa243599a2246c9`.

## Second ownership defect: downstream cleanup

Although upstream ownership now used native connected components,
`cec_fr.reconcile_locked_nets` independently retained the earlier pad-endpoint
proximity test. Its fully-owned branch could strip an unlocked bridge joining
separate locked escapes. Its supposed exact-echo branch compared rounded
endpoints without net, layer, width or arc midpoint. It also lacked source
provenance, so pre-existing authored copper could be mistaken for a new router
addition. The prior aggregate DRC/open-count rollback was a backstop, not a
sound selection proof. The selected actual wave logged two +5VSB removals with
unchanged aggregate opens; that is not proof they caused the residual failures.

## Generic implementation

- Shared native locked connectivity now governs cleanup as well as exclusion.
  An unlocked bridge between separate locked components is preserved.
- Existing serialized copper-echo machinery compares exact full geometry,
  including net/layer, width, arc midpoint, via fields and unknown fields.
- Nonexact whole-owned-net cleanup requires a separate source artifact and
  removes only new UUIDs. Source copper and group-owned additions survive.
  Without source authority, only exact locked copies are eligible.
- Route integration supplies the actual pre-router `route_input`, retains
  selection proofs in the oracle report, and keeps console logs compact.
- Cleanup applies serialized deltas, not unsafe native object destruction;
  a no-op does not rewrite the PCB or project. Existing score/rollback and
  final independent admission remain in force. No board/refdes selector,
  geometry exception, bus shift, width relaxation or design-budget change.

Files: `scripts/cec_copper_echo.py`, `scripts/cec_fr.py`,
`scripts/cec_synth_pipeline.py`; native and serialized regressions in
`tests/test_locked_net_ownership.py` and `tests/test_copper_echo.py`.

## Validation

- `build/locked-reconcile-final-tests-20260915.log`: **828 passed + 35
  subtests**, 106.74 s. The later compact-log integration was replayed with
  **252 passed + 25 subtests** in `locked-reconcile-integration-tests-20260915.log`.
- `build/locked-reconcile-suite-replay-v2-20260915/report.json`: all six
  current inputs/hierarchies unchanged. Four native cleanup replays are
  byte-identical/idempotent with no lost connected nets. EPS/ATX correctly
  refuse the copied sidecar-authority step because their interface ECOs are
  unadmitted; the guard was not bypassed. The first replay stopped on this
  same guard and is retained in the non-v2 directory, not claimed as a pass.
- `build/locked-reconcile-control-comparison-20260915.json`: protected
  historical PCIe2 SHA, complete board-regression object and all probes
  unchanged. Only generalization inventory differs; old strict release
  failures remain. Core **72 modules / zero violations**; broader runtime
  **380 findings** still remain.

## Next bounded run

Harness `tmp/locked_reconcile_followup_20260915.py`; current input plan
`build/locked-reconcile-inputs-20260915.json` uses the verified 905f winner,
not the earlier 12-open artifact, the historical control, or a diagnostic copy.
Only PCIe2 is re-run because it reaches the repaired stage. The other five
remain accounted for in suite checks; their unrelated exhausted placement/
escape/mechanical holds are not blindly re-run.

Journal `build/locked-reconcile-followup-suite-20260915/suite.json`, two
workers, two route seeds/eight passes, 1500-s board bound, 120-s priority
allowance and 16-GiB free floor. Do not edit shared engines until it and all
descendants finish. No automatic promotion. Next performance slice remains
the 36/104 already-owned coarse demands, with explicit preservation and
unchanged obstacle occupancy needed before removing them from prediction.

Dispatched **15:10:23Z**, PCIe2 PID **318752**, parent session **12464**.
Input SHA is exactly 905f961c6257...; placement passed in 31.6 s and the
process entered route preflight. WSL free space is still 68 GiB. No new
routed output or improvement from the cleanup repair is claimed yet.
