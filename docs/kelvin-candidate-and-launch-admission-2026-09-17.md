# Kelvin candidate and launch admission — 2026-09-17

## Root cause, including a rejected intermediate result

The raw diagonals traced to `synthesize_kelvin_taps`' unlocked fallback.
Its direct branch accepted arbitrary headings, omitted the separate partner
sense-pad guard, and exempted *all* sense nets from native copper clearance.
The bent and Vbus branches also had different guard sets. Consequently a
late whole-board rejection was being generated deliberately by an earlier rung.

A first common-guard trial removed the two raw diagonals and generated four
orthogonal replacement segments. That **was not enough**: examining their exact
coordinates showed that the first leg ran backwards through the source force
pad. Merely beginning at an inner-edge coordinate does not prove the conductor
actually leaves the inner edge. The intermediate 96-item prefix in
`build/kelvin-candidate-suite-20260917` is retained as rejected diagnostic evidence;
it is not a continuation input or winner. Do not mistake its `geometry_ok` for
correct Kelvin contact topology.

## Generic production repair

- One `_tap_candidate_clear` predicate now covers canonical, direct, bounded
  fallback and Vbus bridge emission. All use the existing final 0/45/90 heading
  tolerance, native foreign-copper checks, pending-tap checks and future-power
  reservations. Only the actual own net is exempt, including for pre-existing
  partner sense tracks, vias, pads and protected pours.
- Sense taps additionally require their first leg along the inner-edge normal,
  positively inward by the existing 0.3 mm minimum. Ownership no longer waives
  this obligation. Voltage-pad bridges are not shunt launches, but still receive
  every geometric and copper guard.
- Refusal certificates retain heading and inward-launch witnesses, alongside
  pad/copper blockers and the target's signed inward deficit. Nothing is routed
  through a force pad simply to reduce the apparent open count.
- Locked covered-tap handling, pin-function mapping, width/clearance, nine-mm
  range policy, fabrication process, board geometry and load budgets are unchanged.

No board/refdes/coordinate recipe was added. No canonical board was edited.

## Evidence

Final native replay: `build/kelvin-launch-suite-20260917/report.json`.
The actual production priority compiler regenerated PCIe3 from the same canonical
zero-track placement; the other admitted families ran the actual Kelvin entry
point plus their current gates, while EPS/ATX retained the existing ECO hold.
No unchanged USB search waves were launched for Hub/VHP.

PCIe3 now reports:

- All three pair constructors retained; `pairs_ok=true` and generated
  `geometry_ok=true`, zero raw diagonals. Compiler time 13.018 s, not a benchmark.
- **Eleven Kelvin refusals**, not seven: seven prior range refusals plus four
  newly exposed wrong-direction tap paths. Only one of the five previously
  accepted tap paths remains constructible under correct launch admission.
- The four targets' signed inward coordinates are -7.426234, -7.040500,
  -3.187999 and -1.901457 mm. These are measured placement/path obligations,
  not permission to loosen the 0.3 mm launch or nine-mm reach requirements.
- 87 items in the private prefix, versus 94 previously. This reduction is
  rejected Kelvin copper, **not a claimed routing improvement**.

Independent saved-native proof is in
`build/kelvin-launch-postflight-20260917/report.json`: all prior USB/CAN pair
geometry remains; generated heading/graph checks pass; final pair physics still
fails the absent filled adjacent-GND planes. The prefix is not fab-ready and
has not been promoted.

PCIe2 still has five opens. Its Kelvin probe adds no copper and passes. Hub and
VHP Kelvin probes likewise add nothing and pass; their existing USB/placement
blockers remain. EPS/ATX still need the already-requested coupled-interface
choice. All six board/schematic identities and historical PCIe2 hash, regression
and probe parity match. Core generic audit passes; inherited full-pipeline audit
still fails with 23 physical / 380 runtime issues.

Regression coverage includes loaded front/back boards at four rotations, direct
partner pads/tracks/vias/pours, pending copper, reservations, valid 45-degree
paths, rejection before mutation and shared guard use by every emission branch.
`build/kelvin-launch-final-tests-20260917.log`: **897 tests and 16 subtests pass
in 24.84 s** (combined existing/new coverage, not 897 new tests).
The older Kelvin topology fixture's purported good board used raw diagonals and
already failed the scorer's existing heading check (that score path never calls
the changed synthesizer). Its good fixture now uses legal orthogonal copper;
the cut-vertex/bypass assertions remain unchanged. Do not hide that initial red
test as a runtime generator regression or waive the scorer's geometry rule.

## Next bounded slice

1. Extend independent loaded-board Kelvin origin checking to verify actual
   departure from the native pad, not just a near-pad endpoint on its inner half.
   The existing `_chk_kelvin_inner` uses a distance envelope; the rejected
   intermediate prefix is a useful adversarial fixture. Preserve legitimate
   authored contact, branching and back-face cases before production integration.
2. Feed all paired input obligations to the existing joint terminal-range/cell
   solver, including these signed inward deficits. Keep owners/decouplers rigid
   and actual high-current authority fixed. Do not relocate one named monitor
   or treat each radius independently.
3. Resume Hub/VHP only with genuinely new escape/return geometry. Do not rerun
   the unchanged positive/boundary portal domains. Keep Hub's 125-pose history.

The canonical manifest is still `build/additive-first-next-inputs-20260917.json`.
Neither intermediate prefix replaces it. No new board preview was promoted.
