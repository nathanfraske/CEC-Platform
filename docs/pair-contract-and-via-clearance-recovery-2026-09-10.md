# Pair identity, atomic tier admission, and annular-land clearance

## Scope and unchanged authority

This slice changes the reusable pipeline, not component coordinates or power
lanes. The protected 12VHPWR input remains
`build/12vhpwr-pair-search-20260909/checkpoint/board.kicad_pcb`, SHA-256
`3a0deb439290e8b7646b1b736e2947d5c1a711d0b3e4f17b7919c0c5b3da0e28`.
The PCIe 2-port archived control retains SHA-256
`d6bc7c2df081a5c9f8ec32da8586071464c5fe8ba8dc3383c17ffdcb809789ea`.
Neither PCB, its footprint poses, nor its power copper was edited.

## Findings and repairs

1. **Routing and signoff disagreed about pair identity.** The physical checker
   omitted series-separated CAN pairs such as a transceiver-side segment, but
   treated a current monitor's `_P/_N` input nets as high-speed transmission
   lines. `cec_pair_semantics` now supplies the same electrical identity to
   precision routing, default tier selection, and physical signoff. Exact
   same-sheet mates and series suffixes are preserved. Existing recognized
   current-monitor input pin contracts distinguish analog input pairs from
   high-speed pairs; unknown devices retain conservative differential checks.
   Connectivity, DRC, Kelvin, and route-shape checks are not waived.
2. **Connectivity-only tier ownership froze invalid pairs.** Staged routing
   could lock electrically connected USB wires with asymmetric layers and
   vias, poor coupling, and missing returns. Before a tier is owned, its
   touched pairs now need independent physical admission. Legal matched
   transition/return repair runs transactionally before ownership; it is scoped
   to complete pairs touched by the tier. A failed tier retains its exact
   parent, rather than leaving individual completed members as obstacles.
   Later, still-unrouted pairs do not falsely fail an otherwise valid tier.
3. **Known-invalid saved boards triggered expensive constructive validation.**
   Recovery now checks saved-board electrical and physical admission first.
   Failed evidence skips constructive preflight and placement remeasurement;
   skipped checks never count as passes. Reports include explicit failure
   stages and timings. Repeated full copper geometry stops the bounded wave
   loop independently of changing UUIDs or file ordering.
4. **The pair via planner excluded the opposite member.** Its foreign-net
   exemption covered both P and N, and the whole-graph test inspected trace
   centreline spacing without annular lands. Signal via placement now exempts
   only its own net and uses live geometry rather than a stale snapshot.
   Whole-graph validation additionally checks actual via shapes against the
   opposite member's pads, tracks, and vias on every shared copper layer.
   Only conflicts involving newly created copper are attributed to a proposal;
   inherited geometry is not silently repaired. The portal cache version is
   changed to prevent reuse of the earlier weaker admission result.

These rules contain no product name, reference-designator selection, placement
coordinate, or board-specific move. Device pin contracts are electrical part
definitions, not placement exceptions. Native synthetic tests cover annular
land versus centreline clearance, opposite pads, back-layer copper, exact
minimum spacing, and transaction ownership.

## Measured results

The prior canonical `current-suite-routing-20260910-f` job exhausted its
1,800-second budget. Its recovery waves generated 4-DRC/220-open provisional
artifacts, but their USB route had 9.31 mm skew, P/N transition counts 3/0,
15.1% coupled coverage, and missing ground returns. Neither was admitted.

The identity/tier recovery replay in `build/pair-contract-recovery-20260910`
ran two critical-only waves in **46.904 s and 45.801 s** (92.705 s total after
entry preparation). Both correctly retained the **4-DRC/228-open** parent;
the second stopped with `repeated_unadmitted_geometry`. Source hierarchy,
source board, and engine signatures remained unchanged during this run.
This is faster rejection of invalid work, not eight newly repaired connections
or a claimed overall 1,800-to-93-second full-pipeline speedup.

The six manifest-enabled main-board identity replay passed 6/6. Apart from the
explicit protected 12VHPWR incumbent, these were **manifest staging inputs**,
used to check electrical identity only, not promoted placement candidates.
Router/checker high-speed pair counts were 3/3/2/2/3/3 for 12VHPWR, ATX, EPS,
Hub, PCIe 2-port, and PCIe 3-port. Analog-input witnesses were 6/6/4/0/4/6.
Evidence: `build/pair-contract-cross-board-20260910.json`.

The PCIe control replay remains **0 DRC, 0 opens, 615 tracks, 226 vias**, with
unchanged bytes. It still fails the current broader release gates. The newly
included connector-side CAN pair exposes a non-octilinear segment and **78.9%
filled adjacent-GND coverage**, below the existing 95% gate. This was missed
coverage in the checker, not new damage to the control. The existing release
blocker IDs remain; the full pair report preserves this additional detail.
Evidence: `build/pair-contract-pcie-control-20260910.json`.

The earlier rejected native CAN counterexample is now caught directly by the
new annular-land check: **five pair via/copper contacts** are recorded in
`build/native-pair-clearance-slice-20260910/old-counterexample.json`.
Independent raw KiCad evidence is retained in
`build/native-tree-admission-20260910/drc-forensics.json`; its saved-zone
antipad findings must be distinguished from actual pair-member contacts.

## Remaining boundary

No candidate in this slice is promoted or declared fab-ready. USB/CAN must
still obtain physically legal coupled paths before ordinary residual routing.
This slice improves failure attribution, matching between route and signoff
policies, bounded retry behavior, and the shared clearance solver.

The post-clearance native CAN replay completed in **124.102 seconds**, refusing
the unresolved layered trunk instead of returning the illegal annular-land
contacts. The saved, freshly refilled result remains **4 DRC / 228 opens** and
the source hash is unchanged. This is correct rejection, not routing closure.
Evidence: `build/native-pair-clearance-slice-20260910/result.json`.

Final focused regression: **293 passed**, plus two subtests, in 47.83 seconds;
one KiCad SWIG deprecation warning. See
`build/pair-contract-final-tests-20260910.log`. Focused `git diff --check` passed.
The two diagnostic output directories occupy approximately 6.3 MiB together;
the WSL filesystem had 77 GiB free at closeout.

A fresh bounded canonical continuation was launched under
`build/current-suite-routing-20260910-g` with the original protected incumbent
and a 1,800-second job budget. It must earn all existing admission gates; its
launch is not an admitted candidate or a promise of unattended closure.
