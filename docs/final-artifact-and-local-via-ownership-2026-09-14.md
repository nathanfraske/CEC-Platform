# Final-artifact checks and local-via ownership — 2026-09-14

Later evidence correction: the saved local-via output's eight dimension failures
below were undercounted by one whole-track neckdown exemption. The corrected
count is nine; see [original-track proof](prefix-followup-and-original-neckdown-proof-2026-09-14.md).
The earlier tables remain historical receipts, not the current signoff baseline.

## Result and scope

This slice fixes generic admission/checking causes and replays the production
repair stage on the current PCIe2 winner. It does **not** claim routing closure,
an all-board full pass, thermal qualification, or fabrication release.

| Exact native measurement | Before | After automatic stage |
| --- | ---: | ---: |
| Structural DRC | 0 | 0 |
| Unconnected items | 17 | 17 |
| Unqualified same-net via/pad overlaps | 6 | 1 |
| Independent under-minimum dimension violations | 18 | 8 |
| Decoupler adjacency/access on final artifact | pass | pass |
| Completed decoupler cells on final artifact | 14/14 | 14/14 |

The 18/8 dimension counts use the tightened live-topology proof on both inputs.
They are not comparable to the older dimensions-only exemption's six-feature
count. No rule floor or design power/current budget was relaxed.

Immutable source:

- `build/current-search-branch-full-suite-20260914/pcie-8pin-2port/04-route/winner.kicad_pcb`
- SHA256 `9f445b897a341ae5027543b2c98015c5b9a2b5ec543b465c2c51db5f318eb492`

Admitted repair-stage output:

- `build/local-pofv-auto-stage-20260914/board.kicad_pcb`
- SHA256 `a9a74cad9bd7074b53e35a6696e0b842babd7b2f70c52bfbfcbd113ffa3c17a7`
- Dashboard: `http://localhost:8090/?id=20260914-pcie2-local-via-qualified`
- Archive: `build/board-archive/20260914-pcie2-local-via-qualified`
- Body-free top/bottom previews are mirrored into
  `C:/Users/Admin/Documents/CEC-Board-Reviews/20260914-pcie2-local-via-qualified/`.

Source bytes, placements, board outline, net assignments, power pours and track
routes were not edited by the admitted stage. Five already-generated local
barrels were resized in place to the declared process's 0.30 mm land / 0.20 mm
drill, with exact independent containment checks. The sixth cannot fit at its
current centre and is explicitly refused; it needs a bounded owner rebuild.

## Root causes and generic changes

### 1. Final checks were reading different artifacts

`route_oracle_grade` called `_oracle_decoupler_adjacency(placed, cfg)` but
audited completed cells on `routed`. Adjacency now includes exact local supply
and return access, so checking the placement discarded already-admitted copper.

The saved winner passes both native checks across all fourteen cells. No
capacitor move was justified by the stale-file failures. Final adjacency,
body-versus-pour and pour-uniformity checks now all read `routed`; adjacency
records the exact artifact path. Placement preflight remains separate.

Evidence:

- `build/local-access-forensic-20260914/report.json`
- `build/final-artifact-before-grade-20260914/report.json`
- `build/local-pofv-auto-stage-grade-20260914/report.json`

### 2. Dimension legality was mistaken for local-via ownership

`group_local_pofv_signal_vias` previously checked only the selected profile's
diameter/drill limits, then grouped and locked qualifying objects. That could
freeze a partially overlapping or remote barrel and grant it a local netclass
exception before anyone proved its pad connection.

`cec_fab_profile.local_pofv_via_decision` now requires:

- A declared filled/capped profile and a same-assigned-net through via.
- Legal drill and annular dimensions.
- No foreign or unqualified partial pad overlap.
- Either full containment inside an actual SMD land, or an actual short track
  joining that land on its copper layer (default bounded reach 1.50 mm).

The generator uses this proof before ownership/locking. Independent final
netclass checks repeat it from live geometry; group membership alone cannot
grant an exception. A caller-owned cache is limited to one immutable board
inspection. Unrelated owners are not adopted or unlocked.

The existing profile normalizer now also checks **every overlapping pad** for
dogbones whose centres lie outside their nominal owner. A historical evacuated
branch is not a live connection: it cannot obtain a new local-via exemption
until reconnected and re-proved.

The exact generating/importing substage of the six historical bad barrels is
not yet proven. The demonstrated defect is their admission and locking based
on dimensions alone; this document does not guess their original creator.

### 3. Fabrication-only failures lacked an automatic repair stage

Native DRC did not produce structural errors for these overlaps, and ordinary
certificate repair skips locked owners. `repair_local_pofv_admitted` now runs
before residual certificate search, even when structural DRC is zero.

This stage:

1. Uses independent via/pad failures to select exact generated local-via
   owners; no board name, refdes, coordinate or net-name repair table.
2. Tries the shared fixed-centre profile normalizer under bounded target and
   wall-clock budgets (defaults: 16 targets / 120 seconds).
3. Refills the disposable trial and compares independent native score,
   dimension/assembly identities, other constraint failures (including current
   and pair checks), route craft, and fabrication snapshots.
4. Admits only strict dimension or assembly improvement with no new failure
   identities or worsened unrelated checks. Otherwise the source is unchanged.
5. Checks the source-family fingerprint before promotion and removes temporary
   boards. An unsuccessful re-probe skips expensive full-board comparisons.

The native production replay was admitted in **20.013 seconds**. A second
replay took **0.454 seconds**, refused the remaining geometry and left the
output SHA unchanged. This is a bounded, idempotent stage, not an endless
component-by-component repair loop.

Evidence:

- `build/local-pofv-auto-stage-20260914/report.json`
- `build/local-pofv-stage-idempotence-20260914/report.json`
- `build/local-pofv-fab-control-replay-20260914/report.json`

## Regression and generalization evidence

- Focused native/synthetic suite: **297 passed, 4 skipped, 8 subtests passed**,
  26.15 seconds. Log: `build/final-artifact-via-stage-final-tests-20260914.log`.
- Tests cover partial overlap, no connection, wrong copper layer, excessive
  reach, rotation, contained vias, ordinary dogbones, unrelated ownership,
  copied/stale groups, no-write refusal, assembly-versus-dimension admission,
  bounded empty/no-progress/timeout cases, and final-stage artifact wiring.
- A broader CL25 run had **167 passed / 2 failures**. The failures concern
  unchanged candidate/source fixtures: Hub candidate lacks schematic C36;
  PCIe3 candidate C8 pad nets disagree with its hierarchy. They are not waived
  or hidden by changing expectations. Log:
  `build/final-artifact-local-via-tests-20260914.log`.
- Generalization gate: 56 core modules, zero core violations; broader existing
  findings remain 380 runtime / 23 physical. Whole-pipeline generic/release
  status remains false. Report:
  `build/final-artifact-via-generalization-20260914.json`.

### Immutable older fab-review control

Control SHA remains
`d6bc7c2df081a5c9f8ec32da8586071464c5fe8ba8dc3383c17ffdcb809789ea`.
Native route metrics remain 0 DRC / 0 opens / 615 tracks / 226 vias /
1242.073 mm; score, route-quality and fabrication probes are unchanged.

The constraint probe is **not identical**: it reports four additional dimension
violations (two vias' diameter + drill), increasing its pre-existing count
from 50 to 54. Read-only reproduction shows the previous exemptions were false:

- `/CAN_TX`: an inner-layer segment under an SMD pad was treated as a direct
  pad dogbone, despite the pad not existing on that layer.
- `/04-mcu/IO8_STRAP`: a short track did not cure partial via-land overlap.

This is newly exposed existing geometry, not a physical change to the control.
Its broader release flags were already false and remain false. Do not describe
this as an all-gates-passing fab regression. The automatic repair actuator was
also replayed on a copy: one eligible barrel was refused, no bytes changed,
0.498 seconds. Other owners were preserved.

Reports:

- `build/final-artifact-local-via-control-20260914.json`
- `build/fab-control-local-via-requalification-20260914.json`
- `build/local-pofv-fab-control-replay-20260914/report.json`

## Remaining work

The current candidate still has 17 opens across ten nets, including power
rails and an unpowered IC. Four vias still account for eight independent
dimension violations; one also has the remaining invalid pad overlap.

The first bounded residual-search replay on the original winner spent its
240-second budget without improvement. A second replay on the newly repaired
artifact also retained 0 DRC / 17 opens and stopped at 241.001 seconds, source
unchanged. It is recorded at
`build/local-pofv-residual-resume-20260914/report.json`.
Its effort ledger records eight early `congestion_via_relocation` attempts,
then `WorkerPoolStalled` at the whole-transaction deadline. The eight error
records are under `plan.congestion_via_relocation.sweep.attempts`, not the
top-level `attempts` array: seven hit a 25-second worker limit, and the eighth
hit its remaining 10.6-second allowance. This is evidence of repeated early-stage
worker timeouts consuming the budget, not evidence that every remaining
routing strategy exhausted its search space. Progress consumers must read the
nested sweep evidence rather than interpreting the empty top-level array as
zero attempted work.
Do not repeat the same exhausted search unmodified. The next routing slice
needs bounded fair budgets and durable per-attempt evidence so early via
relocation cannot consume the complete residual-routing budget, plus the
remaining local via that requires spatial reconstruction rather than sizing.

No new complete Hub, EPS, ATX, 12VHPWR or PCIe3 routing pass was performed in
this slice. The stale Hub/PCIe3 candidate fixtures must be reconciled against
their authoritative hierarchy before being accepted as cross-board controls.
