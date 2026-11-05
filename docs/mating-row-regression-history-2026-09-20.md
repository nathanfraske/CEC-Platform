# Mating row shrink was a regression, not a new board-size requirement

The user's follow-up asked why previously established clearances need more
space, and whether the terminals were moved. Direct native readback of the
saved before/current PCBs confirms they **were moved inward** during the
September 11 mating-alignment ECO. The recent compiler/dispatch fixes did not
move them again or change footprint lands.

| Main row | Earlier pitch | Current pitch | Installed copper width | Earlier / current lateral copper gap |
|---|---:|---:|---:|---:|
| EPS TB13, TB11, TB12, TB14 | 7.75 mm | 7.00 mm | 7.50 mm | +0.25 / -0.50 mm |
| ATX TB4, TB2, TB1, TB5 | 8.00 mm | 7.00 mm | 7.50 mm | +0.50 / -0.50 mm |

EPS before hash: `cb3cca6ca1052ce3191e13b36cabe09ebfa5b57ed05f1b6f3f7c0345102b08bb`.
EPS current hash: `3af9f2496c44474dc80eee9775596174f9480ace89853f3e463ab7add846aa01`.
ATX before hash: `e7f3764917782737bad791d32ef5459bb141355209633bd78e5494308d10fa0d`.
ATX current hash: `2e45ff7fc4402a63074253cd65d3f584e8311dbb5b8ae285b9a370d6dc0e280c`.

Before-board authority is `build/mating-source-backup-20260911/{eps-main,atx-main}/before.kicad_pcb`.
The adjacent `after.interface-eco.json` files explicitly record the movements.
The initial ATX ECO also pulled its mixed-part end terminals inward. Its later
canonical ECO record has no new movement and inherits invalidation; that
no-op record must not hide the earlier mutation.

The old body-only row screen chose the daughterboard pitch and then compressed
the main row to match. It missed actual rotated copper, so a nominal body-gap
pass was incorrectly treated as sufficient row-clearance evidence. The earlier
main pitches clear this particular pad-overlap failure; that does **not** mean
the historical main/daughter pair had a fully qualified mated fit or matching
datums. Do not restore only the main-board half.

The compiler's +2.1 mm EPS / +3.4 mm ATX shortfalls are relative to the compressed
daughterboard-span constraints. They are not proven requirements to increase
the originally intended main-board outlines or complete assembly size. First
investigate recovering the earlier main clearance while reconciling both halves
within the intended envelopes. The current daughterboard outlines/contact edge
margins, ATX signal companion, pinout and assembly constraints still require a
joint proof. Do not silently relax these or infer a screw-axis Z transform.

This history check made no CAD or production-policy changes. The safe current
cohort and EPS/ATX dispatch holds remain unchanged; unchanged failed waves are
not useful work.
