# Bounded priority cooptimization and durable incumbents — September 16

## Failure, not board closure

The full canonical PCIe3 pass `build/post-authority-return-pass-20260916`
finished at **16:15:10Z**, after **1178.481 s**, with exit 1. Its last isolated
power-replan operation was limited to the remaining 146.071 s rather than its
requested 600 s, and exhausted that budget during power materialization.
All canonical source/hierarchy and shared engine signatures remained unchanged.

The preceding two complete cooptimization rounds had accepted checked placement
steps. They still had ten priority refusals; the second improved the ordered
reservation-crossing objective from 49 to 46 while worsening the lower-ranked
forecast-overflow term from 191536 to 193309. These were **not routed boards**.

The outer loop started another expensive round without accounting for complete
round cost or finalization. The inner timeout then escaped before best-state
selection/reporting, and the accepted snapshots existed only in temporary
storage. This was a coordinator/work-retention defect, not evidence that the
new local-return solver failed or that a routing limit should be relaxed.

The dashboard therefore correctly shows only the older, source-identical seed
checkpoint (`400ffdd...`), labeled BUDGET EXHAUSTED / NOT FAB SIGNOFF. Its
checkpoint hash is verified; the failed full-stage journal does **not** verify
it as a completed stage. Top view has been visually checked; Windows HTTP 200:
[failed full-pass review](http://localhost:8090/?id=pass-post-authority-return-pass-20260916-pcie-8pin-3port-fcb7acd60f).
No scratch placement has been promoted to conceal the failure.

## Shared repair

The repair has no board, refdes or coordinate selector:

- The outer loop uses the existing deadline admission policy and the measured
  duration of its **whole preceding round**, including authority reconstruction
  and native rechecks. `placement_coopt_finish_reserve_s` defaults to 120 s;
  the existing 1.1 cost margin is retained. An unaffordable round is not started.
- Only the explicit supervised `operation_budget_exhausted` failure becomes a
  bounded stop followed by selected-snapshot restoration. Crashes, changed
  inputs and other integrity exceptions still fail closed.
- A strictly better, physically and exact-authority measured priority incumbent
  is stored through the existing bounded two-slot atomic checkpoint mechanism.
  It is explicitly unadmitted and cannot authorize routing or fabrication.
- Round admission checks, timeout evidence and checkpoint identities are retained
  in the completion history. No electrical, mechanical, objective or fabrication
  acceptance limit was loosened.

## Verification

**168 focused tests passed** in 102.82 s. The tests cover ordinary/power budget
exhaustion versus crash, integrity propagation, full-round reserve admission,
atomic-pointer interruption, phase regression rejection and truthful dashboard
checkpoint provenance. Receipt: `build/priority-coopt-durability-tests-20260916.log`.

Native four-family replay **passed** in
`build/priority-coopt-durability-replay-v2-20260916`. The real production
checkpoints survived a later pointer-write interruption; fresh native gates
and rule hashes before/after checkpointing match. Protected copper and qualified
pairs are unchanged, historical PCIe2 board/regression/probes match, and all six
canonical source/hierarchy hashes and the frozen engine signature remain exact.
Independent receipt: `build/priority-coopt-durability-qualified-20260916.json`.
Legacy audit debt remains 23 physical / 380 runtime findings; the complete
pipeline is not generically qualified or released for fabrication.
EPS/ATX retain their coupled-interface hold, not a fabricated routing result.

The first replay completed its native checks but its comparator incorrectly
included relocated absolute report paths. Inspection also found intentional
project-rule restoration during normal staging (not checkpointing), including
the Hub's missing current netclasses. V2 therefore separately records that
source-to-staged rule change and compares the checkpoint with its exact staged
baseline, preserving every rule hash. Source physical outcomes are separately
required to remain identical. The initial failed receipts remain available;
they are not counted as successful qualification.

No canonical candidate changes are authorized by these persistence tests.
Only a newly completed and independently verified full pass may advance the
continuation cohort. Retain `build/bound-return-next-inputs-20260916.json` until
then. Do not repeat unchanged exhausted waves on the other families.

## Successor full pass

**Completed and independently verified at the 17:12Z review.** The full job
finished at **16:57:37Z**, in **604.387 s**. The placement stage is complete
but blocked, not failed: its first measured improvement was durably retained
and the unaffordable second complete round was declined. Required 625.946 s
versus 600.852 s remaining, including the unchanged finish reserve.

The selected PCB is `21109c06887de87d582124f47a6239ace968fee280010c3d81a972e9ab54f727`:
83 footprints, zero tracks/vias, one zone. Independent fresh physical and exact
power checks pass; protected copper and qualified pairs are retained. A fresh
priority solve exactly reproduces the declared complete objective and its ten
refusals. Source/hierarchy, journal/output and engine identities all verify.
Receipt: `build/priority-coopt-durability-pass-qualified-20260916.json`.
Both body-free views are inspected and the immutable dashboard is HTTP 200:
[verified blocked placement](http://localhost:8090/?id=pass-priority-coopt-durability-pass-20260916-pcie-8pin-3port-acdebc87d1).

Only this independently verified full-stage lineage advances into
`build/priority-coopt-next-inputs-20260916.json`; all other rows remain identical.
There is no routing or release admission. The ordered congestion improvement
and lower-ranked overuse regression remain as documented for the underlying
recovery. Do not restart an unchanged wave to claim another layout result.

Historical launch record:

After qualification, one changed-engine full canonical pass started at
**16:47:21Z** in `build/priority-coopt-durability-pass-20260916`, launcher
`tmp/priority_coopt_durability_pass_20260916.py`. Worker PID 1037680 and shell
session 13448 identify this launch; use journal/process checks for live state.
Four workers, 16 trials, 600-second priority / 1200-second job budgets and the
16-GiB floor are unchanged. Approximately 65 GiB is free.

Do not modify shared scripts while this pass runs. On completion, verify the
actual selected board/certificate and source/engine identities, reload native
physical and priority evidence, and inspect both immutable body-free views.
An incomplete-stage priority checkpoint is useful retained work, **not** a
journal-verified stage or routing admission. Do not promote it under that label.
