# Residual-first routing continuation, 2026-09-24

## Authority and scope

Continue the verified Standard Hub artifact, not a placement-only source or
an older BETA board:

`build/route-checkpoint-continuation-20260923/hub-recovery-28-v4/winner.kicad_pcb`

SHA-256: `445b40561b8871cc1b32d8c63a2fb3f1bc31b0f15f692190142496de111d3396`.
Its independently measured starting point is **0 DRC / 28 unconnected**.
No schematic, BOM, outline, functional placement, power declaration or
fabrication clearance was changed in this slice. All routing proposals still
require native admission, protected-prefix preservation, and a fresh full
route oracle. Connectivity is not thermal or fabrication qualification.

## Findings

1. The preceding global route/import consumed its campaign lease before the
   existing certificate-repair stage could start. The stage explicitly logged
   `campaign_finish_reserve`. This was unperformed work, not proof that the
   remaining nets were geometrically impossible.
2. Import-time completion inherited a historical 0.25 mm clearance floor.
   The current project uses 0.20 mm for these branches. Independent, otherwise
   identical per-net probes with both settings produced the same gains on
   this Hub. Correcting the caller is generic rule-authority hygiene; it is
   **not** the explanation for this board's measured improvement.
3. The deeper certificate portfolio spent much of its lease repeating the
   canonical breadth pass that had just run. Its short-distance prefix also
   repeatedly took the limited deep-search slots. Separate per-net tests on
   the 13-open incumbent found a legal +3V3 connection and a legal USB-power
   connection. These independent proposals were not concatenated or counted
   as a combined two-connection improvement.

## Generic implementation

- `cec_full_pipeline._resume_route_residuals` gives a freshly graded,
  DRC-clean routed incumbent with a small remaining open count a bounded
  continuation through the existing certificate engine, before global routing.
  The default 32-open cutoff is a configurable search-allocation policy, not
  a geometric rule. Two rounds are default; four is the hard cap.
- Every accepted round needs fewer native opens, no DRC increase, unchanged
  parent/power/pair/placement authority, no loss of a previously passed oracle
  gate, and a complete fresh grade. A plateau stops this portfolio. Source
  mutation is a fatal integrity error, not another search candidate.
- An admitted continuation bypasses a redundant global route. An unsuccessful
  one leaves global search available. Zero airwires cannot bypass the normal
  router when a route-related physical gate, such as pair qualification, fails.
- The deep certificate pass gets its full bounded deep-search allowance;
  it no longer first repeats the already-performed canonical breadth pass.
  It prioritizes untried work and multiple certified open opportunities before
  the usual distance ordering. It never removes a net from eligibility.
- A small `.route-search.json` sidecar retains per-stage search counts on the
  selected private artifact. PCB hash and algorithm revision bind reuse;
  malformed/stale hints are discarded. These are scheduling hints only, not
  obstacle certificates, geometry authority or no-path evidence.
- Ordinary/final import completion and the isolated import-repair worker use
  the project's exact netclass clearance. Foreign-net requirements still
  participate in the exact guard; native DRC remains mandatory.

No board identifier, reference designator, net name, or coordinate is a repair
dispatch condition. Names appearing in measured diagnostic reports identify
observations only.

## Measured sequence before the fairness retest

| Retained artifact | DRC | Unconnected | What ran |
| --- | ---: | ---: | --- |
| Verified input | 0 | 28 | Fresh baseline measurement |
| `ablation/01-floor-0.0/board.kicad_pcb` | 0 | 23 | One independently admitted per-net probe |
| `certificate-round1/certificate-repaired.kicad_pcb` | 0 | 15 | Existing certificate engine, 240 s |
| `certificate-round2/certificate-repaired.kicad_pcb` | 0 | 13 | Existing certificate engine, 240 s |
| `hub-coordinator/winner.kicad_pcb` | 0 | 12 | Production residual-first coordinator; second round stopped at no progress |

All paths in the table except the initial source are under
`build/residual-continuation-20260924/`. Real searches were used; no route result
was injected. Full grade and preservation reports accompany the retained
proposals. The coordinator honors the selected board recipe's repair effort
parameters; the earlier isolated tests used a broader explicitly recorded
target budget.

## Control and limitations

The PCIe two-port final-fab-review control remains **0 DRC / 0 unconnected**,
SHA-256 `2f09d2765bacc5281a52fc7b6afaafa06078fb3aa1c1c2be037b708edd059388`.
`pcie-native-final-v5/native-control.json` records fresh full grading, the
actual native last-mile call with project clearance, unchanged copper
inventory, and unchanged source family (11.764 s). Its pre-existing pair and
thermal qualification findings remain visible; zero opens do not waive them.
An earlier coordinator replay also retained the exact control, but the final
control additionally checks that a failed route-physics gate cannot take the
closed-board fast path.

The 12-open review artifact was published with hash-bound model-free top and
bottom renders and six native copper-layer plots. Every panel returned a
nonempty HTTP 200 response from Windows. It is explicitly marked NOT FAB READY.
The Hub still needs all remaining connectivity closed, the inherited courtyard
edge issue addressed, and injection/thermal/release qualification completed.

## Fairness retest and late-save forensic

The production coordinator in `hub-fair-coordinator/` admitted **0 DRC / 11
unconnected**. The deep portfolio reached +3V3 and closed one connection that
the previous scheduling prefix did not reach. The next round recorded its
search history and stopped at no progress. It did not start another identical
global routing wave. Total coordinator wall time was 523.839 s.

Independent signoff then exposed a separate late-save defect: a generated
USB-power track was only **1 nm long**. The first appearance was in
`certificate-round2/`, as recorded by `dimensional-forensic.jsonl`. It passed
ordinary KiCad DRC but failed the independent netclass-minimum classifier;
the earlier generic oracle did not expose that classifier as an individual
admission term. An already-failing aggregate gate could therefore hide this
new dimension failure during intermediate selection.

The repair save boundary now invokes the shared micrometre-bounded degenerate
track sanitizer **before** refill and width-group reconciliation, while
preserving every locked primitive. The route oracle also exposes a separate
`netclass_geometry_ok` gate, and the fresh-wave publisher rechecks it on the
actual saved board after hygiene. Missing/error results fail closed. The
gate-schema registry and regressions were updated with the new term.

Replaying this generic save operation removed two unlocked quantization
artifacts, including the offending USB-power item. It did not change DRC or
connectivity. No refdes, net-name or coordinate exception was added.

## Final retained board

Use this artifact for the next routing continuation:

`build/residual-continuation-20260924/hub-final-v2/final/incumbent/board.kicad_pcb`

SHA-256: `959eef1c40c32e6d86cdcf3120f96045e3cb0e61b5f10eb294fef1b55e65214d`.

- **0 DRC / 11 unconnected**, versus 28 at intake: 17 fewer, or 60.7% reduction.
- Independent dimensional conformance passes; no formerly passing oracle
  gate regressed. The original and intermediate source families are unchanged.
- All **641 locked primitives** present in the 28-open input are preserved,
  as are functional placements, outline, physical power declarations, the
  qualified USB/CAN pairs and all **eight rated source/sink connectivity paths**.
  This is not proof that every auxiliary power branch is connected or thermally
  qualified.
- The previously reported stranded IC-power condition is no longer present.
- The Hub/ATX active placement manifest and ATX placement retain their prior
  hashes (`dfbeccb8...` and `83799200...` respectively).

`hub-final-v2/result.json`, `original-prefix-preservation.json`, and
`independent-signoff.json` contain the final evidence. The final dashboard
archive is `20260924-hub-standard-rev2-checkpoint-continuation-959eef1c40`.
Both model-free renders and all six copper plots returned nonempty HTTP 200
responses from Windows; archive and source PCB hashes match.

Release is still withheld. The remaining 11 opens span ten nets, including
power branches, controller support pins, boot and LED control. Independent
signoff also retains the inherited CAN_TX/TEMP_HUB field-coupling findings,
the courtyard-edge problem, thermal/injection and hardware/draft qualification
requirements. Route geometry is octilinear with no blocking angle violations,
but **nine route-shape advisories** remain (seven at intake); these must be
polished before release, not silently called fab-ready.

## Final verification

- `regression-complete.log`: **571 passed, 8 subtests passed, 4 skipped** in
  158.40 s. The four skips are explicitly opt-in minute-scale real-router
  fixtures (`CEC_RUN_REAL_ROUTER=1`), not suppressed failures. This turn's
  separate real Hub searches and native PCIe replay are recorded above.
- `final-save-and-publish-tests.log`: **48 passed**, including the additional
  late-publisher dimensional recheck, which was added after the consolidated
  suite started. This focused set overlaps the consolidated suite.
- `git diff --check` passed for the changed production modules.

All routing search processes from this slice have stopped. The last bounded
portfolio retained its best verified work at a plateau; no unattended retry
loop or fabrication release was started.
