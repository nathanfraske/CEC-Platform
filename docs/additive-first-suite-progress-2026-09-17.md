# Additive-first routing and parallel suite continuation

## Admitted result

PCIe2 improves **0 counted DRC / 8 opens -> 0 / 5** across three sequentially
admitted additive transactions. This is a **37.5% reduction in remaining opens**
from this turn's input, not a percentage of fabrication readiness. The two
remaining 3V3 connections close, plus one VBUS connection. Added: 29 tracks,
two vias. Every pre-existing copper item, footprint pose, electrical identity,
zone declaration and semantic project/custom rule remains unchanged.

Use **`build/additive-first-next-inputs-20260917.json`**. Only PCIe2 advances:

- PCB: `build/board-archive/20260917-additive-pcie2-5-open-032ee2c1a066/board.kicad_pcb`
- SHA256: `032ee2c1a06644b8dc1ced7cc927d90f2e71af69f5a994a5ed5b48352ce0ffbd`
- Adjacent `oracle.json`: fresh hash-bound five-open native residual survey.
- Dashboard ID: `20260917-additive-pcie2-5-open-032ee2c1a066`.
- Windows body-free top/bottom previews:
  `C:/Users/Admin/Documents/CEC-Board-Reviews/additive-first-20260917/pcie-8pin-2port/`.

Independent score/constraints/route-quality/fabrication comparisons all pass
non-regression. Both rendered sides were inspected and both `/img` endpoints
returned HTTP 200 image/png from Windows. The native images show the actual
selected copper, not a proposed board or an earlier revision.

This remains **partially routed, not fab-ready**. Remaining opens: +5VSB x2,
VBUS x1, U4_OV1 x1 and U4_SS x1. Existing ground netclass geometry findings,
the previously recorded routing-quality advisory and the pipeline's existing
excluded USB NPTH-hole DRC findings remain. No fresh thermal solve, physical
terminal qualification or fabrication release is implied.

## Generic implementation

`cec_additive_pair_repair` adds a bounded exact native-island attachment stage
before whole-net probing or footprint/via displacement. It reuses the existing
exact router and whole-board stage admission. Source/current rules must match
a valid native residual snapshot; malformed/stale evidence cannot widen to an
unrelated net search. Live paired and current-sense identities, plus actual
netclass widths, retain their specialized routing ownership.

The transaction also explicitly proves all old copper, poses, identity, zone
declarations, semantic rules and qualified pairs unchanged. Only a complete
accepted private candidate is copied forward; generated-copper lineage carries
the exact added UUIDs. One accepted connection invalidates the old residual
survey and forces remeasurement before another pair is used.

Two added scheduling regressions caught and fixed shortlist starvation and
underfunded-attempt history. History is counted before the new-trial limit and
records actual per-pair search allowance; a short trial cannot suppress a
better-funded retry. History reuse remains confined to matching identity and
algorithm revision; it is not geometric no-path evidence.

The actual coordinator test caught a further integration failure: ordinary
family copying rehomes the frozen skeleton pointer and project metadata, so
an original residual's byte identity no longer matches the scratch family.
The initial v55 coordinator therefore skipped additive repair and spent its
time in the old live probe. **v56 fixes this by performing fresh native scratch
remeasurement**, not by rewriting the evidence hash or weakening identity.
The v56 coordinator then reproduces 8 -> 7 opens, with one admitted additive
attempt, unchanged old geometry, and reused fresh residual guidance in 25.168 s.
This is a regression-fixture reproduction; it does not replace the better
five-open canonical result.

## Parallel board results

| Board | This slice | Admitted state |
| --- | --- | --- |
| PCIe2 | Three sequential additive closures | 0 counted DRC / 5 opens |
| Hub | 32 new poses, zero revisits, 283.353 s | Unchanged three craft blockers |
| PCIe3 | 16 new poses, eight critical probes, 349.930 s | Unchanged eight priority refusals; probe budget inconclusive |
| 12VHPWR | Fresh native physical and protected-copper checks | Unchanged; specialized USB priority refusal remains |
| EPS rev3 | Current source/interface check | Coupled terminal copper-envelope/ECO hold |
| ATX 24-pin | Current source/interface check | Coupled terminal copper-envelope/stack-access/ECO hold |

Latest matching placement search receipts are now at
`build/additive-frontier-continue-20260917/<board>/board.placement-search.json`:
Hub **109** visited poses and PCIe3 **64**. Neither placement is promoted.
Hub's 49 legal evaluated variants did not improve its existing craft key;
other variants hit bounds/overlap gates. PCIe3's critical probes do not prove
global route impossibility. Its pair probing consumed 188.715 s of the recorded
219.023-s repair round; merely adding unchanged waves is not a demonstrated fix.

All six source/hierarchy identities and the historical PCIe2 control's hash,
board-regression and four independent probe payloads match. Approved load
budgets, power buses, dimensions, edge spans, mating pinouts and control PCB
are untouched. About 64 GiB remains free; the 16-GiB floor is maintained.

## Evidence and next bounded work

- `build/additive-first-suite-20260917/report.json`: eight parallel pair trials,
  current suite checks and historical control.
- `build/additive-frontier-continue-20260917/report.json` and `route-chain.json`:
  three sequential accepted route steps alongside completed Hub/PCIe3 searches.
- `build/additive-final-independent-20260917/report.json`: final independent
  native/physical/quality/fabrication non-regression proof.
- `build/additive-production-verify-v56-20260917/report.json`: actual production
  dispatch reproduction plus fresh current six-board and control replay.
- `build/additive-v56-broad-tests-20260917.log`: **524 tests + eight subtests pass**.
- `build/additive-v55-generalization-20260917.json`: core audit passes; broader
  pre-existing physical/runtime generic debt remains **23 / 380**. This is not
  a claim that the entire legacy pipeline is fully generic or release-qualified.

All workers have completed. The existing 15-minute review/repair heartbeat
remains active and reads the newest ledger. Do not replay the just-exhausted
five-open additive domain or the same placement poses. Next useful work is
coordinated owned endpoint/support access (not another detector-via menu),
critical pair-station search/probe attribution for Hub/PCIe3/VHP, and a coupled
main/daughterboard native copper-envelope solution for EPS/ATX. Do not move only
one mating half, infer unverified screw-axis geometry, shrink pads or grow the
board envelope to evade those holds. All future native cohorts must start from
the new manifest and freeze shared scripts for their duration.
