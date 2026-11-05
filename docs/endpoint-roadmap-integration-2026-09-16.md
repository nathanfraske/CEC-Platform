# Complete-local-pair roadmap integration

September 16, 2026, 14:08 UTC. Production implementation and replay qualified;
full changed-domain pass is running. No new board has been promoted.

Follow-up (15:03Z): the input-mutation failure described below is now reproduced
and fixed. Only the supervisor's stack-log output had changed. See
[placement identity output boundary](placement-identity-output-boundary-2026-09-16.md)
for 290 passing tests, fresh cross-family native replay and the real supervised
trial. The repaired trial reaches a genuine local ground-return refusal;
no board has been promoted. Earlier sections retain their as-observed history.

## Completion review (September 16, 14:29Z onward)

The full pass finished at **14:13:43Z** in **345.628 seconds**. All workers are
finished. Its placement-stage output is journal/hash verified and exactly
identical to the canonical input (SHA `400ffdd8635e82b35773cf8377729d8f559628ea5b668445fad05be5384266c8`).
Fresh native inspection confirms **83 footprints, zero tracks, zero vias and
one zone**. Fresh non-routing physical placement gates pass. This is still a
**blocked placement**, not a routed board or an admitted fabrication candidate.
The new solver's 11 -> 10 priority improvement reproduces in the full pass,
but no placement move was accepted and no canonical copper was added.

Independent receipt: `build/endpoint-roadmap-pass-qualified-20260916.json`;
verifier `tmp/verify_endpoint_roadmap_pass_20260916.py`. Source/engine identities
and all six source/hierarchy signatures are unchanged. Top and bottom body-free
previews were visually inspected; both correctly label the artifact PLACEMENT,
BLOCKED, NOT FAB SIGNOFF. Windows HTTP 200 is verified for the immutable review:
`http://localhost:8090/?id=pass-endpoint-roadmap-pass-20260916-pcie-8pin-3port-5725b7ee9f`.
Desktop copies are in the previously declared review directory. Do not present
these unchanged images as a newly routed result.

The ten remaining priority refusals have distinct causes:

- **Nine Kelvin placement-range violations**, not failed maze-route searches.
  Declared maximum is 9 mm; measured source-to-target distances range from
  11.151655 to 20.526898 mm. They cover the three shunts and their monitor/
  comparator inputs. Preserve the existing range policy; more routing effort
  cannot make physically separated pins closer.
- **One CAN_J1 coupled-corridor refusal**. The new complete-local-pair fallback
  does not falsely treat this unfinished portal topology as a complete pair.

Repair attempted 16 proposals: 12 geometrically legal, four exact pair probes
dispatched, and three deferred by the original fixed-share full-probe budget.
No complete finalist was evaluated. It stopped explicitly as
`critical_probe_budget_inconclusive`, not geometric impossibility. Two power-
replan candidates were tested and neither admitted:

1. A bead-shift proposal passed its first physical screen but failed after
   authority rebuilding: `U3.5[+3V3] local-cell-access`, bounded GND-return
   search exhausted. This is the same class of coupled power/return dependency
   relevant to Hub; an unrelated movement must not be admitted by sacrificing
   the regenerated local cell.
2. A connector/support-group shift failed because craft evaluation reported
   **`placement inputs changed during evaluation`**. This is an integrity/
   evaluation failure, not proof of a physical overlap. The coordinator's
   reduced `craft_failure_evidence` retained the error string but discarded
   its `input_identity` / `input_identity_after` certificates. The concrete
   mutated file/config/environment role therefore cannot be established from
   that retained trial report alone. Do not guess its cause or bypass the guard.

Evidence for both is `02-placement/operation-priority-power-replan-o62s9plc/report.json`
under the completed pass (`power_replan.trials`). Use bounded field projections;
the nested reports and one-line worker JSON are large.

Next useful generic slice: preserve compact before/after identity deltas through
all failure-report boundaries, then reproduce the rejected support-group trial
on a disposable authority-bound copy to identify the actual mutation. In
parallel with admissible board work, investigate coordinated local-power/return
reconstruction and Kelvin monitor-group placement, not another identical route
wave or a relaxed 9 mm limit. No unchanged full pass was restarted. Keep the
canonical bound-return cohort; all other boards retain their previous statuses.

## Generic implementation

`scripts/cec_endpoint_roadmap.py` supplies the bounded exact-guard proposal
domain tested in the preceding prototype. The production precision router now
uses it only after its existing template choice fails a complete local-pair
contract, or when that template domain supplies no choice. Successful old fast
paths remain unchanged.

Whole-pair policy is explicitly scoped: native pads must all map to the two
actual endpoints for each member, both ends must exist, and neither member may
already have routed copper. Virtual portals, partial flow/tree legs and existing
routed pairs do not acquire a fictional complete-pair obligation. Those paths
keep their existing solvers and final qualification.

Eight-direction search keeps exact endpoints, uses exact octilinear end hooks,
honors native foreign/partner guards and search deadlines, and rechecks the
whole path after chamfering and same-direction collinear simplification. An
opposite-member proximity cost proposes better pairing but cannot waive any
guard. Search bounds are explicit validated `Limits` values. Edge caches and
duplicate-query suppression are invocation-local, never reused across native
geometry changes.

The existing complete objective still ranks the expanded domain. An optional
pair-admission predicate in `_ranked_joint_escape` prevents its first mutually
clear but electrically inadequate choice from hiding other legal candidates.
The original selection is retained if no qualified alternative is found.
All final physical ownership, saved-copper geometry, skew, detour, coupling,
return-path and fabrication checks remain authoritative. No policy was relaxed.

## Validation

- **449 tests and two subtests pass** in
  `build/endpoint-roadmap-regressions-20260916.log`, including endpoint identity,
  rotation/reflection/translation, invalid numeric domains, trapping, deadlines,
  native loaded foreign copper, complete/partial physical scope, incumbent
  retention, ranked contract rejection and the existing pair/portal/tree/flow
  and native cleanup regressions. One old lightweight fast-path fixture needed
  empty `GetTracks`/`GetFootprints` methods; production does not mask missing
  native APIs. Only the existing KiCad SWIG deprecation warning remains.
- Four current-family native physical A/B reports are identical. EPS/ATX remain
  interface-held. All six source and hierarchy signatures are unchanged.
- The historical PCIe2 control retains exact board hash, regression and probe
  parity. This is non-regression, not a claim that the current PCIe2's nine opens
  have closed.
- New module static findings: **zero**; it is in the generic audit inventory.
  Existing broader debt remains **23 physical / 380 runtime** findings. This
  slice does not justify calling the entire pipeline fully generic.

Consolidated receipt: `build/endpoint-roadmap-qualified-20260916.json`.
Replay: `build/endpoint-roadmap-replay-v2-20260916/report.json`.
Verifier: `tmp/verify_endpoint_roadmap_20260916.py`.

The first replay harness compared current in-memory physical reports directly
against historical JSON and stopped at equality assertions: generated UUIDs,
elapsed values, and tuple/list serialization differed. No source was modified.
The corrected v2 stores failure evidence and compares same-engine native A/B
reports, with historical differences recorded separately. Its full source,
engine and historical-control checks completed successfully. Neither failed
first-harness completion nor old serialized-report equality is claimed.

## Measured routing effect, with scope kept explicit

Production PCIe3 native priority replay improves **11 -> 10** refused important
routes (93.700 s). CAN_J1 and nine Kelvin routes remain refused; the local CAN
pair passes. Exactly one physical complete-pair roadmap domain was invoked.
Concurrent 12VHPWR remains **1 -> 1** (76.912 s), with zero roadmap calls because
its current failure is not this complete-local-pair case.

The production objective and collinear simplification select a different N
path from the prototype: P **4.276701 mm**, N **2.980563 mm**, maximum member
detour **1.113318x**. Its sampled coupling is **26.3%**, not the prototype's
64.5%. It passes the **existing** geometry-bound split-terminal local-fanout
contract: 3.151253 mm uncoupled versus 6.609231 mm allowed. No blanket percentage
exception or changed limit was introduced; final native qualification remains
in place. Do not quote the prototype's coupling percentage for this selection.

## Active full pass and next review

`build/endpoint-roadmap-pass-20260916` started at **14:07:55Z**, running one
changed-domain PCIe3 full pass from the exact canonical hash-bound input.
Launcher: `tmp/endpoint_roadmap_pass_20260916.py`. Four workers, 16 trials,
eight routing passes if admitted, 600-second priority repair / 1,200-second
job limit, and a 16-GiB disk floor. Current source is unchanged and all prior
six-board controls were replayed concurrently. Other exhausted families were
not needlessly restarted; their blockers and mechanical authority are unchanged.

Do not duplicate this campaign or edit shared scripts during its worker run.
On completion, read its journal, verify selected output and source/engine hashes,
run independent gates appropriate to the actual completed stage, and visually
inspect body-free previews before reporting/publishing any new candidate.
The suite will copy verified reviews into
`C:/Users/Admin/Documents/CEC-Board-Reviews/endpoint-roadmap-pass-20260916` and
the dashboard. A completed pass or preview is not automatically a fabrication
candidate. Keep `build/bound-return-next-inputs-20260916.json` until independent
evidence qualifies a replacement continuation.
