# Bounded coupled local-cell search

## Completed cohort: no PCIe2 connectivity improvement

`build/frozen-via-followup-suite-20260915/suite.json` finished **16:09:13Z**.
All descendants exited and source/hierarchy/engine guards passed before edits.
Independent selected seed 0: **0 DRC / 10 opens**, 742 tracks, 386 vias,
1631.710 mm, SHA `c6debcd28b2e7f743bc0e77fcb2a63cb18e5d34d0bc9b603dd530336930226f9`.

The frozen-via replay defect is repaired and the backend now runs, but this
result adds 16 tracks, four vias and **58.859 mm** without closing an open.
It is **not** promoted over the retained, explicit 905f PCIe2 input. Both
remain withheld. Do not restart identical PCIe2 waves because a new archive
entry exists. A future generic continuation selector should compare against
the admitted incumbent as well as against the current wave's other seeds.

Verified review: dashboard ID
`pass-frozen-via-followup-suite-20260915-pcie-8pin-2port-44096ebd13`.
The Windows gallery is
`C:/Users/Admin/Documents/CEC-Board-Reviews/frozen-via-followup-suite-20260915/all-boards-e856670738c2485c.png`.
Image SHA e856670738c2485c618b38a6f2a723acf9cbd38f1379e6255553274b20add487;
visually inspected, no-body top view, labelled BLOCKED / NOT FAB SIGNOFF.
The dashboard archive API resolves that exact immutable ID.

## Implemented generic repair

The evidence in `local-cell-ordering-investigation-2026-09-15.md` is now
implemented in `cec_decoupler_cell` and `cec_fab_profile`:

- Preferred process geometry and the existing supply-first solution remain
  first choice. Only a failed complete cell searches the next alternative.
- Search at most two explicit process geometries and two supply/return
  orders. The second geometry is the already-declared filled/capped process
  floor, not an invented fabrication limit. Unknown profiles receive no
  POFV exception. Ordinary through-via geometry and netclasses are unchanged.
- Native pad containment, drill/edge/foreign-copper checks, frozen power
  reservations, complete local-path length and the existing final DRC/current/
  fabrication gates remain mandatory. A local construction is not release.
- The whole cell is transactional. Failed attempts remove only their own
  copper and groups, rebuild connectivity, and verify inherited copper IDs
  and group membership. Native exceptions also roll back. Collective
  feasibility audit uses the same constructor and removes all trial groups.
- Blocker records distinguish tentative cell copper from inherited locked
  authority, including UUIDs retired by an inner ground-pair retry. The
  former requests joint cell replanning, not movement of a fixed upstream bus.
- Search receipts retain attempted geometry/order, failures and rollback
  counts. Exhausting this bounded set is not proof that no route exists.

## Validation

- Broad suite: `build/coupled-cell-final-tests-20260915.log`, **957 passed**,
  53 subtests, three existing skips, 149.47 s.
- Follow-up integration after nested-retry provenance hardening:
  `build/coupled-cell-integration-tests-20260915.log`, **382 passed**.
- Focused native/ownership tests:
  `build/coupled-cell-native-tests-20260915.log`, **31 passed**. Native loaded
  rollback is byte-exact; inherited groups remain intact. Renamed/translated
  pad fixtures accept fully-contained declared minima, reject overhang and
  unknown process. Scheduling fixtures cover both orders, failed geometry,
  bounded exhaustion, nested provenance and exception rollback.
- Protected historical PCIe2:
  `build/coupled-cell-v2-control-comparison-20260915.json` proves exact board
  hash, whole-board regression and all probes unchanged. Only generalization
  evidence differs. The old release holds are not waived.
- Initial native suite replay:
  `build/coupled-cell-suite-replay-20260915/report.json`; final-code replay:
  `build/coupled-cell-suite-replay-v2-20260915/report.json`. All six canonical
  family sources/hierarchies remain unchanged. EPS/ATX refuse the same
  unadmitted interface ECO; four admitted native audit/rollback paths are
  exercised. No diagnostic copy is used as a production seed.

PCIe3's last local-craft failure clears. The actual pre-route cell transaction
passes with **0 DRC, 254 -> 175 unconnected**, no rollback or deferred DRC.
This is local-cell construction before the whole-board router, not a completed
route. PCIe2 remains locally clean; Hub retains five local/proximity failures;
12VHPWR retains C7/U1.3 local access and its separate critical-pair escape hold.
No component is moved and no power budget is changed by this repair.

## Canonical continuation

`build/coupled-cell-followup-suite-20260915/suite.json` **finished 16:43:45Z**,
after 259.384 s, with all descendants gone and source/hierarchy/engine guards
passed. PCIe3's canonical placement is byte-identical **400ffdd8635e**; craft
and local-cell gates now pass. Main routing **did not start** because important
route admission correctly refused 12 issues. Do not repeat this unchanged
wave or use the diagnostic pre-route copy as a seed.

The verified no-body placement review is dashboard ID
`pass-coupled-cell-followup-suite-20260915-pcie-8pin-3port-1a418542f7`.
Windows image:
`C:/Users/Admin/Documents/CEC-Board-Reviews/coupled-cell-followup-suite-20260915/pcie-8pin-3port/render.png`.
Image SHA 9c2d3e518e2971b279d13a512f2ea75bba0c89483ee822318df28de55b926188;
visually inspected, native board SHA matches the journal, archive API resolves
the exact ID. It is intentionally the **same placement**, now carrying updated
admission evidence; not a new routed or fab-qualified board.

Next blockers are in `02-placement/operation-priority-measure-q98df_b9/report.json`:
nine recognized Kelvin inputs lie **11.152–20.527 mm** from their shunt pad,
against the existing **9 mm** reach gate; CAN_H's candidate detour is 2.071x
against 2.0x; another pair lacks a clear exact 0.2R corridor; USB_D_N has a
covered backtrack. The bounded priority and power-replan stages accepted no
move (`critical_probe_budget_inconclusive`). No limit was waived.

Read-only source inspection finds a causal search gap:
`placement_kelvin_range_repair_max_mm` defaults to 6 mm, and the measured-range
proposal branch **skips the entire refusal** when `required_closer_mm > 6`.
Thus some witnesses cannot generate a targeted correction at all. A next
generic slice should audit the 9 mm reach authority and support bounded,
frozen-power-aware whole-cell relocation or monotonic intermediate progress,
with severity scoring and explicit inconclusive search evidence. It should
not simply relax the Kelvin gate or move one named IC by hand. The current
source describes the reach as the tap synthesizer's limit (owner-lever pass
2026-07-08); do not present it as a datasheet/industry limit without authority.

**Historical 16:41Z observation:** cohort dispatched **16:39:06Z**, PCIe3 PID **357064**,
parent session **85297**. Source intake passed; placement has cleared its
local-cell checks and is executing bounded `priority-measure` (worker 358953)
before declaring placement admission. The board has **not** entered the main
router yet. 68 GiB free; keep engines fixed while this process tree is live.

## Further read-only findings, not implemented here

The latest PCIe2 and retained input have identical route-geometry evidence:
one covered VBUS backtrack and one inherited locked GND segment at 112.5
degrees. There is no route-geometry improvement offsetting the added length.
The generic ground dogbone generator still samples 22.5-degree ray offsets;
that producer policy should be reconciled with the declared 0/45/90 trace
policy, not patched at one pad. Existing locked geometry still requires a
qualified producer-owned replacement transaction. Do not widen clearances or
waive the geometry gate to admit it. This is separate from the repaired
coupled-cell ordering, and shared-code changes must wait for the live cohort.
