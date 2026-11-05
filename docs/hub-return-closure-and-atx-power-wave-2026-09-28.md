# Hub return closure and ATX power-construction waves

## Disposition and exact artifacts

**Neither board is fabrication-release qualified.** The Hub is electrically
routed and has no current electrical-constraint blockers. The ATX remains an
open placement blocked on power construction, not a finished routed board.
No fabrication package or order was released. Canonical BETA designs and the
active mating-pair manifest were not replaced.

All evidence below is under `build/atx-hub-closure-20260928/` unless stated
otherwise. The inherited worktree contains unrelated work; this report does
not attribute all modified/untracked files to this slice.

| Artifact | SHA-256 |
| --- | --- |
| Hub accepted parent, `build/hub-fab-qualification-20260928/coordinator-field/winner.kicad_pcb` | `4aba00e18b0646d662fdac54175382d16e8cdc8c70fd1c6634fbfabdc03f6a4e` |
| New Hub, `hub-return-coordinator/finish-comparison/incumbent/board.kicad_pcb` | `166b9b63d88fb7b06e6710d76f08157d3412e7bea8139992fd60d9d9a1277a87` |
| Compact ATX starting placement, `build/hub-atx-placement-routing-20260922-v3/atx-24pin-rev3/02-placement/board.kicad_pcb` | `83799200c0dae6ddd158d66de1e43d548a34547bd59b8d29539d929ac3d7814b` |
| ATX wave01/wave05 placement, `atx-wave05/02-placement/board.kicad_pcb` | `1b08b39ec4756879c7a25e7f56a1b6c42c7f8c329a316d6dc092bea5ab4b7eb3` |
| Immutable PCIe2 control, `build/board-archive/20260831T2253-pcie-8pin-2port-final-fab-review-v103/board.kicad_pcb` | `2f09d2765bacc5281a52fc7b6afaafa06078fb3aa1c1c2be037b708edd059388` |

## Hub: accepted improvement

The remaining CAN_TX/TEMP_HUB field interaction crossed a local reference-plane
opening at a signal via. The exact filled-plane witness was 3/4 covered, with
no nearby grounding return. A bounded topology-derived grounding via now
contacts both actual reference fills. No signal track, placement, protected
power conductor or zone recipe was moved to achieve this result.

The normal coordinator reproduced and admitted the repair in 82.811 seconds;
the repair worker took 8.74 seconds. A separate 26.031-second boundary proof
confirmed source-family, population, placement, project/rule, frozen-power,
protected-copper/fill and paired-geometry preservation.

| Measurement | Parent | New Hub |
| --- | ---: | ---: |
| Native unconnected | 0 | 0 |
| Qualified structural DRC | 0 | 0 |
| Field-coupling blockers | 1 | 0 |
| Vias | 196 | 197 |
| Track length, mm | 2506.414 | 2506.414 |

Independent replay on the exact new SHA (`hub-release-replay-final.json`):

- All **50 electrical constraint checks pass**, no blockers.
- Fabrication geometry: zero blockers, slivers, islands, acid traps or
  drill-aspect failures, using the declared six-layer POFV signal profile.
- Zero non-octilinear routes. Four covered-backtrack craft advisories remain;
  they are not structural DRC failures and protected copper was not deleted
  to improve a cosmetic count.
- Courtyard-to-edge still fails: C37 is 0.475 mm from the edge, versus 0.8 mm.
- Thermal/injection qualification is still false. An electrical/fab-geometry
  subset pass is not whole-board release approval.

Evidence: `hub-return-coordinator/oracle.json`,
`hub-return-coordinator-boundary.json`, `hub-release-replay-final.json`.

## Generic production changes

1. `cec_field_transition_return` derives candidate signal transitions from
   fresh track UUID/net/endpoint topology, not board names or reference lists.
   It refuses missing fills, stale identities and same-layer shielding claims.
   It uses fabrication-legal via geometry, exact clearance, actual reference
   copper contact before emission, and a second contact proof after refill.
   The existing field checker and all final admission thresholds are unchanged.
2. `cec_field_coupling_repair` schedules that bounded return repair before
   offsetting protected routes. Private process trials have a 10-second
   worker budget and must improve the measured field defect without losing
   existing DRC, connectivity, pair, Kelvin or craft gates.
3. `cec_pour_plan.fallback_current_ask` preserves an already margin-inclusive
   current across a geometry-engine fallback. The old handoff omitted its
   marker, so the fallback applied the approved 25% margin a second time.
   Explicit stronger requirements are preserved, invalid values are refused,
   and repeating the handoff is idempotent. Approved rated loads did not change.
4. `cec_power_failure.construction_probe_eligible` and the full coordinator
   now diagnose a rail-only construction block with one **private**, bounded
   exact-power solve. Only an otherwise legal open placement with a complete
   typed force-rail refusal qualifies. Missing evidence, unrelated failed
   gates and routed incumbents do not. The copy has a 120-second process
   budget; sources and configuration are preserved. Even a successful probe
   cannot grant placement/routing/release admission. This is causal evidence,
   not a waiver of the failed force-rail check.

## ATX waves and measurable result

The retained board is still the compact **78 x 95 mm** current placement.
The earlier 82 mm alternative was not substituted or promoted.

| Attempt | Outcome |
| --- | --- |
| wave01, full coordinator | Source intake passed. Placement ran 755.3 s with 64 trials/two rounds; zero native placement conflicts, bounds and constraint gates pass. Two small accepted C62 placement improvements. Force rails remain 1/4 constructed; signal routing correctly blocked. |
| wave02 | Diagnostic wrapper startup failed on an absent `pre_freeze_local_pi` field. No physical wave occurred; do not count this as a board result. |
| wave03, private exact power | 72.117 s. Five current-domain paths not found; proposed standby output still disconnected after actual fill. Source family unchanged. |
| wave04, same input with margin repair | 72.181 s. Failed planner domains reduced **5 to 4**. The 12 V output now has an actual filled shunt-to-terminal connection. Standby output remains disconnected; entire power plan refused. |
| wave05, full coordinator | Placement stage 130.555 s with four trials/one round. New diagnostic invoked automatically and finished in 78.211 s; source family unchanged. Original hard placement gate retained. Output SHA equals wave01: no false placement improvement or promotion. |

The runtimes are not an apples-to-apples solver speedup: wave05 deliberately
used a much smaller placement-search budget and a bounded diagnostic stage.

Corrected fallback sizing (rated demand unchanged):

| Rated rail load | Erroneous old fallback basis | Correct single-margin basis |
| --- | ---: | ---: |
| 3 A | 4.6875 A | 3.75 A |
| 12 A | 18.75 A | 15 A |
| 20 A | 31.25 A | 25 A |

Remaining exact planner failures are +5VSB, SENSE12V_HI, SENSE3V3_HI and
SENSE3V3_LO. SENSE5VSB_LO has a proposed path but fails the native filled
authority connection. These are distinct construction/fill failures, not
ordinary low-current ratlines for the signal autorouter to repair.

Legacy force-rail evidence separately identifies three refused constructions:
source transition seating/conflict with an existing rail, a sink spine through
the fixed CAN mezzanine field, and a standby sink spine through a reset-switch
pad. Existing authored power copper remains protected. The next useful work
is generalized current-aware terminal escape/branch and obstacle-aware
rail construction, not repeating unchanged full-placement waves or shrinking
approved electrical margins.

Detailed causes, exact rejected boards, and worker phase/stack logs are retained
in `atx-wave03-power`, `atx-wave04-power`, and wave05's
`02-placement/power-construction-diagnostic-8adm0n2l/`.

## Current live/live stack check and refused edge experiments

`live-pair/qualification.json` checks the **new routed Hub against the actual
wave05 compact ATX**, rather than silently using the older pinned peer as the
only assembly proof. All 18 contacts match roles and positions, 373 envelope
comparisons pass, both native vent guards are clear and covering, and declared
vertical/hardware bounds pass. The active pair manifest was not changed.
Declared minimum vent clearance is 4.3 mm against 3.0 mm required.

This is a CAD check under declared bounds, not supplier or sample qualification.
`docs/hub-atx-stack-qualification-status.json` remains `PROTOTYPE_BLOCKED`:
connector capture bounds, cable/plug/latch swept volumes, capacitor approval
and cold/aged/startup qualification, hardware/thread/bow and sample fit remain.

The bounded joint edge probe examined 12 native candidate boards after 54
geometry states. Although all corrected the nominal edge gap, they introduced
2-8 native DRC findings; **none was adopted**. A separate earlier private
experiment removed a conflicting redundant GND segment and scored 0/0, but
has not passed the full placement/branch/paired-vent authority transition.
It is not a released fix. A correct solution must handle neighboring support
components, incident copper and the opposite board's vent guard atomically.

The prior thermal screen combined independent maxima rather than proving a
coherent simultaneous source/load scenario. Its 127.392 C value must not be
presented as a qualified real operating temperature or rebound to this new
SHA. Coherent PSU/USB/KVM cases, complete heat-source/package qualification,
and a new exact-artifact solve remain necessary. No new cooling credit,
lower LED duty or reduced approved load was assumed.

## Regression, storage and visibility

Two focused regression invocations passed **214 and 340 tests** respectively,
including full coordinator, force-rail, placement admission, field return,
power-margin and fail-closed diagnostic tests. Scoped `git diff --check` passes.
The new neutral core passes the static generalization audit; the older full
runtime still has **378 findings**, so whole-pipeline generic release is not
claimed.

The immutable PCIe2 control is byte unchanged and still returns 0 DRC/0 opens,
zero fabrication geometry blockers and zero route-craft issues. Its previously
known stricter-release failures remain: RS1 inward Kelvin departure and CAN
reference coverage 80% versus 95%. They were not introduced by this slice and
are not waived. Evidence: `pcie2-release-replay-final.json`.

Both dashboard IDs are present in the live catalog; native model-free PNGs
were inspected. Windows HTTP checks returned 200 for both render assets and
the Hub In4.Cu asset. Hub has all six copper-layer plots:

- [Hub routed checkpoint](http://localhost:8090/?id=20260928-hub-standard-rev2-checkpoint-continuation-166b9b63d8)
- [ATX latest completed placement pass, blocked](http://localhost:8090/?id=pass-atx-hub-closure-20260928-atx-24pin-rev3-f635fa9716)

Windows preview copies: `C:\Users\Admin\Documents\New project\board-review-20260928\`.
Final work storage is approximately 101 MB, with 58 GiB free in WSL. The last
coordinator exits 2 for the documented placement-admission refusal, not a
crash or a timed-out route. All listed waves/tests finished. No repeating
monitor or unsupported promise of a completion wakeup was introduced.
