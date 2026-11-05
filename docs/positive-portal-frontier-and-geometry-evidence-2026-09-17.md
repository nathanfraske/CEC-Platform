# Positive portal continuation and geometry evidence — 2026-09-17

## Implemented generic changes

1. `fair_screen_domains` now accepts a positive-candidate target (default one),
   resumes incomplete domains below that target, and uses smaller completed
   beams without falsely claiming they meet the requested width. Three unchanged
   observations at the maximum two-second quantum stop optional screening as
   **stalled**, not exhausted. Short fair-share deadlines do not count as full
   quanta. All budgets remain parameters.
2. The native portal producer can resume beyond its already-successful direct
   phase into the dogbone phase. Previously `if accepted: break` stopped every
   resumed call at the first phase even when no additional query ran. Completed
   query frontiers now survive within the same immutable-parent transaction.
   Duplicate seats do not masquerade as a wider beam. Native shape caches remain
   local to each beam; positive fan-ins are still regenerated and checked.
3. After a recognized whole-edge admission/lattice refusal, the consumer may
   request one -> two -> four positive seats, within the existing refill cap,
   endpoint capacity and absolute deadline. Baseline successes return unchanged.
   Existing stranded-source exclusions retain priority; a fixed prequalified
   source is not moved. Local-seat-only failures do not trigger this widening.
4. Route-preflight now preserves the separate `non_octilinear` geometry channel.
   Previously the precision gate used `geometry_ok`, but its caller retained
   only graph `issues`. Two real Kelvin diagonals therefore became the opaque
   message `pairs_ok false without refusal evidence`. Exact copper UUID, net,
   layer, endpoints, heading and component references now reach the caller.
   Admission is unchanged. Compact search traces also retain stall/resume facts.

No board/reference/coordinate-specific branches or electrical/process waivers
were added. The boundary-proposal helper remains **experimental, not production**.

## Regression evidence

`build/positive-frontier-final-tests-20260917.log`: **852 tests and 16 subtests
pass, 23.47 s**. This includes the earlier test groups, not 852 new tests.
New coverage includes mutable producer lists, completed smaller beams, bounded
stalls, progress resets, shortened deadlines, unchanged success/fixed-source
behavior, bounded widening, loaded-native phase continuation and exact rollback,
and independent geometry-witness projection. An initial fixture counted every
heading as a different domain; it was corrected to terminal/polarity, then passed.

## Concurrent current-suite replay

Full receipts: `build/positive-frontier-suite-20260917/report.json`.
Hub, PCIe3 and VHP used the actual production priority compiler concurrently;
PCIe2/EPS/ATX ran their current independent gates, with the historical control.

| Board | Observed result |
| --- | --- |
| PCIe3 | Production generator now constructs CAN_J1 as well as USB_D and CAN; no pair-constructor refusals. 94 copper items versus the previous 68. Still fails overall precision admission. |
| Hub | Same USB leg-1 refusal; no added copper. 74.757 s. |
| 12VHPWR | Same USB leg-2 refusal; no added copper. 69.383 s. |
| PCIe2 | Physical/craft gates pass; still five opens. Board unchanged. |
| EPS / ATX | Interface-ECO decision remains pending; no change to dimensions, terminals or mating authority. |

PCIe3's compiler replay took 15.045 s versus 194.867 s in the prior receipt.
This is an observed run-time difference, **not a controlled speedup benchmark**.
Its native comparison proves all 68 previous copper geometries are preserved;
the 26 additions are 12 CAN_H_J1 tracks, 12 CAN_L_J1 tracks and two GND vias.
The new CAN pair passes generator graph/craft and per-member detour checks
(1.873329 / 1.934168 against 2.0). This is real constructor progress, not a
fab-ready board or a promotion of the complete prefix.

Independent saved-native postflight:
`build/positive-frontier-postflight-20260917/report.json`.

- Whole generated geometry still fails on two **pre-existing** Kelvin diagonal
  tracks, `/SENSEC1_HI` and `/SENSEC2_HI`, now with exact witnesses. The missing
  evidence was repaired; those routes were not silently normalized in this slice.
- Seven Kelvin endpoint/range refusals remain in the compiler report.
- Independent final pair physics rejects all three pairs solely for absent
  filled adjacent-GND coverage (0% vs 95%). This is an incomplete pre-plane prefix,
  not permission to waive the reference-plane requirement. It has not passed full
  saved-board DRC/release qualification.
- All six canonical boards and their schematic hierarchies are unchanged.
  Historical PCIe2 board hash, board-regression result and probes all match.
- Core generic audit passes; full-pipeline generic audit remains false with the
  previously reported 23 physical / 380 runtime issues.

## Experimental boundary continuation

The separate PCIe3 boundary trial now really reaches its wider frontier:
one -> two -> four, no 64-round stall, complete start domains at 1432 queries
each, three positive start seats on the viable polarity and four positive end
seats on both polarities. Twelve final whole-edge attempts still fail exact
detour/lattice admission. The best reported N detour remains >2.0; zero retained
copper, 100.781 s. This is finite-domain coverage, not board impossibility.
Do not repeat this unchanged experiment or merge boundary proposals on this
evidence alone. The production same-layer result is better than this forced
inner-layer experiment.

## Next bounded work

Keep `build/additive-first-next-inputs-20260917.json` authoritative. Preserve the
new private PCIe3 prefix as evidence, not a winner. Trace the Kelvin generator's
raw-diagonal construction and distance/placement certificates generically before
another whole-board run; validate the actual full precision witness handoff.
Hub/VHP need changed upstream escape/return geometry, not repeated identical
seeds. Hub pose history stays 125. EPS/ATX still need the already-requested
coupled-interface decision. No candidate or dashboard preview was promoted;
all replay workers finished.
