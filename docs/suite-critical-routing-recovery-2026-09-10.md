# Current BETA suite: critical-routing recovery

## Status

12VHPWR has entered actual critical-only, tiered Freerouting waves. Ordinary
residual routing remains withheld until critical-route admission passes.
The first authoritative wave produced a provisional **4 DRC / 220 opens**,
versus **4 DRC / 228 opens** at entry. Its immutable copper-prefix and unchanged
placement checks passed; complete pair admission did not. This is not a fab
candidate, and the protected incumbent was not replaced.

Evidence: `build/priority-recovery-authoritative-20260910/recovery.json` and
`build/priority-recovery-authoritative-20260910.log`. Both initial bounded waves
ran; neither earned full critical-route admission. Consult the JSON for exact
per-wave results. A fresh canonical continuation is under
`build/current-suite-routing-20260910-f`; that job subsequently exhausted its
1,800-second budget without admission. Follow-up repairs and measured replay
results are in
`docs/pair-contract-and-via-clearance-recovery-2026-09-10.md`.

Authoritative input:
`build/12vhpwr-pair-search-20260909/checkpoint/board.kicad_pcb`, SHA-256
`3a0deb439290e8b7646b1b736e2947d5c1a711d0b3e4f17b7919c0c5b3da0e28`.
The current hierarchy remains `beta/12vhpwr-standard/12vhpwr-standard-module.kicad_sch`.
The board outline, footprint poses, grounded M2 mounts and protected power buses
were not changed in the authoritative routing wave.

## Root causes and generic repairs

1. **Unreachable routing fallback.** Placement required the constructive
   precision router to finish, before the canonical detailed-routing stage
   could invoke its existing tiered fallback. `cec_priority_recovery.py` now
   connects bounded critical-only waves before another placement ECO. Physical
   and power authority, pin escape, fanout and declaration failures still block
   this path. Successful recovery is rechecked on the actual routed PCB, not a
   newly materialized placement that would erase the recovered copper.
2. **Incomplete pair search domain.** Paired escapes now explore all eight
   octilinear headings with directed P/N handedness. Multidrop recovery tries
   native pad junctions and bounded connected spanning-tree alternatives before
   demanding another placement. A constructive route is not a DRC certificate.
3. **Inline-chain resource conflicts.** Each USB leg routed independently but
   obstructed its successor. Added bounded order backtracking and future inline
   launch reservations. Native tests still expose unsolved cases; this is not
   a claim that the reservation heuristic is complete.
4. **Different screened and emitted junction copper.** A terminal dogbone
   covered by its own runway survived emission and became a false backtrack.
   Normalize newly emitted star copper before composing long edges; authored
   copper is outside that removal scope.
5. **Incomplete rollback.** Late whole-pair rejection could remove the two
   signal nets but leave supporting ground vias. The complete transaction now
   rolls back every newly created copper UUID.
6. **Placement search starvation.** Legal-but-distant inline seats suppressed
   useful bounded eviction proposals. Owner-cell rotations, contact-space
   reseats and small collision-repaired alternatives now enter the proposal
   pool before expensive sampling. They still require frozen-copper, physical,
   craft and routing admission; no board-specific coordinates are embedded.
7. **Package-origin locality error.** Large-module followers could be close to
   their owning pin but far from the module origin. Local source-owned repair
   groups now consider the actual owner pin, preserving nearby electrical
   followers during a cell move.
8. **Stale schematic/PCB source boundary.** Explicit fresh-placement runs now
   perform source normalization for every manifest board, not one family.
   Normalization occurs in a working copy and does not modify an incumbent.
9. **Misleading suite status and mixed-code results.** The new bounded suite
   coordinator distinguishes execution completion from physical admission,
   hashes the complete source hierarchy and engine, rejects non-manifest wave
   inputs, limits parallel jobs and enforces a start-time free-disk floor.
   A mixed-engine campaign is exploratory, never qualified for promotion.
10. **Pair tier classification by spelling.** Staged signal-layer restrictions
    now use derived pair membership instead of assuming `_P/_N` or CAN names.
    Complete forensic tier records remain in JSON; console logs are compact.
11. **Resume retried a routing-owned repair as placement.** A canonical replay
    launched 1,759 placement proposals for a raw craft finding already admitted
    as an executable route-time local-cell repair. Resume now uses the same
    shared craft-admission contract as the physical gate and does not optimize
    clean margin by default. Hard placement blockers still require repair.
    The unproductive owned `e` campaign was stopped; the source was unchanged
    and the corrected `f` continuation was started.

Recovery adoption additionally requires unchanged protected copper and poses,
debt-monotonic full-board scoring, independent connectivity/DRC pair signoff,
the independent high-speed physical-pair checker, and the ordinary placement
and priority gates. Missing evidence is a refusal. Source/engine changes during
future recovery runs invalidate adoption.

## Source corrections

EPS and PCIe 3-port source inventory exposed the same TJA1051/3 VIO bypass
return error. The existing C8 return was changed from GND to +5VSB and assigned
to U2.5; no new BOM line was added. This follows
[NXP AH1014, section 8.9](https://www.nxp.com/docs/en/supporting-information/AH1014.pdf).
Fresh exported netlists verified **only C8.2 changed nets** on each board.
Required supply roles now resolve 14/14 for EPS and 17/17 for PCIe 3-port.
Evidence: `build/suite-supply-*-verified-20260910.json`.

## Cross-board results

All six manifest-enabled current main boards were exercised. They have not all
earned routing admission, and blocked candidates have not been promoted.

| Board | Latest relevant result |
|---|---|
| 12VHPWR | Critical-only routing waves; first provisional result 4 DRC / 220 opens; full pair gate still blocked |
| Standard Hub | Courtyards/craft pass, but two required-width power paths remain unavailable; 6/8 paths |
| ATX 24-pin | Fresh placement reached its 30-minute budget; its incomplete power-authority artifact was correctly rejected as a continuation input |
| EPS rev3 | Source bypass defect fixed; fresh placement still has terminal/body conflicts and unresolved power corridors |
| PCIe 3-port | Source bypass defect fixed and source normalization passed; fresh placement reached its 30-minute budget |
| PCIe 2-port | Fresh candidate remains placement-blocked; archived 0-DRC/0-open regression control remains byte-identical |

ARGB and output-daughterboard entries are not manifest wave-enabled and were
reported as such, not silently treated as successful routing runs.

Campaigns: `build/current-suite-20260910-a`, `build/current-suite-20260910-c`,
and `build/current-suite-continuation-20260910-d`. Runs that overlapped engine
edits are diagnostic; they are not single-revision cross-board qualifications.
These three campaigns occupy approximately 99 MiB together. WSL had 78 GiB
free at the last check. Intermediate tier scratch directories are disposable.

## Regression and limits

The PCIe control at
`build/board-archive/20260831T1619-pcie-8pin-2port-v113-zero-open-v43/board.kicad_pcb`
retains SHA-256
`d6bc7c2df081a5c9f8ec32da8586071464c5fe8ba8dc3383c17ffdcb809789ea`,
0 DRC, 0 opens, 615 tracks and 226 vias. Its eight pre-existing broader release
blockers remain; this replay is not a renewed fab approval.
See `build/priority-recovery-pcie-control-20260910.json`.

Focused tests cover source normalization, suite admission, endpoint transforms,
lane polarity, tree alternatives, rollback, staged prefix preservation and
recovery fail-closed behavior. The final run is recorded in
`build/routing-recovery-verified-tests-20260910.log` (231 passed) and the final
resume-policy replay in `build/routing-recovery-resume-tests-20260910.log`.

A native-pad CAN experiment passed constructive geometry/ownership checks but
introduced DRC debt under full scoring. It was not promoted. The authoritative
waves instead start from the original 4-DRC input; the earlier experiment under
`build/priority-recovery-12vhpwr-20260910` must not be used as an incumbent.

Remaining work is evidence-directed closure of CAN/USB physical admission,
pinch-point/terminal packing on the other boards, and then residual routing.
This run proves a previously unreachable routing stage now runs; it does not
prove unattended fab closure of the suite or arbitrary future boards.
