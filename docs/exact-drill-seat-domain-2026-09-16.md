# Exact drill-seat domain and bounded cell experiments

## Shared search defect repaired

`cec_fr._lastmile_bridge` rejected every offset-via candidate within 0.85 mm
of any existing via, before its existing exact native guard ran. That constant
does not represent the actual two drill diameters and board hole-to-hole rule.
It incorrectly removes legal same-net compact dogbones from the search domain.

The redundant offset halo is removed. The existing `_via_spot_clear` still
requires actual drill separation, refuses coincident holes, checks assembly
and pad exclusions, all-layer foreign copper, and frozen power reservations.
Ordinary via minima and explicitly qualified POFV exceptions are unchanged.
There is no board/refdes/coordinate special case or new clearance waiver.
The separate fixed separation between **two newly proposed** bridge seats is
not changed in this slice and remains a follow-up search-domain limitation.

## Evidence and limitations

- **171 tests plus eight subtests pass**, no skips, 18.16 seconds:
  `build/exact-hole-full-tests-20260916.log`.
- Ten new loaded-native cases include renamed/translated/quarter-turned,
  front/back launches; larger existing drills and board hole gaps; duplicate
  holes; foreign annular clearance; and an independently CLI-DRC-checked
  completed fixture with zero errors and zero opens. Restoring only the old
  halo refuses the four otherwise legal transformed fixtures.
- Early fixture versions used the wrong project rule key and declared an
  existing through barrel as belonging only to one layer. Both fixture errors
  were corrected; production guards were not weakened to pass them.
- Four-worker old/new diagnostic replay covers all six explicit retained
  source identities: `build/exact-hole-suite-replay-20260916/report.json`.
  EPS/ATX correctly remain interface-held. The other four use a 30-second
  total / 6-second per-net cap with at most 24 ordinary-net closures, excluding
  priority pairs and fixed power authority nets. This is not a full pipeline
  run and does not admit the priority-held boards.
- DRC and opens do not worsen against the old solver in those four diagnostic
  runs. VHP and PCIe2 copper is identical. Hub copper is about 0.98 mm shorter;
  PCIe3 is about 29.69 mm longer with three more tracks and the same opens.
  Thus there is **no claim of universally improved route quality or closure**.
  Geometry comparisons and exact metrics are in the replay's `comparison.json`.
- PCIe2's ordinary residual experiment finds one I2C_SDA closure, **10 -> 9
  opens at zero DRC**, with all local cells still passing and original copper
  and poses retained. **The old solver also finds this closure**: it is a
  different bounded residual opportunity, not a gain caused by this patch.
- Historical PCIe2 control bytes, full regression and all probes are unchanged:
  `build/exact-hole-control-comparison-20260916.json`. Existing release holds
  remain; the control's expected exit code is one.
- Generality passes. Original six sources, their hierarchy families and the
  replay's shared engine are unchanged. No diagnostic board is a fab candidate.

## Negative complete-recorded-cell ablation

`build/local-cell-negotiation-probe-20260916/report.json` contains seven
independent private trials: three retained-source controls and four removals
of complete historical **recorded generated-item sets** for relevant U4 cells.
Historical producer primitives and current native signatures matched before
removal. All seven close zero target gaps under their 12-second net budgets;
every working board is restored and no production unlock is authorized.

Removing those recorded cells alone is not a demonstrated repair. These are
bounded negative results, not proofs of global routing impossibility or of
complete ownership of reused dependencies. The subsequent three-target
exact-hole ablation also closes zero in twelve seconds. Do not repeat either
unchanged experiment or present provenance metadata as achieved connectivity.

## Canonical continuation

The independently checked nine-open PCIe2 diagnostic is submitted as an explicit
derived **input only** to `build/exact-hole-residual-followup-20260916` by
`tmp/exact_hole_full_followup_20260916.py`: 600-second whole-job bound,
two workers, four craft trials and two route passes. Every normal intake,
placement, priority, route and release gate remains active. Read its journal
and suite result before claiming admission or selecting a new retained input.

Until that completes, `build/copper-curve-next-inputs-20260915.json` stays the
canonical six-source plan. No unchanged Hub rerun is launched; VHP/PCIe3
priority holds and EPS/ATX coupled interface geometry remain distinct work.
