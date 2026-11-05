# Sampled return seats and frozen terminal ownership — 2026-09-15

## Completed pass and measured advancement

`build/local-return-feedback-suite-20260915/suite.json` finished **11:43:09Z**.
Hub: 197.09 s; PCIe3: 169.96 s. Both stopped at placement. Source/hierarchy
and engine guards passed; former PIDs 153173/153174 and descendants are gone.

- PCIe3 retained two accepted generic craft rounds. The new boundary-exit
  proposal cleared the regulator/decoupler return obstruction, with exact
  frozen power synchronized. Two remaining sense-amplifier local returns
  stayed blocked. Saved board SHA:
  `13bce847b16a613231a1ed5d5dc0b612b5997bc184038727d48f4e07ca953099`.
- Hub correctly rolled back its two incompatible proposals and retained its
  exact input SHA `b7cc3990f31341ab71b73fcf0131a20831e38cd1ffaf64dff0ee23dd406d54da`.
  Its frozen placement snapshot now has **zero mismatches**, versus five in
  the previously retained rejected proposal. This is rollback correctness,
  not physical routing progress.
- No admitted route or fab output was created by this pass.

The final body-free pass gallery was visually inspected and its immutable
digest checked against `all-boards.png`:
`C:/Users/Admin/Documents/CEC-Board-Reviews/local-return-feedback-suite-20260915/all-boards-608fbee82d3fccd6.png`.
Both are explicitly BLOCKED placement panels. Windows port 8090 responded;
both IDs were verified in `/api/archive`:

- `pass-local-return-feedback-suite-20260915-pcie-8pin-3port-33fa4a5aef`
- `pass-local-return-feedback-suite-20260915-hub-standard-rev2-6c34a6ed27`

## Forensics: distinguish hypotheses from evidence

`build/cell-order-forensic-20260915/report.json` tried supply-first and
return-first construction independently on six failed cells across Hub and
PCIe3. Neither order solved any of those isolated cells. **No speculative
order-switching feature was added.** These are bounded counterfactuals, not
proof of global impossibility.

`build/return-seat-forensic-20260915/report.json` captured actual native via
seat refusals. A narrow package pad can legitimately reject the 0.35-mm POFV
land. The usable straight pin escape then reaches a normal 0.9-mm via seat
blocked by an actual power region. Previously only the pad-center rejection
and aggregate dogbone counters survived; placement never received the
off-pad power boundary that matters. No via dimensions or class widths were
reduced.

## Generic changes

1. Ground-return certificates now retain at most **16 unique closest-to-legal
   sampled seats**, their failed predicates and exact via blocker identities,
   plus truncation counts. Samples do not authorize copper: the native guards
   still reject them. Pure counts remain available.
2. `cec_local_return_feedback` consumes samples whose stubs were clear, not
   just pad-center evidence, to propose exact envelope exits. It preserves
   owner/decoupler groups and uses the prior fixed displacement/proposal
   limits. The global budget is distributed across independent owners, so a
   dense package cannot consume all proposals before another gets a turn.
3. Frozen topology distinguishes **declared owned terminals** from consumers
   merely sharing a net. A complete per-net `reserve_report`, aggregate
   `exclude_pins`, and native pin/net identities must agree. Missing or
   inconsistent evidence keeps the whole-net freeze. Declared terminals never
   move under this path.
4. A declared unowned consumer can synchronize a move only if every original
   and proposed pad has exact, layer-aware separation from frozen copper and
   bridge vias. This includes same-net physical taps and THT pads. A package
   body above copper on another layer is not falsely treated as an electrical
   contact. Existing full craft, courtyard, protected-copper and release gates
   still apply. The state update changes placement metadata only; failed
   updates remain transactional.

An initial deliberately conservative body-box proof rejected all native
trials. `build/consumer-contact-probe-20260915.json` proved why that was too
coarse: the body may span an insulated bus with no actual pad contact.
The final rule uses native effective pad shapes on their real copper layers,
not a relaxed net-name or bounding-box exemption. It still rejects the other
amplifier's tempting shortest move because four pads approach top-layer power.

## Native positive and negative replays

`build/return-seat-native-trial-v3-20260915/report.json` tries bounded generated
single-owner and compound proposals; there are **no manual component targets
in the generic engine**. Trial 1 passes the frozen-consumer proof and reduces
PCIe3 native decoupler failures **two to one**, with **zero foreign tracks and
zero foreign vias**. The other seven trials fail the unchanged physical
guards. The surviving failure is the other amplifier's local return.

This is an isolated diagnostic, **not full pipeline promotion or DRC/fab
signoff**. Its board is not used as a continuation input. The next full
pipeline must select/retain the generated move itself.

`build/return-seat-suite-replay-20260915/report.json` covers the hash-bound
six-family plan: Hub gets new sampled-seat proposals; PCIe3 gets eight;
PCIe2 local PI still passes. Hub's terminal declaration is incomplete under
the stronger ownership proof, so it receives no consumer exemption. PCIe2 and
PCIe3 declarations validate. VHP retains its separate local-access/USB
obligations; EPS stays mechanically held with unmoved-placement obligations;
ATX fails closed on unavailable required power authority. All source inputs
are unchanged. Counts of timed local supply failures can differ from the
previous cohort; do not report these as DRC or open-net improvements.

Final validation:

- `build/return-seat-final-tests-v3-20260915.log`: **450 passed, 96.20 s**.
  Includes loaded-native pad/contact, through-layer, ownership and rollback
  tests plus full-pipeline, craft, generalization and shared routing tests.
- `build/return-seat-control-comparison-20260915.json`: protected PCIe2 SHA,
  full regression object and all probes are exactly unchanged after final
  engine edits. Its prior stricter release failures remain, not waived.
- `build/return-seat-generality-20260915.json`: **68 core modules / zero core
  violations**; **380 broader runtime findings** still remain.

Earlier native/synthetic intermediate results are retained for diagnosis;
do not add overlapping test counts or describe rejected trials as winners.

## Active follow-up and next observation

Dispatched **12:20:44Z**:
`build/return-seat-feedback-suite-20260915/suite.json`.
Hub PID **186583**, PCIe3 PID **186582**, parent session **43233**.
Harness: `tmp/return_seat_followup_20260915.py`.
Input plan: `build/return-seat-inputs-20260915.json` with journal-verified
completed placement lineage, including PCIe3's retained 13bce result.

Two workers per board, 12 trials/two craft rounds, eight routing passes,
1800-s board deadline, 1200-s priority allowance, 480-s pair allowance,
2100-s parent group bound and a 16-GiB free floor; 68 GiB free at launch.
Do not edit shared engines or duplicate jobs while any descendant lives.
Completed-stage/pass review publication remains enabled. Check whether the
full solver actually retains the positive native move; do not seed the
diagnostic or repeat an unchanged exhausted attempt. EPS/ATX still need a
coupled qualified interface ECO before routing; retain the VHP and PCIe2
incumbents while their different blocker classes are addressed.

### First live observation — 12:23Z

PCIe3 stopped after 63.83 s (placement failure at 52.263 s). Its cached craft
key expected one remaining local failure; full certification produced two:
`placement craft diagnostic-mode admission drift` at
`cec_synth_pipeline._certify_craft_incumbent`. The consistency gate correctly
withheld promotion; source/hierarchy/engine signatures remain unchanged.
Hub PID 186583 is still running round two; no shared engine edits are allowed
yet. The next task is fast/full oracle parity, including persistence of the
failed native board and paired certificates (the current temporary-directory
exception path removes that board). Do not assume timing, weakened clearance,
or a physical regression without this evidence. The known local-supply wall
deadline is one testable hypothesis, not the established cause.

### Completed and superseded

Both jobs finished at 12:24:02Z; no descendants remain. The next bounded
reproduction captured the actual cutoff failure with exact inputs retained.
See `placement-certificate-parity-2026-09-15.md` for the cause, generalized
evidence/work-budget repair and current validation. The "Active follow-up"
section above is historical launch evidence, not an instruction to duplicate it.
