# Qualified local-to-global escape handoff — 2026-09-15

## Root cause and bounded generic repair

The completed Hub's remaining planning rejection was the PSU_5V_KVM MST
edge from U7 pin 2 to C26 pin 1. Its four cardinal neighbors are blocked at
0.5 mm grid resolution. Independent native local-cell construction already
proved U7 pin 2 -> C28 pin 1 (1.562 mm path, 0.2 mm width), but that proof
only discharged the local MST edge. Global planning never composed it with
a route continuing from C28 toward C26. Native connectivity correctly said
these pads are not yet joined on the saved board; this was not an existing-
copper waiver or an actual open-count improvement.

`cec_qualified_escape.propose` now rechecks native UUID/ref/pad/position/layer
identity and either physical connectivity or a fresh local supply proof.
Per-net identity graphs expose alternative real pad terminals. The limit is
16 failed connections and eight portal nodes per endpoint, one deterministic
proposal per connection. Ambiguous capacitor rail lands, unsupported local
via-bridge proofs, stale identities and unproved same-net links are refused.

The proposal cannot discharge an obligation. Preflight must renegotiate the
**entire workload** once with the original obstacles, allowed layers, priority
ordering and capacity model. It adopts the result only when failed obligations
strictly decrease and every previously reachable obligation survives. The
new workload supplies the congestion metrics and heatmap, so the extra route
is not invisible demand. Original logical endpoints and exact escape witnesses
remain in `qualified_escape_retry` evidence. Detailed copper generation,
electrical DRC, connectivity and all fabrication gates are unchanged.

An alternate real pad uses the global router's existing terminal-cell rule:
its own coarse cell can contain a neighboring land/pour, but no neighboring
cell or other-layer column is cleared. Exact native local qualification
precedes that substitution. A real wall still blocks the retry. The input
blocked-cell masks are never edited.

## Evidence

- `build/qualified-escape-v2-broad-tests-20260915.log`: **230 tests pass** in
  82.54 s, covering
  the adapter, preflight, existing copper, full pipeline, local cells,
  generalization and coordinated routing. Targeted suite: 67 tests pass;
  22 are new adapter tests.
- `build/qualified-escape-hub-bound-native-v2-20260915.json`: actual retained
  Hub SHA `a2861bb5d1140e0c7785b844235da4395d1085eae3921e1b4043f7173ce89c8c`,
  frozen power authority bound, baseline critical global failures **1**, new
  result **0**. One original local failure remains independently qualified;
  no remote obligation is simply waived. Added full negotiation took 24.600 s;
  complete new global analysis 50.666 s. Board and engine unchanged.
- This isolated diagnostic inherits pair ownership only to hold that axis
  constant; it does **not** newly qualify pairs or whole-board release. A
  canonical pipeline follow-up must repeat the normal gates.
- The first unbound diagnostic omitted the frozen-pour environment and is
  explicitly **not** improvement evidence. The first correctly bound version
  reproduced the failure but over-rejected coarse blocked terminal cells.
  Only the final bound A/B above demonstrates the repair.
- `build/qualified-escape-suite-native-v2-20260915.json`: native adapter replay
  on current inputs from all six families. Proposed substitutions: VHP 3,
  EPS 1, Hub 2, PCIe2 4, PCIe3 1. These are adapter proposals, not routed-board
  admissions. ATX fails closed on missing sibling pour-first authority state;
  it is not counted as a passing case. All source families remained unchanged.
- `build/qualified-escape-control-comparison-20260915.json`: protected historical
  PCIe2 SHA, full board regression and every probe exactly match
  `build/pair-pad-control-20260915.json`. Its pre-existing stricter release
  failures remain; this does not reclassify it as currently fab-qualified.

No board name, reference designator or board coordinate selects behavior in
the generic adapter. It is registered in the core anti-overfit audit. Legacy
whole-runtime generalization debt remains separate from this core result:
66 core modules, zero core violations; 380 whole-runtime findings remain.

## Continuation boundaries

The two preceding canonical board passes completed at 09:27:02Z. Hub accepted
its power-terminal repair and reached zero pair refusals; only the global
edge above blocked its saved placement. VHP retained CAN progress and reduced
priority pair refusals from two to one (USB). Both remain BLOCKED / NOT FAB
SIGNOFF, with changed, journal-hash-verified placement previews published.

The next cohort resumes those exact completed outputs, never a diagnostic or
an old root. Hub tests the actual local/global handoff through routing stages.
VHP resumes its newly retained prefix with a fresh bounded allowance for the
remaining USB dependency. PCIe3 needs joint Kelvin/current-corridor work;
EPS and ATX still need a qualified coupled mating solution. Do not spin those
unchanged failures or claim all boards are routing. Keep shared engine files
fixed while the new cohort or any native descendants run.

Canonical follow-up **started 10:05:19Z**:
`build/qualified-escape-suite-20260915/suite.json`, VHP PID 95993 / Hub PID
95994. Input plan: `build/qualified-escape-suite-inputs-20260915.json`.
Two workers per board, 1800-s individual board limits, 1200-s priority repair
allowance, explicit 480-s pair effort, 16-GiB free floor. Parent supervisor has
a 2100-s hard group bound. Both are in placement validation at dispatch; do
not call this a completed route. Completed stages and full passes use the
standard journal/hash-verified publisher and Windows review mirror.
