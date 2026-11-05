# Filtered sense lineage and native current-name coverage

## Implemented reusable topology proof

`cec_sense_topology` resolves declared current-input pins through typed,
two-terminal series resistors to an authoritative sense resistor. It keeps
every intermediate net and pin, excludes capacitors/connectors, and requires
one unambiguous pair of disjoint input paths. Search depth and work are bounded;
exhaustion is unproved, not an impossible-path verdict. Missing/mismatched
input pads remain explicit failures instead of disappearing from coverage.

The native adapter uses resistor library type and the shared existing device
pin contracts. Anchors come from existing HI/LO pair identity or components
explicitly named in complete current-flow authority. It does not recognize
shunts or filters by reference prefix, guess from resistance values, choose
the nearest component or invent electrical ratings. Arbitrarily named anchor
pairs are supported through the explicit API. Unsupported/custom component
typing and ambiguous topology stay unqualified.

The production `kelvin-sense-adjacent-shunt` checker now consumes this proof
for filtered inputs. The old filtered fallback simply selected the nearest
RS-prefixed footprint in board X, which could validate a different lane and
was not invariant under rotation. The corrected measurement uses the actual
connected shunt and its native pad-to-pad axis. It retains the existing **1 mm
filtered lateral-alignment limit**, not a newly invented engineering budget.
Direct-sense distance policy is unchanged. Filtered failures are checked before
the legacy direct-path early return, so a mixed board cannot hide a failed
filtered channel behind a passing direct one. Live input/series/anchor net
identities are rechecked before evaluating stored topology evidence.

This is placement identity/alignment evidence. It does **not** prove actual
Kelvin copper connectivity, create filtered routes, certify resistance/current,
replace thermal signoff or finish the filtered critical-terminal-order placer.
The latter still needs to consume complete filtered path segments, not a
straight fictitious shunt-to-IC net. No board geometry changed in this slice.

## Native suite results

- `build/filtered-sense-gate-replay-20260916/report.json`: all six current
  identities checked, four native workers, EPS/ATX correctly interface-held.
  All PCB and hierarchy signatures remain unchanged.
- 12VHPWR: **six of six** filtered INA240 inputs resolve to their actual shunts,
  through twelve actual series resistors. Each has the same 0.3 mm native
  lateral offset and passes the retained 1 mm criterion. Its former Boolean
  result also passed; the gain is proven identity and rotation correctness,
  not a new accepted placement or route.
- PCIe2: four direct input contracts resolve; adjacency verdict remains pass.
- PCIe3: six direct contracts resolve; its existing adjacency refusal remains.
- Hub: zero applicable input contracts; remains not applicable, not a new pass.
- `build/filtered-sense-authority-suite-20260916/report.json` contains the full
  resolved cells and native axis measurements. The preceding name-only probe
  (`build/filtered-sense-suite-20260916/report.json`) resolved only five VHP
  channels; the sixth force-input net has been renamed. Explicit existing
  current-path component authority resolves that topology without renaming
  nets or altering the approved fan arrangement.

## Tests and protected control

`build/filtered-sense-final-tests-20260916.log`: **434 tests and two subtests
passed**, 135.38 seconds. Includes 35 topology tests, loaded native front/back
fixtures, arbitrary/quarter rotations, save/reload, renamed reference/net
identities, old nearest-lane false-pass reproduction, stale electrical evidence,
ambiguous anchors and paths, search exhaustion, capacitor exclusion and existing
current-width/placement/full-pipeline regressions. Initial test-fixture failures
(LIB_ID constructor arguments and a two-nanometre rounded assertion boundary)
were corrected; no production physical tolerance was relaxed.

`build/filtered-sense-control-comparison-20260916.json` confirms the protected
historical PCIe2 PCB hash, full regression object and all four probes are
identical to the preceding control. Only generalization metadata differs
because the new module was added to the generic core audit; that audit passes.
The historical 0 DRC / 0 opens is unchanged, as are its broader release holds.

## Newly confirmed current-domain name gap — not yet repaired

Tracing the sixth VHP channel exposed a separate shared-intake defect.
`build/current-domain-name-screen-20260916.json` compares the configured current
contracts with native connectivity on all admitted families:

- The existing VHP contract names `/SENSEP6_HI` at **8.33 A**, with source `J3`
  and sink `RS6`. That name is absent from the current native board.
- Those declared authority references share exactly one actual net:
  **`/FAN_12V`**. This is the approved pre-shunt fan connection/name, not a new
  fan-load or regulator-load assumption made by this work.
- `board_current_domains` presently skips an absent literal net before using
  the endpoint authority: it emits **15 of 16** configured VHP domains and no
  `/FAN_12V` entry. The other three admitted families have no absent configured
  name in this screen. EPS/ATX remain held, not passed.

This proves a missing mapping in that shared resolver. It does **not** by
itself prove that every thermal path or width consumer omitted this current;
trace their actual call paths before making that wider claim. Do not change the
8.33 A contract, merge/rename nets, move the high-current copper, alter fan
loading, or claim thermal qualification as a workaround.

**Next slice:** resolve an absent configured name through complete declared
source/sink authority only when native connectivity proves one unique net.
Refuse ambiguity, missing references and conflicting contracts. Preserve named
candidate-bank semantics and original configured provenance. Audit all consumers
(routing/current dimensions and thermal source allocation) so a local resolver
fix cannot leave FEM using a different identity. Add renamed/ambiguous/collision
native tests and cross-board/control replay before any affected full wave.

## Run state

No full wave or replay/control worker remains running. No new board is promoted
or republished, and no release gate is waived. Keep
`build/route-finish-next-inputs-20260916.json`; current PCIe2 remains the retained
0 DRC / 9-open partial route. All other physical holds persist. Roughly 67 GiB
is free; no material deletion was performed. Do not rerun the exhausted local
dogbone/alternate-ground/work-budget experiments or an unchanged placement wave.
