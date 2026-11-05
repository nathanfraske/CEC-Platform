# Complete mating-row outline budget — 2026-09-20

## Status and decision boundary

The owner authorized proceeding toward repair after the row-regression history
was explained. No permission to increase outlines was inferred. The fixed
daughterboard outlines cannot hold the current conservative, same-depth shared
row with the installed lands and margins. A daughterboard-width choice was
requested; **no PCB, schematic, footprint, outline, pinout or input plan changed**.
EPS and ATX remain blocked, not physically repaired or newly routed.

The earlier main-board rows were wider and did clear the identified copper
overlap. Their restoration alone cannot repair the assembly: EPS's former
7.75-mm pitch spans 23.25 mm across four contacts, requiring 30.25 mm including
two 3-mm half-lands and two 0.5-mm edge margins. Its actual daughterboard is
28 mm wide. A rigid lateral shift cannot change this arithmetic.

## Generalized implementation

`cec_mating_rows.rigid_row_outline_fit` evaluates a complete rigid row against
both outline edges. It uses every actual contact interval, including asymmetric
or intervening envelopes, and returns the allowable translation interval,
limiting contacts and width deficit. A failed fit emits no translation; it
cannot grow an outline or weaken a margin. It has no product/refdes selectors.

The XFCN adapter attaches `fixed_outline_budget` to the existing paired-row
compilation receipt. It uses library copper in the installed orientation and
includes the ATX signal companion's existing separation policy. This corrects
the incomplete *explanation* supplied by a last-hole span alone: the signal
header consumes real lateral room beyond the last power contact. It does not
change routing/placement acceptance or publish a repaired interface.

Current minimum-pattern screening, allowing rigid translation within the
existing outline and retaining the existing 0.5-mm copper-edge rule:

| Daughter interface | Existing width | Screened pattern width | Width deficit |
|---|---:|---:|---:|
| EPS | 28.00 mm | 30.10 mm | 2.10 mm |
| ATX, including signal header | 54.00 mm | 57.56 mm | 3.56 mm |
| PCIe | 24.50 mm | 21.50 mm | 0 mm |

These are conservative row-envelope screening results, **not qualified final
dimensions or proof against another interface design**. The EPS 30.10-mm
screen uses 7.70-mm pitch; exact restoration of 7.75 mm requires 30.25 mm.
The PCIe 21.50-mm minimum is diagnostic only: its existing 14-mm mating pitch
is unchanged and must not be compacted to this minimum. Full native rules,
drills, assembly fit, fastener access, keying, thermal revalidation and the
existing incoming-sample gates remain required. No screw-axis/Z transform is
invented. Main-board outline growth is not established by these results.

Direct native Edge.Cuts readback confirmed the declared daughterboard bounds:
EPS `(0,0)-(28,18.5)`, ATX `(0,0)-(54,21.3)`, PCIe `(0,0)-(24.5,20)`.

## Validation

- 63 focused tests pass: invalid input refusal, complete/asymmetric envelopes,
  translation invariance, no growth or mutation, current-family budgets,
  paired compilation, saved native pad DRC and pre-dispatch refusal.
  Receipt: `build/row-outline-budget-tests-20260920.xml`.
- 160 additional integration tests and 41 subtests pass, covering the XFCN
  contract, full-pipeline boundaries, interface ECOs, mating frames, suite
  dispatch and generic audit. Combined: **223 tests + 41 subtests passing**.
  Receipt: `build/row-outline-budget-boundary-tests-20260920.xml`.
- Current six-board native replay retains identical pad-edge, pad-copper and
  assembly counts. EPS has 32 pad-copper/3 assembly report rows; ATX has 56/6.
  The other four have zero findings in this limited geometry screen; that is
  not full routing, craft or fabrication qualification.
- Historical PCIe2 board hash, board-regression results and probes retain exact
  parity. Its pre-existing wider release blocker is not waived.
- All seven interface source PCB hashes, the six canonical input/hierarchy
  signatures and the engine signature remain unchanged during replay.
  Core generic audit passes; no candidate or image is promoted.
- Replay: `build/row-outline-budget-replay-20260920/report.json`.

Do not spend another EPS/ATX wave on the unchanged rows. After the outline or
interface decision, change both mating halves transactionally, retain source
backups, run native geometry/assembly checks, invalidate stale route authority,
and only then normalize and attempt replacement placement/routing.
