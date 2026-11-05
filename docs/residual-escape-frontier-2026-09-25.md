# Residual escape frontier, 2026-09-25

## Authority and retained result

Continued the verified **0 DRC / 11-open Standard Hub**, not a schematic seed
or an older BETA placement:

`build/residual-continuation-20260924/hub-final-v2/final/incumbent/board.kicad_pcb`

SHA-256: `959eef1c40c32e6d86cdcf3120f96045e3cb0e61b5f10eb294fef1b55e65214d`.

The independently admitted production-coordinator result is **0 DRC / 9 opens**:

`build/residual-escape-20260925/hub-coordinator-verified/final/incumbent/board.kicad_pcb`

SHA-256: `5d66fe45a72b27aeab6ea868684df6d8b5696a02ddc62ddcebdf9e0cc4521be8`.

This closes one +5V_SYS branch and the U7_SS pin escape, including restoration
of its displaced ground connection. It does not close the whole rail or board.
The saved candidate passes fresh independent dimensional conformance and
loses no formerly passing route-oracle gate. All **681 locked primitives** in
the 11-open input, eight rated source/sink connectivity paths, qualified
USB/CAN pairs, functional placements, outline and power declarations remain
unchanged. Input file families are unchanged. Connectivity is not thermal or
fabrication qualification.

Evidence is in `build/residual-escape-20260925/hub-coordinator-verified/`:
`result.json`, `preservation.json`, `independent-signoff.json`, and the full
fresh oracle at `final/incumbent/oracle.json`.

## Root causes and generic changes

1. **Wrong-layer escape attribution.** The negotiation rank counted a clear
   hypothetical inner-layer ray as if a blocked SMD surface already had a
   transition to that layer. It now retains the actual surface-trap evidence.
   Complete, all-policy-movable blocker sets from individual surface rays are
   offered before broad histogram windows. The cut is never truncated to fit
   a budget and never includes fixed pads, zones or protected copper. Exact
   cuts do not expand into neighbouring via dogbones. Broad alternatives remain.
2. **Missing 45-degree graph edges.** The maze allowed diagonals only between
   adjacent X/Y array indices. Adding pad or obstacle coordinates subdivides
   those axes differently, deleting valid 45-degree moves. Neighbours now
   follow exact coordinate differences on the nonuniform lattice. The entire
   resulting segment still passes the same native copper and edge guards.
3. **Duplicate anchor attempts.** A junction represented by several track
   ends and a pad consumed multiple scarce attempt slots. The live GPIO0
   frontier contained 13 candidate pairs but only six distinct physical
   choices; each OV1 frontier had six pairs but only three choices. Exact
   coordinate/layer/escape-contract aliases are now coalesced before top-K
   selection. Different layers or neck-down authority are not merged.
4. **Repeated expensive launch searches.** Via-seat enumeration could run
   hundreds of nearly identical failed local mazes before another anchor or
   bridge layer was considered. It now tries cheap guarded canonical launches
   first, retaining a bounded expensive frontier derived from `seat_limit`
   (8–64 seats). A private immutable-plan cache reuses the same launch stub
   and all-layer-qualified barrel across bridge-layer attempts. No cache
   survives board mutation or a different plan.
5. **Underfunded native workers and false search history.** The additive
   stage could start a one-second worker with less time than native startup
   and report it as sampled geometry. Admission now requires at least five
   seconds of real search plus worker/save and admission reserves. Worker
   startup/IPC failures do not populate sampled-domain history.
6. **Inconsistent residual search domains.** Canonical search considered
   branches up to 80 mm but its obstacle-aware fallback silently stopped at
   25 mm. The successful isolated route used a 38.11 mm anchor separation.
   The residual worker now exposes a validated `max_route_mm` parameter,
   defaulting to the same finite 80 mm domain, with the original aggregate and
   per-net deadlines. This is a search-domain change, not a clearance waiver.

No new production dispatch is keyed to a board name, net name, refdes or
coordinate. Diagnostic reports name the measured objects, not repair rules.
Algorithm revision is `2026-09-25-bounded-launch-and-residual-domain-v62`;
older search hints therefore cannot suppress the newly available domain.

## Experiments and limits

- Ten independent baseline per-net probes all retained 11 opens. Each had a
  20-second search allowance; proposals were not concatenated.
- The maze-edge correction alone also retained 11 opens. Its synthetic
  regression demonstrates a real graph defect, but it is not credited with
  a measured Hub closure.
- An early minimal U7_SS surface cut closed that pin but stranded the ground on its
  neighbouring support resistor. The all-board transaction rejected it.
  The crossing ground trace was **not** proven redundant. LED alternatives
  also failed displaced-ground restoration and were rejected. This test
  preceded the launch-frontier and search-domain fixes; the final production
  run subsequently restored the displaced ground and admitted the U7_SS repair.
- The first 240-second production certificate run with surface cuts, maze
  edges and alias coalescing retained the original 11-open input.
- With the bounded launch frontier, the otherwise identical +5V_SYS probe
  closed one connection. Full fresh grade, preservation and independent
  signoff then admitted the intermediate 10-open candidate in
  `hub-verified-10/`. Other independent probes
  did not close another connection. Several negative searches returned much
  sooner, but the candidate frontier changed: this is not an equal-coverage
  solver-speed benchmark or an exhaustive proof of impossibility.
- The normal routing coordinator was replayed from the original 11-open input
  in `hub-production-coordinator/`, using the actual board recipe, without
  supplying either successful isolated route. Round 00 admitted the power
  branch (11 -> 10) and a complete atomic target-plus-ground repair (10 -> 9).
  Round 01 exhausted its bounded search without an accepted change and kept
  the nine-open incumbent. Total coordinator wall time was **524.32 seconds**;
  each certificate round was bounded to 240 seconds. This is a routing
  continuation replay, not a new end-to-end placement or fabrication run.
  Optional finish dimension/fabrication repair was disabled for this replay;
  the independent signoff still reports those outstanding qualifications.
- The final coordinator winner was copied, independently graded and signed
  off again in `hub-coordinator-verified/`. Its hash matches the published
  final archive. The earlier `hub-verified-9/` checkpoint came from round 00
  before coordinator finalization and is superseded by this final artifact.

Release remains withheld. Nine native opens span nine nets. The same two
CAN_TX/TEMP_HUB interference findings remain verbatim; route geometry has
zero blocking angle violations and zero non-octilinear segments, but **ten
advisories versus nine at intake**. The restored ground route added a covered
collinear overlap on F.Cu: this is recorded as a craft regression, not waived
or described as a fully regression-free result. No formerly passing oracle
gate became failing, but that does not mean advisory counts are unchanged.
Courtyard, thermal/injection, hardware and draft-source qualifications are
not waived. The remaining open nets are +3V3, +5V_SYS, /KVM_5V_IN, GPIO0,
U11_OV1, U11_SS, U7_OV1, /USB_VBUS and Net-(DL5-DOUT) (the short names refer
to their existing hierarchical names in the native reports).

Next work should use the remaining endpoint/blocker certificates to improve
bounded target-and-neighbour restoration, not run the same exhausted search
again or transfer connectivity debt to ground. The additional craft repair
needs generic, width-aware collinear-overlap normalization that preserves
protected copper and the full copper union; the existing Kelvin in-call
coalescer does not cover this residual-route case. There was no UUID- or
coordinate-specific cosmetic edit in this slice.

## Cross-board and publication checks

The PCIe two-port fab-review control is unchanged at **0 DRC / 0 opens**,
SHA-256 `2f09d2765bacc5281a52fc7b6afaafa06078fb3aa1c1c2be037b708edd059388`.
`pcie-control-final/native-control.json` records a fresh full grade and actual
native last-mile replay with unchanged copper and source family. Its existing
pair/thermal qualification findings are not hidden by zero connectivity debt.

The active Hub/ATX pairing manifest remains `dfbeccb8...`, and the current ATX
placement remains `83799200...`; neither was edited.

Dashboard archive:
`20260925-hub-standard-rev2-checkpoint-continuation-5d66fe45a7`.
The source and archived PCB hashes match. Both model-free images and all six
native copper-layer panels returned nonempty HTTP 200 responses from Windows.
The review images explicitly say **NOT FAB READY**. Opening the page in the
app returned `queued`, not proof that the user's pane visibly navigated.

## Verification

- `final-feature-v62-tests.log`: 279 passed and eight subtests passed.
- `regression-final.log`: **633 passed, eight subtests passed, four skipped**
  in 150.77 seconds. The four skips explicitly require `CEC_RUN_REAL_ROUTER=1`
  for minute-scale fixtures; actual Hub and PCIe control replays above were
  run separately, not substituted with mocked routing.
- `hub-production-coordinator/native-coordinator.json`: 0 DRC / 9 opens,
  `route_residual_resume` winner, source family unchanged, 524.32 seconds.
- `hub-coordinator-verified/result.json`: accepted routing progress,
  preserved authority, no formerly passing oracle gate lost, dimensions pass.
  Independent release signoff remains failed and is retained alongside it.
- `pcie-control-final/native-control.json`: unchanged 0 DRC / 0 opens,
  13.543 seconds, actual native last-mile replay.
- `git diff --check` passed. No schematic, placement-authority, input PCB or
  shared power-budget edits were made by this slice. No identical unbounded
  routing loop was left running at the plateau.
- New synthetic coverage includes both board sides, unfamiliar component/net
  identities, immutable blockers, complete cut caps, exact diagonal hops,
  full-segment collision rejection, preserved layer/escape authority,
  per-plan cache lifetime, underfunded worker admission and long residuals.
