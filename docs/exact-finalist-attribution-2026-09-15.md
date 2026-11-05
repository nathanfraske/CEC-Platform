# Exact finalist attribution and suite review — 2026-09-15

## Completed three-board pass

`build/reservation-index-suite-20260915/suite.json` completed with **no newly
admitted placement or route**. Hub took 746.0 s, PCIe3 371.3 s and 12VHPWR
974.6 s. All source-board, hierarchy and engine signatures stayed unchanged.
These bounded passes do not establish a full-wave speedup from reservation
indexing: all three retained their blockers and their exact input boards.

The immutable body-free gallery was inspected and the dashboard returned HTTP
200. Its three cards say PLACEMENT / BLOCKED / NOT FAB SIGNOFF. They must not
be advertised as new routed results:

- [Hub](http://localhost:8090/?id=pass-reservation-index-suite-20260915-hub-standard-rev2-308b6d0f10)
- [PCIe3](http://localhost:8090/?id=pass-reservation-index-suite-20260915-pcie-8pin-3port-4fcda58878)
- [12VHPWR](http://localhost:8090/?id=pass-reservation-index-suite-20260915-12vhpwr-standard-b9c4bedb6c)

The gallery is `build/reservation-index-suite-20260915/all-boards-20346f7a04057652.png`.
Windows copies remain in `C:/Users/Admin/Documents/CEC-Board-Reviews/reservation-index-suite-20260915/`.

## Proven logging defect and generic fix

PCIe3's priority-repair report had one exact finalist evaluation, eight early
critical-rank improvements and a final `access_gain_worsened_full_capacity_key`
refusal. But it retained only the incumbent key, not the losing finalist key.
The exact candidate PCB was deleted with the temporary directory before the
decision report returned. That evidence cannot establish whether congestion,
critical routing, another earlier field or an equal key decided the refusal.

The shared repair now records the original ordered key field names, both keys,
all changed fields, the first decisive difference, equal versus worse versus
better, the proposal, early critical rank and pre-analysis PCB hashes. Before
temporary cleanup it can retain up to two exact baseline/candidate bundles
per operation, including project/rule/power sidecars and the complete compact
finalist evidence. Each bundle is capped at 64 MiB, with a 16-GiB free-space
floor. Source hashes are checked before and after capture; incomplete or
unavailable capture is explicitly reported, never claimed as verified.

The outer pipeline summary carries the comparison and artifact pointers too.
Diagnostic artifacts have no promotion or release authority. No ranking weights,
priorities, geometry, clearances, currents or acceptance conditions changed.

## Regression checks

- `build/finalist-evidence-final-tests-20260915.log`: **247 passed, 13 skipped**,
  88.36 s. Tests cover every ordered key field, early/late metric disagreements,
  equal keys, original legacy aliases, invalid numeric input, hash drift,
  byte/count/storage budgets, failed copies and actual repair acceptance and
  rejection paths. Existing placer, preflight, full-pipeline, budget and
  generalization suites are included. An initial test reused its synthetic
  authority cache; isolating that mock cache fixed the test, not production code.
- `build/finalist-evidence-control-20260915.json`: protected PCIe2 board hash,
  board regression and all four probes exactly match
  `build/reservation-index-control-20260915.json`. Its pre-existing broader
  release/pair/craft failures remain; unchanged control evidence is not fab
  qualification.
- The static generic core now checks 62 modules with zero selector violations.
  The broader legacy 23 physical / 380 runtime findings remain, so whole-pipeline
  generic maturity is still false.

## Bounded native replay

`build/finalist-evidence-replay-20260915/` is a **diagnostic-only** replay of the
completed PCIe3 priority operation. Its `lineage.json` identifies the exact
previous operation, source board hash, config and source-plan provenance.
The same six manifest-rooted input/hierarchy hashes are checked at entry/exit.
It uses a 600-second operation limit and retains no fabrication authority.
The operation completed normally in 308.305 s. All six source/hierarchy hashes,
its original operation board and the engine stayed unchanged. The old baseline
context was correctly refused after context changes and recomputed; its key
matched the earlier baseline. The retained bundle is
`finalist-evidence/finalist-dmvkv6mk/` (1,337,636 bytes).

### Native finding and second generic correction

The retained `pair_failure_portal_shift` moved the two series resistors shared
by CAN and CAN_J1. The early probe reported 10 critical refusals, versus a
baseline of 11. Complete finalist authority instead reported 12: nine Kelvin
failures, two pair failures and one USB-quality failure. The decisive key field
is therefore `critical_route_refused_count`, **not congestion**. The candidate
SHA256 is `b3a3e7721ad52bc57dbcd0574dcc7ac3ba2480c2921e71b7017908c746733279`.

The partial probe checked only the already-refused CAN pair. It both omitted
the independent USB backtrack from its total and skipped previously clean
CAN_J1 even though it shares the moved series components. CAN remained refused
for coupling, and CAN_J1 became unroutable in the full check. No bad candidate
was admitted, but the falsely improved early total wasted later evaluation.

`cec_probe_scope.py` now makes these rules reusable:

1. Partial probes retain baseline pair/quality failures outside their measured
   scope. Missing legacy/truncated identities remain conservatively counted.
   Kelvin-only probes retain unmeasured pair and quality failures too.
2. Candidate pair scopes include all current native net-connected pairs sharing
   any moved component, in addition to refused pairs. Truly independent pairs
   still receive the mandatory complete finalist recheck.
3. The probe budget accounts for the expanded pair scope, and each trial logs
   measured scope and carried failures. A partial probe is explicitly not
   complete-board authority. Complete probes may still demonstrate genuine
   improvement; there is no unconditional baseline floor.

`build/probe-scope-tests-20260915.log`: **280 passed, 13 skipped**, 123.95 s.
This overlaps the earlier 247-test set; do not add the counts. The fresh
`build/probe-scope-control-20260915.json` again matches all four protected
PCIe2 probes, board regression and SHA. The neutral core has 63 modules, zero
selector violations; the broader legacy findings remain unchanged.

The bounded native A/B and six-board dependency readback completed under
`build/probe-scope-replay-20260915/`. The legacy-scope native replay reproduces
raw 10 refusals; merely retaining the unmeasured USB failure corrects that to
11, already eliminating the false improvement. Expanding to CAN plus CAN_J1
produces raw 11 / corrected **12**, exactly matching the complete finalist
check. That expanded native probe took 84.05 s; this is a correctness result,
not a claim that measuring more dependencies costs less in isolation.

All 46 component-to-pair scope checks on the six actual input boards passed:
12VHPWR 8, ATX 8, EPS 5, Hub 11, PCIe2 7, PCIe3 7. These are dependency-selection
checks, not full routing or release checks. Sources, hierarchies, the retained
diagnostic candidate and engine hashes stayed unchanged.

## Completed canonical follow-up

`build/probe-scope-suite-20260915/suite.json` tested the complete producer on
PCIe3, where the native defect was reproduced. It used the original explicit
input, two workers, twelve placement trials, eight route passes, a 1,800-second
board deadline and a 1,200-second priority-operation cap. It completed in
350.461 s without an admitted placement. Early claimed improvements fell
from eight to one; no losing finalist reached full evaluation. Four pair
probes ran and three proposals were deferred, not proven infeasible. All
source/hierarchy/engine hashes stayed unchanged. The power-replan handoff
needed a further durable failure-stack repair; see
[the next slice](bounded-power-replan-and-failure-stack-2026-09-15.md).

The first two current 12VHPWR probe moves involve D3/C5; their pair scope and
zero baseline quality count are unchanged by this slice, so they were not
repeated as another full wave. Its native scope readback does confirm that
future FL1/R22/R23 moves include both CAN and CAN_INT. Hub's current blocker is
in committed-power pair construction, not this partial-screen accounting, so
its unchanged exhausted run was not repeated either. This is deliberate
affected-board dispatch, not a claim that all six boards are routing.

No unchanged full Hub or 12VHPWR campaign was repeated for this logging-only
change. PCIe2 remains 0 DRC / 12 opens in its latest partial continuation.
EPS and ATX remain blocked by actual fixed terminal-pad conflicts and coupled
mating qualification. The existing straight-row pitch samples exceed their
declared last-datum limits, but are not a proof that every 2-D arrangement is
impossible. No land shrink, independent mating-half move, dimension increase
or invented 3-D transform was used to bypass those constraints.
