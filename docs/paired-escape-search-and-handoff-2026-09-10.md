# Paired escape search and handoff slice

## Authority and outcome

Continues the current hierarchical BETA 12VHPWR checkpoint from
`inline-flow-placement-and-route-admission-2026-09-09.md`:
`build/12vhpwr-pair-search-20260909/checkpoint/board.kicad_pcb`, SHA-256
`3a0deb439290e8b7646b1b736e2947d5c1a711d0b3e4f17b7919c0c5b3da0e28`.
All 12 schematic and four authority-control hashes were rechecked. No schematic,
component placement, outline, power bus, mount or pad geometry was edited.

**Not routing-admitted or fabrication-ready.** No new PCB was promoted. Native
score remains 4 DRC, 228 opens, 415 tracks, 12 vias and 837.8186 mm. The unchanged
artifact retains the previous 199-feature protected-power and grounded-mount
proof. See `build/pair-escape-search-20260910/closeout.json` for the live identity,
score, regression and refusal evidence.

## Reusable implementation

1. **Necessary geometry predicates before expensive copper probes.** The old
   conventional fan checked exact middle clearance and enumerated four endpoint
   escapes before discovering that its unmodified middle bearing was not
   octilinear. Each endpoint fan also queried shapes before checking its bend
   geometry. Those same acceptance predicates now run first. They prune only
   candidates that would fail the existing final checks, not merely unattractive
   candidates. Six added regression cases reproduced the defect before repair.

2. **Hard handoff constraints inside the local search.** The joint endpoint
   solver previously used arrival direction as a soft ranking term, after
   retaining its shortest per-member beam. The stub or portal then rejected the
   selected candidate for wrong arrival direction or incoherent P/N arrivals.
   Required heading now filters individual paths before the bounded beam;
   required coherence filters path pairs before selection. Direct, ribbon and
   dogbone alternatives all use the same requirements, and final checks remain.
   Constructive cardinal/45-degree endpoint runways also cover cases absent
   from the old cardinal-arrival templates. These parameters operate on actual
   endpoints and direction vectors, not product or reference names.

3. **Yield optional refinement after finding a usable escape.** A screen that
   had two valid fan-ins could spend its entire deadline trying to find four,
   starving the other endpoint and shared middle. Positive beams now have a
   soft compute share. An empty beam retains the full hard deadline: this does
   not reintroduce the earlier defect of abandoning a difficult escape before
   any solution exists. A partial positive beam is not cached as a completed
   domain. Absolute deadlines and exact acceptance remain unchanged.

4. **Preserve the complete flow-leg attempt.** The wrapper's old whitelist
   omitted endpoint-POFV failures and aggregate/future solver evidence. It now
   retains the structured attempt intact instead of assuming a fixed set of
   solver families. The concise outer reason remains separate. This exposed
   that the USB start endpoint was not qualified for POFV on either alternate
   signal layer; that eligibility is not waived.

The initial suspicion about orientation deduplication was not established as a
defect: the subsequent miter operation intentionally makes many same-centre
variants equivalent. That mechanism was **not** changed.

## Native experiments and measured limits

All runs used the same immutable input and 90-second per-pair budget. The USB
flow scheduler gives this first leg approximately 45 seconds.

| Observation | Before | Final slice |
| --- | --- | --- |
| USB deep surface screen, positive polarity | No valid start fan-in; end not visited | 2 start and 4 end fan-ins |
| USB deep surface screen, negative polarity | Not reached | 4 start and 4 end fan-ins |
| USB deep surface middle attempts | 0 | 16 |
| USB transaction accepted | No | No |
| Retained electrical connections gained | 0 | 0 |

The standalone angle-prefilter replay still took 45.12 seconds and timed out,
versus 45.12 seconds before; this is **not** a demonstrated wall-time speedup.
The complete final CAN_INT/CAN/USB replay took 69.25 seconds and all three
transactions rolled back:

- CAN_INT: final detour rejection, 2.48x / 4.27x against a 2x limit. This rejected
  candidate is worse than the previous 2.15x / 3.15x candidate, not an improvement
  to be promoted.
- CAN: no admitted paired junction at the split-member station.
- USB: outer leg deadline, now with actual shared-middle failures visible.

The first final USB surface middle search exhausted its reachable grid after
33 states, not the 120,000-state cap. Its frontier remained 13.89 mm from the
destination. Exact blockers included the MCU VRAIL_DIV/ISENSE pin field and a
nearby ground pad. Another candidate exhausted after one state. Thus some
locally valid fan-ins terminate in globally trapped pockets. This is evidence
about those candidates, not a proof that the whole board is impossible.

Changing only the CAN tree centre was also tested in a separate, unintegrated
harness. All three choices refused at their junction in 8.52, 8.13 and 10.17
seconds. A different shortest-distance tree alone is not the demonstrated fix.

Profiling the bounded USB failure placed almost all time in portal screening,
particularly local stub enumeration and exact shape checks, rather than a large
global-grid solve. The profiler adds overhead; its timing is diagnostic, not an
unprofiled performance benchmark.

## Regression and next boundary

- `tests/test_pair_search_prefilters.py` adds rotated geometry rejection,
  exact-clearance retention, hard-heading beam selection, incompatible handoff
  refusal, soft-budget behaviour and complete-evidence preservation tests.
- `build/pair-softscreen-tests-20260910.log`: 119 tests plus 2 subtests passed.
- `build/pair-handoff-broad-tests-20260910.log`: 642 tests plus 2 subtests passed
  in 257.84 seconds. The final targeted 19-test suite also passed after the
  diagnostic-only metadata update. Counts overlap and must not be summed.
- `build/pair-handoff-pcie-regression-20260910.json`: the immutable PCIe control
  remains SHA `d6bc7c2df081a5c9f8ec32da8586071464c5fe8ba8dc3383c17ffdcb809789ea`,
  0 DRC / 0 opens, with identical score and broader blocker list. Its eight
  pre-existing broader release blockers remain; this is not unconditional fab
  approval or proof that the entire historical pipeline is generalized.

The next constructive boundary is **global reachability feedback into the
local escape beam**: retain exact dead-end/frontier witnesses, reject equivalent
trapped portals, and replenish with a different outward escape or legal layer
transition. Do not move protected buses, relax clearance/coupling, enlarge the
board, or repeatedly spend more time on the same exhausted pocket. CAN still
needs a separate admitted junction/terminal-orientation solution.

No unattended routing loop was started. Since the PCB itself is unchanged,
there is no new board render masquerading as a changed routed candidate.
