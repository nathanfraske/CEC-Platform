# Frozen planned copper is part of placement authority

## Cause

The ordinary priority-route repair protected saved PCB copper, but did not
carry the complete frozen-plan placement domain into its search or commit.
An open placement can contain no tracks while its sidecar already owns the
power pours. Thus a signal placement could improve its route score, survive
the saved-prefix check, and implicitly require different planned power later.
The previously withheld eight-refusal PCIe3 checkpoint is a real negative
regression fixture for this boundary, not an approved continuation.

## Generic repair

- Bind the existing exact sibling plan to a priority-repair candidate, only
  after normal source/placement authority binding. No invented authority for
  boards without a sibling plan or explicit prospective-power recovery.
- Screen complete placement proposals with the existing native postfreeze
  independence proof **before** the finite routing trial quota. Fixed-terminal
  pruning is followed by exact pad/layer/pour/via contact checks. Sharing a net
  does not waive a foreign-pad conflict.
- Carry that domain into craft co-repair, and recheck the whole composition
  after macro legalization and after co-repair, before exact finalist ranking.
- Priority and craft repair now share an atomic artifact-family commit. A
  refused placement restores the PCB and all sidecars and returns the original
  route evidence. Materialization cannot replace/delete the plan; only the
  independently proved placement snapshot may change.

No board family, reference, pin number, destination or electrical bound is
encoded in these rules. They reuse the existing frozen-consumer ownership and
native geometry checks; they do not grant power-replan or release authority.

## Completed validation

`build/frozen-priority-tests-20260916.log`: **168 passed**, 103.77 s. This includes
loaded six-layer fixtures with zero saved copper, separated-layer vs same-face
contacts, complete-group pruning before a one-trial quota, finite diagnostics,
and real native commit/rollback through the production priority adapter. Plan
replacement/deletion and newly introduced contacts restore the complete input
family and do not advertise the losing route evidence. Existing pipeline,
route-evidence and craft commit tests also pass.

`build/frozen-priority-replay-20260916/report.json`: concurrent current-family
physical/native-domain replay and historical PCIe2 control pass. All six source
PCBs and hierarchy signatures are unchanged. Four current physical/craft gates
match their previous receipts; EPS/ATX retain their paired-interface holds.
The previously withheld eight-refusal checkpoint is correctly rejected against
its original plan. PCIe3's 48 joint proposals become five plan-independent
proposals; one also clears the courtyard screen. **43 dependent proposals no
longer consume expensive route trials.** This is screening, not routing gain.
The historical PCIe2 board hash, complete regression and all probe outputs
match. No board is promoted and no unchanged view is republished as new.

## Completed production transaction and independent review (21:17Z)

`build/frozen-priority-production-probe-20260916/` ran the production priority
adapter only for families with newly applicable, courtyard/plan-screened
proposals (PCIe3 in this cohort). One round, 16 trials, four probe/finalist
workers, 600-second operation budget and 900-second job deadline. It starts
from `build/priority-coopt-next-inputs-20260916.json`, not the unapproved
checkpoint. Original plan geometry, saved copper, pairs, and independent
physical/exact-power checks were required for any changed result.

The transaction completed in **329.747 s**, with one accepted compound move:
**10 -> 8 priority refusals (20% fewer)**. The sense-amplifier/bypass group and
its detector/bypass follower group moved generically; no power terminal moved.
The entire proposal menu contained 1,949 moves. The new domain removed 693
power-dependent moves before the finite quota, in **8.229 s**. Sixteen moves
were attempted, twelve passed the local legality screen, four received coupled
route probes, and one reached complete exact-finalist evaluation. The craft
co-repair passed without breaking the original frozen plan.

Independent loaded-native checks pass for physical placement, exact power,
original-plan independence, saved copper and qualified pairs. Pours, corridors,
vias, frozen nets and exclusion pins are unchanged; only the placement snapshot
was synchronized. A fresh **saved-PCB** priority measurement independently
reproduces eight refusals, and current manifest/hierarchy/electrical intake
passes. These are not merely the disposable finalist's reported numbers.
Receipts: `report.json`, `pcie-8pin-3port/independent.json`,
`pcie-8pin-3port/independent-priority.json`, and `independently-reviewed.json`
under that production-probe directory.

The board is retained as an authenticated **unadmitted priority placement
checkpoint**, SHA256
`58c66a712f5a54e211a05f3ebb2f673913fe2507b2226dced593543f8e9fa4db`.
It is not routed, not routing-admitted and not fabrication-ready. A separate
continuation manifest, **`build/frozen-priority-next-inputs-20260916.json`**,
advances only PCIe3 to this verified checkpoint; the other five rows are
unchanged. The old source PCBs and input plan were not rewritten. Automatic
promotion/release and unchanged-wave restart remain disabled.

The broader regressions pass **327 tests** in 62.21 s, in
`build/frozen-priority-regression-tests-v2-20260916.log` (**495 passing tests**
across the two nonoverlapping file sets). The first broad invocation failed
because the scratch pytest launcher lacked a `__main__` guard and recursively
ran pytest inside spawn workers. The launcher was corrected and the entire
broader set rerun; no production-code workaround was made. Generic-core audit
passes, with the pre-existing 23 physical / 380 runtime legacy findings still
open. This slice does not certify the whole legacy pipeline as generic.

Body-free top/bottom views were inspected and published to the existing
dashboard as a blocked, non-routed placement review:
[verified review](http://localhost:8090/?id=20260916-frozen-plan-priority-pcie-8pin-3port-58c66a712f5a).
The Windows mirror is
`C:/Users/Admin/Documents/CEC-Board-Reviews/frozen-priority-20260916/pcie-8pin-3port/`.
The catalog contains the exact ID and its rendered panel returns HTTP 200 from
Windows. The in-app open request was queued, not proof of a visible tab. No
older image was substituted. No campaign/probe/test workers remain running.

The separate full-stage power-reconstruction/finalization budget gap remains
next work. Continue from the new authenticated placement checkpoint, not the
earlier power-replanned eight-refusal board; never convert an operation budget
stop into no-path. PCIe2 stays 0 DRC / nine opens, Hub has three craft blockers,
12VHPWR one USB-priority refusal, and EPS/ATX retain coupled-interface holds.
